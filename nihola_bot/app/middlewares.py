"""Har bir xabar/tugma bosilganda foydalanuvchini bazaga yozib boradi."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from .config import settings


class UserTrackingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        chat = data.get("event_chat")
        data["is_new_user"] = False
        if user and not user.is_bot and (chat is None or chat.type == "private"):
            data["is_new_user"] = await data["db"].upsert_user(user.id, user.full_name, user.username)
        return await handler(event, data)


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, **kwargs: Any) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in settings.admin_ids)
