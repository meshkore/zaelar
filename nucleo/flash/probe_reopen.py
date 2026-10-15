"""The text channel answers `reopen_task` the way the voice turn does — question SAID, report SHOWN (2026-10-14).

Measured on `flat-hunt-recall-the-report` (ES and US, both 1/5). The probe resolved which errand he meant and
reported only the action's NAME: `clarify` carried no question, so the reply fell to the mute backstop («Perdona,
se me ha ido. ¿Me lo dices otra vez?», «Sorry, I lost that») ten turns running, and a resolved errand reported
`canvas:show:results` without rebuilding its sheet or putting it on the canvas — the round ended with zero rows
over a report the task still held.

So the probe now runs the voice turn's own decision (`task_recall.voice_turn`) when it EXECUTES: the sheet comes
back from the task and the card is presented, and on an ambiguity the question names the candidates with the same
phrase the voice uses (`ask_which_item`). A dry run (the routing bench) still only resolves — it reports the
decision and writes nothing.
"""
from __future__ import annotations

import asyncio

from nucleo.flash import task_recall as _task_recall


def _ask_line(cands: str) -> str:
    """The voice's own question («¿Cuál exactamente? Tengo …») in the session's language; empty with no candidates."""
    if not cands:
        return ""
    from i18n import langs as _langs
    return _langs.current_language().ask_which_item.format(cands=cands)


def _present(card: str, verdict: dict) -> None:
    """The card on the canvas and the recall row on the timeline — what the voice's `[[show]]` tag does."""
    from nucleo.flash import canvas_visibility as _cv
    from voice.observer import emit
    _cv.present(card, reason="turn-order", src="flash", emit=emit)
    emit("brain", verdict["label"], role="system", text=verdict["text"], extra=verdict["extra"])


async def action_for(tool_calls, text: str, sess, brief=None) -> dict:
    """`{"action": …}` plus `"spoken"` when the turn has to ASK. Merged by `probe_decide.name_the_action`."""
    q = next((t["args"] for t in tool_calls if t["name"] == "reopen_task"), {}) or {}
    query = str(q.get("query") or "").strip() or text
    if not getattr(sess, "executes", False):
        r = await asyncio.to_thread(_task_recall.resolve, query, heard=text)
        if r.get("ok"):
            return {"action": "canvas:show:results"}
        names = ", ".join(str(x.get("title") or x.get("goal") or "")[:60] for x in (r.get("ask") or [])[:3])
        from nucleo.flash import direct_action as _da
        if not names and _da.verdict_escalates(brief):
            return {"action": "escalate"}
    else:
        v = await asyncio.to_thread(_task_recall.voice_turn, query, text, brief)
        if v["show"]:
            _present(v["show"], v)
            return {"action": f"canvas:show:{v['show']}"}
        if v.get("escalate"):
            from voice.observer import emit
            emit("brain", v["label"], role="system", text=v["text"], extra=v["extra"])
            return {"action": "escalate"}
        names = v["ask"] or ""
    said = _ask_line(names)
    return {"action": "clarify", **({"spoken": said} if said else {})}
