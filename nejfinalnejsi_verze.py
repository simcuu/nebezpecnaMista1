import streamlit as st
import folium
from streamlit_folium import st_folium
import json
import pandas as pd
from folium.plugins import Draw
from supabase import create_client
from navigace_test4 import (
    ovladani_navigace,
    priprav_mista,
    vykresli_navigaci,
    vyhledavaci_panel,
    zpracuj_klik_navigace,
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

    /* Menší horní odsazení stránky, aby nadpis byl výš */
    .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: 3.5rem !important;
        padding-bottom: 2rem !important;
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
    .hlavicka h1 {
        margin: 0 !important;
        padding: 0 !important;
        font-size: clamp(1.3rem, 2.8vw, 2.2rem) !important;
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

    .legenda {
        background: rgba(155, 127, 212, 0.08);
        border: 1px solid #2e2442;
        border-radius: 12px;
        padding: 12px 16px;
        margin: 4px 0 12px 0;
        font-size: 0.9rem;
    }
    .legenda-nadpis {
        font-weight: 600;
        margin-bottom: 8px;
    }
    .legenda-polozka {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 7px 0;
    }
    .legenda-tecka {
        width: 18px;
        height: 18px;
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
        .select("id,nazev,duvod,lat,lon")
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
                "duvod": radek["duvod"]
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


kategorie_slov = {
    "Lidé a chování": (
        "bezdomov", "opil", "lidé", "lidi", "lidí", "lidem",
        "lidech", "ľud", "člověk", "osob", "agres", "podezř",
        "narkom"
    ),
    "Doprava a provoz": (
        "doprav", "provoz", "auto", "autobus", "silnic", "křižovat",
        "přechod", "chodník", "tramvaj", "vlak", "cykl"
    ),
    "Tma a osvětlení": ("tma", "tmav", "svět", "sviet", "osvět"),
    "Krádeže a majetek": ("krad", "krád", "zlod", "vloup", "podvod"),
}


def zarad_kategorie(duvod):
    text = duvod.casefold()
    if not text:
        return []

    kategorie = [
        kategorie
        for kategorie, slova in kategorie_slov.items()
        if any(slovo in text for slovo in slova)
    ]
    return kategorie or ["Ostatní"]


# Barvy podle kategorie
barvy = {
    "a": "#7B61A8",
    "b": "#E5A000",
}


# Načtení a zpracování GeoJSON souboru.
# @st.cache_data: soubor se přečte jen jednou, při dalších klicích se vezme hotová tabulka z paměti.
@st.cache_data
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
@st.cache_data
def nacti_voronoi():
    with open(
        "voronoi_olomouc.geojson",
        encoding="utf-8"
    ) as f:
        return json.load(f)


voronoi_geojson = nacti_voronoi()


# Osvětlení ulic – čáry po ulicích obarvené podle počtu lamp v okolí.
# Soubor vytváří skript priprav_osvetleni_ulic.py (z dat stažených stahni_arcgis_geojson.py).
@st.cache_data
def nacti_osvetleni():
    try:
        with open("osvetleni_ulic.geojson", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


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


@st.cache_data
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


@st.cache_data
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
        kategorie_duvodu=("kategorie", lambda k: bez_obecneho(k, "Ostatní")),
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
@st.cache_data
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
@st.cache_data
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
ZDROJ_OBA = "Obojí"
ZDROJ_STUDENT = "Studenti UP (večerní výuka)"

# Body "za tmy" (fialové) – na tmavé mapě o trochu světlejší odstín, aby byly líp vidět
BARVA_TMA = "#7B61A8"
BARVA_TMA_TMAVA_MAPA = "#A48BDA"


# Boční panel – nastavení mapy
st.sidebar.title("Nastavení mapy")


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
zdroj_dat = st.sidebar.radio(
    "Zdroj dat v mapě:",
    [ZDROJ_POCIT, ZDROJ_VORONOI, ZDROJ_OBA, ZDROJ_STUDENT]
)

studentsky_rezim = zdroj_dat == ZDROJ_STUDENT
zobrazit_pocit = zdroj_dat in (ZDROJ_POCIT, ZDROJ_OBA, ZDROJ_STUDENT)
zobrazit_voronoi = zdroj_dat in (ZDROJ_VORONOI, ZDROJ_OBA)


# Boční panel – filtrování (platí pro pocit nebezpečí i pro kriminalitu)
nadpis_sekce("Filtry")
if studentsky_rezim:
    # Studentská verze je vždy "za tmy": tmavá mapa, body za tmy a osvětlení ulic
    vyber = "Za tmy"
    st.sidebar.caption(
        "Studentská verze ukazuje mapu za tmy: budovy UP, kde výuka končí "
        "po setmění, nebezpečná místa za tmy a osvětlení ulic."
    )
else:
    vyber = st.sidebar.selectbox(
        "Světelné podmínky:",
        ["Za tmy", "Za světla", "Nerozlišovat"],
        index=2,
    )

# Tmavá mapa (dark mode) je při filtru "Za tmy"
tmava_mapa = vyber == "Za tmy"

vybrane_kategorie = st.sidebar.multiselect(
    "Kategorie důvodu:",
    [*kategorie_slov, "Ostatní"],
    placeholder="Všechny kategorie"
)

# Osvětlení ulic jde zapnout jen při filtru "Za tmy"
if vyber == "Za tmy":
    zobrazit_osvetleni = st.sidebar.checkbox(
        "Osvětlení ulic",
        # Ve studentské verzi je osvětlení na začátku vypnuté, jinak zapnuté
        value=not studentsky_rezim,
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
    if studentsky_rezim
    else ""
)


# Boční panel – legenda
st.sidebar.markdown(
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
    + "</div>",
    unsafe_allow_html=True
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

# Pokud jsou zvolena jen Voronoiova data, body pocitu nebezpečí se nezobrazí
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


# Počet činů a nejčastější skupiny v každé oblasti
pocty_oblasti = df_krim_mapa["oblast"].value_counts().to_dict()
skupiny_oblasti = (
    df_krim_mapa.explode("skupiny")
    .groupby("oblast")["skupiny"]
    .value_counts()
)
max_pocet = max(pocty_oblasti.values(), default=0)

oblasti_geojson = {
    "type": "FeatureCollection",
    "features": [],
}

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

    oblasti_geojson["features"].append({
        "type": "Feature",
        "geometry": feature["geometry"],
        "properties": {
            "oblast": oblast,
            "pocet": pocet,
            "podil": pocet / max_pocet if max_pocet else 0,
            "prehled": prehled,
        },
    })


# Boční panel – navigace (pracuje přímo v hlavní mapě)
with st.sidebar:
    nadpis_sekce("Navigace")
    route = ovladani_navigace(priprav_mista(df_mapa.to_dict("records")))

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

            supabase.table("vlastni_body").insert({
                "nazev": nazev.strip(),
                "duvod": duvod.strip(),
                "lat": lat,
                "lon": lon
            }).execute()

            st.session_state.moje_body = nacti_body()

            # Po uložení se režim přidávání vypne
            st.session_state.rezim_pridani = False
            st.rerun()

        else:
            st.warning("Vyplňte název i popis problému.")


# Mapa přes celou šířku
st.markdown(
    '<div class="hlavicka">'
    "<h1>NEBEZPEČNÁ MÍSTA V OLOMOUCI</h1>"
    "<p>Mapa míst, kde se lidé necítí bezpečně, kriminality a osvětlení ulic"
    " – naplánujte si bezpečnější cestu.</p>"
    "</div>"
    "</div>",
    unsafe_allow_html=True
)

mapa = folium.Map(
    location=[49.5938, 17.2509],
    zoom_start=12,
    tiles=None
)

# Podklad mapy (OpenStreetMap): při filtru "Za tmy" tmavý režim, jinak světlý režim.
# Tmavý režim vznikne převrácením barev dlaždic, body a čáry na mapě zůstanou ve svých barvách.
folium.TileLayer(
    "OpenStreetMap",
    class_name="tmava-mapa" if tmava_mapa else "svetla-mapa"
).add_to(mapa)

mapa.get_root().header.add_child(folium.Element(
    "<style>"
    ".tmava-mapa {"
    " filter: invert(100%) hue-rotate(180deg) brightness(95%) contrast(90%);"
    "}"
    "</style>"
))


# Voronoiovy oblasti (kriminalita) – vykreslují se jako první, aby body ležely nad nimi
if zobrazit_voronoi:
    # Čím víc činů (po filtrech), tím sytější červená
    folium.GeoJson(
        oblasti_geojson,
        name="Oblasti kriminality",
        style_function=lambda oblast: {
            "color": "#D64541",
            "weight": 1,
            "fillColor": "#D64541",
            "fillOpacity": 0.03 + 0.6 * oblast["properties"]["podil"],
        },
        highlight_function=lambda _: {
            "weight": 3,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["pocet", "prehled"],
            aliases=["Počet činů:", "Nejčastější:"]
        ),
    ).add_to(mapa)


# Osvětlení ulic (nad oblastmi kriminality, pod body, aby body šly dál kliknout)
if zobrazit_osvetleni and osvetleni is not None:
    folium.GeoJson(
        osvetleni,
        name="Osvětlení ulic",
        interactive=False,  # čáry nezachytávají kliknutí, takže přidávání bodů funguje dál
        style_function=lambda cara: {
            "color": barvy_osvetleni[cara["properties"]["uroven"]],
            "weight": 4 if cara["properties"]["uroven"] == 4 else 3,
            "opacity": 0.9,
            "lineCap": "round",
        },
    ).add_to(mapa)


# Vykreslení nebezpečných míst jako JEDNÉ GeoJSON vrstvy.
# (Dřív byl každý bod samostatný CircleMarker = ~1000 objektů a překreslení trvalo několik sekund.)
body_geojson = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "duvod": duvod or "(bez popisu)",
                # Na tmavé mapě jsou fialové body o trochu světlejší
                "barva": (
                    BARVA_TMA_TMAVA_MAPA
                    if tmava_mapa and barva == BARVA_TMA
                    else barva
                ),
            },
        }
        for lat, lon, duvod, barva in zip(
            df_mapa["latitude"],
            df_mapa["longitude"],
            df_mapa["desc_detail_duvod"],
            df_mapa["barva"],
        )
    ],
}

if zobrazit_pocit and body_geojson["features"]:
    folium.GeoJson(
        body_geojson,
        name="Nebezpečná místa",
        marker=folium.CircleMarker(radius=5, fill=True, fill_opacity=0.8),
        style_function=lambda bod: {
            "color": bod["properties"]["barva"],
            "fillColor": bod["properties"]["barva"],
        },
        tooltip=folium.GeoJsonTooltip(fields=["duvod"], labels=False),
        popup=folium.GeoJsonPopup(fields=["duvod"], labels=False),
    ).add_to(mapa)


# Budovy UP (jen ve studentské verzi) – obarvený tvar budovy, po najetí myší jen název
if studentsky_rezim and budovy:
    vrstva_budov = folium.FeatureGroup(name="Budovy UP")

    # Modrá záře kolem budov, aby byly na tmavé mapě dobře vidět
    mapa.get_root().header.add_child(folium.Element(
        "<style>"
        ".budova-up { filter: drop-shadow(0 0 4px #4fb3ff) drop-shadow(0 0 8px #4fb3ff); }"
        "</style>"
    ))

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

    vrstva_budov.add_to(mapa)


# Skupina pro vlastní body uživatelů
uzivatelske_body = folium.FeatureGroup(
    name="Vlastní body"
)


# Vykreslení již vytvořených vlastních bodů
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
        tooltip=nazev,
        popup=duvod
    ).add_to(uzivatelske_body)


