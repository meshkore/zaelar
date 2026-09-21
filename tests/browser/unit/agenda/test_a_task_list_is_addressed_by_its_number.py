"""V2-744 — the agenda's TASKS section: numbered lists the operator drives by voice.

His words (2026-09-21): *«quiero que haya una lista general de tareas y luego que el usuario pueda generar
una lista para varias cosas… podemos generar una lista de la compra y eso tendrá un identificador… asegúrate
de que todo está bastante numerado para que cuando yo vea una lista le diga: ábreme la lista número 3, coge
el ítem número 2 y modifícalo por esto»*.

So the case this file measures is not «can a task be stored». It is that **the number he reads on screen is
the number he can speak**, in both directions and after every kind of edit — and that the vocabulary
reaches him: a capability the manifest does not declare is one the model will narrate instead of doing
(V2-540), which is the defect that made `show_day` exist.

The store is isolated on the first line of every fixture: a test never touches the operator's real agenda.
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


def _lists(ag):
    return ag.view_data()["tasks"]["lists"]


def _items(ag, list_id):
    return ag.view_data()["tasks"]["items"][list_id]


def _by_no(ag, n):
    return next(l for l in _lists(ag) if l["no"] == n)


# ── the vocabulary EXISTS, or the model can only narrate it ────────────────────────────────────────────

def test_every_task_verb_is_declared_where_the_model_can_pick_it():
    """`apply_action` handling a verb the manifest never names is the V2-540 failure: there is no wrong
    tool to choose, there is NO tool, and the reply becomes «te lo apunto» with nothing behind it."""
    m = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))
    for name in ("add_task", "update_task", "delete_task", "done",
                 "add_list", "rename_list", "clear_list", "delete_list", "show_tasks"):
        assert name in m["actions"], f"«{name}» is unreachable by voice"
    from widgets.agenda import tasklists
    # …and the other direction: a declared action nobody handles is a dead entry the gate rejects.
    for name in tasklists.ACTIONS:
        assert name in m["actions"], f"«{name}» is handled and undeclared"


def test_the_manifest_tells_HIS_tasks_apart_from_the_agents_jobs():
    """The operator's rule is a vocabulary split, and the only place it can act on routing is the prose the
    model reads. Without it, «ábreme las tareas» opens the wall's job list, which is what it used to do."""
    m = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))
    txt = (m["whenToUse"] + " " + m["usage"]).lower()
    assert "tareas" in txt and "lista" in txt
    assert "proceso" in txt, "nothing distinguishes his tasks from the agent's own work"
    assert "show_tasks" in m["usage"], "the way to OPEN the section has to be named in the usage line"


def test_opening_the_section_is_an_action_and_changes_no_data(ag):
    """A view action, like `show_day`: «ábreme la lista de la compra» has to LAND, and reopening the card
    can never select a list by itself."""
    m = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))
    assert m["actions"]["show_tasks"].get("view") is True

    ag.apply_action("add_list", {"name": "La compra"})
    before = json.dumps(ag.load_db().get("tasks", []), sort_keys=True)
    res = ag.apply_action("show_tasks", {"list": "la compra"})
    assert res["tasks"]["view"]["list"] == "tl_la_compra"
    assert json.dumps(ag.load_db().get("tasks", []), sort_keys=True) == before

    # Asking TWICE for the same list still lands: the token is a counter, not the list (the V2-540 rule).
    n1 = ag.view_data()["tasks"]["view"]["n"]
    ag.apply_action("show_tasks", {"list": "la compra"})
    assert ag.view_data()["tasks"]["view"]["n"] == n1 + 1


# ── the general list, and the ones he makes ────────────────────────────────────────────────────────────

def test_a_fresh_agenda_already_has_the_general_list(ag):
    ls = _lists(ag)
    assert [l["no"] for l in ls] == [1]
    assert ls[0]["id"] == "general" and ls[0]["builtin"] is True


def test_a_task_with_no_list_lands_in_general_and_lists_are_numbered_in_order(ag):
    ag.apply_action("add_task", {"title": "Llamar al banco"})
    ag.apply_action("add_list", {"name": "La compra"})
    ag.apply_action("add_list", {"name": "Casa"})
    assert [(l["no"], l["name"]) for l in _lists(ag)] == [(1, "General"), (2, "La compra"), (3, "Casa")]
    assert [i["title"] for i in _items(ag, "general")] == ["Llamar al banco"]


def test_the_list_carries_an_identifier_he_could_hand_to_another_agent(ag):
    """«eso tendrá un identificador y ese identificador lo podré compartir en el futuro con otro agente a
    través de la red de MeshKore». A readable slug rather than a hex blob, because he will read it aloud."""
    res = ag.apply_action("add_list", {"name": "La compra"})
    assert res["list"] == "tl_la_compra"
    assert _by_no(ag, 2)["id"] == "tl_la_compra"


