#
# Slim timeline / SSE bridge for the assistant (English).
#
# Trimmed copy of the interview observer: just enough to (a) stream conversation + pipeline events to the
# browser over SSE, and (b) measure per-turn latency (user stops talking → first LLM token → first audio out),
# which is the whole point of this prototype. No interview folders, no scoring, no archive.
#
import json
import os

# Logging lives in the MeshKore standard location: .meshkore/logs/ (gitignored runtime dir). `ZAELAR_LOG_DIR`
# overrides it (same test-isolation/headless knob as bus/log.py's ZAELAR_DB and nucleo/workspace.py's
# ZAELAR_WORKSPACE): without it, behavior is byte-identical to before. The test suite sets it (root conftest.py)
# so unit tests that call observer.emit() — e.g. tests/infrastructure/integration/test_sse_observer.py's
# "error/boom/oops", the architect
# tests — never append synthetic events to the LIVE timeline the running server/operator reads for real
# post-mortems (found 2026-07-25: an audit flagged a test's "kind:error boom" as if it were a real incident).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # voice/.. = repo root
LOG_DIR = os.getenv("ZAELAR_LOG_DIR") or os.path.join(_REPO_ROOT, ".meshkore", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_t0 = {"v": None}

# CATEGORIES in the observability viewer — the families in the top filter.
#
# REDESIGN 2026-08-09 (operator request): remove “Main,” which was a catch-all where the
# conversation, widgets, tasks, and transport plumbing. The families are now the system’s REAL PIECES,
# system, which is how the operator reasons when debugging: **FlashBrain · Brain Workers · Memory · Widgets ·
# System/Code · Pulse**. The first four are ON by default; `system` and `pulse` are OFF (internal and noisy).
#
# An unmapped `kind` belongs to no family — and the viewer treats it as ALWAYS VISIBLE (it is never hidden by
# the category axis). This is deliberate: a new capability introducing its own kind must be SEEN until someone
# someone classifies it here; silence by omission is the worst way to lose a signal. The same applies to `error`/`alert`.
_CAT = {
    # ── FlashBrain (ON) — the TURN: what was said, decided by the orchestrator, searched, or audited by Susurro.
    "brain": "flash", "transcript": "flash", "ambient": "flash", "search": "flash",
    "susurro": "flash", "rail": "flash", "trace": "flash",
    # `filler` (V2-122 addenda, 2026-08-18): the lead-in wait-filler ("Un segundo…"), explicitly PUSHED to the
    # chat wall (see `voice/engine/speech/filler_audio.py`) — same family as the turn that spoke it, but its own kind so the
    # frontend can mark it distinctly (never confused with a real LLM-generated reply).
    "filler": "flash",
    # `cron` (V2-121, 2026-08-18): schedule/cancel a reminder. Family `flash` because the DECISION belongs to the turn,
    # like a data-op or escalation; its own kind exists so a scheduled reminder leaves a
    # distinguishable trace in the log. Previously it traveled as an ordinary `brain`, and it was impossible to separate “it
    # scheduled it” from “said it would schedule it” without going to the DB — exactly the failure measured by the
    # `remember-and-remind-deadline` use case.
    "cron": "flash",
    # `tool_dropped` (V2-171, 2026-08-20): the turn DECIDED an action and the system could not read the
    # arguments — a truncated or malformed tool call. Family `flash` because the decision was the turn's; its
    # own kind because it is the opposite of every other one here: the others record something that HAPPENED,
    # and this records something that was supposed to and did not. It used to be a bare `continue` under a
    # `logger.warning`, which is why 48 lost escalations went unnoticed for three days — from a conversation
    # log it reads as the assistant having lied about work it never did.
    "tool_dropped": "flash",
    # ── Brain Workers (ON) — ASYNC work: worker sessions, the internal Chromium they open for browsing,
    # and backed/background processes that run outside the turn. The browser belongs HERE (2026-08-09): to the
    # operator, “open the browser” is not its own family; it is what a worker does when needed.
    "task": "worker", "worker_start": "worker", "navegador": "worker",
    "background": "worker", "backed": "worker",
    # `flow` = EXPLICIT flow closure (V2-090/observability): before this, "closed" was only ever INFERRED from the
    # absence of new events under its corr_id; this marks it for real when the worker that spawned it finishes.
    "flow": "worker",
    # ── Memory (ON)
    "memory": "memory",
    # ── Widgets (ON) — EVERY command against the canvas: show/close/move, data-ops (raise volume, maximize…),
    # aliases, and the operator’s own taps on the UI (`ui`). This record ties the “wrong widget”
    # wrong widget” to the PHRASE that requested it (each event carries the turn text + its trace chip).
    "widget": "widget", "ui": "widget",
    # ── Widgets, second batch: NATIVE surfaces that the brain opens like a card (`panel` = ChatWall tab via
    # `show_panel`; `secret` = vault modal). To the operator, “open the chat” and “open the
    # agenda” are the same gesture against the canvas, so they belong to the same family.
    "panel": "widget", "secret": "widget",
    # ── System / Code (OFF) — plumbing: voice transport, state, raw metrics, cluster, perf.
    # `metric` MOVED DOWN from the main view to here (2026-08-09, operator complaint): these are the RAW metrics from the
    # LiveKit plugin, and with streaming STT (Deepgram) the metric does NOT depend on anyone speaking — its
    # PeriodicCollector emits `STTMetrics: audio=5.00s` every 5 s while the microphone is open, PERPETUALLY.
    # PERPETUAL. It cluttered the thread with ~720 rows/hour carrying no signal (the PER-PHRASE latency, which does carry one, already appears
    # as `stt`/`tts`/`brain` with backend, model, and text). Same logic as the `VADMetrics` anti-flood from
    # 2026-07-12: continuous metric ≠ turn event. It remains persisted in the jsonl files.
    "metric": "system", "vad": "system", "cluster": "system", "perf": "system",
    "stt": "system", "tts": "system", "bot_speech": "system", "state": "system",
    "session": "system", "timing": "system", "notify": "system",
    # Health and infrastructure: `error`/`alert` (the viewer never hides them by category — see below),
    # `homeostasis` (the autonomous heartbeat, V2-070), `language` (the language was set), `client` (events the
    # browser reports through `/api/ui-event`).
    "error": "system", "alert": "system", "homeostasis": "system", "language": "system", "client": "system",
    "energy": "system",
    # `run` = the agent's GLOBAL switch (⏻ → nucleo/runstate.py): what was frozen and what continued. It goes in
    # `system` with `session`/`state`, its proper family: it is system state, not turn activity.
    "run": "system",
    # `music` is the music rail driven by FlashBrain (a sibling of `rail`), not a widget: the card that
    # card opened along the way already emits ITS own `widget` event.
    "music": "flash",
    # `interim` = live partial transcription. It never gets a `cat` (it goes through SSE and RETURNS early, see
    # `emit`), but it is mapped anyway so the inventory is COMPLETE and does not look like an omission.
    "interim": "flash",
}


# V2-255 — the HEAD also covers the MEMORY shown to the model. Measured on 2026-08-21 with the empty session:
# the recall block falls at character **2,896** of a 16,585-character prompt, just 104 characters from
# being left out—and in a real turn the cached state and recent conversation come BEFORE it, so it is always dropped.
# The prompt order is language → memory → recent → recall → directive → resources → “RIGHT NOW.”
#
# This matters because the shown memory determines behaviors such as V2-254 (a weather report for
# another city by choosing the city from an assignment), and because the harness proposed monitoring the ARTIFACT instead of the
# surface list: *no prompt contains the text of a background pill unless the request names it*.
# A verifier reading an artifact with truncated memory would say “clean” about a dirty prompt—which is tonight's
# very rule: **a ceiling is only dangerous if the reader accepts prefixes**.
_HEAD_CHARS, _TAIL_CHARS = 6000, 7000


def _prompt_excerpt(system: str) -> str:
    """Keep the HEAD and the TAIL of the composed prompt, not just the first 8 KB.

    V2-195, and it nearly cost a wrong diagnosis. This record exists to answer «what did the model see?» — its
    own docstring says so — and it kept `system[:8000]` of a prompt that measures ~19.000 characters. The
    static persona is the head and **`prompt.live_state()` is appended at the END**, so what got cut was
    exactly the half that changes every turn: the clock, the background tasks, the browser block, a wall, a
    pending confirmation. On 2026-08-20 that truncation made five turns of a measured run look as if the
    browser block had never reached the model — three steps into concluding that a night of fixes was
    invisible, when the only thing missing was the artefact.

    Head plus tail with the gap named, so nobody reads a hole as an absence. The head is worth keeping because
    the rules the model is under live there; the tail because that is where the FACTS of this turn are.
    """
    if len(system) <= _HEAD_CHARS + _TAIL_CHARS:
        return system
    dropped = len(system) - _HEAD_CHARS - _TAIL_CHARS
    return (f"{system[:_HEAD_CHARS]}\n\n… [{dropped} caracteres OMITIDOS del centro del prompt; "
            f"el estado vivo va al final y sí está abajo] …\n\n{system[-_TAIL_CHARS:]}")


def turn_detail(*, system: str, window: list | None = None, tools: list | None = None,
                user: str = "", decision: dict | None = None, extra: dict | None = None) -> None:
    """FORENSIC capture of ONE FlashBrain turn (V2-040, operator request 2026-07-15: “messages, tokens,
    prompts, conditions… for future evaluation and correction”). Records the composed SYSTEM PROMPT, the
    conversation WINDOW the model saw (roles+text), the offered TOOLS, and the turn's DECISION/conditions.

    It goes in the `system` category (OFF by default in the viewer → it does not flood the main view), but IS
    persisted to the file, so it remains available for later diagnosis (e.g. “why did it re-escalate during an
    ambient turn?” = inspect the window/prompt it saw). `ZAELAR_LOG_PROMPTS` gate (default ON); it can be disabled
    on sensitive machines. Never raises."""
    if (os.getenv("ZAELAR_LOG_PROMPTS", "1") or "1").strip().lower() in ("0", "false", "no", "off"):
        return
    try:
        win = [{"role": m.get("role"), "text": (m.get("content") or "")[:600]} for m in (window or [])]
        tool_names = [t.get("function", {}).get("name") if isinstance(t, dict) and "function" in t
                      else (t.get("name") if isinstance(t, dict) else str(t)) for t in (tools or [])]
        payload = {"cat": "system", "module": "flash", "func": "turn",
                   "system_prompt": _prompt_excerpt(system or ""), "system_chars": len(system or ""),
                   "window": win, "window_msgs": len(win), "tools": tool_names,
                   "user": (user or "")[:600], "decision": decision or {}}
        if extra:
            payload.update(extra)
        emit("perf", "🧾 turno (prompt+ventana+tools+decisión)", role="system", text=(user or "")[:120],
             extra=payload)
        # V2-053: SEMANTIC end-of-turn topic on the bus—the modularity connection point for programmatic
        # consumers (Susurro). turn_detail is the ONLY place BOTH paths close (voice provider and probe), so a
        # subscriber receives the complete turn without coupling to either one.
        try:
            import time as _time

            import bus
            from voice import trace as _trace
            bus.emit_sync("turn.completed", dict(payload, trace=_trace.current(), ts=_time.time()))
        except Exception:
            pass
    except Exception:
        pass


def perf(label: str, *, module: str = "", func: str = "", ms: float | None = None, text: str = ""):
    """Internal PERFORMANCE event (V2-037, `system` category, OFF by default in the viewer): instruments cycles,
    callbacks, calls to the model/DB/browser, and any load that could threaten real-time operation. Cheap: reuses
    `emit` (off-thread writing). `module`/`func` say WHERE it happens; `ms` gives the duration when applicable."""
    extra = {"cat": "system"}
    if module:
        extra["module"] = module
    if func:
        extra["func"] = func
    if ms is not None:
        extra["ms"] = round(float(ms), 1)
    return emit("perf", label, text=text, role="system", extra=extra)


# ── CONTENTION TRACKER (PHASE 3, 2026-07-14) ─────────────────────────────────────────────────────────────
# Heavy OFF-HOT-PATH loads that COULD contend with the voice turn (HEART mem_processor qwen, embeddings
# embeddinggemma, reranker cross-encoder). Each marks itself busy/free; the turn reads the snapshot when the LLM
# starts and attaches it to the `reply` event → we correlate: does TTFT rise while the HEART distills? TTFT is
# CLOUD → if it rises under LOCAL load, it is CPU/event-loop contention (not GPU), and more isolation is needed.
# Counter (not bool) in case several runs overlap. Cheap thread safety (GIL + atomic dict); best-effort.
import threading as _threading  # noqa: E402
_busy: dict[str, int] = {}
_busy_lock = _threading.Lock()


def mark_busy(what: str, on: bool) -> None:
    """Mark a heavy load as active/inactive (`what` = 'corazon'|'embed'|'rerank'|…). Best-effort."""
    try:
        with _busy_lock:
            _busy[what] = max(0, _busy.get(what, 0) + (1 if on else -1))
    except Exception:
        pass


class busy:
    """Context manager: `with busy('corazon'): …` marks the block as busy. Supports synchronous use; for async,
    simply wrap the work section (the contending heavy work is usually CPU/`to_thread`, not the await)."""
    def __init__(self, what: str):
        self.what = what

    def __enter__(self):
        mark_busy(self.what, True)
        return self

    def __exit__(self, *exc):
        mark_busy(self.what, False)
        return False


def busy_snapshot() -> dict:
    """Snapshot of which heavy loads are active NOW (to attach to the turn event), e.g. {'corazon': 1}."""
    try:
        with _busy_lock:
            return {k: v for k, v in _busy.items() if v > 0}
    except Exception:
        return {}


def now_ms() -> float:
    import time
    return time.time() * 1000.0


def subscribe():
    """SSE subscription for `GET /events`. RE-EXPRESSED over the Sistema Nervioso (bus/, V2-001): the observer
    is now just another subscriber of the bus `observer` topic. Returns a `bus.Subscription` that exposes
    `.get()`, so `voice_api.events()` stays byte-identical (it just awaits `.get()` and `unsubscribe()`s)."""
    from bus import sse as _bus_sse
    return _bus_sse.subscribe()


def unsubscribe(q):
    from bus import sse as _bus_sse
    _bus_sse.unsubscribe(q)


SESSIONS_DIR = os.path.join(LOG_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)
_events: list = []                 # in-memory ring of the CURRENT session (served by /debug)
# CLEANUP 2026-08-09: a SECOND concept of a session used to live here (`_session = {id, path}`, with an id in
# `%Y%m%d-%H%M%S` format), populated only by calling `reset_session()`… and NOBODY called it. Consequently, the
# documented per-session file (`.meshkore/logs/sessions/<id>.jsonl`) had not been written for some time because
# `path` was None and the write loop skipped it. There is now ONE session—the operator's work session in
# `observability/identity.py`—and the file is derived from ITS id: the documented function truly exists again,
# and the duplication is gone.
_session_file = {"sid": None, "path": None}
_seq = {"n": 0}
_dedup: dict = {}                  # (kind,label) -> last ts, to collapse high-frequency frame floods

# OFF-THREAD file persistence (V2-035, 2026-07-13): emit() runs in BOTH loops (uvicorn + LiveKit job thread).
# The 2 SYNCHRONOUS writes per event held the GIL in the uvicorn thread precisely when the browser
# (Playwright + PIL + DOM) generated bursts of events → they starved the TTS audio pump (jerky frames, `dur`
# 2-8s = CHOPPY voice). Now emit() only ENQUEUES (non-blocking); a dedicated writer drains in order (`_seq` already
# orders them). SSE remains synchronous (safely crosses loops through the bus). Fail-open: full queue → drop the line.
import queue as _queue
import threading as _threading

_write_q: "_queue.Queue" = _queue.Queue(maxsize=20000)


def _writer_loop():
    while True:
        item = _write_q.get()
        try:
            if item is None:
                continue
            path, line = item
            try:
                with open(path, "a") as f:
                    f.write(line)
            except Exception:
                pass
        finally:
            _write_q.task_done()   # enables Queue.join() — e.g. tests waiting for a drain before reading a file


_writer_thread = _threading.Thread(target=_writer_loop, name="observer-writer", daemon=True)
_writer_thread.start()


def emit(kind: str, label: str, text: str = "", role: str = "", extra: dict | None = None):
    """Record one debug event: in-memory ring + rolling buffer + per-session file + SSE subscribers.

    EVERYTHING that matters for debugging a voice turn flows through here — VAD/turn edges, transcripts,
    brain prompts/replies, latencies (ttft/ttfa), silences, TTS, errors. Query it all at GET /debug."""
    ts = now_ms()
    # EPHEMERAL: live partial transcript (interim). UI-only (subtitles/chat while speaking) — it is NOT persisted
    # or put in the ring (it would flood the log with every word). It only goes to SSE. Previously `DebugBus.partial`
    # (vl2 topic) kept this separately; with the observer unified, it is marked ephemeral here.
    if kind == "interim":
        ev = {"kind": "interim", "label": label, "text": text, "role": role}
        if extra:
            ev.update(extra)
        try:
            from bus import sse as _bus_sse
            _bus_sse.publish(ev)
        except Exception:
            pass
        return ev
    # Collapse floods: the same speech/turn frame is re-pushed in both pipeline directions by many processors.
    # Dedup identical (kind,label) within a short window for noisy kinds so /debug stays readable.
    if kind in ("user_speech", "bot_speech", "tts", "vad", "silence", "screenshot", "navegador", "widget"):
        # V2-039: for `widget`, the dedup key includes the id AND origin (`src`) — otherwise two different widgets
        # (or the SAME widget ordered by FlashBrain and by a worker) within <150ms collapsed into one event and the
        # AUDIT lost both the count and provenance. It still kills the real flood (the same identical action).
        if kind == "widget":
            _e = extra or {}
            k = (kind, label, str(_e.get("id") or ""), str(_e.get("src") or ""))
        else:
            k = (kind, label)
        if ts - _dedup.get(k, -1e9) < 150:
            return None
        _dedup[k] = ts
    if _t0["v"] is None:
        _t0["v"] = ts
    _seq["n"] += 1
    ev = {"i": _seq["n"], "t_ms": round(ts), "rel_ms": round(ts - _t0["v"]), "kind": kind,
          "label": label, "text": text, "role": role}
    if extra:
        ev.update(extra)
    # CATEGORY for the viewer filter (V2-037): groups kinds into a few families. The caller can force it with
    # extra={"cat": ...}; otherwise, it is derived from kind. System/Code (`system`) = internal/perf events, OFF by default.
    if "cat" not in ev:
        # No family → `other`: the viewer does NOT hide it by category (see `_CAT` note). An unclassified kind
        # is visible; classification decides where it lives, not whether it exists.
        ev["cat"] = _CAT.get(kind, "other")
    # VERSION STAMP (V2-074): each event carries the version of the code that generated it ('2.74+sha') → the timeline
    # reveals which version produced each line and distinguishes sessions/restarts. Constant at runtime (µs).
    if "ver" not in ev:
        try:
            import version as _v
            ev["ver"] = _v.short()
        except Exception:
            pass
    # TRACEABILITY (V2-044): stamps each event with the trace id of the stimulus that originated it (operator phrase,
    # cron, probe…) + the `span` (actor: worker:N / rail:X / web:tN). It is carried by the ContextVar in `voice/trace.py`
    # (it travels automatically through create_task/to_thread; cross-loop seams adopt it manually). Reading it takes
    # ns—the voice hot path pays nothing (V2-011). The caller can override it with extra={"trace": ...}.
    if "trace" not in ev:
        try:
            from voice import trace as _trace
            _tid = _trace.current()
            if _tid:
                ev["trace"] = _tid
                _sp = _trace.current_span()
                if _sp and "span" not in ev:
                    ev["span"] = _sp
        except Exception:
            pass
    stamp_identity(ev)
    _events.append(ev)
    if len(_events) > 5000:
        del _events[:1000]
    line = json.dumps(ev, ensure_ascii=False) + "\n"
    for path in (os.path.join(LOG_DIR, "timeline-latest.jsonl"), _session_path(ev.get("sid"))):
        if not path:
            continue
        try:
            _write_q.put_nowait((path, line))   # OFF-THREAD: does not block the voice/uvicorn thread (see above)
        except _queue.Full:
            pass
    # Fan out to SSE subscribers over the Sistema Nervioso (bus/, V2-001). emit() runs on BOTH loops (uvicorn
    # + the LiveKit job-thread); the bus's emit_sync crosses to each subscriber's loop safely (call_soon_
    # threadsafe) — this replaces the old put_nowait-across-loops the observer used to do by hand.
    try:
        from bus import sse as _bus_sse
        _bus_sse.publish(ev)
    except Exception:
        pass
    return ev


def debug_events(kind: str = "", limit: int = 0) -> list:
    """Current session's events (for the /debug endpoint). Optional kind filter + tail limit."""
    evs = [e for e in _events if (not kind or e.get("kind") == kind)]
    return evs[-limit:] if limit else evs


def stamp_identity(ev: dict) -> dict:
    """WHO and WHEN (2026-08-09). The event already said WHAT happened (`kind`), from which PIECE (`cat`), and
    from which FLOW (`trace` = correlation id). It lacked the two axes used to analyze REAL usage: the installation
    (`uid`) and work session (`sid`). These are reads from a cached dict (ns)—the voice hot path (V2-011) pays
    nothing. `sid` opens a session automatically on the first event: we prefer an auto-opened session over an
    event without a session, which is data that cannot be reconstructed later.

    It lives in its OWN function because `emit()` is not the only gateway to the stream: some events are published
    manually to the `observer` topic (the loop's `pulse` heartbeat, the `memory.updated` bridge) and skipped the
    stamp—50 of 66 rows from the first startup had no session. `bus/sse.py::publish` applies it too, and that really
    is the SINGLE gateway. Idempotent: applying it twice overwrites nothing."""
    # The FAMILY too: a manually constructed dict does not pass through `emit()`'s derivation and reached the
    # viewer without `cat`, meaning the “Unclassified” row—which is exactly what the operator saw with memory events.
    if "cat" not in ev:
        ev["cat"] = _CAT.get(str(ev.get("kind") or ""), "other")
    # Idle timeout (2026-08-13): only REAL activity (not `system`/`pulse` background noise) counts toward the
    # session clock — runs BEFORE resolving `sid` so that, if a rollover happens, this very event already gets
    # stamped with the NEW session. See `observability/identity.py::note_real_activity`.
    try:
        if ev.get("cat") not in ("system", "pulse"):
            from observability import identity as _ident
            _ident.note_real_activity()
    except Exception:
        pass
    if "uid" in ev and "sid" in ev:
        return ev
    try:
        from observability import identity as _ident
        ev.setdefault("uid", _ident.user_id())
        stopped = False
        try:
            from nucleo import runstate as _runstate
            stopped = _runstate.stopped()
        except Exception:
            pass
        if ev.get("cat") in ("system", "pulse") or stopped:
            # Background noise NEVER fabricates a session (2026-08-15, real finding: closing a session emits
            # its own "end" event, category `system` — with the `setdefault` below that REOPENED a new session
            # in the act of closing the previous one, and the same with any ⏻ event (`run`/stop/start) fired
            # while the agent is stopped. `session_info()` ONLY READS (never opens); with none open, the event
            # goes out with no `sid` instead of lying with a freshly-invented one.
            #
            # 2026-08-16, real finding #2: the `cat` check alone wasn't enough — reloading the browser tab with
            # the agent globally STOPPED (⏻ off, `runstate.stopped()`) still fired ordinary `widget`/`ui` state
            # transitions (cat="widget", not system/pulse), and THOSE self-opened a brand-new "live" session
            # via `session_id()` below, immediately re-appearing in the backoffice master as "EN CURSO" the
            # instant the page was refreshed. “Stopped means stopped” (V2-092) has to mean nothing self-opens a
            # session while stopped, independent of what category the triggering event happens to carry.
            ev.setdefault("sid", _ident.session_info().get("session_id") or "")
        else:
            ev.setdefault("sid", _ident.session_id())
    except Exception:
        pass
    return ev


def _session_path(sid) -> str:
    """File for the current work session. Memoized to avoid rebuilding the path for every event (the voice hot
    path passes through here); when the session changes, it changes automatically."""
    sid = str(sid or "")
    if not sid:
        return ""
    if _session_file["sid"] != sid:
        _session_file["sid"] = sid
        _session_file["path"] = os.path.join(SESSIONS_DIR, f"{sid}.jsonl")
    return _session_file["path"]


def session_info() -> dict:
    """Session state for `/api/debug`. The SOURCE is `observability.identity` — this module no longer maintains
    its own session accounting (see the `_session_file` note)."""
    sid = ""
    try:
        from observability import identity as _ident
        sid = _ident.session_id()
    except Exception:
        pass
    return {"session_id": sid, "events": len(_events), "file": _session_path(sid), "t0_ms": _t0["v"]}


def clear_log():
    _t0["v"] = None
    _events.clear()
    _seq["n"] = 0
    _dedup.clear()          # (kind,label)→last ts: without clearing it, the first event of a new session could
    #                         collapse against one from the previous session and NOT appear (too-clean start)
    try:
        open(os.path.join(LOG_DIR, "timeline-latest.jsonl"), "w").close()
    except Exception:
        pass


def rotate_session(reason: str = "reset") -> dict:
    """Close the current work session and open a NEW one with observability reset to zero. Return the new
    session's information (`{session_id, started_ms, source, user_id}`).

    This is what must happen when “Reset” is pressed (operator request, 2026-08-10): a deliberate reset means
    “stop the agent and start it again”—same rules, same memory, but **we start with a blank slate**. Previously,
    reset emptied the log but did NOT rotate the id (nobody called `begin_session(force=True)`), so subsequent
    events remained attached to the old session: the durable record mixed work from before and after a clean
    break in the same session, and the observability column started “empty” but carried the identity of something
    that no longer existed. A new id is what gives that clean break meaning.

    ORDER, which matters:
      1. `end_session`—the closing event is stamped with the OLD sid and goes into that session's file, where it
         belongs (it preserves the record of when and why it ended).
      2. `clear_log`—the in-RAM ring, sequence counter, and `timeline-latest.jsonl` (the “what is happening now”
         view) are emptied; PER-SESSION files are untouched: they are the history.
      3. `begin_session(force=True)`—new id. `force` is essential: `begin_session` deliberately reuses the open
         session so reconnection after a network hiccup is not counted as a new session.
      4. Traces start numbering again from T1.

    Fail-open: if identity is unavailable, at least clear the log (a partial reset is better than a reset that
    crashes)."""
    trace_reset = None
    try:
        from voice import trace as _trace
        trace_reset = _trace.reset_seq
    except Exception:
        pass
    try:
        from observability import identity as _ident
    except Exception:
        clear_log()
        if trace_reset:
            trace_reset()
        return {}
    try:
        _ident.end_session(reason)
    except Exception:
        pass
    clear_log()
    _session_file["sid"] = None       # the memoized path pointed to the file of the session just closed
    _session_file["path"] = None
    if trace_reset:
        trace_reset()
    try:
        # A reset in front of a STOPPED agent (⏻ off) opens NOTHING — `begin_session` returns `{}` and this
        # returns `{}` too, so the RESET event announces no session rather than a fresh one that would then sit
        # "EN CURSO" in the master with the agent visibly off (measured 2026-08-31; see `identity.begin_session`).
        # The blank slate still happens: the log above was already cleared. The next session is born when the
        # operator presses ⏻ ON, which is what “we start with a blank slate” means with a stopped agent.
        if not _ident.begin_session(source=reason, force=True):
            return {}
        # `session_info()`, not what `begin_session` returns: the latter has the internal `id` key, and callers of
        # this (the reset response, the RESET event) use the public `session_id` vocabulary.
        return _ident.session_info()
    except Exception:
        return {}


# NOTE (INI-012): the Pipecat frame observers (TimelineObserver, AudioProbe) that used to live here were
# removed with the Pipecat engine. The pure SSE/event machinery above is engine-agnostic — it's what the
# LiveKit engine, widgets, connectors, brain and voice_api all consume. Turn/latency + mic-arrival
# instrumentation now lives in the LiveKit pipeline (voice/engine/pipeline/instrument.py), which calls emit()
# with the same kinds ("timing", "transcript", "llm", "bot_speech", "audio", …) so /debug is unchanged.


def _removed_pipecat_observers():  # pragma: no cover
    raise NotImplementedError(
        "TimelineObserver/AudioProbe were removed with Pipecat (INI-012); "
        "instrumentation lives in voice/engine/pipeline/instrument.py"
    )
