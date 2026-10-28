"""Graph expansion of a result list: 1-hop neighbours by `edges` (concept clusters first) plus a PPR pass."""
import os

from .. import db as _db
from .channels import _lane_sql


def graph_expand(results: list[dict], top: int = 6, max_add: int = 8, discount: float = 0.5,
                 concept_discount: float = 1.0, ppr_max_add: int = 6, ppr_discount: float = 0.35,
                 lane: str = "all") -> list[dict]:
    """Adds `edges` neighbours of the `top` results (optional). No duplicates; discounted score.

    CONCEPT GRAPH (T126): when the parent is a CONCEPT node (kind='concept') the query matched («deporte»), its
    neighbours ARE the answer to the category → barely discounted (`concept_discount`), and concepts go FIRST so
    the global `max_add` cannot crowd their cluster out. Plain pill↔pill neighbours keep the strong discount.

    EXTRA CHANNEL (V2-111 §9.1): then a Personalized PageRank pass (`graph_ppr.py`) from the SAME parents adds what
    1-hop cannot reach, with its own discount. Fail-open and switchable off (`ZAELAR_GRAPH_PPR=0`)."""
    if not results:
        return results
    db = _db.get_db()
    present_map = {r["id"]: r for r in results}
    added: list[dict] = []
    # EVERY retrieved concept node (at any rank) is a parent: it signals category intent and its cluster IS the
    # answer, even when the node ranks low. They are few → cheap. Then the best pills as normal parents.
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
                # Already in the results (vector/FTS brought it) but maybe SUNK: a concept parent PROMOTES its
                # cluster member to the cluster's score (otherwise category recall stayed buried).
                if is_concept:
                    ex = present_map[nid]
                    if boosted > ex.get("score", 0):
                        ex["score"] = boosted
                        ex["via"] = f"edge:{parent['id']}"
                continue
            row = db.query_one(
                "SELECT id, level, kind, text, importance, weight, last_access, pinned, slot "
                "FROM memories WHERE id=? AND valid=1 "
                # QUARANTINE: untrusted peer/agent content (trust='untrusted') NEVER surfaces by semantic recall
                # (nor the concept graph) — only by the explicit `recent_by_source` query.
                "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted')"
                + (f" AND {_lane_sql(lane)}" if _lane_sql(lane) else ""),   # an edge never crosses lanes
                (nid,),
            )
            if row is None or row["kind"] == "concept":   # never expand concept→concept
                continue
            m = dict(row)
            m["score"] = boosted
            m["via"] = f"edge:{parent['id']}"
            added.append(m)
            present_map[nid] = m
            if len(added) >= max_add:
                break

    added += _ppr_expand(parents, present_map, ppr_max_add, ppr_discount, lane=lane)
    return results + added


def _ppr_expand(parents: list[dict], present_map: dict, max_add: int, discount: float,
                lane: str = "all") -> list[dict]:
    """PPR from the same `parents` that seeded the 1-hop (V2-111 §9.1). Only adds what 1-hop (already in
    `present_map`) did not bring — never duplicates. Kill-switch `ZAELAR_GRAPH_PPR=0`."""
    if not parents or max_add <= 0 or os.getenv("ZAELAR_GRAPH_PPR", "1") == "0":
        return []
    seeds = {p["id"]: max(float(p.get("score", 0.0)), 1e-6) for p in parents}
    if not seeds:
        return []
    try:
        from .. import graph_ppr as _ppr
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
            "SELECT id, level, kind, text, importance, weight, last_access, pinned, slot FROM memories "
            "WHERE id=? AND valid=1 AND kind != 'concept' "
            "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted')"
            + (f" AND {_lane_sql(lane)}" if _lane_sql(lane) else ""),
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
