from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(os.environ.get("MEAL_PLANNER_HOME", "~/.local/share/meal-planner")).expanduser()
DEFAULT_DB_PATH = Path(os.environ.get("MEAL_PLANNER_DB", str(APP_DIR / "meal_planner.sqlite3"))).expanduser()
COPILOT_CONFIG_PATH = Path(os.environ.get("COPILOT_CONFIG", "~/.copilot/config.json")).expanduser()


def ensure_app_dir() -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DIR
