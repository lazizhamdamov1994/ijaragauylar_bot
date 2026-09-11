"""
Ijaraga Uylar Maklersiz — Telegram bot (v7)
=============================================
Sodda, chalg'ituvchi xabarlarsiz, hech qachon "qotib qolmaydigan" bot.

v7'dagi asosiy o'zgarishlar (v6'dan keyin):
  - Chek-tahlil (rasm-hash + OCR sana) tizimi OLIB TASHLANDI - amalda
    ishonchli ishlamadi (haqiqiy to'lovlarni ham shubhali ko'rsatardi)
  - "Bonus va takliflar" (referral + eski uy-so'rovi) BUTUNLAY OLIB TASHLANDI
  - "Sovg'a obuna" BUTUNLAY OLIB TASHLANDI
  - YANGI: "Hudud bo'yicha xabar" - foydalanuvchi hudud kiritadi, mos yangi
    e'lon chiqqanda avtomatik xabar oladi. Lotin/Kirill yozuvi va imlo
    farqlarini (masalan Yunusobod/Юнусобод/Юнусабад) qamrab oladigan
    aqlli moslashtirish bilan.
  - "Limit sotib olish" atamasi butun botda izchil ishlatiladi (avvalgi
    "Obuna" so'zi chalkashtirgani uchun)
  - Moderatorlar ENDI FAQAT o'zlari joylagan e'lonlar raqamini ko'ra oladi
  - Moderator "Statistika" bossa - o'zining shaxsiy natijalarini ko'radi
  - "Yordam" endi tugmali, mavzu bo'yicha interaktiv qo'llanma
  - "Bloklangan raqamlar" endi ro'yxat->karta uslubida (adashib bosish xavfisiz)
"""

import asyncio
import difflib
import html
import io
import json
import logging
import os
import re
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

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
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    PicklePersistence,
    filters,
)

# ============================= SOZLAMALAR (.env) =============================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID")
CHANNEL_ID = int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW else None
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
TASHKENT_TZ = ZoneInfo("Asia/Tashkent")  # Barcha rejalashtirilgan vazifalar shu vaqt mintaqasida ishlaydi (server UTCda bo'lsa ham)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "your_admin_username")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "").rstrip("/")  # masalan: https://5-180-183-175.nip.io

DB_PATH = os.getenv("DB_PATH", "elonlar.db")
MAX_PHOTOS = 10
MAX_DAILY_LISTINGS = int(os.getenv("MAX_DAILY_LISTINGS", "5"))
MOD_DAILY_LISTINGS = int(os.getenv("MOD_DAILY_LISTINGS", "50"))
STALE_CHECK_DAYS = int(os.getenv("STALE_CHECK_DAYS", "7"))
CARD_HOLDER = os.getenv("CARD_HOLDER", "")
PAGE_SIZE = 10

