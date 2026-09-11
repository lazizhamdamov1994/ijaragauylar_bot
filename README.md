# 🏠 Ijaraga Uylar Maklersiz — Telegram bot + Veb-sayt

Maklersiz uy/kvartira ijarasi platformasi: **Telegram bot** (e'lon joylash, moderatsiya,
to'lov, xarita, "Limit" obunasi) + **veb-sayt** (SEO'lanadigan ommaviy sahifa, o'z-o'zidan
e'lon joylash, interaktiv xarita, admin boshqaruv paneli). Ikkalasi bitta SQLite bazasini
baham ko'radi va bir-biriga to'liq integratsiya qilingan: **botdagi e'lon — saytda,
saytdagi e'lon — botda/kanalda** ko'rinadi.

## ⚠️ MUHIM — xavfsizlik

Ushbu repodagi **eski** `bot.py` faylida bot tokeni ochiq matnda yozilgan edi va bu
holatda GitHub tarixiga tushib qolgan bo'lishi mumkin. **Shu tokenni @BotFather orqali
`/revoke` qiling va yangisini oling** — eski token endi ishonchsiz hisoblanadi, undan
qanday hech kim foydalanmasin siz nazorat qila olmaysiz. Yangi kod tokenni **faqat**
`.env` faylidan o'qiydi (`.env` esa `.gitignore`'da — hech qachon commit qilinmaydi).

## Arxitektura

```
┌─────────────┐      bitta SQLite baza       ┌──────────────────┐
│   bot.py    │ <───────────────────────────> │   dashboard.py    │
│ (Telegram)  │      (elonlar.db)              │  (FastAPI, veb)   │
└─────────────┘                                └──────────────────┘
      │                                                  │
      │  admin tasdiqlash/rad etish tugmalari             │  saytdan yuborilgan e'lon uchun ham
      │  (callback_data: admin_approve_listing_ID)        │  xuddi shu tugmalarni Telegram Bot API
      │                                                    │  orqali to'g'ridan-to'g'ri yuboradi
      └──────────────── bitta bot, ikkita jarayon ─────────┘
```

- **`bot.py`** — asosiy Telegram bot (python-telegram-bot). E'lon berish, moderatsiya,
  to'lov (chek orqali), "Limit" (obuna), xarita/lokatsiya, statistika, admin buyruqlari.
- **`dashboard.py`** — mustaqil FastAPI veb-server. Ommaviy sayt (`/`), e'lon sahifalari
  (`/uy/{id}`), veb-saytdan e'lon berish (`/elon-joylash`), interaktiv xarita (`/xarita`),
  parol bilan himoyalangan admin panel (`/admin`).
- Ikkalasi ham **bitta** `elonlar.db` SQLite faylini o'qiydi/yozadi — hech qanday API
  orqali gaplashishmaydi, faqat baza orqali va Telegram Bot API orqali (admin xabarnomalar
  uchun) bog'lanadi.

## Asosiy imkoniyatlar

- 📝 E'lon berish — botdan **va** veb-saytdan (`/elon-joylash`), ikkalasi ham bitta
  moderatsiya navbatiga tushadi va tasdiqlangach **kanalga ham, saytga ham** chiqadi.
- 💰 Bepul va pullik e'lonlar — **pullik e'lon uy "topshirildi" deb belgilanmaguncha**
  kanalda muntazam qayta joylanadi (har 3 soatda) va saytda doim ro'yxat boshida turadi.
- 🗺️ Kuchli interaktiv xarita — klasterlash, toifa bo'yicha rangli belgilar, filtr,
  "mening joyim" geolokatsiya, fotosuratli popup kartochkalar.
- 🌍 Veb-sayt **o'zbek / rus / ingliz** tillarida (yuqori o'ng burchakdagi til tugmasi).
- 📊 To'liq statistika: tashriflar, konversiya, daromad, xarita orqali qiziqish.
- 🔐 Admin panel: moderatsiya, bloklangan raqamlar, moderatorlar, sozlamalar.

## O'rnatish

### 1. `.env` faylini tayyorlang

```bash
cp .env.example .env
```

`.env` faylini oching va kamida quyidagilarni to'ldiring:

| O'zgaruvchi | Tavsif |
|---|---|
| `BOT_TOKEN` | @BotFather'dan olingan **yangi** token |
| `CHANNEL_ID` | E'lonlar chiqadigan kanal ID'si (masalan `-1001234567890`) |
| `CHANNEL_USERNAME` | Kanal username'i (ochiq bo'lsa) |
| `ADMIN_IDS` | Sizning Telegram `user_id`ingiz (bir nechta bo'lsa vergul bilan) |
| `ADMIN_USERNAME` | Sizning @username'ingiz |
| `DASHBOARD_URL` | Sayt joylashadigan HTTPS manzil (masalan `https://ijaragauylar.uz`) |
| `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` | `/admin` panelga kirish uchun |
| `CARD_NUMBER` / `CARD_HOLDER` | To'lov qabul qilinadigan karta |

### 2. Kutubxonalarni o'rnating

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Botni admin/kanalga qo'shing

Botni kanalga (yoki yopiq guruhga) **administrator** sifatida qo'shing — xabar
joylash huquqi bilan.

### 4. Ikkala jarayonni ishga tushiring

```bash
# 1-terminal — Telegram bot
python bot.py

# 2-terminal — veb-sayt
uvicorn dashboard:app --host 0.0.0.0 --port 8001
```

Ishga tushgach `logo.png` faylini repo papkasiga qo'ying (sayt logotipi/favicon uchun) —
bo'lmasa ham sayt ishlayveradi, faqat logotipsiz.

## Deploy (Railway / shunga o'xshash)

Bot va sayt — **ikkita alohida jarayon**, shuning uchun Railway'da **ikkita xizmat**
(service) yarating, ikkalasi ham shu bitta repoga ulangan holda:

1. **"bot" xizmati** — `railway.toml`dagi standart buyruq ishlatiladi: `python bot.py`
2. **"web" xizmati** — Railway loyihasida yangi xizmat qo'shing, "Deploy from same repo",
   so'ng Settings → Deploy → Custom Start Command ga qo'ying:
   ```
   uvicorn dashboard:app --host 0.0.0.0 --port $PORT
   ```
   va "Generate Domain" bilan ommaviy HTTPS manzil oling — shu manzilni `.env`dagi
   `DASHBOARD_URL`ga yozing (ikkala xizmatga ham bir xil `.env` o'zgaruvchilarini bering).

`Procfile` fayli ham qo'shilgan — Render, Heroku-style platformalar buni avtomatik
o'qib, `worker` (bot) va `web` (sayt) jarayonlarini alohida ishga tushiradi.

**Muhim:** ikkala jarayon ham bitta `elonlar.db` faylini ishlatishi kerak — shuning
uchun Railway'da persistent volume ulang (yoki ikkala xizmatni bitta konteynerga
saqlanadigan diskka ulang), aks holda har bir qayta-deploy'da baza yo'qoladi.

## Fayllar

- `bot.py` — Telegram bot
- `dashboard.py` — veb-sayt + admin panel (FastAPI)
- `requirements.txt` — Python kutubxonalari
- `.env.example` — muhit o'zgaruvchilari namunasi
- `railway.toml`, `Procfile` — deploy sozlamalari
