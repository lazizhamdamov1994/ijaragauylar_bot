"""
Ommaviy sahifalar: bosh sahifa, e'lon tafsiloti, subarenda, e'lon joylash
(+ veb-saytdan yuborilgan e'lonni botning moderatsiya navbatiga yuborish).
"""
import asyncio
import json as _json
import logging
import os
import re
import urllib.parse
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse

from common.config import (
    ADMIN_IDS,
    BOT_TOKEN,
    BOT_USERNAME,
    CARD_HOLDER,
    CHANNEL_USERNAME,
    INSTAGRAM_URL,
    SITE_NAME,
    SITE_URL,
)
from common.db import db, get_favorite_listing_ids, get_price_history, get_setting, has_prior_rejected_listing, is_phone_blocked, now_str
from common.telegram_media import watermark_photo_bytes_list
from common.ai import ai_features_enabled, ai_screen_for_scam

from bot.db import get_listing, set_listing_scam_warning, update_listing_status
from bot.admin_moderation import log_channel_post

from web.auth import _client_ip, get_current_tg_user, is_web_subscribed
from web.listings_data import (
    PER_PAGE,
    current_card_number,
    current_listing_price,
    get_related_listings,
    get_site_listing,
    get_site_listings,
    normalize_phone_web,
    post_listing_to_channel,
    record_web_submission,
    site_stats_summary,
    web_submissions_today,
)
from web.render import (
    CATEGORY_LABELS,
    DISTRICT_SLUGS,
    DISTRICT_TO_SLUG,
    ICONS,
    RENTAL_TYPE_LABELS,
    TASHKENT_DISTRICTS,
    DEFAULT_LANG,
    display_address,
    esc_html,
    extract_district,
    get_lang,
    icon,
    mask_card_holder,
    photo_url,
    render_footer,
    render_head,
    render_header,
    render_listing_card,
    t,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_WEB_LISTING_PHOTOS = 10
MAX_WEB_SUBMISSIONS_PER_IP_PER_DAY = 3

_SORT_OPTIONS = ("", "yangi", "arzon", "qimmat")


@router.get("/", response_class=HTMLResponse)
def homepage(request: Request, hudud: str = Query(""), xona: str = Query(""), page: int = Query(1, ge=1), rental_type: str = Query(""), sort: str = Query("")):
    return _listings_page(request, hudud, xona, page, rental_type, "/", sort=sort)


@router.get("/toshkent/{slug}", response_class=HTMLResponse)
def district_page(request: Request, slug: str, xona: str = Query(""), page: int = Query(1, ge=1), rental_type: str = Query(""), sort: str = Query("")):
    """Har bir tuman uchun alohida, doimiy URL (SEO uchun) - masalan
    /toshkent/chilonzor. Homepage bilan BIR XIL shablon (_listings_page),
    faqat hudud oldindan tanlangan va sarlavha/tavsif/H1 shu tumanga mos."""
    district_name = DISTRICT_SLUGS.get(slug.lower())
    if not district_name:
        raise HTTPException(status_code=404)
    return _listings_page(request, district_name, xona, page, rental_type, f"/toshkent/{slug}", district_name=district_name, sort=sort)


_ROOM_SLUG_RE = re.compile(r"^([1-9])-xonali$")


@router.get("/toshkent/{slug}/{room_slug}", response_class=HTMLResponse)
def district_rooms_page(request: Request, slug: str, room_slug: str, page: int = Query(1, ge=1), rental_type: str = Query(""), sort: str = Query("")):
    """Tuman + xonalar soni bo'yicha alohida URL - masalan
    /toshkent/yunusobod/2-xonali."""
    district_name = DISTRICT_SLUGS.get(slug.lower())
    room_match = _ROOM_SLUG_RE.match(room_slug)
    if not district_name or not room_match:
        raise HTTPException(status_code=404)
    xona = room_match.group(1)
    return _listings_page(request, district_name, xona, page, rental_type, f"/toshkent/{slug}/{room_slug}", district_name=district_name, sort=sort)


def _listings_page(
    request: Request, hudud: str, xona: str, page: int, rental_type: str,
    canonical_path: str, district_name: str = "", sort: str = "",
) -> HTMLResponse:
    lang = get_lang(request)
    if sort not in _SORT_OPTIONS:
        sort = ""
    listings, total = get_site_listings(hudud=hudud, xona=xona, page=page, rental_type=rental_type, sort=sort)
    stats = site_stats_summary()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    tg_user = get_current_tg_user(request)
    favorited_ids = get_favorite_listing_ids(tg_user["uid"]) if tg_user else frozenset()

    district_options = "".join(
        f'<option value="{d}" {"selected" if d.lower() == hudud.lower() else ""}>{d}</option>'
        for d in TASHKENT_DISTRICTS
    )

    def rt_url(rt):
        parts = []
        if canonical_path == "/" and hudud:
            parts.append(f"hudud={urllib.parse.quote(hudud)}")
        if xona:
            parts.append(f"xona={xona}")
        if rt:
            parts.append(f"rental_type={rt}")
        if sort:
            parts.append(f"sort={sort}")
        if lang != DEFAULT_LANG:
            parts.append(f"lang={lang}")
        return f"{canonical_path}?{'&'.join(parts)}" if parts else canonical_path

    def sort_url(s):
        parts = []
        if canonical_path == "/" and hudud:
            parts.append(f"hudud={urllib.parse.quote(hudud)}")
        if xona:
            parts.append(f"xona={xona}")
        if rental_type:
            parts.append(f"rental_type={rental_type}")
        if s:
            parts.append(f"sort={s}")
        if lang != DEFAULT_LANG:
            parts.append(f"lang={lang}")
        return f"{canonical_path}?{'&'.join(parts)}" if parts else canonical_path

    sort_options_html = "".join(
        f'<option value="{sort_url(key)}" {"selected" if sort == key else ""}>{t(lang, tkey)}</option>'
        for key, tkey in [("", "sort_tanlangan"), ("yangi", "sort_yangi"), ("arzon", "sort_arzon"), ("qimmat", "sort_qimmat")]
    )

    rt_tabs_html = "".join(
        f'<a href="{rt_url(key)}" class="rt-tab{" active" if rental_type == key else ""}">{icon(ikey, 15) if ikey else ""}{t(lang, tkey)}</a>'
        for key, tkey, ikey in [
            ("", "rt_all", ""), ("uzoq_muddat", "rt_uzoq_muddat", "home"), ("kunlik", "rt_kunlik", "calendar"),
            ("dacha", "rt_dacha", "tree"), ("mehmonxona", "rt_mehmonxona", "bed"),
        ]
    )

    if listings:
        cards_html = "".join(render_listing_card(l, favorited_ids) for l in listings)
    else:
        cards_html = f"""<div class="empty-state" style="grid-column:1/-1;">
            <div class="icon">{icon('search', 40)}</div>
            <div>{t(lang,'empty_listings')}</div>
        </div>"""

    pag_html = ""
    if total_pages > 1:
        def page_url(p):
            return (f"?page={p}" + (f"&hudud={hudud}" if hudud else "") + (f"&xona={xona}" if xona else "")
                    + (f"&rental_type={rental_type}" if rental_type else "") + (f"&sort={sort}" if sort else "")
                    + (f"&lang={lang}" if lang != DEFAULT_LANG else ""))

        WINDOW = 5
        start_p = max(1, min(page - WINDOW // 2, total_pages - WINDOW + 1))
        end_p = min(total_pages, start_p + WINDOW - 1)
        start_p = max(1, end_p - WINDOW + 1)

        links = []
        if page > 1:
            links.append(f'<a href="{page_url(page-1)}" class="pg-arrow">{icon("chevron_left", 15)}</a>')
        for p in range(start_p, end_p + 1):
            if p == page:
                links.append(f'<span class="active">{p}</span>')
            else:
                links.append(f'<a href="{page_url(p)}">{p}</a>')
        if page < total_pages:
            links.append(f'<a href="{page_url(page+1)}" class="pg-arrow">{icon("chevron_right", 15)}</a>')
        pag_html = f'<div class="pagination">{"".join(links)}</div>'

    if district_name and xona:
        title = t(lang, "seo_district_rooms_title", district=district_name, xona=xona)
        description = t(lang, "seo_district_rooms_desc", district=district_name, xona=xona, active=total)
        hero_title_text = t(lang, "district_hero_title", district=district_name)
    elif district_name:
        title = t(lang, "seo_district_title", district=district_name)
        description = t(lang, "seo_district_desc", district=district_name, active=total)
        hero_title_text = t(lang, "district_hero_title", district=district_name)
    else:
        title = t(lang, "seo_home_title")
        description = t(lang, "seo_home_desc", active=stats['active'])
        hero_title_text = t(lang, "hero_title")
    same_as = [u for u in (f"https://t.me/{CHANNEL_USERNAME}" if CHANNEL_USERNAME else "", INSTAGRAM_URL) if u]
    org_data = {
        "@context": "https://schema.org",
        "@type": "RealEstateAgent",
        "name": SITE_NAME,
        "url": SITE_URL or "",
        "logo": f"{SITE_URL}/logo.png" if SITE_URL else "",
        "areaServed": {"@type": "City", "name": "Toshkent"},
        "sameAs": same_as,
    }
    org_json_ld = f'<script type="application/ld+json">{_json.dumps(org_data, ensure_ascii=False)}</script>'

    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
{render_head(title, description, canonical_path, lang=lang)}
{org_json_ld}
</head>
<body>
{render_header(lang, canonical_path)}

<section class="hero">
  <div class="wrap">
    <h1>{hero_title_text}</h1>
    <p class="sub">{t(lang,'hero_sub')}</p>
    <form class="search-pill" method="get" action="/">
      <input type="hidden" name="lang" value="{lang}">
      <div class="seg cs-wrap">
        <label>{t(lang,'search_district_label')}</label>
        <select name="hudud">
          <option value="">{t(lang,'search_all_districts')}</option>
          {district_options}
        </select>
      </div>
      <div class="seg cs-wrap">
        <label>{t(lang,'search_rooms_label')}</label>
        <select name="xona">
          <option value="">{t(lang,'search_rooms_any')}</option>
          <option value="1" {"selected" if xona=="1" else ""}>1</option>
          <option value="2" {"selected" if xona=="2" else ""}>2</option>
          <option value="3" {"selected" if xona=="3" else ""}>3</option>
          <option value="4" {"selected" if xona=="4" else ""}>4+</option>
        </select>
      </div>
      <button type="submit">{icon('search', 16)} {t(lang,'search_btn')}</button>
    </form>
    <div class="rt-tabs">{rt_tabs_html}</div>
    <button type="button" class="hero-ai-cta" onclick="document.getElementById('ai-chat-toggle').click()">
      <span class="hero-ai-cta-icon">{icon('sparkle', 20)}</span>
      <span>
        <span class="hero-ai-cta-title">{t(lang,'hero_ai_cta_title')}</span>
        <span class="hero-ai-cta-sub">{t(lang,'hero_ai_cta_sub')}</span>
      </span>
    </button>
  </div>
</section>

<div class="stats-strip">
  <div class="wrap">
    <div class="inner">
      <div class="stat-item"><div class="num">{stats['active']}+</div><div class="lbl">{t(lang,'stat_active')}</div></div>
      <div class="stat-item"><div class="num">{stats['users']}+</div><div class="lbl">{t(lang,'stat_users')}</div></div>
      <div class="stat-item"><div class="num">100%</div><div class="lbl">{t(lang,'stat_nofee')}</div></div>
    </div>
  </div>
</div>

<main class="wrap">
  <div class="section-head">
    <div class="section-head-title">
      <h2>{t(lang,'section_search_results') if (hudud or xona) else t(lang,'section_latest')}</h2>
      <span class="count">{t(lang,'section_count_suffix', n=total)}</span>
    </div>
    <div class="cs-wrap sort-select">
      <label>{t(lang,'sort_label')}</label>
      <select onchange="location.href=this.value">
        {sort_options_html}
      </select>
    </div>
  </div>
  <div class="listing-grid">
    {cards_html}
  </div>
  {pag_html}
</main>

<section class="phone-check-section">
  <div class="wrap">
    <div class="phone-check-box">
      <h3>{icon('shield', 20)} {t(lang,'phone_check_title')}</h3>
      <p>{t(lang,'phone_check_desc')}</p>
      <div class="phone-check-form">
        <input type="tel" id="phoneCheckInput" placeholder="{t(lang,'phone_check_placeholder')}" onkeydown="if(event.key==='Enter')checkPhoneNumber()">
        <button type="button" onclick="checkPhoneNumber()">{icon('search', 15)} {t(lang,'phone_check_btn')}</button>
      </div>
      <div id="phoneCheckResult"></div>
    </div>
  </div>
</section>
<script>
async function checkPhoneNumber() {{
  const input = document.getElementById('phoneCheckInput');
  const resultEl = document.getElementById('phoneCheckResult');
  const phone = input.value.trim();
  if (!phone) return;
  resultEl.className = 'pc-result';
  resultEl.textContent = "{t(lang,'phone_check_checking')}";
  try {{
    const res = await fetch('/api/phone-check?phone=' + encodeURIComponent(phone));
    if (!res.ok) {{
      resultEl.className = 'pc-result pc-error';
      resultEl.textContent = "{t(lang,'phone_check_invalid')}";
      return;
    }}
    const data = await res.json();
    if (data.blocked) {{
      resultEl.className = 'pc-result pc-blocked';
      resultEl.textContent = "⚠️ {t(lang,'phone_check_blocked')}";
    }} else {{
      resultEl.className = 'pc-result pc-ok';
      resultEl.textContent = "✅ {t(lang,'phone_check_ok')}";
    }}
  }} catch (err) {{
    resultEl.className = 'pc-result pc-error';
    resultEl.textContent = "{t(lang,'phone_check_error')}";
  }}
}}

// Native <select> ochilganda brauzerning "arzon" standart dropdown
// ro'yxati o'rniga, saytning o'zi dizaynidagi moslashuvchan ro'yxatni
// ko'rsatadi (native select ekranda saqlanadi - JS o'chirilsa ham forma
// ishlayveradi, faqat vizual jihatdan yashiriladi).
function enhanceSelect(select) {{
  const wrap = select.closest('.cs-wrap');
  if (!wrap || wrap.dataset.csDone) return;
  wrap.dataset.csDone = '1';

  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'cs-trigger';
  const labelSpan = document.createElement('span');
  labelSpan.className = 'cs-label';
  const arrow = document.createElement('span');
  arrow.className = 'cs-arrow';
  trigger.appendChild(labelSpan);
  trigger.appendChild(arrow);

  const menu = document.createElement('div');
  menu.className = 'cs-menu';

  function updateLabel() {{
    const sel = select.options[select.selectedIndex];
    labelSpan.textContent = sel ? sel.textContent : '';
  }}

  Array.from(select.options).forEach(opt => {{
    const item = document.createElement('div');
    item.className = 'cs-option' + (opt.selected ? ' selected' : '');
    item.textContent = opt.textContent;
    item.addEventListener('click', () => {{
      select.value = opt.value;
      select.dispatchEvent(new Event('change', {{ bubbles: true }}));
      updateLabel();
      menu.querySelectorAll('.cs-option').forEach(c => c.classList.remove('selected'));
      item.classList.add('selected');
      wrap.classList.remove('open');
    }});
    menu.appendChild(item);
  }});

  trigger.addEventListener('click', (e) => {{
    e.stopPropagation();
    document.querySelectorAll('.cs-wrap.open').forEach(w => {{ if (w !== wrap) w.classList.remove('open'); }});
    wrap.classList.toggle('open');
  }});

  updateLabel();
  wrap.classList.add('cs-enhanced');
  wrap.insertBefore(trigger, select);
  wrap.appendChild(menu);
}}
document.addEventListener('click', () => {{
  document.querySelectorAll('.cs-wrap.open').forEach(w => w.classList.remove('open'));
}});
document.querySelectorAll('.cs-wrap select').forEach(enhanceSelect);
</script>

<section class="why-section">
  <div class="wrap">
    <div class="section-head"><h2>{t(lang,'why_title')}</h2></div>
    <div class="why-grid">
      <div class="why-item"><div class="icon">{icon('coin', 26)}</div><h3>{t(lang,'why1_title')}</h3><p>{t(lang,'why1_desc')}</p></div>
      <div class="why-item"><div class="icon">{icon('shield', 26)}</div><h3>{t(lang,'why2_title')}</h3><p>{t(lang,'why2_desc')}</p></div>
      <div class="why-item"><div class="icon">{icon('bolt', 26)}</div><h3>{t(lang,'why3_title')}</h3><p>{t(lang,'why3_desc')}</p></div>
      <div class="why-item"><div class="icon">{icon('map', 26)}</div><h3>{t(lang,'why4_title')}</h3><p>{t(lang,'why4_desc')}</p></div>
    </div>
  </div>
</section>

<section class="districts-section">
  <div class="wrap">
    <div class="section-head"><h2>{t(lang,'browse_districts_title')}</h2></div>
    <div class="districts-grid">
      {"".join(f'<a href="/toshkent/{DISTRICT_TO_SLUG[d]}" class="district-chip">{d}</a>' for d in TASHKENT_DISTRICTS)}
    </div>
  </div>
</section>

{render_footer(lang)}
</body>
</html>"""
    return HTMLResponse(html)


# ============================= E'LON SAHIFASI =============================

@router.get("/uy/{listing_id}", response_class=HTMLResponse)
def listing_detail(request: Request, listing_id: int):
    lang = get_lang(request)
    l = get_site_listing(listing_id)
    if not l:
        # MUHIM (SEO): muddati o'tgan/olib tashlangan e'lon uchun "quruq"
        # 404 sahifasi o'rniga - shu sahifaga kelgan tashrifchi (va Google)
        # hozirgi FAOL e'lonlardan bir nechtasini ko'radi. Shu orqali
        # sahifa "o'lik tugash" bo'lmaydi va sayt ichidagi havola qiymati
        # (link equity) yo'qolmaydi.
        tg_user = get_current_tg_user(request)
        favorited_ids = get_favorite_listing_ids(tg_user["uid"]) if tg_user else frozenset()
        fallback_listings, _ = get_site_listings(page=1)
        fallback_html = ""
        if fallback_listings:
            fallback_cards = "".join(render_listing_card(r, favorited_ids) for r in fallback_listings[:6])
            fallback_html = f"""<div class="related-strip">
  <div class="section-head"><h2>{t(lang,'related_title')}</h2></div>
  <div class="listing-grid">{fallback_cards}</div>
</div>"""
        not_found_head = render_head(t(lang,'not_found_title'), t(lang,'not_found_desc'), f"/uy/{listing_id}", lang=lang)
        not_found_body = (
            f"<body>{render_header(lang, f'/uy/{listing_id}')}<main class='wrap'><div class='empty-state'>{icon('sad', 46)}"
            f"<div style='margin-top:10px;'>{t(lang,'not_found_body')}</div><br>"
            f"<a href='/' class='btn-cta' style='background:#0f1b2e;'>{t(lang,'back_home_btn')}</a></div>"
            f"{fallback_html}</main>{render_footer(lang)}</body>"
        )
        return HTMLResponse(
            f"<!DOCTYPE html><html lang=\"{lang}\"><head>{not_found_head}</head>{not_found_body}</html>",
            status_code=404,
        )

    addr = display_address(l)
    photos = l.get("photos") or []
    photo_urls = [photo_url(p) for p in photos]
    main_photo = photo_urls[0] if photo_urls else ""

    is_quick = bool(l.get("is_quick"))
    moljal = (l.get("moljal") or "").strip()
    xona = (l.get("xona") or "").strip()
    kimlarga = (l.get("kimlarga") or "").strip()
    qulaylik = (l.get("qulaylik") or "").strip()
    description_text = qulaylik or (l.get("raw_text") or "").strip() or t(lang,'no_desc')

    # Narx tarixi - agar e'lon egasi narxni tahrirlash orqali o'zgartirgan
    # bo'lsa (/kabinet yoki bot), shu yerda ko'rinadi - tashrifchiga narx
    # o'zgarishi shaffof bo'ladi.
    price_hist = get_price_history(l["id"])
    price_history_html = ""
    if price_hist:
        hist_items = "".join(
            f'<div class="price-history-item"><span class="ph-date">{(h["changed_at"] or "")[:10]}</span>'
            f'<span class="ph-old">{esc_html(h["old_narx"] or "")}</span> → <span class="ph-new">{esc_html(h["new_narx"] or "")}</span></div>'
            for h in price_hist
        )
        price_history_html = f'<div class="price-history"><h3>{icon("coin",16)} {t(lang,"price_history_title")}</h3>{hist_items}</div>'

    # ---- Svayp qilinadigan (mobil uchun tabiiy touch-swipe) rasm galereyasi + Lightbox ----
    if photo_urls:
        slides = "".join(f'<div class="gs-slide"><img src="{u}" alt="{esc_html(addr)}" loading="{"eager" if i==0 else "lazy"}" onclick="openLightbox({i})"></div>' for i, u in enumerate(photo_urls))
        dots = "".join(f'<span class="gs-dot{" active" if i==0 else ""}"></span>' for i in range(len(photo_urls))) if len(photo_urls) > 1 else ""
        counter = f'<div class="gs-counter">1 / {len(photo_urls)}</div>' if len(photo_urls) > 1 else ""
        arrows = ""
        if len(photo_urls) > 1:
            arrows = (
                f'<button class="gs-arrow gs-arrow-left" onclick="scrollGallery(-1)" aria-label="Oldingi">{icon("chevron_left", 20)}</button>'
                f'<button class="gs-arrow gs-arrow-right" onclick="scrollGallery(1)" aria-label="Keyingi">{icon("chevron_right", 20)}</button>'
            )
        expand_btn = f'<button class="gs-expand" onclick="openLightbox(gsCurrentIndex)" aria-label="Kattalashtirish">{icon("expand", 15)}</button>'
        gallery_html = f"""<div class="gallery-scroll" id="gallery">{slides}</div>
        {counter}
        {arrows}
        {expand_btn}
        <div class="gs-dots" id="gsDots">{dots}</div>"""
        lightbox_slides = "".join(f'<div class="lb-slide"><img src="{u}" alt="{esc_html(addr)}"></div>' for u in photo_urls)
        lightbox_nav = ""
        if len(photo_urls) > 1:
            lightbox_nav = (
                f'<button class="lb-arrow lb-arrow-left" onclick="lbNav(-1)" aria-label="Oldingi">{icon("chevron_left", 26)}</button>'
                f'<button class="lb-arrow lb-arrow-right" onclick="lbNav(1)" aria-label="Keyingi">{icon("chevron_right", 26)}</button>'
            )
        lightbox_html = f"""<div id="lightbox" class="lightbox">
          <button class="lb-close" onclick="closeLightbox()" aria-label="Yopish">{icon("close", 20)}</button>
          <div class="lb-track" id="lbTrack">{lightbox_slides}</div>
          {lightbox_nav}
        </div>"""
    else:
        gallery_html = f'<div class="gallery-scroll gs-empty">{icon("camera_off", 42)}<div style="margin-top:8px;font-size:13px;">{t(lang,"no_photo")}</div></div>'
        lightbox_html = ""

    bot_link = f"https://t.me/{BOT_USERNAME}?start=phone_{l['id']}" if BOT_USERNAME else "#"

    tg_user = get_current_tg_user(request)
    favorited_ids = get_favorite_listing_ids(tg_user["uid"]) if tg_user else frozenset()
    is_favorited = l["id"] in favorited_ids
    has_limit = False
    if tg_user:
        has_limit, _limit_expire = is_web_subscribed(tg_user["uid"])

    if has_limit:
        phone_cta_html = f'<a href="tel:{esc_html(l["telefon"])}" class="sidebar-cta">{icon("phone", 16)} {esc_html(l["telefon"])}</a>'
        sidebar_note_html = f'<div class="sidebar-note">{t(lang,"sidebar_note_limit_active")}</div>'
    else:
        # Limiti yo'q (kirgan yoki kirmagan, farqi yo'q) - tugma har doim
        # oddiy "Uy egasi raqamini ko'rish" deb turadi. Bosilganda KARTA
        # DARHOL chiqmaydi - avval e'tiborni tortadigan "Limit kerak"
        # ogohlantirishi ko'rinadi; karta va chek yuklash oynasi faqat
        # "Limit sotib olish" bosilgach, /kabinet/limit sahifasida ochiladi.
        buy_next = f"/kabinet/limit?listing_id={l['id']}"
        buy_link = buy_next if tg_user else f"/login?next={urllib.parse.quote(buy_next, safe='')}"
        phone_cta_html = (
            f'<button type="button" class="sidebar-cta" style="width:100%;border:none;cursor:pointer;" '
            f'onclick="document.getElementById(\'phoneLock\').classList.add(\'open\');this.style.display=\'none\';">'
            f'{icon("phone", 16)} {t(lang,"sidebar_cta_view_phone")}</button>'
            f'<div id="phoneLock" class="phone-lock paywall-alert">'
            f'{icon("alert", 26)}'
            f'<p class="phone-lock-text">{t(lang,"paywall_no_limit_msg")}</p>'
            f'<a href="{buy_link}" class="paywall-cta">{t(lang,"kb_buy_limit")} →</a>'
            f'</div>'
        )
        sidebar_note_html = ""

    # Ko'rish vaqtini so'rash - telefon ko'rsatish BILAN AYNAN BIR XIL
    # to'lov devori (paywall) qoidasi (has_limit) orqali tekshiriladi, shu
    # orqali bu Limit sotib olish funksiyasini aylanib o'tish yo'liga
    # aylanib qolmaydi (bot/flow_viewing.py'dagi bilan bir xil g'oya).
    if has_limit:
        viewing_cta_html = f"""<button type="button" class="sidebar-cta-secondary" style="margin-bottom:10px;" onclick="document.getElementById('viewingForm').classList.toggle('open')">
          {icon('calendar', 15)} {t(lang,'viewing_request_btn')}
        </button>
        <form id="viewingForm" class="inquiry-form" onsubmit="return submitViewing(event)">
          <input required name="requested_time" placeholder="{t(lang,'viewing_time_ph')}" maxlength="200">
          <button type="submit" class="inquiry-submit">{icon("send", 14)} {t(lang,'viewing_send')}</button>
          <div id="viewingSuccess" class="inquiry-success">{icon('check_circle',15)} {t(lang,'viewing_success')}</div>
        </form>"""
    else:
        viewing_cta_html = (
            f'<button type="button" class="sidebar-cta-secondary" style="margin-bottom:10px;" '
            f'onclick="document.getElementById(\'phoneLock\').classList.add(\'open\');">'
            f'{icon("calendar", 15)} {t(lang,"viewing_request_btn")}</button>'
        )

    paid_badge = f'<span class="badge paid">{icon("bolt", 13)} {t(lang,"badge_top")}</span>' if (l.get("price_charged") or 0) > 0 else ""
    cat = l.get("category")
    cat_badge_detail = ""
    if cat and cat in CATEGORY_LABELS:
        label, css_cls = CATEGORY_LABELS[cat]
        cat_badge_detail = f'<span class="badge {css_cls}">{label}</span>'
    rtype = l.get("rental_type")
    rt_badge_detail = ""
    if rtype and rtype in RENTAL_TYPE_LABELS:
        rt_label, rt_css_cls = RENTAL_TYPE_LABELS[rtype]
        rt_badge_detail = f'<span class="badge {rt_css_cls}">{rt_label}</span>'
    quick_badge_detail = '<span class="badge badge-quick">⚡ Tezkor e\'lon</span>' if is_quick else ""

    map_html = ""
    if l.get("latitude") and l.get("longitude"):
        map_html = f"""<div id="detail-map"></div>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  try {{
    const dmap = L.map('detail-map', {{ zoomControl: false }}).setView([{l['latitude']}, {l['longitude']}], 15);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ attribution: '&copy; OpenStreetMap' }}).addTo(dmap);
    L.circleMarker([{l['latitude']}, {l['longitude']}], {{ radius: 10, fillColor: '#FF3B5C', color: '#fff', weight: 2, fillOpacity: 0.9 }}).addTo(dmap);
  }} catch (err) {{
    const el = document.getElementById('detail-map');
    if (el) el.outerHTML = '<div style="height:270px;border-radius:20px;margin-top:22px;background:var(--bg-soft);display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:13px;">Xarita yuklanmadi</div>';
  }}
