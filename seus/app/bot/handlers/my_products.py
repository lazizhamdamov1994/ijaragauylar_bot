from __future__ import annotations

from functools import partial
from html import escape as _escape

escape = partial(_escape, quote=False)

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.callbacks import ProductCb
from app.bot.publisher import post_link, publish_to_channel
from app.db.models import Seller
from app.services import channels as channel_service
from app.services import products as product_service
from app.services.formatting import build_caption, view_from_product
from app.texts import all_langs, t

router = Router(name="my_products")
PAGE_SIZE = 10


async def _list_payload(session: AsyncSession, seller: Seller, page: int, lang: str):
    total = await product_service.count_seller_products(session, seller.id)
    if total == 0:
        return t("my_products_empty", lang), None
    items = await product_service.list_seller_products(session, seller.id, PAGE_SIZE, page * PAGE_SIZE)
    has_next = (page + 1) * PAGE_SIZE < total
    return t("my_products_title", lang, count=total), kb.products_list(items, page, has_next, lang)


@router.message(F.text.in_(all_langs("btn_my_products")))
async def my_products(message: Message, state: FSMContext, session: AsyncSession, seller: Seller | None, lang: str):
    await state.clear()
    if seller is None:
        await message.answer(t("not_registered", lang))
        return
    text, markup = await _list_payload(session, seller, 0, lang)
    await message.answer(text, reply_markup=markup)


async def _edit_or_send(call: CallbackQuery, text: str, markup) -> None:
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:  # masalan, xabar rasm bo'lsa — yangisini yuboramiz
        await call.message.answer(text, reply_markup=markup)


@router.callback_query(ProductCb.filter(F.action == "list"))
async def list_page(call: CallbackQuery, callback_data: ProductCb, session: AsyncSession, seller: Seller | None, lang: str):
    if seller is None:
        await call.answer(t("not_registered", lang), show_alert=True)
        return
    text, markup = await _list_payload(session, seller, callback_data.page, lang)
    await _edit_or_send(call, text, markup)
    await call.answer()


@router.callback_query(ProductCb.filter(F.action == "view"))
async def view(call: CallbackQuery, callback_data: ProductCb, session: AsyncSession, seller: Seller | None, lang: str):
    if seller is None:
        await call.answer(t("not_registered", lang), show_alert=True)
        return
    product = await product_service.get_seller_product(session, seller.id, callback_data.id)
    posts = await product_service.count_posts(session, product.id)
    text = build_caption(view_from_product(product, seller.shop_name), lang, 900)
    text += "\n\n" + t("product_posted_times", lang, count=posts)
    if not product.is_active:
        text = t("product_deactivated", lang) + "\n\n" + text
    markup = kb.product_manage(product, callback_data.page, lang)
    first = product.media[0] if product.media else None
    if first and first.kind == "video":
        await call.message.answer_video(first.file_id, caption=text, reply_markup=markup)
    elif first:
        await call.message.answer_photo(first.file_id, caption=text, reply_markup=markup)
    else:
        await call.message.answer(text, reply_markup=markup)
    await call.answer()


@router.callback_query(ProductCb.filter(F.action.in_({"on", "off"})))
async def toggle(call: CallbackQuery, callback_data: ProductCb, session: AsyncSession, seller: Seller | None, lang: str):
    if seller is None:
        await call.answer(t("not_registered", lang), show_alert=True)
        return
    active = callback_data.action == "on"
    product = await product_service.set_active(session, seller.id, callback_data.id, active)
    await call.answer(t("product_activated" if active else "product_deactivated", lang), show_alert=True)
    try:
        await call.message.edit_reply_markup(reply_markup=kb.product_manage(product, callback_data.page, lang))
    except TelegramBadRequest:
        pass


@router.callback_query(ProductCb.filter(F.action == "publish"))
async def publish(call: CallbackQuery, callback_data: ProductCb, bot: Bot, session: AsyncSession, seller: Seller | None, lang: str):
    if seller is None:
        await call.answer(t("not_registered", lang), show_alert=True)
        return
    product = await product_service.get_seller_product(session, seller.id, callback_data.id)
    channel = await channel_service.get_active_channel(session, seller.id)
    if channel is None:
        await call.answer()
        await call.message.answer(t("saved_no_channel", lang))
        return
    await call.answer(t("publishing", lang))
    post = await publish_to_channel(bot, session, seller, product, channel)
    if post is None:
        await call.message.answer(t("publish_failed", lang))
        return
    text = t("published", lang, title=escape(channel.title))
    link = post_link(channel, post.message_ids[0])
    if link:
        text += "\n" + t("published_link", lang, link=link)
    await call.message.answer(text)
