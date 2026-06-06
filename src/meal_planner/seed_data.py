from __future__ import annotations

import ast
import json
import sqlite3
from collections.abc import Iterable

from .units import grams_for

SEED_VERSION = "2026-05-14-mvp-1"
PRICE_CONTEXT = "Lidl Prague 2026"
DRAFT_FILLER_VERSION = "2026-05-15-curated-approved-1"
SERIOUS_CURATION_VERSION = "2026-05-15-explicit-recipe-methods-2"
RECIPE_QUALITY_VERSION = "2026-06-06-english-steak-potato-1"
CURATED_RECIPE_IDS = {"pasta-pollo", "pizza", "pollo-papa-horno", "puchero", "hamburguesa"}

PROCEDURE_FIXES: dict[str, str] = {
    "baguette-fake-pizza": (
        "Batch prep: split the baguettes lengthwise, portion the sauce and toppings, and preheat the oven to 220C. "
        "Batch cook: toast the baguette halves with butter for 4-5 minutes, then spread with tomato sauce and top with mozzarella, Parmesan, and pepperoni if using. "
        "Bake at 220C for 7-9 minutes until the cheese is melted and golden. "
        "Individual cook: slice and serve immediately with a drizzle of olive oil and basil. Batch plan: each baguette yields 2 servings, for 4 total meals."
    ),
    "chilaquiles-verdes-con-totopos-caseros": (
        "Batch cook: make the salsa verde first. Simmer tomatillos, jalapeños, onion, and garlic in water for 5 minutes, then blend with some cooking liquid, cilantro, lime juice, and salt. Chill it. "
        "Batch prep: cut tortillas into quarters and prepare the toppings: sliced red onion, diced tomato, sliced avocado, crumbled cheese, crema, cilantro, and lime. "
        "Batch cook: make all totopos for the 4 servings at once. For the no-fried version, coat tortilla pieces lightly with oil and bake at 200C for 10-14 minutes, turning once, until crisp. "
        "Individual cook: for each meal, warm one salsa portion for 2-3 minutes, fold in one totopo portion only until coated, then top with fresh egg, avocado, red onion, tomato, crema, cotija, cilantro, and lime."
    ),
    "fattush-fattoush": (
        "Batch prep: make the vinaigrette by mixing sumac with hot water and resting 15 minutes, then blending with olive oil, lemon zest, garlic, lemon juice, white vinegar, pomegranate molasses, salt, and pepper. Chill the dressing. "
        "Batch prep: wash and chop cucumber, tomatoes, radishes, spring onions, parsley, mint, and romaine lettuce. "
        "Batch cook: for a lighter non-fried version, cut pita breads into squares, coat with a little oil, and bake at 190C for 8-10 minutes until crisp; season lightly with salt and pepper. "
        "Batch assemble: keep dressing, vegetables, and pita chips separate. Individual cook: toss one salad portion with dressing just before eating and top with pita chips, pomegranate arils, and mint."
    ),
    "panini-italianos-con-schiacciata-casera": (
        "Batch prep: make the biga by mixing 110g strong flour with 50ml warm water and 0.5g fresh yeast. Cover loosely and ferment 12-24 hours at room temperature. "
        "Batch cook: make the schiacciata dough with 550g flour, 15g salt, 425ml water, the biga, 10g fresh yeast, and 25g honey. Knead until smooth and elastic. "
        "Batch cook: ferment 1.5 hours, spread on an oiled tray, brush with olive oil, and proof 30-45 minutes more. Bake at 240C for about 20 minutes, then finish under the grill for 3-5 minutes if the top needs more color. Brush with olive oil after baking. "
        "Batch prep: toast 200g pistachios in a dry pan over medium heat for 4-6 minutes and blend into cream. Make pecorino cream by melting 10g butter, cooking 10g flour for 1 minute, then whisking in 150ml hot milk and 60g pecorino. "
        "Batch plan: cut the schiacciata into 4 portions and keep fillings separate. Individual cook: assemble each panino just before eating so the bread stays good."
    ),
    "salsa-gravy": (
        "Batch cook: preheat the oven to 220C. Roast the chicken carcasses with vegetables, tomato paste, and olive oil for 35-45 minutes until deeply browned. "
        "Batch cook: transfer to a pot, add water, thyme, and bay leaves, simmer gently for 2 hours, then strain and reduce to about 1.5L stock. "
        "Batch cook: make the gravy by cooking butter and flour into a roux for 2-3 minutes, then gradually whisk in the reduced stock until smooth. "
        "Batch prep: season with salt and black pepper. Batch plan: cool and refrigerate; reheat portions gently before serving and adjust texture with a little stock or water if needed."
    ),
    "entrecot-a-la-mantequilla-con-ajo-y-romero": (
        "Batch prep: Pat the entrecots dry with kitchen paper. Season both sides generously with salt and black pepper. "
        "If time allows, rest uncovered in the fridge for up to 1 hour before cooking. "
        "Batch prep: Peel and cut the potatoes into wedges. Toss with a little olive oil, salt, and pepper. "
        "Batch cook: Roast the potato wedges at 200 C for 35 to 40 minutes, turning once halfway, until golden and crispy. Keep warm. "
        "Individual cook: Place a heavy skillet over very high heat. Sear the entrecot 2 minutes on the first side and 1 minute on the second until a deep brown crust forms. "
        "Reduce heat to medium-low. Add the butter, garlic cloves, and rosemary sprigs. Baste the meat continuously with the melted butter for 1 to 2 minutes to your preferred doneness. "
        "Individual cook: Remove to a plate, tent with aluminium foil, and rest for 10 minutes. Slice against the grain, spoon the warm garlic butter over the top, and finish with flaky salt. "
        "Serve with the roasted potato wedges."
    ),
    "steak-with-pickles": (
        "Batch prep: Pat the steak dry, season both sides with salt and black pepper, and let it sit at room temperature for 20 minutes. "
        "Batch prep: Peel and cut the potatoes into 2 cm cubes. Toss with the olive oil, salt, and pepper. "
        "Batch cook: Roast the potatoes at 200 C for 30 to 35 minutes, turning once, until golden and tender. "
        "Batch cook: Heat a dry skillet over medium-high heat for 2 minutes until very hot. Add a drizzle of oil and sear the steak for 3 to 5 minutes per side depending on thickness. "
        "For medium-rare, aim for an internal temperature of 52 to 54 C before resting. "
        "Batch cook: Transfer the steak to a plate and rest for 10 minutes. Batch prep: Portion the pickles into 4 side servings while the steak rests. "
        "Individual cook: Slice the steak against the grain just before serving and plate with the roasted potatoes and pickles."
    ),
}

RECIPE_FIELD_FIXES: dict[str, dict[str, object]] = {
    "entrecot-a-la-mantequilla-con-ajo-y-romero": {
        "name": "Pan-Seared Entrecot with Garlic and Rosemary Butter",
        "tags": ["youtube", "lunch", "dinner", "red_meat"],
        "decision_reason": (
            "Main pan-sear technique, not deep-fried; adapts well to a batch-friendly dinner. "
            "High protein, suitable for fitness. Served with roasted potato wedges for a balanced meal."
        ),
    },
    "steak-with-pickles": {
        "tags": ["youtube", "lunch", "dinner", "red_meat"],
        "decision_reason": (
            "Pan-seared steak dinner; not deep-fried. Expanded into a practical 4-serving batch plan. "
            "Served with roasted potatoes for balanced carbs."
        ),
    },
}

