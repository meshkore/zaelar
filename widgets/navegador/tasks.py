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
_WALL_URL_NEEDLES = (
    ("chrome-error://", "la página no llegó a cargar"),
    ("/sorry/index", "el buscador pidió verificación anti-robot"),
    ("/recaptcha/", "la página pidió resolver un captcha"),
    ("chal_t=", "el sitio interpuso una verificación anti-robot"),
    ("__cf_chl", "el sitio interpuso una verificación anti-robot"),
)

# The site's OWN error landing page — a wall too, and one the browser reports as a perfectly successful
# navigation, because it IS one: status 200, real host, page renders. Measured on
# `cancel-subscription-before-charge__es` (V2-176 round 3): the task ended on
# `https://www.netflix.com/NotFound?prev=…` and zaelar told the operator, twice, that «la página no se ha
# abierto del todo» and then that the login page was ready for him to type his credentials into. The judge
# called it gaslighting; it was not — nothing in the state said the page was an error, so «still loading» was
# the most reasonable thing left to say.
#
# Matched as a whole PATH SEGMENT, never as a substring: «/notfound» is an error page and
# «/articles/404-ways-to-cook-eggs» is not. Query strings are excluded on purpose — the measured URL carries
# `?prev=https://www.netflix.com/es-es/ContactUs`, so a substring match over the whole URL would fire on the
# perfectly good page it came FROM.
_ERROR_PATH_SEGMENTS = frozenset({"notfound", "not-found", "404", "page-not-found", "pagenotfound",
                                  "errorpage", "error-404", "404.html", "not_found"})

# A wall served in the BODY, with a perfectly ordinary URL and a 200 status. V2-167 left this half open on purpose
# after measuring it on a REAL run of the theatre case: `entradas.com` answered the event page with an Akamai
# «Access Denied» bot-detection page. The URL said nothing, `wall_reason()` saw nothing, the card never opened and
# the operator was never told — the worker read it off the snapshot and re-routed by itself, which is why the task
# did not get stuck and why the hole stayed invisible.
#
# This is a SECOND predicate over a DIFFERENT input, not a widening of the first one — `wall_reason` still answers
# only about URLs. The caller decides which inputs it holds; the owner's tab holds both.
#
# The fragility the initiative warned about is «declaring a wall on any page that happens to mention the word», and
# the guard against it is LENGTH, not a longer needle list: a bot wall is a nearly empty page (Akamai's is ~200
# chars, Cloudflare's interstitial ~400), while an article that talks about access being denied is thousands. So a
# needle only counts inside a page too short to be content. Measured on the run above: the wall page was 214 chars.
_WALL_BODY_MAX_CHARS = 1200

# How much text a caller must read before asking. It is deliberately LARGER than the gate above, and single-sourced
# here because getting it wrong is silent and inverts the guard: read exactly 1200 chars of a 50k-char article and
# the text arrives «short», so the length gate — the whole defence against false positives — passes every page.
WALL_BODY_PEEK_CHARS = _WALL_BODY_MAX_CHARS + 400
_WALL_BODY_NEEDLES = (
    ("access denied", "el sitio bloqueó el acceso (te tomó por un robot)"),
    ("acceso denegado", "el sitio bloqueó el acceso (te tomó por un robot)"),
    ("permission to access", "el sitio bloqueó el acceso (te tomó por un robot)"),
    ("you have been blocked", "el sitio bloqueó el acceso (te tomó por un robot)"),
    ("request blocked", "el sitio bloqueó el acceso (te tomó por un robot)"),
    ("unusual traffic", "el sitio pidió verificación anti-robot"),
    ("tráfico inusual", "el sitio pidió verificación anti-robot"),
    ("trafico inusual", "el sitio pidió verificación anti-robot"),
    ("are you a robot", "el sitio pidió verificación anti-robot"),
    ("not a robot", "el sitio pidió verificación anti-robot"),
    ("no soy un robot", "el sitio pidió verificación anti-robot"),
    ("verify you are human", "el sitio pidió verificación anti-robot"),
    ("verifica que eres humano", "el sitio pidió verificación anti-robot"),
    ("checking your browser", "el sitio pidió verificación anti-robot"),
    ("captcha", "la página pidió resolver un captcha"),
    ("enable javascript and cookies", "el sitio exigió javascript y cookies para dejarnos pasar"),
    ("too many requests", "el sitio cortó por exceso de peticiones"),
    ("demasiadas peticiones", "el sitio cortó por exceso de peticiones"),
)


