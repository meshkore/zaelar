"""A sure `canvas = show` on an order, with nothing called, brings up the card the phrase names.

Measured 2026-09-27 (verification after the demo pass): «Show me the monitors.» — canvas=show 0.98, request_type
order 0.98 — the model said «Bringing the monitor comparison back up» and called nothing. The backstop that shows
the named card only woke for the verb table's promises («te lo abro»), and «bringing it back up» is not in it; the
screen stayed empty while the reply said the sheet was up, three turns running.
"""
import re
import threading
from pathlib import Path

from nucleo.flash import direct_action as _da, turn_brief as _tb

SRC = Path(__file__).resolve().parents[3] / "voice" / "engine" / "llm" / "providers" / "nucleo.py"


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


def test_the_promise_backstop_wakes_on_the_verdict_and_identifies_by_it():
    src = SRC.read_text(encoding="utf-8")
    gate = re.search(r"if \(_no_tool and spoken_text\n.*?and not _router\.asks_for_missing_detail\(spoken_text\)\):",
                     src, re.S)
    assert gate and "_direct_action.verdict_shows(_brief)" in gate.group(0)
    assert re.search(r"_pw = \(_identify\(_op_text\) if \(_router\.looks_like_show_strict\(_op_text\) or "
                     r"_direct_action\.verdict_shows\(_brief\)\)", src)


def test_the_backstop_shows_the_card_not_the_bare_piece():
    """Verification re-run: the backstop opened bare `results` — empty — while the monitors lived on
    `results::94b220-ls1`; «Open the best value option» then failed on the empty base."""
    src = SRC.read_text(encoding="utf-8")
    i = src.index('_pw = (_identify(_op_text) if')
    j = src.index('🪟 show por backstop de promesa', i)
    assert "_show_target_instance(_pw, _op_text" in src[i:j]
