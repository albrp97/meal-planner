from __future__ import annotations

import unittest

from meal_planner.llm_schemas import ExtractedIngredient


class LLMSchemaTests(unittest.TestCase):
    def test_ingredient_quantity_accepts_qualitative_text(self) -> None:
        ingredient = ExtractedIngredient.from_dict(
            {"name": "salt", "quantity": "to taste", "unit": "to taste", "grams": "estimate"}
        )

        self.assertEqual(ingredient.quantity, 0.0)
        self.assertEqual(ingredient.grams, 0.0)

    def test_ingredient_quantity_reads_number_from_text(self) -> None:
        ingredient = ExtractedIngredient.from_dict(
            {"name": "honey", "quantity": "2 cucharadas", "unit": "tablespoons", "grams": "40 g"}
        )

        self.assertEqual(ingredient.quantity, 2.0)
        self.assertEqual(ingredient.grams, 40.0)


if __name__ == "__main__":
    unittest.main()
