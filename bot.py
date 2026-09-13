"""
Ijaraga Uylar Maklersiz — Telegram bot kirish nuqtasi.
==========================================================================
Haqiqiy kod endi `bot/` papkasida, oqim bo'yicha bo'lingan fayllarda
(flow_listing.py, flow_quick.py, admin_panel.py, va h.k.). Bu fayl faqat
`bot/main.py`dagi main()ni chaqiradi - shuning uchun serverdagi ishga
tushirish buyrug'i o'zgarishsiz qoladi:

    python bot.py
"""
from bot.main import main

if __name__ == "__main__":
    main()
