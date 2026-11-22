import json
import math
import re
import time
import unicodedata
import folium
import openrouteservice
import requests
import streamlit as st
import streamlit.components.v1 as components

from pathlib import Path
from openrouteservice import convert, exceptions
from folium.plugins import FastMarkerCluster
from streamlit_folium import st_folium

ORS_KLIC = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjYzZDI0NjZlZmUwZDQzMmU4YzIyMjgwMmY5YjRjZWEzIiwiaCI6Im11cm11cjY0In0="


def najdi_trasu(client, start, end, avoid_polygons):
    """Najde pěší trasu, která se vyhne zónám v `avoid_polygons`.

    `avoid_polygons` může být i seznam sad zón od nejpřísnější: když s jednou sadou
    trasa neexistuje (např. všechny cesty z místa vedou přes zónu), zkusí se další.
    Teprve když nevyjde žádná, vrátí se trasa bez vyhýbání (s upozorněním)."""
    sady = avoid_polygons if isinstance(avoid_polygons, list) else [avoid_polygons]

    for zony in sady:
        if not zony["coordinates"]:
            return client.directions([start, end], profile="foot-walking")
        try:
            return client.directions(
                [start, end],
                profile="foot-walking",
                options={"avoid_polygons": zony},
            )
        except exceptions.ApiError as error:
            payload = error.message if isinstance(error.message, dict) else {}
            detail = payload.get("error", {})
            code = detail.get("code") if isinstance(detail, dict) else None
            if code not in {2009, 2010}:
                raise

    zprava = (
        "S vyhýbacími zónami se trasu nepodařilo najít. "
        "Zobrazuji trasu bez vyhýbání; nebezpečná místa jsou vyznačena na mapě."
    )
    st.warning(zprava)
    # Upozornění i mimo panel navigace (ten může být zavřený)
    st.toast(zprava)
    return client.directions([start, end], profile="foot-walking")


def vytvor_avoid_polygony(mista, koncove_body, radius_metres=80, vynechat_do_m=500):
    """Vytvoří zóny kolem nebezpečných bodů, aby si trasa od nich udržela odstup.

    Body blíž než `vynechat_do_m` ke startu nebo cíli se vynechají – kdyby start/cíl
    ležel v zóně, trasa by nešla najít."""
    polygons = []

    for bod in mista:
        lat, lon = bod["souradnice"]
        phi = math.radians(lat)
        if any(
            2
            * 6_371_000
            * math.asin(
                math.sqrt(
                    math.sin(math.radians(lat - konec[1]) / 2) ** 2
                    + math.cos(phi)
                    * math.cos(math.radians(konec[1]))
                    * math.sin(math.radians(lon - konec[0]) / 2) ** 2
                )
            )
            <= vynechat_do_m
            for konec in koncove_body
        ):
            continue

        lat_offset = radius_metres / 111_000
        lon_offset = radius_metres / (111_000 * math.cos(math.radians(lat)))

        ring = [
            [lon - lon_offset, lat - lat_offset],
            [lon + lon_offset, lat - lat_offset],
            [lon + lon_offset, lat + lat_offset],
            [lon - lon_offset, lat + lat_offset],
            [lon - lon_offset, lat - lat_offset],
        ]
        polygons.append([ring])

    return {"type": "MultiPolygon", "coordinates": polygons}


def nacti_mista_z_geojsonu():
    geojson_path = Path(__file__).with_name("pocit-nebezpeci-olomouc-2.geojson")
    with geojson_path.open(encoding="utf-8") as f:
        geojson = json.load(f)

    mista = []
    for feature in geojson["features"]:
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") != "Point":
            continue

        coordinates = geometry.get("coordinates", [])
        if len(coordinates) < 2:
            continue

        lon, lat = coordinates[:2]
        if not (16.8 <= lon <= 17.7 and 49.3 <= lat <= 49.9):
            continue

        properties = feature.get("properties") or {}
        mista.append({
            "typ_nazev": properties.get("typ_nazev") or "",
            "desc_detail_duvod": properties.get("desc_detail_duvod") or "",
            "latitude": lat,
            "longitude": lon,
        })
    return mista



