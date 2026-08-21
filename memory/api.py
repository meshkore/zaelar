"""memory/api.py — FACHADA pública de la memoria central (V2-002 · T52).

Único punto de entrada para el resto de zaelar (FlashBrain, agente de memoria + workers headless, widgets, server).
Encaja con el transporte HÍBRIDO del sistema:

  - **async (cola)** — mutaciones NO urgentes: `write` · `reinforce` · `pin`/`unpin` · `link`. Entran por
    `memory/queue.py` (único escritor → cero colisiones); no bloquean la ruta caliente.
  - **directa (hot path · ms/µs)** — `query` (retriever) · `state` (tabla fija) · `load_episode` (lazy).

Cada mutación emite la señal **`memory.updated`** por el `bus/` (loop-agnóstico, best-effort) para que la UI u
otros suscriptores refresquen. `query()` compone el contexto mínimo = estado (SIEMPRE) + recuerdos relevantes
truncados al presupuesto de tokens, y encola el **refuerzo por uso** de los recuerdos usados (escritura async,
el acceso resetea el decay).

Ciclo de vida: `start()`/`stop()` arrancan/paran el consumidor de la cola en el loop del server (lo cablea
V2-003 en el lifespan). Sin `start()`, las escrituras se aplican en línea (standalone/tests) — nunca se pierden.
"""
import asyncio
import re

from . import consolidator as _consolidator
from . import db as _db  # noqa: F401  (asegura import del paquete; get_db perezoso)
from . import episodic as _episodic
from . import state as _state
from . import writer as _writer
from .queue import get_queue

# tokens ≈ caracteres / 4 (aproximación barata para truncar al presupuesto).
_CHARS_PER_TOKEN = 4
DEFAULT_BUDGET_TOKENS = 1200

# Contrato EXPLÍCITO de la fachada (audit de modularidad 2026-07-17): esto es lo público; el resto del repo no
# debe importar internals (memory.db/writer/queue/slots/…) fuera de tests.
__all__ = [
    "start", "stop",
    "write", "write_now", "ingest_message", "reinforce", "pin", "unpin", "link", "forget", "unforget",
    "state", "set_state", "compose_state", "add_user_rule", "remove_user_rule",
    "kv_get", "kv_set",
    "query", "recent_short", "recent_window", "recent_by_source", "by_concepts",
    "seconds_since_last_conv",
    "critical_facts", "salient_long", "map",
    "load_episode", "register_episode", "write_episode", "list_episodes", "migrate_inbox",
    "consolidate", "DEFAULT_BUDGET_TOKENS",
]

# Stopwords (artículos/preposiciones/POSESIVOS) que se ignoran al hacer olvido GRANULAR por tokens de contenido:
# el operador dice "olvida la matrícula de MI coche" pero el CORAZÓN guarda "matrícula de SU coche" → un LIKE
# contiguo falla por el posesivo. El fallback token-AND compara solo los tokens con contenido (matrícula, coche).
_FORGET_STOP = {
    "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas", "lo", "que", "te", "me", "se",
    "mi", "mis", "tu", "tus", "su", "sus", "nuestro", "vuestra", "esa", "ese", "eso", "esta", "este", "esto",
    "en", "con", "por", "para", "sobre", "como", "más", "muy", "ya", "no",
    "todo", "toda", "todos", "todas", "cosa", "cosas",   # "olvida TODO lo de X" = olvido AMPLIO de X
}


def _emit(topic: str, payload=None):
    try:
        import bus
        bus.emit_sync(topic, payload or {})
    except Exception:
        pass


# ── ciclo de vida de la cola ─────────────────────────────────────────────────────────────────────────────
async def start():
    """Arranca el consumidor único de la cola en el loop actual (server lifespan)."""
    await get_queue().start()


async def stop(drain: bool = True):
    await get_queue().stop(drain=drain)


# ── escrituras (async · cola) ────────────────────────────────────────────────────────────────────────────
def write(text: str, *, level: str = "short", kind: str = "event", importance: float | None = None,
          weight: float = 0.5, ttl_days: float | None = None, pinned: bool = False,
          slot: str | None = None, meta: dict | str | None = None,
          concepts: list[str] | None = None) -> None:
    """Encola un recuerdo (fire-and-forget). El embedding se calcula en el escritor. Emite memory.updated.

    PÍLDORA (V2-013): `slot` = clave canónica del hecho singular (`operator.name`…) → supersede/dedup EXACTO en el
    writer; `meta` = envoltorio JSON libre (entity/source/said_at…) para el visor y el grafo; `concepts` = 1-3
    etiquetas ligeras (salud/finanzas…) → el writer crea/enlaza nodos-concepto en el grafo (T126)."""
    get_queue().submit(
        "write", text, level=level, kind=kind, importance=importance,
        weight=weight, ttl_days=ttl_days, pinned=pinned, slot=slot, meta=meta, concepts=concepts,
    )
    _emit("memory.updated", {"op": "write", "kind": kind})


def write_now(text: str, **kwargs) -> int:
    """Escritura SÍNCRONA directa (para quien necesita el id ya: episódica, tests). Emite memory.updated."""
    mid = _writer.insert_memory(text, **kwargs)
    _emit("memory.updated", {"op": "write", "id": mid})
    return mid


def ingest_message(source: str, entity: str | None, text: str, *, group: str | None = None,
                   directed: bool = False, trust: str = "external", durable: bool = False,
                   importance: float | None = None, ttl_days: float | None = None,
                   concepts: list[str] | None = None, slot: str | None = None) -> None:
    """INGESTA TIPADA de un dato entrante de una FUENTE externa — la vía ÚNICA por la que TODO conector alimenta la
    memoria (V2-013 · multi-fuente 2026-07-10). Da igual 2 conectores que 200, o un peer de cluster («Zalo») que un
    chat de WhatsApp: todos entran por aquí con su `source` (whatsapp/telegram/cluster/agent/email…) y su `entity`
    (quién). El `source`/`entity` van INDEXADOS en `meta` (→ lectura directa por tipo con `recent_by_source`) **y**
    en el TEXTO (`[source] entity: body`) para que FTS/recall los encuentren sin trabajo extra. `trust`:
    'operator' (el dueño) · 'external' (un conector personal del dueño) · 'untrusted' (peer de cluster no
    confiable) — el lector puede distinguir la procedencia. `directed`=el mensaje va dirigido a zaelar (sube la
    importancia). `durable=True` → nivel `mid` (persiste, con conceptos para el grafo); por defecto `short`
    (recencia). `slot` (opcional) = clave canónica del hecho singular → el writer hace supersede/dedup EXACTO: cada
    ingesta con el MISMO slot SOBRESCRIBE la anterior (útil para una SÍNTESIS evolutiva por fuente/entidad que se
    reescribe, p. ej. `cluster:<cluster>:<peer>` — la conversación con un peer se comprime en UNA píldora viva).
    Best-effort. Reemplaza el `_to_memory` ad-hoc de cada conector."""
    body = (text or "").strip()
    if not body:
        return
    where = f" ({group})" if group else ""
    label = f"[{source}] {entity}{where}: {body}" if entity else f"[{source}]{where}: {body}"
    imp = importance if importance is not None else (0.6 if directed else 0.4)
    if concepts is None and durable:
        from memory.concepts import derive_concepts
        concepts = derive_concepts(body) or None
    write(label, level=("mid" if durable else "short"), kind="msg", importance=imp, ttl_days=ttl_days,
          slot=slot,
          meta={"source": source, "entity": entity, "trust": trust, "group": group, "directed": bool(directed)},
          concepts=concepts)


