from decimal import Decimal

import pytest

from app.db.models import OrderStatus, ProductVariant, Seller
from app.services import orders as svc
from app.services import products as product_svc
from app.services.dto import MediaItem, ProductDraft, VariantData
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.services.formatting import order_text


@pytest.fixture
async def product(session, seller):
    return await product_svc.create_product(
        session,
        seller,
        ProductDraft(
            media=[MediaItem("photo", "p1")],
            name="Ko'ylak",
            price=Decimal("150000"),
            variants=[VariantData("S", "qora", 3), VariantData("M", "oq", 0)],
        ),
    )


def req(product, **kw) -> svc.OrderRequest:
    base = dict(
        product_id=product.id,
        variant_id=product.variants[0].id,
        quantity=2,
        buyer_telegram_id=777,
        buyer_name="Ali Valiyev",
        buyer_phone="901234567",
        address="Toshkent, Chilonzor 5-uy",
        comment="  kechqurun qo'ng'iroq qiling ",
    )
    base.update(kw)
    return svc.OrderRequest(**base)


async def stock_of(session, variant_id):
    v = await session.get(ProductVariant, variant_id)
    await session.refresh(v)
    return v.stock


async def test_available_variants(product):
    assert [v.size for v in svc.available_variants(product)] == ["S"]


async def test_create_order(session, seller, product):
    order = await svc.create_order(session, req(product))
    assert order.id and order.status == OrderStatus.NEW and order.seller_id == seller.id
    assert order.total == Decimal("300000")
    assert order.buyer_phone == "+998901234567" and order.comment == "kechqurun qo'ng'iroq qiling"
    item = order.items[0]
    assert (item.product_name, item.size, item.color, item.quantity, item.unit_price) == (
        "Ko'ylak", "S", "qora", 2, Decimal("150000"))
    assert await stock_of(session, product.variants[0].id) == 1  # 3 - 2


async def test_create_order_not_enough_stock(session, product):
    with pytest.raises(ConflictError) as e:
        await svc.create_order(session, req(product, quantity=4))
    assert e.value.code == "order_not_enough_stock" and e.value.params == {"stock": 3}
    with pytest.raises(ConflictError):
        await svc.create_order(session, req(product, variant_id=product.variants[1].id, quantity=1))
    assert await stock_of(session, product.variants[0].id) == 3


@pytest.mark.parametrize(
    "kw, exc, code",
    [
        ({"quantity": 0}, ValidationError, "order_qty_invalid"),
        ({"buyer_phone": "12"}, ValidationError, "phone_use_button"),
        ({"address": "uy"}, ValidationError, "order_address_invalid"),
        ({"variant_id": 99999}, NotFoundError, "order_variant_gone"),
        ({"product_id": 99999}, NotFoundError, "buyer_product_unavailable"),
    ],
)
async def test_create_order_validation(session, product, kw, exc, code):
    with pytest.raises(exc) as e:
        await svc.create_order(session, req(product, **kw))
    assert e.value.code == code


async def test_inactive_product_cannot_be_ordered(session, seller, product):
    await product_svc.set_active(session, seller.id, product.id, False)
    with pytest.raises(NotFoundError):
        await svc.create_order(session, req(product))


async def test_status_flow_and_cancel_restores_stock(session, seller, product):
    order = await svc.create_order(session, req(product))
    vid = product.variants[0].id
    order = await svc.change_status(session, seller.id, order.id, OrderStatus.CONFIRMED)
    assert order.status == OrderStatus.CONFIRMED
    with pytest.raises(ConflictError):
        await svc.change_status(session, seller.id, order.id, OrderStatus.NEW)
    await svc.change_status(session, seller.id, order.id, OrderStatus.CANCELLED)
    assert await stock_of(session, vid) == 3
    with pytest.raises(ConflictError):  # bekor qilingandan keyin hech narsa mumkin emas
        await svc.change_status(session, seller.id, order.id, OrderStatus.CANCELLED)
    assert await stock_of(session, vid) == 3  # ikki marta qaytarilmadi


async def test_delivered_keeps_stock(session, seller, product):
    order = await svc.create_order(session, req(product, quantity=1))
    await svc.change_status(session, seller.id, order.id, OrderStatus.CONFIRMED)
    await svc.change_status(session, seller.id, order.id, OrderStatus.SHIPPED)
    await svc.change_status(session, seller.id, order.id, OrderStatus.DELIVERED)
    assert await stock_of(session, product.variants[0].id) == 2


async def test_other_seller_cannot_touch_order(session, product):
    order = await svc.create_order(session, req(product))
    other = Seller(telegram_id=5, shop_name="Boshqa", phone="+998900000000")
    session.add(other)
    await session.flush()
    with pytest.raises(NotFoundError):
        await svc.change_status(session, other.id, order.id, OrderStatus.CONFIRMED)
    with pytest.raises(NotFoundError):
        await svc.get_seller_order(session, other.id, order.id)


async def test_list_count_and_last_phone(session, seller, product):
    a = await svc.create_order(session, req(product, quantity=1))
    b = await svc.create_order(session, req(product, quantity=1, buyer_phone="+998935554433"))
    await svc.change_status(session, seller.id, a.id, OrderStatus.CONFIRMED)
    listed = await svc.list_seller_orders(session, seller.id)
    assert [o.id for o in listed] == [b.id, a.id]  # "yangi" holatdagilar tepada
    assert await svc.count_seller_orders(session, seller.id) == 2
    await svc.change_status(session, seller.id, a.id, OrderStatus.CANCELLED)
    assert await svc.count_seller_orders(session, seller.id, only_open=True) == 1
    assert [o.id for o in await svc.list_seller_orders(session, seller.id, only_open=True)] == [b.id]
    assert await svc.last_buyer_phone(session, 777) == "+998935554433"
    assert await svc.last_buyer_phone(session, 1) is None


async def test_order_text(session, product):
    order = await svc.create_order(session, req(product, buyer_name="<Ali>"))
    text = order_text(order)
    assert f"№{order.id}" in text and "Ko'ylak — S qora × 2" in text
    assert "300 000 so'm" in text and "&lt;Ali&gt;" in text and "Yangi" in text
