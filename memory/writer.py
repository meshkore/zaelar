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
#
# BACKEND-DEPENDIENTE (hallazgo auditoría 2026-07-26): el umbral 0.45 es la geometría de UN modelo (embeddinggemma)
# — otro backend no comparte esa escala de distancias. Medido en vivo con `fastembed` (el backend ACTIVO hoy,
# `config/v2.json §memory.embed_provider`): frases COMPLETAMENTE NO RELACIONADAS ("Te quiero, ánimo con el libro."
# vs. "El técnico de la caldera viene el jueves por la mañana.") caían a distancia ≤0.45 y se FUSIONABAN — el
# mensaje nuevo se perdía por completo, reforzando el viejo en su lugar. Justo la fusión-con-pérdida que el diseño
# dice evitar. Sin una calibración propia por backend (mismo estudio que produjo 0.45/0.51/0.80 para
# embeddinggemma), el dedup semántico solo se activa con el backend para el que SÍ está calibrado; con cualquier
# otro cae a dedup EXACTO/por-slot (determinista, sin falsos positivos) — un casi-duplicado inocuo vale más que
# perder un dato.
SEMANTIC_DEDUP_MAX_DIST = float(os.getenv("MEM_DEDUP_MAX_DIST", "0.45"))
_SEMANTIC_DEDUP_CALIBRATED_BACKENDS = {"ollama"}   # el único backend con el estudio de distancias detrás del umbral


