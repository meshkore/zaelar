"""A refusal that names what the call MEANT: one same-turn pass may run one of the card's declared alternatives.

Use case `find-videos-on-a-topic-no-ai-slop` (ES, 2026-10-14): six numbered results on the player's dashboard, the
queue empty, and «Ponme el de Iván, el de José Manuel y el de Jaén». The fast model called `youtube:clear_list`. On
an empty queue that changed nothing, the card answered `ok`, «Hecho.» was said — and two turns later «Te dejo esos
tres en la lista», over a list that never held them. The refusal correction (`act_repair.call_for_refusal`) could
not help even once the card refused: it may only re-issue the SAME action (its bound, for good reasons), and here
the action itself was the misreading.

The card is the one reader that knows its own state, so it is the card that says when a call cannot have meant what
it says: `nothing_queued` refuses `clear_list` over an empty queue with the band on screen and declares
`redirect: [add_results, play_result]`. This module is the pass that reads that declaration: his words, the card's
digest and ONLY the redirect actions offered. It may run one of them on the same card, or nothing — never an action
the card did not name, so the consequence stays bounded by the card. Both channels call it at the same seam as the
refusal correction (`data_ops.dispatch_and_report`, `widget_data_turn.execute`). Never raises.
"""
from __future__ import annotations

_SYS = (
    "You are the brain of a voice assistant. To do what the operator said you called `widget_data` with the "
    "action «{action}» on the card «{wid}», and the card REFUSED it: «{why}». That action cannot have been what he "
    "meant. The card names the actions that act on what it holds: {offered}. If his words ask for one of THOSE, "
    "call it once, with the rows he named taken from what the card holds (their numbers, or their titles). If his "
    "words ask for none of them, call nothing.\n\nThose actions:\n{actions}{card}"
)


def offered(wid: str, res) -> list[str]:
    """The declared actions of `wid` the refusal `res` names as what the call may have meant; [] = none."""
    if not isinstance(res, dict) or res.get("ok") is not False or not isinstance(res.get("redirect"), list):
        return []
    try:
        from widgets import runtime as _rt
        actions = (_rt.get(str(wid).split("::")[0]) or {}).get("actions") or {}
    except Exception:  # noqa: BLE001 — no manifest, nothing to offer
        return []
    return [str(a) for a in res["redirect"] if str(a) in actions]


async def call(text: str, wid: str, action: str, res, *, spec=None) -> dict | None:
    """`{"action", "payload"}` of the alternative his words ask for, or None. Never raises."""
    try:
        names = offered(wid, res)
        if not names or not (text or "").strip():
            return None
        from widgets import runtime as _rt
        from nucleo.flash import act_repair as _ar, widget_read as _wr
        manifest = _rt.get(str(wid).split("::")[0]) or {}
        tool = _ar._widget_data_tool()
        if not tool:
            return None
        digest = str(_wr.read(wid) or "").strip()[:1500]
        sub = {"actions": {n: manifest["actions"][n] for n in names}}
        got: list[dict] = []
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _SYS.format(
                wid=wid, action=action, why=str(res.get("message") or res.get("error") or "")[:300],
                offered=", ".join(names), actions=_ar._actions_block(sub),
                card=_ar._CARD.format(wid=wid, digest=digest) if digest else "")},
             {"role": "user", "content": f"Operator: «{text.strip()[:400]}»"}],
            spec=spec, max_tokens=200, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append(args) if name == "widget_data" and isinstance(args, dict) else None)
        for args in got:
            act = str(args.get("action") or "").strip()
            if act in names and _ar._same_card(str(args.get("widget_id") or wid), str(wid)):
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"action": act, "payload": payload}
        _ar._note(str(wid), "the redirect pass named none of the card's alternatives", action=str(action)[:40])
        return None
    except Exception as e:  # noqa: BLE001 — a repair must never take down a live turn
        from loguru import logger
        logger.debug(f"refusal_redirect.call skipped: {type(e).__name__}: {e}")
        return None


async def retry(wid: str, action: str, payload: dict, res, text: str, dispatch) -> tuple[str, dict, dict] | None:
    """`(action, payload, result)` of the alternative that RAN, or None (today's path). `dispatch` is the channel's own
    way to run a data-op — the same one its refusal correction uses. Never raises."""
    if not offered(wid, res):
        return None
    try:
        alt = await call(text, wid, action, res)
        if not alt:
            return None
        res2 = await dispatch(wid, alt["action"], alt["payload"])
        res2 = res2 if isinstance(res2, dict) else {}
        from voice.observer import emit
        emit("widget", "↪ refused data-op → the alternative the card named", text=str(res.get("message") or "")[:160],
             extra={"id": wid, "action": alt["action"], "refused": action, "refused_payload": payload or {},
                    "payload": alt["payload"], "ok": res2.get("ok") is not False and not res2.get("error")})
        return alt["action"], alt["payload"], res2
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"refusal_redirect.retry skipped: {type(e).__name__}: {e}")
        return None
