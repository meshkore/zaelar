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
    # rastro distinguible en el registro. Antes viajaba como un `brain` cualquiera y era imposible separar «lo
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
    # `metric` BAJÓ de la vista principal a aquí (2026-08-09, queja del operador): son las métricas CRUDAS del
    # LiveKit plugin, and with streaming STT (Deepgram) the metric does NOT depend on anyone speaking — its
    # PeriodicCollector emits `STTMetrics: audio=5.00s` every 5 s while the microphone is open, PERPETUALLY.
    # PERPETUA. Ensuciaba el hilo con ~720 filas/hora sin señal (la latencia POR FRASE, que sí la tiene, ya sale
    # as `stt`/`tts`/`brain` with backend, model, and text). Same logic as the `VADMetrics` anti-flood from
    # 2026-07-12: métrica continua ≠ evento del turno. Sigue persistida en los jsonl.
    "metric": "system", "vad": "system", "cluster": "system", "perf": "system",
    "stt": "system", "tts": "system", "bot_speech": "system", "state": "system",
    "session": "system", "timing": "system", "notify": "system",
    # Health and infrastructure: `error`/`alert` (the viewer never hides them by category — see below),
    # `homeostasis` (el latido autónomo, V2-070), `language` (el idioma quedó fijado), `client` (eventos que
    # reporta el navegador por `/api/ui-event`).
    "error": "system", "alert": "system", "homeostasis": "system", "language": "system", "client": "system",
    "energy": "system",
    # `run` = el interruptor GLOBAL del agente (⏻ → nucleo/runstate.py): qué se congeló y qué continuó. Va en
    # `system` con `session`/`state`, que es su familia: es estado del sistema, no actividad de un turno.
    "run": "system",
    # `music` is the music rail driven by FlashBrain (a sibling of `rail`), not a widget: the card that
    # se abre por el camino ya emite SU propio evento `widget`.
    "music": "flash",
    # `interim` = live partial transcription. It never gets a `cat` (it goes through SSE and RETURNS early, see
    # `emit`), pero se mapea igual para que el inventario esté COMPLETO y no parezca un olvido.
    "interim": "flash",
}


# V2-255 — the HEAD also covers the MEMORY shown to the model. Measured on 2026-08-21 with the empty session:
# the recall block falls at character **2,896** of a 16,585-character prompt, just 104 characters from
# quedarse fuera — y en un turno real van DELANTE el estado cacheado y la conversación reciente, así que se cae
# siempre. El orden del prompt es lang → memoria → reciente → recall → directiva → recursos → «AHORA MISMO».
#
# This matters because the shown memory determines behaviors such as V2-254 (a weather report for
# otra ciudad eligiendo la ciudad de un encargo), y porque el arnés propuso vigilar el ARTEFACTO en vez de la
# surface list: *no prompt contains the text of a background pill unless the request names it*.
# Un verificador que lea un artefacto con la memoria recortada diría «limpio» sobre un prompt sucio — que es la
# regla de esta misma noche: **un techo solo es peligroso si el lector acepta prefijos**.
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
    prompts, condiciones… para evaluar y corregir a futuro»). Registra el PROMPT DE SISTEMA compuesto, la VENTANA
    conversacional que vio el modelo (roles+texto), las TOOLS ofrecidas y la DECISIÓN/condiciones del turno.

    Va en categoría `system` (OFF por defecto en el visor → no floodea la vista principal) pero SÍ se persiste al
    fichero, así queda para diagnóstico posterior (p.ej. «¿por qué re-escaló en un turno ambiente?» = mirar qué
    ventana/prompt vio). Gate `ZAELAR_LOG_PROMPTS` (def ON); se puede apagar en máquinas sensibles. Nunca lanza."""
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
        # V2-053: topic SEMÁNTICO de fin de turno en el bus — punto de conexión de modularidad para consumidores
        # programáticos (Susurro). turn_detail es el ÚNICO sitio que cierran AMBOS caminos (provider de voz y
        # probe), así un suscriptor recibe el turno completo sin acoplarse a ninguno de los dos.
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
    callbacks, llamadas a modelo/DB/navegador y cualquier carga que pueda amenazar el tiempo real. Barato: reusa
    `emit` (escritura off-thread). `module`/`func` dicen DÓNDE sucede; `ms` la duración cuando aplica."""
    extra = {"cat": "system"}
    if module:
        extra["module"] = module
    if func:
        extra["func"] = func
    if ms is not None:
        extra["ms"] = round(float(ms), 1)
    return emit("perf", label, text=text, role="system", extra=extra)


# ── CONTENTION TRACKER (PHASE 3, 2026-07-14) ─────────────────────────────────────────────────────────────
# Cargas pesadas OFF-HOT-PATH que PODRÍAN contender con el turno de voz (CORAZÓN mem_processor qwen, embeddings
# embeddinggemma, reranker cross-encoder). Cada una marca ocupado/libre; el turno lee la foto al empezar el LLM y
# la adjunta al evento `reply` → correlacionamos: ¿sube el TTFT cuando el CORAZÓN destila? El TTFT es CLOUD → si
# sube con carga LOCAL, es contención de CPU/event-loop (no de GPU), y hay que aislar más. Contador (no bool) por
# si hay varias corridas a la vez. Thread-safe barato (GIL + dict atómico); best-effort.
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
# LIMPIEZA 2026-08-09: aquí vivía un SEGUNDO concepto de sesión (`_session = {id, path}`, id con formato
# `%Y%m%d-%H%M%S`) que solo se rellenaba llamando a `reset_session()`… y NADIE lo llamaba. Consecuencia: el
# fichero por sesión que documentábamos (`.meshkore/logs/sessions/<id>.jsonl`) llevaba tiempo sin escribirse
# nunca, porque `path` era None y el bucle de escritura lo saltaba. Ahora hay UNA sola sesión —la de trabajo del
# operador, `observability/identity.py`— y el fichero se deriva de SU id: la función documentada vuelve a
# existir de verdad y desaparece la duplicidad.
_session_file = {"sid": None, "path": None}
_seq = {"n": 0}
_dedup: dict = {}                  # (kind,label) -> last ts, to collapse high-frequency frame floods

