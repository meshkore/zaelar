"""Exposes the report-kind and picture-budget contract to pytest / Test Observatory (V2-695).

Same shape as its sibling next door: the reasoning lives in the .mjs, which runs the real frontend
modules pytest cannot import. This wrapper is what puts it inside the deterministic suite instead of
leaving it a script somebody remembers to run.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_report_says_what_kind_it_is.mjs")


def test_a_report_says_what_kind_it_is_and_the_pictures_fit() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the feedback report contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
