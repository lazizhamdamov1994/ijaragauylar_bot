"""Mijoz tomoni: /start (deep-link), filtr sozlash, uy qidirish, saqlanganlar, lid, sotuvchi formasi."""
from __future__ import annotations

import re
from html import escape as h

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import constants as C
from ..config import settings
from ..db import Database
from ..keyboards import (
    admin_menu, channel_post_url, is_admin, phone_request_kb, realtor_url, user_menu,
)
from ..matching import describe_filter, filter_from_listing, listing_matches
from ..notifier import notify_admins
from ..posting import send_card, send_gallery
from ..states import FilterSetup, LeadPhone, SellerForm
from ..texts import code, short_title

router = Router(name="user")
PAGE = 5
PHONE_RE = re.compile(r"^\+?[\d\s\-()]{9,18}$")


def menu_for(user_id: int):
    return user_menu(is_admin=is_admin(user_id))


def contact_lines() -> str:
    lines = [f"👩‍💼 Rieltor: <b>{h(settings.realtor_name)}</b>"]
    if settings.realtor_phone:
        lines.append(f"📞 {h(settings.realtor_phone)}")
    if settings.realtor_username:
        lines.append(f"✈️ @{h(settings.realtor_username)}")
    return "\n".join(lines)


# =====================================================================
#  /start
# =====================================================================
@router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject, state: FSMContext, bot: Bot, db: Database,
    is_new_user: bool,
) -> None:
    await state.clear()
    uid = message.from_user.id
    payload = (command.args or "").strip()
    if payload:
        await db.set_source_if_empty(uid, payload)
        if await handle_payload(message, state, bot, db, uid, payload):
            if is_new_user and not await db.get_filter(uid):
                await offer_filter(message)
            return

    if is_admin(uid) and not payload:
        await message.answer(
            "Assalomu alaykum! Siz <b>admin</b>siz.\n"
            f"{C.BTN_NEW} — kanalga yangi e’lon joylash.", reply_markup=admin_menu())
        return

    await message.answer(
        f"Assalomu alaykum, <b>{h(message.from_user.first_name or '')}</b>! 👋\n\n"
        "<b>Nihola Estate</b> botiga xush kelibsiz.\n"
        "Bu yerda siz:\n"
        "🔎 o‘zingizga mos uylarni topasiz,\n"
        "🔔 mos uy chiqishi bilan birinchi bo‘lib xabar olasiz,\n"
        "❤️ yoqqan uylarni saqlab, narxi tushsa bilib turasiz.",
        reply_markup=menu_for(uid),
    )
    if not await db.get_filter(uid):
        await start_filter(message, state)


async def handle_payload(
    message: Message, state: FSMContext, bot: Bot, db: Database, uid: int, payload: str,
) -> bool:
    m = re.fullmatch(r"(call|save|sim|pics|l)_(\d+)", payload)
    if not m:
        return False
    action, lid = m.group(1), int(m.group(2))
    listing = await db.get_listing(lid)
    if not listing or listing["status"] == "draft":
        await message.answer("😔 Bu e’lon topilmadi.", reply_markup=menu_for(uid))
        return True
    await do_action(message, state, bot, db, uid, action, listing)
    return True


async def do_action(
    message: Message, state: FSMContext, bot: Bot, db: Database, uid: int, action: str, listing: dict,
) -> None:
    """Kanal tugmalari (deep-link) va bot ichidagi tugmalar uchun umumiy mantiq."""
    lid = listing["id"]
    if action in ("l", "card"):
        await db.add_lead(uid, lid, "view")
        await send_card(bot, db, uid, listing)
    elif action == "call":
        await db.add_lead(uid, lid, "call")
        await start_lead(message, state, bot, db, uid, listing)
    elif action == "save":
        await db.add_lead(uid, lid, "save")
        if listing["status"] == "sold":
            await message.answer("Bu uy allaqachon sotilgan 😔", reply_markup=menu_for(uid))
            return
        new = await db.add_favorite(uid, lid)
        await message.answer(
            ("❤️ <b>Saqlandi!</b>" if new else "❤️ Bu uy allaqachon saqlangan.")
            + f"\n{short_title(listing)}\n\n"
            "Narxi tushsa yoki sotilsa — darhol xabar beramiz.",
            reply_markup=menu_for(uid),
        )
    elif action == "sim":
        await db.add_lead(uid, lid, "similar")
        await show_similar_offer(message, db, listing)
    elif action == "pics":
        await db.add_lead(uid, lid, "pics")
        media = await db.get_media(lid)
        if media:
            await send_gallery(bot, db, uid, media)
        await send_card(bot, db, uid, listing)


