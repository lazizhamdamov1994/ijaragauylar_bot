"""
So'rov/javob middleware'lari - xavfsizlik sarlavhalari va tashrif kuzatuvi.
"""
import logging

import httpx
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from common.db import db, now_str
from web.auth import _client_ip

logger = logging.getLogger(__name__)

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



