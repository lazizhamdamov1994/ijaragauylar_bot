"""
Telegram Bot API bilan rasm ishi - BITTA joyda.
==========================================================================
Avval bot.py PTB (`context.bot`) orqali, dashboard.py esa xom `httpx` orqali
Telegram bilan gaplashardi - ikkalasi mustaqil, bir-biridan bexabar edi.
Endi ikkalasi ham shu yerdagi (xom httpx'ga asoslangan, PTB'ga bog'liq
bo'lmagan) funksiyalardan foydalanadi - shu jumladan yangi watermark
bosish oqimi ham shu yerda.
"""
import json
import logging

import httpx

from common.config import BOT_TOKEN
from common.watermark import apply_watermark

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TELEGRAM_FILE_API = f"https://api.telegram.org/file/bot{BOT_TOKEN}"


async def download_photo_bytes(file_id: str) -> bytes | None:
    """Telegram file_id orqali rasm baytlarini yuklab oladi. Xatolikda None."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id})
            data = resp.json()
            if not data.get("ok"):
                return None
            file_path = data["result"]["file_path"]
            img_resp = await client.get(f"{TELEGRAM_FILE_API}/{file_path}")
            if img_resp.status_code != 200:
                return None
            return img_resp.content
    except Exception:
        logger.exception("Telegram'dan rasm yuklab olishda xatolik (file_id=%s)", file_id)
        return None


async def upload_photo_bytes(chat_id: int, image_bytes: bytes, filename: str = "rasm.jpg") -> str | None:
    """Rasm baytlarini bitta chatga yuklab, YANGI file_id qaytaradi. Xatolikda None."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{TELEGRAM_API}/sendPhoto",
                data={"chat_id": str(chat_id)},
                files={"photo": (filename, image_bytes)},
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning("sendPhoto muvaffaqiyatsiz: %s", data.get("description"))
                return None
            return data["result"]["photo"][-1]["file_id"]
    except Exception:
        logger.exception("Telegram'ga rasm yuklashda xatolik")
        return None


async def watermark_telegram_photo(file_id: str, proxy_chat_id: int) -> str:
    """Mavjud Telegram file_id'ga watermark bosib, YANGI file_id qaytaradi.
    Har qanday bosqichda xatolik bo'lsa (yuklab bo'lmadi, qayta yuklab
    bo'lmadi) - ORIGINAL file_id qaytariladi, ya'ni e'lon joylash HECH
    QACHON shu sabab bilan to'xtab qolmaydi, faqat watermark'siz qoladi."""
    if not proxy_chat_id:
        return file_id
    raw = await download_photo_bytes(file_id)
    if raw is None:
        return file_id
    watermarked = apply_watermark(raw)
    new_file_id = await upload_photo_bytes(proxy_chat_id, watermarked)
    return new_file_id or file_id


def watermark_photo_bytes_list(images: list[bytes]) -> list[bytes]:
    """Xom bayt ro'yxatiga (masalan veb-saytdan yuklangan rasmlar) watermark
    bosadi - qayta Telegram'ga yuklab olish SHART EMAS, chunki baytlar
    allaqachon bizda."""
    return [apply_watermark(img) for img in images]
