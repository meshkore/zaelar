"""nucleo/circuit/write_harness.py — an inline WRITE is checked against the end state his words name, and completed once.

Demo pass 144 (2026-10-19), INIT step «Save Quinn and Rowan in my contacts: Quinn's Telegram is @…, and Rowan's
email is …». The model made ONE `add_contact` (Quinn) and the step said «Done.»; p142 and p143 had made two. Rowan
was never saved, and every send to him later in the run was refused «Rowan isn't in your contacts». A per-call `done_when` cannot
see this: it attests the calls that were made, never the one that was not. The errand path has the loop (goal →
spec → check → retry, V2-776 L1); a turn that wrote on a card in-line had no goal at all.

Now it has the same loop, off the hot path, after the turn's ops ran:
  1. GOAL — `spec.infer` writes the end state of his words (one small call, the errand namer's size);
  2. HARNESS — only rows that must be PRESENT on the very card the turn wrote to are kept (an inferred clause about
     another card, a field or an absence is not this turn's to repair);
  3. CHECK — `spec.attest`; met or unreadable ends it;
  4. ITERATE once — one pass is handed what is missing and may only repeat an action THIS turn already ran on that
     card, never one that leaves (consent ≥ sensitive). Then the spec is attested again, on the timeline.
Both channels call `after_turn`. The model writes the content; the engine owns the bound and the check.
"""
from __future__ import annotations

import asyncio

from loguru import logger

#: How long the turn's own ops get to land before the end state is read.
SETTLE_S = 1.5
_BG: set = set()

_SYS = (
    "You are the brain of a voice assistant. The operator's order below was carried out only IN PART on the card "
    "«{wid}»: what is still missing is listed. Make now the `widget_data` calls that add exactly what is missing — "
    "widget_id «{wid}», only these actions: {allowed}, the payload taken from his words. Never repeat what the card "
    "already holds; if nothing fits, call nothing. Write any text in the OPERATOR's language.\n\nActions of «{wid}»:\n"
    "{actions}\n\nWHAT THE CARD HOLDS NOW:\n{digest}"
)


def _base(wid) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def writes_of(ops) -> list[tuple[str, str]]:
    """The turn's (card, action) pairs that WROTE and stay home: no view, nothing that leaves."""
    from nucleo.flash import data_ops as _do, frontend as _fe
    out: list[tuple[str, str]] = []
    for w, a in ops or ():
        w, a = _base(w), str(a or "").strip()
        if w and a and not _do.is_view_op(w, a) and not _fe.at_least_sensitive(w, a) and (w, a) not in out:
            out.append((w, a))
    return out


def after_turn(order_text: str, ops, *, spec=None) -> None:
    """Schedule the check for this turn's writes. Never raises, never waits."""
    try:
        writes = writes_of(ops)
        order = str(order_text or "").strip()
        if not (writes and order) or order.startswith("[SISTEMA]") or len({w for w, _ in writes}) != 1:
            return
        t = asyncio.ensure_future(check(order, writes, spec=spec))
        _BG.add(t)
        t.add_done_callback(_BG.discard)
    except RuntimeError as e:
        logger.debug(f"write harness: no running loop to schedule on ({e})")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"write harness not scheduled: {type(e).__name__}: {e}")


def goal_on(done_when, card: str, order: str = "") -> dict | None:
    """The inferred end state, cut to rows that must be PRESENT on `card` and that HIS words name — the only part this
    turn can owe. Demo pass 145, INIT: «Remember: … the Tesla insurance renews on March 12…» inferred four agenda
    rows («Ducati insurance renewal», «Tesla next service»…) and the harness wrote three meetings nobody asked for;
    a row is owed only when every value that names it is in what he said."""
    from nucleo.circuit import verify as _verify
    if not done_when:
        return None
    said = " ".join(str(order or "").lower().split())
    kept = [c for c in _verify._clauses(done_when)[1]
            if _verify.kind_of(c) == "rows" and _base(c.get("widget")) == card
            and str(c.get("expect") or "present") == "present"
            and all(" ".join(str(v).lower().split()) in said for v in (c.get("where") or {}).values() if isinstance(v, str))]
    return {"all": kept} if kept else None


async def check(order: str, writes: list, *, spec=None, settle_s: float = SETTLE_S) -> int:
    """Run the loop once; the number of repair calls applied. Never raises."""
    try:
        from nucleo.circuit import spec as _spec, verify as _verify
        card = writes[0][0]
        goal = goal_on(await _spec.infer(order), card, order)
        if not goal:
            return 0
        await asyncio.sleep(settle_s)
        e = _spec.open(goal, text=order, source="turn+inferred", widget=card)
        if _spec.attest(e) is not False:
            return 0
        calls = await _missing_calls(order, card, [a for _, a in writes], _verify.missing(goal), spec=spec)
        from widgets.server_api import brain_action
        for action, payload in calls[: len(goal["all"])]:
            await brain_action(card, action, payload)
        if calls:
            from voice.observer import emit
            emit("brain", "🔁 arnés: la orden pedía más de lo que se hizo — completado", role="system",
                 text=f"{card}: {', '.join(a for a, _ in calls)}", extra={"cat": "flash", "widget": card})
            await asyncio.sleep(settle_s)
            _spec.attest(e)
        return len(calls)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"write harness: {type(e).__name__}: {e}")
        return 0


async def _missing_calls(order: str, card: str, allowed: list, missing: list, *, spec=None) -> list[tuple[str, dict]]:
    """One pass, bounded to the actions this turn already ran on `card`."""
    from nucleo.flash import act_repair as _ar, repair_grounding as _rg, widget_read as _wr
    from nucleo.llm.fast_client import FastClient
    from widgets import runtime as _rt
    tool = _ar._widget_data_tool()
    manifest = _rt.get(card) or {}
    if not tool or not manifest:
        return []
    got: list[tuple[str, dict]] = []
    system = _rg.in_his_lang(_SYS).format(wid=card, allowed=", ".join(allowed), actions=_ar._actions_block(manifest),
                                          digest=str(_wr.read(card) or "")[:1500])
    await FastClient().complete(
        [{"role": "system", "content": system},
         {"role": "user", "content": f"Operator: «{order[:600]}»\nStill missing: {'; '.join(missing)[:600]}"}],
        spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
        on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
    out: list[tuple[str, dict]] = []
    for name, args in got:
        action = str(args.get("action") or "").strip()
        if name == "widget_data" and _base(args.get("widget_id")) == card and action in allowed:
            out.append((action, args.get("payload") if isinstance(args.get("payload"), dict) else {}))
    return out
