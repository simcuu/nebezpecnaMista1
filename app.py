import streamlit as st
import folium as fm
from streamlit_folium import st_folium

#stranka
st.set_page_config(page_title="Bezpečná Olomouc", page_icon="📍", layout="wide")

#nadpis
st.title("Bezpečná Olomouc")
st.write("Mapa zobrazující nebezpečná místa v Olomouci.")

# Boční panel (Sidebar)
with st.sidebar:
    st.header("Nějaké random věci")
    st.write("nevim neco.")

# Hlavní nadpis
st.title("bezpecna olomouc asi")

# Rozdělení hlavní obrazovky na 2 části (levý a pravý sloupec)
levy_sloupec, pravy_sloupec = st.columns(2, gap="large")

# 1. část (vlevo) - připraveno pro mapu
with levy_sloupec:
    st.subheader("Mapa")
    st.info("Zde se po naimportování zobrazí mapa.")
    # Sem pak vložíš kód pro vykreslení mapy
with pravy_sloupec:
    st.subheader("Formulář")
    
    with st.form(key="zakladni_formular"):
        nazev = st.text_input("Název")
        popis = st.text_area("Popis")
        
        odeslat = st.form_submit_button("Odeslat")
        
        if odeslat:
            st.success(f"Odesláno: {nazev}")