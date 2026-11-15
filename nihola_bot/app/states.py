from aiogram.fsm.state import State, StatesGroup


class NewListing(StatesGroup):
    field = State()     # matn/tugma maydonlari
    media = State()     # rasm va videolar
    location = State()  # lokatsiya
    preview = State()   # ko'rib chiqish


class ManageListing(StatesGroup):
    price = State()


class Broadcast(StatesGroup):
    message = State()
    confirm = State()


class FilterSetup(StatesGroup):
    active = State()


class LeadPhone(StatesGroup):
    waiting = State()


class SellerForm(StatesGroup):
    district = State()
    rooms = State()
    price = State()
    description = State()
    phone = State()
