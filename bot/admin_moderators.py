"""
Moderatorlarni qo'shish/o'chirish (faqat asosiy admin).
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

logger = logging.getLogger(__name__)

# ============================= MODERATORLAR (FAQAT ASOSIY ADMIN) =============================

def render_moderators() -> tuple:
    mods = list_moderators()
    admins = list_extra_admins()
    lines = ["\U0001F46E <b>Moderatorlar</b>\n"]
    kb_rows = [[InlineKeyboardButton("\u2795 Yangi moderator qo'shish", callback_data="mod_add")]]
    if not mods:
        lines.append("<i>Hozircha moderator yo'q.</i>")
    for m in mods:
        u = get_user(m["user_id"]) or {}
        name = esc(u.get("full_name") or "noma'lum")
        uname = f"@{esc(u['username'])}" if u.get("username") else f"ID: {m['user_id']}"
        lines.append(f"\u2022 {name} ({uname})  \u2014  {m['added_at'][:10]}")
        kb_rows.append([InlineKeyboardButton(f"\u274c Olib tashlash: {name}", callback_data=f"modremove_{m['user_id']}")])

    lines.append("\n\U0001F451 <b>Adminlar</b>\n")
    kb_rows.append([InlineKeyboardButton("\u2795 Yangi admin qo'shish", callback_data="admin_add")])
    if not admins:
        lines.append("<i>Bot sozlamalaridan (ADMIN_IDS) tashqari qo'shimcha admin yo'q.</i>")
    for a in admins:
        u = get_user(a["user_id"]) or {}
        name = esc(u.get("full_name") or "noma'lum")
        uname = f"@{esc(u['username'])}" if u.get("username") else f"ID: {a['user_id']}"
        lines.append(f"\u2022 {name} ({uname})  \u2014  {a['added_at'][:10]}")
        kb_rows.append([InlineKeyboardButton(f"\u274c Olib tashlash: {name}", callback_data=f"adminremove_{a['user_id']}")])

    return "\n".join(lines), InlineKeyboardMarkup(kb_rows)


async def show_moderators(update: Update, context: ContextTypes.DEFAULT_TYPE, _page: int = 0):
    text, markup = render_moderators()
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def mod_remove_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    target_id = int(query.data.rsplit("_", 1)[1])
    remove_moderator(target_id)
    try:
        await context.bot.send_message(target_id, "\u2139\ufe0f Siz endi moderator emassiz.")
    except Exception:
        logger.exception("Moderatorlikdan olib tashlanganlik xabarini yuborib bo'lmadi")
    await query.answer("Olib tashlandi \u2705")
    await show_moderators(update, context)


async def admin_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return ConversationHandler.END
    await query.message.reply_text(
        "\U0001F451 Yangi admin qo'shish uchun, uning biror xabarini shu yerga FORWARD qiling, "
        "yoki uning Telegram user_id raqamini yozing.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADMIN_ADD_WAIT


async def admin_add_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END

    target_id = None
    origin = update.message.forward_origin
    if isinstance(origin, MessageOriginUser):
        target_id = origin.sender_user.id
    elif update.message.text and update.message.text.strip().isdigit():
        target_id = int(update.message.text.strip())

    if not target_id:
        hint = "\n\n(Bu foydalanuvchi profilida forward'da ismi yashirin \u2014 user_id raqamini yozing.)" if isinstance(origin, MessageOriginHiddenUser) else ""
        await update.message.reply_text(f"\u26a0\ufe0f Foydalanuvchini aniqlab bo'lmadi. Xabarini forward qiling yoki user_id raqamini yozing:{hint}")
        return ADMIN_ADD_WAIT

    if is_admin(target_id):
        await update.message.reply_text("\u26a0\ufe0f Bu foydalanuvchi allaqachon admin.", reply_markup=main_menu_keyboard(update.effective_user.id))
        return ConversationHandler.END

    add_extra_admin(target_id, update.effective_user.id)
    remove_moderator(target_id)  # admin bolsa, moderator royxatida ortiqcha turmasin
    await update.message.reply_text(f"\u2705 Admin qo'shildi (user_id: {target_id}).", reply_markup=main_menu_keyboard(update.effective_user.id))
    try:
        await context.bot.send_message(
            target_id,
            "\U0001F451 <b>Siz admin etib tayinlandingiz!</b>\n\n"
            "Endi sizda to'liq boshqaruv huquqi bor: barcha sozlamalar, statistika, "
            "foydalanuvchilarni boshqarish va cheksiz limit.\n\n"
            "Menyuni yangilash uchun /start bosing.",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception("Adminlik haqida xabar yuborib bo'lmadi")
    await show_moderators(update, context)
    return ConversationHandler.END


async def admin_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END


async def admin_remove_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    target_id = int(query.data.rsplit("_", 1)[1])
    if target_id in ADMIN_IDS:
        await query.answer("Bu asosiy admin - bot sozlamalaridan (ADMIN_IDS) olib tashlanishi kerak.", show_alert=True)
        return
    remove_extra_admin(target_id)
    try:
        await context.bot.send_message(target_id, "\u2139\ufe0f Siz endi admin emassiz.")
    except Exception:
        logger.exception("Adminlikdan olib tashlanganlik xabarini yuborib bo'lmadi")
    await query.answer("Olib tashlandi \u2705")
    await show_moderators(update, context)


async def mod_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return ConversationHandler.END
    await query.message.reply_text(
        "\U0001F46E Yangi moderator qo'shish uchun, uning biror xabarini shu yerga FORWARD qiling, "
        "yoki uning Telegram user_id raqamini yozing.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return MOD_ADD_WAIT


async def mod_add_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END

    target_id = None
    origin = update.message.forward_origin
    if isinstance(origin, MessageOriginUser):
        target_id = origin.sender_user.id
    elif update.message.text and update.message.text.strip().isdigit():
        target_id = int(update.message.text.strip())

    if not target_id:
        hint = "\n\n(Bu foydalanuvchi profilida forward'da ismi yashirin \u2014 user_id raqamini yozing.)" if isinstance(origin, MessageOriginHiddenUser) else ""
        await update.message.reply_text(f"\u26a0\ufe0f Foydalanuvchini aniqlab bo'lmadi. Xabarini forward qiling yoki user_id raqamini yozing:{hint}")
        return MOD_ADD_WAIT

    if is_admin(target_id):
        await update.message.reply_text("\u26a0\ufe0f Bu foydalanuvchi allaqachon asosiy admin.", reply_markup=main_menu_keyboard(update.effective_user.id))
        return ConversationHandler.END

    add_moderator(target_id, update.effective_user.id)
    await update.message.reply_text(f"\u2705 Moderator qo'shildi (user_id: {target_id}).", reply_markup=main_menu_keyboard(update.effective_user.id))
    try:
        await context.bot.send_message(
            target_id,
            "\U0001F46E <b>Siz moderator etib tayinlandingiz!</b>\n\n"
            "Endi sizda qo'shimcha imkoniyatlar bor: e'lon/obunalarni tasdiqlash-rad etish, "
            "\"\u26a1 Tezkor e'lon\" orqali tez e'lon joylash, va statistikani ko'rish.\n\n"
            "Menyuni yangilash uchun /start bosing.",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception("Moderatorlik haqida xabar yuborib bo'lmadi")
    await show_moderators(update, context)
    return ConversationHandler.END


async def mod_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END



