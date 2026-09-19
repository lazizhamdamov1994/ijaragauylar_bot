"""
AI Concierge - botdagi erkin suhbat rejimi. Foydalanuvchi "AI yordamchi"
tugmasini bossa, keyingi xabarlari (menyu tugmalaridan biri bosilmaguncha)
AI'ga yuboriladi - AI bazadan mos e'lonlarni qidiradi va javob beradi.

Butun mantiq (tool-use, xarajat logi, kunlik chegara) common/ai_agent.py'da
- bu fayl faqat botga xos "suhbat holati" (ConversationHandler) qatlami.
Xuddi shu common/ai_agent.py veb chat vidjeti (web/) tomonidan ham
ishlatiladi - ikkala tomon bitta AI mantig'ini baham ko'radi.
"""
import logging

from telegram import ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from common.ai import ai_features_enabled
from common.ai_agent import concierge_rate_limited, concierge_turn

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403
from bot.fraud_detection import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

_CONCIERGE_KEYBOARD = ReplyKeyboardMarkup([[BTN_AI_CONCIERGE_END]], resize_keyboard=True)


async def ai_concierge_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not ai_features_enabled():
        await update.message.reply_text(
            "\U0001F916 AI yordamchi hozircha ishga tushirilmagan. Tez orada faollashadi!",
            reply_markup=main_menu_keyboard(user.id),
        )
        return ConversationHandler.END
    if concierge_rate_limited(user.id, "bot"):
        await update.message.reply_text(
            "⚠️ Bugungi AI yordamchi bilan suhbat chegarasiga yetdingiz. Ertaga qayta urinib ko'ring.",
            reply_markup=main_menu_keyboard(user.id),
        )
        return ConversationHandler.END
    context.user_data["ai_concierge_history"] = []
    await update.message.reply_text(
        "\U0001F916 <b>AI yordamchi</b>\n\n"
        "Menga qanday uy kerakligini yozing - masalan: \"Chilonzorda 2 xonali, 300$ gacha uy kerak\". "
        "Savollaringizga ham javob beraman.\n\n"
        "<i>Chiqish uchun pastdagi tugmani bosing.</i>",
        parse_mode=ParseMode.HTML, reply_markup=_CONCIERGE_KEYBOARD,
    )
    return AI_CONCIERGE_CHAT


async def ai_concierge_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await try_escape_to_menu(update, context):
        context.user_data.pop("ai_concierge_history", None)
        return ConversationHandler.END

    user = update.effective_user
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("⚠️ Iltimos, matn ko'rinishida yozing.")
        return AI_CONCIERGE_CHAT
    if len(text) > 500:
        await update.message.reply_text(f"⚠️ Xabar juda uzun ({len(text)} belgi). 500 belgidan qisqaroq yozing:")
        return AI_CONCIERGE_CHAT

    if concierge_rate_limited(user.id, "bot"):
        await update.message.reply_text(
            "⚠️ Bugungi AI yordamchi bilan suhbat chegarasiga yetdingiz. Ertaga qayta urinib ko'ring.",
            reply_markup=main_menu_keyboard(user.id),
        )
        context.user_data.pop("ai_concierge_history", None)
        return ConversationHandler.END

    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    history = context.user_data.get("ai_concierge_history", [])
    reply, new_history = await concierge_turn(user.id, "bot", history, text)

    if reply is None:
        await update.message.reply_text(
            "⚠️ AI yordamchida vaqtinchalik texnik nosozlik. Birozdan keyin qayta urinib ko'ring.",
            reply_markup=_CONCIERGE_KEYBOARD,
        )
        return AI_CONCIERGE_CHAT

    context.user_data["ai_concierge_history"] = new_history
    await update.message.reply_text(reply, reply_markup=_CONCIERGE_KEYBOARD, disable_web_page_preview=True)
    return AI_CONCIERGE_CHAT


async def ai_concierge_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("ai_concierge_history", None)
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END
