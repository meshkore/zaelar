"""nucleo/flash/resume_turn.py — a turn about PENDING work resumes its rows, each from itself (V2-799).

THE CLASS. A turn that refers to earlier work («termina esas tareas», «sigue con lo de antes», «finish those», in any
language) names nothing in its own words. Two doors read only the words, and both broke it live (2026-10-26):

  · the ghost-worker guard (`escalation_guard.drop_if_fragment`) annulled the model's two commissions — complete
    briefs, an email and a table for two — as «a fragment, not an errand»;
  · the promise backstop then rebuilt ONE errand from the window (`escalate_goal_from_window`), gluing an old
    utterance to «termina esas tareas»: date, time, party size and area were gone, and the worker refused.

THE MECHANISM. What is pending is a set of durable rows (`nucleo/pending_work.py`). Where either door is about to
decide from the words alone, the turn is first resolved against those rows by a VERDICT (`jev.select_many` over the
rows' own labels — enumerated, declared, no verb table, any language). Every row his turn means resumes from itself:

  · a widget row (a draft held for his word) through its own declared action, so through its own confirm gate —
    the one question, or none when his order over a draft he has seen already is the yes (`acts.message`);
  · an errand row from its own brief, sheet and outcome (`pending_work.errand_brief`, `task_uid` → the same row and
    the same sheet, CRIT-E16) — never a glued utterance and never a blind restart;
  · a live errand is not started twice: it is already running, or already waiting on his answer.

Paid only where the words cannot decide (CRIT-K9): when a commission would be annulled as a fragment, or when the
backstop would rebuild a brief from the window — and only when something is pending. One verdict per turn (cached
by the turn's words). Never raises: on any failure the doors keep today's path.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

_CACHE: dict = {"key": None, "rows": []}
#: How long a cached verdict for the same words stays the turn's (the two doors of ONE turn are ~ms apart).
_CACHE_S = 20.0


def _criteria(operator_text: str, last_reply: str) -> str:
    return ("The operator just said: «" + str(operator_text or "").strip()[:300] + "»"
            + (f" (our previous reply: «{str(last_reply or '').strip()[:200]}»)" if str(last_reply or "").strip() else "")
            + ". Does his turn ask to continue, finish, send or go back to THIS piece of earlier work? He may mean "
              "several pieces at once. A turn that asks for something new, or refers to no earlier work, fits none.")


def rows_meant(operator_text: str, *, last_reply: str = "", pending=None) -> list[dict]:
    """The pending rows his turn refers to, best first — `[]` when nothing is pending or nothing fits. Blocking
    (one Jev trip); the async doors call `rows_meant_async`."""
    words = str(operator_text or "").strip()
    if not words:
        return []
    key = (words, str(last_reply or "")[:200])
    if _CACHE["key"] == key and time.time() - float(_CACHE.get("at") or 0) < _CACHE_S:
        return list(_CACHE["rows"])
    try:
        from nucleo import jev, pending_work
        rows = list(pending if pending is not None else pending_work.rows())
        if not rows:
            return []
        picked = jev.select_many(rows, _criteria(words, last_reply), key=lambda r: r["id"],
                                 label=pending_work.label)
        out = [p["candidate"] for p in picked if isinstance(p, dict) and p.get("candidate")]
    except Exception as e:  # noqa: BLE001
        logger.info(f"resume_turn: no verdict over the pending rows ({e}) — the doors keep their path")
        out = []
    _CACHE.update(key=key, rows=list(out), at=time.time())
    return out


async def rows_meant_async(operator_text: str, *, last_reply: str = "") -> list[dict]:
    return await asyncio.to_thread(rows_meant, operator_text, last_reply=last_reply)


def resume(rows, *, operator_text: str, apply_widget_data=None, emit=None) -> list[str]:
    """Resume each row from itself. Returns the ids resumed (live errands included: they need nothing started)."""
    done: list[str] = []
    for row in rows or []:
        try:
            if row.get("source") == "widget":
                if not callable(apply_widget_data):
                    continue
                r = row.get("resume") or {}
                apply_widget_data(row["widget"], str(r.get("action") or ""), dict(r.get("payload") or {}))
            elif str(row.get("state") or "") in ("pending", "running", "waiting"):
                pass                                  # alive: its worker already has it, or waits on his answer
            else:
                from nucleo import pending_work
                from nucleo.flash import escalate as _esc
                _esc.escalate_to_slowbrain(pending_work.errand_brief(row, operator_text), context={
                    "src": "resume", "kind": str(row.get("kind") or "generic"), "task_uid": row["id"],
                    "sheet": str(row.get("sheet") or ""), "surface": str(row.get("surface") or "")})
            done.append(str(row["id"]))
            if callable(emit):
                emit("brain", "↩️ retomo lo pendiente desde su fila", text=f"{row.get('title')} · {row.get('state')}",
                     role="system", extra={"cat": "flash", "id": row["id"], "source": row.get("source")})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"resume_turn: could not resume {row.get('id')}: {e}")
    return done


async def take(escalate_req: dict, *, operator_text: str, last_reply: str = "", apply_widget_data=None,
               emit=None) -> bool:
    """The door both decision points call: resolve the turn against the pending rows and, if it means any, resume
    them and REPLACE the turn's commissions with those resumptions (`escalate_req["resumed"]` names them, so no
    later backstop rebuilds an errand from the window). False when nothing pending is meant: today's path."""
    if escalate_req.get("resumed"):
        return True
    rows = await rows_meant_async(operator_text, last_reply=last_reply)
    if not rows:
        return False
    done = resume(rows, operator_text=operator_text, apply_widget_data=apply_widget_data, emit=emit)
    if not done:
        return False
    escalate_req["resumed"] = done
    escalate_req["v"], escalate_req["more"] = None, []
    return True