INITIAL_SETTINGS = {
    "listing_price": os.getenv("LISTING_PRICE", "20000"),
    "subscription_price": os.getenv("SUBSCRIPTION_PRICE", "20000"),
    "subscription_days": os.getenv("SUBSCRIPTION_DAYS", "30"),
    "card_number": os.getenv("CARD_NUMBER", "5614681434261669"),
    "subscriber_discount_percent": os.getenv("SUBSCRIBER_DISCOUNT_PERCENT", "25"),
    "free_views_enabled": "1",
    "free_views_count": "2",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================= HOLATLAR (STATES) =============================

(
    LISTING_TYPE_CHOICE,
    RENTAL_TYPE_CHOICE,
    QUICK_MANZIL,
    QUICK_NARX,
    MANZIL,
    MOLJAL,
    KIMLARGA,
    XONA,
    QULAYLIK,
    NARX,
    TELEFON,
    RASMLAR,
    TASDIQLASH,
    TOLOV_CHEK,
    SUB_WAIT_RECEIPT,
    ADMIN_REASON,
    ADMIN_SETTING_VALUE,
    GIFT_WAIT_USER,
    GIFT_WAIT_MONTHS,
    ADMIN_BLOCK_PHONE,
    ADMIN_BLOCK_REASON,
    CHECK_PHONE_WAIT,
    QUICK_TEXT,
    QUICK_PHONE,
    QUICK_PHOTOS,
    QUICK_CONFIRM,
    MOD_ADD_WAIT,
    CONTACT_INFO_WAIT,
    CONTACT_NOTE_WAIT,
    REQUEST_WAIT,
    USER_SEARCH_WAIT,
    LOCATION_WAIT,
    ADMIN_ADD_WAIT,
    LOCATION_OPTIONAL,
) = range(34)

BTN_ELON = "\U0001F4DD E'lon berish"
BTN_LISTINGS = "\U0001F4CB Mening e'lonlarim"
BTN_SUBSCRIPTION = "\U0001F513 Limit sotib olish"
BTN_HELP = "\u2753 Yordam"
BTN_CHECK_PHONE = "\U0001F50D Raqamni tekshirish"
BTN_LOCATION_ALERT = "\U0001F514 Hudud bo'yicha xabar"
BTN_MY_LOCATIONS = "\U0001F4CD Mening lokatsiyalarim"
BTN_LISTINGS_MAP = "\U0001F5FA E'lonlar xaritasi"
BTN_ADMIN_PANEL = "\U0001F5A5 Admin Panel"
BTN_PUBLIC_MAP = "\U0001F5FA Barcha e'lonlar xaritasi"
BTN_SUBARENDA = "\U0001F3E2 Subarenda dasturi"
BTN_CHANNEL = "\U0001F4E2 Kanalga o'tish"
BTN_STATS = "\U0001F4CA Statistika"
BTN_SUBSCRIBERS = "\U0001F465 Obunachilar"
BTN_SETTINGS = "\u2699\ufe0f Sozlamalar"
BTN_PENDING = "\U0001F553 Kutayotganlar"
BTN_BLOCKED = "\U0001F6AB Bloklangan raqamlar"
BTN_QUICK = "\u26a1 Tezkor e'lon"
BTN_MODERATORS = "\U0001F46E Moderatorlar"
BTN_FLAGGED = "\U0001F6A8 Shubhali faollik"
BTN_USER_SEARCH = "\U0001F50E Qidirish"

STEPS = [
    {"state": MANZIL, "field": "manzil", "prompt": "\U0001F4CD <b>Manzil</b> (Адрес):", "kind": "text", "maxlen": 250},
    {"state": MOLJAL, "field": "moljal", "prompt": "\U0001F3AF <b>Mo'ljal</b> (Ориентир):", "kind": "text", "maxlen": 250},
    {
        "state": KIMLARGA, "field": "kimlarga",
        "prompt": "\U0001F465 <b>Kimlarga beriladi?</b> (Кому сдаётся?)\n<i>Masalan: oilaga, talabalarga, ishlaydiganlarga</i>",
        "kind": "text", "maxlen": 150,
    },
    {
        "state": XONA, "field": "xona",
        "prompt": "\U0001F6CF <b>Nechta xonali?</b> (Сколько комнат?)\n<i>Masalan: 2 xona, studio</i>",
        "kind": "text", "maxlen": 60,
    },
    {"state": QULAYLIK, "field": "qulaylik", "prompt": "\u2705 <b>Sharoitlari</b> (Условия):", "kind": "text", "maxlen": 900},
    {
        "state": NARX, "field": "narx",
        "prompt": "\U0001F4B0 <b>Narxi</b> (Цена):\n<i>Masalan: 150$, 1.2 mln, kelishiladi</i>",
        "kind": "text", "maxlen": 200,
    },
    {"state": TELEFON, "field": "telefon", "prompt": "\U0001F4DE <b>Uy egasi raqami</b> (+998...):", "kind": "phone"},
]
TOTAL_DISPLAY_STEPS = 10

SETTINGS_FIELDS = {
    "listing_price": {"label": "\U0001F4B0 E'lon narxi", "hint": "Yangi narxni FAQAT raqamda yozing (so'mda). Masalan: 20000", "kind": "int"},
    "subscription_price": {"label": "\U0001F4B3 Obuna narxi (oylik)", "hint": "Yangi narxni FAQAT raqamda yozing (so'mda). Masalan: 20000", "kind": "int"},
    "subscription_days": {"label": "\U0001F4C5 Obuna necha kun", "hint": "Kunlar sonini yozing. Masalan: 30", "kind": "int"},
    "card_number": {"label": "\U0001F4B3 Karta raqami", "hint": "16 xonali karta raqamini yozing (bo'shliq bilan yoki bo'shliqsiz).", "kind": "card"},
    "subscriber_discount_percent": {"label": "\U0001F3AF Obunachi uchun e'lon chegirmasi (%)", "hint": "0 dan 100 gacha son yozing. Masalan: 25", "kind": "percent"},
    "free_views_enabled": {"label": "\U0001F381 Bepul ko'rish tizimi", "kind": "bool"},
    "free_views_count": {"label": "\U0001F381 Bepul ko'rish soni (yangi foydalanuvchi)", "hint": "Son yozing. Masalan: 2", "kind": "int"},
}


# ============================= MA'LUMOTLAR BAZASI =============================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_parse_dt(value):
    """Bazadagi sana-vaqt matnini xavfsiz o'qiydi. Eski/nostandart formatdagi
    yozuvlar uchun (masalan qo'lda tuzatilgan yozuvlar) None qaytaradi,
    XATOGA UCHRAMAYDI - bot hech qachon shu sabab bilan qulamasligi kerak."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


def init_db() -> None:
    conn = db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, phone TEXT, created_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT, full_name TEXT,
            sender_phone TEXT, manzil TEXT, moljal TEXT, kimlarga TEXT, xona TEXT, qulaylik TEXT, narx TEXT,
            telefon TEXT, photos TEXT, payment_receipt TEXT, price_charged INTEGER, status TEXT DEFAULT 'pending',
            reject_reason TEXT, channel_msg_id INTEGER, created_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, receipt_photo TEXT, months INTEGER DEFAULT 1,
            price_charged INTEGER, target_listing_id INTEGER, status TEXT DEFAULT 'pending', reject_reason TEXT,
            created_at TEXT, approved_at TEXT, expire_at TEXT)"""
    )
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS blocked_phones (
            phone TEXT PRIMARY KEY, reason TEXT, blocked_by INTEGER, blocked_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS moderators (
            user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS extra_admins (
            user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS channel_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL, posted_at TEXT, buttons_fixed INTEGER DEFAULT 0)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS location_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, location TEXT, created_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS listing_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            reason TEXT, created_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS phone_reveals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, listing_id INTEGER NOT NULL, revealed_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS paywall_hits (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, listing_id INTEGER, hit_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS phone_check_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, checked_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY, reason TEXT, banned_by INTEGER, banned_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS receipt_hashes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, phash TEXT, user_id INTEGER, context_label TEXT,
            ref_id INTEGER, created_at TEXT)"""
    )
    conn.commit()
    conn.close()
    migrate_db()
    seed_settings()


def migrate_db() -> None:
    conn = db()
    for table, needed in (
        ("listings", {"sender_phone": "TEXT", "payment_receipt": "TEXT", "price_charged": "INTEGER", "is_quick": "INTEGER DEFAULT 0", "raw_text": "TEXT", "last_confirmed_at": "TEXT", "expired": "INTEGER DEFAULT 0", "stale_reports": "INTEGER DEFAULT 0", "receipt_warning": "TEXT", "buttons_fixed": "INTEGER DEFAULT 0", "latitude": "REAL", "longitude": "REAL", "category": "TEXT DEFAULT 'egadan'", "rental_type": "TEXT DEFAULT 'uzoq_muddat'"}),
        ("subscriptions", {"months": "INTEGER DEFAULT 1", "price_charged": "INTEGER", "target_listing_id": "INTEGER", "receipt_warning": "TEXT"}),
        ("users", {"free_views_used": "INTEGER DEFAULT 0", "bonus_views": "INTEGER DEFAULT 0", "referred_by": "INTEGER", "referral_bonus_given": "INTEGER DEFAULT 0"}),
    ):
        existing = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        for col, coltype in needed.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
                logger.info("Migratsiya: '%s' jadvaliga '%s' ustuni qo'shildi", table, col)
    conn.commit()
    conn.close()


def seed_settings() -> None:
    conn = db()
    for key, value in INITIAL_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_setting(key: str) -> str:
    conn = db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else INITIAL_SETTINGS.get(key, "")


def set_setting(key: str, value: str) -> None:
    conn = db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def listing_price() -> int:
    return int(get_setting("listing_price"))


def subscription_price() -> int:
    return int(get_setting("subscription_price"))


def subscription_days() -> int:
    return int(get_setting("subscription_days"))


def card_number() -> str:
    return get_setting("card_number")


def subscriber_discount_percent() -> int:
    return int(get_setting("subscriber_discount_percent"))


def free_views_enabled() -> bool:
    return get_setting("free_views_enabled") == "1"


def free_views_count() -> int:
    return int(get_setting("free_views_count"))


def upsert_user(user_id: int, username, full_name, phone=None, referred_by=None) -> bool:
    """Foydalanuvchini yaratadi/yangilaydi. True qaytarsa - bu ENDI YARATILGAN
    (haqiqatan YANGI) foydalanuvchi degani."""
    conn = db()
    row = conn.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,)).fetchone()
    is_new = row is None
    if row is None:
        conn.execute(
            "INSERT INTO users (user_id, username, full_name, phone, referred_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, full_name, phone, referred_by, now_str()),
        )
    else:
        conn.execute(
            "UPDATE users SET username = ?, full_name = ?, phone = COALESCE(?, phone) WHERE user_id = ?",
            (username, full_name, phone, user_id),
        )
    conn.commit()
    conn.close()
    return is_new


def get_user(user_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def user_free_limit(user_id: int) -> int:
    return free_views_count() if free_views_enabled() else 0


def user_free_used(user_id: int) -> int:
    u = get_user(user_id) or {}
    return u.get("free_views_used") or 0


def consume_free_view(user_id: int) -> None:
    conn = db()
    conn.execute("UPDATE users SET free_views_used = COALESCE(free_views_used,0) + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def save_listing(data: dict, price_charged: int) -> int:
    conn = db()
    cur = conn.execute(
        """INSERT INTO listings
            (user_id, username, full_name, sender_phone, manzil, moljal, kimlarga, xona,
             qulaylik, narx, telefon, photos, payment_receipt, price_charged, status, created_at,
             latitude, longitude, rental_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
        (
            data["user_id"], data.get("username"), data.get("full_name"), data.get("sender_phone"),
            data["manzil"], data["moljal"], data["kimlarga"], data["xona"], data["qulaylik"], data["narx"],
            data["telefon"], json.dumps(data["rasmlar"]), data.get("payment_receipt"), price_charged, now_str(),
            data.get("latitude"), data.get("longitude"), data.get("rental_type") or "uzoq_muddat",
        ),
    )
    conn.commit()
    listing_id = cur.lastrowid
    conn.close()
    return listing_id


def save_quick_listing(user_id: int, username, full_name, telefon: str, manzil: str, narx: str, raw_text: str, rasmlar: list) -> int:
    """Admin uchun tezkor rejim: OLX'dan ko'chirilgan matn HECH QANDAY o'zgartirishsiz,
    aynan o'zi saqlanadi va kanalga shu holicha (branding qo'shilmasdan) chiqadi.
    Manzil va narx endi MAJBURIY - shu ikkisi tufayli tezkor e'lonlar ham saytda
    aniq manzili va narxi bilan (lite shablonda) to'g'ri ko'rinadi."""
    conn = db()
    cur = conn.execute(
        """INSERT INTO listings
            (user_id, username, full_name, manzil, moljal, kimlarga, xona, qulaylik, narx,
             telefon, photos, price_charged, status, is_quick, raw_text, created_at)
           VALUES (?, ?, ?, ?, '', '', '', '', ?, ?, ?, 0, 'pending', 1, ?, ?)""",
        (user_id, username, full_name, manzil, narx, telefon, json.dumps(rasmlar), raw_text, now_str()),
    )
    conn.commit()
    listing_id = cur.lastrowid
    conn.close()
    return listing_id


def get_listing(listing_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["photos"] = json.loads(d["photos"] or "[]")
    return d


def update_listing_status(listing_id: int, status: str, reason=None, channel_msg_id=None) -> None:
    conn = db()
    conn.execute(
        "UPDATE listings SET status = ?, reject_reason = ?, channel_msg_id = COALESCE(?, channel_msg_id) WHERE id = ?",
        (status, reason, channel_msg_id, listing_id),
    )
    if status == "approved":
        conn.execute("UPDATE listings SET last_confirmed_at = ? WHERE id = ?", (now_str(), listing_id))
    conn.commit()
    conn.close()


def set_listing_receipt_warning(listing_id: int, warning: str) -> None:
    conn = db()
    conn.execute("UPDATE listings SET receipt_warning = ? WHERE id = ?", (warning, listing_id))
    conn.commit()
    conn.close()



def confirm_listing_still_available(listing_id: int) -> None:
    conn = db()
    conn.execute("UPDATE listings SET last_confirmed_at = ? WHERE id = ?", (now_str(), listing_id))
    conn.commit()
    conn.close()


def mark_listing_expired(listing_id: int) -> None:
    conn = db()
    conn.execute("UPDATE listings SET expired = 1 WHERE id = ?", (listing_id,))
    conn.commit()
    conn.close()


def get_stale_listings(days: int) -> list:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    rows = conn.execute(
        "SELECT * FROM listings WHERE status = 'approved' AND expired = 0 AND last_confirmed_at <= ?",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def increment_stale_report(listing_id: int) -> int:
    conn = db()
    conn.execute("UPDATE listings SET stale_reports = COALESCE(stale_reports,0) + 1 WHERE id = ?", (listing_id,))
    conn.commit()
    row = conn.execute("SELECT stale_reports FROM listings WHERE id = ?", (listing_id,)).fetchone()
    conn.close()
    return row["stale_reports"] if row else 0


def has_user_reported(listing_id: int, user_id: int) -> bool:
    conn = db()
    row = conn.execute("SELECT 1 FROM listing_reports WHERE listing_id = ? AND user_id = ?", (listing_id, user_id)).fetchone()
    conn.close()
    return row is not None


def count_user_reports_today(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM listing_reports WHERE user_id = ? AND substr(created_at,1,10) = ?", (user_id, today)
    ).fetchone()["c"]
    conn.close()
    return n


def save_report(listing_id: int, user_id: int, reason: str) -> None:
    conn = db()
    conn.execute(
        "INSERT INTO listing_reports (listing_id, user_id, reason, created_at) VALUES (?, ?, ?, ?)",
        (listing_id, user_id, reason, now_str()),
    )
    conn.commit()
    conn.close()


def get_user_listings(user_id: int, limit: int = 10):
    conn = db()
    rows = conn.execute("SELECT * FROM listings WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_listings(limit: int = 10):
    conn = db()
    rows = conn.execute("SELECT * FROM listings WHERE status = 'pending' ORDER BY id ASC LIMIT ?", (limit,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["photos"] = json.loads(d["photos"] or "[]")
        result.append(d)
    return result


def count_pending_listings() -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM listings WHERE status='pending'").fetchone()["c"]
    conn.close()
    return n


def get_pending_subscriptions(limit: int = 10):
    conn = db()
    rows = conn.execute("SELECT * FROM subscriptions WHERE status = 'pending' ORDER BY id ASC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_pending_subscriptions() -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM subscriptions WHERE status='pending'").fetchone()["c"]
    conn.close()
    return n


def count_today_listings(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM listings WHERE user_id = ? AND substr(created_at, 1, 10) = ?", (user_id, today)
    ).fetchone()["c"]
    conn.close()
    return n


def save_subscription_request(user_id: int, receipt_photo: str, price_charged: int, target_listing_id) -> int:
    conn = db()
    cur = conn.execute(
        "INSERT INTO subscriptions (user_id, receipt_photo, months, price_charged, target_listing_id, status, created_at) "
        "VALUES (?, ?, 1, ?, ?, 'pending', ?)",
        (user_id, receipt_photo, price_charged, target_listing_id, now_str()),
    )
    conn.commit()
    sub_id = cur.lastrowid
    conn.close()
    return sub_id


def get_subscription(sub_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def approve_subscription(sub_id: int):
    sub = get_subscription(sub_id)
    months = sub["months"] or 1
    expire_at = (datetime.now() + timedelta(days=subscription_days() * months)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    conn.execute(
        "UPDATE subscriptions SET status = 'approved', approved_at = ?, expire_at = ? WHERE id = ?",
        (now_str(), expire_at, sub_id),
    )
    conn.execute(
        "UPDATE subscriptions SET status='rejected', reject_reason='Avtomatik: boshqa so''rovingiz allaqachon tasdiqlandi' "
        "WHERE user_id = ? AND status = 'pending' AND id != ?",
        (sub["user_id"], sub_id),
    )
    conn.commit()
    conn.close()
    return sub["user_id"], expire_at


def reject_subscription(sub_id: int, reason: str) -> None:
    conn = db()
    conn.execute("UPDATE subscriptions SET status = 'rejected', reject_reason = ? WHERE id = ?", (reason, sub_id))
    conn.commit()
    conn.close()


def cancel_subscription(sub_id: int):
    sub = get_subscription(sub_id)
    if not sub:
        return None
    conn = db()
    conn.execute("UPDATE subscriptions SET status = 'cancelled' WHERE id = ?", (sub_id,))
    conn.commit()
    conn.close()
    return sub["user_id"]


def is_subscribed(user_id: int):
    conn = db()
    row = conn.execute(
        "SELECT expire_at FROM subscriptions WHERE user_id = ? AND status = 'approved' ORDER BY expire_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row or not row["expire_at"]:
        return False, None
    expire = safe_parse_dt(row["expire_at"])
    if expire is None:
        return False, None
    return expire > datetime.now(), row["expire_at"]


def get_active_subscription_id(user_id: int):
    conn = db()
    row = conn.execute(
        "SELECT id, expire_at FROM subscriptions WHERE user_id = ? AND status = 'approved' ORDER BY expire_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row or not row["expire_at"]:
        return None
    parsed = safe_parse_dt(row["expire_at"])
    if parsed is None or parsed <= datetime.now():
        return None
    return row["id"]


def count_active_subscribers() -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM subscriptions WHERE status='approved' AND expire_at > ?", (now_str(),)).fetchone()["c"]
    conn.close()
    return n


def active_subscribers_page(offset: int, limit: int = PAGE_SIZE):
    conn = db()
    rows = conn.execute(
        """SELECT s.id AS sub_id, s.user_id, s.expire_at, s.months, u.username, u.full_name, u.phone
           FROM subscriptions s LEFT JOIN users u ON u.user_id = s.user_id
           WHERE s.status = 'approved' AND s.expire_at > ?
           ORDER BY s.expire_at ASC LIMIT ? OFFSET ?""",
        (now_str(), limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stats_for_period(date_from: str, date_to_exclusive: str) -> dict:
    conn = db()

    def count(query, *params):
        return conn.execute(query, params).fetchone()["c"]

    listings_total = count("SELECT COUNT(*) c FROM listings WHERE created_at >= ? AND created_at < ?", date_from, date_to_exclusive)
    listings_approved = count("SELECT COUNT(*) c FROM listings WHERE created_at >= ? AND created_at < ? AND status='approved'", date_from, date_to_exclusive)
    listings_rejected = count("SELECT COUNT(*) c FROM listings WHERE created_at >= ? AND created_at < ? AND status='rejected'", date_from, date_to_exclusive)
    listings_pending = count("SELECT COUNT(*) c FROM listings WHERE created_at >= ? AND created_at < ? AND status='pending'", date_from, date_to_exclusive)
    listings_income = conn.execute(
        "SELECT COALESCE(SUM(price_charged),0) s FROM listings WHERE created_at >= ? AND created_at < ? AND status='approved'",
        (date_from, date_to_exclusive),
    ).fetchone()["s"]
    subs_total = count("SELECT COUNT(*) c FROM subscriptions WHERE created_at >= ? AND created_at < ?", date_from, date_to_exclusive)
    subs_approved = count("SELECT COUNT(*) c FROM subscriptions WHERE created_at >= ? AND created_at < ? AND status='approved'", date_from, date_to_exclusive)
    subs_income = conn.execute(
        "SELECT COALESCE(SUM(price_charged),0) s FROM subscriptions WHERE created_at >= ? AND created_at < ? AND status='approved'",
        (date_from, date_to_exclusive),
    ).fetchone()["s"]
    users_total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    conn.close()
    return {
        "listings_total": listings_total, "listings_approved": listings_approved, "listings_rejected": listings_rejected,
        "listings_pending": listings_pending, "listings_income": listings_income, "subs_total": subs_total,
        "subs_approved": subs_approved, "subs_income": subs_income, "users_total": users_total,
    }


def stats_today() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return stats_for_period(today, tomorrow)


def count_new_users_in_period(date_from: str, date_to_exclusive: str) -> int:
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM users WHERE created_at >= ? AND created_at < ?", (date_from, date_to_exclusive)
    ).fetchone()["c"]
    conn.close()
    return n


def get_period_bounds(period: str):
    """Berilgan davr uchun (boshlanish, tugash, oldingi davr boshlanishi,
    oldingi davr tugashi, ko'rinadigan nom) qaytaradi - taqqoslash uchun."""
    now = datetime.now()
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        prev_start, prev_end = start - timedelta(days=1), start
        label = f"\U0001F4C5 Bugun ({start.strftime('%d.%m.%Y')})"
        prev_label = "kechagi kunga nisbatan"
    elif period == "weekly":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        prev_start, prev_end = start - timedelta(days=7), start
        label = f"\U0001F4C6 Bu hafta ({start.strftime('%d.%m')} \u2014 {(end - timedelta(days=1)).strftime('%d.%m.%Y')})"
        prev_label = "o'tgan haftaga nisbatan"
    elif period == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1))
        prev_start = (start.replace(year=start.year - 1, month=12) if start.month == 1 else start.replace(month=start.month - 1))
        prev_end = start
        label = f"\U0001F5D3 Bu oy ({start.strftime('%m.%Y')})"
        prev_label = "o'tgan oyga nisbatan"
    else:  # yearly
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
        prev_start, prev_end = start.replace(year=start.year - 1), start
        label = f"\U0001F4C8 Bu yil ({start.year})"
        prev_label = "o'tgan yilga nisbatan"
    fmt = "%Y-%m-%d %H:%M:%S"
    return start.strftime(fmt), end.strftime(fmt), prev_start.strftime(fmt), prev_end.strftime(fmt), label, prev_label


def percent_change(old: float, new: float) -> str:
    if old == 0 and new == 0:
        return "o'zgarishsiz"
    if old == 0:
        return "\U0001F195 yangi"
    change = (new - old) / old * 100
    arrow = "\U0001F53A" if change > 0 else ("\U0001F53B" if change < 0 else "\u27a1\ufe0f")
    return f"{arrow} {change:+.0f}%"


def render_period_stats(period: str) -> str:
    start, end, prev_start, prev_end, label, prev_label = get_period_bounds(period)
    cur = stats_for_period(start, end)
    prev = stats_for_period(prev_start, prev_end)
    new_users = count_new_users_in_period(start, end)
    new_users_prev = count_new_users_in_period(prev_start, prev_end)

    total_users_ever = cur["users_total"]  # stats_for_period bu yerda umriy jamini beradi
    total_active_subs = count_active_subscribers()
    total_revenue = cur["listings_income"] + cur["subs_income"]
    prev_revenue = prev["listings_income"] + prev["subs_income"]

    successful_reveals = count_reveals_in_period(start, end)
    failed_attempts = count_paywall_hits_in_period(start, end)
    total_attempts = successful_reveals + failed_attempts
    conversion = f"{(successful_reveals / total_attempts * 100):.0f}%" if total_attempts else "\u2014"
    phone_checks = count_phone_checks_in_period(start, end)
    new_location_alerts = count_location_alerts_in_period(start, end)
    source = count_listings_by_source_in_period(start, end)
    listing_type = count_listings_by_type_in_period(start, end)
    multi_location = get_multi_location_posters(2)

    location_lines = [f"\U0001F4CD <b>JOYLASHUV BO'YICHA E'LON BERUVCHILAR</b> <i>(umumiy, davrga bog'liq emas)</i>\n"]
    location_lines.append(f"2+ hududda e'lon bergan: {len(multi_location)} ta foydalanuvchi\n")
    if multi_location:
        for uid, cnt in multi_location[:5]:
            u = get_user(uid) or {}
            name = u.get("full_name") or f"ID:{uid}"
            location_lines.append(f"\u2022 {esc(name)} \u2014 {cnt} ta hududda")
    location_section = "\n".join(location_lines) + "\n\n"

    text = (
        f"\U0001F4CA <b>Statistika</b> \u2014 {label}\n"
        f"<i>({prev_label} solishtirilgan)</i>\n\n"

        f"\U0001F465 <b>FOYDALANUVCHILAR</b>\n"
        f"Yangi qo'shilgan: {new_users} ta ({percent_change(new_users_prev, new_users)})\n"
        f"Jami (botni ishlatgan): {total_users_ever} ta\n\n"

        f"\U0001F4DD <b>E'LONLAR</b>\n"
        f"Yangi: {cur['listings_total']} ta ({percent_change(prev['listings_total'], cur['listings_total'])})\n"
        f"\u2705 Tasdiqlangan: {cur['listings_approved']} ta\n"
        f"\u274c Rad etilgan: {cur['listings_rejected']} ta\n"
        f"\U0001F553 Kutilmoqda: {cur['listings_pending']} ta\n"
        f"\U0001F464 Foydalanuvchilar o'zi joyladi: {source['user']} ta\n"
        f"\U0001F6E0 Admin/moderator joyladi: {source['staff']} ta\n"
        f"\U0001F4B0 Pullik e'lon: {listing_type['paid']} ta\n"
        f"\U0001F193 Bepul e'lon: {listing_type['free']} ta\n"
        f"\U0001F4B0 Tushum: {cur['listings_income']:,} so'm ({percent_change(prev['listings_income'], cur['listings_income'])})\n\n"

        f"\U0001F4B3 <b>LIMIT (OBUNA)</b>\n"
        f"Yangi so'rov: {cur['subs_total']} ta ({percent_change(prev['subs_total'], cur['subs_total'])})\n"
        f"\u2705 Tasdiqlangan: {cur['subs_approved']} ta\n"
        f"\U0001F513 Hozir FAOL: {total_active_subs} ta\n"
        f"\U0001F4B0 Tushum: {cur['subs_income']:,} so'm ({percent_change(prev['subs_income'], cur['subs_income'])})\n\n"

        f"\U0001F3AF <b>RAQAM KO'RISH URINISHLARI</b>\n"
        f"\u2705 Muvaffaqiyatli (raqam olishgan): {successful_reveals} ta\n"
        f"\u274c Muvaffaqiyatsiz (limit/obunasiz): {failed_attempts} ta\n"
        f"\U0001F4C8 Konversiya: {conversion}\n\n"

        f"\U0001F527 <b>BOSHQA FUNKSIYALAR</b>\n"
        f"\U0001F50D Raqam tekshirish: {phone_checks} marta\n"
        f"\U0001F514 Yangi hudud-xabar: {new_location_alerts} ta\n\n"

        f"{location_section}"

        f"\U0001F4B5 <b>JAMI TUSHUM: {total_revenue:,} so'm</b> ({percent_change(prev_revenue, total_revenue)})"
    )
    return text


def normalize_phone(raw: str):
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("998") and len(digits) == 12:
        pass
    elif len(digits) == 9:
        digits = "998" + digits
    else:
        return None
    if not re.fullmatch(r"998\d{9}", digits):
        return None
    return "+" + digits


def block_phone(phone: str, reason: str, admin_id: int) -> None:
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO blocked_phones (phone, reason, blocked_by, blocked_at) VALUES (?, ?, ?, ?)",
        (phone, reason, admin_id, now_str()),
    )
    conn.commit()
    conn.close()


def unblock_phone(phone: str) -> None:
    conn = db()
    conn.execute("DELETE FROM blocked_phones WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()


def get_blocked_phone(phone: str):
    conn = db()
    row = conn.execute("SELECT * FROM blocked_phones WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    return dict(row) if row else None


def count_blocked_phones() -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM blocked_phones").fetchone()["c"]
    conn.close()
    return n


def has_recent_subscription_request(user_id: int, since: str) -> bool:
    conn = db()
    row = conn.execute("SELECT 1 FROM subscriptions WHERE user_id = ? AND created_at >= ? LIMIT 1", (user_id, since)).fetchone()
    conn.close()
    return row is not None


def list_blocked_phones_page(offset: int, limit: int = PAGE_SIZE):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM blocked_phones ORDER BY blocked_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================= YORDAMCHI FUNKSIYALAR =============================

def esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def card_html(price: int, purpose: str = "To'lov") -> str:
    raw = re.sub(r"\D", "", card_number())
    grouped = " ".join(raw[i:i + 4] for i in range(0, len(raw), 4))
    holder = f"\n\U0001F464 {esc(CARD_HOLDER)}" if CARD_HOLDER else ""
    return (
        f"\U0001F4B3 <b>To'lov</b>\n\n"
        f"{esc(purpose)} \u2014 <b>{price:,} so'm</b>\n\n"
        f"Karta raqami:\n<b>{grouped}</b>{holder}\n\n"
        f"To'lovni amalga oshirgach, chek skrinshotini shu yerga rasm qilib yuboring."
    )


def card_payment_keyboard(cancel_callback: str = "nav_cancel") -> InlineKeyboardMarkup:
    """To'lov ekrani uchun tugmalar: karta raqamini (bo'shliqsiz, toza holda)
    bosib nusxalash tugmasi + bekor qilish."""
    raw = re.sub(r"\D", "", card_number())
    copy_btn = InlineKeyboardButton("\U0001F4CB Karta raqamini nusxalash", api_kwargs={"copy_text": {"text": raw}})
    cancel_btn = InlineKeyboardButton("\u274c Bekor qilish", callback_data=cancel_callback)
    return InlineKeyboardMarkup([[copy_btn], [cancel_btn]])


def build_caption(data: dict, bot_username: str = None) -> str:
    bugun = datetime.now().strftime("%d.%m.%Y")
    trust_badge = "\n\u2705 <b>Ishonchli e'lon beruvchi</b>" if is_trusted_poster(data.get("user_id")) else ""
    location_badge = "\n\n\U0001F4CD <b>Aniq manzil mavjud</b> \u2014 pastdagi \u00abLokatsiya\u00bb tugmasini bosing" if data.get("latitude") and data.get("longitude") else ""
    category_labels = {
        "tasdiqlangan": "\u2705 <b>Tasdiqlangan e'lon</b>",
        "subarenda": "\U0001F3E2 <b>Ijaraga Uylar tomonidan boshqariladi (Subarenda)</b>",
        "premium": "\U0001F48E <b>Premium e'lon</b>",
    }
    category_badge = f"\n{category_labels[data['category']]}" if data.get("category") in category_labels else ""
    rental_type_labels = {
        "kunlik": "\U0001F4C5 <b>Kunlik ijara</b>",
        "uzoq_muddat": "\U0001F3E0 <b>Uzoq muddatli ijara</b>",
        "dacha": "\U0001F333 <b>Dacha</b>",
        "mehmonxona": "\U0001F6CF <b>Mehmonxona</b>",
    }
    rental_type_badge = f"\n{rental_type_labels[data['rental_type']]}" if data.get("rental_type") in rental_type_labels else ""
    if data.get("is_quick"):
        # Tezkor rejim: matnning o'zi o'zgartirilmaydi, lekin brend
        # sarlavha + sana + footer HAR DOIM qo'shiladi (izchillik uchun).
        return (
            f"\U0001F3E0 <b>Ijaraga Uylar Maklersiz</b>{trust_badge}{category_badge}{location_badge}\n\n"
            f"{esc(data.get('raw_text') or '')}\n\n"
            f"\U0001F4C5 {bugun}\n\n"
            f"@{CHANNEL_USERNAME} \u2014 uyingizni maklersiz bering va oling!"
        )
    return (
        f"\U0001F3E0 <b>Ijaraga Uylar Maklersiz</b>{trust_badge}{category_badge}{rental_type_badge}{location_badge}\n\n"
        f"\U0001F4CD <b>Manzil:</b> {esc(data['manzil'])}\n"
        f"\U0001F3AF <b>Mo'ljal:</b> {esc(data['moljal'])}\n"
        f"\U0001F465 <b>Kimlarga:</b> {esc(data['kimlarga'])}\n"
        f"\U0001F6CF <b>Xonalar soni:</b> {esc(data['xona'])}\n\n"
        f"\u2705 <b>Qulayliklar:</b>\n{esc(data['qulaylik'])}\n\n"
        f"\U0001F4B0 <b>Narxi:</b> {esc(data['narx'])}\n\n"
        f"\U0001F4C5 {bugun}\n\n"
        f"@{CHANNEL_USERNAME} \u2014 uyingizni maklersiz bering va oling!"
    )


def phone_reveal_text(listing: dict, expire=None) -> str:
    phone = listing["telefon"]
    text = f'\U0001F4DE Telefon raqami: <a href="tel:{phone}">{esc(phone)}</a>'
    if listing.get("username") and not is_admin(listing["user_id"]):
        text += f'\n\U0001F464 Egasi: <a href="https://t.me/{listing["username"]}">@{esc(listing["username"])}</a>'
    if expire:
        text += f"\n\n<i>Obunangiz {expire[:10]} gacha faol.</i>"
    return text


def channel_keyboard(listing_id: int, bot_username: str, latitude: float = None, longitude: float = None) -> InlineKeyboardMarkup:
    call_link = f"https://t.me/{bot_username}?start=phone_{listing_id}"
    post_link = f"https://t.me/{bot_username}?start=elon"
    complain_link = f"https://t.me/{bot_username}?start=complain_{listing_id}"
    rows = [
        [InlineKeyboardButton("\U0001F4DE Uy egasi raqami", url=call_link)],
    ]
    if DASHBOARD_URL and DASHBOARD_URL.startswith("https://"):
        rows.append([InlineKeyboardButton("\U0001F310 Saytda batafsil ko'rish", url=f"{DASHBOARD_URL}/uy/{listing_id}")])
    if latitude and longitude:
        map_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
        rows.append([InlineKeyboardButton("\U0001F5FA Lokatsiya", url=map_link),
                     InlineKeyboardButton("\U0001F4DD E'lon berish", url=post_link)])
    else:
        rows.append([InlineKeyboardButton("\U0001F4DD E'lon berish", url=post_link)])
    rows.append([InlineKeyboardButton("\U0001F4AC Adminga", url=f"https://t.me/{ADMIN_USERNAME}"),
                 InlineKeyboardButton("\u26A0\uFE0F Etiroz", url=complain_link)])
    return InlineKeyboardMarkup(rows)


def channel_link_button():
    if not CHANNEL_USERNAME:
        return None
    return InlineKeyboardButton("\U0001F4E2 Kanaldagi e'lonlarni ko'rish", url=f"https://t.me/{CHANNEL_USERNAME}")


def main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    rows = [[BTN_ELON], [BTN_LISTINGS, BTN_SUBSCRIPTION], [BTN_CHECK_PHONE, BTN_HELP], [BTN_LOCATION_ALERT, BTN_MY_LOCATIONS], [BTN_CHANNEL]]
    if DASHBOARD_URL:
        rows.append([BTN_SUBARENDA])
    # MUHIM: Telegram WebApp tugmalari FAQAT https:// havolalarni qabul qiladi -
    # http:// bo'lsa, butun klaviaturani yuborishda XATOLIK chiqadi va bot
    # ISHLAMAY QOLADI. Shuning uchun bu yerda ALBATTA tekshiramiz.
    dashboard_https_ready = DASHBOARD_URL.startswith("https://")
    if dashboard_https_ready:
        rows.append([KeyboardButton(BTN_PUBLIC_MAP, web_app=WebAppInfo(url=f"{DASHBOARD_URL}/xarita"))])
    if is_admin(user_id):
        rows.append([BTN_STATS, BTN_SUBSCRIBERS])
        rows.append([BTN_SETTINGS, BTN_MODERATORS])
        rows.append([BTN_PENDING, BTN_BLOCKED])
        rows.append([BTN_FLAGGED, BTN_USER_SEARCH])
        rows.append([BTN_LISTINGS_MAP])
        if DASHBOARD_URL:  # Admin Panel - oddiy URL tugma, http:// bilan ham ishlaydi
            rows.append([BTN_ADMIN_PANEL])
        rows.append([BTN_QUICK])
    elif is_moderator(user_id):
        rows.append([BTN_STATS, BTN_PENDING])
        rows.append([BTN_QUICK])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def nav_keyboard(idx: int) -> InlineKeyboardMarkup:
    nav = []
    if idx > 0:
        nav.append(InlineKeyboardButton("\u25c0\ufe0f Orqaga", callback_data="nav_back"))
    nav.append(InlineKeyboardButton("\u274c Bekor qilish", callback_data="nav_cancel"))
    return InlineKeyboardMarkup([nav])


async def render_step(update: Update, context: ContextTypes.DEFAULT_TYPE, idx: int) -> int:
    context.user_data["step_idx"] = idx
    step = STEPS[idx]
    current = context.user_data.get(step["field"])
    if current:
        text = f"{step['prompt']}\n\n<i>Joriy qiymat: {esc(current)}</i>\n\n<i>Bosqich {idx + 1}/{TOTAL_DISPLAY_STEPS}</i>"
    else:
        text = f"{step['prompt']}\n\n<i>Bosqich {idx + 1}/{TOTAL_DISPLAY_STEPS}</i>"
    markup = nav_keyboard(idx)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return step["state"]


async def update_photo_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    photos = context.user_data.setdefault("rasmlar", [])
    n = len(photos)
    lines = ["\U0001F4F8 Uyning rasmlarini yuboring (1\u201310 ta)."]
    lines.append(f"\n{n}/{MAX_PHOTOS} rasm qabul qilindi." if n > 0 else "\nKamida 1 ta rasm yuboring.")
    text = f"{''.join(lines)}\n\n<i>Bosqich 9/{TOTAL_DISPLAY_STEPS}</i>"
    rows = []
    if n > 0:
        rows.append([InlineKeyboardButton(f"\u2705 Tayyor ({n} ta) \u2014 Davom etish", callback_data="rasm_tayyor")])
    nav = [InlineKeyboardButton("\u25c0\ufe0f Orqaga", callback_data="nav_back_to_location"), InlineKeyboardButton("\u274c Bekor qilish", callback_data="nav_cancel")]
    rows.append(nav)
    markup = InlineKeyboardMarkup(rows)

    msg_id = context.user_data.get("photo_status_msg_id")
    if msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
    sent = await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=markup)
    context.user_data["photo_status_msg_id"] = sent.message_id


def is_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    conn = db()
    row = conn.execute("SELECT 1 FROM extra_admins WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row is not None


def add_extra_admin(user_id: int, added_by: int) -> None:
    conn = db()
    conn.execute("INSERT OR IGNORE INTO extra_admins (user_id, added_by, added_at) VALUES (?, ?, ?)", (user_id, added_by, now_str()))
    conn.commit()
    conn.close()


def remove_extra_admin(user_id: int) -> None:
    conn = db()
    conn.execute("DELETE FROM extra_admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def list_extra_admins() -> list:
    conn = db()
    rows = conn.execute("SELECT * FROM extra_admins ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_moderator(user_id: int) -> bool:
    conn = db()
    row = conn.execute("SELECT 1 FROM moderators WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row is not None


def is_staff(user_id: int) -> bool:
    """Admin YOKI moderator - kunlik moderatsiya ishlarini bajara oladiganlar."""
    return is_admin(user_id) or is_moderator(user_id)


def add_moderator(user_id: int, added_by: int) -> None:
    conn = db()
    conn.execute("INSERT OR IGNORE INTO moderators (user_id, added_by, added_at) VALUES (?, ?, ?)", (user_id, added_by, now_str()))
    conn.commit()
    conn.close()


def remove_moderator(user_id: int) -> None:
    conn = db()
    conn.execute("DELETE FROM moderators WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def list_moderators() -> list:
    conn = db()
    rows = conn.execute("SELECT * FROM moderators ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def all_staff_ids() -> list:
    return list(ADMIN_IDS) + [a["user_id"] for a in list_extra_admins()] + [m["user_id"] for m in list_moderators()]


# ============================= HUDUD BO'YICHA XABAR (Lotin/Kirill moslashtirish) =============================

MAX_LOCATION_ALERTS = 3
FUZZY_MATCH_THRESHOLD = 0.75

# Kirill -> Lotin harf almashtirish (o'zbekcha imloga moslangan)
CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "s",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "қ": "q", "ғ": "g'", "ў": "o'", "ҳ": "h",
}

# Toshkentning eng ko'p qidiriladigan tumanlari - turli yozilish variantlari bilan.
# Bu ro'yxat orqali eng keng tarqalgan holatlar 100% aniqlikda mos keladi.
DISTRICT_ALIASES = {
    "yunusobod": {"yunusobod", "yunusabad", "yunisabad", "юнусобод", "юнусабад", "юнисабад"},
    "chilonzor": {"chilonzor", "chilanzar", "чилонзор", "чиланзар"},
    "sergeli": {"sergeli", "sergели", "сергели"},
    "mirzo ulugbek": {"mirzo ulugbek", "mirzo ulug'bek", "mirzo-ulugbek", "мирзо улугбек", "мирзо-улугбек"},
    "shayxontohur": {"shayxontohur", "shaykhontohur", "шайхонтохур", "шайхантахур"},
    "olmazor": {"olmazor", "olmazar", "олмазор", "олмазар"},
    "bektemir": {"bektemir", "бектемир"},
    "uchtepa": {"uchtepa", "uchtepa", "учтепа"},
    "yashnobod": {"yashnobod", "yashnabad", "яшнобод", "яшнабад"},
    "yakkasaroy": {"yakkasaroy", "yakkasaray", "яккасарой", "яккасарай"},
    "mirobod": {"mirobod", "mirabad", "миробод", "мирабад"},
    "chorsu": {"chorsu", "чорсу"},
}


def translit_cyrillic_to_latin(text: str) -> str:
    result = []
    for ch in text.lower():
        result.append(CYRILLIC_TO_LATIN.get(ch, ch))
    return "".join(result)


def normalize_location_text(text: str) -> str:
    t = (text or "").lower().strip()
    t = translit_cyrillic_to_latin(t)
    t = re.sub(r"[^a-z0-9' ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def location_matches(saved_location: str, listing_text: str) -> bool:
    """Foydalanuvchi saqlagan hudud, yangi e'lon matnida bormi - tekshiradi.
    Lotin/Kirill yozuvi, imlo xatolari va mashhur tuman nomlarini hisobga oladi."""
    saved_norm = normalize_location_text(saved_location)
    listing_norm = normalize_location_text(listing_text)
    if not saved_norm or not listing_norm:
        return False

    # 1) To'g'ridan-to'g'ri (normallashtirilgandan keyin) mos kelishi
    if saved_norm in listing_norm:
        return True

    # 2) Mashhur tuman nomlari ro'yxati orqali (100% aniq holatlar)
    for canonical, aliases in DISTRICT_ALIASES.items():
        norm_aliases = {normalize_location_text(a) for a in aliases}
        if saved_norm in norm_aliases:
            if any(alias in listing_norm for alias in norm_aliases):
                return True

    # 3) Taxminiy moslik (imlo xatolari, kichik farqlar uchun)
    listing_words = listing_norm.split()
    for word in listing_words:
        if len(word) < 3:
            continue
        ratio = difflib.SequenceMatcher(None, saved_norm, word).ratio()
        if ratio >= FUZZY_MATCH_THRESHOLD:
            return True
    return False


def add_location_alert(user_id: int, location: str) -> int:
    conn = db()
    cur = conn.execute("INSERT INTO location_alerts (user_id, location, created_at) VALUES (?, ?, ?)", (user_id, location, now_str()))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def get_user_location_alerts(user_id: int) -> list:
    conn = db()
    rows = conn.execute("SELECT * FROM location_alerts WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_location_alert(alert_id: int, user_id: int) -> None:
    conn = db()
    conn.execute("DELETE FROM location_alerts WHERE id = ? AND user_id = ?", (alert_id, user_id))
    conn.commit()
    conn.close()


def all_location_alerts() -> list:
    conn = db()
    rows = conn.execute("SELECT * FROM location_alerts").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_matching_location_alerts(listing: dict) -> list:
    haystack = " ".join([
        listing.get("manzil") or "", listing.get("moljal") or "", listing.get("raw_text") or "",
    ])
    matches = []
    for alert in all_location_alerts():
        if location_matches(alert["location"], haystack):
            matches.append(alert)
    return matches


def group_location_alerts() -> list:
    """Barcha saqlangan hududlarni (Lotin/Kirill/imlo farqlarini hisobga olib)
    guruhlaydi va har bir guruh uchun (ko'rinadigan nom, kutayotganlar soni)
    qaytaradi, ko'p kutilgandan kamiga qarab tartiblangan."""
    groups: dict = {}
    for a in all_location_alerts():
        norm = normalize_location_text(a["location"])
        canonical = None
        for c, aliases in DISTRICT_ALIASES.items():
            norm_aliases = {normalize_location_text(al) for al in aliases}
            if norm in norm_aliases:
                canonical = c
                break
        key = canonical or norm
        if key not in groups:
            groups[key] = {"display": a["location"], "count": 0}
        groups[key]["count"] += 1
    result = [(v["display"], v["count"]) for v in groups.values()]
    result.sort(key=lambda x: x[1], reverse=True)
    return result


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


# ============================= ASOSIY MENYU / START =============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payload = context.args[0] if context.args else None

    upsert_user(user.id, user.username, user.full_name)

    if payload and payload.startswith("phone_"):
        await reveal_phone(update, context, payload)
        return

    if payload and payload.startswith("complain_"):
        try:
            listing_id = int(payload.split("_", 1)[1])
            await show_complain_menu(update, context, listing_id)
        except (IndexError, ValueError):
            pass
        return

    # QUYIDAGI 3 TA HOLAT: agar tegishli suhbat (elon_conv/sub_conv/check_phone_conv)
    # o'z ichki CommandHandler kirish nuqtasi orqali TO'G'RIDAN-TO'G'RI ishlagan
    # bo'lsa (eng ko'p uchraydigan holat), bu yerga umuman yetib kelmaydi. Bu yerga
    # faqat ikki noyob holatda tushadi: (1) foydalanuvchi biror jarayonda "qolib
    # ketgan" bo'lsa, yoki (2) Telegram "qaytgan foydalanuvchida" havola
    # parametrini yo'qotib qo'ygan bo'lsa. Ikkala holatda ham force_reset orqali
    # eski holatni tozalab, ISHONCHLI (bir marta bosish bilan) davom ettiramiz.
    if payload == "elon":
        force_reset_conversation(context, "elon_conv", user.id)
        keyboard = ReplyKeyboardMarkup([[BTN_ELON]], resize_keyboard=True)
        await update.message.reply_text(
            "\U0001F3E0 Uyingizni ijaraga bermoqchimisiz?\n\nPastdagi tugmani bosing \U0001F447",
            reply_markup=keyboard,
        )
        return

    if payload == "buysub":
        force_reset_conversation(context, "sub_conv", user.id)
        keyboard = ReplyKeyboardMarkup([[BTN_SUBSCRIPTION]], resize_keyboard=True)
        await update.message.reply_text(
            "\U0001F513 Limit sotib olmoqchimisiz?\n\nPastdagi tugmani bosing \U0001F447",
            reply_markup=keyboard,
        )
        return

    if payload == "checkphone":
        force_reset_conversation(context, "check_phone_conv", user.id)
        keyboard = ReplyKeyboardMarkup([[BTN_CHECK_PHONE]], resize_keyboard=True)
        await update.message.reply_text(
            "\U0001F50D Raqam tekshirmoqchimisiz?\n\nPastdagi tugmani bosing \U0001F447",
            reply_markup=keyboard,
        )
        return

    admin = is_admin(user.id)
    welcome = (
        "Assalomu alaykum! \U0001F44B\n\n"
        "Bu bot orqali:\n"
        "\u2022 Uyingizni <b>maklersiz</b> ijaraga qo'yishingiz mumkin\n"
        "\u2022 Kanaldagi e'lonlardan uy egasi bilan <b>to'g'ridan-to'g'ri</b> bog'lanishingiz mumkin\n\n"
        "Quyidagi menyudan boshlang \U0001F447"
    )

    await update.message.reply_text(welcome, reply_markup=main_menu_keyboard(user.id), parse_mode=ParseMode.HTML)

    btn = channel_link_button()
    if btn:
        await update.message.reply_text(
            "\U0001F3E0 Barcha e'lonlar kanalimizda:",
            reply_markup=InlineKeyboardMarkup([[btn]]),
        )


async def reveal_phone_core(context: ContextTypes.DEFAULT_TYPE, user_id: int, listing_id) -> None:
    admin = is_admin(user_id)

    if is_banned(user_id):
        await context.bot.send_message(user_id, "\u26a0\ufe0f Sizga botdan foydalanish cheklangan. Savollar bo'lsa, adminga murojaat qiling.")
        return

    listing = get_listing(listing_id) if listing_id else None
    if not listing or listing["status"] != "approved":
        await context.bot.send_message(user_id, "\u26a0\ufe0f Kechirasiz, bu e'lon topilmadi yoki hali tasdiqlanmagan.", reply_markup=main_menu_keyboard(user_id))
        return

    if listing.get("expired"):
        await context.bot.send_message(user_id, "\u2705 Bu uy allaqachon topshirilgan (ijaraga berilgan).", reply_markup=main_menu_keyboard(user_id))
        return

    if is_moderator(user_id) and not admin and int(listing["user_id"]) != int(user_id):
        await context.bot.send_message(
            user_id,
            "\u26a0\ufe0f Kechirasiz, bu e'lon raqamini siz ko'rolmaysiz \u2014 moderator sifatida faqat "
            "o'zingiz joylagan e'lonlar bilan ishlay olasiz.",
            reply_markup=main_menu_keyboard(user_id),
        )
        return

    blocked = get_blocked_phone(listing["telefon"])
    if blocked:
        await context.bot.send_message(
            user_id,
            "\u26a0\ufe0f <b>Ehtiyot bo'ling!</b>\n\nBu raqam bo'yicha oldin shikoyat qayd etilgan.",
            parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(user_id),
        )
        return

    active, expire = is_subscribed(user_id)
    if admin:
        active = True  # Admin uchun har doim cheksiz - obuna holatidan qat'iy nazar.
    has_free = user_free_used(user_id) < user_free_limit(user_id)

    if not active and not has_free:
        log_paywall_hit(user_id, listing_id)
        price = subscription_price()
        days = subscription_days()
        per_day = max(price // days, 0)
        active_count = count_active_subscribers()
        social_proof_line = f"\u2705 {active_count}+ kishi hozir foydalanmoqda\n" if active_count >= 10 else ""
        text = (
            "\U0001F513 <b>Bepul ko'rishlaringiz tugadi</b>\n\n"
            "Yangi uy egalari raqamini ko'rish uchun Limit oling.\n\n"
            f"\U0001F4B3 {days} kun \u2014 <b>{price:,} so'm</b> (kuniga atigi {per_day:,} so'm)\n\n"
            f"\u2705 Kanaldagi BARCHA raqamlarni {days} kun cheklovsiz ko'rasiz\n"
            f"\u2705 Rieltordan bir necha barobar arzon\n"
            f"\u2705 Firibgardan himoyalangan, tekshirilgan e'lonlar\n"
            f"{social_proof_line}"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"\U0001F513 {days} kunlik limit olish", callback_data=f"buy_subscription_{listing_id}")]])
        await context.bot.send_message(user_id, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return

    free_note = ""
    if not active:
        consume_free_view(user_id)
        left = user_free_limit(user_id) - user_free_used(user_id)
        free_note = f"\n\n<i>\U0001F381 Bu \u2014 sizning bepul ko'rishingiz. Yana {max(left,0)} ta bepul ko'rishingiz qoldi.</i>"

    log_phone_reveal(user_id, listing_id)

    await context.bot.send_message(
        user_id, phone_reveal_text(listing) + free_note, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(user_id), disable_web_page_preview=True
    )


async def reveal_phone(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str):
    """/start orqali (masalan eski chuqur-havola) chaqirilganda ishlatiladi."""
    user_id = update.effective_user.id
    try:
        listing_id = int(payload.split("_", 1)[1])
    except (IndexError, ValueError):
        listing_id = None
    await reveal_phone_core(context, user_id, listing_id)


async def channel_phone_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanal postidagi \"Uy egasi raqami\" tugmasi - CALLBACK orqali (chuqur-havola
    EMAS), shuning uchun Telegramning \"qaytgan foydalanuvchida ishlamaydi\" degan
    muammosidan butunlay xoli - har doim, har qanday holatda ishlaydi. Muvaffaqiyatli
    bo'lsa, foydalanuvchini AVTOMATIK ravishda botning shaxsiy chatiga o'tkazadi."""
    query = update.callback_query
    listing_id = int(query.data.rsplit("_", 1)[1])
    try:
        await reveal_phone_core(context, query.from_user.id, listing_id)
        await query.answer(url=f"https://t.me/{context.bot.username}")
    except Exception:
        # Foydalanuvchi botni HECH QACHON ishga tushirmagan (Telegram bunga yo'l
        # qo'ymaydi - botlar notanish odamga birinchi bo'lib yoza olmaydi).
        # Bu holatda ham u ISHONCHLI ishlaydi, chunki bu uning ROSTDAN HAM
        # birinchi /start'i bo'ladi - chuqur-havolalar bunday holatda har doim
        # to'g'ri ishlaydi (faqat "qaytgan" foydalanuvchilarda muammo bo'ladi).
        try:
            await query.answer(url=f"https://t.me/{context.bot.username}?start=phone_{listing_id}")
        except Exception:
            logger.exception("Kanal orqali raqam ko'rsatishda xatolik")


async def text_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    admin = is_admin(user_id)
    staff = is_staff(user_id)

    if text == BTN_LISTINGS:
        listings = get_user_listings(user_id)
        if not listings:
            await update.message.reply_text("Sizda hali e'lonlar yo'q. \u00abE'lon berish\u00bb tugmasini bosing.")
            return
        status_label = {"pending": "\U0001F553 Ko'rib chiqilmoqda", "approved": "\u2705 Tasdiqlangan", "rejected": "\u274c Rad etilgan"}
        lines = []
        active_listings = []
        for lst in listings:
            addr = lst['manzil'] or (lst.get('raw_text') or '')[:40].replace("\n", " ")
            if lst["status"] == "approved" and lst.get("expired"):
                label = "\U0001F534 Topshirilgan (yopilgan)"
            else:
                label = status_label.get(lst['status'], lst['status'])
            line = f"#{lst['id']} \u2014 {esc(addr)} \u2014 {label} ({lst['created_at'][:16]})"
            if lst["status"] == "rejected" and lst.get("reject_reason"):
                line += f"\n   \u21b3 Sabab: {esc(lst['reject_reason'])}"
            lines.append(line)
            if lst["status"] == "approved" and not lst.get("expired"):
                active_listings.append(lst)
        await update.message.reply_text("\U0001F4CB <b>Sizning e'lonlaringiz:</b>\n\n" + "\n".join(lines), parse_mode=ParseMode.HTML)

        if active_listings:
            kb_rows = [[InlineKeyboardButton(f"\u2705 #{lst['id']} topshirildi deb belgilash", callback_data=f"selfexpire_{lst['id']}")] for lst in active_listings]
            await update.message.reply_text(
                "Uy ijaraga berilgan bo'lsa, shu yerdan belgilab qo'ying \u2014 kanaldan avtomatik olib tashlaymiz:",
                reply_markup=InlineKeyboardMarkup(kb_rows),
            )

    elif text == BTN_HELP:
        await show_help_menu(update, context)

    elif text == BTN_LOCATION_ALERT:
        await show_location_alert_screen(update, context)
    elif text == BTN_MY_LOCATIONS:
        await show_my_locations(update, context)
    elif text == BTN_CHANNEL:
        btn = channel_link_button()
        if btn:
            await update.message.reply_text("\U0001F3E0 Barcha e'lonlar kanalimizda:", reply_markup=InlineKeyboardMarkup([[btn]]))
    elif text == BTN_STATS and admin:
        await show_stats(update, context)
    elif text == BTN_STATS and is_moderator(user_id):
        await show_moderator_stats(update, context)
    elif text == BTN_SUBSCRIBERS and admin:
        await show_subscribers(update, context, 0)
    elif text == BTN_SETTINGS and admin:
        await show_settings_menu(update, context)
    elif text == BTN_PENDING and staff:
        await show_pending(update, context)
    elif text == BTN_BLOCKED and admin:
        await show_blocked(update, context, 0)
    elif text == BTN_MODERATORS and admin:
        await show_moderators(update, context, 0)
    elif text == BTN_FLAGGED and admin:
        await show_flagged(update, context, 0)
    elif text == BTN_LISTINGS_MAP and admin:
        await show_listings_map(update, context)
    elif text == BTN_SUBARENDA:
        await show_subarenda_info(update, context)
    elif text == BTN_ADMIN_PANEL and admin:
        await show_admin_panel_link(update, context)


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001F4C5 Kunlik", callback_data="statsperiod_daily"),
         InlineKeyboardButton("\U0001F4C6 Haftalik", callback_data="statsperiod_weekly")],
        [InlineKeyboardButton("\U0001F5D3 Oylik", callback_data="statsperiod_monthly"),
         InlineKeyboardButton("\U0001F4C8 Yillik", callback_data="statsperiod_yearly")],
    ])
    await update.message.reply_text("\U0001F4CA <b>Statistika</b>\n\nQaysi davr bo'yicha ko'rmoqchisiz?", parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def statsperiod_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    period = query.data.rsplit("_", 1)[1]
    text = render_period_stats(period)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001F4C5 Kunlik", callback_data="statsperiod_daily"),
         InlineKeyboardButton("\U0001F4C6 Haftalik", callback_data="statsperiod_weekly")],
        [InlineKeyboardButton("\U0001F5D3 Oylik", callback_data="statsperiod_monthly"),
         InlineKeyboardButton("\U0001F4C8 Yillik", callback_data="statsperiod_yearly")],
    ])
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


# ============================= YORDAM (tugmali, mavzu bo'yicha) =============================

HELP_TOPIC_LABELS = {
    "elon": "\U0001F4DD E'lon qanday beriladi?",
    "limit": "\U0001F513 Limit qanday ishlaydi?",
    "check": "\U0001F50D Raqamni tekshirish nima?",
    "mening": "\U0001F4CB Mening e'lonlarim nima?",
    "hudud": "\U0001F514 Hudud bo'yicha xabar nima?",
}


def get_help_topic_text(topic: str) -> str:
    if topic == "elon":
        price = listing_price()
        return (
            "\U0001F4DD <b>E'lon qanday beriladi?</b>\n\n"
            "1. \u00abE'lon berish\u00bb tugmasini bosing\n"
            "2. \U0001F193 Bepul yoki \U0001F4B0 Pullik turini tanlaysiz:\n"
            "   \u2022 Bepul \u2014 kanalga bir marta joylanadi\n"
            f"   \u2022 Pullik ({price:,} so'm) \u2014 \u00abtopshirildi\u00bb deb belgilamaguningizcha, "
            "har 3 soatda avtomatik qayta joylanadi\n"
            "3. Savollarga (manzil, narx va h.k.) javob berasiz\n"
            "4. 1\u201310 ta rasm yuklaysiz\n"
            "5. Pullik tanlagan bo'lsangiz \u2014 to'lov qilib, chek yuborasiz\n"
            "6. Admin tekshirib tasdiqlaydi, e'lon kanalga chiqadi\n\n"
            "<i>Kuniga bir foydalanuvchi bir necha marta e'lon berishi mumkin.</i>"
        )
    if topic == "limit":
        return (
            "\U0001F513 <b>Limit qanday ishlaydi?</b>\n\n"
            "Har bir yangi foydalanuvchiga bir nechta uy egasi raqamini <b>bepul</b> ko'rish imkoni beriladi.\n\n"
            f"Bepul ko'rishlar tugagach, <b>{subscription_price():,} so'm / {subscription_days()} kun</b> evaziga "
            f"limit sotib olib, shu muddat davomida kanaldagi <b>barcha</b> uy egalari bilan cheklovsiz bog'lana olasiz."
        )
    if topic == "check":
        return (
            "\U0001F50D <b>Raqamni tekshirish nima?</b>\n\n"
            "Agar sizga biror telefon raqami shubhali tuyulsa, shu tugma orqali uni yozib tekshirishingiz mumkin.\n\n"
            "Agar bu raqam bo'yicha oldin shikoyat qayd etilgan bo'lsa, sizni ogohlantiramiz."
        )
    if topic == "mening":
        return (
            "\U0001F4CB <b>Mening e'lonlarim nima?</b>\n\n"
            "Bu yerda o'zingiz bergan barcha e'lonlaringizning holatini (kutilmoqda / tasdiqlangan / rad etilgan) ko'rasiz.\n\n"
            "Agar uyingiz allaqachon ijaraga berilgan bo'lsa, shu yerdan \u00abtopshirildi\u00bb deb belgilab, "
            "kanaldan olib tashlashingiz mumkin."
        )
    if topic == "hudud":
        return (
            "\U0001F514 <b>Hudud bo'yicha xabar nima?</b>\n\n"
            "Sizga kerakli hududni (masalan: Yunusobod) saqlab qo'ysangiz, aynan shu hududdan yangi e'lon "
            "chiqqanda botimiz sizga <b>darhol</b> xabar beradi \u2014 kanalni doim kuzatib turishning hojati yo'q."
        )
    return ""


async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"help_{k}")] for k, label in HELP_TOPIC_LABELS.items()])
    await update.message.reply_text("\u2753 <b>Yordam</b>\n\nQaysi mavzu bo'yicha yordam kerak?", parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def help_topic_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data.split("_", 1)[1]
    text = get_help_topic_text(topic)
    if not text:
        return
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Orqaga", callback_data="help_back")]])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def help_back_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"help_{k}")] for k, label in HELP_TOPIC_LABELS.items()])
    await query.edit_message_text("\u2753 <b>Yordam</b>\n\nQaysi mavzu bo'yicha yordam kerak?", parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ============================= HUDUD BO'YICHA XABAR (UI) =============================

def get_user_locations(user_id: int) -> list:
    conn = db()
    rows = conn.execute(
        """SELECT id, manzil, latitude, longitude, channel_msg_id, status, expired, created_at
           FROM listings WHERE user_id = ? AND latitude IS NOT NULL AND longitude IS NOT NULL
           ORDER BY created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def categorize_district(manzil: str, moljal: str) -> str:
    """Manzil/mo'ljal matnidan tuman nomini aniqlaydi (mavjud DISTRICT_ALIASES
    lug'atidan foydalanib). Topilmasa \"Aniqlanmagan\" qaytaradi."""
    haystack = normalize_location_text(f"{manzil or ''} {moljal or ''}")
    for canonical, aliases in DISTRICT_ALIASES.items():
        for alias in aliases:
            if normalize_location_text(alias) in haystack:
                return canonical.title()
    return "Aniqlanmagan"


def get_active_listings_with_location() -> list:
    conn = db()
    rows = conn.execute(
        """SELECT id, manzil, moljal, latitude, longitude FROM listings
           WHERE status = 'approved' AND COALESCE(expired,0) = 0
           AND latitude IS NOT NULL AND longitude IS NOT NULL"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def show_subarenda_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Uy egalari uchun \"Subarenda\" (uzoq muddatli boshqaruv) dasturi haqida
    ma'lumot va ariza sahifasiga havola."""
    if not DASHBOARD_URL:
        await update.message.reply_text("\u26a0\ufe0f Bu xizmat hali sozlanmagan.")
        return
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F4DD Ariza qoldirish", url=f"{DASHBOARD_URL}/subarenda")]])
    await update.message.reply_text(
        "\U0001F3E2 <b>Subarenda dasturi</b>\n\n"
        "Uyingizni bizga uzoq muddatga bering \u2014 qolganini biz bajaramiz:\n\n"
        "\u2705 Ijarachini biz topamiz\n"
        "\u2705 Har oy kafolatlangan to'lov (uy bo'sh tursa ham)\n"
        "\u2705 Rasmiy shartnoma asosida\n"
        "\u2705 Uy holatini muntazam nazorat qilamiz\n\n"
        "Qiziqsangiz, pastdagi tugma orqali ariza qoldiring \u2014 24 soat ichida bog'lanamiz.",
        parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )


async def show_admin_panel_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panelga (statistika+xarita) tashqi brauzer orqali kirish tugmasi -
    parol (Basic Auth) tashqi brauzerda to'g'ri ishlashi uchun WebApp emas,
    oddiy URL tugma ishlatiladi."""
    if not DASHBOARD_URL:
        await update.message.reply_text("\u26a0\ufe0f Admin panel hali sozlanmagan (.env da DASHBOARD_URL yo'q).")
        return
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F5A5 Admin Panelni ochish", url=f"{DASHBOARD_URL}/admin")]])
    await update.message.reply_text(
        "\U0001F5A5 <b>Admin Panel</b>\n\nStatistika va xaritani ko'rish uchun pastdagi tugmani bosing.",
        parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )


async def postmap_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin buyrug'i (/postmap) - kanalga, hamma foydalanuvchilar bosishi
    mumkin bo'lgan, PAROLSIZ ommaviy xarita havolasi bilan post joylaydi."""
    if not is_admin(update.effective_user.id):
        return
    if not DASHBOARD_URL:
        await update.message.reply_text("\u26a0\ufe0f DASHBOARD_URL .env faylida sozlanmagan.")
        return
    if not CHANNEL_ID:
        await update.message.reply_text("\u26a0\ufe0f CHANNEL_ID sozlanmagan.")
        return
    listings = get_active_listings_with_location()
    text = (
        "\U0001F5FA <b>Barcha uylarni xaritada ko'ring!</b>\n\n"
        f"Hozirda <b>{len(listings)} ta</b> faol e'lon xaritada belgilangan \u2014 "
        "narxlari bilan birga. O'zingizga qulay hududni tanlab, mos uyni toping.\n\n"
        "Pastdagi tugmani bosing \U0001F447"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F5FA Xaritani ochish", url=f"{DASHBOARD_URL}/xarita")]])
    try:
        await context.bot.send_message(CHANNEL_ID, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        await update.message.reply_text("\u2705 Xarita posti kanalga joylandi.")
    except Exception:
        logger.exception("Xarita postini kanalga yuborib bo'lmadi")
        await update.message.reply_text("\u26a0\ufe0f Postni yuborishda xatolik yuz berdi.")


async def show_listings_map(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin uchun - barcha FAOL, joylashuv biriktirilgan e'lonlarni BITTA
    statik xarita rasmida, tuman bo'yicha sonlar bilan ko'rsatadi. Bepul
    OpenStreetMap xarita-plitalaridan foydalanadi - domen yoki API kalit shart emas."""
    listings = get_active_listings_with_location()
    if not listings:
        await update.message.reply_text("\u26a0\ufe0f Hozircha joylashuv biriktirilgan faol e'lon yo'q.")
        return

    district_counts: dict = {}
    for lst in listings:
        name = categorize_district(lst.get("manzil"), lst.get("moljal"))
        district_counts[name] = district_counts.get(name, 0) + 1

    await update.message.reply_text(f"\U0001F5FA Xarita tayyorlanmoqda... ({len(listings)} ta e'lon)")

    try:
        from staticmap import StaticMap, CircleMarker
        m = StaticMap(
            900, 700, url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
            headers={"User-Agent": "IjaragaUylarBot/1.0 (+https://t.me/ijaraga_uylar)"},
        )
        for lst in listings:
            m.add_marker(CircleMarker((lst["longitude"], lst["latitude"]), "#E74C3C", 14))
        image = m.render(zoom=11)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        buf.name = "xarita.png"
    except Exception:
        logger.exception("Xarita rasmini yaratib bo'lmadi")
        await update.message.reply_text(
            "\u26a0\ufe0f Xarita rasmini yaratishda xatolik yuz berdi.\n\n"
            "Iltimos, serverda quyidagi buyruqni bajarganingizga ishonch hosil qiling:\n"
            "<code>pip install staticmap --break-system-packages</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = [f"\U0001F5FA <b>Faol e'lonlar xaritasi</b> \u2014 jami {len(listings)} ta\n"]
    for name, cnt in sorted(district_counts.items(), key=lambda x: -x[1]):
        lines.append(f"\u2022 {esc(name)}: {cnt} ta")
    await context.bot.send_photo(update.effective_chat.id, buf, caption="\n".join(lines), parse_mode=ParseMode.HTML)


async def show_my_locations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    listings = get_user_locations(user_id)
    if not listings:
        await update.message.reply_text(
            "\U0001F4CD Sizda hali joylashuv bilan berilgan e'lon yo'q.\n\n"
            "E'lon berishda \u00abJoylashuvni yuborish\u00bb bosqichida joylashuv qo'shsangiz, "
            "u shu yerda ko'rinadi."
        )
        return

    lines = [f"\U0001F4CD <b>Mening lokatsiyalarim</b> ({len(listings)} ta)\n"]
    for lst in listings:
        if lst.get("expired"):
            holat = "\u2705 Topshirilgan"
        elif lst["status"] == "approved":
            holat = "\U0001F7E2 Faol"
        elif lst["status"] == "pending":
            holat = "\U0001F553 Kutilmoqda"
        else:
            holat = "\u274c Rad etilgan"
        line = f"\u2022 <b>{esc(lst['manzil'])}</b> \u2014 {holat}"
        if lst.get("channel_msg_id") and CHANNEL_USERNAME:
            line += f"\n  <a href=\"https://t.me/{CHANNEL_USERNAME}/{lst['channel_msg_id']}\">Postni ko'rish</a>"
        lines.append(line)
    await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    # Har bir joylashuvni xarita-xabar sifatida ham alohida yuboramiz - shunda
    # foydalanuvchi to'g'ridan-to'g'ri Telegram xaritasida ko'ra oladi.
    for lst in listings[:10]:  # spam bo'lmasligi uchun eng oxirgi 10 tasi
        try:
            await context.bot.send_location(user_id, latitude=lst["latitude"], longitude=lst["longitude"])
        except Exception:
            logger.exception("Foydalanuvchiga joylashuv xabarini yuborib bo'lmadi")


async def show_location_alert_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    alerts = get_user_location_alerts(user_id)
    lines = ["\U0001F514 <b>Hudud bo'yicha xabar</b>\n",
             "<i>Sizga mos hududdan yangi e'lon chiqqanda, darhol xabar beramiz.</i>\n"]
    kb_rows = []
    if not alerts:
        lines.append("<i>Hozircha saqlangan hududingiz yo'q.</i>")
    for a in alerts:
        lines.append(f"\u2022 \U0001F4CD {esc(a['location'])}")
        kb_rows.append([InlineKeyboardButton(f"\U0001F5D1 O'chirish: {a['location'][:20]}", callback_data=f"delloc_{a['id']}")])
    if len(alerts) < MAX_LOCATION_ALERTS:
        kb_rows.append([InlineKeyboardButton("\u2795 Hudud qo'shish", callback_data="addloc")])
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb_rows))


async def addloc_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    alerts = get_user_location_alerts(query.from_user.id)
    if len(alerts) >= MAX_LOCATION_ALERTS:
        await query.answer(f"Maksimal {MAX_LOCATION_ALERTS} ta hudud saqlash mumkin.", show_alert=True)
        return ConversationHandler.END
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u274c Bekor qilish", callback_data="nav_cancel")]])
    await query.message.reply_text(
        "\U0001F4CD Qaysi hududda uy qidiryapsiz? (masalan: <code>Yunusobod</code>)\n\n"
        "Lotin yoki Kirill, farqi yo'q \u2014 ikkalasini ham tanib olamiz.",
        parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )
    return LOCATION_WAIT


async def addloc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Bekor qilindi.")
    return ConversationHandler.END


async def addloc_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    if not raw or len(raw) > 60:
        await update.message.reply_text("\u26a0\ufe0f Iltimos, 1\u201360 belgidan iborat hudud nomini yozing:")
        return LOCATION_WAIT
    add_location_alert(update.effective_user.id, raw)
    await update.message.reply_text(f"\u2705 Saqlandi: <code>{esc(raw)}</code>", parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(update.effective_user.id))
    await show_location_alert_screen(update, context)
    return ConversationHandler.END


async def delloc_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    alert_id = int(query.data.rsplit("_", 1)[1])
    delete_location_alert(alert_id, query.from_user.id)
    await query.answer("O'chirildi \u2705")
    await show_location_alert_screen(update, context)


PRIORITY_ALERT_DELAY_SECONDS = 2 * 60 * 60  # Avito uslubi: bepul foydalanuvchiga 2 soat kech yuboriladi


async def _send_delayed_location_alert(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    try:
        await context.bot.send_message(data["user_id"], data["text"], parse_mode=ParseMode.HTML, reply_markup=data["keyboard"])
        logger.info("Hudud-xabar (kechiktirilgan, bepul foydalanuvchi) yuborildi: user_id=%s", data["user_id"])
    except Exception:
        logger.exception("Kechiktirilgan hudud-xabarni yuborib bo'lmadi: user_id=%s", data["user_id"])


async def notify_location_alert_matches(context: ContextTypes.DEFAULT_TYPE, listing: dict) -> None:
    matches = find_matching_location_alerts(listing)
    logger.info("Hudud-xabar tekshiruvi: listing_id=%s, topilgan moslik soni=%s", listing.get("id"), len(matches))
    if not matches:
        return
    link = None
    if CHANNEL_USERNAME and listing.get("channel_msg_id"):
        link = f"https://t.me/{CHANNEL_USERNAME}/{listing['channel_msg_id']}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F440 E'lonni ko'rish", url=link)]]) if link else None
    addr = (listing.get("manzil") or (listing.get("raw_text") or "")[:60]).strip()

    for a in matches:
        active, _ = is_subscribed(a["user_id"])
        base_text = (
            f"\U0001F514 <b>Sizga mos yangi uy chiqdi!</b>\n\n"
            f"\U0001F4CD {esc(addr)}\n\n"
            f"<i>Saqlangan hudud: {esc(a['location'])}</i>"
        )
        if active:
            # Limit egalari - DARHOL, birinchi bo'lib bilishadi (Avito uslubidagi ustuvorlik).
            try:
                await context.bot.send_message(a["user_id"], base_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                logger.info("Hudud-xabar DARHOL yuborildi (limit egasi): user_id=%s, hudud=%s", a["user_id"], a["location"])
            except Exception:
                logger.exception("Hudud bildirishnomasini yuborib BO'LMADI: user_id=%s, hudud=%s", a["user_id"], a["location"])
        else:
            # Bepul foydalanuvchi - kechiktirilgan xabar, limit sotib olishga undovchi eslatma bilan.
            delayed_text = base_text + (
                "\n\n\u23f3 <i>Limit egalari buni 2 soat oldin bilib, ko'rib ulgurishdi. "
                "Keyingi safar birinchi bo'lib bilish uchun Limit sotib oling!</i>"
            )
            if context.job_queue:
                context.job_queue.run_once(
                    _send_delayed_location_alert, PRIORITY_ALERT_DELAY_SECONDS,
                    data={"user_id": a["user_id"], "text": delayed_text, "keyboard": keyboard},
                )
                logger.info("Hudud-xabar navbatga qo'yildi (bepul, %s soniya kech): user_id=%s", PRIORITY_ALERT_DELAY_SECONDS, a["user_id"])
            else:
                # JobQueue mavjud bo'lmasa (juda kamdan-kam holat) - hech kimni butunlay
                # mahrum qilmaslik uchun, baribir darhol yuboramiz.
                try:
                    await context.bot.send_message(a["user_id"], base_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                except Exception:
                    logger.exception("Hudud bildirishnomasini yuborib BO'LMADI: user_id=%s", a["user_id"])


# ============================= MODERATOR SHAXSIY STATISTIKASI =============================

def count_listings_stats_by_user(user_id: int) -> dict:
    conn = db()
    row = conn.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN status='approved' AND COALESCE(expired,0)=0 THEN 1 ELSE 0 END) AS active,
                  SUM(CASE WHEN status='approved' AND COALESCE(expired,0)=1 THEN 1 ELSE 0 END) AS closed,
                  SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) AS rejected,
                  SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending
           FROM listings WHERE user_id = ?""",
        (user_id,),
    ).fetchone()
    conn.close()
    return {
        "total": row["total"] or 0, "active": row["active"] or 0, "closed": row["closed"] or 0,
        "rejected": row["rejected"] or 0, "pending": row["pending"] or 0,
    }


TRUSTED_MIN_LISTINGS = 3


def is_trusted_poster(user_id) -> bool:
    """Airbnb uslubidagi ishonch belgisi: kamida TRUSTED_MIN_LISTINGS ta
    tasdiqlangan e'lon bergan VA hech qanday shikoyat olmagan e'lon beruvchi."""
    if not user_id:
        return False
    stats = count_listings_stats_by_user(user_id)
    if (stats["active"] + stats["closed"]) < TRUSTED_MIN_LISTINGS:
        return False
    return count_reports_received(user_id) == 0


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
        rasmlar.append(update.message.photo[-1].file_id)
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


# ============================= E'LON YARATISH OQIMI =============================

async def elon_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("\u26a0\ufe0f Sizga botdan foydalanish cheklangan. Savollar bo'lsa, adminga murojaat qiling.")
        return ConversationHandler.END
    if is_admin(user.id):
        daily_limit = None  # cheksiz
    elif is_moderator(user.id):
        daily_limit = MOD_DAILY_LISTINGS
    else:
        daily_limit = MAX_DAILY_LISTINGS
    if daily_limit is not None and count_today_listings(user.id) >= daily_limit:
        await update.message.reply_text(
            f"\u26a0\ufe0f Siz bugun uchun ruxsat etilgan {daily_limit} ta e'lon chegarasiga yetdingiz.\nErtaga qayta urinib ko'ring."
        )
        return ConversationHandler.END

    context.user_data.clear()
    context.user_data["rasmlar"] = []

    if is_staff(user.id):
        # Xodim (admin/moderator) uchun tanlov shart emas - u har doim
        # to'lovsiz, to'g'ridan-to'g'ri joylash usulidan foydalanadi.
        context.user_data["listing_is_paid"] = False
        return await ask_rental_type(update, context)

    price = listing_price()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001F193 Bepul e'lon", callback_data="listingtype_free")],
        [InlineKeyboardButton(f"\U0001F4B0 Pullik e'lon \u2014 {price:,} so'm", callback_data="listingtype_paid")],
        [InlineKeyboardButton("\u274c Bekor qilish", callback_data="nav_cancel")],
    ])
    text = (
        "\U0001F4E2 <b>E'lon turini tanlang</b>\n\n"
        "\U0001F193 <b>Bepul e'lon</b> joylasangiz \u2014 kanalga bir marta joylanadi.\n\n"
        "\U0001F4B0 <b>Pullik e'lon</b> bersangiz \u2014 sizning eloningiz kanalda va veb-saytda "
        "<b>uyingiz topshirilgunicha (kamida 7 kun)</b> doimiy TOP'da, avtomatik ravishda qayta-qayta joylab "
        "turiladi \u2014 ko'proq odam ko'radi, tezroq topiladi."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    return LISTING_TYPE_CHOICE


async def listing_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["listing_is_paid"] = query.data == "listingtype_paid"
    context.user_data.setdefault("rasmlar", [])
    await query.edit_message_reply_markup(reply_markup=None)
    return await ask_rental_type(update, context)


RENTAL_TYPE_OPTIONS = [
    ("uzoq_muddat", "\U0001F3E0 Uzoq muddatli ijara"),
    ("kunlik", "\U0001F4C5 Kunlik ijara (sutkalik)"),
    ("dacha", "\U0001F333 Dacha"),
    ("mehmonxona", "\U0001F6CF Mehmonxona / mehmon xona"),
]
RENTAL_TYPE_LABELS = dict(RENTAL_TYPE_OPTIONS)


async def ask_rental_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=f"rentaltype_{key}")] for key, label in RENTAL_TYPE_OPTIONS]
        + [[InlineKeyboardButton("\u274c Bekor qilish", callback_data="nav_cancel")]]
    )
    text = "\U0001F3F7\ufe0f <b>Uy qanday turdagi ijaraga beriladi?</b>"
    if update.callback_query:
        await context.bot.send_message(update.effective_chat.id, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    return RENTAL_TYPE_CHOICE


async def rental_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["rental_type"] = query.data.split("_", 1)[1]
    await query.edit_message_reply_markup(reply_markup=None)
    return await render_step(update, context, 0)


async def channel_elon_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanal postidagi \"E'lon berish\" tugmasi - CALLBACK orqali (chuqur-havola
    EMAS). E'lon berish ko'p bosqichli jarayon bo'lgani uchun, buni to'g'ridan
    -to'g'ri, hech qanday tugma bosishsiz boshlash texnik jihatdan ishonchsiz
    bo'lardi (Telegramning suhbat-holati talab qiladi) - shuning uchun BU YERDA
    darhol \"E'lon turini tanlang\" ekrani ko'rsatiladi, va uni tanlash orqali
    suhbat TO'G'RI, ISHONCHLI tarzda, hech qachon \"osilib qolmasdan\" boshlanadi."""
    query = update.callback_query
    user = query.from_user

    # ENG MUHIM QATOR: agar foydalanuvchi oldin biror bosqichda (Manzil,
    # Mo'ljal va h.k.) "qolib ketgan" bo'lsa, shu eski holatni MAJBURIY
    # tozalaymiz - shunda pastda yuboriladigan yangi ekran har doim TO'G'RI
    # ishlaydi, hech qachon "sukut" (hech narsa bo'lmaydigan) holat kelib chiqmaydi.
    force_reset_conversation(context, "elon_conv", user.id)

    if is_banned(user.id):
        try:
            await context.bot.send_message(user.id, "\u26a0\ufe0f Sizga botdan foydalanish cheklangan. Savollar bo'lsa, adminga murojaat qiling.")
            await query.answer(url=f"https://t.me/{context.bot.username}")
        except Exception:
            await query.answer(url=f"https://t.me/{context.bot.username}?start=elon")
        return

    if is_admin(user.id):
        daily_limit = None
    elif is_moderator(user.id):
        daily_limit = MOD_DAILY_LISTINGS
    else:
        daily_limit = MAX_DAILY_LISTINGS
    if daily_limit is not None and count_today_listings(user.id) >= daily_limit:
        try:
            await context.bot.send_message(
                user.id,
                f"\u26a0\ufe0f Siz bugun uchun ruxsat etilgan {daily_limit} ta e'lon chegarasiga yetdingiz.\nErtaga qayta urinib ko'ring.",
            )
            await query.answer(url=f"https://t.me/{context.bot.username}")
        except Exception:
            await query.answer(url=f"https://t.me/{context.bot.username}?start=elon")
        return

    context.user_data.clear()
    context.user_data["rasmlar"] = []

    try:
        if is_staff(user.id):
            # Xodim uchun tanlov shart emas, lekin uni to'g'ridan-to'g'ri Manzil
            # bosqichiga "majburlash" ishonchsiz bo'lardi - shuning uchun bitta
            # aniq, har doim ishlaydigan tugma orqali davom ettiramiz.
            await context.bot.send_message(
                user.id, "\U0001F3E0 Uyingizni ijaraga bermoqchimisiz?\n\nPastdagi tugmani bosing \U0001F447",
                reply_markup=ReplyKeyboardMarkup([[BTN_ELON]], resize_keyboard=True),
            )
        else:
            price = listing_price()
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001F193 Bepul e'lon", callback_data="listingtype_free")],
                [InlineKeyboardButton(f"\U0001F4B0 Pullik e'lon \u2014 {price:,} so'm", callback_data="listingtype_paid")],
                [InlineKeyboardButton("\u274c Bekor qilish", callback_data="nav_cancel")],
            ])
            text = (
                "\U0001F4E2 <b>E'lon turini tanlang</b>\n\n"
                "\U0001F193 <b>Bepul e'lon</b> joylasangiz \u2014 kanalga bir marta joylanadi.\n\n"
                "\U0001F4B0 <b>Pullik e'lon</b> bersangiz \u2014 sizning eloningiz kanalda va veb-saytda "
                "<b>uyingiz topshirilgunicha (kamida 7 kun)</b> doimiy TOP'da, avtomatik ravishda qayta-qayta joylab "
                "turiladi \u2014 ko'proq odam ko'radi, tezroq topiladi."
            )
            await context.bot.send_message(user.id, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        await query.answer(url=f"https://t.me/{context.bot.username}")
    except Exception:
        # Foydalanuvchi botni HECH QACHON ishga tushirmagan - bu uning ROSTDAN
        # HAM birinchi /start'i bo'lgani uchun, chuqur-havola bu yerda ishonchli
        # ishlaydi (faqat "qaytgan" foydalanuvchilarda muammo bo'ladi).
        try:
            await query.answer(url=f"https://t.me/{context.bot.username}?start=elon")
        except Exception:
            logger.exception("Kanal orqali elon-berish oynasini ochishda xatolik")


async def nav_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "nav_cancel":
        await query.edit_message_text("\u274c E'lon berish bekor qilindi.")
        context.user_data.clear()
        return ConversationHandler.END
    idx = max(0, context.user_data.get("step_idx", 0) - 1)
    return await render_step(update, context, idx)


async def text_step_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END

    idx = context.user_data.get("step_idx", 0)
    step = STEPS[idx]
    raw = (update.message.text or "").strip()

    if not raw:
        await update.message.reply_text("\u26a0\ufe0f Bo'sh bo'lishi mumkin emas. Qaytadan yozing:")
        return step["state"]

    maxlen = step.get("maxlen")
    if maxlen and len(raw) > maxlen:
        await update.message.reply_text(f"\u26a0\ufe0f Matn juda uzun ({len(raw)} ta belgi). Iltimos, {maxlen} ta belgidan qisqaroq yozing:")
        return step["state"]

    if step["kind"] == "phone":
        phone = normalize_phone(raw)
        if not phone:
            await update.message.reply_text("\u26a0\ufe0f Telefon raqami noto'g'ri formatda. Masalan: +998901234567. Qaytadan yozing:")
            return step["state"]
        blocked = get_blocked_phone(phone)
        if blocked:
            await update.message.reply_text(
                "\u26a0\ufe0f <b>Ehtiyot bo'ling!</b>\n\n"
                "Bu raqam bo'yicha oldin shikoyat qayd etilgan, shuning uchun bu raqam bilan "
                "e'lon joylashtirib bo'lmaydi. Agar xato deb hisoblasangiz, "
                f"@{ADMIN_USERNAME} ga murojaat qiling.\n\n"
                "Boshqa (to'g'ri) raqamni yozing:",
                parse_mode=ParseMode.HTML,
            )
            return step["state"]
        context.user_data[step["field"]] = phone
    else:
        context.user_data[step["field"]] = raw

    if idx + 1 < len(STEPS):
        return await render_step(update, context, idx + 1)
    return await ask_location_optional(update, context)


BTN_SEND_LOCATION = "\U0001F4CD Joylashuvni yuborish"
BTN_SKIP_LOCATION = "\u23ED O'tkazib yuborish"


BTN_PICK_LOCATION = "\U0001F5FA Xaritadan tanlash"


BTN_LOCATION_BACK = "\u2b05\ufe0f Orqaga"


async def ask_location_optional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    dashboard_https_ready = DASHBOARD_URL.startswith("https://")
    if dashboard_https_ready:
        # ENG QULAY YO'L: WebApp orqali, xaritadan istalgan nuqtani bosib tanlash.
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_PICK_LOCATION, web_app=WebAppInfo(url=f"{DASHBOARD_URL}/tanla-joy"))],
             [BTN_LOCATION_BACK, BTN_SKIP_LOCATION]],
            resize_keyboard=True,
        )
        text = (
            "\U0001F4CD <b>Uyning aniq joylashuvini xaritada ko'rsatmoqchimisiz?</b> <i>(ixtiyoriy)</i>\n\n"
            "Bu \u2014 ijarachilarga uyni xaritadan topishga yordam beradi.\n\n"
            "\U0001F447 Pastdagi <b>\U0001F5FA Xaritadan tanlash</b> tugmasini bosing, xaritani suring va "
            "uyning turgan nuqtasini markazga keltirib, tasdiqlang.\n\n"
            "Xohlamasangiz, o'tkazib yuborishingiz mumkin.\n\n"
            f"<i>Bosqich 8/{TOTAL_DISPLAY_STEPS}</i>"
        )
    else:
        # Zaxira yo'l (DASHBOARD_URL hali HTTPS bilan sozlanmagan bo'lsa).
        keyboard = ReplyKeyboardMarkup([[BTN_LOCATION_BACK, BTN_SKIP_LOCATION]], resize_keyboard=True)
        text = (
            "\U0001F4CD <b>Uyning aniq joylashuvini xaritada ko'rsatmoqchimisiz?</b> <i>(ixtiyoriy)</i>\n\n"
            "Bu \u2014 ijarachilarga uyni xaritadan topishga yordam beradi.\n\n"
            "\U0001F447 <b>Qanday yuborish kerak:</b>\n"
            "1. Pastdagi xabar yozish maydonining yonidagi \U0001F4CE (qog'oz qisqich) belgisini bosing\n"
            "2. \u00abJoylashuv\u00bb (Location) ni tanlang\n"
            "3. Ochilgan xaritada, <b>uyning aniq turgan nuqtasini</b> qo'lingiz bilan bosib/siljitib belgilang\n"
            "4. \u00abTanlangan joylashuvni yuborish\u00bb tugmasini bosing\n\n"
            "Xohlamasangiz, pastdagi tugma orqali o'tkazib yuborishingiz mumkin.\n\n"
            f"<i>Bosqich 8/{TOTAL_DISPLAY_STEPS}</i>"
        )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    return LOCATION_OPTIONAL


async def location_picked_via_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """WebApp xaritasidan tanlangan nuqta shu yerga keladi (Telegram.WebApp.sendData orqali)."""
    try:
        payload = json.loads(update.message.web_app_data.data)
        lat = float(payload["lat"])
        lon = float(payload["lon"])
    except Exception:
        logger.exception("WebApp joylashuv ma'lumotini o'qib bo'lmadi")
        await update.message.reply_text("\u26a0\ufe0f Joylashuvni o'qib bo'lmadi. Qaytadan urinib ko'ring yoki o'tkazib yuboring.")
        return LOCATION_OPTIONAL
    context.user_data["latitude"] = lat
    context.user_data["longitude"] = lon
    await update.message.reply_text("\u2705 Joylashuv qabul qilindi:", reply_markup=ReplyKeyboardRemove())
    # Telegramning odatiy joylashuv-xabari (kichik xarita bilan) - foydalanuvchi
    # o'zi tanlagan nuqtani ANIQ, tanish ko'rinishda ko'rishi uchun.
    try:
        await context.bot.send_location(update.effective_chat.id, latitude=lat, longitude=lon)
    except Exception:
        logger.exception("Tanlangan joylashuv xabarini yuborib bo'lmadi")
    return await start_photos(update, context)


async def location_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    loc = update.message.location
    context.user_data["latitude"] = loc.latitude
    context.user_data["longitude"] = loc.longitude
    await update.message.reply_text("\u2705 Joylashuv qabul qilindi!", reply_markup=ReplyKeyboardRemove())
    return await start_photos(update, context)


async def location_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    await update.message.reply_text("Yaxshi, joylashuvsiz davom etamiz.", reply_markup=ReplyKeyboardRemove())
    return await start_photos(update, context)


async def location_back_to_telefon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Joylashuv bosqichidan \"Orqaga\" bosilsa - to'g'ridan-to'g'ri TELEFON
    bosqichiga qaytadi (Narxga sakrab ketish xatosi bartaraf etilgan)."""
    await update.message.reply_text("\u2b05\ufe0f", reply_markup=ReplyKeyboardRemove())
    return await render_step(update, context, 6)  # 6 = TELEFON bosqichi indeksi


async def location_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    keyboard = ReplyKeyboardMarkup([[BTN_SKIP_LOCATION]], resize_keyboard=True)
    await update.message.reply_text(
        "\u26a0\ufe0f Iltimos, pastdagi tugmalardan birini bosing.", reply_markup=keyboard
    )
    return LOCATION_OPTIONAL


async def start_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["photo_status_msg_id"] = None
    await update_photo_status(update, context)
    return RASMLAR


async def rasm_back_to_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Rasmlar bosqichidan \"Orqaga\" bosilsa - to'g'ridan-to'g'ri Joylashuv
    bosqichiga qaytadi (Narxga sakrab ketish xatosi bartaraf etilgan)."""
    query = update.callback_query
    await query.answer()
    return await ask_location_optional(update, context)


async def rasm_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        rasmlar = context.user_data.setdefault("rasmlar", [])
        if len(rasmlar) >= MAX_PHOTOS:
            await update.message.reply_text(f"\u26a0\ufe0f Maksimal {MAX_PHOTOS} ta rasm yuborish mumkin.")
            return RASMLAR
        rasmlar.append(update.message.photo[-1].file_id)
        await update_photo_status(update, context)
        return RASMLAR

    if await try_escape_to_menu(update, context):
        return ConversationHandler.END

    await update.message.reply_text("\u26a0\ufe0f Iltimos, RASM yuboring yoki yuqoridagi tugmalardan foydalaning.")
    return RASMLAR


async def rasm_tayyor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data
    caption = build_caption(data, context.bot.username)
    rasmlar = data["rasmlar"]
    chat_id = update.effective_chat.id
    user = update.effective_user

    photos_ok = await send_photos(context, chat_id, rasmlar)
    if not photos_ok:
        await context.bot.send_message(
            chat_id,
            "\u26a0\ufe0f Rasmlarni ko'rsatishda tarmoq muammosi yuz berdi. \u00abOrqaga\u00bb tugmasi orqali rasmlar "
            "bosqichiga qaytib, \u00abTayyor\u00bb ni qayta bosing.",
        )
    try:
        await send_with_retry(context.bot.send_message, chat_id, caption, parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("E'lon matnini ko'rsatishda xatolik")
        await context.bot.send_message(chat_id, "\u26a0\ufe0f E'lon matnini ko'rsatishda tarmoq muammosi yuz berdi.")

    # Tugma matni narxga qarab DINAMIK: agar to'lov shart bo'lmasa (xodim yoki
    # foydalanuvchi "Bepul e'lon" tanlagan bo'lsa), "to'lov" so'zi umuman ko'rinmaydi.
    if is_staff(user.id) or not context.user_data.get("listing_is_paid"):
        confirm_label = "\u2705 To'g'ri, joylash"
    else:
        confirm_label = "\u2705 To'g'ri, to'lovga o'tish"

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(confirm_label, callback_data="tasdiqlash_ok")],
            [InlineKeyboardButton("\u25c0\ufe0f Orqaga", callback_data="nav_back")],
            [InlineKeyboardButton("\u274c Bekor qilish", callback_data="nav_cancel")],
        ]
    )
    await context.bot.send_message(chat_id, "Tepadagi ma'lumotlarni tekshirib, tasdiqlang \U0001F446", reply_markup=keyboard)
    return TASDIQLASH


async def tasdiqlash_nav_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "nav_cancel":
        await query.edit_message_text("\u274c E'lon berish bekor qilindi.")
        context.user_data.clear()
        return ConversationHandler.END
    await query.edit_message_reply_markup(reply_markup=None)
    context.user_data["photo_status_msg_id"] = None
    await update_photo_status(update, context)
    return RASMLAR


async def tasdiqlash_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await remind_buttons(update, context, TASDIQLASH)


async def tasdiqlash_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    user = update.effective_user
    data = context.user_data

    if is_staff(user.id):
        data["user_id"] = user.id
        data["username"] = user.username
        data["full_name"] = user.full_name
        data["sender_phone"] = None
        data["payment_receipt"] = None

        listing_id = save_listing(data, 0)
        listing = get_listing(listing_id)
        channel_msg_id = await send_listing_to_channel(context, listing)

        if channel_msg_id is None:
            await context.bot.send_message(
                update.effective_chat.id,
                f"\u26a0\ufe0f Kanalga joylashda xatolik yuz berdi. E'lon #{listing_id} bazada saqlandi, "
                f"\u00abMening e'lonlarim\u00bbdan holatini tekshirishingiz mumkin.",
            )
        else:
            update_listing_status(listing_id, "approved", channel_msg_id=channel_msg_id)
            listing["channel_msg_id"] = channel_msg_id
            await notify_location_alert_matches(context, listing)
            await context.bot.send_message(
                update.effective_chat.id,
                f"\u2705 Xodim sifatida e'loningiz (#{listing_id}) to'lovsiz va tekshiruvsiz, to'g'ridan-to'g'ri kanalga joylandi.",
                reply_markup=main_menu_keyboard(update.effective_user.id),
            )
        context.user_data.clear()
        return ConversationHandler.END

    price = listing_price() if data.get("listing_is_paid") else 0
    note = ""
    subscribed, _ = is_subscribed(user.id)
    if subscribed and price > 0:
        discount = subscriber_discount_percent()
        if discount:
            price = round(price * (100 - discount) / 100 / 1000) * 1000
            note = f"\n\n\U0001F381 Siz faol limitga egasiz \u2014 narxga {discount}% chegirma qo'llanildi!"

    if price <= 0:
        # E'lon narxi 0 qilib qo'yilgan (admin sozlamasi) - to'lov/chek talab qilinmaydi.
        data["user_id"] = user.id
        data["username"] = user.username
        data["full_name"] = user.full_name
        data["sender_phone"] = None
        data["payment_receipt"] = None
        try:
            listing_id = save_listing(data, 0)
        except Exception:
            logger.exception("Bepul e'lonni bazaga saqlashda xatolik")
            await context.bot.send_message(update.effective_chat.id, "\u26a0\ufe0f Texnik xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
            context.user_data.clear()
            return ConversationHandler.END

        admin_notified = False
        try:
            admin_notified = await submit_listing_to_admin(context, listing_id, data, 0)
        except Exception:
            logger.exception("Bepul e'lonni adminga yuborishda xatolik")

        text = (
            f"\U0001F4E8 E'loningiz (#{listing_id}) admin ko'rib chiqishi uchun yuborildi (BEPUL tarif \u2014 chek talab qilinmadi).\n"
            f"Tasdiqlangach avtomatik ravishda kanalga joylanadi."
            if admin_notified else
            f"\U0001F4E8 E'loningiz (#{listing_id}) qabul qilindi va saqlandi. Admin tez orada ko'rib chiqadi."
        )
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=main_menu_keyboard(user.id))
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data["listing_price_charged"] = price

    # KARTA RAQAMI FAQAT SHU YERDA (haqiqiy to'lov bosqichida) ko'rsatiladi.
    text = f"E'loningizni joylashtirish uchun to'lov qilishingiz kerak.{note}\n\n" + card_html(price, purpose="E'lon narxi")
    keyboard = card_payment_keyboard()
    await context.bot.send_message(update.effective_chat.id, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    return TOLOV_CHEK


async def tolov_chek_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        if await try_escape_to_menu(update, context):
            return ConversationHandler.END
        await update.message.reply_text("\u26a0\ufe0f Iltimos, to'lov chekining skrinshotini RASM sifatida yuboring.")
        return TOLOV_CHEK

    data = context.user_data
    user = update.effective_user
    data["user_id"] = user.id
    data["username"] = user.username
    data["full_name"] = user.full_name
    data["sender_phone"] = None
    data["payment_receipt"] = update.message.photo[-1].file_id
    price_charged = data.get("listing_price_charged", listing_price())

    try:
        listing_id = save_listing(data, price_charged)
    except Exception:
        logger.exception("E'lonni bazaga saqlashda xatolik")
        await update.message.reply_text("\u26a0\ufe0f Texnik xatolik yuz berdi. Iltimos, chek rasmni QAYTA yuboring \u2014 ma'lumotlaringiz yo'qolmagan.")
        return TOLOV_CHEK

    admin_notified = False
    try:
        admin_notified = await submit_listing_to_admin(context, listing_id, data, price_charged)
    except Exception:
        logger.exception("Adminga umumiy xabar yuborish jarayonida kutilmagan xatolik")

    if admin_notified:
        text = f"\U0001F4E8 E'loningiz (#{listing_id}) va to'lov chekingiz admin ko'rib chiqishi uchun yuborildi.\nTasdiqlangach avtomatik ravishda kanalga joylanadi. Iltimos, kuting."
    else:
        text = (
            f"\U0001F4E8 E'loningiz (#{listing_id}) qabul qilindi va saqlandi.\n"
            f"Adminga bildirishnoma yuborishda vaqtinchalik tarmoq muammosi bo'ldi, lekin xavotir olmang \u2014 "
            f"e'loningiz yo'qolmagan, admin uni tez orada ko'rib chiqadi."
        )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard(user.id))
    context.user_data.clear()
    return ConversationHandler.END


async def submit_listing_to_admin(context: ContextTypes.DEFAULT_TYPE, listing_id: int, data: dict, price_charged: int) -> bool:
    caption = build_caption(data, context.bot.username) + f"\n\n\U0001F194 E'lon raqami: #{listing_id}"
    rasmlar = data["rasmlar"]

    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS bo'sh \u2014 moderatsiya uchun hech kimga xabar yuborilmadi!")
        return False

    blocked = get_blocked_phone(data["telefon"])
    warning = "\u26a0\ufe0f\u26a0\ufe0f <b>DIQQAT: BU RAQAM BLOKLANGAN RO'YXATDA!</b> \u26a0\ufe0f\u26a0\ufe0f\n\n" if blocked else ""

    sender_line = (
        f"{warning}"
        f"\U0001F464 Yuboruvchi: {esc(data.get('full_name'))} (@{esc(data.get('username')) or 'yo`q'})\n"
        f"\U0001F4B0 To'lov qilingan summa: {price_charged:,} so'm\n"
        f"\U0001F194 E'lon: #{listing_id}\n\n"
        + ("\U0001F4B3 To'lov cheki yuqorida \u2191 \u2014 tekshirib, qaror qabul qiling:" if data.get("payment_receipt") else "\U0001F193 Bu e'lon BEPUL tarifda yuborilgan (chek talab qilinmagan) \u2014 tekshirib, qaror qabul qiling:")
    )
    admin_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u2705 Tasdiqlash", callback_data=f"admin_approve_listing_{listing_id}"),
          InlineKeyboardButton("\u274c Rad etish", callback_data=f"admin_reject_listing_{listing_id}")]]
    )

    any_success = False
    for admin_id in ADMIN_IDS:
        try:
            await send_photos(context, admin_id, rasmlar)
            await send_with_retry(context.bot.send_message, admin_id, caption, parse_mode=ParseMode.HTML)
            if data.get("payment_receipt"):
                await send_with_retry(
                    context.bot.send_photo, admin_id, data["payment_receipt"],
                    caption=sender_line, parse_mode=ParseMode.HTML, reply_markup=admin_keyboard,
                )
            else:
                await send_with_retry(context.bot.send_message, admin_id, sender_line, parse_mode=ParseMode.HTML, reply_markup=admin_keyboard)
            any_success = True
        except Exception:
            logger.exception("Adminga (%s) xabar yuborishda xatolik", admin_id)

    return any_success


async def show_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    listings = get_pending_listings()
    subs = get_pending_subscriptions()
    total_l, total_s = count_pending_listings(), count_pending_subscriptions()

    if not listings and not subs:
        await update.message.reply_text("\u2705 Hozircha kutilayotgan e'lon yoki obuna so'rovi yo'q.")
        return

    extra = ""
    if total_l > len(listings) or total_s > len(subs):
        extra = f"\n\n<i>(Faqat eng birinchi {PAGE_SIZE} tasi ko'rsatilmoqda, jami {total_l} ta e'lon va {total_s} ta obuna kutilmoqda \u2014 avval shularni ko'rib chiqing.)</i>"

    await update.message.reply_text(
        f"\U0001F553 Kutilayotganlar: {len(listings)} ta e'lon, {len(subs)} ta obuna so'rovi.{extra}\n"
        "Har birini alohida, tasdiqlash/rad etish tugmalari bilan yuboraman \U0001F447",
        parse_mode=ParseMode.HTML,
    )

    for listing in listings:
        await resend_listing_for_review(context, chat_id, listing)
    for sub in subs:
        await resend_subscription_for_review(context, chat_id, sub)


async def resend_listing_for_review(context: ContextTypes.DEFAULT_TYPE, admin_chat_id: int, listing: dict) -> None:
    caption = build_caption(listing, context.bot.username) + f"\n\n\U0001F194 E'lon raqami: #{listing['id']}"
    await send_photos(context, admin_chat_id, listing["photos"])
    try:
        await send_with_retry(context.bot.send_message, admin_chat_id, caption, parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("Kutayotgan e'lon matnini yuborishda xatolik")

    blocked = get_blocked_phone(listing["telefon"])
    warning = "\u26a0\ufe0f\u26a0\ufe0f <b>DIQQAT: BU RAQAM BLOKLANGAN RO'YXATDA!</b> \u26a0\ufe0f\u26a0\ufe0f\n\n" if blocked else ""
    sender_line = (
        f"{warning}"
        f"\U0001F464 Yuboruvchi: {esc(listing.get('full_name'))} (@{esc(listing.get('username')) or 'yo`q'})\n"
        f"\U0001F4B0 To'lov qilingan summa: {(listing.get('price_charged') or 0):,} so'm\n"
        f"\U0001F194 E'lon: #{listing['id']}\n\n"
        "\U0001F4B3 To'lov cheki (agar mavjud bo'lsa) yuqorida \u2191 \u2014 tekshirib, qaror qabul qiling:"
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u2705 Tasdiqlash", callback_data=f"admin_approve_listing_{listing['id']}"),
          InlineKeyboardButton("\u274c Rad etish", callback_data=f"admin_reject_listing_{listing['id']}")]]
    )
    try:
        if listing.get("payment_receipt"):
            await send_with_retry(context.bot.send_photo, admin_chat_id, listing["payment_receipt"], caption=sender_line, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        else:
            await send_with_retry(context.bot.send_message, admin_chat_id, sender_line, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception:
        logger.exception("Kutayotgan e'lon uchun tugmali xabarni yuborishda xatolik")


async def resend_subscription_for_review(context: ContextTypes.DEFAULT_TYPE, admin_chat_id: int, sub: dict) -> None:
    db_user = get_user(sub["user_id"]) or {}
    caption = (
        f"\U0001F4B3 <b>Obuna so'rovi</b> #{sub['id']}\n\n"
        f"\U0001F464 {esc(db_user.get('full_name'))} (@{esc(db_user.get('username')) or 'yo`q'})\n"
        f"\U0001F194 user_id: {sub['user_id']}\n"
        f"\U0001F4B0 Summasi: {(sub.get('price_charged') or 0):,} so'm"
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u2705 Tasdiqlash", callback_data=f"admin_approve_sub_{sub['id']}"),
          InlineKeyboardButton("\u274c Rad etish", callback_data=f"admin_reject_sub_{sub['id']}")],
         [profile_link_button(sub["user_id"])]]
    )
    keyboard_fallback = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u2705 Tasdiqlash", callback_data=f"admin_approve_sub_{sub['id']}"),
          InlineKeyboardButton("\u274c Rad etish", callback_data=f"admin_reject_sub_{sub['id']}")]]
    )
    try:
        if sub.get("receipt_photo"):
            await send_with_privacy_fallback(
                context.bot.send_photo, admin_chat_id, sub["receipt_photo"], caption=caption, parse_mode=ParseMode.HTML,
                full_markup=keyboard, fallback_markup=keyboard_fallback,
            )
        else:
            await send_with_privacy_fallback(
                context.bot.send_message, admin_chat_id, caption, parse_mode=ParseMode.HTML,
                full_markup=keyboard, fallback_markup=keyboard_fallback,
            )
    except Exception:
        logger.exception("Kutayotgan obuna so'rovini yuborishda xatolik")


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
    caption = (
        f"\U0001F4B3 <b>Yangi obuna so'rovi</b> #{sub_id}\n\n"
        f"\U0001F464 {esc(user.full_name)} (@{esc(user.username) or 'yo`q'})\n"
        f"\U0001F194 user_id: {user.id}\n"
        f"\U0001F4B0 Summasi: {price:,} so'm"
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


# ============================= RAQAMNI TEKSHIRISH (hammaga) =============================

async def check_phone_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\u274c Bekor qilish", callback_data="nav_cancel")]])
    await update.message.reply_text(
        "\U0001F50D Tekshirmoqchi bo'lgan telefon raqamini yozing (+998...):", reply_markup=keyboard
    )
    return CHECK_PHONE_WAIT


async def check_phone_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Bekor qilindi.")
    return ConversationHandler.END


async def check_phone_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    phone = normalize_phone(raw)
    if not phone:
        await update.message.reply_text("\u26a0\ufe0f Raqam formati noto'g'ri. Masalan: +998901234567. Qaytadan yozing:")
        return CHECK_PHONE_WAIT

    blocked = get_blocked_phone(phone)
    admin = is_admin(update.effective_user.id)
    log_phone_check_use(update.effective_user.id)
    if blocked:
        await update.message.reply_text(
            f"\u26a0\ufe0f <b>Ehtiyot bo'ling!</b>\n\n"
            f"<code>{esc(phone)}</code> raqami bo'yicha oldin shikoyat qayd etilgan.\n"
            f"Iltimos, bu raqam bilan bog'liq shaxsga ehtiyotkorlik bilan yondashing.",
            parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(update.effective_user.id),
        )
    else:
        await update.message.reply_text(
            f"\u2705 <code>{esc(phone)}</code> raqami bo'yicha hech qanday shikoyat qayd etilmagan.",
            parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(update.effective_user.id),
        )
    return ConversationHandler.END


# ============================= E'LON USTIDAN SHIKOYAT (KANAL POSTIDAN) =============================

MAX_REPORTS_PER_DAY = 5

REPORT_REASONS = {
    "rented": "\U0001F3E0 Uy topshirilgan ekan",
    "fake": "\u274c Soxta e'lon (mavjud emas)",
    "noresponse": "\U0001F4F5 Aloqa yo'q / Javob bermayapti",
    "fraud": "\u26a0\ufe0f Firibgarlik shubhali",
}


async def show_complain_menu_core(context: ContextTypes.DEFAULT_TYPE, user_id: int, listing_id: int) -> None:
    listing = get_listing(listing_id)
    if not listing or listing["status"] != "approved":
        await context.bot.send_message(user_id, "\u26a0\ufe0f Bu e'lon topilmadi.", reply_markup=main_menu_keyboard(user_id))
        return
    if listing.get("expired"):
        await context.bot.send_message(user_id, "\u2139\ufe0f Bu e'lon allaqachon \u00abtopshirilgan\u00bb deb belgilangan.", reply_markup=main_menu_keyboard(user_id))
        return
    if has_user_reported(listing_id, user_id):
        await context.bot.send_message(user_id, "\u2139\ufe0f Siz bu e'lon haqida allaqachon xabar bergansiz. Rahmat!", reply_markup=main_menu_keyboard(user_id))
        return
    if count_user_reports_today(user_id) >= MAX_REPORTS_PER_DAY:
        await context.bot.send_message(user_id, f"\u26a0\ufe0f Siz bugun uchun ruxsat etilgan {MAX_REPORTS_PER_DAY} ta shikoyat chegarasiga yetdingiz.", reply_markup=main_menu_keyboard(user_id))
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(REPORT_REASONS["rented"], callback_data=f"rpt_rented_{listing_id}")],
        [InlineKeyboardButton(REPORT_REASONS["fake"], callback_data=f"rpt_fake_{listing_id}")],
        [InlineKeyboardButton(REPORT_REASONS["noresponse"], callback_data=f"rpt_noresponse_{listing_id}")],
        [InlineKeyboardButton(REPORT_REASONS["fraud"], callback_data=f"rpt_fraud_{listing_id}")],
        [InlineKeyboardButton("\u274c Bekor qilish", callback_data=f"rpt_cancel_{listing_id}")],
    ])
    await context.bot.send_message(
        user_id,
        "\U0001F6A9 <b>E'lon bo'yicha shikoyat</b>\n\nIltimos, e'lon ustidan shikoyat sababini tanlang:",
        parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )


