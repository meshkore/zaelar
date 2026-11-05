"""nucleo/circuit/harness.py — the ERRAND HARNESS: what END STATE a turn implied, verified against the REAL state.

V2-660: after his «Adelante» the model said «aquí tienes el texto completo» over an EMPTY `documento` card, and
nothing compared the claim with the screen until he complained (session 0141a72a).

WHAT THIS IS. A small ledger of GOALS — (kind, target, the operator's words) — born when a turn implies
an end state, verified by the readers of the product's own truth (`verify.card_view`, `verify.card_on_screen`), and
consulted at two seams (a third, the turn end reading the reply for a CLAIM of delivery — «aquí lo tienes» — and
speaking a follow-up after it, went in V2-851 F5: a phrase table over our own reply and a second line after it):
  · the prompt's live state: an open goal travels as a FACT WITH THE RULE (V2-453) so the next turn cannot
    narrate it as done;
  · the heartbeat: open goals are re-verified, closed when met (observability), expired when stale.

WHAT THIS IS NOT. Not a scenario script: goals are typed by what the turn TOUCHED (a widget id, a task),
never by the words of one errand; a widget whose truth cannot be read yields `None` (unverifiable) and the
harness stays silent about it — a wrong «you did not deliver» over a delivered card is worse than none.
Verifiers are the RESOURCE half (nailed down, testable); what to deliver stays the model's and the
worker's call (the brain-worker doctrine).
"""
from __future__ import annotations

import re
import time
import unicodedata

from loguru import logger

TTL_S = 300.0          # an errand nobody could deliver in five minutes is history, not a live goal

KIND_WIDGET_CONTENT = "widget_content"


def _norm(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


# ── the ledger ──────────────────────────────────────────────────────────────────────────────────────────
#: V2-776 M4 — the goals are no longer a registry of this module: they are entries of the ONE spec ledger
#: (`nucleo/circuit/spec.py`), marked `source="shown"`. What stays here is what makes them different from an action's
#: end state — they are verified by this module's readers, they speak only when a reply CLAIMS delivery, and they
#: expire at `TTL_S` — so `circuit.tick` leaves them alone (`SOURCE`).
SOURCE = "shown"


def _ledger():
    from nucleo.circuit import spec as _spec
    return _spec


def _expire(now: float) -> None:
    for g in _ledger().open_specs(now):
        if g.get("source") == SOURCE and now - float(g.get("born") or now) > TTL_S:
            g["why"] = "expired"                               # never read before its time ran out
            from nucleo import circuit as _circuit
            _circuit.settle(g, verdict="unverifiable", now=now)
            _emit("🕰 arnés: objetivo caducado sin verificar", g)


def note_goal(kind: str, target: str, text: str, *, trace: str = "", now: float | None = None) -> dict:
    """A turn implied an end state: remember it. Same open (kind, target) → refreshed, never duplicated."""
    now = time.time() if now is None else now
    _expire(now)
    target = (target or "").strip().lower()
    for g in open_goals(now):
        if g.get("kind") == kind and g.get("target") == target:
            g["text"] = (text or g.get("text") or "")[:300]
            g["born"] = now
            return g
    g = _ledger().open({"widget": target, "field": "empty", "is": "false"}, text=text or "", source=SOURCE,
                       widget=target, action="show", trace=trace or "", now=now) or {}
    g.update({"kind": kind, "target": target, "text": (text or "")[:300], "met_at": 0.0, "checks": 0})
    _emit("🎯 arnés: objetivo abierto", g)
    return g


def open_goals(now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    _expire(now)
    return [g for g in _ledger().open_specs(now) if g.get("source") == SOURCE]


def reset() -> None:
    led = _ledger()
    led._OPEN[:] = [e for e in led._OPEN if e.get("source") != SOURCE]


# ── the verifiers (the RESOURCE half: read the product's own truth, never a copy of it) ─────────────────
async def verify(goal: dict) -> bool | None:
    """True = met · False = unmet · None = this goal's truth cannot be read (the harness stays silent).

    The verdict is REMEMBERED on the goal (`last`) because the prompt cannot await one: see `prompt_lines`.
    """
    from nucleo.circuit import verify as _verify
    goal["checks"] = int(goal.get("checks") or 0) + 1
    out: bool | None = None
    if goal["kind"] == KIND_WIDGET_CONTENT:
        view = _verify.card_view(goal["target"])
        if not view or "empty" not in view or str(view.get("error") or "").strip():
            out = None                       # a widget that does not declare emptiness is unverifiable
            if goal.get("last_seen") != "unreadable":
                _emit("🫥 arnés: objetivo NO verificable — la tarjeta no declara si está vacía", goal)
        elif view.get("empty"):
            out = False
            goal["why"] = "empty"
        else:
            opened = _verify.card_on_screen(goal["target"])
            out = True if opened is None else bool(opened)
            goal["why"] = "" if out else "off_screen"
    goal["last"] = out
    goal["last_seen"] = {True: "met", False: "unmet"}.get(out, "unreadable")
    return out


async def sweep(now: float | None = None) -> list[dict]:
    """Heartbeat: re-verify open goals; a met one closes with an event. Returns the goals closed now."""
    now = time.time() if now is None else now
    closed: list[dict] = []
    for g in open_goals(now):
        try:
            ok = await verify(g)
        except Exception:
            ok = None
        if ok:
            from nucleo import circuit as _circuit
            _circuit.settle(g, verdict="met", now=now)
            _emit("✅ arnés: objetivo conseguido", g)
            closed.append(g)
    return closed


def prompt_lines(now: float | None = None) -> list[str]:
    """The open goals as the live state sees them — a FACT with its RULE (V2-453), zero lines when empty.

    V2-755 — and only the goals a VERIFIER actually found unmet. This function used to print every open
    goal as «la hoja sigue VACÍA», which is the one thing this module's own rule forbids: «a widget whose
    truth cannot be read yields None (unverifiable) and the harness stays silent about it — a wrong "you
    did not deliver" over a delivered card is worse than none». `verify` honoured it; the prompt did not,
    and the prompt is the half the model reads.

    Measured live (session 665e666a, 2026-09-23): `youtube.view_data()` declared no `empty` key, so the
    goal born at «Vale, muéstrame el widget de vídeo» was UNVERIFIABLE — it could never be met, never
    closed, and for three minutes every single turn carried «la hoja `youtube` sigue VACÍA. No digas que
    está hecho ni "aquí lo tienes"» over a card holding six numbered results and a playing video.

    Sync on purpose (the prompt is built synchronously), so it reads the verdict `verify` left behind on
    the goal rather than taking one of its own: unverified means silent, which is the honest default.
    """
    out: list[str] = []
    for g in open_goals(now):
        if g["kind"] == KIND_WIDGET_CONTENT and g.get("last") is False:
            out.append(f"OBJETIVO ABIERTO (arnés): «{g['text'][:120]}» → la hoja `{g['target']}` sigue VACÍA. "
                       "No digas que está hecho ni «aquí lo tienes» hasta que el contenido esté cargado: "
                       "entrégalo con widget_data show/append, o escala con superficie documento.")
    return out


def _emit(label: str, g: dict, extra: dict | None = None) -> None:
    try:
        from voice.observer import emit
        emit("brain", label, text=g.get("text", "")[:120], role="system",
             extra={"goal": g.get("id"), "goal_kind": g.get("kind"), "target": g.get("target"),
                    "status": g.get("status"), **({"trace": g["trace"]} if g.get("trace") else {}),
                    **(extra or {})})
    except Exception:
        pass
