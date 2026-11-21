#!/usr/bin/env python3
"""
Ke každé budově UP z budovy_upol.json najde v OpenStreetMap její obrys (tvar budovy)
a uloží budovy_upol_tvary.geojson, který používá sidemapa.py.

Obrys = budova z OSM, ve které leží bod budovy; když bod neleží v žádné,
vezme se nejbližší budova do 40 m. Když se nenajde nic, budova se na mapě ukáže jako kruh.

Použití:
    python priprav_budovy_upol.py
Jen standardní knihovna, nic se nemusí instalovat.
"""
import json
import math
import time
import urllib.parse
import urllib.request

VSTUP = "budovy_upol.json"
VYSTUP = "budovy_upol_tvary.geojson"
OKOLI = 40  # m – jak daleko od bodu se budovy hledají
OVERPASS_SERVERY = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

M_NA_STUPEN_LAT = 110_540
M_NA_STUPEN_LON = 111_320 * math.cos(math.radians(49.59))


def stahni(dotaz):
    for pokus in range(3):
        for server in OVERPASS_SERVERY:
            print(f"Stahuji obrysy budov z OpenStreetMap ({server})…")
            pozadavek = urllib.request.Request(
                server,
                data=urllib.parse.urlencode({"data": dotaz}).encode(),
                headers={"User-Agent": "nebezpecna-mista-olomouc/1.0"},
            )
            try:
                with urllib.request.urlopen(pozadavek, timeout=180) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as e:
                print(f"  nepovedlo se: {e}")
        time.sleep(10)
    raise SystemExit("Obrysy budov se nepodařilo stáhnout, zkuste to za chvíli znovu.")


def bod_v_polygonu(lon, lat, obrys):
    """Ray casting – leží bod uvnitř uzavřeného obrysu?"""
    uvnitr = False
    for (x1, y1), (x2, y2) in zip(obrys, obrys[1:] + obrys[:1]):
        if (y1 > lat) != (y2 > lat):
            if lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                uvnitr = not uvnitr
    return uvnitr


def vzdalenost_m(lon1, lat1, lon2, lat2):
    return math.hypot((lon2 - lon1) * M_NA_STUPEN_LON, (lat2 - lat1) * M_NA_STUPEN_LAT)


def vzdalenost_k_obrysu(lon, lat, obrys):
    """Nejmenší vzdálenost bodu k vrcholům obrysu (pro budovy stačí)."""
    return min(vzdalenost_m(lon, lat, x, y) for x, y in obrys)


def plocha(obrys):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(obrys, obrys[1:] + obrys[:1]))) / 2


def main():
    with open(VSTUP, encoding="utf-8") as f:
        budovy = [b for b in json.load(f) if b["lat"] is not None]

    dotaz = "[out:json][timeout:120];(" + "".join(
        f'way["building"](around:{OKOLI},{b["lat"]},{b["lon"]});'
        f'relation["building"](around:{OKOLI},{b["lat"]},{b["lon"]});'
        for b in budovy
    ) + ");out geom;"
    data = stahni(dotaz)

    # Vnější obrysy všech nalezených budov jako seznam [(lon, lat), ...]
    obrysy = []
    for prvek in data["elements"]:
        if prvek["type"] == "way" and len(prvek.get("geometry", [])) >= 4:
            obrysy.append([(b["lon"], b["lat"]) for b in prvek["geometry"]])
        elif prvek["type"] == "relation":
            for clen in prvek.get("members", []):
                if clen.get("role") == "outer" and len(clen.get("geometry", [])) >= 4:
                    obrysy.append([(b["lon"], b["lat"]) for b in clen["geometry"]])
    print(f"Nalezeno obrysů v okolí: {len(obrysy)}")

    prvky, bez_tvaru = [], []
    for b in budovy:
        uvnitr = [o for o in obrysy if bod_v_polygonu(b["lon"], b["lat"], o)]
        if uvnitr:
            # Když je bod ve více obrysech (budova v areálu), vezme se ten nejmenší
            obrys = min(uvnitr, key=plocha)
        else:
            blizke = [o for o in obrysy if vzdalenost_k_obrysu(b["lon"], b["lat"], o) <= OKOLI]
            obrys = min(blizke, key=lambda o: vzdalenost_k_obrysu(b["lon"], b["lat"], o)) if blizke else None

        if obrys is None:
            bez_tvaru.append(b["id"])
            continue

        souradnice = [[round(x, 6), round(y, 6)] for x, y in obrys]
        if souradnice[0] != souradnice[-1]:
            souradnice.append(souradnice[0])
        prvky.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [souradnice]},
            "properties": {"id": b["id"]},
        })

    with open(VYSTUP, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": prvky}, f, ensure_ascii=False)

    print(f"Uloženo {VYSTUP}: {len(prvky)} budov s tvarem")
    if bez_tvaru:
        print(f"Bez tvaru (na mapě budou jako kruh): {', '.join(bez_tvaru)}")


if __name__ == "__main__":
    main()
