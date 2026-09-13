"""
Firibgar-rieltor aniqlash tizimi (bir xil raqam/matn bilan ko'plab e'lon
joylashni kuzatish) + suhbatlarni majburan qayta tiklash uchun registr.
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

# ============================= FIRIBGAR-RIELTOR ANIQLASH TIZIMI =============================

BURST_COUNT = 5
BURST_MINUTES = 3
DAILY_REVEAL_ALERT = 8
WEEKLY_REVEAL_ALERT = 25
RISK_THRESHOLD = 40


def log_phone_reveal(user_id: int, listing_id: int) -> None:
    conn = db()
    conn.execute("INSERT INTO phone_reveals (user_id, listing_id, revealed_at) VALUES (?, ?, ?)", (user_id, listing_id, now_str()))
    conn.commit()
    conn.close()


def log_paywall_hit(user_id: int, listing_id) -> None:
    conn = db()
    conn.execute("INSERT INTO paywall_hits (user_id, listing_id, hit_at) VALUES (?, ?, ?)", (user_id, listing_id, now_str()))
    conn.commit()
    conn.close()


def log_phone_check_use(user_id: int) -> None:
    conn = db()
    conn.execute("INSERT INTO phone_check_uses (user_id, checked_at) VALUES (?, ?)", (user_id, now_str()))
    conn.commit()
    conn.close()


def count_reveals_in_period(date_from: str, date_to_exclusive: str) -> int:
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM phone_reveals WHERE revealed_at >= ? AND revealed_at < ?", (date_from, date_to_exclusive)
    ).fetchone()["c"]
    conn.close()
    return n


def count_paywall_hits_in_period(date_from: str, date_to_exclusive: str) -> int:
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM paywall_hits WHERE hit_at >= ? AND hit_at < ?", (date_from, date_to_exclusive)
    ).fetchone()["c"]
    conn.close()
    return n


def count_phone_checks_in_period(date_from: str, date_to_exclusive: str) -> int:
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM phone_check_uses WHERE checked_at >= ? AND checked_at < ?", (date_from, date_to_exclusive)
    ).fetchone()["c"]
    conn.close()
    return n


def count_location_alerts_in_period(date_from: str, date_to_exclusive: str) -> int:
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM location_alerts WHERE created_at >= ? AND created_at < ?", (date_from, date_to_exclusive)
    ).fetchone()["c"]
    conn.close()
    return n


def count_listings_by_source_in_period(date_from: str, date_to_exclusive: str) -> dict:
    """E'lonlarni kim joylashtirganini ajratadi: haqiqiy foydalanuvchi (organik
    ekotizim o'sishi) yoki admin/moderator (aggregatsiya). Biznes uchun muhim
    ko'rsatkich - odamlar o'zlari qanchalik faol e'lon berayotganini ko'rsatadi."""
    conn = db()
    rows = conn.execute(
        "SELECT user_id, COUNT(*) c FROM listings WHERE created_at >= ? AND created_at < ? GROUP BY user_id",
        (date_from, date_to_exclusive),
    ).fetchall()
    conn.close()
    user_count, staff_count = 0, 0
    for r in rows:
        if is_staff(r["user_id"]):
            staff_count += r["c"]
        else:
            user_count += r["c"]
    return {"user": user_count, "staff": staff_count}


def count_listings_by_type_in_period(date_from: str, date_to_exclusive: str) -> dict:
    """E'lonlarni pullik/bepul bo'yicha ajratadi (price_charged > 0 - pullik)."""
    conn = db()
    row = conn.execute(
        """SELECT
               SUM(CASE WHEN COALESCE(price_charged,0) > 0 THEN 1 ELSE 0 END) AS paid,
               SUM(CASE WHEN COALESCE(price_charged,0) = 0 THEN 1 ELSE 0 END) AS free
           FROM listings WHERE created_at >= ? AND created_at < ?""",
        (date_from, date_to_exclusive),
    ).fetchone()
    conn.close()
    return {"paid": row["paid"] or 0, "free": row["free"] or 0}


def get_multi_location_posters(min_locations: int = 2) -> list:
    """Har bir foydalanuvchi NECHTA XILMA-XIL hududda (joylashuvda) e'lon
    berganini hisoblaydi (bir xil nuqta qayta-qayta hisoblanmasligi uchun
    koordinatalar 3 xonagacha yaxlitlanadi). min_locations dan kam bo'lganlar
    ro'yxatga kiritilmaydi - natija eng ko'pdan kamiga saralangan."""
    conn = db()
    rows = conn.execute(
        "SELECT user_id, latitude, longitude FROM listings WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
    ).fetchall()
    conn.close()
    per_user: dict = {}
    for r in rows:
        key = (round(r["latitude"], 3), round(r["longitude"], 3))
        per_user.setdefault(r["user_id"], set()).add(key)
    result = [(uid, len(locs)) for uid, locs in per_user.items() if len(locs) >= min_locations]
    result.sort(key=lambda x: x[1], reverse=True)
    return result


def count_reveals_since(user_id: int, since: datetime) -> int:
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM phone_reveals WHERE user_id = ? AND revealed_at >= ?",
        (user_id, since.strftime("%Y-%m-%d %H:%M:%S")),
    ).fetchone()["c"]
    conn.close()
    return n


def total_reveals(user_id: int) -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM phone_reveals WHERE user_id = ?", (user_id,)).fetchone()["c"]
    conn.close()
    return n


def has_burst_activity(user_id: int) -> bool:
    """Ketma-ket BURST_COUNT ta ko'rish BURST_MINUTES daqiqadan kam vaqt ichida bo'lganmi?"""
    conn = db()
    rows = conn.execute(
        "SELECT revealed_at FROM phone_reveals WHERE user_id = ? ORDER BY revealed_at ASC", (user_id,)
    ).fetchall()
    conn.close()
    times = [t for t in (safe_parse_dt(r["revealed_at"]) for r in rows) if t is not None]
    for i in range(len(times) - BURST_COUNT + 1):
        window = times[i + BURST_COUNT - 1] - times[i]
        if window <= timedelta(minutes=BURST_MINUTES):
            return True
    return False


def count_approved_subscriptions(user_id: int) -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM subscriptions WHERE user_id = ? AND status = 'approved'", (user_id,)).fetchone()["c"]
    conn.close()
    return n


def compute_risk_score(user_id: int) -> dict:
    now = datetime.now()
    daily = count_reveals_since(user_id, now - timedelta(days=1))
    weekly = count_reveals_since(user_id, now - timedelta(days=7))
    burst = has_burst_activity(user_id)
    subs_count = count_approved_subscriptions(user_id)
    lifetime = total_reveals(user_id)

    score = 0
    reasons = []
    if daily > DAILY_REVEAL_ALERT:
        score += 40
        reasons.append(f"24 soatda {daily} ta ko'rish (chegara: {DAILY_REVEAL_ALERT})")
    if burst:
        score += 35
        reasons.append(f"{BURST_COUNT} ta ko'rish {BURST_MINUTES} daqiqadan kam vaqtda")
    if weekly > WEEKLY_REVEAL_ALERT:
        score += 25
        reasons.append(f"7 kunda {weekly} ta ko'rish (chegara: {WEEKLY_REVEAL_ALERT})")
    if subs_count >= 3 and lifetime > 60:
        score += 20
        reasons.append(f"{subs_count} marta obuna sotib olgan, jami {lifetime} ta ko'rish")

    return {"score": score, "reasons": reasons, "daily": daily, "weekly": weekly, "lifetime": lifetime, "subs_count": subs_count}


def get_flagged_users(min_score: int = RISK_THRESHOLD, limit: int = 200) -> list:
    """Faol (yaqinda ko'rish qilgan) foydalanuvchilar orasidan xavf balli
    yuqori bo'lganlarni topadi. Katta bazalarda samaradorlik uchun so'nggi
    30 kun ichida ko'rish qilganlar bilan cheklanadi."""
    conn = db()
    since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT DISTINCT user_id FROM phone_reveals WHERE revealed_at >= ? LIMIT ?", (since, limit)
    ).fetchall()
    conn.close()
    flagged = []
    for r in rows:
        info = compute_risk_score(r["user_id"])
        if info["score"] >= min_score:
            info["user_id"] = r["user_id"]
            flagged.append(info)
    flagged.sort(key=lambda x: x["score"], reverse=True)
    return flagged