async def show_complain_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, listing_id: int):
    """/start orqali (masalan eski chuqur-havola) chaqirilganda ishlatiladi."""
    await show_complain_menu_core(context, update.effective_user.id, listing_id)


async def channel_complain_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanal postidagi \"Etiroz\" tugmasi - CALLBACK orqali, chuqur-havola
    muammosidan xoli, har doim ishlaydi."""
    query = update.callback_query
    listing_id = int(query.data.rsplit("_", 1)[1])
    try:
        await show_complain_menu_core(context, query.from_user.id, listing_id)
        await query.answer(url=f"https://t.me/{context.bot.username}")
    except Exception:
        try:
            await query.answer(url=f"https://t.me/{context.bot.username}?start=complain_{listing_id}")
        except Exception:
            logger.exception("Kanal orqali shikoyat menyusini ochishda xatolik")


async def complain_reason_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, reason, listing_id = query.data.split("_", 2)
    listing_id = int(listing_id)
    user_id = query.from_user.id

    if reason == "cancel":
        await query.edit_message_text("Bekor qilindi.")
        return

    listing = get_listing(listing_id)
    if not listing or listing["status"] != "approved" or listing.get("expired"):
        await query.edit_message_text("\u2139\ufe0f Bu e'lon endi faol emas.")
        return
    if has_user_reported(listing_id, user_id):
        await query.edit_message_text("\u2139\ufe0f Siz bu e'lon haqida allaqachon xabar bergansiz. Rahmat!")
        return
    if count_user_reports_today(user_id) >= MAX_REPORTS_PER_DAY:
        await query.edit_message_text(f"\u26a0\ufe0f Siz bugun uchun ruxsat etilgan {MAX_REPORTS_PER_DAY} ta shikoyat chegarasiga yetdingiz.")
        return

    save_report(listing_id, user_id, reason)
    addr = (listing.get("manzil") or (listing.get("raw_text") or "")[:40]).strip()
    channel_link = f"https://t.me/{CHANNEL_USERNAME}/{listing['channel_msg_id']}" if CHANNEL_USERNAME and listing.get("channel_msg_id") else None
    link_row = [InlineKeyboardButton("\U0001F440 Kanalda ko'rish", url=channel_link)] if channel_link else []

    if reason == "rented":
        await query.edit_message_text("\u2705 Rahmat! Tez orada tekshirib, e'lonni yopamiz.")
        rows = [[InlineKeyboardButton("\u2705 Ha, topshirilgan deb belgilash", callback_data=f"staleconfirm_{listing_id}"),
                 InlineKeyboardButton("\u27a1\ufe0f E'tiborsiz qoldirish", callback_data=f"staleignore_{listing_id}")]]
        if link_row:
            rows.append(link_row)
        staff_text = f"\U0001F3E0 E'lon #{listing_id} (\"{esc(addr)}\") \u2014 mijoz uy egasi bilan gaplashib, <b>uy topshirilgan</b> deb xabar berdi."
        staff_kb = InlineKeyboardMarkup(rows)

    elif reason == "fake":
        await query.edit_message_text("\u2705 Rahmat, tekshiramiz.")
        rows = [[InlineKeyboardButton("\u2705 Band deb belgilash", callback_data=f"staleconfirm_{listing_id}"),
                 InlineKeyboardButton("\u27a1\ufe0f E'tiborsiz qoldirish", callback_data=f"staleignore_{listing_id}")]]
        if link_row:
            rows.append(link_row)
        staff_text = f"\U0001F6A9 E'lon #{listing_id} (\"{esc(addr)}\") \u2014 <b>Soxta e'lon (mavjud emas)</b> deb xabar berildi."
        staff_kb = InlineKeyboardMarkup(rows)

    elif reason == "noresponse":
        await query.edit_message_text("\u2705 Rahmat, uy egasiga eslatib qo'yamiz.")
        try:
            await context.bot.send_message(
                listing["user_id"],
                f"\U0001F514 Ijarachilar sizga bog'lanishga harakat qilishmoqda, lekin javob topa olishmayapti.\n\n"
                f"E'loningiz (#{listing_id}): iltimos, tekshirib ko'ring va javob bering!",
            )
        except Exception:
            logger.exception("Egasiga eslatma yuborib bo'lmadi")
        rows = [[InlineKeyboardButton("\U0001F6AB Baribir band deb belgilash", callback_data=f"staleconfirm_{listing_id}"),
                 InlineKeyboardButton("\u27a1\ufe0f E'tiborsiz qoldirish", callback_data=f"staleignore_{listing_id}")]]
        if link_row:
            rows.append(link_row)
        staff_text = (
            f"\U0001F6A9 E'lon #{listing_id} (\"{esc(addr)}\") \u2014 <b>Aloqa yo'q / Javob bermayapti</b>.\n"
            f"Egasiga avtomatik eslatma yuborildi."
        )
        staff_kb = InlineKeyboardMarkup(rows)

    else:  # fraud
        await query.edit_message_text("\u26a0\ufe0f Xabaringiz uchun rahmat, tezkor ko'rib chiqamiz.")
        rows = [[InlineKeyboardButton("\U0001F6AB Raqamni bloklash + olib tashlash", callback_data=f"fraudblock_{listing_id}")],
                [InlineKeyboardButton("\U0001F6A9 Faqat olib tashlash", callback_data=f"staleconfirm_{listing_id}"),
                 InlineKeyboardButton("\u27a1\ufe0f E'tiborsiz qoldirish", callback_data=f"staleignore_{listing_id}")]]
        if link_row:
            rows.append(link_row)
        staff_text = f"\u26a0\ufe0f\u26a0\ufe0f <b>SHOSHILINCH: Firibgarlik shubhasi!</b>\u26a0\ufe0f\u26a0\ufe0f\n\nE'lon #{listing_id} (\"{esc(addr)}\")"
        staff_kb = InlineKeyboardMarkup(rows)

    for staff_id in all_staff_ids():
        try:
            await context.bot.send_message(staff_id, staff_text, parse_mode=ParseMode.HTML, reply_markup=staff_kb)
        except Exception:
            logger.exception("Staff'ga shikoyat xabarini yuborib bo'lmadi")


async def expire_listing(context: ContextTypes.DEFAULT_TYPE, listing_id: int, notify_owner: bool = False) -> None:
    """E'lonni \"topshirilgan\" deb belgilaydi. KANALDAGI POST HECH QACHON
    o'chirilmaydi/tahrirlanmaydi - faqat bazada belgi qo'yiladi. \"Uy egasi
    raqami\" tugmasi bosilganda shu belgi tekshiriladi."""
    mark_listing_expired(listing_id)
    if notify_owner:
        listing = get_listing(listing_id)
        if listing:
            try:
                await context.bot.send_message(listing["user_id"], f"\u2139\ufe0f E'loningiz (#{listing_id}) \u00abtopshirilgan\u00bb deb belgilandi.")
            except Exception:
                logger.exception("Egasiga xabar yuborib bo'lmadi")


