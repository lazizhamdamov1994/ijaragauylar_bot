"""
Toshkent tumanlari - bot va veb UMUMIY (ikkalasi ham erkin matndan tuman
nomini avtomatik aniqlashi kerak: veb - SEO breadcrumb/sitemap va tuman
filtri uchun, bot - "Tezkor e'lon" oqimida manzilni avtomatik taklif
qilish uchun).

MUHIM: tuman -> kalit so'z (alias) bog'lanishi endi DB'dagi
`district_aliases` jadvalida saqlanadi, qattiq kodlangan ro'yxat EMAS -
shu orqali admin/moderatorlar vaqt o'tishi bilan yangi kalit so'zlar
(mahalla/mavze/mashxur joy nomlari - masalan "Darxon" -> Sergeli)
qo'shib, tizimni "o'rgatib" boraveradi, kod o'zgartirmasdan va qayta
deploy qilmasdan. Pastdagi _SEED_DISTRICT_ALIASES faqat DASTLABKI
(bo'sh jadvalga bir martalik) to'ldirish uchun ishlatiladi.
"""
import re

from common.db import db, now_str

TASHKENT_DISTRICTS = [
    "Yunusobod", "Chilonzor", "Sergeli", "Mirzo Ulug'bek", "Shayxontohur",
    "Olmazor", "Bektemir", "Uchtepa", "Yashnobod", "Yakkasaroy",
    "Mirobod", "Yangihayot",
]

# Boshlang'ich (urug') kalit so'zlar - DB jadvali bo'sh bo'lsa, bir marta
# shu ro'yxat bilan to'ldiriladi (seed_district_aliases()). Shundan keyin
# ro'yxat FAQAT DB orqali (admin/moderator amallari bilan) kengayadi.
_SEED_DISTRICT_ALIASES = {
    "Yunusobod": [
        "yunusobod", "yunusabad", "юнусобод", "юнусабад",
        "megaplanet", "mega planet", "мегапланет", "мега плэнет",
        "turkiston", "туркистон", "7a mavze", "7-a mavze", "7 mavze", "7-мавзе",
    ],
    "Chilonzor": ["chilonzor", "chilanzar", "чилонзор", "чиланзар"],
    "Sergeli": [
        "sergeli", "сергели",
        "darxon", "дархон", "yangi darxon", "янги дархон",
        "choshtepa", "чоштепа",
    ],
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


def seed_district_aliases() -> None:
    """Ilova ishga tushganda chaqiriladi (bot/main.py, web/app.py). Jadval
    BO'SH bo'lsagina boshlang'ich ro'yxatni yozadi - keyingi ishga
    tushishlarda (jadvalda allaqachon qatorlar bo'lgani uchun) hech
    narsa qilmaydi, shu bilan admin qo'shgan/o'chirgan aliaslarga
    tegmaydi."""
    conn = db()
    count = conn.execute("SELECT COUNT(*) c FROM district_aliases").fetchone()["c"]
    if count == 0:
        for district, aliases in _SEED_DISTRICT_ALIASES.items():
            for alias in aliases:
                conn.execute(
                    "INSERT OR IGNORE INTO district_aliases (alias, district, added_by, added_at) VALUES (?, ?, NULL, ?)",
                    (alias.strip().lower(), district, now_str()),
                )
        conn.commit()
    conn.close()


def list_district_aliases() -> list:
    conn = db()
    rows = conn.execute("SELECT * FROM district_aliases ORDER BY district, alias").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_aliases_for_district(district: str) -> list:
    """Berilgan tumanga bog'langan barcha kalit so'zlarni (o'zi + aliaslar)
    qaytaradi - tuman filtri (web/listings_data.py) shu ro'yxatning
    HAR BIRINI manzil/mo'ljal matnida qidiradi, shu orqali "Darxon" deb
    yozilgan e'lon ham "Sergeli" filtrida chiqadi."""
    conn = db()
    rows = conn.execute("SELECT alias FROM district_aliases WHERE district = ?", (district,)).fetchall()
    conn.close()
    return [district] + [r["alias"] for r in rows]


def add_district_alias(alias: str, district: str, added_by: int = None) -> bool:
    alias = (alias or "").strip().lower()
    if not alias or district not in TASHKENT_DISTRICTS:
        return False
    conn = db()
    cur = conn.execute(
        "INSERT OR IGNORE INTO district_aliases (alias, district, added_by, added_at) VALUES (?, ?, ?, ?)",
        (alias, district, added_by, now_str()),
    )
    conn.commit()
    added = cur.rowcount > 0
    conn.close()
    return added


def remove_district_alias(alias_id: int) -> None:
    conn = db()
    conn.execute("DELETE FROM district_aliases WHERE id = ?", (alias_id,))
    conn.commit()
    conn.close()


def detect_district(text: str):
    """Matndan tuman nomini (yoki unga bog'langan kalit so'zni) aniqlaydi.
    Topilmasa None qaytaradi (masalan "Tezkor e'lon" oqimida - avtomatik
    taklif berish kerakmi yoki yo'qmi shuni ANIQ bilish uchun; "Toshkent"
    degan noaniq standart qiymat bu yerda ishlatilmaydi)."""
    low = (text or "").lower()
    if not low:
        return None
    conn = db()
    rows = conn.execute("SELECT alias, district FROM district_aliases").fetchall()
    conn.close()
    for r in rows:
        if r["alias"] in low:
            return r["district"]
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


_PHONE_PATTERN = re.compile(r"(?:\+998|998)[\s\-]?(\d{2})[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})\b")


def detect_phone(text: str):
    """Matndan O'zbekiston telefon raqamini ajratib olishga harakat qiladi
    (masalan Tezkor e'lon xom OLX matnida raqam ham bo'lsa). MUHIM: faqat
    aniq "+998"/"998" prefiksi bilan yozilgan raqamlarni tanib oladi -
    prefikssiz 9 xonali ketma-ketliklar (narx, uy raqami va h.k. bilan
    adashtirib yuborish xavfi yuqori) qabul qilinmaydi. Topilmasa None."""
    if not text:
        return None
    m = _PHONE_PATTERN.search(text)
    if not m:
        return None
    digits = "998" + "".join(m.groups())
    if not re.fullmatch(r"998\d{9}", digits):
        return None
    return "+" + digits


_PRICE_RAW_NUMBER = re.compile(r"\d[\d\s.,]{4,}\d")
_PRICE_ALREADY_SHORT = re.compile(r"\$|y\.?\s?e\.?|у\.?\s?е\.?|mln|млн|kelishiladi|келишилади|договорн", re.IGNORECASE)


def format_price_compact(narx: str) -> str:
    """Xaritadagi narx yorlig'i uchun: narx maydonida ba'zan butun bir
    gap/so'z bilan yozilgan uzun matn kelib qolishi mumkin - bu xaritada
    xunuk ko'rinadi. Agar narx allaqachon qisqa va tayyor holatda bo'lsa
    ($ , y.e., mln, kelishiladi) o'zgarishsiz qoldiradi; aks holda matndan
    aniq narxni ajratib oladi va katta xom raqamlarni ("1000000") "1 mln
    so'm" kabi qisqartirib ko'rsatadi. Hech narsa topa olmasa, uzun matnni
    kesib "..." bilan qisqartiradi."""
    narx = (narx or "").strip()
    if not narx:
        return narx
    if len(narx) <= 22 and _PRICE_ALREADY_SHORT.search(narx):
        return narx

    extracted = detect_price(narx)
    if extracted and extracted != narx:
        return format_price_compact(extracted)
    if extracted:
        narx = extracted

    m = _PRICE_RAW_NUMBER.search(narx)
    if m:
        digits = re.sub(r"[\s.,]", "", m.group(0))
        if digits.isdigit():
            n = int(digits)
            if n >= 1_000_000:
                mln_str = f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".")
                return f"{mln_str} mln so'm"
            if n >= 1000:
                return f"{n:,}".replace(",", " ") + " so'm"

    if len(narx) > 22:
        return narx[:19].rstrip() + "..."
    return narx