RECIPE_INGREDIENT_ADDITIONS: list[dict[str, object]] = [
    {
        "recipe_id": "entrecot-a-la-mantequilla-con-ajo-y-romero",
        "ingredient_id": "patata",
        "display_name": "Potato",
        "quantity": 800.0,
        "unit": "g",
        "grams": 800.0,
        "source": "manual_curation",
        "notes": "Roasted wedges served as carb side.",
    },
    {
        "recipe_id": "steak-with-pickles",
        "ingredient_id": "patata",
        "display_name": "Potato",
        "quantity": 800.0,
        "unit": "g",
        "grams": 800.0,
        "source": "manual_curation",
        "notes": "Roasted cubes served as carb side.",
    },
]


def ingredient(
    ingredient_id: str,
    name: str,
    category: str,
    tags: Iterable[str],
    kcal: float,
    protein: float,
    carbs: float,
    fat: float,
    nutrition_source: str = "manual_estimate",
    default_unit: str = "g",
    notes: str = "",
    aliases: Iterable[str] = (),
) -> dict[str, object]:
    return {
        "id": ingredient_id,
        "name": name,
        "category": category,
        "default_unit": default_unit,
        "tags": list(tags),
        "kcal": kcal,
        "protein": protein,
        "carbs": carbs,
        "fat": fat,
        "nutrition_source": nutrition_source,
        "notes": notes,
        "aliases": list(aliases),
    }


INGREDIENTS: list[dict[str, object]] = [
    ingredient(
        "ternera", "Ternera", "meat", ["protein", "red_meat"], 190, 21, 0, 12, aliases=["Maso z Farmy Rump", "beef"]
    ),
    ingredient(
        "pollo",
        "Pollo filetes de muslo",
        "meat",
        ["protein", "chicken"],
        180,
        18,
        0,
        11,
        aliases=["chicken", "filetes de muslo"],
    ),
    ingredient("pollo-picado", "Pollo picado", "meat", ["protein", "chicken"], 165, 19, 0, 9, aliases=["pollo picado"]),
    ingredient(
        "cerdo", "Cerdo cuello/krkovice", "meat", ["protein", "pork"], 240, 17, 0, 19, aliases=["krkovice", "pork"]
    ),
    ingredient(
        "carne-picada-mixta",
        "Carne picada mixta",
        "meat",
        ["protein", "red_meat"],
        250,
        18,
        0,
        20,
        aliases=["carne picada", "mixed mince"],
    ),
    ingredient(
        "chorizo",
        "Chorizo / Uherská",
        "meat",
        ["protein", "processed_meat"],
        455,
        24,
        2,
        38,
        default_unit="unit",
        aliases=["uherská"],
    ),
    ingredient(
        "queso-rallado", "Queso rallado", "dairy", ["protein", "dairy"], 380, 25, 2, 30, aliases=["grated cheese"]
    ),
    ingredient(
        "huevos",
        "Huevos L",
        "protein",
        ["protein", "egg"],
        143,
        13,
        1,
        10,
        default_unit="unit",
        aliases=["eggs", "huevos talla l"],
    ),
    ingredient("tomates-cherry", "Tomates cherry", "vegetable", ["vegetable"], 18, 1, 4, 0),
    ingredient(
        "pimiento-rojo",
        "Pimiento rojo",
        "vegetable",
        ["vegetable"],
        31,
        1,
        6,
        0,
        default_unit="unit",
        aliases=["pimiento", "pepper"],
    ),
    ingredient(
        "tomate-rama",
        "Tomate en rama",
        "vegetable",
        ["vegetable"],
        18,
        1,
        4,
        0,
        default_unit="unit",
        aliases=["tomate", "tomato"],
    ),
    ingredient(
        "cebolla-roja", "Cebolla roja", "vegetable", ["vegetable", "aromatic"], 40, 1, 9, 0, default_unit="unit"
    ),
    ingredient(
        "cebolla-amarilla",
        "Cebolla amarilla",
        "vegetable",
        ["vegetable", "aromatic"],
        40,
        1,
        9,
        0,
        default_unit="unit",
        aliases=["cebolla", "onion"],
    ),
    ingredient(
        "zanahoria", "Zanahoria", "vegetable", ["vegetable"], 41, 1, 10, 0, default_unit="unit", aliases=["carrot"]
    ),
    ingredient("patata", "Patata", "carb", ["staple", "potato"], 77, 2, 17, 0, default_unit="unit", aliases=["potato"]),
    ingredient("limon", "Limón", "fruit", ["fruit", "acid"], 29, 1, 9, 0, default_unit="unit"),
    ingredient("platano", "Plátano", "fruit", ["fruit"], 89, 1, 23, 0),
    ingredient(
        "aguacate", "Aguacate", "fruit", ["fat", "fruit"], 160, 2, 9, 15, default_unit="unit", aliases=["avocado"]
    ),
    ingredient("pepino", "Pepino", "vegetable", ["vegetable"], 15, 1, 4, 0, default_unit="unit"),
    ingredient(
        "yogurt",
        "Yogurt blanco 3.9%",
        "dairy",
        ["protein", "dairy"],
        68,
        3.5,
        5,
        3.9,
        aliases=["yogur", "yogurt blanco"],
    ),
    ingredient(
        "aceite-oliva",
        "Aceite de oliva extra virgen",
        "pantry",
        ["fat"],
        884,
        0,
        0,
        100,
        default_unit="ml",
        aliases=["olive oil"],
    ),
    ingredient(
        "arroz-basmati", "Arroz basmati", "pantry", ["staple", "rice"], 365, 7, 80, 1, aliases=["arroz", "rice"]
    ),
    ingredient(
        "harina", "Harina de trigo fina", "pantry", ["staple", "flour"], 364, 10, 76, 1, aliases=["harina hladká"]
    ),
    ingredient("avena", "Copos de avena", "pantry", ["staple", "oats"], 389, 17, 66, 7),
    ingredient(
        "pasta-espaguetis",
        "Pasta espaguetis",
        "pantry",
        ["staple", "pasta"],
        360,
        12,
        72,
        2,
        aliases=["pasta", "espaguetis"],
    ),
    ingredient(
        "tomate-triturado",
        "Tomate triturado / salsa",
        "pantry",
        ["sauce", "vegetable"],
        32,
        1.5,
        6,
        0,
        aliases=["tomate frito", "salsa de tomate"],
    ),
    ingredient(
        "judias", "Judías negras/rojas", "pantry", ["protein", "legume"], 110, 7, 16, 1, aliases=["beans", "judías"]
    ),
    ingredient(
        "wraps",
        "Tortitas / wraps",
        "pantry",
        ["staple", "wrap"],
        310,
        8,
        52,
        8,
        default_unit="unit",
        aliases=["tortitas"],
    ),
    ingredient(
        "cerveza", "Cerveza Staropramen", "pantry", ["alcohol"], 43, 0.4, 3.6, 0, default_unit="ml", aliases=["beer"]
    ),
    ingredient("leche", "Leche UHT", "dairy", ["dairy"], 47, 3.3, 5, 1.5, default_unit="ml"),
    ingredient("arandanos-secos", "Arándanos secos", "pantry", ["dried_fruit"], 325, 0, 83, 1),
    ingredient("pasas", "Pasas jumbo", "pantry", ["dried_fruit"], 299, 3, 79, 0),
    ingredient(
        "hojaldre",
        "Masa de hojaldre",
        "pantry",
        ["staple", "pastry"],
        558,
        7,
        45,
        38,
        aliases=["milhojas", "masa empanada"],
    ),
    ingredient("nata", "Nata para cocinar", "dairy", ["dairy", "fat"], 190, 3, 4, 18, aliases=["cream"]),
    ingredient("champinon", "Champiñones", "vegetable", ["vegetable"], 22, 3, 3, 0, aliases=["champiñon", "mushrooms"]),
    ingredient(
        "atun", "Atún en lata", "protein", ["protein", "fish"], 130, 28, 0, 2, default_unit="unit", aliases=["tuna"]
    ),
    ingredient("noodles", "Noodles", "pantry", ["staple", "noodles"], 360, 10, 72, 3),
    ingredient("col", "Col", "vegetable", ["vegetable"], 25, 1, 6, 0, aliases=["cabbage"]),
    ingredient("higados", "Hígados", "meat", ["protein", "organ_meat"], 135, 20, 0, 5, aliases=["livers"]),
    ingredient("lentejas", "Lentejas", "pantry", ["protein", "legume"], 352, 25, 63, 1, aliases=["lentils"]),
    ingredient("pan-naan", "Pan naan", "pantry", ["staple", "bread"], 300, 9, 52, 7, aliases=["naan"]),
    ingredient("golden-curry", "Golden curry", "pantry", ["sauce", "spice"], 500, 6, 45, 32),
    ingredient("avecrem", "Avecrem", "pantry", ["seasoning"], 180, 12, 20, 6),
    ingredient("miel", "Miel", "pantry", ["sweetener"], 304, 0, 82, 0),
    ingredient("especias", "Especias", "pantry", ["spice"], 250, 10, 40, 8),
    ingredient("sazonador-burrito", "Sazonador burrito", "pantry", ["spice"], 250, 8, 40, 6),
    ingredient(
        "salsa-soja",
        "Salsa de soja",
        "pantry",
        ["sauce", "seasoning"],
        53,
        8,
        5,
        0,
        default_unit="ml",
        aliases=["soy sauce", "soja"],
    ),
    ingredient("ajo", "Ajo", "vegetable", ["aromatic"], 149, 6, 33, 1, aliases=["garlic"]),
    ingredient("jengibre", "Jengibre", "vegetable", ["aromatic"], 80, 2, 18, 1, aliases=["ginger"]),
    ingredient(
        "vinagre",
        "Vinagre",
        "pantry",
        ["acid", "seasoning"],
        18,
        0,
        0,
        0,
        default_unit="ml",
        aliases=["vinegar"],
    ),
    ingredient("agua", "Agua", "pantry", [], 0, 0, 0, 0, default_unit="ml", aliases=["water"]),
    ingredient("levadura-seca", "Levadura seca", "pantry", ["baking"], 325, 40, 41, 8, aliases=["dry yeast"]),
    ingredient("azucar", "Azúcar blanco", "pantry", ["sweetener"], 387, 0, 100, 0, aliases=["sugar"]),
    ingredient(
        "polvo-hornear",
        "Polvo de hornear",
        "pantry",
        ["baking"],
        53,
        0,
        28,
        0,
        aliases=["baking powder", "kypřicí prášek"],
    ),
    ingredient("mantequilla", "Mantequilla", "dairy", ["fat", "dairy"], 717, 1, 0, 81, aliases=["butter"]),
    ingredient("perejil", "Perejil fresco", "vegetable", ["herb"], 36, 3, 6, 1, aliases=["parsley"]),
    ingredient("comino", "Comino molido", "pantry", ["spice"], 375, 18, 44, 22, aliases=["cumin"]),
    ingredient("pimenton", "Pimentón", "pantry", ["spice"], 282, 14, 54, 13, aliases=["paprika"]),
    ingredient("oregano", "Orégano", "pantry", ["spice"], 265, 9, 69, 4, aliases=["oregano"]),
    ingredient("sal", "Sal", "pantry", ["seasoning"], 0, 0, 0, 0, aliases=["salt"]),
    ingredient("pimienta", "Pimienta negra", "pantry", ["spice"], 251, 10, 64, 3, aliases=["black pepper"]),
]


