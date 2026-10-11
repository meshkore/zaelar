"""A «yes» answers the parked errand it NAMES, and an errand he keeps talking about does not expire (node 2.438).

three-tasks-at-once (ES, 2026-10-11 02:04). Two things were parked on him: the platform game (the build gate's «¿La
hago?») and, newer, a bogus offer. The task gate always answered the NEWEST, so «Sí, móntalo. Y ese ponle que salte
más alto, que si no se quedan cortos los saltos entre plataformas» — the game's yes, by every word in it — was judged
against the other one and launched nothing. Then «¿y al juego le puedes poner monedas?» passed by a parked game that
nobody refreshed, it expired at five minutes, and the agent told him «se quedó a medias porque nunca llegaste a
confirmarlo».

The gate reads which parked errand his words name (`named_errand`, the yardstick every door shares): a yes that names
it launches THAT one with what he added; a sentence that names it without answering folds into it and restarts its
clock. A plain «sí» still answers the most recent question, as before.
"""
from __future__ import annotations

import threading
import time

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo.turn import confirm_gates as gates

GAME = "Crear un NUEVO widget de juego de plataformas tipo Super Mario (saltar, moverse, enemigos)"
OTHER = "Vale. Del informe quítame los híbridos, solo eléctricos puros. ¿Y el monitor qué tal lo llevas?"
YES = "Sí, móntalo. Y ese ponle que salte más alto, que si no se quedan cortos los saltos entre plataformas."


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {k: {"choice": c, "confidence": 0.99, "probs": {c: 0.99}}
                                    for k, c in verdicts.items()}, "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.fixture
def launched(monkeypatch):
    out = []
    monkeypatch.setattr("nucleo.flash.escalate.escalate_to_slowbrain",
                        lambda req, context=None: out.append(req) or 1)
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [])
    now = time.time()
    monkeypatch.setattr(dc, "_EXPIRED_CONFIRM", {})
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {
        "7": {"request": GAME, "kind": "code", "trusted": True, "context": {}, "sheet": "", "ts": now - 20,
              "code_change": "create", "question": "Me pides que te CONSTRUYA una tarjeta nueva. ¿La hago?"},
        "offer:1": {"request": OTHER, "kind": "generic", "trusted": True, "context": {}, "sheet": "", "ts": now,
                    "offered": True, "question": "¿Quieres que lo haga?"}})
    return out


def test_the_yes_that_names_the_game_launches_the_game(launched, monkeypatch):
    from widgets import confirm as wconfirm
    asked = []
    # the live judge, shown a question, reads this sentence as a yes to the GAME's and as «other» to anything else
    monkeypatch.setattr(wconfirm, "_judge", lambda q, r, timeout=4.0: asked.append(q) or (
        "yes" if "CONSTRUYA" in q else "other"))
    ans = gates.resolve_all(YES, brief=_brief(request_type="order"))
    assert all("CONSTRUYA" in q for q in asked), f"judged against the wrong question: {asked}"
    assert ans and ans.yes and ans.gate == "task"
    assert len(launched) == 1 and launched[0].startswith(GAME), launched
    assert "salte más alto" in launched[0], "what he added travels with the yes"
    assert list(dc._PENDING_CONFIRM) == ["offer:1"], "the other question is still waiting"


def test_with_no_judge_a_yes_naming_the_parked_errand_still_answers_it(launched):
    ans = gates.resolve_all("Sí, venga, móntame el juego de plataformas.", brief=_brief(request_type="order"))
    assert ans.yes and len(launched) == 1 and launched[0].startswith(GAME)


def test_a_sentence_about_the_parked_game_keeps_it_alive(launched):
    dc._PENDING_CONFIRM["7"]["ts"] = time.time() - dc._CONFIRM_TTL + 5     # five seconds from expiring
    ans = gates.resolve_all("Oye, ¿y al juego le puedes poner monedas? De esas que vas recogiendo.",
                            brief=_brief(request_type="order"))
    assert not ans and not launched
    p = dc._PENDING_CONFIRM["7"]
    assert time.time() - p["ts"] < 2, "his talking about it restarts the clock"
    assert any("monedas" in r for r in p.get("refinements") or [])
    dc._sweep_confirm(time.time() + 30)
    assert "7" in dc._PENDING_CONFIRM, "it did not expire under him"


def test_a_plain_yes_still_answers_the_newest_question(launched):
    ans = gates.resolve_all("Sí.")
    assert ans.yes and launched == [OTHER]
    assert "7" in dc._PENDING_CONFIRM
