"""nucleo/dispatch_thresholds.py — the RELOJES of a task of background, definidos a vez (V2-354).

Extraido of `dispatch.py` for pagar the trinquete of arquitectura, with the same criterion and the same precedente
that `dispatch_confirm.py` and `dispatch_prompts.py`: son constantes without a sola dependencia of the record, and the
leen TRES sites distintos —the supervisor of `nucleo/loop.py`, the cara live of `nucleo/flash/live_blocks.py` and
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

#: How much can pasar a task CON PLAN without complete a only step before of that is diga. Es mas long that
#: `STUCK_SECS` a purpose: here the task NO esta callada —trabaja, navega, emite— and a step of a operation
#: web can costar minutos. Lo that no es normal es that a plan of cuatro pasos siga in cero pasado this rato.
#:
#: CALIBRADO CON DOS MEDIDAS, no elegido a ojo — and the second caso es the that bajo the number:
#:   · `restaurant-tonight-madrid` (2026-08-27): plan a the 49 s, first step a the 380 → **331 s** parado.
#:   · `weekend-plan-barcelona__es` (2026-08-27): plan a the 237 s, first step a the 473,8 → **236,8 s**,
#:     that with the umbral in 240 no disparo **by 3,2 segundos**. Ocho minutos of errand without a step hecho and
#:     the operator without enterarse: the mecanismo funcionaba and the number estaba mal.
#: El liston it puso the operator the 2026-08-27: «a search is does in a minuto, two or three maximo». If
#: eso es the ENCARGO entero, 150 s for UN step of a plan of seis continues siendo generoso.
NO_STEP_SECS = float(os.getenv("WORKER_NO_STEP_SECS", "150"))
