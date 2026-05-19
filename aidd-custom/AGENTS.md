# Meal Planner Agent Overrides

These instructions override generic AIDD behavior for this repository.

## Before changing code

1. Read `vision.md`.
2. Read the relevant docs:
   - Recipe/data changes: `docs/data-model.md`, `docs/developer-guide.md`.
   - YouTube ingestion: `docs/youtube-ingestion.md`.
   - UI changes: `README.md`, `docs/quickstart.md`, and `src/meal_planner/tui.py`.
3. Prefer existing helpers in `calculations.py`, `recommender.py`, `youtube_ingestion.py`, `localization.py`, and `tui.py` before adding new abstractions.

## Recipe/catalog rules

- Approved recipes must be lunch/dinner appropriate, multi-serving, English-visible, and practical to cook.
- Ingredients must include grams or known gram equivalents.
- Procedures must include concrete times and temperatures where relevant.
- Water can cost `0 Kč`, but it must still be listed when used.
- Estimated prices are allowed only with explicit source flags; missing prices should be fixed.
- Deep-fried recipes should be discarded or adapted to baked, air-fryer, broiled, or minimal-oil methods.

## TUI rules

- Keep `q` as a reliable global quit key.
- Keep arrow navigation and `j`/`k` movement.
- Do not show internal recommendation scores to the user.
- Highlight selected rows and numeric values consistently.
- Preserve fast startup; avoid expensive cleanup on every command.

## Commit rules

- Never commit `.venv/`, `.coverage`, `.ruff_cache/`, SQLite databases, downloaded transcripts/audio, or local auth files.
- Include documentation updates when behavior changes.
- If creating a commit for the user, include:

```text
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