uzivatelske_body.add_to(mapa)


# Start, cíl a trasa navigace
vykresli_navigaci(mapa, route)


# Nástroj pro přesouvání a mazání bodů
Draw(
    feature_group=uzivatelske_body,
    export=False,
    position="topleft",
    draw_options={
        "polyline": False,
        "polygon": False,
        "rectangle": False,
        "circle": False,
        "circlemarker": False,
        "marker": False
    },
    edit_options={
        "edit": True,
        "remove": True
    }
).add_to(mapa)


# Zobrazení mapy a získání kliknutí.
# Vyhledávání trasy (Odkud / Kam) leží ve stejném obalu a zobrazí se přes levý horní roh mapy.
with st.container(key="mapa_obal"):

    vyhledavaci_panel()

    output = st_folium(
        mapa,
        width=None,
        height=650,
        use_container_width=True,
        returned_objects=["all_drawings", "last_clicked"],
        key="mapa"
    )


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


# Uložení upravených a přesunutých bodů
nove_body = output.get("all_drawings")

if nove_body is not None:

    if isinstance(nove_body, dict):
        nove_body = nove_body.get("features", [])

    if nove_body != st.session_state.moje_body:
        st.session_state.moje_body = nove_body


# Řádek se statistikami pod mapou
statistiky = [
    *(
        [
            ("🏫 Budovy UP", f"{len(budovy)}"),
            # (Studenty přes budovy nesčítáme – jeden student chodí do více budov)
            (
                "🌙 Výuka po setmění",
                f"{sum(1 for b in budovy if b['dark_students'])} <small>budov</small>",
            ),
        ]
        if studentsky_rezim
        else []
    ),
    ("📍 Zobrazená místa", f"{len(df_mapa)} <small>/ {len(df)}</small>"),
    ("🟢 Vlastní body", f"{len(st.session_state.moje_body)}"),
]

