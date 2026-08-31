"""`query()` decides WHICH pills count as used; it no longer decides WHEN (V2-311, 2026-08-25).

Reinforcement (`access_count++`, `last_access=now`, `weight+step` — durable write) was triggered when COMPOSING the
bundle. Composing is not using: measured across 223 live sessions, 21 of 27 recalls were abandoned when the turn's
800 ms budget expired **and its thread still terminated**, so reinforcement was applied to pills for questions that
were never answered with them. The signal that «this is used» was being fed by discarded work.

What moves outside is the TIMING. What stays inside —and this is what these cases pin down— is the
POLICY: which selection is made. If the trigger had taken the selection with it, the caller would have
reinforced all of `ids` (the bundle: concepts, graph neighbors, side results), and selective reinforcement
would have disappeared without anything failing.
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
    """The bundle carries context; reinforcing it wholesale turns a housing query into «use» of the allergy."""
    paquete = [{"id": 1, "kind": "concept"}, {"id": 2, "kind": "fact"}, {"id": 3, "kind": "fact"}]
    assert memory_api.reinforce_ids_for(paquete) == [2]


def test_los_nodos_CONCEPTO_no_cuentan_como_recuerdo_usado():
    """They are indexes, not lived memories: reinforcing them inflates the graph merely because it was navigated."""
    assert memory_api.reinforce_ids_for([{"id": 9, "kind": "concept"}]) == []
    assert memory_api.reinforce_ids_for([]) == []


def test_query_REPORTA_lo_reforzable_sin_escribir_cuando_no_se_le_pide(fresh_db, monkeypatch):
    """The piece that makes moving the trigger possible: report without acting."""
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
    """Other callers (the worker's dossier) still deliver immediately: moving the trigger cannot
    silently turn off their reinforcement."""
    escrituras: list = []
    monkeypatch.setattr(memory_api, "reinforce", lambda ids: escrituras.extend(ids))

    from memory import writer as memwriter
    memwriter.insert_memory("vivo en el centro de Madrid", weight=0.5, level="long")

    res = memory_api.query("¿dónde vivo?", reinforce_used=True)

    assert escrituras == res["reinforce_ids"], "el camino de siempre dejó de reforzar lo que decía reforzar"
