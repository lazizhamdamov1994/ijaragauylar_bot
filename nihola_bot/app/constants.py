"""Tumanlar, uy turlari, byudjet oraliqlari va menyu tugmalari matnlari."""

# (slug, nomi, heshteg)
DISTRICTS: list[tuple[str, str, str]] = [
    ("bektemir", "Bektemir", "Bektemir"),
    ("chilonzor", "Chilonzor", "Chilonzor"),
    ("mirobod", "Mirobod", "Mirobod"),
    ("mirzo_ulugbek", "Mirzo Ulug‘bek", "MirzoUlugbek"),
    ("olmazor", "Olmazor", "Olmazor"),
    ("sergeli", "Sergeli", "Sergeli"),
    ("shayxontohur", "Shayxontohur", "Shayxontohur"),
    ("uchtepa", "Uchtepa", "Uchtepa"),
    ("yakkasaroy", "Yakkasaroy", "Yakkasaroy"),
    ("yashnobod", "Yashnobod", "Yashnobod"),
    ("yunusobod", "Yunusobod", "Yunusobod"),
    ("yangihayot", "Yangihayot", "Yangihayot"),
    ("viloyat", "Toshkent viloyati", "ToshkentViloyati"),
]
DISTRICT_NAME = {slug: name for slug, name, _ in DISTRICTS}
DISTRICT_TAG = {slug: tag for slug, _, tag in DISTRICTS}


def district_label(slug: str | None) -> str:
    name = DISTRICT_NAME.get(slug or "", slug or "")
    if slug and slug != "viloyat":
        return f"{name} tumani"
    return name


DEALS = [("sale", "🏷 Sotuv"), ("rent", "🔑 Ijara")]

PTYPES = [
    ("new", "🏗 Novostroyka"),
    ("old", "🏠 Vtorichka"),
    ("house", "🏡 Hovli / kottej"),
    ("commercial", "🏢 Tijorat"),
]
PTYPE_TAG = {"new": "novostroyka", "old": "vtorichka", "house": "hovli", "commercial": "tijorat"}

HEADERS = {
    ("sale", "new"): "🔥 YANGI QURILGAN NOVOSTROYKA!",
    ("sale", "old"): "🏠 KVARTIRA SOTILADI!",
    ("sale", "house"): "🏡 HOVLI SOTILADI!",
    ("sale", "commercial"): "🏢 TIJORAT OBYEKTI SOTILADI!",
    ("rent", "new"): "🔑 NOVOSTROYKA IJARAGA BERILADI!",
    ("rent", "old"): "🔑 KVARTIRA IJARAGA BERILADI!",
    ("rent", "house"): "🔑 HOVLI IJARAGA BERILADI!",
    ("rent", "commercial"): "🔑 TIJORAT OBYEKTI IJARAGA BERILADI!",
}

# (yorliq, min, max) — dollarda
SALE_BUDGETS = [
    ("30 000$ gacha", None, 30000),
    ("30–50 ming $", 30000, 50000),
    ("50–80 ming $", 50000, 80000),
    ("80–120 ming $", 80000, 120000),
    ("120 ming $ dan yuqori", 120000, None),
]
RENT_BUDGETS = [
    ("300$ gacha", None, 300),
    ("300–500$", 300, 500),
    ("500–800$", 500, 800),
    ("800$ dan yuqori", 800, None),
]

ROOM_OPTIONS = [("1", "1 xona"), ("2", "2 xona"), ("3", "3 xona"), ("4", "4+ xona")]

# --- Menyu tugmalari ---
BTN_SEARCH = "🔎 Uy qidirish"
BTN_FILTER = "🔔 Mening filtrim"
BTN_SAVED = "❤️ Saqlanganlar"
BTN_CONTACT = "📞 Rieltor bilan bog‘lanish"
BTN_SELL = "🏡 Uyimni sotmoqchiman"
BTN_ADMIN = "🛠 Admin panel"

BTN_NEW = "➕ Yangi e’lon"
BTN_LIST = "📋 E’lonlar"
BTN_STATS = "📊 Statistika"
BTN_BCAST = "📣 Xabar yuborish"
BTN_USERMODE = "👤 Mijoz menyusi"

BTN_SEND_PHONE = "📱 Raqamni yuborish"
BTN_NO_PHONE = "⏭ Raqamsiz davom etish"
BTN_CANCEL = "❌ Bekor qilish"

# Menyu tugmasi bosilsa — ochiq qolgan jarayon (masalan e'lon yaratish) shu matnni "javob" deb olmasligi uchun
MENU_TEXTS = frozenset({
    BTN_SEARCH, BTN_FILTER, BTN_SAVED, BTN_CONTACT, BTN_SELL, BTN_ADMIN,
    BTN_NEW, BTN_LIST, BTN_STATS, BTN_BCAST, BTN_USERMODE,
})
