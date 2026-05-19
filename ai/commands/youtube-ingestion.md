# YouTube Ingestion Workflow

Use this workflow when adding recipes from a new YouTube channel or finishing a channel backlog.

## Steps

1. Read `vision.md`, `docs/youtube-ingestion.md`, and `aidd-custom/skills/meal-planner-youtube-ingestion/SKILL.md`.
2. Run channel-scoped discovery and source caching.
3. Prefer descriptions, linked recipe pages, manual/generated captions, and auto-captions before local audio transcription.
4. Extract candidates with a channel filter.
5. Review every pending candidate:
   - approve only complete lunch/dinner meals
   - discard breakfast/snack/dessert/side/component entries
   - adapt fried recipes only if the procedure and ingredients are truly non-fried
6. Audit the approved rows for missing prices/grams, duplicate ingredients, category imbalance, and visible language problems.
7. Run targeted YouTube and core tests.

## Useful command skeleton

```sh
CHANNEL="https://www.youtube.com/@example"
.venv/bin/python -m meal_planner.cli youtube discover-channel "$CHANNEL"
.venv/bin/python -m meal_planner.cli youtube fetch-descriptions --channel-url "$CHANNEL"
.venv/bin/python -m meal_planner.cli youtube fetch-transcripts --channel-url "$CHANNEL"
.venv/bin/python -m meal_planner.cli youtube fetch-auto-captions --channel-url "$CHANNEL"
.venv/bin/python -m meal_planner.cli youtube extract-recipes --channel-url "$CHANNEL" --workers 4 --model gpt-5.4-mini
```

