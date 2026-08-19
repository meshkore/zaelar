#
# tasks.py — browser TASK REGISTRY (INI-016, multi-task phase). Each task = one objective driven in ITS OWN tab, with
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

WID = "navegador"
_lock = threading.RLock()
_tasks: dict[str, dict] = {}          # task_id -> state
_counter = itertools.count(1)
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
_WALL_URL_NEEDLES = (
    ("chrome-error://", "la página no llegó a cargar"),
    ("/sorry/index", "el buscador pidió verificación anti-robot"),
    ("/recaptcha/", "la página pidió resolver un captcha"),
    ("chal_t=", "el sitio interpuso una verificación anti-robot"),
    ("__cf_chl", "el sitio interpuso una verificación anti-robot"),
)


def wall_reason(url: str) -> str:
    """Short, operator-facing reason why this URL is a WALL, or '' when it is an ordinary page.

    Deliberately mechanical: this recognises a SIGNAL in a URL, it does not judge what the page means. The phrasing
    is what the operator hears, so it says what happened ("el sitio interpuso una verificación anti-robot"), never
    an internal token.
    """
    u = (url or "").strip().lower()
    if not u:
        return ""
    for needle, reason in _WALL_URL_NEEDLES:
        if needle in u:
            return reason
    return ""

# States: queued (created) · working (executing) · needs_input (waiting for answer) · done · failed · cancelled.


def inst_id(task_id: str) -> str:
    """Canvas card INSTANCE id for this task (one draggable card per task)."""
    return f"{WID}::{task_id}"


def _clock() -> str:
    return time.strftime("%H:%M:%S")


def _notify(task_id: str) -> None:
    """A task change → refresh ONLY its card (SSE widget/data with the instance id). Best-effort."""
    try:
        from voice.observer import emit
        extra = {"id": inst_id(task_id), "src": f"worker:{task_id}"}   # V2-039: driven by the navigation worker
        _tid = trace_of(task_id)                                       # V2-044: chain to the phrase that requested the task
        if _tid:
            extra["trace"] = _tid
            extra["span"] = f"web:{task_id}"
        emit("widget", "data", extra=extra)
    except Exception:
        pass


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


def create(goal: str, title: str = "", *, trace: str = "") -> str:
    """`trace`: pass it explicitly when the caller already knows it (V2-108, 2026-08-17) — `_current_trace()`
    reads the AMBIENT context (`voice.trace.current()`), which is only reliable when creation happens inline in
    a turn. `nucleo/dispatch.py::_prepare_web()` creates the task from inside the worker's OWN async execution,
    which never had that ambient scope active — confirmed with real data: every navigation/screenshot event for
    a worker-dispatched web task carried NO trace, for the task's entire lifetime (not a startup race that
    settles — this field is never written again after `create()`, so an empty read here is empty forever).
    `_prepare_web` has the correct id on hand the whole time (`rec.trace_id`, already reliably set — the
    escalation's own tool-call events prove it); passing it explicitly is a fix, not a fallback."""
    goal = (goal or "").strip()
    with _lock:
        tid = f"t{next(_counter)}"
        _tasks[tid] = {
            "id": tid, "goal": goal, "goal_summary": "", "title": (title or goal)[:60] or "Tarea",
            "status": "queued", "phase": "", "phase_active": False, "events": [], "results": None,
            "question": "", "answer": "", "url": "", "page_title": "", "shot_rev": 0,
            "awaiting_login": False, "created": time.time(),
            # V2-167: when this task last MOVED (new page or a milestone), and whether the page it sits on is a
            # wall. Both are read by `active_progress` so the brain can tell "no news yet" from "eleven minutes
            # on the same page" — two very different things it could not distinguish before.
            "last_progress": time.time(), "wall": "",
            # V2-044: the task is born from the phrase context (or adopted session) — explicit trace wins.
            "trace": trace or _current_trace(),
        }
    return tid


def ensure(task_id: str, goal: str = "", title: str = "") -> str:
    """Create the task with a FIXED id if it does not exist, or reuse it (for SINGLETON cards like manual navigation:
    one reused card instead of a new one for each open/search → no widget proliferation)."""
    with _lock:
        t = _tasks.get(task_id)
        if t:
            if goal:
                t["goal"] = goal
            if title:
                t["title"] = title[:60]
            return task_id
        _tasks[task_id] = {
            "id": task_id, "goal": (goal or "").strip(), "goal_summary": "",
            "title": (title or goal or task_id)[:60] or "Tarea",
            "status": "queued", "phase": "", "phase_active": False, "events": [], "results": None,
            "question": "", "answer": "", "url": "", "page_title": "", "shot_rev": 0,
            "awaiting_login": False, "created": time.time(),
            "last_progress": time.time(), "wall": "",     # V2-167
            "trace": _current_trace(),     # V2-044
        }
    return task_id


