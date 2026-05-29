"""
NutreeCoach — Point d'entrée du bot Telegram
aiogram 3.x — polling mode
"""

import os
import logging
import asyncio
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.client.default import DefaultBotProperties

from models.database import db
from handlers import start, meals, weight, coaching, subscription, admin, sos
from services.reminders import setup_scheduler

# ── Configuration ─────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Initialisation ────────────────────────────────────────
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ── Enregistrement des handlers ───────────────────────────
dp.include_router(start.router)
dp.include_router(meals.router)
dp.include_router(weight.router)
dp.include_router(coaching.router)
dp.include_router(subscription.router)
dp.include_router(admin.router)
dp.include_router(sos.router)


async def on_startup():
    """Actions au démarrage : DB + men commands + reminders."""
    await db.connect()

    # Commands visibles dans le menu Telegram
    commands = [
        BotCommand(command="start", description="🏁 Démarrer le coaching"),
        BotCommand(command="log", description="🍽️ Logger un repas"),
        BotCommand(command="pesee", description="⚖️ Enregistrer mon poids"),
        BotCommand(command="today", description="📊 Résumé de ma journée"),
        BotCommand(command="coach", description="💬 Parler au coach"),
        BotCommand(command="subscribe", description="⭐ Devenir premium"),
        BotCommand(command="privacy", description="🔒 Données et RGPD"),
        BotCommand(command="delete", description="🗑️ Supprimer mes données"),
        BotCommand(command="sos", description="🆘 Au secours ! J'ai besoin d'aide"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

    logger.info("Commands registered — starting polling")

    # Planifier les rappels quotidiens
    setup_scheduler(bot, db)


async def on_shutdown():
    """Nettoyage à l'arrêt."""
    await db.close()


async def main():
    """Lance le bot en mode polling."""
    await on_startup()
    try:
        logger.info("Starting polling...")
        await dp.start_polling(bot)
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
