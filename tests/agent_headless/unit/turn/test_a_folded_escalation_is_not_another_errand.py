"""An escalation the dedup FOLDED into a live errand is part of that errand — never a second one (node 2.600).

best-plumber-same-day ES (2026-10-14, sandbox 010939-es). «ya cerré la llave de paso… si esto no sale hoy me lanzo a
llamar al primero que vea» escalated and the dedup folded it into the live plumber errand (`dedup`, by `model`). Its
escalation stayed open in `escalate._tasks`, so for 90 s `errand_pool.starting` listed his complaint as an errand of
its own. At his goodbye — «Gracias por la ayuda. Quedo a la espera si sale algo, un saludo.» — `named_errand` matched
that phantom by «sale», `delivery._not_owed` read «the turn is about another errand», and three plumbers with their
phones stayed in the prompt while the reply said «Un saludo, y aquí sigo pendiente».

`dispatch_listener._fold_into` / `_absorb_into` close the escalation they fold.
"""
from __future__ import annotations

import asyncio
import time
import types

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo import dispatch_listener as L
from nucleo.flash import delivery, escalate, live_blocks
from nucleo.turn import named_errand

PLUMBER = {"id": "1", "request": "Buscar y contactar fontaneros de urgencia en Madrid centro con buenas valoraciones "
                                 "(reputación contrastada, opiniones recientes positivas)",
           "phase": "", "waiting_on": "", "surface": "lista", "sheet": "results::d3041f-1"}
COMPLAINT = ("ya cerré la llave de paso, no cae ni gota. pero sigo sin tener nada tuyo? es que si esto no sale hoy me "
             "lanzo a llamar al primero que vea")
GOODBYE = "Gracias por la ayuda. Quedo a la espera si sale algo, un saludo."
ROWS = ["FONTANEROS URGENCIAS 24 HORAS… — 652 66 18 46", "Fontanero Urgencia Madrid — 683 13 98 19",
        "Fontaneros Madrid 24h 🧰 — 910 05 95 22"]
WAIT = "Un saludo, y aquí sigo pendiente. En cuanto salga algo te lo hago saber."


@pytest.fixture
def folded(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(PLUMBER)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="", title=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(escalate, "_tasks", {2: {"request": COMPLAINT[:200], "started_at": time.time() - 66,
                                                 "done": False, "summary": ""}})
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (PLUMBER["request"], list(ROWS)))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: False)
    injected: list = []

    async def _inject(which, message):
        injected.append((which, message))
        return [which]
    monkeypatch.setattr(dispatch, "inject", _inject)
    delivery.forget_announced()
    return injected


def test_an_open_folded_escalation_is_what_withheld_the_plumbers(folded):
    """The measured state, reproduced: the phantom is named, the rows are held."""
    assert any(e.get("starting") for e in named_errand.named(GOODBYE)), "the phantom errand is named by «sale»"
    assert delivery.apply_to_reply(WAIT, [], heard_now=GOODBYE) == WAIT


def test_folding_closes_the_escalation_and_the_goodbye_gets_the_rows(folded):
    asyncio.run(L._fold_into("1", COMPLAINT, "2"))
    assert folded == [("1", COMPLAINT)], "the refinement still reaches the live errand"
    assert not escalate.pending(), "a folded escalation is no longer in flight"
    assert not any(e.get("starting") for e in named_errand.known())
    out = delivery.apply_to_reply(WAIT, [], heard_now=GOODBYE)
    assert "652 66 18 46" in out and "683 13 98 19" in out, out


def test_absorbing_into_a_parked_errand_closes_it_too(folded, monkeypatch):
    monkeypatch.setattr(dispatch, "absorb_refinement", lambda pdup, request: "¿La lanzo?")
    assert L._absorb_into("7", COMPLAINT, "2") == "¿La lanzo?"
    assert not escalate.pending()


def test_a_key_that_is_not_an_escalation_id_is_left_alone(folded):
    L._close_folded("?")
    assert escalate.pending(), "nothing to close under a key that names no escalation"