# Persistencia a fichero OFF-THREAD (V2-035, 2026-07-13): emit() corre en AMBOS loops (uvicorn + job-thread de
# LiveKit). Las 2 escrituras SÍNCRONAS por evento retenían el GIL en el hilo de uvicorn justo cuando el navegador
# (Playwright + PIL + DOM) genera ráfagas de eventos → hambreaban el pump de audio del TTS (frames a tirones, `dur`
# 2-8s = voz ENTRECORTADA). Ahora emit() solo ENCOLA (no bloquea); un writer dedicado drena en orden (el `_seq` ya
# ordena). El SSE sigue yendo síncrono (cruza loops seguro por el bus). Fail-open: cola llena → se descarta la línea.
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
    # extra={"cat": ...}; si no, se deriva del kind. System/Code (`system`) = eventos internos/perf, OFF por defecto.
    if "cat" not in ev:
        # No family → `other`: the viewer does NOT hide it by category (see `_CAT` note). An unclassified kind
        # is visible; classification decides where it lives, not whether it exists.
        ev["cat"] = _CAT.get(kind, "other")
    # VERSION STAMP (V2-074): each event carries the version of the code that generated it ('2.74+sha') → the timeline
    # se ve qué versión produjo cada línea y se distinguen sesiones/reinicios. Constante en runtime (µs).
    if "ver" not in ev:
        try:
            import version as _v
            ev["ver"] = _v.short()
        except Exception:
            pass
    # TRACEABILITY (V2-044): stamps each event with the trace id of the stimulus that originated it (operator phrase,
    # cron, probe…) + el `span` (actor: worker:N / rail:X / web:tN). Lo lleva el ContextVar de `voice/trace.py`
    # (viaja solo por create_task/to_thread; las costuras cross-loop adoptan a mano). Leerlo son ns — el hot path
    # de voz no paga nada (V2-011). El caller puede forzarlo con extra={"trace": ...}.
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
            _write_q.put_nowait((path, line))   # OFF-THREAD: no bloquea el hilo de voz/uvicorn (ver arriba)
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
    """QUIÉN y CUÁNDO (2026-08-09). El evento ya decía QUÉ pasó (`kind`), de qué PIEZA (`cat`) y de qué FLUJO
    (`trace` = correlation id). Le faltaban los dos ejes con los que se analiza el uso REAL: la instalación
    (`uid`) y la sesión de trabajo (`sid`). Son lecturas de un dict cacheado (ns) — el hot path de voz (V2-011)
    no paga nada. `sid` abre sesión sola en el primer evento: preferimos una sesión auto-abierta a un evento sin
    sesión, que es un dato que ya no se puede reconstruir después.

    Vive en una función PROPIA porque `emit()` no es la única puerta al stream: hay eventos que se publican a
    mano al topic `observer` (el latido `pulse` del loop, el puente de `memory.updated`) y se saltaban el sello
    —50 de 66 filas del primer arranque salieron sin sesión—. `bus/sse.py::publish` lo aplica también, que sí es
    la puerta ÚNICA. Idempotente: pasar dos veces no pisa nada."""
    # La FAMILIA también: un dict construido a mano no pasa por la derivación de `emit()` y llegaba al visor sin
    # `cat`, o sea a la fila «Sin clasificar» — que es justo lo que el operador vio con los eventos de memoria.
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
            # instant the page was refreshed. "Parar es parar" (V2-092) has to mean nothing self-opens a
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
    """Cierra la sesión de trabajo en curso y abre una NUEVA, con la observabilidad a cero. Devuelve la info de la
    sesión nueva (`{session_id, started_ms, source, user_id}`).

    Es lo que tiene que pasar al pulsar «Reset» (petición del operador, 2026-08-10): un reset deliberado es «para
    el agente y vuélvelo a arrancar» — mismas reglas, misma memoria, pero **empezamos en blanco**. Antes el reset
    vaciaba el log y NO rotaba el id (`begin_session(force=True)` no lo llamaba nadie), así que los eventos de
    después seguían colgando de la sesión vieja: el registro durable mezclaba en una misma sesión el trabajo de
    antes y el de después de un borrón, y la columna de observabilidad arrancaba «vacía» pero con la identidad de
    algo que ya no existía. Un id nuevo es lo que hace que ese borrón signifique algo.

    ORDEN, que importa:
      1. `end_session` — el evento de cierre se sella con el sid VIEJO y cae en el fichero de esa sesión, que es su
         sitio (ahí queda el registro de cuándo y por qué acabó).
      2. `clear_log` — se vacían el anillo en RAM, el contador de secuencia y el `timeline-latest.jsonl` (la vista
         «lo que está pasando ahora»); los ficheros POR SESIÓN no se tocan: son el histórico.
      3. `begin_session(force=True)` — id nuevo. El `force` es imprescindible: `begin_session` reutiliza a
         propósito la sesión abierta para que una reconexión por un bache de red no se cuente como sesión nueva.
      4. Los traces vuelven a numerar desde T1.

    Fail-open: si la identidad no está disponible, al menos se limpia el log (mejor un reset a medias que un reset
    que revienta)."""
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
        # operator presses ⏻ ON, which is what "empezamos en blanco" means with a stopped agent.
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
