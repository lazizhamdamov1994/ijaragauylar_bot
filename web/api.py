"""
Sayt/admin panel ishlatadigan kichik JSON API endpointlari (statistika,
so'rovlar ro'yxati, kuzatuv).
"""
import html
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta

import csv
import io

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from common.config import ADMIN_IDS, BOT_TOKEN, BOT_USERNAME, CHANNEL_ID, CHANNEL_USERNAME
from common.db import (
    ai_accuracy_summary,
    broadcast_notification,
    create_support_request,
    db,
    get_blocked_phone,
    get_district_price_history,
    get_pending_support_requests,
    get_usd_rate_history,
    get_setting,
    is_subscribed,
    now_str,
    reply_support_request,
    set_setting,
    toggle_favorite,
)

from common.districts import add_district_alias, list_district_aliases, remove_district_alias
from common.ai import ai_features_enabled, ai_usage_summary
from common.ai_agent import concierge_rate_limited, concierge_turn

from web.auth import check_auth, get_current_tg_user
from web.listings_data import get_active_listings, normalize_phone_web, post_listing_to_channel
from web.pages import notify_telegram
from web.render import TASHKENT_DISTRICTS

# MUHIM: quyidagilar bot/ paketidan import qilinadi - odatda web/ hech qachon
# bot/'dan import qilmaydi (ikkalasi alohida-alohida ishga tushadigan
# jarayonlar), lekin bu funksiyalar TOZA (faqat sqlite o'qish/yozish yoki matn
# formatlash, import vaqtida yon ta'sir yo'q) va nozik formatlash/xavf-baholash
# mantiqini o'z ichiga oladi - shuning uchun ikkinchi nusxa yaratib, vaqt
# o'tishi bilan bot bilan mos kelmay qolish xavfini tug'dirish o'rniga,
# BITTA manbadan qayta ishlatiladi (admin panel botdagi barcha imkoniyatlarni
# veb orqali ham berishi kerak - shu jumladan kanalga post qilish).
from bot.admin_moderation import log_channel_post
from bot.constants import SETTINGS_FIELDS
from bot.db import (
    active_subscribers_page,
    approve_subscription,
    block_phone,
    cancel_subscription,
    count_active_subscribers,
    count_new_users_in_period,
    get_active_subscription_id,
    get_listing,
    get_pending_listings,
    get_pending_subscriptions,
    get_subscription,
    get_user,
    list_blocked_phones_page,
    log_ai_feedback,
    reject_subscription,
    stats_for_period,
    unblock_phone,
    update_listing_status,
)
from bot.fraud_detection import (
    ban_user,
    compute_risk_score,
    count_listings_by_user,
    count_reports_made,
    count_reports_received,
    get_flagged_users,
    get_period_bounds,
    is_banned,
    unban_user,
)
from bot.helpers import (
    add_extra_admin,
    add_moderator,
    remove_extra_admin,
    remove_moderator,
    set_moderator_super,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================= AI CHAT (OMMAVIY, parolsiz - saytdagi suzuvchi vidjet) =============================
# Suhbat tarixi SERVER tomonida (jarayon xotirasida) saqlanadi - brauzer
# faqat tasodifiy session_id (localStorage) yuboradi. Sabab: Claude SDK
# javob obyektlari (tool_use bloklari) to'g'ridan-to'g'ri JSON-seriyalash
# mumkin emas - shuning uchun ular hech qachon brauzerga yuborilmaydi,
# faqat matnli javob (reply) yuboriladi. common/ai_agent.py - bot
# Concierge bilan BIR XIL mantiq.
_web_chat_sessions: dict = {}
_WEB_CHAT_MAX_SESSIONS = 500


@router.post("/api/ai-chat")
async def api_ai_chat(request: Request):
    data = await request.json()
    session_id = str(data.get("session_id") or "").strip()[:80]
    message = str(data.get("message") or "").strip()
    if not session_id or not message:
        raise HTTPException(status_code=400, detail="invalid_request")
    if len(message) > 500:
        raise HTTPException(status_code=400, detail="message_too_long")

    if not ai_features_enabled():
        return {"reply": None, "disabled": True}
    if concierge_rate_limited(session_id, "web"):
        return {"reply": None, "rate_limited": True}

    history = _web_chat_sessions.get(session_id, [])
    reply, new_history = await concierge_turn(session_id, "web", history, message)
    if reply is None:
        return {"reply": None}

    _web_chat_sessions[session_id] = new_history
    if len(_web_chat_sessions) > _WEB_CHAT_MAX_SESSIONS:
        _web_chat_sessions.pop(next(iter(_web_chat_sessions)), None)
    return {"reply": reply}


@router.get("/api/listing-inquiries")
def get_listing_inquiries(user: str = Depends(check_auth)):
    conn = db()
    rows = conn.execute(
        """SELECT li.*, l.manzil as listing_manzil FROM listing_inquiries li
           LEFT JOIN listings l ON l.id = li.listing_id ORDER BY li.id DESC LIMIT 50"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/api/listing-inquiries/{inquiry_id}")
def update_listing_inquiry(inquiry_id: int, status: str = Query(...), user: str = Depends(check_auth)):
    if status not in ("yangi", "yopiq"):
        raise HTTPException(status_code=400)
    conn = db()
    conn.execute("UPDATE listing_inquiries SET status = ? WHERE id = ?", (status, inquiry_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/api/listing-inquiries/{inquiry_id}/delete")
def delete_listing_inquiry(inquiry_id: int, user: str = Depends(check_auth)):
    conn = db()
    conn.execute("DELETE FROM listing_inquiries WHERE id = ?", (inquiry_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/api/subarenda-lead")
async def submit_subarenda_lead(request: Request):
    data = await request.json()
    full_name = (data.get("full_name") or "").strip()[:100]
    phone = (data.get("phone") or "").strip()[:30]
    manzil = (data.get("manzil") or "").strip()[:200]
    xona = (data.get("xona") or "").strip()[:50]
    narx_talab = (data.get("narx_talab") or "").strip()[:50]
    if not full_name or not phone or not manzil:
        raise HTTPException(status_code=400, detail="Majburiy maydonlar to'ldirilmagan")
    # Kirgan foydalanuvchi bo'lsa, so'rov uning kabinetidagi "Mening
    # so'rovlarim"da ko'rinishi uchun user_id yozib qo'yiladi.
    tg_user = get_current_tg_user(request)
    sender_uid = tg_user["uid"] if tg_user else None
    conn = db()
    conn.execute(
        "INSERT INTO subarenda_requests (user_id, full_name, phone, manzil, xona, narx_talab, status, created_at) VALUES (?,?,?,?,?,?,'yangi',?)",
        (sender_uid, full_name, phone, manzil, xona, narx_talab, now_str()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/api/subarenda-requests")
def get_subarenda_requests(user: str = Depends(check_auth)):
    conn = db()
    rows = conn.execute("SELECT * FROM subarenda_requests ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/api/subarenda-requests/{req_id}")
def update_subarenda_request(req_id: int, status: str = Query(...), user: str = Depends(check_auth)):
    if status not in ("yangi", "bogl", "yopiq"):
        raise HTTPException(status_code=400)
    conn = db()
    conn.execute("UPDATE subarenda_requests SET status = ? WHERE id = ?", (status, req_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/api/subarenda-requests/{req_id}/delete")
def delete_subarenda_request(req_id: int, user: str = Depends(check_auth)):
    conn = db()
    conn.execute("DELETE FROM subarenda_requests WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/api/listings")
def api_listings(user: str = Depends(check_auth)):
    return get_active_listings()


# ============================= API: XARITA (OMMAVIY, parolsiz) =============================

@router.get("/api/public-listings")
def api_public_listings():
    return get_active_listings()


@router.post("/api/track-view")
def track_view():
    """Xarita sahifasi ochilganda chaqiriladi - umumiy ko'rishlar sonini kuzatish uchun."""
    conn = db()
    conn.execute("INSERT INTO map_views (viewed_at) VALUES (?)", (now_str(),))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/api/track-click/{listing_id}")
def track_click(listing_id: int):
    """Xaritadan \"Kanaldagi postni ko'rish\" tugmasi bosilganda chaqiriladi."""
    conn = db()
    conn.execute("INSERT INTO map_clicks (listing_id, clicked_at) VALUES (?, ?)", (listing_id, now_str()))
    conn.commit()
    conn.close()
    return {"ok": True}


# ============================= API: TO'LIQ STATISTIKA (faqat admin) =============================

@router.get("/api/stats")
def api_stats(user: str = Depends(check_auth)):
    conn = db()
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # ---- Asosiy KPI ko'rsatkichlari ----
    total_users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    new_users_today = conn.execute("SELECT COUNT(*) c FROM users WHERE created_at >= ?", (today,)).fetchone()["c"]
    new_users_week = conn.execute("SELECT COUNT(*) c FROM users WHERE created_at >= ?", (week_ago,)).fetchone()["c"]
    new_users_prev_week = conn.execute(
        "SELECT COUNT(*) c FROM users WHERE created_at >= ? AND created_at < ?",
        ((datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d"), week_ago),
    ).fetchone()["c"]

    active_listings = conn.execute(
        "SELECT COUNT(*) c FROM listings WHERE status='approved' AND COALESCE(expired,0)=0"
    ).fetchone()["c"]
    pending_listings = conn.execute("SELECT COUNT(*) c FROM listings WHERE status='pending'").fetchone()["c"]
    listings_with_location = conn.execute("SELECT COUNT(*) c FROM listings WHERE latitude IS NOT NULL").fetchone()["c"]

    active_subs = conn.execute(
        "SELECT COUNT(*) c FROM subscriptions WHERE status='approved' AND expire_at > ?", (now_str(),)
    ).fetchone()["c"]

    revenue_month = conn.execute(
        "SELECT COALESCE(SUM(price_charged),0) s FROM listings WHERE created_at >= ? AND status='approved'", (month_ago,)
    ).fetchone()["s"]
    revenue_prev_month = conn.execute(
        "SELECT COALESCE(SUM(price_charged),0) s FROM listings WHERE created_at >= ? AND created_at < ? AND status='approved'",
        ((datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d"), month_ago),
    ).fetchone()["s"]
    revenue_subs_month = conn.execute(
        "SELECT COALESCE(SUM(price_charged),0) s FROM subscriptions WHERE created_at >= ? AND status='approved'", (month_ago,)
    ).fetchone()["s"]
    revenue_subs_prev_month = conn.execute(
        "SELECT COALESCE(SUM(price_charged),0) s FROM subscriptions WHERE created_at >= ? AND created_at < ? AND status='approved'",
        ((datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d"), month_ago),
    ).fetchone()["s"]

    # ---- 30 kunlik kunlik grafik: elonlar + daromad ----
    daily_listings = []
    daily_revenue = []
    for i in range(29, -1, -1):
        day_start = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        day_end = (datetime.now() - timedelta(days=i - 1)).strftime("%Y-%m-%d")
        cnt = conn.execute(
            "SELECT COUNT(*) c FROM listings WHERE created_at >= ? AND created_at < ?", (day_start, day_end)
        ).fetchone()["c"]
        rev_l = conn.execute(
            "SELECT COALESCE(SUM(price_charged),0) s FROM listings WHERE created_at >= ? AND created_at < ? AND status='approved'",
            (day_start, day_end),
        ).fetchone()["s"]
        rev_s = conn.execute(
            "SELECT COALESCE(SUM(price_charged),0) s FROM subscriptions WHERE created_at >= ? AND created_at < ? AND status='approved'",
            (day_start, day_end),
        ).fetchone()["s"]
        label = day_start[5:]
        daily_listings.append({"date": label, "count": cnt})
        daily_revenue.append({"date": label, "listings": rev_l, "subs": rev_s, "total": rev_l + rev_s})

    # ---- 6 oylik daromad tendensiyasi ----
    monthly_revenue = []
    for i in range(5, -1, -1):
        m_start = (datetime.now().replace(day=1) - timedelta(days=i * 30)).strftime("%Y-%m")
        m_dt = datetime.strptime(m_start, "%Y-%m")
        next_m = (m_dt.replace(day=28) + timedelta(days=4)).replace(day=1)
        rev_l = conn.execute(
            "SELECT COALESCE(SUM(price_charged),0) s FROM listings WHERE created_at >= ? AND created_at < ? AND status='approved'",
            (m_dt.strftime("%Y-%m-%d"), next_m.strftime("%Y-%m-%d")),
        ).fetchone()["s"]
        rev_s = conn.execute(
            "SELECT COALESCE(SUM(price_charged),0) s FROM subscriptions WHERE created_at >= ? AND created_at < ? AND status='approved'",
            (m_dt.strftime("%Y-%m-%d"), next_m.strftime("%Y-%m-%d")),
        ).fetchone()["s"]
        monthly_revenue.append({"month": m_dt.strftime("%b"), "listings": rev_l, "subs": rev_s, "total": rev_l + rev_s})

    # ---- Obuna (Limit) o'sish grafigi - 30 kunlik ----
    daily_subs = []
    for i in range(29, -1, -1):
        day_start = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        day_end = (datetime.now() - timedelta(days=i - 1)).strftime("%Y-%m-%d")
        cnt = conn.execute(
            "SELECT COUNT(*) c FROM subscriptions WHERE created_at >= ? AND created_at < ? AND status='approved'",
            (day_start, day_end),
        ).fetchone()["c"]
        daily_subs.append({"date": day_start[5:], "count": cnt})

    # ---- Xarita: umumiy ko'rishlar va bosishlar ----
    total_map_views = conn.execute("SELECT COUNT(*) c FROM map_views").fetchone()["c"]
    map_views_month = conn.execute("SELECT COUNT(*) c FROM map_views WHERE viewed_at >= ?", (month_ago,)).fetchone()["c"]
    total_map_clicks = conn.execute("SELECT COUNT(*) c FROM map_clicks").fetchone()["c"]
    map_clicks_month = conn.execute("SELECT COUNT(*) c FROM map_clicks WHERE clicked_at >= ?", (month_ago,)).fetchone()["c"]

    top_clicked = conn.execute(
        """SELECT l.id, l.manzil, l.narx, COUNT(mc.id) as clicks
           FROM map_clicks mc JOIN listings l ON l.id = mc.listing_id
           GROUP BY mc.listing_id ORDER BY clicks DESC LIMIT 5"""
    ).fetchall()
    top_clicked_list = [dict(r) for r in top_clicked]

    conversion_rate = round((total_map_clicks / total_map_views * 100), 1) if total_map_views else 0

    total_visits = conn.execute("SELECT COUNT(*) c FROM site_visits").fetchone()["c"]
    visits_today = conn.execute("SELECT COUNT(*) c FROM site_visits WHERE visited_at >= ?", (today,)).fetchone()["c"]
    visits_week = conn.execute("SELECT COUNT(*) c FROM site_visits WHERE visited_at >= ?", (week_ago,)).fetchone()["c"]
    unique_visitors_week = conn.execute("SELECT COUNT(DISTINCT ip) c FROM site_visits WHERE visited_at >= ?", (week_ago,)).fetchone()["c"]

    daily_visits = []
    for i in range(13, -1, -1):
        day_start = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        day_end = (datetime.now() - timedelta(days=i - 1)).strftime("%Y-%m-%d")
        cnt = conn.execute("SELECT COUNT(*) c FROM site_visits WHERE visited_at >= ? AND visited_at < ?", (day_start, day_end)).fetchone()["c"]
        daily_visits.append({"date": day_start[5:], "count": cnt})

    device_breakdown = conn.execute("SELECT device, COUNT(*) c FROM site_visits WHERE visited_at >= ? GROUP BY device ORDER BY c DESC", (week_ago,)).fetchall()
    country_breakdown = conn.execute("SELECT country, COUNT(*) c FROM site_visits WHERE visited_at >= ? GROUP BY country ORDER BY c DESC LIMIT 8", (week_ago,)).fetchall()
    top_pages = conn.execute("SELECT path, COUNT(*) c FROM site_visits WHERE visited_at >= ? GROUP BY path ORDER BY c DESC LIMIT 8", (week_ago,)).fetchall()
    recent_visits = conn.execute("SELECT path, ip, country, city, device, browser, visited_at FROM site_visits ORDER BY id DESC LIMIT 30").fetchall()

    pending_subarenda = conn.execute("SELECT COUNT(*) c FROM subarenda_requests WHERE status='yangi'").fetchone()["c"]

    # ---- Chuqurroq tahlil: ijara turi, tuman va toifa bo'yicha taqsimot (faol e'lonlar) ----
    rt_rows = conn.execute(
        "SELECT COALESCE(rental_type,'uzoq_muddat') rt, COUNT(*) c FROM listings "
        "WHERE status='approved' AND COALESCE(expired,0)=0 GROUP BY rt ORDER BY c DESC"
    ).fetchall()
    rt_label_map = {"uzoq_muddat": "\U0001F3E0 Uzoq muddat", "kunlik": "\U0001F4C5 Kunlik", "dacha": "\U0001F333 Dacha", "mehmonxona": "\U0001F6CF Mehmonxona"}
    rental_type_breakdown = [{"label": rt_label_map.get(r["rt"], r["rt"]), "c": r["c"]} for r in rt_rows]

    cat_rows = conn.execute(
        "SELECT COALESCE(category,'egadan') cat, COUNT(*) c FROM listings "
        "WHERE status='approved' AND COALESCE(expired,0)=0 GROUP BY cat ORDER BY c DESC"
    ).fetchall()
    cat_label_map = {"egadan": "Egasidan", "tasdiqlangan": "✅ Tasdiqlangan", "subarenda": "\U0001F3E2 Subarenda", "premium": "\U0001F48E Premium"}
    category_breakdown = [{"label": cat_label_map.get(r["cat"], r["cat"]), "c": r["c"]} for r in cat_rows]

    active_rows = conn.execute(
        "SELECT manzil FROM listings WHERE status='approved' AND COALESCE(expired,0)=0 AND manzil IS NOT NULL AND manzil != ''"
    ).fetchall()
    district_counts = {}
    for r in active_rows:
        low = (r["manzil"] or "").lower()
        for d in TASHKENT_DISTRICTS:
            if d.lower() in low:
                district_counts[d] = district_counts.get(d, 0) + 1
                break
    district_breakdown = [{"label": k, "c": v} for k, v in sorted(district_counts.items(), key=lambda x: -x[1])[:8]]

    web_vs_bot = conn.execute(
        "SELECT COALESCE(source,'bot') src, COUNT(*) c FROM listings "
        "WHERE created_at >= ? GROUP BY src", (month_ago,)
    ).fetchall()
    source_breakdown = {r["src"]: r["c"] for r in web_vs_bot}

    conn.close()

    return {
        "total_users": total_users,
        "new_users_today": new_users_today,
        "new_users_week": new_users_week,
        "new_users_week_change": pct_change(new_users_prev_week, new_users_week),
        "active_listings": active_listings,
        "pending_listings": pending_listings,
        "listings_with_location": listings_with_location,
        "active_subscribers": active_subs,
        "revenue_month_listings": revenue_month,
        "revenue_month_listings_change": pct_change(revenue_prev_month, revenue_month),
        "revenue_month_subs": revenue_subs_month,
        "revenue_month_subs_change": pct_change(revenue_subs_prev_month, revenue_subs_month),
        "revenue_month_total": revenue_month + revenue_subs_month,
        "daily_listings": daily_listings,
        "daily_revenue": daily_revenue,
        "daily_subs": daily_subs,
        "monthly_revenue": monthly_revenue,
        "pending_subarenda": pending_subarenda,
        "rental_type_breakdown": rental_type_breakdown,
        "category_breakdown": category_breakdown,
        "district_breakdown": district_breakdown,
        "source_breakdown": {"bot": source_breakdown.get("bot", 0), "web": source_breakdown.get("web", 0)},
        "map_stats": {
            "total_views": total_map_views,
            "views_month": map_views_month,
            "total_clicks": total_map_clicks,
            "clicks_month": map_clicks_month,
            "conversion_rate": conversion_rate,
            "top_clicked": top_clicked_list,
        },
        "visit_stats": {
            "total": total_visits, "today": visits_today, "week": visits_week, "unique_week": unique_visitors_week,
            "daily": daily_visits,
            "devices": [dict(r) for r in device_breakdown],
            "countries": [dict(r) for r in country_breakdown],
            "top_pages": [dict(r) for r in top_pages],
            "recent": [dict(r) for r in recent_visits],
        },
    }


def pct_change(old, new):
    if not old:
        return None if not new else 100.0
    return round(((new - old) / old) * 100, 1)


@router.get("/api/admin/period-stats")
def api_admin_period_stats(period: str = Query("daily"), user: str = Depends(check_auth)):
    """Kunlik/haftalik/oylik/yillik statistika - bot ichidagi "Statistika"
    tugmasi (bot/menu.py:show_stats, bot/fraud_detection.py:render_period_stats)
    bilan BIR XIL davr hisoblash mantig'i (get_period_bounds/stats_for_period),
    faqat web admin panelda kartochkalar shaklida."""
    if period not in ("daily", "weekly", "monthly", "yearly"):
        raise HTTPException(status_code=400, detail="invalid_period")
    start, end, prev_start, prev_end, label, prev_label = get_period_bounds(period)
    current = stats_for_period(start, end)
    previous = stats_for_period(prev_start, prev_end)
    new_users = count_new_users_in_period(start, end)
    new_users_prev = count_new_users_in_period(prev_start, prev_end)
    return {
        "label": label,
        "prev_label": prev_label,
        "new_users": new_users,
        "new_users_prev": new_users_prev,
        "current": current,
        "previous": previous,
    }


@router.get("/api/moderator-stats")
def api_moderator_stats(user: str = Depends(check_auth)):
    """Admin uchun - HAR BIR moderator qancha e'lon joylagani, nechtasi
    tasdiqlangani/rad etilgani. Bot ichida moderator faqat O'ZINING
    natijasini ko'radi - bu yerda esa admin BARCHASINI bir joyda ko'radi."""
    conn = db()
    mods = conn.execute(
        """SELECT m.user_id, m.added_at, m.is_super, u.username, u.full_name
           FROM moderators m LEFT JOIN users u ON u.user_id = m.user_id
           ORDER BY m.added_at DESC"""
    ).fetchall()
    result = []
    for m in mods:
        uid = m["user_id"]
        total = conn.execute("SELECT COUNT(*) c FROM listings WHERE user_id = ?", (uid,)).fetchone()["c"]
        approved = conn.execute("SELECT COUNT(*) c FROM listings WHERE user_id = ? AND status='approved'", (uid,)).fetchone()["c"]
        rejected = conn.execute("SELECT COUNT(*) c FROM listings WHERE user_id = ? AND status='rejected'", (uid,)).fetchone()["c"]
        last = conn.execute("SELECT created_at FROM listings WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (uid,)).fetchone()
        result.append({
            "user_id": uid,
            "username": m["username"],
            "full_name": m["full_name"] or f"ID:{uid}",
            "added_at": m["added_at"],
            "is_super": bool(m["is_super"]),
            "total": total, "approved": approved, "rejected": rejected,
            "last_activity": last["created_at"] if last else None,
        })
    conn.close()
    return result


# ============================= SEVIMLILAR (faqat Telegram orqali kirgan foydalanuvchi) =============================

@router.post("/api/favorites/toggle")
async def api_toggle_favorite(request: Request):
    tg_user = get_current_tg_user(request)
    if not tg_user:
        raise HTTPException(status_code=401, detail="login_required")
    data = await request.json()
    try:
        listing_id = int(data.get("listing_id") or 0)
    except (TypeError, ValueError):
        listing_id = 0
    if not listing_id:
        raise HTTPException(status_code=400)
    favorited = toggle_favorite(tg_user["uid"], listing_id)
    return {"ok": True, "favorited": favorited}


# ============================= RAQAM TEKSHIRISH (ommaviy, saytda) =============================

@router.get("/api/phone-check")
def api_phone_check(phone: str = Query("")):
    normalized = normalize_phone_web(phone)
    if not normalized:
        raise HTTPException(status_code=400, detail="invalid_phone")
    blocked = get_blocked_phone(normalized)
    return {"blocked": blocked is not None, "reason": (blocked.get("reason") if blocked else None)}


# ============================= QO'LLAB-QUVVATLASH SO'ROVI (shaxsiy kabinetdan) =============================

async def _notify_admins_new_support_request(req_id: int, tg_user: dict, message: str) -> None:
    """Adminlarga Telegram orqali darhol xabar beradi - alohida admin
    veb-sahifasi hali yo'q, botni faol ishlatishadi, shuning uchun
    eng tez YETIB BORADIGAN kanal shu."""
    if not BOT_TOKEN or not ADMIN_IDS:
        return
    uname = f"@{tg_user['un']}" if tg_user.get("un") else f"ID:{tg_user['uid']}"
    text = (
        f"\U0001F4AC <b>Yangi so'rov (sayt, Shaxsiy kabinet)</b>\n\n"
        f"\U0001F464 {tg_user.get('fn') or uname} ({uname})\n\n"
        f"{message}\n\n"
        f"Javob berish uchun bot admin panelidagi “So'rovlar” bo'limidan foydalaning (#{req_id})."
    )
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            for admin_id in ADMIN_IDS:
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": admin_id, "text": text, "parse_mode": "HTML"})
    except Exception:
        logger.exception("Adminlarga yangi so'rov haqida xabar berishda xatolik")


@router.post("/api/kabinet/support")
async def api_submit_support_request(request: Request):
    tg_user = get_current_tg_user(request)
    if not tg_user:
        raise HTTPException(status_code=401, detail="login_required")
    data = await request.json()
    message = (data.get("message") or "").strip()[:1000]
    if not message:
        raise HTTPException(status_code=400, detail="empty_message")
    req_id = create_support_request(tg_user["uid"], tg_user.get("un"), tg_user.get("fn"), message)
    await _notify_admins_new_support_request(req_id, tg_user, message)
    return {"ok": True}


# ============================= ADMIN: KUTILMOQDA (E'LON / OBUNA SO'ROVLARI) =============================
# Botdagi bilan bir xil oqim (approve_listing/approve_sub/admin_reject_reason,
# bot/admin_moderation.py) - lekin python-telegram-bot Application contextisiz,
# to'g'ridan-to'g'ri Telegram Bot API orqali (xuddi web/pages.py'dagi
# notify_admins_new_web_listing kabi). Haqiqiy kanalga-joylash funksiyasi
# (post_listing_to_channel) endi web/listings_data.py'da - AI avtomatik
# tasdiqlash (web/pages.py) bilan BIR XIL funksiyani ishlatadi.


@router.get("/api/admin/pending")
def api_admin_pending(user: str = Depends(check_auth)):
    listings = get_pending_listings(limit=100)
    subs = get_pending_subscriptions(limit=100)
    if subs:
        conn = db()
        ids = tuple({s["user_id"] for s in subs})
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(f"SELECT user_id, username, full_name FROM users WHERE user_id IN ({placeholders})", ids).fetchall()
        conn.close()
        by_id = {r["user_id"]: dict(r) for r in rows}
        for s in subs:
            u = by_id.get(s["user_id"]) or {}
            s["username"] = u.get("username")
            s["full_name"] = u.get("full_name")
    return {"listings": listings, "subscriptions": subs}


@router.post("/api/admin/pending/listing/{listing_id}/approve")
async def api_admin_approve_listing(listing_id: int, user: str = Depends(check_auth)):
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


@router.post("/api/admin/pending/listing/{listing_id}/reject")
async def api_admin_reject_listing(listing_id: int, reason: str = Query(...), user: str = Depends(check_auth)):
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
    await notify_telegram(listing["user_id"], f"❌ Sizning e'loningiz (#{listing_id}) rad etildi.\n\U0001F4DD Sabab: {html.escape(reason)}")
    return {"ok": True}


@router.post("/api/admin/pending/subscription/{sub_id}/approve")
async def api_admin_approve_subscription(sub_id: int, user: str = Depends(check_auth)):
    sub = get_subscription(sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="not_found")
    if sub["status"] != "pending":
        raise HTTPException(status_code=409, detail="already_reviewed")
    target_user_id, expire = approve_subscription(sub_id)
    await notify_telegram(target_user_id, f"✅ Limitingiz faollashtirildi!\nMuddati: <b>{expire[:10]}</b> gacha.")
    return {"ok": True, "expire_at": expire}


@router.post("/api/admin/pending/subscription/{sub_id}/reject")
async def api_admin_reject_subscription(sub_id: int, reason: str = Query(...), user: str = Depends(check_auth)):
    sub = get_subscription(sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="not_found")
    if sub["status"] != "pending":
        raise HTTPException(status_code=409, detail="already_reviewed")
    reason = reason.strip()[:500]
    if not reason:
        raise HTTPException(status_code=400, detail="empty_reason")
    reject_subscription(sub_id, reason)
    await notify_telegram(sub["user_id"], f"❌ Obuna so'rovingiz rad etildi.\n\U0001F4DD Sabab: {html.escape(reason)}")
    return {"ok": True}


# ============================= ADMIN: OBUNACHILAR (Limit) =============================

@router.get("/api/admin/subscribers")
def api_admin_subscribers(user: str = Depends(check_auth)):
    return active_subscribers_page(0, limit=1000)


@router.post("/api/admin/subscribers/{sub_id}/cancel")
async def api_admin_cancel_subscriber(sub_id: int, user: str = Depends(check_auth)):
    target_user_id = cancel_subscription(sub_id)
    if not target_user_id:
        raise HTTPException(status_code=404, detail="not_found")
    await notify_telegram(target_user_id, "❌ Sizning obunangiz administrator tomonidan muddatidan oldin bekor qilindi.")
    return {"ok": True}


# ============================= ADMIN: MODERATOR / ADMIN BOSHQARUVI =============================

@router.get("/api/admin/extra-admins")
def api_admin_extra_admins(user: str = Depends(check_auth)):
    conn = db()
    rows = conn.execute(
        """SELECT a.user_id, a.added_at, u.username, u.full_name
           FROM extra_admins a LEFT JOIN users u ON u.user_id = a.user_id
           ORDER BY a.added_at DESC"""
    ).fetchall()
    conn.close()
    return [{"user_id": r["user_id"], "username": r["username"], "full_name": r["full_name"] or f"ID:{r['user_id']}", "added_at": r["added_at"]} for r in rows]


@router.post("/api/admin/moderators/add")
def api_admin_add_moderator(target_user_id: int = Query(...), user: str = Depends(check_auth)):
    add_moderator(target_user_id, 0)
    return {"ok": True}


@router.post("/api/admin/moderators/{mod_user_id}/remove")
def api_admin_remove_moderator(mod_user_id: int, user: str = Depends(check_auth)):
    remove_moderator(mod_user_id)
    return {"ok": True}


@router.post("/api/admin/moderators/{mod_user_id}/set-super")
def api_admin_set_moderator_super(mod_user_id: int, is_super: bool = Query(...), user: str = Depends(check_auth)):
    set_moderator_super(mod_user_id, is_super)
    return {"ok": True}


# ============================= ADMIN: TUMAN KALIT SO'ZLARI =============================
# Mahalla/mavze/mashxur joy nomlarini ("Darxon" -> Sergeli) tumanlarga
# biriktirish - "Tezkor e'lon" (bot) va tuman filtri (sayt) shu ro'yxatdan
# foydalanadi. Bot tomonida ham bir xil funksiyalar (common/districts.py)
# ishlatiladi - IKKALA joy ham BITTA manbadan o'qiydi/yozadi.

@router.get("/api/admin/district-aliases")
def api_admin_district_aliases(user: str = Depends(check_auth)):
    return {"districts": TASHKENT_DISTRICTS, "aliases": list_district_aliases()}


@router.post("/api/admin/district-aliases/add")
def api_admin_add_district_alias(district: str = Query(...), alias: str = Query(...), user: str = Depends(check_auth)):
    if district not in TASHKENT_DISTRICTS:
        raise HTTPException(status_code=400, detail="noto'g'ri tuman")
    added_any = False
    for kw in alias.split(","):
        if add_district_alias(kw, district):
            added_any = True
    return {"ok": True, "added": added_any}


@router.post("/api/admin/district-aliases/{alias_id}/remove")
def api_admin_remove_district_alias(alias_id: int, user: str = Depends(check_auth)):
    remove_district_alias(alias_id)
    return {"ok": True}


@router.post("/api/admin/extra-admins/add")
def api_admin_add_extra_admin(target_user_id: int = Query(...), user: str = Depends(check_auth)):
    add_extra_admin(target_user_id, 0)
    return {"ok": True}


@router.post("/api/admin/extra-admins/{admin_user_id}/remove")
def api_admin_remove_extra_admin(admin_user_id: int, user: str = Depends(check_auth)):
    if admin_user_id in ADMIN_IDS:
        raise HTTPException(status_code=400, detail="cannot_remove_env_admin")
    remove_extra_admin(admin_user_id)
    return {"ok": True}


# ============================= ADMIN: BLOKLANGAN RAQAMLAR =============================

@router.get("/api/admin/blocked-phones")
def api_admin_blocked_phones(user: str = Depends(check_auth)):
    return list_blocked_phones_page(0, limit=1000)


@router.post("/api/admin/blocked-phones/add")
def api_admin_block_phone(phone: str = Query(...), reason: str = Query(...), user: str = Depends(check_auth)):
    normalized = normalize_phone_web(phone)
    if not normalized:
        raise HTTPException(status_code=400, detail="invalid_phone")
    reason = reason.strip()[:300]
    if not reason:
        raise HTTPException(status_code=400, detail="empty_reason")
    block_phone(normalized, reason, 0)
    return {"ok": True}


@router.post("/api/admin/blocked-phones/{phone}/unblock")
def api_admin_unblock_phone(phone: str, user: str = Depends(check_auth)):
    unblock_phone(phone)
    return {"ok": True}


# ============================= ADMIN: XAVFLI FOYDALANUVCHILAR / FOYDALANUVCHI KARTASI =============================

@router.get("/api/admin/flagged-users")
def api_admin_flagged_users(user: str = Depends(check_auth)):
    flagged = get_flagged_users()
    if not flagged:
        return []
    conn = db()
    ids = tuple({f["user_id"] for f in flagged})
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT user_id, username, full_name FROM users WHERE user_id IN ({placeholders})", ids).fetchall()
    conn.close()
    by_id = {r["user_id"]: dict(r) for r in rows}
    result = []
    for f in flagged:
        u = by_id.get(f["user_id"]) or {}
        result.append({**f, "username": u.get("username"), "full_name": u.get("full_name") or f"ID:{f['user_id']}"})
    return result


@router.get("/api/admin/user-card/{target_user_id}")
def api_admin_user_card(target_user_id: int, user: str = Depends(check_auth)):
    u = get_user(target_user_id)
    if not u:
        raise HTTPException(status_code=404, detail="not_found")
    active, expire = is_subscribed(target_user_id)
    risk = compute_risk_score(target_user_id)
    return {
        "user_id": target_user_id,
        "username": u.get("username"),
        "full_name": u.get("full_name"),
        "phone": u.get("phone"),
        "created_at": u.get("created_at"),
        "subscribed": active,
        "subscription_expire": expire if active else None,
        "risk": risk,
        "banned": is_banned(target_user_id),
        "listings_count": count_listings_by_user(target_user_id),
        "reports_made": count_reports_made(target_user_id),
        "reports_received": count_reports_received(target_user_id),
    }


@router.post("/api/admin/user/{target_user_id}/ban")
async def api_admin_ban_user(target_user_id: int, reason: str = Query("Admin tomonidan cheklandi (shubhali faollik)"), user: str = Depends(check_auth)):
    clean_reason = reason.strip()[:300] or "Admin tomonidan cheklandi"
    ban_user(target_user_id, clean_reason, 0)
    await notify_telegram(target_user_id, "⚠️ Sizga botdan foydalanish cheklandi. Savollar bo'lsa, adminga murojaat qiling.")
    return {"ok": True}


@router.post("/api/admin/user/{target_user_id}/unban")
def api_admin_unban_user(target_user_id: int, user: str = Depends(check_auth)):
    unban_user(target_user_id)
    return {"ok": True}


@router.post("/api/admin/user/{target_user_id}/cancel-subscription")
async def api_admin_cancel_user_subscription(target_user_id: int, user: str = Depends(check_auth)):
    sub_id = get_active_subscription_id(target_user_id)
    if not sub_id:
        raise HTTPException(status_code=404, detail="no_active_subscription")
    cancel_subscription(sub_id)
    await notify_telegram(target_user_id, "❌ Sizning obunangiz administrator tomonidan muddatidan oldin bekor qilindi.")
    return {"ok": True}


@router.get("/api/admin/user-search")
def api_admin_user_search(q: str = Query(...), user: str = Depends(check_auth)):
    q = q.strip()
    if not q:
        return []
    conn = db()
    if q.isdigit():
        rows = conn.execute(
            "SELECT * FROM users WHERE user_id = ? OR phone LIKE ? ORDER BY created_at DESC LIMIT 30",
            (int(q), f"%{q}%"),
        ).fetchall()
    else:
        like = f"%{q.lstrip('@')}%"
        rows = conn.execute(
            "SELECT * FROM users WHERE username LIKE ? OR full_name LIKE ? ORDER BY created_at DESC LIMIT 30",
            (like, like),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================= ADMIN: SOZLAMALAR =============================

@router.get("/api/admin/settings")
def api_admin_get_settings(user: str = Depends(check_auth)):
    return [
        {"key": key, "label": meta["label"], "kind": meta["kind"], "hint": meta.get("hint", ""), "value": get_setting(key)}
        for key, meta in SETTINGS_FIELDS.items()
    ]


@router.post("/api/admin/settings")
def api_admin_set_setting(key: str = Query(...), value: str = Query(...), user: str = Depends(check_auth)):
    meta = SETTINGS_FIELDS.get(key)
    if not meta:
        raise HTTPException(status_code=400, detail="unknown_setting")
    kind = meta["kind"]
    raw = value.strip()
    if kind == "bool":
        if raw not in ("0", "1"):
            raise HTTPException(status_code=400, detail="invalid_value")
        final = raw
    elif kind in ("int", "percent"):
        if not raw.isdigit():
            raise HTTPException(status_code=400, detail="invalid_value")
        if kind == "percent" and not (0 <= int(raw) <= 100):
            raise HTTPException(status_code=400, detail="invalid_value")
        final = raw
    elif kind == "card":
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 16:
            raise HTTPException(status_code=400, detail="invalid_value")
        final = digits
    elif kind == "text":
        if not raw or len(raw) > 40:
            raise HTTPException(status_code=400, detail="invalid_value")
        final = raw
    else:
        final = raw
    set_setting(key, final)
    return {"ok": True, "value": final}


@router.get("/api/admin/ai-usage")
def api_admin_ai_usage(user: str = Depends(check_auth)):
    return ai_usage_summary(30)


@router.get("/api/admin/ai-accuracy")
def api_admin_ai_accuracy(days: int = Query(7), user: str = Depends(check_auth)):
    return ai_accuracy_summary(days)


def _csv_response(filename: str, header: list, rows: list) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/admin/export/usd-rate-history.csv")
def api_export_usd_rate_history(days: int = Query(365), user: str = Depends(check_auth)):
    rows = get_usd_rate_history(days)
    return _csv_response("usd_rate_history.csv", ["rate_som", "recorded_at"], [[r["rate"], r["recorded_at"]] for r in rows])


@router.get("/api/admin/export/district-price-history.csv")
def api_export_district_price_history(days: int = Query(365), user: str = Depends(check_auth)):
    rows = get_district_price_history(days=days)
    return _csv_response(
        "district_price_history.csv",
        ["district", "avg_price_som", "listing_count", "recorded_at"],
        [[r["district"], r["avg_price_som"], r["listing_count"], r["recorded_at"]] for r in rows],
    )


@router.post("/api/admin/broadcast")
def api_admin_broadcast(title: str = Query(...), body: str = Query(...), user: str = Depends(check_auth)):
    title = title.strip()[:120]
    body = body.strip()[:1000]
    if not title or not body:
        raise HTTPException(status_code=400, detail="empty_fields")
    sent = broadcast_notification(title, body)
    return {"ok": True, "sent": sent}


# ============================= ADMIN: QO'LLAB-QUVVATLASH SO'ROVLARI =============================

@router.get("/api/admin/support-requests")
def api_admin_support_requests(user: str = Depends(check_auth)):
    return get_pending_support_requests(limit=100)


@router.post("/api/admin/support-requests/{request_id}/reply")
async def api_admin_reply_support_request(request_id: int, reply: str = Query(...), user: str = Depends(check_auth)):
    reply = reply.strip()[:1000]
    if not reply:
        raise HTTPException(status_code=400, detail="empty_reply")
    row = reply_support_request(request_id, reply)
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    await notify_telegram(row["user_id"], f"\U0001F4AC Qo'llab-quvvatlash so'rovingizga javob keldi:\n\n{html.escape(reply)}")
    return {"ok": True}


@router.post("/api/admin/support-requests/{request_id}/delete")
def api_admin_delete_support_request(request_id: int, user: str = Depends(check_auth)):
    conn = db()
    conn.execute("DELETE FROM support_requests WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ============================= ADMIN: KANALGA TO'G'RIDAN-TO'G'RI POST YUBORISH =============================
# Botdagi tasdiqlash oqimidan tashqari - admin muhim e'lonlarni (aksiya,
# e'lon, ogohlantirish) veb admin paneldan to'g'ridan-to'g'ri kanalga
# yuborishi uchun (masalan, listingga bog'liq bo'lmagan e'lonlar).

@router.post("/api/admin/channel-post")
async def api_admin_channel_post(
    user: str = Depends(check_auth), text: str = Form(...), photo: UploadFile = File(None)
):
    text = text.strip()[:4000]
    if not text:
        raise HTTPException(status_code=400, detail="empty_text")
    if not BOT_TOKEN or not CHANNEL_ID:
        raise HTTPException(status_code=503, detail="not_configured")
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            if photo and photo.filename:
                content = await photo.read()
                resp = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    data={"chat_id": str(CHANNEL_ID), "caption": text, "parse_mode": "HTML"},
                    files={"photo": (photo.filename, content)},
                )
            else:
                resp = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML"},
                )
        except Exception:
            logger.exception("Kanalga to'g'ridan-to'g'ri post yuborishda xatolik")
            raise HTTPException(status_code=502, detail="send_failed")
    data = resp.json()
    if not data.get("ok"):
        logger.error("Kanalga post yuborishda Telegram xatoligi: %s", data)
        raise HTTPException(status_code=502, detail=data.get("description", "Telegram xatoligi"))
    return {"ok": True}



