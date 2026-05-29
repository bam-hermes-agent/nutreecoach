"""
NutreeCoach — Handler admin et stats (pour le propriétaire du bot)
"""

import os
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from models.database import db

router = Router()

# ID Telegram du propriétaire (toi, Manu)
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "8748903061"))


def is_admin(message: Message) -> bool:
    return message.from_user.id == ADMIN_ID


@router.message(Command("stats"), F.from_user.id == ADMIN_ID)
async def cmd_stats(message: Message):
    async with db.pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        active_today = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE last_active_at >= NOW() - INTERVAL '24 hours'"
        )
        meals_today = await conn.fetchval(
            "SELECT COUNT(*) FROM meals WHERE meal_date = CURRENT_DATE"
        )
        premium_users = await conn.fetchval(
            "SELECT COUNT(*) FROM subscriptions WHERE is_active = TRUE"
        )
        weigh_ins_today = await conn.fetchval(
            "SELECT COUNT(*) FROM body_measurements WHERE measured_at = CURRENT_DATE"
        )

    await message.answer(
        f"📊 <b>Statistiques NutreeCoach</b>\n\n"
        f"👥 Utilisateurs total : <b>{total_users}</b>\n"
        f"📱 Actifs aujourd'hui : <b>{active_today}</b>\n"
        f"🍽️ Repas loggés aujourd'hui : <b>{meals_today}</b>\n"
        f"⭐ Abonnés Premium : <b>{premium_users}</b>\n"
        f"⚖️ Pesées aujourd'hui : <b>{weigh_ins_today}</b>"
    )


@router.message(Command("broadcast"), F.from_user.id == ADMIN_ID)
async def cmd_broadcast(message: Message):
    # Usage: /broadcast Votre message ici
    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer("Utilisation : /broadcast Votre message")
        return

    async with db.pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT telegram_id FROM users WHERE gdpr_consent = TRUE"
        )

    sent = 0
    failed = 0
    for user in users:
        try:
            await message.bot.send_message(user["telegram_id"], text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"✅ Diffusion terminée : {sent} envoyés, {failed} échecs")
