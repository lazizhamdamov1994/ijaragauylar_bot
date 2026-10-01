"""
Windows desktop admin dasturi uchun token-asosli autentifikatsiya.

Brauzer sessiya-cookie tizimidan (web/auth.py) farqli o'laroq, desktop
dastur HTTP so'rovlarida "Authorization: Bearer <token>" sarlavhasini
yuboradi. Token botdagi /desktop_token buyrug'i orqali BIR MARTA olinadi
(bot/admin_panel.py'ga qarang) va dasturga qo'lda kiritiladi.
"""
import logging
import secrets

from common.db import db, now_str

logger = logging.getLogger(__name__)


def create_desktop_token(user_id: int) -> str:
    """Admin uchun yangi token yaratadi (eskisini bekor qilmaydi - bir
    nechta qurilmada ishlatish mumkin)."""
    token = secrets.token_urlsafe(32)
    conn = db()
    conn.execute(
        "INSERT INTO desktop_tokens (user_id, token, created_at) VALUES (?, ?, ?)",
        (user_id, token, now_str()),
    )
    conn.commit()
    conn.close()
    return token


def resolve_desktop_token(token: str):
    """Token haqiqiy bo'lsa - user_id qaytaradi (va so'nggi ishlatilgan
    vaqtni yangilaydi), aks holda None."""
    if not token:
        return None
    conn = db()
    row = conn.execute("SELECT user_id FROM desktop_tokens WHERE token = ?", (token,)).fetchone()
    if row:
        conn.execute("UPDATE desktop_tokens SET last_used_at = ? WHERE token = ?", (now_str(), token))
        conn.commit()
    conn.close()
    return row["user_id"] if row else None


def revoke_desktop_tokens(user_id: int) -> int:
    """Shu adminning BARCHA tokenlarini bekor qiladi (masalan, kompyuter
    yo'qolsa/o'g'irlansa). Nechta token o'chirilganini qaytaradi."""
    conn = db()
    cur = conn.execute("DELETE FROM desktop_tokens WHERE user_id = ?", (user_id,))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n
