"""Admin: yangi e'lon yaratish ustasi (bosqichma-bosqich) va kanalga joylash."""
from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import constants as C
from ..db import Database
from ..geo import resolve_location
from ..keyboards import admin_menu, channel_kb, channel_post_url
from ..media import process_listing_media, remove_listing_dir
from ..middlewares import IsAdmin
from ..notifier import notify_new_listing
from ..posting import publish_listing, send_gallery, send_post
from ..states import NewListing
from ..texts import code

log = logging.getLogger(__name__)
router = Router(name="admin_new")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@dataclass(frozen=True)
class Step:
    key: str
    label: str              # tahrirlash menyusidagi nom
    prompt: str
    kind: str = "text"      # text | int | float | price | choice
    choices: tuple = field(default_factory=tuple)  # ((qiymat, yorliq), ...)
    cols: int = 2
    skippable: bool = False
    free_text: bool = True  # tugmalar bo'lsa ham, o'zi yozishi mumkinmi


def _same(*labels: str) -> tuple:
    return tuple((x, x) for x in labels)


STEPS: list[Step] = [
    Step("deal", "Bitim turi", "Bitim turini tanlang:", "choice", tuple(C.DEALS), free_text=False),
    Step("ptype", "Uy turi", "Uy turini tanlang:", "choice", tuple(C.PTYPES), free_text=False),
    Step("district", "Tuman", "Tumanni tanlang:", "choice",
         tuple((s, n) for s, n, _ in C.DISTRICTS), cols=3, free_text=False),
    Step("address", "Manzil", "📍 Manzil / turar joy majmuasi nomi:\n<i>Masalan: Shinam Uylar</i>",
         skippable=True),
    Step("floor", "Qavat", "🏢 Qavat:\n<i>Masalan: 3/9 yoki 1/8/9</i>"),
    Step("rooms", "Xonalar", "🏠 Xonalar soni:", "int",
         tuple((str(i), str(i)) for i in range(1, 7)), cols=6),
    Step("area", "Maydon", "📐 Umumiy maydoni (m²):\n<i>Masalan: 31 yoki 54,5</i>", "float"),
    Step("balcony", "Balkon", "🌿 Balkon o‘lchami:\n<i>Masalan: 1,5 × 3</i>", skippable=True),
    Step("bathroom", "Sanuzel", "🚿 Sanuzel:", "choice",
         _same("Birgalikda", "Alohida", "2 ta sanuzel"), skippable=True),
    Step("renovation", "Remont", "✨ Ta’mir holati:", "choice",
         _same("Yevro remont", "Ta’mirlangan", "O‘rtacha ta’mir", "Ta’mir talab", "Qora suvoq (korobka)"),
         skippable=True),
    Step("furniture", "Mebel", "🛋 Mebel:", "choice",
         _same("Mebel va texnikalar qoladi", "Mebel qoladi", "Mebelsiz"), cols=1, skippable=True),
    Step("landmark", "Mo‘ljal", "📍 Mo‘ljal:\n<i>Masalan: Mashina bozori — 400 metr</i>", skippable=True),
    Step("extra", "Qo‘shimcha", "📝 Qo‘shimcha ma’lumot (har qatori alohida chiqadi):\n"
         "<i>Masalan: 🚗 Uy katta yo‘l bo‘yida joylashgan</i>", skippable=True),
    Step("price", "Narx", "💰 Narxi ($):\n<i>Masalan: 46000, 46.000 yoki 46 ming</i>", "price"),
]
KEYS = [s.key for s in STEPS]
BY_KEY = {s.key: s for s in STEPS}

_media_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_media_ack: dict[int, asyncio.Task] = {}


# ---------------- yordamchi funksiyalar ----------------
def parse_price(text: str) -> int | None:
    t = text.lower().replace(" ", "").replace("$", "").replace("у.е", "")
    mult = 1
    if t.endswith("k") or "ming" in t:
        mult = 1000
        t = t.replace("ming", "").rstrip("k")
        t = t.replace(",", ".")
        try:
            return int(float(t) * mult)
        except ValueError:
            return None
    digits = re.sub(r"[^\d]", "", t)
    return int(digits) if digits else None


def parse_value(step: Step, text: str):
    t = text.strip()
    if step.kind == "int":
        digits = re.sub(r"\D", "", t)
        n = int(digits) if digits else 0
        return n if 1 <= n <= 50 else None
    if step.kind == "float":
        m = re.search(r"\d+(?:[.,]\d+)?", t)
        return float(m.group(0).replace(",", ".")) if m else None
    if step.kind == "price":
        n = parse_price(t)
        return n if n and n > 0 else None
    return t[:500] if t else None


