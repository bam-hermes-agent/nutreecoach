"""
NutreeCoach — Handler pesée quotidienne
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from models.database import db

router = Router()


class WeighIn(StatesGroup):
    waiting_for_weight = State()


@router.message(Command("pesee"))
async def cmd_pesee(message: Message, state: FSMContext):
    today_weight = await db.has_weighed_today(message.from_user.id)
    last_weights = await db.get_recent_weights(message.from_user.id, days=7)

    text = "⚖️ <b>Pesée du jour</b>\n\n"

    if today_weight:
        text += "✅ Tu t'es déjà pesé aujourd'hui ! Tu peux mettre à jour.\n\n"
    else:
        text += "Envoie ton poids en kg.\n\n"

    if last_weights:
        text += "<b>⬇️ Derniers poids :</b>\n"
        for w in last_weights[:5]:
            text += f"• {w['measured_at']} : {w['weight_kg']} kg\n"

    # Tendances
    if len(last_weights) >= 3:
        recent = [w["weight_kg"] for w in last_weights[:7] if w["weight_kg"]]
        if len(recent) >= 3:
            avg = sum(recent) / len(recent)
            if recent[0] < recent[-1]:
                text += f"\n📈 <b>Tendance :</b> +{avg - recent[-1]:.1f} kg sur les 7 derniers jours"
            elif recent[0] > recent[-1]:
                text += f"\n📉 <b>Tendance :</b> -{recent[-1] - avg:.1f} kg sur les 7 derniers jours"
            else:
                text += "\n📊 <b>Tendance :</b> Stable"

    await message.answer(
        text + "\n\n<i>Ton poids varie naturellement (hydratation, cycle, repas). "
        "L'important c'est la tendance sur 14 jours.</i>"
    )
    await state.set_state(WeighIn.waiting_for_weight)


@router.message(WeighIn.waiting_for_weight, F.text)
async def weight_received(message: Message, state: FSMContext):
    import re
    numbers = re.findall(r"\d+[\.,]?\d*", message.text)
    if not numbers:
        await message.answer("Envoie un nombre valide, comme 72.5 ou 65")
        return

    weight = float(numbers[0].replace(",", "."))
    if weight < 30 or weight > 350:
        await message.answer("😅 Ce poids semble invraisemblable. Tu es sûr ?")
        return

    await db.log_weight(message.from_user.id, weight)

    # Comparaison avec la veille
    last_weights = await db.get_recent_weights(message.from_user.id, days=3)
    diff = ""
    if len(last_weights) >= 2:
        yesterday = last_weights[1]["weight_kg"]
        change = weight - yesterday
        if abs(change) < 0.2:
            diff = "Stable par rapport à hier. 👍"
        elif change > 0:
            diff = f"+{change:.1f} kg par rapport à hier. Normal — ça peut être l'hydratation !"
        else:
            diff = f"{change:.1f} kg par rapport à hier. Bien ! 📉"

    await message.answer(
        f"✅ <b>Pesée enregistrée :</b> {weight} kg\n"
        f"{diff}\n\n"
        f"📏 <i>Si tu as pris tes mensurations, n'oublie pas de les noter — "
        f"le poids ne dit pas tout ! Le muscle pèse plus lourd que le gras 💪</i>"
    )
    await state.clear()


# ── Rappel proactif (appelé par le scheduler) ──────────────

async def send_weigh_in_reminder(bot, telegram_id: int, first_name: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="⚖️ Me peser maintenant", callback_data="remind_pesee")
    kb.button(text="💬 Parler au coach", callback_data="remind_coach")
    kb.adjust(1)

    await bot.send_message(
        telegram_id,
        f"🌅 Bonjour {first_name} !\n\n"
        "C'est l'heure de ta pesée du jour ! ⚖️\n"
        "<i>Pèse-toi à jeun, après être allé aux toilettes, "
        "dans les mêmes conditions chaque jour pour une mesure fiable.</i>\n\n"
        "📸 <i>Et si tu peux, prends une photo dans les mêmes conditions — "
        "c'est encore plus parlant que le chiffre sur la balance !</i>",
        reply_markup=kb.as_markup(),
    )
