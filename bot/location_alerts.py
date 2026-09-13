"""
"Hudud bo'yicha xabar" - foydalanuvchi tuman kiritadi, mos yangi e'lon
chiqqanda avtomatik xabar oladi (UI qismi).
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

logger = logging.getLogger(__name__)

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



