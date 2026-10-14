"""His sentence that COMMISSIONED an errand reaches that errand's sheet, and its door judges rows by it (node 2.630).

find-concert-tickets ES (2026-10-14, sandbox 021207-es). «Búscame entradas para un concierto de Rosalía en Madrid este
mes» became a worker errand whose sheet never had `asked` — only the listing fast pass wrote it — so the door read no
subject, and «Miguel Lago», «El Club de los Poetas Muertos» and «El Cascanueces - Classic Stage» were offered as
candidates. The text channel's launch (`probe_after._launch`) now notes his sentence for the turn's single errand, and
`sheets._sheet_open` hands it to the sheet (`nucleo/turn/commission_words.py`).
"""
from __future__ import annotations

import inspect

import pytest

from nucleo import sheets
from nucleo.turn import commission_words as CW
from nucleo.workers.session import SessionRecord
from widgets.results import data as sheet

HEARD = "Búscame entradas para un concierto de Rosalía en Madrid este mes, lo más baratas posible."
REQUEST = ("Buscar entradas para un concierto de Rosalía en Madrid en el mes de octubre de 2026 (mes en curso). "
           "El operador quiere las más baratas posibles.")
ROWS = [{"title": "Miguel Lago", "price": "19,17 €", "url": "https://www.entradas.com/event/miguel-lago"},
        {"title": "El Club de los Poetas Muertos", "price": "18,50 €", "url": "https://www.entradas.com/event/club"},
        {"title": "El Cascanueces - Classic Stage", "price": "33,00 €", "url": "https://www.entradas.com/event/cn"},
        {"title": "ROSALÍA · LUX Tour — Movistar Arena", "price": "65,00 €",
         "url": "https://www.ticketmaster.es/rosalia-lux-tour"}]


@pytest.fixture(autouse=True)
def _clean():
    CW.forget()
    yield
    CW.forget()


def _open(task_id: str) -> str:
    rec = SessionRecord(task_id=task_id, goal=REQUEST[:200])
    sheets._sheet_open(rec, show=False)
    return rec.sheet


def test_the_measured_round_keeps_only_rows_that_name_rosalia():
    assert CW.note([REQUEST], HEARD)
    sid = _open("t2630a")
    sheet.apply_action("present", {"sheet": sid, "items": ROWS})
    view = sheet.view_data(sid)
    assert [i["title"][:18] for i in view["items"]] == ["ROSALÍA · LUX Tour"]
    assert {r["title"] for r in view["rejected"]} >= {"Miguel Lago", "El Cascanueces - Classic Stage"}


def test_without_his_words_the_door_reads_no_subject():
    sid = _open("t2630b")                    # nothing noted: today's behaviour, every row stays
    sheet.apply_action("present", {"sheet": sid, "items": ROWS})
    assert len(sheet.view_data(sid)["items"]) == 4


def test_a_turn_that_commissions_two_errands_hands_neither_its_words():
    assert not CW.note([REQUEST, "Buscar un hotel en Sevilla"], "entradas de Rosalía y un hotel en Sevilla")
    assert CW.take(REQUEST) == ""


def test_words_are_taken_once_and_our_notes_are_never_his():
    assert CW.note([REQUEST], HEARD + "\n\n[SISTEMA] Avisos pendientes — algo")
    assert CW.take(REQUEST) == HEARD
    assert CW.take(REQUEST) == ""


def test_a_sheet_that_already_holds_his_words_keeps_them():
    from widgets.results import category_gate
    sid = _open("t2630c")
    assert category_gate.hear(sid, "busco un monitor de 27")
    assert not category_gate.hear(sid, HEARD)
    assert category_gate.asked_of(sid) == "busco un monitor de 27"


def test_both_ends_are_wired():
    from nucleo.flash import probe_after
    assert "_commission_words.note(reqs, heard)" in inspect.getsource(probe_after._launch)
    assert "heard=operator_text" in inspect.getsource(probe_after.execute_what_was_decided)
    assert "_cw.seed(_sid" in inspect.getsource(sheets._sheet_open)
