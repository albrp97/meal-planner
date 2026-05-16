from __future__ import annotations

import json
from typing import Callable

from .llm_schemas import ExtractedRecipe

SYSTEM_CONTEXT = """You extract lunch/dinner batch-cooking recipes for a personal fitness meal planner.

Rules:
- Input may be Spanish or English.
- Return strict JSON only: a list of recipe objects.
- All output text must be English, including recipe names, ingredient names, procedures, notes, and decisions. Translate Spanish source content to English.
- Keep only lunch/dinner recipes.
- Normalize ingredients to grams/ml/units.
- Prefer grams for cooking precision.
- Every ingredient referenced by the procedure must appear in the ingredient list with a quantity, including water, salt, oil, dough liquids, marinade liquids, garnishes, and sauces.
- Water used for dough, rice absorption, stews, sauces, marinades, or soaking must be listed in ml. If water is only discarded boiling water, still mention the approximate ml in the procedure.
- Procedures must include practical durations and heat settings: rest/rise/marinate/chill times, simmer/pan times, and oven temperatures in C plus bake/roast minutes.
- No extracted recipe may stay as one serving. Convert single-serving source recipes into a practical multi-serving plan, usually 4 servings, unless package size implies another batch size such as 6 wraps.
- The servings field must represent total planned meals. For recipes best cooked fresh, still set servings > 1 and make the ingredient list cover all planned meals.
- The procedure must explicitly say which components are batch cooked/prepped and which components should be cooked individually per meal.
- Use clear labels in the procedure such as "Batch cook:", "Batch prep:", "Batch plan:", and "Individual cook:".
- Use Lidl Prague 2026 in Czech crowns when estimating missing prices later.
- Mark inferred quantities, prices, or nutrition as estimates.
- Detect fried methods. If a recipe can be changed to baked, stewed, boiled, or sauteed with minimal oil, adapt it; otherwise mark it as discard.
- Fitness matters: mark whether protein is high/good/ok/low/unknown and suggest protein improvements when needed.
- Avoid impractical optional ingredients unless a common substitute exists.
"""


def parse_recipe_json(raw: str) -> list[ExtractedRecipe]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM did not return valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("LLM recipe extraction must return a JSON list.")
    return [ExtractedRecipe.from_dict(item) for item in data]


def build_extraction_prompt(raw_text: str) -> str:
    return (
        "Extract normalized recipes from this source text. "
        "Return JSON only and follow the schema exactly.\n\n"
        "Schema per recipe: {name, meal_type, servings, ingredients:[{name, quantity, unit, grams, source, notes}], "
        "procedure, decision, decision_reason}\n\n"
        "Batch rules: servings must be greater than 1. If the source is one serving, scale it to a practical batch. "
        "The procedure must include batch-cook/batch-prep guidance and individual-cook guidance when texture is better fresh.\n\n"
        "Completeness rules: if the procedure uses water, salt, oil, flour, yeast, sugar, sauces, marinades, or garnish, "
        "those items must appear in ingredients with explicit g/ml/unit quantities. Include exact rest/rise/marinade times, "
        "oven temperatures in C, and cooking durations instead of vague phrases like 'until done' or 'hot oven'.\n\n"
        f"Source text:\n{raw_text}"
    )


def extract_recipes(raw_text: str, ask: Callable[[str, str], str]) -> list[ExtractedRecipe]:
    response = ask(build_extraction_prompt(raw_text), SYSTEM_CONTEXT)
    return parse_recipe_json(response)
