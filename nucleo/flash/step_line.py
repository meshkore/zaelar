"""nucleo/flash/step_line.py — a wait reply while an errand runs names the errand's REAL current step.

Measured on `show-real-photo-of-a-new-car__us` (sandbox 20261011-115914-en): four «let me know» turns in a row
while the worker went through ferrari.com, and the replies were «Still nothing back yet», «Will do», «Sounds
good» — with «entrando en media.ferrari.com…» and the worker's own note («Ferrari product page is JS-rendered —
probing the browser route») in that turn's live state. The prompt asks for the step; the model says it one turn
in three. Same reading as the stall backstop (V2-359): when the right conduct is deterministic — a step exists,
he asked to be told — code guarantees it, not the temperature.

Gate: the brief's sure verdict that he wants to be TOLD (`wants_words=tell`), exactly one live errand (several
are the status line's job, `errands_of_a_turn.status_owed`), and a concrete step this errand has not been heard
saying yet. Nothing is appended when the reply already names it. The step is said in HIS language: the worker's
own note when it is in that language, else the engine's phase (which is written in Spanish) translated from our
OWN phase vocabulary (`workers/progress.py`, never his words), else the plan step the worker is on.
"""
from __future__ import annotations

import re

#: errand id → steps already appended for it. A step is said once; the next wait says the next one or nothing.
_SAID: dict[str, set] = {}

#: Our OWN phase vocabulary (`workers/progress._SAY`) → English. Longest prefix first; the rest of the phase
#: (a host, a quoted query) is kept as it is.
_PHASE_EN = (
    ("recogiendo lo que hay en la página", "collecting what's on the page"),
    ("conduciendo el navegador", "driving the browser"),
    ("recorriendo la página", "scrolling through the page"),
    ("pulsando en la página", "clicking on the page"),
    ("escribiendo en la página", "typing on the page"),
    ("abriendo una página", "opening a page"),
    ("leyendo la página", "reading the page"),
    ("mirando la página", "looking at the page"),
    ("buscando en la web", "searching the web"),
    ("entrando en", "going into"),
    ("leyendo", "reading"),
    ("buscando", "searching for"),
    ("pulsando", "clicking"),
)
#: Phases that say no step at all (queued, starting, thinking) or quote one of our card ids.
_EMPTY_PHASE_RE = re.compile(r"^(arrancando|en cola|pensando|ejecutando un paso|trabajando)\b|«(results|documento|"
                             r"navegador|widget)(::[^»]*)?»", re.I)
_HOST_RE = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)+\b", re.I)


def _clean(text: str) -> str:
    return " ".join(str(text or "").split()).strip().rstrip("…. ")


def _in_language(text: str, code: str) -> bool:
    from nucleo.flash import outgoing_lang as _ol
    lang = _ol.language_of(text)
    if code in ("es", "en"):
        return lang != ("en" if code == "es" else "es")
    return lang == code


def _phase_for(phase: str, code: str) -> str:
    p = _clean(phase)
    if not p or _EMPTY_PHASE_RE.search(p):
        return ""
    if code == "es":
        return p
    if code != "en":
        return ""
    low = p.lower()
    for es, en in _PHASE_EN:
        if low.startswith(es):
            return (en + p[len(es):]).strip()
    return ""


def candidates(errand: dict, code: str) -> list[str]:
    """The steps this errand can be said to be on, best first, already in the session's language."""
    out = []
    note = _clean(errand.get("note"))
    if note and _in_language(note, code):
        out.append(note)
    phase = _phase_for(str(errand.get("phase") or ""), code)
    if phase:
        out.append(phase)
    plan, done = list(errand.get("plan") or []), int(errand.get("done") or 0)
    if 0 <= done < len(plan) and _in_language(str(plan[done]), code):
        out.append(_clean(plan[done]))
    return [s for i, s in enumerate(out) if s and s not in out[:i]]


def _names_it(reply: str, step: str) -> bool:
    r = str(reply or "").lower()
    if any(h.lower() in r for h in _HOST_RE.findall(step)):
        return True
    words = {w for w in re.findall(r"[a-záéíóúñü]{5,}", step.lower())}
    return len(words) > 0 and sum(w in r for w in words) >= min(3, len(words))


def _live_errand() -> dict | None:
    from nucleo import dispatch as _d
    live = [e for e in (_d.pending_summaries() or []) if not e.get("waiting_on") and not e.get("paused")]
    return live[0] if len(live) == 1 else None


def owed(reply: str, brief) -> str:
    """The sentence to append to `reply`, or "". Never raises."""
    try:
        from nucleo.flash import turn_brief as _tb
        if brief is None or not str(reply or "").strip():
            return ""
        words, info = _tb.read(brief, _tb.WORDS_KEY, "")
        if info is None or words != "tell":
            return ""
        errand = _live_errand()
        if not errand:
            return ""
        from i18n import langs as _lg
        code = str(_lg.current_code() or "es")[:2]
        said = _SAID.setdefault(str(errand.get("uid") or errand.get("id") or ""), set())
        fresh = [s for s in candidates(errand, code) if s not in said]
        if not fresh or any(_names_it(reply, s) for s in candidates(errand, code)):
            return ""
        from nucleo.turn import named_errand as _ne
        said.add(fresh[0])
        name = _ne.spoken_name({"title": errand.get("title"), "label": "", "request": errand.get("goal")})
        return _lg.current_language().errand_step_now.format(name=name, step=fresh[0])
    except Exception:  # noqa: BLE001 — a status sentence never costs the reply
        return ""


def forget() -> None:
    _SAID.clear()
