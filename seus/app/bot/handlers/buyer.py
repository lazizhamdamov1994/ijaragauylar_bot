"""Xaridor: kanal tugmasini bosib keladi (/start p_<id>), tovarni ko'radi va buyurtma beradi."""
from __future__ import annotations

import logging
import re
from functools import partial
from html import escape as _escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.callbacks import BuyCb
from app.bot.publisher import contact_url, media_of, refresh_channel_posts, send_product
from app.bot.states import OrderFlow
from app.db.models import Product, ProductVariant, Seller
from app.services import orders as order_service
from app.services import products as product_service
from app.services import sellers as seller_service
from app.services.errors import ServiceError
from app.services.formatting import format_price, order_text, variant_label, view_from_product
from app.services.parsing import normalize_phone
from app.texts import all_langs, t

escape = partial(_escape, quote=False)
log = logging.getLogger(__name__)
router = Router(name="buyer")


def _menu_for(seller: Seller | None, lang: str):
    return kb.main_menu(lang) if seller else ReplyKeyboardRemove()


async def _ask_variant(message: Message, state: FSMContext, product: Product, lang: str) -> None:
    variants = order_service.available_variants(product)
    if not variants:
        await state.clear()
        await message.answer(t("post_out_of_stock", lang))
        return
    if len(variants) == 1:
        await _ask_qty(message, state, variants[0], lang)
        return
    await state.set_state(OrderFlow.variant)
    await message.answer(t("order_choose_variant", lang), reply_markup=kb.variant_picker(variants, lang))


async def _ask_qty(message: Message, state: FSMContext, variant: ProductVariant, lang: str) -> None:
    await state.update_data(variant_id=variant.id)
    await state.set_state(OrderFlow.qty)
    await message.answer(
        t("order_choose_qty", lang, variant=escape(variant_label(variant.size, variant.color)), stock=variant.stock),
        reply_markup=kb.buy_qty_picker(variant.stock, lang),
    )


async def _load(session: AsyncSession, state: FSMContext) -> tuple[Product | None, ProductVariant | None, dict]:
    data = await state.get_data()
    product = await session.get(Product, data.get("product_id", 0))
    variant = await session.get(ProductVariant, data.get("variant_id", 0)) if data.get("variant_id") else None
    return product, variant, data


# ---------- Kirish: /start p_<id> ----------

@router.message(CommandStart(deep_link=True, magic=F.args.regexp(re.compile(r"^p_[A-Za-z0-9]+$"))))
async def open_product(
    message: Message, command: CommandObject, bot: Bot, session: AsyncSession, state: FSMContext, lang: str
) -> None:
    await state.clear()
    product = await product_service.get_by_public_id(session, command.args[2:])
    if product is None:
        await message.answer(t("buyer_product_unavailable", lang))
        return
    seller = await seller_service.get_by_id(session, product.seller_id)
    markup = kb.contact_button(await contact_url(bot, seller, product), lang)
    await send_product(
        bot, message.chat.id, media_of(product), view_from_product(product, seller.shop_name), markup, lang
    )
    await state.update_data(product_id=product.id)
    await _ask_variant(message, state, product, lang)


@router.message(CommandStart(deep_link=True, magic=F.args.regexp(re.compile(r"^c_[A-Za-z0-9]+$"))))
async def seller_contact(
    message: Message, command: CommandObject, session: AsyncSession, state: FSMContext, lang: str
) -> None:
    await state.clear()
    product = await product_service.get_by_public_id(session, command.args[2:])
    if product is None:
        await message.answer(t("buyer_product_unavailable", lang))
        return
    seller = await seller_service.get_by_id(session, product.seller_id)
    text = t("seller_contact", lang, shop=escape(seller.shop_name), phone=escape(seller.phone))
    if seller.username:
        text += "\n" + t("seller_contact_username", lang, username=seller.username)
    await message.answer(text)


# ---------- Razmer va soni ----------

@router.callback_query(OrderFlow.variant, BuyCb.filter(F.action == "variant"))
async def picked_variant(call: CallbackQuery, callback_data: BuyCb, session: AsyncSession, state: FSMContext, lang: str):
    await call.answer()
    product, _, _ = await _load(session, state)
    variant = await session.get(ProductVariant, callback_data.id)
    if product is None or variant is None or variant.product_id != product.id or variant.stock <= 0:
        await call.message.answer(t("order_variant_gone", lang))
        if product is not None:
            await _ask_variant(call.message, state, product, lang)
        return
    await _ask_qty(call.message, state, variant, lang)


async def _set_qty(message: Message, qty: int, session: AsyncSession, state: FSMContext, seller: Seller | None, lang: str):
    _, variant, _ = await _load(session, state)
    if variant is None:
        await state.clear()
        await message.answer(t("session_expired", lang))
        return
    try:
        order_service.validate_quantity(qty, variant.stock)
    except ServiceError as e:
        await message.answer(t(e.code, lang, **e.params))
        return
    await state.update_data(qty=qty)
    await state.set_state(OrderFlow.phone)
    user_id = message.chat.id
    prev = await order_service.last_buyer_phone(session, user_id) or (seller.phone if seller else None)
    await message.answer(t("order_ask_phone", lang), reply_markup=kb.buyer_phone(prev, lang))


