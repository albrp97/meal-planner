from __future__ import annotations

import json
import sqlite3

from .english import translate_name, translate_text

ENGLISH_CLEANUP_VERSION = "2026-05-15-cleanup-3"

INGREDIENT_NAMES = {
    "ternera": "Beef rump",
    "pollo": "Chicken thigh fillets",
    "pollo-picado": "Ground chicken",
    "cerdo": "Pork neck",
    "carne-picada-mixta": "Mixed ground meat",
    "chorizo": "Chorizo-style sausage",
    "queso-rallado": "Grated cheese",
    "huevos": "Large eggs",
    "tomates-cherry": "Cherry tomatoes",
    "pimiento-rojo": "Red bell pepper",
    "tomate-rama": "Vine tomato",
    "cebolla-roja": "Red onion",
    "cebolla-amarilla": "Yellow onion",
    "zanahoria": "Carrot",
    "patata": "Potato",
    "limon": "Lemon",
    "platano": "Banana",
    "aguacate": "Avocado",
    "pepino": "Cucumber",
    "yogurt": "Plain yogurt 3.9%",
    "aceite-oliva": "Extra-virgin olive oil",
    "arroz-basmati": "Basmati rice",
    "harina": "Plain wheat flour",
    "avena": "Rolled oats",
    "pasta-espaguetis": "Spaghetti pasta",
    "tomate-triturado": "Crushed tomato sauce",
    "judias": "Black/red beans",
    "wraps": "Tortilla wraps",
    "cerveza": "Staropramen beer",
    "leche": "UHT milk",
    "arandanos-secos": "Dried cranberries",
    "pasas": "Jumbo raisins",
    "hojaldre": "Puff pastry",
    "nata": "Cooking cream",
    "champinon": "Mushrooms",
    "atun": "Canned tuna",
    "noodles": "Noodles",
    "col": "Cabbage",
    "higados": "Chicken livers",
    "lentejas": "Lentils",
    "pan-naan": "Naan bread",
    "golden-curry": "Golden curry roux",
    "avecrem": "Stock cube",
    "miel": "Honey",
    "especias": "Spices",
    "sazonador-burrito": "Burrito seasoning",
    "salsa-soja": "Soy sauce",
    "ajo": "Garlic",
    "jengibre": "Ginger",
    "vinagre": "Vinegar",
    "agua": "Water",
    "levadura-seca": "Dry yeast",
    "azucar": "White sugar",
    "polvo-hornear": "Baking powder",
    "mantequilla": "Butter",
    "perejil": "Fresh parsley",
    "comino": "Ground cumin",
    "pimenton": "Paprika",
    "oregano": "Oregano",
    "sal": "Salt",
    "pimienta": "Black pepper",
}

RECIPE_NAMES = {
    "burrito": "Burrito batch",
    "lentejas": "Lentil stew with pork and chorizo",
    "pasta-carne": "Pasta with beef",
    "arroz-cerdo": "Rice with pork and chorizo",
    "arroz-higados": "Rice with chicken and livers",
    "risotto-pollo": "Chicken risotto",
    "arroz-chino": "Chicken fried rice (non-fried method)",
    "curry-indio": "Indian-style chicken curry",
    "curry-japones": "Japanese chicken curry",
    "noodles-pollo": "Chicken noodles",
    "empanada-carne": "Beef empanada",
    "empanada-pollo": "Chicken empanada",
    "empanada-atun": "Tuna empanada",
    "sish-kebab": "Beef shish kebab with potatoes",
    "pasta-pollo": "Chicken pasta",
    "pizza": "Pizza",
    "pollo-papa-horno": "Oven chicken and potatoes",
    "puchero": "Spanish-style stew",
    "hamburguesa": "Burger",
}

