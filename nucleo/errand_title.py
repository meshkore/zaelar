"""nucleo/errand_title.py — what an errand is CALLED, which is not the same string as what it was ASKED.

Measured on the operator's own engine (2026-08-31, session `7cab1afd`). Two results sheets side by side, one
per errand, and the titles the operator read on them were:

    «Sanidad con Sanitas en Soria»
    «Me parece bien. Oye, una cosita, estabas buscándome un médico. ¿Eres…»

The second is not a name, it is a slice of the conversation — and it is a slice that ends before the errand is
even mentioned. The same string was ALSO what the voice read out when the worker needed something
(«Oye, el proceso "Me parece bien. Oye, una cosita, estabas" pregunta: …»), so the defect was audible as well
as visible. It made the disambiguation question unanswerable too: with two sheets open, «¿cuál cierro, "Sanidad
con Sanitas en Soria" o "Me parece bien. Oye, una cosita, estabas…"?» names one errand and one pleasantry.

WHY the goal reads like that, and why fixing the goal would be the wrong fix: an errand's GOAL is the
operator's own words on purpose. When the promise backstop escalates (`nucleo/flash/router_guards`), the brief
handed to the worker is the raw turn, because fidelity is what lets the worker do the right thing — the
operator said «invéntate el apellido si te lo piden» and that has to survive verbatim. So the goal stays a
BRIEF, and the NAME becomes its own field.

TWO answers, in this order, because the first one has to exist before the second can arrive:

  · `provisional()` — instant and deterministic. The goal, trimmed at a WORD boundary. It is what today's code
    already did (`goal[:40]`, `_clip`) minus the mid-word cut, so it is never worse than the status quo and it
    needs no provider. Every sheet opens with this.
  · `compose()` — one small model call, off the voice clock and off the worker's critical path, that NAMES the
    errand. The escalation is already asynchronous, the sheet is already on screen, and nothing waits for this:
    if it fails, times out, or answers something unusable, the provisional title stays. Naming a request is
    understanding it — a table of verbs would produce «Me parece» for this exact sentence.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata

logger = logging.getLogger("zaelar.errand_title")

TITLE_MAX = 56          # what fits on the sheet's header and in a spoken «el proceso "…" pregunta»
_TIMEOUT_S = float(os.environ.get("ZAELAR_TITLE_TIMEOUT_S", "12") or 12)

# A model that answers with «Título: Pedir cita» or «"Pedir cita"» has still answered; this is about reading it,
# not about rejecting it. Anything longer than one line is a refusal to be brief and IS rejected below.
_LEAD_RE = re.compile(r"^\s*(t[ií]tulo|title|nombre|name)\s*[:\-–]\s*", re.I)


def enabled() -> bool:
    """`ZAELAR_TITLE_MODEL=off` leaves every sheet on its provisional title — the kill-switch."""
    return str(os.environ.get("ZAELAR_TITLE_MODEL", "on") or "on").strip().lower() not in ("0", "off", "no")


def provisional(goal: str, limit: int = TITLE_MAX) -> str:
    """The instant title: the goal, clipped on a word boundary.

    Deliberately NOT clever. Everything a heuristic could do here — drop the greeting, find the request clause —
    it would do by guessing, and a wrong guess renames the operator's errand to something he never said. The
    only defect it fixes on its own is the mid-word cut, which is the part that makes a truncated goal
    unreadable («Me parece bien. Oye, una cosita, estabas»).
    """
    t = " ".join(str(goal or "").split())
    if len(t) <= limit:
        return t
    cut = t[:limit]
    sp = cut.rfind(" ")
    if sp >= limit // 2:                     # only honour the word boundary when it leaves a real title behind
        cut = cut[:sp]
    return cut.rstrip(" ,.;:—-") + "…"


def clean(raw: str, limit: int = TITLE_MAX) -> str:
    """A model answer → a title, or "" if it is not one.

    Rejecting is the safe direction: the provisional title is already on screen and already truthful, so a
    dubious replacement buys nothing and can lose meaning the operator's own words carried.
    """
    t = " ".join(str(raw or "").split())
    if not t:
        return ""
    t = _LEAD_RE.sub("", t).strip()
    t = t.strip("\"'«»“”‘’ ").rstrip(".;:,")
    if not t or len(t) > limit * 2:           # a paragraph is not a title; keep what we have
        return ""
    return t[:limit].rstrip(" ,.;:—-")


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def names_the_errand(title: str, goal: str) -> bool:
    """Does this name actually name THAT errand?

    Measured against the live model: asked for the `-` sentinel on «mmm, no sé, déjalo» it answered «No encargo»
    — a paraphrase of the instruction, which `clean()` would happily hand over as a sheet title. The guard is
    STRUCTURAL rather than a list of refusal phrases (that list is the treadmill this repo keeps paying, V2-151):
    a name that shares NO content word with the brief is not naming it, whatever it says. Ambiguity costs only
    the provisional title, which is the safe direction.

    Known limit, stated instead of hidden: a language that does not separate words (CJK) never overlaps, so it
    always keeps the provisional. Better than inventing a rule for a case nobody has measured.
    """
    words = {w for w in re.findall(r"\w+", _fold(goal)) if len(w) >= 4}
    if not words:
        return True                      # nothing to check against: do not reject on our own inability
    return any(w in words for w in re.findall(r"\w+", _fold(title)) if len(w) >= 4)


def _spec_for_naming():
    """WHO names it. The voice tier first, and that order is measured, not a preference: on 2026-08-31 the
    reasoning chain's only reachable rung answered nothing in 20 s while the voice tier composed every title in
    ~1.5 s. It is also the right shape for the job — naming is one line, not deliberation, so a non-reasoning
    model is what this wants; the reasoning chain stays as the fallback for a machine wired the other way."""
    from nucleo.flash import provider_chain as _pc
    try:
        tier = _pc.pick(_pc.ROLE_VOICE)
        if tier:
            spec = _pc.spec_for(tier)
            if spec is not None:
                return spec
    except Exception:  # noqa: BLE001
        pass
    from nucleo.research import _spec as _research_spec
    return _research_spec()[0]


def _messages(goal: str) -> list[dict]:
    """One instruction per block, and the fork inside the imperative — two orders in one sentence come out as a
    coin flip (the lesson of V2-226, written into the prompt rules)."""
    return [
        {"role": "system",
         "content": (
             "Nombras encargos. Te dan lo que una persona le pidió a su asistente, tal cual lo dijo, con sus "
             "saludos y sus rodeos, y devuelves el NOMBRE del encargo.\n"
             "Devuelve SOLO el nombre: sin comillas, sin punto final, sin explicar nada.\n"
             f"Como mucho {TITLE_MAX} caracteres, en el idioma en el que está escrito el encargo.\n"
             "Nombra lo que hay que HACER y sobre qué, no lo que la persona dijo: si el encargo va de pedir "
             "cita con un traumatólogo en un centro concreto, el nombre lleva la cita y el centro, no el «oye, "
             "una cosita» con el que empezó.\n"
             "Si de verdad no se ve ningún encargo dentro, devuelve exactamente: -"
         )},
        {"role": "user", "content": (goal or "").strip()[:1200]},
    ]


async def compose(goal: str, *, timeout: float = _TIMEOUT_S) -> str:
    """The composed title, or "" — never raises. "" means «keep the provisional one».

    Uses the same provider CHAIN as the research composer (reasoning tier, off the voice clock), so an
    exhausted primary relays instead of killing the call. Failures are logged, not surfaced: an errand whose
    box is named a little worse is not something to interrupt a person about.
    """
    req = " ".join(str(goal or "").split())
    if not req or not enabled():
        return ""
    try:
        import asyncio

        from nucleo.flash.fast_client import FastClient
        spec = _spec_for_naming()
        if spec is None:
            return ""
        out = await asyncio.wait_for(
            FastClient().complete(_messages(req), spec=spec, max_tokens=120, no_thinking=True),
            timeout=timeout)
    except Exception as e:  # noqa: BLE001
        logger.info(f"errand_title: sin título compuesto ({str(e)[:80]}) — se queda el provisional")
        return ""
    t = clean(out)
    if t == "-" or t.lower() in ("-", "n/a", "ninguno", "none"):
        return ""
    if not names_the_errand(t, req):
        logger.info(f"errand_title: «{t}» no nombra el encargo — se queda el provisional")
        return ""
    return t
