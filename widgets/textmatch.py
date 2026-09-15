"""widgets/textmatch.py — ONE tolerant, intelligent text match for every internal lookup (V2-705).

The operator's standing complaint, 2026-09-15, verbatim: «las búsquedas de contactos y de datos internos
deben funcionar con algún poco de tolerancia… una C por una K, una letra que falta, una H… tiene que
funcionar para cualquiera, tanto para buscar contactos como para buscar una entrada en un calendario…
localizar mensajes de ciertas personas. Que sea flexible, que sea preciso pero que sea inteligente.»

Until now each surface grew its OWN matcher, and each was tolerant in a different way: the contacts door
had a difflib near-match (V2-698), the agenda matched a title as an accent-folded substring, the message
archive leaned on SQL FTS, and the send door had just learned to peel decoration off a recipient. Four
matchers, four behaviours, four bugs. This module is the ONE they share, so «C for K» works the same
whether you are naming a person, a meeting or a sender.

THREE primitives, stdlib-only (this is imported by `widgets/*/data.py`, which is stdlib-only by contract):

  · `fold(s)`      — the canonical form: accent-stripped, lowercased, punctuation to spaces, collapsed.
  · `spans(text)`  — the pieces of a phrase that could be the THING named, decoration peeled off, most
                     specific first («Kryptonite (Telegram @x)» → «Kryptonite (Telegram @x)», «Kryptonite»).
  · `rank(q, items, key, floor)` — every item scored against the query and sorted, best first, only those
                     at or above `floor`. The score is tolerant BY CONSTRUCTION: an exact fold is 1.0, a
                     containment is high, and otherwise it is a character-similarity ratio (difflib), which
                     is exactly what turns a C into a K and forgives a dropped letter.

WHAT THIS IS NOT. Not a decision about WHICH match to act on — that stays with the caller, because the
right answer differs by surface: the send door must never write to the wrong person, so it takes a unique
near-match and asks otherwise (`pick_one`); a read may happily show the top few. And not a ranker that
INVENTS a match: below `floor` it returns nothing, so «no hay, no hay» stays a real answer. When many
plausible matches survive, handing the shortlist to the language model to choose is the caller's move, and
`rank` is what produces that shortlist.
"""
from __future__ import annotations

import difflib
import re
import unicodedata


def fold(s) -> str:
    """Canonical comparison form: NFKD accent-strip, lowercase, every run of non-alphanumerics to one
    space, trimmed. «Crùz, José-Mª » → «cruz jose ma». The one normaliser the whole system compares on."""
    n = unicodedata.normalize("NFKD", str(s or ""))
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    return re.sub(r"[^0-9a-z]+", " ", n).strip()


def _tokens(s) -> list[str]:
    return [t for t in fold(s).split(" ") if t]


#: Words too generic to be the thing named — a query made only of these resolves to nobody, never to
#: «the first row». Kept short and shared; a surface with its own stopwords adds them at the call site.
_GENERIC = frozenset(
    "the a an my your his her their our to for of on at with and or el la los las un una unos unas mi tu su "
    "sus de del al con para por que the contact contacto person persona cita meeting appointment mensaje "
    "message chat grupo group".split())