async def selfexpire_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    listing_id = int(query.data.rsplit("_", 1)[1])
    listing = get_listing(listing_id)
    if not listing or listing["user_id"] != query.from_user.id:
        await query.answer("Bu sizning e'loningiz emas.", show_alert=True)
        return
    await expire_listing(context, listing_id)
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"\u2705 E'lon #{listing_id} \u00abtopshirilgan\u00bb deb belgilandi.")


async def stillavail_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, action, listing_id = query.data.split("_", 2)
    listing_id = int(listing_id)
    if action == "yes":
        confirm_listing_still_available(listing_id)
        await query.edit_message_text("\u2705 Rahmat! E'loningiz faol deb belgilandi.")
    else:
        await expire_listing(context, listing_id)
        await query.edit_message_text("\U0001F4CB Tushunarli, e'loningiz \u00abtopshirilgan\u00bb deb belgilandi.")


async def job_stale_check(context: ContextTypes.DEFAULT_TYPE):
    for listing in get_stale_listings(STALE_CHECK_DAYS):
        if is_staff(listing["user_id"]):
            # Admin/moderator o'zi joylagan (odatda boshqa birov uchun, Tezkor
            # e'lon orqali) e'lonlarga bu savol yuborilmaydi - faqat HAQIQIY
            # uy egalariga (oddiy foydalanuvchilarga) yuboriladi.
            continue
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("\u2705 Ha, hali bo'sh", callback_data=f"stillavail_yes_{listing['id']}"),
              InlineKeyboardButton("\u274c Yo'q, band bo'ldi", callback_data=f"stillavail_no_{listing['id']}")]]
        )
        try:
            await context.bot.send_message(
                listing["user_id"],
                f"\U0001F3E0 <b>{esc(listing.get('manzil') or 'Sizning eloningiz')}</b> uyi hali ham bo'shmi?\n\n"
                f"Agar javob bermasangiz, bir necha kundan keyin yana so'raymiz.",
                parse_mode=ParseMode.HTML, reply_markup=keyboard,
            )
        except Exception:
            logger.exception("Eskirgan e'lon so'rovini yuborib bo'lmadi: listing_id=%s", listing["id"])


