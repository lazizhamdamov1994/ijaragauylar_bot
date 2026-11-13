from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import PreviewCb, ProductCb, VariantCb
from app.db.models import Product
from app.services.formatting import format_price
from app.texts import t

SIZES = ["XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"]
COLORS = ["qora", "oq", "kulrang", "ko'k", "qizil", "yashil", "jigarrang", "bej", "pushti", "sariq"]
QUANTITIES = [1, 2, 3, 5, 10, 20]


def _reply(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=x) for x in row] for row in rows],
        resize_keyboard=True,
    )


def main_menu(lang: str = "uz") -> ReplyKeyboardMarkup:
    return _reply([t("btn_add_product", lang)], [t("btn_my_products", lang), t("btn_my_channel", lang)])


def phone_request(lang: str = "uz") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_send_phone", lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def cancel_only(lang: str = "uz") -> ReplyKeyboardMarkup:
    return _reply([t("btn_cancel", lang)])


def done_cancel(lang: str = "uz") -> ReplyKeyboardMarkup:
    return _reply([t("btn_done", lang)], [t("btn_cancel", lang)])


def skip_cancel(lang: str = "uz") -> ReplyKeyboardMarkup:
    return _reply([t("btn_skip", lang)], [t("btn_cancel", lang)])


def variants_actions(lang: str = "uz", can_undo: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t("btn_variant_wizard", lang), callback_data=VariantCb(action="start"))
    if can_undo:
        b.button(text=t("btn_variant_undo", lang), callback_data=VariantCb(action="undo"))
    b.adjust(1)
    return b.as_markup()


def size_picker(lang: str = "uz") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in SIZES:
        b.button(text=s, callback_data=VariantCb(action="size", value=s))
    b.button(text=t("btn_no_size", lang), callback_data=VariantCb(action="size", value="-"))
    b.adjust(4, 4, 1)
    return b.as_markup()


def color_picker(lang: str = "uz") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in COLORS:
        b.button(text=c.capitalize(), callback_data=VariantCb(action="color", value=c))
    b.button(text=t("btn_no_color", lang), callback_data=VariantCb(action="color", value="-"))
    b.adjust(3, 3, 3, 2)
    return b.as_markup()


def qty_picker() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for q in QUANTITIES:
        b.button(text=str(q), callback_data=VariantCb(action="qty", value=str(q)))
    b.adjust(6)
    return b.as_markup()


def preview_actions(lang: str = "uz") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t("btn_publish", lang), callback_data=PreviewCb(action="publish"))
    b.button(text=t("btn_edit", lang), callback_data=PreviewCb(action="edit"))
    b.button(text=t("btn_cancel", lang), callback_data=PreviewCb(action="cancel"))
    b.adjust(1, 2)
    return b.as_markup()


def edit_fields(lang: str = "uz") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for field in ("photos", "name", "price", "variants", "description"):
        b.button(text=t(f"btn_edit_{field}", lang), callback_data=PreviewCb(action="field", field=field))
    b.button(text=t("btn_back", lang), callback_data=PreviewCb(action="back"))
    b.adjust(2, 2, 1, 1)
    return b.as_markup()


def post_buttons(order_url: str, contact_url: str, lang: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_order", lang), url=order_url)],
            [InlineKeyboardButton(text=t("btn_contact_seller", lang), url=contact_url)],
        ]
    )


def contact_button(contact_url: str, lang: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("btn_contact_seller", lang), url=contact_url)]]
    )


def products_list(products: list[Product], page: int, has_next: bool, lang: str = "uz") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in products:
        mark = "" if p.is_active else t("product_inactive_mark", lang) + " "
        b.row(
            InlineKeyboardButton(
                text=f"{mark}{p.name[:40]} — {format_price(p.price)}",
                callback_data=ProductCb(action="view", id=p.id, page=page).pack(),
            )
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=ProductCb(action="list", page=page - 1).pack()))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=ProductCb(action="list", page=page + 1).pack()))
    if nav:
        b.row(*nav)
    return b.as_markup()


def product_manage(product: Product, page: int, lang: str = "uz") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if product.is_active:
        b.button(text=t("btn_publish", lang), callback_data=ProductCb(action="publish", id=product.id, page=page))
        b.button(text=t("btn_deactivate", lang), callback_data=ProductCb(action="off", id=product.id, page=page))
    else:
        b.button(text=t("btn_activate", lang), callback_data=ProductCb(action="on", id=product.id, page=page))
    b.button(text=t("btn_back", lang), callback_data=ProductCb(action="list", page=page))
    b.adjust(1)
    return b.as_markup()
