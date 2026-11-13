# 👗 Seus — kiyim-kechak sotuvchilari uchun Telegram bot

Sotuvchi tovarni bot orqali qo'shadi → bot uni sotuvchining Telegram kanaliga
rasmlar va tugmalar bilan joylaydi → xaridor «🛒 Buyurtma berish» tugmasini bosib botga keladi.

**1-bosqichda tayyor:** ro'yxatdan o'tish, kanal ulash, tovar qo'shish (rasm, nom, narx,
razmer/rang/son, tavsif), oldindan ko'rish va tahrirlash, kanalga joylash, «Tovarlarim»,
xaridor uchun tovar kartochkasi. To'liq buyurtma berish — 2-bosqichda.

---

## 0-qadam. Kerakli dasturlar (bir marta)

Kompyuterda **Win + R** bosing, `cmd` yozing, Enter. Ochilgan qora oynaga quyidagilarni
birma-bir yozing:

```
py -3.13 --version
psql --version
git --version
```

Har biri versiya raqamini chiqarsa — dastur bor. «topilmadi» / «is not recognized» desa — o'rnating:

| Dastur | Qayerdan | O'rnatishda e'tibor bering |
|---|---|---|
| **Python 3.13** | https://www.python.org/downloads/windows/ → «Python 3.13.x» → *Windows installer (64-bit)* | Birinchi oynada **«Add python.exe to PATH»** belgisini qo'ying |
| **PostgreSQL** | https://www.postgresql.org/download/windows/ → *Download the installer* (16 yoki 17-versiya) | `postgres` foydalanuvchisi uchun parol so'raydi — **yozib qo'ying**, unutmang. Port: 5432 qoldiring. «Stack Builder»ni o'tkazib yuborsangiz bo'ladi |
| **Git** | https://git-scm.com/download/win | Hamma joyda «Next» bosavering |

O'rnatgandan keyin `cmd` oynasini **yopib, qayta oching** va tekshiruvni takrorlang.

> `psql` topilmasa, lekin PostgreSQL o'rnatilgan bo'lsa: Start menyusidan **«SQL Shell (psql)»** ni oching — u ham bo'ladi.

## 1-qadam. Loyihani papkaga joylash

`cmd` da:

```
cd C:\Users\Laziz\Desktop
git clone -b claude/eloquent-feynman-i3qbu4 https://github.com/lazizhamdamov1994/ijaragauylar_bot.git seus-repo
xcopy /E /I seus-repo\seus seus
```

Natijada `C:\Users\Laziz\Desktop\seus` papkasida loyiha paydo bo'ladi.

## 2-qadam. Baza (PostgreSQL) yaratish

