"""nucleo/flash/answer_guards.py — a FACT about the world, answered with NO source (V2-210).

Extracted from `router_guards.py` on 2026-09-03 paying the architecture ratchet (V2-567's show-vs-close guard
crossed that file's ceiling; the table calls for extracting a concern, not raising a number — this family is
pure regex over (question, answer) pairs and nothing that stayed behind uses it). `router_guards` keeps
ALIASES with the historical names, so `probe.py` and the flash tests import through it unchanged.
"""
from __future__ import annotations

import re as _re

# ── A FACT ABOUT THE WORLD, ANSWERED WITH NO SOURCE (V2-210) ──────────────────────────────────────────────────
# Measured on `quick-fact-opening-hours` (2026-08-20 15:08), the cleanest failure on the board because there is
# nothing else in it — no wall, no worker, no network error:
#
#     TESTER  ¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?
#     ZAELAR  Mañana abre a las 10:00 y la entrada general cuesta 15 €.
#
# Zero tools. Families: flash, memory, system — no `search`. The numbers are roughly right, which is WHY this is
# dangerous: the model is confident, so it never reaches for `web_search`, and a confident wrong price reads
# exactly like a confident right one. V2-022's whole point is that this class of question is answered IN THE
# TURN from a real source; V2-135 already fixed the composing half of this same case. What was missing is the
# trigger for the turn where the model does not ask.
#
# NARROW ON PURPOSE, and both halves are required:
#   · the QUESTION has to be about the opening hours / price / address / phone of something out there, and not
#     about the operator's own things («¿a qué hora es mi cita?» is the agenda, and answering it from memory is
#     correct);
#   · the ANSWER has to state a concrete FIGURE. «Suele abrir por la mañana» claims nothing checkable and
#     forcing a search on it would spend a second on every vague sentence.
# A false «go and search» costs latency on every turn it fires on, so the cost of being wide is paid by turns
# that were fine. A false negative costs one invented fact, which is the failure being fixed — hence a rule that
# fires on the shape actually measured and says so.
_EXTERNAL_FACT_RE = _re.compile(
    r"\b(a\s+qu[eé]\s+hora\s+(abre|abren|cierra|cierran|empieza|empiezan)|"
    r"abre[nu]?\b|abierto\b|cierra[nu]?\b|horario\b|horarios\b|"
    r"cu[aá]nto\s+(cuesta|vale|valen|cuestan)|precio\b|tarifa\b|entrada\s+general\b|"
    r"direcci[oó]n\b|tel[eé]fono\b|"
    r"what\s+time\s+(does|do)\b|opening\s+hours\b|how\s+much\s+(is|are|does)\b)", _re.I)

# The operator's OWN things: their agenda, their car, their subscription. Those are answered from memory or from
# their account, never from a search engine, and «mi» is what marks them.
_OWN_THING_RE = _re.compile(r"\b(mi|mis|m[ií]o|m[ií]a|nuestr[oa]s?)\b", _re.I)

# A checkable figure: a time, an amount, a price. Bare digits are NOT enough — «te lo digo en 2 minutos» is not
# a claim about the world.
_FIGURE_RE = _re.compile(
    r"(\b\d{1,2}[:.]\d{2}\b|\b\d{1,2}\s*h\b|\b\d{1,4}([.,]\d{1,2})?\s*(€|euros?|dollars?|usd|\$)|"
    r"(€|\$)\s*\d|\b\d{1,2}\s*(de\s+la\s+ma[ñn]ana|de\s+la\s+tarde|am|pm)\b)", _re.I)


def answer_needs_a_source(operator_text: str, reply: str) -> bool:
    """Did this turn state a checkable fact about the world without consulting anything?

    Only the caller knows whether a tool ran, so this answers the OTHER half: whether the pair
    (question, answer) is the shape that must never be improvised.
    """
    q, a = (operator_text or ""), (reply or "")
    if not q or not a:
        return False
    if _OWN_THING_RE.search(q):
        return False
    return bool(_EXTERNAL_FACT_RE.search(q) and _FIGURE_RE.search(a))


