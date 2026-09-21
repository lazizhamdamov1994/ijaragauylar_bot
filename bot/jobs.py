"""
Fondagi rejalashtirilgan vazifalar (APScheduler orqali, PTB JobQueue).
"""
import asyncio
import difflib
import html
import io
import json
import logging
import os
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

from common.ai import ai_features_enabled, ai_generate_ops_report, ai_review_own_accuracy, ai_usage_summary
from common.db import ai_accuracy_summary
from common.config import ADMIN_IDS, ADMIN_USERNAME, BOT_TOKEN as TOKEN, CARD_HOLDER, CHANNEL_ID, CHANNEL_USERNAME, DASHBOARD_URL, DB_PATH, DEFAULT_SETTINGS as INITIAL_SETTINGS, MAX_DAILY_LISTINGS, MOD_DAILY_LISTINGS, STALE_CHECK_DAYS

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

# ============================= FONDAGI VAZIFALAR (JOBS) =============================

async def job_expiry_reminders(context: ContextTypes.DEFAULT_TYPE):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    conn = db()
    rows = conn.execute("SELECT * FROM subscriptions WHERE status = 'approved' AND substr(expire_at, 1, 10) = ?", (tomorrow,)).fetchall()
    conn.close()
    for row in rows:
        try:
            await context.bot.send_message(
                row["user_id"],
                f"\u23f0 Limitingiz ertaga (<b>{row['expire_at'][:10]}</b>) tugaydi.\n\nUzluksiz foydalanish uchun hoziroq yangilang \U0001F447",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F513 Limitni yangilash", callback_data="buy_subscription")]]),
            )
        except Exception:
            logger.exception("Eslatma yuborib bo'lmadi: user_id=%s", row["user_id"])


