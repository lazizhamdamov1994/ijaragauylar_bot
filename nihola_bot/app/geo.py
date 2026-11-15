"""Google / Yandex xarita havolasidan yoki "41.28, 69.20" matnidan koordinatalarni ajratish."""
from __future__ import annotations

import re

import aiohttp

NUM = r"(-?\d{1,3}\.\d+)"
SHORT_HOSTS = ("goo.gl", "maps.app", "yandex.uz/maps/-/", "yandex.ru/maps/-/", "yandex.com/maps/-/")


def _valid(lat: float, lng: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lng <= 180


def parse_coords(text: str) -> tuple[float, float] | None:
    t = text.strip()
    # Yandex: ll=lng,lat yoki pt=lng,lat (tartibi teskari!)
    if "yandex" in t:
        m = re.search(rf"(?:pt|ll|whatshere%5Bpoint%5D)=?{NUM}(?:,|%2C){NUM}", t)
        if m:
            lng, lat = float(m.group(1)), float(m.group(2))
            if _valid(lat, lng):
                return lat, lng
    patterns = [
        rf"!3d{NUM}!4d{NUM}",          # Google: aniq nuqta
        rf"@{NUM},{NUM}",              # Google: xarita markazi
        rf"[?&](?:q|query|ll|daddr)=(?:loc:)?{NUM}(?:,|%2C)\+?{NUM}",
        rf"^{NUM}\s*[,; ]\s*{NUM}$",   # oddiy "41.28, 69.20"
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))
            if _valid(lat, lng):
                return lat, lng
    return None


async def resolve_location(text: str) -> tuple[float, float] | None:
    coords = parse_coords(text)
    if coords:
        return coords
    url = re.search(r"https?://\S+", text)
    if url and any(h in url.group(0) for h in SHORT_HOSTS):
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(url.group(0), allow_redirects=True) as r:
                    final = str(r.url)
                    body = await r.text(errors="ignore") if not parse_coords(final) else ""
            return parse_coords(final) or (parse_coords(body[:200000]) if body else None)
        except Exception:
            return None
    return None
