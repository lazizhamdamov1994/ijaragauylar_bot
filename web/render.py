"""
Sayt uchun umumiy render yordamchilari: i18n (uz/ru/en), sahifa
head/header/footer, e'lon kartochkasi, to'lov kartasi vizuali, ikonalar.
"""
import hashlib
import json
import os
import re
import urllib.parse
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from common.config import (
    BOT_USERNAME,
    BRAND_SHORT,
    CARD_HOLDER,
    CHANNEL_USERNAME,
    GOOGLE_SITE_VERIFICATION,
    INSTAGRAM_URL,
    SITE_NAME,
    SITE_URL,
    YANDEX_VERIFICATION,
)

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
try:
    with open(os.path.join(STATIC_DIR, "site.css"), "rb") as _f:
        CSS_VERSION = hashlib.md5(_f.read()).hexdigest()[:8]
except Exception:
    CSS_VERSION = "1"

def mask_card_holder(name: str) -> str:
    """Karta egasi ismini saytda XAVFSIZ ko'rsatish uchun - faqat BOSHIDAGI
    2 ta harf ochiq qoladi, qolgani "x" bilan yashiriladi (masalan
    "Laziz Hamdamov" -> "Laxxxx")."""
    name = (name or "").strip()
    if not name:
        return ""
    if len(name) <= 2:
        return name
    return name[:2] + "x" * 4


def render_credit_card(lang: str, card_digits: str, amount_text: str = "", with_copy: bool = False) -> str:
    """Karta raqamini haqiqiy bank kartasiga o'xshash, chiroyli ko'rinishda
    chiqaradi - listing_detail va /kabinet/limit ikkalasida ham ishlatiladi."""
    card_grouped = " ".join(card_digits[i:i + 4] for i in range(0, len(card_digits), 4)) if card_digits else ""
    masked_holder = mask_card_holder(CARD_HOLDER) or SITE_NAME
    amount_html = f'<div class="credit-card-amount">{amount_text}</div>' if amount_text else ""
    copy_html = ""
    if with_copy and card_digits:
        copy_html = (
            f'<button type="button" class="card-copy-btn" onclick="copyCardNumber(this, \'{card_digits}\')">'
            f'{icon("copy", 13)} <span>{t(lang, "copy_btn")}</span></button>'
        )
    return f"""<div class="credit-card">
  <div class="credit-card-top"><span class="credit-card-chip"></span><span class="credit-card-brand">{t(lang,'card_brand')}</span></div>
  <div class="credit-card-number">{esc_html(card_grouped) or '—'}</div>
  <div class="credit-card-bottom">
    <div><div class="credit-card-label">{t(lang,'card_holder_label')}</div><div class="credit-card-holder">{esc_html(masked_holder)}</div></div>
    {amount_html}
  </div>
</div>
{copy_html}"""



# MUHIM: tumanlar ro'yxati/aniqlash logikasi common/districts.py'da - bot
# ("Tezkor e'lon" oqimida manzilni avtomatik taklif qilish) va veb (SEO
# breadcrumb/sitemap) BITTA manbadan foydalanadi. Bu yerda faqat WEB'ga xos
# SEO-slug xaritalari qo'shiladi.
from common.districts import TASHKENT_DISTRICTS, extract_district  # noqa: E402

# Tuman -> SEO-do'stona URL bo'lagi ("Mirzo Ulug'bek" -> "mirzo-ulugbek") va
# teskarisi - /toshkent/{slug} sahifalari (web/pages.py) va sitemap.xml
# (web/seo.py) BITTA shu manbadan foydalanadi (ikki joyda alohida-alohida
# slug hisoblash - va ikkalasi orasida moslik yo'qolishi - xavfini yo'q qiladi).
DISTRICT_SLUGS = {re.sub(r"[^a-z0-9]+", "", d.lower()): d for d in TASHKENT_DISTRICTS}
DISTRICT_TO_SLUG = {name: slug for slug, name in DISTRICT_SLUGS.items()}


def display_address(l: dict) -> str:
    """Kartochka/sarlavha uchun manzilni qaytaradi - agar oddiy manzil
    bo'lmasa (tezkor e'lonlarda bo'lgani kabi), xom matndan tuman nomini
    avtomatik aniqlab, o'rniga qo'yadi."""
    manzil = (l.get("manzil") or "").strip()
    if manzil:
        return manzil
    district = extract_district(l.get("raw_text") or "")
    return f"{district}dagi e'lon"



SUPPORTED_LANGS = ("uz", "ru", "en")
DEFAULT_LANG = "uz"
LANG_FLAGS = {"uz": "\U0001F1FA\U0001F1FF", "ru": "\U0001F1F7\U0001F1FA", "en": "\U0001F1EC\U0001F1E7"}
LANG_META = {"uz": "O'zbekcha", "ru": "\u0420\u0443\u0441\u0441\u043a\u0438\u0439", "en": "English"}

