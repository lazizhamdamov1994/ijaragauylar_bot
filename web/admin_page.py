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
  .side-group-label { font-size: 10px; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; padding: 14px 12px 6px; }
  .side-group-label:first-child { padding-top: 4px; }
  .side-badge { background: var(--brand); color: #fff; font-size: 10px; font-weight: 800; padding: 1px 6px; border-radius: 10px; margin-left: auto; }
  .side-badge:empty { display: none; }
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
    .side-brand, .side-live, .side-group-label { display: none; }
    .side-nav {
      display: flex; width: 100%; justify-content: flex-start; overflow-x: auto;
      -webkit-overflow-scrolling: touch; flex-wrap: nowrap;
    }
    .side-nav a { flex: 0 0 auto; flex-direction: column; gap: 3px; font-size: 10.5px; padding: 8px 10px; text-align: center; position: relative; }
    .side-badge { position: absolute; margin-left: 0; transform: translate(8px, -8px); }
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
  .sr-actions button.reject { color: #DC2626; border-color: #FCA5A5; }
  .sr-status { font-size: 10.5px; font-weight: 800; padding: 2px 8px; border-radius: 7px; text-transform: uppercase; }
  .sr-status.yangi { background: var(--brand-light); color: var(--brand); }
  .sr-status.bogl { background: #E8F1FE; color: #2563EB; }
  .sr-status.yopiq { background: var(--bg); color: var(--muted); }

  /* ===== ADMIN: forms, buttons, modal (Kutilmoqda/Obunachilar/Xavfli/Qidiruv/Bloklangan/Sozlamalar) ===== */
  .form-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
  .form-row label { font-size: 12px; font-weight: 700; color: var(--ink-soft); }
  .form-row .hint { font-size: 11.5px; color: var(--muted); }
  .form-row input, .form-row textarea, .form-row select {
    padding: 9px 11px; border: 1px solid var(--line); border-radius: 8px; font-size: 13.5px;
    font-family: inherit; background: #fff; color: var(--ink);
  }
  .inline-form { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-end; }
  .inline-form .form-row { margin-bottom: 0; flex: 1; min-width: 140px; }
  .btn { padding: 9px 16px; border-radius: 8px; border: none; font-weight: 700; font-size: 13px; cursor: pointer; white-space: nowrap; }
  .btn-primary { background: var(--brand); color: #fff; }
  .btn-secondary { background: var(--bg); color: var(--ink); border: 1px solid var(--line); }
  .btn-danger { background: #FDEDEB; color: #C0362C; }
  .btn-ghost { background: transparent; color: var(--brand); border: 1px solid var(--brand-light); }
  .btn:disabled { opacity: .5; cursor: default; }
  .photo-thumbs { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0; }
  .photo-thumbs img { width: 68px; height: 68px; object-fit: cover; border-radius: 8px; border: 1px solid var(--line); }
  .risk-score { font-weight: 800; }
  .risk-score.hi { color: #C0362C; }
  .risk-score.mid { color: #D97706; }
  .risk-score.lo { color: var(--ink-soft); }
  .settings-card { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 12px 14px; background: var(--bg); border-radius: 10px; margin-bottom: 10px; flex-wrap: wrap; }
  .settings-card .sc-label { font-weight: 700; font-size: 13.5px; }
  .settings-card .sc-hint { font-size: 11.5px; color: var(--muted); margin-top: 2px; }
  .settings-card .sc-value { display: flex; align-items: center; gap: 8px; }
  .toggle-btn { width: 42px; height: 24px; border-radius: 14px; border: none; cursor: pointer; position: relative; background: var(--line); }
  .toggle-btn.on { background: #16A34A; }
  .toggle-btn::after { content: ''; position: absolute; top: 2px; left: 2px; width: 20px; height: 20px; border-radius: 50%; background: #fff; transition: left .15s; }
  .toggle-btn.on::after { left: 20px; }
  .modal-overlay { position: fixed; inset: 0; background: rgba(16,24,38,.5); z-index: 500; display: flex; align-items: center; justify-content: center; padding: 18px; }
  .modal-box { background: #fff; border-radius: 16px; padding: 22px; max-width: 440px; width: 100%; max-height: 86vh; overflow-y: auto; box-shadow: var(--shadow-md); }
  .modal-box h3 { font-size: 17px; margin-bottom: 14px; }
  .modal-close { float: right; background: var(--bg); border: none; border-radius: 8px; width: 28px; height: 28px; cursor: pointer; font-size: 15px; }
  .uc-row { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid var(--line); font-size: 13px; }
  .uc-row:last-of-type { border-bottom: none; }
  .uc-row .uc-k { color: var(--muted); }
  .uc-row .uc-v { font-weight: 700; text-align: right; }
  .uc-reasons { font-size: 12px; color: var(--muted); margin: 6px 0 10px; padding-left: 16px; }
  .uc-actions { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
  .uc-actions .btn { flex: 1; }
  .search-result { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; background: var(--bg); border-radius: 10px; margin-bottom: 8px; cursor: pointer; }
  .search-result:hover { background: var(--brand-light); }
</style>
</head>
<body>

<div id="sidebar">
  <div class="side-brand"><img src="/logo.png" alt="logo"> Ijaraga Uylar</div>
  <nav class="side-nav">
    <div class="side-group-label">Analitika</div>
    <a data-tab="overview" class="active"><span class="icon">\U0001F4CA</span> Umumiy</a>
    <a data-tab="visitors"><span class="icon">\U0001F465</span> Tashriflar</a>
    <a data-tab="mapview"><span class="icon">\U0001F5FA</span> Xarita</a>

    <div class="side-group-label">Moderatsiya</div>
    <a data-tab="pending"><span class="icon">\U0001F553</span> Kutilmoqda <span id="pending-badge" class="side-badge"></span></a>
    <a data-tab="subarenda"><span class="icon">\U0001F3E2</span> Subarenda <span id="subarenda-badge" class="side-badge"></span></a>
    <a data-tab="inquiries"><span class="icon">\U0001F4E9</span> So'rovlar <span id="inquiries-badge" class="side-badge"></span></a>
    <a data-tab="support"><span class="icon">\U0001F4AC</span> Qo'llab-quvvatlash <span id="support-badge" class="side-badge"></span></a>

    <div class="side-group-label">Foydalanuvchilar</div>
    <a data-tab="subscribers"><span class="icon">\U0001F4B3</span> Obunachilar</a>
    <a data-tab="flagged"><span class="icon">\U0001F6A8</span> Xavfli <span id="flagged-badge" class="side-badge"></span></a>
    <a data-tab="usersearch"><span class="icon">\U0001F50D</span> Qidiruv</a>
    <a data-tab="moderators"><span class="icon">\U0001F46E</span> Moderatorlar</a>

    <div class="side-group-label">Tizim</div>
    <a data-tab="blocked"><span class="icon">\U0001F6AB</span> Bloklangan</a>
    <a data-tab="districts"><span class="icon">\U0001F5FA</span> Tuman kalit so'zlari</a>
    <a data-tab="settings"><span class="icon">⚙️</span> Sozlamalar</a>
  </nav>
  <div class="side-live"><span class="pulse-dot"></span> Jonli holat</div>
</div>

<div id="content">

  <div id="tab-overview" class="tab-page active">
    <div class="page-head"><h1>\U0001F4CA Umumiy ko'rinish</h1></div>

    <div class="panel" style="margin-bottom:16px;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div>
          <h2 id="period-stats-label">\U0001F4CA Davr statistikasi</h2>
          <div class="panel-sub" id="period-stats-sublabel"></div>
        </div>
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
          <button class="btn btn-primary period-btn" data-period="daily" onclick="loadPeriodStats('daily')">Kunlik</button>
          <button class="btn btn-secondary period-btn" data-period="weekly" onclick="loadPeriodStats('weekly')">Haftalik</button>
          <button class="btn btn-secondary period-btn" data-period="monthly" onclick="loadPeriodStats('monthly')">Oylik</button>
          <button class="btn btn-secondary period-btn" data-period="yearly" onclick="loadPeriodStats('yearly')">Yillik</button>
        </div>
      </div>
      <div class="kpi-grid" id="period-kpi-grid" style="margin-top:16px;"><div class="empty-note">Yuklanmoqda...</div></div>
    </div>

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

  <div id="tab-pending" class="tab-page">
    <div class="page-head"><h1>\U0001F553 Kutilmoqda</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">Yangi e'lon va Limit (obuna) so'rovlari — tasdiqlansa e'lon kanalga joylanadi</div>
    <div class="panel" style="margin-bottom:16px;">
      <h2>\U0001F4DD E'lon so'rovlari</h2>
      <div class="panel-sub">Tasdiqlash — kanalga darhol post qilinadi</div>
      <div id="pending-listings-list" style="margin-top:12px;"><div class="empty-note">Yuklanmoqda...</div></div>
    </div>
    <div class="panel">
      <h2>\U0001F4B3 Limit (obuna) so'rovlari</h2>
      <div id="pending-subs-list" style="margin-top:12px;"><div class="empty-note">Yuklanmoqda...</div></div>
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
    <div class="panel" style="margin-bottom:16px;">
      <div class="table-scroll">
        <table class="visit-table" id="moderators-table">
          <thead><tr><th>Moderator</th><th>Qo'shilgan</th><th>Jami e'lon</th><th>Tasdiqlangan</th><th>Rad etilgan</th><th>So'nggi faollik</th><th></th></tr></thead>
          <tbody><tr><td colspan="7" class="empty-note">Yuklanmoqda...</td></tr></tbody>
        </table>
      </div>
    </div>
    <div class="panel" style="margin-bottom:16px;">
      <h2>➕ Moderator qo'shish</h2>
      <div class="panel-sub">Moderator e'lonlarni tasdiqlash/rad etish huquqiga ega, admin sozlamalariga kira olmaydi. \U0001F31F Super moderator - bundan tashqari, to'lov cheklarini (Limit so'rovlarini) ham tasdiqlay/rad eta oladi</div>
      <div class="inline-form" style="margin-top:12px;">
        <div class="form-row"><label>Telegram user_id</label><input id="mod-add-input" type="text" placeholder="Masalan: 123456789"></div>
        <button class="btn btn-primary" onclick="addModeratorAction()">Qo'shish</button>
      </div>
    </div>
    <div class="panel">
      <h2>\U0001F451 Qo'shimcha adminlar</h2>
      <div class="panel-sub">To'liq admin huquqiga ega (sozlamalar, moderatorlar, bloklash va h.k.)</div>
      <div class="inline-form" style="margin-top:12px;">
        <div class="form-row"><label>Telegram user_id</label><input id="admin-add-input" type="text" placeholder="Masalan: 123456789"></div>
        <button class="btn btn-primary" onclick="addExtraAdminAction()">Qo'shish</button>
      </div>
      <div id="extra-admins-list" style="margin-top:14px;"></div>
    </div>
  </div>

  <div id="tab-subscribers" class="tab-page">
    <div class="page-head"><h1>\U0001F4B3 Obunachilar</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">Hozir faol Limit egalari</div>
    <div class="panel">
      <div class="table-scroll">
        <table class="visit-table" id="subscribers-table">
          <thead><tr><th>Foydalanuvchi</th><th>user_id</th><th>Telefon</th><th>Muddati</th><th></th></tr></thead>
          <tbody><tr><td colspan="5" class="empty-note">Yuklanmoqda...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <div id="tab-flagged" class="tab-page">
    <div class="page-head"><h1>\U0001F6A8 Xavfli foydalanuvchilar</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">Shubhali faollik bo'yicha xavf balli hisoblangan foydalanuvchilar — ismga bosib batafsil ko'ring</div>
    <div id="flagged-list"><div class="empty-note">Yuklanmoqda...</div></div>
  </div>

  <div id="tab-usersearch" class="tab-page">
    <div class="page-head"><h1>\U0001F50D Foydalanuvchi qidirish</h1></div>
    <div class="panel" style="margin-bottom:16px;">
      <div class="inline-form">
        <div class="form-row"><label>user_id, username yoki ism</label><input id="usersearch-q" type="text" placeholder="Masalan: 123456789 yoki Aziz"></div>
        <button class="btn btn-primary" onclick="runUserSearch()">Qidirish</button>
      </div>
    </div>
    <div id="usersearch-results"></div>
  </div>

  <div id="tab-blocked" class="tab-page">
    <div class="page-head"><h1>\U0001F6AB Bloklangan raqamlar</h1></div>
    <div class="panel" style="margin-bottom:16px;">
      <div class="inline-form">
        <div class="form-row"><label>Telefon raqami</label><input id="block-phone-input" type="text" placeholder="+998901234567"></div>
        <div class="form-row"><label>Sababi</label><input id="block-reason-input" type="text" placeholder="Masalan: yolg'on e'lon"></div>
        <button class="btn btn-primary" onclick="addBlockedPhone()">Bloklash</button>
      </div>
    </div>
    <div id="blocked-list"><div class="empty-note">Yuklanmoqda...</div></div>
  </div>

  <div id="tab-districts" class="tab-page">
    <div class="page-head"><h1>\U0001F5FA Tuman kalit so'zlari</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">Mahalla/mavze/mashxur joy nomlarini ("Darxon" -> Sergeli) tumanlarga biriktiring - "Tezkor e'lon" (bot) bunday so'zlarni matndan avtomatik tanib oladi, sayt tuman filtri ham ularni hisobga oladi</div>
    <div class="panel" style="margin-bottom:16px;">
      <h2>\U00002795 Yangi kalit so'z qo'shish</h2>
      <div class="inline-form" style="margin-top:12px;">
        <div class="form-row"><label>Tuman</label>
          <select id="distalias-district-select"></select>
        </div>
        <div class="form-row"><label>Kalit so'z(lar) - vergul bilan bir nechtasi</label>
          <input id="distalias-add-input" type="text" placeholder="Masalan: Darxon, Yangi Darxon">
        </div>
        <button class="btn btn-primary" onclick="addDistrictAliasAction()">Qo'shish</button>
      </div>
    </div>
    <div class="panel">
      <div class="table-scroll">
        <table class="visit-table" id="district-aliases-table">
          <thead><tr><th>Tuman</th><th>Kalit so'z</th><th>Qo'shilgan</th><th></th></tr></thead>
          <tbody><tr><td colspan="4" class="empty-note">Yuklanmoqda...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <div id="tab-settings" class="tab-page">
    <div class="page-head"><h1>⚙️ Sozlamalar</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">O'zgarish darhol, botni qayta ishga tushirmasdan, hamma joyda kuchga kiradi</div>
    <div class="panel" style="margin-bottom:16px;" id="settings-list"><div class="empty-note">Yuklanmoqda...</div></div>
    <div class="panel">
      <h2>\U0001F4E2 Barcha foydalanuvchilarga xabar yuborish</h2>
      <div class="panel-sub">Kabinetdagi «Bildirishnomalar» bo'limida ko'rinadi</div>
      <div class="form-row" style="margin-top:12px;"><label>Sarlavha</label><input id="broadcast-title" type="text" maxlength="120"></div>
      <div class="form-row"><label>Matn</label><textarea id="broadcast-body" rows="3" maxlength="1000"></textarea></div>
      <button class="btn btn-primary" onclick="sendBroadcast()">Yuborish</button>
    </div>
    <div class="panel" style="margin-top:16px;">
      <h2>\U0001F4E2 Kanalga to'g'ridan-to'g'ri post yuborish</h2>
      <div class="panel-sub">Muhim e'lon/ogohlantirishlar uchun - moderatsiya navbatidan tashqari, darhol kanalga chiqadi</div>
      <div class="form-row" style="margin-top:12px;"><label>Matn (HTML formatlashga ruxsat: &lt;b&gt;, &lt;i&gt;)</label><textarea id="channelpost-text" rows="4" maxlength="4000"></textarea></div>
      <div class="form-row"><label>Rasm (ixtiyoriy)</label><input id="channelpost-photo" type="file" accept="image/*"></div>
      <button class="btn btn-primary" onclick="sendChannelPost()">\U0001F4E2 Kanalga yuborish</button>
      <div id="channelpost-result" style="margin-top:10px;font-size:13px;"></div>
    </div>
  </div>

  <div id="tab-support" class="tab-page">
    <div class="page-head"><h1>\U0001F4AC Qo'llab-quvvatlash so'rovlari</h1></div>
    <div class="panel-sub" style="margin-bottom:16px;">Shaxsiy kabinetdan yuborilgan so'rovlar</div>
    <div id="support-list"><div class="empty-note">Yuklanmoqda...</div></div>
  </div>

  <div id="tab-mapview" class="tab-page">
    <div class="page-head"><h1>\U0001F5FA Faol e'lonlar xaritasi</h1></div>
    <div class="panel"><div id="map"></div></div>
  </div>

  <div id="user-card-modal"></div>

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
function periodTrendHtml(oldVal, newVal) {
  if (oldVal === 0 && newVal === 0) return `<span class="trend flat">o'zgarishsiz</span>`;
  if (oldVal === 0) return `<span class="trend up">\U0001F195 yangi</span>`;
  return trendBadge(Math.round((newVal - oldVal) / oldVal * 100));
}

async function loadPeriodStats(period) {
  document.querySelectorAll('.period-btn').forEach(b => {
    const active = b.dataset.period === period;
    b.classList.toggle('btn-primary', active);
    b.classList.toggle('btn-secondary', !active);
  });
  const res = await fetch(`/api/admin/period-stats?period=${period}`);
  const s = await res.json();
  document.getElementById('period-stats-label').textContent = `\U0001F4CA Davr statistikasi — ${s.label}`;
  document.getElementById('period-stats-sublabel').textContent = s.prev_label;
  const c = s.current, p = s.previous;
  const revenueCur = c.listings_income + c.subs_income;
  const revenuePrev = p.listings_income + p.subs_income;
  document.getElementById('period-kpi-grid').innerHTML = `
    <div class="kpi-card"><div class="icon-badge icon-blue">\U0001F465</div><div class="label">Yangi foydalanuvchilar</div><div class="value">${s.new_users}</div>${periodTrendHtml(s.new_users_prev, s.new_users)}</div>
    <div class="kpi-card"><div class="icon-badge icon-green">\U0001F4DD</div><div class="label">Yangi e'lonlar</div><div class="value">${c.listings_total}</div>${periodTrendHtml(p.listings_total, c.listings_total)}<div style="font-size:11px;color:var(--muted);margin-top:8px;">✅ ${c.listings_approved} · ❌ ${c.listings_rejected} · ⏱ ${c.listings_pending}</div></div>
    <div class="kpi-card"><div class="icon-badge icon-pink">\U0001F4B0</div><div class="label">Jami tushum</div><div class="value">${fmtMoney(revenueCur)}</div>${periodTrendHtml(revenuePrev, revenueCur)}<div style="font-size:11px;color:var(--muted);margin-top:4px;">so'm</div></div>
    <div class="kpi-card"><div class="icon-badge icon-purple">\U0001F4B3</div><div class="label">Yangi Limit sotib olishlar</div><div class="value">${c.subs_total}</div>${periodTrendHtml(p.subs_total, c.subs_total)}<div style="font-size:11px;color:var(--muted);margin-top:8px;">${c.subs_approved} tasdiqlangan</div></div>
  `;
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

async function loadPending() {
  const res = await fetch('/api/admin/pending');
  const data = await res.json();
  const badge = document.getElementById('pending-badge');
  const total = (data.listings || []).length + (data.subscriptions || []).length;
  badge.textContent = total > 0 ? total : '';

  const lEl = document.getElementById('pending-listings-list');
  lEl.innerHTML = (data.listings || []).length ? data.listings.map(l => `
    <div class="sr-card">
      <div class="sr-top">
        <div class="sr-name">${l.manzil || (l.raw_text || '').slice(0, 60) || 'Nomsiz'} — ${l.narx || ''}</div>
        <span class="sr-status yangi">#${l.id}</span>
      </div>
      <div class="sr-meta">
        \U0001F464 ${l.full_name || 'Nomsiz'}${l.username ? ' · @' + l.username : ''}<br>
        \U0001F4DE ${l.telefon || '-'} · \U0001F553 ${l.created_at}<br>
        \U0001F3AF ${l.moljal || ''} · \U0001F6CF ${l.xona || ''}
      </div>
      <div class="photo-thumbs">${(l.photos || []).map(fid => `<img src="/photo/${fid}" loading="lazy">`).join('')}</div>
      <div class="sr-actions">
        <button class="approve" onclick="approvePendingListing(${l.id})">✅ Tasdiqlash</button>
        <button onclick="rejectPendingListing(${l.id})">❌ Rad etish</button>
      </div>
    </div>
  `).join('') : `<div class="empty-note">Kutilayotgan e'lon yo'q</div>`;

  const sEl = document.getElementById('pending-subs-list');
  sEl.innerHTML = (data.subscriptions || []).length ? data.subscriptions.map(s => `
    <div class="sr-card">
      <div class="sr-top">
        <div class="sr-name">${s.full_name || 'Nomsiz'}${s.username ? ' · @' + s.username : ''}</div>
        <span class="sr-status yangi">#${s.id}</span>
      </div>
      <div class="sr-meta">\U0001F194 user_id: ${s.user_id} · \U0001F553 ${s.created_at}</div>
      ${s.receipt_photo ? `<div class="photo-thumbs"><img src="/photo/${s.receipt_photo}" loading="lazy"></div>` : ''}
      <div class="sr-actions">
        <button class="approve" onclick="approvePendingSub(${s.id})">✅ Tasdiqlash</button>
        <button onclick="rejectPendingSub(${s.id})">❌ Rad etish</button>
      </div>
    </div>
  `).join('') : `<div class="empty-note">Kutilayotgan obuna so'rovi yo'q</div>`;
}
async function approvePendingListing(id) {
  const res = await fetch(`/api/admin/pending/listing/${id}/approve`, { method: 'POST' });
  if (!res.ok) alert("Xatolik: kanalga joylashda muammo bo'ldi.");
  loadPending();
}
async function rejectPendingListing(id) {
  const reason = prompt('Rad etish sababini yozing:');
  if (!reason) return;
  await fetch(`/api/admin/pending/listing/${id}/reject?reason=${encodeURIComponent(reason)}`, { method: 'POST' });
  loadPending();
}
async function approvePendingSub(id) {
  await fetch(`/api/admin/pending/subscription/${id}/approve`, { method: 'POST' });
  loadPending();
}
async function rejectPendingSub(id) {
  const reason = prompt('Rad etish sababini yozing:');
  if (!reason) return;
  await fetch(`/api/admin/pending/subscription/${id}/reject?reason=${encodeURIComponent(reason)}`, { method: 'POST' });
  loadPending();
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
        <button class="reject" onclick="deleteSubarenda(${r.id})">\U0001F5D1 O'chirish</button>
      </div>
    </div>
  `).join('');
}
async function updateSubarenda(id, status) {
  await fetch(`/api/subarenda-requests/${id}?status=${status}`, { method: 'POST' });
  loadSubarenda();
}
async function deleteSubarenda(id) {
  if (!confirm("So'rovni butunlay o'chirasizmi?")) return;
  await fetch(`/api/subarenda-requests/${id}/delete`, { method: 'POST' });
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
        <button class="reject" onclick="deleteInquiry(${r.id})">\U0001F5D1 O'chirish</button>
      </div>
    </div>
  `).join('');
}
async function updateInquiry(id) {
  await fetch(`/api/listing-inquiries/${id}?status=yopiq`, { method: 'POST' });
  loadInquiries();
}
async function deleteInquiry(id) {
  if (!confirm("So'rovni butunlay o'chirasizmi?")) return;
  await fetch(`/api/listing-inquiries/${id}/delete`, { method: 'POST' });
  loadInquiries();
}

async function loadModerators() {
  const res = await fetch('/api/moderator-stats');
  const items = await res.json();
  const tbody = document.querySelector('#moderators-table tbody');
  if (!items.length) { tbody.innerHTML = `<tr><td colspan="7" class="empty-note">Hali moderator qo'shilmagan</td></tr>`; return; }
  tbody.innerHTML = items.map(m => `
    <tr>
      <td><b>${m.full_name}</b>${m.username ? ' &middot; @' + m.username : ''}${m.is_super ? ' <span style="background:#FDF3DE;color:#D6960B;font-size:10.5px;font-weight:800;padding:2px 7px;border-radius:7px;">\U0001F31F SUPER</span>' : ''}<br><span style="color:var(--muted);font-size:11px;">ID: ${m.user_id}</span></td>
      <td>${(m.added_at || '-').slice(0, 10)}</td>
      <td>${m.total}</td>
      <td style="color:#16A34A;font-weight:700;">${m.approved}</td>
      <td style="color:#C0362C;font-weight:700;">${m.rejected}</td>
      <td>${m.last_activity ? m.last_activity.slice(0, 16) : '—'}</td>
      <td style="white-space:nowrap;">
        <button class="btn btn-secondary" style="padding:5px 10px;font-size:11.5px;" onclick="toggleModeratorSuperAction(${m.user_id}, ${!m.is_super})">${m.is_super ? "⬇️ Oddiy qilish" : "\U0001F31F Super qilish"}</button>
        <button class="btn btn-danger" style="padding:5px 10px;font-size:11.5px;" onclick="removeModeratorAction(${m.user_id})">O'chirish</button>
      </td>
    </tr>
  `).join('');
  loadExtraAdmins();
}
async function toggleModeratorSuperAction(userId, makeSuper) {
  await fetch(`/api/admin/moderators/${userId}/set-super?is_super=${makeSuper}`, { method: 'POST' });
  loadModerators();
}

let districtAliasesLoaded = false;
async function loadDistrictAliases() {
  const res = await fetch('/api/admin/district-aliases');
  const data = await res.json();
  if (!districtAliasesLoaded) {
    const sel = document.getElementById('distalias-district-select');
    sel.innerHTML = data.districts.map(d => `<option value="${d}">${d}</option>`).join('');
    districtAliasesLoaded = true;
  }
  const tbody = document.querySelector('#district-aliases-table tbody');
  if (!data.aliases.length) { tbody.innerHTML = `<tr><td colspan="4" class="empty-note">Hozircha kalit so'z yo'q</td></tr>`; return; }
  tbody.innerHTML = data.aliases.map(a => `
    <tr>
      <td><b>${a.district}</b></td>
      <td>${a.alias}</td>
      <td>${(a.added_at || '-').slice(0, 10)}${a.added_by ? '' : ' (dastlabki)'}</td>
      <td><button class="btn btn-danger" style="padding:5px 10px;font-size:11.5px;" onclick="removeDistrictAliasAction(${a.id})">O'chirish</button></td>
    </tr>
  `).join('');
}
async function addDistrictAliasAction() {
  const district = document.getElementById('distalias-district-select').value;
  const input = document.getElementById('distalias-add-input');
  const alias = input.value.trim();
  if (!alias) { alert("Kalit so'z kiriting."); return; }
  await fetch(`/api/admin/district-aliases/add?district=${encodeURIComponent(district)}&alias=${encodeURIComponent(alias)}`, { method: 'POST' });
  input.value = '';
  loadDistrictAliases();
}
async function removeDistrictAliasAction(aliasId) {
  if (!confirm("Bu kalit so'zni o'chirasizmi?")) return;
  await fetch(`/api/admin/district-aliases/${aliasId}/remove`, { method: 'POST' });
  loadDistrictAliases();
}
async function addModeratorAction() {
  const input = document.getElementById('mod-add-input');
  const uid = parseInt(input.value.trim(), 10);
  if (!uid) { alert("To'g'ri user_id kiriting."); return; }
  await fetch(`/api/admin/moderators/add?target_user_id=${uid}`, { method: 'POST' });
  input.value = '';
  loadModerators();
}
async function removeModeratorAction(userId) {
  if (!confirm("Bu moderatorni o'chirasizmi?")) return;
  await fetch(`/api/admin/moderators/${userId}/remove`, { method: 'POST' });
  loadModerators();
}
async function loadExtraAdmins() {
  const res = await fetch('/api/admin/extra-admins');
  const rows = await res.json();
  const el = document.getElementById('extra-admins-list');
  el.innerHTML = rows.length ? rows.map(a => `
    <div class="search-result" style="cursor:default;">
      <div><b>${a.full_name}</b>${a.username ? ' · @' + a.username : ''}<br><span style="font-size:11.5px;color:var(--muted);">ID: ${a.user_id} · ${(a.added_at || '').slice(0, 10)}</span></div>
      <button class="btn btn-danger" style="padding:5px 10px;font-size:11.5px;" onclick="removeExtraAdminAction(${a.user_id})">O'chirish</button>
    </div>
  `).join('') : `<div class="empty-note">Qo'shimcha admin yo'q</div>`;
}
async function addExtraAdminAction() {
  const input = document.getElementById('admin-add-input');
  const uid = parseInt(input.value.trim(), 10);
  if (!uid) { alert("To'g'ri user_id kiriting."); return; }
  await fetch(`/api/admin/extra-admins/add?target_user_id=${uid}`, { method: 'POST' });
  input.value = '';
  loadExtraAdmins();
}
async function removeExtraAdminAction(userId) {
  if (!confirm("Bu adminni o'chirasizmi?")) return;
  const res = await fetch(`/api/admin/extra-admins/${userId}/remove`, { method: 'POST' });
  if (!res.ok) { alert("Bu admin .env orqali belgilangan — o'chirib bo'lmaydi."); return; }
  loadExtraAdmins();
}

function riskClass(score) {
  if (score >= 40) return 'hi';
  if (score > 0) return 'mid';
  return 'lo';
}

async function loadSubscribers() {
  const res = await fetch('/api/admin/subscribers');
  const rows = await res.json();
  const tbody = document.querySelector('#subscribers-table tbody');
  tbody.innerHTML = rows.length ? rows.map(s => `
    <tr>
      <td><b>${s.full_name || 'Nomsiz'}</b>${s.username ? ' · @' + s.username : ''}</td>
      <td>${s.user_id}</td>
      <td>${s.phone || '-'}</td>
      <td>${(s.expire_at || '').slice(0, 10)}</td>
      <td><button class="btn btn-danger" style="padding:5px 10px;font-size:11.5px;" onclick="cancelSubscriber(${s.sub_id})">Bekor qilish</button></td>
    </tr>
  `).join('') : `<tr><td colspan="5" class="empty-note">Hozircha faol obunachi yo'q</td></tr>`;
}
async function cancelSubscriber(subId) {
  if (!confirm('Obunani bekor qilasizmi?')) return;
  await fetch(`/api/admin/subscribers/${subId}/cancel`, { method: 'POST' });
  loadSubscribers();
}

async function loadFlagged() {
  const res = await fetch('/api/admin/flagged-users');
  const rows = await res.json();
  document.getElementById('flagged-badge').textContent = rows.length ? rows.length : '';
  const el = document.getElementById('flagged-list');
  el.innerHTML = rows.length ? rows.map(f => `
    <div class="search-result" onclick="showUserCard(${f.user_id})">
      <div><b>${f.full_name || 'Nomsiz'}</b>${f.username ? ' · @' + f.username : ''}<br><span style="font-size:11.5px;color:var(--muted);">ID: ${f.user_id} · ${f.lifetime} ta ko'rish</span></div>
      <div class="risk-score ${riskClass(f.score)}">${f.score} ball</div>
    </div>
  `).join('') : `<div class="empty-note">Hozircha xavfli foydalanuvchi yo'q</div>`;
}

async function showUserCard(userId) {
  const res = await fetch(`/api/admin/user-card/${userId}`);
  if (!res.ok) { alert('Foydalanuvchi topilmadi.'); return; }
  const u = await res.json();
  const r = u.risk;
  const reasons = (r.reasons || []).map(x => `<li>${x}</li>`).join('');
  document.getElementById('user-card-modal').innerHTML = `
    <div class="modal-overlay" onclick="if(event.target===this) closeUserCard()">
      <div class="modal-box">
        <button class="modal-close" onclick="closeUserCard()">✕</button>
        <h3>\U0001F464 ${u.full_name || 'Nomsiz'}${u.username ? ' · @' + u.username : ''}</h3>
        <div class="uc-row"><span class="uc-k">user_id</span><span class="uc-v">${u.user_id}</span></div>
        <div class="uc-row"><span class="uc-k">Telefon</span><span class="uc-v">${u.phone || '—'}</span></div>
        <div class="uc-row"><span class="uc-k">Ro'yxatdan o'tgan</span><span class="uc-v">${(u.created_at || '').slice(0, 10) || '—'}</span></div>
        <div class="uc-row"><span class="uc-k">Obuna</span><span class="uc-v">${u.subscribed ? '✅ ' + (u.subscription_expire || '').slice(0, 10) + ' gacha' : "❌ yo'q"}</span></div>
        <div class="uc-row"><span class="uc-k">Xavf balli</span><span class="uc-v risk-score ${riskClass(r.score)}">${r.score}</span></div>
        <div class="uc-row"><span class="uc-k">Bergan e'lonlari</span><span class="uc-v">${u.listings_count}</span></div>
        <div class="uc-row"><span class="uc-k">Shikoyat qilgan</span><span class="uc-v">${u.reports_made}</span></div>
        <div class="uc-row"><span class="uc-k">Unga shikoyat qilingan</span><span class="uc-v">${u.reports_received}</span></div>
        ${u.banned ? '<div class="uc-row"><span class="uc-k">Holat</span><span class="uc-v" style="color:#C0362C;">⛔ Cheklangan</span></div>' : ''}
        ${reasons ? `<ul class="uc-reasons">${reasons}</ul>` : ''}
        <div class="uc-actions">
          ${u.subscribed ? `<button class="btn btn-secondary" onclick="cancelUserSub(${u.user_id})">Obunani bekor qilish</button>` : ''}
          ${u.banned
            ? `<button class="btn btn-secondary" onclick="unbanUserAction(${u.user_id})">Cheklovni olib tashlash</button>`
            : `<button class="btn btn-danger" onclick="banUserAction(${u.user_id})">Botdan cheklash</button>`}
        </div>
      </div>
    </div>`;
}
function closeUserCard() { document.getElementById('user-card-modal').innerHTML = ''; }
async function banUserAction(userId) {
  const reason = prompt('Cheklash sababi:', 'Admin tomonidan cheklandi (shubhali faollik)');
  if (reason === null) return;
  await fetch(`/api/admin/user/${userId}/ban?reason=${encodeURIComponent(reason)}`, { method: 'POST' });
  showUserCard(userId); loadFlagged();
}
async function unbanUserAction(userId) {
  await fetch(`/api/admin/user/${userId}/unban`, { method: 'POST' });
  showUserCard(userId); loadFlagged();
}
async function cancelUserSub(userId) {
  if (!confirm('Obunani bekor qilasizmi?')) return;
  await fetch(`/api/admin/user/${userId}/cancel-subscription`, { method: 'POST' });
  showUserCard(userId); loadSubscribers();
}

async function runUserSearch() {
  const q = document.getElementById('usersearch-q').value.trim();
  const el = document.getElementById('usersearch-results');
  if (!q) { el.innerHTML = ''; return; }
  const res = await fetch(`/api/admin/user-search?q=${encodeURIComponent(q)}`);
  const rows = await res.json();
  el.innerHTML = rows.length ? rows.map(u => `
    <div class="search-result" onclick="showUserCard(${u.user_id})">
      <div><b>${u.full_name || 'Nomsiz'}</b>${u.username ? ' · @' + u.username : ''}<br><span style="font-size:11.5px;color:var(--muted);">ID: ${u.user_id}${u.phone ? ' · ' + u.phone : ''}</span></div>
      <div>→</div>
    </div>
  `).join('') : `<div class="empty-note">Hech narsa topilmadi</div>`;
}
document.getElementById('usersearch-q') && document.getElementById('usersearch-q').addEventListener('keydown', e => { if (e.key === 'Enter') runUserSearch(); });

async function loadBlocked() {
  const res = await fetch('/api/admin/blocked-phones');
  const rows = await res.json();
  const el = document.getElementById('blocked-list');
  el.innerHTML = rows.length ? rows.map(r => `
    <div class="sr-card">
      <div class="sr-top"><div class="sr-name">${r.phone}</div></div>
      <div class="sr-meta">\U0001F4DD ${r.reason || '—'}<br>\U0001F553 ${(r.blocked_at || '').slice(0, 16)}</div>
      <div class="sr-actions">
        <button class="approve" onclick="unblockPhoneAction('${r.phone}')">✅ Blokdan chiqarish</button>
      </div>
    </div>
  `).join('') : `<div class="empty-note">Bloklangan raqam yo'q</div>`;
}
async function addBlockedPhone() {
  const phone = document.getElementById('block-phone-input').value.trim();
  const reason = document.getElementById('block-reason-input').value.trim();
  if (!phone || !reason) { alert('Raqam va sababni kiriting.'); return; }
  const res = await fetch(`/api/admin/blocked-phones/add?phone=${encodeURIComponent(phone)}&reason=${encodeURIComponent(reason)}`, { method: 'POST' });
  if (!res.ok) { alert("Raqam formati noto'g'ri."); return; }
  document.getElementById('block-phone-input').value = '';
  document.getElementById('block-reason-input').value = '';
  loadBlocked();
}
async function unblockPhoneAction(phone) {
  await fetch(`/api/admin/blocked-phones/${encodeURIComponent(phone)}/unblock`, { method: 'POST' });
  loadBlocked();
}

async function loadSettings() {
  const res = await fetch('/api/admin/settings');
  const rows = await res.json();
  const el = document.getElementById('settings-list');
  el.innerHTML = rows.map(s => `
    <div class="settings-card">
      <div>
        <div class="sc-label">${s.label}</div>
        ${s.hint ? `<div class="sc-hint">${s.hint}</div>` : ''}
      </div>
      <div class="sc-value">
        ${s.kind === 'bool'
          ? `<button class="toggle-btn ${s.value === '1' ? 'on' : ''}" onclick="toggleBoolSetting('${s.key}', this)"></button>`
          : `<b>${s.value}</b><button class="btn btn-secondary" style="padding:6px 12px;font-size:12px;" onclick="editSetting('${s.key}', '${s.value}')">Tahrirlash</button>`}
      </div>
    </div>
  `).join('');
}
async function toggleBoolSetting(key, btn) {
  const next = btn.classList.contains('on') ? '0' : '1';
  await fetch(`/api/admin/settings?key=${encodeURIComponent(key)}&value=${next}`, { method: 'POST' });
  loadSettings();
}
async function editSetting(key, current) {
  const value = prompt('Yangi qiymat:', current);
  if (value === null) return;
  const res = await fetch(`/api/admin/settings?key=${encodeURIComponent(key)}&value=${encodeURIComponent(value)}`, { method: 'POST' });
  if (!res.ok) { alert("Qiymat noto'g'ri formatda."); return; }
  loadSettings();
}
async function sendBroadcast() {
  const title = document.getElementById('broadcast-title').value.trim();
  const body = document.getElementById('broadcast-body').value.trim();
  if (!title || !body) { alert('Sarlavha va matnni kiriting.'); return; }
  if (!confirm('Bu xabar BARCHA foydalanuvchilarga yuboriladi. Davom etamizmi?')) return;
  const res = await fetch(`/api/admin/broadcast?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`, { method: 'POST' });
  const data = await res.json();
  document.getElementById('broadcast-title').value = '';
  document.getElementById('broadcast-body').value = '';
  alert(`Xabar ${data.sent || 0} ta foydalanuvchiga yuborildi.`);
}

async function sendChannelPost() {
  const text = document.getElementById('channelpost-text').value.trim();
  const photoInput = document.getElementById('channelpost-photo');
  const resultEl = document.getElementById('channelpost-result');
  if (!text) { alert('Matnni kiriting.'); return; }
  if (!confirm('Bu post DARHOL kanalga chiqadi. Davom etamizmi?')) return;
  const form = new FormData();
  form.append('text', text);
  if (photoInput.files[0]) form.append('photo', photoInput.files[0]);
  resultEl.textContent = 'Yuborilmoqda...';
  resultEl.style.color = 'var(--muted)';
  try {
    const res = await fetch('/api/admin/channel-post', { method: 'POST', body: form });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      resultEl.textContent = '✅ Kanalga yuborildi.';
      resultEl.style.color = '#16A34A';
      document.getElementById('channelpost-text').value = '';
      photoInput.value = '';
    } else {
      resultEl.textContent = '❌ Xatolik: ' + (data.detail || "noma'lum xatolik");
      resultEl.style.color = '#DC2626';
    }
  } catch (err) {
    resultEl.textContent = '❌ Tarmoq xatoligi.';
    resultEl.style.color = '#DC2626';
  }
}

async function loadSupport() {
  const res = await fetch('/api/admin/support-requests');
  const rows = await res.json();
  document.getElementById('support-badge').textContent = rows.length ? rows.length : '';
  const el = document.getElementById('support-list');
  el.innerHTML = rows.length ? rows.map(r => `
    <div class="sr-card">
      <div class="sr-top">
        <div class="sr-name">${r.full_name || 'Nomsiz'}${r.username ? ' · @' + r.username : ''}</div>
        <span class="sr-status yangi">${r.status}</span>
      </div>
      <div class="sr-meta">\U0001F4AC ${r.message}<br>\U0001F553 ${r.created_at}</div>
      <div class="inline-form" style="margin-top:8px;">
        <div class="form-row"><input type="text" id="support-reply-${r.id}" placeholder="Javob yozing..."></div>
        <button class="btn btn-primary" onclick="replySupportRequest(${r.id})">Yuborish</button>
        <button class="btn btn-danger" onclick="deleteSupportRequest(${r.id})">\U0001F5D1 O'chirish</button>
      </div>
    </div>
  `).join('') : `<div class="empty-note">Hozircha so'rov yo'q</div>`;
}
async function replySupportRequest(id) {
  const input = document.getElementById(`support-reply-${id}`);
  const reply = input.value.trim();
  if (!reply) return;
  await fetch(`/api/admin/support-requests/${id}/reply?reply=${encodeURIComponent(reply)}`, { method: 'POST' });
  loadSupport();
}
async function deleteSupportRequest(id) {
  if (!confirm("So'rovni butunlay o'chirasizmi?")) return;
  await fetch(`/api/admin/support-requests/${id}/delete`, { method: 'POST' });
  loadSupport();
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
loadPeriodStats('daily');
loadSubarenda();
loadInquiries();
loadModerators();
loadPending();
loadSubscribers();
loadFlagged();
loadBlocked();
loadSettings();
loadSupport();
loadDistrictAliases();
setInterval(loadStats, 60000);
setInterval(loadSubarenda, 30000);
setInterval(loadInquiries, 30000);
setInterval(loadModerators, 60000);
setInterval(loadPending, 30000);
setInterval(loadSubscribers, 60000);
setInterval(loadFlagged, 60000);
setInterval(loadBlocked, 60000);
setInterval(loadSupport, 30000);
</script>
</body>
</html>
"""

