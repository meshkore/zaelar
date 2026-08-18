"""nucleo/flash/vault_carrier.py — is the spoken secret the WHOLE turn, or is it inside a request?

V2-141 (`pay-known-bill__es`, round 2). The operator had been asked, by zaelar, for the invoice number, the
amount and the IBAN. He gave all three in one turn — and got NOTHING back. The judge recorded it verbatim as
`(sin respuesta)`, right after bank details, which reads like the system swallowed his money data.

The cause is not the model. Both channels intercept a detected secret DETERMINISTA before the model sees it
(V2-060, and that invariant is untouchable: a secret value must never reach an LLM) — but the intercept then
`return`s, consuming the ENTIRE turn. That is correct when the turn IS the secret («mi contraseña de Netflix es
X»): there is nothing else to answer. It is wrong when the secret arrives INSIDE a request, which is the normal
way an IBAN gets spoken at all — nobody recites an IBAN for fun, they recite it to pay something. The request
is lost, and for money it is worse than lost: the confirm-gate lives further down the turn, so a payment order
carrying its own IBAN could never reach the gate that exists to stop it.

The predicate is deliberately about SHAPE, not intent — it decides whether there is anything left to answer,
and the rest of the turn decides what to do with it. Measured on real utterances of both classes:

    «mi contraseña de Netflix es …»                                    →  5 content words left
    «el IBAN es …»                                                     →  3
    «apunta mi tarjeta …»                                              →  3
    «aquí van: número de factura …, el importe 57,32€, y el IBAN …»    → 24
    «te paso el IBAN … y haz la transferencia de 57,32 a Iberdrola»    → 18

Five and twenty-four are not a close call, and the gap is why a word count is honest here: a carrier phrase is
short by nature («my X is»), a request is not. The threshold sits in the middle of the measured gap, biased to
the SAFE side — erring towards "there is still a request" costs one ordinary turn on a redacted text, while
erring the other way loses what the operator actually asked for.
"""
from __future__ import annotations

import re as _re

# Middle of the measured gap (6 → 18). Not tuned to make one case pass: any value from ~8 to ~15 separates the
# two classes on every utterance measured, so the exact number is not load-bearing.
CARRIER_MAX_WORDS = 10

_WORD_RE = _re.compile(r"\w+", _re.UNICODE)


def leftover_words(text: str, detected) -> int:
    """Content words left once every detected secret VALUE and the redaction marker are taken out."""
    rest = text or ""
    for d in detected or []:
        value = getattr(d, "value", "") or ""
        if value:
            rest = rest.replace(value, " ")
    rest = rest.replace("«secreto guardado»", " ")
    return len(_WORD_RE.findall(rest))


def secret_is_the_whole_turn(text: str, detected) -> bool:
    """True when the turn carries nothing but the secret and the phrase introducing it — so consuming the turn
    loses nothing. False when there is still a request in it, and the turn must go on (on the REDACTED text)."""
    if not detected:
        return False
    return leftover_words(text, detected) <= CARRIER_MAX_WORDS
