import json

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="Bezpečná Olomouc", page_icon="📍", layout="wide")

st.title("Bezpečná Olomouc")
st.write("Mapa zobrazující nebezpečná místa v Olomouci.")

barvy = {
    "a": "#7B61A8",
    "b": "#E5A000",
}

vyber = st.sidebar.selectbox(
    "Zobrazit místa:",
    ["Vše", "Noc", "Den"],
)

with open("pocit-nebezpeci-olomouc-2.geojson", encoding="utf-8") as soubor:
    geojson = json.load(soubor)

rows = []
for feature in geojson["features"]:
    geometry = feature.get("geometry")
    if geometry and geometry["type"] == "Point":
        lon, lat = geometry["coordinates"][:2]
        if 16.8 <= lon <= 17.7 and 49.3 <= lat <= 49.9:
            rows.append({
                "latitude": lat,
                "longitude": lon,
                "typ_ident": feature.get("properties", {}).get("typ_ident"),
            })

df = pd.DataFrame(rows, columns=["latitude", "longitude", "typ_ident"])
df["barva"] = df["typ_ident"].map(barvy)

if vyber == "Noc":
    df_mapa = df[df["typ_ident"] == "a"]
elif vyber == "Den":
    df_mapa = df[df["typ_ident"] == "b"]
else:
    df_mapa = df

mapa = folium.Map(
    location=[49.5938, 17.2509],
    zoom_start=12,
)

for _, misto in df_mapa.iterrows():
    barva = misto["barva"] if pd.notna(misto["barva"]) else "#808080"
    folium.CircleMarker(
        location=[misto["latitude"], misto["longitude"]],
        radius=5,
        color=barva,
        fill=True,
        fill_color=barva,
        fill_opacity=0.8,
        popup=f"Typ identifikace: {misto['typ_ident']}",
    ).add_to(mapa)

nebezpecna_mista = [
    {
        "nazev": "1. Hlavní nádraží Olomouc",
        "problem": "výskyt bezdomovců",
        "souradnice": [49.5920467, 17.2778131],
    },
    {
        "nazev": "2. Lazce",
        "problem": "riziko střetu s raketou",
        "souradnice": [49.6020331, 17.2496403],
    },
    {
        "nazev": "3. Věznice",
        "problem": "3. riziko střetu s vězni",
        "souradnice": [49.5920275, 17.2483156],
    },
    {
        "nazev": "4. Hospoda",
        "problem": "výskyt zajímavých podnapilých lidí",
        "souradnice": [49.6043722, 17.2522578],
    },
    {
        "nazev": "5. Frajtovo náměstí",
        "problem": "hrůzostrašný pán",
        "souradnice": [49.6120267, 17.25756],
    },
]

for misto in nebezpecna_mista:
    folium.Marker(
        location=misto["souradnice"],
        popup=misto["problem"],
        tooltip=misto["nazev"],
        icon=folium.Icon(color="red"),
    ).add_to(mapa)

levy_sloupec, pravy_sloupec = st.columns([2, 1], gap="large")

with levy_sloupec:
    st.subheader("Mapa Olomouce")
    st_folium(mapa, width=None, height=600)

    st.subheader("Poznatky")
    with st.form(key="my_form"):
        nazev = st.text_input("Napište název")
        problem = st.text_input("Svěřte se s problémem")
        odeslat = st.form_submit_button(
            label="Ano bohužel mám tento problém :/",
        )
        if odeslat:
            with open("data.txt", "a", encoding="utf-8") as soubor:
                soubor.write(f"Název: {nazev}\n")
                soubor.write(f"Problém: {problem}\n\n")
            st.success("Děkujeme za sdílení vašeho problému!")

with pravy_sloupec:
    st.subheader("Informace o datech")
    st.metric("Počet zobrazených míst", len(df_mapa))
    st.metric("Celkový počet míst", len(df))
    st.write("Legenda:")
    st.markdown(
        '<span style="color:#7B61A8;">●</span> Noc',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<span style="color:#E5A000;">●</span> Den',
        unsafe_allow_html=True,
    )
