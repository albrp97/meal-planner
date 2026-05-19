# Quickstart tutorial

This tutorial shows how to run the interactive meal planner locally, inspect the recipe catalog, get a recommendation, accept a meal, generate a shopping list, and quit with `q`.

## 1. Open the project

```sh
cd ~/Documents/code/meal-planner
```

The project already has a local virtualenv and command wrappers installed. The wrapper commands are:

```sh
meal-planner
meal
```

Both commands run the same app.

## 2. Check that the app is ready

```sh
meal-planner doctor
```

You should see the database path, number of ingredients, number of recipes, Lidl real-price rows, and whether the Copilot config exists.

Expected shape:

```text
meal-planner 0.1.0
database: /Users/ghiki/.local/share/meal-planner/meal_planner.sqlite3
ingredients: 46
recipes: 19 (14 approved)
real Lidl Prague 2026 price rows: 32
copilot config: found (...)
```

## 3. Open the dashboard

```sh
meal-planner
```

This opens the EVA-01 styled terminal UI.

The main screen shows recommendations, selected recipe details, and the last 5 accepted/cooked meals. Recipes in those last 5 accepted meals are excluded from new recommendations. Recipe and ingredient names are shown in English.

When six recommendations are visible, the first five are ranked picks (`R`) and one is a deterministic daily discovery pick (`D`). The discovery pick is weighted-random from safe viable meals, stays stable for the day while history is unchanged, and avoids low-protein, side/component, dessert, and recently accepted recipes.

Keyboard controls:

| Key | Action |
| --- | --- |
| `q` | Quit the program. |
| `Up` / `Down` arrows | Move through recommendations, or through recipes when the catalog is open. |
| `Enter` | Accept/cook the highlighted recommendation; in the recipe catalog, open recipe details. |
| `x` | Reject the highlighted recipe. |
| `d` | Show ingredients, costs, and cooking steps for the highlighted recommendation or catalog recipe. |
| `s` | Show the shopping list for the highlighted recipe. |
| `r` | Return to recommendations. |
| `c` | Show selectable recipe catalog. |
| `/` | Search recipes by typing in the recipe catalog; `Enter` finishes typing, `Backspace` edits, and `Ctrl+U` clears. |
| `p` | Show past accepted/cooked meals; `Enter` or `d` opens recipe details for the selected meal. |
| `i` | Show ingredient catalog. |
| `h` | Show help. |

Vim-style `j`/`k` movement and `a` to accept still work as secondary shortcuts, but arrows are the intended default.

## 4. See recommendations

```sh
meal-planner recommend --limit 6
```

Each recommendation includes:

- total batch cost and cost per meal
- protein and calories per serving
- servings and cooked count
- `R` for ranked picks or `D` for the daily discovery pick
- meal categories and variety notes when a recent meal overlaps

## 5. Inspect the recipes

```sh
meal-planner recipes list
```

The catalog is selectable in the interactive UI and can also be printed from the command line. It does not show the internal recommendation score; user-facing rows emphasize practical fields such as active sort metric, category, servings, cooked count, protein, and price per meal.

The last column shows whether the recipe has been reviewed by the LLM:

- `llm` means the recipe has a stored Copilot review in `recipe_reviews`
- `manual` means it only has manual seed data

Draft recipes are kept instead of deleted. They are incomplete and should be reviewed before cooking.

Inside the interactive UI, press `c` to open the recipe catalog, press `/` to type a recipe search, press `Enter` to finish typing, move with arrows, then press `Enter` or `d` to inspect the selected recipe. From recommendations, press `p` to jump into past meals and inspect something you cooked before.

To inspect one recipe with its ingredients and cooking steps:

```sh
meal-planner recipes show burrito
```

## 6. Generate a shopping list

For one recipe:

```sh
meal-planner shopping-list burrito
```

For multiple recipes:

```sh
meal-planner shopping-list burrito lentejas
```

The output aggregates quantities and shows the expected cost. Real Lidl purchase prices and estimates are marked separately.

## 7. Accept or reject a recommendation

Inside the UI, highlight a recipe and press `enter` or `a`.

From the command line, you can also run:

```sh
meal-planner accept burrito
```

Inside the UI, highlight a recipe and press `x`.

From the command line, you can also run:

```sh
meal-planner reject burrito --reason "too much rice today"
```

This updates meal history, so future recommendations penalize repeated staples and proteins.

## 8. Run the LLM recipe review again

Use this after changing recipes or adding new drafts:

```sh
meal-planner llm enrich-recipes --only-missing
```

To force review of all recipes:

```sh
meal-planner llm enrich-recipes
```

This calls the local Copilot-backed LLM through `~/.copilot/config.json`, stores the result in `recipe_reviews`, and updates the recipe procedure/protein/decision fields.

## 9. Reset to the built-in seed data

Warning: this recreates the local database and removes meal history.

```sh
meal-planner import seed --reset
meal-planner llm enrich-recipes
```

Use this only when you want a clean local state.

## 10. Run project checks

```sh
cd ~/Documents/code/meal-planner
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m compileall -q src tests
```
