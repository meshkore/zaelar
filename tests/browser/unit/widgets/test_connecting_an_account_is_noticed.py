"""Exposes the `ctx.connect` contract to pytest (V2-700). The reason is in the .mjs, which runs the canvas's
OWN source — the three methods are sliced out of `desktop.js` verbatim, so drift in the shipped file shows up
here instead of being quietly re-typed into the test.

The server half (the callback page, the `widget/data` announcement) is
`tests/connectors/unit/test_a_connected_account_tells_the_card_it_landed.py`.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_connecting_an_account_is_noticed.mjs")
ENGINE = Path(__file__).resolve().parents[4]


def test_connecting_an_account_opens_a_popup_and_is_noticed() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to run the canvas's own source")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_widget_hand_rolls_its_own_consent_window() -> None:
    """The contract with every widget, and the reason the operator saw two behaviours for one idea: five
    copies of «open a window and hope» had drifted into a popup in the agenda and a whole tab in contacts.

    A widget names an action; the CANVAS owns the window and the watching. This is the ratchet that keeps
    the sixth connector from re-inventing it — and it is a source scan on purpose, because the defect is
    the existence of the code, not its behaviour.
    """
    offenders = []
    for js in sorted((ENGINE / "widgets").glob("*/widget.js")):
        src = js.read_text(encoding="utf-8")
        for i, line in enumerate(src.splitlines(), 1):
            if "window.open(" not in line:
                continue
            # Opening a link the operator asked to SEE (a file, a video, a Drive page) is not a consent
            # flow. What may not live in a widget is opening a BLANK window to fill with an auth URL.
            if '""' in line or "''" in line:
                offenders.append(f"{js.parent.name}/widget.js:{i}")
    assert offenders == [], (
        "these open a blank window to drive an OAuth consent themselves; use ctx.connect(...) — " + str(offenders))


def test_the_canvas_offers_connect_on_the_ctx_every_widget_gets() -> None:
    src = (ENGINE / "frontend" / "app" / "widgets" / "desktop.js").read_text(encoding="utf-8")
    assert "connect:(action, payload, opts)=>desk._connectFlow(" in src, "ctx.connect is the seam"
    assert "_watchConnect" in src and "refreshData" in src, "and it ends in a re-read, never in a claim"
