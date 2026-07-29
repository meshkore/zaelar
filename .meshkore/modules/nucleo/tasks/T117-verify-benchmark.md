---
id: T117
title: "Verificar latencia con el tester + registrar en zaelar-model-benchmarks.md"
status: done
priority: high
owner: ricart
category: nucleo
initiative: V2-011
depends_on: [T116]
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [aeaebc3]
---

# T117 — Verificación medida de la latencia

Re-correr el tester (`conversation`/`memory`/`widget`) contra `BRAIN=nucleo` y comparar la latencia con el baseline
del 2026-07-09 (3726avg / 4742max en memory; 5885avg / 8900max en widget). Objetivo: p50 < ~1.5s en charla, sin
picos >3s; recall de memoria conservado (nombre + dato). Registrar los números en
`.meshkore/docs/ops/zaelar-model-benchmarks.md`.

## Cierre (2026-07-09)

Medido con el tester (`memory`/`widget`/`conversation`, `--no-open --hold 0`):
- `memory`: `fast_ms` p50 **1139** (avg 1132, max 1247) vs baseline 3726avg/4742max → **×3.3, sin picos**. Recall
  REAL conservado: "¿dónde está mi coche?" → "Tu coche está en el taller hasta el viernes" (mem_query 137/172 ms
  OFF-LOOP, disparado solo en los 2 turnos de recall).
- `widget`: `fast_ms` p50 **1031** (avg 1045, max 1347) vs baseline 5885avg/8900max → **×5.6, max 8900→1347**.
  Ningún turno tocó el retriever.
- `conversation`: charla pura 751–2070 ms; el max (4 s) es el 1er turno frío (kickoff) + turnos que ESCALAN —
  ajeno a V2-011 (la memoria ya no está en el turno; `mem_state`=0, `mem_query`=None salvo recall).

Números en `zaelar-model-benchmarks.md §4 (V2-011)`. Objetivo cumplido: regresión de memoria eliminada, p50 ~1 s
en memory/widget, recall conservado, medido (no intuición).
