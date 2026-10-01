# Ijaraga Uylar - Windows Desktop Admin Dasturi

Windows kompyuteringizdan to'g'ridan-to'g'ri:
- Yangi e'lon joylash (mahalliy rasmlar yoki OLX havolasidan)
- Kutilayotgan e'lon/obuna so'rovlarini tasdiqlash/rad etish
- Asosiy statistikani ko'rish

## .exe faylni yasash (bir martalik sozlash)

1. Agar kompyuteringizda Python o'rnatilmagan bo'lsa - https://python.org dan
   yuklab o'rnating ("Add python.exe to PATH" katagini belgilashni unutmang).
2. Bu `desktop_admin` papkasini kompyuteringizga ko'chiring.
3. Papka ichida `build_exe.bat` faylini ikki marta bosing.
4. Bir necha daqiqadan keyin `dist\IjaragaUylarAdmin.exe` fayli tayyor bo'ladi.
5. Shu `.exe` faylni istalgan joyga (masalan ish stoliga) ko'chirib, undan
   keyin shu bitta faylni ishlatavering - boshqa hech narsa kerak emas.

**Diqqat**: `.exe` faylni albatta WINDOWS kompyuterda yasash kerak (PyInstaller
dastur ishga tushirilayotgan kompyuterning operatsion tizimi uchun `.exe`
yasaydi) - shuning uchun bu qadamni Laziz o'zi, o'z Windows 10
kompyuterida bajarishi kerak.

## Birinchi marta ishga tushirish

1. `.exe` faylni ikki marta bosing.
2. "Sozlamalar" bo'limida:
   - **Server manzili**: saytingiz manzili (masalan `https://ijaragauylar.uz`)
   - **Token**: Telegram botga (admin sifatida) `/desktop_token` buyrug'ini
     yuboring - bot sizga shaxsiy xabarda token yuboradi, uni shu yerga
     nusxalang.
3. "Saqlash va tekshirish" tugmasini bosing - "✅ Ulandi: ..." deb chiqsa,
   hammasi tayyor.

Token kompyuteringizda saqlanadi (`%USERPROFILE%\.ijaragauylar_admin_config.json`)
- keyingi safar qayta kiritish shart emas.

## Agar token "o'g'irlangan" deb o'ylasangiz

Botga `/desktop_token_revoke` buyrug'ini yuboring - bu BARCHA eski
tokenlaringizni bekor qiladi. Keyin `/desktop_token` bilan yangisini oling.

## OLX'dan rasm olish haqida muhim eslatma

"Yangi e'lon" bo'limidagi "OLX'dan rasm olish" tugmasi OLX e'lon sahifasidan
rasmlarni avtomatik topishga harakat qiladi. Bu funksiya **tekshirilmagan**
holda yuborilgan - chunki ishlab chiqish muhitida olx.uz saytiga tarmoq
ulanishi yo'q edi. Agar ishlamasa yoki noto'g'ri ishlasa:

- Rasmlarni oddiy qo'lda ("Kompyuterdan rasm qo'shish" tugmasi orqali,
  avval OLX sahifasidan rasmlarni kompyuteringizga saqlab) yuklashingiz
  mumkin - bu har doim ishlaydi.
- Menga aniq qaysi OLX havolasida ishlamaganini ayting - men xatoni tuzataman.

## Nusxa ko'chirish/joylashtirish (Ctrl+V) ishlamasa

Agar kompyuteringizda rus/o'zbek kirill klaviatura tartibi o'rnatilgan bo'lsa,
dastur ichida Ctrl+V/Ctrl+C ishlamasligi mumkin edi - bu Windows'dagi
Tkinter'ning mashhur muammosi (standart bog'lanish harfning o'ziga, klaviatura
tartibiga esa bog'liq). Bu versiyada klaviatura tartibidan mustaqil ishlaydigan
maxsus tuzatish qo'shilgan - Ctrl+V/C/X endi qaysi til tartibida bo'lishidan
qat'iy nazar ishlaydi.

## Fayllar

- `app.py` - asosiy dastur (CustomTkinter GUI, saytdagi korall brend
  palitrasiga mos zamonaviy dizayn)
- `api_client.py` - serverga ulanish mantiqi (GUI'dan mustaqil)
- `app_icon.ico` - dastur ikonkasi (.exe fayl va oyna uchun)
- `requirements.txt` - kerakli Python kutubxonalari
- `build_exe.bat` - `.exe` yasash skripti
