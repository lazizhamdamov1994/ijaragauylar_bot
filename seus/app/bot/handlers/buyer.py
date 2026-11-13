"""Xaridor kanal tugmasini bosib kelganda: /start p_<id> yoki /start c_<id>."""
from __future__ import annotations

import re
from functools import partial
from html import escape as _escape

escape = partial(_escape, quote=False)

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.publisher import contact_url, send_product
from app.services import products as product_service
from app.services import sellers as seller_service
from app.services.formatting import view_from_product
from app.texts import t

router = Router(name="buyer")


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
        bot, message.chat.id, [p.file_id for p in product.photos],
        view_from_product(product, seller.shop_name), markup, lang,
    )
    await message.answer(t("buyer_order_soon", lang))


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
