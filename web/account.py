"""
Telegram orqali kirish (Login Widget) + shaxsiy kabinet (/kabinet) + Limit
sotib olish - saytdagi to'lov oqimi bot bilan bitta bazani baham ko'radi.
"""
import logging
import re
import urllib.parse

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from common.config import ADMIN_IDS, BOT_TOKEN, BOT_USERNAME, CARD_HOLDER, SESSION_COOKIE, SESSION_MAX_AGE, SITE_URL
from common.db import (
    db,
    get_favorite_listings_full,
    get_user_notifications,
    get_user_support_requests,
    mark_notifications_read,
    now_str,
)

from web.auth import create_session_token, get_current_tg_user, is_web_subscribed, verify_telegram_auth
from web.listings_data import current_card_number, current_subscription_days, current_subscription_price
from web.pages import telegram_upload_photos
from web.render import DEFAULT_LANG, esc_html, get_lang, icon, render_credit_card, render_footer, render_head, render_header, render_listing_card, t

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = Query("/kabinet")):
    lang = get_lang(request)
    if not BOT_USERNAME or not SITE_URL:
        raise HTTPException(status_code=503, detail="Tizim vaqtincha sozlanmoqda.")
    if not next.startswith("/") or next.startswith("//"):
        next = "/kabinet"
    auth_url = f"{SITE_URL}/auth/telegram-callback?next={urllib.parse.quote(next, safe='')}"
    head = render_head(t(lang, "login_title"), t(lang, "login_desc"), "/login", lang=lang, noindex=True)
    body = f"""<body>
{render_header(lang, "/login")}
<main class="wrap" style="max-width:420px;padding-top:60px;padding-bottom:90px;text-align:center;">
  <h1 style="font-family:var(--font-display);font-size:26px;margin-bottom:10px;">{t(lang,'login_title')}</h1>
  <p style="color:var(--muted);font-size:14px;margin-bottom:28px;">{t(lang,'login_desc')}</p>
  <div style="display:flex;justify-content:center;">
    <script async src="https://telegram.org/js/telegram-widget.js?22"
      data-telegram-login="{BOT_USERNAME}" data-size="large" data-radius="12"
      data-auth-url="{auth_url}" data-request-access="write"></script>
  </div>
</main>
{render_footer(lang)}
</body>"""
    return HTMLResponse(f'<!DOCTYPE html><html lang="{lang}"><head>{head}</head>{body}</html>')


