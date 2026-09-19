"""
AI (Claude) yordamchi funksiyalar - IXTIYORIY qatlam.

MUHIM tamoyil: AI hech qachon yagona hakam emas, faqat TAKLIF beradi -
oxirgi qarorni odam (moderator/admin) yoki mavjud regex mantiq qabul
qiladi. Shuning uchun bu yerdagi HAR BIR funksiya:
  - ANTHROPIC_API_KEY bo'sh bo'lsa - None qaytaradi (chaqiruvchi eski
    mantiqqa qaytadi, hech narsa sinmaydi);
  - admin "ai_features_enabled" sozlamasini o'chirib qo'ysa - None
    qaytaradi (botni qayta ishga tushirmasdan, darhol kuchga kiradi -
    boshqa sozlamalar kabi);
  - so'rov davomida xatolik (tarmoq, JSON parse va h.k.) yuz bersa -
    xatoni log qilib, None qaytaradi (foydalanuvchi/moderator hech
    qachon AI xatosi tufayli bloklanmaydi).

Xarajat nazorati: faqat Claude Haiku 4.5 (eng arzon model) ishlatiladi,
har bir chaqiruv `ai_usage_log` jadvaliga (token va taxminiy $ xarajat
bilan) yoziladi - admin panelda ko'rinadi.
"""
import json
import logging
import re
from datetime import datetime, timedelta

from common.config import ANTHROPIC_API_KEY
from common.db import db, get_setting, now_str

logger = logging.getLogger(__name__)

AI_MODEL = "claude-haiku-4-5"
# Haiku 4.5 narxi (1 mln token uchun, USD) - taxminiy xarajatni hisoblash uchun.
_INPUT_COST_PER_MTOK = 1.00
_OUTPUT_COST_PER_MTOK = 5.00

_client = None
_client_tried = False


def _get_client():
    global _client, _client_tried
    if _client_tried:
        return _client
    _client_tried = True
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=20.0)
    except Exception:
        logger.exception("Anthropic klientini ishga tushirib bo'lmadi")
        _client = None
    return _client


def ai_features_enabled() -> bool:
    return bool(ANTHROPIC_API_KEY) and get_setting("ai_features_enabled", "0") == "1"


