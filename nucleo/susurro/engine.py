"""Susurro orchestration (V2-053 F1): bus subscription → friction detection → audit cycle.

Connected ONLY through the bus (modularity audit 2026-07-17): `turn.completed` (the semantic topic emitted by
`observer.turn_detail`, the single voice AND probe point), `worker.stuck`/`worker.budget_kill`, and the `observer`
topic (filtered) for the event ring and alert/rail-fail signals. Zero imports from the voice provider.

Cycle: friction → (cooldown + single-flight) → compose_audit_window (to_thread, memory reads outside the
loop) → powerful LLM (client, fail-open) → validate catalog → apply (apply, with before/after) → everything traced
with events of kind `susurro` (trigger/request/response/apply/done/error) that flow to the timeline + SSE + bus/log.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import deque

from loguru import logger

_TURN_RING: deque = deque(maxlen=16)      # {user, decision, trace, ts} per turn.completed
_EVENT_RING: deque = deque(maxlen=48)     # filtered observer events (context for the window)
_USER_TEXTS: deque = deque(maxlen=6)      # operator's latest texts (repeated-request detection)

_RING_KINDS = {"alert", "error", "rail", "task", "music", "search", "widget", "ambient"}

_tasks: list[asyncio.Task] = []
_auditing = False
_last_audit_ts = 0.0
_turns_since_audit = 0
_stats = {"turns_seen": 0, "audits": 0, "triggers_skipped": 0, "corrections_applied": 0, "last_reason": ""}


def _cfg() -> dict:
    from .client import cfg
    return cfg()


def enabled() -> bool:
    """First-class kill switch: ZAELAR_SUSURRO env (0 turns it off) + §susurro.enabled config (UI)."""
    if (os.getenv("ZAELAR_SUSURRO", "1") or "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    v = _cfg().get("enabled", True)
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "no", "off")
    return bool(v)


def _emit(label: str, text: str = "", extra: dict | None = None):
    try:
        from voice.observer import emit
        emit("susurro", label, text=text, role="system", extra=extra or {})
    except Exception:
        pass


async def _consume_turns(sub):
    from . import friction
    try:
        while True:
            ev = await sub.get()
            if not isinstance(ev, dict):
                continue
            user = str(ev.get("user") or "")
            trace = str(ev.get("trace") or "")
            _TURN_RING.append({"user": user, "decision": ev.get("decision") or {},
                               "trace": trace, "ts": ev.get("ts") or time.time()})
            _stats["turns_seen"] += 1
            global _turns_since_audit
            _turns_since_audit += 1
            # TURN friction (deterministic, free)
            signals = friction.complaint_signals(user)
            if signals:
                _maybe_trigger("queja/corrección del operador", signals, trace)
            elif friction.repeated_request(user, list(_USER_TEXTS)):
                _maybe_trigger("petición repetida (no atendida)", [user[:80]], trace)
            else:
                # V2-061: RISK from the turn's decision — gives Susurro an opportunity to intervene BEFORE
                # the operator complains (the ITV case: an un-escalated widget action on a real order). The
                # powerful model judges whether the path was wrong; this merely opens the door. Config-gated (ON by default).
                cons = _cfg().get("audit_consequential", True)
                risk = friction.risky_decision(ev.get("decision")) if cons else ""
                # V2-078: the MIRROR — GHOST data-op (chatted and said it acted on a widget, without executing).
                # Same principle as risky_decision: cheap signal that opens the door; the powerful model decides and
                # reroutes (worker_action) off-hot-path. Config-gated (ON by default).
                phantom = friction.phantom_dataop(user, ev.get("decision")) if _cfg().get("audit_phantom", True) else ""
                if risk:
                    _maybe_trigger(risk, [user[:80]], trace)
                elif phantom:
                    _maybe_trigger(phantom, [user[:80]], trace)
                else:
                    pulse = int(_cfg().get("pulse_turns") or 0)
                    if pulse > 0 and _turns_since_audit >= pulse:
                        _maybe_trigger("pulso periódico", [f"cada {pulse} turnos"], trace)
            if user:
                _USER_TEXTS.append(user)
    except asyncio.CancelledError:
        pass


async def _consume_worker_topic(sub, topic: str):
    # The Subscription delivers only the payload (without the topic) → a DEDICATED subscription per friction topic
    from . import friction
    reason = friction.system_friction("", topic=topic)
    try:
        while True:
            ev = await sub.get()
            wid = (ev or {}).get("id") if isinstance(ev, dict) else ""
            _maybe_trigger(reason, [f"worker {wid}"], str((ev or {}).get("trace") or "") if isinstance(ev, dict) else "")
    except asyncio.CancelledError:
        pass


async def _consume_observer(sub):
    from . import friction
    try:
        while True:
            ev = await sub.get()
            if not isinstance(ev, dict):
                continue
            kind = str(ev.get("kind") or "")
            if kind == "susurro":                     # never observe itself (loop)
                continue
            label = str(ev.get("label") or "")
            if kind in _RING_KINDS and not (kind == "vad" and "barge" not in label):
                _EVENT_RING.append({"kind": kind, "label": label, "text": str(ev.get("text") or "")[:200],
                                    "extra": {k: v for k, v in (ev.get("extra") or {}).items()
                                              if isinstance(v, (str, int, float, bool))},
                                    "trace": str(ev.get("trace") or ""),
                                    "ts": (ev.get("t_ms") or 0) / 1000.0 or time.time()})
            reason = friction.system_friction(kind, label)
            if reason:
                _maybe_trigger(reason, [label[:80]], str(ev.get("trace") or ""))
    except asyncio.CancelledError:
        pass


def _maybe_trigger(reason: str, signals: list[str], trace: str):
    global _auditing
    if not enabled():
        return
    cooldown = float(_cfg().get("cooldown_s") or 60)
    if _auditing or (time.time() - _last_audit_ts) < cooldown:
        _stats["triggers_skipped"] += 1
        _emit("👂 fricción detectada (en cooldown, no audita)", text=reason,
              extra={"reason": reason, "signals": signals[:4], "skipped": True})
        return
    _auditing = True
    _stats["last_reason"] = reason
    try:
        asyncio.get_running_loop().create_task(_audit(reason, signals, trace))
    except RuntimeError:
        _auditing = False               # no loop (unusual context/sync tests) → no audit, fail-open


async def _audit(reason: str, signals: list[str], trace: str):
    """A complete audit cycle, with TOTAL observability (request/response/applications)."""
    global _auditing, _last_audit_ts, _turns_since_audit
    t0 = time.time()
    try:
        from voice import trace as _trace
        ctx = _trace.scope(trace or _trace.current(), span="susurro")
    except Exception:
        import contextlib
        ctx = contextlib.nullcontext()
    try:
        with ctx:
            _emit("👂 fricción → auditoría", text=reason, extra={"reason": reason, "signals": signals[:6]})
            from . import apply, catalog, client, window
            turns = int(_cfg().get("window_turns") or 8)
            # BOUND BY RECENCY: the friction is NOW; the global ring (maxlen 16) may contain unrelated old
            # segments that would contaminate the diagnosis (seen in the test suite: one scenario diagnosed
            # ANOTHER earlier failure). Only turns/events from the recency window + the last K.
            recent_s = float(_cfg().get("recency_window_s") or 180)
            cut = time.time() - recent_s
            tr = [t for t in _TURN_RING if float(t.get("ts") or 0) >= cut][-(turns):]
            er = [e for e in _EVENT_RING if float(e.get("ts") or 0) >= cut][-16:]
            # NO CONVERSATION, NO AUDIT (2026-08-13, see `window.has_conversation` for the incident):
            # a conversation auditor without a conversation does not stay silent; it FILLS IN — and with `worker_action` enabled
            # that filling-in becomes a real action in the world. Refraining is free.
            if not await asyncio.to_thread(window.has_conversation, turns, since_ts=cut):
                _emit("🤐 auditoría OMITIDA (ventana sin conversación)", text=reason,
                      extra={"reason": reason, "signals": signals[:4]})
                return
            doc = await asyncio.to_thread(
                window.compose_audit_window, reason=reason, signals=signals,
                turn_ring=tr, event_ring=er, turns=turns, since_ts=cut)
            content, meta = await client.audit_llm(doc)
            # TOTAL observability (operator rule): raw REQUEST and RESPONSE, to the timeline + durable log
            _emit("📤 request → LLM auditor", text=f"{meta.get('model')} · {len(doc)} chars",
                  extra={"model": meta.get("model"), "request": meta.get("request")})
            _emit("📥 response ← LLM auditor",
                  text=(content or meta.get("error", ""))[:200],
                  extra={"raw": content, "ms": meta.get("ms"), "tokens": meta.get("tokens"),
                         "error": meta.get("error")})
            if content is None:
                _emit("⚠️ auditoría fallida (fail-open)", text=str(meta.get("error", "")),
                      extra={"reason": reason})
                return
            parsed = catalog.parse(content)
            if parsed is None:
                _emit("⚠️ respuesta no parseable (fail-open)", text=(content or "")[:200])
                return
            ok, downgraded = catalog.validate(parsed)
            applied = apply.apply_corrections(ok + downgraded, reason=reason, trace=trace, window=doc)
            _stats["audits"] += 1
            _stats["corrections_applied"] += len(applied)
            _emit("✅ auditoría completa",
                  text=str(parsed.get("assessment") or "")[:240],
                  extra={"reason": reason, "assessment": parsed.get("assessment"),
                         "n_corrections": len(applied),
                         "types": [a["type"] for a in applied],
                         "total_ms": round((time.time() - t0) * 1000)})
    except Exception as e:  # noqa: BLE001 — Susurro never crashes anything
        logger.debug(f"susurro: auditoría falló (fail-open): {e}")
        _emit("⚠️ error interno de auditoría (fail-open)", text=str(e)[:200])
    finally:
        _auditing = False
        _last_audit_ts = time.time()
        _turns_since_audit = 0


def start():
    """Start consumers in the current loop (server lifespan). Idempotent."""
    global _tasks
    if _tasks:
        return
    if not enabled():
        logger.info("susurro: desactivado (config/env)")
        return
    import bus
    loop = asyncio.get_event_loop()
    # SYNCHRONOUS subscriptions before launching tasks — zero window in which an early event can be lost
    _tasks = [loop.create_task(_consume_turns(bus.subscribe("turn.completed"))),
              loop.create_task(_consume_worker_topic(bus.subscribe("worker.stuck"), "worker.stuck")),
              loop.create_task(_consume_worker_topic(bus.subscribe("worker.budget_kill"), "worker.budget_kill")),
              loop.create_task(_consume_observer(bus.subscribe("observer")))]
    logger.info("susurro: escuchando (turn.completed + fricción del sistema)")
    _emit("👂 susurro ARRANCADO", extra={"model": str(_cfg().get("model") or ""),
                                         "pulse_turns": _cfg().get("pulse_turns"),
                                         "cooldown_s": _cfg().get("cooldown_s")})


async def stop():
    global _tasks
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    _tasks = []


def status() -> dict:
    return dict(_stats, enabled=enabled(), auditing=_auditing,
                turn_ring=len(_TURN_RING), event_ring=len(_EVENT_RING),
                last_audit_ts=_last_audit_ts)


def reset():
    """For tests: clear in-memory state (does not touch tasks)."""
    global _auditing, _last_audit_ts, _turns_since_audit
    _TURN_RING.clear()
    _EVENT_RING.clear()
    _USER_TEXTS.clear()
    _auditing = False
    _last_audit_ts = 0.0
    _turns_since_audit = 0
    for k in _stats:
        _stats[k] = 0 if isinstance(_stats[k], int) else ""
