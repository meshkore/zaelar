"""V2-748 — the whole card, one order at a time, against a real store.

The operator, after the delete that became a browser search for bread: *«no te olvides de lanzar esa prueba
completa contra el widget de la agenda y las tareas ahora mismo y asegurarte de que todo funciona bien y de
que **todas las órdenes posibles se interpretan correctamente**»*.

WHAT THIS ANSWERS, AND WHAT IT DOES NOT. Which ACTION a sentence picks is the model's decision and it is
measured live. What is deterministic — and what nothing measured before this — is the other half: that every
verb the manifest declares, called with the payload it declares, **lands on a real store or refuses with a
sentence that names what is missing**. A declared action that crashes, or that answers `{ok: True}` while
changing nothing, is the V2-540 failure with the halves swapped: the model picks it correctly and the
product does nothing.

⚠️ THE ISOLATION IS TWO STORES, NOT ONE, AND THAT IS NOT A DETAIL. Moving `widgets.store.DATA_DIR` moves the
agenda's data and leaves the CONNECTOR credentials exactly where they are, so `connect`/`disconnect` reach
the operator's REAL Google account. `conftest._the_suite_never_touches_the_operators_real_google_account`
has covered that since V2-689 — written the day a routine run of this directory unlinked the account he had
just connected — and `test_the_credential_store_is_moved_too` below is a guard on that fixture, not on this
file's own.

It is pinned here because on 2026-09-21 the same thing happened AGAIN, and this time nothing could have
caught it: the sweep of these actions was an ad-hoc script rather than a test, so it inherited none of the
conftest and **disconnected his live Google Calendar**. A refresh token is not recoverable from disk. The
lesson has a shape and this is its fourth payment: *the isolation lives in the suite, so work that is not in
the suite has none of it.*
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def ag(tmp_path, monkeypatch):
    """The widget's own store. The CREDENTIALS and the SCHEDULER are moved by this directory's conftest,
    autouse — see `test_the_credential_store_is_moved_too`, which fails if that ever stops being true."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as _d
    return _d


def _tomorrow() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))


#: Every declared action, in an order where each one finds what it needs. `None` means «assert it lands»;
#: a string means «assert it REFUSES and the refusal says this», which is a real answer and not a failure —
#: `rsvp_meeting` on an appointment nobody invited us to has nothing to answer.
_SCRIPT = [
    ("add_list", {"name": "Obra"}, None),
    ("add_task", {"title": "comprar el pan", "list": "Obra"}, None),
    ("add_task", {"title": "pintar el techo", "list": "Obra", "estimateMinutes": 60}, None),
    ("show_tasks", {"list": "Obra"}, None),
    ("update_task", {"task": "1", "list": "Obra", "newTitle": "comprar pan y leche"}, None),
    ("done", {"task": "2", "list": "Obra"}, None),
    ("snooze", {"taskId": "t_comprar_el_pan"}, None),
    ("not_now", {"taskId": "t_comprar_el_pan"}, None),
    ("drop", {"taskId": "t_pintar_el_techo"}, None),
    ("rename_list", {"list": "Obra", "newName": "La obra"}, None),
    ("delete_task", {"task": "comprar pan y leche", "list": "La obra"}, None),
    ("restore", {}, None),
    ("clear_list", {"list": "La obra"}, None),
    ("restore", {}, None),
    ("delete_list", {"list": "La obra"}, None),
    ("restore", {}, None),
    ("add_meeting", {"title": "Reunión con Iván", "date": "TOM", "startTime": "10:00",
                     "endTime": "11:00"}, None),
    ("set_reminder", {"title": "Reunión con Iván", "date": "TOM", "at": "09:30"}, None),
    ("move_meeting", {"title": "Reunión con Iván", "date": "TOM", "newDate": "TOM",
                      "newTime": "12:00"}, None),
    ("update_meeting", {"title": "Reunión con Iván", "date": "TOM", "location": "la oficina"}, None),
    ("invite", {"who": "ivan@example.com", "meeting": "Reunión con Iván", "date": "TOM"}, None),
    ("dedupe_meetings", {"title": "Reunión con Iván", "date": "TOM"}, None),
    ("show_day", {"day": "month"}, None),
    ("open_meeting", {"title": "Reunión con Iván"}, None),
    ("close_meeting", {}, None),
    ("rsvp_meeting", {"title": "Reunión con Iván", "date": "TOM", "answer": "yes"}, "invitación"),
    ("cancel_meeting", {"title": "Reunión con Iván", "date": "TOM"}, None),
    ("clear_range", {"from": "TOM", "to": "TOM"}, None),
    ("drop_project", {"projectId": "p1"}, None),
    ("clear_all", {}, None),
    ("set_default_calendar", {"calendarId": "primary"}, None),
    ("accept_proposal", {"errand_id": "no-such-errand"}, "propuesta"),
    ("decline_proposal", {"errand_id": "no-such-errand"}, "propuesta"),
    ("connect", {"provider": "google"}, None),
    ("disconnect", {"provider": "google"}, None),
]


