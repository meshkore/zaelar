"""Expone a pytest/Test Observatory el contrato de la escala de la PILA de Energy (ver el .mjs para el porqué)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_energy_scale.mjs")


def test_the_energy_gauge_scale_matches_the_operators_numbers() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the energy gauge scale contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
