"""The voice turn's prompt never loads a worker's brief (refactor2710-08 T-04, node 2.891).

A worker's rules (its drawer, its method, how it presents a sheet) are not the voice's: when both lived beside each
other in `nucleo/`, nothing stopped a prompt block from importing the other's prose. The briefs now live in
`nucleo/workers/prompts/`; importing the voice prompt builder, in a clean interpreter, must not load them.

Disarm: import `nucleo.workers.prompts` from `nucleo/turn/prompt/builder.py` and this goes red.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ENGINE = pathlib.Path(__file__).resolve().parents[4]


def test_importing_the_voice_prompt_loads_no_worker_brief():
    code = ("import sys; import nucleo.turn.prompt.builder, nucleo.turn.prompt.live_state; "
            "print(sorted(m for m in sys.modules if m.startswith('nucleo.workers.prompts')))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ENGINE, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    assert out.stdout.strip().splitlines()[-1] == "[]", f"the voice prompt loaded a worker brief: {out.stdout[-400:]}"


def test_the_worker_briefs_are_where_the_dispatcher_takes_them_from():
    from nucleo import dispatch
    from nucleo.workers import prompts
    assert dispatch._build_prompt is prompts._build_prompt and dispatch._web_prompt is prompts._web_prompt