def _semantic_dedup_on() -> bool:
    if os.getenv("MEM_SEMANTIC_DEDUP", "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    return _emb.active_backend() in _SEMANTIC_DEDUP_CALIBRATED_BACKENDS


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


# UNA LIMITACIÓN DE INGESTIÓN NO SIEMPRE TRAE SU PALABRA DE CATEGORÍA (V2-499, 2026-08-29, autorizado por el
# operador aceptando los falsos positivos). El detector de arriba casa la CATEGORÍA («alérgico», «celíaco»,
# «intolerante»), y así es como la gente lo dice la mitad de las veces; la otra mitad dice lo que NO PUEDE HACER:
# «no puede comer gluten», «no puedo tomar lactosa». Esa frase no contiene ninguna de las palabras del catálogo,
# así que no se marcaba `critical`, no llegaba a la línea ⚠️ CRÍTICO y quedaba compitiendo por una plaza del
# ranking — que es exactamente el fallo que V2-490 midió con macarrones ofrecidos a un celíaco.
#
# El COSTE está aceptado y es real, así que conviene decirlo entero: aquí un falso positivo no es inocuo, porque
# la línea crítica tiene cap (6) y una frase social colada puede EXPULSAR un marcapasos — el daño que V2-491
# acababa de cerrar. Por eso se acota por la única vía que no exige adivinar: una restricción que NOMBRA UN
# MOMENTO («hoy no puedo comer»,«ahora no puedo tomar nada») habla de ese momento, no de la persona, y queda
# fuera. Lo que NO se filtra, a propósito, es lo ambiguo sin marca temporal («no puedo comer más»): descartarlo
# exigiría entender la frase, y ante la duda esta línea existe para pecar de más.
_INGESTION_LIMIT_RE = re.compile(
    r"(?:\bno\s+(?:puede[ns]?|puedo|debe[ns]?|debo)\s+(?:comer|tomar|beber|ingerir|probar|consumir)\b"
    r"|\b(?:can(?:no|')?t|cannot|must\s+not|mustn'?t)\s+(?:eat|drink|have|take|consume)\b)", re.I)

# Una restricción fechada en un momento concreto no es un hecho durable de la persona.
_MOMENTARY_RE = re.compile(
    r"\b(hoy|ahora\s+mismo|ahora|esta\s+noche|este\s+rato|luego|m[aá]s\s+tarde|"
    r"today|tonight|right\s+now|later)\b", re.I)


def _is_critical_health(text: str) -> bool:
    t = text or ""
    if _CRITICAL_HEALTH_RE.search(t):
        return True
    return bool(_INGESTION_LIMIT_RE.search(t)) and not _MOMENTARY_RE.search(t)


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
    from .clock import now
    return now()


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
                    db.execute(f"UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? "
                               f"WHERE id IN ({ph})", (keep, now, now, *stale))
                return keep
            prev_ids = [int(r["id"]) for r in rows]   # dato cambió → superseder TODOS los vigentes tras insertar

    # DEDUP EXACTO en la escritura (V2-103, 2026-08-16): durable + SIN slot → si el MISMO texto (normalizado por
    # mayúsculas) ya está vigente, refuerza en vez de duplicar. Antes solo existía cada hora en
    # `consolidator.dedup()` — la ventana de una hora dejaba pasar duplicados literales del mismo hecho escritos
    # segundos aparte (auditoría en vivo: "Su suegro se llama Pedro." insertado dos veces, 3s de diferencia,
    # ambas filas `valid=1`). Independiente del backend de embeddings (nunca falla en silencio si Ollama está
    # degradado) — defensa en profundidad respecto del dedup SEMÁNTICO de abajo, que sigue cubriendo las
    # paráfrasis. `conv` queda fuera a propósito: el buffer conversacional debe poder repetir texto literal
    # ("sí", "vale") sin colapsar.
    if not slot and kind != "conv":
        exact = db.query_one(
            "SELECT id FROM memories WHERE valid=1 AND kind != 'conv' AND LOWER(text)=LOWER(?) "
            "ORDER BY id DESC LIMIT 1",
            (text,),
        )
        if exact is not None:
            dup_id = int(exact["id"])
            reinforce([dup_id])
            _link_concepts(db, dup_id, concepts, level, kind)
            return dup_id

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
                                     last_access, ttl_days, pinned, valid, slot, meta, created, updated, valid_at)
               VALUES (?,?,?,?,?,0,?,?,?,1,?,?,?,?,?)""",
            (level, kind, text, float(importance), float(weight), now,
             ttl_days, 1 if pinned else 0, slot, meta_json, now, now, now),
        )
        mid = cur.lastrowid
        # FTS5 externo (content='memories'): mantener a mano, rowid = id del recuerdo.
        if db.fts_available:
            cur.execute("INSERT INTO fts_memories (rowid, text) VALUES (?, ?)", (mid, text))
        if prev_ids:                            # TODO hecho vigente con este slot queda superseded
            ph = ",".join("?" * len(prev_ids))
            cur.execute(f"UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? "
                        f"WHERE id IN ({ph})", (mid, now, now, *prev_ids))
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
    # casos la píldora queda SIN vector y se marca `meta.embed_pending` (recuperable por FTS; el sueño la
    # re-embebe). ⚠️ El valor del marcador es el MOTIVO, una cadena — hoy `"sig_mismatch"` o `"degraded"` —
    # NUNCA un 1. Este comentario decía `=1` y esa mentira costó un diagnóstico el 2026-08-24: una consulta
    # `embed_pending = 1` devuelve CERO sobre una base contaminada, o sea que informa de «limpio» justo
    # cuando hay daño. Se consulta como lo hace el producto: `IS NOT NULL` (`rem.py::report`).
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
            # SEGUNDA comprobación, y es la que DECIDE (V2-484). La de arriba se hace ANTES de tener el vector,
            # así que responde por el espacio ACTIVO EN ESE INSTANTE — y la resolución del backend ocurre DENTRO
            # de `_emb.embed()`, una línea más abajo. Si ahí Ollama resulta estar ocupado y fastembed no carga,
            # el backend cae a `hash` con el permiso ya concedido: `last_degraded` es False A PROPÓSITO para un
            # hash CONFIGURADO («es su propio espacio consistente — lo gobierna la firma embedsig»), o sea que
            # los dos guardas se remiten el uno al otro y no queda ninguno. Así entraron los 15 vectores de otro
            # espacio del índice del operador, sin marcador y sin error. La primera llamada sigue estando: evita
            # pagar un embedding que se va a tirar; la que manda es ésta, con el espacio del vector ya sabido.
            elif embedding is None and not _embed_sig_ok():
                pending_reason = "sig_mismatch"
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


# The raw utterance as a second retrieval path (V2-031 T2 / V2-114 F4.2) was BUILT, MEASURED and REMOVED on
# 2026-08-19. Kept as an epitaph rather than silence, so nobody proposes it a third time without the numbers.
#
# The hypothesis was reasonable and came from a real measurement: on LoCoMo, distilling beats raw dialogue at
# multi-hop (+12.6pp) and open-domain (+15.4pp) and LOSES at temporal (-8.1pp) and single-hop (-2.8pp), because
# an answer that IS the literal wording of one turn does not survive being canonicalised. So: keep the pill as
# THE answer and let the operator's own words be an extra way to FIND it — augment, never replace.
#
# It lost on BOTH corpora, and on LoCoMo it lost precisely where it was supposed to win:
#
#   our corpus (tape A/B, 603 durables, 269 queries, identical corpus in both arms)
#     off  recall@1 69.8%  @3 85.9%  @5 89.7%  @10 92.4%  MRR .780  lat p50 533ms  DB 3.6MB
#     on   recall@1 68.3%  @3 85.9%  @5 88.9%  @10 91.6%  MRR .772  lat p50 787ms  DB 6.8MB
#
#   LoCoMo conv-0, distilled, 199 questions      overall  multi  temporal  open  single  adversarial
#     off                                         48.2%   43.8%   70.3%   38.5%  62.9%     14.9%
#     on                                          46.7%   37.5%   70.3%   38.5%  55.7%     23.4%
#
# Temporal did not move at all and single-hop dropped 7.2pp — the two categories the whole idea was for. Plus
# +48% read latency at p50 and ~2x the database, and "reading must be maximum speed" is a hard invariant (V2-013).
# Why it fails: the raw utterance is a NOISIER copy of the pill, so a query can match the wording of the WRONG
# pill and inject a false positive into the fusion, while doubling the rows a brute-force KNN scans.
#
# The one real gain, and where it actually points: adversarial +8.5pp. That category is our WRITE-COMPLETENESS
# hole (63.8% of its questions get "NO INFORMATION AVAILABLE" from the answerer vs ~16% elsewhere), so literal
# material helps there only because the distiller dropped the fact in the first place. The fix that indicates is
# writing the fact properly, not indexing everything twice to paper over it.
#
# NOTE: `index_paraphrases`/`drop_paraphrases` STAY. That channel carries REM-generated paraphrases, it was
# verified working (F4.3, after being mute since it was built), and it is a different mechanism from this one.


def _embed_sig_ok() -> bool:
    """Does the ACTIVE backend's signature match the one stamped on the index?

    Delegates to `reembed.space_ok()` (2026-08-18): the READ path needs the same predicate, and keeping two
    independent 60s caches of one question meant they could disagree during precisely the window where one of
    them is wrong. Kept as a named function because it is the writer's vocabulary for it and it reads better at
    the call site than the module hop."""
    try:
        from . import reembed as _reembed
        return _reembed.space_ok()
    except Exception:  # noqa: BLE001
        return True     # fail-open: with no verdict, vector writes are not blocked


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
                                         last_access, ttl_days, pinned, valid, slot, meta, created, updated, valid_at)
                   VALUES (?, 'concept', ?, 0.3, 0.5, 0, ?, NULL, 1, 1, NULL, NULL, ?, ?, ?)""",
                ("long", n, now, now, now, now),
            )
            cid = cur.lastrowid
            if db.fts_available:
                cur.execute("INSERT INTO fts_memories (rowid, text) VALUES (?, ?)", (cid, n))
        if db.vec_available:
            # El MISMO gate que la píldora (V2-484). Este camino insertaba el vector sin comprobar NADA — ni la
            # firma del índice ni la degradación en caliente — así que no es una carrera ni un permiso rancio:
            # aquí nunca hubo guarda. Por aquí entraron los 9 vectores fastembed (384 rellenados a 768) que
            # tiene el índice del operador, y son TODOS nodos-concepto («familia», «guitar», «trabajo»…).
            # El nodo se crea igual: es un hub del grafo y sin él `_link_concepts` no puede coser nada. Lo que
            # se difiere es su VECTOR, que es justo lo que `repair_embeddings` sabe recuperar — y se marca para
            # que mientras tanto sea CONTABLE en `hygiene()` en vez de un hueco mudo.
            vec = _emb.embed(n)
            if getattr(_emb, "last_degraded", False):
                _mark_embed_pending(db, cid, "degraded")
            elif not _embed_sig_ok():
                _mark_embed_pending(db, cid, "sig_mismatch")
            else:
                db.execute("INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)", (cid, _pack(vec)))
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


