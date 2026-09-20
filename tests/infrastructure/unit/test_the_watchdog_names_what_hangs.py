"""The hang detector is the one thing in the suite nothing else watches — so it is watched here.

A wide pytest sweep was FORBIDDEN in this repo from 2026-09-15 to 2026-09-20 because it hung the
operator's machine and nobody could say which test did it. `tests/watchdog.py` exists to answer that
question, and a detector that silently stops detecting would restore the old situation while looking
healthy: every chunk would come back green because nothing ever gets called hung.

So these tests hang a test ON PURPOSE and require the runner to name it, kill it, and take its
children with it. They are slow by nature (a hang has to be waited for), which is why the timeouts
here are seconds rather than the minute-scale defaults.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]


def _sweep(tmp_path: Path, body: str, *, test_timeout: int = 3, chunk_timeout: int = 40) -> dict:
    """Run the watchdog over one generated test file and return its JSON report."""
    target = tmp_path / "test_generated.py"
    target.write_text(textwrap.dedent(body))
    report = tmp_path / "report.json"
    subprocess.run(
        [sys.executable, str(ENGINE / "tests" / "watchdog.py"), str(target),
         "--test-timeout", str(test_timeout), "--chunk-timeout", str(chunk_timeout),
         "--report", str(report)],
        cwd=str(ENGINE), capture_output=True, text=True, timeout=chunk_timeout + 60,
    )
    return json.loads(report.read_text())["results"][0]


def test_a_hanging_test_is_named_not_merely_survived(tmp_path):
    """The verdict says «hung» AND says who — an unnamed hang is what the prohibition already had."""
    result = _sweep(tmp_path, """
        import time

        def test_this_one_is_fine():
            assert True

        def test_this_one_never_returns():
            time.sleep(300)
    """)
    assert result["verdict"] == "hung", result
    assert result["hung_at"] is not None, "the hang was detected but not attributed to any test"
    assert result["hung_at"].endswith("::test_this_one_never_returns"), result["hung_at"]


def test_the_hang_is_cut_at_the_test_wall_not_at_the_chunk_wall(tmp_path):
    """Detection comes from the faulthandler dump, so it costs seconds — not the whole chunk budget.

    This is the difference between a usable sweep and one nobody launches: with only the outer wall
    clock, every hang costs `--chunk-timeout` (minutes) and a folder with three of them costs the
    session. The dump names the test as soon as ONE test exceeds `--test-timeout`.
    """
    # The passing test in front is NOT decoration. pytest prints its progress character on the same
    # line the faulthandler banner starts (`.Timeout (0:00:03)!`), and the first version of the
    # detector anchored its regex to the start of the line, so it saw nothing and every hang fell
    # through to the chunk wall. A generated file with ONE test hides that bug completely: the
    # banner lands in column 0 and the broken detector passes. Disarm-measured, 2026-09-20.
    result = _sweep(tmp_path, """
        import time

        def test_this_one_passes_first_and_prints_a_progress_dot():
            assert True

        def test_this_one_never_returns():
            time.sleep(300)
    """, test_timeout=3, chunk_timeout=90)
    assert result["verdict"] == "hung"
    assert result["seconds"] < 30, f"took {result['seconds']}s — it fell through to the chunk wall"


def test_a_child_process_does_not_outlive_the_hang_it_belongs_to(tmp_path):
    """The 2026-09-15 incident left 71 orphaned Chromium processes; killing pytest alone repeats it."""
    marker = tmp_path / "child.pid"
    result = _sweep(tmp_path, f"""
        import subprocess, sys, time

        def test_spawns_then_hangs():
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
            open({str(marker)!r}, "w").write(str(child.pid))
            time.sleep(300)
    """)
    assert result["verdict"] == "hung"
    pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        import os
        os.kill(pid, 0)          # raising means it is gone, which is the promise


def test_a_healthy_folder_is_never_called_hung(tmp_path):
    """The other half: a detector that cries hang on a slow-but-alive test is a detector nobody trusts."""
    result = _sweep(tmp_path, """
        import time

        def test_slow_but_alive():
            time.sleep(1.0)
            assert True
    """, test_timeout=5)
    assert result["verdict"] == "ok", result
    assert result["hung_at"] is None
    assert result["counts"].get("passed") == 1
