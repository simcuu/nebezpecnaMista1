"""Vyřízne z dat Policie ČR (kriminalita.policie.cz) jen události v Olomouci.

Použití: uložte stažené měsíční ZIPy (např. 202611.zip) do této složky a spusťte
    python priprav_kriminalitu.py
Vznikne malý soubor kriminalita_olomouc.csv, se kterým pracuje aplikace.

Policie posouvá polohu každé události do středu Voronoiova polygonu, do kterého
spadá (viz readme.txt v ZIPu). Olomoucké události proto poznáme podle toho,
že jejich souřadnice odpovídají středu (def_bod_x, def_bod_y) některé oblasti
ze souboru voronoi_olomouc.geojson.
"""

import glob
import json
import re
import zipfile

import pandas as pd

VORONOI = "voronoi_olomouc.geojson"
VYSTUP = "kriminalita_olomouc.csv"

# Stavy 3 = „skutek se nestal“, 4 = „skutek není trestným činem“ – vynecháme
VYNECHANE_STAVY = {3, 4}


def stredy_oblasti():
    with open(VORONOI, encoding="utf-8") as f:
        geojson = json.load(f)
    return {
        (
            round(feature["properties"]["def_bod_x"], 6),
            round(feature["properties"]["def_bod_y"], 6),
        ): feature["properties"]["id"]
        for feature in geojson["features"]
    }


def nacti_zip(cesta):
    with zipfile.ZipFile(cesta) as archiv:
        jmeno_csv = next(
            jmeno for jmeno in archiv.namelist()
            if re.fullmatch(r"\d{6}\.csv", jmeno.split("/")[-1])
        )
        return pd.read_csv(archiv.open(jmeno_csv))


def main():
    zipy = sorted(
        cesta for cesta in glob.glob("*.zip")
        if re.fullmatch(r"\d{6}\.zip", cesta)
    )
    if not zipy:
        print("Nenalezen žádný ZIP ve tvaru RRRRMM.zip.")
        return

    stredy = stredy_oblasti()
    casti = []

    for cesta in zipy:
        data = nacti_zip(cesta)
        data["oblast"] = [
            stredy.get((round(x, 6), round(y, 6)))
            for x, y in zip(data["x"], data["y"])
        ]
        olomouc = data[
            data["oblast"].notna()
            & ~data["state"].isin(VYNECHANE_STAVY)
        ].copy()
        olomouc["oblast"] = olomouc["oblast"].astype(int)
        print(f"{cesta}: {olomouc['id'].nunique()} událostí v Olomouci")
        casti.append(olomouc)

    vysledek = (
        pd.concat(casti)
        .drop_duplicates(["id", "types"])
        [["id", "oblast", "date", "state", "relevance", "types"]]
        .sort_values(["date", "id", "types"])
    )
    vysledek.to_csv(VYSTUP, index=False)
    print(
        f"Uloženo {vysledek['id'].nunique()} událostí "
        f"({len(vysledek)} řádků) do {VYSTUP}"
    )


if __name__ == "__main__":
    main()
