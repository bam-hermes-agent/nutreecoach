"""
NutreeCoach — Handler abonnements via Telegram Stars
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

from models.database import db

router = Router()

# Prix en Telegram Stars (XTR)
PLANS = {
    "monthly": {"stars": 500, "days": 30, "label": "1 mois Premium"},
    "quarterly": {"stars": 1200, "days": 90, "label": "3 mois Premium"},
    "yearly": {"stars": 4000, "days": 365, "label": "1 an Premium (best value ✨)"},
}


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    user = await db.get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("ℹ️ Commence par /start !")
        return

    # Vérifier si déjà premium
    if user.get("subscription_tier") == "premium":
        valid_until = user.get("subscription_until")
        if valid_until and valid_until > datetime.now():
            await message.answer(
                f"⭐ Tu es déjà <b>Premium</b> !\n"
                f"Valable jusqu'au {valid_until.strftime('%d/%m/%Y')}.\n\n"
                f"Merci de ton soutien ! 🙏"
            )
            return

    kb = InlineKeyboardBuilder()
    for key, plan in PLANS.items():
        kb.button(
            text=f"{plan['label']} — {plan['stars']} ⭐",
            callback_data=f"sub_{key}",
        )
    kb.adjust(1)

    await message.answer(
        "⭐ <b>NutreeCoach Premium</b>\n\n"
        "Passe à Premium et débloque :\n"
        "🧠 <b>Coaching IA illimité</b> — conseils personnalisés avec le coach\n"
        "📸 <b>Reconnaissance photo</b> — prends une photo de ton assiette\n"
        "⚡ <b>Rappels proactifs</b> — coaching quotidien personnalisé\n"
        "📊 <b>Analytiques avancées</b> — tendances, graphiques\n\n"
        "Paiement sécurisé via <b>Telegram Stars</b> ⭐",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("sub_"))
async def plan_selected(callback):
    await callback.answer()
    plan_key = callback.data.replace("sub_", "")
    plan = PLANS[plan_key]

    prices = [LabeledPrice(label=plan["label"], amount=plan["stars"])]

    await callback.message.answer_invoice(
        title="NutreeCoach Premium",
        description=f"{plan['label']} — coaching nutrition illimité",
        payload=f"{plan_key}_{callback.from_user.id}",
        provider_token="",  # Vide pour Telegram Stars
        currency="XTR",
        prices=prices,
    )


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def payment_success(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    plan_key = payload.split("_")[0]
    plan = PLANS[plan_key]

    expires_at = datetime.now() + timedelta(days=plan["days"])

    await db.create_subscription(
        telegram_id=message.from_user.id,
        tier="premium",
        stars_amount=payment.total_amount,
        telegram_payment_id=payment.telegram_payment_charge_id,
        expires_at=expires_at,
    )

    await message.answer(
        f"✅ <b>Merci !</b> Tu es maintenant <b>Premium</b> ⭐\n\n"
        f"Durée : {plan['label']}\n"
        f"🎉 Toutes les fonctionnalités sont débloquées !\n\n"
        f"💬 /coach — Parle au coach"
    )
