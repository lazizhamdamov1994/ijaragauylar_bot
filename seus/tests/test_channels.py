import pytest

from app.db.models import Seller
from app.services import channels as svc
from app.services.channels import MemberInfo
from app.services.errors import ConflictError, ValidationError

ADMIN_POST = MemberInfo("administrator", True)
OWNER = MemberInfo("creator")


@pytest.mark.parametrize(
    "chat_type, bot, user, code",
    [
        ("supergroup", ADMIN_POST, OWNER, "channel_not_channel"),
        ("channel", MemberInfo("left"), OWNER, "channel_bot_not_admin"),
        ("channel", MemberInfo("member"), OWNER, "channel_bot_not_admin"),
        ("channel", MemberInfo("administrator", False), OWNER, "channel_bot_cannot_post"),
        ("channel", ADMIN_POST, MemberInfo("member"), "channel_user_not_admin"),
        ("channel", ADMIN_POST, MemberInfo("left"), "channel_user_not_admin"),
    ],
)
def test_check_access_errors(chat_type, bot, user, code):
    with pytest.raises(ValidationError) as e:
        svc.check_channel_access(chat_type, bot, user)
    assert e.value.code == code


@pytest.mark.parametrize("user", [OWNER, MemberInfo("administrator", False)])
def test_check_access_ok(user):
    svc.check_channel_access("channel", ADMIN_POST, user)


async def test_link_and_get_active(session, seller):
    assert await svc.get_active_channel(session, seller.id) is None
    ch = await svc.link_channel(session, seller, -1001, "Moda kanal", "@moda")
    active = await svc.get_active_channel(session, seller.id)
    assert active.id == ch.id and active.title == "Moda kanal" and active.username == "@moda"


async def test_relink_new_channel_deactivates_old(session, seller):
    old = await svc.link_channel(session, seller, -1001, "Eski", None)
    new = await svc.link_channel(session, seller, -1002, "Yangi", None)
    await session.refresh(old)
    assert not old.is_active and new.is_active
    assert (await svc.get_active_channel(session, seller.id)).id == new.id
    # eski kanalni qayta ulash — yana faollashadi
    again = await svc.link_channel(session, seller, -1001, "Eski 2", None)
    assert again.id == old.id and again.is_active


async def test_channel_taken_by_other_seller(session, seller):
    other = Seller(telegram_id=222, shop_name="Boshqa", phone="+998900000000")
    session.add(other)
    await session.flush()
    await svc.link_channel(session, other, -1001, "Kanal", None)
    with pytest.raises(ConflictError) as e:
        await svc.link_channel(session, seller, -1001, "Kanal", None)
    assert e.value.code == "channel_taken"