def priprav_mista(mista_filtr):
    """Převede záznamy z mapy (latitude, longitude, desc_detail_duvod, typ_nazev)
    na formát navigace. Místa bez popisu důvodu se vynechají."""
    nebezpecna_mista = []
    for misto in mista_filtr:
        duvod = (misto.get("desc_detail_duvod") or "").strip()
        if not duvod:
            continue

        nebezpecna_mista.append({
            "nazev mista": misto.get("typ_nazev") or duvod or "Nebezpečné místo",
            "problem mista": duvod,
            "souradnice": [misto["latitude"], misto["longitude"]],
        })
    return nebezpecna_mista


def inicializuj_stav():
    for klic in ("navigace_start", "navigace_cil", "navigace_vybirany_bod"):
        if klic not in st.session_state:
            st.session_state[klic] = None


def zrus_navigaci():
    st.session_state["navigace_start"] = None
    st.session_state["navigace_cil"] = None
    st.session_state["navigace_vybirany_bod"] = None
    st.session_state["navigace_aktivni"] = False
    st.session_state.pop("route", None)
    st.session_state.pop("navigace_parametry_trasy", None)
    # Vyčistí i vyhledávací řádky nad mapou
    for typ in ("start", "cil"):
        st.session_state.pop(f"_text_{typ}", None)
        st.session_state.pop(f"_zaloha_{typ}", None)
        _nastav_text_pole(typ, "")


def nastav_bod(typ, souradnice):
    """Nastaví start nebo cíl (souřadnice jako (lon, lat)) a určí, co se má vybrat kliknutím dál."""
    st.session_state["navigace_start" if typ == "start" else "navigace_cil"] = souradnice

    if st.session_state.get("navigace_start") is None:
        st.session_state["navigace_vybirany_bod"] = "start"
    elif st.session_state.get("navigace_cil") is None:
        st.session_state["navigace_vybirany_bod"] = "cil"
    else:
        st.session_state["navigace_vybirany_bod"] = None


def _normalizuj_text(hodnota):
    hodnota = unicodedata.normalize("NFKD", str(hodnota))
    hodnota = "".join(pismeno for pismeno in hodnota if not unicodedata.combining(pismeno))
    return re.sub(r"[^a-z0-9]+", " ", hodnota.lower()).strip()


# Zastávky MHD mají často stejný název jako budova vedle (např. "Envelopa"),
# proto je při řazení výsledků odsouváme dozadu.
_TYPY_ZASTAVEK = {"bus_stop", "tram_stop", "stop_position", "platform", "station", "halt"}


def _hledej_nominatim(dotaz):
    """Vyhledání v OpenStreetMap (Nominatim) – zná i nové budovy, které ORS ještě nemá."""
    odpoved = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": dotaz,
            "format": "jsonv2",
            "addressdetails": 1,
            "countrycodes": "cz",
            "viewbox": "16.8,49.9,17.7,49.3",
            "bounded": 1,
            "limit": 10,
            "accept-language": "cs",
        },
        headers={"User-Agent": "nebezpecna-mista-navigace/1.0"},
        timeout=10,
    )
    odpoved.raise_for_status()

    vysledky = []
    for misto in odpoved.json():
        adresa = misto.get("address") or {}
        ulice = adresa.get("road") or adresa.get("pedestrian") or adresa.get("footway")
        cislo = adresa.get("house_number")
        obec = adresa.get("city") or adresa.get("town") or adresa.get("village")
        casti = [misto.get("name"), " ".join(filter(None, [ulice, cislo])), obec]
        popis = ", ".join(dict.fromkeys(c for c in casti if c)) or misto.get("display_name")

        typ = misto.get("type") or ""
        kategorie = misto.get("category") or ""
        if typ in _TYPY_ZASTAVEK or kategorie == "public_transport":
            druh = "zastavka"
        elif kategorie == "highway":
            druh = "ulice"
        elif kategorie == "place" and typ not in {"house"}:
            druh = "oblast"
        elif typ == "house" or kategorie == "building" and not misto.get("name"):
            druh = "adresa"
        else:
            druh = "budova"

        if druh == "zastavka":
            popis = f"{popis} (zastávka)"

        vysledky.append({
            "popis": popis,
            "nazev": misto.get("name") or "",
            "souradnice": (float(misto["lon"]), float(misto["lat"])),
            "druh": druh,
            "zdroj": "osm",
        })
    return vysledky