def is_banned(user_id: int) -> bool:
    conn = db()
    row = conn.execute("SELECT 1 FROM banned_users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row is not None


def ban_user(user_id: int, reason: str, banned_by: int) -> None:
    conn = db()
    conn.execute("INSERT OR REPLACE INTO banned_users (user_id, reason, banned_by, banned_at) VALUES (?, ?, ?, ?)", (user_id, reason, banned_by, now_str()))
    conn.commit()
    conn.close()


def unban_user(user_id: int) -> None:
    conn = db()
    conn.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def count_reports_made(user_id: int) -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM listing_reports WHERE user_id = ?", (user_id,)).fetchone()["c"]
    conn.close()
    return n


def count_reports_received(user_id: int) -> int:
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM listing_reports WHERE listing_id IN (SELECT id FROM listings WHERE user_id = ?)", (user_id,)
    ).fetchone()["c"]
    conn.close()
    return n


def count_listings_by_user(user_id: int) -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM listings WHERE user_id = ?", (user_id,)).fetchone()["c"]
    conn.close()
    return n


def user_link(user_id: int, name) -> str:
    label = esc(name) if name else f"ID {user_id}"
    return f'<a href="tg://user?id={user_id}">{label}</a>'


FRAUD_SHOCK_MESSAGE = (
    "\u26d4 <b>SIZGA BOTDAN FOYDALANISH TAQIQLANDI</b>\n\n"
    "Siz yuborgan to'lov cheki <b>soxta yoki avval ishlatilgan</b> chek sifatida aniqlandi.\n\n"
    "Bu \u2014 firibgarlik harakati sifatida qayd etildi. Hisobingiz butunlay cheklandi va "
    "endi botning hech qanday funksiyasidan (e'lon berish, obuna sotib olish) foydalana olmaysiz.\n\n"
    "Agar bu xato deb hisoblasangiz, quyidagi admin bilan bog'laning va haqiqiy to'lov isbotini taqdim eting."
)


