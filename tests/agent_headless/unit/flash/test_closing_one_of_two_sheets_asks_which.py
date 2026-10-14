"""«Cierra los resultados» with two errands' sheets open asks WHICH — it never closes both (node 2.645).

two-searches-two-sheets (ES, 2026-10-14, sandbox 024032-es): a plumber hunt and a car hunt, each with its sheet
open (`results::8862f3-1`, `results::8862f3-2`). «cierra los resultados» → `close_widget(results)`; the target
resolver kept the bare id (two real sheets, no focus) and the tool path closed it — both sheets went, and the reply
said «He cerrado Resultados. Ya no queda nada en pantalla.». The [[close]] tag already asked in this situation
(`instances.resolve_close`); both tool paths now ask through `nucleo/flash/close_which.py`.
"""
from __future__ import annotations

import inspect
import tempfile

import pytest

from nucleo.flash import close_which as CW
from nucleo.flash import show_target as ST
from widgets import store

OPEN = ["results::8862f3-1", "results::8862f3-2"]


@pytest.fixture(autouse=True)
def _two_sheets(monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tempfile.mkdtemp())
    store._last_hash.clear()
    monkeypatch.setattr("i18n.langs.current_code", lambda: "es")
    from widgets.results import data as sheet
    store.save(sheet.sheet_key("8862f3-1"), {"title": "Fontaneros para el jueves · Madrid centro", "items": [{"title": "x"}]})
    store.save(sheet.sheet_key("8862f3-2"), {"title": "Coches de segunda mano hasta 8.000 €", "items": [{"title": "y"}]})
    monkeypatch.setattr("server.voice_api.open_instances", lambda: list(OPEN))
    from nucleo import canvas_focus
    monkeypatch.setattr(canvas_focus, "last_turn_card", lambda ids: "")
    yield
    store._last_hash.clear()


def test_the_text_channel_asks_and_closes_nothing():
    card = ST.close_target("results")
    assert card == "results", card                       # the resolver cannot pick one: it keeps the bare id
    action, question = CW.probe_action({"widget_id": "results"}, card, "cierra los resultados")
    assert action == "clarify", action
    assert "Fontaneros" in question and "Coches" in question, question


def test_the_voice_tool_path_asks_and_emits_no_close():
    tags, clarify = [], {"msg": ""}
    rid = ST.close_dispatch({"widget_id": "results"}, lambda a, x: tags.append((a, x)), lambda *a, **k: None,
                            text="cierra los resultados", clarify=clarify)
    assert rid and not tags, f"a close reached the canvas: {tags}"
    assert "Fontaneros" in clarify["msg"] and "Coches" in clarify["msg"], clarify


@pytest.mark.parametrize("said,closes", [
    ("cierra los dos", "canvas:close:results"),             # both: his answer to «which» is ALL
    ("cierra la de los coches", "canvas:close:results::8862f3-2"),  # a title word names one
])
def test_his_words_still_decide_without_a_question(said, closes):
    action, question = CW.probe_action({"widget_id": "results"}, "results", said)
    assert question == "" and action == closes, (action, question)


def test_one_sheet_open_is_closed_without_asking(monkeypatch):
    monkeypatch.setattr("server.voice_api.open_instances", lambda: ["results::8862f3-1"])
    assert CW.probe_action({"widget_id": "results"}, "results::8862f3-1", "cierra los resultados") == \
        ("canvas:close:results::8862f3-1", "")


def test_a_minimize_never_asks():
    assert CW.probe_action({"widget_id": "results", "mode": "minimize"}, "results", "minimiza los resultados")[1] == ""


def test_both_tool_paths_read_the_question():
    """The wiring: the text channel's action naming and the voice executor both pass through the asking door."""
    from nucleo.flash import probe_decide, tool_executor_calls
    assert "_close_which.probe_action(" in inspect.getsource(probe_decide.name_the_action)
    assert "clarify=clarify" in inspect.getsource(tool_executor_calls._on_tool_call).split('name == "close_widget"', 1)[1][:400]
