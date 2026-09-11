"""V2-644 — a REPORT is delivered as a DOCUMENT, not as a results list.

Measured (the Juncal research, 2026-09-09, session adc8a7c7): «investígame esta empresa … un informe» was
commissioned on the results-sheet surface. The consequences, all on the operator's screen: the browser's
page-extract pushed einforma's own trust badges («Cero CO2», «Confianza Online») into Resultados as findings,
the criteria seeding filled a tab of a comparison sheet nobody would compare on, and the report itself had
nowhere to land. The fix is a SIXTH surface value, `informe`: commissioned like the sheet surfaces (opened
at commission time, closed at finish), but the box it opens is the `documento` widget, bound to the errand.
"""
from __future__ import annotations

import pathlib
import re
import types

import pytest

from nucleo import sheets, surfaces

_ENGINE = pathlib.Path(__file__).resolve().parents[3]
_DISPATCH_SRC = (_ENGINE / "nucleo" / "dispatch.py").read_text(encoding="utf-8")


def _rec(**over):
    base = dict(task_id="t9", title="Informe: Juncadella Salvador SL", goal="informe de la empresa",
                surface="informe", status="running", phases=[{"t": 1.0, "s": "abriendo einforma"},
                                                             {"t": 2.0, "s": "NIF confirmado"}],
                nav_task="", sheet="")
    base.update(over)
    return types.SimpleNamespace(**base)


# ── the vocabulary ──────────────────────────────────────────────────────────────────────────────────────────
def test_the_sixth_surface_exists_and_is_not_a_sheet():
    assert surfaces.DOC == "informe"
    assert surfaces.DOC in surfaces.SURFACES
    assert surfaces.opens_doc(surfaces.DOC)
    assert not surfaces.opens_sheet(surfaces.DOC), (
        "informe must NOT ride the results-sheet path: open/retitle/close/browser-delivery all branch on it")


@pytest.mark.parametrize("word", ["informe", "documento", "report", "dossier", "doc"])
def test_the_words_a_model_writes_normalize_to_it(word):
    assert surfaces.normalize(word) == surfaces.DOC


def test_the_escalation_tool_offers_it():
    from nucleo.flash import router_catalog
    esc = next(t["function"] for t in router_catalog.TOOLS
               if t["function"]["name"] == "escalate_to_slowbrain")
    prop = esc["parameters"]["properties"]["surface"]
    assert "informe" in prop["enum"]
    assert "informe=" in prop["description"], "the gloss is what tells the model WHEN informe beats item"


# ── the live narrative, keyed by TASK (the doc sheet has no sheet id) ───────────────────────────────────────
def test_task_progress_tells_the_live_errands_story_and_only_its_own():
    live = _rec(task_id="t1")
    other = _rec(task_id="t2", phases=[{"t": 1.0, "s": "otra cosa"}])
    out = sheets.task_progress("t1", [other, live], ("running",))
    assert out["alive"] is True
    assert out["phases"] == ["abriendo einforma", "NIF confirmado"]


def test_a_dead_or_unknown_task_is_not_alive():
    dead = _rec(task_id="t1", status="done")
    assert sheets.task_progress("t1", [dead], ("running",)) == {"alive": False, "phases": []}
    assert sheets.task_progress("", [dead], ("running",)) == {"alive": False, "phases": []}


# ── the results sheet must NOT be auto-opened under a report errand ────────────────────────────────────────
def test_browser_findings_do_not_open_a_results_sheet_for_a_report(monkeypatch):
    """The badge-junk path: `sheet_for_delivery` auto-opens a sheet for any live errand whose browser
    extracted rows (V2-290). For a report errand that is exactly the box that must not appear."""
    opened = []
    monkeypatch.setattr(sheets, "_sheet_open", lambda r: opened.append(r))
    rec = _rec(task_id="t7")
    assert sheets.sheet_for_delivery("t7", [rec], ("running",)) == ""
    assert opened == [], "a report errand got a results sheet opened under it"
    # Sensitivity: the same call on a LIST errand still opens — the guard is the surface, not the function.
    lst = _rec(task_id="t8", surface="lista")
    sheets.sheet_for_delivery("t8", [lst], ("running",))
    assert opened == [lst]


# ── the documento binding (nucleo/docsheet.py) ─────────────────────────────────────────────────────────────
@pytest.fixture()
def doc_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    import importlib
    from nucleo import workspace
    from widgets import store as wstore
    importlib.reload(workspace)
    importlib.reload(wstore)
    from widgets.documento import data as mod
    importlib.reload(mod)
    yield mod
    importlib.reload(workspace)
    importlib.reload(wstore)


