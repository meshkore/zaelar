"""memory/journal.py — la tabla `journal` de continuidad de tarea (V2-005 · T71).

La memoria central ya declara la tabla `journal` (V2-002 · schema.py): id · title · status
(`pending`|`in_progress`|`done`) · detail · created · updated. Este módulo es su **cara de acceso**
(CRUD directo, hot path — sqlite sub-ms, sin cola): lo usa el **scheduler del loop orquestador**
(`nucleo/scheduler.py`) para respaldar las tareas programadas ("cron propio" que sustituye al de Hermes),
y queda disponible para el journal de continuidad de tareas del SlowBrain (V2-006/007).

`detail` guarda un blob JSON libre (para el scheduler: `{"kind":"scheduled","schedule":{...},"prompt":...}`).
Se serializa/deserializa aquí para que el llamador maneje dicts, no strings.
"""
from __future__ import annotations

import json
import time

from . import db as _db

_STATUSES = ("pending", "in_progress", "done")


def _now() -> int:
    return int(time.time())


def _row_to_dict(row) -> dict:
    d = dict(row)
    raw = d.get("detail")
    if raw:
        try:
            d["detail"] = json.loads(raw)
        except Exception:
            d["detail"] = {"_raw": raw}
    else:
        d["detail"] = {}
    return d


def add(title: str, *, status: str = "pending", detail: dict | None = None) -> int:
    """Crea una entrada de journal y devuelve su id. `detail` se serializa a JSON."""
    if status not in _STATUSES:
        status = "pending"
    ts = _now()
    blob = json.dumps(detail or {}, ensure_ascii=False)
    return _db.get_db().execute(
        "INSERT INTO journal (title, status, detail, created, updated) VALUES (?,?,?,?,?)",
        (title or "", status, blob, ts, ts),
    )


def get(jid: int) -> dict | None:
    row = _db.get_db().query_one("SELECT * FROM journal WHERE id=?", (int(jid),))
    return _row_to_dict(row) if row is not None else None


def list_entries(status: str | None = None, limit: int = 200) -> list[dict]:
    """Lista entradas (más recientes primero), filtrando por estado si se pide."""
    if status:
        rows = _db.get_db().query(
            "SELECT * FROM journal WHERE status=? ORDER BY updated DESC LIMIT ?", (status, int(limit)))
    else:
        rows = _db.get_db().query(
            "SELECT * FROM journal ORDER BY updated DESC LIMIT ?", (int(limit),))
    return [_row_to_dict(r) for r in rows]


def update(jid: int, *, title: str | None = None, status: str | None = None,
           detail: dict | None = None) -> None:
    """Actualiza los campos dados (los None se dejan intactos). `detail` REEMPLAZA el blob entero."""
    sets, params = [], []
    if title is not None:
        sets.append("title=?"); params.append(title)
    if status is not None and status in _STATUSES:
        sets.append("status=?"); params.append(status)
    if detail is not None:
        sets.append("detail=?"); params.append(json.dumps(detail, ensure_ascii=False))
    if not sets:
        return
    sets.append("updated=?"); params.append(_now())
    params.append(int(jid))
    _db.get_db().execute(f"UPDATE journal SET {', '.join(sets)} WHERE id=?", tuple(params))


def remove(jid: int) -> None:
    _db.get_db().execute("DELETE FROM journal WHERE id=?", (int(jid),))
