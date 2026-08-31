"""nucleo/rails.py — RAILS: common GUIDED behaviors (V2-042, FlashBrain orchestration pattern).

An **RAIL** is a habitual behavior that we know how to guide in a specific way — fuzzy music, video,
data studies, complex searches on sites, messaging, calendar, recursive searches (cron+search). The
name comes from the operator: they are "rails" along which the action runs. Each rail provides four MODULAR pieces:

  1. a **deterministic chain in CODE** (resolve→validate→act, e.g. `nucleo/flash/music_flow.py`) — the
     FlashBrain remains non-reasoning: it only triggers the tool; the rail guides;
  2. its **tool** in `router.TOOLS` (and nothing else: the "when YES/NO" lives in the description, V2-035);
  3. its **live RUNS** — this module: RAM registry projected into STATE (`state.rails`) → each turn's prompt
     knows what is being searched for, what is playing, and what remains UNRESOLVED (isolated, with attempts)
     so it can continue when the operator provides data ("it was Sinatra");
  4. its **writeback to memory** (via typed `memory.ingest_message(source=…)`) → history + preferences → zaelar knows
     the operator and fine-tunes subsequent guidance.

**Isolated prompts, only when needed** (the operator's idea): in addition to the run in STATE, a rail may
provide a GUIDANCE line to the prompt only while it has a live run (`prompt_lines()` ← `_GUIDANCE`) — zero
prompt cost while the rail is idle.

It is the LIGHTWEIGHT sibling of the sessions in `nucleo/dispatch.py` (heavy workers): a run is NOT a process — it is the
STATE of guidance that FlashBrain itself carries out during its turns. Design:
  · **Singleton per `kind`**: a new run of the same kind REPLACES the previous one (they do not accumulate).
  · **ISOLATED failures with TTL**: a failed run remains `sin_resolver` (15 min) — it neither contaminates nor gets lost.
  · **Writes ALWAYS off the hot path**: callers invoke from `asyncio.to_thread` (V2-011). `project()` performs
    `memory.set_state` best-effort (never raises). Observable transitions (`rail` event in /debug).
"""
from __future__ import annotations

import threading
import time

from loguru import logger

# kind → live run {kind, label, status, detail, attempts, created, updated}
_RUNS: dict[str, dict] = {}
_lock = threading.Lock()

# TTL per status (seconds): how long a run lives without anyone touching it before expiring on its own.
_TTL = {
    "searching": 10 * 60,        # an abandoned search in progress
    "sin_resolver": 15 * 60,     # the ISOLATED failure: kept for resumption, expires if no one resumes it
    "playing": 4 * 60 * 60,      # something playing (long: a music session)
    "paused": 60 * 60,
}
_TTL_DEFAULT = 30 * 60

# Situational GUIDANCE per rail (kind → prompt line + statuses where it applies): INJECTED only while the rail
# has a live run in that status (prompt_lines()). Modular: the prompt does not pay for idle rails.
_GUIDANCE = {
    "music.search": (("sin_resolver",),
                     "Hay una búsqueda de canción SIN RESOLVER en tus rails: si el operador aporta un dato "
                     "(artista, año, otra palabra de la letra), vuelve a llamar a play_music con la query "
                     "ENRIQUECIDA (pista original + dato nuevo)."),
    # Session 22:40 2026-07-16: with music playing, «no se oye» escalated to a worker that investigated zaelar's VOICE.
    # With a live playback run, EVERY audio complaint refers to THAT music — and if you still escalate, the
    # request must say so (the worker cannot see this conversation).
    "music.playing": (("playing", "paused"),
                      "Hay MÚSICA SONANDO ahora (mírala en tus rails). Si el operador dice que «no se oye», «no "
                      "suena», «súbelo», «quita eso» o cualquier queja/orden de audio, se refiere a ESA música — "
                      "resuélvelo TÚ con play_music (volume_up/resume/pause/stop), no lo trates como un problema "
                      "de tu voz ni del equipo. Si necesitas escalarlo, di EXPLÍCITAMENTE en la petición que se "
                      "trata de la música que está sonando (título incluido)."),
}


