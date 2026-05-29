"""
NutreeCoach — Handler coaching : conversation avec le profil Hermès
"""

import os
import httpx
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from models.database import db

router = Router()
HERMES_API = os.getenv("HERMES_API", "http://hermes-coach:8081")


class Coaching(StatesGroup):
    conversation = State()


# ── /coach ──────────────────────────────────────────────────

@router.message(Command("coach"))
async def cmd_coach(message: Message, state: FSMContext):
    user = await db.get_user_by_telegram(message.from_user.id)
    if not user or not user["gdpr_consent"]:
        await message.answer("ℹ️ Commence par /start pour t'inscrire !")
        return

    await message.answer(
        "💬 <b>Pose ta question au coach nutrition !</b>\n\n"
        "Par exemple :\n"
        "• <i>« Que manger ce soir avec ce qu'il me reste ? »</i>\n"
        "• <i>« J'ai craqué sur une pizza, c'est grave ? »</i>\n"
        "• <i>« Est-ce que je devrais augmenter mes protéines ? »</i>\n"
        "• <i>« Motive-moi un peu ! »</i>\n\n"
        "<i>Envoie ton message et je consulte le coach NutreeCoach !</i>"
    )
    await state.set_state(Coaching.conversation)


# ── Messages libres → coaching ─────────────────────────

@router.message(F.text, ~F.text.startswith("/"))
async def free_text_coaching(message: Message, state: FSMContext):
    user = await db.get_user_by_telegram(message.from_user.id)
    if not user or not user["gdpr_consent"]:
        return  # Ignorer les messages de non-inscrits

    # Préparer le contexte pour Hermès
    today = await db.get_today_summary(message.from_user.id)
    today_meals = await db.get_today_meals(message.from_user.id)
    weights = await db.get_recent_weights(message.from_user.id, days=14)

    # Construire le prompt pour le profil Hermès
    prompt = (
        f"[CONTEXTE UTILISATEUR]\n"
        f"Prénom: {user.get('first_name', 'Utilisateur')}\n"
        f"Objectif: {user.get('goal', 'non défini')}\n"
        f"Calories/jour cible: {user.get('daily_calories', 'non défini')}\n"
        f"Activité: {user.get('activity_level', 'non défini')}\n"
    )

    if today:
        prompt += (
            f"Calories aujourd'hui: {today['calories_consumed'] or 0} / {user.get('daily_calories', '?')}\n"
            f"Protéines: {today['protein_g'] or 0:.0f}g\n"
        )

    if today_meals:
        prompt += f"Repas aujourd'hui: {[m['meal_type'] for m in today_meals]}\n"

    if weights:
        prompt += f"Poids: {weights[0]['weight_kg']}kg (dernier relevé)\n"

    prompt += (
        f"\n[MESSAGE UTILISATEUR]\n{message.text}\n\n"
        f"Réponds en tant que NutreeCoach — bienveillant, scientifique, personnalisé. "
        f"Respecte les règles de sécurité (TCA, hors-sujet). "
        f"Réponds en français, en 2-3 phrases maximum."
    )

    # Envoyer au profil Hermès
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{HERMES_API}/chat",
                json={"message": prompt, "user_id": str(message.from_user.id)},
            )
            response.raise_for_status()
            coach_response = response.json().get("response", "")

        # Logger l'interaction
        await db.log_coaching(
            telegram_id=message.from_user.id,
            interaction_type="user_question",
            user_message=message.text,
            coach_response=coach_response,
        )

        await message.answer(coach_response, parse_mode="Markdown")

    except (httpx.RequestError, httpx.HTTPError) as e:
        await message.answer(
            "😅 Désolé, le coach nutrition est momentanément indisponible. "
            "Réessaie dans quelques instants !"
        )


# ── /today ──────────────────────────────────────────────────

@router.message(Command("today"))
async def cmd_today(message: Message):
    user = await db.get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("ℹ️ Commence par /start !")
        return

    today = await db.get_today_summary(message.from_user.id)
    meals = await db.get_today_meals(message.from_user.id)

    if not today:
        await message.answer("📊 Aucun repas loggé aujourd'hui. Utilise /log !")
        return

    goal_kcal = user.get("daily_calories") or 2000
    consumed = today["calories_consumed"] or 0
    remaining = max(0, goal_kcal - consumed)

    text = f"📊 <b>Résumé du jour</b>\n\n"
    text += f"🔥 <b>{consumed:.0f} / {goal_kcal} kcal</b> ({remaining:.0f} restantes)\n\n"
    text += f"🥩 Protéines : {today['protein_g'] or 0:.0f}g\n"
    text += f"🍚 Glucides : {today['carbs_g'] or 0:.0f}g\n"
    text += f"🥑 Lipides : {today['fat_g'] or 0:.0f}g\n\n"

    if meals:
        text += "🍽️ <b>Repas :</b>\n"
        for m in meals:
            text += f"• {m['meal_type']} — {m['total_kcal']:.0f} kcal\n"

    await message.answer(text)


# ── Callbacks des rappels ──────────────────────────────────

@router.callback_query(F.data == "remind_coach")
async def remind_coach_callback(callback_query, state: FSMContext):
    await cmd_coach(callback_query.message, state)
