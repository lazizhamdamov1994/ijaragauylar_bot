"""
Windows desktop admin dasturi uchun JSON API - web/api.py'dagi mavjud
admin panel endpointlaridan FARQLI auth usuli (HTTP Basic cookie-sessiya
o'rniga - Bearer token, common/desktop_auth.py'ga qarang), lekin xuddi
shu BIR XIL "yurak" funksiyalaridan foydalanadi (get_pending_listings,
post_listing_to_channel va h.k.) - mantiq ikki marta yozilmaydi.

MUHIM (OLX rasm olish): /api/desktop/olx-photos TEKSHIRILMAGAN - bu
muhitdan olx.uz saytiga chiqish imkoni yo'q edi, shuning uchun bu kod
OLX kabi saytlarning UMUMIY naqshlariga (og:image meta teglar + <img>
teglar) asoslanadi, lekin olx.uz'ning HAQIQIY joriy sahifa tuzilishi
bilan TEKSHIRILMAGAN. Agar ishlamasa - admin baribir rasmlarni qo'lda
(kompyuteriga saqlab) yuklay oladi, hech narsa buzilmaydi.
"""
import json as _json
import logging
import re
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.security.utils import get_authorization_scheme_param

from common.config import ADMIN_IDS, BOT_TOKEN, CHANNEL_USERNAME
from common.db import db, now_str
from common.desktop_auth import resolve_desktop_token
from common.telegram_media import watermark_photo_bytes_list

from bot.admin_moderation import log_channel_post
from bot.db import (
    approve_subscription,
    get_listing,
    get_pending_listings,
    get_pending_subscriptions,
    get_subscription,
    get_user,
    listing_price,
    log_ai_feedback,
    reject_subscription,
    stats_for_period,
    update_listing_status,
)
from bot.helpers import is_admin

from web.listings_data import normalize_phone_web, post_listing_to_channel
from web.pages import notify_telegram, telegram_upload_photos

logger = logging.getLogger(__name__)
router = APIRouter()


def desktop_auth_required(authorization: str = Header(default="")) -> int:
    """`Authorization: Bearer <token>` sarlavhasini tekshiradi - token
    haqiqiy va admin bo'lsa user_id qaytaradi, aks holda 401."""
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Token kerak (Authorization: Bearer <token>)")
    user_id = resolve_desktop_token(token)
    if not user_id or not is_admin(user_id):
        raise HTTPException(status_code=401, detail="Token yaroqsiz yoki admin huquqi yo'q")
    return user_id


@router.get("/api/desktop/me")
def api_desktop_me(user_id: int = Depends(desktop_auth_required)):
    u = get_user(user_id) or {}
    return {"ok": True, "user_id": user_id, "full_name": u.get("full_name"), "username": u.get("username")}


@router.get("/api/desktop/stats")
def api_desktop_stats(user_id: int = Depends(desktop_auth_required)):
    today = now_str()[:10]
    stats_today = stats_for_period(f"{today} 00:00:00", f"{today} 23:59:59")
    conn = db()
    total_listings = conn.execute("SELECT COUNT(*) c FROM listings WHERE status='approved' AND COALESCE(expired,0)=0").fetchone()["c"]
    total_subscribers = conn.execute("SELECT COUNT(*) c FROM subscriptions WHERE status='approved'").fetchone()["c"]
    conn.close()
    return {
        "ok": True, "today": stats_today,
        "active_listings": total_listings, "active_subscribers": total_subscribers,
        "listing_price": listing_price(),
    }


@router.get("/api/desktop/pending")
def api_desktop_pending(user_id: int = Depends(desktop_auth_required)):
    listings = get_pending_listings(limit=100)
    subs = get_pending_subscriptions(limit=100)
    return {"ok": True, "listings": listings, "subscriptions": subs}


