"""The research brief composes IN PARALLEL with the worker's spawn (V2-301).

Measured across the guitar rounds (2026-08-24): the composer is a REASONING call (15-30 s) and it ran in
series BEFORE the spawn — the worker sat "in the queue" 20-32 s doing nothing while the composer thought, and then
spent its OWN first ~20 s on preamble (mesh STEP 0 + memory reads). Two stretches that overlap perfectly.
That dead time is what pushed an end-to-end search past the operator's 2-3 minute bar ("a search of this
kind should take two to three minutes").

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
    """The same fail-open behavior as the serial path: without a brief there is nothing to inject, but the
    research budget does not depend on the composer being alive (2026-08-13 incident: worker dead at 704 s
    with half the budget remaining)."""
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
    """`compose` returning None outright said "this does not call for breadth or a research standard": no
    injection or promotion — promoting here would charge research budget to a task that is not research."""
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
    """Edge case: injecting into a dead session is noise on the channel; saving the brief is still worthwhile
    (a round 2 of the same request inherits it)."""
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
    """The wiring guard (source WITHOUT comments): the head start and follow-up must be on the real
    `run_listener` path — a test that only exercises the callback passes even with the hook removed."""
    import inspect
    src = "\n".join(ln for ln in inspect.getsource(D._run_session).splitlines()
                    if not ln.strip().startswith("#"))
    assert "ZAELAR_BRIEF_HEAD_START_S" in src, "el head start desapareció del camino real"
    assert "_attach_brief_followup(_brief_bg" in src, "el brief tardío no llega a nadie sin este enganche"
    assert "NO la esperes parado" in src, "el prompt tiene que avisar de que la dirección viene en camino"
