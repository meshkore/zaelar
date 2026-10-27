"""The turn's CONSEQUENCE doors, declared once (refactor2710-01 T-02).

A turn decides, and then some of its decisions reach the world: a Brain Worker starts, a card's data changes (a message
leaves through the mail card), a browser opens for a login, music plays, a reminder is scheduled, a rule is written, a
cluster peer receives a message, a line is spoken out of band. Each of those effects passes through ONE funnel, and
each funnel asks this module before acting: `if not consequence.passes("worker.spawn", ...): return <neutral>`.

That question is what makes a DRY turn possible without a second implementation of the turn. The text channel and the
decision bank run the SAME voice turn with `dry_turn()` around it: every door records what it would have done in the
turn's ledger and does nothing. The doors are a table, not an `if dry` per file — `DOORS` names each one with the funnel
that must ask, and a test reads every funnel's source for its question (remove it from one → red).

The flag rides a ContextVar, so whatever the turn spawns with `create_task` or `to_thread` inherits it. A consequence
handed over a bus (a worker started by a listener) is gated at the publisher, which still runs inside the turn.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

#: door → the funnel (module:function) that asks before acting. One entry per effect that leaves the turn.
DOORS: dict[str, str] = {
    "worker.spawn": "nucleo.flash.escalate:escalate_to_slowbrain",
    "worker.inject": "nucleo.dispatch:inject_soon",
    "worker.stop": "nucleo.dispatch:cancel_soon",
    "worker.answer": "nucleo.worker_api:answer_active_soon",
    "widget.data": "widgets.server_api:brain_action",
    "web.login": "nucleo.flash.web_auth:start",
    "music": "connectors.music:control",
    "cron.create": "nucleo.scheduler:create",
    "cron.cancel": "nucleo.scheduler:cancel",
    "rules.write": "rules.shape:write",
    "cluster.send": "connectors.meshkore:dispatch_tag",
    "architect.send": "connectors.architect:dispatch_tag",
    "messaging.tag": "connectors.messaging:dispatch_tag",
    "speech.out_of_band": "voice.proactive:notify",
    "speech.speaker": "voice.proactive:speaker",
    "tasks.intake": "nucleo.batch:intake",
    "memory.ingest": "nucleo.memory_agent.ingest:ingest_utterance",
}

#: The door a dry turn still lets through when its caller asked to keep what he says (`ingest=True`, the default of
#: the text channel): his words reach memory, nothing reaches anyone else.
MEMORY_DOOR = "memory.ingest"

_blocked: ContextVar[frozenset] = ContextVar("consequence_blocked", default=frozenset())
_ledger: ContextVar[list | None] = ContextVar("consequence_ledger", default=None)


def passes(door: str, **what) -> bool:
    """Record that this turn reached `door` and say whether the effect may happen. An undeclared door is a bug, not a
    door: it raises, so a new effect cannot slip in beside the table."""
    if door not in DOORS:
        raise KeyError(f"undeclared consequence door: {door!r} — add it to consequence.DOORS with its funnel")
    blocked = door in _blocked.get()
    ledger = _ledger.get()
    if ledger is not None:
        ledger.append({"door": door, "blocked": blocked,
                       **{k: (v if isinstance(v, (str, int, float, bool)) or v is None else str(v)[:200])
                          for k, v in what.items()}})
    return not blocked


def dry() -> bool:
    return bool(_blocked.get())


@contextmanager
def dry_turn(*, ingest: bool = True):
    """Run what is inside with every door closed (but memory, when `ingest`), and yield the ledger it fills."""
    closed = frozenset(d for d in DOORS if not (ingest and d == MEMORY_DOOR))
    ledger: list = []
    t1, t2 = _blocked.set(closed), _ledger.set(ledger)
    try:
        yield ledger
    finally:
        _blocked.reset(t1)
        _ledger.reset(t2)


@contextmanager
def recorded():
    """A live turn whose consequences are recorded (nothing closed): the text channel with `execute=True`."""
    ledger: list = []
    t = _ledger.set(ledger)
    try:
        yield ledger
    finally:
        _ledger.reset(t)
