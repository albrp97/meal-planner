from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Callable

from .calculations import recipe_totals
from .llm_client import DEFAULT_MODEL
from .llm_client import ask as copilot_ask

ENRICHMENT_CONTEXT = """You are helping build a personal smart meal planner.

Review one recipe at a time for a fitness-focused batch-cooking app.

Hard requirements:
- All returned text must be English, including procedure, notes, ingredient suggestions, and decision reasons.
- Lunch/dinner recipes only.
- All cooking quantities must be practical and in grams/ml/units.
- If the procedure mentions an ingredient, that ingredient must exist in the ingredient list with a quantity. This includes water, salt, oil, flour, yeast, sugar, sauces, marinade liquids, garnishes, and dough liquids.
- Water absorbed into dough/rice/stew/sauce must be listed in ml. Water used only for boiling can stay out of the shopping list, but the procedure must still state an approximate ml amount.
- Replace vague method wording with exact cooking guidance: rest/rise/marinate/chill times, simmer/pan timings, oven temperatures in C, and bake/roast durations.
- No recipe should remain as one serving. Convert single-serving recipes into a practical multi-serving plan, usually 4 meals unless package sizes imply another natural batch size such as 6 wraps.
- The servings field means total planned meals, even when components are cooked fresh per meal.
- Explicitly identify which components should be batch cooked/prepped and which should be cooked individually per meal.
- Use procedure labels such as "Batch cook:", "Batch prep:", "Batch plan:", and "Individual cook:" so the UI can show this clearly.
- The user avoids fried food. Adapt fried recipes to baked, stewed, boiled, or sauteed with minimal oil if sensible; otherwise mark discard.
- Protein matters. A good target is around 35g protein per serving for main meals.
- If ingredients are missing, list them explicitly. Do not invent them as real prices.
- If optional/impractical ingredients appear, suggest practical substitutes.
- Keep Lidl Prague 2026 and CZK pricing context in mind, but do not fabricate real purchase prices.
- Return strict JSON only. No markdown.

JSON schema:
{
  "procedure": "clear cooking process with batch-cook/batch-prep and individual-cook guidance, explicit quantities, rest times, cooking times, and oven temperatures where relevant",
  "missing_ingredients": ["items needed but absent or unclear"],
  "suggested_ingredients": ["optional additions or substitutions"],
  "adaptation_notes": "fitness/no-fried/practicality notes",
  "protein_status": "high|good|ok|low|unknown",
  "serving_notes": "batch size and serving rationale",
  "decision_status": "approved|needs_review|discard",
  "decision_reason": "why"
}
"""


@dataclass
class RecipeReview:
    procedure: str
    missing_ingredients: list[str] = field(default_factory=list)
    suggested_ingredients: list[str] = field(default_factory=list)
    adaptation_notes: str = ""
    protein_status: str = "unknown"
    serving_notes: str = ""
    decision_status: str = "needs_review"
    decision_reason: str = ""
    raw_response: str = ""

    @classmethod
    def from_json(cls, raw: str) -> RecipeReview:
        data = _loads_json_object(raw)
        required = (
            "procedure",
            "missing_ingredients",
            "suggested_ingredients",
            "adaptation_notes",
            "protein_status",
            "serving_notes",
            "decision_status",
            "decision_reason",
        )
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"LLM review missing fields: {', '.join(missing)}")
        decision = str(data["decision_status"])
        if decision not in {"approved", "needs_review", "discard"}:
            raise ValueError(f"Invalid decision_status: {decision}")
        protein = str(data["protein_status"])
        if protein not in {"high", "good", "ok", "low", "unknown"}:
            raise ValueError(f"Invalid protein_status: {protein}")
        return cls(
            procedure=str(data["procedure"]),
            missing_ingredients=[str(item) for item in data["missing_ingredients"]],
            suggested_ingredients=[str(item) for item in data["suggested_ingredients"]],
            adaptation_notes=str(data["adaptation_notes"]),
            protein_status=protein,
            serving_notes=str(data["serving_notes"]),
            decision_status=decision,
            decision_reason=str(data["decision_reason"]),
            raw_response=raw,
        )


