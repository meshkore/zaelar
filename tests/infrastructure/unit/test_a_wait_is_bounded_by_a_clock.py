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

⚠️ IT PARSES, IT DOES NOT GREP, and that is this file's own scar twice over. The first version matched a
line at a time and counted the testmap note that EXPLAINS the bad shape; skipping `#` comments fixed that
and left the same bug one layer down — the prose in THIS module's docstring and in `tests/waiting.py`'s,
both of which quote `for _ in range(300): sleep(0.05)` to say do not do this, were counted as two more
offences. **A detector that fires on the sentence describing it teaches people to stop writing the
sentence.** An `ast` walk cannot see inside a string, so the class is closed rather than patched again.

It COUNTS the loops of that shape and refuses to let the number grow. It does not fail them one by one,
because most of the 58 are honest: an e2e file waiting for its preview server with `range(60)` +
`sleep(0.5)` really is bounded at thirty seconds — there, the sleep IS the cost of an iteration. Failing
those would be noise, and a ratchet that cries wolf gets silenced.

The dangerous ones are the loops whose BODY does real work. Telling them apart automatically needs to know
what a call costs, which no regex knows — so the number is the signal, and a new one has to say why.
"""
from __future__ import annotations

import ast
import pathlib
import re
import subprocess

ENGINE = pathlib.Path(__file__).resolve().parents[3]

#: Measured 2026-09-20, after V2-728 converted the five loops in the two files that had actually hung.
#: EDIT DOWNWARD ONLY — converting one to `tests/waiting.until` is the celebration.
MAX_ITERATION_BOUNDED_WAITS = 58

#: Does this loop's body SLEEP? A `range()` loop that does not is an ordinary loop, not a wait.
_SLEEPS = re.compile(r"\bsleep\s*\(")


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
            src = (ENGINE / rel).read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.For) or not isinstance(node.target, ast.Name):
                continue
            if not node.target.id.startswith("_"):
                continue
            call = node.iter
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    and call.func.id == "range" and len(call.args) == 1
                    and isinstance(call.args[0], ast.Constant)
                    and isinstance(call.args[0].value, int)):
                continue
            # A `range()` loop is only a WAIT if it SLEEPS; the rest are ordinary loops.
            body = "\n".join(lines[node.body[0].lineno - 1:(node.end_lineno or node.lineno)])
            if _SLEEPS.search(body):
                out.append((rel, node.lineno, int(call.args[0].value)))
    return out


def test_no_new_wait_is_bounded_by_an_iteration_count():
    waits = _waits()
    assert len(waits) <= MAX_ITERATION_BOUNDED_WAITS, (
        f"{len(waits)} waits bounded by an iteration count (ceiling {MAX_ITERATION_BOUNDED_WAITS}). "
        "A new one turns a broken precondition into a hang — use `tests/waiting.py::until`, which waits "
        "against a clock and names what never happened:\n  "
        + "\n  ".join(f"range({n}) {f}:{ln}" for f, ln, n in sorted(waits, key=lambda x: -x[2])[:10]))


def test_the_detector_cannot_be_fooled_by_PROSE_about_the_bad_shape(tmp_path):
    """The bug this file had twice: counting the sentence that describes the offence.

    Both halves are asserted, because a detector that stopped seeing real loops would also pass the first
    half. The generated file carries the shape in a docstring, in a `#` comment AND for real."""
    import ast as _ast
    src = tmp_path / "t_probe.py"
    src.write_text(
        '"""Never write `for _ in range(300): sleep(0.05)` — it reads as 15 s and is not."""\n'
        "import time\n"
        "# also forbidden: for _ in range(300): time.sleep(0.05)\n"
        "def test_x():\n"
        "    for _ in range(7):\n"
        "        time.sleep(0.1)\n", encoding="utf-8")
    tree = _ast.parse(src.read_text(encoding="utf-8"))
    lines = src.read_text(encoding="utf-8").splitlines()
    hits = []
    for node in _ast.walk(tree):
        if (isinstance(node, _ast.For) and isinstance(node.target, _ast.Name)
                and node.target.id.startswith("_") and isinstance(node.iter, _ast.Call)
                and getattr(node.iter.func, "id", "") == "range"):
            body = "\n".join(lines[node.body[0].lineno - 1:(node.end_lineno or node.lineno)])
            if _SLEEPS.search(body):
                hits.append(node.iter.args[0].value)
    assert hits == [7], (
        f"the detector must see the ONE real loop and neither of the two written ABOUT it; saw {hits}")


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
