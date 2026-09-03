"""Exposes the mobile shell's AUDIO-OUTPUT wiring to pytest/the Test Observatory (see the .mjs for the why).

The assertions live in Node because they read the frontend's own source: whether `room.startAudio()` is actually
called, whether the playback-status listener exists, whether the first touch carries the unlock. Same wrapper
pattern as test_mobile_host_contract.py.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_phone_can_be_heard.mjs")


def test_the_phone_unlocks_playback_and_never_inherits_silence() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the mobile audio-output contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