_posledni_nominatim = [0.0]


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def adresa_bodu(lat, lon):
    """Srozumitelný popis místa pro souřadnice, např. „Jeremenkova 40, Nové Hodolany“.
    Nejdřív OpenStreetMap (Nominatim), pak OpenRouteService; když nic, vrátí None.
    Souřadnice zaokrouhlete (např. na 5 míst), ať se adresa pamatuje i po malém posunu."""
    try:
        # Nominatim dovoluje nejvýš 1 dotaz za sekundu
        cekat = 1.0 - (time.monotonic() - _posledni_nominatim[0])
        if cekat > 0:
            time.sleep(cekat)
        _posledni_nominatim[0] = time.monotonic()
        odpoved = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18,
                "addressdetails": 1, "accept-language": "cs",
            },
            headers={"User-Agent": "nebezpecna-mista-navigace/1.0"},
            timeout=10,
        )
        odpoved.raise_for_status()
        data = odpoved.json()
        adresa = data.get("address") or {}
        ulice = (
            adresa.get("road") or adresa.get("pedestrian") or adresa.get("footway")
            or adresa.get("path") or adresa.get("square")
        )
        ulice_cislo = " ".join(filter(None, [ulice, adresa.get("house_number")]))
        cast = adresa.get("quarter") or adresa.get("suburb") or adresa.get("neighbourhood")
        obec = adresa.get("city") or adresa.get("town") or adresa.get("village")
        casti = [
            data.get("name") if data.get("name") != ulice else None,
            ulice_cislo,
            cast,
            obec if obec and obec != "Olomouc" else None,
        ]
        popis = ", ".join(dict.fromkeys(c for c in casti if c))
        if popis:
            return popis
    except Exception:
        pass

    try:
        odpoved = openrouteservice.Client(key=ORS_KLIC).pelias_reverse(
            [lon, lat], size=1, layers=["address", "street", "venue"]
        )
        vlastnosti = odpoved["features"][0]["properties"]
        return vlastnosti.get("name") or vlastnosti.get("label")
    except Exception:
        return None


def _hledej_ors(dotaz):
    client = openrouteservice.Client(key=ORS_KLIC)
    odpoved = client.pelias_search(
        dotaz,
        focus_point=[17.2509, 49.5938],
        rect_min_x=16.8,
        rect_min_y=49.3,
        rect_max_x=17.7,
        rect_max_y=49.9,
        country="CZ",
        layers=["venue", "address", "street"],
        size=10,
    )

    vysledky = []
    for vysledek in odpoved.get("features", []):
        souradnice = tuple(vysledek.get("geometry", {}).get("coordinates", [])[:2])
        if len(souradnice) != 2:
            continue
        vlastnosti = vysledek.get("properties") or {}
        vrstva = str(vlastnosti.get("layer") or "").lower()
        vysledky.append({
            "popis": vlastnosti.get("label") or vlastnosti.get("name") or dotaz,
            "nazev": vlastnosti.get("name") or "",
            "souradnice": souradnice,
            "druh": {"venue": "budova", "address": "adresa", "street": "ulice"}.get(vrstva, "oblast"),
            "zdroj": "ors",
        })
    return vysledky