def _loads_json_object(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("LLM review must be a JSON object.")
    return data


def recipe_payload(conn: sqlite3.Connection, recipe_id: str) -> str:
    recipe = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if recipe is None:
        raise LookupError(recipe_id)
    ingredients = conn.execute(
        """
        SELECT ri.display_name, ri.quantity, ri.unit, ri.grams, i.name
        FROM recipe_ingredients ri
        JOIN ingredients i ON i.id = ri.ingredient_id
        WHERE ri.recipe_id = ?
        ORDER BY ri.id
        """,
        (recipe_id,),
    ).fetchall()
    totals = recipe_totals(conn, recipe_id)
    payload = {
        "id": recipe["id"],
        "name": recipe["name"],
        "status": recipe["status"],
        "servings": recipe["servings"],
        "raw_source": recipe["raw_source"],
        "current_procedure": recipe["procedure"],
        "current_protein_status": recipe["protein_status"],
        "ingredients": [
            {
                "name": row["name"],
                "display_name": row["display_name"],
                "quantity": row["quantity"],
                "unit": row["unit"],
                "grams": row["grams"],
            }
            for row in ingredients
        ],
        "computed_totals": {
            "cost_czk": round(totals["cost_czk"], 2),
            "cost_per_serving_czk": round(totals["cost_per_serving_czk"], 2),
            "kcal_per_serving": round(totals["kcal_per_serving"], 1),
            "protein_per_serving_g": round(totals["protein_per_serving_g"], 1),
            "carbs_per_serving_g": round(totals["carbs_per_serving_g"], 1),
            "fat_per_serving_g": round(totals["fat_per_serving_g"], 1),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def enrich_recipe(
    conn: sqlite3.Connection,
    recipe_id: str,
    ask: Callable[[str, str], str] = copilot_ask,
    model: str = DEFAULT_MODEL,
) -> RecipeReview:
    prompt = "Review and improve this recipe for the meal planner:\n\n" + recipe_payload(conn, recipe_id)
    raw = ask(prompt, ENRICHMENT_CONTEXT)
    review = RecipeReview.from_json(raw)
    save_review(conn, recipe_id, review, model)
    return review


def save_review(conn: sqlite3.Connection, recipe_id: str, review: RecipeReview, model: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO recipe_reviews
        (recipe_id, reviewed_at, model, procedure, missing_ingredients, suggested_ingredients,
         adaptation_notes, protein_status, serving_notes, decision_status, decision_reason, raw_response)
        VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recipe_id,
            model,
            review.procedure,
            json.dumps(review.missing_ingredients, ensure_ascii=False),
            json.dumps(review.suggested_ingredients, ensure_ascii=False),
            review.adaptation_notes,
            review.protein_status,
            review.serving_notes,
            review.decision_status,
            review.decision_reason,
            review.raw_response,
        ),
    )
    conn.execute(
        """
        UPDATE recipes
        SET procedure = ?, protein_status = ?, decision_status = ?, decision_reason = ?
        WHERE id = ?
        """,
        (review.procedure, review.protein_status, review.decision_status, review.decision_reason, recipe_id),
    )
    conn.commit()


NUTRITION_CONTEXT = """You are a nutrition database assistant.
Given a list of food ingredients, return their approximate nutritional values per 100g as JSON.
Use standard USDA/nutritional database values. Round to 1 decimal place.
Return ONLY a JSON array with no markdown, no explanation, matching this schema exactly:
[{"id": "<ingredient_id>", "kcal": <number>, "protein": <number>, "carbs": <number>, "fat": <number>}, ...]
For water and zero-calorie items like salt, use 0 for all macros.
If you truly cannot estimate an ingredient, use reasonable mid-range values for its category.
"""


def fill_missing_nutrition(
    conn: sqlite3.Connection,
    batch_size: int = 50,
    ask: Callable[[str, str], str] = copilot_ask,
    model: str = DEFAULT_MODEL,
) -> dict[str, int]:
    """Fill kcal/protein/carbs/fat for ingredients with llm_estimate source and zero values."""
    rows = conn.execute(
        """
        SELECT id, name FROM ingredients
        WHERE nutrition_source = 'llm_estimate'
        AND kcal_per_100g = 0 AND protein_per_100g = 0 AND carbs_per_100g = 0 AND fat_per_100g = 0
        ORDER BY name
        """
    ).fetchall()
    if not rows:
        return {"total": 0, "updated": 0, "batches": 0}

    updated = 0
    batches = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        items = [{"id": r["id"], "name": r["name"]} for r in batch]
        prompt = (
            "Provide approximate nutritional values per 100g for each ingredient below.\n"
            f"Return a JSON array with one object per ingredient.\n\n{json.dumps(items, ensure_ascii=False)}"
        )
        raw = ask(prompt, NUTRITION_CONTEXT, model)
        text = raw.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            results = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(results, list):
            continue
        for entry in results:
            if not isinstance(entry, dict) or "id" not in entry:
                continue
            try:
                conn.execute(
                    """
                    UPDATE ingredients
                    SET kcal_per_100g = ?, protein_per_100g = ?, carbs_per_100g = ?, fat_per_100g = ?
                    WHERE id = ?
                    """,
                    (
                        float(entry.get("kcal", 0)),
                        float(entry.get("protein", 0)),
                        float(entry.get("carbs", 0)),
                        float(entry.get("fat", 0)),
                        entry["id"],
                    ),
                )
                updated += conn.execute("SELECT changes()").fetchone()[0]
            except (TypeError, ValueError):
                continue
        conn.commit()
        batches += 1
    return {"total": len(rows), "updated": updated, "batches": batches}


def recipe_ids_for_enrichment(conn: sqlite3.Connection, only_missing: bool = False) -> list[str]:
    if only_missing:
        rows = conn.execute(
            """
            SELECT r.id
            FROM recipes r
            LEFT JOIN recipe_reviews rr ON rr.recipe_id = r.id
            WHERE rr.recipe_id IS NULL
            ORDER BY r.status, r.name
            """
        ).fetchall()
    else:
        rows = conn.execute("SELECT id FROM recipes ORDER BY status, name").fetchall()
    return [row["id"] for row in rows]


def enrich_recipes(
    conn: sqlite3.Connection,
    recipe_ids: Iterable[str] | None = None,
    only_missing: bool = False,
    ask: Callable[[str, str], str] = copilot_ask,
    model: str = DEFAULT_MODEL,
) -> list[dict[str, object]]:
    ids = list(recipe_ids) if recipe_ids else recipe_ids_for_enrichment(conn, only_missing=only_missing)
    results = []
    for recipe_id in ids:
        review = enrich_recipe(conn, recipe_id, ask=ask, model=model)
        results.append(
            {
                "recipe_id": recipe_id,
                "decision_status": review.decision_status,
                "protein_status": review.protein_status,
                "missing_ingredients": review.missing_ingredients,
            }
        )
    return results
