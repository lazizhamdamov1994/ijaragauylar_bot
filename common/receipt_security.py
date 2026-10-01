"""
To'lov cheklari xavfsizligi - ikkita mustaqil narsani ta'minlaydi:

1. Bitta chek rasmini bir nechta odam yuborib, har biri alohida to'lov
   (Limit, uy baholash, TOP'ga ko'tarish, pullik e'lon) olishga urinishini
   aniqlash - "barmoq izi" (perceptual hash, aHash) orqali. Faqat
   TASDIQLANGAN to'lovlar yozib boriladi, va tekshiruv FAQAT boshqa
   foydalanuvchi tomonidan oldin ishlatilgan cheklarni topadi (bitta
   odamning o'z chekini qayta yuborishi - masalan avval rad etilgan
   so'rovni qayta yuborish - bu yerda XATO signal EMAS).

   MUHIM chegaralanish: aHash yengil o'zgarishlarga (qayta siqish, kichik
   skrinshot farqlari) chidamli, lekin atayin kesilgan/tahrirlangan
   rasmni aniqlay olmasligi mumkin - bu 100% kafolat EMAS, balki eng keng
   tarqalgan "bitta screenshot'ni bir nechta odamga yuborish" holatini
   tutadigan amaliy to'siq. Shuning uchun topilgan moslik hech qachon
   AVTOMATIK rad etishga olib kelmaydi - faqat avtomatik tasdiqlashni
   to'xtatadi va adminga ALOHIDA, keskin ogohlantirish bilan yuboriladi
   (oxirgi qaror baribir odamda qoladi).

2. AI chek formatini (Click, Payme, Uzcard, Humo, bank ilovalari) noto'g'ri
   "mos emas" deb belgilagan, lekin admin baribir haqiqiy deb tasdiqlagan
   holatlarni "o'rganish" - shu orqali `ai_receipt_extra_guidance`
   sozlamasi avtomatik to'ldirib boriladi, keyingi AI chaqiruvlarida
   darhol kuchga kiradi (common/ai.py'dagi ai_check_receipt()ga qarang).
"""
import logging

from common.db import db, get_setting, now_str, set_setting

logger = logging.getLogger(__name__)

# aHash'da rasm shu o'lchamga (8x8=64 piksel) kichraytiriladi - kichikroq
# bo'lsa farqlarga unchalik sezgir emas, kattaroq bo'lsa haddan tashqari
# qattiq qiyoslaydi (ozgina siqilish farqini ham "boshqa rasm" deb o'ylaydi).
_HASH_SIZE = 8
# 64 bitdan nechtasi farq qilsa ham "bir xil chek" deb hisoblanadi - past
# qiymat qattiqroq (faqat deyarli bir xil rasmlarni tutadi), yuqori
# qiymat yumshoqroq (ko'proq soxta signal berishi mumkin). 6/64 ~ 91%
# o'xshashlik - amaliyotda qayta siqilgan/formatlari ozgina farq qiladigan
# bir xil skrinshotlarni ishonchli tutadi, lekin haqiqatda boshqa
# cheklarni bir-biriga aralashtirmaydi.
_MAX_HAMMING_DISTANCE = 6

MAX_GUIDANCE_ENTRIES = 10


def receipt_phash(image_bytes: bytes) -> str | None:
    """Rasmning aHash ("barmoq izi")ni hisoblaydi - 64 bitli hex satr
    sifatida. Rasmni o'qib bo'lmasa (buzilgan fayl va h.k.) - None."""
    if not image_bytes:
        return None
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("L").resize(
            (_HASH_SIZE, _HASH_SIZE), Image.LANCZOS,
        )
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p > avg else "0" for p in pixels)
        return f"{int(bits, 2):0{_HASH_SIZE * _HASH_SIZE // 4}x}"
    except Exception:
        logger.exception("receipt_phash: rasmni o'qib bo'lmadi")
        return None


def _hamming_distance(hash1: str, hash2: str) -> int:
    try:
        n1, n2 = int(hash1, 16), int(hash2, 16)
    except (TypeError, ValueError):
        return _HASH_SIZE * _HASH_SIZE  # noto'g'ri hash - "butunlay boshqa" deb hisoblash
    return bin(n1 ^ n2).count("1")


