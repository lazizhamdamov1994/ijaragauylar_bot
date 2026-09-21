"""
Umumiy yordamchi funksiyalar (matn formatlash, xabar yuborish/qayta urinish,
foydalanuvchiga bildirishnoma) + hudud nomini Lotin/Kirill moslashtirish.
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

logger = logging.getLogger(__name__)

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


def viewing_request_keyboard(listing_id: int, bot_username: str) -> InlineKeyboardMarkup:
    """Uy egasi raqami ko'rsatilgan xabar TAGIDA chiqadigan tugma - kanal
    postining o'zida EMAS (raqamni ko'rgan, ya'ni haqiqatan qiziqqan
    foydalanuvchigagina taklif qilinadi)."""
    viewing_link = f"https://t.me/{bot_username}?start=viewing_{listing_id}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F5D3 Ko'rish vaqtini band qilish", url=viewing_link)]])


def channel_keyboard(listing_id: int, bot_username: str, latitude: float = None, longitude: float = None) -> InlineKeyboardMarkup:
    call_link = f"https://t.me/{bot_username}?start=phone_{listing_id}"
    post_link = f"https://t.me/{bot_username}?start=elon"
    complain_link = f"https://t.me/{bot_username}?start=complain_{listing_id}"
    rows = [
        [InlineKeyboardButton("\U0001F4DE Uy egasi raqami", url=call_link)],
    ]
    if latitude and longitude:
        map_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
        rows.append([InlineKeyboardButton("\U0001F5FA Lokatsiya", url=map_link),
                     InlineKeyboardButton("\U0001F4DD E'lon berish", url=post_link)])
    else:
        rows.append([InlineKeyboardButton("\U0001F4DD E'lon berish", url=post_link)])
    rows.append([InlineKeyboardButton("\U0001F4AC Adminga", url=f"https://t.me/{ADMIN_USERNAME}"),
                 InlineKeyboardButton("\u26A0\uFE0F Etiroz", url=complain_link)])
    # MUHIM: "Web sahifaga o'tish" har doim ENG PASTKI qator bo'lib qoladi.
    if DASHBOARD_URL and DASHBOARD_URL.startswith("https://"):
        rows.append([InlineKeyboardButton("\U0001F310 Web sahifaga o'tish", url=f"{DASHBOARD_URL}/uy/{listing_id}")])
    return InlineKeyboardMarkup(rows)


def channel_link_button():
    if not CHANNEL_USERNAME:
        return None
    return InlineKeyboardButton("\U0001F4E2 Kanaldagi e'lonlarni ko'rish", url=f"https://t.me/{CHANNEL_USERNAME}")


def main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    rows = [[BTN_ELON], [BTN_AI_CONCIERGE], [BTN_VALUATION], [BTN_LISTINGS, BTN_SUBSCRIPTION], [BTN_CHECK_PHONE, BTN_HELP], [BTN_LOCATION_ALERT, BTN_MY_LOCATIONS], [BTN_CHANNEL]]
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
        rows.append([BTN_LISTINGS_MAP, BTN_DISTRICT_ALIASES])
        if DASHBOARD_URL:  # Admin Panel - oddiy URL tugma, http:// bilan ham ishlaydi
            rows.append([BTN_ADMIN_PANEL])
        rows.append([BTN_QUICK])
    elif is_moderator(user_id):
        rows.append([BTN_STATS, BTN_PENDING])
        rows.append([BTN_QUICK, BTN_DISTRICT_ALIASES])
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


def is_super_moderator(user_id: int) -> bool:
    """Admin YOKI "super moderator" belgisi qo'yilgan moderator - oddiy
    moderatordan farqli, PUL bilan bog'liq (to'lov cheklarini
    tasdiqlash/rad etish) amallarni ham bajara oladi."""
    if is_admin(user_id):
        return True
    conn = db()
    row = conn.execute("SELECT 1 FROM moderators WHERE user_id = ? AND is_super = 1", (user_id,)).fetchone()
    conn.close()
    return row is not None


def set_moderator_super(user_id: int, is_super: bool) -> None:
    conn = db()
    conn.execute("UPDATE moderators SET is_super = ? WHERE user_id = ?", (1 if is_super else 0, user_id))
    conn.commit()
    conn.close()


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



