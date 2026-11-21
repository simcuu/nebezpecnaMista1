#!/usr/bin/env python3
"""
Stáhne všechny vrstvy z ArcGIS Instant App (přes webovou mapu) do GeoJSON.
Jen standardní knihovna, nic se nemusí instalovat.

Použití:
    python stahni_arcgis_geojson.py
Výstup: složka ./data/ s jedním .geojson souborem na vrstvu.
"""
import json
import math
import os
import re
import urllib.parse
import urllib.request

PORTAL = "https://smol.maps.arcgis.com/sharing/rest"
APP_ID = "4e1a69abd052489c888b50854aa47a95"
OUT_DIR = "data"
CHUNK = 200  # kolik objektů na jeden dotaz

HEX32 = re.compile(r"^[0-9a-f]{32}$")


def get_json(url, params=None):
    params = dict(params or {})
    params.setdefault("f", "json")
    full = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"{url}: {data['error']}")
    return data


def safe_name(s):
    s = re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE).strip("_")
    return s or "vrstva"


# ---------- nalezení webové mapy za aplikací ----------
def find_webmap_ids(obj, found=None):
    """Projde konfiguraci aplikace a najde ID webových map."""
    if found is None:
        found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            if "webmap" in kl or kl in ("map", "itemid", "id"):
                if isinstance(v, str) and HEX32.match(v):
                    found.append(v)
                elif isinstance(v, list):
                    found += [x for x in v if isinstance(x, str) and HEX32.match(x)]
            find_webmap_ids(v, found)
    elif isinstance(obj, list):
        for x in obj:
            find_webmap_ids(x, found)
    return found


# ---------- převod Esri JSON -> GeoJSON (záloha) ----------
def merc_to_wgs(x, y):
    lon = x / 6378137.0 * 180.0 / math.pi
    lat = (2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2) * 180.0 / math.pi
    return [lon, lat]


def esri_geom_to_geojson(g, mercator=False):
    if not g:
        return None
    conv = (lambda p: merc_to_wgs(p[0], p[1])) if mercator else (lambda p: [p[0], p[1]])
    if "x" in g:
        if g["x"] is None:
            return None
        return {"type": "Point", "coordinates": conv([g["x"], g["y"]])}
    if "points" in g:
        return {"type": "MultiPoint", "coordinates": [conv(p) for p in g["points"]]}
    if "paths" in g:
        paths = [[conv(p) for p in path] for path in g["paths"]]
        return {"type": "LineString", "coordinates": paths[0]} if len(paths) == 1 \
            else {"type": "MultiLineString", "coordinates": paths}
    if "rings" in g:
        # zjednodušeně: každý ring jako samostatný polygon / díry neřešíme dokonale
        rings = [[conv(p) for p in ring] for ring in g["rings"]]
        return {"type": "Polygon", "coordinates": rings} if len(rings) == 1 \
            else {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}
    return None


def esri_features_to_geojson(features, mercator=False):
    return [
        {
            "type": "Feature",
            "geometry": esri_geom_to_geojson(f.get("geometry"), mercator),
            "properties": f.get("attributes", {}),
        }
        for f in features
    ]


# ---------- stažení jedné vrstvy služby ----------
def download_service_layer(layer_url):
    ids_resp = get_json(layer_url + "/query", {"where": "1=1", "returnIdsOnly": "true"})
    ids = ids_resp.get("objectIds") or []
    ids.sort()
    print(f"    {len(ids)} objektů")
    features = []
    for i in range(0, len(ids), CHUNK):
        chunk = ",".join(map(str, ids[i:i + CHUNK]))
        params = {"objectIds": chunk, "outFields": "*", "outSR": 4326}
        try:
            gj = get_json(layer_url + "/query", {**params, "f": "geojson"})
            features += gj.get("features", [])
        except Exception:
            ej = get_json(layer_url + "/query", {**params, "f": "json"})
            features += esri_features_to_geojson(ej.get("features", []))
    return features


def expand_service(url):
    """Vrátí seznam (url_vrstvy, název) – rozbalí FeatureServer/MapServer bez indexu."""
    url = url.rstrip("/")
    if re.search(r"/\d+$", url):
        info = get_json(url)
        if info.get("type") in ("Group Layer",):
            base = url.rsplit("/", 1)[0]
            return [(f"{base}/{s['id']}", s["name"]) for s in info.get("subLayers", [])]
        return [(url, info.get("name", url.rsplit("/", 1)[-1]))]
    info = get_json(url)
    out = []
    for lyr in info.get("layers", []) + info.get("tables", []):
        if lyr.get("subLayerIds"):
            continue  # skupina, sublayery přijdou samy
        out.append((f"{url}/{lyr['id']}", lyr["name"]))
    return out


def walk_layers(layers, acc):
    for lyr in layers:
        if lyr.get("layers"):  # GroupLayer ve webové mapě
            walk_layers(lyr["layers"], acc)
        acc.append(lyr)
    return acc


def save(name, features):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, safe_name(name) + ".geojson")
    base, n = path[:-8], 1
    while os.path.exists(path):
        n += 1
        path = f"{base}_{n}.geojson"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)
    print(f"    -> uloženo {path} ({len(features)} prvků)")


def main():
    print("Načítám konfiguraci aplikace…")
    app = get_json(f"{PORTAL}/content/items/{APP_ID}/data")
    webmaps = [w for w in dict.fromkeys(find_webmap_ids(app)) if w != APP_ID]
    if not webmaps:
        print("Nenašel jsem ID webové mapy. Konfigurace aplikace:")
        print(json.dumps(app, indent=2, ensure_ascii=False)[:3000])
        return

    for wm in webmaps:
        try:
            item = get_json(f"{PORTAL}/content/items/{wm}")
        except Exception as e:
            print(f"Přeskakuji {wm}: {e}")
            continue
        if item.get("type") not in ("Web Map", "Web Scene"):
            continue
        print(f"\nWebová mapa: {item.get('title')} ({wm})")
        data = get_json(f"{PORTAL}/content/items/{wm}/data")
        layers = walk_layers(data.get("operationalLayers", []), [])
        layers += data.get("tables", [])

        for lyr in layers:
            title = lyr.get("title") or lyr.get("id") or "vrstva"
            print(f"  Vrstva: {title}")
            try:
                # 1) data vložená přímo do mapy (featureCollection)
                fc = lyr.get("featureCollection")
                if fc:
                    feats = []
                    for sub in fc.get("layers", []):
                        sr = sub.get("featureSet", {}).get("spatialReference") \
                            or sub.get("layerDefinition", {}).get("extent", {}).get("spatialReference", {})
                        merc = (sr or {}).get("wkid") in (102100, 3857, 102113)
                        feats += esri_features_to_geojson(
                            sub.get("featureSet", {}).get("features", []), merc)
                    save(title, feats)
                    continue
                # 2) vrstva ze služby
                url = lyr.get("url")
                if not url:
                    print("    (bez URL – podkladová/skupinová vrstva, přeskakuji)")
                    continue
                if not re.search(r"/(FeatureServer|MapServer)", url, re.I):
                    print(f"    (typ {lyr.get('layerType')} se nedá stáhnout jako vektor: {url})")
                    continue
                for layer_url, name in expand_service(url):
                    print(f"   {layer_url}")
                    save(f"{title}__{name}" if name != title else title,
                         download_service_layer(layer_url))
            except Exception as e:
                print(f"    CHYBA: {e}")

    print("\nHotovo.")


if __name__ == "__main__":
    main()