"""The research brief composes IN PARALLEL with the worker's spawn (V2-301).

Measured across the guitar rounds (2026-08-24): the composer is a REASONING call (15-30 s) and it ran in
series BEFORE the spawn — the worker sat «en cola» 20-32 s doing nothing while the composer thought, and then
spent its OWN first ~20 s on preamble (mesh PASO 0 + memory reads). Two stretches that overlap perfectly.
That dead time is what pushed an end-to-end search past the operator's 2-3 minute bar («una búsqueda de este
tipo debería durar de dos a tres minutos»).

The design: a short head start keeps every INSTANT path fully-directed (a resumed or round-2 brief returns
with no LLM call at all); past it, the worker spawns NOW and the brief arrives as an injected turn — the same
channel every mid-task refinement already uses (V2-038). These tests drive `_attach_brief_followup`, the half
that runs after the spawn, through a real asyncio task — not by calling the callback by hand, which would
stay green with the `add_done_callback` line deleted (the V2-199 lesson).
"""
import asyncio

import pytest

from nucleo import dispatch as D
from nucleo import research


class _Rec:
    status = "running"
    kind = "generic"
    label = ""


def _wire(monkeypatch):
    """Capture every side effect the follow-up is supposed to produce."""
    calls = {"saved": [], "rounds": [], "injected": [], "synced": 0, "seeded": []}
    monkeypatch.setattr(research, "save", lambda k, b: calls["saved"].append((k, b)))
    monkeypatch.setattr(research, "remember_round", lambda g, b: calls["rounds"].append(g))
    monkeypatch.setattr(research, "to_prompt_block", lambda b: "== BRIEF ==")
    monkeypatch.setattr(D, "inject_soon", lambda k, m: calls["injected"].append((k, m)))
    monkeypatch.setattr(D, "sync_state", lambda: calls.__setitem__("synced", calls["synced"] + 1))

    async def _seed(b):
        calls["seeded"].append(b)
    monkeypatch.setattr(D, "_seed_research_criteria", _seed)
    return calls


async def _run_followup(result, rec, monkeypatch, *, kind0="generic"):
    calls = _wire(monkeypatch)

    async def _compose():
        if isinstance(result, BaseException):
            raise result
        return result

    task = asyncio.ensure_future(_compose())
    D._attach_brief_followup(task, key="42", rec=rec, req="busca una guitarra", kind0=kind0)
    for _ in range(20):                      # give the loop turns for the callback + ensure_future chain
        await asyncio.sleep(0)
    return calls


def test_a_late_brief_reaches_the_running_worker_and_promotes_the_budget():
    mp = pytest.MonkeyPatch()
    try:
        async def go():
            rec = _Rec()
            calls = await _run_followup({"round": 1}, rec, mp)
            return rec, calls
        rec, calls = asyncio.run(go())
        assert calls["saved"] and calls["rounds"] and calls["seeded"], "el camino serial persiste; el tardío también"
        assert calls["injected"] and "== BRIEF ==" in calls["injected"][0][1], \
            "la dirección tiene que LLEGAR al worker que ya corre — sin inyección el paralelismo es perderla"
        assert rec.kind == "research", "el brief es la prueba de que es una investigación: presupuesto research"
    finally:
        mp.undo()


def test_a_dead_composer_still_promotes_but_injects_nothing():
    """El mismo fail-open que el camino serial: sin brief no hay nada que inyectar, pero el presupuesto de
    investigación no depende de que el compositor esté vivo (banco del 2026-08-13: worker muerto a los 704 s
    con medio presupuesto)."""
    mp = pytest.MonkeyPatch()
    try:
        async def go():
            rec = _Rec()
            calls = await _run_followup(research.ComposerUnavailable("timeout"), rec, mp)
            return rec, calls
        rec, calls = asyncio.run(go())
        assert not calls["injected"] and not calls["saved"]
        assert rec.kind == "research"
    finally:
        mp.undo()


def test_not_an_investigation_changes_nothing():
    """`compose` devolviendo None a secas dijo «esto no pide amplitud ni baremo»: ni inyección ni promoción —
    promocionar aquí cobraría presupuesto de investigación a una tarea que no lo es."""
    mp = pytest.MonkeyPatch()
    try:
        async def go():
            rec = _Rec()
            calls = await _run_followup(None, rec, mp)
            return rec, calls
        rec, calls = asyncio.run(go())
        assert not calls["injected"] and not calls["saved"]
        assert rec.kind == "generic"
    finally:
        mp.undo()


def test_a_finished_worker_gets_no_injection():
    """Sensibilidad: inyectar a una sesión muerta es ruido en el canal; guardar el brief sí vale (una ronda 2
    del mismo encargo lo hereda)."""
    mp = pytest.MonkeyPatch()
    try:
        async def go():
            rec = _Rec()
            rec.status = "done"
            calls = await _run_followup({"round": 1}, rec, mp)
            return rec, calls
        rec, calls = asyncio.run(go())
        assert calls["saved"] and not calls["injected"]
    finally:
        mp.undo()


def test_the_spawn_path_actually_wires_the_followup():
    """La guarda de cableado (fuente SIN comentarios): el head start y el follow-up tienen que estar en el
    camino real de `run_listener` — un test que solo prueba el callback pasa igual con el enganche borrado."""
    import inspect
    src = "\n".join(ln for ln in inspect.getsource(D._run_session).splitlines()
                    if not ln.strip().startswith("#"))
    assert "ZAELAR_BRIEF_HEAD_START_S" in src, "el head start desapareció del camino real"
    assert "_attach_brief_followup(_brief_bg" in src, "el brief tardío no llega a nadie sin este enganche"
    assert "NO la esperes parado" in src, "el prompt tiene que avisar de que la dirección viene en camino"