def recent_by_source(source: str | None = None, entity: str | None = None, limit: int = 20,
                     max_chars: int = 2000) -> list[dict]:
    """LECTURA DIRECTA por TIPO INDEXADO (µs, sin LLM): los datos entrantes (`kind='msg'`) de una FUENTE — y
    opcionalmente de una ENTIDAD — más recientes, filtrando por `meta.source`/`meta.entity` con `json_extract`. Es
    "¿qué me ha llegado por WhatsApp?" / "¿qué me dijo Zalo por el cluster?" resuelto SIN retriever ni LLM. La
    misma capacidad escala a N conectores: solo cambia el valor de `source`. `source=None` → todo lo entrante.
    Devuelve [{id,text,source,entity,trust,created,level}], más reciente primero. Tolera BD vacía."""
    db = _db.get_db()
    where = ["valid=1", "kind='msg'"]
    params: list = []
    if source:
        where.append("json_extract(meta,'$.source')=?"); params.append(source)
    if entity:
        # pylower = lower Unicode (SQLite lower() es ASCII → no casaría 'Álvaro'/'María'/'mamá' con su .lower())
        where.append("pylower(json_extract(meta,'$.entity'))=?"); params.append(str(entity).lower())
    params.append(int(limit))
    rows = db.query(f"SELECT id, text, meta, created, level FROM memories WHERE {' AND '.join(where)} "
                    f"ORDER BY updated DESC, id DESC LIMIT ?", tuple(params))
    out, used = [], 0
    for r in rows:
        txt = (r["text"] or "").strip()
        if not txt:
            continue
        if used + len(txt) > max_chars and out:
            break
        try:
            import json as _json
            m = _json.loads(r["meta"]) if r["meta"] else {}
        except Exception:
            m = {}
        out.append({"id": r["id"], "text": txt, "source": m.get("source"), "entity": m.get("entity"),
                    "trust": m.get("trust"), "created": r["created"], "level": r["level"]})
        used += len(txt)
    return out


def by_concepts(concepts: list[str], *, limit: int = 6) -> list[dict]:
    """LECTURA por CONCEPTO (grafo T126, sin LLM): hechos DURABLES enlazados a los `concepts` dados vía las aristas
    píldora↔concepto. Para AGREGACIÓN por categoría (T178: "¿qué viajes he hecho?") y APLICACIÓN IMPLÍCITA cross-topic
    (T183: al pedir un "restaurante" aflorar la restricción "celíaco" por el concepto compartido 'comida'). Respeta
    valid + CUARENTENA (untrusted fuera) + excluye los propios nodos-concepto. Ordena por peso/importancia. Tolera
    BD vacía. Devuelve [{id,text,level,kind,weight,importance}]."""
    names = [(c or "").strip().lower() for c in (concepts or []) if (c or "").strip()]
    if not names:
        return []
    db = _db.get_db()
    ph = ",".join("?" * len(names))
    cids = [r["id"] for r in db.query(
        f"SELECT id FROM memories WHERE kind='concept' AND valid=1 AND lower(text) IN ({ph})", tuple(names))]
    if not cids:
        return []
    ph2 = ",".join("?" * len(cids))
    rows = db.query(
        f"""SELECT m.id, m.text, m.level, m.kind, m.weight, m.importance
            FROM edges e JOIN memories m ON m.id = e.to_id
            WHERE e.from_id IN ({ph2}) AND e.type='about'
              AND m.valid=1 AND m.kind != 'concept' AND m.level IN ('mid','long')
              AND (json_extract(m.meta,'$.trust') IS NULL OR json_extract(m.meta,'$.trust') != 'untrusted')
            GROUP BY m.id
            ORDER BY m.weight DESC, m.importance DESC
            LIMIT ?""", (*cids, int(limit)))
    return [dict(r) for r in rows]


def forget(match: str, *, hard: bool = False, include_pinned: bool = False) -> int:
    """OLVIDO A PETICIÓN del operador (necesidad humana: "olvida lo del regalo", "bórrate mi contraseña vieja").
    Invalida (soft, `valid=0`) los recuerdos VÁLIDOS cuyo texto contiene `match` (case-insensitive) → dejan de
    aparecer en el recall/lectura, pero se conservan para AUDITORÍA (nunca perdemos el histórico; el operador puede
    preguntar "¿qué te pedí que olvidaras?"). `hard=True` los borra de verdad (irreversible). `pinned` intocable
    salvo `include_pinned=True`. Directo (no cola: el operador espera efecto inmediato). Devuelve nº afectados;
    emite memory.updated. Best-effort."""
    m = (match or "").strip()
    if not m:
        return 0
    db = _db.get_db()
    like = f"%{m.lower()}%"
    pin_clause = "" if include_pinned else "AND pinned=0"
    rows = db.query(f"SELECT id FROM memories WHERE valid=1 {pin_clause} AND lower(text) LIKE ?", (like,))
    ids = {r["id"] for r in rows}
    # OLVIDO GRANULAR robusto al fraseo: SIEMPRE se UNE el match por TOKENS DE CONTENIDO (sin stopwords/posesivos)
    # al contiguo — no como mero fallback. El LIKE contiguo falla o casa SOLO una variante cuando el CORAZÓN
    # canoniza el posesivo ("mi coche"→"su coche") o quita artículos ("de LA seguridad social"→"de seguridad
    # social"): si se borrara solo la variante contigua, la píldora canónica SOBREVIVÍA (bug del hard-forget de la
    # GOLD). Exigir TODOS los tokens (AND) evita sobre-borrar. La unión invalida todas las variantes del mismo hecho.
    import re as _re
    toks = [t for t in _re.findall(r"\w+", m.lower()) if len(t) >= 3 and t not in _FORGET_STOP]
    if toks:
        clause = " AND ".join("lower(text) LIKE ?" for _ in toks)
        rows = db.query(f"SELECT id FROM memories WHERE valid=1 {pin_clause} AND {clause}",
                        tuple(f"%{t}%" for t in toks))
        ids |= {r["id"] for r in rows}
    if not ids:
        return 0
    ids = list(ids)
    ph = ",".join("?" * len(ids))
    from .clock import now as _clock_now
    now = _clock_now()
    if hard:
        # DELEGA en writer.delete_memory (auditoría 2026-07-19 P1-3): el DELETE plano sobre fts_memories
        # (external-content) NO limpiaba el índice → los tokens del dato "borrado del todo" seguían casando MATCH
        # y eran extraíbles de la BD (promesa de privacidad rota) + rowids fantasma ocupaban candidatos k=40.
        # writer.delete_memory hace el 'delete' de FTS5 CON el texto ANTES de borrar la fila (+vec +edges).
        for mid in ids:
            _writer.delete_memory(mid)
    else:
        db.execute(f"UPDATE memories SET valid=0, updated=?, invalidated_at=? WHERE id IN ({ph})",
                   (now, now, *ids))
    _emit("memory.updated", {"op": "forget", "ids": ids, "hard": hard})
    return len(ids)


