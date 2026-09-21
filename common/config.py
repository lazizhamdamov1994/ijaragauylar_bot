"""
Umumiy sozlamalar (.env) - BITTA joyda.
==========================================================================
Avval BOT_TOKEN, ADMIN_IDS va h.k. bot.py va dashboard.py'da ALOHIDA-ALOHIDA
o'qilardi (ba'zan hatto sal boshqacha mantiq bilan - masalan ADMIN_IDS
ikkalasida boshqacha filtrlanardi). Endi ikkalasi ham FAQAT shu fayldan
import qiladi - qiymatlar va nomlar ATAYIN eskisi bilan bir xil qoldirilgan,
shuning uchun serverdagi mavjud `.env` faylini o'zgartirish SHART EMAS.
"""
import hashlib
import os

from dotenv import load_dotenv

load_dotenv()

# ---- Telegram bot ----
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID")
CHANNEL_ID = int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW else None
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")
# MUHIM: eski dashboard.py'da ADMIN_IDS filtri (faqat raqamli qismlarni olish)
# bot.py'dagidan ko'ra qattiqroq edi - shu ikkoviga bitta, XAVFSIZROQ variant
# qo'llanildi (noto'g'ri/bo'sh yozuvlar sokin tashlab ketiladi).
ADMIN_IDS = [int(x) for x in (os.getenv("ADMIN_IDS", "") or "").split(",") if x.strip().lstrip("-").isdigit()]
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "your_admin_username")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

# ---- Veb-sayt ----
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "").rstrip("/")
SITE_URL = DASHBOARD_URL  # dashboard.py'da shu nom bilan ishlatilgan
DASH_USER = os.getenv("DASHBOARD_USERNAME", "admin")
DASH_PASS = os.getenv("DASHBOARD_PASSWORD", "")
INSTAGRAM_URL = os.getenv("INSTAGRAM_URL", "https://www.instagram.com/ijaraga_uylar.uz/")

# ---- Baza va limitlar ----
DB_PATH = os.getenv("DB_PATH", "elonlar.db")
MAX_DAILY_LISTINGS = int(os.getenv("MAX_DAILY_LISTINGS", "5"))
MOD_DAILY_LISTINGS = int(os.getenv("MOD_DAILY_LISTINGS", "50"))
STALE_CHECK_DAYS = int(os.getenv("STALE_CHECK_DAYS", "7"))

# ---- AI (Claude) - ixtiyoriy yordamchi funksiyalar uchun ----
# Kalit bo'sh bo'lsa, common/ai.py'dagi barcha funksiyalar jim ravishda
# None qaytaradi - eski (regex asosidagi) mantiq ishlayveradi, hech narsa
# sinmaydi.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ---- To'lov ----
CARD_HOLDER = os.getenv("CARD_HOLDER", "")
CARD_NUMBER = os.getenv("CARD_NUMBER", "5614681434261669")

# `settings` jadvaliga BIRINCHI ishga tushishda yoziladigan standart qiymatlar
# (keyin admin panel/bot orqali o'zgartirilishi mumkin - shu yerdagilar faqat
# "hali bazada yo'q bo'lsa" ishlatiladi).
DEFAULT_SETTINGS = {
    "listing_price": os.getenv("LISTING_PRICE", "20000"),
    "subscription_price": os.getenv("SUBSCRIPTION_PRICE", "20000"),
    "subscription_days": os.getenv("SUBSCRIPTION_DAYS", "30"),
    "card_number": CARD_NUMBER,
    "subscriber_discount_percent": os.getenv("SUBSCRIBER_DISCOUNT_PERCENT", "25"),
    "free_views_enabled": "1",
    "free_views_count": "2",
    "promote_limit_interval_hours": os.getenv("PROMOTE_LIMIT_INTERVAL_HOURS", "2"),
    "paid_repost_interval_hours": os.getenv("PAID_REPOST_INTERVAL_HOURS", "3"),
    "usd_to_som_rate": os.getenv("USD_TO_SOM_RATE", "12700"),
    "ai_features_enabled": "0",
    "ai_auto_approve_free_listings": "0",
    "ai_concierge_daily_limit": "30",
    "ai_ops_report_enabled": "1",
}

# ---- Telegram orqali kirish (shaxsiy kabinet) ----
SESSION_SECRET = os.getenv("SESSION_SECRET") or hashlib.sha256((BOT_TOKEN + ":session-v1").encode()).hexdigest()
SESSION_COOKIE = "tg_session"
SESSION_MAX_AGE = 90 * 24 * 3600

# ---- Rasm keshi ----
PHOTO_CACHE_MAX_MB = int(os.getenv("PHOTO_CACHE_MAX_MB", "3072"))

# ---- SEO ----
GOOGLE_SITE_VERIFICATION = os.getenv("GOOGLE_SITE_VERIFICATION", "")
YANDEX_VERIFICATION = os.getenv("YANDEX_VERIFICATION", "")

# ---- Umumiy brend ----
SITE_NAME = "Ijaraga Uylar Maklersiz"
BRAND_SHORT = "Ijaraga Uylar"
