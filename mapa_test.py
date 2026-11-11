import streamlit as st
import folium
from streamlit_folium import st_folium


st.title("Nebezpečná místa – Olomouc \n")
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




for misto in nebezpecna_mista:
    folium.Marker(
        location=misto["souradnice"],
        popup=misto["problem mista"],
        tooltip=misto["nazev mista"],
        icon=folium.Icon(color="red")
    ).add_to(mapa)

# Zobrazení mapy ve Streamlitu
st_folium(mapa, width=900, height=600)