import json    
import anthropic    #oficialni knihovna pro AI Claude
import streamlit as st    

from kategorie import NAZVY, V_NABIDCE, _ODPOVEDI    #kategorie a roztrizeni

MODEL = "claude-haiku-5-5"    #maly, rychly a levny model


def _vyber_priklady(na_kategorii=4):
    """Vybere z vaseho roztrideni par kratkych prikladu, aby AI tridila stejne jako vy."""
    priklady = []
    pocty = {k: 0 for k in V_NABIDCE}
    vice_kategorii = []
    for text, kategorie in _ODPOVEDI.items():
        kategorie = [k for k in kategorie if k in V_NABIDCE]
        if len(text) > 100:
            continue
        if len(kategorie) == 1 and pocty[kategorie[0]] < na_kategorii:
            pocty[kategorie[0]] += 1
            priklady.append((text, kategorie))
        elif len(kategorie) >= 2 and len(vice_kategorii) < 6:
            vice_kategorii.append((text, kategorie))
    return priklady + vice_kategorii


# Pokyny pro AI – sestavi se jednou pri spusteni aplikace
_seznam = "\n".join(f"- {k}: {NAZVY[k]}" for k in V_NABIDCE)
_ukazky = "\n".join(f"„{t}“ → {', '.join(k)}" for t, k in _vyber_priklady())
_POKYNY = f"""Třídíš hlášení o místech v Olomouci, kde se lidé necítí bezpečně.
Přiřaď hlášení všechny kategorie, které na něj sedí (klidně víc). Když nesedí žádná, vrať prázdný seznam.
Samotná zmínka o etnické nebo sociální skupině do žádné kategorie nepatří.

Kategorie:
{_seznam}

Příklady, jak třídí náš tým:
{_ukazky}"""

# AI smi odpovedet jen klici z vasi nabidky
_SCHEMA = {
    "type": "object",
    "properties": {
        "kategorie": {"type": "array", "items": {"type": "string", "enum": V_NABIDCE}}
    },
    "required": ["kategorie"],
    "additionalProperties": False,
}


def zarad_pomoci_ai(nazev, popis):
    """Vrati seznam kategorii, napr. ["tma", "podchody"].
    Prazdny seznam = zadna kategorie nesedi. None = AI neni dostupna."""
    try:
        client = anthropic.Anthropic(
            api_key=st.secrets["ANTHROPIC_API_KEY"], timeout=20.0, max_retries=1
        )
        odpoved = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=_POKYNY,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": f"Název: {nazev}\nPopis: {popis}"}],
        )
        if odpoved.stop_reason != "end_turn":
            return None
        text = next(b.text for b in odpoved.content if b.type == "text")
        vybrane = json.loads(text)["kategorie"]
        return [k for k in V_NABIDCE if k in vybrane]    #ve stejnem poradi jako nabidka
    except (anthropic.APIError, KeyError, ValueError, StopIteration):
        return None
