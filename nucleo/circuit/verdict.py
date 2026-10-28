"""nucleo/circuit/verdict.py — ONE vocabulary for how a request ended (refactor2710-02 T-00).

Five tables named the same endings with their own values (a row closed `gave_up` ranked like `met`; memory decided
«delivered» by a value's position). Now each verdict is declared ONCE, with everything a reader needs from it:
  · `ending`    — does the request end on it (a non-ending is never settled, never ranked);
  · `delivered` — did the worker hand something over (memory keeps the result; only `met` was checked);
  · `rank`      — «a later op never improves a failed row»: a settle with a lower rank does not overwrite;
  · `row_state` — the row's LIFECYCLE state (finished or not); what it was worth is the verdict beside it;
  · `ending_note_key` — the note beside a budget kill (`loop.py`); the mouth's line is `reply_<name>` (the 03);
  · `instruction` — the outcome sentence a composed delivery is built on (to the model, never to him);
  · `label`     — the event every settle emits (`kind="verdict"`), with the turn's trace.

`retrying` is `started` with `tries ≥ 1` (a relaunch is a new start), `gave_up` is `unmet` with `tries_left = 0`, and
an unreadable attest is `unverifiable` at an ending — fields, not values.
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger


@dataclass(frozen=True)
class Verdict:
    name: str
    ending: bool
    delivered: bool
    rank: int | None
    row_state: str
    ending_note_key: str
    instruction: str
    label: str


#: The eight, declared once (named constants, one per value).
(STARTED, MET, UNDECLARED, UNVERIFIABLE, UNMET, CANNOT, ASKED, SKIPPED) = (
    Verdict("started", False, False, None, "running", "", "",
            "▶️ veredicto: en marcha — el acto se lanzó y su estado final aún no consta"),
    Verdict("met", True, True, 0, "done", "worker_end_state_met",
            "It is done, and you checked the result yourself.",
            "✅ veredicto: cumplido y comprobado"),
    Verdict("undeclared", True, True, 1, "done", "", "It is done.",
            "🤷 veredicto: sin condición declarada — no se afirma nada"),
    Verdict("unverifiable", True, True, 2, "done", "worker_end_state_unverifiable",
            "The work was done, but you could NOT check the result yourself — say so plainly: done, "
            "unverified. Never say it is done as a fact.",
            "🫥 veredicto: hecho pero no verificable"),
    Verdict("unmet", True, False, 3, "failed", "worker_end_state_unmet",
            "It could not be completed. Say what is missing; do not dress it up.",
            "❌ veredicto: sin cumplir"),
    Verdict("cannot", True, False, 3, "failed", "", "It cannot be done. Say why, once, with no promise of later.",
            "🚫 veredicto: no se puede — no se lanzó nada"),
    Verdict("asked", False, False, None, "waiting", "", "",
            "❓ veredicto: el turno termina en una pregunta nuestra"),
    Verdict("skipped", False, False, None, "cancelled", "", "",
            "⏭ veredicto: no se juzga (cancelada o relevada)"),
)

ALL: dict[str, Verdict] = {v.name: v for v in (STARTED, MET, UNDECLARED, UNVERIFIABLE, UNMET, CANNOT, ASKED, SKIPPED)}

#: What older rows and records still carry, read as the one vocabulary (a stored row outlives a release).
_STORED = {"retrying": STARTED, "gave_up": UNMET, "open": STARTED}


def of(name) -> Verdict | None:
    """The verdict a stored or written name means, or None for a name no verdict has (an empty field included)."""
    n = str(name or "").strip()
    return ALL.get(n) or _STORED.get(n)


def from_attest(out) -> Verdict:
    """`spec.attest`'s answer: True met · False unmet · None (unreadable) unverifiable."""
    return {True: MET, False: UNMET}.get(out, UNVERIFIABLE)


def keeps(prev, new) -> bool:
    """True when a row already settled `prev` must keep it over `new`: a later op never improves a failed row."""
    p, n = of(prev), of(new)
    return bool(p and n and p is not n and p.rank is not None and n.rank is not None and p.rank >= n.rank)


def emit(v: Verdict, *, text: str = "", trace: str = "", **extra) -> None:
    """The settle's event, with the trace of the turn it belongs to (the observer stamps the current one when the
    caller has none). Never raises."""
    try:
        from voice import observer
        fields = {"cat": "circuit", "verdict": v.name, "delivered": v.delivered, "row_state": v.row_state, **extra}
        if trace:
            fields["trace"] = trace
        observer.emit("verdict", v.label, text=str(text or "")[:200], role="system", extra=fields)
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never decides an ending
        logger.debug(f"verdict: event not emitted — {type(e).__name__}: {e}")
