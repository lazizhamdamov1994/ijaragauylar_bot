"""
Qidiruv tizimlari uchun: sitemap.xml, robots.txt, logo/favicon.
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response

from common.config import SITE_URL
from common.db import db
from web.render import DISTRICT_TO_SLUG, SUPPORTED_LANGS, TASHKENT_DISTRICTS

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _sitemap_alt_links(base: str, path: str) -> str:
    """Har bir URL uchun uz/ru/en muqobil versiyalarini ko'rsatadi - Google
    va Yandex mos tildagi qidiruvchiga to'g'ri variantni ko'rsatishi uchun."""
    return "".join(
        f'<xhtml:link rel="alternate" hreflang="{code}" href="{base}{path}?lang={code}"/>'
        for code in SUPPORTED_LANGS
    )


@router.get("/sitemap.xml")
def sitemap():
    conn = db()
    rows = conn.execute("SELECT id, created_at FROM listings WHERE status='approved' AND COALESCE(expired,0)=0").fetchall()
    conn.close()
    base = SITE_URL or ""
    urls = [
        f"<url><loc>{base}/</loc>{_sitemap_alt_links(base, '/')}<changefreq>hourly</changefreq><priority>1.0</priority></url>",
        f"<url><loc>{base}/xarita</loc>{_sitemap_alt_links(base, '/xarita')}<changefreq>daily</changefreq><priority>0.7</priority></url>",
        f"<url><loc>{base}/elon-joylash</loc>{_sitemap_alt_links(base, '/elon-joylash')}<changefreq>weekly</changefreq><priority>0.6</priority></url>",
        f"<url><loc>{base}/subarenda</loc>{_sitemap_alt_links(base, '/subarenda')}<changefreq>weekly</changefreq><priority>0.6</priority></url>",
    ]
    for district in TASHKENT_DISTRICTS:
        district_path = f"/toshkent/{DISTRICT_TO_SLUG[district]}"
        urls.append(
            f"<url><loc>{base}{district_path}</loc>{_sitemap_alt_links(base, district_path)}"
            f"<changefreq>daily</changefreq><priority>0.7</priority></url>"
        )
    for r in rows:
        lastmod = (r["created_at"] or "")[:10]
        listing_path = f"/uy/{r['id']}"
        urls.append(
            f"<url><loc>{base}{listing_path}</loc>{_sitemap_alt_links(base, listing_path)}"
            f"<lastmod>{lastmod}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(urls) + "\n</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@router.get("/robots.txt")
def robots():
    base = SITE_URL or ""
    content = (
        f"User-agent: *\nAllow: /\n"
        f"Disallow: /admin\nDisallow: /api/\nDisallow: /login\nDisallow: /kabinet\nDisallow: /auth/\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return PlainTextResponse(content)


@router.get("/logo.png")
def serve_logo():
    path = os.path.join(BASE_DIR, "logo.png")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})
    raise HTTPException(status_code=404)


@router.get("/favicon.ico")
def serve_favicon():
    path = os.path.join(BASE_DIR, "logo.png")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})
    raise HTTPException(status_code=404)



# ============================= API: XARITA (ADMIN, himoyalangan) =============================


