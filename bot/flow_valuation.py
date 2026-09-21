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

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from common.ai import ai_features_enabled, ai_valuate_property
from common.ai_agent import find_comparable_listings
from common.db import count_today_valuations, save_valuation_request
from common.districts import TASHKENT_DISTRICTS
from common.telegram_media import download_photo_bytes

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403
from bot.fraud_detection import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

MAX_VALUATION_PHOTOS = 3
DAILY_VALUATION_LIMIT = 5

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
    if count_today_valuations(user.id, "bot") >= DAILY_VALUATION_LIMIT:
        await update.message.reply_text(
            "⚠️ Bugungi baholash so'rovlari chegarasiga yetdingiz. Ertaga qayta urinib ko'ring.",
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


async def _finish_valuation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    val = context.user_data.get("valuation") or {}
    district = val.get("district", "")
    xona = val.get("xona", "")
    condition = val.get("condition", "")
    photo_file_ids = val.get("photos", [])

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    photos = []
    for file_id in photo_file_ids:
        raw = await download_photo_bytes(file_id)
        if raw:
            photos.append((raw, "image/jpeg"))

    comps = find_comparable_listings(district, xona)
    result = ai_valuate_property(district, xona, condition, comps, photos)

    context.user_data.pop("valuation", None)

    if not result:
        await update.message.reply_text(
            "⚠️ Baholashda vaqtinchalik texnik nosozlik. Birozdan keyin qayta urinib ko'ring.",
            reply_markup=main_menu_keyboard(user.id),
        )
        return ConversationHandler.END

    save_valuation_request(user.id, "bot", district, xona, condition, result)

    confidence_label = {"past": "past", "o'rta": "o'rta", "yuqori": "yuqori"}.get(result["confidence"], result["confidence"])
    comps_note = (
        f"\U0001F4CA Tahlil {len(comps)} ta shu tuman/xonadagi faol e'longa asoslandi."
        if comps else "⚠️ Shu tuman/xonada solishtirish uchun faol e'lon topilmadi - taxmin keng chegarada berildi."
    )
    text = (
        f"\U0001F3F7 <b>Taxminiy ijara narxi:</b> {result['price_low']} — {result['price_high']}\n"
        f"\U0001F3AF Ishonchlilik darajasi: {confidence_label}\n\n"
        f"{result['reasoning']}\n\n"
        f"{comps_note}\n\n"
        "<i>⚠️ Bu AI tomonidan berilgan taxminiy yo'l-yo'riq, professional baholash emas.</i>\n\n"
        f"Uyingizni shu narxda joylashtirmoqchimisiz? «{BTN_ELON}» tugmasini bosing!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(user.id))
    return ConversationHandler.END


async def valuation_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("valuation", None)
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END
