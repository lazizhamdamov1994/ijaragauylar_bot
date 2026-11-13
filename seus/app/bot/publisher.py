"""Tovarni Telegram'ga yuborish: oldindan ko'rish, kanal posti, xaridor kartochkasi."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.db.models import Channel, ChannelPost, Product, Seller
from app.services import products as product_service
from app.services.dto import MediaItem, ProductView
from app.services.formatting import CAPTION_LIMIT, build_caption, post_buttons_text, view_from_product

log = logging.getLogger(__name__)


def media_of(product: Product) -> list[MediaItem]:
    return [MediaItem(m.kind, m.file_id) for m in product.media]


def _input_media(item: MediaItem, caption: str | None = None):
    cls = InputMediaVideo if item.kind == "video" else InputMediaPhoto
    return cls(media=item.file_id, caption=caption)


async def send_product(
    bot: Bot,
    chat_id: int | str,
    media: list[MediaItem],
    view: ProductView,
    markup: InlineKeyboardMarkup | None,
    lang: str = "uz",
) -> list[Message]:
    """1 ta rasm/video → bitta xabar: media + matn + tugmalar.
    Ko'p rasm/video → albom, matn albomning o'zida (birinchi rasm izohi);
    Telegram albomga tugma qo'yishga ruxsat bermaydi, shuning uchun tugmalar ostidagi kichik xabarda."""
    caption = build_caption(view, lang, CAPTION_LIMIT)
    if len(media) == 1:
        item = media[0]
        send = bot.send_video if item.kind == "video" else bot.send_photo
        msg = await send(chat_id, item.file_id, caption=caption, reply_markup=markup)
        return [msg]
    album = await bot.send_media_group(
        chat_id,
        media=[_input_media(m, caption if i == 0 else None) for i, m in enumerate(media[:10])],
    )
    messages = list(album)
    if markup is not None:
        messages.append(
            await bot.send_message(chat_id, post_buttons_text(view, lang), reply_markup=markup)
        )
    return messages


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


async def _post_markup(bot: Bot, seller: Seller, product: Product) -> InlineKeyboardMarkup:
    return kb.post_buttons(
        await order_url(bot, product), await contact_url(bot, seller, product), seller.language
    )


async def publish_to_channel(
    bot: Bot, session: AsyncSession, seller: Seller, product: Product, channel: Channel
) -> ChannelPost | None:
    """Kanalga joylaydi va ChannelPost yozadi. Telegram xatosida None qaytaradi (bot yiqilmaydi)."""
    markup = await _post_markup(bot, seller, product)
    view = view_from_product(product, seller.shop_name)
    try:
        messages = await send_product(bot, channel.chat_id, media_of(product), view, markup, seller.language)
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


async def refresh_channel_posts(bot: Bot, session: AsyncSession, product: Product) -> int:
    """Qoldiq o'zgarganda kanal postlaridagi matnni yangilaydi (mavjud razmerlar, "tugagan").
    Xato bo'lsa jim o'tadi — buyurtma jarayoni to'xtamasligi kerak. Yangilanganlar sonini qaytaradi."""
    seller = await session.get(Seller, product.seller_id)
    rows = (
        await session.execute(
            select(ChannelPost, Channel)
            .join(Channel, Channel.id == ChannelPost.channel_id)
            .where(ChannelPost.product_id == product.id)
        )
    ).all()
    if not rows:
        return 0
    await session.refresh(product, ["variants"])
    caption = build_caption(view_from_product(product, seller.shop_name), seller.language, CAPTION_LIMIT)
    markup = await _post_markup(bot, seller, product)
    done = 0
    for post, channel in rows:
        single = len(post.message_ids) == 1
        try:
            await bot.edit_message_caption(
                chat_id=channel.chat_id,
                message_id=post.message_ids[0],
                caption=caption,
                reply_markup=markup if single else None,
            )
            done += 1
        except TelegramAPIError as e:  # "message is not modified", post o'chirilgan va h.k.
            log.info("Kanal postini yangilab bo'lmadi (post=%s): %s", post.id, e)
    return done
