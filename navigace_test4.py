import json
import math
import folium
import openrouteservice
import streamlit as st

from pathlib import Path
from openrouteservice import convert, exceptions
from folium.plugins import FastMarkerCluster
from streamlit_folium import st_folium

ORS_KLIC = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjYzZDI0NjZlZmUwZDQzMmU4YzIyMjgwMmY5YjRjZWEzIiwiaCI6Im11cm11cjY0In0="


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


def nacti_mista_z_geojsonu():
    geojson_path = Path(__file__).with_name("pocit-nebezpeci-olomouc-2.geojson")
    with geojson_path.open(encoding="utf-8") as f:
        geojson = json.load(f)

    mista = []
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
        mista.append({
            "typ_nazev": properties.get("typ_nazev") or "",
            "desc_detail_duvod": properties.get("desc_detail_duvod") or "",
            "latitude": lat,
            "longitude": lon,
        })
    return mista



def priprav_mista(mista_filtr):
    """Převede záznamy z mapy (latitude, longitude, desc_detail_duvod, typ_nazev)
    na formát navigace. Místa bez popisu důvodu se vynechají."""
    nebezpecna_mista = []
    for misto in mista_filtr:
        duvod = (misto.get("desc_detail_duvod") or "").strip()
        if not duvod:
            continue

        nebezpecna_mista.append({
            "nazev mista": misto.get("typ_nazev") or duvod or "Nebezpečné místo",
            "problem mista": duvod,
            "souradnice": [misto["latitude"], misto["longitude"]],
        })
    return nebezpecna_mista


def inicializuj_stav():
    for klic in ("navigace_start", "navigace_cil", "navigace_vybirany_bod"):
        if klic not in st.session_state:
            st.session_state[klic] = None


def zrus_navigaci():
    st.session_state["navigace_start"] = None
    st.session_state["navigace_cil"] = None
    st.session_state["navigace_vybirany_bod"] = None
    st.session_state["navigace_aktivni"] = False
    st.session_state.pop("route", None)
    st.session_state.pop("navigace_parametry_trasy", None)
    # Vyčistí i vyhledávací řádky nad mapou
    for typ in ("start", "cil"):
        for predpona in ("hledat_", "hledano_", "vysledky_", "volba_", "_text_"):
            st.session_state.pop(predpona + typ, None)


def nastav_bod(typ, souradnice):
    """Nastaví start nebo cíl (souřadnice jako (lon, lat)) a určí, co se má vybrat kliknutím dál."""
    st.session_state["navigace_start" if typ == "start" else "navigace_cil"] = souradnice

    if st.session_state.get("navigace_start") is None:
        st.session_state["navigace_vybirany_bod"] = "start"
    elif st.session_state.get("navigace_cil") is None:
        st.session_state["navigace_vybirany_bod"] = "cil"
    else:
        st.session_state["navigace_vybirany_bod"] = None


@st.cache_data(ttl=3600, show_spinner=False)
def hledej_misto(text):
    """Najde adresu/místo přes OpenRouteService (přednostně v Olomouci a okolí)."""
    client = openrouteservice.Client(key=ORS_KLIC)
    odpoved = client.pelias_search(
        text,
        focus_point=[17.2509, 49.5938],
        rect_min_x=16.8,
        rect_min_y=49.3,
        rect_max_x=17.7,
        rect_max_y=49.9,
        country="CZ",
        size=5,
    )
    return [
        {
            "popis": vysledek["properties"].get("label") or text,
            "souradnice": tuple(vysledek["geometry"]["coordinates"][:2]),
        }
        for vysledek in odpoved.get("features", [])
    ]


VYHLEDAVANI_CSS = """
<style>
.st-key-mapa_obal {
    position: relative;
}
.st-key-hledani_trasy {
    position: absolute !important;
    top: 10px;
    left: 56px;
    z-index: 1000;
    width: min(380px, calc(100% - 70px)) !important;
    padding: 10px 12px 12px 12px;
    background: rgba(27, 23, 38, 0.96);
    border: 1px solid #3b2a5c;
    border-radius: 12px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
    gap: 0.5rem !important;
}
.st-key-hledani_trasy p {
    margin: 0;
}
</style>
"""


