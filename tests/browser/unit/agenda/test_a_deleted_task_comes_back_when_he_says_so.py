"""V2-748 — a removal that no longer asks, and the trash that makes that safe.

Operator, 2026-09-21, after watching a delete turn into a browser search for bread:

    «No quiero que me pida confirmación para borrar tareas, ¿vale? Añade esto ya como una regla por
    defecto. La agenda va directa. Cuando digo borrar esto, lo borras sin preguntar. (…) Otra cosa es
    que guardes un rastro de lo que había, por si me he equivocado, y te digo restáuralo.»

Two halves of ONE rule, and shipping either alone would be a worse product than before: direct removal with
no way back turns a mis-heard word into lost data, and a trash nobody can reach is a store that only grows.

WHAT THIS PINS, and why each one is here rather than assumed:

  · the removal ASKS NOTHING — `delete_task` declares `confirm: false` and the module writes the row out
    without a question anywhere in the path;
  · the trash keeps the row VERBATIM, the same id and the same list, because restoring from a title is a
    new task wearing the old one's name;
  · and it keeps the SLOT. `items()` numbers by store order and the number is the whole way he addresses a
    task («borra el ítem 2»), so an undo that appends gives him back the data and not the screen. Written
    the other way round first: `_pos` of the first row is 0, and `x or default` reads 0 as absent, so every
    restore landed at the bottom of the list.

The store is isolated on the first line of the fixture: a test never touches the operator's real agenda.
"""
from __future__ import annotations

import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def ag(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real agenda."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as _d
    return _d


@pytest.fixture
def obra(ag):
    """His own list, from the session that caused this: «Obra», with three rows in a known order."""
    ag.apply_action("add_list", {"name": "Obra"})
    for title in ("comprar el pan", "pintar el techo", "llamar al fontanero"):
        ag.apply_action("add_task", {"title": title, "list": "Obra"})
    return "tl_obra"


def _titles(ag, list_id):
    return [r["title"] for r in ag.view_data()["tasks"]["items"][list_id]]


def _nos(ag, list_id):
    return [(r["no"], r["title"]) for r in ag.view_data()["tasks"]["items"][list_id]]


# ── the removal asks nothing ─────────────────────────────────────────────────────────────────────────────

def test_deleting_a_task_never_asks_for_confirmation():
    """`confirm: true` is what makes the FlashBrain stop and ask (`widgets/actions.CONFIRM`). His rule says
    the agenda goes direct, so the two row verbs must not carry it."""
    m = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))
    for name in ("delete_task", "add_task", "restore"):
        assert m["actions"][name].get("confirm") is not True, f"«{name}» would stop and ask"


def test_the_delete_happens_at_once_and_says_it_can_be_undone(ag, obra):
    out = ag.apply_action("delete_task", {"task": "1", "list": "Obra"})
    assert _titles(ag, obra) == ["pintar el techo", "llamar al fontanero"]
    # The result carries the flag the voice reads to offer the way back — without it the capability exists
    # and nobody is ever told about it, which is the V2-540 failure in its quietest form.
    assert json.dumps(out).find("undo") >= 0


# ── and the trash gives back the screen, not only the data ───────────────────────────────────────────────

def test_the_row_comes_back_in_the_slot_it_was_read_from(ag, obra):
    assert _nos(ag, obra)[0] == (1, "comprar el pan")
    ag.apply_action("delete_task", {"task": "1", "list": "Obra"})
    ag.apply_action("restore", {})
    assert _nos(ag, obra) == [(1, "comprar el pan"), (2, "pintar el techo"), (3, "llamar al fontanero")]


def test_a_middle_row_comes_back_to_the_middle(ag, obra):
    ag.apply_action("delete_task", {"task": "2", "list": "Obra"})
    assert _titles(ag, obra) == ["comprar el pan", "llamar al fontanero"]
    ag.apply_action("restore", {})
    assert _titles(ag, obra) == ["comprar el pan", "pintar el techo", "llamar al fontanero"]


