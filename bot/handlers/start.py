"""
NutreeCoach — Handler /start : onboarding, consentement RGPD, objectifs
"""

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from models.database import db

router = Router()


class Onboarding(StatesGroup):
    ask_gdpr = State()
    ask_goal = State()
    ask_stats = State()
    ask_activity = State()
    done = State()


# ── /start ──────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user = await db.get_user_by_telegram(message.from_user.id)

    if user and user["gdpr_consent"]:
        # Déjà inscrit → tableau de bord
        await show_dashboard(message, user)
        return

    # Nouvel utilisateur → consentement RGPD
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ J'accepte — je commence !", callback_data="gdpr_accept")
    kb.button(text="🔒 Politique de confidentialité", callback_data="gdpr_policy")
    kb.adjust(1)

    await message.answer(
        "👋 <b>Bienvenue sur NutreeCoach !</b>\n\n"
        "Je suis ton coach nutrition personnel. Je vais t'aider à :\n"
        "🥗 Suivre ton alimentation\n"
        "⚖️ Atteindre tes objectifs de poids\n"
        "💪 Améliorer ta composition corporelle\n"
        "🧠 Avec des conseils scientifiquement fondés\n\n"
        "Avant de commencer, j'ai besoin de ton accord "
        "pour collecter et traiter tes données (poids, repas, mensurations) "
        "sur des serveurs situés en Union Européenne.\n\n"
        "<i>Tu peux à tout moment supprimer toutes tes données avec /delete.</i>",
        reply_markup=kb.as_markup(),
    )
    await state.set_state(Onboarding.ask_gdpr)


