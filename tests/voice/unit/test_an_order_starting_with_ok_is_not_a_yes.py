"""Demo pass 45 (2026-09-29), C2→C3: the model asked «I'll write to Ethan on Telegram: … Shall I send it?» for a message
nobody had asked for; the next turn — «ok book it, call it catch up with ethan», an order about the CALENDAR —
matched `ok` in the yes/no table and the Telegram went out. A bare answer still resolves at once; a reply that
carries its own words is asked, with the pending question named, whether it answers it."""
import pytest

from widgets import confirm

_Q = "I'll write to Ethan on Telegram: «you free for a 45-minute call tomorrow?». Shall I send it?"


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
    assert confirm.answers_pending("ok book it, call it catch up with ethan") is None
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
    assert confirm.answers_pending("ok book it, call it catch up with ethan") == "yes"


def test_both_voice_sites_and_the_gate_use_it():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    assert (root / "voice/engine/llm/providers/nucleo.py").read_text("utf-8").count("_wconfirm.answers_pending(text)") == 2
    assert "_c.answers_pending(text)" in (root / "nucleo/turn/confirm_gates.py").read_text("utf-8")
