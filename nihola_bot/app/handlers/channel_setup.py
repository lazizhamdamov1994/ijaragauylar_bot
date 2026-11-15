"""E'lonlar joylanadigan chatni (kanal yoki test guruh) avtomatik ulash.

ID'ni qo'lda qidirish shart emas:
  • botni kanal/guruhga qo'shsangiz — bot adminga ID va «✅ Ulash» tugmasini yuboradi;
  • guruhda /ulash deb yozsangiz — shu guruh darhol ulanadi;
  • kanaldan istalgan postni botga forward qilsangiz — bot kanal ID'sini ko'rsatadi.
Tanlangan ID .env fayliga ham yoziladi, bot qayta ishga tushganda ham saqlanib qoladi.
"""
from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from ..config import BASE_DIR, settings
from ..posting import check_channel

log = logging.getLogger(__name__)
router = Router(name="channel_setup")


def is_admin_id(user_id: int | None) -> bool:
    return bool(user_id and user_id in settings.admin_ids)


def save_channel_id(chat_id: int) -> None:
    """CHANNEL_ID ni .env ga yozadi va ishlab turgan botda ham darhol almashtiradi."""
    env = BASE_DIR / ".env"
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    if re.search(r"(?m)^CHANNEL_ID=.*$", text):
        text = re.sub(r"(?m)^CHANNEL_ID=.*$", f"CHANNEL_ID={chat_id}", text)
    else:
        text = text.rstrip("\n") + f"\nCHANNEL_ID={chat_id}\n"
    env.write_text(text, encoding="utf-8")
    object.__setattr__(settings, "channel_id", chat_id)
    log.info("E'lonlar chati o'zgartirildi: %s", chat_id)


def connect_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ E’lonlar shu yerga joylansin", callback_data=f"ch:set:{chat_id}")
    ]])


def kind_of(chat_type: str) -> str:
    return "kanal" if chat_type == "channel" else "guruh"


# 1) Bot kanal/guruhga qo'shildi yoki admin qilindi
@router.my_chat_member()
async def bot_added(event: ChatMemberUpdated, bot: Bot) -> None:
    chat = event.chat
    if chat.type == "private":
        return
    status = getattr(event.new_chat_member.status, "value", event.new_chat_member.status)
    if status not in ("member", "administrator", "creator"):
        return
    kind = kind_of(chat.type)
    if chat.id == settings.channel_id:
        text = f"✅ Bot «{chat.title}» {kind}ida yangilandi (holati: {status}). E’lonlar shu yerga joylanmoqda."
        kb = None
    else:
        text = (f"🤖 Bot «<b>{chat.title}</b>» {kind}iga qo‘shildi (holati: {status}).\n"
                f"ID: <code>{chat.id}</code>\n\nE’lonlar shu {kind}ga joylansinmi?")
        kb = connect_kb(chat.id)
    if chat.type == "channel" and status != "administrator":
        text += "\n\n⚠️ Kanalda bot <b>admin</b> bo‘lishi va «Xabar joylash» huquqi yoqilgan bo‘lishi shart."
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb)
        except Exception as e:
            log.warning("Adminga xabar ketmadi: %s", e)


# 2) Guruhda /ulash
@router.message(Command("ulash"), F.chat.type.in_({"group", "supergroup"}))
async def connect_here(message: Message, bot: Bot) -> None:
    if not is_admin_id(message.from_user and message.from_user.id):
        await message.reply("Bu buyruq faqat bot adminlari uchun.")
        return
    save_channel_id(message.chat.id)
    ok, report = await check_channel(bot)
    await message.reply(("✅ Ulandi! E’lonlar endi shu guruhga joylanadi.\n\n" if ok else "") + report)


# 3) Kanaldan forward qilingan post
@router.message(F.chat.type == "private", F.forward_origin.type == "channel")
async def forwarded_from_channel(message: Message) -> None:
    if not is_admin_id(message.from_user.id):
        return
    chat = message.forward_origin.chat
    await message.answer(
        f"📢 Kanal: «<b>{chat.title}</b>»\nID: <code>{chat.id}</code>\n\nE’lonlar shu kanalga joylansinmi?",
        reply_markup=connect_kb(chat.id))


# 4) «✅ Ulash» tugmasi
@router.callback_query(F.data.startswith("ch:set:"))
async def connect_cb(cb: CallbackQuery, bot: Bot) -> None:
    if not is_admin_id(cb.from_user.id):
        await cb.answer("Faqat admin uchun", show_alert=True)
        return
    chat_id = int(cb.data.split(":")[2])
    save_channel_id(chat_id)
    ok, report = await check_channel(bot)
    await cb.answer("Saqlandi" if ok else "Saqlandi, lekin muammo bor", show_alert=not ok)
    await cb.message.edit_text(
        ("✅ <b>Ulandi!</b> Endi e’lonlar shu yerga joylanadi.\n\n" if ok else "⚠️ ID saqlandi, lekin:\n\n")
        + report
        + ("\n\nE’lon yaratayotgan bo‘lsangiz, ko‘rinish ostidagi <b>✅ Kanalga joylash</b> tugmasini qayta bosing." if ok else ""))


# 5) Oddiy guruh supergroup'ga aylandi — ID o'zgardi, avtomatik yangilaymiz
@router.message(F.migrate_to_chat_id)
async def group_migrated(message: Message, bot: Bot) -> None:
    if message.chat.id != settings.channel_id:
        return
    new_id = message.migrate_to_chat_id
    save_channel_id(new_id)
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(
                admin_id, f"ℹ️ «{message.chat.title}» guruhi supergroup’ga aylandi, ID yangilandi: <code>{new_id}</code>")
        except Exception:
            pass