# =====================================================================
#  Lid: "Bog'lanish"
# =====================================================================
async def start_lead(
    message: Message, state: FSMContext, bot: Bot, db: Database, uid: int, listing: dict | None,
) -> None:
    user = await db.get_user(uid)
    head = f"🏠 {short_title(listing)}\n\n" if listing else ""
    if user and user.get("phone"):
        await send_lead(bot, db, uid, listing)
        await message.answer(
            f"{head}✅ <b>So‘rovingiz qabul qilindi!</b> Rieltor tez orada "
            f"<b>{h(user['phone'])}</b> raqamiga qo‘ng‘iroq qiladi.\n\n{contact_lines()}",
            reply_markup=menu_for(uid))
        return
    await state.set_state(LeadPhone.waiting)
    await state.update_data(listing_id=listing["id"] if listing else None)
    await message.answer(
        f"{head}📱 Raqamingizni qoldiring — rieltor o‘zi qo‘ng‘iroq qiladi.\n"
        "Pastdagi <b>📱 Raqamni yuborish</b> tugmasini bosing yoki raqamni yozing.\n\n"
        f"Yoki o‘zingiz bog‘laning:\n{contact_lines()}",
        reply_markup=phone_request_kb(),
    )


async def send_lead(bot: Bot, db: Database, uid: int, listing: dict | None, note: str = "") -> None:
    user = await db.get_user(uid)
    uname = f" (@{h(user['username'])})" if user.get("username") else ""
    lines = [
        "🔥 <b>Yangi lid!</b>" + (f" — {note}" if note else ""),
        f"👤 <a href=\"tg://user?id={uid}\">{h(user.get('full_name') or 'Mijoz')}</a>{uname}",
        f"📱 {h(user['phone']) if user.get('phone') else 'raqam qoldirmadi'}",
    ]
    if listing:
        lines.append(f"🏠 {short_title(listing)}")
        url = channel_post_url(listing)
        if url:
            lines.append(f"🔗 {url}")
    f = await db.get_filter(uid)
    if f:
        lines += ["", "<b>Mijoz filtri:</b>", describe_filter(f)]
    await notify_admins(bot, "\n".join(lines))


