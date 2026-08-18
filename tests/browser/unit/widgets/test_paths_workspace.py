"""Where a widget's CODE lives — `widgets/paths.py` (V2-125, 2026-08-18).

The measured failure: a sandboxed use-case run generated `log-training-workouts` into the operator's REAL
`engine/widgets/`, so the NEXT run of `build-workout-tracker-widget` opened with «ya tienes ese widget» about
something the simulated user had never asked for. It was a known leak — written down in
`tests/platform/sandbox_engine.py` and deliberately left for the product, because a sandbox cannot sweep that
directory afterwards without risking the operator's own live generation.

The two properties that matter, and they pull in opposite directions:
  · a GENERATED widget is per-tenant state → it belongs under the workspace;
  · the BUILT-IN catalog must stay visible from a workspace → otherwise the sandbox sees no widgets at all
    (the reason the naive "make the catalog workspace-relative" fix was rejected in that same note).
"""
from __future__ import annotations

import json
import os

import pytest

from widgets import paths


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    return tmp_path


def test_without_a_workspace_nothing_moves(monkeypatch):
    """Every self-host install. `workspace.root()` IS the repo root, so both roots collapse into one and the
    behaviour is byte identical to before this module existed — no migration, no moved folder."""
    monkeypatch.delenv("ZAELAR_WORKSPACE", raising=False)
    assert paths.roots() == [paths.BUILTIN_ROOT]
    assert paths.new_dir("nuevo") == os.path.join(paths.BUILTIN_ROOT, "nuevo")


def test_a_generated_widget_goes_to_the_workspace(workspace):
    assert paths.new_dir("nuevo") == str(workspace / "widgets" / "nuevo")
    assert paths.BUILTIN_ROOT not in paths.new_dir("nuevo")


def test_the_builtin_catalog_is_still_visible_from_a_workspace(workspace):
    """The half that the rejected fix would have broken: isolating generation must not blind the engine to
    the widgets it ships with."""
    assert paths.dir_for("agenda") == os.path.join(paths.BUILTIN_ROOT, "agenda")
    assert paths.BUILTIN_ROOT in paths.roots()
    assert {name for name, _ in paths.iter_folders()} >= {"agenda"}


def test_a_generated_widget_shadows_a_builtin_of_the_same_id(workspace):
    folder = workspace / "widgets" / "agenda"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"id": "agenda"}), encoding="utf-8")
    assert paths.dir_for("agenda") == str(folder)          # the operator's own version wins
    ids = [name for name, f in paths.iter_folders() if name == "agenda"]
    assert ids == ["agenda"]                               # …and it is listed ONCE, not twice


def test_a_widget_that_does_not_exist_resolves_to_nothing(workspace):
    assert paths.dir_for("no-existe-en-ningun-sitio") is None
    assert paths.dir_for("") is None


def test_the_runtime_catalog_reads_widgets_from_both_roots(workspace):
    """`runtime.catalog()` is what the brain sees. A widget generated into the workspace has to appear in it
    — that is the whole point — and the built-ins have to survive alongside."""
    from widgets import runtime
    folder = workspace / "widgets" / "solo-en-workspace"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps(
        {"id": "solo-en-workspace", "title": "T", "keywords": ["k"], "entry": "widget.js"}), encoding="utf-8")
    (folder / "widget.js").write_text("export function render(){}", encoding="utf-8")
    runtime.invalidate()
    try:
        ids = {w.get("id") for w in runtime.catalog()}
        assert "solo-en-workspace" in ids
        assert "agenda" in ids
    finally:
        runtime.invalidate()


def test_a_half_built_folder_still_stays_out_of_the_catalog(workspace):
    """Unchanged rule, re-checked because the enumeration moved: a folder with a manifest but no widget.js is
    debris from a generation that died half-way, and it must never reach the brain's brief."""
    from widgets import runtime
    folder = workspace / "widgets" / "a-medio-construir"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"id": "a-medio-construir"}), encoding="utf-8")
    runtime.invalidate()
    try:
        assert "a-medio-construir" not in {w.get("id") for w in runtime.catalog()}
    finally:
        runtime.invalidate()


def test_a_rollback_can_never_delete_engine_source(workspace):
    """`generator._discard` removes a freshly-created folder that failed to validate. It must aim at the
    generated root, not at whatever `dir_for` resolves — otherwise a failed build of an id that shadows a
    built-in would delete the shipped widget."""
    from widgets import generator
    (workspace / "widgets").mkdir(parents=True, exist_ok=True)
    generator._discard("agenda")
    assert os.path.isdir(os.path.join(paths.BUILTIN_ROOT, "agenda"))
