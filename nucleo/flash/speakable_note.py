"""nucleo/flash/speakable_note.py — what a worker's note must be before a sentence of ours says it to him.

Two composers read the same note and filtered it differently. The step line (`step_line.candidates`) dropped a note
in another language or about our plumbing; the status line (`errands_of_a_turn.errand_state`) only checked the
language, and only one way. search-buy-vinyl ES (2026-10-14): «Así va todo: Comprar vinilo The Dark Side of the Moon
— Criterios duros registrados y fuentes abiertas (eBay + Wallapop).» — the worker reporting that it filled in OUR
sheet's hard-criteria column, said to him as where his errand stands. The vocabulary below is the ENGINE's own (the
sheet's columns, our tools, our card ids, `hard_checks.worker_block`), never his: a sentence about it is about us.
"""
from __future__ import annotations

import re

#: Our plumbing: the sheet contract, our tools and clis, our card ids, the hard-criteria column the worker fills.
PLUMBING_RE = re.compile(
    r"\b(contrato de la hoja|sheet contract|herramienta de zaelar|zaelar tool|cli|payload|widget_data|results::|"
    r"cli\.(?:widget|nav|mesh|report|mem|bridge)|criterios duros|requisitos duros|hard (?:criteria|requirements?)|"
    r"criteri(?:a|os) (?:registered|registrados|written|escritos|set|fijados))\b"
    r"|«(?:results|documento|navegador|widget)(?:::[^»]*)?»", re.I)


def plumbing(text: str) -> bool:
    """Does the note talk about our machinery rather than his errand?"""
    return bool(PLUMBING_RE.search(str(text or "")))


def in_language(text: str, code: str, *, strict: bool = False) -> bool:
    """Is the note in his language? In Spanish — the engine's own — it only must not read as English. Elsewhere
    `strict` asks it to READ as his language (the status line: an engine phase «entrando en ebay.es» says nothing an
    English ear should hear); without it, not reading as the other product language is enough (the step line, which
    translates our own phases itself)."""
    from nucleo.flash import outgoing_lang as _ol
    lang = _ol.language_of(text)
    code = str(code or "en")[:2]
    if code == "es":
        return lang != "en"
    if code == "en" and not strict:
        return lang != "es"
    return lang == code


def speakable(text: str, code: str, *, strict: bool = False) -> bool:
    """A note a sentence of ours may say to him: it says something, in his language, about his errand."""
    t = str(text or "").strip()
    return bool(t) and in_language(t, code, strict=strict) and not plumbing(t)