</script>"""

    related = get_related_listings(l["id"], l.get("manzil") or addr)
    related_html = ""
    if related:
        related_cards = "".join(render_listing_card(r, favorited_ids) for r in related)
        related_html = f"""<div class="related-strip">
  <div class="section-head"><h2>{t(lang,'related_title')}</h2></div>
  <div class="listing-grid">{related_cards}</div>
</div>"""

    facts_html = ""
    if xona:
        facts_html += f'<div class="fact-box"><div class="fl">{t(lang,"fact_rooms")}</div><div class="fv">{icon("bed", 16)} {esc_html(xona)}</div></div>'
    if kimlarga:
        facts_html += f'<div class="fact-box"><div class="fl">{t(lang,"fact_for_whom")}</div><div class="fv">{icon("users", 16)} {esc_html(kimlarga)}</div></div>'
    facts_block = f'<div class="detail-facts">{facts_html}</div>' if facts_html else ""
    moljal_block = f'<div class="detail-addr">{icon("target", 15)} {esc_html(moljal)}</div>' if moljal else ""

    xona_fallback = {"uz": "Ijaraga uy", "ru": "Аренда жилья", "en": "Rental property"}.get(lang, "Ijaraga uy")
    title = t(lang, "seo_listing_title", addr=esc_html(addr), price=esc_html(l['narx']))
    description = t(lang, "seo_listing_desc", xona=esc_html(xona) or xona_fallback, price=esc_html(l['narx']))

    # MUHIM: bu yerda ijara narxi erkin matn ("2 mln so'm", "$400" va h.k.),
    # aniq raqam va valyuta emas - shuning uchun schema.org "Product/Offer"
    # (Google buni real narx deb kutadi va Search Console'da xatolik chiqaradi)
    # o'rniga real ko'chmas mulk mazmunini to'g'ri ifodalaydigan
    # "RealEstateListing" ishlatiladi - soxta narx/valyuta ma'lumoti yo'q.
    json_ld = f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "RealEstateListing",
  "name": {_json.dumps(addr)},
  "description": {_json.dumps(description_text[:300])},
  "url": {_json.dumps(f"{SITE_URL}/uy/{listing_id}")},
  "image": {_json.dumps(photo_urls[0] if photo_urls else '')},
  "address": {{
    "@type": "PostalAddress",
    "streetAddress": {_json.dumps(addr)},
    "addressLocality": "Toshkent",
    "addressCountry": "UZ"
  }}
}}
</script>"""

    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
{render_head(title, description, f"/uy/{listing_id}", main_photo, lang=lang)}
{json_ld}
</head>
<body>
{render_header(lang, f"/uy/{listing_id}")}
<main class="wrap">
  <div class="breadcrumb"><a href="/">{t(lang,'breadcrumb_home')}</a> / {esc_html(addr)}</div>

  <div class="detail-grid">
    <div>
      <div class="gallery-wrap">{gallery_html}</div>
      {lightbox_html}

      <div class="detail-title-row">
        <h1 class="detail-title">{esc_html(addr)}</h1>
        <button type="button" class="detail-fav-btn{' active' if is_favorited else ''}" data-listing-id="{l['id']}"
          onclick="toggleFavorite({l['id']}, this)">
          <span class="fav-icon-outline">{icon('heart', 17)}</span><span class="fav-icon-filled">{icon('heart_filled', 17)}</span>
          <span class="fav-label-outline">{t(lang,'fav_save')}</span><span class="fav-label-filled">{t(lang,'fav_saved')}</span>
        </button>
      </div>
      {moljal_block}
      <div class="detail-badges">
        {paid_badge}
        {cat_badge_detail}
        {rt_badge_detail}
        {quick_badge_detail}
        <span class="badge trust">{icon("check_circle", 13)} {t(lang,'badge_verified')}</span>
      </div>

      {facts_block}

      <div class="desc-block">
        <h3>{icon("sparkle", 16)} {t(lang,'desc_title')}</h3>
        <p>{esc_html(description_text)}</p>
      </div>

      {price_history_html}
      {map_html}
    </div>

    <div>
      <div class="sidebar-card">
        <div class="sidebar-price">{esc_html(l['narx'])}{f'<span class="sidebar-price-approx">{esc_html(l["narx_approx"])}</span>' if l.get('narx_approx') else ''}</div>
        {phone_cta_html}
        {viewing_cta_html}
        {sidebar_note_html}
        <div class="sidebar-share">
          <button onclick="shareListing()">{icon("share", 14)} {t(lang,'share_btn')}</button>
          <button onclick="copyLink(this)">{icon("copy", 14)} {t(lang,'copy_btn')}</button>
        </div>

        <div class="inquiry-toggle" onclick="toggleInquiry()">
          {icon("message", 15)} <span>{t(lang,'inquiry_toggle')}</span>
        </div>
        <form id="inquiryForm" class="inquiry-form" onsubmit="return submitInquiry(event)">
          <input required name="name" placeholder="{t(lang,'inquiry_name_ph')}" maxlength="100">
          <input required name="phone" placeholder="{t(lang,'inquiry_phone_ph')}" maxlength="30">
          <textarea name="message" placeholder="{t(lang,'inquiry_msg_ph')}" maxlength="500" rows="3"></textarea>
          <button type="submit" class="inquiry-submit">{icon("send", 14)} {t(lang,'inquiry_send')}</button>
          <div id="inquirySuccess" class="inquiry-success">{icon("check_circle", 15)} {t(lang,'inquiry_success')}</div>
        </form>
      </div>
    </div>
  </div>

  {related_html}
