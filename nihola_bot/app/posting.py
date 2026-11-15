"""Kanalga joylash, postni yangilash, bot ichida kartochka va albom yuborish."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    FSInputFile, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, Message,
)

from .config import settings
from .db import Database
from .keyboards import channel_kb, private_card_kb
from .texts import CAPTION_LIMIT, build_post, visible_len

log = logging.getLogger(__name__)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _media_input(row: dict):
    """Suv belgili fayl hali yuklanmagan bo'lsa — diskdan, aks holda file_id orqali."""
    if not row["ready"] and row.get("local_path"):
        return FSInputFile(row["local_path"])
    return row["file_id"]


def _file_id_of(msg: Message) -> str | None:
    if msg.photo:
        return msg.photo[-1].file_id
    if msg.video:
        return msg.video.file_id
    return None


async def _capture(db: Database, row: dict, msg: Message) -> None:
    if not row["ready"]:
        fid = _file_id_of(msg)
        if fid:
            await db.update_media(row["id"], file_id=fid, ready=1)
            row["file_id"], row["ready"] = fid, 1


async def send_media_item(
    bot: Bot, db: Database, chat_id, row: dict, caption: str | None = None,
    kb: InlineKeyboardMarkup | None = None,
) -> Message:
    kw = dict(caption=caption, reply_markup=kb)
    if row["kind"] == "video":
        msg = await bot.send_video(chat_id, _media_input(row), **kw)
    else:
        msg = await bot.send_photo(chat_id, _media_input(row), **kw)
    await _capture(db, row, msg)
    return msg


async def send_post(
    bot: Bot, db: Database, chat_id, listing: dict, media: list[dict],
    kb: InlineKeyboardMarkup | None, prefix: str = "",
) -> tuple[Message, str]:
    """Bitta e'lonni yuboradi: asosiy rasm + matn + tugmalar.

    Matn 1024 belgidan uzun bo'lsa, rasm alohida, matn tugmalar bilan alohida ketadi.
    Qaytaradi: (tugmali xabar, 'media' yoki 'text').
    """
    text = prefix + build_post(listing)
    if media:
        if visible_len(text) <= CAPTION_LIMIT:
            return await send_media_item(bot, db, chat_id, media[0], text, kb), "media"
        await send_media_item(bot, db, chat_id, media[0])
    return await bot.send_message(chat_id, text, reply_markup=kb), "text"


async def send_gallery(bot: Bot, db: Database, chat_id, media: list[dict]) -> list[Message]:
    """Barcha rasm/videolarni albom qilib yuboradi (10 tadan). Yuborilgan xabarlarni qaytaradi."""
    sent: list[Message] = []
    for start in range(0, len(media), 10):
        chunk = media[start:start + 10]
        if len(chunk) == 1:
            sent.append(await send_media_item(bot, db, chat_id, chunk[0]))
            continue
        group = [
            InputMediaVideo(media=_media_input(r)) if r["kind"] == "video"
            else InputMediaPhoto(media=_media_input(r))
            for r in chunk
        ]
        msgs = await bot.send_media_group(chat_id, group)
        sent.extend(msgs)
        for row, msg in zip(chunk, msgs):
            await _capture(db, row, msg)
    return sent


async def send_channel_style(
    bot: Bot, db: Database, chat_id, listing: dict, media: list[dict], with_media: bool = True,
) -> Message:
    """Kanal formati: avval rasm/videolar albomi, keyin e'lon matni tugmalar bilan alohida xabar."""
    sent = await send_gallery(bot, db, chat_id, media) if (media and with_media) else []
    try:
        return await bot.send_message(
            chat_id, build_post(listing), reply_markup=channel_kb(listing, len(media)))
    except Exception:
        for m in sent:  # matn ketmasa — kanalda "yetim" rasmlar qolmasin
            try:
                await bot.delete_message(chat_id, m.message_id)
            except Exception:
                pass
        raise


async def send_card(bot: Bot, db: Database, chat_id, listing: dict, prefix: str = "") -> Message:
    """Bot ichida (shaxsiy chatda) e'lon kartochkasi."""
    media = await db.get_media(listing["id"])
    msg, _ = await send_post(bot, db, chat_id, listing, media,
                             private_card_kb(listing, len(media)), prefix)
    return msg


