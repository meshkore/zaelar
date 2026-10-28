"""A card is named by what it shows, never by its id (V2-812 T-06).

Measured in a moving car: two restored results sheets with no title were open, he said «cierra el resto de
aplicaciones», and the agent asked out loud «Tienes 2 abiertas: ¿cuál cierro, «4609d2-1» o «187f3c-1»?» — the
instance suffixes, because a card that could not name itself fell through to its id.

The class: a spoken «which card?» names an instance by its content (title, what it was looking for, its first row),
else by its kind, and two that still collide by their place among the open cards. And it is STRUCTURAL: the last
door before the question is built (`instances._no_ids`) replaces any label that carries an open card's id, whatever a
widget's `card_face` returned.
"""
from __future__ import annotations

import tempfile

import pytest

from widgets import instances, store

CAR = ["results::4609d2-1", "results::187f3c-1"]


@pytest.fixture(autouse=True)
def _aislado(monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tempfile.mkdtemp())
    store._last_hash.clear()
    yield
    store._last_hash.clear()


@pytest.fixture
def lang(monkeypatch, request):
    from i18n import langs
    code = getattr(request, "param", "es")
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec(code))
    return langs.spec(code)


def _sheet(inst, title="", items=(), goal=""):
    from widgets.results import data as sheet
    body = {"title": title, "items": list(items)}
    if goal:
        body["criteria"] = {"goal": goal}
    store.save(sheet.sheet_key(inst), body)


def _no_id_in(ask: str, ids=CAR):
    for wid in ids:
        assert wid not in ask and wid.split("::", 1)[-1] not in ask, f"an id reached a spoken line: {ask}"


@pytest.mark.parametrize("lang", ["es", "en"], indirect=True)
def test_the_car_session_sheets_are_named_by_their_first_rows(lang):
    _sheet("4609d2-1", "", [{"title": "Fontanería Pérez"}])
    _sheet("187f3c-1", "", [{"title": "Barbería Centro"}])
    ask = instances.resolve_close("results", CAR, "cierra el resto")["ask"]
    assert ask and "Fontanería Pérez" in ask and "Barbería Centro" in ask
    assert ask.startswith(lang.instances_which_close.split("{")[0])
    _no_id_in(ask)


@pytest.mark.parametrize("lang", ["es", "en"], indirect=True)
def test_a_sheet_is_named_by_what_it_was_looking_for(lang):
    _sheet("4609d2-1", "", [{"title": "x"}], goal="Plumbers in central Madrid")
    _sheet("187f3c-1", "", [{"title": "y"}], goal="Second-hand motorbikes")
    ask = instances.resolve_close("results", CAR, "close the results")["ask"]
    assert "Plumbers in central Madrid" in ask and "Second-hand motorbikes" in ask
    _no_id_in(ask)


@pytest.mark.parametrize("lang,nth", [("es", "n.º"), ("en", "no.")], indirect=["lang"])
def test_two_cards_that_say_nothing_are_told_apart_by_their_place(lang, nth):
    """Both blank (or both the same), so content cannot tell them apart: their place does — never their id."""
    _sheet("4609d2-1")
    _sheet("187f3c-1")
    ask = instances.resolve_close("results", CAR, "cierra los resultados")["ask"]
    assert ask and f"{nth} 1" in ask and f"{nth} 2" in ask, ask
    _no_id_in(ask)


def test_a_piece_that_cannot_describe_its_cards_is_named_by_its_kind():
    ids = ["mensajeria::ab12cd-1", "mensajeria::ef34gh-2"]
    ask = instances.resolve_close("mensajeria", ids, "cierra los mensajes")["ask"]
    assert ask and instances.kind_name("mensajeria") in ask
    _no_id_in(ask, ids)


def test_the_door_scrubs_an_id_whatever_the_widget_returned(monkeypatch):
    """Structural: a widget's own face that leaks its id («Sheet 4609d2-1») is replaced at the last door."""
    monkeypatch.setattr(instances, "card_face", lambda wid: {"label": f"Sheet {wid.split('::')[-1]}"})
    ask = instances.resolve_close("results", CAR, "cierra")["ask"]
    assert ask
    _no_id_in(ask)


def test_disarmed_the_door_lets_the_id_through(monkeypatch):
    """RED proof: without `_no_ids` the leaking face reaches the spoken question — the test reads the door."""
    monkeypatch.setattr(instances, "card_face", lambda wid: {"label": f"Sheet {wid.split('::')[-1]}"})
    monkeypatch.setattr(instances, "_no_ids", lambda etiquetas, ids: list(etiquetas))
    ask = instances.resolve_close("results", CAR, "cierra")["ask"]
    assert "4609d2-1" in ask, "the disarm did not land"
    monkeypatch.undo()
    monkeypatch.setattr(instances, "card_face", lambda wid: {"label": f"Sheet {wid.split('::')[-1]}"})
    _no_id_in(instances.resolve_close("results", CAR, "cierra")["ask"])     # green again


def test_disarmed_the_id_fallback_comes_back(monkeypatch):
    """RED proof for the label: the pre-V2-812 fallback (the instance suffix) is exactly what was spoken in the car."""
    monkeypatch.setattr(instances, "kind_name", lambda wid: wid.split("::", 1)[-1])
    monkeypatch.setattr(instances, "_no_ids", lambda etiquetas, ids: list(etiquetas))
    ids = ["mensajeria::ab12cd-1", "mensajeria::ef34gh-2"]
    assert "ab12cd-1" in instances.resolve_close("mensajeria", ids, "cierra")["ask"], "the disarm did not land"


def test_the_show_question_and_its_choice_follow_the_same_rule():
    _sheet("4609d2-1")
    _sheet("187f3c-1")
    first = instances.resolve_show("results", CAR, "enséñame los resultados")
    _no_id_in(first["ask"])
    again = instances.resolve_show("results", CAR, "el otro", last_spoken=first["ask"])
    _no_id_in(str(again.get("chose") or ""))


def test_the_tool_path_question_has_no_id():
    from nucleo.flash import close_which
    _sheet("4609d2-1", "", [{"title": "a"}])
    _sheet("187f3c-1", "", [{"title": "b"}])
    card, question = close_which.resolve("results", "cierra el resto de aplicaciones", open_ids=CAR)
    assert question
    _no_id_in(question)
