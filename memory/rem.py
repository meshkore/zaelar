"""memory/rem.py — el sueño PROFUNDO de la memoria («fase REM», V2-056 · 2026-07-20).

El consolidador clásico (`consolidator.py`, cada hora) es el sueño LIGERO: mecánica barata (promote/dedup-exacto/
decay/prune/evict). Esta es la fase REM — el ciclo PROFUNDO (diario por defecto) en el que la memoria se ORDENA,
se RELACIONA y se SINTETIZA, como pidió el operador: re-puntuar, depurar, reducir tamaño y mejorar los vectores
de búsqueda. Cuatro fases, cada una aislada (un fallo no tumba el sueño) y todas OFF-hot-path:

  1. `repair_embeddings()` — re-embebe píldoras SIN vector o marcadas `meta.embed_pending` (el enforcement del
     writer las deja así ante firma discordante/degradación) — el índice semántico se AUTO-REPARA cada noche.
  2. `semantic_dedup()`    — dedup por SIGNIFICADO (coseno sobre los vectores ya calculados, sin LLM): fusiona
     casi-duplicados sin slot ("tiene cita ITV el 23" × 8 ecos → 1), transfiere aristas, invalida el resto con
     `superseded_by` (histórico intacto — nunca se borra). Era el pendiente declarado de V2-013.
  3. `synthesize(hook)`    — la parte con LLM (INYECTADA por el llamador — la memoria no importa cerebros; el
     loop cablea `nucleo/memllm.synthesize_concept_groups`, mismo patrón que `summarize_fn`): agrupa durables
     por CONCEPTO (grafo `edges`) y destila 1 INSIGHT de alto nivel por grupo (kind='insight',
     `slot=insight:<concepto>` → se REESCRIBE en cada sueño, no se acumula). Es la reflexión de Generative
     Agents / sleep-time compute de Letta: convierte 30 hechos sueltos en "lo que zaelar SABE de ti".
  4. `hygiene()`           — el chequeo del día: % de escritura heurística (CORAZÓN caído → debe saltar una
     alerta, no otra vez 2 días en silencio), píldoras `embed_pending` restantes, tamaños. El INFORME se
     devuelve al llamador (el loop decide alertar) y se emite por el bus (`memory.rem`).

Cadencia: `due()`/marcador `sys_kv.rem_last_run` (config §memory.rem_every_hours, def 24h; env ZAELAR_REM_SECS
manda si está). Kill-switch: ZAELAR_REM=0. Todo determinista salvo la fase 3 (hook fail-open → [] = sin insights).
"""
from __future__ import annotations

import json
import os
import struct
import time

from loguru import logger

from . import db as _db
from . import writer as _writer

# Umbral CALIBRADO contra la BD real (2026-07-20): los ecos-paráfrasis de una misma tarea ("Reserva la cita
# ITV…" × 8 variantes) puntúan 0.82-0.90 en embeddinggemma — a 0.92 no fusionaba NADA. 0.86 + la guarda de
# números en conflicto (dos hechos con cifras/fechas DISTINTAS jamás se fusionan) da el equilibrio.
SEM_DEDUP_THRESHOLD = float(os.getenv("ZAELAR_REM_DEDUP_SIM", "0.86"))
MIN_GROUP = 4          # nº mínimo de píldoras de un concepto para merecer síntesis
MAX_GROUPS = 8         # cap de grupos sintetizados por sueño (coste acotado)
HEURISTIC_ALERT_PCT = 50.0
HEURISTIC_ALERT_MIN = 10


def _now() -> int:
    from .clock import now
    return now()


def enabled() -> bool:
    return os.getenv("ZAELAR_REM", "1").strip().lower() not in ("0", "false", "no", "off")


def every_s() -> float:
    env = os.getenv("ZAELAR_REM_SECS")
    if env:
        return max(3600.0, float(env))
    try:
        from config import v2 as _v2
        return max(3600.0, float((_v2.get("memory") or {}).get("rem_every_hours") or 24) * 3600.0)
    except Exception:
        return 24 * 3600.0


def due(now: int | None = None) -> bool:
    """¿Toca sueño profundo? Marcador persistente (sobrevive reinicios). Sin marcador → siembra now (el primer
    REM llega un ciclo DESPUÉS de estrenar el sistema, nunca en el arranque)."""
    if not enabled():
        return False
    now = now or _now()
    from .consolidator import _kv_get, _kv_set
    last = _kv_get("rem_last_run")
    if last is None:
        _kv_set("rem_last_run", str(now))
        return False
    return (now - int(float(last))) >= every_s()