TRANSLATIONS = {
    "nav_home": {"uz": "Bosh sahifa", "ru": "\u0413\u043b\u0430\u0432\u043d\u0430\u044f", "en": "Home"},
    "nav_subarenda": {"uz": "Ijara hamkorligi", "ru": "\u041f\u0430\u0440\u0442\u043d\u0451\u0440\u0441\u0442\u0432\u043e \u043f\u043e \u0430\u0440\u0435\u043d\u0434\u0435", "en": "Rental partnership"},
    "nav_map_title": {"uz": "Xaritadan topish", "ru": "\u041d\u0430\u0439\u0442\u0438 \u043d\u0430 \u043a\u0430\u0440\u0442\u0435", "en": "Find on map"},
    "nav_bot_title": {"uz": "Telegram bot", "ru": "Telegram-\u0431\u043e\u0442", "en": "Telegram bot"},
    "nav_channel_title": {"uz": "Telegram kanal", "ru": "Telegram-\u043a\u0430\u043d\u0430\u043b", "en": "Telegram channel"},
    "nav_post_cta": {"uz": "E'lon berish", "ru": "\u0420\u0430\u0437\u043c\u0435\u0441\u0442\u0438\u0442\u044c \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435", "en": "Post a listing"},
    "mobile_post": {"uz": "E'lon berish", "ru": "\u0420\u0430\u0437\u043c\u0435\u0441\u0442\u0438\u0442\u044c \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435", "en": "Post a listing"},
    "nav_account_label": {"uz": "Hisobingiz", "ru": "\u0412\u0430\u0448 \u043a\u0430\u0431\u0438\u043d\u0435\u0442", "en": "Your account"},
    "footer_tagline": {
        "uz": "Maklersiz, to'g'ridan-to'g'ri uy egasi bilan bog'lanish platformasi.",
        "ru": "\u041f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0430 \u0434\u043b\u044f \u043f\u0440\u044f\u043c\u043e\u0439 \u0441\u0432\u044f\u0437\u0438 \u0441 \u0445\u043e\u0437\u044f\u0438\u043d\u043e\u043c \u0436\u0438\u043b\u044c\u044f, \u0431\u0435\u0437 \u043f\u043e\u0441\u0440\u0435\u0434\u043d\u0438\u043a\u043e\u0432.",
        "en": "A platform to connect directly with homeowners \u2014 no agent fees.",
    },
    "footer_rights": {"uz": "Barcha huquqlar himoyalangan.", "ru": "\u0412\u0441\u0435 \u043f\u0440\u0430\u0432\u0430 \u0437\u0430\u0449\u0438\u0449\u0435\u043d\u044b.", "en": "All rights reserved."},
    "footer_nav_title": {"uz": "Sayt", "ru": "\u0421\u0430\u0439\u0442", "en": "Site"},
    "footer_social_title": {"uz": "Ijtimoiy tarmoqlar", "ru": "\u0421\u043e\u0446\u0441\u0435\u0442\u0438", "en": "Social"},

    "hero_title": {
        "uz": "Maklersiz uy toping va ijaraga bering",
        "ru": "\u041d\u0430\u0439\u0434\u0438\u0442\u0435 \u0438\u043b\u0438 \u0441\u0434\u0430\u0439\u0442\u0435 \u0436\u0438\u043b\u044c\u0451 \u0431\u0435\u0437 \u043f\u043e\u0441\u0440\u0435\u0434\u043d\u0438\u043a\u043e\u0432",
        "en": "Find or list a home \u2014 no agents involved",
    },
    "hero_sub": {
        "uz": "Pulingizni qadrlang \u2014 makler uchun emas, o'zingiz uchun ishlating",
        "ru": "\u0426\u0435\u043d\u0438\u0442\u0435 \u0441\u0432\u043e\u0438 \u0434\u0435\u043d\u044c\u0433\u0438 \u2014 \u0442\u0440\u0430\u0442\u044c\u0442\u0435 \u0438\u0445 \u043d\u0430 \u0441\u0435\u0431\u044f, \u0430 \u043d\u0435 \u043d\u0430 \u043c\u0430\u043a\u043b\u0435\u0440\u0430",
        "en": "Value your money \u2014 spend it on yourself, not on an agent",
    },
    "search_district_label": {"uz": "HUDUD", "ru": "\u0420\u0410\u0419\u041e\u041d", "en": "DISTRICT"},
    "search_all_districts": {"uz": "Barcha hududlar", "ru": "\u0412\u0441\u0435 \u0440\u0430\u0439\u043e\u043d\u044b", "en": "All districts"},
    "search_rooms_label": {"uz": "XONALAR SONI", "ru": "\u041a\u041e\u041b\u0418\u0427\u0415\u0421\u0422\u0412\u041e \u041a\u041e\u041c\u041d\u0410\u0422", "en": "ROOMS"},
    "search_rooms_any": {"uz": "Farqi yo'q", "ru": "\u041d\u0435\u0432\u0430\u0436\u043d\u043e", "en": "Any"},
    "search_btn": {"uz": "Qidirish", "ru": "\u041f\u043e\u0438\u0441\u043a", "en": "Search"},
    "stat_active": {"uz": "Faol e'lon", "ru": "\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0439", "en": "Active listings"},
    "stat_users": {"uz": "Foydalanuvchi", "ru": "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439", "en": "Users"},
    "stat_nofee": {"uz": "Maklersiz", "ru": "\u0411\u0435\u0437 \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u0438", "en": "Commission-free"},
    "rt_all": {"uz": "Barchasi", "ru": "\u0412\u0441\u0435", "en": "All"},
    "rt_uzoq_muddat": {"uz": "Uzoq muddat", "ru": "\u0414\u043e\u043b\u0433\u043e\u0441\u0440\u043e\u0447\u043d\u043e", "en": "Long-term"},
    "rt_kunlik": {"uz": "Kunlik", "ru": "\u041f\u043e\u0441\u0443\u0442\u043e\u0447\u043d\u043e", "en": "Daily"},
    "rt_dacha": {"uz": "Dacha", "ru": "\u0414\u0430\u0447\u0430", "en": "Cottage"},
    "rt_mehmonxona": {"uz": "Mehmonxona", "ru": "\u0413\u043e\u0441\u0442\u0435\u0432\u044b\u0435 \u043a\u043e\u043c\u043d\u0430\u0442\u044b", "en": "Guest rooms"},
    "section_search_results": {"uz": "Qidiruv natijalari", "ru": "\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b \u043f\u043e\u0438\u0441\u043a\u0430", "en": "Search results"},
    "section_latest": {"uz": "So'nggi e'lonlar", "ru": "\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f", "en": "Latest listings"},
    "section_count_suffix": {"uz": "{n} ta e'lon topildi", "ru": "\u041d\u0430\u0439\u0434\u0435\u043d\u043e \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0439: {n}", "en": "{n} listings found"},
    "sort_label": {"uz": "Saralash", "ru": "\u0421\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u043a\u0430", "en": "Sort"},
    "sort_tanlangan": {"uz": "Tanlangan", "ru": "\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0443\u0435\u043c\u044b\u0435", "en": "Featured"},
    "sort_yangi": {"uz": "Eng yangi", "ru": "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u043d\u043e\u0432\u044b\u0435", "en": "Newest"},
    "sort_arzon": {"uz": "Eng arzon", "ru": "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0434\u0435\u0448\u0451\u0432\u044b\u0435", "en": "Cheapest"},
    "sort_qimmat": {"uz": "Eng qimmat", "ru": "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0434\u043e\u0440\u043e\u0433\u0438\u0435", "en": "Most expensive"},
    "ai_chat_title": {"uz": "AI yordamchi", "ru": "\u0418\u0418-\u043f\u043e\u043c\u043e\u0449\u043d\u0438\u043a", "en": "AI assistant"},
    "ai_chat_welcome": {
        "uz": "Salom! Menga qanday uy kerakligini yozing - masalan \u00abChilonzorda 2 xonali, 300$ gacha\u00bb.",
        "ru": "\u041f\u0440\u0438\u0432\u0435\u0442! \u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435, \u043a\u0430\u043a\u043e\u0435 \u0436\u0438\u043b\u044c\u0451 \u0432\u0430\u043c \u043d\u0443\u0436\u043d\u043e \u2014 \u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440 \u00ab2-\u043a\u043e\u043c\u043d\u0430\u0442\u043d\u0430\u044f \u0432 \u0427\u0438\u043b\u0430\u043d\u0437\u0430\u0440\u0435, \u0434\u043e $300\u00bb.",
        "en": "Hi! Tell me what kind of place you're looking for - e.g. \u00ab2-room in Chilonzor, up to $300\u00bb.",
    },
    "ai_chat_placeholder": {"uz": "Savolingizni yozing...", "ru": "\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u0432\u043e\u043f\u0440\u043e\u0441...", "en": "Type your question..."},
    "ai_chat_disabled": {
        "uz": "AI yordamchi hozircha ishga tushirilmagan.",
        "ru": "\u0418\u0418-\u043f\u043e\u043c\u043e\u0449\u043d\u0438\u043a \u043f\u043e\u043a\u0430 \u043d\u0435 \u0432\u043a\u043b\u044e\u0447\u0451\u043d.",
        "en": "AI assistant isn't enabled yet.",
    },
    "ai_chat_error": {
        "uz": "Texnik nosozlik. Birozdan keyin qayta urinib ko'ring.",
        "ru": "\u0422\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u043d\u0435\u043f\u043e\u043b\u0430\u0434\u043a\u0430. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435.",
        "en": "Technical issue. Please try again shortly.",
    },
    "ai_chat_rate_limited": {
        "uz": "Bugungi xabar chegarasiga yetdingiz. Ertaga qayta urinib ko'ring.",
        "ru": "\u0412\u044b \u0434\u043e\u0441\u0442\u0438\u0433\u043b\u0438 \u0434\u043d\u0435\u0432\u043d\u043e\u0433\u043e \u043b\u0438\u043c\u0438\u0442\u0430 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0437\u0430\u0432\u0442\u0440\u0430.",
        "en": "You've reached today's message limit. Try again tomorrow.",
    },
    "empty_listings": {
        "uz": "Hech qanday e'lon topilmadi. Boshqa filtrni sinab ko'ring.",
        "ru": "\u041e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0434\u0440\u0443\u0433\u043e\u0439 \u0444\u0438\u043b\u044c\u0442\u0440.",
        "en": "No listings found. Try a different filter.",
    },
    "why_title": {"uz": "Nega bizni tanlashadi", "ru": "\u041f\u043e\u0447\u0435\u043c\u0443 \u0432\u044b\u0431\u0438\u0440\u0430\u044e\u0442 \u043d\u0430\u0441", "en": "Why choose us"},
    "why1_title": {"uz": "Maklersiz", "ru": "\u0411\u0435\u0437 \u043f\u043e\u0441\u0440\u0435\u0434\u043d\u0438\u043a\u043e\u0432", "en": "No agent fees"},
    "why1_desc": {"uz": "0% komissiya", "ru": "0% \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u0438", "en": "0% commission"},
    "why2_title": {"uz": "Tekshirilgan", "ru": "\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e", "en": "Verified"},
    "why2_desc": {"uz": "Firibgarlar bloklangan", "ru": "\u041c\u043e\u0448\u0435\u043d\u043d\u0438\u043a\u0438 \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u044b", "en": "Scammers blocked"},
    "why3_title": {"uz": "Tezkor", "ru": "\u0411\u044b\u0441\u0442\u0440\u043e", "en": "Fast"},
    "why3_desc": {"uz": "Soniyalarda bog'laning", "ru": "\u0421\u0432\u044f\u0437\u044c \u0437\u0430 \u0441\u0435\u043a\u0443\u043d\u0434\u044b", "en": "Connect in seconds"},
    "why4_title": {"uz": "Xaritada", "ru": "\u041d\u0430 \u043a\u0430\u0440\u0442\u0435", "en": "On the map"},
    "why4_desc": {"uz": "Joylashuvi aniq", "ru": "\u0422\u043e\u0447\u043d\u043e\u0435 \u0440\u0430\u0441\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435", "en": "Exact location"},

    "breadcrumb_home": {"uz": "Bosh sahifa", "ru": "\u0413\u043b\u0430\u0432\u043d\u0430\u044f", "en": "Home"},
    "badge_top": {"uz": "TOP e'lon", "ru": "\u0422\u041e\u041f \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435", "en": "TOP listing"},
    "badge_verified": {"uz": "Tekshirilgan e'lon", "ru": "\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043d\u043e\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435", "en": "Verified listing"},
    "fact_rooms": {"uz": "Xonalar soni", "ru": "\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u043a\u043e\u043c\u043d\u0430\u0442", "en": "Rooms"},
    "fact_for_whom": {"uz": "Kimlarga", "ru": "\u041a\u043e\u043c\u0443 \u0441\u0434\u0430\u0451\u0442\u0441\u044f", "en": "For whom"},
    "desc_title": {"uz": "Tavsif", "ru": "\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435", "en": "Description"},
    "no_desc": {"uz": "Qo'shimcha ma'lumot berilmagan.", "ru": "\u0414\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u0430\u044f \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044f \u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u0430.", "en": "No additional details provided."},
    "sidebar_cta": {"uz": "Telefon raqamini olish", "ru": "\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u043d\u043e\u043c\u0435\u0440 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0430", "en": "Get phone number"},
    "sidebar_note": {"uz": "Telegram bot orqali xavfsiz va tez", "ru": "\u0411\u044b\u0441\u0442\u0440\u043e \u0438 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e \u0447\u0435\u0440\u0435\u0437 Telegram-\u0431\u043e\u0442\u0430", "en": "Fast and secure via the Telegram bot"},
    "share_btn": {"uz": "Ulashish", "ru": "\u041f\u043e\u0434\u0435\u043b\u0438\u0442\u044c\u0441\u044f", "en": "Share"},
    "copy_btn": {"uz": "Nusxalash", "ru": "\u0421\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c", "en": "Copy"},
    "copied_btn": {"uz": "Nusxalandi", "ru": "\u0421\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d\u043e", "en": "Copied"},
    "link_copied": {"uz": "Havola nusxalandi!", "ru": "\u0421\u0441\u044b\u043b\u043a\u0430 \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d\u0430!", "en": "Link copied!"},
    "inquiry_toggle": {"uz": "Uy egasiga so'rov yuborish", "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0437\u0430\u043f\u0440\u043e\u0441 \u0445\u043e\u0437\u044f\u0438\u043d\u0443", "en": "Send a request to the owner"},
    "inquiry_name_ph": {"uz": "Ismingiz", "ru": "\u0412\u0430\u0448\u0435 \u0438\u043c\u044f", "en": "Your name"},
    "inquiry_phone_ph": {"uz": "Telefon raqamingiz", "ru": "\u0412\u0430\u0448 \u043d\u043e\u043c\u0435\u0440 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0430", "en": "Your phone number"},
    "inquiry_msg_ph": {"uz": "Xabar (ixtiyoriy)", "ru": "\u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)", "en": "Message (optional)"},
    "inquiry_send": {"uz": "Yuborish", "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c", "en": "Send"},
    "inquiry_success": {"uz": "So'rovingiz yuborildi!", "ru": "\u0412\u0430\u0448 \u0437\u0430\u043f\u0440\u043e\u0441 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d!", "en": "Your request has been sent!"},
    "inquiry_error": {"uz": "Xatolik yuz berdi, qaytadan urinib ko'ring.", "ru": "\u041f\u0440\u043e\u0438\u0437\u043e\u0448\u043b\u0430 \u043e\u0448\u0438\u0431\u043a\u0430, \u043f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430.", "en": "Something went wrong, please try again."},
    "price_history_title": {"uz": "Narx tarixi", "ru": "\u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0446\u0435\u043d", "en": "Price history"},
    "viewing_request_btn": {"uz": "Ko'rish vaqtini so'rash", "ru": "\u0417\u0430\u043f\u0440\u043e\u0441\u0438\u0442\u044c \u0432\u0440\u0435\u043c\u044f \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u0430", "en": "Request a viewing"},
    "viewing_time_ph": {"uz": "Masalan: Ertaga soat 15:00", "ru": "\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0417\u0430\u0432\u0442\u0440\u0430 \u0432 15:00", "en": "E.g. Tomorrow at 3 PM"},
    "viewing_send": {"uz": "So'rov yuborish", "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0437\u0430\u043f\u0440\u043e\u0441", "en": "Send request"},
    "viewing_success": {"uz": "So'rovingiz uy egasiga yuborildi!", "ru": "\u0412\u0430\u0448 \u0437\u0430\u043f\u0440\u043e\u0441 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d \u0432\u043b\u0430\u0434\u0435\u043b\u044c\u0446\u0443!", "en": "Your request has been sent to the owner!"},
    "related_title": {"uz": "O'xshash e'lonlar", "ru": "\u041f\u043e\u0445\u043e\u0436\u0438\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f", "en": "Similar listings"},
    "not_found_title": {"uz": "E'lon topilmadi", "ru": "\u041e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e", "en": "Listing not found"},
    "not_found_desc": {
        "uz": "Bu e'lon topilmadi yoki muddati tugagan",
        "ru": "\u042d\u0442\u043e \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0438\u043b\u0438 \u0441\u0440\u043e\u043a \u0435\u0433\u043e \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f \u0438\u0441\u0442\u0451\u043a",
        "en": "This listing was not found or has expired",
    },
    "not_found_body": {
        "uz": "Bu e'lon topilmadi yoki muddati tugagan.",
        "ru": "\u042d\u0442\u043e \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0438\u043b\u0438 \u0441\u0440\u043e\u043a \u0435\u0433\u043e \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f \u0438\u0441\u0442\u0451\u043a.",
        "en": "This listing was not found or has expired.",
    },
    "back_home_btn": {"uz": "Bosh sahifaga qaytish", "ru": "\u0412\u0435\u0440\u043d\u0443\u0442\u044c\u0441\u044f \u043d\u0430 \u0433\u043b\u0430\u0432\u043d\u0443\u044e", "en": "Back to home"},
    "no_photo": {"uz": "Rasm yo'q", "ru": "\u041d\u0435\u0442 \u0444\u043e\u0442\u043e", "en": "No photo"},

    "ej_hero_title": {"uz": "Uyingizni ijaraga bering", "ru": "\u0421\u0434\u0430\u0439\u0442\u0435 \u0436\u0438\u043b\u044c\u0451 \u0432 \u0430\u0440\u0435\u043d\u0434\u0443", "en": "Rent out your home"},
    "ej_hero_sub": {
        "uz": "Formani to'ldiring \u2014 e'loningiz tekshirilgach, avtomatik ravishda Telegram kanalimizda va shu saytda e'lon qilinadi. Ro'yxatdan o'tish shart emas.",
        "ru": "\u0417\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u0435 \u0444\u043e\u0440\u043c\u0443 \u2014 \u043f\u043e\u0441\u043b\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u043f\u043e\u044f\u0432\u0438\u0442\u0441\u044f \u0432 \u043d\u0430\u0448\u0435\u043c Telegram-\u043a\u0430\u043d\u0430\u043b\u0435 \u0438 \u043d\u0430 \u0441\u0430\u0439\u0442\u0435. \u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f \u043d\u0435 \u0442\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f.",
        "en": "Fill out the form \u2014 once reviewed, your listing automatically appears in our Telegram channel and on this site. No registration needed.",
    },
    "ej_badge": {
        "uz": "Har bir e'lon qo'lda tekshiriladi \u2014 firibgarlarga joy yo'q",
        "ru": "\u041a\u0430\u0436\u0434\u043e\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u0442\u0441\u044f \u0432\u0440\u0443\u0447\u043d\u0443\u044e \u2014 \u043c\u043e\u0448\u0435\u043d\u043d\u0438\u043a\u0430\u043c \u0437\u0434\u0435\u0441\u044c \u043d\u0435 \u043c\u0435\u0441\u0442\u043e",
        "en": "Every listing is manually reviewed \u2014 no room for scammers",
    },
    "ej_section_rental_type": {"uz": "Ijara turi", "ru": "\u0422\u0438\u043f \u0430\u0440\u0435\u043d\u0434\u044b", "en": "Rental type"},
    "ej_section_house": {"uz": "Uy haqida", "ru": "\u041e \u0436\u0438\u043b\u044c\u0435", "en": "About the property"},
    "ej_manzil_label": {"uz": "Manzil (tuman, mahalla)", "ru": "\u0410\u0434\u0440\u0435\u0441 (\u0440\u0430\u0439\u043e\u043d, \u043c\u0430\u0445\u0430\u043b\u043b\u044f)", "en": "Address (district, neighborhood)"},
    "ej_manzil_ph": {"uz": "Masalan: Yunusobod, 12-kvartal", "ru": "\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u042e\u043d\u0443\u0441\u0430\u0431\u0430\u0434, 12-\u0439 \u043a\u0432\u0430\u0440\u0442\u0430\u043b", "en": "e.g. Yunusobod, block 12"},
    "ej_moljal_label": {"uz": "Mo'ljal", "ru": "\u041e\u0440\u0438\u0435\u043d\u0442\u0438\u0440", "en": "Landmark"},
    "ej_moljal_ph": {"uz": "Masalan: Metro bekatiga yaqin, Korzinka yonida", "ru": "\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0440\u044f\u0434\u043e\u043c \u0441 \u043c\u0435\u0442\u0440\u043e, \u0432\u043e\u0437\u043b\u0435 Korzinka", "en": "e.g. near the metro, next to Korzinka"},
    "ej_xona_label": {"uz": "Nechta xonali?", "ru": "\u0421\u043a\u043e\u043b\u044c\u043a\u043e \u043a\u043e\u043c\u043d\u0430\u0442?", "en": "Number of rooms"},
    "ej_xona_ph": {"uz": "Masalan: 2 xona, studio", "ru": "\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: 2 \u043a\u043e\u043c\u043d\u0430\u0442\u044b, \u0441\u0442\u0443\u0434\u0438\u044f", "en": "e.g. 2 rooms, studio"},
    "ej_kimlarga_label": {"uz": "Kimlarga beriladi?", "ru": "\u041a\u043e\u043c\u0443 \u0441\u0434\u0430\u0451\u0442\u0441\u044f?", "en": "Who is it for?"},
    "ej_kimlarga_ph": {"uz": "Masalan: oilaga, talabalarga", "ru": "\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0441\u0435\u043c\u044c\u0435, \u0441\u0442\u0443\u0434\u0435\u043d\u0442\u0430\u043c", "en": "e.g. families, students"},
    "ej_qulaylik_label": {"uz": "Sharoitlari", "ru": "\u0423\u0441\u043b\u043e\u0432\u0438\u044f", "en": "Amenities"},
    "ej_qulaylik_ph": {
        "uz": "Masalan: ta'mirlangan, mebel bilan, isitish tizimi bor...",
        "ru": "\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0441 \u0440\u0435\u043c\u043e\u043d\u0442\u043e\u043c, \u0441 \u043c\u0435\u0431\u0435\u043b\u044c\u044e, \u0435\u0441\u0442\u044c \u043e\u0442\u043e\u043f\u043b\u0435\u043d\u0438\u0435...",
        "en": "e.g. renovated, furnished, has heating...",
    },
    "ej_narx_label": {"uz": "Narxi", "ru": "\u0426\u0435\u043d\u0430", "en": "Price"},
    "ej_narx_ph": {"uz": "Masalan: 150$, 1.2 mln, kelishiladi", "ru": "\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: 150$, 1.2 \u043c\u043b\u043d, \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u043d\u0430\u044f", "en": "e.g. $150, negotiable"},
    "ej_section_contact": {"uz": "Aloqa", "ru": "\u041a\u043e\u043d\u0442\u0430\u043a\u0442\u044b", "en": "Contact"},
    "ej_fullname_label": {"uz": "Ismingiz", "ru": "\u0412\u0430\u0448\u0435 \u0438\u043c\u044f", "en": "Your name"},
    "ej_fullname_ph": {"uz": "Ixtiyoriy", "ru": "\u041d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e", "en": "Optional"},
    "ej_phone_label": {"uz": "Telefon raqami", "ru": "\u041d\u043e\u043c\u0435\u0440 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0430", "en": "Phone number"},
    "ej_phone_hint": {
        "uz": "Bu raqam e'londa ko'rsatiladi \u2014 ijarachilar shu orqali siz bilan bog'lanadi.",
        "ru": "\u042d\u0442\u043e\u0442 \u043d\u043e\u043c\u0435\u0440 \u0431\u0443\u0434\u0435\u0442 \u0432\u0438\u0434\u0435\u043d \u0432 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0438 \u2014 \u0430\u0440\u0435\u043d\u0434\u0430\u0442\u043e\u0440\u044b \u0441\u0432\u044f\u0436\u0443\u0442\u0441\u044f \u0441 \u0432\u0430\u043c\u0438 \u043f\u043e \u043d\u0435\u043c\u0443.",
        "en": "This number will be shown in the listing \u2014 renters will contact you on it.",
    },
    "ej_section_location": {"uz": "Joylashuv (ixtiyoriy)", "ru": "\u0420\u0430\u0441\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435 (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)", "en": "Location (optional)"},
    "ej_loc_toggle": {"uz": "Xaritada aniq nuqtani belgilash", "ru": "\u0423\u043a\u0430\u0437\u0430\u0442\u044c \u0442\u043e\u0447\u043a\u0443 \u043d\u0430 \u043a\u0430\u0440\u0442\u0435", "en": "Pin the exact spot on the map"},
    "ej_section_photos": {"uz": "Rasmlar", "ru": "\u0424\u043e\u0442\u043e\u0433\u0440\u0430\u0444\u0438\u0438", "en": "Photos"},
    "ej_photo_drop_title": {"uz": "Rasmlarni shu yerga bosing yoki tashlang", "ru": "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u0438\u043b\u0438 \u043f\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0444\u043e\u0442\u043e \u0441\u044e\u0434\u0430", "en": "Click or drop photos here"},
    "ej_photo_drop_sub": {"uz": "1 dan 10 tagacha, har biri 10MB gacha", "ru": "\u041e\u0442 1 \u0434\u043e 10 \u0444\u043e\u0442\u043e, \u043a\u0430\u0436\u0434\u043e\u0435 \u0434\u043e 10\u041c\u0411", "en": "1 to 10 photos, up to 10MB each"},
    "ej_section_type": {"uz": "E'lon turi", "ru": "\u0422\u0438\u043f \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f", "en": "Listing type"},
    "ej_type_free_title": {"uz": "Bepul", "ru": "\u0411\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u043e", "en": "Free"},
    "ej_type_free_desc": {
        "uz": "Kanalga bir marta joylanadi, navbat asosida ko'rib chiqiladi.",
        "ru": "\u041f\u0443\u0431\u043b\u0438\u043a\u0443\u0435\u0442\u0441\u044f \u0432 \u043a\u0430\u043d\u0430\u043b\u0435 \u043e\u0434\u0438\u043d \u0440\u0430\u0437, \u0440\u0430\u0441\u0441\u043c\u0430\u0442\u0440\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u0432 \u043f\u043e\u0440\u044f\u0434\u043a\u0435 \u043e\u0447\u0435\u0440\u0435\u0434\u0438.",
        "en": "Posted to the channel once, reviewed in queue order.",
    },
    "ej_type_paid_title": {"uz": "Pullik \u2014 {price} so'm", "ru": "\u041f\u043b\u0430\u0442\u043d\u043e \u2014 {price} \u0441\u0443\u043c", "en": "Paid \u2014 {price} UZS"},
    "ej_type_paid_desc": {
        "uz": "Uyingiz topshirilguncha (kamida 7 kun) doim TOP'da \u2014 tezroq va ko'proq ko'rinadi.",
        "ru": "\u0412\u0430\u0448\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u0432 \u0422\u041e\u041f\u0435, \u043f\u043e\u043a\u0430 \u0436\u0438\u043b\u044c\u0451 \u043d\u0435 \u0441\u0434\u0430\u043d\u043e (\u043c\u0438\u043d\u0438\u043c\u0443\u043c 7 \u0434\u043d\u0435\u0439) \u2014 \u0431\u044b\u0441\u0442\u0440\u0435\u0435 \u0438 \u0431\u043e\u043b\u044c\u0448\u0435 \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u043e\u0432.",
        "en": "Stays TOP-pinned until your place is rented (at least 7 days) \u2014 faster, more visibility.",
    },
    "ej_pay_card_label": {"uz": "TO'LOV KARTASI", "ru": "\u041a\u0410\u0420\u0422\u0410 \u0414\u041b\u042f \u041e\u041f\u041b\u0410\u0422\u042b", "en": "PAYMENT CARD"},
    "ej_pay_copy": {"uz": "Nusxalash", "ru": "\u0421\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c", "en": "Copy"},
    "ej_pay_hint": {
        "uz": "Yuqoridagi kartaga {price} so'm o'tkazing, so'ng chek skrinshotini yuklang.",
        "ru": "\u041f\u0435\u0440\u0435\u0432\u0435\u0434\u0438\u0442\u0435 {price} \u0441\u0443\u043c \u043d\u0430 \u043a\u0430\u0440\u0442\u0443 \u0432\u044b\u0448\u0435, \u0437\u0430\u0442\u0435\u043c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 \u0441\u043a\u0440\u0438\u043d\u0448\u043e\u0442 \u0447\u0435\u043a\u0430.",
        "en": "Transfer {price} UZS to the card above, then upload a screenshot of the receipt.",
    },
    "ej_receipt_title": {"uz": "To'lov chekini yuklash", "ru": "\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0447\u0435\u043a \u043e\u0431 \u043e\u043f\u043b\u0430\u0442\u0435", "en": "Upload payment receipt"},
    "ej_receipt_sub": {"uz": "Skrinshot yoki fotosurat", "ru": "\u0421\u043a\u0440\u0438\u043d\u0448\u043e\u0442 \u0438\u043b\u0438 \u0444\u043e\u0442\u043e", "en": "Screenshot or photo"},
    "ej_submit_btn": {"uz": "E'lonni yuborish", "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435", "en": "Submit listing"},
    "ej_submit_note": {
        "uz": "Yuborish orqali siz e'lon ma'lumotlarining to'g'riligini tasdiqlaysiz.",
        "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u044f \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435, \u0432\u044b \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0430\u0435\u0442\u0435 \u0434\u043e\u0441\u0442\u043e\u0432\u0435\u0440\u043d\u043e\u0441\u0442\u044c \u0443\u043a\u0430\u0437\u0430\u043d\u043d\u044b\u0445 \u0434\u0430\u043d\u043d\u044b\u0445.",
        "en": "By submitting, you confirm the listing details are accurate.",
    },
    "ej_success_title": {"uz": "E'loningiz qabul qilindi!", "ru": "\u0412\u0430\u0448\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u043f\u0440\u0438\u043d\u044f\u0442\u043e!", "en": "Your listing was received!"},
    "ej_success_text": {
        "uz": "Tez orada administrator tekshirib, tasdiqlaydi \u2014 shundan so'ng Telegram kanalimizda va saytda chiqadi. E'lon raqami: #{id}",
        "ru": "\u0412 \u0431\u043b\u0438\u0436\u0430\u0439\u0448\u0435\u0435 \u0432\u0440\u0435\u043c\u044f \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440 \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442 \u0438 \u043e\u0434\u043e\u0431\u0440\u0438\u0442 \u0435\u0433\u043e \u2014 \u043f\u043e\u0441\u043b\u0435 \u044d\u0442\u043e\u0433\u043e \u043e\u043d\u043e \u043f\u043e\u044f\u0432\u0438\u0442\u0441\u044f \u0432 \u043d\u0430\u0448\u0435\u043c Telegram-\u043a\u0430\u043d\u0430\u043b\u0435 \u0438 \u043d\u0430 \u0441\u0430\u0439\u0442\u0435. \u041d\u043e\u043c\u0435\u0440 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f: #{id}",
        "en": "An administrator will review and approve it shortly \u2014 then it will appear in our Telegram channel and on the site. Listing number: #{id}",
    },
    "ej_err_no_photo": {"uz": "Kamida 1 ta uy rasmini yuklang.", "ru": "\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 \u0445\u043e\u0442\u044f \u0431\u044b 1 \u0444\u043e\u0442\u043e \u0436\u0438\u043b\u044c\u044f.", "en": "Upload at least 1 photo of the property."},
    "ej_err_no_receipt": {
        "uz": "Pullik e'lon uchun to'lov chekining skrinshotini yuklang.",
        "ru": "\u0414\u043b\u044f \u043f\u043b\u0430\u0442\u043d\u043e\u0433\u043e \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 \u0441\u043a\u0440\u0438\u043d\u0448\u043e\u0442 \u0447\u0435\u043a\u0430 \u043e\u0431 \u043e\u043f\u043b\u0430\u0442\u0435.",
        "en": "Upload a payment receipt screenshot for a paid listing.",
    },
    "ej_submitting": {"uz": "Yuborilmoqda...", "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u043a\u0430...", "en": "Submitting..."},
    "ej_err_generic": {"uz": "Xatolik yuz berdi. Qaytadan urinib ko'ring.", "ru": "\u041f\u0440\u043e\u0438\u0437\u043e\u0448\u043b\u0430 \u043e\u0448\u0438\u0431\u043a\u0430. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430.", "en": "Something went wrong. Please try again."},
    "ej_err_network": {"uz": "Internet aloqasida muammo. Qaytadan urinib ko'ring.", "ru": "\u041f\u0440\u043e\u0431\u043b\u0435\u043c\u0430 \u0441 \u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442-\u0441\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u0435\u043c. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430.", "en": "Network problem. Please try again."},

    "sr_hero_title": {"uz": "Uyingizni bizga ishoning", "ru": "\u0414\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0441\u0432\u043e\u0451 \u0436\u0438\u043b\u044c\u0451 \u043d\u0430\u043c", "en": "Trust us with your property"},
    "sr_hero_sub": {
        "uz": "Ijarachi qidirish, shartnoma va oylik to'lovlar bilan bosh og'rig'ini unuting \u2014 biz hammasini boshqaramiz, sizga esa har oy kafolatlangan ijara puli keladi.",
        "ru": "\u0417\u0430\u0431\u0443\u0434\u044c\u0442\u0435 \u043e \u043f\u043e\u0438\u0441\u043a\u0435 \u0430\u0440\u0435\u043d\u0434\u0430\u0442\u043e\u0440\u043e\u0432, \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430\u0445 \u0438 \u0435\u0436\u0435\u043c\u0435\u0441\u044f\u0447\u043d\u044b\u0445 \u043f\u043b\u0430\u0442\u0435\u0436\u0430\u0445 \u2014 \u043c\u044b \u0431\u0435\u0440\u0451\u043c \u0432\u0441\u0451 \u043d\u0430 \u0441\u0435\u0431\u044f, \u0430 \u0432\u044b \u043a\u0430\u0436\u0434\u044b\u0439 \u043c\u0435\u0441\u044f\u0446 \u043f\u043e\u043b\u0443\u0447\u0430\u0435\u0442\u0435 \u0433\u0430\u0440\u0430\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u0443\u044e \u0430\u0440\u0435\u043d\u0434\u043d\u0443\u044e \u043f\u043b\u0430\u0442\u0443.",
        "en": "Forget the hassle of finding tenants, contracts, and monthly payments \u2014 we handle everything, and you receive guaranteed rent every month.",
    },
    "sr1_title": {"uz": "Ijarachi biz tomondan", "ru": "\u0410\u0440\u0435\u043d\u0434\u0430\u0442\u043e\u0440\u043e\u0432 \u0438\u0449\u0435\u043c \u043c\u044b", "en": "We find the tenants"},
    "sr1_desc": {"uz": "Sizga ijarachi izlashning hojati yo'q - buni to'liq biz bajaramiz", "ru": "\u0412\u0430\u043c \u043d\u0435 \u043d\u0443\u0436\u043d\u043e \u0438\u0441\u043a\u0430\u0442\u044c \u0430\u0440\u0435\u043d\u0434\u0430\u0442\u043e\u0440\u043e\u0432 \u2014 \u043c\u044b \u0434\u0435\u043b\u0430\u0435\u043c \u044d\u0442\u043e \u043f\u043e\u043b\u043d\u043e\u0441\u0442\u044c\u044e \u0441\u0430\u043c\u0438", "en": "You don't need to search for tenants \u2014 we handle it entirely"},
    "sr2_title": {"uz": "Kafolatlangan to'lov", "ru": "\u0413\u0430\u0440\u0430\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u0430\u044f \u043e\u043f\u043b\u0430\u0442\u0430", "en": "Guaranteed payment"},
    "sr2_desc": {"uz": "Uy bo'sh tursa ham, kelishilgan summa har oy sizga to'lanadi", "ru": "\u0414\u0430\u0436\u0435 \u0435\u0441\u043b\u0438 \u0436\u0438\u043b\u044c\u0451 \u043f\u0443\u0441\u0442\u0443\u0435\u0442, \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u043d\u0430\u044f \u0441\u0443\u043c\u043c\u0430 \u0432\u044b\u043f\u043b\u0430\u0447\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u043a\u0430\u0436\u0434\u044b\u0439 \u043c\u0435\u0441\u044f\u0446", "en": "Even if the property is vacant, the agreed amount is paid every month"},
    "sr3_title": {"uz": "Rasmiy shartnoma", "ru": "\u041e\u0444\u0438\u0446\u0438\u0430\u043b\u044c\u043d\u044b\u0439 \u0434\u043e\u0433\u043e\u0432\u043e\u0440", "en": "Official contract"},
    "sr3_desc": {"uz": "Barcha jarayon yozma shartnoma asosida, qonuniy tartibda amalga oshiriladi", "ru": "\u0412\u0435\u0441\u044c \u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u043e\u0444\u043e\u0440\u043c\u043b\u044f\u0435\u0442\u0441\u044f \u043f\u0438\u0441\u044c\u043c\u0435\u043d\u043d\u044b\u043c \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u043e\u043c \u0432 \u0437\u0430\u043a\u043e\u043d\u043d\u043e\u043c \u043f\u043e\u0440\u044f\u0434\u043a\u0435", "en": "The whole process is governed by a written, legally sound contract"},
    "sr4_title": {"uz": "Uy holatini nazorat", "ru": "\u041a\u043e\u043d\u0442\u0440\u043e\u043b\u044c \u0441\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u044f \u0436\u0438\u043b\u044c\u044f", "en": "Property condition monitoring"},
    "sr4_desc": {"uz": "Uyingiz muntazam tekshiriladi, muammolar tezkor hal qilinadi", "ru": "\u0412\u0430\u0448\u0435 \u0436\u0438\u043b\u044c\u0451 \u0440\u0435\u0433\u0443\u043b\u044f\u0440\u043d\u043e \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u0442\u0441\u044f, \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u044b \u0440\u0435\u0448\u0430\u044e\u0442\u0441\u044f \u043e\u043f\u0435\u0440\u0430\u0442\u0438\u0432\u043d\u043e", "en": "Your property is checked regularly, and issues are resolved promptly"},
    "sr_form_title": {"uz": "Ariza qoldiring", "ru": "\u041e\u0441\u0442\u0430\u0432\u044c\u0442\u0435 \u0437\u0430\u044f\u0432\u043a\u0443", "en": "Leave a request"},
    "sr_form_sub": {"uz": "Mutaxassisimiz 24 soat ichida siz bilan bog'lanadi", "ru": "\u041d\u0430\u0448 \u0441\u043f\u0435\u0446\u0438\u0430\u043b\u0438\u0441\u0442 \u0441\u0432\u044f\u0436\u0435\u0442\u0441\u044f \u0441 \u0432\u0430\u043c\u0438 \u0432 \u0442\u0435\u0447\u0435\u043d\u0438\u0435 24 \u0447\u0430\u0441\u043e\u0432", "en": "Our specialist will contact you within 24 hours"},
    "sr_name_ph": {"uz": "Ismingiz", "ru": "\u0412\u0430\u0448\u0435 \u0438\u043c\u044f", "en": "Your name"},
    "sr_phone_ph": {"uz": "Telefon raqamingiz (+998...)", "ru": "\u0412\u0430\u0448 \u043d\u043e\u043c\u0435\u0440 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0430 (+998...)", "en": "Your phone number (+998...)"},
    "sr_manzil_ph": {"uz": "Uy manzili (tuman, mahalla)", "ru": "\u0410\u0434\u0440\u0435\u0441 \u0436\u0438\u043b\u044c\u044f (\u0440\u0430\u0439\u043e\u043d, \u043c\u0430\u0445\u0430\u043b\u043b\u044f)", "en": "Property address (district, neighborhood)"},
    "sr_xona_ph": {"uz": "Xonalar soni", "ru": "\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u043a\u043e\u043c\u043d\u0430\u0442", "en": "Number of rooms"},
    "sr_narx_ph": {"uz": "Kutilayotgan oylik narx ($ yoki so'm)", "ru": "\u041e\u0436\u0438\u0434\u0430\u0435\u043c\u0430\u044f \u0435\u0436\u0435\u043c\u0435\u0441\u044f\u0447\u043d\u0430\u044f \u0446\u0435\u043d\u0430 ($ \u0438\u043b\u0438 \u0441\u0443\u043c)", "en": "Expected monthly price ($ or UZS)"},
    "sr_submit_btn": {"uz": "Arizani yuborish", "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0437\u0430\u044f\u0432\u043a\u0443", "en": "Submit request"},
    "sr_success_title": {"uz": "Arizangiz qabul qilindi!", "ru": "\u0412\u0430\u0448\u0430 \u0437\u0430\u044f\u0432\u043a\u0430 \u043f\u0440\u0438\u043d\u044f\u0442\u0430!", "en": "Your request was received!"},
    "sr_success_sub": {"uz": "Tez orada siz bilan bog'lanamiz.", "ru": "\u041c\u044b \u0441\u043a\u043e\u0440\u043e \u0441\u0432\u044f\u0436\u0435\u043c\u0441\u044f \u0441 \u0432\u0430\u043c\u0438.", "en": "We'll be in touch shortly."},
    "sr_error": {"uz": "Xatolik yuz berdi, qaytadan urinib ko'ring.", "ru": "\u041f\u0440\u043e\u0438\u0437\u043e\u0448\u043b\u0430 \u043e\u0448\u0438\u0431\u043a\u0430, \u043f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430.", "en": "Something went wrong, please try again."},

    # ---- Telegram orqali kirish / shaxsiy kabinet ----
    "nav_kabinet_title": {"uz": "Shaxsiy kabinet", "ru": "\u041b\u0438\u0447\u043d\u044b\u0439 \u043a\u0430\u0431\u0438\u043d\u0435\u0442", "en": "My account"},
    "login_title": {"uz": "Telegram orqali kirish", "ru": "\u0412\u0445\u043e\u0434 \u0447\u0435\u0440\u0435\u0437 Telegram", "en": "Log in with Telegram"},
    "login_desc": {
        "uz": "Shaxsiy kabinetingizga kirish va Limit sotib olish uchun Telegram akkountingiz orqali tasdiqlang.",
        "ru": "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u0435 \u0447\u0435\u0440\u0435\u0437 \u0441\u0432\u043e\u0439 \u0430\u043a\u043a\u0430\u0443\u043d\u0442 Telegram, \u0447\u0442\u043e\u0431\u044b \u0432\u043e\u0439\u0442\u0438 \u0432 \u043b\u0438\u0447\u043d\u044b\u0439 \u043a\u0430\u0431\u0438\u043d\u0435\u0442 \u0438 \u043a\u0443\u043f\u0438\u0442\u044c \u041b\u0438\u043c\u0438\u0442.",
        "en": "Confirm with your Telegram account to access your dashboard and buy a Limit.",
    },
    "kabinet_title": {"uz": "Shaxsiy kabinet", "ru": "\u041b\u0438\u0447\u043d\u044b\u0439 \u043a\u0430\u0431\u0438\u043d\u0435\u0442", "en": "My account"},
    "kb_limit_title": {"uz": "Limit holati", "ru": "\u0421\u0442\u0430\u0442\u0443\u0441 \u041b\u0438\u043c\u0438\u0442\u0430", "en": "Limit status"},
    "kb_limit_active": {
        "uz": "\u2705 Limit {date} sanagacha faol",
        "ru": "\u2705 \u041b\u0438\u043c\u0438\u0442 \u0430\u043a\u0442\u0438\u0432\u0435\u043d \u0434\u043e {date}",
        "en": "\u2705 Limit active until {date}",
    },
    "kb_buy_limit": {"uz": "Limit sotib olish", "ru": "\u041a\u0443\u043f\u0438\u0442\u044c \u041b\u0438\u043c\u0438\u0442", "en": "Buy a Limit"},
    "kb_my_listings": {"uz": "Mening e'lonlarim", "ru": "\u041c\u043e\u0438 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f", "en": "My listings"},
    "kb_no_listings": {"uz": "Siz hali botda e'lon joylamagansiz.", "ru": "\u0412\u044b \u0435\u0449\u0451 \u043d\u0435 \u0440\u0430\u0437\u043c\u0435\u0441\u0442\u0438\u043b\u0438 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u0447\u0435\u0440\u0435\u0437 \u0431\u043e\u0442\u0430.", "en": "You haven't posted a listing via the bot yet."},
    "kb_col_addr": {"uz": "Manzil", "ru": "\u0410\u0434\u0440\u0435\u0441", "en": "Address"},
    "kb_col_price": {"uz": "Narxi", "ru": "\u0426\u0435\u043d\u0430", "en": "Price"},
    "kb_col_status": {"uz": "Holati", "ru": "\u0421\u0442\u0430\u0442\u0443\u0441", "en": "Status"},
    "kb_col_date": {"uz": "Sana", "ru": "\u0414\u0430\u0442\u0430", "en": "Date"},
    "kb_action_edit": {"uz": "Tahrirlash", "ru": "\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c", "en": "Edit"},
    "kb_action_close": {"uz": "Topshirildi deb belgilash", "ru": "\u041e\u0442\u043c\u0435\u0442\u0438\u0442\u044c \u043a\u0430\u043a \u0441\u0434\u0430\u043d\u043d\u043e\u0435", "en": "Mark as rented out"},
    "kb_action_delete": {"uz": "O'chirish", "ru": "\u0423\u0434\u0430\u043b\u0438\u0442\u044c", "en": "Delete"},
    "kb_save": {"uz": "Saqlash", "ru": "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c", "en": "Save"},
    "kb_cancel": {"uz": "Bekor qilish", "ru": "\u041e\u0442\u043c\u0435\u043d\u0430", "en": "Cancel"},
    "kb_confirm_close": {
        "uz": "Bu e'lonni topshirilgan (ijaraga berilgan) deb belgilaysizmi?",
        "ru": "\u041e\u0442\u043c\u0435\u0442\u0438\u0442\u044c \u044d\u0442\u043e \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u043a\u0430\u043a \u0441\u0434\u0430\u043d\u043d\u043e\u0435?",
        "en": "Mark this listing as rented out?",
    },
    "kb_confirm_delete": {
        "uz": "Bu e'lonni butunlay o'chirasizmi? Bu amalni ortga qaytarib bo'lmaydi.",
        "ru": "\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u044d\u0442\u043e \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u043d\u0430\u0432\u0441\u0435\u0433\u0434\u0430? \u042d\u0442\u043e \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u043d\u0435\u043b\u044c\u0437\u044f \u043e\u0442\u043c\u0435\u043d\u0438\u0442\u044c.",
        "en": "Delete this listing permanently? This cannot be undone.",
    },
    "kb_no_requests": {
        "uz": "Siz hali hech qanday so'rov yubormagansiz.",
        "ru": "\u0412\u044b \u043f\u043e\u043a\u0430 \u043d\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u043b\u0438 \u043d\u0438 \u043e\u0434\u043d\u043e\u0433\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0430.",
        "en": "You haven't sent any requests yet.",
    },
    "kb_request_viewing": {"uz": "Ko'rish vaqti so'rovi", "ru": "\u0417\u0430\u043f\u0440\u043e\u0441 \u043d\u0430 \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440", "en": "Viewing request"},
    "kb_request_inquiry": {"uz": "Xabar yuborildi", "ru": "\u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e", "en": "Message sent"},
    "kb_request_subarenda": {"uz": "Subarenda so'rovi", "ru": "\u0417\u0430\u043f\u0440\u043e\u0441 \u043d\u0430 \u0441\u0443\u0431\u0430\u0440\u0435\u043d\u0434\u0443", "en": "Sublease request"},
    "kb_request_status_new": {"uz": "Yangi", "ru": "\u041d\u043e\u0432\u044b\u0439", "en": "New"},
    "kb_request_status_seen": {"uz": "Ko'rib chiqildi", "ru": "\u0420\u0430\u0441\u0441\u043c\u043e\u0442\u0440\u0435\u043d\u043e", "en": "Reviewed"},
    "kb_request_status_pending": {"uz": "Kutilmoqda", "ru": "\u041e\u0436\u0438\u0434\u0430\u0435\u0442", "en": "Pending"},
    "kb_request_status_confirmed": {"uz": "Tasdiqlandi", "ru": "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043e", "en": "Confirmed"},
    "kb_request_status_declined": {"uz": "Rad etildi", "ru": "\u041e\u0442\u043a\u043b\u043e\u043d\u0435\u043d\u043e", "en": "Declined"},
    "status_pending": {"uz": "Ko'rib chiqilmoqda", "ru": "\u041d\u0430 \u0440\u0430\u0441\u0441\u043c\u043e\u0442\u0440\u0435\u043d\u0438\u0438", "en": "Under review"},
    "status_approved": {"uz": "Faol", "ru": "\u0410\u043a\u0442\u0438\u0432\u043d\u043e", "en": "Active"},
    "status_rejected": {"uz": "Rad etilgan", "ru": "\u041e\u0442\u043a\u043b\u043e\u043d\u0435\u043d\u043e", "en": "Rejected"},
    "status_expired": {"uz": "Topshirilgan", "ru": "\u0421\u0434\u0430\u043d\u043e", "en": "Rented out"},
    "kb_logout": {"uz": "Chiqish", "ru": "\u0412\u044b\u0439\u0442\u0438", "en": "Log out"},
    "kb_notifications_title": {"uz": "Bildirishnomalar", "ru": "\u0423\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u044f", "en": "Notifications"},
    "kb_favorites_title": {"uz": "Sevimlilarim", "ru": "\u0418\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0435", "en": "Favorites"},
    "kb_my_requests_title": {"uz": "Mening so'rovlarim", "ru": "\u041c\u043e\u0438 \u0437\u0430\u043f\u0440\u043e\u0441\u044b", "en": "My requests"},
    "kb_no_favorites": {"uz": "Hali hech qanday e'lonni saqlamadingiz.", "ru": "\u0412\u044b \u043f\u043e\u043a\u0430 \u043d\u0435 \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u043b\u0438 \u043d\u0438 \u043e\u0434\u043d\u043e\u0433\u043e \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f.", "en": "You haven't saved any listings yet."},
    "kb_support_title": {"uz": "Yordam kerakmi?", "ru": "\u041d\u0443\u0436\u043d\u0430 \u043f\u043e\u043c\u043e\u0449\u044c?", "en": "Need help?"},
    "kb_support_hint": {
        "uz": "Savolingiz yoki muammoyingiz bo'lsa, shu yerga yozing \u2014 tez orada javob beramiz.",
        "ru": "\u0415\u0441\u043b\u0438 \u0443 \u0432\u0430\u0441 \u0435\u0441\u0442\u044c \u0432\u043e\u043f\u0440\u043e\u0441 \u0438\u043b\u0438 \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u0430, \u043d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u0437\u0434\u0435\u0441\u044c \u2014 \u043c\u044b \u0441\u043a\u043e\u0440\u043e \u043e\u0442\u0432\u0435\u0442\u0438\u043c.",
        "en": "If you have a question or an issue, write here \u2014 we'll reply soon.",
    },
    "kb_support_placeholder": {"uz": "Xabaringizni yozing...", "ru": "\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u0432\u0430\u0448\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435...", "en": "Write your message..."},
    "kb_support_submit": {"uz": "Yuborish", "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c", "en": "Send"},
    "kb_support_sent": {"uz": "Xabaringiz yuborildi, tez orada javob beramiz!", "ru": "\u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e, \u0441\u043a\u043e\u0440\u043e \u043e\u0442\u0432\u0435\u0442\u0438\u043c!", "en": "Your message was sent, we'll reply soon!"},
    "kb_support_history_title": {"uz": "Sizning so'rovlaringiz", "ru": "\u0412\u0430\u0448\u0438 \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u044f", "en": "Your requests"},
    "kb_support_status_new": {"uz": "Kutilmoqda", "ru": "\u041e\u0436\u0438\u0434\u0430\u0435\u0442", "en": "Pending"},
    "kb_support_status_replied": {"uz": "Javob berildi", "ru": "\u041e\u0442\u0432\u0435\u0447\u0435\u043d\u043e", "en": "Replied"},
    "kb_support_reply_label": {"uz": "Admin javobi:", "ru": "\u041e\u0442\u0432\u0435\u0442 \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430:", "en": "Admin's reply:"},
    "kb_back": {"uz": "\u2190 Kabinetga qaytish", "ru": "\u2190 \u041d\u0430\u0437\u0430\u0434 \u0432 \u043a\u0430\u0431\u0438\u043d\u0435\u0442", "en": "\u2190 Back to my account"},
    "kb_pay_hint": {
        "uz": "To'lovni shu kartaga o'tkazing, so'ng chek rasmini yuklang. Admin tekshirib, tasdiqlagach Limitingiz avtomatik faollashadi.",
        "ru": "\u041f\u0435\u0440\u0435\u0432\u0435\u0434\u0438\u0442\u0435 \u043e\u043f\u043b\u0430\u0442\u0443 \u043d\u0430 \u044d\u0442\u0443 \u043a\u0430\u0440\u0442\u0443, \u0437\u0430\u0442\u0435\u043c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 \u0441\u043a\u0440\u0438\u043d\u0448\u043e\u0442 \u0447\u0435\u043a\u0430. \u041f\u043e\u0441\u043b\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u0430\u0434\u043c\u0438\u043d\u043e\u043c \u041b\u0438\u043c\u0438\u0442 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u0443\u0435\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438.",
        "en": "Transfer payment to this card, then upload a screenshot of the receipt. Your Limit activates automatically once an admin approves it.",
    },
    "kb_upload_receipt": {"uz": "To'lov chekini yuklash", "ru": "\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0447\u0435\u043a \u043e\u043f\u043b\u0430\u0442\u044b", "en": "Upload payment receipt"},
    "kb_submit_receipt": {"uz": "Yuborish", "ru": "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c", "en": "Submit"},
    "kb_receipt_sent": {
        "uz": "Chekingiz qabul qilindi! Admin tekshirgach, Telegram botingizga xabar keladi va Limit faollashadi.",
        "ru": "\u0427\u0435\u043a \u043f\u0440\u0438\u043d\u044f\u0442! \u041f\u043e\u0441\u043b\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u0430\u0434\u043c\u0438\u043d\u043e\u043c \u0432\u0430\u043c \u043f\u0440\u0438\u0434\u0451\u0442 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0432 Telegram-\u0431\u043e\u0442, \u0438 \u041b\u0438\u043c\u0438\u0442 \u0431\u0443\u0434\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d.",
        "en": "Your receipt was received! You'll get a Telegram message once an admin approves it, and your Limit will activate.",
    },
    "kb_error": {"uz": "Xatolik yuz berdi, qaytadan urinib ko'ring.", "ru": "\u041f\u0440\u043e\u0438\u0437\u043e\u0448\u043b\u0430 \u043e\u0448\u0438\u0431\u043a\u0430, \u043f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430.", "en": "Something went wrong, please try again."},
    "sum": {"uz": "so'm", "ru": "\u0441\u0443\u043c", "en": "UZS"},
    "days": {"uz": "kun", "ru": "\u0434\u043d\u0435\u0439", "en": "days"},
    "sidebar_cta_login": {"uz": "Telegram orqali kirib ko'rish", "ru": "\u0412\u043e\u0439\u0442\u0438 \u0447\u0435\u0440\u0435\u0437 Telegram, \u0447\u0442\u043e\u0431\u044b \u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c", "en": "Log in with Telegram to view"},
    "sidebar_cta_buy_limit": {"uz": "Limit sotib olib ko'rish", "ru": "\u041a\u0443\u043f\u0438\u0442\u044c \u041b\u0438\u043c\u0438\u0442, \u0447\u0442\u043e\u0431\u044b \u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c", "en": "Buy a Limit to view"},
    "sidebar_note_limit_active": {"uz": "Limitingiz faol \u2014 raqamga bemalol qo'ng'iroq qiling", "ru": "\u0412\u0430\u0448 \u041b\u0438\u043c\u0438\u0442 \u0430\u043a\u0442\u0438\u0432\u0435\u043d \u2014 \u0437\u0432\u043e\u043d\u0438\u0442\u0435 \u043f\u043e \u043d\u043e\u043c\u0435\u0440\u0443", "en": "Your Limit is active \u2014 feel free to call"},
    "sidebar_note_web_limit": {
        "uz": "Uy egasi raqamini faqat faol Limitga ega foydalanuvchilar ko'radi.",
        "ru": "\u041d\u043e\u043c\u0435\u0440 \u0432\u043b\u0430\u0434\u0435\u043b\u044c\u0446\u0430 \u0432\u0438\u0434\u044f\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0438 \u0441 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u043c \u041b\u0438\u043c\u0438\u0442\u043e\u043c.",
        "en": "Only users with an active Limit can see the owner's phone number.",
    },
    "sidebar_note_via_bot": {"uz": "Yoki bot orqali ko'ring", "ru": "\u0418\u043b\u0438 \u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0438\u0442\u0435 \u0447\u0435\u0440\u0435\u0437 \u0431\u043e\u0442\u0430", "en": "Or view via the bot"},
    "sidebar_cta_view_phone": {"uz": "Uy egasi raqamini ko'rish", "ru": "\u041f\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c \u043d\u043e\u043c\u0435\u0440 \u0432\u043b\u0430\u0434\u0435\u043b\u044c\u0446\u0430", "en": "View owner's phone number"},
    "paywall_no_limit_msg": {
        "uz": "Kechirasiz, uy egasi raqamini ko'rish uchun sizda Limit mavjud emas. Uy egalari raqamlarini ko'rish uchun Bir oylik limit sotib oling:",
        "ru": "\u0418\u0437\u0432\u0438\u043d\u0438\u0442\u0435, \u0443 \u0432\u0430\u0441 \u043d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0433\u043e \u041b\u0438\u043c\u0438\u0442\u0430 \u0434\u043b\u044f \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u0430 \u043d\u043e\u043c\u0435\u0440\u0430 \u0432\u043b\u0430\u0434\u0435\u043b\u044c\u0446\u0430. \u0427\u0442\u043e\u0431\u044b \u0432\u0438\u0434\u0435\u0442\u044c \u043d\u043e\u043c\u0435\u0440\u0430 \u0432\u043b\u0430\u0434\u0435\u043b\u044c\u0446\u0435\u0432, \u043a\u0443\u043f\u0438\u0442\u0435 \u043c\u0435\u0441\u044f\u0447\u043d\u044b\u0439 \u041b\u0438\u043c\u0438\u0442:",
        "en": "Sorry, you don't have an active Limit to view the owner's phone number. To see owners' phone numbers, buy a one-month Limit:",
    },
    "card_brand": {"uz": "TO'LOV KARTASI", "ru": "\u041f\u041b\u0410\u0422\u0401\u0416\u041d\u0410\u042f \u041a\u0410\u0420\u0422\u0410", "en": "PAYMENT CARD"},
    "card_holder_label": {"uz": "Karta egasi", "ru": "\u0414\u0435\u0440\u0436\u0430\u0442\u0435\u043b\u044c \u043a\u0430\u0440\u0442\u044b", "en": "Card holder"},
    "fav_save": {"uz": "Saqlash", "ru": "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c", "en": "Save"},
    "fav_saved": {"uz": "Saqlangan", "ru": "\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e", "en": "Saved"},
    "phone_check_title": {"uz": "Raqamni tekshirish", "ru": "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043d\u043e\u043c\u0435\u0440", "en": "Check a phone number"},
    "phone_check_desc": {
        "uz": "Shubhali telefon raqami bormi? Shu yerda tekshiring \u2014 bizning tizimda bloklangan bo'lsa, darhol bilib olasiz.",
        "ru": "\u0415\u0441\u0442\u044c \u043f\u043e\u0434\u043e\u0437\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0439 \u043d\u043e\u043c\u0435\u0440 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0430? \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0437\u0434\u0435\u0441\u044c \u2014 \u0435\u0441\u043b\u0438 \u043e\u043d \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d \u0432 \u043d\u0430\u0448\u0435\u0439 \u0441\u0438\u0441\u0442\u0435\u043c\u0435, \u0432\u044b \u0441\u0440\u0430\u0437\u0443 \u0443\u0437\u043d\u0430\u0435\u0442\u0435.",
        "en": "Have a suspicious phone number? Check it here \u2014 if it's blocked in our system, you'll know right away.",
    },
    "phone_check_placeholder": {"uz": "+998 90 123 45 67", "ru": "+998 90 123 45 67", "en": "+998 90 123 45 67"},
    "phone_check_btn": {"uz": "Tekshirish", "ru": "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c", "en": "Check"},
    "phone_check_checking": {"uz": "Tekshirilmoqda...", "ru": "\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u0442\u0441\u044f...", "en": "Checking..."},
    "phone_check_invalid": {"uz": "Raqam formati noto'g'ri. Masalan: +998901234567", "ru": "\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u043d\u043e\u043c\u0435\u0440\u0430. \u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: +998901234567", "en": "Invalid phone format. Example: +998901234567"},
    "phone_check_blocked": {
        "uz": "Diqqat! Bu raqam bizning tizimda BLOKLANGAN.",
        "ru": "\u0412\u043d\u0438\u043c\u0430\u043d\u0438\u0435! \u042d\u0442\u043e\u0442 \u043d\u043e\u043c\u0435\u0440 \u0417\u0410\u0411\u041b\u041e\u041a\u0418\u0420\u041e\u0412\u0410\u041d \u0432 \u043d\u0430\u0448\u0435\u0439 \u0441\u0438\u0441\u0442\u0435\u043c\u0435.",
        "en": "Warning! This number is BLOCKED in our system.",
    },
    "phone_check_ok": {"uz": "Bu raqam bloklanmagan.", "ru": "\u042d\u0442\u043e\u0442 \u043d\u043e\u043c\u0435\u0440 \u043d\u0435 \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d.", "en": "This number is not blocked."},
    "phone_check_error": {"uz": "Xatolik yuz berdi, qayta urinib ko'ring.", "ru": "\u041f\u0440\u043e\u0438\u0437\u043e\u0448\u043b\u0430 \u043e\u0448\u0438\u0431\u043a\u0430, \u043f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430.", "en": "Something went wrong, please try again."},

    # ---- SEO: sahifa sarlavhalari va tavsiflari (har bir til uchun alohida) ----
    "seo_home_title": {
        "uz": "Ijaraga uy, kvartira \u2014 Toshkentda maklersiz ijara | Ijaraga Uylar Maklersiz",
        "ru": "\u0410\u0440\u0435\u043d\u0434\u0430 \u043a\u0432\u0430\u0440\u0442\u0438\u0440\u044b \u0438 \u0434\u043e\u043c\u0430 \u0432 \u0422\u0430\u0448\u043a\u0435\u043d\u0442\u0435 \u0431\u0435\u0437 \u043f\u043e\u0441\u0440\u0435\u0434\u043d\u0438\u043a\u043e\u0432 | Ijaraga Uylar Maklersiz",
        "en": "Apartments & Houses for Rent in Tashkent \u2014 No Agent Fees | Ijaraga Uylar Maklersiz",
    },
    "seo_home_desc": {
        "uz": "Toshkentda ijaraga uy va kvartira \u2014 maklersiz, to'g'ridan-to'g'ri uy egasidan. Hozirda {active} ta faol e'lon: kunlik, uzoq muddatli, dacha va mehmonxona uchun xonalar.",
        "ru": "\u0410\u0440\u0435\u043d\u0434\u0430 \u043a\u0432\u0430\u0440\u0442\u0438\u0440 \u0438 \u0434\u043e\u043c\u043e\u0432 \u0432 \u0422\u0430\u0448\u043a\u0435\u043d\u0442\u0435 \u043d\u0430\u043f\u0440\u044f\u043c\u0443\u044e \u043e\u0442 \u0441\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043d\u0438\u043a\u0430, \u0431\u0435\u0437 \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u0438. \u0421\u0435\u0439\u0447\u0430\u0441 {active} \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0439: \u043f\u043e\u0441\u0443\u0442\u043e\u0447\u043d\u043e, \u0434\u043e\u043b\u0433\u043e\u0441\u0440\u043e\u0447\u043d\u043e, \u0434\u0430\u0447\u0438 \u0438 \u0433\u043e\u0441\u0442\u0435\u0432\u044b\u0435 \u043a\u043e\u043c\u043d\u0430\u0442\u044b.",
        "en": "Rent apartments and houses in Tashkent directly from the owner \u2014 zero agent commission. {active} active listings now: daily, long-term, cottages and guest rooms.",
    },
    "seo_district_title": {
        "uz": "{district}da ijaraga uylar \u2014 arzon va maklersiz kvartiralar | Ijaraga Uylar",
        "ru": "\u0410\u0440\u0435\u043d\u0434\u0430 \u0436\u0438\u043b\u044c\u044f \u0432 \u0440\u0430\u0439\u043e\u043d\u0435 {district} \u2014 \u0431\u0435\u0437 \u043f\u043e\u0441\u0440\u0435\u0434\u043d\u0438\u043a\u043e\u0432 | Ijaraga Uylar",
        "en": "Apartments for Rent in {district}, Tashkent \u2014 No Agent Fees | Ijaraga Uylar",
    },
    "seo_district_desc": {
        "uz": "Toshkent {district} tumanida ijaraga beriladigan uy va kvartiralar \u2014 to'g'ridan-to'g'ri uy egasidan, maklersiz. Hozirda {active} ta faol e'lon.",
        "ru": "\u0410\u0440\u0435\u043d\u0434\u0430 \u043a\u0432\u0430\u0440\u0442\u0438\u0440 \u0438 \u0434\u043e\u043c\u043e\u0432 \u0432 \u0440\u0430\u0439\u043e\u043d\u0435 {district} (\u0422\u0430\u0448\u043a\u0435\u043d\u0442) \u043d\u0430\u043f\u0440\u044f\u043c\u0443\u044e \u043e\u0442 \u0441\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043d\u0438\u043a\u0430, \u0431\u0435\u0437 \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u0438. \u0421\u0435\u0439\u0447\u0430\u0441 {active} \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0439.",
        "en": "Rent apartments and houses in {district}, Tashkent \u2014 directly from the owner, zero agent commission. {active} active listings now.",
    },
    "seo_district_rooms_title": {
        "uz": "{district}da {xona} xonali ijaraga uylar | Ijaraga Uylar",
        "ru": "{xona}-\u043a\u043e\u043c\u043d\u0430\u0442\u043d\u044b\u0435 \u043a\u0432\u0430\u0440\u0442\u0438\u0440\u044b \u0432 \u0430\u0440\u0435\u043d\u0434\u0443 \u0432 \u0440\u0430\u0439\u043e\u043d\u0435 {district} | Ijaraga Uylar",
        "en": "{xona}-Room Apartments for Rent in {district}, Tashkent | Ijaraga Uylar",
    },
    "seo_district_rooms_desc": {
        "uz": "Toshkent {district} tumanida {xona} xonali ijaraga beriladigan uy va kvartiralar \u2014 maklersiz, to'g'ridan-to'g'ri uy egasidan. Hozirda {active} ta faol e'lon.",
        "ru": "{xona}-\u043a\u043e\u043c\u043d\u0430\u0442\u043d\u044b\u0435 \u043a\u0432\u0430\u0440\u0442\u0438\u0440\u044b \u0432 \u0430\u0440\u0435\u043d\u0434\u0443 \u0432 \u0440\u0430\u0439\u043e\u043d\u0435 {district} \u2014 \u0431\u0435\u0437 \u043f\u043e\u0441\u0440\u0435\u0434\u043d\u0438\u043a\u043e\u0432. \u0421\u0435\u0439\u0447\u0430\u0441 {active} \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0439.",
        "en": "{xona}-room apartments for rent in {district}, Tashkent \u2014 no agent fees, directly from the owner. {active} active listings now.",
    },
    "district_hero_title": {
        "uz": "{district}da ijaraga uylar va kvartiralar",
        "ru": "\u0410\u0440\u0435\u043d\u0434\u0430 \u0436\u0438\u043b\u044c\u044f \u0432 \u0440\u0430\u0439\u043e\u043d\u0435 {district}",
        "en": "Apartments for Rent in {district}",
    },
    "browse_districts_title": {"uz": "Tumanlar bo'yicha", "ru": "\u041f\u043e \u0440\u0430\u0439\u043e\u043d\u0430\u043c", "en": "Browse by district"},
    "seo_listing_title": {"uz": "{addr} \u2014 ijaraga, {price} | Ijaraga Uylar", "ru": "{addr} \u2014 \u0430\u0440\u0435\u043d\u0434\u0430, {price} | Ijaraga Uylar", "en": "{addr} \u2014 for rent, {price} | Ijaraga Uylar"},
    "seo_listing_desc": {
        "uz": "{xona}. Narxi: {price}. Toshkentda maklersiz ijara \u2014 to'g'ridan-to'g'ri uy egasi bilan bog'laning, komissiya yo'q.",
        "ru": "{xona}. \u0426\u0435\u043d\u0430: {price}. \u0410\u0440\u0435\u043d\u0434\u0430 \u0432 \u0422\u0430\u0448\u043a\u0435\u043d\u0442\u0435 \u0431\u0435\u0437 \u043f\u043e\u0441\u0440\u0435\u0434\u043d\u0438\u043a\u043e\u0432 \u2014 \u0441\u0432\u044f\u0436\u0438\u0442\u0435\u0441\u044c \u043d\u0430\u043f\u0440\u044f\u043c\u0443\u044e \u0441 \u0441\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043d\u0438\u043a\u043e\u043c, \u0431\u0435\u0437 \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u0438.",
        "en": "{xona}. Price: {price}. Commission-free rental in Tashkent \u2014 connect directly with the owner, no agent fees.",
    },
    "seo_subarenda_title": {
        "uz": "Subarenda \u2014 uyingizni ishonchli boshqaruvga bering | Ijaraga Uylar",
        "ru": "\u0421\u0443\u0431\u0430\u0440\u0435\u043d\u0434\u0430 \u2014 \u0434\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0432\u0430\u0448\u0435\u0439 \u043d\u0435\u0434\u0432\u0438\u0436\u0438\u043c\u043e\u0441\u0442\u044c\u044e | Ijaraga Uylar",
        "en": "Sublease Program \u2014 Trusted Property Management | Ijaraga Uylar",
    },
    "seo_subarenda_desc": {
        "uz": "Uyingizni bizga uzoq muddatli ijaraga bering \u2014 biz ijarachini topamiz, boshqaramiz va har oy kafolatlangan to'lovni amalga oshiramiz.",
        "ru": "\u0421\u0434\u0430\u0439\u0442\u0435 \u043d\u0435\u0434\u0432\u0438\u0436\u0438\u043c\u043e\u0441\u0442\u044c \u043d\u0430\u043c \u0432 \u0434\u043e\u043b\u0433\u043e\u0441\u0440\u043e\u0447\u043d\u0443\u044e \u0441\u0443\u0431\u0430\u0440\u0435\u043d\u0434\u0443 \u2014 \u043c\u044b \u043d\u0430\u0439\u0434\u0451\u043c \u0430\u0440\u0435\u043d\u0434\u0430\u0442\u043e\u0440\u0430, \u0432\u043e\u0437\u044c\u043c\u0451\u043c \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u043d\u0430 \u0441\u0435\u0431\u044f \u0438 \u043e\u0431\u0435\u0441\u043f\u0435\u0447\u0438\u043c \u0433\u0430\u0440\u0430\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u0443\u044e \u0435\u0436\u0435\u043c\u0435\u0441\u044f\u0447\u043d\u0443\u044e \u043e\u043f\u043b\u0430\u0442\u0443.",
        "en": "Lease your property to us long-term \u2014 we find the tenant, manage everything, and pay you a guaranteed monthly amount.",
    },
    "seo_post_title": {
        "uz": "E'lon joylash \u2014 uyingizni bepul reklama qiling | Ijaraga Uylar",
        "ru": "\u0420\u0430\u0437\u043c\u0435\u0441\u0442\u0438\u0442\u044c \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u043e\u0431 \u0430\u0440\u0435\u043d\u0434\u0435 | Ijaraga Uylar",
        "en": "Post a Rental Listing | Ijaraga Uylar",
    },
    "seo_post_desc": {
        "uz": "Uyingizni ijaraga berasizmi? Veb-saytdan to'g'ridan-to'g'ri, ro'yxatdan o'tmasdan e'lon joylang. Moderatsiyadan so'ng Telegram kanalimiz va saytimizda chiqadi.",
        "ru": "\u0421\u0434\u0430\u0451\u0442\u0435 \u0436\u0438\u043b\u044c\u0451 \u0432 \u0430\u0440\u0435\u043d\u0434\u0443? \u0420\u0430\u0437\u043c\u0435\u0441\u0442\u0438\u0442\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435 \u043f\u0440\u044f\u043c\u043e \u043d\u0430 \u0441\u0430\u0439\u0442\u0435, \u0431\u0435\u0437 \u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u0438. \u041f\u043e\u0441\u043b\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u043e\u043d\u043e \u043f\u043e\u044f\u0432\u0438\u0442\u0441\u044f \u0432 \u043d\u0430\u0448\u0435\u043c Telegram-\u043a\u0430\u043d\u0430\u043b\u0435 \u0438 \u043d\u0430 \u0441\u0430\u0439\u0442\u0435.",
        "en": "Renting out your place? Post your listing directly on the site, no account needed. After moderation it appears on our Telegram channel and website.",
    },
}