def _log_usage(feature: str, usage=None, ok: bool = True) -> None:
    try:
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cost = (input_tokens / 1_000_000) * _INPUT_COST_PER_MTOK + (output_tokens / 1_000_000) * _OUTPUT_COST_PER_MTOK
        conn = db()
        conn.execute(
            "INSERT INTO ai_usage_log (feature, input_tokens, output_tokens, cost_usd, ok, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (feature, input_tokens, output_tokens, cost, 1 if ok else 0, now_str()),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("AI xarajat logini yozib bo'lmadi")


def _extract_json(text: str):
    """Claude javobidan JSON obyektni ajratib oladi - markdown ```json
    bloklari yoki qo'shimcha matn bilan o'ralgan bo'lsa ham."""
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (ValueError, TypeError):
        return None


# ============================= 1: E'LON MAYDONLARINI AJRATIB OLISH =============================

_EXTRACT_SYSTEM = (
    "Siz Toshkentdagi ijara e'lonlari matnidan ma'lumot ajratib oluvchi yordamchisiz. "
    "Foydalanuvchi xom (masalan OLX'dan ko'chirilgan) e'lon matnini beradi. "
    "Undan quyidagi maydonlarni ajratib oling va FAQAT JSON formatida qaytaring, boshqa hech qanday matn yozmang:\n"
    '{"manzil": "tuman, mahalla/kvartal - agar matnda aniq bo\'lsa, aks holda null", '
    '"narx": "narx, matndagi shakilda qisqa (masalan \'350$\', \'1.2 mln\', \'kelishiladi\') - agar bo\'lmasa null", '
    '"xona": "xonalar soni, faqat raqam (masalan \'2\') - agar bo\'lmasa null"}\n'
    "Aniq ishonchingiz komil bo'lmasa, o'sha maydonni null qiling - taxmin qilmang."
)


def ai_extract_listing_fields(raw_text: str):
    """Xom e'lon matnidan manzil/narx/xona ajratib olishga harakat qiladi.
    Muvaffaqiyatsiz yoki o'chirilgan bo'lsa None qaytaradi. Muvaffaqiyatli
    bo'lsa - faqat AI ANIQ topgan maydonlarni o'z ichiga olgan dict
    qaytaradi (masalan faqat {"narx": "300$"})."""
    if not ai_features_enabled() or not (raw_text or "").strip():
        return None
    client = _get_client()
    if not client:
        return None
    try:
        response = client.messages.create(
            model=AI_MODEL, max_tokens=300,
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": raw_text[:4000]}],
        )
        _log_usage("extract_listing_fields", response.usage, ok=True)
        text = next((b.text for b in response.content if b.type == "text"), "")
        data = _extract_json(text)
        if not isinstance(data, dict):
            return None
        result = {}
        for key in ("manzil", "narx", "xona"):
            value = data.get(key)
            if isinstance(value, str) and value.strip() and value.strip().lower() != "null":
                result[key] = value.strip()
        return result or None
    except Exception:
        logger.exception("ai_extract_listing_fields xatolik")
        _log_usage("extract_listing_fields", ok=False)
        return None


# ============================= 2: FIRIBGARLIK BELGILARINI SKRINING =============================

_SCAM_SYSTEM = (
    "Siz Toshkentdagi ijara e'lonlari orasidan FIRIBGARLIK (aldov) belgilarini aniqlaydigan "
    "yordamchisiz. Odatiy firibgarlik naqshlari: oldindan (ko'rmasdan) pul/kafolat puli so'rash, "
    "juda past narx bilan shoshiltirish, faqat karta orqali to'lovni talab qilish, aloqa faqat "
    "tashqi messenjer orqali bo'lishini talab qilish. Berilgan e'lon matnini tahlil qiling va "
    "FAQAT JSON qaytaring, boshqa matn yozmang:\n"
    '{"suspicious": true yoki false, "reason": "qisqa sabab (o\'zbek tilida, 1 gap) - suspicious=false bo\'lsa bo\'sh qoldiring"}\n'
    "Faqat ANIQ, kuchli belgilar bo'lsa true qiling - oddiy, zararsiz e'lonlarni behuda shubhali deb belgilamang."
)


def ai_screen_for_scam(raw_text: str):
    """E'lon matnida firibgarlik belgilarini tekshiradi. None = AI fikr
    bera olmadi (o'chirilgan/xatolik) - bu holatda listing ODATDAGIDEK
    davom etadi, hech kim bloklanmaydi. dict qaytsa: {"suspicious": bool,
    "reason": str}."""
    if not ai_features_enabled() or not (raw_text or "").strip():
        return None
    client = _get_client()
    if not client:
        return None
    try:
        response = client.messages.create(
            model=AI_MODEL, max_tokens=200,
            system=_SCAM_SYSTEM,
            messages=[{"role": "user", "content": raw_text[:4000]}],
        )
        _log_usage("screen_for_scam", response.usage, ok=True)
        text = next((b.text for b in response.content if b.type == "text"), "")
        data = _extract_json(text)
        if not isinstance(data, dict) or "suspicious" not in data:
            return None
        return {"suspicious": bool(data.get("suspicious")), "reason": str(data.get("reason") or "").strip()}
    except Exception:
        logger.exception("ai_screen_for_scam xatolik")
        _log_usage("screen_for_scam", ok=False)
        return None


# ============================= 3: TO'LOV CHEKINI OLDINDAN TEKSHIRISH =============================

_RECEIPT_SYSTEM = (
    "Siz to'lov chekining skrinshotini tekshiruvchi yordamchisiz. Sizga kutilayotgan summa va "
    "karta egasining ismi beriladi. Rasmdagi chek shu ma'lumotlarga mos keladimi tekshiring. "
    "FAQAT JSON qaytaring, boshqa matn yozmang:\n"
    '{"matches": true yoki false, "note": "qisqa izoh (o\'zbek tilida, 1 gap) - masalan nomuvofiqlik topilsa nima"}\n'
    "Agar rasmni umuman o'qib bo'lmasa yoki chek ekanligi noaniq bo'lsa, matches=false va note'da shuni yozing."
)


def ai_check_receipt(image_bytes: bytes, media_type: str, expected_amount: int, card_holder: str):
    """To'lov cheki rasmini kutilgan summa/karta egasi bilan solishtiradi.
    None = AI fikr bera olmadi (bu holatda moderator ODATDAGIDEK qo'lda
    tekshiradi - hech narsa o'zgarmaydi). dict qaytsa: {"matches": bool,
    "note": str}."""
    if not ai_features_enabled() or not image_bytes:
        return None
    client = _get_client()
    if not client:
        return None
    try:
        import base64
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        response = client.messages.create(
            model=AI_MODEL, max_tokens=200,
            system=_RECEIPT_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": f"Kutilayotgan summa: {expected_amount:,} so'm. Karta egasi: {card_holder or '(belgilanmagan)'}."},
                ],
            }],
        )
        _log_usage("check_receipt", response.usage, ok=True)
        text = next((b.text for b in response.content if b.type == "text"), "")
        data = _extract_json(text)
        if not isinstance(data, dict) or "matches" not in data:
            return None
        return {"matches": bool(data.get("matches")), "note": str(data.get("note") or "").strip()}
    except Exception:
        logger.exception("ai_check_receipt xatolik")
        _log_usage("check_receipt", ok=False)
        return None


def ai_usage_summary(days: int = 30) -> dict:
    """Admin panel uchun - so'nggi N kundagi AI xarajati/chaqiruvlar soni."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    row = conn.execute(
        """SELECT COUNT(*) calls, COALESCE(SUM(input_tokens),0) input_tokens,
                  COALESCE(SUM(output_tokens),0) output_tokens, COALESCE(SUM(cost_usd),0) cost_usd,
                  COALESCE(SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END),0) errors
           FROM ai_usage_log WHERE created_at >= ?""",
        (since,),
    ).fetchone()
    conn.close()
    return dict(row) if row else {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0, "errors": 0}
