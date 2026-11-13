"""Bot qatlami: Telegram'ga ulanmasdan, soxta Bot bilan tekshiramiz."""
from decimal import Decimal
from types import SimpleNamespace

from app.bot.handlers import build_router
from app.bot.publisher import post_link, send_product
from app.services.dto import MediaItem, ProductView, VariantData


class FakeBot:
    def __init__(self):
        self.calls = []
        self._id = 100

    def _msg(self):
        self._id += 1
        return SimpleNamespace(message_id=self._id)

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None):
        self.calls.append(("photo", photo, caption, reply_markup))
        return self._msg()

    async def send_video(self, chat_id, video, caption=None, reply_markup=None):
        self.calls.append(("video", video, caption, reply_markup))
        return self._msg()

    async def send_media_group(self, chat_id, media):
        self.calls.append(("album", [(m.type, m.media, m.caption) for m in media]))
        return [self._msg() for _ in media]

    async def send_message(self, chat_id, text, reply_markup=None):
        self.calls.append(("text", text, reply_markup))
        return self._msg()


VIEW = ProductView("Ko'ylak", Decimal("100000"), None, [VariantData("S", "", 1)], "Moda")


async def test_single_photo_is_one_message_with_buttons():
    bot = FakeBot()
    msgs = await send_product(bot, 1, [MediaItem("photo", "f1")], VIEW, markup="MARKUP")
    assert len(msgs) == 1
    kind, photo, caption, markup = bot.calls[0]
    assert kind == "photo" and photo == "f1" and "Ko'ylak" in caption and markup == "MARKUP"


async def test_single_video_is_one_message_with_buttons():
    bot = FakeBot()
    await send_product(bot, 1, [MediaItem("video", "v1")], VIEW, markup="MARKUP")
    assert bot.calls[0][0] == "video" and bot.calls[0][3] == "MARKUP"


async def test_album_has_caption_inside_then_buttons_message():
    bot = FakeBot()
    media = [MediaItem("photo", "f1"), MediaItem("video", "v1"), MediaItem("photo", "f2")]
    msgs = await send_product(bot, 1, media, VIEW, markup="MARKUP")
    assert [c[0] for c in bot.calls] == ["album", "text"]
    album = bot.calls[0][1]
    assert [(t, m) for t, m, _ in album] == [("photo", "f1"), ("video", "v1"), ("photo", "f2")]
    assert "Ko'ylak" in album[0][2] and "100 000" in album[0][2]  # matn albomning o'zida
    assert album[1][2] is None and album[2][2] is None
    assert bot.calls[1][2] == "MARKUP"
    assert len(msgs) == 4


async def test_album_without_markup_has_no_extra_message():
    bot = FakeBot()
    await send_product(bot, 1, [MediaItem("photo", "a"), MediaItem("photo", "b")], VIEW, markup=None)
    assert [c[0] for c in bot.calls] == ["album"]


def test_post_link():
    pub = SimpleNamespace(username="@moda", chat_id=-1001234)
    priv = SimpleNamespace(username=None, chat_id=-1001234)
    assert post_link(pub, 5) == "https://t.me/moda/5"
    assert post_link(priv, 5) == "https://t.me/c/1234/5"


def test_router_builds():
    assert build_router() is not None


def test_all_text_keys_exist():
    """Kodda ishlatilgan har bir matn kaliti uz.py da bor ekanini tekshiradi."""
    import pathlib
    import re

    from app.db.models import OrderStatus
    from app.texts import uz

    used = set()
    for f in pathlib.Path("app").rglob("*.py"):
        used |= set(re.findall(r"""\bt\(\s*f?["']([a-z_]+)["']""", f.read_text(encoding="utf-8")))
        used |= set(re.findall(r"""Error\(\s*["']([a-z_]+)["']""", f.read_text(encoding="utf-8")))
    used = {k for k in used if not k.endswith("_")}  # f-string prefikslari
    used |= {f"btn_edit_{x}" for x in ("photos", "name", "price", "variants", "description")}
    used |= {f"order_status_{s.value}" for s in OrderStatus}
    used |= {f"btn_status_{s.value}" for s in OrderStatus if s != OrderStatus.NEW}
    missing = used - set(uz.TEXTS)
    assert not missing, missing