def spans(text: str, *, limit: int = 6) -> list[str]:
    """The pieces of `text` that could be the thing NAMED, most specific first and decoration peeled.

    Order: the whole phrase (an exact name wins outright), then the phrase without any «(…)» / «[…]»
    annotation, then the head before the first comma/dash, then the leading Capitalised run, then each
    quoted span. De-duplicated, generic-only fragments dropped. This is what lets «write to Kryptonite
    (Telegram @x)», «the dentist appointment, the one on the 16th» and «"Ana", my neighbour» all reduce to
    the token that identifies them, without a per-surface regex."""
    raw = str(text or "").strip()
    if not raw:
        return []
    out: list[str] = [raw]
    no_paren = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*", " ", raw).strip()
    if no_paren and no_paren != raw:
        out.append(no_paren)
    head = re.split(r"[,;:–—]| - ", no_paren or raw)[0].strip()
    if head:
        out.append(head)
    m = re.match(r"([A-ZÀ-Ý][\wÀ-ſ'\-]*(?:\s+[A-ZÀ-Ý][\wÀ-ſ'\-]*)*)",
                 head or raw)
    if m:
        out.append(m.group(1).strip())
    out += [q.strip() for q in re.findall(r"[\"'«]([^\"'»]{2,60})[\"'»]", raw)]
    seen, keep = set(), []
    for s in out:
        f = fold(s)
        if not f or f in seen:
            continue
        if all(t in _GENERIC for t in f.split(" ")):        # a fragment of only filler names nothing
            continue
        seen.add(f)
        keep.append(s.strip())
        if len(keep) >= limit:
            break
    return keep


def score(query: str, candidate: str) -> float:
    """How well `candidate` answers `query`, in [0, 1]. Tolerant by construction: an exact fold is 1.0; a
    query whose every token appears in the candidate scores high (0.9 shrinking with the length gap, so
    «ana» inside «anastasia» is a WEAKER whole-word hit than «ana garcia» inside «ana garcia lopez»);
    otherwise a character-similarity ratio, which is what forgives a C for a K and a dropped letter."""
    q, c = fold(query), fold(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    # WHOLE-WORD SUBSET, on CONTENT tokens (stopwords dropped): «renovar seguro coche» is the same event as
    # «Renovar el seguro del coche», and the dropped «el/del» must not cost it. Scored by how much of the
    # candidate's content the query covers, so a one-word query inside a five-word title is a weaker hit than
    # a three-word one — without punishing the honest match below the floor.
    qc = [t for t in q.split(" ") if t not in _GENERIC] or q.split(" ")
    cc = [t for t in c.split(" ") if t not in _GENERIC] or c.split(" ")
    cset = set(cc)
    if qc and all(t in cset for t in qc):
        return round(0.75 + 0.2 * (len(qc) / max(len(qc), len(cc))), 4)
    if q in c:
        return round(0.7 + 0.15 * (len(q) / len(c)), 4)
    return difflib.SequenceMatcher(None, q, c).ratio()


def rank(query: str, items, key=None, *, floor: float = 0.72, limit: int = 8) -> list[tuple[float, object]]:
    """`[(score, item), …]` for the items scoring at or above `floor`, best first. `key(item)` yields the
    text to match (default: the item itself). `floor` is deliberately forgiving — one substituted letter in
    a short name still clears it — while staying below the point where unrelated words match. Ties in the
    caller's order. Below the floor the list is EMPTY: «no hay, no hay» must survive."""
    getk = key if callable(key) else (lambda x: x)
    scored = []
    for it in items or ():
        try:
            s = score(query, getk(it))
        except Exception:  # noqa: BLE001
            s = 0.0
        if s >= floor:
            scored.append((s, it))
    scored.sort(key=lambda t: -t[0])
    return scored[:limit]


def pick_one(query: str, items, key=None, *, floor: float = 0.8, margin: float = 0.1):
    """The ONE item `query` unambiguously names, or None — for a door where acting on the wrong one cannot
    be taken back (writing to a person, cancelling a meeting). Returns the top match only when it clears
    `floor` AND stands clear of the runner-up by `margin`; a near tie is an ambiguity the caller must ASK
    about, never resolve silently (the refs.py doctrine). An exact fold always wins, tie or not."""
    getk = key if callable(key) else (lambda x: x)
    q = fold(query)
    exact = [it for it in (items or ()) if fold(getk(it)) == q]
    if len(exact) == 1:
        return exact[0]
    ranked = rank(query, items, key=key, floor=min(floor, 0.72), limit=3)
    if not ranked:
        return None
    if ranked[0][0] >= floor and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= margin):
        return ranked[0][1]
    return None
