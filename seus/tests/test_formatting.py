from decimal import Decimal

from app.services.dto import ProductDraft, ProductView, VariantData
from app.services.formatting import build_caption, format_price, variants_list_text, view_from_draft
from app.services.ids import generate_public_id, is_valid_public_id


def test_format_price():
    assert format_price(Decimal("250000")) == "250 000"
    assert format_price(Decimal("1250000.00")) == "1 250 000"
    assert format_price(Decimal("99.5")) == "99,50"


def _view(**kw):
    base = dict(
        name="Ko'ylak <yangi>",
        price=Decimal("250000"),
        description="Paxta & yumshoq",
        variants=[VariantData("S", "qora", 5), VariantData("M", "qora", 0), VariantData("L", "oq", 2)],
        shop_name="Moda",
    )
    base.update(kw)
    return ProductView(**base)


def test_caption_contains_everything_and_escapes_html():
    text = build_caption(_view())
    assert "<b>Ko'ylak &lt;yangi&gt;</b>" in text
    assert "Paxta &amp; yumshoq" in text
    assert "250 000 so'm" in text
    assert "<b>Qora</b>: S" in text  # M qora — tugagan, ko'rsatilmaydi
    assert "<b>Oq</b>: L" in text
    assert "Moda" in text


def test_caption_out_of_stock():
    text = build_caption(_view(variants=[VariantData("S", "", 0)]))
    assert "tugagan" in text


def test_caption_truncates_long_description_but_keeps_price():
    text = build_caption(_view(description="so'z " * 500), limit=1024)
    assert len(text) <= 1024
    assert "250 000 so'm" in text
    assert "…" in text


def test_draft_roundtrip():
    d = ProductDraft(["f1", "f2"], "Shim", Decimal("150000.00"), [VariantData("M", "", 3)], None)
    assert ProductDraft.from_dict(d.to_dict()) == d
    assert ProductDraft.from_dict(None) == ProductDraft()
    assert view_from_draft(d, "Moda").shop_name == "Moda"


def test_variants_list_text():
    assert "S qora — 5 ta" in variants_list_text([VariantData("S", "qora", 5)])
    assert variants_list_text([]) == "(hali bo'sh)"


def test_public_id_random_and_valid():
    ids = {generate_public_id() for _ in range(1000)}
    assert len(ids) == 1000
    assert all(len(i) == 10 and is_valid_public_id(i) for i in ids)
    assert not is_valid_public_id("ab-c")
    assert not is_valid_public_id("")
