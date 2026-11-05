"""nucleo/acts/card_owner.py — ONE card per task, armed (V2-852 T11, invariants I1 and I7).

The shadow record (`surface_owner`, V2-844 F0) measured who would own each surface; this is the half that acts on it:
  · ONE NAME per task — its row. A boot-local number (`worker:3`, a confirmation parked under `3`) is `task_uid(3)`,
    the same composition its sheet carries (the session measured a relaunch's own first show as a «non owner»);
  · a card a LIVE task owns by name (its results sheet) is never shown by another task — the arbiter refuses it;
    an ENDED task owns its card as a record, never against a new task of the same widget, which takes it over;
  · a cancelled task's card closes with it when it holds nothing; a card with rows stays his to read.
Every entry point is best-effort and never raises: an unreadable owner refuses nothing (V2-653 F1 — zero false
refusals).
"""
from __future__ import annotations

from loguru import logger


def errand(ref) -> str:
    """ONE name per task: its row (V2-852 I1). A boot-local number (`worker:3`, a confirmation parked under `3`) is the
    row `task_uid(3)` — the same composition its sheet carries; a ref that already is a row id is kept as it is. The
    session measured the relaunch's own first show as a «non owner»: `errand:3` against `errand:abffbc-3`."""
    ref = str(ref or "").strip()
    if ref.isdigit():
        try:
            from nucleo.circuit import ledger as _ledger
            ref = _ledger.task_uid(ref)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"card_owner: row of {ref} unreadable — {type(e).__name__}: {e}")
    return f"errand:{ref}"


def errand_of_rec(r) -> str:
    return errand(str(getattr(r, "uid", "") or "") or str(getattr(r, "task_id", "") or ""))


def live_owner_of_sheet(sid: str) -> str:
    """The LIVE errand whose sheet `sid` is (running, queued or parked on his confirmation), else "". An ended errand
    owns its sheet as a record, never against a new task: a new task of the same widget takes the card over."""
    sid = str(sid or "").strip()
    if not sid:
        return ""
    try:
        from nucleo import dispatch as _d
        for r in list(_d._SESSIONS.values()):
            uid = str(getattr(r, "uid", "") or "")
            if sid in (str(getattr(r, "sheet", "") or ""), uid):
                return errand_of_rec(r)
        from nucleo.dispatch import confirm as _dc
        for tid, p in list((getattr(_dc, "_PENDING_CONFIRM", None) or {}).items()):
            if str(p.get("sheet") or "") == sid:
                return errand(tid)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_owner: live owner of {sid} unreadable — {type(e).__name__}: {e}")
    return ""


def held_by_another(wid: str, src: str) -> str:
    """ONE CARD PER TASK (V2-852 T11, I1/I7): the live errand that owns the card `wid` when an errand that is NOT it
    asks to show it, else "". Only a card that belongs to a row by name (a results sheet) is judged; his hands, the
    turn and the lifecycle are never refused here. Never raises: an unreadable owner refuses nothing (V2-653 F1 —
    zero false refusals)."""
    subscribe()
    try:
        from nucleo.acts import surface_owner as _so
        actor = _so.actor_of(src)
        sheet = _so._sheet_of(wid)
        if not (sheet and actor.startswith("errand:")):
            return ""
        owner = live_owner_of_sheet(sheet)
        return owner if owner and owner != actor else ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_owner: owner of {wid} unreadable — {type(e).__name__}: {e}")
        return ""


def is_live(name: str) -> bool:
    """Is the errand `name` live — running, queued or parked on his confirmation?"""
    try:
        from nucleo import dispatch as _d
        from nucleo.dispatch import confirm as _dc
        return (any(errand_of_rec(r) == name for r in list(_d._SESSIONS.values()))
                or any(errand(tid) == name for tid in list(getattr(_dc, "_PENDING_CONFIRM", None) or {})))
    except Exception:  # noqa: BLE001
        return True                 # unreadable: keep the claim as it is — a measurement never invents a takeover


def task_ended(uid: str, state: str, *, emit=None) -> bool:
    """A task's row ENDED (`circuit.settle`): a cancelled task's card closes with it when it holds nothing (V2-852 T11
    — the empty card of the cancelled run stayed beside the relaunch's own). A card with rows is his to read and stays.
    True when a close was sent. Never raises."""
    try:
        if str(state or "") != "cancelled":
            return False
        from nucleo.circuit import ledger as _ledger
        row = _ledger.get(str(uid or "")) or {}
        sheet = str(row.get("sheet") or "").strip()
        if not sheet or live_owner_of_sheet(sheet) not in ("", errand(uid)):
            return False                # no card, or another live task holds it now
        from widgets.results import data as _sheet
        if not _sheet.view_data(sheet).get("empty"):
            return False
        from nucleo.acts import canvas
        sent = canvas.apply("close", _sheet.instance_id(sheet), src="system:task-ended", emit=emit)
        __import__("nucleo.acts.surface_owner", fromlist=["x"]).orphan(sheet, "closed", emit=emit)
        return bool(sent)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_owner: card of the ended {uid} not closed — {type(e).__name__}: {e}")
        return False


def _on_bus(ev: dict) -> None:
    """The `task.ended` subscriber (emitted once per row that moves into its ending, `circuit._state_event`)."""
    if not isinstance(ev, dict) or ev.get("topic") != "task.ended":
        return
    p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    task_ended(str(p.get("task_id") or ""), str(p.get("state") or ""))


def subscribe() -> None:
    """Arm the `task.ended` sink. Idempotent; a sink does not survive `bus.reset()`, so every show re-arms it."""
    try:
        import bus
        bus.add_sink(_on_bus)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_owner: task.ended sink not armed — {type(e).__name__}: {e}")


subscribe()