def parse_price_value(narx: str, usd_to_som_rate: int = 12700):
    """Narxni (erkin matn) taqqoslash uchun so'mdagi taxminiy raqamga
    aylantiradi (sayt saralashi - "Eng arzon"/"Eng qimmat" - uchun). $
    va y.e. (shartli birlik) `usd_to_som_rate` orqali so'mga o'tkaziladi.
    Aniqlab bo'lmasa (masalan "Kelishiladi" yoki bo'sh) None qaytaradi -
    bunday e'lonlar saralashda oxirga suriladi."""
    narx = (narx or "").strip()
    if not narx:
        return None
    m = _PRICE_DOLLAR.search(narx) or _PRICE_DOLLAR_SUFFIX.search(narx)
    if m:
        try:
            return int(float(re.sub(r"[\s,]", "", m.group(1))) * usd_to_som_rate)
        except ValueError:
            pass
    m = _PRICE_YE.search(narx)
    if m:
        try:
            return int(float(re.sub(r"[\s,]", "", m.group(1))) * usd_to_som_rate)
        except ValueError:
            pass
    m = _PRICE_MLN_UZ.search(narx) or _PRICE_MLN_RU.search(narx)
    if m:
        try:
            return int(float(m.group(1).replace(",", ".")) * 1_000_000)
        except ValueError:
            pass
    m = _PRICE_SUM.search(narx) or _PRICE_RAW_NUMBER.search(narx)
    if m:
        digits = re.sub(r"[\s.,]", "", m.group(1) if m.lastindex else m.group(0))
        if digits.isdigit():
            return int(digits)
    return None