Start → **«SQL Shell (psql)»** ni oching. U Server, Database, Port, Username so'raydi —
hammasida shunchaki **Enter** bosing. Keyin `postgres` parolini kiriting (o'rnatishda yozgan parolingiz;
yozayotganda ekranda ko'rinmaydi — bu normal).

`postgres=#` chiqqanda quyidagi 2 qatorni yozing. **`BU_YERGA_PAROL`** o'rniga o'zingiz o'ylab
topgan yangi parolni yozing (lotin harflari va raqamlar, masalan `Seus2026kuchli`):

```sql
CREATE USER seus WITH PASSWORD 'BU_YERGA_PAROL';
CREATE DATABASE seus OWNER seus;
```

Har biridan keyin `CREATE ROLE` va `CREATE DATABASE` deb javob bersa — tayyor. `\q` yozib chiqing.

## 3-qadam. `.env` fayliga token va parolni yozish

1. `C:\Users\Laziz\Desktop\seus` papkasini oching.
2. `.env.example` faylidan nusxa oling (Ctrl+C, Ctrl+V) va nusxaning nomini **`.env`** qiling
   (oxirida `.txt` bo'lmasin!).
   - Yoki `cmd` da: `cd C:\Users\Laziz\Desktop\seus` va `copy .env.example .env`
3. `.env` ni **Bloknot** (Notepad) bilan oching va to'ldiring:

```
BOT_TOKEN=1234567890:AAH...sizning_tokeningiz
DB_PASSWORD=2-qadamdagi_parol
```

Saqlang (Ctrl+S). **Bu faylni hech kimga yubormang** — u GitHub'ga ham tushmaydi.

## 4-qadam. Botni ishga tushirish

`seus` papkasidagi **`run.bat`** ni ikki marta bosing. Birinchi marta 1–2 daqiqa
kutubxonalarni o'rnatadi. Oxirida shunday yozuv chiqadi:

```
INFO seus: Bot ishga tushdi: @sizning_botingiz
```

Oyna ochiq tursa — bot ishlayapti. To'xtatish: oynada **Ctrl+C** yoki oynani yopish.

## 5-qadam. Sinab ko'rish

1. Telegram'da botingizga **/start** yozing → do'kon nomi → «📱 Raqamni yuborish».
2. Test uchun yangi kanal oching. Kanal → **Administratorlar** → **Admin qo'shish** →
   botingizni toping → **«Xabarlarni joylash»** huquqini yoqing.
3. Botda **📢 Kanalim** → kanal username'ini yuboring (`@kanal_nomi`)
   yoki kanaldan biror xabarni botga forward qiling.
4. **➕ Tovar qo'shish** → 2–3 ta rasm → «✅ Tayyor» → nom → narx → `S qora 5` → «✅ Tayyor»
   → tavsif → oldindan ko'rish → **📢 Kanalga joylash**.
5. Kanalni oching: albom + tugmali xabar chiqadi. **🛒 Buyurtma berish** ni bosing —
   bot tovar kartochkasini ko'rsatadi.

## Testlar

**`test.bat`** ni ikki marta bosing — barcha testlar ishga tushadi (oxirida `passed` chiqishi kerak).
Testlar uchun PostgreSQL shart emas (xotiradagi vaqtinchalik baza ishlatiladi).

## Muammo bo'lsa

| Xabar | Nima qilish kerak |
|---|---|
| `.env fayli topilmadi` | 3-qadam |
| `BOT_TOKEN noto'g'ri` | @BotFather → /mybots → bot → API Token — qayta nusxa oling |
| `Bazaga ulanib bo'lmadi` | PostgreSQL ishlayaptimi (Win+R → `services.msc` → postgresql — «Running»), parol to'g'rimi |
| `Python topilmadi` | 0-qadam, «Add to PATH» belgisi bilan qayta o'rnating |
| Bot javob bermayapti | `run.bat` oynasi ochiqmi? `logs\bot.log` faylida xato bormi? |

## Loyiha tuzilmasi

```
seus/
├── app/
│   ├── config.py          sozlamalar (.env dan o'qiladi)
│   ├── texts/uz.py        BARCHA bot matnlari (rus tili keyin shu yerga qo'shiladi)
│   ├── db/                baza jadvallari (Seller, Channel, Product, ..., Order)
│   ├── services/          biznes mantiq — Telegram'ga bog'liq emas, veb-saytda ham ishlatiladi
│   └── bot/               Telegram qismi: handlers, tugmalar, holatlar (FSM), middleware
├── migrations/            baza tuzilmasi o'zgarishlari (Alembic)
├── tests/                 testlar
├── run.bat / test.bat     ikki marta bosib ishga tushirish
└── .env.example           sozlamalar namunasi
```

## Keyinroq: serverga qo'yish (qisqacha)

Linux serverda: Python 3.13 va PostgreSQL o'rnatiladi, loyiha `git clone` qilinadi, `.env` yoziladi, so'ng:

```
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m app.bot
```

Doimiy ishlashi uchun `systemd` xizmati qilinadi — bu bosqichga kelganda birga sozlaymiz.

> **Eslatma:** hozir FSM (tovar qo'shish jarayoni) xotirada saqlanadi — bot qayta ishga
> tushsa, chala qolgan tovar qo'shishni boshidan boshlash kerak. Saqlangan tovarlar yo'qolmaydi.
