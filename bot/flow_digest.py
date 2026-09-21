"""
Kunlik AI bozor tahlili - admin tasdiqlagandan keyingina Telegram kanalga
va saytga (/bozor-yangiliklari) chiqadigan OMMAVIY post. Loyihani
bot/jobs.py'dagi job_generate_market_digest tayyorlab adminlarga
yuboradi; shu yerdagi ikkita router o'sha xabardagi ✅/❌ tugmalarini
qayta ishlaydi - Laziz o'zi tanlagan rejim: hech qachon avtomatik
e'lon qilinmaydi, doim avval admin/super moderator tasdiqlaydi.
"""
import logging

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from common.config import BOT_TOKEN, CHANNEL_ID, CHANNEL_USERNAME
from common.db import get_market_digest, now_str, update_market_digest_status

from bot.helpers import is_super_moderator

logger = logging.getLogger(__name__)


async def digest_approve_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_moderator(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q — faqat admin yoki super moderator tasdiqlay oladi.", show_alert=True)
        return
    digest_id = int(query.data.rsplit("_", 1)[1])
    digest = get_market_digest(digest_id)
    if not digest or digest["status"] != "draft":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ Bu loyiha allaqachon ko'rib chiqilgan.")
        return
    if not BOT_TOKEN or not CHANNEL_ID:
        await query.message.reply_text("⚠️ Kanal sozlanmagan — joylab bo'lmadi.")
        return

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": CHANNEL_ID, "text": digest["content"]},
            )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description", "Telegram xatoligi"))
    except Exception:
        logger.exception("Bozor digestini kanalga joylab bo'lmadi (id=%s)", digest_id)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"❌ Kanalga joylab bo'lmadi (#{digest_id}). Qaytadan urinib ko'ring.")
        return

    update_market_digest_status(digest_id, "posted", now_str())
    await query.edit_message_reply_markup(reply_markup=None)
    link = f"https://t.me/{CHANNEL_USERNAME}" if CHANNEL_USERNAME else None
    msg = f"✅ Bozor tahlili #{digest_id} kanalga joylandi!"
    if link:
        msg += f"\n{link}"
    await query.message.reply_text(msg)


async def digest_reject_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_moderator(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q — faqat admin yoki super moderator bekor qila oladi.", show_alert=True)
        return
    digest_id = int(query.data.rsplit("_", 1)[1])
    digest = get_market_digest(digest_id)
    if not digest or digest["status"] != "draft":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ Bu loyiha allaqachon ko'rib chiqilgan.")
        return
    update_market_digest_status(digest_id, "rejected")
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"❌ Bozor tahlili #{digest_id} bekor qilindi.")
