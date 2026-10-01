"""The voice turn answers a PENDING confirmation: a delete, a restore or a data change the brain asked about, and
the operator's yes or no to it (V2-778 F1, 2026-10-01).

Moved out of `voice/engine/llm/providers/nucleo.py` with no behaviour change. Every module-level name it reads is
read through the provider (`_p.<name>`), so a patch on the provider still governs it, and the provider imports it
back under its name.
"""
from __future__ import annotations

from voice.engine.llm.providers import nucleo as _p


def _resolve_pending_confirm(ok: bool) -> bool:
    """Resolve the pending confirmation (any widget). If `ok`, EXECUTE what was confirmed: a widget DELETION
    (deterministic, including memory) or an irreversible DATA-OP (dispatched by `apply_action`, NEVER code).
    Return True if there was something to resolve.

    MODULE function (not a closure of `_run_inner`, V2-090 addendum 2026-08-15), specifically so it can be called
    ANTES de que el turno haga ningún trabajo lento — ver el hueco real que arregla en el sitio donde se llama
    early, inside `_run_inner`: the old deterministic backstop ran only AFTER the model’s COMPLETE streaming, and a
    turn cancelled by barge-in before reaching it silently lost the “yes” — the confirmation remained pending forever
    and the widget was never touched (real session: “Yes, empty the whole thing.” was cancelled because the operator
    kept speaking; the operator saw “confirm” and the agenda did not change)."""
    try:
        from voice.observer import emit
        p = _p._wconfirm.resolve("", ok)
        if p is None:
            return False
        # Observability (V2-090 addenda): esta respuesta nació en SU PROPIO turno (trace fresco) — antes de
        # ejecutar/cancelar, adopta el trace de la pregunta para que ask→respuesta→acción sean UN flujo, no dos.
        try:
            _ptid = str(p.get("trace_id") or "")
            if _ptid:
                from voice import trace as _trace4
                _trace4.adopt(_ptid)
        except Exception:
            pass
        if not ok:
            emit("brain", "↩️ acción cancelada", text=p.get("widget_id", ""), role="system")
        elif p.get("action") == "data" and isinstance(p.get("op"), dict) \
                and p["op"].get("action") == "connect_cluster":
            try:
                from connectors import meshkore as _mk
                _pl = p["op"].get("payload") or {}
                _p._spawn(_mk.dispatch_tag("cluster.connect", {"data": _pl}), "cluster")
                emit("brain", "🛰 conectando cluster MeshKore (confirmado)", text=_pl.get("name", ""),
                     role="system")
            except Exception:
                pass
        elif p.get("action") == "data" and isinstance(p.get("op"), dict):
            try:
                # V2-743 — `receipt=True`: this is the CONFIRMED path, the one where a false «done» costs
                # something, so the outcome is witnessed against the widget's own view before anything is said.
                _p._spawn(_p._data_ops.dispatch_and_report(p["widget_id"], str(p["op"].get("action") or ""),
                                                     p["op"].get("payload") or {}, receipt=True),
                       "widget-data-confirmed")
                emit("brain", "✅ acción irreversible confirmada", role="system",
                     text=f"{p['widget_id']}:{p['op'].get('action')}")
            except Exception:
                pass
        elif p.get("action") == "delete":
            _p._spawn(_p._wlifecycle.delete_widget(p["widget_id"], "flash"), "widget-delete")
            emit("brain", "🗑️ widget borrado (confirmado)", text=p["widget_id"], role="system")
        elif p.get("action") == "restore":
            _p._spawn(_p._wlifecycle.restore_widget(p["widget_id"], "flash"), "widget-restore")
            emit("brain", "⟲ widget restaurado a la versión de sistema (confirmado)", text=p["widget_id"],
                 role="system")
        return True
    except Exception:
        return False