def demote_summarized(ids: list[int], insight_id: int, factor: float = 0.6, floor: float = 0.05) -> int:
    """REM (V2-103) resume un grupo de píldoras en UN insight — hasta ahora eso era pura ADICIÓN: el insight se
    escribía y las píldoras crudas que lo alimentaron seguían compitiendo a peso completo para siempre. Esta es
    la mitad que faltaba de "REM como sueño que consolida" (no solo apila un resumen encima): multiplica su
    `weight` por `factor` (con suelo `floor`, nunca additive/`reinforce` — y sin tocar `access_count`/
    `last_access`, así el decay natural sigue corriendo desde donde ya estaba) y estampa `meta.summarized_by`.
    **NUNCA invalida ni borra** — `valid`/`superseded_by` intactos, el histórico se conserva igual que siempre;
    solo deja de pesar tanto como el insight que las suplanta. `pinned` nunca se toca. Devuelve nº demotadas."""
    if not ids:
        return 0
    db = _db.get_db()
    now = _now()
    done = 0
    with db.cursor() as cur:
        for mid in ids:
            row = cur.execute("SELECT weight, pinned, meta FROM memories WHERE id=?", (int(mid),)).fetchone()
            if row is None or row["pinned"]:
                continue
            new_weight = max(float(floor), float(row["weight"]) * float(factor))
            try:
                meta = json.loads(row["meta"] or "{}")
            except Exception:
                meta = {}
            meta["summarized_by"] = int(insight_id)
            cur.execute(
                "UPDATE memories SET weight=?, meta=?, updated=? WHERE id=?",
                (new_weight, json.dumps(meta, ensure_ascii=False), now, int(mid)),
            )
            done += 1
    return done


