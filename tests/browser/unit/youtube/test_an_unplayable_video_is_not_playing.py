"""A video the site refuses to embed must not count as PLAYING (V2-401).

Found by the OPERATOR's own screenshot (2026-08-27), not by the harness: the player showed "This video is
unavailable" while the engine's declared state said `videoId` set, `paused: false` — which is exactly what
`active_when` reads, so `/widgets/producing` would answer `["youtube"]` about a player that produces
nothing. The brain, the judge and the master all trust that endpoint (V2-392/V2-395 taught them to), so the
declared state lying makes every one of them lie with it.

The mechanism: `widget.js` only listened for `onStateChange` (ENDED). The IFrame API also posts `onError`
(codes 2/5/100/101/150 — 101/150 are "embedding disabled by the owner") and nobody read it. Now the widget
reports it back (`ctx.action("player_error")`), `data.py` records it, and the manifest's `active_when`
excludes it — so "is it producing?" is answered with the player's reported reality, not our intent alone.
"""
from __future__ import annotations

import json
from pathlib import Path

from widgets.producers import _clause_holds
from widgets.youtube import data as D


def _fresh(monkeypatch, tmp_path):
    saved = {}
    monkeypatch.setattr(D, "_load", lambda: dict(saved.get("db") or D._seed()))
    monkeypatch.setattr(D.store, "save", lambda wid, db: saved.update(db=dict(db)) or db)
    return saved


# ── the error is recorded ──────────────────────────────────────────────────────────────────────────────────

def test_player_error_lands_in_the_state(monkeypatch, tmp_path):
    saved = _fresh(monkeypatch, tmp_path)
    out = D.apply_action("player_error", {"code": "150"})
    assert out.get("ok") is True
    assert saved["db"]["player_error"] == "150"


def test_a_garbage_code_is_still_recorded_as_a_string(monkeypatch, tmp_path):
    """The code comes from the player via postMessage — never trusted enough to crash on."""
    saved = _fresh(monkeypatch, tmp_path)
    D.apply_action("player_error", {"code": {"weird": True}})
    assert isinstance(saved["db"]["player_error"], str) and saved["db"]["player_error"]


# ── loading something new clears it ────────────────────────────────────────────────────────────────────────

def test_loading_a_new_video_clears_the_error(monkeypatch, tmp_path):
    saved = _fresh(monkeypatch, tmp_path)
    D.apply_action("player_error", {"code": "150"})
    monkeypatch.setattr(D, "_load", lambda: dict(saved["db"]))
    D.apply_action("load", {"videoId": "abcdefghijk"})   # a direct id never touches the network
    assert not saved["db"].get("player_error"), "a fresh video must start with a clean slate"


def test_play_item_clears_it_too(monkeypatch, tmp_path):
    """Advancing the playlist plays a DIFFERENT video: the old error says nothing about it."""
    saved = _fresh(monkeypatch, tmp_path)
    db = D._seed()
    db["list"] = [{"videoId": "aaaaaaaaaaa", "title": "a", "channel": "", "published": "", "url": ""},
                  {"videoId": "bbbbbbbbbbb", "title": "b", "channel": "", "published": "", "url": ""}]
    db["player_error"] = "101"
    saved["db"] = db
    monkeypatch.setattr(D, "_load", lambda: dict(saved["db"]))
    D.apply_action("play_item", {"item": "2"})
    assert not saved["db"].get("player_error")


# ── the producing predicate excludes it ────────────────────────────────────────────────────────────────────

def test_active_when_excludes_a_player_in_error():
    man = json.loads(Path("widgets/youtube/manifest.json").read_text())
    cond = man["runtime"]["active_when"]
    assert cond.get("player_error") is False, "the manifest does not exclude a broken player from producing"
    playing = {"videoId": "x", "paused": False, "player_error": ""}
    broken = {"videoId": "x", "paused": False, "player_error": "150"}
    assert _clause_holds(playing, cond) is True
    assert _clause_holds(broken, cond) is False, "a video the site refuses to embed still counts as playing"


# ── the widget reports it (source guard: the handler is DOM plumbing, unreachable from pytest) ─────────────

def test_the_widget_listens_for_onError_and_reports_it():
    src = Path("widgets/youtube/widget.js").read_text()
    assert '"onError"' in src or "'onError'" in src, "nobody listens for the player's onError"
    assert 'player_error' in src, "the error never leaves the iframe: nobody calls the action"


def test_the_action_is_declared_in_the_manifest():
    """An undeclared action is invisible to the dispatch gate (V2-025: only DECLARED actions run)."""
    man = json.loads(Path("widgets/youtube/manifest.json").read_text())
    assert "player_error" in (man.get("actions") or {})
