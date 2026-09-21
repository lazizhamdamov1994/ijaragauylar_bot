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
import json
import logging
import sqlite3
from datetime import datetime, timedelta

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
    conn.execute("""CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, listing_id INTEGER NOT NULL,
        created_at TEXT, UNIQUE(user_id, listing_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS support_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT, full_name TEXT,
        message TEXT, status TEXT DEFAULT 'yangi', admin_reply TEXT, created_at TEXT, replied_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS user_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT, body TEXT,
        is_read INTEGER DEFAULT 0, created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS listing_price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL,
        old_narx TEXT, new_narx TEXT, changed_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS viewing_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        requested_time TEXT, status TEXT DEFAULT 'pending', created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS district_aliases (
        id INTEGER PRIMARY KEY AUTOINCREMENT, alias TEXT NOT NULL UNIQUE, district TEXT NOT NULL,
        added_by INTEGER, added_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_usage_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, feature TEXT NOT NULL, input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0, ok INTEGER DEFAULT 1, created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT NOT NULL, platform TEXT NOT NULL, created_at TEXT)""")
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
            "ai_scam_warning": "TEXT",
            "buttons_fixed": "INTEGER DEFAULT 0", "latitude": "REAL", "longitude": "REAL",
            "category": "TEXT DEFAULT 'egadan'", "rental_type": "TEXT DEFAULT 'uzoq_muddat'",
            "source": "TEXT DEFAULT 'bot'",
        }),
        ("subscriptions", {"months": "INTEGER DEFAULT 1", "price_charged": "INTEGER", "target_listing_id": "INTEGER", "receipt_warning": "TEXT"}),
        ("users", {"free_views_used": "INTEGER DEFAULT 0", "bonus_views": "INTEGER DEFAULT 0", "referred_by": "INTEGER", "referral_bonus_given": "INTEGER DEFAULT 0"}),
        ("listing_inquiries", {"sender_user_id": "INTEGER"}),
        ("moderators", {"is_super": "INTEGER DEFAULT 0"}),
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


def count_today_ai_chat_messages(user_key: str, platform: str) -> int:
    """AI Concierge kuchlik xarajatni nazorat qilish uchun - bitta
    foydalanuvchi/sessiya bir kunda nechta xabar yuborganini sanaydi
    (bot uchun user_key=telegram user_id, veb uchun sessiya/IP kaliti)."""
    since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM ai_chat_messages WHERE user_key = ? AND platform = ? AND created_at >= ?",
        (str(user_key), platform, since),
    ).fetchone()["c"]
    conn.close()
    return n


def log_ai_chat_message(user_key: str, platform: str) -> None:
    conn = db()
    conn.execute(
        "INSERT INTO ai_chat_messages (user_key, platform, created_at) VALUES (?, ?, ?)",
        (str(user_key), platform, now_str()),
    )
    conn.commit()
    conn.close()


def has_prior_rejected_listing(user_id: int = None, phone: str = None) -> bool:
    """Foydalanuvchining (yoki - veb orqali anonim yuborilgan e'lonlar
    uchun, ular hammasi user_id=0 bilan saqlanadi, shuning uchun TELEFON
    RAQAMI bo'yicha) ilgari rad etilgan e'loni bo'lganmi - AI orqali
    avtomatik tasdiqlash (auto-moderation) uchun ishonch tekshiruvi: agar
    bo'lsa, bunday yuboruvchining KEYINGI e'loni ham AVTOMATIK emas, odam
    tomonidan ko'rib chiqiladi."""
    conn = db()
    if user_id:
        row = conn.execute("SELECT 1 FROM listings WHERE user_id = ? AND status = 'rejected' LIMIT 1", (user_id,)).fetchone()
    elif phone:
        row = conn.execute("SELECT 1 FROM listings WHERE telefon = ? AND status = 'rejected' LIMIT 1", (phone,)).fetchone()
    else:
        row = None
    conn.close()
    return row is not None


# ============================= SEVIMLILAR (bot va sayt UMUMIY) =============================

