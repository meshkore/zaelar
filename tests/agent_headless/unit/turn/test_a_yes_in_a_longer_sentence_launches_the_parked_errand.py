"""A yes inside a longer sentence launches the parked errand, and the reply says what the gate did (node 2.456).

three-tasks-at-once (2026-10-11 02:58), the game parked on «¿La hago?» / «Shall I?»:
  · ES «Sí, justo eso, y ponle que el muñeco salte más alto, que si no no hay quien pase las plataformas. ¿El monitor
    cómo va?» — `classify_reply` reads the LAST word, «no» (from «si no»), and the game stayed parked;
  · EN «yeah go ahead with the game, and add coins to it too. btw for the monitor it has to be at least 27 inches» —
    the judge, seeing the monitor, answered OTHER; parked again, and the monitor's refinement was dropped with it;
  · EN «ok. just ping me when it's up» resolved the yes — and the reply asked «shall I start it? Say the word»;
  · ES «Vale, perfecto. Del monitor, que no pase de 150» → the model re-escalated the game and said «va en marcha»
    over an errand still parked.

Mechanisms: the answer a reply OPENS with answers the parked errand it names (`confirm.opening_answer`); the turn's
`send_to_worker` for OTHER errands still goes out beside a yes; a reply that asks again after a yes becomes the start
line; an escalation that lands on a parked errand carries that errand's question.
"""
from __future__ import annotations

import threading
import time
import types

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo.flash import probe_after
from nucleo.turn import confirm_gates as gates
from nucleo.turn import errands_of_a_turn as E
from widgets import confirm as wconfirm

GAME = "Build a playable platform game widget, Super Mario style: a side-scrolling platformer with a character"
MONITOR = E.listing_errand({"query": "cheap used monitor"})
Q = "If I've got this right, you're asking me to BUILD you a new card. Shall I?"


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {k: {"choice": c, "confidence": 0.99, "probs": {c: 0.99}}
                                    for k, c in verdicts.items()}, "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.fixture
def parked(monkeypatch):
    out = []
    monkeypatch.setattr("nucleo.flash.escalate.escalate_to_slowbrain", lambda req, context=None: out.append(req) or 1)
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [{"id": "3", "request": MONITOR, "phase": "",
                                                                  "waiting_on": ""}])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="", title=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {"2": {"request": GAME, "kind": "code", "trusted": True,
                                                       "context": {}, "sheet": "", "ts": time.time(),
                                                       "code_change": "create", "question": Q}})
    monkeypatch.setattr(wconfirm, "_judge", lambda q, r, timeout=4.0: "other")     # what the live judge said
    return out


JUEGO = "Crear un widget nuevo para el canvas: un juego de plataformas tipo Super Mario, jugable, para probar"


@pytest.mark.parametrize("game, said", [
    (GAME, "yeah go ahead with the game, and add coins to it too. btw for the monitor it has to be at least 27 inches"),
    (JUEGO, "Sí, justo eso, y ponle que el muñeco salte más alto, que si no no hay quien pase las plataformas. ¿El "
            "monitor cómo va?"),
])
def test_the_yes_it_opens_with_launches_the_game(parked, game, said):
    dc._PENDING_CONFIRM["2"]["request"] = game
    ans = gates.resolve_all(said, brief=_brief(request_type="order"))
    assert ans and ans.yes, said
    assert len(parked) == 1 and parked[0].startswith(game)


def test_an_if_is_not_a_yes():
    assert wconfirm.opening_answer("Si no te importa, espera un poco") is None
    assert wconfirm.opening_answer("si, dale") == "yes" and wconfirm.opening_answer("Sí, venga") == "yes"
    assert wconfirm.opening_answer("No, el juego déjalo") == "no"
    assert wconfirm.opening_answer("Intenta reservarlo, mejor") is None


def test_the_monitor_refinement_beside_the_yes_still_goes_out():
    sent = []
    calls = [{"name": "send_to_worker", "args": {"which": "the platform game", "message": "add coins to the game"}},
             {"name": "send_to_worker", "args": {"which": "the monitor hunt", "message": "at least 27 inches, used"}}]
    E.send_beside_an_answer(calls, GAME, lambda c, t: sent.extend(c))
    assert [c["args"]["which"] for c in sent] == ["the monitor hunt"]


def test_the_reply_says_what_the_gate_did(monkeypatch):
    sess = types.SimpleNamespace(window=[])
    out = probe_after._true_to_the_gate("Building it takes a few minutes — shall I start it? Say the word.",
                                        "confirm_task", {}, sess)
    assert "shall I" not in out and out, out
    claim = "Hecho, el tope de 150. Y el juego te lo construyo, va en marcha."
    out = probe_after._true_to_the_gate(claim, "escalate", {"still_parked": "¿La hago?"}, sess)
    assert out == claim + " ¿La hago?"
    assert probe_after._true_to_the_gate("¿Seguro?", "escalate", {"still_parked": "¿La hago?"}, sess) == "¿Seguro?"


def test_an_escalation_of_the_parked_errand_finds_its_question(parked):
    again = "Build a playable platform game widget, Super Mario style, side-scrolling platformer with a character"
    assert E.parked_question_for([again]) == Q
    assert E.parked_question_for(["Write a report on electric cars"]) == ""
