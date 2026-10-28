#
# tasks.py — browser TASK REGISTRY (multi-task phase). Each task = one objective driven in ITS OWN tab, with
# a live feed (events), structured results, and an optional question for the operator.
#
# Split (decided with the operator on 2026-07-08): the ORCHESTRATOR (fast layer, brains/duo) owns the FLEET — creates
# tasks, routes operator answers, and knows what is in progress / done / waiting; Hermes plans/analyzes each task;
# owner.py EXECUTES it in its tab and writes progress here; data.py serves per-task state to the canvas card.
# 1:1 mapping: card(canvas) ↔ tab(Chrome) ↔ task(this registry).
#
# Intentionally in-memory: a task lives while its tab lives; a restart kills tabs, so persisting them makes no sense.
# Same process for owner/data/duo → they all share this module (one dict).
#
import itertools
import threading
import time

# F4 (2026-08-23): the set-comparison arithmetic comes from THE yardstick module. `nucleo.matching` is pure
# stdlib (no engine import, no cycle): this file keeps its own stemming and clarification contract — those are
# browser-specific and measured — but the primitive underneath is the shared one, so the two judges of «same
# errand?» can no longer drift apart silently (they did: 2026-08-21, three workers driving one tab).
from nucleo import matching

WID = "navegador"
_lock = threading.RLock()
_tasks: dict[str, dict] = {}          # task_id -> state
# Task ids come from the process-identity owner (F5). Per-process is CORRECT here, unlike the results sheet
# (32c7dc6): this registry is RAM, a task dies with its process, and its canvas card is ephemeral by design —
# nothing durable is keyed on `tN`, so a repeated id after a restart has nothing left to collide with.
from nucleo.runtime_ids import next_seq as _next_seq
_MAX_EVENTS = 60

# A WALL is a page that STOPPED us — an anti-bot challenge, a CAPTCHA, a load error. V2-167 measured three runs that
# ended `status=working results=null` with `awaiting_login: false`, and in two of them the browser was sitting on a
# wall the whole time: Booking's `chal_t=` challenge and Google's `/sorry/index`. Nothing here recognised either, so
# the only field that could have said it (`awaiting_login`, written ONLY by the real login flow) said there was
# nothing to say — and the brain, correctly, reported no news for eleven minutes.
#
# URL-only ON PURPOSE. `nucleo/browser_search.py::_looks_blocked` reads the page BODY for the same class of event,
# and it can: it owns its own page object. This registry never sees a body — `update_view` is fed url+title. Both
# measured walls are visible in the URL, so this is what the evidence supports; a body check would need to live where
# the body is (the owner), not here. Keeping them apart is deliberate — one predicate reading two different inputs
# would be a predicate that lies about half its callers.
# ── WHAT A WALL IS — extracted to `widgets/navegador/walls.py` (ratchet, V2-358). Re-exports under the
# historical names: classification is pure and lives there; the HISTORY of walls encountered (t["walls"])
# remains here, because it belongs to the registry.
from widgets.navegador.walls import (  # noqa: F401 — re-export
    WALL_BODY_PEEK_CHARS, _WALL_BODY_MAX_CHARS, body_wall_reason, host_of, status_wall_reason, wall_reason,
)

_MAX_WALLS = 6          # enough to say «this happens everywhere», bounded so a loop cannot grow the task

# States: queued (created) · working (executing) · needs_input (waiting for answer) · open (a page opened FOR
# the operator, standing) · done · failed · cancelled.
#
# V2-197 — enumerated ONCE. `active_summaries()` and `recently_finished()` used to spell out their own subsets
# by hand, and a state in neither list is a task the live state does not mention AT ALL: not alive, not
# finished. The model then carries on with the last thing it knew, which is the correct thing to do when
# nobody tells it otherwise. That hole cost `cancelled` (V2-196, measured: «infinite wait loop on a task that
# had already failed») — and the moment the enumeration was single-sourced it turned out `open` was sitting in
# the same hole, set by `owner.py` every time a page is opened for the operator. Two lists that must be kept in
# sync are two lists that will not be.
LIVE_STATES = frozenset({"queued", "working", "needs_input"})
ENDED_STATES = frozenset({"done", "failed", "cancelled", "open"})


def inst_id(task_id: str) -> str:
    """Canvas card INSTANCE id for this task (one draggable card per task)."""
    return f"{WID}::{task_id}"


def _clock() -> str:
    return time.strftime("%H:%M:%S")


def _notify(task_id: str) -> None:
    """A task change → refresh ONLY its card (SSE widget/data with the instance id). Best-effort.

    A tab an errand drives also refreshes that errand's sheet (the wall/login it must act on, V2-571) and
    its entry in the processes panel (capture, page, V2-822)."""
    try:
        from voice.observer import emit
        _tid = trace_of(task_id)                                       # V2-044: chain to the phrase that requested the task
        with _lock:
            _sheet = str((_tasks.get(task_id) or {}).get("sheet") or "")
        ids = [inst_id(task_id)]
        if _sheet:
            from widgets.results import data as _results
            ids.append(_results.instance_id(_sheet))
        for cid in ids:                                                # V2-039: driven by the navigation worker
            extra = {"id": cid, "src": f"worker:{task_id}"}
            if _tid:
                extra.update(trace=_tid, span=f"web:{task_id}")
            emit("widget", "data", extra=extra)
    except Exception:
        pass
    from nucleo import process_view                    # V2-822: the panel's expanded entry shows this browser
    process_view.notify_for_tab(task_id)


