from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess  # nosec B404
import sys
import urllib.request
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from .english import translate_name, translate_text
from .extraction import extract_recipes
from .llm_client import DEFAULT_MODEL
from .llm_client import ask as copilot_ask
from .paths import APP_DIR
from .units import grams_for

CHANNEL_URL = "https://www.youtube.com/@diegodoal"
TRANSCRIPT_LANGUAGES = ("es", "en")
TRANSCRIPT_SOURCE_MANUAL = "manual_caption"
TRANSCRIPT_SOURCE_AUTO = "auto_caption"
TRANSCRIPT_SOURCE_AUDIO = "audio_transcription"
TRANSCRIPT_SOURCE_RECIPE_PAGE = "linked_recipe_page"
TRANSCRIPT_SOURCE_DESCRIPTION = "video_description"
TRANSCRIPT_SOURCE_UNAVAILABLE = "unavailable"
USABLE_TRANSCRIPT_SOURCES = (
    TRANSCRIPT_SOURCE_MANUAL,
    TRANSCRIPT_SOURCE_AUTO,
    TRANSCRIPT_SOURCE_AUDIO,
    TRANSCRIPT_SOURCE_RECIPE_PAGE,
    TRANSCRIPT_SOURCE_DESCRIPTION,
)
VIDEO_URL_TEMPLATE = "https://www.youtube.com/watch?v={video_id}"
AUDIO_CACHE_DIR = APP_DIR / "cache" / "youtube-audio"
SUBTITLE_CACHE_DIR = APP_DIR / "cache" / "youtube-subtitles"
RECIPE_WORDS = (
    "receta",
    "recipe",
    "meal",
    "chicken",
    "beef",
    "turkey",
    "protein",
    "comida",
    "cena",
    "almuerzo",
    "pollo",
    "arroz",
    "pasta",
    "curry",
    "noodles",
    "burrito",
    "pizza",
    "lentils",
    "lentejas",
)
COMMON_INGREDIENT_ALIASES = {
    "water": "agua",
    "cold water": "agua",
    "boiling water": "agua",
    "salt": "sal",
    "black pepper": "pimienta",
    "ground cumin": "comino",
    "cumin": "comino",
    "garlic": "ajo",
    "garlic clove": "ajo",
    "garlic cloves": "ajo",
    "fresh ginger": "jengibre",
    "ginger": "jengibre",
    "honey": "miel",
    "rice": "arroz-basmati",
    "jasmine rice": "arroz-basmati",
    "basmati rice": "arroz-basmati",
    "jasmine or basmati rice": "arroz-basmati",
    "cucumber": "pepino",
    "carrot": "zanahoria",
    "carrots": "zanahoria",
    "white onion": "cebolla-amarilla",
    "yellow onion": "cebolla-amarilla",
    "onion": "cebolla-amarilla",
    "red bell pepper": "pimiento-rojo",
    "soy sauce": "salsa-soja",
    "low-sodium soy sauce": "salsa-soja",
    "plain yogurt": "yogurt",
    "plain greek yogurt": "yogurt",
    "greek yogurt": "yogurt",
    "olive oil": "aceite-oliva",
    "extra-virgin olive oil": "aceite-oliva",
}
COMMON_INGREDIENT_ESTIMATES: dict[str, dict[str, object]] = {
    "chicken breast": {
        "category": "meat",
        "default_unit": "g",
        "kcal": 165.0,
        "protein": 31.0,
        "carbs": 0.0,
        "fat": 3.6,
        "price_per_kg": 189.9,
    },
    "skinless chicken breast": {
        "category": "meat",
        "default_unit": "g",
        "kcal": 165.0,
        "protein": 31.0,
        "carbs": 0.0,
        "fat": 3.6,
        "price_per_kg": 189.9,
    },
    "sweet potatoes": {
        "category": "carb",
        "default_unit": "g",
        "kcal": 86.0,
        "protein": 1.6,
        "carbs": 20.0,
        "fat": 0.1,
        "price_per_kg": 69.9,
    },
    "gochujang": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 210.0,
        "protein": 4.0,
        "carbs": 45.0,
        "fat": 3.0,
        "price_per_kg": 220.0,
    },
    "neutral oil": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 884.0,
        "protein": 0.0,
        "carbs": 0.0,
        "fat": 100.0,
        "price_per_kg": 240.0,
    },
    "oil": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 884.0,
        "protein": 0.0,
        "carbs": 0.0,
        "fat": 100.0,
        "price_per_kg": 240.0,
    },
    "sesame oil": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 884.0,
        "protein": 0.0,
        "carbs": 0.0,
        "fat": 100.0,
        "price_per_kg": 300.0,
    },
    "sesame seeds": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 573.0,
        "protein": 17.0,
        "carbs": 23.0,
        "fat": 50.0,
        "price_per_kg": 250.0,
    },
    "rice vinegar": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 18.0,
        "protein": 0.0,
        "carbs": 0.0,
        "fat": 0.0,
        "price_per_kg": 90.0,
    },
    "garlic powder": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 331.0,
        "protein": 17.0,
        "carbs": 73.0,
        "fat": 1.0,
        "price_per_kg": 350.0,
    },
    "turmeric": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 312.0,
        "protein": 10.0,
        "carbs": 67.0,
        "fat": 3.0,
        "price_per_kg": 350.0,
    },
    "chili flakes": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 318.0,
        "protein": 12.0,
        "carbs": 57.0,
        "fat": 17.0,
        "price_per_kg": 350.0,
    },
    "cornstarch": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 381.0,
        "protein": 0.3,
        "carbs": 91.0,
        "fat": 0.1,
        "price_per_kg": 90.0,
    },
    "light mayonnaise": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 300.0,
        "protein": 1.0,
        "carbs": 8.0,
        "fat": 30.0,
        "price_per_kg": 120.0,
    },
    "lime juice": {
        "category": "fruit",
        "default_unit": "g",
        "kcal": 25.0,
        "protein": 0.4,
        "carbs": 8.0,
        "fat": 0.1,
        "price_per_kg": 70.0,
    },
    "fresh mint": {
        "category": "vegetable",
        "default_unit": "g",
        "kcal": 44.0,
        "protein": 3.3,
        "carbs": 8.0,
        "fat": 0.7,
        "price_per_kg": 500.0,
    },
    "vegetable stock powder": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 220.0,
        "protein": 8.0,
        "carbs": 35.0,
        "fat": 5.0,
        "price_per_kg": 350.0,
    },
    "canned corn, drained": {
        "category": "pantry",
        "default_unit": "g",
        "kcal": 96.0,
        "protein": 3.4,
        "carbs": 21.0,
        "fat": 1.5,
        "price_per_kg": 65.0,
    },
}
LIKELY_RECIPE_PLAYLISTS = {
    "24 horas cocinando",
    "Asia Profunda",
    "Hago toda la carta",
    "Hago todos los platos clásicos",
    "Operación Navidad",
    "Platos rápidos",
    "Recetas orientales",
    "Recetas rápidas y fáciles",
    "Restaurante Chino",
    "Te monto un pollo",
    "Tuppers!",
    "¡Viva México!",
}
MEAL_TITLE_WORDS = {
    "almuerzo",
    "arroz",
    "burrito",
    "burger",
    "chicken",
    "cena",
    "comida",
    "cooking only",
    "cocinando",
    "curry",
    "dinner",
    "gyoza",
    "hamburg",
    "lasaña",
    "lasagna",
    "lunch",
    "meal",
    "noodles",
    "pasta",
    "pizza",
    "pollo",
    "recipe",
    "receta",
    "rice",
    "salad",
    "sandwich",
    "sopa",
    "soup",
    "taco",
    "tortilla",
    "tupper",
}
NON_MEAL_TITLE_WORDS = {
    "basics",
    "cheesecake",
    "comiendo",
    "consejos",
    "cookie",
    "cookies",
    "dessert",
    "eating",
    "errores",
    "ferment",
    "hummus",
    "ingredientes",
    "kitchen",
    "postre",
    "presentation",
    "regalos",
    "spices",
    "tips",
    "tricks",
    "utensil",
    "viaje",
    "vlog",
}


