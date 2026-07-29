---
id: V2-020
title: Rendimiento — hot-tier en RAM (estado + corto) + evaluación Rust, guiada por perfilado
epic: v2-colmena
status: backlog
priority: low
owner: ricart
modules: [memory, nucleo, voice]
depends_on: [V2-011, V2-013]
wall_order: 20
created: 2026-07-10
updated: 2026-07-10
---

## Goal

Planteamiento a FUTURO (NO implementar ahora — no sobrecomplicar). Capturar dos ideas del operador sobre velocidad
para que no se pierdan y se aborden **cuando el perfilado lo justifique**, no por intuición:

1. **Parte de la memoria en RAM** (estado + corto plazo) para optimizar la velocidad de lectura.
2. **Piezas críticas (cerebro/memoria) en Rust** en lugar de Python, si la latencia lo pide.

## Diagnóstico ACTUAL (por qué NO es urgente)

- **El hot path de lectura YA es RAM.** El bloque de memoria del turno (ESTADO + CORTO + perfil durable) se compone
  FUERA del turno y se **cachea en proceso** (`nucleo/flash/memory_cache._compose`, dict de Python en RAM, TTL +
  invalidación por `memory.updated`). El turno lee un string ya compuesto desde RAM — NO toca SQLite. Además SQLite
  con **WAL + page cache del SO** mantiene las páginas calientes (estado = 1 fila; `recent_short` = scan indexado
  diminuto) en RAM de facto. La lectura de estado/corto es µs HOY.
- **El p50 del turno (~1.1s, V2-011) lo domina el MODELO, no Python ni SQLite**: TTFT del LLM del FlashBrain (red)
  + embeddings (Ollama) + inferencia STT/TTS. Esas piezas YA corren en C/Rust/Metal (sqlite-vec=C, mlx-audio=Metal,
  mlx-whisper=Metal, ollama=Go/C, SDKs de LLM). Python es **glue orquestando I/O asíncrono**, no un hot loop de CPU.
- **No hay hot loop de CPU en Python** en la ruta caliente: el vector-search lo hace sqlite-vec (C); el scoring del
  retriever (α·rel+β·rec+…) es aritmética trivial sobre ≤40 filas. Reescribir glue en Rust NO movería el p50 porque
  el tiempo vive en inferencia de modelos + red.

## Cuándo SÍ tocaría (disparadores medibles)

- **Hot-tier en RAM (estado+corto)**: si el perfilado muestra SQLite en la ruta caliente (hoy no), aplicar primero
  lo BARATO — `PRAGMA mmap_size`, `PRAGMA temp_store=MEMORY`, o un `:memory:` con snapshot a disco — antes que una
  estructura RAM propia. Medir con el desglose `timing` de `/debug`.
- **Rust (pyo3, pieza aislada, NO reescritura)**: solo si aparece un **hot-spot de CPU medido** — p. ej. (a) el
  retriever/scoring sobre **millones** de recuerdos, (b) **muchas sesiones concurrentes por máquina** (pivote SaaS
  cloud) donde el GIL/overhead de Python sea el cuello, (c) procesamiento de texto pesado por turno. Se aislaría ESA
  pieza como extensión Rust (`pyo3`/`maturin`), conservando LiveKit Agents + el ecosistema de voz en Python. NUNCA
  reescribir voice/nucleo enteros: fragmentaría el stack y perdería la integración con LiveKit Agents/mlx/ollama.

## Regla

Guiado por PERFILADO, no por intuición: **medir → aislar el hot-spot → optimizar esa pieza** (config SQLite → RAM →
extensión Rust, en ese orden de coste). La regla de oro de V2-011 (LLM al escribir, lecturas directas µs) ya
mantiene el turno libre de I/O pesado; este trabajo es un escalón MÁS, no un rescate.

## Tareas (backlog, sin fecha)

- [ ] T160 — Perfilado del hot path de memoria (¿SQLite aparece? ¿dónde van los ms?) con el desglose `timing`.
- [ ] T161 — Si procede: tuning SQLite (`mmap_size`/`temp_store`) o hot-tier RAM para estado+corto, medido antes/después.
- [ ] T162 — Reevaluar Rust (pyo3) SOLO ante un hot-spot de CPU medido o el pivote a SaaS multi-sesión; aislar la pieza, no reescribir.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
