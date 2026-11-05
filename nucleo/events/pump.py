"""The pulse's EVENT beat: the one subscriber per source, the one router, the route obeyed (V2-851 F4, §7).

Each beat drains the bus topics an event comes from (an inbound message — mail is its own stream —, a worker that
ended, a worker that asked), turns each into an event (`nucleo/events.event`), asks `flow_of.route(event=…)` and
obeys: RESUME a row that waits for it (its session relaunched by id with the event as its re-brief) or hand it to
the claimant that owns it (an errand bound to that conversation, `errands.watch`); STREAM it to the worker of the
rules that subscribe to it; NOTHING leaves the source's own handling standing (the messaging triage, the delivery).
A cron's due job is routed through the same door from `pulse/due` (`publish`). Every route is recorded once
(`flow` event, literal label). Never raises: an event that cannot be routed is left to its source.
"""
from __future__ import annotations

import time

from loguru import logger

from nucleo import events as _events

_subs: dict = {}
_OBEY: dict = {}          # claimant name -> obey(claim, ev, now)


def obeys(name: str, fn) -> None:
    """What a claimant does with an event the router gave it (registered beside its `flow_events.claimant`)."""
    _OBEY[str(name)] = fn


def start() -> bool:
    if _subs:
        return True
    try:
        import bus
        from connectors.messaging import ingest
        _subs["msg"] = bus.subscribe(ingest.TOPIC_MSG)
        _subs["done"] = bus.subscribe(_events.WORKER_DONE)
        _subs["ask"] = bus.subscribe(_events.WORKER_ASK)
        return True
    except Exception as e:  # noqa: BLE001 — no bus (a bare self-host): nothing arrives, nothing is routed
        logger.debug(f"events: no bus ({e!r})")
        _subs.clear()
        return False


def stop() -> None:
    for s in list(_subs.values()):
        try:
            s.close()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"events: a subscription did not close ({e!r})")
    _subs.clear()


def _drain(name: str) -> list:
    q = getattr(_subs.get(name), "queue", None)
    out = []
    while q is not None:
        try:
            out.append(q.get_nowait())
        except Exception:  # noqa: BLE001 — empty
            break
    return out


def _arrived() -> list[dict]:
    out = [_events.of_message(m) for m in _drain("msg") if isinstance(m, dict) and m.get("platform")]
    out += [_events.event(_events.WORKER_DONE, key=str(p.get("id") or ""), ok=bool(p.get("ok")),
                          status=str(p.get("status") or "")) for p in _drain("done") if isinstance(p, dict)]
    out += [_events.event(_events.WORKER_ASK, key=str(p.get("task_id") or p.get("id") or ""),
                          text=str(p.get("question") or p.get("text") or ""), ask_id=str(p.get("ask_id") or ""))
            for p in _drain("ask") if isinstance(p, dict)]
    return out


async def tick(now: float | None = None) -> int:
    """One beat: the stream's budget and held items, then every event that arrived. Returns how many were routed."""
    now = time.time() if now is None else now
    from nucleo.events import stream
    stream.supervise(now)
    stream.drain()
    if not start():
        return 0
    n = 0
    for ev in _arrived():
        await publish(ev, now=now)
        n += 1
    return n


async def publish(ev: dict, *, now: float | None = None) -> dict:
    """Route ONE event and obey the route. The entry for any source (`pulse/due` for a cron's job)."""
    now = time.time() if now is None else now
    from nucleo.turn import flow_events, flow_of
    r = await flow_of.route(event=ev)
    how = r.get("as")
    try:
        if how == flow_events.RESUME and r.get("by") == "row":
            from nucleo.cli import worker_api_resume as _resume
            _resume.resume_soon(str(r["task"]), {"answer": f"[{ev['origin']}] {ev.get('text') or ''}"[:600]},
                                src="event")
        elif how == flow_events.RESUME:
            fn = _OBEY.get(str(r.get("by") or ""))
            if fn is not None:
                fn(r.get("claim"), ev, now)
        elif how == flow_events.STREAM:
            from nucleo.events import stream
            stream.deliver(ev, list(r.get("rules") or []))
    except Exception as e:  # noqa: BLE001 — the source's own handling stands
        logger.warning(f"events: route {how} not obeyed — {type(e).__name__}: {e}")
    if how != flow_events.NOTHING:
        _said(ev, r)
    return r


def _said(ev: dict, r: dict) -> None:
    try:
        from voice.observer import emit
        emit("flow", "🧵 an event is routed", role="system", text=str(ev.get("text") or "")[:160],
             extra={"cat": "events", "origin": ev.get("origin"), "key": ev.get("key"), "as": r.get("as"),
                    "by": r.get("by", ""), "task_id": r.get("task", ""),
                    "rules": [x.get("id") for x in (r.get("rules") or [])]})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"events: route not recorded — {e!r}")
