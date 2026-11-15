"""Rasmlarni diskka saqlash va ularga "Nihola Estate" suv belgisini qo'yish."""
from __future__ import annotations

import asyncio
import io
import logging
import shutil
from pathlib import Path

from aiogram import Bot
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import settings
from .db import Database

log = logging.getLogger(__name__)
MAX_SIDE = 2560


def listing_dir(listing_id: int) -> Path:
    return settings.media_dir / f"L{listing_id}"


def remove_listing_dir(listing_id: int) -> None:
    shutil.rmtree(listing_dir(listing_id), ignore_errors=True)


def _watermark(data: bytes, dest: Path, text: str) -> None:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    if text:
        w, h = img.size
        size = max(18, w // 20)
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:  # juda eski Pillow
            font = ImageFont.load_default()
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        box = draw.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        margin = max(12, w // 40)
        x, y = w - tw - margin, h - th - margin * 1.4
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 110))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 170))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=88)


async def process_listing_media(bot: Bot, db: Database, listing_id: int) -> None:
    """Har bir faylni diskka yuklaydi (web sayt uchun), rasmlarga suv belgisi qo'yadi.

    Suv belgili rasm hali Telegramga yuklanmagan, shuning uchun ready=0 qilib qo'yiladi —
    birinchi yuborilganda yangi file_id saqlanadi.
    """
    folder = listing_dir(listing_id)
    for row in await db.get_media(listing_id):
        if row["local_path"]:
            continue
        try:
            buf = io.BytesIO()
            await bot.download(row["file_id"], destination=buf)
            if row["kind"] == "photo":
                dest = folder / f"{row['position']:02d}.jpg"
                await asyncio.to_thread(_watermark, buf.getvalue(), dest, settings.watermark_text)
                await db.update_media(
                    row["id"], local_path=str(dest), ready=0 if settings.watermark_text else 1)
            else:
                dest = folder / f"{row['position']:02d}.mp4"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(buf.getvalue())
                await db.update_media(row["id"], local_path=str(dest))
        except Exception as e:  # masalan 20 MB dan katta video — Bot API yuklab bermaydi
            log.warning("Media %s yuklab olinmadi: %s", row["id"], e)
