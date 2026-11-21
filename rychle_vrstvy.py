"""Pomůcky pro rychlou mapu, která se po načtení stránky už znovu nenačítá.

Jak to funguje:
- Základní mapa (podklad, vlastní body, nástroj na úpravy) je při každém běhu stejná,
  takže ji streamlit-folium nepřekresluje.
- Všechno, co se mění s filtry (body, oblasti kriminality, osvětlení, trasa…), se předává
  jako samostatné vrstvy přes `st_folium(feature_group_to_add=[...])` – v prohlížeči se
  vymění jen tyto vrstvy, mapa zůstane na stejném místě a přiblížení.
- Tmavá mapa a skrytí vlastních bodů se jen přepnou CSS třídou na mapě (`PrepinacMapy`).
- Malá data se převedou na text jen jednou (`RychlyGeoJson`), místo aby je folium při
  každém kliknutí znovu zpracovávalo.
- Velká neměnná data (osvětlení, tvary oblastí) jsou ve složce static a prohlížeč si je
  stáhne jen jednou (`GeoJsonZeSouboru`) – dřív se při každém kliknutí posílaly znovu
  a jen jejich zpracování trvalo ~4 s.
"""

import hashlib
import json
import math
from pathlib import Path

from branca.element import MacroElement
from jinja2 import Template


class RychlyGeoJson(MacroElement):
    """GeoJSON vrstva z hotového JSON textu; vzhled, popisky apod. řeší JS `moznosti_js`.

    `data_json` je už převedený text (např. z funkce s @st.cache_data), takže se při
    vykreslení jen vloží – bez procházení dat ve folium."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = L.geoJSON(
            {{ this.data_json }},
            {{ this.moznosti_js }}
        ).addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, data_json, moznosti_js="{}"):
        super().__init__()
        self._name = "RychlyGeoJson"
        self.data_json = data_json
        self.moznosti_js = moznosti_js


class GeoJsonZeSouboru(MacroElement):
    """GeoJSON vrstva, jejíž data si prohlížeč stáhne ze statického souboru (jen jednou,
    pak je má v paměti), takže se velká data neposílají při každém kliknutí znovu.

    `soubor` je název souboru ve složce static (viz `uloz_staticky_soubor`).
    `vlastnosti_json` (nepovinné) je JSON seznam vlastností pro jednotlivé tvary ve stejném
    pořadí – tak se dá měnit např. barva oblastí podle filtru, aniž by se znovu posílaly tvary.
    """

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        (function () {
            var skupina = {{ this._parent.get_name() }};
            // Komponenta mapy běží na adrese .../component/...; statické soubory jsou na .../app/static/
            var url = window.location.href.split("/component/")[0] + "/app/static/" + {{ this.soubor|tojson }};
            window.__staticka_data = window.__staticka_data || {};
            var data = window.__staticka_data[url] ||
                (window.__staticka_data[url] = fetch(url).then(function (r) { return r.json(); }));
            var vlastnosti = {{ this.vlastnosti_json }};
            // Vlastní "patro" mapy: data přijdou až po stažení, ale vrstva i tak zůstane
            // pod body a trasou (ty jsou v overlayPane se z-index 400)
            var mapa = {{ this._parent._parent.get_name() }};
            if (!mapa.getPane({{ this.pane|tojson }})) {
                mapa.createPane({{ this.pane|tojson }}).style.zIndex = {{ this.pane_z }};
            }
            data.then(function (geojson) {
                if (vlastnosti) {
                    geojson = {type: "FeatureCollection", features: geojson.features.map(function (f, i) {
                        return {type: "Feature", geometry: f.geometry, properties: vlastnosti[i]};
                    })};
                }
                var moznosti = {{ this.moznosti_js }};
                moznosti.pane = {{ this.pane|tojson }};
                L.geoJSON(geojson, moznosti).addTo(skupina);
            });
        })();
        {% endmacro %}
        """
    )

    def __init__(self, soubor, moznosti_js="{}", vlastnosti_json="null", pane="podkladova_data", pane_z=350):
        super().__init__()
        self._name = "GeoJsonZeSouboru"
        self.soubor = soubor
        self.moznosti_js = moznosti_js
        self.vlastnosti_json = vlastnosti_json
        # Leaflet "pane" = patro mapy; nižší pane_z je níž (body a trasa mají 400)
        self.pane = pane
        self.pane_z = int(pane_z)


STATICKA_SLOZKA = Path(__file__).with_name("static")