def get(task_id: str) -> dict:
    with _lock:
        t = _tasks.get(task_id)
        return dict(t) if t else {}


def all_ids() -> list[str]:
    with _lock:
        return list(_tasks.keys())


_COEXIST_RE = None


def _words(s: str) -> set:
    import re as _re
    global _COEXIST_RE
    if _COEXIST_RE is None:
        # Trim CLAUSES that talk about ANOTHER task ("without stopping the motorcycle task", "without closing X",
        # "apart from the search for Y", "besides Z") — their subject belongs to ANOTHER task and polluted matching
        # (bug 2026-07-13: "dog face WITHOUT STOPPING the motorcycle task" matched the bike because of "motorcycles").
        _COEXIST_RE = _re.compile(
            r"\b(sin (parar|detener|cerrar|tocar|cancelar)|aparte de|adem[aá]s de|dejando|manteniendo)\b.*$",
            _re.I)
    s = _COEXIST_RE.sub("", (s or "").lower())
    return {w for w in _re.split(r"[^0-9a-záéíóúñ]+", s) if len(w) > 2}


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


def _similar(g: set, other_goal: str) -> bool:
    """True if word set `g` and `other_goal` are the SAME search. Anchor on the shared SUBJECT (roots len≥4, not
    stopword/marketplace). To avoid merging different topics through an incidental mention (bug 2026-07-13: "dog face
    without stopping the motorcycle task" matched the bike through "motorcycles"), a ONE-word anchor only counts for
    SHORT CLARIFICATIONS (`g` ≤3 content words, e.g. "no, enduro"); a fuller request requires ≥2 shared subjects or
    Jaccard ≥0.4. Two different topics (motorcycle vs apartment, motorcycle vs dog) do not match."""
    gs = {_stem(w) for w in g}
    os_ = {_stem(w) for w in _words(other_goal)}
    if not gs or not os_:
        return False
    shared = gs & os_
    subject = {w for w in shared if len(w) >= 4 and w not in _STOP_STEMMED}   # shared subject(s) (moto, enduro, car...)
    # SHORT clarification → 1 subject is enough (keeps "no, enduro" anchored to the bike); fuller request → ≥2.
    # "Short" is measured in CONTENT words (as the contract above says), NOT total words: "no, I want a 300 enduro
    # motorcycle" has filler but its content is 2 words — it is a clarification.
    content = {w for w in gs if len(w) >= 4 and w not in _STOP_STEMMED}
    if subject and (len(content) <= 3 or len(subject) >= 2):
        return True
    union = len(gs | os_)
    return (len(shared) / union if union else 0) >= 0.4


# An ACTIVE browser task is "what we are doing RIGHT NOW": while it lives, any similar request is routed to IT — never
# open a SECOND browser for the same thing (state control, 2026-07-12). The only limit is an anti-ZOMBIE guard: a task
# hung for longer than _ZOMBIE_MAX must not block new searches forever. Previously dedup only looked at the first
# 45-90 s FROM CREATION → a long task (marketplaces take MINUTES) stopped being protected and a late refinement ("raise
# the price", "analyze them") spawned a TWIN browser doing the same search (bug from the 2026-07-12 session: one bike
# search ended up opening t1 + t2 in parallel).
_ZOMBIE_MAX = 1800.0   # s (30 min): beyond this, an "active" task is considered hung and no longer deduplicates.


def similar_active(goal: str, within: float = _ZOMBIE_MAX) -> str | None:
    """Id of an ACTIVE task (queued/working/needs_input) whose objective looks very similar to `goal` — so the SAME
    search does NOT open a SECOND browser even if the operator refines it turns —or MINUTES— later while the browser is
    still working. An active task deduplicates throughout its WHOLE life (up to `within`, only anti-zombie guard).
    Returns None if there is no similar one (two different tasks —motorcycle vs apartment— do NOT merge)."""
    g = _words(goal)
    if not g:
        return None
    now = time.time()
    with _lock:
        for tid, t in _tasks.items():
            if t.get("status") not in ("queued", "working", "needs_input"):
                continue
            if now - t.get("created", 0) > within:   # anti-zombie guard (hung task); NOT a dedup window
                continue
            if _similar(g, t.get("goal", "")):
                return tid
    return None


