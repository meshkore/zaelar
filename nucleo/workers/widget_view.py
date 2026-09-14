"""nucleo/workers/widget_view.py — what a WORKER gets back when it reads a widget (V2-692c).

Measured live (2026-09-14, worker `8a787f-3`): asked to organise a meeting, the worker called `read agenda`
and got **59 955 bytes**, of which **55 666 are the `meetings` array** — the operator's entire calendar,
every field of every row. The CLI persisted it to a file («Output too large (58.5KB)»), the worker then
tried to READ that file and was refused twice («31 844 tokens exceeds maximum allowed 25 000»), and after
four wasted calls it still did not know what was in the calendar. Context reached 111 282 tokens in three
minutes and the engine had to ask it to deliver early.

**So the defect is not the size, it is that the only door hands back something nobody can consume.** The
worker could not read the operator's agenda at all, by construction — and the same is true of any widget
that grows: `mensajeria` with a year of threads, `results` with a long sheet.

The remedy is the one this house already built for the same problem one layer over: `refs.prompt_digest`,
the compact line-per-row summary the TURN prompt has used since V2-576. For the agenda it says the same
useful things in **975 bytes instead of 55 666** — sixty times smaller, and readable. A worker is a reader
of widgets exactly like the turn is; it simply never got the seam.

Two rules keep this honest:

  · **nothing is silently truncated.** A cut JSON object is worse than none — it reads as complete and is
    a different shape. Either the whole payload travels, or it is REPLACED by the digest plus a sentence
    saying what happened and where the rest is;
  · **a widget with no digest still answers.** It gets the payload's top-level keys and their sizes, so
    the worker learns what exists and can ask a declared action for the slice it needs, instead of being
    told «too big» with nowhere to go (the V2-219 class: a worker dies in the aridity of our own CLI).
"""
from __future__ import annotations

import json

from loguru import logger

#: Bytes of serialised payload above which the digest replaces it. ~3 000 tokens: generous enough that
#: nothing that fits today starts behaving differently, small enough to leave room for the actual work.
#: Chosen by measuring the catalog rather than guessed — only `agenda` and a long `mensajeria` pass it.
MAX_BYTES = 12_000


def _size(data) -> int:
    try:
        return len(json.dumps(data, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        return 0


def _digest(wid: str) -> str:
    """The widget's own compact summary, through the seam the turn prompt already uses."""
    try:
        from widgets import refs
        return str(refs.prompt_digest(wid) or "")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"widget_view: sin digest para «{wid}» ({e!r})")
        return ""


def _shape(data) -> str:
    """What IS in there, when there is no digest: the top-level keys and how big each one is. It tells the
    worker where the weight lives, which is what it needs to choose an action to ask for a slice."""
    if not isinstance(data, dict):
        return f"(un {type(data).__name__} de {_size(data)} bytes)"
    rows = sorted(((k, _size(v)) for k, v in data.items()), key=lambda kv: -kv[1])
    return " · ".join(f"{k} ({n} bytes)" for k, n in rows[:12])


def bounded(wid: str, data, *, max_bytes: int = MAX_BYTES) -> dict:
    """What travels back to the worker: `{"data"}` unchanged, or `{"digest", "too_big", "shape", "note"}`.

    The caller puts this straight into its `result`, so a small widget's answer is byte-for-byte what it
    has always been — this changes nothing for the fourteen widgets that fit.
    """
    n = _size(data)
    if data is None or n <= max_bytes:
        return {"data": data}
    digest = _digest(wid)
    note = (f"El contenido completo de «{wid}» ocupa {n} bytes y NO cabe en tu contexto — "
            f"no intentes leerlo entero. ")
    if digest:
        note += ("Abajo tienes el RESUMEN que usa el propio cerebro, con una línea por elemento. Si "
                 "necesitas el detalle de uno concreto, pídeselo al widget con una de sus acciones "
                 "DECLARADAS (las tienes en el `manifest`), nunca volviendo a leer el widget entero.")
    else:
        note += ("Este widget no publica resumen, así que abajo tienes QUÉ hay dentro y cuánto ocupa cada "
                 "parte. Pide la parte que te haga falta con una de sus acciones DECLARADAS.")
    return {"data": None, "too_big": n, "digest": digest, "shape": _shape(data), "note": note}
