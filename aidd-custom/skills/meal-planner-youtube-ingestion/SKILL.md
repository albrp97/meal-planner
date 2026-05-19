---
name: meal-planner-youtube-ingestion
description: Use when ingesting recipes from YouTube channels, transcripts, descriptions, recipe pages, or audio transcription.
---

# Meal Planner YouTube Ingestion

Use this skill for channel discovery, transcript/description caching, LLM extraction, candidate review, and approval.

## Pipeline

Prefer channel-scoped commands so older backlog is not reprocessed:

```sh
.venv/bin/python -m meal_planner.cli youtube discover-channel <channel-url>
.venv/bin/python -m meal_planner.cli youtube fetch-descriptions --channel-url <channel-url>
.venv/bin/python -m meal_planner.cli youtube fetch-transcripts --channel-url <channel-url>
.venv/bin/python -m meal_planner.cli youtube fetch-auto-captions --channel-url <channel-url>
.venv/bin/python -m meal_planner.cli youtube extract-recipes --channel-url <channel-url> --workers 4 --model gpt-5.4-mini
.venv/bin/python -m meal_planner.cli youtube candidates list
```

Use audio transcription only when captions/descriptions/pages are insufficient because it is slow locally.

## Approval rules

- Approve only complete lunch/dinner recipes that meet the recipe quality contract.
- Discard breakfasts, snacks, desserts, sauces-only entries, sides/components, and low-protein recipes unless deliberately adapted into a complete meal.
- Preserve candidate validation errors; do not hide failures with success-shaped fallbacks.
- Reuse canonical ingredients and aliases whenever possible.
- After approval, audit for missing prices, missing grams, fried-method leakage, and duplicate categories.

## Validation

Run targeted tests after pipeline code changes:

```sh
.venv/bin/python -m unittest tests.test_youtube_ingestion
.venv/bin/python -m unittest tests.test_core
```