PRICES: list[dict[str, object]] = [
    {
        "ingredient_id": "ternera",
        "price_czk": 569.0,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 569.0,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "pollo",
        "price_czk": 198.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 198.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "pollo-picado",
        "price_czk": 79.9,
        "package_qty": 500,
        "package_unit": "g",
        "price_per_kg": 159.8,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "cerdo",
        "price_czk": 119.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 119.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "carne-picada-mixta",
        "price_czk": 99.9,
        "package_qty": 500,
        "package_unit": "g",
        "price_per_kg": 199.8,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "chorizo",
        "price_czk": 67.9,
        "package_qty": 1,
        "package_unit": "unit",
        "price_per_unit": 67.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "queso-rallado",
        "price_czk": 39.9,
        "package_qty": 200,
        "package_unit": "g",
        "price_per_kg": 199.5,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "huevos",
        "price_czk": 149.9,
        "package_qty": 18,
        "package_unit": "unit",
        "price_per_unit": 8.33,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "tomates-cherry",
        "price_czk": 249.0,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 249.0,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "pimiento-rojo",
        "price_czk": 119.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 119.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "tomate-rama",
        "price_czk": 99.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 99.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "cebolla-roja",
        "price_czk": 49.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 49.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "cebolla-amarilla",
        "price_czk": 39.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 39.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "zanahoria",
        "price_czk": 39.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 39.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "patata",
        "price_czk": 39.9,
        "package_qty": 2,
        "package_unit": "kg",
        "price_per_kg": 19.95,
        "source": "real_purchase",
        "notes": "Provided as approx. 2kg sack.",
    },
    {
        "ingredient_id": "limon",
        "price_czk": 69.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 69.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "platano",
        "price_czk": 17.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 17.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "aguacate",
        "price_czk": 79.9,
        "package_qty": 2,
        "package_unit": "unit",
        "price_per_unit": 39.95,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "pepino",
        "price_czk": 19.9,
        "package_qty": 1,
        "package_unit": "unit",
        "price_per_kg": 66.33,
        "price_per_unit": 19.9,
        "source": "real_purchase",
        "notes": "One cucumber assumed 300g for gram-based recipe costing.",
    },
    {
        "ingredient_id": "yogurt",
        "price_czk": 59.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 59.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "aceite-oliva",
        "price_czk": 159.9,
        "package_qty": 0.75,
        "package_unit": "l",
        "price_per_l": 213.2,
        "source": "real_purchase",
        "notes": "Bottle size assumed 750ml for costing.",
    },
    {
        "ingredient_id": "arroz-basmati",
        "price_czk": 59.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 59.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "harina",
        "price_czk": 9.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 9.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "avena",
        "price_czk": 11.9,
        "package_qty": 500,
        "package_unit": "g",
        "price_per_kg": 23.8,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "pasta-espaguetis",
        "price_czk": 15.9,
        "package_qty": 500,
        "package_unit": "g",
        "price_per_kg": 31.8,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "tomate-triturado",
        "price_czk": 36.9,
        "package_qty": 700,
        "package_unit": "g",
        "price_per_kg": 52.71,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "judias",
        "price_czk": 16.9,
        "package_qty": 400,
        "package_unit": "g",
        "price_per_kg": 42.25,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "wraps",
        "price_czk": 27.9,
        "package_qty": 6,
        "package_unit": "unit",
        "price_per_unit": 4.65,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "cerveza",
        "price_czk": 21.9,
        "package_qty": 0.5,
        "package_unit": "l",
        "price_per_l": 43.8,
        "price_per_unit": 21.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "leche",
        "price_czk": 17.9,
        "package_qty": 1,
        "package_unit": "l",
        "price_per_l": 17.9,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "arandanos-secos",
        "price_czk": 49.9,
        "package_qty": 200,
        "package_unit": "g",
        "price_per_kg": 249.5,
        "source": "real_purchase",
    },
    {
        "ingredient_id": "pasas",
        "price_czk": 34.9,
        "package_qty": 500,
        "package_unit": "g",
        "price_per_kg": 69.8,
        "source": "real_purchase",
        "notes": "Package size not provided; assumed 500g.",
    },
    {
        "ingredient_id": "hojaldre",
        "price_czk": 39.9,
        "package_qty": 275,
        "package_unit": "g",
        "price_per_kg": 145.09,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "nata",
        "price_czk": 32.9,
        "package_qty": 200,
        "package_unit": "g",
        "price_per_kg": 164.5,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "champinon",
        "price_czk": 49.9,
        "package_qty": 250,
        "package_unit": "g",
        "price_per_kg": 199.6,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "atun",
        "price_czk": 24.9,
        "package_qty": 1,
        "package_unit": "unit",
        "price_per_unit": 24.9,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "noodles",
        "price_czk": 34.9,
        "package_qty": 250,
        "package_unit": "g",
        "price_per_kg": 139.6,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "col",
        "price_czk": 29.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 29.9,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "higados",
        "price_czk": 79.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 79.9,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "lentejas",
        "price_czk": 44.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 44.9,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "pan-naan",
        "price_czk": 49.9,
        "package_qty": 5,
        "package_unit": "unit",
        "price_per_unit": 9.98,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "golden-curry",
        "price_czk": 69.9,
        "package_qty": 100,
        "package_unit": "g",
        "price_per_kg": 699.0,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "avecrem",
        "price_czk": 2.0,
        "package_qty": 1,
        "package_unit": "unit",
        "price_per_unit": 2.0,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "miel",
        "price_czk": 119.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 119.9,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "especias",
        "price_czk": 5.0,
        "package_qty": 1,
        "package_unit": "unit",
        "price_per_unit": 5.0,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "sazonador-burrito",
        "price_czk": 19.9,
        "package_qty": 1,
        "package_unit": "unit",
        "price_per_unit": 19.9,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "salsa-soja",
        "price_czk": 49.9,
        "package_qty": 150,
        "package_unit": "ml",
        "price_per_l": 332.67,
        "source": "manual_estimate",
        "notes": "Estimated Lidl Prague 2026 soy sauce bottle.",
    },
    {
        "ingredient_id": "ajo",
        "price_czk": 149.0,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 149.0,
        "source": "manual_estimate",
        "notes": "Estimated garlic loose/bag price.",
    },
    {
        "ingredient_id": "jengibre",
        "price_czk": 199.0,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 199.0,
        "source": "manual_estimate",
        "notes": "Estimated fresh ginger price.",
    },
    {
        "ingredient_id": "vinagre",
        "price_czk": 24.9,
        "package_qty": 1,
        "package_unit": "l",
        "price_per_l": 24.9,
        "source": "manual_estimate",
        "notes": "Estimated vinegar bottle.",
    },
    {
        "ingredient_id": "agua",
        "price_czk": 0.0,
        "package_qty": 1,
        "package_unit": "l",
        "price_per_l": 0.0,
        "source": "real_purchase",
        "notes": "Approved free tap water.",
    },
    {
        "ingredient_id": "levadura-seca",
        "price_czk": 20.0,
        "package_qty": 100,
        "package_unit": "g",
        "price_per_kg": 200.0,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "azucar",
        "price_czk": 24.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 24.9,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "polvo-hornear",
        "price_czk": 10.0,
        "package_qty": 40,
        "package_unit": "g",
        "price_per_kg": 250.0,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "mantequilla",
        "price_czk": 49.9,
        "package_qty": 250,
        "package_unit": "g",
        "price_per_kg": 199.6,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "perejil",
        "price_czk": 29.9,
        "package_qty": 30,
        "package_unit": "g",
        "price_per_kg": 996.67,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "comino",
        "price_czk": 29.9,
        "package_qty": 50,
        "package_unit": "g",
        "price_per_kg": 598.0,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "pimenton",
        "price_czk": 29.9,
        "package_qty": 50,
        "package_unit": "g",
        "price_per_kg": 598.0,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "oregano",
        "price_czk": 24.9,
        "package_qty": 20,
        "package_unit": "g",
        "price_per_kg": 1245.0,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "sal",
        "price_czk": 12.9,
        "package_qty": 1,
        "package_unit": "kg",
        "price_per_kg": 12.9,
        "source": "manual_estimate",
    },
    {
        "ingredient_id": "pimienta",
        "price_czk": 39.9,
        "package_qty": 50,
        "package_unit": "g",
        "price_per_kg": 798.0,
        "source": "manual_estimate",
    },
]


