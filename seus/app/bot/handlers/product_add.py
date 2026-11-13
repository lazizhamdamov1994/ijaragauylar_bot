"""Tovar qo'shish: rasm/video → nom → narx → razmer/rang/son → tavsif → oldindan ko'rish → joylash."""
from __future__ import annotations

from functools import partial
from html import escape as _escape

escape = partial(_escape, quote=False)

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.callbacks import PreviewCb, VariantCb
from app.bot.publisher import post_link, publish_to_channel, send_product
from app.bot.states import ProductAdd
from app.db.models import Seller
from app.services import channels as channel_service
from app.services import products as product_service
from app.services.dto import MediaItem, ProductDraft, VariantData
from app.services.errors import ServiceError
from app.services.formatting import variants_list_text, view_from_draft
from app.services.parsing import (
    merge_variants,
    parse_price,
    parse_stock,
    parse_variants,
    validate_description,
    validate_product_name,
)
from app.services.products import MAX_MEDIA
from app.texts import all_langs, t

router = Router(name="product_add")


# ---------- yordamchilar ----------

async def get_draft(state: FSMContext) -> ProductDraft:
    return ProductDraft.from_dict((await state.get_data()).get("draft"))


async def save_draft(state: FSMContext, draft: ProductDraft) -> None:
    await state.update_data(draft=draft.to_dict())


async def is_editing(state: FSMContext) -> bool:
    return bool((await state.get_data()).get("editing"))


