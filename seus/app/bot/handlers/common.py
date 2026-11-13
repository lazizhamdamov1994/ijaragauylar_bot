from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, ExceptionTypeFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ErrorEvent, Message, ReplyKeyboardRemove

from app.bot import keyboards as kb
from app.db.models import Seller
from app.services.errors import ServiceError
from app.texts import all_langs, t

log = logging.getLogger(__name__)
router = Router(name="common")
fallback_router = Router(name="fallback")


async def show_menu(message: Message, seller: Seller | None, lang: str, text: str | None = None) -> None:
    if seller is None:
        await message.answer(t("not_registered", lang), reply_markup=ReplyKeyboardRemove())
        return
    await message.answer(text or t("menu", lang), reply_markup=kb.main_menu(lang))


@router.message(Command("cancel"))
@router.message(F.text.in_(all_langs("btn_cancel")))
async def cancel(message: Message, state: FSMContext, seller: Seller | None, lang: str) -> None:
    await state.clear()
    await show_menu(message, seller, lang, t("cancelled", lang))


@fallback_router.message()
async def unknown(message: Message, seller: Seller | None, lang: str) -> None:
    await show_menu(message, seller, lang, t("unknown_command", lang))


@fallback_router.callback_query()
async def stale_callback(call: CallbackQuery, lang: str) -> None:
    await call.answer(t("session_expired", lang), show_alert=True)


async def _reply(event: ErrorEvent, text: str) -> None:
    update = event.update
    try:
        if update.message:
            await update.message.answer(text)
        elif update.callback_query:
            await update.callback_query.answer(text[:200], show_alert=True)
    except Exception:  # javob ham yuborilmasa — jim o'tamiz
        log.debug("Xato haqida javob yuborib bo'lmadi", exc_info=True)


@router.errors(ExceptionTypeFilter(ServiceError))
async def on_service_error(event: ErrorEvent) -> bool:
    err: ServiceError = event.exception  # type: ignore[assignment]
    await _reply(event, t(err.code, **err.params))
    return True


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    log.exception("Kutilmagan xato (update_id=%s)", event.update.update_id, exc_info=event.exception)
    await _reply(event, t("error_generic"))
    return True