def get_lang(request: Request) -> str:
    lang = request.query_params.get("lang") or request.cookies.get("lang") or DEFAULT_LANG
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def t(lang: str, key: str, **kwargs) -> str:
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    return text.format(**kwargs) if kwargs else text


def lang_switcher_html(current_path: str, lang: str) -> str:
    """Bayroqli til tanlash: joriy til bayrog'i tugma sifatida ko'rinadi,
    bosilganda faqat QOLGAN tillar (bayroq + nom bilan) ochiladi."""
    current_flag = LANG_FLAGS.get(lang, LANG_FLAGS[DEFAULT_LANG])
    options = "".join(
        f'<a href="/set-lang/{code}?next={urllib.parse.quote(current_path)}" class="lang-option">'
        f'<span class="lang-flag">{LANG_FLAGS[code]}</span>{LANG_META[code]}</a>'
        for code in SUPPORTED_LANGS if code != lang
    )
    return f"""<div class="lang-switcher">
  <button type="button" class="lang-current" onclick="event.stopPropagation();this.closest('.lang-switcher').classList.toggle('open')" aria-label="Til / Language">{current_flag}</button>
  <div class="lang-menu">{options}</div>
</div>"""


@router.get("/set-lang/{lang}")
def set_lang(lang: str, next: str = "/"):
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    if not next.startswith("/"):
        next = "/"
    resp = RedirectResponse(url=next, status_code=307)
    resp.set_cookie("lang", lang, max_age=31536000, path="/", samesite="lax")
    return resp


