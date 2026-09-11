"""
Ijaraga Uylar Maklersiz - To'liq veb-tizim
==========================================================================
Botning ASOSIY jarayonidan MUSTAQIL, alohida ishlaydigan veb-server.
Xuddi shu SQLite bazasini o'qiydi - botga hech qanday xalaqit bermaydi.

Sahifalar:
  /            - OMMAVIY veb-sayt (bosh sahifa) - SEO uchun, PAROLSIZ
  /uy/{id}     - Har bir e'lonning alohida sahifasi - SEO uchun, PAROLSIZ
  /photo/{id}  - Rasm proksi (Telegram fayllarini xavfsiz ko'rsatish uchun)
  /xarita      - Ommaviy interaktiv xarita - PAROLSIZ
  /tanla-joy   - E'lon berishda joylashuv tanlash (bot uchun WebApp) - PAROLSIZ
  /admin       - Admin panel (statistika + boshqaruv xaritasi) - PAROL bilan
  /sitemap.xml, /robots.txt - qidiruv tizimlari uchun

Ishga tushirish:
    uvicorn dashboard:app --host 0.0.0.0 --port 8001
"""
import hashlib
import logging
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "elonlar.db")
DASH_USER = os.getenv("DASHBOARD_USERNAME", "admin")
DASH_PASS = os.getenv("DASHBOARD_PASSWORD", "")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
INSTAGRAM_URL = os.getenv("INSTAGRAM_URL", "https://www.instagram.com/ijaraga_uylar.uz/")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SITE_URL = os.getenv("DASHBOARD_URL", "").rstrip("/")
SITE_NAME = "Ijaraga Uylar Maklersiz"
BRAND_SHORT = "Ijaraga Uylar"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADMIN_IDS = [int(x) for x in (os.getenv("ADMIN_IDS", "") or "").split(",") if x.strip().lstrip("-").isdigit()]
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "")
MAX_WEB_LISTING_PHOTOS = 10
MAX_WEB_SUBMISSIONS_PER_IP_PER_DAY = 3

app = FastAPI(title=SITE_NAME, docs_url=None, redoc_url=None, openapi_url=None)
security = HTTPBasic()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Har bir javobga xavfsizlik sarlavhalarini qo'shadi."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Server"] = "IjaragaUylar"
        return response


app.add_middleware(SecurityHeadersMiddleware)


_failed_attempts: dict = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
BLOCK_SECONDS = 900


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_auth(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    ip = _client_ip(request)
    now = time.time()
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if now - t < BLOCK_SECONDS]
    if len(_failed_attempts[ip]) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Juda ko'p noto'g'ri urinish. 15 daqiqadan keyin qayta urinib ko'ring.")
    correct_user = secrets.compare_digest(credentials.username, DASH_USER)
    correct_pass = secrets.compare_digest(credentials.password, DASH_PASS)
    if not (correct_user and correct_pass):
        _failed_attempts[ip].append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login yoki parol noto'g'ri",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_tracking_tables():
    """Faqat shu dashboard ishlatadigan, YANGI, MUSTAQIL jadvallar."""
    conn = db()
    conn.execute("""CREATE TABLE IF NOT EXISTS map_views (id INTEGER PRIMARY KEY AUTOINCREMENT, viewed_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS map_clicks (id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL, clicked_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS site_visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, ip TEXT, country TEXT, city TEXT,
        device TEXT, browser TEXT, referrer TEXT, visited_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS subarenda_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, full_name TEXT, phone TEXT,
        manzil TEXT, xona TEXT, narx_talab TEXT, status TEXT DEFAULT 'yangi', created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS listing_inquiries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER, owner_user_id INTEGER,
        name TEXT, phone TEXT, message TEXT, status TEXT DEFAULT 'yangi', created_at TEXT)""")
    # Veb-saytdan yuborilgan e'lonlarni spamdan himoya qilish uchun (IP bo'yicha kunlik limit).
    conn.execute("""CREATE TABLE IF NOT EXISTS web_listing_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT, created_at TEXT)""")
    # "listings" jadvali bot.py tomonidan yaratiladi — bu yerda faqat dashboard'ga
    # kerak bo'lgan, botga zarar bermaydigan YANGI ustunni qo'shamiz (mavjud bo'lsa o'tkazib yuboriladi).
    existing_cols = [r["name"] for r in conn.execute("PRAGMA table_info(listings)").fetchall()]
    if existing_cols and "source" not in existing_cols:
        conn.execute("ALTER TABLE listings ADD COLUMN source TEXT DEFAULT 'bot'")
    conn.commit()
    conn.close()


