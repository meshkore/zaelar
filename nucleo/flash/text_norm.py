"""nucleo/flash/text_norm.py — the text normalisation every deterministic guard runs on.

Extracted from `router_guards.py` (2026-09-02, architecture ratchet) because it is the one piece BOTH halves
of that file need: the reminder/agenda guards that moved to `reminder_guards.py` and the routing guards that
stayed. Keeping it in either one would have made the other import it back, which is a cycle papered over with
a function-local import — the exact debt the ratchet counts.

`delivery.py` was already reaching into `router_guards` for `_norm_txt`, which is the smell that says this was
never a router concern to begin with: it is what «the same words» means in this codebase — accents stripped,
lowercased — so that a guard compares meaning and not typography.

Nothing here decides anything. No I/O, no state, no imports beyond the standard library.
"""
import re as _re


def _norm_txt(text: str) -> str:
    import unicodedata as _ud
    n = _ud.normalize("NFKD", text or "")
    return "".join(c for c in n if not _ud.combining(c)).lower()
_STOPWORDS = frozenset({"el", "la", "los", "las", "un", "una", "de", "del", "al", "que", "y", "a", "en",
                        "mi", "tu", "su", "the", "a", "an", "of", "to", "my", "your"})
def _content_words(text: str) -> set[str]:
    return {w for w in _norm_txt(text).split() if len(w) > 2 and w not in _STOPWORDS}
_CLAUSE_SPLIT_RE = _re.compile(r"[,;.!?\n]|\sy\s|\sand\s", _re.I)
# The words that only DATE something and never describe it. Needed to answer one question: does this clause say
# anything BESIDES when?
_DATE_ONLY_WORDS = frozenset({
    "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "manana", "tomorrow", "hoy", "today", "dia", "day", "esta", "este", "proximo", "proxima", "que", "viene",
})
def clause_is_only_a_date(clause: str) -> bool:
    """True when the «commitment» clause says nothing except WHEN — so there is no event for a notice to precede.

    Found while fixing the measured case, one line away from it: «El martes recuérdame lo del seguro» leaves
    `commitment_clause` with just «El martes», because the clause is cut at the ask verb and the date sits before
    it. `reminder_before` then reads that as the event day, sees the notice is not earlier than the event, walks
    back a week into the past and falls through to «fire promptly» — so a reminder asked for Tuesday goes off
    THIS SECOND. `reminder_before` is right about its own rule; what was wrong was being handed a date and told
    it was a commitment.

    A date with nothing around it is not a commitment. When that is what we have, the constraint simply does not
    apply and the moment the operator named stands.
    """
    return not (_content_words(clause) - _DATE_ONLY_WORDS)
