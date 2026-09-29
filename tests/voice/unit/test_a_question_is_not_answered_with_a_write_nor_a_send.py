"""full19 C2-C3 (demo pass 2026-09-28): «find me a free 45 minutes tomorrow afternoon to talk with ethan, after my
last meeting» — the verdict read `agenda:find_free` at 0.91; the model BOOKED the meeting and also sent Ethan a
Telegram. Twice, across two turns. Two rules close it:

· a sure verdict naming an action declared `output.answer`, over a model WRITE on the same card, runs the answer:
  a write lands in his calendar and is the costly mistake;
· an act that leaves (`external.send`) that the verdict does not back — it surely names another card — is DROPPED
  and the model is told it did not run. It was ASKED until demo pass 45 (2026-09-29): the pending question was what
  «ok book it» answered one turn later, and two Telegrams went to Ethan he never ordered. Never sent silently,
  never left pending for the next «ok»."""
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[3]
SRC = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")


def test_a_message_to_a_person_is_an_act_that_leaves():
    from nucleo.flash import frontend
    from widgets import effects as fx
    for a in ("send_to", "forward", "reply", "send_draft"):
        assert fx.carries("mensajeria", a, fx.EXTERNAL_SEND), a
        assert frontend.at_least_sensitive("mensajeria", a), a
    assert not frontend.at_least_sensitive("agenda", "add_meeting")


@pytest.fixture
def verdict(monkeypatch):
    from nucleo.flash import direct_action as da
    from nucleo.flash import turn_brief as tb
    state = {"v": ("agenda", "find_free"), "sure": True}
    monkeypatch.setattr(da, "from_brief", lambda brief: state["v"])
    monkeypatch.setattr(da, "_action_sure", lambda brief, floor=0.8: state["sure"])
    return state


def test_a_send_the_verdict_puts_on_another_card_is_asked(verdict):
    from nucleo.flash import direct_action as da
    assert da.verdict_elsewhere({"x": 1}, "mensajeria") is True
    verdict["v"] = ("mensajeria", "send_to")
    assert da.verdict_elsewhere({"x": 1}, "mensajeria") is False, "the verdict backs it"
    verdict["v"], verdict["sure"] = ("agenda", "find_free"), False
    assert da.verdict_elsewhere({"x": 1}, "mensajeria") is False, "an unsure verdict is no verdict"


def test_the_voice_wires_both_rules():
    assert "elif _direct_action.verdict_elsewhere(_brief, wid):" in SRC
    i = SRC.index("acto que sale fuera sin respaldo del veredicto")
    seg = SRC[i:i + 900]
    assert "no se ejecuta" in seg and "_bn_drop.push(" in seg and "mode = _wactions.CONFIRM" not in seg
    j = SRC.index("la pregunta gana a la escritura")
    block = SRC[SRC.rindex("if (_fx_q.carries", 0, j):j]
    assert "_fx_q.OUTPUT_ANSWER" in block and "_fx_q.DATA_WRITE" in block and "instead_of=action_name" in block


def test_when_the_verdict_cannot_complete_alone_the_write_still_does_not_run():
    """Demo pass 51 (2026-09-29), C2: «find me a free 45 minutes tomorrow afternoon…» → the model called add_meeting
    (15:45, over the 15:00 meeting), the verdict read find_free at 0.86, and `complete` could not build find_free on
    its own — so the write ran. Now the write never runs: the verdict's call is asked of the model after the turn,
    and the branch returns either way."""
    j = SRC.index("la pregunta gana a la escritura")
    block = SRC[SRC.rindex("if (_fx_q.carries", 0, j):j + 400]
    assert "and _direct_action._action_sure(_brief)):" in block, "complete() is part of the condition again"
    assert '_repeat_repair["v"] = (_cd["card"], action_name, _dis)' in block
    k = block.index("la pregunta gana a la escritura")
    assert "return" in block[k:k + 400]
