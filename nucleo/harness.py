"""nucleo/harness.py — the ERRAND HARNESS: what END STATE a turn implied, verified against the REAL state.

V2-659 (operator directive, 2026-09-11): «cuando obtiene permiso para realizar una acción falta terminar
de cerrar el círculo … un arnés dinámico que comprueba que lo pedido se ha conseguido — el documento
correcto, en el idioma pedido, el visor abierto y el documento cargado — y solo entonces se informa al
usuario». Measured the same night (session 0141a72a): after his «Adelante», the model said «Claro, aquí
tienes el texto completo de la Declaración…» having run ONE web_search — the `documento` card was open
and EMPTY, and nothing in the engine compared the claim with the screen until he complained.

WHAT THIS IS. A small ledger of GOALS — (kind, target, the operator's words) — born when a turn implies
an end state, verified by a closed set of VERIFIERS that read the product's own truth (the widget's
`view_data()`, the open-cards state), and consulted at three seams:
  · turn end (both channels): a reply that CLAIMS delivery («aquí lo tienes», «ya está en pantalla»)
    over an UNMET goal is a false claim — the turn adds the honest follow-up and hands the errand to the
    machinery that can deliver it (escalation with the doc surface), instead of letting the sentence stand;
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

_GOALS: list[dict] = []
TTL_S = 300.0          # an errand nobody could deliver in five minutes is history, not a live goal
_MAX = 8

KIND_WIDGET_CONTENT = "widget_content"


def _norm(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


# The COMPLETION CLAIM. Deliberately not `promise_backstop.committed` (a promise is about the future and
# has its own backstop): this is a sentence that says the thing is ALREADY in front of him. Negation is
# honoured through the shared clause arithmetic («todavía NO lo tienes en pantalla» is honest).
_CLAIM_RE = re.compile(
    r"\b(aqui (?:lo |la |las |los )?(?:tienes|esta|estan)|ahi (?:lo |la )?tienes|ya (?:lo |la )?tienes"
    r"(?: en pantalla| delante| cargad[oa])?|te (?:lo|la) he (?:puesto|cargado|mostrado)|ya esta (?:en pantalla|"
    r"cargad[oa]|abiert[oa]|listo|lista)|(?:lo|la) tienes (?:ya )?en (?:la pantalla|pantalla|el documento|la hoja)|"
    r"here (?:it is|you go)|there (?:it is|you go)|it'?s (?:on (?:the|your) screen|loaded))\b")


def claims_done(reply: str) -> bool:
    """Does the reply ASSERT that the deliverable is already in front of the operator?"""
    try:
        from nucleo.flash.negation import unnegated_match
        return unnegated_match(_CLAIM_RE, _norm(reply))
    except Exception:
        return bool(_CLAIM_RE.search(_norm(reply)))


# ── the ledger ──────────────────────────────────────────────────────────────────────────────────────────
def _sweep_expired(now: float) -> None:
    for g in _GOALS:
        if g["status"] == "open" and now - g["born"] > TTL_S:
            g["status"] = "expired"
            _emit("🕰 arnés: objetivo caducado sin verificar", g)
    del _GOALS[:-_MAX]


def note_goal(kind: str, target: str, text: str, *, trace: str = "", now: float | None = None) -> dict:
    """A turn implied an end state: remember it. Same open (kind, target) → refreshed, never duplicated."""
    now = time.time() if now is None else now
    _sweep_expired(now)
    target = (target or "").strip().lower()
    for g in _GOALS:
        if g["status"] == "open" and g["kind"] == kind and g["target"] == target:
            g["text"] = (text or g["text"])[:300]
            g["born"] = now
            return g
    g = {"id": f"g{int(now * 1000) % 10_000_000}", "kind": kind, "target": target, "text": (text or "")[:300],
         "born": now, "trace": trace or "", "status": "open", "met_at": 0.0, "checks": 0}
    _GOALS.append(g)
    _emit("🎯 arnés: objetivo abierto", g)
    return g


def open_goals(now: float | None = None) -> list[dict]:
    _sweep_expired(time.time() if now is None else now)
    return [g for g in _GOALS if g["status"] == "open"]


def reset() -> None:
    _GOALS.clear()


# ── the verifiers (the RESOURCE half: read the product's own truth, never a copy of it) ─────────────────
async def _widget_view(wid: str) -> dict | None:
    try:
        from widgets.server_api import run_widget_hook, MISSING

        def call(view_data):
            try:
                return view_data(q="")
            except TypeError:
                return view_data()
        res = await run_widget_hook(wid, "view_data", call)
        return res if isinstance(res, dict) and res is not MISSING else None
    except Exception as e:  # noqa: BLE001
        logger.debug(f"harness: view of {wid} unreadable: {e}")
        return None


def _card_is_open(wid: str) -> bool | None:
    try:
        from memory import api as memory
        opened = {str(w).strip().lower() for w in (memory.state().get("open_widgets") or [])}
        return wid in opened
    except Exception:
        return None


async def verify(goal: dict) -> bool | None:
    """True = met · False = unmet · None = this goal's truth cannot be read (the harness stays silent)."""
    goal["checks"] = int(goal.get("checks") or 0) + 1
    if goal["kind"] == KIND_WIDGET_CONTENT:
        view = await _widget_view(goal["target"])
        if not view or "empty" not in view or "error" in view:
            return None                      # a widget that does not declare emptiness is unverifiable
        if view.get("empty"):
            return False
        opened = _card_is_open(goal["target"])
        return True if opened is None else bool(opened)
    return None


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
            g["status"], g["met_at"] = "met", now
            _emit("✅ arnés: objetivo conseguido", g)
            closed.append(g)
    return closed


