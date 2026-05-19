# AI Agent Guidelines

This repository uses AIDD-inspired guidance for AI-assisted development. Before changing code, read `vision.md` and then the most relevant files under `aidd-custom/`.

## Project source of truth

1. `vision.md` defines product goals, non-goals, technical constraints, and UX principles.
2. `README.md` and `docs/quickstart.md` define the user-facing behavior.
3. `docs/developer-guide.md`, `docs/data-model.md`, and `docs/youtube-ingestion.md` define implementation and data-quality rules.

If a requested change conflicts with the vision or recipe quality contract, stop and ask for clarification.

## Engineering rules

- Keep the app local-first, terminal-first, and dependency-light.
- Preserve Python 3.9 compatibility.
- Do not commit local databases, virtualenvs, coverage files, caches, OAuth tokens, transcripts, or other private local artifacts.
- Keep visible recipe, ingredient, procedure, and review text in English.
- Keep all recipe quantities batch-aware, grams-first, and explicit about water, salt, oils, sauces, garnishes, and procedure-critical ingredients.
- Do not silently approve low-quality YouTube candidates. Invalid candidates should fail visibly or be discarded with a reason.
- Favor deterministic calculations and tests over hidden LLM behavior.
- UI changes must preserve keyboard-first behavior and the EVA-01 terminal aesthetic.

## Validation

For code changes, run the relevant tests first, then the full gate before finalizing when practical:

```sh
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/coverage run -m unittest discover -s tests
.venv/bin/coverage report
.venv/bin/python -m compileall -q src tests
.venv/bin/bandit -q -r src -c pyproject.toml
.venv/bin/pip-audit --local --skip-editable --ignore-vuln GHSA-58qw-9mgm-455v --ignore-vuln GHSA-jp4c-xjxw-mgf9 --ignore-vuln GHSA-w853-jp5j-5j7f --ignore-vuln GHSA-qmgc-5h2g-mvrw --ignore-vuln GHSA-gc5v-m9x4-r6x2 --ignore-vuln GHSA-qccp-gfcp-xxvc --ignore-vuln GHSA-mf9v-mfxr-j63j --ignore-vuln GHSA-g3gw-q23r-pgqm
```

## AIDD-style project customization

Read `aidd-custom/index.md` to discover project-specific skills and workflow commands. Use:

- `aidd-custom/skills/meal-planner-recipe-curation/SKILL.md` for recipe quality and catalog changes.
- `aidd-custom/skills/meal-planner-youtube-ingestion/SKILL.md` for YouTube import work.
- `aidd-custom/skills/meal-planner-tui/SKILL.md` for terminal UI work.

