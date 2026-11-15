"""Nihola Estate web sayti (FastAPI). Bot bilan bitta bazadan o'qiydi."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.constants import DISTRICTS, PTYPES

from . import data
from .i18n import (
    LANGS, ago, area_label, district_name, listing_place, listing_title, price_label, t,
)

HERE = Path(__file__).resolve().parent
app = FastAPI(title="Nihola Estate", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
settings.media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
templates = Jinja2Templates(directory=HERE / "templates")

ROOM_CHOICES = ["1", "2", "3", "4"]


def get_lang(request: Request) -> str:
    lang = request.cookies.get("lang", "uz")
    return lang if lang in LANGS else "uz"


def _int(v) -> int | None:
    try:
        n = int(str(v).replace(" ", "").replace(" ", ""))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def ctx(request: Request, **extra) -> dict:
    lang = get_lang(request)
    bot = data.bot_username()

    def tr(key, **kw):
        return t(lang, key, **kw)

    def tg(payload: str = "") -> str:
        if not bot:
            return "#"
        return f"https://t.me/{bot}" + (f"?start={payload}" if payload else "")

    def url_with(**changes) -> str:
        """Joriy so'rov parametrlarini o'zgartirib yangi havola yasaydi (chiplar uchun)."""
        params: list[tuple[str, str]] = []
        keys = set(changes)
        for k, v in request.query_params.multi_items():
            if k not in keys and k != "page":
                params.append((k, v))
        for k, v in changes.items():
            if v is None or v == "":
                continue
            if isinstance(v, (list, tuple)):
                params += [(k, str(x)) for x in v]
            else:
                params.append((k, str(v)))
        q = urlencode(params)
        return request.url.path + (f"?{q}" if q else "")

    base = {
        "request": request, "lang": lang, "t": tr, "tg": tg, "url_with": url_with,
        "price_label": lambda l: price_label(lang, l),
        "area_label": area_label,
        "listing_title": lambda l: listing_title(lang, l),
        "listing_place": lambda l: listing_place(lang, l),
        "district_name": lambda s: district_name(lang, s),
        "ago": lambda l: ago(lang, data.parse_dt(l.get("published_at") or l.get("created_at"))),
        "is_new": lambda l: (data.parse_dt(l.get("published_at")) is not None and
                             ago(lang, data.parse_dt(l.get("published_at"))) in (t(lang, "today"), t(lang, "yesterday"))),
        "districts": [(s, district_name(lang, s)) for s, _, _ in DISTRICTS],
        "ptypes": [(v, t(lang, "ptype_" + v)) for v, _ in PTYPES],
        "realtor_phone": settings.realtor_phone,
        "channel_url": (f"https://t.me/{settings.channel_public_username}"
                        if settings.channel_public_username else None),
        "path": request.url.path,
    }
    base.update(extra)
    return base


def read_filters(request: Request) -> dict:
    qp = request.query_params
    deal = qp.get("deal", "sale")
    return {
        "deal": deal if deal in ("sale", "rent") else "sale",
        "ptype": qp.get("ptype") or None,
        "district": qp.get("district") or None,
        "rooms": [r for r in qp.getlist("rooms") if r in ROOM_CHOICES],
        "pmin": _int(qp.get("pmin")), "pmax": _int(qp.get("pmax")),
        "amin": _int(qp.get("amin")), "amax": _int(qp.get("amax")),
        "period": qp.get("period") if qp.get("period") in ("7", "30") else None,
        "q": (qp.get("q") or "").strip()[:80],
        "sort": qp.get("sort") if qp.get("sort") in data.SORTS else "new",
        "page": _int(qp.get("page")) or 1,
    }


# ---------------- sahifalar ----------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    f = read_filters(request)
    items, total = data.search(f)
    plain = not any(f[k] for k in ("ptype", "district", "rooms", "pmin", "pmax", "amin", "amax", "period", "q"))
    latest = data.latest(f["deal"]) if plain and f["page"] == 1 else []
    return templates.TemplateResponse(request, "index.html", ctx(
        request, f=f, items=items, total=total, all_total=data.total_visible(), latest=latest,
        has_more=f["page"] * data.PER_PAGE < total, room_choices=ROOM_CHOICES,
        active_filters=sum(bool(f[k]) for k in ("pmin", "pmax", "amin", "amax", "district")),
    ))


@app.get("/api/listings")
def api_listings(request: Request):
    f = read_filters(request)
    items, total = data.search(f)
    html = templates.get_template("_cards.html").render(ctx(request, items=items))
    return JSONResponse({"html": html, "has_more": f["page"] * data.PER_PAGE < total})


@app.get("/uy/{listing_id}", response_class=HTMLResponse)
def listing_page(request: Request, listing_id: int):
    listing = data.get_listing(listing_id)
    if not listing:
        return not_found(request)
    return templates.TemplateResponse(request, "listing.html", ctx(
        request, l=listing, similar=data.similar(listing)))


@app.get("/xarita", response_class=HTMLResponse)
def map_page(request: Request):
    deal = request.query_params.get("deal", "sale")
    return templates.TemplateResponse(request, "map.html", ctx(request, deal=deal if deal in ("sale", "rent") else "sale"))


@app.get("/api/map")
def api_map(request: Request):
    lang = get_lang(request)
    deal = request.query_params.get("deal")
    out = []
    for l in data.map_points(deal):
        out.append({
            "id": l["id"], "lat": l["lat"], "lng": l["lng"],
            "price": price_label(lang, l), "price_raw": l["price"] or 0,
            "rooms": l["rooms"], "title": listing_title(lang, l),
            "place": listing_place(lang, l), "cover": l["cover"],
            "status": l["status"], "url": f"/uy/{l['id']}",
        })
    return JSONResponse(out)


@app.get("/sevimlilar", response_class=HTMLResponse)
def favorites_page(request: Request):
    return templates.TemplateResponse(request, "favorites.html", ctx(request))


@app.get("/api/cards")
def api_cards(request: Request, ids: str = ""):
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()][:100]
    items = data.by_ids(id_list)
    html = templates.get_template("_cards.html").render(ctx(request, items=items))
    return JSONResponse({"html": html, "count": len(items)})


@app.get("/lang/{code}")
def set_lang(code: str, next: str = "/"):
    resp = RedirectResponse(next if next.startswith("/") else "/", status_code=303)
    if code in LANGS:
        resp.set_cookie("lang", code, max_age=3600 * 24 * 365, samesite="lax")
    return resp


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request):
    return f"User-agent: *\nAllow: /\nSitemap: {request.base_url}sitemap.xml\n"


@app.get("/sitemap.xml")
def sitemap(request: Request):
    base = str(request.base_url).rstrip("/")
    urls = [f"<url><loc>{base}/</loc></url>", f"<url><loc>{base}/xarita</loc></url>"]
    for r in data.sitemap_ids():
        urls.append(f"<url><loc>{base}/uy/{r['id']}</loc><lastmod>{r['updated_at'][:10]}</lastmod></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(urls) + "</urlset>")
    return Response(xml, media_type="application/xml")


def not_found(request: Request):
    return templates.TemplateResponse(request, "404.html", ctx(request), status_code=404)


@app.exception_handler(404)
async def handle_404(request: Request, exc):
    return not_found(request)
