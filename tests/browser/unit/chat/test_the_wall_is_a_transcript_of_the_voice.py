"""Exposes the voice↔wall transcript contract to pytest/Test Observatory (V2-745).

The measured session, the operator's own words and the reason each assertion exists are in the `.mjs`
beside this file — it drives the REAL store and the REAL attention hold, so this is a runner, not a copy.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_wall_is_a_transcript_of_the_voice.mjs")


def test_the_wall_is_a_transcript_of_the_voice() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the voice↔wall transcript contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
