"""
NutreeCoach — Handler /sos : coup de pouce motivationnel
Quand l'utilisateur est prêt à craquer, il tape /sos
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from models.database import db

router = Router()


# ── Messages motivationnels ─────────────────────────────────

SOS_REASONS = {
    "craving": {
        "label": "🍕 J'ai envie de craquer",
        "message": (
            "C'est normal d'avoir des envies, vraiment ! 🫂\n\n"
            "👉 **Avant de céder, essaye ça :**\n"
            "• Bois un grand verre d'eau — la soif imite la faim\n"
            "• Attends 10 minutes — l'envie passe souvent toute seule\n"
            "• Respire 5 fois profondément 🧘\n\n"
            "Si tu « craques », ce n'est pas un échec. "
            "Un écart ne ruine pas une semaine d'efforts. "
            "L'important c'est la régularité, pas la perfection. 💪"
        ),
    },
    "demotive": {
        "label": "😞 Je suis démotivé(e)",
        "message": (
            "La motivation ça va, ça vient. Ce qui compte, "
            "c'est la discipline. 📈\n\n"
            "👉 **Rappelle-toi pourquoi tu as commencé :**\n"
            "• Tu n'es pas venu(e) jusqu'ici pour abandonner\n"
            "• Les résultats ne sont pas linéaires — c'est normal\n"
            "• Un petit pas chaque jour > une course un jour\n\n"
            "Regarde d'où tu viens, pas seulement où tu vas. "
            "Tu as déjà fait le plus dur : commencer. 🌟"
        ),
    },
    "hungry": {
        "label": "🍽️ J'ai faim entre les repas",
        "message": (
            "La faim entre les repas, ça s'anticipe ! 🥗\n\n"
            "👉 **Des pistes :**\n"
            "• Trop peu de protéines au dernier repas ? Augmente-les\n"
            "• Une collation saine : yaourt, fruit, amandes (15-20)\n"
            "• Parfois c'est la soif — un grand verre d'eau d'abord\n\n"
            "Ton corps s'habitue à un nouveau rythme. "
            "Donne-lui 1 à 2 semaines pour s'adapter. ⏳"
        ),
    },
    "plateau": {
        "label": "📉 Je stagne, ça ne bouge plus",
        "message": (
            "La stagnation, c'est frustrant mais c'est NORMAL. 📊\n\n"
            "👉 **Ce qui se passe :**\n"
            "• Ton corps s'adapte — c'est un bon signe\n"
            "• Les variations d'eau cachent la vraie perte de gras\n"
            "• Le muscle pèse plus lourd que le gras — tu changes de composition\n\n"
            "👉 **Actions possibles :**\n"
            "• Révise tes calories (ton poids a changé)\n"
            "• Change ton activité (marche, hiit, muscu)\n"
            "• Regarde tes mensurations, pas que la balance\n\n"
            "Patience. Les résultats durables prennent du temps. 🐢"
        ),
    },
    "party": {
        "label": "🎉 J'ai un événement / resto",
        "message": (
            "Vivre sa vie sociale, c'est essentiel ! 🥳\n\n"
            "👉 **Stratégies sans frustration :**\n"
            "• Avant de sortir : mange une pomme + 2 verres d'eau\n"
            "• Au resto : commence par une entrée légère\n"
            "• Bois de l'eau entre chaque verre d'alcool\n"
            "• Tu n'es pas obligé(e) de finir ton assiette\n\n"
            "Un repas ne définit pas ta semaine. "
            "Profite, reprends le fil demain. Pas de culpabilité. ✨"
        ),
    },
}

SOS_ORDER = ["craving", "demotive", "hungry", "plateau", "party"]


# ── /sos ────────────────────────────────────────────────────

@router.message(Command("sos"))
async def cmd_sos(message: Message):
    """Affiche le menu SOS : l'utilisateur choisit sa situation."""
    user = await db.get_user_by_telegram(message.from_user.id)
    if not user or not user.get("gdpr_consent"):
        await message.answer(
            "ℹ️ Tu n'es pas encore inscrit(e) ! Fais /start pour commencer."
        )
        return

    kb = InlineKeyboardBuilder()
    for key in SOS_ORDER:
        reason = SOS_REASONS[key]
        kb.button(text=reason["label"], callback_data=f"sos_{key}")
    kb.button(text="🔙 Menu principal", callback_data="sos_back")
    kb.adjust(1)

    await message.answer(
        "🆘 <b>Tu es prêt(e) à craquer ?</b>\n\n"
        "Respire. Je suis là. 👊\n"
        "Choisis ce que tu ressens :",
        reply_markup=kb.as_markup(),
    )


# ── Réponse par situation ───────────────────────────────────

@router.callback_query(F.data.startswith("sos_"))
async def sos_callback(callback: CallbackQuery):
    await callback.answer()

    key = callback.data.replace("sos_", "")

    if key == "back":
        await cmd_sos(callback.message)
        return

    reason = SOS_REASONS.get(key)
    if not reason:
        return

    # Logger l'interaction dans coaching_log
    try:
        await db.log_coaching(
            telegram_id=callback.from_user.id,
            interaction_type="motivation",
            user_message=f"/sos — {reason['label']}",
            coach_response=reason["message"],
        )
    except Exception:
        pass  # Silently fail logging — ne pas bloquer l'utilisateur

    # Re-afficher le menu avec la réponse
    kb = InlineKeyboardBuilder()
    kb.button(text="🔁 Autre situation", callback_data="sos_back")
    kb.adjust(1)

    await callback.message.edit_text(
        reason["message"] + "\n\n" + "👇 <b>Besoin d'autre chose ?</b>",
        reply_markup=kb.as_markup(),
    )
