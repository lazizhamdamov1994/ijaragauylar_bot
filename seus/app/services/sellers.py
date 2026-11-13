from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Seller
from app.services.parsing import normalize_phone, validate_shop_name


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> Seller | None:
    return await session.scalar(select(Seller).where(Seller.telegram_id == telegram_id))


async def get_by_id(session: AsyncSession, seller_id: int) -> Seller | None:
    return await session.get(Seller, seller_id)


async def register_seller(
    session: AsyncSession,
    telegram_id: int,
    shop_name: str,
    phone: str,
    username: str | None = None,
) -> Seller:
    """Yangi sotuvchini yaratadi; bor bo'lsa ma'lumotini yangilaydi va faollashtiradi."""
    shop_name = validate_shop_name(shop_name)
    phone = normalize_phone(phone)
    seller = await get_by_telegram_id(session, telegram_id)
    if seller is None:
        seller = Seller(telegram_id=telegram_id)
        session.add(seller)
    seller.shop_name = shop_name
    seller.phone = phone
    seller.username = username
    seller.is_active = True
    await session.flush()
    return seller


async def update_username(session: AsyncSession, seller: Seller, username: str | None) -> None:
    if seller.username != username:
        seller.username = username
        await session.flush()
