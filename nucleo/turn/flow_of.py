"""Which open flow does a request belong to? — the one answer every door that CREATES work asks first (V2-784 F2).

The product's promise is that each request lands in its flow. Until now that was decided after the fact: the
dispatcher's dedup folded a duplicate escalation into a live worker (`dispatch_listener`), continuity inherited
an ended errand's sheet (`errand_continuity`) — both AFTER the turn had already opened a sheet. Measured on the
operator's demo pass (2026-10-21 19:23): a fragment launched a hunt, the full sentence launched a second one,
the dedup folded the second worker into the first and left the second sheet open with nobody behind it.

This is the same question asked BEFORE anything is opened, over every open flow at once — live workers, errands
parked on a question to him, escalations and fast passes in flight (`named_errand.known`, which reads
`errand_pool` and `launches`), and fast passes that just delivered. Not just the last trace: a question about the
weather in between does not hide the monitor hunt.

Two judges, the house ones, in order: the dedup's containment yardstick (`errands_of_a_turn.same_errand`,
microseconds — the fragment-inside-the-sentence case), then the model judge the dispatcher already uses
(`dedup.about_a_live_errand`) for a refinement that shares few words with its errand («under 350»). Fail-open in
the same direction as the dispatcher: an unreadable judge answers «no flow», and the door opens a new one.
"""
from __future__ import annotations

import asyncio

from loguru import logger

#: The model judge runs INSIDE a turn here (the dispatcher's copy runs after it), so it gets a turn-sized budget;
#: past it the answer is «no flow» — the dispatcher's dedup still stands behind, as an alarm (V2-784 F4).
JUDGE_S = 3.0


def candidates() -> list[dict]:
    """Every open flow a request can belong to. Same entry shape as `named_errand.known()`, plus `delivered`."""
    from nucleo.turn import named_errand as _ne
    out = list(_ne.known())
    try:
        from nucleo.turn.errands_of_a_turn import same_errand
        from nucleo.workers import ended as _ended
        for d in _ended.recent_listing_deliveries():
            goal = str(d.get("goal") or "")
            if goal and d.get("sheet") and not any(same_errand(goal, str(e.get("request") or "")) for e in out):
                out.append({"id": f"delivered:{d.get('id')}", "request": goal, "sheet": str(d["sheet"]),
                            "delivered": True, "parked": False})
    except Exception as e:  # noqa: BLE001 — a reader never breaks a turn
        logger.debug(f"flow_of: deliveries unreadable — {type(e).__name__}: {e}")
    return [c for c in out if str(c.get("request") or "").strip()]


def kind(flow: dict) -> str:
    """How a request JOINS this flow: «worker» (inject), «sheet» (re-run into its sheet), or «none»."""
    fid = str(flow.get("id") or "")
    if not flow.get("parked") and not flow.get("starting") and not flow.get("delivered") and ":" not in fid:
        return "worker"
    return "sheet" if str(flow.get("sheet") or "").strip() else "none"


def lexical(text: str, pool: list[dict]) -> dict | None:
    from nucleo.turn.errands_of_a_turn import same_errand
    hits = [c for c in pool if same_errand(text, str(c.get("request") or ""))]
    return hits[0] if hits else None


async def flow_of(text: str, *, emit=None) -> dict | None:
    """The open flow `text` belongs to, or None (a new flow). Never raises; costs nothing with no flow open."""
    text = str(text or "").strip()
    pool = candidates() if text else []
    if not pool:
        return None
    hit, by = lexical(text, pool), "containment"
    if hit is None:
        try:
            from nucleo import dedup as _dedup
            tid = await asyncio.wait_for(asyncio.to_thread(
                _dedup.about_a_live_errand, text, [(str(c["id"]), str(c["request"])) for c in pool]), JUDGE_S)
        except Exception as e:  # noqa: BLE001 — fail-open: no flow, the door opens a new one
            logger.warning(f"flow_of: the judge failed, treating as a new flow — {type(e).__name__}: {e}")
            tid = ""
        hit, by = next((c for c in pool if str(c["id"]) == tid), None), "model"
    if hit is not None and emit is not None:
        emit("flow", "🧵 la petición es de un flujo abierto", role="system", text=f"{text[:100]} → {hit['request'][:100]}",
             extra={"cat": "flash", "flow": hit.get("id"), "sheet": hit.get("sheet", ""), "by": by,
                    "join": kind(hit)})
    return hit


async def join(text: str) -> dict:
    """The listing door's use of `flow_of`: `{}` for a new flow; `{flow, sheet}` to re-run into an open flow's
    sheet; `{flow, sheet, injected: True}` when a live worker took the request as a refinement. Never raises."""
    try:
        from voice.observer import emit
    except Exception:  # noqa: BLE001 — a headless caller has no timeline
        emit = None
    flow = await flow_of(text, emit=emit)
    if flow is None:
        return {}
    how = kind(flow)
    if how == "worker":
        try:
            from nucleo import dispatch as _d
            if await _d.inject(str(flow["id"]), str(text)):
                return {"flow": flow["id"], "sheet": str(flow.get("sheet") or ""), "injected": True}
        except Exception as e:  # noqa: BLE001 — a failed inject falls back to its sheet, never to a second one
            logger.warning(f"flow_of: inject into {flow.get('id')} failed — {type(e).__name__}: {e}")
    return {"flow": flow["id"], "sheet": str(flow.get("sheet") or "")} if flow.get("sheet") else {}


def late_fold(target: str, ctx: dict) -> str:
    """The dispatcher folded an escalation into live errand `target` AFTER the turn acted (V2-784 F3/F4).

    That fold is a backstop now: with `flow_of` asked first it should not fire, so it is an ALARM with its
    evidence, not a silent merge. And it no longer leaks: the escalation's own sheet, when it is not the
    target's, is closed instead of left on screen with nobody writing into it (the 19:23 «Searching in depth…»
    card). Returns the sheet it closed, "" when none. Never raises."""
    own = str((ctx or {}).get("sheet") or "").strip()
    try:
        from nucleo import dispatch as _d
        rec = _d.get_record(target)
        theirs = str(_d.sheet_of(rec) or "") if rec is not None else ""
    except Exception as e:  # noqa: BLE001
        logger.warning(f"flow_of: late fold into {target} — target unreadable: {e}")
        theirs = ""
    orphan = own if own and own != theirs else ""
    try:
        from voice.observer import emit
        emit("alert", "🧵 fusión tardía: la petición llegó al despachador sin pasar por su flujo", role="system",
             text=f"→ {target}" + (f" · hoja huérfana {orphan} cerrada" if orphan else ""),
             extra={"cat": "flash", "flow": target, "orphan_sheet": orphan, "v": "V2-784"})
        if orphan:
            from widgets.results import data as _sheet
            from nucleo.acts import canvas
            canvas.apply("close", _sheet.instance_id(orphan), src="system:flow_of", emit=emit)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"flow_of: could not report/close the late fold into {target}: {e}")
    return orphan
