"""The deliverable sheet declares what an end state reads (V2-852 T10 follow-up, 2026-11-06).

Measured on the use-case battery of 2026-11-06, in both languages and on five search errands: every worker wrote its
checkpoint-1 goal in the grammar the door asks for — `results.items[title~=…] count≥n` — and the door refused it six
times in a row as an «undeclared collection». The results sheet, the card EVERY search errand delivers into, declared
no collection at all, so no end state could ever be written against it; `hbwidget rows results list` died the same
way (`unknown_collection`), and nothing told the worker what the card reads. The class: the deliverable card declares
no collection the grammar can read, and a sheet INSTANCE is not resolved to its card.

Now: the sheet declares `items` (read from its view, listed only); an instance id (`results::<sheet>`) declares what
its card declares and its rows are read on THAT sheet, never the base card; the refusal names what the card declares;
the worker's `read` sees the declared fields even on an empty sheet. The variants are a Spanish hunt by title, an
English one by price, and the other cards still reading as before.
"""
from __future__ import annotations

import pytest

from memory import db as memdb
from nucleo.circuit import spec, verify
from widgets import rows

SHEET = "ab12cd-ls1"
_ES = {"all": [{"widget": "results", "collection": "items", "where": {"title~": "sofá"}, "count": {"min": 3}}]}
_EN = {"all": [{"widget": "results", "collection": "items", "where": {"price<=": 150}, "count": {"min": 2}}]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db()
    memdb.get_db()
    spec.reset()
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path / "w"))
    from widgets.results.sheet_names import sheet_key
    items = [{"title": "Sofá chaise longue gris", "price": "120 €", "url": "https://x.example/1"},
             {"title": "Sofá cama 3 plazas", "price": "140 €", "url": "https://x.example/2"},
             {"title": "Sofá de piel marrón", "price": "390 €", "url": "https://x.example/3"}]
    store.save(sheet_key(SHEET), {"title": "Sofás", "subtitle": "", "items": items})
    monkeypatch.setattr(spec, "_emit", lambda label, e, **extra: None)
    yield
    spec.reset()
    memdb.reset_db()


def _worker(uid: str, sheet: str = SHEET):
    from nucleo.workers.session import SessionRecord
    r = SessionRecord(task_id=uid[-1], goal="find me a second-hand sofa under 150", uid=uid)
    r.sheet = sheet
    return r


def test_the_sheet_declares_its_rows_and_so_does_each_of_its_instances():
    assert "items" in rows.declared("results"), "the deliverable sheet declares no collection an end state can read"
    assert rows.declared(f"results::{SHEET}") == rows.declared("results"), "an instance does not declare its card's"
    assert rows.ops_for("results", "items") == ("list",), "the sheet's rows are written by its own actions, never put/patch"
    assert "meetings" in rows.declared("agenda") and "sections" in rows.declared("documento")


@pytest.mark.parametrize("dw", [_ES, _EN], ids=["es-title", "en-price"])
def test_a_search_workers_goal_on_its_sheet_is_taken_and_bound_to_that_sheet(world, monkeypatch, dw):
    from nucleo import dispatch
    rec = _worker(uid="u-861")
    monkeypatch.setitem(dispatch._SESSIONS, "1", rec)
    why = spec.session_goal("1", dw)
    assert why == "", f"the grammar goal every search worker writes was refused: {why}"
    assert rec.done_when["all"][0]["widget"] == f"results::{SHEET}", "the goal was not bound to the errand's own sheet"
    assert (spec.of_task("u-861") or {}).get("source") == "worker"


def test_the_end_state_is_read_on_the_errands_own_sheet_never_the_base_card(world):
    own = {"all": [{"widget": f"results::{SHEET}", "collection": "items", "where": {"title~": "sofá"}, "count": {"min": 3}}]}
    assert verify.check(own) is True, "the rows on the errand's sheet were not read"
    base = {"all": [{"widget": "results", "collection": "items", "where": {"title~": "sofá"}, "count": {"min": 3}}]}
    assert verify.check(base) is False, "the bare card read as the sheet (or as unreadable)"
    cheaper = {"all": [{"widget": f"results::{SHEET}", "collection": "items", "where": {"price<=": 150}, "count": 2}]}
    assert verify.check(cheaper) is True
    assert verify.check({"all": [{"widget": f"results::{SHEET}", "collection": "items", "where": {"title~": "mesa"}}]}) is False


def test_the_refusal_names_what_the_card_declares(world, monkeypatch):
    from nucleo import dispatch
    rec = _worker(uid="u-862")
    monkeypatch.setitem(dispatch._SESSIONS, "2", rec)
    why = spec.session_goal("2", {"all": [{"widget": "results", "collection": "fichas", "where": {"title~": "x"}, "count": 3}]})
    assert why and "«results» declares: items" in why and "title" in why, why
    why = spec.session_goal("2", {"all": [{"widget": "nosuchcard", "collection": "x", "where": {"title~": "x"}}]})
    assert "«nosuchcard» is not a card" in why, why
    assert not rec.done_when


def test_the_generic_rows_door_and_the_workers_read_see_the_sheet(world):
    got = rows.plan(f"results::{SHEET}", "list", {"collection": "items", "where": {"title~": "sofá"}})
    assert got.get("ok") and got.get("n") == 3, got
    assert rows.plan(f"results::{SHEET}", "delete", {"collection": "items"}).get("ok") is False
    empty = rows.schema("results::never-written")
    assert "items" in empty and {"title", "url", "price"} <= set(empty["items"]["fields"]) and empty["items"]["count"] == 0
    assert rows.schema(f"results::{SHEET}")["items"]["count"] == 3


def test_every_command_the_goal_help_and_the_widget_usage_name_is_one_the_worker_can_run():
    """Measured 2026-11-06 (8 judge inputs, 18 attempts): the goal help said «`hbwidget read <widget>`», the worker
    composed `python -m nucleo.cli.hbwidget read results`, and the harness's permission gate asked for approval every
    time — a headless worker has nobody to say yes, so it could neither read the sheet's grammar nor state its end
    state. A help text names a command by the module that answers to it, and every module it names exists."""
    import importlib.util
    import re

    from nucleo.cli import report, widget
    texts = [report._GOAL_HELP, widget.__doc__ or ""]
    src = open(widget.__file__, encoding="utf-8").read()
    texts += re.findall(r'"(uso: [^"]+)"', src)
    joined = "\n".join(texts)
    assert not re.search(r"`hb[a-z]+\b", joined), "the help names a command by an alias no module answers to"
    named = set(re.findall(r"-m (nucleo\.cli\.[a-z_]+)", joined))
    assert {"nucleo.cli.widget"} <= named, named
    missing = [m for m in named if importlib.util.find_spec(m) is None]
    assert not missing, f"the help names modules that do not exist: {missing}"
