"""The English half of «did the reply PROMISE a first-person act?» (V2-776 K4, 2026-09-29).

`router_guards._PROMISE_RE` is the Spanish table; every consumer of `promises_action` — the act-repair gate,
the promise backstops, `a_promise_left_hanging` — was blind on the English demo («Yep — putting Madonna on.»,
«Sending that off to Andrew now.» → False). Measured shapes from demo passes 33-58; negation is honoured by the
same `unnegated_match` as the Spanish half («I won't send anything» is not a promise).
"""
from __future__ import annotations

import re

_PROMISE_EN_RE = re.compile(
    r"\b(?:i'?ll\b|i will\b|i'?m going to\b|i am going to\b|let me\b|"
    r"give me (?:a |one )?(?:sec|second|moment|minute)\b|one (?:sec|second|moment)\b|"
    r"(?:^|[—\-–,.!]\s*)on it\b|right away\b|coming (?:right )?up\b|"
    # a present participle of doing, with or without «I'm»: «putting Madonna on», «sending that off», «opening the…»
    r"(?:i'?m |i am )?(?:sending|opening|putting|adding|booking|drafting|writing|checking|looking|searching|"
    r"setting|moving|closing|playing|pulling|bringing|getting|switching|hunting|finding|queuing|cueing|"
    r"marking|forwarding|saving|creating|making|starting|turning|loading)\b[^.!?]{0,60}"
    r"(?:\bnow\b|\bon\b|\bup\b|\bfor you\b|\bright away\b|\bthat\b|\bit\b|\bthis\b|\bthem\b|\byou\b|\bto\b|\bthe\b|\ba\b|\bsome\b))")


#: a participle followed by a denial in the same breath is a refusal, not a promise («sending mail isn't something
#: I can do», «I'm not opening that»)
_DENIED_NEAR_RE = re.compile(r"(?:n't\b|n t\b|\bnot\b|\bcannot\b|\bnever\b|\bunable\b|\bno way\b)")


def promises_en(normalized: str) -> bool:
    """True when the NORMALISED reply (lowercase, accents folded — `text_norm._norm_txt`) promises an act."""
    from nucleo.flash.negation import clause_negated
    n = normalized or ""
    for m in _PROMISE_EN_RE.finditer(n):
        if clause_negated(n, m.start(), m.end()):
            continue
        window = n[max(0, m.start() - 24):min(len(n), m.end() + 40)]
        if _DENIED_NEAR_RE.search(window):
            continue
        return True
    return False