</main>

<script>
function toggleInquiry() {{
  document.getElementById('inquiryForm').classList.toggle('open');
}}
async function submitInquiry(e) {{
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form).entries());
  data.listing_id = {l['id']};
  const btn = form.querySelector('.inquiry-submit');
  btn.disabled = true;
  try {{
    const res = await fetch('/api/listing-inquiry', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(data)
    }});
    if (res.ok) {{
      form.querySelectorAll('input, textarea, button').forEach(el => el.style.display = 'none');
      document.getElementById('inquirySuccess').style.display = 'flex';
    }} else {{
      alert("{t(lang,'inquiry_error')}");
      btn.disabled = false;
    }}
  }} catch (err) {{
    alert("{t(lang,'inquiry_error')}");
    btn.disabled = false;
  }}
  return false;
}}
async function submitViewing(e) {{
  e.preventDefault();
  const form = e.target;
  const btn = form.querySelector('.inquiry-submit');
  btn.disabled = true;
  try {{
    const res = await fetch('/api/kabinet/viewing-request', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{listing_id: {l['id']}, requested_time: form.requested_time.value}})
    }});
    if (res.ok) {{
      form.querySelectorAll('input, button').forEach(el => el.style.display = 'none');
      document.getElementById('viewingSuccess').style.display = 'flex';
    }} else {{
      alert("{t(lang,'inquiry_error')}");
      btn.disabled = false;
    }}
  }} catch (err) {{
    alert("{t(lang,'inquiry_error')}");
    btn.disabled = false;
  }}
  return false;
}}
</script>
{render_footer(lang)}

