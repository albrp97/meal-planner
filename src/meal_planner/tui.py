from __future__ import annotations

import os
import re
import select
import sqlite3
import sys
import termios
import textwrap
import tty
from collections.abc import Iterable

from .calculations import latest_price, line_cost, recipe_totals, shopping_list
from .db import find_recipe
from .recipe_chat import ask_recipe_copilot
from .recommender import (
    meal_category_label,
    meal_category_labels,
    primary_meal_category,
    recipe_meal_categories,
    recommendations,
    record_decision,
)
from .youtube_ingestion import load_candidate

RESET = "\033[0m"
BG = "\033[48;2;15;16;32m"
PURPLE = "\033[38;2;196;167;231m"
PURPLE_DIM = "\033[38;2;124;95;184m"
GREEN = "\033[38;2;163;217;119m"
ORANGE = "\033[38;2;246;193;119m"
ROSE = "\033[38;2;217;139;196m"
TEXT = "\033[38;2;242;234;255m"
CLEAR = "\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
RECENT_MEALS_LIMIT = 5
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def category_text(categories: Iterable[str]) -> str:
    labels = [meal_category_label(str(category)) for category in categories]
    return ", ".join(labels) if labels else "uncategorized"


def use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def color(text: object, value: str = TEXT) -> str:
    if not use_color():
        return str(text)
    return f"{value}{text}{RESET}"


def strip_ansi(text: object) -> str:
    return ANSI_RE.sub("", str(text))


def visual_len(text: object) -> int:
    return len(strip_ansi(text))


def fit_line(text: object, width: int) -> str:
    value = str(text)
    if visual_len(value) > width:
        plain = strip_ansi(value)
        return plain[: max(0, width - 1)] + "…"
    return value + " " * (width - visual_len(value))


def padded_color(text: object, width: int, value: str = TEXT) -> str:
    return color(f"{str(text):<{width}}", value)


def money(value: float) -> str:
    return f"{value:.2f} Kč"


def price_marker_from_totals(totals: dict[str, float]) -> str:
    if totals.get("missing_price_lines", 0) > 0:
        return "?"
    if totals.get("estimated_price_lines", 0) > 0:
        return "*"
    return "✓"


def price_marker_from_sources(sources: Iterable[str]) -> str:
    source_set = set(sources)
    if not source_set:
        return "?"
    return "✓" if source_set == {"real_purchase"} else "*"


def price_marker_for_ingredient(conn: sqlite3.Connection, ingredient_id: str) -> str:
    price = latest_price(conn, ingredient_id)
    if price is None:
        return "?"
    return "✓" if price["source"] == "real_purchase" else "*"


def marked_money(value: float, marker: str) -> str:
    return f"{money(value)}{marker}"


def price_legend() -> str:
    return "price: ✓ verified/approved  * estimated  ? missing"


def cost_pair(totals: dict[str, float]) -> str:
    marker = price_marker_from_totals(totals)
    return (
        f"{color('batch::', PURPLE_DIM)}{color(marked_money(totals['cost_czk'], marker), ORANGE)}  "
        f"{color('meal::', PURPLE_DIM)}{color(marked_money(totals['cost_per_serving_czk'], marker), ORANGE)}"
    )


def clip(text: object, width: int) -> str:
    value = str(text)
    if len(value) <= width:
        return value
    return value[: max(0, width - 1)] + "…"


def metric(label: str, value: object, value_color: str = TEXT) -> str:
    return f"{color(label + '::', PURPLE_DIM)}{color(value, value_color)}"


def compact_metric(label: str, value: object) -> str:
    return f"{color(label + ':', PURPLE_DIM)}{color(value, ORANGE)}"


def highlight_numbers(text: object) -> str:
    value = str(text)
    return re.sub(
        r"(?<!\w)(\d+(?:[.,]\d+)?(?:-\d+(?:[.,]\d+)?)?)(?=\w*|\b)", lambda m: color(m.group(1), ORANGE), value
    )


def amount_with_grams(quantity: float, unit: str, grams: float | None) -> str:
    amount = f"{quantity:g}{unit}"
    if grams is None or unit.lower() in {"g", "gram", "grams", "gramos"}:
        return amount
    return f"{amount} ({grams:.0f}g)"


def aggregated_amounts(item: dict[str, object]) -> list[str]:
    amounts: list[str] = []
    if item["grams"]:
        amounts.append(f"{float(item['grams']):.0f}g")
    if item["ml"]:
        ml = float(item["ml"])
        ml_grams = float(item.get("ml_grams", 0.0))
        amounts.append(f"{ml:.0f}ml" + (f" ({ml_grams:.0f}g)" if ml_grams else ""))
    if item["units"]:
        units = float(item["units"])
        unit_grams = float(item.get("unit_grams", 0.0))
        amounts.append(f"{units:.1f}u" + (f" ({unit_grams:.0f}g)" if unit_grams else ""))
    return amounts


def header(title: str) -> None:
    if not use_color():
        print(f"+{'-' * 76}+")
        print(f"| {title:<74}|")
        print(f"+{'-' * 76}+")
        return
    print(f"{BG}{GREEN}+{'-' * 76}+{RESET}")
    print(f"{BG}{GREEN}|{RESET} {PURPLE}{title:<74}{RESET}{BG}{GREEN}|{RESET}")
    print(f"{BG}{GREEN}+{'-' * 76}+{RESET}")


def recommendation_mode(rec: dict[str, object]) -> str:
    return "daily discovery" if rec.get("recommendation_kind") == "discovery" else "ranked"


def print_dashboard(conn: sqlite3.Connection) -> None:
    header("MEAL PLANNER // EVA-01 LOCAL DASH")
    recs = recommendations(conn, limit=6)
    if not recs:
        print(color("No approved recipes available.", ROSE))
        return
    top = recs[0]
    totals = top["totals"]
    protein = f"{totals['protein_per_serving_g']:.1f}g"
    kcal = f"{totals['kcal_per_serving']:.0f}"
    print(color("next recommendation", GREEN))
    print(f"  {color(top['name'], PURPLE)}")
    print(
        "  "
        + f"{metric('cost', cost_pair(totals))}  "
        + f"{metric('protein', protein, ORANGE)}  "
        + f"{metric('kcal', kcal, ORANGE)}"
    )
    print()
    print(color("ranked options", GREEN))
    for idx, rec in enumerate(recs, start=1):
        t = rec["totals"]
        protein = f"{t['protein_per_serving_g']:.1f}g"
        marker = price_marker_from_totals(t)
        kind = "D" if rec.get("recommendation_kind") == "discovery" else "R"
        print(
            f"  {compact_metric(kind, idx)} {color(rec['name'], PURPLE)} "
            f"{metric('batch', marked_money(t['cost_czk'], marker))} "
            f"{metric('meal', marked_money(t['cost_per_serving_czk'], marker))} "
            f"{metric('protein', protein, ORANGE)} "
            f"{metric('cooked', rec.get('cooked_count', 0), ORANGE)}"
        )
    print()
    print(color(f"recent meals last {RECENT_MEALS_LIMIT}", GREEN))
    for line in recent_meal_lines(conn, RECENT_MEALS_LIMIT):
        print(f"  {line}")
    print()
    print(color("commands", GREEN))
    print("  meal-planner accept <recipe>       mark cooked and update history")
    print("  meal-planner shopping-list <recipe> show aggregated ingredients")
    print("  meal-planner recipes list          inspect recipes and drafts")