def _repair_limit_default() -> int:
    """Presupuesto de reparación por sueño — configurable (§memory.rem_repair_limit, mismo patrón que
    `rem_every_hours`). Es un job 100% local (Ollama/fastembed, sin LLM, sin coste) — 200/día no vaciaba una
    cola de varios cientos en tiempo razonable (V2-103, auditoría 2026-08-16: 51,6% de la memoria válida sin
    vector). Sin config, 1000/sueño."""
    env = os.getenv("ZAELAR_REM_REPAIR_LIMIT")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    try:
        from config import v2 as _v2
        return max(1, int((_v2.get("memory") or {}).get("rem_repair_limit") or 1000))
    except Exception:
        return 1000


# ── fase 1 · reparación de vectores ─────────────────────────────────────────────────────────────────────────
#: A stored vector IS the hash of its own text. Both sides are L2-normalised, so a genuine match is 1.0 exactly;
#: the margin is only there so float round-trips through `struct` cannot turn a match into a miss.
_FOREIGN_MATCH = 0.999


def _drop_foreign_vectors(db, limit: int) -> int:
    """Delete vectors produced by the HASH backend from an index sealed for a real embedding model (V2-482).

    `repair_embeddings` below only ever looks for rows with NO vector, because that is what the write guard
    leaves behind: on a signature mismatch the writer refuses the vector and marks `meta.embed_pending`
    (`writer._embed_sig_ok`). A row whose FOREIGN vector got past that guard HAS a vector, so the repair pass
    never selects it and the damage is permanent by construction. The rows the guard caught heal on the next
    sleep; these never do — and they are the worse half: a hash vector in an embeddinggemma index is noise
    fused into the RRF on every semantic recall, and it is invisible to every count of `embed_pending`.

    MEASURED 2026-08-29 on the operator's live memory: 15 durable rows carry a literal `_hash_embed` output
    (cosine 1.0000 against a recomputation from their own text) inside an index sealed
    `ollama:embeddinggemma:768`. The consequence was measured on the same rows: `semantic_dedup` can never
    merge them, because its threshold is calibrated on embeddinggemma (0.82-0.90 between echoes of one fact,
    see SEM_DEDUP_THRESHOLD) while hash collisions between those same sentences top out at 0.788. So the
    operator's memory holds eight live copies of one taste, each decaying alone, none with the weight to reach
    the passive block. The threshold is not what is wrong here — the vectors are, and this is where they die.

    Only the HASH space is detectable this way, and that is the point rather than a shortfall: hash is the
    emergency degradation target, so it is the space that leaks. A vector from a different REAL model is not
    reproducible from the text, and keeping those out is the signature guard's job, not this one's.

    Does nothing when hash IS the sealed space (dev, tests, a fresh DB) — there the vectors are native — nor
    when nothing is sealed, because then there is no space to call anything foreign to. Deleting the vector is
    the entire repair: the pass that follows selects the row precisely because it now has none, and re-embeds
    it in the correct space. Marking `embed_pending` too is what makes a failure to do so COUNTABLE in
    `hygiene()` instead of silent.
    """
    from . import embeddings as _emb
    from . import reembed as _reembed
    sealed = _reembed.stored_signature()
    if not sealed or sealed.startswith("hash:"):
        return 0
    rows = db.query(
        "SELECT m.id, m.text, v.embedding FROM memories m JOIN vec_memories v ON v.memory_id = m.id "
        "WHERE m.valid=1 AND m.kind NOT IN ('conv') LIMIT ?", (limit,))
    gone = 0
    for r in rows:
        txt = (r["text"] or "").strip()
        if not txt:
            continue
        try:
            stored = _unpack(r["embedding"])
            hashed = _emb._l2_normalize(_emb._fit_dim(_emb._hash_embed(txt, len(stored)), len(stored)))
            if _cos(stored, hashed) < _FOREIGN_MATCH:
                continue
            db.execute("DELETE FROM vec_memories WHERE memory_id=?", (r["id"],))
            _writer._mark_embed_pending(db, r["id"], "foreign_space")
            gone += 1
        except Exception:  # noqa: BLE001
            continue
    if gone:
        logger.warning(f"memoria: {gone} vectores de espacio ajeno (hash) retirados de un índice «{sealed}» "
                       f"— se re-embeben en esta misma pasada")
        try:
            from voice import health_state
            health_state.record("memory", "degraded",
                                f"{gone} vectores de otro espacio retirados del índice: el recall semántico "
                                f"estaba fusionando ruido en esas píldoras")
        except Exception:  # noqa: BLE001
            pass
    return gone


