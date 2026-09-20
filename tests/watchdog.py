"""Hang-aware test runner — runs the suite in chunks and NAMES whatever hangs.

## Why this exists

A whole-tree `pytest` run had been forbidden here since 2026-09-15 because it hung the operator's
machine, and the prohibition shipped with its root cause **undiagnosed** — the honest state at the
time, but a prohibition is not a diagnosis, and it left the engine with no way to answer "does
everything still pass?". The operator's correction (2026-09-20): *some* tests hang, not all of them,
and what is missing is a runner that detects a hang instead of a rule that avoids the question.

## How a hang is caught

Three layers, cheapest first:

1. **`faulthandler_timeout`** (stdlib, already inside pytest — no new dependency). A test that runs
   longer than `--test-timeout` dumps every thread's stack to **fd 2, unbuffered**. That dump names
   the file, the line and the test function, so a hang is IDENTIFIED rather than merely survived.
   This runner watches the stream for that dump and kills the chunk the moment it appears.
2. **A wall clock per chunk** (`--chunk-timeout`), the backstop for hangs `faulthandler` cannot see
   because they happen outside a test item — an import or a collection that blocks. When this fires
   the chunk is re-run one file at a time to name the culprit.
3. **The process GROUP**, not the process. Every chunk runs in its own session, so killing it takes
   its children with it. The 2026-09-15 incident left **71 orphaned Chromium processes** alive; a
   plain `kill` on pytest would have left them exactly as they were.

## The other half of that incident

Two pytest runs from two sessions were sharing this checkout (1222 s and 1589 s for sweeps that take
9 minutes alone). So this runner takes a **checkout-wide lock** and refuses to start next to another
one instead of adding a third. Chunks run serially for the same reason: the failure mode was
contention, and parallelism is what buys it.

Nothing here replaces `python -m tests run <suite>` — that one publishes to the Observatory and is
still the interface for a suite. This is the wide regression sweep, and it is safe to launch.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
TESTS = ENGINE / "tests"
LOCK = TESTS / "runs" / ".watchdog.lock"

# The faulthandler banner, and the first frame under it that belongs to a test file. The banner is
# NOT anchored to the start of the line on purpose: pytest's progress character lands in front of it
# (`.Timeout (0:00:04)!`), and an anchored match silently never fires — measured here, 2026-09-20.
_DUMP = re.compile(r"Timeout \(\d+:\d\d:\d\d\)!")
_FRAME = re.compile(r'^  File "(?P<file>[^"]+)", line (?P<line>\d+) in (?P<func>\w+)')
_COUNTS = re.compile(r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)")

# Suites whose tests want a live service or a browser: excluded from --all on purpose, because a
# skip-storm is not a green and a live-boundary run is a decision, not a default.
_LIVE = ("/e2e/", "/integration/", "/benchmarks/", "/lab/")


def label_of(path: Path) -> str:
    try:
        return str(path.relative_to(ENGINE))
    except ValueError:
        return str(path)


def leaf_dirs(roots: list[Path], *, include_live: bool) -> list[Path]:
    """Every directory that directly holds test files, deepest-first for a stable report order."""
    found: set[Path] = set()
    for root in roots:
        if root.is_file():
            found.add(root)
            continue
        for path in root.rglob("test_*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = "/" + str(path.relative_to(ENGINE))
            if not include_live and any(mark in rel for mark in _LIVE):
                continue
            found.add(path.parent)
    return sorted(found)


# ── Which tests does a change actually reach? ──────────────────────────────────────────────────
#
# Not a hand-written table of "this folder belongs to that suite" — that kind of map is a guess that
# rots the first time a module moves. The signal used here is the one the code itself states: a test
# that imports `nucleo.flash.turn_brief` is a test that change can break. A changed test file is
# always selected; a changed source file selects every test that names its module. Anything the grep
# cannot see (a fixture reaching production through a string, a template, a JS bundle) is exactly why
# this is a fast pre-check and the wide sweep stays the safety net before a commit lands.

_SOURCE_SUFFIXES = (".py",)


def changed_files(base: str) -> list[str]:
    """Everything touched vs `base`, committed or not."""
    out: set[str] = set()
    for cmd in (["git", "diff", "--name-only", base, "--"],
                ["git", "diff", "--name-only", "HEAD", "--"],
                ["git", "ls-files", "--others", "--exclude-standard"]):
        try:
            done = subprocess.run(cmd, cwd=str(ENGINE), capture_output=True, text=True, timeout=30)
        except Exception:
            continue
        if done.returncode == 0:
            out.update(line for line in done.stdout.splitlines() if line.strip())
    return sorted(out)


def impacted_targets(base: str) -> tuple[list[Path], list[str]]:
    """Test files reached by the change, plus the human-readable reasons."""
    picked: set[Path] = set()
    why: list[str] = []
    every_test = [p for p in TESTS.rglob("test_*.py") if "__pycache__" not in p.parts]
    haystack = {p: p.read_text(errors="ignore") for p in every_test}

    for rel in changed_files(base):
        path = ENGINE / rel
        if rel.startswith("tests/") and path.name.startswith("test_") and path.exists():
            picked.add(path)
            why.append(f"{rel} → itself (a changed test runs)")
            continue
        if not rel.endswith(_SOURCE_SUFFIXES) or not path.exists():
            continue
        module = rel[:-3].replace("/", ".")
        leaf = module.rsplit(".", 1)[-1]
        if leaf == "__init__":
            module = module.rsplit(".", 1)[0]
            leaf = module.rsplit(".", 1)[-1]
        # Import FORMS only. Matching the bare leaf name matched prose instead of code — the first
        # version selected 14 tests for `tests/watchdog.py` because `use_cases` describes a
        # "mid-scenario watchdog" in English. A word in a docstring is not a dependency.
        parent = module.rsplit(".", 1)[0] if "." in module else ""
        forms = [re.compile(re.escape(module) + r"\b")]
        if parent:
            forms.append(re.compile(rf"from\s+{re.escape(parent)}\s+import\s+[^\n]*\b{re.escape(leaf)}\b"))
        hits = [p for p, text in haystack.items() if any(f.search(text) for f in forms)]
        for hit in hits:
            picked.add(hit)
        why.append(f"{rel} → {len(hits)} tests name `{module}`")
    return sorted(picked), why


class Chunk:
    """One pytest invocation, watched while it runs."""

    def __init__(self, target: Path, *, test_timeout: int, chunk_timeout: int, actor: str):
        self.target = target
        self.test_timeout = test_timeout
        self.chunk_timeout = chunk_timeout
        self.actor = actor
        self.lines: deque[str] = deque(maxlen=4000)
        self.hung_at: str | None = None
        self.stack: list[str] = []

    def _watch_stream(self, proc: subprocess.Popen) -> None:
        collecting = False
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            self.lines.append(line)
            if _DUMP.search(line):
                # A test just blew through --test-timeout. The next frames say where.
                collecting = True
                self.stack = [line]
                continue
            if collecting:
                self.stack.append(line)
                match = _FRAME.match(line)
                if match and self.hung_at is None:
                    here = match.group("file")
                    if "/site-packages/" not in here:
                        rel = os.path.relpath(here, ENGINE)
                        self.hung_at = f"{rel}::{match.group('func')}"
                if len(self.stack) > 60:
                    collecting = False

    def run(self) -> dict:
        # A directory is run NON-recursively. pytest would otherwise descend into the child
        # directories that are chunks in their own right, running them twice and double-counting
        # every `passed` in the report — measured here on the first sweep, 2026-09-20.
        cmd = [str(ENGINE / ".venv/bin/python"), "-m", "pytest"]
        if self.target.is_dir():
            cmd += [str(child) for child in sorted(self.target.glob("test_*.py"))]
        else:
            cmd.append(str(self.target))
        cmd += ["-q", "-p", "no:cacheprovider", "--tb=line", "--no-header",
                "-o", f"faulthandler_timeout={self.test_timeout}"]
        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",          # so the dump reaches us the instant it is written
            "ZAELAR_TEST_ACTOR": self.actor,
        }
        started = time.monotonic()
        proc = subprocess.Popen(
            cmd, cwd=str(ENGINE), env=env, text=True, bufsize=1,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=True,           # its own process group: children die with it
        )
        reader = threading.Thread(target=self._watch_stream, args=(proc,), daemon=True)
        reader.start()

        verdict = "ok"
        while True:
            if proc.poll() is not None:
                break
            if self.hung_at is not None:
                verdict = "hung"
                break
            if time.monotonic() - started > self.chunk_timeout:
                verdict = "hung"
                break
            time.sleep(0.2)

        if verdict == "hung":
            self._kill(proc)
        reader.join(timeout=3)
        elapsed = round(time.monotonic() - started, 1)
        code = proc.returncode if proc.returncode is not None else -9
        tail = list(self.lines)
        if verdict != "hung":
            verdict = "ok" if code == 0 else ("failed" if code == 1 else f"exit{code}")
        return {
            "target": label_of(self.target),
            "verdict": verdict,
            "seconds": elapsed,
            "exit": code,
            "hung_at": self.hung_at,
            "counts": self._counts(tail),
            "stack": self.stack[:25],
            "tail": tail[-25:],
        }

    @staticmethod
    def _counts(lines: list[str]) -> dict:
        out: dict[str, int] = {}
        for line in reversed(lines):
            for number, what in _COUNTS.findall(line):
                out.setdefault(what.rstrip("s"), int(number))
            if out:
                break
        return out

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        """Take down the whole group — pytest AND whatever it spawned (Chromium, http.server…)."""
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        for sig, grace in ((signal.SIGTERM, 4.0), (signal.SIGKILL, 2.0)):
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + grace
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    return
                time.sleep(0.1)


def take_lock() -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            held = json.loads(LOCK.read_text())
            alive = True
            try:
                os.kill(int(held["pid"]), 0)
            except (ProcessLookupError, ValueError):
                alive = False
            if alive:
                print(f"⛔ another sweep is running here: pid {held['pid']} by {held.get('actor')} "
                      f"since {held.get('started')}. Two sweeps on one checkout is the 2026-09-15 hang.")
                return False
        except Exception:
            pass          # a corrupt lock is a stale lock
    LOCK.write_text(json.dumps({
        "pid": os.getpid(),
        "actor": os.environ.get("ZAELAR_TEST_ACTOR", "unknown"),
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    }))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Run tests in chunks and name whatever hangs.")
    ap.add_argument("paths", nargs="*", help="files or directories (default: every deterministic dir)")
    ap.add_argument("--test-timeout", type=int, default=60, help="seconds before ONE test is called hung")
    ap.add_argument("--chunk-timeout", type=int, default=420, help="wall clock for one directory")
    ap.add_argument("--include-live", action="store_true", help="also e2e/integration (needs services)")
    ap.add_argument("--by-file", action="store_true", help="one pytest per FILE instead of per directory")
    ap.add_argument("--report", default="", help="where to write the JSON report")
    ap.add_argument("--impacted", metavar="REF", help="run only what the diff vs REF can reach (e.g. origin/main)")
    ap.add_argument("--explain", action="store_true", help="with --impacted: print the selection and run nothing")
    args = ap.parse_args()

    if args.impacted:
        targets, why = impacted_targets(args.impacted)
        print(f"impact of the diff vs {args.impacted}:")
        for line in why:
            print(f"  · {line}")
        print(f"  = {len(targets)} test files selected")
        if args.explain:
            return 0
        if not targets:
            print("nothing reached — run the wide sweep before the commit lands anyway")
            return 0
    else:
        roots = [Path(p).resolve() for p in args.paths] or [TESTS]
        targets = leaf_dirs(roots, include_live=args.include_live)
    if args.by_file and not args.impacted:
        files: list[Path] = []
        for target in targets:
            files.extend(sorted(target.glob("test_*.py")) if target.is_dir() else [target])
        targets = files
    if not targets:
        print("nothing to run")
        return 0
    # The lock guards against two WIDE sweeps sharing this checkout — that is the contention that
    # turned 9-minute runs into 20-minute ones on 2026-09-15. An explicit narrow target is cheap and
    # must stay nestable: the watchdog's own tests run the watchdog.
    wide = not args.paths and not args.impacted
    if wide and not take_lock():
        return 2

    actor = os.environ.get("ZAELAR_TEST_ACTOR", "watchdog")
    print(f"▶ {len(targets)} chunks · test wall {args.test_timeout}s · chunk wall {args.chunk_timeout}s")
    results = []
    started = time.monotonic()
    try:
        for n, target in enumerate(targets, 1):
            label = label_of(target)
            print(f"[{n}/{len(targets)}] {label} … ", end="", flush=True)
            res = Chunk(target, test_timeout=args.test_timeout,
                        chunk_timeout=args.chunk_timeout, actor=actor).run()
            results.append(res)
            counts = " ".join(f"{v} {k}" for k, v in sorted(res["counts"].items()))
            if res["verdict"] == "hung":
                print(f"⏱ HUNG after {res['seconds']}s — {res['hung_at'] or 'outside any test'}")
            else:
                mark = "✓" if res["verdict"] == "ok" else "✗"
                print(f"{mark} {res['seconds']}s · {counts or res['verdict']}")
    finally:
        if wide:
            LOCK.unlink(missing_ok=True)

    hung = [r for r in results if r["verdict"] == "hung"]
    bad = [r for r in results if r["verdict"] not in ("ok", "hung")]
    total = {k: sum(r["counts"].get(k, 0) for r in results) for k in ("passed", "failed", "error", "skipped")}
    print(f"\n── {round(time.monotonic() - started)}s · {len(results)} chunks · "
          f"{total['passed']} passed, {total['failed']} failed, {total['error']} errors, "
          f"{total['skipped']} skipped")
    if hung:
        print(f"\n⏱ {len(hung)} HUNG:")
        for r in hung:
            print(f"   {r['target']} → {r['hung_at'] or 'hang outside a test (import/collection)'}")
    if bad:
        print(f"\n✗ {len(bad)} chunks with failures:")
        for r in bad:
            print(f"   {r['target']} ({r['verdict']})")
            for line in r["tail"][-6:]:
                if line.strip():
                    print(f"      {line}")

    report = Path(args.report) if args.report else TESTS / "runs" / f"watchdog-{time.strftime('%Y%m%d-%H%M%S')}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"results": results, "totals": total}, indent=2))
    print(f"\nreport: {label_of(report)}")
    return 1 if (hung or bad) else 0


if __name__ == "__main__":
    sys.exit(main())
