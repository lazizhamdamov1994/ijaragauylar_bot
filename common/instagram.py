"""
E'lonlarni Instagram'ga avtomatik Reels sifatida joylash - IXTIYORIY qatlam.

MUHIM tamoyil (boshqa ixtiyoriy qatlamlar - common/ai.py, Instagram'ning
o'zi - bilan bir xil): kerakli sozlamalar (.env dagi INSTAGRAM_ACCESS_TOKEN
va INSTAGRAM_BUSINESS_ACCOUNT_ID) bo'sh bo'lsa YOKI admin
"instagram_auto_post_enabled" sozlamasini o'chirib qo'ysa - bu modul JIM
ravishda hech narsa qilmaydi. Har qanday bosqichda xatolik (tarmoq, Meta
API, video yasash) yuz bersa - log qilinib yutib yuboriladi, e'lonni
kanalga joylash oqimi HECH QACHON bu sabab bilan to'xtamaydi/kechikmaydi
(shuning uchun chaqiruvchi kod buni fire-and-forget - asyncio.create_task -
sifatida chaqirishi kerak, natijani kutmasdan).

Meta Content Publishing API oqimi (Reels uchun):
  1. POST /{ig-user-id}/media  (video_url, caption, media_type=REELS)
     -> {id: creation_id}  - Instagram videoni o'zi SIZNING URL'ingizdan
        yuklab oladi (to'g'ridan-to'g'ri fayl yuklash qo'llab-quvvatlanmaydi),
        shuning uchun video avval SITE_URL orqali qisqa muddat ochiq URL'da
        turishi kerak (pastdagi `_save_video_for_public_serving`).
  2. GET /{creation_id}?fields=status_code  - FINISHED bo'lguncha kutiladi
     (Instagram video konteynerini orqa fonda tayyorlaydi).
  3. POST /{ig-user-id}/media_publish  (creation_id) -> {id: media_id}

Kunlik chegarasi: Meta Content Publishing API taxminan 25 ta post/kun bilan
cheklaydi (instagram_daily_post_limit sozlamasi, standart 25) - shundan
oshsa, qolgan e'lonlar shunchaki Instagram'ga joylanmaydi (kanalga baribir
joylanadi), ertasi kuni avtomatik tiklanadi.
"""
import asyncio
import logging
import os
import secrets

import httpx

from common.config import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID, SITE_URL
from common.db import count_today_instagram_posts, get_setting, log_instagram_post
from common.slideshow import build_instagram_caption, build_slideshow_video
from common.telegram_media import download_photo_bytes

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Video yuklab olinishini (Instagram o'zi SITE_URL'dan tortib oladi) kutish
# uchun maksimal urinishlar soni va oraliq - umumiy taxminan 3 daqiqa.
_STATUS_POLL_ATTEMPTS = 18
_STATUS_POLL_INTERVAL_SEC = 10

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IG_VIDEO_CACHE_DIR = os.path.join(BASE_DIR, "ig_video_cache")
os.makedirs(IG_VIDEO_CACHE_DIR, exist_ok=True)


def is_instagram_configured() -> bool:
    return bool(INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID)


def is_instagram_posting_enabled() -> bool:
    return is_instagram_configured() and get_setting("instagram_auto_post_enabled", "0") == "1"


def is_instagram_posting_throttled() -> bool:
    limit = int(get_setting("instagram_daily_post_limit", "25") or "25")
    if limit <= 0:
        return False
    return count_today_instagram_posts() >= limit


def _save_video_for_public_serving(video_bytes: bytes) -> str:
    """Video baytlarini diskka (ig_video_cache/) yozib, Instagram o'zi
    yuklab olishi uchun ochiq URL qaytaradi (web/photos.py:
    GET /ig-video/{token}.mp4 orqali xizmat qiladi). Token taxmin
    qilib bo'lmaydigan (secrets.token_urlsafe) - mazmuni maxfiy emas
    (kanalga allaqachon joylangan e'lon rasmlari), lekin shunchaki
    tasodifiy odam/bot topib olmasligi uchun."""
    token = secrets.token_urlsafe(24)
    path = os.path.join(IG_VIDEO_CACHE_DIR, f"{token}.mp4")
    with open(path, "wb") as f:
        f.write(video_bytes)
    return f"{SITE_URL}/ig-video/{token}.mp4", path