def detect_device(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "bot" in ua or "crawl" in ua or "spider" in ua:
        return "Bot"
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        return "Mobil"
    if "ipad" in ua or "tablet" in ua:
        return "Planshet"
    return "Kompyuter"


def detect_browser(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "edg/" in ua:
        return "Edge"
    if "chrome" in ua and "chromium" not in ua:
        return "Chrome"
    if "safari" in ua and "chrome" not in ua:
        return "Safari"
    if "firefox" in ua:
        return "Firefox"
    if "telegram" in ua:
        return "Telegram"
    return "Boshqa"


_geo_cache: dict = {}


async def lookup_geo(ip: str) -> tuple:
    if ip in _geo_cache:
        return _geo_cache[ip]
    if ip in ("127.0.0.1", "unknown", "testclient") or ip.startswith("192.168.") or ip.startswith("10."):
        return ("Mahalliy", "Mahalliy")
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"http://ip-api.com/json/{ip}?fields=country,city,status")
            data = resp.json()
            if data.get("status") == "success":
                result = (data.get("country") or "Noma'lum", data.get("city") or "Noma'lum")
                _geo_cache[ip] = result
                return result
    except Exception:
        pass
    return ("Noma'lum", "Noma'lum")


TRACK_EXCLUDE_PREFIXES = ("/api/", "/photo/", "/admin", "/static", "/logo", "/favicon", "/sitemap", "/robots")


class VisitTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            if request.method == "GET" and not any(request.url.path.startswith(p) for p in TRACK_EXCLUDE_PREFIXES):
                ip = _client_ip(request)
                ua = request.headers.get("user-agent", "")
                referrer = request.headers.get("referer", "")[:200]
                country, city = await lookup_geo(ip)
                conn = db()
                conn.execute(
                    "INSERT INTO site_visits (path, ip, country, city, device, browser, referrer, visited_at) VALUES (?,?,?,?,?,?,?,?)",
                    (request.url.path, ip, country, city, detect_device(ua), detect_browser(ua), referrer, now_str()),
                )
                conn.commit()
                conn.close()
        except Exception:
            pass
        return response


app.add_middleware(VisitTrackingMiddleware)


init_tracking_tables()


def get_active_listings():
    conn = db()
    rows = conn.execute(
        """SELECT id, manzil, moljal, kimlarga, xona, narx, latitude, longitude, created_at, channel_msg_id
           FROM listings
           WHERE status = 'approved' AND COALESCE(expired,0) = 0
           AND latitude IS NOT NULL AND longitude IS NOT NULL"""
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("channel_msg_id") and CHANNEL_USERNAME:
            d["post_link"] = f"https://t.me/{CHANNEL_USERNAME}/{d['channel_msg_id']}"
        else:
            d["post_link"] = None
        result.append(d)
    return result


# ============================= OMMAVIY SAYT - MA'LUMOTLAR =============================

import json as _json

PER_PAGE = 12


def _parse_photos(row_dict):
    try:
        row_dict["photos"] = _json.loads(row_dict.get("photos") or "[]")
    except Exception:
        row_dict["photos"] = []
    return row_dict


def get_site_listings(hudud: str = "", xona: str = "", page: int = 1):
    conn = db()
    query = "SELECT * FROM listings WHERE status='approved' AND COALESCE(expired,0)=0"
    params = []
    if hudud:
        query += " AND (manzil LIKE ? OR moljal LIKE ?)"
        params += [f"%{hudud}%", f"%{hudud}%"]
    if xona:
        query += " AND xona LIKE ?"
        params.append(f"%{xona}%")
    # Pullik ("TOP") e'lonlar — egasi "topshirildi" deb belgilamaguncha —
    # ro'yxat boshida turadi (botdagi kanalga qayta-joylash mantig'i bilan bir xil).
    query += " ORDER BY (CASE WHEN COALESCE(price_charged,0) > 0 THEN 0 ELSE 1 END) ASC, created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    listings = [_parse_photos(dict(r)) for r in rows]
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
        """SELECT id, manzil, moljal, xona, narx, photos, price_charged FROM listings
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


TASHKENT_DISTRICTS = [
    "Yunusobod", "Chilonzor", "Sergeli", "Mirzo Ulug'bek", "Shayxontohur",
    "Olmazor", "Bektemir", "Uchtepa", "Yashnobod", "Yakkasaroy",
    "Mirobod", "Yangihayot",
]

_DISTRICT_ALIASES = {
    "Yunusobod": ["yunusobod", "yunusabad", "юнусобод", "юнусабад"],
    "Chilonzor": ["chilonzor", "chilanzar", "чилонзор", "чиланзар"],
    "Sergeli": ["sergeli", "сергели"],
    "Mirzo Ulug'bek": ["mirzo ulug", "mirzo-ulug", "мирзо улуг", "мирзо-улуг"],
    "Shayxontohur": ["shayxontohur", "shaykhontohur", "шайхонтохур", "шайхантахур"],
    "Olmazor": ["olmazor", "olmazar", "олмазор", "олмазар"],
    "Bektemir": ["bektemir", "бектемир"],
    "Uchtepa": ["uchtepa", "учтепа"],
    "Yashnobod": ["yashnobod", "yashnabad", "яшнобод", "яшнабад"],
    "Yakkasaroy": ["yakkasaroy", "yakkasaray", "яккасарой", "яккасарай"],
    "Mirobod": ["mirobod", "миробод"],
    "Yangihayot": ["yangihayot", "янгихаёт", "янгихает"],
}


def extract_district(text: str) -> str:
    """Matndan (masalan tezkor e'lon xom matnidan) tuman nomini avtomatik
    aniqlaydi. Topilmasa umumiy \"Toshkent\" qaytaradi."""
    low = (text or "").lower()
    for canonical, aliases in _DISTRICT_ALIASES.items():
        for alias in aliases:
            if alias in low:
                return canonical
    return "Toshkent"


def display_address(l: dict) -> str:
    """Kartochka/sarlavha uchun manzilni qaytaradi - agar oddiy manzil
    bo'lmasa (tezkor e'lonlarda bo'lgani kabi), xom matndan tuman nomini
    avtomatik aniqlab, o'rniga qo'yadi."""
    manzil = (l.get("manzil") or "").strip()
    if manzil:
        return manzil
    district = extract_district(l.get("raw_text") or "")
    return f"{district}dagi e'lon"


# ============================= RASM PROKSI (Telegram fayllarini xavfsiz ko'rsatish) =============================

import hashlib

PHOTO_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photo_cache")
os.makedirs(PHOTO_CACHE_DIR, exist_ok=True)


@app.get("/photo/{file_id}")
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

SITE_CSS = """
  :root {
    --brand: #FF385C; --brand-dark: #E31C5F; --brand-light: #FFE8EC;
    --ink: #222222; --ink-soft: #484848; --muted: #717171; --line: #EBEBEB;
    --bg: #ffffff; --bg-soft: #F7F7F7;
    --radius-sm: 8px; --radius: 12px; --radius-lg: 20px; --radius-pill: 999px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.08);
    --shadow: 0 6px 16px rgba(0,0,0,0.12);
    --shadow-lg: 0 12px 32px rgba(0,0,0,0.16), 0 2px 8px rgba(0,0,0,0.06);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: var(--ink); background: var(--bg); line-height: 1.5; font-size: 15px;
    -webkit-font-smoothing: antialiased;
  }
  img { max-width: 100%; display: block; }
  a { color: inherit; text-decoration: none; }
  .ico { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; vertical-align: middle; }
  .ico svg { width: 100%; height: 100%; }
  button, input, select { font-family: inherit; }

  .wrap { max-width: 1280px; margin: 0 auto; padding: 0 24px; }
  @media (max-width: 640px) { .wrap { padding: 0 16px; } }

  /* ============ HEADER ============ */
  header.site-header {
    background: #fff; position: sticky; top: 0; z-index: 500;
    border-bottom: 1px solid var(--line);
  }
  .header-inner {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 24px; max-width: 1280px; margin: 0 auto; gap: 16px;
  }
  .brand { display: flex; align-items: center; gap: 10px; font-size: 19px; font-weight: 800; letter-spacing: -0.4px; color: var(--ink); flex-shrink: 0; }
  .brand img { width: 34px; height: 34px; border-radius: 9px; }
  nav.main-nav { display: flex; gap: 4px; align-items: center; }
  nav.main-nav a.nav-link {
    font-size: 14px; font-weight: 600; color: var(--ink-soft); padding: 10px 14px;
    border-radius: var(--radius-pill); transition: background .15s;
  }
  nav.main-nav a.nav-link:hover { background: var(--bg-soft); }
  .btn-cta {
    background: var(--brand); color: #fff !important; padding: 10px 20px; border-radius: var(--radius-pill);
    font-weight: 700; font-size: 14px; transition: background .15s, transform .1s;
    display: inline-flex; align-items: center; gap: 7px; border: none; cursor: pointer;
  }
  .btn-cta:hover { background: var(--brand-dark); }
  .btn-cta:active { transform: scale(0.97); }
  .nav-icon-link { display: flex; align-items: center; justify-content: center; width: 38px; height: 38px; padding: 0 !important; color: var(--ink-soft); }
  .mobile-menu-btn {
    display: none; width: 38px; height: 38px; border-radius: var(--radius-pill); border: none;
    background: var(--bg-soft); color: var(--ink); align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0;
  }
  .mobile-menu {
    display: none; flex-direction: column; padding: 8px 16px 14px; border-top: 1px solid var(--line); background: #fff;
  }
  .mobile-menu.open { display: flex; }
  .mobile-menu a {
    display: flex; align-items: center; gap: 12px; padding: 12px 6px; font-size: 14.5px; font-weight: 600;
    color: var(--ink-soft); border-bottom: 1px solid var(--line);
  }
  .mobile-menu a:last-child { border-bottom: none; }
  .mobile-menu a:hover { color: var(--brand); }
  @media (max-width: 640px) {
    .header-inner { padding: 12px 16px; }
    .brand { font-size: 15px; }
    .brand img { width: 28px; height: 28px; }
    nav.main-nav { display: none; }
    .mobile-menu-btn { display: flex; }
  }

  /* ============ HERO + SEARCH ============ */
  .hero {
    background: linear-gradient(180deg, var(--brand-light) 0%, #fff 100%);
    padding: 48px 20px 96px; text-align: center;
  }
  .hero h1 { font-size: 36px; font-weight: 800; letter-spacing: -1px; margin-bottom: 10px; color: var(--ink); }
  .hero p.sub { font-size: 16.5px; color: var(--ink-soft); max-width: 520px; margin: 0 auto 32px; }
  @media (max-width: 640px) { .hero { padding: 32px 16px 84px; } .hero h1 { font-size: 24px; } .hero p.sub { font-size: 14px; margin-bottom: 24px; } }

  .search-pill {
    background: #fff; border-radius: var(--radius-pill); padding: 8px; max-width: 720px; margin: 0 auto;
    box-shadow: var(--shadow-lg); border: 1px solid var(--line);
    display: grid; grid-template-columns: 1fr 1fr auto; align-items: stretch; gap: 0;
  }
  .search-pill .seg { padding: 10px 22px; border-right: 1px solid var(--line); text-align: left; }
  .search-pill .seg:last-of-type { border-right: none; }
  .search-pill label { display: block; font-size: 11px; font-weight: 700; color: var(--ink); margin-bottom: 2px; }
  .search-pill select {
    border: none; outline: none; font-size: 13.5px; font-weight: 500; color: var(--ink-soft);
    background: transparent; width: 100%; cursor: pointer;
  }
  .search-pill button {
    background: var(--brand); color: #fff; border: none; border-radius: var(--radius-pill); padding: 0 26px;
    font-weight: 700; font-size: 14px; cursor: pointer; display: flex; align-items: center; gap: 8px;
    transition: background .15s;
  }
  .search-pill button:hover { background: var(--brand-dark); }
  @media (max-width: 640px) {
    .search-pill { grid-template-columns: 1fr 1fr; border-radius: var(--radius-lg); padding: 10px; gap: 8px; }
    .search-pill .seg { border-right: none; border-bottom: 1px solid var(--line); padding: 8px 12px; }
    .search-pill button { grid-column: 1 / -1; padding: 13px; border-radius: var(--radius); justify-content: center; margin-top: 4px; }
  }

  /* ============ STATS STRIP ============ */
  .stats-strip { margin-top: -56px; position: relative; z-index: 10; }
  .stats-strip .inner {
    background: #fff; border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); border: 1px solid var(--line);
    padding: 22px 32px; display: flex; justify-content: space-around; gap: 20px; flex-wrap: wrap; max-width: 720px; margin: 0 auto;
  }
  .stat-item { text-align: center; }
  .stat-item .num { font-size: 26px; font-weight: 800; color: var(--ink); }
  .stat-item .lbl { font-size: 12px; color: var(--muted); font-weight: 600; margin-top: 2px; }
  @media (max-width: 640px) { .stats-strip .inner { padding: 16px 12px; gap: 8px; } .stat-item .num { font-size: 19px; } }

  /* ============ MAIN CONTENT ============ */
  main { padding: 56px 0 60px; }
  @media (max-width: 640px) { main { padding: 36px 0 40px; } }
  .section-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 24px; flex-wrap: wrap; gap: 8px; }
  .section-head h2 { font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }
  .section-head .count { font-size: 13.5px; color: var(--muted); font-weight: 600; }

  /* ============ LISTING CARDS ============ */
  .listing-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 28px 22px; }
  @media (max-width: 640px) { .listing-grid { grid-template-columns: repeat(2, 1fr); gap: 18px 12px; } }
  .listing-card { cursor: pointer; }
  .lc-photo { position: relative; aspect-ratio: 1/1; background: var(--bg-soft); overflow: hidden; border-radius: var(--radius); margin-bottom: 10px; }
  .listing-card:hover .lc-photo img { transform: scale(1.06); }
  .lc-photo img { width: 100%; height: 100%; object-fit: cover; transition: transform .35s ease; }
  .lc-photo .lc-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 44px; background: linear-gradient(135deg,#FFE8EC,#FFF5F1); }
  .lc-badge {
    position: absolute; top: 10px; left: 10px; background: #fff; color: var(--ink);
    padding: 4px 11px; border-radius: var(--radius-pill); font-size: 11px; font-weight: 700; box-shadow: var(--shadow-sm);
    display: inline-flex; align-items: center; gap: 4px;
  }
  .lc-badge-fire { background: var(--ink); color: #fff; }
  .lc-badge .ico, .badge .ico { width: 13px; height: 13px; }
  .cat-verified { background: #E7F6EC; color: #1A7A3C; }
  .cat-subarenda { background: #EAF1FE; color: #1D4ED8; }
  .cat-premium { background: #FDF3E3; color: #B8860B; }
  .lc-body { padding: 0 2px; }
  .lc-top { display: flex; justify-content: space-between; align-items: baseline; gap: 6px; }
  .lc-title { font-size: 14.5px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  .lc-meta { font-size: 13px; color: var(--muted); margin-top: 2px; }
  .lc-price { font-size: 14.5px; font-weight: 800; margin-top: 4px; }
  @media (max-width: 640px) { .lc-title { font-size: 13px; } .lc-meta { font-size: 11.5px; } .lc-price { font-size: 13px; } }

  .pagination { display: flex; justify-content: center; gap: 8px; margin-top: 40px; }
  .pagination a, .pagination span {
    width: 38px; height: 38px; display: flex; align-items: center; justify-content: center;
    border-radius: 50%; font-size: 13.5px; font-weight: 700;
  }
  .pagination a { background: #fff; color: var(--ink); border: 1px solid var(--line); }
  .pagination a:hover { border-color: var(--ink); }
  .pagination .active { background: var(--ink); color: #fff; }

  /* ============ WHY SECTION ============ */
  .why-section { background: var(--bg-soft); padding: 64px 0; margin-top: 24px; }
  .why-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 28px; margin-top: 32px; }
  .why-item { text-align: center; padding: 12px; }
  .why-item .icon {
    width: 56px; height: 56px; border-radius: 50%; background: var(--brand-light); display: flex;
    align-items: center; justify-content: center; margin: 0 auto 14px; color: var(--brand);
  }
  .why-item .icon .ico { width: 26px; height: 26px; }
  .why-item h3 { font-size: 16px; font-weight: 700; margin-bottom: 6px; }
  .why-item p { font-size: 13.5px; color: var(--muted); }

  /* ============ FOOTER ============ */
  footer.site-footer { background: #fff; border-top: 1px solid var(--line); padding: 40px 0 24px; }
  .footer-inner { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 24px; margin-bottom: 24px; }
  .footer-brand { display: flex; align-items: center; gap: 8px; color: var(--ink); font-weight: 800; font-size: 16px; margin-bottom: 8px; }
  .footer-brand img { width: 26px; height: 26px; border-radius: 7px; }
  .footer-links { display: flex; gap: 22px; flex-wrap: wrap; }
  .footer-links a { font-size: 13.5px; font-weight: 600; color: var(--ink-soft); }
  .footer-links a:hover { color: var(--ink); text-decoration: underline; }
  .footer-bottom { border-top: 1px solid var(--line); padding-top: 18px; font-size: 12.5px; text-align: center; color: var(--muted); }

  .empty-state { text-align: center; padding: 70px 20px; color: var(--muted); }
  .empty-state .icon { color: var(--muted); margin-bottom: 16px; display: flex; justify-content: center; }

  /* ============ BATAFSIL SAHIFA ============ */
  .breadcrumb { font-size: 13px; color: var(--muted); margin-bottom: 20px; }
  .breadcrumb a:hover { color: var(--ink); text-decoration: underline; }
  .detail-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 40px; align-items: start; }
  @media (max-width: 900px) { .detail-grid { grid-template-columns: 1fr; gap: 24px; } }

  .gallery-wrap { position: relative; margin-bottom: 22px; }
  .gallery-scroll {
    display: flex; overflow-x: auto; scroll-snap-type: x mandatory; border-radius: var(--radius-lg);
    aspect-ratio: 4/3; background: var(--bg-soft); scrollbar-width: none; -webkit-overflow-scrolling: touch;
  }
  .gallery-scroll::-webkit-scrollbar { display: none; }
  .gallery-scroll.gs-empty { display: flex; align-items: center; justify-content: center; flex-direction: column; color: var(--muted); }
  .gs-slide { flex: 0 0 100%; scroll-snap-align: start; width: 100%; height: 100%; }
  .gs-slide img { width: 100%; height: 100%; object-fit: cover; cursor: zoom-in; }
  .gs-dots { position: absolute; bottom: 14px; left: 0; right: 0; display: flex; justify-content: center; gap: 6px; }
  .gs-dot { width: 6px; height: 6px; border-radius: 50%; background: rgba(255,255,255,0.55); transition: all .2s; }
  .gs-dot.active { background: #fff; width: 18px; border-radius: 3px; }
  .gs-counter { position: absolute; top: 14px; right: 14px; background: rgba(0,0,0,0.55); color: #fff; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: var(--radius-pill); }
  .gs-arrow {
    position: absolute; top: 50%; transform: translateY(-50%); width: 38px; height: 38px; border-radius: 50%;
    background: rgba(255,255,255,0.9); border: none; cursor: pointer; display: none; align-items: center; justify-content: center;
    color: var(--ink); box-shadow: var(--shadow); transition: background .15s;
  }
  .gs-arrow:hover { background: #fff; }
  .gs-arrow-left { left: 12px; }
  .gs-arrow-right { right: 12px; }
  .gs-expand {
    position: absolute; bottom: 14px; right: 14px; width: 34px; height: 34px; border-radius: 50%;
    background: rgba(0,0,0,0.55); border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #fff;
  }
  @media (min-width: 901px) { .gs-arrow { display: flex; } }

  .lightbox {
    display: none; position: fixed; inset: 0; background: rgba(10,10,10,0.96); z-index: 2000;
    align-items: center; justify-content: center;
  }
  .lightbox.open { display: flex; }
  .lb-track { display: flex; width: 100%; height: 100%; transition: transform .3s ease; }
  .lb-slide { flex: 0 0 100%; display: flex; align-items: center; justify-content: center; padding: 40px; }
  .lb-slide img { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 6px; }
  .lb-close {
    position: absolute; top: 18px; right: 18px; width: 42px; height: 42px; border-radius: 50%;
    background: rgba(255,255,255,0.12); border: none; cursor: pointer; color: #fff; display: flex; align-items: center; justify-content: center;
    z-index: 2001;
  }
  .lb-close:hover { background: rgba(255,255,255,0.22); }
  .lb-arrow {
    position: absolute; top: 50%; transform: translateY(-50%); width: 46px; height: 46px; border-radius: 50%;
    background: rgba(255,255,255,0.12); border: none; cursor: pointer; color: #fff; display: flex; align-items: center; justify-content: center;
    z-index: 2001;
  }
  .lb-arrow:hover { background: rgba(255,255,255,0.22); }
  .lb-arrow-left { left: 16px; }
  .lb-arrow-right { right: 16px; }
  @media (max-width: 640px) { .lb-slide { padding: 12px; } .lb-arrow { width: 38px; height: 38px; } }

  .detail-title { font-size: 26px; font-weight: 800; letter-spacing: -0.6px; margin: 24px 0 6px; }
  .detail-addr { font-size: 15px; color: var(--muted); margin-bottom: 16px; }
  .detail-badges { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }
  .badge { font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: var(--radius-pill); display: inline-flex; align-items: center; gap: 5px; }
  .badge.trust { background: #E7F6EC; color: #1A7A3C; }
  .badge.paid { background: var(--brand-light); color: var(--brand-dark); }

  .detail-facts { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 22px 0; }
  .fact-box { background: var(--bg-soft); border-radius: var(--radius); padding: 16px; }
  .fact-box .fl { font-size: 11.5px; color: var(--muted); font-weight: 600; margin-bottom: 4px; }
  .fact-box .fv { font-size: 15px; font-weight: 700; }

  .desc-block { border-top: 1px solid var(--line); padding: 24px 0; margin: 8px 0; }
  .desc-block h3 { font-size: 16px; font-weight: 700; margin-bottom: 10px; }
  .desc-block p { font-size: 14.5px; color: var(--ink-soft); white-space: pre-line; }

  .sidebar-card { background: #fff; border: 1px solid var(--line); border-radius: var(--radius-lg); padding: 24px; position: sticky; top: 90px; box-shadow: var(--shadow); }
  @media (max-width: 900px) { .sidebar-card { position: static; margin-top: 8px; } }
  .sidebar-price { font-size: 30px; font-weight: 800; color: var(--ink); }
  .sidebar-cta {
    display: flex; align-items: center; justify-content: center; gap: 8px; text-align: center; background: var(--brand); color: #fff; padding: 16px;
    border-radius: var(--radius-pill); font-weight: 700; font-size: 15.5px; margin: 18px 0 10px; transition: background .15s;
  }
  .sidebar-cta:hover { background: var(--brand-dark); }
  .sidebar-note { font-size: 12.5px; color: var(--muted); text-align: center; }
  .sidebar-share { display: flex; gap: 8px; margin-top: 18px; }
  .sidebar-share button {
    flex: 1; padding: 11px; border-radius: var(--radius); border: 1px solid var(--line); background: #fff;
    font-size: 12.5px; font-weight: 700; cursor: pointer; color: var(--ink); transition: border-color .15s;
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  }
  .sidebar-share button:hover { border-color: var(--ink); }

  .inquiry-toggle {
    display: flex; align-items: center; gap: 8px; margin-top: 16px; padding-top: 16px;
    border-top: 1px solid var(--line); font-size: 13.5px; font-weight: 700; color: var(--ink);
    cursor: pointer; user-select: none;
  }
  .inquiry-toggle:hover { color: var(--brand); }
  .inquiry-form { display: none; flex-direction: column; gap: 8px; margin-top: 12px; }
  .inquiry-form.open { display: flex; }
  .inquiry-form input, .inquiry-form textarea {
    padding: 10px 12px; border: 1.5px solid var(--line); border-radius: 10px; font-size: 13.5px;
    font-family: inherit; resize: vertical;
  }
  .inquiry-form input:focus, .inquiry-form textarea:focus { outline: none; border-color: var(--brand); }
  .inquiry-submit {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    background: var(--ink); color: #fff; border: none; padding: 11px; border-radius: 10px;
    font-weight: 700; font-size: 13.5px; cursor: pointer; transition: opacity .15s;
  }
  .inquiry-submit:hover { opacity: 0.85; }
  .inquiry-submit:disabled { opacity: 0.5; cursor: default; }
  .inquiry-success {
    display: none; align-items: center; gap: 6px; color: #1A7A3C; font-size: 13.5px; font-weight: 700;
    justify-content: center; padding: 6px 0;
  }

  #detail-map { height: 270px; border-radius: var(--radius-lg); margin-top: 22px; }
  .related-strip { margin-top: 56px; }

  /* ============ E'LON JOYLASH FORMASI (/elon-joylash) ============ */
  .form-page-hero { background: linear-gradient(180deg, var(--brand-light) 0%, #fff 100%); padding: 40px 20px 60px; text-align: center; }
  .form-page-hero h1 { font-size: 30px; font-weight: 800; letter-spacing: -0.6px; margin-bottom: 8px; }
  .form-page-hero p { font-size: 15px; color: var(--ink-soft); max-width: 560px; margin: 0 auto; }
  @media (max-width: 640px) { .form-page-hero h1 { font-size: 22px; } .form-page-hero { padding: 28px 16px 44px; } }

  .form-shell { max-width: 720px; margin: -32px auto 0; position: relative; z-index: 5; }
  .form-card { background: #fff; border: 1px solid var(--line); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); padding: 28px; }
  @media (max-width: 640px) { .form-card { padding: 18px; border-radius: var(--radius); } }

  .fstep-badge { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; color: var(--brand); background: var(--brand-light); padding: 4px 12px; border-radius: var(--radius-pill); margin-bottom: 14px; }
  .form-section-title { font-size: 17px; font-weight: 800; margin: 26px 0 14px; display: flex; align-items: center; gap: 8px; }
  .form-section-title:first-child { margin-top: 0; }
  .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  @media (max-width: 560px) { .form-row { grid-template-columns: 1fr; } }
  .form-group { margin-bottom: 14px; }
  .form-group label { display: block; font-size: 12.5px; font-weight: 700; color: var(--ink-soft); margin-bottom: 6px; }
  .form-group .req { color: var(--brand); }
  .form-input, .form-textarea, .form-select {
    width: 100%; padding: 12px 14px; border: 1.5px solid var(--line); border-radius: 10px;
    font-size: 14px; font-family: inherit; background: #fff; color: var(--ink); transition: border-color .15s;
  }
  .form-input:focus, .form-textarea:focus, .form-select:focus { outline: none; border-color: var(--brand); }
  .form-textarea { resize: vertical; min-height: 84px; }
  .form-hint { font-size: 11.5px; color: var(--muted); margin-top: 5px; }
  .form-error-box { background: #FDEDEB; color: #C0362C; border: 1px solid #F6C6C0; border-radius: 10px; padding: 11px 14px; font-size: 13px; font-weight: 600; margin-bottom: 16px; display: none; }
  .form-error-box.show { display: block; }

  .type-toggle { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 6px; }
  .type-option { position: relative; border: 2px solid var(--line); border-radius: 14px; padding: 14px; cursor: pointer; transition: border-color .15s, background .15s; }
  .type-option input { position: absolute; opacity: 0; }
  .type-option .to-title { font-weight: 800; font-size: 14.5px; display: flex; align-items: center; gap: 6px; }
  .type-option .to-desc { font-size: 12px; color: var(--muted); margin-top: 4px; line-height: 1.45; }
  .type-option.active { border-color: var(--brand); background: var(--brand-light); }
  @media (max-width: 560px) { .type-toggle { grid-template-columns: 1fr; } }

  .pay-panel { display: none; margin-top: 14px; background: var(--bg-soft); border-radius: 14px; padding: 16px; }
  .pay-panel.show { display: block; }
  .card-box { background: #fff; border: 1.5px dashed var(--line); border-radius: 12px; padding: 14px; display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
  .card-box .cb-num { font-family: 'Courier New', monospace; font-size: 16px; font-weight: 800; letter-spacing: 1px; }
  .card-box button { background: var(--ink); color: #fff; border: none; padding: 8px 14px; border-radius: 8px; font-size: 12px; font-weight: 700; cursor: pointer; flex-shrink: 0; }

  .photo-drop {
    border: 2px dashed var(--line); border-radius: 14px; padding: 26px 16px; text-align: center; cursor: pointer;
    transition: border-color .15s, background .15s; color: var(--muted);
  }
  .photo-drop:hover, .photo-drop.dragover { border-color: var(--brand); background: var(--brand-light); }
  .photo-drop .pd-title { font-weight: 700; color: var(--ink); font-size: 14px; margin-top: 8px; }
  .photo-drop .pd-sub { font-size: 12px; margin-top: 3px; }
  .photo-preview { display: grid; grid-template-columns: repeat(auto-fill, minmax(78px, 1fr)); gap: 8px; margin-top: 12px; }
  .photo-thumb { position: relative; aspect-ratio: 1/1; border-radius: 10px; overflow: hidden; background: var(--bg-soft); }
  .photo-thumb img { width: 100%; height: 100%; object-fit: cover; }
  .photo-thumb .pt-remove {
    position: absolute; top: 3px; right: 3px; width: 20px; height: 20px; border-radius: 50%; background: rgba(0,0,0,0.6);
    color: #fff; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 12px; line-height: 1;
  }

  #locationMap { height: 240px; border-radius: 14px; margin-top: 10px; display: none; }
  #locationMap.show { display: block; }
  .loc-toggle-row { display: flex; align-items: center; justify-content: space-between; background: var(--bg-soft); border-radius: 12px; padding: 12px 14px; }
  .loc-toggle-row .lt-label { font-size: 13.5px; font-weight: 700; display: flex; align-items: center; gap: 7px; }
  .switch { position: relative; display: inline-block; width: 42px; height: 24px; flex-shrink: 0; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .switch .slider { position: absolute; inset: 0; background: var(--line); border-radius: 24px; transition: .2s; cursor: pointer; }
  .switch .slider::before { content: ""; position: absolute; width: 18px; height: 18px; left: 3px; top: 3px; background: #fff; border-radius: 50%; transition: .2s; box-shadow: 0 1px 3px rgba(0,0,0,.3); }
  .switch input:checked + .slider { background: var(--brand); }
  .switch input:checked + .slider::before { transform: translateX(18px); }

  .form-submit-btn {
    width: 100%; background: var(--brand); color: #fff; border: none; padding: 15px; border-radius: 14px;
    font-weight: 800; font-size: 15.5px; cursor: pointer; margin-top: 22px; display: flex; align-items: center;
    justify-content: center; gap: 8px; transition: background .15s, opacity .15s;
  }
  .form-submit-btn:hover { background: var(--brand-dark); }
  .form-submit-btn:disabled { opacity: 0.6; cursor: default; }

  .form-success-screen { text-align: center; padding: 50px 20px; }
  .form-success-screen .fs-icon { width: 74px; height: 74px; border-radius: 50%; background: #E7F6EC; color: #1A7A3C; display: flex; align-items: center; justify-content: center; margin: 0 auto 18px; }
  .form-success-screen h2 { font-size: 21px; font-weight: 800; margin-bottom: 8px; }
  .form-success-screen p { font-size: 14px; color: var(--muted); max-width: 400px; margin: 0 auto; }
"""


def render_head(title: str, description: str, canonical_path: str, og_image: str = "") -> str:
    canonical = f"{SITE_URL}{canonical_path}" if SITE_URL else canonical_path
    if not og_image and SITE_URL:
        og_image = f"{SITE_URL}/logo.png"
    return f"""<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{og_image}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0f1b2e">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{SITE_CSS}</style>"""


def render_header() -> str:
    bot_link = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "#"
    channel_link = f"https://t.me/{CHANNEL_USERNAME}" if CHANNEL_USERNAME else "#"
    logo = "/logo.png"
    return f"""<header class="site-header">
  <div class="header-inner">
    <a href="/" class="brand"><img src="{logo}" alt="{SITE_NAME}"> {BRAND_SHORT}</a>
    <nav class="main-nav">
      <a href="/" class="nav-link">Bosh sahifa</a>
      <a href="/subarenda" class="nav-link">Subarenda</a>
      <a href="/xarita" class="nav-link nav-icon-link" title="Xarita">{icon('map', 18)}</a>
      <a href="{bot_link}" class="nav-link nav-icon-link" target="_blank" title="Telegram bot">{icon('phone', 16)}</a>
      <a href="{channel_link}" class="nav-link nav-icon-link" target="_blank" title="Telegram kanal">{icon('send', 17)}</a>
      <a href="{INSTAGRAM_URL}" class="nav-link nav-icon-link" target="_blank" title="Instagram">{icon('instagram', 18)}</a>
      <a href="/elon-joylash" class="btn-cta">{icon('sparkle', 14)} Bepul e'lon joylash</a>
    </nav>
    <button class="mobile-menu-btn" onclick="toggleMobileMenu()" aria-label="Menyu">{icon('menu', 20)}</button>
  </div>
  <div class="mobile-menu" id="mobileMenu">
    <a href="/">{icon('home', 17)} Bosh sahifa</a>
    <a href="/elon-joylash">{icon('sparkle', 17)} E'lon joylash</a>
    <a href="/xarita">{icon('map', 17)} Xarita</a>
    <a href="/subarenda">{icon('coin', 17)} Subarenda</a>
    <a href="{channel_link}" target="_blank">{icon('send', 17)} Telegram kanal</a>
    <a href="{INSTAGRAM_URL}" target="_blank">{icon('instagram', 17)} Instagram</a>
    <a href="{bot_link}" target="_blank">{icon('phone', 17)} Botni ochish</a>
  </div>
</header>
<script>
function toggleMobileMenu() {{
  document.getElementById('mobileMenu').classList.toggle('open');
}}
// MUHIM: brauzerning "orqaga" tugmasi bosilganda sahifa bfcache'dan
// (avvalgi holatida "muzlatilgan" holda) tiklanishi mumkin - bu holda
// mobil menyu ochiq qolib ketishi yoki body scroll qulflangan holda
// qolib ketishi mumkin edi. Shu narsani har safar tuzatib qo'yamiz.
window.addEventListener('pageshow', function(event) {{
  const menu = document.getElementById('mobileMenu');
  if (menu) menu.classList.remove('open');
  document.body.style.overflow = '';
  document.documentElement.style.overflow = '';
  const lb = document.getElementById('lightbox');
  if (lb) lb.classList.remove('open');
}});
</script>"""


def render_footer() -> str:
    bot_link = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "#"
    channel_link = f"https://t.me/{CHANNEL_USERNAME}" if CHANNEL_USERNAME else "#"
    year = datetime.now().year
    logo = "/logo.png"
    return f"""<footer class="site-footer">
  <div class="wrap">
    <div class="footer-inner">
      <div>
        <div class="footer-brand"><img src="{logo}" alt="{SITE_NAME}"> {BRAND_SHORT}</div>
        <div style="font-size:13px;max-width:320px;color:var(--muted);">Maklersiz, to'g'ridan-to'g'ri uy egasi bilan bog'lanish platformasi.</div>
      </div>
      <div class="footer-links">
        <a href="/">Bosh sahifa</a>
        <a href="/elon-joylash">E'lon joylash</a>
        <a href="/xarita">Xarita</a>
        <a href="/subarenda">Subarenda</a>
        <a href="{channel_link}" target="_blank">Telegram kanal</a>
        <a href="{bot_link}" target="_blank">Telegram bot</a>
        <a href="{INSTAGRAM_URL}" target="_blank">Instagram</a>
      </div>
    </div>
    <div class="footer-bottom">&copy; {year} {SITE_NAME}. Barcha huquqlar himoyalangan.</div>
  </div>
</footer>"""


def photo_url(file_id: str) -> str:
    base = SITE_URL or ""
    return f"{base}/photo/{file_id}"


CATEGORY_LABELS = {
    "tasdiqlangan": ("\u2705 Tasdiqlangan", "cat-verified"),
    "subarenda": ("\U0001F3E2 Subarenda", "cat-subarenda"),
    "premium": ("\U0001F48E Premium", "cat-premium"),
}


def render_listing_card(l: dict) -> str:
    photos = l.get("photos") or []
    img = photo_url(photos[0]) if photos else ""
    img_html = f'<img src="{img}" alt="{esc_html(display_address(l))}" loading="lazy">' if img else f'<div class="lc-placeholder">{icon("home", 34)}</div>'
    paid_badge = f'<span class="lc-badge lc-badge-fire">{icon("bolt", 13)} TOP</span>' if (l.get("price_charged") or 0) > 0 else ""
    cat = l.get("category")
    cat_badge = ""
    if cat and cat in CATEGORY_LABELS:
        label, css_cls = CATEGORY_LABELS[cat]
        cat_badge = f'<span class="lc-badge {css_cls}" style="{"left:auto;right:10px;" if paid_badge else ""}">{label}</span>'
    xona = (l.get("xona") or "").strip()
    kimlarga = (l.get("kimlarga") or "").strip()
    meta_parts = []
    if xona:
        meta_parts.append(f'{icon("bed", 14)} {esc_html(xona)}')
    if kimlarga:
        meta_parts.append(f'{icon("users", 14)} {esc_html(kimlarga[:16])}')
    meta_html = f'<div class="lc-meta">{" &nbsp;·&nbsp; ".join(meta_parts)}</div>' if meta_parts else ""
    return f"""<a href="/uy/{l['id']}" class="listing-card">
  <div class="lc-photo">
    {img_html}
    {paid_badge}
    {cat_badge}
  </div>
  <div class="lc-body">
    <div class="lc-top">
      <div class="lc-title">{esc_html(display_address(l))}</div>
    </div>
    {meta_html}
    <div class="lc-price">{esc_html(l.get('narx') or '')}</div>
  </div>
</a>"""


ICONS = {
    "bed": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18v-6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v6"/><path d="M3 18h18"/><path d="M7 10V7a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v3"/><path d="M3 14v4"/><path d="M21 14v4"/></svg>',
    "users": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1"/><circle cx="10" cy="8" r="3.5"/><path d="M21 20v-1a4 4 0 0 0-2.5-3.7"/><path d="M15.5 4.3a3.5 3.5 0 0 1 0 6.9"/></svg>',
    "pin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 10c0 5.5-7 11-7 11s-7-5.5-7-11a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2.5"/></svg>',
    "target": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z"/><path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"/></svg>',
    "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/></svg>',
    "shield": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21c4.5-1.5 7.5-5.5 7.5-10.5V6l-7.5-3-7.5 3v4.5C4.5 15.5 7.5 19.5 12 21Z"/><path d="m9 12 2 2 4-4.5"/></svg>',
    "bolt": '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12.6 1.4 3.3 13.5c-.4.5 0 1.3.7 1.3h6.1l-1.6 7.5c-.2.9.9 1.5 1.5.8l9.7-12.4c.4-.5 0-1.3-.7-1.3h-6.3l1.7-7.2c.2-.9-1-1.5-1.7-.8Z"/></svg>',
    "map": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4Z"/><path d="M9 4v14"/><path d="M15 6v14"/></svg>',
    "coin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M15 9.5c-.5-.8-1.5-1.3-3-1.3-2 0-3.2 1-3.2 2.3 0 3 6 1.3 6 4.3 0 1.4-1.3 2.4-3.2 2.4-1.5 0-2.6-.5-3.2-1.3"/><path d="M12 6.5v11"/></svg>',
    "phone": '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M6.6 10.8c1.4 2.7 3.6 4.9 6.3 6.3l2.1-2.1c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1-9.4 0-17-7.6-17-17 0-.6.4-1 1-1h3.6c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.4 0 .8-.2 1L6.6 10.8Z"/></svg>',
    "share": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><path d="M16 6l-4-4-4 4"/><path d="M12 2v14"/></svg>',
    "copy": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="13" height="13" rx="2.5"/><path d="M16 8V5.5A2.5 2.5 0 0 0 13.5 3h-8A2.5 2.5 0 0 0 3 5.5v8A2.5 2.5 0 0 0 5.5 16H8"/></svg>',
    "chevron_left": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>',
    "chevron_right": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>',
    "home": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9a1 1 0 0 0 1 1h3v-6h4v6h3a1 1 0 0 0 1-1v-9"/></svg>',
    "check_circle": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 5-5.5"/></svg>',
    "sparkle": '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 2.5c.3 3 1 5.2 2.3 6.5s3.5 2 6.5 2.3c-3 .3-5.2 1-6.5 2.3s-2 3.5-2.3 6.5c-.3-3-1-5.2-2.3-6.5S6.2 11.6 3.2 11.3c3-.3 5.2-1 6.5-2.3S11.7 5.5 12 2.5Z"/></svg>',
    "camera_off": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4l16 16"/><path d="M9.5 4.5H14l1.3 2H18a2 2 0 0 1 2 2v8.8"/><path d="M18.6 18.6a2 2 0 0 1-.6.1H5a2 2 0 0 1-2-2V8.5a2 2 0 0 1 2-2h.4"/><circle cx="12" cy="13" r="3.2"/></svg>',
    "sad": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="9" cy="10" r="0.9" fill="currentColor" stroke="none"/><circle cx="15" cy="10" r="0.9" fill="currentColor" stroke="none"/><path d="M8.5 16c1-1.2 2.2-1.8 3.5-1.8s2.5.6 3.5 1.8"/></svg>',
    "close": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>',
    "expand": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M21 16v3a2 2 0 0 1-2 2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/></svg>',
    "send": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 3 11 13"/><path d="M21 3 14.5 21a.4.4 0 0 1-.7 0L11 13l-8-2.8a.4.4 0 0 1 0-.7L21 3Z"/></svg>',
    "instagram": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.2" cy="6.8" r="0.6" fill="currentColor" stroke="none"/></svg>',
    "menu": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/></svg>',
    "message": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5c-1.2 0-2.3-.2-3.4-.7L3 21l1.7-4.6A8.5 8.5 0 1 1 21 11.5Z"/></svg>',
}


def icon(name: str, size: int = 18) -> str:
    svg = ICONS.get(name, "")
    return f'<span class="ico" style="width:{size}px;height:{size}px;">{svg}</span>'


def esc_html(s) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


# ============================= BOSH SAHIFA =============================

@app.get("/", response_class=HTMLResponse)
def homepage(hudud: str = Query(""), xona: str = Query(""), page: int = Query(1, ge=1)):
    listings, total = get_site_listings(hudud=hudud, xona=xona, page=page)
    stats = site_stats_summary()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    district_options = "".join(
        f'<option value="{d}" {"selected" if d.lower() == hudud.lower() else ""}>{d}</option>'
        for d in TASHKENT_DISTRICTS
    )

    if listings:
        cards_html = "".join(render_listing_card(l) for l in listings)
    else:
        cards_html = f"""<div class="empty-state" style="grid-column:1/-1;">
            <div class="icon">{icon('search', 40)}</div>
            <div>Hech qanday e'lon topilmadi. Boshqa filtrni sinab ko'ring.</div>
        </div>"""

    pag_html = ""
    if total_pages > 1:
        def page_url(p):
            return f"?page={p}" + (f"&hudud={hudud}" if hudud else "") + (f"&xona={xona}" if xona else "")

        WINDOW = 5
        start_p = max(1, min(page - WINDOW // 2, total_pages - WINDOW + 1))
        end_p = min(total_pages, start_p + WINDOW - 1)
        start_p = max(1, end_p - WINDOW + 1)

        links = []
        if page > 1:
            links.append(f'<a href="{page_url(page-1)}" class="pg-arrow">{icon("chevron_left", 15)}</a>')
        for p in range(start_p, end_p + 1):
            if p == page:
                links.append(f'<span class="active">{p}</span>')
            else:
                links.append(f'<a href="{page_url(p)}">{p}</a>')
        if page < total_pages:
            links.append(f'<a href="{page_url(page+1)}" class="pg-arrow">{icon("chevron_right", 15)}</a>')
        pag_html = f'<div class="pagination">{"".join(links)}</div>'

    title = f"{SITE_NAME} — Toshkentda uy, kvartira ijarasi (maklersiz)"
    description = f"Toshkentda maklersiz uy va kvartira ijarasi. Hozirda {stats['active']} ta faol e'lon. To'g'ridan-to'g'ri uy egasi bilan bog'laning, komissiyasiz."

    html = f"""<!DOCTYPE html>
<html lang="uz">
<head>
{render_head(title, description, "/")}
</head>
<body>
{render_header()}

<section class="hero">
  <div class="wrap">
    <h1>Maklersiz uy ijarasi Toshkentda</h1>
    <p class="sub">To'g'ridan-to'g'ri uy egasi bilan bog'laning — hech qanday makler haqqi to'lamang</p>
    <form class="search-pill" method="get" action="/">
      <div class="seg">
        <label>HUDUD</label>
        <select name="hudud">
          <option value="">Barcha hududlar</option>
          {district_options}
        </select>
      </div>
      <div class="seg">
        <label>XONALAR SONI</label>
        <select name="xona">
          <option value="">Farqi yo'q</option>
          <option value="1" {"selected" if xona=="1" else ""}>1 xona</option>
          <option value="2" {"selected" if xona=="2" else ""}>2 xona</option>
          <option value="3" {"selected" if xona=="3" else ""}>3 xona</option>
          <option value="4" {"selected" if xona=="4" else ""}>4+ xona</option>
        </select>
      </div>
      <button type="submit">{icon('search', 16)} Qidirish</button>
    </form>
  </div>
</section>

<div class="stats-strip">
  <div class="wrap">
    <div class="inner">
      <div class="stat-item"><div class="num">{stats['active']}+</div><div class="lbl">Faol e'lon</div></div>
      <div class="stat-item"><div class="num">{stats['users']}+</div><div class="lbl">Foydalanuvchi</div></div>
      <div class="stat-item"><div class="num">100%</div><div class="lbl">Maklersiz</div></div>
    </div>
  </div>
</div>

<main class="wrap">
  <div class="section-head">
    <h2>{"Qidiruv natijalari" if (hudud or xona) else "So'nggi e'lonlar"}</h2>
    <span class="count">{total} ta e'lon topildi</span>
  </div>
  <div class="listing-grid">
    {cards_html}
  </div>
  {pag_html}
</main>

<section class="why-section">
  <div class="wrap">
    <div class="section-head"><h2>Nega bizni tanlashadi</h2></div>
    <div class="why-grid">
      <div class="why-item"><div class="icon">{icon('coin', 26)}</div><h3>Maklersiz</h3><p>Hech qanday komissiya yoki vositachi haqqi yo'q</p></div>
      <div class="why-item"><div class="icon">{icon('shield', 26)}</div><h3>Tekshirilgan</h3><p>Har bir e'lon moderatsiyadan o'tadi, firibgarlar bloklanadi</p></div>
      <div class="why-item"><div class="icon">{icon('bolt', 26)}</div><h3>Tezkor</h3><p>Bot orqali bir necha soniyada uy egasi bilan bog'laning</p></div>
      <div class="why-item"><div class="icon">{icon('map', 26)}</div><h3>Xaritada</h3><p>Uylarni interaktiv xaritada joylashuvi bo'yicha toping</p></div>
    </div>
  </div>
</section>

{render_footer()}
</body>
</html>"""
    return HTMLResponse(html)


# ============================= E'LON SAHIFASI =============================

@app.get("/uy/{listing_id}", response_class=HTMLResponse)
def listing_detail(listing_id: int):
    l = get_site_listing(listing_id)
    if not l:
        not_found_head = render_head("E'lon topilmadi", "Bu e'lon topilmadi yoki muddati tugagan", f"/uy/{listing_id}")
        not_found_body = (
            f"<body>{render_header()}<main class='wrap'><div class='empty-state'>{icon('sad', 46)}"
            f"<div style='margin-top:10px;'>Bu e'lon topilmadi yoki muddati tugagan.</div><br>"
            f"<a href='/' class='btn-cta' style='background:#0f1b2e;'>Bosh sahifaga qaytish</a></div></main>{render_footer()}</body>"
        )
        return HTMLResponse(
            f"<!DOCTYPE html><html><head>{not_found_head}</head>{not_found_body}</html>",
            status_code=404,
        )

    addr = display_address(l)
    photos = l.get("photos") or []
    photo_urls = [photo_url(p) for p in photos]
    main_photo = photo_urls[0] if photo_urls else ""

    is_quick = bool(l.get("is_quick"))
    moljal = (l.get("moljal") or "").strip()
    xona = (l.get("xona") or "").strip()
    kimlarga = (l.get("kimlarga") or "").strip()
    qulaylik = (l.get("qulaylik") or "").strip()
    description_text = qulaylik or (l.get("raw_text") or "").strip() or "Qo'shimcha ma'lumot berilmagan."

    # ---- Svayp qilinadigan (mobil uchun tabiiy touch-swipe) rasm galereyasi + Lightbox ----
    if photo_urls:
        slides = "".join(f'<div class="gs-slide"><img src="{u}" alt="{esc_html(addr)}" loading="{"eager" if i==0 else "lazy"}" onclick="openLightbox({i})"></div>' for i, u in enumerate(photo_urls))
        dots = "".join(f'<span class="gs-dot{" active" if i==0 else ""}"></span>' for i in range(len(photo_urls))) if len(photo_urls) > 1 else ""
        counter = f'<div class="gs-counter">1 / {len(photo_urls)}</div>' if len(photo_urls) > 1 else ""
        arrows = ""
        if len(photo_urls) > 1:
            arrows = (
                f'<button class="gs-arrow gs-arrow-left" onclick="scrollGallery(-1)" aria-label="Oldingi">{icon("chevron_left", 20)}</button>'
                f'<button class="gs-arrow gs-arrow-right" onclick="scrollGallery(1)" aria-label="Keyingi">{icon("chevron_right", 20)}</button>'
            )
        expand_btn = f'<button class="gs-expand" onclick="openLightbox(gsCurrentIndex)" aria-label="Kattalashtirish">{icon("expand", 15)}</button>'
        gallery_html = f"""<div class="gallery-scroll" id="gallery">{slides}</div>
        {counter}
        {arrows}
        {expand_btn}
        <div class="gs-dots" id="gsDots">{dots}</div>"""
        lightbox_slides = "".join(f'<div class="lb-slide"><img src="{u}" alt="{esc_html(addr)}"></div>' for u in photo_urls)
        lightbox_nav = ""
        if len(photo_urls) > 1:
            lightbox_nav = (
                f'<button class="lb-arrow lb-arrow-left" onclick="lbNav(-1)" aria-label="Oldingi">{icon("chevron_left", 26)}</button>'
                f'<button class="lb-arrow lb-arrow-right" onclick="lbNav(1)" aria-label="Keyingi">{icon("chevron_right", 26)}</button>'
            )
        lightbox_html = f"""<div id="lightbox" class="lightbox">
          <button class="lb-close" onclick="closeLightbox()" aria-label="Yopish">{icon("close", 20)}</button>
          <div class="lb-track" id="lbTrack">{lightbox_slides}</div>
          {lightbox_nav}
        </div>"""
    else:
        gallery_html = f'<div class="gallery-scroll gs-empty">{icon("camera_off", 42)}<div style="margin-top:8px;font-size:13px;">Rasm yo\'q</div></div>'
        lightbox_html = ""

    bot_link = f"https://t.me/{BOT_USERNAME}?start=phone_{l['id']}" if BOT_USERNAME else "#"
    paid_badge = f'<span class="badge paid">{icon("bolt", 13)} TOP e\'lon</span>' if (l.get("price_charged") or 0) > 0 else ""
    cat = l.get("category")
    cat_badge_detail = ""
    if cat and cat in CATEGORY_LABELS:
        label, css_cls = CATEGORY_LABELS[cat]
        cat_badge_detail = f'<span class="badge {css_cls}">{label}</span>'

    map_html = ""
    if l.get("latitude") and l.get("longitude"):
        map_html = f"""<div id="detail-map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script>
  const dmap = L.map('detail-map', {{ zoomControl: false }}).setView([{l['latitude']}, {l['longitude']}], 15);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ attribution: '&copy; OpenStreetMap' }}).addTo(dmap);
  L.circleMarker([{l['latitude']}, {l['longitude']}], {{ radius: 10, fillColor: '#FF385C', color: '#fff', weight: 2, fillOpacity: 0.9 }}).addTo(dmap);
</script>"""

    related = get_related_listings(l["id"], l.get("manzil") or addr)
    related_html = ""
    if related:
        related_cards = "".join(render_listing_card(r) for r in related)
        related_html = f"""<div class="related-strip">
  <div class="section-head"><h2>O'xshash e'lonlar</h2></div>
  <div class="listing-grid">{related_cards}</div>
</div>"""

    facts_html = ""
    if xona:
        facts_html += f'<div class="fact-box"><div class="fl">Xonalar soni</div><div class="fv">{icon("bed", 16)} {esc_html(xona)}</div></div>'
    if kimlarga:
        facts_html += f'<div class="fact-box"><div class="fl">Kimlarga</div><div class="fv">{icon("users", 16)} {esc_html(kimlarga)}</div></div>'
    facts_block = f'<div class="detail-facts">{facts_html}</div>' if facts_html else ""
    moljal_block = f'<div class="detail-addr">{icon("target", 15)} {esc_html(moljal)}</div>' if moljal else ""

    title = f"{esc_html(addr)} \u2014 {esc_html(l['narx'])} | Ijaraga Uylar"
    description = f"{esc_html(xona or 'Ijaraga uy')}. Narxi: {esc_html(l['narx'])}. Maklersiz, to'g'ridan-to'g'ri uy egasi bilan bog'laning."

    json_ld = f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": {_json.dumps(addr)},
  "description": {_json.dumps(description_text[:300])},
  "image": {_json.dumps(photo_urls[0] if photo_urls else '')},
  "offers": {{
    "@type": "Offer",
    "availability": "https://schema.org/InStock",
    "priceCurrency": "USD",
    "price": "0"
  }}
}}
</script>"""

    html = f"""<!DOCTYPE html>
<html lang="uz">
<head>
{render_head(title, description, f"/uy/{listing_id}", main_photo)}
{json_ld}
</head>
<body>
{render_header()}
<main class="wrap">
  <div class="breadcrumb"><a href="/">Bosh sahifa</a> / {esc_html(addr)}</div>

  <div class="detail-grid">
    <div>
      <div class="gallery-wrap">{gallery_html}</div>
      {lightbox_html}

      <h1 class="detail-title">{esc_html(addr)}</h1>
      {moljal_block}
      <div class="detail-badges">
        {paid_badge}
        {cat_badge_detail}
        <span class="badge trust">{icon("check_circle", 13)} Tekshirilgan e'lon</span>
      </div>

      {facts_block}

      <div class="desc-block">
        <h3>{icon("sparkle", 16)} Tavsif</h3>
        <p>{esc_html(description_text)}</p>
      </div>

      {map_html}
    </div>

    <div>
      <div class="sidebar-card">
        <div class="sidebar-price">{esc_html(l['narx'])}</div>
        <a href="{bot_link}" class="sidebar-cta" target="_blank">{icon("phone", 16)} Telefon raqamini olish</a>
        <div class="sidebar-note">Telegram bot orqali xavfsiz va tez</div>
        <div class="sidebar-share">
          <button onclick="shareListing()">{icon("share", 14)} Ulashish</button>
          <button onclick="copyLink(this)">{icon("copy", 14)} Nusxalash</button>
        </div>

        <div class="inquiry-toggle" onclick="toggleInquiry()">
          {icon("message", 15)} <span>Uy egasiga so'rov yuborish</span>
        </div>
        <form id="inquiryForm" class="inquiry-form" onsubmit="return submitInquiry(event)">
          <input required name="name" placeholder="Ismingiz" maxlength="100">
          <input required name="phone" placeholder="Telefon raqamingiz" maxlength="30">
          <textarea name="message" placeholder="Xabar (ixtiyoriy)" maxlength="500" rows="3"></textarea>
          <button type="submit" class="inquiry-submit">{icon("send", 14)} Yuborish</button>
          <div id="inquirySuccess" class="inquiry-success">{icon("check_circle", 15)} So'rovingiz yuborildi!</div>
        </form>
      </div>
    </div>
  </div>

  {related_html}
</main>

<script>
function toggleInquiry() {{
  document.getElementById('inquiryForm').classList.toggle('open');
}}
async function submitInquiry(e) {{
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form).entries());
  data.listing_id = {l['id']};
  const btn = form.querySelector('.inquiry-submit');
  btn.disabled = true;
  try {{
    const res = await fetch('/api/listing-inquiry', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(data)
    }});
    if (res.ok) {{
      form.querySelectorAll('input, textarea, button').forEach(el => el.style.display = 'none');
      document.getElementById('inquirySuccess').style.display = 'flex';
    }} else {{
      alert("Xatolik yuz berdi, qaytadan urinib ko'ring.");
      btn.disabled = false;
    }}
  }} catch (err) {{
    alert("Xatolik yuz berdi, qaytadan urinib ko'ring.");
    btn.disabled = false;
  }}
  return false;
}}
</script>
{render_footer()}

