"""
Kunlik "Omad g'ildiragi" o'yini - har kuni kanalga post joylanadi, obunachi
tugmani bosib botga o'tadi va BEPUL Limit (1/5/30 kun) yutib olish imkoniga
ega bo'ladi. Maqsad - obunachilarni muntazam jonlantirish, botdan foydalanish
faolligini oshirish va uy egalarining e'lonlari tezroq ijarachilarga
topshirilishi (faol limitga ega foydalanuvchi bepul/chegirmali e'lon
joylay oladi).

MUHIM: yutuq - mavjud `subscriptions` (Limit) jadvalidan foydalanadi
(grant_bonus_subscription_days), shuning uchun bot/sayt/admin panelning
BARCHA joylarida darhol, qo'shimcha kod yozmasdan ishlay boshlaydi.
"""
import logging
import random
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from common.config import CHANNEL_ID

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


def _parse_prize_weights(raw: str) -> list:
    """"kun:og'irlik" juftliklarini ("0:85,1:10,5:4,30:1") ro'yxatga
    o'giradi. Noto'g'ri/bo'sh format bo'lsa - xavfsiz standart qiymatga
    qaytadi, hech qachon o'yin shu sabab bilan buzilmaydi."""
    pairs = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        days_s, weight_s = part.split(":", 1)
        try:
            days, weight = int(days_s.strip()), int(weight_s.strip())
        except ValueError:
            continue
        if weight > 0:
            pairs.append((days, weight))
    return pairs or [(0, 1)]


def _pick_prize_days() -> int:
    raw = get_setting("lucky_wheel_prize_weights", "0:85,1:10,5:4,30:1")
    pairs = _parse_prize_weights(raw)
    days_options = [p[0] for p in pairs]
    weights = [p[1] for p in pairs]
    return random.choices(days_options, weights=weights, k=1)[0]


def _today_tashkent() -> str:
    return datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d")


async def omadpost_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin buyrug'i: /omadpost - kunlik "Omad g'ildiragi" postini
    rejadagi vaqtni kutmasdan, HOZIR qo'lda kanalga joylaydi (sinov yoki
    rejadagi post negadir o'tkazib yuborilgan holatlar uchun)."""
    if not is_admin(update.effective_user.id):
        return
    if not CHANNEL_ID:
        await update.message.reply_text("⚠️ CHANNEL_ID sozlanmagan.")
        return
    await job_post_lucky_wheel(context, force=True)
    await update.message.reply_text("✅ Omad g'ildiragi posti kanalga joylandi.")