@st.cache_data(ttl=3600, show_spinner=False)
def hledej_misto(text):
    """Najde adresu/místo (OpenStreetMap + OpenRouteService), budovy a adresy mají přednost."""
    dotaz = text.strip()
    dotaz_normalizovany = _normalizuj_text(dotaz)

    vysledky = []
    chyby = 0
    for hledac in (_hledej_nominatim, _hledej_ors):
        try:
            vysledky.extend(hledac(dotaz))
        except Exception:
            chyby += 1
    if chyby == 2:
        raise RuntimeError("Vyhledávání není dostupné")

    # Když dotaz neobsahuje město a nic přesného se nenašlo, zkusí se ještě s "Olomouc"
    if "olomouc" not in dotaz_normalizovany and not any(
        dotaz_normalizovany in _normalizuj_text(v["nazev"]) for v in vysledky
    ):
        try:
            vysledky.extend(_hledej_ors(f"{dotaz}, Olomouc"))
        except Exception:
            pass

    def vzdalenost_m(a, b):
        return math.hypot((a[0] - b[0]) * 72_000, (a[1] - b[1]) * 111_000)

    # ORS zná zastávky jen jako obecná "místa" – pokud na stejném místě leží zastávka
    # z OSM se stejným jménem, jde o tutéž zastávku.
    zastavky = [v for v in vysledky if v["druh"] == "zastavka"]
    for vysledek in vysledky:
        if vysledek["zdroj"] == "ors" and any(
            _normalizuj_text(z["nazev"]) == _normalizuj_text(vysledek["nazev"])
            and vzdalenost_m(z["souradnice"], vysledek["souradnice"]) < 60
            for z in zastavky
        ):
            vysledek["druh"] = "zastavka"
            vysledek["popis"] = f"{vysledek['nazev']} (zastávka)"

    stred_olomouce = (17.2509, 49.5938)
    body_za_druh = {"budova": 300, "adresa": 250, "oblast": 0, "ulice": -100, "zastavka": -400}
    kandidati = []
    for vysledek in vysledky:
        lon, lat = vysledek["souradnice"]
        if not (16.8 <= lon <= 17.7 and 49.3 <= lat <= 49.9):
            continue

        nazev = _normalizuj_text(vysledek["nazev"] or vysledek["popis"])
        skore = body_za_druh.get(vysledek["druh"], 0)
        if vzdalenost_m(vysledek["souradnice"], stred_olomouce) < 8_000:
            skore += 250
        if dotaz_normalizovany == nazev:
            skore += 500
        elif nazev and dotaz_normalizovany in nazev:
            skore += 300
        elif nazev and nazev in dotaz_normalizovany:
            skore += 150
        if "olomouc" in _normalizuj_text(vysledek["popis"]):
            skore += 100
        if vysledek["zdroj"] == "osm":
            skore += 20  # při shodě vyhrává přesnější OSM

        kandidati.append({
            "popis": vysledek["popis"],
            "souradnice": vysledek["souradnice"],
            "_skore": skore,
        })

    kandidati.sort(key=lambda kandidat: kandidat["_skore"], reverse=True)

    unique = []
    for kandidat in kandidati:
        lon, lat = kandidat["souradnice"]
        je_duplicitni = any(
            math.hypot(
                (lon - jiny["souradnice"][0]) * 73_000,
                (lat - jiny["souradnice"][1]) * 111_000,
            ) < 25
            for jiny in unique
        )
        if not je_duplicitni:
            kandidat.pop("_skore", None)
            unique.append(kandidat)
        if len(unique) == 5:
            break
    return unique


# --- Našeptávač ve stylu mapy.com -------------------------------------------------
# Komponenta ve složce "naseptavac" hledá návrhy přímo v prohlížeči (Photon nad
# OpenStreetMap), takže psaní nespouští Streamlit znovu a nic se nezasekává.
# Do Pythonu pošle až vybrané místo, nebo žádost o záložní hledání, když Photon nejede.
_naseptavac = components.declare_component(
    "naseptavac", path=str(Path(__file__).with_name("naseptavac"))
)

VYHLEDAVANI_CSS = """
<style>
.st-key-mapa_obal {
    position: relative;
}
.st-key-hledani_trasy {
    position: absolute !important;
    top: 10px;
    left: 56px;
    z-index: 1000;
    width: min(420px, calc(100% - 70px)) !important;
    padding: 10px 12px 12px 12px;
    background: rgba(27, 23, 38, 0.97);
    border: 1px solid #3b2a5c;
    border-radius: 12px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
    gap: 0.4rem !important;
}
.st-key-hledani_trasy p {
    margin: 0;
}
/* Políčka se po zapnutí načítají asi 0,3 s a panel by mezitím měnil velikost.
   Proto se ukáže až potom (zpoždění 0,35 s) jemným náběhem – rovnou hotový. */
.st-key-hledani_trasy iframe {
    min-height: 42px;
}
.st-key-hledani_trasy {
    animation: hledani-objevit 0.2s ease-out 0.35s both;
}
@keyframes hledani-objevit {
    from { opacity: 0; transform: translateY(-6px); }
    to { opacity: 1; transform: none; }
}
</style>
"""


