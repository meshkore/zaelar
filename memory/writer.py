"""memory/writer.py — el ÚNICO escritor de la memoria (V2-002 · T45).

Todas las mutaciones de la BD pasan por aquí, y SOLO las invoca el consumidor de `memory/queue.py` (un único
consumidor → cero colisiones de escritura; los lectores van en WAL sin bloquear). Cada inserción de recuerdo
calcula su **embedding LOCAL** (`memory/embeddings.py`) y sincroniza las tres representaciones: la fila en
`memories`, el vector en `vec_memories` (si sqlite-vec está disponible) y el índice keyword en `fts_memories`
(FTS5 con `content='memories'` → índice externo que hay que mantener a mano).

Las funciones son SÍNCRONAS y operan sobre `db.get_db()` (serializado por su RLock). El writer no sabe de
asyncio: la serialización de orden la da la cola; la seguridad de la conexión la da el lock del `Database`.
"""
import json
import os
import re
import struct
import time

from . import db as _db
from . import embeddings as _emb

# refuerzo por uso: cada acceso sube el peso este paso (con techo 1.0) y RESETEA la recencia.
REINFORCE_STEP = 0.1

# Dedup SEMÁNTICO al insertar (V2-013 · T125): antes de crear un recuerdo DURABLE sin `slot`, se busca por
# SIGNIFICADO (embedding) si YA existe uno casi idéntico; si la distancia L2 (vectores normalizados) es ≤ este
# umbral → se REFUERZA el existente en vez de duplicar. Calibrado con embeddinggemma vía el test bot: el MISMO
# hecho en distintos fraseos cae ≤0.51; hechos que solo comparten ENTIDAD (misma persona, info distinta) ≥0.80.
# 0.45 = umbral CONSERVADOR: fusiona solo paráfrasis muy próximas (evita el falso positivo que perdía info —
# "Laura es mi jefa" vs "Laura me pidió el informe" NO deben fusionarse). Preferimos un casi-duplicado (inocuo) a
# una fusión que pierde información. Configurable/desactivable (`MEM_DEDUP_MAX_DIST`/`MEM_SEMANTIC_DEDUP`).
SEMANTIC_DEDUP_MAX_DIST = float(os.getenv("MEM_DEDUP_MAX_DIST", "0.45"))


def _semantic_dedup_on() -> bool:
    return os.getenv("MEM_SEMANTIC_DEDUP", "1").strip().lower() not in ("0", "false", "no", "off")


_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    """Normaliza para comparar texto (dedup exacto por slot): trim + minúsculas + espacios colapsados."""
    return _WS.sub(" ", (text or "").strip().lower())


# SEGURIDAD MÉDICA (auditoría de memoria 2026-07-14): una ALERGIA/intolerancia es un hecho ADITIVO y CRÍTICO. El
# CORAZÓN LLM la mis-asignaba al slot SINGULAR `operator.diet` (pese a que el registro dice "NUNCA alergias") → una
# DIETA declarada después ("soy vegetariana") caía en el mismo slot y SUPERSEDÍA/BORRABA la alergia. Olvidar una
# alergia es un fallo de seguridad. Detector DETERMINISTA (es/en) para el guard del writer — el ÚNICO chokepoint por
# el que pasa TODA escritura (voz, worker, widget, heurística) → la protección es universal.
_CRITICAL_HEALTH_RE = re.compile(
    r"\b(al[eé]rgic[oa]s?|alergia|anafila|intoleran(?:te|cia)|"
    r"allerg(?:ic|y)|intoleran(?:t|ce)|"
    r"celiac[oa]|cel[íi]ac[oa]|diab[eé]tic[oa]|diabetes|epil[eé]p|marcapasos|anticoagul|"
    r"asm[aá]tic[oa])\b", re.I)


def _is_critical_health(text: str) -> bool:
    return bool(_CRITICAL_HEALTH_RE.search(text or ""))


def _stamp_critical(meta):
    """Marca meta.critical='health' preservando lo que hubiera (dict/JSON/None)."""
    if isinstance(meta, dict):
        return {**meta, "critical": "health"}
    if isinstance(meta, str) and meta.strip():
        try:
            d = json.loads(meta)
            if isinstance(d, dict):
                d["critical"] = "health"
                return d
        except Exception:
            pass
        return meta
    return {"critical": "health"}