def render_head(title: str, description: str, canonical_path: str, og_image: str = "", lang: str = DEFAULT_LANG, noindex: bool = False) -> str:
    canonical = f"{SITE_URL}{canonical_path}" if SITE_URL else canonical_path
    if not og_image and SITE_URL:
        og_image = f"{SITE_URL}/logo.png"
    alt_links = "".join(
        f'<link rel="alternate" hreflang="{code}" href="{canonical}{"&" if "?" in canonical else "?"}lang={code}">'
        for code in SUPPORTED_LANGS
    )
    # x-default: Google'ga qaysi tilga to'g'ri kelmagan qidiruvchilar uchun
    # standart (o'zbek) versiyani ko'rsatishni bildiradi.
    alt_links += f'<link rel="alternate" hreflang="x-default" href="{canonical}">'
    robots_content = "noindex,nofollow" if noindex else "index,follow"
    verification_tags = ""
    if GOOGLE_SITE_VERIFICATION:
        verification_tags += f'<meta name="google-site-verification" content="{GOOGLE_SITE_VERIFICATION}">'
    if YANDEX_VERIFICATION:
        verification_tags += f'<meta name="yandex-verification" content="{YANDEX_VERIFICATION}">'
    return f"""<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="robots" content="{robots_content}">
<link rel="canonical" href="{canonical}">
{alt_links}
{verification_tags}
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{og_image}">
<meta property="og:url" content="{canonical}">
<meta property="og:locale" content="{lang}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#FF3B5C">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/site.css?v={CSS_VERSION}">"""


