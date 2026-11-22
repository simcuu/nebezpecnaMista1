import streamlit as st
import folium
import base64
from streamlit_folium import st_folium
import html
import json
import os
import pandas as pd
from supabase import create_client
from navigace_test4 import (
    adresa_bodu,
    ovladani_navigace,
    priprav_mista,
    vrstva_navigace,
    vyhledavaci_panel,
    zpracuj_klik_navigace,
)
from kategorie import zarad_kategorie, NAZVY, V_NABIDCE
from ai_kategorie import zarad_pomoci_ai
from srovnani_tras import zobraz_srovnani
from rychle_vrstvy import (
    GeoJsonZeSouboru,
    PrepinacMapy,
    RychlyGeoJson,
    na_json,
    uloz_staticky_soubor,
    zjednodus_osvetleni,
)

# Nastavení stránky
st.set_page_config(
    page_title="Nebezpečná místa – Olomouc",
    page_icon="🛡️",
    layout="wide"
)
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

# Vzhled legendy a řádku se statistikami
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stMarkdown, button, input, textarea, select {
        font-family: 'Inter', sans-serif;
    }

    /* Při přepočtu (kliknutí, výběr startu/cíle) Streamlit stránku zešedí –
       necháme ji plně viditelnou, aby to nevypadalo jako znovunačtení */
    [data-stale="true"], .stale-element {
        opacity: 1 !important;
        transition: none !important;
    }

    /* Menší horní odsazení stránky, aby nadpis byl výš */
    .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: 3.5rem !important;
        padding-bottom: 2rem !important;
    }

    /* Boční panel – obsah začíná výš */
    [data-testid="stSidebarHeader"] {
        height: 1.75rem;
        padding-top: 0.25rem;
        padding-bottom: 0;
    }
    [data-testid="stSidebarUserContent"] {
        padding-top: 0 !important;
    }
    [data-testid="stSidebarUserContent"] h1 {
        padding-top: 0 !important;
    }

    /* Hlavička */
    .hlavicka {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 18px 22px;
        margin-bottom: 14px;
        border-radius: 16px;
        background:
            radial-gradient(circle at 0% 0%, rgba(155, 127, 212, 0.35), transparent 55%),
            linear-gradient(135deg, #1d1729 0%, #141019 100%);
        border: 1px solid #2e2442;
    }
    .hlavicka-ikona {
        font-size: 2.2rem;
        width: 58px;
        height: 58px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 14px;
        background: rgba(155, 127, 212, 0.18);
        flex-shrink: 0;
    }
    .hlavicka-text {
        display: flex;
        flex-direction: column;
        min-width: 0;
    }
    .hlavicka h1 {
        margin: 0 !important;
        padding: 0 !important;
        /* Nadpis vždy na jednom řádku – na úzké obrazovce se zmenší písmo */
        white-space: nowrap;
        font-size: clamp(1rem, 2.6vw, 2.2rem) !important;
        font-weight: 800 !important;
        letter-spacing: 0.02em;
        line-height: 1.2 !important;
        background: linear-gradient(90deg, #ffffff, #c9b6f0);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
    }
    .hlavicka p {
        margin: 4px 0 0 0;
        opacity: 0.7;
        font-size: 0.95rem;
    }

    /* Boční panel */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #17131f 0%, #100d16 100%);
        border-right: 1px solid #2e2442;
    }
    .sekce {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #9b7fd4;
        margin: 18px 0 6px 0;
    }

    /* Tlačítka */
    .stButton > button {
        border-radius: 10px;
        font-weight: 600;
        border: 1px solid #3b2a5c;
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        border-color: #9b7fd4;
        box-shadow: 0 0 0 3px rgba(155, 127, 212, 0.2);
    }

    /* Mapa se zaoblenými rohy a stínem */
    .st-key-mapa_obal iframe {
        border-radius: 14px;
        border: 1px solid #2e2442 !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
    }

    /* Rozbalovací seznam */
    [data-testid="stExpander"] details {
        border-radius: 12px;
        border-color: #2e2442;
        background: #141019;
    }

    /* Legenda jako banner v pravém horním rohu mapy */
    /* gap: 0 – legenda a vyhledávání leží přes mapu (absolute), ale Streamlit by jim
       jinak nechal mezeru 1rem. Při zapnutí navigace by se tak obal mapy prodloužil
       a všechno pod mapou by poskočilo dolů. */
    .st-key-mapa_obal {
        position: relative;
        gap: 0 !important;
    }
    .st-key-legenda_mapy {
        position: absolute !important;
        top: 8px;
        right: 14px;
        z-index: 1000;
        width: 240px !important;
        overflow: visible;
    }
    .legenda {
        background: rgba(27, 23, 38, 0.95);
        border: 1px solid #3b2a5c;
        border-radius: 12px;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
        padding: 10px 14px;
        margin: 0;
        font-size: 0.82rem;
        line-height: 1.3;
    }
    .legenda-nadpis {
        font-weight: 600;
        margin-bottom: 8px;
    }
    .legenda-polozka {
        display: flex;
        align-items: center;
        gap: 8px;
        margin: 5px 0;
    }
    .legenda-tecka {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        border: 2px solid rgba(255, 255, 255, 0.8);
        flex-shrink: 0;
    }
    .legenda-osvetleni {
        height: 8px;
        border-radius: 4px;
        background: linear-gradient(90deg, #e3261b, #f47a20, #f9b233, #ffd84a, #fff200);
    }
    .legenda-osvetleni-popis {
        display: flex;
        justify-content: space-between;
        font-size: 0.8rem;
        opacity: 0.8;
        margin-top: 4px;
    }
    /* Statistiky pod mapou jako karty */
    .statistiky {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px;
        margin: 14px 0 12px 0;
    }
    .karta {
        background: linear-gradient(180deg, #1b1726 0%, #15111d 100%);
        border: 1px solid #2e2442;
        border-radius: 12px;
        padding: 12px 14px;
    }
    .karta-popis {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.65;
    }
    .karta-hodnota {
        font-size: 1.5rem;
        font-weight: 700;
        color: #c9b6f0;
        margin-top: 2px;
    }
    .karta-hodnota small {
        font-size: 0.85rem;
        font-weight: 500;
        opacity: 0.6;
        color: #ECE8F5;
    }
    </style>
    """,
    unsafe_allow_html=True
)

def nacti_body():
    radky = (
        supabase.table("vlastni_body")
        .select("id,nazev,duvod,lat,lon,kategorie")
        .execute()
        .data
    ) or []

    return [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [radek["lon"], radek["lat"]]
            },
            "properties": {
                "id": radek["id"],
                "nazev": radek["nazev"],
                "duvod": radek["duvod"],
                "kategorie": radek.get("kategorie") or []
            }
        }
        for radek in radky
    ]

# Inicializace vlastních bodů
if "moje_body" not in st.session_state:
    st.session_state.moje_body = nacti_body()

if "cekajici_bod" not in st.session_state:
    st.session_state.cekajici_bod = None

if "posledni_klik" not in st.session_state:
    st.session_state.posledni_klik = None

# Režim přidávání bodu (zapíná se tlačítkem v bočním panelu)
if "rezim_pridani" not in st.session_state:
    st.session_state.rezim_pridani = False


# Barvy podle kategorie
barvy = {
    "a": "#7B61A8",
    "b": "#E5A000",
}


# Načtení a zpracování GeoJSON souboru.
# @st.cache_data: soubor se přečte jen jednou, při dalších klicích se vezme hotová tabulka z paměti.
@st.cache_data(show_spinner=False)
def nacti_data():
    with open(
        "pocit-nebezpeci-olomouc-2.geojson",
        encoding="utf-8"
    ) as f:
        geojson = json.load(f)

    rows = []

    for feature in geojson["features"]:
        geometry = feature.get("geometry")

        if geometry and geometry["type"] == "Point":
            lon, lat = geometry["coordinates"][:2]

            if 16.8 <= lon <= 17.7 and 49.3 <= lat <= 49.9:
                rows.append({
                    "latitude": lat,
                    "longitude": lon,
                    "typ_ident": feature["properties"].get("typ_ident"),
                    "typ_nazev": feature["properties"].get("typ_nazev") or "",
                    "desc_detail_duvod": (
                        feature["properties"].get("desc_detail_duvod") or ""
                    ),
                })

    df = pd.DataFrame(rows)
    df["desc_detail_duvod"] = (
        df["desc_detail_duvod"].fillna("").astype(str).str.strip()
    )
    df["kategorie_duvodu"] = df["desc_detail_duvod"].apply(zarad_kategorie)
    df["barva"] = df["typ_ident"].map(barvy).fillna("#888888")
    return df


df = nacti_data()


# Načtení Voronoiových oblastí (data kriminality) – polygony, také jen jednou
@st.cache_data(show_spinner=False)
def nacti_voronoi():
    with open(
        "voronoi_olomouc.geojson",
        encoding="utf-8"
    ) as f:
        return json.load(f)


voronoi_geojson = nacti_voronoi()


# Osvětlení ulic – čáry po ulicích obarvené podle počtu lamp v okolí.
# Soubor vytváří skript priprav_osvetleni_ulic.py (z dat stažených stahni_arcgis_geojson.py).
# Čáry se jednou zjednoduší (cca poloviční velikost) a uloží do složky static,
# odkud si je prohlížeč stáhne jen jednou. Vrací název souboru pro mapu (nebo None).
@st.cache_data(show_spinner=False)
def nacti_osvetleni():
    try:
        with open("osvetleni_ulic.geojson", encoding="utf-8") as f:
            data = zjednodus_osvetleni(json.load(f))
    except FileNotFoundError:
        return None
    return uloz_staticky_soubor("osvetleni_ulic.json", na_json(data))


# Barvy čar: 0 = žádná lampa (červená) … 4 = hodně lamp (zářivě žlutá)
barvy_osvetleni = {
    0: "#e3261b",
    1: "#f47a20",
    2: "#f9b233",
    3: "#ffd84a",
    4: "#fff200",
}

osvetleni = nacti_osvetleni()


# Data kriminality Policie ČR (kriminalita_olomouc.csv vytváří priprav_kriminalitu.py).
# Každý typ činu patří do skupiny (Násilná, Krádeže, PŘ – BESIP…) a skupina
# do stejných kategorií, jaké používá filtr pocitu nebezpečí.
kategorie_skupin = {
    "Lidé a chování": (
        1,    # Násilná
        80,   # Toxikománie
        84,   # Zbraně
        96,   # Extremismus
        75,   # PŘ – alkohol a toxi
        76,   # PŘ – veřejný pořádek a občanské soužití
    ),
    "Doprava a provoz": (
        79,   # Dopravní nehody
        74,   # PŘ – BESIP
    ),
    "Krádeže a majetek": (
        18,   # Krádeže vloupáním
        35,   # Krádeže
        54,   # Podvody
        55,   # Jiná majetková
        77,   # PŘ – majetek
    ),
}

# Tma = 20:00–5:59, světlo = 6:00–19:59
NOC_OD = 20
NOC_DO = 6


def _kod_z_iri(iri):
    return int(iri.rsplit("/", 1)[1]) if iri else 0


@st.cache_data(show_spinner=False)
def nacti_typy_cinu():
    """Vrátí {kód typu: (název skupiny, kategorie)}."""
    with open("types.json", encoding="utf-8") as f:
        polozky = json.load(f)["polozky"]

    nazvy = {p["kod"]: p["nazev"]["cs"] for p in polozky}
    typy = {}

    for p in polozky:
        rodic1 = _kod_z_iri(p["iri_1"])
        rodic2 = _kod_z_iri(p["iri_2"])

        if rodic1 == 0:
            skupina = p["kod"]
        elif rodic1 == 97:
            # Přestupky se dělí ještě o úroveň níž (BESIP, alkohol, majetek…)
            skupina = rodic2 or p["kod"]
        else:
            skupina = rodic1

        kategorie = next(
            (k for k, skupiny in kategorie_skupin.items() if skupina in skupiny),
            "Ostatní"
        )
        typy[p["kod"]] = (nazvy[skupina], kategorie)

    return typy


@st.cache_data(show_spinner=False)
def nacti_kriminalitu():
    """Jeden řádek = jedna událost se seznamem kategorií a skupin."""
    try:
        radky = pd.read_csv("kriminalita_olomouc.csv")
    except FileNotFoundError:
        return pd.DataFrame(
            columns=["id", "oblast", "typ_ident", "kategorie_duvodu", "skupiny"]
        )

    typy = nacti_typy_cinu()
    radky["skupina"] = radky["types"].map(lambda t: typy.get(t, ("Ostatní",))[0])
    radky["kategorie"] = radky["types"].map(
        lambda t: typy.get(t, (None, "Ostatní"))[1]
    )

    def bez_obecneho(hodnoty, obecna):
        # „Ostatní“ / „Přestupky“ jen tehdy, když událost nemá nic konkrétnějšího
        konkretni = sorted(set(hodnoty) - {obecna})
        return konkretni or [obecna]

    udalosti = radky.groupby("id").agg(
        oblast=("oblast", "first"),
        date=("date", "first"),
        kategorie_duvodu=("kategorie", lambda k: ["policie"]),
        skupiny=("skupina", lambda s: bez_obecneho(s, "Přestupky")),
    ).reset_index()

    # Čas události je místní (+01:00/+02:00), stačí vzít hodinu z textu
    hodina = pd.to_datetime(udalosti["date"].str[:19]).dt.hour
    noc = (hodina >= NOC_OD) | (hodina < NOC_DO)
    udalosti["typ_ident"] = noc.map({True: "a", False: "b"})
    return udalosti


df_krim = nacti_kriminalitu()

# Budovy Univerzity Palackého a večerní výuka (data z upol.html, uložená v budovy_upol.json).
# Za každou budovu: kolik studentů tam má výuku končící po setmění, jak často a kdy.
@st.cache_data(show_spinner=False)
def nacti_budovy():
    try:
        with open("budovy_upol.json", encoding="utf-8") as f:
            budovy = json.load(f)
    except FileNotFoundError:
        return []
    # Budovy bez souřadnic (BO, DK, OV, PV) na mapu dát nejde
    return [b for b in budovy if b["lat"] is not None and b["lon"] is not None]


budovy = nacti_budovy()


# Tvary (obrysy) budov z OpenStreetMap – vytváří je priprav_budovy_upol.py
@st.cache_data(show_spinner=False)
def nacti_tvary_budov():
    try:
        with open("budovy_upol_tvary.geojson", encoding="utf-8") as f:
            return {
                prvek["properties"]["id"]: prvek["geometry"]
                for prvek in json.load(f)["features"]
            }
    except FileNotFoundError:
        return {}


tvary_budov = nacti_tvary_budov()


# Školy v Olomouci (data o školách s body; jen obec Olomouc):
# zs.geojson = základní, ss.geojson = střední. Obrysy budov z OpenStreetMap
# vytváří priprav_zs_tvary.py (zs_tvary.geojson, ss_tvary.geojson).
@st.cache_data(show_spinner=False)
def nacti_skoly(soubor, zmena_souboru):
    # zmena_souboru = čas změny souboru, aby se po úpravě dat nepoužila stará cache
    with open(soubor, encoding="utf-8") as f:
        prvky = json.load(f)["features"]
    skoly = []
    for prvek in prvky:
        p = prvek["properties"]
        lon, lat = prvek["geometry"]["coordinates"][:2]
        skoly.append({
            "id": p.get("OBJECTID"),
            "lat": lat,
            "lon": lon,
            "nazev": p.get("ORG_NAZEV") or "Škola",
            "typ": p.get("ZAR_TYP_NAZEV") or "",
            "adresa": p.get("ADRESA") or "",
            "kapacita": p.get("ZAR_KAPACITA"),
            "web": p.get("ORG_WEB"),
        })
    return skoly


@st.cache_data(show_spinner=False)
def nacti_tvary(soubor, zmena_souboru):
    with open(soubor, encoding="utf-8") as f:
        return {
            prvek["properties"]["id"]: prvek["geometry"]
            for prvek in json.load(f)["features"]
        }


def nacti_bezpecne(funkce, soubor, prazdne):
    """Zavolá načítací funkci; když soubor chybí, vrátí `prazdne` (a nic se neuloží do cache)."""
    try:
        return funkce(soubor, os.path.getmtime(soubor))
    except FileNotFoundError:
        return prazdne


# Typy škol na mapě: název, data, tvary, barva výplně, barva záře, CSS třída
TYPY_SKOL = [
    {
        "nazev": "Základní školy",
        "skoly": nacti_bezpecne(nacti_skoly, "zs.geojson", []),
        "tvary": nacti_bezpecne(nacti_tvary, "zs_tvary.geojson", {}),
        "barva": "#f2c94c",
        "obrys": "#fff8e1",
        "zare": "#ffd24d",
        "trida": "zakladni-skola",
    },
    {
        "nazev": "Střední školy",
        "skoly": nacti_bezpecne(nacti_skoly, "ss.geojson", []),
        "tvary": nacti_bezpecne(nacti_tvary, "ss_tvary.geojson", {}),
        "barva": "#4cd6a0",
        "obrys": "#e3fff3",
        "zare": "#3dffb0",
        "trida": "stredni-skola",
    },
]

DNY = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]
MESICE = {
    "01": "leden", "02": "únor", "03": "březen", "04": "duben",
    "05": "květen", "06": "červen", "07": "červenec", "08": "srpen",
    "09": "září", "10": "říjen", "11": "listopad", "12": "prosinec",
}

# Všechny budovy UP mají stejnou světle modrou barvu
BARVA_BUDOV = "#86b6ef"


def nejvic(slovnik):
    """Klíč s nejvyšší hodnotou, nebo None."""
    return max(slovnik, key=slovnik.get) if slovnik else None


def popup_budovy(b):
    """HTML okénko s detaily budovy (po kliknutí)."""
    radky = [
        f"<b style='font-size:14px'>{b['name']}</b> <span style='opacity:.6'>({b['id']})</span>",
        f"Studenti v budově: <b>{b['students']}</b>",
        f"Z toho s výukou po setmění: <b>{b['dark_students']}</b> "
        f"({b['share_students']:.0%})",
        f"Hodin výuky po setmění: <b>{b['dark_occ']}</b> z {b['occ']} "
        f"({b['share_occ']:.1%})",
    ]

    if b["dark_occ"]:
        radky.append(
            f"Končí typicky <b>{b['median']:.0f} min</b> po setmění, "
            f"nejpozději {b['max']:.0f} min"
        )

        # Malý sloupcový graf: kolik výuky končí v kterou hodinu
        nejvyssi = max(b["hour"].values())
        sloupce = "".join(
            "<div style='display:flex;align-items:center;gap:6px;margin:2px 0'>"
            f"<span style='width:42px'>{hodina}:00</span>"
            f"<span style='display:inline-block;height:9px;border-radius:3px;"
            f"background:#2a78d6;width:{max(4, 120 * pocet / nejvyssi):.0f}px'></span>"
            f"<span style='opacity:.7'>{pocet}</span></div>"
            for hodina, pocet in sorted(b["hour"].items(), key=lambda x: int(x[0]))
        )
        radky.append(f"<div style='margin-top:6px'><b>Kdy výuka po setmění končí</b>{sloupce}</div>")

        den = nejvic(b["wd"])
        mesic = nejvic(b["month"])
        dny = ", ".join(f"{d} {b['wd'][d]}" for d in DNY if d in b["wd"])
        radky.append(f"Podle dnů: {dny}")
        if den and mesic:
            radky.append(
                f"Nejvíc ve dnech: <b>{den}</b>, nejvíc v měsíci: "
                f"<b>{MESICE[mesic[5:]]} {mesic[:4]}</b>"
            )
    else:
        radky.append("Žádná výuka nekončí po setmění.")

    return "<div style='font-size:12.5px;line-height:1.5'>" + "<br>".join(radky) + "</div>"


ZDROJ_POCIT = "Pocit nebezpečí"
ZDROJ_VORONOI = "Oblasti kriminality"
ZDROJ_STUDENT = "Školy"

# Body "za tmy" (fialové) – na tmavé mapě o trochu světlejší odstín, aby byly líp vidět
BARVA_TMA = "#7B61A8"
BARVA_TMA_TMAVA_MAPA = "#A48BDA"


# Navigace – rozbaluje se tlačítkem s ikonou v bočním panelu
if "navigace_panel_otevreny" not in st.session_state:
    st.session_state.navigace_panel_otevreny = False


def prepni_panel_navigace():
    st.session_state.navigace_panel_otevreny = not st.session_state.navigace_panel_otevreny


@st.cache_data(show_spinner=False)
def ikona_jako_url(soubor):
    """Obrázek jako data: URL, aby šel použít v CSS (bez servírování souborů)."""
    with open(soubor, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")


st.markdown(
    f"""
    <style>
    /* Tlačítko navigace v bočním panelu: ikona + nápis + šipka */
    .st-key-navigace_tlacitko button {{
        height: 52px;
        justify-content: flex-start;
        padding: 0 14px 0 52px;
        background: url("{ikona_jako_url("Ikony/NavigaceMain.png")}") 12px center / 30px no-repeat,
                    linear-gradient(135deg, rgba(155, 127, 212, 0.22), rgba(155, 127, 212, 0.08));
        border-color: #5a4387;
    }}
    .st-key-navigace_tlacitko button {{
        position: relative;
    }}
    .st-key-navigace_tlacitko button > div {{
        justify-content: flex-start;
    }}
    .st-key-navigace_tlacitko button p {{
        font-size: 1rem;
        font-weight: 700;
    }}
    .st-key-navigace_tlacitko button::after {{
        content: "›";
        position: absolute;
        right: 16px;
        top: 50%;
        transform: translateY(-55%);
        font-size: 1.6rem;
        opacity: 0.7;
    }}

    .st-key-navigace_tlacitko button::after {{
        transition: transform 0.15s ease;
    }}

    /* Navigace se rozbalí přímo pod tlačítkem v bočním panelu – nezakrývá mapu,
       vyhledávání ani filtry (ty jsou dál pod ní) */
    .st-key-navigace_panel {{
        margin-top: -1rem;
        padding: 12px 14px 14px 14px;
        background: rgba(155, 127, 212, 0.06);
        border: 1px solid #3b2a5c;
        border-top: none;
        border-radius: 0 0 12px 12px;
        animation: navigace-rozbalit 0.15s ease-out;
    }}
    @keyframes navigace-rozbalit {{
        from {{ opacity: 0; transform: translateY(-6px); }}
        to {{ opacity: 1; transform: none; }}
    }}
    .st-key-navigace_panel .stButton > button {{
        white-space: nowrap;
    }}
    /* Bez nápovědy „Press Enter to apply" u políčka s odstupem */
    .st-key-navigace_panel [data-testid="InputInstructions"] {{
        display: none;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Boční panel – nastavení mapy, hned pod nadpisem tlačítko navigace
st.sidebar.title("Nastavení mapy")
st.sidebar.button(
    "Navigace",
    key="navigace_tlacitko",
    on_click=prepni_panel_navigace,
    use_container_width=True,
)
# Místo pro rozbalenou navigaci hned pod tlačítkem. Obsah se do něj vykreslí až
# později (potřebuje body vybrané filtry níž), na obrazovce je ale tady.
panel_navigace = st.sidebar.container(key="navigace_panel")


def nadpis_sekce(text):
    st.sidebar.markdown(f'<div class="sekce">{text}</div>', unsafe_allow_html=True)


nadpis_sekce("Vlastní body")


# Tlačítko pro zapnutí / vypnutí režimu přidávání bodu
if not st.session_state.rezim_pridani:

    if st.sidebar.button("Přidat nový bod", use_container_width=True):
        st.session_state.rezim_pridani = True
        # Výběr startu/cíle navigace se tím ukončí, aby klik do mapy nebyl dvojznačný
        st.session_state["navigace_vybirany_bod"] = None
        st.rerun()

else:

    st.sidebar.info("Režim přidávání je zapnutý. Klikněte do mapy.")

    if st.sidebar.button("Zrušit přidávání", use_container_width=True):
        st.session_state.rezim_pridani = False
        st.rerun()


# Boční panel – výběr zdroje dat
nadpis_sekce("Data")
# Vrstvy jdou libovolně kombinovat (zaškrtávátka místo jedné volby)
st.sidebar.markdown("Vrstvy v mapě:")
zobrazit_pocit = st.sidebar.checkbox(ZDROJ_POCIT, value=True)
zobrazit_voronoi = st.sidebar.checkbox(ZDROJ_VORONOI, value=False)
studentsky_rezim = st.sidebar.checkbox(
    ZDROJ_STUDENT,
    value=False,
    help="Budovy UP s výukou končící po setmění a základní a střední školy.",
)
# Vlastní body patří k pocitu nebezpečí – zobrazí se jen s ním
zobrazit_vlastni_body = zobrazit_pocit


# Boční panel – filtrování (platí pro pocit nebezpečí i pro kriminalitu)
nadpis_sekce("Filtry")
vyber = st.sidebar.selectbox(
    "Světelné podmínky:",
    ["Za tmy", "Za světla", "Nerozlišovat"],
    index=2,
)

# Tmavá mapa (dark mode) je při filtru "Za tmy"
tmava_mapa = vyber == "Za tmy"

vybrane_kategorie = st.sidebar.multiselect(
    "Kategorie důvodu:",
    V_NABIDCE,
    format_func=NAZVY.get,
    placeholder="Všechny kategorie"
)

# Osvětlení ulic jde zapnout jen při filtru "Za tmy"
if vyber == "Za tmy":
    zobrazit_osvetleni = st.sidebar.checkbox(
        "Osvětlení ulic",
        value=True,
        disabled=osvetleni is None,
        help=(
            "Ulice obarvené podle počtu lamp v okolí."
            if osvetleni is not None
            else "Chybí soubor osvetleni_ulic.geojson – spusťte priprav_osvetleni_ulic.py."
        ),
    )
else:
    zobrazit_osvetleni = False

# Pozor: HTML bez odsazení a prázdných řádků, jinak ho Streamlit ukáže jako kód
legenda_osvetleni = (
    '<div class="legenda-nadpis" style="margin-top:12px;">Osvětlení ulic</div>'
    '<div class="legenda-osvetleni"></div>'
    '<div class="legenda-osvetleni-popis">'
    "<span>neosvětlené</span><span>osvětlené</span>"
    "</div>"
    if zobrazit_osvetleni
    else ""
)

legenda_budovy = (
    '<div class="legenda-polozka">'
    f'<span class="legenda-tecka" style="background:{BARVA_BUDOV}; border-radius:3px;"></span>'
    " Budovy UP"
    "</div>"
    + "".join(
        '<div class="legenda-polozka">'
        f'<span class="legenda-tecka" style="background:{t["barva"]}; border-radius:3px;"></span>'
        f' {t["nazev"]}'
        "</div>"
        for t in TYPY_SKOL
        if t["skoly"]
    )
    if studentsky_rezim
    else ""
)


# Legenda – vykreslí se jako banner v pravém horním rohu mapy
legenda_html = (
    '<div class="legenda">'
    '<div class="legenda-nadpis">Legenda</div>'
    '<div class="legenda-polozka">'
    '<span class="legenda-tecka" style="background:'
    + (BARVA_TMA_TMAVA_MAPA if tmava_mapa else BARVA_TMA)
    + ';"></span> Tma'
    "</div>"
    '<div class="legenda-polozka">'
    '<span class="legenda-tecka" style="background:#E5A000;"></span> Světlo'
    "</div>"
    '<div class="legenda-polozka">'
    '<span class="legenda-tecka" style="background:green;"></span> Vlastní body'
    "</div>"
    '<div class="legenda-polozka">'
    '<span class="legenda-tecka" style="background:rgba(214,69,65,0.35); '
    'border-color:#D64541; border-radius:3px;"></span> '
    "Oblasti kriminality (tmavší = více činů)"
    "</div>"
    + legenda_budovy
    + legenda_osvetleni
    + "</div>"
)


# Výběr bodů podle filtru
if vyber == "Za tmy":
    df_mapa = df[df["typ_ident"] == "a"]

elif vyber == "Za světla":
    df_mapa = df[df["typ_ident"] == "b"]

else:
    df_mapa = df

if vybrane_kategorie:
    df_mapa = df_mapa[
        df_mapa["kategorie_duvodu"].apply(
            lambda kategorie: any(
                vybrana in kategorie
                for vybrana in vybrane_kategorie
            )
        )
    ]

# Když je vrstva pocitu nebezpečí vypnutá, její body se nezobrazí
if not zobrazit_pocit:
    df_mapa = df.iloc[0:0]


# Stejné filtry pro události kriminality
df_krim_mapa = df_krim

if vyber == "Za tmy":
    df_krim_mapa = df_krim_mapa[df_krim_mapa["typ_ident"] == "a"]

elif vyber == "Za světla":
    df_krim_mapa = df_krim_mapa[df_krim_mapa["typ_ident"] == "b"]

if vybrane_kategorie:
    df_krim_mapa = df_krim_mapa[
        df_krim_mapa["kategorie_duvodu"].apply(
            lambda kategorie: any(
                vybrana in kategorie
                for vybrana in vybrane_kategorie
            )
        )
    ]


# Tvary oblastí se nemění – uloží se jednou do složky static a prohlížeč si je
# stáhne jen jednou. S filtry se mění jen čísla v oblastech (viz níže).
@st.cache_data(show_spinner=False)
def soubor_tvaru_oblasti():
    return uloz_staticky_soubor("voronoi_oblasti.json", na_json({
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": f["geometry"], "properties": {}}
            for f in voronoi_geojson["features"]
        ],
    }))


# Počet činů a nejčastější skupiny v každé oblasti (ve stejném pořadí jako tvary).
# Výsledek se pamatuje pro každou kombinaci filtrů, takže se při klikání do mapy
# nepřepočítává. Tabulka `_df_krim_mapa` je daná filtry (vyber, kategorie),
# proto ji Streamlit nemusí hashovat (podtržítko).
@st.cache_data(show_spinner=False)
def oblasti_kriminality_json(vyber, kategorie, _df_krim_mapa):
    pocty_oblasti = _df_krim_mapa["oblast"].value_counts().to_dict()
    skupiny_oblasti = (
        _df_krim_mapa.explode("skupiny")
        .groupby("oblast")["skupiny"]
        .value_counts()
    )
    max_pocet = max(pocty_oblasti.values(), default=0)

    oblasti = []
    for feature in voronoi_geojson["features"]:
        oblast = feature["properties"]["id"]
        pocet = int(pocty_oblasti.get(oblast, 0))

        if pocet:
            nejcastejsi = skupiny_oblasti[oblast].head(5)
            prehled = "<br>".join(
                f"{skupina}: {kolik}" for skupina, kolik in nejcastejsi.items()
            )
        else:
            prehled = "žádné činy pro zvolený filtr"

        oblasti.append({
            "pocet": pocet,
            "podil": pocet / max_pocet if max_pocet else 0,
            "prehled": prehled,
        })

    return na_json(oblasti)


# Navigace (pracuje přímo v hlavní mapě) v rozbalovací sekci pod tlačítkem „Navigace".
# Vykresluje se vždy, i když je sekce sbalená (jen se skryje CSS) – trasa se tak
# dál počítá a zobrazuje v mapě. Vyhýbá se přesně bodům, které jsou podle filtrů
# vidět v mapě; po změně filtrů nebo odstupu se trasa sama přepočítá.
with panel_navigace:
    if st.session_state.navigace_panel_otevreny:
        # Šipka na tlačítku míří dolů, když je navigace rozbalená
        st.markdown(
            "<style>.st-key-navigace_tlacitko button::after "
            "{ transform: translateY(-55%) rotate(90deg) !important; }"
            ".st-key-navigace_tlacitko button { border-radius: 10px 10px 0 0 !important; }</style>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<style>.st-key-navigace_panel { display: none !important; }</style>",
            unsafe_allow_html=True,
        )
    st.caption("Trasa se vyhýbá nebezpečným místům, která jsou podle filtrů vidět v mapě.")
    # Vlastní body se pro navigaci převedou do stejné podoby jako body z ankety
    vlastni_pro_navigaci = [
        {
            "latitude": bod["geometry"]["coordinates"][1],
            "longitude": bod["geometry"]["coordinates"][0],
            "desc_detail_duvod": bod.get("properties", {}).get("duvod", ""),
            "typ_nazev": bod.get("properties", {}).get("nazev", ""),
        }
        for bod in st.session_state.moje_body
        if zobrazit_vlastni_body and (
            not vybrane_kategorie
            or set(vybrane_kategorie) & set(bod.get("properties", {}).get("kategorie", []))
        )
    ]
    mista_navigace = priprav_mista(df_mapa.to_dict("records") + vlastni_pro_navigaci)
    route = ovladani_navigace(mista_navigace, posun_listy=False)

# Výběr startu/cíle a přidávání bodu se navzájem vylučují
if st.session_state.get("navigace_vybirany_bod") and st.session_state.rezim_pridani:
    st.session_state.rezim_pridani = False
    st.rerun()


# Vyskakovací okénko pro nový bod
@st.dialog("Označit nové místo")
def okno_pro_bod(lat, lon):

    st.caption(
        f"Souřadnice: {lat:.6f}, "
        f"{lon:.6f}"
    )

    nazev = st.text_input(
        "Název problému",
        placeholder="Např. Tmavý podchod"
    )

    duvod = st.text_area(
        "Popis problému",
        placeholder="Popište, proč se zde necítíte bezpečně..."
    )

    if st.button("Uložit bod"):

        if nazev.strip() and duvod.strip():

            # AI zařadí bod do kategorií podle názvu a popisu
            with st.spinner("AI třídí bod do kategorií…"):
                kategorie_bodu = zarad_pomoci_ai(nazev.strip(), duvod.strip())

            supabase.table("vlastni_body").insert({
                "nazev": nazev.strip(),
                "duvod": duvod.strip(),
                "lat": lat,
                "lon": lon,
                "kategorie": kategorie_bodu or []
            }).execute()

            # Hláška, která se ukáže po uložení
            if kategorie_bodu is None:
                st.session_state.zprava_ai = "⚠️ Bod uložen bez kategorie – AI teď není dostupná."
            elif kategorie_bodu:
                st.session_state.zprava_ai = "✅ Bod uložen. AI ho zařadila do: " + ", ".join(NAZVY[k] for k in kategorie_bodu)
            else:
                st.session_state.zprava_ai = "Bod uložen. AI nenašla žádnou odpovídající kategorii."

            st.session_state.moje_body = nacti_body()

            # Po uložení se režim přidávání vypne
            st.session_state.rezim_pridani = False
            st.rerun()

        else:
            st.warning("Vyplňte název i popis problému.")


# Hláška od AI po uložení bodu (zobrazí se jednou)
if "zprava_ai" in st.session_state:
    st.toast(st.session_state.pop("zprava_ai"))


# Mapa přes celou šířku
st.markdown(
    '<div class="hlavicka">'
    # Nadpis a popis v jednom bloku – popis je pod nadpisem, ne vedle něj
    '<div class="hlavicka-text">'
    "<h1>NEBEZPEČNÁ MÍSTA V OLOMOUCI</h1>"
    "<p>Mapa míst, kde se lidé necítí bezpečně, kriminality a osvětlení ulic"
    " – naplánujte si bezpečnější cestu.</p>"
    "</div>"
    "</div>",
    unsafe_allow_html=True
)

# ---------------------------------------------------------------------------------
# MAPA
# Základní mapa je při každém běhu STEJNÁ (podklad, vlastní body, nástroj na úpravy),
# proto ji streamlit-folium po prvním načtení už nepřekresluje. Vše, co se mění
# s filtry (body, oblasti, osvětlení, budovy, trasa, tmavý režim), jsou samostatné
# vrstvy v seznamu `vrstvy`, které se předají do st_folium(feature_group_to_add=...)
# a v prohlížeči se jen vymění. Mapa tak zůstane na místě i s přiblížením.
# ---------------------------------------------------------------------------------

mapa = folium.Map(
    location=[49.5938, 17.2509],
    zoom_start=12,
    tiles=None,
    # Bez ovládání klávesnicí: Leaflet si jinak při kliknutí do mapy vezme fokus
    # a prohlížeč stránku odscrolluje, aby byla mapa celá vidět – stránka poskočí
    # a klik (např. výběr startu) dopadne jinam, než uživatel mířil.
    keyboard=False,
)

# Podklad mapy (OpenStreetMap). Tmavý režim ("Za tmy") se zapíná jen CSS třídou
# na mapě (viz PrepinacMapy níže) – převrátí barvy dlaždic, body a čáry zůstanou.
folium.TileLayer("OpenStreetMap").add_to(mapa)

mapa.get_root().header.add_child(folium.Element(
    "<style>"
    ".tmava-mapa .leaflet-tile-pane {"
    " filter: invert(100%) hue-rotate(180deg) brightness(95%) contrast(90%);"
    "}"
    # Vlastní body a nástroj na jejich úpravu se skryjí, když nejsou zapnuté
    ".skryt-vlastni .vlastni-bod { display: none !important; }"
    # Při výběru kategorie se zelené body skryjí a ukážou se jen ty z vybrané kategorie
    ".filtr-kategorii .vlastni-bod { display: none; }"
    + "".join(
        f".ukaz-{k.replace('_', '-')} .vlastni-bod.kat-{k.replace('_', '-')} {{ display: inline; }}"
        for k in V_NABIDCE
    )
    +
    # Modrá záře kolem budov UP, aby byly na tmavé mapě dobře vidět
    ".budova-up { filter: drop-shadow(0 0 4px #4fb3ff) drop-shadow(0 0 8px #4fb3ff); }"
    # Stejná záře kolem škol, v barvě daného typu školy
    + "".join(
        f".{t['trida']} {{ filter: drop-shadow(0 0 4px {t['zare']}) drop-shadow(0 0 8px {t['zare']}); }}"
        for t in TYPY_SKOL
    )
    +
    "</style>"
))


# Skupina pro vlastní body uživatelů – je v základní mapě vždy (nástroj na úpravy
# potřebuje pevnou skupinu); když se nemají zobrazit, jen se skryjí přes CSS.
uzivatelske_body = folium.FeatureGroup(
    name="Vlastní body"
)

for index, bod in enumerate(st.session_state.moje_body):

    souradnice = bod["geometry"]["coordinates"]

    lon = souradnice[0]
    lat = souradnice[1]

    vlastnosti = bod.get("properties", {})

    nazev = vlastnosti.get(
        "nazev",
        f"Vlastní bod {index + 1}"
    )

    duvod = vlastnosti.get(
        "duvod",
        "Vlastní označené místo"
    )

    folium.CircleMarker(
        location=[lat, lon],
        radius=5,
        color="green",
        fill=True,
        fill_color="green",
        fill_opacity=0.8,
        class_name="vlastni-bod " + " ".join(
            "kat-" + k.replace("_", "-") for k in vlastnosti.get("kategorie", [])
        ),
        tooltip=nazev,
        popup=duvod
    ).add_to(uzivatelske_body)

uzivatelske_body.add_to(mapa)



# --- Vrstvy, které se mění (pořadí = pořadí vykreslení, poslední je nahoře) --------
vrstvy = []

# Přepínač tmavého režimu a viditelnosti vlastních bodů
prepinac = folium.FeatureGroup(name="Nastavení mapy")
PrepinacMapy(
    tmava_mapa=tmava_mapa,
    skryt_vlastni=not zobrazit_vlastni_body,
    filtr_kategorii=bool(vybrane_kategorie),
    **{f"ukaz_{k}": k in vybrane_kategorie for k in V_NABIDCE},
).add_to(prepinac)
vrstvy.append(prepinac)


# Voronoiovy oblasti (kriminalita) – jako první, aby body ležely nad nimi.
# Čím víc činů (po filtrech), tím sytější červená.
if zobrazit_voronoi:
    vrstva_oblasti = folium.FeatureGroup(name="Oblasti kriminality")
    GeoJsonZeSouboru(
        soubor_tvaru_oblasti(),
        vlastnosti_json=oblasti_kriminality_json(vyber, tuple(vybrane_kategorie), df_krim_mapa),
        pane="oblasti_kriminality",
        pane_z=350,  # nejníž – pod osvětlením i body
        moznosti_js="""{
            style: function (f) {
                return {color: "#D64541", weight: 1, fillColor: "#D64541",
                        fillOpacity: 0.03 + 0.6 * f.properties.podil};
            },
            onEachFeature: function (f, vrstva) {
                vrstva.bindTooltip(
                    "<b>Počet činů:</b> " + f.properties.pocet +
                    "<br><b>Nejčastější:</b><br>" + f.properties.prehled,
                    {sticky: true}
                );
                vrstva.on("mouseover", function () { vrstva.setStyle({weight: 3}); });
                vrstva.on("mouseout", function () { vrstva.setStyle({weight: 1}); });
            }
        }""",
    ).add_to(vrstva_oblasti)
    vrstvy.append(vrstva_oblasti)


# Osvětlení ulic (nad oblastmi kriminality, pod body, aby body šly dál kliknout)
if zobrazit_osvetleni and osvetleni is not None:
    vrstva_osvetleni = folium.FeatureGroup(name="Osvětlení ulic")
    GeoJsonZeSouboru(
        osvetleni,
        pane="osvetleni_ulic",
        pane_z=360,  # nad oblastmi, pod body a trasou
        moznosti_js="""{
            interactive: false,
            style: function (f) {
                var u = f.properties.uroven;
                return {color: %s[u], weight: u === 4 ? 4 : 3, opacity: 0.9, lineCap: "round"};
            }
        }""" % na_json(barvy_osvetleni),
    ).add_to(vrstva_osvetleni)
    vrstvy.append(vrstva_osvetleni)


# Nebezpečná místa jako JEDNA vrstva (dřív ~1000 samostatných značek = pomalé).
# Body se posílají jen jako [lon, lat, důvod, barva] – méně dat než celý GeoJSON.
if zobrazit_pocit and len(df_mapa):
    body = [
        [
            round(lon, 6),
            round(lat, 6),
            duvod or "(bez popisu)",
            # Na tmavé mapě jsou fialové body o trochu světlejší
            BARVA_TMA_TMAVA_MAPA if tmava_mapa and barva == BARVA_TMA else barva,
        ]
        for lat, lon, duvod, barva in zip(
            df_mapa["latitude"],
            df_mapa["longitude"],
            df_mapa["desc_detail_duvod"],
            df_mapa["barva"],
        )
    ]
    vrstva_bodu = folium.FeatureGroup(name="Nebezpečná místa")
    RychlyGeoJson(
        na_json({
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [b[0], b[1]]},
                 "properties": {"d": b[2], "b": b[3]}}
                for b in body
            ],
        }),
        """{
            pointToLayer: function (f, poloha) {
                return L.circleMarker(poloha, {radius: 5, color: f.properties.b,
                    fillColor: f.properties.b, fill: true, fillOpacity: 0.8});
            },
            onEachFeature: function (f, vrstva) {
                // textContent = text od lidí se nikdy nevykoná jako HTML
                var popisek = document.createElement("div");
                popisek.textContent = f.properties.d;
                vrstva.bindTooltip(popisek);
                var okno = document.createElement("div");
                okno.textContent = f.properties.d;
                vrstva.bindPopup(okno);
            }
        }""",
    ).add_to(vrstva_bodu)
    vrstvy.append(vrstva_bodu)


# Budovy UP (jen se zapnutou vrstvou Školy) – obarvený tvar budovy, po najetí myší jen název
if studentsky_rezim and budovy:
    vrstva_budov = folium.FeatureGroup(name="Budovy UP")

    for b in budovy:
        tooltip = folium.Tooltip(f"<b>{b['name']}</b>", sticky=True)
        popup = folium.Popup(popup_budovy(b), max_width=320)

        if b["id"] in tvary_budov:
            folium.GeoJson(
                {"type": "Feature", "geometry": tvary_budov[b["id"]], "properties": {}},
                class_name="budova-up",
                style_function=lambda _: {
                    # Světlý silný obrys – i malá budova je vidět při oddálené mapě
                    "color": "#e6f4ff",
                    "weight": 3,
                    "fillColor": BARVA_BUDOV,
                    "fillOpacity": 0.95,
                },
                highlight_function=lambda _: {"weight": 5, "color": "#ffffff", "fillOpacity": 1},
                tooltip=tooltip,
                popup=popup,
            ).add_to(vrstva_budov)
        else:
            # Záloha, kdyby k budově chyběl tvar
            folium.CircleMarker(
                location=[b["lat"], b["lon"]],
                radius=8,
                color="#e6f4ff",
                weight=3,
                fill=True,
                fill_color=BARVA_BUDOV,
                fill_opacity=0.95,
                class_name="budova-up",
                tooltip=tooltip,
                popup=popup,
            ).add_to(vrstva_budov)

    vrstvy.append(vrstva_budov)


def popis_skoly(s):
    """HTML s detaily jedné školy (do okénka po kliknutí)."""
    radky = [f"<b style='font-size:14px'>{html.escape(s['nazev'])}</b>"]
    if s["typ"]:
        radky.append(html.escape(s["typ"]))
    if s["adresa"]:
        radky.append(html.escape(s["adresa"]))
    if s["kapacita"]:
        radky.append(f"Kapacita: <b>{s['kapacita']}</b> žáků")
    if s["web"]:
        web = html.escape(s["web"])
        odkaz = web if web.startswith("http") else f"https://{web}"
        radky.append(f"<a href='{odkaz}' target='_blank'>{web}</a>")
    return "<br>".join(radky)


def vrstva_skol(typ):
    """Vrstva s obarvenými obrysy budov škol jednoho typu (jako u budov UP)."""
    vrstva = folium.FeatureGroup(name=typ["nazev"])
    styl = {
        "color": typ["obrys"],
        "weight": 3,
        "fillColor": typ["barva"],
        "fillOpacity": 0.95,
    }

    # Víc škol (míst výuky) může být v jedné budově – seskupí se podle obrysu
    skupiny = {}
    for s in typ["skoly"]:
        tvar = typ["tvary"].get(s["id"])
        klic = json.dumps(tvar, sort_keys=True) if tvar else f"bod-{s['lat']}-{s['lon']}"
        skupiny.setdefault(klic, (tvar, []))[1].append(s)

    for tvar, skoly_v_budove in skupiny.values():
        # Stejná škola na stejné adrese se v okénku neopakuje
        unikatni = list({(s["nazev"], s["adresa"]): s for s in skoly_v_budove}.values())
        tooltip = folium.Tooltip(
            "<br>".join(f"<b>{html.escape(s['nazev'])}</b>" for s in unikatni), sticky=True
        )
        popup = folium.Popup(
            "<div style='font-size:12.5px;line-height:1.5'>"
            + "<hr style='margin:6px 0'>".join(popis_skoly(s) for s in unikatni)
            + "</div>",
            max_width=320,
        )

        if tvar:
            folium.GeoJson(
                {"type": "Feature", "geometry": tvar, "properties": {}},
                class_name=typ["trida"],
                style_function=lambda _: styl,
                highlight_function=lambda _: {"weight": 5, "color": "#ffffff", "fillOpacity": 1},
                tooltip=tooltip,
                popup=popup,
            ).add_to(vrstva)
        else:
            # Záloha, kdyby ke škole chyběl tvar
            s = unikatni[0]
            folium.CircleMarker(
                location=[s["lat"], s["lon"]],
                radius=8,
                color=styl["color"],
                weight=3,
                fill=True,
                fill_color=styl["fillColor"],
                fill_opacity=0.95,
                class_name=typ["trida"],
                tooltip=tooltip,
                popup=popup,
            ).add_to(vrstva)

    return vrstva


# Základní a střední školy (jen se zapnutou vrstvou Školy)
if studentsky_rezim:
    for typ in TYPY_SKOL:
        if typ["skoly"]:
            vrstvy.append(vrstva_skol(typ))


# Start, cíl a trasa navigace (nahoře nad vším)
vrstvy.append(vrstva_navigace(route))


# Zobrazení mapy a získání kliknutí.
# Vyhledávání trasy (Odkud / Kam) leží ve stejném obalu a zobrazí se přes levý horní roh mapy.
with st.container(key="mapa_obal"):

    with st.container(key="legenda_mapy"):
        st.markdown(legenda_html, unsafe_allow_html=True)

    output = st_folium(
        mapa,
        width=None,
        height=650,
        use_container_width=True,
        feature_group_to_add=vrstvy,
        returned_objects=["last_clicked"],
        key="mapa"
    )

    # Vyhledávání (Odkud / Kam) je AŽ ZA mapou: kdyby bylo před ní, jeho objevení by
    # mapu v obalu posunulo o pozici a Streamlit by ji načetl celou znovu.
    # Na obrazovce je i tak nad mapou (CSS position: absolute).
    vyhledavaci_panel()


# Zpracování kliknutí na mapu – výběr startu/cíle nebo přidání bodu
kliknuti = output.get("last_clicked")

if kliknuti:

    podpis = (
        round(kliknuti["lat"], 6),
        round(kliknuti["lng"], 6)
    )

    if podpis != st.session_state.posledni_klik:

        st.session_state.posledni_klik = podpis

        if zpracuj_klik_navigace(kliknuti):
            st.rerun()

        elif st.session_state.rezim_pridani:
            st.session_state.cekajici_bod = [
                kliknuti["lat"],
                kliknuti["lng"]
            ]


# Řádek se statistikami pod mapou
statistiky = [
    *(
        [
            ("Budovy UP", f"{len(budovy)}"),
            # (Studenty přes budovy nesčítáme – jeden student chodí do více budov)
            (
                "Výuka po setmění",
                f"{sum(1 for b in budovy if b['dark_students'])} <small>budov</small>",
            ),
            *((t["nazev"], f"{len(t['skoly'])}") for t in TYPY_SKOL if t["skoly"]),
        ]
        if studentsky_rezim
        else []
    ),
    ("Zobrazená místa", f"{len(df_mapa)} <small>/ {len(df)}</small>"),
    ("Vlastní body", f"{len(st.session_state.moje_body)}"),
]

if zobrazit_voronoi:
    statistiky.append(
        ("Činy (kriminalita)", f"{len(df_krim_mapa)} <small>/ {len(df_krim)}</small>")
    )

if route is not None:
    souhrn = route["routes"][0]["summary"]
    statistiky.append(("Délka trasy", f"{souhrn['distance'] / 1000:.2f} <small>km</small>"))
    statistiky.append(("Doba chůze", f"{round(souhrn['duration'] / 60)} <small>min</small>"))

st.markdown(
    '<div class="statistiky">'
    + "".join(
        f'<div class="karta"><div class="karta-popis">{popis}</div>'
        f'<div class="karta-hodnota">{hodnota}</div></div>'
        for popis, hodnota in statistiky
    )
    + "</div>",
    unsafe_allow_html=True
)


# Srovnání nejkratší a nejbezpečnější cesty (srovnani_tras.py) – když je zvolený start i cíl.
# Používá stejný start, cíl a nebezpečná místa jako navigace (tedy i filtry a vlastní body).
start_navigace = st.session_state.get("navigace_start")
cil_navigace = st.session_state.get("navigace_cil")
if start_navigace is not None and cil_navigace is not None:
    if st.toggle(
        "Porovnat nejkratší a nejbezpečnější cestu",
        key="srovnani_zapnuto",
        help="Ukáže vedle sebe nejkratší trasu a trasu, která se nejvíc vyhne "
             "nebezpečným místům, a o kolik se liší čas a bezpečnost.",
    ):
        nastaveni_odstup, nastaveni_zajizdka, nastaveni_svetlo = st.columns(3)
        srovnani_odstup = nastaveni_odstup.slider(
            "Odstup od nebezpečných míst (m)", 10, 150, 50, step=10, key="srovnani_odstup",
            help="Místo se počítá jako ‚u trasy‘, když je od ní blíž než tato vzdálenost.",
        )
        srovnani_zajizdka = nastaveni_zajizdka.slider(
            "Maximální zajížďka (%)", 10, 150, 60, step=10, key="srovnani_zajizdka",
            help="Bezpečná trasa nesmí být delší než nejkratší o víc než toto procento.",
        )
        srovnani_svetlo = nastaveni_svetlo.checkbox(
            "Obarvit trasy podle osvětlení ulic", value=vyber == "Za tmy",
            key="srovnani_svetlo",
        )
        zobraz_srovnani(
            tuple(start_navigace),
            tuple(cil_navigace),
            [
                {
                    "lat": m["souradnice"][0],
                    "lon": m["souradnice"][1],
                    "typ": m["nazev mista"],
                    "duvod": m["problem mista"],
                }
                for m in mista_navigace
            ],
            za_tmy=vyber != "Za světla",
            odstup=srovnani_odstup,
            max_zajizdka=srovnani_zajizdka,
            podle_svetla=srovnani_svetlo,
            klic="hlavni_srovnani",
            tmava=tmava_mapa,
        )


# Seznam vlastních bodů (sbalitelný, aby nezabíral místo)
with st.expander(f"Seznam vlastních bodů ({len(st.session_state.moje_body)})"):

    for index, bod in enumerate(st.session_state.moje_body):

        souradnice = bod["geometry"]["coordinates"]

        vlastnosti = bod.get("properties", {})

        nazev = vlastnosti.get(
            "nazev",
            f"Vlastní bod {index + 1}"
        )

        duvod = vlastnosti.get(
            "duvod",
            "Bez popisu"
        )

        st.write(f"**{nazev}** – {duvod}")

        # Místo souřadnic adresa / ulice (zaokrouhleno, ať se pamatuje i po malém posunu bodu)
        adresa = adresa_bodu(round(souradnice[1], 5), round(souradnice[0], 5))
        st.caption(f"📍 {adresa}" if adresa else "📍 Adresu se nepodařilo zjistit")

    if len(st.session_state.moje_body) == 0:
        st.info("Zatím nebyl vytvořen žádný vlastní bod.")


# Otevření okénka po kliknutí na mapu
if st.session_state.cekajici_bod is not None:

    lat_bodu, lon_bodu = st.session_state.cekajici_bod

    # Vynulujeme hned, aby se okno znovu neotevřelo po zavření křížkem
    st.session_state.cekajici_bod = None
    
    okno_pro_bod(lat_bodu, lon_bodu)
