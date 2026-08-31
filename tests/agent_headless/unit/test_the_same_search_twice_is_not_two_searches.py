"""56 web searches, 31 queries, 0 candidates: that is not diligence, it is going in circles.

Measured on `weekend-plan-barcelona__es` (2026-08-28, 24/7 set). The judge wrote it in these words:
*«repeating the same query without changing the criteria… a request is considered, searched once with the
conditions in place, and delivered»*. Each turn costs the client seconds, the provider's quota, and a turn
of conversation in which zaelar says it is still searching.

The repetition is NOT blocked, it is ANSWERED — and marked. Blocking it would break a legitimate retry; returning
the same thing instantly cuts the loop just as well, and also records the fact (`repeated`), which is what turns
«went in circles» from an impression into data.

The short TTL (120 s) IS the design, not an isolated parameter: long enough to kill a tight loop —56 searches
in nine minutes—, short enough for a «look again» at a human pace to bring fresh information. A search cache
that lasts longer than a person's patience serves stale data to precisely the person who asked for the opposite.
"""
from __future__ import annotations

import pytest

from nucleo import websearch as W


@pytest.fixture(autouse=True)
def _limpio():
    W._recent.clear()
    yield
    W._recent.clear()


def _backend_contador(monkeypatch, veces: list):
    def _b(q, k):
        veces.append(q)
        return {"query": q, "answer": "", "results": [{"title": f"r{len(veces)}", "url": "u", "snippet": ""}],
                "source": "ddg", "ai": False}
    monkeypatch.setattr(W, "_order", lambda: ["ddg"])
    monkeypatch.setitem(W._BACKENDS, "ddg", _b)


def test_la_segunda_vez_no_sale_a_la_red(monkeypatch):
    veces: list = []
    _backend_contador(monkeypatch, veces)
    a = W.search("salas de conciertos barcelona", 5)
    b = W.search("salas de conciertos barcelona", 5)
    assert len(veces) == 1, "la segunda consulta idéntica no puede volver a gastar red"
    assert b["results"] == a["results"]


def test_y_lo_DICE(monkeypatch):
    """Without the marker, «went in circles» remains an impression of the judge rather than a fact in the report."""
    veces: list = []
    _backend_contador(monkeypatch, veces)
    W.search("hoteles en sevilla", 5)
    b = W.search("hoteles en sevilla", 5)
    assert b["repeated"]["n"] >= 1 and b["repeated"]["ttl_s"] == 120


def test_la_primera_no_lleva_marca(monkeypatch):
    """The sensitivity half: a marker that always appears stops being a marker."""
    _backend_contador(monkeypatch, [])
    assert "repeated" not in W.search("algo nuevo", 5)


def test_dos_consultas_DISTINTAS_son_dos_busquedas(monkeypatch):
    veces: list = []
    _backend_contador(monkeypatch, veces)
    W.search("fontanero madrid", 5)
    W.search("fontanero barcelona", 5)
    assert len(veces) == 2


def test_la_misma_consulta_con_otro_espaciado_o_mayusculas_es_la_misma(monkeypatch):
    veces: list = []
    _backend_contador(monkeypatch, veces)
    W.search("Salas   de Conciertos BARCELONA", 5)
    W.search("salas de conciertos barcelona", 5)
    assert len(veces) == 1


def test_pasado_el_TTL_se_vuelve_a_buscar(monkeypatch):
    """A «look again» at a human pace has to bring fresh information."""
    veces: list = []
    _backend_contador(monkeypatch, veces)
    W.search("conciertos este finde", 5)
    ahora = W._time.time()
    monkeypatch.setattr(W._time, "time", lambda: ahora + W._REPEAT_TTL_S + 1)
    W.search("conciertos este finde", 5)
    assert len(veces) == 2


def test_no_se_cobra_dos_veces_por_una_sola_peticion(monkeypatch):
    """`_meter_search` charges for what a provider ANSWERED. A response served from memory did not do so."""
    cobros: list = []
    monkeypatch.setattr(W, "_meter_search", lambda src: cobros.append(src))
    _backend_contador(monkeypatch, [])
    W.search("un seguro barato", 5)
    W.search("un seguro barato", 5)
    assert len(cobros) == 1


def test_esta_acotado(monkeypatch):
    """It lives in the engine process: it is not a store and cannot grow without limit."""
    _backend_contador(monkeypatch, [])
    for i in range(W._REPEAT_MAX + 20):
        W.search(f"consulta numero {i}", 5)
    assert len(W._recent) <= W._REPEAT_MAX
