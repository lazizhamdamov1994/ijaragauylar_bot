@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Seus bot

if not exist ".env" (
  echo [XATO] .env fayli topilmadi.
  echo .env.example faylidan nusxa olib, nomini .env qiling va BOT_TOKEN hamda DB_PASSWORD ni yozing.
  echo Batafsil: README.md, 3-qadam.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Birinchi ishga tushirish: virtual muhit yaratilmoqda...
  py -3.13 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo [XATO] Python 3.13 topilmadi. README.md dagi 0-qadamni ko'ring.
  pause
  exit /b 1
)

echo Kutubxonalar tekshirilmoqda...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo [XATO] Kutubxonalarni o'rnatib bo'lmadi. Internetni tekshiring.
  pause
  exit /b 1
)

echo Baza jadvallari tekshirilmoqda...
".venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 (
  echo [XATO] Bazaga ulanib bo'lmadi. PostgreSQL ishlayaptimi va .env dagi DB_ qiymatlar to'g'rimi?
  pause
  exit /b 1
)

echo.
echo Bot ishga tushmoqda. To'xtatish uchun shu oynada Ctrl+C bosing.
echo.
".venv\Scripts\python.exe" -m app.bot
pause
