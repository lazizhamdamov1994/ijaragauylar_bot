"""Bot qatlami: Telegram'ga ulanmasdan, soxta Bot bilan tekshiramiz."""
from decimal import Decimal
from types import SimpleNamespace

from app.bot.handlers import build_router
from app.bot.publisher import post_link, send_product
from app.services.dto import ProductView, VariantData


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

    async def send_media_group(self, chat_id, media):
        self.calls.append(("album", [m.media for m in media]))
        return [self._msg() for _ in media]

    async def send_message(self, chat_id, text, reply_markup=None):
        self.calls.append(("text", text, reply_markup))
        return self._msg()


VIEW = ProductView("Ko'ylak", Decimal("100000"), None, [VariantData("S", "", 1)], "Moda")


async def test_single_photo_is_one_message_with_buttons():
    bot = FakeBot()
    msgs = await send_product(bot, 1, ["f1"], VIEW, markup="MARKUP")
    assert len(msgs) == 1
    kind, photo, caption, markup = bot.calls[0]
    assert kind == "photo" and photo == "f1" and "Ko'ylak" in caption and markup == "MARKUP"


async def test_many_photos_album_then_text_with_buttons():
    bot = FakeBot()
    msgs = await send_product(bot, 1, ["f1", "f2", "f3"], VIEW, markup="MARKUP")
    assert [c[0] for c in bot.calls] == ["album", "text"]
    assert bot.calls[0][1] == ["f1", "f2", "f3"]
    assert bot.calls[1][2] == "MARKUP"
    assert len(msgs) == 4


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

    from app.texts import uz

    used = set()
    for f in pathlib.Path("app").rglob("*.py"):
        used |= set(re.findall(r"""\bt\(\s*f?["']([a-z_]+)["']""", f.read_text(encoding="utf-8")))
    used |= {"btn_edit_photos", "btn_edit_name", "btn_edit_price", "btn_edit_variants", "btn_edit_description"}
    for f in pathlib.Path("app/services").rglob("*.py"):
        used |= set(re.findall(r"""Error\(\s*["']([a-z_]+)["']""", f.read_text(encoding="utf-8")))
    missing = used - set(uz.TEXTS)
    assert not missing, missing
