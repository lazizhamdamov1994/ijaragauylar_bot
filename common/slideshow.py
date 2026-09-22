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
INTRO_SECONDS = 3.0  # sarlavha+manzil+narx - HAMMASI BIRDAN, video boshidanoq
OTHER_FRAME_SECONDS = 1.7
MAX_PHOTOS = 10

# ===== Harakat (Ken Burns zoom) + kadrlar orasidagi yumshoq o'tish =====
# Oddiy statik-rasm slaydshov o'rniga - haqiqiy Instagram Reels'dagi kabi
# HAR BIR kadr sekin zumlanadi (navbat bilan ichkariga/tashqariga - bir xil
# effekt takrorlanavermasligi uchun), kadrlar orasida esa qattiq kesish
# emas, yumshoq eritib o'tish (crossfade) ishlatiladi. Bu ffmpeg'ning o'zida
# (GPU/AI shart emas) bajariladi - kichik VPS'da ham ishlaydi, faqat video
# yasash biroz ko'proq vaqt oladi (_GEN_SEMAPHORE bitta video bilan cheklab,
# resursni himoya qiladi).
FPS = 30
XFADE_SECONDS = 0.5
ZOOM_RANGE = 0.14  # masalan 1.0 -> 1.14 (yoki teskari) - sezilarli, lekin haddan oshmagan harakat
PRESCALE = 1.5  # zoompan silliq ishlashi uchun manba kadrni oldindan kattalashtirish

BRAND_ACCENT = (255, 59, 92)  # sayt bilan bir xil #FF3B5C