def reset() -> None:
    _CACHE.update(key=None, rows=[], at=0)


# ── the three seams the turn calls, each ONE statement there (the doors' size ratchets) ─────────────────

def from_tool(args: dict, *, escalate_req: dict, operator_text: str, apply_widget_data, emit, acted: dict) -> None:
    """`resume_task(ids)` — the MODEL's choice, from the PENDIENTE block and his words. Ids that are not pending rows
    are dropped (it chooses among declared rows); each row resumes from itself."""
    from nucleo import pending_work
    rows = pending_work.by_ids((args or {}).get("ids") or [])
    if rows and not escalate_req.get("resumed"):
        escalate_req["resumed"] = resume(rows, operator_text=operator_text, apply_widget_data=apply_widget_data,
                                         emit=emit)
        acted["widget"] = bool(escalate_req["resumed"]) or bool(acted.get("widget"))


async def before_fragment_guard(escalate_req: dict, *, operator_text: str, brief, last_reply: str, apply_widget_data,
                                emit, acted: dict) -> None:
    """The verdict COMPLETES the model where its commissions are about to be annulled as «a fragment»: the turn is
    resolved against the pending rows first (a model that already called `resume_task` is left alone)."""
    from nucleo.flash import escalation_guard as _eg
    if escalate_req.get("v") is None or escalate_req.get("resumed") \
            or not _eg.is_a_fragment(operator_text, brief=brief, last_reply=last_reply):
        return
    if await take(escalate_req, operator_text=operator_text, last_reply=last_reply,
                  apply_widget_data=apply_widget_data, emit=emit):
        acted["widget"] = True


async def before_backstops(no_tool: bool, escalate_req: dict, *, spoken_text: str, operator_text: str, brief,
                           last_reply: str, apply_widget_data, emit, acted: dict) -> bool:
    """Returns the `_no_tool` the promise backstops read. Where a tool-less promise would make a backstop REBUILD a
    brief from his words or the window, the pending rows are asked first; resumed rows mean no backstop runs."""
    if escalate_req.get("resumed"):
        return False
    if not no_tool or escalate_req.get("v") is not None:
        return no_tool
    from nucleo.flash import direct_action as _da
    from nucleo.turn import reply as _reply
    if not (_reply.owes_an_act(brief) or _da.verdict_escalates(brief, answered=False)):
        return no_tool
    if await take(escalate_req, operator_text=operator_text, last_reply=last_reply,
                  apply_widget_data=apply_widget_data, emit=emit):
        acted["widget"] = True
        return False
    return no_tool
