"""Exposes the ORB RING contract to pytest (V2-661b). The reason is in the .mjs, which MOUNTS the real
`sse.js` handler over the real store with a controllable clock and replays the operator's own session."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_ring_never_dies_while_he_is_talking.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_ring_never_dies_while_he_is_talking():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