def ri(
    ingredient_id: str,
    quantity: float,
    unit: str = "g",
    display: str | None = None,
    source: str = "manual_seed",
    notes: str = "",
) -> dict[str, object]:
    return {
        "ingredient_id": ingredient_id,
        "display_name": display or ingredient_id,
        "quantity": quantity,
        "unit": unit,
        "grams": grams_for(ingredient_id, quantity, unit),
        "source": source,
        "notes": notes,
    }


RECIPES: list[dict[str, object]] = [
    {
        "id": "burrito",
        "name": "Burrito batch",
        "status": "approved",
        "servings": 6,
        "tags": ["lunch", "dinner", "wrap", "rice", "chicken"],
        "protein_status": "high",
        "raw": "500g pollo picado 6 tortitas 250g arroz 1 bote judias 2 aguacates 1 queso rallado 1 pimiento 3 cebollas yogurt sazonador",
        "procedure": "Cook seasoned minced chicken, rice, beans, pepper and onions. Fill six wraps with avocado, yogurt sauce, and grated cheese.",
        "ingredients": [
            ri("pollo-picado", 500),
            ri("wraps", 6, "unit"),
            ri("arroz-basmati", 250),
            ri("judias", 400),
            ri("aguacate", 2, "unit"),
            ri("queso-rallado", 200),
            ri("pimiento-rojo", 1, "unit"),
            ri("cebolla-amarilla", 3, "unit"),
            ri("yogurt", 150),
            ri("sazonador-burrito", 1, "unit"),
            ri("limon", 0.5, "unit"),
            ri("agua", 500, "ml", notes="For cooking the 250g rice batch."),
            ri("sal", 6, notes="For rice and final seasoning."),
        ],
    },
    {
        "id": "lentejas",
        "name": "Lentejas con cerdo y chorizo",
        "status": "approved",
        "servings": 6,
        "tags": ["lunch", "dinner", "stew", "legume", "pork", "potato"],
        "protein_status": "good",
        "raw": "1 cebolla 1 pimiento 2 tomates carne cerdo 300g lentejas 1 chorizo 3 zanahorias 4 patatas",
        "procedure": "Stew lentils with pork, chorizo, vegetables, and potatoes until tender.",
        "ingredients": [
            ri("cebolla-amarilla", 1, "unit"),
            ri("pimiento-rojo", 1, "unit"),
            ri("tomate-rama", 2, "unit"),
            ri("cerdo", 500),
            ri("lentejas", 300),
            ri("chorizo", 1, "unit"),
            ri("zanahoria", 3, "unit"),
            ri("patata", 4, "unit"),
            ri("ajo", 12),
            ri("avecrem", 1, "unit"),
            ri("aceite-oliva", 10, "ml"),
            ri("especias", 1, "unit"),
            ri("agua", 1600, "ml", notes="Initial stew liquid; top up only if it gets too thick."),
            ri("sal", 10),
            ri("pimienta", 3),
        ],
    },
    {
        "id": "pasta-carne",
        "name": "Pasta con carne",
        "status": "approved",
        "servings": 5,
        "tags": ["lunch", "dinner", "pasta", "red_meat"],
        "protein_status": "good",
        "raw": "500 g carne picada 500 g pasta 1 tomate frito 3 cebollas 1 cerveza avecrem",
        "procedure": "Cook pasta. Simmer mince with onion, tomato sauce, beer, and stock cube, then combine.",
        "ingredients": [
            ri("carne-picada-mixta", 500),
            ri("pasta-espaguetis", 500),
            ri("tomate-triturado", 700),
            ri("cebolla-amarilla", 3, "unit"),
            ri("cerveza", 250, "ml"),
            ri("avecrem", 1, "unit"),
            ri("ajo", 10),
            ri("aceite-oliva", 10, "ml"),
            ri("especias", 1, "unit"),
            ri("agua", 2500, "ml", notes="Salted pasta cooking water for the whole batch."),
            ri("sal", 12, notes="Mostly for the pasta water."),
        ],
    },
    {
        "id": "arroz-cerdo",
        "name": "Arroz con cerdo y chorizo",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "rice", "pork"],
        "protein_status": "good",
        "raw": "250g cerdo 1 chorizo 300g arroz 1 tomate 1 cerveza",
        "procedure": "Cook pork and chorizo with tomato and beer, then simmer with rice.",
        "ingredients": [
            ri("cerdo", 250),
            ri("chorizo", 1, "unit"),
            ri("arroz-basmati", 300),
            ri("cebolla-amarilla", 1, "unit"),
            ri("tomate-rama", 1, "unit"),
            ri("cerveza", 500, "ml"),
            ri("avecrem", 1, "unit"),
            ri("aceite-oliva", 10, "ml"),
            ri("especias", 1, "unit"),
            ri("agua", 650, "ml", notes="Rice cooking liquid after accounting for beer."),
            ri("sal", 6),
        ],
    },
    {
        "id": "arroz-higados",
        "name": "Arroz con hígados y pollo",
        "status": "approved",
        "servings": 5,
        "tags": ["lunch", "dinner", "rice", "chicken", "organ_meat"],
        "protein_status": "high",
        "raw": "250g higados 250g pollo 300g arroz 1 tomate 2 cebollas 1 pimientos 1 cervezas tomate frito",
        "procedure": "Brown chicken and livers, add vegetables, beer, tomato sauce, and rice; simmer until cooked.",
        "ingredients": [
            ri("higados", 250),
            ri("pollo", 250),
            ri("arroz-basmati", 300),
            ri("tomate-rama", 1, "unit"),
            ri("cebolla-amarilla", 2, "unit"),
            ri("pimiento-rojo", 1, "unit"),
            ri("cerveza", 500, "ml"),
            ri("tomate-triturado", 350),
            ri("ajo", 10),
            ri("avecrem", 1, "unit"),
            ri("aceite-oliva", 10, "ml"),
            ri("especias", 1, "unit"),
            ri("agua", 650, "ml", notes="Rice cooking liquid after accounting for beer and tomato sauce."),
            ri("sal", 6),
        ],
    },
    {
        "id": "risotto-pollo",
        "name": "Risotto de pollo",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "rice", "chicken", "dairy"],
        "protein_status": "good",
        "raw": "250g pollo 250g arroz nata champiñon 1 queso rallado",
        "procedure": "Cook chicken, mushrooms, rice, cream, and grated cheese into a creamy rice dish.",
        "ingredients": [
            ri("pollo", 250),
            ri("arroz-basmati", 250),
            ri("nata", 200),
            ri("champinon", 250),
            ri("queso-rallado", 200),
            ri("cebolla-amarilla", 1, "unit"),
            ri("ajo", 8),
            ri("avecrem", 1, "unit"),
            ri("aceite-oliva", 10, "ml"),
            ri("agua", 850, "ml", notes="Added in stages for the risotto texture."),
            ri("sal", 4),
        ],
    },
    {
        "id": "arroz-chino",
        "name": "Arroz chino no frito",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "rice", "chicken", "adapted_no_fry"],
        "protein_status": "good",
        "raw": "80g arroz 100g pollo col 1 zanahoria 1 cebolla",
        "procedure": "Cook rice separately. Sauté or steam chicken and vegetables with minimal oil; do not fry rice.",
        "ingredients": [
            ri("arroz-basmati", 320),
            ri("pollo", 500),
            ri("col", 400),
            ri("zanahoria", 4, "unit"),
            ri("cebolla-amarilla", 3, "unit"),
            ri("salsa-soja", 80, "ml"),
            ri("huevos", 4, "unit"),
            ri("ajo", 24),
            ri("jengibre", 20),
            ri("aceite-oliva", 20, "ml"),
            ri("agua", 720, "ml", notes="640ml for rice plus 80ml for the sauce."),
        ],
    },
    {
        "id": "curry-indio",
        "name": "Curry indio de pollo",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "rice", "chicken", "curry"],
        "protein_status": "good",
        "raw": "80g arroz 100g pollo 1 tomate frito 1 cerveza yogurt 1 zanahoria",
        "procedure": "Cook chicken with tomato, beer, yogurt, carrot, and spices; serve with rice.",
        "ingredients": [
            ri("arroz-basmati", 320),
            ri("pollo", 600),
            ri("tomate-triturado", 700),
            ri("cerveza", 500, "ml"),
            ri("yogurt", 400),
            ri("zanahoria", 4, "unit"),
            ri("especias", 1, "unit"),
            ri("cebolla-amarilla", 2, "unit"),
            ri("ajo", 24),
            ri("jengibre", 20),
            ri("aceite-oliva", 20, "ml"),
            ri("agua", 850, "ml", notes="640ml for rice plus about 210ml for the curry sauce."),
            ri("sal", 6),
        ],
    },
    {
        "id": "curry-japones",
        "name": "Curry japonés de pollo",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "rice", "chicken", "curry", "potato"],
        "protein_status": "good",
        "raw": "80g arroz 100g pollo 1 zanahoria 1/2 cebolla 1/2 patata cucharadita de miel trozo de golden curry avecrem",
        "procedure": "Simmer chicken, vegetables, curry cube, honey, and stock; serve with rice.",
        "ingredients": [
            ri("arroz-basmati", 320),
            ri("pollo", 600),
            ri("zanahoria", 4, "unit"),
            ri("cebolla-amarilla", 2, "unit"),
            ri("patata", 2, "unit"),
            ri("miel", 20),
            ri("golden-curry", 100),
            ri("avecrem", 1, "unit"),
            ri("ajo", 20),
            ri("aceite-oliva", 20, "ml"),
            ri("agua", 1800, "ml", notes="640ml for rice plus about 1160ml for the curry."),
        ],
    },
    {
        "id": "noodles-pollo",
        "name": "Noodles con pollo",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "noodles", "chicken"],
        "protein_status": "ok",
        "raw": "125g noodles, col, 1/3 pimiento 1/2 cebolla 100g pollo 1 zanahoria",
        "procedure": "Cook noodles and combine with chicken and vegetables; avoid deep frying.",
        "ingredients": [
            ri("noodles", 500),
            ri("col", 400),
            ri("pimiento-rojo", 1.33, "unit"),
            ri("cebolla-amarilla", 2, "unit"),
            ri("pollo", 500),
            ri("zanahoria", 4, "unit"),
            ri("salsa-soja", 100, "ml"),
            ri("ajo", 24),
            ri("jengibre", 20),
            ri("miel", 28),
            ri("vinagre", 40, "ml"),
            ri("aceite-oliva", 20, "ml"),
            ri("agua", 2120, "ml", notes="2L noodle cooking water plus 120ml sauce water."),
        ],
    },
    {
        "id": "empanada-carne",
        "name": "Empanada de carne",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "pastry", "red_meat"],
        "protein_status": "good",
        "raw": "2 milhojas, 1 cebolla 1/2 pimiento 500g carne picada tomate frito 1/2 cerveza",
        "procedure": "Fill pastry with cooked mince, onion, pepper, tomato sauce, and beer reduction; bake, do not fry.",
        "ingredients": [
            ri("hojaldre", 550),
            ri("cebolla-amarilla", 1, "unit"),
            ri("pimiento-rojo", 0.5, "unit"),
            ri("carne-picada-mixta", 500),
            ri("tomate-triturado", 350),
            ri("cerveza", 250, "ml"),
            ri("ajo", 8),
            ri("aceite-oliva", 10, "ml"),
            ri("especias", 1, "unit"),
        ],
    },
    {
        "id": "empanada-pollo",
        "name": "Empanada de pollo",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "pastry", "chicken"],
        "protein_status": "good",
        "raw": "2 milhojas, 2 cebollas 500g pollo nata champiñones",
        "procedure": "Fill pastry with chicken, onion, cream, and mushrooms; bake, do not fry.",
        "ingredients": [
            ri("hojaldre", 550),
            ri("cebolla-amarilla", 2, "unit"),
            ri("pollo", 500),
            ri("nata", 200),
            ri("champinon", 250),
            ri("ajo", 8),
            ri("aceite-oliva", 10, "ml"),
            ri("especias", 1, "unit"),
        ],
    },
    {
        "id": "empanada-atun",
        "name": "Empanada de atún",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "pastry", "fish", "egg"],
        "protein_status": "good",
        "raw": "2 milhojas, 2 latas atun 4 huevos tomate frito",
        "procedure": "Fill pastry with tuna, boiled egg, and tomato sauce; bake, do not fry.",
        "ingredients": [
            ri("hojaldre", 550),
            ri("atun", 2, "unit"),
            ri("huevos", 4, "unit"),
            ri("tomate-triturado", 350),
            ri("cebolla-amarilla", 1, "unit"),
            ri("pimiento-rojo", 0.5, "unit"),
            ri("especias", 1, "unit"),
        ],
    },
    {
        "id": "sish-kebab",
        "name": "Sish kebab con patatas",
        "status": "approved",
        "servings": 6,
        "tags": ["lunch", "dinner", "beef", "potato", "bread", "grill"],
        "protein_status": "high",
        "raw": (
            "750g rumpsteak, lemon-garlic spice marinade, homemade skillet naan, "
            "oven potatoes, and a tomato-red onion topping with vinaigrette."
        ),
        "procedure": "Marinate beef with spices and lemon. Cook with tomato/onion and serve with oven potatoes and naan.",
        "ingredients": [
            ri("ternera", 750, notes="Cut into 3cm cubes for skewers."),
            ri(
                "aceite-oliva",
                132,
                "ml",
                notes="45ml beef marinade, 20ml naan dough, 45ml potatoes, 22ml salad vinaigrette.",
            ),
            ri("limon", 112, notes="Juice for beef marinade, potatoes, and vinaigrette."),
            ri("ajo", 18, notes="Finely minced for the beef marinade."),
            ri("comino", 5),
            ri("pimenton", 8, notes="5g smoked paprika for beef plus 3g sweet paprika for vinaigrette."),
            ri("sal", 21, notes="Total salt across beef, naan, potatoes, and vinaigrette."),
            ri("pimienta", 6, notes="Black pepper for beef and potatoes."),
            ri("harina", 450, notes="Plain wheat flour for skillet naan."),
            ri("agua", 150, "ml", notes="Warm water for activating the yeast."),
            ri("yogurt", 90, notes="Greek/plain yogurt for naan dough."),
            ri("levadura-seca", 9),
            ri("azucar", 6),
            ri("polvo-hornear", 4.5),
            ri("mantequilla", 25, notes="Melted, brushed on naan after cooking."),
            ri("patata", 900, notes="Halved and roasted."),
            ri("oregano", 3),
            ri("tomates-cherry", 375, notes="Halved or quartered for salad."),
            ri("cebolla-roja", 225, notes="Thinly sliced and macerated in vinaigrette."),
            ri("perejil", 30),
            ri("vinagre", 8, "ml"),
        ],
    },
    {
        "id": "pasta-pollo",
        "name": "Pasta con pollo",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "pasta", "chicken", "curated"],
        "protein_status": "good",
        "raw": "Pasta: 100g pasta / Pollo: missing details",
        "procedure": (
            "Cook the pasta until al dente. Cook chicken with onion, mushrooms, tomato sauce, "
            "and spices using minimal oil. Combine with pasta and portion into four meals."
        ),
        "ingredients": [
            ri("pasta-espaguetis", 400),
            ri("pollo", 500),
            ri("tomate-triturado", 350),
            ri("cebolla-amarilla", 2, "unit"),
            ri("champinon", 250),
            ri("ajo", 8),
            ri("aceite-oliva", 15, "ml"),
            ri("especias", 1, "unit"),
            ri("agua", 2500, "ml", notes="Salted pasta cooking water for the whole batch."),
            ri("sal", 10),
        ],
    },
    {
        "id": "pizza",
        "name": "Pizza",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "pizza", "chicken", "curated"],
        "protein_status": "good",
        "raw": "Pipsa:",
        "procedure": (
            "Make a simple tray dough with flour, water, salt, and a little olive oil. Spread tomato sauce, "
            "add cooked chicken, mushrooms, pepper, and grated cheese. Bake until the base is cooked and cheese is browned."
        ),
        "ingredients": [
            ri("harina", 500),
            ri("tomate-triturado", 350),
            ri("queso-rallado", 200),
            ri("pollo", 300),
            ri("champinon", 250),
            ri("pimiento-rojo", 1, "unit"),
            ri("ajo", 8),
            ri("aceite-oliva", 30, "ml", notes="20ml for dough plus 10ml for cooking chicken/topping prep."),
            ri("agua", 325, "ml", notes="Warm water for the pizza dough."),
            ri("levadura-seca", 7, notes="For the pizza dough."),
            ri("azucar", 5, notes="Feeds the yeast in the dough."),
            ri("sal", 10, notes="For the dough."),
            ri("oregano", 2, notes="For the tomato sauce/topping."),
        ],
    },
    {
        "id": "pollo-papa-horno",
        "name": "Pollo papa horno",
        "status": "approved",
        "servings": 4,
        "tags": ["lunch", "dinner", "chicken", "potato", "oven", "curated"],
        "protein_status": "high",
        "raw": "Pollo papa horno:",
        "procedure": (
            "Cut potatoes, onion, pepper, and tomatoes into a tray. Add chicken, lemon, spices, and measured olive oil. "
            "Bake until the potatoes are tender and the chicken is cooked through, then portion into four meals."
        ),
        "ingredients": [
            ri("pollo", 700),
            ri("patata", 5, "unit"),
            ri("cebolla-amarilla", 2, "unit"),
            ri("pimiento-rojo", 1, "unit"),
            ri("tomate-rama", 2, "unit"),
            ri("limon", 1, "unit"),
            ri("ajo", 10),
            ri("aceite-oliva", 20, "ml"),
            ri("especias", 1, "unit"),
            ri("agua", 120, "ml", notes="Tray liquid so the vegetables and chicken do not dry out."),
            ri("sal", 8),
            ri("pimienta", 3),
        ],
    },
    {
        "id": "puchero",
        "name": "Puchero",
        "status": "approved",
        "servings": 6,
        "tags": ["lunch", "dinner", "stew", "chicken", "pork", "curated"],
        "protein_status": "high",
        "raw": "Puchero:",
        "procedure": (
            "Simmer chicken, pork, potatoes, carrots, onion, beans, and stock cube in water until tender. "
            "Keep it as a lean stew, skim excess fat, and portion into six batch meals."
        ),
        "ingredients": [
            ri("pollo", 500),
            ri("cerdo", 500),
            ri("judias", 400),
            ri("patata", 4, "unit"),
            ri("zanahoria", 3, "unit"),
            ri("cebolla-amarilla", 1, "unit"),
            ri("ajo", 12),
            ri("avecrem", 1, "unit"),
            ri("especias", 1, "unit"),
            ri("agua", 1800, "ml", notes="Stew broth; top up only if needed while simmering."),
            ri("sal", 8),
            ri("pimienta", 3),
        ],
    },
    {
        "id": "hamburguesa",
        "name": "Hamburguesa",
        "status": "approved",
        "servings": 5,
        "tags": ["lunch", "dinner", "burger", "red_meat", "potato", "curated"],
        "protein_status": "good",
        "raw": "Hamborguesa:",
        "procedure": (
            "Form five patties from the ground meat and cook on a non-stick pan or grill without deep frying. "
            "Bake potato wedges, then serve each patty with naan, tomato, onion, cheese, and yogurt sauce."
        ),
        "ingredients": [
            ri("carne-picada-mixta", 500),
            ri("pan-naan", 5, "unit"),
            ri("queso-rallado", 100),
            ri("tomate-rama", 2, "unit"),
            ri("cebolla-amarilla", 1, "unit"),
            ri("patata", 5, "unit"),
            ri("yogurt", 150),
            ri("ajo", 8),
            ri("especias", 1, "unit"),
            ri("aceite-oliva", 20, "ml", notes="For the baked potato wedges."),
            ri("sal", 8),
            ri("pimienta", 3),
        ],
    },
]


