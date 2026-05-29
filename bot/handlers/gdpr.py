"""
NutreeCoach — Handler RGPD : vie privée, export, suppression
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models.database import db

router = Router()


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Exporter mes données", callback_data="privacy_export")
    kb.button(text="🗑️ Supprimer toutes mes données", callback_data="privacy_delete")
    kb.adjust(1)

    await message.answer(
        "🔒 <b>Vie privée et données</b>\n\n"
        "NutreeCoach traite tes données conformément au <b>RGPD</b> :\n\n"
        "📦 <b>Données collectées :</b>\n"
        "• Poids, mensurations, photos de progression\n"
        "• Repas loggés et habitudes alimentaires\n"
        "• Messages échangés avec le coach\n\n"
        "📍 <b>Hébergement :</b> Union Européenne\n"
        "⏳ <b>Conservation :</b> 12 mois après inactivité\n"
        "🔐 <b>Cryptage :</b> Données chiffrées au repos et en transit\n\n"
        '<i>Tu peux exporter ou supprimer toutes tes données à tout moment.</i>',
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "privacy_export")
async def export_data(callback: CallbackQuery):
    await callback.answer()

    user = await db.get_user_by_telegram(callback.from_user.id)
    if not user:
        return

    # Récupérer les données
    weights = await db.get_recent_weights(callback.from_user.id, days=365)
    meals = await db.get_today_meals(callback.from_user.id)

    # Construire le fichier
    lines = ["=== EXPORT NUTRICOACH ===\n"]
    lines.append(f"Utilisateur : {user.get('first_name')}")
    lines.append(f"Objectif : {user.get('goal')}")
    lines.append(f"Calories cibles : {user.get('daily_calories')}\n")

    lines.append("=== POIDS ===")
    for w in weights:
        lines.append(f"{w['measured_at']} : {w['weight_kg']} kg")

    lines.append("\n=== REPAS RÉCENTS ===")
    for m in meals:
        lines.append(f"{m['meal_type']} — {m['total_kcal']} kcal")

    text = "\n".join(lines)

    # Envoyer comme fichier texte via message
    await callback.message.answer(
        f"<b>📥 Voici tes données :</b>\n\n"
        f"<pre>{text[:3000]}</pre>\n\n"
        f"<i>Si tu veux un export complet, contacte l'administrateur.</i>"
    )


@router.callback_query(F.data == "privacy_delete")
async def delete_data_confirm(callback: CallbackQuery):
    await callback.answer()

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Oui, supprime tout", callback_data="privacy_delete_confirm")
    kb.button(text="❌ Non, je reste", callback_data="privacy_cancel")
    kb.adjust(1)

    await callback.message.edit_text(
        "⚠️ <b>Es-tu sûr de vouloir supprimer toutes tes données ?</b>\n\n"
        "Cette action est irréversible :\n"
        "• Ton profil et tes objectifs\n"
        "• Tout l'historique des repas\n"
        "• Les pesées et mensurations\n"
        "• Les conversations avec le coach\n\n"
        "<i>Tu pourras toujours recommencer avec /start</i>",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "privacy_delete_confirm")
async def delete_data_execute(callback: CallbackQuery):
    await callback.answer()

    async with db.pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE telegram_id = $1", callback.from_user.id
        )
        if user_id:
            await conn.execute("DELETE FROM coaching_log WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM daily_progress WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM meals WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM body_measurements WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM subscriptions WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)

    await callback.message.edit_text(
        "✅ <b>Toutes tes données ont été supprimées.</b>\n\n"
        "Si tu veux recommencer, fais /start\n"
        "Merci d'avoir utilisé NutreeCoach ! 🙏",
    )


@router.callback_query(F.data == "privacy_cancel")
async def delete_data_cancel(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("✅ Annulé. Tes données sont conservées.")
