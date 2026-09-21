"""
Limit (kanal uchun obuna) sotib olish oqimi.
"""
import asyncio
import difflib
import html
import io
import json
import logging
import re
import urllib.parse
from datetime import datetime, timedelta
from datetime import time as dtime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    MessageOriginHiddenUser,
    MessageOriginUser,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes, ConversationHandler, filters

from common.config import ADMIN_IDS, ADMIN_USERNAME, BOT_TOKEN as TOKEN, CARD_HOLDER, CHANNEL_ID, CHANNEL_USERNAME, DASHBOARD_URL, DB_PATH, DEFAULT_SETTINGS as INITIAL_SETTINGS, MAX_DAILY_LISTINGS, MOD_DAILY_LISTINGS, STALE_CHECK_DAYS

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403
from bot.fraud_detection import *  # noqa: F401,F403

from common.telegram_media import download_photo_bytes
from common.ai import ai_check_receipt, ai_features_enabled

logger = logging.getLogger(__name__)

# ============================= OBUNA (KANAL UCHUN) - ODDIY, 1 OYLIK =============================

async def subscription_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username, user.full_name)
    if is_banned(user.id):
        target = update.callback_query.message if update.callback_query else update.message
        if update.callback_query:
            await update.callback_query.answer()
        await target.reply_text("\u26a0\ufe0f Sizga botdan foydalanish cheklangan. Savollar bo'lsa, adminga murojaat qiling.")
        return ConversationHandler.END
    is_cb = bool(update.callback_query)
    target_listing_id = None
    if is_cb:
        await update.callback_query.answer()
        data = update.callback_query.data
        if "_" in data and data.rsplit("_", 1)[1].isdigit():
            target_listing_id = int(data.rsplit("_", 1)[1])
        target = update.callback_query.message
    else:
        target = update.message

    active, expire = is_subscribed(user.id)
    if is_admin(user.id):
        await target.reply_text("\U0001F451 Siz adminsiz \u2014 sizda har doim <b>cheksiz</b> limit bor.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    if active:
        await target.reply_text(f"\u2705 Sizda faol limit bor.\nMuddati: <b>{expire[:10]}</b> gacha.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    context.user_data["target_listing_id"] = target_listing_id
    price = subscription_price()
    days = subscription_days()

    # KARTA RAQAMI FAQAT SHU YERDA - "Limit sotib olish" bosilgan zahoti - ko'rsatiladi.
    text = card_html(price, purpose=f"{days} kunlik limit")
    keyboard = card_payment_keyboard()
    await target.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    schedule_cart_reminder(context, user.id)
    return SUB_WAIT_RECEIPT


CART_REMINDER_DELAY_SECONDS = 35 * 60


async def send_cart_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    user_id, since = data["user_id"], data["since"]
    active, _ = is_subscribed(user_id)
    if active or has_recent_subscription_request(user_id, since):
        return  # Allaqachon sotib olgan yoki chek yuborgan - eslatma keraksiz.
    active_count = count_active_subscribers()
    social_proof = f"{active_count}+ kishi Limit sotib oldi va hali hech kim afsuslanmadi \u2014 " if active_count >= 10 else ""
    text = (
        "\U0001F44B Sizga karta raqami yuborilgan edi \u2014 hali to'lov chekini yubormadingiz.\n\n"
        f"{social_proof}siz ham maklerlarga ortiqcha pul to'lamang, hoziroq Limit oling!\n\n"
        "Savol yoki muammo bo'lsa, yordam berishga tayyormiz."
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F4B3 Qayta ko'rish", callback_data="buy_subscription")]])
    try:
        await context.bot.send_message(user_id, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception:
        logger.exception("Savat eslatmasini yuborib bo'lmadi: user_id=%s", user_id)


def schedule_cart_reminder(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    if not context.job_queue:
        return
    name = f"cartreminder_{user_id}"
    for job in context.job_queue.get_jobs_by_name(name):
        job.schedule_removal()
    context.job_queue.run_once(send_cart_reminder, CART_REMINDER_DELAY_SECONDS, data={"user_id": user_id, "since": now_str()}, name=name)


async def sub_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("\u274c Bekor qilindi.")
    return ConversationHandler.END


async def subscription_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        if await try_escape_to_menu(update, context):
            return ConversationHandler.END
        await update.message.reply_text("\u26a0\ufe0f Iltimos, to'lov chekining skrinshotini RASM sifatida yuboring.")
        return SUB_WAIT_RECEIPT

    user = update.effective_user
    price = subscription_price()
    receipt = update.message.photo[-1].file_id
    target_listing_id = context.user_data.get("target_listing_id")

    try:
        sub_id = save_subscription_request(user.id, receipt, price, target_listing_id)
    except Exception:
        logger.exception("Obuna so'rovini bazaga saqlashda xatolik")
        await update.message.reply_text("\u26a0\ufe0f Texnik xatolik yuz berdi. Iltimos, chek rasmni QAYTA yuboring \u2014 ma'lumotlaringiz yo'qolmagan.")
        return SUB_WAIT_RECEIPT

    admin_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u2705 Tasdiqlash", callback_data=f"admin_approve_sub_{sub_id}"),
          InlineKeyboardButton("\u274c Rad etish", callback_data=f"admin_reject_sub_{sub_id}")],
         [profile_link_button(user.id)]]
    )
    admin_keyboard_fallback = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u2705 Tasdiqlash", callback_data=f"admin_approve_sub_{sub_id}"),
          InlineKeyboardButton("\u274c Rad etish", callback_data=f"admin_reject_sub_{sub_id}")]]
    )
    ai_note = ""
    if ai_features_enabled():
        try:
            receipt_bytes = await download_photo_bytes(receipt)
            if receipt_bytes:
                loop = asyncio.get_event_loop()
                receipt_check = await loop.run_in_executor(None, ai_check_receipt, receipt_bytes, "image/jpeg", price, CARD_HOLDER)
                if receipt_check and not receipt_check.get("matches"):
                    ai_note = f"\n\n\U0001F916⚠️ <b>AI: chekda nomuvofiqlik</b> — {esc(receipt_check.get('note') or '')}"
                    set_subscription_receipt_warning(sub_id, receipt_check.get("note") or "")
        except Exception:
            logger.exception("AI obuna chekini tekshirishda xatolik")

    caption = (
        f"\U0001F4B3 <b>Yangi obuna so'rovi</b> #{sub_id}\n\n"
        f"\U0001F464 {esc(user.full_name)} (@{esc(user.username) or 'yo`q'})\n"
        f"\U0001F194 user_id: {user.id}\n"
        f"\U0001F4B0 Summasi: {price:,} so'm"
        f"{ai_note}"
    )
    any_success = False
    for admin_id in ADMIN_IDS:
        try:
            await send_with_privacy_fallback(
                context.bot.send_photo, admin_id, receipt, caption=caption, parse_mode=ParseMode.HTML,
                full_markup=admin_keyboard, fallback_markup=admin_keyboard_fallback,
            )
            any_success = True
        except Exception:
            logger.exception("Adminga (%s) obuna chekini yuborishda xatolik", admin_id)

    if any_success:
        text = "\U0001F4E8 Chekingiz qabul qilindi, admin tekshirmoqda. Tasdiqlangach xabar beramiz."
    else:
        text = "\U0001F4E8 Chekingiz qabul qilindi va saqlandi. Adminga bildirishnoma yuborishda vaqtinchalik tarmoq muammosi bo'ldi, lekin xavotir olmang \u2014 so'rovingiz yo'qolmagan."
    await update.message.reply_text(text, reply_markup=main_menu_keyboard(user.id))
    context.user_data.pop("target_listing_id", None)
    return ConversationHandler.END