@dataclass
class TranscriptResult:
    language: str
    source_type: str
    text: str


@dataclass
class AudioTranscriptionResult:
    language: str
    text: str
    backend: str
    model: str
    audio_path: str = ""
    audio_hash: str = ""


@dataclass
class CandidateIngredient:
    name: str
    quantity: float
    unit: str
    grams: float | None = None
    ingredient_id: str = ""
    source: str = "llm_estimate"
    notes: str = ""


@dataclass
class RecipeCandidate:
    name: str
    meal_type: str
    servings: int
    ingredients: list[CandidateIngredient] = field(default_factory=list)
    procedure: str = ""
    decision: str = "needs_review"
    decision_reason: str = ""
    protein_status: str = "unknown"
    confidence: float = 0.0


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_channel_url(value: str) -> str:
    return value.strip().rstrip("/")


def visible_text_from_html(html: str) -> str:
    parser = VisibleTextParser()
    parser.feed(html)
    return "\n".join(parser.parts)


def channel_handle(channel_url: str) -> str:
    tail = normalize_channel_url(channel_url).rsplit("/", 1)[-1]
    return tail if tail.startswith("@") else ""


def video_url(video_id: str) -> str:
    return VIDEO_URL_TEMPLATE.format(video_id=video_id)


def yt_dlp_command() -> list[str]:
    executable = shutil.which("yt-dlp")
    if executable:
        return [executable]
    return [sys.executable, "-m", "yt_dlp"]


def yt_dlp_json(url: str) -> dict[str, object]:
    command = [
        *yt_dlp_command(),
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
        "--ignore-errors",
        url,
    ]
    try:
        completed = subprocess.run(  # nosec B603
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp is required. Install with: pip install -e '.[youtube]'") from exc
    return json.loads(completed.stdout)


def yt_dlp_video_json(video_id: str) -> dict[str, object]:
    command = [*yt_dlp_command(), "--dump-json", "--skip-download", "--no-warnings", video_url(video_id)]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)  # nosec B603
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp is required. Install with: pip install -e '.[youtube]'") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"yt-dlp metadata fetch failed for {video_id}: {detail}") from exc
    return json.loads(completed.stdout)


def download_audio(video_id: str, audio_dir: Path = AUDIO_CACHE_DIR) -> tuple[Path, str]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    command = [
        *yt_dlp_command(),
        "--no-playlist",
        "--no-warnings",
        "-f",
        "ba/bestaudio/best",
        "-o",
        str(audio_dir / "%(id)s.%(ext)s"),
        video_url(video_id),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)  # nosec B603
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp is required. Install with: pip install -e '.[youtube]'") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"yt-dlp audio download failed for {video_id}: {detail}") from exc

    candidates = sorted(audio_dir.glob(f"{video_id}.*"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError(f"yt-dlp did not produce an audio file for {video_id}")
    audio_path = candidates[0]
    return audio_path, file_hash(audio_path)


def clean_vtt_text(raw: str) -> str:
    lines = []
    previous = ""
    for line in raw.splitlines():
        text = line.strip()
        if not text or text == "WEBVTT" or text.startswith(("Kind:", "Language:")):
            continue
        if "-->" in text or text.isdigit():
            continue
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text and text != previous:
            lines.append(text)
            previous = text
    return " ".join(lines)


def fetch_transcript_with_ytdlp(video_id: str, subtitle_dir: Path = SUBTITLE_CACHE_DIR) -> TranscriptResult:
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    for old_file in subtitle_dir.glob(f"{video_id}.*.vtt"):
        old_file.unlink(missing_ok=True)
    command = [
        *yt_dlp_command(),
        "--write-auto-subs",
        "--sub-langs",
        "es-orig,es,en",
        "--sub-format",
        "vtt",
        "--skip-download",
        "--no-warnings",
        "-o",
        str(subtitle_dir / "%(id)s.%(ext)s"),
        video_url(video_id),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)  # nosec B603
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp is required. Install with Homebrew or pip install -e '.[youtube]'") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"yt-dlp subtitle fetch failed for {video_id}: {detail}") from exc

    candidates = sorted(subtitle_dir.glob(f"{video_id}.*.vtt"))
    if not candidates:
        raise LookupError(f"No yt-dlp auto captions found for {video_id}")
    preferred = candidates[0]
    text = clean_vtt_text(preferred.read_text(encoding="utf-8", errors="replace"))
    if not text:
        raise LookupError(f"yt-dlp auto captions were empty for {video_id}")
    parts = preferred.name.split(".")
    language = parts[-2] if len(parts) >= 3 else "es"
    return TranscriptResult(language=language, source_type=TRANSCRIPT_SOURCE_AUTO, text=text)


def extract_recipe_page_urls(description: str) -> list[str]:
    urls = re.findall(r"https?://(?:www\.)?diegodoal\.com/recetas/[^\s)]+", description)
    cleaned = []
    seen = set()
    for url in urls:
        normalized = url.rstrip(".,;")
        if normalized not in seen:
            cleaned.append(normalized)
            seen.add(normalized)
    return cleaned


def fetch_recipe_page_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "meal-planner/0.1"})  # nosec B310
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
        html = response.read().decode("utf-8", errors="replace")
    return visible_text_from_html(html)


