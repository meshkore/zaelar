"""memory/retriever.py — retriever híbrido (RUTA CALIENTE · ms) (V2-002 · T47).

Compone el **contexto mínimo** ante un prompt, lo más rápido posible (lectura directa, WAL, sin bloquear al
escritor). El **estado** se inyecta SIEMPRE aparte (sin búsqueda, `memory/state.py`); aquí va lo demás:

    vector (sqlite-vec, k=POOL_K)  ∥  keyword (FTS5, k=POOL_K)  ∥  paráfrasis (vec_paraphrases, k=POOL_K)
        → fusión RRF  ( rrf(doc) = Σ 1/(k+rank) , k=60 )
        → score = α·rel + β·rec + γ·imp + δ·uso    (α .45 · β .25 · γ .20 · δ .10)
        → orden desc
        → graph_expand (opcional: vecinos por `edges`, top-K)
        → trunca al presupuesto de tokens

`rel` = relevancia de la fusión (RRF normalizado a [0,1]); `rec` = recencia (half-life configurable);
`imp` = importancia base; `uso` = peso vivo. Solo entran recuerdos `valid=1`. Si sqlite-vec no está
disponible, degrada a solo-FTS; si FTS tampoco, a un LIKE básico — nunca revienta.

El refuerzo por uso NO se hace aquí (mantiene el retriever puro y sin escritura): `search()` devuelve los ids
usados y la fachada (`memory/api.py`) los encola por la cola async. `search(..., reinforce=True)` emite además
la señal `memory.reinforce` por el bus (best-effort, loop-agnóstico) para quien quiera reaccionar.
"""
import math
import os
import re
import struct
import time

from . import db as _db
from . import embeddings as _emb

# Pesos del score (ajustables por perfil).
ALPHA = 0.45   # relevancia semántica (fusión)
BETA = 0.25    # recencia
GAMMA = 0.20   # importancia
DELTA = 0.10   # peso de uso
RRF_K = 60
RECENCY_HALFLIFE_DAYS = 7.0

# Pool de candidatos ANTES de la fusión RRF (V2-031 T2, 2026-08-17): subido de 40 a 100. El reranker
# (`memory/rerank.py::rerank()`) SOLO cross-encodea su propio `top_n` (20 por defecto) tras la fusión — un pool
# más ancho da a la RRF más superficie donde encontrar un candidato relevante que hoy queda fuera del corte
# antes de llegar siquiera al reranker (found@10 medido en 70,5% con el pool de 40, `.meshkore/logs/membot/`),
# SIN encarecer el cross-encoder (que sigue viendo como mucho `top_n` candidatos, cueste 40 o 100 traerlos).
POOL_K = int(os.getenv("ZAELAR_RETRIEVER_POOL_K", "100"))

_FTS_TOKEN = re.compile(r"\w+", re.UNICODE)


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _fts_query(prompt: str) -> str:
    """Prompt libre → consulta FTS5 segura: OR de tokens con STEM-por-prefijo (evita errores de sintaxis).

    Español es MUY flexivo y el CORAZÓN canonicaliza persona/tiempo al escribir ("estoy aprendiendo" → "aprende
    japonés", "me operaron" → "se operó"): el token exacto de la query ("aprendiendo") NO casa con el almacenado
    ("aprende") y, con el embedding local plano, el hecho se ENTIERRA (T150). Un stemming ligero por prefijo une
    las variantes morfológicas: truncamos los tokens de contenido (≥5) a 6 chars + `*` → "aprend*" casa
    aprende/aprendiendo/aprender. Solo ensancha el canal FTS (la fusión RRF + el canal vectorial mantienen la
    precisión). Descartamos stopwords y tokens muy cortos (evita `de*`/`la*` que casarían con todo)."""
    terms: list[str] = []
    for t in _FTS_TOKEN.findall(prompt.lower()):
        if t in _FTS_STOP:
            continue
        if len(t) >= 5:
            terms.append(f"{t[:6]}*")        # stem por prefijo (6 chars) → cubre la flexión es
        elif len(t) >= 3:
            terms.append(f'"{t}"')           # token corto con contenido (números, siglas) → exacto
    return " OR ".join(terms)