def _hledaci_radek(typ, popisek, placeholder):
    """Jeden vyhledávací řádek (Odkud / Kam). Vrací True, když se změnil start/cíl."""
    klic = f"hledat_{typ}"

    # Text nastavený kliknutím do mapy se musí zapsat před vytvořením políčka
    cekajici_text = st.session_state.pop(f"_text_{typ}", None)
    if cekajici_text is not None:
        st.session_state[klic] = cekajici_text
        st.session_state[f"hledano_{typ}"] = cekajici_text
        st.session_state.pop(f"vysledky_{typ}", None)
        st.session_state.pop(f"volba_{typ}", None)

    text = st.text_input(
        popisek,
        key=klic,
        placeholder=placeholder,
        label_visibility="collapsed",
    ).strip()

    if text and text != st.session_state.get(f"hledano_{typ}"):
        st.session_state[f"hledano_{typ}"] = text
        st.session_state.pop(f"volba_{typ}", None)
        try:
            st.session_state[f"vysledky_{typ}"] = hledej_misto(text)
        except Exception:
            st.session_state[f"vysledky_{typ}"] = None

    vysledky = st.session_state.get(f"vysledky_{typ}")
    if text and text == st.session_state.get(f"hledano_{typ}"):
        if vysledky is None and f"vysledky_{typ}" in st.session_state:
            st.caption("⚠️ Vyhledávání teď nefunguje, zkuste to znovu nebo klikněte do mapy.")
        elif vysledky == []:
            st.caption("Nic jsme nenašli, zkuste napsat adresu jinak.")

    if not vysledky:
        return False

    poradi = 0
    if len(vysledky) > 1:
        poradi = st.selectbox(
            f"Upřesnit – {popisek}",
            range(len(vysledky)),
            format_func=lambda i: vysledky[i]["popis"],
            key=f"volba_{typ}",
            label_visibility="collapsed",
        )

    souradnice = vysledky[poradi]["souradnice"]
    klic_bodu = "navigace_start" if typ == "start" else "navigace_cil"
    if st.session_state.get(klic_bodu) != souradnice:
        nastav_bod(typ, souradnice)
        return True
    return False


def vyhledavaci_panel():
    """Vyhledávací řádky Odkud/Kam, které se zobrazí přes mapu (volat uvnitř kontejneru 'mapa_obal')."""
    if not st.session_state.get("navigace_aktivni"):
        return

    with st.container(key="hledani_trasy"):
        st.markdown(VYHLEDAVANI_CSS, unsafe_allow_html=True)

        nadpis, zavrit = st.columns([5, 1], vertical_alignment="center")
        nadpis.markdown("**🧭 Naplánovat trasu**")
        if zavrit.button("✕", key="zavrit_hledani", help="Skrýt vyhledávání (trasa zůstane)"):
            st.session_state["navigace_aktivni"] = False
            st.rerun()

        zmena = _hledaci_radek("start", "Odkud", "🟢 Odkud – adresa nebo místo")
        zmena = _hledaci_radek("cil", "Kam", "🏁 Kam – adresa nebo místo") or zmena

    if zmena:
        st.rerun()


def posun_bocni_listu_dolu():
    """Plynule posune dolů jen boční lištu (sidebar), hlavní stránka s mapou zůstane, kde je."""
    # Počítadlo zajistí, že se skript spustí znovu i při opakovaném kliknutí
    st.session_state["navigace_posun"] = st.session_state.get("navigace_posun", 0) + 1
    st.iframe(
        f"""
        <script>
        // pokus {st.session_state["navigace_posun"]}
        const doc = window.parent.document;
        function posun() {{
            const lista = doc.querySelector('[data-testid="stSidebar"]');
            if (!lista) return;
            const kandidati = [lista, ...lista.querySelectorAll("div")];
            const posuvny = kandidati.find(
                el => el.scrollHeight > el.clientHeight + 5
                    && getComputedStyle(el).overflowY !== "visible"
            );
            if (posuvny) {{
                posuvny.scrollTo({{ top: posuvny.scrollHeight, behavior: "smooth" }});
            }}
        }}
        setTimeout(posun, 150);
        </script>
        """,
        height="content",
    )


