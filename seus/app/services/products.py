from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChannelPost, Product, ProductPhoto, ProductVariant, Seller
from app.services.dto import ProductDraft
from app.services.errors import NotFoundError, ValidationError
from app.services.ids import generate_public_id, is_valid_public_id
from app.services.parsing import validate_description, validate_product_name

MAX_PHOTOS = 10


def validate_draft(draft: ProductDraft) -> ProductDraft:
    if not 1 <= len(draft.photo_file_ids) <= MAX_PHOTOS:
        raise ValidationError("photos_need_one")
    draft.name = validate_product_name(draft.name)
    if draft.price is None or draft.price <= 0:
        raise ValidationError("price_invalid")
    if not draft.variants:
        raise ValidationError("variants_need_one")
    draft.description = validate_description(draft.description)
    return draft


async def create_product(session: AsyncSession, seller: Seller, draft: ProductDraft) -> Product:
    draft = validate_draft(draft)
    for _ in range(5):  # public_id to'qnashuvi deyarli imkonsiz, lekin baribir tekshiramiz
        public_id = generate_public_id()
        exists = await session.scalar(select(Product.id).where(Product.public_id == public_id))
        if not exists:
            break
    product = Product(
        public_id=public_id,
        seller_id=seller.id,
        name=draft.name,
        price=draft.price,
        description=draft.description,
        is_active=True,
        photos=[ProductPhoto(file_id=f, position=i) for i, f in enumerate(draft.photo_file_ids)],
        variants=[
            ProductVariant(size=v.size, color=v.color, stock=v.stock) for v in draft.variants
        ],
    )
    session.add(product)
    await session.flush()
    return product


async def get_by_public_id(
    session: AsyncSession, public_id: str, only_active: bool = True
) -> Product | None:
    if not is_valid_public_id(public_id):
        return None
    stmt = select(Product).where(Product.public_id == public_id)
    if only_active:
        stmt = stmt.join(Seller).where(Product.is_active.is_(True), Seller.is_active.is_(True))
    return await session.scalar(stmt)


async def get_seller_product(session: AsyncSession, seller_id: int, product_id: int) -> Product:
    product = await session.scalar(
        select(Product).where(Product.id == product_id, Product.seller_id == seller_id)
    )
    if product is None:
        raise NotFoundError("product_not_found")
    return product


async def list_seller_products(
    session: AsyncSession, seller_id: int, limit: int = 50, offset: int = 0
) -> list[Product]:
    result = await session.scalars(
        select(Product)
        .where(Product.seller_id == seller_id)
        .order_by(Product.is_active.desc(), Product.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result)


async def count_seller_products(session: AsyncSession, seller_id: int) -> int:
    return await session.scalar(
        select(func.count(Product.id)).where(Product.seller_id == seller_id)
    ) or 0


async def set_active(
    session: AsyncSession, seller_id: int, product_id: int, active: bool
) -> Product:
    product = await get_seller_product(session, seller_id, product_id)
    product.is_active = active
    await session.flush()
    return product


async def record_channel_post(
    session: AsyncSession,
    product_id: int,
    channel_id: int,
    message_ids: list[int],
    button_message_id: int,
) -> ChannelPost:
    post = ChannelPost(
        product_id=product_id,
        channel_id=channel_id,
        message_ids=list(message_ids),
        button_message_id=button_message_id,
    )
    session.add(post)
    await session.flush()
    return post


async def count_posts(session: AsyncSession, product_id: int) -> int:
    return await session.scalar(
        select(func.count(ChannelPost.id)).where(ChannelPost.product_id == product_id)
    ) or 0
