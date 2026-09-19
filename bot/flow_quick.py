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
from common.districts import TASHKENT_DISTRICTS, detect_district, detect_price
from common.ai import ai_extract_listing_fields

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
        "\u26a1 <b>Tezkor e'lon</b>\n\nE'lon matnini kiriting:",
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
    await update.message.reply_text("\U0001F4DE Telefon raqamni yozing (+998...):", reply_markup=keyboard)
    return QUICK_PHONE


async def quick_back_to_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await query.edit_message_text(
        "\u26a1 <b>Tezkor e'lon</b>\n\nE'lon matnini kiriting:",
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
    text, keyboard, parse_mode = await _build_manzil_prompt(context)
    await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=keyboard)
    return QUICK_MANZIL


async def quick_back_to_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_totext"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await query.edit_message_text("\U0001F4DE Telefon raqamni yozing (+998...):", reply_markup=keyboard)
    return QUICK_PHONE


# ============================= MANZIL (avtomatik aniqlash bilan) =============================
# Matndan tuman nomi aniqlansa, foydalanuvchiga qo'lda yozish o'rniga
# "Ha, to'g'ri" / "O'zim yozaman" tanlovi beriladi - aniqlanmasa, ODATDAGIDEK
# ish yuruvchi (arzon, tez) regex birinchi urinib ko'radi; u ham topa
# olmasa - AI (agar admin yoqib qo'ygan bo'lsa) matndan manzil/narx/xona
# ajratib olishga harakat qiladi, natija bitta so'rovda keshlanadi (ikkalasi
# uchun ham qayta so'rov yuborilmaydi). AI ham topa olmasa - odatdagidek
# qo'lda so'raladi.

async def _get_ai_fields(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "_ai_fields" not in context.user_data:
        quick_text = context.user_data.get("quick_text", "")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, ai_extract_listing_fields, quick_text)
        context.user_data["_ai_fields"] = result or {}
    return context.user_data["_ai_fields"]


async def _build_manzil_prompt(context: ContextTypes.DEFAULT_TYPE) -> tuple:
    quick_text = context.user_data.get("quick_text", "")
    detected = detect_district(quick_text)
    if detected:
        text = f"\U0001F4CD Matndan manzil (tuman) aniqlandi: <b>{esc(detected)}</b>\n\nShu to'g'rimi?"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2705 Ha, to'g'ri", callback_data="quick_manzil_auto")],
            [InlineKeyboardButton("\u270f\ufe0f O'zim yozaman", callback_data="quick_manzil_write")],
            [InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tophone"),
             InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")],
        ])
        return text, keyboard, ParseMode.HTML
    ai_fields = await _get_ai_fields(context)
    ai_manzil = ai_fields.get("manzil")
    if ai_manzil:
        text = f"\U0001F916 AI orqali manzil taklif qilindi: <b>{esc(ai_manzil)}</b>\n\nShu to'g'rimi?"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2705 Ha, to'g'ri", callback_data="quick_manzil_ai")],
            [InlineKeyboardButton("\u270f\ufe0f O'zim yozaman", callback_data="quick_manzil_write")],
            [InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tophone"),
             InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")],
        ])
        return text, keyboard, ParseMode.HTML
    text = "\U0001F4CD Manzilni yozing (tuman, mahalla) \u2014 bu saytda va xaritada ko'rsatiladi:"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tophone"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    return text, keyboard, None


async def _advance_to_narx_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_query: bool = False) -> int:
    text, keyboard, parse_mode = await _build_narx_prompt(context)
    if edit_query:
        await update.callback_query.edit_message_text(text, parse_mode=parse_mode, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=keyboard)
    return QUICK_NARX


async def quick_manzil_auto_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    detected = detect_district(context.user_data.get("quick_text", ""))
    if not detected:
        # Matn shu oraliqda o'zgarmagan bo'lsa, bu holat yuzaga kelmaydi -
        # ehtiyot chorasi sifatida qo'lda yozishga o'tkaziladi.
        return await quick_manzil_manual_router(update, context)
    context.user_data["quick_manzil"] = detected
    return await _advance_to_narx_prompt(update, context, edit_query=True)


async def quick_manzil_ai_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ai_fields = await _get_ai_fields(context)
    ai_manzil = ai_fields.get("manzil")
    if not ai_manzil:
        return await quick_manzil_manual_router(update, context)
    context.user_data["quick_manzil"] = ai_manzil
    return await _advance_to_narx_prompt(update, context, edit_query=True)


async def quick_manzil_manual_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tophone"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await query.edit_message_text(
        "\U0001F4CD Manzilni yozing (tuman, mahalla) \u2014 bu saytda va xaritada ko'rsatiladi:",
        reply_markup=keyboard,
    )
    return QUICK_MANZIL