# importancia base por tipo de recuerdo (I0). Ajustable por perfil.
_IMPORTANCE_BY_KIND = {
    "fact": 0.7,
    "pref": 0.7,
    "insight": 0.65,
    "summary": 0.55,
    "event": 0.5,
    "msg": 0.4,
}


def _now() -> int:
    return int(time.time())


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


# NORMALIZACIÓN DE SLOTS (V2-038 retest 2026-07-14 · registro canónico 2026-07-14): el CORAZÓN (LLM) emite
# nombres de slot a su aire ('location', 'ubicacion', 'name'…) mientras la heurística usa los canónicos
# ('operator.location'…) → DOS linajes del MISMO hecho singular que nunca se superseden entre sí (píldoras
# contradictorias coexistiendo: Soria + Valencia + Bilbao a la vez). El writer es el ÚNICO punto por el que
# pasa TODA escritura → se normaliza AQUÍ, para todos los escritores. El vocabulario y sus alias viven en el
# REGISTRO ÚNICO `memory/slots.py` (compartido con el agente de memoria y el prompt del procesador — las tres
# capas ya no pueden divergir). Slots desconocidos/namespaced pasan lowercased/stripped.
from . import slots as _slots


def canon_slot(slot: str | None) -> str | None:
    """Slot canónico: lowercase + strip + alias → una sola lengua de slots para el supersede exacto."""
    return _slots.canonical(slot)


