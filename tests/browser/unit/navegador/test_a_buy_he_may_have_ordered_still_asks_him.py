"""A «Buy» click still ASKS him whenever he may have ordered it (node 2.655) — the other side of node 2.654.

`buy_held` only hands a click back when his only words about the sheet's rows are questions and no row is chosen.
Everything else keeps the click gate exactly as it was: a chosen row, an order that names a row without asking, an
errand without a sheet, a page that could not be read.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from nucleo import his_words
from widgets.navegador import buy_held
from widgets.results import data as sheet

WHY = "el botón dice «Comprar»"


@pytest.fixture()
def rec(monkeypatch):
    from nucleo import dispatch
    his_words.reset()
    buy_held.forget()
    r = SimpleNamespace(task_id="w2", nav_task="t8", surface="lista", sheet="t2655", started=time.time())
    monkeypatch.setattr(dispatch, "record_by_nav_task", lambda tid: r if str(tid) == "t8" else None)
    sheet.store.save(sheet.sheet_key("t2655"), {"title": "Planes", "items": [{"title": "Piano Jazz Café de la Ópera"}]})
    yield r
    his_words.reset()
    buy_held.forget()


def test_a_chosen_row_asks(rec):
    his_words.note("¿El de jazz cuánto cuesta?")
    data = sheet.view_data("t2655")
    sheet.store.save(sheet.sheet_key("t2655"), {**data, "chosen": "Piano Jazz Café de la Ópera"})
    assert buy_held.held("t8", WHY) == ""


def test_an_order_that_names_the_row_asks(rec):
    his_words.note("Cómprame dos entradas del jazz.")
    assert buy_held.held("t8", WHY) == ""


class _Unreadable:
    async def evaluate(self, _js):
        raise RuntimeError("detached frame")


@pytest.mark.parametrize("code", ["es", "en"])
def test_an_unreadable_page_asks_in_either_language(rec, monkeypatch, code):
    """The gate's reason for an unreadable page travels as a FACT (`readable=False`), never as its text: on
    2026-10-14 `a436f23e` moved the text to the langspec and the hold kept comparing against the old literal,
    so an unreadable page was held in both languages (audit V2-783 P0-4)."""
    import asyncio
    from widgets.navegador import click_gate
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    his_words.note("¿El de jazz cuánto cuesta?")
    asked = []

    async def confirm(q):
        asked.append(q)
        return False
    ok, _why = asyncio.run(click_gate.may_act(None, _Unreadable(), confirm=confirm, task_id="t8"))
    assert not ok and len(asked) == 1            # he was asked — the click was not held back to the worker
    assert buy_held.held("t8", _why, readable=False) == ""


def test_an_errand_without_a_sheet_asks(rec):
    rec.surface = "voz"
    his_words.note("¿El de jazz cuánto cuesta?")
    assert buy_held.held("t8", WHY) == ""


def test_a_browser_task_of_no_errand_asks(rec):
    assert buy_held.held("t-unknown", WHY) == ""


def test_a_hold_lasts_only_until_he_speaks_again(rec):
    his_words.note("¿El de jazz cuánto cuesta?")
    assert buy_held.held("t8", WHY)                       # held once: the worker is told to read the price
    assert buy_held.held("t8", WHY)                       # he said nothing new: still held
    his_words.note("Vale, cómpralo.")
    assert buy_held.held("t8", WHY) == ""                 # his next word makes the click his to answer
