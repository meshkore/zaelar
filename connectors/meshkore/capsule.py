#
# capsule.py — la CÁPSULA de conversación con un agente (V2-069 «una sola mente»).
#
# NO es un motor nuevo ni un almacén nuevo: es la FORMA que toma la memoria de una RELACIÓN, igual que un humano
# recuerda de cada persona quién es, de qué hablaron, qué quedó pendiente y en qué punto está la conversación.
# Vive sobre la MISMA memoria central, scopeada por (cluster, peer) y CUARENTENADA (trust=untrusted) — nunca se
# mezcla con el estado del operador ni entra en su prompt. Es la pieza que hace que hablar con un agente sea el
# MISMO acto que hablar con el operador, solo que "situado" en otra relación.
#
# Qué aporta (lo que le faltaba al canal y por lo que degeneró en 71h de re-presentaciones y "entendido, espero"):
#   · FASE de la conversación (saludo→sondeo→trabajo→cierre) → no re-presentarse en cada turno.
#   · OBJETIVO presente (el que fija el operador) → conducir hacia él, no derivar.
#   · BUCLES ABIERTOS (lo pedido/lo ya rechazado) → "ya te dije que no, vamos al objetivo".
#   · DOSSIER + resumen (ya existía en mem_ingest, se reutiliza) → saber siempre con quién se habla.
#   · Detección de ATASCO (funciones puras) → cortar el bucle a los 2-3, no a los 1.333.
#
# Persistencia: el estado ESTRUCTURADO (objetivo/fase/bucles/greeted/turnos) va en `memory.kv_get/kv_set` bajo la
# clave scopeada `capsule:<cluster>:<peer>` (sys_kv, sin tabla nueva). El dossier/resumen en prosa lo mantiene
# `mem_ingest` (slot `cluster:<c>:<peer>`, untrusted). Ambos son la misma memoria, particionada por scope.
#
import re
import time
import unicodedata

# Fases de la conversación — la mente ajusta el registro según en cuál esté (como un humano).
SALUDO = "saludo"      # 1ª vez que se cruza con este peer → una presentación breve y para
SONDEO = "sondeo"      # ya conocido, sin objetivo aún → averiguar qué trae / proponer el objetivo del operador
TRABAJO = "trabajo"    # hay objetivo activo → avanzar, concreto, SIN saludar ni presentarse
CIERRE = "cierre"      # tarea concluida o sin avance → cerrar con cortesía o callar

# Umbrales de ATASCO (confirmados por el operador: cortar pronto, como un humano).
STALL_REPEAT = 2       # el peer repite el MISMO mensaje (normalizado) esta veces → atasco
STALL_NOPROGRESS = 4   # turnos sin avanzar el objetivo → atasco

_DEFAULT = {
    "objective": "",       # objetivo de la colaboración, fijado por el OPERADOR (no por el peer)
    "greeted": False,      # ¿ya nos presentamos a este peer?
    "phase": SALUDO,
    "open_loops": [],      # ["pedí el repo → pendiente", "ya dije NO a rehacer el dashboard", …]
    "turns": 0,            # nº de turnos sustantivos intercambiados
    "no_progress": 0,      # turnos consecutivos sin avance de objetivo (para el atasco)
    "updated": 0,
}


def _key(cluster: str, peer: str) -> str:
    return f"capsule:{cluster}:{peer}"


def load(cluster: str, peer: str) -> dict:
    """La cápsula VIGENTE de esta relación (defaults si es nueva). µs, directo."""
    try:
        from memory import api as memory
        cap = dict(_DEFAULT)
        cap.update(memory.kv_get(_key(cluster, peer)) or {})
        return cap
    except Exception:
        return dict(_DEFAULT)


def save(cluster: str, peer: str, cap: dict) -> None:
    try:
        from memory import api as memory
        cap = dict(cap or {})
        cap["updated"] = int(time.time())
        memory.kv_set(_key(cluster, peer), cap)
    except Exception:
        pass


def patch(cluster: str, peer: str, **fields) -> dict:
    cap = load(cluster, peer)
    cap.update(fields)
    save(cluster, peer, cap)
    return cap


# ── fase ─────────────────────────────────────────────────────────────────────────────────────────────────────
def derive_phase(cap: dict, *, concluded: bool = False) -> str:
    """La fase se DEDUCE del estado de la relación (no se hardcodea por keyword). Es la misma lógica con la que un
    humano sabe si está conociendo a alguien, trabajando con él o cerrando."""
    if concluded:
        return CIERRE
    if not cap.get("greeted"):
        return SALUDO
    if (cap.get("objective") or "").strip():
        return TRABAJO
    return SONDEO