def repair_embeddings(limit: int | None = None) -> int:
    """Re-embebe píldoras válidas sin vector (o `meta.embed_pending`). Solo si la firma del backend activo casa
    con el índice (jamás repara metiendo vectores de otro espacio). Devuelve nº reparadas."""
    if limit is None:
        limit = _repair_limit_default()
    db = _db.get_db()
    if not db.vec_available or not _writer._embed_sig_ok():
        return 0
    # BEFORE the SELECT, never after: a foreign vector is exactly what hides its own row from it (V2-482).
    _drop_foreign_vectors(db, limit)
    from . import embeddings as _emb
    rows = db.query(
        "SELECT m.id, m.text, m.meta FROM memories m LEFT JOIN vec_memories v ON v.memory_id = m.id "
        "WHERE m.valid=1 AND m.kind NOT IN ('conv') AND v.memory_id IS NULL LIMIT ?",
        (limit,),
    )
    fixed = 0
    for r in rows:
        try:
            vec = _emb.embed(r["text"])
            if getattr(_emb, "last_degraded", False):
                continue           # backend caído a hash — mejor sin vector que con vector de otro espacio
            db.execute("INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)",
                       (r["id"], _writer._pack(vec)))
            meta = json.loads(r["meta"] or "{}")
            if meta.pop("embed_pending", None) is not None:
                db.execute("UPDATE memories SET meta=? WHERE id=?",
                           (json.dumps(meta, ensure_ascii=False), r["id"]))
            fixed += 1
        except Exception:
            continue
    return fixed


# ── fase 1b · índice de PARÁFRASIS (V2-031 T2, con LLM inyectado) ──────────────────────────────────────────
def _paraphrase_limit_default() -> int:
    """Presupuesto por sueño — mismo patrón que `_repair_limit_default()`, pero ESTA fase SÍ cuesta un LLM real
    por píldora, así que el default es deliberadamente MODESTO (no 1000/noche): el backlog se vacía en varias
    noches, no de golpe. Configurable (§memory.rem_paraphrase_limit / ZAELAR_REM_PARAPHRASE_LIMIT)."""
    env = os.getenv("ZAELAR_REM_PARAPHRASE_LIMIT")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    try:
        from config import v2 as _v2
        return max(1, int((_v2.get("memory") or {}).get("rem_paraphrase_limit") or 30))
    except Exception:
        return 30


