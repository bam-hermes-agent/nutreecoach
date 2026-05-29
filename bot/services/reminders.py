"""
NutreeCoach — Planificateur de rappels quotidiens
"""

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def setup_scheduler(bot, db):
    """Configure les rappels quotidiens pour tous les utilisateurs."""
    scheduler = AsyncIOScheduler()

    # Rappel de pesée chaque matin à 8h (heure de Paris)
    @scheduler.scheduled_job(
        CronTrigger(hour=8, minute=0, timezone=ZoneInfo("Europe/Paris"))
    )
    async def morning_weigh_in():
        logger.info("Running morning weigh-in reminder...")
        users = await db.get_users_pending_weigh_in()
        logger.info(f"Found {len(users)} users pending weigh-in")

        from handlers.weight import send_weigh_in_reminder

        for user in users:
            try:
                await send_weigh_in_reminder(
                    bot=bot,
                    telegram_id=user["telegram_id"],
                    first_name=user["first_name"] or "là",
                )
                logger.info(f"  → Reminder sent to user {user['telegram_id']}")
            except Exception as e:
                logger.warning(f"  → Failed to send reminder to {user['telegram_id']}: {e}")

    # Rappel repas du midi à 12h30
    @scheduler.scheduled_job(
        CronTrigger(hour=12, minute=30, timezone=ZoneInfo("Europe/Paris"))
    )
    async def lunch_reminder():
        logger.info("Running lunch reminder...")
        await _send_tip_to_active_users(bot, db, "🍽️ C'est l'heure du déjeuner ! Pense à logger ton repas avec /log")

    # Rappel dîner à 19h
    @scheduler.scheduled_job(
        CronTrigger(hour=19, minute=0, timezone=ZoneInfo("Europe/Paris"))
    )
    async def dinner_reminder():
        logger.info("Running dinner reminder...")
        await _send_tip_to_active_users(bot, db, "🥗 Pense à ton dîner ! Un repas équilibré, c'est la clé. /log")

    # Bilan de fin de journée à 21h
    @scheduler.scheduled_job(
        CronTrigger(hour=21, minute=0, timezone=ZoneInfo("Europe/Paris"))
    )
    async def evening_summary():
        logger.info("Running evening summary...")
        users = await db.get_users_pending_weigh_in()
        for user in users:
            try:
                await bot.send_message(
                    user["telegram_id"],
                    "🌙 <b>Bilan de la journée</b>\n\n"
                    "N'oublie pas de faire le point avec /today\n"
                    "Et si tu as besoin d'un conseil, je suis là : /coach 💬"
                )
            except Exception as e:
                logger.warning(f"Evening summary failed for {user['telegram_id']}: {e}")

    scheduler.start()
    logger.info("Scheduler started with reminders (8h, 12h30, 19h, 21h)")


async def _send_tip_to_active_users(bot, db, message: str):
    """Envoie un message aux utilisateurs premium uniquement."""
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT telegram_id, first_name FROM users
                   WHERE gdpr_consent = TRUE
                   LIMIT 50"""
            )
            for row in rows:
                try:
                    await bot.send_message(row["telegram_id"], message)
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Failed to send bulk message: {e}")
