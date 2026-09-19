"""
Asosiy menyu, /start, "Yordam" (mavzu bo'yicha), va "Raqamni tekshirish"
funksiyalari.
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

from common.telegram_media import watermark_telegram_photo

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403
from bot.fraud_detection import *  # noqa: F401,F403
# text_menu_router quyidagi modullardagi show_* funksiyalarni chaqiradi -
# ular menu.py'dan KEYIN emas, shu yerda kerak (birortasi menu.py'ni
# import qilmaydi, shuning uchun aylanma import xavfi yo'q).
from bot.location_alerts import *  # noqa: F401,F403
from bot.admin_panel import *  # noqa: F401,F403
from bot.flow_listing import *  # noqa: F401,F403
from bot.admin_moderators import *  # noqa: F401,F403
from bot.flow_complaint import *  # noqa: F401,F403
from bot.district_alias_ui import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

# ============================= ASOSIY MENYU / START =============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payload = context.args[0] if context.args else None

    upsert_user(user.id, user.username, user.full_name)

    if payload and payload.startswith("phone_"):
        await reveal_phone(update, context, payload)
        return

    if payload and payload.startswith("viewing_"):
        # Odatiy holatda bu chuqur-havola viewing_conv'ning O'Z kirish nuqtasi
        # orqali ushlanadi (u shu generik start()dan OLDIN ro'yxatdan
        # o'tkazilgan) - bu yerga faqat "qaytgan foydalanuvchi" noyob holatida
        # tushadi, xuddi elon/buysub/checkphone kabi.
        await update.message.reply_text(
            "\U0001F5D3 Ko'rish vaqtini band qilish uchun, iltimos, \"Uy egasi raqami\" tugmasini qayta bosib, "
            "chiqqan xabar tagidagi tugmani bosing.",
            reply_markup=main_menu_keyboard(user.id),
        )
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

    # "Ko'rish vaqtini band qilish" tugmasi ENDI kanal postida emas, balki
    # aynan shu yerda - raqamni ko'rgan (haqiqatan qiziqqan) foydalanuvchiga
    # taklif qilinadi.
    await context.bot.send_message(
        user_id, phone_reveal_text(listing) + free_note, parse_mode=ParseMode.HTML,
        reply_markup=viewing_request_keyboard(listing_id, context.bot.username), disable_web_page_preview=True,
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
            kb_rows = []
            for lst in active_listings:
                kb_rows.append([InlineKeyboardButton(f"\u2705 #{lst['id']} topshirildi deb belgilash", callback_data=f"selfexpire_{lst['id']}")])
                kb_rows.append([
                    InlineKeyboardButton(f"\u270f\ufe0f #{lst['id']} tahrirlash", callback_data=f"editlisting_{lst['id']}"),
                    InlineKeyboardButton(f"\U0001F5D1 #{lst['id']} o'chirish", callback_data=f"deletelisting_{lst['id']}"),
                ])
            await update.message.reply_text(
                "Uy ijaraga berilgan bo'lsa, shu yerdan belgilab qo'ying \u2014 kanaldan avtomatik olib tashlaymiz. "
                "Narx yoki boshqa ma'lumotni o'zgartirish/o'chirish uchun ham shu yerdan foydalaning:",
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
    elif text == BTN_DISTRICT_ALIASES and staff:
        await show_district_alias_districts(update, context)


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





# ============================= RAQAMNI TEKSHIRISH (hammaga) =============================

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



