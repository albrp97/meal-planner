# Smart Meal Planner

Local terminal-first meal planner for fitness-focused batch cooking with real Lidl Prague 2026 prices in Czech crowns.

The app stores ingredients, prices, normalized recipes, YouTube-imported recipes, meal history, internal recommendation ranking, and shopping lists in SQLite. It opens as an interactive terminal UI by default and uses deterministic Python for cost, macros, shopping lists, and recommendation ranking.

## Quick start

For a step-by-step walkthrough, see [`docs/quickstart.md`](docs/quickstart.md).

```sh
cd ~/Documents/code/meal-planner
python3 -m venv .venv
.venv/bin/pip install -e '.[llm,dev]'
.venv/bin/python -m meal_planner.cli doctor
.venv/bin/python -m meal_planner.cli recommend
.venv/bin/python -m meal_planner.cli shopping-list burrito
```

After local command wrappers are installed, use:

```sh
meal-planner
meal
```

Inside the UI, press `q` to quit, `Up`/`Down` arrows to move, `Enter` to accept the highlighted recommendation, `x` to reject, `d` for ingredients and cooking steps, `s` for the shopping list, `c` for the selectable recipe catalog, `i` for ingredients, and `h` for help. In a recipe detail view, press `m` to ask Copilot a question or request a recipe change; accepted structured changes refresh recipe totals and recommendations. In the recipe catalog, use arrows, `o` to cycle sorting, `Enter`/`d` to open details, `a` to cook the selected recipe, and `x` to delete/hide it. Vim-style `j`/`k` and `a` still work as secondary shortcuts.

## What is implemented

- SQLite database under `~/.local/share/meal-planner/meal_planner.sqlite3`.
- Real purchase price seed data from the provided Lidl Prague 2026 list.
- Recipe and ingredient names are displayed in English, while original Spanish aliases are kept internally for matching/imports.
- Manual-estimate flags for missing prices and nutrition values; approved free tap water is tracked as `0 Kč` with a verified marker.
- Recipe and ingredient prices show source markers: `✓` verified/approved, `*` estimated, `?` missing.
- Normalized recipes with grams/ml/units, gram equivalents beside non-gram amounts when known, multi-serving batch plans, batch-vs-individual cooking steps, total batch costs, per-meal costs, and macros.
- Recommendation ranking based on cost, protein, meal category, variety, batch practicality, estimate confidence, cooked count, rejections, and recent meal history.
- Recommendations show at most one recipe per meal category, prefer categories that were not recently cooked, and include a deterministic daily discovery slot (`D`) when six suggestions are shown.
- The interactive UI shows the last 5 accepted/cooked meals on the main recommendation screen and has a selectable past-meals view for reopening recipe details from history.
- Recipe catalog is selectable and searchable in the UI; when sorted, the first metric shown follows the active sort, such as `P:` for protein or `M:` for cheapest per meal.
- Recipe details include a Copilot ask/modify action for cooking questions and structured recipe edits.
- Shopping-list aggregation for one or more recipes.
- EVA-01 inspired terminal dashboard using ANSI colors compatible with the MacBook Linux Rice terminal palette.

## Core commands

| Command | Purpose |
| --- | --- |
| `meal-planner` | Open the interactive terminal UI. |
| `meal-planner doctor` | Check database, seed data, and local Copilot auth file presence. |
| `meal-planner init --reset` | Recreate the local database and seed the initial data. |
| `meal-planner recommend --limit 6` | Show category-diverse recipe recommendations with cost, protein, servings, variety notes, and one daily discovery slot. |
| `meal-planner accept <recipe>` | Mark a recipe as cooked/accepted and update history. |
| `meal-planner reject <recipe> --reason "..."` | Record a rejected recommendation. |
| `meal-planner shopping-list <recipe>` | Show quantities and expected costs for a recipe. |
| `meal-planner history --limit 20` | Show cooked/rejected recipe history. |
| `meal-planner recipes list --sort category` | List recipes sorted by name, category, cheap, calories, high-calories, protein, cooked, or recent. |
| `meal-planner recipes categories` | List the meal categories used for recommendation diversity. |
| `meal-planner recipes show <recipe>` | Show one recipe with ingredients, costs, and cooking steps. |
| `meal-planner recipes delete <recipe>` | Hide a recipe from the catalog and recommendations. |
| `meal-planner ingredients list` | List ingredient catalog entries and price source flags. |
| `meal-planner import seed --reset` | Recreate the database from the built-in Lidl/recipe seed data. |
| `meal-planner import prices <file.json>` | Import extra price rows for existing ingredients. |
| `meal-planner import recipes <file.json>` | Import extra recipe rows for existing ingredients. |
| `meal-planner similar "recipe name"` | Check whether a new recipe is close to existing recipes. |
| `meal-planner llm enrich-recipes` | Run the local Copilot-backed LLM review over recipes and persist the result. |
| `meal-planner youtube discover-channel <url>` | Discover public YouTube playlists/videos for ingestion. |
| `meal-planner youtube fetch-transcripts` | Cache Spanish/English captions where available. |
| `meal-planner youtube prefilter-audio` | Skip videos whose metadata clearly is not lunch/dinner recipe content before audio transcription. |
| `meal-planner youtube fetch-recipe-pages` | Cache linked `diegodoal.com/recetas` pages from video descriptions. |
| `meal-planner youtube fetch-auto-captions` | Fetch YouTube auto-captions through the current `yt-dlp` fallback. |
| `meal-planner youtube fetch-descriptions --channel-url https://www.youtube.com/@Felu` | Cache recipe text written directly in video descriptions before audio transcription. |
| `meal-planner youtube transcribe-missing` | Run the audio-transcription fallback for videos without captions. |
| `meal-planner youtube extract-recipes [--model gpt-5.4-mini]` | Extract reviewable recipe candidates from cached transcripts/pages. |
| `meal-planner youtube status` | Show ingestion status counts. |
| `meal-planner youtube candidates list/show/approve/approve-all/discard/merge` | Review extracted candidates before importing them, or bulk-approve them. |

