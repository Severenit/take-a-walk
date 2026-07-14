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
