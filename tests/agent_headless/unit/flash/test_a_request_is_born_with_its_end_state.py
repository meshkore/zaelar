"""V2-776 L1 · A request is born with its END STATE, and the engine can read it (node 2.183).

Demo pass 60 (2026-09-29), B1→B2: «find me the wallpaper cosmic eye in the sky» went to a worker whose brief
said «find the artwork»; the end state — the desktop wallpaper has changed — was written nowhere, and «set the
first one as my background» was completed by the screen verdict as `results:choose` on the monitors sheet.

What is pinned here: a widget action's postcondition renders from its manifest over the payload, with the
baseline of a `changed` clause taken at birth; the three new clause kinds read the product's truth and never
guess; the data-op door opens the spec BEFORE the op and attests it after; and a verdict completion may only
fire an action that attests the end state the brief read in the phrase.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo import spec, truth, verify


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    spec.reset()
    yield
    spec.reset()


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    result = {k: {"choice": c, "confidence": float(p), "probs": {c: float(p)}} for k, (c, p) in verdicts.items()}
    return {"event": ev, "result": result, "_call_id": "t", "turn_id": "t", "open_ids": ["results"]}


# ── templates ──────────────────────────────────────────────────────────────────────────────────────────────

def test_the_wallpaper_action_declares_a_changed_desktop_and_takes_its_baseline(monkeypatch):
    monkeypatch.setattr(truth, "desktop_wallpaper", lambda: {"url": "https://x/old.jpg", "title": "Old"})
    dw = spec.render("imagenes", "wallpaper", {"item": "1"})
    assert dw == {"desktop": "wallpaper", "expect": "changed", "baseline": {"url": "https://x/old.jpg", "title": "Old"}}
    assert spec.target_of(dw) == "desktop:wallpaper"


def test_a_required_placeholder_with_no_value_renders_nothing_and_an_optional_one_is_dropped():
    assert spec.render("results", "layout", {}) is None, "a `{layout}` nobody gave is not a spec — never a guess"
    dw = spec.render("agenda", "add_meeting", {"title": "Catch up with Ethan", "startTime": "16:00"})
    assert dw == {"widget": "agenda", "collection": "meetings", "where": {"title~": "Catch up with Ethan"}}


def test_an_action_without_a_template_has_no_spec():
    assert spec.template_of("results", "choose") is None
    assert spec.render("results", "choose", {"title": "x"}) is None


# ── the readers ────────────────────────────────────────────────────────────────────────────────────────────

def test_a_docked_card_is_not_visible(monkeypatch):
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda: {"open_widgets": ["results", "agenda"], "minimized_widgets": ["results"]})
    assert truth.canvas_state("results") == "minimized"
    assert verify.check({"canvas": "results", "expect": "visible"}) is False
    assert verify.check({"canvas": "agenda", "expect": "visible"}) is True
    assert verify.check({"canvas": "map", "expect": "closed"}) is True


def test_a_changed_clause_reads_against_its_baseline(monkeypatch):
    monkeypatch.setattr(truth, "desktop_wallpaper", lambda: {"url": "https://x/helix.jpg", "title": "Helix"})
    assert verify.check({"desktop": "wallpaper", "expect": "changed", "baseline": {}}) is True
    assert verify.check({"desktop": "wallpaper", "expect": "changed", "baseline": {"url": "https://x/helix.jpg", "title": "Helix"}}) is False
    assert verify.check({"desktop": "wallpaper", "expect": "changed"}) is None, "nothing to compare against is unreadable, not false"
    assert verify.check({"desktop": "wallpaper", "has": "helix"}) is True
    assert "sigue como estaba" in " ".join(verify.missing(
        {"desktop": "wallpaper", "expect": "changed", "baseline": {"url": "https://x/helix.jpg", "title": "Helix"}}))


def test_a_field_clause_reads_a_scalar_of_the_view_and_an_error_value_is_unreadable(monkeypatch):
    monkeypatch.setattr(truth, "widget_view", lambda wid: {"layout": "compare", "view": "list", "error": ""})
    assert verify.check({"widget": "results", "field": "layout", "is": "compare"}) is True
    assert verify.check({"widget": "results", "field": "view", "is": "detail"}) is False
    assert verify.check({"widget": "results", "field": "nope", "is": "x"}) is None
    monkeypatch.setattr(truth, "widget_view", lambda wid: {"layout": "compare", "error": "store unreadable"})
    assert verify.check({"widget": "results", "field": "layout", "is": "compare"}) is None


# ── the door ───────────────────────────────────────────────────────────────────────────────────────────────

def test_the_data_op_door_opens_the_spec_before_the_op_and_attests_it_after(monkeypatch):
    import widgets
    from nucleo.flash import data_ops
    walls = iter([{}, {"url": "https://x/helix.jpg", "title": "Helix"}])
    monkeypatch.setattr(truth, "desktop_wallpaper", lambda: next(walls, {"url": "https://x/helix.jpg", "title": "Helix"}))

    async def _noop(*_a, **_k):
        return False
    monkeypatch.setattr(data_ops, "report_failure", _noop)

    async def _fake(_tag, _payload):
        return {"ok": True, "wallpaper": "https://x/helix.jpg"}
    monkeypatch.setattr(widgets, "dispatch_tag", _fake)
    asyncio.run(data_ops.dispatch_and_report("imagenes", "wallpaper", {"item": "1"}, text="set the first one as my background"))
    met = [e for e in spec.settled() if e.get("status") == "met"]
    assert met and met[0]["target"] == "desktop:wallpaper" and met[0]["done_when"]["baseline"] == {}, spec._OPEN
    assert spec.open_specs() == [], "a met spec is no longer owed"


# ── the gate ───────────────────────────────────────────────────────────────────────────────────────────────

def test_a_completion_that_attests_a_different_end_state_is_refused():
    brief = _brief(end_state=("desktop:wallpaper", 0.92), screen_action=("results:choose", 0.98))
    why = spec.gate_completion(brief, "results", "choose")
    assert "desktop:wallpaper" in why and "attests nothing" in why
    assert spec.gate_completion(brief, "imagenes", "wallpaper") == ""


def test_without_an_end_state_verdict_the_completion_is_untouched():
    assert spec.gate_completion(_brief(screen_action=("results:choose", 0.98)), "results", "choose") == ""
    assert spec.gate_completion(_brief(end_state=("none", 0.9)), "results", "choose") == ""
    assert spec.gate_completion(_brief(end_state=("desktop:wallpaper", 0.3)), "results", "choose") == "", "an unsure verdict is no verdict"


def test_the_brief_enumerates_the_end_states_of_the_screen_and_of_the_specs_still_owed(monkeypatch):
    assert spec.end_state_question([]) is None
    q = spec.end_state_question(["results"])
    assert set(q["criteria"]) == {"results:view", "results:layout", "none"}
    spec.open({"desktop": "wallpaper", "expect": "changed", "baseline": {}}, text="find me the wallpaper cosmic eye", source="voice")
    q = spec.end_state_question(["results"])
    assert "desktop:wallpaper" in q["criteria"], "a closed card whose end state is still owed is an option (B2)"
