import json
import math
from pathlib import Path

import folium
import openrouteservice
import streamlit as st
from openrouteservice import convert, exceptions
from folium.plugins import FastMarkerCluster
from streamlit_folium import st_folium


def najdi_trasu(client, start, end, avoid_polygons):
    if not avoid_polygons["coordinates"]:
        return client.directions([start, end], profile="foot-walking")

    try:
        return client.directions(
            [start, end],
            profile="foot-walking",
            options={"avoid_polygons": avoid_polygons},
        )
    except exceptions.ApiError as error:
        payload = error.message if isinstance(error.message, dict) else {}
        detail = payload.get("error", {})
        code = detail.get("code") if isinstance(detail, dict) else None
        if code not in {2009, 2010}:
            raise

        st.warning(
            "S vyhýbacími zónami se trasu nepodařilo najít. "
            "Zobrazuji trasu bez vyhýbání; nebezpečná místa jsou vyznačena na mapě."
        )
        return client.directions([start, end], profile="foot-walking")


def vytvor_avoid_polygony(mista, koncove_body, radius_metres=80):
    """Vytvoří zóny kolem nebezpečných bodů, aby si trasa od nich udržela odstup."""
    polygons = []

    for bod in mista:
        lat, lon = bod["souradnice"]
        phi = math.radians(lat)
        if any(
            2
            * 6_371_000
            * math.asin(
                math.sqrt(
                    math.sin(math.radians(lat - konec[1]) / 2) ** 2
                    + math.cos(phi)
                    * math.cos(math.radians(konec[1]))
                    * math.sin(math.radians(lon - konec[0]) / 2) ** 2
                )
            )
            <= 500
            for konec in koncove_body
        ):
            continue

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

# Načtení GeoJSON souboru
geojson_path = Path(__file__).with_name("pocit-nebezpeci-olomouc-2.geojson")
with geojson_path.open(encoding="utf-8") as f:
    geojson = json.load(f)

# Převod bodů do formátu používaného navigací
nebezpecna_mista = []
for feature in geojson["features"]:
    geometry = feature.get("geometry")
    if not geometry or geometry.get("type") != "Point":
        continue

    coordinates = geometry.get("coordinates", [])
    if len(coordinates) < 2:
        continue

    lon, lat = coordinates[:2]
    if not (16.8 <= lon <= 17.7 and 49.3 <= lat <= 49.9):
        continue

    properties = feature.get("properties") or {}
    nebezpecna_mista.append({
        "nazev mista": properties.get("typ_nazev", "Nebezpečné místo"),
        "problem mista": properties.get("desc_detail_duvod", ""),
        "souradnice": [lat, lon],
    })

# OpenRouteService očekává souřadnice ve formátu [lon, lat], ne [lat, lon]
start = (17.237912, 49.602605)
end = (17.276758, 49.592780)
avoid_polygons = vytvor_avoid_polygony(
    nebezpecna_mista,
    [start, end],
    radius_metres=20,
)

client = openrouteservice.Client(
    key="eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjYzZDI0NjZlZmUwZDQzMmU4YzIyMjgwMmY5YjRjZWEzIiwiaCI6Im11cm11cjY0In0="
)

if st.button("Najdi trasu"):
    st.session_state["route"] = najdi_trasu(
        client,
        start,
        end,
        avoid_polygons,
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

    body_nebezpecnych_mist = [
        [
            misto["souradnice"][0],
            misto["souradnice"][1],
            misto["nazev mista"],
            misto["problem mista"],
        ]
        for misto in nebezpecna_mista
    ]
    FastMarkerCluster(
        data=body_nebezpecnych_mist,
        callback="""
        function (row) {
            var icon = L.divIcon({
                className: "",
                html: '<div style="width:10px;height:10px;border-radius:50%;background:#d62728;border:1px solid white;"></div>',
                iconSize: [12, 12],
                iconAnchor: [6, 6]
            });
            var marker = L.marker(new L.LatLng(row[0], row[1]), {icon: icon});
            var tooltip = document.createElement("div");
            tooltip.textContent = row[2];
            marker.bindTooltip(tooltip);
            if (row[3]) {
                var popup = document.createElement("div");
                popup.textContent = row[3];
                marker.bindPopup(popup);
            }
            return marker;
        }
        """,
        name="Nebezpečná místa",
        options={
            "maxClusterRadius": 60,
            "animate": False,
            "spiderfyOnMaxZoom": False,
            "showCoverageOnHover": False,
        },
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


# python -m streamlit run navigace_test4.py