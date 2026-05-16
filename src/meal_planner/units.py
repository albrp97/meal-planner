from __future__ import annotations

UNIT_GRAMS = {
    "cebolla-amarilla": 80,
    "cebolla-roja": 80,
    "pimiento-rojo": 180,
    "tomate-rama": 120,
    "zanahoria": 70,
    "patata": 160,
    "aguacate": 150,
    "pepino": 300,
    "huevos": 60,
    "limon": 90,
    "chorizo": 200,
    "wraps": 60,
    "pan-naan": 70,
    "avecrem": 10,
    "especias": 5,
    "sazonador-burrito": 30,
    "atun": 160,
}


def grams_for(ingredient_id: str, quantity: float, unit: str) -> float | None:
    unit = unit.lower()
    if unit in ("g", "gram", "grams", "gramos"):
        return quantity
    if unit in ("kg", "kilo", "kilos"):
        return quantity * 1000
    if unit in ("ml", "milliliter", "milliliters"):
        return quantity
    if unit in ("l", "liter", "liters", "litro", "litros"):
        return quantity * 1000
    if unit in ("unit", "units", "unidad", "unidades"):
        grams = UNIT_GRAMS.get(ingredient_id)
        return grams * quantity if grams else None
    return None
