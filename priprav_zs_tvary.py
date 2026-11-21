#!/usr/bin/env python3
"""
Ke každé základní škole ze zs.geojson najde v OpenStreetMap obrys budovy
a uloží zs_tvary.geojson (klíč = OBJECTID školy). Postup je stejný jako
v priprav_budovy_upol.py: budova, ve které bod leží, jinak nejbližší do 40 m.

Použití:
    python priprav_zs_tvary.py                          # základní školy
    python priprav_zs_tvary.py ss.geojson ss_tvary.geojson  # střední školy
"""
import json
import subprocess
import sys

from priprav_budovy_upol import (
    OKOLI,
    OVERPASS_SERVERY,
    bod_v_polygonu,
    plocha,
    stahni,
    vzdalenost_k_obrysu,
)

VSTUP = "zs.geojson"
VYSTUP = "zs_tvary.geojson"


def stahni_curl(dotaz):
    """Stáhne přes curl (Python na macOS má starou LibreSSL a s Overpass se nedomluví);
    když curl chybí nebo selže, zkusí to přes Python."""
    for server in OVERPASS_SERVERY:
        print(f"Stahuji obrysy budov z OpenStreetMap ({server})…")
        try:
            vystup = subprocess.run(
                ["curl", "-sS", "--fail", "--max-time", "300",
                 "-A", "nebezpecna-mista-olomouc/1.0",
                 "--data-urlencode", f"data={dotaz}", server],
                capture_output=True, check=True,
            ).stdout
            return json.loads(vystup.decode("utf-8"))
        except (OSError, subprocess.CalledProcessError, ValueError) as e:
            print(f"  nepovedlo se: {e}")
    return stahni(dotaz)


def main():
    vstup, vystup = (sys.argv[1], sys.argv[2]) if len(sys.argv) >= 3 else (VSTUP, VYSTUP)
    with open(vstup, encoding="utf-8") as f:
        skoly = [
            {
                "id": p["properties"]["OBJECTID"],
                "lon": p["geometry"]["coordinates"][0],
                "lat": p["geometry"]["coordinates"][1],
            }
            for p in json.load(f)["features"]
        ]

    # Jeden obdélník kolem všech škol (+ ~500 m) – rychlejší než desítky dotazů "around"
    jih = min(s["lat"] for s in skoly) - 0.005
    sever = max(s["lat"] for s in skoly) + 0.005
    zapad = min(s["lon"] for s in skoly) - 0.007
    vychod = max(s["lon"] for s in skoly) + 0.007
    ohraniceni = f"{jih},{zapad},{sever},{vychod}"
    dotaz = (
        f'[out:json][timeout:180];(way["building"]({ohraniceni});'
        f'relation["building"]({ohraniceni}););out geom;'
    )
    data = stahni_curl(dotaz)

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
    for s in skoly:
        uvnitr = [o for o in obrysy if bod_v_polygonu(s["lon"], s["lat"], o)]
        if uvnitr:
            obrys = min(uvnitr, key=plocha)
        else:
            blizke = [o for o in obrysy if vzdalenost_k_obrysu(s["lon"], s["lat"], o) <= OKOLI]
            obrys = min(blizke, key=lambda o: vzdalenost_k_obrysu(s["lon"], s["lat"], o)) if blizke else None

        if obrys is None:
            bez_tvaru.append(str(s["id"]))
            continue

        souradnice = [[round(x, 6), round(y, 6)] for x, y in obrys]
        if souradnice[0] != souradnice[-1]:
            souradnice.append(souradnice[0])
        prvky.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [souradnice]},
            "properties": {"id": s["id"]},
        })

    with open(vystup, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": prvky}, f, ensure_ascii=False)

    print(f"Uloženo {vystup}: {len(prvky)} škol s tvarem")
    if bez_tvaru:
        print(f"Bez tvaru (na mapě budou jako kruh), OBJECTID: {', '.join(bez_tvaru)}")


if __name__ == "__main__":
    main()