async def publish_listing(bot: Bot, db: Database, listing_id: int) -> dict:
    listing = await db.get_listing(listing_id)
    media = await db.get_media(listing_id)
    listing["status"] = "active"
    msg = await send_channel_style(bot, db, settings.channel_id, listing, media)
    await db.update_listing(
        listing_id, status="active", channel_msg_id=msg.message_id,
        channel_post_kind="text", published_at=utcnow_iso(),
    )
    return await db.get_listing(listing_id)


async def refresh_channel_post(bot: Bot, db: Database, listing_id: int) -> bool:
    """Narx yoki holat o'zgarganda kanaldagi postni tahrirlaydi."""
    listing = await db.get_listing(listing_id)
    if not listing or not listing.get("channel_msg_id"):
        return False
    count = await db.media_count(listing_id)
    text = build_post(listing)
    kb = channel_kb(listing, count)
    try:
        if listing["channel_post_kind"] == "media":
            await bot.edit_message_caption(
                chat_id=settings.channel_id, message_id=listing["channel_msg_id"],
                caption=text, reply_markup=kb)
        else:
            await bot.edit_message_text(
                text, chat_id=settings.channel_id, message_id=listing["channel_msg_id"],
                reply_markup=kb)
        return True
    except TelegramBadRequest as e:
        if "not modified" in str(e):
            return True
        log.warning("Kanal posti #%s tahrirlanmadi: %s", listing_id, e)
        return False


def explain_channel_error(e: Exception) -> str:
    """Telegram xatosini oddiy tilda tushuntiradi."""
    t = str(e).lower()
    if "chat not found" in t:
        return ("Kanal topilmadi. .env dagi CHANNEL_ID ni tekshiring: ochiq kanal bo‘lsa @username, "
                "yopiq bo‘lsa -100 bilan boshlanadigan raqam. Bot kanalga qo‘shilgan bo‘lishi ham shart.")
    if "not enough rights" in t or "administrator" in t or "not a member" in t or "forbidden" in t:
        return ("Botda kanalga yozish huquqi yo‘q. Kanal → Administratorlar → botni admin qiling va "
                "«Xabar joylash» hamda «Xabarlarni tahrirlash» huquqlarini yoqing.")
    if "wrong file identifier" in t or "wrong remote file" in t:
        return "Rasm fayli topilmadi. E’lonni rasmlarni qayta yuklab yarating."
    return "Noma’lum xato. Shu xabarni dasturchiga yuboring."


async def check_channel(bot: Bot) -> tuple[bool, str]:
    """Bot kanalga post joylay oladimi — tekshiradi va hisobot qaytaradi."""
    try:
        chat = await bot.get_chat(settings.channel_id)
    except Exception as e:
        return False, f"❌ Kanal: {settings.channel_id}\n{explain_channel_error(e)}\n<code>{e}</code>"
    me = await bot.me()
    try:
        member = await bot.get_chat_member(chat.id, me.id)
    except Exception as e:
        return False, f"❌ Kanal «{chat.title}» topildi, lekin bot a’zo emas.\n<code>{e}</code>"
    if member.status != "administrator":
        return False, (f"❌ Kanal «{chat.title}» topildi, lekin bot <b>admin emas</b> (holati: {getattr(member.status, "value", member.status)}).\n"
                       "Kanal → Administratorlar → Admin qo‘shish → botni tanlang.")
    missing = []
    if not getattr(member, "can_post_messages", False):
        missing.append("«Xabar joylash» (Post messages)")
    if not getattr(member, "can_edit_messages", False):
        missing.append("«Boshqalarning xabarlarini tahrirlash» (Edit messages)")
    if missing:
        return False, (f"⚠️ Bot «{chat.title}» kanalida admin, lekin quyidagi huquq(lar) o‘chiq:\n• "
                       + "\n• ".join(missing))
    return True, f"✅ Hammasi joyida: bot «{chat.title}» kanaliga post joylay oladi."
