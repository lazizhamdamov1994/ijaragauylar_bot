"""
Telegram fayl-ID orqali rasmlarni xavfsiz ko'rsatish + disk keshini
PHOTO_CACHE_MAX_MB ichida ushlab turish (LRU tozalash).
"""
import asyncio
import hashlib
import io
import logging
import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from PIL import Image, ImageOps

from common.config import BOT_TOKEN, PHOTO_CACHE_MAX_MB

logger = logging.getLogger(__name__)
router = APIRouter()

# MUHIM (tezlik/SEO): Telegram'dan kelgan xom rasm ko'pincha kerakidan
# ancha katta (bir necha MB) bo'ladi - saytda hech qaysi joyda bunday
# o'lcham/sifat shart emas. Shuning uchun keshlashdan OLDIN bir marta
# WebP'ga o'girib, mos o'lchamga kichraytiramiz - shundan keyin HAR BIR
# tashrifchi shu KICHIK, TEZ yuklanadigan versiyani oladi.
PHOTO_MAX_DIMENSION = 1600
PHOTO_WEBP_QUALITY = 82


def _optimize_photo(raw: bytes) -> bytes | None:
    """Rasmni WebP'ga o'giradi + mos o'lchamga kichraytiradi. Muvaffaqiyatsiz
    bo'lsa (buzuq/noma'lum format) None qaytaradi - chaqiruvchi kod xom
    baytlarni ishlatishda davom etadi, rasm HECH QACHON yo'qolmaydi."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img).convert("RGB")
        if img.width > PHOTO_MAX_DIMENSION or img.height > PHOTO_MAX_DIMENSION:
            ratio = PHOTO_MAX_DIMENSION / max(img.width, img.height)
            new_size = (max(int(img.width * ratio), 1), max(int(img.height * ratio), 1))
            img = img.resize(new_size, Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="WEBP", quality=PHOTO_WEBP_QUALITY)
        return out.getvalue()
    except Exception:
        logger.exception("Rasmni WebP'ga o'girishda xatolik - xom bayt ishlatiladi")
        return None

# ============================= RASM PROKSI (Telegram fayllarini xavfsiz ko'rsatish) =============================

# MUHIM: repo ILDIZIDAGI photo_cache/ papkasi ishlatiladi (bu fayl endi
# web/ ichida bo'lsa ham) - shuning uchun __file__'ning ENASINING ENASI
# (repo ildizi) olinadi, aks holda eski keshlangan rasmlar "yo'qolib qoladi".
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_CACHE_DIR = os.path.join(BASE_DIR, "photo_cache")
os.makedirs(PHOTO_CACHE_DIR, exist_ok=True)
PHOTO_CACHE_CLEANUP_INTERVAL_SEC = 6 * 3600


def cleanup_photo_cache():
    """photo_cache/ papkasi hajmini PHOTO_CACHE_MAX_MB ichida ushlab turadi -
    diskda joy tugab qolmasligi uchun eng kam ko'rilgan (LRU) rasmlarni o'chiradi."""
    try:
        entries = []
        total = 0
        with os.scandir(PHOTO_CACHE_DIR) as it:
            for entry in it:
                if not entry.is_file():
                    continue
                st = entry.stat()
                entries.append((entry.path, st.st_atime, st.st_size))
                total += st.st_size
        limit = PHOTO_CACHE_MAX_MB * 1024 * 1024
        if total <= limit:
            return
        entries.sort(key=lambda e: e[1])
        for path, _atime, size in entries:
            if total <= limit:
                break
            try:
                os.remove(path)
                total -= size
            except OSError:
                pass
        logger.info(f"photo_cache tozalandi, yangi hajm: {total / 1024 / 1024:.1f}MB")
    except Exception:
        logger.exception("photo_cache tozalashda xatolik")


async def periodic_photo_cache_cleanup():
    while True:
        await asyncio.sleep(PHOTO_CACHE_CLEANUP_INTERVAL_SEC)
        await asyncio.to_thread(cleanup_photo_cache)


async def start_photo_cache_cleanup():
    """web/app.py'ning FastAPI startup hodisasidan chaqiriladi (routerlar
    o'zining alohida on_event'ini qo'llab-quvvatlamaydi/tavsiya etilmaydi)."""
    await asyncio.to_thread(cleanup_photo_cache)
    asyncio.create_task(periodic_photo_cache_cleanup())


@router.get("/photo/{file_id}")
async def get_photo(file_id: str):
    """Telegram fayl-ID orqali rasmni XAVFSIZ ko'rsatadi - bot tokeni hech qachon
    tashqariga chiqmaydi (server tomonida ishlatiladi, keshlanadi, WebP'ga
    optimallashtiriladi)."""
    digest = hashlib.sha256(file_id.encode()).hexdigest()
    cache_path = os.path.join(PHOTO_CACHE_DIR, digest + ".webp")
    legacy_cache_path = os.path.join(PHOTO_CACHE_DIR, digest + ".jpg")

    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            content = f.read()
        return Response(content=content, media_type="image/webp", headers={"Cache-Control": "public, max-age=604800"})
    if os.path.exists(legacy_cache_path):
        # Eski (WebP'dan OLDINGI) kesh yozuvi yoki optimallashtirib
        # bo'lmagan rasm - JPEG sifatida ko'rsatamiz, qayta yuklab olishga
        # hojat yo'q.
        with open(legacy_cache_path, "rb") as f:
            content = f.read()
        return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})

    if not BOT_TOKEN:
        raise HTTPException(status_code=404)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile", params={"file_id": file_id})
            data = resp.json()
            if not data.get("ok"):
                raise HTTPException(status_code=404)
            file_path = data["result"]["file_path"]
            img_resp = await client.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}")
            if img_resp.status_code != 200:
                raise HTTPException(status_code=404)
            raw = img_resp.content
        optimized = await asyncio.to_thread(_optimize_photo, raw)
        if optimized is not None:
            with open(cache_path, "wb") as f:
                f.write(optimized)
            return Response(content=optimized, media_type="image/webp", headers={"Cache-Control": "public, max-age=604800"})
        # WebP'ga o'girib bo'lmadi (buzuq/noma'lum format) - xom baytni JPEG
        # sifatida keshlab, shu holicha ko'rsatamiz (rasm baribir ko'rinadi).
        with open(legacy_cache_path, "wb") as f:
            f.write(raw)
        return Response(content=raw, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404)




# ============================= OMMAVIY SAYT - DIZAYN YORDAMCHILARI =============================

# SITE_CSS endi Python satrida emas - static/site.css haqiqiy fayl sifatida
# saqlanadi (mobil-moslashuvchanlik CSS'i shu yerda tekshirilib, tuzatilgan).
# Fayl BASE_DIR/static/site.css'da, /static/site.css orqali xizmat qiladi
# (pastroqda StaticFiles orqali ulangan).


# ============================= 3 TILLI QO'LLAB-QUVVATLASH (o'zbek / rus / ingliz) =============================
# Faqat OMMAVIY (parolsiz) sahifalar tarjima qilinadi - admin panel ichki vosita bo'lgani
# uchun o'zbek tilida qoladi. Til ?lang= so'rov parametri yoki "lang" cookie orqali tanlanadi.