<script>
function shareListing() {{
  if (navigator.share) {{
    navigator.share({{ title: document.title, url: window.location.href }});
  }} else {{
    navigator.clipboard.writeText(window.location.href);
    alert("{t(lang,'link_copied')}");
  }}
}}
function copyLink(btn) {{
  navigator.clipboard.writeText(window.location.href);
  const original = btn.innerHTML;
  btn.textContent = "\u2705 {t(lang,'copied_btn')}";
  setTimeout(() => btn.innerHTML = original, 1800);
}}
function copyCardNumber(btn, digits) {{
  navigator.clipboard.writeText(digits);
  const original = btn.innerHTML;
  btn.innerHTML = "\u2705 {t(lang,'copied_btn')}";
  setTimeout(() => btn.innerHTML = original, 1800);
}}

let gsCurrentIndex = 0;
function scrollGallery(dir) {{
  const gallery = document.getElementById('gallery');
  if (!gallery) return;
  gallery.scrollBy({{ left: dir * gallery.clientWidth, behavior: 'smooth' }});
}}
function openLightbox(idx) {{
  const lb = document.getElementById('lightbox');
  if (!lb) return;
  lbIndex = idx;
  document.getElementById('lbTrack').style.transform = 'translateX(-' + (idx * 100) + '%)';
  lb.classList.add('open');
  document.body.style.overflow = 'hidden';
}}
function closeLightbox() {{
  const lb = document.getElementById('lightbox');
  if (!lb) return;
  lb.classList.remove('open');
  document.body.style.overflow = '';
}}
let lbIndex = 0;
function lbNav(dir) {{
  const slides = document.querySelectorAll('.lb-slide');
  if (!slides.length) return;
  lbIndex = (lbIndex + dir + slides.length) % slides.length;
  document.getElementById('lbTrack').style.transform = 'translateX(-' + (lbIndex * 100) + '%)';
}}
document.addEventListener('keydown', (e) => {{
  const lb = document.getElementById('lightbox');
  if (!lb || !lb.classList.contains('open')) return;
  if (e.key === 'Escape') closeLightbox();
  if (e.key === 'ArrowLeft') lbNav(-1);
  if (e.key === 'ArrowRight') lbNav(1);
}});

