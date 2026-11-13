from __future__ import annotations

import logging
from functools import partial
from html import escape as _escape

escape = partial(_escape, quote=False)

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberAdministrator, Message, MessageOriginChannel
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.states import ChannelLink
from app.db.models import Seller
from app.services import channels as channel_service
from app.services.channels import MemberInfo
from app.services.errors import ServiceError
from app.texts import all_langs, t

log = logging.getLogger(__name__)
router = Router(name="channel")


def _member_info(member) -> MemberInfo:
    can_post = member.can_post_messages if isinstance(member, ChatMemberAdministrator) else None
    return MemberInfo(status=member.status, can_post_messages=can_post)


@router.message(F.text.in_(all_langs("btn_my_channel")))
async def my_channel(
    message: Message, state: FSMContext, session: AsyncSession, seller: Seller | None, bot: Bot, lang: str
) -> None:
    if seller is None:
        await message.answer(t("not_registered", lang))
        return
    channel = await channel_service.get_active_channel(session, seller.id)
    await state.set_state(ChannelLink.waiting)
    if channel is None:
        me = await bot.me()
        await message.answer(t("channel_none", lang, bot=me.username), reply_markup=kb.cancel_only(lang))
    else:
        username = f"({channel.username})" if channel.username else ""
        await message.answer(
            t("channel_current", lang, title=escape(channel.title), username=username),
            reply_markup=kb.cancel_only(lang),
        )


@router.message(ChannelLink.waiting)
async def got_channel(
    message: Message, state: FSMContext, session: AsyncSession, seller: Seller | None, bot: Bot, lang: str
) -> None:
    if seller is None:
        await message.answer(t("not_registered", lang))
        return
    me = await bot.me()

    # 1) Kanalni aniqlaymiz: forward qilingan xabar yoki username
    if isinstance(message.forward_origin, MessageOriginChannel):
        chat_ref: int | str = message.forward_origin.chat.id
    else:
        try:
            chat_ref = channel_service.parse_channel_username(message.text)
        except ServiceError as e:
            await message.answer(t(e.code, lang))
            return

    await message.answer(t("channel_checking", lang))
    try:
        chat = await bot.get_chat(chat_ref)
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer(t("channel_not_found", lang, bot=me.username))
        return

    # 2) Huquqlarni tekshiramiz
    try:
        if chat.type != "channel":
            raise ServiceError("channel_not_channel")
        try:
            bot_member = _member_info(await bot.get_chat_member(chat.id, me.id))
        except TelegramAPIError:
            bot_member = MemberInfo(status="left")
        try:
            user_member = _member_info(await bot.get_chat_member(chat.id, message.from_user.id))
        except TelegramAPIError:
            user_member = MemberInfo(status="left")
        channel_service.check_channel_access(chat.type, bot_member, user_member)
        username = f"@{chat.username}" if chat.username else None
        channel = await channel_service.link_channel(session, seller, chat.id, chat.title or "", username)
    except ServiceError as e:
        await message.answer(t(e.code, lang, bot=me.username))
        return

    await state.clear()
    await message.answer(t("channel_linked", lang, title=escape(channel.title)), reply_markup=kb.main_menu(lang))
