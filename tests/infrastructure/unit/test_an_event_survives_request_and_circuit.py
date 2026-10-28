"""An event of the request and the circuit survives their refactor (V2-826 §2b, refactor2710-02).

The section moved spec, harness, verify, the deliverable gate, the worker's goal and the ledger into
`nucleo/circuit/`, and request_row, the errand's kind and title, dedup with continuity and the stop decision into
`nucleo/request/`. A move may carry an `emit(...)` to another file; it may never drop it. This freezes what both
packages emit with literal arguments — the (kind, label) pairs, and the first literal argument of the helpers
that fix the kind themselves (`spec._emit(label, …)`, `harness._emit(label, …)`). A pair added later passes; a pair
retired on purpose leaves this set in the same commit, with the reason. The new `verdict` kind (T-00) is here too.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

FROZEN_PAIRS = {
    ("brain", "↪️ his correction → the running errand (steer verdict)"),
    ("brain", "🔁 replace: the stopped errand's place is taken by the one he named"),
    ("task", "linear_rerun"), ("task", "sheet_inherited"),
    ("task", "🎯 objetivo declarado — así se medirá si está hecho"),
    ("widget", "🚫 a card that is not the deliverable stays closed"),
}
#: First literal arguments: the kinds themselves, and the labels a kind-fixing helper takes first.
FROZEN_FIRST = {
    "brain", "spec", "task", "verdict", "widget",
    "🎯 spec: nace con la petición", "✅ spec: cumplida", "❌ spec: sin cumplir todavía",
    "❌ spec: SIN cumplir tras el plazo — se le dice al modelo", "🫥 spec: no verificable — la tarjeta no lo declara",
    "🫥 spec: el encargo no acaba en nada que un widget pueda atestiguar",
    "🎯 arnés: objetivo abierto", "✅ arnés: objetivo conseguido", "🕰 arnés: objetivo caducado sin verificar",
    "⚠️ arnés: afirmó entrega y la hoja sigue VACÍA",
    "🫥 arnés: objetivo NO verificable — la tarjeta no declara si está vacía",
    "🪟 arnés: afirmó que estaba en pantalla y seguía en el dock — la presento",
}


def _emitted() -> tuple[set, set]:
    pairs, first = set(), set()
    for root in ("nucleo/circuit", "nucleo/request"):
        for p in (ENGINE / root).rglob("*.py"):
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if not isinstance(n, ast.Call):
                    continue
                name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if "emit" not in name or not n.args or not isinstance(n.args[0], ast.Constant):
                    continue
                first.add(n.args[0].value)
                if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                    pairs.add((n.args[0].value, n.args[1].value))
    return pairs, first


def _missing(pairs: set, first: set) -> list:
    return sorted(FROZEN_PAIRS - pairs) + sorted(FROZEN_FIRST - first)


def test_no_frozen_event_of_the_request_or_the_circuit_vanishes():
    assert not _missing(*_emitted()), f"an event stopped being emitted: {_missing(*_emitted())}"


def test_disarm_a_dropped_event_is_named():
    pairs, first = _emitted()
    assert _missing(pairs - {("task", "linear_rerun")}, first) == [("task", "linear_rerun")]
    assert _missing(pairs, first - {"verdict"}) == ["verdict"]


def test_the_verdict_event_carries_the_trace_the_doors_carry(monkeypatch):
    """§2b: the verdict a settle emits joins the turn's consequence ledger by its trace."""
    from nucleo.circuit import verdict as V
    from voice import observer
    seen: list = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None: seen.append(
        {"kind": kind, **(extra or {})}))
    V.emit(V.UNMET, text="no row", trace="t-door", uid="r9")
    assert seen == [{"kind": "verdict", "cat": "circuit", "verdict": "unmet", "delivered": False,
                     "row_state": "failed", "trace": "t-door", "uid": "r9"}]