(function() {{
  const gallery = document.getElementById('gallery');
  if (!gallery) return;
  const dots = document.querySelectorAll('#gsDots .gs-dot');
  const counterEl = document.querySelector('.gs-counter');
  const slideCount = dots.length;
  gallery.addEventListener('scroll', () => {{
    const idx = Math.round(gallery.scrollLeft / gallery.clientWidth);
    gsCurrentIndex = idx;
    dots.forEach((d, i) => d.classList.toggle('active', i === idx));
    if (counterEl) counterEl.textContent = (idx + 1) + ' / ' + slideCount;
  }}, {{ passive: true }});
}})();
</script>
</body>
</html>"""
    return HTMLResponse(html)


# ============================= SEO: SITEMAP VA ROBOTS =============================

# ============================= SUBARENDA =============================

@router.get("/subarenda", response_class=HTMLResponse)
def subarenda_page(request: Request):
    lang = get_lang(request)
    title = t(lang, "seo_subarenda_title")
    description = t(lang, "seo_subarenda_desc")
    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
{render_head(title, description, "/subarenda", lang=lang)}
</head>
<body>
{render_header(lang, "/subarenda")}
<section class="hero">
  <div class="wrap">
    <h1>{t(lang,'sr_hero_title')}</h1>
    <p class="sub">{t(lang,'sr_hero_sub')}</p>
  </div>
</section>
<main class="wrap" style="padding-top:40px;padding-bottom:80px;">
  <div style="max-width:520px;margin:0 auto 56px;">
    <div class="sidebar-card" style="position:static;margin-bottom:0;">
      <h2 style="font-size:19px;font-weight:800;margin-bottom:6px;">{t(lang,'sr_form_title')}</h2>
      <p style="font-size:13px;color:var(--muted);margin-bottom:18px;">{t(lang,'sr_form_sub')}</p>
      <form id="subarenda-form" onsubmit="return submitSubarenda(event)">
        <div style="margin-bottom:12px;">
          <input required name="full_name" placeholder="{t(lang,'sr_name_ph')}" style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;">
        </div>
        <div style="margin-bottom:12px;">
          <input required name="phone" placeholder="{t(lang,'sr_phone_ph')}" style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;">
        </div>
        <div style="margin-bottom:12px;">
          <input required name="manzil" placeholder="{t(lang,'sr_manzil_ph')}" style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;">
        </div>
        <div style="margin-bottom:12px;">
          <input name="xona" placeholder="{t(lang,'sr_xona_ph')}" style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;">
        </div>
        <div style="margin-bottom:18px;">
          <input name="narx_talab" placeholder="{t(lang,'sr_narx_ph')}" style="width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;font-size:14px;">
        </div>
        <button type="submit" class="sidebar-cta" style="width:100%;border:none;cursor:pointer;">{t(lang,'sr_submit_btn')}</button>
      </form>
      <div id="subarenda-success" style="display:none;text-align:center;padding:20px 0;">
        <div style="font-size:40px;margin-bottom:10px;">✅</div>
        <div style="font-weight:700;margin-bottom:6px;">{t(lang,'sr_success_title')}</div>
        <div style="font-size:13px;color:var(--muted);">{t(lang,'sr_success_sub')}</div>
      </div>
    </div>
  </div>

  <div class="why-grid">
    <div class="why-item"><div class="icon">{icon('users', 26)}</div><h3>{t(lang,'sr1_title')}</h3><p>{t(lang,'sr1_desc')}</p></div>
    <div class="why-item"><div class="icon">{icon('coin', 26)}</div><h3>{t(lang,'sr2_title')}</h3><p>{t(lang,'sr2_desc')}</p></div>
    <div class="why-item"><div class="icon">{icon('shield', 26)}</div><h3>{t(lang,'sr3_title')}</h3><p>{t(lang,'sr3_desc')}</p></div>
    <div class="why-item"><div class="icon">{icon('sparkle', 26)}</div><h3>{t(lang,'sr4_title')}</h3><p>{t(lang,'sr4_desc')}</p></div>
  </div>
</main>
{render_footer(lang)}
<script>
async function submitSubarenda(e) {{
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form).entries());
  const res = await fetch('/api/subarenda-lead', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(data)
  }});
  if (res.ok) {{
    form.style.display = 'none';
    document.getElementById('subarenda-success').style.display = 'block';
  }} else {{
    alert("{t(lang,'sr_error')}");
  }}
  return false;
}}
</script>
</body>
</html>"""
    return HTMLResponse(html)


# ============================= VEB-SAYTDAN E'LON JOYLASH SAHIFASI =============================

@router.get("/elon-joylash", response_class=HTMLResponse)
def elon_joylash_page(request: Request):
    lang = get_lang(request)
    title = t(lang, "seo_post_title")
    description = t(lang, "seo_post_desc")
    price = current_listing_price()
    card = current_card_number()
    card_grouped = " ".join(re.sub(r"\D", "", card)[i:i + 4] for i in range(0, len(re.sub(r"\D", "", card)), 4)) if card else ""

    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
{render_head(title, description, "/elon-joylash", lang=lang)}
</head>
<body>
{render_header(lang, "/elon-joylash")}

<section class="form-page-hero">
  <div class="wrap">
    <h1>{icon('sparkle', 26)} {t(lang,'ej_hero_title')}</h1>
    <p>{t(lang,'ej_hero_sub')}</p>
  </div>
</section>

<main class="wrap">
  <div class="form-shell">
    <div class="form-card">
      <div id="formStep">
        <div class="fstep-badge">{icon('shield', 13)} {t(lang,'ej_badge')}</div>
        <div id="formError" class="form-error-box"></div>

        <form id="listingForm">
          <div class="form-section-title">{icon('coin', 17)} {t(lang,'ej_section_rental_type')}</div>
          <div class="type-toggle" id="rentalTypeToggle">
            <label class="type-option active" data-rt="uzoq_muddat"><input type="radio" name="rental_type" value="uzoq_muddat" checked><div class="to-title">{icon('home', 16)} {t(lang,'rt_uzoq_muddat')}</div></label>
            <label class="type-option" data-rt="kunlik"><input type="radio" name="rental_type" value="kunlik"><div class="to-title">{icon('calendar', 16)} {t(lang,'rt_kunlik')}</div></label>
            <label class="type-option" data-rt="dacha"><input type="radio" name="rental_type" value="dacha"><div class="to-title">{icon('tree', 16)} {t(lang,'rt_dacha')}</div></label>
            <label class="type-option" data-rt="mehmonxona"><input type="radio" name="rental_type" value="mehmonxona"><div class="to-title">{icon('bed', 16)} {t(lang,'rt_mehmonxona')}</div></label>
          </div>

          <div class="form-section-title">{icon('home', 17)} {t(lang,'ej_section_house')}</div>
          <div class="form-group">
            <label>{t(lang,'ej_manzil_label')} <span class="req">*</span></label>
            <input class="form-input" name="manzil" maxlength="250" required placeholder="{t(lang,'ej_manzil_ph')}">
          </div>
          <div class="form-group">
            <label>{t(lang,'ej_moljal_label')} <span class="req">*</span></label>
            <input class="form-input" name="moljal" maxlength="250" required placeholder="{t(lang,'ej_moljal_ph')}">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>{t(lang,'ej_xona_label')} <span class="req">*</span></label>
              <input class="form-input" name="xona" maxlength="60" required placeholder="{t(lang,'ej_xona_ph')}">
            </div>
            <div class="form-group">
              <label>{t(lang,'ej_kimlarga_label')} <span class="req">*</span></label>
              <input class="form-input" name="kimlarga" maxlength="150" required placeholder="{t(lang,'ej_kimlarga_ph')}">
            </div>
          </div>
          <div class="form-group">
            <label>{t(lang,'ej_qulaylik_label')} <span class="req">*</span></label>
            <textarea class="form-textarea" name="qulaylik" maxlength="900" required placeholder="{t(lang,'ej_qulaylik_ph')}"></textarea>
          </div>
          <div class="form-group">
            <label>{t(lang,'ej_narx_label')} <span class="req">*</span></label>
            <input class="form-input" name="narx" maxlength="200" required placeholder="{t(lang,'ej_narx_ph')}">
          </div>

          <div class="form-section-title">{icon('phone', 17)} {t(lang,'ej_section_contact')}</div>
          <div class="form-row">
            <div class="form-group">
              <label>{t(lang,'ej_fullname_label')}</label>
              <input class="form-input" name="full_name" maxlength="100" placeholder="{t(lang,'ej_fullname_ph')}">
            </div>
            <div class="form-group">
              <label>{t(lang,'ej_phone_label')} <span class="req">*</span></label>
              <input class="form-input" name="telefon" maxlength="30" required placeholder="+998 90 123 45 67">
            </div>
          </div>
          <div class="form-hint" style="margin:-8px 0 14px;">{t(lang,'ej_phone_hint')}</div>

          <div class="form-section-title">{icon('map', 17)} {t(lang,'ej_section_location')}</div>
          <div class="loc-toggle-row">
            <div class="lt-label">{icon('target', 15)} {t(lang,'ej_loc_toggle')}</div>
            <label class="switch"><input type="checkbox" id="locToggle"><span class="slider"></span></label>
          </div>
          <div id="locationMap"></div>
          <input type="hidden" name="latitude" id="latInput">
          <input type="hidden" name="longitude" id="lonInput">

          <div class="form-section-title">{icon('camera_off', 17)} {t(lang,'ej_section_photos')} <span class="req">*</span></div>
          <div class="photo-drop" id="photoDrop">
            <div class="ico" style="width:30px;height:30px;margin:0 auto;color:var(--muted);">{ICONS['camera_off']}</div>
            <div class="pd-title">{t(lang,'ej_photo_drop_title')}</div>
            <div class="pd-sub">{t(lang,'ej_photo_drop_sub')}</div>
          </div>
          <input type="file" id="photoInput" accept="image/*" multiple hidden>
          <div class="photo-preview" id="photoPreview"></div>

          <div class="form-section-title">{icon('coin', 17)} {t(lang,'ej_section_type')}</div>
          <div class="type-toggle">
            <label class="type-option active" id="typeFree">
              <input type="radio" name="listing_type" value="free" checked>
              <div class="to-title">{icon('sparkle', 14)} {t(lang,'ej_type_free_title')}</div>
              <div class="to-desc">{t(lang,'ej_type_free_desc')}</div>
            </label>
            <label class="type-option" id="typePaid">
              <input type="radio" name="listing_type" value="paid">
              <div class="to-title">{icon('bolt', 14)} {t(lang,'ej_type_paid_title', price=f'{price:,}')}</div>
              <div class="to-desc">{t(lang,'ej_type_paid_desc')}</div>
            </label>
          </div>

          <div class="pay-panel" id="payPanel">
            <div class="card-box">
              <div><div style="font-size:11px;color:var(--muted);font-weight:700;margin-bottom:3px;">{t(lang,'ej_pay_card_label')}</div><div class="cb-num" id="cardNumText">{card_grouped or "—"}</div></div>
              <button type="button" onclick="copyCard()">{icon('copy', 12)} {t(lang,'ej_pay_copy')}</button>
            </div>
            <div class="form-hint" style="margin-bottom:10px;">{t(lang,'ej_pay_hint', price=f'<b>{price:,}</b>')}</div>
            <div class="photo-drop" id="receiptDrop" style="padding:16px;">
              <div class="pd-title" id="receiptLabel">{t(lang,'ej_receipt_title')}</div>
              <div class="pd-sub">{t(lang,'ej_receipt_sub')}</div>
            </div>
            <input type="file" id="receiptInput" accept="image/*" hidden>
          </div>

          <button type="submit" class="form-submit-btn" id="submitBtn">{icon('send', 16)} {t(lang,'ej_submit_btn')}</button>
          <div class="form-hint" style="text-align:center;margin-top:10px;">{t(lang,'ej_submit_note')}</div>
        </form>
      </div>

      <div id="formSuccess" class="form-success-screen" style="display:none;">
        <div class="fs-icon">{icon('check_circle', 34)}</div>
        <h2>{t(lang,'ej_success_title')}</h2>
        <p id="successText"></p>
        <a href="/" class="btn-cta" style="display:inline-flex;margin-top:20px;">{t(lang,'back_home_btn')}</a>
      </div>
    </div>
  </div>
