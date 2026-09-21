"""V2-747 — «la tarea número tres» reaches the row printed with a 3 beside it.

## The session

`16a39050` (2026-09-21), the operator's own, one day after V2-744 gave the agenda its numbered task lists.
He had a list «Obra» with three tasks on screen and said:

    «Vale, modifica la tarea número tres con crear la nueva cuenta y pedir la en el banco Vivid.»

The model did everything right — `agenda:update_task`, reference «la tarea 3 de la lista Obra» — and the
resolver answered `no_match` with an EMPTY candidate list, so he heard *«No tengo claro a cuál te refieres,
¿me lo concretas?»* over three tasks he was reading. His requirement for the whole feature, verbatim:

    «Asegúrate de que todo está bastante numerado para que cuando yo vea una lista de tareas le diga pues
     ábreme la lista número 3, coge el item número 2 y modifícalo por esto.»

## Three causes, and the third is the one that would have been shipped again

1. `positional: false` on the agenda (V2-643 — no calendar view numbers an appointment) ALSO silenced the
   tasks half, which numbers every row. One flag, two halves of one card.
2. `ref_index` published tasks under `taskId` only, while `update_task`/`delete_task` declare `ref: "task"`:
   for the two actions that CHANGE a task there was not one row to match against. Lists were not published
   at all, so `clear_list`/`rename_list`/`delete_list` could not resolve either.
3. Position resolved against the FLAT index, and a card with several numbered lists restarts at #1 in each.
   That is the dangerous one: it does not refuse, it silently picks the wrong row.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from widgets import refs

MANIFEST = Path(__file__).resolve().parents[4] / "widgets/agenda/manifest.json"


@pytest.fixture
def two_lists(monkeypatch):
    """Two lists, each numbered from 1 — the shape the card actually renders and the one that breaks a
    flat count. `field` is published once per key the manifest declares, which is the whole of cause 2."""
    rows = []
    for gi, (group, titles) in enumerate((("La compra", ["Pan", "Leche"]),
                                          ("Casa", ["Llamar al fontanero", "Pintar el techo"]))):
        for i, title in enumerate(titles):
            for f in ("taskId", "task"):
                rows.append({"id": f"t{gi}{i}", "label": title, "field": f, "no": i + 1,
                             "group": group, "hint": f"{group} #{i + 1}"})
    for i, name in enumerate(("La compra", "Casa")):
        rows.append({"id": f"tl_{i}", "label": name, "field": "list", "no": i + 1, "hint": f"#{i + 1}"})
    monkeypatch.setattr(refs, "_ref_index", lambda w: rows)
    return rows


def _r(action, ref, order=""):
    return refs.resolve("agenda", action, ref, {}, order=order)


# ── 1 · the flag ──────────────────────────────────────────────────────────────────────────────────────

def test_the_tasks_half_may_be_counted_even_though_the_calendar_may_not():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert man.get("positional") is False, (
        "the calendar half must stay uncountable — V2-643: «la tercera» over an unnumbered agenda would "
        "cancel an appointment nobody named")
    for a in ("done", "update_task", "delete_task", "show_tasks", "clear_list", "delete_list"):
        assert refs.positional("agenda", a) is True, f"«la {a} número 3» is unsayable: {a} is not positional"
    for a in ("cancel_meeting", "set_reminder", "dedupe_meetings"):
        assert refs.positional("agenda", a) is False, f"{a} counts rows nobody numbered"


# ── 2 · every action can see the rows it acts on ──────────────────────────────────────────────────────

@pytest.mark.parametrize("action,field", [("done", "taskId"), ("drop", "taskId"), ("update_task", "task"),
                                          ("delete_task", "task"), ("clear_list", "list"),
                                          ("rename_list", "list"), ("delete_list", "list")])
def test_every_task_action_resolves_against_rows_that_exist(two_lists, action, field):
    assert refs.id_field_for_action("agenda", action) == field
    got = [i for i in two_lists if i["field"] == field]
    assert got, f"«{action}» declares `{field}` and the index publishes no row under it: nothing to match"


def test_the_REAL_index_publishes_a_row_under_every_key_its_own_manifest_declares():
    """Over `tasklists.ref_rows` itself, not a fixture. The fixture above proves the RESOLVER works given
    the right rows; this proves the widget hands them over — and that is the half that was broken. A fixture
    that hardcodes both fields cannot fail when the widget stops publishing one of them (measured: that
    disarm came back green, so this exists)."""
    from widgets.agenda import tasklists
    db = {"tasks": [{"id": "t1", "title": "Pan", "status": "todo", "listId": "tl_c"}],
          "taskLists": [{"id": "general", "name": "General", "builtin": True},
                        {"id": "tl_c", "name": "La compra"}]}
    fields = {r["field"] for r in tasklists.ref_rows(db)}
    declared = {refs.id_field_for_action("agenda", a)
                for a in ("done", "drop", "snooze", "not_now", "update_task", "delete_task",
                          "clear_list", "rename_list", "delete_list")}
    assert declared <= fields, f"the manifest names {sorted(declared - fields)} and the index publishes none"
    for r in tasklists.ref_rows(db):
        assert isinstance(r.get("no"), int) and r["no"] >= 1, f"a row with no printed number: {r}"


def test_the_action_that_CHANGES_a_task_can_find_it_by_name(two_lists):
    """THE MEASURED FAILURE. `done` resolved «Transfer R4» and `update_task` did not — same task, same
    index, different declared key — so «modifícala» could not reach anything at all."""
    res = _r("update_task", "Pintar el techo")
    assert res.ok and res.payload == {"task": "t11"}, res.needs


# ── 3 · the number is the PRINTED one, and a collision is a question ──────────────────────────────────

@pytest.mark.parametrize("ref,expect", [
    ("la tarea 3 de la lista Obra", None),          # no #3 anywhere → no_match, not a guess
    ("la 2 de la compra", "t01"),
    ("el item 2 de casa", "t11"),
    ("la tarea número dos de casa", "t11"),         # the WORD, and `_ORDINALS` is 0-based: «dos» is #2
    ("la primera de la compra", "t00"),
])
def test_a_number_inside_the_list_he_named(two_lists, ref, expect):
    res = _r("update_task", ref)
    assert (res.payload or {}).get("task") == expect, (ref, res.needs, res.payload)


def test_a_bare_number_that_means_two_rows_ASKS(two_lists):
    """The one that used to touch the wrong task in silence: «la 2» is row 2 of BOTH lists, and a flat
    count would have picked «Leche» with nobody asked."""
    res = _r("update_task", "la 2")
    assert not res.ok and res.needs == "ambiguous"
    assert set(res.candidates) == {"Leche", "Pintar el techo"}, res.candidates


def test_a_bare_number_that_means_ONE_row_resolves(monkeypatch):
    rows = [{"id": f"t{i}", "label": t, "field": "task", "no": i + 1, "group": "Obra"}
            for i, t in enumerate(("Cerrar acuerdo", "Transfer R4", "Abrir cuenta"))]
    monkeypatch.setattr(refs, "_ref_index", lambda w: rows)
    assert _r("update_task", "la tarea número tres").payload == {"task": "t2"}
    assert _r("update_task", "3").payload == {"task": "t2"}


def test_a_number_that_is_part_of_a_TITLE_still_goes_to_the_matcher(monkeypatch):
    """`_POS_FILLER`'s own distinction, and it has to survive the new lookup: «el episodio 12» is identity,
    not position. Leftover tokens that name no list are CONTENT."""
    rows = [{"id": "a", "label": "Sinfonía número 9", "field": "task", "no": 1, "group": "Música"},
            {"id": "b", "label": "Llamar a Ana", "field": "task", "no": 2, "group": "Música"}]
    monkeypatch.setattr(refs, "_ref_index", lambda w: rows)
    assert _r("update_task", "la sinfonía número 9").payload == {"task": "a"}


def test_the_list_itself_is_addressable_by_its_number(two_lists):
    """«ábreme la lista número 3» — the other half of his sentence, and the lists were not published."""
    assert _r("clear_list", "la lista 2").payload == {"list": "tl_1"}
    assert _r("rename_list", "la compra").payload == {"list": "tl_0"}


def test_a_widget_that_does_not_number_its_rows_is_untouched(monkeypatch):
    """Everything without `no` keeps the flat reading — this is an addition to the contract, not a change
    of it, and `youtube`'s «play the third one» (V2-465) has to mean exactly what it meant."""
    rows = [{"id": f"v{i}", "label": f"Vídeo {i}", "field": "item"} for i in range(4)]
    monkeypatch.setattr(refs, "_ref_index", lambda w: rows)
    assert refs.resolve("youtube", "play_item", "el tercero", {}).payload == {"item": "v2"}
