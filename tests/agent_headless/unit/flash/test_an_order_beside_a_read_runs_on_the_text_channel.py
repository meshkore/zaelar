"""An order the model called BESIDE a read runs on the text channel too (V2-781, second round).

Measured in `tres-tarjetas-y-el-video-por-alusion` (ES, 2026-10-10): «Justo estábamos con el tráiler... pausa eso un
momento. Y ya que tengo la agenda abierta, ¿qué tengo el jueves?» → the model called `widget_data youtube:pause` AND
`read_widget agenda` — both right. The voice runs every call; the text channel named ONE action (`read_widget`),
answered Thursday, and the pause never ran: the trailer kept playing while the reply later said it «sigue donde lo
dejamos». The data-ops of a read turn run beside it, through the same rail as every other text-channel data-op.
"""
from __future__ import annotations

import asyncio

from nucleo.flash import probe_companions as pc

TEXT = ("Ah, perfecto. Justo estábamos con el tráiler... pausa eso un momento. Y ya que tengo la agenda abierta, "
        "¿qué tengo el jueves?")
CALLS = [{"name": "widget_data", "args": {"widget_id": "youtube", "action": "pause"}},
         {"name": "read_widget", "args": {"widget_id": "agenda", "question": "¿Qué hay el jueves?"}}]


def _wire(monkeypatch):
    ran = []
    from nucleo.flash import widget_data_turn

    async def _exec(tool_calls, text="", brief=None):
        ran.extend((t["args"]["widget_id"], t["args"]["action"]) for t in tool_calls if t["name"] == "widget_data")
        return {"executed": "widget_data", "ok": True}

    monkeypatch.setattr(widget_data_turn, "execute", _exec)
    return ran


def _run(action, calls=CALLS):
    return asyncio.new_event_loop().run_until_complete(pc.run(action, calls, TEXT, window=[], brief=None))


def test_the_pause_beside_the_read_runs(monkeypatch):
    ran = _wire(monkeypatch)
    out = _run("read_widget")
    assert ran == [("youtube", "pause")], ran
    assert out and out[0]["executed"] == "widget_data"


def test_a_read_alone_runs_nothing_beside_it(monkeypatch):
    ran = _wire(monkeypatch)
    assert _run("read_widget", [CALLS[1]]) == [] and ran == []


def test_a_data_op_turn_is_not_run_twice(monkeypatch):
    ran = _wire(monkeypatch)
    assert _run("widget_data") == [] and ran == []
