(function () {
  'use strict';

  var BASE = '__BASE__';

  // ---------- отметки "нашли" ----------
  var KEY = 'progulki:found';
  var found = {};
  try { found = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
  var persist = function () {
    try { localStorage.setItem(KEY, JSON.stringify(found)); } catch (e) {}
  };

  var boxes = [].slice.call(document.querySelectorAll('.cb'));
  var pnum = document.querySelector('[data-progress-num]');
  var pbar = document.querySelector('[data-progress-bar]');

  function tick() {
    if (!pnum) return;
    var n = boxes.filter(function (b) { return b.checked; }).length;
    pnum.textContent = n;
    if (pbar) pbar.style.width = (boxes.length ? n / boxes.length * 100 : 0) + '%';
  }

  // гасим найденные точки на схеме
  function syncScheme() {
    boxes.forEach(function (b) {
      var n = b.closest('.card').id.replace('p', '');
      var a = document.querySelector('.scheme a[href="#p' + n + '"]');
      if (a) a.classList.toggle('found', b.checked);
    });
  }

  boxes.forEach(function (b) {
    var card = b.closest('.card');
    if (found[b.dataset.id]) { b.checked = true; card.classList.add('done'); }
    b.addEventListener('change', function () {
      if (b.checked) { found[b.dataset.id] = 1; } else { delete found[b.dataset.id]; }
      card.classList.toggle('done', b.checked);
      persist();
      tick();
      syncScheme();
      updResume();
    });
  });
  tick();
  syncScheme();

  // клик по шапке найденной карточки — развернуть/свернуть обратно
  document.addEventListener('click', function (e) {
    var head = e.target.closest('.card.done .head');
    if (head) head.closest('.card').classList.toggle('peek');
  });

  // ---------- «продолжить с ближайшей» ----------
  var resumeBtn = document.querySelector('[data-resume]');
  var geoCards = [].slice.call(document.querySelectorAll('.card[data-lat]'));
  function leftCards() {
    return geoCards.filter(function (c) {
      var cb = c.querySelector('.cb');
      return cb && !cb.checked && !c.classList.contains('gone');
    });
  }
  function updResume() {
    if (!resumeBtn) return;
    var left = leftCards();
    if (!left.length || left.length === geoCards.length) {
      resumeBtn.hidden = (left.length === 0);
      resumeBtn.textContent = 'Продолжить с ближайшей точки';
      return;
    }
    resumeBtn.hidden = false;
    resumeBtn.textContent = 'Продолжить — осталось ' + left.length;
  }
  if (resumeBtn) {
    updResume();
    resumeBtn.addEventListener('click', function () {
      var left = leftCards();
      if (!left.length) return;
      if (!('geolocation' in navigator)) {
        location.hash = '#' + left[0].id;
        return;
      }
      resumeBtn.textContent = 'Ищу вас…';
      navigator.geolocation.getCurrentPosition(function (pos) {
        var la = pos.coords.latitude, lo = pos.coords.longitude;
        var k = Math.cos(la * Math.PI / 180);
        var best = 0, bd = Infinity;
        left.forEach(function (c, i) {
          var dla = parseFloat(c.dataset.lat) - la;
          var dlo = (parseFloat(c.dataset.lon) - lo) * k;
          var d = dla * dla + dlo * dlo;
          if (d < bd) { bd = d; best = i; }
        });
        var seq = left.slice(best);
        var rtext = la.toFixed(6) + ',' + lo.toFixed(6) +
          seq.map(function (c) { return '~' + c.dataset.lat + ',' + c.dataset.lon; }).join('');
        updResume();
        location.hash = '#' + seq[0].id;
        window.open('https://yandex.ru/maps/?rtext=' + rtext + '&rtt=pd', '_blank', 'noopener');
      }, function () {
        updResume();
        location.hash = '#' + left[0].id;
      }, { enableHighAccuracy: true, timeout: 10000 });
    });
  }

  // ---------- отметки в квестах ----------
  var QKEY = 'progulki:qfound';
  var qfound = {};
  try { qfound = JSON.parse(localStorage.getItem(QKEY) || '{}'); } catch (e) {}
  [].slice.call(document.querySelectorAll('li[data-q]')).forEach(function (li) {
    var btn = li.querySelector('.qi-tick');
    if (!btn || li.classList.contains('got')) return;
    var id = li.dataset.q;
    if (qfound[id]) li.classList.add('self');
    btn.addEventListener('click', function () {
      var on = !li.classList.contains('self');
      li.classList.toggle('self', on);
      if (on) { qfound[id] = 1; } else { delete qfound[id]; }
      try { localStorage.setItem(QKEY, JSON.stringify(qfound)); } catch (e) {}
    });
  });

  // ---------- «где я» на схеме ----------
  var geoSvg = document.querySelector('.scheme svg[data-geo]');
  var locBtn = document.querySelector('[data-locate]');
  if (geoSvg && locBtn && 'geolocation' in navigator) {
    var g = geoSvg.dataset.geo.split(',').map(Number); // la1, lo0, kx, scale, xoff, yoff
    var meDot = geoSvg.querySelector('.me');
    var watching = false;
    locBtn.addEventListener('click', function () {
      if (watching) return;
      watching = true;
      locBtn.textContent = 'Ищу вас…';
      navigator.geolocation.watchPosition(function (pos) {
        var x = g[4] + (pos.coords.longitude - g[1]) * g[2] * g[3];
        var y = g[5] + (g[0] - pos.coords.latitude) * g[3];
        if (x < -2 || x > 102 || y < -2 || y > 102) {
          meDot.setAttribute('hidden', 'hidden');
          locBtn.textContent = 'Вы пока за пределами схемы';
          return;
        }
        meDot.removeAttribute('hidden');
        meDot.setAttribute('cx', x.toFixed(1));
        meDot.setAttribute('cy', y.toFixed(1));
        locBtn.textContent = 'Вы — тёмная точка';
      }, function () {
        watching = false;
        locBtn.textContent = 'Геолокация недоступна';
      }, { enableHighAccuracy: true, maximumAge: 5000 });
    });
  } else if (locBtn) {
    locBtn.hidden = true;
  }

  // ---------- аудио-истории ----------
  var playing = null;
  [].slice.call(document.querySelectorAll('[data-player]')).forEach(function (el) {
    var btn = el.querySelector('.pp');
    var track = el.querySelector('.pl-track');
    var fill = el.querySelector('.pl-line i');
    var time = el.querySelector('.pl-time');
    var a = null;

    function fmt(s) {
      s = Math.max(0, Math.round(s));
      return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
    }
    function draw() {
      if (!a || !a.duration) return;
      fill.style.width = (a.currentTime / a.duration * 100) + '%';
      time.textContent = fmt(a.currentTime) + ' / ' + fmt(a.duration);
    }
    function make() {
      if (a) return a;
      a = new Audio(el.dataset.player);
      a.preload = 'metadata';
      a.addEventListener('loadedmetadata', draw);
      a.addEventListener('timeupdate', draw);
      a.addEventListener('play', function () {
        if (playing && playing !== a) playing.pause();
        playing = a;
        el.classList.add('playing');
      });
      a.addEventListener('pause', function () { el.classList.remove('playing'); });
      a.addEventListener('ended', function () { a.currentTime = 0; draw(); });
      return a;
    }

    btn.addEventListener('click', function () {
      var au = make();
      if (au.paused) { au.play(); } else { au.pause(); }
    });
    track.addEventListener('click', function (ev) {
      var au = make();
      if (!au.duration) { au.play(); return; }
      var r = track.getBoundingClientRect();
      au.currentTime = Math.min(Math.max((ev.clientX - r.left) / r.width, 0), 1) * au.duration;
      draw();
      au.play();
    });
  });

  // ---------- офлайн: кладём фото маршрута в кэш ----------
  var btn = document.querySelector('[data-offline]');
  if (btn && 'caches' in window) {
    var urls = [];
    try { urls = JSON.parse(btn.dataset.offline) || []; } catch (e) {}
    var label = btn.querySelector('[data-offline-label]');
    var main = document.querySelector('[data-route]');
    var CACHE = 'progulki-route:' + (main ? main.dataset.route : 'x');

    caches.has(CACHE).then(function (yes) {
      if (yes) { btn.dataset.state = 'saved'; label.textContent = 'Сохранён офлайн ✔'; }
    });

    btn.addEventListener('click', function () {
      if (btn.dataset.state === 'saved' || btn.dataset.state === 'busy') return;
      btn.dataset.state = 'busy';

      var done = 0;
      var pages = [location.pathname, BASE + '/app.css', BASE + '/app.js'];
      var all = pages.concat(urls);

      caches.open(CACHE).then(function (cache) {
        return Promise.all(all.map(function (u) {
          return cache.add(new Request(u, { cache: 'reload' }))
            .catch(function () { /* одна картинка не должна ронять всё */ })
            .then(function () {
              done++;
              label.textContent = 'Качаю… ' + Math.round(done / all.length * 100) + '%';
            });
        }));
      }).then(function () {
        btn.dataset.state = 'saved';
        label.textContent = 'Сохранён офлайн ✔';
      }).catch(function () {
        btn.dataset.state = '';
        label.textContent = 'Не вышло — попробуйте ещё';
      });
    });
  } else if (btn) {
    btn.hidden = true;
  }

  // ---------- service worker ----------
  if ('serviceWorker' in navigator && location.protocol === 'https:') {
    navigator.serviceWorker.register(BASE + '/sw.js').catch(function () {});
  }
})();
