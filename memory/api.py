"""memory/api.py — Public facade for central memory (V2-002 · T52).

The sole entry point for the rest of zaelar (FlashBrain, memory agent + headless workers, widgets, server).
It fits the system's HYBRID transport:

  - **async (queue)** — NON-urgent mutations: `write` · `reinforce` · `pin`/`unpin` · `link`. They enter through
    `memory/queue.py` (single writer → zero collisions); they do not block the hot path.
  - **direct (hot path · ms/µs)** — `query` (retriever) · `state` (fixed table) · `load_episode` (lazy).

Each mutation emits the **`memory.updated`** signal through `bus/` (loop-agnostic, best-effort) so the UI or
other subscribers can refresh. `query()` composes the minimum context = state (ALWAYS) + relevant memories
truncated to the token budget, and queues **use reinforcement** for used memories (async write; access resets decay).

Lifecycle: `start()`/`stop()` start/stop the queue consumer in the server loop (wired by
V2-003 in the lifespan). Without `start()`, writes are applied inline (standalone/tests) — they are never lost.
"""
import asyncio
import re

from . import consolidator as _consolidator
from .clock import now as _clock_now
from . import db as _db  # noqa: F401  (asegura import del paquete; get_db perezoso)
from . import episodic as _episodic
from . import state as _state
from . import writer as _writer
from .queue import get_queue

# tokens ≈ characters / 4 (cheap approximation for truncating to the budget).
_CHARS_PER_TOKEN = 4
DEFAULT_BUDGET_TOKENS = 1200

# EXPLICIT facade contract (modularity audit 2026-07-17): this is the public surface; the rest of the repo must not
# import internals (memory.db/writer/queue/slots/…) outside tests.
__all__ = [
    "start", "stop",
    "write", "write_now", "ingest_message", "correction_targets", "widget_trace_ids", "reinforce", "reinforce_ids_for", "pin", "unpin", "link",
    "forget", "unforget", "clear_conversation", "clear_slot_prefix",
    "state", "set_state", "compose_state", "add_user_rule", "remove_user_rule",
    "kv_get", "kv_set",
    "query", "recent_short", "recent_window", "recent_by_source", "by_concepts",
    "seconds_since_last_conv",
    "critical_facts", "salient_long", "map",
    "load_episode", "register_episode", "write_episode", "list_episodes", "migrate_inbox",
    "consolidate", "DEFAULT_BUDGET_TOKENS",
]

# Stopwords (articles/prepositions/POSSESSIVES) ignored when performing GRANULAR forgetting by content tokens:
# the operator says "forget my car's license plate" but the CORE stores "your car's license plate" → a contiguous
# LIKE fails because of the possessive. The token-AND fallback compares only content tokens (license plate, car).
_FORGET_STOP = {
    "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas", "lo", "que", "te", "me", "se",
    "mi", "mis", "tu", "tus", "su", "sus", "nuestro", "vuestra", "esa", "ese", "eso", "esta", "este", "esto",
    "en", "con", "por", "para", "sobre", "como", "más", "muy", "ya", "no",
    "todo", "toda", "todos", "todas", "cosa", "cosas",   # "forget EVERYTHING about X" = BROAD forgetting of X
}


def _emit(topic: str, payload=None):
    try:
        import bus
        bus.emit_sync(topic, payload or {})
    except Exception:
        pass


# ── queue lifecycle ─────────────────────────────────────────────────────────────────────────────
async def start():
    """Start the queue's sole consumer in the current loop (server lifespan)."""
    await get_queue().start()


async def stop(drain: bool = True):
    await get_queue().stop(drain=drain)


# ── writes (async · queue) ────────────────────────────────────────────────────────────────────────────
def write(text: str, *, level: str = "short", kind: str = "event", importance: float | None = None,
          weight: float = 0.5, ttl_days: float | None = None, pinned: bool = False,
          slot: str | None = None, meta: dict | str | None = None,
          concepts: list[str] | None = None, supersedes: list[int] | None = None) -> None:
    """Queue a memory (fire-and-forget). The embedding is computed by the writer. Emits memory.updated.

    PILL (V2-013): `slot` = canonical key for the singular fact (`operator.name`…) → EXACT supersede/dedup in the
    writer; `meta` = free-form JSON wrapper (entity/source/said_at…) for the viewer and graph; `concepts` = 1–3
    lightweight labels (health/finance…) → the writer creates/links concept nodes in the graph (T126)."""
    get_queue().submit(
        "write", text, level=level, kind=kind, importance=importance,
        weight=weight, ttl_days=ttl_days, pinned=pinned, slot=slot, meta=meta, concepts=concepts,
        supersedes=supersedes,
    )
    _emit("memory.updated", {"op": "write", "kind": kind})


