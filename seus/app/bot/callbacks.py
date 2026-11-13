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