def find_cross_user_receipt_reuse(phash: str, user_id: int) -> dict | None:
    """Shu chek (yoki unga juda o'xshash rasm) BOSHQA foydalanuvchi
    tomonidan oldin TASDIQLANGAN to'lov uchun ishlatilganmi - tekshiradi.
    Topilsa: {"payment_type", "payment_ref_id", "user_id", "created_at"}."""
    if not phash:
        return None
    conn = db()
    rows = conn.execute(
        "SELECT phash, context_label, ref_id, user_id, created_at FROM receipt_hashes WHERE user_id != ? AND phash IS NOT NULL",
        (user_id,),
    ).fetchall()
    conn.close()
    for row in rows:
        if _hamming_distance(phash, row["phash"]) <= _MAX_HAMMING_DISTANCE:
            return {
                "payment_type": row["context_label"], "payment_ref_id": row["ref_id"],
                "user_id": row["user_id"], "created_at": row["created_at"],
            }
    return None


_PHASH_TABLES = {"listings", "subscriptions", "valuation_payments", "boost_payments"}


def store_receipt_phash(table: str, row_id: int, phash: str) -> None:
    """Chek yuborilgan payt hisoblangan "barmoq izi"ni shu to'lov so'rovi
    qatoriga yozib qo'yadi - tasdiqlash vaqtida (avtomatik yoki admin
    tomonidan) qayta Telegram'dan yuklab olish shart bo'lmasin uchun."""
    if table not in _PHASH_TABLES or not phash:
        return
    conn = db()
    conn.execute(f"UPDATE {table} SET receipt_phash = ? WHERE id = ?", (phash, row_id))
    conn.commit()
    conn.close()


def get_receipt_phash(table: str, row_id: int) -> str | None:
    if table not in _PHASH_TABLES:
        return None
    conn = db()
    row = conn.execute(f"SELECT receipt_phash FROM {table} WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    return row["receipt_phash"] if row else None


def record_approved_receipt(phash: str, payment_type: str, payment_ref_id: int, user_id: int) -> None:
    """To'lov TASDIQLANGANDA (avtomatik yoki admin tomonidan) chaqiriladi -
    shu chekning "barmoq izi"ni keyingi tekshiruvlar uchun saqlaydi
    (mavjud `receipt_hashes` jadvaliga - context_label/ref_id ustunlari)."""
    if not phash:
        return
    conn = db()
    conn.execute(
        "INSERT INTO receipt_hashes (phash, user_id, context_label, ref_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (phash, user_id, payment_type, payment_ref_id, now_str()),
    )
    conn.commit()
    conn.close()


def log_receipt_feedback(payment_type: str, payment_ref_id: int, ai_matched, ai_note: str, admin_decision: str) -> None:
    conn = db()
    conn.execute(
        "INSERT INTO receipt_feedback_log (payment_type, payment_ref_id, ai_matched, ai_note, admin_decision, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (payment_type, payment_ref_id, None if ai_matched is None else int(bool(ai_matched)), ai_note or "", admin_decision, now_str()),
    )
    conn.commit()
    conn.close()


def note_admin_overrode_ai_mismatch(ai_note: str) -> None:
    """Admin AI "mos emas" deb belgilagan chekni baribir HAQIQIY deb
    tasdiqlasa chaqiriladi - `ai_receipt_extra_guidance` sozlamasiga qisqa
    qo'shimcha yozuv qo'shadi (eng so'nggi MAX_GUIDANCE_ENTIRES tasi
    saqlanadi, eskilari chetlab tashlanadi - sozlama cheksiz o'smasligi
    uchun). Admin istalgan vaqt ushbu matnni admin panel/bot sozlamalari
    orqali ko'rib, qo'lda tahrirlashi yoki tozalashi mumkin."""
    note = (ai_note or "").strip()
    if not note:
        return
    current = (get_setting("ai_receipt_extra_guidance", "") or "").strip()
    entries = [e.strip() for e in current.split("\n") if e.strip()] if current else []
    new_entry = f"- Admin bunday holatni HAQIQIY chek deb tasdiqlagan: {note[:200]}"
    if new_entry in entries:
        return
    entries.append(new_entry)
    entries = entries[-MAX_GUIDANCE_ENTRIES:]
    set_setting("ai_receipt_extra_guidance", "\n".join(entries))
