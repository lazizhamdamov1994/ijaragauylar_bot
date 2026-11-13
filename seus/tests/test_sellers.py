import pytest

from app.services import sellers as svc
from app.services.errors import ValidationError


async def test_register_new_seller(session):
    s = await svc.register_seller(session, 555, "  Moda  ", "998901112233", "moda")
    assert s.id and s.shop_name == "Moda" and s.phone == "+998901112233" and s.is_active
    assert (await svc.get_by_telegram_id(session, 555)).id == s.id
    assert (await svc.get_by_id(session, s.id)).telegram_id == 555


async def test_register_again_updates_existing(session):
    a = await svc.register_seller(session, 555, "Moda", "998901112233")
    a.is_active = False
    b = await svc.register_seller(session, 555, "Moda 2", "+998 90 999 88 77")
    assert a.id == b.id and b.shop_name == "Moda 2" and b.phone == "+998909998877" and b.is_active


async def test_register_validation(session):
    with pytest.raises(ValidationError):
        await svc.register_seller(session, 1, "M", "998901112233")
    with pytest.raises(ValidationError):
        await svc.register_seller(session, 1, "Moda", "12")


async def test_get_missing_and_update_username(session, seller):
    assert await svc.get_by_telegram_id(session, 999) is None
    await svc.update_username(session, seller, "yangi")
    assert seller.username == "yangi"