def _entries(payload: dict[str, object]) -> list[dict[str, object]]:
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _entry_url(entry: dict[str, object]) -> str:
    for key in ("webpage_url", "url"):
        value = entry.get(key)
        if value:
            text = str(value)
            if text.startswith("http"):
                return text
            if len(text) == 11:
                return video_url(text)
            return text
    entry_id = str(entry.get("id", ""))
    return video_url(entry_id) if len(entry_id) == 11 else ""


def _upsert_channel(conn: sqlite3.Connection, channel_url: str, title: str = "") -> None:
    conn.execute(
        """
        INSERT INTO youtube_channels (url, handle, title, status, updated_at)
        VALUES (?, ?, ?, 'discovered', CURRENT_TIMESTAMP)
        ON CONFLICT(url) DO UPDATE SET
            handle = excluded.handle,
            title = COALESCE(NULLIF(excluded.title, ''), youtube_channels.title),
            status = 'discovered',
            updated_at = CURRENT_TIMESTAMP
        """,
        (channel_url, channel_handle(channel_url), title),
    )


def _upsert_playlist(conn: sqlite3.Connection, channel_url: str, entry: dict[str, object]) -> str | None:
    playlist_id = str(entry.get("id", "")).strip()
    if not playlist_id:
        return None
    conn.execute(
        """
        INSERT INTO youtube_playlists (id, channel_url, title, url, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            url = excluded.url,
            updated_at = CURRENT_TIMESTAMP
        """,
        (playlist_id, channel_url, str(entry.get("title", "")), _entry_url(entry)),
    )
    return playlist_id


