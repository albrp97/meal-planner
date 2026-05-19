---
name: meal-planner-recipe-curation
description: Use when adding, approving, hiding, categorizing, pricing, or auditing recipes in Smart Meal Planner.
---

# Meal Planner Recipe Curator

Use this skill for catalog quality, recipe import, price cleanup, category changes, and recommendation inputs.

## Quality contract

An approved visible recipe must:

- Be lunch/dinner appropriate.
- Have more than one serving.
- Be written in English for all user-visible text.
- Include every procedure-critical ingredient: water, salt, oil, sauces, dough liquids, garnishes, spices, and marinades.
- Use grams where possible and store gram equivalents for non-gram units where known.
- Include exact cooking durations, rest/rise/marinade/chill durations, and oven temperatures.
- Explicitly label `Batch cook:`, `Batch prep:`, `Batch plan:`, and/or `Individual cook:` steps.
- Have a verified or estimated price for every ingredient.
- Avoid deep frying unless adapted to a non-fried method and the procedure reflects the adaptation.

## Audit checklist

1. Query visible approved recipes and check for missing prices, missing grams, list-like procedures, non-English visible names, and placeholder wording.
2. Inspect suspect categories: `uncategorized`, `sides & components`, `desserts & sweets`, and recipes with very low protein.
3. Hide components or non-main meals instead of deleting them unless the user explicitly wants deletion.
4. Add or reuse ingredient aliases instead of creating duplicate ingredient rows for common names.
5. Add tests for any reusable normalization, category, display, or validation behavior.

## Useful commands

```sh
.venv/bin/python -m meal_planner.cli recipes categories
.venv/bin/python -m meal_planner.cli recipes list --sort category
.venv/bin/python -m meal_planner.cli recipes show <recipe>
.venv/bin/python -m unittest discover -s tests
```

