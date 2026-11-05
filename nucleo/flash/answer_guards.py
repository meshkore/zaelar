"""nucleo/flash/answer_guards.py — the agent never denies a capability it has (V2-676).

This file held five guards that read OUR OWN reply after the turn: a world fact with no source (V2-210), a bare ack
or an empty wait answering a question (V2-572/V2-587), a continuity claim over nothing (V2-645). Each fed a second
model pass after the main stream; V2-851 F5 removed every such re-run (node 2.1191), and the four went with their
only readers. What stays is a reading the SEARCH door makes of a provider's answer before it is spoken: a sentence
claiming the agent cannot reach the internet is false about this product in every case, so the door replaces it.
"""
from __future__ import annotations

import re as _re


# ── THE AGENT DENIES A CAPABILITY IT HAS (V2-676) ────────────────────────────────────────────────────────────
# Measured on the operator's own English session (`af4429e0`, 2026-09-11, 22:03:03), after five searches that
# all came back empty because Google and DuckDuckGo both answered with an anti-bot challenge:
#
#     OPERATOR  How is this possible? Don't you have access to the Internet?
#     ZAELAR    I actually don't have live internet access to fetch real-time information like current
#               weather conditions. I can only work with knowledge from my training data, which has a
#               cutoff date.
#
# Every clause of that is false about this product: there is a search module, a real browser, and a model
# that reaches both. What the model was doing is what a bare language model does with an empty context — it
# explained the emptiness with its own nature. His reaction is the measure of the cost: «no entiendo cómo
# después de dos meses de pruebas el sistema falla y dice que no sabe buscar».
#
# Unlike the other guards in this file, this one reads the ANSWER ALONE. The others need the question to know
# whether the reply is wrong; this sentence is false whenever it is said, over an empty search or a full one.
#
# It is narrow on purpose. It does NOT fire on «no he podido comprobarlo» or «la búsqueda no ha traído nada»
# — those are true and are exactly what we want said instead. It fires on a claim about what the agent IS.
_DENIES_THE_WORLD_RE = _re.compile(
    r"(no\s+tengo\s+acceso\s+(directo\s+)?a\s+(internet|la\s+red|la\s+web)|"
    r"sin\s+acceso\s+a\s+internet|"
    r"no\s+puedo\s+(acceder\s+a|navegar\s+por|buscar\s+en|conectarme\s+a)\s+(internet|la\s+red|la\s+web)|"
    r"no\s+puedo\s+(consultar|acceder\s+a|obtener)\s+[^.]{0,30}tiempo\s+real|"
    r"(mis\s+)?datos\s+de\s+entrenamiento|fecha\s+de\s+corte|"
    r"(do\s*n[o']?t|do\s+not|cannot|can\s*not|can[o']?t)\s+have\s+[^.]{0,30}"
    r"(internet|web|online)\s+access|"
    r"no\s+(live|real[\s-]?time|direct)\s+(internet|web|online)\s+access|"
    r"(do\s*n[o']?t|do\s+not|cannot|can\s*not|can[o']?t)\s+(access|browse|search|reach)\s+the\s+"
    r"(internet|web)|"
    r"(training|knowledge)\s+data[^.]{0,40}cut\s*-?\s*off|"
    r"(training|knowledge)\s+cut\s*-?\s*off)", _re.I)


def a_reply_denies_the_world(reply: str) -> bool:
    """Does this answer claim the agent cannot reach the internet, or that it only knows its training data?

    The claim is FALSE about this product in every case, so there is no second condition to check. The caller
    replaces the sentence rather than merely logging it: a false claim the operator can hear is not a warning,
    it is the failure itself.
    """
    return bool(_DENIES_THE_WORLD_RE.search(reply or ""))
