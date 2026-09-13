"""
Admin moderatsiyasi - e'lon/obuna so'rovlarini tasdiqlash yoki rad etish.
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
from bot.location_alerts import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

# ============================= ADMIN MODERATSIYASI =============================

def log_channel_post(listing_id: int, message_id: int) -> None:
    conn = db()
    conn.execute("INSERT INTO channel_posts (listing_id, message_id, posted_at) VALUES (?, ?, ?)", (listing_id, message_id, now_str()))
    conn.commit()
    conn.close()


async def send_listing_to_channel(context: ContextTypes.DEFAULT_TYPE, listing: dict):
    caption = build_caption(listing, context.bot.username)
    keyboard = channel_keyboard(listing["id"], context.bot.username, listing.get("latitude"), listing.get("longitude"))
    ok = await send_photos(context, CHANNEL_ID, listing["photos"])
    if not ok:
        return None
    try:
        sent = await send_with_retry(context.bot.send_message, CHANNEL_ID, caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        log_channel_post(listing["id"], sent.message_id)
        return sent.message_id
    except Exception:
        logger.exception("Kanalga matn+tugma xabarini yuborishda xatolik")
        return None


async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    _, _, kind, obj_id = query.data.split("_", 3)
    obj_id = int(obj_id)
    if kind == "listing":
        await approve_listing(update, context, obj_id)
    else:
        await approve_sub(update, context, obj_id)


async def approve_listing(update: Update, context: ContextTypes.DEFAULT_TYPE, listing_id: int):
    query = update.callback_query
    listing = get_listing(listing_id)
    if not listing:
        await query.message.reply_text("\u26a0\ufe0f E'lon topilmadi.")
        return
    if listing["status"] != "pending":
        await query.message.reply_text(f"Bu e'lon allaqachon ko'rib chiqilgan (holat: {listing['status']}).")
        return

    channel_msg_id = await send_listing_to_channel(context, listing)
    if channel_msg_id is None:
        await query.message.reply_text("\u26a0\ufe0f Kanalga joylashda xatolik yuz berdi (tarmoq muammosi). Hech narsa joylanmadi \u2014 \u00abTasdiqlash\u00bb tugmasini qaytadan bosing.")
        return

    update_listing_status(listing_id, "approved", channel_msg_id=channel_msg_id)
    listing["channel_msg_id"] = channel_msg_id
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"\u2705 E'lon #{listing_id} kanalga joylandi.")

    await notify_location_alert_matches(context, listing)

    try:
        link = f"https://t.me/{CHANNEL_USERNAME}" if CHANNEL_USERNAME else None
        msg = "\u2705 Sizning e'loningiz tasdiqlandi va kanalga joylandi!"
        if link:
            msg += f"\n{link}"
        await context.bot.send_message(listing["user_id"], msg)
    except Exception:
        logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi")


async def approve_sub(update: Update, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    query = update.callback_query
    sub = get_subscription(sub_id)
    if not sub:
        await query.message.reply_text("\u26a0\ufe0f Obuna so'rovi topilmadi.")
        return
    if sub["status"] != "pending":
        await query.message.reply_text(f"Bu so'rov allaqachon ko'rib chiqilgan (holat: {sub['status']}).")
        return

    user_id, expire = approve_subscription(sub_id)
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"\u2705 Obuna #{sub_id} tasdiqlandi ({expire[:10]} gacha).")

    text = (
        f"\u2705 Limitingiz faollashtirildi!\nMuddati: <b>{expire[:10]}</b> gacha.\n\n"
        "Endi kanaldagi istalgan e'londa \u00abUy egasi raqami\u00bb tugmasini bosib, raqamni ko'rishingiz mumkin."
    )
    target_listing_id = sub.get("target_listing_id")
    if target_listing_id:
        listing = get_listing(target_listing_id)
        if listing and listing["status"] == "approved":
            text += "\n\n" + phone_reveal_text(listing)

    try:
        await context.bot.send_message(user_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception:
        logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi")


async def admin_reject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return ConversationHandler.END
    _, _, kind, obj_id = query.data.split("_", 3)
    context.user_data["pending_reject"] = {"kind": kind, "id": int(obj_id)}
    await query.message.reply_text("\u270D\ufe0f Rad etish sababini yozing (bu matn foydalanuvchiga yuboriladi):", reply_markup=ReplyKeyboardRemove())
    return ADMIN_REASON


async def admin_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END

    reason = (update.message.text or "").strip()
    if not reason:
        await update.message.reply_text("\u26a0\ufe0f Sabab bo'sh bo'lishi mumkin emas. Qaytadan yozing:")
        return ADMIN_REASON

    pending = context.user_data.get("pending_reject")
    if not pending:
        return ConversationHandler.END

    if pending["kind"] == "listing":
        listing_id = pending["id"]
        listing = get_listing(listing_id)
        if listing and listing["status"] == "pending":
            update_listing_status(listing_id, "rejected", reason=reason)
            await update.message.reply_text(f"\u274c E'lon #{listing_id} rad etildi.", reply_markup=main_menu_keyboard(update.effective_user.id))
            try:
                await context.bot.send_message(
                    listing["user_id"],
                    f"\u274c Sizning e'loningiz (#{listing_id}) rad etildi.\n\U0001F4DD Sabab: {esc(reason)}\n\nSavollar bo'lsa, @{ADMIN_USERNAME} ga murojaat qiling.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi")

            block_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("\U0001F6AB Ha, raqamni ham bloklash", callback_data=f"blockask_yes_{listing_id}"),
                  InlineKeyboardButton("\u27a1\ufe0f Yo'q", callback_data=f"blockask_no_{listing_id}")]]
            )
            await update.message.reply_text(
                f"Bu bilan birga <code>{esc(listing['telefon'])}</code> raqamini ham bloklaymizmi?",
                parse_mode=ParseMode.HTML, reply_markup=block_keyboard,
            )
            ban_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("\U0001F6AB Firibgar \u2014 hisobini cheklash", callback_data=f"fraudban_{listing['user_id']}"),
                  InlineKeyboardButton("\u27a1\ufe0f Yo'q", callback_data="fraudban_skip")]]
            )
            await update.message.reply_text(
                "Agar bu soxta chek/firibgarlik bo'lsa, foydalanuvchining hisobini ham cheklaymizmi?",
                reply_markup=ban_keyboard,
            )
        else:
            await update.message.reply_text("Bu e'lon allaqachon ko'rib chiqilgan yoki topilmadi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    else:
        sub_id = pending["id"]
        sub = get_subscription(sub_id)
        if sub and sub["status"] == "pending":
            reject_subscription(sub_id, reason)
            await update.message.reply_text(f"\u274c Obuna so'rovi #{sub_id} rad etildi.", reply_markup=main_menu_keyboard(update.effective_user.id))
            try:
                await context.bot.send_message(
                    sub["user_id"],
                    f"\u274c Obuna so'rovingiz rad etildi.\n\U0001F4DD Sabab: {esc(reason)}\n\nSavollar bo'lsa, @{ADMIN_USERNAME} ga murojaat qiling.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi")
            ban_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("\U0001F6AB Firibgar \u2014 hisobini cheklash", callback_data=f"fraudban_{sub['user_id']}"),
                  InlineKeyboardButton("\u27a1\ufe0f Yo'q", callback_data="fraudban_skip")]]
            )
            await update.message.reply_text(
                "Agar bu soxta chek/firibgarlik bo'lsa, foydalanuvchining hisobini ham cheklaymizmi?",
                reply_markup=ban_keyboard,
            )
        else:
            await update.message.reply_text("Bu so'rov allaqachon ko'rib chiqilgan yoki topilmadi.", reply_markup=main_menu_keyboard(update.effective_user.id))

    context.user_data.pop("pending_reject", None)
    return ConversationHandler.END


async def fraudban_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    if query.data == "fraudban_skip":
        await query.edit_message_reply_markup(reply_markup=None)
        return
    target_id = int(query.data.rsplit("_", 1)[1])
    ban_user(target_id, "Soxta chek / firibgarlik sababli cheklandi", query.from_user.id)
    try:
        await context.bot.send_message(target_id, FRAUD_SHOCK_MESSAGE, parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("Firibgarga ogohlantirish xabarini yuborib bo'lmadi")
    await query.edit_message_text(f"\U0001F6AB Foydalanuvchi (user_id: {target_id}) botdan cheklandi.")


async def admin_reject_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_reject", None)
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END



