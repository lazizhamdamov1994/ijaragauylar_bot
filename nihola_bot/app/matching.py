"""Mijoz filtri va e'lonni solishtirish ("sizga mos uy chiqdi")."""
from __future__ import annotations

from .constants import DISTRICT_NAME
from .texts import fmt_num


def csv(value: str | None) -> list[str]:
    return [x for x in (value or "").split(",") if x]


def rooms_match(rooms: int | None, wanted: list[str]) -> bool:
    if not wanted:
        return True
    r = int(rooms or 0)
    for w in wanted:
        if w == "4" and r >= 4:
            return True
        if w.isdigit() and int(w) == r:
            return True
    return False


def listing_matches(listing: dict, f: dict) -> bool:
    if f.get("deal") and f["deal"] != listing.get("deal"):
        return False
    districts = csv(f.get("districts"))
    if districts and listing.get("district") not in districts:
        return False
    if not rooms_match(listing.get("rooms"), csv(f.get("rooms"))):
        return False
    price = listing.get("price") or 0
    if f.get("price_min") and price < f["price_min"]:
        return False
    if f.get("price_max") and price > f["price_max"]:
        return False
    return True


def filter_from_listing(listing: dict) -> dict:
    """"Shunga o'xshash uylar" tugmasi uchun e'lon asosida filtr tuzadi (narx ±20%)."""
    price = listing.get("price") or 0
    step = 100 if listing.get("deal") == "rent" else 1000
    rooms = listing.get("rooms")
    return {
        "deal": listing.get("deal"),
        "districts": listing.get("district") or "",
        "rooms": str(min(int(rooms), 4)) if rooms else "",
        "price_min": int(price * 0.8 // step * step) if price else None,
        "price_max": int(-(-price * 1.2 // step) * step) if price else None,
    }


def describe_filter(f: dict | None, mode: str | None = None) -> str:
    if not f:
        return "Filtr hali sozlanmagan."
    deal = {"sale": "Sotib olish", "rent": "Ijaraga olish"}.get(f.get("deal"), "Sotib olish va ijara")
    districts = ", ".join(DISTRICT_NAME.get(d, d) for d in csv(f.get("districts"))) or "Barcha tumanlar"
    rooms = ", ".join(("4+" if r == "4" else r) for r in csv(f.get("rooms")))
    rooms = f"{rooms} xona" if rooms else "Farqi yo‘q"
    pmin, pmax = f.get("price_min"), f.get("price_max")
    if pmin and pmax:
        budget = f"{fmt_num(pmin)}$ – {fmt_num(pmax)}$"
    elif pmax:
        budget = f"{fmt_num(pmax)}$ gacha"
    elif pmin:
        budget = f"{fmt_num(pmin)}$ dan yuqori"
    else:
        budget = "Farqi yo‘q"
    lines = [
        f"🏷 Maqsad: <b>{deal}</b>",
        f"📍 Tuman: <b>{districts}</b>",
        f"🏠 Xonalar: <b>{rooms}</b>",
        f"💰 Byudjet: <b>{budget}</b>",
    ]
    if mode:
        m = {"instant": "⚡ Darhol", "daily": "🗓 Kuniga 1 marta", "off": "🔕 O‘chirilgan"}.get(mode, mode)
        lines.append(f"🔔 Xabarnoma: <b>{m}</b>")
    return "\n".join(lines)
