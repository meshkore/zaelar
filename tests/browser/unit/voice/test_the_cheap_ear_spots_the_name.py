"""Exposes the «the browser hears the name for free» contract to pytest/Test Observatory (V2-749).

The measured session, the operator's own words and the reason each assertion exists are in the `.mjs`
beside this file — it drives the REAL `frontend/app/services/wakeword.js`, so this is a runner, not a copy.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_cheap_ear_spots_the_name.mjs")


def test_the_cheap_ear_spots_the_name() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the wake-word spotter contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
