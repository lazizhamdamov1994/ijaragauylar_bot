"""
Bizning brendimizni har bir rasmga bosish (watermark).
==========================================================================
MUHIM: bu boshqa saytlar/agentliklarning watermarkini OLIB TASHLAMAYDI -
buni ishonchli va arzon qilib bo'lmaydi (ML modeli yoki pullik API kerak
bo'ladi, kichik serverga og'ir). Buning o'rniga - haqiqiy ijara-saytlari
(OLX kabi) qiladigan ishni qilamiz: HAR BIR rasmga, birinchi yuklanganda,
BIR MARTA, o'zimizning logotipimiz + sayt manzilini bosamiz. Shundan keyin
u qayerda chiqmasin (kanalda, saytda) - bizning brendimiz bilan chiqadi.

Xatolik yuz bersa (masalan logo.png topilmasa) - ORIGINAL rasm baytlari
qaytariladi, hech qachon e'lon joylashni TO'XTATMAYDI.
"""
import io
import logging
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_PATH = os.path.join(BASE_DIR, "logo.png")
WATERMARK_TEXT = "ijaragauylar.uz"

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)

_logo_cache = None
_logo_cache_loaded = False


def _load_logo():
    global _logo_cache, _logo_cache_loaded
    if _logo_cache_loaded:
        return _logo_cache
    _logo_cache_loaded = True
    try:
        _logo_cache = Image.open(LOGO_PATH).convert("RGBA")
    except Exception:
        logger.warning("logo.png topilmadi (%s) - watermark faqat matn bilan bosiladi", LOGO_PATH)
        _logo_cache = None
    return _logo_cache


def _load_font(size: int):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def apply_watermark(image_bytes: bytes) -> bytes:
    """Rasmning pastki-o'ng burchagiga logotip + 'ijaragauylar.uz' yozuvini
    bosib, JPEG bayt sifatida qaytaradi. Har qanday ichki xatolikda ORIGINAL
    baytlar qaytariladi - bu funksiya HECH QACHON exception ko'tarmaydi."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)  # telefon rasmlari "yotib qolmasligi" uchun
        img = img.convert("RGBA")
        w, h = img.size

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        margin = max(int(min(w, h) * 0.025), 10)
        logo_h = min(max(int(h * 0.09), 28), 100)

        logo = _load_logo()
        right_edge = w - margin
        bottom_edge = h - margin

        if logo is not None:
            ratio = logo_h / logo.height
            logo_w = max(int(logo.width * ratio), 1)
            logo_resized = logo.resize((logo_w, logo_h), Image.LANCZOS)
            # Biroz shaffof - belgi ko'zga tashlanadi, lekin rasmni to'smaydi.
            alpha = logo_resized.split()[-1].point(lambda p: int(p * 0.88))
            logo_resized.putalpha(alpha)
            logo_x = right_edge - logo_w
            logo_y = bottom_edge - logo_h
            overlay.alpha_composite(logo_resized, (logo_x, logo_y))
            text_right_edge = logo_x - 8
            text_center_y = logo_y + logo_h // 2
        else:
            text_right_edge = right_edge
            text_center_y = bottom_edge - logo_h // 2

        draw = ImageDraw.Draw(overlay)
        font = _load_font(max(int(logo_h * 0.4), 13))
        bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        text_x = text_right_edge - text_w
        text_y = text_center_y - text_h // 2

        for dx, dy in ((1, 1), (-1, -1), (1, -1), (-1, 1), (0, 1), (1, 0)):
            draw.text((text_x + dx, text_y + dy), WATERMARK_TEXT, font=font, fill=(0, 0, 0, 150))
        draw.text((text_x, text_y), WATERMARK_TEXT, font=font, fill=(255, 255, 255, 235))

        result = Image.alpha_composite(img, overlay).convert("RGB")
        out = io.BytesIO()
        result.save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception:
        logger.exception("Watermark bosishda xatolik - original rasm ishlatildi")
        return image_bytes
