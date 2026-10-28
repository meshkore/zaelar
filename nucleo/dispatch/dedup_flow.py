"""Is this escalation the errand already running? Live keys, traces, the duplicate scan, the flow it folds into.
Every package name is read through `_d`, so a patch of `dispatch.<name>` reaches the code here."""
from __future__ import annotations

import re

from nucleo import dispatch as _d


# ── resolucion of "which" for inject / stop (determinista, §v2·B/§v3·M) ──────────────────────────────────────
def _norm(text: str) -> str:
    return _d.matching.norm_text(text)


_ALL_RE = re.compile(r"\b(todo|todos|todas|all|everything|cualquier|lo que estas haciendo|lo que haces)\b")


_KIND_HINTS = {
    "code": ("widget", "tarjeta", "panel", "codigo", "code", "card"),
    "web":  ("web", "navegador", "busqueda", "buscando", "wallapop", "amazon", "internet", "browser", "search"),
    "memory": ("memoria", "memory"),
    "research": ("estudio", "informe", "investiga", "research"),
}


def _live_keys() -> list[str]:
    return [k for k, r in _d._SESSIONS.items() if r.status in _d.LIVE_SESSION_STATES]


def live_traces() -> list[str]:
    """Distinct `trace_id`s of the sessions that are still LIVE. The set form of `has_live_trace`, for the caller
    that needs to know WHICH task is running rather than whether a given trace is one (`nucleo.py::_merge_target`,
    V2-123). Same liveness filter as `_live_keys` — a `done` session is not a task the conversation can still be
    about, and reading unfiltered `_SESSIONS` is the exact bug `active_sessions()` carried until 2026-08-18."""
    out = []
    for k in _d._live_keys():
        t = str(getattr(_d._SESSIONS[k], "trace_id", "") or "")
        if t and t not in out:
            out.append(t)
    return out


# The tokenizer lives in `nucleo/matching.py` (F4, 2026-08-23): `widgets/browser/tasks._similar` had its own copy
# and disagreed on the same pair. One yardstick, imported; local names survive for callers.
def _content_words(text: str) -> set:
    return _d.matching.content_words(text)


def _target_widget(request: str) -> str:
    return _d._dedup.target_widget(request)


def trace_of(tid: str) -> str:
    """`trace_id` of a live session by its tid ('' if it doesn't exist or has none yet). The single cross-module
    accessor to `_SESSIONS` for this field — keeps the caller (the voice provider) from reaching into the private
    dict directly."""
    r = _d._SESSIONS.get(str(tid))
    return str(getattr(r, "trace_id", "") or "") if r else ""


def has_live_trace(trace_id: str) -> bool:
    """Is there a LIVE worker session carrying this trace_id? The reverse of `trace_of` — a plain conversational
    turn that finishes cleanly can close its own flow (V2-090 addenda, `nucleo.py::_maybe_close_flow`), but only
    once nothing spawned on this trace is still working; the worker's OWN end (`_run_session`'s finally block)
    already emits the explicit close, and closing the flow again from here would be a stale, contradictory
    second "end" while the session is still running."""
    tid = (trace_id or "").strip()
    if not tid:
        return False
    return any(getattr(r, "trace_id", "") == tid for r in _d._SESSIONS.values())


def find_duplicate(request: str, kind: str) -> str | None:
    """tid of a session VIVA that already atiende ESTA request ('' → None). La REGLA lives in `nucleo/dedup.py`;
    here only is resuelve QUIÉN esta live, that es it only that this module sabe."""
    return _d.dedup_scan(request, kind)[0]


def _live_errands() -> list[tuple[str, str]]:
    """(tid, goal) of each session VIVA — the only point that traduce the record RAM for the two jueces."""
    return [(k, r.goal) for k, r in _d._SESSIONS.items() if r.status in _d.LIVE_SESSION_STATES]


def dedup_scan(request: str, kind: str) -> tuple[str | None, dict]:
    """El veredicto of the dedup Y the evidencia sobre the that it tomo (`nucleo/dedup.scan`)."""
    return _d._dedup.scan(request, kind, _d._live_errands())