<script>
function shareListing() {{
  if (navigator.share) {{
    navigator.share({{ title: document.title, url: window.location.href }});
  }} else {{
    navigator.clipboard.writeText(window.location.href);
    alert("Havola nusxalandi!");
  }}
}}
function copyLink(btn) {{
  navigator.clipboard.writeText(window.location.href);
  const original = btn.innerHTML;
  btn.textContent = "\u2705 Nusxalandi";
  setTimeout(() => btn.innerHTML = original, 1800);
}}

let gsCurrentIndex = 0;
function scrollGallery(dir) {{
  const gallery = document.getElementById('gallery');
  if (!gallery) return;
  gallery.scrollBy({{ left: dir * gallery.clientWidth, behavior: 'smooth' }});
}}
function openLightbox(idx) {{
  const lb = document.getElementById('lightbox');
  if (!lb) return;
  lbIndex = idx;
  document.getElementById('lbTrack').style.transform = 'translateX(-' + (idx * 100) + '%)';
  lb.classList.add('open');
  document.body.style.overflow = 'hidden';
}}
function closeLightbox() {{
  const lb = document.getElementById('lightbox');
  if (!lb) return;
  lb.classList.remove('open');
  document.body.style.overflow = '';
}}
let lbIndex = 0;
function lbNav(dir) {{
  const slides = document.querySelectorAll('.lb-slide');
  if (!slides.length) return;
  lbIndex = (lbIndex + dir + slides.length) % slides.length;
  document.getElementById('lbTrack').style.transform = 'translateX(-' + (lbIndex * 100) + '%)';
}}
document.addEventListener('keydown', (e) => {{
  const lb = document.getElementById('lightbox');
  if (!lb || !lb.classList.contains('open')) return;
  if (e.key === 'Escape') closeLightbox();
  if (e.key === 'ArrowLeft') lbNav(-1);
  if (e.key === 'ArrowRight') lbNav(1);
}});

