"""nucleo/dispatch/thresholds.py — the RELOJES of a task of background, definidos a vez (V2-354).

Extraido of `dispatch.py` for pagar the trinquete of arquitectura, with the same criterion and the same precedente
that `dispatch_confirm.py` and `dispatch_prompts.py`: son constantes without a sola dependencia of the record, and the
leen TRES sites distintos —the supervisor of `nucleo/pulse/loop.py`, the cara live of `nucleo/flash/live_blocks.py` and
`dispatch.pending_summaries()`—. Se re-exportan from `dispatch` because ese continues siendo the contrato publico and
there is callers that the importan by there; esto es a mudanza, no a cambio of interfaz.

**Por what a sola definition and no a by consumidor**: two copias of estos numeros es exactamente how the
operator acaba oyendo a cosa of the aviso proactivo and another of the agent al that acaba of preguntar.
"""
from __future__ import annotations

import os

#: How much can estar a worker live SIN EMITIR NADA before of llamarlo stalled. «Encallado = silent», and esa
#: definition fue a correccion measurement: until the 2026-08-02 esto miraba the EDAD of the task, so that any
#: worker that pasara of three minutos is declaraba stalled although estuviera emitting each five segundos — the
#: Susurro is it creia, re-escalaba, and salian two and three workers haciendo the same work.
STUCK_SECS = float(os.getenv("WORKER_STUCK_SECS", "180"))

#: How long a task WITH a plan may go without completing one step (longer than `STUCK_SECS`: it is working, not
#: silent). Calibrated on two runs, 331 s and 236.8 s stuck at the first step; the operator's bar: «a search is
#: done in a minute, two or three at most», so 150 s for ONE step of a plan stays generous.
NO_STEP_SECS = float(os.getenv("WORKER_NO_STEP_SECS", "150"))
