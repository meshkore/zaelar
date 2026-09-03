"""
observability.identity — WHO and WHEN: the user of this installation and the current work session.

Events already knew WHAT happened (`kind`), which COMPONENT (`cat`), and which FLOW (`trace`/correlation id).
They were missing the two axes that make it possible to analyze REAL usage:

- **`user_id`** — stable for the lifetime of this installation. A **random UUID4** is generated the first time and
  persisted. Random and non-sequential by design: it does not identify anyone by itself and cannot collide with
  that of another installation. If the environment already provides one (`ZAELAR_USER_ID`), it takes precedence —
  whoever deploys it can set the identity, and this module does not need to know why.
- **`session_id`** — one UUID4 per WORK SESSION: from when the operator starts the agent until they close the
  browser or press the stop button. It is neither the process (the server can run for weeks) nor the turn (which
  lasts seconds): it is the stretch of work the operator would recognize as “this afternoon’s work.”

**Where each thing lives, and why:** `user_id` goes into a JSON file in `config/` (gitignored), deliberately NOT
into the database — a `reset` with “delete memory” destroys `zaelar.db`, and losing the installation’s identity
every time someone clears its memory would make any longitudinal analysis useless. The session, by contrast, is
ephemeral by definition and lives in RAM.

Everything is defensive: if the file cannot be read or written, an in-memory process id is returned. An
observability failure must NEVER bring down a work session.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from loguru import logger

from nucleo import workspace as _workspace

_lock = threading.Lock()
_user: dict = {"id": None}
_session: dict = {"id": None, "started_ms": None, "source": ""}

# REAL INACTIVITY ceiling (operator, 2026-08-13): without this, a session lives in RAM until ⏻/the tab
# EXPLICITLY closes it, and if that signal never arrives (network cut, tab killed without `pagehide`) it stays alive
# forever, accumulating events from work segments that have nothing to do with each other. Safety net; it does not
# replace explicit closing — it only acts when that closing did not arrive.
IDLE_TIMEOUT_MS = int(os.getenv("ZAELAR_SESSION_IDLE_MIN", "5")) * 60_000
_last_real_activity_ms: dict = {"v": None}

# HEARTBEAT to the control-plane (2026-08-15, operator's proposal). The explicit session close
# (`_report_to_control_plane("end", ...)`) is best-effort: if the Machine dies hard (OOM, `kill -9`) it never
# arrives, and the backoffice (`cloud/backoffice/src/flyQuery.js`) had to GUESS "is this account still alive?"
# from the timestamp of the most recent event in the account's own SQLite — a 60s window polluted by background
# noise (homeostasis/cron), not a signal designed for this. No need to invent anything: the same "start" report
# already sent on open (`_report_to_control_plane`) already touches `last_seen_at` on the control-plane
# (`userSessions.touch`, idempotent — no new row, no `energy`/`events` duplication with `energy=0`). Repeating
# it every `_HEARTBEAT_INTERVAL_S` while the session stays open gives that mark the precision it was missing,
# with no new verb on the control-plane. Still a total no-op on a local install without
# `CONTROL_PLANE_URL`/`ZAELAR_USER_ID` (same guard as `_report_to_control_plane`) — one single piece of code
# serves both the self-hosted engine and the one deployed on Fly. Do NOT confuse this with the 4s heartbeat in
# `server/livekit_api.py` (an in-memory "one tab per machine" lock, no control-plane involved).
_HEARTBEAT_INTERVAL_S = float(os.getenv("ZAELAR_SESSION_HEARTBEAT_S", "15"))
_heartbeat: dict = {"task": None}

# The server's event loop, captured once from the lifespan — same cross-thread bridge as
# `nucleo/energy_meter.py::set_loop` (V2-102) and for a sharper version of the same reason: a work session is
# usually opened LAZILY, by whatever thread emits the first real event, and that thread has no loop of its own.
_loop = None


def set_loop(loop) -> None:
    """Captures the server's loop so a session opened off-loop can still report itself and beat."""
    global _loop
    _loop = loop


def _identity_file() -> Path:
    return _workspace.root() / "config" / "identity.json"


