"""Botni ishga tushirish."""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, LinkPreviewOptions

from .config import runtime, settings
from .db import Database
from .handlers import admin_manage, admin_new, user
from .middlewares import UserTrackingMiddleware
from .notifier import digest_loop

log = logging.getLogger("nihola")


def check_settings() -> None:
    problems = []
    if not settings.bot_token:
        problems.append("BOT_TOKEN bo'sh")
    if not settings.channel_id:
        problems.append("CHANNEL_ID bo'sh")
    if not settings.admin_ids:
        problems.append("ADMIN_IDS bo'sh")
    if problems:
        sys.exit(".env faylini to'ldiring: " + ", ".join(problems) + "  (namuna: .env.example)")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    check_settings()

    db = Database(settings.db_path)
    await db.connect()
    settings.media_dir.mkdir(parents=True, exist_ok=True)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview=LinkPreviewOptions(is_disabled=True),
        ),
    )
    me = await bot.get_me()
    runtime.bot_username = me.username
    log.info("Bot: @%s", me.username)

    try:
        chat = await bot.get_chat(settings.channel_id)
        log.info("Kanal topildi: %s", chat.title)
    except Exception as e:
        log.warning("Kanalga ulanib bo'lmadi (%s): botni kanalga ADMIN qilib qo'shing! %s",
                    settings.channel_id, e)

    await bot.set_my_commands([
        BotCommand(command="start", description="Bosh menyu"),
    ])

    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp.message.outer_middleware(UserTrackingMiddleware())
    dp.callback_query.outer_middleware(UserTrackingMiddleware())
    dp.include_routers(admin_manage.router, admin_new.router, user.router)

    digest = asyncio.create_task(digest_loop(bot, db))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        digest.cancel()
        await db.close()
        await bot.session.close()


def run() -> None:
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code not in (None, 0):
            raise
