"""V2-705 · The widget store keeps what it is about to overwrite.

2026-09-15: one `cancel_meeting {}` emptied the agenda store and «what was there?» had no answer — the store
kept nothing but its latest state, and the local-only appointments were gone for good. Every `save` now
copies the file it replaces under `<widget>/history/`, bounded, and `restore` puts one back (snapshotting
the current state first, so a restore is itself undoable). An idempotent save — the change gate that kills
the poll flood — never snapshots.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    from widgets import store as st
    monkeypatch.setattr(st, "DATA_DIR", str(tmp_path))
    st.forget("agenda-snap")
    return st


def test_the_first_save_has_nothing_to_keep(store):
    store.save("agenda-snap", {"n": 1})
    assert store.history("agenda-snap") == []


def test_a_change_keeps_the_previous_state(store):
    store.save("agenda-snap", {"n": 1})
    store.save("agenda-snap", {"n": 2})
    h = store.history("agenda-snap")
    assert len(h) == 1
    import json
    kept = json.load(open(os.path.join(store.data_dir("agenda-snap"), "history", h[0] + ".json")))
    assert kept == {"n": 1}


def test_an_identical_save_does_not_snapshot(store):
    store.save("agenda-snap", {"n": 1})
    store.save("agenda-snap", {"n": 1})
    store.save("agenda-snap", {"n": 1})
    assert store.history("agenda-snap") == []


def test_the_history_is_bounded(store):
    for i in range(store.HISTORY_KEEP + 4):
        store.save("agenda-snap", {"n": i})
    assert len(store.history("agenda-snap")) == store.HISTORY_KEEP


def test_two_saves_inside_one_millisecond_are_two_snapshots(store):
    store.save("agenda-snap", {"n": 0})
    for i in range(1, 6):
        store.save("agenda-snap", {"n": i})
    assert len(store.history("agenda-snap")) == 5


def test_restore_puts_a_snapshot_back_and_is_itself_undoable(store):
    store.save("agenda-snap", {"n": 1})
    store.save("agenda-snap", {"n": 2})
    stamp = store.history("agenda-snap")[0]
    assert store.restore("agenda-snap", stamp) == {"n": 1}
    assert store.load("agenda-snap") == {"n": 1}
    assert len(store.history("agenda-snap")) == 2, "the state replaced by the restore was kept too"
    assert store.restore("agenda-snap", "nope") is None


def test_a_failed_snapshot_never_costs_the_write(store, monkeypatch):
    store.save("agenda-snap", {"n": 1})
    monkeypatch.setattr(store, "_history_dir", lambda wid: "/dev/null/impossible")
    assert store.save("agenda-snap", {"n": 2}) == {"n": 2}
    assert store.load("agenda-snap") == {"n": 2}


def test_the_snapshot_is_taken_inside_save_before_the_replace():
    """Structural: the copy happens before `os.replace`, under the same lock — after it there is nothing left
    to copy."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets/store.py").read_text(encoding="utf-8")
    body = src[src.index("def save("):src.index("# ── the pre-mutation SNAPSHOT")]
    assert body.index("_snapshot(widget_id, p)") < body.index("os.replace(tmp, p)")