def step_kb(step: Step, editing: bool):
    b = InlineKeyboardBuilder()
    for i, (_, label) in enumerate(step.choices):
        b.button(text=label, callback_data=f"nl:c:{i}")
    b.adjust(step.cols)
    if step.skippable:
        b.row(_btn("⏭ O‘tkazib yuborish", "nl:skip"))
    if editing:
        b.row(_btn("🔙 Ko‘rinishga qaytish", "nl:preview"))
    b.row(_btn(C.BTN_CANCEL, "nl:cancel"))
    return b.as_markup()


def _btn(text: str, data: str):
    from aiogram.types import InlineKeyboardButton
    return InlineKeyboardButton(text=text, callback_data=data)


def _display(step: Step, value) -> str:
    for v, label in step.choices:
        if str(v) == str(value):
            return label
    return str(value)


async def ask(message: Message, state: FSMContext, key: str) -> None:
    step = BY_KEY[key]
    data = await state.get_data()
    editing = data.get("editing", False)
    await state.set_state(NewListing.field)
    await state.update_data(cur=key)
    head = "✏️ Tahrirlash" if editing else f"<b>{KEYS.index(key) + 1}/{len(KEYS)}</b>"
    text = f"{head} · {step.prompt}"
    if editing and data.get(key) not in (None, ""):
        text += f"\n\nHozirgi qiymat: <b>{_display(step, data[key])}</b>"
    await message.answer(text, reply_markup=step_kb(step, editing))


