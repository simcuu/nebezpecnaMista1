#!/usr/bin/env python3
"""
Z bodů veřejného osvětlení (stažených skriptem stahni_arcgis_geojson.py) udělá
čáry po ulicích Olomouce obarvené podle toho, kolik lamp je v okolí.

Postup:
  1. načte lampy ze složky ./data/ (soubor s "osv" v názvu),
  2. stáhne ulice a chodníky Olomouce z OpenStreetMap (Overpass API),
  3. každou ulici rozseká na krátké kousky (~20 m) a u každého spočítá lampy do 35 m,
  4. sousední kousky se stejnou úrovní osvětlení zase spojí, aby bylo čar méně,
  5. uloží osvetleni_ulic.geojson (vlastnost "uroven": 0 = žádná lampa ... 4 = hodně lamp).

Použití:
    python stahni_arcgis_geojson.py      # jednou, stáhne lampy do ./data/
    python priprav_osvetleni_ulic.py     # vytvoří osvetleni_ulic.geojson
Jen standardní knihovna, nic se nemusí instalovat.
"""
import glob
import json
import math
import os
import time
import urllib.parse
import urllib.request

DATA_DIR = "data"
VYSTUP = "osvetleni_ulic.geojson"
ULICE_CACHE = os.path.join(DATA_DIR, "ulice_osm.json")  # smažte, chcete-li ulice stáhnout znovu
OVERPASS_SERVERY = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

DELKA_KOUSKU = 20   # m – na jak dlouhé kousky se ulice rozsekají
DOSAH_LAMPY = 35    # m – lampy do této vzdálenosti od kousku se počítají

# Typy cest z OpenStreetMap, po kterých se dá chodit (bez dálnic a rychlostních silnic)
TYPY_CEST = (
    "primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|"
    "unclassified|residential|living_street|pedestrian|footway|steps|"
    "cycleway|path|service"
)

# Převod stupňů na metry (pro Olomouc stačí jednoduchá rovinná aproximace)
LAT0 = 49.59
M_NA_STUPEN_LAT = 110_540
M_NA_STUPEN_LON = 111_320 * math.cos(math.radians(LAT0))


def na_metry(lon, lat):
    return lon * M_NA_STUPEN_LON, lat * M_NA_STUPEN_LAT


def nacti_lampy():
    soubory = [f for f in glob.glob(os.path.join(DATA_DIR, "*.geojson")) if "osv" in f.lower()]
    if not soubory:
        raise SystemExit(
            "V ./data/ nejsou lampy – nejdřív spusťte: python stahni_arcgis_geojson.py"
        )
    with open(soubory[0], encoding="utf-8") as f:
        data = json.load(f)
    lampy = [
        na_metry(*ft["geometry"]["coordinates"][:2])
        for ft in data["features"]
        if ft.get("geometry") and ft["geometry"]["type"] == "Point"
    ]
    print(f"Lampy: {len(lampy)} (soubor {soubory[0]})")
    return lampy


def stahni_ulice():
    dotaz = f"""
    [out:json][timeout:180];
    area["name"="Olomouc"]["boundary"="administrative"]["admin_level"="8"]->.mesto;
    way(area.mesto)["highway"~"^({TYPY_CEST})$"]["service"!~"."]["access"!~"^(private|no)$"];
    out geom;
    """
    if os.path.exists(ULICE_CACHE):
        print(f"Ulice beru z dříve staženého souboru {ULICE_CACHE}")
        with open(ULICE_CACHE, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = None
        for pokus in range(3):
            for server in OVERPASS_SERVERY:
                print(f"Stahuji ulice z OpenStreetMap ({server})…")
                pozadavek = urllib.request.Request(
                    server,
                    data=urllib.parse.urlencode({"data": dotaz}).encode(),
                    headers={"User-Agent": "nebezpecna-mista-olomouc/1.0"},
                )
                try:
                    with urllib.request.urlopen(pozadavek, timeout=300) as r:
                        data = json.loads(r.read().decode("utf-8"))
                    break
                except Exception as e:
                    print(f"  nepovedlo se: {e}")
            if data is not None:
                break
            time.sleep(10)
        if data is None:
            raise SystemExit("Ulice se nepodařilo stáhnout, zkuste to za chvíli znovu.")
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ULICE_CACHE, "w", encoding="utf-8") as f:
            json.dump(data, f)

    ulice = [
        [(bod["lon"], bod["lat"]) for bod in prvek["geometry"]]
        for prvek in data["elements"]
        if prvek.get("type") == "way" and len(prvek.get("geometry", [])) >= 2
    ]
    print(f"Ulice/cesty: {len(ulice)}")
    return ulice