def _nastav_text_pole(typ, text):
    """Vepíše text do vyhledávacího políčka (projeví se při dalším vykreslení)."""
    st.session_state[f"_popisek_{typ}"] = text
    st.session_state[f"_verze_{typ}"] = st.session_state.get(f"_verze_{typ}", 0) + 1


def _hledaci_radek(typ, ikona, placeholder):
    """Jeden vyhledávací řádek s našeptávačem. Vrací True, když se změnil start/cíl."""
    # Text nastavený kliknutím do mapy
    cekajici_text = st.session_state.pop(f"_text_{typ}", None)
    if cekajici_text is not None:
        _nastav_text_pole(typ, cekajici_text)

    hodnota = _naseptavac(
        ikona=ikona,
        placeholder=placeholder,
        text=st.session_state.get(f"_popisek_{typ}", ""),
        verze=st.session_state.get(f"_verze_{typ}", 0),
        zaloha=st.session_state.get(f"_zaloha_{typ}"),
        key=f"naseptavac_{typ}",
        default=None,
    )

    # Komponenta vrací pořád poslední hodnotu -> zpracujeme jen novou (podle nonce)
    if not isinstance(hodnota, dict) or hodnota.get("nonce") == st.session_state.get(f"_nonce_{typ}"):
        return False
    st.session_state[f"_nonce_{typ}"] = hodnota.get("nonce")

    if "zaloha" in hodnota:
        dotaz = hodnota["zaloha"]
        try:
            vysledky = [
                {"popis": v["popis"], "souradnice": list(v["souradnice"])}
                for v in hledej_misto(dotaz)
            ]
            st.session_state[f"_zaloha_{typ}"] = {"dotaz": dotaz, "vysledky": vysledky}
        except Exception:
            st.session_state[f"_zaloha_{typ}"] = {"dotaz": dotaz, "vysledky": [], "chyba": True}
        return True  # překreslit, aby komponenta dostala výsledky

    souradnice = tuple(hodnota["souradnice"])
    st.session_state[f"_popisek_{typ}"] = hodnota.get("popis", "")
    nastav_bod(typ, souradnice)
    return True


def _prohod_start_a_cil():
    stav = st.session_state
    stav["navigace_start"], stav["navigace_cil"] = stav.get("navigace_cil"), stav.get("navigace_start")
    popisek_start, popisek_cil = stav.get("_popisek_start", ""), stav.get("_popisek_cil", "")
    _nastav_text_pole("start", popisek_cil)
    _nastav_text_pole("cil", popisek_start)
    if stav["navigace_start"] is None:
        stav["navigace_vybirany_bod"] = "start"
    elif stav["navigace_cil"] is None:
        stav["navigace_vybirany_bod"] = "cil"
    else:
        stav["navigace_vybirany_bod"] = None


def vyhledavaci_panel():
    """Vyhledávací řádky Odkud/Kam s našeptávačem (volat uvnitř kontejneru 'mapa_obal')."""
    if not st.session_state.get("navigace_aktivni"):
        return

    with st.container(key="hledani_trasy"):
        st.markdown(VYHLEDAVANI_CSS, unsafe_allow_html=True)

        nadpis, prohodit, zavrit = st.columns([4, 1, 1], vertical_alignment="center")
        nadpis.markdown("**Naplánovat trasu**")
        if prohodit.button("⇅", key="prohodit_body", help="Prohodit start a cíl"):
            _prohod_start_a_cil()
            st.rerun()
        if zavrit.button("✕", key="zavrit_hledani", help="Skrýt vyhledávání (trasa zůstane)"):
            st.session_state["navigace_aktivni"] = False
            st.rerun()

        zmena = _hledaci_radek("start", "", "Odkud – adresa nebo místo")
        zmena = _hledaci_radek("cil", "", "Kam – adresa nebo místo") or zmena

    if zmena:
        st.rerun()


