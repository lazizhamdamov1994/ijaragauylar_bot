"""Botni ishga tushirish: python -m app.bot"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.bot.handlers import build_router
from app.bot.logging_setup import setup_logging
from app.bot.middlewares import AlbumMiddleware, DbSessionMiddleware, SellerMiddleware
from app.config import BASE_DIR, get_settings
from app.db.session import make_engine, make_session_factory

log = logging.getLogger("seus")


async def main() -> int:
    settings = get_settings()
    token = settings.bot_token.get_secret_value().strip()
    setup_logging(
        settings.log_level,
        secrets=[token, settings.db_password.get_secret_value()],
        log_dir=BASE_DIR / "logs",
    )
    if not token:
        log.error(".env faylida BOT_TOKEN yozilmagan. README.md dagi 3-qadamni ko'ring.")
        return 1

    engine = make_engine(settings.db_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        log.error(
            "PostgreSQL bazasiga ulanib bo'lmadi (%s). PostgreSQL ishlayaptimi va .env dagi "
            "DB_* qiymatlar to'g'rimi — tekshiring.", type(e).__name__,
        )
        return 1
    session_factory = make_session_factory(engine)

    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(DbSessionMiddleware(session_factory))
    dp.update.outer_middleware(SellerMiddleware())
    dp.message.outer_middleware(AlbumMiddleware())
    dp.include_router(build_router())

    # Hisobotlar uchun rejalashtiruvchi (keyingi bosqichlarda vazifalar qo'shiladi)
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.start()

    try:
        try:
            me = await bot.me()
        except TelegramUnauthorizedError:
            log.error("BOT_TOKEN noto'g'ri. @BotFather'dan tokenni tekshirib, .env ga qayta yozing.")
            return 1
        except TelegramNetworkError:
            log.error("Telegram'ga ulanib bo'lmadi. Internet aloqasini tekshiring.")
            return 1
        log.info("Bot ishga tushdi: @%s", me.username)
        await bot.set_my_commands([
            BotCommand(command="start", description="Bosh menyu"),
            BotCommand(command="cancel", description="Bekor qilish"),
        ])
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await engine.dispose()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("Bot to'xtatildi.")
