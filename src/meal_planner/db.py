from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .paths import DEFAULT_DB_PATH, ensure_app_dir


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    ensure_app_dir()
    path = Path(db_path or DEFAULT_DB_PATH).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ingredients (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            default_unit TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            nutrition_source TEXT NOT NULL DEFAULT 'unknown',
            kcal_per_100g REAL NOT NULL DEFAULT 0,
            protein_per_100g REAL NOT NULL DEFAULT 0,
            carbs_per_100g REAL NOT NULL DEFAULT 0,
            fat_per_100g REAL NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ingredient_aliases (
            alias TEXT PRIMARY KEY,
            ingredient_id TEXT NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingredient_id TEXT NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
            context TEXT NOT NULL,
            price_czk REAL NOT NULL,
            package_qty REAL,
            package_unit TEXT,
            price_per_kg REAL,
            price_per_l REAL,
            price_per_unit REAL,
            source TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS recipes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            servings INTEGER NOT NULL,
            raw_source TEXT NOT NULL,
            procedure TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            source_type TEXT NOT NULL,
            protein_status TEXT NOT NULL,
            decision_status TEXT NOT NULL,
            decision_reason TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS recipe_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id TEXT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            ingredient_id TEXT NOT NULL REFERENCES ingredients(id),
            display_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            grams REAL,
            source TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS recipe_reviews (
            recipe_id TEXT PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
            reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            model TEXT NOT NULL,
            procedure TEXT NOT NULL,
            missing_ingredients TEXT NOT NULL DEFAULT '[]',
            suggested_ingredients TEXT NOT NULL DEFAULT '[]',
            adaptation_notes TEXT NOT NULL DEFAULT '',
            protein_status TEXT NOT NULL DEFAULT 'unknown',
            serving_notes TEXT NOT NULL DEFAULT '',
            decision_status TEXT NOT NULL,
            decision_reason TEXT NOT NULL DEFAULT '',
            raw_response TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id TEXT NOT NULL REFERENCES recipes(id),
            action TEXT NOT NULL,
            servings INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            score REAL,
            score_breakdown TEXT NOT NULL DEFAULT '{}',
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS youtube_channels (
            url TEXT PRIMARY KEY,
            handle TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'discovered',
            discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS youtube_playlists (
            id TEXT PRIMARY KEY,
            channel_url TEXT NOT NULL REFERENCES youtube_channels(url) ON DELETE CASCADE,
            title TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS youtube_videos (
            id TEXT PRIMARY KEY,
            channel_url TEXT NOT NULL REFERENCES youtube_channels(url) ON DELETE CASCADE,
            playlist_id TEXT REFERENCES youtube_playlists(id) ON DELETE SET NULL,
            title TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            duration INTEGER,
            language_hints TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'discovered',
            skip_reason TEXT NOT NULL DEFAULT '',
            discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS youtube_transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL REFERENCES youtube_videos(id) ON DELETE CASCADE,
            language TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL,
            text TEXT NOT NULL,
            content_hash TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(video_id, language, source_type)
        );

        CREATE TABLE IF NOT EXISTS youtube_audio_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL REFERENCES youtube_videos(id) ON DELETE CASCADE,
            audio_path TEXT NOT NULL DEFAULT '',
            audio_hash TEXT NOT NULL DEFAULT '',
            backend TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS youtube_extraction_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT '',
            workers INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            counts TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS youtube_recipe_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL REFERENCES youtube_videos(id) ON DELETE CASCADE,
            recipe_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending_review',
            candidate_json TEXT NOT NULL,
            duplicate_recipe_ids TEXT NOT NULL DEFAULT '[]',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS recipe_sources (
            recipe_id TEXT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL,
            youtube_video_id TEXT REFERENCES youtube_videos(id) ON DELETE SET NULL,
            youtube_playlist_id TEXT REFERENCES youtube_playlists(id) ON DELETE SET NULL,
            youtube_channel_url TEXT REFERENCES youtube_channels(url) ON DELETE SET NULL,
            source_url TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(recipe_id, source_type, source_url)
        );
        """
    )
    conn.commit()


def is_seeded(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM settings WHERE key = 'seed_version'").fetchone()
    return bool(row)


def reset_database(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS meal_history;
        DROP TABLE IF EXISTS recipe_reviews;
        DROP TABLE IF EXISTS recipe_ingredients;
        DROP TABLE IF EXISTS recipes;
        DROP TABLE IF EXISTS prices;
        DROP TABLE IF EXISTS ingredient_aliases;
        DROP TABLE IF EXISTS ingredients;
        DROP TABLE IF EXISTS settings;
        """
    )
    conn.commit()
    init_schema(conn)


def ensure_database(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    if not is_seeded(conn):
        from .seed_data import seed_database

        seed_database(conn)
    from .seed_data import apply_curated_draft_fillers

    apply_curated_draft_fillers(conn)
    from .seed_data import apply_serious_recipe_curation

    apply_serious_recipe_curation(conn)
    from .localization import apply_english_labels

    apply_english_labels(conn)
    from .seed_data import apply_recipe_quality_curation

    apply_recipe_quality_curation(conn)


def fetch_one(conn: sqlite3.Connection, query: str, params: Iterable[object] = ()) -> sqlite3.Row:
    row = conn.execute(query, tuple(params)).fetchone()
    if row is None:
        raise LookupError("No row found")
    return row


def find_recipe(conn: sqlite3.Connection, query: str) -> sqlite3.Row:
    normalized = query.strip().lower()
    row = conn.execute("SELECT * FROM recipes WHERE lower(id) = ?", (normalized,)).fetchone()
    if row:
        return row
    row = conn.execute(
        "SELECT * FROM recipes WHERE lower(name) LIKE ? ORDER BY length(name) LIMIT 1",
        (f"%{normalized}%",),
    ).fetchone()
    if row:
        return row
    raise LookupError(f"Recipe not found: {query}")
