"""nucleo/dispatch_confirm.py — the pending-confirmation gate for an IRREVERSIBLE task (V2-126).

Split out of `dispatch.py` in F3 of the 2026-08-23 architecture audit. It was already the cleanest seam in that
file — its own registry, its own TTL, its own vocabulary, and (measured before moving anything) **zero reads of
`_SESSIONS`**, which is what made it safe to move while the rest of the file's seams are not: that registry is
rebound by `monkeypatch` in 26 tests, so a module holding its own reference to it would silently keep the old
dict. Nothing here touches it.

Same contract as `widgets/confirm.py`, the sibling gate for irreversible WIDGET actions: remember the ask, expire
it rather than let it hang forever, and expose a line the FlashBrain can read in its live state. Two registries
on purpose — that one is keyed by widget id and executes through `apply_action`, this one RE-DISPATCHES a worker
task; fusing them would couple two unrelated execution paths for the sake of a shared TTL.

`dispatch.py` re-exports every public name here, so `dispatch.confirm_line()`, `dispatch.resolve_confirm(...)`
and the tests that mutate `dispatch._PENDING_CONFIRM` keep working untouched. Mutation survives a re-export
(same dict object); only REBINDING would not, and nothing rebinds these.
"""
from __future__ import annotations

import logging
import time

from nucleo.workers.session import SessionRecord

logger = logging.getLogger("zaelar.dispatch.confirm")

# Same contract as `widgets/confirm.py` (the sibling gate for irreversible WIDGET actions): remember the ask,
# expire it rather than let it hang forever, and expose a line the FlashBrain can read in its live state. It is
# a separate registry on purpose — that one is keyed by widget id and executes through `apply_action`, this one
# re-dispatches a worker task; fusing them would couple two unrelated execution paths for a shared TTL.
_PENDING_CONFIRM: dict[str, dict] = {}
_CONFIRM_TTL = 300.0     # 5 min. Longer than the widget gate's 90 s: this question ("shall I really pay?")
                         # arrives mid-conversation and the operator may reasonably think about it.


# V2-190 — an expired confirmation is a FACT, and losing it is how a gated task turns into narrated work.
# Measured on `renew-gym-membership__es` (2026-08-20 01:01): the gate parked the renewal, the operator was
# asked, five minutes went by inside a normal conversation, `_sweep_confirm` dropped the entry, `confirm_line()`
# went empty — and from that turn on the state said NOTHING about it. The model fell back on the only thing it
# still had, its own earlier «empiezo already with the renovacion», and answered «sigo without novedades of the web of
# Basic-Fit» about a task whose record read `status=done url= shot_rev=0`: it never opened a single page.
#
# The TTL itself is NOT the bug and is not raised: a «shall I really pay?» answered «si» forty minutes later is
# exactly what it protects against. What was wrong is that expiring the GATE also erased the MEMORY of it. So
# the gate still expires — `resolve_confirm` reads `_PENDING_CONFIRM` and an expired ask can no longer be armed
# by a late yes — and the fact moves here, where the turn can still say it. Same remedy as
# `widgets/browser/tasks.recently_finished()` (V2-150): an ending is a fact.
_EXPIRED_CONFIRM: dict[str, dict] = {}
_EXPIRED_MEMORY_S = 900.0     # 15 min: long enough to outlive the conversation that asked


def _sweep_confirm(now: float | None = None) -> None:
    now = time.time() if now is None else now
    for k in [k for k, v in _PENDING_CONFIRM.items() if now - v["ts"] > _CONFIRM_TTL]:
        _EXPIRED_CONFIRM[k] = {**_PENDING_CONFIRM.pop(k), "expired_at": now}
    for k in [k for k, v in _EXPIRED_CONFIRM.items() if now - float(v.get("expired_at") or 0) > _EXPIRED_MEMORY_S]:
        _EXPIRED_CONFIRM.pop(k, None)


def remember_confirm(task_id: str, request: str, task: "Task", *, sheet: str = "") -> None:
    """Keep the question the gate just asked, so a later «si» has somewhere to go.

    …AND the SHEET it had already opened (V2-508). The gate parks the errand and pops its record, but the
    sheet is on the operator's screen by then: `run_listener` opens it at the moment of the errand, on
    purpose, so nobody stares at a blank canvas. Without carrying it, the «si» relaunches through the normal
    door with no sheet in its context, mints a SECOND box beside the first, and leaves the first one empty
    for good — measured 2026-08-30 (`cheapest-monitor__us`, `results::101c0f-1` abandoned, `-2` filled).

    A CONFIRMED ERRAND IS A CONTINUATION, exactly like the provider relay and the context handoff that
    `_sheet_open` already inherits for: same errand, same request, and the operator is already looking at
    its box."""
    from nucleo import danger as _danger
    _sweep_confirm()
    _EXPIRED_CONFIRM.pop(str(task_id), None)      # se vuelve a preguntar: ya no es un caducado sin respuesta
    _PENDING_CONFIRM[str(task_id)] = {
        "request": request, "kind": (task.kind or "generic"), "trusted": bool(task.trusted),
        "context": dict(task.context or {}), "question": _danger.confirm_question(request),
        "sheet": str(sheet or ""), "ts": time.time()}


