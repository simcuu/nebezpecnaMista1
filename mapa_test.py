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
    zpracuj_klik_navigace,
)

# Nastavení stránky
st.set_page_config(
    page_title="Nebezpečná místa – Olomouc",
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
    /* Menší horní odsazení stránky, aby nadpis byl výš */
    .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: 2rem !important;
    }
    .legenda {
        background: #3b2a5c;
        border-radius: 10px;
        padding: 12px 16px;
        margin: 4px 0 12px 0;
    }
    .legenda-nadpis {
        font-weight: 600;
        margin-bottom: 8px;
    }
    .legenda-polozka {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 6px 0;
    }
    .legenda-tecka {
        width: 18px;
        height: 18px;
        border-radius: 50%;
        border: 2px solid rgba(255, 255, 255, 0.8);
        flex-shrink: 0;
    }
    .statistiky {
        display: flex;
        flex-wrap: wrap;
        gap: 8px 28px;
        background: #1b1726;
        border: 1px solid #3b2a5c;
        border-radius: 8px;
        padding: 8px 16px;
        margin-top: 8px;
        font-size: 0.9rem;
    }
    .statistiky span b {
        color: #c9b6f0;
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


# Boční panel – nastavení mapy
st.sidebar.title("Nastavení mapy")


# Tlačítko pro zapnutí / vypnutí režimu přidávání bodu
if not st.session_state.rezim_pridani:

    if st.sidebar.button("📍 Přidat nový bod", use_container_width=True):
        st.session_state.rezim_pridani = True
        # Výběr startu/cíle navigace se tím ukončí, aby klik do mapy nebyl dvojznačný
        st.session_state["navigace_vybirany_bod"] = None
        st.rerun()

else:

    st.sidebar.info("Režim přidávání je zapnutý. Klikněte do mapy.")

    if st.sidebar.button("❌ Zrušit přidávání", use_container_width=True):
        st.session_state.rezim_pridani = False
        st.rerun()


# Boční panel – filtrování
vyber = st.sidebar.selectbox(
    "Zobrazit místa:",
    ["Vše", "Noc", "Den"]
)

vybrane_kategorie = st.sidebar.multiselect(
    "Kategorie důvodu:",
    [*kategorie_slov, "Ostatní"]
)


# Boční panel – legenda
st.sidebar.markdown(
    """
    <div class="legenda">
        <div class="legenda-nadpis">Legenda</div>
        <div class="legenda-polozka">
            <span class="legenda-tecka" style="background:#7B61A8;"></span> Noc
        </div>
        <div class="legenda-polozka">
            <span class="legenda-tecka" style="background:#E5A000;"></span> Den
        </div>
        <div class="legenda-polozka">
            <span class="legenda-tecka" style="background:green;"></span> Vlastní body
        </div>
    </div>
    """,
    unsafe_allow_html=True
)


# Výběr bodů podle filtru
if vyber == "Noc":
    df_mapa = df[df["typ_ident"] == "a"]

elif vyber == "Den":
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


# Boční panel – navigace (pracuje přímo v hlavní mapě)
with st.sidebar:
    st.divider()
    st.subheader("Navigace")
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
    '<h1 style="white-space:nowrap; font-size:clamp(1.4rem, 3.2vw, 2.6rem); '
    'line-height:1.4; overflow:visible; '
    'margin:0 0 0.4rem 0; padding:0.25em 0 0 0;">NEBEZPEČNÁ MÍSTA V OLOMOUCI</h1>',
    unsafe_allow_html=True
)

mapa = folium.Map(
    location=[49.5938, 17.2509],
    zoom_start=12
)


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
                "barva": barva,
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


# Zobrazení mapy a získání kliknutí
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
    f"Zobrazená místa: <b>{len(df_mapa)}</b>",
    f"Celkem míst: <b>{len(df)}</b>",
    f"Vlastní body: <b>{len(st.session_state.moje_body)}</b>",
]

if route is not None:
    souhrn = route["routes"][0]["summary"]
    statistiky.append(f"Délka trasy: <b>{souhrn['distance'] / 1000:.2f} km</b>")
    statistiky.append(f"Doba chůze: <b>{round(souhrn['duration'] / 60)} min</b>")

st.markdown(
    '<div class="statistiky">'
    + "".join(f"<span>{polozka}</span>" for polozka in statistiky)
    + "</div>",
    unsafe_allow_html=True
)


# Seznam vlastních bodů (sbalitelný, aby nezabíral místo)
with st.expander(f"Vlastní body ({len(st.session_state.moje_body)})"):

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