@router.message(LeadPhone.waiting, F.contact)
@router.message(LeadPhone.waiting, F.text.regexp(PHONE_RE.pattern))
async def lead_phone(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    uid = message.from_user.id
    phone = message.contact.phone_number if message.contact else message.text.strip()
    if not phone.startswith("+") and phone.replace(" ", "").isdigit() and len(phone.replace(" ", "")) >= 12:
        phone = "+" + phone
    await db.set_user_field(uid, "phone", phone)
    data = await state.get_data()
    await state.clear()
    listing = await db.get_listing(data["listing_id"]) if data.get("listing_id") else None
    await send_lead(bot, db, uid, listing)
    await message.answer(
        "✅ <b>Rahmat!</b> Rieltor tez orada siz bilan bog‘lanadi.", reply_markup=menu_for(uid))


@router.message(LeadPhone.waiting, F.text == C.BTN_NO_PHONE)
async def lead_no_phone(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    uid = message.from_user.id
    data = await state.get_data()
    await state.clear()
    listing = await db.get_listing(data["listing_id"]) if data.get("listing_id") else None
    await send_lead(bot, db, uid, listing, note="raqamsiz")
    await message.answer(
        f"Mayli! Rieltorga Telegram orqali yozishingiz mumkin:\n\n{contact_lines()}",
        reply_markup=menu_for(uid))


# =====================================================================
#  Filtr ("Sizga mos uy chiqdi" xabarnomasi uchun)
# =====================================================================
async def offer_filter(message: Message) -> None:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔔 Ha, sozlash", callback_data="f:start"))
    await message.answer(
        "💡 Qanday uy qidiryapsiz? 30 soniyada filtr sozlang — "
        "mos uy joylanishi bilan sizga <b>birinchi bo‘lib</b> xabar beramiz.",
        reply_markup=b.as_markup())


async def start_filter(message: Message, state: FSMContext, edit: bool = False) -> None:
    await state.set_state(FilterSetup.active)
    await state.update_data(fd={"deal": None, "districts": [], "rooms": []})
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🏷 Sotib olish", callback_data="f:deal:sale"),
          InlineKeyboardButton(text="🔑 Ijaraga olish", callback_data="f:deal:rent"))
    b.row(InlineKeyboardButton(text="🤷 Ikkalasi ham", callback_data="f:deal:any"))
    text = "🔔 <b>Filtr sozlash</b> (1/4)\n\nUy sotib olmoqchimisiz yoki ijaraga?"
    if edit:
        await message.edit_text(text, reply_markup=b.as_markup())
    else:
        await message.answer(text, reply_markup=b.as_markup())


def _multi_kb(options: list[tuple[str, str]], selected: list[str], prefix: str, cols: int):
    b = InlineKeyboardBuilder()
    for val, label in options:
        mark = "✅ " if val in selected else ""
        b.button(text=mark + label, callback_data=f"f:{prefix}:{val}")
    b.adjust(cols)
    b.row(InlineKeyboardButton(text="🌐 Farqi yo‘q", callback_data=f"f:{prefix}:all"),
          InlineKeyboardButton(text="➡️ Davom etish", callback_data=f"f:{prefix}:done"))
    return b.as_markup()


DISTRICT_OPTS = [(s, n) for s, n, _ in C.DISTRICTS]


async def _fd(cb: CallbackQuery, state: FSMContext) -> dict | None:
    fd = (await state.get_data()).get("fd")
    if fd is None:
        await cb.answer("Sessiya eskirdi, qaytadan boshlaymiz")
        await start_filter(cb.message, state, edit=True)
    return fd


@router.callback_query(F.data == "f:start")
async def f_start(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await start_filter(cb.message, state, edit=True)


@router.callback_query(F.data.startswith("f:deal:"))
async def f_deal(cb: CallbackQuery, state: FSMContext) -> None:
    fd = await _fd(cb, state)
    if fd is None:
        return
    val = cb.data.split(":")[2]
    fd["deal"] = None if val == "any" else val
    await state.update_data(fd=fd)
    await cb.answer()
    await cb.message.edit_text(
        "🔔 <b>Filtr sozlash</b> (2/4)\n\n📍 Qaysi tumanlar? (bir nechtasini tanlash mumkin)",
        reply_markup=_multi_kb(DISTRICT_OPTS, fd["districts"], "d", 3))


@router.callback_query(F.data.startswith("f:d:"))
async def f_district(cb: CallbackQuery, state: FSMContext) -> None:
    fd = await _fd(cb, state)
    if fd is None:
        return
    val = cb.data.split(":")[2]
    if val in ("all", "done"):
        if val == "all":
            fd["districts"] = []
        await state.update_data(fd=fd)
        await cb.answer()
        await cb.message.edit_text(
            "🔔 <b>Filtr sozlash</b> (3/4)\n\n🏠 Necha xonali?",
            reply_markup=_multi_kb(C.ROOM_OPTIONS, fd["rooms"], "r", 4))
        return
    fd["districts"].remove(val) if val in fd["districts"] else fd["districts"].append(val)
    await state.update_data(fd=fd)
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=_multi_kb(DISTRICT_OPTS, fd["districts"], "d", 3))


@router.callback_query(F.data.startswith("f:r:"))
async def f_rooms(cb: CallbackQuery, state: FSMContext, db: Database) -> None:
    fd = await _fd(cb, state)
    if fd is None:
        return
    val = cb.data.split(":")[2]
    if val in ("all", "done"):
        if val == "all":
            fd["rooms"] = []
        await state.update_data(fd=fd)
        await cb.answer()
        if fd["deal"] is None:  # sotuv va ijara narxlari har xil — byudjetni so'ramaymiz
            fd["pmin"] = fd["pmax"] = None
            await state.update_data(fd=fd)
            return await ask_mode(cb, state)
        budgets = C.RENT_BUDGETS if fd["deal"] == "rent" else C.SALE_BUDGETS
        b = InlineKeyboardBuilder()
        for i, (label, _, _) in enumerate(budgets):
            b.button(text=label, callback_data=f"f:b:{i}")
        b.adjust(2)
        b.row(InlineKeyboardButton(text="🌐 Farqi yo‘q", callback_data="f:b:any"))
        await cb.message.edit_text("🔔 <b>Filtr sozlash</b> (4/4)\n\n💰 Byudjetingiz?",
                                   reply_markup=b.as_markup())
        return
    fd["rooms"].remove(val) if val in fd["rooms"] else fd["rooms"].append(val)
    await state.update_data(fd=fd)
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=_multi_kb(C.ROOM_OPTIONS, fd["rooms"], "r", 4))


