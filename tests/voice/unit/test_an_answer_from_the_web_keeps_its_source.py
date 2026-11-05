"""An answer a web search gave keeps its source in the dialog window (node 3.176).

V2-834 T11, use case `quick-fact-opening-hours` (sandbox, 2026-11-02): the first turn searched («🔎 resultados web»)
and answered hours and price from it; two turns later, «¿seguro de esos datos? ¿Los has comprobado?», the reply was
«no los he comprobado, te los he dado de memoria» — the window held only the words, so the model could not know its
own answer was sourced, and denied it.

Mechanism pinned here: the window's copy of a reply a web search answered carries `[web search: «query»]`; single
brackets are a stage direction to the mouth, so if the model ever imitates it, nothing is spoken.
"""
from __future__ import annotations

from tests.voice_turn_source import read as _vts_read

import ast
from pathlib import Path

import pytest

from nucleo.flash import dialog
from voice import speech

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("reply, query", [
    ("Mañana abre a las diez y la entrada general cuesta quince euros.", "Museo del Prado horario y precio entrada"),
    ("It opens at 10 and general admission is $30.", "MoMA opening hours tomorrow and ticket price"),
])
def test_the_window_line_names_the_search(reply, query):
    got = dialog.sourced(reply, query)
    assert got.startswith(reply) and f"«{query}»" in got
    assert speech.drop_stage_directions(got).strip() == reply, "an imitation of the marker is never spoken"


def test_without_a_search_the_line_is_the_reply():
    assert dialog.sourced("Hola.", None) == "Hola." and dialog.sourced("", "q") == ""


def test_the_voice_turn_writes_the_window_through_it():
    tree = ast.parse(_vts_read(ROOT / "nucleo/turn/pipeline_close.py"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "source_last_reply"]
    assert calls and any("search_req" in ast.unparse(c) for c in calls), "the window write must carry the search"


def test_only_our_last_line_is_marked():
    win = [{"role": "user", "content": "¿A qué hora abre?"}, {"role": "assistant", "content": "A las diez."}]
    dialog.source_last_reply(win, "horario museo")
    assert win[-1]["content"] == "A las diez. [web search: «horario museo»]"
    mute = [{"role": "user", "content": "x"}]
    dialog.source_last_reply(mute, "q")
    assert mute == [{"role": "user", "content": "x"}], "an unanswered order gets no source line"