def test_the_restored_row_is_the_same_row_and_not_a_copy_of_its_title(ag, obra):
    before = next(t for t in ag.load_db()["tasks"] if t["title"] == "comprar el pan")
    ag.apply_action("delete_task", {"task": "1", "list": "Obra"})
    ag.apply_action("restore", {})
    after = next(t for t in ag.load_db()["tasks"] if t["title"] == "comprar el pan")
    assert after == before, "the row came back rebuilt instead of restored"


def test_no_internal_bookkeeping_leaks_into_the_restored_row(ag, obra):
    """The slot travels in the trash entry, never in the task. A `_pos` left on the row would reach the
    render, the digest and Google's sync as a field of the operator's data."""
    ag.apply_action("delete_task", {"task": "1", "list": "Obra"})
    ag.apply_action("restore", {})
    assert all("_pos" not in t for t in ag.load_db()["tasks"])


def test_emptying_a_list_is_undoable_whole(ag, obra):
    ag.apply_action("clear_list", {"list": "Obra"})
    assert _titles(ag, obra) == []
    ag.apply_action("restore", {})
    assert _titles(ag, obra) == ["comprar el pan", "pintar el techo", "llamar al fontanero"]


def test_deleting_a_list_brings_back_the_list_and_its_rows(ag, obra):
    ag.apply_action("delete_list", {"list": "Obra"})
    assert all(l["id"] != obra for l in ag.view_data()["tasks"]["lists"])
    ag.apply_action("restore", {"what": "obra"})
    assert any(l["id"] == obra for l in ag.view_data()["tasks"]["lists"])
    assert _titles(ag, obra) == ["comprar el pan", "pintar el techo", "llamar al fontanero"]


def test_the_list_comes_back_BEFORE_its_rows_or_they_are_homeless(ag, obra):
    """`migrate` moves a task whose list does not exist into General — so a restore that puts the rows back
    first and the list second loses them to the general list on the very next read."""
    ag.apply_action("delete_list", {"list": "Obra"})
    ag.apply_action("restore", {})
    from widgets.agenda import tasklists
    assert _titles(ag, tasklists.GENERAL) == []


def test_he_can_name_which_removal_he_wants_back(ag, obra):
    ag.apply_action("delete_task", {"task": "comprar el pan", "list": "Obra"})
    ag.apply_action("delete_task", {"task": "llamar al fontanero", "list": "Obra"})
    ag.apply_action("restore", {"what": "comprar el pan"})
    assert _titles(ag, obra) == ["comprar el pan", "pintar el techo"]


def test_restoring_twice_does_not_duplicate_the_row(ag, obra):
    ag.apply_action("delete_task", {"task": "1", "list": "Obra"})
    ag.apply_action("restore", {})
    out = ag.apply_action("restore", {})
    assert _titles(ag, obra).count("comprar el pan") == 1
    assert "papelera" in json.dumps(out, ensure_ascii=False), "an empty trash has to SAY it is empty"


def test_an_empty_trash_refuses_and_names_what_it_has(ag, obra):
    from widgets.agenda import tasklists
    db = ag.load_db()
    out = tasklists.apply("restore", {"what": "una lista que nunca existió"}, db)
    assert out["ok"] is False
    ag.apply_action("delete_task", {"task": "1", "list": "Obra"})
    db = ag.load_db()
    out = tasklists.apply("restore", {"what": "una lista que nunca existió"}, db)
    assert out["ok"] is False and "comprar el pan" in out["error"], "it has to say what it DOES hold"


def test_the_trash_is_bounded(ag, obra):
    """It rides in the agenda's own store. An unbounded undo log is a store that grows for ever."""
    from widgets.agenda import tasklists
    db = ag.load_db()
    for i in range(tasklists.TRASH_MAX + 6):
        tasklists.apply("add_task", {"title": f"t{i}", "list": "Obra"}, db)
        tasklists.apply("delete_task", {"task": f"t{i}", "list": "Obra"}, db)
    assert len(db["trash"]) == tasklists.TRASH_MAX


def test_the_way_back_is_declared_where_the_model_can_pick_it():
    """V2-540 again: a capability the manifest does not name is one the model narrates instead of doing."""
    m = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))
    assert "restore" in m["actions"]
    from widgets.agenda import tasklists
    assert "restore" in tasklists.ACTIONS
