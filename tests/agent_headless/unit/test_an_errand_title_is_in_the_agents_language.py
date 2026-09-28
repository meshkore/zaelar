"""The errand's title is written in the language the personal agent was set up in (demo pass 30, 2026-09-28).

An English brief — «Plan a 5-day warm-weather trip for two people…» — came back titled «Viaje 5 días Los Ángeles
para dos, dic 2026» on an English agent. The naming prompt was written in Spanish and said «in the language of
the request»; the model followed the language of the instruction. Now the instruction is in English and names
the agent's language explicitly."""
from nucleo import errand_title as ET


def _system(monkeypatch, code):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    return ET._messages("Plan a 5-day warm-weather trip for two people from LAX")[0]["content"]


def test_an_english_agent_asks_for_an_english_title(monkeypatch):
    text = _system(monkeypatch, "en")
    assert "Write it in English" in text, text
    assert "Nombras" not in text


def test_a_spanish_agent_asks_for_a_spanish_title(monkeypatch):
    assert "Spanish" in _system(monkeypatch, "es")
