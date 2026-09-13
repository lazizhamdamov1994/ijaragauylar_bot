"""
Sayt/admin panel ishlatadigan kichik JSON API endpointlari (statistika,
so'rovlar ro'yxati, kuzatuv).
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from common.db import db, now_str

from web.auth import check_auth
from web.listings_data import get_active_listings
from web.render import TASHKENT_DISTRICTS

logger = logging.getLogger(__name__)
router = APIRouter()

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
    conn = db()
    conn.execute(
        "INSERT INTO subarenda_requests (full_name, phone, manzil, xona, narx_talab, status, created_at) VALUES (?,?,?,?,?,'yangi',?)",
        (full_name, phone, manzil, xona, narx_talab, now_str()),
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


@router.get("/api/moderator-stats")
def api_moderator_stats(user: str = Depends(check_auth)):
    """Admin uchun - HAR BIR moderator qancha e'lon joylagani, nechtasi
    tasdiqlangani/rad etilgani. Bot ichida moderator faqat O'ZINING
    natijasini ko'radi - bu yerda esa admin BARCHASINI bir joyda ko'radi."""
    conn = db()
    mods = conn.execute(
        """SELECT m.user_id, m.added_at, u.username, u.full_name
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
            "total": total, "approved": approved, "rejected": rejected,
            "last_activity": last["created_at"] if last else None,
        })
    conn.close()
    return result



