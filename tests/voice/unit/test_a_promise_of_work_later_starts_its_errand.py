"""V2-794 — a reply that promises work handed over LATER starts that work, or says it was not done.

The class, as measured (text typed into a live session): «Crea una lista de 40 canciones» → «Vale… te monto la lista
de 40 canciones para el cumpleaños… La tendrás en la tarjeta de música en un rato.» The reply's verdict read `act`
at 1.00, the model called nothing, the late catalogue named no card, the escalate question had said handle_inline —
and the promise harness emitted nothing: `owed` still asked the Spanish phrase tables, which do not know «te monto»,
and a promise of LATER work had no door that could keep it. He waited; nothing was ever started.

Now (refactor2710-03): the turn's BRIEF is the evidence, never our words — a sure order owed an act, and a sure
`escalate` with nothing run starts the errand through the turn's escalation (the same portal every escalation
crosses) instead of a «not done», which the mouth says (`nucleo/turn/reply.py`) when only an order was owed. The
variants carry other domains and the other language.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.turn import promise_kept as pk
from nucleo.turn import reply as R

LATER = {
    "es_songs": ("Crea una lista de 40 canciones",
                 "Vale… te monto la lista de 40 canciones para el cumpleaños, con clásicos que gustan a esa edad. "
                 "La tendrás en la tarjeta de música en un rato."),
    "en_films": ("Put together a list of 20 films for a rainy weekend",
                 "Sure — I'll line up twenty films for the weekend and have them ready for you shortly."),
    "es_restaurants": ("Hazme una lista de 30 restaurantes en Madrid",
                       "Perfecto, te preparo los treinta restaurantes y te aviso cuando los tenga."),
}
NOW = {"es": "Te organizo los tres ahora.", "en": "Lining those three up for you."}


def _verdict(monkeypatch, owed: str) -> None:
    """The brief's verdict on what the turn owed: "escalate", "order" or "" (`reply.owes_an_act`)."""
    monkeypatch.setattr(R, "owes_an_act", lambda brief: owed)


def _turn(escalated: list):
    return (None, [], None, lambda req, context=None: escalated.append((req, context)))


def _say(reply, turn, *, outcome=None, acted=False):
    said, events = [], []
    window = [{"role": "assistant", "content": reply}]
    data_done = {"promise": outcome} if outcome is not None else {}
    line = pk.say_after(reply, data_done, acted=acted, send=said.append, speech=SimpleNamespace(sanitize=lambda t, **k: t),
                        window=window, emit=lambda *a, **k: events.append((a, k)), turn=turn)
    return line, said, events, data_done


@pytest.mark.parametrize("case", sorted(LATER))
def test_a_promise_of_later_work_starts_the_errand_and_says_no_undone(monkeypatch, case):
    words, reply = LATER[case]
    _verdict(monkeypatch, "escalate")
    escalated: list = []
    turn = (None, [], words, lambda req, context=None: escalated.append((req, context)))
    line, said, events, data_done = _say(reply, turn)
    assert escalated and escalated[0][0] == words, "his words are the errand, through the turn's escalation"
    assert escalated[0][1]["src"] == "voice"
    assert line == "" and not said, "the promise is being kept: no «I have not done it» over it"
    assert data_done["promise"]["kind"] == pk.STARTED
    assert any(a[1] == "🧭 Flash → Brain Worker (escalada registrada)" for a, _k in events)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_promise_to_act_now_that_ran_nothing_is_said_undone_without_any_table(monkeypatch, lang):
    reply = NOW[lang]
    _verdict(monkeypatch, "order")
    escalated: list = []
    line, said, _e, _d = _say(reply, (None, [], "organízamelos", lambda r, context=None: escalated.append(r)))
    assert not escalated, "an act promised for NOW is not a worker's errand"
    assert line and said and said[-1].strip() == line, "the brief alone says an act was owed: the mouth says it was not done"


def test_the_live_case_replayed(monkeypatch):
    words, reply = LATER["es_songs"]
    _verdict(monkeypatch, "escalate")
    escalated: list = []
    line, *_ = _say(reply, (None, [], words, lambda r, context=None: escalated.append(r)))
    assert escalated == [words] and line == ""


@pytest.mark.parametrize("why,outcome,calls,acted", [
    ("something ran", None, [], True),
    ("a guard ate the model's own call (V2-753: the honest line, never a worker)", None,
     [{"name": "widget_data", "args": {"widget_id": "musica", "action": "play"}}], False),
    ("the pass declared it cannot", {"kind": pk.CANNOT, "say": "No puedo hacerlo desde aquí."}, [], False),
    ("the pass's call was swallowed", {"kind": pk.SWALLOWED}, [], False),
    ("the pass ran the call", {"kind": pk.CALL}, [], False),
])
def test_what_is_not_a_deferred_errand(monkeypatch, why, outcome, calls, acted):
    words, reply = LATER["en_films"]
    _verdict(monkeypatch, "escalate")
    escalated: list = []
    _say(reply, (None, calls, words, lambda r, context=None: escalated.append(r)), outcome=outcome, acted=acted)
    assert not escalated, why


def test_a_turn_the_brief_owes_nothing_starts_nothing_and_says_nothing(monkeypatch):
    reply = "Cuando me digas, te preparo la lista y la tendrás en un rato."
    _verdict(monkeypatch, "")
    escalated: list = []
    line, *_ = _say(reply, (None, [], "una lista", lambda r, context=None: escalated.append(r)))
    assert not escalated and line == ""


def test_without_a_sure_verdict_nothing_is_started(monkeypatch):
    words, reply = LATER["es_restaurants"]
    _verdict(monkeypatch, "order")
    escalated: list = []
    _say(reply, (None, [], words, lambda r, context=None: escalated.append(r)))
    assert not escalated, "a worker costs minutes: only the verdict may start one, never a table"


def test_the_voice_turn_end_hands_the_door_its_turn():
    from pathlib import Path

    from tests import voice_turn_source as _vts
    src = _vts.read(Path(__file__).resolve().parents[2].parent / "voice/engine/llm/providers/turn_after.py")
    j = src.index("_promise_kept.say_after(spoken_text, data_done, send=send")
    call = src[j:j + 900]
    assert "turn=(_brief, getattr(brain, \"_turn_calls\", None), _op_text, _escalate_mod.escalate_to_slowbrain)" \
        in call, call
