"""nucleo/dispatch.py — Manager of Brain Worker sessions (V2-038; reframes dispatcher V2-006/V2-036).

Receives escalations from FlashBrain (`bus:escalate.requested`) and converts them into live **Brain Workers**
(`nucleo/workers/`): an agnostic backend (`get_backend`) driven by a `WorkerSession`. Maintains the **SINGLE
IN-MEMORY REGISTRY** of live sessions (`_SESSIONS`), which is the **SOURCE OF TRUTH** (§v2·C) — absorbs and replaces
the three partial registries from before (`escalate._tasks`, `_INFLIGHT`, old `_SESSIONS`, §v3·G). Exposes:
  · `active_sessions()`/`has_active()`/`pending_summaries()` — projection for STATE/prompt/`/api/tasks`.
  · `inject(which, msg)` — injects into a live session (refinement; replaces V2-029's deduplicate-and-discard).
  · `cancel_session(tid)`/`cancel_all()` — terminate politely (terminate the process group through the backend).
  · `resolve_sessions(query)` — “for that process” → deterministic tid(s).

The confirmation gate for irreversible actions (V2-007) and kind classification are retained. Design:
initiatives/V2-038-brain-workers-interactivos.md.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets as _secrets
import secrets
import time
import unicodedata
from dataclasses import dataclass, field

from nucleo.request import append as _dedup
from nucleo import matching
from typing import Any

from loguru import logger

from nucleo import dev_worker_guard, protected_core

from nucleo.workers import brief as research
from nucleo.workers import WorkerSpec, get_backend, workdir
from nucleo.workers.providers import worker_sees as _worker_sees
from nucleo import surfaces
from nucleo.workers.session import SessionRecord, WorkerSession
# Prompt composition (pure, no session-pool state) split out (V2-098) into its own module; re-exported by name
# so existing call sites (below, and tests doing dispatch._build_prompt/_web_prompt) keep working unchanged.
from nucleo.workers.prompts import _build_prompt, _web_prompt  # noqa: F401

# V2-289 — the errand's CLASS (which kind, how it is labelled) is pure text work in `nucleo/request/kind.py`; kind
# «web» means operating a site in a real browser, never «the data is on the internet» (that is research).
from nucleo.request.kind import (  # noqa: E402,F401 — re-export
    _ARCHITECT_RE, _DATA_NOT_CODE_RE, _MODIFY_CODE_RE, _WEB_RE,
    classify_kind as _classify_kind, default_label as _default_label)


@dataclass
class Task:
    """An incoming FlashBrain escalation."""
    id: str
    request: str
    kind: str = "generic"
    trusted: bool = True
    context: dict[str, Any] = field(default_factory=dict)


# ── REGISTRO ÚNICO EN RAM = source of truth (§v2·C, §v3·G) ─────────────────────────────────────────────────
_SESSIONS: dict[str, SessionRecord] = {}

# ── V2-049 web CONTINUITY lives in `nucleo/workers/resume.py`: a web worker that dies unfinished is RESUMED (same tab,
# native `--resume`) by the next escalation of the same goal. The old names stay as aliases to the SAME objects.
from nucleo.workers import resume as _wres, quota_wait as _qwait

_WEB_RESUME = _wres._WEB_RESUME
_RESUME_TTL = _wres._RESUME_TTL
_RESUME_CAP = _wres._RESUME_CAP
_resume_persist = _wres._resume_persist
_resume_restore = _wres._resume_restore
_goal_key = _wres._goal_key
_resume_entry = _wres._resume_entry
_leave_resume = _wres._leave_resume
_find_resume = _wres._find_resume


# Loop DUEÑO of the sessions (uvicorn/server). El FlashBrain corre in OTRO loop (job-thread of LiveKit) → todo
# comando of session disparado from the turn of voice is MARSHALEA here (§v3·D), como browser_search.search_sync.
_LOOP: "asyncio.AbstractEventLoop | None" = None


def set_loop(loop) -> None:
    global _LOOP
    _LOOP = loop


# ── the confined DEV WORKER (V2-076) lives in `devworker.py`; re-exported, callers use both access forms.
from nucleo.dispatch.devworker import (  # noqa: F401 — re-export
    _git_tools, _DEV_TOOLS, _dev_worker_params, _dev_prompt,
)


_sem: "asyncio.Semaphore | None" = None


def _pool():
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(_max_parallel())
    return _sem


# V2-354 — the RELOJES viven in `dispatch_thresholds` (trinquete); is re-exportan: `dispatch` es the contrato.
from nucleo.dispatch.thresholds import NO_STEP_SECS, STUCK_SECS  # noqa: F401,E402


# ── An ENDING is a FACT (V2-198/199/222/224/238) — in `nucleo/workers/ended.py` (ratchet, 2026-09-03, V2-566). The
# old names are ALIASES to the SAME objects, so in-place mutation of `dispatch._ENDED_SESSIONS` still hits the dict.
from nucleo.workers import ended as _ended
from nucleo.request import append as _continuity

LIVE_SESSION_STATES = _ended.LIVE_SESSION_STATES
ENDED_SESSION_STATES = _ended.ENDED_SESSION_STATES
JUST_ENDED_S = _ended.JUST_ENDED_S
_ENDED_SESSIONS = _ended._ENDED_SESSIONS
_live_goals = _ended._live_goals
_remember_ended = _ended._remember_ended
recently_ended_sessions = _ended.recently_ended_sessions
mark_death_reported = _ended.mark_death_reported


# ── the results SHEET as progress surface (V2-227 scope C) — moved to `nucleo/sheets.py` (2026-08-24, V2-276),
# which does not import this file; these wrappers pass the record in. Re-exported: a move, not an interface change.
from nucleo.turn_marks import mark_stall_offered, stall_offered  # noqa: F401 — re-export
from nucleo.sheets import (  # noqa: F401 — re-export
    PHASES_KEPT, _phrases, _sheet_close, _sheet_open, retitle as _sheet_retitle, sheet_id_for, sheet_of,
)
from nucleo import docsheet as _docsheet, sheets as _sheets


# V2-059 — lo que el worker REPORTA de sí mismo (fase, plan, progreso, amplitud) vive junto en
# `workers/reports.py`. Re-exportado: `agent_api`, `agentes/worker` y 4 tests llaman por aquí.
from nucleo.workers.reports import (  # noqa: E402,F401 — re-export
    _progress_pct, session_alive, session_considered, session_phase, session_plan, session_progress,
    session_reported)


_last_sync: tuple | None = None


#: Re-exportado for that `run_listener` it resuelva como global of the module — so a test can sustituirlo
#: and the cableado real continues siendo the that is prueba.
about_a_live_errand = _dedup.about_a_live_errand


# ── arranque of a session from a escalada ────────────────────────────────────────────────────────────


_seed_research_criteria = research.seed_criteria   # V2-644: body moved to research.py (ratchet)


# La address of this motor lives in `nucleo/engine_url.py` (V2-296): funcion pura of two env vars, without state
# of the gestor of sessions. Se re-exporta because es a mudanza, no a cambio of interfaz.
from nucleo.engine_url import _own_base_url  # noqa: E402,F401 — re-export


def _task_row(how: str, rec, **kw) -> None:
    """V2-776 D1 — the durable row of an errand that ended BEFORE its worker ran. Each early return of
    `_run_session` used to skip `tasks.closed()` (only the `finally` below reaches it), so the row stayed
    `pending` forever. Best-effort: a store that failed must not change how the errand ended."""
    try:
        from nucleo.circuit import ledger as _tasks
        getattr(_tasks, how)(rec, **kw)
    except Exception:  # noqa: BLE001
        logger.debug(f"dispatch: task row {how} failed", exc_info=True)


async def _run_session(task: 'Task'):
    """V2-778 F1 — the body lives in `nucleo/dispatch/session.py`; this delegate keeps the name (and its patches)."""
    return await _dispatch_session._run_session(task)


def rec_token(rec: "SessionRecord") -> str:
    """Token of auth by-task for the bridges (§v2·D). Se guarda in the own record (atributo dinamico)."""
    tok = getattr(rec, "_token", "")
    if not tok:
        tok = secrets.token_urlsafe(18)
        setattr(rec, "_token", tok)
    return tok


# ── PENDING CONFIRMATION of an irreversible task (V2-126) — moved to `nucleo/dispatch/confirm.py` (F3, 2026-08-23):
# own registry and TTL, no `_SESSIONS` reads. Re-exported; tests mutating `dispatch._PENDING_CONFIRM` still work.
from nucleo.dispatch.confirm import (  # noqa: E402,F401
    _CONFIRM_TTL,     _EXPIRED_CONFIRM,     _EXPIRED_MEMORY_S,     _PENDING_CONFIRM,     _deliver_confirm,
    _sweep_confirm,     absorb_refinement,     confirm_line,     parked_errands,     pending_confirm,
    remember_code_change,     remember_confirm,     resolve_confirm,)


# ── compat: llamada directa (tester) ───────────────────────────────────────────────────────────────────────
async def dispatch(task: "Task") -> str:
    """Compat: starts a session and waits su result (for tests/voice/e2e/agent/llamadas directas)."""
    if not (task.request or "").strip():        # una petición vacía es un no-op, no una sesión
        return ""
    key = str(task.id)
    _SESSIONS[key] = SessionRecord(task_id=key, goal=(task.request or "").strip()[:200],
                                   kind=(task.kind or "generic"))
    await _run_session(task)
    return "(tarea despachada)"


# ── ciclo of vida (lifespan, BRAIN=nucleo) ────────────────────────────────────────────────────────────────
_listener_task: "asyncio.Task | None" = None
_listener_stop: "asyncio.Event | None" = None


def start() -> None:
    global _listener_task, _listener_stop, _LOOP
    if _listener_task is not None and not _listener_task.done():
        return
    try:
        _LOOP = asyncio.get_running_loop()   # loop dueño de las sesiones (server) → marshaling cross-loop (§v3·D)
    except RuntimeError:
        pass
    _resume_restore()               # continuidad web del proceso anterior, ANTES de aceptar escaladas
    _listener_stop = asyncio.Event()
    _listener_task = asyncio.create_task(run_listener(_listener_stop), name="nucleo:workers-dispatch")


async def stop() -> None:
    global _listener_task, _listener_stop
    try:
        await stop_all_async()          # apagado ordenado (§v3·L): mata workers ANTES de parar el listener
    except Exception:
        pass
    if _listener_stop is not None:
        _listener_stop.set()
    if _listener_task is not None:
        _listener_task.cancel()
        try:
            await _listener_task
        except (asyncio.CancelledError, Exception):
            pass
        _listener_task = None
    _listener_stop = None


def running() -> bool:
    return _listener_task is not None and not _listener_task.done()


# V2-778 F1-11 — the escalation listener lives in `nucleo/dispatch/listener.py`; this name delegates to it, so
# `dispatch.start()`, every caller and every test keep calling `dispatch.run_listener`. A module import (not a
# `from … import`) keeps the two-way reference safe whichever module is imported first.
from nucleo.dispatch import listener as _listener  # noqa: E402


def run_listener(*args, **kwargs):
    return _listener.run_listener(*args, **kwargs)
from nucleo.dispatch import session as _dispatch_session  # noqa: E402 — V2-778 F1, reads this module back


# V2-778 F1 — moved to `dispatch_prepare.py`, imported back under their names (that module reads this one).
from .prepare import (  # noqa: E402,F401
    _compose_brief, _TITLE_BG_TASKS, _name_errand, _BRIEF_BG_TASKS, _attach_brief_followup, _FORCE_NEW_RE,
    _COEXIST_RE, _prepare_web, _finalize_web, _compose_context)

from nucleo.dispatch.model import (  # noqa: E402,F401
    _model_for, _tools_for, _max_parallel)
from nucleo.dispatch.registry import (  # noqa: E402,F401
    sync_state, unclosed_uids, active_sessions, has_active, sheets_have_live_work, pending_summaries, get_record,
    record_by_nav_task, _sheet_sessions, sheet_for_nav_task, errand_goal_for_nav_task, sheet_progress,
    task_progress, sheet_harvest, sheet_browser, record_phase)
from nucleo.dispatch.dedup_flow import (  # noqa: E402,F401
    _ALL_RE, _REF_WORD_RE, _norm, _KIND_HINTS, _live_keys, live_traces, _content_words, _target_widget, trace_of,
    has_live_trace, find_duplicate, _live_errands, dedup_scan, _ref_words, _same_thing, resolve_sessions,
    _merge_dedup_flow, _close_escalated_flow)
from nucleo.dispatch.control import (  # noqa: E402,F401
    _schedule_auto_resume, inject, take_pending_injects, cancel_session, cancel_all,
    pause_all, resume_all, stop_all_async)
# The SYNCHRONOUS entries marshalled to the registry's loop are consequence doors (refactor2710-01).
from nucleo.dispatch.soon import cancel_soon, his_words_may_reach_an_errand, inject_soon, relay_his_words, settle_soon  # noqa: E402,F401
