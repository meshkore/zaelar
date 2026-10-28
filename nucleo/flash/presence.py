"""The PRESENCE knock and the bare call by name, read as ACTION-MAP ROWS (V2-640, V2-665, refactor2710-07).

«¿Sigues ahí?» is a knock on the door, not a task, and «Johnny.» alone is an address, not a request: both are answered
without a model by the voice lane (`voice/.../fast_lane.presence`, which owns speaking). What they ARE is declared data —
`do: presence` and `do: address` rows of the language's action-map pack (`i18n/genesis/<lang>/actionmap.json`) — so a new
language adds knocks as a translation; the regex that read them is gone. The lane's vocatives (`langs.smalltalk_book`)
are INJECTED by the caller, never imported: this module is neutral ground (dependency-direction ratchet, 7.32).
"""
from __future__ import annotations


def _norm(text: str) -> str:
    from nucleo.actionmap import normalize
    return normalize(text)


def _row(text: str, assistant_name: str, vocatives: tuple[str, ...]) -> tuple[str, bool]:
    """`(do, named)`: the action-map row the utterance is once the assistant's name and the language's generic
    vocatives are taken out («Hey, mate. You there?» → «hey you there»), and whether his name was in it. ≤7 words.
    `do` is "bare" when nothing is left, "" when what is left is no row of the active language."""
    from nucleo.actionmap import normalize, store
    n = f" {normalize(text)} "
    if not n.strip() or len(n.split()) > 7:
        return "", False
    named = False
    for name in sorted({normalize(x) for x in ({assistant_name} | set(assistant_names())) if x}, key=len, reverse=True):
        if name and f" {name} " in n:
            n, named = n.replace(f" {name} ", " "), True
    voc = {normalize(v) for v in vocatives} - {""}
    rest = " ".join(w for w in n.split() if w not in voc)
    if not rest:
        return "bare", named
    return str(((store.index().get(rest) or {}).get("action") or {}).get("do") or ""), named


def is_presence_check(text: str, assistant_name: str = "", vocatives: tuple[str, ...] = ()) -> bool:
    """True only when the WHOLE utterance is a presence knock: a `presence` row of the action map once his name and
    the vocatives are out (refactor2710-07 — the rows replaced the regex, so a language adds knocks as DATA).

    `vocatives` are the GENERIC forms of address of the operator's language, handed in by the caller from the
    phrasebook (V2-674): «Hey, mate. You there?» was measured reaching a model, and the only word standing between
    it and this function was «mate». Removed WHEREVER they appear: the remainder still has to be a row exactly."""
    return _row(text, assistant_name, vocatives)[0] == "presence"


# A bare call by NAME is an address, not a request — it opens the window and asks for attention, and the only
# honest answer is «dime». V2-665, session e82f7fcb (2026-09-11): «Johnny.» alone reached the model with a
# memory pill about a video he had asked for the night before still in the window, and the model ANSWERED «Voy
# a buscar el vídeo del Apolo 11» and fired a `widget_data` search on his behalf — inventing a request out of
# a summons. Six seconds later a second bare «Johnny.» got «Dime, Ricardo.», which is the right answer: the
# most frequent utterance in wake-word mode was non-deterministic, and half the time it acted. Now it never
# reaches a model and never reaches a tool.

def assistant_names() -> tuple[str, ...]:
    """Every word that counts as HIS NAME, normalized — the wake words the attention gate actually uses.

    ⚠️ Measured while building V2-665 and it is a defect OLDER than this batch: both callers of
    `is_presence_check` read `config.settings.get("assistant_name")`, and **that key is never written**.
    A rename lands in MEMORY state (`memory.state()["assistant_name"]`) and is pushed into `voice.attention`
    by `memory_cache`; the settings file has held `None` the whole time. So the vocative strip that lets
    «Johnny, ¿sigues ahí?» be recognised has been dead for a renamed assistant since V2-640 shipped, and the
    summons check would have been born dead the same way. One source now, and it is the one the gate itself
    consults — anything else is a second opinion that drifts.
    """
    try:
        from voice import attention
        ws = tuple(n for n in (_norm(w) for w in attention.wakewords()) if n)
        if ws:
            return ws
    except Exception:  # noqa: BLE001 — the probe may run with no voice engine at all
        pass
    return ("zaelar",)


def is_summons(text: str, assistant_name: str = "") -> bool:
    """True when the WHOLE utterance is the assistant's name and nothing else, or his name with only an `address`
    row around it («oye Johnny, por favor»): they carry no request either. Anything else after the name is a turn."""
    do, named = _row(text, assistant_name, ())
    return named and do in ("bare", "address")
