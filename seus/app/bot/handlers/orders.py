"""Sotuvchi: buyurtmalar ro'yxati va holatini o'zgartirish."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.callbacks import SellerOrderCb
from app.bot.publisher import refresh_channel_posts
from app.db.models import OrderStatus, Product, Seller
from app.services import orders as order_service
from app.services.formatting import order_text, status_label
from app.texts import all_langs, t

log = logging.getLogger(__name__)
router = Router(name="orders")
PAGE_SIZE = 10


async def _list_payload(session: AsyncSession, seller: Seller, page: int, lang: str):
    total = await order_service.count_seller_orders(session, seller.id)
    if total == 0:
        return t("orders_empty", lang), None
    items = await order_service.list_seller_orders(session, seller.id, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    has_next = (page + 1) * PAGE_SIZE < total
    return t("orders_title", lang, count=total), kb.seller_orders_list(items, page, has_next, lang)


@router.message(F.text.in_(all_langs("btn_orders")))
async def orders_menu(message: Message, state: FSMContext, session: AsyncSession, seller: Seller | None, lang: str):
    await state.clear()
    if seller is None:
        await message.answer(t("not_registered", lang))
        return
    text, markup = await _list_payload(session, seller, 0, lang)
    await message.answer(text, reply_markup=markup)


@router.callback_query(SellerOrderCb.filter(F.action == "list"))
async def orders_page(call: CallbackQuery, callback_data: SellerOrderCb, session: AsyncSession, seller: Seller | None, lang: str):
    if seller is None:
        await call.answer(t("not_registered", lang), show_alert=True)
        return
    text, markup = await _list_payload(session, seller, callback_data.page, lang)
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        await call.message.answer(text, reply_markup=markup)
    await call.answer()


@router.callback_query(SellerOrderCb.filter(F.action == "view"))
async def order_view(call: CallbackQuery, callback_data: SellerOrderCb, session: AsyncSession, seller: Seller | None, lang: str):
    if seller is None:
        await call.answer(t("not_registered", lang), show_alert=True)
        return
    order = await order_service.get_seller_order(session, seller.id, callback_data.id)
    await call.message.answer(order_text(order, lang), reply_markup=kb.seller_order_actions(order, callback_data.page, lang))
    await call.answer()


@router.callback_query(SellerOrderCb.filter(F.action == "set"))
async def order_set_status(
    call: CallbackQuery, callback_data: SellerOrderCb, bot: Bot, session: AsyncSession, seller: Seller | None, lang: str
):
    if seller is None:
        await call.answer(t("not_registered", lang), show_alert=True)
        return
    new_status = OrderStatus(callback_data.status)
    order = await order_service.change_status(session, seller.id, callback_data.id, new_status)
    await session.commit()
    await call.answer(t("order_status_updated", lang, status=status_label(new_status, lang)))
    try:
        await call.message.edit_text(
            order_text(order, lang), reply_markup=kb.seller_order_actions(order, callback_data.page, lang)
        )
    except TelegramBadRequest:
        pass

    if order.buyer_telegram_id and order.buyer_telegram_id != seller.telegram_id:
        try:
            await bot.send_message(
                order.buyer_telegram_id,
                t("order_status_changed_buyer", "uz", number=order.id, status=status_label(new_status, "uz")),
            )
        except TelegramAPIError as e:
            log.info("Xaridorga xabar yuborib bo'lmadi (order=%s): %s", order.id, e)

    if new_status == OrderStatus.CANCELLED:  # qoldiq qaytdi — kanal postini yangilaymiz
        for item in order.items:
            if item.product_id:
                product = await session.get(Product, item.product_id)
                if product:
                    await refresh_channel_posts(bot, session, product)
