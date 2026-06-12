from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meal_planner.calculations import recipe_totals, shopping_list
from meal_planner.db import connect, init_schema
from meal_planner.english import translate_text
from meal_planner.enrichment import enrich_recipes
from meal_planner.extraction import parse_recipe_json
from meal_planner.importers import import_recipes
from meal_planner.recipe_chat import apply_recipe_chat_update, ask_recipe_copilot
from meal_planner.recommender import (
    meal_category_names,
    primary_meal_category,
    recent_accepted_recipe_ids,
    recipe_meal_categories,
    recommendations,
    record_decision,
    score_recipe,
)
from meal_planner.seed_data import (
    DRAFT_FILLER_VERSION,
    RECIPE_QUALITY_VERSION,
    SERIOUS_CURATION_VERSION,
    apply_curated_draft_fillers,
    apply_recipe_quality_curation,
    apply_serious_recipe_curation,
    seed_database,
)
from meal_planner.tui import (
    decode_escape_sequence,
    filter_recipe_rows,
    history_lines,
    history_rows,
    key_hint_lines,
    procedure_steps,
    recent_meal_lines,
    recipe_catalog_rows,
    recipe_ingredient_lines,
    recipe_lines,
    recipe_overview_lines,
    recipe_step_lines,
    strip_ansi,
)
from meal_planner.units import grams_for


class MealPlannerCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "test.sqlite3")
        init_schema(self.conn)
        seed_database(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_local_quantity_assumptions(self) -> None:
        self.assertEqual(grams_for("cebolla-amarilla", 1, "unit"), 80)
        self.assertEqual(grams_for("pimiento-rojo", 0.5, "unit"), 90)
        self.assertEqual(grams_for("arroz-basmati", 0.25, "kg"), 250)

    def test_seed_preserves_real_price_source(self) -> None:
        row = self.conn.execute(
            """
            SELECT p.source, p.price_per_kg
            FROM prices p
            JOIN ingredients i ON i.id = p.ingredient_id
            WHERE i.id = 'pollo-picado'
            """
        ).fetchone()
        self.assertEqual(row["source"], "real_purchase")
        self.assertAlmostEqual(row["price_per_kg"], 159.8)

    def test_water_is_approved_free_price(self) -> None:
        row = self.conn.execute(
            """
            SELECT source, price_per_l
            FROM prices
            WHERE ingredient_id = 'agua'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        self.assertEqual(row["source"], "real_purchase")
        self.assertEqual(row["price_per_l"], 0)

    def test_burrito_totals_are_batch_and_serving_aware(self) -> None:
        totals = recipe_totals(self.conn, "burrito")
        self.assertEqual(int(totals["servings"]), 6)
        self.assertGreater(totals["cost_czk"], 200)
        self.assertAlmostEqual(totals["cost_per_serving_czk"], totals["cost_czk"] / 6)
        self.assertGreater(totals["protein_per_serving_g"], 25)
        self.assertGreater(totals["estimated_price_lines"], 0)
        self.assertGreater(totals["verified_price_lines"], 0)

    def test_shopping_list_aggregates_recipe_lines(self) -> None:
        items = shopping_list(self.conn, ["burrito"])
        by_id = {item["ingredient_id"]: item for item in items}
        self.assertEqual(by_id["wraps"]["units"], 6)
        self.assertGreater(by_id["pollo-picado"]["grams"], 499)

    def test_recommendations_exclude_drafts(self) -> None:
        self.conn.execute("UPDATE recipes SET status = 'draft' WHERE id = 'burrito'")
        self.conn.commit()
        recs = recommendations(self.conn, limit=1000)
        ids = {rec["recipe_id"] for rec in recs}
        self.assertNotIn("burrito", ids)
        self.assertTrue(ids)

    def test_recent_rice_penalty_changes_score(self) -> None:
        baseline = score_recipe(self.conn, "curry-indio", recent_tags=[])
        penalized = score_recipe(self.conn, "curry-indio", recent_tags=["rice", "chicken"])
        self.assertLess(penalized["score"], baseline["score"])

    def test_recent_category_penalty_infers_pasta_from_ingredients(self) -> None:
        self.conn.execute(
            """
            INSERT INTO recipes
            (id, name, status, meal_type, servings, raw_source, procedure, tags, source_type,
             protein_status, decision_status, decision_reason)
            VALUES
            ('test-gricia', 'Test gricia', 'approved', 'lunch_dinner', 4, '', 'Cook pasta sauce.',
             '["youtube", "lunch", "dinner"]', 'test', 'ok', 'approved', '')
            """
        )
        self.conn.execute(
            """
            INSERT INTO recipe_ingredients
            (recipe_id, ingredient_id, display_name, quantity, unit, grams, source, notes)
            VALUES ('test-gricia', 'pasta-espaguetis', 'pasta', 400, 'g', 400, 'test', '')
            """
        )
        self.conn.commit()
        recipe = self.conn.execute("SELECT * FROM recipes WHERE id = 'test-gricia'").fetchone()
        self.assertIn("pasta_lasagna", recipe_meal_categories(self.conn, recipe))

        baseline = score_recipe(self.conn, "test-gricia", recent_tags=[], recent_categories=[])
        record_decision(self.conn, "pasta-carne", "accepted", "test")
        penalized = score_recipe(self.conn, "test-gricia")

        self.assertIn("pasta_lasagna", penalized["repeated_categories"])
        self.assertLess(penalized["score"], baseline["score"] - 30)

    def test_recommendations_only_show_one_item_per_category(self) -> None:
        recs = recommendations(self.conn, limit=20)
        used: set[str] = set()
        for rec in recs:
            category = str(rec["primary_category"])
            self.assertNotIn(category, used)
            used.add(category)

    def test_recommendations_prefer_untried_viable_meals_before_repeats(self) -> None:
        first_id = str(recommendations(self.conn, limit=1)[0]["recipe_id"])
        record_decision(self.conn, first_id, "accepted", "test")

        rec_ids = {str(rec["recipe_id"]) for rec in recommendations(self.conn, limit=6)}

        self.assertNotIn(first_id, rec_ids)

    def test_recommendations_add_stable_daily_discovery_slot(self) -> None:
        first = recommendations(self.conn, limit=6)
        second = recommendations(self.conn, limit=6)

        self.assertEqual(len(first), 6)
        self.assertEqual(first[-1]["recommendation_kind"], "discovery")
        self.assertEqual(second[-1]["recommendation_kind"], "discovery")
        self.assertEqual(first[-1]["recipe_id"], second[-1]["recipe_id"])
        self.assertTrue(all(rec["recommendation_kind"] == "ranked" for rec in first[:-1]))
        self.assertGreaterEqual(first[-1]["totals"]["protein_per_serving_g"], 20)
        self.assertNotIn(first[-1]["primary_category"], {"sides_components", "desserts_sweets"})

    def test_recommendations_surface_low_scored_untried_viable_meal_before_repeats(self) -> None:
        self.conn.execute(
            """
            INSERT INTO ingredients
            (id, name, category, default_unit, tags, nutrition_source, kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g)
            VALUES ('test-lean-protein', 'Test lean protein', 'protein', 'g', '["protein"]',
                    'llm_estimate', 400, 80, 5, 5)
            """
        )
        self.conn.execute(
            """
            INSERT INTO prices (ingredient_id, context, price_czk, package_qty, package_unit, price_per_kg, source)
            VALUES ('test-lean-protein', 'test', 5000, 1, 'kg', 5000, 'llm_estimate')
            """
        )
        self.conn.execute(
            """
            INSERT INTO recipes
            (id, name, status, meal_type, servings, raw_source, procedure, tags, source_type,
             protein_status, decision_status, decision_reason)
            VALUES
            ('test-low-score-chicken', 'Low Score Chicken Bowl', 'approved', 'lunch_dinner', 4,
             'chicken bowl', 'Batch cook: cook the protein and divide into four meals.',
             '["chicken"]', 'test', 'ok', 'approved', '')
            """
        )
        for _ in range(30):
            self.conn.execute(
                """
                INSERT INTO recipe_ingredients
                (recipe_id, ingredient_id, display_name, quantity, unit, grams, source, notes)
                VALUES ('test-low-score-chicken', 'test-lean-protein', 'Test lean protein', 15, 'g', 15, 'test', '')
                """
            )
        self.conn.commit()
        scored = [
            score_recipe(self.conn, row["id"], recent_tags=[], recent_categories=[])
            for row in self.conn.execute("SELECT id FROM recipes WHERE status = 'approved'").fetchall()
        ]
        target = min(
            (
                item
                for item in scored
                if item["totals"]["protein_per_serving_g"] >= 20
                and item["primary_category"] not in {"sides_components", "desserts_sweets"}
            ),
            key=lambda item: item["score"],
        )
        target_id = str(target["recipe_id"])
        self.assertLess(target["score"], 35)
        for row in self.conn.execute("SELECT id FROM recipes WHERE status = 'approved'").fetchall():
            if row["id"] != target_id:
                record_decision(self.conn, row["id"], "accepted", "test")

        rec_ids: list[str] = []
        for _ in range(10):
            rec_ids = [str(rec["recipe_id"]) for rec in recommendations(self.conn, limit=20)]
            if target_id in rec_ids:
                break
            record_decision(self.conn, rec_ids[0], "accepted", "test")

        self.assertIn(target_id, rec_ids)

    def test_recommendations_filter_low_protein_and_component_meals(self) -> None:
        recs = recommendations(self.conn, limit=1000)

        self.assertTrue(recs)
        for rec in recs:
            self.assertGreaterEqual(rec["totals"]["protein_per_serving_g"], 20)
            self.assertNotIn(rec["primary_category"], {"sides_components", "desserts_sweets"})

    def test_cooked_and_rejected_penalties_keep_rotating_recipes(self) -> None:
        baseline = score_recipe(self.conn, "pizza")
        for _ in range(5):
            record_decision(self.conn, "pizza", "accepted", "test")
        cooked = score_recipe(self.conn, "pizza")
        record_decision(self.conn, "pizza", "rejected", "test")
        rejected = score_recipe(self.conn, "pizza")

        self.assertEqual(cooked["breakdown"]["cooked_count_penalty"], -20.0)
        self.assertLess(cooked["score"], baseline["score"] - 15)
        self.assertLess(rejected["score"], cooked["score"])
        self.assertLess(rejected["breakdown"]["recent_rejected_recipe_penalty"], 0)

    def test_recommendations_penalize_last_five_without_forcing_exclusion(self) -> None:
        recent_ids = ["lentejas", "arroz-chino", "burrito", "pasta-carne", "empanada-pollo"]
        for recipe_id in recent_ids:
            record_decision(self.conn, recipe_id, "accepted", "test")
        excluded = recent_accepted_recipe_ids(self.conn)
        rec_ids = {rec["recipe_id"] for rec in recommendations(self.conn, limit=20)}
        self.assertEqual(excluded, set(recent_ids))
        self.assertFalse(set(recent_ids) & rec_ids)
        self.assertLess(score_recipe(self.conn, "burrito")["breakdown"]["recent_recipe_penalty"], 0)
        self.assertNotIn(
            "rice_bowls",
            [category for rec in recommendations(self.conn, limit=20) for category in rec["meal_categories"]],
        )

    def test_recent_meal_lines_show_accepted_history(self) -> None:
        record_decision(self.conn, "lentejas", "accepted", "test")
        record_decision(self.conn, "arroz-chino", "accepted", "test")
        lines = recent_meal_lines(self.conn, limit=5)
        joined = "\n".join(lines)
        self.assertIn("Lentil stew", joined)
        self.assertIn("Chicken fried rice", joined)
        self.assertNotIn("score::", joined)

    def test_seed_display_names_are_english(self) -> None:
        recipe = self.conn.execute("SELECT name FROM recipes WHERE id = 'arroz-chino'").fetchone()
        ingredient = self.conn.execute("SELECT name FROM ingredients WHERE id = 'pimiento-rojo'").fetchone()
        self.assertEqual(recipe["name"], "Chicken fried rice (non-fried method)")
        self.assertEqual(ingredient["name"], "Red bell pepper")

    def test_curated_draft_recipes_are_populated(self) -> None:
        recipe_ids = ["pasta-pollo", "pizza", "pollo-papa-horno", "puchero", "hamburguesa"]
        for recipe_id in recipe_ids:
            with self.subTest(recipe_id=recipe_id):
                row = self.conn.execute(
                    """
                    SELECT r.status, r.servings, length(trim(r.procedure)) AS procedure_len, count(ri.id) AS ingredient_count
                    FROM recipes r
                    LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id
                    WHERE r.id = ?
                    GROUP BY r.id
                    """,
                    (recipe_id,),
                ).fetchone()
                self.assertEqual(row["status"], "approved")
                self.assertGreater(row["servings"], 1)
                self.assertGreater(row["procedure_len"], 50)
                self.assertGreater(row["ingredient_count"], 3)

    def test_recipe_detail_helpers_show_ingredients_and_steps(self) -> None:
        ingredients = "\n".join(recipe_ingredient_lines(self.conn, "pollo-papa-horno"))
        steps = "\n".join(recipe_step_lines(self.conn, "pollo-papa-horno"))
        overview = "\n".join(recipe_overview_lines(self.conn, "pollo-papa-horno"))
        self.assertIn("Chicken", ingredients)
        self.assertIn("✓", ingredients)
        self.assertIn("*", ingredients)
        self.assertIn("price source", overview)
        self.assertIn("calories", overview)
        self.assertIn("macros", overview)
        self.assertIn("C ", overview)
        self.assertIn("F ", overview)
        self.assertIn("Bake", steps)

    def test_non_gram_recipe_amounts_show_gram_equivalent(self) -> None:
        ingredients = strip_ansi("\n".join(recipe_ingredient_lines(self.conn, "pizza", limit=20)))
        self.assertIn("325ml (325g)", ingredients)
        self.assertIn("1unit (180g)", ingredients)
        self.assertIn("Water", ingredients)

    def test_procedure_steps_do_not_split_decimal_grams(self) -> None:
        steps = procedure_steps("Batch prep: mix 4.5 g garlic powder. Batch cook: simmer for 12 minutes.")

        self.assertEqual(steps[0], "Batch prep: mix 4.5 g garlic powder")
        self.assertEqual(steps[1], "Batch cook: simmer for 12 minutes")

    def test_english_cleanup_preserves_cooking_pan_in_procedures(self) -> None:
        text = translate_text(
            "Batch cook: Heat a cast iron bread over medium-high heat. Tilt the bread and baste in a bread."
        )

        self.assertIn("cast iron pan", text)
        self.assertIn("tilt the pan", text)
        self.assertIn("in a pan", text)
        self.assertNotIn("cast iron bread", text)

    def test_recipe_catalog_lines_are_selectable(self) -> None:
        lines = recipe_lines(self.conn, selected=1, limit=4)
        joined = "\n".join(lines)
        self.assertIn("o cycles sort", joined)
        self.assertIn("category", joined)
        self.assertIn("C:", joined)
        self.assertIn(">*", joined)
        self.assertNotIn("approved", strip_ansi(joined))

    def test_recipe_catalog_can_filter_by_typed_search(self) -> None:
        rows = recipe_catalog_rows(self.conn)
        filtered = filter_recipe_rows(rows, "pizza")
        lines = recipe_lines(self.conn, selected=0, limit=5, rows=filtered, query="pizza", total_count=len(rows))
        joined = strip_ansi("\n".join(lines))

        self.assertLess(len(filtered), len(rows))
        self.assertTrue(any(row["id"] == "pizza" for row in filtered))
        self.assertIn("search::pizza", joined)
        self.assertIn("Pizza", joined)

    def test_history_lines_are_selectable_for_recipe_details(self) -> None:
        record_decision(self.conn, "pizza", "accepted", "test")
        rows = history_rows(self.conn)
        lines = history_lines(rows, selected=0, limit=5)
        joined = strip_ansi("\n".join(lines))

        self.assertEqual(rows[0]["recipe_id"], "pizza")
        self.assertIn("Pizza", joined)
        self.assertIn("enter/d opens recipe details", joined)

    def test_recipe_catalog_can_sort_by_category(self) -> None:
        lines = recipe_lines(self.conn, selected=0, limit=8, sort="category")
        joined = strip_ansi("\n".join(lines))
        self.assertIn("sort::category", joined)
        self.assertIn("CAT:", joined)
        self.assertTrue(meal_category_names())
        self.assertEqual(primary_meal_category(["pasta_lasagna"]), "pasta_lasagna")

    def test_recipe_catalog_sort_metric_changes_with_sort(self) -> None:
        protein_lines = strip_ansi("\n".join(recipe_lines(self.conn, selected=0, limit=4, sort="protein")))
        cheap_lines = strip_ansi("\n".join(recipe_lines(self.conn, selected=0, limit=4, sort="cheap")))
        self.assertIn("P:", protein_lines)
        self.assertIn("M:", cheap_lines)

    def test_burrito_steps_are_practical_not_placeholder(self) -> None:
        steps = recipe_step_lines(self.conn, "burrito", limit=20)
        plain_steps = [strip_ansi(line) for line in steps]
        joined = "\n".join(plain_steps)
        self.assertGreaterEqual(len([line for line in plain_steps if line[:1].isdigit()]), 6)
        self.assertIn("exactly six wraps", joined)
        self.assertIn("without frying", joined)

    def test_noodles_have_real_sauce_components(self) -> None:
        ingredient_ids = {
            row["ingredient_id"]
            for row in self.conn.execute(
                "SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id = 'noodles-pollo'"
            )
        }
        steps = "\n".join(recipe_step_lines(self.conn, "noodles-pollo", limit=20))
        self.assertTrue({"salsa-soja", "ajo", "jengibre", "miel", "vinagre"}.issubset(ingredient_ids))
        self.assertIn("Batch prep", steps)
        self.assertIn("soy sauce", steps)

    def test_all_recipes_are_multi_serving_batch_plans(self) -> None:
        rows = self.conn.execute("SELECT id, servings, procedure FROM recipes").fetchall()
        single_serving = [row["id"] for row in rows if int(row["servings"]) <= 1]
        missing_batch_guidance = [row["id"] for row in rows if "Batch " not in row["procedure"]]
        self.assertEqual(single_serving, [])
        self.assertEqual(missing_batch_guidance, [])

    def test_noodles_are_multi_serving_but_individually_cooked(self) -> None:
        recipe = self.conn.execute("SELECT servings, procedure FROM recipes WHERE id = 'noodles-pollo'").fetchone()
        totals = recipe_totals(self.conn, "noodles-pollo")
        self.assertEqual(recipe["servings"], 4)
        self.assertIn("Individual cook", recipe["procedure"])
        self.assertGreater(totals["protein_per_serving_g"], 30)

    def test_curated_draft_migration_replaces_placeholders_and_stale_reviews(self) -> None:
        self.conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = 'pizza'")
        self.conn.execute(
            """
            UPDATE recipes
            SET servings = 1, procedure = 'Draft placeholder; needs recipe.'
            WHERE id = 'pizza'
            """
        )
        self.conn.execute(
            """
            INSERT OR REPLACE INTO recipe_reviews
            (recipe_id, model, procedure, missing_ingredients, suggested_ingredients, adaptation_notes,
             protein_status, serving_notes, decision_status, decision_reason, raw_response)
            VALUES ('pizza', 'test', 'stale placeholder review', '[]', '[]', '', 'unknown', '', 'needs_review', '', '{}')
            """
        )
        self.conn.execute("DELETE FROM settings WHERE key = 'draft_filler_version'")
        self.conn.commit()

        apply_curated_draft_fillers(self.conn)

        row = self.conn.execute(
            """
            SELECT r.status, r.servings, length(trim(r.procedure)) AS procedure_len, count(ri.id) AS ingredient_count
            FROM recipes r
            LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id
            WHERE r.id = 'pizza'
            GROUP BY r.id
            """
        ).fetchone()
        review = self.conn.execute("SELECT 1 FROM recipe_reviews WHERE recipe_id = 'pizza'").fetchone()
        setting = self.conn.execute("SELECT value FROM settings WHERE key = 'draft_filler_version'").fetchone()

        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["servings"], 4)
        self.assertGreater(row["procedure_len"], 50)
        self.assertGreater(row["ingredient_count"], 3)
        self.assertIsNone(review)
        self.assertEqual(setting["value"], DRAFT_FILLER_VERSION)

    def test_serious_curation_migration_adds_missing_sauce_and_clears_stale_review(self) -> None:
        self.conn.execute(
            "DELETE FROM recipe_ingredients WHERE recipe_id = 'noodles-pollo' AND ingredient_id IN ('salsa-soja', 'ajo', 'jengibre', 'miel', 'vinagre')"
        )
        self.conn.execute(
            """
            INSERT OR REPLACE INTO recipe_reviews
            (recipe_id, model, procedure, missing_ingredients, suggested_ingredients, adaptation_notes,
             protein_status, serving_notes, decision_status, decision_reason, raw_response)
            VALUES ('noodles-pollo', 'test', 'stale review without sauce', '[]', '[]', '', 'ok', '', 'approved', '', '{}')
            """
        )
        self.conn.execute("DELETE FROM settings WHERE key = 'serious_curation_version'")
        self.conn.commit()

        apply_serious_recipe_curation(self.conn)

        ingredient_ids = {
            row["ingredient_id"]
            for row in self.conn.execute(
                "SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id = 'noodles-pollo'"
            )
        }
        review = self.conn.execute("SELECT 1 FROM recipe_reviews WHERE recipe_id = 'noodles-pollo'").fetchone()
        setting = self.conn.execute("SELECT value FROM settings WHERE key = 'serious_curation_version'").fetchone()

        self.assertTrue({"salsa-soja", "ajo", "jengibre", "miel", "vinagre"}.issubset(ingredient_ids))
        self.assertIsNone(review)
        self.assertEqual(setting["value"], SERIOUS_CURATION_VERSION)

    def test_pizza_dough_has_explicit_water_rest_temperature_and_time(self) -> None:
        ingredient_ids = {
            row["ingredient_id"]
            for row in self.conn.execute("SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id = 'pizza'")
        }
        procedure = self.conn.execute("SELECT procedure FROM recipes WHERE id = 'pizza'").fetchone()["procedure"]

        self.assertTrue({"agua", "levadura-seca", "azucar", "sal"}.issubset(ingredient_ids))
        self.assertIn("325ml warm water", procedure)
        self.assertIn("rise 60-90 minutes", procedure)
        self.assertIn("240C", procedure)
        self.assertIn("12-16 minutes", procedure)

    def test_recipe_quality_curation_normalizes_list_procedures_and_adds_temperature(self) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO recipes
            (id, name, status, meal_type, servings, raw_source, procedure, tags, source_type, protein_status, decision_status)
            VALUES ('baguette-fake-pizza', 'Baguette fake pizza', 'approved', 'lunch_dinner', 4, '',
                    '["Batch cook: Toast in oven.", "Individual cook: serve."]', '[]', 'youtube', 'ok', 'approved')
            """
        )
        self.conn.execute("DELETE FROM settings WHERE key = 'recipe_quality_version'")
        self.conn.commit()

        apply_recipe_quality_curation(self.conn)

        row = self.conn.execute("SELECT procedure FROM recipes WHERE id = 'baguette-fake-pizza'").fetchone()
        setting = self.conn.execute("SELECT value FROM settings WHERE key = 'recipe_quality_version'").fetchone()

        self.assertNotIn("['", row["procedure"])
        self.assertIn("220C", row["procedure"])
        self.assertIn("7-9 minutes", row["procedure"])
        self.assertEqual(setting["value"], RECIPE_QUALITY_VERSION)

    def test_arrow_escape_sequences_decode(self) -> None:
        self.assertEqual(decode_escape_sequence("[B"), "down")
        self.assertEqual(decode_escape_sequence("OB"), "down")
        self.assertEqual(decode_escape_sequence("[1;2B"), "down")
        self.assertEqual(decode_escape_sequence("[A"), "up")
        self.assertEqual(decode_escape_sequence("OA"), "up")
        self.assertEqual(decode_escape_sequence("[1;2A"), "up")

    def test_recipe_json_import(self) -> None:
        path = Path(self.tmp.name) / "recipes.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "id": "test-pollo",
                        "name": "Test Pollo",
                        "status": "draft",
                        "servings": 2,
                        "ingredients": [{"ingredient_id": "pollo", "quantity": 200, "unit": "g"}],
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.assertEqual(import_recipes(self.conn, path), 1)
        row = self.conn.execute("SELECT * FROM recipes WHERE id = 'test-pollo'").fetchone()
        self.assertEqual(row["name"], "Test Pollo")

    def test_extraction_json_validation(self) -> None:
        recipes = parse_recipe_json(
            json.dumps(
                [
                    {
                        "name": "Pollo simple",
                        "meal_type": "lunch_dinner",
                        "servings": 2,
                        "ingredients": [{"name": "pollo", "quantity": 200, "unit": "g", "grams": 200}],
                    }
                ]
            )
        )
        self.assertEqual(recipes[0].ingredients[0].grams, 200)

    def test_extraction_joins_list_procedure(self) -> None:
        recipes = parse_recipe_json(
            json.dumps(
                [
                    {
                        "name": "Chicken meal",
                        "meal_type": "lunch_dinner",
                        "servings": 4,
                        "ingredients": [{"name": "chicken", "quantity": 500, "unit": "g", "grams": 500}],
                        "procedure": ["Batch cook: bake at 200C for 20 minutes.", "Individual cook: reheat."],
                    }
                ]
            )
        )

        self.assertEqual(recipes[0].procedure, "Batch cook: bake at 200C for 20 minutes. Individual cook: reheat.")

    def test_recipe_enrichment_persists_review(self) -> None:
        def fake_ask(_prompt: str, _context: str) -> str:
            return json.dumps(
                {
                    "procedure": "Cook the chicken and rice, then portion into two meals.",
                    "missing_ingredients": [],
                    "suggested_ingredients": ["Add vegetables if available."],
                    "adaptation_notes": "No frying required.",
                    "protein_status": "good",
                    "serving_notes": "Two practical servings.",
                    "decision_status": "approved",
                    "decision_reason": "Complete enough for the planner.",
                }
            )

        results = enrich_recipes(self.conn, recipe_ids=["curry-indio"], ask=fake_ask)
        self.assertEqual(results[0]["decision_status"], "approved")
        row = self.conn.execute("SELECT * FROM recipe_reviews WHERE recipe_id = 'curry-indio'").fetchone()
        self.assertIn("portion", row["procedure"])

    def test_recipe_chat_answers_without_modifying_recipe(self) -> None:
        before = recipe_totals(self.conn, "curry-indio")

        def fake_ask(_prompt: str, _context: str, model: str = "") -> str:
            self.assertEqual(model, "gpt-5.4")
            return json.dumps({"message": "Use a wider pan so the chicken browns faster.", "update": None})

        result = ask_recipe_copilot(self.conn, "curry-indio", "How can I cook this faster?", ask=fake_ask)
        after = recipe_totals(self.conn, "curry-indio")

        self.assertFalse(result.updated)
        self.assertIn("wider pan", result.message)
        self.assertEqual(before["cost_czk"], after["cost_czk"])

    def test_recipe_chat_update_recalculates_totals_and_clears_stale_review(self) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO recipe_reviews
            (recipe_id, model, procedure, missing_ingredients, suggested_ingredients, adaptation_notes,
             protein_status, serving_notes, decision_status, decision_reason, raw_response)
            VALUES ('curry-indio', 'test', 'stale review', '[]', '[]', '', 'ok', '', 'approved', '', '{}')
            """
        )
        self.conn.commit()
        before = recipe_totals(self.conn, "curry-indio")

        def fake_ask(_prompt: str, _context: str, model: str = "") -> str:
            self.assertEqual(model, "gpt-5.4")
            return json.dumps(
                {
                    "message": "Scaled the curry to six higher-protein meals.",
                    "update": {
                        "servings": 6,
                        "procedure": (
                            "Batch cook: simmer 900g chicken with curry sauce for 25 minutes. "
                            "Batch plan: portion into six meals."
                        ),
                        "protein_status": "good",
                        "decision_status": "approved",
                        "decision_reason": "Updated from Copilot detail chat.",
                        "ingredients": [
                            {
                                "ingredient_id": "pollo",
                                "display_name": "Chicken",
                                "quantity": 900,
                                "unit": "g",
                                "grams": 900,
                            }
                        ],
                    },
                }
            )

        result = ask_recipe_copilot(self.conn, "curry-indio", "Make this six meals with more chicken.", ask=fake_ask)
        after = recipe_totals(self.conn, "curry-indio")
        recipe = self.conn.execute("SELECT servings, procedure FROM recipes WHERE id = 'curry-indio'").fetchone()
        review = self.conn.execute("SELECT 1 FROM recipe_reviews WHERE recipe_id = 'curry-indio'").fetchone()

        self.assertTrue(result.updated)
        self.assertIn("Recalculated", result.message)
        self.assertEqual(recipe["servings"], 6)
        self.assertIn("900g chicken", recipe["procedure"])
        self.assertNotEqual(before["cost_czk"], after["cost_czk"])
        self.assertIsNone(review)

    def test_recipe_chat_update_name_tags_and_default_ingredient_fields(self) -> None:
        changed = apply_recipe_chat_update(
            self.conn,
            "curry-indio",
            {
                "name": "Chicken Curry Meal Prep",
                "tags": [" curry ", "", "dinner", "meal-prep"],
                "ingredients": [{"ingredient_id": "pollo-picado", "quantity": 0.5, "unit": "kg"}],
            },
        )
        recipe = self.conn.execute("SELECT name, tags FROM recipes WHERE id = 'curry-indio'").fetchone()
        line = self.conn.execute(
            """
            SELECT display_name, grams, source, notes
            FROM recipe_ingredients
            WHERE recipe_id = 'curry-indio'
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()

        self.assertTrue(changed)
        self.assertEqual(recipe["name"], "Chicken Curry Meal Prep")
        self.assertEqual(json.loads(recipe["tags"]), ["curry", "dinner", "meal-prep"])
        self.assertEqual(line["display_name"], "Ground chicken")
        self.assertEqual(line["grams"], 500)
        self.assertEqual(line["source"], "copilot_chat")
        self.assertEqual(line["notes"], "")

    def test_recipe_chat_update_rejects_invalid_fields(self) -> None:
        invalid_updates = (
            {"tags": "not-a-list"},
            {"servings": 1},
            {"protein_status": "very_high"},
            {"decision_status": "ship_it"},
        )

        for update in invalid_updates:
            with self.subTest(update=update):
                with self.assertRaises(ValueError):
                    apply_recipe_chat_update(self.conn, "curry-indio", update)

    def test_recipe_chat_update_rejects_invalid_ingredient_payloads(self) -> None:
        invalid_updates = (
            {"ingredients": []},
            {"ingredients": ["bad-line"]},
            {"ingredients": [{"ingredient_id": "missing", "quantity": 1, "unit": "g"}]},
            {"ingredients": [{"ingredient_id": "pollo", "quantity": 0, "unit": "g"}]},
        )

        for update in invalid_updates:
            with self.subTest(update=update):
                with self.assertRaises(ValueError):
                    apply_recipe_chat_update(self.conn, "curry-indio", update)

    def test_recipe_chat_update_rejects_invalid_target_or_noop(self) -> None:
        self.assertFalse(apply_recipe_chat_update(self.conn, "curry-indio", {}))

        with self.assertRaises(ValueError):
            apply_recipe_chat_update(self.conn, "curry-indio", None)

        with self.assertRaises(LookupError):
            apply_recipe_chat_update(self.conn, "missing-recipe", {})

    def test_recipe_chat_requires_json_object_and_message(self) -> None:
        def fake_list_response(_prompt: str, _context: str, model: str = "") -> str:
            self.assertEqual(model, "claude-sonnet-4.6")
            return "```json\n[]\n```"

        def fake_missing_message(_prompt: str, _context: str, model: str = "") -> str:
            self.assertEqual(model, "claude-sonnet-4.6")
            return '```json\n{"update": null}\n```'

        with self.assertRaises(ValueError):
            ask_recipe_copilot(
                self.conn,
                "curry-indio",
                "Answer in JSON.",
                ask=fake_list_response,
                model="claude-sonnet-4.6",
            )

        with self.assertRaises(ValueError):
            ask_recipe_copilot(
                self.conn,
                "curry-indio",
                "Answer in JSON.",
                ask=fake_missing_message,
                model="claude-sonnet-4.6",
            )

    def test_header_controls_wrap_and_show_detail_copilot_action(self) -> None:
        lines = [strip_ansi(line) for line in key_hint_lines("detail")]

        self.assertGreaterEqual(len(lines), 2)
        self.assertIn("m ask/modify with Copilot", lines[1])
        self.assertTrue(all(len(line) < 100 for line in lines))


if __name__ == "__main__":
    unittest.main()
