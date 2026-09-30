"""The test map is well formed, and a node whose file is gone is RED (V2-778 F0-8, 2026-09-30).

`tests/run_testmap.py` is the source of truth for «is everything green?». The audit found three ways it could lie:

  · `_run_node` reported a node green when some of its mapped files no longer existed — only a note said so;
  · 15 files were mapped under two nodes, so one test answered two questions and a move broke both silently;
  · five node ids (`8.1b`…`8.1f`) did not follow the `N.M` shape every reader of the map assumes.

The unmapped file itself is caught by `test_a_test_outside_the_map_is_not_a_test.py`; this is the other half.
"""
from __future__ import annotations

import collections
import importlib.util
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]


def _map():
    spec = importlib.util.spec_from_file_location("_testmap", ENGINE / "tests" / "run_testmap.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_node_id_is_N_dot_M_and_unique():
    ids = [n["id"] for d in _map().DOMAINS for n in d["nodes"]]
    assert [i for i in ids if not re.fullmatch(r"\d+\.\d+", i)] == []
    assert [i for i, c in collections.Counter(ids).items() if c > 1] == []


def test_every_mapped_path_exists_and_is_mapped_once():
    nodes = [n for d in _map().DOMAINS for n in d["nodes"]]
    every = {p for n in nodes for p in n.get("paths", [])}
    assert [p for p in every if not (ENGINE / p).exists()] == []
    # A LIVE node's paths are the file its command runs, not a deterministic run: the same file may also sit
    # under the deterministic node that runs it without the service (2.68 → 3.76). Everything else, once.
    runs = collections.Counter(p for n in nodes if not n.get("live") for p in n.get("paths", []))
    assert [p for p, c in runs.items() if c > 1] == [], "a file answers ONE deterministic node of the map"


def test_a_node_with_a_missing_file_is_red(monkeypatch):
    """Behaviour, with pytest itself stubbed green: the existing file passes, the missing one must still fail it."""
    import subprocess
    tm = _map()
    monkeypatch.setattr(tm.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="1 passed", stderr=""))
    ok, note = tm._run_node(["tests/infrastructure/unit/test_the_map_is_well_formed.py",
                             "tests/this/file/does/not/exist.py"])
    assert ok is False, f"a node with one of its files gone was reported green: {note}"
