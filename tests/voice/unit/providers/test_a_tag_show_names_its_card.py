"""A `[[show:X]]` tag records WHICH card it showed, as the `show_widget` tool path does.

Measured 2026-09-27 (demo pass v7, M1): «Show me a chart of Apple stock today» — the model wrote `[[show:markets]]`
and «Here's Apple's chart for today». The tag path set `acted["widget"]` but never `acted["widget_id"]`, and the
after-show repair (`card_commission.after_show`, the pass that adds `show {symbol: AAPL}`) is gated on that id, so
it never ran: the Markets card came up EMPTY and «the last month instead» then failed on «no chart on screen».

SOURCE guard, like its neighbours: the tag path lives inside `_run_inner`'s closure.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[4] / "voice" / "engine" / "llm" / "providers" / "nucleo.py"


def _tag_path() -> str:
    text = SRC.read_text(encoding="utf-8")
    m = re.search(r'acted\["widget"\] = True\n(.*?)emit\("widget", action, text=', text, re.S)
    assert m, "the tag emit path moved — repoint this guard"
    return m.group(1)


def test_a_tag_show_records_the_card_it_showed():
    block = _tag_path()
    assert 'acted["widget_id"]' in block and 'action == "show"' in block, \
        "without the id, the after-show repair never runs for a tag show"


def test_the_after_show_repair_is_still_gated_on_that_id():
    """The premise: if the repair stopped reading `widget_id`, this guard would protect nothing."""
    text = SRC.read_text(encoding="utf-8")
    assert re.search(r'if acted\.get\("widget_id"\) and not data_done\["v"\]', text)