def _upsert_video(
    conn: sqlite3.Connection,
    channel_url: str,
    entry: dict[str, object],
    playlist_id: str | None = None,
) -> str | None:
    video_id = str(entry.get("id", "")).strip()
    if not video_id or len(video_id) > 64:
        return None
    duration = entry.get("duration")
    conn.execute(
        """
        INSERT INTO youtube_videos
        (id, channel_url, playlist_id, title, url, duration, language_hints, status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'discovered', CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            playlist_id = COALESCE(youtube_videos.playlist_id, excluded.playlist_id),
            title = COALESCE(NULLIF(excluded.title, ''), youtube_videos.title),
            url = COALESCE(NULLIF(excluded.url, ''), youtube_videos.url),
            duration = COALESCE(excluded.duration, youtube_videos.duration),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            video_id,
            channel_url,
            playlist_id,
            str(entry.get("title", "")),
            _entry_url(entry) or video_url(video_id),
            int(duration) if isinstance(duration, int) else None,
            json.dumps([]),
        ),
    )
    return video_id


def looks_like_meal_video(title: str, playlist_title: str = "", duration: int | None = None) -> tuple[bool, str]:
    text = f"{title} {playlist_title}".lower()
    if any(word in text for word in NON_MEAL_TITLE_WORDS):
        return False, "metadata suggests non-lunch/dinner content"
    if playlist_title in LIKELY_RECIPE_PLAYLISTS:
        return True, "likely recipe playlist"
    if any(word in text for word in MEAL_TITLE_WORDS):
        return True, "recipe-like title"
    if duration is not None and duration < 90:
        return False, "short video without recipe-like metadata"
    return False, "metadata does not look like a lunch/dinner recipe"


def discover_channel(
    conn: sqlite3.Connection,
    channel_url: str = CHANNEL_URL,
    metadata_loader: Callable[[str], dict[str, object]] = yt_dlp_json,
    include_playlists: bool = True,
    include_shorts: bool = False,
    limit: int | None = None,
) -> dict[str, int]:
    normalized = normalize_channel_url(channel_url)
    _upsert_channel(conn, normalized)
    counts = {"playlists": 0, "videos": 0}
    seen: set[str] = set()

    if include_playlists:
        try:
            playlist_payload = metadata_loader(f"{normalized}/playlists")
        except Exception:
            playlist_payload = {}
        for playlist in _entries(playlist_payload):
            playlist_id = _upsert_playlist(conn, normalized, playlist)
            if not playlist_id:
                continue
            counts["playlists"] += 1
            playlist_url = _entry_url(playlist)
            if not playlist_url:
                continue
            video_payload = metadata_loader(playlist_url)
            for entry in _entries(video_payload):
                if limit is not None and counts["videos"] >= limit:
                    break
                video_id = _upsert_video(conn, normalized, entry, playlist_id)
                if video_id and video_id not in seen:
                    seen.add(video_id)
                    counts["videos"] += 1

    videos_payload = metadata_loader(f"{normalized}/videos")
    for entry in _entries(videos_payload):
        if limit is not None and counts["videos"] >= limit:
            break
        url = _entry_url(entry)
        if not include_shorts and "/shorts/" in url:
            continue
        video_id = _upsert_video(conn, normalized, entry)
        if video_id and video_id not in seen:
            seen.add(video_id)
            counts["videos"] += 1

    conn.commit()
    return counts


def videos_for_transcripts(
    conn: sqlite3.Connection, limit: int | None = None, channel_url: str | None = None
) -> list[sqlite3.Row]:
    query = """
        SELECT v.*
        FROM youtube_videos v
        WHERE NOT EXISTS (
            SELECT 1 FROM youtube_transcripts t
            WHERE t.video_id = v.id
            AND t.source_type IN (?, ?, ?, ?, ?)
        )
    """
    params: list[object] = list(USABLE_TRANSCRIPT_SOURCES)
    if channel_url:
        query += " AND v.channel_url = ?"
        params.append(channel_url)
    query += " ORDER BY v.discovered_at, v.id"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def fetch_transcript_with_api(video_id: str, languages: Sequence[str] = TRANSCRIPT_LANGUAGES) -> TranscriptResult:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError("youtube-transcript-api is required. Install with: pip install -e '.[youtube]'") from exc

    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    transcript_errors = []
    for language in languages:
        try:
            transcript = transcript_list.find_manually_created_transcript([language])
            segments = transcript.fetch()
            text = " ".join(str(segment.get("text", "")) for segment in segments)
            return TranscriptResult(language=language, source_type=TRANSCRIPT_SOURCE_MANUAL, text=text)
        except Exception as exc:
            transcript_errors.append(f"manual {language}: {exc}")
    for language in languages:
        try:
            transcript = transcript_list.find_generated_transcript([language])
            segments = transcript.fetch()
            text = " ".join(str(segment.get("text", "")) for segment in segments)
            return TranscriptResult(language=language, source_type=TRANSCRIPT_SOURCE_AUTO, text=text)
        except Exception as exc:
            transcript_errors.append(f"auto {language}: {exc}")
    detail = "; ".join(transcript_errors) if transcript_errors else "no matching transcript languages"
    raise LookupError(f"No transcript found for video {video_id}: {detail}")


def save_transcript(conn: sqlite3.Connection, video_id: str, result: TranscriptResult) -> None:
    digest = content_hash(result.text)
    conn.execute(
        """
        INSERT INTO youtube_transcripts (video_id, language, source_type, text, content_hash, fetched_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(video_id, language, source_type) DO UPDATE SET
            text = excluded.text,
            content_hash = excluded.content_hash,
            fetched_at = CURRENT_TIMESTAMP
        """,
        (video_id, result.language, result.source_type, result.text, digest),
    )
    conn.execute(
        "UPDATE youtube_videos SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        ("transcript_ready", video_id),
    )


def mark_transcript_unavailable(conn: sqlite3.Connection, video_id: str, error: str) -> None:
    conn.execute(
        """
        INSERT INTO youtube_transcripts (video_id, language, source_type, text, content_hash, fetched_at)
        VALUES (?, '', ?, ?, '', CURRENT_TIMESTAMP)
        ON CONFLICT(video_id, language, source_type) DO UPDATE SET
            text = excluded.text,
            fetched_at = CURRENT_TIMESTAMP
        """,
        (video_id, TRANSCRIPT_SOURCE_UNAVAILABLE, error),
    )
    conn.execute(
        "UPDATE youtube_videos SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        ("needs_audio_transcription", video_id),
    )


def fetch_missing_transcripts(
    conn: sqlite3.Connection,
    fetcher: Callable[[str], TranscriptResult] = fetch_transcript_with_api,
    workers: int = 4,
    limit: int | None = None,
    channel_url: str | None = None,
) -> dict[str, int]:
    videos = videos_for_transcripts(conn, limit=limit, channel_url=channel_url)
    counts = {"fetched": 0, "unavailable": 0}
    if not videos:
        return counts

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_video = {executor.submit(fetcher, row["id"]): row["id"] for row in videos}
        for future in as_completed(future_to_video):
            video_id = future_to_video[future]
            try:
                save_transcript(conn, video_id, future.result())
                counts["fetched"] += 1
            except Exception as exc:
                mark_transcript_unavailable(conn, video_id, str(exc))
                counts["unavailable"] += 1
    conn.commit()
    return counts


def fetch_ytdlp_auto_captions(
    conn: sqlite3.Connection,
    fetcher: Callable[[str], TranscriptResult] = fetch_transcript_with_ytdlp,
    workers: int = 4,
    limit: int | None = None,
    channel_url: str | None = None,
) -> dict[str, int]:
    videos = videos_needing_audio(conn, limit=limit, channel_url=channel_url)
    counts = {"fetched": 0, "unavailable": 0}
    if not videos:
        return counts
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_video = {executor.submit(fetcher, row["id"]): row["id"] for row in videos}
        for future in as_completed(future_to_video):
            video_id = future_to_video[future]
            try:
                save_transcript(conn, video_id, future.result())
                counts["fetched"] += 1
            except Exception as exc:
                mark_transcript_unavailable(conn, video_id, f"yt-dlp captions unavailable: {exc}")
                counts["unavailable"] += 1
    conn.commit()
    return counts


def videos_needing_audio(
    conn: sqlite3.Connection, limit: int | None = None, channel_url: str | None = None
) -> list[sqlite3.Row]:
    query = """
        SELECT v.*
        FROM youtube_videos v
        WHERE v.status = 'needs_audio_transcription'
        AND NOT EXISTS (
            SELECT 1 FROM youtube_transcripts t
            WHERE t.video_id = v.id AND t.source_type = ?
        )
    """
    params: list[object] = [TRANSCRIPT_SOURCE_AUDIO]
    if channel_url:
        query += " AND v.channel_url = ?"
        params.append(channel_url)
    query += " ORDER BY v.updated_at, v.id"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def prefilter_audio_candidates(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT v.id, v.title, v.duration, COALESCE(p.title, '') AS playlist_title
        FROM youtube_videos v
        LEFT JOIN youtube_playlists p ON p.id = v.playlist_id
        WHERE v.status = 'needs_audio_transcription'
        ORDER BY v.discovered_at, v.id
        """
    ).fetchall()
    counts = {"kept": 0, "skipped": 0}
    for row in rows:
        keep, reason = looks_like_meal_video(row["title"], row["playlist_title"], row["duration"])
        if keep:
            counts["kept"] += 1
            continue
        conn.execute(
            "UPDATE youtube_videos SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            ("skipped_not_recipe", row["id"]),
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (video_id, language, source_type, text, content_hash, fetched_at)
            VALUES (?, '', ?, ?, '', CURRENT_TIMESTAMP)
            ON CONFLICT(video_id, language, source_type) DO UPDATE SET
                text = excluded.text,
                fetched_at = CURRENT_TIMESTAMP
            """,
            (row["id"], TRANSCRIPT_SOURCE_UNAVAILABLE, reason),
        )
        counts["skipped"] += 1
    conn.commit()
    return counts


def videos_for_recipe_pages(conn: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    query = """
        SELECT v.*
        FROM youtube_videos v
        WHERE v.status IN ('needs_audio_transcription', 'transcription_failed')
        AND NOT EXISTS (
            SELECT 1 FROM youtube_transcripts t
            WHERE t.video_id = v.id AND t.source_type = ?
        )
        ORDER BY v.updated_at, v.id
    """
    params: list[object] = [TRANSCRIPT_SOURCE_RECIPE_PAGE]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def videos_for_descriptions(
    conn: sqlite3.Connection, limit: int | None = None, channel_url: str | None = None
) -> list[sqlite3.Row]:
    query = """
        SELECT v.*
        FROM youtube_videos v
        WHERE v.status IN ('needs_audio_transcription', 'transcription_failed', 'discovered')
        AND NOT EXISTS (
            SELECT 1 FROM youtube_transcripts t
            WHERE t.video_id = v.id AND t.source_type = ?
        )
    """
    params: list[object] = [TRANSCRIPT_SOURCE_DESCRIPTION]
    if channel_url:
        query += " AND v.channel_url = ?"
        params.append(channel_url)
    query += " ORDER BY v.updated_at, v.id"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def description_has_recipe_payload(title: str, description: str) -> bool:
    keep, _reason = looks_like_recipe_source(title, description)
    if not keep:
        return False
    return bool(
        re.search(r"\b\d+(?:[.,]\d+)?\s*g\b", description.lower())
        or re.search(r"\b(macros?|directions?|ingredients?)\b", description.lower())
    )


def save_description_transcript(conn: sqlite3.Connection, video_id: str, title: str, description: str) -> None:
    body = f"Video title: {title}\nSource: YouTube video description\n\n{description}"
    save_transcript(
        conn, video_id, TranscriptResult(language="en", source_type=TRANSCRIPT_SOURCE_DESCRIPTION, text=body)
    )


def fetch_video_descriptions(
    conn: sqlite3.Connection,
    metadata_loader: Callable[[str], dict[str, object]] = yt_dlp_video_json,
    workers: int = 4,
    limit: int | None = None,
    channel_url: str | None = None,
) -> dict[str, int]:
    videos = videos_for_descriptions(conn, limit=limit, channel_url=channel_url)
    counts = {"fetched": 0, "skipped": 0, "failed": 0}
    if not videos:
        return counts

    def fetch_one(row: sqlite3.Row) -> tuple[str, str, str]:
        metadata = metadata_loader(row["id"])
        return row["id"], str(metadata.get("title", row["title"])), str(metadata.get("description", ""))

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_video = {executor.submit(fetch_one, row): row["id"] for row in videos}
        for future in as_completed(future_to_video):
            video_id = future_to_video[future]
            try:
                found_video_id, title, description = future.result()
                if description_has_recipe_payload(title, description):
                    save_description_transcript(conn, found_video_id, title, description)
                    counts["fetched"] += 1
                else:
                    counts["skipped"] += 1
            except Exception as exc:
                mark_transcript_unavailable(conn, video_id, f"description fetch failed: {exc}")
                counts["failed"] += 1
    conn.commit()
    return counts


def save_recipe_page_transcript(conn: sqlite3.Connection, video_id: str, url: str, title: str, text: str) -> None:
    body = f"Video title: {title}\nSource recipe page: {url}\n\n{text}"
    save_transcript(
        conn, video_id, TranscriptResult(language="es", source_type=TRANSCRIPT_SOURCE_RECIPE_PAGE, text=body)
    )


def fetch_linked_recipe_pages(
    conn: sqlite3.Connection,
    metadata_loader: Callable[[str], dict[str, object]] = yt_dlp_video_json,
    page_fetcher: Callable[[str], str] = fetch_recipe_page_text,
    workers: int = 4,
    limit: int | None = None,
) -> dict[str, int]:
    videos = videos_for_recipe_pages(conn, limit=limit)
    counts = {"pages": 0, "no_link": 0, "failed": 0}
    if not videos:
        return counts

    def fetch_one(row: sqlite3.Row) -> tuple[str, str, str, str]:
        metadata = metadata_loader(row["id"])
        description = str(metadata.get("description", ""))
        title = str(metadata.get("title", row["title"]))
        urls = extract_recipe_page_urls(description)
        if not urls:
            raise LookupError("no linked diegodoal.com recipe page")
        url = urls[0]
        return row["id"], url, title, page_fetcher(url)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_video = {executor.submit(fetch_one, row): row["id"] for row in videos}
        for future in as_completed(future_to_video):
            video_id = future_to_video[future]
            try:
                found_video_id, url, title, text = future.result()
                save_recipe_page_transcript(conn, found_video_id, url, title, text)
                counts["pages"] += 1
            except LookupError:
                counts["no_link"] += 1
            except Exception as exc:
                mark_transcript_unavailable(conn, video_id, f"linked recipe page failed: {exc}")
                counts["failed"] += 1
    conn.commit()
    return counts


def transcribe_audio_faster_whisper(video_id: str) -> AudioTranscriptionResult:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is required. Install with: pip install -e '.[transcribe]'") from exc

    audio_path, digest = download_audio(video_id)
    model_name = os.environ.get("MEAL_PLANNER_WHISPER_MODEL", "base")
    device = os.environ.get("MEAL_PLANNER_WHISPER_DEVICE", "auto")
    compute_type = os.environ.get("MEAL_PLANNER_WHISPER_COMPUTE_TYPE", "")
    keep_audio = os.environ.get("MEAL_PLANNER_KEEP_AUDIO", "").lower() in {"1", "true", "yes"}

    kwargs = {"device": device}
    if compute_type:
        kwargs["compute_type"] = compute_type
    try:
        model = WhisperModel(model_name, **kwargs)
        segments, info = model.transcribe(str(audio_path))
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    finally:
        if not keep_audio:
            audio_path.unlink(missing_ok=True)

    if not text:
        raise RuntimeError(f"faster-whisper produced an empty transcript for {video_id}")

    return AudioTranscriptionResult(
        language=getattr(info, "language", "") or "unknown",
        text=text,
        backend="faster-whisper",
        model=model_name,
        audio_path=str(audio_path) if keep_audio else "",
        audio_hash=digest,
    )


def save_audio_transcription(conn: sqlite3.Connection, video_id: str, result: AudioTranscriptionResult) -> None:
    conn.execute(
        """
        INSERT INTO youtube_audio_jobs
        (video_id, audio_path, audio_hash, backend, model, status, error, finished_at)
        VALUES (?, ?, ?, ?, ?, 'completed', '', CURRENT_TIMESTAMP)
        """,
        (video_id, result.audio_path, result.audio_hash, result.backend, result.model),
    )
    save_transcript(
        conn,
        video_id,
        TranscriptResult(language=result.language, source_type=TRANSCRIPT_SOURCE_AUDIO, text=result.text),
    )


def mark_audio_failed(conn: sqlite3.Connection, video_id: str, error: str, backend: str = "") -> None:
    conn.execute(
        """
        INSERT INTO youtube_audio_jobs
        (video_id, backend, status, error, finished_at)
        VALUES (?, ?, 'failed', ?, CURRENT_TIMESTAMP)
        """,
        (video_id, backend, error),
    )
    conn.execute(
        "UPDATE youtube_videos SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        ("transcription_failed", video_id),
    )


def transcribe_missing_audio(
    conn: sqlite3.Connection,
    transcriber: Callable[[str], AudioTranscriptionResult] = transcribe_audio_faster_whisper,
    workers: int = 1,
    limit: int | None = None,
) -> dict[str, int]:
    videos = videos_needing_audio(conn, limit=limit)
    counts = {"transcribed": 0, "failed": 0}
    if not videos:
        return counts
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_video = {executor.submit(transcriber, row["id"]): row["id"] for row in videos}
        for future in as_completed(future_to_video):
            video_id = future_to_video[future]
            try:
                save_audio_transcription(conn, video_id, future.result())
                counts["transcribed"] += 1
            except Exception as exc:
                mark_audio_failed(conn, video_id, str(exc))
                counts["failed"] += 1
    conn.commit()
    return counts


def transcript_rows_for_extraction(
    conn: sqlite3.Connection, limit: int | None = None, channel_url: str | None = None
) -> list[sqlite3.Row]:
    query = """
        SELECT t.*, v.title, v.url
        FROM youtube_transcripts t
        JOIN youtube_videos v ON v.id = t.video_id
        WHERE t.source_type IN (?, ?, ?, ?, ?)
        AND NOT EXISTS (
            SELECT 1 FROM youtube_recipe_candidates c WHERE c.video_id = t.video_id AND c.status != 'failed'
        )
    """
    params: list[object] = list(USABLE_TRANSCRIPT_SOURCES)
    if channel_url:
        query += " AND v.channel_url = ?"
        params.append(channel_url)
    query += " ORDER BY t.fetched_at, t.video_id"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def looks_like_recipe_source(title: str, transcript: str) -> tuple[bool, str]:
    haystack = f"{title} {transcript[:2000]}".lower()
    if any(word in haystack for word in RECIPE_WORDS):
        return True, ""
    return False, "No obvious recipe keywords in title/transcript."


def candidate_from_extracted(recipe: object) -> RecipeCandidate:
    ingredients = [
        CandidateIngredient(
            name=translate_name(ingredient.name, title=False),
            quantity=ingredient.quantity,
            unit=ingredient.unit,
            grams=ingredient.grams,
            source=ingredient.source,
            notes=ingredient.notes,
        )
        for ingredient in recipe.ingredients
    ]
    return RecipeCandidate(
        name=translate_name(recipe.name, title=True),
        meal_type=recipe.meal_type,
        servings=recipe.servings,
        ingredients=ingredients,
        procedure=translate_text(recipe.procedure),
        decision=recipe.decision,
        decision_reason=recipe.decision_reason,
    )


def validate_candidate(candidate: RecipeCandidate) -> None:
    if candidate.servings <= 1:
        raise ValueError(f"Candidate recipe must have more than one serving: {candidate.name}")
    if not candidate.ingredients:
        raise ValueError(f"Candidate recipe has no ingredients: {candidate.name}")
    if "Batch " not in candidate.procedure and "Individual cook:" not in candidate.procedure:
        raise ValueError(f"Candidate recipe is missing batch/individual cooking guidance: {candidate.name}")
    ingredient_text = " ".join(
        f"{ingredient.name} {ingredient.ingredient_id} {ingredient.notes}".lower()
        for ingredient in candidate.ingredients
    )
    procedure = candidate.procedure.lower()
    if re.search(r"\b(water|agua)\b", procedure) and not re.search(r"\b(water|agua)\b", ingredient_text):
        raise ValueError(f"Candidate recipe mentions water but does not list it as an ingredient: {candidate.name}")
    if re.search(r"\b(oven|bake|baked|roast|roasted|horno|hornear)\b", procedure) and not re.search(
        r"\b\d{2,3}\s*(?:°\s*)?c\b|maximum heat|max(?:imum)? oven|grill to maximum", procedure
    ):
        raise ValueError(f"Candidate recipe uses an oven but is missing a temperature: {candidate.name}")
    if re.search(
        r"\b(rest|rise|proof|marinate|chill|refrigerate|reposar|levar|fermentar)\b", procedure
    ) and not re.search(r"\b\d+(?:[.,]\d+)?\s*(?:-|to|a)?\s*\d*\s*(?:minutes?|mins?|hours?|hrs?|h|min)\b", procedure):
        raise ValueError(f"Candidate recipe has a rest/marinade/chill step without a duration: {candidate.name}")
    for ingredient in candidate.ingredients:
        if not ingredient.unit or ingredient.quantity <= 0:
            raise ValueError(f"Invalid ingredient quantity in {candidate.name}: {ingredient.name}")


def save_candidate(
    conn: sqlite3.Connection, video_id: str, candidate: RecipeCandidate, status: str = "pending_review"
) -> int:
    validate_candidate(candidate)
    payload = json.dumps(asdict(candidate), ensure_ascii=False)
    cursor = conn.execute(
        """
        INSERT INTO youtube_recipe_candidates
        (video_id, recipe_name, status, candidate_json, duplicate_recipe_ids, error, updated_at)
        VALUES (?, ?, ?, ?, '[]', '', CURRENT_TIMESTAMP)
        """,
        (video_id, candidate.name, status, payload),
    )
    return int(cursor.lastrowid)


def mark_video_skipped(conn: sqlite3.Connection, video_id: str, reason: str) -> None:
    conn.execute(
        "UPDATE youtube_videos SET status = ?, skip_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        ("skipped", reason, video_id),
    )


def extract_candidates(
    conn: sqlite3.Connection,
    ask: Callable[[str, str], str] = copilot_ask,
    workers: int = 2,
    limit: int | None = None,
    model: str = DEFAULT_MODEL,
    channel_url: str | None = None,
) -> dict[str, int]:
    rows = transcript_rows_for_extraction(conn, limit=limit, channel_url=channel_url)
    source = f"youtube_transcripts:{channel_url}" if channel_url else "youtube_transcripts"
    run = conn.execute(
        """
        INSERT INTO youtube_extraction_runs (source, model, workers, status)
        VALUES (?, ?, ?, 'running')
        """,
        (source, model, workers),
    )
    run_id = int(run.lastrowid)
    counts = {"videos": 0, "candidates": 0, "skipped": 0, "failed": 0}

    def process(row: sqlite3.Row) -> tuple[str, list[RecipeCandidate], str]:
        keep, reason = looks_like_recipe_source(str(row["title"]), str(row["text"]))
        if not keep:
            return str(row["video_id"]), [], reason
        model_ask = (lambda prompt, context: ask(prompt, context, model)) if ask is copilot_ask else ask
        extracted = extract_recipes(str(row["text"]), ask=model_ask)
        return str(row["video_id"]), [candidate_from_extracted(recipe) for recipe in extracted], ""

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_row = {executor.submit(process, row): row for row in rows}
        for future in as_completed(future_to_row):
            row = future_to_row[future]
            video_id = str(row["video_id"])
            counts["videos"] += 1
            try:
                result_video_id, candidates, skip_reason = future.result()
                if skip_reason:
                    mark_video_skipped(conn, result_video_id, skip_reason)
                    counts["skipped"] += 1
                    continue
                conn.execute(
                    """
                    UPDATE youtube_recipe_candidates
                    SET status = 'superseded', updated_at = CURRENT_TIMESTAMP
                    WHERE video_id = ? AND status = 'failed'
                    """,
                    (result_video_id,),
                )
                for candidate in candidates:
                    save_candidate(conn, result_video_id, candidate)
                    counts["candidates"] += 1
                conn.execute(
                    "UPDATE youtube_videos SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    ("extracted", result_video_id),
                )
            except Exception as exc:
                counts["failed"] += 1
                conn.execute(
                    """
                    INSERT INTO youtube_recipe_candidates
                    (video_id, recipe_name, status, candidate_json, error, updated_at)
                    VALUES (?, '', 'failed', '{}', ?, CURRENT_TIMESTAMP)
                    """,
                    (video_id, str(exc)),
                )
    conn.execute(
        """
        UPDATE youtube_extraction_runs
        SET status = 'completed', finished_at = CURRENT_TIMESTAMP, counts = ?
        WHERE id = ?
        """,
        (json.dumps(counts), run_id),
    )
    conn.commit()
    return counts


def candidate_rows(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status:
        return conn.execute(
            "SELECT * FROM youtube_recipe_candidates WHERE status = ? ORDER BY id",
            (status,),
        ).fetchall()
    return conn.execute("SELECT * FROM youtube_recipe_candidates ORDER BY id").fetchall()


def load_candidate(row: sqlite3.Row) -> RecipeCandidate:
    data = json.loads(row["candidate_json"])
    ingredients = [CandidateIngredient(**item) for item in data.get("ingredients", [])]
    data["ingredients"] = ingredients
    return RecipeCandidate(**data)


def slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text or "youtube-recipe"


def ingredient_lookup_keys(name: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", name.strip().lower())
    simplified = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    keys = [normalized]
    if simplified and simplified not in keys:
        keys.append(simplified)
    if simplified.endswith("s") and simplified[:-1] not in keys:
        keys.append(simplified[:-1])
    return keys


def existing_ingredient_id(conn: sqlite3.Connection, name: str) -> str | None:
    keys = ingredient_lookup_keys(name)
    for key in keys:
        common = COMMON_INGREDIENT_ALIASES.get(key)
        if common and conn.execute("SELECT 1 FROM ingredients WHERE id = ?", (common,)).fetchone():
            return common
    for key in keys:
        row = conn.execute("SELECT ingredient_id FROM ingredient_aliases WHERE alias = ?", (key,)).fetchone()
        if row:
            return str(row["ingredient_id"])
    for key in keys:
        row = conn.execute("SELECT id FROM ingredients WHERE lower(name) = ?", (key,)).fetchone()
        if row:
            return str(row["id"])
    return None


def estimated_price_for_unit(unit: str) -> dict[str, float | None]:
    normalized = unit.strip().lower()
    if normalized in {"ml", "milliliter", "milliliters", "l", "liter", "liters"}:
        return {"price_per_kg": None, "price_per_l": 100.0, "price_per_unit": None}
    if normalized in {"unit", "units", "unidad", "unidades"}:
        return {"price_per_kg": None, "price_per_l": None, "price_per_unit": 10.0}
    return {"price_per_kg": 100.0, "price_per_l": None, "price_per_unit": None}


def ensure_estimated_ingredient(conn: sqlite3.Connection, ingredient: CandidateIngredient) -> str:
    ingredient_name = translate_name(ingredient.name, title=False)
    existing = existing_ingredient_id(conn, ingredient_name)
    if existing:
        return existing
    estimate = next(
        (
            COMMON_INGREDIENT_ESTIMATES[key]
            for key in ingredient_lookup_keys(ingredient_name)
            if key in COMMON_INGREDIENT_ESTIMATES
        ),
        None,
    )
    base = slugify(ingredient_name)
    ingredient_id = base
    suffix = 2
    while conn.execute("SELECT 1 FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone():
        ingredient_id = f"{base}-{suffix}"
        suffix += 1
    default_unit = (
        str(estimate["default_unit"]) if estimate else ("g" if ingredient.grams is not None else ingredient.unit or "g")
    )
    conn.execute(
        """
        INSERT INTO ingredients
        (id, name, category, default_unit, tags, nutrition_source, kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, notes)
        VALUES (?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?)
        """,
        (
            ingredient_id,
            ingredient_name,
            str(estimate["category"]) if estimate else "youtube_estimate",
            default_unit,
            "manual_estimate" if estimate else "llm_estimate",
            float(estimate["kcal"]) if estimate else 0,
            float(estimate["protein"]) if estimate else 0,
            float(estimate["carbs"]) if estimate else 0,
            float(estimate["fat"]) if estimate else 0,
            "Estimated for Lidl Prague YouTube imports."
            if estimate
            else "Created automatically while approving a YouTube recipe candidate.",
        ),
    )
    prices = estimated_price_for_unit(default_unit)
    if estimate:
        prices = {
            "price_per_kg": float(estimate["price_per_kg"]) if estimate.get("price_per_kg") is not None else None,
            "price_per_l": float(estimate["price_per_l"]) if estimate.get("price_per_l") is not None else None,
            "price_per_unit": float(estimate["price_per_unit"]) if estimate.get("price_per_unit") is not None else None,
        }
    conn.execute(
        """
        INSERT INTO prices
        (ingredient_id, context, price_czk, package_qty, package_unit, price_per_kg, price_per_l, price_per_unit, source, notes)
        VALUES (?, 'youtube_estimate', 0, NULL, NULL, ?, ?, ?, ?, ?)
        """,
        (
            ingredient_id,
            prices["price_per_kg"],
            prices["price_per_l"],
            prices["price_per_unit"],
            "manual_estimate" if estimate else "llm_estimate",
            "Usable Lidl Prague estimate for YouTube import."
            if estimate
            else "Placeholder estimate created during bulk YouTube approval. Replace with Lidl Prague price when bought.",
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO ingredient_aliases (alias, ingredient_id) VALUES (?, ?)",
        (ingredient.name.strip().lower(), ingredient_id),
    )
    conn.execute(
        "INSERT OR IGNORE INTO ingredient_aliases (alias, ingredient_id) VALUES (?, ?)",
        (ingredient_name.strip().lower(), ingredient_id),
    )
    return ingredient_id


def recipe_similarity(conn: sqlite3.Connection, candidate: RecipeCandidate) -> list[str]:
    candidate_tokens = set(slugify(candidate.name).split("-"))
    matches: list[str] = []
    for row in conn.execute("SELECT id, name FROM recipes"):
        tokens = set(slugify(row["name"]).split("-"))
        if candidate_tokens and len(candidate_tokens & tokens) / max(1, len(candidate_tokens | tokens)) >= 0.5:
            matches.append(str(row["id"]))
    return matches


def update_candidate_duplicates(conn: sqlite3.Connection, candidate_id: int) -> list[str]:
    row = conn.execute("SELECT * FROM youtube_recipe_candidates WHERE id = ?", (candidate_id,)).fetchone()
    if row is None:
        raise LookupError(candidate_id)
    candidate = load_candidate(row)
    duplicates = recipe_similarity(conn, candidate)
    conn.execute(
        """
        UPDATE youtube_recipe_candidates
        SET duplicate_recipe_ids = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (json.dumps(duplicates), candidate_id),
    )
    conn.commit()
    return duplicates


def approve_candidate(conn: sqlite3.Connection, candidate_id: int) -> str:
    row = conn.execute("SELECT * FROM youtube_recipe_candidates WHERE id = ?", (candidate_id,)).fetchone()
    if row is None:
        raise LookupError(candidate_id)
    candidate = load_candidate(row)
    validate_candidate(candidate)
    candidate.name = translate_name(candidate.name, title=True)
    candidate.procedure = translate_text(candidate.procedure)
    for ingredient in candidate.ingredients:
        ingredient.name = translate_name(ingredient.name, title=False)
    recipe_id = slugify(candidate.name)
    suffix = 2
    base = recipe_id
    recipe_name = candidate.name
    while conn.execute("SELECT 1 FROM recipes WHERE id = ? OR name = ?", (recipe_id, recipe_name)).fetchone():
        recipe_id = f"{base}-{suffix}"
        recipe_name = f"{candidate.name} (YouTube {suffix})"
        suffix += 1
    conn.execute(
        """
        INSERT INTO recipes
        (id, name, status, meal_type, servings, raw_source, procedure, tags, source_type, protein_status, decision_status, decision_reason)
        VALUES (?, ?, 'approved', ?, ?, ?, ?, ?, 'youtube', ?, 'approved', ?)
        """,
        (
            recipe_id,
            recipe_name,
            candidate.meal_type,
            candidate.servings,
            f"YouTube candidate {candidate_id}",
            candidate.procedure,
            json.dumps(["youtube", "lunch", "dinner"]),
            candidate.protein_status,
            candidate.decision_reason,
        ),
    )
    for ingredient in candidate.ingredients:
        ingredient_id = existing_ingredient_id(conn, ingredient.name)
        if ingredient_id is None and ingredient.ingredient_id:
            exists = conn.execute("SELECT 1 FROM ingredients WHERE id = ?", (ingredient.ingredient_id,)).fetchone()
            if exists:
                ingredient_id = ingredient.ingredient_id
        if ingredient_id is None:
            ingredient_id = ensure_estimated_ingredient(conn, ingredient)
        grams = ingredient.grams
        if grams is None:
            grams = grams_for(ingredient_id, ingredient.quantity, ingredient.unit)
        conn.execute(
            """
            INSERT INTO recipe_ingredients
            (recipe_id, ingredient_id, display_name, quantity, unit, grams, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recipe_id,
                ingredient_id,
                ingredient.name,
                ingredient.quantity,
                ingredient.unit,
                grams,
                ingredient.source,
                ingredient.notes,
            ),
        )
    video = conn.execute("SELECT * FROM youtube_videos WHERE id = ?", (row["video_id"],)).fetchone()
    conn.execute(
        """
        INSERT INTO recipe_sources
        (recipe_id, source_type, youtube_video_id, youtube_playlist_id, youtube_channel_url, source_url)
        VALUES (?, 'youtube', ?, ?, ?, ?)
        """,
        (
            recipe_id,
            row["video_id"],
            video["playlist_id"] if video else None,
            video["channel_url"] if video else None,
            video["url"] if video else "",
        ),
    )
    conn.execute(
        "UPDATE youtube_recipe_candidates SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (candidate_id,),
    )
    conn.commit()
    return recipe_id


def approve_all_candidates(conn: sqlite3.Connection) -> dict[str, int]:
    rows = candidate_rows(conn, status="pending_review")
    counts = {"approved": 0, "failed": 0}
    for row in rows:
        try:
            approve_candidate(conn, int(row["id"]))
            counts["approved"] += 1
        except Exception as exc:
            conn.execute(
                """
                UPDATE youtube_recipe_candidates
                SET status = 'failed', error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (str(exc), row["id"]),
            )
            conn.commit()
            counts["failed"] += 1
    return counts


def discard_candidate(conn: sqlite3.Connection, candidate_id: int, reason: str = "") -> None:
    conn.execute(
        """
        UPDATE youtube_recipe_candidates
        SET status = 'discarded', error = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (reason, candidate_id),
    )
    conn.commit()


def merge_candidate(conn: sqlite3.Connection, candidate_id: int, recipe_id: str, reason: str = "") -> None:
    exists = conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if not exists:
        raise LookupError(f"Recipe not found for merge: {recipe_id}")
    row = conn.execute(
        "SELECT duplicate_recipe_ids FROM youtube_recipe_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    if row is None:
        raise LookupError(candidate_id)
    duplicates = set(json.loads(row["duplicate_recipe_ids"] or "[]"))
    duplicates.add(recipe_id)
    conn.execute(
        """
        UPDATE youtube_recipe_candidates
        SET status = 'merged',
            duplicate_recipe_ids = ?,
            error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (json.dumps(sorted(duplicates)), reason, candidate_id),
    )
    conn.commit()


def youtube_status(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {
        "videos": int(conn.execute("SELECT count(*) AS c FROM youtube_videos").fetchone()["c"]),
        "transcripts": int(conn.execute("SELECT count(*) AS c FROM youtube_transcripts").fetchone()["c"]),
        "candidates": int(conn.execute("SELECT count(*) AS c FROM youtube_recipe_candidates").fetchone()["c"]),
    }
    counts["pending_candidates"] = int(
        conn.execute("SELECT count(*) AS c FROM youtube_recipe_candidates WHERE status = 'pending_review'").fetchone()[
            "c"
        ]
    )
    counts["audio_failed"] = int(
        conn.execute("SELECT count(*) AS c FROM youtube_audio_jobs WHERE status = 'failed'").fetchone()["c"]
    )
    counts["audio_pending"] = int(
        conn.execute("SELECT count(*) AS c FROM youtube_videos WHERE status = 'needs_audio_transcription'").fetchone()[
            "c"
        ]
    )
    counts["skipped_not_recipe"] = int(
        conn.execute("SELECT count(*) AS c FROM youtube_videos WHERE status = 'skipped_not_recipe'").fetchone()["c"]
    )
    return counts
