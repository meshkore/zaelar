"""A BUILD errand that mentions deleting its own entries builds, and a worker never deletes a card (V2-781 T531).

«Móntame un widget para mis entrenamientos… y el tiempo que le dediqué» became the errand «Crear un widget nuevo…
que se puedan añadir, editar y borrar entradas». `widget_action` checked the delete verb FIRST, «tiempo» resolved
to `clock`, and the generator DELETED the clock (folder+store+memory) and announced a workout widget that did not
exist. The first verb names the act; and deleting a card is a confirmed act (`pending_confirm`), never a side
effect inside a worker.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.agentes import code as C

BUILD_ES = ("Crear un widget nuevo para que el operador registre sus entrenamientos: cada entrada con la fecha y "
            "qué hizo, y el tiempo que le dedicó. Que se puedan añadir, editar y borrar entradas.")


@pytest.fixture
def clock_exists(monkeypatch):
    """The catalog is ENVIRONMENT: pin that «tiempo» resolves to an existing `clock`, never the live catalog."""
    monkeypatch.setattr(C, "_identify_widget",
                        lambda r: {"match": "clock" if "tiempo" in r or "reloj" in r else None,
                                   "ambiguous": False, "candidates": []})


def test_a_build_that_mentions_deleting_entries_is_a_create(clock_exists):
    assert C.widget_action(BUILD_ES) == ("create", "")


def test_a_delete_order_is_still_a_delete(clock_exists):
    assert C.widget_action("borra el widget del reloj") == ("delete", "clock")
    assert C.widget_action("borra el reloj que creaste ayer") == ("delete", "clock")


def test_the_generator_worker_never_deletes_a_card(clock_exists, monkeypatch):
    from widgets import lifecycle
    from nucleo.workers.generator_session import GeneratorBackend
    from nucleo.workers.base import WorkerSpec
    deleted = []

    async def _delete(wid, src="system"):
        deleted.append(wid)
        return {"ok": True}
    monkeypatch.setattr(lifecycle, "delete_widget", _delete)

    async def _go():
        b = GeneratorBackend()
        await b.start("", spec=WorkerSpec(task_id="T531", kind="code",
                                          env={"ZAELAR_TASK_REQUEST": "borra el widget del reloj"}))
        await b._run_task
        out = []
        while not b._q.empty():
            out.append(b._q.get_nowait())
        return out
    events = asyncio.run(_go())
    assert deleted == [], "a worker deleted a card with no confirmation of its own"
    result = [e for e in events if e.type == "result"]
    assert result and result[0].data.get("ok") is False, events
