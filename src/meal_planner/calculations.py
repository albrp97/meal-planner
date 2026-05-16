from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

UNIT_UNITS = {
    "unit",
    "units",
    "unidad",
    "unidades",
    "piece",
    "pieces",
    "leaf",
    "leaves",
    "hoja",
    "hojas",
    "package",
    "paquete",
    "pinch",
    "pinches",
    "pizca",
    "pizcas",
    "optional",
    "to taste",
    "cantidad al gusto",
}
VOLUME_ML_PER_UNIT = {
    "tbsp": 15.0,
    "tablespoon": 15.0,
    "tablespoons": 15.0,
    "cucharada": 15.0,
    "cucharadas": 15.0,
    "tsp": 5.0,
    "teaspoon": 5.0,
    "teaspoons": 5.0,
    "cucharadita": 5.0,
    "cucharaditas": 5.0,
    "dash": 1.0,
    "dashes": 1.0,
}


def latest_price(conn: sqlite3.Connection, ingredient_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM prices WHERE ingredient_id = ? ORDER BY id DESC LIMIT 1",
        (ingredient_id,),
    ).fetchone()


def line_cost(conn: sqlite3.Connection, ingredient_id: str, quantity: float, unit: str, grams: float | None) -> float:
    price = latest_price(conn, ingredient_id)
    if not price:
        return 0.0
    unit = unit.lower()
    if grams is not None and float(grams) > 0 and price["price_per_kg"] is not None:
        return grams / 1000.0 * float(price["price_per_kg"])
    if (
        grams is not None
        and float(grams) > 0
        and unit in ("g", "gram", "grams", "gramos")
        and price["price_per_l"] is not None
    ):
        return grams / 1000.0 * float(price["price_per_l"])
    if unit in ("ml", "milliliter", "milliliters") and price["price_per_l"] is not None:
        return quantity / 1000.0 * float(price["price_per_l"])
    if unit in ("l", "liter", "liters") and price["price_per_l"] is not None:
        return quantity * float(price["price_per_l"])
    if unit in VOLUME_ML_PER_UNIT and price["price_per_l"] is not None:
        return quantity * VOLUME_ML_PER_UNIT[unit] / 1000.0 * float(price["price_per_l"])
    if unit in UNIT_UNITS and price["price_per_unit"] is not None:
        return quantity * float(price["price_per_unit"])
    return 0.0


def recipe_totals(conn: sqlite3.Connection, recipe_id: str) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT ri.*, i.kcal_per_100g, i.protein_per_100g, i.carbs_per_100g, i.fat_per_100g, i.nutrition_source
        FROM recipe_ingredients ri
        JOIN ingredients i ON i.id = ri.ingredient_id
        WHERE ri.recipe_id = ?
        """,
        (recipe_id,),
    ).fetchall()
    recipe = conn.execute("SELECT servings FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    servings = int(recipe["servings"]) if recipe else 1
    totals = {
        "cost_czk": 0.0,
        "kcal": 0.0,
        "protein_g": 0.0,
        "carbs_g": 0.0,
        "fat_g": 0.0,
        "estimated_lines": 0.0,
        "verified_price_lines": 0.0,
        "estimated_price_lines": 0.0,
        "missing_price_lines": 0.0,
    }
    for row in rows:
        grams = row["grams"]
        totals["cost_czk"] += line_cost(conn, row["ingredient_id"], row["quantity"], row["unit"], grams)
        if grams is not None:
            factor = float(grams) / 100.0
            totals["kcal"] += factor * float(row["kcal_per_100g"])
            totals["protein_g"] += factor * float(row["protein_per_100g"])
            totals["carbs_g"] += factor * float(row["carbs_per_100g"])
            totals["fat_g"] += factor * float(row["fat_per_100g"])
        price = latest_price(conn, row["ingredient_id"])
        if price is None:
            totals["missing_price_lines"] += 1
        elif price["source"] == "real_purchase":
            totals["verified_price_lines"] += 1
        else:
            totals["estimated_price_lines"] += 1
        if (price and price["source"] != "real_purchase") or row["nutrition_source"] != "manual_estimate":
            totals["estimated_lines"] += 1
    totals["servings"] = float(servings)
    totals["cost_per_serving_czk"] = totals["cost_czk"] / servings if servings else totals["cost_czk"]
    totals["kcal_per_serving"] = totals["kcal"] / servings if servings else totals["kcal"]
    totals["protein_per_serving_g"] = totals["protein_g"] / servings if servings else totals["protein_g"]
    totals["carbs_per_serving_g"] = totals["carbs_g"] / servings if servings else totals["carbs_g"]
    totals["fat_per_serving_g"] = totals["fat_g"] / servings if servings else totals["fat_g"]
    return totals


def shopping_list(conn: sqlite3.Connection, recipe_ids: Iterable[str]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for recipe_id in recipe_ids:
        rows = conn.execute(
            """
            SELECT ri.*, i.name
            FROM recipe_ingredients ri
            JOIN ingredients i ON i.id = ri.ingredient_id
            WHERE ri.recipe_id = ?
            """,
            (recipe_id,),
        ).fetchall()
        for row in rows:
            key = row["ingredient_id"]
            if key not in grouped:
                grouped[key] = {
                    "ingredient_id": key,
                    "name": row["name"],
                    "grams": 0.0,
                    "units": 0.0,
                    "unit_grams": 0.0,
                    "ml": 0.0,
                    "ml_grams": 0.0,
                    "cost_czk": 0.0,
                    "sources": set(),
                }
            item = grouped[key]
            unit = row["unit"].lower()
            if unit in ("ml", "milliliter", "milliliters"):
                item["ml"] = float(item["ml"]) + float(row["quantity"])
                if row["grams"] is not None:
                    item["ml_grams"] = float(item["ml_grams"]) + float(row["grams"])
            elif row["grams"] is not None and unit not in ("unit", "units", "unidad", "unidades"):
                item["grams"] = float(item["grams"]) + float(row["grams"])
            elif unit in UNIT_UNITS:
                item["units"] = float(item["units"]) + float(row["quantity"])
                if row["grams"] is not None:
                    item["unit_grams"] = float(item["unit_grams"]) + float(row["grams"])
            item["cost_czk"] = float(item["cost_czk"]) + line_cost(
                conn, row["ingredient_id"], row["quantity"], row["unit"], row["grams"]
            )
            price = latest_price(conn, row["ingredient_id"])
            if price:
                item["sources"].add(price["source"])
    out = []
    for item in grouped.values():
        item["sources"] = sorted(item["sources"])
        out.append(item)
    return sorted(out, key=lambda x: str(x["name"]).lower())


def recipe_tags(row: sqlite3.Row) -> list[str]:
    try:
        return list(json.loads(row["tags"]))
    except (TypeError, json.JSONDecodeError):
        return []
