"""
Bizning brendimizni har bir rasmga bosish (watermark).
==========================================================================
MUHIM: bu boshqa saytlar/agentliklarning watermarkini OLIB TASHLAMAYDI -
buni ishonchli va arzon qilib bo'lmaydi (ML modeli yoki pullik API kerak
bo'ladi, kichik serverga og'ir). Buning o'rniga - haqiqiy ijara-saytlari
(OLX kabi) qiladigan ishni qilamiz: HAR BIR rasmga, birinchi yuklanganda,
BIR MARTA, o'zimizning logotipimizni bosamiz. Shundan keyin u qayerda
chiqmasin (kanalda, saytda, Instagram videosida) - bizning brendimiz bilan
chiqadi. FAQAT logotip - qo'shimcha yozuv YO'Q (logo o'zi yetarli va
tozaroq ko'rinadi).

Xatolik yuz bersa (masalan logo topilmasa) - ORIGINAL rasm baytlari
qaytariladi, hech qachon e'lon joylashni TO'XTATMAYDI.
"""
import io
import logging
import os

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# MUHIM: bu logo.png'DAN ALOHIDA - logo.png sayt (web/) uchun ishlatilishda
# davom etadi, pechat_logo.png esa FAQAT rasmlarga (e'lon fotolari, Instagram
# slaydshov videosi) bosiladigan muhr uchun (repo ildiziga alohida yuklanadi).
LOGO_PATH = os.path.join(BASE_DIR, "pechat_logo.png")

_logo_cache = None
_logo_cache_loaded = False


def load_logo():
    """`pechat_logo.png`ni (RGBA, keshlangan) qaytaradi - topilmasa None.
    Watermark bosishda ham, Instagram slaydshov videosidagi brend belgisi
    uchun ham (common/slideshow.py) BITTA manbadan ishlatiladi."""
    global _logo_cache, _logo_cache_loaded
    if _logo_cache_loaded:
        return _logo_cache
    _logo_cache_loaded = True
    try:
        _logo_cache = Image.open(LOGO_PATH).convert("RGBA")
    except Exception:
        logger.warning("pechat_logo.png topilmadi (%s) - watermark bosilmaydi", LOGO_PATH)
        _logo_cache = None
    return _logo_cache


def apply_watermark(image_bytes: bytes) -> bytes:
    """Rasmning pastki-o'ng burchagiga logotipni bosib, JPEG bayt sifatida
    qaytaradi. Logo topilmasa yoki har qanday ichki xatolikda ORIGINAL
    baytlar qaytariladi - bu funksiya HECH QACHON exception ko'tarmaydi."""
    logo = load_logo()
    if logo is None:
        return image_bytes
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)  # telefon rasmlari "yotib qolmasligi" uchun
        img = img.convert("RGBA")
        w, h = img.size

        margin = max(int(min(w, h) * 0.025), 10)
        logo_h = min(max(int(h * 0.13), 40), 150)
        ratio = logo_h / logo.height
        logo_w = max(int(logo.width * ratio), 1)
        logo_resized = logo.resize((logo_w, logo_h), Image.LANCZOS)
        # Biroz shaffof - belgi ko'zga tashlanadi, lekin rasmni to'smaydi.
        alpha = logo_resized.split()[-1].point(lambda p: int(p * 0.88))
        logo_resized.putalpha(alpha)

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay.alpha_composite(logo_resized, (w - margin - logo_w, h - margin - logo_h))

        result = Image.alpha_composite(img, overlay).convert("RGB")
        out = io.BytesIO()
        result.save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception:
        logger.exception("Watermark bosishda xatolik - original rasm ishlatildi")
        return image_bytes
