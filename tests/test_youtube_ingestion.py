from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from meal_planner.db import connect, init_schema
from meal_planner.seed_data import seed_database
from meal_planner.youtube_ingestion import (
    AudioTranscriptionResult,
    CandidateIngredient,
    RecipeCandidate,
    TranscriptResult,
    approve_candidate,
    candidate_rows,
    clean_vtt_text,
    discover_channel,
    download_audio,
    extract_candidates,
    extract_recipe_page_urls,
    fetch_linked_recipe_pages,
    fetch_missing_transcripts,
    fetch_recipe_page_text,
    fetch_transcript_with_ytdlp,
    fetch_video_descriptions,
    fetch_ytdlp_auto_captions,
    file_hash,
    looks_like_meal_video,
    merge_candidate,
    prefilter_audio_candidates,
    save_candidate,
    save_recipe_page_transcript,
    transcribe_audio_faster_whisper,
    transcribe_missing_audio,
    update_candidate_duplicates,
    validate_candidate,
    visible_text_from_html,
    yt_dlp_command,
    yt_dlp_json,
    yt_dlp_video_json,
)


class YouTubeIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "youtube.sqlite3")
        init_schema(self.conn)
        seed_database(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_file_hash_reads_file_content(self) -> None:
        path = Path(self.tmp.name) / "audio.m4a"
        path.write_bytes(b"recipe audio")

        self.assertEqual(
            file_hash(path),
            "25ecd0d9147cacd9c2487cbea2f78aae0e7a36c29391926288782484b1739985",
        )

    def test_yt_dlp_json_uses_module_command(self) -> None:
        def fake_run(command, check, capture_output, text):
            self.assertIn("-m", command)
            self.assertIn("yt_dlp", command)
            self.assertTrue(check)
            self.assertTrue(capture_output)
            self.assertTrue(text)
            return SimpleNamespace(stdout='{"entries": [{"id": "VIDEO000003"}]}')

        with (
            patch("meal_planner.youtube_ingestion.shutil.which", return_value=None),
            patch("meal_planner.youtube_ingestion.subprocess.run", fake_run),
        ):
            payload = yt_dlp_json("https://youtube.com/@channel/videos")

        self.assertEqual(payload["entries"][0]["id"], "VIDEO000003")

    def test_yt_dlp_command_prefers_executable_when_available(self) -> None:
        with patch("meal_planner.youtube_ingestion.shutil.which", return_value="/opt/homebrew/bin/yt-dlp"):
            self.assertEqual(yt_dlp_command(), ["/opt/homebrew/bin/yt-dlp"])

    def test_yt_dlp_json_reports_missing_dependency(self) -> None:
        def fake_run(*_args, **_kwargs):
            raise FileNotFoundError("yt-dlp")

        with (
            patch("meal_planner.youtube_ingestion.shutil.which", return_value=None),
            patch("meal_planner.youtube_ingestion.subprocess.run", fake_run),
        ):
            with self.assertRaisesRegex(RuntimeError, "yt-dlp is required"):
                yt_dlp_json("https://youtube.com/@channel/videos")

    def test_yt_dlp_video_json_fetches_one_video(self) -> None:
        def fake_run(command, check, capture_output, text):
            self.assertIn("--dump-json", command)
            self.assertIn("--skip-download", command)
            return SimpleNamespace(stdout='{"id": "VIDEO000003", "description": "desc"}')

        with (
            patch("meal_planner.youtube_ingestion.shutil.which", return_value="/opt/homebrew/bin/yt-dlp"),
            patch("meal_planner.youtube_ingestion.subprocess.run", fake_run),
        ):
            payload = yt_dlp_video_json("VIDEO000003")

        self.assertEqual(payload["id"], "VIDEO000003")

    def test_yt_dlp_video_json_surfaces_downloader_errors(self) -> None:
        def fake_run(command, check, capture_output, text):
            raise subprocess.CalledProcessError(1, command, stderr="metadata blocked")

        with (
            patch("meal_planner.youtube_ingestion.shutil.which", return_value="/opt/homebrew/bin/yt-dlp"),
            patch("meal_planner.youtube_ingestion.subprocess.run", fake_run),
        ):
            with self.assertRaisesRegex(RuntimeError, "metadata blocked"):
                yt_dlp_video_json("VIDEO000003")

    def test_download_audio_finds_downloaded_file(self) -> None:
        audio_dir = Path(self.tmp.name) / "audio-cache"

        def fake_run(command, check, capture_output, text):
            self.assertIn("ba/bestaudio/best", command)
            self.assertTrue(check)
            self.assertTrue(capture_output)
            self.assertTrue(text)
            (audio_dir / "VIDEO000003.m4a").write_bytes(b"downloaded audio")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("meal_planner.youtube_ingestion.subprocess.run", fake_run):
            path, digest = download_audio("VIDEO000003", audio_dir=audio_dir)

        self.assertEqual(path.name, "VIDEO000003.m4a")
        self.assertEqual(digest, file_hash(path))

    def test_download_audio_surfaces_downloader_errors(self) -> None:
        def fake_run(command, check, capture_output, text):
            raise subprocess.CalledProcessError(1, command, stderr="download blocked")

        with patch("meal_planner.youtube_ingestion.subprocess.run", fake_run):
            with self.assertRaisesRegex(RuntimeError, "download blocked"):
                download_audio("VIDEO000003", audio_dir=Path(self.tmp.name) / "audio-cache")

    def test_clean_vtt_text_removes_timestamps_and_duplicates(self) -> None:
        raw = (
            "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n<c>Hello</c>\n<c>Hello</c>\n00:00:01.000 --> 00:00:02.000\nworld"
        )

        self.assertEqual(clean_vtt_text(raw), "Hello world")

    def test_fetch_transcript_with_ytdlp_reads_caption_file(self) -> None:
        subtitle_dir = Path(self.tmp.name) / "subs"

        def fake_run(command, check, capture_output, text):
            self.assertIn("--write-auto-subs", command)
            subtitle_dir.mkdir(parents=True, exist_ok=True)
            (subtitle_dir / "VIDEO000003.es-orig.vtt").write_text(
                "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHola receta",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("meal_planner.youtube_ingestion.subprocess.run", fake_run):
            result = fetch_transcript_with_ytdlp("VIDEO000003", subtitle_dir=subtitle_dir)

        self.assertEqual(result.language, "es-orig")
        self.assertEqual(result.source_type, "auto_caption")
        self.assertIn("Hola receta", result.text)

    def test_extract_recipe_page_urls_dedupes_description_links(self) -> None:
        urls = extract_recipe_page_urls(
            "Recipe https://diegodoal.com/recetas/shuizhu-niurou and https://www.diegodoal.com/recetas/shuizhu-niurou."
        )

        self.assertEqual(
            urls,
            [
                "https://diegodoal.com/recetas/shuizhu-niurou",
                "https://www.diegodoal.com/recetas/shuizhu-niurou",
            ],
        )

    def test_visible_text_from_html_ignores_scripts_and_styles(self) -> None:
        text = visible_text_from_html(
            "<html><style>.x{}</style><p>INGREDIENTES</p><script>x()</script><p>250 g rice</p>"
        )

        self.assertIn("INGREDIENTES", text)
        self.assertIn("250 g rice", text)
        self.assertNotIn("x()", text)

    def test_fetch_recipe_page_text_decodes_html_response(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b"<p>METODO</p><p>Batch cook rice.</p>"

        with patch("meal_planner.youtube_ingestion.urllib.request.urlopen", return_value=FakeResponse()):
            text = fetch_recipe_page_text("https://diegodoal.com/recetas/demo")

        self.assertIn("Batch cook rice", text)

    def test_default_audio_transcriber_requires_faster_whisper(self) -> None:
        with (
            patch("meal_planner.youtube_ingestion.WhisperModel", side_effect=ImportError("missing"), create=True),
            patch.dict("sys.modules", {"faster_whisper": None}),
        ):
            with self.assertRaisesRegex(RuntimeError, "faster-whisper is required"):
                transcribe_audio_faster_whisper("VIDEO000003")

    def test_audio_transcriber_surfaces_download_failure(self) -> None:
        fake_module = SimpleNamespace(WhisperModel=object)
        with (
            patch.dict("sys.modules", {"faster_whisper": fake_module}),
            patch("meal_planner.youtube_ingestion.download_audio", side_effect=RuntimeError("download failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                transcribe_audio_faster_whisper("VIDEO000003")

    def test_metadata_prefilter_identifies_lunch_dinner_candidates(self) -> None:
        self.assertEqual(looks_like_meal_video("Chicken rice for lunch")[0], True)
        self.assertEqual(looks_like_meal_video("10 kitchen utensils under 10 euros")[0], False)
        self.assertEqual(looks_like_meal_video("Anything", "Tuppers!")[0], True)

    def test_prefilter_audio_candidates_skips_non_recipe_videos(self) -> None:
        self.conn.execute(
            "INSERT INTO youtube_channels (url, handle) VALUES ('https://www.youtube.com/@diegodoal', '@diegodoal')"
        )
        self.conn.executemany(
            """
            INSERT INTO youtube_videos (id, channel_url, title, url, status)
            VALUES (?, 'https://www.youtube.com/@diegodoal', ?, ?, 'needs_audio_transcription')
            """,
            [
                ("VIDEO000003", "Chicken rice for lunch", "https://youtube.com/watch?v=VIDEO000003"),
                ("VIDEO000004", "10 kitchen utensils", "https://youtube.com/watch?v=VIDEO000004"),
            ],
        )
        self.conn.commit()

        counts = prefilter_audio_candidates(self.conn)
        statuses = {
            row["id"]: row["status"]
            for row in self.conn.execute("SELECT id, status FROM youtube_videos WHERE id LIKE 'VIDEO00000%'")
        }

        self.assertEqual(counts, {"kept": 1, "skipped": 1})
        self.assertEqual(statuses["VIDEO000003"], "needs_audio_transcription")
        self.assertEqual(statuses["VIDEO000004"], "skipped_not_recipe")

    def test_discover_channel_is_idempotent_and_dedupes_videos(self) -> None:
        def fake_loader(url: str) -> dict[str, object]:
            if url.endswith("/playlists"):
                return {"entries": [{"id": "PL1", "title": "Recetas", "url": "https://youtube.com/playlist?list=PL1"}]}
            if "playlist" in url:
                return {
                    "entries": [
                        {"id": "VIDEO000001", "title": "Receta pollo", "url": "VIDEO000001", "duration": 600},
                        {"id": "VIDEO000002", "title": "Receta pasta", "url": "VIDEO000002", "duration": 700},
                    ]
                }
            return {
                "entries": [
                    {"id": "VIDEO000001", "title": "Receta pollo updated", "url": "VIDEO000001", "duration": 600},
                    {"id": "VIDEO000003", "title": "Receta arroz", "url": "VIDEO000003", "duration": 800},
                ]
            }

        first = discover_channel(self.conn, "https://www.youtube.com/@diegodoal", metadata_loader=fake_loader)
        second = discover_channel(self.conn, "https://www.youtube.com/@diegodoal", metadata_loader=fake_loader)

        videos = self.conn.execute("SELECT count(*) AS c FROM youtube_videos").fetchone()["c"]
        playlists = self.conn.execute("SELECT count(*) AS c FROM youtube_playlists").fetchone()["c"]
        self.assertEqual(first["videos"], 3)
        self.assertEqual(second["videos"], 3)
        self.assertEqual(videos, 3)
        self.assertEqual(playlists, 1)

    def test_discover_channel_falls_back_when_playlists_tab_is_missing(self) -> None:
        def fake_loader(url: str) -> dict[str, object]:
            if url.endswith("/playlists"):
                raise RuntimeError("channel has no playlists tab")
            return {"entries": [{"id": "VIDEO000011", "title": "Recipe video", "url": "VIDEO000011", "duration": 600}]}

        counts = discover_channel(self.conn, "https://www.youtube.com/@recipes", metadata_loader=fake_loader)
        videos = self.conn.execute(
            "SELECT count(*) AS c FROM youtube_videos WHERE channel_url = ?", ("https://www.youtube.com/@recipes",)
        ).fetchone()["c"]

        self.assertEqual(counts, {"playlists": 0, "videos": 1})
        self.assertEqual(videos, 1)

    def test_transcript_fetch_marks_missing_for_audio_fallback(self) -> None:
        self.conn.execute(
            """
            INSERT INTO youtube_channels (url, handle) VALUES ('https://www.youtube.com/@diegodoal', '@diegodoal')
            """
        )
        self.conn.execute(
            """
            INSERT INTO youtube_videos (id, channel_url, title, url)
            VALUES ('VIDEO000001', 'https://www.youtube.com/@diegodoal', 'Receta pollo', 'https://youtube.com/watch?v=VIDEO000001'),
                   ('VIDEO000002', 'https://www.youtube.com/@diegodoal', 'No captions', 'https://youtube.com/watch?v=VIDEO000002')
            """
        )
        self.conn.commit()

        def fake_fetcher(video_id: str) -> TranscriptResult:
            if video_id == "VIDEO000002":
                raise LookupError("missing captions")
            return TranscriptResult(language="es", source_type="manual_caption", text="receta de pollo con arroz")

        counts = fetch_missing_transcripts(self.conn, fetcher=fake_fetcher, workers=2)
        needs_audio = self.conn.execute("SELECT status FROM youtube_videos WHERE id = 'VIDEO000002'").fetchone()

        self.assertEqual(counts, {"fetched": 1, "unavailable": 1})
        self.assertEqual(needs_audio["status"], "needs_audio_transcription")

    def test_fetch_ytdlp_auto_captions_updates_missing_videos(self) -> None:
        self.conn.execute(
            "INSERT INTO youtube_channels (url, handle) VALUES ('https://www.youtube.com/@diegodoal', '@diegodoal')"
        )
        self.conn.execute(
            """
            INSERT INTO youtube_videos (id, channel_url, title, url, status)
            VALUES ('VIDEO000008', 'https://www.youtube.com/@diegodoal', 'Auto captions',
                    'https://youtube.com/watch?v=VIDEO000008', 'needs_audio_transcription')
            """
        )
        self.conn.commit()

        counts = fetch_ytdlp_auto_captions(
            self.conn,
            fetcher=lambda _video_id: TranscriptResult("es-orig", "auto_caption", "receta de pollo"),
        )
        row = self.conn.execute(
            "SELECT status FROM youtube_videos WHERE id = 'VIDEO000008'",
        ).fetchone()

        self.assertEqual(counts, {"fetched": 1, "unavailable": 0})
        self.assertEqual(row["status"], "transcript_ready")

    def test_audio_transcription_fills_missing_transcript(self) -> None:
        self.conn.execute(
            "INSERT INTO youtube_channels (url, handle) VALUES ('https://www.youtube.com/@diegodoal', '@diegodoal')"
        )
        self.conn.execute(
            """
            INSERT INTO youtube_videos (id, channel_url, title, url, status)
            VALUES ('VIDEO000002', 'https://www.youtube.com/@diegodoal', 'No captions', 'https://youtube.com/watch?v=VIDEO000002', 'needs_audio_transcription')
            """
        )
        self.conn.commit()

        def fake_transcriber(video_id: str) -> AudioTranscriptionResult:
            return AudioTranscriptionResult(
                language="es",
                text=f"receta de noodles desde audio {video_id}",
                backend="fake-whisper",
                model="tiny",
                audio_hash="abc",
            )

        counts = transcribe_missing_audio(self.conn, transcriber=fake_transcriber)
        transcript = self.conn.execute(
            "SELECT source_type, text FROM youtube_transcripts WHERE video_id = 'VIDEO000002'"
        ).fetchone()

        self.assertEqual(counts, {"transcribed": 1, "failed": 0})
        self.assertEqual(transcript["source_type"], "audio_transcription")
        self.assertIn("noodles", transcript["text"])

    def test_fetch_linked_recipe_pages_saves_page_text(self) -> None:
        self.conn.execute(
            "INSERT INTO youtube_channels (url, handle) VALUES ('https://www.youtube.com/@diegodoal', '@diegodoal')"
        )
        self.conn.execute(
            """
            INSERT INTO youtube_videos (id, channel_url, title, url, status)
            VALUES ('VIDEO000005', 'https://www.youtube.com/@diegodoal', 'Recipe page',
                    'https://youtube.com/watch?v=VIDEO000005', 'needs_audio_transcription')
            """
        )
        self.conn.commit()

        def fake_metadata(_video_id: str) -> dict[str, object]:
            return {
                "title": "Recipe page",
                "description": "Full recipe: https://diegodoal.com/recetas/shuizhu-niurou",
            }

        def fake_page(_url: str) -> str:
            return "INGREDIENTES\n250 g ternera\nMÉTODO\nBatch cook: simmer the beef."

        counts = fetch_linked_recipe_pages(self.conn, metadata_loader=fake_metadata, page_fetcher=fake_page)
        transcript = self.conn.execute(
            "SELECT source_type, text FROM youtube_transcripts WHERE video_id = 'VIDEO000005'"
        ).fetchone()

        self.assertEqual(counts, {"pages": 1, "no_link": 0, "failed": 0})
        self.assertEqual(transcript["source_type"], "linked_recipe_page")
        self.assertIn("250 g ternera", transcript["text"])

    def test_fetch_linked_recipe_pages_counts_missing_links(self) -> None:
        self.conn.execute(
            "INSERT INTO youtube_channels (url, handle) VALUES ('https://www.youtube.com/@diegodoal', '@diegodoal')"
        )
        self.conn.execute(
            """
            INSERT INTO youtube_videos (id, channel_url, title, url, status)
            VALUES ('VIDEO000007', 'https://www.youtube.com/@diegodoal', 'No link',
                    'https://youtube.com/watch?v=VIDEO000007', 'needs_audio_transcription')
            """
        )
        self.conn.commit()

        counts = fetch_linked_recipe_pages(
            self.conn,
            metadata_loader=lambda _video_id: {"description": "no recipe url"},
            page_fetcher=lambda _url: "",
        )

        self.assertEqual(counts, {"pages": 0, "no_link": 1, "failed": 0})

    def test_fetch_video_descriptions_caches_recipe_payloads(self) -> None:
        self.conn.execute(
            "INSERT INTO youtube_channels (url, handle) VALUES ('https://www.youtube.com/@felu', '@felu')"
        )
        self.conn.execute(
            """
            INSERT INTO youtube_videos (id, channel_url, title, url, status)
            VALUES ('VIDEO000010', 'https://www.youtube.com/@felu', 'Chicken bowl',
                    'https://youtube.com/watch?v=VIDEO000010', 'needs_audio_transcription')
            """
        )
        self.conn.commit()

        def fake_loader(_video_id: str) -> dict[str, object]:
            return {
                "title": "Chicken bowl",
                "description": "Macros: 500 calories. Ingredients: 200g chicken, 60g rice.",
            }

        counts = fetch_video_descriptions(
            self.conn, metadata_loader=fake_loader, workers=1, channel_url="https://www.youtube.com/@felu"
        )
        row = self.conn.execute(
            "SELECT source_type, text FROM youtube_transcripts WHERE video_id = 'VIDEO000010'"
        ).fetchone()

        self.assertEqual(counts, {"fetched": 1, "skipped": 0, "failed": 0})
        self.assertEqual(row["source_type"], "video_description")
        self.assertIn("200g chicken", row["text"])

    def test_save_recipe_page_transcript_marks_ready(self) -> None:
        self.conn.execute(
            "INSERT INTO youtube_channels (url, handle) VALUES ('https://www.youtube.com/@diegodoal', '@diegodoal')"
        )
        self.conn.execute(
            """
            INSERT INTO youtube_videos (id, channel_url, title, url, status)
            VALUES ('VIDEO000006', 'https://www.youtube.com/@diegodoal', 'Recipe page',
                    'https://youtube.com/watch?v=VIDEO000006', 'needs_audio_transcription')
            """
        )
        save_recipe_page_transcript(
            self.conn,
            "VIDEO000006",
            "https://diegodoal.com/recetas/demo",
            "Demo",
            "INGREDIENTES\nMÉTODO",
        )
        row = self.conn.execute(
            "SELECT status FROM youtube_videos WHERE id = 'VIDEO000006'",
        ).fetchone()

        self.assertEqual(row["status"], "transcript_ready")

    def test_extract_candidate_enforces_batch_policy(self) -> None:
        self.conn.execute(
            "INSERT INTO youtube_channels (url, handle) VALUES ('https://www.youtube.com/@diegodoal', '@diegodoal')"
        )
        self.conn.execute(
            """
            INSERT INTO youtube_videos (id, channel_url, title, url, status)
            VALUES ('VIDEO000001', 'https://www.youtube.com/@diegodoal', 'Receta burrito', 'https://youtube.com/watch?v=VIDEO000001', 'transcript_ready')
            """
        )
        self.conn.execute(
            """
            INSERT INTO youtube_transcripts (video_id, language, source_type, text, content_hash)
            VALUES ('VIDEO000001', 'es', 'manual_caption', 'receta pollo burrito', 'hash')
            """
        )
        self.conn.commit()

        def fake_ask(_prompt: str, _context: str) -> str:
            return json.dumps(
                [
                    {
                        "name": "YouTube chicken burrito",
                        "meal_type": "lunch_dinner",
                        "servings": 4,
                        "ingredients": [
                            {"name": "chicken", "quantity": 500, "unit": "g", "grams": 500},
                            {"name": "rice", "quantity": 300, "unit": "g", "grams": 300},
                        ],
                        "procedure": "Batch cook: cook the filling. Individual cook: warm one wrap per meal.",
                        "decision": "needs_review",
                        "decision_reason": "Extracted from transcript.",
                    }
                ]
            )

        counts = extract_candidates(self.conn, ask=fake_ask, workers=1)
        row = candidate_rows(self.conn)[0]
        duplicates = update_candidate_duplicates(self.conn, row["id"])

        self.assertEqual(counts["candidates"], 1)
        self.assertEqual(row["recipe_name"], "YouTube chicken burrito")
        self.assertIsInstance(duplicates, list)

    def test_candidate_validation_rejects_missing_water_ingredient(self) -> None:
        candidate = RecipeCandidate(
            name="Incomplete dough",
            meal_type="lunch_dinner",
            servings=4,
            ingredients=[CandidateIngredient(name="flour", quantity=500, unit="g", grams=500)],
            procedure="Batch cook: mix flour with water and rest 30 minutes. Individual cook: bake at 220C.",
        )

        with self.assertRaisesRegex(ValueError, "mentions water"):
            validate_candidate(candidate)

    def test_candidate_validation_rejects_vague_oven_temperature(self) -> None:
        candidate = RecipeCandidate(
            name="Vague bake",
            meal_type="lunch_dinner",
            servings=4,
            ingredients=[CandidateIngredient(name="chicken", quantity=500, unit="g", grams=500)],
            procedure="Batch cook: bake the chicken in a hot oven for 20 minutes. Individual cook: reheat.",
        )

        with self.assertRaisesRegex(ValueError, "missing a temperature"):
            validate_candidate(candidate)

    def test_approve_candidate_links_source(self) -> None:
        self.test_extract_candidate_enforces_batch_policy()
        candidate_id = candidate_rows(self.conn)[0]["id"]
        recipe_id = approve_candidate(self.conn, candidate_id)
        source = self.conn.execute("SELECT * FROM recipe_sources WHERE recipe_id = ?", (recipe_id,)).fetchone()
        recipe = self.conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()

        self.assertEqual(recipe["source_type"], "youtube")
        self.assertEqual(recipe["servings"], 4)
        self.assertEqual(source["youtube_video_id"], "VIDEO000001")

    def test_approve_candidate_prefers_canonical_ingredient_alias(self) -> None:
        self.conn.execute(
            "INSERT INTO youtube_channels (url, handle) VALUES ('https://www.youtube.com/@felu', '@felu')"
        )
        self.conn.execute(
            """
            INSERT INTO youtube_videos (id, channel_url, title, url)
            VALUES ('VIDEO000009', 'https://www.youtube.com/@felu', 'Rice bowl', 'https://youtube.com/watch?v=VIDEO000009')
            """
        )
        candidate_id = save_candidate(
            self.conn,
            "VIDEO000009",
            RecipeCandidate(
                name="Rice bowl",
                meal_type="lunch_dinner",
                servings=4,
                ingredients=[
                    CandidateIngredient(name="water", quantity=600, unit="ml", grams=600, ingredient_id="water"),
                    CandidateIngredient(name="jasmine rice", quantity=300, unit="g", grams=300),
                ],
                procedure="Batch cook: simmer rice with water for 12 minutes at low heat. Individual cook: reheat.",
            ),
        )

        recipe_id = approve_candidate(self.conn, candidate_id)
        ingredient_ids = {
            row["ingredient_id"]
            for row in self.conn.execute(
                "SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,)
            )
        }

        self.assertIn("agua", ingredient_ids)
        self.assertIn("arroz-basmati", ingredient_ids)
        self.assertNotIn("water", ingredient_ids)

    def test_merge_candidate_marks_existing_recipe(self) -> None:
        self.test_extract_candidate_enforces_batch_policy()
        candidate_id = candidate_rows(self.conn)[0]["id"]
        merge_candidate(self.conn, candidate_id, "burrito", "similar filling")
        row = self.conn.execute(
            "SELECT status, duplicate_recipe_ids FROM youtube_recipe_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()

        self.assertEqual(row["status"], "merged")
        self.assertIn("burrito", row["duplicate_recipe_ids"])


if __name__ == "__main__":
    unittest.main()