def toggle_favorite(user_id: int, listing_id: int) -> bool:
    """E'lonni sevimlilarga qo'shadi/o'chiradi - YANGI holatni (True=qo'shildi,
    False=o'chirildi) qaytaradi."""
    conn = db()
    row = conn.execute("SELECT id FROM favorites WHERE user_id = ? AND listing_id = ?", (user_id, listing_id)).fetchone()
    if row:
        conn.execute("DELETE FROM favorites WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        return False
    conn.execute("INSERT INTO favorites (user_id, listing_id, created_at) VALUES (?, ?, ?)", (user_id, listing_id, now_str()))
    conn.commit()
    conn.close()
    return True


def get_favorite_listing_ids(user_id: int) -> set:
    conn = db()
    rows = conn.execute("SELECT listing_id FROM favorites WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return {r["listing_id"] for r in rows}


def get_favorite_listings_full(user_id: int) -> list:
    """Foydalanuvchining sevimli e'lonlarini (hali FAOL/tasdiqlangan
    bo'lganlarini, eng yangisi birinchi) to'liq ma'lumot bilan qaytaradi.
    `photos` ustuni bazada JSON MATN sifatida saqlanadi - kartochka
    render qilinishi uchun bu yerda ro'yxatga PARSE qilib beriladi
    (boshqa joylarda - masalan web/listings_data.py'da - xuddi shunday)."""
    conn = db()
    rows = conn.execute(
        """SELECT l.* FROM favorites f JOIN listings l ON l.id = f.listing_id
           WHERE f.user_id = ? AND l.status = 'approved' AND COALESCE(l.expired,0) = 0
           ORDER BY f.created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["photos"] = json.loads(d.get("photos") or "[]")
        except (TypeError, ValueError):
            d["photos"] = []
        result.append(d)
    return result


# ============================= E'LONNI TAHRIRLASH / YOPISH / O'CHIRISH (bot va sayt UMUMIY) =============================

LISTING_EDITABLE_FIELDS = ("manzil", "moljal", "kimlarga", "xona", "qulaylik", "narx")


def update_listing_fields(listing_id: int, updates: dict) -> None:
    """E'lonning ba'zi maydonlarini yangilaydi (FAQAT ruxsat etilgan
    maydonlar - telefon va rasmlar bu yerdan o'zgartirilmaydi). Narx
    o'zgarsa, `listing_price_history`ga eski/yangi qiymat yozib qo'yiladi -
    e'lon sahifasidagi "Narx tarixi" shundan o'qiladi."""
    updates = {k: v for k, v in updates.items() if k in LISTING_EDITABLE_FIELDS and v is not None}
    if not updates:
        return
    conn = db()
    if "narx" in updates:
        row = conn.execute("SELECT narx FROM listings WHERE id = ?", (listing_id,)).fetchone()
        old_narx = row["narx"] if row else None
        if old_narx is not None and old_narx != updates["narx"]:
            conn.execute(
                "INSERT INTO listing_price_history (listing_id, old_narx, new_narx, changed_at) VALUES (?, ?, ?, ?)",
                (listing_id, old_narx, updates["narx"], now_str()),
            )
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE listings SET {set_clause} WHERE id = ?", (*updates.values(), listing_id))
    conn.commit()
    conn.close()


def get_price_history(listing_id: int) -> list:
    conn = db()
    rows = conn.execute(
        "SELECT * FROM listing_price_history WHERE listing_id = ? ORDER BY changed_at ASC", (listing_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_listing_row(listing_id: int) -> None:
    conn = db()
    conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
    conn.commit()
    conn.close()


def mark_listing_expired(listing_id: int) -> None:
    """Foydalanuvchi o'zining e'lonini "topshirildi" deb belgilashi -
    (bot/db.py'da AVVAL shu yerda edi, endi web ham ishlatgani uchun
    umumiy joyga ko'chirildi; bot/db.py hozir buni faqat qayta eksport
    qiladi)."""
    conn = db()
    conn.execute("UPDATE listings SET expired = 1 WHERE id = ?", (listing_id,))
    conn.commit()
    conn.close()


# ============================= KO'RISH VAQTINI BRON QILISH (bot va sayt UMUMIY) =============================
# MUHIM: bu yerdagi funksiyalar faqat SO'ROVNI SAQLAYDI. Kimga ruxsat
# berish (Limit obunasi yoki bepul ko'rish bor-yo'qligi) - chaqiruvchi kod
# tomonidan, bu yerga yozishdan OLDIN, xuddi telefon ko'rsatishdagi BILAN
# AYNAN BIR XIL qoida bilan tekshiriladi (bot/menu.py:reveal_phone_core,
# web/pages.py'dagi is_web_subscribed tekshiruvi) - shu orqali bu funksiya
# to'lov devorini (paywall) aylanib o'tish yo'liga aylanib qolmaydi.

def create_viewing_request(listing_id: int, user_id: int, requested_time: str) -> int:
    conn = db()
    conn.execute(
        "INSERT INTO viewing_requests (listing_id, user_id, requested_time, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (listing_id, user_id, requested_time, now_str()),
    )
    conn.commit()
    req_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
    conn.close()
    return req_id


def get_viewing_request(request_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM viewing_requests WHERE id = ?", (request_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_viewing_request_status(request_id: int, status: str) -> None:
    conn = db()
    conn.execute("UPDATE viewing_requests SET status = ? WHERE id = ?", (status, request_id))
    conn.commit()
    conn.close()


def count_viewing_requests_today(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM viewing_requests WHERE user_id = ? AND substr(created_at,1,10) = ?", (user_id, today)
    ).fetchone()["c"]
    conn.close()
    return n


# ============================= "MENING SO'ROVLARIM" (kabinet - foydalanuvchi o'zi yuborgan so'rovlar) =============================

def get_sent_inquiries(user_id: int) -> list:
    conn = db()
    rows = conn.execute(
        """SELECT li.*, l.manzil AS listing_manzil FROM listing_inquiries li
           LEFT JOIN listings l ON l.id = li.listing_id
           WHERE li.sender_user_id = ? ORDER BY li.created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sent_subarenda_requests(user_id: int) -> list:
    conn = db()
    rows = conn.execute(
        "SELECT * FROM subarenda_requests WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sent_viewing_requests(user_id: int) -> list:
    conn = db()
    rows = conn.execute(
        """SELECT vr.*, l.manzil AS listing_manzil FROM viewing_requests vr
           LEFT JOIN listings l ON l.id = vr.listing_id
           WHERE vr.user_id = ? ORDER BY vr.created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================= QO'LLAB-QUVVATLASH SO'ROVLARI (foydalanuvchi -> admin) =============================

def create_support_request(user_id: int, username: str, full_name: str, message: str) -> int:
    conn = db()
    conn.execute(
        "INSERT INTO support_requests (user_id, username, full_name, message, status, created_at) VALUES (?, ?, ?, ?, 'yangi', ?)",
        (user_id, username, full_name, message, now_str()),
    )
    conn.commit()
    req_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
    conn.close()
    return req_id


def get_user_support_requests(user_id: int) -> list:
    conn = db()
    rows = conn.execute(
        "SELECT * FROM support_requests WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_support_requests(limit: int = 50) -> list:
    conn = db()
    rows = conn.execute(
        "SELECT * FROM support_requests WHERE status = 'yangi' ORDER BY created_at ASC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def reply_support_request(request_id: int, reply: str) -> dict | None:
    """Javob yozadi va so'rovni 'javob berildi' deb belgilaydi - qaysi
    foydalanuvchiga bildirishnoma yuborish kerakligini bilish uchun
    to'liq qatorni (user_id bilan) qaytaradi."""
    conn = db()
    conn.execute(
        "UPDATE support_requests SET admin_reply = ?, status = 'javob_berildi', replied_at = ? WHERE id = ?",
        (reply, now_str(), request_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM support_requests WHERE id = ?", (request_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ============================= BILDIRISHNOMALAR (admin -> foydalanuvchi, shaxsiy kabinetda ko'rinadi) =============================

def add_user_notification(user_id: int, title: str, body: str) -> None:
    conn = db()
    conn.execute(
        "INSERT INTO user_notifications (user_id, title, body, is_read, created_at) VALUES (?, ?, ?, 0, ?)",
        (user_id, title, body, now_str()),
    )
    conn.commit()
    conn.close()


def broadcast_notification(title: str, body: str) -> int:
    """Barcha (botdan foydalangan) foydalanuvchilarga bitta xabarni
    yuboradi - nechta odamga yetganini qaytaradi."""
    conn = db()
    user_ids = [r["user_id"] for r in conn.execute("SELECT user_id FROM users").fetchall()]
    now = now_str()
    conn.executemany(
        "INSERT INTO user_notifications (user_id, title, body, is_read, created_at) VALUES (?, ?, ?, 0, ?)",
        [(uid, title, body, now) for uid in user_ids],
    )
    conn.commit()
    conn.close()
    return len(user_ids)


def get_user_notifications(user_id: int, limit: int = 20) -> list:
    conn = db()
    rows = conn.execute(
        "SELECT * FROM user_notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_unread_notifications(user_id: int) -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM user_notifications WHERE user_id = ? AND is_read = 0", (user_id,)).fetchone()["c"]
    conn.close()
    return n


def mark_notifications_read(user_id: int) -> None:
    conn = db()
    conn.execute("UPDATE user_notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0", (user_id,))
    conn.commit()
    conn.close()
