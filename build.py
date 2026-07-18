#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Прогулки — генератор.

    python3 build.py            собрать в dist/
    python3 build.py --serve    собрать и поднять localhost:8000

Контент лежит в content/<город>/<маршрут>.md, фото — в photos/<город>/<маршрут>/.
Ничего больше знать не нужно: добавил файл, запустил, получил сайт.
"""
import argparse, hashlib, json, math, os, re, shutil, sys, urllib.parse
from datetime import date

import yaml
from PIL import Image, ImageOps
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
PHOTOS = os.path.join(ROOT, "photos")
AUDIO = os.path.join(ROOT, "audio")
THEME = os.path.join(ROOT, "theme")
DIST = os.path.join(ROOT, "dist")

WIDTHS = [560, 900]          # что кладём в dist: телефон и retina
QUALITY = 62

# ---------------------------------------------------------------- разбор .md

POINT_RE = re.compile(r"^##\s+(.+)$", re.M)
FIELD_RE = re.compile(r"^(addr|geo|photo|audio|checked|mine|fragile|closed):\s*(.*)$", re.M)
BLOCK_RE = re.compile(r"^:::\s*(story|warn|look)\s*\n(.*?)^:::\s*$", re.M | re.S)


def parse_route(path):
    raw = open(path, encoding="utf-8").read()
    if not raw.startswith("---"):
        raise ValueError(f"{path}: нет фронтматтера")
    _, fm, body = raw.split("---", 2)
    route = yaml.safe_load(fm) or {}

    chunks = POINT_RE.split(body)[1:]          # [заголовок, тело, заголовок, тело...]
    points = []
    for i in range(0, len(chunks), 2):
        name, chunk = chunks[i].strip(), chunks[i + 1]

        fields = dict(FIELD_RE.findall(chunk))
        blocks = {t: v.strip() for t, v in BLOCK_RE.findall(chunk)}

        audio = None
        if fields.get("audio", "").strip():
            head = [s.strip() for s in fields["audio"].split("·", 1)]
            audio = {"file": head[0], "dur": head[1] if len(head) > 1 else ""}

        text = FIELD_RE.sub("", BLOCK_RE.sub("", chunk)).strip()

        geo = fields.get("geo", "")
        try:
            lat, lon = [float(x) for x in geo.split(",")]
        except ValueError:
            raise ValueError(f"{path} / «{name}»: нет или битый geo (нужно «59.93, 30.31»)")

        points.append({
            "n": len(points) + 1,
            "name": name,
            "addr": fields.get("addr", "").strip(),
            "lat": lat, "lon": lon,
            "photos": [p.strip() for p in fields.get("photo", "").split(",") if p.strip()],
            "checked": fields.get("checked", "").strip(),
            "mine": fields.get("mine", "").strip().lower() in ("yes", "true", "1"),
            "fragile": fields.get("fragile", "").strip().lower() in ("yes", "true", "1"),
            "closed": fields.get("closed", "").strip().lower() in ("yes", "true", "1"),
            "text": [p.strip() for p in text.split("\n\n") if p.strip()],
            "story": [p.strip() for p in blocks.get("story", "").split("\n\n") if p.strip()],
            "warn": blocks.get("warn", "").strip(),
            "look": blocks.get("look", "").strip(),
            "audio": audio,
        })

    route["points"] = points
    route.setdefault("id", os.path.splitext(os.path.basename(path))[0])
    return route


def normalize_quests(q, city_name, path):
    """Пункт квеста — либо строка (как раньше), либо словарь name/addr/geo/note/have.
    Строки в have/todo превращаются в те же словари, чтобы шаблон был один.
    geo даёт точную ссылку на карту, addr без geo — ссылку-поиск."""
    for i, quest in enumerate(q.get("quests") or []):
        quest["qid"] = quest.get("id") or f"q{i}"
        items = quest.get("items")
        if items is None:
            items = [{"name": x, "have": True} for x in quest.get("have") or []] + \
                    [{"name": x} for x in quest.get("todo") or []]
        norm = []
        for it in items:
            if isinstance(it, str):
                it = {"name": it}
            if not it.get("name"):
                it["name"] = it.get("addr", "")
            geo = str(it.get("geo") or "").strip()
            if geo:
                try:
                    lat, lon = [float(x) for x in geo.split(",")]
                except ValueError:
                    raise ValueError(f"{path} / «{quest['title']}» / «{it.get('name')}»: "
                                     f"битый geo (нужно «59.93, 30.31»)")
                it["map"] = f"https://yandex.ru/maps/?pt={lon},{lat}&z=18&l=map"
            elif it.get("addr"):
                it["map"] = ("https://yandex.ru/maps/?text=" +
                             urllib.parse.quote(f"{city_name}, {it['addr']}"))
            norm.append(it)
        quest["items"] = norm
        if norm and not quest.get("score"):
            n = sum(1 for it in norm if it.get("have"))
            quest["score"] = f"Найдено {n} из {len(norm)}"


def render_map_layers(data, tx):
    """Слои подложки OSM → path-строки в координатах схемы (viewBox 0 0 100)."""
    def d_of(lines, close_only=None, cap=60000):
        segs, total = [], 0
        for line in lines:
            xy = [tx(la, lo) for la, lo in line]
            if all(x < -5 or x > 105 or y < -5 or y > 105 for x, y in xy):
                continue
            closed = line[0] == line[-1]
            if close_only is True and not closed:
                continue
            if close_only is False and closed:
                continue
            pts, prev = [], None
            for x, y in xy:
                cur = (round(x, 1), round(y, 1))
                if cur != prev:
                    pts.append(cur)
                    prev = cur
            if len(pts) < 2:
                continue
            seg = "M" + "L".join(f"{x} {y}" for x, y in pts)
            if closed:
                seg += "Z"
            total += len(seg)
            if total > cap:
                break
            segs.append(seg)
        return "".join(segs)

    L = data.get("layers", {})
    out = {
        "bld": d_of(L.get("bld", []), close_only=True, cap=90000),
        "water_fill": d_of(L.get("water", []), close_only=True),
        "water_line": d_of(L.get("water", []), close_only=False),
        "park": d_of(L.get("park", []), close_only=True),
        "road": d_of(L.get("road", [])),
        "lane": d_of(L.get("lane", [])),
        "rail": d_of(L.get("rail", [])),
    }
    return out if any(out.values()) else None


def process_quest_photos(city, BASE=""):
    """Фото у пунктов квестов: photos/<город>/quests/<файл> → dist/img/<город>/quests/."""
    if not city.get("quests"):
        return
    src_dir = os.path.join(PHOTOS, city["id"], "quests")
    if not os.path.isdir(src_dir):
        return
    out_dir = os.path.join(DIST, "img", city["id"], "quests")
    os.makedirs(out_dir, exist_ok=True)
    for quest in city["quests"].get("quests") or []:
        for it in quest.get("items") or []:
            fn = it.get("photo")
            if not fn:
                continue
            src = os.path.join(src_dir, fn)
            if not os.path.exists(src):
                print(f"  ! нет файла {city['id']}/quests/{fn}")
                continue
            im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
            stem = os.path.splitext(fn)[0]
            srcset = []
            for w in WIDTHS:
                ow, oh = im.size
                r = im if ow <= w else im.resize((w, round(oh * w / ow)), Image.LANCZOS)
                name = f"{stem}-{w}.jpg"
                r.save(os.path.join(out_dir, name), "JPEG",
                       quality=QUALITY, optimize=True, progressive=True)
                srcset.append((f"{BASE}/img/{city['id']}/quests/{name}", w))
            it["shot"] = {"src": srcset[0][0],
                          "srcset": ", ".join(f"{u} {w}w" for u, w in srcset)}


def load_city(city_dir):
    city = yaml.safe_load(open(os.path.join(city_dir, "city.yml"), encoding="utf-8"))
    city["id"] = os.path.basename(city_dir)
    city["routes"] = []
    for fn in sorted(os.listdir(city_dir)):
        if fn.endswith(".md") and not fn.startswith("_"):
            city["routes"].append(parse_route(os.path.join(city_dir, fn)))
    qp = os.path.join(city_dir, "quests.yml")
    city["quests"] = yaml.safe_load(open(qp, encoding="utf-8")) if os.path.exists(qp) else None
    if city["quests"]:
        normalize_quests(city["quests"], city["name"], qp)

    order = city.get("order")
    if order:
        rank = {rid: i for i, rid in enumerate(order)}
        city["routes"].sort(key=lambda r: rank.get(r["id"], 999))
    return city


# ---------------------------------------------------------------- фото

def process_photos(city, route, BASE=""):
    src_dir = os.path.join(PHOTOS, city["id"], route["id"])
    out_dir = os.path.join(DIST, "img", city["id"], route["id"])
    made = []
    if not os.path.isdir(src_dir):
        return made
    os.makedirs(out_dir, exist_ok=True)

    for p in route["points"]:
        variants = []
        for fn in p["photos"]:
            src = os.path.join(src_dir, fn)
            if not os.path.exists(src):
                print(f"  ! нет файла {city['id']}/{route['id']}/{fn}")
                continue
            im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
            stem = os.path.splitext(fn)[0]
            srcset = []
            for w in WIDTHS:
                ow, oh = im.size
                r = im if ow <= w else im.resize((w, round(oh * w / ow)), Image.LANCZOS)
                name = f"{stem}-{w}.jpg"
                dst = os.path.join(out_dir, name)
                r.save(dst, "JPEG", quality=QUALITY, optimize=True, progressive=True)
                url = f"{BASE}/img/{city['id']}/{route['id']}/{name}"
                srcset.append((url, w))
                made.append(url)
            variants.append({
                "src": srcset[0][0],
                "srcset": ", ".join(f"{u} {w}w" for u, w in srcset),
            })
        p["shots"] = variants
    return made


def process_audio(city, route, BASE=""):
    src_dir = os.path.join(AUDIO, city["id"], route["id"])
    out_dir = os.path.join(DIST, "audio", city["id"], route["id"])
    made = []
    for p in route["points"]:
        a = p["audio"]
        if not a:
            continue
        src = os.path.join(src_dir, a["file"])
        if not os.path.exists(src):
            print(f"  ! нет аудио {city['id']}/{route['id']}/{a['file']}")
            p["audio"] = None
            continue
        os.makedirs(out_dir, exist_ok=True)
        shutil.copy(src, os.path.join(out_dir, a["file"]))
        mb = os.path.getsize(src) / 1024 / 1024
        if mb > 5:
            print(f"  ! аудио {a['file']} — {mb:.1f} MB, пожмите (ffmpeg: моно 64 kbps)")
        a["url"] = f"{BASE}/audio/{city['id']}/{route['id']}/{a['file']}"
        made.append(a["url"])
    return made


# ---------------------------------------------------------------- сборка

def build(serve=False):
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    env = Environment(
        loader=FileSystemLoader(os.path.join(THEME, "templates")),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    env.filters["ymaps_route"] = lambda p: f"https://yandex.ru/maps/?rtext=~{p['lat']},{p['lon']}&rtt=pd"
    env.filters["ymaps_point"] = lambda p: f"https://yandex.ru/maps/?ll={p['lon']},{p['lat']}&z=18&pt={p['lon']},{p['lat']},pm2rdm"
    env.filters["ymaps_all"] = lambda pts: (
        "https://yandex.ru/maps/?rtext=" + "~".join(f"{p['lat']},{p['lon']}" for p in pts) + "&rtt=pd"
    )

    cities = []
    for cid in sorted(os.listdir(CONTENT)):
        cdir = os.path.join(CONTENT, cid)
        if os.path.isdir(cdir) and os.path.exists(os.path.join(cdir, "city.yml")):
            cities.append(load_city(cdir))

    site = yaml.safe_load(open(os.path.join(ROOT, "site.yml"), encoding="utf-8"))
    site["base"] = (site.get("base") or "").rstrip("/")
    BASE = site["base"]
    shell = []                                   # что кэшируем при установке

    for city in cities:
        for route in city["routes"]:
            imgs = process_photos(city, route, BASE)
            sounds = process_audio(city, route, BASE)
            route["offline_urls"] = imgs + sounds
            route["img_count"] = len(imgs)
            route["n_points"] = len(route["points"])
            route["n_stories"] = sum(1 for p in route["points"] if p["story"])
            route["cover"] = next(
                (p["shots"][0]["src"] for p in route["points"] if p.get("shots")), None)
        process_quest_photos(city, BASE)
        for route in city["routes"]:

            # нормированные координаты для svg-схемы маршрута (viewBox 0 0 100 100)
            pts = route["points"]
            route["map"] = None
            if pts:
                la0, la1 = min(p["lat"] for p in pts), max(p["lat"] for p in pts)
                lo0, lo1 = min(p["lon"] for p in pts), max(p["lon"] for p in pts)
                kx = math.cos(math.radians((la0 + la1) / 2))
                w, h = (lo1 - lo0) * kx, (la1 - la0)
                scale = 82 / (max(w, h) or 1e-9)
                xoff = 9 + (82 - w * scale) / 2
                yoff = 9 + (82 - h * scale) / 2

                def tx(lat, lon):
                    return (xoff + (lon - lo0) * kx * scale,
                            yoff + (la1 - lat) * scale)

                placed = []
                for p in pts:
                    x, y = tx(p["lat"], p["lon"])
                    ox, oy = x, y
                    # раздвинуть совпадающие/слипшиеся точки
                    for qx, qy in placed:
                        dx, dy = x - qx, y - qy
                        d = (dx * dx + dy * dy) ** .5
                        if d < 4.5:
                            if d < .01:
                                dx, dy, d = 1.0, -1.0, 2 ** .5
                            x, y = qx + dx / d * 4.5, qy + dy / d * 4.5
                    p["mx"], p["my"] = round(x, 1), round(y, 1)
                    if ((x - ox) ** 2 + (y - oy) ** 2) ** .5 > 2.5:
                        p["lx"], p["ly"] = round(ox, 1), round(oy, 1)
                    placed.append((x, y))

                mp = os.path.join(CONTENT, city["id"], "_map", route["id"] + ".json")
                if os.path.exists(mp):
                    mdata = json.load(open(mp, encoding="utf-8"))
                    route["map"] = render_map_layers(mdata, tx)
                    if route["map"] is not None and mdata.get("walk"):
                        wpts, prev = [], None
                        for la, lo in mdata["walk"]:
                            x, y = tx(la, lo)
                            cur = (round(x, 1), round(y, 1))
                            if cur != prev:
                                wpts.append(cur)
                                prev = cur
                        if len(wpts) > 1:
                            route["map"]["walk"] = "M" + "L".join(
                                f"{x} {y}" for x, y in wpts)
                route["geo_params"] = (f"{la1:.6f},{lo0:.6f},{kx:.6f},"
                                       f"{scale:.4f},{xoff:.2f},{yoff:.2f}")

            size = sum(os.path.getsize(os.path.join(DIST, *u[len(BASE):].strip("/").split("/")))
                       for u in route["offline_urls"])
            mb = size / 1024 / 1024
            route["offline_mb"] = f"{mb:.1f}" if mb < 3 else f"{mb:.0f}"

            out = os.path.join(DIST, city["id"], route["id"])
            os.makedirs(out, exist_ok=True)
            html = env.get_template("route.html").render(
                site=site, city=city, route=route, today=date.today().isoformat())
            open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)

        if city.get("quests"):
            qout = os.path.join(DIST, city["id"], "quests")
            os.makedirs(qout, exist_ok=True)
            html = env.get_template("quests.html").render(site=site, city=city, q=city["quests"])
            open(os.path.join(qout, "index.html"), "w", encoding="utf-8").write(html)

        out = os.path.join(DIST, city["id"])
        os.makedirs(out, exist_ok=True)
        html = env.get_template("city.html").render(site=site, city=city)
        open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)
        shell.append(f"{BASE}/{city['id']}/")

    stats = {
        "cities": len(cities),
        "routes": sum(len(c["routes"]) for c in cities),
        "points": sum(r["n_points"] for c in cities for r in c["routes"]),
        "stories": sum(r["n_stories"] for c in cities for r in c["routes"]),
    }
    # галерея «находки крупным планом»: проверенные точки со своими фото
    found = [{"shot": p["shots"][0], "name": p["name"], "addr": p["addr"],
              "city": c["name"]}
             for c in cities for r in c["routes"] for p in r["points"]
             if p.get("shots") and p.get("checked")]
    want = site.get("hero_photo") or ""
    hero_shot = next((g["shot"] for g in found if want and want in g["shot"]["src"]),
                     found[0]["shot"] if found else None)
    gallery = [g for g in found if g["shot"] is not hero_shot][:3]
    html = env.get_template("home.html").render(
        site=site, cities=cities, stats=stats, gallery=gallery, hero_shot=hero_shot)
    open(os.path.join(DIST, "index.html"), "w", encoding="utf-8").write(html)

    # питч для партнёров — /pitch/, с главной на него ссылок нет
    out = os.path.join(DIST, "pitch")
    os.makedirs(out, exist_ok=True)
    html = env.get_template("pitch.html").render(site=site)
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)

    shutil.copy(os.path.join(THEME, "app.css"), os.path.join(DIST, "app.css"))
    fonts_src = os.path.join(THEME, "fonts")
    fonts = []
    if os.path.isdir(fonts_src):
        shutil.copytree(fonts_src, os.path.join(DIST, "fonts"))
        fonts = [f"{BASE}/fonts/{fn}" for fn in sorted(os.listdir(fonts_src))
                 if fn.endswith(".woff2")]
    app_js = open(os.path.join(THEME, "app.js"), encoding="utf-8").read().replace("__BASE__", BASE)
    open(os.path.join(DIST, "app.js"), "w", encoding="utf-8").write(app_js)

    manifest = {
        "name": site["title"], "short_name": site["short"],
        "start_url": (BASE or "") + "/", "display": "standalone",
        "background_color": "#CDC8BD", "theme_color": "#2F353B",
        "icons": [{"src": BASE + "/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
    }
    open(os.path.join(DIST, "manifest.json"), "w").write(json.dumps(manifest, ensure_ascii=False))
    shutil.copy(os.path.join(THEME, "icon.svg"), os.path.join(DIST, "icon.svg"))

    core = [f"{BASE}/", f"{BASE}/app.css", f"{BASE}/app.js",
            f"{BASE}/manifest.json", f"{BASE}/icon.svg"] + fonts + shell
    sw = open(os.path.join(THEME, "sw.js"), encoding="utf-8").read()
    version = hashlib.sha1(json.dumps(core, sort_keys=True).encode()).hexdigest()[:8]
    sw = (sw.replace("__VERSION__", version)
            .replace("__CORE__", json.dumps(core, ensure_ascii=False))
            .replace("__BASE__", BASE))
    open(os.path.join(DIST, "sw.js"), "w", encoding="utf-8").write(sw)

    open(os.path.join(DIST, ".nojekyll"), "w").write("")

    np = sum(len(r["points"]) for c in cities for r in c["routes"])
    ns = sum(r["n_stories"] for c in cities for r in c["routes"])
    na = sum(1 for c in cities for r in c["routes"] for p in r["points"] if p["audio"])
    nr = sum(len(c["routes"]) for c in cities)
    mb = sum(os.path.getsize(os.path.join(dp, f))
             for dp, _, fs in os.walk(DIST) for f in fs) / 1024 / 1024
    print(f"\n  {len(cities)} города · {nr} маршрута · {np} точек · {ns} историй"
          + (f" · {na} аудио" if na else ""))
    print(f"  dist/ — {mb:.1f} MB\n")

    if serve:
        import http.server, socketserver, functools, tempfile
        root = DIST
        if BASE:
            # сайт живёт в подпапке — локально повторяем то же самое через симлинк
            root = tempfile.mkdtemp(prefix="progulki-serve-")
            os.symlink(DIST, os.path.join(root, BASE.strip("/")))
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
        print(f"  http://localhost:8000{BASE}/  (Ctrl+C — выход)\n")
        socketserver.TCPServer.allow_reuse_address = True
        socketserver.TCPServer(("", 8000), h).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="поднять локальный сервер")
    build(**vars(ap.parse_args()))
