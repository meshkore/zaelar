"""proposals.py — an appointment somebody ELSE asked for, waiting for the operator's yes (V2-697).

WHY IT EXISTS. `book.py::may_schedule` answers whether the operator granted this errand permission to write
to his calendar, and until now a False there meant the agreement was simply DROPPED: the other person had
said yes, the engine had the slot, and nothing happened and nobody was told. That is the wrong half to fail
on — refusing to WRITE is right, refusing to ASK is not.

So a proposal is parked instead: the errand keeps the slot it negotiated, the operator is told in his own
next turn, and one yes from him turns it into a real appointment through `book.book()` unchanged.

THE AUTHORIZATION MODEL, and why it is not a list of trusted contacts. A proposal can arrive from a message
or from another agent in the MeshKore cluster, and a cluster peer's `handle` is SELF-DECLARED — there is no
signature behind it (`connectors/meshkore/security.py::neutralize_identity` sanitizes the string; it does not
prove it), and the allowlist that does exist is per-CLUSTER, not per-person. An allowlist keyed on a name
anybody can claim would be worse than none, because it would look like a control. So:

  · the name of whoever proposed is a LABEL SHOWN TO THE OPERATOR, never an authorization;
  · every proposal needs his explicit yes — the operator's own scoping: «de momento podemos dejar que el
    sistema siempre necesite aceptaciones manuales»;
  · the text that came from outside stays DATA. Nothing here interprets it as an instruction.

WHERE IT LIVES. On the errand row, not in a store of its own: the errand is already durable, already
expires, already appears on the operator's board, and — the part that matters most — already holds the
BINDING to the conversation the proposal arrived on, which is the address the answer has to travel back to.
A parallel table would have to re-derive all four.
"""
from __future__ import annotations

import logging
import time

from . import book as _book

logger = logging.getLogger(__name__)

#: The errand state a parked proposal sits in. It is deliberately NOT one of the negotiating states: an
#: errand waiting for the operator is not waiting for the other party, and the two must not read alike.
STATE = "proposed"


def _errands():
    """The package's own facade, imported LAZILY: `book.py` reaches this module from inside the package, so
    binding the package at import time would close the cycle."""
    from .. import errands
    return errands


def park(errand: dict, decision: dict, party: str = "") -> dict:
    """Hold an agreed slot until the operator says yes. Returns `{"ok", "why"}`; never raises.

    Called from `book.book()` when the mandate does not include `schedule`. Everything needed to write the
    appointment later is captured NOW, because the conversation that produced it may be over by the time he
    answers.
    """
    agreed = decision.get("agreed") if isinstance(decision.get("agreed"), dict) else {}
    when = _book._when(agreed.get("start"))
    if not when:
        return {"ok": False, "why": "sin hora acordada"}
    date, start = when
    end = ""
    ended = _book._when(agreed.get("end"))
    if ended and ended[0] == date:
        end = ended[1]
    proposal = {
        "date": date, "startTime": start, "endTime": end,
        "party": str(party or "")[:120],
        "medium": str(agreed.get("medium") or "").strip().lower()[:40],
        "at": f"{date} {start}",
        "asked_at": int(time.time()),
    }
    eid = str(errand.get("id") or "")
    if not eid:
        return {"ok": False, "why": "propuesta sin encargo"}
    try:
        done = dict(errand.get("done_when") or {})
        done["proposal"] = proposal
        _errands().update(eid, state=STATE, done_when=done)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: could not park the proposal for {eid} ({e!r})")
        return {"ok": False, "why": "no pude guardar la propuesta"}
    _tell_operator(errand, proposal)
    return {"ok": True, "parked": True, "date": date, "time": start}


