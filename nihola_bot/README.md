# 🏠 Nihola Estate — Telegram bot

Rieltor uchun bot. U kanalga e’lon joylaydi, mijozlarni bazaga yig‘adi va mijozga mos uy chiqqanda unga avtomatik xabar beradi.
Python 3.10+ talab qilinadi. Bot **aiogram 3** va **SQLite** asosida ishlaydi (SQLite Python bilan birga keladi).

## Imkoniyatlar

**Admin (rieltor):**
- ➕ **Yangi e’lon.** Bot savollarni bitta-bitta beradi: tuman, qavat, xona, maydon, narx, rasm/video, lokatsiya. Keyin postni o‘zi yig‘ib, oldindan ko‘rsatadi. Har bir maydonni ✏️ tahrirlash mumkin.
- 📸 Rasmlarga avtomatik **“Nihola Estate” suv belgisi** qo‘yiladi va ular `media/` papkaga saqlanadi (keyinchalik web sayt uchun).
- 📍 **Lokatsiya.** Telegram joylashuvi, Google/Yandex xarita havolasi yoki koordinata (`41.28, 69.20`) qabul qilinadi. Koordinatalar bazaga yoziladi, keyinchalik saytdagi xaritada ishlatiladi.
- 📋 **E’lonlar.** Har bir e’lonni ✅ Sotildi, ⏸ Band yoki 💲 Narxni o‘zgartirish mumkin. Kanaldagi post avtomatik tahrirlanadi.
- 📊 **Statistika:** foydalanuvchilar, lidlar, eng ko‘p qidirilgan tumanlar, eng faol e’lonlar.
- 📣 **Ommaviy xabar:** botdagi barcha mijozlarga xabar yuborish.
- 🔥 **Lidlar.** Mijoz “Bog‘lanish”ni bossa, ismi, raqami, qaysi uy va filtri adminga (yoki `LEADS_CHAT_ID` guruhiga) keladi.
- 🏡 **Sotuvchi arizalari.** Uy egalari “Uyimni sotmoqchiman” orqali ariza qoldiradi.

**Kanal posti** ikki qismdan iborat: avval rasm/videolar albomi, keyin e’lon matni alohida xabar bo‘lib chiqadi. Matn ostida tugmalar bor (hammasi mijozni botga olib kiradi va bazaga qo‘shadi):

```
[📞 Bog‘lanish]      [🗺 Xaritada]
[❤️ Saqlash]         [🔔 O‘xshash uylar]
```

**Mijoz:**
- 🔔 **Filtr:** tuman, xonalar, byudjet. Mos uy joylansa bot **darhol** yoki **kuniga 1 marta** (kechqurun, dayjest) xabar beradi.
- ❤️ **Saqlanganlar.** Saqlangan uyning narxi tushsa yoki uy sotilsa, mijozga xabar boradi.
- 🔎 Uy qidirish, 📞 rieltor bilan bog‘lanish, 🏡 uyini sotish uchun ariza.

## 🌐 Web sayt

Sayt bot bilan **bitta bazadan** (`nihola.db`) va rasmlar papkasidan (`media/`) o‘qiydi. Botda joylangan e’lon saytda o‘zi paydo bo‘ladi.

- **Bosh sahifa.** Sotuv va Ijara tablari, chip-filtrlar (uy turi, tuman, xonalar, oxirgi hafta/oy), to‘liq filtr paneli (narx, maydon), qidiruv (tuman, majmua yoki `N0012` raqami), saralash, “Yangi e’lonlar” karuseli. E’lonlarni katta, panjara yoki ro‘yxat ko‘rinishida chiqarish mumkin.
- **E’lon sahifasi.** Galereya (rasm va video, telefonda barmoq bilan surish), xususiyatlar, xarita, “Telegramda bog‘lanish” (lid botga tushadi), qo‘ng‘iroq, saqlash, ulashish, o‘xshash e’lonlar.
- **🗺 Xarita** (`/xarita`). Har bir uy narx yorlig‘i bilan ko‘rinadi, yaqin uylar guruhlanadi.
- **❤️ Sevimlilar.** Brauzerda saqlanadi.
- **Qo‘shimcha:** ipoteka kalkulyatori, o‘zbek va rus tillari, tungi rejim, telefon uchun pastki menyu, `sitemap.xml` (Google uchun).

Ishga tushirish (bot ishlab turgan holda, **ikkinchi** cmd oynasida):

```bash
.venv\Scripts\activate
python web.py
```

Brauzerda **http://localhost:8000** manzilini oching.

## O‘rnatish (noutbukda sinash)

1. **@BotFather** → `/newbot` buyrug‘i bilan bot yarating va tokenni oling.
2. Botni **Nihola Estate kanaliga admin** qilib qo‘shing (“Post messages” va “Edit messages of others” huquqlari bilan).
3. O‘z Telegram ID’ingizni **@userinfobot** dan bilib oling.
4. Terminalda quyidagilarni bajaring:

```bash
cd nihola_bot
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

5. `.env` faylini oching va `BOT_TOKEN`, `CHANNEL_ID`, `ADMIN_IDS`, `REALTOR_PHONE` qiymatlarini to‘ldiring.
6. Botni ishga tushiring:

```bash
python run.py
```

7. Botga `/start` yozing. Siz admin bo‘lganingiz uchun admin menyusi ochiladi. **➕ Yangi e’lon** tugmasini bosing.

Mijoz sifatida sinash uchun **👤 Mijoz menyusi** tugmasini bosing.

## Admin buyruqlari

| Buyruq | Vazifa |
|---|---|
| `/admin` | Admin panel |
| `/new` | Yangi e’lon |
| `/e 12` | 12-e’lonni ochish (sotildi / narx) |
| `/stats` | Statistika |
| `/tekshir` | Bot kanalga post joylay olishini tekshirish |

## Fayllar

```
nihola_bot/
├── run.py                  # botni ishga tushirish
├── web.py                  # saytni ishga tushirish (http://localhost:8000)
├── web/                    # sayt: app.py, data.py, i18n.py, templates/, static/
├── app/
│   ├── config.py           # .env sozlamalari
│   ├── db.py               # SQLite jadvallari va so‘rovlar
│   ├── texts.py            # kanal posti formati
│   ├── keyboards.py        # tugmalar
│   ├── posting.py          # kanalga joylash / postni tahrirlash
│   ├── notifier.py         # xabarnomalar, ommaviy xabar, kunlik dayjest
│   ├── matching.py         # filtr ↔ e’lon solishtirish
│   ├── media.py            # suv belgisi, diskka saqlash
│   ├── geo.py              # xarita havolasidan koordinata olish
│   └── handlers/
│       ├── admin_new.py    # e’lon yaratish ustasi
│       ├── admin_manage.py # ro‘yxat, sotildi, narx, statistika, ommaviy xabar
│       └── user.py         # mijoz tomoni
```

## Serverga qo‘yishda

- `nihola.db` va `media/` papkasini saqlab qo‘ying, chunki baza va rasmlar shu yerda turadi.
- Botni `systemd` yoki `pm2` orqali doimiy ishlaydigan qilib qo‘ying.
- Web sayt keyinroq **shu bazani** (`listings`, `listing_media`, `lat/lng`) o‘qiydi.
