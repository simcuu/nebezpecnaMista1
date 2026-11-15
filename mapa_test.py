import streamlit as st
import folium
from streamlit_folium import st_folium
import json
import pandas as pd
from folium.plugins import Draw

# Nastavení stránky
st.set_page_config(
    page_title="Nebezpečná místa – Olomouc",
    layout="wide"
)

st.write("Testovací mapa nebezpečných míst.")

# Inicializace vlastních bodů
if "moje_body" not in st.session_state:
    st.session_state.moje_body = []

if "cekajici_bod" not in st.session_state:
    st.session_state.cekajici_bod = None

if "posledni_klik" not in st.session_state:
    st.session_state.posledni_klik = None

# Režim přidávání bodu (zapíná se tlačítkem v bočním panelu)
if "rezim_pridani" not in st.session_state:
    st.session_state.rezim_pridani = False


# Testovací místa
nebezpecna_mista = [
    {
        "nazev mista": "1. Hlavní nádraží Olomouc",
        "problem mista": "výskyt bezdomovců",
        "souradnice": [49.5920467, 17.2778131]
    },
    {
        "nazev mista": "2. Lazce",
        "problem mista": "riziko střetu s raketou",
        "souradnice": [49.6020331, 17.2496403]
    },
    {
        "nazev mista": "3. Věznice",
        "problem mista": "riziko střetu s vězni",
        "souradnice": [49.5920275, 17.2483156]
    },
    {
        "nazev mista": "4. Hospoda",
        "problem mista": "výskyt zajímavých podnapilých lidí",
        "souradnice": [49.6043722, 17.2522578]
    },
    {
        "nazev mista": "5. Frajtovo náměstí",
        "problem mista": "hrůzostrašný pán",
        "souradnice": [49.6120267, 17.2575600]
    }
]


# Načtení GeoJSON souboru
with open(
    "pocit-nebezpeci-olomouc-2.geojson",
    encoding="utf-8"
) as f:
    geojson = json.load(f)


# Získání souřadnic jednotlivých bodů
rows = []

for feature in geojson["features"]:
    geometry = feature.get("geometry")

    if geometry and geometry["type"] == "Point":
        lon, lat = geometry["coordinates"][:2]

        if 16.8 <= lon <= 17.7 and 49.3 <= lat <= 49.9:
            rows.append({
                "latitude": lat,
                "longitude": lon,
                "typ_ident": feature["properties"].get("typ_ident")
            })


# Převod dat na tabulku
df = pd.DataFrame(rows)


# Barvy podle kategorie
barvy = {
    "a": "#7B61A8",
    "b": "#E5A000",
}

df["barva"] = df["typ_ident"].map(barvy)


# Boční panel – nastavení mapy
st.sidebar.title("Nastavení mapy")


# Tlačítko pro zapnutí / vypnutí režimu přidávání bodu
if not st.session_state.rezim_pridani:

    if st.sidebar.button("📍 Přidat nový bod", use_container_width=True):
        st.session_state.rezim_pridani = True
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


# Výběr bodů podle filtru
if vyber == "Noc":
    df_mapa = df[df["typ_ident"] == "a"]

elif vyber == "Den":
    df_mapa = df[df["typ_ident"] == "b"]

else:
    df_mapa = df


# Uložení vybraného bodu
if "vybrany_bod" not in st.session_state:
    st.session_state.vybrany_bod = None


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

            st.session_state.moje_body.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        lon,
                        lat
                    ]
                },
                "properties": {
                    "nazev": nazev,
                    "duvod": duvod
                }
            })

            # Po uložení se režim přidávání vypne
            st.session_state.rezim_pridani = False
            st.rerun()

        else:
            st.warning("Vyplňte název i popis problému.")


# Rozdělení obrazovky
levy_sloupec, pravy_sloupec = st.columns([2, 1])


# Levý sloupec – mapa
with levy_sloupec:

    st.subheader("Mapa Olomouce")

    mapa = folium.Map(
        location=[49.5938, 17.2509],
        zoom_start=12
    )


    # Vykreslení GeoJSON bodů
    for index, misto in df_mapa.iterrows():

        bod_id = f"geo_{index}"

        vybran = st.session_state.vybrany_bod == bod_id

        barva_bodu = "green" if vybran else misto["barva"]

        folium.CircleMarker(
            location=[
                misto["latitude"],
                misto["longitude"]
            ],
            radius=8 if vybran else 5,
            color=barva_bodu,
            fill=True,
            fill_color=barva_bodu,
            fill_opacity=0.8,
            popup=f"Typ identifikace: {misto['typ_ident']}"
        ).add_to(mapa)


    # Vykreslení testovacích bodů
    for index, misto in enumerate(nebezpecna_mista):

        bod_id = f"test_{index}"

        vybran = st.session_state.vybrany_bod == bod_id

        folium.Marker(
            location=misto["souradnice"],
            popup=misto["problem mista"],
            tooltip=misto["nazev mista"],
            icon=folium.Icon(
                color="green" if vybran else "red"
            )
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

        # Stejně jako u testovacích bodů: název v tooltipu, popis v popupu
        folium.Marker(
            location=[lat, lon],
            tooltip=nazev,
            popup=duvod,
            icon=folium.Icon(color="green")
        ).add_to(uzivatelske_body)


    uzivatelske_body.add_to(mapa)


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
        height=600,
        returned_objects=["all_drawings", "last_clicked"],
        key="mapa"
    )


    # Zpracování kliknutí na mapu – jen v režimu přidávání
    kliknuti = output.get("last_clicked")

    if kliknuti and st.session_state.rezim_pridani:

        podpis = (
            round(kliknuti["lat"], 6),
            round(kliknuti["lng"], 6)
        )

        if podpis != st.session_state.posledni_klik:

            st.session_state.posledni_klik = podpis

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


# Pravý sloupec – informace
with pravy_sloupec:

    st.subheader("Informace o datech")

    st.metric(
        "Počet zobrazených míst",
        len(df_mapa)
    )

    st.metric(
        "Celkový počet míst",
        len(df)
    )

    st.metric(
        "Počet vlastních bodů",
        len(st.session_state.moje_body)
    )

    st.write("Legenda:")

    st.markdown(
        '<span style="color:#7B61A8;">●</span> Noc',
        unsafe_allow_html=True
    )

    st.markdown(
        '<span style="color:#E5A000;">●</span> Den',
        unsafe_allow_html=True
    )

    st.markdown(
        '<span style="color:green;">●</span> Vlastní body',
        unsafe_allow_html=True
    )

    st.markdown(
        '<span style="color:red;">●</span> Testovací místa',
        unsafe_allow_html=True
    )

    st.divider()

    st.subheader("Vlastní body")

    st.write("Body, které vytvořil uživatel:")

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

        st.write(f"**{nazev}**")
        st.write(f"Popis: {duvod}")

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
