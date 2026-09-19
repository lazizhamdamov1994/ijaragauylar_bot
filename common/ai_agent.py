"""
AI Concierge - bot va sayt uchun UMUMIY suhbat-agent qatlami. Foydalanuvchi
erkin tabiiy tilda yozadi ("Chilonzorda 2 xonali, 300$ gacha uy kerak"),
AI bazadan mos e'lonlarni izlab topadi (search_listings tool orqali) va
javob beradi.

MUHIM chegaralar (common/ai.py bilan bir xil tamoyil):
  - Faqat "ai_features_enabled" yoqilgan bo'lsa ishlaydi.
  - Har bir foydalanuvchi/mehmon uchun kunlik xabar chegarasi bor
    (ai_concierge_daily_limit) - xarajat nazoratdan chiqmasligi uchun.
  - AI hech qachon telefon raqamini o'zi bermaydi va pullik (Limit)
    to'siqni chetlab o'tmaydi - faqat mavjud e'lonlarga havola beradi,
    "Uy egasi raqami" tugmasi orqali ko'rish odatdagidek Limit/bepul
    ko'rish tizimiga bog'liq bo'lib qoladi.
  - Har bir chaqiruv ai_usage_log'ga yoziladi (feature="concierge").
"""
import json
import logging

from common.ai import AI_MODEL, _get_client, _log_usage, ai_features_enabled
from common.db import count_today_ai_chat_messages, get_setting, log_ai_chat_message

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
MAX_HISTORY_MESSAGES = 20  # eski xabarlarni kesib tashlaydi - token xarajatini cheklaydi

SEARCH_TOOL = {
    "name": "search_listings",
    "description": (
        "Ijaraga Uylar bazasidan mos keladigan e'lonlarni qidiradi. Foydalanuvchi tuman, "
        "xonalar soni, narx yoki ijara turi bo'yicha talab bildirsa shu funksiyani chaqiring."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hudud": {"type": "string", "description": "Tuman nomi (masalan 'Chilonzor', 'Yunusobod') - noma'lum bo'lsa bo'sh qoldiring"},
            "xona": {"type": "string", "description": "Xonalar soni ('1','2','3','4') - noma'lum bo'lsa bo'sh qoldiring"},
            "rental_type": {"type": "string", "enum": ["", "uzoq_muddat", "kunlik", "dacha", "mehmonxona"], "description": "Ijara turi - noma'lum bo'lsa bo'sh"},
            "narx_max_som": {"type": "integer", "description": "Maksimal narx SO'MDA (agar foydalanuvchi dollarda aytsa, tizim sozlamasidagi kursga ko'ra o'zingiz so'mga o'tkazing) - cheklov yo'q bo'lsa 0"},
        },
        "required": [],
    },
}


def _search_listings_tool(hudud: str = "", xona: str = "", rental_type: str = "", narx_max_som: int = 0) -> dict:
    from common.config import SITE_URL
    from common.districts import parse_price_value
    from web.listings_data import get_site_listings

    listings, total = get_site_listings(hudud=hudud or "", xona=xona or "", rental_type=rental_type or "", page=1)
    results = []
    for l in listings:
        if narx_max_som:
            val = parse_price_value(l.get("narx"))
            if val is not None and val > narx_max_som:
                continue
        results.append({
            "manzil": l.get("manzil"), "narx": l.get("narx"), "xona": l.get("xona"),
            "link": f"{SITE_URL}/uy/{l['id']}" if SITE_URL else f"/uy/{l['id']}",
        })
        if len(results) >= 5:
            break
    return {"jami_topildi": total, "korsatilgan": results}


def _concierge_system_prompt() -> str:
    usd_rate = get_setting("usd_to_som_rate", "12700")
    return (
        "Siz \"Ijaraga Uylar\" (ijaragauylar.uz) - Toshkentdagi maklersiz ijara e'lonlari "
        "platformasining AI yordamchisisiz. Vazifangiz: foydalanuvchiga mos uy topishda yordam berish, "
        "savollarga qisqa va aniq javob berish.\n\n"
        "QOIDALAR:\n"
        "- Uy qidirish so'ralsa - HAR DOIM search_listings funksiyasini chaqiring, hech qachon "
        "e'lonlarni o'zingizdan o'ylab topmang.\n"
        f"- Agar foydalanuvchi narxni dollarda aytsa (masalan '300$ gacha'), {usd_rate} so'm/$ kursi "
        "bilan taxminiy so'mga o'tkazib narx_max_som parametriga bering.\n"
        "- Uy egasining TELEFON RAQAMINI hech qachon bermang - bu faqat botda \"Uy egasi raqami\" "
        "tugmasi orqali (Limit/bepul ko'rish tizimiga bog'liq) ko'rinadi. Agar so'rasa, shu tugmani "
        "bosishni tavsiya qiling.\n"
        "- Javoblaringiz qisqa, samimiy va o'zbek tilida bo'lsin (foydalanuvchi rus/ingliz tilida "
        "yozsa, shu tilda javob bering).\n"
        "- E'lon topilmasa, buni ochiq ayting va boshqa mezon bilan qidirishni taklif qiling.\n"
        "- Platformaga aloqasi bo'lmagan savollarga (siyosat, dasturlash va h.k.) javob bermang, "
        "muloyimlik bilan mavzuga qaytaring."
    )


def concierge_rate_limited(user_key: str, platform: str) -> bool:
    try:
        limit = int(get_setting("ai_concierge_daily_limit", "30"))
    except (TypeError, ValueError):
        limit = 30
    return count_today_ai_chat_messages(user_key, platform) >= limit


async def concierge_turn(user_key: str, platform: str, history: list, user_message: str):
    """Bitta suhbat almashinuvi: oldingi tarix + yangi xabar -> AI javobi
    + yangilangan tarix. AI o'chirilgan/mavjud bo'lmasa (None, history)
    qaytaradi - chaqiruvchi mos xabar ko'rsatishi kerak."""
    if not ai_features_enabled():
        return None, history
    client = _get_client()
    if not client:
        return None, history

    log_ai_chat_message(user_key, platform)
    messages = list(history[-MAX_HISTORY_MESSAGES:]) + [{"role": "user", "content": user_message}]

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            response = client.messages.create(
                model=AI_MODEL, max_tokens=600,
                system=_concierge_system_prompt(),
                tools=[SEARCH_TOOL],
                messages=messages,
            )
            _log_usage("concierge", response.usage, ok=True)

            if response.stop_reason == "tool_use":
                tool_blocks = [b for b in response.content if b.type == "tool_use"]
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for tb in tool_blocks:
                    if tb.name == "search_listings":
                        result = _search_listings_tool(**tb.input)
                    else:
                        result = {"error": "unknown_tool"}
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": tb.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                messages.append({"role": "user", "content": tool_results})
                continue

            text = next((b.text for b in response.content if b.type == "text"), "")
            messages.append({"role": "assistant", "content": response.content})
            return text, messages

        return "Kechirasiz, so'rovingizni birroz soddaroq qayta yozib ko'ring.", messages
    except Exception:
        logger.exception("AI concierge xatolik")
        _log_usage("concierge", ok=False)
        return None, history
