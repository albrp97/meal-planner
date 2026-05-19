# Catalog Audit Workflow

Use this workflow when the user asks to review, clean, categorize, approve, hide, or rebalance recipes.

## Steps

1. Read `vision.md`, `docs/developer-guide.md`, and `aidd-custom/skills/meal-planner-recipe-curation/SKILL.md`.
2. Count approved recipes by primary and secondary category using `recipe_meal_categories()`.
3. Check for missing prices, missing grams, list-like procedures, non-English visible names, and obvious components/desserts/sides in approved recommendations.
4. Inspect representative rows before changing bulk data.
5. Prefer hiding inappropriate recipes over deleting them.
6. Add deterministic tests for code-level fixes.
7. Run the relevant validation commands.

## Output

Report:

- recipes approved/hidden/changed
- category counts before/after when categories changed
- any remaining known limitations
- validation run

