"""nucleo/flash/reminder_fact.py — what a notice SAYS when it was asked for about something still to be looked up.

Measured on `find-a-future-release-and-remind-me` (ES, 2026-10-10 21:20): «¿Te enteras de cuándo se estrena y me
avisas?» → the search found «Dexter: Resurrection T2, 30 oct 2026» → the prose backstop scheduled the notice for
the 30th with the prompt «AVISA al operador, es el recordatorio que te pidió: Oye, me gusta mucho la serie
Dexter… ¿Te enteras de cuándo se estrena». Two defects in one field:

  · the SUBJECT was the operator's first ask (`commitment_from_window`), and that ask was a QUESTION — a lookup,
    not a commitment. Read back on the 30th it asks the agent to find out again; it names neither the show nor
    the date the conversation settled on;
  · it was CUT: `commitment_clause` drops the reminder ask («y me avisas?») and the question lost its tail.

The rule here: a commitment clause that is a lookup is replaced by the FACT the conversation answered it with —
the sentence an assistant turn said that names the very day the notice rings (and shares a word with the ask,
and is not itself a question, a refusal or talk about the reminder). No such sentence → the job carries the
lookup intent EXPLICITLY, as a whole quoted question, in the session language — never a cut sentence.

A clause that is not a lookup («llamar al dentista») passes through untouched.
"""
from __future__ import annotations

import re as _re

from nucleo import scheduler as _sched

from .text_norm import _norm_txt

_BODY_MAX = 240          # `_reminder_prompt` caps the whole prompt at 300; this keeps the cut off the body

# A lookup ask: a find-out verb, or a question that asks WHEN/WHICH DAY. Normalised text (no accents, lower case).
# A bare «¿…?» is not enough: «¿Me apuntas que el jueves renuevo el seguro…?» is a commitment asked politely.
_FIND_OUT_RE = _re.compile(
    r"\b(te\s+enteras|enterate|averigu\w*|investiga\w*|comprueba\s+cuando|mira\s+(?:a\s+ver\s+)?cuando|"
    r"busca(?:me)?\s+cuando|find\s+out|look\s+up|check\s+when)\b", _re.I)
_ASKS_WHEN_RE = _re.compile(r"\b(cuando|que\s+dia|que\s+fecha|a\s+que\s+hora|when|what\s+(?:day|date|time))\b", _re.I)
# A sentence that is not a fact: it refuses, doubts, or talks about the notice itself rather than the event.
_NOT_A_FACT_RE = _re.compile(
    r"\b(no|not|cannot|can'?t|won'?t|todavia|aun|sin\s+confirmar|unconfirmed|yet|"
    r"aviso|avisar\w*|avisare|recordatorio|recordar\w*|recuerdo|alarma|alerta|reminder|remind|heads-up|notify)\b",
    _re.I)
# A sentence ends at . ! ? … before a capital — but not after an initial («Michael C. Hall»).
_SENTENCE_RE = _re.compile(r"(?<=[.!?…])(?<!\b[A-Z]\.)\s+(?=[¡¿«\"(A-ZÁÉÍÓÚÑ0-9])")
_TRAILING_AND_RE = _re.compile(r"(?:^|\s+)(?:y|e|and)\s*$", _re.I)
_INTENT = {
    "es": "comprueba primero lo que te pidió averiguar y díselo: «{q}»",
    "en": "first check what he asked you to find out and tell him: «{q}»",
}


def is_lookup(clause: str) -> bool:
    """Does this clause ASK for something to be found out, rather than state a commitment?"""
    n = _norm_txt(clause or "")
    return bool(_FIND_OUT_RE.search(n) or (_re.search(r"[?¿]", n) and _ASKS_WHEN_RE.search(n)))


def tidy_clause(head: str) -> str:
    """The clause left once the reminder ask is cut off, without its dangling punctuation and conjunction.

    `strip(" ,.;:y")` used to do this and it stripped CHARACTERS: «…a mamá hoy, recuérdamelo» became «…a mamá
    ho», and an English «… premieres and let me know» kept its «and».
    """
    return _TRAILING_AND_RE.sub("", (head or "").rstrip(" ,.;:")).rstrip(" ,.;:").strip()


# Words that only DATE or REQUEST something: two sentences sharing «octubre» or «reminder» share no subject.
_NOT_SUBJECT = frozenset(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre january february "
    "march april june july august september october november december lunes martes miercoles jueves viernes "
    "sabado domingo monday tuesday wednesday thursday friday saturday sunday manana tomorrow today hoy "
    "aviso avisame recordatorio recuerdame reminder remind please porfa favor".split())
# The clause still carries the reminder REQUEST (the cut found no ask to cut at): it says when, not what.
_REQUEST_RE = _re.compile(r"\b(aviso|recordatorio|alarma|alerta|reminder|heads-up|remind|recuerdame|avisame)\b",
                          _re.I)


def _words(text: str) -> set[str]:
    """Subject stems: five letters, so «premiere» meets «premieres» and «estrena» meets «estreno»."""
    return {w[:5] for w in _re.findall(r"[^\W\d_]+", _norm_txt(text)) if len(w) > 3 and w not in _NOT_SUBJECT}


def fact_for(clause: str, window, reply: str, when: str) -> str:
    """The most recent assistant sentence that names `when`'s DAY and answers `clause` — or ""."""
    day = (when or "")[:10]
    if not day:
        return ""
    asked = _words(clause)
    said = [str((m or {}).get("content") or "") for m in (window or []) if (m or {}).get("role") == "assistant"]
    for text in reversed(said + [reply or ""]):
        for s in reversed(_SENTENCE_RE.split(text.strip())):
            s = s.strip()
            if not s or "?" in s or _NOT_A_FACT_RE.search(_norm_txt(s)) or not (_words(s) & asked):
                continue
            if (_sched.parse_when(s) or "")[:10] == day:
                return s
    return ""


def _bounded(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) <= _BODY_MAX:
        return text
    return text[:_BODY_MAX].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"


def _lang() -> str:
    try:
        from i18n import langs as _lg
        return _lg.current_code()
    except Exception:  # noqa: BLE001 — a notice in the wrong language beats a lost notice
        return "es"


def lookup_intent(clause: str, lang: str = "") -> str:
    """The lookup said as a whole instruction: the question quoted, closed if its «¿» lost its «?»."""
    q = tidy_clause(clause)
    if "¿" in q and not q.endswith("?"):
        q += "?"
    tpl = _INTENT.get((lang or _lang())[:2], _INTENT["en"])
    return tpl.format(q=_bounded(q))


def reminder_body(clause: str, window, reply: str, when: str) -> str:
    """What the notice carries: the clause itself, unless it is a lookup (→ its answer, or the lookup said whole)
    or nothing but the reminder request (→ its answer, or the clause as it was)."""
    if not _re.search(r"\w", clause or ""):
        return ""        # nothing but punctuation («¿» left by the cut) → the caller falls back to his whole turn
    if is_lookup(clause):
        fact = fact_for(clause, window, reply, when)
        return _bounded(fact) if fact else lookup_intent(clause)
    if _REQUEST_RE.search(_norm_txt(clause)):
        fact = fact_for(clause, window, reply, when)
        return _bounded(fact) if fact else clause
    return clause