def pending_confirm() -> dict | None:
    """The confirmation still waiting for a yes/no, or None. Most recent wins — a second irreversible ask
    supersedes the first, exactly like the widget gate."""
    _sweep_confirm()
    if not _PENDING_CONFIRM:
        return None
    tid = max(_PENDING_CONFIRM, key=lambda k: _PENDING_CONFIRM[k]["ts"])
    return {"task_id": tid, **_PENDING_CONFIRM[tid]}


def confirm_line() -> str:
    """Line for the FlashBrain's live state. Without it the brain has NO idea a task is parked waiting on the
    operator — which is precisely how a gated task turned into narrated progress."""
    p = pending_confirm()
    if not p:
        # V2-190: nothing waiting — but maybe something EXPIRED waiting, and that is not the same as nothing.
        _sweep_confirm()
        if not _EXPIRED_CONFIRM:
            return ""
        _e = max(_EXPIRED_CONFIRM.values(), key=lambda v: float(v.get("expired_at") or 0))
        return (f"UNA CONFIRMACIÓN QUE LE PEDISTE CADUCÓ SIN RESPUESTA: «{str(_e.get('request') or '')[:120]}». "
                f"Esa tarea NUNCA EMPEZÓ y no va a empezar sola — no digas que sigue en marcha ni que esperas "
                f"novedades suyas. Si sale a colación, dilo y ofrece retomarla desde cero.")
    from nucleo import danger as _danger_line
    # If mueve DINERO is says here also (V2-129): the operator already oyo «no hago ningun cargo without decirte the
    # importe», and the turn siguiente no can contradecir esa promesa.
    money = (" MUEVE DINERO: le prometiste decirle el importe exacto ANTES de cobrar nada, así que ni lo pagues"
             " ni digas que está pagado hasta haber mirado la cifra y habértela confirmado él."
             if _danger_line.moves_money(p["request"]) else "")
    return (f"CONFIRMACIÓN PENDIENTE de una acción IRREVERSIBLE: «{p['request'][:120]}».{money} Le preguntaste al "
            f"operador y AÚN NO ha contestado, así que la tarea está PARADA y no ha empezado nada — no digas "
            f"que está en marcha. Si dice que SÍ, arranca; si dice que NO, olvídalo y confírmaselo.")


def resolve_confirm(ok: bool) -> dict | None:
    """Answer the pending confirmation. `True` re-dispatches the SAME request with `confirmed` set (the gate
    lets it through this time); `False` drops it. Returns what was resolved, or None if nothing was pending."""
    p = pending_confirm()
    if not p:
        return None
    _PENDING_CONFIRM.pop(p["task_id"], None)
    if not ok:
        return {**p, "ok": False}
    # Se re-lanza by the MISMA puerta that any escalada (`escalate.requested` → `run_listener`), no by a
    # atajo: so preserves the trace, the dedup and the record of tasks. Lo only distinto es `confirmed`, that es
    # it that the gate mira for dejarla pasar this vez.
    ctx = {**p["context"], "confirmed": True, "kind": p["kind"]}
    # La HOJA of the errand viaja with the «si». `_sheet_open` already sabe heredarla (compara contra the that le tocaria
    # a ESTE task_id: if the that trae no deriva of el, es of su predecesor and no is estrena). Sin this linea the
    # confirmado opens caja new al lado of the that the operator already has delante.
    if p.get("sheet"):
        ctx["sheet"] = str(p["sheet"])
    try:
        from nucleo.flash import escalate as _esc
        _esc.escalate_to_slowbrain(p["request"], context=ctx)
    except Exception:
        logger.warning("resolve_confirm: no se pudo re-lanzar la tarea confirmada")
    return {**p, "ok": True}


async def _deliver_confirm(rec: "SessionRecord") -> None:
    try:
        from voice import proactive
        await proactive.notify("zaelar", rec.result_summary, speak=True)
    except Exception:
        pass


