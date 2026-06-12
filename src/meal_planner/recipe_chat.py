from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Callable

from .calculations import recipe_totals
from .enrichment import recipe_payload
from .llm_client import DEFAULT_MODEL
from .llm_client import ask as copilot_ask
from .units import grams_for

RECIPE_CHAT_CONTEXT = """You are the Copilot recipe assistant inside a local smart meal planner.

Help the user with one recipe at a time.

Hard rules:
- Visible text must be English.
- Answer normal cooking, nutrition, shopping, substitution, and batch-planning questions without changing the database.
- Only modify the recipe when the user explicitly asks to change, replace, scale, add, remove, rewrite, or update something.
- If you modify ingredients, return the complete new ingredient list for the recipe, not just the changed lines.
- Use only existing ingredient_id values from the provided available_ingredients list. Do not invent ingredient IDs or prices.
- Keep recipes lunch/dinner appropriate, multi-serving, grams-first, practical for batch cooking, and non-fried unless explicitly unavoidable.
- Procedure text must include concrete times/temperatures where relevant and keep Batch cook/Batch prep/Batch plan/Individual cook labels.
- Return strict JSON only. No markdown.

JSON schema:
{
  "message": "short user-facing answer explaining what you did or answering the question",
  "update": null | {
    "name": "optional new recipe name",
    "servings": 4,
    "procedure": "optional full replacement procedure",
    "tags": ["optional", "complete", "tag", "list"],
    "protein_status": "high|good|ok|low|unknown",
    "decision_status": "approved|needs_review|discard",
    "decision_reason": "optional user-facing curation note",
    "ingredients": [
      {
        "ingredient_id": "existing-id",
        "display_name": "English display name",
        "quantity": 500,
        "unit": "g",
        "grams": 500,
        "notes": "optional note"
      }
    ]
  }
}
"""

VALID_PROTEIN_STATUS = {"high", "good", "ok", "low", "unknown"}
VALID_DECISION_STATUS = {"approved", "needs_review", "discard"}


@dataclass
class RecipeChatResult:
    message: str
    updated: bool = False
    raw_response: str = ""


