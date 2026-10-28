"""Every CLI a worker runs starts, at the path the product names (refactor2710-10 T-01).

The entry points a Brain Worker runs (`hbnav`, `hbwidget`, `hbnote`, `hbask`, `hbmem`, `hbmesh`, the git bridge) moved
into `nucleo/cli/`. A moved CLI fails SILENTLY: the worker's prompt, its allow-list and the command shims still name
the old module, the subprocess exits 1 and the worker reads «command not found» as a fact about the world. So two
checks: each declared CLI answers `-h`, and every `-m nucleo.<module>` written anywhere in the product resolves to a
module that exists.

Disarm: point one `-m` string in the product at an old path → the second test names it.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]
CLIS = ("nucleo.cli.nav", "nucleo.cli.mesh", "nucleo.cli.widget", "nucleo.cli.mem", "nucleo.cli.git",
        "nucleo.cli.report", "nucleo.cli.bridge", "nucleo.cli")


@pytest.mark.parametrize("module", CLIS)
def test_each_cli_answers_help(module):
    r = subprocess.run([sys.executable, "-m", module, "-h"], cwd=ENGINE, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"{module} -h exited {r.returncode}: {(r.stderr or r.stdout)[-300:]}"


def _named_modules() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    pat = re.compile(r"-m (nucleo(?:\.[a-z_]{2,})+)")   # `nucleo.x` in a docstring is an example, not a CLI
    for root in ("nucleo", "widgets", "voice", "server", "connectors"):
        for p in (ENGINE / root).rglob("*.py"):
            for m in pat.finditer(p.read_text(encoding="utf-8")):
                found.setdefault(m.group(1), []).append(str(p.relative_to(ENGINE)))
    return found


def test_every_module_the_product_tells_a_worker_to_run_exists():
    missing = {m: files[:3] for m, files in _named_modules().items() if importlib.util.find_spec(m) is None}
    assert not missing, f"the product names CLIs that do not exist (a worker would get «command not found»): {missing}"
