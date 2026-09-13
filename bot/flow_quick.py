"""
Tezkor e'lon oqimi (faqat admin/moderator uchun tezkor joylash yo'li).
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

from common.telegram_media import watermark_telegram_photo

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403
from bot.fraud_detection import *  # noqa: F401,F403
from bot.admin_moderation import *  # noqa: F401,F403
from bot.location_alerts import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

# ============================= TEZKOR E'LON (FAQAT ADMIN) =============================

QUICK_MAX_LEN = 3500


async def quick_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_staff(user.id):
        return ConversationHandler.END
    if is_admin(user.id):
        daily_limit = None
    else:
        daily_limit = MOD_DAILY_LISTINGS
    if daily_limit is not None and count_today_listings(user.id) >= daily_limit:
        await update.message.reply_text(f"\u26a0\ufe0f Bugun uchun ruxsat etilgan {daily_limit} ta e'lon chegarasiga yetdingiz.\nErtaga qayta urinib ko'ring.")
        return ConversationHandler.END
    context.user_data.clear()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await update.message.reply_text(
        "\u26a1 <b>Tezkor e'lon</b>\n\n"
        "OLX'dan (yoki boshqa joydan) nusxalagan TO'LIQ matnni shu yerga joylashtiring \u2014 "
        "hech qanday o'zgartirishsiz, aynan shu holicha kanalga chiqadi.",
        parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )
    return QUICK_TEXT


async def quick_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("\u274c Bekor qilindi.")
    context.user_data.clear()
    return ConversationHandler.END


async def quick_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    if not raw:
        await update.message.reply_text("\u26a0\ufe0f Bo'sh bo'lishi mumkin emas. Matnni qaytadan joylashtiring:")
        return QUICK_TEXT
    if len(raw) > QUICK_MAX_LEN:
        await update.message.reply_text(f"\u26a0\ufe0f Matn juda uzun ({len(raw)} belgi). Iltimos, {QUICK_MAX_LEN} belgidan qisqaroq qiling:")
        return QUICK_TEXT
    context.user_data["quick_text"] = raw
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_totext"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await update.message.reply_text("\U0001F4DE Endi uy egasi telefon raqamini yozing (+998...):", reply_markup=keyboard)
    return QUICK_PHONE


async def quick_back_to_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await query.edit_message_text(
        "\u26a1 <b>Tezkor e'lon</b>\n\n"
        "OLX'dan (yoki boshqa joydan) nusxalagan TO'LIQ matnni shu yerga joylashtiring \u2014 "
        "hech qanday o'zgartirishsiz, aynan shu holicha kanalga chiqadi.",
        parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )
    return QUICK_TEXT


async def quick_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    phone = normalize_phone(raw)
    if not phone:
        await update.message.reply_text("\u26a0\ufe0f Raqam formati noto'g'ri. Masalan: +998901234567. Qaytadan yozing:")
        return QUICK_PHONE
    blocked = get_blocked_phone(phone)
    if blocked:
        await update.message.reply_text(
            f"\u26a0\ufe0f Bu raqam (<code>{esc(phone)}</code>) BLOKLANGAN ro'yxatda "
            f"(sabab: {esc(blocked.get('reason') or '—')}). Boshqa raqam yozing yoki avval blokdan chiqaring:",
            parse_mode=ParseMode.HTML,
        )
        return QUICK_PHONE
    context.user_data["telefon"] = phone
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tophone"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await update.message.reply_text(
        "\U0001F4CD Endi uyning manzilini yozing (tuman, mahalla) \u2014 bu saytda va xaritada ko'rsatiladi:",
        reply_markup=keyboard,
    )
    return QUICK_MANZIL


async def quick_back_to_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_totext"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await query.edit_message_text("\U0001F4DE Endi uy egasi telefon raqamini yozing (+998...):", reply_markup=keyboard)
    return QUICK_PHONE


async def quick_manzil_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    if not raw:
        await update.message.reply_text("\u26a0\ufe0f Bo'sh bo'lishi mumkin emas. Manzilni yozing:")
        return QUICK_MANZIL
    if len(raw) > 250:
        await update.message.reply_text(f"\u26a0\ufe0f Manzil juda uzun ({len(raw)} belgi). 250 belgidan qisqaroq yozing:")
        return QUICK_MANZIL
    context.user_data["quick_manzil"] = raw
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tomanzil"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await update.message.reply_text("\U0001F4B0 Endi narxini yozing (masalan: 150$, 1.2 mln, kelishiladi):", reply_markup=keyboard)
    return QUICK_NARX


async def quick_back_to_manzil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tophone"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await query.edit_message_text(
        "\U0001F4CD Endi uyning manzilini yozing (tuman, mahalla) \u2014 bu saytda va xaritada ko'rsatiladi:",
        reply_markup=keyboard,
    )
    return QUICK_MANZIL


async def quick_narx_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    if not raw:
        await update.message.reply_text("\u26a0\ufe0f Bo'sh bo'lishi mumkin emas. Narxni yozing:")
        return QUICK_NARX
    if len(raw) > 200:
        await update.message.reply_text(f"\u26a0\ufe0f Narx juda uzun ({len(raw)} belgi). Qisqaroq yozing:")
        return QUICK_NARX
    context.user_data["quick_narx"] = raw
    context.user_data["rasmlar"] = []
    context.user_data["photo_status_msg_id"] = None
    await quick_update_photo_status(update, context)
    return QUICK_PHOTOS


async def quick_back_to_narx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tomanzil"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await query.edit_message_text("\U0001F4B0 Endi narxini yozing (masalan: 150$, 1.2 mln, kelishiladi):", reply_markup=keyboard)
    return QUICK_NARX


async def quick_update_photo_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    photos = context.user_data.setdefault("rasmlar", [])
    n = len(photos)
    text = f"\U0001F4F8 Rasmlarni yuboring (1\u201310 ta).\n\n{n}/{MAX_PHOTOS} rasm qabul qilindi." if n else "\U0001F4F8 Rasmlarni yuboring (1\u201310 ta).\n\nKamida 1 ta rasm yuboring."
    rows = []
    if n > 0:
        rows.append([InlineKeyboardButton(f"\u2705 Tayyor ({n} ta) \u2014 Davom etish", callback_data="quick_rasm_tayyor")])
    rows.append([InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tonarx"),
                 InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")])
    markup = InlineKeyboardMarkup(rows)
    msg_id = context.user_data.get("photo_status_msg_id")
    if msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
    sent = await context.bot.send_message(chat_id, text, reply_markup=markup)
    context.user_data["photo_status_msg_id"] = sent.message_id


async def quick_rasm_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        rasmlar = context.user_data.setdefault("rasmlar", [])
        if len(rasmlar) >= MAX_PHOTOS:
            await update.message.reply_text(f"\u26a0\ufe0f Maksimal {MAX_PHOTOS} ta rasm yuborish mumkin.")
            return QUICK_PHOTOS
        file_id = update.message.photo[-1].file_id
        if ADMIN_IDS:
            file_id = await watermark_telegram_photo(file_id, ADMIN_IDS[0])
        rasmlar.append(file_id)
        await quick_update_photo_status(update, context)
        return QUICK_PHOTOS
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    await update.message.reply_text("\u26a0\ufe0f Iltimos, RASM yuboring yoki yuqoridagi tugmalardan foydalaning.")
    return QUICK_PHOTOS


async def quick_rasm_tayyor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data
    chat_id = update.effective_chat.id
    await send_photos(context, chat_id, data["rasmlar"])
    await context.bot.send_message(chat_id, esc(data["quick_text"]), parse_mode=ParseMode.HTML)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u2705 Kanalga joylash", callback_data="quick_post")],
         [InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tophotos"),
          InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]]
    )
    await context.bot.send_message(chat_id, "Tepadagi ko'rinishni tekshiring \u2014 shu holicha kanalga chiqadi \U0001F446", reply_markup=keyboard)
    return QUICK_CONFIRM


async def quick_back_to_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    await quick_update_photo_status(update, context)
    return QUICK_PHOTOS


async def quick_confirm_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await remind_buttons(update, context, QUICK_CONFIRM)


async def quick_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    user = update.effective_user
    data = context.user_data
    listing_id = save_quick_listing(
        user.id, user.username, user.full_name, data["telefon"],
        data["quick_manzil"], data["quick_narx"], data["quick_text"], data["rasmlar"],
    )
    listing = get_listing(listing_id)
    channel_msg_id = await send_listing_to_channel(context, listing)

    chat_id = update.effective_chat.id
    if channel_msg_id is None:
        await context.bot.send_message(chat_id, f"\u26a0\ufe0f Kanalga joylashda xatolik yuz berdi. E'lon #{listing_id} bazada saqlandi \u2014 qaytadan urinib ko'ring.")
    else:
        update_listing_status(listing_id, "approved", channel_msg_id=channel_msg_id)
        listing["channel_msg_id"] = channel_msg_id
        await notify_location_alert_matches(context, listing)
        await context.bot.send_message(chat_id, f"\u2705 E'lon #{listing_id} kanalga joylandi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    context.user_data.clear()
    return ConversationHandler.END



