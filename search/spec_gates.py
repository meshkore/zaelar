"""search/spec_gates.py — the door's last gates: page chrome, a contradicted spec, another capacity, a second copy
(V2-782 T3.3). One call for `row_fit`, in order: `fragment_fit` (a facet or a navigation label is no row),
`spec_fit` (OLED asked, QNED named), `measure_fit` (8 kg asked, 6 kg stated), `row_dedupe` (the same model twice).
"""
from __future__ import annotations

from search import fragment_fit as _fragment
from search import measure_fit as _measure
from search import row_dedupe as _dedupe
from search import spec_fit as _spec


def split(on: list[dict], off: list[dict], asked: str = "", context=(), prior=()):
    """The (on, off) of the gates before, with these four applied; `prior` = rows already on the sheet."""
    on, off = _fragment.split(on, off)
    on, off = _spec.split(on, off, asked, context)
    on, off = _measure.split(on, off, asked, context)
    return _dedupe.split(on, off, prior)