@router.callback_query(F.data.startswith("f:b:"))
async def f_budget(cb: CallbackQuery, state: FSMContext) -> None:
    fd = await _fd(cb, state)
    if fd is None:
        return
    val = cb.data.split(":")[2]
    budgets = C.RENT_BUDGETS if fd["deal"] == "rent" else C.SALE_BUDGETS
    if val == "any":
        fd["pmin"] = fd["pmax"] = None
    else:
        _, fd["pmin"], fd["pmax"] = budgets[int(val)]
    await state.update_data(fd=fd)
    await cb.answer()
    await ask_mode(cb, state)


async def ask_mode(cb: CallbackQuery, state: FSMContext) -> None:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⚡ Darhol (har yangi uyda)", callback_data="f:n:instant"))
    b.row(InlineKeyboardButton(text="🗓 Kuniga 1 marta (kechqurun)", callback_data="f:n:daily"))
    await cb.message.edit_text("🔔 Mos uy chiqqanda qanday xabar beraylik?", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("f:n:"))
async def f_mode(cb: CallbackQuery, state: FSMContext, db: Database) -> None:
    fd = await _fd(cb, state)
    if fd is None:
        return
    uid = cb.from_user.id
    mode = cb.data.split(":")[2]
    await db.save_filter(uid, fd["deal"], fd["districts"], fd["rooms"], fd.get("pmin"), fd.get("pmax"))
    await db.set_user_field(uid, "notify_mode", mode)
    await state.clear()
    await cb.answer("Saqlandi ✅")
    f = await db.get_filter(uid)
    matches = [l for l in await db.active_listings() if listing_matches(l, f)]
    b = InlineKeyboardBuilder()
    if matches:
        b.row(InlineKeyboardButton(text=f"🔎 Hozir mos uylarni ko‘rish ({len(matches)})",
                                   callback_data="u:more:f:0"))
    await cb.message.edit_text(
        "✅ <b>Filtr saqlandi!</b>\n\n" + describe_filter(f, mode) +
        "\n\nMos uy joylanishi bilan xabar beramiz. O‘zgartirish: «🔔 Mening filtrim».",
        reply_markup=b.as_markup() if matches else None)


