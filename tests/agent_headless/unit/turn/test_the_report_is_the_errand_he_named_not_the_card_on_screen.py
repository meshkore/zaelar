"""«El informe» is the errand he named, not the card on screen (node 2.436).

three-tasks-at-once (ES/EN, 2026-10-11 02:04). The monitor's results sheet was the card on screen; the car report ran
in the background with no card of its own in front of him. «¿Y el informe ese va bien? Lo quiero corto, con autonomía
real y precio, para España» — the screen verdict read `results:criteria`, and the repair wrote «informe corto, con
autonomía real» as CRITERIA ON THE MONITOR SHEET. Three turns later «A ver si ahora sí me sacas el listado de
eléctricos puros… Y el juego… El monitor ya está, ¿no?» was repaired into `results:present` on the same sheet, and the
answer read back from it was «No hay nada en Resultados: ni listado de eléctricos, ni datos del juego, ni el monitor».

The sentence's errand is read from his original asks (`named_errand`), and a results/document card owned by another
errand is not where his order goes — in both channels' repair doors.
"""
from __future__ import annotations

import asyncio
import time
import types

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo.flash import act_repair, build_decision, card_commission
from nucleo.turn import errands_of_a_turn as E
from nucleo.turn import named_errand

REPORT = {"id": "1", "request": "Elaborar un INFORME escrito (documento completo, no una lista de enlaces) sobre coches "
                                "eléctricos para uso urbano: modelos, autonomía real, precio de compra y de uso",
          "phase": "", "waiting_on": "", "surface": "informe", "sheet": ""}
MONITOR = {"id": "3", "request": E.listing_errand({"query": "monitor de segunda mano barato"}),
           "phase": "", "waiting_on": "", "surface": "lista", "sheet": "results::afe5ce-3"}
ABOUT_THE_REPORT = "¿Y el informe ese va bien? Lo quiero corto, con autonomía real y precio, para España."
ABOUT_ALL_THREE = ("Vale, perfecto. A ver si ahora sí me sacas el listado de eléctricos puros, corto, con autonomía "
                   "real y precio en España. Y el juego, ¿me dices cuando lo tengas con el salto más alto y las "
                   "monedas? El monitor ya está, ¿no?")
ABOUT_THE_MONITOR = "Oye, esos monitores son de 22, no de 27. Sigue buscando monitores de 27."


@pytest.fixture(autouse=True)
def errands(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(REPORT), dict(MONITOR)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {"7": {
        "request": "Crear un NUEVO widget de juego de plataformas tipo Super Mario", "kind": "code", "context": {},
        "trusted": True, "sheet": "", "ts": time.time(), "question": "¿La hago?"}})


def test_a_sentence_about_the_report_does_not_belong_to_the_monitor_sheet():
    assert named_errand.card_is_another_errands("results", ABOUT_THE_REPORT)
    assert named_errand.card_is_another_errands("results::afe5ce-3", ABOUT_THE_REPORT)
    assert named_errand.card_is_another_errands("results", ABOUT_ALL_THREE), "the report is what it names most"
    assert not named_errand.card_is_another_errands("documento", ABOUT_THE_REPORT), "the report's own box"
    assert not named_errand.card_is_another_errands("results::afe5ce-3", ABOUT_THE_MONITOR)
    assert not named_errand.card_is_another_errands("results", "Vale, gracias."), "names nothing: the screen decides"
    assert not named_errand.card_is_another_errands("agenda", ABOUT_THE_REPORT), "only sheets belong to errands"


def test_the_repair_doors_decline_the_monitor_sheet(monkeypatch):
    monkeypatch.setattr(build_decision, "named_card", lambda brief: "results")
    assert card_commission.named_or_catalogue({"x": 1}, ABOUT_THE_REPORT) == ""
    assert card_commission.named_or_catalogue({"x": 1}, ABOUT_THE_MONITOR) == "results"

    from nucleo import jev
    from nucleo.flash import turn_brief
    monkeypatch.setattr(turn_brief, "ask_for_turn", lambda text, last_reply="": {"h": 1})
    monkeypatch.setattr(jev, "_is_ready", lambda h: True)
    called = []

    async def _spy(*a, **k):
        called.append(a)
        return {"widget_id": "results", "action": "criteria", "payload": {}}
    monkeypatch.setattr(act_repair, "call_for_promise", _spy)
    assert asyncio.run(act_repair.probe_call_for_promise(ABOUT_THE_REPORT, "Le paso la instrucción.")) is None
    assert not called, "the text channel's own door asks the same question"
    assert asyncio.run(act_repair.probe_call_for_promise(ABOUT_THE_MONITOR, "Sigo buscando.")) is not None
