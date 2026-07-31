"""Orquestación del Susurro (V2-053 F1): suscripción al bus → detección de fricción → ciclo de auditoría.

Enchufado SOLO por el bus (audit de modularidad 2026-07-17): `turn.completed` (el topic semántico que emite
`observer.turn_detail`, punto único de voz Y probe), `worker.stuck`/`worker.budget_kill`, y el topic `observer`
(filtrado) para el anillo de eventos y las señales alert/rail-fail. Cero imports del provider de voz.

Ciclo: fricción → (cooldown + single-flight) → compose_audit_window (to_thread, lecturas de memoria fuera del
loop) → LLM potente (client, fail-open) → validar catálogo → aplicar (apply, con antes/después) → todo trazado
con eventos kind `susurro` (trigger/request/response/apply/done/error) que caen al timeline + SSE + bus/log.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import deque

from loguru import logger

_TURN_RING: deque = deque(maxlen=16)      # {user, decision, trace, ts} por turn.completed
_EVENT_RING: deque = deque(maxlen=48)     # eventos filtrados del observer (contexto para la ventana)
_USER_TEXTS: deque = deque(maxlen=6)      # últimos textos del operador (detección de petición repetida)

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
    """Kill-switch de 1ª clase: env ZAELAR_SUSURRO (0 apaga) + config §susurro.enabled (UI)."""
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
            # fricción de TURNO (determinista, gratis)
            signals = friction.complaint_signals(user)
            if signals:
                _maybe_trigger("queja/corrección del operador", signals, trace)
            elif friction.repeated_request(user, list(_USER_TEXTS)):
                _maybe_trigger("petición repetida (no atendida)", [user[:80]], trace)
            else:
                # V2-061: RIESGO por la decisión del turno — le da a Susurro la oportunidad de intervenir ANTES de
                # que el operador se queje (el caso ITV: acción de widget sin escalar sobre una orden real). El
                # modelo potente juzga si el path fue erróneo; esto solo abre la puerta. Gate por config (ON def).
                cons = _cfg().get("audit_consequential", True)
                risk = friction.risky_decision(ev.get("decision")) if cons else ""
                # V2-078: el ESPEJO — data-op FANTASMA (charló y dijo que actuaba sobre un widget, sin ejecutar).
                # Mismo principio que risky_decision: señal barata que abre la puerta; el modelo potente decide y
                # re-rutea (worker_action) off-hot-path. Gate por config (ON def).
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
    # la Subscription entrega solo el payload (sin topic) → una suscripción DEDICADA por topic de fricción
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
            if kind == "susurro":                     # nunca auto-observarse (bucle)
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
        _auditing = False               # sin loop (contexto raro/tests sync) → no audita, fail-open


async def _audit(reason: str, signals: list[str], trace: str):
    """Un ciclo completo de auditoría, con observabilidad TOTAL (request/response/aplicaciones)."""
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
            # ACOTAR POR RECENCIA: la fricción es de AHORA; el anillo global (maxlen 16) puede contener tramos
            # viejos no relacionados que contaminarían el diagnóstico (visto en la batería: un escenario diagnosticó
            # el fallo de OTRO anterior). Solo turnos/eventos de la ventana de recencia + últimos K.
            recent_s = float(_cfg().get("recency_window_s") or 180)
            cut = time.time() - recent_s
            tr = [t for t in _TURN_RING if float(t.get("ts") or 0) >= cut][-(turns):]
            er = [e for e in _EVENT_RING if float(e.get("ts") or 0) >= cut][-16:]
            doc = await asyncio.to_thread(
                window.compose_audit_window, reason=reason, signals=signals,
                turn_ring=tr, event_ring=er, turns=turns)
            content, meta = await client.audit_llm(doc)
            # observabilidad TOTAL (regla del operador): ENVÍO y RESPUESTA crudos, al timeline + log durable
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
            applied = apply.apply_corrections(ok + downgraded, reason=reason, trace=trace)
            _stats["audits"] += 1
            _stats["corrections_applied"] += len(applied)
            _emit("✅ auditoría completa",
                  text=str(parsed.get("assessment") or "")[:240],
                  extra={"reason": reason, "assessment": parsed.get("assessment"),
                         "n_corrections": len(applied),
                         "types": [a["type"] for a in applied],
                         "total_ms": round((time.time() - t0) * 1000)})
    except Exception as e:  # noqa: BLE001 — el Susurro jamás revienta nada
        logger.debug(f"susurro: auditoría falló (fail-open): {e}")
        _emit("⚠️ error interno de auditoría (fail-open)", text=str(e)[:200])
    finally:
        _auditing = False
        _last_audit_ts = time.time()
        _turns_since_audit = 0


def start():
    """Arranca los consumidores en el loop actual (lifespan del server). Idempotente."""
    global _tasks
    if _tasks:
        return
    if not enabled():
        logger.info("susurro: desactivado (config/env)")
        return
    import bus
    loop = asyncio.get_event_loop()
    # suscripciones SÍNCRONAS antes de lanzar las tareas — cero ventana en la que un evento temprano se pierda
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
    """Para tests: limpia el estado en RAM (no toca tasks)."""
    global _auditing, _last_audit_ts, _turns_since_audit
    _TURN_RING.clear()
    _EVENT_RING.clear()
    _USER_TEXTS.clear()
    _auditing = False
    _last_audit_ts = 0.0
    _turns_since_audit = 0
    for k in _stats:
        _stats[k] = 0 if isinstance(_stats[k], int) else ""
