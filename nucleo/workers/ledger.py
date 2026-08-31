"""nucleo/workers/ledger.py — Durable LEDGER for Brain Workers (V2-079).

The live registry (`nucleo/dispatch.py::_SESSIONS`) is the truth of what is running NOW and is projected to
`memory.state()["sessions"]` + `/api/tasks` (the hexagons). BUT when a session ends, it is `pop`ped → erased
and disappears: there was no way to see "which workers have run today / yesterday / a few days ago". This piece
keeps a compact HISTORY of the LAST FINISHED executions to provide VISIBILITY (the ChatWall’s «Procesos» tab).

Decisions:
  · **Outside the hot path**: persisted in `sys_kv` (key `worker_ledger`), NOT in the root `state()` that travels in
    every FlashBrain prompt — visibility is for the UI; the brain does not need it on every turn.
  · **FINISHED ONLY**: LIVE workers are read from `dispatch.active_sessions()` (real time). The ledger is the
    history; the frontend merges live (top) + history (bottom), deduplicated by id.
  · **Hard cap + cleanup over time**: MRU by `finished_at`, cap `CAP`. The sleep sweep
    (`consolidator.consolidate`) calls `prune()` to delete finished executions older than N days — just like
    memory decay/eviction. INFINITE WEIGHT = those linked to a STILL active cron (recurring): they do not expire
    while their cron exists (the session equivalent of a `pinned` memory).
"""
from __future__ import annotations

import time

CAP = 50
_KEY = "worker_ledger"
_CLEAR_KEY = "worker_ledger_cleared_at"   # the FENCE: when the history was last wiped (see clear())
_GOAL_MAX = 160


def _load() -> list[dict]:
    try:
        from memory import api as _mem
        v = _mem.kv_get(_KEY)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _save(entries: list[dict]) -> None:
    try:
        from memory import api as _mem
        _mem.kv_set(_KEY, entries[:CAP])
    except Exception:
        pass


def clear() -> int:
    """Empties the ledger (the HISTORY of the Procesos tab). RESET uses it to leave the processes BLANK
    («we start from zero»): killing live workers clears the chips; this clears the history. Returns how many
    entries were discarded. The state/memory/widget data are NOT touched (this is only the process registry).

    THE FENCE (2026-08-31, seen live by the operator): the wipe alone was not enough. `reset_all` kills the live
    workers FIRST and clears the ledger after — but a kill is a signal, and the dying worker's finish path runs
    asynchronously: milliseconds after the wipe, `record_finish(status="cancelled")` landed and the very task the
    reset had just killed wrote its own tombstone into the fresh slate. The operator reset, and «Histórico» showed
    one entry: the search his reset cancelled, «· ahora». Stamping WHEN the wipe happened lets `record_finish`
    drop any record born before it — reordering reset_all would only shrink the window, never close it, because
    the worker's death is not ours to sequence."""
    n = len(_load())
    if n:
        _save([])
    try:
        from memory import api as _mem
        _mem.kv_set(_CLEAR_KEY, time.time())
    except Exception:
        pass
    return n


def record_finish(*, id: str, kind: str = "", goal: str = "", status: str = "done",
                   started_at: float | None = None, finished_at: float | None = None,
                   trace_id: str = "", cron: str = "", ok: bool = False) -> None:
    """Records (or updates) a FINISHED execution in the ledger. Deduplicates by `id` (a re-entry updates in
    place), MRU (most recent first), cap `CAP`. Best-effort: never raises (it must not bring down session shutdown).
    `cron` = name of the source cron if the execution came from one (best-effort today; "" otherwise)."""
    try:
        fid = str(id or "").strip()
        if not fid:
            return
        now = time.time()
        # A record BORN before the last wipe belongs to the era the wipe erased — drop it (see clear()). Judged
        # by the task's start when known, else by the old snapshot time rehydrate passes as `finished_at`, else
        # by arrival (a record with no dates at all is judged by when it shows up, and is kept).
        try:
            from memory import api as _mem
            fence = float(_mem.kv_get(_CLEAR_KEY) or 0.0)
        except Exception:
            fence = 0.0
        if fence and float(started_at or finished_at or now) < fence:
            return
        entry = {
            "id": fid, "kind": str(kind or ""), "goal": str(goal or "")[:_GOAL_MAX],
            "status": str(status or "done"), "ok": bool(ok),
            "started_at": float(started_at or 0) or None,
            "finished_at": float(finished_at if finished_at is not None else now),
            "trace_id": str(trace_id or ""), "cron": str(cron or ""),
        }
        entries = [e for e in _load() if e.get("id") != fid]
        entries.insert(0, entry)
        _save(entries)
    except Exception:
        pass


def history(limit: int = CAP) -> list[dict]:
    """Most recent finished executions, most recent first (for the «Procesos» tab)."""
    return _load()[: max(1, int(limit))]


def prune(max_age_days: float = 7.0, now: float | None = None, active_crons: set | None = None) -> int:
    """Sweeps the ledger during sleep (V2-079): deletes FINISHED executions older than `max_age_days`, EXCEPT those
    linked to a STILL active cron (infinite weight). Returns how many were removed. `active_crons` = names/ids of
    live crons (so recurring executions do not expire); if None, resolved from the scheduler. Never raises."""
    try:
        now = float(now or time.time())
        cutoff = now - float(max_age_days) * 86400.0
        if active_crons is None:
            active_crons = _active_cron_labels()
        keep, removed = [], 0
        for e in _load():
            cron = str(e.get("cron") or "")
            if cron and cron in active_crons:          # recurring execution with live cron → never expires
                keep.append(e)
                continue
            if float(e.get("finished_at") or 0) >= cutoff:
                keep.append(e)
            else:
                removed += 1
        if removed:
            _save(keep)
        return removed
    except Exception:
        return 0


def _active_cron_labels() -> set:
    """Names+ids of ACTIVE crons (status pending) — so recurring executions do not expire."""
    try:
        from nucleo import scheduler
        out = set()
        for j in scheduler.list_jobs():
            out.add(str(j.get("id")))
            if j.get("name"):
                out.add(str(j.get("name")))
        return out
    except Exception:
        return set()
