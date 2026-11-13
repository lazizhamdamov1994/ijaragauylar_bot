"""Tovarni Telegram'ga yuborish: oldindan ko'rish, kanal posti, xaridor kartochkasi."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.db.models import Channel, ChannelPost, Product, Seller
from app.services import products as product_service
from app.services.dto import ProductView
from app.services.formatting import CAPTION_LIMIT, MESSAGE_LIMIT, build_caption, view_from_product

log = logging.getLogger(__name__)


async def send_product(
    bot: Bot,
    chat_id: int | str,
    photo_ids: list[str],
    view: ProductView,
    markup: InlineKeyboardMarkup | None,
    lang: str = "uz",
) -> list[Message]:
    """1 ta rasm → rasm+matn+tugmalar. Ko'p rasm → albom, keyin matn+tugmalar alohida xabar
    (Telegram albomga tugma qo'yishga ruxsat bermaydi)."""
    if len(photo_ids) == 1:
        msg = await bot.send_photo(
            chat_id, photo_ids[0], caption=build_caption(view, lang, CAPTION_LIMIT), reply_markup=markup
        )
        return [msg]
    album = await bot.send_media_group(
        chat_id, media=[InputMediaPhoto(media=f) for f in photo_ids[:10]]
    )
    text_msg = await bot.send_message(
        chat_id, build_caption(view, lang, MESSAGE_LIMIT), reply_markup=markup
    )
    return [*album, text_msg]


async def contact_url(bot: Bot, seller: Seller, product: Product) -> str:
    if seller.username:
        return f"https://t.me/{seller.username}"
    me = await bot.me()
    return f"https://t.me/{me.username}?start=c_{product.public_id}"


async def order_url(bot: Bot, product: Product) -> str:
    me = await bot.me()
    return f"https://t.me/{me.username}?start=p_{product.public_id}"


def post_link(channel: Channel, message_id: int) -> str | None:
    if channel.username:
        return f"https://t.me/{channel.username.lstrip('@')}/{message_id}"
    cid = str(channel.chat_id)
    if cid.startswith("-100"):
        return f"https://t.me/c/{cid[4:]}/{message_id}"
    return None


async def publish_to_channel(
    bot: Bot, session: AsyncSession, seller: Seller, product: Product, channel: Channel
) -> ChannelPost | None:
    """Kanalga joylaydi va ChannelPost yozadi. Telegram xatosida None qaytaradi (bot yiqilmaydi)."""
    markup = kb.post_buttons(await order_url(bot, product), await contact_url(bot, seller, product), seller.language)
    view = view_from_product(product, seller.shop_name)
    try:
        messages = await send_product(
            bot, channel.chat_id, [p.file_id for p in product.photos], view, markup, seller.language
        )
    except TelegramAPIError as e:
        log.warning("Kanalga joylab bo'lmadi (channel_id=%s, product=%s): %s", channel.id, product.id, e)
        return None
    return await product_service.record_channel_post(
        session,
        product_id=product.id,
        channel_id=channel.id,
        message_ids=[m.message_id for m in messages],
        button_message_id=messages[-1].message_id,
    )