def write_now(text: str, **kwargs) -> int:
    """Direct SYNCHRONOUS write (for callers that need the id immediately: episodic storage, tests). Emits memory.updated."""
    mid = _writer.insert_memory(text, **kwargs)
    _emit("memory.updated", {"op": "write", "id": mid})
    return mid


def correction_targets(window_s: float = 2700.0, limit: int = 6) -> list[dict]:
    """The durable SLOTLESS pills a same-conversation correction may reach (V2-565): id + text, newest first.

    Two consumers, deliberately the same function so they cannot drift: `nucleo/mem_processor._render` OFFERS
    these to the distiller (so it can notice that the turn contradicts something just stored — it cannot correct
    what it never sees), and `nucleo/memory_agent/ingest` uses the same list as the WHITELIST for the model's
    `supersedes` answer, so the model can only ever name ids it was shown.

    Slotless only: slotted facts already have exact supersede, and keeping identity/state out of this path is
    what makes it safe to let the model aim. The window is the practical definition of "this conversation" —
    a correction corrects what was just said, not last month's facts. `created`, not `updated`: decay and
    reinforcement touch `updated`, and this asks when the pill was WRITTEN. Clock via `now()` (clock.travel)."""
    db = _db.get_db()
    since = now() - float(window_s)
    rows = db.query(
        "SELECT id, text FROM memories WHERE valid=1 AND slot IS NULL AND level IN ('mid','long') "
        "AND kind NOT IN ('conv') AND created >= ? "
        "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted') "
        "ORDER BY created DESC, id DESC LIMIT ?", (since, int(limit)))
    return [{"id": int(r["id"]), "text": r["text"]} for r in rows]


def widget_trace_ids(widget_id: str, limit: int = 4) -> list[int]:
    """The valid pills anchored to a widget — ids of `[widget:<id>]`-prefixed rows, newest first (V2-577).

    One consumer: `widgets/lifecycle.py`. Every lifecycle transition (created/deleted/restored) writes its own
    `[widget:<id>]` pill and passes THIS list as `supersedes`, so only the newest chapter of a widget's story
    stays valid and recall stops serving a birth announcement next to its own tombstone (measured 2026-09-04,
    V2-576 cause B: pill 1165 said the deleted widget existed, and the fix worker believed it first).

    The anchor is the TEXT PREFIX — the only deterministic handle those pills carry. Pills that never declared
    it are out of reach on purpose: matching by content invents targets. `_` is escaped (a LIKE wildcard, a
    legal slug character). Capped to the writer's own supersede cap; the chain keeps the valid set at ~1, so
    the cap never truncates in practice."""
    wid = (widget_id or "").strip().lower()
    if not wid:
        return []
    db = _db.get_db()
    pat = "[widget:" + wid.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "]%"
    rows = db.query(
        "SELECT id FROM memories WHERE valid=1 AND slot IS NULL AND kind != 'conv' "
        "AND text LIKE ? ESCAPE '\\' ORDER BY created DESC, id DESC LIMIT ?", (pat, int(limit)))
    return [int(r["id"]) for r in rows]


