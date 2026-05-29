"""
NutreeCoach — Handler repas : log par texte, code-barres
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from models.database import db
from services.food_db import search_food, search_by_barcode

router = Router()


class LogMeal(StatesGroup):
    waiting_for_food = State()
    waiting_for_quantity = State()
    waiting_for_meal_type = State()


MEAL_TYPES = {
    "breakfast": "🥐 Petit-déjeuner",
    "lunch": "🍝 Déjeuner",
    "dinner": "🥗 Dîner",
    "snack": "🍪 Snack",
}


# ── /log ────────────────────────────────────────────────────

@router.message(Command("log"))
async def cmd_log(message: Message, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 Texte (ex: 'riz poulet brocolis')", callback_data="log_text")
    kb.button(text="📟 Scanner un code-barres", callback_data="log_barcode")
    kb.adjust(1)

    await message.answer(
        "🍽️ <b>Logger un repas</b>\n\n"
        "Comment veux-tu le faire ?",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "log_text")
async def log_by_text(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📝 Envoie ce que tu as mangé !\n\n"
        "<i>Exemple : 150g de riz, 200g de poulet, brocolis</i>\n"
        "<i>Ou simplement : pizza, salade, pomme</i>"
    )
    await state.set_state(LogMeal.waiting_for_food)


@router.callback_query(F.data == "log_barcode")
async def log_by_barcode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📟 Envoie la <b>photo du code-barres</b> du produit !\n\n"
        "<i>Ou tape le numéro du code-barres si tu l'as</i>"
    )
    await state.set_state(LogMeal.waiting_for_food)
    await state.update_data(mode="barcode")


# ── Réception du texte / code-barres ──────────────────────

@router.message(LogMeal.waiting_for_food, F.text)
async def food_text_received(message: Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get("mode", "text")

    if mode == "barcode":
        # Recherche par code-barres
        product = await search_by_barcode(message.text.strip())
        if product:
            await state.update_data(
                selected_food=product,
                quantity=100  # 100g par défaut
            )
            await state.set_state(LogMeal.waiting_for_quantity)
            await ask_quantity(message, product["name"], product["kcal_per_100g"])
            return
        else:
            await message.answer("❌ Produit introuvable avec ce code-barres. Essaie le mode texte !")
            return

    # Mode texte : parser les aliments individuels
    import re
    lines = re.split(r'[,;\n\r]+', message.text.strip())
    parsed_items = []
    for line in lines:
        line = line.strip().lstrip('-*•').strip()
        if not line:
            continue
        m = re.match(r'(\d+)\s*g\s*(?:de|d\'|)\s*(.+)', line)
        if m:
            parsed_items.append({"qty": int(m.group(1)), "name": m.group(2).strip()})
        else:
            parsed_items.append({"qty": 100, "name": line})

    if not parsed_items:
        await message.answer("Je n'ai rien compris. Essaie : `300g poulet, 200g riz`")
        return

    # Chercher chaque aliment un par un
    meal_foods = []
    not_found = []
    for item in parsed_items:
        results = await search_food(item["name"])
        if results:
            food = results[0]
            qty = item["qty"]
            meal_foods.append({
                "name": food["name"],
                "grams": qty,
                "kcal": round(food["kcal_per_100g"] * qty / 100, 1),
                "protein_g": round(food.get("protein_per_100g", 0) * qty / 100, 1),
                "carbs_g": round(food.get("carbs_per_100g", 0) * qty / 100, 1),
                "fat_g": round(food.get("fat_per_100g", 0) * qty / 100, 1),
                "barcode": food.get("barcode"),
            })
        else:
            not_found.append(item["name"])

    if not meal_foods:
        await message.answer(
            "😕 Je n'ai trouvé aucun de ces aliments. "
            "Peux-tu être plus précis ? (ex: '150g riz blanc, 200g poulet')"
        )
        return

    # Résumé des aliments trouvés
    total_kcal = sum(f["kcal"] for f in meal_foods)
    total_protein = sum(f["protein_g"] for f in meal_foods)
    total_carbs = sum(f["carbs_g"] for f in meal_foods)
    total_fat = sum(f["fat_g"] for f in meal_foods)

    summary = "✅ <b>Aliments reconnus :</b>\n\n"
    for f in meal_foods:
        summary += f"• {f['name']} — {f['grams']}g → {f['kcal']} kcal\n"
    if not_found:
        summary += f"\n⚠️ Non trouvé(s) : {', '.join(not_found)}\n"
    summary += f"\n📊 <b>Total estimé :</b> {total_kcal:.0f} kcal | P:{total_protein:.0f}g G:{total_carbs:.0f}g L:{total_fat:.0f}g"

    await state.update_data(meal_foods=meal_foods)
    await state.set_state(LogMeal.waiting_for_meal_type)
    await ask_meal_type(message, state, summary)


@router.callback_query(F.data.startswith("food_"), LogMeal.waiting_for_food)
async def food_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    idx = int(callback.data.replace("food_", ""))
    data = await state.get_data()
    food = data["food_results"][idx]

    await state.update_data(selected_food=food)
    await state.set_state(LogMeal.waiting_for_quantity)
    await ask_quantity(callback.message, food["name"], food["kcal_per_100g"])


async def ask_quantity(message, food_name: str, kcal_per_100g: float):
    kb = InlineKeyboardBuilder()
    kb.button(text="100g (portion standard)", callback_data="qty_100")
    kb.button(text="200g (grosse portion)", callback_data="qty_200")
    kb.button(text="50g (petite portion)", callback_data="qty_50")
    kb.button(text="✏️ Autre quantité", callback_data="qty_custom")
    kb.adjust(1)

    await message.answer(
        f"🍽️ <b>{food_name}</b>\n"
        f"📊 {kcal_per_100g:.0f} kcal / 100g\n\n"
        f"Quelle quantité as-tu mangée ?",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("qty_"), LogMeal.waiting_for_quantity)
async def quantity_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    if callback.data == "qty_custom":
        await callback.message.edit_text("✏️ Envoie la quantité en grammes (ex: 150)")
        await state.set_state(LogMeal.waiting_for_quantity)
        return

    qty = int(callback.data.replace("qty_", ""))
    await state.update_data(quantity=qty)
    await state.set_state(LogMeal.waiting_for_meal_type)
    await ask_meal_type(callback.message, state)


@router.message(LogMeal.waiting_for_quantity, F.text, lambda m: m.text.lstrip('-').replace('.','',1).isdigit())
async def custom_quantity(message: Message, state: FSMContext):
    qty = int(message.text)
    await state.update_data(quantity=qty)
    await state.set_state(LogMeal.waiting_for_meal_type)
    await ask_meal_type(message, state)


async def ask_meal_type(message, state: FSMContext, summary: str = None):
    await state.set_state(LogMeal.waiting_for_meal_type)
    kb = InlineKeyboardBuilder()
    for key, label in MEAL_TYPES.items():
        kb.button(text=label, callback_data=f"mealtype_{key}")
    kb.adjust(2)

    text = "🍽️ <b>C'est quel type de repas ?</b>"
    if summary:
        text = summary + "\n\n🍽️ <b>C'est quel type de repas ?</b>"

    await message.answer(
        text,
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("mealtype_"), LogMeal.waiting_for_meal_type)
async def meal_type_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    meal_type = callback.data.replace("mealtype_", "")
    data = await state.get_data()

    # Support multi-aliments (meal_foods) ET mono-aliment (selected_food)
    foods = data.get("meal_foods")
    if foods:
        total_kcal = sum(f["kcal"] for f in foods)
    else:
        food = data["selected_food"]
        qty = data["quantity"]
        total_kcal = round(food["kcal_per_100g"] * qty / 100, 1)
        foods = [{
            "name": food["name"],
            "grams": qty,
            "kcal": total_kcal,
            "protein_g": round(food.get("protein_per_100g", 0) * qty / 100, 1),
            "carbs_g": round(food.get("carbs_per_100g", 0) * qty / 100, 1),
            "fat_g": round(food.get("fat_per_100g", 0) * qty / 100, 1),
            "barcode": food.get("barcode"),
        }]

    await db.log_meal(
        telegram_id=callback.from_user.id,
        meal_type=meal_type,
        foods=foods,
        total_kcal=round(total_kcal, 1),
    )

    today = await db.get_today_summary(callback.from_user.id)
    remaining = max(0, (data.get("daily_goal") or 2000) - (today["calories_consumed"] or 0))

    detail = "\n".join(f"• {f['name']} — {f['grams']}g → {f['kcal']} kcal"
                       for f in foods)
    await callback.message.edit_text(
        f"✅ <b>Repas loggé !</b> ({MEAL_TYPES[meal_type]})\n\n"
        f"{detail}\n\n"
        f"🔥 <b>Reste aujourd'hui :</b> {remaining:.0f} kcal\n\n"
        f"<i>Continue avec /log ou parle au coach /coach</i>"
    )

    await state.clear()
