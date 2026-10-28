"""A close that names no card closes the OTHERS — never the card he is working on (V2-807 T-08).

Measured: «Close whatever you don't need right now» closed every card on the canvas, including the draft he had
corrected three times in the minute before. The model's plan kept the document (a `show_widget` over the open
card, discarded as «the order says CLOSE»), and the next fragment reached the canvas as a bare close = close all.

The class: the card in use — the newest card a data-op RAN on, still open, or one the turn chose to keep — is
spared by every bulk close unless his words name it. Read from facts (`done_ops`, the keep), never from words, so
the same holds in any language and any script.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo import done_ops
from nucleo.flash import bulk_close

OPEN = ["documento", "navegador", "mensajeria"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    done_ops.reset()
    bulk_close.reset()
    from nucleo import canvas_arbiter          # the turn ordered the close: the licence the canvas door reads
    monkeypatch.setattr(canvas_arbiter, "request_of", lambda brief=None, text=None, **k: {
        "text": text or "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("close", 0.9)}})
    yield
    done_ops.reset()
    bulk_close.reset()


def _collect():
    events: list[tuple] = []

    def emit(kind, action, text=None, role=None, extra=None):
        events.append((kind, action, dict(extra or {})))
    return events, emit


def _closed(events) -> list:
    return [e[2].get("id", "*ALL*") for e in events if e[0] == "widget" and e[1] == "close"]


@pytest.mark.parametrize("said", [
    "Cierra todo lo que no necesites ahora mismo",
    "Close everything you don't need right now",
    "必要ないものは全部閉じて",
])
def test_the_draft_he_is_working_on_stays_and_the_others_close(said):
    done_ops.note("documento", "show", {"body": "draft"})
    events, emit = _collect()
    kept = bulk_close.close_all(emit, src="flash", text=said, open_ids=OPEN)
    assert kept == ["documento"]
    assert sorted(_closed(events)) == ["mensajeria", "navegador"]


def test_a_card_he_names_is_closed_even_while_in_use():
    done_ops.note("documento", "show", {"body": "draft"})
    events, emit = _collect()
    assert bulk_close.close_all(emit, src="flash", text="cierra todo, también el documento", open_ids=OPEN) == []
    assert _closed(events) == ["*ALL*"]


def test_with_nothing_in_use_a_plain_close_all_closes_all():
    events, emit = _collect()
    assert bulk_close.close_all(emit, src="flash", text="cierra todo", open_ids=OPEN) == []
    assert _closed(events) == ["*ALL*"]
    assert events[0][2] == {"src": "flash"}


def test_an_unknown_canvas_keeps_the_old_bare_close():
    done_ops.note("documento", "show", {})
    events, emit = _collect()
    bulk_close.close_all(emit, src="flash", text="close all", open_ids=[])
    assert _closed(events) == ["*ALL*"]


def test_the_working_card_is_the_newest_one_still_open():
    """The draft moved from the document to the messages card, which then closed: the document is in use again."""
    done_ops.note("documento", "show", {})
    done_ops.note("mensajeria", "open_draft", {})
    assert bulk_close.working_card(["documento", "navegador"]) == "documento"
    assert bulk_close.working_card(OPEN) == "mensajeria"


def test_an_old_data_op_does_not_make_a_card_in_use(monkeypatch):
    done_ops.note("documento", "show", {})
    import time as _time
    later = _time.time() + bulk_close.WORKING_S + 5
    monkeypatch.setattr(done_ops.time, "time", lambda: later)
    assert bulk_close.working_card(OPEN) == ""


def test_a_card_the_model_kept_is_spared_by_the_next_fragment(monkeypatch):
    bulk_close.note_kept("documento")
    events, emit = _collect()
    assert bulk_close.close_all(emit, src="flash", text="lo que no necesites", open_ids=OPEN) == ["documento"]
    later = bulk_close.time.time() + bulk_close.KEPT_S + 1
    monkeypatch.setattr(bulk_close.time, "time", lambda: later)
    assert bulk_close.kept_now() == []


def _brief(canvas, conf=0.96):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [], "result": {"canvas": {"choice": canvas, "confidence": conf}}}


def test_the_voice_fallback_close_goes_through_the_door(monkeypatch):
    from voice.engine.llm.providers import widget_intent as WI
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: list(OPEN))
    monkeypatch.setattr(WI, "_identify_named", lambda text: None)
    done_ops.note("documento", "show", {})
    events, emit = _collect()
    assert WI._widget_fallback("Cierra todo lo que no necesites", emit, brief=_brief("close")) is True
    assert sorted(_closed(events)) == ["mensajeria", "navegador"]


def test_the_hard_interrupt_close_goes_through_the_door(monkeypatch):
    from nucleo.flash import hard_turn
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: list(OPEN))
    done_ops.note("documento", "show", {})
    events, emit = _collect()
    asyncio.run(hard_turn.handle("cierra todo lo que no necesites", "close", emit))
    assert sorted(_closed(events)) == ["mensajeria", "navegador"]


def test_the_action_map_close_all_goes_through_the_door(monkeypatch):
    from nucleo.actionmap import executor
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: list(OPEN))
    done_ops.note("documento", "show", {})
    events, emit = _collect()
    assert executor.execute({"do": "close_all"}, emit, phrase="cierra todo") is True
    assert sorted(_closed(events)) == ["mensajeria", "navegador"]


def test_disarmed_without_the_in_use_reading_the_draft_closes_again(monkeypatch):
    """RED proof: with nothing read as in use the bulk close is the bare close-all — the draft goes with the rest.
    The tests above measure `in_use`, not a constant."""
    done_ops.note("documento", "show", {})
    monkeypatch.setattr(bulk_close, "working_card", lambda open_ids, **k: "")
    events, emit = _collect()
    bulk_close.close_all(emit, src="flash", text="Cierra todo lo que no necesites", open_ids=OPEN)
    assert _closed(events) == ["*ALL*"], "the disarm did not land"
    monkeypatch.undo()
    events, emit = _collect()
    bulk_close.close_all(emit, src="flash", text="Cierra todo lo que no necesites", open_ids=OPEN)
    assert sorted(_closed(events)) == ["mensajeria", "navegador"]   # green again


def _show_on_a_close_turn(wid, monkeypatch, open_now):
    from nucleo.flash import canvas_visibility, tool_executor_calls as TEC

    class _Router:
        @staticmethod
        def show_contradicts_the_order(text):
            return True

    monkeypatch.setattr(canvas_visibility, "is_open", lambda w, known=None: open_now)
    events, emit = _collect()
    TEC._t_show_widget(args={"widget_id": wid}, _brief=None, _router=_Router, _say=None, _show_guard_target=None,
                       _show_target_instance=None, _tag_emit=lambda *a, **k: None, _tool_fired=set(), acted={},
                       brain=None, clarify={}, deduped={"v": False}, emit=emit, escalate_req={"v": None},
                       text="Cierra todo lo que no necesites")
    return events


def test_the_models_show_of_an_open_card_on_a_close_turn_is_a_keep(monkeypatch):
    """T17's plan: close the others and `show_widget(documento)` to keep it. Nothing opens; the keep is recorded."""
    events = _show_on_a_close_turn("documento", monkeypatch, open_now=True)
    assert not [e for e in events if e[0] == "widget"]
    assert bulk_close.kept_now() == ["documento"]


def test_a_show_of_a_closed_card_on_a_close_turn_is_still_discarded(monkeypatch):
    events = _show_on_a_close_turn("navegador", monkeypatch, open_now=False)
    assert not [e for e in events if e[0] == "widget"]
    assert bulk_close.kept_now() == []
