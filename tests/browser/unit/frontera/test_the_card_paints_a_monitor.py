"""Exposes the REAL rendering of the browser card to pytest (V2-257). The reason is in the .mjs."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_card_paints_a_monitor.mjs")
ENGINE = Path(__file__).resolve().parents[4]
WIDGET = ENGINE / "widgets" / "navegador" / "widget.js"


def test_the_browser_card_paints_a_monitor_and_never_results() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to mount the browser card render")
    result = subprocess.run([node, str(SCRIPT), str(WIDGET)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
