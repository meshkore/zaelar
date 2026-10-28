"""A memory event survives a refactor of the file that emits it (V2-826 §2b, refactor2710-11).

The same guard as `test_an_event_survives_a_move.py` (connectors/server), over `memory/` and `nucleo/memory_agent/`:
splitting a file moves its `emit(...)` calls, and deleting one fails silently — the viewer and the Master just show
less. Frozen here: the (kind, label) pairs emitted with literal arguments, the kinds emitted with a computed label,
and the `op` of every `memory.updated` bus event (the viewer's 🧠 refresh is keyed by it). A pair may move between
files, never vanish; one retired on purpose leaves this set in the same commit, with the reason.

Measured 2026-10-28 against the tree before the split (mem_processor.py, memllm.py and the flat memory/ files): no
pair, kind or op was lost; the split added «recall medido» and the write events.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

FROZEN = {
    ("memory", "espacio vectorial descuadrado"), ("memory", "identidad protegida de una autodeclaración"),
    ("memory", "procesador"), ("memory", "recall medido"), ("memory", "slot de identidad protegido"),
}
#: Kinds emitted at all (several with a computed label: the pill kind, the result door's verdict).
FROZEN_KINDS = {"memory", "memory.reinforce", "memory.rem", "memory.updated"}
FROZEN_OPS = {
    "clear_conversation", "clear_slot_prefix", "consolidate", "episode", "forget", "link", "migrate_inbox", "pin",
    "reinforce", "state", "unforget", "unpin", "vault", "write",
}


def _emitted() -> tuple[set, set, set]:
    pairs, kinds, ops = set(), set(), set()
    for root in ("memory", "nucleo/memory_agent"):
        for p in (ENGINE / root).rglob("*.py"):
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if not isinstance(n, ast.Call):
                    continue
                name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if name not in ("emit", "_emit", "emit_sync") or not n.args or not isinstance(n.args[0], ast.Constant):
                    continue
                kind = n.args[0].value
                kinds.add(kind)
                arg = n.args[1] if len(n.args) > 1 else None
                if isinstance(arg, ast.Constant):
                    pairs.add((kind, arg.value))
                elif isinstance(arg, ast.Dict) and kind == "memory.updated":
                    ops |= {v.value for k, v in zip(arg.keys, arg.values)
                            if isinstance(k, ast.Constant) and k.value == "op" and isinstance(v, ast.Constant)}
    return pairs, kinds, ops


def _missing(pairs: set, kinds: set, ops: set) -> list:
    return sorted(FROZEN - pairs) + sorted(FROZEN_KINDS - kinds) + sorted(FROZEN_OPS - ops)


def test_no_frozen_event_vanishes_from_memory():
    assert not _missing(*_emitted()), f"a memory event stopped being emitted: {_missing(*_emitted())}"


def test_disarm_a_dropped_event_is_named():
    pairs, kinds, ops = _emitted()
    assert _missing(pairs - {("memory", "procesador")}, kinds, ops) == [("memory", "procesador")]
    assert _missing(pairs, kinds - {"memory.rem"}, ops) == ["memory.rem"]
    assert _missing(pairs, kinds, ops - {"reinforce"}) == ["reinforce"]
