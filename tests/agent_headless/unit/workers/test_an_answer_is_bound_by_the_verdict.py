"""V2-851 F1b §3a — which waiting task an utterance answers is a VERDICT of the turn's brief, by `ask_id`.

Died here: the ≤140-char backstop (F0: all 49 non-answers after a question were ≤140 chars — length separates nothing),
`answer_active` (the OLDEST ask got any answer) and the model's `answer_worker` binding by age. The brief carries one
declared question while tasks wait; an `ask_id` ≥ licence binds, `none` ≥ veto binds nothing, anything else is asked
(ASK_WHICH, an `ask` naming the waiting tasks).
"""
from __future__ import annotations

import pytest

from nucleo.cli import worker_api, worker_api_bind as bind
from nucleo.turn import brief, verdicts

A1 = {"task_id": "b0-1", "ask_id": "a-old", "question": "Which Raquel?", "title": "Photos to Raquel", "since": 1}
A2 = {"task_id": "b0-2", "ask_id": "a-new", "question": "Which hotel?", "title": "Hotel in Rome", "since": 2}


def _verdict(monkeypatch, choice, conf):
    monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None:
                        (choice, {"confidence": conf}) if key == bind.KEY and choice is not None else (fb, None))


def test_the_brief_asks_it_only_while_a_task_waits():
    assert bind.KEY in brief.keys()
    assert bind.KEY not in brief.build("hola")
    q = brief.build("Pérez", open_asks=[A1, A2])[bind.KEY]
    assert set(q["criteria"]) == {"a-old", "a-new", bind.NONE}, "the open questions by ask_id, plus none"


def test_a_sure_verdict_binds_its_own_task_not_the_oldest(monkeypatch):
    _verdict(monkeypatch, "a-new", 0.6)
    assert bind.bind({}, asks=[A1, A2]) == (bind.ANSWER, [A2])


def test_a_sure_none_binds_nothing_even_when_the_model_answered(monkeypatch):
    _verdict(monkeypatch, bind.NONE, 0.9)
    assert bind.bind({}, model_answered=True, asks=[A1]) == (bind.NOTHING, [])


@pytest.mark.parametrize("choice,conf", [("a-old", 0.4), (bind.NONE, 0.7)])
def test_a_doubt_is_asked_among_the_waiting_tasks(monkeypatch, choice, conf):
    _verdict(monkeypatch, choice, conf)
    assert bind.bind({}, asks=[A1, A2]) == (bind.ASK_WHICH, [A1, A2])


def test_no_verdict_binds_a_short_answer_to_nothing(monkeypatch):
    """Disarm of the ≤140-char backstop: a short turn with a task waiting and no verdict is NOT its answer."""
    _verdict(monkeypatch, None, 0)
    assert bind.bind(None, asks=[A1]) == (bind.NOTHING, [])
    sent, acted = [], {"v": None}
    monkeypatch.setattr(worker_api, "open_asks", lambda: [A1])
    monkeypatch.setattr(worker_api, "answer_soon", lambda *a: sent.append(a) or True)
    from nucleo.flash import post_stream_settle as pss
    pss.bind_the_answer(None, "sí", model_answer="", worker_acted=acted, escalate_req={"v": None},
                        others_acted=False, spoken_text="", send=lambda *_: None,
                        speech=type("S", (), {"sanitize": staticmethod(lambda t, **_: t)}), emit=lambda *a, **k: None)
    assert sent == [] and acted["v"] is None


def test_without_a_verdict_the_models_routing_binds_only_a_lone_task(monkeypatch):
    _verdict(monkeypatch, None, 0)
    assert bind.bind(None, model_answered=True, asks=[A1]) == (bind.ANSWER, [A1])
    assert bind.bind(None, model_answered=True, asks=[A1, A2]) == (bind.ASK_WHICH, [A1, A2])


def test_the_oldest_first_binders_are_gone():
    """Disarm: nothing answers «the active ask»; `active_ask` survives only as the voice relay's next question."""
    assert not hasattr(worker_api, "answer_active") and not hasattr(worker_api, "answer_active_soon")
    import inspect
    from nucleo.flash import post_stream_settle, tool_executor_calls
    assert "len(text) <= 140" not in inspect.getsource(post_stream_settle)
    assert "answer_soon" not in inspect.getsource(tool_executor_calls._t_answer_worker)


def test_ask_which_names_the_tasks_and_his_words_reach_the_one_he_picks(monkeypatch):
    events = []
    monkeypatch.setattr(worker_api, "emit_ask", lambda **kw: events.append(kw))
    line = bind.ask_which([A1, A2], text="Pérez")
    assert events and events[0]["among"] == ["b0-1", "b0-2"] and events[0]["task_id"] == ""
    assert "Photos to Raquel" in line
    assert bind.answer_text("the photos one") == "Pérez — the photos one"
    assert bind.answer_text("Ruiz") == "Ruiz", "the doubt is spent once resolved"
