"""Oddiy ma'lumot tuzilmalari (bazaga ham, Telegramga ham bog'liq emas)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal


@dataclass
class VariantData:
    size: str = ""
    color: str = ""
    stock: int = 0

    def key(self) -> tuple[str, str]:
        return (self.size.lower(), self.color.lower())

    def label(self) -> str:
        return " ".join(p for p in (self.size, self.color) if p) or "—"


@dataclass
class MediaItem:
    kind: str  # "photo" yoki "video"
    file_id: str


@dataclass
class ProductDraft:
    """Tovar qo'shilayotgan paytdagi qoralama (FSM'da dict ko'rinishida saqlanadi)."""

    media: list[MediaItem] = field(default_factory=list)
    name: str = ""
    price: Decimal | None = None
    variants: list[VariantData] = field(default_factory=list)
    description: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["price"] = str(self.price) if self.price is not None else None
        return d

    @classmethod
    def from_dict(cls, d: dict | None) -> ProductDraft:
        d = d or {}
        price = d.get("price")
        return cls(
            media=[MediaItem(**m) for m in d.get("media") or []],
            name=d.get("name") or "",
            price=Decimal(price) if price is not None else None,
            variants=[VariantData(**v) for v in d.get("variants") or []],
            description=d.get("description"),
        )


@dataclass
class ProductView:
    """Post/kartochka matnini yasash uchun kerakli ma'lumot."""

    name: str
    price: Decimal
    description: str | None
    variants: list[VariantData]
    shop_name: str = ""
