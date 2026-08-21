"""Exposes the feedback failure contract to pytest / Test Observatory (V2-256).

The reasoning lives in the .mjs next to this file — it runs the real frontend module, which pytest
cannot import. This wrapper exists so the contract is inside the deterministic suite instead of being
a script somebody remembers to run.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_send_that_fails_says_so.mjs")


def test_a_feedback_send_that_fails_is_never_silent() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the feedback outcome contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
