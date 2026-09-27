"""A results sheet nothing stands behind is a ghost, and a ghost is never restored (V2-773, 2026-09-27).

After `make reset` the operator's tab, open across it, re-reported its old cards and the server saved them
again in `canvas_layout`; every tab with no desktop of its own then rehydrated four empty «Resultados» — and
their own reads recreated their folders on disk (bare, no `state.json`). A sheet is real when its data is on
disk or its errand is live; the server prunes the rest on read AND on write, and the desktop applies the same
judgment to its own localStorage list through the `sheets` the layout answer carries."""
from __future__ import annotations

import asyncio
import json
import os
import pathlib

import pytest

from memory import db as memdb
from memory import embeddings as mememb

DESKTOP = pathlib.Path("frontend/app/widgets/desktop.js")


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def disk(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    os.makedirs(tmp_path / "results--real-1"); (tmp_path / "results--real-1" / "state.json").write_text("{}")
    os.makedirs(tmp_path / "results--bare-1")               # the folder a ghost's own read creates
    return tmp_path


def test_a_bare_folder_is_not_a_sheet(disk):
    from server import voice_api
    assert voice_api._sheet_ids_on_disk() == ["results::real-1"]


def test_the_prune_keeps_data_and_live_and_drops_the_rest(disk, monkeypatch):
    from server import voice_api
    items = [{"id": "results::real-1"}, {"id": "results::bare-1"}, {"id": "results::live-1"}, {"id": "results::gone-1"},
             {"id": "agenda"}, {"id": "navegador::t1"}]
    got = voice_api._prune_ghost_sheets(items, ["results::live-1"])
    assert [i["id"] for i in got] == ["results::real-1", "results::live-1", "agenda", "navegador::t1"], (
        "THE BUG: a sheet with nothing behind it came back on every restore")


def test_the_layout_answer_is_pruned_and_names_the_real_sheets(disk, tmp_path, monkeypatch):
    from memory import api as memapi
    from server import voice_api
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db(); memdb.get_db()
    try:
        monkeypatch.setattr(voice_api, "_live_canvas_instances", lambda: [])
        memapi.kv_set("canvas_layout", {"at": 1, "items": [{"id": "results::gone-1", "q": "gone-1"}, {"id": "results::real-1", "q": "real-1"}]})
        body = json.loads(asyncio.run(voice_api.canvas_layout()).body)
        assert [i["id"] for i in body["items"]] == ["results::real-1"]
        assert body["sheets"] == ["results::real-1"]
        # …and a tab reporting ghosts cannot put them back
        asyncio.run(voice_api.canvas_state({"open": ["results::gone-1", "results::real-1"],
                                            "layout": [{"id": "results::gone-1"}, {"id": "results::real-1"}]}))
        assert [i["id"] for i in memapi.kv_get("canvas_layout")["items"]] == ["results::real-1"]
    finally:
        memdb.reset_db()


def test_the_desktop_applies_the_same_judgment_to_its_own_list():
    src = DESKTOP.read_text(encoding="utf-8")
    restore = src[src.index("async restore()"):src.index("\n  has(id){")]
    i_srv = restore.index('fetch("/api/canvas/layout")')
    i_filter = restore.index("srv.sheets", i_srv)
    i_show = restore.index("await this.show(it.id", i_filter)
    assert i_srv < i_filter < i_show, "the ghost filter runs after the server answers and before any card is shown"
    assert 'id.startsWith("results::") && !real.has(id)' in restore
