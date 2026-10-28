#
# tasks — browser TASK REGISTRY. Each task = one objective driven in ITS OWN tab, with a live feed (events),
# structured results, and an optional question for the operator.
#
# The ORCHESTRATOR (fast layer) owns the FLEET — creates tasks, routes operator answers, knows what is in progress /
# done / waiting; Hermes plans each task; owner.py EXECUTES it in its tab and writes progress here; data.py serves
# per-task state to the canvas card. 1:1: card(canvas) ↔ tab(Chrome) ↔ task(this registry).
#
# In-memory on purpose: a task lives while its tab lives, and a restart kills tabs. owner/data/duo share this dict.
#
import itertools
import threading
import time

# The set-comparison arithmetic comes from THE yardstick module (`nucleo.matching`, pure stdlib, no cycle): the
# stemming and clarification contract stay here (browser-specific), the primitive is shared so the two judges of
# «same errand?» cannot drift apart.
from nucleo import matching

WID = "navegador"
_lock = threading.RLock()
_tasks: dict[str, dict] = {}          # task_id -> state
# Task ids come from the process-identity owner (F5). Per-process is CORRECT here: this registry is RAM, a task dies
# with its process and its card is ephemeral, so nothing durable is keyed on `tN` to collide after a restart.
from nucleo.runtime_ids import next_seq as _next_seq
_MAX_EVENTS = 60

# A WALL is a page that STOPPED us (anti-bot challenge, CAPTCHA, load error) — V2-167. Classification is pure and
# lives in `widgets/navegador/walls.py` (re-exported under the historical names); the HISTORY of walls hit
# (t["walls"]) belongs to the registry. Wall-by-URL here; a body check lives where the body is (the owner tab).
from widgets.navegador.walls import (  # noqa: F401 — re-export
    WALL_BODY_PEEK_CHARS, _WALL_BODY_MAX_CHARS, body_wall_reason, host_of, status_wall_reason, wall_reason,
)

_MAX_WALLS = 6          # enough to say «this happens everywhere», bounded so a loop cannot grow the task

# States: queued (created) · working (executing) · needs_input (waiting for answer) · open (a page opened FOR
# the operator, standing) · done · failed · cancelled.
#
# V2-197 — enumerated ONCE: a state missing from both the active and the finished subsets is a task the live state
# does not mention AT ALL. Two lists that must be kept in sync are two lists that will not be.
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


# Words that do NOT identify the search SUBJECT: filler, search verbs, MARKETPLACE NAMES (two searches can share
# "wallapop" and not be the same topic) and stopwords. The real subject anchors "this is the SAME search": "no,
# enduro" stays with the motorcycle, but "motorcycle" and "apartment" never merge.
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
# a SECOND browser for the same thing, however late the refinement (marketplaces take MINUTES). The only limit is the
# anti-ZOMBIE guard: a task hung longer than _ZOMBIE_MAX must not block new searches forever.
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

# The registry's code lives in its concern modules; the STATE above stays here, and they read it (and every other
# name of this module) through the package.
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