(function() {{
  const gallery = document.getElementById('gallery');
  if (!gallery) return;
  const dots = document.querySelectorAll('#gsDots .gs-dot');
  const counterEl = document.querySelector('.gs-counter');
  const slideCount = dots.length;
  gallery.addEventListener('scroll', () => {{
    const idx = Math.round(gallery.scrollLeft / gallery.clientWidth);
    gsCurrentIndex = idx;
    dots.forEach((d, i) => d.classList.toggle('active', i === idx));
    if (counterEl) counterEl.textContent = (idx + 1) + ' / ' + slideCount;
  }}, {{ passive: true }});
}})();
</script>
</body>
</html>"""
    return HTMLResponse(html)


# ============================= SEO: SITEMAP VA ROBOTS =============================

# ============================= SUBARENDA =============================

@app.get("/subarenda", response_class=HTMLResponse)
def subarenda_page():
    title = f"Subarenda dasturi — {SITE_NAME}"
    description = "Uyingizni bizga uzoq muddatli ijaraga bering - biz ijarachini topamiz, boshqaramiz va sizga har oy kafolatlangan to'lovni amalga oshiramiz."
    html = f"""<!DOCTYPE html>
<html lang="uz">
<head>
{render_head(title, description, "/subarenda")}
</head>
<body>
{render_header()}
<section class="hero">
  <div class="wrap">
    <h1>Uyingizni bizga ishoning</h1>
    <p class="sub">Ijarachi qidirish, shartnoma va oylik to'lovlar bilan bosh og'rig'ini unuting — biz hammasini boshqaramiz, sizga esa har oy kafolatlangan ijara puli keladi.</p>
  </div>
