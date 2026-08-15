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

# CATEGORÍAS del visor de observabilidad — las familias del filtro superior.
#
# REDISEÑO 2026-08-09 (petición del operador): fuera «Principal», que era un cajón de sastre donde convivían la
# conversación, los widgets, las tareas y la plomería del transporte. Las familias son ahora las PIEZAS REALES del
# sistema, que es como el operador razona cuando depura: **FlashBrain · Brain Workers · Memoria · Widgets ·
# Sistema/Código · Pulso**. ON por defecto las cuatro primeras; `system` y `pulse` OFF (internos y ruidosos).
#
# Un `kind` NO mapeado NO cae en ninguna familia — y el visor lo trata como SIEMPRE VISIBLE (nunca se oculta por
# el eje de categoría). Es deliberado: una capacidad nueva que estrene su propio kind debe VERSE hasta que alguien
# la clasifique aquí; el silencio por omisión es la peor forma de perder señal. Lo mismo vale para `error`/`alert`.
_CAT = {
    # ── FlashBrain (ON) — el TURNO: qué se dijo, qué decidió el orquestador, qué buscó, qué auditó Susurro.
    "brain": "flash", "transcript": "flash", "ambient": "flash", "search": "flash",
    "susurro": "flash", "rail": "flash", "trace": "flash",
    # ── Brain Workers (ON) — el trabajo ASYNC: sesiones de worker, el Chromium interno que abren para navegar,
    # y los procesos backed/background que corren fuera del turno. El navegador va AQUÍ (2026-08-09): para el
    # operador «abrir el navegador» no es una familia propia, es lo que hace un worker cuando le hace falta.
    "task": "worker", "worker_start": "worker", "navegador": "worker",
    "background": "worker", "backed": "worker",
    # `flow` = EXPLICIT flow closure (V2-090/observability): before this, "closed" was only ever INFERRED from the
    # absence of new events under its corr_id; this marks it for real when the worker that spawned it finishes.
    "flow": "worker",
    # ── Memoria (ON)
    "memory": "memory",
    # ── Widgets (ON) — TODA orden contra el canvas: show/close/move, data-ops (subir volumen, maximizar…),
    # alias, y los taps del propio operador sobre la UI (`ui`). Es el registro que permite atar «widget
    # equivocado» con la FRASE que lo pidió (cada evento lleva el texto del turno + su chip de trace).
    "widget": "widget", "ui": "widget",
    # ── Widgets, 2ª tanda: superficies NATIVAS que el cerebro abre igual que una tarjeta (`panel` = pestaña del
    # ChatWall vía `show_panel`; `secret` = modal de la bóveda). Para el operador «abrir el chat» y «abrir la
    # agenda» son el mismo gesto contra el canvas, así que viven en la misma familia.
    "panel": "widget", "secret": "widget",
    # ── Sistema / Código (OFF) — plomería: transporte de voz, estado, métricas crudas, cluster, perf.
    # `metric` BAJÓ de la vista principal a aquí (2026-08-09, queja del operador): son las métricas CRUDAS del
    # plugin de LiveKit, y con un STT de streaming (Deepgram) la métrica NO depende de que alguien hable — su
    # PeriodicCollector suelta `STTMetrics: audio=5.00s` cada 5 s mientras el micro esté abierto, de forma
    # PERPETUA. Ensuciaba el hilo con ~720 filas/hora sin señal (la latencia POR FRASE, que sí la tiene, ya sale
    # como `stt`/`tts`/`brain` con backend, modelo y texto). Misma lógica que el anti-flood de `VADMetrics` del
    # 2026-07-12: métrica continua ≠ evento del turno. Sigue persistida en los jsonl.
    "metric": "system", "vad": "system", "cluster": "system", "perf": "system",
    "stt": "system", "tts": "system", "bot_speech": "system", "state": "system",
    "session": "system", "timing": "system", "notify": "system",
    # Salud e infraestructura: `error`/`alert` (el visor NO los oculta nunca por categoría — ver abajo),
    # `homeostasis` (el latido autónomo, V2-070), `language` (el idioma quedó fijado), `client` (eventos que
    # reporta el navegador por `/api/ui-event`).
    "error": "system", "alert": "system", "homeostasis": "system", "language": "system", "client": "system",
    "energy": "system",
    # `run` = el interruptor GLOBAL del agente (⏻ → nucleo/runstate.py): qué se congeló y qué continuó. Va en
    # `system` con `session`/`state`, que es su familia: es estado del sistema, no actividad de un turno.
    "run": "system",
    # `music` es el rail de música conducido por el FlashBrain (hermano de `rail`), no un widget: la tarjeta que
    # se abre por el camino ya emite SU propio evento `widget`.
    "music": "flash",
    # `interim` = transcripción parcial en vivo. Nunca llega a llevar `cat` (sale por SSE y RETORNA antes, ver
    # `emit`), pero se mapea igual para que el inventario esté COMPLETO y no parezca un olvido.
    "interim": "flash",
}


def turn_detail(*, system: str, window: list | None = None, tools: list | None = None,
                user: str = "", decision: dict | None = None, extra: dict | None = None) -> None:
    """Captura FORENSE de UN turno del FlashBrain (V2-040, pedido del operador 2026-07-15: «mensajes, tokens,
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
                   "system_prompt": (system or "")[:8000], "system_chars": len(system or ""),
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
    """Evento de RENDIMIENTO / interno (V2-037, categoría `system`, OFF por defecto en el visor): instrumenta ciclos,
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


