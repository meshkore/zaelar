"""search/spec_fit.py — a row that names ANOTHER value of an attribute he stated is not a candidate (V2-782 T3.3).

search-buy-tv ES (2026-10-14): «Búscame una tele OLED de 55 pulgadas por menos de 900 euros». The worker brought
«LG 65QNED70B6C», then — after «yo pedí OLED, esos no me valen» — «LG 55QNED70B6C» twice; the turn offered them.
search-buy-watch ES: «un Seiko automático … un solo Seiko, no un pack de dos» → «Pack 2 Relojes Seiko Automáticos»,
«Seiko 9533-5000 Majesta HAQ» (quartz) and «Seiko Solar» offered as candidates.

The asked value of each family (`spec_words.FAMILIES`) is the FIRST value his words name that is not ruled out
(«no QNED», «descarta el cuarzo»), plus any later one tied to it («diésel o híbrido») or wanted in so many words
(«me vale un QLED»): a correction that names what he got («son LED normales, y el LG es QNED») never becomes the
ask. His words first; the sheet's title and criteria only for a family his words leave silent. A row is off when
its title or facts name a value of that family and none of the asked ones. A row silent on the family stays.

Quantity is read the same way: «uno solo / a single / no un pack» asks for one item, «pack de 2 / 2-pack» for that
many; a row that states another count («Pack 2 …», «lote de …», «3 unidades») is off.
"""
from __future__ import annotations

import re

from search import asked as _asked
from search import spec_words as _w

_LB, _RB = r"(?<![a-z])", r"(?![a-z])"
_FAMILY_RX = {
    name: re.compile(_LB + "(" + "|".join(f"(?P<v{i}_{j}>{p})" for i, (_v, pats) in enumerate(fam["values"].items())
                                         for j, p in enumerate(sorted(pats, key=len, reverse=True))) + ")" + _RB)
    for name, fam in _w.FAMILIES.items()
}
_NEEDS = {name: re.compile(rf"\b(?:{fam['needs']})\b") for name, fam in _w.FAMILIES.items() if fam.get("needs")}
_NEG, _JOIN, _WANT = re.compile(_w.NEGATED_BEFORE), re.compile(_w.JOINED_BEFORE), re.compile(_w.WANTED_BEFORE)
_PACK = [re.compile(p) for p in _w.PACK]
_SINGLE = re.compile(_w.SINGLE)


def _value(name: str, m: re.Match) -> str:
    group = next(k for k, v in m.groupdict().items() if v)
    return list(_w.FAMILIES[name]["values"])[int(group[1:].split("_")[0])]


def _hits(name: str, text: str) -> list[tuple[int, int, str]]:
    """(start, end, value) of every value of family `name` that `text` names (accent-free lowercase)."""
    rx = _FAMILY_RX[name]
    # «LED» inside «Mini-LED» / «OLED» never reads alone: the alternation is longest-first and the boundary refuses
    # a letter before it, but a digit is allowed («55qned70», «oled55»).
    return [(m.start(), m.end(), _value(name, m)) for m in rx.finditer(text)]


def _asked_values(name: str, text: str) -> set[str]:
    """The values of one family this text ASKS for (see the module docstring), empty when it names none."""
    out: set[str] = set()
    last_end = None
    for start, end, value in _hits(name, text):
        if _NEG.search(text[max(0, start - 40):start]):
            continue
        before = text[last_end:start] if last_end is not None else ""
        if not out or _JOIN.match(before) or _WANT.search(text[max(0, start - 40):start]):
            out.add(value)
            last_end = end
    return out


def _row_text(row: dict) -> str:
    facts = " ".join(f"{f.get('label', '')}: {f.get('value', '')}" for f in (row.get("facts") or [])
                     if isinstance(f, dict))
    return _asked.norm(f"{row.get('title') or ''} · {facts}")


def _count(text: str) -> int | None:
    """How many items a text says one row is (-1 = several, uncounted), or None when it says nothing."""
    for rx in _PACK:
        m = rx.search(text)
        if m:
            raw = (m.group(1) or "").strip()
            n = int(raw) if raw.isdigit() else _w.NUMBER_WORDS.get(raw, -1)
            if n != 1:
                return n
    return None


def _asked_count(text: str) -> int | None:
    if _SINGLE.search(text):
        return 1
    for rx in _PACK[:2]:
        for m in rx.finditer(text):
            if _NEG.search(text[max(0, m.start() - 40):m.start()]):
                continue
            raw = m.group(1)
            return int(raw) if raw.isdigit() else _w.NUMBER_WORDS.get(raw)
    return None


def asked_specs(asked: str = "", context=()) -> dict:
    """{family: set of asked values} plus "count" (int) for every family the request states."""
    own = _asked.norm(asked)
    ctx = [_asked.norm(t) for t in (context or ()) if t]
    domain = " ".join([own] + ctx)
    out: dict = {}
    for name in _w.FAMILIES:
        if name in _NEEDS and not _NEEDS[name].search(domain):
            continue
        for text in [own] + ctx:
            got = _asked_values(name, text)
            if got:
                out[name] = got
                break
    for text in [own] + ctx:
        n = _asked_count(text)
        if n:
            out["count"] = n
            break
    return out


def why_off(row: dict, specs: dict) -> str:
    """Why this row contradicts a spec he stated, or "" when nothing it names does."""
    if not specs:
        return ""
    text = _row_text(row)
    for name, wanted in specs.items():
        if name == "count":
            continue
        named = {v for _s, _e, v in _hits(name, text)}
        served = named.union(*(_w.SATISFIES.get(name, {}).get(v, ()) for v in named)) if named else named
        if named and not served & wanted:
            return f"{sorted(named)[0]}, not {' / '.join(sorted(wanted))}, which he asked ({name})"
    want = specs.get("count")
    got = _count(text) if want else None
    if want and got is not None and got != want:
        said = "several items" if got < 0 else f"{got} items"
        return f"{said} in one offer, not {'one' if want == 1 else want}, which he asked"
    return ""


def split(on: list[dict], off: list[dict], asked: str = "", context=()):
    """The (on, off) of the gates before, with the rows that contradict a stated spec moved to `off` (with `why`)."""
    specs = asked_specs(asked, context)
    if not specs:
        return on, off
    keep, out = [], list(off)
    for it in on:
        why = why_off(it, specs)
        if why:
            out.append({"title": it.get("title", ""), "url": it.get("url", ""), "why": why[:200]})
        else:
            keep.append(it)
    return keep, out