def user_id() -> str:
    """The STABLE id of this installation: the one supplied by the environment, if any, or a persisted UUID4 of our own."""
    from nucleo import cloud_account

    provided = cloud_account.my_user_id()
    if provided:
        return provided
    if _user["id"]:
        return _user["id"]
    with _lock:
        if _user["id"]:
            return _user["id"]
        p = _identity_file()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            uid = str(data.get("user_id") or "").strip()
        except Exception:
            uid = ""
        if not uid:
            uid = str(uuid.uuid4())
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".json.tmp")
                tmp.write_text(json.dumps({"user_id": uid, "created_ms": round(time.time() * 1000)},
                                          ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, p)          # atomic: an interruption during writing does not leave a corrupt file
            except Exception:
                pass                        # without a writable disk we continue with a process id and break nothing
        _user["id"] = uid
        return uid


def _announce(info: dict) -> None:
    """Everything a session owes the world the instant it is BORN, in ONE place (V2-562).

    There are two doors into a new session — the explicit `begin_session()` and the lazy self-open below — and
    only the first one used to announce itself, so a session born lazily existed locally and was invisible to
    the central activity registry: `POST /session` only ever arrived with `event="end"`, and closing a row that
    was never opened is an UPDATE matching nothing. Measured 2026-09-03 on the real control-plane:
    `zaelar_user_sessions` held **0 rows for every account since the table was created**, while every Machine's
    `/session` call returned 200. The registry that exists precisely to survive a Machine being destroyed was
    recording nobody, and nothing failed.

    So the announcement is not the caller's to remember: a session cannot be born without it. Called OUTSIDE
    `_lock` on purpose — reporting talks to the network and starting the heartbeat touches the event loop."""
    _emit_session("start", info, extra={"source": info.get("source") or ""})
    _report_to_control_plane("start", info)
    _start_heartbeat(info)


def session_id() -> str:
    """The CURRENT work session. It opens automatically on first use — an event is never left without a session."""
    if _session["id"]:
        return _session["id"]
    born = None
    with _lock:
        if not _session["id"]:
            _session["id"] = str(uuid.uuid4())
            _session["started_ms"] = round(time.time() * 1000)
            _session["source"] = _session["source"] or "auto"
            born = dict(_session)
    if born is not None:
        _announce(born)
    return _session["id"]


def begin_session(source: str = "frontend", force: bool = False) -> dict:
    """Opens the work session. **Reuses the one already open** unless `force`: the frontend calls this every time
    it connects, and a reconnection after a network hiccup or a light `/reset` is NOT a new session — splitting it
    in two would distort any analysis of “how long it lasted and what it did.” A new session is born only when the
    previous one was truly CLOSED (⏻ or tab closed), precisely when none is open.

    **A STOPPED agent has no work session at all**: with ⏻ off this opens nothing and returns `{}`. Measured on
    the operator's engine 2026-08-31 — with the agent stopped, pressing Reset minted a brand-new session that
    then sat "EN CURSO" in the master indefinitely, holding nothing but the browser tab's own background noise
    (7 events, 0 flows, no work). `voice/observer.py::stamp_identity` has refused to let an EVENT self-open a
    session while stopped since 2026-08-16; this closes the OTHER door, the explicit `begin_session` calls (the
    reset, the frontend endpoint), which walked straight past that guard. “Stopping means stopped” (V2-092): the session
    that groups the work reopens when the work can happen again — ⏻ ON (`nucleo/runstate.py::start`) — never as
    a side effect of a gesture made in front of a stopped agent."""
    if _agent_stopped():
        return {}
    with _lock:
        if _session["id"] and not force:
            return dict(_session)
        _session["id"] = str(uuid.uuid4())
        _session["started_ms"] = round(time.time() * 1000)
        _session["source"] = (source or "frontend")[:40]
        info = dict(_session)
    _announce(info)
    return info


def end_session(reason: str = "frontend") -> dict:
    """Closes the current session (stop button, tab closed). The next event will open a new one automatically:
    we prefer a clearly marked orphaned session to an event without a session."""
    with _lock:
        info = dict(_session)
        _session["id"] = None
        _session["started_ms"] = None
        _session["source"] = ""
    _stop_heartbeat()
    if info.get("id"):
        dur = round(time.time() * 1000) - (info.get("started_ms") or 0)
        _emit_session("end", info, extra={"reason": (reason or "")[:40], "duration_ms": dur})
        _report_to_control_plane("end", info)
        _bill_transport(dur)
    return info


# Real-time transport (LiveKit) is billed per PARTICIPANT-minute and a voice session has TWO of them
# (the operator and the agent), so the session's wall-clock is doubled here. It is charged per SESSION
# rather than per turn because the room is up — and billing — during the silences between turns too,
# which is exactly the part no per-turn hook would ever see.
#
# Only the duration crosses this seam: whether that costs anything, and how much, is the tariff's
# business (`nucleo/energy_tariffs.py` — it may legitimately be zero while the deployment sits inside
# LiveKit's included quota). Failing to bill must never break closing a session, hence the guard.
_TRANSPORT_PARTICIPANTS = 2


def _bill_transport(duration_ms: int) -> None:
    if duration_ms <= 0:
        return
    try:
        from nucleo import energy_meter
        energy_meter.report_transport_usage(
            participant_seconds=(duration_ms / 1000.0) * _TRANSPORT_PARTICIPANTS)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"identity: could not bill the transport for this session: {e}")


