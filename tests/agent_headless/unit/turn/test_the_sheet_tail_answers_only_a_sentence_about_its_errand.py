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
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
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


def test_a_sentence_about_the_report_gets_no_monitor_rows(three):
    out = delivery.apply_to_reply(WAIT, [], heard_now="¿Y el informe ese va bien? Lo quiero corto, con autonomía "
                                                      "real y precio, para España.")
    assert "Samsung" not in out and out == WAIT, out


def test_a_sentence_about_the_monitor_gets_its_rows_once(three, monkeypatch):
    out = delivery.apply_to_reply(WAIT, [], heard_now="¿Y lo del monitor cómo va? Que no pase de 150, y al menos "
                                                      "27 pulgadas.")
    assert "Samsung C27R500FH" in out, "a bare «27» is his criterion, not a row he named"
    _rows(monkeypatch, ROWS + MORE)
    again = delivery.apply_to_reply(WAIT, [], heard_now="Vale, guay, gracias.")
    assert "ASUS" not in again and again == WAIT, "a sentence about no errand does not get the tail a second time"
    asked = delivery.apply_to_reply(WAIT, [], heard_now="¿Y del monitor hay algo más?")
    assert "ASUS" in asked, "asked about THAT errand, the new rows are owed"


def test_a_row_he_picked_ends_the_offering(three):
    out = delivery.apply_to_reply(WAIT, [], heard_now="Y el monitor sí, con el Samsung de 50 € me vale.")
    assert out == WAIT, out


def test_with_one_errand_a_sentence_naming_none_still_gets_new_rows(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(MONITOR)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: False)
    delivery.forget_announced()
    _rows(monkeypatch, ROWS)
    assert "Samsung" in delivery.apply_to_reply(WAIT, [], heard_now="¿Cómo va?")
    _rows(monkeypatch, ROWS + MORE)
    assert "ASUS" in delivery.apply_to_reply(WAIT, [], heard_now="¿Y ahora?"), "one errand: it is the one he means"