def drop_paraphrases(memory_id: int) -> int:
    """Delete a memory's paraphrase rows AND their vectors. Returns how many were removed.

    This is not hygiene, it is two defects that only became REAL on 2026-08-18, the day the paraphrase channel
    started producing rows at all (it had been mute since it was built, see `nucleo/memllm._DEFAULTS`):
      1. **Right to be forgotten.** `forget(hard=True)` deleted the `memories` row, its vector, its FTS entry and
         its edges — and left the text sitting VERBATIM in `paraphrase_index.text`. A paraphrase is a rewrite of
         the operator's own datum, so "deleted" would have been false in the one place it must not be.
      2. **Orphans that keep matching.** `vec_paraphrases` is keyed by the synthetic PK, so a deleted memory's
         vectors survive and keep winning KNN slots, mapping back to a `memory_id` that no longer exists. The
         reader would not return them (`search()` filters `valid=1`) — it would just silently spend pool budget
         on dead rows, which is the kind of leak that only shows up as "recall got worse" months later.
    Both hard-delete paths (`writer.delete_memory`, `consolidator`'s eviction) call this — there is no third."""
    if not memory_id:
        return 0
    db = _db.get_db()
    try:
        rows = db.query("SELECT id FROM paraphrase_index WHERE memory_id=?", (int(memory_id),))
    except Exception:  # noqa: BLE001
        return 0        # table absent (a DB from before the channel existed) — nothing to clean
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    try:
        with db.cursor() as cur:
            cur.execute("DELETE FROM paraphrase_index WHERE memory_id=?", (int(memory_id),))
        if db.vec_available:
            ph = ",".join("?" * len(ids))
            db.execute(f"DELETE FROM vec_paraphrases WHERE id IN ({ph})", tuple(ids))
    except Exception:  # noqa: BLE001
        return 0
    return len(ids)