def note_real_activity() -> None:
    """Marks that REAL activity has occurred (voice/worker/memory/widget — never background noise such as
    homeostasis/pulse/cron). If the open session has gone longer than `IDLE_TIMEOUT_MS` without any, it CLOSES it
    (same path as ⏻, reports `end_session('idle_timeout')` to the timeline and control plane) and leaves it closed:
    the next `session_id()` will open a new one automatically. Only REAL activity counts for the clock — if the
    pulse extended it, a live but unused machine would never rotate; if the pulse could trigger rotation, an idle
    machine would rotate on every pulse tick. With this filter: neither one nor the other — only the real gap matters."""
    now = round(time.time() * 1000)
    with _lock:
        last = _last_real_activity_ms["v"]
        idle = bool(_session["id"] and last is not None and (now - last) > IDLE_TIMEOUT_MS)
        _last_real_activity_ms["v"] = now
    if idle:
        end_session("idle_timeout")


def _agent_stopped() -> bool:
    """The server-side ⏻ switch (`nucleo/runstate`, V2-092). Fail-OPEN on purpose: a switch that cannot be read
    counts as RUNNING, because the cost of the two mistakes is not symmetric — wrongly refusing to open a session
    loses the operator's work from the record for good, wrongly opening one leaves a session the idle timeout
    closes on its own."""
    try:
        from nucleo import runstate
        return runstate.stopped()
    except Exception:
        return False


def close_if_idle() -> bool:
    """Closes the open session once it has gone longer than `IDLE_TIMEOUT_MS` with no REAL activity. Same
    decision as `note_real_activity`, taken from the other side: THAT one can only fire when activity comes
    BACK, so a session nobody ever returns to (the operator walks away, a tab dies without `pagehide`) stayed
    open forever and read "EN CURSO" in the master with nothing happening inside it. The pulse calls this
    (`nucleo/loop.py::tick`). It only ever CLOSES — it never opens a session and never touches the activity
    clock — so an idle machine closes once and then has nothing left to close.

    The clock counts from the LATER of the last real activity and this session's own start: `_last_real_activity_ms`
    is global, so a brand-new session opened after a long quiet stretch would otherwise be born already expired."""
    with _lock:
        if not _session["id"]:
            return False
        ref = max(_last_real_activity_ms["v"] or 0, _session["started_ms"] or 0)
        idle = (round(time.time() * 1000) - ref) > IDLE_TIMEOUT_MS
    if idle:
        end_session("idle_timeout")
    return idle


def session_info() -> dict:
    sid = _session["id"]
    return {"session_id": sid, "started_ms": _session["started_ms"], "source": _session["source"],
            "user_id": user_id()}