def test_the_same_list_asked_for_twice_is_not_two_lists(ag):
    ag.apply_action("add_list", {"name": "La compra"})
    r = ag.apply_action("add_list", {"name": "la  COMPRA"})
    assert r.get("existed") is True
    assert len(_lists(ag)) == 2


# ── «la lista número 3, el ítem número 2» ──────────────────────────────────────────────────────────────

@pytest.fixture
def shopping(ag):
    ag.apply_action("add_list", {"name": "La compra"})
    for t in ("Pan", "Leche", "Huevos"):
        ag.apply_action("add_task", {"title": t, "list": "la compra"})
    return ag


def test_an_item_is_reachable_by_the_number_the_screen_shows(shopping):
    assert [(i["no"], i["title"]) for i in _items(shopping, "tl_la_compra")] == \
        [(1, "Pan"), (2, "Leche"), (3, "Huevos")]
    shopping.apply_action("done", {"list": "2", "task": "2"})
    assert [(i["no"], i["status"]) for i in _items(shopping, "tl_la_compra")] == \
        [(1, "todo"), (2, "done"), (3, "todo")]


@pytest.mark.parametrize("said", ["2", "la 2", "lista 2", "la lista número 2", "segunda",
                                  "la compra", "COMPRA", "tl_la_compra"])
def test_however_he_names_the_list_it_is_the_same_list(shopping, said):
    r = shopping.apply_action("add_task", {"title": "Aceite", "list": said})
    assert r["list"] == "tl_la_compra", (said, r)


@pytest.mark.parametrize("said", ["2", "el 2", "el ítem 2", "item numero 2", "segundo", "Leche", "leche"])
def test_however_he_names_the_item_it_is_the_same_item(shopping, said):
    r = shopping.apply_action("delete_task", {"list": "la compra", "task": said})
    assert r["deleted"] == "Leche", (said, r)


def test_a_title_that_CONTAINS_a_number_is_not_a_position(ag):
    """«comprar 2 barras de pan» is a thing to do, not «item 2» — and reading it as a position would act on
    a row he never mentioned. The rule: it is a number only when the number is ALL that is left."""
    from widgets.agenda import tasklists
    assert tasklists.number_in("comprar 2 barras de pan") is None
    assert tasklists.number_in("el ítem 2") == 2
    ag.apply_action("add_list", {"name": "Casa"})
    ag.apply_action("add_task", {"title": "Pintar", "list": "casa"})
    ag.apply_action("add_task", {"title": "Comprar 2 barras de pan", "list": "casa"})
    r = ag.apply_action("delete_task", {"list": "casa", "task": "comprar 2 barras de pan"})
    assert r["deleted"] == "Comprar 2 barras de pan"


def test_deleting_renumbers_what_is_left_because_the_number_IS_the_position(shopping):
    shopping.apply_action("delete_task", {"list": "la compra", "task": "1"})
    assert [(i["no"], i["title"]) for i in _items(shopping, "tl_la_compra")] == [(1, "Leche"), (2, "Huevos")]
    # …and the NEXT «el 1» means what the screen now says it means.
    shopping.apply_action("done", {"list": "la compra", "task": "1"})
    assert _items(shopping, "tl_la_compra")[0]["status"] == "done"


def test_a_number_that_is_not_there_is_a_refusal_that_names_what_IS(shopping):
    r = shopping.apply_action("done", {"list": "la compra", "task": "9"})
    assert r["ok"] is False
    assert "9" in r["error"] and "Pan" in r["error"], r["error"]
    # nothing moved
    assert all(i["status"] == "todo" for i in _items(shopping, "tl_la_compra"))


def test_two_lists_that_could_both_be_meant_are_a_QUESTION_not_a_guess(ag):
    ag.apply_action("add_list", {"name": "Compra semanal"})
    ag.apply_action("add_list", {"name": "Compra de Navidad"})
    r = ag.apply_action("add_task", {"title": "Turrón", "list": "compra"})
    assert r["ok"] is False and "Compra semanal" in r["error"] and "Compra de Navidad" in r["error"]


# ── filling, emptying and editing ──────────────────────────────────────────────────────────────────────

def test_an_item_can_be_renamed_moved_and_reopened(shopping):
    shopping.apply_action("update_task", {"list": "la compra", "task": "1", "newTitle": "Pan integral"})
    assert _items(shopping, "tl_la_compra")[0]["title"] == "Pan integral"

    shopping.apply_action("add_list", {"name": "Casa"})
    shopping.apply_action("update_task", {"list": "la compra", "task": "Pan integral", "newList": "casa"})
    assert [i["title"] for i in _items(shopping, "tl_la_compra")] == ["Leche", "Huevos"]
    assert [i["title"] for i in _items(shopping, "tl_casa")] == ["Pan integral"]

    shopping.apply_action("done", {"list": "casa", "task": "1"})
    shopping.apply_action("update_task", {"list": "casa", "task": "1", "status": "pendiente"})
    assert _items(shopping, "tl_casa")[0]["status"] == "todo"


