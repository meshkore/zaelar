"""Thin HTTP client for zaelar's text/probe channel (`POST /api/flash/say`, V2-032) and the durable
observability API (`GET /api/observability/flow/{corr_id}`). Independent: talks to zaelar only over HTTP,
imports no zaelar core code — same posture as the voice tester's interlocutor/trace.py.

`execute=True` is not optional here: the probe defaults to a dry run (tool calls reported, never fired).
Without it nothing this suite cares about — a worker spawning, a browser navigating — would ever happen.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import config

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _post(path: str, body: dict, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        config.ZAELAR_URL.rstrip("/") + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": _UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get(path: str, timeout: float = 15.0) -> dict:
    """`path` must already be percent-encoded — corr_ids and other ids can contain non-ASCII characters
    (e.g. the trace id's "·" separator) that `http.client` cannot put on the request line as-is."""
    req = urllib.request.Request(config.ZAELAR_URL.rstrip("/") + path,
                                 headers={"User-Agent": _UA, "X-Observability-Token": config.OBS_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:  # observability is best-effort ground truth, never worth crashing the run over
        return {"error": str(e)}


def say(text: str, session: str, *, execute: bool = True, ingest: bool = False, timeout: float = 90.0) -> dict:
    """One turn over the probe channel. Returns the raw response: reply text, tool_calls, tags, trace id,
    and (with execute=True) `executed`/`task_id` for anything that really fired.

    `ingest` defaults to False, matching tests/README.md's own convention for ad-hoc probe calls ("Use a
    unique session and ingest:false unless persistence is the feature under test") — this suite tests
    real-world task execution, not memory writing, and must not leave test conversations in the operator's
    actual long-term memory. `execute=True` still fires tools/escalation normally; `ingest` only gates the
    durable-memory write."""
    return _post("/api/flash/say", {"text": text, "session": session, "ingest": ingest, "execute": execute},
                 timeout=timeout)


def reset(session: str) -> dict:
    """Clear the probe's conversational window before a scenario. Does NOT touch memory (matches the
    testing playbook's "never test against the operator's real memory" rule at the conversational level;
    memory isolation for use_cases is a follow-up, not solved by this call)."""
    return _post("/api/flash/reset", {"session": session}, timeout=15.0)


def flow(corr_id: str) -> list[dict]:
    """The full durable event sequence for one trace id, in order — the ground truth for "what actually
    fired", independent of anything the agent claimed in its reply text."""
    if not corr_id:
        return []
    data = _get(f"/api/observability/flow/{urllib.parse.quote(corr_id, safe='')}")
    return data.get("events", []) if isinstance(data, dict) else []


def current_session_id() -> str:
    """The engine's LIVE observability session_id (`/api/observability/identity`) — a server-wide concept, one
    at a time, that rotates only on explicit triggers (reset, session start/end), NOT per conversation. The
    `session` string this suite passes to `say()`/`reset()` is just the probe channel's dialogue-window key; it
    is never written to the `events.session_id` column, so it cannot be used to scope an observability query."""
    data = _get("/api/observability/identity")
    return data.get("session_id", "") if isinstance(data, dict) else ""


def session_events(session_id: str, *, limit: int = 2000) -> list[dict]:
    """Every durable event tied to the engine's live observability session, across however many corr_ids it
    spans. Deliberately not scoped to any one turn's trace id: a dispatched worker's own steps (browser
    navigate/screenshot/etc.) mint FRESH corr_ids as they run (every stimulus is born with its own trace,
    V2-044) rather than inheriting the turn that triggered them — confirmed 2026-08-17 investigating a scenario
    where a real browser search launched, navigated and screenshotted for two minutes, yet per-turn `flow()`
    polling reported `worker`/`widget` as entirely missing because none of that activity's corr_ids matched any
    polled turn's trace id. Pass `current_session_id()`, not the probe's own `session` string (see its
    docstring) — the two are unrelated identifiers."""
    if not session_id:
        return []
    data = _get(f"/api/observability/events?session_id={urllib.parse.quote(session_id, safe='')}&limit={limit}")
    return data.get("events", []) if isinstance(data, dict) else []


def live_tasks() -> list[dict]:
    """The engine's LIVE worker-session registry (`GET /api/tasks` → `dispatch.active_sessions()`, the RAM
    registry that is the source of truth for the Procesos tab). Each entry carries `id`/`kind`/`goal`/
    `phase`/`status`.

    This is the only honest way to prove CONCURRENCY for a multi-flow scenario: the durable event stream can
    show afterwards that N tasks existed, but not that two were ever in flight at the same MOMENT — for that
    you have to look while it's happening. `tests/journey/runner.py` polls the same endpoint for the same
    reason. Note it returns only live (`queued`/`running`) sessions — finished ones move to the ledger
    (`nucleo/workers/ledger.py`), so a task that already completed correctly disappears from here rather than
    lingering as a false "still working"."""
    data = _get("/api/tasks")
    if not isinstance(data, dict):
        return []
    sessions = data.get("sessions")
    return sessions if isinstance(sessions, list) else []


def navegador_task(task_id: str) -> dict:
    """A browser task's current/final state from OUTSIDE the conversation — real extracted results if any,
    independent of the transcript. `task_id` is the navegador task id (not the escalation's worker id)."""
    if not task_id:
        return {}
    return _get(f"/widgets/navegador/data?q={urllib.parse.quote(task_id, safe='')}")