</main>

<div style="height:60px;"></div>
{render_footer(lang)}

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
// ---- Rasm tanlash / oldindan ko'rish ----
let selectedPhotos = [];
const photoInput = document.getElementById('photoInput');
const photoDrop = document.getElementById('photoDrop');
const photoPreview = document.getElementById('photoPreview');

photoDrop.addEventListener('click', () => photoInput.click());
['dragover', 'dragleave', 'drop'].forEach(evt => {{
  photoDrop.addEventListener(evt, (e) => {{
    e.preventDefault();
    photoDrop.classList.toggle('dragover', evt === 'dragover');
    if (evt === 'drop') addPhotos(e.dataTransfer.files);
  }});
}});
photoInput.addEventListener('change', () => addPhotos(photoInput.files));

function addPhotos(fileList) {{
  for (const f of fileList) {{
    if (!f.type.startsWith('image/')) continue;
    if (selectedPhotos.length >= 10) break;
    selectedPhotos.push(f);
  }}
  renderPhotoPreview();
}}
function removePhoto(idx) {{
  selectedPhotos.splice(idx, 1);
  renderPhotoPreview();
}}
function renderPhotoPreview() {{
  photoPreview.innerHTML = selectedPhotos.map((f, i) => {{
    const url = URL.createObjectURL(f);
    return `<div class="photo-thumb"><img src="${{url}}"><button type="button" class="pt-remove" onclick="removePhoto(${{i}})">✕</button></div>`;
  }}).join('');
}}

// ---- Chek rasmi ----
let receiptFile = null;
const receiptInput = document.getElementById('receiptInput');
document.getElementById('receiptDrop').addEventListener('click', () => receiptInput.click());
receiptInput.addEventListener('change', () => {{
  if (receiptInput.files[0]) {{
    receiptFile = receiptInput.files[0];
    document.getElementById('receiptLabel').textContent = '✅ ' + receiptFile.name;
  }}
}});

// ---- Ijara turi tanlash ----
document.querySelectorAll('#rentalTypeToggle .type-option').forEach(opt => {{
  opt.addEventListener('click', () => {{
    document.querySelectorAll('#rentalTypeToggle .type-option').forEach(o => o.classList.toggle('active', o === opt));
  }});
}});

// ---- Bepul / Pullik tanlash ----
const typeFree = document.getElementById('typeFree');
const typePaid = document.getElementById('typePaid');
const payPanel = document.getElementById('payPanel');
[typeFree, typePaid].forEach(el => {{
  el.addEventListener('click', () => {{
    typeFree.classList.toggle('active', el === typeFree);
    typePaid.classList.toggle('active', el === typePaid);
    payPanel.classList.toggle('show', el === typePaid);
  }});
}});
function copyCard() {{
  navigator.clipboard.writeText("{re.sub(r'[^0-9]', '', card)}");
}}

// ---- Lokatsiya xaritasi ----
let locMap = null, locMarker = null;
document.getElementById('locToggle').addEventListener('change', function() {{
  const mapEl = document.getElementById('locationMap');
  mapEl.classList.toggle('show', this.checked);
  if (this.checked && !locMap) {{
    setTimeout(() => {{
      try {{
        locMap = L.map('locationMap').setView([41.311081, 69.240562], 12);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ attribution: '&copy; OpenStreetMap' }}).addTo(locMap);
        locMap.on('click', (e) => setLocMarker(e.latlng.lat, e.latlng.lng));
        if (navigator.geolocation) {{
          navigator.geolocation.getCurrentPosition(
            (pos) => {{ locMap.setView([pos.coords.latitude, pos.coords.longitude], 15); }},
            () => {{}}
          );
        }}
      }} catch (err) {{
        mapEl.innerHTML = '<div style="padding:16px;text-align:center;color:var(--muted);font-size:13px;">Xarita yuklanmadi. Internet aloqasini tekshiring yoki joylashuvsiz davom eting.</div>';
      }}
    }}, 50);
  }} else if (!this.checked) {{
    document.getElementById('latInput').value = '';
    document.getElementById('lonInput').value = '';
  }}
}});
function setLocMarker(lat, lon) {{
  if (locMarker) locMap.removeLayer(locMarker);
  locMarker = L.marker([lat, lon]).addTo(locMap);
  document.getElementById('latInput').value = lat;
  document.getElementById('lonInput').value = lon;
}}