@router.message(F.text == C.BTN_FILTER)
async def my_filter(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    uid = message.from_user.id
    f = await db.get_filter(uid)
    if not f:
        return await start_filter(message, state)
    user = await db.get_user(uid)
    mode = user["notify_mode"]
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ O‘zgartirish", callback_data="f:start"))
    if mode == "off":
        b.row(InlineKeyboardButton(text="🔔 Xabarnomani yoqish", callback_data="f:set:instant"))
    else:
        other = ("daily", "🗓 Kuniga 1 martaga o‘tish") if mode == "instant" else ("instant", "⚡ Darhol rejimiga o‘tish")
        b.row(InlineKeyboardButton(text=other[1], callback_data=f"f:set:{other[0]}"))
        b.row(InlineKeyboardButton(text="🔕 Xabarnomani o‘chirish", callback_data="f:set:off"))
    await message.answer("🔔 <b>Sizning filtringiz</b>\n\n" + describe_filter(f, mode),
                         reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("f:set:"))
async def f_set_mode(cb: CallbackQuery, db: Database) -> None:
    mode = cb.data.split(":")[2]
    await db.set_user_field(cb.from_user.id, "notify_mode", mode)
    f = await db.get_filter(cb.from_user.id)
    await cb.answer("Saqlandi ✅")
    await cb.message.edit_text("🔔 <b>Sizning filtringiz</b>\n\n" + describe_filter(f, mode))


# =====================================================================
#  "O'xshash uylar"
# =====================================================================
async def show_similar_offer(message: Message, db: Database, listing: dict) -> None:
    f = filter_from_listing(listing)
    matches = [l for l in await db.active_listings() if l["id"] != listing["id"] and listing_matches(l, f)]
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Ha, shunday uylar chiqsa xabar bering",
                               callback_data=f"u:simok:{listing['id']}"))
    if matches:
        b.row(InlineKeyboardButton(text=f"🔎 Hozir ko‘rish ({len(matches)})",
                                   callback_data=f"u:simshow:{listing['id']}"))
    b.row(InlineKeyboardButton(text="⚙️ O‘zim sozlayman", callback_data="f:start"))
    await message.answer(
        f"🔔 <b>#{code(listing['id'])} ga o‘xshash uylar</b>\n\n" + describe_filter(f) +
        "\n\nShunday uy joylanishi bilan sizga xabar beraylikmi?", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("u:simok:"))
async def sim_ok(cb: CallbackQuery, db: Database) -> None:
    listing = await db.get_listing(int(cb.data.split(":")[2]))
    f = filter_from_listing(listing)
    uid = cb.from_user.id
    await db.save_filter(uid, f["deal"], [f["districts"]] if f["districts"] else [],
                         [f["rooms"]] if f["rooms"] else [], f["price_min"], f["price_max"])
    user = await db.get_user(uid)
    if user["notify_mode"] == "off":
        await db.set_user_field(uid, "notify_mode", "instant")
    await cb.answer("Obuna bo‘ldingiz ✅")
    await cb.message.edit_text(
        "✅ <b>Tayyor!</b> Shunday uy chiqishi bilan xabar beramiz.\n\n" + describe_filter(await db.get_filter(uid)))


@router.callback_query(F.data.startswith("u:simshow:"))
async def sim_show(cb: CallbackQuery, bot: Bot, db: Database) -> None:
    listing = await db.get_listing(int(cb.data.split(":")[2]))
    f = filter_from_listing(listing)
    matches = [l for l in await db.active_listings() if l["id"] != listing["id"] and listing_matches(l, f)]
    await cb.answer()
    for l in matches[:PAGE]:
        await send_card(bot, db, cb.from_user.id, l)


