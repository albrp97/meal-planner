from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
        return float(match.group(0).replace(",", ".")) if match else 0.0


def _text_or_join(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


@dataclass
class ExtractedIngredient:
    name: str
    quantity: float
    unit: str
    grams: float
    source: str = "llm_estimate"
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedIngredient:
        required = ("name", "quantity", "unit", "grams")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"Missing ingredient fields: {', '.join(missing)}")
        return cls(
            name=str(data["name"]),
            quantity=_float_or_zero(data["quantity"]),
            unit=str(data["unit"]),
            grams=_float_or_zero(data["grams"]),
            source=str(data.get("source", "llm_estimate")),
            notes=str(data.get("notes", "")),
        )


@dataclass
class ExtractedRecipe:
    name: str
    meal_type: str
    servings: int
    ingredients: list[ExtractedIngredient] = field(default_factory=list)
    procedure: str = ""
    decision: str = "needs_review"
    decision_reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedRecipe:
        required = ("name", "meal_type", "servings", "ingredients")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"Missing recipe fields: {', '.join(missing)}")
        return cls(
            name=str(data["name"]),
            meal_type=str(data["meal_type"]),
            servings=int(data["servings"]),
            ingredients=[ExtractedIngredient.from_dict(item) for item in data["ingredients"]],
            procedure=_text_or_join(data.get("procedure", "")),
            decision=str(data.get("decision", "needs_review")),
            decision_reason=str(data.get("decision_reason", "")),
        )