def render_header(lang: str = DEFAULT_LANG, current_path: str = "/") -> str:
    logo = "/logo.png"
    switcher = lang_switcher_html(current_path, lang)
    return f"""<header class="site-header">
  <div class="header-inner">
    <a href="/" class="brand"><img src="{logo}" alt="{SITE_NAME}"> {BRAND_SHORT}</a>
    <nav class="main-nav">
      <a href="/" class="nav-link">{t(lang,'nav_home')}</a>
      <a href="/subarenda" class="nav-link">{t(lang,'nav_subarenda')}</a>
      <a href="/xarita" class="nav-link">{icon('map', 16)} {t(lang,'nav_map_title')}</a>
      {switcher}
      <a href="/kabinet" class="nav-link nav-account-link" title="{t(lang,'nav_kabinet_title')}">{icon('user', 17)} {t(lang,'nav_account_label')}</a>
      <a href="/elon-joylash" class="btn-cta">{icon('sparkle', 14)} {t(lang,'nav_post_cta')}</a>
    </nav>
    <button class="mobile-menu-btn" onclick="toggleMobileMenu()" aria-label="Menyu">{icon('menu', 20)}</button>
  </div>
  <div class="mobile-menu" id="mobileMenu">
    <a href="/">{icon('home', 17)} {t(lang,'nav_home')}</a>
    <a href="/elon-joylash">{icon('sparkle', 17)} {t(lang,'mobile_post')}</a>
    <a href="/xarita">{icon('map', 17)} {t(lang,'nav_map_title')}</a>
    <a href="/subarenda">{icon('coin', 17)} {t(lang,'nav_subarenda')}</a>
    <a href="/kabinet">{icon('user', 17)} {t(lang,'nav_account_label')}</a>
    <div class="mobile-lang-label">{LANG_META[lang]}</div>
    {switcher}
  </div>
</header>
<script>
function toggleMobileMenu() {{
  document.getElementById('mobileMenu').classList.toggle('open');
}}
async function toggleFavorite(listingId, btn) {{
  try {{
    const res = await fetch('/api/favorites/toggle', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{listing_id: listingId}}),
    }});
    if (res.status === 401) {{
      window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
      return;
    }}
    if (!res.ok) return;
    const data = await res.json();
    btn.classList.toggle('active', !!data.favorited);
  }} catch (err) {{ /* jimgina e'tiborsiz qoldiriladi - tarmoq muammosi */ }}
}}
document.addEventListener('click', function() {{
  document.querySelectorAll('.lang-switcher.open').forEach(function(el) {{ el.classList.remove('open'); }});
}});
// MUHIM: brauzerning "orqaga" tugmasi bosilganda sahifa bfcache'dan
// (avvalgi holatida "muzlatilgan" holda) tiklanishi mumkin - bu holda
// mobil menyu ochiq qolib ketishi yoki body scroll qulflangan holda
// qolib ketishi mumkin edi. Shu narsani har safar tuzatib qo'yamiz.
window.addEventListener('pageshow', function(event) {{
  const menu = document.getElementById('mobileMenu');
  if (menu) menu.classList.remove('open');
  document.body.style.overflow = '';
  document.documentElement.style.overflow = '';
  const lb = document.getElementById('lightbox');
  if (lb) lb.classList.remove('open');
  document.querySelectorAll('.lang-switcher.open').forEach(function(el) {{ el.classList.remove('open'); }});
}});
</script>"""


