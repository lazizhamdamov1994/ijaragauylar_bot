from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, Seller
from app.services.errors import ConflictError, ValidationError

_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


def parse_channel_username(text: str | None) -> str:
    """'@kanal', 'kanal', 't.me/kanal', 'https://t.me/kanal/12' → '@kanal'."""
    v = (text or "").strip()
    m = re.match(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.me/([^/?#\s]+)", v)
    if m:
        v = m.group(1)
    v = v.lstrip("@")
    if not _USERNAME_RE.match(v):
        raise ValidationError("channel_bad_input")
    return "@" + v


@dataclass
class MemberInfo:
    """Telegram'dagi a'zolik holati (status: creator/administrator/member/left/kicked)."""

    status: str
    can_post_messages: bool | None = None


def check_channel_access(chat_type: str, bot: MemberInfo, user: MemberInfo) -> None:
    """Kanalni ulash mumkinmi — tekshiradi. Muammo bo'lsa ValidationError (aniq sabab bilan)."""
    if chat_type != "channel":
        raise ValidationError("channel_not_channel")
    if bot.status not in ("administrator", "creator"):
        raise ValidationError("channel_bot_not_admin")
    if bot.status == "administrator" and not bot.can_post_messages:
        raise ValidationError("channel_bot_cannot_post")
    if user.status not in ("administrator", "creator"):
        raise ValidationError("channel_user_not_admin")


async def get_active_channel(session: AsyncSession, seller_id: int) -> Channel | None:
    return await session.scalar(
        select(Channel)
        .where(Channel.seller_id == seller_id, Channel.is_active.is_(True))
        .order_by(Channel.id.desc())
        .limit(1)
    )


async def link_channel(
    session: AsyncSession,
    seller: Seller,
    chat_id: int,
    title: str,
    username: str | None,
) -> Channel:
    """Kanalni sotuvchiga ulaydi. 1-bosqichda sotuvchida bitta faol kanal bo'ladi."""
    channel = await session.scalar(select(Channel).where(Channel.chat_id == chat_id))
    if channel is not None and channel.seller_id != seller.id and channel.is_active:
        raise ConflictError("channel_taken")

    await session.execute(
        update(Channel)
        .where(Channel.seller_id == seller.id, Channel.chat_id != chat_id)
        .values(is_active=False)
    )
    if channel is None:
        channel = Channel(chat_id=chat_id)
        session.add(channel)
    channel.seller_id = seller.id
    channel.title = title[:255]
    channel.username = username
    channel.is_active = True
    await session.flush()
    return channel
