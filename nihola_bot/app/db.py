"""SQLite baza (aiosqlite orqali, asinxron). Keyinchalik web sayt ham shu bazani o'qiydi."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY,          -- Telegram user_id
    full_name    TEXT,
    username     TEXT,
    phone        TEXT,
    notify_mode  TEXT NOT NULL DEFAULT 'instant',  -- instant | daily | off
    active       INTEGER NOT NULL DEFAULT 1,       -- 0 = botni bloklagan
    source       TEXT,                             -- birinchi kirgan deep-link (masalan call_12)
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS filters (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    deal       TEXT,            -- sale | rent | NULL (farqi yo'q)
    districts  TEXT DEFAULT '', -- vergul bilan: sergeli,chilonzor
    rooms      TEXT DEFAULT '', -- vergul bilan: 1,2,4 (4 = 4 va undan ko'p)
    price_min  INTEGER,
    price_max  INTEGER,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS listings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    deal              TEXT NOT NULL DEFAULT 'sale',
    ptype             TEXT,
    district          TEXT,
    address           TEXT,
    floor             TEXT,
    rooms             INTEGER,
    area              REAL,
    balcony           TEXT,
    bathroom          TEXT,
    renovation        TEXT,
    furniture         TEXT,
    landmark          TEXT,
    extra             TEXT,
    price             INTEGER,
    lat               REAL,
    lng               REAL,
    status            TEXT NOT NULL DEFAULT 'draft',  -- draft | active | reserved | sold
    channel_msg_id    INTEGER,
    channel_post_kind TEXT,                            -- media | text
    created_by        INTEGER,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    published_at      TEXT,
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_listings_status ON listings(status);

CREATE TABLE IF NOT EXISTS listing_media (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,       -- photo | video
    file_id     TEXT NOT NULL,       -- Telegram file_id
    local_path  TEXT,                -- diskdagi nusxa (web sayt uchun)
    ready       INTEGER NOT NULL DEFAULT 1,  -- 0 = file_id hali suv belgili faylga yangilanmagan
    position    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_media_listing ON listing_media(listing_id);

CREATE TABLE IF NOT EXISTS favorites (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, listing_id)
);

CREATE TABLE IF NOT EXISTS leads (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    listing_id INTEGER,
    kind       TEXT NOT NULL,    -- call | save | similar | pics | general | view
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_leads_listing ON leads(listing_id);

CREATE TABLE IF NOT EXISTS seller_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    district    TEXT,
    rooms       INTEGER,
    price       TEXT,
    description TEXT,
    phone       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

LISTING_FIELDS = {
    "deal", "ptype", "district", "address", "floor", "rooms", "area", "balcony",
    "bathroom", "renovation", "furniture", "landmark", "extra", "price", "lat", "lng",
    "status", "channel_msg_id", "channel_post_kind", "created_by", "published_at",
}


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    # ---------- umumiy ----------
    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def execute(self, sql: str, *args: Any) -> int:
        cur = await self.conn.execute(sql, args)
        await self.conn.commit()
        return cur.lastrowid

    async def fetchone(self, sql: str, *args: Any) -> dict | None:
        async with self.conn.execute(sql, args) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def fetchall(self, sql: str, *args: Any) -> list[dict]:
        async with self.conn.execute(sql, args) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def scalar(self, sql: str, *args: Any) -> Any:
        row = await self.fetchone(sql, *args)
        return next(iter(row.values())) if row else None

    # ---------- foydalanuvchilar ----------
    async def upsert_user(self, user_id: int, full_name: str, username: str | None) -> bool:
        """Foydalanuvchini qo'shadi/yangilaydi. Yangi bo'lsa True qaytaradi."""
        exists = await self.scalar("SELECT 1 FROM users WHERE id=?", user_id)
        await self.execute(
            """INSERT INTO users (id, full_name, username) VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET full_name=excluded.full_name,
                   username=excluded.username, last_seen=datetime('now'), active=1""",
            user_id, full_name, username,
        )
        return not exists

    async def get_user(self, user_id: int) -> dict | None:
        return await self.fetchone("SELECT * FROM users WHERE id=?", user_id)

    async def set_user_field(self, user_id: int, field: str, value: Any) -> None:
        assert field in {"phone", "notify_mode", "active", "source"}
        await self.execute(f"UPDATE users SET {field}=? WHERE id=?", value, user_id)

    async def set_source_if_empty(self, user_id: int, source: str) -> None:
        await self.execute(
            "UPDATE users SET source=? WHERE id=? AND (source IS NULL OR source='')", source, user_id
        )

    async def active_user_ids(self) -> list[int]:
        rows = await self.fetchall("SELECT id FROM users WHERE active=1")
        return [r["id"] for r in rows]

    # ---------- filtrlar ----------
    async def get_filter(self, user_id: int) -> dict | None:
        return await self.fetchone("SELECT * FROM filters WHERE user_id=?", user_id)

    async def save_filter(
        self, user_id: int, deal: str | None, districts: Iterable[str], rooms: Iterable[str],
        price_min: int | None, price_max: int | None,
    ) -> None:
        await self.execute(
            """INSERT INTO filters (user_id, deal, districts, rooms, price_min, price_max)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET deal=excluded.deal, districts=excluded.districts,
                   rooms=excluded.rooms, price_min=excluded.price_min, price_max=excluded.price_max,
                   updated_at=datetime('now')""",
            user_id, deal, ",".join(districts), ",".join(rooms), price_min, price_max,
        )

    async def filters_for_mode(self, mode: str) -> list[dict]:
        return await self.fetchall(
            """SELECT f.* FROM filters f JOIN users u ON u.id=f.user_id
               WHERE u.active=1 AND u.notify_mode=?""",
            mode,
        )

    # ---------- e'lonlar ----------
    async def create_listing(self, fields: dict) -> int:
        fields = {k: v for k, v in fields.items() if k in LISTING_FIELDS}
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        return await self.execute(
            f"INSERT INTO listings ({cols}) VALUES ({marks})", *fields.values()
        )

    async def update_listing(self, listing_id: int, **fields: Any) -> None:
        fields = {k: v for k, v in fields.items() if k in LISTING_FIELDS}
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        await self.execute(
            f"UPDATE listings SET {sets}, updated_at=datetime('now') WHERE id=?",
            *fields.values(), listing_id,
        )

    async def get_listing(self, listing_id: int) -> dict | None:
        return await self.fetchone("SELECT * FROM listings WHERE id=?", listing_id)

    async def delete_listing(self, listing_id: int) -> None:
        await self.execute("DELETE FROM listings WHERE id=?", listing_id)

    async def listings_by_status(
        self, statuses: Iterable[str], limit: int = 10, offset: int = 0
    ) -> list[dict]:
        statuses = list(statuses)
        marks = ",".join("?" for _ in statuses)
        return await self.fetchall(
            f"""SELECT * FROM listings WHERE status IN ({marks})
                ORDER BY COALESCE(published_at, created_at) DESC LIMIT ? OFFSET ?""",
            *statuses, limit, offset,
        )

    async def count_by_status(self, statuses: Iterable[str]) -> int:
        statuses = list(statuses)
        marks = ",".join("?" for _ in statuses)
        return await self.scalar(
            f"SELECT COUNT(*) FROM listings WHERE status IN ({marks})", *statuses
        )

    async def active_listings(self) -> list[dict]:
        return await self.fetchall(
            "SELECT * FROM listings WHERE status='active' ORDER BY published_at DESC"
        )

    async def published_since(self, since_iso: str) -> list[dict]:
        return await self.fetchall(
            "SELECT * FROM listings WHERE status='active' AND published_at>=? ORDER BY published_at DESC",
            since_iso,
        )

    # ---------- media ----------
    async def add_media(self, listing_id: int, kind: str, file_id: str, position: int) -> int:
        return await self.execute(
            "INSERT INTO listing_media (listing_id, kind, file_id, position) VALUES (?, ?, ?, ?)",
            listing_id, kind, file_id, position,
        )

    async def get_media(self, listing_id: int) -> list[dict]:
        return await self.fetchall(
            "SELECT * FROM listing_media WHERE listing_id=? ORDER BY position", listing_id
        )

    async def update_media(self, media_id: int, **fields: Any) -> None:
        fields = {k: v for k, v in fields.items() if k in {"file_id", "local_path", "ready"}}
        sets = ", ".join(f"{k}=?" for k in fields)
        await self.execute(f"UPDATE listing_media SET {sets} WHERE id=?", *fields.values(), media_id)

    async def delete_media(self, listing_id: int) -> None:
        await self.execute("DELETE FROM listing_media WHERE listing_id=?", listing_id)

    async def media_count(self, listing_id: int) -> int:
        return await self.scalar("SELECT COUNT(*) FROM listing_media WHERE listing_id=?", listing_id)

    # ---------- saqlanganlar ----------
    async def add_favorite(self, user_id: int, listing_id: int) -> bool:
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO favorites (user_id, listing_id) VALUES (?, ?)", (user_id, listing_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def remove_favorite(self, user_id: int, listing_id: int) -> None:
        await self.execute("DELETE FROM favorites WHERE user_id=? AND listing_id=?", user_id, listing_id)

    async def user_favorites(self, user_id: int) -> list[dict]:
        return await self.fetchall(
            """SELECT l.* FROM favorites f JOIN listings l ON l.id=f.listing_id
               WHERE f.user_id=? ORDER BY f.created_at DESC LIMIT 30""",
            user_id,
        )

    async def favorite_user_ids(self, listing_id: int) -> list[int]:
        rows = await self.fetchall(
            """SELECT f.user_id FROM favorites f JOIN users u ON u.id=f.user_id
               WHERE f.listing_id=? AND u.active=1""",
            listing_id,
        )
        return [r["user_id"] for r in rows]

    # ---------- lidlar ----------
    async def add_lead(self, user_id: int, listing_id: int | None, kind: str) -> None:
        await self.execute(
            "INSERT INTO leads (user_id, listing_id, kind) VALUES (?, ?, ?)", user_id, listing_id, kind
        )

    async def add_seller_request(self, **f: Any) -> int:
        return await self.execute(
            """INSERT INTO seller_requests (user_id, district, rooms, price, description, phone)
               VALUES (?, ?, ?, ?, ?, ?)""",
            f["user_id"], f.get("district"), f.get("rooms"), f.get("price"),
            f.get("description"), f.get("phone"),
        )

    # ---------- meta ----------
    async def get_meta(self, key: str) -> str | None:
        return await self.scalar("SELECT value FROM meta WHERE key=?", key)

    async def set_meta(self, key: str, value: str) -> None:
        await self.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            key, value,
        )

    # ---------- statistika ----------
    async def listing_stats(self, listing_id: int) -> dict:
        return {
            "leads": await self.scalar(
                "SELECT COUNT(*) FROM leads WHERE listing_id=? AND kind='call'", listing_id),
            "favs": await self.scalar(
                "SELECT COUNT(*) FROM favorites WHERE listing_id=?", listing_id),
            "clicks": await self.scalar(
                "SELECT COUNT(*) FROM leads WHERE listing_id=?", listing_id),
        }

    async def stats(self) -> dict:
        s = {}
        s["users"] = await self.scalar("SELECT COUNT(*) FROM users")
        s["active"] = await self.scalar("SELECT COUNT(*) FROM users WHERE active=1")
        s["blocked"] = s["users"] - s["active"]
        s["with_filter"] = await self.scalar(
            "SELECT COUNT(*) FROM filters f JOIN users u ON u.id=f.user_id WHERE u.active=1 AND u.notify_mode!='off'")
        s["with_phone"] = await self.scalar("SELECT COUNT(*) FROM users WHERE phone IS NOT NULL")
        s["new_today"] = await self.scalar(
            "SELECT COUNT(*) FROM users WHERE created_at>=datetime('now','-1 day')")
        s["new_week"] = await self.scalar(
            "SELECT COUNT(*) FROM users WHERE created_at>=datetime('now','-7 day')")
        s["listings_active"] = await self.count_by_status(["active", "reserved"])
        s["listings_sold"] = await self.count_by_status(["sold"])
        s["leads_today"] = await self.scalar(
            "SELECT COUNT(*) FROM leads WHERE kind='call' AND created_at>=datetime('now','-1 day')")
        s["leads_week"] = await self.scalar(
            "SELECT COUNT(*) FROM leads WHERE kind='call' AND created_at>=datetime('now','-7 day')")
        s["sellers_week"] = await self.scalar(
            "SELECT COUNT(*) FROM seller_requests WHERE created_at>=datetime('now','-7 day')")
        s["top_listings"] = await self.fetchall(
            """SELECT l.id, l.district, l.rooms, l.price, l.deal, COUNT(*) AS n
               FROM leads ld JOIN listings l ON l.id=ld.listing_id
               WHERE ld.created_at>=datetime('now','-30 day')
               GROUP BY l.id ORDER BY n DESC LIMIT 5""")
        s["filter_districts"] = await self.fetchall("SELECT districts FROM filters")
        return s
