"""The router's answer for an EVENT — `flow_of.route(event=…)`, the same door his words go through (V2-851 F4, §7).

An event is a request whose origin is a source (`nucleo/events`). The question is the same as for his words — which
open flow does it belong to — and the answers are three, in order:

  1. a task WAITS for it: a row `waiting_for = event:<topic>` or `event:<topic>:<key>` (`RESUME`, the row), or a
     CLAIMANT of the topic says the event is its own (an errand bound to that conversation, `RESUME` by the claimant);
  2. a rule SUBSCRIBES to it (`rules.subscriptions`, matched on the event's declared fields, its pre-condition a
     declared verdict) → the stream worker (`STREAM`);
  3. else `NOTHING` — the source's own handling stands (the messaging triage, the cron's notice).

Claimants register here (`claimant`) instead of subscribing to the bus themselves: there is ONE subscriber per topic,
the pump, and one router. Never raises: an unreadable route is `NOTHING` and the source's handling stands.
"""
from __future__ import annotations

from loguru import logger

RESUME, STREAM, NOTHING = "resume", "stream", "nothing"
_CLAIMANTS: dict[str, list] = {}      # topic -> [(name, claim(ev) -> dict | None)]


def claimant(topic: str, name: str, claim) -> None:
    """Register `claim(ev)` for `topic`: it returns what claims the event (its own record) or None. Idempotent."""
    lst = _CLAIMANTS.setdefault(str(topic), [])
    lst[:] = [(n, c) for n, c in lst if n != name] + [(name, claim)]


def _waiting_row(ev: dict) -> dict | None:
    from nucleo import events
    from nucleo.circuit import ledger
    topic, key = str(ev.get("origin") or ""), str(ev.get("key") or "")
    wanted = {events.waits_for(topic)} | ({events.waits_for(topic, key)} if key else set())
    rows = ledger.store().tasks_where(states=("waiting",), visible_only=False, limit=200)
    return next((r for r in rows if str(r.get("waiting_for") or "") in wanted and r.get("kind") != "stream"), None)


def _subscribed(ev: dict) -> list[dict]:
    from rules import subscriptions as subs
    topic = str(ev.get("origin") or "")
    if subs.unread_notes():
        subs.shape_notes()                       # his sentences are read once, the first time an event could use them
    hits = [r for r in subs.rows(topic) if subs.matches(r, ev)]
    return [r for r in hits if subs.precondition(r, ev)]


def route(ev: dict) -> dict:
    """THE decision for an event: `{as: resume, task|by, claim}` · `{as: stream, rules}` · `{as: nothing}`. Blocking
    (a note read once, a pre-condition verdict): the pump calls it off the loop."""
    try:
        row = _waiting_row(ev)
        if row is not None:
            return {"as": RESUME, "by": "row", "task": str(row["id"]), "row": row}
        for name, claim in list(_CLAIMANTS.get(str(ev.get("origin") or ""), ())):
            got = claim(ev)
            if got:
                return {"as": RESUME, "by": name, "claim": got}
        subs = _subscribed(ev)
        if subs:
            return {"as": STREAM, "rules": subs}
    except Exception as e:  # noqa: BLE001 — the source's own handling stands
        logger.warning(f"flow_events: route unreadable, nothing — {type(e).__name__}: {e}")
    return {"as": NOTHING}