def posun_bocni_listu_dolu():
    """Plynule posune dolů jen boční lištu (sidebar), hlavní stránka s mapou zůstane, kde je."""
    # Počítadlo zajistí, že se skript spustí znovu i při opakovaném kliknutí
    st.session_state["navigace_posun"] = st.session_state.get("navigace_posun", 0) + 1
    components.html(
        f"""
        <script>
        // pokus {st.session_state["navigace_posun"]}
        const doc = window.parent.document;
        function posun() {{
            const lista = doc.querySelector('[data-testid="stSidebar"]');
            if (!lista) return;
            const kandidati = [lista, ...lista.querySelectorAll("div")];
            const posuvny = kandidati.find(
                el => el.scrollHeight > el.clientHeight + 5
                    && getComputedStyle(el).overflowY !== "visible"
            );
            if (posuvny) {{
                posuvny.scrollTo({{ top: posuvny.scrollHeight, behavior: "smooth" }});
            }}
        }}
        setTimeout(posun, 150);
        </script>
        """,
        height=0,
    )


def ovladani_navigace(nebezpecna_mista, posun_listy=True):
    """Vykreslí ovládání navigace do aktuálního kontejneru a vrátí nalezenou trasu (nebo None).

    `posun_listy=False` vypne posunutí boční lišty dolů po kliknutí na „Zvolit start a cíl“
    (když je navigace ve vlastním vysouvacím panelu, není kam posouvat)."""
    inicializuj_stav()

    posunout_listu = False
    if st.button("Zvolit start a cíl", use_container_width=True):
        zrus_navigaci()
        st.session_state["navigace_vybirany_bod"] = "start"
        st.session_state["navigace_aktivni"] = True
        posunout_listu = True

    start = st.session_state["navigace_start"]
    end = st.session_state["navigace_cil"]

    if st.session_state["navigace_vybirany_bod"] == "start":
        st.info("Napište start do vyhledávání nad mapou, nebo klikněte do mapy.")
    elif st.session_state["navigace_vybirany_bod"] == "cil":
        st.info("Start je vybrán. Napište cíl do vyhledávání, nebo klikněte do mapy.")

    st.caption(
        "Start: "
        + (f"{start[1]:.5f}, {start[0]:.5f}" if start else "nevybrán")
        + "  \nCíl: "
        + (f"{end[1]:.5f}, {end[0]:.5f}" if end else "nevybrán")
    )
    # Odstup je vidět pořád (i po zavření vyhledávání); po změně se trasa přepočítá
    if "navigace_odstup_m" not in st.session_state:
        st.session_state["navigace_odstup_m"] = 20
    radius_metres = st.number_input(
        "Odstup od nebezpečných míst (m)",
        min_value=1,
        max_value=300,
        step=5,
        key="navigace_odstup_m",
        help="Trasa se vyhne všem zobrazeným nebezpečným místům alespoň o tuto "
             "vzdálenost (kromě míst přímo u startu a cíle).",
    )

    # Při změně filtru se trasa přepočítá s novými nebezpečnými místy
    podpis_filtru = tuple(
        (m["souradnice"][0], m["souradnice"][1], m["problem mista"])
        for m in nebezpecna_mista
    )
    zmena_filtru = st.session_state.get("route_filter_signature") != podpis_filtru
    st.session_state["route_filter_signature"] = podpis_filtru

    parametry_trasy = (start, end, radius_metres)
    route = st.session_state.get("route")

    def prepocitej_trasu():
        client = openrouteservice.Client(key=ORS_KLIC)
        # Nejdřív se trasa vyhne všem bodům kromě těch přímo u startu/cíle (jejich zóna
        # by start/cíl zakryla). Kdyby taková trasa neexistovala, zkusí se vynechat
        # body do 500 m od startu/cíle a až pak trasa bez vyhýbání.
        sady_zon = [
            vytvor_avoid_polygony(
                nebezpecna_mista,
                [start, end],
                radius_metres=radius_metres,
                vynechat_do_m=vynechat,
            )
            for vynechat in (radius_metres * 1.5 + 30, 500)
        ]
        st.session_state["route"] = najdi_trasu(client, start, end, sady_zon)
        st.session_state["navigace_parametry_trasy"] = parametry_trasy
        return st.session_state["route"]

    zrusit = st.button(
        "Zrušit",
        disabled=start is None and end is None and route is None
        and st.session_state["navigace_vybirany_bod"] is None
        and not st.session_state.get("navigace_aktivni"),
        use_container_width=True,
    )

    if zrusit:
        zrus_navigaci()
        st.rerun()

    if posunout_listu and posun_listy:
        posun_bocni_listu_dolu()

    if start is not None and end is not None and (
        route is None
        or zmena_filtru
        or st.session_state.get("navigace_parametry_trasy") != parametry_trasy
    ):
        with st.spinner("Hledám trasu..."):
            route = prepocitej_trasu()

    return route


