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
def repair_embeddings(limit: int | None = None) -> int:
    """Re-embebe píldoras válidas sin vector (o `meta.embed_pending`). Solo si la firma del backend activo casa
    con el índice (jamás repara metiendo vectores de otro espacio). Devuelve nº reparadas."""
    if limit is None:
        limit = _repair_limit_default()
    db = _db.get_db()
    if not db.vec_available or not _writer._embed_sig_ok():
        return 0
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
                cur.execute("UPDATE memories SET valid=0, superseded_by=?, updated=? WHERE id=?",
                            (keep["id"], _now(), drop["id"]))
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


def synthesize(synthesize_fn, min_group: int = MIN_GROUP) -> int:
    """Destila 1 insight por grupo de concepto y lo escribe con `slot=insight:<concepto>` (supersede por sueño:
    el insight de un concepto se REESCRIBE, nunca se acumula). `synthesize_fn(groups)->[{concept,insight}]` la
    inyecta el llamador (el loop → nucleo/memllm). Fail-open: sin hook o sin respuesta = 0 insights."""
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
            # suplanta. Se busca el grupo por concepto (no se arrastra el `ids` de fuera del bucle de resultados
            # porque `results` viene del hook, no de `groups` — empareja por texto de concepto).
            src = next((g for g in groups if g["concept"] == concept), None)
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
def run(synthesize_fn=None) -> dict:
    """Un ciclo de sueño PROFUNDO. Síncrono (el llamador lo mete en `asyncio.to_thread`). Cada fase aislada."""
    t0 = time.time()
    report: dict = {}
    for name, fn in (("repaired", repair_embeddings),
                     ("sem_deduped", semantic_dedup),
                     ("insights", lambda: synthesize(synthesize_fn)),
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