# ── A QUESTION IS NOT ANSWERED WITH A BARE ACK (V2-572) ──────────────────────────────────────────────────────
# Measured twice in ONE live session (2026-09-03, operator's engine):
#
#     OPERATOR  ¿Tenemos alguna reserva en la agenda a algún restaurante?
#     ZAELAR    Hecho.                          (and it closed a widget nobody asked about)
#     OPERATOR  Te he hecho una pregunta.
#
#     OPERATOR  Dime si has hecho alguna reserva efectiva. Para comer en un restaurante, en la agenda.
#     ZAELAR    Hecho.
#     OPERATOR  Respóndeme a la pregunta.
#
# Both recoveries were the operator doing BY HAND what this guard automates: forcing the model to actually
# answer. NARROW like its sibling above, and both halves are required:
#   · the question has to be INFORMATION-seeking («¿tenemos…?», «dime si…», «¿hay…?») and carry no action
#     verb — «¿puedes cerrar los mensajes?» is a polite order, and «Hecho.» is its correct answer;
#   · the reply has to be a bare acknowledgement and nothing else. «Hecho, no tienes reservas» answers.
_INFO_QUESTION_RE = _re.compile(
    r"(\?|¿|\b(?:dime|di\s+si|cu[eé]ntame|resp[oó]ndeme|expl[ií]came|"
    r"tell\s+me|say\s+if|let\s+me\s+know)\b)", _re.I)
_ACTION_VERB_ANYWHERE_RE = _re.compile(
    r"\b(cierra\w*|cerrar\w*|abre\w*|abrir\w*|quita\w*|quitar\w*|muestra\w*|mostrar\w*|ensename?\w*|"
    r"ensenar\w*|pon\w*|poner\w*|apaga\w*|apagar\w*|enciende\w*|encender\w*|borra\w*|borrar\w*|"
    r"guarda\w*|guardar\w*|manda\w*|mandar\w*|envia\w*|enviar\w*|limpia\w*|limpiar\w*|"
    r"close|open|show|hide|dismiss|play|stop|send|save|delete|clear|turn)\b", _re.I)
# V2-603: `show_ack` («Aquí lo tienes.») belongs here too. It is OUR canned line for a `show_widget` turn the
# model left mute, and it is content-free in exactly the same way `data_ack` is — but it was never seeded, so
# an information question answered with it sailed past this guard. Measured live on the operator's engine
# (2026-09-06): «¿ya has cogido los datos de mi cuenta de YouTube?» → «Aquí lo tienes.», over a connector with
# no OAuth app at all. Non-deterministic, which is why it survived: the same question answers correctly
# whenever the model happens to speak, and falls back to this line whenever it does not.
_BARE_ACK_RE = _re.compile(
    r"^\s*(?:vale|ok|okay|claro|hecho|listo|ya\s+esta|de\s+acuerdo|perfecto|entendido|"
    r"done|all\s+set|sure|got\s+it|aqui\s+lo\s+tienes|aqui\s+tienes|here\s+you\s+go|here\s+it\s+is)"
    r"(?:\s*[,.]?\s*(?:vale|ok|okay|hecho|listo|ya\s+esta|done))?\s*[.!]*\s*$", _re.I)


def _fold(text: str) -> str:
    import unicodedata as _ud
    t = _ud.normalize("NFKD", text or "")
    return "".join(c for c in t if not _ud.combining(c))


def a_bare_ack_answers_a_question(operator_text: str, reply: str) -> bool:
    """Did an information-seeking question get a content-free «Hecho.»? Only the caller knows how to repair it
    (the voice channel speaks a follow-up, the probe re-composes); this answers the shape."""
    q, a = _fold(operator_text), _fold(reply).strip()
    if not q or not a:
        return False
    if not _INFO_QUESTION_RE.search(q) or _ACTION_VERB_ANYWHERE_RE.search(q):
        return False
    return bool(_BARE_ACK_RE.match(a))


# ── A QUESTION IS NOT ANSWERED WITH AN EMPTY WAIT (V2-587) ───────────────────────────────────────────────────
# The bare-ack guard's blind sibling, measured in session 0e3a42d6 (2026-09-05):
#
#     OPERATOR  ¿Cuántos correos hay en mi bandeja?
#     ZAELAR    Sigo con ello; te aviso en cuanto lo tenga.     (ZERO tools, ZERO tasks — nothing was running)
#     …three minutes and two reminders later, a whisper repair finally spawned a worker; the session ended
#     before any answer arrived.
#
# «Sigo con ello» is HONEST when something is actually running for it — which is why this guard takes the two
# facts only the caller has: did THIS turn act, and is ANYTHING alive. Both false + an information question +
# a wait-shaped reply with no content = a promise about work that does not exist. NARROW like its siblings:
# a reply carrying a «?» is a clarifying question (legitimate), and anything past one short breath of text is
# assumed to carry content.
_EMPTY_WAIT_RE = _re.compile(
    r"^\s*(?:vale|ok|okay|claro)?[,.\s]*"
    r"(?:sigo\s+(?:con\s+ello|en\s+ello|con\s+eso)|estoy\s+en\s+ello|me\s+pongo\s+con\s+ello|"
    r"dame\s+un\s+momento|un\s+momento|te\s+aviso|te\s+lo\s+digo\s+en\s+cuanto|en\s+cuanto\s+lo\s+tenga|"
    r"working\s+on\s+it|i'?ll\s+let\s+you\s+know|give\s+me\s+a\s+(?:moment|sec))\b", _re.I)


