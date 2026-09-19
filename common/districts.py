"""
Toshkent tumanlari - bot va veb UMUMIY (ikkalasi ham erkin matndan tuman
nomini avtomatik aniqlashi kerak: veb - SEO breadcrumb/sitemap uchun,
bot - "Tezkor e'lon" oqimida manzilni avtomatik taklif qilish uchun).
"""
import re

TASHKENT_DISTRICTS = [
    "Yunusobod", "Chilonzor", "Sergeli", "Mirzo Ulug'bek", "Shayxontohur",
    "Olmazor", "Bektemir", "Uchtepa", "Yashnobod", "Yakkasaroy",
    "Mirobod", "Yangihayot",
]

_DISTRICT_ALIASES = {
    "Yunusobod": ["yunusobod", "yunusabad", "юнусобод", "юнусабад"],
    "Chilonzor": ["chilonzor", "chilanzar", "чилонзор", "чиланзар"],
    "Sergeli": ["sergeli", "сергели"],
    "Mirzo Ulug'bek": ["mirzo ulug", "mirzo-ulug", "мирзо улуг", "мирзо-улуг"],
    "Shayxontohur": ["shayxontohur", "shaykhontohur", "шайхонтохур", "шайхантахур"],
    "Olmazor": ["olmazor", "olmazar", "олмазор", "олмазар"],
    "Bektemir": ["bektemir", "бектемир"],
    "Uchtepa": ["uchtepa", "учтепа"],
    "Yashnobod": ["yashnobod", "yashnabad", "яшнобод", "яшнабад"],
    "Yakkasaroy": ["yakkasaroy", "yakkasaray", "яккасарой", "яккасарай"],
    "Mirobod": ["mirobod", "миробод"],
    "Yangihayot": ["yangihayot", "янгихаёт", "янгихает"],
}


def detect_district(text: str):
    """Matndan tuman nomini aniqlaydi. Topilmasa None qaytaradi (masalan
    "Tezkor e'lon" oqimida - avtomatik taklif berish kerakmi yoki yo'qmi
    shuni ANIQ bilish uchun; "Toshkent" degan noaniq standart qiymat
    bu yerda ishlatilmaydi)."""
    low = (text or "").lower()
    for canonical, aliases in _DISTRICT_ALIASES.items():
        for alias in aliases:
            if alias in low:
                return canonical
    return None


def extract_district(text: str) -> str:
    """Matndan (masalan tezkor e'lon xom matnidan) tuman nomini avtomatik
    aniqlaydi. Topilmasa umumiy "Toshkent" qaytaradi (masalan SEO
    breadcrumb kabi joylarda HAR DOIM biror qiymat kerak bo'lgani uchun)."""
    return detect_district(text) or "Toshkent"


_PRICE_DOLLAR = re.compile(r"\$\s?(\d[\d\s.,]{0,10}\d|\d)")
_PRICE_DOLLAR_SUFFIX = re.compile(r"(\d[\d\s.,]{0,10}\d|\d)\s?\$")
_PRICE_YE = re.compile(r"(\d[\d\s.,]{0,10}\d|\d)\s?(?:y\.?\s?e\.?|у\.?\s?е\.?)", re.IGNORECASE)
_PRICE_MLN_UZ = re.compile(r"(\d[\d.,]{0,6})\s?mln", re.IGNORECASE)
_PRICE_MLN_RU = re.compile(r"(\d[\d.,]{0,6})\s?млн", re.IGNORECASE)
_PRICE_SUM = re.compile(r"(\d[\d\s]{4,12}\d)\s?(?:so['‘’]?m|sum|сум)", re.IGNORECASE)
_PRICE_NEGOTIABLE = re.compile(r"kelishiladi|келишилади|договорн", re.IGNORECASE)


def detect_price(text: str):
    """Matndan narxni avtomatik aniqlashga harakat qiladi (masalan
    "Tezkor e'lon" oqimida). Ishonchli topilmasa None qaytaradi - taxminiy
    (noto'g'ri bo'lishi mumkin) qiymatni foydalanuvchiga majburlab
    ko'rsatishdan ko'ra, aniq topilmagan holatni bildirish afzalroq."""
    if not text:
        return None
    m = _PRICE_DOLLAR.search(text)
    if m:
        return f"{m.group(1).strip()}$"
    m = _PRICE_DOLLAR_SUFFIX.search(text)
    if m:
        return f"{m.group(1).strip()}$"
    m = _PRICE_YE.search(text)
    if m:
        return f"{m.group(1).strip()} y.e."
    m = _PRICE_MLN_UZ.search(text) or _PRICE_MLN_RU.search(text)
    if m:
        return f"{m.group(1).strip()} mln so'm"
    m = _PRICE_SUM.search(text)
    if m:
        digits = re.sub(r"\s", "", m.group(1))
        return f"{digits} so'm"
    if _PRICE_NEGOTIABLE.search(text):
        return "Kelishiladi"
    return None
