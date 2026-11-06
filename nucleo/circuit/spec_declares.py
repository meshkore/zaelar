"""What the cards an end state names DECLARE — the datum the goal door hands back with a refusal (2026-11-06).

Split out of `spec.py` by concern: the end-state grammar stays there; what the refusal says about the cards lives here.
Measured on the use-case battery of 2026-11-06: six refusals in a row on one sheet (`items`, `rows`, `fichas`…) with
nothing telling the worker what the card reads. A fact about the manifests, never an example it could copy (V2-852 T10).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.circuit.spec")


def said(done_when) -> str:
    """What each card the clauses name DECLARES — the datum the refusal hands back, so the worker rewrites against
    the card's own collections instead of guessing names (measured 2026-11-06: six refusals in a row on one sheet,
    `items`, `rows`, `fichas`… with nothing telling it what the card reads). A card nobody knows is said so."""
    try:
        from nucleo.circuit import verify as _verify
        from widgets import rows as _rows, runtime as _rt
        said: list[str] = []
        for c in _verify._clauses(done_when)[1]:
            wid = str(c.get("widget") or "").strip().lower()
            base = wid.split("::", 1)[0]
            if not base or any(s.startswith(f"«{base}»") for s in said):
                continue
            if _rt.get(base) is None:
                said.append(f"«{base}» is not a card")
                continue
            cols = _rows.declared(base)
            if not cols:
                said.append(f"«{base}» declares no collection a row clause can read")
                continue
            parts = []
            for name, cs in cols.items():
                fields = [str(f) for f in (cs.get("fields") or []) if isinstance(f, str)] if isinstance(cs, dict) else []
                parts.append(f"{name}" + (f" ({', '.join(fields[:8])})" if fields else ""))
            said.append(f"«{base}» declares: " + "; ".join(parts))
        return (" — " + " · ".join(said)) if said else ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"spec: what the named cards declare could not be read: {e!r}")
        return ""