</section>
<main class="wrap" style="padding-top:40px;">
  <div class="why-grid" style="margin-bottom:50px;">
    <div class="why-item"><div class="icon">{icon('users', 26)}</div><h3>Ijarachi biz tomondan</h3><p>Sizga ijarachi izlashning hojati yo'q - buni to'liq biz bajaramiz</p></div>
    <div class="why-item"><div class="icon">{icon('coin', 26)}</div><h3>Kafolatlangan to'lov</h3><p>Uy bo'sh tursa ham, kelishilgan summa har oy sizga to'lanadi</p></div>
    <div class="why-item"><div class="icon">{icon('shield', 26)}</div><h3>Rasmiy shartnoma</h3><p>Barcha jarayon yozma shartnoma asosida, qonuniy tartibda amalga oshiriladi</p></div>
    <div class="why-item"><div class="icon">{icon('sparkle', 26)}</div><h3>Uy holatini nazorat</h3><p>Uyingiz muntazam tekshiriladi, muammolar tezkor hal qilinadi</p></div>
  </div>

  <div style="max-width:520px;margin:0 auto;">
    <div class="sidebar-card" style="position:static;">
      <h2 style="font-size:19px;font-weight:800;margin-bottom:6px;">Ariza qoldiring</h2>
      <p style="font-size:13px;color:var(--muted);margin-bottom:18px;">Mutaxassisimiz 24 soat ichida siz bilan bog'lanadi</p>
      <form id="subarenda-form" onsubmit="return submitSubarenda(event)">
        <div style="margin-bottom:12px;">
          <input required name="full_name" placeholder="Ismingiz" style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;">
        </div>
        <div style="margin-bottom:12px;">
          <input required name="phone" placeholder="Telefon raqamingiz (+998...)" style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;">
        </div>
        <div style="margin-bottom:12px;">
          <input required name="manzil" placeholder="Uy manzili (tuman, mahalla)" style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;">
        </div>
        <div style="margin-bottom:12px;">
          <input name="xona" placeholder="Xonalar soni" style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;">
        </div>
        <div style="margin-bottom:18px;">
          <input name="narx_talab" placeholder="Kutilayotgan oylik narx ($ yoki so'm)" style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;">
        </div>
        <button type="submit" class="sidebar-cta" style="width:100%;border:none;cursor:pointer;">Arizani yuborish</button>
      </form>
      <div id="subarenda-success" style="display:none;text-align:center;padding:20px 0;">
        <div style="font-size:40px;margin-bottom:10px;">✅</div>
        <div style="font-weight:700;margin-bottom:6px;">Arizangiz qabul qilindi!</div>
        <div style="font-size:13px;color:var(--muted);">Tez orada siz bilan bog'lanamiz.</div>
      </div>
    </div>
  </div>
</main>
{render_footer()}
<script>
async function submitSubarenda(e) {{
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form).entries());
  const res = await fetch('/api/subarenda-lead', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(data)
  }});
  if (res.ok) {{
    form.style.display = 'none';
    document.getElementById('subarenda-success').style.display = 'block';
  }} else {{
    alert("Xatolik yuz berdi, qaytadan urinib ko'ring.");
  }}
  return false;
}}
</script>
</body>
</html>"""
    return HTMLResponse(html)


# ============================= VEB-SAYTDAN E'LON JOYLASH SAHIFASI =============================

@app.get("/elon-joylash", response_class=HTMLResponse)
def elon_joylash_page():
    title = f"Bepul e'lon joylash — {SITE_NAME}"
    description = "Uyingizni ijaraga berasizmi? Veb-saytdan to'g'ridan-to'g'ri, ro'yxatdan o'tmasdan bepul e'lon joylang — avtomatik moderatsiyadan so'ng Telegram kanalimiz va saytimizda chiqadi."
    price = current_listing_price()
    card = current_card_number()
    card_grouped = " ".join(re.sub(r"\D", "", card)[i:i + 4] for i in range(0, len(re.sub(r"\D", "", card)), 4)) if card else ""

    html = f"""<!DOCTYPE html>
<html lang="uz">
<head>
{render_head(title, description, "/elon-joylash")}
</head>
<body>
{render_header()}

<section class="form-page-hero">
  <div class="wrap">
    <h1>{icon('sparkle', 26)} Uyingizni ijaraga bering</h1>
    <p>Formani to'ldiring — e'loningiz tekshirilgach, avtomatik ravishda Telegram kanalimizda va shu saytda e'lon qilinadi. Ro'yxatdan o'tish shart emas.</p>
  </div>
</section>

<main class="wrap">
  <div class="form-shell">
    <div class="form-card">
      <div id="formStep">
        <div class="fstep-badge">{icon('shield', 13)} Har bir e'lon qo'lda tekshiriladi — firibgarlarga joy yo'q</div>
        <div id="formError" class="form-error-box"></div>

        <form id="listingForm">
          <div class="form-section-title">{icon('home', 17)} Uy haqida</div>
          <div class="form-group">
            <label>Manzil (tuman, mahalla) <span class="req">*</span></label>
            <input class="form-input" name="manzil" maxlength="250" required placeholder="Masalan: Yunusobod, 12-kvartal">
          </div>
          <div class="form-group">
            <label>Mo'ljal <span class="req">*</span></label>
            <input class="form-input" name="moljal" maxlength="250" required placeholder="Masalan: Metro bekatiga yaqin, Korzinka yonida">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Nechta xonali? <span class="req">*</span></label>
              <input class="form-input" name="xona" maxlength="60" required placeholder="Masalan: 2 xona, studio">
            </div>
            <div class="form-group">
              <label>Kimlarga beriladi? <span class="req">*</span></label>
              <input class="form-input" name="kimlarga" maxlength="150" required placeholder="Masalan: oilaga, talabalarga">
            </div>
          </div>
          <div class="form-group">
            <label>Sharoitlari <span class="req">*</span></label>
            <textarea class="form-textarea" name="qulaylik" maxlength="900" required placeholder="Masalan: ta'mirlangan, mebel bilan, isitish tizimi bor..."></textarea>
          </div>
          <div class="form-group">
            <label>Narxi <span class="req">*</span></label>
            <input class="form-input" name="narx" maxlength="200" required placeholder="Masalan: 150$, 1.2 mln, kelishiladi">
          </div>

          <div class="form-section-title">{icon('phone', 17)} Aloqa</div>
          <div class="form-row">
            <div class="form-group">
              <label>Ismingiz</label>
              <input class="form-input" name="full_name" maxlength="100" placeholder="Ixtiyoriy">
            </div>
            <div class="form-group">
              <label>Telefon raqami <span class="req">*</span></label>
              <input class="form-input" name="telefon" maxlength="30" required placeholder="+998 90 123 45 67">
            </div>
          </div>
          <div class="form-hint" style="margin:-8px 0 14px;">Bu raqam e'londa ko'rsatiladi — ijarachilar shu orqali siz bilan bog'lanadi.</div>

          <div class="form-section-title">{icon('map', 17)} Joylashuv (ixtiyoriy)</div>
          <div class="loc-toggle-row">
            <div class="lt-label">{icon('target', 15)} Xaritada aniq nuqtani belgilash</div>
            <label class="switch"><input type="checkbox" id="locToggle"><span class="slider"></span></label>
          </div>
          <div id="locationMap"></div>
          <input type="hidden" name="latitude" id="latInput">
          <input type="hidden" name="longitude" id="lonInput">

          <div class="form-section-title">{icon('camera_off', 17)} Rasmlar <span class="req">*</span></div>
          <div class="photo-drop" id="photoDrop">
            <div class="ico" style="width:30px;height:30px;margin:0 auto;color:var(--muted);">{ICONS['camera_off']}</div>
            <div class="pd-title">Rasmlarni shu yerga bosing yoki tashlang</div>
            <div class="pd-sub">1 dan 10 tagacha, har biri 10MB gacha</div>
          </div>
          <input type="file" id="photoInput" accept="image/*" multiple hidden>
          <div class="photo-preview" id="photoPreview"></div>

          <div class="form-section-title">{icon('coin', 17)} E'lon turi</div>
          <div class="type-toggle">
            <label class="type-option active" id="typeFree">
              <input type="radio" name="listing_type" value="free" checked>
              <div class="to-title">{icon('sparkle', 14)} Bepul</div>
              <div class="to-desc">Kanalga bir marta joylanadi, navbat asosida ko'rib chiqiladi.</div>
            </label>
            <label class="type-option" id="typePaid">
              <input type="radio" name="listing_type" value="paid">
              <div class="to-title">{icon('bolt', 14)} Pullik — {price:,} so'm</div>
              <div class="to-desc">Uyingiz topshirilguncha (kamida 7 kun) doim TOP'da — tezroq va ko'proq ko'rinadi.</div>
            </label>
          </div>

          <div class="pay-panel" id="payPanel">
            <div class="card-box">
              <div><div style="font-size:11px;color:var(--muted);font-weight:700;margin-bottom:3px;">TO'LOV KARTASI</div><div class="cb-num" id="cardNumText">{card_grouped or "—"}</div></div>
              <button type="button" onclick="copyCard()">{icon('copy', 12)} Nusxalash</button>
            </div>
            <div class="form-hint" style="margin-bottom:10px;">Yuqoridagi kartaga <b>{price:,} so'm</b> o'tkazing, so'ng chek skrinshotini yuklang.</div>
            <div class="photo-drop" id="receiptDrop" style="padding:16px;">
              <div class="pd-title" id="receiptLabel">To'lov chekini yuklash</div>
              <div class="pd-sub">Skrinshot yoki fotosurat</div>
            </div>
            <input type="file" id="receiptInput" accept="image/*" hidden>
          </div>

          <button type="submit" class="form-submit-btn" id="submitBtn">{icon('send', 16)} E'lonni yuborish</button>
          <div class="form-hint" style="text-align:center;margin-top:10px;">Yuborish orqali siz e'lon ma'lumotlarining to'g'riligini tasdiqlaysiz.</div>
        </form>
      </div>

      <div id="formSuccess" class="form-success-screen" style="display:none;">
        <div class="fs-icon">{icon('check_circle', 34)}</div>
        <h2>E'loningiz qabul qilindi!</h2>
        <p id="successText">Tez orada administrator tekshirib, tasdiqlaydi — shundan so'ng Telegram kanalimizda va saytda chiqadi.</p>
        <a href="/" class="btn-cta" style="display:inline-flex;margin-top:20px;">Bosh sahifaga qaytish</a>
      </div>
    </div>
  </div>
</main>

<div style="height:60px;"></div>
{render_footer()}

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
// ---- Rasm tanlash / oldindan ko'rish ----
let selectedPhotos = [];
const photoInput = document.getElementById('photoInput');
const photoDrop = document.getElementById('photoDrop');
const photoPreview = document.getElementById('photoPreview');

photoDrop.addEventListener('click', () => photoInput.click());
['dragover', 'dragleave', 'drop'].forEach(evt => {{
  photoDrop.addEventListener(evt, (e) => {{
    e.preventDefault();
    photoDrop.classList.toggle('dragover', evt === 'dragover');
    if (evt === 'drop') addPhotos(e.dataTransfer.files);
  }});
}});
photoInput.addEventListener('change', () => addPhotos(photoInput.files));

function addPhotos(fileList) {{
  for (const f of fileList) {{
    if (!f.type.startsWith('image/')) continue;
    if (selectedPhotos.length >= 10) break;
    selectedPhotos.push(f);
  }}
  renderPhotoPreview();
}}
function removePhoto(idx) {{
  selectedPhotos.splice(idx, 1);
  renderPhotoPreview();
}}
function renderPhotoPreview() {{
  photoPreview.innerHTML = selectedPhotos.map((f, i) => {{
    const url = URL.createObjectURL(f);
    return `<div class="photo-thumb"><img src="${{url}}"><button type="button" class="pt-remove" onclick="removePhoto(${{i}})">✕</button></div>`;
  }}).join('');
}}

// ---- Chek rasmi ----
let receiptFile = null;
const receiptInput = document.getElementById('receiptInput');
document.getElementById('receiptDrop').addEventListener('click', () => receiptInput.click());
receiptInput.addEventListener('change', () => {{
  if (receiptInput.files[0]) {{
    receiptFile = receiptInput.files[0];
    document.getElementById('receiptLabel').textContent = '✅ ' + receiptFile.name;
  }}
}});

// ---- Bepul / Pullik tanlash ----
const typeFree = document.getElementById('typeFree');
const typePaid = document.getElementById('typePaid');
const payPanel = document.getElementById('payPanel');
[typeFree, typePaid].forEach(el => {{
  el.addEventListener('click', () => {{
    typeFree.classList.toggle('active', el === typeFree);
    typePaid.classList.toggle('active', el === typePaid);
    payPanel.classList.toggle('show', el === typePaid);
  }});
}});
function copyCard() {{
  navigator.clipboard.writeText("{re.sub(r'[^0-9]', '', card)}");
}}

// ---- Lokatsiya xaritasi ----
let locMap = null, locMarker = null;
document.getElementById('locToggle').addEventListener('change', function() {{
  const mapEl = document.getElementById('locationMap');
  mapEl.classList.toggle('show', this.checked);
  if (this.checked && !locMap) {{
    setTimeout(() => {{
      locMap = L.map('locationMap').setView([41.311081, 69.240562], 12);
      L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ attribution: '&copy; OpenStreetMap' }}).addTo(locMap);
      locMap.on('click', (e) => setLocMarker(e.latlng.lat, e.latlng.lng));
      if (navigator.geolocation) {{
        navigator.geolocation.getCurrentPosition(
          (pos) => {{ locMap.setView([pos.coords.latitude, pos.coords.longitude], 15); }},
          () => {{}}
        );
      }}
    }}, 50);
  }} else if (!this.checked) {{
    document.getElementById('latInput').value = '';
    document.getElementById('lonInput').value = '';
  }}
}});
function setLocMarker(lat, lon) {{
  if (locMarker) locMap.removeLayer(locMarker);
  locMarker = L.marker([lat, lon]).addTo(locMap);
  document.getElementById('latInput').value = lat;
  document.getElementById('lonInput').value = lon;
}}

// ---- Yuborish ----
const form = document.getElementById('listingForm');
const errorBox = document.getElementById('formError');
form.addEventListener('submit', async function(e) {{
  e.preventDefault();
  errorBox.classList.remove('show');

  if (selectedPhotos.length === 0) {{
    errorBox.textContent = "Kamida 1 ta uy rasmini yuklang.";
    errorBox.classList.add('show');
    window.scrollTo({{ top: photoDrop.offsetTop - 100, behavior: 'smooth' }});
    return;
  }}
  const isPaid = typePaid.classList.contains('active');
  if (isPaid && !receiptFile) {{
    errorBox.textContent = "Pullik e'lon uchun to'lov chekining skrinshotini yuklang.";
    errorBox.classList.add('show');
    return;
  }}

  const submitBtn = document.getElementById('submitBtn');
  submitBtn.disabled = true;
  submitBtn.textContent = "Yuborilmoqda...";

  const fd = new FormData(form);
  selectedPhotos.forEach(f => fd.append('photos', f));
  if (isPaid && receiptFile) fd.append('receipt', receiptFile);

  try {{
    const res = await fetch('/api/elon-joylash', {{ method: 'POST', body: fd }});
    const data = await res.json().catch(() => ({{}}));
    if (res.ok && data.ok) {{
      document.getElementById('formStep').style.display = 'none';
      document.getElementById('formSuccess').style.display = 'block';
      document.getElementById('successText').textContent =
        `Tez orada administrator tekshirib, tasdiqlaydi — shundan so'ng Telegram kanalimizda va saytda chiqadi. E'lon raqami: #${{data.listing_id}}`;
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }} else {{
      errorBox.textContent = data.detail || "Xatolik yuz berdi. Qaytadan urinib ko'ring.";
      errorBox.classList.add('show');
      submitBtn.disabled = false;
      submitBtn.innerHTML = '{icon("send", 16)} E\\'lonni yuborish';
      window.scrollTo({{ top: errorBox.offsetTop - 100, behavior: 'smooth' }});
    }}
  }} catch (err) {{
    errorBox.textContent = "Internet aloqasida muammo. Qaytadan urinib ko'ring.";
    errorBox.classList.add('show');
    submitBtn.disabled = false;
    submitBtn.innerHTML = '{icon("send", 16)} E\\'lonni yuborish';
  }}
}});
</script>
</body>
</html>"""
    return HTMLResponse(html)


async def notify_telegram(chat_id: int, text: str):
    """Bot API orqali to'g'ridan-to'g'ri Telegram xabar yuboradi (BOT_TOKEN
    orqali) - dashboarddan botga alohida ulanishsiz."""
    if not BOT_TOKEN or not chat_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
    except Exception:
        pass


# ============================= VEB-SAYTDAN E'LON JOYLASH (bot bilan to'liq integratsiya) =============================
#
# G'oya: veb-saytdan kelgan e'lon ham AYNAN bot orqali kelgan e'lon kabi
# moderatsiya navbatiga tushadi. Buning uchun:
#   1) Yuklangan rasmlar Telegram Bot API orqali (asosiy admin chatiga) yuboriladi
#      va shu yerdan Telegram file_id olinadi - baza faqat shu ID'larni saqlaydi
#      (dashboard hech qanday faylni o'zida saqlamaydi, bot bilan bir xil format).
#   2) "listings" jadvaliga status='pending' bilan yoziladi.
#   3) Barcha adminlarga XUDDI botning o'ziga xos "Tasdiqlash/Rad etish" tugmalari
#      (callback_data: admin_approve_listing_ID / admin_reject_listing_ID) bilan
#      xabar yuboriladi - bu tugmalarni ishlaydigan bot.py jarayoni (u alohida,
#      lekin bir xil token bilan long-polling qilib turadi) avtomatik qabul qiladi
#      va tasdiqlansa - kanalga ham, shu tufayli saytga ham chiqadi.

def get_setting(key: str, default: str = "") -> str:
    conn = db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row and row["value"] is not None else default


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


def is_phone_blocked(phone: str) -> bool:
    conn = db()
    row = conn.execute("SELECT 1 FROM blocked_phones WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    return row is not None


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


async def telegram_upload_photos(chat_id: int, contents: list, filenames: list) -> list:
    """Rasm baytlarini BIR MARTA Telegram'ga yuklab, file_id ro'yxatini qaytaradi.
    Shu file_id'lar keyin boshqa istalgan chatga (boshqa adminlar, kanal) QAYTA
    yuklamasdan, faqat ID orqali yuborilishi mumkin - tezkor va tejamkor."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN sozlanmagan")
    file_ids = []
    async with httpx.AsyncClient(timeout=60) as client:
        if len(contents) == 1:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={"chat_id": str(chat_id)},
                files={"photo": (filenames[0], contents[0])},
            )
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("description", "Telegram xatoligi"))
            file_ids.append(data["result"]["photo"][-1]["file_id"])
        else:
            media, files = [], {}
            for i, (content, name) in enumerate(zip(contents, filenames)):
                key = f"photo{i}"
                media.append({"type": "photo", "media": f"attach://{key}"})
                files[key] = (name, content)
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup",
                data={"chat_id": str(chat_id), "media": _json.dumps(media)},
                files=files,
            )
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("description", "Telegram xatoligi"))
            for msg in data["result"]:
                photos = msg.get("photo") or []
                if photos:
                    file_ids.append(photos[-1]["file_id"])
    return file_ids


