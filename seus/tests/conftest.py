"""Testlar uchun baza. Odatda xotiradagi SQLite ishlatiladi (hech narsa o'rnatish shart emas).
Haqiqiy PostgreSQL'da sinash uchun: TEST_DATABASE_URL=postgresql+asyncpg://... pytest"""
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.db.models import Seller

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def seller(session) -> Seller:
    s = Seller(telegram_id=111, shop_name="Moda", phone="+998901234567", username="moda_shop")
    session.add(s)
    await session.flush()
    return s
