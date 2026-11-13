"""Buyurtmalar: yaratish, holatini o'zgartirish, ro'yxat. Telegram'ga bog'liq emas."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Order, OrderItem, OrderStatus, Product, ProductVariant, Seller
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.services.ids import generate_public_id
from app.services.parsing import clean_text, normalize_phone

MAX_QTY = 100

# Qaysi holatdan qaysi holatga o'tish mumkin
TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}
OPEN_STATUSES = (OrderStatus.NEW, OrderStatus.CONFIRMED, OrderStatus.SHIPPED)


@dataclass
class OrderRequest:
    product_id: int
    variant_id: int
    quantity: int
    buyer_telegram_id: int | None
    buyer_name: str
    buyer_phone: str
    address: str
    comment: str | None = None
    source: str = "telegram"


def available_variants(product: Product) -> list[ProductVariant]:
    return [v for v in product.variants if v.stock > 0]


def validate_address(value: str | None) -> str:
    v = clean_text(value)
    if not 5 <= len(v) <= 500:
        raise ValidationError("order_address_invalid")
    return v


def validate_quantity(qty: int, stock: int) -> int:
    if qty < 1 or qty > MAX_QTY:
        raise ValidationError("order_qty_invalid", max=min(stock, MAX_QTY))
    if qty > stock:
        raise ConflictError("order_not_enough_stock", stock=stock)
    return qty


async def create_order(session: AsyncSession, req: OrderRequest) -> Order:
    """Buyurtma yaratadi va qoldiqdan ayiradi (bir vaqtda ikki kishi olsa ham to'g'ri ishlaydi)."""
    product = await session.get(Product, req.product_id)
    if product is None or not product.is_active:
        raise NotFoundError("buyer_product_unavailable")
    seller = await session.get(Seller, product.seller_id)
    if seller is None or not seller.is_active:
        raise NotFoundError("buyer_product_unavailable")

    # Qatorni qulflab o'qiymiz: parallel buyurtmalar qoldiqni manfiy qilib qo'ymasin
    variant = await session.scalar(
        select(ProductVariant)
        .where(ProductVariant.id == req.variant_id, ProductVariant.product_id == product.id)
        .with_for_update()
    )
    if variant is None:
        raise NotFoundError("order_variant_gone")
    qty = validate_quantity(req.quantity, variant.stock)

    name = clean_text(req.buyer_name)[:100] or "—"
    phone = normalize_phone(req.buyer_phone)
    address = validate_address(req.address)
    comment = clean_text(req.comment)[:1000] or None

    variant.stock -= qty
    order = Order(
        public_id=generate_public_id(),
        seller_id=seller.id,
        buyer_telegram_id=req.buyer_telegram_id,
        buyer_name=name,
        buyer_phone=phone,
        address=address,
        comment=comment,
        status=OrderStatus.NEW,
        total=product.price * qty,
        source=req.source,
        items=[
            OrderItem(
                product_id=product.id,
                variant_id=variant.id,
                product_name=product.name,
                size=variant.size,
                color=variant.color,
                quantity=qty,
                unit_price=product.price,
            )
        ],
    )
    session.add(order)
    await session.flush()
    return order


async def get_seller_order(session: AsyncSession, seller_id: int, order_id: int) -> Order:
    order = await session.scalar(
        select(Order).where(Order.id == order_id, Order.seller_id == seller_id)
    )
    if order is None:
        raise NotFoundError("order_not_found")
    return order


async def change_status(
    session: AsyncSession, seller_id: int, order_id: int, new_status: OrderStatus
) -> Order:
    """Holatni o'zgartiradi. Bekor qilinsa — tovar qoldig'i qaytariladi."""
    order = await get_seller_order(session, seller_id, order_id)
    if new_status not in TRANSITIONS[order.status]:
        raise ConflictError("order_status_not_allowed")
    if new_status == OrderStatus.CANCELLED:
        for item in order.items:
            if item.variant_id is not None:
                variant = await session.scalar(
                    select(ProductVariant).where(ProductVariant.id == item.variant_id).with_for_update()
                )
                if variant is not None:
                    variant.stock += item.quantity
    order.status = new_status
    await session.flush()
    return order


async def list_seller_orders(
    session: AsyncSession, seller_id: int, only_open: bool = False, limit: int = 20, offset: int = 0
) -> list[Order]:
    stmt = select(Order).where(Order.seller_id == seller_id)
    if only_open:
        stmt = stmt.where(Order.status.in_(OPEN_STATUSES))
    # Yangilari tepada: avval "yangi" holatdagilar, keyin qolganlari
    stmt = stmt.order_by(case((Order.status == OrderStatus.NEW, 0), else_=1), Order.id.desc())
    return list(await session.scalars(stmt.limit(limit).offset(offset)))


async def count_seller_orders(session: AsyncSession, seller_id: int, only_open: bool = False) -> int:
    stmt = select(func.count(Order.id)).where(Order.seller_id == seller_id)
    if only_open:
        stmt = stmt.where(Order.status.in_(OPEN_STATUSES))
    return await session.scalar(stmt) or 0


async def last_buyer_phone(session: AsyncSession, buyer_telegram_id: int) -> str | None:
    """Xaridor oldin buyurtma bergan bo'lsa — raqamini qayta so'ramaslik uchun."""
    return await session.scalar(
        select(Order.buyer_phone)
        .where(Order.buyer_telegram_id == buyer_telegram_id)
        .order_by(Order.id.desc())
        .limit(1)
    )


def order_total(items: list[OrderItem]) -> Decimal:
    return sum((i.unit_price * i.quantity for i in items), Decimal(0))
