"""nucleo/workers/ledger.py — LEDGER durable de Brain Workers (V2-079).

El registro vivo (`nucleo/dispatch.py::_SESSIONS`) es la verdad de lo que corre AHORA y se proyecta a
`memory.state()["sessions"]` + `/api/tasks` (los hexágonos). PERO al terminar una sesión se hace `pop` → se borra
y desaparece: no había forma de ver "qué workers han corrido hoy / ayer / hace unos días". Esta pieza conserva un
HISTORIAL compacto de las ÚLTIMAS ejecuciones TERMINADAS para dar VISIBILIDAD (pestaña «Procesos» del ChatWall).

Decisiones:
  · **Fuera del hot-path**: se persiste en `sys_kv` (clave `worker_ledger`), NO en el `state()` raíz que viaja en
    cada prompt del FlashBrain — la visibilidad es de UI, el cerebro no la necesita cada turno.
  · **Solo TERMINADAS**: los workers VIVOS se leen de `dispatch.active_sessions()` (tiempo real). El ledger es el
    histórico; el frontend fusiona vivos (arriba) + histórico (abajo), dedup por id.
  · **Cap duro + limpieza en el tiempo**: MRU por `finished_at`, cap `CAP`. El barrido del sueño
    (`consolidator.consolidate`) llama a `prune()` para borrar terminadas más viejas que N días — igual que el
    decay/evict de la memoria. PESO INFINITO = las ligadas a un cron TODAVÍA activo (recurrentes): no caducan
    mientras exista su cron (el equivalente en sesiones a un recuerdo `pinned`).
"""
from __future__ import annotations

import time

CAP = 50
_KEY = "worker_ledger"
_GOAL_MAX = 160


def _load() -> list[dict]:
    try:
        from memory import api as _mem
        v = _mem.kv_get(_KEY)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _save(entries: list[dict]) -> None:
    try:
        from memory import api as _mem
        _mem.kv_set(_KEY, entries[:CAP])
    except Exception:
        pass


def clear() -> int:
    """Vacía el ledger (el HISTÓRICO de la pestaña Procesos). Lo usa el RESET para dejar los procesos EN BLANCO
    («empezamos de cero»): matar los workers vivos limpia los chips, esto limpia el histórico. Devuelve cuántas
    entradas se descartaron. El estado/memoria/datos de widgets NO se tocan (esto es solo el registro de procesos)."""
    n = len(_load())
    if n:
        _save([])
    return n


def record_finish(*, id: str, kind: str = "", goal: str = "", status: str = "done",
                   started_at: float | None = None, finished_at: float | None = None,
                   trace_id: str = "", cron: str = "", ok: bool = False) -> None:
    """Registra (o actualiza) una ejecución TERMINADA en el ledger. Dedup por `id` (una re-entrada actualiza en
    sitio), MRU (la más reciente delante), cap `CAP`. Best-effort: nunca lanza (no debe tumbar el cierre de una
    sesión). `cron` = nombre del cron de origen si la ejecución vino de uno (hoy best-effort; "" si no)."""
    try:
        fid = str(id or "").strip()
        if not fid:
            return
        now = time.time()
        entry = {
            "id": fid, "kind": str(kind or ""), "goal": str(goal or "")[:_GOAL_MAX],
            "status": str(status or "done"), "ok": bool(ok),
            "started_at": float(started_at or 0) or None,
            "finished_at": float(finished_at if finished_at is not None else now),
            "trace_id": str(trace_id or ""), "cron": str(cron or ""),
        }
        entries = [e for e in _load() if e.get("id") != fid]
        entries.insert(0, entry)
        _save(entries)
    except Exception:
        pass


def history(limit: int = CAP) -> list[dict]:
    """Últimas ejecuciones terminadas, la más reciente primero (para la pestaña «Procesos»)."""
    return _load()[: max(1, int(limit))]


def prune(max_age_days: float = 7.0, now: float | None = None, active_crons: set | None = None) -> int:
    """Barre el ledger en el sueño (V2-079): borra ejecuciones TERMINADAS más viejas que `max_age_days`, SALVO las
    ligadas a un cron TODAVÍA activo (peso infinito). Devuelve cuántas se quitaron. `active_crons` = nombres/ids de
    crons vivos (para no caducar las recurrentes); si None, se resuelve del scheduler. Nunca lanza."""
    try:
        now = float(now or time.time())
        cutoff = now - float(max_age_days) * 86400.0
        if active_crons is None:
            active_crons = _active_cron_labels()
        keep, removed = [], 0
        for e in _load():
            cron = str(e.get("cron") or "")
            if cron and cron in active_crons:          # recurrente con cron vivo → nunca caduca
                keep.append(e)
                continue
            if float(e.get("finished_at") or 0) >= cutoff:
                keep.append(e)
            else:
                removed += 1
        if removed:
            _save(keep)
        return removed
    except Exception:
        return 0


def _active_cron_labels() -> set:
    """Nombres+ids de los crons ACTIVOS (status pending) — para no caducar las ejecuciones recurrentes."""
    try:
        from nucleo import scheduler
        out = set()
        for j in scheduler.list_jobs():
            out.add(str(j.get("id")))
            if j.get("name"):
                out.add(str(j.get("name")))
        return out
    except Exception:
        return set()
