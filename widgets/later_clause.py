"""A card he says he will LOOK AT LATER is a card to keep (`tres-tarjetas-y-el-video-por-alusion`, ES, 2026-10-14).

The trailer on `youtube`, the music and the agenda open: «Perfecto, cierra el vídeo y deja la música sonando de
fondo, porfa. La agenda la miro luego.» closed the AGENDA. «el vídeo» is an alias of the player, not its catalogue
name, so the only card the close words called by its NAME was the agenda — in a clause that defers looking at it.
`naming.split_kept` knew keep / leave / don't-touch / except, not «I'll look at it later», so the deferral stayed in
the close words and `card_close.verdict_unless_named` let that name beat the verdict's `youtube:close`.

A deferral is a look verb and a later adverb in one clause with no close verb: «la agenda la miro luego», «luego la
miro», «ya la veré después», «I'll check the calendar later». Read by `naming.split_kept` before its own clause split
(which cuts at « luego » / « then » and would separate «la agenda» from «luego la miro»), so every close reader of
both channels inherits it. The Spanish and English words below are product vocabulary, not prose.
"""
from __future__ import annotations

import re

#: Sentence pieces: punctuation only — the conjunction split happens per piece, below.
_PIECE_RE = re.compile(r"([,.;:!?¡¿]+)")
#: Conjunctions that join two orders inside one piece. «luego» / «then» are NOT here: they are the later adverb.
_AND_RE = re.compile(r"(\s(?:and|but|y|e|pero)\s)", re.I)

_LOOK_RE = re.compile(
    r"(?<!\w)(?:mir(?:o|are|aremos|amos)|ve(?:o|re|remos)|revis(?:o|are)|consult(?:o|are)|le(?:o|ere)"
    r"|ech(?:o|are)\s+(?:un\s+)?(?:vistazo|ojo)|me\s+pongo|check|look|see|read|review|go\s+through|get\s+to"
    r"|deal\s+with)(?!\w)", re.I)
_LATER_RE = re.compile(
    r"(?<!\w)(?:luego|despues|mas\s+tarde|en\s+un\s+rato|otro\s+rato|para\s+luego|manana|later|afterwards"
    r"|in\s+a\s+(?:bit|while|minute)|another\s+time|tomorrow)(?!\w)", re.I)
#: A clause that also orders a close is that close, not a deferral: «cierra la agenda, luego la miro» stays an order.
_CLOSE_RE = re.compile(r"(?<!\w)(?:cierr\w*|cerr\w*|quit\w*|close[sd]?|shut|remove|get\s+rid)(?!\w)", re.I)


def _plain(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def is_deferral(part: str) -> bool:
    """Whether this clause puts LOOKING at something off until later — and orders no close."""
    p = _plain(part)
    return bool(_LOOK_RE.search(p) and _LATER_RE.search(p) and not _CLOSE_RE.search(p))


def split_deferred(text: str) -> tuple[str, list[str]]:
    """`(rest, deferred)`: the sentence without its deferral clauses, and those clauses. Never raises."""
    rest: list[str] = []
    deferred: list[str] = []
    for piece in _PIECE_RE.split(str(text or "")):
        if _PIECE_RE.fullmatch(piece or ""):
            rest.append(piece)
            continue
        for sub in _AND_RE.split(piece):
            if sub and not _AND_RE.fullmatch(sub) and is_deferral(sub):
                deferred.append(sub)
            else:
                rest.append(sub)
    return "".join(rest), deferred