@router.post("/api/desktop/pending/listing/{listing_id}/approve")
async def api_desktop_approve_listing(listing_id: int, user_id: int = Depends(desktop_auth_required)):
    listing = get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="not_found")
    if listing["status"] != "pending":
        raise HTTPException(status_code=409, detail="already_reviewed")
    message_id = await post_listing_to_channel(listing)
    if message_id is None:
        raise HTTPException(status_code=502, detail="channel_post_failed")
    update_listing_status(listing_id, "approved", channel_msg_id=message_id)
    log_channel_post(listing_id, message_id)
    log_ai_feedback(listing_id, was_flagged=bool(listing.get("ai_scam_warning")), decision="approved")
    link = f"https://t.me/{CHANNEL_USERNAME}" if CHANNEL_USERNAME else None
    msg = "✅ Sizning e'loningiz tasdiqlandi va kanalga joylandi!"
    if link:
        msg += f"\n{link}"
    await notify_telegram(listing["user_id"], msg)
    return {"ok": True, "channel_msg_id": message_id}


@router.post("/api/desktop/pending/listing/{listing_id}/reject")
async def api_desktop_reject_listing(listing_id: int, reason: str = Form(...), user_id: int = Depends(desktop_auth_required)):
    listing = get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="not_found")
    if listing["status"] != "pending":
        raise HTTPException(status_code=409, detail="already_reviewed")
    reason = reason.strip()[:500]
    if not reason:
        raise HTTPException(status_code=400, detail="empty_reason")
    update_listing_status(listing_id, "rejected", reason=reason)
    log_ai_feedback(listing_id, was_flagged=bool(listing.get("ai_scam_warning")), decision="rejected")
    await notify_telegram(listing["user_id"], f"❌ Sizning e'loningiz (#{listing_id}) rad etildi.\n\U0001F4DD Sabab: {reason}")
    return {"ok": True}


@router.post("/api/desktop/pending/subscription/{sub_id}/approve")
async def api_desktop_approve_subscription(sub_id: int, user_id: int = Depends(desktop_auth_required)):
    sub = get_subscription(sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="not_found")
    if sub["status"] != "pending":
        raise HTTPException(status_code=409, detail="already_reviewed")
    target_user_id, expire = approve_subscription(sub_id)
    await notify_telegram(target_user_id, f"✅ Limitingiz faollashtirildi!\nMuddati: <b>{expire[:10]}</b> gacha.")
    return {"ok": True, "expire_at": expire}


@router.post("/api/desktop/pending/subscription/{sub_id}/reject")
async def api_desktop_reject_subscription(sub_id: int, reason: str = Form(...), user_id: int = Depends(desktop_auth_required)):
    sub = get_subscription(sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="not_found")
    if sub["status"] != "pending":
        raise HTTPException(status_code=409, detail="already_reviewed")
    reason = reason.strip()[:500]
    if not reason:
        raise HTTPException(status_code=400, detail="empty_reason")
    reject_subscription(sub_id, reason)
    await notify_telegram(sub["user_id"], f"❌ Obuna so'rovingiz rad etildi.\n\U0001F4DD Sabab: {reason}")
    return {"ok": True}


@router.post("/api/desktop/listings")
async def api_desktop_create_listing(
    manzil: str = Form(...),
    narx: str = Form(...),
    telefon: str = Form(...),
    xona: str = Form(""),
    moljal: str = Form(""),
    kimlarga: str = Form(""),
    qulaylik: str = Form(""),
    rental_type: str = Form("uzoq_muddat"),
    photos: list[UploadFile] = File(...),
    user_id: int = Depends(desktop_auth_required),
):
    """Desktop dasturdan yangi e'lon - admin postlagani uchun darhol
    (navbatsiz) kanalga chiqadi, xuddi bot/flow_quick.py (Tezkor e'lon)
    kabi. Rasmlar ko'p qismli (multipart) fayllar sifatida yuboriladi."""
    manzil, narx, telefon = manzil.strip(), narx.strip(), telefon.strip()
    if not manzil or not narx or not telefon:
        raise HTTPException(status_code=400, detail="Manzil, narx va telefon majburiy.")
    phone = normalize_phone_web(telefon) or telefon

    valid_photos = [p for p in (photos or []) if p and p.filename]
    if not valid_photos:
        raise HTTPException(status_code=400, detail="Kamida bitta rasm kerak.")
    photo_bytes, photo_names = [], []
    for p in valid_photos[:10]:
        content = await p.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Har bir rasm 10MB dan oshmasligi kerak.")
        photo_bytes.append(content)
        photo_names.append(p.filename or "rasm.jpg")

    if not ADMIN_IDS or not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Tizim vaqtincha sozlanmoqda.")

    photo_bytes = watermark_photo_bytes_list(photo_bytes)
    upload_chat_id = ADMIN_IDS[0]
    try:
        file_ids = await telegram_upload_photos(upload_chat_id, photo_bytes, photo_names)
    except Exception:
        logger.exception("Desktop e'londan rasm yuklashda xatolik")
        raise HTTPException(status_code=502, detail="Rasmlarni yuklashda xatolik yuz berdi.")
    if not file_ids:
        raise HTTPException(status_code=502, detail="Rasmlarni yuklab bo'lmadi.")

    admin = get_user(user_id) or {}
    conn = db()
    cur = conn.execute(
        """INSERT INTO listings
            (user_id, username, full_name, manzil, moljal, kimlarga, xona, qulaylik, narx,
             telefon, photos, price_charged, status, category, source, rental_type, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', 'egadan', 'desktop', ?, ?)""",
        (user_id, admin.get("username"), admin.get("full_name") or "Desktop dastur", manzil, moljal,
         kimlarga, xona, qulaylik, narx, phone, _json.dumps(file_ids), rental_type, now_str()),
    )
    conn.commit()
    listing_id = cur.lastrowid
    conn.close()

    listing = get_listing(listing_id)
    message_id = await post_listing_to_channel(listing)
    posted = message_id is not None
    if posted:
        update_listing_status(listing_id, "approved", channel_msg_id=message_id)
        log_channel_post(listing_id, message_id)
    return {"ok": True, "listing_id": listing_id, "posted": posted}


