"""nucleo/harness.py — the ERRAND HARNESS: what END STATE a turn implied, verified against the REAL state.

V2-660 (operator directive, 2026-09-11): «cuando obtiene permiso para realizar una acción falta terminar
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

TTL_S = 300.0          # an errand nobody could deliver in five minutes is history, not a live goal

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
#: V2-776 M4 — the goals are no longer a registry of this module: they are entries of the ONE spec ledger
#: (`nucleo/spec.py`), marked `source="shown"`. What stays here is what makes them different from an action's
#: end state — they are verified by this module's readers, they speak only when a reply CLAIMS delivery, and they
#: expire at `TTL_S` — so `circuit.tick` leaves them alone (`SOURCE`).
SOURCE = "shown"


def _ledger():
    from nucleo import spec as _spec
    return _spec


def _expire(now: float) -> None:
    for g in _ledger().open_specs(now):
        if g.get("source") == SOURCE and now - float(g.get("born") or now) > TTL_S:
            g["status"] = "expired"
            g["met_at"] = now
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
async def _widget_view(wid: str) -> dict | None:
    """V2-776 L2 — the one reader (`nucleo/truth.py`): the instance rides as `q`, and an `error` VALUE is what
    makes a view unreadable — not the key (four seeds always carry `error: ""`)."""
    try:
        from nucleo import truth as _truth
        return _truth.widget_view(wid)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"harness: view of {wid} unreadable: {e}")
        return None


def _card_is_open(wid: str) -> bool | None:
    """On screen = open minus minimized (pass 59, S1: a docked sheet counted as open)."""
    try:
        from nucleo import truth as _truth
        state = _truth.canvas_state(wid)
        return None if state is None else state in ("visible", "maximized")
    except Exception:
        return None


async def verify(goal: dict) -> bool | None:
    """True = met · False = unmet · None = this goal's truth cannot be read (the harness stays silent).

    The verdict is REMEMBERED on the goal (`last`) because the prompt cannot await one: see `prompt_lines`.
    """
    goal["checks"] = int(goal.get("checks") or 0) + 1
    out: bool | None = None
    if goal["kind"] == KIND_WIDGET_CONTENT:
        view = await _widget_view(goal["target"])
        if not view or "empty" not in view or str(view.get("error") or "").strip():
            out = None                       # a widget that does not declare emptiness is unverifiable
            if goal.get("last_seen") != "unreadable":
                _emit("🫥 arnés: objetivo NO verificable — la tarjeta no declara si está vacía", goal)
        elif view.get("empty"):
            out = False
            goal["why"] = "empty"
        else:
            opened = _card_is_open(goal["target"])
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
        # Demo pass 65, S1: «so how did the monitors go, show me» brought the sheet back from the dock with its three
        # monitors, and the canvas report still listed it as minimized a moment later — «not on screen» read as
        # «not delivered», and a worker was sent to «locate the content» of a full sheet. A worker cannot fix a card
        # that is off screen; only an EMPTY sheet is a false claim of delivery.
        if ok is False and g.get("why") == "empty":
            _emit("⚠️ arnés: afirmó entrega y la hoja sigue VACÍA", g, extra={"claim": spoken[:160]})
            return g
        if ok is False and g.get("why") == "off_screen":
            # Demo pass 67, S1: «Three monitors on your screen…» with the sheet still in the dock and no show this
            # turn. The words already said it is in front of him; the card goes there through the one door.
            try:
                from nucleo.flash import canvas_visibility as _cv
                if _cv.present(str(g.get("target") or ""), reason="turn-order", src="harness"):
                    _emit("🪟 arnés: afirmó que estaba en pantalla y seguía en el dock — la presento", g,
                          extra={"claim": spoken[:160]})
            except Exception as e:  # noqa: BLE001
                logger.debug(f"harness: could not present {g.get('target')}: {e}")
    return None


def rescue_request(goal: dict) -> str:
    """The escalation text for an unmet content goal: the operator's own words plus where it must land."""
    return (goal["text"] + " — [el turno afirmó haberlo entregado y la hoja `" + goal["target"]
            + "` sigue VACÍA: localiza el contenido correcto, en el idioma pedido, y entrégalo al widget "
            + goal["target"] + " con `show`/`append` por secciones.]")


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
             extra={"goal": g.get("id"), "kind": g.get("kind"), "target": g.get("target"),
                    "status": g.get("status"), **({"trace": g["trace"]} if g.get("trace") else {}),
                    **(extra or {})})
    except Exception:
        pass
