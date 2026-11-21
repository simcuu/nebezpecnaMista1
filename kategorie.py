import json    
from pathlib import Path    #Path pomaha najit soubor vedle tohoto skriptu

# Nacteni rucniho rozrazeni odpovedi z kategorie.json
# (soubor lezi ve stejne slozce jako tento skript)
with Path(__file__).with_name("kategorie.json").open(encoding="utf-8") as f:
    _data = json.load(f)

# klic kategorie -> nazev, ktery uvidi uzivatel, napr. "tma" -> "Tma, špatné osvětlení"
NAZVY = _data["kategorie"]

# kategorie, ktere nabizime v bocnim panelu (bez "nenavist" – ta jen popisuje odpoved)
V_NABIDCE = _data["v_nabidce"]

# text odpovedi respondenta -> seznam klicu kategorii
_ODPOVEDI = _data["odpovedi"]


def zarad_kategorie(duvod):
    """Vrati seznam kategorii pro text odpovedi, napr. "tma" -> ["tma"].
    Kdyz odpoved v rozrazeni neni, vrati prazdny seznam."""
    text = (duvod or "").replace("\r\n", "\n").strip()
    return _ODPOVEDI.get(text, [])
