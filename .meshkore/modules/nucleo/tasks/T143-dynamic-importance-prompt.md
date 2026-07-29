---
id: T143
title: "Prompt DINÁMICO de importancia: se compone desde el estado/situación del operador (estudio derecho → derecho importa)"
status: next
priority: high
owner: ricart
category: nucleo
initiative: V2-013
depends_on: [T123]
created: 2026-07-09
updated: 2026-07-09
---

# T143 — Prompt dinámico de importancia del procesador de memoria

El prompt que usa el LLM local para decidir capa+importancia NO es fijo: se compone desde el estado/situación del
operador. Si el operador estudia derecho, lo relativo a derecho es muy importante; si investiga pájaros, esa info
importa. El procesador (T123) lee el `state` y arma un prompt contextual que sesga la evaluación de relevancia
hacia lo que le importa al operador AHORA. Evitar el "todo es importante": presupuesto/umbral + el consolidador poda.
