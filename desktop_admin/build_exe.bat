@echo off
REM Ijaraga Uylar - desktop admin dasturini .exe fayliga aylantirish.
REM Shu papka ICHIDA (desktop_admin\) ikki marta bosib ishga tushiring,
REM yoki "cmd" ochib shu papkaga kirib "build_exe.bat" deb yozing.

echo 1-qadam: kerakli kutubxonalar o'rnatilmoqda...
pip install -r requirements.txt
if errorlevel 1 (
    echo XATOLIK: kutubxonalarni o'rnatib bo'lmadi. Python va pip to'g'ri o'rnatilganini tekshiring.
    pause
    exit /b 1
)

echo.
echo 2-qadam: .exe fayl yasalmoqda (bir necha daqiqa davom etishi mumkin)...
pyinstaller --onefile --windowed --name "IjaragaUylarAdmin" app.py
if errorlevel 1 (
    echo XATOLIK: .exe yasashda muammo yuz berdi.
    pause
    exit /b 1
)

echo.
echo TAYYOR! .exe fayl shu yerda: dist\IjaragaUylarAdmin.exe
echo Uni istalgan joyga ko'chirib, ikki marta bosib ishga tushirishingiz mumkin.
pause