async def job_post_lucky_wheel(context: ContextTypes.DEFAULT_TYPE, force: bool = False) -> None:
    """Har kuni kanalga yangi o'yin postini joylaydi (admin sozlagan
    soatda) - tugma https://t.me/BOT?start=wheel_<bugungi-sana> havolasiga
    olib boradi. `force=True` - /omadpost orqali qo'lda chaqirilganda
    "yoqilgan/o'chirilgan" sozlamasini e'tiborsiz qoldirib, baribir
    joylaydi (sinov uchun)."""
    if not CHANNEL_ID:
        return
    if not force and (get_setting("lucky_wheel_enabled", "1") or "1") != "1":
        return
    today = _today_tashkent()
    attempts = int(get_setting("lucky_wheel_attempts_per_day", "3") or "3")
    text = (
        "\U0001F3B0 <b>Kunlik Omad g'ildiragi!</b>\n\n"
        f"Bugun ham omadingizni sinab ko'ring — har bir foydalanuvchiga <b>{attempts} marta</b> urinish beriladi.\n"
        "Yutuq — BEPUL Limit (1, 5 yoki 30 kunlik)! \U0001F381\n\n"
        "Pastdagi tugmani bosing \U0001F447"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
        "\U0001F3B0 Omadimni sinash", url=f"https://t.me/{context.bot.username}?start=wheel_{today}",
    )]])
    try:
        await context.bot.send_message(CHANNEL_ID, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception:
        logger.exception("Omad g'ildiragi postini kanalga joylashda xatolik")


async def omadgoliblar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin buyrug'i: /omadgoliblar - kun yakunidagi (23:45) g'oliblar
    postini rejadagi vaqtni kutmasdan, HOZIR kanalga joylaydi (sinov
    uchun)."""
    if not is_admin(update.effective_user.id):
        return
    if not CHANNEL_ID:
        await update.message.reply_text("⚠️ CHANNEL_ID sozlanmagan.")
        return
    today = _today_tashkent()
    winners = get_lucky_wheel_winners(today)
    if not winners:
        await update.message.reply_text(
            "ℹ️ Bugun hali hech kim yutuq yutmagan - joylash uchun g'olib yo'q."
        )
        return
    await job_announce_lucky_wheel_winners(context)
    await update.message.reply_text(f"✅ G'oliblar posti kanalga joylandi ({len(winners)} ta g'olib).")


async def job_announce_lucky_wheel_winners(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kun yakunida (admin postni qaysi soatda joylashidan qat'iy nazar,
    kechqurun bir marta) shu kungi BARCHA g'oliblarni BITTA postda e'lon
    qiladi - har bir yutuqni alohida e'lon qilish kanalni to'ldirib
    yuboradi, shuning uchun bitta umumiy post ma'qul."""
    if not CHANNEL_ID:
        return
    today = _today_tashkent()
    winners = get_lucky_wheel_winners(today)
    if not winners:
        return
    lines = ["\U0001F3C6 <b>Bugungi Omad g'ildiragi g'oliblari:</b>\n"]
    for w in winners:
        name = esc((w.get("full_name") or "").strip() or (f"@{w['username']}" if w.get("username") else "Foydalanuvchi"))
        lines.append(f"\U0001F389 {name} — <b>{w['prize_days']} kunlik</b> BEPUL Limit")
    lines.append("\nErtaga SIZ ham g'olib bo'lishingiz mumkin — kanaldagi yangi postni kuzatib boring! \U0001F3B0")
    try:
        await context.bot.send_message(CHANNEL_ID, "\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("G'oliblar postini kanalga joylashda xatolik")


async def lucky_wheel_spin(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str) -> None:
    """`/start wheel_<sana>` chuqur-havolasi orqali chaqiriladi - bitta
    urinishni hisoblaydi, yutuq chiqsa darhol Limit beradi."""
    user = update.effective_user
    today = _today_tashkent()
    game_date = payload.split("_", 1)[1] if "_" in payload else ""

    if (get_setting("lucky_wheel_enabled", "1") or "1") != "1":
        await update.message.reply_text(
            "⚠️ Omad g'ildiragi o'yini hozircha o'chirilgan.",
            reply_markup=main_menu_keyboard(user.id),
        )
        return

    if game_date != today:
        await update.message.reply_text(
            "⏰ Bu o'yinning muddati tugagan. Bugungi yangi postni kanalda topib, qayta urinib ko'ring!",
            reply_markup=main_menu_keyboard(user.id),
        )
        return

    max_attempts = int(get_setting("lucky_wheel_attempts_per_day", "3") or "3")
    used = count_today_lucky_wheel_spins(user.id, today)
    if used >= max_attempts:
        await update.message.reply_text(
            f"\U0001F3B0 Bugun uchun {max_attempts} ta urinishingiz tugadi. Ertaga yangi o'yin boshlanadi, omad tilaymiz! \U0001F340",
            reply_markup=main_menu_keyboard(user.id),
        )
        return

    prize_days = _pick_prize_days()
    record_lucky_wheel_spin(user.id, user.full_name, user.username, today, prize_days)
    remaining = max_attempts - used - 1

    if prize_days <= 0:
        await update.message.reply_text(
            "\U0001F3B0 Afsus, bu safar yutqazdingiz. \U0001F614\n\n"
            f"Qolgan urinishlaringiz: <b>{remaining}/{max_attempts}</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(user.id),
        )
        return

    expire_at = grant_bonus_subscription_days(user.id, prize_days)
    await update.message.reply_text(
        f"\U0001F389 <b>Tabriklaymiz!</b> Siz <b>{prize_days} kunlik BEPUL Limit</b> yutib oldingiz!\n\n"
        f"Limitingiz endi <b>{expire_at[:10]}</b> gacha amal qiladi.\n\n"
        f"Qolgan urinishlaringiz: <b>{remaining}/{max_attempts}</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(user.id),
    )
