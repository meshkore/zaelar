"""Thin HTTP client for zaelar's text/probe channel (`POST /api/flash/say`, V2-032) and the durable
observability API (`GET /api/observability/flow/{corr_id}`). Independent: talks to zaelar only over HTTP,
imports no zaelar core code — same posture as the voice tester's interlocutor/trace.py.

`execute=True` is not optional here: the probe defaults to a dry run (tool calls reported, never fired).
Without it nothing this suite cares about — a worker spawning, a browser navigating — would ever happen.
"""
from __future__ import annotations

import json
import os
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


# ── THE LEDGER OF READS THAT DID NOT HAPPEN (V2-396) ───────────────────────────────────────────────────────
# Every reader below is fail-soft on purpose: ground truth is best-effort and a transient 504 must not throw
# away an eight-minute round. What that posture cost is that a failure and an honest emptiness became the
# same value. Pointed at a closed port the whole report came back `families_observed: []`, `n_events: 0`,
# `widgets_producing: []` — the exact shape of a product that ran and did nothing, with nothing anywhere
# saying the engine was never asked. So the fail-soft stays and the failure is WRITTEN DOWN instead.
_READ_FAILURES: list[dict] = []


def read_failures() -> list[dict]:
    """Which reads failed since the last `clear_read_failures()`, with the reason for each."""
    return list(_READ_FAILURES)


def clear_read_failures() -> None:
    _READ_FAILURES.clear()


