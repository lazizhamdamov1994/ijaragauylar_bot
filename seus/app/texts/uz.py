# Barcha matnlar shu yerda. {nom} — o'rniga qiymat qo'yiladigan joy.
# Matnlar HTML formatida (<b>qalin</b>, <i>qiya</i>).

TEXTS: dict[str, str] = {
    # ---- Umumiy ----
    "error_generic": "😔 Kechirasiz, xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring.",
    "unknown_command": "Tushunmadim 🤔 Pastdagi menyudan foydalaning.",
    "not_registered": "Avval ro'yxatdan o'ting: /start",
    "cancelled": "❌ Bekor qilindi.",
    "btn_cancel": "❌ Bekor qilish",
    "btn_back": "⬅️ Orqaga",
    "btn_done": "✅ Tayyor",
    "btn_skip": "⏭ O'tkazib yuborish",

    # ---- Ro'yxatdan o'tish ----
    "welcome_new": (
        "👋 Assalomu alaykum! <b>Seus</b> — kiyim-kechak sotuvchilari uchun yordamchi bot.\n\n"
        "Bu yerda tovar qo'shasiz, bot uni kanalingizga chiroyli qilib joylaydi, "
        "xaridorlar esa buyurtmani bot orqali beradi.\n\n"
        "Ro'yxatdan o'tamiz. <b>Do'koningiz nomini</b> yozing:"
    ),
    "welcome_back": "👋 Xush kelibsiz, <b>{shop}</b>! Kerakli bo'limni tanlang:",
    "shop_name_invalid": "Do'kon nomi 2 dan 100 gacha belgidan iborat bo'lsin. Qayta yozing:",
    "ask_phone": (
        "📱 Endi telefon raqamingizni yuboring.\n"
        "Pastdagi <b>«📱 Raqamni yuborish»</b> tugmasini bosing."
    ),
    "btn_send_phone": "📱 Raqamni yuborish",
    "phone_use_button": "Iltimos, raqamni pastdagi <b>«📱 Raqamni yuborish»</b> tugmasi orqali yuboring.",
    "phone_not_yours": "Bu boshqa odamning raqami. O'zingizning raqamingizni tugma orqali yuboring.",
    "registered": (
        "🎉 Tabriklaymiz, <b>{shop}</b> ro'yxatdan o'tdi!\n\n"
        "Keyingi qadam — <b>kanalingizni ulang</b>: «📢 Kanalim» tugmasini bosing."
    ),

    # ---- Menyu ----
    "btn_add_product": "➕ Tovar qo'shish",
    "btn_my_products": "📦 Tovarlarim",
    "btn_my_channel": "📢 Kanalim",
    "btn_orders": "🧾 Buyurtmalar",
    "menu": "Asosiy menyu:",

    # ---- Kanal ----
    "channel_none": (
        "📢 Sizda hali ulangan kanal yo'q.\n\n"
        "<b>Kanalni ulash uchun:</b>\n"
        "1️⃣ Kanalingiz sozlamalariga kiring → <b>Administratorlar</b> → <b>Admin qo'shish</b>.\n"
        "2️⃣ Qidiruvga <b>@{bot}</b> deb yozing va botni tanlang.\n"
        "3️⃣ <b>«Xabarlarni joylash»</b> (Post messages) huquqini yoqing va saqlang.\n"
        "4️⃣ Shu yerga kanal username'ini yuboring (masalan <code>@mening_kanalim</code>) "
        "yoki kanaldan istalgan xabarni shu botga <b>forward</b> qiling."
    ),
    "channel_current": (
        "📢 Ulangan kanal: <b>{title}</b> {username}\n\n"
        "Boshqa kanal ulamoqchi bo'lsangiz, uning username'ini yuboring yoki kanaldan xabar forward qiling."
    ),
    "channel_checking": "⏳ Kanal tekshirilmoqda...",
    "channel_bad_input": (
        "Bu kanal username'iga o'xshamaydi. Masalan: <code>@mening_kanalim</code>\n"
        "Yoki kanaldan xabarni forward qiling."
    ),
    "channel_not_found": (
        "❌ Kanal topilmadi yoki bot unga qo'shilmagan.\n\n"
        "Tekshiring:\n• username to'g'ri yozilganmi;\n"
        "• bot (@{bot}) kanalga <b>administrator</b> qilib qo'shilganmi.\n\n"
        "Yopiq (private) kanal bo'lsa — kanaldan xabarni forward qiling."
    ),
    "channel_not_channel": "❌ Bu kanal emas (guruh yoki shaxsiy chat). Iltimos, <b>kanal</b> yuboring.",
    "channel_bot_not_admin": (
        "❌ Bot kanalda administrator emas.\n\n"
        "Kanal → Administratorlar → Admin qo'shish → @{bot} → «Xabarlarni joylash» huquqini yoqing. "
        "Keyin qayta yuboring."
    ),
    "channel_bot_cannot_post": (
        "❌ Bot kanalda admin, lekin unda <b>«Xabarlarni joylash»</b> huquqi yo'q.\n\n"
        "Kanal → Administratorlar → @{bot} → «Xabarlarni joylash»ni yoqing va qayta yuboring."
    ),
    "channel_user_not_admin": (
        "❌ Siz bu kanalning egasi yoki administratori emassiz. "
        "Faqat o'z kanalingizni ulay olasiz."
    ),
    "channel_taken": "❌ Bu kanal boshqa sotuvchiga ulangan.",
    "channel_linked": "✅ Kanal ulandi: <b>{title}</b>\nEndi tovarlaringiz shu kanalga joylanadi.",

    # ---- Tovar qo'shish ----
    "ask_photos": (
        "📸 Tovar <b>rasm yoki videolarini</b> yuboring (jami 1 dan 10 tagacha).\n"
        "Bir nechtasini bitta albom qilib yuborsangiz ham bo'ladi.\n"
        "Tugatgach <b>«✅ Tayyor»</b> tugmasini bosing."
    ),
    "photos_added": "🖼 Rasm/video: <b>{count}</b>/10 (📷 {photos}, 🎬 {videos}). Yana yuboring yoki «✅ Tayyor»ni bosing.",
    "photos_limit": "⚠️ Ko'pi bilan 10 ta rasm/video. Ortiqchalari qabul qilinmadi.",
    "photos_need_one": "Kamida bitta rasm yoki video yuboring.",
    "photos_only": "Iltimos, rasm yoki video yuboring (fayl/hujjat sifatida emas).",
    "ask_name": "✏️ Tovar nomini yozing (masalan: <i>Erkaklar ko'ylagi, paxta</i>):",
    "name_invalid": "Nom 2 dan 200 gacha belgidan iborat bo'lsin. Qayta yozing:",
    "ask_price": "💰 Narxini so'mda yozing (masalan: <code>250000</code> yoki <code>250 000</code>):",
    "price_invalid": "Narxni tushuna olmadim. Faqat raqam yozing, masalan: <code>250000</code>",
    "ask_variants": (
        "📏 Razmer, rang va sonini kiriting.\n\n"
        "<b>1-usul:</b> yozib yuboring, har bir qatorga bittadan:\n"
        "<code>S qora 5\nM qora 3\nL oq 2</code>\n\n"
        "<b>2-usul:</b> «➕ Tugmalar bilan qo'shish»ni bosing.\n\n"
        "Razmer/rang bo'lmasa — shunchaki sonini yozing (masalan <code>10</code>)."
    ),
    "variants_current": "📏 <b>Hozirgi ro'yxat:</b>\n{list}\n\nYana qo'shing yoki «✅ Tayyor»ni bosing.",
    "variants_empty": "(hali bo'sh)",
    "variants_parse_error": "⚠️ Bu qatorlarni tushunmadim:\n{lines}\n\nNamuna: <code>S qora 5</code>",
    "variants_need_one": "Kamida bitta razmer/rang yoki sonini kiriting.",
    "btn_variant_wizard": "➕ Tugmalar bilan qo'shish",
    "btn_variant_undo": "🗑 Oxirgisini o'chirish",
    "choose_size": "Razmerni tanlang (yoki yozing):",
    "choose_color": "Rangni tanlang (yoki yozing):",
    "choose_qty": "Sonini tanlang (yoki yozing):",
    "btn_no_size": "Razmersiz",
    "btn_no_color": "Rangsiz",
    "qty_invalid": "Son 0 dan 100000 gacha bo'lsin.",
    "ask_description": "📝 Tavsif yozing (mato, ishlab chiqaruvchi, parvarish...). Ixtiyoriy:",
    "description_too_long": "Tavsif 2000 belgidan oshmasin.",
    "preview_title": "👀 <b>Oldindan ko'rish.</b> Kanalda shunday ko'rinadi:",
    "btn_publish": "📢 Kanalga joylash",
    "btn_edit": "✏️ Tahrirlash",
    "edit_what": "Nimani o'zgartiramiz?",
    "btn_edit_photos": "🖼 Rasm/video",
    "btn_edit_name": "✏️ Nom",
    "btn_edit_price": "💰 Narx",
    "btn_edit_variants": "📏 Razmer/rang",
    "btn_edit_description": "📝 Tavsif",
    "add_cancelled": "❌ Tovar qo'shish bekor qilindi.",
    "session_expired": "Bu amal eskirgan. Qaytadan boshlang.",

    # ---- Joylash ----
    "publishing": "⏳ Kanalga joylanmoqda...",
    "published": "✅ Tovar kanalga joylandi: <b>{title}</b>",
    "published_link": "🔗 Post: {link}",
    "saved_no_channel": (
        "💾 Tovar saqlandi, lekin sizda ulangan kanal yo'q.\n"
        "«📢 Kanalim» orqali kanal ulang, keyin «📦 Tovarlarim»dan joylaysiz."
    ),
    "publish_failed": (
        "⚠️ Tovar saqlandi, lekin kanalga joylab bo'lmadi.\n"
        "Bot kanalda admin ekanini va «Xabarlarni joylash» huquqi borligini tekshiring, "
        "so'ng «📦 Tovarlarim»dan qayta joylang."
    ),

    # ---- Post matni ----
    "post_price": "💰 Narxi: <b>{price} so'm</b>",
    "post_variants_title": "📏 Mavjud:",
    "post_out_of_stock": "❗️ Hozircha tugagan",
    "post_shop": "🏪 {shop}",
    "btn_order": "🛒 Buyurtma berish",
    "btn_contact_seller": "📞 Sotuvchi bilan bog'lanish",
    "post_buttons_text": "👆 <b>{name}</b> — {price} so'm\nBuyurtma berish uchun pastdagi tugmani bosing 👇",

    # ---- Tovarlarim ----
    "my_products_empty": "📦 Sizda hali tovar yo'q. «➕ Tovar qo'shish»ni bosing.",
    "my_products_title": "📦 <b>Tovarlaringiz</b> ({count} ta). Birini tanlang:",
    "product_inactive_mark": "🚫",
    "btn_deactivate": "🚫 Sotuvdan olish",
    "btn_activate": "✅ Sotuvga qaytarish",
    "product_not_found": "Tovar topilmadi yoki o'chirilgan.",
    "product_deactivated": "🚫 Tovar sotuvdan olindi.",
    "product_activated": "✅ Tovar yana sotuvda.",
    "product_posted_times": "📢 Kanalga joylangan: {count} marta",

    # ---- Xaridor ----
    "buyer_welcome": (
        "👋 Assalomu alaykum! Bu <b>Seus</b> — do'konlar boti.\n"
        "Kanallardagi «🛒 Buyurtma berish» tugmasi orqali tovarlarni ko'rishingiz mumkin."
    ),
    "buyer_product_unavailable": "😔 Bu tovar hozir sotuvda yo'q.",
    "seller_contact": "🏪 <b>{shop}</b>\n📞 Telefon: {phone}",
    "seller_contact_username": "💬 Telegram: @{username}",

    # ---- Buyurtma (xaridor) ----
    "order_choose_variant": "👇 Razmer/rangni tanlang:",
    "order_variant_btn": "{variant} ({stock} ta)",
    "order_choose_qty": "🔢 Nechta olasiz? (<b>{variant}</b>, mavjud: {stock} ta)\nTugmani bosing yoki sonini yozing:",
    "order_qty_invalid": "Son 1 dan {max} gacha bo'lsin.",
    "order_not_enough_stock": "😔 Kechirasiz, bu razmerdan faqat {stock} ta qoldi.",
    "order_variant_gone": "😔 Bu razmer endi mavjud emas. Boshqasini tanlang.",
    "order_ask_phone": "📱 Telefon raqamingizni yuboring (tugma orqali yoki yozib, masalan <code>+998901234567</code>):",
    "order_phone_invalid": "Raqamni tushunmadim. Masalan: <code>+998901234567</code> yoki tugmani bosing.",
    "order_ask_address": "📍 Yetkazib berish manzilini yozing (shahar, ko'cha, uy):",
    "order_address_invalid": "Manzil 5 dan 500 gacha belgidan iborat bo'lsin.",
    "order_ask_comment": "💬 Sotuvchiga izoh (ixtiyoriy). Masalan: qo'ng'iroq qilish vaqti.",
    "order_confirm_title": "✅ <b>Buyurtmani tekshiring:</b>",
    "btn_order_send": "✅ Buyurtmani yuborish",
    "order_created_buyer": (
        "🎉 Buyurtmangiz qabul qilindi! <b>№{number}</b>\n"
        "Sotuvchi tez orada siz bilan bog'lanadi."
    ),
    "order_cancelled_flow": "❌ Buyurtma bekor qilindi.",
    "order_status_changed_buyer": "🔔 Buyurtma <b>№{number}</b> holati: {status}",

    # ---- Buyurtma (sotuvchi) ----
    "order_new_seller": "🔔 <b>Yangi buyurtma!</b>\n\n{text}",
    "order_title": "🧾 <b>Buyurtma №{number}</b>",
    "order_item_line": "👗 {name} — {variant} × {qty} ({price} so'm)",
    "order_total_line": "💰 Jami: <b>{total} so'm</b>",
    "order_buyer_line": "👤 {name}",
    "order_phone_line": "📞 {phone}",
    "order_address_line": "📍 {address}",
    "order_comment_line": "💬 {comment}",
    "order_status_line": "Holati: {status}",
    "order_status_new": "🆕 Yangi",
    "order_status_confirmed": "✅ Tasdiqlangan",
    "order_status_shipped": "🚚 Yo'lda",
    "order_status_delivered": "📦 Yetkazildi",
    "order_status_cancelled": "❌ Bekor qilingan",
    "btn_status_confirmed": "✅ Tasdiqlash",
    "btn_status_shipped": "🚚 Jo'natildi",
    "btn_status_delivered": "📦 Yetkazildi",
    "btn_status_cancelled": "❌ Bekor qilish",
    "btn_write_buyer": "💬 Xaridorga yozish",
    "order_status_updated": "Holat yangilandi: {status}",
    "order_status_not_allowed": "Bu buyurtma holatini endi o'zgartirib bo'lmaydi.",
    "order_not_found": "Buyurtma topilmadi.",
    "orders_empty": "🧾 Hozircha buyurtmalar yo'q.",
    "orders_title": "🧾 <b>Buyurtmalar</b> ({count} ta). Birini tanlang:",
}