SLOZKA_IKON = Path(__file__).with_name("Ikony")


def _ikona_spendliku(soubor):
    """Vlastní ikona špendlíku (obrázek 35×45 px, na mapě zmenšený na 28×36) –
    špička dole uprostřed sedí přesně na bodu."""
    return folium.CustomIcon(
        str(SLOZKA_IKON / soubor),
        icon_size=(28, 36),
        icon_anchor=(14, 36),
        popup_anchor=(0, -33),
    )


def vrstva_navigace(route):
    """Vrátí start, cíl a trasu jako samostatnou vrstvu (FeatureGroup).

    Vrstva se předá do st_folium přes `feature_group_to_add`. Základní mapa tak zůstane
    stejná a při změně startu/cíle/trasy se jen vymění tato vrstva – mapa se znovu
    nenačítá a zůstane na stejném místě i přiblížení."""
    vrstva = folium.FeatureGroup(name="Navigace")
    start = st.session_state.get("navigace_start")
    end = st.session_state.get("navigace_cil")

    if route is not None:
        decoded = convert.decode_polyline(route["routes"][0]["geometry"])
        body_trasy = [[bod[1], bod[0]] for bod in decoded["coordinates"]]
        # Bílý obrys pod trasou, aby byla vidět i na tmavé mapě přes barevné čáry osvětlení
        folium.PolyLine(
            locations=body_trasy,
            color="white",
            weight=9,
            opacity=0.9,
        ).add_to(vrstva)
        folium.PolyLine(
            locations=body_trasy,
            color="#1f5bff",
            weight=5,
            opacity=1,
        ).add_to(vrstva)

    if start is not None:
        folium.Marker(
            location=[start[1], start[0]],
            popup="Start",
            icon=_ikona_spendliku("StartMain.png"),
        ).add_to(vrstva)

    if end is not None:
        folium.Marker(
            location=[end[1], end[0]],
            popup="Cíl",
            icon=_ikona_spendliku("CilMain.png"),
        ).add_to(vrstva)

    return vrstva


def vykresli_navigaci(mapa, route):
    """Přidá do mapy start, cíl a trasu (starší způsob – mapa se při každé změně načte znovu)."""
    vrstva_navigace(route).add_to(mapa)


def zpracuj_klik_navigace(kliknuti):
    """Zpracuje kliknutí do mapy při výběru startu/cíle. Vrací True, pokud klik použila navigace."""
    rezim = st.session_state.get("navigace_vybirany_bod")
    if rezim is None:
        return False

    souradnice = (kliknuti["lng"], kliknuti["lat"])
    nastav_bod(rezim, souradnice)
    # Do vyhledávacího řádku se vepíše, že bod byl vybrán na mapě
    st.session_state[f"_text_{rezim}"] = (
        f"Bod na mapě ({kliknuti['lat']:.5f}, {kliknuti['lng']:.5f})"
    )
    return True