def _web_listing_caption(d: dict) -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    return (
        f"\U0001F3E0 <b>Ijaraga Uylar Maklersiz</b>\n\n"
        f"\U0001F4CD <b>Manzil:</b> {esc_html(d['manzil'])}\n"
        f"\U0001F3AF <b>Mo'ljal:</b> {esc_html(d['moljal'])}\n"
        f"\U0001F465 <b>Kimlarga:</b> {esc_html(d['kimlarga'])}\n"
        f"\U0001F6CF <b>Xonalar soni:</b> {esc_html(d['xona'])}\n\n"
        f"✅ <b>Qulayliklar:</b>\n{esc_html(d['qulaylik'])}\n\n"
        f"\U0001F4B0 <b>Narxi:</b> {esc_html(d['narx'])}\n\n"
        f"\U0001F4C5 {today}\n\n"
        f"@{CHANNEL_USERNAME} — uyingizni maklersiz bering va oling!"
    )


async def notify_admins_new_web_listing(listing_id: int, d: dict, file_ids: list, receipt_file_id, price_charged: int) -> None:
    if not ADMIN_IDS or not BOT_TOKEN:
        return
    caption = _web_listing_caption(d) + f"\n\n\U0001F194 E'lon raqami: #{listing_id}\n\U0001F310 Manba: <b>veb-sayt</b> orqali yuborilgan"
    sender_line = (
        f"\U0001F464 Yuboruvchi: {esc_html(d.get('full_name') or 'Nomsiz')} (veb-saytdan — Telegram akkaunti yo'q)\n"
        f"\U0001F4DE Bog'lanish uchun: {esc_html(d['telefon'])}\n"
        f"\U0001F4B0 To'lov qilingan summa: {price_charged:,} so'm\n"
        f"\U0001F194 E'lon: #{listing_id}\n\n"
        + ("\U0001F4B3 To'lov cheki yuqorida ↑ — tekshirib, qaror qabul qiling:"
           if receipt_file_id else "\U0001F193 Bu e'lon BEPUL tarifda yuborilgan (chek talab qilinmagan) — tekshirib, qaror qabul qiling:")
    )
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Tasdiqlash", "callback_data": f"admin_approve_listing_{listing_id}"},
        {"text": "❌ Rad etish", "callback_data": f"admin_reject_listing_{listing_id}"},
    ]]}
    async with httpx.AsyncClient(timeout=20) as client:
        for admin_id in ADMIN_IDS:
            try:
                if len(file_ids) == 1:
                    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                       json={"chat_id": admin_id, "photo": file_ids[0]})
                elif file_ids:
                    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup",
                                       json={"chat_id": admin_id, "media": [{"type": "photo", "media": fid} for fid in file_ids]})
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                   json={"chat_id": admin_id, "text": caption, "parse_mode": "HTML"})
                if receipt_file_id:
                    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                       json={"chat_id": admin_id, "photo": receipt_file_id, "caption": sender_line,
                                             "parse_mode": "HTML", "reply_markup": keyboard})
                else:
                    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                       json={"chat_id": admin_id, "text": sender_line, "parse_mode": "HTML", "reply_markup": keyboard})
            except Exception:
                logger.exception("Web e'lon haqida adminga (%s) xabar yuborib bo'lmadi", admin_id)