if zobrazit_voronoi:
    statistiky.append(
        ("🚨 Činy (kriminalita)", f"{len(df_krim_mapa)} <small>/ {len(df_krim)}</small>")
    )

if route is not None:
    souhrn = route["routes"][0]["summary"]
    statistiky.append(("🧭 Délka trasy", f"{souhrn['distance'] / 1000:.2f} <small>km</small>"))
    statistiky.append(("🚶 Doba chůze", f"{round(souhrn['duration'] / 60)} <small>min</small>"))

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


# Seznam vlastních bodů (sbalitelný, aby nezabíral místo)
with st.expander(f"📋 Seznam vlastních bodů ({len(st.session_state.moje_body)})"):

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

        st.caption(
            f"Zeměpisná šířka: {souradnice[1]:.6f}, "
            f"zeměpisná délka: {souradnice[0]:.6f}"
        )

    if len(st.session_state.moje_body) == 0:
        st.info("Zatím nebyl vytvořen žádný vlastní bod.")


# Otevření okénka po kliknutí na mapu
if st.session_state.cekajici_bod is not None:

    lat_bodu, lon_bodu = st.session_state.cekajici_bod

    # Vynulujeme hned, aby se okno znovu neotevřelo po zavření křížkem
    st.session_state.cekajici_bod = None
    
    okno_pro_bod(lat_bodu, lon_bodu)
