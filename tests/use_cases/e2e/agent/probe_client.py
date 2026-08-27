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


def say(text: str, session: str, *, execute: bool = True, ingest: bool = False, timeout: float = 90.0) -> dict:
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
    """Qué recuerda el motor sobre algo. `POST /api/memory/recall` NO pide token de tarea (a diferencia de
    `/api/memory/remember`, que es solo para los puentes de los workers), así que el arnés puede LEER la
    memoria del sandbox sin inventarse credenciales.

    Existe para una cosa concreta: comprobar que una siembra de preferencias aterrizó ANTES de juzgar al
    agente por no recordarla. Sin esta comprobación, un caso de «infiere lo que me gusta» mediría el
    destilador de memoria y lo reportaría como que el agente no razona.
    """
    try:
        r = _post("/api/memory/recall", {"query": query, "k": k}, timeout=30.0)
    except Exception:
        return None       # V2-400: una petición caída no es una memoria vacía — «no pude preguntar»
    if isinstance(r, dict):
        return r.get("results") or r.get("items") or r.get("memories") or []
    return r if isinstance(r, list) else []


def hard_reset() -> dict:
    """Deja el motor LIMPIO entre casos: mata el trabajo de fondo, cierra el canvas y rota la sesión.

    Existe por una contaminación MEDIDA (2026-08-19): una tanda comparte UN sandbox, y en
    `find-theatre-tickets__es` el juez vio que «el sistema intentaba reservar un restaurante irrelevante» —
    era la tarea viva del caso ANTERIOR (`restaurant-tonight-madrid`) del mismo lote. O sea que el caso no se
    midió a sí mismo: se midió arrastrando el trabajo del vecino. `reset(session)` no vale para esto, solo
    limpia la ventana conversacional; los workers, las tareas y el canvas siguen ahí.

    NO borra memoria a propósito (`/reset/hard`, no `/api/reset/full` con `wipe_memory`): borrarla exige matar
    el proceso y, además, los casos de descubrimiento SIEMBRAN preferencias que tienen que sobrevivir a esto —
    se siembran después, ya dentro del caso.
    """
    return _post("/reset/hard", {}, timeout=60.0)


def canvas_items() -> list:
    """Las tarjetas que el SERVIDOR tiene guardadas del escritorio (`GET /api/canvas/layout`).

    NO es lo mismo que lo que se ve en pantalla —el navegador es el dueño del canvas (V2-124)— pero es lo
    único observable desde aquí, y una tarjeta que sigue en esta lista reaparece en cuanto alguien recargue.
    """
    data = _get("/api/canvas/layout")
    return list((data or {}).get("items") or []) if isinstance(data, dict) else []


def settle_after_reset(*, budget_s: float = 25.0, poll_s: float = 1.0) -> dict:
    """Espera a que el motor quede REALMENTE limpio y devuelve lo que encontró, se haya limpiado o no.

    Sustituye a un `time.sleep(2.0)` seguido de imprimir «motor reseteado (sin trabajo ni canvas anterior)»
    pasara lo que pasara — una afirmación que nadie comprobaba, en el sitio donde el operador la lee para
    fiarse de que el caso siguiente se mide solo. Dos segundos era además un número inventado: en la tanda
    del 2026-08-24 un worker de investigación seguía escribiendo en la hoja del caso ANTERIOR casi un
    segundo después del reset, y su tarjeta se quedaba en pantalla.

    El presupuesto es un TOPE, no una espera: en cuanto las dos señales están a cero se vuelve. Y si se
    agota, se vuelve igual **diciendo qué quedó vivo** — parar la tanda porque un worker tarda en morir
    costaría más que medir un caso con una advertencia encima.
    """
    import time as _t

    def _still_working() -> list[dict]:
        # El filtro de estado se aplica AQUÍ y no se le delega al motor. `active_sessions()` estuvo sin
        # filtrar hasta V2-115 —y ese hueco pintó como «en curso» tareas ya terminadas—, así que esperar a
        # que la lista se vacíe sin mirar el estado ataría el arranque del caso siguiente a un registro que
        # ya ha fallado una vez de esa forma exacta.
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
    """Qué widgets están PRODUCIENDO ahora mismo (audio, vídeo, un proceso vivo), según el propio motor.

    Se pregunta, no se deduce: `active_when` lo evalúa `widgets/producers.py` contra el `view_data()` del
    widget, y reimplementarlo aquí sería una segunda verdad que puede divergir de la que usa el producto.
    `None` cuando NO SE PUDO PREGUNTAR, lista (quizá vacía) cuando el motor contestó. La distinción es la
    que V2-395 le enseñó al juez, y devolver `[]` ante un motor inalcanzable la resolvía justo por la rama
    que acusa al producto. Nunca lanza: es un dato del informe, no un paso del turno.
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