# ── the turn-end decision, shared by the voice provider and the probe ───────────────────────────────────
async def false_claim(spoken: str, *, data_done: bool) -> dict | None:
    """The reply CLAIMS delivery, the turn fired no data-op of its own, and an open content goal is UNMET →
    the goal (the caller repairs). `data_done` guards the one honest race: a data-op this same turn is
    fire-and-forget (V2-603), so the store may not have caught up yet — trust it, never contradict it."""
    if data_done or not spoken or not claims_done(spoken):
        return None
    for g in open_goals():
        if g["kind"] != KIND_WIDGET_CONTENT:
            continue
        ok = await verify(g)
        if ok is False:
            _emit("⚠️ arnés: afirmó entrega y la hoja sigue VACÍA", g, extra={"claim": spoken[:160]})
            return g
    return None


def rescue_request(goal: dict) -> str:
    """The escalation text for an unmet content goal: the operator's own words plus where it must land."""
    return (goal["text"] + " — [el turno afirmó haberlo entregado y la hoja `" + goal["target"]
            + "` sigue VACÍA: localiza el contenido correcto, en el idioma pedido, y entrégalo al widget "
            + goal["target"] + " con `show`/`append` por secciones.]")


def prompt_lines(now: float | None = None) -> list[str]:
    """The open goals as the live state sees them — a FACT with its RULE (V2-453), zero lines when empty."""
    out: list[str] = []
    for g in open_goals(now):
        if g["kind"] == KIND_WIDGET_CONTENT:
            out.append(f"OBJETIVO ABIERTO (arnés): «{g['text'][:120]}» → la hoja `{g['target']}` sigue VACÍA. "
                       "No digas que está hecho ni «aquí lo tienes» hasta que el contenido esté cargado: "
                       "entrégalo con widget_data show/append, o escala con superficie documento.")
    return out


def _emit(label: str, g: dict, extra: dict | None = None) -> None:
    try:
        from voice.observer import emit
        emit("brain", label, text=g.get("text", "")[:120], role="system",
             extra={"goal": g.get("id"), "kind": g.get("kind"), "target": g.get("target"),
                    "status": g.get("status"), **({"trace": g["trace"]} if g.get("trace") else {}),
                    **(extra or {})})
    except Exception:
        pass