@router.callback_query(OrderFlow.qty, BuyCb.filter(F.action == "qty"))
async def picked_qty(call: CallbackQuery, callback_data: BuyCb, session: AsyncSession, state: FSMContext, seller: Seller | None, lang: str):
    await call.answer()
    await _set_qty(call.message, callback_data.id, session, state, seller, lang)


@router.message(OrderFlow.qty, F.text.regexp(r"^\s*\d{1,4}\s*$"))
async def typed_qty(message: Message, session: AsyncSession, state: FSMContext, seller: Seller | None, lang: str):
    await _set_qty(message, int(message.text), session, state, seller, lang)


# ---------- Telefon, manzil, izoh ----------

async def _set_phone(message: Message, raw: str, state: FSMContext, lang: str) -> None:
    try:
        phone = normalize_phone(raw)
    except ServiceError:
        await message.answer(t("order_phone_invalid", lang))
        return
    await state.update_data(phone=phone)
    await state.set_state(OrderFlow.address)
    await message.answer(t("order_ask_address", lang), reply_markup=kb.cancel_only(lang))


@router.message(OrderFlow.phone, F.contact)
async def got_contact(message: Message, state: FSMContext, lang: str):
    await _set_phone(message, message.contact.phone_number, state, lang)


@router.message(OrderFlow.phone, F.text)
async def got_phone_text(message: Message, state: FSMContext, lang: str):
    await _set_phone(message, message.text, state, lang)


@router.message(OrderFlow.address, F.text)
async def got_address(message: Message, state: FSMContext, lang: str):
    try:
        address = order_service.validate_address(message.text)
    except ServiceError as e:
        await message.answer(t(e.code, lang))
        return
    await state.update_data(address=address)
    await state.set_state(OrderFlow.comment)
    await message.answer(t("order_ask_comment", lang), reply_markup=kb.skip_cancel(lang))


@router.message(OrderFlow.comment, F.text)
async def got_comment(message: Message, session: AsyncSession, state: FSMContext, lang: str):
    comment = None if message.text in all_langs("btn_skip") else message.text[:1000]
    await state.update_data(comment=comment)
    product, variant, data = await _load(session, state)
    if product is None or variant is None:
        await state.clear()
        await message.answer(t("session_expired", lang))
        return
    qty = data["qty"]
    lines = [
        t("order_confirm_title", lang),
        "",
        t("order_item_line", lang, name=escape(product.name),
          variant=escape(variant_label(variant.size, variant.color)), qty=qty, price=format_price(product.price)),
        t("order_total_line", lang, total=format_price(product.price * qty)),
        "",
        t("order_buyer_line", lang, name=escape(message.from_user.full_name)),
        t("order_phone_line", lang, phone=escape(data["phone"])),
        t("order_address_line", lang, address=escape(data["address"])),
    ]
    if comment:
        lines.append(t("order_comment_line", lang, comment=escape(comment)))
    await state.set_state(OrderFlow.confirm)
    await message.answer("👌", reply_markup=ReplyKeyboardRemove())
    await message.answer("\n".join(lines), reply_markup=kb.order_confirm(lang))


# ---------- Tasdiqlash ----------

@router.callback_query(OrderFlow.confirm, BuyCb.filter(F.action == "send"))
async def send_order(call: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext, seller: Seller | None, lang: str):
    data = await state.get_data()
    await state.clear()  # ikki marta bosilsa, ikkinchi buyurtma yaratilmaydi
    await call.answer()
    try:
        order = await order_service.create_order(
            session,
            order_service.OrderRequest(
                product_id=data["product_id"],
                variant_id=data["variant_id"],
                quantity=data["qty"],
                buyer_telegram_id=call.from_user.id,
                buyer_name=call.from_user.full_name,
                buyer_phone=data["phone"],
                address=data["address"],
                comment=data.get("comment"),
            ),
        )
    except ServiceError as e:
        await call.message.answer(t(e.code, lang, **e.params), reply_markup=_menu_for(seller, lang))
        return
    await session.commit()  # buyurtma albatta saqlansin, xabarlar yuborilmasa ham

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        pass
    await call.message.answer(t("order_created_buyer", lang, number=order.id), reply_markup=_menu_for(seller, lang))

    shop = await seller_service.get_by_id(session, order.seller_id)
    try:
        await bot.send_message(
            shop.telegram_id,
            t("order_new_seller", shop.language, text=order_text(order, shop.language)),
            reply_markup=kb.seller_order_actions(order, 0, shop.language),
        )
    except TelegramAPIError as e:
        log.warning("Sotuvchiga buyurtma xabarini yuborib bo'lmadi (order=%s): %s", order.id, e)

    product = await session.get(Product, data["product_id"])
    await refresh_channel_posts(bot, session, product)


@router.callback_query(BuyCb.filter(F.action == "cancel"))
async def cancel_order_flow(call: CallbackQuery, state: FSMContext, seller: Seller | None, lang: str):
    await state.clear()
    await call.answer()
    await call.message.answer(t("order_cancelled_flow", lang), reply_markup=_menu_for(seller, lang))