# CONTINUITY: a recently FINISHED task remains "the search we are talking about" during this window → a follow-up on
# the same topic RE-LAUNCHES it in the SAME card (does not open a second browser). Outside the window, "the motorcycle
# thing again" is already a new search.
_CONTINUATION_MAX = 600.0   # s (10 min)


def find_continuation(goal: str) -> tuple[str, str] | None:
    """(tid, status) of the task that this `goal` CONTINUES — so operator CLARIFICATIONS MODIFY the current task
    instead of opening another browser:
      · similar ACTIVE task → refined WHILE RUNNING (the loop re-reads the objective);
      · similar recently FINISHED task (≤_CONTINUATION_MAX) → RE-LAUNCHED in the same card.
    Prioritize active; otherwise the most recent finished one. None if there is no same-topic task (motorcycle vs
    apartment do not match). This is STATE CONTROL: "when I search for a bike and say «no, enduro», modify the task,
    do not open another one"."""
    g = _words(goal)
    if not g:
        return None
    now = time.time()
    with _lock:
        for tid, t in _tasks.items():   # 1) active (priority) → refine while running
            if t.get("status") in ("queued", "working", "needs_input") \
                    and now - t.get("created", 0) <= _ZOMBIE_MAX and _similar(g, t.get("goal", "")):
                return (tid, t["status"])
        best = None                     # 2) recently finished → re-launch in its card (most recent)
        for tid, t in _tasks.items():
            if t.get("status") not in ("done", "failed"):
                continue
            ts = t.get("finished") or t.get("created", 0)
            if now - ts <= _CONTINUATION_MAX and _similar(g, t.get("goal", "")):
                if best is None or ts > best[2]:
                    best = (tid, t["status"], ts)
        if best:
            return (best[0], best[1])
    return None


def active_summaries(limit: int = 3) -> list[tuple[str, str]]:
    """(id, objective) for tasks ACTIVE now — so brain STATE says EXPLICITLY what is in progress (not just "there are N
    tasks") and does not relaunch a search that is already running. Most recent first."""
    with _lock:
        act = [(tid, (t.get("goal") or "").strip())
               for tid, t in _tasks.items() if t.get("status") in ("queued", "working", "needs_input")]
    return list(reversed(act))[:max(1, limit)]


def active_progress(limit: int = 3) -> list[dict]:
    """What each live browser task has ACTUALLY done: the page it is on and how many steps it has taken.

    V2-145 — the brain was told a browser task existed and its goal, and nothing else, so «how is it going?» had
    only the elapsed seconds to answer with. It turned them into detail it could not have: «lleva unos 2 minutos
    abierto en la página» and «todavía interactuando», while the mechanism report for that very task read
    `status=working url= events=[] n_search_events=0` — the task had opened nothing at all.

    Same remedy as `silent_s` in V2-131, one layer down: the truth already existed here and simply never reached
    the prompt. `url` and `events` are what the task itself records as it drives, so an empty pair is not a gap
    in our knowledge — it is the fact that nothing has happened yet, and it is what the brain has to say.
    """
    now = time.time()
    with _lock:
        rows = [{"id": tid,
                 "goal": (t.get("goal") or "").strip(),
                 "url": (t.get("url") or "").strip(),
                 "phase": (t.get("phase") or "").strip(),
                 "steps": len(t.get("events") or []),
                 # V2-150: the run discovered «Casa Lucio solo acepta reservas por teléfono» and the operator
                 # only heard it at the very end, when he asked to stop. The milestone was in the task all
                 # along; what the brain saw was a step COUNT. A number cannot be said out loud.
                 "last_event": ((t.get("events") or [{}])[-1].get("text") or "").strip()
                                if t.get("events") else "",
                 # V2-167: the two facts the brain was missing. `stalled_s` is time since the task last MOVED
                 # (new page or reported step), not time since it started — the difference between "still
                 # working" and "stuck" is exactly this, and without it the turn could only offer elapsed
                 # seconds, which V2-145 already established is not a description of anything.
                 "stalled_s": int(max(0.0, now - float(t.get("last_progress") or t.get("created") or now))),
                 "wall": (t.get("wall") or ""),
                 "awaiting_login": bool(t.get("awaiting_login"))}
                for tid, t in _tasks.items() if t.get("status") in ("queued", "working", "needs_input")]
    return list(reversed(rows))[:max(1, limit)]


