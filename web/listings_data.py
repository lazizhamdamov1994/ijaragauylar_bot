"""
E'lonlarni bazadan o'qish va narx/karta sozlamalari - saytning barcha
sahifalari shu yerdagi funksiyalardan foydalanadi.
"""
import json as _json
import os
import re
from datetime import datetime, timedelta

from common.config import CARD_NUMBER, CHANNEL_USERNAME
from common.db import db, get_setting, now_str
from common.districts import TASHKENT_DISTRICTS, format_price_compact, get_aliases_for_district, parse_price_value
from web.render import RENTAL_TYPE_LABELS, photo_url

def current_subscription_price() -> int:
    try:
        return int(get_setting("subscription_price", os.getenv("SUBSCRIPTION_PRICE", "20000")))
    except (TypeError, ValueError):
        return 20000


def current_subscription_days() -> int:
    try:
        return int(get_setting("subscription_days", os.getenv("SUBSCRIPTION_DAYS", "30")))
    except (TypeError, ValueError):
        return 30



def get_active_listings():
    conn = db()
    rows = conn.execute(
        """SELECT id, manzil, moljal, kimlarga, xona, narx, latitude, longitude, created_at,
                  channel_msg_id, price_charged, category, photos
           FROM listings
           WHERE status = 'approved' AND COALESCE(expired,0) = 0
           AND latitude IS NOT NULL AND longitude IS NOT NULL
           ORDER BY (CASE WHEN COALESCE(price_charged,0) > 0 THEN 0 ELSE 1 END) ASC, created_at DESC"""
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("channel_msg_id") and CHANNEL_USERNAME:
            d["post_link"] = f"https://t.me/{CHANNEL_USERNAME}/{d['channel_msg_id']}"
        else:
            d["post_link"] = None
        try:
            photos = _json.loads(d.pop("photos") or "[]")
        except Exception:
            photos = []
        d["photo"] = photo_url(photos[0]) if photos else ""
        d["is_paid"] = bool((d.get("price_charged") or 0) > 0)
        d["detail_link"] = f"/uy/{d['id']}"
        d["narx"] = format_price_compact(d.get("narx"))
        result.append(d)
    return result


# ============================= OMMAVIY SAYT - MA'LUMOTLAR =============================

PER_PAGE = 12


def _parse_photos(row_dict):
    try:
        row_dict["photos"] = _json.loads(row_dict.get("photos") or "[]")
    except Exception:
        row_dict["photos"] = []
    return row_dict


def get_site_listings(hudud: str = "", xona: str = "", page: int = 1, rental_type: str = "", sort: str = ""):
    conn = db()
    query = "SELECT * FROM listings WHERE status='approved' AND COALESCE(expired,0)=0"
    params = []
    if hudud:
        # MUHIM: tuman tanlansa, faqat aynan shu nom EMAS, balki unga
        # bog'langan barcha kalit so'zlar (masalan "Darxon" -> Sergeli)
        # ham qidiriladi - shu orqali mahalla/mavze nomi bilan yozilgan
        # e'lonlar ham tegishli tuman filtrida chiqadi.
        keywords = get_aliases_for_district(hudud) if hudud in TASHKENT_DISTRICTS else [hudud]
        or_clauses = []
        for kw in keywords:
            or_clauses.append("manzil LIKE ?")
            params.append(f"%{kw}%")
            or_clauses.append("moljal LIKE ?")
            params.append(f"%{kw}%")
        query += " AND (" + " OR ".join(or_clauses) + ")"
    if xona:
        query += " AND xona LIKE ?"
        params.append(f"%{xona}%")
    if rental_type and rental_type in RENTAL_TYPE_LABELS:
        query += " AND COALESCE(rental_type,'uzoq_muddat') = ?"
        params.append(rental_type)
    if sort in ("yangi", "arzon", "qimmat"):
        # "Eng yangi"/"Eng arzon"/"Eng qimmat" - foydalanuvchi ANIQ shu
        # mezon bo'yicha tartiblanishini kutadi, shuning uchun "TOP"
        # pullik e'lonlarni yuqoriga surish (pinning) qo'llanilmaydi -
        # narx/vaqt bo'yicha saralash pastda (Python'da, narx uchun) yoki
        # shu yerda (vaqt uchun) to'g'ridan-to'g'ri qo'llanadi.
        query += " ORDER BY created_at DESC"
    else:
        # "Tanlangan" (standart) - pullik ("TOP") e'lonlar — egasi
        # «topshirildi» deb belgilamaguncha — ro'yxat boshida turadi
        # (botdagi kanalga qayta-joylash mantig'i bilan bir xil).
        query += " ORDER BY (CASE WHEN COALESCE(price_charged,0) > 0 THEN 0 ELSE 1 END) ASC, created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    listings = [_parse_photos(dict(r)) for r in rows]

    if sort in ("arzon", "qimmat"):
        try:
            usd_rate = int(get_setting("usd_to_som_rate", "12700"))
        except (TypeError, ValueError):
            usd_rate = 12700
        reverse = sort == "qimmat"
        for l in listings:
            l["_price_value"] = parse_price_value(l.get("narx"), usd_rate)
        priced = [l for l in listings if l["_price_value"] is not None]
        unpriced = [l for l in listings if l["_price_value"] is None]
        priced.sort(key=lambda l: l["_price_value"], reverse=reverse)
        listings = priced + unpriced
        for l in listings:
            l.pop("_price_value", None)

    total = len(listings)
    start = (page - 1) * PER_PAGE
    return listings[start:start + PER_PAGE], total


def get_site_listing(listing_id: int):
    conn = db()
    row = conn.execute(
        "SELECT * FROM listings WHERE id = ? AND status='approved' AND COALESCE(expired,0)=0", (listing_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _parse_photos(dict(row))


def get_related_listings(listing_id: int, hudud_hint: str, limit: int = 3):
    conn = db()
    rows = conn.execute(
        """SELECT id, manzil, moljal, xona, narx, photos, price_charged, rental_type, kimlarga, is_quick FROM listings
           WHERE status='approved' AND COALESCE(expired,0)=0 AND id != ?
           AND (manzil LIKE ? OR moljal LIKE ?)
           ORDER BY (CASE WHEN COALESCE(price_charged,0) > 0 THEN 0 ELSE 1 END) ASC, created_at DESC LIMIT ?""",
        (listing_id, f"%{hudud_hint[:15]}%", f"%{hudud_hint[:15]}%", limit),
    ).fetchall()
    conn.close()
    return [_parse_photos(dict(r)) for r in rows]


def site_stats_summary():
    conn = db()
    active = conn.execute("SELECT COUNT(*) c FROM listings WHERE status='approved' AND COALESCE(expired,0)=0").fetchone()["c"]
    users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    conn.close()
    return {"active": active, "users": users}



def current_listing_price() -> int:
    try:
        return int(get_setting("listing_price", "20000"))
    except (TypeError, ValueError):
        return 20000


def current_card_number() -> str:
    return get_setting("card_number", CARD_NUMBER)


def normalize_phone_web(raw: str):
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("998") and len(digits) == 12:
        pass
    elif len(digits) == 9:
        digits = "998" + digits
    else:
        return None
    if not re.fullmatch(r"998\d{9}", digits):
        return None
    return "+" + digits


def web_submissions_today(ip: str) -> int:
    since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM web_listing_submissions WHERE ip = ? AND created_at >= ?", (ip, since)
    ).fetchone()["c"]
    conn.close()
    return n


def record_web_submission(ip: str) -> None:
    conn = db()
    conn.execute("INSERT INTO web_listing_submissions (ip, created_at) VALUES (?, ?)", (ip, now_str()))
    conn.commit()
    conn.close()