def trace_of(task_id: str) -> str:
    """Trace id of the operator phrase that originated this task ("" if none). V2-044 — used by `_notify` and owner's
    `_TaskBrowser._emit` to chain each navigation step to its phrase in the Traces tree."""
    with _lock:
        t = _tasks.get(task_id)
        return (t or {}).get("trace") or ""


def _current_trace() -> str:
    try:
        from voice import trace as _trace
        return _trace.current()
    except Exception:
        return ""


_COEXIST_RE = None


# Words that do NOT identify the search SUBJECT: filler + search verbs + MARKETPLACE NAMES (two different searches —
# a motorcycle, a sofa— share "wallapop" but are NOT the same topic) + stopwords. The real subject
# (motorcycle/enduro/car/apartment/sofa...) anchors "this is the SAME search". Thus a short clarification ("no,
# enduro") stays anchored to the motorcycle through the word "motorcycle", but "motorcycle" and "apartment" never merge.
_STOP = {
    # search verbs/filler
    "buscar", "busca", "busque", "busques", "buscame", "buscando", "mostrar", "muestra", "dame", "encuentra",
    "encuentrame", "resultados", "segunda", "mano", "venta", "vender", "comprar", "quiero", "quiere", "necesito",
    "operador", "abrir", "abre", "navegador", "web", "pagina", "página", "internet", "mejores", "opciones",
    "candidatas", "anteriores", "rechaza", "cerca", "tarea", "tareas", "ventana", "ventanas", "pestaña", "pestana",
    "pestañas", "pestanas", "busqueda", "búsqueda",
    # marketplaces (the CHANNEL, not the subject)
    "wallapop", "milanuncios", "idealista", "amazon", "ebay", "aliexpress", "fotocasa", "vibbo",
    # frequent Spanish stopwords
    "una", "uno", "unos", "unas", "los", "las", "del", "para", "con", "por", "que", "eso", "esa", "ese", "esta",
    "este", "esto", "más", "mas", "muy", "dos", "tres", "todo", "toda", "todas", "todos", "sus", "porque", "son",
    "como", "pero", "the", "and", "for",
}


def _stem(w: str) -> str:
    """Rough singularization (no dependencies): moto/motos, coche/coches → same root. Only removes a final 's' from
    long words (len>4) → does not touch "los"/"las" or "moto"."""
    return w[:-1] if len(w) > 4 and w.endswith("s") else w


_STOP_STEMMED = {_stem(w) for w in _STOP}


# An ACTIVE browser task is "what we are doing RIGHT NOW": while it lives, any similar request is routed to IT — never
# open a SECOND browser for the same thing (state control, 2026-07-12). The only limit is an anti-ZOMBIE guard: a task
# hung for longer than _ZOMBIE_MAX must not block new searches forever. Previously dedup only looked at the first
# 45-90 s FROM CREATION → a long task (marketplaces take MINUTES) stopped being protected and a late refinement ("raise
# the price", "analyze them") spawned a TWIN browser doing the same search (bug from the 2026-07-12 session: one bike
# search ended up opening t1 + t2 in parallel).
_ZOMBIE_MAX = 1800.0   # s (30 min): beyond this, an "active" task is considered hung and no longer deduplicates.


# CONTINUITY: a recently FINISHED task remains "the search we are talking about" during this window → a follow-up on
# the same topic RE-LAUNCHES it in the SAME card (does not open a second browser). Outside the window, "the motorcycle
# thing again" is already a new search.
_CONTINUATION_MAX = 600.0   # s (10 min)


# How long a task that ENDED still deserves a line in the brain's state. Long enough to cover the turn where
# the operator asks «¿lo conseguiste?», short enough not to talk about yesterday's errands.
JUST_FINISHED_S = 600.0


#: The HARVEST of a browser task, key by key. Cumulative and monotonic — a page already counted never
#: un-counts itself, which is what lets the operator read the tab as a running total instead of a snapshot.
TALLY_KEYS = ("pages", "rows", "repeated", "unnamed", "hollow", "kept", "offered")

# refactor2710-12 — the registry's code lives in its concern modules; the STATE above stays here, and they read it
# (and every other name of this module) through the package.
from widgets.navegador.tasks.store import (  # noqa: E402,F401 — re-export
    create, ensure, get, all_ids, active_ids, waiting_id, login_waiting_id, add_event, tally, is_cancelled,
    cancel, finish)
from widgets.navegador.tasks.fields import (  # noqa: E402,F401 — re-export
    set_phase, set_login_wait, _raise_for_him, milestone, set_status, set_goal, set_sheet, set_title,
    set_goal_summary, set_results)
from widgets.navegador.tasks.continuation import (  # noqa: E402,F401 — re-export
    _words, _similar, similar_active, find_continuation)
from widgets.navegador.tasks.progress import (  # noqa: E402,F401 — re-export
    active_summaries, active_progress, recently_finished)
from widgets.navegador.tasks.announce import (  # noqa: E402,F401 — re-export
    _announce_wall, update_view, ask, answer, answer_from_turn, take_answer)
