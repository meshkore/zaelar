"""A `[[show:X]]` tag records WHICH card it showed, as the `show_widget` tool path does.

Measured 2026-09-27 (demo pass v7, M1): «Show me a chart of Apple stock today» — the model wrote `[[show:markets]]`
and «Here's Apple's chart for today». The tag path set `acted["widget"]` but never `acted["widget_id"]`, and the
after-show repair (`card_commission.after_show`, the pass that adds `show {symbol: AAPL}`) is gated on that id, so
it never ran: the Markets card came up EMPTY and «the last month instead» then failed on «no chart on screen».

SOURCE guard, like its neighbours: the tag path lives inside `_run_inner`'s closure.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[4] / "voice" / "engine" / "llm" / "providers" / "nucleo.py"


def test_the_after_show_repair_is_still_gated_on_that_id():
    """The premise: if the repair stopped reading `widget_id`, this guard would protect nothing."""
    text = _vts.read(SRC)
    assert re.search(r'if acted\.get\("widget_id"\) and not data_done\["v"\]', text)


def test_a_tag_show_resolves_to_the_open_card():
    """Verification 2026-09-27: `[[show:results]]` over the open monitor sheet opened the empty base beside it."""
    text = _vts.read(SRC)
    i = text.index('lambda: _show_guard_target(text, brain._window, brain._last_action)')   # V2-807 T-06
    j = text.index('GUARD anti-clutter', i)
    assert "_show_target_instance(_tid" in text[i:j]