def apply_curated_draft_fillers(conn: sqlite3.Connection) -> None:
    current = conn.execute("SELECT value FROM settings WHERE key = 'draft_filler_version'").fetchone()
    if current and current["value"] == DRAFT_FILLER_VERSION:
        return

    recipes_by_id = {str(recipe["id"]): recipe for recipe in RECIPES}
    for recipe_id in sorted(CURATED_RECIPE_IDS):
        recipe = recipes_by_id[recipe_id]
        exists = conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if not exists:
            continue
        conn.execute(
            """
            UPDATE recipes
            SET status = 'approved',
                servings = ?,
                raw_source = ?,
                procedure = ?,
                tags = ?,
                protein_status = ?,
                decision_status = 'approved',
                decision_reason = 'Curated recipe approved after batch-cooking review.'
            WHERE id = ?
            """,
            (
                recipe["servings"],
                recipe["raw"],
                recipe["procedure"],
                json.dumps(recipe["tags"]),
                recipe["protein_status"],
                recipe_id,
            ),
        )
        conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
        conn.execute("DELETE FROM recipe_reviews WHERE recipe_id = ?", (recipe_id,))
        for line in recipe["ingredients"]:
            conn.execute(
                """
                INSERT INTO recipe_ingredients
                (recipe_id, ingredient_id, display_name, quantity, unit, grams, source, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recipe_id,
                    line["ingredient_id"],
                    line["display_name"],
                    line["quantity"],
                    line["unit"],
                    line["grams"],
                    "curated_seed",
                    line["notes"],
                ),
            )
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('draft_filler_version', ?)", (DRAFT_FILLER_VERSION,)
    )
    conn.commit()


def _ensure_seed_catalog_items(conn: sqlite3.Connection) -> None:
    for item in INGREDIENTS:
        conn.execute(
            """
            INSERT OR IGNORE INTO ingredients
            (id, name, category, default_unit, tags, nutrition_source, kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["name"],
                item["category"],
                item["default_unit"],
                json.dumps(item["tags"]),
                item["nutrition_source"],
                item["kcal"],
                item["protein"],
                item["carbs"],
                item["fat"],
                item["notes"],
            ),
        )
        for alias in item["aliases"]:
            conn.execute(
                "INSERT OR IGNORE INTO ingredient_aliases (alias, ingredient_id) VALUES (?, ?)",
                (str(alias).lower(), item["id"]),
            )

    for price in PRICES:
        exists = conn.execute(
            """
            SELECT 1 FROM prices
            WHERE ingredient_id = ? AND context = ? AND source = ? AND price_czk = ?
            LIMIT 1
            """,
            (price["ingredient_id"], PRICE_CONTEXT, price["source"], price["price_czk"]),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO prices
            (ingredient_id, context, price_czk, package_qty, package_unit, price_per_kg, price_per_l, price_per_unit, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                price["ingredient_id"],
                PRICE_CONTEXT,
                price["price_czk"],
                price.get("package_qty"),
                price.get("package_unit"),
                price.get("price_per_kg"),
                price.get("price_per_l"),
                price.get("price_per_unit"),
                price["source"],
                price.get("notes", ""),
            ),
        )