def _get(path: str, timeout: float = 15.0) -> dict:
    """`path` must already be percent-encoded — corr_ids and other ids can contain non-ASCII characters
    (e.g. the trace id's "·" separator) that `http.client` cannot put on the request line as-is.

    A failed read returns `{"error": ...}` AND is recorded in `_READ_FAILURES`. Callers are free to keep
    collapsing that into an empty collection — the ledger is what makes the collapse recoverable.
    """
    req = urllib.request.Request(config.ZAELAR_URL.rstrip("/") + path,
                                 headers={"User-Agent": _UA, "X-Observability-Token": config.OBS_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:  # observability is best-effort ground truth, never worth crashing the run over
        _READ_FAILURES.append({"path": path, "reason": f"{type(e).__name__}: {str(e)[:160]}"})
        return {"error": str(e)}


#: Per-turn budget for the probe channel. 90s fixed was sized for the DIRECT titular (TTFT ~1s); on the
#: AIMLAPI relay the broker reasons on every call (it ignores `thinking:disabled` — the very reason direct is
#: titular) and under night load a single turn can exceed 90s. Measured 2026-08-31: two rounds died
    #: «turn N: timed out» in the first hour of the relay-only night shift. Configurable so a relay night can
#: widen it without touching code; the default stays 90 for the titular.
_TURN_TIMEOUT_S = float(os.getenv("UC_TURN_TIMEOUT_S", "90"))


def say(text: str, session: str, *, execute: bool = True, ingest: bool = False,
        timeout: float = _TURN_TIMEOUT_S) -> dict:
    """One turn over the probe channel. Returns the raw response: reply text, tool_calls, tags, trace id,
    and (with execute=True) `executed`/`task_id` for anything that really fired.

    `ingest` defaults to False, matching tests/README.md's own convention for ad-hoc probe calls ("Use a
    unique session and ingest:false unless persistence is the feature under test"): a test conversation has
    no business in the OPERATOR's long-term memory. In a SANDBOX that reason disappears — the memory is
    thrown away with the engine — and leaving it off actively breaks the measurement: a case that asks to be
    remembered can never pass if the write is suppressed by the harness. So the caller passes
    `ingest=sandboxed` (see run._run_scenario) rather than trusting this default. `execute=True` still fires
    tools/escalation normally; `ingest` only gates the durable-memory write."""
    return _post("/api/flash/say", {"text": text, "session": session, "ingest": ingest, "execute": execute},
                 timeout=timeout)


def reset(session: str) -> dict:
    """Clear the probe's conversational window before a scenario. Does NOT touch memory (matches the
    testing playbook's "never test against the operator's real memory" rule at the conversational level;
    memory isolation for use_cases is a follow-up, not solved by this call)."""
    return _post("/api/flash/reset", {"session": session}, timeout=15.0)


def recall(query: str, k: int = 8) -> list[dict] | None:
    """What the engine remembers about something. `POST /api/memory/recall` does NOT require a task token
    (unlike `/api/memory/remember`, which is only for worker bridges), so the harness can READ the sandbox's
    memory without making up credentials.

    It exists for one specific purpose: to check that a preference seed landed BEFORE judging the agent for
    not remembering it. Without this check, a case of «infer what I like» would measure the memory distiller
    and report it as the agent failing to reason.
    """
    try:
        r = _post("/api/memory/recall", {"query": query, "k": k}, timeout=30.0)
    except Exception:
        return None       # V2-400: a failed request is not empty memory — «I could not ask»
    if isinstance(r, dict):
        return r.get("results") or r.get("items") or r.get("memories") or []
    return r if isinstance(r, list) else []


def hard_reset() -> dict:
    """Leaves the engine CLEAN between cases: kills background work, closes the canvas, and rotates the session.

    It exists because of a MEASURED contamination (2026-08-19): one batch shares ONE sandbox, and in
    `find-theatre-tickets__es` the judge saw that «the system was trying to book an irrelevant restaurant» —
    it was the live task from the PREVIOUS case (`restaurant-tonight-madrid`) in the same batch. In other
    words, the case was not measured on its own: it was measured while carrying the neighbor's work along.
    `reset(session)` is not enough for this; it only clears the conversational window; the workers, tasks,
    and canvas remain.

    It deliberately does NOT erase memory (`/reset/hard`, not `/api/reset/full` with `wipe_memory`): erasing it
    requires killing the process and, moreover, discovery cases SEED preferences that must survive this — they
    are seeded afterward, already inside the case.
    """
    return _post("/reset/hard", {}, timeout=60.0)


def canvas_items() -> list:
    """The cards that the SERVER has saved for the desktop (`GET /api/canvas/layout`).

    This is NOT the same as what is visible on screen —the browser owns the canvas (V2-124)— but it is the
    only thing observable from here, and a card that remains in this list reappears as soon as someone reloads.
    """
    data = _get("/api/canvas/layout")
    return list((data or {}).get("items") or []) if isinstance(data, dict) else []


def settle_after_reset(*, budget_s: float = 25.0, poll_s: float = 1.0) -> dict:
    """Waits for the engine to become REALLY clean and returns what it found, whether it was cleaned or not.

    It replaces a `time.sleep(2.0)` followed by printing «engine reset (with no previous work or canvas)»
    regardless of what happened — an assertion nobody checked, in the place where the operator reads it to
    trust that the next case is measured by itself. Two seconds was also an invented number: in the
    2026-08-24 batch, a research worker was still writing to the PREVIOUS case's sheet almost a second after
    the reset, and its card remained on screen.

    The budget is a CEILING, not a wait: as soon as both signals are zero it returns. And if it runs out, it
    returns anyway **saying what remained alive** — stopping the batch because a worker takes time to die
    would cost more than measuring a case with a warning attached.
    """
    import time as _t

    def _still_working() -> list[dict]:
        # The status filter is applied HERE and not delegated to the engine. `active_sessions()` went without
        # filtering until V2-115 —and that gap displayed already-finished tasks as «in progress»—, so waiting
        # for the list to empty without checking the status would tie the next case's start to a registry that
        # has already failed once in that exact way.
        return [x for x in live_tasks() if str(x.get("status") or "") in ("queued", "running", "needs_input")]

    t0 = _t.monotonic()
    tasks, items = _still_working(), canvas_items()
    while (tasks or items) and (_t.monotonic() - t0) < budget_s:
        _t.sleep(poll_s)
        tasks, items = _still_working(), canvas_items()
    return {"clean": not (tasks or items), "waited_s": round(_t.monotonic() - t0, 1),
            "tasks": [str(s.get("goal") or s.get("id") or "?")[:60] for s in tasks],
            "items": [str(i.get("id") or i)[:40] for i in items]}


def flow(corr_id: str) -> list[dict]:
    """The full durable event sequence for one trace id, in order — the ground truth for "what actually
    fired", independent of anything the agent claimed in its reply text."""
    if not corr_id:
        return []
    data = _get(f"/api/observability/flow/{urllib.parse.quote(corr_id, safe='')}")
    return data.get("events", []) if isinstance(data, dict) else []


def current_session_id() -> str | None:
    """The engine's LIVE observability session_id (`/api/observability/identity`) — a server-wide concept, one
    at a time, that rotates only on explicit triggers (reset, session start/end), NOT per conversation. The
    `session` string this suite passes to `say()`/`reset()` is just the probe channel's dialogue-window key; it
    is never written to the `events.session_id` column, so it cannot be used to scope an observability query."""
    data = _get("/api/observability/identity")
    if not isinstance(data, dict) or "error" in data:
        return None                     # NOBODY ANSWERED — which is not the same as "no live session" ("")
    return data.get("session_id", "")


def session_events(session_id: str, *, limit: int = 4000) -> list[dict] | None:
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
    if not isinstance(data, dict) or "error" in data:
        return None                     # see `current_session_id`: an empty stream is a fact, silence is not
    return data.get("events", [])


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


def widgets_producing() -> list[str] | None:
    """Which widgets are PRODUCING right now (audio, video, a live process), according to the engine itself.

    It is queried, not inferred: `active_when` evaluates it in `widgets/producers.py` against the widget's
    `view_data()`, and reimplementing it here would create a second truth that could diverge from the one
    used by the product. `None` means it COULD NOT BE QUERIED; a list (possibly empty) means the engine
    answered. V2-395 taught the judge this distinction, and returning `[]` for an unreachable engine resolved
    it precisely through the branch that accuses the product. It never raises: it is report data, not a turn step.
    """
    try:
        d = _get("/widgets/producing")
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(d, dict) or "error" in d:
        return None
    return [str(x) for x in d.get("producing") or []]


def _widget_path(wid: str, q: str = "") -> str:
    """The read route of ONE widget box. `q` is how an INSTANCE is asked for: since V2-259 a results sheet is
    keyed per errand and the route takes the suffix as a query argument (`results` + `q=2` is the box of task
    2). Without it every read lands on the un-instanced box, which after V2-259 is a DIFFERENT box from the
    one the errand wrote to — a reader pointed there does not fail, it invents (see `verify.results_sheet`).

    It is a shared helper and not a line inside one reader on purpose: the two readers below are the same
    request seen at two shapes, and when only one of them learned about `q` the other went on quietly reading
    the wrong box.
    """
    path = f"/widgets/{urllib.parse.quote(wid, safe='')}/data"
    return path + (f"?q={urllib.parse.quote(q, safe='')}" if q else "")


def widget_rows(wid: str, key: str, q: str = "") -> list:
    """One collection of a widget, READ from the engine: `GET /widgets/<wid>/data`.

    It exists because of an expensive false positive (2026-08-20): the judge wrote "zero appointments
    persisted" about `remember-and-remind-deadline` on two consecutive rounds, and the harness had NEVER
    looked at that — it had no way to look. The engine team reproduced it and found the opposite: the
    appointment was written. The source of truth was one HTTP request away.

    The rule that comes out of it: about a widget's persistence, only what has been READ may be asserted. An
    empty list and "I did not look" are nothing alike, so the report keeps the two apart.
    """
    d = _get(_widget_path(wid, q), timeout=20.0)
    v = d.get(key) if isinstance(d, dict) else None
    return v if isinstance(v, list) else []


def widget_data(wid: str, q: str = "") -> dict | None:
    """A widget's WHOLE state, or `None` when the engine could not be asked.

    `widget_rows` above collapses both failures into `[]`, which is right for its caller (it wants a
    collection) and wrong for anything that has to tell "the widget is empty" from "nobody looked" — the very
    distinction its own docstring says the report must keep. This returns the raw dict so that call sites can
    keep the two apart instead of inferring absence from a shape.
    """
    d = _get(_widget_path(wid, q), timeout=20.0)
    if not isinstance(d, dict) or not d or "error" in d:
        return None       # `_get` reports a failed request as `{"error": ...}`, never as an empty payload
    return d


def scheduled_jobs() -> list[dict]:
    """The engine's ACTIVE scheduled tasks (`GET /api/cron` → `scheduler.list_jobs`).

    Why this is a mechanism source and not a nicety: a whole class of use case ("remind me Wednesday", "never
    let it auto-renew without asking", "order flowers the day before, every year") succeeds by leaving a
    durable TRIGGER behind, and the mechanism report had no field for one. So the judge could not see a
    reminder that genuinely existed, and the only visible difference between a real one and the words "listo,
    te aviso el miércoles" was nothing at all — which is precisely the failure these cases exist to catch.
    Reported by the session running the fixes (V2-121) as the reason its round could not be judged honestly.
    """
    data = _get("/api/cron")
    jobs = (data or {}).get("jobs")
    return jobs if isinstance(jobs, list) else []


def memory_map() -> dict:
    """The memory as the ENGINE sees it (`GET /api/memory/map`): state + pills, already resolved.

    Asking the engine rather than its database is the point. `state.language` is stored as `null` when nobody
    chose one explicitly and `state.read()` resolves it against the active configuration, so the raw row says
    "null" while the distiller is happily writing in Spanish. Reading the column and calling that "unknown" is
    the same mistake as reading any field at the wrong level: it does not fail, it invents.
    """
    return _get("/api/memory/map", timeout=20.0)