async def post_block_announcement(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Raqam bloklanganda kanalga avtomatik, qisqa, faollikka chaqiruvchi post
    joylaydi - shaffoflik va foydalanuvchi ishtirokini oshirish uchun."""
    if not CHANNEL_ID:
        return
    total_blocked = count_blocked_phones()
    text = (
        "\U0001F6A8 <b>Yana bir firibgar bloklandi!</b>\n\n"
        "Biz sizni maklersiz, xavfsiz uy topishga yordam berish uchun kurashamiz \u2014 "
        "bunda sizning faolligingiz ham muhim.\n\n"
        "\U0001F449 Agar e'lon egasi pullik kanal, makler haqqi yoki oldindan pul so'rasa \u2014 "
        "o'sha e'lon ustidan <b>Etiroz</b> yuboring. Biz tekshirib, firibgarni bloklaymiz.\n\n"
        f"\U0001F4CA Jami bloklangan raqamlar: <b>{total_blocked} ta</b>"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F50D Raqamni tekshirish", callback_data="chcheckphone")]])
    try:
        await context.bot.send_message(CHANNEL_ID, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception:
        logger.exception("Bloklash e'lonini kanalga yuborib bo'lmadi")


async def channel_checkphone_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanaldagi bloklash-e'lonidagi \"Raqamni tekshirish\" tugmasi - CALLBACK
    orqali, ishonchli ishlaydigan mos-tugma usuli bilan."""
    query = update.callback_query
    user = query.from_user
    force_reset_conversation(context, "check_phone_conv", user.id)
    try:
        await context.bot.send_message(
            user.id, "\U0001F50D Raqam tekshirmoqchimisiz?\n\nPastdagi tugmani bosing \U0001F447",
            reply_markup=ReplyKeyboardMarkup([[BTN_CHECK_PHONE]], resize_keyboard=True),
        )
        await query.answer(url=f"https://t.me/{context.bot.username}")
    except Exception:
        try:
            await query.answer(url=f"https://t.me/{context.bot.username}?start=checkphone")
        except Exception:
            logger.exception("Kanal orqali raqam-tekshirish oynasini ochishda xatolik")


async def job_weekly_top_location(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Haftada bir marta (dushanba), eng ko'p odam kutayotgan hudud haqida
    kanalga tashviqiy post joylanadi - uy egalarini o'sha yerda tezroq
    joylashga undash uchun."""
    if not CHANNEL_ID:
        return
    groups = group_location_alerts()
    if not groups:
        return
    top_name, top_count = groups[0]
    if top_count < 3:
        # Juda kam sonli hudud haqida post qilish ma'nosiz - signal kuchsiz.
        return
    text = (
        f"\U0001F4C8 <b>Bu hafta eng ko'p qidirilgan hudud: {esc(top_name)}</b>\n\n"
        f"{top_count} kishi shu hududdan uy kutmoqda!\n\n"
        f"Agar sizda shu yerda bo'sh xonadon bo'lsa \u2014 hoziroq joylang, tezroq ijaraga beriladi \U0001F447"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F4DD E'lon berish", callback_data="chelon")]])
    try:
        await context.bot.send_message(CHANNEL_ID, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception:
        logger.exception("Haftalik hudud postini yuborib bo'lmadi")


EMPTY_REGION_MIN_WAITING = 10
EMPTY_REGION_CHECK_DAYS = 10


async def job_empty_region_alert(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Agar biror hududda ko'p odam kutayotgan bo'lsa, lekin so'nggi
    EMPTY_REGION_CHECK_DAYS kun ichida shu hududga mos yangi e'lon
    kelmagan bo'lsa - staff'ga ogohlantirish yuboradi (kontent yig'ish
    strategiyasini boshqarish uchun)."""
    groups = group_location_alerts()
    if not groups:
        return
    since = (datetime.now() - timedelta(days=EMPTY_REGION_CHECK_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    recent_listings = conn.execute("SELECT manzil, moljal, raw_text FROM listings WHERE created_at >= ?", (since,)).fetchall()
    conn.close()

    empty = []
    for name, count in groups:
        if count < EMPTY_REGION_MIN_WAITING:
            continue
        matched = False
        for row in recent_listings:
            haystack = " ".join([row["manzil"] or "", row["moljal"] or "", row["raw_text"] or ""])
            if location_matches(name, haystack):
                matched = True
                break
        if not matched:
            empty.append((name, count))

    if not empty:
        return
    lines = ["\u26a0\ufe0f <b>Bo'sh hudud signali</b>\n"]
    for name, count in empty:
        lines.append(f"\U0001F4CD {esc(name)} \u2014 {count} kishi kutmoqda, so'nggi {EMPTY_REGION_CHECK_DAYS} kunda mos yangi e'lon yo'q!")
    text = "\n".join(lines)
    for staff_id in all_staff_ids():
        try:
            await context.bot.send_message(staff_id, text, parse_mode=ParseMode.HTML)
        except Exception:
            logger.exception("Bo'sh hudud signalini yuborib bo'lmadi: staff_id=%s", staff_id)


async def job_repost_paid_listings(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pullik e'lonlar (price_charged > 0) e'lon egasi \u00abtopshirildi\u00bb deb
    belgilamaguncha, har 3 soatda kanalga QAYTA joylanadi (bepul e'lonlar
    faqat bir marta joylanadi, o'zgarishsiz qoladi)."""
    if not CHANNEL_ID:
        return
    conn = db()
    rows = conn.execute(
        "SELECT * FROM listings WHERE status = 'approved' AND COALESCE(expired,0) = 0 AND COALESCE(price_charged,0) > 0"
    ).fetchall()
    conn.close()
    for row in rows:
        listing = dict(row)
        listing["photos"] = json.loads(listing["photos"] or "[]")
        try:
            new_msg_id = await send_listing_to_channel(context, listing)
            if new_msg_id:
                update_listing_status(listing["id"], "approved", channel_msg_id=new_msg_id)
                logger.info("Pullik e'lon qayta joylandi: listing_id=%s", listing["id"])
        except Exception:
            logger.exception("Pullik e'lonni qayta joylashda xatolik: listing_id=%s", listing["id"])


def mark_channel_post_fixed(post_id: int) -> None:
    conn = db()
    conn.execute("UPDATE channel_posts SET buttons_fixed = 1 WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()


async def fixbuttons_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Og'ir ish - FONDA (job_queue orqali) ishlaydi, botning boshqa
    foydalanuvchilarga xizmat ko'rsatishini TO'XTATMAYDI. Endi \"channel_posts\"
    jadvali orqali HAR BIR tarixiy joylashni (pullik e'lonning barcha qayta
    joylanishlari ham) tekshiradi, faqat eng so'nggisini emas. Allaqachon
    tekshirilganlarni QAYTA tekshirmaydi - jarayon uzilib qolsa, qayta ishga
    tushirilganda faqat qolganlarini davom ettiradi."""
    admin_id = context.job.data["admin_id"]

    # Eski (bu kuzatuv jadvali qo'shilishidan OLDIN joylangan) e'lonlar uchun -
    # ularning bazadagi so'nggi ma'lum post-raqamini shu jadvalga "moslashtirib" qo'yamiz.
    conn = db()
    conn.execute(
        """INSERT INTO channel_posts (listing_id, message_id, posted_at, buttons_fixed)
           SELECT id, channel_msg_id, created_at, 0 FROM listings
           WHERE channel_msg_id IS NOT NULL AND id NOT IN (SELECT listing_id FROM channel_posts)"""
    )
    conn.commit()
    conn.close()

    conn = db()
    rows = conn.execute(
        """SELECT cp.id AS post_id, cp.listing_id, cp.message_id, l.latitude, l.longitude
           FROM channel_posts cp LEFT JOIN listings l ON l.id = cp.listing_id
           WHERE COALESCE(cp.buttons_fixed,0) = 0"""
    ).fetchall()
    conn.close()

    updated, already_ok, failed = 0, 0, 0
    sample_errors = []
    for row in rows:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=CHANNEL_ID, message_id=row["message_id"],
                reply_markup=channel_keyboard(row["listing_id"], context.bot.username, row["latitude"], row["longitude"]),
            )
            updated += 1
        except Exception as e:
            if "not modified" in str(e).lower():
                # Bu XATO EMAS - bu post tugmasi ALLAQACHON yangi turda.
                already_ok += 1
            else:
                failed += 1
                if len(sample_errors) < 5:
                    sample_errors.append(f"#{row['listing_id']}: {e}")
                logger.warning("Tugma yangilashda xato: listing_id=%s, msg_id=%s, xato=%s", row["listing_id"], row["message_id"], e)
        mark_channel_post_fixed(row["post_id"])
        await asyncio.sleep(0.15)  # Telegram tezlik chegarasidan saqlanish uchun

    error_block = ("\n\n\U0001F50D Namuna xatolar:\n" + "\n".join(sample_errors)) if sample_errors else ""
    try:
        await context.bot.send_message(
            admin_id,
            f"\u2705 Tayyor!\n\U0001F195 Yangi yangilandi: {updated} ta\n\u2705 Allaqachon yangi edi: {already_ok} ta\n\u26a0\ufe0f Haqiqiy xato: {failed} ta{error_block}",
        )
    except Exception:
        logger.exception("/fixbuttons natijasini yuborib bo'lmadi")


async def setcategory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin buyrug'i: /setcategory <elon_id> <toifa>
    toifa: egadan, tasdiqlangan, subarenda, premium"""
    if not is_admin(update.effective_user.id):
        return
    valid = {"egadan", "tasdiqlangan", "subarenda", "premium"}
    args = context.args
    if len(args) != 2 or not args[0].isdigit() or args[1] not in valid:
        await update.message.reply_text(
            "Foydalanish: <code>/setcategory ID toifa</code>\n\n"
            "Toifalar: <code>egadan</code>, <code>tasdiqlangan</code>, <code>subarenda</code>, <code>premium</code>\n\n"
            "Masalan: <code>/setcategory 42 tasdiqlangan</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    listing_id, category = int(args[0]), args[1]
    listing = get_listing(listing_id)
    if not listing:
        await update.message.reply_text(f"\u26a0\ufe0f #{listing_id} raqamli e'lon topilmadi.")
        return
    conn = db()
    conn.execute("UPDATE listings SET category = ? WHERE id = ?", (category, listing_id))
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"\u2705 #{listing_id} e'loni endi <b>{category}</b> toifasiga o'tkazildi.\n\n"
        f"Manzil: {esc(listing.get('manzil') or '-')}",
        parse_mode=ParseMode.HTML,
    )


async def fixbuttons_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bir martalik admin buyrug'i (/fixbuttons) - kanalda AVVALDAN turgan
    (eski, url-havolali tugmalar bilan joylangan) barcha faol e'lonlarning
    tugmalarini yangi, ishonchli (callback) tugmalarga almashtiradi.
    Ish og'ir bo'lgani uchun FONDA (job_queue) ishga tushiriladi - shuning
    uchun bot shu vaqt ichida boshqa hech kimga xizmat ko'rsatishni
    TO'XTATMAYDI."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    if not CHANNEL_ID:
        await update.message.reply_text("\u26a0\ufe0f CHANNEL_ID sozlanmagan.")
        return
    if not context.job_queue:
        await update.message.reply_text("\u26a0\ufe0f JobQueue mavjud emas, bu buyruqni ishlata olmayman.")
        return

    context.job_queue.run_once(fixbuttons_job, 0, data={"admin_id": user_id})
    await update.message.reply_text(
        "\U0001F504 Fonda ishga tushdi \u2014 bot bu vaqtda BEMALOL ishlayveradi, "
        "boshqa foydalanuvchilarga xalaqit bermaydi. Tayyor bo'lgach, sizga xabar beraman."
    )


async def job_promote_limit(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har 4 soatda kanalga Limit haqida qisqa, tushunarli tanishtiruv posti
    joylanadi - real obunachilar soni bilan, to'g'ridan-to'g'ri sotib olish
    tugmasi bilan."""
    if not CHANNEL_ID:
        return
    price = subscription_price()
    days = subscription_days()
    active_count = count_active_subscribers()
    social_proof_line = f"\U0001F465 Hozir <b>{active_count}+ kishi</b> shu limitdan foydalanmoqda\n\n" if active_count >= 10 else "\n"
    text = (
        "\U0001F513 <b>Limit nima uchun kerak?</b>\n\n"
        "Kanaldagi e'lonlarda uy egasi raqami yashiringan \u2014 uni ko'rish uchun "
        "<b>Limit</b> kerak bo'ladi.\n\n"
        f"\U0001F4B3 {days} kun \u2014 <b>{price:,} so'm</b>\n"
        f"\u2705 Shu muddat davomida BARCHA e'lonlarda raqamlarni cheklovsiz ko'rasiz\n\n"
        f"{social_proof_line}"
        "Maklersiz, to'g'ridan-to'g'ri uy egasi bilan bog'laning \U0001F447"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"\U0001F513 {days} kunlik limit olish", callback_data="chbuysub")]])
    try:
        await context.bot.send_message(CHANNEL_ID, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception:
        logger.exception("Limit reklama postini kanalga yuborib bo'lmadi")


async def channel_buysub_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanaldagi \"Limit sotib olish\" reklama postidagi tugma - CALLBACK
    orqali. Bu ko'p bosqichli (chek kutish) jarayon bo'lgani uchun, ishonchli
    ishlashi uchun mos tugma orqali davom ettiramiz."""
    query = update.callback_query
    user = query.from_user
    force_reset_conversation(context, "sub_conv", user.id)
    try:
        await context.bot.send_message(
            user.id, "\U0001F513 Limit sotib olmoqchimisiz?\n\nPastdagi tugmani bosing \U0001F447",
            reply_markup=ReplyKeyboardMarkup([[BTN_SUBSCRIPTION]], resize_keyboard=True),
        )
        await query.answer(url=f"https://t.me/{context.bot.username}")
    except Exception:
        try:
            await query.answer(url=f"https://t.me/{context.bot.username}?start=buysub")
        except Exception:
            logger.exception("Kanal orqali limit-sotib-olish oynasini ochishda xatolik")


async def staleconfirm_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    listing_id = int(query.data.rsplit("_", 1)[1])
    await expire_listing(context, listing_id, notify_owner=True)
    await query.edit_message_text("\u2705 E'lon \u00abtopshirilgan\u00bb deb belgilandi.")


async def fraudblock_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    listing_id = int(query.data.rsplit("_", 1)[1])
    listing = get_listing(listing_id)
    if not listing:
        await query.edit_message_text("\u26a0\ufe0f E'lon topilmadi.")
        return
    block_phone(listing["telefon"], f"E'lon #{listing_id} firibgarlik shikoyati sababli", query.from_user.id)
    await expire_listing(context, listing_id, notify_owner=True)
    await post_block_announcement(context)
    await query.edit_message_text(f"\U0001F6AB <code>{esc(listing['telefon'])}</code> bloklandi va e'lon \u00abtopshirilgan\u00bb deb belgilandi.", parse_mode=ParseMode.HTML)


async def staleignore_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)


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


# ============================= XATOLIKLAR =============================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Xatolik yuz berdi", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("\u26a0\ufe0f Kutilmagan xatolik yuz berdi. Iltimos, \u00abBekor qilish\u00bb tugmasini bosib qaytadan urinib ko'ring.")
        except Exception:
            pass


# ============================= ILOVANI ISHGA TUSHIRISH =============================

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi. .env faylida BOT_TOKEN o'rnating.")
    if CHANNEL_ID is None:
        raise RuntimeError("CHANNEL_ID topilmadi. .env faylida CHANNEL_ID o'rnating.")

    init_db()
    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    app = (
        Application.builder().token(TOKEN).persistence(persistence)
        .connect_timeout(20).read_timeout(20).write_timeout(20).pool_timeout(20)
        .build()
    )

    nav_cb = CallbackQueryHandler(nav_router, pattern="^(nav_back|nav_cancel)$")
    text_cb = MessageHandler(filters.TEXT & ~filters.COMMAND, text_step_router)

    def make_reminder(state):
        async def _h(update, context):
            return await remind_text(update, context, state)
        return _h

    def text_state(state):
        return [nav_cb, text_cb, MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(state))]

    elon_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(BTN_ELON)}$"), elon_entry),
            CommandHandler("start", elon_entry, filters=filters.Regex(r"^/start elon$")),
            CallbackQueryHandler(listing_type_chosen, pattern="^listingtype_(free|paid)$"),
        ],
        states={
            LISTING_TYPE_CHOICE: [nav_cb, CallbackQueryHandler(listing_type_chosen, pattern="^listingtype_(free|paid)$"), MessageHandler(~filters.COMMAND, make_reminder(LISTING_TYPE_CHOICE))],
            RENTAL_TYPE_CHOICE: [nav_cb, CallbackQueryHandler(rental_type_chosen, pattern="^rentaltype_(uzoq_muddat|kunlik|dacha|mehmonxona)$"), MessageHandler(~filters.COMMAND, make_reminder(RENTAL_TYPE_CHOICE))],
            MANZIL: text_state(MANZIL),
            MOLJAL: text_state(MOLJAL),
            KIMLARGA: text_state(KIMLARGA),
            XONA: text_state(XONA),
            QULAYLIK: text_state(QULAYLIK),
            NARX: text_state(NARX),
            TELEFON: text_state(TELEFON),
            LOCATION_OPTIONAL: [
                MessageHandler(filters.LOCATION, location_received),
                MessageHandler(filters.StatusUpdate.WEB_APP_DATA, location_picked_via_webapp),
                MessageHandler(filters.Regex(f"^{re.escape(BTN_SKIP_LOCATION)}$"), location_skip),
                MessageHandler(filters.Regex(f"^{re.escape(BTN_LOCATION_BACK)}$"), location_back_to_telefon),
                MessageHandler(~filters.COMMAND, location_reminder),
            ],
            RASMLAR: [CallbackQueryHandler(rasm_back_to_location, pattern="^nav_back_to_location$"), nav_cb, CallbackQueryHandler(rasm_tayyor, pattern="^rasm_tayyor$"), MessageHandler(~filters.COMMAND, rasm_qabul)],
            TASDIQLASH: [
                CallbackQueryHandler(tasdiqlash_ok, pattern="^tasdiqlash_ok$"),
                CallbackQueryHandler(tasdiqlash_nav_router, pattern="^(nav_back|nav_cancel)$"),
                MessageHandler(~filters.COMMAND, tasdiqlash_reminder),
            ],
            TOLOV_CHEK: [nav_cb, MessageHandler(~filters.COMMAND, tolov_chek_router)],
        },
        fallbacks=[nav_cb],
        name="elon_conv",
        persistent=False,
    )

    sub_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(BTN_SUBSCRIPTION)}$"), subscription_entry),
            CallbackQueryHandler(subscription_entry, pattern=r"^buy_subscription(_\d+)?$"),
            CommandHandler("start", subscription_entry, filters=filters.Regex(r"^/start buysub$")),
        ],
        states={
            SUB_WAIT_RECEIPT: [CallbackQueryHandler(sub_cancel_cb, pattern="^nav_cancel$"), MessageHandler(~filters.COMMAND, subscription_receipt)],
        },
        fallbacks=[CallbackQueryHandler(sub_cancel_cb, pattern="^nav_cancel$")],
        name="sub_conv",
        persistent=False,
    )

    check_phone_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(BTN_CHECK_PHONE)}$"), check_phone_entry),
            CommandHandler("start", check_phone_entry, filters=filters.Regex(r"^/start checkphone$")),
        ],
        states={CHECK_PHONE_WAIT: [CallbackQueryHandler(check_phone_cancel, pattern="^nav_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, check_phone_receive)]},
        fallbacks=[CallbackQueryHandler(check_phone_cancel, pattern="^nav_cancel$")],
        name="check_phone_conv",
        persistent=False,
    )

    admin_reject_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_reject_start, pattern=r"^admin_reject_(listing|sub)_\d+$")],
        states={ADMIN_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reject_reason), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(ADMIN_REASON))]},
        fallbacks=[CommandHandler("bekor", admin_reject_cancel)],
        name="admin_reject_conv",
        persistent=False,
    )

    admin_settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_setting_edit_start, pattern=r"^editset_\w+$")],
        states={ADMIN_SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_setting_value_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(ADMIN_SETTING_VALUE))]},
        fallbacks=[CommandHandler("bekor", admin_setting_cancel)],
        name="admin_settings_conv",
        persistent=False,
    )

    admin_block_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(block_new_entry, pattern="^block_new$")],
        states={
            ADMIN_BLOCK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, block_phone_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(ADMIN_BLOCK_PHONE))],
            ADMIN_BLOCK_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, block_reason_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(ADMIN_BLOCK_REASON))],
        },
        fallbacks=[CommandHandler("bekor", block_flow_cancel)],
        name="admin_block_conv",
        persistent=False,
    )

    quick_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{re.escape(BTN_QUICK)}$"), quick_entry)],
        states={
            QUICK_TEXT: [CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, quick_text_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(QUICK_TEXT))],
            QUICK_PHONE: [CallbackQueryHandler(quick_back_to_text, pattern="^quick_back_totext$"), CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, quick_phone_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(QUICK_PHONE))],
            QUICK_MANZIL: [CallbackQueryHandler(quick_back_to_phone, pattern="^quick_back_tophone$"), CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, quick_manzil_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(QUICK_MANZIL))],
            QUICK_NARX: [CallbackQueryHandler(quick_back_to_manzil, pattern="^quick_back_tomanzil$"), CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, quick_narx_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(QUICK_NARX))],
            QUICK_PHOTOS: [CallbackQueryHandler(quick_back_to_narx, pattern="^quick_back_tonarx$"), CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), CallbackQueryHandler(quick_rasm_tayyor, pattern="^quick_rasm_tayyor$"), MessageHandler(~filters.COMMAND, quick_rasm_qabul)],
            QUICK_CONFIRM: [CallbackQueryHandler(quick_back_to_photos, pattern="^quick_back_tophotos$"), CallbackQueryHandler(quick_post, pattern="^quick_post$"), CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), MessageHandler(~filters.COMMAND, quick_confirm_reminder)],
        },
        fallbacks=[CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$")],
        name="quick_conv",
        persistent=False,
    )

    mod_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(mod_add_entry, pattern="^mod_add$")],
        states={MOD_ADD_WAIT: [MessageHandler(filters.ALL & ~filters.COMMAND, mod_add_received)]},
        fallbacks=[CommandHandler("bekor", mod_add_cancel)],
        name="mod_add_conv",
        persistent=False,
    )

    admin_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_entry, pattern="^admin_add$")],
        states={ADMIN_ADD_WAIT: [MessageHandler(filters.ALL & ~filters.COMMAND, admin_add_received)]},
        fallbacks=[CommandHandler("bekor", admin_add_cancel)],
        name="admin_add_conv",
        persistent=False,
    )

    usersearch_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{re.escape(BTN_USER_SEARCH)}$") & filters.User(ADMIN_IDS), usersearch_entry)],
        states={USER_SEARCH_WAIT: [MessageHandler(filters.ALL & ~filters.COMMAND, usersearch_received)]},
        fallbacks=[CommandHandler("bekor", usersearch_cancel)],
        name="usersearch_conv",
        persistent=False,
    )

    addloc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(addloc_entry, pattern="^addloc$")],
        states={LOCATION_WAIT: [CallbackQueryHandler(addloc_cancel, pattern="^nav_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, addloc_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(LOCATION_WAIT))]},
        fallbacks=[CallbackQueryHandler(addloc_cancel, pattern="^nav_cancel$")],
        name="addloc_conv",
        persistent=False,
    )

    app.add_handler(elon_conv)
    register_conv("elon_conv", elon_conv)  # force_reset_conversation funksiyasi buni topa olishi uchun
    app.add_handler(sub_conv)
    register_conv("sub_conv", sub_conv)
    app.add_handler(check_phone_conv)
    register_conv("check_phone_conv", check_phone_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fixbuttons", fixbuttons_command))
    app.add_handler(CommandHandler("setcategory", setcategory_command))
    app.add_handler(CommandHandler("postmap", postmap_command))
    app.add_handler(admin_reject_conv)
    app.add_handler(admin_settings_conv)
    app.add_handler(admin_block_conv)
    app.add_handler(quick_conv)
    app.add_handler(mod_add_conv)
    app.add_handler(admin_add_conv)
    app.add_handler(usersearch_conv)
    app.add_handler(addloc_conv)
    app.add_handler(MessageHandler(
        filters.Regex(f"^({re.escape(BTN_LISTINGS)}|{re.escape(BTN_HELP)}|{re.escape(BTN_LOCATION_ALERT)}|{re.escape(BTN_MY_LOCATIONS)}|{re.escape(BTN_CHANNEL)}|{re.escape(BTN_STATS)}|{re.escape(BTN_SUBSCRIBERS)}|{re.escape(BTN_SETTINGS)}|{re.escape(BTN_PENDING)}|{re.escape(BTN_BLOCKED)}|{re.escape(BTN_MODERATORS)}|{re.escape(BTN_FLAGGED)}|{re.escape(BTN_LISTINGS_MAP)}|{re.escape(BTN_ADMIN_PANEL)}|{re.escape(BTN_SUBARENDA)})$"),
        text_menu_router,
    ))
    app.add_handler(CallbackQueryHandler(admin_approve, pattern=r"^admin_approve_(listing|sub)_\d+$"))
    app.add_handler(CallbackQueryHandler(subpage_router, pattern=r"^subpage_\d+$"))
    app.add_handler(CallbackQueryHandler(usercard_router, pattern=r"^usercard_\d+$"))
    app.add_handler(CallbackQueryHandler(cardcancel_router, pattern=r"^cardcancel_\d+$"))
    app.add_handler(CallbackQueryHandler(cardcancelyes_router, pattern=r"^cardcancelyes_\d+$"))
    app.add_handler(CallbackQueryHandler(cardban_router, pattern=r"^cardban_\d+$"))
    app.add_handler(CallbackQueryHandler(cardunban_router, pattern=r"^cardunban_\d+$"))
    app.add_handler(CallbackQueryHandler(flagpage_router, pattern=r"^flagpage_\d+$"))
    app.add_handler(CallbackQueryHandler(statsperiod_router, pattern=r"^statsperiod_(daily|weekly|monthly|yearly)$"))
    app.add_handler(CallbackQueryHandler(fraudban_router, pattern=r"^fraudban_(\d+|skip)$"))
    app.add_handler(CallbackQueryHandler(blockpage_router, pattern=r"^blockpage_\d+$"))
    app.add_handler(CallbackQueryHandler(unblock_router, pattern=r"^unblock_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(blockask_router, pattern=r"^blockask_(yes|no)_\d+$"))
    app.add_handler(CallbackQueryHandler(toggle_setting_router, pattern=r"^toggleset_\w+$"))
    app.add_handler(CallbackQueryHandler(mod_remove_router, pattern=r"^modremove_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_remove_router, pattern=r"^adminremove_\d+$"))
    app.add_handler(CallbackQueryHandler(stillavail_router, pattern=r"^stillavail_(yes|no)_\d+$"))
    app.add_handler(CallbackQueryHandler(complain_reason_router, pattern=r"^rpt_(rented|fake|noresponse|fraud|cancel)_\d+$"))
    app.add_handler(CallbackQueryHandler(channel_phone_button, pattern=r"^chphone_\d+$"))
    app.add_handler(CallbackQueryHandler(channel_complain_button, pattern=r"^chcomplain_\d+$"))
    app.add_handler(CallbackQueryHandler(channel_elon_button, pattern="^chelon$"))
    app.add_handler(CallbackQueryHandler(channel_buysub_button, pattern="^chbuysub$"))
    app.add_handler(CallbackQueryHandler(channel_checkphone_button, pattern="^chcheckphone$"))
    app.add_handler(CallbackQueryHandler(staleconfirm_router, pattern=r"^staleconfirm_\d+$"))
    app.add_handler(CallbackQueryHandler(staleignore_router, pattern=r"^staleignore_\d+$"))
    app.add_handler(CallbackQueryHandler(fraudblock_router, pattern=r"^fraudblock_\d+$"))
    app.add_handler(CallbackQueryHandler(selfexpire_router, pattern=r"^selfexpire_\d+$"))
    app.add_handler(CallbackQueryHandler(delloc_router, pattern=r"^delloc_\d+$"))
    app.add_handler(CallbackQueryHandler(help_topic_router, pattern=r"^help_(elon|limit|check|mening|hudud)$"))
    app.add_handler(CallbackQueryHandler(help_back_router, pattern="^help_back$"))
    app.add_handler(CallbackQueryHandler(blockcard_router, pattern=r"^blockcard_\d+_\d+$"))
    app.add_error_handler(error_handler)

    if app.job_queue:
        app.job_queue.run_daily(job_expiry_reminders, time=dtime(hour=9, minute=0, tzinfo=TASHKENT_TZ))
        app.job_queue.run_monthly(job_monthly_report, when=dtime(hour=9, minute=0, tzinfo=TASHKENT_TZ), day=1)
        app.job_queue.run_daily(job_daily_backup, time=dtime(hour=4, minute=0, tzinfo=TASHKENT_TZ))
        app.job_queue.run_daily(job_morning_digest, time=dtime(hour=8, minute=45, tzinfo=TASHKENT_TZ))
        app.job_queue.run_daily(job_stale_check, time=dtime(hour=10, minute=0, tzinfo=TASHKENT_TZ))
        # Aniq soat asosidagi jadval (O'ZBEKISTON vaqti bo'yicha) - dastur qachon
        # ishga tushganidan qat'iy nazar, faqat shu aniq soatlarda ishga tushadi
        # (00:00-08:00 Toshkent vaqti bo'yicha tinch vaqt).
        for hour in (8, 10, 12, 14, 16, 18, 20, 22):
            app.job_queue.run_daily(job_promote_limit, time=dtime(hour=hour, minute=0, tzinfo=TASHKENT_TZ))
        for hour in (8, 11, 14, 17, 20, 23):
            app.job_queue.run_daily(job_repost_paid_listings, time=dtime(hour=hour, minute=0, tzinfo=TASHKENT_TZ))
        app.job_queue.run_daily(job_weekly_top_location, time=dtime(hour=9, minute=0, tzinfo=TASHKENT_TZ), days=(0,))
        app.job_queue.run_daily(job_empty_region_alert, time=dtime(hour=11, minute=0, tzinfo=TASHKENT_TZ))
    else:
        logger.warning("JobQueue mavjud emas \u2014 eslatma va oylik hisobot ishlamaydi. O'rnating: pip install \"python-telegram-bot[job-queue]\"")

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
