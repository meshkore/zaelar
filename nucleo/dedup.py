#
# dedup.py — «is this a NEW errand, or the one already running?», with the evidence it decided on.
#
# Carved out of `dispatch.py` (V2-507) when the architecture ratchet went red: the file was 1922 lines
# against a 1865 cap, and this is a self-contained question — two judges over text, no session lifecycle,
# no pool, no bus. Same precedent as `sheets.py`, `errand_kind.py` and `engine_url.py` before it.
#
# PURE over the live errands it is HANDED: `dispatch` owns `_SESSIONS` and resolves which of them are alive;
# this module never reaches into it. That is what lets the rule be tested without a pool, a backend or a loop.
#
import re

from nucleo import matching


def target_widget(request: str) -> str:
    """Widget EXISTENTE que la petición referencia ('' si ninguno) — clave de dedup para tareas de widget."""
    try:
        from nucleo.agentes import code as _code
        return _code._referenced_widget(request) or ""
    except Exception:
        return ""


def scan(request: str, kind: str, live: list[tuple[str, str]]) -> tuple[str | None, dict]:
    """El veredicto del dedup Y la evidencia sobre la que lo tomó, sobre los encargos VIVOS que se le pasan.

    DOS señales: (1) MISMO widget destino (tareas de código sobre el mismo widget) → dedup fuerte;
    (2) CONTENCIÓN de palabras de contenido con el goal de una sesión viva. El dedup vive aquí y no en el
    snapshot de inicio de turno del provider de voz (que falló la sesión 2026-07-15: la re-escalada llegó en
    un turno ambiente por contaminación de ventana y `_similar_pending` no la vio).

    F4 (2026-08-23) — la vara es `matching.containment`, no Jaccard, y el porqué está medido: el cerebro
    REFORMULA el encargo en cada escalada (668/437/342/298 chars el mismo caso), Jaccard divide por la UNIÓN y
    una reformulación más larga se ve distinta *por ser más larga* — cuatro workers para un encargo el
    2026-08-21, Jaccard entre pares 0,319-0,450, todos bajo el 0,60 de entonces. La contención divide por el
    conjunto PEQUEÑO, que es la pregunta real («¿la versión corta está dentro de la larga?»), y separa sin
    solape (mismo encargo 0,571-0,893 · distintos 0,062-0,227). De propina neutraliza el recorte de
    `goal=request[:200]`: el lado truncado es el `min` por el que se divide, así que recortar el goal guardado
    apenas mueve la medida — con Jaccard lo hundía siempre.

    POR QUÉ LA EVIDENCIA VIAJA CON EL VEREDICTO (V2-507). Una respuesta negativa era muda: se devolvía None, y
    «ninguna sesión viva casó» se lee exactamente igual que «no había ninguna sesión viva contra la que
    casar». Piden arreglos OPUESTOS —una vara rota, o una sesión que murió al nacer— así que un informe que no
    las distingue manda a mirar el fichero equivocado.

    Medido el 2026-08-30, `cheapest-monitor__us` ronda 20260830-114302: dos hojas abiertas
    (`results::101c0f-1` a las 11:34:03, `-2` a las 11:34:22), UN solo worker arrancado (`task/start` de id=2;
    los 209 eventos task de la ventana llevan id=2) y ningún `task/dedup` en toda ella. Releyendo el log de
    eventos del sandbox seguía sin poder decidirse cuál de las dos había pasado. El arnés había tapado el
    hueco con un número propio —la contención entre los dos goals que ÉL vio—, pero ese es un par DISTINTO
    del que compara esta función (la petición entrante contra el goal truncado de una sesión viva), así que
    su 1,0 tampoco podía falsar la decisión del motor. Una acusación que no se puede falsar es peor que el
    defecto que nombra.

    La evidencia la produce el bucle que DECIDE, nunca se recalcula al lado: una segunda copia de una regla
    deriva, y entonces la fila reporta un número que el código no usó — justo la confusión que esto quita."""
    ev: dict = {"live": len(live), "best": 0.0, "against": "", "bar": float(matching.SAME_ERRAND), "by": ""}
    req_w = matching.content_words(request)
    if not req_w:
        return None, ev
    tgt = target_widget(request) if kind in ("code", "generic") else ""
    for k, goal in live:
        if tgt and target_widget(goal) == tgt:
            ev.update(best=1.0, against=k, by="widget")
            return k, ev
        c = matching.containment(req_w, matching.content_words(goal))
        # `or not ev["against"]`: una contención de exactamente 0.0 sigue siendo una comparación que OCURRIÓ,
        # y dejar `against` vacío ahí diría «no casé con nadie» cuando la verdad es «casé con éste y sacó
        # cero» — el mismo silencio que esta fila existe para romper, un campo más adentro.
        if c > ev["best"] or not ev["against"]:
            ev.update(best=round(c, 3), against=k)
        if c >= matching.SAME_ERRAND:
            ev["by"] = "containment"
            return k, ev
    return None, ev