def index_paraphrases(paraphrase_fn, limit: int | None = None) -> int:
    """Backfill del índice de paráfrasis: durables SIN ninguna fila en `paraphrase_index` aún, hasta `limit`.
    `paraphrase_fn(text) -> [str, …]` la inyecta el llamador (el loop → `nucleo/memllm.generate_paraphrases`,
    mismo patrón que `synthesize_fn`). Fail-open total: sin hook, sin backend vec, o cualquier fallo por
    píldora → esa píldora simplemente sigue sin paráfrasis (se sigue recuperando por su propio embedding,
    igual que siempre — esto solo AÑADE superficie, nunca es la única vía). Devuelve nº de píldoras procesadas
    con éxito (con ≥1 paráfrasis indexada)."""
    if paraphrase_fn is None:
        return 0
    db = _db.get_db()
    if not db.vec_available:
        return 0
    if limit is None:
        limit = _paraphrase_limit_default()
    rows = db.query(
        "SELECT m.id, m.text FROM memories m "
        "LEFT JOIN paraphrase_index p ON p.memory_id = m.id "
        "WHERE m.valid=1 AND m.level IN ('mid','long') AND m.kind NOT IN ('conv','concept','insight') "
        "AND p.memory_id IS NULL GROUP BY m.id LIMIT ?",
        (limit,),
    )
    done = 0
    empty = 0
    for r in rows:
        try:
            variants = paraphrase_fn(r["text"]) or []
        except Exception as e:  # noqa: BLE001
            logger.debug(f"rem.index_paraphrases: hook falló para #{r['id']}: {str(e)[:120]}")
            empty += 1
            continue
        if not variants:
            empty += 1
            continue
        if _writer.index_paraphrases(r["id"], variants) > 0:
            done += 1
    # A MUTE hook has to be VISIBLE (2026-08-18). The per-pill fail-open above is right — a pill without
    # paraphrases is still retrieved by its own embedding — but it turned "the whole channel is dead" into
    # "no candidates tonight": `generate_paraphrases` returns [] on ANY problem and this loop treated that
    # exactly like "nothing to do". Measured 2026-08-18: `vec_paraphrases` had **0 rows** since the channel was
    # built, because the model spent its entire token budget on reasoning and returned empty — the third
    # retrieval channel contributed NOTHING and no surface said so. Fourth time this module pays for the same
    # failure shape (distiller down 2 days, REM raising KeyError, i18n pointed at OpenAI in cloud): the rule
    # already written here is that a memory failure NEVER stops at a `logger.warning`.
    # It only fires when work was ATTEMPTED and NOTHING came out: with mixed candidates the channel is alive and
    # one failing pill is normal noise, not an outage worth turning the ◉ amber.
    if empty and not done:
        logger.warning(f"rem.index_paraphrases: {empty} candidates and NOT ONE paraphrase — paraphrase channel mute")
        try:
            from voice import health_state
            health_state.record("memory", "degraded",
                                f"paraphrase channel mute: {empty} candidates, 0 indexed")
        except Exception:  # noqa: BLE001
            pass  # observability NEVER breaks the sleep cycle
    return done


# ── fase 2 · dedup SEMÁNTICO (sin LLM: coseno sobre vectores ya pagados) ────────────────────────────────────
def _unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def _cos(a: list[float], b: list[float]) -> float:
    # vectores YA L2-normalizados al insertar → coseno = producto escalar
    return sum(x * y for x, y in zip(a, b))


import re as _re

_NUM_RE = _re.compile(r"\d+(?:[.,:]\d+)*")


def _conflicting_numbers(a: str, b: str) -> bool:
    """Dos textos con CIFRAS/FECHAS distintas son hechos DISTINTOS aunque el embedding los vea casi iguales
    ('cita dentista el lunes 3' vs 'cita dentista el jueves 12') → jamás fusionar. Sin cifras en uno de los
    dos, no hay conflicto (el que las tiene es la versión más informativa)."""
    na, nb = set(_NUM_RE.findall(a)), set(_NUM_RE.findall(b))
    return bool(na and nb and na != nb)


# ── V2-104: fidelidad del insight — backstop determinista antes del gate por LLM ────────────────────────────
MAX_INSIGHT_CHARS = 400  # 1-2 frases de síntesis; sin techo, un insight puede crecer sin límite sueño tras sueño


def _proper_nouns(text: str) -> set[str]:
    """Palabras con mayúscula inicial que NO abren su frase — candidatas a nombre propio/entidad. La mayúscula
    de apertura de frase no cuenta (falso positivo casi seguro), el resto sí."""
    nouns: set[str] = set()
    for sentence in _re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sentence.split()
        for i, w in enumerate(words):
            core = w.strip(".,;:!?()\"'“”«»").strip()
            if i == 0 or len(core) < 3 or not core[0].isupper() or not core.isalpha():
                continue
            nouns.add(core)
    return nouns


def _grounded(insight: str, pills: list[str]) -> bool:
    """Backstop GRATIS (sin LLM): toda cifra/fecha y todo nombre propio del insight debe aparecer en el texto
    de las píldoras que lo originaron. No prueba fidelidad SEMÁNTICA — solo la fabricación más burda (una cifra
    o un nombre que no está en los datos). La verificación fina va en `nucleo/memllm.verify_insight_grounded`."""
    source = " ".join(pills).lower()
    for num in _NUM_RE.findall(insight):
        if num.lower() not in source:
            return False
    for noun in _proper_nouns(insight):
        if noun.lower() not in source:
            return False
    return True


