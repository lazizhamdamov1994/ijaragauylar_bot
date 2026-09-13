"""
Admin panel: moderator shaxsiy statistikasi, obunachilar ro'yxati, shubhali
faollik, foydalanuvchi qidirish, sozlamalar, bloklangan raqamlar.
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
from bot.flow_complaint import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

# ============================= MODERATOR SHAXSIY STATISTIKASI =============================
# MUHIM: count_listings_stats_by_user / TRUSTED_MIN_LISTINGS / is_trusted_poster
# endi bot/helpers.py'da (build_caption ularni chaqiradi, u esa bu fayldan
# OLDINROQ import zanjirida turadi - shuning uchun bu yerda emas, o'sha yerda
# aniqlanishi kerak).

async def show_moderator_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    s = count_listings_stats_by_user(user_id)
    text = (
        f"\U0001F4CA <b>Sizning statistikangiz</b>\n\n"
        f"\U0001F4DD Jami joylagan e'lonlaringiz: {s['total']} ta\n"
        f"   \u2705 Faol: {s['active']} \u00b7 \U0001F534 Topshirilgan: {s['closed']}\n"
        f"   \u274c Rad etilgan: {s['rejected']} \u00b7 \U0001F553 Kutilmoqda: {s['pending']}\n\n"
        f"<i>Batafsil ro'yxat uchun \u00abMening e'lonlarim\u00bb tugmasidan foydalaning.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ============================= OBUNACHILAR (sahifalangan) =============================

def render_subscribers(rows: list, page: int, total: int):
    if not rows:
        return "\U0001F465 Hozircha faol obunachilar yo'q.", InlineKeyboardMarkup([])
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    lines = [f"\U0001F465 <b>Faol obunachilar</b> (sahifa {page + 1}/{total_pages}, jami {total} ta):",
              "<i>Batafsil ko'rish uchun ismga bosing.</i>\n"]
    kb_rows = []
    for i, r in enumerate(rows, page * PAGE_SIZE + 1):
        name = r.get("full_name") or "Noma'lum"
        btn_label = f"{i}. {name} \u2014 {r['expire_at'][:10]} gacha"
        kb_rows.append([InlineKeyboardButton(btn_label[:64], callback_data=f"usercard_{r['user_id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("\u2b05\ufe0f Oldingi", callback_data=f"subpage_{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("Keyingi \u27a1\ufe0f", callback_data=f"subpage_{page + 1}"))
    if nav:
        kb_rows.append(nav)
    return "\n".join(lines), InlineKeyboardMarkup(kb_rows)


async def show_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    total = count_active_subscribers()
    rows = active_subscribers_page(page * PAGE_SIZE)
    text, markup = render_subscribers(rows, page, total)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def subpage_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    page = int(query.data.rsplit("_", 1)[1])
    await show_subscribers(update, context, page)


def render_user_card(user_id: int) -> tuple:
    u = get_user(user_id) or {}
    name = u.get("full_name") or "Noma'lum"
    uname = f"@{esc(u['username'])}" if u.get("username") else "<i>username yo'q</i>"
    reg_date = (u.get("created_at") or "")[:10] or "\u2014"

    active, expire = is_subscribed(user_id)
    sub_line = f"\u2705 Faol ({expire[:10]} gacha)" if active else "\u274c Faol obuna yo'q"

    risk = compute_risk_score(user_id)
    risk_line = f"{risk['score']} ball"
    if risk["score"] >= RISK_THRESHOLD:
        risk_line += " \U0001F6A8 (YUQORI)"
    elif risk["score"] > 0:
        risk_line += " \u26a0\ufe0f"

    banned = is_banned(user_id)

    lines = [
        f"\U0001F464 <b>{user_link(user_id, name)}</b>",
        f"{uname}",
        f"\U0001F194 user_id: <code>{user_id}</code>",
        f"\U0001F4C5 Ro'yxatdan o'tgan: {reg_date}\n",
        f"\U0001F4B3 Obuna: {sub_line}",
        f"\U0001F6A8 Xavf balli: {risk_line}",
    ]
    if risk["reasons"]:
        for r in risk["reasons"]:
            lines.append(f"   \u2022 {esc(r)}")
    lines.append("")
    lines.append(f"\U0001F4CA Jami ko'rgan raqamlari: {risk['lifetime']} ta")
    lines.append(f"\U0001F4DD Bergan e'lonlari: {count_listings_by_user(user_id)} ta")
    lines.append(f"\U0001F6A9 Shikoyat qilganlari: {count_reports_made(user_id)} ta")
    lines.append(f"\U0001F4E5 Unga shikoyat qilinganlari: {count_reports_received(user_id)} ta")
    if banned:
        lines.append("\n\u26d4 <b>Bu foydalanuvchi hozir botdan cheklangan.</b>")

    kb_rows = []
    if active:
        kb_rows.append([InlineKeyboardButton("\u274c Obunani bekor qilish", callback_data=f"cardcancel_{user_id}")])
    if banned:
        kb_rows.append([InlineKeyboardButton("\u2705 Cheklovni olib tashlash", callback_data=f"cardunban_{user_id}")])
    else:
        kb_rows.append([InlineKeyboardButton("\U0001F6AB Botdan cheklash", callback_data=f"cardban_{user_id}")])
    kb_rows.append([InlineKeyboardButton("\U0001F464 Profilga o'tish", url=f"tg://user?id={user_id}")])

    return "\n".join(lines), InlineKeyboardMarkup(kb_rows)


async def show_user_card(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    try:
        text, markup = render_user_card(user_id)
    except Exception:
        logger.exception("Foydalanuvchi kartasini tayyorlashda xatolik: user_id=%s", user_id)
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text("\u26a0\ufe0f Bu foydalanuvchi haqida ma'lumotni tayyorlashda xatolik yuz berdi.")
        return
    try:
        if update.callback_query:
            await send_with_retry(update.callback_query.edit_message_text, text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)
        else:
            await send_with_retry(update.message.reply_text, text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)
    except BadRequest as e:
        err = str(e).lower()
        if "not modified" in err:
            # Foydalanuvchi bir xil tugmani ikki marta bosgan (yoki karta allaqachon
            # aynan shu holatda ko'rsatilgan) - bu XATO EMAS, jim o'tkazamiz.
            if update.callback_query:
                try:
                    await update.callback_query.answer()
                except Exception:
                    pass
            return
        if "button_user_privacy_restricted" in err:
            # Bu foydalanuvchining maxfiylik sozlamalari "profilga havola"
            # tugmasini yaratishga to'sqinlik qiladi - shu TUGMASIZ qayta yuboramiz.
            stripped_markup = InlineKeyboardMarkup(list(markup.inline_keyboard[:-1]))
            note_text = text + "\n\n<i>\u2139\ufe0f Bu foydalanuvchi profiliga havola berib bo'lmadi (uning maxfiylik sozlamalari tufayli).</i>"
            try:
                if update.callback_query:
                    await send_with_retry(update.callback_query.edit_message_text, note_text, parse_mode=ParseMode.HTML, reply_markup=stripped_markup, disable_web_page_preview=True)
                else:
                    await send_with_retry(update.message.reply_text, note_text, parse_mode=ParseMode.HTML, reply_markup=stripped_markup, disable_web_page_preview=True)
            except Exception:
                logger.exception("Profilga havolasiz ham kartani yuborib bo'lmadi: user_id=%s", user_id)
                target = update.callback_query.message if update.callback_query else update.message
                await target.reply_text("\u26a0\ufe0f Kartani ko'rsatishda xatolik yuz berdi.")
            return
        logger.error("Foydalanuvchi kartasini yuborishda HTML/so'rov xatosi: user_id=%s, xato=%s\nMatn:\n%s", user_id, e, text)
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text(f"\u26a0\ufe0f Kartani ko'rsatishda xatolik: {esc(str(e))}")
    except Exception:
        logger.exception("Foydalanuvchi kartasini yuborishda xatolik: user_id=%s", user_id)
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text("\u26a0\ufe0f Kartani ko'rsatishda tarmoq muammosi yuz berdi. Qaytadan urinib ko'ring.")


async def usercard_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    user_id = int(query.data.rsplit("_", 1)[1])
    await show_user_card(update, context, user_id)


async def cardcancel_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    user_id = int(query.data.rsplit("_", 1)[1])
    u = get_user(user_id) or {}
    name = esc(u.get("full_name") or "Noma'lum")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u2705 Ha, bekor qilish", callback_data=f"cardcancelyes_{user_id}"),
         InlineKeyboardButton("\u274c Yo'q", callback_data=f"usercard_{user_id}")],
    ])
    await query.edit_message_text(f"Rostdan ham <b>{name}</b>ning obunasini bekor qilasizmi?", parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def cardcancelyes_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    user_id = int(query.data.rsplit("_", 1)[1])
    sub_id = get_active_subscription_id(user_id)
    if sub_id:
        cancel_subscription(sub_id)
        try:
            await context.bot.send_message(user_id, "\u274c Sizning obunangiz administrator tomonidan muddatidan oldin bekor qilindi.")
        except Exception:
            logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi")
    await show_user_card(update, context, user_id)


async def cardban_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    user_id = int(query.data.rsplit("_", 1)[1])
    ban_user(user_id, "Admin tomonidan cheklandi (shubhali faollik)", query.from_user.id)
    try:
        await context.bot.send_message(user_id, "\u26a0\ufe0f Sizga botdan foydalanish cheklandi. Savollar bo'lsa, adminga murojaat qiling.")
    except Exception:
        logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi")
    await show_user_card(update, context, user_id)


async def cardunban_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    user_id = int(query.data.rsplit("_", 1)[1])
    unban_user(user_id)
    try:
        await context.bot.send_message(user_id, "\u2705 Sizga botdan foydalanish cheklovi olib tashlandi.")
    except Exception:
        logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi")
    await show_user_card(update, context, user_id)


# ============================= SHUBHALI FAOLLIK (ADMIN) =============================

def render_flagged(page: int) -> tuple:
    flagged = get_flagged_users()
    total = len(flagged)
    if not total:
        return "\u2705 Hozircha shubhali faollik qayd etilmagan.", InlineKeyboardMarkup([])
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page_items = flagged[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]
    lines = [f"\U0001F6A8 <b>Shubhali faollik</b> (sahifa {page + 1}/{total_pages}, jami {total} ta):",
             "<i>Batafsil ko'rish uchun ismga bosing.</i>\n"]
    kb_rows = []
    for i, f in enumerate(page_items, page * PAGE_SIZE + 1):
        u = get_user(f["user_id"]) or {}
        name = u.get("full_name") or f"ID {f['user_id']}"
        btn_label = f"{i}. {name} \u2014 {f['score']} ball"
        kb_rows.append([InlineKeyboardButton(btn_label[:64], callback_data=f"usercard_{f['user_id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("\u2b05\ufe0f Oldingi", callback_data=f"flagpage_{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("Keyingi \u27a1\ufe0f", callback_data=f"flagpage_{page + 1}"))
    if nav:
        kb_rows.append(nav)
    return "\n".join(lines), InlineKeyboardMarkup(kb_rows)


async def show_flagged(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    text, markup = render_flagged(page)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def flagpage_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    page = int(query.data.rsplit("_", 1)[1])
    await show_flagged(update, context, page)


# ============================= FOYDALANUVCHINI QIDIRISH (ADMIN) =============================

async def usersearch_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001F50E Qidirmoqchi bo'lgan foydalanuvchining biror xabarini FORWARD qiling, "
        "yoki uning user_id raqamini yozing.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return USER_SEARCH_WAIT


async def usersearch_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        return USER_SEARCH_WAIT

    if not get_user(target_id):
        await update.message.reply_text("\u26a0\ufe0f Bu foydalanuvchi haqida ma'lumot topilmadi (u botdan hali foydalanmagan).", reply_markup=main_menu_keyboard(update.effective_user.id))
        return ConversationHandler.END

    await update.message.reply_text("Topildi:", reply_markup=main_menu_keyboard(update.effective_user.id))
    await show_user_card(update, context, target_id)
    return ConversationHandler.END


async def usersearch_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END


# ============================= SOZLAMALAR (ADMIN) =============================

def settings_menu_markup() -> InlineKeyboardMarkup:
    rows = []
    for key, meta in SETTINGS_FIELDS.items():
        value = get_setting(key)
        if meta["kind"] == "bool":
            display = "\u2705 Yoqilgan" if value == "1" else "\u274c O'chirilgan"
            rows.append([InlineKeyboardButton(f"{meta['label']}: {display}", callback_data=f"toggleset_{key}")])
        else:
            rows.append([InlineKeyboardButton(f"{meta['label']}: {value}", callback_data=f"editset_{key}")])
    return InlineKeyboardMarkup(rows)


async def toggle_setting_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    key = query.data[len("toggleset_"):]
    current = get_setting(key)
    set_setting(key, "0" if current == "1" else "1")
    await query.edit_message_text(
        "\u2699\ufe0f <b>Sozlamalar</b>\n\nO'zgartirmoqchi bo'lgan qiymatni tanlang:\n"
        "<i>(o'zgarish darhol, botni qayta ishga tushirmasdan, hamma joyda kuchga kiradi)</i>",
        parse_mode=ParseMode.HTML, reply_markup=settings_menu_markup(),
    )


async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\u2699\ufe0f <b>Sozlamalar</b>\n\nO'zgartirmoqchi bo'lgan qiymatni tanlang:\n"
        "<i>(o'zgarish darhol, botni qayta ishga tushirmasdan, hamma joyda kuchga kiradi)</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=settings_menu_markup(),
    )


async def admin_setting_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return ConversationHandler.END
    key = query.data[len("editset_"):]
    meta = SETTINGS_FIELDS.get(key)
    if not meta:
        return ConversationHandler.END
    context.user_data["editing_setting"] = key
    await query.message.reply_text(
        f"{meta['label']}\nJoriy qiymat: <b>{esc(get_setting(key))}</b>\n\n{meta['hint']}",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADMIN_SETTING_VALUE


async def admin_setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END

    key = context.user_data.get("editing_setting")
    meta = SETTINGS_FIELDS.get(key) if key else None
    if not meta:
        return ConversationHandler.END

    raw = (update.message.text or "").strip()
    kind = meta["kind"]

    if kind in ("int", "percent"):
        if not raw.isdigit():
            await update.message.reply_text("\u26a0\ufe0f Faqat butun son kiriting. Qaytadan yozing:")
            return ADMIN_SETTING_VALUE
        value = raw
        if kind == "percent" and not (0 <= int(raw) <= 100):
            await update.message.reply_text("\u26a0\ufe0f 0 dan 100 gacha son bo'lishi kerak. Qaytadan yozing:")
            return ADMIN_SETTING_VALUE
    elif kind == "card":
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 16:
            await update.message.reply_text("\u26a0\ufe0f Karta raqami 16 xonali bo'lishi kerak. Qaytadan yozing:")
            return ADMIN_SETTING_VALUE
        value = digits
    elif kind == "text":
        if not raw:
            await update.message.reply_text("\u26a0\ufe0f Bo'sh bo'lishi mumkin emas. Qaytadan yozing:")
            return ADMIN_SETTING_VALUE
        if len(raw) > 40:
            await update.message.reply_text(f"\u26a0\ufe0f Tugma matni juda uzun ({len(raw)} belgi). 40 belgidan qisqaroq yozing:")
            return ADMIN_SETTING_VALUE
        value = raw
    else:
        value = raw

    set_setting(key, value)
    context.user_data.pop("editing_setting", None)
    await update.message.reply_text(
        f"\u2705 {meta['label']} yangilandi: <b>{esc(value)}</b>\n\n"
        f"Bu o'zgarish hozirdan boshlab BARCHA joyda kuchga kirdi.",
        parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(update.effective_user.id),
    )
    return ConversationHandler.END


async def admin_setting_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("editing_setting", None)
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END


# ============================= BLOKLANGAN RAQAMLAR (ADMIN) =============================

def render_blocked(rows: list, page: int, total: int):
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    lines = [f"\U0001F6AB <b>Bloklangan raqamlar</b> (sahifa {page + 1}/{total_pages}, jami {total} ta):",
             "<i>Batafsil ko'rish uchun raqamga bosing.</i>\n"]
    kb_rows = [[InlineKeyboardButton("\u2795 Yangi raqam bloklash", callback_data="block_new")]]
    if not rows:
        lines.append("<i>Hozircha bloklangan raqam yo'q.</i>")
    for r in rows:
        digits = re.sub(r"\D", "", r["phone"])
        lines.append(f"\u2022 <code>{esc(r['phone'])}</code> ({r['blocked_at'][:10]})")
        kb_rows.append([InlineKeyboardButton(f"\U0001F4DE {r['phone']}", callback_data=f"blockcard_{digits}_{page}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("\u2b05\ufe0f Oldingi", callback_data=f"blockpage_{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("Keyingi \u27a1\ufe0f", callback_data=f"blockpage_{page + 1}"))
    if nav:
        kb_rows.append(nav)
    return "\n".join(lines), InlineKeyboardMarkup(kb_rows)


async def show_blocked(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    total = count_blocked_phones()
    rows = list_blocked_phones_page(page * PAGE_SIZE)
    text, markup = render_blocked(rows, page, total)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def blockpage_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    page = int(query.data.rsplit("_", 1)[1])
    await show_blocked(update, context, page)


def render_block_card(phone: str, page: int) -> tuple:
    info = get_blocked_phone(phone)
    if not info:
        return "\u2139\ufe0f Bu raqam endi bloklangan ro'yxatda emas.", InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Ro'yxatga qaytish", callback_data=f"blockpage_{page}")]])
    blocked_by_line = user_link(info["blocked_by"], None) if info.get("blocked_by") else "noma'lum"
    text = (
        f"\U0001F4DE <b>{esc(phone)}</b>\n\n"
        f"\U0001F4DD Sabab: {esc(info.get('reason') or '—')}\n"
        f"\U0001F464 Kim bloklagan: {blocked_by_line}\n"
        f"\U0001F4C5 Qachon: {info['blocked_at'][:16]}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u2705 Blokdan chiqarish", callback_data=f"unblock_{re.sub(r'[^0-9]', '', phone)}_{page}")],
        [InlineKeyboardButton("\u2b05\ufe0f Ro'yxatga qaytish", callback_data=f"blockpage_{page}")],
    ])
    return text, keyboard


async def blockcard_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    _, digits, page = query.data.split("_")
    phone = "+" + digits
    text, keyboard = render_block_card(phone, int(page))
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def unblock_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    _, digits, page = query.data.split("_")
    phone = "+" + digits
    unblock_phone(phone)
    await query.answer("Blokdan chiqarildi \u2705")
    await show_blocked(update, context, int(page))


async def block_new_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return ConversationHandler.END
    await query.message.reply_text("\U0001F4DE Bloklamoqchi bo'lgan telefon raqamini yozing (+998...):", reply_markup=ReplyKeyboardRemove())
    return ADMIN_BLOCK_PHONE


async def block_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    phone = normalize_phone(raw)
    if not phone:
        await update.message.reply_text("\u26a0\ufe0f Raqam formati noto'g'ri. Masalan: +998901234567. Qaytadan yozing:")
        return ADMIN_BLOCK_PHONE
    context.user_data["block_phone_tmp"] = phone
    await update.message.reply_text("Sababini yozing (masalan: \"Yolg'on e'lon, pul so'ragan\"):")
    return ADMIN_BLOCK_REASON


async def block_reason_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    reason = (update.message.text or "").strip()
    if not reason:
        await update.message.reply_text("\u26a0\ufe0f Sabab bo'sh bo'lishi mumkin emas. Qaytadan yozing:")
        return ADMIN_BLOCK_REASON
    phone = context.user_data.pop("block_phone_tmp", None)
    if not phone:
        return ConversationHandler.END
    block_phone(phone, reason, update.effective_user.id)
    await post_block_announcement(context)
    await update.message.reply_text(f"\U0001F6AB <code>{esc(phone)}</code> bloklandi.", parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(update.effective_user.id))
    await show_blocked(update, context, 0)
    return ConversationHandler.END


async def block_flow_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("block_phone_tmp", None)
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END


async def blockask_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """E'lonni rad etgandan keyin, admin xohlasa telefon raqamni ham
    bloklashi mumkin - bitta qo'shimcha tugma bilan, alohida bosqichsiz."""
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    _, action, listing_id = query.data.split("_", 2)
    listing_id = int(listing_id)
    if action == "no":
        await query.edit_message_reply_markup(reply_markup=None)
        return
    listing = get_listing(listing_id)
    if not listing:
        await query.edit_message_text("\u26a0\ufe0f E'lon topilmadi.")
        return
    block_phone(listing["telefon"], f"E'lon #{listing_id} rad etilgani sababli", query.from_user.id)
    await post_block_announcement(context)
    await query.edit_message_text(f"\U0001F6AB <code>{esc(listing['telefon'])}</code> bloklandi.", parse_mode=ParseMode.HTML)



