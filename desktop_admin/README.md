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

## OLX'dan e'lon import qilish (TAVSIYA ETILGAN usul)

"Yangi e'lon" bo'limida **"\U0001F4C4 OLX HTML fayldan import"** tugmasi bor -
bu eng ishonchli usul:

1. OLX'dagi kerakli e'lonning O'ZINING sahifasini (ro'yxat emas, aniq
   e'lonning o'zi) brauzeringizda oching.
2. `Ctrl+S` bosing, "To'liq sahifa" / "Webpage, Complete" formatini
   tanlab, kompyuteringizga saqlang (`.html` fayl sifatida).
3. Desktop dasturda "OLX HTML fayldan import" tugmasini bosib, shu
   faylni tanlang.
4. Narx, tavsif va tuman maydonlari avtomatik to'ldiriladi, rasmlar
   ham avtomatik yuklab olinadi.
5. **Manzil, Xonalar soni va Telefon** maydonlarini albatta o'zingiz
   tekshirib/to'ldirib chiqing - OLX sahifasida bular yo'q (yoki aniq
   emas).

Bu usul OLX sahifasining ichidagi tayyor, tuzilgan ma'lumotdan (JSON-LD)
foydalanadi - shuning uchun sahifa tashqi ko'rinishi o'zgarsa ham odatda
ishlayveradi.

## OLX havolasidan rasm olish (zahira usul)

Shu bo'limdagi "OLX'dan rasm olish" tugmasi - faqat havolani kiritib,
rasmlarni topishga harakat qiladigan ESKI usul. HTML-fayl usuli
ishlamasa (masalan tarmoq cheklovi sabab) shuni sinab ko'ring, lekin u
umumiy taxminlarga asoslangani uchun har doim ishlashi kafolatlanmaydi.

Ikkala usul ham ishlamasa: rasmlarni oddiy qo'lda ("Kompyuterdan rasm
qo'shish" tugmasi orqali, avval OLX sahifasidan rasmlarni kompyuteringizga
saqlab) yuklashingiz mumkin - bu har doim ishlaydi.

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