async def _offer_quick_teach(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manzil qo'lda kiritilib, matnda tuman AVTOMATIK aniqlanmagan bo'lsa -
    moderatorga tizimni "o'rgatish" imkoniyatini ixtiyoriy (o'tkazib
    yuborsa bo'ladigan) tarzda taklif qiladi. MUHIM: bu yerdagi tugmalar
    quick_conv'dan MUSTAQIL - "district_alias_add_conv" (bot/main.py,
    bot/district_alias_ui.py) ni ishga tushiradi, xuddi shu callback_data
    ("distalias_add_{idx}") "Tuman kalit so'zlari" bo'limidagi bilan bir
    xil - shu orqali ikkinchi nusxa yozish shart bo'lmadi."""
    rows, row = [], []
    for i, d in enumerate(TASHKENT_DISTRICTS):
        row.append(InlineKeyboardButton(d, callback_data=f"distalias_add_{i}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("\u23ed O'tkazib yuborish", callback_data="quickteach_skip")])
    await update.message.reply_text(
        "\U0001F393 Bu manzilda tuman nomi avtomatik aniqlanmadi. Xohlasangiz, "
        "tizimni o'rgatish uchun shu manzildagi kalit so'zni tegishli tumanga "
        "biriktiring (ixtiyoriy - o'tkazib yuborsangiz ham e'lon davom etadi):",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def quickteach_skip_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass


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
    if detect_district(context.user_data.get("quick_text", "")) is None:
        await _offer_quick_teach(update, context)
    return await _advance_to_narx_prompt(update, context, edit_query=False)


async def quick_back_to_manzil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text, keyboard, parse_mode = await _build_manzil_prompt(context)
    await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=keyboard)
    return QUICK_MANZIL


# ============================= NARX (avtomatik aniqlash bilan) =============================

async def _build_narx_prompt(context: ContextTypes.DEFAULT_TYPE) -> tuple:
    quick_text = context.user_data.get("quick_text", "")
    detected = detect_price(quick_text)
    if detected:
        text = f"\U0001F4B0 Matndan narx aniqlandi: <b>{esc(detected)}</b>\n\nShu to'g'rimi?"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2705 Ha, to'g'ri", callback_data="quick_narx_auto")],
            [InlineKeyboardButton("\u270f\ufe0f O'zim yozaman", callback_data="quick_narx_write")],
            [InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tomanzil"),
             InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")],
        ])
        return text, keyboard, ParseMode.HTML
    ai_fields = await _get_ai_fields(context)
    ai_narx = ai_fields.get("narx")
    if ai_narx:
        text = f"\U0001F916 AI orqali narx taklif qilindi: <b>{esc(ai_narx)}</b>\n\nShu to'g'rimi?"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2705 Ha, to'g'ri", callback_data="quick_narx_ai")],
            [InlineKeyboardButton("\u270f\ufe0f O'zim yozaman", callback_data="quick_narx_write")],
            [InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tomanzil"),
             InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")],
        ])
        return text, keyboard, ParseMode.HTML
    text = "\U0001F4B0 Narxni yozing (masalan: 150$, 1.2 mln, kelishiladi):"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tomanzil"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    return text, keyboard, None


async def _finish_narx(update: Update, context: ContextTypes.DEFAULT_TYPE, narx: str) -> int:
    context.user_data["quick_narx"] = narx
    # Xona soni uchun alohida so'rov bosqichi yo'q - agar AI matndan
    # (manzil/narx aniqlash jarayonida keshlangan chaqiruvdan) xona sonini
    # ham topgan bo'lsa, shuni ishlatamiz - hozirgacha bu maydon Tezkor
    # e'londa doim bo'sh qolar edi.
    ai_xona = context.user_data.get("_ai_fields", {}).get("xona")
    if ai_xona:
        context.user_data["quick_xona"] = ai_xona
    context.user_data["rasmlar"] = []
    context.user_data["photo_status_msg_id"] = None
    await quick_update_photo_status(update, context)
    return QUICK_PHOTOS


async def quick_narx_auto_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    detected = detect_price(context.user_data.get("quick_text", ""))
    if not detected:
        return await quick_narx_manual_router(update, context)
    await query.edit_message_reply_markup(reply_markup=None)
    return await _finish_narx(update, context, detected)


async def quick_narx_ai_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ai_fields = await _get_ai_fields(context)
    ai_narx = ai_fields.get("narx")
    if not ai_narx:
        return await quick_narx_manual_router(update, context)
    await query.edit_message_reply_markup(reply_markup=None)
    return await _finish_narx(update, context, ai_narx)


async def quick_narx_manual_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="quick_back_tomanzil"),
                                       InlineKeyboardButton("\u274c Bekor qilish", callback_data="quick_cancel")]])
    await query.edit_message_text("\U0001F4B0 Narxni yozing (masalan: 150$, 1.2 mln, kelishiladi):", reply_markup=keyboard)
    return QUICK_NARX


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
    return await _finish_narx(update, context, raw)


async def quick_back_to_narx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text, keyboard, parse_mode = await _build_narx_prompt(context)
    await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=keyboard)
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
        xona=data.get("quick_xona", ""),
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