// ---- Yuborish ----
const form = document.getElementById('listingForm');
const errorBox = document.getElementById('formError');
form.addEventListener('submit', async function(e) {{
  e.preventDefault();
  errorBox.classList.remove('show');

  if (selectedPhotos.length === 0) {{
    errorBox.textContent = "{t(lang,'ej_err_no_photo')}";
    errorBox.classList.add('show');
    window.scrollTo({{ top: photoDrop.offsetTop - 100, behavior: 'smooth' }});
    return;
  }}
  const isPaid = typePaid.classList.contains('active');
  if (isPaid && !receiptFile) {{
    errorBox.textContent = "{t(lang,'ej_err_no_receipt')}";
    errorBox.classList.add('show');
    return;
  }}

  const submitBtn = document.getElementById('submitBtn');
  const submitBtnHtml = submitBtn.innerHTML;
  submitBtn.disabled = true;
  submitBtn.textContent = "{t(lang,'ej_submitting')}";

  const fd = new FormData(form);
  selectedPhotos.forEach(f => fd.append('photos', f));
  if (isPaid && receiptFile) fd.append('receipt', receiptFile);

  try {{
    const res = await fetch('/api/elon-joylash', {{ method: 'POST', body: fd }});
    const data = await res.json().catch(() => ({{}}));
    if (res.ok && data.ok) {{
      document.getElementById('formStep').style.display = 'none';
      document.getElementById('formSuccess').style.display = 'block';
      document.getElementById('successText').textContent = "{t(lang,'ej_success_text', id='%ID%')}".replace('%ID%', data.listing_id);
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }} else {{
      errorBox.textContent = data.detail || "{t(lang,'ej_err_generic')}";
      errorBox.classList.add('show');
      submitBtn.disabled = false;
      submitBtn.innerHTML = submitBtnHtml;
      window.scrollTo({{ top: errorBox.offsetTop - 100, behavior: 'smooth' }});
    }}
  }} catch (err) {{
    errorBox.textContent = "{t(lang,'ej_err_network')}";
    errorBox.classList.add('show');
    submitBtn.disabled = false;
    submitBtn.innerHTML = submitBtnHtml;
  }}
}});
</script>
</body>
</html>"""
    return HTMLResponse(html)


async def notify_telegram(chat_id: int, text: str, reply_markup: dict = None):
    """Bot API orqali to'g'ridan-to'g'ri Telegram xabar yuboradi (BOT_TOKEN
    orqali) - dashboarddan botga alohida ulanishsiz."""
    if not BOT_TOKEN or not chat_id:
        return
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)
    except Exception:
        pass


# ============================= VEB-SAYTDAN E'LON JOYLASH (bot bilan to'liq integratsiya) =============================
#
# G'oya: veb-saytdan kelgan e'lon ham AYNAN bot orqali kelgan e'lon kabi
# moderatsiya navbatiga tushadi. Buning uchun:
#   1) Yuklangan rasmlar Telegram Bot API orqali (asosiy admin chatiga) yuboriladi
#      va shu yerdan Telegram file_id olinadi - baza faqat shu ID'larni saqlaydi
#      (dashboard hech qanday faylni o'zida saqlamaydi, bot bilan bir xil format).
#   2) "listings" jadvaliga status='pending' bilan yoziladi.
#   3) Barcha adminlarga XUDDI botning o'ziga xos "Tasdiqlash/Rad etish" tugmalari
#      (callback_data: admin_approve_listing_ID / admin_reject_listing_ID) bilan
#      xabar yuboriladi - bu tugmalarni ishlaydigan bot.py jarayoni (u alohida,
#      lekin bir xil token bilan long-polling qilib turadi) avtomatik qabul qiladi
#      va tasdiqlansa - kanalga ham, shu tufayli saytga ham chiqadi.

async def telegram_upload_photos(chat_id: int, contents: list, filenames: list) -> list:
    """Rasm baytlarini BIR MARTA Telegram'ga yuklab, file_id ro'yxatini qaytaradi.
    Shu file_id'lar keyin boshqa istalgan chatga (boshqa adminlar, kanal) QAYTA
    yuklamasdan, faqat ID orqali yuborilishi mumkin - tezkor va tejamkor.

    MUHIM: file_id olish uchun rasm biror chatga (odatda ADMIN_IDS[0]) haqiqatan
    YUBORILISHI kerak (Telegram Bot API'da boshqa yo'l yo'q) - lekin bu shunchaki
    ICHKI mexanizm, chatdagi haqiqiy xabar emas. Shu sabab, file_id olingandan
    so'ng bu "vaqtinchalik" xabar(lar) DARHOL o'chiriladi - aks holda o'sha admin
    keyinroq (notify_admins_new_web_listing/buy_limit orqali) YUBORILADIGAN,
    tugmali/sarlavhali "haqiqiy" nusxadan TASHQARI, ortiqcha "yalang'och"
    nusxasini ham ko'rib, rasm/chek IKKI MARTA kelayotgandek bo'lib qolardi."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN sozlanmagan")
    file_ids = []
    sent_message_ids = []
    async with httpx.AsyncClient(timeout=60) as client:
        if len(contents) == 1:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={"chat_id": str(chat_id)},
                files={"photo": (filenames[0], contents[0])},
            )
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("description", "Telegram xatoligi"))
            file_ids.append(data["result"]["photo"][-1]["file_id"])
            sent_message_ids.append(data["result"].get("message_id"))
        else:
            media, files = [], {}
            for i, (content, name) in enumerate(zip(contents, filenames)):
                key = f"photo{i}"
                media.append({"type": "photo", "media": f"attach://{key}"})
                files[key] = (name, content)
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup",
                data={"chat_id": str(chat_id), "media": _json.dumps(media)},
                files=files,
            )
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("description", "Telegram xatoligi"))
            for msg in data["result"]:
                photos = msg.get("photo") or []
                if photos:
                    file_ids.append(photos[-1]["file_id"])
                sent_message_ids.append(msg.get("message_id"))
        for mid in sent_message_ids:
            if not mid:
                continue
            try:
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage", json={"chat_id": chat_id, "message_id": mid})
            except Exception:
                logger.exception("Vaqtinchalik yuklash xabarini o'chirib bo'lmadi (chat_id=%s, message_id=%s)", chat_id, mid)
    return file_ids


def _web_listing_caption(d: dict) -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    rt = d.get("rental_type")
    rt_line = f"{RENTAL_TYPE_LABELS[rt][0]}\n" if rt and rt in RENTAL_TYPE_LABELS and rt != "uzoq_muddat" else ""
    return (
        f"\U0001F3E0 <b>Ijaraga Uylar Maklersiz</b>\n"
        f"{rt_line}\n"
        f"\U0001F4CD <b>Manzil:</b> {esc_html(d['manzil'])}\n"
        f"\U0001F3AF <b>Mo'ljal:</b> {esc_html(d['moljal'])}\n"
        f"\U0001F465 <b>Kimlarga:</b> {esc_html(d['kimlarga'])}\n"
        f"\U0001F6CF <b>Xonalar soni:</b> {esc_html(d['xona'])}\n\n"
        f"✅ <b>Qulayliklar:</b>\n{esc_html(d['qulaylik'])}\n\n"
        f"\U0001F4B0 <b>Narxi:</b> {esc_html(d['narx'])}\n\n"
        f"\U0001F4C5 {today}\n\n"
        f"@{CHANNEL_USERNAME} — uyingizni maklersiz bering va oling!"
    )


async def notify_admins_new_web_listing(listing_id: int, d: dict, file_ids: list, receipt_file_id, price_charged: int) -> None:
    if not ADMIN_IDS or not BOT_TOKEN:
        return
    caption = _web_listing_caption(d) + f"\n\n\U0001F194 E'lon raqami: #{listing_id}\n\U0001F310 Manba: <b>veb-sayt</b> orqali yuborilgan"

    ai_warning = ""
    scam = None
    try:
        loop = asyncio.get_event_loop()
        scam = await loop.run_in_executor(None, ai_screen_for_scam, caption)
        if scam and scam.get("suspicious"):
            ai_warning = f"\U0001F916⚠️ <b>AI: shubhali belgilar topildi</b> — {esc_html(scam.get('reason') or '')}\n\n"
            set_listing_scam_warning(listing_id, scam.get("reason") or "")
    except Exception:
        logger.exception("AI firibgarlik skriningida xatolik (veb e'lon)")

    # AI avtomatik tasdiqlash - bot/flow_listing.py'dagi bilan bir xil
    # shart: faqat bepul e'lon + admin alohida yoqqan bo'lsa + AI shubha
    # topmasa + telefon bloklanmagan + foydalanuvchining oldin rad
    # etilgan e'loni bo'lmasa. Aks holda odatdagidek admin navbatiga tushadi.
    if price_charged == 0 and ai_features_enabled() and get_setting("ai_auto_approve_free_listings", "0") == "1":
        listing_row = get_listing(listing_id)
        trusted = (
            listing_row is not None
            and scam is not None and not scam.get("suspicious")
            and not is_phone_blocked(d["telefon"])
            and not has_prior_rejected_listing(phone=d["telefon"])
        )
        if trusted:
            message_id = await post_listing_to_channel(listing_row)
            if message_id is not None:
                update_listing_status(listing_id, "approved", channel_msg_id=message_id)
                log_channel_post(listing_id, message_id)
                link = f"https://t.me/{CHANNEL_USERNAME}" if CHANNEL_USERNAME else None
                msg = "✅ Sizning e'loningiz tasdiqlandi va kanalga joylandi!"
                if link:
                    msg += f"\n{link}"
                await notify_telegram(listing_row["user_id"], msg)
                for admin_id in ADMIN_IDS:
                    try:
                        async with httpx.AsyncClient(timeout=10) as client:
                            await client.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                json={"chat_id": admin_id, "text": f"\U0001F916 AI avtomatik tasdiqladi (veb, bepul, xavf belgisi topilmadi): E'lon #{listing_id} kanalga joylandi."},
                            )
                    except Exception:
                        logger.exception("Adminga (%s) AI avto-tasdiq xabarini yuborib bo'lmadi (veb)", admin_id)
                return
            # Kanalga joylashda xato bo'lsa - pastdagi ODATDAGI (qo'lda
            # tasdiqlash) yo'lga o'tkaziladi, hech narsa yo'qolmaydi.

    sender_line = (
        f"{ai_warning}"
        f"\U0001F464 Yuboruvchi: {esc_html(d.get('full_name') or 'Nomsiz')} (veb-saytdan — Telegram akkaunti yo'q)\n"
        f"\U0001F4DE Bog'lanish uchun: {esc_html(d['telefon'])}\n"
        f"\U0001F4B0 To'lov qilingan summa: {price_charged:,} so'm\n"
        f"\U0001F194 E'lon: #{listing_id}\n\n"
        + ("\U0001F4B3 To'lov cheki yuqorida ↑ — tekshirib, qaror qabul qiling:"
           if receipt_file_id else "\U0001F193 Bu e'lon BEPUL tarifda yuborilgan (chek talab qilinmagan) — tekshirib, qaror qabul qiling:")
    )
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Tasdiqlash", "callback_data": f"admin_approve_listing_{listing_id}"},
        {"text": "❌ Rad etish", "callback_data": f"admin_reject_listing_{listing_id}"},
    ]]}
    async with httpx.AsyncClient(timeout=20) as client:
        for admin_id in ADMIN_IDS:
            try:
                if len(file_ids) == 1:
                    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                       json={"chat_id": admin_id, "photo": file_ids[0]})
                elif file_ids:
                    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup",
                                       json={"chat_id": admin_id, "media": [{"type": "photo", "media": fid} for fid in file_ids]})
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                   json={"chat_id": admin_id, "text": caption, "parse_mode": "HTML"})
                if receipt_file_id:
                    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                       json={"chat_id": admin_id, "photo": receipt_file_id, "caption": sender_line,
                                             "parse_mode": "HTML", "reply_markup": keyboard})
                else:
                    await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                       json={"chat_id": admin_id, "text": sender_line, "parse_mode": "HTML", "reply_markup": keyboard})
            except Exception:
                logger.exception("Web e'lon haqida adminga (%s) xabar yuborib bo'lmadi", admin_id)


