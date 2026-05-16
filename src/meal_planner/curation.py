from __future__ import annotations

import difflib
import sqlite3


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def similar_recipes(conn: sqlite3.Connection, name: str, threshold: float = 0.72) -> list[dict[str, object]]:
    rows = conn.execute("SELECT id, name FROM recipes").fetchall()
    matches = []
    for row in rows:
        score = similarity(name, row["name"])
        if score >= threshold:
            matches.append({"recipe_id": row["id"], "name": row["name"], "similarity": round(score, 3)})
    return sorted(matches, key=lambda item: float(item["similarity"]), reverse=True)