RECIPE_PROCEDURES = {
    "arroz-chino": (
        "Batch plan: this makes four meals, but the texture is best if rice, egg, chicken, vegetables, and sauce are stored separately. Batch prep: cook 320g rice with 640ml water for 12 minutes, rest covered 10 minutes, then spread it out to steam dry. Cook 4 eggs as thin omelettes for 1-2 minutes per side, slice them, and mix 80ml soy sauce, 24g garlic, 20g ginger, and 80ml water as the sauce. "
        "Individual cook: for each meal, cook one 125g chicken portion with 5ml oil for 5-6 minutes, add one vegetable portion with a splash of water for 3-4 minutes, then fold in one portion of rice, egg, and sauce only to warm through for 2 minutes. "
        "Do not fry the rice aggressively; keep it as a non-fried reheated rice bowl. Portion remaining components separately for the next meals."
    ),
    "lentejas": (
        "Batch cook: this stew is cooked fully as one pot and portioned into six meals. Rinse 300g lentils and cut the pork, potatoes, carrot, onion, pepper, and tomatoes into spoon-sized pieces. Brown the pork in 10ml olive oil for 5-7 minutes, then add onion and pepper for 5 minutes until aromatic. "
        "Add lentils, chorizo-style sausage, tomatoes, carrots, potatoes, garlic, stock cube, spices, 10g salt, 3g pepper, and 1600ml water. Simmer gently covered for 45-60 minutes until the lentils and potatoes are tender, adding only a small splash of water if it thickens too much. "
        "Rest for 10 minutes, skim excess fat if needed, and portion into batch meals. Individual cook: no separate cooking is needed; reheat one portion with a splash of water."
    ),
    "pasta-carne": (
        "Batch cook: make the meat sauce as one batch. Cook onions with 10ml olive oil for 6-8 minutes until soft, add 500g ground meat and break it up well for 8-10 minutes, then add 700g tomato sauce, 250ml beer, stock cube, 10g garlic, and spices. "
        "Simmer uncovered for 20-25 minutes until thick and the alcohol cooks off, then cool and portion the sauce into five containers. Individual cook: pasta is best cooked fresh per meal; cook 100g pasta in about 500ml salted water for 9-11 minutes, reheat one sauce portion for 3-4 minutes, and combine with a splash of pasta water. "
        "If convenience matters more than texture, cook all pasta slightly underdone and box it with the sauce."
    ),
    "arroz-cerdo": (
        "Batch cook: this rice dish is cooked fully as one pot and portioned into four meals. Cut the pork and chorizo-style sausage into bite-sized pieces. Brown them in 10ml olive oil for 6-8 minutes, then add onion, tomato, 6g salt, and spices and cook 5 minutes until the tomato breaks down. "
        "Add 300g rice, 500ml beer, and 650ml water, then simmer covered on low heat for 15-18 minutes until the rice is cooked and the liquid is absorbed. Rest covered for 5 minutes. "
        "Fluff the rice and portion evenly so each meal gets pork and sausage. Individual cook: no separate cooking is needed; reheat gently with a splash of water."
    ),
    "arroz-higados": (
        "Batch cook: cook the full rice, chicken, and liver pot together, then portion into five meals. Trim the livers and cut the chicken into bite-sized pieces. Brown the chicken in 10ml olive oil for 5 minutes, add the livers for 2 minutes, then add onion, pepper, and tomato for 5 minutes. "
        "Add 500ml beer, 350g tomato sauce, 300g rice, stock cube, spices, 6g salt, and 650ml water. Simmer covered on low heat for 15-18 minutes until the rice is tender and the protein is fully cooked. "
        "Rest, stir gently so the livers do not break apart too much, and portion into batch meals. Individual cook: reheat one portion gently so the livers stay tender."
    ),
    "risotto-pollo": (
        "Batch cook: make the chicken, mushrooms, and creamy rice as one four-serving pot. Cut chicken and mushrooms into small pieces. Cook the chicken in 10ml olive oil for 5-6 minutes until browned, then add mushrooms and cook 5 minutes until their water evaporates. "
        "Add 250g rice and 850ml hot water/stock in 3-4 additions over 18-22 minutes, stirring often until creamy and cooked. Stir in 200g cream and 200g grated cheese at the end for 2 minutes on low heat so it does not split. "
        "Rest for a few minutes and portion while still loose, because it thickens in the fridge. Individual cook: reheat one portion with a splash of milk or water to bring back the texture."
    ),
    "curry-indio": (
        "Batch cook: make four portions of curry sauce and rice. Cook 320g rice with 640ml water for 12 minutes, rest 10 minutes, and portion it into four containers. Cut chicken and carrot into bite-sized pieces, then cook the chicken with 20ml oil and spices for 5-6 minutes until sealed. "
        "Add carrot, 700g tomato sauce, 500ml beer, 210ml water, garlic, ginger, and 6g salt, then simmer 18-22 minutes until the chicken is cooked and the carrot softens. Lower the heat and stir in 400g yogurt for 2 minutes so it stays creamy. "
        "Taste for seasoning and portion the curry over the rice. Individual cook: no separate cooking is needed; reheat gently so the yogurt sauce does not split."
    ),
    "curry-japones": (
        "Batch cook: make four portions of curry and rice. Cook 320g rice with 640ml water for 12 minutes, rest 10 minutes, and portion it. Cut chicken, carrot, onion, and potato into similar sizes so they cook evenly. "
        "Simmer chicken and vegetables with 1160ml water/light stock for 18-22 minutes until tender, then dissolve the curry roux and stock cube into the pot. Add 20g honey only to balance bitterness, not to make it sweet. "
        "Simmer until thick, stir often so the roux does not stick, and portion with rice. Individual cook: no separate cooking is needed; reheat one portion with a splash of water."
    ),
    "noodles-pollo": (
        "Batch plan: this buys and preps four portions, but the actual noodle cooking should be individual because noodles get bad in the fridge. Batch prep: slice the chicken and vegetables, divide them into four raw/prepped portions, and mix 100ml soy sauce, 24g garlic, 20g ginger, 28g honey, 40ml vinegar, and 120ml water as a four-portion sauce. "
        "Individual cook: for each meal, cook 125g noodles fresh in about 500ml water for 3-5 minutes, cook one chicken portion with 5ml oil for 5-6 minutes, add one vegetable portion with a splash of water for 3 minutes, then add one sauce portion and toss for 1-2 minutes until glossy. "
        "Do not deep fry or fry the noodles aggressively. Store uncooked noodles dry and prepped components separately."
    ),
    "empanada-carne": (
        "Batch cook: make the whole empanada and cut it into four meal portions. Cook onion and pepper in 10ml olive oil for 6-8 minutes until soft, then add 500g ground meat and break it up completely for 8-10 minutes. Add tomato sauce, beer, garlic, and spices, then simmer 15-20 minutes until the filling is thick and not watery. "
        "Let the filling cool for 20 minutes so it does not melt the puff pastry. Heat the oven to 200C. Fill the pastry sheets, seal the edges, cut a few steam vents, and bake 25-30 minutes until crisp and browned. "
        "Rest 10 minutes before cutting, then portion into meal-sized pieces. Individual cook: no separate cooking is needed; reheat in the oven or air fryer at 180C for 8-10 minutes if possible."
    ),
    "empanada-pollo": (
        "Batch cook: make the whole empanada and cut it into four meal portions. Dice the chicken and cook it with onion in 10ml olive oil for 8-10 minutes until fully done. Add mushrooms and cook 5-7 minutes until their liquid evaporates, then stir in cream and reduce 4-5 minutes until the filling is thick. "
        "Cool the filling for 20 minutes before adding it to the puff pastry. Heat the oven to 200C. Fill, seal, vent, and bake 25-30 minutes until the pastry is deeply golden. "
        "Rest 10 minutes before slicing so the filling stays inside the portions. Individual cook: no separate cooking is needed; reheat gently at 180C for 8-10 minutes so the pastry crisps again."
    ),
    "empanada-atun": (
        "Batch cook: make the whole tuna empanada and cut it into four portions. Boil the eggs for 10 minutes, cool them in cold water for 5 minutes, peel them, and chop them. Drain the tuna well so the pastry does not become soggy. "
        "Mix tuna, egg, tomato sauce, onion, pepper, and seasoning into a thick filling. Heat the oven to 200C. Fill the puff pastry, seal the edges, cut steam vents, and bake 25-30 minutes until browned. "
        "Rest 10 minutes before cutting and portion with a vegetable side if the meal needs more volume. Individual cook: no separate cooking is needed; reheat at 180C for 8-10 minutes in a dry oven-style method."
    ),
    "sish-kebab": (
        "Batch prep: make the naan dough first. Mix warm water, dry yeast, and sugar; rest for 10 minutes, then add flour, yogurt, olive oil, salt, and baking powder. Knead 5-8 minutes until elastic, cover, and rise for 1 hour. "
        "Marinate the rumpsteak cubes with olive oil, lemon juice, garlic, cumin, paprika, salt, and black pepper while the dough rises. Toss halved potatoes with olive oil, lemon, oregano, salt, and pepper, then roast at 200C for about 40 minutes until tender and browned. "
        "Make the salad by whisking olive oil, lemon, vinegar, paprika, and salt, then macerating thin red onion for 15 minutes before adding cherry tomatoes and parsley. "
        "Individual cook: stretch one naan portion and cook it in a very hot dry pan 1-2 minutes per side, then brush with melted butter. Skewer one beef portion and grill close to maximum heat for 4-5 minutes per side. "
        "Plate warm naan with beef juices, potatoes on the side, and the tomato-red onion salad over the top. Batch cook the potatoes and salad components; cook naan and beef fresh per meal for best texture."
    ),
    "burrito": (
        "Batch cook: this is a six-wrap batch using the full wrap pack. Cook 250g rice with 500ml water and 3g salt for 12 minutes, then rest covered 10 minutes while the filling is prepared. Cook the ground chicken in a wide non-stick pan for 7-9 minutes, breaking it into small pieces, then season it with burrito spices and 2-3 tablespoons water so the seasoning coats the meat. "
        "Add diced onion and red pepper and cook 6-8 minutes until softened, then stir in the drained beans and warm them through for 2-3 minutes. Mash or slice the avocado and mix yogurt with lemon and a little seasoning for a quick sauce. "
        "Warm the wraps 15-20 seconds each so they fold without tearing. Divide rice, chicken-bean filling, avocado, yogurt sauce, and grated cheese across exactly six wraps. "
        "Fold the sides in, roll tightly, and toast each burrito seam-side down in a dry pan if you want structure without frying. Individual cook: no separate cooking is required, but re-toast one burrito dry when eating. Cool before storing so the wraps do not turn soggy."
    ),
    "pasta-pollo": (
        "Batch cook: make the chicken tomato sauce as one four-serving batch. Cut chicken into bite-sized pieces and cook it with 15ml olive oil for 6-8 minutes until browned and fully done. "
        "Add onion and mushrooms, cook 6-8 minutes until softened, then add tomato sauce, garlic, and spices. Simmer 12-15 minutes until the sauce is thick and portion it into four containers. "
        "Individual cook: pasta is best cooked fresh per meal; cook 100g pasta in about 625ml salted water for 9-11 minutes, reheat one sauce portion for 3-4 minutes, and loosen with pasta water. If needed, batch cook the pasta slightly underdone for convenience."
    ),
    "pizza": (
        "Batch cook: pizza is fully batch cooked as one tray and sliced into four meal portions. Dough: mix 500g flour, 325ml warm water, 7g dry yeast, 5g sugar, 10g salt, and 20ml olive oil. Knead 8-10 minutes until smooth, cover, and let it rise 60-90 minutes until puffy. "
        "Preheat the oven to 240C for at least 20 minutes. Cook the 300g chicken pieces with 10ml olive oil for 5-6 minutes before topping so the pizza bakes safely. "
        "Stretch the dough on one tray, spread 350g tomato sauce, then add chicken, mushrooms, pepper, oregano, and grated cheese. Bake at 240C for 12-16 minutes until the base is cooked through and the cheese is browned. "
        "Rest 5 minutes before slicing into four meal portions. Individual cook: no separate cooking is needed; reheat slices dry at 180C for 6-8 minutes so the base stays crisp."
    ),
    "pollo-papa-horno": (
        "Batch cook: cook the full oven tray and divide it into four meals. Heat the oven to 200C. Cut potatoes, onion, pepper, and tomatoes into even pieces and spread them in an oven tray. Add chicken, lemon juice, garlic, spices, 20ml olive oil, 120ml water, 8g salt, and 3g pepper so the tray does not dry out. "
        "Bake at 200C for 45-55 minutes until the potatoes are tender and the chicken reaches 74C inside, turning once halfway if needed. Rest for 5 minutes, spoon tray juices over the portions, and divide into four meals. Individual cook: no separate cooking is needed."
    ),
    "puchero": (
        "Batch cook: puchero is a full six-portion stew. Cut chicken, pork, potatoes, carrots, and onion into stew-sized pieces. Add them to a pot with beans, stock cube, garlic, spices, 8g salt, 3g pepper, and 1800ml water. "
        "Bring to a boil, lower to a gentle simmer, and cook 60-75 minutes until the meats are tender and the potatoes are cooked, topping up water only if the solids are no longer covered. Skim excess fat, adjust seasoning, and portion into six batch meals with a balanced amount of broth and solids. Individual cook: reheat one portion with broth for 4-6 minutes."
    ),
    "hamburguesa": (
        "Batch prep: season the ground meat with 8g salt, 3g pepper, garlic, and spices, then form five even 100g patties and store them separated. Batch cook the potato wedges with 20ml olive oil and spices at 210C for 35-40 minutes until tender and browned. "
        "Individual cook: cook one patty on a non-stick pan or grill over medium-high heat for 3-4 minutes per side, then rest 3 minutes. Warm one naan for 30-45 seconds per side, slice tomato and onion, and use yogurt as the sauce. "
        "Assemble with tomato, onion, cheese, and yogurt sauce right before eating so the bread does not become soggy."
    ),
}


