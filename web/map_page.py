"""
Ommaviy interaktiv xarita (/xarita) va joylashuv tanlash WebApp sahifasi
(/tanla-joy) - ikkalasi ham statik shablon, parolsiz.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.render import get_lang

router = APIRouter()

@router.get("/xarita", response_class=HTMLResponse)
def public_map_page(request: Request):
    lang = get_lang(request)
    return PUBLIC_MAP_HTML.replace("__LANG__", lang)


@router.get("/tanla-joy", response_class=HTMLResponse)
def pick_location_page():
    return PICK_LOCATION_HTML






# ============================= OMMAVIY XARITA HTML (parolsiz) =============================

PUBLIC_MAP_HTML = """<!DOCTYPE html>
<html lang="__LANG__">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>Ijaraga Uylar \u2014 Interaktiv xarita</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<style>
  :root { --map-bg: #0b1220; --map-panel: #131c2e; --map-line: #223049; --map-ink: #e9edf5; --map-muted: #8b98ac; --map-accent: #ff5470; }
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  html, body { width: 100%; height: 100%; overflow: hidden; }
  body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: var(--map-bg); }

  #topbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
    background: rgba(19,28,46,0.92); backdrop-filter: blur(10px);
    padding: 10px 14px; display: flex; align-items: center; justify-content: space-between; gap: 10px;
    border-bottom: 1px solid var(--map-line); color: var(--map-ink);
    padding-top: calc(10px + env(safe-area-inset-top));
  }
  #topbar h1 { font-size: 14.5px; font-weight: 700; }
  #topbar .count { font-size: 11.5px; color: var(--map-muted); font-weight: 600; }
  #topbar-left { display: flex; align-items: center; gap: 9px; min-width: 0; }
  #topbar-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  #topbar-logo { width: 28px; height: 28px; border-radius: 8px; flex-shrink: 0; object-fit: cover; }
  #filter-btn {
    display: flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.08); border: 1px solid var(--map-line);
    color: var(--map-ink); padding: 7px 12px; border-radius: 10px; font-size: 12.5px; font-weight: 700; cursor: pointer; flex-shrink: 0;
  }
  #filter-btn .fcount { background: var(--map-accent); color: #fff; border-radius: 20px; padding: 0 6px; font-size: 10.5px; min-width: 16px; text-align: center; }
  #close-btn {
    display: flex; align-items: center; justify-content: center; width: 32px; height: 32px;
    border-radius: 9px; background: rgba(255,255,255,0.08); color: var(--map-ink); flex-shrink: 0; border: none; cursor: pointer;
  }
  #close-btn svg { width: 16px; height: 16px; }

  #map { position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; }

  #filter-panel {
    position: fixed; top: 0; right: -320px; bottom: 0; width: 300px; z-index: 1500;
    background: var(--map-panel); border-left: 1px solid var(--map-line); color: var(--map-ink);
    padding: 18px 16px; padding-top: calc(18px + env(safe-area-inset-top)); overflow-y: auto;
    transition: right .25s ease; box-shadow: -8px 0 30px rgba(0,0,0,.4);
  }
  #filter-panel.open { right: 0; }
  #filter-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1400; display: none; }
  #filter-overlay.open { display: block; }
  .fp-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
  .fp-head h2 { font-size: 16px; font-weight: 800; }
  .fp-close { background: rgba(255,255,255,0.08); border: none; color: var(--map-ink); width: 30px; height: 30px; border-radius: 8px; cursor: pointer; }
  .fp-section { margin-bottom: 20px; }
  .fp-label { font-size: 11.5px; font-weight: 700; color: var(--map-muted); text-transform: uppercase; letter-spacing: .3px; margin-bottom: 10px; }
  .fp-select { width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--map-line); background: #0f1826; color: var(--map-ink); font-size: 13.5px; }
  .fp-chip-row { display: flex; flex-wrap: wrap; gap: 8px; }
  .fp-chip { display: flex; align-items: center; gap: 6px; padding: 7px 12px; border-radius: 20px; border: 1px solid var(--map-line); font-size: 12.5px; font-weight: 600; cursor: pointer; background: #0f1826; }
  .fp-chip .dot { width: 9px; height: 9px; border-radius: 50%; }
  .fp-chip.active { border-color: var(--map-accent); background: rgba(255,84,112,0.14); }
  .fp-toggle-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; }
  .fp-apply { width: 100%; background: var(--map-accent); color: #fff; border: none; padding: 13px; border-radius: 12px; font-weight: 800; font-size: 14px; cursor: pointer; margin-top: 6px; }
  .switch { position: relative; display: inline-block; width: 40px; height: 22px; flex-shrink: 0; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .switch .slider { position: absolute; inset: 0; background: #2a3a56; border-radius: 24px; transition: .2s; cursor: pointer; }
  .switch .slider::before { content: ""; position: absolute; width: 16px; height: 16px; left: 3px; top: 3px; background: #fff; border-radius: 50%; transition: .2s; }
  .switch input:checked + .slider { background: var(--map-accent); }
  .switch input:checked + .slider::before { transform: translateX(18px); }

  /* O'ng pastdagi tugmalar - vertikal ustun, bir-biriga aniq mos oraliqlar bilan.
     Leaflet'ning o'z +/- zoom tugmasi chapga (bottomleft) o'tkazilgan - shu bilan
     ular hech qachon bir-birining ustiga tushmaydi. */
  #map-actions {
    position: fixed; right: 12px; bottom: calc(24px + env(safe-area-inset-bottom)); z-index: 900;
    display: flex; flex-direction: column; gap: 10px;
  }
  #locate-btn, #legend-btn {
    width: 42px; height: 42px; border-radius: 50%; border: 1px solid var(--map-line);
    background: var(--map-panel); color: var(--map-ink); box-shadow: 0 2px 10px rgba(0,0,0,0.5); cursor: pointer;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  }
  #legend-btn { font-size: 16px; }
  .leaflet-bottom.leaflet-left { margin-bottom: env(safe-area-inset-bottom); }

  #legend-box {
    position: fixed; left: 12px; bottom: 24px; z-index: 900; background: var(--map-panel); border: 1px solid var(--map-line);
    border-radius: 12px; padding: 10px 12px; color: var(--map-ink); font-size: 11.5px; display: none; box-shadow: 0 4px 14px rgba(0,0,0,.4);
  }
  #legend-box.show { display: block; }
  .legend-row { display: flex; align-items: center; gap: 7px; margin: 4px 0; }
  .legend-row .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

  .cluster-icon { background: var(--map-accent); color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 13px; border: 3px solid rgba(255,255,255,0.85); box-shadow: 0 2px 8px rgba(0,0,0,0.4); }

  .leaflet-popup-content-wrapper { border-radius: 14px; overflow: hidden; padding: 0; }
  .leaflet-popup-content { margin: 0; width: 240px !important; }
  .leaflet-popup-tip { background: #fff; }
  .pcard-photo { width: 100%; height: 120px; object-fit: cover; background: #eee; display: block; }
  .pcard-photo-empty { width: 100%; height: 120px; background: linear-gradient(135deg,#f3f4f6,#e5e7eb); display: flex; align-items: center; justify-content: center; font-size: 30px; }
  .pcard-body { padding: 12px 13px 13px; }
  .pcard-badges { display: flex; gap: 5px; margin-bottom: 6px; flex-wrap: wrap; }
  .pcard-badge { font-size: 10px; font-weight: 800; padding: 2px 8px; border-radius: 20px; text-transform: uppercase; }
  .pcard-title { font-size: 13.5px; font-weight: 800; color: #16202e; line-height: 1.3; margin-bottom: 3px; }
  .pcard-meta { font-size: 11.5px; color: #6b7688; margin-bottom: 8px; }
  .pcard-price { font-size: 15px; font-weight: 800; color: #16202e; margin-bottom: 9px; }
  .pcard-actions { display: flex; gap: 6px; }
  .pcard-actions a { flex: 1; text-align: center; padding: 8px 6px; border-radius: 9px; font-size: 11.5px; font-weight: 700; text-decoration: none; }
  .pcard-btn-primary { background: var(--map-accent); color: #fff !important; }
  .pcard-btn-secondary { background: #f1f3f6; color: #16202e !important; }

  #loading { position: fixed; inset: 0; background: var(--map-bg); color: var(--map-muted); display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 14px; z-index: 2000; gap: 10px; }
  .spinner { width: 30px; height: 30px; border: 3px solid #2a3a56; border-top-color: var(--map-accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div id="loading"><div class="spinner"></div><div data-i18n="loading">Xarita yuklanmoqda...</div></div>

<div id="topbar">
  <div id="topbar-left">
    <img id="topbar-logo" src="/logo.png" alt="logo" onerror="this.style.display='none'">
    <div>
      <h1>Ijaraga Uylar</h1>
      <div class="count" id="count-badge"></div>
    </div>
  </div>
  <div id="topbar-right">
    <button id="filter-btn" onclick="toggleFilters(true)">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M7 12h10M10 18h4"/></svg>
      <span data-i18n="filter_btn">Filtr</span> <span class="fcount" id="filterCount">0</span>
    </button>
    <button id="close-btn" onclick="closeMap()" data-i18n-title="close_title" title="Yopish" aria-label="Yopish">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>
    </button>
  </div>
</div>

<div id="map"></div>

<div id="map-actions">
  <button id="locate-btn" data-i18n-title="locate_title" title="Mening joylashuvim" onclick="locateMe()">
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>
  </button>
  <button id="legend-btn" data-i18n-title="legend_title" title="Belgilar" onclick="toggleLegend()">\U0001F3F7\ufe0f</button>
</div>
<div id="legend-box">
  <div class="legend-row"><span class="dot" style="background:#ff5470;"></span> <span data-i18n="cat_egadan">Egasidan (oddiy)</span></div>
  <div class="legend-row"><span class="dot" style="background:#16a34a;"></span> <span data-i18n="cat_tasdiqlangan_plain">Tasdiqlangan</span></div>
  <div class="legend-row"><span class="dot" style="background:#2563eb;"></span> <span data-i18n="cat_subarenda_plain">Subarenda</span></div>
  <div class="legend-row"><span class="dot" style="background:#d97706;"></span> <span data-i18n="cat_premium_plain">Premium</span></div>
  <div class="legend-row" style="margin-top:6px;border-top:1px solid var(--map-line);padding-top:6px;">\u26a1 <span data-i18n="legend_top">TOP \u2014 pullik e'lon</span></div>
</div>

<div id="filter-overlay" onclick="toggleFilters(false)"></div>
<div id="filter-panel">
  <div class="fp-head"><h2>\U0001F50D <span data-i18n="filter_btn">Filtr</span></h2><button class="fp-close" onclick="toggleFilters(false)">\u2715</button></div>

  <div class="fp-section">
    <div class="fp-label" data-i18n="rooms_label">Xonalar soni</div>
    <select class="fp-select" id="fXona">
      <option value="" data-i18n="rooms_any">Farqi yo'q</option>
      <option value="1">1</option>
      <option value="2">2</option>
      <option value="3">3</option>
      <option value="4">4+</option>
    </select>
  </div>

  <div class="fp-section">
    <div class="fp-label" data-i18n="category_label">Toifa</div>
    <div class="fp-chip-row" id="categoryChips">
      <div class="fp-chip active" data-cat=""><span class="dot" style="background:#94a3b8;"></span> <span data-i18n="cat_all">Barchasi</span></div>
      <div class="fp-chip" data-cat="egadan"><span class="dot" style="background:#ff5470;"></span> <span data-i18n="cat_egadan_plain">Egasidan</span></div>
      <div class="fp-chip" data-cat="tasdiqlangan"><span class="dot" style="background:#16a34a;"></span> <span data-i18n="cat_tasdiqlangan_plain">Tasdiqlangan</span></div>
      <div class="fp-chip" data-cat="subarenda"><span class="dot" style="background:#2563eb;"></span> <span data-i18n="cat_subarenda_plain">Subarenda</span></div>
      <div class="fp-chip" data-cat="premium"><span class="dot" style="background:#d97706;"></span> <span data-i18n="cat_premium_plain">Premium</span></div>
    </div>
  </div>

  <div class="fp-section">
    <div class="fp-toggle-row">
      <div style="font-size:13.5px;font-weight:700;">\u26a1 <span data-i18n="top_only">Faqat TOP e'lonlar</span></div>
      <label class="switch"><input type="checkbox" id="fTopOnly"><span class="slider"></span></label>
    </div>
  </div>

  <button class="fp-apply" onclick="applyFilters()" data-i18n="apply_btn">Qo'llash</button>
</div>

<script>
const MAP_LANG = "__LANG__";
const MI18N = {
  uz: { page_title: "Ijaraga Uylar — Interaktiv xarita", loading: "Xarita yuklanmoqda...", filter_btn: "Filtr", locate_title: "Mening joylashuvim", legend_title: "Belgilar", close_title: "Yopish",
        cat_egadan: "Egasidan (oddiy)", cat_egadan_plain: "Egasidan", cat_tasdiqlangan_plain: "Tasdiqlangan", cat_subarenda_plain: "Subarenda", cat_premium_plain: "Premium",
        legend_top: "TOP \u2014 pullik e'lon", rooms_label: "Xonalar soni", rooms_any: "Farqi yo'q", category_label: "Toifa",
        cat_all: "Barchasi", top_only: "Faqat TOP e'lonlar", apply_btn: "Qo'llash", count_suffix: "ta e'lon",
        detail_btn: "Batafsil", channel_btn: "Kanalda", no_address: "Manzil ko'rsatilmagan", map_error: "\u26a0\ufe0f Xarita yuklanmadi. Internet aloqangizni tekshirib, sahifani qayta yuklang.",
        locate_error: "Joylashuvni aniqlab bo'lmadi. Brauzer sozlamalarida ruxsat berilganini tekshiring." },
  ru: { page_title: "Ijaraga Uylar \u2014 \u0418\u043d\u0442\u0435\u0440\u0430\u043a\u0442\u0438\u0432\u043d\u0430\u044f \u043a\u0430\u0440\u0442\u0430", loading: "\u041a\u0430\u0440\u0442\u0430 \u0437\u0430\u0433\u0440\u0443\u0436\u0430\u0435\u0442\u0441\u044f...", filter_btn: "\u0424\u0438\u043b\u044c\u0442\u0440", locate_title: "\u041c\u043e\u0451 \u043c\u0435\u0441\u0442\u043e\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435", legend_title: "\u041e\u0431\u043e\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f", close_title: "\u0417\u0430\u043a\u0440\u044b\u0442\u044c",
        cat_egadan: "\u041e\u0442 \u0445\u043e\u0437\u044f\u0438\u043d\u0430 (\u043e\u0431\u044b\u0447\u043d.)", cat_egadan_plain: "\u041e\u0442 \u0445\u043e\u0437\u044f\u0438\u043d\u0430", cat_tasdiqlangan_plain: "\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e", cat_subarenda_plain: "\u0421\u0443\u0431\u0430\u0440\u0435\u043d\u0434\u0430", cat_premium_plain: "\u041f\u0440\u0435\u043c\u0438\u0443\u043c",
        legend_top: "\u0422\u041e\u041f \u2014 \u043f\u043b\u0430\u0442\u043d\u043e\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435", rooms_label: "\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u043a\u043e\u043c\u043d\u0430\u0442", rooms_any: "\u041d\u0435\u0432\u0430\u0436\u043d\u043e", category_label: "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f",
        cat_all: "\u0412\u0441\u0435", top_only: "\u0422\u043e\u043b\u044c\u043a\u043e \u0422\u041e\u041f \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f", apply_btn: "\u041f\u0440\u0438\u043c\u0435\u043d\u0438\u0442\u044c", count_suffix: "\u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0439",
        detail_btn: "\u041f\u043e\u0434\u0440\u043e\u0431\u043d\u0435\u0435", channel_btn: "\u0412 \u043a\u0430\u043d\u0430\u043b\u0435", no_address: "\u0410\u0434\u0440\u0435\u0441 \u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d", map_error: "\u26a0\ufe0f \u041a\u0430\u0440\u0442\u0430 \u043d\u0435 \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u043b\u0430\u0441\u044c. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442-\u0441\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u0435 \u0438 \u043e\u0431\u043d\u043e\u0432\u0438\u0442\u0435 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0443.",
        locate_error: "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u0442\u044c \u043c\u0435\u0441\u0442\u043e\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0440\u0430\u0437\u0440\u0435\u0448\u0435\u043d\u0438\u044f \u0432 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430\u0445 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0430." },
  en: { page_title: "Ijaraga Uylar — Interactive Map", loading: "Loading map...", filter_btn: "Filter", locate_title: "My location", legend_title: "Legend", close_title: "Close",
        cat_egadan: "From owner (regular)", cat_egadan_plain: "From owner", cat_tasdiqlangan_plain: "Verified", cat_subarenda_plain: "Sublease", cat_premium_plain: "Premium",
        legend_top: "TOP \u2014 paid listing", rooms_label: "Rooms", rooms_any: "Any", category_label: "Category",
        cat_all: "All", top_only: "TOP listings only", apply_btn: "Apply", count_suffix: "listings",
        detail_btn: "Details", channel_btn: "On channel", no_address: "Address not provided", map_error: "\u26a0\ufe0f Map failed to load. Check your internet connection and reload the page.",
        locate_error: "Couldn't determine your location. Check your browser's location permission." },
};
const ML = MI18N[MAP_LANG] || MI18N.uz;
if (ML.page_title) document.title = ML.page_title;
document.querySelectorAll('[data-i18n]').forEach(el => { if (ML[el.dataset.i18n]) el.textContent = ML[el.dataset.i18n]; });
document.querySelectorAll('[data-i18n-title]').forEach(el => { if (ML[el.dataset.i18nTitle]) el.title = ML[el.dataset.i18nTitle]; });

if (window.Telegram && window.Telegram.WebApp) {
  Telegram.WebApp.ready();
  Telegram.WebApp.expand();
}

function trackClick(listingId) {
  fetch('/api/track-click/' + listingId, { method: 'POST' }).catch(() => {});
}

const CATEGORY_COLORS = { egadan: '#ff5470', tasdiqlangan: '#16a34a', subarenda: '#2563eb', premium: '#d97706' };
const CATEGORY_LABELS = { egadan: ML.cat_egadan_plain || 'Egasidan', tasdiqlangan: '\u2705 ' + ML.cat_tasdiqlangan_plain, subarenda: '\U0001F3E2 ' + ML.cat_subarenda_plain, premium: '\U0001F48E ' + ML.cat_premium_plain };

let map, cluster, allListings = [], userMarker = null;

function toggleFilters(open) {
  document.getElementById('filter-panel').classList.toggle('open', open);
  document.getElementById('filter-overlay').classList.toggle('open', open);
}
function toggleLegend() {
  document.getElementById('legend-box').classList.toggle('show');
}
function closeMap() {
  // Agar xarita boshqa sahifadan (masalan bosh sahifadan) ochilgan bo'lsa - "orqaga"
  // qaytish tabiiyroq (foydalanuvchi qayerdan kelgan bo'lsa, o'sha yerga qaytadi).
  // Aks holda (masalan to'g'ridan-to'g'ri /xarita havolasi bosilgan bo'lsa) - bosh sahifaga.
  if (document.referrer && document.referrer.indexOf(window.location.host) !== -1 && window.history.length > 1) {
    window.history.back();
  } else {
    window.location.href = '/';
  }
}
document.querySelectorAll('.fp-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.fp-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
  });
});

function makeMarker(l) {
  const cat = l.category || 'egadan';
  const color = CATEGORY_COLORS[cat] || '#ff5470';
  const size = l.is_paid ? 15 : 11;
  const marker = L.circleMarker([l.latitude, l.longitude], {
    radius: size, fillColor: color, color: '#fff', weight: l.is_paid ? 3 : 2, fillOpacity: 0.95,
  });
  if (l.narx) {
    const cls = 'price-label' + (l.is_paid ? ' price-label-top' : '');
    marker.bindTooltip((l.is_paid ? '\u26a1 ' : '') + l.narx, { permanent: false, direction: 'top', className: cls, offset: [0, -size] });
  }
  const photoHtml = l.photo
    ? `<img class="pcard-photo" src="${l.photo}" loading="lazy">`
    : `<div class="pcard-photo-empty">\U0001F3E0</div>`;
  const badges = `<div class="pcard-badges">${l.is_paid ? '<span class="pcard-badge" style="background:#fff2e0;color:#c2650b;">\u26a1 TOP</span>' : ''}${CATEGORY_LABELS[cat] ? `<span class="pcard-badge" style="background:#eef2f7;color:#334155;">${CATEGORY_LABELS[cat]}</span>` : ''}</div>`;
  const detailBtn = `<a href="${l.detail_link}" target="_blank" class="pcard-btn-primary">${ML.detail_btn}</a>`;
  const chanBtn = l.post_link ? `<a href="${l.post_link}" target="_blank" class="pcard-btn-secondary" onclick="trackClick(${l.id})">${ML.channel_btn}</a>` : '';
  marker.bindPopup(
    `${photoHtml}<div class="pcard-body">${badges}` +
    `<div class="pcard-title">${l.manzil || l.moljal || ML.no_address}</div>` +
    `<div class="pcard-meta">\U0001F6CF ${l.xona || '-'} \u00b7 \U0001F465 ${(l.kimlarga||'').slice(0,20) || '-'}</div>` +
    `<div class="pcard-price">${l.narx || ''}</div>` +
    `<div class="pcard-actions">${detailBtn}${chanBtn}</div></div>`
  );
  return marker;
}

function renderMarkers(listings) {
  cluster.clearLayers();
  listings.forEach(l => cluster.addLayer(makeMarker(l)));
  document.getElementById('count-badge').textContent = listings.length + " " + ML.count_suffix;
}

function applyFilters() {
  const xona = document.getElementById('fXona').value;
  const topOnly = document.getElementById('fTopOnly').checked;
  const cat = document.querySelector('.fp-chip.active').dataset.cat;

  let filtered = allListings;
  if (xona) filtered = filtered.filter(l => (l.xona || '').includes(xona));
  if (topOnly) filtered = filtered.filter(l => l.is_paid);
  if (cat) filtered = filtered.filter(l => (l.category || 'egadan') === cat);

  let activeCount = 0;
  if (xona) activeCount++;
  if (topOnly) activeCount++;
  if (cat) activeCount++;
  document.getElementById('filterCount').textContent = activeCount;
  document.getElementById('filterCount').style.display = activeCount ? 'inline-block' : 'none';

  renderMarkers(filtered);
  toggleFilters(false);
}

function locateMe() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition((pos) => {
    const { latitude, longitude } = pos.coords;
    if (userMarker) map.removeLayer(userMarker);
    userMarker = L.circleMarker([latitude, longitude], { radius: 8, fillColor: '#4285F4', color: '#fff', weight: 3, fillOpacity: 1 }).addTo(map);
    map.setView([latitude, longitude], 14);
  }, () => alert(ML.locate_error));
}

async function init() {
  try {
    fetch('/api/track-view', { method: 'POST' }).catch(() => {});

    map = L.map('map', { tap: true, zoomControl: false }).setView([41.311081, 69.240562], 11);
    L.control.zoom({ position: 'bottomleft' }).addTo(map);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap', maxZoom: 19 }).addTo(map);

    cluster = L.markerClusterGroup({
      maxClusterRadius: 50,
      iconCreateFunction: function(c) {
        const count = c.getChildCount();
        const size = count < 10 ? 34 : (count < 50 ? 42 : 50);
        return L.divIcon({ html: `<div class="cluster-icon" style="width:${size}px;height:${size}px;">${count}</div>`, className: '', iconSize: [size, size] });
      },
    });
    map.addLayer(cluster);

    const res = await fetch('/api/public-listings');
    allListings = await res.json();
    renderMarkers(allListings);

    document.getElementById('loading').style.display = 'none';
  } catch (err) {
    document.getElementById('loading').innerHTML = ML.map_error;
  }
}

init();
</script>
</body>
</html>
"""


# ============================= JOYLASHUV TANLASH (WebApp, elon berish jarayoni uchun) =============================

PICK_LOCATION_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>Joylashuvni tanlang</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  html, body { width: 100%; height: 100%; overflow: hidden; }
  body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #0f1419; }
  #topbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
    background: rgba(26,35,50,0.97); backdrop-filter: blur(6px);
    padding: 12px 16px; color: #e8eaed; text-align: center;
    border-bottom: 1px solid #2a3441;
    padding-top: calc(12px + env(safe-area-inset-top));
  }
  #topbar h1 { font-size: 14px; font-weight: 600; margin-bottom: 2px; }
  #topbar p { font-size: 12px; color: #8b98a5; }
  #map { position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; }
  #center-pin {
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -100%);
    font-size: 42px; z-index: 999; pointer-events: none;
    filter: drop-shadow(0 4px 6px rgba(0,0,0,0.4));
  }
  #locate-btn {
    position: fixed; right: 12px; bottom: 100px; z-index: 1000;
    width: 46px; height: 46px; border-radius: 50%; border: none;
    background: #1a2332; color: #4285F4; font-size: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5); cursor: pointer;
    display: flex; align-items: center; justify-content: center;
  }
  #locate-btn:active { background: #263148; }
  #confirm-bar {
    position: fixed; bottom: 0; left: 0; right: 0; z-index: 1000;
    padding: 16px; padding-bottom: calc(16px + env(safe-area-inset-bottom));
    background: linear-gradient(to top, rgba(15,20,25,0.98), rgba(15,20,25,0.7));
  }
  #confirm-btn {
    width: 100%; padding: 16px; border: none; border-radius: 14px;
    background: #2ea043; color: #fff; font-size: 16px; font-weight: 700;
    cursor: pointer;
  }
  #confirm-btn:active { background: #268a39; }
  .user-dot { width: 18px; height: 18px; border-radius: 50%; background: #4285F4; border: 3px solid #fff; box-shadow: 0 0 0 4px rgba(66,133,244,0.3); }
</style>
</head>
<body>
<div id="topbar">
  <h1>\U0001F4CD Uyning joylashuvini belgilang</h1>
  <p>Xaritani suring, markazdagi belgi \u2014 tanlangan nuqta</p>
</div>
<div id="map"></div>
<div id="center-pin">\U0001F4CD</div>
<button id="locate-btn" title="Mening joylashuvim">\U0001F3AF</button>
<div id="confirm-bar">
  <button id="confirm-btn">\u2705 Shu nuqtani tanlash</button>
</div>

<script>
const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); }

const map = L.map('map', { zoomControl: false, tap: true }).setView([41.311081, 69.240562], 13);
L.control.zoom({ position: 'bottomright' }).addTo(map);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap', maxZoom: 19 }).addTo(map);

// "Google/Yandex Maps"dagidek - foydalanuvchining O'ZI TURGAN joyi doim
// xaritada ko'k nuqta bilan ko'rinib turadi (bu - tanlangan nuqtadan FARQLI,
// faqat orientir uchun).
let userMarker = null;
const userIcon = L.divIcon({ className: '', html: '<div class="user-dot"></div>', iconSize: [18, 18] });

function showUserLocation(lat, lon, recenter) {
  if (userMarker) { userMarker.setLatLng([lat, lon]); }
  else { userMarker = L.marker([lat, lon], { icon: userIcon, zIndexOffset: 500 }).addTo(map); }
  if (recenter) map.setView([lat, lon], 15);
}

function locateMe() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => showUserLocation(pos.coords.latitude, pos.coords.longitude, true),
    () => {}
  );
}

// Sahifa ochilganda avtomatik bir marta joylashuvni aniqlaymiz
locateMe();
// "Mening joylashuvim" tugmasi - istalgan vaqt bosib, o'z joyiga qaytish mumkin
document.getElementById('locate-btn').addEventListener('click', locateMe);

document.getElementById('confirm-btn').addEventListener('click', () => {
  const center = map.getCenter();
  const data = JSON.stringify({ lat: center.lat, lon: center.lng });
  if (tg) {
    tg.sendData(data);
  } else {
    alert('lat: ' + center.lat + ', lon: ' + center.lng);
  }
});
</script>
</body>
</html>
"""

