"""Sayt matnlari: o'zbek (lotin) va rus tillari."""
from __future__ import annotations

from datetime import datetime, timezone

from app.constants import DISTRICT_NAME

LANGS = ("uz", "ru")

DISTRICT_RU = {
    "bektemir": "Бектемир", "chilonzor": "Чиланзар", "mirobod": "Мирабад",
    "mirzo_ulugbek": "Мирзо-Улугбек", "olmazor": "Алмазар", "sergeli": "Сергели",
    "shayxontohur": "Шайхантахур", "uchtepa": "Учтепа", "yakkasaroy": "Яккасарай",
    "yashnobod": "Яшнабад", "yunusobod": "Юнусабад", "yangihayot": "Янгихаёт",
    "viloyat": "Ташкентская обл.",
}

T = {
    "uz": {
        "site_title": "Nihola Estate — Toshkentda kvartira va uylar",
        "site_desc": "Nihola Estate: Toshkentdagi yangi va ikkilamchi kvartiralar, hovlilar sotuvi va ijarasi. Xaritada qidiring, rieltor bilan bog‘laning.",
        "search_ph": "Tuman, majmua yoki e’lon raqami",
        "post_ad": "Uyimni sotish",
        "view_map": "Xaritada ko‘rish",
        "filters": "Filtrlar",
        "mortgage": "Ipoteka kalkulyatori",
        "mortgage_sub": "Oylik to‘lovni hisoblang",
        "consult": "Bepul konsultatsiya",
        "consult_sub": "Rieltor o‘zi qo‘ng‘iroq qiladi",
        "sale": "Sotuv", "rent": "Ijara",
        "ptype": "Uy turi", "any": "Hammasi", "district": "Tuman", "rooms": "Xonalar",
        "last_week": "Oxirgi hafta", "last_month": "Oxirgi oy",
        "latest": "Yangi e’lonlar", "new_badge": "YANGI",
        "found": "Topildi", "all_listings": "Jami e’lonlar",
        "sorting": "Saralash",
        "sort_new": "Avval yangilari", "sort_cheap": "Avval arzonlari",
        "sort_expensive": "Avval qimmatlari", "sort_area": "Maydoni bo‘yicha",
        "load_more": "Yana ko‘rsatish",
        "no_results": "Hozircha mos e’lon topilmadi",
        "no_results_sub": "Filtrni o‘zgartiring yoki Telegram botda obuna bo‘ling — mos uy chiqishi bilan xabar beramiz.",
        "subscribe_bot": "🔔 Botda obuna bo‘lish",
        "reset": "Tozalash", "apply": "Ko‘rsatish",
        "price": "Narx", "price_from": "dan", "price_to": "gacha",
        "area_m2": "Maydon, m²",
        "favorites": "Sevimlilar", "no_favorites": "Sevimlilar ro‘yxati bo‘sh",
        "no_favorites_sub": "E’lonlardagi ♡ belgisini bosing — ular shu yerda saqlanadi.",
        "map": "Xarita", "home": "Asosiy", "search": "Qidiruv", "add": "Sotish",
        "back": "Orqaga",
        "contact_tg": "Telegramda bog‘lanish", "call": "Qo‘ng‘iroq qilish",
        "save": "Saqlash", "saved": "Saqlangan", "share": "Ulashish", "copied": "Havola nusxalandi",
        "features": "Xususiyatlari", "floor": "Qavat", "area": "Umumiy maydon",
        "balcony": "Balkon", "bathroom": "Sanuzel", "renovation": "Ta’mir",
        "furniture": "Mebel", "landmark": "Mo‘ljal", "address": "Manzil",
        "type": "Turi", "deal": "Bitim", "listing_no": "E’lon raqami", "published": "Joylangan",
        "extra": "Qo‘shimcha ma’lumot",
        "similar": "O‘xshash e’lonlar", "location": "Joylashuv",
        "sold": "SOTILDI", "sold_rent": "IJARAGA BERILDI", "reserved": "BAND",
        "sold_note": "Bu uy allaqachon sotilgan. O‘xshash e’lonlarni ko‘ring 👇",
        "calc_title": "Ipoteka kalkulyatori", "calc_price": "Uy narxi ($)",
        "calc_down": "Boshlang‘ich to‘lov (%)", "calc_years": "Muddat (yil)",
        "calc_rate": "Yillik foiz (%)", "calc_monthly": "Oylik to‘lov",
        "calc_loan": "Kredit summasi", "calc_overpay": "Ortiqcha to‘lov",
        "calc_note": "Hisob taxminiy. Aniq shartlarni rieltordan so‘rang.",
        "calc_ask": "Rieltordan ipoteka haqida so‘rash",
        "today": "Bugun", "yesterday": "Kecha", "days_ago": "{n} kun oldin",
        "rooms_n": "{n} xonali", "per_month": "/oy",
        "ptype_new": "Novostroyka", "ptype_old": "Vtorichka",
        "ptype_house": "Hovli / kottej", "ptype_commercial": "Tijorat",
        "title_flat": "{rooms} xonali kvartira", "title_house": "Hovli", "title_commercial": "Tijorat obyekti",
        "channel": "Telegram kanal", "rights": "Barcha huquqlar himoyalangan",
        "photos": "rasm", "close": "Yopish", "on_map_count": "Xaritada {n} ta uy",
        "no_location": "Lokatsiya ko‘rsatilmagan", "open": "Ochish", "not_found": "Sahifa topilmadi",
        "to_home": "Bosh sahifaga", "theme": "Tungi rejim", "lang": "Til",
        "view_big": "Katta", "view_grid": "Panjara", "view_list": "Ro‘yxat",
        "all_districts": "Barcha tumanlar", "any_rooms": "Istalgan",
    },
    "ru": {
        "site_title": "Nihola Estate — квартиры и дома в Ташкенте",
        "site_desc": "Nihola Estate: продажа и аренда новостроек, вторичного жилья и домов в Ташкенте. Поиск на карте, связь с риелтором.",
        "search_ph": "Район, ЖК или номер объявления",
        "post_ad": "Продать жильё",
        "view_map": "Смотреть на карте",
        "filters": "Фильтры",
        "mortgage": "Ипотечный калькулятор",
        "mortgage_sub": "Рассчитайте ежемесячный платёж",
        "consult": "Бесплатная консультация",
        "consult_sub": "Риелтор сам перезвонит",
        "sale": "Продажа", "rent": "Аренда",
        "ptype": "Тип жилья", "any": "Все", "district": "Район", "rooms": "Комнаты",
        "last_week": "За неделю", "last_month": "За месяц",
        "latest": "Новые объявления", "new_badge": "НОВОЕ",
        "found": "Найдено", "all_listings": "Всего объявлений",
        "sorting": "Сортировка",
        "sort_new": "Сначала новые", "sort_cheap": "Сначала дешёвые",
        "sort_expensive": "Сначала дорогие", "sort_area": "По площади",
        "load_more": "Показать ещё",
        "no_results": "Подходящих объявлений пока нет",
        "no_results_sub": "Измените фильтр или подпишитесь в Telegram-боте — сообщим, как только появится подходящий вариант.",
        "subscribe_bot": "🔔 Подписаться в боте",
        "reset": "Сбросить", "apply": "Показать",
        "price": "Цена", "price_from": "от", "price_to": "до",
        "area_m2": "Площадь, м²",
        "favorites": "Избранное", "no_favorites": "В избранном пусто",
        "no_favorites_sub": "Нажимайте ♡ на объявлениях — они сохранятся здесь.",
        "map": "Карта", "home": "Главная", "search": "Поиск", "add": "Продать",
        "back": "Назад",
        "contact_tg": "Написать в Telegram", "call": "Позвонить",
        "save": "В избранное", "saved": "В избранном", "share": "Поделиться", "copied": "Ссылка скопирована",
        "features": "Характеристики", "floor": "Этаж", "area": "Общая площадь",
        "balcony": "Балкон", "bathroom": "Санузел", "renovation": "Ремонт",
        "furniture": "Мебель", "landmark": "Ориентир", "address": "Адрес",
        "type": "Тип", "deal": "Сделка", "listing_no": "Номер объявления", "published": "Опубликовано",
        "extra": "Дополнительно",
        "similar": "Похожие объявления", "location": "Расположение",
        "sold": "ПРОДАНО", "sold_rent": "СДАНО", "reserved": "ЗАБРОНИРОВАНО",
        "sold_note": "Этот объект уже продан. Посмотрите похожие 👇",
        "calc_title": "Ипотечный калькулятор", "calc_price": "Цена жилья ($)",
        "calc_down": "Первоначальный взнос (%)", "calc_years": "Срок (лет)",
        "calc_rate": "Годовая ставка (%)", "calc_monthly": "Ежемесячный платёж",
        "calc_loan": "Сумма кредита", "calc_overpay": "Переплата",
        "calc_note": "Расчёт примерный. Точные условия уточните у риелтора.",
        "calc_ask": "Спросить риелтора об ипотеке",
        "today": "Сегодня", "yesterday": "Вчера", "days_ago": "{n} дн. назад",
        "rooms_n": "{n}-комн.", "per_month": "/мес",
        "ptype_new": "Новостройка", "ptype_old": "Вторичка",
        "ptype_house": "Дом / коттедж", "ptype_commercial": "Коммерция",
        "title_flat": "{rooms}-комнатная квартира", "title_house": "Дом", "title_commercial": "Коммерческий объект",
        "channel": "Telegram-канал", "rights": "Все права защищены",
        "photos": "фото", "close": "Закрыть", "on_map_count": "На карте {n} объектов",
        "no_location": "Расположение не указано", "open": "Открыть", "not_found": "Страница не найдена",
        "to_home": "На главную", "theme": "Тёмная тема", "lang": "Язык",
        "view_big": "Крупно", "view_grid": "Сетка", "view_list": "Список",
        "all_districts": "Все районы", "any_rooms": "Любое",
    },
}