def render_footer(lang: str = DEFAULT_LANG) -> str:
    bot_link = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "#"
    channel_link = f"https://t.me/{CHANNEL_USERNAME}" if CHANNEL_USERNAME else "#"
    year = datetime.now().year
    logo = "/logo.png"
    return f"""<footer class="site-footer">
  <div class="wrap">
    <div class="footer-inner">
      <div class="footer-col footer-col-brand">
        <div class="footer-brand"><img src="{logo}" alt="{SITE_NAME}"> {BRAND_SHORT}</div>
        <div class="footer-tagline">{t(lang,'footer_tagline')}</div>
      </div>
      <div class="footer-col">
        <div class="footer-col-title">{t(lang,'footer_nav_title')}</div>
        <a href="/">{t(lang,'nav_home')}</a>
        <a href="/elon-joylash">{t(lang,'mobile_post')}</a>
        <a href="/xarita">{t(lang,'nav_map_title')}</a>
        <a href="/subarenda">{t(lang,'nav_subarenda')}</a>
        <a href="/kabinet">{t(lang,'nav_account_label')}</a>
      </div>
      <div class="footer-col">
        <div class="footer-col-title">{t(lang,'footer_social_title')}</div>
        <a href="{channel_link}" target="_blank">{icon('send', 15)} {t(lang,'nav_channel_title')}</a>
        <a href="{bot_link}" target="_blank">{icon('phone', 14)} {t(lang,'nav_bot_title')}</a>
        <a href="{INSTAGRAM_URL}" target="_blank">{icon('instagram', 15)} Instagram</a>
      </div>
    </div>
    <div class="footer-bottom">&copy; {year} {SITE_NAME}. {t(lang,'footer_rights')}</div>
  </div>
</footer>
{render_ai_chat_widget(lang)}"""