async def ask_name(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(ProductAdd.name)
    await message.answer(t("ask_name", lang), reply_markup=kb.cancel_only(lang))


async def ask_price(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(ProductAdd.price)
    await message.answer(t("ask_price", lang), reply_markup=kb.cancel_only(lang))


async def ask_variants(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(ProductAdd.variants)
    draft = await get_draft(state)
    await message.answer(t("ask_variants", lang), reply_markup=kb.done_cancel(lang))
    if draft.variants:
        await show_variants(message, draft, lang)
    else:
        await message.answer("👇", reply_markup=kb.variants_actions(lang))


async def show_variants(message: Message, draft: ProductDraft, lang: str) -> None:
    await message.answer(
        t("variants_current", lang, list=variants_list_text(draft.variants, lang)),
        reply_markup=kb.variants_actions(lang, can_undo=bool(draft.variants)),
    )


async def ask_description(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(ProductAdd.description)
    await message.answer(t("ask_description", lang), reply_markup=kb.skip_cancel(lang))


async def show_preview(message: Message, state: FSMContext, bot: Bot, seller: Seller, lang: str) -> None:
    await state.set_state(ProductAdd.preview)
    await state.update_data(editing=False)
    draft = await get_draft(state)
    await message.answer(t("preview_title", lang), reply_markup=ReplyKeyboardRemove())
    await send_product(
        bot, message.chat.id, draft.media, view_from_draft(draft, seller.shop_name),
        kb.preview_actions(lang), lang,
    )


async def next_step(after: str, message: Message, state: FSMContext, bot: Bot, seller: Seller, lang: str) -> None:
    """Tahrirlash rejimida — oldindan ko'rishga qaytadi, aks holda keyingi qadamga o'tadi."""
    if await is_editing(state):
        await show_preview(message, state, bot, seller, lang)
        return
    steps = {"photos": ask_name, "name": ask_price, "price": ask_variants, "variants": ask_description}
    if after in steps:
        await steps[after](message, state, lang)
    else:
        await show_preview(message, state, bot, seller, lang)


# ---------- 1. Boshlash va rasmlar ----------

@router.message(F.text.in_(all_langs("btn_add_product")))
async def start_add(message: Message, state: FSMContext, seller: Seller | None, lang: str) -> None:
    if seller is None:
        await message.answer(t("not_registered", lang))
        return
    await state.clear()
    await state.set_state(ProductAdd.photos)
    await save_draft(state, ProductDraft())
    await message.answer(t("ask_photos", lang), reply_markup=kb.done_cancel(lang))


def _media_from(message: Message) -> MediaItem | None:
    if message.photo:
        return MediaItem("photo", message.photo[-1].file_id)  # eng katta o'lcham
    if message.video:
        return MediaItem("video", message.video.file_id)
    return None


@router.message(ProductAdd.photos, F.photo | F.video)
async def got_media(message: Message, state: FSMContext, lang: str, album: list[Message] | None = None) -> None:
    new_items = [m for m in (_media_from(x) for x in (album or [message])) if m]
    draft = await get_draft(state)
    room = MAX_MEDIA - len(draft.media)
    draft.media += new_items[:room]
    await save_draft(state, draft)
    if len(new_items) > room:
        await message.answer(t("photos_limit", lang))
    photos = sum(1 for m in draft.media if m.kind == "photo")
    await message.answer(
        t("photos_added", lang, count=len(draft.media), photos=photos, videos=len(draft.media) - photos),
        reply_markup=kb.done_cancel(lang),
    )


@router.message(ProductAdd.photos, F.text.in_(all_langs("btn_done")))
async def photos_done(message: Message, state: FSMContext, bot: Bot, seller: Seller, lang: str) -> None:
    draft = await get_draft(state)
    if not draft.media:
        await message.answer(t("photos_need_one", lang))
        return
    await next_step("photos", message, state, bot, seller, lang)


@router.message(ProductAdd.photos)
async def photos_wrong(message: Message, lang: str) -> None:
    await message.answer(t("photos_only", lang))


# ---------- 2. Nom ----------

@router.message(ProductAdd.name, F.text)
async def got_name(message: Message, state: FSMContext, bot: Bot, seller: Seller, lang: str) -> None:
    try:
        name = validate_product_name(message.text)
    except ServiceError as e:
        await message.answer(t(e.code, lang))
        return
    draft = await get_draft(state)
    draft.name = name
    await save_draft(state, draft)
    await next_step("name", message, state, bot, seller, lang)


# ---------- 3. Narx ----------

@router.message(ProductAdd.price, F.text)
async def got_price(message: Message, state: FSMContext, bot: Bot, seller: Seller, lang: str) -> None:
    try:
        price = parse_price(message.text)
    except ServiceError as e:
        await message.answer(t(e.code, lang))
        return
    draft = await get_draft(state)
    draft.price = price
    await save_draft(state, draft)
    await next_step("price", message, state, bot, seller, lang)


# ---------- 4. Razmer / rang / son ----------

@router.message(ProductAdd.variants, F.text.in_(all_langs("btn_done")))
async def variants_done(message: Message, state: FSMContext, bot: Bot, seller: Seller, lang: str) -> None:
    draft = await get_draft(state)
    if not draft.variants:
        await message.answer(t("variants_need_one", lang))
        return
    await next_step("variants", message, state, bot, seller, lang)


@router.message(ProductAdd.variants, F.text)
async def got_variants_text(message: Message, state: FSMContext, lang: str) -> None:
    found, bad = parse_variants(message.text)
    draft = await get_draft(state)
    if found:
        draft.variants = merge_variants(draft.variants, found)
        await save_draft(state, draft)
    if bad:
        await message.answer(t("variants_parse_error", lang, lines=escape("\n".join(bad))))
    await show_variants(message, draft, lang)


@router.callback_query(ProductAdd.variants, VariantCb.filter(F.action == "start"))
async def wizard_start(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(ProductAdd.variant_size)
    await call.message.answer(t("choose_size", lang), reply_markup=kb.size_picker(lang))
    await call.answer()


@router.callback_query(ProductAdd.variants, VariantCb.filter(F.action == "undo"))
async def wizard_undo(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    draft = await get_draft(state)
    if draft.variants:
        draft.variants.pop()
        await save_draft(state, draft)
    await show_variants(call.message, draft, lang)
    await call.answer()


async def _set_size(message: Message, state: FSMContext, size: str, lang: str) -> None:
    await state.update_data(pending_size="" if size == "-" else size[:20])
    await state.set_state(ProductAdd.variant_color)
    await message.answer(t("choose_color", lang), reply_markup=kb.color_picker(lang))


async def _set_color(message: Message, state: FSMContext, color: str, lang: str) -> None:
    await state.update_data(pending_color="" if color == "-" else color[:50].lower())
    await state.set_state(ProductAdd.variant_qty)
    await message.answer(t("choose_qty", lang), reply_markup=kb.qty_picker())


async def _set_qty(message: Message, state: FSMContext, qty_text: str, lang: str) -> None:
    try:
        qty = parse_stock(qty_text)
    except ServiceError as e:
        await message.answer(t(e.code, lang))
        return
    data = await state.get_data()
    draft = await get_draft(state)
    new = VariantData(size=data.get("pending_size", ""), color=data.get("pending_color", ""), stock=qty)
    draft.variants = merge_variants(draft.variants, [new])
    await save_draft(state, draft)
    await state.set_state(ProductAdd.variants)
    await show_variants(message, draft, lang)


@router.callback_query(ProductAdd.variant_size, VariantCb.filter(F.action == "size"))
async def wizard_size_cb(call: CallbackQuery, callback_data: VariantCb, state: FSMContext, lang: str) -> None:
    await call.answer()
    await _set_size(call.message, state, callback_data.value, lang)


@router.message(ProductAdd.variant_size, F.text)
async def wizard_size_text(message: Message, state: FSMContext, lang: str) -> None:
    await _set_size(message, state, message.text.strip().upper(), lang)


@router.callback_query(ProductAdd.variant_color, VariantCb.filter(F.action == "color"))
async def wizard_color_cb(call: CallbackQuery, callback_data: VariantCb, state: FSMContext, lang: str) -> None:
    await call.answer()
    await _set_color(call.message, state, callback_data.value, lang)


@router.message(ProductAdd.variant_color, F.text)
async def wizard_color_text(message: Message, state: FSMContext, lang: str) -> None:
    await _set_color(message, state, message.text.strip(), lang)


@router.callback_query(ProductAdd.variant_qty, VariantCb.filter(F.action == "qty"))
async def wizard_qty_cb(call: CallbackQuery, callback_data: VariantCb, state: FSMContext, lang: str) -> None:
    await call.answer()
    await _set_qty(call.message, state, callback_data.value, lang)


@router.message(ProductAdd.variant_qty, F.text)
async def wizard_qty_text(message: Message, state: FSMContext, lang: str) -> None:
    await _set_qty(message, state, message.text, lang)


# ---------- 5. Tavsif ----------

@router.message(ProductAdd.description, F.text)
async def got_description(message: Message, state: FSMContext, bot: Bot, seller: Seller, lang: str) -> None:
    if message.text in all_langs("btn_skip"):
        description = None
    else:
        try:
            description = validate_description(message.text)
        except ServiceError as e:
            await message.answer(t(e.code, lang))
            return
    draft = await get_draft(state)
    draft.description = description
    await save_draft(state, draft)
    await next_step("description", message, state, bot, seller, lang)


# ---------- 6. Oldindan ko'rish ----------

@router.callback_query(ProductAdd.preview, PreviewCb.filter(F.action == "edit"))
async def preview_edit(call: CallbackQuery, lang: str) -> None:
    await call.message.answer(t("edit_what", lang), reply_markup=kb.edit_fields(lang))
    await call.answer()


@router.callback_query(ProductAdd.preview, PreviewCb.filter(F.action == "back"))
async def preview_back(call: CallbackQuery, state: FSMContext, bot: Bot, seller: Seller, lang: str) -> None:
    await call.answer()
    await show_preview(call.message, state, bot, seller, lang)


@router.callback_query(ProductAdd.preview, PreviewCb.filter(F.action == "field"))
async def preview_field(call: CallbackQuery, callback_data: PreviewCb, state: FSMContext, lang: str) -> None:
    await call.answer()
    await state.update_data(editing=True)
    field = callback_data.field
    if field == "photos":
        draft = await get_draft(state)
        draft.media = []
        await save_draft(state, draft)
        await state.set_state(ProductAdd.photos)
        await call.message.answer(t("ask_photos", lang), reply_markup=kb.done_cancel(lang))
    elif field == "name":
        await ask_name(call.message, state, lang)
    elif field == "price":
        await ask_price(call.message, state, lang)
    elif field == "variants":
        await ask_variants(call.message, state, lang)
    else:
        await ask_description(call.message, state, lang)


@router.callback_query(ProductAdd.preview, PreviewCb.filter(F.action == "cancel"))
async def preview_cancel(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await call.answer()
    await call.message.answer(t("add_cancelled", lang), reply_markup=kb.main_menu(lang))


@router.callback_query(ProductAdd.preview, PreviewCb.filter(F.action == "publish"))
async def preview_publish(
    call: CallbackQuery, state: FSMContext, bot: Bot, session: AsyncSession, seller: Seller, lang: str
) -> None:
    draft = await get_draft(state)
    await state.clear()  # ikki marta bosilsa, ikkinchisi "eskirgan" bo'ladi
    await call.answer()
    product = await product_service.create_product(session, seller, draft)
    await session.commit()  # tovar albatta saqlansin, joylash muvaffaqiyatsiz bo'lsa ham

    channel = await channel_service.get_active_channel(session, seller.id)
    if channel is None:
        await call.message.answer(t("saved_no_channel", lang), reply_markup=kb.main_menu(lang))
        return
    await call.message.answer(t("publishing", lang))
    post = await publish_to_channel(bot, session, seller, product, channel)
    if post is None:
        await call.message.answer(t("publish_failed", lang), reply_markup=kb.main_menu(lang))
        return
    text = t("published", lang, title=escape(channel.title))
    link = post_link(channel, post.message_ids[0])
    if link:
        text += "\n" + t("published_link", lang, link=link)
    await call.message.answer(text, reply_markup=kb.main_menu(lang))


@router.message(ProductAdd.preview)
async def preview_text(message: Message, lang: str) -> None:
    await message.answer(t("edit_what", lang), reply_markup=kb.preview_actions(lang))