def print_recommendations(conn: sqlite3.Connection, limit: int = 5) -> None:
    header("RECOMMENDATIONS")
    print(color(price_legend(), PURPLE_DIM))
    for idx, rec in enumerate(recommendations(conn, limit=limit), start=1):
        totals = rec["totals"]
        protein = f"{totals['protein_per_serving_g']:.1f}g"
        kcal = f"{totals['kcal_per_serving']:.0f}"
        kind = "D" if rec.get("recommendation_kind") == "discovery" else "R"
        print(f"{compact_metric(kind, idx)} {color(rec['name'], PURPLE)}")
        print(
            f"  {metric('cost', cost_pair(totals))}  "
            f"{metric('protein', protein, ORANGE)}  "
            f"{metric('kcal', kcal, ORANGE)}  "
            f"{metric('servings', int(totals['servings']), ORANGE)}  "
            f"{metric('cooked', rec.get('cooked_count', 0), ORANGE)}  "
            f"{metric('mode', recommendation_mode(rec))}"
        )
        if rec["meal_categories"]:
            print(f"  {metric('categories', category_text(rec['meal_categories']))}")
        variety_notes = []
        if rec["repeated_categories"]:
            variety_notes.append(f"same category recently: {category_text(rec['repeated_categories'])}")
        if rec["repeated_staples"]:
            variety_notes.append(f"same staple recently: {', '.join(rec['repeated_staples'])}")
        if rec["repeated_proteins"]:
            variety_notes.append(f"same protein recently: {', '.join(rec['repeated_proteins'])}")
        if variety_notes:
            print(f"  {metric('variety note', '; '.join(variety_notes))}")
        print()


def print_shopping_list(conn: sqlite3.Connection, recipe_ids: Iterable[str]) -> None:
    header("SHOPPING LIST")
    rows = shopping_list(conn, recipe_ids)
    total = 0.0
    for item in rows:
        total += float(item["cost_czk"])
        amounts = aggregated_amounts(item)
        source = ",".join(item["sources"])
        price_marker = price_marker_from_sources(item["sources"])
        marker_color = GREEN if price_marker == "✓" else ORANGE
        print(
            f"{padded_color(item['name'], 34, PURPLE)} {' + '.join(amounts):14} "
            f"{color(marked_money(float(item['cost_czk']), price_marker), ORANGE):>13} {color(source, marker_color)}"
        )
    total_marker = price_marker_from_sources(source for item in rows for source in item["sources"])
    print(f"\n{metric('expected total', marked_money(total, total_marker), ORANGE)}")
    print(color(price_legend(), PURPLE_DIM))


CATALOG_SORTS = ["name", "category", "cheap", "calories", "high-calories", "protein", "cooked", "recent"]


def catalog_sort_metric(row: dict[str, object], sort: str) -> tuple[str, str]:
    marker = price_marker_from_totals(row)
    if sort == "cheap":
        return "M", marked_money(float(row["cost_per_serving_czk"]), marker)
    if sort == "calories":
        return "K", f"{float(row['kcal_per_serving']):.0f}"
    if sort == "high-calories":
        return "K", f"{float(row['kcal_per_serving']):.0f}"
    if sort == "protein":
        return "P", f"{float(row['protein_per_serving_g']):.1f}g"
    if sort == "cooked":
        return "C", str(int(row["cooked_count"]))
    if sort == "recent":
        last = str(row["last_cooked"] or "never")
        return "L", last[:10]
    if sort == "category":
        return "CAT", clip(meal_category_label(str(row["category"])), 14)
    return "A", clip(str(row["name"]), 10)


def print_recipes(conn: sqlite3.Connection, sort: str = "name") -> None:
    header(f"RECIPES // SORT {sort}")
    rows = recipe_catalog_rows(conn, sort=sort)
    for row in rows:
        sort_label, sort_value = catalog_sort_metric(row, sort)
        if row["kind"] == "candidate":
            print(
                f"{compact_metric('YT', row['candidate_id'])} {compact_metric(sort_label, sort_value)} "
                f"{row['name']:<42} {color('youtube candidate', PURPLE):>22} "
                f"{row['servings']} servings cooked::{row['cooked_count']}"
            )
            continue
        review = "llm" if row["reviewed_at"] else "manual"
        print(
            f"{compact_metric(sort_label, sort_value)} "
            f"{row['name']:<36} {padded_color(meal_category_label(str(row['category'])), 20, PURPLE_DIM)} "
            f"{color(marked_money(float(row['cost_czk']), price_marker_from_totals(row)), ORANGE):>11}/batch "
            f"{color(marked_money(float(row['cost_per_serving_czk']), price_marker_from_totals(row)), ORANGE):>11}/meal "
            f"{float(row['kcal_per_serving']):.0f} kcal {float(row['protein_per_serving_g']):.1f}g protein "
            f"cooked::{row['cooked_count']} {color(review, GREEN if review == 'llm' else ORANGE)}"
        )


def print_categories() -> None:
    header("MEAL CATEGORIES")
    for category in meal_category_labels():
        print(category)