@router.callback_query(F.data == "gdpr_accept")
async def gdpr_accepted(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    # Créer l'utilisateur + consentement
    user = await db.create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    await db.set_gdpr_consent(callback.from_user.id, True)

    # Choisir l'objectif
    kb = InlineKeyboardBuilder()
    kb.button(text="🏋️ Perdre du poids", callback_data="goal_weight_loss")
    kb.button(text="💪 Prendre du muscle", callback_data="goal_muscle_gain")
    kb.button(text="🔄 Recomposition", callback_data="goal_recomposition")
    kb.button(text="🌿 Mieux manger (sans objectif poids)", callback_data="goal_health")
    kb.adjust(1)

    await callback.message.edit_text(
        "✅ <b>Merci !</b> Tes données sont protégées.\n\n"
        "🎯 <b>Quel est ton objectif principal ?</b>",
        reply_markup=kb.as_markup(),
    )
    await state.set_state(Onboarding.ask_goal)


@router.callback_query(F.data.startswith("goal_"))
async def goal_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    goal_map = {
        "goal_weight_loss": "weight_loss",
        "goal_muscle_gain": "muscle_gain",
        "goal_recomposition": "recomposition",
        "goal_health": "general_health",
    }
    goal = goal_map[callback.data]

    await db.update_user_goal(callback.from_user.id, goal=goal)
    await state.update_data(goal=goal)

    # Demander les stats physiques
    await callback.message.edit_text(
        "📏 <b>Quelques chiffres pour personnaliser ton suivi</b>\n\n"
        "Envoie-moi :\n"
        "• Taille (cm)\n"
        "• Poids actuel (kg)\n"
        "• Âge\n\n"
        "<i>Exemple : 175 cm, 80 kg, 30 ans</i>",
    )
    await state.set_state(Onboarding.ask_stats)


@router.message(Onboarding.ask_stats, F.text)
async def stats_received(message: Message, state: FSMContext):
    import re
    numbers = re.findall(r"\d+[\.,]?\d*", message.text)
    if len(numbers) < 2:
        await message.answer("Je n'ai pas bien compris. Donne-moi taille, poids et âge. Exemple : 175 cm, 80 kg, 30 ans")
        return

    height = float(numbers[0].replace(",", "."))
    weight = float(numbers[1].replace(",", "."))
    age = int(float(numbers[2])) if len(numbers) > 2 else 30

    await db.update_user_goal(
        message.from_user.id,
        height_cm=height,
        target_weight=weight,
    )
    await state.update_data(weight=weight, height=height, age=age)

    # Niveau d'activité
    kb = InlineKeyboardBuilder()
    kb.button(text="🛋️ Sédentaire (peu d'exercice)", callback_data="activity_sedentary")
    kb.button(text="🚶 Léger (1-2j/sem)", callback_data="activity_light")
    kb.button(text="🏃 Modéré (3-4j/sem)", callback_data="activity_moderate")
    kb.button(text="💪 Actif (5-6j/sem)", callback_data="activity_active")
    kb.button(text="🏋️ Très actif (tous les jours)", callback_data="activity_very_active")
    kb.adjust(1)

    await message.answer(
        "🏃 <b>Quel est ton niveau d'activité physique ?</b>",
        reply_markup=kb.as_markup(),
    )
    await state.set_state(Onboarding.ask_activity)


@router.callback_query(F.data.startswith("activity_"))
async def activity_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    activity = callback.data.replace("activity_", "")
    data = await state.get_data()

    await db.update_user_goal(callback.from_user.id, activity_level=activity)

    # Calculer les calories cibles
    bmr = 10 * data["weight"] + 6.25 * data["height"] - 5 * data["age"]
    bmr += 5  # homme par défaut (on améliorera avec le sexe plus tard)

    activity_mult = {
        "sedentary": 1.2, "light": 1.375, "moderate": 1.55,
        "active": 1.725, "very_active": 1.9,
    }
    tdee = bmr * activity_mult[activity]

    goal = data.get("goal", "weight_loss")
    if goal == "weight_loss":
        daily_cal = int(tdee - 400)
    elif goal == "muscle_gain":
        daily_cal = int(tdee + 300)
    elif goal == "recomposition":
        daily_cal = int(tdee - 200)
    else:
        daily_cal = int(tdee)

    protein = round(data["weight"] * 2.0)
    fats = round(daily_cal * 0.25 / 9)
    carbs_cal = daily_cal - (protein * 4 + fats * 9)
    carbs = max(0, round(carbs_cal / 4))

    await db.update_user_goal(
        callback.from_user.id,
        daily_calories=daily_cal,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fats,
    )

    await callback.message.edit_text(
        f"✅ <b>Parfait, {callback.from_user.first_name} !</b>\n\n"
        f"🎯 <b>Ton objectif :</b> {goal.replace('_', ' ').title()}\n"
        f"🔥 <b>Calories cibles :</b> {daily_cal} kcal/jour\n"
        f"🥩 <b>Protéines :</b> {protein}g\n"
        f"🍚 <b>Glucides :</b> {carbs}g\n"
        f"🥑 <b>Lipides :</b> {fats}g\n\n"
        f"<b>Prêt à commencer !</b> 🎉\n\n"
        f"📝 <i>Commence par logger ton prochain repas avec /log</i>\n"
        f"⚖️ <i>Pèse-toi demain matin avec /pesee</i>\n"
        f"💬 <i>Besoin d'un conseil ? /coach</i>",
    )
    await state.clear()


# ── Dashboard ───────────────────────────────────────────────

async def show_dashboard(message: Message, user: dict):
    today = await db.get_today_summary(message.from_user.id)
    weighed = await db.has_weighed_today(message.from_user.id)

    text = f"👋 <b>Bonjour {user['first_name']} !</b>\n\n"

    if today:
        remaining = (user.get("daily_calories") or 2000) - (today["calories_consumed"] or 0)
        text += (
            f"📊 <b>Aujourd'hui</b>\n"
            f"🍽️ {today['meal_count']} repas — {today['calories_consumed'] or 0} / {user.get('daily_calories') or '—'} kcal\n"
            f"🥩 {today['protein_g'] or 0:.0f}g protéines   "
            f"🍚 {today['carbs_g'] or 0:.0f}g glucides   "
            f"🥑 {today['fat_g'] or 0:.0f}g lipides\n"
        )
    else:
        text += "📊 <b>Aujourd'hui</b> — rien de loggé pour l'instant.\n"
        remaining = user.get("daily_calories") or 2000

    if weighed:
        text += "✅ <b>Pesée du jour</b> — faite ✅\n\n"
    else:
        text += "⚖️ <b>Pesée du jour</b> — pas encore ! Fais /pesee\n\n"

    text += (
        f"🔥 <b>Calories restantes :</b> {remaining:.0f} kcal\n\n"
        f"💬 /coach — Parler au coach\n"
        f"🍽️ /log — Logger un repas"
    )

    await message.answer(text)
