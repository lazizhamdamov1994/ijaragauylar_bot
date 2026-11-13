"""Foydalanuvchi kiritgan matnni tekshirish va tushunish."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.services.dto import VariantData
from app.services.errors import ValidationError

MAX_PRICE = Decimal("1000000000")  # 1 mlrd so'm
MAX_STOCK = 100_000


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def validate_shop_name(value: str | None) -> str:
    v = clean_text(value)
    if not 2 <= len(v) <= 100:
        raise ValidationError("shop_name_invalid")
    return v


def validate_product_name(value: str | None) -> str:
    v = clean_text(value)
    if not 2 <= len(v) <= 200:
        raise ValidationError("name_invalid")
    return v


def validate_description(value: str | None) -> str | None:
    v = (value or "").strip()
    if not v:
        return None
    if len(v) > 2000:
        raise ValidationError("description_too_long")
    return v


def normalize_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not 9 <= len(digits) <= 15:
        raise ValidationError("phone_use_button")
    if len(digits) == 9:  # mahalliy raqam: 90 123 45 67
        digits = "998" + digits
    return "+" + digits


def parse_price(value: str | None) -> Decimal:
    """'250000', '250 000', '250.000', '250,000', '250k', '250 ming', '1.5 mln' → Decimal."""
    raw = (value or "").strip().lower().replace("so'm", "").replace("sum", "").replace("сум", "")
    multiplier = Decimal(1)
    for suffix, mult in (("mln", 1_000_000), ("million", 1_000_000), ("ming", 1000), ("k", 1000)):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)].strip()
            multiplier = Decimal(mult)
            break
    raw = raw.replace(" ", "").replace(" ", "")
    if not raw or not re.fullmatch(r"[\d.,]+", raw):
        raise ValidationError("price_invalid")
    # Ming ajratgich: "250.000" / "1,250,000". Kasr faqat ko'paytiruvchi bilan: "1.5 mln"
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", raw) and multiplier == 1:
        raw = re.sub(r"[.,]", "", raw)
    else:
        raw = raw.replace(",", ".")
        if raw.count(".") > 1:
            raise ValidationError("price_invalid")
    try:
        price = (Decimal(raw) * multiplier).quantize(Decimal("0.01"))
    except InvalidOperation as e:
        raise ValidationError("price_invalid") from e
    if price <= 0 or price > MAX_PRICE:
        raise ValidationError("price_invalid")
    return price


def parse_stock(value: str | None) -> int:
    v = (value or "").strip()
    if not v.isdigit() or int(v) > MAX_STOCK:
        raise ValidationError("qty_invalid")
    return int(v)


def parse_variant_line(line: str) -> VariantData:
    """'S qora 5' → (S, qora, 5); 'M 10' → (M, '', 10); '10' → ('', '', 10); 'to'q ko'k L 2'? → razmer birinchi."""
    tokens = [t for t in re.split(r"[\s,;]+", line.strip()) if t]
    if not tokens:
        raise ValidationError("variants_parse_error")
    qty_token = tokens[-1].lower().removesuffix("ta").removesuffix("x")
    if not qty_token.isdigit():
        raise ValidationError("variants_parse_error")
    stock = int(qty_token)
    if stock > MAX_STOCK:
        raise ValidationError("variants_parse_error")
    rest = tokens[:-1]
    size = rest[0][:20] if rest else ""
    color = " ".join(rest[1:])[:50]
    return VariantData(size=size.upper() if len(size) <= 4 else size, color=color.lower(), stock=stock)


def parse_variants(text: str) -> tuple[list[VariantData], list[str]]:
    """Ko'p qatorli matnni o'qiydi. (topilganlar, tushunilmagan qatorlar) qaytaradi."""
    ok: list[VariantData] = []
    bad: list[str] = []
    for line in re.split(r"[\n;]+", text or ""):
        if not line.strip():
            continue
        try:
            ok.append(parse_variant_line(line))
        except ValidationError:
            bad.append(line.strip())
    return ok, bad


def merge_variants(existing: list[VariantData], new: list[VariantData]) -> list[VariantData]:
    """Bir xil razmer+rang bo'lsa sonini qo'shadi, aks holda oxiriga qo'shadi."""
    result = [VariantData(v.size, v.color, v.stock) for v in existing]
    index = {v.key(): v for v in result}
    for v in new:
        if v.key() in index:
            index[v.key()].stock = min(index[v.key()].stock + v.stock, MAX_STOCK)
        else:
            item = VariantData(v.size, v.color, v.stock)
            result.append(item)
            index[item.key()] = item
    return result