def index_paraphrases(memory_id: int, texts: list[str]) -> int:
    """V2-031 T2 (2026-08-17): indexa 1-2 REFORMULACIONES de una píldora durable — cierra el vocab-gap
    ("instrumento" en la query, "guitarra" en el dato) sin LLM en la lectura. Va en tabla PROPIA
    (`paraphrase_index` + `vec_paraphrases`, PK sintética), nunca en `vec_memories` (que exige 1 vector por
    `memory_id`). `memory/retriever.py` las funde en la fusión RRF mapeando de vuelta al `memory_id` real —
    nunca se devuelven como resultado por sí mismas, ni cuentan para dedup/consolidación. Off-hot-path (llamado
    desde `memory/rem.py`, nunca desde el turno). Fail-open: backend degradado → 0 indexadas, sin romper nada."""
    if not memory_id or not texts:
        return 0
    from . import embeddings as _emb
    if getattr(_emb, "last_degraded", False):
        return 0  # mismo criterio que repair_embeddings(): mejor sin vector que en el espacio equivocado
    db = _db.get_db()
    now = _now()
    done = 0
    for text in texts:
        text = (text or "").strip()
        if not text:
            continue
        try:
            vec = _emb.embed(text)
            if getattr(_emb, "last_degraded", False):
                break  # se degradó a mitad de lote → para, no mezcles espacios vectoriales
            with db.cursor() as cur:
                cur.execute(
                    "INSERT INTO paraphrase_index (memory_id, text, created) VALUES (?, ?, ?)",
                    (int(memory_id), text, now),
                )
                pid = cur.lastrowid
                cur.execute(
                    "INSERT INTO vec_paraphrases (id, embedding) VALUES (?, ?)",
                    (pid, _pack(vec)),
                )
            done += 1
        except Exception:
            continue
    return done


def supersede(old_id: int, new_id: int) -> None:
    """Marca un recuerdo como superado por otro (conflicto temporal; el consolidador también lo usa)."""
    db = _db.get_db()
    now = _now()
    db.execute(
        "UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? WHERE id=?",
        (int(new_id), now, now, int(old_id)),
    )


def delete_memory(mid: int) -> None:
    """Borra un recuerdo y sus representaciones (vec/fts). Solo el consolidador debería llamar esto."""
    import json as _json

    db = _db.get_db()
    mid = int(mid)
    row = db.query_one("SELECT text, meta FROM memories WHERE id=?", (mid,))
    already_pruned = False
    if row is not None:
        try:
            already_pruned = bool(_json.loads(row["meta"] or "{}").get("pruned"))
        except Exception:
            already_pruned = False
    with db.cursor() as cur:
        if db.fts_available and row is not None and not already_pruned:
            # FTS5 externo: borrado explícito con la sintaxis 'delete'.
            # Una fila invalidada puede haber sido retirada antes por
            # consolidator.prune_invalid(meta.pruned=1). Repetir el comando
            # especial `delete` sobre esa rowid corrompe el índice FTS5
            # (`database disk image is malformed`) durante una eviction posterior.
            cur.execute(
                "INSERT INTO fts_memories (fts_memories, rowid, text) VALUES ('delete', ?, ?)",
                (mid, row["text"]),
            )
        cur.execute("DELETE FROM memories WHERE id=?", (mid,))
        cur.execute("DELETE FROM edges WHERE from_id=? OR to_id=?", (mid, mid))
    if db.vec_available:
        db.execute("DELETE FROM vec_memories WHERE memory_id=?", (mid,))
    drop_paraphrases(mid)


# operaciones despachables desde la cola: op -> callable
OPS = {
    "write": insert_memory,
    "reinforce": reinforce,
    "link": link,
    "pin": lambda mid: set_pinned(mid, True),
    "unpin": lambda mid: set_pinned(mid, False),
    "supersede": supersede,
    "delete": delete_memory,
    "demote_summarized": demote_summarized,
}