def pending_candidate_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM youtube_recipe_candidates
        WHERE status = 'pending_review'
        ORDER BY recipe_name, id
        """
    ).fetchall()


def find_candidate(conn: sqlite3.Connection, query: str) -> sqlite3.Row:
    normalized = query.strip()
    candidate_id = normalized.removeprefix("yt:").removeprefix("youtube:")
    if candidate_id.isdigit():
        row = conn.execute("SELECT * FROM youtube_recipe_candidates WHERE id = ?", (int(candidate_id),)).fetchone()
        if row:
            return row
    row = conn.execute(
        """
        SELECT *
        FROM youtube_recipe_candidates
        WHERE lower(recipe_name) LIKE ?
        ORDER BY CASE status WHEN 'pending_review' THEN 0 ELSE 1 END, length(recipe_name), id
        LIMIT 1
        """,
        (f"%{normalized.lower()}%",),
    ).fetchone()
    if row:
        return row
    raise LookupError(f"YouTube candidate not found: {query}")


def print_recipe_detail(conn: sqlite3.Connection, recipe_query: str) -> None:
    try:
        recipe = find_recipe(conn, recipe_query)
        header(f"RECIPE // {recipe['name']}")
        for line in recipe_overview_lines(conn, recipe["id"]):
            print(line)
        print()
        print(color("ingredients", GREEN))
        for line in recipe_ingredient_lines(conn, recipe["id"], limit=80):
            print(f"  {line}")
        print()
        print(color("steps", GREEN))
        for line in recipe_step_lines(conn, recipe["id"], width=74, limit=20):
            print(f"  {line}")
    except LookupError:
        row = find_candidate(conn, recipe_query)
        candidate = load_candidate(row)
        header(f"YOUTUBE CANDIDATE // {candidate.name}")
        for line in candidate_overview_lines(row):
            print(line)
        print()
        print(color("ingredients", GREEN))
        for line in candidate_ingredient_lines(row, limit=80):
            print(f"  {line}")
        print()
        print(color("steps", GREEN))
        for line in candidate_step_lines(row, width=74, limit=20):
            print(f"  {line}")


def print_ingredients(conn: sqlite3.Connection) -> None:
    header("INGREDIENTS")
    rows = conn.execute(
        """
        SELECT i.name, i.category, p.price_per_kg, p.price_per_l, p.price_per_unit, p.source
        FROM ingredients i
        LEFT JOIN prices p ON p.ingredient_id = i.id
        GROUP BY i.id
        ORDER BY i.category, i.name
        """
    ).fetchall()
    for row in rows:
        price = row["price_per_kg"] or row["price_per_l"] or row["price_per_unit"] or 0
        unit = "kg" if row["price_per_kg"] else "l" if row["price_per_l"] else "unit"
        source_color = GREEN if row["source"] == "real_purchase" else ORANGE
        price_text = f"{price:>8.2f} Kč/{unit:<4}"
        print(
            f"{padded_color(row['name'], 38, PURPLE)} {row['category']:<12} "
            f"{color(price_text, ORANGE)} {color(row['source'], source_color)}"
        )


def term_size() -> tuple[int, int]:
    size = os.get_terminal_size()
    return size.columns, size.lines


def write_line(text: str = "") -> None:
    sys.stdout.write(text + "\n")


def draw_box(title: str, lines: list[str], width: int) -> None:
    inner = max(20, width - 2)
    write_line(color("+" + "-" * inner + "+", GREEN))
    label = f"[ {title} ]"
    write_line(color("|", GREEN) + " " + fit_line(color(label, PURPLE), inner - 2) + " " + color("|", GREEN))
    write_line(color("|" + "-" * inner + "|", PURPLE_DIM))
    for line in lines:
        write_line(color("|", GREEN) + " " + fit_line(line, inner - 2) + " " + color("|", GREEN))
    write_line(color("+" + "-" * inner + "+", GREEN))


def key_hint_lines(view: str = "recommendations") -> list[str]:
    first = (
        f"{color('q', ORANGE)} quit  {color('up/down', ORANGE)} move  {color('r', ORANGE)} recs  "
        f"{color('c', ORANGE)} recipes  {color('p', ORANGE)} history  {color('h', ORANGE)} help"
    )
    if view == "detail":
        second = (
            f"{color('m', ORANGE)} ask/modify with Copilot  {color('s', ORANGE)} shopping  "
            f"{color('r', ORANGE)} back to recs"
        )
    elif view == "recipes":
        second = (
            f"{color('enter/d', ORANGE)} details  {color('a', ORANGE)} cook  {color('x', ORANGE)} delete  "
            f"{color('o', ORANGE)} sort  {color('/', ORANGE)} search"
        )
    elif view == "history":
        second = f"{color('enter/d', ORANGE)} details  {color('r', ORANGE)} back to recommendations"
    else:
        second = (
            f"{color('enter/a', ORANGE)} accept  {color('x', ORANGE)} reject  {color('d', ORANGE)} details  "
            f"{color('s', ORANGE)} shopping  {color('/', ORANGE)} search  {color('i', ORANGE)} ingredients"
        )
    return [first, second]


def decode_escape_sequence(sequence: str) -> str:
    if sequence in ("[A", "OA"):
        return "up"
    if sequence in ("[B", "OB"):
        return "down"
    if sequence.endswith("A") and sequence.startswith("["):
        return "up"
    if sequence.endswith("B") and sequence.startswith("["):
        return "down"
    return "escape"


def read_char() -> str:
    return os.read(sys.stdin.fileno(), 1).decode("utf-8", "ignore")


def read_escape_sequence() -> str:
    if not select.select([sys.stdin], [], [], 0.08)[0]:
        return ""
    sequence = read_char()
    for _ in range(8):
        if len(sequence) > 1 and (sequence[-1].isalpha() or sequence[-1] == "~"):
            break
        if not select.select([sys.stdin], [], [], 0.08)[0]:
            break
        char = read_char()
        sequence += char
    return sequence


def read_key() -> str:
    char = read_char()
    if char == "\x1b":
        return decode_escape_sequence(read_escape_sequence())
    if char in ("\r", "\n"):
        return "enter"
    if char in ("\x7f", "\b"):
        return "backspace"
    if char == "\x15":
        return "clear"
    return char.lower()


def recipe_review_label(conn: sqlite3.Connection, recipe_id: str) -> str:
    row = conn.execute(
        "SELECT decision_status, protein_status FROM recipe_reviews WHERE recipe_id = ?",
        (recipe_id,),
    ).fetchone()
    if not row:
        return "manual review pending"
    return f"llm::{row['decision_status']} protein::{row['protein_status']}"


def recent_meal_lines(conn: sqlite3.Connection, limit: int = RECENT_MEALS_LIMIT) -> list[str]:
    rows = conn.execute(
        """
        SELECT mh.created_at, mh.action, mh.score, r.name, r.id
        FROM meal_history mh
        JOIN recipes r ON r.id = mh.recipe_id
        WHERE mh.action = 'accepted'
        ORDER BY mh.created_at DESC, mh.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    if not rows:
        return ["No cooked meals recorded yet."]
    lines = []
    for row in rows:
        created = str(row["created_at"])[:16]
        lines.append(f"{color(created, ORANGE)}  {row['name']}")
    return lines