def _fill(payload: dict) -> dict:
    return {k: (_tomorrow() if v == "TOM" else v) for k, v in payload.items()}


def test_every_declared_action_is_in_the_script():
    """The script is a FLOOR: a verb added to the manifest arrives with the call that exercises it, or this
    file quietly stops covering the card."""
    man = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))
    missing = sorted(set(man.get("actions") or {}) - {a for a, _p, _e in _SCRIPT})
    assert not missing, f"declared and never called here: {missing}"


def test_the_whole_card_runs_end_to_end_without_one_crash(ag):
    """One pass, in order, each action finding what the previous one left. A traceback here is the failure
    the operator cannot work around: the model chose right and the product fell over."""
    for action, payload, expect_refusal in _SCRIPT:
        try:
            res = ag.apply_action(action, _fill(payload))
        except Exception as e:  # noqa: BLE001 — naming it is the whole point
            raise AssertionError(f"«{action}» crashed: {type(e).__name__}: {e}") from e
        assert isinstance(res, dict), f"«{action}» answered {type(res).__name__}, not a view"
        blob = json.dumps(res, ensure_ascii=False)
        if expect_refusal:
            assert res.get("ok") is False, f"«{action}» should have refused and did not: {blob[:200]}"
            assert expect_refusal in blob, f"«{action}» refused without naming why: {blob[:200]}"
        else:
            assert res.get("ok") is not False, f"«{action}» refused: {blob[:240]}"


def test_the_credential_store_is_moved_too(ag, tmp_path):
    """`connect`/`disconnect` write to the CONNECTOR's own store, which `widgets.store.DATA_DIR` does not
    cover. The conftest moves it; this is the assertion that notices if it stops. Without it, one run of the
    script above disconnects the operator's real Google account and the refresh token is gone."""
    from connectors.calendar import oauth as _oauth
    assert pathlib.Path(_oauth.STORE).parent == tmp_path, "the calendar credentials are NOT isolated"
    assert ".meshkore/credentials" not in str(_oauth.STORE)


def test_a_write_verb_really_changes_the_store(ag):
    """`ok: True` is not evidence. Each of these is read back from `view_data()`, which is the screen."""
    ag.apply_action("add_list", {"name": "Obra"})
    ag.apply_action("add_task", {"title": "comprar el pan", "list": "Obra"})
    titles = lambda: [r["title"] for r in ag.view_data()["tasks"]["items"]["tl_obra"]]
    assert titles() == ["comprar el pan"]
    ag.apply_action("update_task", {"task": "1", "list": "Obra", "newTitle": "comprar pan y leche"})
    assert titles() == ["comprar pan y leche"]
    ag.apply_action("delete_task", {"task": "1", "list": "Obra"})
    assert titles() == []
    ag.apply_action("restore", {})
    assert titles() == ["comprar pan y leche"]


def test_a_selector_that_names_nothing_refuses_instead_of_guessing(ag):
    """The other half of «interpreted correctly»: a wrong reference must come back as a QUESTION, never as
    a silent hit on whatever was nearest. `clear_list` and `delete_list` refuse an EMPTY selector too
    (V2-705) — «vacíala» must never empty whatever happened to be open."""
    ag.apply_action("add_list", {"name": "Obra"})
    ag.apply_action("add_task", {"title": "comprar el pan", "list": "Obra"})
    for action, payload in (("delete_task", {"task": "17", "list": "Obra"}),
                            ("delete_task", {"task": "una tarea que no existe", "list": "Obra"}),
                            ("update_task", {"task": "17", "list": "Obra", "newTitle": "x"}),
                            ("clear_list", {}),
                            ("delete_list", {}),
                            ("rename_list", {"list": "una lista que no existe", "newName": "x"})):
        res = ag.apply_action(action, payload)
        assert res.get("ok") is False, f"«{action}» {payload} did not refuse: {json.dumps(res)[:200]}"
        assert str(res.get("error") or "").strip(), f"«{action}» refused with an empty reason"
