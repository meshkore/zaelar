"""search/measure_fit.py — a row whose stated capacity is not the one he asked is not a candidate (V2-782 T3.3).

«Una lavadora de 8 kg», «a 4.5 cu ft washer»: a row that states a capacity in the same unit, and none of them
matches, contradicts him. A capacity said bare is what he needs: a smaller row is off, and so is one more than
`OVERSIZE` times it (a 12 kg machine is another class than an 8 kg one), while a 9 kg row stays. A floor («al menos
8 kg», «4.5 cu ft or more») rules out only smaller rows, a cap («hasta 8 kg») only bigger ones. Only amounts within half to double the asked one are read as the row's capacity:
«peso 65 kg» or a «45 to Up» filter label is another number, and a fact labelled as another quantity (weight,
dryer) is skipped. A row that states no capacity in that unit stays. Units: `spec_words.MEASURES`.
"""
from __future__ import annotations

import re

from search import asked as _asked
from search import spec_words as _w

OVERSIZE = 1.3
_NUM = r"(\d{1,3}(?:[.,]\d{1,2})?)"
_RX = {name: re.compile(rf"(?<![\d.,]){_NUM}(?:\s?/\s?{_NUM})?\s?(?:{unit})(?![a-z])")
       for name, (unit, _tol) in _w.MEASURES.items()}
_OTHER = re.compile(_w.MEASURE_OTHER_LABEL)
_FLOOR = [re.compile(p) for p in _w.MEASURE_FLOOR]
_CAP = [re.compile(p) for p in _w.MEASURE_CAP]


def _f(raw: str) -> float:
    return float(raw.replace(",", "."))


def _asked_one(name: str, text: str) -> dict | None:
    for m in _RX[name].finditer(text):
        before, after = text[max(0, m.start() - 30):m.start()], text[m.end():m.end() + 20]
        bound = ("floor" if _FLOOR[0].search(before) or _FLOOR[1].match(after) else
                 "cap" if _CAP[0].search(before) or _CAP[1].match(after) else "exact")
        return {"value": _f(m.group(1)), "bound": bound}
    return None


def asked_measures(asked: str = "", context=()) -> dict:
    """{unit: {"value", "bound"}} for every capacity the request states (his words first)."""
    out = {}
    for name in _w.MEASURES:
        for text in [_asked.norm(asked)] + [_asked.norm(t) for t in (context or ()) if t]:
            got = _asked_one(name, text)
            if got:
                out[name] = got
                break
    return out


def _row_amounts(name: str, row: dict, want: float) -> list[float]:
    parts = [str(row.get("title") or "")]
    parts += [str(f.get("value") or "") for f in (row.get("facts") or [])
              if isinstance(f, dict) and not _OTHER.search(_asked.norm(f.get("label")))]
    out = []
    for m in _RX[name].finditer(_asked.norm(" · ".join(parts))):
        out += [_f(g) for g in m.groups() if g]
    return [v for v in out if want / 2 <= v <= want * 2]


def _fits(v: float, ask: dict, tol: float) -> bool:
    if ask["bound"] == "floor":
        return v >= ask["value"] - tol
    if ask["bound"] == "cap":
        return v <= ask["value"] + tol
    return ask["value"] - tol <= v <= ask["value"] * OVERSIZE + tol


def why_off(row: dict, measures: dict) -> str:
    for name, ask in measures.items():
        tol = _w.MEASURES[name][1]
        got = _row_amounts(name, row, ask["value"])
        if got and not any(_fits(v, ask, tol) for v in got):
            word = {"floor": "at least ", "cap": "at most "}.get(ask["bound"], "about ")
            return f"{got[0]:g} {name}, not the {word}{ask['value']:g} {name} he asked"
    return ""


def split(on: list[dict], off: list[dict], asked: str = "", context=()):
    """The (on, off) of the gates before, with the rows of another capacity moved to `off` (with `why`)."""
    measures = asked_measures(asked, context)
    if not measures:
        return on, off
    keep, out = [], list(off)
    for it in on:
        why = why_off(it, measures)
        if why:
            out.append({"title": it.get("title", ""), "url": it.get("url", ""), "why": why[:200]})
        else:
            keep.append(it)
    return keep, out