def sort_catalog_rows(rows: list[dict[str, object]], sort: str) -> list[dict[str, object]]:
    def row_name(row: dict[str, object]) -> str:
        return str(row["name"]).lower()

    if sort == "cheap":

        def key(row: dict[str, object]) -> tuple[float, str]:
            return float(row["cost_per_serving_czk"]), row_name(row)
    elif sort == "calories":

        def key(row: dict[str, object]) -> tuple[float, str]:
            return float(row["kcal_per_serving"]), row_name(row)
    elif sort == "high-calories":

        def key(row: dict[str, object]) -> tuple[float, str]:
            return -float(row["kcal_per_serving"]), row_name(row)
    elif sort == "protein":

        def key(row: dict[str, object]) -> tuple[float, str]:
            return -float(row["protein_per_serving_g"]), row_name(row)
    elif sort == "cooked":

        def key(row: dict[str, object]) -> tuple[int, str]:
            return -int(row["cooked_count"]), row_name(row)
    elif sort == "category":

        def key(row: dict[str, object]) -> tuple[str, str]:
            return str(row["category"]), row_name(row)
    elif sort == "recent":

        def key(row: dict[str, object]) -> tuple[str, str]:
            return str(row["last_cooked"] or ""), row_name(row)

        return sorted(rows, key=key, reverse=True)
    else:

        def key(row: dict[str, object]) -> tuple[str, str]:
            return str(row["status"]), row_name(row)

    return sorted(rows, key=key)


def recipe_catalog_rows(conn: sqlite3.Connection, sort: str = "name") -> list[dict[str, object]]:
    recipe_rows = conn.execute(
        """
        SELECT r.*, rr.reviewed_at, count(ri.id) AS ingredient_count
        FROM recipes r
        LEFT JOIN recipe_reviews rr ON rr.recipe_id = r.id
        LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id
        WHERE r.status != 'deleted'
        GROUP BY r.id
        """
    ).fetchall()
    rows: list[dict[str, object]] = []
    for row in recipe_rows:
        totals = recipe_totals(conn, row["id"])
        categories = recipe_meal_categories(conn, row)
        history = conn.execute(
            """
            SELECT count(*) AS cooked_count, max(created_at) AS last_cooked
            FROM meal_history
            WHERE recipe_id = ? AND action = 'accepted'
            """,
            (row["id"],),
        ).fetchone()
        rows.append(
            {
                "kind": "recipe",
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "reviewed_at": row["reviewed_at"],
                "ingredient_count": row["ingredient_count"],
                "servings": row["servings"],
                "category": primary_meal_category(categories),
                "categories": categories,
                "cooked_count": int(history["cooked_count"] or 0),
                "last_cooked": history["last_cooked"] or "",
                **totals,
            }
        )
    for row in pending_candidate_rows(conn):
        candidate = load_candidate(row)
        rows.append(
            {
                "kind": "candidate",
                "id": f"yt:{row['id']}",
                "candidate_id": row["id"],
                "name": candidate.name,
                "status": "youtube",
                "reviewed_at": None,
                "ingredient_count": len(candidate.ingredients),
                "servings": candidate.servings,
                "category": "youtube",
                "categories": ["youtube"],
                "cooked_count": 0,
                "last_cooked": "",
                "cost_czk": 0.0,
                "cost_per_serving_czk": 0.0,
                "kcal_per_serving": 0.0,
                "protein_per_serving_g": 0.0,
                "video_id": row["video_id"],
            }
        )
    return sort_catalog_rows(rows, sort if sort in CATALOG_SORTS else "name")


def searchable_recipe_text(row: dict[str, object]) -> str:
    category_labels = " ".join(meal_category_label(str(category)) for category in row.get("categories", []))
    return " ".join(
        [
            str(row.get("name", "")),
            str(row.get("status", "")),
            str(row.get("category", "")),
            category_labels,
        ]
    ).lower()


def filter_recipe_rows(rows: list[dict[str, object]], query: str) -> list[dict[str, object]]:
    terms = [term for term in query.lower().split() if term]
    if not terms:
        return rows
    return [row for row in rows if all(term in searchable_recipe_text(row) for term in terms)]