# =====================================================================
#  Uy qidirish va saqlanganlar
# =====================================================================
@router.message(F.text == C.BTN_SEARCH)
async def search(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    await state.clear()
    await show_listings(message, bot, db, message.from_user.id, "f", 0)


@router.callback_query(F.data.startswith("u:more:"))
async def search_more(cb: CallbackQuery, bot: Bot, db: Database) -> None:
    _, _, mode, offset = cb.data.split(":")
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await show_listings(cb.message, bot, db, cb.from_user.id, mode, int(offset))


async def show_listings(message: Message, bot: Bot, db: Database, uid: int, mode: str, offset: int) -> None:
    listings = await db.active_listings()
    f = await db.get_filter(uid) if mode == "f" else None
    if f:
        listings = [l for l in listings if listing_matches(l, f)]
    if not listings:
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🏘 Barcha e’lonlarni ko‘rish", callback_data="u:more:a:0"))
        b.row(InlineKeyboardButton(text="⚙️ Filtrni o‘zgartirish", callback_data="f:start"))
        await message.answer(
            "😔 Hozircha filtringizga mos uy yo‘q.\nMos uy chiqishi bilan sizga xabar beramiz 🔔",
            reply_markup=b.as_markup() if f else None)
        return
    if offset == 0:
        title = "🔎 Filtringizga mos uylar" if f else "🏘 Barcha e’lonlar"
        await message.answer(f"{title}: <b>{len(listings)}</b> ta")
    page = listings[offset:offset + PAGE]
    for l in page:
        await send_card(bot, db, uid, l)
    rest = len(listings) - offset - PAGE
    if rest > 0:
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text=f"⬇️ Yana ko‘rsatish ({rest})",
                                   callback_data=f"u:more:{mode}:{offset + PAGE}"))
        await message.answer("Davomi bor 👇", reply_markup=b.as_markup())


@router.message(F.text == C.BTN_SAVED)
async def saved(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await render_saved(message, db, message.from_user.id, edit=False)


async def render_saved(message: Message, db: Database, uid: int, edit: bool) -> None:
    favs = await db.user_favorites(uid)
    if not favs:
        text, kb = "❤️ Saqlangan uylar yo‘q.\nE’lon ostidagi <b>❤️ Saqlash</b> tugmasini bosing.", None
    else:
        b = InlineKeyboardBuilder()
        for l in favs:
            icon = {"sold": "✅ ", "reserved": "⏸ "}.get(l["status"], "")
            b.row(InlineKeyboardButton(text=f"{icon}{short_title(l)}", callback_data=f"u:card:{l['id']}"),
                  InlineKeyboardButton(text="🗑", callback_data=f"u:unsave:{l['id']}"))
        text, kb = f"❤️ <b>Saqlangan uylar</b>: {len(favs)} ta", b.as_markup()
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("u:unsave:"))
async def unsave(cb: CallbackQuery, db: Database) -> None:
    await db.remove_favorite(cb.from_user.id, int(cb.data.split(":")[2]))
    await cb.answer("O‘chirildi")
    await render_saved(cb.message, db, cb.from_user.id, edit=True)


# Bot ichidagi kartochka tugmalari: u:call:12, u:save:12, u:sim:12, u:pics:12, u:card:12
@router.callback_query(F.data.regexp(r"^u:(call|save|sim|pics|card):\d+$"))
async def card_action(cb: CallbackQuery, state: FSMContext, bot: Bot, db: Database) -> None:
    _, action, lid = cb.data.split(":")
    listing = await db.get_listing(int(lid))
    await cb.answer()
    if not listing or listing["status"] == "draft":
        await cb.message.answer("😔 Bu e’lon topilmadi.")
        return
    await do_action(cb.message, state, bot, db, cb.from_user.id, action, listing)


# =====================================================================
#  Rieltor bilan bog'lanish
# =====================================================================
@router.message(F.text == C.BTN_CONTACT)
async def contact(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    await state.clear()
    uid = message.from_user.id
    await db.add_lead(uid, None, "general")
    url = realtor_url()
    if url:
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="✈️ Telegramda yozish", url=url))
        await message.answer(contact_lines(), reply_markup=b.as_markup())
    await start_lead(message, state, bot, db, uid, None)


# =====================================================================
#  "Uyimni sotmoqchiman" — sotuvchidan ariza (rieltor uchun yangi obyektlar)
# =====================================================================
@router.message(F.text == C.BTN_SELL)
async def sell_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SellerForm.district)
    b = InlineKeyboardBuilder()
    for slug, name, _ in C.DISTRICTS:
        b.button(text=name, callback_data=f"s:d:{slug}")
    b.adjust(3)
    await message.answer(
        "🏡 <b>Uyingizni sotishda yordam beramiz!</b>\n\n"
        "Bir necha savolga javob bering, rieltor siz bilan bog‘lanadi.\n\n📍 Uy qaysi tumanda?",
        reply_markup=b.as_markup())