async def _create_media_container(client: httpx.AsyncClient, video_url: str, caption: str) -> str | None:
    resp = await client.post(
        f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        },
    )
    data = resp.json()
    if "id" not in data:
        logger.warning("Instagram media konteyner yaratilmadi: %s", data)
        return None
    return data["id"]


async def _wait_until_ready(client: httpx.AsyncClient, creation_id: str) -> bool:
    for _ in range(_STATUS_POLL_ATTEMPTS):
        resp = await client.get(
            f"{GRAPH_API_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": INSTAGRAM_ACCESS_TOKEN},
        )
        data = resp.json()
        status = data.get("status_code")
        if status == "FINISHED":
            return True
        if status in ("ERROR", "EXPIRED"):
            logger.warning("Instagram video konteyneri tayyor bo'lmadi (status=%s): %s", status, data)
            return False
        await asyncio.sleep(_STATUS_POLL_INTERVAL_SEC)
    logger.warning("Instagram video konteyneri kutish vaqti tugadi (creation_id=%s)", creation_id)
    return False


async def _publish_media(client: httpx.AsyncClient, creation_id: str) -> str | None:
    resp = await client.post(
        f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": INSTAGRAM_ACCESS_TOKEN},
    )
    data = resp.json()
    if "id" not in data:
        logger.warning("Instagram'da post qilib bo'lmadi: %s", data)
        return None
    return data["id"]


async def post_reel_to_instagram(video_url: str, caption: str) -> str | None:
    """To'liq Meta Content Publishing oqimini bajaradi. Muvaffaqiyatda
    media_id, aks holda None qaytaradi - hech qachon xatolik ko'tarmaydi."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            creation_id = await _create_media_container(client, video_url, caption)
            if not creation_id:
                return None
            if not await _wait_until_ready(client, creation_id):
                return None
            return await _publish_media(client, creation_id)
    except Exception:
        logger.exception("Instagram'ga post qilishda kutilmagan xatolik")
        return None


async def maybe_post_listing_to_instagram(listing: dict) -> None:
    """Kanalga ENDI joylangan e'londan Instagram Reels yasab joylashga
    harakat qiladi - sozlamalar/chegaradan o'tmasa yoki istalgan bosqichda
    xato chiqsa, JIM o'tkazib yuboradi. Chaqiruvchi kod buni
    `asyncio.create_task(...)` orqali, natijani kutmasdan chaqirishi kerak
    (kanalga joylash oqimini hech qachon kechiktirmasligi uchun)."""
    try:
        if not is_instagram_posting_enabled():
            return
        if not SITE_URL:
            logger.warning("Instagram joylash yoqilgan, lekin SITE_URL/DASHBOARD_URL sozlanmagan - o'tkazib yuborildi")
            return
        if is_instagram_posting_throttled():
            logger.info("Instagram kunlik chegarasiga yetildi - e'lon #%s o'tkazib yuborildi", listing.get("id"))
            return
        photos = listing.get("photos") or []
        if not photos:
            return

        photo_bytes = []
        for file_id in photos[:10]:
            raw = await download_photo_bytes(file_id)
            if raw:
                photo_bytes.append(raw)
        if not photo_bytes:
            return

        manzil = listing.get("manzil") or ""
        narx = listing.get("narx") or ""
        xona = listing.get("xona") or ""
        video = await build_slideshow_video(photo_bytes, manzil, narx, xona)
        if video is None:
            return

        caption = build_instagram_caption(
            manzil, narx, xona=xona,
            kimlarga=listing.get("kimlarga") or "", qulaylik=listing.get("qulaylik") or "",
        )
        video_url, video_path = _save_video_for_public_serving(video)
        try:
            media_id = await post_reel_to_instagram(video_url, caption)
            log_instagram_post(listing["id"], media_id)
        finally:
            # Instagram video konteynerini tayyorlab bo'lgach (yoki xato
            # bo'lsa ham) faylga endi ehtiyoj yo'q - diskni band qilmaslik
            # uchun darhol o'chiramiz.
            try:
                os.remove(video_path)
            except OSError:
                pass
    except Exception:
        logger.exception("E'lonni Instagram'ga joylashda kutilmagan xatolik (listing_id=%s)", listing.get("id"))
