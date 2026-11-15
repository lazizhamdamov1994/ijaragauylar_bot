"""Admin: e'lonlar ro'yxati, "Sotildi"/"Band", narxni o'zgartirish, statistika, ommaviy xabar."""
from __future__ import annotations

import asyncio
from collections import Counter

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import constants as C
from ..db import Database
from ..keyboards import admin_menu, channel_post_url, user_menu
from ..matching import csv
from ..middlewares import IsAdmin
from ..notifier import broadcast, notify_favorites
from ..posting import refresh_channel_post
from ..states import Broadcast, ManageListing
from ..texts import STATUS_ICON, code, fmt_price, short_title
from .admin_new import parse_price

router = Router(name="admin_manage")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

PAGE = 8


@router.message(F.text == C.BTN_ADMIN)
@router.message(Command("admin"))
async def admin_home(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=admin_menu())


@router.message(F.text == C.BTN_USERMODE)
async def user_mode(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("👤 Mijoz menyusi (botni mijoz ko‘zi bilan sinab ko‘ring).",
                         reply_markup=user_menu(is_admin=True))


# ---------------- e'lonlar ro'yxati ----------------
async def render_list(db: Database, which: str, offset: int):
    statuses = ["sold"] if which == "sold" else ["active", "reserved"]
    total = await db.count_by_status(statuses)
    items = await db.listings_by_status(statuses, PAGE, offset)
    b = InlineKeyboardBuilder()
    for l in items:
        b.row(InlineKeyboardButton(
            text=f"{STATUS_ICON.get(l['status'], '')} {short_title(l)}", callback_data=f"ml:open:{l['id']}"))
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"ml:list:{which}:{max(0, offset - PAGE)}"))
    if offset + PAGE < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"ml:list:{which}:{offset + PAGE}"))
    if nav:
        b.row(*nav)
    other = ("act", "🟢 Faol e’lonlar") if which == "sold" else ("sold", "✅ Sotilganlar")
    b.row(InlineKeyboardButton(text=other[1], callback_data=f"ml:list:{other[0]}:0"))
    title = "✅ Sotilgan e’lonlar" if which == "sold" else "🟢 Faol e’lonlar"
    text = f"<b>{title}</b>: {total} ta" + ("" if total else "\n\nHozircha bo‘sh.")
    return text, b.as_markup()


@router.message(F.text == C.BTN_LIST)
async def list_listings(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, kb = await render_list(db, "act", 0)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("ml:list:"))
async def list_page(cb: CallbackQuery, db: Database) -> None:
    _, _, which, offset = cb.data.split(":")
    text, kb = await render_list(db, which, int(offset))
    await cb.answer()
    await cb.message.edit_text(text, reply_markup=kb)


async def render_card(db: Database, lid: int):
    l = await db.get_listing(lid)
    if not l:
        return "E’lon topilmadi.", None
    st = await db.listing_stats(lid)
    status_name = {"active": "🟢 Faol", "reserved": "⏸ Band", "sold": "✅ Sotilgan", "draft": "📝 Qoralama"}
    text = (
        f"<b>{short_title(l)}</b>\n\n"
        f"Holat: {status_name.get(l['status'], l['status'])}\n"
        f"📞 Bog‘lanish so‘rovlari: <b>{st['leads']}</b>\n"
        f"❤️ Saqlaganlar: <b>{st['favs']}</b>\n"
        f"👆 Jami bosishlar: <b>{st['clicks']}</b>\n"
        f"📍 Lokatsiya: {'bor' if l['lat'] is not None else 'yo‘q'}"
    )
    b = InlineKeyboardBuilder()
    if l["status"] == "active":
        b.row(InlineKeyboardButton(text="✅ Sotildi", callback_data=f"ml:st:{lid}:sold"),
              InlineKeyboardButton(text="⏸ Band (zaklad)", callback_data=f"ml:st:{lid}:reserved"))
    elif l["status"] in ("reserved", "sold"):
        b.row(InlineKeyboardButton(text="▶️ Qayta faol qilish", callback_data=f"ml:st:{lid}:active"))
        if l["status"] == "reserved":
            b.row(InlineKeyboardButton(text="✅ Sotildi", callback_data=f"ml:st:{lid}:sold"))
    if l["status"] != "sold":
        b.row(InlineKeyboardButton(text="💲 Narxni o‘zgartirish", callback_data=f"ml:price:{lid}"))
    url = channel_post_url(l)
    if url:
        b.row(InlineKeyboardButton(text="🔗 Kanalda ko‘rish", url=url))
    b.row(InlineKeyboardButton(text="🔙 Ro‘yxat", callback_data="ml:list:act:0"))
    return text, b.as_markup()


@router.callback_query(F.data.startswith("ml:open:"))
async def open_card(cb: CallbackQuery, db: Database) -> None:
    text, kb = await render_card(db, int(cb.data.split(":")[2]))
    await cb.answer()
    await cb.message.edit_text(text, reply_markup=kb)


@router.message(Command("e"))
async def open_by_id(message: Message, command: CommandObject, db: Database) -> None:
    """/e 12 yoki /e N0012 — e'lonni ID bo'yicha ochish."""
    digits = "".join(ch for ch in (command.args or "") if ch.isdigit())
    if not digits:
        return await message.answer("Foydalanish: <code>/e 12</code>")
    text, kb = await render_card(db, int(digits))
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("ml:st:"))
async def set_status(cb: CallbackQuery, bot: Bot, db: Database) -> None:
    _, _, lid, status = cb.data.split(":")
    lid = int(lid)
    await db.update_listing(lid, status=status)
    ok = await refresh_channel_post(bot, db, lid)
    await cb.answer("Saqlandi" + ("" if ok else " (kanal posti yangilanmadi!)"), show_alert=not ok)
    text, kb = await render_card(db, lid)
    await cb.message.edit_text(text, reply_markup=kb)
    if status == "sold":
        l = await db.get_listing(lid)
        word = "ijaraga berildi" if l["deal"] == "rent" else "sotildi"
        asyncio.create_task(notify_favorites(
            bot, db, lid, f"😔 Siz saqlagan uy <b>{word}</b>. Lekin o‘xshash uylarni topib beramiz 👇"))