def ingest_message(source: str, entity: str | None, text: str, *, group: str | None = None,
                   directed: bool = False, trust: str = "external", durable: bool = False,
                   importance: float | None = None, ttl_days: float | None = None,
                   concepts: list[str] | None = None, slot: str | None = None) -> None:
    """TYPED INGESTION of an incoming datum from an external SOURCE — the ONLY path through which every connector
    feeds memory (V2-013 · multi-source 2026-07-10). Whether there are 2 connectors or 200, or a cluster peer («Zalo»)
    or WhatsApp chat, all enter here with their `source` (whatsapp/telegram/cluster/agent/email…) and `entity`
    (who). `source`/`entity` are INDEXED in `meta` (→ direct type-based reads with `recent_by_source`) **and**
    en el TEXTO (`[source] entity: body`) para que FTS/recall los encuentren sin trabajo extra. `trust`:
    'operator' (the owner) · 'external' (the owner's personal connector) · 'untrusted' (an untrusted cluster peer) —
    the reader can distinguish provenance. `directed`=the message is addressed to zaelar (raises
    importancia). `durable=True` → nivel `mid` (persiste, con conceptos para el grafo); por defecto `short`
    (recencia). `slot` (opcional) = clave canónica del hecho singular → el writer hace supersede/dedup EXACTO: cada
    ingesta con el MISMO slot SOBRESCRIBE la anterior (útil para una SÍNTESIS evolutiva por fuente/entidad que se
    reescribe, p. ej. `cluster:<cluster>:<peer>` — la conversación con un peer se comprime en UNA píldora viva).
    Best-effort. Replaces each connector's ad-hoc `_to_memory`."""
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
    """CONCEPT-BASED READ (T126 graph, no LLM): DURABLE facts linked to the given `concepts` through
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
    """FORGETTING AT THE OPERATOR'S REQUEST (human need: "forget the gift", "erase my old password").
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
    """UNFORGET (dim N): reverses a SOFT forget — human need "no, recover X / remember again".
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
    now = _clock_now()
    # invalidated_at vuelve a NULL: la fila vuelve a estar vigente, no puede seguir marcada como "cerrada" en
    # una fecha pasada — un `as_of()` posterior al unforget debe verla vigente desde ahora, no seguir leyéndola
    # como invalidada en la fecha del forget.
    db.execute(f"UPDATE memories SET valid=1, updated=?, invalidated_at=NULL WHERE id IN ({ph})", (now, *ids))
    # "Basta revertir el flag — sin reindexar" stopped being fully true the day `consolidator.prune_invalid`
    # was built (2026-07-19): a shell invalidated MORE than 2 days ago was pruned OUT of the indexes (vector
    # and FTS deleted, paraphrases dropped, `meta.pruned=1` stamped), so flipping `valid` back revived a row no
    # search could ever surface again — and nothing anywhere re-indexed it (found in the 2026-09-05 integrity
    # review). Re-add the FTS row here (cheap, deterministic, and recall works immediately through the keyword
    # half of the RRF); the VECTOR is the nightly repair's job — `embed_pending` makes the wait COUNTABLE in
    # `hygiene()` — and the paraphrase backfill re-covers it on its own. The `pruned` stamp comes off so a
    # future invalidation can prune it again. Only rows the pruner actually touched: re-inserting FTS for a
    # still-indexed row would duplicate its index entries (FTS5 external-content has no upsert).
    import json as _json
    for r in db.query(f"SELECT id, text, meta FROM memories WHERE id IN ({ph})", tuple(ids)):
        try:
            meta = _json.loads(r["meta"] or "{}")
            if meta.pop("pruned", None) is None:
                continue
            meta["embed_pending"] = "revived"
            with db.cursor() as cur:
                cur.execute("INSERT INTO fts_memories (rowid, text) VALUES (?, ?)", (r["id"], r["text"]))
                cur.execute("UPDATE memories SET meta=? WHERE id=?",
                            (_json.dumps(meta, ensure_ascii=False), r["id"]))
        except Exception:  # noqa: BLE001
            continue
    _emit("memory.updated", {"op": "unforget", "ids": ids})
    return len(ids)


def now() -> int:
    """The memory's clock, THROUGH the facade — never `time.time()` in a caller.

    `memory/clock.py` supports `travel()` so the timeline corpus can replay 270 simulated days; a caller that read
    the wall clock would date its pills in 2026 while the rest of the run believes it is March. Re-exported for the
    same reason as `canon_slot`: the alternative is every module reaching into a memory internal, which the
    contract test counts as the boundary opening up."""
    return _clock_now()


def canon_slot(slot: str | None) -> str | None:
    """The canonical key for a slot name/alias, THROUGH the facade. Re-exported (not reimplemented) because the
    registry in `memory/slots.py` stays the single vocabulary; this only spares every caller outside the module a
    direct reach into `memory.writer` for one pure lookup — which the contract test counts, correctly, as the
    boundary opening up."""
    return _writer.canon_slot(slot)


def as_of(slot: str, ts: int | None = None) -> dict | None:
    """Bi-temporal (V2-111 §9.2): what value a canonical slot had at a PAST instant — the question that
    `updated` no puede responder de forma fiable (lo toca también el refuerzo y la promoción de nivel, así que
    no es "cuándo se invalidó"). Devuelve la fila más reciente cuyo `valid_at` ya había llegado en `ts` Y que
    todavía no se había invalidado en `ts` (o que nunca se invalidó). `None` si el slot no existía todavía en
    `ts`, o si `slot` no es una clave canónica reconocida — nunca lanza, nunca inventa un valor.

    `ts=None` significa AHORA, o sea «qué valor tiene este slot vigente». Con el parámetro obligatorio, todo
    llamante que solo quisiera el valor actual tenía que importar `memory.clock` para conseguir el `now` — la
    fachada empujando su propio reloj al otro lado de la frontera, que es justo lo que el test de contrato
    (`test_memory_boundary.py`) señaló cuando P0d lo hizo. El reloj es asunto de la memoria, no del llamante."""
    if ts is None:
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
    """Stamp widget(s) in the `recent_widgets` MRU (V2-078): the second narrowing layer for "which widget does this
    refer to?" (open > recently used > catalog). The canvas choke point calls it when a widget becomes OPEN. Emits
    memory.updated so the cached prompt can be rebuilt outside the turn (V2-011)."""
    merged = _state.push_recent_widgets(ids)
    _emit("memory.updated", {"op": "state"})
    return merged


# ── KV genérico (sys_kv) — estado ESTRUCTURADO scopeado que no es el ESTADO raíz del operador ────────────────
# V2-069 «una sola mente»: la memoria-de-relación con cada agente (cápsula) necesita persistir un pequeño estado
# ESTRUCTURADO por (cluster,peer) — objetivo, fase, bucles abiertos — SIN inflar el `state()` raíz (que es la
# conciencia del operador) ni crear una tabla nueva. Reusa `sys_kv` (ya lo usan consolidator/rem). Es scope-partido:
# la clave lleva el scope (`capsule:<cluster>:<peer>`), así el estado de una conversación con un agente vive junto a
# todo lo demás pero AISLADO — nunca se mezcla con el estado del operador. Valor = JSON. µs, directo.
#
# ⚠️ FORMA CONSUMIDA DESDE FUERA (2026-08-24). `sys_kv` es `(key, value)` y el plató de los casos de uso lo
# lee y escribe con SQL DIRECTO sobre el fichero, no por aquí — legítimo, porque corre con el motor APAGADO
# (acarrea los cooldowns de proveedor a través de su `--fresh`, que si no se queman ~20 % del presupuesto de
# cada ronda redescubriendo un escalón ya muerto). Consecuencia para quien toque el schema: cambiar los
# nombres de esas dos columnas NO le falla con ruido — su lectura es fail-open y silenciosa, así que dejaría
# de acarrearlos y la única señal sería que sus tandas vuelven a ir lentas. Avisar antes de tocarlo.
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


# ── USER RULES (V2-046 A1) — reglas de comportamiento impuestas por el operador, persistentes ─────────────
_RULES_CAP = 8


def _norm_rule(text: str) -> str:
    import re
    import unicodedata
    n = unicodedata.normalize("NFKD", (text or "").strip().lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", n).split())     # sin acentos ni puntuación, espacios colapsados


def action_map_active(lang: str) -> list[dict]:
    """Active action-map rows for ONE language (V2-539) — the runtime index loads only these. Facade access
    on purpose (memory-boundary contract): `nucleo/actionmap/` never touches memory internals. Tolerates an
    empty/old DB → []."""
    try:
        rows = _db.get_db().query(
            "SELECT id, phrase, action, source FROM action_map WHERE lang=? AND status='active'", (lang,))
        return [dict(r) for r in rows]
    except Exception:
        return []


def action_map_has_seed(lang: str) -> bool:
    """True if this language's shipped seed pack was already imported (any 'seed' row exists)."""
    try:
        return _db.get_db().query_one(
            "SELECT 1 AS x FROM action_map WHERE lang=? AND source='seed' LIMIT 1", (lang,)) is not None
    except Exception:
        return True  # fail CLOSED for the importer: better to skip a re-import than to double-write blindly


