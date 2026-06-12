# Developer guide

This document tracks what has been implemented and why. It should stay aligned with the code and the saved session plan.

## Current direction

Build a local-first Python CLI/TUI app before adding YouTube ingestion. This keeps the first milestone useful immediately: it can load the provided Lidl Prague 2026 prices, normalize the initial recipe list, recommend meals, update history, and generate shopping lists.

## Implementation choices

| Choice | Why |
| --- | --- |
| Python 3.9-compatible code | The local system reports Python 3.9.6, so the MVP avoids Python 3.10+ syntax. |
| SQLite in `~/.local/share/meal-planner` | Durable local storage without a service or cloud account. |
| Dependency-light core | The one-word command can run immediately without installing Typer/Rich/Textual first. Optional extras can be added later if the TUI outgrows ANSI rendering. |
| ANSI EVA-01 dashboard | Matches the `macbook-linux-rice` terminal aesthetic without requiring a TUI dependency. |
| Deterministic calculators | Cost, macros, recommendation scores, and shopping lists should be testable and reproducible. |
| No single-serving recipes | Stored recipes are meal plans for batch cooking. Texture-sensitive meals still use `servings > 1`, but their steps mark fresh per-meal cooking. |
| English visible text | Spanish/English sources are accepted, but displayed recipe names, ingredient names, procedures, and review notes are normalized to English. |
| Source flags | Real Lidl prices and approved zero-cost water must remain distinguishable from estimates. |
| LLM client isolated in `llm_client.py` | Copilot-backed calls are available later without coupling core calculations to network calls. |
| AIDD-style guidance | `vision.md`, `AGENTS.md`, `aidd-custom/`, and `ai/commands/` guide future AI-assisted work without adding a runtime dependency. |
| Controlled discovery | Recommendation lists with six visible slots use five ranked picks plus one deterministic daily discovery pick to avoid overly repetitive patterns without surfacing unsafe meals. |

## Implemented modules

| Module | Purpose |
| --- | --- |
| `db.py` | SQLite paths, schema creation, seed detection, and row helpers. |
| `seed_data.py` | Initial ingredient price catalog, nutrition estimates, aliases, and recipe seed data. |
| `importers.py` | JSON importers for additional price rows and recipe drafts. |
| `units.py` | Local quantity assumptions such as small onions and large peppers. |
| `calculations.py` | Recipe totals, per-serving costs/macros, and shopping-list aggregation. |
| `recommender.py` | Fitness/cost/variety recommendation scoring and history recording. |
| `curation.py` | Similarity helpers for future keep/merge/discard workflows. |
| `extraction.py` | LLM prompt and strict JSON parsing helpers for future recipe extraction. |
| `enrichment.py` | Copilot-backed recipe review for procedures, missing ingredients, protein status, serving rationale, and curation decisions. |
| `recipe_chat.py` | Detail-view Copilot Q&A and structured recipe edits using existing ingredient IDs. |
| `llm_client.py` | Adapted local Copilot client pattern from the existing `temporal` project. |
| `llm_schemas.py` | Structured recipe/ingredient validation helpers for future LLM output parsing. |
| `youtube_ingestion.py` | Channel discovery, transcript caching, audio transcription fallback hooks, candidate extraction, dedupe, and approval workflow. |
| `tui.py` | Terminal dashboard, searchable recipe catalog, past-meal navigation, detail panes, and formatted command output. |
| `cli.py` | Command routing and local app entry point. |

## AIDD-inspired workflow layer

The sibling `aidd` framework is a JavaScript/Markdown AI development system. This Python app does not need its Node runtime, server utilities, or generic scaffold files. The useful pieces have been adapted as repository-local guidance:

- `vision.md` gives agents a single source of truth for product goals, non-goals, technical constraints, and UX rules.
- `AGENTS.md` defines project-wide agent instructions and validation commands.
- `aidd-custom/AGENTS.md` and `aidd-custom/skills/` add meal-planner-specific rules for recipe curation, YouTube ingestion, and TUI work.
- `ai/commands/` provides repeatable workflow prompts for catalog audits, channel ingestion, and UI changes.

This layer is intentionally documentation-only: it improves future AI work without adding dependencies, startup cost, or runtime complexity.

## Deferred work

