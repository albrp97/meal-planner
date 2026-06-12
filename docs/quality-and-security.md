# Quality and security

This project is local-first, but it should still keep a professional baseline for correctness and safety.

## Local quality gate

Run this before handing changes over:

```sh
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/coverage run -m unittest discover -s tests
.venv/bin/coverage report
.venv/bin/python -m compileall -q src tests
.venv/bin/bandit -q -r src -c pyproject.toml
.venv/bin/pip-audit --local --skip-editable --ignore-vuln GHSA-58qw-9mgm-455v --ignore-vuln GHSA-jp4c-xjxw-mgf9 --ignore-vuln GHSA-w853-jp5j-5j7f --ignore-vuln GHSA-qmgc-5h2g-mvrw --ignore-vuln GHSA-gc5v-m9x4-r6x2 --ignore-vuln GHSA-qccp-gfcp-xxvc --ignore-vuln GHSA-mf9v-mfxr-j63j --ignore-vuln GHSA-g3gw-q23r-pgqm --ignore-vuln PYSEC-2026-196
```

## What each check covers

| Check | Purpose |
| --- | --- |
| `ruff format --check` | Prevents inconsistent formatting from entering the project. |
| `ruff check` | Catches Python style, import, upgrade, and bugbear issues. |
| `coverage run` + `coverage report` | Runs the unit tests and enforces the configured coverage threshold for deterministic core modules. |
| `compileall` | Confirms all source and test files are syntactically valid. |
| `bandit` | Scans source code for common Python security issues. |
| `pip-audit` | Checks installed dependencies for known vulnerabilities. |

## CI pipeline

The GitHub Actions workflow in `.github/workflows/quality.yml` runs on pushes, pull requests, and manual dispatches. It tests both Python 3.9, matching the local machine compatibility target, and Python 3.12 for current Python support.

The audit ignores known advisories in `pip`, `filelock`, `requests`, `urllib3`, and the Python 3.9-compatible `yt-dlp` release on Python 3.9 because their fixed releases require Python 3.10+ or are otherwise outside the installable Python 3.9 toolchain for this project. The project keeps Python 3.9 support for this machine and still audits all installable project/runtime dependencies.

## Security posture

- The app stores data locally in SQLite under the user data directory.
- There is no web server, public API, or cloud database in the current architecture.
- Copilot LLM calls are explicit commands and read the existing local Copilot token from `~/.copilot/config.json`; the token is never stored in the project database.
- Missing prices and nutrition values are marked as estimates instead of being silently treated as real purchase data.
- LLM output is parsed as structured JSON and invalid responses fail visibly.
- YouTube ingestion stores public video metadata and transcript text locally. Audio fallback uses local `faster-whisper` by default; downloaded audio belongs in the app cache and is deleted after successful transcription unless `MEAL_PLANNER_KEEP_AUDIO=1` is set.

## Current limitations

- Coverage is intentionally scoped to deterministic core modules for the MVP. CLI routing, raw terminal UI rendering, and the live Copilot transport are validated separately with smoke checks and should get fuller tests as the app grows.
- The terminal UI has smoke coverage, but not full end-to-end golden-screen tests.
- Live YouTube calls are manual/integration checks; CI uses fixture-based tests so it does not depend on YouTube availability.
