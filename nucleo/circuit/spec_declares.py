"""What the cards an end state names DECLARE — the datum the goal door hands back with a refusal (2026-11-06).

Split out of `spec.py` by concern: the end-state grammar stays there; what the refusal says about the cards lives here.
Measured on the use-case battery of 2026-11-06: six refusals in a row on one sheet (`items`, `rows`, `fichas`…) with
nothing telling the worker what the card reads. A fact about the manifests, never an example it could copy (V2-852 T10).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.circuit.spec")

#: The shape of a row's end state, with placeholders and no value a worker could copy as its own (V2-852 T10). Read by
#: the goal door's help and by the worker's playbook (checkpoint 1), so the brief shows the shape the row takes and not
#: only the prose it is judged by — measured 2026-11-06, every first `report goal` of eleven errands was prose.
SHAPE = ('{"all": [{"widget": "<card your work fills>", "collection": "<its collection>", '
         '"where": {"<field>~": "<what he asked for>"}, "count": {"min": <n>}}]}')


def said_of(base: str) -> str:
    """One card's sentence: unknown, declares nothing, or its collections with their declared fields."""
    from widgets import rows as _rows, runtime as _rt
    if _rt.get(base) is None:
        return f"«{base}» is not a card"
    cols = _rows.declared(base)
    if not cols:
        return f"«{base}» declares no collection a row clause can read"
    parts = []
    for name, cs in cols.items():
        fields = [str(f) for f in (cs.get("fields") or []) if isinstance(f, str)] if isinstance(cs, dict) else []
        parts.append(f"{name}" + (f" ({', '.join(fields[:8])})" if fields else ""))
    return f"«{base}» declares: " + "; ".join(parts)


def said(done_when, sheet: str = "") -> str:
    """What each card the clauses name DECLARES — the datum the refusal hands back, so the worker rewrites against
    the card's own collections instead of guessing names (measured 2026-11-06: six refusals in a row on one sheet,
    `items`, `rows`, `fichas`… with nothing telling it what the card reads). A card nobody knows is said so."""
    try:
        from nucleo.circuit import verify as _verify
        said: list[str] = []
        for c in _verify._clauses(done_when)[1]:
            wid = str(c.get("widget") or "").strip().lower()
            base = wid.split("::", 1)[0]
            if not base or any(s.startswith(f"«{base}»") for s in said):
                continue
            said.append(said_of(base))
        if not said and sheet:
            # prose names no card at all: the task's OWN sheet is the card its work fills, so say what it declares
            said.append("your sheet " + said_of("results"))
        return (" — " + " · ".join(said)) if said else ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"spec: what the named cards declare could not be read: {e!r}")
        return ""
