"""`search()` — the hot-path recall: lanes, the wrong-space guard, RRF, scoring, rerank and graph expansion.

⚠️ `search` calls `vec_search` / `fts_search` / `vec_search_paraphrases` through THIS module's globals: a test
that wants to intercept a channel patches `memory.retriever.recall`, not the package."""
import logging
import time

from .. import db as _db
from .. import embeddings as _emb
from .channels import (
    ALPHA, BETA, DELTA, GAMMA, LANE_ALL, LANE_MESSAGES, LANE_OWN, POOL_K, _FTS_TOKEN, _lane_sql, _recency,
    fts_search, rrf, vec_search, vec_search_paraphrases,
)
from .graph import graph_expand

_WRONG_SPACE_GAP_S = 60.0
_wrong_space_last = 0.0


def _warn_wrong_space() -> None:
    """State that can deceive has to be VISIBLE and fixable in one gesture — this read is running on the lexical
    channel alone, and the numbers it produces are NOT comparable with a healthy run's. Rate-limited to once a
    minute: a degraded window is 300s of MANY recalls, and one line per recall would bury the signal it is for."""
    global _wrong_space_last
    now = time.time()
    if now - _wrong_space_last < _WRONG_SPACE_GAP_S:
        return
    _wrong_space_last = now
    # V2-741 — TELL THE TWO CAUSES APART: they call for opposite fixes. Identical signatures mean the EMBEDDER
    # returned nothing (a credential, quota or network); different ones mean a re-index. The signatures are
    # COMPARED, not printed side by side — a line naming the wrong cause sends the reader to the wrong file.
    try:
        from .. import reembed as _reembed
        active, stored = str(_reembed.signature() or ""), str(_reembed.stored_signature() or "")
        if active and stored and active == stored:
            detail = (f"recall on FTS only: the embedder returned nothing this time — the space "
                      f"({active}) is the indexed one, so this is the EMBEDDER (key, quota or "
                      f"network), not a migration")
            _why = str(getattr(_emb, "last_error", lambda: "")() or "")
            if _why:
                detail += f" — the provider said: {_why}"
        else:
            detail = (f"recall on FTS only: active embedding space ({active or '?'}) is not the "
                      f"indexed one ({stored or '?'}) — the index needs re-embedding")
    except Exception:  # noqa: BLE001
        detail = "recall on FTS only: the query's embedding space is not the indexed one"
    try:
        from voice import health_state
        health_state.record("memory", "degraded", detail)
    except Exception:  # noqa: BLE001
        pass            # observability NEVER breaks a read
    try:
        from voice.observer import emit
        emit("memory", "espacio vectorial descuadrado", text=detail, extra={"module": "memory.retriever"})
    except Exception:  # noqa: BLE001
        pass


def search(
    prompt: str,
    k: int = POOL_K,
    limit: int = 12,
    expand: bool = True,
    reinforce: bool = False,
    rerank: bool = True,
    lexical_only: bool = False,
    lane: str = "own",
) -> list[dict]:
    """Hot path: relevant memories ordered by score (each dict carries `score`).

    `lexical_only` (V2-762): the FTS5 channel alone — no embedding call, no reranker. It is the half of the recall
    that lives entirely on this machine (15-90 ms measured), and the turn's recall budget runs it BESIDE the full
    search so that a slow embedding provider degrades the recall instead of erasing it.

    `lane` (V2-802 T-03, see `LANE_*`): `own` (the default — the operator-fact recall) / `messages` search one pool;
    `all` returns the own lane (up to `limit`) followed by the message lane (up to `limit`), so an inbound message
    never outranks an own row. Each lane runs its own channels, so `all` costs two lexical/vector passes over one
    embedding of the query."""
    if lane not in (LANE_OWN, LANE_MESSAGES, LANE_ALL):
        lane = LANE_OWN
    if lexical_only:
        rerank = False
    t0 = time.perf_counter()
    qvec = None if lexical_only else _emb.embed(prompt)
    ms = {"embed_ms": _ms_since(t0), "lexical_ms": 0.0, "vector_ms": 0.0, "rerank_ms": 0.0}
    lanes = (LANE_OWN, LANE_MESSAGES) if lane == LANE_ALL else (lane,)
    out: list[dict] = []
    for ln in lanes:
        out += _search_lane(prompt, qvec, ln, k=k, limit=limit, expand=expand, rerank=rerank,
                            lexical_only=lexical_only, ms=ms)
    _observe_timing(ms, total_ms=_ms_since(t0), lane=lane, lexical_only=lexical_only, hits=len(out))
    if reinforce and out:
        try:
            import bus  # lazy: keeps memory from coupling to the bus at import time
            bus.emit_sync("memory.reinforce", {"ids": [r["id"] for r in out]})
        except Exception:
            pass
    return out


