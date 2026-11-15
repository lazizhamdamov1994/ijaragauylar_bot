"""E'lon postini formatlash (kanal posti shu yerda yig'iladi)."""
from __future__ import annotations

import re
from html import escape as h, unescape

from .config import settings
from .constants import DISTRICT_NAME, DISTRICT_TAG, HEADERS, PTYPE_TAG, district_label

CAPTION_LIMIT = 1024


def fmt_num(n: int | float | None) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def fmt_price(listing: dict) -> str:
    p = fmt_num(listing.get("price"))
    return f"{p}$ / oy" if listing.get("deal") == "rent" else f"{p}$"


def fmt_area(a: float | None) -> str:
    if a is None:
        return ""
    a = float(a)
    return str(int(a)) if a.is_integer() else f"{a:g}".replace(".", ",")


def code(listing_id: int) -> str:
    return f"N{listing_id:04d}"


def status_banner(listing: dict) -> str:
    st = listing.get("status")
    if st == "sold":
        return "✅ <b>IJARAGA BERILDI</b>" if listing.get("deal") == "rent" else "✅ <b>SOTILDI</b>"
    if st == "reserved":
        return "⏸ <b>BAND QILINGAN (zaklad)</b>"
    return ""


def hashtags(listing: dict) -> str:
    tags = [f"#{code(listing['id'])}"]
    if listing.get("district") in DISTRICT_TAG:
        tags.append("#" + DISTRICT_TAG[listing["district"]])
    if listing.get("rooms"):
        tags.append(f"#{listing['rooms']}xona")
    if listing.get("ptype") in PTYPE_TAG:
        tags.append("#" + PTYPE_TAG[listing["ptype"]])
    if listing.get("deal") == "rent":
        tags.append("#ijara")
    return " ".join(tags)


def build_post(listing: dict) -> str:
    """Kanal posti matni (HTML). Format rieltor namunasiga mos."""
    lines: list[str] = []
    banner = status_banner(listing)
    if banner:
        lines += [banner, ""]

    header = HEADERS.get((listing.get("deal"), listing.get("ptype")), "🏠 E’LON")
    lines += [f"<b>{header}</b>", ""]

    addr = district_label(listing.get("district"))
    if listing.get("address"):
        addr = f"{addr}, {h(listing['address'])}" if addr else h(listing["address"])
    lines += [f"📍 Manzil: {addr}", ""]

    if listing.get("floor"):
        lines.append(f"🏢 Qavat: {h(str(listing['floor']))}")
    if listing.get("rooms"):
        lines.append(f"🏠 Xonalar: {listing['rooms']} xona")
    if listing.get("area"):
        lines.append(f"📐 Umumiy maydoni: {fmt_area(listing['area'])} m²")
    if listing.get("balcony"):
        lines.append(f"🌿 Balkon: {h(listing['balcony'])}")
    if listing.get("bathroom"):
        lines.append(f"🚿 Sanuzel: {h(listing['bathroom'])}")
    if listing.get("renovation"):
        lines.append(f"✨ {h(listing['renovation'])}")
    if listing.get("furniture"):
        lines.append(f"🛋 {h(listing['furniture'])}")

    extra: list[str] = []
    if listing.get("landmark"):
        extra.append(f"📍 Mo‘ljal: {h(listing['landmark'])}")
    for line in (listing.get("extra") or "").splitlines():
        if line.strip():
            extra.append(h(line.strip()))
    if extra:
        lines += [""] + extra

    lines += ["", f"💰 <b>Narxi: {fmt_price(listing)}</b>", ""]
    lines.append(hashtags(listing))
    if settings.realtor_phone:
        lines.append(f"📞 {h(settings.realtor_phone)}")
    return "\n".join(lines)


def visible_len(html_text: str) -> int:
    """Telegram limitini tekshirish uchun HTML teglarsiz uzunlik."""
    return len(unescape(re.sub(r"<[^>]+>", "", html_text)))


def short_title(listing: dict) -> str:
    parts = [f"#{code(listing['id'])}", DISTRICT_NAME.get(listing.get("district") or "", "—")]
    if listing.get("rooms"):
        parts.append(f"{listing['rooms']} xona")
    if listing.get("area"):
        parts.append(f"{fmt_area(listing['area'])} m²")
    parts.append(fmt_price(listing))
    return " · ".join(parts)


STATUS_ICON = {"active": "🟢", "reserved": "⏸", "sold": "✅", "draft": "📝"}