def unforget(match: str, *, include_pinned: bool = False) -> int:
    """DES-OLVIDO (dim N): revierte un olvido SOFT — necesidad humana "no, recupera lo de X / vuelve a acordarte".
    Restaura (`valid=1`) los recuerdos INVALIDADOS cuyo texto contiene `match`. Contraparte exacta de `forget()`:
    como el soft-forget solo pone `valid=0` (no toca vec/fts) y el retriever filtra por `valid=1`, basta revertir
    el flag para que el dato vuelva a aflorar — sin reindexar. Solo afecta a soft-forgotten (los `hard` ya no
    existen). Directo (efecto inmediato), emite memory.updated. Devuelve nº restaurados. Best-effort."""
    m = (match or "").strip()
    if not m:
        return 0
    db = _db.get_db()
    like = f"%{m.lower()}%"
    pin_clause = "" if include_pinned else "AND pinned=0"
    rows = db.query(f"SELECT id FROM memories WHERE valid=0 {pin_clause} AND lower(text) LIKE ?", (like,))
    ids = {r["id"] for r in rows}
    # UNIÓN token-AND — SIMÉTRICO al de forget(): el LIKE contiguo falla o casa solo UNA variante cuando el CORAZÓN
    # canoniza el posesivo ("mi correo"→"su correo") o quita artículos. Unir (no fallback) restaura TODAS las
    # variantes de lo olvidado. Sin esto el des-olvido dejaba fuera la píldora canónica.
    import re as _re
    toks = [t for t in _re.findall(r"\w+", m.lower()) if len(t) >= 3 and t not in _FORGET_STOP]
    if toks:
        clause = " AND ".join("lower(text) LIKE ?" for _ in toks)
        rows = db.query(f"SELECT id FROM memories WHERE valid=0 {pin_clause} AND {clause}",
                        tuple(f"%{t}%" for t in toks))
        ids |= {r["id"] for r in rows}
    if not ids:
        return 0
    ids = list(ids)
    ph = ",".join("?" * len(ids))
    from .clock import now as _clock_now
    now = _clock_now()
    # invalidated_at vuelve a NULL: la fila vuelve a estar vigente, no puede seguir marcada como "cerrada" en
    # una fecha pasada — un `as_of()` posterior al unforget debe verla vigente desde ahora, no seguir leyéndola
    # como invalidada en la fecha del forget.
    db.execute(f"UPDATE memories SET valid=1, updated=?, invalidated_at=NULL WHERE id IN ({ph})", (now, *ids))
    _emit("memory.updated", {"op": "unforget", "ids": ids})
    return len(ids)


def now() -> int:
    """The memory's clock, THROUGH the facade — never `time.time()` in a caller.

    `memory/clock.py` supports `travel()` so the timeline corpus can replay 270 simulated days; a caller that read
    the wall clock would date its pills in 2026 while the rest of the run believes it is March. Re-exported for the
    same reason as `canon_slot`: the alternative is every module reaching into a memory internal, which the
    contract test counts as the boundary opening up."""
    from .clock import now as _clock_now
    return _clock_now()


def canon_slot(slot: str | None) -> str | None:
    """The canonical key for a slot name/alias, THROUGH the facade. Re-exported (not reimplemented) because the
    registry in `memory/slots.py` stays the single vocabulary; this only spares every caller outside the module a
    direct reach into `memory.writer` for one pure lookup — which the contract test counts, correctly, as the
    boundary opening up."""
    return _writer.canon_slot(slot)


def as_of(slot: str, ts: int | None = None) -> dict | None:
    """Bi-temporal (V2-111 §9.2): qué valor tenía un slot canónico en un instante PASADO — la pregunta que
    `updated` no puede responder de forma fiable (lo toca también el refuerzo y la promoción de nivel, así que
    no es "cuándo se invalidó"). Devuelve la fila más reciente cuyo `valid_at` ya había llegado en `ts` Y que
    todavía no se había invalidado en `ts` (o que nunca se invalidó). `None` si el slot no existía todavía en
    `ts`, o si `slot` no es una clave canónica reconocida — nunca lanza, nunca inventa un valor.

    `ts=None` significa AHORA, o sea «qué valor tiene este slot vigente». Con el parámetro obligatorio, todo
    llamante que solo quisiera el valor actual tenía que importar `memory.clock` para conseguir el `now` — la
    fachada empujando su propio reloj al otro lado de la frontera, que es justo lo que el test de contrato
    (`test_memory_boundary.py`) señaló cuando P0d lo hizo. El reloj es asunto de la memoria, no del llamante."""
    if ts is None:
        from .clock import now as _clock_now
        ts = _clock_now()
    canon = _writer.canon_slot(slot)
    if not canon:
        return None
    db = _db.get_db()
    keys = []
    try:
        from . import slots as _slots
        keys = list(_slots.equivalent_keys(canon) or [canon])
    except Exception:
        keys = [canon]
    ph = ",".join("?" * len(keys))
    row = db.query_one(
        f"SELECT id, level, kind, text, importance, weight, slot, meta, created, updated, valid_at, "
        f"invalidated_at FROM memories WHERE slot IN ({ph}) AND valid_at <= ? "
        f"AND (invalidated_at IS NULL OR invalidated_at > ?) ORDER BY valid_at DESC, id DESC LIMIT 1",
        (*keys, ts, ts),
    )
    return dict(row) if row is not None else None


def reinforce(ids: list[int]) -> None:
    if not ids:
        return
    get_queue().submit("reinforce", list(ids))
    _emit("memory.updated", {"op": "reinforce", "ids": list(ids)})


def pin(mid: int) -> None:
    get_queue().submit("pin", int(mid))
    _emit("memory.updated", {"op": "pin", "id": int(mid)})


def unpin(mid: int) -> None:
    get_queue().submit("unpin", int(mid))
    _emit("memory.updated", {"op": "unpin", "id": int(mid)})


def link(from_id: int, to_id: int, type: str = "about", weight: float = 1.0) -> None:
    get_queue().submit("link", int(from_id), int(to_id), type, weight)
    _emit("memory.updated", {"op": "link"})


# ── lecturas (directas · hot path) ───────────────────────────────────────────────────────────────────────
def state() -> dict:
    """Estado (tabla fija). Directo, µs, sin búsqueda. SIEMPRE en el prompt."""
    return _state.read()


def set_state(fields: dict) -> dict:
    """Actualiza el estado (merge superficial). Emite memory.updated."""
    s = _state.patch(fields)
    _emit("memory.updated", {"op": "state"})
    return s


def note_widgets_used(ids) -> list:
    """Estampa widget(s) en el MRU `recent_widgets` (V2-078): la 2ª capa de acotación para "¿a qué widget se
    refiere?" (abiertos > usados hace poco > catálogo). Lo llama el choke point del canvas cuando un widget pasa
    a ABIERTO. Emite memory.updated para que el prompt cacheado se recomponga fuera del turno (V2-011)."""
    merged = _state.push_recent_widgets(ids)
    _emit("memory.updated", {"op": "state"})
    return merged


