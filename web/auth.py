"""
Autentifikatsiya - ADMIN PANEL uchun oddiy parol (HTTP Basic) va veb-sayt
foydalanuvchilari uchun Telegram Login Widget orqali kirish (shaxsiy kabinet).
"""
import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

import json as _json

from common.config import BOT_TOKEN, DASH_PASS, DASH_USER, SESSION_COOKIE, SESSION_MAX_AGE, SESSION_SECRET
from common.db import is_subscribed

security = HTTPBasic()

_failed_attempts: dict = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
BLOCK_SECONDS = 900


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_auth(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    ip = _client_ip(request)
    now = time.time()
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if now - t < BLOCK_SECONDS]
    if len(_failed_attempts[ip]) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Juda ko'p noto'g'ri urinish. 15 daqiqadan keyin qayta urinib ko'ring.")
    correct_user = secrets.compare_digest(credentials.username, DASH_USER)
    correct_pass = secrets.compare_digest(credentials.password, DASH_PASS)
    if not (correct_user and correct_pass):
        _failed_attempts[ip].append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login yoki parol noto'g'ri",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# db(), now_str(), safe_parse_dt(), get_setting(), is_subscribed(),
# is_phone_blocked() - endi common/db.py'da BITTA joyda (bot.py bilan
# umumiy). Pastroqda import qilingan.

# ============================= TELEGRAM ORQALI KIRISH (shaxsiy kabinet) =============================
#
# Telegram Login Widget (https://core.telegram.org/widgets/login) botning
# domeniga (@BotFather -> /setdomain) bog'lanadi. Foydalanuvchi vidjetda
# "Log in with Telegram" bosgach, Telegram uni id/ism/username/auth_date va
# shu ma'lumotlarning BOT_TOKEN bilan hisoblangan HMAC-SHA256 xeshi (hash)
# bilan birga /auth/telegram-callback ga qaytaradi - biz shu xeshni QAYTA
# hisoblab, mos kelishini tekshiramiz (soxtalashtirib bo'lmaydi, chunki
# BOT_TOKEN faqat bizda va Telegram serverida bor). Shundan keyingina
# o'zimiz imzolagan xavfsiz cookie o'rnatiladi - parol/sessiya bazasi shart emas.

def verify_telegram_auth(params: dict) -> bool:
    if not BOT_TOKEN:
        return False
    check_hash = params.get("hash")
    if not check_hash:
        return False
    data = {k: v for k, v in params.items() if k not in ("hash", "next")}
    data_check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, check_hash):
        return False
    try:
        auth_date = int(data.get("auth_date", 0))
    except (TypeError, ValueError):
        return False
    if time.time() - auth_date > 86400:
        return False
    return True


def create_session_token(uid: int, first_name: str, username: str) -> str:
    payload = {"uid": uid, "fn": first_name or "", "un": username or "", "iat": int(time.time())}
    raw = _json.dumps(payload, separators=(",", ":")).encode()
    b64 = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = hmac.new(SESSION_SECRET.encode(), b64.encode(), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_session_token(token: str):
    try:
        b64, sig = token.rsplit(".", 1)
        expected = hmac.new(SESSION_SECRET.encode(), b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        pad = "=" * (-len(b64) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(b64 + pad))
        if time.time() - payload.get("iat", 0) > SESSION_MAX_AGE:
            return None
        return payload
    except Exception:
        return None


def get_current_tg_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return verify_session_token(token)


# is_web_subscribed() nomi eskisi bilan qoldirilgan (ko'plab joyda
# ishlatiladi), lekin endi common/db.py'dagi umumiy is_subscribed()ning o'zi.
is_web_subscribed = is_subscribed



