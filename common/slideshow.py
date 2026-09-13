"""
E'lon rasmlaridan Instagram uchun qisqa (ovozsiz) slaydshov video yasash +
shu e'lon uchun tayyor Instagram post matnini (hashtaglar bilan) yozish.
==========================================================================
MUHIM: bu modul Instagram'ga HECH NARSANI o'zi avtomatik joylamaydi - u
faqat videoni yasab, botga (bot/flow_listing.py orqali) adminga yuboradi.
Instagram'ga joylashtirish - adminning o'zi qo'lda bajaradigan YAGONA ishi
(Instagram Graph API uchun Facebook Business sozlash talab qilinmasligi
uchun ataylab shunday soddalashtirilgan).

Video xatosiz yasalmasa (ffmpeg topilmadi, rasm buzuq va h.k.) - funksiya
None qaytaradi, bu e'lon joylashni HECH QACHON to'xtatmaydi (chaqiruvchi
kod xatoni yutib, botning asosiy oqimini davom ettiradi).

MUHIM (resurs): serverda bir vaqtning o'zida faqat BITTA video yasaladi
(_GEN_SEMAPHORE) - bir nechta e'lon "Ha" desa ham, videolar birin-ketin
navbat bilan tayyorlanadi, kichik VPS'ning xotirasi/protsessori bir vaqtda
haddan tashqari band bo'lib qolmaydi.
"""
import asyncio
import io
import logging
import os
import re
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

logger = logging.getLogger(__name__)

CANVAS_W, CANVAS_H = 1080, 1920  # Instagram Reels/Stories uchun tik (9:16) format
INTRO_STEP_SECONDS = 1  # sarlavha -> manzil -> narx uchun 3 ta alohida (1s dan) kadr - ketma-ket "ochilish" effekti
OTHER_FRAME_SECONDS = 1
MAX_PHOTOS = 10

BRAND_ACCENT = (255, 59, 92)  # sayt bilan bir xil #FF3B5C

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)

_GEN_SEMAPHORE = asyncio.Semaphore(1)


def _load_font(size: int):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _fit_frame(image_bytes: bytes) -> Image.Image:
    """Rasmni 1080x1920 kanvasga, KESMASDAN (to'liq ko'rinadigan qilib)
    joylaydi - bo'sh joylar o'sha rasmning o'zidan xiralashtirilgan fon
    bilan to'ldiriladi (professional slaydshovlarda keng qo'llaniladigan usul)."""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img).convert("RGB")

    bg = img.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(45))
    bg = Image.eval(bg, lambda p: int(p * 0.5))  # qorong'ilashtirish - old plandagi matn/rasm ko'zga yaqqol tashlanishi uchun

    ratio = min(CANVAS_W / img.width, CANVAS_H / img.height)
    new_w, new_h = max(int(img.width * ratio), 1), max(int(img.height * ratio), 1)
    fg = img.resize((new_w, new_h), Image.LANCZOS)
    bg.paste(fg, ((CANVAS_W - new_w) // 2, (CANVAS_H - new_h) // 2))
    return bg


def _vertical_gradient_scrim(y0: int, y1: int, peak_alpha: int) -> Image.Image:
    """y0..y1 oralig'ida yumshoq (qattiq chiziqsiz) qorong'ilashtiruvchi
    qatlam - kinematik "caption card" ko'rinishi uchun (qattiq to'rtburchak
    emas, yuqori/pastki chetlari asta so'nadi)."""
    band_h = y1 - y0
    gradient = Image.new("L", (1, band_h), 0)
    half = band_h // 2
    for y in range(band_h):
        dist_from_edge = min(y, band_h - 1 - y)
        alpha = min(peak_alpha, int(peak_alpha * (dist_from_edge / max(half * 0.5, 1))))
        gradient.putpixel((0, y), alpha)
    gradient = gradient.resize((CANVAS_W, band_h))
    layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    black = Image.new("RGBA", (CANVAS_W, band_h), (10, 8, 14, 255))
    black.putalpha(gradient)
    layer.paste(black, (0, y0), black)
    return layer


def _draw_spaced_text(draw, cx: int, y: int, text: str, font, fill, tracking: int = 6):
    """Harflar orasiga qo'shimcha bo'shliq (tracking) qo'yib, markazlashtirib
    chizadi - katta sarlavhalarni "premium" ko'rinishga keltiradi."""
    widths = [draw.textbbox((0, 0), ch, font=font)[2] for ch in text]
    total_w = sum(widths) + tracking * (len(text) - 1)
    x = cx - total_w // 2
    for ch, w in zip(text, widths):
        for dx, dy in ((2, 2), (-2, 2), (0, 3)):
            draw.text((x + dx, y + dy), ch, font=font, fill=(0, 0, 0, 160))
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking


def _centered_text(draw, y, text, font, fill=(255, 255, 255, 255), shadow=True):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (CANVAS_W - w) // 2
    if shadow:
        for dx, dy in ((2, 2), (-1, 2), (0, 3)):
            draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 170))
    draw.text((x, y), text, font=font, fill=fill)
    return w


