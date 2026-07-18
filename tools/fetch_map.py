#!/usr/bin/env python3
"""Скачивает подложку для схем маршрутов из OpenStreetMap (Overpass).

Запускать руками при добавлении/изменении маршрута:
    python3 tools/fetch_map.py            # все маршруты
    python3 tools/fetch_map.py spb/nevsky # один

Результат — content/<город>/_map/<маршрут>.json (коммитится в репозиторий;
сборка сети не требует). Данные © участники OpenStreetMap, лицензия ODbL.
"""
import json, os, re, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")
GEO_RE = re.compile(r"^geo:\s*([\d.]+),\s*([\d.]+)", re.M)
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

MAJOR = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
         "residential", "living_street", "pedestrian"}


def routes():
    for city in sorted(os.listdir(CONTENT)):
        cdir = os.path.join(CONTENT, city)
        if not os.path.isdir(cdir):
            continue
        for fn in sorted(os.listdir(cdir)):
            if fn.endswith(".md") and not fn.startswith("_"):
                yield city, fn[:-3], os.path.join(cdir, fn)


def fetch(city, rid, path):
    pts = [(float(a), float(b)) for a, b in GEO_RE.findall(open(path, encoding="utf-8").read())]
    if not pts:
        print(f"  {city}/{rid}: нет geo, пропуск")
        return
    la0, la1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lo0, lo1 = min(p[1] for p in pts), max(p[1] for p in pts)
    pad_la = max((la1 - la0) * 0.18, 0.0025)
    pad_lo = max((lo1 - lo0) * 0.18, 0.004)
    bbox = f"{la0 - pad_la},{lo0 - pad_lo},{la1 + pad_la},{lo1 + pad_lo}"
    q = f"""[out:json][timeout:90];
(
  way["highway"]["highway"!~"^(footway|path|steps|cycleway|track|bridleway|corridor|platform|proposed|construction)$"]({bbox});
  way["natural"="water"]({bbox});
  way["natural"="coastline"]({bbox});
  way["waterway"~"^(river|stream|canal)$"]({bbox});
  way["leisure"~"^(park|garden)$"]({bbox});
  way["landuse"~"^(forest|grass|cemetery)$"]({bbox});
  way["railway"="rail"]({bbox});
);
out geom;"""
    data = None
    for attempt in range(4):
        url = OVERPASS_MIRRORS[attempt % len(OVERPASS_MIRRORS)]
        try:
            req = urllib.request.Request(
                url, data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "progulki-guide/1.0 (severenit@gmail.com)"})
            data = json.load(urllib.request.urlopen(req, timeout=300))
            break
        except Exception as e:
            print(f"  {city}/{rid}: попытка {attempt + 1} не удалась ({e}), жду…")
            time.sleep(10)
    if data is None:
        print(f"  {city}/{rid}: НЕ СКАЧАЛОСЬ, пропуск")
        return

    layers = {"water": [], "park": [], "road": [], "lane": [], "rail": []}
    for el in data.get("elements", []):
        geom = el.get("geometry")
        if not geom:
            continue
        tags = el.get("tags", {})
        line = [(round(g["lat"], 5), round(g["lon"], 5)) for g in geom]
        # прореживание: каждая ~вторая точка на длинных путях
        if len(line) > 60:
            line = line[::2]
        if "highway" in tags:
            key = "road" if tags["highway"] in MAJOR else "lane"
        elif tags.get("railway") == "rail":
            key = "rail"
        elif tags.get("natural") == "water" or "waterway" in tags \
                or tags.get("natural") == "coastline":
            key = "water"
        else:
            key = "park"
        layers[key].append(line)

    out_dir = os.path.join(CONTENT, city, "_map")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{rid}.json")
    json.dump({"bbox": [la0, lo0, la1, lo1], "layers": layers},
              open(out, "w"), separators=(",", ":"))
    n = sum(len(v) for v in layers.values())
    print(f"  {city}/{rid}: {n} путей, {os.path.getsize(out)//1024} KB")


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for city, rid, path in routes():
        if only and f"{city}/{rid}" != only:
            continue
        out = os.path.join(CONTENT, city, "_map", f"{rid}.json")
        if os.path.exists(out) and not only:
            print(f"  {city}/{rid}: уже есть, пропуск")
            continue
        fetch(city, rid, path)
        time.sleep(3)
