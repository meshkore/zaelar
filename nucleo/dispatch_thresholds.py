"""nucleo/dispatch_thresholds.py — los RELOJES de una tarea de fondo, definidos una vez (V2-354).

Extraído de `dispatch.py` para pagar el trinquete de arquitectura, con el mismo criterio y el mismo precedente
que `dispatch_confirm.py` y `dispatch_prompts.py`: son constantes sin una sola dependencia del registro, y las
leen TRES sitios distintos —el supervisor de `nucleo/loop.py`, la cara viva de `nucleo/flash/live_blocks.py` y
`dispatch.pending_summaries()`—. Se re-exportan desde `dispatch` porque ése sigue siendo el contrato público y
hay llamantes que las importan por ahí; esto es una mudanza, no un cambio de interfaz.

**Por qué una sola definición y no una por consumidor**: dos copias de estos números es exactamente cómo el
operador acaba oyendo una cosa del aviso proactivo y otra del agente al que acaba de preguntar.
"""
from __future__ import annotations

import os

#: Cuánto puede estar un worker vivo SIN EMITIR NADA antes de llamarlo encallado. «Encallado = callado», y esa
#: definición fue una corrección medida: hasta el 2026-08-02 esto miraba la EDAD de la tarea, así que cualquier
#: worker que pasara de tres minutos se declaraba encallado aunque estuviera emitiendo cada cinco segundos — el
#: Susurro se lo creía, re-escalaba, y salían dos y tres workers haciendo el mismo trabajo.
STUCK_SECS = float(os.getenv("WORKER_STUCK_SECS", "180"))

#: Cuánto puede pasar una tarea CON PLAN sin completar un solo paso antes de que se diga. Es más largo que
#: `STUCK_SECS` a propósito: aquí la tarea NO está callada —trabaja, navega, emite— y un paso de una gestión
#: web puede costar minutos. Lo que no es normal es que un plan de cuatro pasos siga en cero pasado este rato.
#:
#: CALIBRADO CON DOS MEDIDAS, no elegido a ojo — y el segundo caso es el que bajó el número:
#:   · `restaurant-tonight-madrid` (2026-08-27): plan a los 49 s, primer paso a los 380 → **331 s** parado.
#:   · `weekend-plan-barcelona__es` (2026-08-27): plan a los 237 s, primer paso a los 473,8 → **236,8 s**,
#:     que con el umbral en 240 no disparó **por 3,2 segundos**. Ocho minutos de encargo sin un paso hecho y
#:     el operador sin enterarse: el mecanismo funcionaba y el número estaba mal.
#: El listón lo puso el operador el 2026-08-27: «una búsqueda se hace en un minuto, dos o tres máximo». Si
#: eso es el ENCARGO entero, 150 s para UN paso de un plan de seis sigue siendo generoso.
NO_STEP_SECS = float(os.getenv("WORKER_NO_STEP_SECS", "150"))
