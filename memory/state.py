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

# Default state: no personal data yet (the memory agent seeds it / V2-003), and ENGLISH.
#
# This is the FOURTH place the language bootstrap contract lives, and it was the one out of step. The other
# three — `langs.DEFAULT_LANG`, the frontend's `store.lang()`, and the engine settings — all say "en"; this one
# said "es", and it is the field the memory CORAZÓN reads to decide the canonical language it distils pills in
# (`mem_processor._render`). So a brand-new account, before the operator had said a single word, was already
# committed to writing their memory in Spanish. The product opens in English and switches to the operator's real
# language on their first sentence; the memory has to start from the same place as everything else.
_DEFAULT: dict = {
    "assistant_name": "Zaelar",
    "operator_name": None,
    # None = NOT YET CHOSEN, the same convention `mission`/`operator_name`/`location` already use here. It used to
    # be the literal "en", and that literal was a PIN nothing could move: no code in the tree ever writes this
    # field (the i18n lock persists `settings.stt_language`, not the state), and a non-empty value means the two
    # consumers that were written to fall back to the active language — `mem_processor._render` and
    # `memllm` — can never reach their fallback. Measured 2026-08-20 in the use_cases sandboxes: `ZAELAR_LANGUAGE=es`,
    # the i18n detect logging «text channel locked operator language -> 'es'», the whole conversation in Spanish,
    # and every pill distilled into ENGLISH because this said so. It even made a real finding look false — the
    # tester grepped the Spanish word for a datum that was in the prompt in English.
    # Resolved at READ time (see `read`), so it reports the language the operator actually has configured instead
    # of a guess, which is what the "linguistic start-up" decision of 2026-07-10 asked for in the first place: the
    # memory starts where everything else starts. What that decision was against is a HARDCODED "es"; "en" turned
    # out to be the same mistake mirrored.
    "language": None,
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
    # MRU de widgets USADOS hace poco (V2-078): la SEGUNDA capa de acotación de "¿a qué widget se refiere?" — los
    # abiertos mandan (están DELANTE), luego los usados hace poco, y solo si no casa ahí se recurre al catálogo
    # completo (salvo nombre inequívoco). Se estampa cuando un widget PASA a abierto (server/voice_api.py::canvas_state,
    # único choke point del canvas) y PERSISTE tras cerrarse — por eso es distinto de open_widgets. Lista corta MRU
    # (dedup, la más reciente primero, cap ~6). Idea del operador: con 100 widgets pero 3 recién usados, casi seguro
    # se refiere a esos → menos ambigüedad sin hardcodear frases por widget.
    "recent_widgets": [],     # ids de widgets usados hace poco (MRU, dedup, cap ~6), aunque ya no estén abiertos
    # CATÁLOGO de NOMBRES + ALIAS (V2-082): proyección de VISIBILIDAD del registro unificado (widgets de usuario +
    # superficies de sistema), [{id,name,aliases,surface}]. NO es fuente de verdad (la identidad vive en el manifest
    # de cada widget y en system-surfaces.js) — es un espejo para que el operador VEA en el estado qué se puede abrir
    # y con qué alias. Lo regenera widgets/registry.refresh_state() tras un cambio de catálogo/alias y al arrancar.
    "widget_registry": [],

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
    if not base.get("language"):
        base["language"] = _active_language()
    return base


def _active_language() -> str:
    """The language the operator ACTUALLY has configured (⚙ / `ZAELAR_LANGUAGE`), for a state that has not been
    told one yet. Best-effort and env-only (`langs.current_code` reads no disk), so it is safe on the per-turn read
    path; falls back to English exactly as the frozen default used to.

    NOTE ON WHAT GETS PERSISTED: `patch()` is read→merge→write, so the first patch after this resolution STAMPS the
    then-active language into the row. That is deliberate and is the "learn it once, then keep it" behaviour the
    2026-07-10 decision described — a memory whose canonical language flip-flops with an env var would be worse
    than one that is briefly wrong. It also means an install that already stamped "en" while its operator speaks
    another language KEEPS it: an explicit stored value is indistinguishable from a real choice, and silently
    rewriting a persisted user field is a worse bug than the one this fixes."""
    try:
        from voice.engine.core import langs
        return langs.current_code()
    except Exception:  # noqa: BLE001
        return "en"


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


# ── CATÁLOGO de nombres + alias (V2-082) ────────────────────────────────────────────────────────────────────
# TECHO DURO de la proyección (V2-085). `widget_registry` es O(N) sobre el catálogo, y el ESTADO es material que
# viaja: se compone en el prompt (`compose_state`), se serializa en snapshots y se devuelve en respuestas de API.
# Hoy `compose_state()` NO lo incluye — pero "hoy no" no es una garantía, y un catálogo de 10.000 widgets colado
# en un prompt por un cambio futuro sería un incidente caro y silencioso. El cap lo hace IMPOSIBLE por
# construcción: la proyección es un espejo de VISIBILIDAD, no el inventario. El inventario completo se consulta
# donde vive — `GET /widgets` (índice) y `runtime.identify()` (resolución) — que sí trabajan con los N reales.
_REGISTRY_CAP = 200


def set_widget_registry(rows) -> list:
    """Escribe la proyección de VISIBILIDAD del registro de widgets/superficies (id/name/aliases/surface). Best-effort,
    bajo el mismo lock que `patch`. No es fuente de verdad — la regenera widgets/registry.refresh_state().
    ACOTADA a `_REGISTRY_CAP` filas: por encima de eso se guarda el prefijo + un marcador `_truncated` con el total
    real, para que quien lea el estado sepa que está viendo un extracto y no crea que ese es todo el catálogo."""
    rows = list(rows or [])
    if len(rows) > _REGISTRY_CAP:
        rows = rows[:_REGISTRY_CAP] + [{"_truncated": True, "total": len(rows), "shown": _REGISTRY_CAP,
                                        "hint": "catálogo completo en GET /widgets"}]
    with _patch_lock:
        cur = read()
        cur["widget_registry"] = rows
        write(cur)
        return rows


# ── MRU de widgets usados hace poco (V2-078) ────────────────────────────────────────────────────────────────
_RECENT_CAP = 6


def push_recent_widgets(ids, cap: int = _RECENT_CAP) -> list:
    """Estampa uno o más widgets como USADOS AHORA en el MRU `recent_widgets` (dedup, la más reciente primero,
    cap corto). Bajo el mismo lock que `patch` (es un RMW más del estado). `ids` = id(s) base, normalizados a
    minúsculas y sin sufijo de instancia (navegador::t1 → navegador). Best-effort: ids vacíos se ignoran.
    Devuelve la lista MRU resultante. Lo llama el único choke point del canvas (canvas_state) cuando un widget
    pasa a ABIERTO — así "reciente" persiste aunque luego se cierre (≠ open_widgets)."""
    if isinstance(ids, str):
        ids = [ids]
    fresh = []
    for w in (ids or []):
        b = str(w or "").split("::", 1)[0].strip().lower()
        if b and b not in fresh:
            fresh.append(b)
    if not fresh:
        return read().get("recent_widgets") or []
    with _patch_lock:
        cur = read()
        prev = [str(w).strip().lower() for w in (cur.get("recent_widgets") or []) if str(w).strip()]
        # MRU: los nuevos delante (en el orden dado), luego los previos que no repitan, recorta al cap.
        merged = fresh + [w for w in prev if w not in fresh]
        merged = merged[:max(1, int(cap))]
        cur["recent_widgets"] = merged
        write(cur)
        return merged
