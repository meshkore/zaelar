"""Resolver a widget by ANY of the names the system already knows it by.

Every widget carries an identity list —its id, its display name and its aliases— and `widgets/registry.py`
already builds it, normalised, for all 26 of them. What did not exist was anyone USING it from the worker's
side: `paths.dir_for` matches the folder id and nothing else, so the bridge answered «el widget «music» no
existe» to a name the rest of the system resolves without blinking.

Measured 2026-08-28 on `build-a-video-playlist-from-links` (24/7 lab). The worker asked for `music`; the
folder is `musica`. And it is not only an English problem — the same lookup rejects **`reloj`**, which is the
Spanish name of the widget whose folder is `clock`. The bridge simply did not speak the vocabulary.

It matters twice over right now: the US lab drives every round in English, and English is the language the
product is being sold in.

COLLISION IS A REFUSAL, not a guess. `widgets/aliases.py` guarantees an alias belongs to exactly one piece,
but a manifest edited by hand can break that, and picking one of two widgets to operate on is worse than
saying no — the caller is about to WRITE somewhere.
"""
from __future__ import annotations

import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def resolve(name: str) -> tuple[str, list[str]]:
    """`(id, candidatos)`. With a resolved id, `candidatos` is empty; with multiple candidates, the id is."""
    n = _norm(name)
    if not n:
        return "", []
    try:
        from widgets import registry
        entradas = registry.registry() or []
    except Exception:  # noqa: BLE001 — an unreadable registry must not bring down the caller
        return "", []
    exactos = [w for w in entradas if _norm(w.get("id")) == n]
    if exactos:
        return str(exactos[0].get("id") or ""), []
    tocados = []
    for w in entradas:
        vocab = [w.get("name")] + list(w.get("aliases") or []) + list(w.get("keywords") or [])
        if any(_norm(v) == n for v in vocab if v):
            tocados.append(str(w.get("id") or ""))
    tocados = sorted(set(tocados))
    if len(tocados) == 1:
        return tocados[0], []
    return "", tocados


def not_found(name: str, varios: list[str] | None = None) -> str:
    """The «does not exist» response, stating what IS available. A rejected name on its own leaves the worker guessing, and what it
    then does is retry the same one — measured all night at three other gateways."""
    if varios:
        return (f"«{name}» vale para varios widgets ({', '.join(varios)}): dilo por su id exacto")
    try:
        from widgets import registry
        ids = sorted(str(w.get("id") or "") for w in (registry.registry() or []) if w.get("id"))
    except Exception:  # noqa: BLE001
        ids = []
    cola = f" · los que hay: {', '.join(ids[:14])}" + ("…" if len(ids) > 14 else "") if ids else ""
    return f"el widget «{name}» no existe{cola}"


_NAMES_CACHE: dict = {}


def catalogue_names(widget_id: str) -> list[str]:
    """What the card is CALLED — its id, its manifest name and its translated catalogue name in every language
    bundle there is. Never its aliases: those name what it HOLDS («video», «clip»), not the card."""
    base = str(widget_id or "").split("::")[0].strip().lower()
    if base in _NAMES_CACHE:
        return _NAMES_CACHE[base]
    names = {base}
    try:
        from widgets import runtime as _rt
        names.add(str((_rt.get(base) or {}).get("name") or ""))
    except Exception:  # noqa: BLE001
        pass
    try:
        import json
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1] / "i18n"
        files = list((root / "bundles").glob("*.json"))
        try:
            from i18n import store as _i18n_store
            files += [_i18n_store._path(c) for c in _i18n_store.codes()]
        except Exception:  # noqa: BLE001
            pass
        for f in files:
            try:
                b = json.loads(pathlib.Path(f).read_text("utf-8"))
                b = b.get("strings", b) if isinstance(b, dict) else {}
                names.add(str(b.get(f"widgets.{base}.name") or ""))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    out = sorted({n.strip() for n in names if n and n.strip()}, key=len, reverse=True)
    _NAMES_CACHE[base] = out
    return out


def says_the_name(text: str, widget_id: str) -> bool:
    """Whether `text` calls the card by what it is CALLED (`catalogue_names`), as a whole word, accent- and
    case-blind. An alias («video» for the player) does not count: it names what the card holds."""
    import re
    t = _norm(text)
    return any(re.search(r"(?<!\w)" + re.escape(_norm(x)) + r"(?!\w)", t)
               for x in catalogue_names(widget_id) if len(x) >= 3)


# ── the cards a sentence tells to STAY (V2-781, `tres-tarjetas-y-el-video-por-alusion__us`) ─────────────────────
# «get rid of the video too, just keep the calendar up» closed the CALENDAR: every close reader looked for the
# cards the sentence NAMES, and the only card it named was the one it said to keep. A clause that tells a card to
# stay (keep, leave, don't close — and the same verbs in every language we ship) or excepts it («except») names a
# card that a close must never reach. One split, read by every close site (`instances.also_named`, `card_close`).
import re as _re

_CLAUSE_RE = _re.compile(r"([,.;:!?¡¿]+|\s(?:and|but|then|y|e|pero|luego)\s)", _re.I)
_KEEP_RE = _re.compile(r"(?<!\w)(?:keep(?:s|ing)?|leave|stays?|staying|d[eé]ja(?!\s+de\b)\w*|d[eé]jal\w*"
                       r"|mant[eé]n\w*|que\s+se\s+qued\w*|se\s+qued\w*|que\s+sig\w*)(?!\w)", _re.I)
_NOT_KEEP_RE = _re.compile(r"(?<!\w)(?:don'?t|do\s+not|no)\s+(?:keep|leave|dejes|mantengas)(?!\w)", _re.I)
_DONT_TOUCH_RE = _re.compile(r"(?<!\w)(?:don'?t|do\s+not|never|no)\s+(?:(?:lo|la|los|las|le|me|it|that|them)\s+)?(?:close|shut|touch|remove|kill|turn\s+off"
                             r"|cierres|quites|toques|apagues)(?!\w)", _re.I)
_EXCEPT_RE = _re.compile(r"(?<!\w)(?:except(?:\s+for)?|but\s+not|apart\s+from|other\s+than|menos|salvo|excepto)"
                         r"(?!\w).*", _re.I | _re.S)


def split_kept(text: str) -> tuple[str, str]:
    """`(close_words, kept_words)`: the sentence without the clauses that tell a card to stay, and those clauses.

    «get rid of the video too, just keep the calendar up» → («…get rid of the video too, », «just keep the calendar
    up»); «No, el vídeo, la música déjala» keeps «la música»; «cierra todo menos la agenda» keeps «la agenda».
    A negated keep («don't leave the music on») is an order to remove, and stays in the close words."""
    kept: list[str] = []
    out: list[str] = []
    for part in _CLAUSE_RE.split(str(text or "")):
        if _CLAUSE_RE.fullmatch(part or ""):
            out.append(part)
            continue
        if (_KEEP_RE.search(part) and not _NOT_KEEP_RE.search(part)) or _DONT_TOUCH_RE.search(part):
            kept.append(part)
            continue
        m = _EXCEPT_RE.search(part)
        if m:
            kept.append(m.group(0))
            part = part[:m.start()]
        out.append(part)
    return "".join(out), " ".join(kept)


def without_kept(text: str) -> str:
    """The words a close reads: the sentence minus every clause that tells a card to stay (`split_kept`)."""
    return split_kept(text)[0]
