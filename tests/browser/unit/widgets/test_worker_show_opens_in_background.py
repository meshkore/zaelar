"""A worker-commissioned card opens WITHOUT taking focus (fix04, session 6d19df41).

The operator: «Hey. Why are you open the documents right now? I set open my
email». A ghost "Scarborough" errand's `documento` sheet (show src `worker:1`)
came to the FRONT over his email flow. The mechanism: `sse.js` marks
worker-src shows as `background:true`; desktop `show()` then places the card
without `_bringFront`, and mobile Deck mounts it without `_goTo`. His own
voice-ordered shows (flash/sourceless) still front; the canvas echo stays
silent (V2-261).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_worker_show_opens_in_background.mjs")
DESKTOP = Path("frontend/app/widgets/desktop.js")
DECK = Path("frontend/mobile/app/shell/Deck.js")
SSE = Path("frontend/app/services/sse.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_worker_show_opens_but_does_not_take_focus():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def _method(src: str, start: str, end: str) -> str:
    return src[src.index(start):src.index(end)]


def test_desktop_show_never_fronts_a_background_card():
    """Every `_bringFront` inside desktop `show()` answers to `background`.

    A source test cannot say the card stays down — the .mjs mounts only the
    SSE host contract, not the canvas — so this pins the other half: no
    `_bringFront` in `show()` may run for a background card.
    """
    body = _method(DESKTOP.read_text(encoding="utf-8"),
                   "async show(rawId,", "async _showActivity(")
    calls = [l.strip() for l in body.splitlines() if "_bringFront(" in l]
    # the pointerdown REGISTRATION is not a front — it only says clicks front later, as always
    calls = [l for l in calls if "=>" not in l]
    assert len(calls) == 3, f"show() must front in exactly 3 places, found {calls}"
    assert all("if(!background)" in l.replace(" ", "") for l in calls), \
        f"every front inside show() must answer to `background`: {calls}"


def test_deck_show_never_switches_to_a_background_card():
    body = _method(DECK.read_text(encoding="utf-8"),
                   "let baseId, id, wq;", "close(id) {")
    assert "if (!background) this._goTo" in body
    bare = [l for l in body.splitlines()
            if "this._goTo(" in l and "if (!background)" not in l]
    assert not bare, f"Deck.show() switches cards past the guard: {bare}"


def test_worker_provenance_is_detected_by_prefix_not_a_list():
    """`worker:<anything>` is background — a new worker kind must not need a new rule."""
    src = SSE.read_text(encoding="utf-8")
    assert "/^worker:/" in src, "the gate must match the worker: prefix"
    assert "background: _bg" in src, "the verdict must travel to the host as `background`"
