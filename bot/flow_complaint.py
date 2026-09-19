"""
E'lon ustidan shikoyat (kanal postidagi tugmalardan boshlanadigan oqim) +
kanal postidagi boshqa tugmalar (telefon, elon berish, limit va h.k.).
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
from bot.admin_moderation import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

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
    """E'lonni \"topshirilgan\" deb belgilaydi. Kanaldagi post O'CHIRILMAYDI
    (kanal statistikasi/tarixi saqlanadi uchun), lekin MATNI (caption)
    \u00ab\u274c BAND QILINDI\u00bb deb YANGILANADI - shu orqali tomoshabinlar buni
    darhol ko'radi (tugmalar o'zgarmaydi - \"Uy egasi raqami\" tugmasi
    bosilsa ham, `expired` belgisi allaqachon tekshirilib, raqam
    ko'rsatilmaydi)."""
    mark_listing_expired(listing_id)
    listing = get_listing(listing_id)
    if listing and listing.get("channel_msg_id"):
        try:
            caption = "\u274c <b>BAND QILINDI / TOPSHIRILDI</b>\n\n" + build_caption(listing, context.bot.username)
            await context.bot.edit_message_text(
                chat_id=CHANNEL_ID, message_id=listing["channel_msg_id"], text=caption, parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception("Kanaldagi postni \u00abband qilindi\u00bb deb belgilashda xatolik (listing_id=%s)", listing_id)
    if notify_owner and listing:
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
    belgilamaguncha, admin belgilagan oraliqda (sozlamalar:
    paid_repost_interval_hours) kanalga QAYTA joylanadi (bepul e'lonlar
    faqat bir marta joylanadi, o'zgarishsiz qoladi). job_promote_limit
    kabi - tez-tez tekshiriladi, lekin oraliq o'tmagan bo'lsa chiqib
    ketadi."""
    if not CHANNEL_ID:
        return
    interval_hours = max(1, int(get_setting("paid_repost_interval_hours", "3") or "3"))
    last_run = get_setting("_last_paid_repost_run_at", "")
    if last_run:
        try:
            if datetime.now(TASHKENT_TZ) - datetime.fromisoformat(last_run) < timedelta(hours=interval_hours):
                return
        except ValueError:
            pass
    set_setting("_last_paid_repost_run_at", datetime.now(TASHKENT_TZ).isoformat())
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
    """Admin belgilagan oraliqda (sozlamalar: promote_limit_interval_hours)
    kanalga Limit haqida qisqa, tushunarli tanishtiruv posti joylanadi -
    real obunachilar soni bilan, to'g'ridan-to'g'ri sotib olish tugmasi
    bilan. Job JobQueue'da tez-tez (har 30 daqiqada) tekshiriladi, lekin
    oxirgi joylashdan buyon admin belgilagan soat o'tmagan bo'lsa, hech
    narsa qilmasdan chiqadi - shu tariqa admin oraliqni o'zgartirsa, botni
    qayta ishga tushirmasdan, keyingi tekshiruvda kuchga kiradi."""
    if not CHANNEL_ID:
        return
    interval_hours = max(1, int(get_setting("promote_limit_interval_hours", "2") or "2"))
    last_run = get_setting("_last_promote_limit_run_at", "")
    if last_run:
        try:
            if datetime.now(TASHKENT_TZ) - datetime.fromisoformat(last_run) < timedelta(hours=interval_hours):
                return
        except ValueError:
            pass
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
        set_setting("_last_promote_limit_run_at", datetime.now(TASHKENT_TZ).isoformat())
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