def zobraz_navigaci(mista_filtr=None):
    """Samostatná stránka navigace (pro testování: python -m streamlit run navigace_test4.py)."""
    st.title("Navigace")

    if mista_filtr is None:
        mista_filtr = nacti_mista_z_geojsonu()
    nebezpecna_mista = priprav_mista(mista_filtr)

    levy_sloupec, pravy_sloupec = st.columns([3, 1])

    with pravy_sloupec:
        st.subheader("Body trasy")
        route = ovladani_navigace(nebezpecna_mista)
        st.metric("Nebezpečných míst", len(nebezpecna_mista))

    with levy_sloupec:
        st.caption("Vyhledat adresu nebo místo")
        sloupec_dotaz, sloupec_hledat = st.columns([5, 1])
        with sloupec_dotaz:
            dotaz = st.text_input(
                "Adresa nebo místo",
                placeholder="Např. ulice, adresa nebo místo",
                label_visibility="collapsed",
                key="navigace_hledany_dotaz",
            )
        with sloupec_hledat:
            hledat = st.button(
                "Hledat",
                use_container_width=True,
            )

        if hledat:
            st.session_state["navigace_hledana_lokace"] = None
            if not dotaz.strip():
                st.warning("Zadejte adresu nebo místo k vyhledání.")
            else:
                try:
                    nalezena_mista = hledej_misto(dotaz.strip())
                except Exception as error:
                    st.error(f"Místo se nepodařilo vyhledat: {error}")
                else:
                    if not nalezena_mista:
                        st.warning("Pro zadaný dotaz se nepodařilo najít místo.")
                    else:
                        nalezene_misto = nalezena_mista[0]
                        st.session_state["navigace_hledana_lokace"] = {
                            "souradnice": nalezene_misto["souradnice"],
                            "nazev": nalezene_misto["popis"],
                        }

        hledana_lokace = st.session_state.get("navigace_hledana_lokace")
        if hledana_lokace:
            st.caption(f"Nalezeno: {hledana_lokace['nazev']}")
            stred_mapy = [
                hledana_lokace["souradnice"][1],
                hledana_lokace["souradnice"][0],
            ]
            priblizeni = 16
        else:
            stred_mapy = [49.5938, 17.2509]
            priblizeni = 13

        mapa = folium.Map(location=stred_mapy, zoom_start=priblizeni)
        if hledana_lokace:
            folium.Marker(
                location=stred_mapy,
                tooltip=hledana_lokace["nazev"],
                icon=folium.Icon(color="orange", icon="search"),
            ).add_to(mapa)

        FastMarkerCluster(
            data=[
                [m["souradnice"][0], m["souradnice"][1], m["nazev mista"], m["problem mista"]]
                for m in nebezpecna_mista
            ],
            callback="""
            function (row) {
                var icon = L.divIcon({
                    className: "",
                    html: '<div style="width:10px;height:10px;border-radius:50%;background:#d62728;border:1px solid white;"></div>',
                    iconSize: [12, 12],
                    iconAnchor: [6, 6]
                });
                var marker = L.marker(new L.LatLng(row[0], row[1]), {icon: icon});
                if (row[2]) {
                    var tooltip = document.createElement("div");
                    tooltip.textContent = row[2];
                    marker.bindTooltip(tooltip);
                }
                if (row[3]) {
                    var popup = document.createElement("div");
                    popup.textContent = row[3];
                    marker.bindPopup(popup);
                }
                return marker;
            }
            """,
            name="Nebezpečná místa",
            options={
                "maxClusterRadius": 60,
                "animate": False,
                "spiderfyOnMaxZoom": False,
                "showCoverageOnHover": False,
            },
        ).add_to(mapa)
        vykresli_navigaci(mapa, route)

        if route is not None:
            summary = route["routes"][0]["summary"]
            st.write("Délka trasy:", summary["distance"], "m")
            st.write("Doba chůze:", round(summary["duration"] / 60, 1), "minut")

        output = st_folium(
            mapa,
            width=None,
            height=600,
            returned_objects=["last_clicked"],
            key="navigace",
        )

        kliknuti = output.get("last_clicked")
        if kliknuti:
            podpis_kliku = (round(kliknuti["lat"], 6), round(kliknuti["lng"], 6))
            if podpis_kliku != st.session_state.get("navigace_posledni_klik"):
                st.session_state["navigace_posledni_klik"] = podpis_kliku
                if zpracuj_klik_navigace(kliknuti):
                    st.rerun()


if __name__ == "__main__":
    zobraz_navigaci()
