"""
"Ko'rish vaqtini band qilish" - telefon raqami ko'rsatilgan xabar
TAGIDAGI tugmadan, chuqur-havola orqali (?start=viewing_{listing_id})
boshlanadi. MUHIM: bu yerga kirish `reveal_phone_core` (bot/menu.py,
telefon ko'rsatish) BILAN AYNAN BIR XIL Limit-obuna/bepul-ko'rish
to'lov devori (paywall) qoidasi orqali tekshiriladi - aks holda bu
funksiya pullik funksiyani (telefon ko'rish) bepul aylanib o'tish
yo'liga aylanib qolardi.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403
from bot.fraud_detection import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

MAX_VIEWING_REQUESTS_PER_DAY = 5


async def request_viewing_core(update: Update, context: ContextTypes.DEFAULT_TYPE, listing_id) -> int:
    """`reveal_phone_core` (bot/menu.py) bilan bir xil tartibda tekshiradi:
    ban -> e'lon holati -> obuna YOKI bepul ko'rish. Muvaffaqiyatli bo'lsa
    vaqt so'rash holatiga o'tadi (VIEWING_TIME_WAIT qaytaradi), aks holda
    ConversationHandler.END."""
    user = update.effective_user
    user_id = user.id
    admin = is_admin(user_id)

    if is_banned(user_id):
        await context.bot.send_message(user_id, "⚠️ Sizga botdan foydalanish cheklangan. Savollar bo'lsa, adminga murojaat qiling.")
        return ConversationHandler.END

    listing = get_listing(listing_id) if listing_id else None
    if not listing or listing["status"] != "approved":
        await context.bot.send_message(user_id, "⚠️ Kechirasiz, bu e'lon topilmadi yoki hali tasdiqlanmagan.", reply_markup=main_menu_keyboard(user_id))
        return ConversationHandler.END

    if listing.get("expired"):
        await context.bot.send_message(user_id, "✅ Bu uy allaqachon topshirilgan (ijaraga berilgan).", reply_markup=main_menu_keyboard(user_id))
        return ConversationHandler.END

    if int(listing["user_id"]) == int(user_id):
        await context.bot.send_message(user_id, "ℹ️ Bu sizning o'z e'loningiz.", reply_markup=main_menu_keyboard(user_id))
        return ConversationHandler.END

    active, _expire = is_subscribed(user_id)
    if admin:
        active = True  # Admin uchun har doim cheksiz.
    has_free = user_free_used(user_id) < user_free_limit(user_id)

    if not active and not has_free:
        log_paywall_hit(user_id, listing_id)
        price, days = subscription_price(), subscription_days()
        text = (
            "\U0001F513 <b>Bepul ko'rishlaringiz tugadi</b>\n\n"
            "Ko'rish vaqtini band qilish ham — uy egasi raqamini ko'rish bilan bir xil — Limit talab qiladi.\n\n"
            f"\U0001F4B3 {days} kun — <b>{price:,} so'm</b>"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"\U0001F513 {days} kunlik limit olish", callback_data=f"buy_subscription_{listing_id}")]])
        await context.bot.send_message(user_id, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return ConversationHandler.END

    if count_viewing_requests_today(user_id) >= MAX_VIEWING_REQUESTS_PER_DAY:
        await context.bot.send_message(user_id, "⚠️ Kunlik so'rov chegarasiga yetdingiz. Ertaga qayta urinib ko'ring.", reply_markup=main_menu_keyboard(user_id))
        return ConversationHandler.END

    if not active:
        consume_free_view(user_id)

    context.user_data["viewing_listing_id"] = listing_id
    await context.bot.send_message(
        user_id,
        "\U0001F5D3 <b>Ko'rish vaqtini band qilish</b>\n\nQaysi kun/soatda ko'rmoqchisiz? Yozing (masalan: «Ertaga soat 15:00»):",
        parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove(),
    )
    return VIEWING_TIME_WAIT


async def viewing_deeplink_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user.id, update.effective_user.username, update.effective_user.full_name)
    payload = context.args[0] if context.args else ""
    try:
        listing_id = int(payload.split("_", 1)[1])
    except (IndexError, ValueError):
        return ConversationHandler.END
    return await request_viewing_core(update, context, listing_id)


async def viewing_time_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        context.user_data.pop("viewing_listing_id", None)
        return ConversationHandler.END

    listing_id = context.user_data.get("viewing_listing_id")
    if not listing_id:
        return ConversationHandler.END

    raw = (update.message.text or "").strip()
    if not raw:
        await update.message.reply_text("⚠️ Bo'sh bo'lishi mumkin emas. Qaytadan yozing:")
        return VIEWING_TIME_WAIT
    if len(raw) > 200:
        await update.message.reply_text("⚠️ Juda uzun. 200 belgidan qisqaroq yozing:")
        return VIEWING_TIME_WAIT

    user = update.effective_user
    listing = get_listing(listing_id)
    context.user_data.pop("viewing_listing_id", None)
    if not listing:
        await update.message.reply_text("⚠️ Bu e'lon endi topilmadi.", reply_markup=main_menu_keyboard(user.id))
        return ConversationHandler.END

    request_id = create_viewing_request(listing_id, user.id, raw)
    await update.message.reply_text(
        "✅ So'rovingiz uy egasiga yuborildi. U tasdiqlasa yoki rad etsa, sizga xabar beramiz.",
        reply_markup=main_menu_keyboard(user.id),
    )

    requester_name = user.full_name or (f"@{user.username}" if user.username else f"ID:{user.id}")
    addr = listing.get("manzil") or (listing.get("raw_text") or "")[:60]
    owner_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"viewingaccept_{request_id}"),
         InlineKeyboardButton("❌ Rad etish", callback_data=f"viewingdecline_{request_id}")],
    ])
    try:
        await context.bot.send_message(
            listing["user_id"],
            f"\U0001F4C5 <b>Ko'rish vaqti so'raldi</b>\n\n\U0001F3E0 E'lon: {esc(addr)} (#{listing_id})\n"
            f"\U0001F464 So'ragan: {esc(requester_name)}\n\U0001F553 Taklif qilingan vaqt: {esc(raw)}",
            parse_mode=ParseMode.HTML, reply_markup=owner_keyboard,
        )
    except Exception:
        logger.exception("Uy egasiga ko'rish so'rovi haqida xabar yuborib bo'lmadi (listing_id=%s)", listing_id)

    return ConversationHandler.END


async def viewing_time_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("viewing_listing_id", None)
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END


# ============================= UY EGASINING JAVOBI (tasdiqlash/rad etish) =============================

async def _viewing_owner_respond(query, context: ContextTypes.DEFAULT_TYPE, request_id: int, status: str) -> None:
    vr = get_viewing_request(request_id)
    if not vr:
        await query.answer("So'rov topilmadi.", show_alert=True)
        return
    listing = get_listing(vr["listing_id"])
    if not listing or int(listing["user_id"]) != int(query.from_user.id):
        await query.answer("Bu sizning e'loningiz emas.", show_alert=True)
        return
    if vr["status"] != "pending":
        await query.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    update_viewing_request_status(request_id, status)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if status == "confirmed":
        await query.message.reply_text("✅ Tasdiqlandi. So'rovchiga xabar berildi.")
        notify_text = (
            f"✅ Uy egasi ko'rish vaqtingizni TASDIQLADI!\n\n\U0001F3E0 E'lon #{vr['listing_id']}\n"
            f"\U0001F553 Vaqt: {esc(vr['requested_time'])}"
        )
    else:
        await query.message.reply_text("❌ Rad etildi. So'rovchiga xabar berildi.")
        notify_text = f"❌ Uy egasi so'ragan ko'rish vaqtini rad etdi.\n\n\U0001F3E0 E'lon #{vr['listing_id']}"

    try:
        await context.bot.send_message(vr["user_id"], notify_text, parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("So'rovchiga ko'rish natijasi haqida xabar yuborib bo'lmadi (request_id=%s)", request_id)


async def viewingaccept_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    request_id = int(query.data.rsplit("_", 1)[1])
    await _viewing_owner_respond(query, context, request_id, "confirmed")


async def viewingdecline_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    request_id = int(query.data.rsplit("_", 1)[1])
    await _viewing_owner_respond(query, context, request_id, "declined")
