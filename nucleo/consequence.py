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

import functools
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from typing import NamedTuple


class Door(NamedTuple):
    name: str
    funnel: str          # module:function — the one place that asks before the effect


#: Every effect that leaves the turn, with the funnel that must ask. One record per door.
DOORS: dict[str, Door] = {d.name: d for d in (
    Door("worker.spawn", "nucleo.acts.errand:escalate_to_slowbrain"),
    Door("worker.inject", "nucleo.dispatch.soon:inject_soon"),
    Door("worker.stop", "nucleo.dispatch.soon:cancel_soon"),
    Door("worker.settle", "nucleo.dispatch.soon:settle_soon"),
    Door("worker.answer", "nucleo.cli.worker_api:answer_active_soon"),
    Door("widget.data", "widgets.server_api:brain_action"),
    Door("sheet.rebuild", "widgets.results.rehydrate:sheet_from_task"),
    Door("web.login", "nucleo.flash.web_auth:start"),
    Door("music", "connectors.music:control"),
    Door("cron.create", "nucleo.pulse.scheduler:create"),
    Door("cron.cancel", "nucleo.pulse.scheduler:cancel"),
    Door("rules.write", "rules.shape:write"),
    Door("cluster.send", "connectors.meshkore:dispatch_tag"),
    Door("architect.send", "connectors.architect:dispatch_tag"),
    Door("messaging.tag", "connectors.messaging:dispatch_tag"),
    Door("speech.out_of_band", "voice.proactive:notify"),
    Door("speech.speaker", "voice.proactive:speaker"),
    Door("tasks.intake", "nucleo.batch:intake"),
    Door("memory.ingest", "nucleo.memory_agent.ingest:ingest_utterance"),
    Door("vault.write", "voice.engine.llm.providers.vault_intercept:try_vault_intercept"),
)}

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
    row = {"door": door, "blocked": blocked, "verdict": "veto" if blocked else "pass", "dry": bool(_blocked.get()),
           "reason": "closed for this turn" if blocked else "",
           **{k: (v if isinstance(v, (str, int, float, bool)) or v is None else str(v)[:200]) for k, v in what.items()}}
    ledger = _ledger.get()
    if ledger is not None:
        ledger.append(row)
    _observe(row)
    if not blocked:
        _note_reached(door)
    return not blocked


#: The doors each turn (by its trace) went THROUGH, bounded: «did this turn start or reach an errand?» is read here,
#: once, instead of from the flags each lane keeps (refactor2710-99: a worker started by a fallback lane was counted
#: by none of them, and the turn said «not done» over a running errand).
_REACHED: dict[str, set] = {}


def _note_reached(door: str) -> None:
    try:
        from voice import trace as _trace
        if (t := _trace.current()):
            _REACHED.setdefault(t, set()).add(door)
            while len(_REACHED) > 64:
                _REACHED.pop(next(iter(_REACHED)))
    except Exception as e:  # noqa: BLE001 — a turn that cannot be told apart reads as «nothing reached»
        from loguru import logger
        logger.debug(f"consequence: reach not noted — {e!r}")


def reached(*doors: str, trace: str | None = None) -> bool:
    """Did this turn (its trace, or `trace`) go through any of `doors` — the effect really allowed, not refused?"""
    if trace is None:
        try:
            from voice import trace as _trace
            trace = _trace.current() or ""
        except Exception:  # noqa: BLE001
            trace = ""
    return bool(trace) and bool(_REACHED.get(trace, set()) & set(doors))


def _observe(row: dict) -> None:
    """Every door reached is a `consequence` event on the timeline (the observer stamps the turn's trace), live or
    dry: the verdict of this mechanism is visible where every other one is. Never raises."""
    try:
        from voice import observer
        observer.emit("consequence", row["door"], role="system", extra=row)   # the label IS the door
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never decides a consequence
        from loguru import logger
        logger.debug(f"consequence: event not emitted — {type(e).__name__}: {e}")


def door(name: str, *, neutral=None):
    """A funnel that asks at its own threshold: `@consequence.door("cron.create", neutral=...)`. Closed, the funnel
    does not run and returns `neutral(*args, **kwargs)` (or `neutral` itself when it is not callable) — what the
    caller reads when the effect did not happen. A funnel that must validate BEFORE it decides (escalate refuses
    some commissions) asks `passes()` inside its body instead."""
    if name not in DOORS:
        raise KeyError(f"undeclared consequence door: {name!r}")

    def _neutral(args, kwargs):
        return neutral(*args, **kwargs) if callable(neutral) else neutral

    def wrap(fn):
        what = lambda args: {"arg": str(args[0])[:200]} if args else {}   # noqa: E731 — what the ledger shows
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def run(*args, **kwargs):
                if not passes(name, **what(args)):
                    return _neutral(args, kwargs)
                return await fn(*args, **kwargs)
        else:
            @functools.wraps(fn)
            def run(*args, **kwargs):
                if not passes(name, **what(args)):
                    return _neutral(args, kwargs)
                return fn(*args, **kwargs)
        run.__door__ = name
        return run
    return wrap


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
def recorded(*, closed=()):
    """A live turn whose consequences are recorded: the text channel with `execute=True`. `closed` names the doors
    that still stay shut (a list's own step must not open another list: `tasks.intake`)."""
    for name in closed:
        if name not in DOORS:
            raise KeyError(f"undeclared consequence door: {name!r}")
    ledger: list = []
    t1, t2 = _blocked.set(frozenset(closed)), _ledger.set(ledger)
    try:
        yield ledger
    finally:
        _blocked.reset(t1)
        _ledger.reset(t2)
