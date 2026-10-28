"""V2-791 · A re-emitted op is a drag only when the previous one LANDED and the turn did not ask for it again.

The measured shape (one session, a video card open): `youtube:channel_videos` ran once and filled the queue
behind the player face, so nothing on screen changed. He complained three times — «¿lo vas a hacer en el widget de
YouTube que estoy viendo?», «no estás haciendo nada con el widget de YouTube», «quiero que lo hagas directamente» —
the model re-emitted the same op each time, and the anti-drag guard ate every one as context-bleed while the
reply promised it.

The guard keeps its job (the original drag: a write repeated by a turn about something else); what it can no longer
do is eat a REDO. Three structural readings license one, none of them a phrase table:

  · the card reported that the previous op did not happen (`widgets/late_report.falsified_since`);
  · his turn names that card as its target (`named_target.names_it`; a card named to be left alone does not count);
  · the redo verdict reads the turn as a correction of the op on that card (when a verdict exists).
"""
from __future__ import annotations

import time

import pytest

from nucleo.flash import data_ops, redo_decision
from widgets import late_report

_PAYLOAD = {"channel": "José Luis Cárpatos"}


def _last(ts=None, wid="youtube", action="channel_videos", payload=None):
    return (wid, action, dict(payload if payload is not None else _PAYLOAD), time.time() - 5 if ts is None else ts)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(late_report, "_falsified", {})
    monkeypatch.setattr(late_report, "_last_agent_order", {})


def _bleed(said, last=None, wid="youtube", action="channel_videos", payload=None, brief=None):
    return data_ops.is_context_bleed(last or _last(), wid, action, dict(payload if payload is not None else _PAYLOAD),
                                     said, brief=brief)


def test_the_original_drag_is_still_eaten():
    """A turn about something else, with the previous write re-emitted beside it: still a drag."""
    assert _bleed("pon la música de fondo más baja") is True
    assert _bleed("and what's the weather tomorrow?", wid="agenda", action="add_meeting",
                  payload={"title": "Dentist"}, last=_last(wid="agenda", action="add_meeting",
                                                            payload={"title": "Dentist"})) is True


def test_a_turn_that_names_the_card_asks_for_the_op_again():
    assert _bleed("¿Vas a hacerlo en el widget de YouTube que estoy viendo?") is False


def test_the_same_complaint_in_english_runs_too():
    assert _bleed("You're not doing anything on the YouTube card, just do it") is False


def test_a_card_named_only_to_be_left_alone_licenses_nothing():
    """«el YouTube déjalo» names the card to EXCLUDE it: never a request for its op."""
    assert _bleed("baja la música, el YouTube déjalo como está") is True


def test_an_op_the_card_falsified_left_no_effect_and_runs_again():
    """The player reported after the agent's order that it did not happen (e.g. sound kept silent by the
    browser): the re-emit is a retry of something that never landed, whatever words the turn used."""
    last = _last(wid="youtube", action="unmute", payload={})
    late_report.note_agent_order("youtube")
    late_report.deliver("youtube", {"tell": "el navegador no deja activar el sonido"})   # no loop: not spoken here
    assert late_report.falsified_since("youtube", last[3]), "the card's late report must stamp the falsification"
    assert data_ops.is_context_bleed(last, "youtube", "unmute", {}, "quiero que lo hagas directamente") is False


def test_a_late_report_with_no_agent_order_falsifies_nothing():
    """His own click on a dead control is in front of him: nobody promised it, nothing to retry."""
    late_report.deliver("youtube", {"tell": "el navegador no deja activar el sonido"})
    assert not late_report.falsified_since("youtube", 0)


def test_a_falsification_BEFORE_the_op_does_not_license_its_re_emit():
    late_report._falsified["youtube"] = time.time() - 60
    assert _bleed("quiero que lo hagas directamente", last=_last(ts=time.time() - 5)) is True


def test_the_redo_verdict_licenses_it_when_there_is_one(monkeypatch):
    monkeypatch.setattr(redo_decision, "corrects", lambda brief, widget="": widget == "youtube")
    assert _bleed("quiero que lo hagas directamente", brief={"any": "brief"}) is False


def test_without_a_verdict_and_without_evidence_the_guard_stands(monkeypatch):
    monkeypatch.setattr(redo_decision, "corrects", lambda brief, widget="": False)
    assert _bleed("quiero que lo hagas directamente", brief={"any": "brief"}) is True
    assert _bleed("quiero que lo hagas directamente", brief=None) is True


def test_the_call_site_hands_the_turn_brief_to_the_guard():
    """The verdict hatch is dead code unless the turn's own brief reaches the predicate."""
    import inspect

    from nucleo.acts import card
    from nucleo.flash import tool_executor_widget_calls as _tw
    src = inspect.getsource(card._context_bleed)
    i = src.index("is_context_bleed(")
    assert 'brief=(r or {}).get("brief")' in src[i:i + 300]
    assert '_req = {"brief": _brief, "text": text}' in inspect.getsource(_tw._apply_widget_data), \
        "the gate hands the turn's brief to the card door"
