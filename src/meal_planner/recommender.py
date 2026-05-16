from __future__ import annotations

import json
import re
import sqlite3

from .calculations import recipe_tags, recipe_totals

PROTEIN_TARGET_G = 35.0
RECENT_RECIPE_EXCLUSION_LIMIT = 5
RECENT_CATEGORY_LIMIT = 5
RECENT_REJECTED_LIMIT = 10
STAPLE_TAGS = {"rice", "pasta", "wrap", "potato", "noodles", "bread", "pastry"}
PROTEIN_TAGS = {"chicken", "red_meat", "pork", "fish", "egg", "legume", "organ_meat"}
RECENT_CATEGORY_PENALTIES = (-52.0, -32.0, -20.0, -12.0, -8.0)
COMPONENT_MEAL_PENALTY = -60.0
LOW_PROTEIN_MEAL_PENALTY = -25.0
COOKED_COUNT_PENALTY = -4.0
REJECTED_COUNT_PENALTY = -12.0
RECENT_REJECTED_RECIPE_PENALTY = -40.0
MIN_RECOMMENDATION_SCORE = 35.0
MIN_RECOMMENDATION_COUNT = 3
MEAL_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "pasta_lasagna": (
        "agnolotti",
        "canelones",
        "pasta",
        "spaghetti",
        "carbonara",
        "gricia",
        "cacio e pepe",
        "aglio e olio",
        "amatriciana",
        "pesto pasta",
        "lasagna",
        "lasaña",
        "ravioli",
        "tagliatelle",
        "fettuccine",
        "fettuccini",
        "mac and cheese",
        "uovo in raviolo",
        "capriccio di faenza",
    ),
    "rice_bowls": (
        "arroz",
        "rice",
        "risotto",
        "paella",
        "biryani",
        "biriyani",
        "pilaf",
        "bibimbap",
        "sushi",
        "nasi goreng",
        "omurice",
        "onigiri",
        "gohan",
        "sinangag",
        "hainanes",
        "hainanés",
    ),
    "noodles_ramen": (
        "noodle",
        "noodles",
        "ramen",
        "udon",
        "soba",
        "yakisoba",
        "chow mein",
        "lo mein",
        "jjajangmyeon",
        "biang biang",
        "khao soi",
        "dan dan",
        "pad thai",
        "tallarines",
        "tteokbokki",
    ),
    "curries_dals": ("curry", "masala", "dal", "daal", "matar paneer", "ají de gallina", "mole poblano", "korma"),
    "soups_stews": (
        "stew",
        "soup",
        "sopa",
        "puchero",
        "lentejas",
        "lentil",
        "guiso",
        "cocido",
        "chili",
        "borscht",
        "harira",
        "minestrone",
        "avgolemono",
        "crema cremosa",
        "tom yum",
        "galbi-jjim",
        "pozole",
    ),
    "tacos_wraps": (
        "wrap",
        "burrito",
        "burritos",
        "taco",
        "tacos",
        "quesadilla",
        "sincronizadas",
        "fajita",
        "tortilla",
        "enchilada",
        "enchiladas",
        "chilaquiles",
        "nachos",
        "arepas",
        "pani puris",
        "pato laqueado",
        "rollitos primavera",
    ),
    "sandwiches_burgers": (
        "burger",
        "hamburger",
        "hamburguesa",
        "goiko",
        "sandwich",
        "sándwich",
        "sando",
        "bocadillo",
        "panini",
        "grilled cheese",
        "montecristo",
        "blt",
        "bao",
        "baos",
        "nashville hot chicken",
        "katsu-sando",
        "gyukatsu",
    ),
    "pizza_flatbread": ("pizza", "calzone", "flatbread", "schiacciata", "focaccia", "baguette fake pizza"),
    "empanadas_pies": ("empanada", "empanadas", "pie", "pastel", "wellington"),
    "salads_cold": (
        "salad",
        "ensalada",
        "ensaladilla",
        "fattush",
        "fattoush",
        "causa",
        "ajoblanco",
        "som tam",
        "tabbule",
        "tabbouleh",
        "tarator",
        "yam khai dao",
    ),
    "egg_dishes": ("omelet", "omelette", "tortilla francesa", "frittata", "huevos", "huevo", "scotch egg", "shakshuka"),
    "protein_mains": (
        "pollo",
        "chicken",
        "cerdo",
        "pork",
        "beef",
        "ternera",
        "solomillo",
        "entrecot",
        "salmón",
        "salmon",
        "fish",
        "pescado",
        "langostinos",
        "tempura",
        "alitas",
        "wings",
        "char siu",
        "barbacoa",
        "cochinita",
        "kebab",
        "pinchos",
        "nuggets",
        "mapo tofu",
        "moussaka",
        "laab moo",
        "hongshaorou",
        "berenjenas salteadas",
        "yu xiang",
    ),
    "vegetable_potato": (
        "potato",
        "patata",
        "patatas",
        "microwaved potatoes",
        "gnocchi",
        "samosas",
        "calabacín",
        "berenjena",
        "berenjenas",
        "guisantes",
    ),
    "sides_components": (
        "sauce",
        "salsa",
        "mayonnaise",
        "mayonesa",
        "aceite de chile",
        "chutney",
        "kimchi",
        "mermelada",
        "relish",
        "bread",
        "pan ",
        "pan de",
        "panecillos",
        "brioche",
        "mantou",
        "dough",
        "masa",
        "crackers",
        "purple corn drink",
    ),
    "desserts_sweets": (
        "dessert",
        "cookie",
        "cake",
        "chocolate",
        "turron",
        "turrón",
        "mochi",
        "mochis",
        "helado",
        "carrot cake",
        "marshmallow",
        "marshmallows",
        "polvorones",
        "roscón",
    ),
}
MEAL_CATEGORY_LABELS = {
    "pasta_lasagna": "pasta & lasagna",
    "rice_bowls": "rice bowls",
    "noodles_ramen": "noodles & ramen",
    "curries_dals": "curries & dals",
    "soups_stews": "soups & stews",
    "tacos_wraps": "tacos & wraps",
    "sandwiches_burgers": "sandwiches & burgers",
    "pizza_flatbread": "pizza & flatbread",
    "empanadas_pies": "empanadas & pies",
    "salads_cold": "salads & cold plates",
    "egg_dishes": "egg dishes",
    "protein_mains": "protein mains",
    "vegetable_potato": "vegetable & potato",
    "sides_components": "sides & components",
    "desserts_sweets": "desserts & sweets",
    "uncategorized": "uncategorized",
}
CORE_INGREDIENT_CATEGORY_FALLBACK: dict[str, tuple[str, ...]] = {
    "pasta_lasagna": ("pasta-espaguetis",),
    "rice_bowls": ("arroz-basmati",),
    "noodles_ramen": ("noodles",),
    "tacos_wraps": ("wraps",),
    "vegetable_potato": ("patata",),
}
COMPONENT_KEYWORDS = (
    "sauce",
    "salsa",
    "mayonnaise",
    "dough",
    "masa",
    "cracker",
    "crackers",
    "turron",
    "turrón",
    "dessert",
    "cookie",
    "cake",
    "chocolate",
)


