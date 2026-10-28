"""A persona's goodbye gets ONE second look before it ends the round (play-music-and-build-playlist__us, 2026-10-14).

«Put on some calm music for working.» → «I'll put something calm on for you.» → a farewell, and the round ended on
turn 1 of 8 with the playlist the brief tells the persona to ask for never requested; the judge scored the missing
list against the product (2/5) while every round in which the persona asked built it (5/5). And the goodbye was
invisible: `run.py` breaks before noting a closing line.

Disarm: return `line` unconditionally from `farewell.second_look` (or drop its call from `Driver.reply`) and the
first test goes red; drop the once-per-round guard and the third goes red.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import driver as D, farewell as F, llm, scenarios as SC


def _driver(locale="us"):
    return D.Driver(SC.UseCaseScenario(id="x__us", locale=locale, tier=1, persona_brief="music, then a playlist",
                                       opening_line="Put on some calm music for working.", success_checks="s"))


def _llm(monkeypatch, lines):
    seen = []

    def fake(msgs, **kw):
        seen.append(msgs)
        return lines.pop(0)
    monkeypatch.setattr(llm, "call", fake)
    return seen


def test_a_goodbye_with_the_request_half_asked_becomes_the_missing_ask(monkeypatch):
    d = _driver()
    d.opening(); d.hears("I'll put something calm on for you.")
    seen = _llm(monkeypatch, ["Perfect, thanks!", "nice — can you save it in a playlist called Work?"])
    out = d.reply()
    assert out == "nice — can you save it in a playlist called Work?" and d.done is False
    assert seen[1][-1]["role"] == "system" and "What you want" in seen[1][-1]["content"]
    assert seen[1][-2] == {"role": "assistant", "content": "Perfect, thanks!"}
    assert d.history[-1]["content"] == out, "zaelar never saw the goodbye: only the new line is in the history"
    assert d.farewell == {"turn": 2, "first": "Perfect, thanks!", "second": out}


def test_a_goodbye_confirmed_on_the_second_look_ends_the_round(monkeypatch):
    d = _driver(locale="es")
    d.opening(); d.hears("Ya está, guardada en tu lista Curro.")
    seen = _llm(monkeypatch, ["Vale, gracias.", "Perfecto, gracias."])
    assert d.reply() == "Perfecto, gracias." and d.done is True
    assert "Lo que quieres conseguir" in seen[1][-1]["content"]


def test_only_the_first_goodbye_is_looked_at_twice(monkeypatch):
    d = _driver()
    d.opening(); d.hears("Now playing X.")
    _llm(monkeypatch, ["Thanks!", "save it in Work please", "Thanks!"])
    d.reply(); d.hears("Done, saved to Work.")
    assert d.reply() == "Thanks!" and d.done is True


def test_the_judge_is_told_the_persona_left():
    from tests.use_cases.e2e.agent import judge as J
    left = {"turn": 2, "first": "Perfect, thanks!", "second": "Perfect, thanks!"}
    assert "SE DESPIDIÓ en su turno 2" in J.mechanism_facts({"farewell": left})
    stayed = {"turn": 2, "first": "Thanks!", "second": "can you save it in Work?"}
    assert "NO le llegó a zaelar" in F.judge_line(stayed)
    assert F.judge_line(None) == "" and "DESPIDIÓ" not in J.mechanism_facts({})