def upsert(kind: str, label: str = "", *, status: str = "", detail: str = "", bump: bool = False) -> dict:
    """Create/update the run for a `kind` (singleton: replaces the previous one). `bump` increments attempts.
    Returns the run. Call OFF-LOOP (to_thread)."""
    kind = (kind or "").strip()
    if not kind:
        return {}
    now = time.time()
    # V2-044: trace of the phrase that GUIDES this run (turn ctxvar; travels through to_thread). A new run
    # adopts it; a live one preserves it — so later transitions (fail/resolve off-turn) remain chained.
    try:
        from voice import trace as _trace
        _tid = _trace.current()
    except Exception:
        _tid = ""
    with _lock:
        a = _RUNS.get(kind)
        if a is None or (label and a.get("label") != label):
            # new run (or the same kind with a DIFFERENT target → replaces it; attempts start from zero)
            a = {"kind": kind, "label": label or (a or {}).get("label", ""), "status": status or "searching",
                 "detail": detail, "attempts": 1 if bump else 0, "created": now, "updated": now,
                 "trace": _tid}
        else:
            if status:
                a["status"] = status
            if detail:
                a["detail"] = detail
            if label:
                a["label"] = label
            if bump:
                a["attempts"] = int(a.get("attempts") or 0) + 1
            a["updated"] = now
        _RUNS[kind] = a
        snap = dict(a)
    _observe("upsert", snap)
    project()
    return snap


def resolve(kind: str) -> None:
    """The run ended SUCCESSFULLY → disappears from state. Call OFF-LOOP."""
    with _lock:
        a = _RUNS.pop((kind or "").strip(), None)
    if a:
        _observe("resolve", a)
    project()


def fail(kind: str, reason: str = "") -> None:
    """The run failed → remains ISOLATED as `sin_resolver` (with its label/attempts) until someone resumes it with
    more data or its TTL expires. It does NOT disappear: this is the state that allows continuation ("it was Sinatra")."""
    snap = None
    with _lock:
        a = _RUNS.get((kind or "").strip())
        if a is not None:
            a["status"] = "sin_resolver"
            if reason:
                a["detail"] = reason
            a["updated"] = time.time()
            snap = dict(a)
    if snap:
        _observe("fail", snap)
    project()


def get(kind: str) -> "dict | None":
    with _lock:
        a = _RUNS.get((kind or "").strip())
        return dict(a) if a else None


def live() -> list[dict]:
    """Current runs (removes those expired by TTL). Order: most recent first."""
    now = time.time()
    with _lock:
        dead = [k for k, a in _RUNS.items()
                if now - float(a.get("updated") or 0) > _TTL.get(a.get("status") or "", _TTL_DEFAULT)]
        for k in dead:
            _RUNS.pop(k, None)
        return sorted((dict(a) for a in _RUNS.values()), key=lambda a: -float(a.get("updated") or 0))


def prompt_lines() -> list[str]:
    """Situational GUIDANCE for rails with a live run — injected into the prompt ONLY when applicable (the operator's idea:
    isolated prompts per behavior, zero idle cost)."""
    out = []
    for a in live():
        spec = _GUIDANCE.get(a.get("kind") or "")
        if spec and (a.get("status") or "") in spec[0]:
            out.append(spec[1])
    return out


def project() -> None:
    """Projects the RAM registry → memory STATE (`state.rails`). Best-effort, never raises. Callers are already
    off-loop (to_thread), so the state write taking µs is safe (V2-011)."""
    try:
        from memory import api as memory
        memory.set_state({"rails": [
            {"kind": a["kind"], "label": (a.get("label") or "")[:120], "status": a.get("status") or "",
             "detail": (a.get("detail") or "")[:100], "attempts": int(a.get("attempts") or 0)}
            for a in live()[:6]
        ]})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"rails.project saltado: {e!r}")


def _observe(op: str, run: dict) -> None:
    """OBSERVABLE transition (`rail` event → /debug + SSE): visibility into each guidance operation. Best-effort."""
    try:
        from voice.observer import emit
        extra = {"kind": run.get("kind"), "status": run.get("status"), "label": (run.get("label") or "")[:80],
                 "attempts": int(run.get("attempts") or 0), "op": op}
        # V2-044: chains the transition to the phrase that guides the run (even if it occurs off-turn, e.g. a later
        # failure) + span=rail:<kind> for level 2 of the Trace tree.
        _tid = run.get("trace") or ""
        if _tid:
            extra["trace"] = _tid
            extra["span"] = f"rail:{run.get('kind')}"
        emit("rail", f"🛤 {op} {run.get('kind')}", role="system", extra=extra)
    except Exception:
        pass


def clear_all() -> None:
    """Full cleanup (reset/tests)."""
    with _lock:
        _RUNS.clear()
    project()