@router.get("/auth/telegram-callback")
async def telegram_auth_callback(request: Request):
    params = dict(request.query_params)
    next_url = params.get("next") or "/kabinet"
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/kabinet"
    if not verify_telegram_auth(params):
        raise HTTPException(status_code=403, detail="Telegram orqali tasdiqlash muvaffaqiyatsiz tugadi. Qaytadan urinib ko'ring.")
    try:
        uid = int(params["id"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Noto'g'ri ma'lumot.")
    token = create_session_token(uid, params.get("first_name", ""), params.get("username", ""))
    resp = RedirectResponse(next_url, status_code=302)
    resp.set_cookie(SESSION_COOKIE, token, max_age=SESSION_MAX_AGE, httponly=True, secure=True, samesite="lax")
    return resp


@router.get("/logout")
def logout(next: str = Query("/")):
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    resp = RedirectResponse(next, status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@router.get("/kabinet", response_class=HTMLResponse)
def kabinet_page(request: Request):
    lang = get_lang(request)
    tg_user = get_current_tg_user(request)
    if not tg_user:
        return RedirectResponse("/login?next=/kabinet", status_code=302)
    uid = tg_user["uid"]
    active, expire = is_web_subscribed(uid)

    conn = db()
    rows = conn.execute(
        "SELECT id, manzil, narx, status, expired, created_at FROM listings WHERE user_id = ? ORDER BY created_at DESC LIMIT 30",
        (uid,),
    ).fetchall()
    conn.close()

    status_map = {
        "pending": (t(lang, "status_pending"), "st-pending"),
        "approved": (t(lang, "status_approved"), "st-approved"),
        "rejected": (t(lang, "status_rejected"), "st-rejected"),
    }
    rows_html = ""
    for r in rows:
        addr = esc_html(r["manzil"] or "—")
        label, cls = status_map.get(r["status"], (r["status"], ""))
        if r["expired"]:
            label, cls = t(lang, "status_expired"), "st-expired"
        addr_cell = f'<a href="/uy/{r["id"]}">{addr}</a>' if r["status"] == "approved" else addr
        rows_html += (
            f'<tr><td>{addr_cell}</td><td>{esc_html(r["narx"] or "")}</td>'
            f'<td><span class="kb-status {cls}">{label}</span></td><td>{(r["created_at"] or "")[:10]}</td></tr>'
        )
    listings_html = (
        f'<div class="kb-table-wrap"><table class="kb-table"><thead><tr>'
        f'<th>{t(lang,"kb_col_addr")}</th><th>{t(lang,"kb_col_price")}</th>'
        f'<th>{t(lang,"kb_col_status")}</th><th>{t(lang,"kb_col_date")}</th></tr></thead>'
        f'<tbody>{rows_html}</tbody></table></div>'
        if rows else f'<div class="kb-empty">{t(lang,"kb_no_listings")}</div>'
    )
    if active:
        limit_html = f'<div class="kb-limit-active">{icon("check_circle",16)} {t(lang,"kb_limit_active", date=expire[:10])}</div>'
    else:
        limit_html = f'<a href="/kabinet/limit" class="btn-cta">{icon("bolt",14)} {t(lang,"kb_buy_limit")}</a>'

    display_name = esc_html(tg_user.get("fn") or "")
    username_line = f' · @{esc_html(tg_user["un"])}' if tg_user.get("un") else ""

    # Bildirishnomalar (admin tomonidan yuborilgan) - ko'rilgach o'qilgan
    # deb belgilanadi (sahifa ochilganda darhol - keyingi safar "yangi"
    # nishoni ko'rsatilmaydi).
    notifications = get_user_notifications(uid)
    notif_html = ""
    if notifications:
        items = "".join(
            f'<div class="kb-notif{"" if n["is_read"] else " unread"}">'
            f'<div class="kb-notif-title">{esc_html(n["title"] or "")}</div>'
            f'<div class="kb-notif-body">{esc_html(n["body"] or "")}</div>'
            f'<div class="kb-notif-date">{(n["created_at"] or "")[:16]}</div></div>'
            for n in notifications
        )
        notif_html = f'<div class="kb-card"><div class="kb-card-title">{t(lang,"kb_notifications_title")}</div><div class="kb-notif-list">{items}</div></div>'
        mark_notifications_read(uid)

    # Sevimlilar
    favorites = get_favorite_listings_full(uid)
    favorited_ids = {f["id"] for f in favorites}
    if favorites:
        fav_cards = "".join(render_listing_card(f, favorited_ids) for f in favorites)
        fav_body = f'<div class="listing-grid">{fav_cards}</div>'
    else:
        fav_body = f'<div class="kb-empty">{t(lang,"kb_no_favorites")}</div>'
    fav_html = f'<div class="kb-card"><div class="kb-card-title">{t(lang,"kb_favorites_title")}</div>{fav_body}</div>'

    # Qo'llab-quvvatlash so'rovlari (foydalanuvchi -> admin)
    support_requests = get_user_support_requests(uid)
    support_history_html = ""
    if support_requests:
        items = ""
        for r in support_requests:
            replied = r["status"] == "javob_berildi"
            status_label = t(lang, "kb_support_status_replied") if replied else t(lang, "kb_support_status_new")
            status_cls = "st-approved" if replied else "st-pending"
            reply_html = (
                f'<div class="kb-support-reply"><b>{t(lang,"kb_support_reply_label")}</b> {esc_html(r["admin_reply"] or "")}</div>'
                if replied else ""
            )
            items += (
                f'<div class="kb-support-item"><div class="kb-support-msg">{esc_html(r["message"] or "")}</div>'
                f'<div class="kb-support-meta"><span class="kb-status {status_cls}">{status_label}</span> '
                f'<span class="kb-support-date">{(r["created_at"] or "")[:16]}</span></div>{reply_html}</div>'
            )
        support_history_html = f'<div class="kb-support-history"><div class="kb-card-title" style="margin-top:18px;">{t(lang,"kb_support_history_title")}</div>{items}</div>'

    support_html = f"""<div class="kb-card">
    <div class="kb-card-title">{t(lang,'kb_support_title')}</div>
    <p style="color:var(--muted);font-size:13px;margin-bottom:12px;">{t(lang,'kb_support_hint')}</p>
    <form id="supportForm" onsubmit="return submitSupport(event)">
      <textarea name="message" required maxlength="1000" rows="3" placeholder="{t(lang,'kb_support_placeholder')}"
        style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;font-family:inherit;resize:vertical;"></textarea>
      <button type="submit" class="btn-cta" style="margin-top:10px;border:none;cursor:pointer;">{t(lang,'kb_support_submit')}</button>
      <div id="supportSuccess" style="display:none;color:var(--brand);font-size:13px;font-weight:700;margin-top:10px;">{icon('check_circle',14)} {t(lang,'kb_support_sent')}</div>
    </form>
    {support_history_html}
  </div>
  <script>
  async function submitSupport(e) {{
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector('button[type=submit]');
    const ta = form.querySelector('textarea');
    btn.disabled = true;
    try {{
      const res = await fetch('/api/kabinet/support', {{
        method: 'POST', headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{message: ta.value}}),
      }});
      if (res.ok) {{
        ta.value = '';
        document.getElementById('supportSuccess').style.display = 'block';
      }} else {{
        btn.disabled = false;
      }}
    }} catch (err) {{ btn.disabled = false; }}
    return false;
  }}
  </script>"""

    head = render_head(t(lang, "kabinet_title"), t(lang, "kabinet_title"), "/kabinet", lang=lang, noindex=True)
    body = f"""<body>
{render_header(lang, "/kabinet")}
<main class="wrap" style="padding-top:32px;padding-bottom:80px;max-width:760px;">
  <h1 style="font-family:var(--font-display);font-size:24px;margin-bottom:4px;">{t(lang,'kabinet_title')}</h1>
  <p style="color:var(--muted);font-size:14px;margin-bottom:22px;">{display_name}{username_line}</p>
  {notif_html}
  <div class="kb-card">
    <div class="kb-card-title">{t(lang,'kb_limit_title')}</div>
    {limit_html}
  </div>
  <div class="kb-card">
    <div class="kb-card-title">{t(lang,'kb_my_listings')}</div>
    {listings_html}
  </div>
  {fav_html}
  {support_html}
  <a href="/logout?next=/" style="font-size:13px;color:var(--muted);">{t(lang,'kb_logout')}</a>
</main>
{render_footer(lang)}
</body>"""
    return HTMLResponse(f'<!DOCTYPE html><html lang="{lang}"><head>{head}</head>{body}</html>')


@router.get("/kabinet/limit", response_class=HTMLResponse)
def kabinet_limit_page(request: Request, listing_id: str = Query("")):
    lang = get_lang(request)
    tg_user = get_current_tg_user(request)
    if not tg_user:
        next_path = f"/kabinet/limit?listing_id={listing_id}" if listing_id else "/kabinet/limit"
        return RedirectResponse(f"/login?next={urllib.parse.quote(next_path, safe='')}", status_code=302)
    active, expire = is_web_subscribed(tg_user["uid"])
    price = current_subscription_price()
    days = current_subscription_days()
    card = current_card_number()

    if active:
        body_inner = (
            f'<div class="kb-limit-active">{icon("check_circle",16)} {t(lang,"kb_limit_active", date=expire[:10])}</div>'
            f'<a href="/kabinet" class="btn-cta" style="margin-top:16px;">{t(lang,"kb_back")}</a>'
        )
    else:
        listing_field = f'<input type="hidden" name="listing_id" value="{esc_html(listing_id)}">' if listing_id else ""
        card_digits = re.sub(r"\D", "", card)
        card_html = render_credit_card(lang, card_digits, with_copy=True)
        body_inner = f"""
    <div class="kb-pay-box">
      <div class="kb-pay-price">{price:,} {t(lang,'sum')} <span>/ {days} {t(lang,'days')}</span></div>
      {card_html}
      <p class="kb-pay-hint">{t(lang,'kb_pay_hint')}</p>
    </div>
    <form id="limitForm" onsubmit="return submitLimit(event)">
      {listing_field}
      <label class="kb-file-label">
        {icon('camera_off',15)} <span id="fileLabelText">{t(lang,'kb_upload_receipt')}</span>
        <input type="file" name="receipt" accept="image/*" required
          onchange="document.getElementById('fileLabelText').textContent=this.files[0]?this.files[0].name:''">
      </label>
      <button type="submit" class="btn-cta" style="width:100%;justify-content:center;margin-top:14px;border:none;cursor:pointer;">{t(lang,'kb_submit_receipt')}</button>
      <div id="limitSuccess" class="kb-limit-success">{icon('check_circle',15)} {t(lang,'kb_receipt_sent')}</div>
      <div id="limitError" class="kb-limit-error"></div>
    </form>
    <script>
    function copyCardNumber(btn, digits) {{
      navigator.clipboard.writeText(digits);
      const original = btn.innerHTML;
      btn.innerHTML = "✅ {t(lang,'copied_btn')}";
      setTimeout(() => btn.innerHTML = original, 1800);
    }}
    async function submitLimit(e) {{
      e.preventDefault();
      const form = e.target;
      const btn = form.querySelector('button[type=submit]');
      btn.disabled = true;
      const errEl = document.getElementById('limitError');
      errEl.style.display = 'none';
      try {{
        const res = await fetch('/api/kabinet/buy-limit', {{ method: 'POST', body: new FormData(form) }});
        const data = await res.json().catch(() => ({{}}));
        if (res.ok) {{
          form.style.display = 'none';
          document.getElementById('limitSuccess').style.display = 'flex';
        }} else {{
          errEl.textContent = data.detail || "{t(lang,'kb_error')}";
          errEl.style.display = 'block';
          btn.disabled = false;
        }}
      }} catch (err) {{
        errEl.textContent = "{t(lang,'kb_error')}";
        errEl.style.display = 'block';
        btn.disabled = false;
      }}
      return false;
    }}
    </script>"""

    head = render_head(t(lang, "kb_buy_limit"), t(lang, "kb_buy_limit"), "/kabinet/limit", lang=lang, noindex=True)
    body = f"""<body>
{render_header(lang, "/kabinet/limit")}
<main class="wrap" style="max-width:440px;padding-top:32px;padding-bottom:80px;">
  <h1 style="font-family:var(--font-display);font-size:22px;margin-bottom:18px;">{t(lang,'kb_buy_limit')}</h1>
  {body_inner}
</main>
{render_footer(lang)}
</body>"""
    return HTMLResponse(f'<!DOCTYPE html><html lang="{lang}"><head>{head}</head>{body}</html>')


@router.post("/api/kabinet/buy-limit")
async def buy_limit(request: Request, receipt: UploadFile = File(...), listing_id: str = Form("")):
    tg_user = get_current_tg_user(request)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Iltimos, avval Telegram orqali kiring.")
    uid = tg_user["uid"]
    if not receipt or not receipt.filename:
        raise HTTPException(status_code=400, detail="Chek rasmini yuklang.")
    content = await receipt.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Chek rasmi 10MB dan oshmasligi kerak.")
    if not ADMIN_IDS or not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Tizim vaqtincha sozlanmoqda.")

    try:
        r_ids = await telegram_upload_photos(ADMIN_IDS[0], [content], ["chek.jpg"])
    except Exception:
        logger.exception("Kabinet: chek yuklashda xatolik")
        raise HTTPException(status_code=502, detail="Chekni yuklab bo'lmadi. Qaytadan urinib ko'ring.")
    if not r_ids:
        raise HTTPException(status_code=502, detail="Chekni yuklab bo'lmadi.")
    receipt_file_id = r_ids[0]

    target_listing_id = int(listing_id) if listing_id and listing_id.isdigit() else None
    price = current_subscription_price()

    conn = db()
    cur = conn.execute(
        "INSERT INTO subscriptions (user_id, receipt_photo, months, price_charged, target_listing_id, status, created_at) "
        "VALUES (?, ?, 1, ?, ?, 'pending', ?)",
        (uid, receipt_file_id, price, target_listing_id, now_str()),
    )
    conn.commit()
    sub_id = cur.lastrowid
    conn.close()

    fn = esc_html(tg_user.get("fn") or "")
    un = f" (@{esc_html(tg_user['un'])})" if tg_user.get("un") else ""
    caption = (
        f"\U0001F4B3 <b>Yangi obuna so'rovi (veb-saytdan)</b> #{sub_id}\n\n"
        f"\U0001F464 {fn}{un}\n"
        f"\U0001F194 user_id: {uid}\n"
        f"\U0001F4B0 Summasi: {price:,} so'm"
    )
    keyboard = {"inline_keyboard": [
        [
            {"text": "✅ Tasdiqlash", "callback_data": f"admin_approve_sub_{sub_id}"},
            {"text": "❌ Rad etish", "callback_data": f"admin_reject_sub_{sub_id}"},
        ],
        [{"text": "\U0001F464 Profilga o'tish", "url": f"tg://user?id={uid}"}],
    ]}
    async with httpx.AsyncClient(timeout=20) as client:
        for admin_id in ADMIN_IDS:
            try:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    json={"chat_id": admin_id, "photo": receipt_file_id, "caption": caption,
                          "parse_mode": "HTML", "reply_markup": keyboard},
                )
            except Exception:
                logger.exception("Obuna so'rovi haqida adminga (%s) xabar yuborib bo'lmadi", admin_id)

    return {"ok": True}