def meal_category_names() -> list[str]:
    return list(MEAL_CATEGORY_KEYWORDS)


def meal_category_label(category: str) -> str:
    return MEAL_CATEGORY_LABELS.get(category, category.replace("_", " "))


def meal_category_labels() -> list[str]:
    return [meal_category_label(category) for category in meal_category_names()]


def _keyword_matches(haystack: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in haystack
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", haystack) is not None


def recipe_meal_categories(conn: sqlite3.Connection, recipe: sqlite3.Row) -> list[str]:
    tags = recipe_tags(recipe)
    recipe_text = " ".join([str(recipe["id"]), str(recipe["name"]), str(recipe["raw_source"] or ""), *tags])
    recipe_text = recipe_text.lower().replace("-", " ")
    categories = [
        category
        for category, keywords in MEAL_CATEGORY_KEYWORDS.items()
        if any(_keyword_matches(recipe_text, keyword) for keyword in keywords)
    ]
    if categories:
        return categories

    rows = conn.execute(
        """
        SELECT ri.ingredient_id, ri.grams
        FROM recipe_ingredients ri
        WHERE ri.recipe_id = ?
        """,
        (recipe["id"],),
    ).fetchall()
    ingredient_ids = {str(row["ingredient_id"]) for row in rows if float(row["grams"] or 0) >= 150.0}
    return [
        category
        for category, fallback_ids in CORE_INGREDIENT_CATEGORY_FALLBACK.items()
        if ingredient_ids & set(fallback_ids)
    ]


def primary_meal_category(categories: list[str]) -> str:
    return categories[0] if categories else "uncategorized"


def recent_accepted_category_sets(conn: sqlite3.Connection, limit: int = RECENT_CATEGORY_LIMIT) -> list[set[str]]:
    rows = conn.execute(
        """
        SELECT r.*
        FROM meal_history mh
        JOIN recipes r ON r.id = mh.recipe_id
        WHERE mh.action = 'accepted'
        ORDER BY mh.created_at DESC, mh.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [{primary_meal_category(recipe_meal_categories(conn, row))} for row in rows]


def recent_accepted_tags(conn: sqlite3.Connection, limit: int = 3) -> list[str]:
    rows = conn.execute(
        """
        SELECT r.tags
        FROM meal_history mh
        JOIN recipes r ON r.id = mh.recipe_id
        WHERE mh.action = 'accepted'
        ORDER BY mh.created_at DESC, mh.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    tags: list[str] = []
    for row in rows:
        tags.extend(json.loads(row["tags"]))
    return tags


def recent_accepted_recipe_ids(conn: sqlite3.Connection, limit: int = RECENT_RECIPE_EXCLUSION_LIMIT) -> set[str]:
    rows = conn.execute(
        """
        SELECT recipe_id
        FROM meal_history
        WHERE action = 'accepted'
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return {str(row["recipe_id"]) for row in rows}


def recent_rejected_recipe_ids(conn: sqlite3.Connection, limit: int = RECENT_REJECTED_LIMIT) -> set[str]:
    rows = conn.execute(
        """
        SELECT recipe_id
        FROM meal_history
        WHERE action = 'rejected'
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return {str(row["recipe_id"]) for row in rows}


def score_recipe(
    conn: sqlite3.Connection,
    recipe_id: str,
    recent_tags: list[str] | None = None,
    recent_categories: list[set[str]] | None = None,
) -> dict[str, object]:
    recipe = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if recipe is None:
        raise LookupError(recipe_id)
    totals = recipe_totals(conn, recipe_id)
    tags = recipe_tags(recipe)
    recent = set(recent_tags if recent_tags is not None else recent_accepted_tags(conn))
    categories = recipe_meal_categories(conn, recipe)
    primary_category = primary_meal_category(categories)
    recent_category_sets = recent_categories if recent_categories is not None else recent_accepted_category_sets(conn)
    score = 70.0
    breakdown: dict[str, float] = {}

    cost_per_serving = totals["cost_per_serving_czk"]
    cost_bonus = max(-20.0, min(20.0, 40.0 - cost_per_serving))
    score += cost_bonus
    breakdown["cost"] = round(cost_bonus, 2)

    protein = totals["protein_per_serving_g"]
    if protein >= PROTEIN_TARGET_G:
        protein_bonus = 22.0
    else:
        protein_bonus = -min(35.0, (PROTEIN_TARGET_G - protein) * 1.2)
    score += protein_bonus
    breakdown["protein"] = round(protein_bonus, 2)

    if protein < 20.0:
        score += LOW_PROTEIN_MEAL_PENALTY
        breakdown["low_protein_meal_penalty"] = LOW_PROTEIN_MEAL_PENALTY

    recipe_text = f"{recipe['id']} {recipe['name']} {recipe['raw_source']}".lower()
    if any(_keyword_matches(recipe_text, keyword) for keyword in COMPONENT_KEYWORDS):
        score += COMPONENT_MEAL_PENALTY
        breakdown["component_meal_penalty"] = COMPONENT_MEAL_PENALTY

    repeated_staples = sorted((set(tags) & STAPLE_TAGS) & recent)
    staple_penalty = -15.0 * len(repeated_staples)
    score += staple_penalty
    breakdown["recent_staple_penalty"] = staple_penalty

    repeated_proteins = sorted((set(tags) & PROTEIN_TAGS) & recent)
    protein_repeat_penalty = -8.0 * len(repeated_proteins)
    score += protein_repeat_penalty
    breakdown["recent_protein_penalty"] = protein_repeat_penalty

    repeated_categories: list[str] = []
    category_penalty = 0.0
    category_set = {primary_category}
    for index, recent_category_set in enumerate(recent_category_sets[:RECENT_CATEGORY_LIMIT]):
        overlap = sorted(category_set & recent_category_set)
        if not overlap:
            continue
        penalty = RECENT_CATEGORY_PENALTIES[min(index, len(RECENT_CATEGORY_PENALTIES) - 1)]
        category_penalty += penalty * len(overlap)
        for category in overlap:
            if category not in repeated_categories:
                repeated_categories.append(category)
    score += category_penalty
    breakdown["recent_category_penalty"] = round(category_penalty, 2)

    batch_bonus = 8.0 if 4 <= int(recipe["servings"]) <= 6 else 0.0
    score += batch_bonus
    breakdown["batch_practicality"] = batch_bonus

    estimate_penalty = -2.0 * totals["estimated_lines"]
    score += estimate_penalty
    breakdown["estimate_confidence"] = estimate_penalty

    if recipe["status"] != "approved":
        score -= 100.0
        breakdown["draft_penalty"] = -100.0

    cooked = conn.execute(
        "SELECT count(*) AS c FROM meal_history WHERE recipe_id = ? AND action = 'accepted'",
        (recipe_id,),
    ).fetchone()["c"]
    cooked_penalty = COOKED_COUNT_PENALTY * float(cooked)
    score += cooked_penalty
    breakdown["cooked_count_penalty"] = cooked_penalty

    rejected = conn.execute(
        "SELECT count(*) AS c FROM meal_history WHERE recipe_id = ? AND action = 'rejected'",
        (recipe_id,),
    ).fetchone()["c"]
    rejected_penalty = REJECTED_COUNT_PENALTY * float(rejected)
    score += rejected_penalty
    breakdown["rejected_count_penalty"] = rejected_penalty

    if recipe_id in recent_accepted_recipe_ids(conn):
        recent_recipe_penalty = -25.0
        score += recent_recipe_penalty
        breakdown["recent_recipe_penalty"] = recent_recipe_penalty

    if recipe_id in recent_rejected_recipe_ids(conn):
        score += RECENT_REJECTED_RECIPE_PENALTY
        breakdown["recent_rejected_recipe_penalty"] = RECENT_REJECTED_RECIPE_PENALTY

    return {
        "recipe_id": recipe_id,
        "name": recipe["name"],
        "score": round(score, 2),
        "breakdown": breakdown,
        "totals": totals,
        "tags": tags,
        "meal_categories": categories,
        "primary_category": primary_category,
        "repeated_categories": repeated_categories,
        "repeated_staples": repeated_staples,
        "repeated_proteins": repeated_proteins,
        "cooked_count": int(cooked),
        "rejected_count": int(rejected),
    }


def recommendations(conn: sqlite3.Connection, limit: int = 5) -> list[dict[str, object]]:
    recent = recent_accepted_tags(conn)
    recent_categories = recent_accepted_category_sets(conn)
    rows = conn.execute("SELECT id FROM recipes WHERE status = 'approved'").fetchall()
    scored = [score_recipe(conn, row["id"], recent, recent_categories) for row in rows]
    scored.sort(key=lambda item: float(item["score"]), reverse=True)
    diverse: list[dict[str, object]] = []
    used_categories: set[str] = set()

    def add_items(items: list[dict[str, object]], minimum_score: float | None = None) -> None:
        for item in items:
            if minimum_score is not None and float(item["score"]) < minimum_score:
                continue
            category = str(item["primary_category"])
            if category in used_categories:
                continue
            diverse.append(item)
            used_categories.add(category)
            if len(diverse) >= limit:
                return

    add_items([item for item in scored if not item["repeated_categories"]], MIN_RECOMMENDATION_SCORE)
    if len(diverse) < min(limit, MIN_RECOMMENDATION_COUNT):
        add_items([item for item in scored if item["repeated_categories"]], MIN_RECOMMENDATION_SCORE)
    if not diverse and scored:
        add_items(scored)
    return diverse


def record_decision(conn: sqlite3.Connection, recipe_id: str, action: str, notes: str = "") -> dict[str, object]:
    scored = score_recipe(conn, recipe_id)
    recipe = conn.execute("SELECT servings FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    conn.execute(
        """
        INSERT INTO meal_history (recipe_id, action, servings, score, score_breakdown, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            recipe_id,
            action,
            int(recipe["servings"]) if recipe else 1,
            scored["score"],
            json.dumps(scored["breakdown"]),
            notes,
        ),
    )
    conn.commit()
    return scored