async def advance(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    data = await state.get_data()
    if data.get("editing"):
        return await show_preview(message, state, bot, db)
    idx = KEYS.index(data["cur"])
    if idx + 1 < len(KEYS):
        return await ask(message, state, KEYS[idx + 1])
    await ask_media(message, state)


async def ask_media(message: Message, state: FSMContext) -> None:
    await state.set_state(NewListing.media)
    await state.update_data(media=[])
    b = InlineKeyboardBuilder()
    b.row(_btn("✅ Tayyor", "nl:media_done"), _btn("⏭ Rasmsiz", "nl:media_done"))
    b.row(_btn(C.BTN_CANCEL, "nl:cancel"))
    await message.answer(
        "📸 Rasm va videolarni yuboring (10 tagacha, albom qilib ham bo‘ladi).\n"
        "Birinchi fayl postning asosiy rasmi bo‘ladi.\n\n"
        "Tugatgach <b>✅ Tayyor</b> ni bosing.",
        reply_markup=b.as_markup(),
    )


async def ask_location(message: Message, state: FSMContext) -> None:
    await state.set_state(NewListing.location)
    b = InlineKeyboardBuilder()
    b.row(_btn("⏭ Lokatsiyasiz", "nl:loc_skip"))
    b.row(_btn(C.BTN_CANCEL, "nl:cancel"))
    await message.answer(
        "📍 Uy joylashuvini yuboring:\n"
        "• 📎 → <b>Joylashuv (Location)</b> orqali xaritadan nuqta tanlang, yoki\n"
        "• Google Maps / Yandex xarita havolasini tashlang, yoki\n"
        "• koordinata yozing: <code>41.2856, 69.2034</code>\n\n"
        "<i>Lokatsiya saytdagi xaritada uyni ko‘rsatish uchun kerak.</i>",
        reply_markup=b.as_markup(),
    )


def listing_fields_from(data: dict, admin_id: int) -> dict:
    f = {k: data.get(k) for k in KEYS}
    f.update(lat=data.get("lat"), lng=data.get("lng"), created_by=admin_id)
    return f


async def show_preview(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    data = await state.get_data()
    admin_id = message.chat.id
    fields = listing_fields_from(data, admin_id)
    listing_id = data.get("listing_id")
    if listing_id:
        await db.update_listing(listing_id, **fields)
    else:
        listing_id = await db.create_listing({**fields, "status": "draft"})
        await state.update_data(listing_id=listing_id)

    if not data.get("media_saved"):
        await db.delete_media(listing_id)
        remove_listing_dir(listing_id)
        for pos, m in enumerate(data.get("media", [])):
            await db.add_media(listing_id, m["kind"], m["file_id"], pos)
        if data.get("media"):
            wait = await message.answer("⏳ Rasmlar tayyorlanmoqda (suv belgisi qo‘yilmoqda)...")
            await process_listing_media(bot, db, listing_id)
            await wait.delete()
        await state.update_data(media_saved=True, gallery_shown=False)
        data = await state.get_data()

    listing = await db.get_listing(listing_id)
    media = await db.get_media(listing_id)
    if len(media) > 1 and not data.get("gallery_shown"):
        await message.answer("📸 Barcha fayllar:")
        await send_gallery(bot, db, admin_id, media)
        await state.update_data(gallery_shown=True)
        media = await db.get_media(listing_id)

    await message.answer("👇 Post kanalda shunday ko‘rinadi:")
    listing["status"] = "active"
    await send_post(bot, db, admin_id, listing, media, channel_kb(listing, len(media)))

    loc = "✅ bor" if listing.get("lat") is not None else "❌ yo‘q"
    b = InlineKeyboardBuilder()
    b.row(_btn("✅ Kanalga joylash", "nl:publish"))
    b.row(_btn("✏️ Tahrirlash", "nl:edit"), _btn(C.BTN_CANCEL, "nl:cancel"))
    await state.set_state(NewListing.preview)
    await state.update_data(editing=False)
    await message.answer(
        f"🆔 #{code(listing_id)} · Lokatsiya: {loc} · Fayllar: {len(media)} ta\n\nHammasi to‘g‘rimi?",
        reply_markup=b.as_markup(),
    )


# ---------------- boshlash ----------------
@router.message(F.text == C.BTN_NEW)
@router.message(Command("new"))
async def start_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("➕ <b>Yangi e’lon</b>. Savollarga javob bering — bot postni o‘zi yig‘adi.")
    await ask(message, state, KEYS[0])


# ---------------- maydonlar ----------------
@router.callback_query(NewListing.field, F.data.startswith("nl:c:"))
async def on_choice(cb: CallbackQuery, state: FSMContext, bot: Bot, db: Database) -> None:
    data = await state.get_data()
    step = BY_KEY[data["cur"]]
    idx = int(cb.data.split(":")[2])
    if idx >= len(step.choices):
        return await cb.answer()
    value, label = step.choices[idx]
    if step.kind == "int":
        value = int(value)
    await state.update_data({step.key: value})
    await cb.answer(label)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(f"✔️ {step.label}: <b>{label}</b>")
    await advance(cb.message, state, bot, db)


@router.callback_query(NewListing.field, F.data == "nl:skip")
async def on_skip(cb: CallbackQuery, state: FSMContext, bot: Bot, db: Database) -> None:
    data = await state.get_data()
    await state.update_data({data["cur"]: None})
    await cb.answer("O‘tkazib yuborildi")
    await cb.message.edit_reply_markup(reply_markup=None)
    await advance(cb.message, state, bot, db)


@router.message(NewListing.field, F.text, ~F.text.in_(C.MENU_TEXTS))
async def on_text(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    data = await state.get_data()
    step = BY_KEY[data["cur"]]
    if step.choices and not step.free_text:
        return await message.answer("Iltimos, yuqoridagi tugmalardan birini tanlang 👆")
    value = parse_value(step, message.text)
    if value is None:
        return await message.answer("⚠️ Qiymat noto‘g‘ri. Qaytadan kiriting.\n\n" + step.prompt)
    await state.update_data({step.key: value})
    await advance(message, state, bot, db)


# ---------------- media ----------------
@router.message(NewListing.media, F.photo | F.video)
async def on_media(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    async with _media_locks[uid]:  # albom bir vaqtda keladi — ma'lumot yo'qolmasligi uchun
        data = await state.get_data()
        media = list(data.get("media", []))
        if len(media) >= 10:
            return await message.answer("⚠️ Ko‘pi bilan 10 ta fayl. ✅ Tayyor ni bosing.")
        if message.photo:
            media.append({"kind": "photo", "file_id": message.photo[-1].file_id})
        else:
            media.append({"kind": "video", "file_id": message.video.file_id})
        await state.update_data(media=media)

    old = _media_ack.get(uid)
    if old and not old.done():
        old.cancel()

    async def ack():
        await asyncio.sleep(1.5)
        count = len((await state.get_data()).get("media", []))
        b = InlineKeyboardBuilder()
        b.row(_btn("✅ Tayyor", "nl:media_done"))
        await message.answer(f"📥 Qabul qilindi: <b>{count}</b> ta fayl. Yana yuborishingiz mumkin.",
                             reply_markup=b.as_markup())

    _media_ack[uid] = asyncio.create_task(ack())


@router.message(NewListing.media, F.document)
async def on_document(message: Message) -> None:
    await message.answer("⚠️ Faylni <b>rasm/video sifatida</b> yuboring (siqilgan holda), hujjat sifatida emas.")


@router.callback_query(NewListing.media, F.data == "nl:media_done")
async def on_media_done(cb: CallbackQuery, state: FSMContext, bot: Bot, db: Database) -> None:
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await state.update_data(media_saved=False)
    data = await state.get_data()
    if data.get("editing"):
        return await show_preview(cb.message, state, bot, db)
    await ask_location(cb.message, state)


# ---------------- lokatsiya ----------------
@router.message(NewListing.location, F.location)
async def on_location(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    await state.update_data(lat=message.location.latitude, lng=message.location.longitude)
    await message.answer("✅ Lokatsiya saqlandi.")
    await show_preview(message, state, bot, db)


@router.message(NewListing.location, F.text, ~F.text.in_(C.MENU_TEXTS))
async def on_location_text(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    coords = await resolve_location(message.text)
    if not coords:
        return await message.answer(
            "⚠️ Havoladan koordinatani aniqlay olmadim. 📎 → Joylashuv orqali yuboring "
            "yoki <code>41.2856, 69.2034</code> ko‘rinishida yozing.")
    await state.update_data(lat=coords[0], lng=coords[1])
    await message.answer(f"✅ Lokatsiya saqlandi: <code>{coords[0]:.6f}, {coords[1]:.6f}</code>")
    await show_preview(message, state, bot, db)


@router.callback_query(NewListing.location, F.data == "nl:loc_skip")
async def on_location_skip(cb: CallbackQuery, state: FSMContext, bot: Bot, db: Database) -> None:
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await show_preview(cb.message, state, bot, db)


# ---------------- tahrirlash ----------------
@router.callback_query(NewListing.preview, F.data == "nl:edit")
async def on_edit(cb: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    for s in STEPS:
        b.button(text=s.label, callback_data=f"nl:ef:{s.key}")
    b.button(text="📸 Rasmlar", callback_data="nl:ef:media")
    b.button(text="📍 Lokatsiya", callback_data="nl:ef:location")
    b.adjust(3)
    b.row(_btn("🔙 Orqaga", "nl:preview"))
    await cb.answer()
    await cb.message.edit_text("✏️ Qaysi maydonni o‘zgartiramiz?", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("nl:ef:"))
async def on_edit_field(cb: CallbackQuery, state: FSMContext) -> None:
    key = cb.data.split(":", 2)[2]
    data = await state.get_data()
    if not data.get("listing_id"):
        return await cb.answer("Sessiya eskirgan. ➕ Yangi e’lon dan boshlang.", show_alert=True)
    await state.update_data(editing=True)
    await cb.answer()
    await cb.message.delete()
    if key == "media":
        await ask_media(cb.message, state)
    elif key == "location":
        await ask_location(cb.message, state)
    elif key in BY_KEY:
        await ask(cb.message, state, key)


@router.callback_query(F.data == "nl:preview")
async def on_back_preview(cb: CallbackQuery, state: FSMContext, bot: Bot, db: Database) -> None:
    if not (await state.get_data()).get("listing_id"):
        return await cb.answer("Sessiya eskirgan.", show_alert=True)
    await cb.answer()
    await cb.message.delete()
    await show_preview(cb.message, state, bot, db)


# ---------------- bekor qilish / joylash ----------------
@router.callback_query(F.data == "nl:cancel")
async def on_cancel(cb: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lid = data.get("listing_id")
    if lid:
        listing = await db.get_listing(lid)
        if listing and listing["status"] == "draft":
            await db.delete_listing(lid)
            remove_listing_dir(lid)
    await state.clear()
    await cb.answer("Bekor qilindi")
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer("❌ E’lon bekor qilindi.", reply_markup=admin_menu())


@router.callback_query(NewListing.preview, F.data == "nl:publish")
async def on_publish(cb: CallbackQuery, state: FSMContext, bot: Bot, db: Database) -> None:
    data = await state.get_data()
    lid = data.get("listing_id")
    await state.set_state(None)  # ikki marta bosilmasligi uchun
    await cb.answer("Joylanmoqda...")
    try:
        listing = await publish_listing(bot, db, lid)
    except Exception as e:
        log.exception("Kanalga joylashda xato")
        await state.set_state(NewListing.preview)
        return await cb.message.answer(
            f"⚠️ Kanalga joylab bo‘lmadi:\n<code>{e}</code>\n\n"
            "Bot kanalga <b>admin</b> qilib qo‘shilganini va .env dagi CHANNEL_ID to‘g‘riligini tekshiring.")
    await state.clear()
    await cb.message.edit_reply_markup(reply_markup=None)
    url = channel_post_url(listing)
    await cb.message.answer(
        f"✅ #{code(lid)} kanalga joylandi!" + (f"\n🔗 {url}" if url else ""),
        reply_markup=admin_menu(),
    )
    asyncio.create_task(notify_new_listing(bot, db, lid, report_to=cb.from_user.id))
