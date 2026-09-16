"""V2-707 F1 · The generic data door: any operation over a widget's rows, through the SAME funnel.

## What he asked (2026-09-16)

> «Si el Brainworker puede acceder a los datos de la memoria de la agenda, puede perfectamente ver la
> estructura de los datos y borrarlo todo. […] Los guardarraíles, las tools, las hash tables de las acciones
> son para agilizar ciertas cosas. Pero el resto también tiene que ser posible.»

Right about the goal. What a worker must NOT do is write `widgets/_data/<id>/state.json`, for four reasons
each measured on this tree: the agenda MIRRORS Google and `tick()` brings a file-deleted row back (the 46
that resurrected on 2026-09-15); `store.save` is what notifies the canvas; the store has one writer and a
worker is another process; and the V2-705 contract lives in the funnel.

So the door is a RESOLVER, not a second writer. It turns an expression over the data into the rows it
matches and runs the widget's OWN declared action on each — the mirror, the canvas, the snapshot and the
contract all still happen, and there is no second doctrine about the same data. `party.py`'s shape applied
to data: freedom of reasoning, zero freedom of consequence.

These cases pin: what an expression may say, that the declared action carries every write, that the
friction is the RADIUS and not a verb, that nothing matching is refused rather than silently doing nothing,
and that a collection may declare itself read-only.
"""
from __future__ import annotations

import asyncio

import pytest

from widgets import rows


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """ISOLATED store — these tests must never touch the operator's real calendar."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    db = ag.load_db()
    db["meetings"] = [
        {"id": "m1", "title": "Dentist", "date": "2035-01-01", "startTime": "17:00"},
        {"id": "m2", "title": "Meeting with Cryptonite", "date": "2035-01-02", "startTime": "17:00"},
        {"id": "m3", "title": "Crypto standup", "date": "2035-01-03", "startTime": "09:00"},
        {"id": "m4", "title": "Dentist", "date": "2024-01-01", "startTime": "10:00"},   # past
    ]
    store.save(ag.WIDGET_ID, db)
    return ag


def _run(action, payload):
    from widgets import server_api
    return asyncio.run(server_api.brain_action("agenda", action, payload))


def _titles(ag):
    return sorted(m["title"] + "@" + m["date"] for m in ag.load_db()["meetings"])


# ── the expression: closed in OPERATORS, open in CONTENT ───────────────────────────────────────────────

@pytest.mark.parametrize("where,expected", [
    ({}, 4),                                          # everything: sayable, and gated by radius below
    ({"title": "Dentist"}, 2),                        # equality
    ({"title": "dentist"}, 2),                        # …folding case
    ({"title~": "crypto"}, 2),                        # contains, folding case
    ({"date<": "2035-01-01"}, 1),                     # ISO dates compare as strings
    ({"date>=": "2035-01-02"}, 2),
    ({"title!": "Dentist"}, 2),                       # not-equal
    ({"id": ["m1", "m3"]}, 2),                        # a list means «any of these»
    ({"title~": "crypto", "date>=": "2035-01-03"}, 1),  # clauses are AND
    ({"title": "nothing here"}, 0),
])
def test_what_an_expression_may_say(agenda, where, expected):
    assert len(rows.select("agenda", "meetings", where)) == expected


def test_an_unknown_field_matches_nothing_rather_than_everything(agenda):
    """A typo in a field name must never widen the set — that is the V2-705 lesson at another door."""
    assert rows.select("agenda", "meetings", {"titel": "Dentist"}) == []


# ── the radius IS the gate ─────────────────────────────────────────────────────────────────────────────

def test_one_row_runs(agenda):
    res = _run("rows.delete", {"collection": "meetings", "where": {"id": "m2"}})
    assert res["ok"] and res["done"] == 1
    assert "Meeting with Cryptonite@2035-01-02" not in _titles(agenda)


def test_more_than_one_ASKS_and_touches_nothing(agenda):
    before = _titles(agenda)
    res = _run("rows.delete", {"collection": "meetings", "where": {"title": "Dentist"}})
    assert res["ok"] is False and res["error"] == rows.NEEDS_CONFIRM
    assert res["n"] == 2 and res["needs_confirm"] is True
    assert _titles(agenda) == before, "an unanswered question must leave the calendar alone"


def test_the_question_carries_the_count_AND_the_names(agenda):
    """«Are you sure?» over an unnamed number is not a question anybody can answer."""
    res = _run("rows.delete", {"collection": "meetings", "where": {"title~": "crypto"}})
    assert "2" in res["detail"]
    assert "Meeting with Cryptonite" in res["detail"] and "Crypto standup" in res["detail"]


def test_and_once_he_says_yes_it_really_runs(agenda):
    res = _run("rows.delete", {"collection": "meetings",
                               "where": {"title~": "crypto"}, "confirmed": True})
    assert res["ok"] and res["done"] == 2
    assert not [t for t in _titles(agenda) if "rypto" in t]


def test_the_whole_collection_is_sayable_and_asks(agenda):
    """«Borra la agenda entera» has no declared action, and it must be possible — behind the radius."""
    res = _run("rows.delete", {"collection": "meetings"})
    assert res["error"] == rows.NEEDS_CONFIRM and res["n"] == 4
    assert len(agenda.load_db()["meetings"]) == 4


# ── nothing matched is a MISUNDERSTANDING, never a silent no-op ────────────────────────────────────────

def test_an_expression_that_matches_nothing_is_refused_with_what_there_IS(agenda):
    res = _run("rows.delete", {"collection": "meetings", "where": {"title": "Board review"}})
    assert res["ok"] is False and res["error"] == rows.NOTHING_MATCHED
    assert any("Dentist" in o for o in res["options"]), res["options"]


def test_an_unknown_collection_says_which_ones_exist(agenda):
    res = _run("rows.delete", {"collection": "facturas"})
    assert res["error"] == rows.UNKNOWN_COLLECTION
    assert "meetings" in res["detail"] and set(res["collections"]) >= {"meetings", "tasks", "projects"}


def test_a_collection_may_declare_itself_read_only():
    """`mensajeria.items`: a message is SENT (`send_to`), never inserted, and `trash` keys on the visible
    position, which a filter has no business computing. Declaring the ops is the widget's own rail."""
    assert rows.ops_for("mensajeria", "items") == ("list",)
    res = asyncio.run(__import__("widgets.server_api", fromlist=["x"])
                      .brain_action("mensajeria", "rows.delete", {"collection": "items"}))
    assert res["error"] == rows.OP_NOT_ALLOWED