def t(lang: str, key: str, **kw) -> str:
    text = T.get(lang, T["uz"]).get(key) or T["uz"].get(key) or key
    return text.format(**kw) if kw else text


def district_name(lang: str, slug: str | None) -> str:
    if not slug:
        return ""
    if lang == "ru":
        return DISTRICT_RU.get(slug, slug)
    return DISTRICT_NAME.get(slug, slug)


def fmt_money(n) -> str:
    return f"{int(n or 0):,}".replace(",", " ")


def price_label(lang: str, listing: dict) -> str:
    p = f"{fmt_money(listing.get('price'))} $"
    return p + t(lang, "per_month") if listing.get("deal") == "rent" else p


def area_label(a) -> str:
    if a is None:
        return ""
    a = float(a)
    return (str(int(a)) if a.is_integer() else f"{a:g}".replace(".", ",")) + " m²"


def listing_title(lang: str, l: dict) -> str:
    if l.get("ptype") == "house":
        base = t(lang, "title_house")
    elif l.get("ptype") == "commercial":
        base = t(lang, "title_commercial")
    elif l.get("rooms"):
        base = t(lang, "title_flat", rooms=l["rooms"])
    else:
        base = t(lang, "ptype_" + (l.get("ptype") or "old"))
    if l.get("area"):
        base += ", " + area_label(l["area"])
    return base


def listing_place(lang: str, l: dict) -> str:
    parts = [district_name(lang, l.get("district"))]
    if l.get("address"):
        parts.append(l["address"])
    return ", ".join(p for p in parts if p)


def ago(lang: str, dt: datetime | None) -> str:
    if not dt:
        return ""
    days = (datetime.now(timezone.utc).date() - dt.date()).days
    if days <= 0:
        return t(lang, "today")
    if days == 1:
        return t(lang, "yesterday")
    return t(lang, "days_ago", n=days)
