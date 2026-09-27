"""«Close the results» closes the sheet unless an errand is delivering INTO that sheet.

Measured 2026-09-27 (demo pass v6, S4): a Telegram follow-up errand was live — nothing to do with the sheet on
screen — and the deterministic close stepped aside because ANY worker counted as «live work behind the results».
The model got the turn, promised «Done, the results sheet is closed» without calling anything, and the promise
repair ran the previous turn's failed `detail` instead. The sheet stayed on screen.
"""
from __future__ import annotations

from types import SimpleNamespace

from nucleo import dispatch
from nucleo.actionmap import executor


def _live(tid, sheet="", surface="lista"):
    return SimpleNamespace(task_id=tid, status="running", sheet=sheet, surface=surface)


def _close(monkeypatch, open_cards):
    from server import voice_api
    monkeypatch.setattr(voice_api, "open_instances", lambda: open_cards)
    seen = []
    ok = executor.execute({"do": "close_widget", "widget": "results"},
                          lambda kind, label, **k: seen.append((label, (k.get("extra") or {}).get("id"))),
                          phrase="Close the results.")
    return ok, seen


def test_an_unrelated_live_errand_does_not_block_the_close(monkeypatch):
    monkeypatch.setattr(dispatch, "_SESSIONS", {"a": _live("a", sheet="", surface="none")})
    ok, seen = _close(monkeypatch, ["results::e6e498-7"])
    assert ok and ("close", "results::e6e498-7") in seen, seen


def test_an_errand_delivering_into_that_sheet_still_blocks_it(monkeypatch):
    monkeypatch.setattr(dispatch, "_SESSIONS", {"b": _live("b", sheet="e6e498-7")})
    ok, seen = _close(monkeypatch, ["results::e6e498-7"])
    assert ok is False and not seen, "closing it would orphan the errand writing into it"


def test_an_errand_on_another_sheet_does_not_block_this_one(monkeypatch):
    monkeypatch.setattr(dispatch, "_SESSIONS", {"c": _live("c", sheet="e6e498-9")})
    ok, seen = _close(monkeypatch, ["results::e6e498-7"])
    assert ok and ("close", "results::e6e498-7") in seen, seen
