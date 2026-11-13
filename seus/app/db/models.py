"""Ma'lumotlar bazasi jadvallari."""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

Money = Numeric(14, 2)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Seller(TimestampMixin, Base):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    shop_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(5), default="uz")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    channels: Mapped[list[Channel]] = relationship(back_populates="seller")
    products: Mapped[list[Product]] = relationship(back_populates="seller")


class Channel(TimestampMixin, Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"))
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    seller: Mapped[Seller] = relationship(back_populates="channels")


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Havolalarda ishlatiladigan, taxmin qilib bo'lmaydigan qisqa ID
    public_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Money)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    seller: Mapped[Seller] = relationship(back_populates="products")
    media: Mapped[list[ProductMedia]] = relationship(
        back_populates="product",
        order_by="ProductMedia.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product",
        order_by="ProductVariant.id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    posts: Mapped[list[ChannelPost]] = relationship(back_populates="product")


class ProductMedia(Base):
    """Tovar rasmi yoki videosi (Telegram file_id saqlanadi, fayl yuklab olinmaydi)."""

    __tablename__ = "product_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10), default="photo", server_default="photo")  # photo / video
    file_id: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="media")


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    size: Mapped[str] = mapped_column(String(20), default="")
    color: Mapped[str] = mapped_column(String(50), default="")
    stock: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="variants")


class ChannelPost(TimestampMixin, Base):
    __tablename__ = "channel_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    # Albomdagi rasmlar + tugmali xabar — hammasining message_id'lari
    message_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    # Tugmalar turgan xabar (keyin tahrirlash uchun)
    button_message_id: Mapped[int] = mapped_column(BigInteger)

    product: Mapped[Product] = relationship(back_populates="posts")
    channel: Mapped[Channel] = relationship()


class OrderStatus(str, enum.Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Order(TimestampMixin, Base):
    """2-bosqichda ishlatiladi."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"))
    buyer_telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    buyer_name: Mapped[str] = mapped_column(String(100), default="")
    buyer_phone: Mapped[str] = mapped_column(String(20), default="")
    address: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", values_callable=lambda e: [x.value for x in e]),
        default=OrderStatus.NEW,
    )
    total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(20), default="telegram")  # telegram / web
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (UniqueConstraint("order_id", "product_id", "variant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL")
    )
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL")
    )
    # Buyurtma paytidagi holat saqlanadi (keyin tovar o'zgarsa ham)
    product_name: Mapped[str] = mapped_column(String(200))
    size: Mapped[str] = mapped_column(String(20), default="")
    color: Mapped[str] = mapped_column(String(50), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Money)

    order: Mapped[Order] = relationship(back_populates="items")
