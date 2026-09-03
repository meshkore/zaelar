"""nucleo/errand_continuity.py — a follow-up is not a new errand, and a DELIVERED hunt is not re-hunted
in parallel (V2-566 inheritance + V2-570 linear gate).

Extracted from `dispatch.run_listener` when adding the linear gate: dispatch sat ONE line under its
architecture-ratchet ceiling, and the table calls for extracting a concern, not raising the number. This is
a cohesive one — «what does a NEW escalation continue, and what follows from that» — with two answers:

  1. INHERITANCE (V2-566, moved here verbatim): an escalation that continues a just-ended errand inherits
     its results sheet instead of opening a second box beside it. The pool now also carries the listing
     fast-pass DELIVERIES (`workers/ended.note_listing_delivery`): measured on session 9dcff6f5 (2026-09-03,
     the catamaran errand), a fast pass delivered 20 rows and seven seconds later the model escalated the
     same hunt — `dedup_miss` said `live: 0`, because a fast pass is not a session, and the worker opened a
     SECOND sheet. The existing matcher (`dedup.continues_ended`), unchanged, links the two (containment
     0.6 > bar 0.45, verified on the session's own strings); it only ever lacked the snapshot.

  2. THE LINEAR GATE (V2-570, the operator's doctrine, his words from that session): a search resolves
     LINEARLY — the fast pass delivers and THAT is the answer; deeper machinery runs only when the module
     itself judges a pass insufficient or the operator pushes again. So the FIRST escalation that continues
     a just-DELIVERED fast pass does not spawn a worker: the fast pass re-runs with the escalation's full
     request as the refined query, into the inherited sheet, and `listing_turn.run` keeps its own verdict —
     enough → a pushed note names the rows (the route that arrives 3/3, V2-222); not enough → it escalates
     BY ITSELF carrying the same sheet, and the consumed refinement mark lets that one through to a worker.

Cost asymmetry, said out loud: a wrong redirect costs one ≤10 s fast pass and the next escalation passes;
a wrong spawn costs minutes, dollars and a second box — which is what was measured. The gate never fires
for `web`/`code`/`dev`/`memory` kinds: booking or acting on a site is a different errand even when its
words contain the hunt's, and `_classify_kind` (V2-486's tested classifier) already draws that line —
no new phrase lists.

Fail-soft throughout: continuity is worth nothing if it can drop an escalation.
"""
from __future__ import annotations

import asyncio

from loguru import logger

#: Kinds the linear gate never redirects: they ACT (on a site, on code, on memory) rather than search, and
#: turning an action order into another search would be worse than the duplicate it prevents.
_NO_REDIRECT_KINDS = frozenset({"web", "code", "dev", "memory"})


def inherit_and_maybe_rerun(request: str, kind: str, ctx: dict, key: str) -> tuple[dict, bool]:
    """The continuity decision for one NEW escalation, called by `dispatch.run_listener` after the dedup miss.

    Returns `(ctx, redirected)`. `ctx` may come back with `ctx["sheet"]` set (inheritance); `redirected` True
    means the linear gate took the errand — the caller closes the flow and does NOT spawn a session, because
    `_rerun` is already running the refined fast pass into the inherited box.
    """
    if str(ctx.get("sheet", "") or ""):
        return ctx, False               # the escalation already declared its box (e.g. listing auto-escalate)
    try:
        from nucleo import dedup as _dedup
        from nucleo.workers import ended as _ended
        pool = list(_ended._ENDED_SESSIONS.values()) + _ended.recent_listing_deliveries()
        sheet_prev, ev = _dedup.continues_ended(request, kind, pool)
        if not sheet_prev:
            return ctx, False
        ctx = dict(ctx)
        ctx["sheet"] = sheet_prev
        try:
            from voice.observer import emit
            emit("task", "sheet_inherited", role="system", text=request[:120],
                 extra={"id": key, "from": ev.get("from", ""), "sheet": sheet_prev,
                        "by": ev.get("by") or "", "best": ev.get("best", 0.0),
                        "reason": "continúa un encargo recién terminado: misma hoja, no una segunda caja"})
        except Exception:  # noqa: BLE001
            pass
        _from = str(ev.get("from") or "")
        if (_from.startswith("listing:") and kind not in _NO_REDIRECT_KINDS
                and _ended.consume_listing_refinement(_from)):
            try:
                from voice.observer import emit
                emit("task", "linear_rerun", role="system", text=request[:120],
                     extra={"id": key, "from": _from, "sheet": sheet_prev,
                            "reason": "misma caza YA entregada por la pasada rápida: se afina en la misma "
                                      "caja en vez de abrir un worker en paralelo (doctrina lineal)"})
            except Exception:  # noqa: BLE001
                pass
            asyncio.create_task(_rerun(request, sheet_prev), name=f"linear-rerun-{key}")
            return ctx, True
    except Exception as e:  # noqa: BLE001 — continuity must never drop an escalation
        logger.warning(f"errand_continuity: la decisión de continuidad falló, la escalada sigue ({e!r})")
    return ctx, False


async def _rerun(request: str, sheet: str) -> None:
    """The gate's refined fast re-run: same hunt, the escalation's FULL request as the query, SAME box.

    The verdict stays with the module (V2-556's principle, extended to cover the model's stray escalation):
    a delivery is announced by PUSHED note — the route measured 3/3 against the prompt line's 0/13 (V2-222) —
    and an insufficient pass escalates by itself from inside `run`, carrying this very sheet.
    """
    try:
        from nucleo.flash import listing_turn
        res = await asyncio.to_thread(listing_turn.run, request, operator_text=request, sheet=sheet)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errand_continuity: la re-pasada rápida falló ({e!r})")
        return
    try:
        if res.get("delivered"):
            from voice import brain_notes
            rows = str(res.get("ctx") or "").strip()
            n = int(res.get("n") or 0)
            brain_notes.push(
                f"[SISTEMA] La búsqueda afinada ya está hecha: {n} anuncios reales en su hoja, en pantalla "
                "(la misma que ya tenía abierta). NÓMBRALE en este turno los mejores con su precio; si "
                "alguno no encaja con lo que pidió, dilo — no ofrezcas como resultado lo que no responde a "
                "su encargo, y no digas que sigues buscando." + (f"\n{rows}" if rows else ""))
    except Exception:  # noqa: BLE001
        pass
