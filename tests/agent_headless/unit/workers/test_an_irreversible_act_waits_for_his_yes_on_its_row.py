"""An irreversible act of a card waits for his yes ON ITS ROW, through the one asker (V2-857 phase 3).

What he does by hand: «vacía toda la agenda» — the agenda's `clear_all` is `confirm:true`, so the engine asks. The
question used to live in this process's memory for 90 s (`widgets.confirm._PENDING`) and its yes was read by a word
list before the brief: a restart or a barge-in lost it, and «ok, book it» once sent a mail. Now the request's inline
row waits with its `ask_id`, the act is retained on the row, the two answers are DECLARED candidates the brief picks
(`#0` yes · `#1` no) and the screen shows as buttons, and the yes re-runs the act through its own door — once,
whoever answered first (the voice bound by the brief, or the card's button). Nothing waits in memory.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from nucleo.request import consent_ask as ca, inline_ask as ia, model as rq

TURNS = {"es": ("vacía toda la agenda", "¿Vacío toda la agenda?", "sí, vacíala"),
         "en": ("clear the whole agenda", "Clear the whole agenda?", "yes, clear it")}


@pytest.fixture
def world(monkeypatch):
    from nucleo.cli import worker_api, worker_api_resume
    from nucleo.flash import data_ops
    from nucleo.turn import verdicts
    from widgets import confirm as wc
    st = {"dispatched": [], "choice": None, "events": []}

    async def _dispatch(wid, action, payload, **kw):
        st["dispatched"].append((wid, action, dict(payload or {}), kw.get("row")))
        return {"ok": True}
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    monkeypatch.setattr(worker_api_resume, "resume_soon", lambda uid, e: None)
    monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None:
                        (st["choice"], {"confidence": 0.9}) if key == "answers_open_question" and st["choice"] else (fb, None))
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        st["events"].append((kind, label, dict(extra or {}))) or real(kind, label, text=text, role=role, extra=extra))
    wc.reset()
    ia._TAKEN.clear()
    st["rows"] = []
    yield st
    from nucleo.circuit import ledger
    for uid in st["rows"]:                      # the rows this test opened go with it: nothing waits for the next test
        ledger.store().task_forget(uid)
    wc.reset()
    ia._TAKEN.clear()
    rq._TURN.set(None)


def _ask(world, lang: str) -> tuple[str, str]:
    words, question, _yes = TURNS[lang]
    rq.begin(words)
    row, ask_id = ca.ask_consent("agenda", "clear_all", {}, question, text=words)
    assert row and ask_id, "the question found no row"
    world["rows"].append(row)
    return row, ask_id


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_question_waits_on_the_row_with_its_two_declared_answers_and_nothing_in_memory(world, lang):
    from nucleo.cli import worker_api
    from nucleo.turn.prompt import live_tasks
    from widgets import confirm as wc
    row, ask_id = _ask(world, lang)
    (a,) = [a for a in worker_api.open_asks() if a["ask_id"] == ask_id]
    assert a["task_id"] == row and a["candidates"] == ca.yes_no() and len(a["candidates"]) == 2
    assert wc.pending() == {}, "the question still waits in this process's memory"
    assert any(TURNS[lang][1][:20] in ln for ln in live_tasks.waiting_lines()), "the next turn is not told about it"
    kinds = [(k, e.get("ask_id")) for k, _l, e in world["events"] if k in ("task", "ask")]
    assert ("task", ask_id) in kinds and ("ask", ask_id) in kinds


@pytest.mark.parametrize("lang", ["es", "en"])
def test_his_yes_bound_by_the_brief_runs_the_act_once_on_that_row(world, lang):
    from nucleo.cli import worker_api, worker_api_bind as bind
    from nucleo.circuit import ledger
    row, ask_id = _ask(world, lang)
    world["choice"] = f"{ask_id}#0"
    how, asks = bind.bind(object())
    assert how == bind.ANSWER and asks[0]["ask_id"] == ask_id and asks[0]["choice"] == 0
    assert asyncio.run(worker_api.answer(ask_id, TURNS[lang][2], choice=0)) is True
    assert world["dispatched"] == [("agenda", "clear_all", {}, row)]
    assert (ledger.get(row) or {}).get("waiting_for") in (None, ""), "the row still waits after his yes"
    # a second reader of the same answer (the model re-calling the act, the button) runs nothing more
    assert asyncio.run(worker_api.answer(ask_id, TURNS[lang][2], choice=0)) is False
    assert len(world["dispatched"]) == 1


def test_his_no_ends_the_row_and_runs_nothing(world):
    from nucleo.cli import worker_api
    from nucleo.circuit import ledger
    row, ask_id = _ask(world, "es")
    assert asyncio.run(worker_api.answer(ask_id, "no, déjala", choice=1)) is True
    assert world["dispatched"] == [] and (ledger.get(row) or {}).get("state") == "cancelled"


def test_the_cards_button_answers_the_same_question(world):
    from fastapi.responses import JSONResponse
    from widgets import server_api
    row, ask_id = _ask(world, "en")
    res: JSONResponse = asyncio.run(server_api.confirm_widget("agenda", {"ok": True}))
    assert res.status_code == 200 and world["dispatched"] == [("agenda", "clear_all", {}, row)]
    again: JSONResponse = asyncio.run(server_api.confirm_widget("agenda", {"ok": True}))
    assert again.status_code == 409 and len(world["dispatched"]) == 1


def test_the_turn_asks_on_the_row_first_and_keeps_the_old_gate_only_when_no_row_opens():
    from nucleo.flash import tool_executor_widget as txw
    src = inspect.getsource(txw)
    assert src.index("_ca.ask_consent(") < src.index('_wconfirm.request("data", d["wid"]')
    assert "if not row:" in src


def test_disarmed_in_memory_the_yes_binds_nothing(world, monkeypatch):
    from nucleo.cli import worker_api_bind as bind
    from widgets import confirm as wc
    monkeypatch.setattr(ca, "ask_consent", lambda wid, action, payload, question, text="":
                        (wc.request("data", wid, question, op={"action": action, "payload": payload}, notify_ui=False), "") and ("", ""))
    rq.begin(TURNS["es"][0])
    assert ca.ask_consent("agenda", "clear_all", {}, TURNS["es"][1], text=TURNS["es"][0]) == ("", "")
    assert wc.pending(), "the disarm did not take"
    world["choice"] = "anything#0"
    assert bind.bind(object()) == (bind.NOTHING, []), "with the question in memory the brief had nothing to bind"