# How long a task that ENDED still deserves a line in the brain's state. Long enough to cover the turn where
# the operator asks «¿lo conseguiste?», short enough not to talk about yesterday's errands.
JUST_FINISHED_S = 600.0


def recently_finished(now: float | None = None, limit: int = 3) -> list[dict]:
    """Tasks that ENDED in the last few minutes, and whether they brought anything back.

    V2-150 — `restaurant-tonight-madrid`: the mechanism report read `status=done url=` and zaelar kept saying
    «los procesos siguen en marcha — llevan casi 5 minutos». That is not the model inventing for the sake of it:
    the brain only ever sees ACTIVE tasks (`active_summaries`/`active_progress`), so the moment this one
    finished it simply VANISHED from the state. There was no fact left saying it had ended, let alone that it
    had ended empty — and the turn filled the hole with the only thing it still had, the worker.

    Same remedy as `silent_s` (V2-131) and the browser progress (V2-145), one step further: an ending is a
    FACT, and a task that finished without results is the most useful fact of the three.
    """
    now = time.time() if now is None else now
    with _lock:
        rows = [{"id": tid,
                 "goal": (t.get("goal") or "").strip(),
                 "status": t.get("status") or "",
                 "url": (t.get("url") or "").strip(),
                 "has_results": bool(t.get("results")),
                 "last_event": ((t.get("events") or [{}])[-1].get("text") or "").strip()
                                if t.get("events") else "",
                 "ago_s": int(now - float(t.get("finished") or now))}
                for tid, t in _tasks.items()
                if t.get("status") in ("done", "failed")
                and (now - float(t.get("finished") or 0)) <= JUST_FINISHED_S]
    rows.sort(key=lambda r: r["ago_s"])
    return rows[:max(1, limit)]


def active_ids() -> list[str]:
    """Tasks that have not finished yet (for routing answers / cancelling / listing)."""
    with _lock:
        return [tid for tid, t in _tasks.items() if t["status"] in ("queued", "working", "needs_input")]


def waiting_id() -> str | None:
    """The task waiting for an operator answer (most recent if several exist)."""
    with _lock:
        w = [tid for tid, t in _tasks.items() if t["status"] == "needs_input"]
        return w[-1] if w else None


def login_waiting_id() -> str | None:
    """The task waiting for the operator to SIGN IN in the visible window (awaiting_login). Most recent if several
    exist. Used to route the voice "I'm already in" to that task's auth_done."""
    with _lock:
        w = [tid for tid, t in _tasks.items() if t.get("awaiting_login")]
        return w[-1] if w else None


def add_event(task_id: str, text: str) -> None:
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["events"].append({"t": _clock(), "text": str(text)[:300]})
        del t["events"][:-_MAX_EVENTS]
        t["last_progress"] = time.time()          # V2-167: a reported step IS progress
    _notify(task_id)


