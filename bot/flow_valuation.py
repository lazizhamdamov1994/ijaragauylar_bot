"""
AI uy baholash - foydalanuvchi o'z uyi haqida qisqa anketa to'ldiradi
(tuman, xonalar soni, holati, ixtiyoriy rasmlar) va AI shu tuman/
xonadagi HAQIQIY faol e'lonlarga (comps) asoslanib taxminiy ijara narxi
diapazonini taklif qiladi.

MUHIM: bu professional baholash EMAS, faqat taxmin - foydalanuvchiga
ochiq shunday aytiladi (odamlarning "men arzonga bermayapmanmi" degan
xavotirini bartaraf etish - to'g'ri javob emas, YO'NALISH berish uchun).
Umumiy AI qoidalar (common/ai.py bilan bir xil): AI o'chirilgan yoki
xatolik bersa, foydalanuvchiga muloyim xabar bilan tushuntiriladi,
hech qachon "buzilib" qolmaydi.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from common.ai import ai_check_receipt, ai_features_enabled, ai_valuate_property
from common.ai_agent import find_comparable_listings
from common.config import ADMIN_IDS, CARD_HOLDER
from common.db import (
    get_setting,
    get_valuation_payment,
    has_prior_valuation,
    save_valuation_payment,
    save_valuation_request,
    update_valuation_payment_status,
)
from common.districts import TASHKENT_DISTRICTS
from common.telegram_media import download_photo_bytes

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403
from bot.fraud_detection import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

MAX_VALUATION_PHOTOS = 3

_PHOTO_KEYBOARD = ReplyKeyboardMarkup([[BTN_VALUATION_DONE_PHOTOS], [BTN_VALUATION_SKIP_PHOTOS]], resize_keyboard=True)


def _district_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(d, callback_data=f"valdist_{i}")] for i, d in enumerate(TASHKENT_DISTRICTS)]
    return InlineKeyboardMarkup(rows)


async def valuation_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not ai_features_enabled():
        await update.message.reply_text(
            "\U0001F916 Bu funksiya hozircha ishga tushirilmagan. Tez orada faollashadi!",
            reply_markup=main_menu_keyboard(user.id),
        )
        return ConversationHandler.END
    context.user_data["valuation"] = {"photos": []}
    await update.message.reply_text(
        "\U0001F3F7 <b>AI uy baholash</b>\n\n"
        "Bir necha savolga javob bering - AI shu tuman/xonadagi HAQIQIY faol e'lonlarga "
        "asoslanib, taxminiy ijara narxini aytadi.\n\n"
        "<i>⚠️ Bu professional baholash EMAS - faqat yo'naltiruvchi taxmin.</i>\n\n"
        "Uyingiz qaysi tumanda?",
        parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup([[BTN_AI_CONCIERGE_END]], resize_keyboard=True),
    )
    await update.message.reply_text("Tumanni tanlang:", reply_markup=_district_keyboard())
    return VALUATION_DISTRICT_WAIT


async def valuation_district_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = int(query.data.rsplit("_", 1)[1])
    if idx < 0 or idx >= len(TASHKENT_DISTRICTS):
        return VALUATION_DISTRICT_WAIT
    district = TASHKENT_DISTRICTS[idx]
    context.user_data.setdefault("valuation", {"photos": []})["district"] = district
    await query.edit_message_text(f"\U0001F3D8 Tuman: <b>{district}</b>", parse_mode=ParseMode.HTML)
    await query.message.reply_text(
        "\U0001F6CF Nechta xonali? (masalan: 2 xona, studio)",
        reply_markup=ReplyKeyboardMarkup([[BTN_AI_CONCIERGE_END]], resize_keyboard=True),
    )
    return VALUATION_XONA


async def valuation_xona_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await try_escape_to_menu(update, context):
        context.user_data.pop("valuation", None)
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("⚠️ Iltimos, matn ko'rinishida yozing.")
        return VALUATION_XONA
    context.user_data.setdefault("valuation", {"photos": []})["xona"] = text[:60]
    await update.message.reply_text(
        "✅ Uyning holati/qulayliklari qanday? (masalan: yevroremont, mebel bor, yangi uy)"
    )
    return VALUATION_CONDITION


async def valuation_condition_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await try_escape_to_menu(update, context):
        context.user_data.pop("valuation", None)
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    context.user_data.setdefault("valuation", {"photos": []})["condition"] = text[:900]
    await update.message.reply_text(
        f"\U0001F4F8 Ixtiyoriy: uyning 1-{MAX_VALUATION_PHOTOS} ta rasmini yuboring (AI holatini ham hisobga oladi) - "
        "yoki quyidagi tugma bilan o'tkazib yuboring.",
        reply_markup=_PHOTO_KEYBOARD,
    )
    return VALUATION_PHOTOS


async def valuation_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    val = context.user_data.setdefault("valuation", {"photos": []})
    photos = val.setdefault("photos", [])
    if update.message.photo and len(photos) < MAX_VALUATION_PHOTOS:
        photos.append(update.message.photo[-1].file_id)
    if len(photos) >= MAX_VALUATION_PHOTOS:
        await update.message.reply_text(f"✅ {MAX_VALUATION_PHOTOS} ta rasm qabul qilindi.")
        return await _finish_valuation(update, context)
    await update.message.reply_text(
        f"✅ Qabul qilindi ({len(photos)}/{MAX_VALUATION_PHOTOS}). Yana yuborishingiz yoki «{BTN_VALUATION_DONE_PHOTOS}» bosishingiz mumkin.",
        reply_markup=_PHOTO_KEYBOARD,
    )
    return VALUATION_PHOTOS


async def valuation_photos_finish_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await try_escape_to_menu(update, context):
        context.user_data.pop("valuation", None)
        return ConversationHandler.END
    return await _finish_valuation(update, context)


async def _generate_and_send_valuation(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int,
                                        district: str, xona: str, condition: str, photo_file_ids: list) -> bool:
    """AI orqali baholab, natijani foydalanuvchiga yuboradi - bepul (darhol
    ishlaydigan) va pullik-tasdiqlangan (admin/AI to'lovni tasdiqlagandan
    keyin ishlaydigan) yo'llarning IKKALASI ham shu bitta funksiyadan
    foydalanadi - mantiq ikki joyda takrorlanmaydi. Muvaffaqiyatli
    bo'lsa True."""
    photos = []
    for file_id in photo_file_ids:
        raw = await download_photo_bytes(file_id)
        if raw:
            photos.append((raw, "image/jpeg"))

    comps = find_comparable_listings(district, xona)
    result = ai_valuate_property(district, xona, condition, comps, photos)

    if not result:
        try:
            await context.bot.send_message(
                chat_id, "⚠️ Baholashda vaqtinchalik texnik nosozlik. Birozdan keyin qayta urinib ko'ring.",
                reply_markup=main_menu_keyboard(user_id),
            )
        except Exception:
            logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi")
        return False

    save_valuation_request(user_id, "bot", district, xona, condition, result)

    comps_note = (
        f"\U0001F4CA Tahlil {len(comps)} ta shu tuman/xonadagi faol e'longa asoslandi."
        if comps else "⚠️ Shu tuman/xonada solishtirish uchun faol e'lon topilmadi - taxmin keng chegarada berildi."
    )
    text = (
        f"\U0001F3F7 <b>Taxminiy ijara narxi:</b> {result['price_low']} — {result['price_high']}\n"
        f"\U0001F3AF Ishonchlilik darajasi: {result['confidence']}\n\n"
        f"{result['reasoning']}\n\n"
        f"{comps_note}\n\n"
        "<i>⚠️ Bu AI tomonidan berilgan taxminiy yo'l-yo'riq, professional baholash emas.</i>\n\n"
        f"Uyingizni shu narxda joylashtirmoqchimisiz? «{BTN_ELON}» tugmasini bosing!"
    )
    try:
        await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(user_id))
    except Exception:
        logger.exception("Baholash natijasini yuborib bo'lmadi")
    return True


