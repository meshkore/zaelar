"""Demo pass 45 (2026-09-29), C2→C3: the model asked «I'll write to Rowan on Telegram: … Shall I send it?» for a message
nobody had asked for; the next turn — «ok book it, call it catch up with rowan», an order about the CALENDAR —
matched `ok` in the yes/no table and the Telegram went out. A bare answer still resolves at once; a reply that
carries its own words is asked, with the pending question named, whether it answers it."""
from tests import voice_turn_source as _vts
import pytest

from widgets import confirm

_Q = "I'll write to Rowan on Telegram: «you free for a 45-minute call tomorrow?». Shall I send it?"


@pytest.fixture(autouse=True)
def pending():
    confirm.reset()
    confirm.request("data", "mensajeria", _Q, op={"action": "send_to", "payload": {}}, notify_ui=False)
    yield
    confirm.reset()


def _reader(monkeypatch, choice):
    asked = []

    def _judge(question, reply, timeout=4.0):
        asked.append(question)
        return choice
    monkeypatch.setattr(confirm, "_judge", _judge)
    return asked


def test_a_different_order_that_starts_with_ok_confirms_nothing(monkeypatch):
    asked = _reader(monkeypatch, "other")
    assert confirm.answers_pending("ok book it, call it catch up with rowan") is None
    assert "Shall I send it?" in asked[0], "the reader was not told which question is pending"


def test_a_bare_answer_is_not_asked_about(monkeypatch):
    asked = _reader(monkeypatch, "other")
    assert confirm.answers_pending("yes") == "yes"
    assert confirm.answers_pending("ok go ahead") == "yes"
    assert confirm.answers_pending("no, cancel it") == "no"
    assert asked == []


def test_a_long_yes_the_reader_confirms_is_a_yes(monkeypatch):
    _reader(monkeypatch, "yes")
    assert confirm.answers_pending("yeah sure, send that to him right now please") == "yes"


def test_without_the_reader_the_word_reading_stands(monkeypatch):
    monkeypatch.setattr(confirm, "_judge", lambda *a, **k: None)
    assert confirm.answers_pending("ok book it, call it catch up with rowan") == "yes"


def test_both_voice_sites_and_the_gate_use_it():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    assert _vts.read(root / "voice/engine/llm/providers/nucleo.py").count("_wconfirm.answers_pending(text)") == 2
    assert "_c.answers_pending(text)" in (root / "nucleo/turn/confirm_gates.py").read_text("utf-8")


def test_a_no_read_from_a_longer_order_cancels_and_the_turn_serves_the_order(monkeypatch):
    """Demo pass 129 (2026-10-14), C3: the same sentence, and the reader said NO — the pending mail was cancelled
    and the turn ENDED on «Alright, I won't touch anything.»: the meeting he asked for was never booked. A bare
    «no» is the whole answer; a «no» read from a longer order cancels and leaves the rest of the turn to run."""
    _reader(monkeypatch, "no")
    text = "ok book it, call it catch up with rowan"
    assert confirm.answers_pending(text) == "no" and not confirm.is_plain_answer(text, "no")
    assert confirm.is_plain_answer("no, cancel it", "no")
    from pathlib import Path
    src = _vts.read(Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py")
    assert "if _resolve_and_end_the_turn(_verdict_early, text):" in src, "the early answer no longer asks"
    from voice.engine.llm.providers import pending_confirm as pc
    monkeypatch.setattr(pc, "_resolve_pending_confirm", lambda ok: True)
    assert pc._resolve_and_end_the_turn("no", text) is False, "a judged «no» ends the turn before its order"
    assert pc._resolve_and_end_the_turn("no", "no, cancel it") is True
    assert pc._resolve_and_end_the_turn("yes", "yes") is True