# MUHIM (dizayn sifati + REAL XATO TUZATILDI): avval generik tizim shrifti
# (DejaVu Sans Bold) ishlatilardi - "qo'pol/havaskor" ko'rinishning asosiy
# sabablaridan biri edi. Birinchi tuzatishda "Big Shoulders Bold" (faqat
# lotin harflarini qo'llaydigan Google Font) qo'yilgan edi - lekin bu
# HAQIQIY ishlab chiqarishda sinovdan o'tkazilganda, o'zbek foydalanuvchilar
# manzil/matnni KIRILL alifbosida yozganda, kirill harflari umuman
# ko'rsatilmasligi (bo'sh to'rtburchaklar) aniqlandi - shrift kirillni
# qo'llab-quvvatlamasa. Shuning uchun "Montserrat ExtraBold" (Google Fonts,
# SIL Open Font License - fonts/Montserrat-OFL.txt, wght=800 statik
# nusxasi) ga almashtirildi - lotin (o'zbekcha ʻ/ʼ belgilari bilan) VA
# kirill alifbosini IKKALASINI HAM to'liq qo'llaydi, TEKSHIRILGAN (fontTools
# cmap tahlili orqali). Tizim shriftlari FAQAT shu fayl serverda
# topilmasa ishlatiladigan zaxira (ular ham kirillni qo'llab-quvvatlaydi).
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONT_CANDIDATES = (
    os.path.join(_BASE_DIR, "fonts", "Montserrat-ExtraBold.ttf"),
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


def _draw_spaced_text(draw, cx: int, y: int, text: str, font, fill, tracking: int = 6, shadow=True):
    """Harflar orasiga qo'shimcha bo'shliq (tracking) qo'yib, markazlashtirib
    chizadi - katta sarlavhalarni "premium" ko'rinishga keltiradi. Karta endi
    QATTIQ (opaque) fonga ega bo'lgani uchun og'ir ko'p yo'nalishli soya
    SHART emas - bitta yumshoq soya yetarli va toza chiqadi."""
    widths = [draw.textbbox((0, 0), ch, font=font)[2] for ch in text]
    total_w = sum(widths) + tracking * (len(text) - 1)
    x = cx - total_w // 2
    for ch, w in zip(text, widths):
        if shadow:
            draw.text((x + 2, y + 3), ch, font=font, fill=(0, 0, 0, 110))
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking


def _centered_text(draw, y, text, font, fill=(255, 255, 255, 255), shadow=False):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (CANVAS_W - w) // 2
    if shadow:
        draw.text((x + 2, y + 3), text, font=font, fill=(0, 0, 0, 110))
    draw.text((x, y), text, font=font, fill=fill)
    return w


def _shrink_font_to_fit(draw, text: str, base_size: int, max_width: int, min_size: int = 26, extra_width: int = 0):
    """Matn shriftini (kerak bo'lsa) max_width'ga sig'guncha kamaytiradi -
    uzun manzillar branded karta chegarasidan tashqariga chiqib ketmasligi
    uchun (avval qattiq belgi-soni bo'yicha kesish ishlatilgan edi - bu
    uzun so'zli manzillarda hali ham matn kartadan oshib ketishiga olib
    kelardi). Eng kichik o'lchamda ham sig'masa, "..." bilan qisqartiradi."""
    size = base_size
    while size >= min_size:
        font = _load_font(size)
        w = draw.textbbox((0, 0), text, font=font)[2] + extra_width
        if w <= max_width:
            return font, text
        size -= 2
    font = _load_font(min_size)
    trimmed = text
    while trimmed and draw.textbbox((0, 0), trimmed + "...", font=font)[2] + extra_width > max_width:
        trimmed = trimmed[:-1]
    return font, (trimmed.rstrip() + "..." if trimmed else text[:1])



# ===== "Stiker" kartalar (BEZMAKLER uslubidagi shablon) =====
# Laziz yuborgan namuna post (pushti "BEZMAKLER" + ko'k manzil/narx +
# yashil "Uy egasi raqami" kartalari, rasm ustiga suzuvchi) asosida
# qurilgan: HAR BIR karta QATTIQ (to'liq xira bo'lmagan) rangli fonga ega
# yumaloq burchakli "stiker" - ostidagi rasm nima bo'lishidan qat'iy
# nazar, kontrast har doim bir xil va professional ko'rinadi. Uchchala
# karta ham HAMMASI BIRDAN, video boshidanoq ko'rinadi (ketma-ket
# "ochilish" yo'q - zamonaviy Reels formatiga mos).
STICKER_PINK = BRAND_ACCENT       # sarlavha ("MAKLERSIZ UY")
STICKER_BLUE = (33, 118, 255)     # manzil + xona/narx
STICKER_GREEN = (22, 163, 74)     # CTA ("Uy egasi raqami...")

STICKER_MARGIN_X = 64
STICKER_X0, STICKER_X1 = STICKER_MARGIN_X, CANVAS_W - STICKER_MARGIN_X
STICKER_RADIUS = 30

TITLE_BOX_TOP = 380
TITLE_BOX_H = 132
TITLE_BOX_BOTTOM = TITLE_BOX_TOP + TITLE_BOX_H

INFO_BOX_TOP = TITLE_BOX_BOTTOM + 26
INFO_BOX_H = 236
INFO_BOX_BOTTOM = INFO_BOX_TOP + INFO_BOX_H

# Pastki CTA stikeri - Instagram'ning o'z pastki UI'si (izoh, like/share
# ikonalari) odatda eng pastki ~220px'ni yopib qo'yadi, shuning uchun
# stiker ANIQ shu chegaradan yuqorida, "xavfsiz zona"da joylashadi
# (haqiqiy sinov videosida tekshirilgan/tasdiqlangan chegaralar).
CTA_BANNER_TOP, CTA_BANNER_BOTTOM = 1560, 1750
CTA_LINE1 = "UY EGASI RAQAMI"
CTA_LINE2 = "TELEGRAM KANALIMIZDA"


def _draw_sticker_box(overlay: Image.Image, x0: int, y0: int, x1: int, y1: int, fill: tuple, radius: int = STICKER_RADIUS) -> None:
    """Qattiq rangli, yumaloq burchakli "stiker" karta - ortida yumshoq
    soya (rasm ustida suzayotgandek chuqurlik hissi) VA yuqori qismida
    yupqa yorqinroq "sheen" chizig'i bilan - bu tekis rangni yengil
    yaltiroq/dizayn qilingan sirt ko'rinishiga keltiradi (reklama
    shablonlarida keng qo'llaniladigan, arzon-lekin-samarali usul)."""
    draw = ImageDraw.Draw(overlay, "RGBA")
    draw.rounded_rectangle([x0 - 4, y0 + 8, x1 + 4, y1 + 14], radius=radius + 4, fill=(0, 0, 0, 70))
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=(*fill, 255))

    # MUHIM: sheen'ni TO'G'RIDAN-TO'G'RI shu overlay'ga (ImageDraw "RGBA"
    # rejimida ham) chizish - haqiqiy renderda tekshirilganda - kutilganidek
    # pushti/ko'k rang ustiga emas, TAGIDAGI FOTOSURATGA aralashib, kulrang/
    # loyqa chiqishi aniqlandi. Shuning uchun sheen ALOHIDA, o'zining sof
    # shaffof qatlamida chizilib, keyin Image.alpha_composite() orqali
    # ANIQ shu bosqichda (box tagida emas, ENDI opaque box ustida) qo'shiladi
    # - shu yo'l bilan yorqinroq rang HAQIQATAN HAM box rangi ustiga
    # aralashadi, fon rasmiga emas.
    sheen_color = tuple(min(255, c + 45) for c in fill)
    sheen_bottom = y0 + max(int((y1 - y0) * 0.24), radius)
    sheen_layer = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    ImageDraw.Draw(sheen_layer).rounded_rectangle(
        [x0 + 3, y0 + 3, x1 - 3, sheen_bottom], radius=max(radius - 3, 1), fill=(*sheen_color, 60),
    )
    overlay.alpha_composite(sheen_layer)


