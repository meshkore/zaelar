"""memory/graph_ppr.py — Personalized PageRank over the `edges` graph (V2-111 §9.1).

`retriever.graph_expand()` solo hace UN salto (pill→concepto→píldoras hermanas) — pierde conexiones
genuinamente de 2-3 saltos (pill→concepto→pill hermana→SU OTRO concepto→pill prima). Es la misma clase de
hueco que Engraphis mide con PPR (2-hop recall 0/3→3/3 frente a la expansión de 1-hop). Este módulo NO
sustituye `graph_expand()` — es un canal ADICIONAL que `retriever.py` funde con su propio descuento.

Acotado a propósito: nunca carga la tabla `edges` entera. BFS desde las semillas hasta `MAX_HOPS` o
`MAX_NODES` nodos explorados, lo que llegue antes — a escala personal (cientos de aristas) esto cubre el
grafo entero en la práctica; el techo existe para que un catálogo de entidades más denso (V2-111 fases 0-3)
no cambie el perfil de latencia sin avisar. Power iteration pura en Python sobre el subgrafo acotado — sin
numpy/scipy como dependencia nueva, coherente con que el resto del camino de memoria evita dependencias
pesadas. Fail-open TOTAL: grafo vacío, `edges` sin filas o cualquier excepción → `{}`, nunca rompe el
retriever que lo llama.
"""
import os

from . import db as _db

ALPHA = float(os.getenv("ZAELAR_PPR_ALPHA", "0.85"))       # damping: prob. de continuar el paseo
MAX_ITER = int(os.getenv("ZAELAR_PPR_MAX_ITER", "20"))
TOL = 1e-6
MAX_HOPS = int(os.getenv("ZAELAR_PPR_MAX_HOPS", "3"))
MAX_NODES = int(os.getenv("ZAELAR_PPR_MAX_NODES", "400"))  # tope del subgrafo explorado (escala personal)
FANOUT = int(os.getenv("ZAELAR_PPR_FANOUT", "12"))         # aristas consideradas por nodo y salto


def _load_subgraph(db, seed_ids: list[int]) -> tuple[dict[int, list[tuple[int, float]]], set[int]]:
    """Bounded BFS from `seed_ids`. Returns (adjacency ONLY for expanded nodes, ALL seen nodes—
    including leaves at the last hop that were never expanded, so they do not silently lose their mass)."""
    adj: dict[int, list[tuple[int, float]]] = {}
    seen: set[int] = set(seed_ids)
    frontier = list(dict.fromkeys(seed_ids))
    for _hop in range(MAX_HOPS):
        if not frontier or len(seen) >= MAX_NODES:
            break
        next_frontier: list[int] = []
        for nid in frontier:
            if nid in adj:
                continue
            rows = db.query(
                "SELECT to_id, weight FROM edges WHERE from_id=? ORDER BY weight DESC LIMIT ?",
                (nid, FANOUT),
            )
            neigh = [(int(r["to_id"]), float(r["weight"])) for r in rows]
            adj[nid] = neigh
            for to_id, _w in neigh:
                if to_id not in seen and len(seen) < MAX_NODES:
                    seen.add(to_id)
                    next_frontier.append(to_id)
        frontier = next_frontier
    return adj, seen


def personalized_pagerank(seed_weights: dict[int, float]) -> dict[int, float]:
    """Power-iteration PPR seeded by `seed_weights` (id -> restart mass; it need not sum to 1—it is
    normalized internally). Returns id -> PPR score for every touched node (including seeds). Fail-open: an
    empty/degenerate graph or any exception returns `{}`—the caller treats it as "nothing to add"."""
    if not seed_weights:
        return {}
    try:
        db = _db.get_db()
        seed_ids = list(seed_weights.keys())
        adj, seen = _load_subgraph(db, seed_ids)
    except Exception:
        return {}
    if not seen:
        return {}

    total = sum(seed_weights.values()) or 1.0
    restart = {nid: w / total for nid, w in seed_weights.items()}
    nodes = list(seen)
    rank = {nid: restart.get(nid, 0.0) for nid in nodes}

    for _ in range(MAX_ITER):
        new_rank: dict[int, float] = {nid: (1.0 - ALPHA) * restart.get(nid, 0.0) for nid in nodes}
        for nid in nodes:
            neigh = adj.get(nid) or []          # nodo sin expandir (hoja del último salto) = sumidero, ok
            out_w = sum(w for _, w in neigh)
            if out_w <= 0:
                continue
            share = ALPHA * rank.get(nid, 0.0)
            if share <= 0:
                continue
            for to_id, w in neigh:
                if to_id in new_rank:            # nunca fuera de `seen` — coherente con el corte de MAX_NODES
                    new_rank[to_id] += share * (w / out_w)
        delta = sum(abs(new_rank[n] - rank.get(n, 0.0)) for n in nodes)
        rank = new_rank
        if delta < TOL:
            break
    return rank