@router.callback_query(F.data.startswith("ml:price:"))
async def ask_price(cb: CallbackQuery, state: FSMContext, db: Database) -> None:
    lid = int(cb.data.split(":")[2])
    l = await db.get_listing(lid)
    await state.set_state(ManageListing.price)
    await state.update_data(listing_id=lid)
    await cb.answer()
    await cb.message.answer(
        f"💲 #{code(lid)} hozirgi narxi: <b>{fmt_price(l)}</b>\nYangi narxni yozing:")


@router.message(ManageListing.price, F.text, ~F.text.in_(C.MENU_TEXTS))
async def set_price(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    new = parse_price(message.text)
    if not new:
        return await message.answer("⚠️ Narx noto‘g‘ri. Masalan: 43000")
    lid = (await state.get_data())["listing_id"]
    l = await db.get_listing(lid)
    old = l["price"] or 0
    await db.update_listing(lid, price=new)
    await state.clear()
    ok = await refresh_channel_post(bot, db, lid)
    l["price"] = new
    msg = f"✅ Narx yangilandi: <b>{fmt_price(l)}</b>"
    if not ok:
        msg += "\n⚠️ Kanal posti yangilanmadi."
    await message.answer(msg, reply_markup=admin_menu())
    if new < old:
        l_old = dict(l, price=old)
        sent = await notify_favorites(
            bot, db, lid,
            f"📉 <b>Narx tushdi!</b> Siz saqlagan uy: {fmt_price(l_old)} → <b>{fmt_price(l)}</b>")
        await message.answer(f"📨 Saqlab qo‘yganlarga xabar yuborildi: {sent} ta")


# ---------------- statistika ----------------
@router.message(F.text == C.BTN_STATS)
@router.message(Command("stats"))
async def stats(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    s = await db.stats()
    districts = Counter()
    for row in s["filter_districts"]:
        districts.update(csv(row["districts"]))
    top_d = ", ".join(f"{C.DISTRICT_NAME.get(d, d)} ({n})" for d, n in districts.most_common(5)) or "—"
    top_l = "\n".join(
        f"  {i}. {short_title(l)} — {l['n']} ta" for i, l in enumerate(s["top_listings"], 1)) or "  —"
    await message.answer(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['users']}</b> (faol {s['active']}, bloklagan {s['blocked']})\n"
        f"🆕 Yangi: bugun <b>{s['new_today']}</b>, 7 kunda <b>{s['new_week']}</b>\n"
        f"🔔 Filtr bilan kutayotganlar: <b>{s['with_filter']}</b>\n"
        f"📱 Raqam qoldirganlar: <b>{s['with_phone']}</b>\n\n"
        f"🏠 Faol e’lonlar: <b>{s['listings_active']}</b> · Sotilgan: <b>{s['listings_sold']}</b>\n"
        f"🔥 Lidlar: bugun <b>{s['leads_today']}</b>, 7 kunda <b>{s['leads_week']}</b>\n"
        f"🏡 Sotuvchi arizalari (7 kun): <b>{s['sellers_week']}</b>\n\n"
        f"📍 Eng ko‘p qidirilgan tumanlar: {top_d}\n\n"
        f"🏆 Eng faol e’lonlar (30 kun):\n{top_l}"
    )


# ---------------- ommaviy xabar ----------------
@router.message(F.text == C.BTN_BCAST)
async def bcast_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Broadcast.message)
    await message.answer(
        "📣 Barcha foydalanuvchilarga yuboriladigan xabarni yuboring (matn, rasm yoki video).\n"
        "Bekor qilish: /admin")


@router.message(Broadcast.message, ~F.text.in_(C.MENU_TEXTS))
async def bcast_got(message: Message, state: FSMContext, db: Database) -> None:
    await state.update_data(src_chat=message.chat.id, src_msg=message.message_id)
    await state.set_state(Broadcast.confirm)
    n = len(await db.active_user_ids())
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"✅ Yuborish ({n} kishi)", callback_data="bc:go"),
          InlineKeyboardButton(text=C.BTN_CANCEL, callback_data="bc:no"))
    await message.answer(
        f"Shu xabar <b>{n}</b> ta foydalanuvchiga yuboriladi (~{max(1, n // 25 // 60)} daqiqa). Tasdiqlaysizmi?",
        reply_markup=b.as_markup())


@router.callback_query(Broadcast.confirm, F.data.in_({"bc:go", "bc:no"}))
async def bcast_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot, db: Database) -> None:
    data = await state.get_data()
    await state.clear()
    await cb.message.edit_reply_markup(reply_markup=None)
    if cb.data == "bc:no":
        await cb.answer("Bekor qilindi")
        return
    await cb.answer("Yuborish boshlandi")
    ids = await db.active_user_ids()

    async def run():
        res = await broadcast(
            db, ids, lambda uid: bot.copy_message(uid, data["src_chat"], data["src_msg"]))
        await bot.send_message(
            cb.from_user.id,
            f"📣 Tugadi. Yetkazildi: {res['ok']} · Bloklagan: {res['blocked']} · Xato: {res['error']}")

    asyncio.create_task(run())
    await cb.message.answer("⏳ Yuborilmoqda... tugagach xabar beraman.", reply_markup=admin_menu())