def apply_serious_recipe_curation(conn: sqlite3.Connection) -> None:
    current = conn.execute("SELECT value FROM settings WHERE key = 'serious_curation_version'").fetchone()
    if current and current["value"] == SERIOUS_CURATION_VERSION:
        return

    _ensure_seed_catalog_items(conn)
    for recipe in RECIPES:
        recipe_id = recipe["id"]
        exists = conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if not exists:
            continue
        decision_status = "needs_review" if recipe["status"] == "draft" else "approved"
        decision_reason = "Manually curated with missing sauces, aromatics, oil, stock/seasoning, and practical batch-cooking details."
        conn.execute(
            """
            UPDATE recipes
            SET status = ?,
                servings = ?,
                raw_source = ?,
                procedure = ?,
                tags = ?,
                protein_status = ?,
                decision_status = ?,
                decision_reason = ?
            WHERE id = ?
            """,
            (
                recipe["status"],
                recipe["servings"],
                recipe["raw"],
                recipe["procedure"],
                json.dumps(recipe["tags"]),
                recipe["protein_status"],
                decision_status,
                decision_reason,
                recipe_id,
            ),
        )
        conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
        conn.execute("DELETE FROM recipe_reviews WHERE recipe_id = ?", (recipe_id,))
        for line in recipe["ingredients"]:
            conn.execute(
                """
                INSERT INTO recipe_ingredients
                (recipe_id, ingredient_id, display_name, quantity, unit, grams, source, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recipe_id,
                    line["ingredient_id"],
                    line["display_name"],
                    line["quantity"],
                    line["unit"],
                    line["grams"],
                    "manual_curation",
                    line["notes"],
                ),
            )
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('serious_curation_version', ?)",
        (SERIOUS_CURATION_VERSION,),
    )
    conn.commit()


def _normalize_procedure_text(procedure: str) -> str:
    text = procedure.strip()
    if not text.startswith("["):
        return procedure
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return procedure
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        return procedure
    return " ".join(item.strip() for item in parsed if item.strip())


def apply_recipe_quality_curation(conn: sqlite3.Connection) -> None:
    current = conn.execute("SELECT value FROM settings WHERE key = 'recipe_quality_version'").fetchone()
    if current and current["value"] == RECIPE_QUALITY_VERSION:
        return

    for row in conn.execute("SELECT id, procedure FROM recipes").fetchall():
        normalized = _normalize_procedure_text(str(row["procedure"]))
        if normalized != row["procedure"]:
            conn.execute("UPDATE recipes SET procedure = ? WHERE id = ?", (normalized, row["id"]))

    for recipe_id, procedure in PROCEDURE_FIXES.items():
        exists = conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if exists:
            conn.execute("UPDATE recipes SET procedure = ? WHERE id = ?", (procedure, recipe_id))

    for recipe_id, fields in RECIPE_FIELD_FIXES.items():
        exists = conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if not exists:
            continue
        if "name" in fields:
            conn.execute("UPDATE recipes SET name = ? WHERE id = ?", (fields["name"], recipe_id))
        if "tags" in fields:
            conn.execute("UPDATE recipes SET tags = ? WHERE id = ?", (json.dumps(fields["tags"]), recipe_id))
        if "decision_reason" in fields:
            conn.execute("UPDATE recipes SET decision_reason = ? WHERE id = ?", (fields["decision_reason"], recipe_id))

    for addition in RECIPE_INGREDIENT_ADDITIONS:
        recipe_id = addition["recipe_id"]
        ingredient_id = addition["ingredient_id"]
        if not conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone():
            continue
        if not conn.execute(
            "SELECT 1 FROM recipe_ingredients WHERE recipe_id = ? AND ingredient_id = ?",
            (recipe_id, ingredient_id),
        ).fetchone():
            conn.execute(
                """
                INSERT INTO recipe_ingredients
                (recipe_id, ingredient_id, display_name, quantity, unit, grams, source, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recipe_id,
                    ingredient_id,
                    addition["display_name"],
                    addition["quantity"],
                    addition["unit"],
                    addition["grams"],
                    addition["source"],
                    addition["notes"],
                ),
            )

    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('recipe_quality_version', ?)",
        (RECIPE_QUALITY_VERSION,),
    )
    conn.commit()