def semantic_dedup(threshold: float = SEM_DEDUP_THRESHOLD, cap: int = 1500) -> int:
    """Fusiona durables casi-idénticos por SIGNIFICADO: los ecos de una misma tarea/hecho dichos de N formas
    ("Reserva la cita ITV…" × 8) colapsan en el de mayor peso; el resto queda `valid=0, superseded_by` (histórico
    intacto, el sueño ligero los podará de los índices). SOLO sin `slot` (los con slot ya supersedan exacto) y
    nunca pinned-vs-pinned distintos ni kinds críticos. O(n²) acotado por `cap` (a nuestra escala, ms)."""
    db = _db.get_db()
    if not db.vec_available:
        return 0
    rows = db.query(
        "SELECT m.id, m.text, m.weight, m.access_count, m.pinned, m.kind, v.embedding FROM memories m "
        "JOIN vec_memories v ON v.memory_id = m.id "
        "WHERE m.valid=1 AND m.slot IS NULL AND m.level IN ('mid','long') "
        "AND m.kind NOT IN ('conv','concept','insight') ORDER BY m.id DESC LIMIT ?",
        (cap,),
    )
    vecs = {r["id"]: _unpack(r["embedding"]) for r in rows}
    by_id = {r["id"]: r for r in rows}
    ids = sorted(vecs.keys())
    merged = 0
    gone: set[int] = set()
    for i, a in enumerate(ids):
        if a in gone:
            continue
        for b in ids[i + 1:]:
            if b in gone:
                continue
            if _cos(vecs[a], vecs[b]) < threshold:
                continue
            ra, rb = by_id[a], by_id[b]
            if _conflicting_numbers(ra["text"], rb["text"]):
                continue           # cifras/fechas distintas = hechos distintos, no ecos
            # conserva el "mejor" (pinned > peso > accesos > más reciente)
            keep, drop = (ra, rb) if (ra["pinned"], ra["weight"], ra["access_count"], ra["id"]) >= \
                                     (rb["pinned"], rb["weight"], rb["access_count"], rb["id"]) else (rb, ra)
            if drop["pinned"]:
                continue           # nunca invalidar un pinned a favor de otro
            with db.cursor() as cur:
                cur.execute("UPDATE OR IGNORE edges SET from_id=? WHERE from_id=?", (keep["id"], drop["id"]))
                cur.execute("UPDATE OR IGNORE edges SET to_id=? WHERE to_id=?", (keep["id"], drop["id"]))
                _now_ts = _now()
                cur.execute("UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? WHERE id=?",
                            (keep["id"], _now_ts, _now_ts, drop["id"]))
            _writer.reinforce([keep["id"]], step=0.0)
            gone.add(drop["id"])
            merged += 1
    return merged


# ── fase 3 · SÍNTESIS (LLM inyectado): conceptos → insights ─────────────────────────────────────────────────
def _concept_groups(min_group: int = MIN_GROUP, max_groups: int = MAX_GROUPS) -> list[dict]:
    """Grupos de durables por NODO-concepto del grafo (los más poblados primero). Sin LLM: traversal directo."""
    db = _db.get_db()
    rows = db.query(
        "SELECT c.id AS cid, c.text AS concept, m.id AS mid, m.text AS pill FROM memories c "
        "JOIN edges e ON (e.from_id = c.id OR e.to_id = c.id) "
        "JOIN memories m ON m.id = (CASE WHEN e.from_id = c.id THEN e.to_id ELSE e.from_id END) "
        "WHERE c.kind='concept' AND m.valid=1 AND m.level IN ('mid','long') "
        "AND m.kind NOT IN ('conv','concept','insight') "
        "AND (m.meta IS NULL OR m.meta NOT LIKE '%\"trust\": \"untrusted\"%')",
    )
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(r["concept"], {"concept": r["concept"], "pills": [], "_ids": set()})
        if r["mid"] not in g["_ids"]:
            g["_ids"].add(r["mid"])
            g["pills"].append(r["pill"])
    out = [g for g in groups.values() if len(g["pills"]) >= min_group]
    out.sort(key=lambda g: -len(g["pills"]))
    for g in out:
        # V2-103: antes se descartaban — `synthesize()` las necesita para DEMOTAR las píldoras crudas que
        # alimentaron el insight (ver `writer.demote_summarized`), no solo escribirlo encima de ellas.
        g["ids"] = sorted(g.pop("_ids", set()))
    return out[:max_groups]


