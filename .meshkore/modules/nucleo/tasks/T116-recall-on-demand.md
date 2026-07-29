---
id: T116
title: "Recall bajo demanda (no en cada frase), en paralelo con la frase-puente"
status: done
priority: medium
owner: ricart
category: nucleo
initiative: V2-011
depends_on: [T115]
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [1eb506c]
---

# T116 — Recall específico solo cuando el turno lo pide

La consulta semántica a memoria solo se dispara cuando el turno la necesita (heurística ligera o tool del
FlashBrain), no en cada frase de charla. Cuando se dispare, correr en paralelo con la frase-puente
(`filler_holding`) para que el usuario no perciba espera. El estado básico (nombre/trato/ubicación) sigue viniendo
del bloque cacheado de T114.

## Cierre (2026-07-09)

`prompt.needs_recall(text)` — heurística ligera (regex normalizado sin acentos/apóstrofes, patrones es/en) que
detecta turnos que piden RECORDAR un dato más allá del estado cacheado (verbos de recuerdo, referencias a sesiones
pasadas, preguntas por una posesión/dato personal: "¿dónde está mi coche?", "where is my car"). `nucleo.py::_run`
solo dispara `compose_recall` (embeddings, off-loop) cuando `needs_recall` es True → la charla normal NUNCA toca el
retriever (cierra ~1s); el estado (nombre/trato/…) sigue viniendo del caché de T114. Se emite `recall_fired` en el
evento `timing` para verlo en `/debug`. Tests parametrizados (dispara / no dispara). **Decisión (mínima latencia +
limpio):** cuando el recall se dispara corre off-loop (warm ~100–200 ms), muy por debajo del pico de 3s, así que
NO se antepone una frase-puente hablada (crearía un turno de dos locuciones "dame un momento"…+respuesta, peor UX);
el mecanismo `filler_holding` se conserva para el path lento de escalada real, que sí lo necesita.
