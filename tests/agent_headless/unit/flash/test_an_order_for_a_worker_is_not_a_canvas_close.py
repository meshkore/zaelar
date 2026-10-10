"""An order the model routed to a live worker is not a canvas close (three-tasks-at-once, 2026-10-10).

Measured in sandbox 20261010-145227-es. With the report, the monitor search and the game in flight, the operator
said «Y del informe quítame los híbridos, solo eléctricos puros». The model did the right thing — `send_to_worker`
to the report, «Restricción nueva del operador: solo eléctricos puros…» — and the turn's action became
`canvas:close:results`: «quita» is a close verb, the results sheet was the one card open, and the close backstop
reached it by context. In the text channel that also meant the worker message was never sent, because the action
the executor ran was the close.

`removing a row never closes its card` (V2-781) does not cover it: no row is named. The class is that the model
already decided where the order goes. A sentence it routed to a worker is an order for that worker, and the
close backstop — which exists for a turn where the model closed nothing and SAID it did — has nothing to complete.
Both channels ask the same predicate (`close_guards.taken_elsewhere`).
"""
from __future__ import annotations

import asyncio
import pathlib
import types

from nucleo.flash import close_guards as CG

ENGINE = pathlib.Path(__file__).resolve().parents[4]
SAID = "Y del informe quítame los híbridos, solo eléctricos puros, que si no al final no es lo que quiero."


def test_a_worker_call_takes_the_order():
    assert CG.taken_elsewhere({"send_to_worker"}) and CG.taken_elsewhere(["answer_worker"])
    assert CG.taken_elsewhere({"fullscreen_widget"})                       # the guard it already had
    assert not CG.taken_elsewhere(set()) and not CG.taken_elsewhere(["widget_data"])


def test_the_text_channel_keeps_the_worker_call(monkeypatch):
    from memory import api as memapi
    from nucleo.flash import probe_mirrors as PM
    from widgets import runtime as rt
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": ["results"]})
    monkeypatch.setattr(rt, "identify", lambda text, open_ids=None, **k: {"match": "results", "by_context": True})
    calls = [{"name": "send_to_worker", "args": {"which": "el informe", "message": "solo eléctricos puros"}}]
    tags: list = []
    out = asyncio.run(PM.mirror_the_voice_backstops(
        _akp=False, _cw=None, _hw=True, _router=__import__("nucleo.flash.router", fromlist=["x"]), _rt=None,
        _sp=None, _tbrief=None, action="send_to_worker", canvas_h=None,
        dialog=__import__("nucleo.flash.dialog", fromlist=["x"]), names=["send_to_worker"], operator_text=SAID,
        sess=types.SimpleNamespace(window=[], last_action=""), spec=None, speech=None,
        spoken="Hecho, solo eléctricos puros, fuera híbridos.", tags=tags, text=SAID, tool_calls=calls))
    assert out.get("action", "send_to_worker") == "send_to_worker", out.get("action")
    assert not [t for t in tags if t["action"] == "close"], tags


def test_the_voice_close_backstop_asks_it_and_the_worker_call_marks_it():
    lanes = (ENGINE / "nucleo/flash/post_stream_lanes.py").read_text(encoding="utf-8")
    assert "_closeg.taken_elsewhere(_tool_fired)" in lanes
    calls = (ENGINE / "nucleo/flash/tool_executor_calls.py").read_text(encoding="utf-8")
    assert 'fired.add("send_to_worker")' in calls and 'fired.add("answer_worker")' in calls


def test_the_text_channel_sends_each_message_to_the_worker_it_names(monkeypatch):
    """The other half of «the worker message was never delivered»: the text channel sent only the FIRST
    `send_to_worker` and sent it to EVERY live worker (`which=""`). Measured on the EN twin (20261010-145237-en):
    «the monitor, no more than $150» reached the REPORT's worker, and the game's «jump higher» reached nobody. The
    voice executor sends each call to its own `which`; so does this one now."""
    from nucleo import dispatch
    from nucleo.flash import probe_after as PA
    sent: list = []
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, msg: sent.append((which, msg)))
    calls = [{"name": "send_to_worker", "args": {"which": "the monitor search", "message": "max $150"}},
             {"name": "widget_data", "args": {}},
             {"name": "send_to_worker", "args": {"which": "the platform game widget", "message": "jump higher"}}]
    out = PA._send_each(calls, "And the monitor, no more than $150. How's everything going?")
    assert sent == [("the monitor search", "max $150"), ("the platform game widget", "jump higher")]
    assert out == {"executed": "inject", "sent": 2, "to": []}   # nothing live here, so nobody to name back
