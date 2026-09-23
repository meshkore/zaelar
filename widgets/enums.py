"""widgets/enums.py — a declared CHOICE payload, read the way it is written (V2-754).

A manifest spells an enumerated payload key as text: `"tab": "inicio | player | cola"`, or
`"by": "'title' o 'added'"`. The model reads that text; the widget then compares the value it gets
against its own internal ids. Between the two sits a gap this module closes.

THE INCIDENT (live session 3afe34a8, 2026-09-23). «Venga, vuelve al inicio del widget de vídeo.»
The model called `youtube:show_tab` — the right card, the right action — with `tab: "home"`, which
is what «inicio» means and is not the string the widget keys on. The widget answered `unknown_tab`,
the reply said «te lo llevo al inicio», and nothing moved. A correct order, a correct action,
refused over vocabulary.

So a value may carry its ALIASES in the declaration, in parentheses, and both readers use the same
text: `"inicio (home, dashboard, catálogo) | player (reproductor) | cola (queue)"`. The model sees
the words it may use; the widget resolves any of them to the id. Aliases are product data — they
live in the manifest, in the operator's languages, never in a table of the engine's.

Pure and stdlib: no I/O, never raises. Unknown stays unknown — `resolve` returns "" rather than the
nearest value, because a silent wrong face is worse than a refused order (V2-742's own rule).
"""
from __future__ import annotations

import re as _re
import unicodedata as _ud

#: How a declaration separates its values. ` | ` is the house form; `' o '`/`' or '` is the older one.
_SEP_RE = _re.compile(r"\s*\|\s*|\s+o\s+|\s+or\s+")
#: `value (alias, alias)` — the parenthesised list is optional.
_VAL_RE = _re.compile(r"^\s*['\"]?([^\s'\"(]+)['\"]?\s*(?:\(([^)]*)\))?\s*$")


def _norm(s: str) -> str:
    n = _ud.normalize("NFKD", str(s or ""))
    n = "".join(c for c in n if not _ud.combining(c)).lower()
    return _re.sub(r"\s+", " ", n).strip()


def parse(spec: str) -> dict[str, list[str]]:
    """`{value: [aliases…]}` in declaration order, or `{}` when the text is not an enumeration.

    A trailing free-text tail («… (o como lo diga él)», «… — solo colorea la cita (opcional)») is a
    hint to the model, not a value: anything that does not read as `word (aliases)` is dropped, and
    a declaration that yields fewer than two values is not an enumeration at all.
    """
    out: dict[str, list[str]] = {}
    for part in _SEP_RE.split(str(spec or "")):
        m = _VAL_RE.match(part)
        if not m:
            continue
        value = m.group(1).strip().strip("'\"")
        if not value or value in out:
            continue
        aliases = [a.strip().strip("'\"") for a in (m.group(2) or "").split(",")]
        out[value] = [a for a in aliases if a]
    return out if len(out) >= 2 else {}


def values(spec: str) -> list[str]:
    return list(parse(spec))


def resolve(spec: str, given: str = "", words: str = "") -> str:
    """The declared value that `given` names — by id or by alias — else the ONE value the operator's
    own `words` name, else "".

    `given` first and alone: an explicit value the model wrote wins over anything in the sentence.
    Only when it is empty or unknown do the words count, and then the answer must be unambiguous — two
    different values named in one sentence («del reproductor a la cola») is a question, not a pick.
    """
    table = parse(spec)
    if not table:
        return ""
    g = _norm(given)
    if g:
        for value, aliases in table.items():
            if g == _norm(value) or g in {_norm(a) for a in aliases}:
                return value
    w = _norm(words)
    if not w:
        return ""
    found: list[str] = []
    for value, aliases in table.items():
        for token in [value, *aliases]:
            t = _norm(token)
            if t and _re.search(r"(?<!\w)" + _re.escape(t) + r"(?!\w)", w):
                if value not in found:
                    found.append(value)
                break
    return found[0] if len(found) == 1 else ""
