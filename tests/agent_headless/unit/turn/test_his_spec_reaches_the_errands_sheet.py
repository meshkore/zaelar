"""A spec he states about ONE errand reaches that errand's sheet, whatever the reply did with it (node 2.555).

three-tasks-at-once (ES, 2026-10-11 11:34, sandbox 113401-es). «Y el monitor, que sea de 27 al menos» got «del monitor
apunto lo de 27 pulgadas o más; ¿te vale hasta cuánto pagar?» and no call: a reply that asks is no promise, so no
backstop sent it. The monitor sheet never heard the floor and its finalists opened with an LG 24", a BenQ 24" and an
Asus 23,8". He said it twice more after the delivery and the rows stayed. Both channels now hand each sentence that
names exactly one errand with a sheet — and states something the sheet's door reads — to that sheet
(`nucleo/turn/his_spec_to_sheet.py`): the same re-judging an injected correction gets.
"""
from __future__ import annotations

import time
import types

import pytest

from nucleo import dispatch
from nucleo.dispatch import confirm as dc
from nucleo.flash import escalate
from nucleo.turn import errands_of_a_turn as E, his_spec_to_sheet as S
from nucleo.workers import ended
from widgets.results import data as sheet

SHEET = "t2555"
MONITOR = {"id": "3", "request": E.listing_errand({"query": "monitor de segunda mano barato", "condition": "usado"}),
           "phase": "", "waiting_on": "", "surface": "lista", "sheet": f"results::{SHEET}"}
REPORT = {"id": "1", "request": "Elaborar un INFORME escrito sobre coches eléctricos para uso urbano", "phase": "",
          "waiting_on": "", "surface": "informe", "sheet": ""}
GAME = "Crear un widget nuevo: un juego de plataformas tipo Super Mario, jugable con teclado"
ROWS = ['LG UltraGear 24" IPS 144Hz', 'Fujitsu P27-8 TE Pro 27" QHD', 'Asus VA24DQ 23,8" IPS 75Hz']


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(REPORT), dict(MONITOR)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="", title=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {"6": {"request": GAME, "kind": "code", "context": {}, "sheet": "",
                                                       "ts": time.time(), "question": "¿La hago?"}})
    monkeypatch.setattr(escalate, "_tasks", {})
    monkeypatch.setattr(ended, "_ENDED_SESSIONS", {})
    sheet.store.save(sheet.sheet_key(SHEET), {"title": "Resultados", "items": [{"title": t, "price": "50 €"} for t in ROWS]})
    S.forget()


def _titles() -> list[str]:
    return [i["title"] for i in sheet.view_data(SHEET)["items"]]


def test_the_measured_sentence_rejects_the_rows_under_his_floor(live):
    said = ("Oye, genial. En lo del juego, que el muñeco salte más alto, que si no se hace un poco pesado. Y el "
            "monitor, que sea de 27 al menos, que con")
    assert S.carry(said) == [f"results::{SHEET}"]
    assert _titles() == ['Fujitsu P27-8 TE Pro 27" QHD']


def test_a_sentence_naming_two_errands_is_left_alone(live):
    # the monitor is the errand it names MOST — and the ceiling in it is the report's
    said = "Que el informe no pase de 30.000 €, y lo del monitor de segunda mano barato ya te lo dije."
    assert S.carry(said) == []
    assert _titles() == ROWS, "the report's ceiling must never become the monitor's"


def test_a_sentence_with_no_spec_changes_nothing(live):
    assert S.carry("¿Y el monitor cómo va?") == []
    assert _titles() == ROWS


def test_a_finished_errand_still_hears_it(live, monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [])
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(ended, "_ENDED_SESSIONS", {"3": {
        "id": "3", "goal": MONITOR["request"], "status": "done", "ok": True, "summary": "", "at": time.time() - 30,
        "told": 0, "sheet": f"results::{SHEET}", "title": "", "kind": "", "error_class": ""}})
    monkeypatch.setattr(ended, "_live_goals", lambda: set())
    S.carry("Oye, me has dicho que el monitor era de 27 o más, y ahora me sacas un LG de 24 y un Asus de 23,8... "
            "eso no me vale.")
    assert _titles() == ['Fujitsu P27-8 TE Pro 27" QHD']


def test_the_voice_channel_carries_it_on_every_turn(live):
    from voice.engine.llm.providers import promise_backstop
    promise_backstop.run("Apuntado.", did_act=True, op_text="Y el monitor, que sea de 27 al menos.", prev_pending=[],
                         emit=lambda *a, **k: None, escalate=lambda *a, **k: 0, similar_pending=lambda *a: None)
    assert _titles() == ['Fujitsu P27-8 TE Pro 27" QHD']
