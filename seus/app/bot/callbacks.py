from aiogram.filters.callback_data import CallbackData


class VariantCb(CallbackData, prefix="vw"):
    action: str  # start / undo / size / color / qty
    value: str = ""


class PreviewCb(CallbackData, prefix="pv"):
    action: str  # publish / edit / cancel / field
    field: str = ""


class ProductCb(CallbackData, prefix="pr"):
    action: str  # list / view / publish / off / on
    id: int = 0
    page: int = 0


class BuyCb(CallbackData, prefix="ob"):
    """Xaridor buyurtma berayotganda."""

    action: str  # variant / qty / send / cancel
    id: int = 0


class SellerOrderCb(CallbackData, prefix="os"):
    """Sotuvchi buyurtmalarni boshqarayotganda."""

    action: str  # list / view / set
    id: int = 0
    status: str = ""
    page: int = 0
