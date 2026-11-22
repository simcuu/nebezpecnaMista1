"""
Srovnání tras: nejkratší vs. nejbezpečnější cesta z A do B.

Spuštění:
    venv/bin/streamlit run srovnani_tras.py

Jak to funguje:
1. Z OpenRouteService se stáhne nejkratší pěší trasa a k ní pár alternativ.
2. Zvlášť se stáhne trasa, která se vyhýbá okolí nebezpečných míst (avoid_polygons).
   Hledá se s několika odstupy, aby vznikly i kompromisní varianty.
3. Každá kandidátní trasa dostane riziko = počet nebezpečných míst v okolí
   + (za tmy) 1 bod za každých 100 m po neosvětlených ulicích.
4. Nejbezpečnější = nejnižší riziko mezi trasami, které nejsou delší
   než zvolená maximální zajížďka (při shodě vyhrává kratší).
"""
import json
import math
from pathlib import Path

import folium
import openrouteservice
import streamlit as st
from openrouteservice import convert, exceptions
from streamlit_folium import st_folium

from navigace_test4 import ORS_KLIC, hledej_misto, nacti_mista_z_geojsonu

SLOZKA = Path(__file__).parent
COS_OLOMOUC = math.cos(math.radians(49.59))
M_NA_STUPEN_LAT = 111_000
M_NA_STUPEN_LON = 111_000 * COS_OLOMOUC

BARVA_NEJKRATSI = "#1f5bff"
BARVA_BEZPECNA = "#1fa463"
BARVY_OSVETLENI = {0: "#e3261b", 1: "#f47a20", 2: "#f9b233", 3: "#ffd84a", 4: "#fff200"}


# --- Geometrie (v metrech, lokální rovinná projekce kolem Olomouce) -----------------

def na_metry(lon, lat):
    return lon * M_NA_STUPEN_LON, lat * M_NA_STUPEN_LAT


