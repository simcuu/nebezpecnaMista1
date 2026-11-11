import streamlit as st
import openrouteservice

st.title("Navigace: Hejčín → hlavní nádraží")

# OpenRouteService očekává souřadnice ve formátu [lon, lat], ne [lat, lon]
start = (17.241747, 49.597386)
end = (17.260292, 49.593720)

client = openrouteservice.Client(
    key='eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjYzZDI0NjZlZmUwZDQzMmU4YzIyMjgwMmY5YjRjZWEzIiwiaCI6Im11cm11cjY0In0='
)

if st.button("Najdi trasu"):
    route = client.directions([start, end], profile='foot-walking')
    summary = route['routes'][0]['summary']
    st.write("Délka trasy:", summary['distance'], "m")
    st.write("Doba chůze:", round(summary['duration'] / 60, 1), "minut")
    st.json(route)

    