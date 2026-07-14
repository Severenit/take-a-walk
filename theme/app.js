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

  boxes.forEach(function (b) {
    var card = b.closest('.card');
    if (found[b.dataset.id]) { b.checked = true; card.classList.add('done'); }
    b.addEventListener('change', function () {
      if (b.checked) { found[b.dataset.id] = 1; } else { delete found[b.dataset.id]; }
      card.classList.toggle('done', b.checked);
      persist();
      tick();
    });
  });
  tick();

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
