from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .curation import similar_recipes
from .db import connect, ensure_database, find_recipe, init_schema, reset_database
from .enrichment import enrich_recipes
from .importers import import_prices, import_recipes
from .paths import COPILOT_CONFIG_PATH, DEFAULT_DB_PATH
from .recommender import record_decision
from .seed_data import seed_database
from .tui import (
    print_categories,
    print_ingredients,
    print_recipe_detail,
    print_recipes,
    print_recommendations,
    print_shopping_list,
    run_interactive,
)
from .youtube_ingestion import (
    CHANNEL_URL,
    approve_all_candidates,
    approve_candidate,
    candidate_rows,
    discard_candidate,
    discover_channel,
    extract_candidates,
    fetch_linked_recipe_pages,
    fetch_missing_transcripts,
    fetch_video_descriptions,
    fetch_ytdlp_auto_captions,
    load_candidate,
    merge_candidate,
    prefilter_audio_candidates,
    transcribe_missing_audio,
    update_candidate_duplicates,
    youtube_status,
)


def open_db():
    conn = connect()
    ensure_database(conn)
    return conn


def cmd_init(args: argparse.Namespace) -> None:
    conn = connect()
    if args.reset:
        reset_database(conn)
    else:
        init_schema(conn)
    if not args.no_seed:
        seed_database(conn)
    print(f"database ready: {DEFAULT_DB_PATH}")


def cmd_doctor(_args: argparse.Namespace) -> None:
    conn = open_db()
    ingredients = conn.execute("SELECT count(*) AS c FROM ingredients").fetchone()["c"]
    recipes = conn.execute("SELECT count(*) AS c FROM recipes").fetchone()["c"]
    approved = conn.execute("SELECT count(*) AS c FROM recipes WHERE status = 'approved'").fetchone()["c"]
    real_prices = conn.execute("SELECT count(*) AS c FROM prices WHERE source = 'real_purchase'").fetchone()["c"]
    print(f"meal-planner {__version__}")
    print(f"database: {DEFAULT_DB_PATH}")
    print(f"ingredients: {ingredients}")
    print(f"recipes: {recipes} ({approved} approved)")
    print(f"real Lidl Prague 2026 price rows: {real_prices}")
    print(f"copilot config: {'found' if COPILOT_CONFIG_PATH.exists() else 'missing'} ({COPILOT_CONFIG_PATH})")
    yt = youtube_status(conn)
    print(
        "youtube: "
        f"{yt['videos']} videos, {yt['transcripts']} transcripts, "
        f"{yt['candidates']} candidates ({yt['pending_candidates']} pending), {yt['audio_failed']} audio failures"
    )


def cmd_recommend(args: argparse.Namespace) -> None:
    conn = open_db()
    print_recommendations(conn, limit=args.limit)


def cmd_accept(args: argparse.Namespace) -> None:
    conn = open_db()
    recipe = find_recipe(conn, args.recipe)
    record_decision(conn, recipe["id"], "accepted", args.notes or "")
    print(f"accepted: {recipe['name']}")


def cmd_reject(args: argparse.Namespace) -> None:
    conn = open_db()
    recipe = find_recipe(conn, args.recipe)
    record_decision(conn, recipe["id"], "rejected", args.reason or "")
    print(f"rejected: {recipe['name']}")


def cmd_shopping_list(args: argparse.Namespace) -> None:
    conn = open_db()
    recipe_ids = [find_recipe(conn, value)["id"] for value in args.recipes]
    print_shopping_list(conn, recipe_ids)


def cmd_recipes(args: argparse.Namespace) -> None:
    conn = open_db()
    print_recipes(conn, sort=args.sort)


def cmd_recipe_categories(_args: argparse.Namespace) -> None:
    print_categories()


def cmd_recipe_show(args: argparse.Namespace) -> None:
    conn = open_db()
    print_recipe_detail(conn, args.recipe)


def cmd_recipe_delete(args: argparse.Namespace) -> None:
    conn = open_db()
    recipe = find_recipe(conn, args.recipe)
    conn.execute("UPDATE recipes SET status = 'deleted' WHERE id = ?", (recipe["id"],))
    conn.commit()
    print(f"deleted recipe::{recipe['id']} {recipe['name']}")