def action_map_seed_version(lang: str) -> int:
    """Which version of the shipped pack this install already imported (0 = none, V2-545).

    `action_map_has_seed` only ever answered «was ANY pack imported», so a better pack shipped later reached
    nobody: every engine that had booted once kept the phrases of the day it was first seeded. This is the
    upgrade key. Legacy installs (rows present, no version recorded) report 1, which is what they hold."""
    try:
        v = kv_get("actionmap.seed_version." + (lang or ""), None)
        if isinstance(v, int):
            return v
        return 1 if action_map_has_seed(lang) else 0
    except Exception:
        return 999   # fail CLOSED for the importer: skipping an upgrade beats re-writing rows blindly


def action_map_set_seed_version(lang: str, version: int) -> None:
    try:
        kv_set("actionmap.seed_version." + (lang or ""), int(version))
    except Exception:
        pass


def action_map_retarget_seed(lang: str, phrase: str, action_json: str) -> bool:
    """Point an UNTOUCHED shipped phrase at a new action (pack upgrade). Returns whether a row changed.

    Only `source='seed'` AND `status='active'` rows move: a phrase the operator disabled, or one the map
    LEARNED, is theirs and survives every upgrade — the same veto rule `action_map_add`'s OR IGNORE encodes."""
    try:
        cur = _db.get_db().query_one(
            "SELECT action FROM action_map WHERE lang=? AND phrase=? AND source='seed' AND status='active'",
            (lang, phrase))
        if not cur or (cur["action"] or "") == action_json:   # sqlite3.Row: index, not .get
            return False
        _db.get_db().execute(
            "UPDATE action_map SET action=? WHERE lang=? AND phrase=? AND source='seed' AND status='active'",
            (action_json, lang, phrase))
        return True
    except Exception:
        return False


