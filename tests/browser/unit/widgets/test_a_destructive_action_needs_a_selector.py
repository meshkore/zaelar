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
    assert contract.guard("agenda", "cancel_meeting", {}) is not None    # it answers instead of raising


# ── V2-710 T0.3 · and when the guard ITSELF fails, it fails CLOSED ──────────────────────────────────────
# The body used to sit under `except Exception: return None` and `server_api` wrapped the call in a second
# `try/except: pass`. Either one turned a broken contract into «proceed», so a destructive action ran with
# an empty selector — the pre-V2-705 state that sent 147 DELETE requests to the real calendar — in silence.

def test_a_destructive_action_is_REFUSED_when_the_contract_cannot_be_read(monkeypatch):
    from widgets import runtime
    monkeypatch.setattr(runtime, "get", lambda wid: (_ for _ in ()).throw(RuntimeError("boom")))
    refused = contract.guard("agenda", "cancel_meeting", {"title": "Dentist"})
    assert refused and refused["error"] == contract.GUARD_ERROR, refused
    assert refused["message"], "and the operator hears a sentence, not a code"


def test_a_harmless_action_still_goes_through_when_the_contract_cannot_be_read(monkeypatch):
    """Refusing every read because the contract had a bad day is a different kind of broken, and there is
    nothing to protect on a `show_view`."""
    from widgets import runtime
    monkeypatch.setattr(runtime, "get", lambda wid: (_ for _ in ()).throw(RuntimeError("boom")))
    assert contract.guard("agenda", "add_meeting", {"title": "x"}) is None


def test_the_funnel_cannot_swallow_the_refusal(agenda, monkeypatch):
    """The guard's decision reaches the caller: no frame between it and the answer may drop it."""
    from widgets import runtime, server_api
    monkeypatch.setattr(runtime, "get", lambda wid: (_ for _ in ()).throw(RuntimeError("boom")))
    res = asyncio.run(server_api.brain_action("agenda", "cancel_meeting", {"title": "Dentist"}))
    assert res.get("ok") is False and res.get("error") == contract.GUARD_ERROR, res
    assert len(agenda.load_db()["meetings"]) == 3, "and nothing was removed while the contract was blind"


def test_the_sentence_for_a_blind_guard_comes_from_the_language_table(monkeypatch):
    from i18n import langs
    from widgets import runtime
    monkeypatch.setattr(runtime, "get", lambda wid: (_ for _ in ()).throw(RuntimeError("boom")))
    en = contract.guard("agenda", "cancel_meeting", {"title": "x"})["message"]
    monkeypatch.setattr(langs, "spec", lambda code=None: langs.LangSpec())      # the Castilian defaults
    es = contract.guard("agenda", "cancel_meeting", {"title": "x"})["message"]
    assert en != es and en and es


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


# ── V2-707 F0 · the menu the refusal offers is ordered by WHAT COMES NEXT ──────────────────────────────
# Measured 2026-09-16 (session cb0ac5da, i=7911): asked to remove a meeting today at five, the operator was
# read back «¡Feliz cumpleaños! (cita 2027-08-19); Cristina Sergio Primo Raquel - Cumplea…» — birthdays
# eleven months out, while the two meetings he could have meant sat further down. `_options` takes the
# first eight rows of `ref_index`, and that index handed them back in Google-sync order. The model then
# re-emitted the same empty selector, because nothing in the menu was usable. `prompt_digest` has always
# sorted by (date, hour); the index that feeds the REFUSAL never did, so the brain's two views of the same
# card disagreed about what comes next.

