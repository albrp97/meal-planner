# YouTube ingestion plan

YouTube ingestion is implemented as a staged, review-first pipeline. It discovers public channel videos/playlists, caches subtitles or locally transcribed audio, extracts recipe candidates with the Copilot-backed LLM, and keeps candidates in a review queue before they become normal recipes.

Previously imported channel:

```text
https://www.youtube.com/@diegodoal
```

Current additional target:

```text
https://www.youtube.com/@Felu
```

Saved test playlist:

```text
https://www.youtube.com/playlist?list=PLuPXdq8cpUVwlWjUmwXAnP_Nq0OLV-wsH
```

## Commands

```sh
meal-planner youtube discover-channel https://www.youtube.com/@diegodoal
meal-planner youtube fetch-transcripts --workers 4
meal-planner youtube prefilter-audio
meal-planner youtube fetch-recipe-pages --workers 4
meal-planner youtube fetch-auto-captions --workers 4
meal-planner youtube fetch-descriptions --workers 4 --channel-url https://www.youtube.com/@Felu
meal-planner youtube transcribe-missing --workers 1
meal-planner youtube extract-recipes --workers 2 --model gpt-5.4-mini
meal-planner youtube status
meal-planner youtube candidates list
meal-planner youtube candidates show <id>
meal-planner youtube candidates approve <id>
meal-planner youtube candidates approve-all
meal-planner youtube candidates discard <id> --reason "not lunch/dinner"
meal-planner youtube candidates merge <id> burrito --reason "same concept"
```

## Workflow

1. Fetch video metadata and transcripts.
2. Support Spanish and English transcript text.
3. Before audio transcription, mark videos whose metadata clearly does not look like lunch/dinner recipe content as `skipped_not_recipe`.
4. Fetch linked `diegodoal.com/recetas/...` pages from video descriptions when available; those pages usually include ingredients and method text and are preferred over audio.
5. If the transcript API and linked recipe pages are missing, fetch YouTube auto-captions with the current `yt-dlp`.
6. Cache recipe payloads written directly in video descriptions, especially for channels such as Felu that include macros, grams, and directions there.
7. If subtitles, linked recipe pages, auto-captions, and useful descriptions are missing for likely recipe videos, extract audio and transcribe locally with a configured Whisper-style backend.
8. Ask the local Copilot-backed LLM to extract only lunch/dinner recipes.
9. Normalize ingredients into grams/ml/units.
10. Convert every recipe into a multi-serving meal plan; no stored recipe should remain as one serving.
11. Add batch-vs-individual cooking guidance to the recipe steps.
12. Apply protein, no-fried-food, ingredient-substitution, and duplicate checks.
13. Save extracted recipes as reviewable candidates before they enter the approved catalog.

## Approval checklist

Before approving a YouTube candidate into the main catalog, verify the candidate satisfies the same rules as hand-written recipes:

| Rule | Required output |
| --- | --- |
| Language | All visible recipe names, ingredient names, steps, notes, and decisions are in English. |
| Servings | `servings > 1`; single-plate videos must be scaled to a practical batch plan. |
| Quantities | Ingredients cover the full batch/shopping list and use grams where possible. `ml` and `unit` lines should include gram equivalents when known. |
| Completeness | Every item used in the method is listed as an ingredient, including water, salt, oil, sauces, garnishes, and marinade components. |
| Method detail | Rest/rise/marinade/chill steps include durations; oven/roast/bake steps include temperatures in `C`; cooking steps include practical time ranges. |
| Batch guidance | Procedure uses `Batch cook:`, `Batch prep:`, `Batch plan:`, and/or `Individual cook:` labels. |
| Price source | Real Lidl/approved prices use `real_purchase`; approved tap water is `0 Kč`; estimates use `manual_estimate` or `llm_estimate`. |
| Fitness/preference | Main meals need a meaningful protein source, fried methods should be adapted, and impractical ingredients should be substituted or flagged. |
| Duplicates | Similar recipes should be kept only when they are meaningfully different; otherwise merge or discard the candidate. |

The current validation code blocks common incomplete candidates, including water mentioned in the procedure but missing from ingredients, oven steps without a temperature, and rest/marinade/chill steps without a duration.

## Audio transcription fallback

Missing subtitles do not block ingestion. Videos without usable captions move to `needs_audio_transcription` and can be processed with:

```sh
meal-planner youtube transcribe-missing --workers 1
```

The default backend is local `faster-whisper`, not a paid cloud transcription API:

```sh
.venv/bin/pip install -e '.[transcribe]'
MEAL_PLANNER_WHISPER_MODEL=base meal-planner youtube transcribe-missing --workers 1
```

Audio is downloaded under the app cache, hashed, transcribed, and deleted after a successful transcription by default. Set `MEAL_PLANNER_KEEP_AUDIO=1` only when debugging transcription failures.

## Batch-cooking rule

Every YouTube-ingested recipe must become a batch plan, even if the source video is for one plate.

| Case | Required handling |
| --- | --- |
| Fully batchable meals, such as pizza, stews, curries, empanadas, burritos, oven trays | Scale ingredients to the practical batch size and write steps as `Batch cook:`. |
| Texture-sensitive meals, such as noodles or some burger components | Keep `servings > 1`, scale the shopping list to all planned meals, and write steps as `Batch prep:` plus `Individual cook:`. |
| Mixed meals, such as pasta | Batch cook the sauce/filling, but mark pasta or final assembly as `Individual cook:` when it is better fresh. |
| Package-driven meals | Use natural package sizes when they matter, for example 6 wraps for burritos. |

## LLM prompt requirements

The extraction and enrichment prompts must require:

```text
- No recipe should remain as one serving.
- Convert single-serving source recipes into a practical multi-serving plan.
- The servings field means total planned meals, even when components are cooked fresh per meal.
- The ingredient list covers the full plan/shopping list, not just one individual cook.
- The procedure must explicitly say what is batch cooked/prepped and what is cooked individually.
- Use labels such as "Batch cook:", "Batch prep:", "Batch plan:", and "Individual cook:".
- Output English-only visible text.
- List every ingredient referenced in the procedure, including water, salt, oil, sauces, garnishes, and seasoning.
- Include exact oven temperatures in C, cooking durations, and rest/rise/marinade/chill times.
```

The current code enforces this instruction in:

- `src/meal_planner/extraction.py`
- `src/meal_planner/enrichment.py`
- `src/meal_planner/youtube_ingestion.py`

## Example extraction behavior

If a transcript describes one serving of chicken noodles, the saved recipe should become a four-meal plan:

```text
servings: 4
ingredients: total ingredients for four noodle meals
procedure:
  Batch plan: this buys and preps four portions...
  Batch prep: slice chicken and vegetables, mix sauce...
  Individual cook: cook 125g noodles fresh, cook one chicken/vegetable portion, add one sauce portion...
```
