"""
Mijozlar fikri (testimonial) - foydalanuvchi botga fikr-mulohaza yuboradi
(matn, ixtiyoriy 1 ta rasm bilan), admin ko'rib chiqadi va:
  - shunchaki tasdiqlashi,
  - tasdiqlab kanalga post sifatida joylashi, yoki
  - rad etishi mumkin.

MUHIM (Telegram Bot API cheklovi): kanal "Stories"siga avtomatik joylash
ODDIY BOT orqali MUMKIN EMAS - Bot API'ning postStory/repostStory metodlari
FAQAT shaxsiy "Business" akkauntlar uchun ishlaydi, kanallar uchun esa bunday
metod umuman yo'q (kanal story'sini faqat shu kanalning admin-INSONI, odatiy
Telegram ilovasidan, "boost" to'plangan kanalda qo'lda joylay oladi). Shuning
uchun bu yerda faqat ODDIY kanal postiga joylash qilingan - admin xohlasa,
shu tayyor postni o'z ilovasidan "Repost as story" orqali qo'lda storiga
qo'yishi mumkin (buning uchun qo'shimcha kod kerak emas).
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from common.config import CHANNEL_ID

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403
from bot.fraud_detection import send_with_retry, try_escape_to_menu  # noqa: F401

logger = logging.getLogger(__name__)

MAX_FEEDBACK_LEN = 1000


async def feedback_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="nav_cancel")]])
    await update.message.reply_text(
        "\U0001F4AC <b>Fikringizni yozing</b>\n\n"
        "Xizmatimiz haqidagi fikr-mulohazangiz boshqa foydalanuvchilar uchun ham qadrli! "
        "Xohlasangiz, 1 ta rasm biriktirib, izohini shu yerga yozishingiz mumkin.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
    return FEEDBACK_TEXT


async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Bekor qilindi.")
    return ConversationHandler.END


async def feedback_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await try_escape_to_menu(update, context):
        return ConversationHandler.END

    user = update.effective_user
    photo_file_id = None
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
        text = (update.message.caption or "").strip()
    else:
        text = (update.message.text or "").strip()

    if not text:
        await update.message.reply_text(
            "⚠️ Iltimos, fikringizni matn ko'rinishida yozing"
            + (" (rasm ostiga izoh qilib yozsangiz ham bo'ladi)." if update.message.photo else ".")
        )
        return FEEDBACK_TEXT

    text = text[:MAX_FEEDBACK_LEN]
    testimonial_id = save_testimonial(user.id, user.full_name, user.username, text, photo_file_id)

    await update.message.reply_text(
        "✅ Rahmat! Fikringiz qabul qilindi va ko'rib chiqilgandan so'ng kanalga joylanishi mumkin.",
        reply_markup=main_menu_keyboard(user.id),
    )

    admin_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001F4E2 Tasdiqlash + kanalga joylash", callback_data=f"fbapprovepost_{testimonial_id}")],
        [
            InlineKeyboardButton("✅ Faqat tasdiqlash", callback_data=f"fbapprove_{testimonial_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"fbreject_{testimonial_id}"),
        ],
    ])
    caption = (
        f"\U0001F4AC <b>Yangi mijoz fikri</b> #{testimonial_id}\n\n"
        f"\U0001F464 {esc(user.full_name)} (@{esc(user.username) or 'yo`q'})\n"
        f"\U0001F194 user_id: {user.id}\n\n"
        f"“{esc(text)}”"
    )
    for admin_id in all_staff_ids():
        try:
            if photo_file_id:
                await send_with_retry(context.bot.send_photo, admin_id, photo_file_id, caption=caption,
                                       parse_mode=ParseMode.HTML, reply_markup=admin_keyboard)
            else:
                await send_with_retry(context.bot.send_message, admin_id, caption,
                                       parse_mode=ParseMode.HTML, reply_markup=admin_keyboard)
        except Exception:
            logger.exception("Adminga (%s) mijoz fikri bildirishnomasini yuborishda xatolik", admin_id)
    return ConversationHandler.END


def _testimonial_card(t: dict) -> str:
    name = esc((t.get("full_name") or "").strip() or (f"@{t['username']}" if t.get("username") else "Mijoz"))
    return f"⭐️ <b>Mijoz fikri</b>\n\n“{esc(t['text'])}”\n\n— {name}"


async def testimonial_approve_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    testimonial_id = int(query.data.rsplit("_", 1)[1])
    t = get_testimonial(testimonial_id)
    if not t or t["status"] != "pending":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ Bu fikr allaqachon ko'rib chiqilgan.")
        return
    update_testimonial_status(testimonial_id, "approved")
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"✅ Fikr #{testimonial_id} tasdiqlandi (kanalga joylanmadi).")


async def testimonial_approve_post_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    testimonial_id = int(query.data.rsplit("_", 1)[1])
    t = get_testimonial(testimonial_id)
    if not t or t["status"] != "pending":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ Bu fikr allaqachon ko'rib chiqilgan.")
        return
    update_testimonial_status(testimonial_id, "approved")
    caption = _testimonial_card(t)
    channel_message_id = None
    try:
        if not CHANNEL_ID:
            raise RuntimeError("CHANNEL_ID sozlanmagan")
        if t.get("photo_file_id"):
            msg = await send_with_retry(context.bot.send_photo, CHANNEL_ID, t["photo_file_id"], caption=caption, parse_mode=ParseMode.HTML)
        else:
            msg = await send_with_retry(context.bot.send_message, CHANNEL_ID, caption, parse_mode=ParseMode.HTML)
        channel_message_id = msg.message_id
        set_testimonial_channel_post(testimonial_id, channel_message_id)
    except Exception:
        logger.exception("Mijoz fikrini kanalga joylashda xatolik")

    await query.edit_message_reply_markup(reply_markup=None)
    if channel_message_id:
        await query.message.reply_text(f"✅\U0001F4E2 Fikr #{testimonial_id} tasdiqlandi va kanalga joylandi.")
        try:
            await context.bot.send_message(
                t["user_id"],
                "\U0001F389 Fikringiz tasdiqlandi va kanalimizga joylandi! Qo'llab-quvvatlaganingiz uchun rahmat.",
            )
        except Exception:
            pass
    else:
        await query.message.reply_text(f"⚠️ Fikr #{testimonial_id} tasdiqlandi, lekin kanalga joylashda xatolik yuz berdi.")


async def testimonial_reject_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    testimonial_id = int(query.data.rsplit("_", 1)[1])
    t = get_testimonial(testimonial_id)
    if not t or t["status"] != "pending":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ Bu fikr allaqachon ko'rib chiqilgan.")
        return
    update_testimonial_status(testimonial_id, "rejected")
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"❌ Fikr #{testimonial_id} rad etildi.")
