from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    shop_name = State()
    phone = State()


class ChannelLink(StatesGroup):
    waiting = State()


class ProductAdd(StatesGroup):
    photos = State()
    name = State()
    price = State()
    variants = State()
    variant_size = State()
    variant_color = State()
    variant_qty = State()
    description = State()
    preview = State()


class OrderFlow(StatesGroup):
    variant = State()
    qty = State()
    phone = State()
    address = State()
    comment = State()
    confirm = State()