def _report_to_control_plane(label: str, info: dict) -> None:
    """Optional notice to an external logging service that a session is starting or ending, when the deployment
    has one configured (`CONTROL_PLANE_URL` + a `ZAELAR_USER_ID`). **In a normal installation this is a no-op**:
    without those variables nothing is contacted and not a single byte leaves the machine.

    Same guarded-until-configured contract as `nucleo/energy_meter.py`: fire-and-forget, and a failure can NEVER
    bring down starting or closing a session. No event or transcription is sent — only
    `(user_id, session_id, start|end)`."""

    try:
        import asyncio
        import os

        from nucleo import cloud_account

        url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
        uid = cloud_account.my_user_id()
        if not url or not uid:
            return

        async def _post() -> None:
            import httpx
            token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    await client.post(url.rstrip("/") + "/session",
                                      json={"user_id": uid, "session_id": info.get("id"), "event": label},
                                      headers={"X-Service-Token": token} if token else {})
            except Exception as e:  # noqa: BLE001
                logger.warning(f"observability: reporte de sesión '{label}' falló (no fatal): {e}")

        try:
            asyncio.get_running_loop()
            asyncio.create_task(_post())
            return
        except RuntimeError:
            pass
        # No loop in THIS thread. A work session most often opens LAZILY, from whatever thread emitted the first
        # real event — the voice thread, a `to_thread` worker — none of which has a loop, so the report was
        # dropped exactly where it mattered most and the central registry never learned the session existed.
        # Same bridge `nucleo/energy_meter.py::_fire_and_forget` uses for the identical problem (V2-102). No
        # loop captured yet (a unit test) → drop, same as before.
        if _loop is not None:
            asyncio.run_coroutine_threadsafe(_post(), _loop)
    except Exception:
        pass


async def _heartbeat_loop(info: dict) -> None:
    """Repeats the "start" report every `_HEARTBEAT_INTERVAL_S` while the session stays alive — see the
    `_heartbeat`/`_HEARTBEAT_INTERVAL_S` comment above. `_report_to_control_plane` is already a no-op when
    unconfigured, so this loop costs nothing on a local install: it just sleeps and sends not a single byte."""
    import asyncio
    try:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_S)
            _report_to_control_plane("start", info)
    except asyncio.CancelledError:
        pass


def _start_heartbeat(info: dict) -> None:
    _stop_heartbeat()
    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Same reason as `_report_to_control_plane`: a lazily-opened session is born on whatever thread
            # emitted the first event, and that thread has no loop of its own. Without the bridge the session
            # would report its start once and then never refresh `last_seen_at`, so a long quiet session would
            # look abandoned to the master. `call_soon_threadsafe` (not `run_coroutine_threadsafe`) so the task
            # HANDLE lands in `_heartbeat` and `_stop_heartbeat` can still cancel it.
            loop = _loop
            if loop is None:
                return
            loop.call_soon_threadsafe(lambda: _heartbeat.update({"task": loop.create_task(_heartbeat_loop(info))}))
            return
        _heartbeat["task"] = loop.create_task(_heartbeat_loop(info))
    except Exception:  # noqa: BLE001
        pass          # no loop at all (startup, a test) — no heartbeat to launch, and none needed


def _stop_heartbeat() -> None:
    t = _heartbeat["task"]
    if t is not None:
        t.cancel()
    _heartbeat["task"] = None


def _emit_session(label: str, info: dict, extra: dict | None = None) -> None:
    """Session marker in the event thread itself. Lazy import: `voice.observer` imports this module.

    `sid` is stamped EXPLICITLY here, and that one word is the whole point of the line. By the time the CLOSING
    event is emitted `_session["id"]` is already `None`, and `stamp_identity` — correctly, since 2026-08-15 —
    refuses to invent a session for a `system` event: the event went out with an empty `sid`, and
    `observer._session_path("")` then dropped it instead of writing it. Measured 2026-08-31: not ONE of the last
    twelve session files on the operator's engine held its own `session/end` record, so opening a session to
    audit it could never say how or why it ended — the closing mark existed in RAM and in the live timeline, and
    nowhere durable. Passing the id we already hold puts the mark in the file of the session it closes, and opens
    nothing: it is a value, not a lookup."""
    try:
        from voice.observer import emit
        emit("session", label, role="system",
             extra={"sid": info.get("id") or "", "session_id": info.get("id"),
                    "user_id": user_id(), **(extra or {})})
    except Exception:
        pass
