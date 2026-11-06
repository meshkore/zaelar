"""`tests/runs/` is pruned by age, and only what is disposable (2026-11-05: 45 GB that nobody had ever pruned)."""
from __future__ import annotations

import os
from pathlib import Path

from tests.platform import retention

DAY = 86400


def _touch(p: Path, age_days: float, now: float, *, as_dir: bool = False) -> Path:
    if as_dir:
        p.mkdir(parents=True, exist_ok=True)
        (p / "payload.bin").write_bytes(b"x" * 10)
        os.utime(p / "payload.bin", (now - age_days * DAY, now - age_days * DAY))
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * 10)
    os.utime(p, (now - age_days * DAY, now - age_days * DAY))
    return p


def _root(tmp_path: Path, now: float) -> Path:
    root = tmp_path / "runs"
    _touch(root / "20260801-103443-memory-aaaaaa", 30, now, as_dir=True)
    _touch(root / "20261101-120000-all-bbbbbb", 2, now, as_dir=True)
    _touch(root / "legacy-agent", 60, now, as_dir=True)
    _touch(root / "watchdog-20260901-000000.json", 40, now)
    _touch(root / "watchdog-20261104-000000.json", 1, now)
    uc = root / "use_cases"
    _touch(uc / "sandbox" / "20260818-182233-es", 50, now, as_dir=True)
    _touch(uc / "sandbox" / "20261104-010101-en", 1, now, as_dir=True)
    _touch(uc / "videos" / "old.webm", 20, now)
    _touch(uc / "lab" / "20260901-aaaa", 20, now, as_dir=True)
    _touch(uc / "report_20260817-085715.md", 20, now)
    _touch(uc / "pending" / "round.json", 90, now)
    _touch(uc / "supervisor" / "state.json", 90, now)
    _touch(uc / "CID.json", 90, now)
    return root


def test_old_entries_go_and_recent_ones_stay(tmp_path):
    now = 1_800_000_000.0
    root = _root(tmp_path, now)
    res = retention.prune(root, days=7, now=now)
    assert res["removed"] == 7 and res["bytes"] > 0
    assert not (root / "20260801-103443-memory-aaaaaa").exists()
    assert not (root / "legacy-agent").exists()
    assert not (root / "watchdog-20260901-000000.json").exists()
    assert not (root / "use_cases" / "sandbox" / "20260818-182233-es").exists()
    assert not (root / "use_cases" / "videos" / "old.webm").exists()
    assert not (root / "use_cases" / "lab" / "20260901-aaaa").exists()
    assert not (root / "use_cases" / "report_20260817-085715.md").exists()
    assert (root / "20261101-120000-all-bbbbbb").is_dir()
    assert (root / "watchdog-20261104-000000.json").exists()
    assert (root / "use_cases" / "sandbox" / "20261104-010101-en").is_dir()


def test_the_harness_state_and_the_latest_run_are_never_pruned(tmp_path):
    """`pending/`, `supervisor/` and `CID.json` are the harness's memory, and the newest run directory is what
    the Observatory's keepalive serves — both stay whatever their age."""
    now = 1_800_000_000.0
    root = _root(tmp_path, now)
    for p in root.iterdir():            # age EVERYTHING past the cutoff; the newest stays the newest
        if p.is_dir():
            age = 20 if p.name == "20261101-120000-all-bbbbbb" else 30
            os.utime(p, (now - age * DAY, now - age * DAY))
    res = retention.prune(root, days=7, now=now)
    assert (root / "use_cases" / "pending" / "round.json").exists()
    assert (root / "use_cases" / "supervisor" / "state.json").exists()
    assert (root / "use_cases" / "CID.json").exists()
    assert res["kept_latest"] == "20261101-120000-all-bbbbbb"
    assert (root / "20261101-120000-all-bbbbbb").is_dir()
    assert not (root / "20260801-103443-memory-aaaaaa").exists()


def test_dry_run_counts_and_deletes_nothing(tmp_path):
    now = 1_800_000_000.0
    root = _root(tmp_path, now)
    before = sorted(str(p) for p in root.rglob("*"))
    res = retention.prune(root, days=7, dry_run=True, now=now)
    assert res["removed"] == 7
    assert sorted(str(p) for p in root.rglob("*")) == before


def test_a_missing_root_is_a_no_op(tmp_path):
    assert retention.prune(tmp_path / "nope", days=7) == {"removed": 0, "bytes": 0, "kept_latest": ""}