def body_wall_reason(text: str) -> str:
    """Short, operator-facing reason why this PAGE TEXT is a WALL, or '' when it is an ordinary page.

    Sibling of `wall_reason()`, never a replacement: that one answers about a URL, this one about the text the tab
    is showing. Only pages too short to be content are considered at all (see `_WALL_BODY_MAX_CHARS`) — the needles
    alone would fire on any article that discusses bot detection.
    """
    t = " ".join((text or "").split()).lower()
    if not t or len(t) > _WALL_BODY_MAX_CHARS:
        return ""
    for needle, reason in _WALL_BODY_NEEDLES:
        if needle in t:
            return reason
    return ""


_MAX_WALLS = 6          # enough to say «esto pasa en todas partes», bounded so a loop cannot grow the task


def host_of(url: str) -> str:
    """Host of a URL, without `www.` — what the operator recognises. Never the full URL: a query string read out
    loud is noise, and the site is the part he can act on («pues mira en otra web»)."""
    try:
        from urllib.parse import urlparse
        h = (urlparse((url or "").strip()).netloc or "").lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


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
    try:
        from urllib.parse import urlparse
        path = urlparse(u).path or ""
    except Exception:
        return ""
    if any(seg.strip().lower() in _ERROR_PATH_SEGMENTS for seg in path.split("/") if seg.strip()):
        return "el sitio devolvió una página de error (no existe esa página)"
    return ""

# States: queued (created) · working (executing) · needs_input (waiting for answer) · open (a page opened FOR
# the operator, standing) · done · failed · cancelled.
#
# V2-197 — enumerated ONCE. `active_summaries()` and `recently_finished()` used to spell out their own subsets
# by hand, and a state in neither list is a task the live state does not mention AT ALL: not alive, not
# finished. The model then carries on with the last thing it knew, which is the correct thing to do when
# nobody tells it otherwise. That hole cost `cancelled` (V2-196, measured: «bucle de espera infinito sobre una
# tarea que ya falló») — and the moment the enumeration was single-sourced it turned out `open` was sitting in
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
        tid = f"t{_next_seq('navegador.task')}"
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
    return matching.jaccard(gs, os_) >= 0.4


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
               for tid, t in _tasks.items() if t.get("status") in LIVE_STATES]
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
                 # The obstacles this task has ALREADY hit, which `wall` cannot carry (it is recomputed per
                 # capture). Count + the last one, because that is what a sentence needs.
                 "walls_hit": len(t.get("walls") or []),
                 "last_wall": ((t.get("walls") or [{}])[-1] if t.get("walls") else {}),
                 "awaiting_login": bool(t.get("awaiting_login")),
                 # V2-202: the confirm-gate's QUESTION. `ask()` has always written it here, and this is the only
                 # route a live task has into the prompt, so a task parked on «shall I press Buy tickets?» was
                 # structurally unable to reach the conversation: the operator was never asked, the answer had
                 # nowhere to arrive, and the gate died on its timeout while the turn narrated progress.
                 "question": (t.get("question") or "").strip(),
                 # V2-192: si la tarea YA TRAJO algo, eso gana a cualquier medida de atasco. Sin este campo el
                 # turno solo podía elegir entre «sigue viva» y «está bloqueada», y ninguna de las dos es la
                 # verdad cuando los resultados están ahí.
                 "has_results": bool(t.get("results"))}
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
                # V2-196: `cancelled` también es un final, y era el único que caía en un HUECO — ni activa
                # (`active_summaries` filtra por queued/working/needs_input) ni recién terminada. O sea que el
                # estado no la mencionaba EN ABSOLUTO y el modelo seguía con lo último que recordaba: «bucle de
                # espera infinito sobre una tarea que ya falló», medido en `find-theatre-tickets__es`
                # (2026-08-20 03:11) con `status=cancelled` en el informe de mecanismo.
                if t.get("status") in ENDED_STATES
                and (now - float(t.get("finished") or 0)) <= JUST_FINISHED_S]
    rows.sort(key=lambda r: r["ago_s"])
    return rows[:max(1, limit)]


def active_ids() -> list[str]:
    """Tasks that have not finished yet (for routing answers / cancelling / listing)."""
    with _lock:
        return [tid for tid, t in _tasks.items() if t["status"] in LIVE_STATES]


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
        if status in ENDED_STATES:
            # V2-197: la MISMA lista que usan los filtros. Estaba escrita a mano aquí también —una tercera
            # copia— y por eso `open` no sellaba nunca cuándo había terminado: entraba en los finales y
            # `recently_finished()` lo descartaba igual por su ventana de tiempo. Un estado terminal que no
            # sella su hora es un final que nadie puede fechar.
            t["finished"] = time.time()   # mark the CONTINUITY window (find_continuation)
            # …and the SPINNER goes off with it, for the same reason the line above exists. Measured
            # 2026-08-23 (`search-secondhand-monitor__es`): a task read `status="cancelled"` while still
            # carrying `phase="en pausa — reanudando la gestión"` and `phase_active=True` — a resume that was
            # never going to happen, announced by a task that had already ended. The card kept spinning and
            # every reader of the phase saw work in flight; the round's watchdog fired on exactly that gap
            # between what the mechanism said and what the state advertised.
            # The phase TEXT is left alone on purpose: it is the last true thing that happened and it dates
            # the ending. What cannot survive the ending is the claim that it is still going.
            t["phase_active"] = False
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
    # …AND THE CONVERSATION, which is the one place the three above cannot reach (2026-08-20, measured on
    # `cancel-subscription-before-charge__es` and `find-theatre-tickets__es`). The card, the phase and the panel
    # are all surfaces the operator has to be LOOKING at. If he is not, the wall is recorded everywhere and said
    # nowhere: the tester measured `wall="la página pidió resolver un captcha"`, `walls_hit=1` and brain-notes=0
    # in the same round the turn was still narrating that the cancellation was going ahead.
    #
    # `active_progress()` already carries the wall into the prompt, but that only helps when the operator ASKS.
    # A note is what covers the other half — it enters the NEXT turn on its own, and it does so on the TEXT
    # channel too, which `proactive.notify` cannot (its brain-note fallback lives inside `if _speaker is not
    # None`, so a chat-only session gets nothing at all).
    #
    # Same seam the FINISH of a task already uses (`owner.py`), for the same reason: a fact the operator can act
    # on has to arrive by itself.
    try:
        from voice import brain_notes
        _g = (get(task_id) or {}).get("goal") or "la tarea del navegador"
        brain_notes.push(
            f"[SISTEMA] Navegador (tarea {task_id}): la web BLOQUEÓ «{str(_g)[:70]}» — {reason}. No va a "
            f"terminar sola. Díselo al operador EN ESTE TURNO, con una salida concreta (probar otro sitio, "
            f"que entre él, o dejarlo); no le digas que sigues con ello.")
    except Exception:
        pass


