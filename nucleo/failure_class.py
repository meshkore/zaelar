"""nucleo/failure_class.py — WHY a provider call failed, in five words a person can act on (V2-776 D4 / A5).

Measured 2026-09-27: the memory heart card said «sin proveedor (… [Errno 8] nodename nor servname provided)»
for two minutes of DNS trouble and the operator went to check his balances; the same day the widget generator's
CLI exited 1 twice and the reason was thrown away entirely. A failure that is not classified sends the person
to the wrong place, or to no place at all.

The vocabulary is closed on purpose — the durable row (`tasks.error_class`), the ⚙ and the heart card all read
it, and an open string drifts into a taxonomy nobody maintains:

  network   the call never reached the provider (DNS, refused, reset, timeout)   → check the connection
  credit    the provider refused on money or plan quota (402, «limit exhausted») → top up / wait for the reset
  auth      the credential was rejected (401/403, invalid key, not logged in)    → fix the key
  rate      too many requests right now (429 without a quota word)               → wait a moment
  ours      anything else — our bug until proven otherwise                       → look at the log

Lexical and deterministic: this runs on error text, never on a model.
"""
from __future__ import annotations

import re

CLASSES = ("network", "credit", "auth", "rate", "ours")

# Order matters: a «429 … Weekly Limit Exhausted» is a QUOTA (credit), not a transient rate limit — waiting a
# minute will not fix it, which is exactly the distinction the operator needs (z.ai, 2026-09-27 12:45).
_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("network", re.compile(r"errno 8|nodename nor servname|name or service not known|getaddrinfo|"
                           r"temporary failure in name resolution|connection (refused|reset|aborted)|"
                           r"connecterror|timed? ?out|timeout|network is unreachable|no route to host", re.I)),
    ("credit", re.compile(r"\b402\b|insufficient|balance|credit|billing|payment required|"
                          r"limit exhausted|usage limit|quota|out of (credits|funds)", re.I)),
    ("auth", re.compile(r"\b40[13]\b|unauthori[sz]ed|forbidden|invalid (api )?key|authentication|"
                        r"not logged in|please run /login|permission denied for (the )?api", re.I)),
    ("rate", re.compile(r"\b429\b|rate.?limit|too many requests|overloaded|\b529\b", re.I)),
)


def classify(text: str) -> str:
    """One of `CLASSES` for an error text. Empty or unrecognised text is `ours`: an unexplained failure is ours
    to explain, never silently blamed on a provider."""
    t = str(text or "")
    for name, rx in _RULES:
        if rx.search(t):
            return name
    return "ours"
