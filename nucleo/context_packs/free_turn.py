"""A FREE turn — the only kind a phase pack may ride (V2-781, `tres-tarjetas-y-el-video-por-alusion`).

Measured 2026-10-11 (ES): «Perfecto, música cerrada. Te quedan el tráiler pausado y la agenda abierta. ¿Sigo con algo
o le damos a la agenda?» was answered with «Una cosa antes de nada: ¿cómo te llamas? Y si quieres te cuento en un
momento qué puedo hacer por ti.» — the introduction pack, on top of a direct question, and the question unanswered.
(EN, same day: «hey, did you turn down the music or the video?» → «…By the way, I don't think I've caught your name
yet.»; «pause the video.» → «…Meanwhile, Alex, where are you based?».) The pack's own prose said «if he asks for
something, solve it first» and the model did not: a sentence about how to behave is not a mechanism.

So the turn's words decide whether the pack is SENT at all. A turn is free when it asks nothing, orders nothing and
is short — a greeting, an acknowledgement, an answer to our own question («Alex», «me llamo Alex»). A question mark,
an order verb or a long sentence is his business, and the prompt carries no phase block that turn.
"""
from __future__ import annotations

import re
import unicodedata

#: Beyond this many words a turn is a request of some kind, whatever its verbs.
MAX_FREE_WORDS = 16

_ORDER_RE = re.compile(
    r"(?<!\w)(?:"
    # ES imperatives (accent-blind, the text is normalised) and request openers
    r"pon(?:me|lo|la|los|las|le)?|abre(?:me|lo|la)?|cierra(?:lo|la|los|las)?|quita(?:me|lo|la)?|baja(?:le|lo|la)?"
    r"|sube(?:le|lo|la)?|para(?:lo|la)|pausa(?:lo|la)?|busca(?:me|lo|la)?|dime|ensena(?:me)?|muestra(?:me)?"
    r"|mira|apaga(?:lo|la)?|encien?de(?:lo|la)?|cambia(?:me|lo|la)?|anade(?:me|lo|la)?|borra(?:me|lo|la)?"
    r"|elimina(?:lo|la)?|crea(?:me)?|haz(?:me|lo)?|reserva(?:me)?|compra(?:me)?|llama(?:me|lo|la)?|manda(?:me|le)?"
    r"|envia(?:me|le)?|escribe(?:me|le)?|lee(?:me|lo)?|reproduce|dale|vuelve|sigue|recuerda(?:me)?|avisa(?:me)?"
    r"|guarda(?:me|lo|la)?|apunta(?:me|lo)?|quiero|necesito|puedes|podrias"
    # EN imperatives and request openers
    r"|put|open|close|turn|pause|play|stop|show|find|search|look|get|add|remove|delete|make|set|book|buy|call"
    r"|send|write|read|tell|give|bring|go|start|run|save|remind|check|please|can\s+you|could\s+you|would\s+you"
    r"|i\s+need|i\s+want|i'?d\s+like"
    r")(?!\w)", re.I)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def why_not(text: str) -> str:
    """"question" | "order" | "long" when the turn is not free, else ""."""
    t = str(text or "").strip()
    if not t:
        return ""
    if "?" in t or "¿" in t:
        return "question"
    if _ORDER_RE.search(_norm(t)):
        return "order"
    if len(re.findall(r"\w+", t)) > MAX_FREE_WORDS:
        return "long"
    return ""


def is_free(text: str) -> bool:
    """Whether a phase pack may ride this turn: he asked nothing, ordered nothing, and said it briefly."""
    return not why_not(text)
