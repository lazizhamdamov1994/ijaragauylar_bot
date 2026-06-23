import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8437972006:AAGuK0OAtIYeNZiNUv-94VVMtqh91d27bd0"
YOPIQ_KANAL_ID = -1001380301260
YOPIQ_KANAL_LINK = "https://t.me/+YOPIQ_KANAL_INVITE_LINK"  # Bu ni o'zgartiring!
# ====================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# E'lonlar ma'lumotlari - har bir e'lon uchun
elonlar = {
    "elon_1": {
        "manzil": "Qorasuv-2 | Prezident trassasi yaqinida",
        "narx": "$399 (depozit bilan)",
        "uy_egasi": "+998909300066",
        "sana": "23.06.2026"
    }
}

def azo_tekshirish_klaviatura(elon_id: str):
    """Tugmali klaviatura yaratish"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📞 Uy egasi raqamini olish",
            callback_data=f"raqam_{elon_id}"
        )
    ]])

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Salom! Men ijaraga uy e'lonlari botiman.\n\n"
        "📢 Ochiq kanal: @ijaraga_uylar\n"
        "🔐 Yopiq kanal: maxsus a'zolar uchun\n\n"
        "E'lon yuborish uchun: /elon"
    )

@dp.message(Command("elon"))
async def yuborish(message: types.Message):
    """Test uchun e'lon yuborish"""
    matn = (
        "🔓 <b>2 XONALI KVARTIRA</b>\n"
        "🚩 Qorasuv-2 | Prezident trassasi yaqinida\n"
        "👥 Oilaga\n"
        "🏫 2 xonali | 3-etaj\n"
        "🟢 Ta'mirlangan, toza va qulay joylashuv.\n"
        "Akademiya, Korzinka va Sadaf restorani yaqinida.\n\n"
        "💵 Narxi: $399 (depozit bilan)\n"
        "📅 Sana: 23.06.2026\n"
        "📩 Admin: @laziz_hamdamov\n\n"
        "⬇️ Uy egasi raqamini olish uchun tugmani bosing:"
    )
    await message.answer(
        matn,
        parse_mode="HTML",
        reply_markup=azo_tekshirish_klaviatura("elon_1")
    )

@dp.message(Command("kanalpost"))
async def kanal_post(message: types.Message):
    """Kanalga post yuborish (faqat admin uchun)"""
    matn = (
        "🔓 <b>2 XONALI KVARTIRA</b>\n"
        "🚩 Qorasuv-2 | Prezident trassasi yaqinida\n"
        "👥 Oilaga\n"
        "🏫 2 xonali | 3-etaj\n"
        "🟢 Ta'mirlangan, toza va qulay joylashuv.\n"
        "Akademiya, Korzinka va Sadaf restorani yaqinida.\n\n"
        "💵 Narxi: $399 (depozit bilan)\n"
        "📅 Sana: 23.06.2026\n"
        "📩 Admin: @laziz_hamdamov\n\n"
        "⬇️ Uy egasi raqamini olish uchun tugmani bosing:"
    )
    await bot.send_message(
        "@ijaraga_uylar",
        matn,
        parse_mode="HTML",
        reply_markup=azo_tekshirish_klaviatura("elon_1")
    )
    await message.answer("✅ Post kanalga yuborildi!")

@dp.callback_query(lambda c: c.data.startswith("raqam_"))
async def raqam_berish(callback: types.CallbackQuery):
    """Tugma bosilganda a'zolikni tekshirish"""
    user_id = callback.from_user.id
    elon_id = callback.data.replace("raqam_", "")

    try:
        member = await bot.get_chat_member(YOPIQ_KANAL_ID, user_id)

        if member.status in ["member", "administrator", "creator"]:
            # ✅ A'zo — raqamni yuborish
            elon = elonlar.get(elon_id, {})
            uy_raqam = elon.get("uy_egasi", "Ma'lumot topilmadi")

            await callback.answer("✅ Raqam yuborildi!", show_alert=False)
            await callback.message.answer(
                f"📞 <b>Uy egasi raqami:</b> <code>{uy_raqam}</code>\n\n"
                f"🏠 Qorasuv-2 | 2 xonali kvartira\n"
                f"💵 $399 (depozit bilan)\n\n"
                f"⚠️ Bu raqam faqat siz uchun yuborildi.",
                parse_mode="HTML"
            )
        else:
            # ❌ A'zo emas
            raise Exception("Not member")

    except Exception:
        # A'zo emas yoki xato
        klaviatura = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🔐 Yopiq kanalga a'zo bo'lish",
                url=YOPIQ_KANAL_LINK
            )
        ]])
        await callback.answer(
            "❌ Siz yopiq kanalga a'zo emassiz!",
            show_alert=True
        )
        await callback.message.answer(
            "🔐 <b>Uy egasi raqamini olish uchun</b>\n"
            "yopiq kanalimizga a'zo bo'lishingiz kerak!\n\n"
            "A'zo bo'lgach, tugmani qayta bosing. ✅",
            parse_mode="HTML",
            reply_markup=klaviatura
        )

async def main():
    print("✅ Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
