"""memory/retriever — hybrid retriever (HOT PATH · ms) (V2-002 · T47).

Composes the minimal context for a prompt as fast as possible (direct reads, WAL, never blocking the writer).
The STATE is injected separately, always, without search (`memory/state.py`); this is the rest:

    vector (sqlite-vec, k=POOL_K)  ∥  keyword (FTS5, k=POOL_K)  ∥  paraphrases (vec_paraphrases, k=POOL_K)
        → RRF fusion  ( rrf(doc) = Σ 1/(k+rank) , k=60 )
        → score = α·rel + β·rec + γ·imp + δ·use    (α .45 · β .25 · γ .20 · δ .10)
        → rerank (optional) → graph_expand (optional: neighbours by `edges` + PPR) → cut to `limit`

Only `valid=1` rows. Without sqlite-vec it degrades to FTS alone; without FTS, to a basic LIKE — it never raises.
Reinforcement is NOT done here (the retriever stays read-only): the facade queues the used ids, and
`search(..., reinforce=True)` only emits `memory.reinforce` on the bus.

  channels.py  scoring constants, lanes, the three channels, RRF, recency
  graph.py     graph_expand (1-hop + concept clusters) and the PPR pass
  recall.py    search(): the lanes, the wrong-space guard, fusion, scoring, rerank, graph
"""
from .channels import (  # noqa: F401
    ALPHA, BETA, DELTA, GAMMA, LANE_ALL, LANE_MESSAGES, LANE_OWN, POOL_K, RECENCY_HALFLIFE_DAYS, RRF_K, _fts_query,
    _lane_sql, fts_search, rrf, vec_search, vec_search_paraphrases,
)
from .graph import graph_expand  # noqa: F401
from .recall import search  # noqa: F401
