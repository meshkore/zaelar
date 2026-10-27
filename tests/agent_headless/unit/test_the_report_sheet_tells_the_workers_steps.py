"""A report errand's process view moves as the worker works, and shows the steps it declared (V2-820).

Measured on a live session: a document errand ran for two minutes; the worker declared a five-step plan
(«Leer el widget de mensajería · Extraer los enviados · Filtrar los largos · …»), narrated three times and reported a
phase and a progress — and the document sheet said «Preparando… · Aún no hay pasos que contar» the whole time. He
asked to see the steps («leyendo tus mensajes», «analizando cómo escribes», «creando el documento»).

The cause was not the worker: every line reached the record. Only the RESULTS sheet was told a line had arrived
(`record_phase` notified `opens_sheet` surfaces); the document sheet (`opens_doc`) was painted once at commission and
never again — zero `widget data documento` events in those two minutes. Now one door (`sheets.notify_process`) tells
whichever card shows the errand's process, on a phase, a declared plan and a step done; and the process view carries
the plan the worker declared with how much of it is done — its words, never steps we invent.
"""
from __future__ import annotations

import importlib
import types

import pytest

from nucleo import sheets

#: The plan as a worker declares it, in the operator's language.
PLANS = {
    "es": ["Leer tus mensajes enviados", "Analizar cómo escribes", "Crear el documento", "Presentártelo"],
    "en": ["Read your sent emails", "Analyse how you write", "Write the document", "Present it to you"],
}


def _rec(surface="informe", **over):
    base = dict(task_id="t9", title="Informe", goal="tu estilo", surface=surface, status="running", phases=[],
                plan=[], done=0, nav_task="", sheet="s-1", trace_id="", last_event_at=0.0, last_step_at=0.0,
                phase="", note="", pct=-1, reported_at=0.0)
    base.update(over)
    return types.SimpleNamespace(**base)


@pytest.fixture
def emitted(monkeypatch):
    from voice import observer
    out: list = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: out.append((kind, label, k.get("extra") or {})))
    return out


def _cards(emitted) -> list:
    return [x.get("id") for kind, label, x in emitted if kind == "widget" and label == "data"]


def test_a_new_line_on_a_report_errand_tells_the_document_card(emitted):
    assert sheets.record_phase(_rec(), "Leyendo tus mensajes enviados", 150)
    assert _cards(emitted) == ["documento"], "the document sheet must hear that its process moved"


def test_the_results_sheet_is_still_told_and_a_silent_errand_tells_nobody(emitted):
    sheets.record_phase(_rec(surface="lista"), "Recorriendo la página", 150)
    assert len(_cards(emitted)) == 1 and _cards(emitted)[0] != "documento"
    emitted.clear()
    sheets.record_phase(_rec(surface="silenciosa"), "x", 150)
    assert _cards(emitted) == []


@pytest.mark.parametrize("lang", sorted(PLANS))
def test_a_declared_plan_and_a_step_done_move_the_card(lang, emitted, monkeypatch):
    from nucleo import dispatch
    from nucleo.workers import reports
    rec = _rec()
    monkeypatch.setattr(dispatch, "_SESSIONS", {"t9": rec})
    reports.session_plan("t9", "|".join(PLANS[lang]))
    assert "documento" in _cards(emitted), "the plan reaches the card the moment it is declared"
    emitted.clear()
    reports.session_progress("t9", PLANS[lang][0], done=1)
    assert "documento" in _cards(emitted), "a step done moves the card"


@pytest.mark.parametrize("lang", sorted(PLANS))
def test_the_process_carries_the_workers_plan_and_how_far_it_is(lang):
    rec = _rec(plan=list(PLANS[lang]), done=2, phases=[{"t": 1.0, "s": PLANS[lang][0]}])
    out = sheets.task_progress("t9", [rec], ("running",))
    assert out == {"alive": True, "phases": [PLANS[lang][0]], "plan": PLANS[lang], "done": 2}
    assert sheets.task_progress("t9", [_rec(plan=list(PLANS[lang]), done=99)], ("running",))["done"] == 4


@pytest.fixture()
def doc_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from nucleo import workspace
    from widgets import store as wstore
    importlib.reload(workspace)
    importlib.reload(wstore)
    from widgets.documento import data as mod
    importlib.reload(mod)
    yield mod
    importlib.reload(workspace)
    importlib.reload(wstore)


@pytest.mark.parametrize("lang", sorted(PLANS))
def test_the_document_sheet_view_hands_the_plan_to_the_card(lang, doc_data, monkeypatch):
    import sys

    import nucleo
    doc_data.begin_task("Tu estilo", task_id="t9")
    fake = types.SimpleNamespace(task_progress=lambda tid: {"alive": True, "phases": [], "plan": PLANS[lang],
                                                            "done": 1})
    monkeypatch.setitem(sys.modules, "nucleo.dispatch", fake)
    monkeypatch.setattr(nucleo, "dispatch", fake, raising=False)
    proc = doc_data.view_data()["process"]
    assert proc["alive"] is True and proc["plan"] == PLANS[lang] and proc["done"] == 1
