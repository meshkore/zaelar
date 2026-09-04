"""A SYSTEM widget is never deleted from disk — it is hidden (V2-515, phase 3).

Measured 2026-08-30: a use-case lab asked to delete a widget, `lifecycle.delete_widget` resolved the
folder through `dir_for` and rmtree'd ENGINE SOURCE — `widgets/clock` and `widgets/musica` left the
git tree and had to be restored by hand. The rule now reads the FOLDER (`paths.is_repo_source`), not
the manifest: a manifest field is written by the very code being guarded against.

"Delete" still means GONE from the catalog: the shipped folder stays on disk (so engine updates keep
reaching it, and restore can bring it back) while its id is HIDDEN — filtered out of the catalog, and
with it out of identify(), the registry, and the brain's brief.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

from widgets import hidden, lifecycle, paths, runtime


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """An isolated workspace + a lifecycle whose side channels (memory, SSE, store) cannot touch the
    operator's real data. The BUILTIN root stays the real one on purpose: repo-source protection is
    exactly what is under test."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(lifecycle, "_mem_write", lambda text, importance, wid="": None)
    monkeypatch.setattr(lifecycle, "_emit_widget", lambda action, w, src="system": None)
    monkeypatch.setattr(lifecycle.store, "delete", lambda wid: None)
    runtime.invalidate()
    yield tmp_path
    hidden.unhide("clock")
    runtime.invalidate()


def _fork(tmp_path, wid: str) -> str:
    folder = tmp_path / "widgets" / wid
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"id": wid, "title": wid, "keywords": [wid]}),
                                          encoding="utf-8")
    (folder / "widget.js").write_text("export function render(){}", encoding="utf-8")
    return str(folder)


def test_deleting_a_shipped_widget_hides_it_and_keeps_the_files(lab):
    shipped = os.path.join(paths.BUILTIN_ROOT, "clock")
    res = asyncio.run(lifecycle.delete_widget("clock"))
    assert res["ok"] is True
    assert os.path.isdir(shipped)                              # the FILES survive — engine source
    assert "clock" in hidden.ids()
    assert "clock" not in {w.get("id") for w in runtime.catalog()}   # …but the brain no longer knows it


def test_deleting_a_fork_removes_the_fork_and_hides_the_shipped_one(lab):
    """The user who forked `clock` and now deletes it means GONE — not "back to stock". The fork's
    files go; the shipped counterpart stays on disk but leaves the catalog with it."""
    fork = _fork(lab, "clock")
    runtime.invalidate()
    res = asyncio.run(lifecycle.delete_widget("clock"))
    assert res["ok"] is True
    assert not os.path.isdir(fork)                             # the user's own copy is really deleted
    assert os.path.isdir(os.path.join(paths.BUILTIN_ROOT, "clock"))
    assert "clock" in hidden.ids()
    assert "clock" not in {w.get("id") for w in runtime.catalog()}


def test_deleting_a_purely_generated_widget_still_removes_it(lab):
    """No shipped counterpart → today's behaviour, untouched: the folder dies and nothing is hidden."""
    wid = "tmptest-solo-generado"
    folder = _fork(lab, wid)
    runtime.invalidate()
    res = asyncio.run(lifecycle.delete_widget(wid))
    assert res["ok"] is True
    assert not os.path.isdir(folder)
    assert wid not in hidden.ids()


def test_is_repo_source_reads_the_folder_not_the_manifest(lab):
    assert paths.is_repo_source(os.path.join(paths.BUILTIN_ROOT, "clock"))
    assert not paths.is_repo_source(os.path.join(paths.generated_root(), "clock"))
    assert not paths.is_repo_source("")


def test_on_self_host_the_user_yard_never_counts_as_source(monkeypatch):
    """The generated root lives INSIDE the builtin one on self-host (`widgets/_user/`) — a bare prefix
    check on BUILTIN_ROOT would claim the forks too and make them undeletable."""
    monkeypatch.delenv("ZAELAR_WORKSPACE", raising=False)
    assert not paths.is_repo_source(os.path.join(paths.BUILTIN_ROOT, "_user", "clock"))
    assert paths.is_repo_source(os.path.join(paths.BUILTIN_ROOT, "clock"))
