"""Exposes the MOBILE SHELL's host contract to pytest/the Test Observatory (see the .mjs for the why).

The assertions live in Node because they read the frontend's own source as the source of truth — the list of
methods `services/sse.js` actually calls, the endpoints `Deck.js` actually fetches — rather than a hand-copied
list that would keep passing while the phone silently ignored the brain. Same wrapper pattern as
tests/browser/unit/energy/test_energy_scale.py.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_mobile_host_contract.mjs")


def test_the_mobile_shell_still_satisfies_the_host_and_widget_contracts() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the mobile host contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