def insert_memory(
    text: str,
    *,
    level: str = "short",
    kind: str = "event",
    importance: float | None = None,
    weight: float = 0.5,
    ttl_days: float | None = None,
    pinned: bool = False,
    slot: str | None = None,
    meta: dict | str | None = None,
    concepts: list[str] | None = None,
    embedding: list[float] | None = None,
) -> int:
    """Inserta un recuerdo (PÍLDORA: dato canónico + `slot` + `meta`) + su vector + su fila FTS. Devuelve el id.

    **Supersede/dedup por SLOT (V2-013, exacto, sin LLM)**: si se pasa `slot` (clave canónica del hecho singular,
    p. ej. `operator.name`), miramos el recuerdo VIGENTE con ese slot:
      - si su texto normalizado es IGUAL → es el mismo dato repetido: `reinforce` (sube peso) y NO se duplica;
        devuelve el id existente.
      - si difiere → el hecho cambió (mudanza, nuevo objetivo): inserta el nuevo y marca el viejo `valid=0,
        superseded_by=nuevo` ("el más reciente MANDA").
    Calcula el embedding si no se pasa."""
    db = _db.get_db()
    now = _now()
    if importance is None:
        importance = _IMPORTANCE_BY_KIND.get(kind, 0.5)

    slot = canon_slot(slot)                     # una sola lengua de slots (alias del LLM → canónico)
    # GUARD DE SEGURIDAD MÉDICA (auditoría 2026-07-14): una alergia/intolerancia NUNCA puede llevar un slot SINGULAR
    # (identidad) — la borraría un dato posterior del mismo slot (una dieta pisaba la alergia). Se le retira el slot
    # (queda ADITIVA: varias alergias coexisten, dedup semántico funde repeticiones), se fija pinned + importancia
    # alta, y se marca meta.critical='health' para que el ESTADO la surface SIEMPRE (fuera del cap de salient_long).
    if _is_critical_health(text):
        if slot in _slots.identity_slots():
            slot = None
        pinned = True
        importance = max(float(importance), 0.95)
        meta = _stamp_critical(meta)
    meta_json = meta if isinstance(meta, (str, type(None))) else json.dumps(meta, ensure_ascii=False)
    prev_ids: list[int] = []
    if slot:
        # TODOS los vigentes del slot (no LIMIT 1): si por cualquier vía (alias sin normalizar de antes, unforget,
        # legacy) coexisten 2+ vigentes del mismo hecho singular, la SIGUIENTE escritura los colapsa TODOS —
        # el supersede es auto-curativo ("el más reciente MANDA" de verdad). V2-038 retest: se encontraron 4
        # píldoras de ubicación vigentes a la vez.
        # El SELECT expande por ALIAS (auditoría de memoria 2026-07-14): matchea la clave canónica Y sus variantes
        # legacy (`operator.location` colapsa también un `location`/`ubicacion` crudo que quedara sin normalizar),
        # así el colapso por slot es INMEDIATO y NO depende de que el sueño del consolidador (`heal_slots`) pase antes
        # — cierra el residuo del retest (dos píldoras contradictorias del mismo hecho conviviendo con claves distintas).
        # desempate por id (orden de inserción): `updated` tiene resolución de segundo — sin él, "el más
        # reciente" era arbitrario entre escrituras del mismo segundo (mismo fix que recent_short, V2-013).
        _keys = _slots.equivalent_keys(slot) or [slot]
        _ph = ",".join("?" * len(_keys))
        rows = db.query(
            f"SELECT id, text FROM memories WHERE slot IN ({_ph}) AND valid=1 ORDER BY updated DESC, id DESC",
            tuple(_keys))
        if rows:
            if _norm(rows[0]["text"]) == _norm(text):
                keep = int(rows[0]["id"])
                reinforce([keep])               # mismo dato → refuerza, no duplica
                _link_concepts(db, keep, concepts, level, kind)  # asegura aristas del grafo (idempotente)
                stale = [int(r["id"]) for r in rows[1:]]
                if stale:                       # duplicados rezagados del mismo slot → colapsa igualmente
                    ph = ",".join("?" * len(stale))
                    db.execute(f"UPDATE memories SET valid=0, superseded_by=?, updated=? WHERE id IN ({ph})",
                               (keep, now, *stale))
                return keep
            prev_ids = [int(r["id"]) for r in rows]   # dato cambió → superseder TODOS los vigentes tras insertar

    # DEDUP SEMÁNTICO (T125): durable + SIN slot → si ya existe un recuerdo casi idéntico por SIGNIFICADO,
    # refuerza en vez de duplicar ("me llamo Ricard" = "soy Ricard" = "Ricard"). Reutiliza el embedding calculado.
    if not slot and level in ("mid", "long") and db.vec_available and _semantic_dedup_on():
        if embedding is None:
            embedding = _emb.embed(text)
        dup = _find_semantic_dup(db, embedding)
        if dup is not None:
            reinforce([dup])
            _link_concepts(db, dup, concepts, level, kind)   # el hecho repetido conserva/gana sus aristas de concepto
            return dup

    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO memories (level, kind, text, importance, weight, access_count,
                                     last_access, ttl_days, pinned, valid, slot, meta, created, updated)
               VALUES (?,?,?,?,?,0,?,?,?,1,?,?,?,?)""",
            (level, kind, text, float(importance), float(weight), now,
             ttl_days, 1 if pinned else 0, slot, meta_json, now, now),
        )
        mid = cur.lastrowid
        # FTS5 externo (content='memories'): mantener a mano, rowid = id del recuerdo.
        if db.fts_available:
            cur.execute("INSERT INTO fts_memories (rowid, text) VALUES (?, ?)", (mid, text))
        if prev_ids:                            # TODO hecho vigente con este slot queda superseded
            ph = ",".join("?" * len(prev_ids))
            cur.execute(f"UPDATE memories SET valid=0, superseded_by=?, updated=? WHERE id IN ({ph})",
                        (mid, now, *prev_ids))
    # embedding fuera del lock de escritura del cursor (puede tardar) → luego insert corto en vec.
    # OPTIMIZACIÓN (2026-07-12): el BUFFER CONVERSACIONAL (`kind='conv'`, el par turno↔respuesta crudo que se
    # escribe CADA turno, efímero TTL 2d) NO se embebe: (a) se lee por RECENCIA (`recent_short`, SQL directo), nunca
    # por vector; (b) `compose_recall` lo excluye — es más, la charla cruda COPABA el top del retriever y enterraba
    # el hecho durable. Embeberlo era un cálculo de embedding (embeddinggemma/Ollama → GPU) por turno GASTADO, que
    # además compite con STT/TTS locales. El CORAZÓN (`mem_processor`) ya destila lo memorable en píldoras aparte
    # (esas SÍ se embeben). Para que un conv nunca acabe durable sin vector, `consolidator.promote` lo excluye.
    # ENFORCEMENT de espacio vectorial (auditoría 2026-07-19 P0-1): jamás insertar en el índice un vector de OTRO
    # espacio — ni de firma discordante (embedsig ≠ backend activo: pasó 2 días con fastembed/bge-EN sobre índice
    # embeddinggemma, misma dim → cero errores, recall corrompido) ni de degradación a hash en caliente. En esos
    # casos la píldora queda SIN vector + `meta.embed_pending=1` (recuperable por FTS; el sueño la re-embebe).
    if db.vec_available and kind != "conv":
        pending_reason = None
        if not _embed_sig_ok():
            pending_reason = "sig_mismatch"
            vec = None
        else:
            vec = embedding if embedding is not None else _emb.embed(text)
            if embedding is None and getattr(_emb, "last_degraded", False):
                pending_reason = "degraded"
                vec = None
        if vec is not None:
            try:
                db.execute("INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)", (mid, _pack(vec)))
            except Exception:
                pending_reason = "insert_failed"   # píldora committeada sin vector (P2-11) → reparable, no huérfana
        if pending_reason is not None:
            _mark_embed_pending(db, mid, pending_reason)

    _link_concepts(db, mid, concepts, level, kind)
    return mid


_SIG_CACHE: tuple[float, bool] = (0.0, True)


def _embed_sig_ok() -> bool:
    """¿La firma del backend ACTIVO casa con la sellada en el índice? Cacheado 60s (se consulta por inserción)."""
    global _SIG_CACHE
    now = time.time()
    if now - _SIG_CACHE[0] < 60:
        return _SIG_CACHE[1]
    ok = True
    try:
        from . import reembed as _reembed
        stored = _reembed.stored_signature()
        ok = stored is None or stored == _reembed.signature()
    except Exception:
        ok = True   # fail-open: sin veredicto no se bloquea la escritura de vectores
    _SIG_CACHE = (now, ok)
    return ok


def _mark_embed_pending(db, mid: int, reason: str) -> None:
    try:
        row = db.query_one("SELECT meta FROM memories WHERE id=?", (mid,))
        meta = json.loads(row["meta"] or "{}") if row else {}
        meta["embed_pending"] = reason
        db.execute("UPDATE memories SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), mid))
    except Exception:
        pass


def _link_concepts(db, mid: int, concepts: list[str] | None, level: str, kind: str) -> None:
    """GRAFO DE CONCEPTOS (V2-013 T126): organiza la memoria conceptualmente (alergia↔salud, hipoteca↔finanzas…).
    Crea/reusa un NODO-concepto (fila kind='concept', recuperable por FTS/vector) y enlaza píldora↔concepto en
    `edges` (bidireccional). En la LECTURA una query de categoría casa el nodo por FTS y `graph_expand` aflora el
    cluster — sin LLM. IDEMPOTENTE (link = INSERT OR REPLACE, nodo reutilizado): se llama también al reforzar un
    hecho repetido, para que un dato dicho antes-de-T126 o sin etiqueta gane sus aristas al repetirse. Cap 3."""
    if level not in ("mid", "long") or kind == "concept":
        return
    cs = [c for c in (concepts or []) if c]
    if not cs:
        # El CORAZÓN LLM a veces OMITE `concepts` (los emite vacíos) → la píldora durable quedaba SIN aristas y una
        # query de CATEGORÍA ("mis viajes", "mi trayectoria") no podía alcanzarla por graph_expand (bug del ciclo
        # 2026-07-12: viaje a Tailandia / eventos laborales fechados guardados pero irrecuperables por categoría).
        # Backstop DETERMINISTA: derivar los conceptos del TEXTO (mismo `derive_concepts` que el resto del sistema).
        try:
            from memory.concepts import derive_concepts
            row = db.query_one("SELECT text FROM memories WHERE id=?", (mid,))
            cs = derive_concepts(row["text"]) if row and row["text"] else []
        except Exception:
            cs = []
    for c in list(cs)[:3]:
        cid = _get_or_create_concept(db, c)
        if cid and cid != mid:
            link(mid, cid, "about", 1.0)
            link(cid, mid, "about", 1.0)         # bidireccional → graph_expand desde el nodo trae las píldoras


def _get_or_create_concept(db, name: str) -> int | None:
    """Nodo-concepto SINGLETON por nombre (fila kind='concept', hub del grafo). Reutiliza el existente (por texto
    normalizado) o lo crea con su fila FTS + vector para que una query de categoría lo encuentre. Sin slot (el
    supersede lo mataría) y sin dedup semántico (no debe fundirse con una píldora). Best-effort → None si falla."""
    n = _norm(name).strip()
    if not n:
        return None
    try:
        row = db.query_one(
            "SELECT id FROM memories WHERE kind='concept' AND valid=1 AND lower(text)=? LIMIT 1", (n,)
        )
        if row is not None:
            return int(row["id"])
        now = _now()
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO memories (level, kind, text, importance, weight, access_count,
                                         last_access, ttl_days, pinned, valid, slot, meta, created, updated)
                   VALUES (?, 'concept', ?, 0.3, 0.5, 0, ?, NULL, 1, 1, NULL, NULL, ?, ?)""",
                ("long", n, now, now, now),
            )
            cid = cur.lastrowid
            if db.fts_available:
                cur.execute("INSERT INTO fts_memories (rowid, text) VALUES (?, ?)", (cid, n))
        if db.vec_available:
            db.execute("INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)", (cid, _pack(_emb.embed(n))))
        return int(cid)
    except Exception:
        return None