# ── RASTREADOR DE CONTENCIÓN (FASE 3, 2026-07-14) ─────────────────────────────────────────────────────────────
# Cargas pesadas OFF-HOT-PATH que PODRÍAN contender con el turno de voz (CORAZÓN mem_processor qwen, embeddings
# embeddinggemma, reranker cross-encoder). Cada una marca ocupado/libre; el turno lee la foto al empezar el LLM y
# la adjunta al evento `reply` → correlacionamos: ¿sube el TTFT cuando el CORAZÓN destila? El TTFT es CLOUD → si
# sube con carga LOCAL, es contención de CPU/event-loop (no de GPU), y hay que aislar más. Contador (no bool) por
# si hay varias corridas a la vez. Thread-safe barato (GIL + dict atómico); best-effort.
import threading as _threading  # noqa: E402
_busy: dict[str, int] = {}
_busy_lock = _threading.Lock()


def mark_busy(what: str, on: bool) -> None:
    """Marca una carga pesada como activa/inactiva (`what` = 'corazon'|'embed'|'rerank'|…). Best-effort."""
    try:
        with _busy_lock:
            _busy[what] = max(0, _busy.get(what, 0) + (1 if on else -1))
    except Exception:
        pass


class busy:
    """Context manager: `with busy('corazon'): …` marca ocupado durante el bloque. Soporta uso síncrono; para async
    basta envolver la sección de trabajo (el trabajo pesado que contende suele ser CPU/`to_thread`, no el await)."""
    def __init__(self, what: str):
        self.what = what

    def __enter__(self):
        mark_busy(self.what, True)
        return self

    def __exit__(self, *exc):
        mark_busy(self.what, False)
        return False


def busy_snapshot() -> dict:
    """Foto de qué cargas pesadas están activas AHORA (para adjuntar al evento del turno). p. ej. {'corazon':1}."""
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
    # EFÍMEROS: transcript parcial en vivo (interim). Es UI-only (subtítulos/chat mientras hablas) — NO se
    # persiste ni ocupa el anillo (floodearía el log con cada palabra). Solo va al SSE. Antes esto lo mantenía
    # aparte `DebugBus.partial` (topic vl2); al unificar el registro en el observador, se marca aquí como efímero.
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
        # V2-039: para `widget` la clave de dedup incluye el id Y el origen (`src`) — si no, dos widgets distintos
        # (o el MISMO widget ordenado por el FlashBrain y por un worker) en <150ms colapsaban a un solo evento y la
        # AUDITORÍA perdía tanto la cuenta como la procedencia. Sigue matando el flood real (misma acción idéntica).
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
    # CATEGORÍA para el filtro del visor (V2-037): agrupa los kinds en pocas familias. El caller puede forzarla con
    # extra={"cat": ...}; si no, se deriva del kind. System/Code (`system`) = eventos internos/perf, OFF por defecto.
    if "cat" not in ev:
        # Sin familia → `other`: el visor NO lo oculta por categoría (ver la nota de `_CAT`). Un kind sin clasificar
        # se ve; clasificarlo es lo que decide dónde vive, no lo que decide si existe.
        ev["cat"] = _CAT.get(kind, "other")
    # SELLO DE VERSIÓN (V2-074): cada evento lleva la versión del código que lo generó ('2.74+sha') → en el timeline
    # se ve qué versión produjo cada línea y se distinguen sesiones/reinicios. Constante en runtime (µs).
    if "ver" not in ev:
        try:
            import version as _v
            ev["ver"] = _v.short()
        except Exception:
            pass
    # TRAZABILIDAD (V2-044): sella cada evento con el trace id del estímulo que lo originó (frase del operador,
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
        ev.setdefault("sid", _ident.session_id())
    except Exception:
        pass
    return ev


def _session_path(sid) -> str:
    """Fichero de la sesión de trabajo en curso. Se memoiza para no recomponer la ruta en cada evento (el hot
    path de voz pasa por aquí); al cambiar de sesión, cambia solo."""
    sid = str(sid or "")
    if not sid:
        return ""
    if _session_file["sid"] != sid:
        _session_file["sid"] = sid
        _session_file["path"] = os.path.join(SESSIONS_DIR, f"{sid}.jsonl")
    return _session_file["path"]


def session_info() -> dict:
    """Estado de la sesión para `/api/debug`. La FUENTE es `observability.identity` — este módulo ya no lleva
    su propia contabilidad de sesiones (ver la nota de `_session_file`)."""
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
    _dedup.clear()          # (kind,label)→último ts: sin vaciarlo, el 1er evento de una sesión nueva puede
    #                         colapsarse contra uno de la sesión anterior y NO aparecer (arranca en blanco de más)
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
    _session_file["sid"] = None       # la ruta memoizada apuntaba al fichero de la sesión que acaba de cerrar
    _session_file["path"] = None
    if trace_reset:
        trace_reset()
    try:
        _ident.begin_session(source=reason, force=True)
        # `session_info()` y no lo que devuelve `begin_session`: esa lleva la clave interna `id`, y quien llama a
        # esto (la respuesta del reset, el evento RESET) habla el vocabulario público `session_id`.
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
