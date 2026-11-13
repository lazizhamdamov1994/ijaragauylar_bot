"""To'liq ssenariy: ro'yxatdan o'tish → kanal ulash → tovar qo'shish → kanalga joylash → xaridor.
Telegram'ga ulanmaydi: soxta sessiya so'rovlarni yozib oladi va tayyor javob qaytaradi."""
from __future__ import annotations

import itertools
from datetime import datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    GetChat, GetChatMember, GetMe, SendMediaGroup, SendMessage, SendPhoto, TelegramMethod,
)
from aiogram.types import (
    Chat, ChatFullInfo, ChatMemberAdministrator, ChatMemberOwner, Message, Update, User,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers import build_router
from app.bot.middlewares import DbSessionMiddleware, SellerMiddleware
from app.db import Base
from app.db.models import ChannelPost, Product, Seller
from tests.conftest import TEST_DB_URL

BOT_ID, USER_ID, CHANNEL_ID = 42, 1000, -1009999
NOW = datetime(2026, 1, 1)
USER = User(id=USER_ID, is_bot=False, first_name="Laziz", username="laziz")
PRIVATE = Chat(id=USER_ID, type="private")
CHANNEL = Chat(id=CHANNEL_ID, type="channel", title="Moda kanal", username="moda_kanal")


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.requests: list[TelegramMethod] = []
        self.ids = itertools.count(1)

    def _msg(self, chat_id, **kw):
        chat = CHANNEL if chat_id == CHANNEL_ID else PRIVATE
        return Message(message_id=next(self.ids), date=NOW, chat=chat, **kw)

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, GetMe):
            return User(id=BOT_ID, is_bot=True, first_name="Seus", username="seus_bot")
        if isinstance(method, GetChat):
            return ChatFullInfo.model_construct(
                id=CHANNEL_ID, type="channel", title="Moda kanal", username="moda_kanal")
        if isinstance(method, GetChatMember):
            if method.user_id == BOT_ID:
                return ChatMemberAdministrator.model_construct(
                    status="administrator", user=User(id=BOT_ID, is_bot=True, first_name="Seus"),
                    can_post_messages=True)
            return ChatMemberOwner(user=USER, is_anonymous=False)
        if isinstance(method, SendMediaGroup):
            return [self._msg(method.chat_id, photo=[]) for _ in method.media]
        if isinstance(method, (SendMessage, SendPhoto)):
            return self._msg(method.chat_id, text="ok")
        return True

    async def close(self):
        pass

    async def stream_content(self, *a, **kw):  # pragma: no cover
        yield b""

    def texts(self) -> list[str]:
        out = [getattr(r, "text", None) or getattr(r, "caption", None) for r in self.requests]
        return [x for x in out if x]


@pytest.fixture
async def env():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fake = FakeSession()
    bot = Bot("123456:TEST", session=fake)
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(DbSessionMiddleware(factory))
    dp.update.outer_middleware(SellerMiddleware())
    root = build_router()
    dp.include_router(root)
    counter = itertools.count(1)

    async def send(**kw):
        msg = Message(message_id=next(counter), date=NOW, chat=PRIVATE, from_user=USER, **kw)
        fake.requests.clear()
        await dp.feed_update(bot, Update(update_id=next(counter), message=msg))
        return fake

    async def press(data: str):
        from aiogram.types import CallbackQuery
        cq = CallbackQuery(id=str(next(counter)), from_user=USER, chat_instance="x", data=data,
                           message=Message(message_id=1, date=NOW, chat=PRIVATE, text="x"))
        fake.requests.clear()
        await dp.feed_update(bot, Update(update_id=next(counter), callback_query=cq))
        return fake

    yield send, press, factory
    root._parent_router = None  # keyingi test uchun routerni bo'shatamiz
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def photo(fid):
    from aiogram.types import PhotoSize
    return [PhotoSize(file_id=fid + "_small", file_unique_id="s", width=90, height=90),
            PhotoSize(file_id=fid, file_unique_id="b", width=800, height=800)]


