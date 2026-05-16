from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .units import grams_for


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def import_prices(conn: sqlite3.Connection, path: Path, context: str = "manual import") -> int:
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError("Price import must be a JSON list.")
    imported = 0
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each price row must be an object.")
        ingredient_id = str(item["ingredient_id"])
        exists = conn.execute("SELECT 1 FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()
        if not exists:
            raise ValueError(f"Unknown ingredient_id in price import: {ingredient_id}")
        conn.execute(
            """
            INSERT INTO prices
            (ingredient_id, context, price_czk, package_qty, package_unit, price_per_kg, price_per_l, price_per_unit, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ingredient_id,
                str(item.get("context", context)),
                float(item["price_czk"]),
                item.get("package_qty"),
                item.get("package_unit"),
                item.get("price_per_kg"),
                item.get("price_per_l"),
                item.get("price_per_unit"),
                str(item.get("source", "manual_estimate")),
                str(item.get("notes", "")),
            ),
        )
        imported += 1
    conn.commit()
    return imported


def import_recipes(conn: sqlite3.Connection, path: Path) -> int:
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError("Recipe import must be a JSON list.")
    imported = 0
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each recipe row must be an object.")
        recipe_id = str(item["id"])
        ingredients = item.get("ingredients", [])
        if not isinstance(ingredients, list):
            raise ValueError(f"Recipe {recipe_id} ingredients must be a list.")
        conn.execute(
            """
            INSERT OR REPLACE INTO recipes
            (id, name, status, meal_type, servings, raw_source, procedure, tags, source_type, protein_status, decision_status, decision_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recipe_id,
                str(item["name"]),
                str(item.get("status", "draft")),
                str(item.get("meal_type", "lunch_dinner")),
                int(item.get("servings", 1)),
                str(item.get("raw_source", "")),
                str(item.get("procedure", "")),
                json.dumps(item.get("tags", [])),
                str(item.get("source_type", "manual_import")),
                str(item.get("protein_status", "unknown")),
                str(item.get("decision_status", "needs_review")),
                str(item.get("decision_reason", "")),
            ),
        )
        conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
        for line in ingredients:
            ingredient_id = str(line["ingredient_id"])
            exists = conn.execute("SELECT 1 FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()
            if not exists:
                raise ValueError(f"Unknown ingredient_id in recipe {recipe_id}: {ingredient_id}")
            quantity = float(line["quantity"])
            unit = str(line.get("unit", "g"))
            grams = line.get("grams")
            if grams is None:
                grams = grams_for(ingredient_id, quantity, unit)
            conn.execute(
                """
                INSERT INTO recipe_ingredients
                (recipe_id, ingredient_id, display_name, quantity, unit, grams, source, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recipe_id,
                    ingredient_id,
                    str(line.get("display_name", ingredient_id)),
                    quantity,
                    unit,
                    grams,
                    str(line.get("source", "manual_import")),
                    str(line.get("notes", "")),
                ),
            )
        imported += 1
    conn.commit()
    return imported
