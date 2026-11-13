from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, User
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services import sellers as seller_service


class DbSessionMiddleware(BaseMiddleware):
    """Har bir yangilanish uchun bitta baza sessiyasi: muvaffaqiyatli bo'lsa commit, xatoda rollback."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class SellerMiddleware(BaseMiddleware):
    """Foydalanuvchi sotuvchi bo'lsa, `seller` ni handlerga beradi (aks holda None)."""

    async def __call__(self, handler, event, data):
        user: User | None = data.get("event_from_user")
        seller = None
        if user is not None and "session" in data:
            seller = await seller_service.get_by_telegram_id(data["session"], user.id)
            if seller is not None:
                await seller_service.update_username(data["session"], seller, user.username)
        data["seller"] = seller
        data["lang"] = (seller.language if seller else None) or "uz"
        return await handler(event, data)


class AlbumMiddleware(BaseMiddleware):
    """Albom (bir nechta rasm birga) bo'lib kelgan xabarlarni bitta ro'yxatga yig'adi → data['album']."""

    def __init__(self, latency: float = 0.8):
        self.latency = latency
        self._albums: dict[str, list[Message]] = {}

    async def __call__(self, handler, event: Message, data):
        if not isinstance(event, Message) or not event.media_group_id:
            return await handler(event, data)
        key = f"{event.chat.id}:{event.media_group_id}"
        if key in self._albums:
            self._albums[key].append(event)
            return None
        self._albums[key] = [event]
        await asyncio.sleep(self.latency)
        album = self._albums.pop(key)
        data["album"] = sorted(album, key=lambda m: m.message_id)
        return await handler(event, data)