def an_empty_wait_answers_a_question(operator_text: str, reply: str, *,
                                     acted: bool, anything_running: bool) -> bool:
    """Did an information-seeking question get a «sigo con ello» with NO work behind it? The caller passes the
    two liveness facts; when either is true the wait may be honest and this stays out. Fail-safe direction:
    a caller that cannot read liveness must pass anything_running=True (skipping a repair costs nothing new;
    repairing over a genuinely running task contradicts the state)."""
    if acted or anything_running:
        return False
    q, a = _fold(operator_text), _fold(reply).strip()
    if not q or not a:
        return False
    if not _INFO_QUESTION_RE.search(q) or _ACTION_VERB_ANYWHERE_RE.search(q):
        return False
    if "?" in a or len(a) > 140:
        return False
    return bool(_EMPTY_WAIT_RE.match(a))


# ── A CONTINUITY CLAIM OVER NOTHING (V2-645) ────────────────────────────────────────────────────────────────
# Measured live (the La Mella session, 2026-09-09, turn T15): «¿Sigues con esa tarea del WhatsApp o la has
# perdido cuando te he parado?» → «Sigo con ella, no la he perdido. Estoy revisando ese grupo…» — with ZERO
# live sessions (both escalations sat dead: one parked at the confirm gate, one discarded) and the prompt's
# own state line saying «la tarea está PARADA — no digas que está en marcha». The V2-587 guard could not see
# it three ways: «sigo con ELLA» is not in its wait regex, «te he PARADO» trips its action-verb bail, and a
# reply that NAMES what it is supposedly doing reads as content. This guard takes the specific shape whole:
# a question ABOUT task continuity + a reply CLAIMING continuity + nothing alive = a lie about the state,
# and the state is ours to say.
_CONTINUITY_Q_RE = _re.compile(
    r"\bsigues\s+(?:con|en)\b|\bcomo\s+va\s+(?:la\s+tarea|eso|la\s+busqueda|lo\s+(?:de|del))\b|"
    r"\b(?:la|lo)\s+has\s+perdido\b|\bstill\s+(?:working\s+on|on)\b|\bhow\s+is\s+(?:it|the\s+task)\s+going\b",
    _re.I)
_CONTINUITY_CLAIM_RE = _re.compile(
    r"\bsigo\s+(?:con|en)\b|\bestoy\s+(?:revisando|buscando|mirando|en\s+ello|con\s+ello)\b|"
    r"\bno\s+l[ao]\s+he\s+perdido\b|\bstill\s+(?:working\s+on|on)\s+it\b|\bworking\s+on\s+it\b", _re.I)


def a_continuity_claim_over_nothing(operator_text: str, reply: str, *,
                                    acted: bool, anything_running: bool) -> bool:
    """Did «are you still on that task?» get «yes, on it» while NOTHING runs? Same liveness contract as
    V2-587: a caller that cannot read liveness passes anything_running=True and this stays out. No length
    cap and no action-verb bail on purpose — the measured lie was long, specific, and the question carried
    «parado» (the operator naming his own power press, not ordering an action)."""
    if acted or anything_running:
        return False
    q, a = _fold(operator_text), _fold(reply).strip()
    if not q or not a or "?" in a:
        return False               # a clarifying counter-question is legitimate
    return bool(_CONTINUITY_Q_RE.search(q) and _CONTINUITY_CLAIM_RE.search(a))


def a_cover_left_hanging(operator_text: str, reply: str, *, covered: bool, acted: bool) -> bool:
    """Did the turn end MUTE — zero spoken characters — after a wait-cover already sounded, or over an
    information question? Session 651c25ac (2026-09-09 20:51): «¿Por qué la vista semanal no tiene una
    columna para cada día?» → «Déjame que mire…» → the model spent its 84 tokens re-emitting a stale data-op
    (rightly ignored by the context-bleed guard) → completion_chars=0 → silence forever. A cover is a spoken
    PROMISE that words are coming; a mute completion breaks it. The operator's rule: «igual no tenía
    respuesta, pero igualmente hay que cerrar las conversaciones».

    `covered` = a lead-in actually sounded for THIS turn; `acted` = the turn executed something visible.
    A mute turn with no cover and no question stays legitimate silence (V2-633: for a short order the pause
    IS the answer)."""
    if acted or (reply or "").strip():
        return False
    q = _fold(operator_text)
    if not q:
        return False
    if covered:
        return True
    return bool(_INFO_QUESTION_RE.search(q) and not _ACTION_VERB_ANYWHERE_RE.search(q))
