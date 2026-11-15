/* Nihola Estate — sayt skriptlari */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };

  function toast(text) {
    var t = $('#toast'); if (!t) return;
    t.textContent = text; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(function () { t.hidden = true; }, 1800);
  }

  // ---------- xarita plitkalari (och/tungi) ----------
  window.niholaTiles = function () {
    var dark = document.documentElement.getAttribute('data-theme') === 'dark';
    return 'https://{s}.basemaps.cartocdn.com/' + (dark ? 'dark_all' : 'rastertiles/voyager') + '/{z}/{x}/{y}{r}.png';
  };

  // ---------- tungi rejim ----------
  $$('[data-theme-toggle]').forEach(function (b) {
    b.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', cur);
      try { localStorage.setItem('nihola_theme', cur); } catch (e) {}
      if (document.querySelector('.leaflet-container')) location.reload();
    });
  });

  // ---------- sevimlilar (brauzerda saqlanadi) ----------
  var FKEY = 'nihola_favs';
  var favs = {
    list: function () { return store.get(FKEY, []); },
    has: function (id) { return favs.list().indexOf(id) !== -1; },
    toggle: function (id) {
      var l = favs.list(), i = l.indexOf(id);
      if (i === -1) l.unshift(id); else l.splice(i, 1);
      store.set(FKEY, l.slice(0, 200)); favs.paint(); return i === -1;
    },
    paint: function () {
      var l = favs.list();
      $$('[data-fav]').forEach(function (b) {
        var on = l.indexOf(parseInt(b.getAttribute('data-fav'), 10)) !== -1;
        b.classList.toggle('on', on);
        if (b.hasAttribute('data-fav-label')) { var s = $('span', b); if (s) s.textContent = on ? NIHOLA.saved : NIHOLA.save; }
      });
      $$('[data-fav-count]').forEach(function (c) { c.textContent = l.length; c.hidden = !l.length; });
    }
  };
  window.niholaFavs = favs;
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-fav]');
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    var added = favs.toggle(parseInt(b.getAttribute('data-fav'), 10));
    toast(added ? '♥ ' + NIHOLA.saved : '♡');
  }, true);
  favs.paint();

  // ---------- ko'rinish: katta / panjara / ro'yxat ----------
  var cards = $('#cards');
  function setView(v) {
    if (!cards) return;
    cards.classList.remove('view-big', 'view-grid', 'view-list');
    cards.classList.add('view-' + v);
    $$('[data-view]').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-view') === v); });
    store.set('nihola_view', v);
  }
  if ($('[data-view]')) {
    setView(store.get('nihola_view', 'grid'));
    $$('[data-view]').forEach(function (b) { b.addEventListener('click', function () { setView(b.getAttribute('data-view')); }); });
  }

  // ---------- "Yana ko'rsatish" ----------
  $$('[data-load-more]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var page = btn.getAttribute('data-page');
      var params = new URLSearchParams(location.search); params.set('page', page);
      btn.disabled = true;
      fetch('/api/listings?' + params.toString()).then(function (r) { return r.json(); }).then(function (d) {
        cards.insertAdjacentHTML('beforeend', d.html); favs.paint();
        if (d.has_more) { btn.setAttribute('data-page', String(parseInt(page, 10) + 1)); btn.disabled = false; }
        else btn.parentNode.remove();
      }).catch(function () { btn.disabled = false; });
    });
  });

  // ---------- modallar ----------
  function openModal(id, trigger) {
    var m = document.getElementById(id); if (!m) return;
    m.hidden = false; document.body.style.overflow = 'hidden';
    if (id === 'calc' && trigger && trigger.getAttribute('data-calc-price')) {
      $('#calc [name=price]').value = trigger.getAttribute('data-calc-price');
    }
    if (id === 'calc') niholaCalc();
  }
  function closeModals() { $$('.modal').forEach(function (m) { m.hidden = true; }); document.body.style.overflow = ''; }
  document.addEventListener('click', function (e) {
    var o = e.target.closest('[data-open]');
    if (o) { e.preventDefault(); openModal(o.getAttribute('data-open'), o); return; }
    if (e.target.closest('[data-close]')) closeModals();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModals(); });

  // ---------- dropdownlar: tashqariga bosilsa yopiladi ----------
  document.addEventListener('click', function (e) {
    $$('details.dropdown[open]').forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute('open'); });
  });

  // ---------- ipoteka kalkulyatori ----------
  function money(n) { return Math.round(n).toLocaleString('ru-RU').replace(/,/g, ' ') + ' $'; }
  window.niholaCalc = function () {
    var f = $('#calc form'); if (!f) return;
    var price = +f.price.value || 0, down = +f.down.value, years = +f.years.value, rate = +f.rate.value;
    f.down_o.value = down + '%'; f.years_o.value = years;
    var loan = price * (1 - down / 100), n = years * 12, r = rate / 100 / 12;
    var monthly = r ? loan * r / (1 - Math.pow(1 + r, -n)) : loan / n;
    $('[data-out=monthly]').textContent = money(monthly);
    $('[data-out=loan]').textContent = money(loan);
    $('[data-out=over]').textContent = money(monthly * n - loan);
  };

  // ---------- ulashish ----------
  $$('[data-share]').forEach(function (b) {
    b.addEventListener('click', function () {
      var data = { title: document.title, url: location.href };
      if (navigator.share) { navigator.share(data).catch(function () {}); return; }
      (navigator.clipboard ? navigator.clipboard.writeText(location.href) : Promise.reject())
        .then(function () { toast(NIHOLA.copied); }, function () { prompt('URL', location.href); });
    });
  });

  // ---------- mobil "Qidiruv" tugmasi ----------
  $$('[data-focus-search]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var inp = $('#search input[name=q]');
      if (inp) { e.preventDefault(); inp.scrollIntoView({ behavior: 'smooth', block: 'center' }); setTimeout(function () { inp.focus(); }, 300); }
    });
  });
  if (location.hash === '#search') { var si = $('#search input[name=q]'); if (si) setTimeout(function () { si.focus(); }, 200); }

  // ---------- karusel ----------
  $$('.carousel').forEach(function (c) {
    var track = $('.car-track', c), prev = $('.prev', c), next = $('.next', c);
    var dots = c.parentNode.querySelector('.car-dots');
    var pages = function () { return Math.max(1, Math.ceil(track.scrollWidth / track.clientWidth - 0.05)); };
    function update() {
      var max = track.scrollWidth - track.clientWidth - 2;
      prev.disabled = track.scrollLeft <= 2; next.disabled = track.scrollLeft >= max;
      if (dots) {
        var n = pages(), cur = Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
        if (dots.children.length !== n) { dots.innerHTML = n > 1 ? new Array(n + 1).join('<span></span>') : ''; }
        $$('span', dots).forEach(function (d, i) { d.classList.toggle('on', i === Math.min(cur, n - 1)); });
      }
    }
    prev.addEventListener('click', function () { track.scrollBy({ left: -track.clientWidth, behavior: 'smooth' }); });
    next.addEventListener('click', function () { track.scrollBy({ left: track.clientWidth, behavior: 'smooth' }); });
    track.addEventListener('scroll', function () { requestAnimationFrame(update); });
    window.addEventListener('resize', update); update();
  });

  // ---------- galereya (e'lon sahifasi) ----------
  $$('[data-gallery]').forEach(function (g) {
    var slides = $$('.g-slide', g), thumbs = $$('.g-thumb', g), idx = 0, counter = $('[data-g-index]', g);
    if (slides.length < 2) return;
    function go(i) {
      var v = $('video', slides[idx]); if (v) v.pause();
      idx = (i + slides.length) % slides.length;
      slides.forEach(function (s, k) { s.classList.toggle('on', k === idx); });
      thumbs.forEach(function (t, k) { t.classList.toggle('on', k === idx); });
      if (thumbs[idx]) thumbs[idx].scrollIntoView({ block: 'nearest', inline: 'nearest' });
      if (counter) counter.textContent = idx + 1;
    }
    $('.g-arrow.prev', g).addEventListener('click', function () { go(idx - 1); });
    $('.g-arrow.next', g).addEventListener('click', function () { go(idx + 1); });
    thumbs.forEach(function (t) { t.addEventListener('click', function () { go(+t.getAttribute('data-g-go')); }); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') go(idx - 1);
      if (e.key === 'ArrowRight') go(idx + 1);
    });
    var stage = $('.g-stage', g), x0 = null;
    stage.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; }, { passive: true });
    stage.addEventListener('touchend', function (e) {
      if (x0 === null) return;
      var dx = e.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 40) go(idx + (dx < 0 ? 1 : -1));
      x0 = null;
    });
  });
})();
