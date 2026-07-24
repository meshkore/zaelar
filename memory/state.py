"""memory/state.py — la tabla FIJA de estado (V2-002 · T48).

El **estado** es la capa que se inyecta SIEMPRE en el prompt, **sin búsqueda** (lectura de una fila única →
µs): nombres (nuestro y del operador), idioma (castellano por defecto), reglas de trato (directo vs elaborado),
ubicación, tareas/mensajes recientes, temas hablados. Es el "lo de hace dos horas está prácticamente en
contexto".

Lo LEE el compositor en cada prompt (directo, hot path). Lo ESCRIBEN el agente de memoria del SlowBrain y el
consolidador (fuera del camino crítico). `read()` nunca toca el índice ni hace búsqueda: un solo `SELECT` por
PK. `patch()` hace merge superficial (no pierdes campos al actualizar uno). Persistido como JSON en la única
fila `state(id=1)`.
"""
import json

from . import db as _db

# Estado por defecto: castellano, sin datos personales todavía (los siembra el agente de memoria / V2-003).
_DEFAULT: dict = {
    "assistant_name": "Zaelar",
    "operator_name": None,
    "language": "es",
    # MISIÓN/identidad de zaelar (sección A del ESTADO compuesto, `memory.compose_state`). VIVE en la memoria:
    # se SIEMBRA al arrancar desde el catálogo de idioma (`langs.LangSpec.mission`, en el idioma del operador) por
    # `nucleo/flash/memory_cache.prime()`; nunca se hardcodea en un prompt inglés. None = aún sin sembrar (compose
    # cae al texto de `langs`). Es la parte FIJA del prompt que comparten los dos cerebros.
    "mission": None,
    "treatment": None,        # p.ej. "directo, sin narrar" | "elaborado"
    # USER RULES (V2-046 A1): reglas de comportamiento que el OPERADOR impone hablando ("sé más directo",
    # "responde solo sí o no", "cuando te pida una acción hazla sin responder"). El agente NACE EN BLANCO de
    # user rules y cada usuario lo personaliza; PERSISTEN entre sesiones (≠ la directiva de sesión, que muere al
    # reconectar). Lista corta de frases imperativas (cap ~8, dedup, la más reciente manda) — la escribe el
    # provider al reconocer una regla (tool set_style_directive) vía memory.add_user_rule; la lee compose_state §B.
    # Es la capa APRENDIDA frente a las BRAIN RULES (genética primigenia hardcodeada). Ver V2-046-sistema-arena.
    "rules": [],
    "location": None,
    "recent": [],             # tareas/mensajes recientes (lista corta)
    "topics": [],             # temas hablados recientemente
    # ── CONTEXTO DE UI VIVO (la parte más volátil del ESTADO) ────────────────────────────────────────────
    # "lo que el operador tiene DELANTE ahora mismo": qué widgets están abiertos en el canvas y qué está
    # haciendo el SlowBrain. Viaja SIEMPRE en el prompt (memory_cache) para que el cerebro resuelva "modifica
    # el widget de X" sin preguntar (si está abierto/es único). Lo escribe el frontend (autoritativo del canvas,
    # POST /api/canvas/state) y el dispatcher (tareas en marcha); visible en el mapa de la memoria.
    "open_widgets": [],       # ids de widgets ABIERTOS ahora en la pantalla del operador
    "activity": [],           # tareas del SlowBrain EN MARCHA ahora (etiquetas cortas)
    "sessions": [],           # V2-036: sesiones de trabajo VIVAS del SlowBrain [{id,goal,phase}] — el orquestador
    #                           las conoce para situarse y dirigirles follow-ups; el FlashBrain las cuenta al operador.
    "rails": [],              # V2-042: RUNS vivos de los RAILS del FlashBrain [{kind,label,status,detail,attempts}]
    #                           — comportamientos conducidos que cruzan turnos (búsqueda de canción difusa, música
    #                           sonando, fallos AISLADOS sin_resolver…). Los proyecta nucleo/rails.py.
    # REGLAS DE SEGURIDAD/CONFIG (V2-060) — 2ª clase de user rules, DURAS: NO son estilo (las de `rules`, que guían
    # por prompt), sino CONFIGURACIÓN que se aplica DETERMINISTA en código y solo cambia por orden explícita o el ⚙.
    # `secrets_voice`: ¿puede zaelar leer un secreto en voz alta? True = modo cómodo (default, el operador lo dijo);
    # False = «no me digas los secretos por voz» → solo pantalla. No cuenta contra el cap de las rules de estilo.
    "security": {},
}


def read() -> dict:
    """Lee el estado (fila única). µs, sin búsqueda. Devuelve una copia de los defaults fusionada con lo guardado."""
    row = _db.get_db().query_one("SELECT data FROM state WHERE id=1")
    base = dict(_DEFAULT)
    if row is not None:
        try:
            base.update(json.loads(row["data"]))
        except Exception:
            pass
    return base


def write(data: dict) -> None:
    """Reemplaza el estado completo por `data` (fusiona sobre los defaults para no dejar huecos)."""
    merged = dict(_DEFAULT)
    merged.update(data or {})
    blob = json.dumps(merged, ensure_ascii=False)
    _db.get_db().execute(
        "INSERT INTO state (id, data) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
        (blob,),
    )


import threading

_patch_lock = threading.Lock()


def patch(fields: dict) -> dict:
    """Merge superficial: actualiza solo las claves de `fields`, conserva el resto. Devuelve el estado nuevo.
    Bajo lock propio (auditoría 2026-07-19 P2-7): read→merge→write sin transacción que lo abarque era una carrera
    RMW entre los 4 escritores concurrentes de estado (frontend/canvas, dispatch/sessions, rails, memory_agent) —
    last-write-wins podía perder `open_widgets` o `rails` del otro. El RLock de la BD serializa cada statement,
    no la secuencia; este lock serializa el ciclo completo."""
    with _patch_lock:
        cur = read()
        cur.update(fields or {})
        write(cur)
        return cur


# ── REGLAS DE SEGURIDAD/CONFIG (V2-060) — 2ª clase de user rules, DURAS ─────────────────────────────────────
def security_flag(key: str, default=False):
    """Lee una regla de seguridad/config (µs, directo). p.ej. security_flag('secrets_voice', True)."""
    try:
        return (read().get("security") or {}).get(key, default)
    except Exception:
        return default


def set_security_flag(key: str, value) -> None:
    """Fija una regla de seguridad/config (bajo el mismo lock que patch; merge en `security`)."""
    with _patch_lock:
        cur = read()
        sec = dict(cur.get("security") or {})
        sec[key] = value
        cur["security"] = sec
        write(cur)
