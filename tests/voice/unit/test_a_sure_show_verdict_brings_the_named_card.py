"""A sure `canvas = show` on an order, with nothing called, brings up the card the phrase names.

Measured 2026-09-27 (verification after the demo pass): «Show me the monitors.» — canvas=show 0.98, request_type
order 0.98 — the model said «Bringing the monitor comparison back up» and called nothing. The backstop that shows
the named card only woke for the verb table's promises («te lo abro»), and «bringing it back up» is not in it; the
screen stayed empty while the reply said the sheet was up, three turns running.
"""
import threading

from nucleo.flash import direct_action as _da

from nucleo.turn import brief as _tb



def _brief(answers):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [],
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


def test_a_sure_show_on_an_order_reads_as_a_show():
    assert _da.verdict_shows(_brief({_tb.CANVAS_KEY: ("show", 0.98), _tb.REQUEST_KEY: ("order", 0.98)}))


def test_unsure_or_not_an_order_does_not():
    assert not _da.verdict_shows(_brief({_tb.CANVAS_KEY: ("show", 0.3), _tb.REQUEST_KEY: ("order", 0.98)}))
    assert not _da.verdict_shows(_brief({_tb.CANVAS_KEY: ("show", 0.98), _tb.REQUEST_KEY: ("question", 0.9)}))
    assert not _da.verdict_shows(_brief({_tb.CANVAS_KEY: ("neither", 0.9), _tb.REQUEST_KEY: ("order", 0.9)}))