## AI-assisted development

This repository includes a lightweight AIDD-style guidance layer adapted from the sibling `aidd` framework:

- [`vision.md`](vision.md) is the source of truth for product goals, non-goals, technical constraints, and UX principles.
- [`AGENTS.md`](AGENTS.md) gives AI agents project-wide rules and validation expectations.
- [`aidd-custom/`](aidd-custom/) contains meal-planner-specific skills for recipe curation, YouTube ingestion, and TUI work.
- [`ai/commands/`](ai/commands/) contains reusable workflow prompts for catalog audits, YouTube ingestion, and terminal UI changes.

Read these files before asking an AI agent to make substantial code, recipe, or ingestion changes.

## LLM usage

The app calls Copilot through `src/meal_planner/llm_client.py`, adapted from the existing `~/Documents/code/temporal/01_llm_client/copilot_client.py` project:

- reads the OAuth token from `~/.copilot/config.json`
- sends HTTPS requests to `https://api.business.githubcopilot.com`
- uses `/responses` for GPT models and `/chat/completions` for Claude-prefixed models
- defaults to model `gpt-5.4`
- requires the optional LLM dependency: `pip install -e '.[llm]'`

Run enrichment after seeding:

```sh
meal-planner llm enrich-recipes
```

The result is stored in the `recipe_reviews` table and the visible recipe procedure/protein/decision fields are updated from the LLM review.

## Design notes

- The app is personal/local only: no server, no cloud database.
- Real purchase prices stay separate from estimated values.
- Every inferred price or nutrition value carries a source flag.
- Recipes with incomplete data are stored as drafts or approved with explicit estimated ingredient/price flags instead of being silently treated as fully verified.

See `docs/developer-guide.md` for implementation notes, `docs/data-model.md` for schema details, and `docs/quality-and-security.md` for the CI, coverage, and security baseline.

## Adding new recipes

Every new recipe, whether imported manually or extracted from YouTube, must be normalized before it is approved:

1. Keep all visible recipe names, ingredient names, procedures, notes, and decision text in English. Spanish source text is allowed, but it must be translated during import.
2. Use more than one serving. A single-serving source must become a practical batch plan, usually 4 meals unless package size suggests another number.
3. Make the ingredient list cover the full batch/shopping list, not just one fresh serving.
4. Use grams by default. If a line uses `ml` or `unit`, make sure `grams` is available when the app can reasonably infer it; the UI shows values such as `325ml (325g)` or `1unit (180g)`.
5. Include every ingredient mentioned by the procedure, including water, salt, oil, dough liquids, sauces, marinades, garnish, and seasoning.
6. Include exact method details: rest/rise/marinate/chill times, oven temperatures in `C`, and cooking durations. Avoid vague steps like “hot oven” or “until done” without a practical range.
7. Mark steps with `Batch cook:`, `Batch prep:`, `Batch plan:`, and/or `Individual cook:` so it is clear what is cooked in advance and what is cooked fresh.
8. Keep fried-food adaptations explicit. Prefer baked, stewed, boiled, grilled, or minimal-oil pan methods when sensible.
9. Check price sources: `real_purchase` for real Lidl/approved zero-cost water, `manual_estimate` for estimated Lidl Prague prices, and `llm_estimate` only for LLM-created placeholders.
10. Review duplicates with `meal-planner similar "recipe name"` or the YouTube candidate merge flow before adding near-identical recipes.

## Import file shape

Price imports are JSON lists:

```json
[
  {
    "ingredient_id": "pollo",
    "price_czk": 198.9,
    "package_qty": 1,
    "package_unit": "kg",
    "price_per_kg": 198.9,
    "source": "real_purchase"
  }
]
```

Recipe imports are JSON lists using existing `ingredient_id` values:

```json
[
  {
    "id": "my-recipe",
    "name": "My Recipe",
    "status": "draft",
    "servings": 4,
    "tags": ["lunch", "dinner", "chicken"],
    "procedure": "Batch cook: cook the sauce for 20 minutes. Individual cook: boil 100g pasta per meal for 9-11 minutes and combine with one sauce portion.",
    "ingredients": [
      {"ingredient_id": "pollo", "quantity": 500, "unit": "g"},
      {"ingredient_id": "agua", "quantity": 2500, "unit": "ml"}
    ]
  }
]
```

Manual JSON recipe imports must reference existing `ingredient_id` values. YouTube candidate approval can create placeholder estimated ingredients when the source contains a new ingredient, but those placeholders should be reviewed and priced with Lidl Prague estimates before regular use.
