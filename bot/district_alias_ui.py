"""
"Tuman kalit so'zlari" - admin/moderatorlar mahalla/mavze/mashxur joy
nomlarini (masalan "Darxon" -> Sergeli) tumanlarga biriktiradigan,
vaqt o'tishi bilan o'zi kengayadigan bo'lim. Bog'lanish DB'da
(common/districts.py, `district_aliases` jadvali) saqlanadi - shundan
keyin "Tezkor e'lon" oqimi va sayt tuman filtri ham shu ro'yxatdan
foydalanadi.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from common.districts import TASHKENT_DISTRICTS, add_district_alias, list_district_aliases, remove_district_alias

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


def _district_list_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(d, callback_data=f"distalias_view_{i}")] for i, d in enumerate(TASHKENT_DISTRICTS)]
    return InlineKeyboardMarkup(rows)


async def show_district_alias_districts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "\U0001F5FA <b>Tuman kalit so'zlari</b>\n\n"
        "Bu yerda har bir tumanga mahalla/mavze/mashxur joy nomlarini "
        "(masalan «Darxon» → Sergeli) biriktirasiz - shundan keyin "
        "«Tezkor e'lon» bunday so'zlarni matndan avtomatik tanib oladi, "
        "sayt tuman filtri ham ularni hisobga oladi.\n\nQaysi tumanni ko'rmoqchisiz?"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=_district_list_keyboard())
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=_district_list_keyboard())


def _render_district_aliases(idx: int) -> tuple:
    district = TASHKENT_DISTRICTS[idx]
    aliases = [a for a in list_district_aliases() if a["district"] == district]
    lines = [f"\U0001F5FA <b>{esc(district)}</b>\n"]
    rows = [[InlineKeyboardButton("➕ Yangi kalit so'z qo'shish", callback_data=f"distalias_add_{idx}")]]
    if not aliases:
        lines.append("<i>Hozircha kalit so'z yo'q (faqat tuman nomining o'zi tanib olinadi).</i>")
    else:
        for a in aliases:
            lines.append(f"• {esc(a['alias'])}")
            rows.append([InlineKeyboardButton(f"❌ {a['alias']}", callback_data=f"distaliasrm_{a['id']}_{idx}")])
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="distalias_back")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def district_alias_view_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    idx = int(query.data.rsplit("_", 1)[1])
    text, kb = _render_district_aliases(idx)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def district_alias_back_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_district_alias_districts(update, context)


async def district_alias_remove_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return
    _, alias_id, idx = query.data.split("_")
    remove_district_alias(int(alias_id))
    text, kb = _render_district_aliases(int(idx))
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def district_alias_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_staff(query.from_user.id):
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return ConversationHandler.END
    idx = int(query.data.rsplit("_", 1)[1])
    context.user_data["distalias_target_idx"] = idx
    district = TASHKENT_DISTRICTS[idx]
    await query.message.reply_text(
        f"✏️ <b>{esc(district)}</b> uchun yangi kalit so'z(lar)ni yozing.\n\n"
        "Bir nechtasini vergul bilan ajratib yozishingiz mumkin "
        "(masalan: <i>Darxon, Yangi Darxon, Choshtepa</i>):",
        parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove(),
    )
    return DISTALIAS_ADD_WAIT


async def district_alias_add_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await try_escape_to_menu(update, context):
        context.user_data.pop("distalias_target_idx", None)
        return ConversationHandler.END
    idx = context.user_data.get("distalias_target_idx")
    if idx is None:
        return ConversationHandler.END
    district = TASHKENT_DISTRICTS[idx]
    raw = (update.message.text or "").strip()
    if not raw:
        await update.message.reply_text("⚠️ Bo'sh bo'lishi mumkin emas. Qaytadan yozing:")
        return DISTALIAS_ADD_WAIT
    if len(raw) > 300:
        await update.message.reply_text("⚠️ Juda uzun. Qisqaroq yozing:")
        return DISTALIAS_ADD_WAIT
    keywords = [k.strip() for k in raw.split(",") if k.strip()]
    added_count = sum(1 for kw in keywords if add_district_alias(kw, district, added_by=update.effective_user.id))
    context.user_data.pop("distalias_target_idx", None)
    await update.message.reply_text(
        f"✅ {added_count} ta yangi kalit so'z «{esc(district)}» tumaniga biriktirildi.",
        parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(update.effective_user.id),
    )
    text, kb = _render_district_aliases(idx)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return ConversationHandler.END


async def district_alias_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("distalias_target_idx", None)
    await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END