def cmd_history(args: argparse.Namespace) -> None:
    conn = open_db()
    rows = conn.execute(
        """
        SELECT mh.created_at, mh.action, mh.notes, r.name, r.id
        FROM meal_history mh
        JOIN recipes r ON r.id = mh.recipe_id
        ORDER BY mh.created_at DESC, mh.id DESC
        LIMIT ?
        """,
        (args.limit,),
    ).fetchall()
    for row in rows:
        print(f"{row['created_at'][:16]} {row['action']:<8} {row['name']} notes::{row['notes']}")


def cmd_ingredients(args: argparse.Namespace) -> None:
    conn = open_db()
    print_ingredients(conn)


def cmd_import_prices(args: argparse.Namespace) -> None:
    conn = open_db()
    count = import_prices(conn, Path(args.file))
    print(f"imported price rows: {count}")


def cmd_import_recipes(args: argparse.Namespace) -> None:
    conn = open_db()
    count = import_recipes(conn, Path(args.file))
    print(f"imported recipes: {count}")


def cmd_import_seed(args: argparse.Namespace) -> None:
    conn = connect()
    if args.reset:
        reset_database(conn)
    else:
        init_schema(conn)
    seed_database(conn)
    print("seed data imported")


def cmd_similar(args: argparse.Namespace) -> None:
    conn = open_db()
    matches = similar_recipes(conn, args.name, threshold=args.threshold)
    if not matches:
        print("no similar recipes found")
        return
    for match in matches:
        print(f"{match['recipe_id']}: {match['name']} similarity::{match['similarity']}")


def cmd_llm_enrich(args: argparse.Namespace) -> None:
    conn = open_db()
    recipe_ids = [find_recipe(conn, value)["id"] for value in args.recipes] if args.recipes else None
    results = enrich_recipes(conn, recipe_ids=recipe_ids, only_missing=args.only_missing)
    for result in results:
        missing = ", ".join(result["missing_ingredients"]) if result["missing_ingredients"] else "none"
        print(
            f"{result['recipe_id']}: decision::{result['decision_status']} "
            f"protein::{result['protein_status']} missing::{missing}"
        )


def cmd_dashboard(_args: argparse.Namespace) -> None:
    conn = open_db()
    run_interactive(conn)


def cmd_youtube_discover(args: argparse.Namespace) -> None:
    conn = open_db()
    counts = discover_channel(conn, args.url, limit=args.limit, include_shorts=args.include_shorts)
    print(f"discovered playlists::{counts['playlists']} videos::{counts['videos']}")


def cmd_youtube_fetch_transcripts(args: argparse.Namespace) -> None:
    conn = open_db()
    counts = fetch_missing_transcripts(conn, workers=args.workers, limit=args.limit, channel_url=args.channel_url)
    print(f"transcripts fetched::{counts['fetched']} unavailable::{counts['unavailable']}")


def cmd_youtube_fetch_auto_captions(args: argparse.Namespace) -> None:
    conn = open_db()
    counts = fetch_ytdlp_auto_captions(conn, workers=args.workers, limit=args.limit, channel_url=args.channel_url)
    print(f"auto captions fetched::{counts['fetched']} unavailable::{counts['unavailable']}")


def cmd_youtube_fetch_descriptions(args: argparse.Namespace) -> None:
    conn = open_db()
    counts = fetch_video_descriptions(conn, workers=args.workers, limit=args.limit, channel_url=args.channel_url)
    print(f"descriptions fetched::{counts['fetched']} skipped::{counts['skipped']} failed::{counts['failed']}")


def cmd_youtube_transcribe_missing(args: argparse.Namespace) -> None:
    conn = open_db()
    counts = transcribe_missing_audio(conn, workers=args.workers, limit=args.limit)
    print(f"audio transcribed::{counts['transcribed']} failed::{counts['failed']}")


def cmd_youtube_prefilter_audio(_args: argparse.Namespace) -> None:
    conn = open_db()
    counts = prefilter_audio_candidates(conn)
    print(f"audio candidates kept::{counts['kept']} skipped_not_recipe::{counts['skipped']}")


