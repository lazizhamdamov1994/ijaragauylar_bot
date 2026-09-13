"""
Botning o'z ma'lumotlar bazasi qatlami - e'lonlar, obunalar, foydalanuvchilar,
bloklangan raqamlar, statistika. `common/db.py`dagi UMUMIY (sayt bilan
baham ko'rilgan) funksiyalardan farqli o'laroq, bu yerdagilar FAQAT botga xos.
"""
from common.db import db, now_str, safe_parse_dt, get_setting, set_setting, is_subscribed, get_blocked_phone, is_phone_blocked

from bot.constants import *  # noqa: F401,F403

# ============================= MA'LUMOTLAR BAZASI =============================
# MUHIM: bazaga oid umumiy funksiyalar endi common/db.py'da BITTA joyda
# (bot.py va dashboard.py ikkalasi ham shundan foydalanadi - nomlar va
# xatti-harakat ATAYIN eskisi bilan bir xil qoldirilgan).

from common.db import (  # noqa: E402
    db,
    now_str,
    safe_parse_dt,
    get_setting,
    set_setting,
    is_subscribed,
    get_blocked_phone,
    is_phone_blocked,
    init_and_migrate,
)


def init_db() -> None:
    """Bazadagi barcha jadval/ustunlarni yaratadi va standart sozlamalarni
    urug'laydi - endi common/db.init_and_migrate() orqali (bot va sayt bitta
    sxemani baham ko'radi)."""
    init_and_migrate()


def listing_price() -> int:
    return int(get_setting("listing_price"))


def subscription_price() -> int:
    return int(get_setting("subscription_price"))


def subscription_days() -> int:
    return int(get_setting("subscription_days"))


def card_number() -> str:
    return get_setting("card_number")


def subscriber_discount_percent() -> int:
    return int(get_setting("subscriber_discount_percent"))


def free_views_enabled() -> bool:
    return get_setting("free_views_enabled") == "1"


def free_views_count() -> int:
    return int(get_setting("free_views_count"))


def upsert_user(user_id: int, username, full_name, phone=None, referred_by=None) -> bool:
    """Foydalanuvchini yaratadi/yangilaydi. True qaytarsa - bu ENDI YARATILGAN
    (haqiqatan YANGI) foydalanuvchi degani."""
    conn = db()
    row = conn.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,)).fetchone()
    is_new = row is None
    if row is None:
        conn.execute(
            "INSERT INTO users (user_id, username, full_name, phone, referred_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, full_name, phone, referred_by, now_str()),
        )
    else:
        conn.execute(
            "UPDATE users SET username = ?, full_name = ?, phone = COALESCE(?, phone) WHERE user_id = ?",
            (username, full_name, phone, user_id),
        )
    conn.commit()
    conn.close()
    return is_new


