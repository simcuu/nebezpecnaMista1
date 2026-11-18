import json
import math
import folium
import openrouteservice
import streamlit as st

from pathlib import Path
from openrouteservice import convert, exceptions
from folium.plugins import FastMarkerCluster
from streamlit_folium import st_folium

# nastavení klíče OpenRouteService z .env souboru
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


def zobraz_navigaci():
    st.title("Navigace")

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
            "typ_ident": properties.get("typ_ident"),
        })

    if "navigace_start" not in st.session_state:
        st.session_state["navigace_start"] = None
    if "navigace_cil" not in st.session_state:
        st.session_state["navigace_cil"] = None
    if "navigace_posledni_klik" not in st.session_state:
        st.session_state["navigace_posledni_klik"] = None

    levy_sloupec, pravy_sloupec = st.columns([3, 1])

    with pravy_sloupec:
        st.subheader("Body trasy")
        bod_k_nastaveni = st.radio(
            "Po kliknutí na mapu nastavit:",
            ["Start", "Cíl"],
            key="navigace_bod_k_nastaveni",
        )
        st.caption("Vyberte Start nebo Cíl a potom klikněte na požadované místo v mapě.")
        start = st.session_state["navigace_start"]
        end = st.session_state["navigace_cil"]
        st.write(
            "Start: "
            + (f"{start[1]:.5f}, {start[0]:.5f}" if start else "nevybrán")
        )
        st.write(
            "Cíl: "
            + (f"{end[1]:.5f}, {end[0]:.5f}" if end else "nevybrán")
        )

        st.subheader("Filtrovat místa")
        zobrazit_den = st.checkbox("Den", value=True, key="navigace_den")
        zobrazit_noc = st.checkbox("Noc", value=True, key="navigace_noc")

        vybrana_kategorie = set()
        if zobrazit_den:
            vybrana_kategorie.add("b")
        if zobrazit_noc:
            vybrana_kategorie.add("a")

        st.metric(
            "Zobrazeno míst",
            sum(
                1
                for bod in nebezpecna_mista
                if bod["typ_ident"] in vybrana_kategorie
            ),
        )

    nebezpecna_mista = [
        bod for bod in nebezpecna_mista
        if bod["typ_ident"] in vybrana_kategorie
    ]

    client = openrouteservice.Client(
        key="eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjYzZDI0NjZlZmUwZDQzMmU4YzIyMjgwMmY5YjRjZWEzIiwiaCI6Im11cm11cjY0In0="
    )

    start = st.session_state["navigace_start"]
    end = st.session_state["navigace_cil"]
    parametry_trasy = (start, end, zobrazit_den, zobrazit_noc)
    route = st.session_state.get("route")

    def prepocitej_trasu():
        avoid_polygons = vytvor_avoid_polygony(
            nebezpecna_mista,
            [start, end],
            radius_metres=15,
        )
        st.session_state["route"] = najdi_trasu(
            client,
            start,
            end,
            avoid_polygons,
        )
        st.session_state["navigace_parametry_trasy"] = parametry_trasy

    with pravy_sloupec:
        if st.button(
            "Najít trasu",
            disabled=start is None or end is None,
            use_container_width=True,
        ):
            prepocitej_trasu()
            route = st.session_state["route"]

    if (
        route is not None
        and start is not None
        and end is not None
        and st.session_state.get("navigace_parametry_trasy") != parametry_trasy
    ):
        prepocitej_trasu()
        route = st.session_state["route"]

    with levy_sloupec:
        mapa = folium.Map(location=[49.5938, 17.2509], zoom_start=13)

        if start is not None:
            folium.Marker(
                location=[start[1], start[0]],
                popup="Start",
                icon=folium.Icon(color="green", icon="play"),
            ).add_to(mapa)

        if end is not None:
            folium.Marker(
                location=[end[1], end[0]],
                popup="Cíl",
                icon=folium.Icon(color="blue", icon="flag"),
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

        if route is not None:
            summary = route["routes"][0]["summary"]
            geometry_coords = route["routes"][0]["geometry"]
            decoded = convert.decode_polyline(geometry_coords)
            folium_coords = [[point[1], point[0]] for point in decoded["coordinates"]]
            folium.PolyLine(
                locations=folium_coords,
                color="blue",
                weight=5,
                opacity=0.7,
            ).add_to(mapa)
            st.write("Délka trasy:", summary["distance"], "m")
            st.write("Doba chůze:", round(summary["duration"] / 60, 1), "minut")

        output = st_folium(
            mapa,
            width=None,
            height=600,
            returned_objects=["last_clicked"],
            key="navigace",
        )

        kliknuti = output.get("last_clicked")
        if kliknuti:
            podpis_kliku = (
                round(kliknuti["lat"], 6),
                round(kliknuti["lng"], 6),
            )
            if podpis_kliku != st.session_state["navigace_posledni_klik"]:
                st.session_state["navigace_posledni_klik"] = podpis_kliku
                souradnice = (kliknuti["lng"], kliknuti["lat"])
                if bod_k_nastaveni == "Start":
                    st.session_state["navigace_start"] = souradnice
                else:
                    st.session_state["navigace_cil"] = souradnice
                st.rerun()


    # Pokud chcete spustit aplikaci, použijte následující příkaz v terminálu:
    # python -m streamlit run navigace_test4.py

if __name__ == "__main__":
    zobraz_navigaci()
