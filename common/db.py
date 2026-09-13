"""
Umumiy baza qatlami - BITTA joyda.
==========================================================================
Avval bot.py'da `init_db()`/`migrate_db()` va dashboard.py'da
`init_tracking_tables()` ALOHIDA-ALOHIDA jadval yaratardi (bir xil
`elonlar.db` faylida) - endi ikkalasi ham shu yerdagi BITTA sxemadan
foydalanadi. Jadval/ustun nomlari ATAYIN eskisi bilan bir xil qoldirilgan -
mavjud serverdagi bazani o'chirish yoki qo'lda migratsiya qilish SHART EMAS,
`init_schema()`/`migrate_schema()` idempotent (necha marta chaqirilsa ham
xavfsiz).
"""
import logging
import sqlite3
from datetime import datetime

from common.config import DB_PATH, DEFAULT_SETTINGS

logger = logging.getLogger(__name__)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_parse_dt(value):
    """Bazadagi sana-vaqt matnini xavfsiz o'qiydi. Eski/nostandart formatdagi
    yozuvlar uchun (masalan qo'lda tuzatilgan yozuvlar) None qaytaradi,
    dastur hech qachon shu sabab bilan qulamasligi kerak."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


def init_schema() -> None:
    """Botga kerak BARCHA jadvallar + saytga kerak qo'shimcha (kuzatuv)
    jadvallar - bittada. CREATE TABLE IF NOT EXISTS bo'lgani uchun ikkala
    jarayon ham ishga tushishda xavfsiz chaqirishi mumkin."""
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
    # ---- Faqat sayt (dashboard) ishlatadigan kuzatuv jadvallari ----
    conn.execute("""CREATE TABLE IF NOT EXISTS map_views (id INTEGER PRIMARY KEY AUTOINCREMENT, viewed_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS map_clicks (id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL, clicked_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS site_visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, ip TEXT, country TEXT, city TEXT,
        device TEXT, browser TEXT, referrer TEXT, visited_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS subarenda_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, full_name TEXT, phone TEXT,
        manzil TEXT, xona TEXT, narx_talab TEXT, status TEXT DEFAULT 'yangi', created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS listing_inquiries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER, owner_user_id INTEGER,
        name TEXT, phone TEXT, message TEXT, status TEXT DEFAULT 'yangi', created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS web_listing_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT, created_at TEXT)""")
    conn.commit()
    conn.close()


def migrate_schema() -> None:
    """Eski bazalarga yangi ustunlarni qo'shadi (mavjud bo'lsa o'tkazib
    yuboriladi) - shu jumladan HAR IKKALA jarayonga kerak bo'lgan
    `listings.source`/`listings.rental_type`."""
    conn = db()
    for table, needed in (
        ("listings", {
            "sender_phone": "TEXT", "payment_receipt": "TEXT", "price_charged": "INTEGER",
            "is_quick": "INTEGER DEFAULT 0", "raw_text": "TEXT", "last_confirmed_at": "TEXT",
            "expired": "INTEGER DEFAULT 0", "stale_reports": "INTEGER DEFAULT 0", "receipt_warning": "TEXT",
            "buttons_fixed": "INTEGER DEFAULT 0", "latitude": "REAL", "longitude": "REAL",
            "category": "TEXT DEFAULT 'egadan'", "rental_type": "TEXT DEFAULT 'uzoq_muddat'",
            "source": "TEXT DEFAULT 'bot'",
        }),
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
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def init_and_migrate() -> None:
    """Ikkala jarayon ham ishga tushishda shu BITTA funksiyani chaqiradi."""
    init_schema()
    migrate_schema()
    seed_settings()


def get_setting(key: str, default: str = None) -> str:
    """`default` berilmasa - `common.config.DEFAULT_SETTINGS`dagi qiymatga
    tushadi (bot.py'ning eski xatti-harakati); `default` berilsa - aynan shu
    qiymat ishlatiladi (dashboard.py'ning eski xatti-harakati). Ikkala eski
    chaqiruv uslubi ham o'zgarishsiz ishlayveradi."""
    conn = db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row and row["value"] is not None:
        return row["value"]
    if default is not None:
        return default
    return DEFAULT_SETTINGS.get(key, "")


def set_setting(key: str, value: str) -> None:
    conn = db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def is_subscribed(user_id: int):
    """`subscriptions` jadvali bot va sayt uchun UMUMIY - shuning uchun bot
    orqali sotib olingan Limit saytda ham, aksincha ham darhol ko'rinadi."""
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


def get_blocked_phone(phone: str):
    conn = db()
    row = conn.execute("SELECT * FROM blocked_phones WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    return dict(row) if row else None


def is_phone_blocked(phone: str) -> bool:
    return get_blocked_phone(phone) is not None
