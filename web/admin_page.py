"""
Admin panel (/admin) - parol bilan himoyalangan, ichki boshqaruv sahifasi.
Butun HTML/CSS/JS bitta statik shablon (server tomonidan hisoblanadigan
o'zgaruvchi yo'q - ma'lumotlar JS orqali /api/* dan olinadi).
"""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from web.auth import check_auth

router = APIRouter()

# ============================= SAHIFALAR =============================

@router.get("/admin", response_class=HTMLResponse)
def dashboard_page(user: str = Depends(check_auth)):
    return ADMIN_HTML




# ============================= ADMIN PANEL HTML (PRO) =============================

ADMIN_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Admin Panel - Ijaraga Uylar</title>
<link rel="icon" href="/logo.png">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --brand: #FF3B5C; --brand-dark: #E01E45; --brand-light: #FFEBEF;
    --ink: #101826; --ink-soft: #47526B; --muted: #6B7690; --line: #E7EAF0;
    --bg: #F6F8FA; --card: #ffffff;
    --sidebar-w: 232px;
    --shadow: 0 1px 3px rgba(16,24,38,0.06), 0 1px 2px rgba(16,24,38,0.04);
    --shadow-md: 0 4px 16px rgba(16,24,38,0.08);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  html, body { width: 100%; overflow-x: hidden; }
  body { font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--ink); font-size: 14px; }

  /* ===== SIDEBAR ===== */
  #sidebar {
    position: fixed; top: 0; left: 0; bottom: 0; width: var(--sidebar-w); background: #fff;
    border-right: 1px solid var(--line); padding: 20px 14px; z-index: 100; overflow-y: auto;
  }
  .side-brand { display: flex; align-items: center; gap: 10px; padding: 6px 10px 22px; font-weight: 800; font-size: 16px; }
  .side-brand img { width: 32px; height: 32px; border-radius: 9px; }
  .side-nav a {
    display: flex; align-items: center; gap: 11px; padding: 11px 12px; border-radius: 10px;
    color: var(--ink-soft); font-weight: 600; font-size: 13.5px; margin-bottom: 3px; cursor: pointer;
    transition: background .15s;
  }
  .side-nav a:hover { background: var(--bg); }
  .side-nav a.active { background: var(--brand-light); color: var(--brand-dark); }
  .side-nav .icon { font-size: 17px; width: 20px; text-align: center; }
  .side-live {
    margin-top: 20px; padding: 10px 12px; background: var(--bg); border-radius: 10px;
    display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; color: #1A7A3C;
  }
  .pulse-dot { width: 7px; height: 7px; border-radius: 50%; background: #22C55E; animation: pulse 1.6s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }

  #content { margin-left: var(--sidebar-w); padding: 26px 30px 50px; max-width: 1400px; }

  @media (max-width: 900px) {
    #sidebar {
      top: auto; bottom: 0; left: 0; right: 0; width: 100%; height: auto; border-right: none;
      border-top: 1px solid var(--line); padding: 8px; display: flex; justify-content: space-around;
    }
    .side-brand, .side-live { display: none; }
    .side-nav { display: flex; width: 100%; justify-content: space-around; }
    .side-nav a { flex-direction: column; gap: 3px; font-size: 10.5px; padding: 8px 6px; flex: 1; text-align: center; }
    #content { margin-left: 0; padding: 18px 14px 90px; }
  }

  .page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 22px; flex-wrap: wrap; gap: 10px; }
  .page-head h1 { font-size: 21px; font-weight: 800; letter-spacing: -0.4px; }

  .tab-page { display: none; }
  .tab-page.active { display: block; }

  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 26px; }
  .kpi-card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; box-shadow: var(--shadow); }
  .kpi-card .icon-badge { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 17px; margin-bottom: 10px; }
  .kpi-card .label { font-size: 12px; color: var(--muted); font-weight: 600; margin-bottom: 4px; }
  .kpi-card .value { font-size: 25px; font-weight: 800; letter-spacing: -0.5px; }
  .kpi-card .trend { display: inline-flex; align-items: center; gap: 3px; font-size: 11.5px; font-weight: 700; margin-top: 7px; padding: 2px 8px; border-radius: 7px; }
  .trend.up { color: #1A7A3C; background: #E7F6EC; }
  .trend.down { color: #C0362C; background: #FDEDEB; }
  .trend.flat { color: var(--muted); background: var(--bg); }
  .icon-pink { background: var(--brand-light); color: var(--brand); }
  .icon-blue { background: #E8F1FE; color: #2563EB; }
  .icon-green { background: #E7F6EC; color: #16A34A; }
  .icon-purple { background: #F3E8FE; color: #9333EA; }
  .icon-orange { background: #FEF3E2; color: #D97706; }

  .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 26px; }
  @media (max-width: 980px) { .charts-grid { grid-template-columns: 1fr; } }
  .panel { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; box-shadow: var(--shadow); }
  .panel h2 { font-size: 14.5px; font-weight: 700; margin-bottom: 3px; }
  .panel .panel-sub { font-size: 12px; color: var(--muted); margin-bottom: 14px; }
  .chart-box { height: 250px; position: relative; }

  #map { height: 460px; border-radius: 12px; width: 100%; }
  .price-label { background: var(--brand); color: #fff; font-weight: 700; font-size: 12px; padding: 2px 8px; border-radius: 10px; border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,.3); white-space: nowrap; }
  .price-label::before { border-top-color: var(--brand) !important; }
  .post-link-btn { display: inline-block; margin-top: 8px; background: var(--brand); color: #fff !important; text-decoration: none; padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; }

  .top-list { display: flex; flex-direction: column; gap: 8px; }
  .top-item { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; background: var(--bg); border-radius: 10px; }
  .top-item .ti-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .top-item .ti-rank { width: 22px; height: 22px; border-radius: 50%; background: var(--brand-light); color: var(--brand); font-size: 11px; font-weight: 800; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .top-item .ti-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }
  .top-item .ti-clicks { font-size: 12px; font-weight: 700; color: #D97706; white-space: nowrap; }
  .empty-note { color: var(--muted); font-size: 13px; text-align: center; padding: 20px; }

  .funnel-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
  .funnel-box { flex: 1; text-align: center; padding: 14px 8px; border-radius: 12px; background: var(--bg); }
  .funnel-box .fb-val { font-size: 21px; font-weight: 800; }
  .funnel-box .fb-label { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .funnel-arrow { color: var(--muted); font-size: 18px; }

  table.visit-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  table.visit-table th { text-align: left; color: var(--muted); font-weight: 700; font-size: 11px; text-transform: uppercase; padding: 8px 10px; border-bottom: 1px solid var(--line); }
  table.visit-table td { padding: 9px 10px; border-bottom: 1px solid var(--line); }
  table.visit-table tr:last-child td { border-bottom: none; }
  .device-chip { padding: 2px 9px; border-radius: 7px; font-size: 11px; font-weight: 700; }
  .device-chip.Mobil { background: #E8F1FE; color: #2563EB; }
  .device-chip.Kompyuter { background: #E7F6EC; color: #16A34A; }
  .device-chip.Planshet { background: #F3E8FE; color: #9333EA; }
  .device-chip.Bot { background: #FEF3E2; color: #D97706; }
  .table-scroll { overflow-x: auto; }

  .bars-list { display: flex; flex-direction: column; gap: 10px; }
  .bar-row { display: flex; align-items: center; gap: 10px; }
  .bar-row .bl { font-size: 12.5px; font-weight: 600; width: 110px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar-row .bt { flex: 1; height: 8px; background: var(--bg); border-radius: 4px; overflow: hidden; }
  .bar-row .bt .fill { height: 100%; background: var(--brand); border-radius: 4px; }
  .bar-row .bv { font-size: 12px; font-weight: 700; color: var(--muted); width: 30px; text-align: right; flex-shrink: 0; }
  #subarenda-badge { background: var(--brand); color: #fff; font-size: 10px; font-weight: 800; padding: 1px 6px; border-radius: 10px; margin-left: 4px; }
  #subarenda-badge:empty { display: none; }
  .sr-card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin-bottom: 10px; }
  .sr-top { display: flex; justify-content: space-between; align-items: start; gap: 10px; margin-bottom: 8px; }
  .sr-name { font-weight: 700; font-size: 14px; }
  .sr-meta { font-size: 12.5px; color: var(--muted); margin-bottom: 10px; line-height: 1.6; }
  .sr-actions { display: flex; gap: 8px; }
  .sr-actions button { flex: 1; padding: 8px; border-radius: 8px; border: 1px solid var(--line); background: #fff; font-size: 12.5px; font-weight: 700; cursor: pointer; }
  .sr-actions button.approve { background: #16A34A; color: #fff; border: none; }
  .sr-status { font-size: 10.5px; font-weight: 800; padding: 2px 8px; border-radius: 7px; text-transform: uppercase; }
  .sr-status.yangi { background: var(--brand-light); color: var(--brand); }
  .sr-status.bogl { background: #E8F1FE; color: #2563EB; }
  .sr-status.yopiq { background: var(--bg); color: var(--muted); }
</style>
</head>
<body>

<div id="sidebar">
  <div class="side-brand"><img src="/logo.png" alt="logo"> Ijaraga Uylar</div>
  <nav class="side-nav">
    <a data-tab="overview" class="active"><span class="icon">\U0001F4CA</span> Umumiy</a>
    <a data-tab="visitors"><span class="icon">\U0001F465</span> Tashriflar</a>
    <a data-tab="subarenda"><span class="icon">\U0001F3E2</span> Subarenda <span id="subarenda-badge"></span></a>
    <a data-tab="inquiries"><span class="icon">\U0001F4E9</span> So'rovlar <span id="inquiries-badge"></span></a>
    <a data-tab="moderators"><span class="icon">\U0001F46E</span> Moderatorlar</a>
    <a data-tab="mapview"><span class="icon">\U0001F5FA</span> Xarita</a>
  </nav>
  <div class="side-live"><span class="pulse-dot"></span> Jonli holat</div>
</div>

<div id="content">

  <div id="tab-overview" class="tab-page active">
    <div class="page-head"><h1>\U0001F4CA Umumiy ko'rinish</h1></div>
    <div class="kpi-grid" id="kpi-main"><div class="empty-note">Yuklanmoqda...</div></div>
    <div class="kpi-grid" id="kpi-secondary"></div>
    <div class="charts-grid">
      <div class="panel">
        <h2>\U0001F4B5 Oylik daromad tendensiyasi</h2>
        <div class="panel-sub">So'nggi 6 oy — e'lon va Limit daromadi</div>
        <div class="chart-box"><canvas id="revenueChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>\U0001F4DD E'lonlar o'sishi</h2>
        <div class="panel-sub">So'nggi 30 kun</div>
        <div class="chart-box"><canvas id="listingsChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>\U0001F513 Limit sotib olishlar</h2>
        <div class="panel-sub">So'nggi 30 kun</div>
        <div class="chart-box"><canvas id="subsChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>\U0001F5FA Xarita orqali qiziqish</h2>
        <div class="panel-sub">Xaritadan e'longa o'tish jarayoni</div>
        <div class="funnel-row" id="funnel-row"></div>
        <div style="margin-top:16px;">
          <div style="font-size:12px;color:var(--muted);font-weight:700;margin-bottom:8px;">TOP 5 — eng ko'p qiziqish</div>
          <div class="top-list" id="top-clicked"><div class="empty-note">Ma'lumot yo'q</div></div>
        </div>
      </div>
      <div class="panel">
        <h2>\U0001F3F7️ Ijara turi bo'yicha</h2>
        <div class="panel-sub">Hozirgi faol e'lonlar</div>
        <div id="rt-bars" class="bars-list"></div>
      </div>
      <div class="panel">
        <h2>\U0001F4CD Tuman bo'yicha (TOP 8)</h2>
        <div class="panel-sub">Hozirgi faol e'lonlar</div>
        <div id="district-bars" class="bars-list"></div>
      </div>
      <div class="panel">
        <h2>\U0001F3F7️ Toifa va manba bo'yicha</h2>
        <div class="panel-sub">Toifa: hozirgi faol e'lonlar &middot; Manba: so'nggi 30 kun</div>
        <div id="cat-bars" class="bars-list" style="margin-bottom:14px;"></div>
        <div class="funnel-row" id="source-row"></div>
      </div>
    </div>
  </div>

  <div id="tab-visitors" class="tab-page">
    <div class="page-head"><h1>\U0001F465 Sayt tashriflari</h1></div>
    <div class="kpi-grid" id="kpi-visits"></div>
    <div class="charts-grid">
      <div class="panel">
        <h2>\U0001F4C8 So'nggi 14 kunlik tashriflar</h2>
        <div class="panel-sub">Har kungi umumiy sahifa ko'rishlar</div>
        <div class="chart-box"><canvas id="visitsChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>\U0001F4F1 Qurilmalar va davlatlar</h2>
        <div class="panel-sub">So'nggi 7 kun</div>
        <div id="device-bars" class="bars-list" style="margin-bottom:18px;"></div>
        <div id="country-bars" class="bars-list"></div>
      </div>
    </div>
    <div class="panel" style="margin-bottom:16px;">
      <h2>\U0001F4C4 Eng ko'p ko'rilgan sahifalar</h2>
      <div class="panel-sub">So'nggi 7 kun</div>
      <div id="pages-bars" class="bars-list" style="margin-top:14px;"></div>
    </div>
    <div class="panel">
      <h2>\U0001F553 So'nggi tashriflar</h2>
      <div class="panel-sub">Oxirgi 30 ta kirish (jonli)</div>
      <div class="table-scroll">
        <table class="visit-table" id="visits-table">
          <thead><tr><th>Vaqt</th><th>Sahifa</th><th>Davlat/Shahar</th><th>Qurilma</th><th>Brauzer</th></tr></thead>
          <tbody><tr><td colspan="5" class="empty-note">Yuklanmoqda...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <div id="tab-subarenda" class="tab-page">
    <div class="page-head"><h1>\U0001F3E2 Subarenda so\'rovlari</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">Uy egalaridan kelgan, uyni platformaga boshqarishga topshirish so\'rovlari</div>
    <div id="subarenda-list"><div class="empty-note">Yuklanmoqda...</div></div>
  </div>

  <div id="tab-inquiries" class="tab-page">
    <div class="page-head"><h1>\U0001F4E9 Saytdan kelgan so\'rovlar</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">Foydalanuvchilar veb-saytdan e\'lon egalariga yuborgan so\'rovlar</div>
    <div id="inquiries-list"><div class="empty-note">Yuklanmoqda...</div></div>
  </div>

  <div id="tab-moderators" class="tab-page">
    <div class="page-head"><h1>\U0001F46E Moderatorlar nazorati</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">Har bir moderator qancha e'lon joylagani, nechtasi tasdiqlangani/rad etilgani — bot ichida moderator faqat o'zinikini ko'radi, bu yerda siz barchasini bir joyda ko'rasiz</div>
    <div class="panel">
      <div class="table-scroll">
        <table class="visit-table" id="moderators-table">
          <thead><tr><th>Moderator</th><th>Qo'shilgan</th><th>Jami e'lon</th><th>Tasdiqlangan</th><th>Rad etilgan</th><th>So'nggi faollik</th></tr></thead>
          <tbody><tr><td colspan="6" class="empty-note">Yuklanmoqda...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <div id="tab-mapview" class="tab-page">
    <div class="page-head"><h1>\U0001F5FA Faol e'lonlar xaritasi</h1></div>
    <div class="panel"><div id="map"></div></div>
  </div>

</div>

<script>
document.querySelectorAll('.side-nav a').forEach(a => {
  a.addEventListener('click', () => {
    document.querySelectorAll('.side-nav a').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-page').forEach(x => x.classList.remove('active'));
    a.classList.add('active');
    document.getElementById('tab-' + a.dataset.tab).classList.add('active');
    if (a.dataset.tab === 'mapview' && !window._mapLoaded) { loadMap(); window._mapLoaded = true; }
  });
});

function fmtMoney(n) {
  if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n/1000).toFixed(0) + 'k';
  return String(n);
}
function trendBadge(pct) {
  if (pct === null || pct === undefined) return '';
  if (pct > 0) return `<span class="trend up">\u2191 ${pct}%</span>`;
  if (pct < 0) return `<span class="trend down">\u2193 ${Math.abs(pct)}%</span>`;
  return `<span class="trend flat">\u2192 0%</span>`;
}
function barsHtml(items, keyField, maxItems) {
  const top = items.slice(0, maxItems || 6);
  const max = Math.max(...top.map(i => i.c), 1);
  return top.map(i => `
    <div class="bar-row">
      <div class="bl">${i[keyField]}</div>
      <div class="bt"><div class="fill" style="width:${(i.c/max*100)}%"></div></div>
      <div class="bv">${i.c}</div>
    </div>`).join('') || `<div class="empty-note">Ma'lumot yo'q</div>`;
}

let statsCache = null;

async function loadStats() {
  const res = await fetch('/api/stats');
  const s = await res.json();
  statsCache = s;

  document.getElementById('kpi-main').innerHTML = `
    <div class="kpi-card"><div class="icon-badge icon-blue">\U0001F465</div><div class="label">Jami foydalanuvchilar</div><div class="value">${s.total_users}</div>${trendBadge(s.new_users_week_change)}</div>
    <div class="kpi-card"><div class="icon-badge icon-green">\U0001F3E0</div><div class="label">Faol e'lonlar</div><div class="value">${s.active_listings}</div><div style="font-size:12px;color:var(--muted);margin-top:8px;">${s.pending_listings} kutilmoqda</div></div>
    <div class="kpi-card"><div class="icon-badge icon-purple">\U0001F513</div><div class="label">Faol Limit egalari</div><div class="value">${s.active_subscribers}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-pink">\U0001F4B0</div><div class="label">Bu oy jami tushum</div><div class="value">${fmtMoney(s.revenue_month_total)}</div><div style="font-size:11px;color:var(--muted);margin-top:4px;">so'm</div></div>
  `;
  document.getElementById('kpi-secondary').innerHTML = `
    <div class="kpi-card"><div class="icon-badge icon-green">\U0001F4DD</div><div class="label">E'lon daromadi (oy)</div><div class="value">${fmtMoney(s.revenue_month_listings)}</div>${trendBadge(s.revenue_month_listings_change)}</div>
    <div class="kpi-card"><div class="icon-badge icon-purple">\U0001F4B3</div><div class="label">Limit daromadi (oy)</div><div class="value">${fmtMoney(s.revenue_month_subs)}</div>${trendBadge(s.revenue_month_subs_change)}</div>
    <div class="kpi-card"><div class="icon-badge icon-blue">\U0001F4CD</div><div class="label">Joylashuvli e'lonlar</div><div class="value">${s.listings_with_location}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-orange">\U0001F5FA</div><div class="label">Xarita ko'rishlar (oy)</div><div class="value">${s.map_stats.views_month}</div><div style="font-size:12px;color:var(--muted);margin-top:8px;">${s.map_stats.clicks_month} ta bosish</div></div>
  `;
  document.getElementById('funnel-row').innerHTML = `
    <div class="funnel-box"><div class="fb-val">${s.map_stats.total_views}</div><div class="fb-label">Xarita ochilgan</div></div>
    <div class="funnel-arrow">\u2192</div>
    <div class="funnel-box"><div class="fb-val">${s.map_stats.total_clicks}</div><div class="fb-label">Postga o'tilgan</div></div>
    <div class="funnel-arrow">\u2192</div>
    <div class="funnel-box"><div class="fb-val">${s.map_stats.conversion_rate}%</div><div class="fb-label">Konversiya</div></div>
  `;
  const topEl = document.getElementById('top-clicked');
  topEl.innerHTML = s.map_stats.top_clicked.length ? s.map_stats.top_clicked.map((t, i) => `
    <div class="top-item"><div class="ti-left"><div class="ti-rank">${i+1}</div><div class="ti-name">${t.manzil || 'Nomsiz'} — ${t.narx || ''}</div></div><div class="ti-clicks">${t.clicks} bosish</div></div>
  `).join('') : `<div class="empty-note">Hali bosishlar yo'q</div>`;

  document.getElementById('rt-bars').innerHTML = barsHtml(s.rental_type_breakdown, 'label', 10);
  document.getElementById('district-bars').innerHTML = barsHtml(s.district_breakdown, 'label', 8);
  document.getElementById('cat-bars').innerHTML = barsHtml(s.category_breakdown, 'label', 10);
  const srcTotal = (s.source_breakdown.bot || 0) + (s.source_breakdown.web || 0);
  const srcPct = srcTotal ? Math.round((s.source_breakdown.web / srcTotal) * 100) : 0;
  document.getElementById('source-row').innerHTML = `
    <div class="funnel-box"><div class="fb-val">${s.source_breakdown.bot || 0}</div><div class="fb-label">\U0001F916 Bot orqali</div></div>
    <div class="funnel-arrow">+</div>
    <div class="funnel-box"><div class="fb-val">${s.source_breakdown.web || 0}</div><div class="fb-label">\U0001F310 Sayt orqali</div></div>
    <div class="funnel-arrow">=</div>
    <div class="funnel-box"><div class="fb-val">${srcPct}%</div><div class="fb-label">Sayt ulushi</div></div>
  `;

  // Tashriflar KPI
  const v = s.visit_stats;
  document.getElementById('kpi-visits').innerHTML = `
    <div class="kpi-card"><div class="icon-badge icon-pink">\U0001F441</div><div class="label">Jami tashriflar</div><div class="value">${v.total}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-blue">\U0001F4C5</div><div class="label">Bugun</div><div class="value">${v.today}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-green">\U0001F4C8</div><div class="label">So'nggi 7 kun</div><div class="value">${v.week}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-purple">\U0001F464</div><div class="label">Noyob tashrifchi (7 kun)</div><div class="value">${v.unique_week}</div></div>
  `;
  document.getElementById('device-bars').innerHTML = '<div style="font-size:11px;color:var(--muted);font-weight:700;margin-bottom:8px;">QURILMALAR</div>' + barsHtml(v.devices, 'device');
  document.getElementById('country-bars').innerHTML = '<div style="font-size:11px;color:var(--muted);font-weight:700;margin-bottom:8px;">DAVLATLAR</div>' + barsHtml(v.countries, 'country');
  document.getElementById('pages-bars').innerHTML = barsHtml(v.top_pages, 'path', 8);

  const tbody = document.querySelector('#visits-table tbody');
  tbody.innerHTML = v.recent.length ? v.recent.map(r => `
    <tr>
      <td>${r.visited_at.slice(5,16)}</td>
      <td>${r.path}</td>
      <td>${r.city !== 'Mahalliy' ? (r.city + ', ' + r.country) : 'Mahalliy'}</td>
      <td><span class="device-chip ${r.device}">${r.device}</span></td>
      <td>${r.browser}</td>
    </tr>
  `).join('') : `<tr><td colspan="5" class="empty-note">Hali tashrif yo'q</td></tr>`;

  const gridColor = 'rgba(0,0,0,0.04)';
  const tickColor = '#717171';

  if (window._charts) window._charts.forEach(c => c.destroy());
  window._charts = [];

  window._charts.push(new Chart(document.getElementById('revenueChart'), {
    type: 'bar',
    data: { labels: s.monthly_revenue.map(d => d.month), datasets: [
      { label: "E'lon", data: s.monthly_revenue.map(d => d.listings), backgroundColor: '#FF3B5C', borderRadius: 6 },
      { label: 'Limit', data: s.monthly_revenue.map(d => d.subs), backgroundColor: '#9333EA', borderRadius: 6 }
    ]},
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: tickColor, font: { size: 11 } } } },
      scales: { y: { beginAtZero: true, grid: { color: gridColor }, ticks: { color: tickColor } }, x: { grid: { display: false }, ticks: { color: tickColor } } } }
  }));
  window._charts.push(new Chart(document.getElementById('listingsChart'), {
    type: 'bar',
    data: { labels: s.daily_listings.map(d => d.date), datasets: [{ label: "Yangi e'lonlar", data: s.daily_listings.map(d => d.count), backgroundColor: '#2563EB', borderRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, grid: { color: gridColor }, ticks: { color: tickColor, stepSize: 1 } }, x: { grid: { display: false }, ticks: { color: tickColor, maxRotation: 0, autoSkipPadding: 12 } } } }
  }));
  window._charts.push(new Chart(document.getElementById('subsChart'), {
    type: 'line',
    data: { labels: s.daily_subs.map(d => d.date), datasets: [{ label: 'Limit', data: s.daily_subs.map(d => d.count), borderColor: '#D97706', backgroundColor: 'rgba(217,119,6,0.12)', fill: true, tension: 0.35, pointRadius: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, grid: { color: gridColor }, ticks: { color: tickColor, stepSize: 1 } }, x: { grid: { display: false }, ticks: { color: tickColor, maxRotation: 0, autoSkipPadding: 12 } } } }
  }));
  window._charts.push(new Chart(document.getElementById('visitsChart'), {
    type: 'line',
    data: { labels: v.daily.map(d => d.date), datasets: [{ label: 'Tashriflar', data: v.daily.map(d => d.count), borderColor: '#FF3B5C', backgroundColor: 'rgba(255,59,92,0.12)', fill: true, tension: 0.35, pointRadius: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, grid: { color: gridColor }, ticks: { color: tickColor, stepSize: 1 } }, x: { grid: { display: false }, ticks: { color: tickColor, maxRotation: 0, autoSkipPadding: 12 } } } }
  }));
}

async function loadSubarenda() {
  const res = await fetch('/api/subarenda-requests');
  const items = await res.json();
  const badge = document.getElementById('subarenda-badge');
  const pending = items.filter(i => i.status === 'yangi').length;
  badge.textContent = pending > 0 ? pending : '';
  const listEl = document.getElementById('subarenda-list');
  if (!items.length) { listEl.innerHTML = `<div class="empty-note">Hali so'rov yo'q</div>`; return; }
  listEl.innerHTML = items.map(r => `
    <div class="sr-card">
      <div class="sr-top">
        <div class="sr-name">${r.full_name || 'Nomsiz'}</div>
        <span class="sr-status ${r.status}">${r.status}</span>
      </div>
      <div class="sr-meta">
        \U0001F4CD ${r.manzil || '-'}<br>
        \U0001F6CF ${r.xona || '-'} \u00b7 \U0001F4B0 So\'ragan narx: ${r.narx_talab || '-'}<br>
        \U0001F4DE ${r.phone || '-'} \u00b7 \U0001F553 ${r.created_at}
      </div>
      <div class="sr-actions">
        <button onclick="updateSubarenda(${r.id}, 'bogl')">\U0001F4DE Bog'lanildi</button>
        <button class="approve" onclick="updateSubarenda(${r.id}, 'yopiq')">\u2705 Yakunlandi</button>
      </div>
    </div>
  `).join('');
}
async function updateSubarenda(id, status) {
  await fetch(`/api/subarenda-requests/${id}?status=${status}`, { method: 'POST' });
  loadSubarenda();
}

async function loadInquiries() {
  const res = await fetch('/api/listing-inquiries');
  const items = await res.json();
  const badge = document.getElementById('inquiries-badge');
  const pending = items.filter(i => i.status === 'yangi').length;
  badge.textContent = pending > 0 ? pending : '';
  const listEl = document.getElementById('inquiries-list');
  if (!items.length) { listEl.innerHTML = `<div class="empty-note">Hali so'rov yo'q</div>`; return; }
  listEl.innerHTML = items.map(r => `
    <div class="sr-card">
      <div class="sr-top">
        <div class="sr-name">${r.name || 'Nomsiz'}</div>
        <span class="sr-status ${r.status === 'yangi' ? 'yangi' : 'yopiq'}">${r.status}</span>
      </div>
      <div class="sr-meta">
        \U0001F3E0 ${r.listing_manzil || ('E\\'lon #' + r.listing_id)}<br>
        \U0001F4DE ${r.phone || '-'} \u00b7 \U0001F553 ${r.created_at}
        ${r.message ? '<br>\U0001F4AC ' + r.message : ''}
      </div>
      <div class="sr-actions">
        <a href="/uy/${r.listing_id}" target="_blank" style="flex:1;"><button style="width:100%;">\U0001F3E0 E'lonni ko'rish</button></a>
        <button class="approve" onclick="updateInquiry(${r.id})">\u2705 Ko'rib chiqildi</button>
      </div>
    </div>
  `).join('');
}
async function updateInquiry(id) {
  await fetch(`/api/listing-inquiries/${id}?status=yopiq`, { method: 'POST' });
  loadInquiries();
}

async function loadModerators() {
  const res = await fetch('/api/moderator-stats');
  const items = await res.json();
  const tbody = document.querySelector('#moderators-table tbody');
  if (!items.length) { tbody.innerHTML = `<tr><td colspan="6" class="empty-note">Hali moderator qo'shilmagan</td></tr>`; return; }
  tbody.innerHTML = items.map(m => `
    <tr>
      <td><b>${m.full_name}</b>${m.username ? ' &middot; @' + m.username : ''}<br><span style="color:var(--muted);font-size:11px;">ID: ${m.user_id}</span></td>
      <td>${(m.added_at || '-').slice(0, 10)}</td>
      <td>${m.total}</td>
      <td style="color:#16A34A;font-weight:700;">${m.approved}</td>
      <td style="color:#C0362C;font-weight:700;">${m.rejected}</td>
      <td>${m.last_activity ? m.last_activity.slice(0, 16) : '—'}</td>
    </tr>
  `).join('');
}

async function loadMap() {
  const map = L.map('map', { tap: true }).setView([41.311081, 69.240562], 11);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap', maxZoom: 19 }).addTo(map);
  const res = await fetch('/api/listings');
  const listings = await res.json();
  listings.forEach(l => {
    const marker = L.circleMarker([l.latitude, l.longitude], { radius: 8, fillColor: '#FF3B5C', color: '#fff', weight: 2, fillOpacity: 0.9 }).addTo(map);
    if (l.narx) marker.bindTooltip(l.narx, { permanent: true, direction: 'top', className: 'price-label', offset: [0, -6] });
    const postBtn = l.post_link ? `<br><a href="${l.post_link}" target="_blank" class="post-link-btn">\U0001F4E2 Kanaldagi postni ko'rish</a>` : '';
    marker.bindPopup(`<b>${l.manzil || ''}</b><br>\U0001F3AF ${l.moljal || ''}<br>\U0001F6CF ${l.xona || ''} \u2014 \U0001F4B0 ${l.narx || ''}<br>\U0001F465 ${l.kimlarga || ''}<br><small>#${l.id}</small>${postBtn}`);
  });
}

loadStats();
loadSubarenda();
loadInquiries();
loadModerators();
setInterval(loadStats, 60000);
setInterval(loadSubarenda, 30000);
setInterval(loadInquiries, 30000);
setInterval(loadModerators, 60000);
</script>
</body>
</html>
"""

