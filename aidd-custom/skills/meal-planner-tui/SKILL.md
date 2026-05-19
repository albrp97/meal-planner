---
name: meal-planner-tui
description: Use when changing the meal planner terminal UI, keyboard controls, display rows, color emphasis, search, history, details, or shopping-list rendering.
---

# Meal Planner TUI Designer

Use this skill for `src/meal_planner/tui.py` and related CLI display changes.

## UX rules

- Keep the UI terminal-first, fast, and keyboard-only friendly.
- Preserve `q` as global quit, arrows and `j`/`k` for movement, and `r` for recommendations.
- Do not show internal recommendation scores in user-facing views.
- Recommendations and recipe catalog rows should emphasize practical metrics: cost, protein, calories/macros, servings, cooked count, category, and price-source markers.
- Selected rows should be visually distinct.
- Numeric values should be orange where practical.
- Detail views should show calories and protein/carbs/fat macros, not just protein.
- Search mode must never trap the user; `q` exits and `Enter` finishes typing while keeping the filter.

## Validation

For display helpers, add or update tests in `tests/test_core.py`. For interactive behavior, smoke-test with the actual CLI when possible:

```sh
.venv/bin/python -m unittest tests.test_core
.venv/bin/python -m meal_planner.cli
```

