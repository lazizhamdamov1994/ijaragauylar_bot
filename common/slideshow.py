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
FIRST_FRAME_SECONDS = 3
OTHER_FRAME_SECONDS = 1
MAX_PHOTOS = 10

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


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


def _centered_text(draw, y, text, font, fill=(255, 255, 255, 255)):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (CANVAS_W - w) // 2
    for dx, dy in ((2, 2), (-2, -2), (2, -2), (-2, 2), (0, 2)):
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 200))
    draw.text((x, y), text, font=font, fill=fill)


def _draw_intro_overlay(canvas: Image.Image, manzil: str, narx: str) -> Image.Image:
    """Faqat BIRINCHI kadrga: yuqorida sarlavha+manzil+narx, pastda kanal
    haqida eslatma - har biri o'qish uchun qorong'i "panel" fonida."""
    canvas = canvas.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw.rectangle([(0, 0), (CANVAS_W, 360)], fill=(0, 0, 0, 165))
    draw.rectangle([(0, CANVAS_H - 140), (CANVAS_W, CANVAS_H)], fill=(0, 0, 0, 175))

    title_font = _load_font(76)
    sub_font = _load_font(54)
    bottom_font = _load_font(42)

    _centered_text(draw, 45, "BEZMAKLER UY", title_font, fill=(255, 255, 255, 255))
    _centered_text(draw, 155, (manzil or "")[:40], sub_font, fill=(255, 209, 102, 255))
    _centered_text(draw, 235, (narx or "")[:30], sub_font, fill=(255, 255, 255, 255))
    _centered_text(draw, CANVAS_H - 100, "Uy egasi raqami Telegram kanalimizda", bottom_font)

    return Image.alpha_composite(canvas, overlay).convert("RGB")


async def build_slideshow_video(photos: list[bytes], manzil: str, narx: str) -> bytes | None:
    """1-rasm 3 soniya (sarlavha/manzil/narx/kanal matni bilan), qolgan
    rasmlar 1 soniyadan (matnsiz) almashadigan, OVOZSIZ mp4 video yasaydi."""
    photos = photos[:MAX_PHOTOS]
    if not photos:
        return None

    try:
        with tempfile.TemporaryDirectory(prefix="slideshow_") as tmpdir:
            frame_paths = []
            for i, raw in enumerate(photos):
                try:
                    frame = _fit_frame(raw)
                    if i == 0:
                        frame = _draw_intro_overlay(frame, manzil, narx)
                except Exception:
                    logger.exception("Slaydshov kadrini tayyorlashda xatolik (%s-rasm)", i)
                    continue
                path = os.path.join(tmpdir, f"frame_{i:02d}.jpg")
                frame.save(path, format="JPEG", quality=92)
                frame_paths.append(path)

            if not frame_paths:
                return None

            concat_path = os.path.join(tmpdir, "concat.txt")
            with open(concat_path, "w", encoding="utf-8") as f:
                for i, path in enumerate(frame_paths):
                    duration = FIRST_FRAME_SECONDS if i == 0 else OTHER_FRAME_SECONDS
                    f.write(f"file '{path}'\nduration {duration}\n")
                # ffmpeg concat demuxer'ning o'zига xos xususiyati: oxirgi
                # faylning "duration"si e'tiborga olinmaydi, shuning uchun
                # oxirgi kadr yana bir marta (duration'siz) takrorlanadi.
                f.write(f"file '{frame_paths[-1]}'\n")

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
