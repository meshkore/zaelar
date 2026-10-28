"""The clean-clone check, as one command (refactor2710-99): what a self-hoster gets, with nothing of this machine's state.

    ./.venv/bin/python -m tests.infrastructure.clean_clone              # the committed HEAD of this repo
    ./.venv/bin/python -m tests.infrastructure.clean_clone --ref main --remote
    ./.venv/bin/python -m tests.infrastructure.clean_clone --dry-run    # print the plan, run nothing

It clones the repository into a temp dir — no `config/`, no `.meshkore/` runtime, no credentials, no `widgets/_user/` —
and, inside the clone, runs: `ruff check .`, `compileall` of every engine package, the event freezers (every
`test_*event*surviv*.py`) and `tests/infrastructure` under the watchdog. No live battery: nothing here needs the engine
running or a provider key.

The packages and the freezers are FOUND in the clone (a package is a top-level folder with `__init__.py`, minus
`tests`), so the check follows the tree instead of a list that goes stale. The interpreter is this one (its installed
packages are the «minimum installed»); `--fresh-venv` builds a venv in the clone from `requirements.txt` instead,
which needs the network and minutes. Exit code 0 only when every step passed; the summary says which one failed.

The clone lives OUTSIDE the system temp dir (`--dest-root`, default `~/.cache/zaelar/clean-clone`). Measured on the first
run: a clone under `$TMPDIR` shares its parent with every pytest `tmp_path`, so a test that runs pytest on a generated
file (the watchdog's own) got that crowded temp dir as its rootdir, lost the repo's config and hit its 40 s wall.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEST_ROOT = pathlib.Path("~/.cache/zaelar/clean-clone")


def packages(tree: pathlib.Path) -> list[str]:
    """The engine's top-level packages in `tree`: every folder with an `__init__.py`, the test suite left out."""
    return sorted(p.name for p in tree.iterdir()
                  if p.is_dir() and (p / "__init__.py").exists() and p.name not in {"tests"} and not p.name.startswith("."))


def freezers(tree: pathlib.Path) -> list[str]:
    """Every event freezer in `tree` (`test_*event*surviv*.py`): the tests that fail when an emitted event vanishes."""
    return sorted(str(p.relative_to(tree)) for p in (tree / "tests").rglob("test_*event*surviv*.py"))


def plan(tree: pathlib.Path, python: str) -> list[tuple[str, list[str]]]:
    """The steps, in order, as (name, argv), run with `tree` as the working directory."""
    return [("ruff", [python, "-m", "ruff", "check", "."]),
            ("compileall", [python, "-m", "compileall", "-q", *packages(tree)]),
            ("freezers", [python, "tests/watchdog.py", *freezers(tree)]),
            ("infrastructure", [python, "tests/watchdog.py", "tests/infrastructure"])]


def clone(dest: pathlib.Path, *, ref: str, remote: bool) -> str:
    """Clone into `dest`: the committed `ref` of this repo (offline), or `ref` of its `origin` (`--remote`)."""
    if remote:
        url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], check=True,
                             capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", ref, url, str(dest)], check=True)
    else:
        subprocess.run(["git", "clone", "--quiet", "--no-local", "--no-checkout", str(ROOT), str(dest)], check=True)
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", ref], check=True,
                             capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", sha], check=True)
    return subprocess.run(["git", "-C", str(dest), "rev-parse", "--short", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()


def fresh_venv(tree: pathlib.Path) -> str:
    """A venv inside the clone with `requirements.txt` installed; returns its interpreter."""
    venv = tree / ".venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = str(venv / "bin" / "python")
    subprocess.run([py, "-m", "pip", "install", "-q", "-r", str(tree / "requirements.txt"), "ruff"], check=True)
    return py


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tests.infrastructure.clean_clone", description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="HEAD", help="what to clone: a commit/branch of this repo, or a branch with --remote")
    ap.add_argument("--remote", action="store_true", help="clone `--ref` of `origin` instead of this repo's history")
    ap.add_argument("--fresh-venv", action="store_true", help="install requirements.txt into a venv in the clone")
    ap.add_argument("--keep", action="store_true", help="leave the clone on disk and print where")
    ap.add_argument("--dest-root", default=str(DEST_ROOT), help="where clones are made (never under the system temp)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan against THIS tree and run nothing")
    a = ap.parse_args(argv)
    if a.dry_run:
        for name, cmd in plan(ROOT, sys.executable):
            print(f"{name:15} {' '.join(cmd)}")
        return 0
    root = pathlib.Path(a.dest_root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    dest = pathlib.Path(tempfile.mkdtemp(prefix="run-", dir=root))
    results, ok = [], True
    try:
        head = clone(dest / "engine", ref=a.ref, remote=a.remote)
        tree = dest / "engine"
        python = fresh_venv(tree) if a.fresh_venv else sys.executable
        print(f"clean clone of {a.ref} @ {head} in {tree}", flush=True)
        for name, cmd in plan(tree, python):
            t0 = time.monotonic()
            r = subprocess.run(cmd, cwd=tree)
            results.append({"step": name, "ok": r.returncode == 0, "s": round(time.monotonic() - t0, 1)})
            print(f"── {name}: {'ok' if r.returncode == 0 else f'FAILED (exit {r.returncode})'}", flush=True)
            ok = ok and r.returncode == 0
        print(json.dumps({"ref": a.ref, "head": head, "ok": ok, "steps": results}))
        return 0 if ok else 1
    finally:
        if a.keep:
            print(f"kept: {dest}")
        else:
            shutil.rmtree(dest, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