async def _finish_valuation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    val = context.user_data.get("valuation") or {}
    district = val.get("district", "")
    xona = val.get("xona", "")
    condition = val.get("condition", "")
    photo_file_ids = val.get("photos", [])
    context.user_data.pop("valuation", None)

    if not has_prior_valuation(user.id):
        await context.bot.send_chat_action(update.effective_chat.id, "typing")
        await _generate_and_send_valuation(context, user.id, update.effective_chat.id, district, xona, condition, photo_file_ids)
        return ConversationHandler.END

    # MUHIM: birinchi baholash HAR DOIM bepul - keyingilari pullik (admin
    # "valuation_price" sozlamasida narxni belgilaydi). To'lov oqimi
    # bot/flow_subscription.py bilan bir xil naqsh: karta ko'rsatiladi,
    # chek so'raladi, AI oldindan tekshiradi, mos kelsa darhol davom
    # etadi, mos kelmasa/AI o'chirilgan bo'lsa admin qo'lda tasdiqlaydi.
    price = int(get_setting("valuation_price", "10000"))
    context.user_data["valuation_pending_payment"] = {"district": district, "xona": xona, "condition": condition, "photos": photo_file_ids}
    await update.message.reply_text(
        "ℹ️ Birinchi baholashingiz allaqachon bepul ishlatilgan - keyingi baholashlar pullik.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text(
        card_html(price, "Uy baholash"), parse_mode=ParseMode.HTML, reply_markup=card_payment_keyboard("nav_cancel"),
    )
    return VALUATION_RECEIPT_WAIT


