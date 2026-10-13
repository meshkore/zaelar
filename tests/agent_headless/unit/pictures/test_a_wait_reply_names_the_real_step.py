"""A wait reply while ONE errand runs names its real current step, in his language, once (2.504).

show-real-photo-of-a-new-car__us (sandbox 20261011-115914-en): «let me know» ×4 answered «Still nothing back yet»,
«Will do», «Sounds good» — with «entrando en media.ferrari.com…» and the worker's own English note in that turn's
live state. The step comes from the errand (its note when it is in his language, the engine's phase translated
from our own vocabulary, the plan step), never from his words, and is said once.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from nucleo.flash import step_line

from ._brief import brief

TELL = brief(wants_words="tell")


@pytest.fixture
def errand(monkeypatch):
    step_line.forget()
    live = {"id": "2", "uid": "u-2", "goal": "Get real, verified photos of the NEW Ferrari Amalfi",
            "title": "Ferrari Amalfi official photos", "phase": "entrando en media.ferrari.com", "note": "",
            "plan": ["Check the agent network", "Open Ferrari's official site"], "done": 1, "waiting_on": ""}
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [live])
    monkeypatch.setattr("i18n.langs.current_code", lambda: "en")
    yield live
    step_line.forget()


def test_the_wait_says_where_it_is(errand):
    line = step_line.owed("Sounds good — I'll let you know the moment they land.", TELL)
    assert "Ferrari Amalfi official photos" in line and "going into media.ferrari.com" in line, line
    assert "entrando" not in line, "never our Spanish phase in an English ear"


def test_a_step_is_said_once_then_the_next_one(errand):
    first = step_line.owed("Will do.", TELL)
    second = step_line.owed("Will do.", TELL)
    assert first != second and "Open Ferrari's official site" in second
    assert step_line.owed("Will do.", TELL) == "", "nothing new to say is not a broken record"


def test_the_workers_own_note_comes_first(errand):
    errand["note"] = "Ferrari product page is JS-rendered — probing the browser route"
    assert "probing the browser route" in step_line.owed("Will do.", TELL)


def test_a_reply_that_already_names_it_gets_nothing(errand):
    assert step_line.owed("It's on media.ferrari.com now.", TELL) == "", "the host it is on is the step"


def test_only_when_he_wants_to_be_told_and_one_errand_runs(errand, monkeypatch):
    assert step_line.owed("Will do.", brief(wants_words="act")) == ""
    assert step_line.owed("Will do.", None) == ""
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [errand, {**errand, "id": "3", "uid": "u-3"}])
    assert step_line.owed("Will do.", TELL) == "", "several errands are the status line's job"


def test_an_idle_phase_is_no_step(errand):
    errand.update(phase="arrancando", plan=[])
    assert step_line.owed("Will do.", TELL) == ""


def test_a_spanish_session_hears_the_phase_as_it_is(errand, monkeypatch):
    monkeypatch.setattr("i18n.langs.current_code", lambda: "es")
    errand.update(plan=[])
    assert "entrando en media.ferrari.com" in step_line.owed("Vale, te aviso.", TELL)


def test_an_errand_without_a_name_never_leaves_an_empty_slot(errand, monkeypatch):
    """docs-single-recipe-not-a-list ES (2026-10-14) heard «Ahora mismo, : buscando…» — a nameless errand."""
    from nucleo.turn import named_errand
    monkeypatch.setattr(named_errand, "spoken_name", lambda _e: "")
    line = step_line.owed("Will do.", TELL)
    assert line.startswith("Right now: ") and ", :" not in line, line


def test_our_plumbing_and_bare_phases_are_no_step(errand, monkeypatch):
    monkeypatch.setattr("i18n.langs.current_code", lambda: "es")
    errand.update(note="Contrato de la hoja leído y receta auténtica confirmada", phase="buscando…",
                  plan=["usando una herramienta de zaelar."], done=0)
    assert step_line.owed("Te aviso.", TELL) == ""