@router.post("/api/elon-joylash")
async def submit_web_listing(
    request: Request,
    full_name: str = Form(""),
    telefon: str = Form(...),
    manzil: str = Form(...),
    moljal: str = Form(...),
    kimlarga: str = Form(...),
    xona: str = Form(...),
    qulaylik: str = Form(...),
    narx: str = Form(...),
    listing_type: str = Form("free"),
    rental_type: str = Form("uzoq_muddat"),
    latitude: str = Form(""),
    longitude: str = Form(""),
    photos: list[UploadFile] = File(...),
    receipt: UploadFile = File(None),
):
    ip = _client_ip(request)
    if web_submissions_today(ip) >= MAX_WEB_SUBMISSIONS_PER_IP_PER_DAY:
        raise HTTPException(status_code=429, detail="Kunlik e'lon yuborish limitiga yetdingiz. Ertaga qayta urinib ko'ring yoki Telegram bot orqali yuboring.")

    def clip(s, n):
        return (s or "").strip()[:n]

    manzil, moljal = clip(manzil, 250), clip(moljal, 250)
    kimlarga, xona = clip(kimlarga, 150), clip(xona, 60)
    qulaylik, narx = clip(qulaylik, 900), clip(narx, 200)
    full_name = clip(full_name, 100) or "Veb-sayt orqali"
    if rental_type not in RENTAL_TYPE_LABELS:
        rental_type = "uzoq_muddat"
    if not all([manzil, moljal, kimlarga, xona, qulaylik, narx]):
        raise HTTPException(status_code=400, detail="Iltimos, barcha majburiy maydonlarni to'ldiring.")

    phone = normalize_phone_web(telefon)
    if not phone:
        raise HTTPException(status_code=400, detail="Telefon raqami noto'g'ri formatda. Masalan: +998901234567")
    if is_phone_blocked(phone):
        raise HTTPException(status_code=400, detail="Bu raqam bilan e'lon joylashtirib bo'lmaydi. Savollar bo'lsa, adminga murojaat qiling.")

    valid_photos = [p for p in (photos or []) if p and p.filename]
    if not (1 <= len(valid_photos) <= MAX_WEB_LISTING_PHOTOS):
        raise HTTPException(status_code=400, detail=f"1 dan {MAX_WEB_LISTING_PHOTOS} tagacha uy rasmini yuklang.")

    photo_bytes, photo_names = [], []
    for p in valid_photos:
        content = await p.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Har bir rasm 10MB dan oshmasligi kerak.")
        photo_bytes.append(content)
        photo_names.append(p.filename or "rasm.jpg")

    is_paid = listing_type == "paid"
    receipt_bytes = None
    if is_paid:
        if not receipt or not receipt.filename:
            raise HTTPException(status_code=400, detail="Pullik e'lon uchun to'lov chekining skrinshotini yuklang.")
        receipt_bytes = await receipt.read()
        if len(receipt_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Chek rasmi 10MB dan oshmasligi kerak.")

    if not ADMIN_IDS or not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Tizim vaqtincha sozlanmoqda. Iltimos, birozdan so'ng qaytadan urinib ko'ring.")

    # Kanal/saytda faqat BIZNING logotipimiz bilan chiqishi uchun - to'lov
    # cheki EMAS, faqat uy rasmlariga watermark bosiladi.
    photo_bytes = watermark_photo_bytes_list(photo_bytes)

    upload_chat_id = ADMIN_IDS[0]
    try:
        file_ids = await telegram_upload_photos(upload_chat_id, photo_bytes, photo_names)
    except Exception:
        logger.exception("Web e'londan rasm yuklashda xatolik")
        raise HTTPException(status_code=502, detail="Rasmlarni yuklashda xatolik yuz berdi. Birozdan so'ng qaytadan urinib ko'ring.")
    if not file_ids:
        raise HTTPException(status_code=502, detail="Rasmlarni yuklab bo'lmadi. Qaytadan urinib ko'ring.")

    receipt_file_id = None
    if receipt_bytes:
        try:
            r_ids = await telegram_upload_photos(upload_chat_id, [receipt_bytes], ["chek.jpg"])
            receipt_file_id = r_ids[0] if r_ids else None
        except Exception:
            logger.exception("Web e'lon chekini yuklashda xatolik")

    price_charged = current_listing_price() if is_paid else 0

    lat = lon = None
    try:
        if latitude and longitude:
            lat, lon = float(latitude), float(longitude)
    except ValueError:
        lat = lon = None

    conn = db()
    cur = conn.execute(
        """INSERT INTO listings
            (user_id, username, full_name, sender_phone, manzil, moljal, kimlarga, xona,
             qulaylik, narx, telefon, photos, payment_receipt, price_charged, status, created_at,
             latitude, longitude, category, source, rental_type)
           VALUES (0, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, 'egadan', 'web', ?)""",
        (full_name, phone, manzil, moljal, kimlarga, xona, qulaylik, narx, phone,
         _json.dumps(file_ids), receipt_file_id, price_charged, now_str(), lat, lon, rental_type),
    )
    conn.commit()
    listing_id = cur.lastrowid
    conn.close()
    record_web_submission(ip)

    d = {"manzil": manzil, "moljal": moljal, "kimlarga": kimlarga, "xona": xona,
         "qulaylik": qulaylik, "narx": narx, "full_name": full_name, "telefon": phone, "rental_type": rental_type}
    try:
        await notify_admins_new_web_listing(listing_id, d, file_ids, receipt_file_id, price_charged)
    except Exception:
        logger.exception("Web e'lon uchun adminlarga umumiy xabar yuborishda xatolik")

    return {"ok": True, "listing_id": listing_id}


@router.post("/api/listing-inquiry")
async def submit_listing_inquiry(request: Request):
    data = await request.json()
    listing_id = data.get("listing_id")
    name = (data.get("name") or "").strip()[:100]
    phone = (data.get("phone") or "").strip()[:30]
    message = (data.get("message") or "").strip()[:500]
    if not listing_id or not name or not phone:
        raise HTTPException(status_code=400, detail="Majburiy maydonlar to'ldirilmagan")

    # Kirgan foydalanuvchi bo'lsa, so'rov uning kabinetidagi "Mening
    # so'rovlarim"da ko'rinishi uchun sender_user_id yozib qo'yiladi -
    # kirmagan (anonim) foydalanuvchi ham so'rov yuborishda davom etadi.
    tg_user = get_current_tg_user(request)
    sender_user_id = tg_user["uid"] if tg_user else None

    conn = db()
    row = conn.execute("SELECT user_id, manzil, raw_text, channel_msg_id FROM listings WHERE id = ?", (listing_id,)).fetchone()
    owner_id = row["user_id"] if row else None
    addr = (row["manzil"] if row and row["manzil"] else extract_district(row["raw_text"] if row else "")) if row else "e'lon"
    conn.execute(
        "INSERT INTO listing_inquiries (listing_id, owner_user_id, name, phone, message, status, created_at, sender_user_id) VALUES (?,?,?,?,?,'yangi',?,?)",
        (listing_id, owner_id, name, phone, message, now_str(), sender_user_id),
    )
    conn.commit()
    conn.close()

    notify_text = (
        f"\U0001F4E9 <b>Saytdan yangi so'rov!</b>\n\n"
        f"\U0001F3E0 E'lon: {esc_html(addr)} (#{listing_id})\n"
        f"\U0001F464 Ism: {esc_html(name)}\n"
        f"\U0001F4DE Telefon: {esc_html(phone)}\n"
        + (f"\U0001F4AC Xabar: {esc_html(message)}\n" if message else "")
    )
    channel_msg_id = row["channel_msg_id"] if row else None
    reply_markup = None
    if channel_msg_id and CHANNEL_USERNAME:
        reply_markup = {"inline_keyboard": [[
            {"text": "\U0001F4E2 Kanaldagi e'lonni ko'rish", "url": f"https://t.me/{CHANNEL_USERNAME}/{channel_msg_id}"}
        ]]}

    # MUHIM: e'lon egasi ba'zan o'zi ham admin/moderator bo'lishi mumkin (ADMIN_IDS
    # ichida) - shu holatda "egasiga" va "har bir adminga" alohida yuborilsa, u
    # bir xil xabarni IKKI MARTA olardi. Shuning uchun qabul qiluvchilar ro'yxatini
    # (owner + barcha adminlar) avval bitta TO'PLAMga (set) yig'amiz - bu takroriy
    # ID'larni avtomatik olib tashlaydi - va har biriga FAQAT BIR MARTA yuboramiz.
    recipients = set()
    if owner_id:
        recipients.add(owner_id)
    for admin_id_str in (os.getenv("ADMIN_IDS", "") or "").split(","):
        admin_id_str = admin_id_str.strip()
        if admin_id_str.isdigit():
            recipients.add(int(admin_id_str))
    for uid in recipients:
        await notify_telegram(uid, notify_text, reply_markup=reply_markup)

    return {"ok": True}


# ============================= TELEGRAM ORQALI KIRISH / SHAXSIY KABINET =============================


