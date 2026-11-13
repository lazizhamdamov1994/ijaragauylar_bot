"""Tovar kartochkasi va post matnlarini yasash (HTML)."""
from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from functools import partial
from html import escape as _escape

escape = partial(_escape, quote=False)

from app.db.models import Product
from app.services.dto import ProductDraft, ProductView, VariantData
from app.texts import t

CAPTION_LIMIT = 1024  # Telegram rasm izohi chegarasi
MESSAGE_LIMIT = 4096


def format_price(price: Decimal) -> str:
    """Decimal('250000.00') → '250 000'."""
    q = price.quantize(Decimal("0.01"))
    whole = int(q)
    s = f"{whole:,}".replace(",", " ")
    frac = q - whole
    if frac:
        s += "," + f"{frac:.2f}"[2:]
    return s


def format_variants(variants: list[VariantData]) -> list[str]:
    """Mavjud (soni > 0) variantlarni rang bo'yicha guruhlab qatorlarga aylantiradi."""
    groups: OrderedDict[str, list[str]] = OrderedDict()
    for v in variants:
        if v.stock <= 0:
            continue
        groups.setdefault(v.color, [])
        if v.size and v.size not in groups[v.color]:
            groups[v.color].append(v.size)
    lines = []
    for color, sizes in groups.items():
        parts = []
        if color:
            parts.append(f"<b>{escape(color.capitalize())}</b>")
        if sizes:
            parts.append(", ".join(escape(s) for s in sizes))
        if parts:
            lines.append("• " + ": ".join(parts))
    return lines


def build_caption(view: ProductView, lang: str = "uz", limit: int = CAPTION_LIMIT) -> str:
    head = [f"<b>{escape(view.name)}</b>"]
    tail = ["", t("post_price", lang, price=format_price(view.price))]
    in_stock = any(v.stock > 0 for v in view.variants)
    if not in_stock:
        tail.append(t("post_out_of_stock", lang))
    else:
        lines = format_variants(view.variants)
        if lines:
            tail += ["", t("post_variants_title", lang), *lines]
    if view.shop_name:
        tail += ["", t("post_shop", lang, shop=escape(view.shop_name))]

    body = "\n".join(head + tail)
    if view.description:
        desc = escape(view.description)
        room = limit - len(body) - 2
        if room > 20:
            if len(desc) > room:
                desc = desc[: room - 1].rsplit(" ", 1)[0] + "…"
            body = "\n".join(head + ["", desc] + tail)
    return body[:limit]


def view_from_draft(draft: ProductDraft, shop_name: str = "") -> ProductView:
    return ProductView(
        name=draft.name,
        price=draft.price or Decimal(0),
        description=draft.description,
        variants=list(draft.variants),
        shop_name=shop_name,
    )


def view_from_product(product: Product, shop_name: str = "") -> ProductView:
    return ProductView(
        name=product.name,
        price=product.price,
        description=product.description,
        variants=[VariantData(v.size, v.color, v.stock) for v in product.variants],
        shop_name=shop_name,
    )


def variants_list_text(variants: list[VariantData], lang: str = "uz") -> str:
    if not variants:
        return t("variants_empty", lang)
    return "\n".join(f"• {escape(v.label())} — {v.stock} ta" for v in variants)
