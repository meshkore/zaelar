"""V2-705 · A DESTRUCTIVE action with no selector is REFUSED at the single funnel — never widened to «all».

Measured 2026-09-15 18:03:25 (session 878b0122): «remove the appointment tomorrow at seven — it was just a
test» → `agenda.cancel_meeting` with `payload: {}` → every local appointment gone and **147 DELETE requests
against the operator's real Google Calendar in sixty seconds, 100 accepted**. Every `cancel_meeting` the
model had ever issued arrived empty (3 of 3 in fourteen days); the manifest declares `title: string`; no
layer between the model and the handler read it.

The contract lives in `widgets/contract.py` and is enforced in `server_api._dispatch`, which is the ONE door
the brain, the worker, a card button and cron all go through. These cases pin: what is refused, what is
NOT (creations, views, whole-wipes behind their confirm gate, optional selectors), that the refusal reaches
the caller through the funnel with the widget untouched, and that the sentence the operator hears comes from
the language table.
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from widgets import contract

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """ISOLATED store — the test must never touch the operator's real agenda."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    db = ag.load_db()
    db["meetings"] = [
        {"id": "m1", "title": "Dentist", "date": "2099-09-16", "startTime": "17:00"},
        {"id": "m2", "title": "Kryptonite test", "date": "2099-09-16", "startTime": "07:00"},
        {"id": "m3", "title": "Renovar el seguro", "date": "2099-10-01", "startTime": "10:00"},
    ]
    store.save(ag.WIDGET_ID, db)
    return ag


# ── the classification: what counts as destructive, and which key is the selector ──────────────────────

@pytest.mark.parametrize("wid,action,field", [
    ("agenda", "cancel_meeting", "title"),
    ("agenda", "drop", "taskId"),
    ("agenda", "drop_project", "projectId"),
    ("contactos", "remove_contact", "contactId"),
    ("mensajeria", "trash", "n"),
    ("youtube", "remove", "item"),
    ("archivos", "delete_file", "fileId"),
])
def test_a_destructive_action_declares_which_key_names_its_target(wid, action, field):
    spec = json.loads((ENGINE / "widgets" / wid / "manifest.json").read_text())["actions"][action]
    assert contract.is_destructive(spec, action)
    assert contract.selector_for(wid, action, spec) == field


@pytest.mark.parametrize("wid,action", [
    ("agenda", "add_meeting"),        # a creation: a missing hour is the handler's business
    ("agenda", "show_day"),           # a view
    ("agenda", "not_now"),            # its description says «no la quita» — prose is not the contract
    ("youtube", "filter_list"),       # «q vacío quita el filtro»: same trap
    ("mensajeria", "read"),           # «quita el no-leído»: same trap
])
def test_the_name_is_the_contract_never_the_descriptions_prose(wid, action):
    spec = json.loads((ENGINE / "widgets" / wid / "manifest.json").read_text())["actions"][action]
    assert not contract.is_destructive(spec, action) or contract.selector_for(wid, action, spec) == ""
    assert contract.guard(wid, action, {}) is None


def test_a_whole_wipe_with_no_selector_is_left_to_its_confirm_gate():
    """`clear_all` declares no payload: «all of them» is what it MEANS, and the confirm gate is its friction."""
    assert contract.guard("agenda", "clear_all", {}) is None


def test_an_optional_selector_is_not_demanded():
    """`contactos.disconnect` takes an optional `provider`; refusing it empty would break «disconnect»."""
    assert contract.guard("contactos", "disconnect", {}) is None


# ── the refusal ────────────────────────────────────────────────────────────────────────────────────────

def test_the_measured_call_is_refused(agenda):
    r = contract.guard("agenda", "cancel_meeting", {})
    assert r and r["ok"] is False and r["error"] == contract.SELECTOR_MISSING and r["field"] == "title"


def test_an_empty_string_is_as_empty_as_a_missing_key(agenda):
    assert contract.guard("agenda", "cancel_meeting", {"title": "   "})["error"] == contract.SELECTOR_MISSING
    assert contract.guard("agenda", "drop", {"taskId": ""})["error"] == contract.SELECTOR_MISSING


def test_a_named_target_goes_through(agenda):
    assert contract.guard("agenda", "cancel_meeting", {"title": "Dentist"}) is None


def test_the_refusal_lists_what_the_widget_itself_can_name(agenda):
    r = contract.guard("agenda", "cancel_meeting", {})
    assert any("Dentist" in o for o in r["options"]), r["options"]
    assert "Dentist" in r["message"], "the spoken sentence carries the menu, so the next turn can pick"


def test_the_sentence_he_hears_comes_from_the_language_table(agenda, monkeypatch):
    """V2-676/V2-689: a refusal is a text the operator HEARS, so it lives in the table that gets translated."""
    from i18n import langs
    en = contract.guard("agenda", "cancel_meeting", {})["message"]
    monkeypatch.setattr(langs, "spec", lambda code=None: langs.LangSpec())      # the Castilian defaults
    es = contract.guard("agenda", "cancel_meeting", {})["message"]
    assert en != es and "Dentist" in en and "Dentist" in es
    assert "which one" in en.lower() or "which of these" in en.lower()


def test_the_guard_never_raises(monkeypatch):
    from widgets import runtime
    monkeypatch.setattr(runtime, "get", lambda wid: (_ for _ in ()).throw(RuntimeError("boom")))
    assert contract.guard("agenda", "cancel_meeting", {}) is None


# ── through the funnel: the widget is NOT touched, and every caller is covered ─────────────────────────

def test_through_the_funnel_the_calendar_is_untouched_and_google_is_never_called(agenda, monkeypatch):
    from widgets.agenda import gcal
    calls = []
    monkeypatch.setattr(gcal, "delete_google", lambda m: calls.append(m) or True)
    from widgets import server_api
    res = asyncio.run(server_api.brain_action("agenda", "cancel_meeting", {}))
    assert res.get("ok") is False and res.get("error") == contract.SELECTOR_MISSING
    assert len(agenda.load_db()["meetings"]) == 3, "the empty selector deleted nothing"
    assert calls == [], "and Google was never asked to delete anything"


def test_the_refusal_is_observable(agenda, monkeypatch):
    seen = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda cat, kind, **kw: seen.append((cat, kind, kw)))
    from widgets import server_api
    asyncio.run(server_api.brain_action("agenda", "cancel_meeting", {}))
    labels = [k for _, k, _ in seen]
    assert "action_refused" in labels, labels


def test_the_contract_sits_before_the_production_gate_in_the_funnel():
    """Structural: the FIRST thing `_dispatch` does is the contract — for every caller, before any policy."""
    src = (ENGINE / "widgets" / "server_api.py").read_text(encoding="utf-8")
    body = src[src.index("async def _dispatch("):src.index("async def widget_action(")]
    assert body.index("contract.guard(") < body.index("producers.gate("), (
        "the contract must run before the production gate: a refused action never reaches a policy that "
        "could let it through")
