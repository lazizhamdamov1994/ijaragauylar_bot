from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.states import Registration
from app.db.models import Seller
from app.services import sellers as seller_service
from app.services.errors import ValidationError
from app.services.parsing import validate_shop_name
from app.texts import t

router = Router(name="registration")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, seller: Seller | None, lang: str) -> None:
    await state.clear()
    if seller is not None:
        await message.answer(t("welcome_back", lang, shop=seller.shop_name), reply_markup=kb.main_menu(lang))
        return
    await state.set_state(Registration.shop_name)
    await message.answer(t("welcome_new", lang), reply_markup=ReplyKeyboardRemove())


@router.message(Registration.shop_name, F.text)
async def got_shop_name(message: Message, state: FSMContext, lang: str) -> None:
    try:
        name = validate_shop_name(message.text)
    except ValidationError as e:
        await message.answer(t(e.code, lang))
        return
    await state.update_data(shop_name=name)
    await state.set_state(Registration.phone)
    await message.answer(t("ask_phone", lang), reply_markup=kb.phone_request(lang))


@router.message(Registration.phone, F.contact)
async def got_phone(message: Message, state: FSMContext, session: AsyncSession, lang: str) -> None:
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer(t("phone_not_yours", lang), reply_markup=kb.phone_request(lang))
        return
    data = await state.get_data()
    seller = await seller_service.register_seller(
        session,
        telegram_id=message.from_user.id,
        shop_name=data.get("shop_name", ""),
        phone=contact.phone_number,
        username=message.from_user.username,
    )
    await state.clear()
    await message.answer(t("registered", lang, shop=seller.shop_name), reply_markup=kb.main_menu(lang))


@router.message(Registration.phone)
async def phone_wrong_input(message: Message, lang: str) -> None:
    await message.answer(t("phone_use_button", lang), reply_markup=kb.phone_request(lang))