def _centered_text_with_dot(draw, y, text, font, fill, dot_color):
    """Manzil qatori uchun - emoji shrift bilan har doim ham to'g'ri
    chiqmagani uchun (ba'zi serverlarda "quti" bo'lib chiqadi), oldida
    chizilgan rangli nuqta ishlatiladi - shrift'ga bog'liq emas, ishonchli."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    dot_r, gap = 8, 16
    total_w = dot_r * 2 + gap + text_w
    x0 = (CANVAS_W - total_w) // 2
    text_h = bbox[3] - bbox[1]
    dot_cy = y - bbox[1] + text_h // 2
    draw.ellipse([x0, dot_cy - dot_r, x0 + dot_r * 2, dot_cy + dot_r], fill=(*dot_color, 255))
    tx = x0 + dot_r * 2 + gap
    for dx, dy in ((2, 2), (-1, 2), (0, 3)):
        draw.text((tx + dx, y + dy), text, font=font, fill=(0, 0, 0, 170))
    draw.text((tx, y), text, font=font, fill=fill)


def _draw_price_chip(draw, cy: int, text: str, font):
    pad_x, pad_y = 46, 20
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    chip_w, chip_h = w + pad_x * 2, h + pad_y * 2
    x0 = (CANVAS_W - chip_w) // 2
    y0 = cy - chip_h // 2
    draw.rounded_rectangle(
        [x0 + 4, y0 + 6, x0 + chip_w + 4, y0 + chip_h + 6], radius=chip_h // 2, fill=(0, 0, 0, 90),
    )
    draw.rounded_rectangle(
        [x0, y0, x0 + chip_w, y0 + chip_h], radius=chip_h // 2, fill=(*BRAND_ACCENT, 255),
    )
    draw.text((x0 + pad_x - bbox[0], y0 + pad_y - bbox[1]), text, font=font, fill=(255, 255, 255, 255))


# Sarlavha kartasi joylashuvi (kanvasning o'rtasiga yaqin - reels'larda
# ko'z avval shu joyga tushadi).
CARD_TOP, CARD_BOTTOM = 690, 1260
TITLE_Y = 760
ACCENT_BAR_Y = 850
ADDRESS_Y = 900
PRICE_CY = 1050
CTA_Y = 1160


def _draw_intro_frame(canvas: Image.Image, step: int, manzil: str, narx: str) -> Image.Image:
    """BIRINCHI rasmning 3 ta bosqichli ("ochiluvchi") kadri:
    step 0 -> faqat sarlavha, step 1 -> + manzil, step 2 -> + narx va CTA."""
    canvas = canvas.convert("RGBA")
    overlay = _vertical_gradient_scrim(CARD_TOP, CARD_BOTTOM, peak_alpha=210)
    draw = ImageDraw.Draw(overlay)

    title_font = _load_font(84)
    address_font = _load_font(46)
    price_font = _load_font(56)
    cta_font = _load_font(36)

    _draw_spaced_text(draw, CANVAS_W // 2, TITLE_Y, "MAKLERSIZ UY", title_font, fill=(255, 255, 255, 255), tracking=8)
    bar_w = 130
    draw.rounded_rectangle(
        [(CANVAS_W - bar_w) // 2, ACCENT_BAR_Y, (CANVAS_W + bar_w) // 2, ACCENT_BAR_Y + 6],
        radius=3, fill=(*BRAND_ACCENT, 255),
    )

    if step >= 1:
        _centered_text_with_dot(draw, ADDRESS_Y, (manzil or "").strip()[:42], address_font, fill=(235, 238, 245, 255), dot_color=BRAND_ACCENT)

    if step >= 2:
        _draw_price_chip(draw, PRICE_CY, (narx or "").strip()[:24], price_font)
        _centered_text(draw, CTA_Y, "Uy egasi raqami Telegram kanalimizda", cta_font, fill=(255, 214, 102, 255))

    return Image.alpha_composite(canvas, overlay).convert("RGB")


async def build_slideshow_video(photos: list[bytes], manzil: str, narx: str) -> bytes | None:
    """1-rasm ustida 3 bosqichli "ochiluvchi" sarlavha (sarlavha -> manzil ->
    narx, har biri 1 soniya, jami 3 soniya), qolgan rasmlar 1 soniyadan
    (matnsiz) almashadigan, OVOZSIZ mp4 video yasaydi."""
    photos = photos[:MAX_PHOTOS]
    if not photos:
        return None

    async with _GEN_SEMAPHORE:
        try:
            with tempfile.TemporaryDirectory(prefix="slideshow_") as tmpdir:
                frame_paths = []

                try:
                    first = _fit_frame(photos[0])
                    for step in range(3):
                        frame = _draw_intro_frame(first, step, manzil, narx)
                        path = os.path.join(tmpdir, f"frame_intro_{step}.jpg")
                        frame.save(path, format="JPEG", quality=92)
                        frame_paths.append((path, INTRO_STEP_SECONDS))
                except Exception:
                    logger.exception("Slaydshov sarlavha kadrini tayyorlashda xatolik")

                for i, raw in enumerate(photos[1:], start=1):
                    try:
                        frame = _fit_frame(raw)
                    except Exception:
                        logger.exception("Slaydshov kadrini tayyorlashda xatolik (%s-rasm)", i)
                        continue
                    path = os.path.join(tmpdir, f"frame_{i:02d}.jpg")
                    frame.save(path, format="JPEG", quality=92)
                    frame_paths.append((path, OTHER_FRAME_SECONDS))

                if not frame_paths:
                    return None

                concat_path = os.path.join(tmpdir, "concat.txt")
                with open(concat_path, "w", encoding="utf-8") as f:
                    for path, duration in frame_paths:
                        f.write(f"file '{path}'\nduration {duration}\n")
                    # ffmpeg concat demuxer'ning o'zига xos xususiyati: oxirgi
                    # faylning "duration"si e'tiborga olinmaydi, shuning uchun
                    # oxirgi kadr yana bir marta (duration'siz) takrorlanadi.
                    f.write(f"file '{frame_paths[-1][0]}'\n")

                output_path = os.path.join(tmpdir, "output.mp4")
                cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_path,
                    "-vf", "fps=30,format=yuv420p",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-an", "-movflags", "+faststart",
                    output_path,
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode != 0:
                    logger.error("ffmpeg slaydshov yasashda xatolik: %s", stderr.decode(errors="ignore")[-800:])
                    return None

                with open(output_path, "rb") as f:
                    return f.read()
        except FileNotFoundError:
            logger.error("ffmpeg serverda o'rnatilmagan - slaydshov video yasab bo'lmadi ('apt install ffmpeg' kerak)")
            return None
        except Exception:
            logger.exception("Slaydshov video yasashda kutilmagan xatolik")
            return None


def _hashtag(word: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zʻʼ']", "", word or "")
    return f"#{cleaned}" if cleaned else ""


def build_instagram_caption(manzil: str, narx: str, xona: str = "", kimlarga: str = "", qulaylik: str = "") -> str:
    """Shu e'lon uchun tayyor, professional darajadagi Instagram post matnini
    (hashtaglar bilan) yozadi - admin buni faqat NUSXA OLIB, Instagram'ga
    videoni joylaganda tavsif sifatida qo'yishi kerak."""
    first_word = (manzil or "").replace(",", " ").split()[0] if manzil and manzil.split() else ""
    loc_tag = _hashtag(first_word)

    details = []
    if xona:
        details.append(f"\U0001F6CF Xonalar soni: {xona}")
    if kimlarga:
        details.append(f"\U0001F465 Kimlarga: {kimlarga}")
    if qulaylik:
        details.append(f"✅ Sharoitlari: {qulaylik}")
    details_block = ("\n".join(details) + "\n\n") if details else ""

    hashtags = [
        "#ijaragauylar", "#toshkentijara", "#uyijara", "#kvartiraijara",
        "#arendauzb", "#tashkentrentals", "#kochmasmulk", "#maklersiz",
        "#uyarenda", "#ijarakvartira", "#toshkent", "#arenda",
    ]
    if loc_tag and loc_tag not in hashtags:
        hashtags.insert(2, loc_tag)

    return (
        f"\U0001F3E0 Ijaraga uy — {manzil}\n\n"
        f"\U0001F4CD Manzil: {manzil}\n"
        f"\U0001F4B0 Narxi: {narx}\n\n"
        f"{details_block}"
        f"☎️ Uy egasi raqami bizning Telegram botimizda — bio'dagi havola orqali o'ting va BEPUL ko'ring!\n\n"
        + " ".join(hashtags)
    )