SCOPE_SYSTEM = (
    "Decides ONE thing about an assistant's background work: the operator has errands ALREADY RUNNING, and a "
    "new request just arrived. Is it a SEPARATE errand, or is it ABOUT one of the running ones?\n\n"
    "ABOUT a running one (answer its number): asking how it is going, whether there is anything yet, telling it "
    "to hurry, thanking, acknowledging, adding a detail or a correction to it, narrowing or widening it, asking "
    "it to try another site — anything the running errand's own worker could act on.\n"
    "SEPARATE (answer 0): a different thing to find, book, build or investigate — even in the same domain. "
    "Looking for a guitar and looking for a camera are two errands.\n\n"
    'Reply ONLY with JSON: {"about": <number of the running errand, or 0>}. Nothing else.\n'
    "If you cannot tell, answer 0."
)


def about_a_live_errand(request: str, live: list[tuple[str, str]]) -> str:
    """The tid of the live errand this request is ABOUT, or "" when it is a genuinely NEW one.

    THE SECOND HALF OF THE DEDUP, and the one `find_duplicate` structurally cannot do. That one answers «is
    this a reformulation of the same request», by containment over content words, and it is right to: it was
    built for a brain that rewrites the errand every time it escalates. What it cannot see is a turn that is
    not a request at all. Measured 2026-08-24, goals straight out of the lab's durable log — ONE guitar
    search:

        16:14:30  web       «Busca en marketplaces de segunda mano … una guitarra acústica…»   <- the errand
        16:15:48  research  «¿Alguna novedad ya?»                                              <- a worker
        16:16:20  research  «Perfecto, dale. ¿Tienes algo ya?»                                 <- another

    Four cards on the operator's screen for one errand, three workers competing for the same turn, and a
    fourth-case worker reporting on «the four searches» because its own errand WAS a follow-up question.
    Containment reads 0 between «¿alguna novedad?» and «busca una guitarra» — correctly. There is no word
    list that fixes this either: the ways of asking how something is going are unbounded, and a list would
    be the hardcoding this codebase keeps paying for. So a MODEL judges it, exactly like V2-075's
    conversational-health criterion, and for the same reason.

    Runs ONLY with something already live, which is what keeps it cheap: the first errand of a conversation —
    the common case — never pays for it. It is off the voice turn (the dispatcher already answered) though
    still in front of a worker the operator is waiting on, hence the direct reasoning-OFF endpoint.

    FAIL-OPEN, and the direction is deliberate: anything unreadable answers "" and the errand spawns, which is
    exactly today's conduct. Refusing to spawn on a failed model call would silently swallow real errands —
    an operator whose request vanished has no way to even see what happened, while a spurious extra worker is
    visible on screen, which is how this defect got found in the first place.
    """
    if not request.strip() or not live:
        return ""
    menu = "\n".join(f"{i + 1}. {str(goal or '')[:160]}" for i, (_tid, goal) in enumerate(live))
    try:
        from nucleo import memllm
        raw = memllm.chat_sync("errand_scope", SCOPE_SYSTEM,
                               f"RUNNING ERRANDS:\n{menu}\n\nNEW REQUEST:\n{request[:400]}",
                               max_tokens=32, temperature=0.0, timeout=12.0)
    except Exception:  # noqa: BLE001
        return ""
    if not raw:
        return ""
    m = re.search(r'"about"\s*:\s*(\d+)', raw)
    if not m:
        return ""
    n = int(m.group(1))
    # Out of range is NOT "the last one": a number nobody offered is a model that did not answer the question,
    # and picking a neighbour would attach the operator's request to an errand chosen at random.
    return live[n - 1][0] if 1 <= n <= len(live) else ""