def _find_semantic_dup(db, vec: list[float]) -> int | None:
    """Vecino más cercano DURABLE y válido por SIGNIFICADO. Devuelve su id si la distancia ≤ umbral, si no None.
    Best-effort: cualquier fallo del backend vectorial → None (se inserta normal)."""
    try:
        rows = db.query(
            "SELECT memory_id, distance FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT 5",
            (_pack(vec),),
        )
    except Exception:
        return None
    for r in rows:
        if r["distance"] is None or r["distance"] > SEMANTIC_DEDUP_MAX_DIST:
            break                               # ordenado por distancia: si el mejor ya no cuela, ninguno
        m = db.query_one(
            "SELECT id FROM memories WHERE id=? AND valid=1 AND level IN ('mid','long')",
            (r["memory_id"],),
        )
        if m is not None:
            return int(m["id"])
    return None


def reinforce(ids: list[int], step: float = REINFORCE_STEP) -> None:
    """Refuerzo por uso: access_count++, last_access=now, weight=min(1, weight+step). El acceso resetea decay."""
    if not ids:
        return
    db = _db.get_db()
    now = _now()
    with db.cursor() as cur:
        for mid in ids:
            cur.execute(
                """UPDATE memories
                   SET access_count = access_count + 1,
                       last_access  = ?,
                       weight       = MIN(1.0, weight + ?),
                       updated      = ?
                   WHERE id = ?""",
                (now, float(step), now, int(mid)),
            )