@router.callback_query(SellerForm.district, F.data.startswith("s:d:"))
async def sell_district(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(district=cb.data.split(":")[2])
    await state.set_state(SellerForm.rooms)
    b = InlineKeyboardBuilder()
    for i in range(1, 7):
        b.button(text=str(i), callback_data=f"s:r:{i}")
    b.adjust(6)
    await cb.answer()
    await cb.message.edit_text("🏠 Necha xonali?", reply_markup=b.as_markup())


@router.callback_query(SellerForm.rooms, F.data.startswith("s:r:"))
async def sell_rooms(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(rooms=int(cb.data.split(":")[2]))
    await state.set_state(SellerForm.price)
    await cb.answer()
    await cb.message.edit_text("💰 Qancha narxda sotmoqchisiz? (masalan: 55 000$)")


@router.message(SellerForm.price, F.text, ~F.text.in_(C.MENU_TEXTS))
async def sell_price(message: Message, state: FSMContext) -> None:
    await state.update_data(price=message.text[:100])
    await state.set_state(SellerForm.description)
    await message.answer("📝 Uy haqida qisqacha yozing: manzil/mo‘ljal, qavat, maydon, holati.")


@router.message(SellerForm.description, F.text, ~F.text.in_(C.MENU_TEXTS))
async def sell_desc(message: Message, state: FSMContext, db: Database) -> None:
    await state.update_data(description=message.text[:1500])
    user = await db.get_user(message.from_user.id)
    if user and user.get("phone"):
        return await finish_seller(message, state, message.bot, db, user["phone"])
    await state.set_state(SellerForm.phone)
    await message.answer("📱 Bog‘lanish uchun raqamingizni yuboring:", reply_markup=phone_request_kb())


@router.message(SellerForm.phone, F.contact)
@router.message(SellerForm.phone, F.text.regexp(PHONE_RE.pattern))
async def sell_phone(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    phone = message.contact.phone_number if message.contact else message.text.strip()
    await db.set_user_field(message.from_user.id, "phone", phone)
    await finish_seller(message, state, bot, db, phone)


@router.message(SellerForm.phone, F.text == C.BTN_NO_PHONE)
async def sell_no_phone(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    await finish_seller(message, state, bot, db, None)


async def finish_seller(message: Message, state: FSMContext, bot: Bot, db: Database, phone: str | None) -> None:
    data = await state.get_data()
    await state.clear()
    uid = message.from_user.id
    rid = await db.add_seller_request(user_id=uid, district=data.get("district"), rooms=data.get("rooms"),
                                      price=data.get("price"), description=data.get("description"), phone=phone)
    user = await db.get_user(uid)
    uname = f" (@{h(user['username'])})" if user.get("username") else ""
    await notify_admins(bot, "\n".join([
        f"🏡 <b>Sotuvchidan ariza #{rid}</b>",
        f"👤 <a href=\"tg://user?id={uid}\">{h(user.get('full_name') or 'Mijoz')}</a>{uname}",
        f"📱 {h(phone) if phone else 'raqam qoldirmadi'}",
        f"📍 {C.district_label(data.get('district'))} · 🏠 {data.get('rooms')} xona",
        f"💰 {h(data.get('price') or '')}",
        f"📝 {h(data.get('description') or '')}",
    ]))
    await message.answer(
        "✅ <b>Arizangiz qabul qilindi!</b> Rieltor tez orada siz bilan bog‘lanadi.",
        reply_markup=menu_for(uid))


# =====================================================================
#  Boshqa xabarlar
# =====================================================================
@router.message(F.chat.type == "private")
async def fallback(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current in (LeadPhone.waiting.state, SellerForm.phone.state):
        await message.answer("📱 Iltimos, raqamni <b>📱 Raqamni yuborish</b> tugmasi orqali yuboring "
                             "yoki +998 90 123 45 67 ko‘rinishida yozing.")
        return
    await message.answer("Quyidagi menyudan foydalaning 👇", reply_markup=menu_for(message.from_user.id))