def uloz_staticky_soubor(nazev, text):
    """Uloží text do složky static (Streamlit ji servíruje na /app/static/, musí být zapnuté
    server.enableStaticServing). Vrací název i s verzí, aby prohlížeč po změně dat
    nepoužil starou kopii."""
    STATICKA_SLOZKA.mkdir(exist_ok=True)
    cesta = STATICKA_SLOZKA / nazev
    if not cesta.exists() or cesta.read_text(encoding="utf-8") != text:
        cesta.write_text(text, encoding="utf-8")
    verze = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{nazev}?v={verze}"


class PrepinacMapy(MacroElement):
    """Přepne CSS třídy na kontejneru mapy (např. tmavý podklad) bez překreslení mapy.

    Musí být uvnitř vrstvy (FeatureGroup) předané do `feature_group_to_add`."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        (function () {
            var kontejner = {{ this._parent._parent.get_name() }}.getContainer();
            {% for trida, zapnuto in this.tridy.items() %}
            kontejner.classList.toggle({{ trida|tojson }}, {{ zapnuto|tojson }});
            {% endfor %}
        })();
        {% endmacro %}
        """
    )

    def __init__(self, **tridy):
        super().__init__()
        self._name = "PrepinacMapy"
        # Pythonní názvy (tmava_mapa) -> CSS třídy (tmava-mapa)
        self.tridy = {nazev.replace("_", "-"): bool(zapnuto) for nazev, zapnuto in tridy.items()}


# --- Zjednodušení čar osvětlení ------------------------------------------------------

_COS_OLOMOUC = math.cos(math.radians(49.6))


def _spoj_useky(useky):
    """Spojí úseky, které na sebe navazují (konec jednoho = začátek dalšího)."""
    podle_zacatku = {}
    for i, usek in enumerate(useky):
        podle_zacatku.setdefault(tuple(usek[0]), []).append(i)

    pouzito = [False] * len(useky)
    cary = []
    for i, usek in enumerate(useky):
        if pouzito[i]:
            continue
        pouzito[i] = True
        cara = list(usek)
        while True:
            dalsi = next(
                (j for j in podle_zacatku.get(tuple(cara[-1]), []) if not pouzito[j]),
                None,
            )
            if dalsi is None:
                break
            pouzito[dalsi] = True
            cara.extend(useky[dalsi][1:])
        cary.append(cara)
    return cary


def _zjednodus_caru(body, tolerance_m):
    """Douglas–Peucker: vynechá body, které čáru posunou méně než o `tolerance_m`."""
    if len(body) < 3:
        return body
    tolerance = tolerance_m / 111_000
    xy = [(x * _COS_OLOMOUC, y) for x, y in body]
    ponechat = [False] * len(body)
    ponechat[0] = ponechat[-1] = True
    zasobnik = [(0, len(body) - 1)]
    while zasobnik:
        a, b = zasobnik.pop()
        ax, ay = xy[a]
        bx, by = xy[b]
        dx, dy = bx - ax, by - ay
        delka = math.hypot(dx, dy)
        nejvic, index = -1.0, -1
        for k in range(a + 1, b):
            px, py = xy[k]
            if delka == 0:
                vzdalenost = math.hypot(px - ax, py - ay)
            else:
                vzdalenost = abs(dy * px - dx * py + bx * ay - by * ax) / delka
            if vzdalenost > nejvic:
                nejvic, index = vzdalenost, k
        if nejvic > tolerance:
            ponechat[index] = True
            zasobnik.append((a, index))
            zasobnik.append((index, b))
    return [bod for bod, drzet in zip(body, ponechat) if drzet]


def zjednodus_osvetleni(geojson, tolerance_m=1.0):
    """Vrátí menší kopii osvětlení (MultiLineString po úrovních) – na mapě vypadá stejně,
    ale má zhruba poloviční velikost, takže se rychleji posílá i vykresluje."""
    features = []
    for feature in geojson["features"]:
        geometrie = feature["geometry"]
        cary = geometrie["coordinates"] if geometrie["type"] == "MultiLineString" else [geometrie["coordinates"]]
        cary = [_zjednodus_caru(cara, tolerance_m) for cara in _spoj_useky(cary)]
        features.append({
            "type": "Feature",
            "geometry": {"type": "MultiLineString", "coordinates": cary},
            "properties": feature["properties"],
        })
    return {"type": "FeatureCollection", "features": features}


def na_json(data):
    """Kompaktní JSON (bez mezer) pro vložení do <script> v mapě."""
    # "</" by uvnitř <script> mohlo ukončit skript (např. v textu od uživatele)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
