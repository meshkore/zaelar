"""An observability event survives a refactor of the file that emits it (V2-826 §2b, refactor2710-13).

Splitting a file moves its `emit(...)` calls; deleting one by accident costs nothing that fails loudly — the
timeline and the Master simply show less. This freezes the (kind, label) pairs `connectors/` and `server/` emit
with literal arguments: a pair may move between files, never vanish. A pair added later passes; a pair retired on
purpose leaves this set in the same commit, with the reason.

Measured 2026-10-28 over the refactored tree; the before/after diff of every emit call in both packages (126 → 118
calls) differed only by folds of the same event — five account connectors' `announce` into one door, the two
hard resets' `widget/close` into one sequence.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

FROZEN = {
    ("cluster", "changed"), ("cluster", "🧠 zaelar"), ("device", "📱 device state"),
    ("error", "cluster.connect: missing 'name'"),
    ("error", "cluster.pact: falta 'to' (con qué agente se pacta) — ignorado."),
    ("flow", "end"), ("memory", "cluster→síntesis"), ("memory", "session lookup failed"),
    ("resource", "🔒 permiso 'code' concedido pero SIN objetivo del operador — dev-worker bloqueado hasta que se fije uno"),
    ("screens", "moved"), ("session", "RESET"), ("spec", "reach"),
    ("widget", "arrange"), ("widget", "close"), ("widget", "data"), ("widget", "show"),
}
#: Kinds emitted with a computed label: the kind itself must survive.
FROZEN_KINDS = {"brain", "client", "cluster", "error", "feedback", "memory", "resource", "session"}


def _emitted() -> tuple[set, set]:
    pairs, kinds = set(), set()
    for root in ("connectors", "server"):
        for p in (ENGINE / root).rglob("*.py"):
            if "whatsapp/bridge/" in p.as_posix():
                continue
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if not isinstance(n, ast.Call):
                    continue
                name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if name == "apply" and n.args and isinstance(n.args[0], ast.Constant):
                    # the canvas door (`nucleo.acts.canvas.apply("<op>", …)`) emits ("widget", "<op>") for its caller
                    kinds.add("widget")
                    pairs.add(("widget", n.args[0].value))
                    continue
                if name not in ("emit", "_emit") or not n.args or not isinstance(n.args[0], ast.Constant):
                    continue
                kind = n.args[0].value
                kinds.add(kind)
                if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                    pairs.add((kind, n.args[1].value))
    return pairs, kinds


def _missing(pairs: set, kinds: set) -> list:
    return sorted(FROZEN - pairs) + sorted(FROZEN_KINDS - kinds)


def test_no_frozen_event_vanishes_from_connectors_or_server():
    assert not _missing(*_emitted()), f"an event stopped being emitted: {_missing(*_emitted())}"


def test_disarm_a_dropped_event_is_named():
    pairs, kinds = _emitted()
    assert _missing(pairs - {("spec", "reach")}, kinds) == [("spec", "reach")]
    assert _missing(pairs, kinds - {"feedback"}) == ["feedback"]