def _unique_name(conn: sqlite3.Connection, table: str, row_id: str, name: str) -> str:
    base = name
    candidate = base
    suffix = 2
    if table == "ingredients":
        query = "SELECT 1 FROM ingredients WHERE name = ? AND id != ?"
    elif table == "recipes":
        query = "SELECT 1 FROM recipes WHERE name = ? AND id != ?"
    else:
        raise ValueError(f"Unsupported name table: {table}")
    while conn.execute(
        query,
        (candidate, row_id),
    ).fetchone():
        candidate = f"{base} ({suffix})"
        suffix += 1
    return candidate


def apply_english_name_cleanup(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT id, name FROM ingredients ORDER BY id").fetchall():
        old_name = str(row["name"])
        new_name = _unique_name(conn, "ingredients", str(row["id"]), translate_name(old_name, title=False))
        if new_name and new_name != old_name:
            conn.execute("UPDATE ingredients SET name = ? WHERE id = ?", (new_name, row["id"]))
            conn.execute(
                "INSERT OR IGNORE INTO ingredient_aliases (alias, ingredient_id) VALUES (?, ?)",
                (old_name.strip().lower(), row["id"]),
            )

    for row in conn.execute("SELECT id, name, procedure FROM recipes ORDER BY id").fetchall():
        old_name = str(row["name"])
        new_name = _unique_name(conn, "recipes", str(row["id"]), translate_name(old_name, title=True))
        if new_name and new_name != old_name:
            conn.execute("UPDATE recipes SET name = ? WHERE id = ?", (new_name, row["id"]))
        old_procedure = str(row["procedure"])
        new_procedure = translate_text(old_procedure)
        if new_procedure and new_procedure != old_procedure:
            conn.execute("UPDATE recipes SET procedure = ? WHERE id = ?", (new_procedure, row["id"]))

    for row in conn.execute("SELECT id, candidate_json, recipe_name FROM youtube_recipe_candidates").fetchall():
        data = json.loads(row["candidate_json"])
        data["name"] = translate_name(str(data.get("name", row["recipe_name"])), title=True)
        for ingredient in data.get("ingredients", []):
            if "name" in ingredient:
                ingredient["name"] = translate_name(str(ingredient["name"]), title=False)
        data["procedure"] = translate_text(str(data.get("procedure", "")))
        conn.execute(
            """
            UPDATE youtube_recipe_candidates
            SET recipe_name = ?, candidate_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (data["name"], json.dumps(data, ensure_ascii=False), row["id"]),
        )
    conn.commit()


def apply_english_labels(conn: sqlite3.Connection) -> None:
    for ingredient_id, name in INGREDIENT_NAMES.items():
        conn.execute("UPDATE ingredients SET name = ? WHERE id = ?", (name, ingredient_id))
    for recipe_id, name in RECIPE_NAMES.items():
        conn.execute("UPDATE recipes SET name = ? WHERE id = ?", (name, recipe_id))
    for recipe_id, procedure in RECIPE_PROCEDURES.items():
        conn.execute("UPDATE recipes SET procedure = ? WHERE id = ?", (procedure, recipe_id))
    conn.commit()
    current = conn.execute("SELECT value FROM settings WHERE key = 'english_cleanup_version'").fetchone()
    if current and current["value"] == ENGLISH_CLEANUP_VERSION:
        return
    apply_english_name_cleanup(conn)
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('english_cleanup_version', ?)",
        (ENGLISH_CLEANUP_VERSION,),
    )
    conn.commit()