def ovladani_navigace(nebezpecna_mista):
    """Vykreslí ovládání navigace do aktuálního kontejneru a vrátí nalezenou trasu (nebo None)."""
    inicializuj_stav()

    posunout_listu = False
    if st.button("🧭 Zvolit start a cíl", use_container_width=True):
        zrus_navigaci()
        st.session_state["navigace_vybirany_bod"] = "start"
        st.session_state["navigace_aktivni"] = True
        posunout_listu = True

    start = st.session_state["navigace_start"]
    end = st.session_state["navigace_cil"]

    if st.session_state["navigace_vybirany_bod"] == "start":
        st.info("Napište start do vyhledávání nad mapou, nebo klikněte do mapy.")
    elif st.session_state["navigace_vybirany_bod"] == "cil":
        st.info("Start je vybrán. Napište cíl do vyhledávání, nebo klikněte do mapy.")
    elif start is not None and end is not None and "route" not in st.session_state:
        st.info("Start i cíl jsou vybrané, hledám trasu.")

    st.caption(
        "Start: "
        + (f"{start[1]:.5f}, {start[0]:.5f}" if start else "nevybrán")
        + "  \nCíl: "
        + (f"{end[1]:.5f}, {end[0]:.5f}" if end else "nevybrán")
    )
    radius_metres = st.number_input(
        "Odstup od nebezpečných míst (m)",
        min_value=1,
        value=15,
        step=1,
        help="Trasa se bude snažit držet alespoň tuto vzdálenost od míst.",
    )

    # Při změně filtru se trasa přepočítá s novými nebezpečnými místy
    podpis_filtru = tuple(
        (m["souradnice"][0], m["souradnice"][1], m["problem mista"])
        for m in nebezpecna_mista
    )
    zmena_filtru = st.session_state.get("route_filter_signature") != podpis_filtru
    st.session_state["route_filter_signature"] = podpis_filtru

    parametry_trasy = (start, end, radius_metres)
    route = st.session_state.get("route")

    def prepocitej_trasu():
        client = openrouteservice.Client(key=ORS_KLIC)
        avoid_polygons = vytvor_avoid_polygony(
            nebezpecna_mista,
            [start, end],
            radius_metres=radius_metres,
        )
        st.session_state["route"] = najdi_trasu(client, start, end, avoid_polygons)
        st.session_state["navigace_parametry_trasy"] = parametry_trasy
        return st.session_state["route"]

    zrusit = st.button(
        "Zrušit",
        disabled=start is None and end is None and route is None
        and st.session_state["navigace_vybirany_bod"] is None
        and not st.session_state.get("navigace_aktivni"),
        use_container_width=True,
    )

    if zrusit:
        zrus_navigaci()
        st.rerun()

    if posunout_listu:
        posun_bocni_listu_dolu()

    if start is not None and end is not None and (
        route is None
        or zmena_filtru
        or st.session_state.get("navigace_parametry_trasy") != parametry_trasy
    ):
        with st.spinner("Hledám trasu..."):
            route = prepocitej_trasu()

    return route


def vykresli_navigaci(mapa, route):
    """Přidá do mapy start, cíl a trasu."""
    start = st.session_state.get("navigace_start")
    end = st.session_state.get("navigace_cil")

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

    if route is not None:
        decoded = convert.decode_polyline(route["routes"][0]["geometry"])
        folium.PolyLine(
            locations=[[bod[1], bod[0]] for bod in decoded["coordinates"]],
            color="blue",
            weight=5,
            opacity=0.7,
        ).add_to(mapa)


def zpracuj_klik_navigace(kliknuti):
    """Zpracuje kliknutí do mapy při výběru startu/cíle. Vrací True, pokud klik použila navigace."""
    rezim = st.session_state.get("navigace_vybirany_bod")
    if rezim is None:
        return False

    souradnice = (kliknuti["lng"], kliknuti["lat"])
    nastav_bod(rezim, souradnice)
    # Do vyhledávacího řádku se vepíše, že bod byl vybrán na mapě
    st.session_state[f"_text_{rezim}"] = (
        f"📍 Bod na mapě ({kliknuti['lat']:.5f}, {kliknuti['lng']:.5f})"
    )
    return True


