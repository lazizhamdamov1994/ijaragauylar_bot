"""Sayt uchun bazadan o'qish. Bot yozadi, sayt faqat o'qiydi (bitta nihola.db)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.constants import DISTRICTS

VISIBLE = ("active", "reserved")
PER_PAGE = 30


@contextmanager
def connect():
    conn = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def db_ready() -> bool:
    return Path(settings.db_path).exists()


def _rows(sql: str, args=()) -> list[dict]:
    if not db_ready():
        return []
    with connect() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def _one(sql: str, args=()):
    rows = _rows(sql, args)
    return rows[0] if rows else None


def bot_username() -> str:
    import os
    env = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
    if env:
        return env
    row = _one("SELECT value FROM meta WHERE key='bot_username'")
    return row["value"] if row else ""


# ---------------- media ----------------
def media_url(row: dict) -> str | None:
    p = row.get("local_path")
    if not p:
        return None
    p = Path(p)
    return f"/media/{p.parent.name}/{p.name}"


def media_for(listing_ids: list[int]) -> dict[int, list[dict]]:
    if not listing_ids:
        return {}
    marks = ",".join("?" for _ in listing_ids)
    out: dict[int, list[dict]] = {i: [] for i in listing_ids}
    for r in _rows(f"SELECT * FROM listing_media WHERE listing_id IN ({marks}) ORDER BY position",
                   listing_ids):
        url = media_url(r)
        if url:
            out[r["listing_id"]].append({"kind": r["kind"], "url": url})
    return out


def attach_covers(items: list[dict]) -> list[dict]:
    media = media_for([i["id"] for i in items])
    for it in items:
        files = media.get(it["id"], [])
        photos = [m for m in files if m["kind"] == "photo"]
        it["cover"] = photos[0]["url"] if photos else None
        it["media"] = files
        it["photo_count"] = len(files)
    return items


# ---------------- qidiruv ----------------
def _district_slugs_for(q: str) -> list[str]:
    from .i18n import DISTRICT_RU
    ql = q.lower()
    out = []
    for slug, name, _ in DISTRICTS:
        if ql in name.lower() or name.lower() in ql or ql in DISTRICT_RU.get(slug, "").lower():
            out.append(slug)
    return out


SORTS = {
    "new": "COALESCE(published_at, created_at) DESC",
    "cheap": "price ASC",
    "expensive": "price DESC",
    "area": "area DESC",
}


def search(p: dict) -> tuple[list[dict], int]:
    where = ["status IN ('active','reserved')"]
    args: list = []
    if p.get("deal") in ("sale", "rent"):
        where.append("deal=?"); args.append(p["deal"])
    if p.get("ptype"):
        where.append("ptype=?"); args.append(p["ptype"])
    if p.get("district"):
        where.append("district=?"); args.append(p["district"])
    rooms = [r for r in p.get("rooms", []) if r.isdigit()]
    if rooms:
        conds = []
        for r in rooms:
            if r == "4":
                conds.append("rooms>=4")
            else:
                conds.append("rooms=?"); args.append(int(r))
        where.append("(" + " OR ".join(conds) + ")")
    for key, col, op in (("pmin", "price", ">="), ("pmax", "price", "<="),
                         ("amin", "area", ">="), ("amax", "area", "<=")):
        if p.get(key):
            where.append(f"{col}{op}?"); args.append(p[key])
    if p.get("period") in ("7", "30"):
        where.append("COALESCE(published_at, created_at)>=datetime('now', ?)")
        args.append(f"-{p['period']} day")
    q = (p.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        conds = ["address LIKE ?", "landmark LIKE ?", "extra LIKE ?", "CAST(id AS TEXT)=?"]
        args += [like, like, like, q.lstrip("#Nn").lstrip("0") or "0"]
        slugs = _district_slugs_for(q)
        if slugs:
            conds.append("district IN (%s)" % ",".join("?" for _ in slugs)); args += slugs
        where.append("(" + " OR ".join(conds) + ")")

    sql_where = " AND ".join(where)
    total = (_one(f"SELECT COUNT(*) AS n FROM listings WHERE {sql_where}", args) or {"n": 0})["n"]
    order = SORTS.get(p.get("sort"), SORTS["new"])
    page = max(1, int(p.get("page") or 1))
    items = _rows(
        f"SELECT * FROM listings WHERE {sql_where} ORDER BY {order} LIMIT ? OFFSET ?",
        args + [PER_PAGE, (page - 1) * PER_PAGE],
    )
    return attach_covers(items), total


def total_visible() -> int:
    row = _one("SELECT COUNT(*) AS n FROM listings WHERE status IN ('active','reserved')")
    return row["n"] if row else 0


def latest(deal: str | None, limit: int = 12) -> list[dict]:
    args: list = []
    extra = ""
    if deal in ("sale", "rent"):
        extra = " AND deal=?"; args.append(deal)
    return attach_covers(_rows(
        f"""SELECT * FROM listings WHERE status='active'{extra}
            AND published_at>=datetime('now','-14 day')
            ORDER BY published_at DESC LIMIT ?""", args + [limit]))


def get_listing(listing_id: int) -> dict | None:
    row = _one("SELECT * FROM listings WHERE id=? AND status!='draft'", (listing_id,))
    return attach_covers([row])[0] if row else None


def similar(listing: dict, limit: int = 10) -> list[dict]:
    price = listing.get("price") or 0
    return attach_covers(_rows(
        """SELECT * FROM listings WHERE status='active' AND id!=? AND deal=?
           ORDER BY (district=?) DESC, (rooms=?) DESC, ABS(price-?) ASC LIMIT ?""",
        (listing["id"], listing["deal"], listing.get("district"), listing.get("rooms"), price, limit)))


def by_ids(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    rows = _rows(f"SELECT * FROM listings WHERE id IN ({marks}) AND status!='draft'", ids)
    order = {i: n for n, i in enumerate(ids)}
    rows.sort(key=lambda r: order.get(r["id"], 0))
    return attach_covers(rows)


def map_points(deal: str | None) -> list[dict]:
    args: list = []
    extra = ""
    if deal in ("sale", "rent"):
        extra = " AND deal=?"; args.append(deal)
    return attach_covers(_rows(
        f"""SELECT * FROM listings WHERE status IN ('active','reserved')
            AND lat IS NOT NULL AND lng IS NOT NULL{extra}""", args))


def sitemap_ids() -> list[dict]:
    return _rows("SELECT id, updated_at FROM listings WHERE status IN ('active','reserved')")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
