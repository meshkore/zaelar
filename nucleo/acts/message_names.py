"""nucleo/acts/message_names.py — how the message door reads a NAME in his words (V2-849 D5, V2-854).

Split from `nucleo/acts/message.py` by concern: the folding and the token shape every reading of «did he name this
recipient» shares, and the one question V2-854 added — do his words name somebody ELSE whole?
"""
from __future__ import annotations

import re
import unicodedata as _ud

TOK = re.compile(r"[\w.@+-]{2,}[\w@+]")   # a sentence's closing mark is not part of a name or an address


def fold(v) -> str:
    return "".join(c for c in _ud.normalize("NFKD", str(v or "").lower()) if not _ud.combining(c))


def names_someone_else(said: list[str], ids: set[str], directory) -> bool:
    """Does a run of two or three of his words resolve, alone and exactly, to a contact that is not one of `ids`? A run
    whose first or last word is shorter than three letters («a raquel», «pablo de») is a phrase around a name, not a
    name, and is skipped."""
    for t in said:
        toks = TOK.findall(fold(t))
        for n in (3, 2):
            for i in range(len(toks) - n + 1):
                win = toks[i:i + n]
                if len(win[0]) < 3 or len(win[-1]) < 3:
                    continue
                hits = directory.resolve(" ".join(win), tolerant=False)
                if len(hits) == 1 and str(hits[0].get("id") or "") not in ids:
                    return True
    return False
