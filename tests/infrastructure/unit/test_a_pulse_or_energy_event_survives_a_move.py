"""The pulse's, the energy's and the CLIs' events survive the move out of the top of `nucleo/` (V2-826 §2b, refactor2710-10).

The sibling of `test_an_errand_event_survives_a_move.py` for the packages this section built: `nucleo/pulse/` (the loop
split into loop/workers/flows/due/signals, plus scheduler, sparks, homeostasis, wake, cron_api, rehydrate, notices,
webpush, notice_today), `nucleo/energy/` (meter, lease, tariffs, limits, routing, account, egress, keys) and
`nucleo/cli/` (the worker CLIs, worker_api, worker_policy, sandbox, usage), with `nucleo/workers/source_outcomes.py`.
Frozen: the (kind, label) pairs emitted with literal arguments and the kinds emitted at all. A pair may move between
files, never vanish; one retired on purpose leaves this set in the same commit, with the reason.

Measured 2026-10-28 against the flat files at the section's base (0bcc5b7d0): the same 7 pairs and 28 kinds.

Disarm: rename one literal kind in `nucleo/pulse/workers.py` (say `worker.stuck`) → the test names it.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
ROOTS = ("nucleo/pulse", "nucleo/energy", "nucleo/cli")
FILES = ("nucleo/workers/source_outcomes.py",)

FROZEN = {
    ("degraded", "motor LiveKit degradado (bucle WebRTC) — reciclando en frío"), ("energy", "saldo"),
    ("recycle", "motor LiveKit reciclado (worker embebido re-registrado)"), ("start", "latido autónomo en marcha"),
    ("task", "⏰ aviso programado"), ("task", "✂️ se cortó al reiniciar y no la reanudo"),
    ("task", "🔁 lo reanudo — se cortó al reiniciar"),
}
FROZEN_KINDS = {
    "alert", "degraded", "energy", "evict", "homeostasis", "loop.chat_digest", "loop.consolidated", "loop.rem",
    "loop.scheduled_fired", "loop.spark", "loop.tick", "notice", "notify", "recycle", "rotate", "start", "task",
    "task.reconciled", "widget", "worker.ask", "worker.budget_kill", "worker.budget_nudge", "worker.report_demanded",
    "worker.say", "worker.stuck", "📋 informe de estado exigido", "🥶 worker sin señales", "🧹 tareas huérfanas cerradas",
}


def _emitted() -> tuple[set, set]:
    pairs, kinds = set(), set()
    paths = [p for root in ROOTS for p in (ENGINE / root).rglob("*.py")] + [ENGINE / f for f in FILES]
    for p in paths:
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(n, ast.Call):
                continue
            name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if name not in ("emit", "_emit", "emit_sync", "_emit_d", "_observe", "_note") or not n.args \
                    or not isinstance(n.args[0], ast.Constant) or not isinstance(n.args[0].value, str):
                continue
            kinds.add(n.args[0].value)
            if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
                pairs.add((n.args[0].value, n.args[1].value))
    return pairs, kinds


def test_no_frozen_event_vanishes_from_pulse_energy_or_cli():
    pairs, kinds = _emitted()
    missing = sorted(FROZEN - pairs) + sorted(FROZEN_KINDS - kinds)
    assert not missing, f"an event the observability viewer reads stopped being emitted by the moved code: {missing}"