# ============================= OLX RASM OLISH (tekshirilmagan) =============================

_IMG_TAG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_OG_IMAGE_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)
_NEXT_DATA_RE = re.compile(r'"(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', re.IGNORECASE)
# OLX'ning rasm CDN manzillarida odatda shu kabi so'zlar uchraydi - oddiy
# saytning o'z logotipi/ikonkalarini (ular ham <img> bo'ladi) chetlab
# o'tish uchun bir xil domendagi "haqiqiy e'lon rasmi" ehtimoli yuqori
# bo'lgan havolalarni afzal ko'rish uchun. MUHIM: "static" kabi juda
# umumiy so'zlar ATAYIN kiritilmagan - ular logotip/ikonka yo'llarida
# ham ko'p uchraydi va soxta signal berib yuboradi.
_LIKELY_CDN_HINTS = ("olxcdn", "apollo", "/files/", "photo", "image")
_EXCLUDE_HINTS = ("logo", "icon", "favicon", "sprite", "avatar", "placeholder")


@router.post("/api/desktop/olx-photos")
async def api_desktop_olx_photos(url: str = Form(...), user_id: int = Depends(desktop_auth_required)):
    """Berilgan OLX e'lon havolasidan rasm URL'larini (yuklamasdan, faqat
    manzillarini) topishga urinadi - TEKSHIRILMAGAN, chunki bu muhitdan
    olx.uz'ga tarmoq ulanishi yo'q edi. Topa olmasa - aniq xato qaytaradi,
    admin baribir rasmlarni qo'lda yuklay oladi."""
    url = (url or "").strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Noto'g'ri havola.")
    try:
        async with httpx.AsyncClient(
            timeout=20, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html_text = resp.text
    except Exception:
        logger.exception("OLX sahifasini yuklab bo'lmadi: %s", url)
        raise HTTPException(status_code=502, detail="Sahifani ochib bo'lmadi. Havolani tekshiring yoki rasmlarni qo'lda yuklang.")

    candidates: list[str] = []
    for pattern in (_IMG_TAG_RE, _OG_IMAGE_RE, _NEXT_DATA_RE):
        for match in pattern.findall(html_text):
            src = urljoin(url, match)
            if src not in candidates:
                candidates.append(src)

    def _score(src: str) -> int:
        low = src.lower()
        if any(bad in low for bad in _EXCLUDE_HINTS):
            return 0
        return sum(1 for hint in _LIKELY_CDN_HINTS if hint in low)

    candidates.sort(key=_score, reverse=True)
    photo_urls = [c for c in candidates if _score(c) > 0][:20]
    if not photo_urls:
        raise HTTPException(status_code=404, detail="Rasm topilmadi. Sahifa tuzilishi o'zgargan bo'lishi mumkin - rasmlarni qo'lda yuklang.")
    return {"ok": True, "photo_urls": photo_urls}