def _draw_phone_icon(overlay: Image.Image, cx: int, cy: int, badge_r: int, icon_color: tuple) -> None:
    """Telefon (smartfon) ikonkasini shrift/emoji'ga BUTUNLAY bog'liq
    bo'lmagan holda, sof PIL geometriyasi orqali chizadi (manzil
    qatoridagi rangli nuqta bilan bir xil sabab - ba'zi serverlarda emoji
    "quti" bo'lib chiqishi mumkin, bu esa HAR DOIM bir xil chiqadi).
    Klassik telefon dastasi shaklini geometrik primitivlardan yasashga
    urinish (chiziq+doiralar) amalda tanib bo'lmaydigan "suyak" shaklga
    aylanib qoldi (haqiqiy render orqali topilgan xato) - shuning uchun
    ANIQ, darhol tanib olinadigan shakl ishlatiladi: yumaloq burchakli
    "korpus" + ichida oq "ekran" to'rtburchagi - zamonaviy smartfon
    siluetiga o'xshaydi, kichik o'lchamda ham aniq o'qiladi."""
    draw = ImageDraw.Draw(overlay, "RGBA")
    draw.ellipse([cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r], fill=(255, 255, 255, 255))

    w, h = badge_r * 1.05, badge_r * 1.85
    x0, y0 = cx - w / 2, cy - h / 2 + badge_r * 0.06
    x1, y1 = x0 + w, y0 + h
    draw.rounded_rectangle([x0, y0, x1, y1], radius=w * 0.24, fill=icon_color)
    pad_x, pad_top, pad_bot = w * 0.11, h * 0.13, h * 0.15
    draw.rounded_rectangle(
        [x0 + pad_x, y0 + pad_top, x1 - pad_x, y1 - pad_bot], radius=w * 0.10, fill=(255, 255, 255, 255),
    )
    cam_r = w * 0.06
    draw.ellipse([cx - cam_r, y0 + h * 0.06, cx + cam_r, y0 + h * 0.06 + cam_r * 2], fill=(255, 255, 255, 255))


def _draw_cta_banner(canvas: Image.Image) -> Image.Image:
    """Yashil CTA stikeri - HAR BIR kadrga (birinchi rasmning sarlavha
    stikerlaridan tortib, oxirgi rasmgacha) qo'yiladi - shuning uchun
    tomoshabin "Telegram kanalimizda" degan xabarni FAQAT 1 soniya ko'rib
    qolib ketmaydi, balki VIDEO OXIRIGACHA (bir necha soniya davomida)
    doimiy ko'rib boradi - Instagram reels'larda odam oqimini haydashning
    asosiy omili shu."""
    canvas = canvas.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    _draw_sticker_box(overlay, STICKER_X0, CTA_BANNER_TOP, STICKER_X1, CTA_BANNER_BOTTOM, STICKER_GREEN)

    icon_cy = (CTA_BANNER_TOP + CTA_BANNER_BOTTOM) // 2
    _draw_phone_icon(overlay, STICKER_X0 + 76, icon_cy, badge_r=34, icon_color=(*STICKER_GREEN, 255))

    draw = ImageDraw.Draw(overlay, "RGBA")
    line1_font = _load_font(48)
    line2_font = _load_font(40)
    _centered_text(draw, CTA_BANNER_TOP + 30, CTA_LINE1, line1_font, fill=(255, 255, 255, 255))
    _centered_text(draw, CTA_BANNER_TOP + 98, CTA_LINE2, line2_font, fill=(255, 255, 255, 255))

    return Image.alpha_composite(canvas, overlay).convert("RGB")


