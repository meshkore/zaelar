"""nucleo/circuit/reopen.py — a correction on a FINISHED search reopens that errand (V2-840 H5).

Car search, 2026-11-02: after the errand had delivered, «only the peninsula» reached the sheet as an inline `criteria`
op — it wrote `criteria.excluded` and its verdict was `undeclared` — and nothing else happened: the errand was closed,
so the row on an island stayed. The sheet's own gate matches names, and «islands» is not written on a row in Menorca.
Whether a row is on an island, or white, is a fact about THAT row, judged by reading it — the worker's job, never a
word table's.

So a criteria change on a sheet whose errand is finished is handed to the circuit here:
  · the errand's brief takes the change (hard criteria, exclusions, the correction itself as `feedback`);
  · it is re-checked: a change the brief already holds is met, and nothing moves;
  · otherwise it is unmet until the rows have been judged against it, and the SAME errand is relaunched as a
    continuation (`task_uid`, the V2-835 door in `continuation.py`) on the same sheet — its rows, its pool, its
    rejected and its sources are where it left them — with the brief reused, never recomposed.
Every correction does this again: there is no count. A correction while the errand still runs is not handled here —
the live worker hears it on its own path.
"""
from __future__ import annotations

import time

from loguru import logger

#: A relaunch takes a moment to open its row; a second correction inside it updates the brief the relaunch will read.
_PENDING_S = 90.0
_PENDING: dict[str, float] = {}


def _row_of(sheet: str, data: dict) -> dict | None:
    """The errand row this sheet belongs to: a named sheet IS its errand's durable id; the shared one names it."""
    from nucleo.circuit import ledger as _ledger
    st = _ledger.store()
    cands = [sheet] if sheet else []
    owner = str((data or {}).get("errand") or "").strip()
    if owner:
        cands += [owner, _ledger.task_uid(owner)]
    for uid in cands:
        if uid and (row := st.task_get(uid)):
            return row
    return None


def _live(uid: str, sheet: str) -> bool:
    try:
        from nucleo import dispatch as _d
        return any(str(getattr(r, "uid", "") or "") == uid or (sheet and str(getattr(r, "sheet", "") or "") == sheet)
                   for r in list(_d._SESSIONS.values())
                   if str(getattr(r, "status", "") or "") in _d.LIVE_SESSION_STATES)
    except Exception:  # noqa: BLE001 — unreadable registry: the row's state decides alone
        return False


def finished(row: dict | None, sheet: str = "") -> bool:
    from memory.tasks_store import LIVE_STATES
    return bool(row) and str(row.get("state") or "") not in LIVE_STATES and not _live(str(row.get("id") or ""), sheet)


def _change_lines(upd: dict) -> list[str]:
    """The correction in his words, as the brief will carry it: each new hard line, exclusion and change."""
    out: list[str] = []
    for k in ("changes", "hard"):
        out += [str(x) for x in upd.get(k) or [] if str(x).strip()]
    if upd.get("excluded"):
        out.append("excluded: " + ", ".join(str(x) for x in upd["excluded"]))
    return out


def absorb(brief: dict, upd: dict) -> bool:
    """Write the change into the brief; True when it held something the brief did not already have."""
    new = False
    for k in ("hard", "soft", "quality_bar"):
        cur = brief.setdefault(k, [])
        for x in upd.get(k) or []:
            if x not in cur:
                cur.append(x)
                new = True
    ex = brief.setdefault("excluded", [])
    for x in upd.get("excluded") or []:
        if x not in ex:
            ex.append(x)
            new = True
    fb = brief.setdefault("feedback", [])
    for x in upd.get("changes") or []:
        if x not in fb:
            fb.append(x)
            new = True
    return new


def _note(lines: list[str]) -> str:
    return ("\n\n[ARNÉS] El operador ha CAMBIADO los criterios de esta búsqueda ya entregada: "
            + " · ".join(lines)[:600]
            + ". Juzga CADA fila de la hoja y de su reserva (pool) contra sus propios datos — ubicación, color, lo que "
              "diga el cambio —, quita las que no cumplan con su motivo en `rejected`, y completa la selección hasta el "
              "objetivo del brief desde las fuentes ya usadas y las que hagan falta. Lo demás ya está hecho: no lo "
              "repitas.")


def on_criteria(sheet: str, upd: dict, data: dict | None = None) -> int:
    """A `criteria` change landed on `sheet`: reopen its FINISHED errand when the change is new to it. Returns the
    relaunched task id (0 = nothing reopened). Never raises — the sheet's own write already happened."""
    try:
        row = _row_of(sheet, data or {})
        if not finished(row, sheet):
            return 0
        uid = str(row["id"])
        from nucleo.workers import brief as _brief
        brief = _brief.load(uid)
        lines = _change_lines(upd)
        if not lines:
            return 0
        if brief is not None:
            if not absorb(brief, upd):
                _event("🧾 reopen: the change is already in its brief — met, nothing relaunched", uid, lines)
                return 0
            brief["ts"] = time.time()
            _brief.save(uid, brief)
        if time.time() - _PENDING.get(uid, 0.0) < _PENDING_S:
            _event("🧾 reopen: relaunch already on its way — the brief carries this change too", uid, lines)
            return 0
        from nucleo.acts import errand as _esc
        tid = _esc.escalate_to_slowbrain(
            str(row.get("goal") or row.get("title") or "") + _note(lines),
            context={"src": "criteria_reopen", "kind": str(row.get("kind") or "research"),
                     "trace": str(row.get("trace_id") or ""), "sheet": str(row.get("sheet") or sheet or ""),
                     "surface": str(row.get("surface") or ""), "task_uid": uid,
                     **({"resume": {"brief_task": uid}} if brief is not None else {})})
        if tid:
            _PENDING[uid] = time.time()
        _event("🔁 reopen: a correction reopened the finished errand" if tid else
               "🧾 reopen: the relaunch was refused", uid, lines, tid=tid)
        return int(tid or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reopen: criteria change not handed to the circuit: {type(e).__name__}: {e}")
        return 0


def _event(label: str, uid: str, lines: list[str], tid: int = 0) -> None:
    try:
        from voice.observer import emit
        emit("task", label, role="system", text=" · ".join(lines)[:240],
             extra={"uid": uid, "cat": "circuit", **({"id": str(tid)} if tid else {})})
    except Exception:  # noqa: BLE001
        pass
