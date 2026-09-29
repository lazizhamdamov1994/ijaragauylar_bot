"""
"Topga ko'tarish" - bepul joylangan e'lonni to'lov evaziga TOP (pullik)
aylanishiga qo'shish. YANGI E'LON YARATILMAYDI - faqat mavjud e'lonning
`price_charged` maydoni yangilanadi, chunki `job_repost_paid_listings`
(bot/flow_complaint.py) aynan shu maydonga qarab ishlaydi.

To'lov oqimi bot/flow_subscription.py va bot/flow_valuation.py bilan bir
xil naqsh: karta ko'rsatiladi, chek so'raladi, AI oldindan tekshiradi, mos
kelsa darhol faollashadi, mos kelmasa/AI o'chirilgan bo'lsa admin (yoki
super moderator) qo'lda tasdiqlaydi.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from common.ai import ai_check_receipt, ai_features_enabled
from common.config import ADMIN_IDS, CARD_HOLDER
from common.db import boost_listing_to_top, get_boost_payment, get_setting, save_boost_payment, update_boost_payment_status
from common.telegram_media import download_photo_bytes

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


def boost_offer_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F680 TOP'ga ko'tarish", callback_data=f"boost_offer_{listing_id}")]])


async def boost_offer_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    listing_id = int(query.data.rsplit("_", 1)[1])
    listing = get_listing(listing_id)

    if not listing or listing["user_id"] != query.from_user.id:
        await query.message.reply_text("⚠️ E'lon topilmadi.")
        return ConversationHandler.END
    if listing["status"] != "approved" or listing.get("expired"):
        await query.message.reply_text("⚠️ Bu e'lon endi faol emas.")
        return ConversationHandler.END
    if (listing.get("price_charged") or 0) > 0:
        await query.message.reply_text("✅ Bu e'lon allaqachon TOP'da.")
        return ConversationHandler.END

    price = listing_price()
    context.user_data["boost_pending_listing_id"] = listing_id
    await query.message.reply_text(
        card_html(price, "E'lonni TOP'ga ko'tarish"), parse_mode=ParseMode.HTML, reply_markup=card_payment_keyboard("boost_cancel"),
    )
    return BOOST_RECEIPT_WAIT


async def boost_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("boost_pending_listing_id", None)
    await query.edit_message_text("❌ Bekor qilindi.")
    return ConversationHandler.END


async def boost_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("⚠️ Iltimos, to'lov chekining skrinshotini RASM sifatida yuboring.")
        return BOOST_RECEIPT_WAIT

    user = update.effective_user
    listing_id = context.user_data.get("boost_pending_listing_id")
    if not listing_id:
        context.user_data.pop("boost_pending_listing_id", None)
        return ConversationHandler.END

    listing = get_listing(listing_id)
    if not listing or listing["status"] != "approved" or (listing.get("price_charged") or 0) > 0:
        context.user_data.pop("boost_pending_listing_id", None)
        await update.message.reply_text("⚠️ Bu e'lon endi TOP'ga ko'tarish uchun mos emas.", reply_markup=main_menu_keyboard(user.id))
        return ConversationHandler.END

    receipt_file_id = update.message.photo[-1].file_id
    price = listing_price()

    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    receipt_check = None
    try:
        receipt_bytes = await download_photo_bytes(receipt_file_id)
        if receipt_bytes:
            receipt_check = ai_check_receipt(receipt_bytes, "image/jpeg", price, CARD_HOLDER)
    except Exception:
        logger.exception("AI topga ko'tarish chekini tekshirishda xatolik")

    payment_id = save_boost_payment(listing_id, user.id, price, receipt_file_id)
    context.user_data.pop("boost_pending_listing_id", None)

    if receipt_check and receipt_check.get("matches"):
        update_boost_payment_status(payment_id, "approved")
        boost_listing_to_top(listing_id, price)
        await update.message.reply_text(
            "✅ To'lov tasdiqlandi! E'loningiz endi TOP aylanishida - navbat bilan qayta-qayta yuqoriga chiqarib turiladi.",
            reply_markup=main_menu_keyboard(user.id),
        )
        fyi_caption = (
            f"\U0001F916✅ <b>AI avtomatik tasdiqladi</b> — TOP'ga ko'tarish #{payment_id}\n\n"
            f"\U0001F464 {esc(user.full_name)} (@{esc(user.username) or 'yo`q'})\n"
            f"\U0001F194 user_id: {user.id}\n"
            f"\U0001F3E0 E'lon #{listing_id}\n"
            f"\U0001F4B0 Summasi: {price:,} so'm\n\n"
            "AI chek va summani mos deb topdi, shuning uchun admin tasdiqlashini kutmay darhol faollashtirildi."
        )
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_photo(admin_id, receipt_file_id, caption=fyi_caption, parse_mode=ParseMode.HTML)
            except Exception:
                logger.exception("Adminga (%s) TOP FYI xabarini yuborishda xatolik", admin_id)
        return ConversationHandler.END

    await update.message.reply_text(
        "\U0001F4E8 Chekingiz adminga tekshirish uchun yuborildi. Tasdiqlangach, e'loningiz TOP'ga chiqadi.",
        reply_markup=main_menu_keyboard(user.id),
    )
    ai_note = f"\n\n\U0001F916⚠️ AI: {esc(receipt_check.get('note') or '')}" if receipt_check else ""
    admin_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"boostpay_approve_{payment_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"boostpay_reject_{payment_id}"),
    ]])
    caption = (
        f"\U0001F680 <b>Yangi «TOP'ga ko'tarish» so'rovi</b> #{payment_id}\n\n"
        f"\U0001F464 {esc(user.full_name)} (@{esc(user.username) or 'yo`q'})\n"
        f"\U0001F194 user_id: {user.id}\n"
        f"\U0001F3E0 E'lon #{listing_id}\n"
        f"\U0001F4B0 Summasi: {price:,} so'm"
        f"{ai_note}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(admin_id, receipt_file_id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=admin_keyboard)
        except Exception:
            logger.exception("Adminga (%s) TOP to'lov so'rovini yuborib bo'lmadi", admin_id)
    return ConversationHandler.END


async def boostpay_approve_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_moderator(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q — to'lovlarni faqat admin yoki super moderator tasdiqlay oladi.", show_alert=True)
        return
    payment_id = int(query.data.rsplit("_", 1)[1])
    payment = get_boost_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ Bu so'rov allaqachon ko'rib chiqilgan.")
        return
    update_boost_payment_status(payment_id, "approved")
    boost_listing_to_top(payment["listing_id"], payment["price"])
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"✅ TOP to'lovi #{payment_id} tasdiqlandi.")
    try:
        await context.bot.send_message(
            payment["user_id"],
            "✅ TOP'ga ko'tarish uchun to'lovingiz tasdiqlandi! E'loningiz endi TOP aylanishida.",
        )
    except Exception:
        logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi")


async def boostpay_reject_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_moderator(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q — to'lovlarni faqat admin yoki super moderator rad eta oladi.", show_alert=True)
        return
    payment_id = int(query.data.rsplit("_", 1)[1])
    payment = get_boost_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ Bu so'rov allaqachon ko'rib chiqilgan.")
        return
    update_boost_payment_status(payment_id, "rejected")
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"❌ TOP to'lovi #{payment_id} rad etildi.")
    try:
        await context.bot.send_message(
            payment["user_id"],
            "❌ TOP'ga ko'tarish uchun to'lovingiz tasdiqlanmadi. Chekni tekshirib qaytadan urinib ko'ring yoki qo'llab-quvvatlash bilan bog'laning.",
        )
    except Exception:
        logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi")