def action_map_add(lang: str, phrase: str, action_json: str, *, source: str = "seed",
                   status: str = "active") -> None:
    """Insert one action-map row (idempotent: UNIQUE(lang, phrase) + OR IGNORE — an existing row, including
    one the user disabled or retargeted, is NEVER overwritten; that is how a veto survives a seed upgrade)."""
    import time as _time
    try:
        _db.get_db().execute(
            "INSERT OR IGNORE INTO action_map (lang, phrase, action, source, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (lang, phrase, action_json, source, status, int(_time.time())))
    except Exception:
        pass


def action_map_hit(entry_id: int) -> None:
    """Bump a row's hit counter (fire-and-forget bookkeeping; the turn never waits on it)."""
    import time as _time
    try:
        _db.get_db().execute("UPDATE action_map SET hits = hits + 1, last_hit_at = ? WHERE id = ?",
                             (int(_time.time()), entry_id))
    except Exception:
        pass


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


# ── PRESENTACIÓN: vive en `_prompt.py` desde la auditoría del 2026-08-23 (H3) ────────────────────────────
# La fachada sigue exponiendo estos nombres tal cual —el trinquete de superficie lo exige y ningún llamador
# cambia—, pero su cuerpo ya no engorda este fichero. Lo que se movió es lo que PINTA para un modelo; lo
# que decide QUÉ se recupera (`query`, `background_slot_off_topic`) se queda aquí, con el resto de datos.
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


from ._prompt import (  # noqa: E402,F401
    compose_state, critical_facts, recent_short, recent_window, salient_long, seconds_since_last_conv)


def _pack(memories: list[dict], budget_tokens: int) -> list[dict]:
    """Truncate the list to the token budget (approximately chars/4)."""
    out, used = [], 0
    for m in memories:
        cost = max(1, len(m.get("text", "")) // _CHARS_PER_TOKEN)
        if used + cost > budget_tokens and out:
            break
        out.append(m)
        used += cost
    return out


def reinforce_ids_for(mems: list[dict]) -> list[int]:
    """Qué píldoras de un paquete cuentan como USADAS. Una sola casa para la política.

    Refuerzo SELECTIVO: el paquete puede incluir conceptos, vecinos de grafo y resultados laterales para dar
    contexto al cerebro. Reforzar todos ellos convierte una consulta sobre vivienda en "uso" de la alergia, la
    infancia o cualquier otro resultado empaquetado. Sin un feedback explícito del LLM sobre qué leyó, la señal
    honesta es el primer recuerdo de contenido (los nodos conceptuales son índices, no recuerdos vividos). Esto
    evita crecimiento neuronal artificial.

    Sale de dentro de `query()` (V2-311, 2026-08-25) porque el refuerzo dejó de dispararse al CALCULAR el recall
    y pasó a dispararse al ENTREGARLO — y quien entrega no es esta función. Lo que NO se mueve es la política:
    si el disparador se llevara consigo la selección, el llamante reforzaría los `ids` enteros (40 píldoras en
    vez de 1) y el refuerzo selectivo desaparecería sin que fallara nada. La decisión se queda aquí; fuera solo
    viaja el momento."""
    return [m["id"] for m in mems if m.get("kind") != "concept"][:1]


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
    a_reforzar = reinforce_ids_for(mems)
    if reinforce_used and a_reforzar:
        reinforce(a_reforzar)  # escritura async (el acceso resetea el decay)
    return {"state": st, "memories": mems, "ids": ids, "reinforce_ids": a_reforzar}


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



def clear_conversation() -> int:
    """Invalidates the VERBATIM conversational buffer (`level='short'`, `meta.source='conv'` — what
    `recent_window` reads and the voice provider re-seeds its window from after a reconnect).

    Exists for the RESET (operator, 2026-08-31, measured live): he reset, the frontend chat cleared, the engine
    restarted — and the first greeting said «sigo con lo del digestólogo» because the window was re-seeded from
    this very buffer. «El chat se borra» has to include the seed, or the wiped conversation walks back in
    through the side door. SOFT invalidation (`valid=0`), same doctrine as `forget`: gone from every read,
    kept for audit. Touches ONLY conv records — facts, profile, triaged messages and worker results survive."""
    db = _db.get_db()
    rows = db.query("SELECT id FROM memories WHERE valid=1 AND level='short' "
                    "AND json_extract(meta,'$.source')='conv'")
    ids = [r["id"] for r in rows]
    if not ids:
        return 0
    ph = ",".join("?" * len(ids))
    db.execute(f"UPDATE memories SET valid=0, updated=? WHERE id IN ({ph})", (_clock_now(), *ids))
    _emit("memory.updated", {"op": "clear_conversation", "n": len(ids)})
    return len(ids)


def clear_slot_prefix(prefix: str) -> int:
    """Invalidates every pill whose SLOT starts with `prefix` (soft, `valid=0` — audit keeps them). The write
    twin of `by_slot_prefix`, with the same LIKE escaping (slots carry `_` naturally; unescaped, `task.` would
    also match `taskX`). Born for the reset wiping `task.*` — the durable «we are in the middle of X» pills that
    made a fresh session claim to still be working (2026-08-31). Generic on purpose: any namespaced catalogue
    can be retired by its prefix."""
    pref = (prefix or "").strip()
    if not pref:
        return 0
    db = _db.get_db()
    esc = pref.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = db.query("SELECT id FROM memories WHERE valid=1 AND slot LIKE ? ESCAPE '\\'", (esc + "%",))
    ids = [r["id"] for r in rows]
    if not ids:
        return 0
    ph = ",".join("?" * len(ids))
    db.execute(f"UPDATE memories SET valid=0, updated=? WHERE id IN ({ph})", (_clock_now(), *ids))
    _emit("memory.updated", {"op": "clear_slot_prefix", "prefix": pref, "n": len(ids)})
    return len(ids)


def by_slot_prefix(prefix: str, *, limit: int = 20, newest_first: bool = True) -> list[dict]:
    """Las píldoras cuyo SLOT empieza por `prefix` — lectura DIRECTA por clave (µs, sin embeddings ni reranker).

    Existe para leer un CATÁLOGO namespaced sin pagar el recall semántico: «¿qué electricistas tenemos?» sobre
    `candidato:electricista:` es un SELECT por prefijo, no una consulta por significado (V2-260). Pasar por
    `query()` costaría embedding + RRF + reranker —cientos de ms— para responder algo que la clave ya ordena, y
    en el caso de uso que esto sirve el criterio de éxito es justamente que NO se dispare el proceso caro.

    El prefijo se ESCAPA antes de entrar en el `LIKE`: `_` y `%` son comodines de SQL y los slots llevan
    guiones bajos con naturalidad, así que sin escapar `candidato:aire_acondicionado:` devuelve también
    `candidato:aireXacondicionado:` — comprobado. El separador del prefijo lo pone el llamador (terminar en
    `:` es lo que evita que `candidato:electricista:` arrastre `candidato:electricista_industrial:`).

    Solo `valid=1`: la caducidad es de `ttl_days` y la aplica el consolidador (`created + ttl_days`), no el
    decay — el decay baja el PESO con vida media de 693 días, que para un catálogo no es caducar. Y misma
    CUARENTENA por confianza que el resto de lecturas que pueden acabar en un prompt: lo `untrusted` no sale.
    """
    pref = (prefix or "").strip()
    if not pref:
        return []
    esc = pref.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    db = _db.get_db()
    order = "updated DESC, id DESC" if newest_first else "updated ASC, id ASC"
    rows = db.query(
        "SELECT id, level, kind, text, slot, importance, weight, created, updated FROM memories "
        "WHERE valid=1 AND slot LIKE ? ESCAPE '\\' "
        "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted') "
        f"ORDER BY {order} LIMIT ?", (esc + "%", max(1, int(limit))))
    return [dict(r) for r in rows if (r["text"] or "").strip()]


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


# ── workflows (V2-594) ────────────────────────────────────────────────────────────────────────────────────
# Facade access on purpose (memory-boundary contract): `nucleo/workflows/` never touches memory internals.
def workflows_for(domain: str) -> list[dict]:
    """Every row for one errand domain, best rank first — INCLUDING the negative ones, because «the mesh has
    nothing for this» is the answer that saves the most work and the caller has to see it."""
    try:
        rows = _db.get_db().query(
            "SELECT id, domain, channel, rank, status, source, target, evidence, ttl_s, checked_at "
            "FROM workflows WHERE domain=? ORDER BY rank ASC", (domain,))
        return [dict(r) for r in rows]
    except Exception:
        return []


def workflow_upsert(domain: str, channel: str, *, status: str = "active", rank: int = 100,
                    source: str = "learned", target: str = "", evidence: str = "",
                    ttl_s: int = 7 * 24 * 3600) -> None:
    """Write what was just learned about (domain, channel). Unlike `action_map_add` this REPLACES on conflict:
    an action-map row carries a user's veto that a seed upgrade must never overwrite, while a workflow row is
    a perishable observation about the outside world — the whole point is that the newest measurement wins.
    A row the OPERATOR pinned is protected by the caller, which refuses to overwrite `source='operator'`."""
    import time as _time
    now = int(_time.time())
    try:
        _db.get_db().execute(
            "INSERT INTO workflows (domain, channel, rank, status, source, target, evidence, ttl_s, "
            "checked_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(domain, channel) DO UPDATE SET status=excluded.status, rank=excluded.rank, "
            "source=excluded.source, target=excluded.target, evidence=excluded.evidence, "
            "ttl_s=excluded.ttl_s, checked_at=excluded.checked_at",
            (domain, channel, int(rank), status, source, target, evidence, int(ttl_s), now, now))
    except Exception:
        pass


def workflow_hit(entry_id: int) -> None:
    """Bump a row's hit counter (fire-and-forget bookkeeping; the turn never waits on it)."""
    import time as _time
    try:
        _db.get_db().execute("UPDATE workflows SET hits = hits + 1, last_hit_at = ? WHERE id = ?",
                             (int(_time.time()), entry_id))
    except Exception:
        pass


def workflow_forget(domain: str, channel: str = "") -> None:
    """Drop a domain's rows (all of them, or one channel). Used when the operator corrects the route, and by
    the tests. Deliberately a delete and not a status flip: a stale route that is merely disabled would still
    be read by anything that forgets to filter."""
    try:
        if channel:
            _db.get_db().execute("DELETE FROM workflows WHERE domain=? AND channel=?", (domain, channel))
        else:
            _db.get_db().execute("DELETE FROM workflows WHERE domain=?", (domain,))
    except Exception:
        pass
