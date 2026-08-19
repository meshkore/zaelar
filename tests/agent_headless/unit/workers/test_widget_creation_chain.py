"""V2-139 (`build-workout-tracker-widget`) — the chain from «móntame un widget» to a card on screen, walked.

V2-115 left this written down as its own primary open task, in CLAUDE.md: *«Creating a new widget has no
end-to-end test at all — that's what let failure (2) live indefinitely. Every link is tested in isolation; the
chain isn't.»* Failure (2) there was a widget that got created, announced by voice («He creado el widget X») and
opened by nobody, because the id travelled in the `result`'s `data` and `session.py` drops `data`.

This case is exactly that chain, and its success criterion is mechanical: the report must show the `widget`
family and a generation task, not zaelar saying «ya lo tienes».

The generator itself is stubbed — it launches a real `claude` CLI and takes a minute or two, which belongs to a
live node. What is walked here is every SEAM between the links, which is where the silent failures have been:
a break in any of them produces a worker that never emits a `widget` family, and the judge sees the model
narrating a widget that does not exist.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import dispatch
from nucleo.agentes import code as code_helpers
from nucleo.workers import registry
from nucleo.workers.base import WorkerSpec
from nucleo.flash import router_guards as g


ASK = "Móntame un widget para ir apuntando mis entrenamientos, con el día y qué hice."


def _spec(req: str, kind: str = "code") -> WorkerSpec:
    return WorkerSpec(task_id="T-chain", kind=kind, env={"ZAELAR_TASK_REQUEST": req})


# ── link 1: the sentence is a widget CREATION ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ask", [
    ASK,
    "móntame un panel de entrenamientos",          # «panel», no «widget»
    "créame un widget para mis gastos",
    "hazme un widget de peso diario",
    "constrúyeme un widget de hábitos",
])
def test_the_ask_is_recognised_and_routed_to_code(ask):
    assert g.looks_like_create_widget(ask) is True
    assert dispatch._classify_kind(ask) == "code"


# ── link 2: a `code` task about a widget picks the GENERATOR, not the generic worker ────────────────────────
@pytest.mark.parametrize("ask", [
    ASK,
    "móntame un panel de entrenamientos",
    "créame un widget para mis gastos",
])
def test_code_plus_a_widget_request_selects_the_generator_backend(ask, monkeypatch):
    monkeypatch.delenv("WORKER_BACKEND", raising=False)
    assert code_helpers.is_widget_request(ask) is True
    assert code_helpers.widget_action(ask)[0] == "create"
    assert type(registry.get_backend(_spec(ask))).__name__ == "GeneratorBackend"


def test_a_code_task_that_is_NOT_a_widget_does_not(monkeypatch):
    """The carve-out matters as much as the rule: an architect request is `code` too and must keep the generic
    backend, or asking for a project would silently try to build a widget."""
    monkeypatch.delenv("WORKER_BACKEND", raising=False)
    ask = "dile al architect que arranque el proyecto nuevo del daemon"
    if code_helpers.is_architect_request(ask):
        assert type(registry.get_backend(_spec(ask))).__name__ != "GeneratorBackend"


def test_the_request_reaches_the_backend_through_the_env_dispatch_sets():
    """`dispatch` puts the RAW request in `ZAELAR_TASK_REQUEST`, and both the registry and the backend read it
    from there. If that key ever drifts, the registry silently falls back to the generic worker."""
    spec = _spec(ASK)
    assert (spec.env or {}).get("ZAELAR_TASK_REQUEST") == ASK
    assert registry._is_widget_task(spec) is True
    assert registry._is_widget_task(_spec(ASK, kind="generic")) is False


# ── link 3: driving it opens the card AND reports the id ────────────────────────────────────────────────────
def _drive(monkeypatch, *, req, gen_result):
    from nucleo.workers.generator_session import GeneratorBackend
    from widgets import generator as _gen

    seen: list[tuple] = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda cat, label, **kw: seen.append((cat, label, kw.get("extra") or {})))
    monkeypatch.setattr(_gen, "generate_widget", lambda *a, **k: gen_result, raising=False)
    backend = GeneratorBackend()
    backend._task_id = "T-chain"
    asyncio.run(backend._drive(req))
    events = []
    while not backend._q.empty():
        events.append(backend._q.get_nowait())
    return seen, events


def test_a_created_widget_is_opened_and_its_id_is_reported(monkeypatch):
    seen, events = _drive(monkeypatch, req=ASK, gen_result={"ok": True, "id": "entrenamientos"})
    shows = [e for e in seen if e[0] == "widget" and e[1] == "show"]
    assert shows and shows[0][2].get("id") == "entrenamientos"
    results = [e.data for e in events if e.type == "result"]
    assert results and (results[0].get("data") or {}).get("widget") == "entrenamientos"
    assert results[0].get("ok") is True


def test_a_failed_generation_neither_opens_anything_nor_claims_success(monkeypatch):
    """The other half of the case: «ya lo tienes» without a mechanism behind it is the failure it hunts for."""
    seen, events = _drive(monkeypatch, req=ASK, gen_result={"ok": False, "error": "validation failed"})
    assert not [e for e in seen if e[0] == "widget" and e[1] == "show"]
    results = [e.data for e in events if e.type == "result"]
    assert results and results[0].get("ok") is False
    assert "No pude" in (results[0].get("summary") or "")


def test_the_failure_reason_is_recorded_not_swallowed(monkeypatch):
    """A generation that fails without a diagnosable reason is what made the 2026-07-16 session unfixable."""
    seen, _ = _drive(monkeypatch, req=ASK, gen_result={"ok": False, "error": "widget.js references a missing class"})
    fails = [e for e in seen if e[0] == "task" and e[1] == "generator_fail"]
    assert fails