- Full Textual/Rich interactive app if ANSI rendering becomes too limiting.
- Manual edit screens for catalog data.
- More precise nutrition sources beyond current estimates.

## Batch cooking policy

Every recipe in the catalog must have more than one serving. If the original source is a single plate, the app scales it into a practical plan, usually four meals unless package size suggests another number such as six wraps.

Recipe procedures must explicitly mark:

- `Batch cook:` for components cooked fully in advance.
- `Batch prep:` for components prepared in advance but cooked later.
- `Batch plan:` for texture-sensitive recipes where the shopping list covers multiple meals.
- `Individual cook:` for components that should be cooked or assembled fresh per meal.

This applies to manual recipes and future YouTube transcript extraction.

## Recipe quality contract

Recipe import, extraction, curation, and approval should preserve this contract:

- Visible recipe names, ingredient names, procedures, candidate decisions, and review text are English-only.
- Ingredient quantities cover the full batch plan and use grams where possible.
- Non-gram units keep enough conversion data for the UI to display gram equivalents when known.
- Procedure-critical ingredients are explicit rows, including water, salt, oil, dough liquids, sauces, garnishes, spice mixes, and marinade components.
- Time and heat instructions are concrete: rest/rise/marinade/chill steps include durations, oven steps include temperatures in `C`, and cooking steps include practical time ranges.
- Procedures distinguish `Batch cook:`, `Batch prep:`, `Batch plan:`, and `Individual cook:` work.
- Price rows carry a source flag. `real_purchase` means real Lidl/approved price data; approved tap water is stored as `0 Kč`; estimates use `manual_estimate` or `llm_estimate`.
- Candidate validation should fail visibly rather than approving incomplete recipes.

## LLM transport

The app does not use a normal paid API key. `llm_client.py` follows the local Copilot pattern from `~/Documents/code/temporal/01_llm_client/copilot_client.py`:

1. Load the OAuth token from `~/.copilot/config.json`.
2. Call `https://api.business.githubcopilot.com`.
3. Use `/responses` for the default GPT model (`gpt-5.4`).
4. Keep LLM calls explicit behind commands such as `meal-planner llm enrich-recipes`.

LLM output is parsed as strict JSON and persisted. Invalid JSON or missing required fields raises an error instead of silently accepting a bad review.

The interactive detail-view Copilot action uses the same transport but a separate structured schema. Plain questions return a message only. Explicit recipe-change requests may update recipe fields and recipe ingredient rows, but only with existing ingredient IDs; after a successful update, derived cost, macro, shopping-list, and recommendation values are recomputed from SQLite on the next render.

## Current verification state

The catalog now includes the seeded recipes plus approved YouTube-imported recipes. Recipe quality is enforced through seed curation, candidate validation, manual approval/discard decisions, and regression tests instead of relying on hidden fallbacks.

Quality gate currently used:

```sh
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/coverage run -m unittest discover -s tests
.venv/bin/coverage report
.venv/bin/python -m compileall -q src tests
.venv/bin/bandit -q -r src -c pyproject.toml
.venv/bin/pip-audit --local --skip-editable --ignore-vuln GHSA-58qw-9mgm-455v --ignore-vuln GHSA-jp4c-xjxw-mgf9 --ignore-vuln GHSA-w853-jp5j-5j7f --ignore-vuln GHSA-qmgc-5h2g-mvrw --ignore-vuln GHSA-gc5v-m9x4-r6x2 --ignore-vuln GHSA-qccp-gfcp-xxvc --ignore-vuln GHSA-mf9v-mfxr-j63j --ignore-vuln GHSA-g3gw-q23r-pgqm --ignore-vuln PYSEC-2026-196
meal-planner doctor
meal-planner recipes list
meal-planner shopping-list burrito
```

The same core checks run in GitHub Actions on Python 3.9 and 3.12. See `docs/quality-and-security.md`.
Coverage currently gates deterministic core modules. CLI routing, raw terminal UI rendering, and live Copilot transport are smoke-tested separately because they depend more on terminal/process/network behavior than pure business logic.

## Future YouTube test source

```text
https://www.youtube.com/playlist?list=PLuPXdq8cpUVwlWjUmwXAnP_Nq0OLV-wsH
```
