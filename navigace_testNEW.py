import ast
import math
from pathlib import Path

import folium
import openrouteservice
import streamlit as st
from openrouteservice import convert
from streamlit_folium import st_folium


def nacti_nebezpecna_mista(cesta_k_souboru):
    """Načte seznam nebezpečných míst z mapy_test.py bez jeho úprav."""
    soubor = Path(cesta_k_souboru)
    if not soubor.exists():
        st.warning(f"Soubor s nebezpečnými místy nebyl nalezen: {soubor}")
        return []

    text = soubor.read_text(encoding="utf-8")
    strom = ast.parse(text, filename=str(soubor))

    for prvek in strom.body:
        if isinstance(prvek, ast.Assign):
            for target in prvek.targets:
                if isinstance(target, ast.Name) and target.id == "nebezpecna_mista":
                    return ast.literal_eval(prvek.value)

    st.warning("V souboru nebyla nalezena proměnná nebezpecna_mista.")
    return []


def vytvor_avoid_polygony(mista, radius_metres=80):
    """Vytvoří zóny kolem nebezpečných bodů, aby si trasa od nich udržela odstup."""
    polygons = []

    for bod in mista:
        lat, lon = bod["souradnice"]
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


st.title("Navigace: Hejčín → Hlavní nádraží")

# Otevření souboru se seznamem nebezpečných míst bez úprav v mapy_test.py
nebezpecna_mista = nacti_nebezpecna_mista(Path(__file__).with_name("mapa_test.py"))
avoid_polygons = vytvor_avoid_polygony(nebezpecna_mista)

# OpenRouteService očekává souřadnice ve formátu [lon, lat], ne [lat, lon]
start = (17.237912, 49.602605)
end = (17.276758, 49.592780)

client = openrouteservice.Client(
    key="eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjYzZDI0NjZlZmUwZDQzMmU4YzIyMjgwMmY5YjRjZWEzIiwiaCI6Im11cm11cjY0In0="
)

if st.button("Najdi trasu"):
    if nebezpecna_mista:
        st.session_state["route"] = client.directions(
            [start, end],
            profile="foot-walking",
            options={"avoid_polygons": avoid_polygons},
        )
    else:
        st.session_state["route"] = client.directions(
            [start, end],
            profile="foot-walking",
        )

route = st.session_state.get("route")
if route is not None:
    summary = route["routes"][0]["summary"]

    st.write("Délka trasy:", summary["distance"], "m")
    st.write("Doba chůze:", round(summary["duration"] / 60, 1), "minut")

    geometry_coords = route["routes"][0]["geometry"]
    decoded = convert.decode_polyline(geometry_coords)
    folium_coords = [[point[1], point[0]] for point in decoded["coordinates"]]

    mapa = folium.Map(location=[start[1], start[0]], zoom_start=14)

    folium.Marker(
        location=[start[1], start[0]],
        popup="Start: Hejčín",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(mapa)

    folium.Marker(
        location=[end[1], end[0]],
        popup="Cíl: Hlavní nádraží",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(mapa)

    for misto in nebezpecna_mista:
        lat, lon = misto["souradnice"]
        folium.Circle(
            location=[lat, lon],
            radius=80,
            color="red",
            fill=True,
            fill_color="red",
            fill_opacity=0.15,
            popup=misto["nazev mista"],
        ).add_to(mapa)

    folium.PolyLine(
        locations=folium_coords,
        color="blue",
        weight=5,
        opacity=0.7,
    ).add_to(mapa)

    st_folium(mapa, width=700, height=500)

    with st.expander("Zobrazit surová JSON data trasy"):
        st.json(route)


# python -m streamlit run navigace_test2tem.py