def test_a_task_can_carry_a_day_and_an_hour_he_SPOKE(ag):
    ag.apply_action("add_task", {"title": "Renovar el DNI", "date": "mañana", "time": "cinco de la tarde"})
    it = _items(ag, "general")[0]
    assert it["time"] == "17:00"
    assert it["date"] == ag.view_data()["days"][1]["date"]


def test_emptying_a_list_keeps_the_list_and_deleting_it_does_not(shopping):
    shopping.apply_action("clear_list", {"list": "la compra"})
    assert _items(shopping, "tl_la_compra") == []
    assert len(_lists(shopping)) == 2, "clear_list empties, it does not remove the list"

    shopping.apply_action("add_task", {"title": "Pan", "list": "la compra"})
    shopping.apply_action("delete_list", {"list": "la compra"})
    assert [l["name"] for l in _lists(shopping)] == ["General"]
    assert shopping.load_db().get("tasks") == [], "its items went with it"


def test_the_general_list_is_emptied_and_never_removed(ag):
    """It is where a task with no home lands, so deleting it would leave the next `add_task` writing into
    a list that does not exist."""
    ag.apply_action("add_task", {"title": "Algo"})
    r = ag.apply_action("delete_list", {"list": "general"})
    assert r.get("kept_list") is True
    assert [l["id"] for l in _lists(ag)] == ["general"]
    assert _items(ag, "general") == []


def test_emptying_without_saying_WHICH_is_refused(shopping):
    """An empty selector never means «the one on screen» for a verb that removes things — `pick_list`
    falls back to the open list by design, which is right for «añade pan» and wrong for «vacíala»."""
    for act in ("clear_list", "delete_list"):
        r = shopping.apply_action(act, {})
        assert r["ok"] is False, act
        assert "La compra" in r["error"], r["error"]
    assert len(_items(shopping, "tl_la_compra")) == 3


def test_renaming_a_list_keeps_its_items_and_its_number(shopping):
    shopping.apply_action("rename_list", {"list": "2", "newName": "Súper"})
    l = _by_no(shopping, 2)
    assert l["name"] == "Súper" and l["total"] == 3


def test_progress_is_what_the_row_shows(shopping):
    shopping.apply_action("done", {"list": "la compra", "task": "1"})
    l = _by_no(shopping, 2)
    assert (l["done"], l["total"]) == (1, 3)


# ── the two halves of the card agree, and the day plan is not invaded ──────────────────────────────────

def test_the_brain_reads_the_SAME_numbering_the_screen_shows(shopping):
    """`index.py`'s own lesson: two views of one card that disagree about what «the second one» is are
    worse than one view. The digest is built from the same function the render is."""
    digest = shopping.prompt_digest()
    assert "lista 2. «La compra»" in digest
    assert "2. Leche" in digest
    assert "id=tl_la_compra" in digest, "the shareable id belongs in what the brain can read back to him"
    hints = {r["label"]: r["hint"] for r in shopping.ref_index()}
    assert hints["Leche"] == "La compra #2"


def test_a_checklist_item_does_not_book_half_an_hour_of_his_day(shopping):
    """The planner turns a task into a BLOCK, and it used to invent 30 minutes for anything without one.
    With a shopping list in the same array that invention becomes visible: «Pan» would take the 9:00 slot."""
    plan = shopping.view_data()["plan"]
    assert [b for b in plan["blocks"] if b.get("taskId")] == [], plan["blocks"]

    # …and a task that DOES say how long it takes is still planned, which is the half that must not break.
    shopping.apply_action("add_task", {"title": "Revisar el contrato", "estimateMinutes": 45})
    blocks = [b for b in shopping.view_data()["plan"]["blocks"] if b.get("taskId")]
    assert [b["label"] for b in blocks] == ["Revisar el contrato"]


def test_an_agenda_written_before_today_keeps_its_tasks(ag, tmp_path):
    """The lazy migration. A task written by an older build has no `listId`, and a section built around
    lists would have shown him an empty screen — data loss wearing the face of a fresh start."""
    from widgets import store
    store.save("agenda", {"tasks": [{"id": "t_old", "title": "De antes", "status": "todo"}],
                          "meetings": [], "projects": [], "ideas": [], "recurring": [],
                          "user": {"workStart": "09:00", "workEnd": "18:00"}})
    assert [i["title"] for i in _items(ag, "general")] == ["De antes"]
    assert _items(ag, "general")[0]["no"] == 1
