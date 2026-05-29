"""
NutreeCoach — Modèles et accès base de données (PostgreSQL async)
"""

import os
import asyncpg
from datetime import date, datetime
from typing import Optional

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nutricoach:***@localhost:5432/nutricoach")


class Database:
    """Connexion PostgreSQL avec pool de connexions."""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

    async def close(self):
        if self.pool:
            await self.pool.close()

    # ── Utilisateurs ──────────────────────────────────────

    async def get_user_by_telegram(self, telegram_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1", telegram_id
            )
            return dict(row) if row else None

    async def create_user(self, telegram_id: int, username: str = None,
                          first_name: str = None) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO users (telegram_id, username, first_name)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (telegram_id)
                   DO UPDATE SET username = $2, first_name = $3
                   RETURNING *""",
                telegram_id, username, first_name,
            )
            return dict(row)

    async def update_user_goal(self, telegram_id: int, **kwargs):
        cols = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
        vals = list(kwargs.values())
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE users SET {cols}, updated_at = NOW() WHERE telegram_id = $1",
                telegram_id, *vals,
            )

    async def set_gdpr_consent(self, telegram_id: int, consent: bool):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """UPDATE users SET gdpr_consent = $2, gdpr_consent_date = NOW()
                   WHERE telegram_id = $1""",
                telegram_id, consent,
            )

    # ── Poids et mensurations ─────────────────────────────

    async def log_weight(self, telegram_id: int, weight_kg: float) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO body_measurements (user_id, measured_at, weight_kg)
                   VALUES (
                       (SELECT id FROM users WHERE telegram_id = $1),
                       CURRENT_DATE, $2
                   )
                   ON CONFLICT (user_id, measured_at)
                   DO UPDATE SET weight_kg = $2
                   RETURNING *""",
                telegram_id, weight_kg,
            )
            return dict(row)

    async def get_recent_weights(self, telegram_id: int, days: int = 14) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT measured_at, weight_kg
                   FROM body_measurements
                   WHERE user_id = (SELECT id FROM users WHERE telegram_id = $1)
                     AND weight_kg IS NOT NULL
                     AND measured_at >= CURRENT_DATE - $2::integer
                   ORDER BY measured_at DESC""",
                telegram_id, days,
            )
            return [dict(r) for r in rows]

    async def has_weighed_today(self, telegram_id: int) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT 1 FROM body_measurements
                   WHERE user_id = (SELECT id FROM users WHERE telegram_id = $1)
                     AND measured_at = CURRENT_DATE
                     AND weight_kg IS NOT NULL""",
                telegram_id,
            )
            return row is not None

    # ── Repas ─────────────────────────────────────────────

    async def log_meal(self, telegram_id: int, meal_type: str,
                       foods: list, total_kcal: float,
                       source: str = "manual") -> dict:
        async with self.pool.acquire() as conn:
            total_protein = sum(f.get("protein_g", 0) for f in foods)
            total_carbs = sum(f.get("carbs_g", 0) for f in foods)
            total_fat = sum(f.get("fat_g", 0) for f in foods)

            row = await conn.fetchrow(
                """INSERT INTO meals (user_id, meal_type, source, foods,
                                     total_kcal, total_protein, total_carbs, total_fat)
                   VALUES (
                       (SELECT id FROM users WHERE telegram_id = $1),
                       $2, $3, $4::jsonb, $5, $6, $7, $8
                   ) RETURNING *""",
                telegram_id, meal_type, source,
                asyncpg.Json(foods),
                total_kcal, total_protein, total_carbs, total_fat,
            )

            # Mettre à jour le daily_progress
            await conn.execute(
                """INSERT INTO daily_progress (user_id, date, calories_consumed,
                                               protein_g, carbs_g, fat_g, meal_count)
                   VALUES (
                       (SELECT id FROM users WHERE telegram_id = $1),
                       CURRENT_DATE, $2, $3, $4, $5, 1
                   )
                   ON CONFLICT (user_id, date)
                   DO UPDATE SET
                       calories_consumed = daily_progress.calories_consumed + $2,
                       protein_g = daily_progress.protein_g + $3,
                       carbs_g = daily_progress.carbs_g + $4,
                       fat_g = daily_progress.fat_g + $5,
                       meal_count = daily_progress.meal_count + 1""",
                telegram_id, total_kcal, total_protein, total_carbs, total_fat,
            )

            return dict(row)

    async def get_today_meals(self, telegram_id: int) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT meal_type, foods, total_kcal, total_protein,
                          total_carbs, total_fat, logged_at
                   FROM meals
                   WHERE user_id = (SELECT id FROM users WHERE telegram_id = $1)
                     AND meal_date = CURRENT_DATE
                   ORDER BY logged_at""",
                telegram_id,
            )
            return [dict(r) for r in rows]

    async def get_today_summary(self, telegram_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT dp.*
                   FROM daily_progress dp
                   JOIN users u ON u.id = dp.user_id
                   WHERE u.telegram_id = $1 AND dp.date = CURRENT_DATE""",
                telegram_id,
            )
            return dict(row) if row else None

    # ── Coaching ──────────────────────────────────────────

    async def log_coaching(self, telegram_id: int, interaction_type: str,
                           user_message: str, coach_response: str,
                           tokens_used: int = 0, safety_flagged: bool = False):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO coaching_log
                   (user_id, interaction_type, user_message, coach_response,
                    tokens_used, safety_flagged)
                   VALUES (
                       (SELECT id FROM users WHERE telegram_id = $1),
                       $2, $3, $4, $5, $6
                   )""",
                telegram_id, interaction_type, user_message,
                coach_response, tokens_used, safety_flagged,
            )

    # ── Cache alimentaire ─────────────────────────────────

    async def get_food_by_barcode(self, barcode: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM food_cache WHERE barcode = $1", barcode
            )
            return dict(row) if row else None

    async def cache_food(self, barcode: str, name: str, brand: str,
                         kcal: float, protein: float, carbs: float, fat: float,
                         source: str = "openfoodfacts"):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO food_cache (barcode, name, brand,
                           kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g,
                           source)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   ON CONFLICT (barcode, source)
                   DO UPDATE SET last_updated = NOW()""",
                barcode, name, brand, kcal, protein, carbs, fat, source,
            )

    # ── Abonnement ────────────────────────────────────────

    async def has_active_subscription(self, telegram_id: int) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT 1 FROM subscriptions s
                   JOIN users u ON u.id = s.user_id
                   WHERE u.telegram_id = $1
                     AND s.is_active = TRUE
                     AND (s.expires_at IS NULL OR s.expires_at > NOW())""",
                telegram_id,
            )
            return row is not None

    async def create_subscription(self, telegram_id: int, tier: str,
                                  stars_amount: int, telegram_payment_id: str,
                                  expires_at=None):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO subscriptions
                   (user_id, tier, stars_amount, telegram_payment_id, expires_at)
                   VALUES (
                       (SELECT id FROM users WHERE telegram_id = $1),
                       $2, $3, $4, $5
                   )""",
                telegram_id, tier, stars_amount, telegram_payment_id, expires_at,
            )

    # ── Rappels ───────────────────────────────────────────

    async def get_users_pending_weigh_in(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM users_pending_weigh_in")
            return [dict(r) for r in rows]


# Instance globale
db = Database()