async def send_with_retry(func, *args, retries: int = 3, delay: float = 2.0, **kwargs):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return await func(*args, **kwargs)
        except BadRequest:
            # BadRequest - doimiy (permanent) xato (masalan noto'g'ri so'rov,
            # maxfiylik cheklovi va h.k.) - qayta urinish yordam bermaydi,
            # darhol yuqoriga uzatamiz (BadRequest texnik sabablarga ko'ra
            # NetworkError'dan meros oladi, shuning uchun buni ALOHIDA ushlashimiz kerak).
            raise
        except (TimedOut, NetworkError) as e:
            last_exc = e
            logger.warning("Tarmoq xatosi (urinish %s/%s): %s", attempt, retries, e)
            if attempt < retries:
                await asyncio.sleep(delay)
    raise last_exc


def profile_link_button(user_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton("\U0001F464 Profilga o'tish", url=f"tg://user?id={user_id}")


async def send_with_privacy_fallback(func, *args, full_markup: InlineKeyboardMarkup, fallback_markup: InlineKeyboardMarkup, **kwargs):
    """Tugmalar orasida \"Profilga o'tish\" bo'lsa, ba'zi foydalanuvchilarning
    maxfiylik sozlamalari bu tugmani rad etishi mumkin (BUTTON_USER_PRIVACY_RESTRICTED).
    Shunday holatda, avtomatik ravishda o'sha tugmasiz qayta yuboradi."""
    try:
        return await send_with_retry(func, *args, reply_markup=full_markup, **kwargs)
    except BadRequest as e:
        if "button_user_privacy_restricted" in str(e).lower():
            return await send_with_retry(func, *args, reply_markup=fallback_markup, **kwargs)
        raise


async def send_photos(context: ContextTypes.DEFAULT_TYPE, chat_id: int, photos: list) -> bool:
    try:
        if len(photos) == 1:
            await send_with_retry(context.bot.send_photo, chat_id, photos[0])
        else:
            media = [InputMediaPhoto(r) for r in photos]
            await send_with_retry(context.bot.send_media_group, chat_id, media)
        return True
    except Exception:
        logger.exception("Rasmlarni yuborishda xatolik (chat_id=%s)", chat_id)
        return False


RESERVED_MENU_TEXTS = {
    BTN_ELON, BTN_LISTINGS, BTN_SUBSCRIPTION, BTN_HELP, BTN_CHECK_PHONE, BTN_LOCATION_ALERT, BTN_MY_LOCATIONS, BTN_CHANNEL,
    BTN_STATS, BTN_SUBSCRIBERS, BTN_SETTINGS, BTN_PENDING, BTN_BLOCKED, BTN_QUICK,
    BTN_MODERATORS, BTN_FLAGGED, BTN_USER_SEARCH, BTN_LISTINGS_MAP, BTN_ADMIN_PANEL, BTN_SUBARENDA,
}


_CONV_REGISTRY: dict = {}  # PicklePersistence bot_data'ni qayta yuklaganda o'chirib
                            # yubormasligi uchun, oddiy Python global o'zgaruvchisi ishlatiladi.


def register_conv(name: str, conv) -> None:
    _CONV_REGISTRY[name] = conv


def force_reset_conversation(context: ContextTypes.DEFAULT_TYPE, conv_name: str, user_id: int) -> None:
    """Agar foydalanuvchi biror ko'p-bosqichli jarayonda (masalan Manzil,
    Mo'ljal so'ralayotganda) \"qolib ketgan\" bo'lsa - bu funksiya o'sha ESKI,
    tugallanmagan holatni MAJBURIY tozalaydi. Shu orqali, foydalanuvchi QAYSI
    bosqichda qolib ketmasin, kanal orqali \"E'lon berish\"ni qayta bossa,
    tizim HAR DOIM to'g'ri, boshidan qayta boshlay oladi."""
    conv = _CONV_REGISTRY.get(conv_name)
    if conv is None:
        return
    key = (user_id, user_id)  # shaxsiy chatda chat_id == user_id
    conv._conversations.pop(key, None)
    job = conv.timeout_jobs.pop(key, None) if hasattr(conv, "timeout_jobs") else None
    if job:
        job.schedule_removal()


async def try_escape_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.message or not update.message.text:
        return False
    if update.message.text.strip() not in RESERVED_MENU_TEXTS:
        return False
    for key in ("pending_reject", "editing_setting", "gift_target", "block_phone_tmp"):
        context.user_data.pop(key, None)
    await update.message.reply_text(
        "\u21a9\ufe0f Joriy jarayon bekor qilindi. Endi kerakli tugmani QAYTA bosing.",
        reply_markup=main_menu_keyboard(update.effective_user.id),
    )
    return True


async def remind_text(update: Update, context: ContextTypes.DEFAULT_TYPE, state: int) -> int:
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    await update.message.reply_text("\u26a0\ufe0f Iltimos, matn ko'rinishida javob bering.")
    return state


async def remind_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE, state: int) -> int:
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    await update.message.reply_text("\u26a0\ufe0f Iltimos, tepadagi tugmalardan birini bosing.")
    return state