async def job_monthly_report(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_start = (first_of_this_month - timedelta(days=1)).replace(day=1)
    s = stats_for_period(last_month_start.strftime("%Y-%m-%d %H:%M:%S"), first_of_this_month.strftime("%Y-%m-%d %H:%M:%S"))
    period_label = last_month_start.strftime("%Y-%m")
    text = (
        f"\U0001F4C8 <b>Oylik hisobot \u2014 {period_label}</b>\n\n"
        f"\U0001F4DD Jami e'lonlar: {s['listings_total']} (\u2705 {s['listings_approved']} / \u274c {s['listings_rejected']})\n"
        f"\U0001F4B0 E'londan tushum: {s['listings_income']:,} so'm\n\n"
        f"\U0001F4B3 Obuna so'rovlari: {s['subs_total']} (\u2705 {s['subs_approved']})\n"
        f"\U0001F4B0 Obunadan tushum: {s['subs_income']:,} so'm\n\n"
        f"\U0001F4B5 Umumiy tushum: {s['listings_income'] + s['subs_income']:,} so'm\n"
        f"\U0001F465 Jami foydalanuvchilar: {s['users_total']}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, parse_mode=ParseMode.HTML)
        except Exception:
            logger.exception("Oylik hisobotni yuborib bo'lmadi: admin_id=%s", admin_id)


def collect_ops_report_stats() -> dict:
    """Bugungi (0:00'dan hozirgacha) asosiy raqamlarni - o'sish, daromad,
    AI firibgarlik/chek belgilari, AI xarajati - bitta joyda yig'adi.
    `ai_scam_warning`/`receipt_warning` ustunlari (common/db.py) endi har
    bir moderatsiya bosqichida to'ldirib boriladi - shu orqali "AI necha
    ta shubhali e'lon topdi" kabi raqamlar HAQIQIY, ilgari bu ma'lumot
    hech qayerda saqlanmagani uchun mavjud emas edi."""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    now_str_ = now.strftime("%Y-%m-%d %H:%M:%S")

    s = stats_for_period(today_start, now_str_)
    new_users = count_new_users_in_period(today_start, now_str_)

    conn = db()
    scam_flags = conn.execute(
        "SELECT COUNT(*) c FROM listings WHERE ai_scam_warning IS NOT NULL AND created_at >= ?", (today_start,)
    ).fetchone()["c"]
    receipt_mismatches = (
        conn.execute(
            "SELECT COUNT(*) c FROM listings WHERE receipt_warning IS NOT NULL AND created_at >= ?", (today_start,)
        ).fetchone()["c"]
        + conn.execute(
            "SELECT COUNT(*) c FROM subscriptions WHERE receipt_warning IS NOT NULL AND created_at >= ?", (today_start,)
        ).fetchone()["c"]
    )
    conn.close()

    ai_cost = ai_usage_summary(1).get("cost_usd", 0) or 0
    return {
        **s, "new_users": new_users, "scam_flags": scam_flags,
        "receipt_mismatches": receipt_mismatches, "ai_cost_usd": ai_cost,
    }


def _format_ops_stats_text(s: dict) -> str:
    total_income = s["listings_income"] + s["subs_income"]
    return (
        f"Sana: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"Yangi e'lonlar: {s['listings_total']} (tasdiqlangan: {s['listings_approved']}, "
        f"rad etilgan: {s['listings_rejected']}, kutilmoqda: {s['listings_pending']})\n"
        f"E'londan tushum: {s['listings_income']:,} so'm\n"
        f"Yangi Limit (obuna) so'rovlari: {s['subs_total']} (tasdiqlangan: {s['subs_approved']})\n"
        f"Obunadan tushum: {s['subs_income']:,} so'm\n"
        f"Bugungi umumiy tushum: {total_income:,} so'm\n"
        f"Yangi foydalanuvchilar: {s['new_users']} (jami: {s['users_total']})\n"
        f"AI firibgarlik belgisi qo'ygan e'lonlar: {s['scam_flags']}\n"
        f"AI to'lov chekida nomuvofiqlik topgan holatlar: {s['receipt_mismatches']}\n"
        f"Bugungi AI xarajati: ${s['ai_cost_usd']:.3f}"
    )


async def job_ai_daily_report(context: ContextTypes.DEFAULT_TYPE):
    """Har kuni kechqurun adminlarga qisqa hisobot yuboradi - AI yoqilgan
    bo'lsa, raqamlar asosida yozilgan tahlil+tavsiya bilan; AI o'chirilgan
    yoki xatolik bersa (None qaytsa), sharhsiz raqamlar bilan (egasi hech
    qachon hisobotsiz qolmaydi). Xabar ATAYIN parse_mode'siz (oddiy matn)
    yuboriladi - AI matnida tasodifan "<"/">" belgisi bo'lib qolsa ham,
    Telegram'ning HTML tahlili xato bermasin."""
    if get_setting("ai_ops_report_enabled", "1") != "1":
        return
    stats = collect_ops_report_stats()
    stats_text = _format_ops_stats_text(stats)

    report = None
    if ai_features_enabled():
        try:
            loop = asyncio.get_event_loop()
            report = await loop.run_in_executor(None, ai_generate_ops_report, stats_text)
        except Exception:
            logger.exception("AI kunlik hisobot generatsiyasida xatolik")

    body = report if report else stats_text
    text = f"\U0001F4C8 Kunlik hisobot\n\n{body}"
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text)
        except Exception:
            logger.exception("Kunlik hisobotni yuborib bo'lmadi: admin_id=%s", admin_id)


def _format_accuracy_text(a: dict) -> str:
    return (
        f"So'nggi hafta:\n"
        f"AI shubhali deb belgilagan e'lonlar: {a['flagged_total']}\n"
        f"Shulardan moderator baribir tasdiqlagani: {a['flagged_but_approved']}\n"
        f"AI belgilamagan-u, keyin foydalanuvchilar shikoyat qilgan e'lonlar: {a['reported_after_unflagged']}"
    )


async def job_ai_accuracy_review(context: ContextTypes.DEFAULT_TYPE):
    """Har hafta (yakshanba) AI'ning o'z ishini - REAL moderator qarorlari
    va foydalanuvchi shikoyatlari asosida - tahlil qiladi va kerak bo'lsa
    qo'shimcha ko'rsatma taklif qiladi. Bu tavsiya HECH QACHON avtomatik
    qo'llanmaydi - admin xohlasa, `ai_scam_extra_guidance` sozlamasiga
    o'zi ko'chirib qo'yadi (shundan keyin ai_screen_for_scam() uni darhol
    o'qiy boshlaydi, qayta deploy shart emas)."""
    if not ai_features_enabled():
        return
    accuracy = ai_accuracy_summary(7)
    if accuracy["flagged_total"] == 0 and accuracy["reported_after_unflagged"] == 0:
        return
    accuracy_text = _format_accuracy_text(accuracy)
    suggestion = None
    try:
        loop = asyncio.get_event_loop()
        suggestion = await loop.run_in_executor(None, ai_review_own_accuracy, accuracy_text)
    except Exception:
        logger.exception("AI aniqlik tahlilida xatolik")
    if not suggestion:
        return
    text = f"\U0001F9E0 Haftalik AI aniqlik tahlili\n\n{accuracy_text}\n\nAI tavsiyasi:\n{suggestion}"
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text)
        except Exception:
            logger.exception("Aniqlik tahlilini yuborib bo'lmadi: admin_id=%s", admin_id)


