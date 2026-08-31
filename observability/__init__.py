"""
observability/ — WHO, WHEN, and in which FLOW (2026-08-09).

The event log (`voice/observer.py` + `bus/log.py`) already recorded WHAT happens in the system. This module adds
the missing dimensions so it can be ANALYZED instead of merely watched go by:

- **`identity`** — a stable `user_id` per installation (a random, persisted UUID4) and
  a `session_id` for each operator work session.
- **`flows`** — reading by CORRELATION ID: a flow = everything triggered by a stimulus, from start to finish.

The **correlation id is NOT a new identifier**: it is the `trace` from V2-044 (`voice/trace.py`), which was already
created with each stimulus and propagated through ContextVar to everything derived from it. Inventing a second
parallel id would have created two truths that diverge at the first cross-loop seam someone forgets. What was done
was to PROMOTE IT: it goes from being a field inside the JSON to an **indexed column** (`events.corr_id`), and the
viewer displays it in its own column. A new flow (a new operator request, even if it modifies a previous result)
starts with a new correlation id; whatever continues a live flow (a worker delivery, a browser step) inherits its
own — ContextVar already handled that, and it does not change.

Boundaries: this module NEVER writes to the database. The bus sink (`bus/log.py`) remains the only writer of
`events`, just as the memory agent remains the only writer of memory.
"""
