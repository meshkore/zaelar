"""A reset reaches a tab that stayed open (V2-773).

`make reset` bumps the wipe epoch and restarts the engine. The epoch used to be read at BOOT only, so the
operator's tab, open across the reset, came back with every old card still on it and re-reported them to the
restarted server as open — the ghosts were back in the server's canvas state before anyone typed a word
(measured 2026-09-27: four result sheets and a document on a «blank» desktop). The SSE stream re-opens
exactly when the engine is back, and that re-open now runs the boot's own takeover again.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_reset_reaches_a_tab_that_stayed_open.mjs")
SSE = Path("frontend/app/services/sse.js")
MAIN = Path("frontend/app/main.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_reopen_of_the_stream_runs_the_reset_takeover():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_stream_open_handler_is_wired_to_the_sweep():
    """The seam is only worth something if `onopen` calls it with a COUNTER and the real takeover. A seam that
    exists and is never reached is the V2-741 shape: paid for, unread."""
    src = SSE.read_text(encoding="utf-8")
    i_open = src.index("es.onopen = () => {")
    i_end = src.index("};", i_open)
    body = src[i_open:i_end]
    assert "sweepOnReopen(++_opens, () => takeoverOnReset(browserTakeoverArgs()))" in body, (
        "the re-open must run the SAME takeover the boot runs, with the browser's own arguments")


def test_both_callers_share_one_set_of_arguments():
    """Two hand-written copies of «fetch the epoch, no cache» is how one of them ends up reading a cached
    epoch and never wiping. main.js and sse.js both go through `browserTakeoverArgs()`."""
    assert "firstRun.takeoverOnReset(firstRun.browserTakeoverArgs())" in MAIN.read_text(encoding="utf-8")
    assert '"/api/desktop/epoch"' not in MAIN.read_text(encoding="utf-8"), "the URL has one owner: first-run.js"
