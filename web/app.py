"""
FastAPI ilovasini yig'ish - BITTA joyda: `app` shu yerda yaratiladi, barcha
routerlar shu yerga ulanadi. `dashboard.py` (repo ildizida) faqat
`from web.app import app` qiladi - shuning uchun serverdagi
`uvicorn dashboard:app` buyrug'i o'zgarishsiz ishlayveradi.
"""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from common.config import SITE_NAME
from common.db import init_and_migrate
from common.districts import seed_district_aliases

from web import account, admin_page, api, map_page, pages, render, seo
from web.middleware import SecurityHeadersMiddleware, VisitTrackingMiddleware
from web.photos import router as photos_router, start_photo_cache_cleanup

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title=SITE_NAME, docs_url=None, redoc_url=None, openapi_url=None)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(VisitTrackingMiddleware)

init_and_migrate()
seed_district_aliases()

app.include_router(render.router)
app.include_router(pages.router)
app.include_router(account.router)
app.include_router(api.router)
app.include_router(seo.router)
app.include_router(admin_page.router)
app.include_router(map_page.router)
app.include_router(photos_router)


@app.on_event("startup")
async def _on_startup():
    await start_photo_cache_cleanup()
