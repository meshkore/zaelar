"""`nucleo/worker_bridge.py` has no product importer and is alive: it is the CLI a worker RUNS (refactor2710-09).

The import graph lists it with fan-in 0, which reads as an orphan — but a worker reaches it as
`python -m nucleo.worker_bridge ask|act|say|wait|decide`, the way it asks him a question, searches and hands work to a
card. Deleting it as an orphan would leave every worker with a prompt that teaches a door that is not there. Proven
three ways: the worker's allowlist names it, the prompt teaches it, and the module runs as `-m`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]


def test_the_worker_may_run_it():
    from nucleo.workers.providers import claude
    allowed = " ".join(claude._BRIDGE_TOOLS)
    assert "nucleo.worker_bridge" in allowed, "the bridge is not in the worker's Bash allowlist"


def test_the_prompt_teaches_it():
    from nucleo.workers.prompts import _build_prompt
    assert "python -m nucleo.worker_bridge ask" in _build_prompt("busca un carpintero en Soria", "", True, None)


def test_it_runs_as_a_module_with_its_five_commands():
    r = subprocess.run([sys.executable, "-m", "nucleo.worker_bridge", "-h"], cwd=ENGINE, capture_output=True,
                       text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    for cmd in ("ask", "wait", "act", "say", "decide"):
        assert cmd in r.stdout, (cmd, r.stdout)
