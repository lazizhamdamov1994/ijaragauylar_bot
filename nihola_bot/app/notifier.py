"""Ommaviy xabar yuborish: limitga rioya qiladi, botni bloklaganlarni belgilaydi."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import settings
from .db import Database
from .keyboards import deep_link
from .matching import listing_matches
from .posting import send_card
from .texts import code, short_title

log = logging.getLogger(__name__)

RATE_DELAY = 1 / 25  # Telegram limiti ~30 xabar/soniya, biz 25 bilan yuboramiz


async def broadcast(
    db: Database, user_ids: list[int], send: Callable[[int], Awaitable],
) -> dict:
    """Har bir foydalanuvchiga send(user_id) ni chaqiradi. Natija: ok/blocked/error soni."""
    res = {"ok": 0, "blocked": 0, "error": 0}
    for uid in user_ids:
        for attempt in range(3):
            try:
                await send(uid)
                res["ok"] += 1
                break
            except TelegramRetryAfter as e:
                log.warning("Flood limit: %s soniya kutamiz", e.retry_after)
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError:
                await db.set_user_field(uid, "active", 0)
                res["blocked"] += 1
                break
            except TelegramBadRequest as e:
                if "chat not found" in str(e).lower():
                    await db.set_user_field(uid, "active", 0)
                    res["blocked"] += 1
                else:
                    log.warning("Xabar %s ga ketmadi: %s", uid, e)
                    res["error"] += 1
                break
            except Exception as e:
                log.exception("Xabar %s ga ketmadi: %s", uid, e)
                res["error"] += 1
                break
        await asyncio.sleep(RATE_DELAY)
    return res


async def notify_admins(bot: Bot, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    targets = [settings.leads_chat_id] if settings.leads_chat_id else list(settings.admin_ids)
    for chat_id in targets:
        try:
            await bot.send_message(chat_id, text, reply_markup=kb)
        except Exception as e:
            log.warning("Adminga (%s) xabar ketmadi: %s", chat_id, e)


async def notify_new_listing(bot: Bot, db: Database, listing_id: int, report_to: int | None) -> None:
    """Yangi e'lon: filtri mos va "darhol" rejimidagi mijozlarga kartochka yuboradi."""
    listing = await db.get_listing(listing_id)
    filters = await db.filters_for_mode("instant")
    targets = [f["user_id"] for f in filters if listing_matches(listing, f)]
    if not targets:
        if report_to:
            await bot.send_message(report_to, f"ℹ️ #{code(listing_id)}: filtri mos mijoz hozircha yo‘q.")
        return
    if report_to:
        await bot.send_message(
            report_to, f"🔔 #{code(listing_id)} — {len(targets)} ta mos mijozga yuborilmoqda...")

    async def send(uid: int):
        await send_card(bot, db, uid, listing, prefix="🔔 <b>Sizga mos uy joylandi!</b>\n\n")

    res = await broadcast(db, targets, send)
    if report_to:
        await bot.send_message(
            report_to,
            f"✅ #{code(listing_id)} xabarnomasi tugadi.\n"
            f"Yetkazildi: {res['ok']} · Bloklagan: {res['blocked']} · Xato: {res['error']}",
        )


async def notify_favorites(bot: Bot, db: Database, listing_id: int, text: str) -> int:
    """E'lonni saqlab qo'yganlarga xabar (narx tushdi / sotildi)."""
    users = await db.favorite_user_ids(listing_id)
    listing = await db.get_listing(listing_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📄 E’lonni ochish", callback_data=f"u:card:{listing_id}"),
        InlineKeyboardButton(text="🔔 O‘xshash uylar", callback_data=f"u:sim:{listing_id}"),
    ]])

    async def send(uid: int):
        await bot.send_message(uid, f"{text}\n\n{short_title(listing)}", reply_markup=kb)

    res = await broadcast(db, users, send)
    return res["ok"]


# ---------- kunlik dayjest ----------
async def send_daily_digest(bot: Bot, db: Database) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    fresh = await db.published_since(since)
    if not fresh:
        return {"ok": 0, "blocked": 0, "error": 0}
    per_user: dict[int, list[dict]] = {}
    for f in await db.filters_for_mode("daily"):
        matched = [l for l in fresh if listing_matches(l, f)]
        if matched:
            per_user[f["user_id"]] = matched

    async def send(uid: int):
        items = per_user[uid][:15]
        lines = [f"🗞 <b>Bugun sizga mos {len(per_user[uid])} ta uy joylandi:</b>", ""]
        for l in items:
            lines.append(f"• <a href=\"{deep_link(f'l_{l['id']}')}\">{short_title(l)}</a>")
        await bot.send_message(uid, "\n".join(lines))

    return await broadcast(db, list(per_user), send)


async def digest_loop(bot: Bot, db: Database) -> None:
    tz = ZoneInfo(settings.timezone)
    while True:
        try:
            now = datetime.now(tz)
            today = now.strftime("%Y-%m-%d")
            if now.hour >= settings.digest_hour and await db.get_meta("digest_date") != today:
                await db.set_meta("digest_date", today)
                res = await send_daily_digest(bot, db)
                log.info("Kunlik dayjest yuborildi: %s", res)
        except Exception:
            log.exception("Dayjest xatosi")
        await asyncio.sleep(60)
