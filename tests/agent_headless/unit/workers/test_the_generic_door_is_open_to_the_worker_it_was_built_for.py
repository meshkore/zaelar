"""V2-710 T0.2 · The generic data door, open to the Brain Worker it was built for.

## What was measured (2026-09-16)

`widgets/rows.py` was born from a sentence the operator said ABOUT THE WORKER:

> «Si el Brainworker puede acceder a los datos de la memoria de la agenda, puede perfectamente ver la
> estructura de los datos y borrarlo todo. […] Los guardarraíles, las tools, las hash tables de las
> acciones son para agilizar ciertas cosas. Pero el resto también tiene que ser posible.»

Everything got built except the last wire. `nucleo/widget_cli.py` documents `hbwidget rows` to the worker,
`read_widget` hands it the collection schema so it can write the expression, and then:

    classify_act("widget_data", {"widget_id": "agenda", "action": "rows.delete"}) -> deny
    classify_act("widget_data", {"widget_id": "agenda", "action": "rows.list"})   -> deny
    classify_act("widget_data", {"widget_id": "agenda", "action": "cancel_meeting"}) -> allow

because the `widget_data` branch resolves the mode with `frontend.action_mode`, which answers `None` for
anything not DECLARED in the manifest — and `rows.*` is not declared there BY DESIGN: it is the door for
what nobody declared. The denial then told the worker «LEE el widget primero y usa una de sus acciones
declaradas», advice it cannot follow, about the one capability built for this exact case. Net effect: the
generic door had no live caller at all (V2-540's class — a capability nobody can reach is one the model
narrates instead of using).

## Why ALLOW and not CONFIRM

The friction of this door is the RADIUS, not the verb (V2-707 F1): `rows.apply` runs one matching row and
refuses several with the count and the names until the operator says yes. Each row is executed through the
widget's OWN declared action, so the V2-705 contract, the external mirror, the canvas refresh and the
snapshot all still happen. Marking the door CONFIRM would put a second question in front of a gate that
already asks the right one, on `rows.list` too — a read.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.worker_policy import ALLOW, CONFIRM, DENY, classify_act


def _act(_kind, **payload):
    return classify_act(_kind, payload)


# ── 1 · the door answers the worker ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("op", ["list", "put", "patch", "delete"])
def test_every_generic_op_is_allowed_to_the_worker(op):
    assert _act("widget_data", widget_id="agenda", action=f"rows.{op}") == ALLOW, (
        f"rows.{op} is the door V2-707 F1 built FOR the worker; denying it leaves the door with no caller")


def test_the_door_does_not_depend_on_the_widget_declaring_it():
    """That is the whole point: it is the path for what nobody wrote an action for."""
    assert _act("widget_data", widget_id="lista_de_la_compra", action="rows.delete") == ALLOW


def test_a_widget_that_does_not_exist_is_still_refused_downstream_not_here():
    """`classify_act` is policy, not existence: `worker_api` resolves the widget and answers `not_found`.
    Pinned so nobody re-adds a catalog lookup here and re-closes the door by a different route."""
    assert _act("widget_data", widget_id="", action="rows.list") == ALLOW


# ── 2 · what the change must NOT move ─────────────────────────────────────────────────────────────────────

def test_a_declared_FAST_action_is_still_allowed():
    assert _act("widget_data", widget_id="agenda", action="cancel_meeting") == ALLOW


def test_an_UNDECLARED_named_action_is_still_denied():
    """The `rows.` prefix is the door. An invented verb is still an invented verb."""
    assert _act("widget_data", widget_id="agenda", action="nuke_everything") == DENY


def test_an_outward_facing_action_still_asks():
    assert _act("push_channel", channel="whatsapp") == CONFIRM


def test_an_operator_only_tool_is_still_denied():
    assert _act("use_tool", tool="delete_widget") == DENY


# ── 3 · and the radius still is the friction, through the worker's own door ──────────────────────────────

@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real calendar."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.agenda import data as ag
    db = ag.load_db()
    db["meetings"] = [
        {"id": "m1", "title": "Dentist", "date": "2035-01-01", "startTime": "17:00"},
        {"id": "m2", "title": "Meeting with Cryptonite", "date": "2035-01-02", "startTime": "17:00"},
        {"id": "m3", "title": "Crypto standup", "date": "2035-01-03", "startTime": "09:00"},
    ]
    store.save(ag.WIDGET_ID, db)
    return ag


def _rows(op, body):
    from widgets import server_api
    return asyncio.run(server_api.brain_action("agenda", f"rows.{op}", body))


def test_one_row_runs(agenda):
    res = _rows("delete", {"collection": "meetings", "where": {"title": "Dentist"}})
    assert res.get("ok") is True and res.get("done") == 1, res
    assert [m["title"] for m in agenda.load_db()["meetings"]] == ["Meeting with Cryptonite", "Crypto standup"]


def test_several_rows_ask_with_the_count_and_the_names(agenda):
    res = _rows("delete", {"collection": "meetings", "where": {"title~": "crypto"}})
    assert res.get("ok") is False and res.get("needs_confirm") is True, res
    assert res.get("n") == 2 and len(res.get("names") or []) == 2
    assert len(agenda.load_db()["meetings"]) == 3, "nothing may run while the question is open"
