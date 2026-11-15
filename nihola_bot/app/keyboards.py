"""Barcha tugmalar (kanal posti ostidagi, bot ichidagi va menyular)."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import constants as C
from .config import runtime, settings


# ---------- havolalar ----------
def deep_link(payload: str) -> str:
    return f"https://t.me/{runtime.bot_username}?start={payload}"


def map_url(listing: dict) -> str | None:
    if listing.get("lat") is None or listing.get("lng") is None:
        return None
    return f"https://maps.google.com/?q={listing['lat']},{listing['lng']}"


def channel_post_url(listing: dict) -> str | None:
    msg_id = listing.get("channel_msg_id")
    if not msg_id:
        return None
    if settings.channel_public_username:
        return f"https://t.me/{settings.channel_public_username}/{msg_id}"
    cid = str(settings.channel_id)
    if cid.startswith("-100"):
        return f"https://t.me/c/{cid[4:]}/{msg_id}"
    return None


def realtor_url() -> str | None:
    return f"https://t.me/{settings.realtor_username}" if settings.realtor_username else None


# ---------- kanal posti ostidagi tugmalar ----------
def channel_kb(listing: dict, media_count: int) -> InlineKeyboardMarkup | None:
    """Kanal postidagi tugmalar. Hammasi mijozni botga olib kiradi (deep-link)."""
    if listing.get("status") == "sold":
        return None
    lid = listing["id"]
    rows = []
    row = [InlineKeyboardButton(text="📞 Bog‘lanish", url=deep_link(f"call_{lid}"))]
    if map_url(listing):
        row.append(InlineKeyboardButton(text="🗺 Xaritada", url=map_url(listing)))
    rows.append(row)
    rows.append([
        InlineKeyboardButton(text="❤️ Saqlash", url=deep_link(f"save_{lid}")),
        InlineKeyboardButton(text="🔔 O‘xshash uylar", url=deep_link(f"sim_{lid}")),
    ])
    if media_count > 1:
        rows.append([InlineKeyboardButton(
            text=f"📸 Barcha rasmlar ({media_count})", url=deep_link(f"pics_{lid}"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- bot ichidagi e'lon kartochkasi ----------
def private_card_kb(listing: dict, media_count: int) -> InlineKeyboardMarkup:
    lid = listing["id"]
    b = InlineKeyboardBuilder()
    if listing.get("status") != "sold":
        b.row(
            InlineKeyboardButton(text="📞 Bog‘lanish", callback_data=f"u:call:{lid}"),
            InlineKeyboardButton(text="❤️ Saqlash", callback_data=f"u:save:{lid}"),
        )
    second = [InlineKeyboardButton(text="🔔 O‘xshash uylar", callback_data=f"u:sim:{lid}")]
    if map_url(listing):
        second.append(InlineKeyboardButton(text="🗺 Xaritada", url=map_url(listing)))
    b.row(*second)
    if media_count > 1:
        b.row(InlineKeyboardButton(
            text=f"📸 Barcha rasmlar ({media_count})", callback_data=f"u:pics:{lid}"))
    if channel_post_url(listing):
        b.row(InlineKeyboardButton(text="📢 Kanalda ko‘rish", url=channel_post_url(listing)))
    return b.as_markup()


# ---------- menyular ----------
def user_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text=C.BTN_SEARCH), KeyboardButton(text=C.BTN_FILTER)],
        [KeyboardButton(text=C.BTN_SAVED), KeyboardButton(text=C.BTN_CONTACT)],
        [KeyboardButton(text=C.BTN_SELL)],
    ]
    if is_admin:
        kb.append([KeyboardButton(text=C.BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=C.BTN_NEW), KeyboardButton(text=C.BTN_LIST)],
            [KeyboardButton(text=C.BTN_STATS), KeyboardButton(text=C.BTN_BCAST)],
            [KeyboardButton(text=C.BTN_USERMODE)],
        ],
        resize_keyboard=True,
    )


def phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=C.BTN_SEND_PHONE, request_contact=True)],
            [KeyboardButton(text=C.BTN_NO_PHONE)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids
