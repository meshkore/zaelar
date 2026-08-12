#
# tasks.py — REGISTRO de TAREAS del navegador (INI-016, Fase multi-tarea). Cada tarea = un objetivo que se conduce
# en SU PROPIA pestaña, con un feed vivo (eventos), resultados estructurados y una pregunta opcional al operador.
#
# Reparto (decidido con el operador 2026-07-08): el ORQUESTADOR (capa rápida, brains/duo) posee la FLOTA — crea
# tareas, enruta las respuestas del operador y sabe qué está en curso / hecho / esperando; Hermes planifica/analiza
# cada tarea; owner.py la EJECUTA en su pestaña y escribe aquí el progreso; data.py sirve el estado por-tarea a la
# tarjeta del canvas. Correspondencia 1:1  tarjeta(canvas) ↔ pestaña(Chrome) ↔ tarea(este registro).
#
# En memoria a propósito: una tarea vive mientras vive su pestaña; un reinicio mata las pestañas, así que no tiene
# sentido persistirlas. Mismo proceso para owner/data/duo → todos comparten este módulo (un solo dict).
#
import itertools
import threading
import time

WID = "navegador"
_lock = threading.RLock()
_tasks: dict[str, dict] = {}          # task_id -> estado
_counter = itertools.count(1)
_MAX_EVENTS = 60

# Estados: queued (creada) · working (ejecutando) · needs_input (espera respuesta) · done · failed · cancelled.


def inst_id(task_id: str) -> str:
    """Id de INSTANCIA de la tarjeta en el canvas para esta tarea (una tarjeta arrastrable por tarea)."""
    return f"{WID}::{task_id}"


def _clock() -> str:
    return time.strftime("%H:%M:%S")


def _notify(task_id: str) -> None:
    """Un cambio en la tarea → refresca SOLO su tarjeta (SSE widget/data con el id de instancia). Best-effort."""
    try:
        from voice.observer import emit
        extra = {"id": inst_id(task_id), "src": f"worker:{task_id}"}   # V2-039: conducida por el worker de navegación
        _tid = trace_of(task_id)                                       # V2-044: encadena a la frase que pidió la tarea
        if _tid:
            extra["trace"] = _tid
            extra["span"] = f"web:{task_id}"
        emit("widget", "data", extra=extra)
    except Exception:
        pass


def trace_of(task_id: str) -> str:
    """Trace id de la frase del operador que originó esta tarea ("" si no hay). V2-044 — lo usan `_notify` y el
    `_TaskBrowser._emit` del owner para encadenar cada paso de navegación a su frase en el árbol de Trazas."""
    with _lock:
        t = _tasks.get(task_id)
        return (t or {}).get("trace") or ""


def _current_trace() -> str:
    try:
        from voice import trace as _trace
        return _trace.current()
    except Exception:
        return ""


def create(goal: str, title: str = "") -> str:
    goal = (goal or "").strip()
    with _lock:
        tid = f"t{next(_counter)}"
        _tasks[tid] = {
            "id": tid, "goal": goal, "goal_summary": "", "title": (title or goal)[:60] or "Tarea",
            "status": "queued", "phase": "", "phase_active": False, "events": [], "results": None,
            "question": "", "answer": "", "url": "", "page_title": "", "shot_rev": 0,
            "awaiting_login": False, "created": time.time(),
            "trace": _current_trace(),     # V2-044: la tarea nace del contexto de la frase (o de la sesión adoptada)
        }
    return tid


def ensure(task_id: str, goal: str = "", title: str = "") -> str:
    """Crea la tarea con un id FIJO si no existe, o la reutiliza (para tarjetas SINGLETON como la de navegación a
    mano: una sola tarjeta reutilizada en vez de una nueva por cada open/search → no proliferan widgets)."""
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
        # Recorta las CLÁUSULAS que hablan de OTRA tarea ("sin parar la tarea de motos", "sin cerrar la de X",
        # "aparte de la búsqueda de Y", "además de lo de Z") — su sujeto es de OTRA tarea y contaminaba el matching
        # (bug 2026-07-13: "cara de perro SIN PARAR la tarea de motos" casaba con la moto por la palabra "motos").
        _COEXIST_RE = _re.compile(
            r"\b(sin (parar|detener|cerrar|tocar|cancelar)|aparte de|adem[aá]s de|dejando|manteniendo)\b.*$",
            _re.I)
    s = _COEXIST_RE.sub("", (s or "").lower())
    return {w for w in _re.split(r"[^0-9a-záéíóúñ]+", s) if len(w) > 2}


# Palabras que NO identifican el SUJETO de la búsqueda: relleno + verbos de buscar + NOMBRES DE MARKETPLACE (dos
# búsquedas distintas —una moto, un sofá— comparten "wallapop" pero NO son el mismo tema) + stopwords. El sujeto
# real (moto/enduro/coche/piso/sofá…) es lo que ancla "es la MISMA búsqueda". Así una aclaración corta ("no, de
# enduro") sigue anclada a la moto por la palabra "moto", pero "moto" y "piso" nunca se fusionan.
_STOP = {
    # verbos/relleno de búsqueda
    "buscar", "busca", "busque", "busques", "buscame", "buscando", "mostrar", "muestra", "dame", "encuentra",
    "encuentrame", "resultados", "segunda", "mano", "venta", "vender", "comprar", "quiero", "quiere", "necesito",
    "operador", "abrir", "abre", "navegador", "web", "pagina", "página", "internet", "mejores", "opciones",
    "candidatas", "anteriores", "rechaza", "cerca", "tarea", "tareas", "ventana", "ventanas", "pestaña", "pestana",
    "pestañas", "pestanas", "busqueda", "búsqueda",
    # marketplaces (el CANAL, no el sujeto)
    "wallapop", "milanuncios", "idealista", "amazon", "ebay", "aliexpress", "fotocasa", "vibbo",
    # stopwords castellano frecuentes
    "una", "uno", "unos", "unas", "los", "las", "del", "para", "con", "por", "que", "eso", "esa", "ese", "esta",
    "este", "esto", "más", "mas", "muy", "dos", "tres", "todo", "toda", "todas", "todos", "sus", "porque", "son",
    "como", "pero", "the", "and", "for",
}


def _stem(w: str) -> str:
    """Singularización tosca (sin dependencias): moto/motos, coche/coches → misma raíz. Solo quita una 's' final en
    palabras largas (len>4) → no toca "los"/"las" ni "moto"."""
    return w[:-1] if len(w) > 4 and w.endswith("s") else w


_STOP_STEMMED = {_stem(w) for w in _STOP}


def _similar(g: set, other_goal: str) -> bool:
    """True si el set de palabras `g` y el objetivo `other_goal` son la MISMA búsqueda. Ancla en el SUJETO común
    (raíces len≥4, no stopword/marketplace). Para NO fusionar temas distintos por una mención incidental (bug
    2026-07-13: "cara de perro sin parar la tarea de motos" casaba con la moto por "motos"), el anclaje de UNA sola
    palabra solo vale para ACLARACIONES CORTAS (`g` ≤3 palabras de contenido, p.ej. "no, de enduro"); una petición
    con cuerpo exige ≥2 sujetos compartidos o Jaccard ≥0.4. Dos temas distintos (moto vs piso, moto vs perro) no
    casan."""
    gs = {_stem(w) for w in g}
    os_ = {_stem(w) for w in _words(other_goal)}
    if not gs or not os_:
        return False
    shared = gs & os_
    subject = {w for w in shared if len(w) >= 4 and w not in _STOP_STEMMED}   # sujeto(s) común (moto, enduro, coche…)
    # aclaración CORTA → basta 1 sujeto (mantiene "no, de enduro" anclado a la moto); petición con cuerpo → ≥2.
    # "Corta" se mide en palabras de CONTENIDO (como dice el contrato de arriba), NO en palabras totales: "no,
    # quiero una moto de enduro 300" está llena de relleno pero su contenido son 2 palabras — es una aclaración.
    content = {w for w in gs if len(w) >= 4 and w not in _STOP_STEMMED}
    if subject and (len(content) <= 3 or len(subject) >= 2):
        return True
    union = len(gs | os_)
    return (len(shared) / union if union else 0) >= 0.4


# Una tarea de navegador ACTIVA es "lo que estamos haciendo AHORA MISMO": mientras viva, cualquier petición
# parecida se enruta a ELLA — nunca se abre un SEGUNDO navegador para lo mismo (control de estado, 2026-07-12).
# El único límite es un guard anti-ZOMBIE: una tarea colgada más de _ZOMBIE_MAX no debe bloquear búsquedas nuevas
# para siempre. Antes la dedup solo miraba los primeros 45-90 s DESDE LA CREACIÓN → una tarea larga (los
# marketplaces tardan MINUTOS) dejaba de estar protegida y un refinamiento tardío ("sube el precio", "analízalas")
# spawneaba un navegador GEMELO haciendo la misma búsqueda (bug de la sesión del 2026-07-12: una sola búsqueda de
# moto acabó abriendo t1 + t2 en paralelo).
_ZOMBIE_MAX = 1800.0   # s (30 min): por encima, una tarea "activa" se considera colgada y ya no deduplica.


def similar_active(goal: str, within: float = _ZOMBIE_MAX) -> str | None:
    """Id de una tarea ACTIVA (queued/working/needs_input) cuyo objetivo se PARECE mucho a `goal` — para que una
    MISMA búsqueda NO abra un SEGUNDO navegador aunque el operador la refine turnos —o MINUTOS— después, mientras
    el navegador sigue trabajando. Una tarea activa deduplica durante TODA su vida (hasta `within`, solo guard
    anti-zombie). Devuelve None si no hay parecida (dos tareas distintas —moto vs piso— NO se fusionan)."""
    g = _words(goal)
    if not g:
        return None
    now = time.time()
    with _lock:
        for tid, t in _tasks.items():
            if t.get("status") not in ("queued", "working", "needs_input"):
                continue
            if now - t.get("created", 0) > within:   # guard anti-zombie (tarea colgada); NO una ventana de dedup
                continue
            if _similar(g, t.get("goal", "")):
                return tid
    return None


# CONTINUIDAD: una tarea recién TERMINADA sigue siendo "la búsqueda de la que hablamos" durante esta ventana → un
# follow-up del mismo tema la RE-LANZA en su MISMA tarjeta (no abre un segundo navegador). Fuera de la ventana, un
# "otra vez lo de la moto" ya es una búsqueda nueva.
_CONTINUATION_MAX = 600.0   # s (10 min)


def find_continuation(goal: str) -> tuple[str, str] | None:
    """(tid, status) de la tarea que este `goal` CONTINÚA — para que las ACLARACIONES del operador MODIFIQUEN la
    tarea en curso en vez de abrir otro navegador:
      · una tarea ACTIVA parecida  → se refina EN MARCHA (el bucle re-lee el objetivo);
      · una recién TERMINADA parecida (≤_CONTINUATION_MAX) → se RE-LANZA en su misma tarjeta.
    Prioriza la activa; si no, la terminada más reciente. None si no hay ninguna del mismo tema (moto vs piso no
    casan). Es el CONTROL DE ESTADO: "cuando busco una moto y digo «no, enduro», modifica la tarea, no abras otra"."""
    g = _words(goal)
    if not g:
        return None
    now = time.time()
    with _lock:
        for tid, t in _tasks.items():   # 1) activa (prioridad) → refinar en marcha
            if t.get("status") in ("queued", "working", "needs_input") \
                    and now - t.get("created", 0) <= _ZOMBIE_MAX and _similar(g, t.get("goal", "")):
                return (tid, t["status"])
        best = None                     # 2) recién terminada → re-lanzar en su tarjeta (la más reciente)
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
    """(id, objetivo) de las tareas ACTIVAS ahora — para que el ESTADO del cerebro diga EXPLÍCITAMENTE qué está en
    curso (no solo "hay N tareas") y no relance una búsqueda que ya corre. Las más recientes primero."""
    with _lock:
        act = [(tid, (t.get("goal") or "").strip())
               for tid, t in _tasks.items() if t.get("status") in ("queued", "working", "needs_input")]
    return list(reversed(act))[:max(1, limit)]


def active_ids() -> list[str]:
    """Tareas que aún no terminaron (para enrutar respuestas / cancelar / listar)."""
    with _lock:
        return [tid for tid, t in _tasks.items() if t["status"] in ("queued", "working", "needs_input")]


