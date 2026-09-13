"""
Ijaraga Uylar Maklersiz - veb-server kirish nuqtasi.
==========================================================================
Haqiqiy kod endi `web/` papkasida, mavzu bo'yicha bo'lingan fayllarda
(pages.py, account.py, api.py, admin_page.py, map_page.py, va h.k.).
Bu fayl faqat ularni yig'adigan `web.app.app`ni ochib beradi - shuning
uchun serverdagi ishga tushirish buyrug'i o'zgarishsiz qoladi:

    uvicorn dashboard:app --host 0.0.0.0 --port 8001
"""
from web.app import app

__all__ = ["app"]
