"""ONE turn, typed, through the VOICE turn itself (refactor2710-01 T-02).

`run_turn` runs `NucleoLLMStream`'s own turn — the one the microphone runs — without LiveKit: the turn's methods are
borrowed whole and its two seams (the context it reads his line from, the channel it speaks into) are the typed line
and a collector. There is no second implementation of the turn to keep in step.
What the text channel used to change by being a different program it now changes by being a different INPUT (a typed
`Utterance`, complete by construction) and a different CONSEQUENCE policy:

  · `execute=False` runs the turn inside `consequence.dry_turn()`: every door that would reach the world (a worker, a
    card's data, a login, music, a reminder, a send) records what it would have done and does nothing;
  · `ingest=False` closes the memory door too.

The result keeps the shape the text channel always returned — `{ok, reply, action, tool_calls, tags, ...}` — read from
what the turn left behind: the model's calls (`brain._turn_calls`), the canvas events it emitted, its decision record
(`observer.turn_detail`) and the consequence ledger.
"""
from __future__ import annotations

import time

from loguru import logger

from nucleo import consequence

_SESSIONS: dict = {}

def _brain(sid: str):
    from voice import typed_turn
    if sid not in _SESSIONS:
        _SESSIONS[sid] = typed_turn.new_brain()
    return _SESSIONS[sid]


def reset(sid: str | None = None) -> None:
    if sid is None:
        _SESSIONS.clear()
    else:
        _SESSIONS.pop(sid, None)


def _tags(events: list[dict]) -> list[dict]:
    """The canvas steps the turn emitted (the events the screen acts on), as the text channel reports them."""
    canvas = ("show", "close", "fullscreen", "unfullscreen", "minimize", "arrange")
    out = []
    for e in events:
        if e.get("kind") == "widget" and e.get("label") in canvas:
            out.append({"action": e["label"], "extra": {"id": e.get("id") or ""}})
    return out


def _decision(events: list[dict]) -> dict:
    for e in reversed(events):
        if str(e.get("label") or "").startswith("🧾 turno"):
            return dict(e.get("decision") or {})
    return {}


def _action(decision: dict, events: list[dict], ledger: list[dict], tags: list[dict], calls: list[dict]) -> str:
    """The turn's primary act in the text channel's vocabulary (`canvas:show:<id>`, `widget_data:<id>:<op>`, …)."""
    if decision.get("actionmap") is not None and decision.get("action"):
        return str(decision["action"])                    # an action-map lane names its act itself
    doors = [e["door"] for e in ledger]
    if decision.get("escalated") or "worker.spawn" in doors:
        return "escalate"
    names = [c.get("name") for c in calls]
    data = [e for e in events if e.get("kind") == "widget" and str(e.get("label") or "").startswith("data:")]
    # The model ASKED for a card's data-op: that is the act. A data-op the turn made on its own to fill a card it
    # opened (`play_video` loads the player it shows) is part of the show, which is what he saw.
    if data and "widget_data" in names:
        return f"widget_data:{data[0].get('id') or ''}:{data[0].get('action') or data[0]['label'][5:]}"
    if "music" in doors:
        return "music"
    # Several canvas steps in one turn name the one he asked for: a full screen is shown first, «close the messages
    # and show me the agenda» closes first — so the stronger step names the turn, not the earlier one.
    for kind in ("fullscreen", "minimize", "unfullscreen", "show", "close"):
        t = next((t for t in tags if t["action"] == kind), None)
        if t is None:
            continue
        wid = t["extra"].get("id") or ""
        if kind == "unfullscreen":
            return "canvas:unfullscreen"
        return f"canvas:{kind}:{wid}" if wid else f"canvas:{kind}"
    if data:
        return f"widget_data:{data[0].get('id') or ''}:{data[0].get('action') or data[0]['label'][5:]}"
    if decision.get("searched") or "web_search" in names:
        return "search"
    if "search_listings" in names:
        return "listings"
    if "read_widget" in names:
        return "read_widget"
    for e in events:
        if e.get("kind") == "panel":
            return f"panel:{e.get('id') or e.get('label') or ''}"
    if decision.get("clarify"):
        return "clarify"
    return "chat"


async def run_turn(text: str, *, sid: str = "default", ingest: bool = True, model: str = "",
                   execute: bool = False, lists: bool = True) -> dict:
    """One typed turn through the voice turn. Same signature as the text channel always had; `model` and `lists` are
    accepted for its callers: the model is the routing's (`config/v2.py`), and `lists=False` (a list's own step) keeps
    the task-list door shut so a step never opens another list."""
    from voice import attention, observer, typed_turn
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "texto vacío"}
    brain = _brain(sid)
    brain._turn_failed = ""
    attention.note_directed()
    attention.note_typed(text=text)          # a typed line: directed, complete, never ambient
    n0 = len(observer._events)
    t0 = time.time()
    if model:
        logger.info(f"cli.turn: model override {model!r} ignored — the voice turn takes its model from the routing")
    policy = (consequence.recorded(closed=() if lists else ("tasks.intake",)) if execute
              else consequence.dry_turn(ingest=ingest))
    try:
        with policy as ledger:
            reply = await typed_turn.drive(brain, text)
    except Exception as e:  # noqa: BLE001 — the channel reports a failed turn, it never raises
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    events = [dict(e) for e in observer._events[n0:]]
    calls = [dict(c) for c in (getattr(brain, "_turn_calls", None) or [])]
    tags = _tags(events)
    decision = _decision(events)
    # The act is REPORTED, never written back into the brain: `brain._last_action` is the voice turn's own state
    # (it writes «search»/«listings» and reads them to resolve a deictic show), and this channel's vocabulary there
    # would make the next turn resolve differently from the microphone.
    action = _action(decision, events, ledger, tags, calls)
    if brain._turn_failed:            # the model did not answer: reported as the failure it is (CRIT-M4)
        return {"ok": False, "error": brain._turn_failed, "spec": getattr(brain, "_turn_failed_spec", ""),
                "reply": reply, "action": action, "tool_calls": calls, "consequences": ledger}
    secret = next(({"n": e.get("n"), "labels": e.get("labels")} for e in events
                   if e.get("kind") == "secret" and e.get("label") in ("saved", "no_vault")), None)
    return {"ok": True, "reply": reply, "action": action, "tool_calls": calls, "tags": tags,
            **({"secret": secret} if secret else {}),
            "consequences": ledger, "decision": decision, "channel": "pipeline",
            "timings": {"total_ms": round((time.time() - t0) * 1000, 1)},
            "trace": next((e.get("trace") for e in reversed(events) if e.get("trace")), "")}
