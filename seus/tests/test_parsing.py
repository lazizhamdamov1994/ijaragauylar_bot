from decimal import Decimal

import pytest

from app.services.channels import parse_channel_username
from app.services.dto import VariantData
from app.services.errors import ValidationError
from app.services.parsing import (
    merge_variants,
    normalize_phone,
    parse_price,
    parse_stock,
    parse_variant_line,
    parse_variants,
    validate_description,
    validate_product_name,
    validate_shop_name,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("250000", "250000"),
        ("250 000", "250000"),
        ("250.000", "250000"),
        ("1,250,000", "1250000"),
        ("250k", "250000"),
        ("250 ming", "250000"),
        ("1.5 mln", "1500000"),
        ("99 000 so'm", "99000"),
        ("120.50", "120.50"),
    ],
)
def test_parse_price_ok(text, expected):
    assert parse_price(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["", "abc", "0", "-5", "1.2.3", "99999999999", None])
def test_parse_price_bad(text):
    with pytest.raises(ValidationError) as e:
        parse_price(text)
    assert e.value.code == "price_invalid"


def test_parse_variant_line_full():
    assert parse_variant_line("s qora 5") == VariantData("S", "qora", 5)


def test_parse_variant_line_multiword_color_and_suffix():
    assert parse_variant_line("XL to'q ko'k 3ta") == VariantData("XL", "to'q ko'k", 3)


def test_parse_variant_line_size_only_and_qty_only():
    assert parse_variant_line("42 10") == VariantData("42", "", 10)
    assert parse_variant_line("7") == VariantData("", "", 7)


def test_parse_variants_multiline_with_errors():
    ok, bad = parse_variants("S qora 5\nM, oq, 3\n\nnoto'g'ri qator\nL qizil 2; XL qizil 1")
    assert [v.label() for v in ok] == ["S qora", "M oq", "L qizil", "XL qizil"]
    assert bad == ["noto'g'ri qator"]


def test_merge_variants_sums_duplicates():
    merged = merge_variants([VariantData("S", "qora", 5)], [VariantData("s", "QORA", 2), VariantData("M", "", 1)])
    assert merged == [VariantData("S", "qora", 7), VariantData("M", "", 1)]


def test_parse_stock():
    assert parse_stock(" 12 ") == 12
    for bad in ("-1", "x", "1000001"):
        with pytest.raises(ValidationError):
            parse_stock(bad)


def test_normalize_phone():
    assert normalize_phone("998901234567") == "+998901234567"
    assert normalize_phone("+998 (90) 123-45-67") == "+998901234567"
    assert normalize_phone("901234567") == "+998901234567"
    with pytest.raises(ValidationError):
        normalize_phone("123")


def test_text_validators():
    assert validate_shop_name("  Moda   uyi ") == "Moda uyi"
    assert validate_product_name("Ko'ylak") == "Ko'ylak"
    assert validate_description("   ") is None
    for fn, bad in ((validate_shop_name, "a"), (validate_product_name, "x" * 201), (validate_description, "y" * 2001)):
        with pytest.raises(ValidationError):
            fn(bad)


@pytest.mark.parametrize(
    "text", ["@moda_kanal", "moda_kanal", "https://t.me/moda_kanal", "t.me/moda_kanal/15"]
)
def test_parse_channel_username(text):
    assert parse_channel_username(text) == "@moda_kanal"


@pytest.mark.parametrize("text", ["", "@ab", "salom dunyo", "@1abc"])
def test_parse_channel_username_bad(text):
    with pytest.raises(ValidationError):
        parse_channel_username(text)
