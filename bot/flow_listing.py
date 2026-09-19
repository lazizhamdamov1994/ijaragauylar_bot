"""
Asosiy e'lon yaratish oqimi - bosh suhbat (ConversationHandler) bilan.
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

from common.telegram_media import download_photo_bytes, watermark_telegram_photo
from common.slideshow import build_instagram_caption, build_slideshow_video
from common.ai import ai_check_receipt, ai_features_enabled, ai_screen_for_scam

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403
from bot.fraud_detection import *  # noqa: F401,F403
from bot.admin_moderation import *  # noqa: F401,F403
from bot.location_alerts import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

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
        file_id = update.message.photo[-1].file_id
        if ADMIN_IDS:
            file_id = await watermark_telegram_photo(file_id, ADMIN_IDS[0])
        rasmlar.append(file_id)
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

    # Slaydshov video FAQAT admin/moderatorlar uchun - oddiy e'lon
    # beruvchilarga bu savol umuman ko'rsatilmaydi.
    if not is_staff(user.id):
        context.user_data["want_slideshow"] = False
        return await _show_tasdiqlash_keyboard(update, context)

    slideshow_keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("\u2705 Ha", callback_data="slideshow_yes"),
             InlineKeyboardButton("\u274c Yo'q", callback_data="slideshow_no")],
        ]
    )
    await context.bot.send_message(
        chat_id,
        "\U0001F3AC Ushbu e'lon uchun Instagram'da joylash uchun qisqa slaydshov video ham tayyorlab beraylikmi?\n"
        "(Video + tayyor post matni sizga alohida yuboriladi - Instagram'ga faqat o'zingiz joylaysiz.)",
        reply_markup=slideshow_keyboard,
    )
    return SLIDESHOW_CONFIRM


async def slideshow_choice_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    context.user_data["want_slideshow"] = query.data == "slideshow_yes"
    return await _show_tasdiqlash_keyboard(update, context)


async def _show_tasdiqlash_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

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


async def slideshow_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await remind_buttons(update, context, SLIDESHOW_CONFIRM)


async def _generate_and_send_slideshow(
    context: ContextTypes.DEFAULT_TYPE, listing_id: int, rasmlar: list,
    manzil: str, narx: str, xona: str, kimlarga: str, qulaylik: str,
) -> None:
    """Fonda (bot javob berishini KUTMASDAN) slaydshov video yasab, tayyor
    Instagram post matni bilan birga ADMINGA yuboradi. Xatolik bo'lsa ham
    (ffmpeg yo'q, rasm yuklanmadi va h.k.) e'lonning o'zi allaqachon
    saqlangan/joylangan - shuning uchun bu yerdagi xatolik hech narsani
    buzmaydi, faqat log'ga yoziladi."""
    if not ADMIN_IDS:
        return
    try:
        photo_bytes = []
        for file_id in rasmlar[:10]:
            raw = await download_photo_bytes(file_id)
            if raw:
                photo_bytes.append(raw)
        if not photo_bytes:
            logger.warning("Slaydshov uchun rasm yuklab bo'lmadi (e'lon #%s)", listing_id)
            return

        video = await build_slideshow_video(photo_bytes, manzil, narx)
        if video is None:
            logger.warning("Slaydshov video yasalmadi (e'lon #%s)", listing_id)
            return

        caption = build_instagram_caption(manzil, narx, xona=xona, kimlarga=kimlarga, qulaylik=qulaylik)
        for admin_id in ADMIN_IDS:
            try:
                await send_with_retry(
                    context.bot.send_video, admin_id, video,
                    caption=f"\U0001F3AC E'lon #{listing_id} uchun Instagram slaydshov video tayyor.\nInstagram'ga shu videoni joylang \U0001F447",
                )
                await send_with_retry(context.bot.send_message, admin_id, caption)
            except Exception:
                logger.exception("Slaydshov videoni adminga (%s) yuborishda xatolik", admin_id)
    except Exception:
        logger.exception("Slaydshov generatsiya jarayonida kutilmagan xatolik (e'lon #%s)", listing_id)


def _maybe_start_slideshow(context: ContextTypes.DEFAULT_TYPE, data: dict, listing_id: int) -> None:
    if not data.get("want_slideshow"):
        return
    asyncio.create_task(_generate_and_send_slideshow(
        context, listing_id, list(data.get("rasmlar") or []),
        data.get("manzil", ""), data.get("narx", ""),
        data.get("xona", ""), data.get("kimlarga", ""), data.get("qulaylik", ""),
    ))


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
        _maybe_start_slideshow(context, data, listing_id)
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

        _maybe_start_slideshow(context, data, listing_id)
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

    _maybe_start_slideshow(context, data, listing_id)
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

    # AI firibgarlik skrining va (agar chek bo'lsa) to'lov cheki oldindan
    # tekshiruvi - faqat admin "ai_features_enabled" sozlamasini yoqib
    # qo'ygan bo'lsa ishlaydi; xatolik yoki o'chirilgan bo'lsa None
    # qaytadi va bu bosqich jimgina o'tkazib yuboriladi - moderatsiya
    # jarayoni hech qachon bunga bog'liq bo'lmaydi (moderator baribir
    # qo'lda tekshirib, o'zi qaror qiladi).
    ai_warning = ""
    try:
        loop = asyncio.get_event_loop()
        scam = await loop.run_in_executor(None, ai_screen_for_scam, caption)
        if scam and scam.get("suspicious"):
            ai_warning += f"\U0001F916\u26a0\ufe0f <b>AI: shubhali belgilar topildi</b> \u2014 {esc(scam.get('reason') or '')}\n\n"
    except Exception:
        logger.exception("AI firibgarlik skriningida xatolik")

    if data.get("payment_receipt") and ai_features_enabled():
        try:
            receipt_bytes = await download_photo_bytes(data["payment_receipt"])
            if receipt_bytes:
                receipt_check = await loop.run_in_executor(
                    None, ai_check_receipt, receipt_bytes, "image/jpeg", price_charged, CARD_HOLDER,
                )
                if receipt_check and not receipt_check.get("matches"):
                    ai_warning += f"\U0001F916\u26a0\ufe0f <b>AI: chekda nomuvofiqlik</b> \u2014 {esc(receipt_check.get('note') or '')}\n\n"
        except Exception:
            logger.exception("AI to'lov cheki tekshiruvida xatolik")

    sender_line = (
        f"{warning}{ai_warning}"
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



