"""A «Buy» click on an errand where he only ASKED about rows goes back to the worker, not to him (node 2.654).

things-to-do-nearby-weekend ES (2026-10-14, sandbox 021515-es): he asked «¿para qué día es…?» and «¿Y de precio qué
tal?» about the jazz row, and the round ended on «La tarea 2 necesita tu OK para pulsar «Comprar»» — the worker had
gone into a checkout to read a price. `click_gate.may_act` now refuses that click to the worker with what to do
instead, and `confirm` (the ask to him) is never called.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from nucleo import his_words
from widgets.navegador import buy_held, click_gate
from widgets.results import data as sheet

ROWS = [{"title": "WAH Show Madrid: El show más…"}, {"title": "Piano Jazz Café de la Ópera, El…"}]
BUY = {"name": "Comprar", "role": "button", "isSubmit": False, "inForm": False, "pageUrl": "https://x.es/evento"}


@pytest.fixture()
def errand(monkeypatch):
    from nucleo import dispatch
    his_words.reset()
    buy_held.forget()
    rec = SimpleNamespace(task_id="w1", nav_task="t9", surface="lista", sheet="t2654", started=time.time())
    monkeypatch.setattr(dispatch, "record_by_nav_task", lambda tid: rec if str(tid) == "t9" else None)
    sheet.store.save(sheet.sheet_key("t2654"), {"title": "Planes finde Madrid", "items": [dict(r) for r in ROWS]})
    yield rec
    his_words.reset()
    buy_held.forget()


class _Handle:
    async def evaluate(self, _js):
        return dict(BUY)


def _may_act():
    asked = []

    async def confirm(q):
        asked.append(q)
        return True
    ok, why = asyncio.run(click_gate.may_act(None, _Handle(), confirm=confirm, task_id="t9"))
    return ok, why, asked


def test_a_question_about_a_row_holds_the_buy_click_without_asking_him(errand):
    his_words.note("El de jazz me llama, pero ¿para qué día es, sábado o domingo?")
    his_words.note("¿Y de precio qué tal?")
    ok, why, asked = _may_act()
    assert not ok and asked == []
    assert "Piano Jazz" in why and "read it on the page" in why


def test_the_held_reason_names_the_rows_he_asked_about(errand):
    his_words.note("¿El de jazz cuánto cuesta?")
    assert "Piano Jazz Café de la Ópera" in buy_held.held("t9", "el botón dice «Comprar»")
