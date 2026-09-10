"""Exposes the V2-651 F0 speaker-fingerprint shadow contract to pytest/Test Observatory (see the .mjs)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_speaker_id_shadow.mjs")


def test_speaker_id_shadow() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the speaker-id shadow contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
