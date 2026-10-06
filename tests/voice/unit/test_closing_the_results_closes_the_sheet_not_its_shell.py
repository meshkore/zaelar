"""«close the results» closes the SHEET, not a bare shell beside it (demo pass 119, S4, 2026-10-06).

The open cards were a bare `results` shell and the one sheet `results::1e9044-ls1`; the last turn's focus was the
shell, so the close went to `results`, the reply said «closing it now», and the sheet stayed on screen. A bare shell
next to exactly ONE instance is never what he means — the sheet is the card he sees.
"""
from __future__ import annotations

import pytest

from nucleo.flash import show_target as ST


@pytest.fixture
def screen(monkeypatch):
    st = {"ids": ["results", "results::1e9044-ls1"], "focus": "results"}
    import server.voice_api as _va
    from nucleo import canvas_focus as _cf
    monkeypatch.setattr(_va, "open_instances", lambda: list(st["ids"]))
    monkeypatch.setattr(_cf, "last_turn_card", lambda same: st["focus"] if st["focus"] in same else "")
    return st


def test_a_shell_beside_one_sheet_closes_the_sheet(screen):
    assert ST.close_target("results") == "results::1e9044-ls1"


def test_two_sheets_keep_the_focus_rule(screen):
    screen["ids"] = ["results", "results::a-1", "results::b-2"]
    screen["focus"] = "results::b-2"
    assert ST.close_target("results") == "results::b-2"
