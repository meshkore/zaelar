"""Retention of `tests/runs/` — the diary is disposable, and until 2026-11-05 nothing ever pruned it.

Every run leaves something under `tests/runs/`: a run directory per `python -m tests run`, a `watchdog-*.json`
per sweep, and — the bulk of it — one KEPT sandbox workspace per use-case round (`use_cases/sandbox/<stamp>-<lang>`:
the engine's DB, its widget data, a whole Chromium profile), kept on purpose so the operator can watch the round and
read its evidence afterwards. Kept FOREVER was never a decision. Measured 2026-11-05: 2.664 sandboxes, 42 GB of the
45 GB the folder weighed, for rounds whose verdicts had long been copied to the scoreboard.

Policy: everything older than `DAYS` goes, except the newest run directory (the Observatory's keepalive serves it)
and the harness's own state (`use_cases/pending`, `use_cases/supervisor`, `use_cases/CID.json`). What a round needs
after a week lives elsewhere — `tests/use_cases/status.json`, an incident in the inbox, the ledger. `prune()` runs at
the start of every sandbox batch and every watchdog sweep; by hand:
`./.venv/bin/python -m tests.platform.retention [--days N] [--dry-run] [--root PATH]`.
"""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2]
RUNS = ENGINE / "tests" / "runs"
DAYS = 7

#: Under `use_cases/`, what is pruned (a dir of dirs or files, by entry) and what is never touched.
_USE_CASES_PRUNED = ("sandbox", "videos", "lab")
_USE_CASES_KEPT = ("pending", "supervisor", "CID.json")


def _mtime(p: Path) -> float:
    try:
        return p.lstat().st_mtime
    except OSError:
        return time.time()


def _remove(p: Path, dry_run: bool) -> int:
    """Delete one entry, return the bytes it held. Symlinks are unlinked, never followed."""
    size = _size(p)
    if dry_run:
        return size
    try:
        if p.is_symlink() or p.is_file():
            p.unlink()
        else:
            shutil.rmtree(p, ignore_errors=True)
    except OSError:
        return 0
    return size


def _size(p: Path) -> int:
    if p.is_symlink() or p.is_file():
        return _stat_size(p)
    total = 0
    for q in p.rglob("*"):
        if q.is_file() and not q.is_symlink():
            total += _stat_size(q)
    return total


def _stat_size(p: Path) -> int:
    try:
        return p.lstat().st_size
    except OSError:
        return 0


def prune(root: Path = RUNS, *, days: int = DAYS, dry_run: bool = False, now: float | None = None) -> dict:
    """Remove what is older than `days`. Returns {"removed": n, "bytes": b, "kept_latest": name}."""
    root = Path(root)
    if not root.is_dir():
        return {"removed": 0, "bytes": 0, "kept_latest": ""}
    cutoff = (now if now is not None else time.time()) - days * 86400
    victims: list[Path] = []

    run_dirs = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and p.name != "use_cases"),
                      key=_mtime)
    latest = run_dirs[-1].name if run_dirs else ""
    victims += [p for p in run_dirs[:-1] if _mtime(p) < cutoff]
    victims += [p for p in root.glob("watchdog-*.json") if _mtime(p) < cutoff]

    uc = root / "use_cases"
    if uc.is_dir():
        for sub in _USE_CASES_PRUNED:
            d = uc / sub
            if d.is_dir():
                victims += [p for p in d.iterdir() if _mtime(p) < cutoff]
        victims += [p for p in uc.glob("report_*") if p.is_file() and _mtime(p) < cutoff]

    removed, freed = 0, 0
    for p in victims:
        if p.name in _USE_CASES_KEPT and p.parent == uc:
            continue
        freed += _remove(p, dry_run)
        removed += 1
    return {"removed": removed, "bytes": freed, "kept_latest": latest}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prune tests/runs/ by age.")
    ap.add_argument("--days", type=int, default=DAYS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", type=Path, default=RUNS)
    args = ap.parse_args(argv)
    res = prune(args.root, days=args.days, dry_run=args.dry_run)
    verb = "would remove" if args.dry_run else "removed"
    print(f"retention: {verb} {res['removed']} entries older than {args.days}d "
          f"({res['bytes'] / 1e9:.1f} GB) under {args.root}; kept latest run {res['kept_latest'] or '—'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