def _ms_since(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _observe_timing(ms: dict, **extra) -> None:
    """The recall's cost BY PHASE as one event, so the viewer and the Master show where a slow recall went."""
    try:
        from voice.observer import emit
        emit("memory", "recall medido", role="system",
             text=" · ".join(f"{k[:-3]} {v:.0f} ms" for k, v in ms.items()) + f" · total {extra['total_ms']:.0f} ms",
             extra={"layer": "recall", **ms, **extra})
    except Exception as e:  # noqa: BLE001 — observability NEVER breaks the recall
        logging.getLogger("zaelar.memory.retriever").debug("recall timing event not emitted: %s", e)


def _search_lane(prompt: str, qvec, lane: str, *, k: int, limit: int, expand: bool, rerank: bool,
                 lexical_only: bool, ms: dict | None = None) -> list[dict]:
    """One lane of `search()`: channels → RRF → score → rerank → graph, all restricted to `lane`."""
    db = _db.get_db()
    from ..clock import now as _clock_now
    now = _clock_now()
    # A query embedded in the WRONG SPACE is worse than no vector channel at all: fused into RRF it is noise
    # presented as evidence. Two silent ways in: the backend LATCHED to a fallback (a transient 503 demotes the
    # process to another model for `_BACKEND_RECHECK_S` — `last_degraded` does not catch it, the fallback
    # SUCCEEDED in a different geometry), or the embed fell over IN FLIGHT (`last_degraded`). FTS keeps carrying
    # the read, so the symptom is only «recall got worse». Fail-open: `space_ok()` is True without a verdict.
    from .. import reembed as _reembed
    space_ok = (not lexical_only) and _reembed.space_ok() and not getattr(_emb, "last_degraded", False)
    ms = ms if ms is not None else {}
    t0 = time.perf_counter()
    vec = vec_search(qvec, k=k, lane=lane) if space_ok else []
    para = vec_search_paraphrases(qvec, k=k, lane=lane) if space_ok else []  # V2-031 T2: third channel
    ms["vector_ms"] = ms.get("vector_ms", 0.0) + _ms_since(t0)
    t0 = time.perf_counter()
    kw = fts_search(prompt, k=k, lane=lane)             # lexical: always, it does not depend on any space
    ms["lexical_ms"] = ms.get("lexical_ms", 0.0) + _ms_since(t0)
    if not space_ok and not lexical_only:
        _warn_wrong_space()

    fused = rrf(vec, kw, para)
    if not fused:
        # total degradation (no vec, no fts): a basic LIKE on the tokens.
        toks = _FTS_TOKEN.findall(prompt.lower())
        if toks:
            like = "%" + toks[0] + "%"
            cond = _lane_sql(lane)
            rows = db.query(
                "SELECT id FROM memories WHERE valid=1 AND lower(text) LIKE ? "
                + (f"AND {cond} " if cond else "") + "ORDER BY updated DESC LIMIT ?",
                (like, k),
            )
            fused = {r["id"]: 1.0 for r in rows}
    if not fused:
        return []

    max_rrf = max(fused.values()) or 1.0
    ids = list(fused.keys())
    placeholders = ",".join("?" * len(ids))
    rows = db.query(
        f"SELECT id, level, kind, text, importance, weight, last_access, pinned, slot "
        f"FROM memories WHERE valid=1 AND id IN ({placeholders}) "
        # QUARANTINE (multi-source): trust='untrusted' content (cluster peers, foreign agents) is NEVER returned by
        # semantic recall — anti prompt-injection. It only surfaces through `memory.recent_by_source`.
        f"AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted')"
        + (f" AND {_lane_sql(lane)}" if _lane_sql(lane) else ""),
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

    # RE-RANKING (V2-030): at scale the local embedding orders «fuzzily» (the answer is in the top-10, not the
    # top-1/3). The reranker reorders the top reading query+memory together. FAIL-OPEN: any problem keeps the order.
    t0 = time.perf_counter()
    if rerank and len(results) > 1:
        try:
            from .. import rerank as _rr
            if _rr.enabled():
                results = _rr.rerank(prompt, results)
        except Exception:
            pass  # the reranker NEVER breaks the recall
    ms["rerank_ms"] = ms.get("rerank_ms", 0.0) + _ms_since(t0)

    results = results[:limit]

    if expand:
        results = graph_expand(results, lane=lane)
        results.sort(key=lambda r: r["score"], reverse=True)

    # A concept node is a SEED, not an answer (V2-114 F4.1): `graph_expand` needs it near the top (it promotes its
    # cluster, T126), which is why it is filtered AFTER — but its `text` is just the concept word, zero information
    # in a top-3 slot. The other graph read paths already exclude it (`_ppr_expand`, `api.by_concepts`).
    return [r for r in results if r.get("kind") != "concept"]