def link(from_id: int, to_id: int, type: str, weight: float = 1.0) -> None:
    """Crea/actualiza una arista del grafo (idempotente por la PK (from_id, to_id, type))."""
    db = _db.get_db()
    db.execute(
        "INSERT OR REPLACE INTO edges (from_id, to_id, type, weight) VALUES (?,?,?,?)",
        (int(from_id), int(to_id), str(type), float(weight)),
    )


def set_pinned(mid: int, pinned: bool) -> None:
    db = _db.get_db()
    db.execute(
        "UPDATE memories SET pinned=?, updated=? WHERE id=?",
        (1 if pinned else 0, _now(), int(mid)),
    )


def supersede(old_id: int, new_id: int) -> None:
    """Marca un recuerdo como superado por otro (conflicto temporal; el consolidador también lo usa)."""
    db = _db.get_db()
    db.execute(
        "UPDATE memories SET valid=0, superseded_by=?, updated=? WHERE id=?",
        (int(new_id), _now(), int(old_id)),
    )


def delete_memory(mid: int) -> None:
    """Borra un recuerdo y sus representaciones (vec/fts). Solo el consolidador debería llamar esto."""
    db = _db.get_db()
    mid = int(mid)
    row = db.query_one("SELECT text FROM memories WHERE id=?", (mid,))
    with db.cursor() as cur:
        if db.fts_available and row is not None:
            # FTS5 externo: borrado explícito con la sintaxis 'delete'.
            cur.execute(
                "INSERT INTO fts_memories (fts_memories, rowid, text) VALUES ('delete', ?, ?)",
                (mid, row["text"]),
            )
        cur.execute("DELETE FROM memories WHERE id=?", (mid,))
        cur.execute("DELETE FROM edges WHERE from_id=? OR to_id=?", (mid, mid))
    if db.vec_available:
        db.execute("DELETE FROM vec_memories WHERE memory_id=?", (mid,))


# operaciones despachables desde la cola: op -> callable
OPS = {
    "write": insert_memory,
    "reinforce": reinforce,
    "link": link,
    "pin": lambda mid: set_pinned(mid, True),
    "unpin": lambda mid: set_pinned(mid, False),
    "supersede": supersede,
    "delete": delete_memory,
}