# Stopwords ES/EN (función + VERBOS META de recall, no contenido): fuera del FTS para no ensuciar el prefijo.
# ⚠️ CRÍTICO: los verbos de recall ("recuerdas", "acuerdas", "dime", "sabes") son META ("¿te acuerdas de…?"),
# NO el dato buscado. Sin filtrarlos, "recuerdas"→prefijo "recuer*" casaría con TODOS los "recuérdame…" del store
# (dentista/pasaporte/basura) y ENTERRARÍA la respuesta real (bug detectado con "¿recuerdas a qué soy alérgico?").
_FTS_STOP = frozenset(
    "de la el los las un una unos unas y o a en con por para del al es son era mi mis tu tus su sus me te se "
    "lo le nos os que qué cual cuál como cómo donde dónde cuando cuándo mas más pero si sí no ni ya "
    "va van voy vas vais esta estan están estoy estas estás estamos ando anda andas hay ha han he has "
    "recuerdas recuerda recuérdame recuerdame acuerdas acuerda acuerdo dime dímelo sabes cuéntame cuentame "
    "cuenta quién quien qué hago hice había tengo tienes tuve algún alguna algo cosa "
    "the of to in on at is are was for and or my your his her remember recall tell know what did do i you".split()
)


def vec_search(query_vec: list[float], k: int = POOL_K) -> list[tuple[int, float]]:
    db = _db.get_db()
    if not db.vec_available:
        return []
    try:
        rows = db.query(
            "SELECT memory_id, distance FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (_pack(query_vec), k),
        )
        return [(r["memory_id"], r["distance"]) for r in rows]
    except Exception:
        return []


def vec_search_paraphrases(query_vec: list[float], k: int = POOL_K) -> list[tuple[int, float]]:
    """V2-031 T2: como `vec_search()`, pero sobre `vec_paraphrases` — mapeando de vuelta al `memory_id` REAL vía
    `paraphrase_index`. Una paráfrasis nunca es un resultado por sí misma, solo un canal MÁS de evidencia a
    favor de la píldora que representa; `search()` la pasa a `rrf()` como una lista ranked independiente (igual
    que vec/FTS) — si el vector propio Y una paráfrasis casan, el memory_id acumula señal de los dos canales,
    el mismo principio por el que ya acumula señal de vec+FTS hoy."""
    db = _db.get_db()
    if not db.vec_available:
        return []
    try:
        # sqlite-vec exige que el `LIMIT`/`k=?` vaya SOBRE la propia consulta KNN a la tabla virtual — un JOIN
        # en la MISMA query rompe el reconocimiento del plan KNN (`OperationalError: A LIMIT or 'k = ?'
        # constraint is required on vec0 knn queries`, medido). Dos pasos: KNN "pelado" sobre `vec_paraphrases`
        # → mapear `paraphrase_index.id → memory_id` en una segunda consulta normal.
        hits = db.query(
            "SELECT id, distance FROM vec_paraphrases WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (_pack(query_vec), k),
        )
        if not hits:
            return []
        pids = [h["id"] for h in hits]
        placeholders = ",".join("?" * len(pids))
        rows = db.query(
            f"SELECT id, memory_id FROM paraphrase_index WHERE id IN ({placeholders})", pids)
        mid_by_pid = {r["id"]: r["memory_id"] for r in rows}
        return [(mid_by_pid[h["id"]], h["distance"]) for h in hits if h["id"] in mid_by_pid]
    except Exception:
        return []


def fts_search(prompt: str, k: int = POOL_K) -> list[tuple[int, float]]:
    db = _db.get_db()
    if not db.fts_available:
        return []
    q = _fts_query(prompt)
    if not q:
        return []
    try:
        rows = db.query(
            "SELECT rowid, bm25(fts_memories) AS rank FROM fts_memories "
            "WHERE fts_memories MATCH ? ORDER BY rank LIMIT ?",
            (q, k),
        )
        return [(r["rowid"], r["rank"]) for r in rows]
    except Exception:
        return []