async def test_full_flow(env):
    send, press, factory = env

    # Ro'yxatdan o'tish
    assert "Do'koningiz nomini" in (await send(text="/start")).texts()[0]
    assert "telefon" in (await send(text="Moda uyi")).texts()[0]
    from aiogram.types import Contact
    r = await send(contact=Contact(phone_number="998901234567", first_name="L", user_id=USER_ID))
    assert "ro'yxatdan o'tdi" in r.texts()[0]

    # Kanal ulash
    assert "ulangan kanal yo'q" in (await send(text="📢 Kanalim")).texts()[0]
    assert "Kanal ulandi" in (await send(text="@moda_kanal")).texts()[-1]

    # Tovar qo'shish
    await send(text="➕ Tovar qo'shish")
    assert "<b>1</b>/10" in (await send(photo=photo("A"))).texts()[0]
    assert "<b>2</b>/10" in (await send(photo=photo("B"))).texts()[0]
    assert "nomini" in (await send(text="✅ Tayyor")).texts()[0]
    assert "Narxini" in (await send(text="Erkaklar ko'ylagi")).texts()[0]
    assert "Razmer" in (await send(text="250 000")).texts()[0]
    r = await send(text="S qora 5\nM qora 3\nxato")
    assert "tushunmadim" in r.texts()[0] and "M qora — 3 ta" in r.texts()[1]
    # tugmalar bilan qo'shish
    await press("vw:start:")
    await press("vw:size:L")
    await press("vw:color:oq")
    assert "L oq — 2 ta" in (await press("vw:qty:2")).texts()[0]
    assert "Tavsif" in (await send(text="✅ Tayyor")).texts()[0]
    r = await send(text="Paxta, Turkiya")
    assert isinstance(r.requests[1], SendMediaGroup)  # oldindan ko'rish: albom + matn

    # Tahrirlash: narxni o'zgartiramiz
    await press("pv:edit:")
    await press("pv:field:price")
    r = await send(text="300k")
    assert "300 000" in r.texts()[-1]

    # Kanalga joylash
    r = await press("pv:publish:")
    sent_to_channel = [q for q in r.requests if getattr(q, "chat_id", None) == CHANNEL_ID]
    assert isinstance(sent_to_channel[0], SendMediaGroup)
    assert [m.media for m in sent_to_channel[0].media] == ["A", "B"]  # eng katta o'lcham
    buttons = sent_to_channel[1].reply_markup.inline_keyboard
    async with factory() as s:
        product = await s.scalar(select(Product))
        post = await s.scalar(select(ChannelPost))
        seller = await s.scalar(select(Seller))
    assert buttons[0][0].url == f"https://t.me/seus_bot?start=p_{product.public_id}"
    assert buttons[1][0].url == "https://t.me/laziz"
    assert post.message_ids and post.button_message_id == post.message_ids[-1]
    assert seller.phone == "+998901234567" and product.price == 300000
    assert "joylandi" in r.texts()[-1]

    # Ikkinchi marta bosish — eskirgan
    r = await press("pv:publish:")
    assert not [q for q in r.requests if getattr(q, "chat_id", None) == CHANNEL_ID]

    # Xaridor havolani ochadi
    r = await send(text=f"/start p_{product.public_id}")
    assert "tez orada" in r.texts()[-1]
    r = await send(text="/start p_YOQTOVAR12")
    assert "sotuvda yo'q" in r.texts()[0]

    # Tovarlarim
    r = await send(text="📦 Tovarlarim")
    assert "1 ta" in r.texts()[0]
    r = await press(f"pr:off:{product.id}:0")
    async with factory() as s:
        assert not (await s.get(Product, product.id)).is_active


async def test_unknown_text_and_cancel(env):
    send, press, _ = env
    assert "ro'yxatdan" in (await send(text="salom")).texts()[0].lower()
    assert "/start" in (await send(text="/cancel")).texts()[0]