def _district_avg_price(district: str, usd_rate: int) -> tuple:
    """Bitta tuman uchun faol e'lonlar bo'yicha o'rtacha narx (so'mda) va
    e'lonlar sonini hisoblaydi - web/listings_data.py'dagi get_site_listings
    bilan BIR XIL alias-ga bog'liq qidiruv mantig'idan foydalanadi (masalan
    "Darxon" -> Sergeli), shuning uchun natija saytdagi filtr bilan mos keladi."""
    from common.districts import TASHKENT_DISTRICTS, get_aliases_for_district, parse_price_value

    keywords = get_aliases_for_district(district) if district in TASHKENT_DISTRICTS else [district]
    or_clauses, params = [], []
    for kw in keywords:
        or_clauses.append("manzil LIKE ?")
        params.append(f"%{kw}%")
        or_clauses.append("moljal LIKE ?")
        params.append(f"%{kw}%")
    conn = db()
    rows = conn.execute(
        "SELECT narx FROM listings WHERE status='approved' AND COALESCE(expired,0)=0 AND (" + " OR ".join(or_clauses) + ")",
        params,
    ).fetchall()
    conn.close()
    values = [v for v in (parse_price_value(r["narx"], usd_rate) for r in rows) if v]
    if not values:
        return 0, 0
    return sum(values) // len(values), len(values)


async def job_market_snapshot(context: ContextTypes.DEFAULT_TYPE):
    """Har kuni: joriy dollar kursi va har bir tuman uchun o'rtacha narxni
    "suratga oladi" (usd_rate_history/district_price_history) - vaqt
    o'tishi bilan bozor tendensiyasini grafik/AI tahlil qilish uchun
    ma'lumot to'planib boradi."""
    from common.districts import TASHKENT_DISTRICTS, current_usd_to_som_rate

    usd_rate = current_usd_to_som_rate()
    recorded_at = now_str()
    conn = db()
    conn.execute("INSERT INTO usd_rate_history (rate, recorded_at) VALUES (?, ?)", (usd_rate, recorded_at))
    conn.commit()
    conn.close()

    for district in TASHKENT_DISTRICTS:
        avg_price, count = _district_avg_price(district, usd_rate)
        if count == 0:
            continue
        conn = db()
        conn.execute(
            "INSERT INTO district_price_history (district, avg_price_som, listing_count, recorded_at) VALUES (?, ?, ?, ?)",
            (district, avg_price, count, recorded_at),
        )
        conn.commit()
        conn.close()


async def job_daily_backup(context: ContextTypes.DEFAULT_TYPE):
    """Har kuni bazaning zaxira nusxasini FAQAT asosiy adminlarga (moderatorlarga
    emas - bu nozik ma'lumot) fayl qilib yuboradi."""
    if not os.path.exists(DB_PATH):
        return
    today = datetime.now().strftime("%Y-%m-%d")
    for admin_id in ADMIN_IDS:
        try:
            with open(DB_PATH, "rb") as f:
                await context.bot.send_document(
                    admin_id, document=f, filename=f"zaxira_{today}.db",
                    caption=f"\U0001F4BE Kunlik avtomatik zaxira nusxa \u2014 {today}",
                )
        except Exception:
            logger.exception("Zaxira nusxani yuborib bo'lmadi: admin_id=%s", admin_id)


async def job_morning_digest(context: ContextTypes.DEFAULT_TYPE):
    """Har kuni ertalab, agar kutayotgan ish bo'lsa, xodimlarga (admin+moderator) eslatadi."""
    pending_l = count_pending_listings()
    pending_s = count_pending_subscriptions()
    if pending_l == 0 and pending_s == 0:
        return
    text = (
        f"\u2600\ufe0f <b>Xayrli tong!</b>\n\n"
        f"\U0001F553 Kutayotgan ishlar bor:\n"
        f"\u2022 {pending_l} ta e'lon\n"
        f"\u2022 {pending_s} ta obuna so'rovi\n\n"
        f"\u00abKutayotganlar\u00bb tugmasi orqali ko'rib chiqing."
    )
    for staff_id in all_staff_ids():
        try:
            await context.bot.send_message(staff_id, text, parse_mode=ParseMode.HTML)
        except Exception:
            logger.exception("Ertalabki eslatmani yuborib bo'lmadi: user_id=%s", staff_id)