def vzdalenost_bodu_k_usecce(p, a, b):
    """Vzdálenost bodu p od úsečky a–b (vše v metrech)."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    delka2 = dx * dx + dy * dy
    if delka2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / delka2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def vzdalenost_k_trase(bod_m, trasa_m):
    return min(
        vzdalenost_bodu_k_usecce(bod_m, a, b) for a, b in zip(trasa_m, trasa_m[1:])
    )


def vzorky_trasy(trasa_m, krok=10):
    """Body na trase po ~`krok` metrech, každý s délkou úseku, který zastupuje."""
    vzorky = []
    for a, b in zip(trasa_m, trasa_m[1:]):
        delka = math.hypot(b[0] - a[0], b[1] - a[1])
        pocet = max(1, int(delka // krok))
        for i in range(pocet):
            t = (i + 0.5) / pocet
            vzorky.append(((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), delka / pocet))
    return vzorky


# --- Data ----------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def nacti_mista():
    """Nebezpečná místa z pocit-nebezpeci-olomouc-2.geojson (stejná jako v navigaci)."""
    mista = []
    for m in nacti_mista_z_geojsonu():
        duvod = (m.get("desc_detail_duvod") or "").strip()
        if not duvod:
            continue
        mista.append({
            "lat": m["latitude"],
            "lon": m["longitude"],
            "typ": m.get("typ_nazev") or "",
            "za_tmy": "tma" in (m.get("typ_nazev") or "").lower()
                      or "noc" in (m.get("typ_nazev") or "").lower(),
            "duvod": duvod,
        })
    return mista


@st.cache_resource(show_spinner="Připravuji data o osvětlení ulic…")
def index_osvetleni(bunka=50):
    """Mřížka úseků osvětlených ulic: {(x, y) buňky: [(a, b, úroveň), ...]}.
    Bere zjednodušený static/osvetleni_ulic.json, jinak původní osvetleni_ulic.geojson."""
    for soubor in (SLOZKA / "static" / "osvetleni_ulic.json", SLOZKA / "osvetleni_ulic.geojson"):
        if soubor.exists():
            data = json.loads(soubor.read_text(encoding="utf-8"))
            break
    else:
        return None

    mrizka = {}
    for prvek in data["features"]:
        uroven = prvek["properties"]["uroven"]
        geometrie = prvek["geometry"]
        cary = geometrie["coordinates"] if geometrie["type"] == "MultiLineString" else [geometrie["coordinates"]]
        for cara in cary:
            body = [na_metry(lon, lat) for lon, lat in cara]
            for a, b in zip(body, body[1:]):
                x0, x1 = sorted((int(a[0] // bunka), int(b[0] // bunka)))
                y0, y1 = sorted((int(a[1] // bunka), int(b[1] // bunka)))
                for x in range(x0, x1 + 1):
                    for y in range(y0, y1 + 1):
                        mrizka.setdefault((x, y), []).append((a, b, uroven))
    return {"bunka": bunka, "mrizka": mrizka}


def uroven_osvetleni(bod_m, index, max_vzdalenost=20):
    """Úroveň osvětlení nejbližší ulice do `max_vzdalenost` m, jinak None (bez dat)."""
    bunka, mrizka = index["bunka"], index["mrizka"]
    cx, cy = int(bod_m[0] // bunka), int(bod_m[1] // bunka)
    nejblizsi, uroven = max_vzdalenost, None
    for x in (cx - 1, cx, cx + 1):
        for y in (cy - 1, cy, cy + 1):
            for a, b, u in mrizka.get((x, y), ()):
                d = vzdalenost_bodu_k_usecce(bod_m, a, b)
                if d <= nejblizsi:
                    nejblizsi, uroven = d, u
    return uroven


# --- Trasy z OpenRouteService --------------------------------------------------------

def _klient():
    return openrouteservice.Client(key=ORS_KLIC)


def _dekoduj(odpoved):
    trasy = []
    for r in odpoved.get("routes", []):
        body = convert.decode_polyline(r["geometry"])["coordinates"]  # [lon, lat]
        trasy.append({
            "body": [tuple(b[:2]) for b in body],
            "delka": r["summary"].get("distance", 0.0),
            "cas": r["summary"].get("duration", 0.0),
        })
    return trasy


@st.cache_data(ttl=3600, show_spinner=False)
def trasy_bez_vyhybani(start, cil):
    """Nejkratší pěší trasa + až 2 alternativy."""
    odpoved = _klient().directions(
        [list(start), list(cil)],
        profile="foot-walking",
        preference="shortest",
        alternative_routes={"target_count": 3, "weight_factor": 1.6, "share_factor": 0.6},
    )
    return _dekoduj(odpoved)


def avoid_polygony(mista, start, cil, odstup, vyjimka):
    """Čtverce o poloviční straně `odstup` kolem míst; místa blíž než `vyjimka` ke startu
    nebo cíli se vynechají (ORS neumí začít ani skončit uvnitř zakázané zóny)."""
    konce = [na_metry(*start), na_metry(*cil)]
    polygony = []
    for m in mista:
        bod = na_metry(m["lon"], m["lat"])
        if any(math.hypot(bod[0] - k[0], bod[1] - k[1]) < vyjimka for k in konce):
            continue
        dlat = odstup / M_NA_STUPEN_LAT
        dlon = odstup / M_NA_STUPEN_LON
        lon, lat = m["lon"], m["lat"]
        polygony.append([[
            [lon - dlon, lat - dlat], [lon + dlon, lat - dlat],
            [lon + dlon, lat + dlat], [lon - dlon, lat + dlat],
            [lon - dlon, lat - dlat],
        ]])
    return {"type": "MultiPolygon", "coordinates": polygony}


@st.cache_data(ttl=3600, show_spinner=False)
def trasy_s_vyhybanim(start, cil, mista_klic, odstup):
    """Trasa vyhýbající se okolí nebezpečných míst. Když ORS trasu nenajde,
    zkusí to znovu s větší výjimkou kolem startu a cíle. Vrací (trasy, poznámka)."""
    mista = [{"lon": lon, "lat": lat} for lon, lat in mista_klic]
    for vyjimka in (odstup + 30, 500):
        polygony = avoid_polygony(mista, start, cil, odstup, vyjimka)
        if not polygony["coordinates"]:
            return [], None
        try:
            odpoved = _klient().directions(
                [list(start), list(cil)],
                profile="foot-walking",
                options={"avoid_polygons": polygony},
                alternative_routes={"target_count": 2, "weight_factor": 1.8, "share_factor": 0.6},
            )
            poznamka = None if vyjimka == odstup + 30 else (
                "Místa do 500 m od startu a cíle se při hledání bezpečné trasy nebrala v úvahu "
                "(jinak by trasa nešla najít)."
            )
            return _dekoduj(odpoved), poznamka
        except exceptions.ApiError:
            continue
    return [], "Trasu, která se vyhne všem místům, se nepodařilo najít."


# --- Hodnocení trasy -----------------------------------------------------------------

def ohodnot(trasa, mista, odstup, index, za_tmy):
    trasa_m = [na_metry(lon, lat) for lon, lat in trasa["body"]]
    blizka = [
        i for i, m in enumerate(mista)
        if vzdalenost_k_trase(na_metry(m["lon"], m["lat"]), trasa_m) <= odstup
    ]
    vzorky = vzorky_trasy(trasa_m)

    # Osvětlení: podíl délky trasy podle úrovně (None = ulice bez dat o lampách)
    delky = {}
    useky = []
    if index is not None:
        for bod, delka in vzorky:
            u = uroven_osvetleni(bod, index)
            delky[u] = delky.get(u, 0.0) + delka
            useky.append(u)
    celkem = sum(delky.values()) or 1.0
    neosvetleno = (delky.get(0, 0.0) + delky.get(1, 0.0)) / celkem
    bez_dat = delky.get(None, 0.0) / celkem
    neosvetleno_m = delky.get(0, 0.0) + delky.get(1, 0.0)

    # Riziko: 1 bod za každé místo u trasy
    #         + za tmy 1 bod za každých 100 m bez osvětlení
    riziko_mista = float(len(blizka))
    riziko_svetlo = neosvetleno_m / 100 if za_tmy and index is not None else 0.0

    return {
        **trasa,
        "blizka": blizka,
        "neosvetleno": neosvetleno,
        "bez_dat": bez_dat,
        "neosvetleno_m": neosvetleno_m,
        "useky_svetla": useky,
        "riziko_mista": riziko_mista,
        "riziko_svetlo": riziko_svetlo,
        "riziko": riziko_mista + riziko_svetlo,
    }


# --- Mapa ----------------------------------------------------------------------------

def mapa_trasy(trasa, barva, mista, zvyraznena, vyhnuta, start, cil, podle_svetla, tmava=False):
    body = [(lat, lon) for lon, lat in trasa["body"]]
    mapa = folium.Map(tiles="CartoDB dark_matter" if tmava else "CartoDB positron", control_scale=True)
    mapa.fit_bounds([
        [min(b[0] for b in body), min(b[1] for b in body)],
        [max(b[0] for b in body), max(b[1] for b in body)],
    ], padding=(30, 30))

    # Všechna nebezpečná místa – malé šedé tečky
    for i, m in enumerate(mista):
        if i in zvyraznena or i in vyhnuta:
            continue
        folium.CircleMarker(
            [m["lat"], m["lon"]], radius=3, color="#888", weight=1,
            fill=True, fill_opacity=0.5, tooltip=m["duvod"],
        ).add_to(mapa)

    folium.PolyLine(body, color="white", weight=9, opacity=0.9).add_to(mapa)
    if podle_svetla and trasa["useky_svetla"]:
        # Trasa obarvená podle osvětlení (vzorky po ~10 m)
        trasa_m = [na_metry(lon, lat) for lon, lat in trasa["body"]]
        vzorky = vzorky_trasy(trasa_m)
        souradnice = [(y / M_NA_STUPEN_LAT, x / M_NA_STUPEN_LON) for (x, y), _ in vzorky]
        for (a, b), u in zip(zip(souradnice, souradnice[1:]), trasa["useky_svetla"]):
            folium.PolyLine([a, b], color=BARVY_OSVETLENI.get(u, "#9aa0a6"), weight=6, opacity=1).add_to(mapa)
    else:
        folium.PolyLine(body, color=barva, weight=5, opacity=1).add_to(mapa)

    # Místa u trasy – červená, místa, kterým se trasa vyhnula – zelená
    for i in zvyraznena:
        m = mista[i]
        folium.CircleMarker(
            [m["lat"], m["lon"]], radius=7, color="#fff", weight=2,
            fill=True, fill_color="#d62728", fill_opacity=0.95,
            tooltip=f"U trasy: {m['duvod']}",
        ).add_to(mapa)
    for i in vyhnuta:
        m = mista[i]
        folium.CircleMarker(
            [m["lat"], m["lon"]], radius=7, color="#fff", weight=2,
            fill=True, fill_color="#1fa463", fill_opacity=0.95,
            tooltip=f"Vyhnuto: {m['duvod']}",
        ).add_to(mapa)

    folium.Marker([start[1], start[0]], tooltip="Start (A)",
                  icon=folium.Icon(color="blue", icon="play")).add_to(mapa)
    folium.Marker([cil[1], cil[0]], tooltip="Cíl (B)",
                  icon=folium.Icon(color="red", icon="flag")).add_to(mapa)
    return mapa


# --- Srovnání (dá se použít i v jiné stránce) -------------------------------

def zobraz_srovnani(start, cil, mista, za_tmy, odstup=50, max_zajizdka=60,
                    podle_svetla=False, klic="srovnani", tmava=False, strucne=False):
    """Vykreslí srovnání nejkratší a nejbezpečnější trasy do aktuálního místa stránky.

    start, cil: (lon, lat); mista: seznam {"lat", "lon", "typ", "duvod"}.
    Používá ho tato stránka i hlavní aplikace (nejfinalnejsi_verze.py).
    `strucne=True` ukáže jen krátké shrnutí (bez map, tabulek a seznamů)."""
    with st.spinner("Hledám a porovnávám trasy…"):
        try:
            kandidati_kratke = trasy_bez_vyhybani(start, cil)
        except Exception as chyba:
            st.error(f"Trasu se nepodařilo najít: {chyba}")
            return
        mista_klic = tuple((m["lon"], m["lat"]) for m in mista)
        # Víc odstupů = víc variant: od „obejít všechno široce“ po „jen se neotřít“
        kandidati_bezpecne, poznamka = [], None
        for odstup_vyhybani in sorted({odstup, max(15, round(odstup * 0.6)), 15}, reverse=True):
            try:
                trasy, poznamka_zde = trasy_s_vyhybanim(start, cil, mista_klic, odstup_vyhybani)
            except Exception:
                trasy, poznamka_zde = [], "Některou z bezpečných tras se nepodařilo stáhnout."
            kandidati_bezpecne += trasy
            poznamka = poznamka or poznamka_zde

        index = index_osvetleni()
        hodnocene = [
            ohodnot(t, mista, odstup, index, za_tmy)
            for t in kandidati_kratke + kandidati_bezpecne
        ]

    nejkratsi = min(hodnocene, key=lambda t: t["delka"])
    povolene = [t for t in hodnocene if t["delka"] <= nejkratsi["delka"] * (1 + max_zajizdka / 100)]
    bezpecna = min(povolene, key=lambda t: (round(t["riziko"], 2), t["delka"]))

    stejne = bezpecna is nejkratsi or bezpecna["body"] == nejkratsi["body"]

    if strucne:
        def radek(nazev, t):
            pocet = len(t["blizka"])
            mist = "místo" if pocet == 1 else "místa" if 2 <= pocet <= 4 else "míst"
            km = f"{t['delka'] / 1000:.1f}".replace(".", ",")
            return (f"**{nazev}:** {km} km · {t['cas'] / 60:.0f} min · "
                    f"{pocet} nebezpečn{'é' if pocet == 1 else 'á' if 2 <= pocet <= 4 else 'ých'} {mist}")
        if stejne:
            st.markdown(radek("Nejkratší = nejbezpečnější", nejkratsi))
        else:
            st.markdown(radek("Nejkratší", nejkratsi) + "  \n" + radek("Nejbezpečnější", bezpecna))
        return

    if poznamka:
        st.caption(f"ℹ️ {poznamka}")

    if stejne:
        st.success("Nejkratší trasa je zároveň nejbezpečnější – nemusíte nic obcházet.")

    # --- Souhrn rozdílů ------------------------------------------------------------------
    vyhnuta = sorted(set(nejkratsi["blizka"]) - set(bezpecna["blizka"]))
    nova = sorted(set(bezpecna["blizka"]) - set(nejkratsi["blizka"]))
    rozdil_cas = (bezpecna["cas"] - nejkratsi["cas"]) / 60
    rozdil_delka = bezpecna["delka"] - nejkratsi["delka"]
    rozdil_pct = 100 * rozdil_delka / max(nejkratsi["delka"], 1)
    pred, po = len(nejkratsi["blizka"]), len(bezpecna["blizka"])
    bezpecnejsi_o = (
        100 * (nejkratsi["riziko"] - bezpecna["riziko"]) / nejkratsi["riziko"]
        if nejkratsi["riziko"] else 0.0
    )

    st.markdown("##### Rozdíl")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Čas navíc", f"{rozdil_cas:+.0f} min", f"{rozdil_pct:+.0f} % délky", delta_color="inverse")
    k2.metric(
        "Bezpečnější o",
        f"{bezpecnejsi_o:.0f} %",
        f"riziko {nejkratsi['riziko']:.1f} → {bezpecna['riziko']:.1f}",
        delta_color="off",
    )
    k3.metric(
        "Vyhne se místům",
        f"{len(vyhnuta)} z {pred}",
        f"{len(nova)} nových u trasy" if nova else "žádné nové",
        delta_color="inverse" if nova else "off",
    )
    if za_tmy and index is not None:
        k4.metric(
            "Neosvětlené úseky",
            f"{bezpecna['neosvetleno']:.0%}",
            f"{100 * (bezpecna['neosvetleno'] - nejkratsi['neosvetleno']):+.0f} b. proti nejkratší",
            delta_color="inverse",
        )
    else:
        k4.metric("Míst u bezpečné trasy", f"{po}", f"{po - pred:+d} proti nejkratší", delta_color="inverse")
    # --- Dvě mapy vedle sebe -------------------------------------------------------------
    levy, pravy = st.columns(2)
    for sloupec, nazev, trasa, barva, zvyraznena, vyhnuta_zde in (
        (levy, "Nejkratší cesta", nejkratsi, BARVA_NEJKRATSI, nejkratsi["blizka"], []),
        (pravy, "Nejbezpečnější cesta", bezpecna, BARVA_BEZPECNA, bezpecna["blizka"], vyhnuta),
    ):
        with sloupec:
            st.markdown(f"##### {nazev}")
            a, b, c = st.columns(3)
            a.metric("Délka", f"{trasa['delka'] / 1000:.2f} km")
            b.metric("Chůze", f"{trasa['cas'] / 60:.0f} min")
            c.metric("Riziko", f"{trasa['riziko']:.1f}")
            st_folium(
                mapa_trasy(trasa, barva, mista, zvyraznena, vyhnuta_zde, start, cil, podle_svetla, tmava),
                height=460, use_container_width=True, returned_objects=[], key=f"{klic}_mapa_{nazev}",
            )
            popis = f"Nebezpečných míst do {odstup} m: **{len(trasa['blizka'])}**"
            if index is not None:
                popis += (
                    f" · neosvětleno: **{trasa['neosvetleno']:.0%}**"
                    f" · bez dat o lampách: {trasa['bez_dat']:.0%}"
                )
            st.markdown(popis)
            st.caption(
                f"Riziko {trasa['riziko']:.1f} = místa {trasa['riziko_mista']:.0f}"
                f" + osvětlení {trasa['riziko_svetlo']:.1f}"
            )

    # --- Seznam míst ---------------------------------------------------------------------
    if vyhnuta:
        with st.expander(f"Místa, kterým se bezpečná trasa vyhne ({len(vyhnuta)})", expanded=True):
            for i in vyhnuta:
                st.markdown(f"- **{mista[i]['typ']}** – {mista[i]['duvod']}")
    if nova:
        with st.expander(f"Místa, která jsou u bezpečné trasy navíc ({len(nova)})"):
            for i in nova:
                st.markdown(f"- **{mista[i]['typ']}** – {mista[i]['duvod']}")

    # --- Všechny porovnávané varianty ---------------------------------------------------
    with st.expander(f"Všechny porovnávané varianty ({len(hodnocene)})"):
        st.dataframe(
            [
                {
                    "": ("🔵 nejkratší" if t is nejkratsi else "🟢 nejbezpečnější" if t is bezpecna else ""),
                    "Délka (km)": round(t["delka"] / 1000, 2),
                    "Chůze (min)": round(t["cas"] / 60),
                    "Zajížďka (%)": round(100 * (t["delka"] / nejkratsi["delka"] - 1)),
                    "Míst u trasy": len(t["blizka"]),
                    "Neosvětleno (m)": round(t["neosvetleno_m"]),
                    "Riziko": round(t["riziko"], 1),
                    "V limitu zajížďky": "ano" if t in povolene else "ne",
                }
                for t in sorted(hodnocene, key=lambda t: t["delka"])
            ],
            width="stretch",
            hide_index=True,
        )

    with st.expander("Jak se počítá bezpečnost"):
        st.markdown(
            f"""
    - **Riziko trasy** = počet nebezpečných míst blíž než {odstup} m od trasy
      + za tmy **1 bod za každých 100 m** po neosvětlených ulicích (úroveň osvětlení 0–1 z 0–4).
      Úseky bez dat o lampách se nepočítají jako neosvětlené.
    - **Bezpečnější o X %** = o kolik procent má bezpečná trasa nižší riziko než nejkratší.
    - Porovnává se nejkratší trasa, její alternativy a trasy, které se místům vyhýbají
      s různým odstupem. Vyhrává ta s nejnižším rizikem, která není delší o víc než
      {max_zajizdka} % (při shodě kratší).
    - Místa jsou z dotazníku pocitu nebezpečí (`pocit-nebezpeci-olomouc-2.geojson`),
      osvětlení z dat o lampách.
      Jde o pocity a odhad, ne o záruku bezpečí.
    """
        )


# --- Samostatná stránka ------------------------------------------------------

def stranka():
    """Samostatná stránka: venv/bin/streamlit run srovnani_tras.py"""
    st.set_page_config(page_title="Srovnání tras", layout="wide")
    st.title("Nejkratší vs. nejbezpečnější cesta")
    st.caption(
        "Porovnání dvou pěších tras z A do B: nejkratší podle mapy a ta, která se "
        "nejvíc vyhne místům, kde se lidé necítí bezpečně."
    )

    with st.sidebar:
        st.header("Nastavení")
        podminky = st.radio("Kdy jdete?", ["Za tmy", "Za světla"], index=0)
        odstup = st.slider(
            "Odstup od nebezpečných míst (m)", 10, 150, 50, step=10,
            help="Místo se počítá jako ‚u trasy‘, když je od ní blíž než tato vzdálenost. "
                 "Stejný odstup se použije při hledání bezpečné trasy.",
        )
        max_zajizdka = st.slider(
            "Maximální zajížďka (%)", 10, 150, 60, step=10,
            help="Bezpečná trasa nesmí být delší než nejkratší o víc než toto procento.",
        )
        podle_svetla = st.checkbox(
            "Obarvit trasy podle osvětlení ulic", value=podminky == "Za tmy",
            help="Červená = bez lamp, žlutá = hodně lamp, šedá = bez dat.",
        )

    vsechna_mista = nacti_mista()
    za_tmy = podminky == "Za tmy"
    mista = [m for m in vsechna_mista if m["za_tmy"] == za_tmy]

    def vyber_mista(popisek, vychozi, klic):
        """Textové pole + výběr z nalezených míst. Vrací (lon, lat) a popis, nebo (None, None)."""
        dotaz = st.text_input(popisek, value=vychozi, key=f"dotaz_{klic}")
        if not dotaz.strip():
            return None, None
        try:
            nalezena = hledej_misto(dotaz.strip())
        except Exception:
            st.error("Vyhledávání míst teď nefunguje, zkuste to za chvíli.")
            return None, None
        if not nalezena:
            st.warning(f"„{dotaz}“ se nepodařilo najít.")
            return None, None
        volba = st.selectbox(
            "Nalezeno", range(len(nalezena)), format_func=lambda i: nalezena[i]["popis"],
            key=f"volba_{klic}", label_visibility="collapsed",
        )
        return tuple(nalezena[volba]["souradnice"]), nalezena[volba]["popis"]

    sloupec_a, sloupec_b = st.columns(2)
    with sloupec_a:
        start, popis_start = vyber_mista("Odkud (A)", "Hlavní nádraží, Olomouc", "a")
    with sloupec_b:
        cil, popis_cil = vyber_mista("Kam (B)", "Horní náměstí, Olomouc", "b")

    if start is None or cil is None:
        st.info("Zadejte start a cíl.")
        return

    zobraz_srovnani(start, cil, mista, za_tmy, odstup, max_zajizdka, podle_svetla)


if __name__ == "__main__":
    stranka()