def waiting_id() -> str | None:
    """La tarea que espera una respuesta del operador (la más reciente si hay varias)."""
    with _lock:
        w = [tid for tid, t in _tasks.items() if t["status"] == "needs_input"]
        return w[-1] if w else None


def login_waiting_id() -> str | None:
    """La tarea que espera a que el operador INICIE SESIÓN en la ventana visible (awaiting_login). La más reciente
    si hay varias. Sirve para enrutar el 'ya estoy dentro' por voz al auth_done de esa tarea."""
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
    _notify(task_id)


def set_phase(task_id: str, phase: str, active: bool = True) -> None:
    """FASE del proceso (lo que el operador quiere ver, no cada clic): 'buscando…', 'recopilando resultados',
    'investigando los mejores', 'listo'. `active`=True → spinner en la tarjeta. Refresca la tarjeta."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["phase"] = str(phase or "")
        t["phase_active"] = bool(active)
    _notify(task_id)


def set_login_wait(task_id: str, on: bool) -> None:
    """La tarjeta espera a que el operador inicie sesión en la ventana visible (muestra un botón 'ya entré')."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["awaiting_login"] = bool(on)
    _notify(task_id)


def milestone(task_id: str, text: str) -> None:
    """Un HITO del proceso (p.ej. '34 anuncios encontrados', 'analizando 10 finalistas') — NO cada acción de
    navegador.

    Va a DOS sitios (2026-08-10): al feed de la tarjeta (que es efímero, en memoria, y muere con la tarea) y al
    registro de eventos, que es lo que se puede auditar después. Antes solo iba a la tarjeta: los hitos que
    cuentan lo que la tarea ENCONTRÓ y lo que DESCARTÓ —justo la evidencia de si la búsqueda trajo lo pedido—
    desaparecían al cerrarla. Ahora quedan, con el trace de la frase que pidió la tarea y el `span` del actor."""
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
            t["finished"] = time.time()   # marca la ventana de CONTINUIDAD (find_continuation)
    _notify(task_id)


def set_goal(task_id: str, goal: str) -> None:
    """Actualiza el OBJETIVO de una tarea (las aclaraciones del operador lo MODIFICAN). El bucle del automatizador
    re-lee el objetivo cada paso (agent.run_task) → una aclaración sobre una tarea VIVA cambia lo que busca sin
    abrir otro navegador. No toca el título (la tarjeta conserva su nombre)."""
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
    """Fija la ESENCIA sintetizada del objetivo (objetivo + criterios, comprimido por LLM) para MOSTRAR en la
    tarjeta — el `goal` completo se conserva intacto como texto operativo que guía la búsqueda. Best-effort: si la
    síntesis falla, la tarjeta cae al `goal` crudo."""
    summary = (summary or "").strip()
    if not summary:
        return
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["goal_summary"] = summary[:200]
        t["title"] = summary[:60]   # el título de la tarjeta también usa la esencia (antes truncaba el crudo)
    _notify(task_id)


def set_results(task_id: str, results) -> None:
    """`results` estructurados (p.ej. {"conclusion": "...", "items": [{title,subtitle,price,url,image}]})."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["results"] = results
    _notify(task_id)


def update_view(task_id: str, url: str = "", page_title: str = "", shot_rev: int | None = None) -> None:
    """El navegador de esta tarea cambió de vista (nueva captura) → refresca su tarjeta."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        if url:
            t["url"] = url
        if page_title:
            t["page_title"] = page_title
        if shot_rev is not None:
            t["shot_rev"] = shot_rev
    _notify(task_id)


def ask(task_id: str, question: str) -> None:
    """La tarea necesita un dato del operador → estado needs_input + pregunta (sale en su feed y por voz)."""
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t["question"] = str(question or "").strip()
        t["answer"] = ""
        t["status"] = "needs_input"
    add_event(task_id, f"❓ {question}")


def answer(task_id: str, text: str) -> None:
    """El operador respondió a la pregunta de esta tarea → el bucle lo recogerá (poll de `answer`)."""
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
    """El bucle consume la respuesta pendiente (una sola vez)."""
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
    """Cierra la tarea (done|failed) y deja el resumen en el feed."""
    if summary:
        add_event(task_id, summary)
    set_status(task_id, status if status in ("done", "failed") else "done")