def cmd_youtube_fetch_recipe_pages(args: argparse.Namespace) -> None:
    conn = open_db()
    counts = fetch_linked_recipe_pages(conn, workers=args.workers, limit=args.limit)
    print(f"recipe pages::{counts['pages']} no_link::{counts['no_link']} failed::{counts['failed']}")


def cmd_youtube_extract(args: argparse.Namespace) -> None:
    conn = open_db()
    counts = extract_candidates(
        conn, workers=args.workers, limit=args.limit, model=args.model, channel_url=args.channel_url
    )
    print(
        f"videos::{counts['videos']} candidates::{counts['candidates']} "
        f"skipped::{counts['skipped']} failed::{counts['failed']}"
    )


def cmd_youtube_status(_args: argparse.Namespace) -> None:
    conn = open_db()
    counts = youtube_status(conn)
    for key in sorted(counts):
        print(f"{key}::{counts[key]}")


def cmd_youtube_candidates_list(args: argparse.Namespace) -> None:
    conn = open_db()
    rows = candidate_rows(conn, status=args.status)
    for row in rows:
        print(f"{row['id']}: {row['status']} {row['recipe_name']} video::{row['video_id']}")


def cmd_youtube_candidates_show(args: argparse.Namespace) -> None:
    conn = open_db()
    row = conn.execute("SELECT * FROM youtube_recipe_candidates WHERE id = ?", (args.candidate_id,)).fetchone()
    if row is None:
        raise LookupError(args.candidate_id)
    candidate = load_candidate(row)
    duplicates = update_candidate_duplicates(conn, args.candidate_id)
    print(f"{row['id']}: {candidate.name} status::{row['status']} video::{row['video_id']}")
    print(f"servings::{candidate.servings} decision::{candidate.decision} confidence::{candidate.confidence}")
    print(f"duplicates::{', '.join(duplicates) if duplicates else 'none'}")
    print("ingredients:")
    for ingredient in candidate.ingredients:
        grams = "" if ingredient.grams is None else f" grams::{ingredient.grams:g}"
        print(f"  {ingredient.name} {ingredient.quantity:g}{ingredient.unit}{grams}")
    print("procedure:")
    print(candidate.procedure)


def cmd_youtube_candidates_approve(args: argparse.Namespace) -> None:
    conn = open_db()
    recipe_id = approve_candidate(conn, args.candidate_id)
    print(f"approved candidate::{args.candidate_id} recipe::{recipe_id}")


def cmd_youtube_candidates_approve_all(_args: argparse.Namespace) -> None:
    conn = open_db()
    counts = approve_all_candidates(conn)
    print(f"approved::{counts['approved']} failed::{counts['failed']}")


def cmd_youtube_candidates_discard(args: argparse.Namespace) -> None:
    conn = open_db()
    discard_candidate(conn, args.candidate_id, args.reason or "")
    print(f"discarded candidate::{args.candidate_id}")


