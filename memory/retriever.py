"""memory/retriever.py — retriever híbrido (RUTA CALIENTE · ms) (V2-002 · T47).

Compone el **contexto mínimo** ante un prompt, lo más rápido posible (lectura directa, WAL, sin bloquear al
escritor). El **estado** se inyecta SIEMPRE aparte (sin búsqueda, `memory/state.py`); aquí va lo demás:

    vector (sqlite-vec, k=40)  ∥  keyword (FTS5, k=40)
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


def vec_search(query_vec: list[float], k: int = 40) -> list[tuple[int, float]]:
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


def fts_search(prompt: str, k: int = 40) -> list[tuple[int, float]]:
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
                 concept_discount: float = 1.0) -> list[dict]:
    """Añade vecinos por `edges` de los `top` mejores resultados (opcional). No duplica; score descontado.

    GRAFO DE CONCEPTOS (T126): si el parent es un NODO-CONCEPTO (kind='concept') que casó la query (p. ej.
    "deporte" en "¿qué hago de deporte?"), sus vecinos SON la respuesta a la categoría → apenas se descuentan
    (`concept_discount` alto) y los conceptos se procesan PRIMERO para que su cluster no lo desplace el
    `max_add` global. Los vecinos pill↔pill normales siguen con el descuento fuerte (contexto, no respuesta)."""
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
    return results + added


def search(
    prompt: str,
    k: int = 40,
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

    fused = rrf(vec, kw)
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