def update_view(task_id: str, url: str = "", page_title: str = "", shot_rev: int | None = None,
                page_text: str = "") -> None:
    """This task's browser changed view (new capture) → refresh its card.

    `page_text` is what the tab is SHOWING (bounded, best-effort). It is the only input that can catch a wall served
    in the body with an ordinary URL — see `body_wall_reason`. Callers that do not hold the text simply omit it and
    get exactly the URL-only behaviour they had before.
    """
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
            was, t["wall"] = (t.get("wall") or ""), (wall_reason(url) or body_wall_reason(page_text))
            if t["wall"] and t["wall"] != was:
                struck = t["wall"]
                # A WALL THAT WAS STRUCK LEAVES A TRACE. `wall` above is recomputed on every capture, so it
                # describes the page the tab is standing on RIGHT NOW — and the moment the worker re-routes (which
                # is the correct thing for it to do) the fact is erased. Measured on `find-theatre-tickets__es`
                # (2026-08-20 12:39): the body-served wall detector fired in production — the judge quotes its
                # exact wording back at us, «el sitio bloqueó el acceso» — the worker adapted and moved on to
                # elcorteingles.es, and zaelar spent TEN turns saying «sigue sin dar señal de dónde está». The
                # obstacle had happened, nobody could still see it, and the operator was never told.
                #
                # Bounded, and it keeps the SITE: «me bloquearon» is a fact, «me bloqueó entradas.com» is one the
                # operator can act on. Same lesson as V2-150/V2-196/V2-198, now for an obstacle instead of an
                # ending: a fact that only lives one turn is a fact the conversation loses.
                _hist = t.setdefault("walls", [])
                _hist.append({"reason": struck, "site": host_of(url), "at": time.time()})
                del _hist[:-_MAX_WALLS]
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
        _goal = (t.get("goal") or "").strip()
    add_event(task_id, f"❓ {question}")
    # A QUESTION NOBODY IS ASKED IS NOT A QUESTION. Measured 2026-08-20 on `find-theatre-tickets__es`: the task
    # parked on «Voy a pulsar COMPRAR ENTRADAS. ¿Lo confirmo?» at 16:22:18 and the operator was never told —
    # the question reached the card's feed and stopped there. V2-202 gave the ANSWER a way back in
    # (`answer_from_turn`); this is the other half, the way OUT. Without it the gate stops the work and waits on
    # a person who does not know they are being waited on, which is the confirm-gate defect one layer up.
    try:
        from voice import brain_notes
        brain_notes.push(
            f"[SISTEMA] Navegador (tarea {task_id}): «{_goal[:70]}» está PARADA esperando tu OK. Pregúntaselo al "
            f"operador EN ESTE TURNO, literalmente: «{str(question or '')[:140]}». Su sí o su no ES la respuesta: "
            f"no lo trates como una petición nueva.")
    except Exception:
        pass


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


def answer_from_turn(text: str) -> dict | None:
    """The operator's yes/no IN THE CONVERSATION answers the task parked at the confirm-gate. None if there was
    nothing waiting or the turn was not an answer.

    V2-202 — until now the ONLY way to answer was the card's button (`answer_task`, a widget data-op), so a
    confirm-gate hit during a voice/text errand had no route back at all: `waiting_id()` had zero callers in
    production. Measured on `find-theatre-tickets__es` (2026-08-20 13:33): the gate stopped «Comprar entradas»,
    asked nobody, and failed the worker with `acción NO confirmada por el operador` while the turn kept
    reporting progress. The judge, reading only the dialogue, called it «esperando una confirmación que nunca se
    pidió al usuario» — both halves of the same hole.

    The decision lives HERE, with the state it resolves, exactly like `dispatch.resolve_confirm` lives with
    `_PENDING_CONFIRM`: both channels call this one function instead of each classifying on its own (V2-153 is
    what two copies of one decision cost). The yes/no classifier is the shared deterministic one — a gate is no
    place to ask an LLM whether «venga, dale» meant yes.
    """
    tid = waiting_id()
    if not tid:
        return None
    # ⚠️ `needs_input` NO significa «hay una pregunta»: el traspaso de LOGIN lo pone (`owner._authenticate`) y las
    # tareas que ese traspaso PAUSA también, las dos SIN pregunta. Sin esta comprobación, un turno que llevara un
    # «vale» —«Vale, abre la web de Netflix y me dices cuando esté en el login»— se leía como la respuesta a un
    # confirm-gate que nadie había abierto, y se comía la acción REAL de ese turno. Regresión medida el mismo día
    # en `cancel-subscription-before-charge__es`, que era el único 5/5 del tablero. La pregunta es lo único que
    # distingue «te estoy esperando a ti» de «estoy esperando a que TÚ hagas algo en otra ventana».
    if not (get(tid) or {}).get("question"):
        return None
    from widgets import confirm as _confirm
    verdict = _confirm.classify_reply(text or "")
    if not verdict:
        return None
    answer(tid, text or "")
    return {"task_id": tid, "ok": verdict == "yes"}


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