def render_ai_chat_widget(lang: str = DEFAULT_LANG) -> str:
    """Butun saytda (footer orqali) ko'rinadigan suzuvchi AI chat vidjeti.
    Orqa tarafi (/api/ai-chat, web/api.py) common/ai_agent.py'dagi bot
    Concierge bilan BIR XIL mantiqni ishlatadi. AI o'chirilgan bo'lsa ham
    tugma ko'rinadi - ochilganda mos xabar ko'rsatiladi (botdagi bilan bir
    xil "graceful degrade" tamoyili)."""
    return f"""<div id="ai-chat-widget">
  <button id="ai-chat-toggle" type="button" aria-label="{t(lang,'ai_chat_title')}">\U0001F916</button>
  <div id="ai-chat-panel" class="ai-chat-hidden">
    <div class="ai-chat-header">
      <span>\U0001F916 {t(lang,'ai_chat_title')}</span>
      <button id="ai-chat-close" type="button" aria-label="close">&times;</button>
    </div>
    <div id="ai-chat-messages"></div>
    <div class="ai-chat-typing ai-chat-hidden" id="ai-chat-typing"><span></span><span></span><span></span></div>
    <div class="ai-chat-input-row">
      <input id="ai-chat-input" type="text" placeholder="{t(lang,'ai_chat_placeholder')}" maxlength="500" autocomplete="off">
      <button id="ai-chat-send" type="button" aria-label="send">\U0001F680</button>
    </div>
  </div>
</div>
<style>
#ai-chat-widget {{ position: fixed; right: 18px; bottom: 18px; z-index: 200; }}
#ai-chat-toggle {{
  width: 56px; height: 56px; border-radius: 50%; border: none; cursor: pointer;
  background: var(--brand); color: #fff; font-size: 24px; box-shadow: var(--shadow-lg);
  display: flex; align-items: center; justify-content: center; transition: transform .15s;
}}
#ai-chat-toggle:hover {{ transform: scale(1.06); }}
#ai-chat-panel {{
  position: absolute; right: 0; bottom: 68px; width: 340px; max-width: calc(100vw - 32px);
  height: 460px; max-height: calc(100vh - 120px); background: #fff; border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg); border: 1px solid var(--line); display: flex; flex-direction: column;
  overflow: hidden;
}}
.ai-chat-hidden {{ display: none !important; }}
.ai-chat-header {{
  background: var(--brand); color: #fff; padding: 14px 16px; font-weight: 700; font-size: 14.5px;
  display: flex; align-items: center; justify-content: space-between;
}}
.ai-chat-header button {{ background: none; border: none; color: #fff; font-size: 20px; cursor: pointer; line-height: 1; }}
#ai-chat-messages {{ flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }}
.ai-chat-bubble {{ max-width: 84%; padding: 9px 13px; border-radius: var(--radius); font-size: 13.5px; line-height: 1.45; white-space: pre-wrap; word-break: break-word; }}
.ai-chat-bubble.user {{ align-self: flex-end; background: var(--brand); color: #fff; border-bottom-right-radius: 4px; }}
.ai-chat-bubble.ai {{ align-self: flex-start; background: var(--bg-soft); color: var(--ink); border-bottom-left-radius: 4px; }}
.ai-chat-bubble.ai a {{ color: var(--brand-dark); font-weight: 600; }}
.ai-chat-typing {{ padding: 0 14px 8px; display: flex; gap: 4px; }}
.ai-chat-typing span {{ width: 6px; height: 6px; border-radius: 50%; background: var(--muted); animation: aiTypingBlink 1.2s infinite ease-in-out; }}
.ai-chat-typing span:nth-child(2) {{ animation-delay: .2s; }}
.ai-chat-typing span:nth-child(3) {{ animation-delay: .4s; }}
@keyframes aiTypingBlink {{ 0%, 80%, 100% {{ opacity: .25; }} 40% {{ opacity: 1; }} }}
.ai-chat-input-row {{ display: flex; gap: 8px; padding: 10px; border-top: 1px solid var(--line); }}
.ai-chat-input-row input {{
  flex: 1; border: 1px solid var(--line); border-radius: var(--radius-pill); padding: 9px 14px;
  font-size: 13.5px; outline: none; font-family: inherit;
}}
.ai-chat-input-row input:focus {{ border-color: var(--brand); }}
.ai-chat-input-row button {{
  width: 38px; height: 38px; border-radius: 50%; border: none; background: var(--brand); color: #fff;
  font-size: 15px; cursor: pointer; flex-shrink: 0;
}}
@media (max-width: 640px) {{
  #ai-chat-widget {{ right: 12px; bottom: 12px; }}
  #ai-chat-panel {{ width: calc(100vw - 24px); height: calc(100vh - 140px); bottom: 64px; }}
}}
</style>
<script>
(function() {{
  var LANG = {json.dumps(lang)};
  var STR = {{
    disabled: {json.dumps(t(lang, 'ai_chat_disabled'))},
    error: {json.dumps(t(lang, 'ai_chat_error'))},
    rateLimited: {json.dumps(t(lang, 'ai_chat_rate_limited'))},
    welcome: {json.dumps(t(lang, 'ai_chat_welcome'))}
  }};
  var toggle = document.getElementById('ai-chat-toggle');
  var panel = document.getElementById('ai-chat-panel');
  var closeBtn = document.getElementById('ai-chat-close');
  var messagesEl = document.getElementById('ai-chat-messages');
  var typingEl = document.getElementById('ai-chat-typing');
  var input = document.getElementById('ai-chat-input');
  var sendBtn = document.getElementById('ai-chat-send');
  var opened = false;
  var sending = false;

  function sessionId() {{
    try {{
      var id = localStorage.getItem('ai_chat_session');
      if (!id) {{
        id = (crypto.randomUUID ? crypto.randomUUID() : (Date.now() + '-' + Math.random().toString(36).slice(2)));
        localStorage.setItem('ai_chat_session', id);
      }}
      return id;
    }} catch (e) {{
      return 'anon-' + Math.random().toString(36).slice(2);
    }}
  }}

  function escapeHtml(s) {{
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }}

  function linkify(escaped) {{
    return escaped.replace(/(https?:\\/\\/[^\\s<]+)/g, function(url) {{
      var trail = '';
      while (url.length && /[*_.,!?:;)\\]]/.test(url.slice(-1))) {{
        trail = url.slice(-1) + trail;
        url = url.slice(0, -1);
      }}
      return '<a href="' + url + '" target="_blank" rel="noopener">' + url + '</a>' + trail;
    }});
  }}

  function addBubble(text, who) {{
    var b = document.createElement('div');
    b.className = 'ai-chat-bubble ' + who;
    b.innerHTML = linkify(escapeHtml(text));
    messagesEl.appendChild(b);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }}

  function open() {{
    panel.classList.remove('ai-chat-hidden');
    if (!opened) {{
      opened = true;
      addBubble(STR.welcome, 'ai');
      input.focus();
    }}
  }}

  toggle.addEventListener('click', function() {{
    if (panel.classList.contains('ai-chat-hidden')) open();
    else panel.classList.add('ai-chat-hidden');
  }});
  closeBtn.addEventListener('click', function() {{ panel.classList.add('ai-chat-hidden'); }});

  async function send() {{
    var msg = input.value.trim();
    if (!msg || sending) return;
    sending = true;
    addBubble(msg, 'user');
    input.value = '';
    typingEl.classList.remove('ai-chat-hidden');
    try {{
      var res = await fetch('/api/ai-chat', {{
        method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ session_id: sessionId(), message: msg, lang: LANG }})
      }});
      var data = await res.json();
      typingEl.classList.add('ai-chat-hidden');
      if (data.disabled) addBubble(STR.disabled, 'ai');
      else if (data.rate_limited) addBubble(STR.rateLimited, 'ai');
      else if (!data.reply) addBubble(STR.error, 'ai');
      else addBubble(data.reply, 'ai');
    }} catch (e) {{
      typingEl.classList.add('ai-chat-hidden');
      addBubble(STR.error, 'ai');
    }}
    sending = false;
  }}

  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', function(e) {{ if (e.key === 'Enter') send(); }});
}})();
</script>"""