def rrf(*ranked_lists: list[tuple[int, float]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal Rank Fusion. Cada lista viene ordenada mejor→peor; el score es Σ 1/(k+rank)."""
    scores: dict[int, float] = {}
    for lst in ranked_lists:
        for rank, (mid, _) in enumerate(lst, start=1):
            scores[mid] = scores.get(mid, 0.0) + 1.0 / (k + rank)
    return scores


def _recency(last_access: int | None, now: int) -> float:
    if not last_access:
        return 0.0
    days = max(0.0, (now - last_access) / 86400.0)
    return math.pow(2.0, -days / RECENCY_HALFLIFE_DAYS)


def graph_expand(results: list[dict], top: int = 6, max_add: int = 8, discount: float = 0.5,
                 concept_discount: float = 1.0, ppr_max_add: int = 6, ppr_discount: float = 0.35) -> list[dict]:
    """Añade vecinos por `edges` de los `top` mejores resultados (opcional). No duplica; score descontado.

    GRAFO DE CONCEPTOS (T126): si el parent es un NODO-CONCEPTO (kind='concept') que casó la query (p. ej.
    "deporte" en "¿qué hago de deporte?"), sus vecinos SON la respuesta a la categoría → apenas se descuentan
    (`concept_discount` alto) y los conceptos se procesan PRIMERO para que su cluster no lo desplace el
    `max_add` global. Los vecinos pill↔pill normales siguen con el descuento fuerte (contexto, no respuesta).

    CANAL ADICIONAL (V2-111 §9.1): tras el 1-hop de arriba, una pasada de Personalized PageRank
    (`graph_ppr.py`) explora varios saltos desde los MISMOS parents y añade lo que el 1-hop no puede alcanzar
    — con su propio descuento (menor evidencia que un vecino directo). Fail-open total y APAGABLE
    (`ZAELAR_GRAPH_PPR=0`); con el grafo vacío o sin capacidad, no añade nada y el resto de `graph_expand`
    sigue exactamente igual que antes de esta pieza."""
    if not results:
        return results
    db = _db.get_db()
    present_map = {r["id"]: r for r in results}
    added: list[dict] = []
    # TODOS los nodos-concepto recuperados (a cualquier rango) son parents: su presencia señala intención de
    # categoría y su cluster ES la respuesta, aunque el nodo no entre en el top-N por score (varias píldoras con la
    # palabra lo empujan abajo). Son pocos → barato. Luego, las mejores píldoras como parents normales.
    concept_parents = [r for r in results if r.get("kind") == "concept"]
    pill_parents = [r for r in results[:top] if r.get("kind") != "concept"]
    parents = concept_parents + pill_parents
    for parent in parents:
        if len(added) >= max_add:
            break
        is_concept = parent.get("kind") == "concept"
        disc = concept_discount if is_concept else discount
        edges = db.query(
            "SELECT to_id, weight FROM edges WHERE from_id=? ORDER BY weight DESC LIMIT ?",
            (parent["id"], max_add),
        )
        for e in edges:
            nid = e["to_id"]
            boosted = parent["score"] * float(e["weight"]) * disc
            if nid in present_map:
                # El vecino YA está en los resultados (lo trajo el vector/FTS) pero quizá HUNDIDO. Si el parent es
                # un nodo-concepto, PROMOCIONAMOS al miembro del cluster (su score sube al del cluster) — antes se
                # saltaba y se quedaba enterrado (bug del recall por categoría, "¿cómo van mis finanzas?").
                if is_concept:
                    ex = present_map[nid]
                    if boosted > ex.get("score", 0):
                        ex["score"] = boosted
                        ex["via"] = f"edge:{parent['id']}"
                continue
            row = db.query_one(
                "SELECT id, level, kind, text, importance, weight, last_access, pinned "
                "FROM memories WHERE id=? AND valid=1 "
                # CUARENTENA: el contenido de peers/agentes no confiables (trust='untrusted') NUNCA aflora por
                # recall semántico (ni por el grafo de conceptos) — solo por consulta explícita `recent_by_source`.
                "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted')",
                (nid,),
            )
            if row is None or row["kind"] == "concept":   # no expandir concepto→concepto
                continue
            m = dict(row)
            m["score"] = boosted
            m["via"] = f"edge:{parent['id']}"
            added.append(m)
            present_map[nid] = m
            if len(added) >= max_add:
                break

    added += _ppr_expand(parents, present_map, ppr_max_add, ppr_discount)
    return results + added


def _ppr_expand(parents: list[dict], present_map: dict, max_add: int, discount: float) -> list[dict]:
    """PPR desde los mismos `parents` que ya sembraron el 1-hop (V2-111 §9.1). Solo añade lo que el 1-hop
    (arriba, ya reflejado en `present_map`) no trajo — nunca duplica. Kill-switch `ZAELAR_GRAPH_PPR=0`."""
    if not parents or max_add <= 0 or os.getenv("ZAELAR_GRAPH_PPR", "1") == "0":
        return []
    seeds = {p["id"]: max(float(p.get("score", 0.0)), 1e-6) for p in parents}
    if not seeds:
        return []
    try:
        from . import graph_ppr as _ppr
        ranks = _ppr.personalized_pagerank(seeds)
    except Exception:
        return []
    candidates = [(nid, v) for nid, v in ranks.items() if nid not in seeds and nid not in present_map]
    if not candidates:
        return []
    max_rank = max(v for _, v in candidates)
    if max_rank <= 0:
        return []
    candidates.sort(key=lambda kv: kv[1], reverse=True)
    max_seed_score = max(seeds.values())
    db = _db.get_db()
    added: list[dict] = []
    for nid, v in candidates:
        if len(added) >= max_add:
            break
        row = db.query_one(
            "SELECT id, level, kind, text, importance, weight, last_access, pinned FROM memories "
            "WHERE id=? AND valid=1 AND kind != 'concept' "
            "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted')",
            (nid,),
        )
        if row is None:
            continue
        m = dict(row)
        m["score"] = max_seed_score * (v / max_rank) * discount
        m["via"] = "ppr"
        added.append(m)
        present_map[nid] = m
    return added


def search(
    prompt: str,
    k: int = POOL_K,
    limit: int = 12,
    expand: bool = True,
    reinforce: bool = False,
    rerank: bool = True,
) -> list[dict]:
    """Ruta caliente: devuelve recuerdos relevantes ordenados por score (con `score` en cada dict)."""
    db = _db.get_db()
    from .clock import now as _clock_now
    now = _clock_now()
    qvec = _emb.embed(prompt)
    vec = vec_search(qvec, k=k)
    kw = fts_search(prompt, k=k)
    para = vec_search_paraphrases(qvec, k=k)  # V2-031 T2: tercer canal, mapeado a memory_id real

    fused = rrf(vec, kw, para)
    if not fused:
        # degradación total (sin vec ni fts): LIKE básico sobre los tokens.
        toks = _FTS_TOKEN.findall(prompt.lower())
        if toks:
            like = "%" + toks[0] + "%"
            rows = db.query(
                "SELECT id FROM memories WHERE valid=1 AND lower(text) LIKE ? ORDER BY updated DESC LIMIT ?",
                (like, k),
            )
            fused = {r["id"]: 1.0 for r in rows}
    if not fused:
        return []

    max_rrf = max(fused.values()) or 1.0
    ids = list(fused.keys())
    placeholders = ",".join("?" * len(ids))
    rows = db.query(
        f"SELECT id, level, kind, text, importance, weight, last_access, pinned "
        f"FROM memories WHERE valid=1 AND id IN ({placeholders}) "
        # CUARENTENA (multi-fuente): el contenido trust='untrusted' (peers de cluster/agentes ajenos) NUNCA se
        # devuelve por el recall semántico — anti prompt-injection. Solo aflora por `memory.recent_by_source`.
        f"AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted')",
        ids,
    )
    results: list[dict] = []
    for row in rows:
        m = dict(row)
        rel = fused.get(m["id"], 0.0) / max_rrf
        rec = _recency(m["last_access"], now)
        m["score"] = (
            ALPHA * rel + BETA * rec + GAMMA * float(m["importance"]) + DELTA * float(m["weight"])
        )
        results.append(m)
    results.sort(key=lambda r: r["score"], reverse=True)

    # RE-RANKING (V2-030): a escala el embedding local ordena "borroso" — la respuesta está en el top-10 pero no en
    # el top-1/3. El reranker (model-agnostic, local por defecto) reordena el tope LEYENDO query+recuerdo juntos.
    # FUERA del hot path (esta search del recall largo ya va bajo demanda + to_thread) y FAIL-OPEN (ante cualquier
    # problema devuelve el orden intacto). No toca ESTADO/CORTO. `rerank()` funde con recencia/importancia (blend).
    if rerank and len(results) > 1:
        try:
            from . import rerank as _rr
            if _rr.enabled():
                results = _rr.rerank(prompt, results)
        except Exception:
            pass  # el reranker NUNCA rompe el recall

    results = results[:limit]

    if expand:
        results = graph_expand(results)
        results.sort(key=lambda r: r["score"], reverse=True)

    if reinforce and results:
        try:
            import bus  # lazy: evita acoplar la memoria al bus en import-time
            bus.emit_sync("memory.reinforce", {"ids": [r["id"] for r in results]})
        except Exception:
            pass
    return results
