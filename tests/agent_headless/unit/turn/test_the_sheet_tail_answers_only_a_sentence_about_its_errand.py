"""The results-sheet tail answers only a sentence about ITS errand, and never twice as a tail (node 2.435).

three-tasks-at-once (ES, 2026-10-11 02:04) — a report, a monitor hunt and a game ordered in one breath. «Bueno, de
hecho ya hay candidatos en la hoja de resultados: «…». Dime si alguno te encaja o sigo afinando.» was glued to five
replies in a row: three were answers about the car REPORT («¿Y el informe ese va bien? Lo quiero corto, con
autonomía real y precio»), one came right after he had picked «el Samsung de 27 por 50 €».

The guard that should have held it existed (node 2.350) and read the right thing — which errand his sentence names —
over the wrong words: the monitor's goal is OUR wrapper «Find real marketplace listings for: …», and «real» in
«autonomía real» named the monitor hunt. The errand is named by what HE asked, not by our template.
"""
from __future__ import annotations

import time
import types

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo.flash import delivery, live_blocks
from nucleo.turn import errands_of_a_turn as E
from nucleo.turn import named_errand

REPORT = {"id": "1", "request": "Elaborar un INFORME escrito (documento completo, no una lista de enlaces) sobre coches "
                                "eléctricos para uso urbano: qué modelos existen, autonomía real, precio de compra y de uso",
          "phase": "leyendo", "waiting_on": "", "surface": "informe", "sheet": ""}
MONITOR = {"id": "3", "request": E.listing_errand({"query": "monitor de segunda mano barato", "condition": "usado"}),
           "phase": "entrando en wallapop", "waiting_on": "", "surface": "lista", "sheet": "results::afe5ce-3"}
GAME = "Crear un NUEVO widget de juego de plataformas tipo Super Mario (saltar, moverse, enemigos)"
ROWS = ['Samsung C27R500FH 27" — 50 €', "Millenium MD27 PRO-2 — 35 €", 'Acer ED273 27" — 75 €']
MORE = ['ASUS VG27VH1B 27" — 85 €', "Samsung Essential S4 27\" — 130 €", "AOC Q27G3XMN — 140 €"]


@pytest.fixture
def three(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(REPORT), dict(MONITOR)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="Investigando…"))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {"7": {
        "request": GAME, "kind": "code", "trusted": True, "context": {}, "sheet": "", "ts": time.time(),
        "question": "Si no te he entendido mal, me pides que te CONSTRUYA una tarjeta nueva. ¿La hago?"}})
    monkeypatch.setattr(delivery, "_speaks_en", lambda: False)
    delivery.forget_announced()
    _rows(monkeypatch, ROWS)


def _rows(monkeypatch, rows):
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (MONITOR["request"], list(rows)))


WAIT = "Vale, dame un momento que lo miro."


def test_an_errand_is_named_by_his_ask_not_by_our_wrapper():
    assert E.ask_of(MONITOR["request"]) == "monitor de segunda mano barato"
    assert E.ask_of(REPORT["request"]) == REPORT["request"], "a goal written from his words stays whole"
    hits = named_errand.named("¿Y el informe ese va bien? Lo quiero corto, con autonomía real y precio, para España.",
                              [dict(REPORT, parked=False), dict(MONITOR, parked=False)])
    assert [e["id"] for e in hits] == ["1"], "«real» is our template's word, not his monitor"
