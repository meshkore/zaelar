"""nucleo/workers/resume.py — CONTINUITY for a web task across workers and processes (V2-049).

Extracted from `dispatch.py` on 2026-08-26 when paying the architecture ratchet (V2-342 added `_leave_resume`
and the file exceeded its ceiling: the table calls for extracting a concern, not increasing the number). It is a
COHESIVE concern: a dict with a durable mirror (`_WEB_RESUME` ⇄ `sys_kv`) and the five operations on it — persist,
restore, the signature of a task (`_goal_key`), the entry left when closing (`_resume_entry`/`_leave_resume`) and
matching a new request with an incomplete task (`_find_resume`, with its `take=True` from V2-237).

`dispatch.py` retains ALIASES with the historical names (`dispatch._WEB_RESUME` is THE SAME object): external
in-place mutators (`reset.py`, `test_rehydrate`) continue working unchanged. What does NOT move here is
`_schedule_auto_resume`: it triggers escalations, and that belongs to the dispatcher.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def _content_words(text: str) -> set:
    from nucleo import matching
    return matching.content_words(text)


_WEB_RESUME: dict[str, dict] = {}
_RESUME_TTL = 1800.0
_RESUME_CAP = 3
# …and like the session registry, this used to live ONLY in RAM: a restart in the middle of a web task wiped out the
# only way to CONTINUE IT (the `native_sid` that lets the worker resume its reasoning instead of starting from
# scratch). Mirror in `sys_kv` — process state, not operator state, just like the worker ledger. The TTL is applied
# on loading as well, so a stale entry revives nothing.
_RESUME_KEY = "web_resume"


def _resume_persist() -> None:
    """Mirrors `_WEB_RESUME` to `sys_kv`. Best-effort and outside the hot path (only when closing a web session)."""
    try:
        from memory import api as _mem
        if _WEB_RESUME:
            _mem.kv_set(_RESUME_KEY, _WEB_RESUME)
        else:
            _mem.kv_del(_RESUME_KEY)
    except Exception:
        pass


def _resume_restore() -> int:
    """Reloads web continuity entries that have not expired. Returns the count. Called by `start()`."""
    try:
        from memory import api as _mem
        raw = _mem.kv_get(_RESUME_KEY)
        if not isinstance(raw, dict):
            return 0
        now = time.time()
        n = 0
        for k, ent in raw.items():
            if isinstance(ent, dict) and (now - float(ent.get("ts") or 0)) <= _RESUME_TTL:
                _WEB_RESUME[str(k)] = ent
                n += 1
        if n:
            logger.info(f"dispatch: {n} gestión(es) web reanudables recuperadas del proceso anterior")
        return n
    except Exception:
        return 0


def _goal_key(req: str) -> str:
    """Stable signature of a task for matching resumptions (sorted content words)."""
    return " ".join(sorted(_content_words(req)))


def _resume_entry(rec, *, nav_tid: str, resume: dict | None, req: str, key: str,
                  brief: bool, prev_count: int) -> dict:
    """The resumption entry left by an INCOMPLETE web task. Outside `_run_session` so it can be tested.

    V2-239 — A `native_sid` THAT KILLED A WORKER MUST NOT BE REASSEMBLED. There used to be a
    `rec.native_sid or (resume or {}).get("native_sid")` here that RECYCLED the inherited id when the worker never
    obtained its own. And failing to obtain one means exactly one thing: the CLI never announced its session
    (`rec.native_sid` is set by the `spawned` event, which originates from Claude Code's `system/init` — and that
    init arrives both on a clean start and on `--resume`, so a resumption that STARTS does leave its id). In other
    words, the id returned to the entry, the next worker took it, and died again during startup.

    Measured by the harness ON TOP OF the V2-237 fix (05dd79f, clean worktree, `n_dirty=0`): `take=True`
    consumed correctly and yet session `0364d544-505` took down workers 3 and 4, dead 2/2 at
    380 and 420 ms. **Consuming the entry is not enough if the death path reassembles it with the same id.**

    `nav_task` DOES retain its fallback: the browser tab is another resource, survives the worker that opened it,
    and is not what was killing anything.
    """
    return {"nav_task": nav_tid or str((resume or {}).get("nav_task") or ""),
            "native_sid": rec.native_sid,
            "ts": time.time(), "count": int(prev_count) + 1, "goal": req[:200],
            # The criteria already agreed upon travel with the resumption: rebuilding them halfway through a search
            # would turn it into a different search without warning.
            "brief_task": key if brief else str((resume or {}).get("brief_task") or "")}


def _leave_resume(rec, *, nav_tid: str, resume: dict | None, req: str, key: str,
                  brief: bool, prev_count: int) -> None:
    """The resumable TRACE left by a web task when closing. Outside `_run_session` so it can be tested.

    V2-342 — A CANCELLED TASK ALSO LEAVES IT. Previously `status == "cancelled"` deleted the entry (“stopped →
    nothing to resume”), and that line turned every “relaunch from scratch” into a genuine start from scratch.
    Measured in session 7575e81a (2026-08-26, search-buy-used-car): 3 workers in 21.6 min, two cancelled after
    operator complaints and relaunched without inheriting anything — 2/3 of the time spent on discarded work, and
    the loop feeds itself (slow → complaint → relaunch from scratch → slower). Stopping deletes the PROCESS (the
    tab closes, auto-resume does not trigger: `_resumable` continues excluding `cancelled` — stopping is stopping,
    V2-092); what it does NOT delete is the work done: the CLI's native session retains all its reasoning, and if
    the operator relaunches the same task within the TTL, `_find_resume` gives it to the new worker instead of
    discarding it. If it is never relaunched, the TTL prunes it; `_RESUME_CAP` cuts the chain if something is truly
    broken."""
    gk = _goal_key(req)
    if rec.ok:
        _WEB_RESUME.pop(gk, None)                       # completed → nothing to resume
    elif nav_tid or rec.native_sid:
        _WEB_RESUME[gk] = _resume_entry(rec, nav_tid=nav_tid, resume=resume, req=req, key=key,
                                        brief=brief, prev_count=prev_count)
    _resume_persist()       # survives restart → the resumption CONTINUES instead of starting from scratch


def _find_resume(req: str, *, take: bool = False) -> dict | None:
    """Recent resumption entry matching this request ('' → None): word overlap ≥0.5 with an INCOMPLETE web task
    within the TTL. Prunes expired entries along the way.

    `take=True` CONSUMES it, which prevents multiple workers from resuming the same CLI session.

    Measured by the harness on 2026-08-21 in `best-plumber-same-day` (1/5, zero rows extracted), with perfect
    correlation: three different workers started with “RESUMES native session c5ad1d9e-ad0…” —**the same one**—
    and all three died at 371, 401, and 374 ms; the two that opened their own session survived. **3 out of 3
    versus 0 out of 3.** A CLI session cannot be resumed twice at once: the second `--resume` for the same id dies
    during startup, before doing anything. And because this was read without being consumed, every escalation of
    the same request —including those triggered by auto-resume— took the SAME `native_sid`.

    Consuming it is safe because the lifecycle returns it: when closing an incomplete web task, `_run_session`
    rewrites the entry with the CURRENT `native_sid`. And if the worker dies before reaching that point, the
    resumption is lost and the next task starts from scratch — which is strictly better than dying in 400 ms.
    """
    now = time.time()
    req_w = _content_words(req)
    if not req_w:
        return None
    best, best_key, best_score = None, "", 0.0
    for key, ent in list(_WEB_RESUME.items()):
        if now - ent.get("ts", 0) > _RESUME_TTL:
            _WEB_RESUME.pop(key, None)
            continue
        o = set(key.split())
        # V2-342 — scored against the SMALLER set (with a floor of 3), not the union. Measured in session
        # 7575e81a (2026-08-26): the real “Relaunch the car search from scratch…” contains 47 content words
        # —pacing instructions, sources, notices— and with Jaccard the incomplete task it RELAUNCHES scored 0.208:
        # the verbosity of the instruction hid that the entire task was CONTAINED in it (11 of its 17 words,
        # 0.647). Strictly more permissive than Jaccard, so nothing that matched stops matching; the floor of 3
        # prevents a one-word request (“search”) from taking any pending task.
        inter = len(req_w & o)
        denom = max(3, min(len(req_w), len(o)))
        score = inter / denom
        if score >= 0.5 and score > best_score:
            best, best_key, best_score = ent, key, score
    if best is not None and take:
        _WEB_RESUME.pop(best_key, None)
        _resume_persist()          # …and prevents the durable trace from serving it again after a restart
    return best
