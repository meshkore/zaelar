"""V2-667 · the generator's contract never contradicts its gate, and a failed gate gets ONE repair pass.

Measured live, session 53de97d4 (2026-09-11): two builds of a simple Bitcoin chart widget died 17 minutes
apart — 3 min and ~1 $ each — on the SAME error, `data.py imports non-stdlib 'memory' (data.py must be
stdlib-only)`. Not the data, not the complexity: `_CONTRACT` said «STDLIB ONLY» in one bullet and
«`from memory import api as memory; memory.write(...)`» in the next, and the gate sided with the stricter one
after the money was spent. `widgets/AGENTS.md` had carried the corrected `ctx.remember(...)` form all along.
"""
from __future__ import annotations

import re
from pathlib import Path

from widgets import generator, validator


# ── the contract agrees with the gate ─────────────────────────────────────────────────────────────────────
def test_the_contract_never_tells_the_agent_to_import_memory():
    c = generator._CONTRACT
    assert "from memory import" not in c and "import memory" not in c.replace("NEVER `import memory`", "")
    assert "ctx.remember(" in c and "ctx.ingest(" in c
    assert "tick(ctx=None)" in c
    assert "STDLIB ONLY" in c


def test_the_gate_really_rejects_what_the_old_contract_taught():
    err = validator._scan_data_py("from memory import api as memory\n\ndef view_data(q=''):\n    return {}\n",
                                  "bitcoin-chart")
    assert err and "non-stdlib 'memory'" in err


def test_the_gate_accepts_the_sanctioned_door():
    src = ("import json\n\ndef view_data(q=''):\n    return {}\n\n"
           "def tick(ctx=None):\n    if ctx: ctx.remember('x', slot='bitcoin:price')\n")
    assert validator._scan_data_py(src, "bitcoin-chart") is None


def test_the_repair_prompt_names_the_error_and_the_rules_the_gate_enforces():
    p = generator._REPAIR_PROMPT.format(wid="w1", error="data.py imports non-stdlib 'memory'", folder="/x/w1")
    assert "non-stdlib 'memory'" in p and "/x/w1" in p
    assert "STDLIB" in p and "ctx.remember" in p and "DONE w1" in p


# ── one bounded repair pass ───────────────────────────────────────────────────────────────────────────────
def test_a_repaired_build_passes_the_gate_and_says_so(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(generator, "_run_agent",
                        lambda prompt, token="", *, target: (prompts.append(prompt) or (True, "")))
    monkeypatch.setattr(generator, "_validate", lambda wid, stamp_origin=False: (True, ""))
    ok, err = generator._repair_once("w1", "/tmp/w1", "data.py imports non-stdlib 'memory'", token="t")
    assert ok is True and err == ""
    assert len(prompts) == 1 and "non-stdlib 'memory'" in prompts[0]


def test_a_second_failure_reports_the_error_that_STOOD_after_the_repair(monkeypatch):
    monkeypatch.setattr(generator, "_run_agent", lambda prompt, token="", *, target: (True, ""))
    monkeypatch.setattr(generator, "_validate", lambda wid, stamp_origin=False: (False, "widget.js uses innerHTML"))
    ok, err = generator._repair_once("w1", "/tmp/w1", "data.py imports non-stdlib 'memory'")
    assert ok is False
    assert err.startswith("widget.js uses innerHTML"), "the NEW error leads — it is what the operator's trace needs"
    assert "after one repair pass" in err and "non-stdlib 'memory'" in err


def test_an_agent_that_never_ran_is_not_a_repair(monkeypatch):
    monkeypatch.setattr(generator, "_run_agent", lambda prompt, token="", *, target: (False, "the agent timed out"))
    calls = []
    monkeypatch.setattr(generator, "_validate", lambda wid, stamp_origin=False: calls.append(wid) or (True, ""))
    ok, err = generator._repair_once("w1", "/tmp/w1", "gate error")
    assert ok is False and "repair pass did not run" in err and "timed out" in err
    assert calls == [], "nothing to validate when the agent never ran"


def test_the_create_path_repairs_BEFORE_it_discards():
    """A structural guard on the seam: `generate_widget` must consult `_repair_once` before `_discard`, and only
    on a build that RAN (a killed agent leaves nothing worth repairing)."""
    src = Path("widgets/generator.py").read_text(encoding="utf-8")
    code = re.sub(r"(?m)^\s*#.*$", "", src)
    body = code[code.index("def generate_widget("):code.index("def _folder_ref(")]
    i_val = body.index("ok, verr = _validate(wid, stamp_origin=True)")
    i_rep = body.index("_repair_once(wid, dst, verr, token)")
    i_dis = body.index("_discard(wid)", i_val)
    assert i_val < i_rep < i_dis, "validate → repair once → only then discard"
