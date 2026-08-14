"""memory/graph.py — the memory graph (V2-002 · T50).

The graph is **edges in the SAME SQLite file** (`edges` table, no Neo4j). This module is the graph's READ/link face:

  - `link(from, to, type, weight)` — create/update an edge. The real WRITE is done by the writer (single writer);
    through the async path it is queued via `memory/api.py`. This direct shortcut (delegating to `writer.link`) is
    offered for the consolidator/memory agent and tests.
  - `neighbors(id, type=None)` — outgoing edges from a node (ordered by weight).
  - `expand(ids, depth=1)` — neighborhood expansion (bounded BFS) -> reachable id set. Used by the retriever to
    bring relevant neighbor memories (top-K) without searching again.
"""
from . import db as _db
from . import writer as _writer


def link(from_id: int, to_id: int, type: str = "about", weight: float = 1.0) -> None:
    """Create/update an edge (idempotent). Direct shortcut -> writer (single writer)."""
    _writer.link(from_id, to_id, type, weight)


def neighbors(mid: int, type: str | None = None, limit: int = 20) -> list[dict]:
    """Outgoing edges from `mid`, highest weight first. Optional type filter."""
    db = _db.get_db()
    if type is None:
        rows = db.query(
            "SELECT to_id, type, weight FROM edges WHERE from_id=? ORDER BY weight DESC LIMIT ?",
            (int(mid), limit),
        )
    else:
        rows = db.query(
            "SELECT to_id, type, weight FROM edges WHERE from_id=? AND type=? ORDER BY weight DESC LIMIT ?",
            (int(mid), type, limit),
        )
    return [dict(r) for r in rows]


def expand(ids: list[int], depth: int = 1, per_node: int = 5) -> set[int]:
    """Bounded BFS from `ids`. Return reached NEIGHBOR ids (excluding starting ids)."""
    if not ids or depth < 1:
        return set()
    seen: set[int] = set(int(i) for i in ids)
    frontier: set[int] = set(seen)
    reached: set[int] = set()
    for _ in range(depth):
        nxt: set[int] = set()
        for node in frontier:
            for e in neighbors(node, limit=per_node):
                nid = e["to_id"]
                if nid not in seen:
                    nxt.add(nid)
                    reached.add(nid)
                    seen.add(nid)
        if not nxt:
            break
        frontier = nxt
    return reached
