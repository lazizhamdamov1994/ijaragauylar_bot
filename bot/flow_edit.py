"""
Foydalanuvchining o'z e'lonini tahrirlash/o'chirish - "Mening e'lonlarim"
bo'limidan boshlanadi. Tasdiqlangan (kanalga chiqqan) e'lon tahrirlansa,
kanaldagi post ham (caption) YANGILANADI - shu orqali foydalanuvchi narxni
o'zgartirish uchun butunlay YANGI e'lon yuborish shart bo'lmaydi.
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

# MUHIM: telefon va rasmlar bu yerdan o'zgartirilmaydi (v1 doirasidan
# tashqarida) - faqat matnli maydonlar. STEPS (bot/constants.py, e'lon
# yaratish bosqichlari) dagi prompt/maxlen shu yerda QAYTA ishlatiladi -
# ikkinchi nusxa yozib, ikkalasi orasida moslik yo'qolish xavfini yo'q qiladi.
EDIT_FIELD_META = {s["field"]: s for s in STEPS if s["field"] in ("manzil", "moljal", "kimlarga", "xona", "qulaylik", "narx")}
EDIT_FIELD_LABELS = {
    "manzil": "\U0001F4CD Manzil", "moljal": "\U0001F3AF Mo'ljal", "kimlarga": "\U0001F465 Kimlarga beriladi",
    "xona": "\U0001F6CF Xonalar soni", "qulaylik": "✅ Sharoitlari", "narx": "\U0001F4B0 Narxi",
}


async def _sync_channel_caption(context: ContextTypes.DEFAULT_TYPE, listing_id: int) -> None:
    """E'lon TASDIQLANGAN va kanalda bo'lsa, kanaldagi postning matnini
    (caption) yangi ma'lumotlar bilan qayta yozadi. Xatolik bo'lsa (masalan
    xabar juda eski/o'chirilgan) jim o'tkaziladi - bazadagi tahrirlash
    baribir saqlanadi, bu yerdagi muvaffaqiyatsizlik uni bekor qilmaydi."""
    listing = get_listing(listing_id)
    if not listing or listing["status"] != "approved" or not listing.get("channel_msg_id"):
        return
    try:
        caption = build_caption(listing, context.bot.username)
        keyboard = channel_keyboard(listing_id, context.bot.username, listing.get("latitude"), listing.get("longitude"))
        await context.bot.edit_message_text(
            chat_id=CHANNEL_ID, message_id=listing["channel_msg_id"], text=caption,
            parse_mode=ParseMode.HTML, reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Kanaldagi postni yangilashda xatolik (listing_id=%s)", listing_id)


def _edit_menu_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"editfield_{listing_id}_{field}")] for field, label in EDIT_FIELD_LABELS.items()]
    rows.append([InlineKeyboardButton("❌ Bekor qilish", callback_data=f"editcancelmenu_{listing_id}")])
    return InlineKeyboardMarkup(rows)


async def editlisting_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    listing_id = int(query.data.rsplit("_", 1)[1])
    listing = get_listing(listing_id)
    if not listing or listing["user_id"] != query.from_user.id:
        await query.answer("Bu sizning e'loningiz emas.", show_alert=True)
        return
    await query.message.reply_text(
        f"✏️ <b>E'lon #{listing_id}ni tahrirlash</b>\n\nQaysi maydonni o'zgartirmoqchisiz?",
        parse_mode=ParseMode.HTML, reply_markup=_edit_menu_keyboard(listing_id),
    )


async def editcancelmenu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass


async def editfield_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, listing_id, field = query.data.split("_", 2)
    listing_id = int(listing_id)
    listing = get_listing(listing_id)
    if not listing or listing["user_id"] != query.from_user.id:
        await query.answer("Bu sizning e'loningiz emas.", show_alert=True)
        return ConversationHandler.END
    meta = EDIT_FIELD_META.get(field)
    if not meta:
        return ConversationHandler.END
    context.user_data["editing_listing"] = {"id": listing_id, "field": field, "maxlen": meta["maxlen"]}
    current = listing.get(field) or "—"
    await query.message.reply_text(
        f"Joriy qiymat: <b>{esc(current)}</b>\n\nYangisini yozing:\n\n{meta['prompt']}",
        parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove(),
    )
    return EDIT_LISTING_VALUE


async def editfield_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        context.user_data.pop("editing_listing", None)
        return ConversationHandler.END

    editing = context.user_data.get("editing_listing")
    if not editing:
        return ConversationHandler.END

    raw = (update.message.text or "").strip()
    if not raw:
        await update.message.reply_text("⚠️ Bo'sh bo'lishi mumkin emas. Qaytadan yozing:")
        return EDIT_LISTING_VALUE
    if len(raw) > editing["maxlen"]:
        await update.message.reply_text(f"⚠️ Juda uzun ({len(raw)} belgi). {editing['maxlen']} belgidan qisqaroq yozing:")
        return EDIT_LISTING_VALUE

    update_listing_fields(editing["id"], {editing["field"]: raw})
    await _sync_channel_caption(context, editing["id"])
    context.user_data.pop("editing_listing", None)
    await update.message.reply_text(
        f"✅ E'lon #{editing['id']} yangilandi.",
        reply_markup=main_menu_keyboard(update.effective_user.id),
    )
    return ConversationHandler.END


async def editfield_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("editing_listing", None)
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END


# ============================= O'CHIRISH (butunlay, qaytarib bo'lmaydi) =============================

async def deletelisting_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    listing_id = int(query.data.rsplit("_", 1)[1])
    listing = get_listing(listing_id)
    if not listing or listing["user_id"] != query.from_user.id:
        await query.answer("Bu sizning e'loningiz emas.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Ha, butunlay o'chirish", callback_data=f"deletelistingyes_{listing_id}"),
         InlineKeyboardButton("❌ Yo'q", callback_data=f"editcancelmenu_{listing_id}")],
    ])
    await query.message.reply_text(
        f"Rostdan ham #{listing_id} e'lonni butunlay o'chirasizmi?\n<i>Bu amalni ortga qaytarib bo'lmaydi («topshirildi» deb belgilashdan farqli).</i>",
        parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )


async def deletelisting_confirm_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    listing_id = int(query.data.rsplit("_", 1)[1])
    listing = get_listing(listing_id)
    if not listing or listing["user_id"] != query.from_user.id:
        await query.answer("Bu sizning e'loningiz emas.", show_alert=True)
        return
    if listing.get("channel_msg_id"):
        try:
            await context.bot.delete_message(CHANNEL_ID, listing["channel_msg_id"])
        except Exception:
            logger.exception("Kanaldagi postni o'chirishda xatolik (listing_id=%s)", listing_id)
    delete_listing_row(listing_id)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text(f"\U0001F5D1 E'lon #{listing_id} butunlay o'chirildi.")