def test_the_menu_starts_with_the_soonest_appointment(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    db = ag.load_db()
    # The incident's own calendar: the two meetings he could have meant were TODAY and TOMORROW, the
    # birthdays eleven months out. Stored in the order the store had them — the far birthday FIRST.
    import datetime as _dt
    today = _dt.date.today()
    db["meetings"] = [
        {"id": "b1", "title": "¡Feliz cumpleaños!", "date": str(today.replace(year=today.year + 1)),
         "startTime": ""},
        {"id": "b2", "title": "Cumpleaños de Cristina",
         "date": str(today.replace(year=today.year + 1) - _dt.timedelta(days=48)), "startTime": ""},
        {"id": "m1", "title": "Meeting with Cryptonite",
         "date": str(today + _dt.timedelta(days=1)), "startTime": "17:00"},
        {"id": "m0", "title": "Dentist", "date": str(today), "startTime": "17:00"},
    ]
    store.save(ag.WIDGET_ID, db)

    menu = contract.guard("agenda", "cancel_meeting", {})["options"]
    assert menu, "the refusal has to offer something"
    assert "Dentist" in menu[0], f"the soonest appointment must lead the menu, got {menu}"
    assert menu.index([o for o in menu if "Cryptonite" in o][0]) < \
        menu.index([o for o in menu if "cumpleaños" in o.lower()][0]), \
        f"a meeting next week cannot rank below a birthday next year: {menu}"


def test_the_index_and_the_digest_agree_on_what_comes_next(tmp_path, monkeypatch):
    """The two surfaces the brain reads about the SAME card. They disagreed, and the disagreement is what
    the model had to resolve on its own — with the wrong half in front of it."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    db = ag.load_db()
    year = int(ag._today()[:4]) + 9
    db["meetings"] = [
        {"id": "z", "title": "Zeta", "date": f"{year}-03-03", "startTime": "09:00"},
        {"id": "a", "title": "Alfa", "date": f"{year}-01-01", "startTime": "08:00"},
        {"id": "b", "title": "Beta", "date": f"{year}-01-01", "startTime": "20:00"},
    ]
    store.save(ag.WIDGET_ID, db)

    from_index = [r["label"] for r in ag.ref_index() if r["field"] == "title"]
    from_digest = [ln.split("«")[1].split("»")[0] for ln in ag.prompt_digest().splitlines() if "«" in ln]
    assert from_index == from_digest == ["Alfa", "Beta", "Zeta"], (from_index, from_digest)


# ── V2-711 T2.5 · the census of destructive actions that run with NO friction ────────────────────────────
# Walking the whole catalog: 24 actions are destructive by `contract`, and six of them were FAST. That list
# was an accident of which manifest happened to carry `confirm: true`, not a decision — so it is written
# down as one here, with the reason for each survivor beside it.

_DESTRUCTIVE_AND_FAST = {
    # DELIBERATE, and re-confirmed in V2-711: one row with a selector and a snapshot runs; N>1 asks by
    # RADIUS (V2-707 F1). Making it CONFIRM reopens the five-minute case that motivated F0 — «borra la
    # cita» parked a whole worker before it ran a single step.
    ("agenda", "cancel_meeting"),
    ("agenda", "drop"),                    # a task the operator drops; the store snapshots what it wrote
    # V2-744 — ONE item out of one of his own lists («borra el ítem 2 de la compra»), and the whole point
    # of a checklist is that crossing things off it is cheap. It declares `ref: "task"`, so `contract.guard`
    # still refuses it with an empty selector: an empty one never means «all of them». Emptying the LIST is
    # the action that asks (`clear_list`), and so is deleting the list itself.
    ("agenda", "delete_task"),
    ("musica", "remove_from_playlist"),    # one track off a list he owns, re-addable by name
    ("youtube", "remove"),                 # one row out of a queue
    ("youtube", "unfollow_channel"),       # re-followable in one gesture; asking would be noise
}


def test_the_destructive_actions_without_friction_are_a_DECISION_not_an_accident():
    from widgets import actions as _acts, runtime as _rt
    live = set()
    for w in _rt.catalog():
        for name, spec in (w.get("actions") or {}).items():
            if contract.is_destructive(spec, name) and _acts.classify(spec, name) != _acts.CONFIRM:
                live.add((w["id"], name))
    assert live == _DESTRUCTIVE_AND_FAST, (
        "the set of destructive actions that run with no friction changed. Each one in this list has its "
        "reason written beside it; add yours, or give the action `confirm: true` in its manifest:\n"
        f"  new: {sorted(live - _DESTRUCTIVE_AND_FAST)}\n  gone: {sorted(_DESTRUCTIVE_AND_FAST - live)}")


def test_disconnecting_an_account_ASKS_because_the_contract_cannot_see_it():
    """`musica:disconnect` was destructive, FAST **and declared no selector**, so `contract.guard` never
    looked at it: it unlinked the operator's Spotify account with no question anywhere in the path and no
    way for the V2-705 refusal to reach it. Unlike the five above, it is not one row of his own data — it
    is the account itself, and re-linking it means going back through an OAuth consent."""
    from widgets import actions as _acts, runtime as _rt
    spec = (_rt.get("musica") or {}).get("actions", {}).get("disconnect") or {}
    assert contract.is_destructive(spec, "disconnect") is True
    assert _acts.classify(spec, "disconnect") == _acts.CONFIRM
    assert contract.selector_for("musica", "disconnect", spec) == "", (
        "it declares no selector BY NATURE — there is nothing to name — which is exactly why the friction "
        "has to come from its confirm flag and cannot come from the contract")
    assert str(spec.get("confirm_q") or "").strip(), "and a confirmation the operator hears says what it does"
