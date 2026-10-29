"""The RECORD of one worker session: what it was asked, what it reported, how it ended — the row the registry
keeps. Part of nucleo.workers.session; module names are read through _s."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio
    from nucleo.workers.session import WorkerSession

import time
from dataclasses import dataclass, field

from nucleo.workers import session as _s
from voice import trace as _trace


@dataclass
class Inject:
    text: str
    ts: float
    state: str = "pending"        # pending | delivered
    trace: str = field(default_factory=_trace.current)   # the turn that sent it: his steer, or our own note (V2-831)


@dataclass
class SessionRecord:
    """The ROW for a live session in the in-memory record (source of truth). Absorbs what was previously scattered
    across escalate._tasks / dispatch._INFLIGHT / dispatch._SESSIONS (§v3·G). The serializable projection is provided
    by `dispatch.active_sessions()`; handles (session/task) do not travel to STATE or /api/tasks."""
    task_id: str
    goal: str
    # V2-728 — the DURABLE `tasks` id of this commission. Not `task_id` (`escalate._seq`, reset each restart).
    # A RELAY inherits it: one commission, one row across provider changes.
    uid: str = ""
    title: str = ""               # V2-530 — the NAME, beside the BRIEF; readers fall back to `goal`
    kind: str = "generic"
    backend: str = ""
    label: str = ""
    phase: str = field(default_factory=lambda: _s._progress.say("queued", "queued"))
    status: str = "queued"        # queued | running | done | error | cancelled
    started: float = field(default_factory=time.time)
    native_sid: str = ""
    waiting_on: str = ""          # "" | "user" | "flash"  (lo fija worker_api al aparcar un ask)
    ask: str = ""                 # text of the active question (if waiting_on)
    ask_corr: str = ""            # corr_id of the active ask
    result_summary: str = ""
    settled: str = ""             # V2-831 T-29: his words that MET its goal — its end is done, not cancelled
    ok: bool = True
    parent_task_id: str = ""
    depth: int = 0
    trace_id: str = ""            # V2-044: trace of the phrase that originated the session (chains all its events)
    heard: str = ""               # his commissioning sentence (Request.heard): what the errand's sheet judges rows by
    nav_task: str = ""            # kind=web: associated browser task ID (card) — set by dispatch
    # V2-259 — this errand's SHEET (`results::<sheet>`), sealed ONCE by `dispatch._sheet_open`. Not `task_id`:
    # `escalate._seq` repeats across restarts, and a new errand reopened (= DELETED) the old `results--1` sheet.
    sheet: str = ""
    # V2-227 — WHERE the operator sees the result, decided when ASSIGNING; closed vocabulary (`nucleo/surfaces.py`):
    # list | item | widget | voice | silent. Sealed ONCE (`set_once`). Empty = not sealed yet.
    surface: str = ""
    # V2-227 scope C — short ring of readable phases for the PROCESS tab (not an audit log); raw `steps` stay apart.
    phases: list = field(default_factory=list)     # [{"t": <ts>, "s": "entrando en booking.com"}]
    last_event_at: float = field(default_factory=time.time)
    # V2-776 D1 — the worker's last SELF report (`hbnote` via `/api/agent/report`): «it told us where it is», unlike
    # `last_event_at` («alive»). The pulse enforces it (D2). 0.0 = never reported.
    reported_at: float = 0.0
    # V2-776 D2 — WHY it failed, in the A5 vocabulary (network | credit | auth | rate | stalled | ours). Written by
    # whoever detects the cause (the stall watchdog, the generator), copied into the durable row on close.
    error_class: str = ""
    injects: list = field(default_factory=list)     # [Inject]
    paused: bool = False           # V2-065: SIGSTOP'd (⏻ del operador) — sigue "running" para el registro, pero
                                    # frozen; do not confuse with status=cancelled (that is irreversible)
    # ── STRUCTURED worker observability (V2-059): `plan` (`hbnote plan "a|b|c"`), `done` (`--done N`), `pct`
    # (0-100, wins over done/plan; -1 = unknown), `note` (latest), `steps` (ring of REAL stream steps).
    plan: list = field(default_factory=list)
    done: int = 0
    pct: int = -1
    note: str = ""
    steps: list = field(default_factory=list)
    # BREADTH (`hbnote considered N --kept M`): candidates REALLY examined, so the brain can say «I've seen 47;
    # enough?». -1 = not reported.
    considered: int = -1
    kept: int = -1
    # V2-707 F2 — HOW SUCCESS IS MEASURED, in `nucleo/circuit/verify.py`'s grammar; the rule is in `workers/goal.py`.
    # Empty = nothing declared, and then nothing is claimed: an absent condition is not a failed one.
    done_when: dict = field(default_factory=dict)
    goal_retried: bool = False
    # Died of PROVIDER quota → `{provider, next, text}`; `_finish` retries ONCE on the handoff tier instead of
    # delivering «API Error … Weekly Limit Exhausted» as the report.
    provider_down: dict | None = None
    provider_retried: bool = False
    # Died (or will) of CONTEXT size (incident 2026-08-18): relaying won't fix it, so NOBODY goes on cooldown —
    # it COMPACTS AND CONTINUES.
    context_full: dict | None = None
    context_retried: bool = False
    # AUTOMATIC relaunches that led to THIS worker. `context_retried`/`provider_retried` live on the record, which
    # each relay rebuilds, so they never bounded the chain: 2026-08-17, SIX workers for one car search (the first
    # 7m47s, $2.0897, 138k tokens; the next four died in ~17 s). A per-instance counter read as a global one.
    relay_gen: int = 0
    # V2-238 — A HANDOFF IS NOT A DEATH: the session PASSED THE BATON; `ok=False` alone told the operator the task
    # «DIED without a result» while the handoff worked.
    handoff: str = ""             # "" = genuinely final · otherwise, where the baton went, in readable form
    # V2-241 — the exact FRAGMENT the gate stopped (`cd /Users/…`), named in the correction and in a silent final.
    perm_denied: str = ""
    ctx_tokens: int = 0             # context size of the last message (for the panel and the watchdog)
    real_model: str = ""            # the model that ACTUALLY ran, when the provider says so (≠ requested alias)
    # runtime handles (NOT serialized):
    session: "WorkerSession | None" = None
    task: "asyncio.Task | None" = None