# ATTRIBUTION: which words of an allusion identify a task, and when two are THE SAME thing.
# V2-140 (`three-tasks-at-once`, «each allusion goes to the RIGHT task»): «¿and the car one?» matched all three.
# Two mechanical causes: punctuation stuck to tokens (`coche?`, as in V2-123) and exact equality (`coche` ≠
# `coches`). Prefix match is BOUNDED (root ≥ 4 chars, ≤ 3 diff): `coche`/`coches` match, `coche`/`cocina` don't.
_REF_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _ref_words(text: str) -> set[str]:
    return {w for w in _d._REF_WORD_RE.findall(text or "") if len(w) > 3}


def _same_thing(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and len(long_) - len(short) <= 3 and long_.startswith(short)


def resolve_sessions(query: str) -> list[str]:
    """Operator reference → live tid(s): a live id → that one; ''/all → all; one live → it; else kind, word overlap, all."""
    keys = _d._live_keys()
    if not keys:
        return []
    if str(query or "").strip() in keys:      # an id is never a phrase (pass 116: a brief went to every worker)
        return [str(query).strip()]
    q = _d._norm(query)
    if not q or _d._ALL_RE.search(q):
        return list(keys)
    if len(keys) == 1:
        return list(keys)
    # The errand's own WORDS first, its kind only when no word names one (three-tasks, 20:00): «informe» is a
    # `research` hint, the report ran as `generic` and the marketplace hunt as `research` — the report's refinement
    # went to the monitor worker.
    q_words = _d._ref_words(q)
    scored = sorted(((sum(1 for w in q_words if any(_d._same_thing(w, h) for h in _d._ref_words(_d._norm(
        f"{_d._SESSIONS[k].label} {_d._SESSIONS[k].goal}")))), k) for k in keys), reverse=True)
    if scored and scored[0][0] > 0:
        return [k for s, k in scored if s == scored[0][0]]
    want = {k for k, hints in _d._KIND_HINTS.items() if any(h in q for h in hints)}
    by_kind = [k for k in keys if (_d._SESSIONS[k].kind or "") in want]
    return by_kind or list(keys)


# ── consumo of escalados of the bus (FlashBrain → workers) ────────────────────────────────────────────────────
def _merge_dedup_flow(ctx: dict, dup: str) -> bool:
    """An escalation just absorbed into the live session `dup` is PROOF they are one task (`find_duplicate` needs 60%
    content-word overlap): fuse this turn's flow into the live one so the viewer paints ONE thread (V2-123). True
    means the caller must NOT emit its own `flow/end` — the reader sums both halves' ends, so closing here would mark
    live work finished; the live session's own end owns the close. It merges on the strict matcher's evidence, never
    on `resolve_sessions`' loose guess (loose suits cancelling, not attribution)."""
    src = str((ctx or {}).get("trace") or "")
    if not src:
        return False
    dst = _d.trace_of(dup)
    if not dst:
        return False
    if dst == src:
        return True             # already the same flow: nothing to fuse, and its worker still owns the close
    try:
        from voice import trace as _trace_merge
        _trace_merge.merge(dst, src)
    except Exception:
        return False
    return True


def _close_escalated_flow(ctx: dict, *, ok: bool, status: str) -> None:
    """Explicit flow-close for an `escalate.requested` outcome that never spawns its own `SessionRecord` —
    rejected while the agent is halted, or absorbed as a refinement into an already-live session (V2-113). Both
    paths leave `has_live_trace(trace_id)` False forever for THIS trace, so without an explicit close here the
    voice provider's `just_escalated` guard (`nucleo.py::_flow_should_close`) would block the flow from EVER
    closing — mirrors the close `_run_session`'s finally block emits for a real spawn."""
    trace_id = str((ctx or {}).get("trace") or "")
    if not trace_id:
        return
    try:
        from voice import trace as _trace3
        from voice.observer import emit as _emit_close2
        with _trace3.scope(trace_id):
            _emit_close2("flow", "end", role="system", extra={"ok": ok, "status": status})
    except Exception:
        pass