def get_user(user_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def user_free_limit(user_id: int) -> int:
    return free_views_count() if free_views_enabled() else 0


def user_free_used(user_id: int) -> int:
    u = get_user(user_id) or {}
    return u.get("free_views_used") or 0


def consume_free_view(user_id: int) -> None:
    conn = db()
    conn.execute("UPDATE users SET free_views_used = COALESCE(free_views_used,0) + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def save_listing(data: dict, price_charged: int) -> int:
    conn = db()
    cur = conn.execute(
        """INSERT INTO listings
            (user_id, username, full_name, sender_phone, manzil, moljal, kimlarga, xona,
             qulaylik, narx, telefon, photos, payment_receipt, price_charged, status, created_at,
             latitude, longitude, rental_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
        (
            data["user_id"], data.get("username"), data.get("full_name"), data.get("sender_phone"),
            data["manzil"], data["moljal"], data["kimlarga"], data["xona"], data["qulaylik"], data["narx"],
            data["telefon"], json.dumps(data["rasmlar"]), data.get("payment_receipt"), price_charged, now_str(),
            data.get("latitude"), data.get("longitude"), data.get("rental_type") or "uzoq_muddat",
        ),
    )
    conn.commit()
    listing_id = cur.lastrowid
    conn.close()
    return listing_id


def save_quick_listing(user_id: int, username, full_name, telefon: str, manzil: str, narx: str, raw_text: str, rasmlar: list) -> int:
    """Admin uchun tezkor rejim: OLX'dan ko'chirilgan matn HECH QANDAY o'zgartirishsiz,
    aynan o'zi saqlanadi va kanalga shu holicha (branding qo'shilmasdan) chiqadi.
    Manzil va narx endi MAJBURIY - shu ikkisi tufayli tezkor e'lonlar ham saytda
    aniq manzili va narxi bilan (lite shablonda) to'g'ri ko'rinadi."""
    conn = db()
    cur = conn.execute(
        """INSERT INTO listings
            (user_id, username, full_name, manzil, moljal, kimlarga, xona, qulaylik, narx,
             telefon, photos, price_charged, status, is_quick, raw_text, created_at)
           VALUES (?, ?, ?, ?, '', '', '', '', ?, ?, ?, 0, 'pending', 1, ?, ?)""",
        (user_id, username, full_name, manzil, narx, telefon, json.dumps(rasmlar), raw_text, now_str()),
    )
    conn.commit()
    listing_id = cur.lastrowid
    conn.close()
    return listing_id


def get_listing(listing_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["photos"] = json.loads(d["photos"] or "[]")
    return d


def update_listing_status(listing_id: int, status: str, reason=None, channel_msg_id=None) -> None:
    conn = db()
    conn.execute(
        "UPDATE listings SET status = ?, reject_reason = ?, channel_msg_id = COALESCE(?, channel_msg_id) WHERE id = ?",
        (status, reason, channel_msg_id, listing_id),
    )
    if status == "approved":
        conn.execute("UPDATE listings SET last_confirmed_at = ? WHERE id = ?", (now_str(), listing_id))
    conn.commit()
    conn.close()


def set_listing_receipt_warning(listing_id: int, warning: str) -> None:
    conn = db()
    conn.execute("UPDATE listings SET receipt_warning = ? WHERE id = ?", (warning, listing_id))
    conn.commit()
    conn.close()



def confirm_listing_still_available(listing_id: int) -> None:
    conn = db()
    conn.execute("UPDATE listings SET last_confirmed_at = ? WHERE id = ?", (now_str(), listing_id))
    conn.commit()
    conn.close()


def mark_listing_expired(listing_id: int) -> None:
    conn = db()
    conn.execute("UPDATE listings SET expired = 1 WHERE id = ?", (listing_id,))
    conn.commit()
    conn.close()


def get_stale_listings(days: int) -> list:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    rows = conn.execute(
        "SELECT * FROM listings WHERE status = 'approved' AND expired = 0 AND last_confirmed_at <= ?",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def increment_stale_report(listing_id: int) -> int:
    conn = db()
    conn.execute("UPDATE listings SET stale_reports = COALESCE(stale_reports,0) + 1 WHERE id = ?", (listing_id,))
    conn.commit()
    row = conn.execute("SELECT stale_reports FROM listings WHERE id = ?", (listing_id,)).fetchone()
    conn.close()
    return row["stale_reports"] if row else 0


def has_user_reported(listing_id: int, user_id: int) -> bool:
    conn = db()
    row = conn.execute("SELECT 1 FROM listing_reports WHERE listing_id = ? AND user_id = ?", (listing_id, user_id)).fetchone()
    conn.close()
    return row is not None


def count_user_reports_today(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM listing_reports WHERE user_id = ? AND substr(created_at,1,10) = ?", (user_id, today)
    ).fetchone()["c"]
    conn.close()
    return n


def save_report(listing_id: int, user_id: int, reason: str) -> None:
    conn = db()
    conn.execute(
        "INSERT INTO listing_reports (listing_id, user_id, reason, created_at) VALUES (?, ?, ?, ?)",
        (listing_id, user_id, reason, now_str()),
    )
    conn.commit()
    conn.close()


def get_user_listings(user_id: int, limit: int = 10):
    conn = db()
    rows = conn.execute("SELECT * FROM listings WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_listings(limit: int = 10):
    conn = db()
    rows = conn.execute("SELECT * FROM listings WHERE status = 'pending' ORDER BY id ASC LIMIT ?", (limit,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["photos"] = json.loads(d["photos"] or "[]")
        result.append(d)
    return result


def count_pending_listings() -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM listings WHERE status='pending'").fetchone()["c"]
    conn.close()
    return n


def get_pending_subscriptions(limit: int = 10):
    conn = db()
    rows = conn.execute("SELECT * FROM subscriptions WHERE status = 'pending' ORDER BY id ASC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_pending_subscriptions() -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM subscriptions WHERE status='pending'").fetchone()["c"]
    conn.close()
    return n


def count_today_listings(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM listings WHERE user_id = ? AND substr(created_at, 1, 10) = ?", (user_id, today)
    ).fetchone()["c"]
    conn.close()
    return n


def save_subscription_request(user_id: int, receipt_photo: str, price_charged: int, target_listing_id) -> int:
    conn = db()
    cur = conn.execute(
        "INSERT INTO subscriptions (user_id, receipt_photo, months, price_charged, target_listing_id, status, created_at) "
        "VALUES (?, ?, 1, ?, ?, 'pending', ?)",
        (user_id, receipt_photo, price_charged, target_listing_id, now_str()),
    )
    conn.commit()
    sub_id = cur.lastrowid
    conn.close()
    return sub_id


def get_subscription(sub_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def approve_subscription(sub_id: int):
    sub = get_subscription(sub_id)
    months = sub["months"] or 1
    expire_at = (datetime.now() + timedelta(days=subscription_days() * months)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    conn.execute(
        "UPDATE subscriptions SET status = 'approved', approved_at = ?, expire_at = ? WHERE id = ?",
        (now_str(), expire_at, sub_id),
    )
    conn.execute(
        "UPDATE subscriptions SET status='rejected', reject_reason='Avtomatik: boshqa so''rovingiz allaqachon tasdiqlandi' "
        "WHERE user_id = ? AND status = 'pending' AND id != ?",
        (sub["user_id"], sub_id),
    )
    conn.commit()
    conn.close()
    return sub["user_id"], expire_at


def reject_subscription(sub_id: int, reason: str) -> None:
    conn = db()
    conn.execute("UPDATE subscriptions SET status = 'rejected', reject_reason = ? WHERE id = ?", (reason, sub_id))
    conn.commit()
    conn.close()


def cancel_subscription(sub_id: int):
    sub = get_subscription(sub_id)
    if not sub:
        return None
    conn = db()
    conn.execute("UPDATE subscriptions SET status = 'cancelled' WHERE id = ?", (sub_id,))
    conn.commit()
    conn.close()
    return sub["user_id"]


# is_subscribed() endi common/db.py'dan import qilinadi (yuqoridagi import bloki).


def get_active_subscription_id(user_id: int):
    conn = db()
    row = conn.execute(
        "SELECT id, expire_at FROM subscriptions WHERE user_id = ? AND status = 'approved' ORDER BY expire_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row or not row["expire_at"]:
        return None
    parsed = safe_parse_dt(row["expire_at"])
    if parsed is None or parsed <= datetime.now():
        return None
    return row["id"]


def count_active_subscribers() -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM subscriptions WHERE status='approved' AND expire_at > ?", (now_str(),)).fetchone()["c"]
    conn.close()
    return n


def active_subscribers_page(offset: int, limit: int = PAGE_SIZE):
    conn = db()
    rows = conn.execute(
        """SELECT s.id AS sub_id, s.user_id, s.expire_at, s.months, u.username, u.full_name, u.phone
           FROM subscriptions s LEFT JOIN users u ON u.user_id = s.user_id
           WHERE s.status = 'approved' AND s.expire_at > ?
           ORDER BY s.expire_at ASC LIMIT ? OFFSET ?""",
        (now_str(), limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stats_for_period(date_from: str, date_to_exclusive: str) -> dict:
    conn = db()

    def count(query, *params):
        return conn.execute(query, params).fetchone()["c"]

    listings_total = count("SELECT COUNT(*) c FROM listings WHERE created_at >= ? AND created_at < ?", date_from, date_to_exclusive)
    listings_approved = count("SELECT COUNT(*) c FROM listings WHERE created_at >= ? AND created_at < ? AND status='approved'", date_from, date_to_exclusive)
    listings_rejected = count("SELECT COUNT(*) c FROM listings WHERE created_at >= ? AND created_at < ? AND status='rejected'", date_from, date_to_exclusive)
    listings_pending = count("SELECT COUNT(*) c FROM listings WHERE created_at >= ? AND created_at < ? AND status='pending'", date_from, date_to_exclusive)
    listings_income = conn.execute(
        "SELECT COALESCE(SUM(price_charged),0) s FROM listings WHERE created_at >= ? AND created_at < ? AND status='approved'",
        (date_from, date_to_exclusive),
    ).fetchone()["s"]
    subs_total = count("SELECT COUNT(*) c FROM subscriptions WHERE created_at >= ? AND created_at < ?", date_from, date_to_exclusive)
    subs_approved = count("SELECT COUNT(*) c FROM subscriptions WHERE created_at >= ? AND created_at < ? AND status='approved'", date_from, date_to_exclusive)
    subs_income = conn.execute(
        "SELECT COALESCE(SUM(price_charged),0) s FROM subscriptions WHERE created_at >= ? AND created_at < ? AND status='approved'",
        (date_from, date_to_exclusive),
    ).fetchone()["s"]
    users_total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    conn.close()
    return {
        "listings_total": listings_total, "listings_approved": listings_approved, "listings_rejected": listings_rejected,
        "listings_pending": listings_pending, "listings_income": listings_income, "subs_total": subs_total,
        "subs_approved": subs_approved, "subs_income": subs_income, "users_total": users_total,
    }


def stats_today() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return stats_for_period(today, tomorrow)


def count_new_users_in_period(date_from: str, date_to_exclusive: str) -> int:
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM users WHERE created_at >= ? AND created_at < ?", (date_from, date_to_exclusive)
    ).fetchone()["c"]
    conn.close()
    return n


def get_period_bounds(period: str):
    """Berilgan davr uchun (boshlanish, tugash, oldingi davr boshlanishi,
    oldingi davr tugashi, ko'rinadigan nom) qaytaradi - taqqoslash uchun."""
    now = datetime.now()
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        prev_start, prev_end = start - timedelta(days=1), start
        label = f"\U0001F4C5 Bugun ({start.strftime('%d.%m.%Y')})"
        prev_label = "kechagi kunga nisbatan"
    elif period == "weekly":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        prev_start, prev_end = start - timedelta(days=7), start
        label = f"\U0001F4C6 Bu hafta ({start.strftime('%d.%m')} \u2014 {(end - timedelta(days=1)).strftime('%d.%m.%Y')})"
        prev_label = "o'tgan haftaga nisbatan"
    elif period == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1))
        prev_start = (start.replace(year=start.year - 1, month=12) if start.month == 1 else start.replace(month=start.month - 1))
        prev_end = start
        label = f"\U0001F5D3 Bu oy ({start.strftime('%m.%Y')})"
        prev_label = "o'tgan oyga nisbatan"
    else:  # yearly
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
        prev_start, prev_end = start.replace(year=start.year - 1), start
        label = f"\U0001F4C8 Bu yil ({start.year})"
        prev_label = "o'tgan yilga nisbatan"
    fmt = "%Y-%m-%d %H:%M:%S"
    return start.strftime(fmt), end.strftime(fmt), prev_start.strftime(fmt), prev_end.strftime(fmt), label, prev_label


def percent_change(old: float, new: float) -> str:
    if old == 0 and new == 0:
        return "o'zgarishsiz"
    if old == 0:
        return "\U0001F195 yangi"
    change = (new - old) / old * 100
    arrow = "\U0001F53A" if change > 0 else ("\U0001F53B" if change < 0 else "\u27a1\ufe0f")
    return f"{arrow} {change:+.0f}%"


def render_period_stats(period: str) -> str:
    start, end, prev_start, prev_end, label, prev_label = get_period_bounds(period)
    cur = stats_for_period(start, end)
    prev = stats_for_period(prev_start, prev_end)
    new_users = count_new_users_in_period(start, end)
    new_users_prev = count_new_users_in_period(prev_start, prev_end)

    total_users_ever = cur["users_total"]  # stats_for_period bu yerda umriy jamini beradi
    total_active_subs = count_active_subscribers()
    total_revenue = cur["listings_income"] + cur["subs_income"]
    prev_revenue = prev["listings_income"] + prev["subs_income"]

    successful_reveals = count_reveals_in_period(start, end)
    failed_attempts = count_paywall_hits_in_period(start, end)
    total_attempts = successful_reveals + failed_attempts
    conversion = f"{(successful_reveals / total_attempts * 100):.0f}%" if total_attempts else "\u2014"
    phone_checks = count_phone_checks_in_period(start, end)
    new_location_alerts = count_location_alerts_in_period(start, end)
    source = count_listings_by_source_in_period(start, end)
    listing_type = count_listings_by_type_in_period(start, end)
    multi_location = get_multi_location_posters(2)

    location_lines = [f"\U0001F4CD <b>JOYLASHUV BO'YICHA E'LON BERUVCHILAR</b> <i>(umumiy, davrga bog'liq emas)</i>\n"]
    location_lines.append(f"2+ hududda e'lon bergan: {len(multi_location)} ta foydalanuvchi\n")
    if multi_location:
        for uid, cnt in multi_location[:5]:
            u = get_user(uid) or {}
            name = u.get("full_name") or f"ID:{uid}"
            location_lines.append(f"\u2022 {esc(name)} \u2014 {cnt} ta hududda")
    location_section = "\n".join(location_lines) + "\n\n"

    text = (
        f"\U0001F4CA <b>Statistika</b> \u2014 {label}\n"
        f"<i>({prev_label} solishtirilgan)</i>\n\n"

        f"\U0001F465 <b>FOYDALANUVCHILAR</b>\n"
        f"Yangi qo'shilgan: {new_users} ta ({percent_change(new_users_prev, new_users)})\n"
        f"Jami (botni ishlatgan): {total_users_ever} ta\n\n"

        f"\U0001F4DD <b>E'LONLAR</b>\n"
        f"Yangi: {cur['listings_total']} ta ({percent_change(prev['listings_total'], cur['listings_total'])})\n"
        f"\u2705 Tasdiqlangan: {cur['listings_approved']} ta\n"
        f"\u274c Rad etilgan: {cur['listings_rejected']} ta\n"
        f"\U0001F553 Kutilmoqda: {cur['listings_pending']} ta\n"
        f"\U0001F464 Foydalanuvchilar o'zi joyladi: {source['user']} ta\n"
        f"\U0001F6E0 Admin/moderator joyladi: {source['staff']} ta\n"
        f"\U0001F4B0 Pullik e'lon: {listing_type['paid']} ta\n"
        f"\U0001F193 Bepul e'lon: {listing_type['free']} ta\n"
        f"\U0001F4B0 Tushum: {cur['listings_income']:,} so'm ({percent_change(prev['listings_income'], cur['listings_income'])})\n\n"

        f"\U0001F4B3 <b>LIMIT (OBUNA)</b>\n"
        f"Yangi so'rov: {cur['subs_total']} ta ({percent_change(prev['subs_total'], cur['subs_total'])})\n"
        f"\u2705 Tasdiqlangan: {cur['subs_approved']} ta\n"
        f"\U0001F513 Hozir FAOL: {total_active_subs} ta\n"
        f"\U0001F4B0 Tushum: {cur['subs_income']:,} so'm ({percent_change(prev['subs_income'], cur['subs_income'])})\n\n"

        f"\U0001F3AF <b>RAQAM KO'RISH URINISHLARI</b>\n"
        f"\u2705 Muvaffaqiyatli (raqam olishgan): {successful_reveals} ta\n"
        f"\u274c Muvaffaqiyatsiz (limit/obunasiz): {failed_attempts} ta\n"
        f"\U0001F4C8 Konversiya: {conversion}\n\n"

        f"\U0001F527 <b>BOSHQA FUNKSIYALAR</b>\n"
        f"\U0001F50D Raqam tekshirish: {phone_checks} marta\n"
        f"\U0001F514 Yangi hudud-xabar: {new_location_alerts} ta\n\n"

        f"{location_section}"

        f"\U0001F4B5 <b>JAMI TUSHUM: {total_revenue:,} so'm</b> ({percent_change(prev_revenue, total_revenue)})"
    )
    return text


def normalize_phone(raw: str):
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("998") and len(digits) == 12:
        pass
    elif len(digits) == 9:
        digits = "998" + digits
    else:
        return None
    if not re.fullmatch(r"998\d{9}", digits):
        return None
    return "+" + digits


def block_phone(phone: str, reason: str, admin_id: int) -> None:
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO blocked_phones (phone, reason, blocked_by, blocked_at) VALUES (?, ?, ?, ?)",
        (phone, reason, admin_id, now_str()),
    )
    conn.commit()
    conn.close()


def unblock_phone(phone: str) -> None:
    conn = db()
    conn.execute("DELETE FROM blocked_phones WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()


# get_blocked_phone() endi common/db.py'dan import qilinadi (yuqoridagi import bloki).


def count_blocked_phones() -> int:
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM blocked_phones").fetchone()["c"]
    conn.close()
    return n


def has_recent_subscription_request(user_id: int, since: str) -> bool:
    conn = db()
    row = conn.execute("SELECT 1 FROM subscriptions WHERE user_id = ? AND created_at >= ? LIMIT 1", (user_id, since)).fetchone()
    conn.close()
    return row is not None


def list_blocked_phones_page(offset: int, limit: int = PAGE_SIZE):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM blocked_phones ORDER BY blocked_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]



