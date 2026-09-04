"""A widget event reaches the pills that assert the widget's own state (V2-577).

Measured 2026-09-04 (V2-576 cause B, operator session `0a93de06`): pill 1165 — the birth announcement
`[widget:restaurantes-favoritos-operador] Widget 'Restaurantes favoritos' … CREATED` — stayed valid after
the widget was DELETED. The tombstone existed, but recall served birth and grave side by side, and the fix
worker read the birth first: it spent its opening move on a widget that no longer existed.

The fix rides V2-565's supersede plumbing. Lifecycle pills already carry a deterministic anchor — the
`[widget:<id>]` text prefix, written only by `widgets/lifecycle.py` — so every new lifecycle write passes
the widget's PRIOR anchored pills as `supersedes`: only the newest chapter of a widget's story stays valid,
and the superseded chain keeps the history. Pills that never declared the anchor are out of reach ON
PURPOSE: matching by content invents targets (the worker pill 1160 said «restaurantes favoritos» without
ever naming the widget id — no deterministic hook can claim it, and none tries)."""
import asyncio
import json

import pytest

from memory import api as mem
from memory import db as memdb


@pytest.fixture(autouse=True)
def _own_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _pill(wid: str, text: str) -> int:
    return mem.write_now(f"[widget:{wid}] {text}", kind="event", level="mid")


# ── the door: memory resolves the anchor, and only the anchor ─────────────────────────────────────────────
def test_the_door_returns_only_the_widgets_valid_anchored_pills():
    a = _pill("meteo", "Widget 'Meteo' was CREATED on 2026-09-04 for: weather at a glance.")
    _pill("agenda", "Widget 'Agenda' was CREATED on 2026-09-04 for: the day's appointments.")
    mem.write_now("The meteo widget shows his home town by default.", kind="pref", level="long")
    assert mem.widget_trace_ids("meteo") == [a], \
        "prose that merely MENTIONS a widget has no anchor — reaching it would be guessing"


def test_an_underscore_in_the_id_is_a_literal_not_a_wildcard():
    """SQLite LIKE treats `_` as a one-char wildcard; a widget id is a slug that may carry one. The door
    must escape it, or `mi_widget` would claim `mi-widget`'s story too."""
    good = _pill("mi_widget", "Widget 'Mi widget' was CREATED on 2026-09-04 for: keeping the shopping list.")
    _pill("mi-widget", "Widget 'Mi-widget' was CREATED on 2026-09-04 for: watching the bus timetable.")
    assert mem.widget_trace_ids("mi_widget") == [good]


# ── the chain: each lifecycle chapter supersedes the previous ones ────────────────────────────────────────
def test_the_tombstone_supersedes_the_birth_announcement():
    born = _pill("meteo", "Widget 'Meteo' was CREATED on 2026-09-01 for: weather at a glance.")
    other = _pill("agenda", "Widget 'Agenda' was CREATED on 2026-09-01 for: the day's appointments.")
    prose = mem.write_now("He checks the weather every morning before leaving.", kind="pref", level="long")
    tomb = mem.write_now("[widget:meteo] Widget 'Meteo' was DELETED on 2026-09-04 at the operator's request.",
                         kind="event", level="mid", supersedes=mem.widget_trace_ids("meteo"))
    db = memdb.get_db()
    row = db.query_one("SELECT valid, superseded_by FROM memories WHERE id=?", (born,))
    assert row["valid"] == 0 and row["superseded_by"] == tomb, \
        "a still-valid birth next to its own tombstone is exactly what sent the worker to a deleted widget"
    assert db.query_one("SELECT valid FROM memories WHERE id=?", (other,))["valid"] == 1, \
        "another widget's story is untouched"
    assert db.query_one("SELECT valid FROM memories WHERE id=?", (prose,))["valid"] == 1, \
        "unanchored prose is untouched — the hook never matches by content"


def test_a_restore_supersedes_the_tombstone():
    """Symmetry: after a restore, «it no longer exists; remind them they ordered its deletion» is the lie."""
    born = _pill("clock", "Widget 'Clock' was CREATED on 2026-09-01 for: telling the time.")
    tomb = mem.write_now("[widget:clock] Widget 'Clock' was DELETED on 2026-09-02 at the operator's request.",
                         kind="event", level="mid", supersedes=mem.widget_trace_ids("clock"))
    back = mem.write_now("[widget:clock] Widget 'Clock' was RESTORED to the shipped version on 2026-09-04.",
                         kind="event", level="mid", supersedes=mem.widget_trace_ids("clock"))
    db = memdb.get_db()
    assert db.query_one("SELECT superseded_by FROM memories WHERE id=?", (tomb,))["superseded_by"] == back
    assert db.query_one("SELECT valid FROM memories WHERE id=?", (born,))["valid"] == 0
    assert db.query_one("SELECT valid FROM memories WHERE id=?", (back,))["valid"] == 1, \
        "exactly one chapter of the story is alive at any moment"


# ── the seam: delete_widget actually walks the door ───────────────────────────────────────────────────────
def test_delete_widget_hands_the_prior_trace_to_the_write(tmp_path, monkeypatch):
    from widgets import lifecycle, runtime
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    folder = tmp_path / "widgets" / "probe"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"id": "probe", "title": "Probe"}), encoding="utf-8")
    runtime.invalidate()
    born = _pill("probe", "Widget 'Probe' was CREATED on 2026-09-04 for: probing the seam.")
    calls: list = []
    monkeypatch.setattr(lifecycle, "_emit_widget", lambda *a, **k: None)
    monkeypatch.setattr(lifecycle.store, "delete", lambda wid: None)
    monkeypatch.setattr(mem, "write", lambda text, **kw: calls.append((text, kw)))
    try:
        res = asyncio.run(lifecycle.delete_widget("probe"))
    finally:
        runtime.invalidate()
    assert res["ok"] is True
    text, kw = calls[-1]
    assert text.startswith("[widget:probe]") and "DELETED" in text
    assert kw.get("supersedes") == [born], \
        "the tombstone must name the pills it outdates — without it recall serves birth and grave side by side"