def zobraz_navigaci(mista_filtr=None):
    """Samostatná stránka navigace (pro testování: python -m streamlit run navigace_test4.py)."""
    st.title("Navigace")

    if mista_filtr is None:
        mista_filtr = nacti_mista_z_geojsonu()
    nebezpecna_mista = priprav_mista(mista_filtr)

    levy_sloupec, pravy_sloupec = st.columns([3, 1])

    with pravy_sloupec:
        st.subheader("Body trasy")
        route = ovladani_navigace(nebezpecna_mista)
        st.metric("Nebezpečných míst", len(nebezpecna_mista))

    with levy_sloupec:
        st.caption("Vyhledat adresu nebo místo")
        sloupec_dotaz, sloupec_hledat = st.columns([5, 1])
        with sloupec_dotaz:
            dotaz = st.text_input(
                "Adresa nebo místo",
                placeholder="Např. ulice, adresa nebo místo",
                label_visibility="collapsed",
                key="navigace_hledany_dotaz",
            )
        with sloupec_hledat:
            hledat = st.button(
                "Hledat",
                use_container_width=True,
            )

        if hledat:
            st.session_state["navigace_hledana_lokace"] = None
            if not dotaz.strip():
                st.warning("Zadejte adresu nebo místo k vyhledání.")
            else:
                klient = openrouteservice.Client(key=ORS_KLIC)
                try:
                    vysledek = klient.pelias_search(
                        dotaz.strip(),
                        focus_point=(17.2509, 49.5938),
                        country="CZE",
                        size=1,
                    )
                except exceptions.ApiError as error:
                    st.error(f"Místo se nepodařilo vyhledat: {error}")
                else:
                    nalezena_mista = vysledek.get("features") or []
                    if not nalezena_mista:
                        st.warning("Pro zadaný dotaz se nepodařilo najít místo.")
                    else:
                        nalezene_misto = nalezena_mista[0]
                        geometrie = nalezene_misto.get("geometry")
                        souradnice = (
                            geometrie.get("coordinates")
                            if isinstance(geometrie, dict)
                            else None
                        )
                        if (
                            not isinstance(souradnice, list)
                            or len(souradnice) < 2
                            or not all(
                                isinstance(hodnota, (int, float))
                                and math.isfinite(hodnota)
                                for hodnota in souradnice[:2]
                            )
                            or not -180 <= souradnice[0] <= 180
                            or not -90 <= souradnice[1] <= 90
                        ):
                            st.error("Vyhledávání vrátilo neplatné souřadnice.")
                        else:
                            vlastnosti = nalezene_misto.get("properties") or {}
                            st.session_state["navigace_hledana_lokace"] = {
                                "souradnice": souradnice[:2],
                                "nazev": vlastnosti.get("label") or dotaz.strip(),
                            }

        hledana_lokace = st.session_state.get("navigace_hledana_lokace")
        if hledana_lokace:
            st.caption(f"Nalezeno: {hledana_lokace['nazev']}")
            stred_mapy = [
                hledana_lokace["souradnice"][1],
                hledana_lokace["souradnice"][0],
            ]
            priblizeni = 16
        else:
            stred_mapy = [49.5938, 17.2509]
            priblizeni = 13

        mapa = folium.Map(location=stred_mapy, zoom_start=priblizeni)
        if hledana_lokace:
            folium.Marker(
                location=stred_mapy,
                tooltip=hledana_lokace["nazev"],
                icon=folium.Icon(color="orange", icon="search"),
            ).add_to(mapa)

        FastMarkerCluster(
            data=[
                [m["souradnice"][0], m["souradnice"][1], m["nazev mista"], m["problem mista"]]
                for m in nebezpecna_mista
            ],
            callback="""
            function (row) {
                var icon = L.divIcon({
                    className: "",
                    html: '<div style="width:10px;height:10px;border-radius:50%;background:#d62728;border:1px solid white;"></div>',
                    iconSize: [12, 12],
                    iconAnchor: [6, 6]
                });
                var marker = L.marker(new L.LatLng(row[0], row[1]), {icon: icon});
                if (row[2]) {
                    var tooltip = document.createElement("div");
                    tooltip.textContent = row[2];
                    marker.bindTooltip(tooltip);
                }
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
        vykresli_navigaci(mapa, route)

        if route is not None:
            summary = route["routes"][0]["summary"]
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
            podpis_kliku = (round(kliknuti["lat"], 6), round(kliknuti["lng"], 6))
            if podpis_kliku != st.session_state.get("navigace_posledni_klik"):
                st.session_state["navigace_posledni_klik"] = podpis_kliku
                if zpracuj_klik_navigace(kliknuti):
                    st.rerun()


if __name__ == "__main__":
    zobraz_navigaci()
