"""V2-667 · the generator's contract never contradicts its gate, and a failed gate gets ONE repair pass.

Measured live, session 53de97d4 (2026-09-11): two builds of a simple Bitcoin chart widget died 17 minutes
apart — 3 min and ~1 $ each — on the SAME error, `data.py imports non-stdlib 'memory' (data.py must be
stdlib-only)`. Not the data, not the complexity: `_CONTRACT` said «STDLIB ONLY» in one bullet and
«`from memory import api as memory; memory.write(...)`» in the next, and the gate sided with the stricter one
after the money was spent. `widgets/AGENTS.md` had carried the corrected `ctx.remember(...)` form all along.
"""
from __future__ import annotations


from widgets import generator, validator
from widgets import validator_actions as _validator_actions_m


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
# ── V2-778 F1-12: the dispatch shape the contract teaches is the one the gate reads ──────────────────────
def test_the_contract_teaches_the_actions_table():
    c = generator._CREATE_PROMPT.format(wid="w1", spec="x", folder="/x/w1")
    assert "ACTIONS = {" in c and "ACTIONS.get(action)" in c and "unknown_action" in c


def test_a_widget_written_the_way_the_contract_says_is_read_by_the_gate():
    """What the contract teaches, written out: the gate must see its actions — a table the gate fail-opened on
    would switch the contract check off for every generated widget, silently."""
    src = ('def _a_add(action: str, p: dict) -> dict:\n    return {"ok": True}\n\n\n'
           'def _a_done(action: str, p: dict) -> dict:\n    return {"ok": True}\n\n\n'
           'ACTIONS = {"add": _a_add, "done": _a_done}\n\n\n'
           'def apply_action(action, payload=None):\n    p = payload or {}\n'
           '    handler = ACTIONS.get(action) if isinstance(action, str) else None\n'
           '    if handler is None:\n        return {"ok": False, "error": "unknown_action", "action": action}\n'
           '    return handler(action, p)\n')
    assert _validator_actions_m._apply_action_names(src) == {"add", "done"}
    man = {"id": "w1", "actions": {"add": {"desc": "x"}, "done": {"desc": "x"}, "ghost": {"desc": "x"}}}
    err = _validator_actions_m._validate_actions_sync(man, src)
    assert err and "ghost" in err, err
