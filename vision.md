# Smart Meal Planner Vision

## Purpose

Smart Meal Planner is a local terminal-first meal planning app that helps one fitness-focused user plan batch-cooked lunches and dinners using real Lidl Prague prices, normalized recipes, practical shopping lists, and recommendation diversity.

## Goals

1. **Practical cooking output:** Every approved recipe should be cookable from the app without opening external notes, with explicit quantities, timings, temperatures, and batch-vs-individual steps.
2. **Fitness-aware recommendations:** Recommendations should prefer high-protein, reasonably priced meals while avoiding repetitive recent categories, staples, and proteins.
3. **Local-first ownership:** Data lives locally in SQLite and can be inspected, backed up, or reset without relying on a hosted service.
4. **Fast terminal UX:** The main `meal-planner` command should open quickly and support keyboard-first browsing, searching, accepting/rejecting, details, history, and shopping lists.
5. **Controlled AI ingestion:** LLMs can extract and review recipes, but deterministic validation and human approval decide what enters the catalog.

## Non-Goals

- **No web app by default:** A browser UI is not part of the core product unless explicitly requested later.
- **No cloud sync:** The app should not require accounts, hosted databases, or background services.
- **No generic recipe dumping:** Breakfasts, snacks, desserts, sauces-only entries, components, and low-protein dishes should not be visible lunch/dinner recommendations unless explicitly adapted and approved.
- **No silent missing data:** Unknown prices, vague procedures, or missing ingredients should be surfaced and fixed, not hidden behind optimistic defaults.
- **No deep-fried default cooking:** Fried recipes must be discarded or adapted to a non-fried method with matching instructions.

## Technical Constraints

- **Stack:** Python 3.9-compatible standard-library-first CLI/TUI with optional extras for LLM and YouTube ingestion.
- **Storage:** SQLite in `~/.local/share/meal-planner/meal_planner.sqlite3`.
- **UI:** ANSI terminal UI with EVA-01-inspired colors and keyboard shortcuts.
- **LLM transport:** Local Copilot OAuth flow in `llm_client.py`; no normal API-key dependency.
- **Testing:** Deterministic core logic must stay covered by unit tests. LLM/network-heavy workflows should have isolated parsing/validation tests plus explicit smoke checks.
- **Data privacy:** Do not commit live SQLite databases, OAuth tokens, downloaded audio/transcripts, or local caches.

## Users

**Primary:** A single local user cooking fitness-focused lunches and dinners in Prague.

- Shops mainly at Lidl Prague.
- Wants grams, macros, prices, and shopping lists.
- Values speed, keyboard navigation, variety, and practical batch cooking.

**Secondary:** Future AI agents maintaining the project.

- Need clear constraints to avoid bloated dependencies, unsafe ingestion, or recipe-quality regressions.
- Need reusable workflow instructions for adding YouTube channels and curating recipes.

## UX Principles

- Show useful cooking facts, not internal scores.
- Highlight selected rows clearly and color numeric values orange.
- Keep recommendation rows compact and category-diverse.
- Make recipe details complete: calories, protein/carbs/fat macros, ingredients, prices, and steps.
- Search and history navigation must never trap the user; `q` always quits.

## Success Criteria

- The app opens in under one second on a warm local database.
- Approved recipes have multi-serving batch plans and complete ingredients.
- Recommendation lists show at most one item per primary meal category.
- No approved visible recipe has missing prices or missing grams where conversion is known.
- Future YouTube ingestion can be resumed, audited, and validated without reprocessing unrelated channels.