def photo_url(file_id: str) -> str:
    base = SITE_URL or ""
    return f"{base}/photo/{file_id}"


CATEGORY_LABELS = {
    "tasdiqlangan": ("\u2705 Tasdiqlangan", "cat-verified"),
    "subarenda": ("\U0001F3E2 Subarenda", "cat-subarenda"),
    "premium": ("\U0001F48E Premium", "cat-premium"),
}

RENTAL_TYPE_LABELS = {
    "kunlik": ("\U0001F4C5 Kunlik", "rt-kunlik"),
    "uzoq_muddat": ("\U0001F3E0 Uzoq muddat", "rt-uzoq"),
    "dacha": ("\U0001F333 Dacha", "rt-dacha"),
    "mehmonxona": ("\U0001F6CF Mehmonxona", "rt-mehmon"),
}



def render_listing_card(l: dict, favorited_ids: frozenset = frozenset()) -> str:
    photos = l.get("photos") or []
    img = photo_url(photos[0]) if photos else ""
    img_html = f'<img src="{img}" alt="{esc_html(display_address(l))}" loading="lazy">' if img else f'<div class="lc-placeholder">{icon("home", 34)}</div>'
    paid_badge = f'<span class="lc-badge lc-badge-fire">{icon("bolt", 13)} TOP</span>' if (l.get("price_charged") or 0) > 0 else ""
    cat = l.get("category")
    cat_badge = ""
    if cat and cat in CATEGORY_LABELS:
        label, css_cls = CATEGORY_LABELS[cat]
        cat_badge = f'<span class="lc-badge {css_cls}" style="{"left:auto;right:10px;" if paid_badge else ""}">{label}</span>'
    xona = (l.get("xona") or "").strip()
    kimlarga = (l.get("kimlarga") or "").strip()
    meta_parts = []
    if l.get("is_quick"):
        meta_parts.append('⚡ Tezkor e\'lon')
    rtype = l.get("rental_type")
    if rtype and rtype != "uzoq_muddat" and rtype in RENTAL_TYPE_LABELS:
        meta_parts.append(esc_html(RENTAL_TYPE_LABELS[rtype][0]))
    if xona:
        meta_parts.append(f'{icon("bed", 14)} {esc_html(xona)}')
    if kimlarga:
        meta_parts.append(f'{icon("users", 14)} {esc_html(kimlarga[:16])}')
    meta_html = f'<div class="lc-meta">{" &nbsp;·&nbsp; ".join(meta_parts)}</div>' if meta_parts else ""
    fav_active = " active" if l["id"] in favorited_ids else ""
    fav_btn = f"""<button type="button" class="lc-fav-btn{fav_active}" data-listing-id="{l['id']}"
    onclick="event.preventDefault();event.stopPropagation();toggleFavorite({l['id']}, this);" aria-label="Sevimlilarga qo'shish">
    <span class="fav-icon-outline">{icon('heart', 17)}</span><span class="fav-icon-filled">{icon('heart_filled', 17)}</span>
  </button>"""
    return f"""<a href="/uy/{l['id']}" class="listing-card">
  <div class="lc-photo">
    {img_html}
    {paid_badge}
    {cat_badge}
    {fav_btn}
  </div>
  <div class="lc-body">
    <div class="lc-top">
      <div class="lc-title">{esc_html(display_address(l))}</div>
    </div>
    {meta_html}
    <div class="lc-price">{esc_html(l.get('narx') or '')}{f'<span class="lc-price-approx">{esc_html(l["narx_approx"])}</span>' if l.get('narx_approx') else ''}</div>
  </div>
</a>"""


ICONS = {
    "bed": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18v-6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v6"/><path d="M3 18h18"/><path d="M7 10V7a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v3"/><path d="M3 14v4"/><path d="M21 14v4"/></svg>',
    "users": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1"/><circle cx="10" cy="8" r="3.5"/><path d="M21 20v-1a4 4 0 0 0-2.5-3.7"/><path d="M15.5 4.3a3.5 3.5 0 0 1 0 6.9"/></svg>',
    "pin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 10c0 5.5-7 11-7 11s-7-5.5-7-11a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2.5"/></svg>',
    "target": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z"/><path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"/></svg>',
    "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/></svg>',
    "shield": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21c4.5-1.5 7.5-5.5 7.5-10.5V6l-7.5-3-7.5 3v4.5C4.5 15.5 7.5 19.5 12 21Z"/><path d="m9 12 2 2 4-4.5"/></svg>',
    "bolt": '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12.6 1.4 3.3 13.5c-.4.5 0 1.3.7 1.3h6.1l-1.6 7.5c-.2.9.9 1.5 1.5.8l9.7-12.4c.4-.5 0-1.3-.7-1.3h-6.3l1.7-7.2c.2-.9-1-1.5-1.7-.8Z"/></svg>',
    "map": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4Z"/><path d="M9 4v14"/><path d="M15 6v14"/></svg>',
    "coin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M15 9.5c-.5-.8-1.5-1.3-3-1.3-2 0-3.2 1-3.2 2.3 0 3 6 1.3 6 4.3 0 1.4-1.3 2.4-3.2 2.4-1.5 0-2.6-.5-3.2-1.3"/><path d="M12 6.5v11"/></svg>',
    "phone": '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M6.6 10.8c1.4 2.7 3.6 4.9 6.3 6.3l2.1-2.1c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1-9.4 0-17-7.6-17-17 0-.6.4-1 1-1h3.6c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.4 0 .8-.2 1L6.6 10.8Z"/></svg>',
    "share": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><path d="M16 6l-4-4-4 4"/><path d="M12 2v14"/></svg>',
    "copy": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="13" height="13" rx="2.5"/><path d="M16 8V5.5A2.5 2.5 0 0 0 13.5 3h-8A2.5 2.5 0 0 0 3 5.5v8A2.5 2.5 0 0 0 5.5 16H8"/></svg>',
    "chevron_left": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>',
    "chevron_right": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>',
    "home": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9a1 1 0 0 0 1 1h3v-6h4v6h3a1 1 0 0 0 1-1v-9"/></svg>',
    "check_circle": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 5-5.5"/></svg>',
    "sparkle": '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 2.5c.3 3 1 5.2 2.3 6.5s3.5 2 6.5 2.3c-3 .3-5.2 1-6.5 2.3s-2 3.5-2.3 6.5c-.3-3-1-5.2-2.3-6.5S6.2 11.6 3.2 11.3c3-.3 5.2-1 6.5-2.3S11.7 5.5 12 2.5Z"/></svg>',
    "camera_off": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4l16 16"/><path d="M9.5 4.5H14l1.3 2H18a2 2 0 0 1 2 2v8.8"/><path d="M18.6 18.6a2 2 0 0 1-.6.1H5a2 2 0 0 1-2-2V8.5a2 2 0 0 1 2-2h.4"/><circle cx="12" cy="13" r="3.2"/></svg>',
    "sad": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="9" cy="10" r="0.9" fill="currentColor" stroke="none"/><circle cx="15" cy="10" r="0.9" fill="currentColor" stroke="none"/><path d="M8.5 16c1-1.2 2.2-1.8 3.5-1.8s2.5.6 3.5 1.8"/></svg>',
    "close": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>',
    "expand": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M21 16v3a2 2 0 0 1-2 2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/></svg>',
    "send": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 3 11 13"/><path d="M21 3 14.5 21a.4.4 0 0 1-.7 0L11 13l-8-2.8a.4.4 0 0 1 0-.7L21 3Z"/></svg>',
    "instagram": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.2" cy="6.8" r="0.6" fill="currentColor" stroke="none"/></svg>',
    "menu": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/></svg>',
    "message": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5c-1.2 0-2.3-.2-3.4-.7L3 21l1.7-4.6A8.5 8.5 0 1 1 21 11.5Z"/></svg>',
    "user": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-3.9 3.6-7 8-7s8 3.1 8 7"/></svg>',
    "calendar": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="16" rx="2.5"/><path d="M8 3v4"/><path d="M16 3v4"/><path d="M3.5 10h17"/></svg>',
    "tree": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22v-7"/><path d="M12 15c-3.5 0-6-2.3-6-5.3C6 6.3 8.7 3 12 2c3.3 1 6 4.3 6 7.7 0 3-2.5 5.3-6 5.3Z"/></svg>',
    "heart": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20.5s-7.5-4.6-9.8-9.4C.8 7.6 2.4 4.5 5.6 3.8c2-.4 3.9.4 5 2 .5-1.6 2.4-2.4 5-2 3.2.7 4.8 3.8 3.4 7.3C19.5 15.9 12 20.5 12 20.5Z"/></svg>',
    "heart_filled": '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 20.5s-7.5-4.6-9.8-9.4C.8 7.6 2.4 4.5 5.6 3.8c2-.4 3.9.4 5 2 .5-1.6 2.4-2.4 5-2 3.2.7 4.8 3.8 3.4 7.3C19.5 15.9 12 20.5 12 20.5Z"/></svg>',
    "alert": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 20.5h20L12 3Z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.5" r="0.6" fill="currentColor" stroke="none"/></svg>',
}


def icon(name: str, size: int = 18) -> str:
    svg = ICONS.get(name, "")
    return f'<span class="ico" style="width:{size}px;height:{size}px;">{svg}</span>'


def esc_html(s) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


# ============================= BOSH SAHIFA =============================