def set_phase(task_id: str, phase: str, active: bool = True) -> None:
    """Process PHASE (what the operator wants to see, not every click): 'searching...', 'collecting results',
    'investigating the best', 'ready'. `active`=True → spinner in the card. Refreshes the card."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["phase"] = str(phase or "")
        t["phase_active"] = bool(active)
    _notify(task_id)


def set_login_wait(task_id: str, on: bool) -> None:
    """The card waits for the operator to sign in in the visible window (shows an 'I'm in' button)."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["awaiting_login"] = bool(on)
    _notify(task_id)


def milestone(task_id: str, text: str) -> None:
    """A process MILESTONE (e.g. '34 listings found', 'analyzing 10 finalists') — NOT every browser action.

    Goes to TWO places (2026-08-10): the card feed (ephemeral, in memory, dies with the task) and the event registry,
    which is what can be audited later. Previously it only went to the card: milestones describing what the task FOUND
    and DISCARDED —exactly the evidence of whether the search returned what was requested— disappeared when closing
    it. Now they remain, with the trace of the phrase that requested the task and the actor `span`."""
    add_event(task_id, text)
    try:
        from voice.observer import emit
        extra = {"id": "navegador", "task": task_id, "span": f"web:{task_id}"}
        tid = trace_of(task_id)
        if tid:
            extra["trace"] = tid
        emit("navegador", "🏁 hito", text=str(text), extra=extra)
    except Exception:
        pass


def set_status(task_id: str, status: str) -> None:
    with _lock:
        t = _tasks.get(task_id)
        if not t or t["status"] == status:
            return
        t["status"] = status
        if status in ("done", "failed", "cancelled"):
            t["finished"] = time.time()   # mark the CONTINUITY window (find_continuation)
    _notify(task_id)


def set_goal(task_id: str, goal: str) -> None:
    """Update a task OBJECTIVE (operator clarifications MODIFY it). The automator loop re-reads the objective on every
    step (agent.run_task) → a clarification about a LIVE task changes what it searches without opening another
    browser. Does not touch the title (the card keeps its name)."""
    goal = (goal or "").strip()
    if not goal:
        return
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["goal"] = goal
    _notify(task_id)


def set_goal_summary(task_id: str, summary: str) -> None:
    """Set the synthesized ESSENCE of the objective (objective + criteria, compressed by LLM) for DISPLAY in the card —
    the full `goal` remains intact as operational text guiding the search. Best-effort: if synthesis fails, the card
    falls back to the raw `goal`."""
    summary = (summary or "").strip()
    if not summary:
        return
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["goal_summary"] = summary[:200]
        t["title"] = summary[:60]   # the card title also uses the essence (previously truncated the raw goal)
    _notify(task_id)


def set_results(task_id: str, results) -> None:
    """Structured `results` (e.g. {"conclusion": "...", "items": [{title,subtitle,price,url,image}]})."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["results"] = results
    _notify(task_id)


def _announce_wall(task_id: str, reason: str) -> None:
    """A wall is not progress and it is not a phase: it is the end of what this task can do on its own.

    So it is SAID in the three places the operator can see, instead of only being a field somebody might read
    (V2-167, operator's request: «podríamos mostrar la imagen del navegador en pantalla y decir "Booking me ha
    bloqueado" y poner una captura de lo que ha pasado y decirle que tú ya no puedes seguir»):

      · a MILESTONE, which lands in the card's feed AND in the durable event registry, so it can be audited
        later — a phase alone dies with the task;
      · the PHASE, with the spinner OFF: a spinner on a blocked page is the screen saying «trabajando» while
        nothing works, exactly the kind of state that can lie;
      · and the card is OPENED, because the capture already on disk IS the evidence — the operator sees the
        challenge page itself rather than being told about it.
    """
    milestone(task_id, f"⛔ {reason} — no puedo seguir yo solo desde aquí")
    set_phase(task_id, reason, False)
    try:
        from voice.observer import emit
        emit("widget", "show", extra={"id": inst_id(task_id), "src": f"wall:{task_id}"})
    except Exception:
        pass


def update_view(task_id: str, url: str = "", page_title: str = "", shot_rev: int | None = None) -> None:
    """This task's browser changed view (new capture) → refresh its card."""
    struck = ""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        if url:
            # V2-167: only a page CHANGE counts as progress. A screenshot does not: the restaurant run took ten
            # capture revisions over four URLs and spent its last eleven minutes re-photographing the same page,
            # so `shot_rev` would have reported healthy movement while nothing moved.
            if url != t.get("url"):
                t["last_progress"] = time.time()
            t["url"] = url
            was, t["wall"] = (t.get("wall") or ""), wall_reason(url)
            if t["wall"] and t["wall"] != was:
                struck = t["wall"]
        if page_title:
            t["page_title"] = page_title
        if shot_rev is not None:
            t["shot_rev"] = shot_rev
    _notify(task_id)
    if struck:
        _announce_wall(task_id, struck)


def ask(task_id: str, question: str) -> None:
    """The task needs data from the operator → needs_input status + question (appears in its feed and by voice)."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["question"] = str(question or "").strip()
        t["answer"] = ""
        t["status"] = "needs_input"
    add_event(task_id, f"❓ {question}")


def answer(task_id: str, text: str) -> None:
    """The operator answered this task's question → the loop will pick it up (`answer` poll)."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["answer"] = str(text or "").strip()
        t["question"] = ""
        if t["status"] == "needs_input":
            t["status"] = "working"
    add_event(task_id, f"↩︎ respuesta: {text}")


def take_answer(task_id: str) -> str:
    """The loop consumes the pending answer (once only)."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return ""
        ans = t.get("answer") or ""
        t["answer"] = ""
        return ans


def is_cancelled(task_id: str) -> bool:
    with _lock:
        t = _tasks.get(task_id)
        return (not t) or t["status"] == "cancelled"


def cancel(task_id: str) -> None:
    set_status(task_id, "cancelled")
    add_event(task_id, "⏹ cancelada por el operador")


def finish(task_id: str, status: str, summary: str = "") -> None:
    """Close the task (done|failed) and leave the summary in the feed."""
    if summary:
        add_event(task_id, summary)
    set_status(task_id, status if status in ("done", "failed") else "done")
