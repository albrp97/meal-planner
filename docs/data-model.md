# Data model

The MVP uses SQLite and plain JSON text columns for tags and score breakdowns. This keeps the database inspectable while avoiding an ORM dependency.

## Tables

| Table | Purpose |
| --- | --- |
| `ingredients` | Canonical ingredient catalog with category, default unit, tags, nutrition, source, and notes. |
| `ingredient_aliases` | Spanish/English/Czech or shopping-name aliases mapped to canonical ingredient IDs. |
| `prices` | Purchase or estimated price records with package size and normalized price fields. |
| `recipes` | Raw source text, multi-serving batch plan servings, status, tags, procedure, and curation decisions. |
| `recipe_ingredients` | Normalized recipe lines with quantity, unit, grams/ml/unit cost basis, and source notes. |
| `recipe_reviews` | LLM review results for procedure, missing ingredients, adaptations, protein status, serving notes, and curation decision. |
| `meal_history` | Accepted/rejected recommendation history with score snapshots. |
| `settings` | Small key/value metadata such as seed version. |
| `youtube_channels` | Public channel metadata for YouTube ingestion sources. |
| `youtube_playlists` | Playlist metadata linked to channels. |
| `youtube_videos` | Discovered video metadata and ingestion status. |
| `youtube_transcripts` | Cached captions, auto captions, audio transcriptions, or unavailable markers. |
| `youtube_audio_jobs` | Local audio transcription attempts, backend/model, status, and errors. |
| `youtube_extraction_runs` | LLM extraction run metadata and counts. |
| `youtube_recipe_candidates` | Reviewable extracted recipe candidates before catalog import. |
| `recipe_sources` | Links approved recipes back to YouTube videos/playlists/channels. |

## Source flags

| Flag | Meaning |
| --- | --- |
| `real_purchase` | Directly provided purchase price from Lidl Prague 2026. |
| `manual_estimate` | Practical estimate entered by the project because no real price/nutrition was provided. |
| `llm_estimate` | Reserved for future LLM-produced estimates. |
| `unknown` | Missing and not yet estimated. |

Approved zero-cost tap water is stored as `real_purchase` with `0 Kč` so it displays as verified instead of missing.

## Quantity assumptions

The app records local assumptions from the request:

- small onion: 80g
- large red pepper: 180g
- tomato on vine: 120g
- carrot: 70g
- potato: 160g
- avocado edible unit: 150g
- egg: 60g

These are centralized in `units.py` so recipe normalization can be adjusted without rewriting calculations.

## JSON imports

Import commands are intentionally strict:

- Price imports must reference existing `ingredient_id` values.
- Recipe imports must reference existing `ingredient_id` values.
- Unknown ingredients raise visible errors instead of being silently created.
- Missing recipe ingredient grams are derived through `units.py` when possible.

## Batch plan rules

- `recipes.servings` must be greater than 1.
- `recipe_ingredients` quantities cover the full planned batch/shopping list.
- Visible recipe and ingredient text should be English; source-language aliases can stay in `ingredient_aliases`.
- Ingredients mentioned in procedures, including water, salt, oil, sauces, garnishes, and seasonings, should exist as `recipe_ingredients` rows.
- Oven, rest, rise, marinade, chill, and cooking-duration details belong in `recipes.procedure`; vague source text should be completed during curation or candidate approval.
- `recipe_ingredients.grams` should be populated for non-gram lines when a conversion is known so ingredient and shopping-list displays can show gram equivalents.
- Procedure text must distinguish batch-cooked/prepped components from individually cooked components.
- Texture-sensitive recipes, such as noodles, still use multi-serving ingredient totals but mark final cooking as `Individual cook:`.
