"""Modifying a SHIPPED widget edits a FORK, never engine source (V2-515, phase 2).

Before: `modify_widget` resolved the folder through `dir_for` and handed the headless agent the SHIPPED
folder itself — the edit rewrote repo source in place, and `_validate(stamp_origin=True)` then relabelled
the shipped manifest `origin:"user"` (a measured 2026-08-28 incident relabelled 15 shipped widgets in one
harness run). Now the edit lands on a copy in the generated root; the copy shadows the original everywhere,
the shipped folder keeps receiving engine updates untouched underneath, and a failed FIRST edit discards
the fork so the shipped version simply resurfaces.
"""
from __future__ import annotations

import os

import pytest

from widgets import generator, paths, runtime


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    runtime.invalidate()
    yield tmp_path
    paths.forget_modules("clock")
    runtime.invalidate()


def _read(p: str) -> str:
    return open(p, encoding="utf-8").read()


def test_the_validator_never_stamps_a_shipped_manifest(lab):
    """`make test-widgets` runs this same validator over the whole catalog; with `stamp_origin=True` it once
    relabelled 15 shipped widgets as user-created. A manifest under repo source is read, never rewritten."""
    shipped_man = os.path.join(paths.BUILTIN_ROOT, "clock", "manifest.json")
    before = _read(shipped_man)
    generator._validate("clock", stamp_origin=True)
    assert _read(shipped_man) == before
