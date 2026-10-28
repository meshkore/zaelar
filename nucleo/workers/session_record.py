"""The RECORD of one worker session: what it was asked, what it reported, how it ended — the row the registry
keeps. Part of nucleo.workers.session; module names are read through _s."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from nucleo.workers import session as _s


@dataclass
class Inject:
    text: str
    ts: float
    state: str = "pending"        # pending | delivered


@dataclass
class SessionRecord:
    """The ROW for a live session in the in-memory record (source of truth). Absorbs what was previously scattered
    across escalate._tasks / dispatch._INFLIGHT / dispatch._SESSIONS (§v3·G). The serializable projection is provided
    by `dispatch.active_sessions()`; handles (session/task) do not travel to STATE or /api/tasks."""
    task_id: str
    goal: str
    # V2-728 — the DURABLE id of the commission this session serves, in `tasks`. NOT `task_id`: that one is
    # `escalate._seq`, which returns to 0 every restart, so it names a session and never an errand. A RELAY
    # inherits this value, which is what keeps one commission one row across a change of provider.
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
    ok: bool = True
    parent_task_id: str = ""
    depth: int = 0
    trace_id: str = ""            # V2-044: trace of the phrase that originated the session (chains all its events)
    nav_task: str = ""            # kind=web: associated browser task ID (card) — set by dispatch
    # V2-259 — the SHEET for this errand (`results::<sheet>`), sealed ONCE by `dispatch._sheet_open`. It is not
    # `task_id` alone, and that was a real defect: `escalate._seq` starts at 0 in each process, so IDs
    # REPEAT across restarts and the first errand of a new startup landed in the previous session's
    # `results--1` sheet — which `begin_task(fresh=True)` opens anew, that is, DELETES. Exactly the «search deletion
    # error» this initiative exists to remove, reintroduced through the back door.
    sheet: str = ""
    # V2-227 — WHERE the operator will see the result, decided when ASSIGNING it and not when delivering it. CLOSED
    # vocabulary (`nucleo/surfaces.py`): list | item | widget | voice | silent. It is sealed ONCE (`set_once`) and
    # not reconsidered midway: changing surfaces when the operator is already looking at the first is worse than
    # having chosen incorrectly. Empty = not sealed yet (for example, a session created manually in a test).
    surface: str = ""
    # V2-227 scope C — the HISTORY of readable phases, for the sheet's PROCESS tab. Short ring: it is
    # what the operator is looking at now, not an audit log (that already lives in observability). It is kept
    # separate from `steps`, which are the raw steps derived from the stream and are shown to nobody.
    phases: list = field(default_factory=list)     # [{"t": <ts>, "s": "entrando en booking.com"}]
    last_event_at: float = field(default_factory=time.time)
    # V2-776 D1 — the last report the worker made ITSELF (`hbnote` via `/api/agent/report`). `last_event_at`
    # moves on every stream event, so it says «the process is alive»; this says «it told us where it is», which is
    # the obligation the pulse enforces (D2). 0.0 = it has not reported once.
    reported_at: float = 0.0
    # V2-776 D2 — WHY it failed, in the A5 vocabulary (network | credit | auth | rate | stalled | ours). Written by
    # whoever detects the cause (the stall watchdog, the generator), copied into the durable row on close.
    error_class: str = ""
    injects: list = field(default_factory=list)     # [Inject]
    paused: bool = False           # V2-065: SIGSTOP'd (⏻ del operador) — sigue "running" para el registro, pero
                                    # frozen; do not confuse with status=cancelled (that is irreversible)
    # ── observabilidad ESTRUCTURADA del worker (V2-059) ──────────────────────────────────────────────────────
    # The worker opens a Claude Code session with opaque INTERNAL work. To view it in a controlled way:
    #  · `plan`  = the list of tasks the worker DECLARES at startup (`hbnote plan "a|b|c"`).
    #  · `done`  = how many plan steps it has completed (`hbnote progress --done N`) → progress = done/len(plan).
    #  · `pct`   = explicit 0-100 progress if reported (takes precedence over done/plan); -1 = derive/unknown.
    #  · `note`  = latest readable progress note.
    #  · `steps` = ring of the latest REAL steps (derived from the stream: tool + where + what) → debug + UI.
    plan: list = field(default_factory=list)
    done: int = 0
    pct: int = -1
    note: str = ""
    steps: list = field(default_factory=list)
    # BREADTH of an investigation (`hbnote considered N --kept M`): how many candidates the worker REALLY
    # examined before keeping M. This is what separates a defensible selection from the first three search-result
    # rows, and lets the brain offer «I've seen 47; is that enough, or should I continue?» instead of hiding the fact.
    # -1 = not reported (a task that is not an investigation, or a worker that did not say).
    considered: int = -1
    kept: int = -1
    # V2-707 F2 — HOW SUCCESS IS MEASURED, in `nucleo/verify.py`'s grammar; the rule is in `workers/goal.py`.
    # Empty = nothing declared, and then nothing is claimed: an absent condition is not a failed one.
    done_when: dict = field(default_factory=dict)
    goal_retried: bool = False
    # Died because the PROVIDER ran out of quota (not because of the task) → `{provider, next, text}`. The
    # backend sets it when it sees the error; `_finish` uses it to retry ONCE with the handoff tier instead of
    # delivering the operator an «API Error … Weekly Limit Exhausted» as though it were the report.
    provider_down: dict | None = None
    provider_retried: bool = False
    # Died (or is about to) because the CONTEXT no longer fits, not because the provider failed (incident
    # 2026-08-18). A separate family on purpose: relaying to another provider does not fix a blown context — the
    # next one blows up identically — so this puts NOBODY on cooldown: it COMPACTS AND CONTINUES with what was learned.
    context_full: dict | None = None
    context_retried: bool = False
    # How many AUTOMATIC relaunches led to THIS worker. `context_retried`/`provider_retried` above read like
    # they bound the chain ("relaunched ONCE"), and they do not: they live on the RECORD, and every relay builds
    # a fresh one, so each new worker starts at False and may relay again. Measured on the operator's own engine
    # (2026-08-17, `zaelar.db`): SIX workers for one car search. The first ran 7m47s and died on a context-window
    # error after $2.0897 and 138k tokens; the next four were born 3-8s after the previous one ended and died in
    # ~17s with the SAME error. `depth` was travelling through the relay UNCHANGED, so it could not count it
    # either. Same shape as the sheet id that reset on every process: a per-instance counter read as if it were
    # a global one.
    relay_gen: int = 0
    # V2-238 — A HANDOFF IS NOT A DEATH. When one of `_finish`'s two deliveries completes (provider handoff,
    # compact-and-continue), this session has not failed: it has PASSED THE BATON to another that is already
    # running. Without this fact, `ok=False` made it indistinguishable from a dead worker, and the engine told the
    # operator that their task «DIED without a result and will not be retried automatically» while the handoff worked.
    handoff: str = ""             # "" = genuinely final · otherwise, where the baton went, in readable form
    # V2-241 — the exact FRAGMENT the gate stopped (`cd /Users/…`, `curl -s https://…`). It is stored so it can be
    # named in the correction —a general rule does not say which of its commands is unnecessary— and so a final
    # without delivery can say why it was left incomplete instead of staying silent.
    perm_denied: str = ""
    ctx_tokens: int = 0             # context size of the last message (for the panel and the watchdog)
    real_model: str = ""            # the model that ACTUALLY ran, when the provider says so (≠ requested alias)
    # runtime handles (NOT serialized):
    session: "WorkerSession | None" = None
    task: "asyncio.Task | None" = None