@app.post("/api/elon-joylash")
async def submit_web_listing(
    request: Request,
    full_name: str = Form(""),
    telefon: str = Form(...),
    manzil: str = Form(...),
    moljal: str = Form(...),
    kimlarga: str = Form(...),
    xona: str = Form(...),
    qulaylik: str = Form(...),
    narx: str = Form(...),
    listing_type: str = Form("free"),
    latitude: str = Form(""),
    longitude: str = Form(""),
    photos: list[UploadFile] = File(...),
    receipt: UploadFile = File(None),
):
    ip = _client_ip(request)
    if web_submissions_today(ip) >= MAX_WEB_SUBMISSIONS_PER_IP_PER_DAY:
        raise HTTPException(status_code=429, detail="Kunlik e'lon yuborish limitiga yetdingiz. Ertaga qayta urinib ko'ring yoki Telegram bot orqali yuboring.")

    def clip(s, n):
        return (s or "").strip()[:n]

    manzil, moljal = clip(manzil, 250), clip(moljal, 250)
    kimlarga, xona = clip(kimlarga, 150), clip(xona, 60)
    qulaylik, narx = clip(qulaylik, 900), clip(narx, 200)
    full_name = clip(full_name, 100) or "Veb-sayt orqali"
    if not all([manzil, moljal, kimlarga, xona, qulaylik, narx]):
        raise HTTPException(status_code=400, detail="Iltimos, barcha majburiy maydonlarni to'ldiring.")

    phone = normalize_phone_web(telefon)
    if not phone:
        raise HTTPException(status_code=400, detail="Telefon raqami noto'g'ri formatda. Masalan: +998901234567")
    if is_phone_blocked(phone):
        raise HTTPException(status_code=400, detail="Bu raqam bilan e'lon joylashtirib bo'lmaydi. Savollar bo'lsa, adminga murojaat qiling.")

    valid_photos = [p for p in (photos or []) if p and p.filename]
    if not (1 <= len(valid_photos) <= MAX_WEB_LISTING_PHOTOS):
        raise HTTPException(status_code=400, detail=f"1 dan {MAX_WEB_LISTING_PHOTOS} tagacha uy rasmini yuklang.")

    photo_bytes, photo_names = [], []
    for p in valid_photos:
        content = await p.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Har bir rasm 10MB dan oshmasligi kerak.")
        photo_bytes.append(content)
        photo_names.append(p.filename or "rasm.jpg")

    is_paid = listing_type == "paid"
    receipt_bytes = None
    if is_paid:
        if not receipt or not receipt.filename:
            raise HTTPException(status_code=400, detail="Pullik e'lon uchun to'lov chekining skrinshotini yuklang.")
        receipt_bytes = await receipt.read()
        if len(receipt_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Chek rasmi 10MB dan oshmasligi kerak.")

    if not ADMIN_IDS or not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Tizim vaqtincha sozlanmoqda. Iltimos, birozdan so'ng qaytadan urinib ko'ring.")

    upload_chat_id = ADMIN_IDS[0]
    try:
        file_ids = await telegram_upload_photos(upload_chat_id, photo_bytes, photo_names)
    except Exception:
        logger.exception("Web e'londan rasm yuklashda xatolik")
        raise HTTPException(status_code=502, detail="Rasmlarni yuklashda xatolik yuz berdi. Birozdan so'ng qaytadan urinib ko'ring.")
    if not file_ids:
        raise HTTPException(status_code=502, detail="Rasmlarni yuklab bo'lmadi. Qaytadan urinib ko'ring.")

    receipt_file_id = None
    if receipt_bytes:
        try:
            r_ids = await telegram_upload_photos(upload_chat_id, [receipt_bytes], ["chek.jpg"])
            receipt_file_id = r_ids[0] if r_ids else None
        except Exception:
            logger.exception("Web e'lon chekini yuklashda xatolik")

    price_charged = current_listing_price() if is_paid else 0

    lat = lon = None
    try:
        if latitude and longitude:
            lat, lon = float(latitude), float(longitude)
    except ValueError:
        lat = lon = None

    conn = db()
    cur = conn.execute(
        """INSERT INTO listings
            (user_id, username, full_name, sender_phone, manzil, moljal, kimlarga, xona,
             qulaylik, narx, telefon, photos, payment_receipt, price_charged, status, created_at,
             latitude, longitude, category, source)
           VALUES (0, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, 'egadan', 'web')""",
        (full_name, phone, manzil, moljal, kimlarga, xona, qulaylik, narx, phone,
         _json.dumps(file_ids), receipt_file_id, price_charged, now_str(), lat, lon),
    )
    conn.commit()
    listing_id = cur.lastrowid
    conn.close()
    record_web_submission(ip)

    d = {"manzil": manzil, "moljal": moljal, "kimlarga": kimlarga, "xona": xona,
         "qulaylik": qulaylik, "narx": narx, "full_name": full_name, "telefon": phone}
    try:
        await notify_admins_new_web_listing(listing_id, d, file_ids, receipt_file_id, price_charged)
    except Exception:
        logger.exception("Web e'lon uchun adminlarga umumiy xabar yuborishda xatolik")

    return {"ok": True, "listing_id": listing_id}


@app.post("/api/listing-inquiry")
async def submit_listing_inquiry(request: Request):
    data = await request.json()
    listing_id = data.get("listing_id")
    name = (data.get("name") or "").strip()[:100]
    phone = (data.get("phone") or "").strip()[:30]
    message = (data.get("message") or "").strip()[:500]
    if not listing_id or not name or not phone:
        raise HTTPException(status_code=400, detail="Majburiy maydonlar to'ldirilmagan")

    conn = db()
    row = conn.execute("SELECT user_id, manzil, raw_text FROM listings WHERE id = ?", (listing_id,)).fetchone()
    owner_id = row["user_id"] if row else None
    addr = (row["manzil"] if row and row["manzil"] else extract_district(row["raw_text"] if row else "")) if row else "e'lon"
    conn.execute(
        "INSERT INTO listing_inquiries (listing_id, owner_user_id, name, phone, message, status, created_at) VALUES (?,?,?,?,?,'yangi',?)",
        (listing_id, owner_id, name, phone, message, now_str()),
    )
    conn.commit()
    conn.close()

    notify_text = (
        f"\U0001F4E9 <b>Saytdan yangi so'rov!</b>\n\n"
        f"\U0001F3E0 E'lon: {esc_html(addr)} (#{listing_id})\n"
        f"\U0001F464 Ism: {esc_html(name)}\n"
        f"\U0001F4DE Telefon: {esc_html(phone)}\n"
        + (f"\U0001F4AC Xabar: {esc_html(message)}\n" if message else "")
    )
    if owner_id:
        await notify_telegram(owner_id, notify_text)
    for admin_id_str in (os.getenv("ADMIN_IDS", "") or "").split(","):
        admin_id_str = admin_id_str.strip()
        if admin_id_str.isdigit():
            await notify_telegram(int(admin_id_str), notify_text)

    return {"ok": True}


@app.get("/api/listing-inquiries")
def get_listing_inquiries(user: str = Depends(check_auth)):
    conn = db()
    rows = conn.execute(
        """SELECT li.*, l.manzil as listing_manzil FROM listing_inquiries li
           LEFT JOIN listings l ON l.id = li.listing_id ORDER BY li.id DESC LIMIT 50"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/listing-inquiries/{inquiry_id}")
def update_listing_inquiry(inquiry_id: int, status: str = Query(...), user: str = Depends(check_auth)):
    if status not in ("yangi", "yopiq"):
        raise HTTPException(status_code=400)
    conn = db()
    conn.execute("UPDATE listing_inquiries SET status = ? WHERE id = ?", (status, inquiry_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/subarenda-lead")
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


@app.get("/api/subarenda-requests")
def get_subarenda_requests(user: str = Depends(check_auth)):
    conn = db()
    rows = conn.execute("SELECT * FROM subarenda_requests ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/subarenda-requests/{req_id}")
def update_subarenda_request(req_id: int, status: str = Query(...), user: str = Depends(check_auth)):
    if status not in ("yangi", "bogl", "yopiq"):
        raise HTTPException(status_code=400)
    conn = db()
    conn.execute("UPDATE subarenda_requests SET status = ? WHERE id = ?", (status, req_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/sitemap.xml")
def sitemap():
    conn = db()
    rows = conn.execute("SELECT id, created_at FROM listings WHERE status='approved' AND COALESCE(expired,0)=0").fetchall()
    conn.close()
    base = SITE_URL or ""
    urls = [f"<url><loc>{base}/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>"]
    for r in rows:
        lastmod = (r["created_at"] or "")[:10]
        urls.append(f"<url><loc>{base}/uy/{r['id']}</loc><lastmod>{lastmod}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"
    return Response(content=xml, media_type="application/xml")


@app.get("/robots.txt")
def robots():
    base = SITE_URL or ""
    content = f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /api/\nSitemap: {base}/sitemap.xml\n"
    return PlainTextResponse(content)


@app.get("/logo.png")
def serve_logo():
    path = os.path.join(BASE_DIR, "logo.png")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})
    raise HTTPException(status_code=404)


@app.get("/favicon.ico")
def serve_favicon():
    path = os.path.join(BASE_DIR, "logo.png")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})
    raise HTTPException(status_code=404)



# ============================= API: XARITA (ADMIN, himoyalangan) =============================

@app.get("/api/listings")
def api_listings(user: str = Depends(check_auth)):
    return get_active_listings()


# ============================= API: XARITA (OMMAVIY, parolsiz) =============================

@app.get("/api/public-listings")
def api_public_listings():
    return get_active_listings()


@app.post("/api/track-view")
def track_view():
    """Xarita sahifasi ochilganda chaqiriladi - umumiy ko'rishlar sonini kuzatish uchun."""
    conn = db()
    conn.execute("INSERT INTO map_views (viewed_at) VALUES (?)", (now_str(),))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/track-click/{listing_id}")
def track_click(listing_id: int):
    """Xaritadan \"Kanaldagi postni ko'rish\" tugmasi bosilganda chaqiriladi."""
    conn = db()
    conn.execute("INSERT INTO map_clicks (listing_id, clicked_at) VALUES (?, ?)", (listing_id, now_str()))
    conn.commit()
    conn.close()
    return {"ok": True}


# ============================= API: TO'LIQ STATISTIKA (faqat admin) =============================

@app.get("/api/stats")
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


# ============================= SAHIFALAR =============================

@app.get("/admin", response_class=HTMLResponse)
def dashboard_page(user: str = Depends(check_auth)):
    return ADMIN_HTML


@app.get("/xarita", response_class=HTMLResponse)
def public_map_page():
    return PUBLIC_MAP_HTML


@app.get("/tanla-joy", response_class=HTMLResponse)
def pick_location_page():
    return PICK_LOCATION_HTML


# ============================= ADMIN PANEL HTML (PRO) =============================

ADMIN_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Admin Panel - Ijaraga Uylar</title>
<link rel="icon" href="/logo.png">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --brand: #FF385C; --brand-dark: #E31C5F; --brand-light: #FFF0F2;
    --ink: #222222; --ink-soft: #484848; --muted: #717171; --line: #EBEBEB;
    --bg: #F7F7F7; --card: #ffffff;
    --sidebar-w: 232px;
    --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 16px rgba(0,0,0,0.08);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  html, body { width: 100%; overflow-x: hidden; }
  body { font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--ink); font-size: 14px; }

  /* ===== SIDEBAR ===== */
  #sidebar {
    position: fixed; top: 0; left: 0; bottom: 0; width: var(--sidebar-w); background: #fff;
    border-right: 1px solid var(--line); padding: 20px 14px; z-index: 100; overflow-y: auto;
  }
  .side-brand { display: flex; align-items: center; gap: 10px; padding: 6px 10px 22px; font-weight: 800; font-size: 16px; }
  .side-brand img { width: 32px; height: 32px; border-radius: 9px; }
  .side-nav a {
    display: flex; align-items: center; gap: 11px; padding: 11px 12px; border-radius: 10px;
    color: var(--ink-soft); font-weight: 600; font-size: 13.5px; margin-bottom: 3px; cursor: pointer;
    transition: background .15s;
  }
  .side-nav a:hover { background: var(--bg); }
  .side-nav a.active { background: var(--brand-light); color: var(--brand-dark); }
  .side-nav .icon { font-size: 17px; width: 20px; text-align: center; }
  .side-live {
    margin-top: 20px; padding: 10px 12px; background: var(--bg); border-radius: 10px;
    display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; color: #1A7A3C;
  }
  .pulse-dot { width: 7px; height: 7px; border-radius: 50%; background: #22C55E; animation: pulse 1.6s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }

  #content { margin-left: var(--sidebar-w); padding: 26px 30px 50px; max-width: 1400px; }

  @media (max-width: 900px) {
    #sidebar {
      top: auto; bottom: 0; left: 0; right: 0; width: 100%; height: auto; border-right: none;
      border-top: 1px solid var(--line); padding: 8px; display: flex; justify-content: space-around;
    }
    .side-brand, .side-live { display: none; }
    .side-nav { display: flex; width: 100%; justify-content: space-around; }
    .side-nav a { flex-direction: column; gap: 3px; font-size: 10.5px; padding: 8px 6px; flex: 1; text-align: center; }
    #content { margin-left: 0; padding: 18px 14px 90px; }
  }

  .page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 22px; flex-wrap: wrap; gap: 10px; }
  .page-head h1 { font-size: 21px; font-weight: 800; letter-spacing: -0.4px; }

  .tab-page { display: none; }
  .tab-page.active { display: block; }

  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 26px; }
  .kpi-card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; box-shadow: var(--shadow); }
  .kpi-card .icon-badge { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 17px; margin-bottom: 10px; }
  .kpi-card .label { font-size: 12px; color: var(--muted); font-weight: 600; margin-bottom: 4px; }
  .kpi-card .value { font-size: 25px; font-weight: 800; letter-spacing: -0.5px; }
  .kpi-card .trend { display: inline-flex; align-items: center; gap: 3px; font-size: 11.5px; font-weight: 700; margin-top: 7px; padding: 2px 8px; border-radius: 7px; }
  .trend.up { color: #1A7A3C; background: #E7F6EC; }
  .trend.down { color: #C0362C; background: #FDEDEB; }
  .trend.flat { color: var(--muted); background: var(--bg); }
  .icon-pink { background: var(--brand-light); color: var(--brand); }
  .icon-blue { background: #E8F1FE; color: #2563EB; }
  .icon-green { background: #E7F6EC; color: #16A34A; }
  .icon-purple { background: #F3E8FE; color: #9333EA; }
  .icon-orange { background: #FEF3E2; color: #D97706; }

  .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 26px; }
  @media (max-width: 980px) { .charts-grid { grid-template-columns: 1fr; } }
  .panel { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; box-shadow: var(--shadow); }
  .panel h2 { font-size: 14.5px; font-weight: 700; margin-bottom: 3px; }
  .panel .panel-sub { font-size: 12px; color: var(--muted); margin-bottom: 14px; }
  .chart-box { height: 250px; position: relative; }

  #map { height: 460px; border-radius: 12px; width: 100%; }
  .price-label { background: var(--brand); color: #fff; font-weight: 700; font-size: 12px; padding: 2px 8px; border-radius: 10px; border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,.3); white-space: nowrap; }
  .price-label::before { border-top-color: var(--brand) !important; }
  .post-link-btn { display: inline-block; margin-top: 8px; background: var(--brand); color: #fff !important; text-decoration: none; padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; }

  .top-list { display: flex; flex-direction: column; gap: 8px; }
  .top-item { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; background: var(--bg); border-radius: 10px; }
  .top-item .ti-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .top-item .ti-rank { width: 22px; height: 22px; border-radius: 50%; background: var(--brand-light); color: var(--brand); font-size: 11px; font-weight: 800; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .top-item .ti-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }
  .top-item .ti-clicks { font-size: 12px; font-weight: 700; color: #D97706; white-space: nowrap; }
  .empty-note { color: var(--muted); font-size: 13px; text-align: center; padding: 20px; }

  .funnel-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
  .funnel-box { flex: 1; text-align: center; padding: 14px 8px; border-radius: 12px; background: var(--bg); }
  .funnel-box .fb-val { font-size: 21px; font-weight: 800; }
  .funnel-box .fb-label { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .funnel-arrow { color: var(--muted); font-size: 18px; }

  table.visit-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  table.visit-table th { text-align: left; color: var(--muted); font-weight: 700; font-size: 11px; text-transform: uppercase; padding: 8px 10px; border-bottom: 1px solid var(--line); }
  table.visit-table td { padding: 9px 10px; border-bottom: 1px solid var(--line); }
  table.visit-table tr:last-child td { border-bottom: none; }
  .device-chip { padding: 2px 9px; border-radius: 7px; font-size: 11px; font-weight: 700; }
  .device-chip.Mobil { background: #E8F1FE; color: #2563EB; }
  .device-chip.Kompyuter { background: #E7F6EC; color: #16A34A; }
  .device-chip.Planshet { background: #F3E8FE; color: #9333EA; }
  .device-chip.Bot { background: #FEF3E2; color: #D97706; }
  .table-scroll { overflow-x: auto; }

  .bars-list { display: flex; flex-direction: column; gap: 10px; }
  .bar-row { display: flex; align-items: center; gap: 10px; }
  .bar-row .bl { font-size: 12.5px; font-weight: 600; width: 110px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar-row .bt { flex: 1; height: 8px; background: var(--bg); border-radius: 4px; overflow: hidden; }
  .bar-row .bt .fill { height: 100%; background: var(--brand); border-radius: 4px; }
  .bar-row .bv { font-size: 12px; font-weight: 700; color: var(--muted); width: 30px; text-align: right; flex-shrink: 0; }
  #subarenda-badge { background: var(--brand); color: #fff; font-size: 10px; font-weight: 800; padding: 1px 6px; border-radius: 10px; margin-left: 4px; }
  #subarenda-badge:empty { display: none; }
  .sr-card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin-bottom: 10px; }
  .sr-top { display: flex; justify-content: space-between; align-items: start; gap: 10px; margin-bottom: 8px; }
  .sr-name { font-weight: 700; font-size: 14px; }
  .sr-meta { font-size: 12.5px; color: var(--muted); margin-bottom: 10px; line-height: 1.6; }
  .sr-actions { display: flex; gap: 8px; }
  .sr-actions button { flex: 1; padding: 8px; border-radius: 8px; border: 1px solid var(--line); background: #fff; font-size: 12.5px; font-weight: 700; cursor: pointer; }
  .sr-actions button.approve { background: #16A34A; color: #fff; border: none; }
  .sr-status { font-size: 10.5px; font-weight: 800; padding: 2px 8px; border-radius: 7px; text-transform: uppercase; }
  .sr-status.yangi { background: var(--brand-light); color: var(--brand); }
  .sr-status.bogl { background: #E8F1FE; color: #2563EB; }
  .sr-status.yopiq { background: var(--bg); color: var(--muted); }
</style>
</head>
<body>

<div id="sidebar">
  <div class="side-brand"><img src="/logo.png" alt="logo"> Ijaraga Uylar</div>
  <nav class="side-nav">
    <a data-tab="overview" class="active"><span class="icon">\U0001F4CA</span> Umumiy</a>
    <a data-tab="visitors"><span class="icon">\U0001F465</span> Tashriflar</a>
    <a data-tab="subarenda"><span class="icon">\U0001F3E2</span> Subarenda <span id="subarenda-badge"></span></a>
    <a data-tab="inquiries"><span class="icon">\U0001F4E9</span> So'rovlar <span id="inquiries-badge"></span></a>
    <a data-tab="mapview"><span class="icon">\U0001F5FA</span> Xarita</a>
  </nav>
  <div class="side-live"><span class="pulse-dot"></span> Jonli holat</div>
</div>

<div id="content">

  <div id="tab-overview" class="tab-page active">
    <div class="page-head"><h1>\U0001F4CA Umumiy ko'rinish</h1></div>
    <div class="kpi-grid" id="kpi-main"><div class="empty-note">Yuklanmoqda...</div></div>
    <div class="kpi-grid" id="kpi-secondary"></div>
    <div class="charts-grid">
      <div class="panel">
        <h2>\U0001F4B5 Oylik daromad tendensiyasi</h2>
        <div class="panel-sub">So'nggi 6 oy — e'lon va Limit daromadi</div>
        <div class="chart-box"><canvas id="revenueChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>\U0001F4DD E'lonlar o'sishi</h2>
        <div class="panel-sub">So'nggi 30 kun</div>
        <div class="chart-box"><canvas id="listingsChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>\U0001F513 Limit sotib olishlar</h2>
        <div class="panel-sub">So'nggi 30 kun</div>
        <div class="chart-box"><canvas id="subsChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>\U0001F5FA Xarita orqali qiziqish</h2>
        <div class="panel-sub">Xaritadan e'longa o'tish jarayoni</div>
        <div class="funnel-row" id="funnel-row"></div>
        <div style="margin-top:16px;">
          <div style="font-size:12px;color:var(--muted);font-weight:700;margin-bottom:8px;">TOP 5 — eng ko'p qiziqish</div>
          <div class="top-list" id="top-clicked"><div class="empty-note">Ma'lumot yo'q</div></div>
        </div>
      </div>
    </div>
  </div>

  <div id="tab-visitors" class="tab-page">
    <div class="page-head"><h1>\U0001F465 Sayt tashriflari</h1></div>
    <div class="kpi-grid" id="kpi-visits"></div>
    <div class="charts-grid">
      <div class="panel">
        <h2>\U0001F4C8 So'nggi 14 kunlik tashriflar</h2>
        <div class="panel-sub">Har kungi umumiy sahifa ko'rishlar</div>
        <div class="chart-box"><canvas id="visitsChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>\U0001F4F1 Qurilmalar va davlatlar</h2>
        <div class="panel-sub">So'nggi 7 kun</div>
        <div id="device-bars" class="bars-list" style="margin-bottom:18px;"></div>
        <div id="country-bars" class="bars-list"></div>
      </div>
    </div>
    <div class="panel" style="margin-bottom:16px;">
      <h2>\U0001F4C4 Eng ko'p ko'rilgan sahifalar</h2>
      <div class="panel-sub">So'nggi 7 kun</div>
      <div id="pages-bars" class="bars-list" style="margin-top:14px;"></div>
    </div>
    <div class="panel">
      <h2>\U0001F553 So'nggi tashriflar</h2>
      <div class="panel-sub">Oxirgi 30 ta kirish (jonli)</div>
      <div class="table-scroll">
        <table class="visit-table" id="visits-table">
          <thead><tr><th>Vaqt</th><th>Sahifa</th><th>Davlat/Shahar</th><th>Qurilma</th><th>Brauzer</th></tr></thead>
          <tbody><tr><td colspan="5" class="empty-note">Yuklanmoqda...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <div id="tab-subarenda" class="tab-page">
    <div class="page-head"><h1>\U0001F3E2 Subarenda so\'rovlari</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">Uy egalaridan kelgan, uyni platformaga boshqarishga topshirish so\'rovlari</div>
    <div id="subarenda-list"><div class="empty-note">Yuklanmoqda...</div></div>
  </div>

  <div id="tab-inquiries" class="tab-page">
    <div class="page-head"><h1>\U0001F4E9 Saytdan kelgan so\'rovlar</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">Foydalanuvchilar veb-saytdan e\'lon egalariga yuborgan so\'rovlar</div>
    <div id="inquiries-list"><div class="empty-note">Yuklanmoqda...</div></div>
  </div>

  <div id="tab-mapview" class="tab-page">
    <div class="page-head"><h1>\U0001F5FA Faol e'lonlar xaritasi</h1></div>
    <div class="panel"><div id="map"></div></div>
  </div>

</div>

<script>
document.querySelectorAll('.side-nav a').forEach(a => {
  a.addEventListener('click', () => {
    document.querySelectorAll('.side-nav a').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-page').forEach(x => x.classList.remove('active'));
    a.classList.add('active');
    document.getElementById('tab-' + a.dataset.tab).classList.add('active');
    if (a.dataset.tab === 'mapview' && !window._mapLoaded) { loadMap(); window._mapLoaded = true; }
  });
});

function fmtMoney(n) {
  if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n/1000).toFixed(0) + 'k';
  return String(n);
}
function trendBadge(pct) {
  if (pct === null || pct === undefined) return '';
  if (pct > 0) return `<span class="trend up">\u2191 ${pct}%</span>`;
  if (pct < 0) return `<span class="trend down">\u2193 ${Math.abs(pct)}%</span>`;
  return `<span class="trend flat">\u2192 0%</span>`;
}
function barsHtml(items, keyField, maxItems) {
  const top = items.slice(0, maxItems || 6);
  const max = Math.max(...top.map(i => i.c), 1);
  return top.map(i => `
    <div class="bar-row">
      <div class="bl">${i[keyField]}</div>
      <div class="bt"><div class="fill" style="width:${(i.c/max*100)}%"></div></div>
      <div class="bv">${i.c}</div>
    </div>`).join('') || `<div class="empty-note">Ma'lumot yo'q</div>`;
}

let statsCache = null;

async function loadStats() {
  const res = await fetch('/api/stats');
  const s = await res.json();
  statsCache = s;

  document.getElementById('kpi-main').innerHTML = `
    <div class="kpi-card"><div class="icon-badge icon-blue">\U0001F465</div><div class="label">Jami foydalanuvchilar</div><div class="value">${s.total_users}</div>${trendBadge(s.new_users_week_change)}</div>
    <div class="kpi-card"><div class="icon-badge icon-green">\U0001F3E0</div><div class="label">Faol e'lonlar</div><div class="value">${s.active_listings}</div><div style="font-size:12px;color:var(--muted);margin-top:8px;">${s.pending_listings} kutilmoqda</div></div>
    <div class="kpi-card"><div class="icon-badge icon-purple">\U0001F513</div><div class="label">Faol Limit egalari</div><div class="value">${s.active_subscribers}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-pink">\U0001F4B0</div><div class="label">Bu oy jami tushum</div><div class="value">${fmtMoney(s.revenue_month_total)}</div><div style="font-size:11px;color:var(--muted);margin-top:4px;">so'm</div></div>
  `;
  document.getElementById('kpi-secondary').innerHTML = `
    <div class="kpi-card"><div class="icon-badge icon-green">\U0001F4DD</div><div class="label">E'lon daromadi (oy)</div><div class="value">${fmtMoney(s.revenue_month_listings)}</div>${trendBadge(s.revenue_month_listings_change)}</div>
    <div class="kpi-card"><div class="icon-badge icon-purple">\U0001F4B3</div><div class="label">Limit daromadi (oy)</div><div class="value">${fmtMoney(s.revenue_month_subs)}</div>${trendBadge(s.revenue_month_subs_change)}</div>
    <div class="kpi-card"><div class="icon-badge icon-blue">\U0001F4CD</div><div class="label">Joylashuvli e'lonlar</div><div class="value">${s.listings_with_location}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-orange">\U0001F5FA</div><div class="label">Xarita ko'rishlar (oy)</div><div class="value">${s.map_stats.views_month}</div><div style="font-size:12px;color:var(--muted);margin-top:8px;">${s.map_stats.clicks_month} ta bosish</div></div>
  `;
  document.getElementById('funnel-row').innerHTML = `
    <div class="funnel-box"><div class="fb-val">${s.map_stats.total_views}</div><div class="fb-label">Xarita ochilgan</div></div>
    <div class="funnel-arrow">\u2192</div>
    <div class="funnel-box"><div class="fb-val">${s.map_stats.total_clicks}</div><div class="fb-label">Postga o'tilgan</div></div>
    <div class="funnel-arrow">\u2192</div>
    <div class="funnel-box"><div class="fb-val">${s.map_stats.conversion_rate}%</div><div class="fb-label">Konversiya</div></div>
  `;
  const topEl = document.getElementById('top-clicked');
  topEl.innerHTML = s.map_stats.top_clicked.length ? s.map_stats.top_clicked.map((t, i) => `
    <div class="top-item"><div class="ti-left"><div class="ti-rank">${i+1}</div><div class="ti-name">${t.manzil || 'Nomsiz'} — ${t.narx || ''}</div></div><div class="ti-clicks">${t.clicks} bosish</div></div>
  `).join('') : `<div class="empty-note">Hali bosishlar yo'q</div>`;

  // Tashriflar KPI
  const v = s.visit_stats;
  document.getElementById('kpi-visits').innerHTML = `
    <div class="kpi-card"><div class="icon-badge icon-pink">\U0001F441</div><div class="label">Jami tashriflar</div><div class="value">${v.total}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-blue">\U0001F4C5</div><div class="label">Bugun</div><div class="value">${v.today}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-green">\U0001F4C8</div><div class="label">So'nggi 7 kun</div><div class="value">${v.week}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-purple">\U0001F464</div><div class="label">Noyob tashrifchi (7 kun)</div><div class="value">${v.unique_week}</div></div>
  `;
  document.getElementById('device-bars').innerHTML = '<div style="font-size:11px;color:var(--muted);font-weight:700;margin-bottom:8px;">QURILMALAR</div>' + barsHtml(v.devices, 'device');
  document.getElementById('country-bars').innerHTML = '<div style="font-size:11px;color:var(--muted);font-weight:700;margin-bottom:8px;">DAVLATLAR</div>' + barsHtml(v.countries, 'country');
  document.getElementById('pages-bars').innerHTML = barsHtml(v.top_pages, 'path', 8);

  const tbody = document.querySelector('#visits-table tbody');
  tbody.innerHTML = v.recent.length ? v.recent.map(r => `
    <tr>
      <td>${r.visited_at.slice(5,16)}</td>
      <td>${r.path}</td>
      <td>${r.city !== 'Mahalliy' ? (r.city + ', ' + r.country) : 'Mahalliy'}</td>
      <td><span class="device-chip ${r.device}">${r.device}</span></td>
      <td>${r.browser}</td>
    </tr>
  `).join('') : `<tr><td colspan="5" class="empty-note">Hali tashrif yo'q</td></tr>`;

  const gridColor = 'rgba(0,0,0,0.04)';
  const tickColor = '#717171';

  if (window._charts) window._charts.forEach(c => c.destroy());
  window._charts = [];

  window._charts.push(new Chart(document.getElementById('revenueChart'), {
    type: 'bar',
    data: { labels: s.monthly_revenue.map(d => d.month), datasets: [
      { label: "E'lon", data: s.monthly_revenue.map(d => d.listings), backgroundColor: '#FF385C', borderRadius: 6 },
      { label: 'Limit', data: s.monthly_revenue.map(d => d.subs), backgroundColor: '#9333EA', borderRadius: 6 }
    ]},
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: tickColor, font: { size: 11 } } } },
      scales: { y: { beginAtZero: true, grid: { color: gridColor }, ticks: { color: tickColor } }, x: { grid: { display: false }, ticks: { color: tickColor } } } }
  }));
  window._charts.push(new Chart(document.getElementById('listingsChart'), {
    type: 'bar',
    data: { labels: s.daily_listings.map(d => d.date), datasets: [{ label: "Yangi e'lonlar", data: s.daily_listings.map(d => d.count), backgroundColor: '#2563EB', borderRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, grid: { color: gridColor }, ticks: { color: tickColor, stepSize: 1 } }, x: { grid: { display: false }, ticks: { color: tickColor, maxRotation: 0, autoSkipPadding: 12 } } } }
  }));
  window._charts.push(new Chart(document.getElementById('subsChart'), {
    type: 'line',
    data: { labels: s.daily_subs.map(d => d.date), datasets: [{ label: 'Limit', data: s.daily_subs.map(d => d.count), borderColor: '#D97706', backgroundColor: 'rgba(217,119,6,0.12)', fill: true, tension: 0.35, pointRadius: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, grid: { color: gridColor }, ticks: { color: tickColor, stepSize: 1 } }, x: { grid: { display: false }, ticks: { color: tickColor, maxRotation: 0, autoSkipPadding: 12 } } } }
  }));
  window._charts.push(new Chart(document.getElementById('visitsChart'), {
    type: 'line',
    data: { labels: v.daily.map(d => d.date), datasets: [{ label: 'Tashriflar', data: v.daily.map(d => d.count), borderColor: '#FF385C', backgroundColor: 'rgba(255,56,92,0.1)', fill: true, tension: 0.35, pointRadius: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, grid: { color: gridColor }, ticks: { color: tickColor, stepSize: 1 } }, x: { grid: { display: false }, ticks: { color: tickColor, maxRotation: 0, autoSkipPadding: 12 } } } }
  }));
}

async function loadSubarenda() {
  const res = await fetch('/api/subarenda-requests');
  const items = await res.json();
  const badge = document.getElementById('subarenda-badge');
  const pending = items.filter(i => i.status === 'yangi').length;
  badge.textContent = pending > 0 ? pending : '';
  const listEl = document.getElementById('subarenda-list');
  if (!items.length) { listEl.innerHTML = `<div class="empty-note">Hali so'rov yo'q</div>`; return; }
  listEl.innerHTML = items.map(r => `
    <div class="sr-card">
      <div class="sr-top">
        <div class="sr-name">${r.full_name || 'Nomsiz'}</div>
        <span class="sr-status ${r.status}">${r.status}</span>
      </div>
      <div class="sr-meta">
        \U0001F4CD ${r.manzil || '-'}<br>
        \U0001F6CF ${r.xona || '-'} \u00b7 \U0001F4B0 So\'ragan narx: ${r.narx_talab || '-'}<br>
        \U0001F4DE ${r.phone || '-'} \u00b7 \U0001F553 ${r.created_at}
      </div>
      <div class="sr-actions">
        <button onclick="updateSubarenda(${r.id}, 'bogl')">\U0001F4DE Bog'lanildi</button>
        <button class="approve" onclick="updateSubarenda(${r.id}, 'yopiq')">\u2705 Yakunlandi</button>
      </div>
    </div>
  `).join('');
}
async function updateSubarenda(id, status) {
  await fetch(`/api/subarenda-requests/${id}?status=${status}`, { method: 'POST' });
  loadSubarenda();
}

async function loadInquiries() {
  const res = await fetch('/api/listing-inquiries');
  const items = await res.json();
  const badge = document.getElementById('inquiries-badge');
  const pending = items.filter(i => i.status === 'yangi').length;
  badge.textContent = pending > 0 ? pending : '';
  const listEl = document.getElementById('inquiries-list');
  if (!items.length) { listEl.innerHTML = `<div class="empty-note">Hali so'rov yo'q</div>`; return; }
  listEl.innerHTML = items.map(r => `
    <div class="sr-card">
      <div class="sr-top">
        <div class="sr-name">${r.name || 'Nomsiz'}</div>
        <span class="sr-status ${r.status === 'yangi' ? 'yangi' : 'yopiq'}">${r.status}</span>
      </div>
      <div class="sr-meta">
        \U0001F3E0 ${r.listing_manzil || ('E\\'lon #' + r.listing_id)}<br>
        \U0001F4DE ${r.phone || '-'} \u00b7 \U0001F553 ${r.created_at}
        ${r.message ? '<br>\U0001F4AC ' + r.message : ''}
      </div>
      <div class="sr-actions">
        <a href="/uy/${r.listing_id}" target="_blank" style="flex:1;"><button style="width:100%;">\U0001F3E0 E'lonni ko'rish</button></a>
        <button class="approve" onclick="updateInquiry(${r.id})">\u2705 Ko'rib chiqildi</button>
      </div>
    </div>
  `).join('');
}
async function updateInquiry(id) {
  await fetch(`/api/listing-inquiries/${id}?status=yopiq`, { method: 'POST' });
  loadInquiries();
}

async function loadMap() {
  const map = L.map('map', { tap: true }).setView([41.311081, 69.240562], 11);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap', maxZoom: 19 }).addTo(map);
  const res = await fetch('/api/listings');
  const listings = await res.json();
  listings.forEach(l => {
    const marker = L.circleMarker([l.latitude, l.longitude], { radius: 8, fillColor: '#FF385C', color: '#fff', weight: 2, fillOpacity: 0.9 }).addTo(map);
    if (l.narx) marker.bindTooltip(l.narx, { permanent: true, direction: 'top', className: 'price-label', offset: [0, -6] });
    const postBtn = l.post_link ? `<br><a href="${l.post_link}" target="_blank" class="post-link-btn">\U0001F4E2 Kanaldagi postni ko'rish</a>` : '';
    marker.bindPopup(`<b>${l.manzil || ''}</b><br>\U0001F3AF ${l.moljal || ''}<br>\U0001F6CF ${l.xona || ''} \u2014 \U0001F4B0 ${l.narx || ''}<br>\U0001F465 ${l.kimlarga || ''}<br><small>#${l.id}</small>${postBtn}`);
  });
}

loadStats();
loadSubarenda();
loadInquiries();
setInterval(loadStats, 60000);
setInterval(loadSubarenda, 30000);
setInterval(loadInquiries, 30000);
</script>
</body>
</html>
"""


# ============================= OMMAVIY XARITA HTML (parolsiz) =============================

PUBLIC_MAP_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>Ijaraga Uylar - Xarita</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  html, body { width: 100%; height: 100%; overflow: hidden; }
  body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #0f1419; }
  #topbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
    background: rgba(26,35,50,0.95); backdrop-filter: blur(6px);
    padding: 10px 14px; display: flex; align-items: center; justify-content: space-between;
    border-bottom: 1px solid #2a3441; color: #e8eaed;
    padding-top: calc(10px + env(safe-area-inset-top));
  }
  #topbar h1 { font-size: 15px; font-weight: 600; }
  #topbar .count { font-size: 12px; color: #8b98a5; }
  #topbar-left { display: flex; align-items: center; gap: 10px; }
  #home-link {
    display: flex; align-items: center; justify-content: center; width: 30px; height: 30px;
    border-radius: 8px; background: rgba(255,255,255,0.08); color: #e8eaed; flex-shrink: 0;
  }
  #home-link svg { width: 16px; height: 16px; }
  #map { position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; }
  .leaflet-popup-content-wrapper { border-radius: 12px; }
  .leaflet-popup-content { font-size: 14px; line-height: 1.6; margin: 12px 14px; min-width: 200px; }
  .leaflet-popup-content b { font-size: 15px; }
  .price-label { background: #e74c3c; color: #fff; font-weight: 700; font-size: 13px; padding: 3px 9px; border-radius: 10px; border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,.4); white-space: nowrap; }
  .price-label::before { border-top-color: #e74c3c !important; }
  .post-link-btn { display: inline-block; margin-top: 8px; background: #2ea043; color: #fff !important; text-decoration: none; padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; }
  .post-link-btn:hover { background: #35c455; }
  #loading { position: fixed; inset: 0; background: #0f1419; color: #8b98a5; display: flex; align-items: center; justify-content: center; font-size: 14px; z-index: 2000; }
</style>
</head>
<body>
<div id="loading">\U0001F5FA Xarita yuklanmoqda...</div>
<div id="topbar">
  <div id="topbar-left">
    <a href="/" id="home-link" aria-label="Bosh sahifa"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9a1 1 0 0 0 1 1h3v-6h4v6h3a1 1 0 0 0 1-1v-9"/></svg></a>
    <h1>\U0001F3E0 Ijaraga Uylar</h1>
  </div>
  <span class="count" id="count-badge"></span>
</div>
<div id="map"></div>

<script>
if (window.Telegram && window.Telegram.WebApp) {
  Telegram.WebApp.ready();
  Telegram.WebApp.expand();
}

function trackClick(listingId) {
  fetch('/api/track-click/' + listingId, { method: 'POST' }).catch(() => {});
}

async function init() {
  fetch('/api/track-view', { method: 'POST' }).catch(() => {});

  const map = L.map('map', { tap: true, zoomControl: false }).setView([41.311081, 69.240562], 11);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap', maxZoom: 19 }).addTo(map);

  const res = await fetch('/api/public-listings');
  const listings = await res.json();

  listings.forEach(l => {
    const marker = L.circleMarker([l.latitude, l.longitude], { radius: 9, fillColor: '#e74c3c', color: '#fff', weight: 2, fillOpacity: 0.9 }).addTo(map);
    if (l.narx) marker.bindTooltip(l.narx, { permanent: true, direction: 'top', className: 'price-label', offset: [0, -8] });
    const postBtn = l.post_link ? `<a href="${l.post_link}" target="_blank" class="post-link-btn" onclick="trackClick(${l.id})">\U0001F4E2 Kanaldagi postni ko'rish</a>` : '';
    marker.bindPopup(`<b>${l.manzil || ''}</b><br>\U0001F3AF ${l.moljal || ''}<br>\U0001F6CF ${l.xona || ''} \u2014 \U0001F4B0 ${l.narx || ''}<br>\U0001F465 ${l.kimlarga || ''}${postBtn}`);
  });

  document.getElementById('count-badge').textContent = listings.length + " ta e'lon";
  document.getElementById('loading').style.display = 'none';
}

init();
</script>
</body>
</html>
"""


# ============================= JOYLASHUV TANLASH (WebApp, elon berish jarayoni uchun) =============================

PICK_LOCATION_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>Joylashuvni tanlang</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  html, body { width: 100%; height: 100%; overflow: hidden; }
  body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #0f1419; }
  #topbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
    background: rgba(26,35,50,0.97); backdrop-filter: blur(6px);
    padding: 12px 16px; color: #e8eaed; text-align: center;
    border-bottom: 1px solid #2a3441;
    padding-top: calc(12px + env(safe-area-inset-top));
  }
  #topbar h1 { font-size: 14px; font-weight: 600; margin-bottom: 2px; }
  #topbar p { font-size: 12px; color: #8b98a5; }
  #map { position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; }
  #center-pin {
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -100%);
    font-size: 42px; z-index: 999; pointer-events: none;
    filter: drop-shadow(0 4px 6px rgba(0,0,0,0.4));
  }
  #locate-btn {
    position: fixed; right: 12px; bottom: 100px; z-index: 1000;
    width: 46px; height: 46px; border-radius: 50%; border: none;
    background: #1a2332; color: #4285F4; font-size: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5); cursor: pointer;
    display: flex; align-items: center; justify-content: center;
  }
  #locate-btn:active { background: #263148; }
  #confirm-bar {
    position: fixed; bottom: 0; left: 0; right: 0; z-index: 1000;
    padding: 16px; padding-bottom: calc(16px + env(safe-area-inset-bottom));
    background: linear-gradient(to top, rgba(15,20,25,0.98), rgba(15,20,25,0.7));
  }
  #confirm-btn {
    width: 100%; padding: 16px; border: none; border-radius: 14px;
    background: #2ea043; color: #fff; font-size: 16px; font-weight: 700;
    cursor: pointer;
  }
  #confirm-btn:active { background: #268a39; }
  .user-dot { width: 18px; height: 18px; border-radius: 50%; background: #4285F4; border: 3px solid #fff; box-shadow: 0 0 0 4px rgba(66,133,244,0.3); }
</style>
</head>
<body>
<div id="topbar">
  <h1>\U0001F4CD Uyning joylashuvini belgilang</h1>
  <p>Xaritani suring, markazdagi belgi \u2014 tanlangan nuqta</p>
</div>
<div id="map"></div>
<div id="center-pin">\U0001F4CD</div>
<button id="locate-btn" title="Mening joylashuvim">\U0001F3AF</button>
<div id="confirm-bar">
  <button id="confirm-btn">\u2705 Shu nuqtani tanlash</button>
</div>

<script>
const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); }

const map = L.map('map', { zoomControl: false, tap: true }).setView([41.311081, 69.240562], 13);
L.control.zoom({ position: 'bottomright' }).addTo(map);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap', maxZoom: 19 }).addTo(map);

// "Google/Yandex Maps"dagidek - foydalanuvchining O'ZI TURGAN joyi doim
// xaritada ko'k nuqta bilan ko'rinib turadi (bu - tanlangan nuqtadan FARQLI,
// faqat orientir uchun).
let userMarker = null;
const userIcon = L.divIcon({ className: '', html: '<div class="user-dot"></div>', iconSize: [18, 18] });

function showUserLocation(lat, lon, recenter) {
  if (userMarker) { userMarker.setLatLng([lat, lon]); }
  else { userMarker = L.marker([lat, lon], { icon: userIcon, zIndexOffset: 500 }).addTo(map); }
  if (recenter) map.setView([lat, lon], 15);
}

function locateMe() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => showUserLocation(pos.coords.latitude, pos.coords.longitude, true),
    () => {}
  );
}

// Sahifa ochilganda avtomatik bir marta joylashuvni aniqlaymiz
locateMe();
// "Mening joylashuvim" tugmasi - istalgan vaqt bosib, o'z joyiga qaytish mumkin
document.getElementById('locate-btn').addEventListener('click', locateMe);

document.getElementById('confirm-btn').addEventListener('click', () => {
  const center = map.getCenter();
  const data = JSON.stringify({ lat: center.lat, lon: center.lng });
  if (tg) {
    tg.sendData(data);
  } else {
    alert('lat: ' + center.lat + ', lon: ' + center.lng);
  }
});
</script>
</body>
</html>
"""
