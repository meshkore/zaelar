"""An errand's events survive a refactor of the files that emit them (V2-826 §2b, refactor2710-09).

The guard `test_an_event_survives_a_move.py` keeps for connectors/server and `test_a_memory_event_survives_a_move.py`
for memory, over the three packages this section moved: `nucleo/dispatch/` (nine top-level files folded into one
package), `nucleo/workers/` (backends into `providers/`, the session split by record/events/ending, the research
brief moved in) and `nucleo/errands/`. Frozen: the (kind, label) pairs emitted with literal arguments, the kinds
emitted at all, and the phases of the session's chips (`_emit_chip`). A pair may move between files, never vanish;
one retired on purpose leaves this set in the same commit, with the reason.

Measured 2026-10-28 against `origin/main` before the move (the `dispatch*.py` files, `research.py`, the flat
`workers/` and `errands/`): the same 25 pairs and the same kinds; the section adds `spec/reach vs spec`, the verdict of
the worker's first step (V2-825 F6).
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
ROOTS = ("nucleo/dispatch", "nucleo/workers", "nucleo/errands", "nucleo/circuit")   # circuit: the worker's goal (02)

FROZEN = {
    ("alert", "🕶️ worker CIEGO — sin herramientas de búsqueda"), ("alert", "🧯 worker sin proveedor en contenedor"),
    ("spec", "reach vs spec"), ("task", "alive"), ("task", "blocked"), ("task", "cancel"), ("task", "considered"),
    ("task", "dedup"), ("task", "dedup_miss"), ("task", "end"), ("task", "phase"), ("task", "plan"),
    ("task", "progress"), ("task", "provider_asleep"), ("task", "resume"), ("task", "⏳ rate limit — waiting it out"),
    ("task", "⚠️ contexto casi lleno"), ("task", "⚠️ el worker chocó con una puerta de permiso"),
    ("task", "🎯 objetivo declarado — así se medirá si está hecho"), ("task", "🏷️ encargo nombrado"),
    ("task", "💬 worker"), ("task", "📋 delivery names the options it owes"),
    ("task", "🔁 búsqueda → la de Zaelar (cuota del proveedor agotada)"), ("task", "🔁 worker reiniciado tras colgarse"),
    ("task", "🔔 entrega dicha en voz — su aviso al cerebro se retira"), ("widget", "close"),
}
#: Kinds emitted at all (many with a computed label), and the phases the session's chips paint.
FROZEN_KINDS = {"alert", "errand", "perf", "spec", "task", "widget", "worker_start", "↩️ encargo reabierto",
                "🎯 encargo abierto", "comando no permitido", "contexto agotado", "contexto casi lleno", "done", "end",
                "phase", "result", "start"}


def _emitted() -> tuple[set, set]:
    pairs, kinds = set(), set()
    for root in ROOTS:
        for p in (ENGINE / root).rglob("*.py"):
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if not isinstance(n, ast.Call):
                    continue
                name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if name not in ("emit", "_emit", "emit_sync", "_emit_d", "_emit_chip") or not n.args \
                        or not isinstance(n.args[0], ast.Constant) or not isinstance(n.args[0].value, str):
                    continue
                kinds.add(n.args[0].value)
                if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
                    pairs.add((n.args[0].value, n.args[1].value))
    return pairs, kinds


def _missing(pairs: set, kinds: set) -> list:
    return sorted(FROZEN - pairs) + sorted(FROZEN_KINDS - kinds)


def test_no_frozen_event_vanishes_from_dispatch_workers_or_errands():
    assert not _missing(*_emitted()), f"an errand event stopped being emitted: {_missing(*_emitted())}"


def test_disarm_a_dropped_event_is_named():
    pairs, kinds = _emitted()
    assert _missing(pairs - {("spec", "reach vs spec")}, kinds) == [("spec", "reach vs spec")]
    assert _missing(pairs, kinds - {"worker_start"}) == ["worker_start"]