def cmd_youtube_candidates_merge(args: argparse.Namespace) -> None:
    conn = open_db()
    recipe = find_recipe(conn, args.recipe)
    merge_candidate(conn, args.candidate_id, recipe["id"], args.reason or "")
    print(f"merged candidate::{args.candidate_id} into::{recipe['id']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meal-planner", description="Local smart meal planner.")
    parser.set_defaults(func=cmd_dashboard)
    sub = parser.add_subparsers(dest="command")

    init = sub.add_parser("init", help="Initialize or reset the database.")
    init.add_argument("--reset", action="store_true", help="Drop and recreate all local meal-planner tables.")
    init.add_argument("--no-seed", action="store_true", help="Create schema without seed data.")
    init.set_defaults(func=cmd_init)

    doctor = sub.add_parser("doctor", help="Check local app state.")
    doctor.set_defaults(func=cmd_doctor)

    recommend = sub.add_parser("recommend", help="Show ranked recommendations.")
    recommend.add_argument("--limit", type=int, default=5)
    recommend.set_defaults(func=cmd_recommend)

    accept = sub.add_parser("accept", help="Accept/cook a recommended recipe.")
    accept.add_argument("recipe")
    accept.add_argument("--notes", default="")
    accept.set_defaults(func=cmd_accept)

    reject = sub.add_parser("reject", help="Reject a recommended recipe.")
    reject.add_argument("recipe")
    reject.add_argument("--reason", default="")
    reject.set_defaults(func=cmd_reject)

    shopping = sub.add_parser("shopping-list", help="Generate a shopping list for recipes.")
    shopping.add_argument("recipes", nargs="+")
    shopping.set_defaults(func=cmd_shopping_list)

    import_cmd = sub.add_parser("import", help="Import seed, price, or recipe JSON data.")
    import_sub = import_cmd.add_subparsers(dest="import_command")
    import_seed = import_sub.add_parser("seed", help="Import built-in Lidl/recipe seed data.")
    import_seed.add_argument("--reset", action="store_true")
    import_seed.set_defaults(func=cmd_import_seed)
    import_prices_cmd = import_sub.add_parser("prices", help="Import price JSON rows.")
    import_prices_cmd.add_argument("file")
    import_prices_cmd.set_defaults(func=cmd_import_prices)
    import_recipes_cmd = import_sub.add_parser("recipes", help="Import recipe JSON rows.")
    import_recipes_cmd.add_argument("file")
    import_recipes_cmd.set_defaults(func=cmd_import_recipes)

    similar = sub.add_parser("similar", help="Find similar existing recipes by name.")
    similar.add_argument("name")
    similar.add_argument("--threshold", type=float, default=0.72)
    similar.set_defaults(func=cmd_similar)

    llm = sub.add_parser("llm", help="LLM-assisted review commands.")
    llm_sub = llm.add_subparsers(dest="llm_command")
    llm_enrich = llm_sub.add_parser("enrich-recipes", help="Run Copilot-backed recipe enrichment.")
    llm_enrich.add_argument("recipes", nargs="*", help="Recipe ids/names. Defaults to all recipes.")
    llm_enrich.add_argument(
        "--only-missing", action="store_true", help="Only review recipes without a stored LLM review."
    )
    llm_enrich.set_defaults(func=cmd_llm_enrich)

    recipes = sub.add_parser("recipes", help="Recipe commands.")
    recipes_sub = recipes.add_subparsers(dest="recipes_command")
    recipes_list = recipes_sub.add_parser("list", help="List recipes.")
    recipes_list.add_argument(
        "--sort",
        choices=["name", "category", "cheap", "calories", "high-calories", "protein", "cooked", "recent"],
        default="name",
    )
    recipes_list.set_defaults(func=cmd_recipes)
    recipes_categories = recipes_sub.add_parser("categories", help="List meal categories.")
    recipes_categories.set_defaults(func=cmd_recipe_categories)
    recipes_show = recipes_sub.add_parser("show", help="Show one recipe with ingredients and steps.")
    recipes_show.add_argument("recipe")
    recipes_show.set_defaults(func=cmd_recipe_show)
    recipes_delete = recipes_sub.add_parser("delete", help="Hide a recipe from lists and recommendations.")
    recipes_delete.add_argument("recipe")
    recipes_delete.set_defaults(func=cmd_recipe_delete)

    history = sub.add_parser("history", help="Show cooked/rejected recipe history.")
    history.add_argument("--limit", type=int, default=20)
    history.set_defaults(func=cmd_history)

    ingredients = sub.add_parser("ingredients", help="Ingredient commands.")
    ingredients_sub = ingredients.add_subparsers(dest="ingredients_command")
    ingredients_list = ingredients_sub.add_parser("list", help="List ingredients.")
    ingredients_list.set_defaults(func=cmd_ingredients)

    youtube = sub.add_parser("youtube", help="YouTube ingestion commands.")
    youtube_sub = youtube.add_subparsers(dest="youtube_command")
    youtube_discover = youtube_sub.add_parser("discover-channel", help="Discover channel playlists and videos.")
    youtube_discover.add_argument("url", nargs="?", default=CHANNEL_URL)
    youtube_discover.add_argument("--limit", type=int)
    youtube_discover.add_argument("--include-shorts", action="store_true")
    youtube_discover.set_defaults(func=cmd_youtube_discover)

    youtube_fetch = youtube_sub.add_parser("fetch-transcripts", help="Fetch and cache captions/subtitles.")
    youtube_fetch.add_argument("--workers", type=int, default=4)
    youtube_fetch.add_argument("--limit", type=int)
    youtube_fetch.add_argument("--channel-url")
    youtube_fetch.set_defaults(func=cmd_youtube_fetch_transcripts)

    youtube_auto_captions = youtube_sub.add_parser(
        "fetch-auto-captions", help="Fetch YouTube auto captions with yt-dlp for videos still missing transcripts."
    )
    youtube_auto_captions.add_argument("--workers", type=int, default=4)
    youtube_auto_captions.add_argument("--limit", type=int)
    youtube_auto_captions.add_argument("--channel-url")
    youtube_auto_captions.set_defaults(func=cmd_youtube_fetch_auto_captions)

    youtube_descriptions = youtube_sub.add_parser(
        "fetch-descriptions", help="Cache recipe text from YouTube video descriptions before audio transcription."
    )
    youtube_descriptions.add_argument("--workers", type=int, default=4)
    youtube_descriptions.add_argument("--limit", type=int)
    youtube_descriptions.add_argument("--channel-url")
    youtube_descriptions.set_defaults(func=cmd_youtube_fetch_descriptions)

    youtube_transcribe = youtube_sub.add_parser(
        "transcribe-missing", help="Transcribe audio for videos without captions."
    )
    youtube_transcribe.add_argument("--workers", type=int, default=1)
    youtube_transcribe.add_argument("--limit", type=int)
    youtube_transcribe.set_defaults(func=cmd_youtube_transcribe_missing)

    youtube_prefilter = youtube_sub.add_parser(
        "prefilter-audio", help="Skip videos whose metadata does not look like a lunch/dinner recipe."
    )
    youtube_prefilter.set_defaults(func=cmd_youtube_prefilter_audio)

    youtube_pages = youtube_sub.add_parser(
        "fetch-recipe-pages", help="Fetch diegodoal.com recipe pages linked from video descriptions."
    )
    youtube_pages.add_argument("--workers", type=int, default=4)
    youtube_pages.add_argument("--limit", type=int)
    youtube_pages.set_defaults(func=cmd_youtube_fetch_recipe_pages)

    youtube_extract = youtube_sub.add_parser(
        "extract-recipes", help="Extract recipe candidates from cached transcripts."
    )
    youtube_extract.add_argument("--workers", type=int, default=2)
    youtube_extract.add_argument("--limit", type=int)
    youtube_extract.add_argument("--model", default="gpt-5.4-mini")
    youtube_extract.add_argument("--channel-url")
    youtube_extract.set_defaults(func=cmd_youtube_extract)

    youtube_status_parser = youtube_sub.add_parser("status", help="Show YouTube ingestion status counts.")
    youtube_status_parser.set_defaults(func=cmd_youtube_status)

    candidates = youtube_sub.add_parser("candidates", help="Review extracted recipe candidates.")
    candidates_sub = candidates.add_subparsers(dest="candidate_command")
    candidates_list = candidates_sub.add_parser("list", help="List recipe candidates.")
    candidates_list.add_argument("--status")
    candidates_list.set_defaults(func=cmd_youtube_candidates_list)
    candidates_show = candidates_sub.add_parser("show", help="Show candidate details.")
    candidates_show.add_argument("candidate_id", type=int)
    candidates_show.set_defaults(func=cmd_youtube_candidates_show)
    candidates_approve = candidates_sub.add_parser("approve", help="Approve candidate into recipe catalog.")
    candidates_approve.add_argument("candidate_id", type=int)
    candidates_approve.set_defaults(func=cmd_youtube_candidates_approve)
    candidates_approve_all = candidates_sub.add_parser("approve-all", help="Approve every pending YouTube candidate.")
    candidates_approve_all.set_defaults(func=cmd_youtube_candidates_approve_all)
    candidates_discard = candidates_sub.add_parser("discard", help="Discard candidate.")
    candidates_discard.add_argument("candidate_id", type=int)
    candidates_discard.add_argument("--reason", default="")
    candidates_discard.set_defaults(func=cmd_youtube_candidates_discard)
    candidates_merge = candidates_sub.add_parser("merge", help="Mark candidate as merged into an existing recipe.")
    candidates_merge.add_argument("candidate_id", type=int)
    candidates_merge.add_argument("recipe")
    candidates_merge.add_argument("--reason", default="")
    candidates_merge.set_defaults(func=cmd_youtube_candidates_merge)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