async def valuation_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("⚠️ Iltimos, to'lov chekining skrinshotini RASM sifatida yuboring.")
        return VALUATION_RECEIPT_WAIT

    user = update.effective_user
    pending = context.user_data.get("valuation_pending_payment")
    if not pending:
        context.user_data.pop("valuation_pending_payment", None)
        return ConversationHandler.END

    receipt_file_id = update.message.photo[-1].file_id
    price = int(get_setting("valuation_price", "10000"))

    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    receipt_check = None
    try:
        receipt_bytes = await download_photo_bytes(receipt_file_id)
        if receipt_bytes:
            receipt_check = ai_check_receipt(receipt_bytes, "image/jpeg", price, CARD_HOLDER)
    except Exception:
        logger.exception("AI uy baholash chekini tekshirishda xatolik")

    if receipt_check and receipt_check.get("matches"):
        await update.message.reply_text("✅ To'lov tasdiqlandi! Baholanmoqda...", reply_markup=main_menu_keyboard(user.id))
        await _generate_and_send_valuation(
            context, user.id, update.effective_chat.id, pending["district"], pending["xona"], pending["condition"], pending["photos"],
        )
        context.user_data.pop("valuation_pending_payment", None)
        return ConversationHandler.END

    payment_id = save_valuation_payment(
        user.id, "bot", pending["district"], pending["xona"], pending["condition"], pending["photos"], receipt_file_id,
    )
    context.user_data.pop("valuation_pending_payment", None)
    await update.message.reply_text(
        "\U0001F4E8 Chekingiz adminga tekshirish uchun yuborildi. Tasdiqlangach, baholash natijasi shu yerga keladi.",
        reply_markup=main_menu_keyboard(user.id),
    )
    ai_note = f"\n\n\U0001F916⚠️ AI: {esc(receipt_check.get('note') or '')}" if receipt_check else ""
    admin_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"valpay_approve_{payment_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"valpay_reject_{payment_id}"),
    ]])
    caption = (
        f"\U0001F3F7 <b>Yangi pullik uy baholash so'rovi</b> #{payment_id}\n\n"
        f"\U0001F464 {esc(user.full_name)} (@{esc(user.username) or 'yo`q'})\n"
        f"\U0001F194 user_id: {user.id}\n"
        f"\U0001F3D8 Tuman: {esc(pending['district'])} · {esc(pending['xona'])} xona\n"
        f"\U0001F4B0 Summasi: {price:,} so'm"
        f"{ai_note}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(admin_id, receipt_file_id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=admin_keyboard)
        except Exception:
            logger.exception("Adminga (%s) to'lov so'rovini yuborib bo'lmadi", admin_id)
    return ConversationHandler.END


async def valuation_receipt_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("valuation_pending_payment", None)
    await query.edit_message_text("❌ Bekor qilindi.")
    return ConversationHandler.END


async def valpay_approve_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_moderator(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q — to'lovlarni faqat admin yoki super moderator tasdiqlay oladi.", show_alert=True)
        return
    payment_id = int(query.data.rsplit("_", 1)[1])
    payment = get_valuation_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ Bu so'rov allaqachon ko'rib chiqilgan.")
        return
    update_valuation_payment_status(payment_id, "approved")
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"✅ To'lov #{payment_id} tasdiqlandi, baholash yuborilmoqda...")
    await _generate_and_send_valuation(
        context, payment["user_id"], payment["user_id"],
        payment["district"], payment["xona"], payment["condition_text"], payment["photo_file_ids"],
    )


async def valpay_reject_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_moderator(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q — to'lovlarni faqat admin yoki super moderator rad eta oladi.", show_alert=True)
        return
    payment_id = int(query.data.rsplit("_", 1)[1])
    payment = get_valuation_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ Bu so'rov allaqachon ko'rib chiqilgan.")
        return
    update_valuation_payment_status(payment_id, "rejected")
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"❌ To'lov #{payment_id} rad etildi.")
    try:
        await context.bot.send_message(
            payment["user_id"],
            "❌ Uy baholash uchun to'lovingiz tasdiqlanmadi. Chekni tekshirib qaytadan urinib ko'ring yoki qo'llab-quvvatlash bilan bog'laning.",
        )
    except Exception:
        logger.exception("Foydalanuvchiga rad etish xabarini yuborib bo'lmadi")


async def valuation_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("valuation", None)
    context.user_data.pop("valuation_pending_payment", None)
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END