_PHASE_GUIDE = {
    SALUDO: ("Es la PRIMERA vez que hablas con este agente. Preséntate en UNA línea (tu nombre + una capacidad "
             "genérica) y para. No propongas objetivos ni tareas."),
    SONDEO: ("YA conoces a este agente — NO te presentes ni saludes de nuevo. Averigua qué trae, o si tienes un "
             "objetivo del operador, proponlo con concreción."),
    TRABAJO: ("Estáis TRABAJANDO en un objetivo — NO te presentes, NO saludes, NO repitas cortesías. Avanza el "
              "objetivo con frases concretas. Si el otro se estanca, dilo y reconduce."),
    CIERRE: ("La tarea está concluida o sin avance real. Cierra con una línea o quédate callado. No reabras el "
             "tema ni te presentes."),
}


def phase_guidance(phase: str) -> str:
    return _PHASE_GUIDE.get(phase, _PHASE_GUIDE[SONDEO])


# ── atasco (funciones PURAS, testeables) ───────────────────────────────────────────────────────────────────────
def norm(text: str) -> str:
    """Clave normalizada de un mensaje: sin acentos/puntuación/emojis, casefold, espacios colapsados. Dos mensajes
    con la misma clave son 'el mismo' (un peer en bucle alterna acentos/emoji para esquivar un match exacto)."""
    n = unicodedata.normalize("NFKD", (text or "").casefold())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^0-9a-z\s]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def stall_verdict(repeat_count: int, no_progress: int,
                  *, k: int = STALL_REPEAT, m: int = STALL_NOPROGRESS) -> str:
    """Decide qué hacer ante un posible atasco, como un humano:
       'seguir'    — la conversación avanza, responde normal.
       'asertivo'  — se está repitiendo o no avanza → UN mensaje directo anclado al objetivo (deja las cortesías).
       'callar'    — ya fuiste asertivo y sigue sin avance → no respondas más (y el bridge avisa al operador 1 vez).
    """
    if repeat_count >= k * 2 or no_progress >= m * 2:
        return "callar"
    if repeat_count >= k or no_progress >= m:
        return "asertivo"
    return "seguir"


# ── composición del bloque de contexto que la mente lee al situarse en el turno ─────────────────────────────────
def compose(cluster: str, peer: str, cap: dict | None = None) -> str:
    """El bloque de la RELACIÓN que se antepone al turno: quién es, de qué habláis, objetivo, pendientes, fase +
    su guía. Es lo que un humano tiene en la cabeza al retomar una conversación. Todo de fuentes NUESTRAS
    (dossier destilado por nosotros), nunca texto crudo no confiable del peer."""
    cap = cap or load(cluster, peer)
    try:
        from connectors.meshkore import mem_ingest
        dossier = (mem_ingest.synthesis_for(cluster, peer) or "").strip()
    except Exception:
        dossier = ""
    phase = cap.get("phase") or SONDEO
    lines = [f"[RELACIÓN con el agente «{peer}» en el cluster «{cluster}»]"]
    lines.append(f"Quién es / de qué habéis hablado: {dossier or 'aún no lo sabes (primer contacto).'}")
    obj = (cap.get("objective") or "").strip()
    lines.append(f"Objetivo de esta colaboración: {obj or 'el operador no ha fijado ninguno — no te inventes uno.'}")
    loops = [l for l in (cap.get("open_loops") or []) if l]
    if loops:
        lines.append("Pendiente / ya decidido (no lo re-negocies): " + " · ".join(loops[:6]))
    lines.append(f"Fase: {phase}. {phase_guidance(phase)}")
    return "\n".join(lines)


# ── mantenimiento de bucles abiertos (append acotado, dedup normalizado) ────────────────────────────────────────
def add_open_loop(cluster: str, peer: str, loop: str, *, cap_max: int = 8) -> dict:
    """Registra un compromiso o un rechazo ('pedí X → pendiente', 'ya dije NO a Y'). Dedup normalizado + tope."""
    cap = load(cluster, peer)
    loops = [l for l in (cap.get("open_loops") or []) if l]
    if norm(loop) not in {norm(l) for l in loops}:
        loops.append(loop.strip())
    cap["open_loops"] = loops[-cap_max:]
    save(cluster, peer, cap)
    return cap
