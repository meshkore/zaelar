"""memory/graph.py — el grafo de la memoria (V2-002 · T50).

El grafo son **aristas en el MISMO fichero** SQLite (tabla `edges`, nada de Neo4j). Este módulo es la cara de
LECTURA/enlace del grafo:

  - `link(from, to, type, weight)` — crea/actualiza una arista. La ESCRITURA real la hace el writer (único
    escritor); por la ruta async se encola vía `memory/api.py`. Aquí se ofrece el atajo directo (delegando en
    `writer.link`) para el consolidador/agente de memoria y los tests.
  - `neighbors(id, type=None)` — aristas salientes de un nodo (ordenadas por peso).
  - `expand(ids, depth=1)` — expansión por vecindad (BFS acotado) → conjunto de ids alcanzables. Lo usa el
    retriever para traer recuerdos vecinos relevantes (top-K) sin volver a buscar.
"""
from . import db as _db
from . import writer as _writer


def link(from_id: int, to_id: int, type: str = "about", weight: float = 1.0) -> None:
    """Crea/actualiza una arista (idempotente). Atajo directo → writer (único escritor)."""
    _writer.link(from_id, to_id, type, weight)


def neighbors(mid: int, type: str | None = None, limit: int = 20) -> list[dict]:
    """Aristas salientes de `mid`, mejor peso primero. Filtro opcional por tipo."""
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
    """BFS acotado desde `ids`. Devuelve los ids VECINOS alcanzados (sin incluir los de partida)."""
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
