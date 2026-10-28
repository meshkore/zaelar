"""An answer-only search result is not «nothing useful»: the composing pass is not told to offer the browser.

Use case `quick-fact-opening-hours` ES (2026-10-14): Gemini grounding returns a synthesised answer with no ranked
pages (`n: 0`). `compose_system` keyed the «la búsqueda no ha devuelto nada útil … ofrécete a mirarlo a fondo
con el navegador» tail on `results` alone, so a fact the provider DID answer was composed as an empty search —
the instruction that turns a one-search fact into a Brain Worker on the operator's «sí».
"""
from __future__ import annotations

from nucleo.acts import search as st

_Q = "¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?"


def test_an_answer_with_no_pages_gets_no_empty_search_tail():
    res = {"answer": "Abre a las 10:00; la entrada general cuesta 15 €.", "results": [], "source": "gemini", "ai": True}
    sysm = st.compose_system(_Q, "Museo del Prado horario y precio", res, "RESPUESTA: Abre a las 10:00; 15 €.")
    assert "LA BÚSQUEDA SÍ SE HA HECHO" not in sysm and "navegador" not in sysm


def test_a_truly_empty_search_still_says_why():
    res = {"answer": "", "results": [], "source": "none", "failure": {"kind": "quota", "detail": "x"}}
    sysm = st.compose_system(_Q, "Museo del Prado horario y precio", res, "")
    assert "LA BÚSQUEDA SÍ SE HA HECHO" in sysm and "cuota" in sysm
