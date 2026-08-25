"""`query()` decide QUÉ píldoras cuentan como usadas; ya no decide CUÁNDO (V2-311, 2026-08-25).

El refuerzo (`access_count++`, `last_access=now`, `weight+step` — escritura durable) se disparaba al COMPONER el
paquete. Componer no es usar: medido sobre 223 sesiones vivas, 21 de 27 recalls se abandonaban al vencer el
presupuesto de 800 ms del turno **y su hilo terminaba igualmente**, así que el refuerzo se aplicaba a píldoras
por preguntas que nunca se contestaron con ellas. La señal de «esto se usa» la alimentaba el trabajo tirado.

Lo que se mueve fuera es el MOMENTO. Lo que se queda dentro —y esto es lo que estos casos clavan— es la
POLÍTICA: cuál es la selección. Si el disparador se hubiera llevado consigo la selección, el llamante habría
reforzado `ids` entero (el paquete: conceptos, vecinos de grafo, resultados laterales) y el refuerzo selectivo
habría desaparecido sin que fallara nada.
"""
from __future__ import annotations

import pytest

from memory import api as memory_api
from memory import db as memdb


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_la_seleccion_es_UNA_pildora_de_contenido_y_no_el_paquete():
    """El paquete lleva contexto; reforzarlo entero convierte una consulta de vivienda en «uso» de la alergia."""
    paquete = [{"id": 1, "kind": "concept"}, {"id": 2, "kind": "fact"}, {"id": 3, "kind": "fact"}]
    assert memory_api.reinforce_ids_for(paquete) == [2]


def test_los_nodos_CONCEPTO_no_cuentan_como_recuerdo_usado():
    """Son índices, no recuerdos vividos: reforzarlos infla el grafo por el hecho de haber navegado por él."""
    assert memory_api.reinforce_ids_for([{"id": 9, "kind": "concept"}]) == []
    assert memory_api.reinforce_ids_for([]) == []


def test_query_REPORTA_lo_reforzable_sin_escribir_cuando_no_se_le_pide(fresh_db, monkeypatch):
    """La pieza que hace posible mover el disparador: informar sin actuar."""
    escrituras: list = []
    monkeypatch.setattr(memory_api, "reinforce", lambda ids: escrituras.extend(ids))

    from memory import writer as memwriter
    mid = memwriter.insert_memory("vivo en el centro de Madrid", weight=0.5, level="long")

    res = memory_api.query("¿dónde vivo?", reinforce_used=False)

    assert "reinforce_ids" in res, "sin este campo quien entrega no sabe qué reforzar y acabaría reforzando `ids`"
    assert escrituras == [], "se le dijo que NO reforzara y escribió igual"
    if res["reinforce_ids"]:
        assert res["reinforce_ids"] == [mid]


def test_query_SIGUE_reforzando_cuando_se_le_pide(fresh_db, monkeypatch):
    """Otros llamantes (el dossier del worker) siguen entregando en el acto: mover el disparador no puede
    apagarles el refuerzo por la puerta de atrás."""
    escrituras: list = []
    monkeypatch.setattr(memory_api, "reinforce", lambda ids: escrituras.extend(ids))

    from memory import writer as memwriter
    memwriter.insert_memory("vivo en el centro de Madrid", weight=0.5, level="long")

    res = memory_api.query("¿dónde vivo?", reinforce_used=True)

    assert escrituras == res["reinforce_ids"], "el camino de siempre dejó de reforzar lo que decía reforzar"
