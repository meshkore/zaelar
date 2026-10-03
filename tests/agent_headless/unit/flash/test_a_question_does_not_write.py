"""A WRITE the model makes on a QUESTION, while the verdict surely reads «no action on the screen», is not run.

Demo pass 93 (2026-10-03), R2 «When does Anna's vacation start? Show it to me on the calendar.»: screen_action «none»
(0.83), and the model called agenda:add_meeting — a second «Anna vacation» over the one the INIT had made.
"""
from nucleo.flash import tool_executor_widget_calls as TW
from nucleo.flash import turn_brief as tb


def _verdict(monkeypatch, choice, used):
    monkeypatch.setattr(tb, "read", lambda brief, key, fallback="", **k:
                        ((choice if used else fallback), {"choice": choice, "used": used}) if key == tb.TARGET_KEY
                        else (fallback, None))


Q = "When does Anna's vacation start? Show it to me on the calendar."


def test_a_question_with_a_sure_no_action_verdict_does_not_write(monkeypatch):
    _verdict(monkeypatch, "none", True)
    assert TW.a_question_the_verdict_keeps_unwritten("agenda", "add_meeting", Q, {"x": 1})


def test_a_view_still_runs_and_an_order_still_writes(monkeypatch):
    _verdict(monkeypatch, "none", True)
    assert not TW.a_question_the_verdict_keeps_unwritten("agenda", "show_day", Q, {"x": 1}), "a lens is not a write"
    assert not TW.a_question_the_verdict_keeps_unwritten("agenda", "add_meeting", "book the dentist on friday",
                                                         {"x": 1}), "no question mark: an order"


def test_an_unsure_or_acting_verdict_lets_the_model_write(monkeypatch):
    _verdict(monkeypatch, "none", False)
    assert not TW.a_question_the_verdict_keeps_unwritten("agenda", "add_meeting", Q, {"x": 1})
    _verdict(monkeypatch, "agenda:add_meeting", True)
    assert not TW.a_question_the_verdict_keeps_unwritten("agenda", "add_meeting", Q, {"x": 1})
