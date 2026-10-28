"""A verdict cannot veto a clear close; an answer to our own question carries its licence (V2-812 T-05).

Measured in a moving car (phone PWA):

  · «Vale, pues aquí no suena nada, cierra el resto de aplicaciones.» — the brief read `canvas=neither` (0.87) beside
    `request_type=order` (0.60), and `canvas_license.close_license` let the `neither` veto the clear close: the
    model's close was refused twice as context-bleed.
  · The engine then asked «¿cuál cierro, …?», he answered «Las dos.», and the close was refused AGAIN — two words, no
    close verb — while the same turn resumed the music, the one thing the answer did not ask for.

The class: `neither` vetoes a close the grammar saw only when the brief READS A NEGATION — the turn surely read as
something other than an order or an answer (the fce3eff3 denials read as complaints). His answer to our pending
«which one should I close?» (the brief reads `answer`; `widgets.instances` remembers the question) licenses the close
and nothing that starts a player (`runtime.produce`). Verdict → declared data → one door; no word table.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import canvas_license, close_answer, show_target, turn_brief
from widgets import instances

CAR = ["results::4609d2-1", "results::187f3c-1"]


@pytest.fixture(autouse=True)
def _clean():
    instances.clear_close_ask()
    yield
    instances.clear_close_ask()


def _brief(canvas="neither", kind="order", cconf=0.87, kconf=0.6):
    ev = threading.Event()
    ev.set()
    result = {}
    if canvas:
        result[turn_brief.CANVAS_KEY] = {"choice": canvas, "confidence": cconf, "probs": {}}
    if kind:
        result[turn_brief.REQUEST_KEY] = {"choice": kind, "confidence": kconf, "probs": {}}
    return {"event": ev, "turn_id": "t", "open_ids": (), "result": result}


ORDERS = ["Vale, pues aquí no suena nada, cierra el resto de aplicaciones.",
          "Okay, nothing is playing here, close the rest of the apps."]


@pytest.mark.parametrize("said", ORDERS)
def test_a_neither_verdict_does_not_veto_a_clear_close_order(said):
    assert canvas_license.close_license(said, brief=_brief())
    assert show_target.close_has_order(said, None, brief=_brief())[0] is True


@pytest.mark.parametrize("said", ["Yo no te he dicho en ningún momento que cerraras el widget de vídeo.",
                                  "You did close the document of Bitcoin without me telling you."])
def test_a_verdict_that_reads_a_complaint_still_vetoes(said):
    """The half that must not move: the denials V2-752 exists for read as complaints, and stay vetoed."""
    assert not canvas_license.close_license(said, brief=_brief(kind="complaint", kconf=0.9))


def test_disarmed_the_bare_neither_vetoes_the_car_order_again(monkeypatch):
    """RED proof: the pre-V2-812 rule (a sure `neither` alone vetoes) refuses the car-session order."""
    monkeypatch.setattr(canvas_license, "verdict_denies_close",
                        lambda brief: turn_brief.read(brief, turn_brief.CANVAS_KEY, "")[0] == "neither")
    assert not canvas_license.close_license(ORDERS[0], brief=_brief()), "the disarm did not land"
    monkeypatch.undo()
    assert canvas_license.close_license(ORDERS[0], brief=_brief())              # green again


@pytest.mark.parametrize("said", ["Las dos.", "Both."])
def test_an_answer_to_our_close_question_carries_its_licence(said):
    instances.note_close_ask(CAR)
    answer = _brief(canvas="neither", cconf=0.61, kind="answer", kconf=0.9)
    assert canvas_license.close_license(said, brief=answer)
    assert show_target.close_has_order(said, None, brief=answer) == (True, "answer")


@pytest.mark.parametrize("said", ["Las dos.", "Both."])
def test_without_our_question_the_same_words_license_nothing(said):
    answer = _brief(canvas="neither", cconf=0.61, kind="answer", kconf=0.9)
    assert not canvas_license.close_license(said, brief=answer)
    assert show_target.close_has_order(said, None, brief=answer)[0] is False


def test_only_a_sure_answer_and_never_a_negated_one_borrows_the_licence():
    instances.note_close_ask(CAR)
    assert not canvas_license.close_license("Las dos.", brief=_brief(kind="answer", kconf=0.3))
    assert not canvas_license.close_license("Las dos.", brief=_brief(kind="comment", kconf=0.9))
    assert not canvas_license.close_license("Las dos.", brief=None)
    assert not canvas_license.close_license("No cierres ninguna.", brief=_brief(kind="answer", kconf=0.9))


def test_a_stale_question_is_not_answered(monkeypatch):
    instances.note_close_ask(CAR)
    import time as _t
    later = _t.time() + instances.CLOSE_ASK_S + 1
    monkeypatch.setattr(_t, "time", lambda: later)
    assert not canvas_license.close_license("Las dos.", brief=_brief(kind="answer", kconf=0.9))


def test_the_engine_asking_which_one_records_the_question():
    """The record is written by the one place the question is built — not by a caller remembering to."""
    out = instances.resolve_close("results", CAR, "cierra los resultados")
    assert out["ask"]
    assert instances.pending_close_ask() == CAR


def _collect():
    events: list[tuple] = []

    def emit(kind, action, text=None, role=None, extra=None):
        events.append((kind, action, dict(extra or {})))
    return events, emit


@pytest.mark.parametrize("said", ["Las dos.", "Both of them."])
def test_the_backstop_closes_what_the_answer_picks(said):
    instances.note_close_ask(CAR)
    events, emit = _collect()
    acted: dict = {}
    closed = close_answer.backstop(said, _brief(kind="answer", kconf=0.9), emit, acted,
                                   open_ids=CAR + ["musica"])
    assert closed == CAR and acted.get("closed")
    assert [e[2]["id"] for e in events if e[:2] == ("widget", "close")] == CAR
    assert instances.pending_close_ask() == [], "an answered question is no longer pending"


def _play_music(brief):
    from nucleo.flash import tool_executor_calls as TEC
    events, emit = _collect()
    music_req = {"v": None}
    TEC._t_play_music(args={"action": "resume"}, music_req=music_req, _brief=brief, emit=emit, text="Las dos.")
    return music_req["v"]


def test_an_answer_to_our_close_question_resumes_no_music():
    instances.note_close_ask(CAR)
    assert _play_music(_brief(kind="answer", kconf=0.9)) is None


def test_disarmed_the_answer_resumes_the_music_again(monkeypatch):
    """RED proof: without the door the car session's «Las dos.» → Spotify resume is back."""
    instances.note_close_ask(CAR)
    monkeypatch.setattr(close_answer, "refuses", lambda *a, **k: False)
    assert _play_music(_brief(kind="answer", kconf=0.9)) == {"query": "", "action": "resume"}, "disarm did not land"
    monkeypatch.undo()
    assert _play_music(_brief(kind="answer", kconf=0.9)) is None                   # green again


def test_a_pause_is_not_production_and_an_order_turn_still_plays():
    """Declared data decides: `pause` is not in `runtime.produce`; a real order (no pending question) plays."""
    instances.note_close_ask(CAR)
    assert not close_answer.refuses(_brief(kind="answer", kconf=0.9), "musica", "pause")
    instances.clear_close_ask()
    assert _play_music(_brief(kind="order", kconf=0.9)) == {"query": "", "action": "resume"}