# ── KV genérico (sys_kv) — estado ESTRUCTURADO scopeado que no es el ESTADO raíz del operador ────────────────
# V2-069 «una sola mente»: la memoria-de-relación con cada agente (cápsula) necesita persistir un pequeño estado
# ESTRUCTURADO por (cluster,peer) — objetivo, fase, bucles abiertos — SIN inflar el `state()` raíz (que es la
# conciencia del operador) ni crear una tabla nueva. Reusa `sys_kv` (ya lo usan consolidator/rem). Es scope-partido:
# la clave lleva el scope (`capsule:<cluster>:<peer>`), así el estado de una conversación con un agente vive junto a
# todo lo demás pero AISLADO — nunca se mezcla con el estado del operador. Valor = JSON. µs, directo.
def kv_get(key: str, default=None):
    """Lee un valor JSON de sys_kv por clave scopeada. Tolera BD vacía/JSON corrupto → default."""
    import json
    try:
        row = _db.get_db().query_one("SELECT value FROM sys_kv WHERE key=?", (key,))
    except Exception:
        return default
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def kv_set(key: str, value) -> None:
    """Escribe un valor JSON en sys_kv (upsert). Directo (no pasa por la cola: es estado de proceso, no una píldora)."""
    import json
    try:
        _db.get_db().execute(
            "INSERT INTO sys_kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
    except Exception:
        pass


def kv_keys(prefix: str = "") -> list[str]:
    """Todas las claves de sys_kv que empiezan por `prefix` (vacío = todas). Para el barrido de mantenimiento
    (homeostasis) que evicta cápsulas muertas sin abrir la BD por su cuenta. El filtro por prefijo se hace en
    Python (sys_kv es pequeño y `LIKE` trataría `_` como comodín). Tolera BD vacía → []."""
    try:
        rows = _db.get_db().query("SELECT key FROM sys_kv ORDER BY key")
        return [r["key"] for r in rows if str(r["key"]).startswith(prefix)]
    except Exception:
        return []


def kv_del(key: str) -> None:
    """Borra una clave de sys_kv (idempotente). Usado por el mantenimiento para evictar estado muerto."""
    try:
        _db.get_db().execute("DELETE FROM sys_kv WHERE key=?", (key,))
    except Exception:
        pass


# Claves del ESTADO que la sección B renderiza con su propia línea (no como "campo suelto"): no las vuelques dos veces.
_STATE_RENDERED = {"assistant_name", "operator_name", "language", "treatment", "location", "recent", "topics",
                   "open_widgets", "activity", "sessions", "mission", "rails", "rules"}


# ── USER RULES (V2-046 A1) — reglas de comportamiento impuestas por el operador, persistentes ─────────────
_RULES_CAP = 8


def _norm_rule(text: str) -> str:
    import re
    import unicodedata
    n = unicodedata.normalize("NFKD", (text or "").strip().lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", n).split())     # sin acentos ni puntuación, espacios colapsados


def add_user_rule(text: str) -> list:
    """Añade (o refuerza) una USER RULE del operador. Dedup por texto normalizado (re-decirla la sube a la más
    reciente), cap `_RULES_CAP` (fuera la más antigua). Devuelve la lista vigente. Emite memory.updated (por
    set_state) → memory_cache recompone el ESTADO off-loop. Llamar SIEMPRE fuera del turno (to_thread)."""
    t = (text or "").strip().rstrip(".") if text else ""
    if not t:
        return list(state().get("rules") or [])
    cur = [r for r in (state().get("rules") or []) if isinstance(r, str) and r.strip()]
    key = _norm_rule(t)
    cur = [r for r in cur if _norm_rule(r) != key]     # dedup: la nueva versión manda
    cur.append(t)
    cur = cur[-_RULES_CAP:]
    set_state({"rules": cur})
    return cur


def remove_user_rule(text: str) -> tuple[list, str]:
    """Retira la USER RULE que mejor casa con `text` (match difuso stdlib; el operador dice "olvida esa regla de
    ser breve", no el texto exacto). Devuelve `(lista vigente, regla retirada | '')`. Sin match claro no toca nada."""
    import difflib
    cur = [r for r in (state().get("rules") or []) if isinstance(r, str) and r.strip()]
    if not cur:
        return [], ""
    key = _norm_rule(text)
    # match: mejor candidata por similitud de secuencia O por solape de tokens (>=1 token significativo compartido)
    best, best_score = "", 0.0
    key_toks = {w for w in key.split() if len(w) > 3}
    for r in cur:
        rn = _norm_rule(r)
        score = difflib.SequenceMatcher(None, key, rn).ratio()
        if key_toks & {w for w in rn.split() if len(w) > 3}:
            score = max(score, 0.6)
        if score > best_score:
            best, best_score = r, score
    if best_score < 0.45:      # sin señal suficiente → no retirar la regla equivocada
        return cur, ""
    cur = [r for r in cur if r != best]
    set_state({"rules": cur})
    return cur, best

# Cómo se lee cada estado de un run de rail en el prompt (V2-042). SOLO DATOS (la directiva de qué hacer con un
# rail vive en la capa de recursos del FlashBrain — `nucleo/rails.prompt_lines()` — como con los workers).
_RAIL_STATUS = {"searching": "buscando", "playing": "sonando", "paused": "en pausa",
                "sin_resolver": "SIN RESOLVER"}


def compose_state(*, mission_fallback: str = "") -> tuple[str, str, dict]:
    """Compone el ESTADO COMPARTIDO que ven AMBOS cerebros (FlashBrain y SlowBrain): pequeño, ordenado, en el
    idioma del operador. Devuelve `(bloque, operator_name, stats)`.

    Es el contrato del rediseño del prompt (V2-027): el cerebro recibe **[ESTADO compuesto] + [petición]**, y el
    ESTADO se compone aquí una sola vez (los RECURSOS/tools divergen por cerebro → capa propia). Estructura:

      A. **QUIÉN ERES** — la misión/identidad (state.mission, sembrada al init desde `langs`; `mission_fallback`
         si aún no se sembró). Es la parte FIJA; nunca un prompt inglés hardcodeado en un `.py`.
      B. **QUIÉN TIENES DELANTE** — situacional VARIABLE: operador (nombre/trato/ubicación + campos durables del
         estado), widgets ABIERTOS ahora, tareas EN MARCHA, y el perfil durable saliente ("lo que sabes de él").
      C. **DE QUÉ ÍBAIS HABLANDO** — síntesis TENSA de la conversación reciente (corto plazo con cap agresivo:
         las últimas líneas, NO el volcado crudo entero; NUNCA la memoria de largo plazo).

    Lectura DIRECTA (µs, sin LLM ni retriever) → seguro cachearla off-hot-path (`nucleo/flash/memory_cache`). El
    turno de voz NUNCA la compone sin caché (invariante V2-011). Best-effort: `('', '', {...})` si la memoria no
    está disponible. `mission_fallback` lo pasa el llamador que conoce el idioma (nucleo/flash), para no invertir
    la dependencia memoria→voz."""
    stats = {"has_state": False, "state_fields": 0, "short_count": 0, "short_chars": 0,
             "salient_count": 0, "has_mission": False, "op": ""}
    try:
        st = _state.read()
    except Exception:
        return "", "", stats
    op = (st.get("operator_name") or "").strip()
    stats["op"] = op

    # ── A · QUIÉN ERES (misión) ──────────────────────────────────────────────────────────────────────────
    mission = (st.get("mission") or "").strip() or (mission_fallback or "").strip()
    stats["has_mission"] = bool(mission)

    # ── B · QUIÉN TIENES DELANTE (situacional) ───────────────────────────────────────────────────────────
    sit: list[str] = []
    if op:
        sit.append(f"El operador se llama {op}.")
    if st.get("treatment"):
        sit.append(f"Trato preferido: {st['treatment']}.")
    # USER RULES (V2-046 A1): reglas de comportamiento que el operador impuso hablando; persisten entre sesiones
    # y viajan SIEMPRE (cacheadas, µs). Capa APRENDIDA sobre las brain rules. Vacío = ni una línea (prompt idéntico).
    rules = [str(r).strip() for r in (st.get("rules") or []) if str(r).strip()]
    if rules:
        sit.append("REGLAS DEL OPERADOR (te las dio él; síguelas SIEMPRE): "
                   + " · ".join(r[:90] for r in rules[:8]))
    if st.get("location"):
        sit.append(f"Ubicación: {st['location']}.")
    # HECHOS CRÍTICOS de seguridad (alergias/condiciones médicas): línea PROPIA y PROMINENTE que se surface SIEMPRE,
    # independiente del ranking/cap del perfil saliente — olvidar una alergia bajo densidad es un fallo de seguridad
    # (auditoría 2026-07-14). El guard del writer los marca `meta.critical='health'`.
    try:
        crit = critical_facts(limit=6)
    except Exception:
        crit = []
    if crit:
        sit.append("⚠️ CRÍTICO (tenlo SIEMPRE presente): " + " · ".join(crit))
    # Campos CUSTOM escalares del estado (objetivo/proyecto/coche/empresa/cumpleaños…): la "pila" durable del
    # operador va SIEMPRE — el cerebro debe verla sin tener que recordarla.
    for k, v in st.items():
        if k in _STATE_RENDERED:
            continue
        if isinstance(v, (str, int, float)) and str(v).strip():
            sit.append(f"{k.capitalize().replace('_', ' ')}: {v}.")
    open_w = [str(w).strip() for w in (st.get("open_widgets") or []) if str(w).strip()]
    if open_w:
        sit.append("Widgets ABIERTOS ahora en su pantalla: " + ", ".join(open_w[:12]) + ".")
    # PROCESOS/SESIONES VIVAS del SlowBrain (V2-036, P4): id + objetivo + fase, para que el orquestador (FlashBrain)
    # ASOCIE cada pregunta/orden del operador a la sesión correcta ("¿cómo va la moto?", "y el estudio del universo?",
    # "para la tarea del mercado…"). Rico (sesiones) si lo hay; si no, cae a las etiquetas de `activity`.
    sessions = [s for s in (st.get("sessions") or []) if isinstance(s, dict) and (s.get("goal") or s.get("phase"))]
    if sessions:
        lines = []
        waiting_any = False
        for s in sessions[:6]:
            sid = str(s.get("id") or "?")
            goal = (str(s.get("goal") or "")).strip().replace("\n", " ")[:90]
            phase = (str(s.get("phase") or "")).strip()[:40]
            line = f"  · [{sid}] «{goal}»" + (f" — fase: {phase}" if phase else "")
            if (s.get("waiting_on") or "") == "user":
                waiting_any = True
                ask = (str(s.get("ask") or "")).strip()[:120]
                line += f" — ESPERA tu respuesta a: «{ask}»" if ask else " — ESPERA una respuesta tuya"
            lines.append(line)
        # SOLO DATOS (auditoría 2026-07-14): la memoria compone el ESTADO COMPARTIDO; la DIRECTIVA de cómo
        # dirigir workers (refinar=inyectar, parar=matar, responder un ask) es prosa del FlashBrain y vive en su
        # capa de recursos (`nucleo/flash/prompt._flash_layer`) — V2-027: cada cerebro añade SU capa.
        head = "PROCESOS DE FONDO en marcha ahora:\n"
        if waiting_any:
            head = "⚠️ Un proceso de fondo ESPERA una respuesta del operador (abajo). " + head
        sit.append(head + "\n".join(lines))
    else:
        activity = [str(a).strip() for a in (st.get("activity") or []) if str(a).strip()]
        if activity:
            sit.append("Tareas en marcha ahora: " + "; ".join(a[:80] for a in activity[:6]) + ".")
    # RAILS con run VIVO (V2-042): comportamientos conducidos que cruzan turnos — qué se está buscando, qué suena,
    # y las búsquedas SIN RESOLVER (aisladas, con intentos) que el operador puede retomar aportando datos. Los
    # proyecta `nucleo/rails.py`; aquí SOLO datos (la guía por rail la inyecta el FlashBrain solo cuando aplica).
    rails = [a for a in (st.get("rails") or []) if isinstance(a, dict) and (a.get("label") or "").strip()]
    if rails:
        lines = []
        for a in rails[:5]:
            status = _RAIL_STATUS.get(str(a.get("status") or ""), str(a.get("status") or ""))
            line = f"  · [{str(a.get('kind') or '?')}] {status}: «{str(a['label']).strip()[:90]}»"
            det = (str(a.get("detail") or "")).strip()
            if det:
                line += f" — {det[:80]}"
            att = int(a.get("attempts") or 0)
            if att > 1:
                line += f" ({att} intentos)"
            lines.append(line)
        sit.append("Rails en curso (conducciones tuyas):\n" + "\n".join(lines))
    stats["state_fields"] = len(sit)
    stats["has_state"] = bool(sit)

    # Perfil durable SALIENTE ("lo que sabes de él", SOTA in-context availability): cap TERSO (V2-027).
    salient: list[str] = []
    try:
        for m in salient_long(limit=5, max_chars=440):
            t = (m.get("text") or "").strip().replace("\n", " ")
            if t:
                salient.append(f"· {t[:140]}")
    except Exception:
        pass
    stats["salient_count"] = len(salient)

    # ── C · DE QUÉ ÍBAIS HABLANDO (síntesis TENSA del corto plazo) ────────────────────────────────────────
    # V2-027: sustituye el volcado CRUDO de 30 líneas / 1800 chars por las ÚLTIMAS pocas líneas (cap agresivo).
    # Sigue siendo lectura DIRECTA (µs, sin LLM) — la "síntesis" es el recorte, no un resumen por modelo (que, si
    # se quisiera, iría OFF del turno como el resto de la escritura). Da el hilo reciente sin inflar el prompt.
    convo: list[str] = []
    short_chars = 0
    try:
        for m in recent_short(limit=5, max_chars=550):
            t = (m.get("text") or "").strip().replace("\n", " ")
            if t:
                convo.append(f"· {t[:180]}")
                short_chars += len(t)
    except Exception:
        pass
    stats["short_count"] = len(convo)
    stats["short_chars"] = short_chars

    if not (mission or sit or salient or convo):
        return "", op, stats

    parts: list[str] = []
    if mission:
        parts.append("── QUIÉN ERES ──\n" + mission)
    if sit or salient:
        b = "── QUIÉN TIENES DELANTE (trátalo como sabido de siempre; salúdalo por su nombre sin volver a preguntar) ──"
        if sit:
            b += "\n" + "\n".join(sit)
        if salient:
            b += "\n[Lo que sabes de él, dalo por sabido sin buscar]\n" + "\n".join(salient)
        parts.append(b)
    if convo:
        parts.append("── DE QUÉ ÍBAIS HABLANDO (lo más reciente primero; el último MANDA si hay contradicción) ──\n"
                     + "\n".join(convo))
    block = "\n\n".join(parts)
    return block, op, stats


def _pack(memories: list[dict], budget_tokens: int) -> list[dict]:
    """Trunca la lista al presupuesto de tokens (aprox chars/4)."""
    out, used = [], 0
    for m in memories:
        cost = max(1, len(m.get("text", "")) // _CHARS_PER_TOKEN)
        if used + cost > budget_tokens and out:
            break
        out.append(m)
        used += cost
    return out


def query(prompt: str, budget_tokens: int = DEFAULT_BUDGET_TOKENS, limit: int = 12,
          expand: bool = True, reinforce_used: bool = True) -> dict:
    """Ruta caliente: compone el contexto mínimo = estado (SIEMPRE) + recuerdos relevantes al presupuesto.

    Devuelve {'state': dict, 'memories': list[dict], 'ids': list[int]}. Encola el refuerzo de los usados."""
    from . import retriever as _retriever  # import perezoso (evita ciclos en import-time)

    st = _state.read()
    mems = _retriever.search(prompt, limit=limit, expand=expand, reinforce=False)
    # THE CHOKEPOINT for the background-slot rule (2026-08-21). Every surface that shows pills to a model gets
    # them from here, and `query` already has the request the rule needs — so applying it once, at the source,
    # is what makes a FUTURE surface inherit it instead of re-deriving it. The list-of-surfaces approach was
    # tried and failed three times in one day: passive block (2026-07-14), worker dossier and active recall
    # (both 2026-08-21), and `/api/memory/recall` — the bridge `mem_cli` uses — was a FOURTH that nobody had
    # listed, found while looking for a way to stop needing the list.
    mems = [m for m in mems if not background_slot_off_topic(m.get("slot"), prompt)]
    mems = _pack(mems, budget_tokens)
    ids = [m["id"] for m in mems]
    if reinforce_used and ids:
        # Refuerzo SELECTIVO: el paquete puede incluir conceptos, vecinos de
        # grafo y resultados laterales para dar contexto al cerebro. Reforzar
        # todos ellos convierte una consulta sobre vivienda en "uso" de la
        # alergia, la infancia o cualquier otro resultado empaquetado. Sin un
        # feedback explícito del LLM sobre qué leyó, la señal honesta es el
        # primer recuerdo de contenido (los nodos conceptuales son índices, no
        # recuerdos vividos). Esto evita crecimiento neuronal artificial.
        used = [m["id"] for m in mems if m.get("kind") != "concept"][:1]
        if used:
            reinforce(used)  # escritura async (el acceso resetea el decay)
    return {"state": st, "memories": mems, "ids": ids}


def _concept_graph(pills: list[dict], resolver) -> dict:
    """Construye un MAPA CONCEPTUAL de una capa (V2-013 T126, redseño del visor 2026-07-10): nodos = conceptos con
    su `count` (nº de datos de ESTA capa que los tocan), links = aristas CONCEPTO↔CONCEPTO por CO-OCURRENCIA (dos
    conceptos se relacionan si comparten una píldora; `weight` = nº de píldoras compartidas). SIN contenido: es el
    plano de CÓMO se organiza la información, no las píldoras. `resolver(pill) -> [labels]` da los conceptos de
    cada píldora (para el LARGO = aristas persistidas; para el CORTO = derivadas al vuelo, no hay aristas)."""
    from itertools import combinations
    node_count: dict[str, int] = {}
    link_w: dict[tuple, int] = {}
    for p in pills:
        cs = sorted({c for c in (resolver(p) or []) if c})
        for c in cs:
            node_count[c] = node_count.get(c, 0) + 1
        for a, b in combinations(cs, 2):
            key = (a, b)
            link_w[key] = link_w.get(key, 0) + 1
    nodes = [{"key": c, "label": c, "count": n}
             for c, n in sorted(node_count.items(), key=lambda kv: (-kv[1], kv[0]))]
    links = [{"a": a, "b": b, "weight": w} for (a, b), w in link_w.items()]
    return {"nodes": nodes, "links": links}


def map() -> dict:
    """Mapa COMPLETO de la memoria para el VISOR (V2-014 · T129 · redseño de 2 vistas 2026-07-10). Lectura DIRECTA
    de la BD (no hot path, NO refuerza ni toca pesos). Sirve DOS vistas que el frontend alterna:

      • **SLOTS** — `state` + `layers.{short,long}` (tarjetas por capa, con TODOS los metadatos por unidad).
      • **CONCEPTOS** — `concept_graph.{short,long}`: mapa conceptual SEPARADO por capa (corto y largo son
        storages distintos en la realidad → diagramas distintos). Cada uno = {nodes:[{key,label,count}],
        links:[{a,b,weight}]} — conceptos con nº de datos + relaciones concepto↔concepto por co-ocurrencia, SIN
        volcar el contenido. El LARGO usa las aristas persistidas (grafo emergente del CORAZÓN); el CORTO las
        deriva al vuelo (`memory.concepts.derive_concepts`, el corto no persiste aristas — píldoras efímeras).

    Devuelve::

        {
          "state":         {...},
          "layers":        {"short": [mem...], "long": [mem...]},   # vista SLOTS
          "concept_graph": {"short": {nodes,links}, "long": {nodes,links}},  # vista CONCEPTOS (separada)
          "concepts":      [mem+degree...],      # (compat) nodos-concepto crudos
          "edges":         [{from_id,to_id,type,weight}...],
          "counts":        {"short": n, "long": m, "concepts": k, "edges": e, "total": t},
        }

    Read-only: lo sirve `GET /api/memory/map` (no-cache) y se refresca en vivo por `memory.updated` (puente SSE
    en el server). Tolera BD vacía (listas/grafos vacíos)."""
    from memory.concepts import derive_concepts
    db = _db.get_db()
    rows = db.query(
        "SELECT id, level, kind, text, importance, weight, access_count, last_access, ttl_days, "
        "pinned, valid, superseded_by, slot, meta, created, updated FROM memories ORDER BY updated DESC"
    )
    mems = [dict(r) for r in rows]
    short = [m for m in mems if m.get("level") == "short" and m.get("kind") != "concept"]
    # NODOS-CONCEPTO (T126) fuera de las capas: son HUBS del grafo, no hechos → capa propia para el visor.
    concepts = [m for m in mems if m.get("kind") == "concept"]
    longterm = [m for m in mems if m.get("level") in ("mid", "long") and m.get("kind") != "concept"]
    edges = [dict(r) for r in db.query("SELECT from_id, to_id, type, weight FROM edges")]
    # nº de píldoras enlazadas por concepto (para pintar el tamaño del hub).
    deg: dict[int, int] = {}
    for e in edges:
        deg[e["from_id"]] = deg.get(e["from_id"], 0) + 1
    for c in concepts:
        c["degree"] = deg.get(c["id"], 0)

    # ── MAPA CONCEPTUAL por capa (vista CONCEPTOS) ──────────────────────────────────────────────────────────
    # LARGO: conceptos de cada píldora vía aristas persistidas (grafo emergente del CORAZÓN). Backstop derivado
    # si una píldora durable no tiene aristas (pre-T126 / sin etiqueta del LLM).
    concept_label = {c["id"]: (c.get("text") or "").strip() for c in concepts}
    pill_concepts: dict[int, set] = {}
    cid_set = set(concept_label)
    for e in edges:
        f, t = e.get("from_id"), e.get("to_id")
        if f in cid_set and t not in cid_set:
            pill_concepts.setdefault(t, set()).add(concept_label[f])
        elif t in cid_set and f not in cid_set:
            pill_concepts.setdefault(f, set()).add(concept_label[t])

    def _long_resolver(p):
        labels = pill_concepts.get(p.get("id"))
        return list(labels) if labels else derive_concepts(p.get("text") or "")

    def _short_resolver(p):
        return derive_concepts(p.get("text") or "")

    concept_graph = {
        "short": _concept_graph(short, _short_resolver),
        "long": _concept_graph(longterm, _long_resolver),
    }

    return {
        "state": _state.read(),
        "layers": {"short": short, "long": longterm},
        "concept_graph": concept_graph,
        "concepts": concepts,
        "edges": edges,
        "counts": {"short": len(short), "long": len(longterm), "concepts": len(concepts),
                   "edges": len(edges), "total": len(mems)},
    }


def recent_short(limit: int = 30, max_chars: int = 1800) -> list[dict]:
    """CORTO PLAZO reciente, LECTURA DIRECTA (µs, sin embeddings ni retriever) — el "working set" que se enchufa
    ENTERO al prompt (V2-013 T146): la memoria de corto plazo es pequeña y cabe, así que en vez de buscar
    (lento, y hoy poco fiable) el modelo la ve completa. Más reciente primero, acotado por nº y por chars para
    no inflar el prompt/latencia. Devuelve [{id, text, created}]. Tolera BD vacía."""
    db = _db.get_db()
    # Orden DETERMINISTA: `updated` tiene resolución de segundo → varias escrituras en el mismo segundo empatan y
    # el desempate arbitrario haría que un turno MÁS reciente cayera fuera de la ventana (rompe "el más reciente
    # MANDA" de la recencia). Desempatamos por `id` (monótono, orden de inserción) → la recencia es estable.
    # CUARENTENA por CONFIANZA (multi-fuente 2026-07-10): lo `trust='untrusted'` (peers de cluster, agentes
    # ajenos) NUNCA entra en el bloque PASIVO que ve el FlashBrain cada turno — evita que un peer no confiable
    # inyecte instrucciones en el prompt del operador. Sigue siendo recuperable por consulta EXPLÍCITA
    # (`recent_by_source`) o recall dirigido. Lo del propio dueño (operator/external) sí entra.
    rows = db.query(
        "SELECT id, text, created FROM memories WHERE level='short' AND valid=1 "
        "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted') "
        "ORDER BY updated DESC, id DESC LIMIT ?", (int(limit),)
    )
    out, used = [], 0
    for r in rows:
        txt = (r["text"] or "").strip()
        if not txt:
            continue
        if used + len(txt) > max_chars and out:
            break
        out.append({"id": r["id"], "text": txt, "created": r["created"]})
        used += len(txt)
    return out


def recent_window(limit: int = 6, max_chars: int = 1600) -> list[dict]:
    """VENTANA CONVERSACIONAL verbatim (los últimos turnos LITERALES operador↔zaelar), LECTURA DIRECTA (µs, sin
    LLM ni retriever). Reconstruye los pares del BUFFER de corto `kind='conv'` (que escribe el provider cada turno)
    en mensajes listos para SEMBRAR `brain._window` tras un reinicio/reconexión — así el FlashBrain no pierde "de
    qué hablábamos" cuando su ventana en memoria arranca vacía (circuito de corto plazo, 2026-07-14). Devuelve
    `[{role, content}]` MÁS ANTIGUO primero (orden natural de chat). Prefiere los campos estructurados `meta.u`/
    `meta.a`; si un registro viejo no los tiene, parsea el texto "Operador: … · zaelar: …". Tolera BD vacía."""
    import json as _json
    db = _db.get_db()
    rows = db.query(
        "SELECT text, meta, created FROM memories WHERE level='short' AND valid=1 "
        "AND json_extract(meta,'$.source')='conv' "
        "ORDER BY updated DESC, id DESC LIMIT ?", (int(limit),)
    )
    pairs: list[tuple[str, str, float]] = []
    used = 0
    for r in rows:                                    # vienen NUEVO→VIEJO; recortamos por chars y luego invertimos
        u = a = ""
        try:
            meta = _json.loads(r["meta"]) if r["meta"] else {}
            u = (meta.get("u") or "").strip()
            a = (meta.get("a") or "").strip()
        except Exception:
            meta = {}
        if not u and not a:                            # registro viejo sin meta estructurado → parsea el texto
            txt = (r["text"] or "")
            if "· zaelar:" in txt:
                left, _, right = txt.partition("· zaelar:")
                u = left.replace("Operador:", "", 1).strip()
                a = right.strip()
            else:
                u = txt.strip()
        seg = len(u) + len(a)
        if used + seg > max_chars and pairs:
            break
        pairs.append((u, a, float(r["created"] or 0)))
        used += seg
    out: list[dict] = []
    for u, a, ts in reversed(pairs):                   # VIEJO→NUEVO
        # `ts` = epoch seconds this pair was written (V2-105 follow-up, 2026-08-17): lets a caller that needs
        # RECENCY — not just "is there any conversation" — filter out an entry from hours/days ago. The 2-day
        # TTL on this buffer is deliberate continuity for the FlashBrain's own "what were we talking about"
        # (voice/engine/pipeline/agent.py's reconnect-vs-new-session read), so `recent_window` keeps returning
        # everything within TTL by default; filtering by `ts` is opt-in per caller, not a change here.
        if u:
            out.append({"role": "user", "content": u, "ts": ts})
        if a:
            out.append({"role": "assistant", "content": a, "ts": ts})
    return out


def seconds_since_last_conv() -> float | None:
    """Segundos desde el ÚLTIMO turno conversacional (buffer corto `source='conv'`), o None si no hay ninguno.
    Sirve para que el kickoff (voice/engine/pipeline/agent.py) distinga una sesión NUEVA de una RECONEXIÓN a una
    conversación EN CURSO: si el operador habló hace un momento, reconectar NO debe re-saludar como si fuera el
    primer turno (bug 2026-07-25: cada reconexión soltaba «Hola, ¿qué necesitas?» en mitad de la charla). Lectura
    directa µs, tolera BD vacía."""
    try:
        db = _db.get_db()
        row = db.query(
            "SELECT MAX(created) AS c FROM memories WHERE level='short' AND valid=1 "
            "AND json_extract(meta,'$.source')='conv'"
        )
        c = (row[0]["c"] if row else None)
        if not c:
            return None
        return max(0.0, __import__("time").time() - float(c))
    except Exception:
        return None


def critical_facts(limit: int = 8) -> list[str]:
    """Hechos CRÍTICOS de seguridad (alergias, intolerancias, condiciones médicas) marcados `meta.critical='health'`
    por el guard del writer. Lectura DIRECTA. Van a una LÍNEA PROPIA del estado (compose_state) que se surface
    SIEMPRE — nunca dependen del ranking/cap de `salient_long`: olvidar una alergia bajo densidad es un fallo de
    seguridad (auditoría de memoria 2026-07-14, hallazgo del corpus v3: la penicilina se enterraba bajo ~130
    píldoras). Solo válidos y durables; dedup por texto normalizado (varias alergias distintas SÍ coexisten)."""
    try:
        rows = _db.get_db().query(
            "SELECT text FROM memories WHERE valid=1 AND level IN ('mid','long') "
            "AND json_extract(meta,'$.critical')='health' ORDER BY (importance*weight) DESC, updated DESC LIMIT ?",
            (int(limit) * 2,))
    except Exception:
        return []
    out, seen = [], set()
    for r in rows:
        t = (r["text"] or "").strip()
        k = " ".join(t.lower().split())
        if t and k not in seen:
            seen.add(k)
            out.append(t)
        if len(out) >= limit:
            break
    return out


_SLOT_WORD_MIN = 4


def background_slot_off_topic(slot: str | None, prompt: str) -> bool:
    """True when `slot` is a BACKGROUND slot and the request never named it — the ONE rule, for every surface
    that renders pills to a model.

    Background/widget/cluster pills carry a namespaced slot (`<widget>:<key>`); the operator's own facts use
    dots (`operator.location`). Three surfaces show pills to a model and each must apply this, because to the
    model they all read as «what you know about this person»:

      1. the PASSIVE block  — `salient_long()` below, since the 2026-07-14 audit;
      2. the WORKER DOSSIER — `nucleo/memory_agent.compose_context`, since 2026-08-21;
      3. the ACTIVE RECALL  — `nucleo/flash/prompt.compose_recall`, the one that runs EVERY turn.

    Surface 1 expresses it in SQL (`slot NOT LIKE '%:%'`) rather than calling this, and that is on purpose but
    NOT a semantic difference: the passive block has no request to check a slot against, and this predicate with
    an empty prompt returns exactly the same verdict (checked — with no words to match, every namespaced slot is
    off-topic). SQL keeps it because filtering before the ranking is cheaper than filtering after, not because
    the rule differs. If you ever move it here, that equivalence is what makes it safe.

    The rule lived in surface 1 for five weeks and in prose everywhere else, so 2 and 3 each had to be found by
    a live failure. Measured 2026-08-21 with V2-242 and the dossier fix already in the tree: surface 3 still put
    `Weather in Soria now…` ABOVE «Vive en el centro de Madrid» under the header «Puede que venga a cuento (de
    tu memoria)». A convention repeated in three places is not a rule — this function is.

    CONDITIONAL, not a ban: the 2026-07-14 note promises these stay reachable on an EXPLICIT question, so a
    namespaced pill still passes when the request names its namespace or its key («el tiempo en Soria»).
    """
    if ":" not in (slot or ""):
        return False
    # The colon is a PROXY for "written by a background job", not the thing itself — and memory's own synthesis
    # shares the shape without sharing the nature. `insight:<concept>` is what REM writes when it summarises the
    # operator's own pills (V2-056); excluding it would mean a question about the topic no longer returns the
    # insight that summarises it, which is the entire point of the REM cycle and is asserted by
    # `test_several_turns_then_rem_structurally_improves_memory`. That test is what caught this: the rule went in
    # at the chokepoint and turned red on first contact.
    # `secret:*` is deliberately NOT excepted: a vault entry has no business in a model prompt.
    if str(slot).lower().startswith("insight:"):
        return False
    low = (prompt or "").lower()
    for part in re.split(r"[:._\-]+", str(slot).lower()):
        if len(part) >= _SLOT_WORD_MIN and re.search(rf"\b{re.escape(part)}\b", low):
            return False
    return True


def salient_long(limit: int = 8, max_chars: int = 800) -> list[dict]:
    """LO QUE ZAELAR "SABE DE TI" — las memorias durables MÁS salientes (mayor importancia·peso), lectura DIRECTA
    (µs, sin embeddings ni retriever) — SOTA "in-context availability": un humano sabe que le gusta el pádel sin
    tener que *recordarlo*. Se enchufa cacheada en el bloque del FlashBrain (memory_cache), junto al estado y al
    corto, para que lo esencial durable esté SIEMPRE disponible sin disparar el recall semántico (V2-013). Solo
    `valid=1`, nivel durable (mid/long). Devuelve [{id, text, importance, weight, kind}]. Tolera BD vacía."""
    db = _db.get_db()
    # EXCLUYE los slots de FONDO namespaced (`weather:soria`, `<widget>:<clave>`, `cluster:…`) — auditoría de
    # memoria 2026-07-14: el bloque pasivo es "lo que zaelar sabe del OPERADOR" y se pinta con "dalo por sabido SIN
    # buscar"; un `weather:soria` volcado por el widget de fondo se colaba ahí y SECUESTRABA "¿qué tiempo hace hoy?"
    # (el cerebro leía Soria en vez de aterrizar en state.location y buscar). Los slots del operador usan `.`
    # (operator.location, goal.current…); los de fondo/widget/cluster usan `:` → quedan SUBORDINADOS a state.location
    # (fuera del pasivo). Siguen siendo recuperables por el retriever ante una pregunta EXPLÍCITA por esa ciudad.
    rows = db.query(
        "SELECT id, text, importance, weight, kind FROM memories "
        "WHERE valid=1 AND level IN ('mid','long') AND kind != 'profile' "
        "AND (slot IS NULL OR slot NOT LIKE '%:%') "
        "AND (json_extract(meta,'$.critical') IS NULL) "        # los CRÍTICOS van en su línea propia (no aquí, sin dup)
        "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted') "
        "ORDER BY (importance * weight) DESC, updated DESC LIMIT ?", (int(limit) * 3,)
    )
    out, used = [], 0
    for r in rows:
        txt = (r["text"] or "").strip()
        if not txt:
            continue
        if used + len(txt) > max_chars and out:
            break
        out.append({"id": r["id"], "text": txt, "importance": r["importance"],
                    "weight": r["weight"], "kind": r["kind"]})
        used += len(txt)
        if len(out) >= limit:
            break
    return out


def load_episode(episode_id: int, as_text: bool = True):
    """Carga LAZY del binario/texto de un episodio (bajo orden). Directo."""
    return _episodic.load_text(episode_id) if as_text else _episodic.load_bytes(episode_id)


def register_episode(path: str, summary: str, **kwargs) -> dict:
    """Registra un fichero episódico (resumen buscable + fila episodic). Emite memory.updated."""
    ref = _episodic.register(path, summary, **kwargs)
    _emit("memory.updated", {"op": "episode", **ref})
    return ref


def write_episode(data: bytes, *, filename: str, mime: str | None = None,
                  summary: str | None = None, importance: float | None = None) -> dict:
    """Guarda bytes en la memoria episódica (data-dir) + resumen buscable (V2-003). Sustituye a la vieja
    bandeja `files/uploads/`: lo escribe el endpoint de subida. Emite memory.updated. Directo (necesita el id)."""
    ref = _episodic.write_episode(data, filename=filename, mime=mime, summary=summary, importance=importance)
    _emit("memory.updated", {"op": "episode", "id": ref.get("memory_id"), "name": ref.get("name")})
    return ref


def list_episodes(limit: int = 200) -> list[dict]:
    """Listado plano de episodios (para verificación / futuro widget). Directo."""
    return _episodic.list_episodes(limit=limit)


def migrate_inbox(src_dir=None) -> dict:
    """Migración perezosa, idempotente y NO destructiva de `files/uploads/` → memoria episódica (V2-003)."""
    rep = _episodic.migrate_inbox(src_dir)
    if rep.get("migrated"):
        _emit("memory.updated", {"op": "migrate_inbox", "count": len(rep["migrated"])})
    return rep


# ── job periódico (no hot path) ──────────────────────────────────────────────────────────────────────────
def consolidate(**kwargs) -> dict:
    """Un ciclo de consolidación ("sueño"). Lo dispara el loop orquestador (V2-005). Emite memory.updated."""
    rep = _consolidator.consolidate(**kwargs)
    _emit("memory.updated", {"op": "consolidate", **{k: rep[k] for k in ("deduped", "evicted")}})
    return rep
