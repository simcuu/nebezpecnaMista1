import streamlit as st
import folium
from streamlit_folium import st_folium

# Nastavení stránky
st.set_page_config(
    page_title="Nebezpečná místa – Olomouc",
    layout="wide"
)


st.write("Testovací mapa nebezpečných míst.")
mapa = folium.Map(
    location=[49.5938, 17.2509],
    zoom_start=14
)

nebezpecna_mista = [
    {
        "nazev mista": "1. Hlavní nádraží Olomouc", 
        "problem mista": "výskyt bezdomovců",
        "souradnice" :  [49.5920467, 17.2778131]
    },
    {
        "nazev mista": "2. Lazce",
        "problem mista":"riziko střetu s raketou",
        "souradnice" :  [49.6020331, 17.2496403]
    },
    {
        "nazev mista": "3. Věznice",
        "problem mista": "3. riziko střetu s vězni",
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


import json
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium


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
    "a": "#7B61A8",  # noc – fialová
    "b": "#E5A000",  # den – žlutá
}

df["barva"] = df["typ_ident"].map(barvy)


# Boční panel – filtrování
st.sidebar.title("Nastavení mapy")

vyber = st.sidebar.selectbox(
    "Zobrazit místa:",
    [
        "Vše",
        "Noc",
        "Den"
    ]
)


# Výběr bodů podle filtru
if vyber == "Noc":
    df_mapa = df[df["typ_ident"] == "a"]

elif vyber == "Den":
    df_mapa = df[df["typ_ident"] == "b"]

else:
    df_mapa = df


# Rozdělení obrazovky
levy_sloupec, pravy_sloupec = st.columns([2, 1])


# Levý sloupec – mapa
with levy_sloupec:

    st.subheader("Mapa Olomouce")

    mapa = folium.Map(
        location=[49.5938, 17.2509],
        zoom_start=12
    )

    # Vykreslení jednotlivých bodů
    for index, misto in df_mapa.iterrows():

        folium.CircleMarker(
            location=[
                misto["latitude"],
                misto["longitude"]
            ],
            radius=5,
            color=misto["barva"],
            fill=True,
            fill_color=misto["barva"],
            fill_opacity=0.8,
            popup=f"Typ identifikace: {misto['typ_ident']}"
        ).add_to(mapa)

    # Zobrazení mapy
    st_folium(
        mapa,
        width=None,
        height=600
    )


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

    st.write("Legenda:")

    st.markdown(
        '<span style="color:#7B61A8;">●</span> Noc',
        unsafe_allow_html=True
    )

    st.markdown(
        '<span style="color:#E5A000;">●</span> Den',
        unsafe_allow_html=True
    )



for misto in nebezpecna_mista:
    folium.Marker(
        location=misto["souradnice"],
        popup=misto["problem mista"],
        tooltip=misto["nazev mista"],
        icon=folium.Icon(color="red")
    ).add_to(mapa)

# Zobrazení mapy ve Streamlitu
st_folium(mapa, width=900, height=600)