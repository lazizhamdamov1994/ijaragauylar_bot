"""
Telegram fayl-ID orqali rasmlarni xavfsiz ko'rsatish + disk keshini
PHOTO_CACHE_MAX_MB ichida ushlab turish (LRU tozalash).
"""
import asyncio
import hashlib
import logging
import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from common.config import BOT_TOKEN, PHOTO_CACHE_MAX_MB

logger = logging.getLogger(__name__)
router = APIRouter()

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
    tashqariga chiqmaydi (server tomonida ishlatiladi, keshlanadi)."""
    safe_name = hashlib.sha256(file_id.encode()).hexdigest() + ".jpg"
    cache_path = os.path.join(PHOTO_CACHE_DIR, safe_name)

    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
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
            content = img_resp.content
        with open(cache_path, "wb") as f:
            f.write(content)
        return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})
    except HTTPException:
        raise
    except Exception:
        logger_fallback_placeholder = None
        raise HTTPException(status_code=404)




# ============================= OMMAVIY SAYT - DIZAYN YORDAMCHILARI =============================

# SITE_CSS endi Python satrida emas - static/site.css haqiqiy fayl sifatida
# saqlanadi (mobil-moslashuvchanlik CSS'i shu yerda tekshirilib, tuzatilgan).
# Fayl BASE_DIR/static/site.css'da, /static/site.css orqali xizmat qiladi
# (pastroqda StaticFiles orqali ulangan).


# ============================= 3 TILLI QO'LLAB-QUVVATLASH (o'zbek / rus / ingliz) =============================
# Faqat OMMAVIY (parolsiz) sahifalar tarjima qilinadi - admin panel ichki vosita bo'lgani
# uchun o'zbek tilida qoladi. Til ?lang= so'rov parametri yoki "lang" cookie orqali tanlanadi.


