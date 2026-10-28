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

import pathlib

from nucleo.flash import close_guards as CG

ENGINE = pathlib.Path(__file__).resolve().parents[4]
SAID = "Y del informe quítame los híbridos, solo eléctricos puros, que si no al final no es lo que quiero."


def test_a_worker_call_takes_the_order():
    assert CG.taken_elsewhere({"send_to_worker"}) and CG.taken_elsewhere(["answer_worker"])
    assert CG.taken_elsewhere({"fullscreen_widget"})                       # the guard it already had
    assert not CG.taken_elsewhere(set()) and not CG.taken_elsewhere(["widget_data"])


def test_the_voice_close_backstop_asks_it_and_the_worker_call_marks_it():
    lanes = (ENGINE / "nucleo/flash/post_stream_lanes.py").read_text(encoding="utf-8")
    assert "_closeg.taken_elsewhere(_tool_fired)" in lanes
    calls = (ENGINE / "nucleo/flash/tool_executor_calls.py").read_text(encoding="utf-8")
    assert 'fired.add("send_to_worker")' in calls and 'fired.add("answer_worker")' in calls