def _reject(concept: str, reason: str) -> None:
    """Un insight rechazado es un fallo de la MEMORIA, no un descarte silencioso — misma disciplina que el
    fallo de hook de abajo (incidente 2026-07-17/19: un `logger.warning` entre miles de líneas dejó semanas sin
    que nadie lo viera)."""
    logger.warning(f"rem.synthesize: insight de «{concept}» rechazado — {reason}")
    try:
        from voice import health_state
        health_state.record("memory", "degraded", f"insight de «{concept}» rechazado: {reason}")
    except Exception:  # noqa: BLE001
        pass


def synthesize(synthesize_fn, min_group: int = MIN_GROUP, verify_fn=None) -> int:
    """Destila 1 insight por grupo de concepto y lo escribe con `slot=insight:<concepto>` (supersede por sueño:
    el insight de un concepto se REESCRIBE, nunca se acumula). `synthesize_fn(groups)->[{concept,insight}]` la
    inyecta el llamador (el loop → nucleo/memllm). Fail-open: sin hook o sin respuesta = 0 insights.

    V2-104: antes de escribir y de demotar las píldoras fuente, cada insight pasa un gate de fidelidad. Con
    `verify_fn` cableado (típicamente `memllm.verify_insight_grounded`, inyectado igual que `synthesize_fn`), ES
    EL ÁRBITRO — una segunda opinión por LLM en una llamada FRESCA, distinta de la que generó el insight (el
    autocriterio en el mismo turno es más débil que un juicio independiente). `_grounded()` (backstop
    determinista, cifras/nombres propios deben anclar en los datos) solo decide cuando NO hay `verify_fn`
    disponible — corregido tras validación real (2026-08-16): dejarlo vetar SIEMPRE, antes del LLM, rechazaba
    sistemáticamente paráfrasis fieles (dígito↔palabra: "nueve"→"9") que el verificador real sí reconocía bien.
    Política ASIMÉTRICA ante cualquier rechazo: no se escribe el insight y NO se demotan las fuentes — el grupo
    se reintenta en el próximo sueño. Importa más desde hoy que ayer: la democión (V2-103) hace que un insight
    malo DESPLACE los hechos correctos, no solo compita con ellos."""
    if synthesize_fn is None:
        return 0
    groups = _concept_groups(min_group=min_group)
    if not groups:
        return 0
    try:
        results = synthesize_fn(groups) or []
    except Exception as e:  # noqa: BLE001
        # NUNCA en silencio (lección del incidente del CORAZÓN 2026-07-17/19, y de este mismo módulo: un
        # `KeyError` del prompt dejó esta fase sin escribir un solo insight durante semanas y solo constaba
        # como un warning entre miles de líneas). El fallo del hook es un fallo de la MEMORIA: se marca en
        # `health_state` → lo pinta el ◉ de estado, igual que una caída del destilador. Sigue siendo fail-open:
        # el sueño continúa con sus otras fases.
        logger.error(f"rem.synthesize: hook falló ({str(e)[:160]}) → sin insights este sueño")
        try:
            from voice import health_state
            health_state.record("memory", "outage", f"sueño REM sin insights: {str(e)[:120]}")
        except Exception:  # noqa: BLE001
            pass
        return 0
    written = 0
    for it in results:
        concept = (it.get("concept") or "").strip().lower()
        insight = (it.get("insight") or "").strip() if it.get("insight") else ""
        if not concept or not insight or len(insight) < 12:
            continue
        if len(insight) > MAX_INSIGHT_CHARS:
            _reject(concept, f"demasiado largo ({len(insight)} > {MAX_INSIGHT_CHARS} chars)")
            continue
        src = next((g for g in groups if g["concept"] == concept), None)
        pills = src["pills"] if src else []
        # V2-104 (corregido tras validación REAL, 2026-08-16): `verify_fn`, cuando existe, es el ÁRBITRO — no
        # `_grounded()`. Medido con DeepSeek V4 Flash real: el modelo convierte de forma CONSISTENTE "las nueve"
        # (fuente) → "las 9" (insight), una paráfrasis fiel — `_grounded()` la rechaza SIEMPRE por comparar
        # substring literal sin normalizar dígito↔palabra, mientras el verificador LLM la acepta correctamente
        # (3/3 intentos reales). Dejar que el backstop determinista vetara ANTES del LLM significaba que REM casi
        # nunca podía escribir un insight sobre cualquier concepto con una cantidad dicha en palabras — el mismo
        # error de fondo que V2-075 ya nombró en otro módulo: el juicio semántico no se hace con patrones
        # hardcodeados, lo decide un MODELO. `_grounded()` se queda como red de seguridad GRATIS solo para cuando
        # NO hay `verify_fn` cableado (fail-safe sin LLM disponible).
        if verify_fn is not None:
            try:
                ok = bool(verify_fn(insight, pills))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"rem.synthesize: verify_fn falló ({str(e)[:120]}) → tratado como NO fiable")
                ok = False
            if not ok:
                _reject(concept, "la verificación por LLM no lo respalda")
                continue
        elif not _grounded(insight, pills):
            _reject(concept, "una cifra o un nombre propio no aparece en los datos fuente (sin verify_fn: solo backstop)")
            continue
        try:
            insight_id = _writer.insert_memory(
                insight, level="long", kind="insight", importance=0.65,
                slot=f"insight:{concept}",
                meta={"source": "rem", "concept": concept},
                concepts=[concept],
            )
            written += 1
            # V2-103: REM debe RETIRAR lo que resume, no solo añadir encima — demota (nunca invalida/borra) las
            # píldoras crudas de este grupo para que dejen de competir a peso completo con el insight que las
            # suplanta. Solo llega aquí un insight que ya pasó los dos gates de fidelidad de arriba.
            if src and src.get("ids"):
                _writer.demote_summarized(src["ids"], insight_id)
        except Exception:
            continue
    return written