def seed_database(conn: sqlite3.Connection) -> None:
    for item in INGREDIENTS:
        conn.execute(
            """
            INSERT OR REPLACE INTO ingredients
            (id, name, category, default_unit, tags, nutrition_source, kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["name"],
                item["category"],
                item["default_unit"],
                json.dumps(item["tags"]),
                item["nutrition_source"],
                item["kcal"],
                item["protein"],
                item["carbs"],
                item["fat"],
                item["notes"],
            ),
        )
        for alias in item["aliases"]:
            conn.execute(
                "INSERT OR REPLACE INTO ingredient_aliases (alias, ingredient_id) VALUES (?, ?)",
                (str(alias).lower(), item["id"]),
            )

    for price in PRICES:
        conn.execute(
            """
            INSERT INTO prices
            (ingredient_id, context, price_czk, package_qty, package_unit, price_per_kg, price_per_l, price_per_unit, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                price["ingredient_id"],
                PRICE_CONTEXT,
                price["price_czk"],
                price.get("package_qty"),
                price.get("package_unit"),
                price.get("price_per_kg"),
                price.get("price_per_l"),
                price.get("price_per_unit"),
                price["source"],
                price.get("notes", ""),
            ),
        )

    for recipe in RECIPES:
        conn.execute(
            """
            INSERT OR REPLACE INTO recipes
            (id, name, status, meal_type, servings, raw_source, procedure, tags, source_type, protein_status, decision_status, decision_reason)
            VALUES (?, ?, ?, 'lunch_dinner', ?, ?, ?, ?, 'manual_seed', ?, ?, ?)
            """,
            (
                recipe["id"],
                recipe["name"],
                recipe["status"],
                recipe["servings"],
                recipe["raw"],
                recipe["procedure"],
                json.dumps(recipe["tags"]),
                recipe["protein_status"],
                "needs_review" if recipe["status"] == "draft" else "approved",
                "Incomplete seed recipe; keep as draft."
                if recipe["status"] == "draft"
                else "Seeded from provided initial recipe list.",
            ),
        )
        conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe["id"],))
        for line in recipe["ingredients"]:
            conn.execute(
                """
                INSERT INTO recipe_ingredients
                (recipe_id, ingredient_id, display_name, quantity, unit, grams, source, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recipe["id"],
                    line["ingredient_id"],
                    line["display_name"],
                    line["quantity"],
                    line["unit"],
                    line["grams"],
                    line["source"],
                    line["notes"],
                ),
            )

    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('seed_version', ?)", (SEED_VERSION,))
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('future_youtube_playlist', ?)",
        ("https://www.youtube.com/playlist?list=PLuPXdq8cpUVwlWjUmwXAnP_Nq0OLV-wsH",),
    )
    from .localization import apply_english_labels

    apply_english_labels(conn)
    conn.commit()