def _loads_json_object(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Copilot recipe response must be a JSON object.")
    return data


def _available_ingredients_payload(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, name, category, default_unit
        FROM ingredients
        ORDER BY category, name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def recipe_chat_payload(conn: sqlite3.Connection, recipe_id: str, user_request: str) -> str:
    payload = {
        "user_request": user_request,
        "recipe": json.loads(recipe_payload(conn, recipe_id)),
        "available_ingredients": _available_ingredients_payload(conn),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalized_tags(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("Recipe update tags must be a list.")
    return json.dumps([str(item).strip() for item in value if str(item).strip()], ensure_ascii=False)


def _validated_ingredient_lines(
    conn: sqlite3.Connection, recipe_id: str, ingredients: object
) -> list[tuple[str, str, str, float, str, float | None, str, str]]:
    if not isinstance(ingredients, list) or not ingredients:
        raise ValueError("Recipe update ingredients must be a non-empty list when provided.")
    out = []
    for index, line in enumerate(ingredients, start=1):
        if not isinstance(line, dict):
            raise ValueError(f"Recipe update ingredient line {index} must be an object.")
        ingredient_id = str(line.get("ingredient_id", "")).strip()
        exists = conn.execute("SELECT name FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()
        if not exists:
            raise ValueError(f"Unknown ingredient_id in recipe update: {ingredient_id}")
        quantity = float(line.get("quantity", 0))
        if quantity <= 0:
            raise ValueError(f"Ingredient quantity must be positive for {ingredient_id}.")
        unit = str(line.get("unit", "g")).strip() or "g"
        grams_value = line.get("grams")
        grams = float(grams_value) if grams_value is not None else grams_for(ingredient_id, quantity, unit)
        display_name = str(line.get("display_name") or exists["name"])
        source = str(line.get("source") or "copilot_chat")
        notes = str(line.get("notes") or "")
        out.append((recipe_id, ingredient_id, display_name, quantity, unit, grams, source, notes))
    return out


def apply_recipe_chat_update(conn: sqlite3.Connection, recipe_id: str, update: object) -> bool:
    if not isinstance(update, dict):
        raise ValueError("Recipe update must be an object or null.")
    recipe = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if recipe is None:
        raise LookupError(recipe_id)

    new_name = str(recipe["name"])
    if "name" in update and str(update["name"]).strip():
        new_name = str(update["name"]).strip()
    new_servings = int(recipe["servings"])
    if "servings" in update:
        new_servings = int(update["servings"])
        if new_servings <= 1:
            raise ValueError("Recipe updates must keep servings greater than 1.")
    new_procedure = str(recipe["procedure"])
    if "procedure" in update and str(update["procedure"]).strip():
        new_procedure = str(update["procedure"]).strip()
    new_tags = str(recipe["tags"])
    tags = _normalized_tags(update.get("tags")) if "tags" in update else None
    if tags is not None:
        new_tags = tags
    new_protein_status = str(recipe["protein_status"])
    if "protein_status" in update:
        new_protein_status = str(update["protein_status"])
        if new_protein_status not in VALID_PROTEIN_STATUS:
            raise ValueError(f"Invalid protein_status: {new_protein_status}")
    new_decision_status = str(recipe["decision_status"])
    if "decision_status" in update:
        new_decision_status = str(update["decision_status"])
        if new_decision_status not in VALID_DECISION_STATUS:
            raise ValueError(f"Invalid decision_status: {new_decision_status}")
    new_decision_reason = str(recipe["decision_reason"])
    if "decision_reason" in update:
        new_decision_reason = str(update["decision_reason"])

    recipe_fields_changed = (
        new_name != str(recipe["name"])
        or new_servings != int(recipe["servings"])
        or new_procedure != str(recipe["procedure"])
        or new_tags != str(recipe["tags"])
        or new_protein_status != str(recipe["protein_status"])
        or new_decision_status != str(recipe["decision_status"])
        or new_decision_reason != str(recipe["decision_reason"])
    )

    ingredient_lines = None
    if "ingredients" in update:
        ingredient_lines = _validated_ingredient_lines(conn, recipe_id, update["ingredients"])

    if not recipe_fields_changed and ingredient_lines is None:
        return False

    with conn:
        if recipe_fields_changed:
            conn.execute(
                """
                UPDATE recipes
                SET name = ?, servings = ?, procedure = ?, tags = ?,
                    protein_status = ?, decision_status = ?, decision_reason = ?
                WHERE id = ?
                """,
                (
                    new_name,
                    new_servings,
                    new_procedure,
                    new_tags,
                    new_protein_status,
                    new_decision_status,
                    new_decision_reason,
                    recipe_id,
                ),
            )
        if ingredient_lines is not None:
            conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
            conn.executemany(
                """
                INSERT INTO recipe_ingredients
                (recipe_id, ingredient_id, display_name, quantity, unit, grams, source, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ingredient_lines,
            )
        conn.execute("DELETE FROM recipe_reviews WHERE recipe_id = ?", (recipe_id,))
    return True


def ask_recipe_copilot(
    conn: sqlite3.Connection,
    recipe_id: str,
    user_request: str,
    ask: Callable[..., str] = copilot_ask,
    model: str = DEFAULT_MODEL,
) -> RecipeChatResult:
    raw = ask(recipe_chat_payload(conn, recipe_id, user_request), RECIPE_CHAT_CONTEXT, model=model)
    data = _loads_json_object(raw)
    message = str(data.get("message") or "").strip()
    if not message:
        raise ValueError("Copilot recipe response missing message.")
    update = data.get("update")
    updated = False
    if update is not None:
        updated = apply_recipe_chat_update(conn, recipe_id, update)
        if updated:
            totals = recipe_totals(conn, recipe_id)
            message = (
                f"{message} Recalculated: {totals['kcal_per_serving']:.0f} kcal/meal, "
                f"{totals['protein_per_serving_g']:.1f}g protein, "
                f"{totals['cost_per_serving_czk']:.2f} Kč/meal."
            )
    return RecipeChatResult(message=message, updated=updated, raw_response=raw)
