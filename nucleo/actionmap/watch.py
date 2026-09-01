"""nucleo/actionmap/watch.py — is the map any good? (V2-539)

The map logs its HITS at the moment they execute. What it could not show is the other half of the
question — **what it is missing**: phrases the operator says often that the model resolves with a single
canvas action, i.e. exactly the turns that should have been a table lookup and instead cost a full model
turn. Without that signal, "are we mapping well?" can only be answered by reading transcripts by hand.

Plugged in ONLY through the bus (`turn.completed`), the Susurro pattern: zero coupling with the voice
provider, and it covers BOTH channels for free — `voice/observer.py::turn_detail` is the single place
where the voice turn and the probe turn close, so one subscriber sees both.

It OBSERVES and nothing else: no rows are written, no entry is promoted. Growing the table from what is
seen here is Phase 2 (`actionmap_define` + shadow mode); this module exists so that phase starts from
measured evidence instead of intuition.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("zaelar.actionmap")

_tasks: list = []

# A turn is a MAP CANDIDATE when the model did exactly what a table entry does: one canvas action, no
# work behind it, nothing to say. Any of these keys being truthy means the turn needed understanding —
# a worker, a search, a confirmation, a question — which the map must never attempt.
_DISQUALIFYING = ("escalated", "searched", "worker_acted", "data_done", "confirm_opened", "clarify")

# A pure command turn says little or nothing ("Ya está", "Hecho"). Above this, the operator asked for
# something the reply carried — content the map cannot produce.
_MAX_REPLY_CHARS = 60


# The probe channel writes a DIFFERENT decision dict through the same seam (it reports an `action` string
# instead of the voice provider's flags), so a reader that knows only one shape is blind to a whole channel —
# and the probe is the one the use-case platform drives, i.e. where most measuring happens. Caught live:
# «muéstrame la mensajería» resolved to a single `show_widget` and produced no candidate at all.
_PROBE_OK_TOOLS = {"show_widget", "widget_data", "show_panel"}


def _probe_candidate(decision: dict) -> str:
    """Probe shape: `{action, tool_calls, tags, reply}`. The `action` string already collapses the turn."""
    action = str(decision.get("action") or "")
    if not (action.startswith("canvas:show:") or action == "canvas:close"):
        return ""
    # A canvas verb reached alongside anything heavier is not one entry's job. `_PRIORITY` in the router
    # already collapses, so an extra tool here means the turn did more than open a card.
    if any(t not in _PROBE_OK_TOOLS for t in (decision.get("tool_calls") or [])):
        return ""
    if len(str(decision.get("reply") or "")) > _MAX_REPLY_CHARS:
        return ""
    return action


def _candidate_reason(decision: dict) -> str:
    """'' if this turn is not a map candidate, else the action it resolved to. Understands BOTH channels."""
    if not isinstance(decision, dict):
        return ""
    if decision.get("actionmap"):
        return ""                                   # the map already served it — that is a hit, not a miss
    if "widget_acted" not in decision:              # not the voice shape → the probe's
        return _probe_candidate(decision)
    if any(decision.get(k) for k in _DISQUALIFYING):
        return ""
    if not decision.get("widget_acted"):
        return ""
    if len(str(decision.get("reply") or "")) > _MAX_REPLY_CHARS:
        return ""
    shown = decision.get("shown_ids") or []
    if len(shown) > 1:
        return ""                                   # several targets in one turn: not one entry's job
    return f"canvas:show:{shown[0]}" if shown else "canvas:close"


async def _consume_turns(q) -> None:
    while True:
        try:
            payload = await q.get()
        except asyncio.CancelledError:
            raise
        except Exception:
            continue
        try:
            user = str((payload or {}).get("user") or "").strip()
            decision = (payload or {}).get("decision") or {}
            if not user:
                continue
            from . import enabled, match
            if not enabled():
                continue
            action = _candidate_reason(decision)
            if not action:
                continue
            # Already in the table but it did not fire → the entry exists yet something upstream took the
            # turn (a pending fragment chain, an unresolvable target). That is a DIFFERENT problem from a
            # missing entry, and conflating the two is how a table looks healthy while never being used.
            known = match(user) is not None
            from voice.observer import emit
            emit("actionmap", "🕵️ map candidate: the model resolved a single action",
                 text=user[:160], role="system",
                 extra={"cat": "flash", "action": action, "origin": "flash",
                        "known_entry": known, "phrase": user[:160]})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"actionmap watch: {e!r}")


def start() -> None:
    """Subscribe in the current loop (server lifespan). Idempotent; never raises into the caller."""
    global _tasks
    if _tasks:
        return
    try:
        from . import enabled
        if not enabled():
            logger.info("actionmap watch: disabled (config/env)")
            return
        import bus
        loop = asyncio.get_event_loop()
        _tasks = [loop.create_task(_consume_turns(bus.subscribe("turn.completed")))]
        from voice.observer import emit
        emit("actionmap", "🗺️ action map WATCHING (candidates + quality)", role="system",
             extra={"cat": "flash"})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"actionmap watch start failed (voice/chat unaffected): {e!r}")


async def stop() -> None:
    global _tasks
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    _tasks = []
