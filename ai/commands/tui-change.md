# TUI Change Workflow

Use this workflow when changing the terminal UI, shortcuts, search, details, recipe list, recommendations, history, or shopping-list views.

## Steps

1. Read `vision.md`, `docs/quickstart.md`, and `aidd-custom/skills/meal-planner-tui/SKILL.md`.
2. Identify the exact view(s) affected in `src/meal_planner/tui.py`.
3. Preserve global escape hatches: `q` quits, `r` returns to recommendations, arrows move.
4. Update display helper tests in `tests/test_core.py`.
5. Smoke-test the real interactive command when keyboard behavior changes.
6. Update README/quickstart if user-facing shortcuts or display semantics change.

## Acceptance checklist

- No internal score shown to users.
- Selected rows are obvious.
- Numeric values are emphasized consistently.
- Search/history/details remain navigable by keyboard.
- Tests and lint pass.