def test_commissioning_binds_the_sheet_and_puts_it_on_screen(doc_data, monkeypatch):
    from nucleo import docsheet
    from voice import observer
    shown = []
    monkeypatch.setattr(observer, "emit", lambda *a, **k: shown.append((a, k)))
    docsheet.doc_open(_rec())
    db = doc_data.view_data()
    assert db["empty"] is True, "the report sheet starts BLANK — the old document must not pose as the answer"
    proc = db["process"]
    assert proc is not None and proc["title"] == "Informe: Juncadella Salvador SL"
    assert any((k.get("extra") or {}).get("id") == "documento" for _, k in shown), \
        "the sheet must be SHOWN at commission time — opening late is the blank-screen problem again"


def test_the_composed_name_reaches_the_process_header_but_only_for_its_errand(doc_data):
    from nucleo import docsheet
    docsheet.doc_open(_rec(task_id="t9", title="provisional"))
    docsheet.doc_retitle(_rec(task_id="t9", title="Informe: Juncadella Salvador SL"))
    assert doc_data.view_data()["process"]["title"] == "Informe: Juncadella Salvador SL"
    docsheet.doc_retitle(_rec(task_id="OTHER", title="ajena"))
    assert doc_data.view_data()["process"]["title"] == "Informe: Juncadella Salvador SL"


def test_finishing_persists_the_narrative_and_releases_the_binding(doc_data):
    from nucleo import docsheet
    rec = _rec(task_id="t9")
    docsheet.doc_open(rec)
    docsheet.doc_close(rec)
    db = doc_data._load()
    assert db["task"] == ""
    assert db["process"] == ["abriendo einforma", "NIF confirmado"], (
        "the live record dies with the errand: without persisting, the Proceso tab goes blank at the exact "
        "moment the report arrives")


def test_the_view_derives_the_live_narrative_from_the_dispatcher(doc_data, monkeypatch):
    import sys

    import nucleo
    doc_data.begin_task("Informe X", task_id="t9")
    fake = types.SimpleNamespace(task_progress=lambda tid: {"alive": True, "phases": [f"fase de {tid}"]})
    # `from nucleo import dispatch` resolves through BOTH the package attribute and sys.modules.
    monkeypatch.setitem(sys.modules, "nucleo.dispatch", fake)
    monkeypatch.setattr(nucleo, "dispatch", fake, raising=False)
    proc = doc_data.view_data()["process"]
    assert proc == {"alive": True, "phases": ["fase de t9"], "title": "Informe X"}
    # And the brain sees the same fact instead of «the sheet is empty» (which would contradict the screen).
    digest = doc_data.prompt_digest()
    assert "PROCESO" in digest and "fase de t9" in digest


def test_without_a_dispatcher_the_sheet_fails_soft(doc_data):
    doc_data.begin_task("Informe X", task_id="t-dead")
    proc = doc_data.view_data()["process"]
    assert proc["alive"] is False and proc["phases"] == []


# ── the worker's delivery contract flips ────────────────────────────────────────────────────────────────────
def test_the_report_block_sends_the_worker_to_documento_and_away_from_results():
    from nucleo.dispatch_prompts import DOC_SURFACE_BLOCK as b
    assert "documento" in b and "append" in b
    assert re.search(r"NO entregues en `results`", b), "without the prohibition, step 4b still wins"
    assert "Elaborando el informe" in b, "the operator asked for this exact phase before the writing starts"


def test_dispatch_wires_every_doc_branch_the_sheet_already_has():
    """Source-level: the four gestures the results sheet gets (open, retitle, close, criteria-guard) must
    each have their doc sibling — a missing one fails SILENTLY in production (nothing opens, nothing closes)."""
    assert "docsheet.doc_open(rec)" in _DISPATCH_SRC
    assert "docsheet.doc_retitle(rec)" in _DISPATCH_SRC
    assert "docsheet.doc_close(rec)" in _DISPATCH_SRC
    assert _DISPATCH_SRC.count('opens_doc(getattr(rec, "surface", ""))') >= 5, (
        "commission, retitle, close, two criteria guards and the prompt block all branch on opens_doc")
    # V2-661: the prompt BLOCKS a trusted worker gets (this one + the library block) compose in one place,
    # `dispatch_prompts.trusted_blocks`; dispatch calls it. The guard follows the CHANNEL (V2-555).
    assert "trusted_blocks(getattr(rec, \"surface\", \"\"))" in _DISPATCH_SRC
    _PROMPTS_SRC = (pathlib.Path(__file__).resolve().parents[3] / "nucleo" / "dispatch_prompts.py").read_text(
        encoding="utf-8")
    assert "DOC_SURFACE_BLOCK" in _PROMPTS_SRC and "opens_doc(surface" in _PROMPTS_SRC
