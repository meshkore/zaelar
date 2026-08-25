"""V2-320 — un worker que resuelve BUSCANDO dejaba la hoja vacía siempre, por construcción.

Medido en `kid-friendly-activity-nearby` (2026-08-25 12:37): worker vivo 709 s, 8 búsquedas web, 7 returns,
0 navegaciones — y la hoja vacía de punta a punta. El return de búsqueda tenía UN solo camino: la nota al
cerebro (`hand_web_finding`), que el turno lee una vez y se gasta. La hoja no los rechazaba (`_to_item`
acepta título+url sin precio, comprobado antes de tocar nada): no tenían puerta. Buscar es una forma
legítima de resolver «actividades cerca», así que sus hallazgos son hallazgos.
"""
from __future__ import annotations

import pytest

from nucleo.workers import findings
from widgets import store
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    yield
    store._last_hash.clear()


class _Rec:
    task_id = "t1"
    goal = "actividades para niños cerca"
    sheet = "hoja-k"


RES = {"query": "actividades niños Madrid", "source": "tavily", "results": [
    {"title": "Parque de atracciones de Madrid", "snippet": "Atracciones para todas las edades…",
     "url": "https://x/parque"},
    {"title": "Faunia", "snippet": "Naturaleza y animales", "url": "https://x/faunia"},
    {"title": "", "snippet": "", "url": "https://x/cita-sin-titulo"},          # cita pelada de Perplexity
]}


def test_el_return_de_busqueda_llega_a_la_hoja_del_encargo():
    n = findings.hand_search_rows(_Rec(), RES)
    assert n == 2, "las filas con nombre tenían que entrar; la cita sin título, no"
    items = sheet.view_data("hoja-k")["items"]
    assert [i["title"] for i in items] == ["Parque de atracciones de Madrid", "Faunia"]
    assert items[0]["url"] == "https://x/parque"
    assert "Atracciones" in items[0].get("subtitle", ""), "el snippet es lo que hace legible la fila"


def test_ocho_busquedas_solapadas_CONVERGEN_en_vez_de_apilar():
    """El ejemplar real hizo 8 búsquedas. Sin el dedup de la hoja (título+url), la misma Faunia saldría ocho
    veces y la hoja parecería llena de hallazgos que son uno."""
    for _ in range(8):
        findings.hand_search_rows(_Rec(), RES)
    assert len(sheet.view_data("hoja-k")["items"]) == 2


def test_la_fuente_queda_en_la_pestana_de_fuentes():
    findings.hand_search_rows(_Rec(), RES)
    fuentes = sheet.view_data("hoja-k").get("sources") or []
    assert any("búsqueda web" in str(f.get("name") or "") for f in fuentes), \
        "de dónde salió esto también es parte del informe"


def test_un_return_vacio_o_roto_no_toca_la_hoja_ni_revienta():
    assert findings.hand_search_rows(_Rec(), {"results": []}) == 0
    assert findings.hand_search_rows(_Rec(), {}) == 0
    assert findings.hand_search_rows(_Rec(), {"results": "no-es-una-lista"}) == 0
    assert sheet.view_data("hoja-k")["items"] == []


def test_el_worker_api_lo_llama_donde_entrega_la_nota():
    """Guarda de CABLEADO por AST: la función puede estar perfecta y no servir de nada si la costura que
    recibe el return no la llama — que es literalmente el defecto que arregla."""
    import ast
    src = ast.parse(open("nucleo/worker_api.py", encoding="utf8").read())
    fn = next(n for n in ast.walk(src)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_exec_allow")
    llamadas = [getattr(c.func, "attr", getattr(c.func, "id", "")) for c in ast.walk(fn) if isinstance(c, ast.Call)]
    assert "hand_web_finding" in llamadas, "¿la nota desapareció? eso es OTRA regresión (V2-236)"
    assert "hand_search_rows" in llamadas, \
        "el return de búsqueda volvió a tener un solo camino: la nota que se gasta en un turno — la hoja queda vacía"