# ── fase 4 · higiene del día ────────────────────────────────────────────────────────────────────────────────
def hygiene(window_s: int = 86400) -> dict:
    """Chequeo de salud de la ESCRITURA de las últimas 24h — el guardián que faltaba (auditoría 2026-07-19: el
    CORAZÓN estuvo 2 días caído y el % heurístico se disparó sin que nadie lo viera)."""
    db = _db.get_db()
    since = _now() - window_s
    total = db.query_one(
        "SELECT COUNT(*) c FROM memories WHERE created >= ? AND kind NOT IN ('conv','concept')", (since,))["c"]
    heur = db.query_one(
        "SELECT COUNT(*) c FROM memories WHERE created >= ? AND kind NOT IN ('conv','concept') "
        "AND json_extract(meta, '$.path') LIKE 'heuristic%'", (since,))["c"]
    pending = db.query_one(
        "SELECT COUNT(*) c FROM memories WHERE valid=1 AND json_extract(meta, '$.embed_pending') IS NOT NULL",
        ())["c"]
    pct = round(100.0 * heur / total, 1) if total else 0.0
    return {
        "written_24h": total,
        "heuristic_24h": heur,
        "heuristic_pct": pct,
        "embed_pending": pending,
        "alert": bool(total >= HEURISTIC_ALERT_MIN and pct >= HEURISTIC_ALERT_PCT),
    }


# ── orquestación ────────────────────────────────────────────────────────────────────────────────────────────
def run(synthesize_fn=None, verify_fn=None, paraphrase_fn=None) -> dict:
    """Un ciclo de sueño PROFUNDO. Síncrono (el llamador lo mete en `asyncio.to_thread`). Cada fase aislada.
    `verify_fn` (V2-104) es el segundo gate de fidelidad de `synthesize()`, opcional — el loop la cablea junto
    a `synthesize_fn`. `paraphrase_fn` (V2-031 T2) alimenta `index_paraphrases()`, opcional e independiente."""
    t0 = time.time()
    report: dict = {}
    for name, fn in (("repaired", repair_embeddings),
                     ("paraphrased", lambda: index_paraphrases(paraphrase_fn)),
                     ("sem_deduped", semantic_dedup),
                     ("insights", lambda: synthesize(synthesize_fn, verify_fn=verify_fn)),
                     ("hygiene", hygiene)):
        try:
            report[name] = fn()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"rem.{name} falló: {str(e)[:140]} → fase saltada")
            report[name] = None
    from .consolidator import _kv_set
    _kv_set("rem_last_run", str(_now()))
    report["ms"] = round((time.time() - t0) * 1000)
    try:
        import bus
        bus.emit_sync("memory.rem", dict(report))
    except Exception:
        pass
    logger.info(f"sueño REM: {report}")
    return report
