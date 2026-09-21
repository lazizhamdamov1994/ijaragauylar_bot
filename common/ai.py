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
# Har bir model uchun narx (1 mln token uchun, USD: kirish, chiqish) -
# taxminiy xarajatni hisoblash uchun. Ko'pchilik funksiya arzon Haiku
# modelidan foydalanadi (yuqori hajm); faqat sifat muhim bo'lgan, kam
# chaqiriladigan funksiyalar (masalan kunlik AI hisobot) kuchliroq
# Opus 5'dan foydalanadi.
OPS_REPORT_MODEL = "claude-opus-5"
_MODEL_PRICING = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-5": (5.00, 25.00),
}
_DEFAULT_PRICING = _MODEL_PRICING[AI_MODEL]

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


def _log_usage(feature: str, usage=None, ok: bool = True, model: str = None) -> None:
    try:
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        input_cost_per_mtok, output_cost_per_mtok = _MODEL_PRICING.get(model, _DEFAULT_PRICING)
        cost = (input_tokens / 1_000_000) * input_cost_per_mtok + (output_tokens / 1_000_000) * output_cost_per_mtok
        conn = db()
        conn.execute(
            "INSERT INTO ai_usage_log (feature, input_tokens, output_tokens, cost_usd, ok, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (feature, input_tokens, output_tokens, cost, 1 if ok else 0, now_str()),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("AI xarajat logini yozib bo'lmadi")


_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def strip_markdown(text: str) -> str:
    """AI vaqti-vaqti bilan qoidaga qaramay Markdown yozib qo'yishi mumkin
    (masalan **havola**) - bot/veb xabarlari oddiy matn sifatida yuborilgani
    uchun bu belgilar havolaga yopishib, buzilgan URL hosil qiladi. Shuning
    uchun har bir foydalanuvchiga ko'rinadigan AI javobi (concierge,
    hisobot va h.k.) shu orqali qo'shimcha tozalanadi."""
    text = _MD_LINK_RE.sub(lambda m: f"{m.group(1)}: {m.group(2)}", text)
    text = text.replace("**", "").replace("__", "")
    return text


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


# ============================= 4: KUNLIK AI BOSHQARUV HISOBOTI =============================

_OPS_REPORT_SYSTEM = (
    "Siz \"Ijaraga Uylar\" (ijaragauylar.uz) platformasining AI boshqaruv yordamchisisiz. "
    "Platforma egasi davlat ishida band, kuniga bir marta sizning qisqa hisobotingizni o'qiydi - "
    "boshqa hech narsani faol kuzatib turmaydi. Sizga bugungi/joriy raqamlar beriladi.\n\n"
    "QOIDALAR:\n"
    "- FAQAT berilgan raqamlar asosida yozing - hech qanday raqam yoki faktni o'zingizdan "
    "o'ylab topmang yoki taxmin qilmang.\n"
    "- Qisqa, aniq, o'zbek tilida yozing (4-6 gap, executive-brief uslubida) - uzun tahlil emas.\n"
    "- Avval eng muhim natijani ayting (o'sish/pasayish, daromad), keyin agar raqamlarda real "
    "muammo ko'rinsa (masalan ko'p rad etilgan e'lon, AI ko'p firibgarlik topgan, o'sish sust) - "
    "shuni ochiq ayting.\n"
    "- Oxirida 1-2 ta ANIQ, amalga oshirish mumkin bo'lgan tavsiya bering (masalan qaysi sozlamani "
    "o'zgartirish, qayerga e'tibor qaratish) - umumiy \"yaxshiroq ishlang\" kabi bo'sh gap emas.\n"
    "- Hech qanday Markdown belgisidan foydalanmang (**, __, #, [matn](havola)) - javobingiz "
    "Telegram'da oddiy matn sifatida yuboriladi."
)


def ai_generate_ops_report(stats_text: str) -> str:
    """Kunlik/haftalik raqamlardan (oldindan tayyorlangan, o'qilishi oson matn
    blok - bot/jobs.py'dagi collect_ops_report_stats() yasaydi) qisqa AI
    tahlili + tavsiyalar yozadi. None = AI fikr bera olmadi (o'chirilgan/
    xatolik) - bu holatda chaqiruvchi (job_ai_daily_report) raqamlarning
    o'zini, sharhsiz, standart shablon bilan yuborishga o'tadi - egasi
    hech qachon hisobotsiz qolmaydi."""
    if not ai_features_enabled() or not (stats_text or "").strip():
        return None
    client = _get_client()
    if not client:
        return None
    try:
        response = client.messages.create(
            model=OPS_REPORT_MODEL, max_tokens=1500,
            output_config={"effort": "low"},
            system=_OPS_REPORT_SYSTEM,
            messages=[{"role": "user", "content": stats_text}],
        )
        _log_usage("ops_report", response.usage, ok=True, model=OPS_REPORT_MODEL)
        text = next((b.text for b in response.content if b.type == "text"), "")
        text = strip_markdown(text).strip()
        return text or None
    except Exception:
        logger.exception("ai_generate_ops_report xatolik")
        _log_usage("ops_report", ok=False, model=OPS_REPORT_MODEL)
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