def _draw_intro_frame(canvas: Image.Image, manzil: str, narx: str, xona: str = "") -> Image.Image:
    """Ikkita sarlavha stikeri (pushti "MAKLERSIZ UY" + ko'k manzil/xona/
    narx) - HAMMASI BIRDAN, video boshidanoq ko'rinadi (avvalgi versiyada
    bu ketma-ket "ochilib" chiqardi - Instagram Reels formatiga mos emas
    edi). Pastki yashil CTA stikeri ALOHIDA (_draw_cta_banner) - bu kadrga
    ham, qolgan barcha rasmlarga ham qo'shiladi (build_slideshow_video
    ichida)."""
    canvas = canvas.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    # ---- Pushti sarlavha stikeri ----
    _draw_sticker_box(overlay, STICKER_X0, TITLE_BOX_TOP, STICKER_X1, TITLE_BOX_BOTTOM, STICKER_PINK)
    title_font = _load_font(64)
    title_bbox = draw.textbbox((0, 0), "MAKLERSIZ UY", font=title_font)
    title_h = title_bbox[3] - title_bbox[1]
    title_y = TITLE_BOX_TOP + (TITLE_BOX_H - title_h) // 2 - title_bbox[1]
    _draw_spaced_text(draw, CANVAS_W // 2, title_y, "MAKLERSIZ UY", title_font, fill=(255, 255, 255, 255), tracking=4, shadow=False)

    # ---- Ko'k manzil + xona/narx stikeri ----
    _draw_sticker_box(overlay, STICKER_X0, INFO_BOX_TOP, STICKER_X1, INFO_BOX_BOTTOM, STICKER_BLUE)
    box_inner_w = (STICKER_X1 - STICKER_X0) - 90

    addr_text = (manzil or "").strip()
    addr_font, addr_text = _shrink_font_to_fit(draw, addr_text, 50, box_inner_w, min_size=30)
    addr_bbox = draw.textbbox((0, 0), addr_text, font=addr_font)
    addr_h = addr_bbox[3] - addr_bbox[1]

    line2_parts = [p for p in [(xona or "").strip(), (narx or "").strip()] if p]
    line2_text = " · ".join(line2_parts) or "Narxi: kelishiladi"
    line2_font, line2_text = _shrink_font_to_fit(draw, line2_text, 58, box_inner_w, min_size=32)
    line2_bbox = draw.textbbox((0, 0), line2_text, font=line2_font)
    line2_h = line2_bbox[3] - line2_bbox[1]

    gap = 22
    block_h = addr_h + gap + line2_h
    addr_y = INFO_BOX_TOP + (INFO_BOX_H - block_h) // 2 - addr_bbox[1]
    line2_y = addr_y + addr_h + gap - (line2_bbox[1] - addr_bbox[1])
    _centered_text(draw, addr_y, addr_text, addr_font, fill=(255, 255, 255, 255))
    _centered_text(draw, line2_y, line2_text, line2_font, fill=(255, 255, 255, 255))

    return Image.alpha_composite(canvas, overlay).convert("RGB")


def _zoompan_filter(idx: int, duration: float, zoom_in: bool) -> str:
    """Bitta kadr uchun sekin "Ken Burns" zum filtri - toq/juft indeksларда
    yo'nalish almashtiriladi (ichkariga/tashqariga), shu orqali barcha
    kadrlar bir xil effektni takrorlamaydi. Manba avval PRESCALE marta
    kattalashtiriladi - aks holda zoompan kichik manbadan kesganda harakat
    "sakrab-sakrab" (jitter) chiqadi."""
    d_frames = max(int(round(duration * FPS)), 1)
    rate = ZOOM_RANGE / d_frames
    zmax = 1 + ZOOM_RANGE
    if zoom_in:
        z_expr = f"if(eq(on,0),1.0,min(zoom+{rate:.6f},{zmax:.4f}))"
    else:
        z_expr = f"if(eq(on,0),{zmax:.4f},max(zoom-{rate:.6f},1.0))"
    pw, ph = int(CANVAS_W * PRESCALE), int(CANVAS_H * PRESCALE)
    return (
        f"[{idx}:v]scale={pw}:{ph}:flags=lanczos,setsar=1,"
        f"zoompan=z='{z_expr}':d={d_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={CANVAS_W}x{CANVAS_H}:fps={FPS},"
        # MUHIM: "-loop 1 -i rasm.jpg" standart 25 fps bilan cheksiz "kadr"
        # beradi, zoompan esa HAR BIR kirish kadriga d ta chiqish kadri
        # qo'shadi - shu sabab trim BO'LMASA video kutilganidan O'NLAB
        # MARTA uzun chiqadi (haqiqiy videoda sinovdan o'tkazib topilgan
        # xato). trim orqali chiqish ANIQ d ta kadr bilan cheklanadi.
        f"trim=start_frame=0:end_frame={d_frames},setpts=PTS-STARTPTS,format=yuv420p[v{idx}]"
    )


def _build_video_filter_complex(frame_paths: list[tuple[str, float]]) -> tuple[str, str]:
    """Har bir kadrga Ken Burns zum filtrini qo'llaydi, keyin ularni
    ketma-ket yumshoq eritib o'tish (xfade) bilan bog'laydi. Statik
    rasmlar ketma-ketligi o'rniga haqiqiy, professional harakatli video
    hosil qiladi - HAMMASI ffmpeg'ning o'zida, tashqi AI/GPU xizmatisiz.
    (filter_complex_matni, oxirgi_oqim_nomi) qaytaradi."""
    filters = [_zoompan_filter(idx, dur, zoom_in=(idx % 2 == 0)) for idx, (_, dur) in enumerate(frame_paths)]
    n = len(frame_paths)
    if n == 1:
        return ";".join(filters), "v0"

    prev_label = "v0"
    cum = 0.0
    for j in range(1, n):
        cum += frame_paths[j - 1][1]
        offset = cum - j * XFADE_SECONDS
        out_label = f"vx{j}" if j < n - 1 else "vout"
        filters.append(f"[{prev_label}][v{j}]xfade=transition=fade:duration={XFADE_SECONDS}:offset={offset:.3f}[{out_label}]")
        prev_label = out_label
    return ";".join(filters), prev_label


async def build_slideshow_video(photos: list[bytes], manzil: str, narx: str, xona: str = "") -> bytes | None:
    """1-rasm ustida sarlavha+manzil+xona+narx BIRDANIGA (video boshidanoq)
    ko'rinadigan "stiker" kartalar, qolgan rasmlar - har biri sekin
    zumlanadigan (Ken Burns) va bir-biriga yumshoq eriydigan (crossfade)
    kadrlar - zamonaviy Instagram Reels formatiga mos, OVOZSIZ mp4 video
    yasaydi."""
    photos = photos[:MAX_PHOTOS]
    if not photos:
        return None

    async with _GEN_SEMAPHORE:
        try:
            with tempfile.TemporaryDirectory(prefix="slideshow_") as tmpdir:
                frame_paths: list[tuple[str, float]] = []

                try:
                    first = _fit_frame(photos[0])
                    frame = _draw_cta_banner(_draw_intro_frame(first, manzil, narx, xona))
                    path = os.path.join(tmpdir, "frame_intro.jpg")
                    frame.save(path, format="JPEG", quality=92)
                    frame_paths.append((path, INTRO_SECONDS))
                except Exception:
                    logger.exception("Slaydshov sarlavha kadrini tayyorlashda xatolik")

                for i, raw in enumerate(photos[1:], start=1):
                    try:
                        frame = _draw_cta_banner(_fit_frame(raw))
                    except Exception:
                        logger.exception("Slaydshov kadrini tayyorlashda xatolik (%s-rasm)", i)
                        continue
                    path = os.path.join(tmpdir, f"frame_{i:02d}.jpg")
                    frame.save(path, format="JPEG", quality=92)
                    frame_paths.append((path, OTHER_FRAME_SECONDS))

                if not frame_paths:
                    return None

                filter_complex, final_label = _build_video_filter_complex(frame_paths)

                output_path = os.path.join(tmpdir, "output.mp4")
                cmd = ["ffmpeg", "-y"]
                for path, duration in frame_paths:
                    cmd += ["-loop", "1", "-t", f"{duration}", "-i", path]
                cmd += [
                    "-filter_complex", filter_complex,
                    "-map", f"[{final_label}]",
                    "-r", str(FPS),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-an", "-movflags", "+faststart", "-pix_fmt", "yuv420p",
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