def visible_window(total: int, selected: int, limit: int) -> tuple[int, int]:
    limit = max(1, limit)
    selected = min(max(selected, 0), max(0, total - 1))
    start = max(0, selected - limit // 2)
    end = min(total, start + limit)
    start = max(0, end - limit)
    return start, end


def recipe_lines(
    conn: sqlite3.Connection,
    selected: int = 0,
    limit: int = 14,
    sort: str = "name",
    rows: list[dict[str, object]] | None = None,
    query: str = "",
    total_count: int | None = None,
) -> list[str]:
    rows = rows if rows is not None else recipe_catalog_rows(conn, sort=sort)
    total_count = len(rows) if total_count is None else total_count
    start, end = visible_window(len(rows), selected, limit)
    lines = []
    if rows:
        lines.append(
            f"{metric('recipes', f'{len(rows)}/{total_count}', ORANGE)}  {metric('selected', selected + 1, ORANGE)}  "
            f"{metric('sort', sort, ORANGE)}  "
            f"{metric('search', query or 'off', ORANGE)}  "
            f"{color('category shown; / types search; backspace edits; o cycles sort; a cooks selected; x deletes selected', PURPLE_DIM)}"
        )
    elif query:
        return [
            f"{metric('recipes', f'0/{total_count}', ORANGE)}  {metric('sort', sort, ORANGE)}  "
            f"{metric('search', query, ORANGE)}",
            "No recipes match the current search.",
        ]
    for idx, row in enumerate(rows[start:end], start=start):
        prefix = color(">*", ORANGE) if idx == selected else "  "
        name_color = PURPLE if idx == selected else TEXT
        category = clip(meal_category_label(str(row["category"])), 14)
        sort_label, sort_value = catalog_sort_metric(row, sort)
        if row["kind"] == "candidate":
            lines.append(
                f"{prefix} {compact_metric('YT', row['candidate_id'])} {compact_metric(sort_label, sort_value)} "
                f"{padded_color(clip(row['name'], 24), 24, name_color)} "
                f"{fit_line(color(category, PURPLE_DIM), 14)} "
                f"{compact_metric('S', row['servings'])} "
                f"{compact_metric('C', row['cooked_count'])} pending review"
            )
        else:
            review = "llm" if row["reviewed_at"] else "manual"
            protein = f"{float(row['protein_per_serving_g']):.1f}g"
            marker = price_marker_from_totals(row)
            lines.append(
                f"{prefix} {compact_metric(sort_label, sort_value)} "
                f"{padded_color(clip(row['name'], 24), 24, name_color)} "
                f"{fit_line(color(category, PURPLE_DIM), 14)} "
                f"{compact_metric('S', row['servings'])} "
                f"{compact_metric('C', row['cooked_count'])} "
                f"{compact_metric('P', protein)} "
                f"{compact_metric('M', marked_money(float(row['cost_per_serving_czk']), marker))} {review}"
            )
    return lines or ["No recipes available."]


def history_rows(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT mh.id AS history_id, mh.created_at, mh.notes, r.id AS recipe_id, r.name, r.status
        FROM meal_history mh
        JOIN recipes r ON r.id = mh.recipe_id
        WHERE mh.action = 'accepted'
        ORDER BY mh.created_at DESC, mh.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def history_lines(rows: list[dict[str, object]], selected: int = 0, limit: int = 14) -> list[str]:
    if not rows:
        return ["No cooked meals recorded yet."]
    selected = min(max(selected, 0), max(0, len(rows) - 1))
    start, end = visible_window(len(rows), selected, limit)
    lines = [
        f"{metric('meals', len(rows), ORANGE)}  {metric('selected', selected + 1, ORANGE)}  "
        f"{color('enter/d opens recipe details; r returns to recommendations', PURPLE_DIM)}"
    ]
    for idx, row in enumerate(rows[start:end], start=start):
        prefix = color(">*", ORANGE) if idx == selected else "  "
        created = str(row["created_at"])[:16]
        status = str(row["status"])
        lines.append(
            f"{prefix} {color(created, ORANGE)}  {clip(row['name'], 44):<44} {compact_metric('status', status)}"
        )
    return lines


def ingredient_lines(conn: sqlite3.Connection, limit: int = 14) -> list[str]:
    rows = conn.execute(
        """
        SELECT i.name, i.category, p.price_per_kg, p.price_per_l, p.price_per_unit, p.source
        FROM ingredients i
        LEFT JOIN prices p ON p.ingredient_id = i.id
        GROUP BY i.id
        ORDER BY i.category, i.name
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    lines = []
    for row in rows:
        price = row["price_per_kg"] or row["price_per_l"] or row["price_per_unit"] or 0
        unit = "kg" if row["price_per_kg"] else "l" if row["price_per_l"] else "unit"
        price_text = f"{price:>7.2f} Kč/{unit:<4}"
        lines.append(f"{row['name']:<30} {row['category']:<10} {color(price_text, ORANGE)} {row['source']}")
    return lines


def shopping_lines(conn: sqlite3.Connection, recipe_id: str) -> list[str]:
    rows = shopping_list(conn, [recipe_id])
    lines = []
    total = 0.0
    for item in rows:
        total += float(item["cost_czk"])
        amounts = aggregated_amounts(item)
        marker = price_marker_from_sources(item["sources"])
        lines.append(
            f"{item['name']:<28} {fit_line(color(' + '.join(amounts), ORANGE), 12)} "
            f"{fit_line(color(marked_money(float(item['cost_czk']), marker), ORANGE), 11)}"
        )
    lines.append("")
    total_marker = price_marker_from_sources(source for item in rows for source in item["sources"])
    lines.append(metric("expected total", marked_money(total, total_marker), ORANGE))
    lines.append(color(price_legend(), PURPLE_DIM))
    return lines


def recipe_overview_lines(conn: sqlite3.Connection, recipe_id: str) -> list[str]:
    recipe = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if recipe is None:
        return ["Recipe not found."]
    totals = recipe_totals(conn, recipe_id)
    history = conn.execute(
        """
        SELECT count(*) AS cooked_count, max(created_at) AS last_cooked
        FROM meal_history
        WHERE recipe_id = ? AND action = 'accepted'
        """,
        (recipe_id,),
    ).fetchone()
    kcal = f"{totals['kcal_per_serving']:.0f} kcal/meal"
    macros = (
        f"P {totals['protein_per_serving_g']:.1f}g  "
        f"C {totals['carbs_per_serving_g']:.1f}g  "
        f"F {totals['fat_per_serving_g']:.1f}g"
    )
    last_cooked = history["last_cooked"] or "never"
    return [
        metric("name", recipe["name"], PURPLE),
        f"{metric('status', recipe['status'])}  {metric('review', recipe_review_label(conn, recipe_id))}",
        metric("categories", category_text(recipe_meal_categories(conn, recipe))),
        f"{metric('servings', int(totals['servings']), ORANGE)}  {metric('calories', kcal, ORANGE)}",
        f"{metric('cost', cost_pair(totals))}  {metric('macros', macros, ORANGE)}",
        metric("price source", price_legend()),
        f"{metric('cooked', int(history['cooked_count'] or 0), ORANGE)}  {metric('last cooked', highlight_numbers(last_cooked))}",
        metric("decision", recipe["decision_reason"] or "No decision note."),
    ]


def recipe_ingredient_lines(conn: sqlite3.Connection, recipe_id: str, limit: int = 10) -> list[str]:
    rows = conn.execute(
        """
        SELECT ri.*, i.name
        FROM recipe_ingredients ri
        JOIN ingredients i ON i.id = ri.ingredient_id
        WHERE ri.recipe_id = ?
        ORDER BY ri.id
        LIMIT ?
        """,
        (recipe_id, limit),
    ).fetchall()
    if not rows:
        return [color("No ingredients recorded yet.", ROSE)]
    lines = []
    for row in rows:
        amount = amount_with_grams(float(row["quantity"]), str(row["unit"]), row["grams"])
        cost = line_cost(conn, row["ingredient_id"], row["quantity"], row["unit"], row["grams"])
        marker = price_marker_for_ingredient(conn, row["ingredient_id"])
        source = latest_price(conn, row["ingredient_id"])
        source_label = "verified" if marker == "✓" else "estimate" if marker == "*" else "missing"
        source_notes = f"{source_label}:{source['source']}" if source else source_label
        lines.append(
            f"{row['name']:<30} {fit_line(color(amount, ORANGE), 14)} "
            f"{fit_line(color(marked_money(cost, marker), ORANGE), 11)} "
            f"{color(source_notes, GREEN if marker == '✓' else ORANGE)}"
        )
    return lines


def procedure_steps(procedure: str) -> list[str]:
    text = re.sub(r"\s+", " ", procedure.strip())
    if not text:
        return []
    return [step.strip().rstrip(".") for step in re.split(r"(?<=[.!?])\s+", text) if step.strip()]


def recipe_step_lines(conn: sqlite3.Connection, recipe_id: str, width: int = 86, limit: int = 8) -> list[str]:
    row = conn.execute("SELECT procedure FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None or not str(row["procedure"]).strip():
        return [color("No cooking steps recorded yet.", ROSE)]
    raw_steps = procedure_steps(str(row["procedure"]))
    if not raw_steps:
        raw_steps = [str(row["procedure"]).strip()]
    lines: list[str] = []
    for idx, step in enumerate(raw_steps, start=1):
        wrapped = textwrap.wrap(step, width=max(32, width - 4)) or [step]
        lines.append(f"{color(str(idx) + '.', ORANGE)} {highlight_numbers(wrapped[0])}")
        lines.extend(f"   {highlight_numbers(part)}" for part in wrapped[1:])
        if len(lines) >= limit:
            break
    return lines[:limit]


def candidate_overview_lines(row: sqlite3.Row) -> list[str]:
    candidate = load_candidate(row)
    return [
        metric("name", candidate.name, PURPLE),
        f"{metric('status', row['status'])}  {metric('source', 'youtube candidate')}",
        f"{metric('candidate id', 'yt:' + str(row['id']), ORANGE)}  {metric('video', row['video_id'])}",
        f"{metric('servings', candidate.servings, ORANGE)}  {metric('confidence', f'{candidate.confidence:.2f}', ORANGE)}",
        metric("decision", candidate.decision_reason or candidate.decision or "Pending review."),
        color("Approve with: meal-planner youtube candidates approve " + str(row["id"]), PURPLE_DIM),
    ]


def candidate_ingredient_lines(row: sqlite3.Row, limit: int = 10) -> list[str]:
    candidate = load_candidate(row)
    if not candidate.ingredients:
        return [color("No ingredients recorded yet.", ROSE)]
    lines = []
    for ingredient in candidate.ingredients[:limit]:
        amount = amount_with_grams(ingredient.quantity, ingredient.unit, ingredient.grams)
        notes = f" — {ingredient.notes}" if ingredient.notes else ""
        lines.append(f"{ingredient.name:<30} {fit_line(color(amount, ORANGE), 18)}{highlight_numbers(notes)}")
    return lines


def candidate_step_lines(row: sqlite3.Row, width: int = 86, limit: int = 8) -> list[str]:
    candidate = load_candidate(row)
    if not candidate.procedure.strip():
        return [color("No cooking steps recorded yet.", ROSE)]
    raw_steps = procedure_steps(candidate.procedure)
    if not raw_steps:
        raw_steps = [candidate.procedure.strip()]
    lines: list[str] = []
    for idx, step in enumerate(raw_steps, start=1):
        wrapped = textwrap.wrap(step, width=max(32, width - 4)) or [step]
        lines.append(f"{color(str(idx) + '.', ORANGE)} {highlight_numbers(wrapped[0])}")
        lines.extend(f"   {highlight_numbers(part)}" for part in wrapped[1:])
        if len(lines) >= limit:
            break
    return lines[:limit]


def detail_name(conn: sqlite3.Connection, item_id: str) -> str:
    if item_id.startswith("yt:"):
        row = find_candidate(conn, item_id)
        return load_candidate(row).name
    recipe = conn.execute("SELECT name FROM recipes WHERE id = ?", (item_id,)).fetchone()
    return recipe["name"] if recipe else "Unknown recipe"


def detail_overview_lines(conn: sqlite3.Connection, item_id: str) -> list[str]:
    if item_id.startswith("yt:"):
        return candidate_overview_lines(find_candidate(conn, item_id))
    return recipe_overview_lines(conn, item_id)


def detail_ingredient_lines(conn: sqlite3.Connection, item_id: str, limit: int = 10) -> list[str]:
    if item_id.startswith("yt:"):
        return candidate_ingredient_lines(find_candidate(conn, item_id), limit=limit)
    return recipe_ingredient_lines(conn, item_id, limit=limit)


def detail_step_lines(conn: sqlite3.Connection, item_id: str, width: int = 86, limit: int = 8) -> list[str]:
    if item_id.startswith("yt:"):
        return candidate_step_lines(find_candidate(conn, item_id), width=width, limit=limit)
    return recipe_step_lines(conn, item_id, width=width, limit=limit)


def copilot_reply_lines(reply: str, width: int = 86, limit: int = 6) -> list[str]:
    text = reply.strip()
    if not text:
        return []
    wrapped: list[str] = []
    for paragraph in text.splitlines():
        wrapped.extend(textwrap.wrap(paragraph, width=max(32, width)) or [""])
    return [highlight_numbers(line) for line in wrapped[:limit]]


def read_text_prompt(old_term: list[object], prompt: str) -> str:
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_term)
    sys.stdout.write(SHOW_CURSOR + RESET + "\n")
    sys.stdout.write(prompt + "\n> ")
    sys.stdout.flush()
    try:
        return sys.stdin.readline().strip()
    finally:
        tty.setcbreak(sys.stdin.fileno())
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()


def draw_interactive(
    conn: sqlite3.Connection,
    view: str,
    selected: int,
    recipe_selected: int = 0,
    recipe_sort: str = "name",
    detail_recipe_id: str | None = None,
    history_selected: int = 0,
    search_query: str = "",
    message: str = "",
    copilot_reply: str = "",
    recs: list[dict[str, object]] | None = None,
    recipes: list[dict[str, object]] | None = None,
    history: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    columns, lines = term_size()
    width = min(max(columns - 2, 78), 116)
    max_recs = max(3, min(6, lines - 19))
    if recs is None:
        recs = recommendations(conn, limit=max_recs)
    selected = min(max(selected, 0), max(0, len(recs) - 1))
    selected_rec = recs[selected] if recs else None
    if recipes is None:
        recipes = recipe_catalog_rows(conn, sort=recipe_sort) if view == "recipes" else []
    recipe_total = len(recipes)
    visible_recipes = filter_recipe_rows(recipes, search_query)
    recipe_selected = min(max(recipe_selected, 0), max(0, len(visible_recipes) - 1))
    if history is None:
        history = history_rows(conn) if view == "history" else []
    history_selected = min(max(history_selected, 0), max(0, len(history) - 1))

    sys.stdout.write(CLEAR + HIDE_CURSOR)
    draw_box("MEAL PLANNER // EVA-01 LOCAL", [*key_hint_lines(view), message or "ready"], width)

    if view == "help":
        draw_box(
            "HELP",
            [
                "This is the interactive mode. No commands are needed while it is open.",
                "Use Up/Down arrow keys to move through recommendations.",
                "Press enter or a to accept/cook the selected recipe.",
                "Press c for the recipe catalog; enter/d opens details and a cooks the selected recipe.",
                "Press / to type a live recipe search; Enter finishes typing and keeps the filter.",
                "Press p from recommendations to open past cooked meals; enter/d opens their details.",
                "In the recipe catalog, o cycles sorting and x deletes/hides the selected recipe.",
                "In a detail view, press m to ask Copilot or request a structured recipe update.",
                "Press x to reject a recommendation, d for selected details, s for a shopping list.",
                "Press r to return to recommendations and q to quit safely.",
            ],
            width,
        )
    elif view == "recipes":
        draw_box(
            "RECIPES",
            recipe_lines(
                conn,
                selected=recipe_selected,
                limit=max(8, lines - 10),
                sort=recipe_sort,
                rows=visible_recipes,
                query=search_query,
                total_count=recipe_total,
            ),
            width,
        )
    elif view == "history":
        draw_box("PAST MEALS", history_lines(history, selected=history_selected, limit=max(8, lines - 10)), width)
    elif view == "ingredients":
        draw_box("INGREDIENTS", ingredient_lines(conn, limit=max(8, lines - 10)), width)
    elif view == "shopping" and (detail_recipe_id or selected_rec):
        recipe_id = detail_recipe_id or str(selected_rec["recipe_id"])
        draw_box(f"SHOPPING // {detail_name(conn, recipe_id)}", shopping_lines(conn, recipe_id), width)
    elif view == "detail" and (detail_recipe_id or selected_rec):
        recipe_id = detail_recipe_id or str(selected_rec["recipe_id"])
        recipe_name = detail_name(conn, recipe_id)
        draw_box(f"DETAIL // {recipe_name}", detail_overview_lines(conn, recipe_id), width)
        if copilot_reply:
            draw_box("COPILOT", copilot_reply_lines(copilot_reply, width=width - 8, limit=max(3, lines // 6)), width)
        draw_box("INGREDIENTS", detail_ingredient_lines(conn, recipe_id, limit=max(4, min(12, lines // 3))), width)
        draw_box("STEPS", detail_step_lines(conn, recipe_id, width=width - 8, limit=max(4, lines // 4)), width)
    else:
        ranking: list[str] = []
        for idx, rec in enumerate(recs):
            prefix = color(">*", ORANGE) if idx == selected else "  "
            totals = rec["totals"]
            name = f"{clip(rec['name'], 24):<24}"
            marker = price_marker_from_totals(totals)
            batch = f"{marked_money(totals['cost_czk'], marker):>10}"
            meal = f"{marked_money(totals['cost_per_serving_czk'], marker):>9}"
            protein = f"{totals['protein_per_serving_g']:>4.1f}g"
            cooked = f"{int(rec.get('cooked_count', 0)):>2}"
            kind = "D" if rec.get("recommendation_kind") == "discovery" else "R"
            ranking.append(
                f"{prefix} {compact_metric(kind, idx + 1)} {color(name, PURPLE if idx == selected else TEXT)} "
                f"{compact_metric('B', batch)} "
                f"{compact_metric('M', meal)} "
                f"{compact_metric('P', protein)} "
                f"{compact_metric('C', cooked)}"
            )
        draw_box("RECOMMENDATIONS", ranking or ["No approved recipes available."], width)
        if selected_rec:
            totals = selected_rec["totals"]
            kcal = f"{totals['kcal_per_serving']:.0f}/meal"
            protein = f"{totals['protein_per_serving_g']:.1f}g"
            detail = [
                metric("name", selected_rec["name"], PURPLE),
                f"{metric('servings', int(totals['servings']), ORANGE)}  {metric('kcal', kcal, ORANGE)}",
                f"{metric('cost', cost_pair(totals))}  {metric('protein', protein, ORANGE)}",
                metric("price source", price_legend()),
                metric("cooked", selected_rec.get("cooked_count", 0), ORANGE),
                metric("mode", recommendation_mode(selected_rec)),
                metric("categories", category_text(selected_rec.get("meal_categories", []))),
                metric("review", recipe_review_label(conn, str(selected_rec["recipe_id"]))),
            ]
            draw_box("SELECTED", detail, width)
            draw_box(f"RECENT MEALS // LAST {RECENT_MEALS_LIMIT}", recent_meal_lines(conn, RECENT_MEALS_LIMIT), width)
    sys.stdout.flush()
    return {
        "recommendations": recs,
        "recipes": visible_recipes,
        "recipe_selected": recipe_selected,
        "history": history,
        "history_selected": history_selected,
    }


def run_interactive(conn: sqlite3.Connection) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print_dashboard(conn)
        return

    old_term = termios.tcgetattr(sys.stdin)
    view = "recommendations"
    selected = 0
    recipe_selected = 0
    recipe_sort = "name"
    detail_recipe_id: str | None = None
    history_selected = 0
    search_query = ""
    search_active = False
    message = "q exits; enter accepts the highlighted recommendation"
    copilot_reply = ""
    recs_cache: list[dict[str, object]] | None = None
    recipes_cache: list[dict[str, object]] | None = None
    history_cache: list[dict[str, object]] | None = None
    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            max_recs = max(3, min(6, term_size()[1] - 19))
            if recs_cache is None:
                recs_cache = recommendations(conn, limit=max_recs)
            if view == "recipes" and recipes_cache is None:
                recipes_cache = recipe_catalog_rows(conn, sort=recipe_sort)
            state = draw_interactive(
                conn,
                view,
                selected,
                recipe_selected,
                recipe_sort,
                detail_recipe_id,
                history_selected,
                search_query,
                message,
                copilot_reply,
                recs=recs_cache,
                recipes=recipes_cache,
                history=history_cache,
            )
            recs = state["recommendations"]
            recipes = state["recipes"]
            recipe_selected = int(state["recipe_selected"])
            history = state["history"]
            history_selected = int(state["history_selected"])
            if view == "history" and history_cache is None:
                history_cache = history
            key = read_key()
            message = ""
            if key == "q":
                break
            if key in ("j", "down"):
                if view == "recipes":
                    recipe_selected = min(recipe_selected + 1, max(0, len(recipes) - 1))
                elif view == "history":
                    history_selected = min(history_selected + 1, max(0, len(history) - 1))
                else:
                    selected = min(selected + 1, max(0, len(recs) - 1))
                    view = "recommendations" if view == "shopping" else view
            elif key in ("k", "up"):
                if view == "recipes":
                    recipe_selected = max(0, recipe_selected - 1)
                elif view == "history":
                    history_selected = max(0, history_selected - 1)
                else:
                    selected = max(0, selected - 1)
                    view = "recommendations" if view == "shopping" else view
            elif key == "escape" and view == "recipes" and search_active:
                search_active = False
                message = "search input paused; press / to edit or r for recommendations"
            elif view == "recipes" and search_active and key == "backspace":
                search_query = search_query[:-1]
                recipe_selected = 0
                message = f"search::{search_query or 'off'}"
            elif view == "recipes" and search_active and key == "clear":
                search_query = ""
                recipe_selected = 0
                message = "search cleared"
            elif view == "recipes" and search_active and key == "enter":
                search_active = False
                message = "search locked; shortcuts active; press / to edit or enter to open details"
            elif view == "recipes" and search_active and len(key) == 1 and key.isprintable():
                search_query += key
                recipe_selected = 0
                message = f"search::{search_query}"
            elif key in ("r", "escape"):
                view = "recommendations"
                detail_recipe_id = None
                copilot_reply = ""
                search_active = False
            elif key == "c":
                view = "recipes"
                detail_recipe_id = None
                copilot_reply = ""
                search_active = False
            elif key == "p":
                view = "history"
                detail_recipe_id = None
                copilot_reply = ""
                history_selected = 0
                history_cache = None
                search_active = False
            elif key == "i":
                view = "ingredients"
                copilot_reply = ""
                search_active = False
            elif key == "h":
                view = "help"
                copilot_reply = ""
                search_active = False
            elif key == "s":
                if view == "detail" and detail_recipe_id and detail_recipe_id.startswith("yt:"):
                    message = "shopping lists are available after approving the YouTube candidate"
                else:
                    view = "shopping"
                    search_active = False
            elif key == "/":
                view = "recipes"
                detail_recipe_id = None
                search_active = True
                message = "search: type recipe text; enter finishes typing; q still quits"
            elif key == "o" and view == "recipes":
                index = CATALOG_SORTS.index(recipe_sort) if recipe_sort in CATALOG_SORTS else 0
                recipe_sort = CATALOG_SORTS[(index + 1) % len(CATALOG_SORTS)]
                recipe_selected = 0
                recipes_cache = None
                message = f"recipe sort::{recipe_sort}"
            elif key == "d":
                if view == "recipes" and recipes:
                    detail_recipe_id = str(recipes[recipe_selected]["id"])
                elif view == "history" and history:
                    detail_recipe_id = str(history[history_selected]["recipe_id"])
                elif recs:
                    detail_recipe_id = str(recs[selected]["recipe_id"])
                view = "detail"
                copilot_reply = ""
                search_active = False
            elif key == "enter" and view == "recipes" and recipes:
                detail_recipe_id = str(recipes[recipe_selected]["id"])
                view = "detail"
                copilot_reply = ""
                search_active = False
            elif key == "enter" and view == "history" and history:
                detail_recipe_id = str(history[history_selected]["recipe_id"])
                view = "detail"
                copilot_reply = ""
            elif key == "m" and view == "detail" and detail_recipe_id:
                if detail_recipe_id.startswith("yt:"):
                    message = "Copilot chat is available after approving the YouTube candidate"
                    continue
                recipe_name = detail_name(conn, detail_recipe_id)
                user_request = read_text_prompt(
                    old_term,
                    f"Ask Copilot about {recipe_name}. Ask a question or request a recipe change.",
                )
                if not user_request:
                    message = "Copilot request cancelled"
                    continue
                message = "asking Copilot..."
                draw_interactive(
                    conn,
                    view,
                    selected,
                    recipe_selected,
                    recipe_sort,
                    detail_recipe_id,
                    history_selected,
                    search_query,
                    message,
                    copilot_reply,
                    recs=recs_cache,
                    recipes=recipes_cache,
                    history=history_cache,
                )
                try:
                    result = ask_recipe_copilot(conn, detail_recipe_id, user_request)
                except Exception as exc:
                    message = f"Copilot error: {type(exc).__name__}: {exc}"
                    copilot_reply = ""
                else:
                    copilot_reply = result.message
                    message = (
                        "recipe updated; totals recalculated"
                        if result.updated
                        else "Copilot answered; no recipe change"
                    )
                    if result.updated:
                        recs_cache = None
                        recipes_cache = None
                        history_cache = None
            elif key == "a" and view == "recipes" and recipes:
                item = recipes[recipe_selected]
                if str(item["id"]).startswith("yt:"):
                    message = "approve YouTube candidates before cooking them"
                else:
                    record_decision(conn, str(item["id"]), "accepted", "Accepted from recipe catalog.")
                    message = f"cooked {item['name']}"
                    recipe_selected = 0
                    recs_cache = None
                    recipes_cache = None
                    history_cache = None
            elif key in ("enter", "a") and view == "recommendations" and recs:
                recipe_id = str(recs[selected]["recipe_id"])
                record_decision(conn, recipe_id, "accepted", "Accepted from interactive TUI.")
                message = f"accepted {recs[selected]['name']}"
                view = "recommendations"
                selected = 0
                recs_cache = None
                history_cache = None
            elif key == "x" and view == "recipes" and recipes:
                item = recipes[recipe_selected]
                if str(item["id"]).startswith("yt:"):
                    message = "discard YouTube candidates from the youtube candidates command"
                else:
                    conn.execute("UPDATE recipes SET status = 'deleted' WHERE id = ?", (str(item["id"]),))
                    conn.commit()
                    message = f"deleted {item['name']}"
                    recipe_selected = min(recipe_selected, max(0, len(recipes) - 2))
                    recs_cache = None
                    recipes_cache = None
            elif key == "x" and view == "recommendations" and recs:
                recipe_id = str(recs[selected]["recipe_id"])
                record_decision(conn, recipe_id, "rejected", "Rejected from interactive TUI.")
                message = f"rejected {recs[selected]['name']}"
                view = "recommendations"
                selected = 0
                recs_cache = None
            else:
                message = "unknown key; press h for help or q to quit"
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_term)
        sys.stdout.write(SHOW_CURSOR + RESET + "\n")
        sys.stdout.flush()
