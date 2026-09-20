"""A test that waits must wait against a CLOCK — V2-728, at the operator's request (2026-09-20).

*«Marca los tests que se cuelgan para apartarlos o arreglarlos.»*

**Measured the same day, with the suites healthy: nothing in `agent_headless`/`memory` takes over 3.5 s.**
So there is no slow test to quarantine. What there is, is a shape that turns a broken precondition into a
hang, and it does not show up until something else is already wrong:

| test | healthy | with its precondition broken |
|---|---|---|
| `test_dispatch.py::test_listener_consumes_escalate_requested` | 1.3 s | **15 minutes** |
| `test_a_commission_leaves_a_durable_row.py` (per case) | 2.8 s | **114 s** |

Both were `for _ in range(300): await asyncio.sleep(0.05)`. Two defects in that line:

1. **The budget counts ITERATIONS, and the cost of an iteration is not the sleep.** It reads as fifteen
   seconds; dispatch performs a real recall (~2 s with the local reranker) inside it, so the wall clock is
   unbounded exactly when something is wrong. `range(N)` is not a duration and nobody reads it as one.
2. **When it finally gives up, the assertion that fails is about the RESULT** — «assert done is True» — which
   says nothing about having waited. The cause has to be reconstructed from timestamps in a captured log.

`tests/waiting.py::until` is the replacement: a real deadline, and a failure that NAMES the wait.

## What this ratchet does, and what it deliberately does not

It COUNTS the loops of that shape and refuses to let the number grow. It does not fail them one by one,
because most of the 58 are honest: an e2e file waiting for its preview server with `range(60)` +
`sleep(0.5)` really is bounded at thirty seconds — there, the sleep IS the cost of an iteration. Failing
those would be noise, and a ratchet that cries wolf gets silenced.

The dangerous ones are the loops whose BODY does real work. Telling them apart automatically needs to know
what a call costs, which no regex knows — so the number is the signal, and a new one has to say why.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

ENGINE = pathlib.Path(__file__).resolve().parents[3]

#: Measured 2026-09-20, after V2-728 converted the five loops in the two files that had actually hung.
#: EDIT DOWNWARD ONLY — converting one to `tests/waiting.until` is the celebration.
MAX_ITERATION_BOUNDED_WAITS = 58

_POLL = re.compile(r"for\s+_\w*\s+in\s+range\(\s*(\d+)\s*\)\s*:")


def _waits() -> list[tuple[str, int, int]]:
    """`[(file, line, iterations)]` for every poll loop bounded by a count instead of a clock.

    Asked of `git ls-files`, not of the checkout: V2-727's lesson, and the same one V2-728 re-learned when
    `.meshkore/snapshots/` — the §20 pre-edit copies of production files — was counted as production.
    """
    done = subprocess.run(["git", "ls-files", "-z", "tests/*.py"], cwd=str(ENGINE),
                          capture_output=True, timeout=60)
    assert done.returncode == 0, "the sweep needs git to know what the tree IS"
    out: list[tuple[str, int, int]] = []
    for rel in done.stdout.decode("utf-8", errors="ignore").split("\0"):
        if not rel:
            continue
        try:
            lines = (ENGINE / rel).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            # …and NOT inside a comment. Caught on this very file's first run: the testmap note that
            # EXPLAINS the bad shape quotes `for _ in range(300): sleep(0.05)` in prose, and the sweep
            # counted its own documentation. A detector that fires on the sentence describing it teaches
            # people to stop writing the sentence.
            if line.lstrip().startswith("#"):
                continue
            m = _POLL.search(line)
            # a `range()` loop is only a WAIT if it sleeps; the rest are ordinary loops
            if m and "sleep(" in "\n".join(lines[i:i + 8]):
                out.append((rel, i + 1, int(m.group(1))))
    return out


def test_no_new_wait_is_bounded_by_an_iteration_count():
    waits = _waits()
    assert len(waits) <= MAX_ITERATION_BOUNDED_WAITS, (
        f"{len(waits)} waits bounded by an iteration count (ceiling {MAX_ITERATION_BOUNDED_WAITS}). "
        "A new one turns a broken precondition into a hang — use `tests/waiting.py::until`, which waits "
        "against a clock and names what never happened:\n  "
        + "\n  ".join(f"range({n}) {f}:{ln}" for f, ln, n in sorted(waits, key=lambda x: -x[2])[:10]))


def test_the_two_that_actually_hung_now_wait_on_a_clock():
    """The precedent, pinned. These are the files that were measured hanging; a regression here is the
    fifteen-minute wait coming back, and it would otherwise only be noticed the next time it happened."""
    for rel in ("tests/agent_headless/unit/test_dispatch.py",
                "tests/agent_headless/unit/test_a_commission_leaves_a_durable_row.py"):
        src = (ENGINE / rel).read_text(encoding="utf-8")
        assert "from tests.waiting import until" in src, f"{rel} stopped using the clock-bounded wait"
        assert not [1 for f, _, _ in _waits() if f == rel], f"{rel} grew a counted wait again"


def test_the_helper_fails_FAST_and_says_what_it_was_waiting_for():
    """The guard for the guard: a helper that swallowed the timeout would reintroduce the silent hang, and
    one whose message did not name the wait would reintroduce the hour of log archaeology."""
    import time

    from tests.waiting import until_sync
    t0 = time.monotonic()
    try:
        until_sync(lambda: False, "the durable row", timeout_s=0.3)
    except AssertionError as e:
        assert time.monotonic() - t0 < 2.0, "the deadline is not a deadline"
        assert "the durable row" in str(e), "the failure does not name what never happened"
    else:
        raise AssertionError("a wait that never succeeds must FAIL, not return")


def test_a_wait_that_succeeds_returns_what_it_waited_for():
    from tests.waiting import until_sync
    box = {"n": 0}

    def _tick():
        box["n"] += 1
        return {"row": 1} if box["n"] > 2 else None

    assert until_sync(_tick, "the row", timeout_s=2) == {"row": 1}