# ── the declared action carries every write (so the MIRROR travels) ────────────────────────────────────

def test_a_delete_goes_through_the_widgets_OWN_action_so_google_is_told(agenda, monkeypatch):
    """THE WHOLE POINT. If this door wrote the store itself, a row deleted here would stay in Google and
    come back on the next `tick()` — which is exactly what happened to 46 rows on 2026-09-15."""
    from widgets.agenda import gcal
    told = []
    monkeypatch.setattr(gcal, "delete_google", lambda m: told.append(m.get("title")) or True)
    db = agenda.load_db()
    db["meetings"] = [{"id": "g1", "title": "Board review", "date": "2035-02-02",
                       "startTime": "10:00", "source": "google", "googleId": "abc"}]
    from widgets import store
    store.save(agenda.WIDGET_ID, db)

    res = _run("rows.delete", {"collection": "meetings", "where": {"title~": "board"}})
    assert res["ok"] and res["done"] == 1
    assert told == ["Board review"], "the widget's own action has to run, so the mirror is told"


def test_the_door_declares_which_action_carries_each_operation():
    """Structural: every `via` a manifest names must be an action that manifest actually declares, or the
    door resolves rows and then calls nothing."""
    import json
    import pathlib
    engine = pathlib.Path(__file__).resolve().parents[4]
    for wid in ("agenda", "contactos", "mensajeria"):
        man = json.loads((engine / "widgets" / wid / "manifest.json").read_text(encoding="utf-8"))
        for coll, spec in (man.get("collections") or {}).items():
            for op, act in (spec.get("via") or {}).items():
                assert act in man["actions"], f"{wid}.{coll}.{op} → «{act}» is not a declared action"
                assert op in rows.ops_for(wid, coll), f"{wid}.{coll} declares a `via` for a disallowed op"


def test_the_generic_door_sits_INSIDE_the_single_funnel():
    """A second write path is the defect this whole batch exists against, so the door must be reached
    through `_dispatch` — where the contract, the production gate and the provenance already are."""
    import pathlib
    engine = pathlib.Path(__file__).resolve().parents[4]
    src = (engine / "widgets" / "server_api.py").read_text(encoding="utf-8")
    body = src[src.index("async def _dispatch("):src.index("async def widget_action(")]
    assert 'action or "").startswith("rows.")' in body
    assert body.index("contract.guard(") < body.index('startswith("rows.")'), (
        "the contract runs first, for the generic door too")


# ── reading ────────────────────────────────────────────────────────────────────────────────────────────

def test_a_read_is_bounded_and_says_how_many_there_are(agenda):
    res = _run("rows.list", {"collection": "meetings", "where": {"title~": "crypto"}})
    assert res["ok"] and res["n"] == 2 and len(res["rows"]) == 2


def test_the_schema_hands_the_worker_the_STRUCTURE(agenda):
    """What he asked for literally: «puede perfectamente ver la estructura de los datos»."""
    sch = rows.schema("agenda")["meetings"]
    assert sch["id"] == "title" and sch["count"] == 4 and sch["mirror"] == "google"
    assert {"title", "date", "startTime"} <= set(sch["fields"])
    assert set(sch["ops"]) == {"list", "put", "patch", "delete"}


# ── a refusal must reach the WORKER with a way out ─────────────────────────────────────────────────────

def test_the_worker_bridge_carries_the_refusals_ACTIONABLE_half(agenda):
    """`worker_api.widget_data` returned the bare code, so a worker that hit the V2-705 contract read
    «selector_missing» with no menu, and one that hit the radius gate read «needs_confirm» with neither the
    count nor the names nor the fact that answering is the way through. Same lesson as V2-203 at the bridge
    next door: for a worker, a message with no way out is a message that stops it."""
    import types
    from nucleo import worker_api
    rec = types.SimpleNamespace(task_id="t1", trace_id="", goal="", sheet="", surface="")

    gate = asyncio.run(worker_api._exec_allow(
        "widget_data", {"widget_id": "agenda", "action": "rows.delete",
                        "payload": {"collection": "meetings"}}, rec))
    assert gate["ok"] is False and gate["error"] == rows.NEEDS_CONFIRM
    assert gate["n"] == 4 and gate["names"] and "Dentist" in gate["detail"]

    contract_refusal = asyncio.run(worker_api._exec_allow(
        "widget_data", {"widget_id": "agenda", "action": "cancel_meeting", "payload": {}}, rec))
    assert contract_refusal["error"] == "selector_missing"
    assert "Dentist" in contract_refusal["detail"], "the menu the model is told to pick from has to travel"