def _tell_operator(errand: dict, proposal: dict) -> None:
    """One `[SISTEMA]` note on the operator's next turn. Best-effort: a proposal that cannot be announced is
    still parked and still visible on the agenda — losing the notice costs a delay, losing the row costs the
    appointment."""
    who = proposal.get("party") or "alguien"
    when = f"{proposal.get('date')} {proposal.get('startTime')}".strip()
    what = str(errand.get("objective") or "").strip()[:120]
    line = (f"{who} propone una cita el {when}"
            + (f" — {what}" if what else "")
            + ". Está pendiente de que TÚ la aceptes: no está en el calendario todavía. "
              "Cuéntaselo y espera su respuesta; si dice que sí, usa la acción `accept_proposal` de la agenda.")
    try:
        from voice import brain_notes
        brain_notes.push(line, key=f"proposal:{errand.get('id')}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: could not announce the proposal ({e!r})")


def pending(now: float | None = None) -> list[dict]:
    """Every proposal waiting for the operator, newest first. One row per errand, flattened for a card."""
    out: list[dict] = []
    try:
        rows = _errands().live(now)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: could not read the pending proposals ({e!r})")
        return out
    for row in rows or []:
        if str(row.get("state") or "") != STATE:
            continue
        p = (row.get("done_when") or {}).get("proposal")
        if not isinstance(p, dict):
            continue
        out.append({"errand_id": str(row.get("id") or ""),
                    "objective": str(row.get("objective") or ""),
                    "title": str(row.get("title") or ""), **p})
    out.sort(key=lambda p: int(p.get("asked_at") or 0), reverse=True)
    return out


def _find(errand_id: str) -> tuple[dict, dict] | None:
    for p in pending():
        if p["errand_id"] == errand_id or not errand_id:
            row = _errands().get(p["errand_id"])
            if row:
                return row, p
    return None


def accept(errand_id: str = "") -> dict:
    """The operator said yes: write the appointment and let the errand carry on.

    His yes IS the missing grant — that is the whole reason this was parked — so `schedule` is added to the
    errand's own mandate and `book.book()` runs unchanged. Nothing here re-implements booking: the path that
    writes a calendar row stays the single one that has always written it.
    """
    found = _find(errand_id)
    if not found:
        return {"ok": False, "error": "no encuentro ninguna propuesta pendiente"}
    row, p = found
    mandate = dict(row.get("mandate") or {})
    may = list(mandate.get("may") or [])
    if "schedule" not in may:
        may.append("schedule")
    mandate["may"] = may
    try:
        done = dict(row.get("done_when") or {})
        done.pop("proposal", None)                 # it stops being a question the moment he answers it
        row = _errands().update(row["id"], mandate=mandate, done_when=done, state="agreed") or row
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: could not grant the proposal for {row.get('id')} ({e!r})")
        return {"ok": False, "error": "no pude guardar tu respuesta"}
    decision = {"agreed": {"start": p.get("at"), "medium": p.get("medium") or ""}}
    if p.get("endTime"):
        decision["agreed"]["end"] = f"{p.get('date')} {p.get('endTime')}"
    res = _book.book(row, decision, party=str(p.get("party") or ""))
    if not res.get("ok"):
        return {"ok": False, "error": str(res.get("why") or "no pude crear la cita")}
    _retract(row.get("id"))
    return {"ok": True, "date": res.get("date"), "time": res.get("time"),
            "party": p.get("party"), "errand_id": row.get("id")}


def decline(errand_id: str = "") -> dict:
    """The operator said no. The errand closes, which RELEASES its conversation — and releasing it is what
    lets the next round with the same person start clean. Telling the requester is the errand's own job,
    through the thread it is bound to; nothing is sent from here."""
    found = _find(errand_id)
    if not found:
        return {"ok": False, "error": "no encuentro ninguna propuesta pendiente"}
    row, p = found
    try:
        _errands().close(row["id"], outcome="declined", why="el operador no acepta la cita propuesta")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: could not close the declined proposal {row.get('id')} ({e!r})")
        return {"ok": False, "error": "no pude guardar tu respuesta"}
    _retract(row.get("id"))
    return {"ok": True, "party": p.get("party"), "errand_id": row.get("id")}


def _retract(errand_id) -> None:
    try:
        from voice import brain_notes
        brain_notes.retract(f"proposal:{errand_id}")
    except Exception:  # noqa: BLE001
        pass
