import streamlit as st
import openrouteservice
import folium
from streamlit_folium import st_folium
from openrouteservice import convert

st.title("Navigace: Hejčín → hlavní nádraží")

# OpenRouteService očekává souřadnice ve formátu [lon, lat], ne [lat, lon]
start = (17.237912, 49.602605)
end = (17.276758, 49.592780)

client = openrouteservice.Client(
    key='eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjYzZDI0NjZlZmUwZDQzMmU4YzIyMjgwMmY5YjRjZWEzIiwiaCI6Im11cm11cjY0In0='
)

if st.button("Najdi trasu"):
    st.session_state["route"] = client.directions(
        [start, end],
        profile="foot-walking",
    )

route = st.session_state.get("route")
if route is not None:
    summary = route['routes'][0]['summary']

    st.write("Délka trasy:", summary['distance'], "m")
    st.write("Doba chůze:", round(summary['duration'] / 60, 1), "minut")

    # 1. Extrakce souřadnic cesty z JSON odpovědi
    # ORS vrací trasu jako seznam [lon, lat] bodů v geometrii
    geometry_coords = route['routes'][0]['geometry']

    decoded = convert.decode_polyline(geometry_coords)

    # 2. Folium vyžaduje formát [lat, lon], proto musíme otočit pořadí u každého bodu trasy
    folium_coords = [[point[1], point[0]] for point in decoded['coordinates']]

    # 3. Vytvoření základní mapy (vycentrováno na začátek trasy, prohozené na lat, lon)
    m = folium.Map(location=[start[1], start[0]], zoom_start=14)

    # Přidání značky pro Start
    folium.Marker(
        location=[start[1], start[0]],
        popup="Start: Hejčín",
        icon=folium.Icon(color="green", icon="play")
    ).add_to(m)

    # Přidání značky pro Cíl
    folium.Marker(
        location=[end[1], end[0]],
        popup="Cíl: Hlavní nádraží",
        icon=folium.Icon(color="red", icon="stop")
    ).add_to(m)

    # 4. Vykreslení samotné trasy (čáry) na mapu
    folium.PolyLine(locations=folium_coords, color="blue", weight=5, opacity=0.7).add_to(m)

    # 5. Zobrazení mapy přímo ve Streamlitu
    st_folium(m, width=700, height=500)

    # Původní JSON výpis schováme do rozbalovacího menu, ať nepřekáží
    with st.expander("Zobrazit surová JSON data trasy"):
        st.json(route)
