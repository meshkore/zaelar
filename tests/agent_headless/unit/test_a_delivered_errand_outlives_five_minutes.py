"""A DELIVERED errand stays a fact for the conversation, not five minutes (node 2.552).

three-tasks-at-once (ES, 2026-10-11 11:34, sandbox 113401-es, prompts 7 and 8). The car report finished at 11:36:55;
the monitor hunt and the game finished at 11:42:28. That turn's prompt listed the monitor and the game under
«TAREAS DE FONDO — YA ACABADAS» and NOT the report — it was 333 s old, past `JUST_ENDED_S` — and asked «¿el informe
ese en qué punto está?», the reply was «del informe no me consta ningún dato todavía» with the report open on his
screen. Three errands at once outlive five minutes. A death or a stop keeps the short window its notice machinery
was measured with (V2-221/224); a delivery stays for `DELIVERED_KEPT_S`, and the block's cap of three keeps the
prompt the size it was.
"""
from __future__ import annotations

import time

import pytest

from nucleo import dispatch
from nucleo.workers import ended


@pytest.fixture(autouse=True)
def _clean():
    dispatch._SESSIONS.clear()
    dispatch._ENDED_SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()
    dispatch._ENDED_SESSIONS.clear()


def _ended(tid: str, goal: str, *, ok: bool = True, status: str = "done", ago: float = 0.0) -> None:
    r = dispatch.SessionRecord(task_id=tid, goal=goal, kind="generic")
    r.status, r.ok, r.result_summary = status, ok, f"{goal[:20]} listo"
    dispatch._SESSIONS[tid] = r
    dispatch._remember_ended(r)                  # the path `_run_session`'s `finally` takes
    dispatch._SESSIONS.pop(tid, None)
    dispatch._ENDED_SESSIONS[tid]["at"] = time.time() - ago


def _block() -> str:
    from nucleo.flash import prompt as _p
    return next((ln for ln in _p.live_state().splitlines() if ln.startswith("TAREAS DE FONDO — YA ACABADAS")), "")


def test_the_report_is_still_in_the_block_beside_two_later_endings():
    _ended("1", "Elaborar un INFORME escrito sobre coches eléctricos para uso urbano", ago=333)
    _ended("3", "Buscar monitores de segunda mano baratos", ago=5)
    _ended("6", "Crear un widget nuevo: un juego de plataformas tipo Super Mario", ago=2)
    block = _block()
    assert "INFORME escrito sobre coches" in block, block
    assert "monitores" in block and "juego de plataformas" in block


def test_a_death_still_leaves_after_five_minutes():
    _ended("2", "Reservar una mesa para cuatro", ok=False, status="error", ago=ended.JUST_ENDED_S + 30)
    assert _block() == "", "the death notice machinery was measured with the short window"


def test_a_delivery_is_not_a_fact_forever():
    _ended("1", "Elaborar un INFORME escrito sobre coches eléctricos", ago=ended.DELIVERED_KEPT_S + 30)
    assert _block() == ""


def test_the_block_keeps_its_cap():
    for i in range(5):
        _ended(str(i), f"Encargo número {i} de la tarde con su propio objetivo", ago=10 + i)
    assert _block().count("TERMINÓ") == 3, "the prompt does not grow: three endings at most, newest first"
