from decimal import Decimal

import pytest

from app.db.models import Order, OrderItem, OrderStatus, Seller
from app.services import channels as channel_svc
from app.services import products as svc
from app.services.dto import MediaItem, ProductDraft, VariantData
from app.services.errors import NotFoundError, ValidationError


def draft(**kw) -> ProductDraft:
    base = dict(
        media=[MediaItem("photo", "photo1"), MediaItem("video", "video1")],
        name="Ko'ylak",
        price=Decimal("250000"),
        variants=[VariantData("S", "qora", 5), VariantData("M", "oq", 2)],
        description="Paxta",
    )
    base.update(kw)
    return ProductDraft(**base)


async def test_create_product(session, seller):
    p = await svc.create_product(session, seller, draft())
    assert p.id and len(p.public_id) == 10 and p.is_active
    assert [(m.kind, m.file_id) for m in p.media] == [("photo", "photo1"), ("video", "video1")]
    assert [m.position for m in p.media] == [0, 1]
    assert [(v.size, v.color, v.stock) for v in p.variants] == [("S", "qora", 5), ("M", "oq", 2)]
    assert p.price == Decimal("250000")


@pytest.mark.parametrize(
    "kw, code",
    [
        ({"media": []}, "photos_need_one"),
        ({"media": [MediaItem("photo", f"p{i}") for i in range(11)]}, "photos_need_one"),
        ({"media": [MediaItem("document", "d1")]}, "photos_only"),
        ({"name": "x"}, "name_invalid"),
        ({"price": None}, "price_invalid"),
        ({"variants": []}, "variants_need_one"),
    ],
)
async def test_create_product_validation(session, seller, kw, code):
    with pytest.raises(ValidationError) as e:
        await svc.create_product(session, seller, draft(**kw))
    assert e.value.code == code


async def test_get_by_public_id(session, seller):
    p = await svc.create_product(session, seller, draft())
    assert (await svc.get_by_public_id(session, p.public_id)).id == p.id
    assert await svc.get_by_public_id(session, "yoqIdXXXXX") is None
    assert await svc.get_by_public_id(session, "bad-id!") is None
    await svc.set_active(session, seller.id, p.id, False)
    assert await svc.get_by_public_id(session, p.public_id) is None
    assert (await svc.get_by_public_id(session, p.public_id, only_active=False)).id == p.id


async def test_inactive_seller_hides_products(session, seller):
    p = await svc.create_product(session, seller, draft())
    seller.is_active = False
    await session.flush()
    assert await svc.get_by_public_id(session, p.public_id) is None


async def test_list_count_and_ownership(session, seller):
    a = await svc.create_product(session, seller, draft(name="Birinchi"))
    b = await svc.create_product(session, seller, draft(name="Ikkinchi"))
    await svc.set_active(session, seller.id, a.id, False)
    items = await svc.list_seller_products(session, seller.id)
    assert [p.id for p in items] == [b.id, a.id]  # faollar oldin
    assert await svc.count_seller_products(session, seller.id) == 2

    other = Seller(telegram_id=999, shop_name="Begona", phone="+998900000001")
    session.add(other)
    await session.flush()
    with pytest.raises(NotFoundError):
        await svc.get_seller_product(session, other.id, a.id)
    with pytest.raises(NotFoundError):
        await svc.set_active(session, other.id, a.id, True)


async def test_record_channel_post(session, seller):
    p = await svc.create_product(session, seller, draft())
    ch = await channel_svc.link_channel(session, seller, -1001, "Kanal", None)
    assert await svc.count_posts(session, p.id) == 0
    post = await svc.record_channel_post(session, p.id, ch.id, [10, 11, 12], 12)
    assert post.message_ids == [10, 11, 12] and post.button_message_id == 12
    assert await svc.count_posts(session, p.id) == 1


async def test_order_models(session, seller):
    p = await svc.create_product(session, seller, draft())
    order = Order(
        public_id="ORD1234567", seller_id=seller.id, buyer_telegram_id=42, total=Decimal("500000"),
        items=[OrderItem(product_id=p.id, variant_id=p.variants[0].id, product_name=p.name,
                         size="S", color="qora", quantity=2, unit_price=p.price)],
    )
    session.add(order)
    await session.flush()
    await session.refresh(order)
    assert order.status == OrderStatus.NEW and len(order.items) == 1
