"""
Global konstantalar: .env'dan olingan sozlamalar (common/config orqali),
suhbat holatlari (STATES), tugma matnlari (BTN_*), va bir nechta statik
lug'atlar (STEPS, SETTINGS_FIELDS).
"""
import logging
from zoneinfo import ZoneInfo

from common.config import ADMIN_IDS, ADMIN_USERNAME, BOT_TOKEN as TOKEN, CARD_HOLDER, CHANNEL_ID, CHANNEL_USERNAME, DASHBOARD_URL, DB_PATH, DEFAULT_SETTINGS as INITIAL_SETTINGS, MAX_DAILY_LISTINGS, MOD_DAILY_LISTINGS, STALE_CHECK_DAYS

logger = logging.getLogger(__name__)

# ============================= SOZLAMALAR (.env) =============================
# MUHIM: barcha .env o'qish endi common/config.py'da BITTA joyda (yuqorida
# import qilingan) - bu yerda alohida load_dotenv()/qayta import shart emas.

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")  # Barcha rejalashtirilgan vazifalar shu vaqt mintaqasida ishlaydi (server UTCda bo'lsa ham)
MAX_PHOTOS = 10
PAGE_SIZE = 10

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
    SLIDESHOW_CONFIRM,
    EDIT_LISTING_VALUE,
    VIEWING_TIME_WAIT,
    DISTALIAS_ADD_WAIT,
    AI_CONCIERGE_CHAT,
    VALUATION_DISTRICT_WAIT,
    VALUATION_XONA,
    VALUATION_CONDITION,
    VALUATION_PHOTOS,
    VALUATION_RECEIPT_WAIT,
) = range(44)

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
BTN_DISTRICT_ALIASES = "\U0001F5FA Tuman kalit so'zlari"
BTN_AI_CONCIERGE = "\U0001F916 AI yordamchi"
BTN_AI_CONCIERGE_END = "\U0001F51A Suhbatni tugatish"
BTN_VALUATION = "\U0001F3F7 Uyimni baholash (AI)"
BTN_VALUATION_SKIP_PHOTOS = "➡️ Rasmsiz davom etish"
BTN_VALUATION_DONE_PHOTOS = "✅ Tayyor, baholang"

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
    "promote_limit_interval_hours": {
        "label": "\U0001F4E2 Limit reklama posti oralig'i (soat)",
        "hint": "Necha soatda bir marta kanalga «Limit» haqida reklama posti joylanishini yozing. Masalan: 2",
        "kind": "int",
    },
    "paid_repost_interval_hours": {
        "label": "\U0001F501 Pullik e'lonlarni qayta joylash oralig'i (soat)",
        "hint": "Pullik e'lonlar necha soatda bir marta kanalga qayta joylanishini yozing. Masalan: 3",
        "kind": "int",
    },
    "usd_to_som_rate": {
        "label": "\U0001F4B1 Dollar kursi (so'mda)",
        "hint": "1 dollar (yoki y.e.) necha so'm ekanini yozing - saytda «Eng arzon/qimmat» saralashda $ va so'm narxlarni solishtirish uchun ishlatiladi. Masalan: 12700",
        "kind": "int",
    },
    "ai_features_enabled": {
        "label": "\U0001F916 AI yordamchi funksiyalar",
        "kind": "bool",
    },
    "ai_auto_approve_free_listings": {
        "label": "\U0001F916 Bepul e'lonlarni AI avtomatik tasdiqlasin",
        "kind": "bool",
    },
    "ai_concierge_daily_limit": {
        "label": "\U0001F4AC AI yordamchi - kunlik xabar chegarasi (bitta foydalanuvchi)",
        "hint": "Bitta foydalanuvchi/mehmon bir kunda AI yordamchiga nechta xabar yozishi mumkinligini yozing. Masalan: 30",
        "kind": "int",
    },
    "ai_ops_report_enabled": {
        "label": "\U0001F4C8 Kunlik AI boshqaruv hisoboti",
        "hint": "Yoqilsa, har kuni kechqurun AI tahlili + tavsiyalar bilan qisqa hisobot adminlarga yuboriladi.",
        "kind": "bool",
    },
    "ai_scam_extra_guidance": {
        "label": "\U0001F9E0 AI firibgarlik skriningiga qo'shimcha ko'rsatma",
        "hint": "Haftalik \"AI aniqlik tahlili\" xabarida AI o'zi tavsiya bergan qo'shimcha ko'rsatmani shu yerga ko'chiring - darhol kuchga kiradi. Bo'sh qoldirish mumkin.",
        "kind": "text_long",
    },
    "ai_valuation_extra_guidance": {
        "label": "\U0001F9E0 AI uy baholashga qo'shimcha ko'rsatma",
        "hint": "AI narxni noto'g'ri baholayotganini payqasangiz, shu yerga tuzatuvchi ko'rsatma yozing (masalan \"eski uylarga rasm asosida narxni oshirmang\") - darhol kuchga kiradi.",
        "kind": "text_long",
    },
    "valuation_price": {
        "label": "\U0001F3F7 Pullik uy baholash narxi (so'm)",
        "hint": "Har bir foydalanuvchining BIRINCHI baholashi doim bepul. Keyingi (2-, 3- ...) baholashlar uchun narxni shu yerda belgilang. Masalan: 10000",
        "kind": "int",
    },
}