def mrizka_lamp(lampy):
    """Lampy rozdělené do čtverců DOSAH_LAMPY × DOSAH_LAMPY, aby bylo hledání rychlé."""
    mrizka = {}
    for x, y in lampy:
        mrizka.setdefault((int(x // DOSAH_LAMPY), int(y // DOSAH_LAMPY)), []).append((x, y))
    return mrizka


def pocet_lamp(mrizka, x, y):
    cx, cy = int(x // DOSAH_LAMPY), int(y // DOSAH_LAMPY)
    limit = DOSAH_LAMPY ** 2
    return sum(
        1
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for lx, ly in mrizka.get((cx + dx, cy + dy), ())
        if (lx - x) ** 2 + (ly - y) ** 2 <= limit
    )


def uroven(pocet):
    """0 = tma (žádná lampa), 1 = 1 lampa, 2 = 2–3, 3 = 4–5, 4 = 6 a víc lamp u sebe."""
    if pocet <= 1:
        return pocet
    if pocet <= 3:
        return 2
    if pocet <= 5:
        return 3
    return 4


def rozsekej(cesta):
    """Rozseká lomenou čáru na kousky dlouhé zhruba DELKA_KOUSKU (v souřadnicích lon/lat).
    Vrací (začátek, konec, je_to_konec_původního_úseku)."""
    kousky = []
    for (lon1, lat1), (lon2, lat2) in zip(cesta, cesta[1:]):
        x1, y1 = na_metry(lon1, lat1)
        x2, y2 = na_metry(lon2, lat2)
        delka = math.hypot(x2 - x1, y2 - y1)
        n = max(1, round(delka / DELKA_KOUSKU))
        for i in range(n):
            t1, t2 = i / n, (i + 1) / n
            kousky.append((
                (lon1 + (lon2 - lon1) * t1, lat1 + (lat2 - lat1) * t1),
                (lon1 + (lon2 - lon1) * t2, lat1 + (lat2 - lat1) * t2),
                i == n - 1,
            ))
    return kousky


def main():
    lampy = nacti_lampy()
    mrizka = mrizka_lamp(lampy)
    ulice = stahni_ulice()

    prvky = []
    statistika = [0] * 5

    for cesta in ulice:
        kousky = rozsekej(cesta)
        urovne = [
            uroven(pocet_lamp(mrizka, *na_metry((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)))
            for a, b, _ in kousky
        ]
        # Vyhlazení: osamocený kousek mezi dvěma stejnými sousedy dostane jejich úroveň
        for i in range(1, len(urovne) - 1):
            if urovne[i - 1] == urovne[i + 1] != urovne[i]:
                urovne[i] = urovne[i - 1]

        aktualni_uroven, body = None, []

        for (a, b, konec_useku), u in zip(kousky, urovne):
            statistika[u] += 1

            if not body:
                body = [a]
            elif u != aktualni_uroven:
                # Změna osvětlení – čára končí tady a začíná nová
                if body[-1] != a:
                    body.append(a)
                prvky.append((aktualni_uroven, body))
                body = [a]

            # Mezilehlé body uvnitř rovného úseku nejsou potřeba (šetří velikost souboru)
            if konec_useku:
                body.append(b)
            aktualni_uroven = u

        if len(body) >= 2:
            prvky.append((aktualni_uroven, body))

    # Jeden prvek (MultiLineString) na každou úroveň – mapa se pak vykreslí mnohem rychleji
    podle_urovne = {}
    for u, body in prvky:
        podle_urovne.setdefault(u, []).append(
            [[round(lon, 5), round(lat, 5)] for lon, lat in body]
        )

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "MultiLineString", "coordinates": cary},
                "properties": {"uroven": u},
            }
            for u, cary in sorted(podle_urovne.items())
        ],
    }
    with open(VYSTUP, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))

    celkem = sum(statistika) or 1
    print("Podíl kousků podle počtu lamp v okolí:")
    for u, n in enumerate(statistika):
        print(f"  úroveň {u}: {n / celkem:6.1%}")
    print(f"Uloženo {VYSTUP} ({len(prvky)} čar)")


if __name__ == "__main__":
    main()
