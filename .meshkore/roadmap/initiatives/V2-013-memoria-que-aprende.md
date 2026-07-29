---
id: V2-013
title: Memoria que APRENDE — el CORAZÓN de escritura (LLM local) cura cada dato como PÍLDORA (dato+metadatos), decide dónde/importancia y no duplica
epic: v2-colmena
status: next
priority: critical
owner: ricart
modules: [nucleo, memory, voice]
depends_on: [V2-002, V2-003, V2-006]
wall_order: 13
created: 2026-07-09
updated: 2026-07-10
---

## Goal

La memoria guarda pero **no aprende**: escribe CUALQUIER frase del chat como event crudo (importancia plana 0.3),
el `state` está vacío, no deduplica, no evalúa importancia. Hay que construir el **CORAZÓN de escritura**: un
**procesador de memoria** (LLM **LOCAL**, Ollama/qwen — gratis) que, por cada dato que entra, lo **transforma en el
dato/concepto preciso** y decide **si lo guarda, DÓNDE y con qué importancia**, y **no duplica** (si el concepto ya
existe, refuerza el peso en vez de crear otra fila).

## Principio rector (aclaración del operador, 2026-07-10) — LLM al ESCRIBIR, queries directas al LEER

> "La inserción tiene que pasar por un modelo para decidir CÓMO se guarda el dato, cómo se transforma el texto en el
> dato preciso. Pero al **consumir** quiero queries directas: meter latencia de modelo cada vez que accedo a la
> memoria ralentiza todo. El **estado** se captura entero en el prompt siempre (es pequeño, es abrir los ojos). La
> **memoria rápida** se consulta con algo super-rápido y sobre-incluye datos por defecto. La **memoria grande** ahí
> sí puede permitirse esperas (qué pasó el mes pasado, dónde vivía Bartolo, mensajes de hace 4 meses) — no requiere
> reacción inmediata."

Esto fija dos invariantes de latencia **complementarios** al de V2-011:

1. **ESCRIBIR = con LLM, SIEMPRE off-hot-path** (async, en cola). El turno de voz nunca espera al procesador. Que sea
   de baja latencia para que el mapa refleje la realidad pronto, pero nunca en el event loop.
2. **LEER = queries DIRECTAS, sin LLM en el camino**, con tres velocidades:
   - **ESTADO** — se inyecta ENTERO en cada prompt (µs, cero query). "Abrir los ojos": quién soy, quién es el
     interlocutor, mi objetivo/proyecto actual, dónde estoy. Pequeño a propósito.
   - **CORTO / memoria rápida** — sistema super-rápido que **sobre-incluye** (lee el working set entero, sin
     retriever, sin LLM). Mejor traer de más que perder tiempo afinando.
   - **LARGO / memoria grande** — retriever directo vec+FTS→RRF (ms). Es la única capa donde **se toleran esperas
     más largas** (tareas: recall de sesiones viejas, "cómo hicimos X", un mensaje de hace meses) → aquí el LLM
     PUEDE entrar para reformular/rerankear, pero **solo off-hot-path** (SlowBrain / tareas), nunca en el turno.

## Decisión de diseño — la memoria es una PÍLDORA (dato canónico + metadatos), no texto crudo

El operador dejó abierto "¿texto o píldoras con metadatos?". **Decisión (2026-07-10): píldoras.** Cada recuerdo es
un **enunciado canónico** (bueno para embedding + FTS + legible en el visor) MÁS un **envoltorio de metadatos**:

- Columnas ya existentes: `level · kind · importance · weight · ttl_days · pinned · valid · superseded_by · created
  · updated`.
- **NUEVO `slot TEXT`** (indexado) — clave canónica del hecho singular (`operator.name`, `operator.location`,
  `goal.current`, `project.current`, `car`…). Da **supersede EXACTO sin LLM ni búsqueda semántica**: al insertar un
  hecho con `slot`, el hecho vigente con ese mismo `slot` pasa a `valid=0, superseded_by=nuevo` ("el más reciente
  MANDA"). Ancla también el grafo de conceptos.
- **NUEVO `meta TEXT` (JSON)** — píldora libre: `{entity, attribute, source, confidence, said_at, …}`. No toca el
  hot path (se selecciona junto al resto); alimenta el visor y el grafo. Futuro-proof sin re-migrar por cada campo.

El LLM del procesador **destila** el turno crudo → 0..N píldoras: `me llamo Ricard, vivo en Barcelona y trabajo en
zaelar` → 3 átomos con sus `slot`/`state_patch`, en vez de una fila de texto con la frase entera. Embedding y FTS
siguen operando sobre el `text` canónico → el retriever no cambia.

## Encaje con lo YA construido (fit-gap, actualizado 2026-07-10)

| Pieza del diseño del operador | Estado hoy |
|---|---|
| Embeddings LOCALES por recuerdo (búsqueda por significado) | **YA** (`memory/writer.py::insert_memory` → `vec_memories`) |
| "Si el dato ya existe, sube su PESO en vez de duplicar" | **Primitiva YA** (`writer.reinforce`) — falta LLAMARLA al insertar (dedup) |
| El peso perdura / decae si no se usa | **YA** (`consolidator.decay`; acceso resetea) |
| Borrar lo menos relevante cuando hay demasiado | **YA** (`consolidator.evict` por peso, respeta pinned) |
| Estado + grafo de conceptos | **Substrato YA** (`state`, `edges`, `link()`) — vacíos, nadie los puebla |
| **Lectura en 3 velocidades** (ESTADO cache · CORTO entero · LARGO query) | **YA** (V2-011 + T146). Confirmado por el operador — **no se toca** |
| **Procesador LLM que DESTILA + decide DÓNDE/DESCARTAR/importancia** | **FALTA** (hoy `nucleo.py` escribe event crudo 0.3 a ciegas) |
| **Memoria como PÍLDORA** (`slot` + `meta`) | **FALTA** (schema v1 no tiene esas columnas) |
| **Prompt DINÁMICO de importancia** (según mi situación) | **FALTA** |
| **Dedup SEMÁNTICO al insertar** (no literal) → reforzar | **FALTA** (embed + vec-search + reinforce están; falta cablearlas) |
| **Supersede por slot** ("el nombre nuevo manda") | **FALTA** (`writer.supersede` existe; falta invocarla por slot) |

Invariante confirmado por el operador: **insert LENTO (destila, embebe, dedup, decide con LLM), query RÁPIDO
(directo, sin LLM)**.

## Qué se construye

1. **PÍLDORA — schema v2** (`memory/schema.py` + migración en `memory/db.py`, `SCHEMA_VERSION=2`): añade `slot TEXT`
   (+ índice) y `meta TEXT` (JSON) a `memories`. ALTER idempotente, no destructivo.
2. **El CORAZÓN — procesador LLM local** (`nucleo/memory_agent` ampliado): por cada turno del operador, **heurística
   barata primero** (trivia/comando → DESCARTAR; perfil obvio por regex → ESTADO) y **LLM LOCAL solo para el juicio
   dudoso** (hoy TODO lo no-matcheado caía a `mid/0.5` a ciegas). El LLM devuelve átomos:
   `{text, dest: state|short|long|discard, kind, importance, ttl_days, slot, state_patch}`. Off-hot-path (la vía
   `ingest_utterance` ya es fire-and-forget), OpenAI-compatible (mismo patrón que `connectors/messaging/triage.py`),
   modelo por env `MEM_PROCESSOR_MODEL` (default `qwen2.5:3b` local). **Reemplaza el write crudo** de `nucleo.py`.
   Mantiene los pulsos de observabilidad (V2-014).
3. **CORTO limpio como buffer conversacional**: el turno sigue alimentando el working set de CORTO (para la ruta de
   lectura entera de T146) pero como `kind='conv'` con **TTL corto** que auto-caduca — NO como recuerdo durable 0.3.
   El procesador decide aparte qué gradúa a LARGO.
4. **ESTADO = la PILA curada**: el corazón decide qué gana hueco (nombre del interlocutor, objetivo/proyecto actual,
   ubicación, equipo), con fecha de alta (en la traza `long/pinned` + `meta.said_at`) y bajas al cambiar. `state`
   sigue plano-y-rápido (scalars) para el prompt; `memory_cache` lo sirve instantáneo; persiste entre sesiones.
5. **Supersede por SLOT (dedup exacto, sin LLM)**: al insertar con `slot`, el vigente con ese slot → `valid=0`.
6. **Dedup SEMÁNTICO al insertar → reforzar** (para lo SIN slot): embed + vec-search por significado; si supera el
   umbral → `reinforce()` en vez de duplicar. Umbral configurable, calibrado con el tester.
7. **Prompt DINÁMICO de importancia**: el juicio se compone desde el ESTADO/situación (estudio derecho → derecho
   importa; investigo pájaros → pájaros importa). Relevancia con contexto, no plana.
8. **Grafo de conceptos**: al guardar, enlazar entidad↔concepto en `edges` (deporte→pádel); el retriever expande.

> El **aislamiento del tester** y la **consolidación CORTO→LARGO por TTL/peso** + limpieza de la BD contaminada se
> mueven a **V2-019** (housekeeping/ciclo de vida) para no mezclar "aprender a escribir" con "el sueño y la higiene".

## Tareas

- [ ] T123 — EL CORAZÓN: procesador LLM LOCAL (Ollama/qwen, off-hot-path, OpenAI-compatible) que DESTILA cada turno en píldoras y decide DESCARTAR/ESTADO/CORTO/LARGO + importancia + TTL. Heurística barata para lo obvio + LLM solo para lo dudoso. Reemplaza el write crudo. Mantiene pulsos de observabilidad (V2-014).
- [ ] T124 — ESTADO = la PILA curada por el LLM: nombre del interlocutor, objetivo/proyecto actual, ubicación…, con fecha de alta y bajas; `memory_cache` la sirve instantánea; persiste entre sesiones.
- [ ] T130 — PÍLDORA (schema v2): `slot TEXT` (+índice) + `meta TEXT` (JSON) en `memories`; migración idempotente no destructiva (`SCHEMA_VERSION=2`). El visor y el grafo consumen `meta`.
- [ ] T131 — CORTO como buffer conversacional LIMPIO: el turno alimenta CORTO como `kind='conv'` con TTL corto (auto-caduca), no como recuerdo durable 0.3. Preserva la ruta de lectura entera de T146.
- [x] T146 — CORTO como RUTA DE LECTURA entera: `memory.recent_short()` (lectura directa µs, sin embeddings) + `memory_cache` lo enchufa ENTERO al prompt. `done` 2026-07-09.
- [x] T125 — Dedup: **supersede por SLOT** (exacto, sin LLM) para hechos singulares + **dedup SEMÁNTICO** (embed+vec-search) para lo sin slot → `reinforce()` si ya existe; umbral configurable. `done` 2026-07-10 (umbral 0.60 con embeddinggemma; validado con el test bot: 3 fraseos del cumpleaños → 1 recuerdo reforzado).
- [x] T126 — Grafo de conceptos (primer corte, 2026-07-10): el CORAZÓN etiqueta cada píldora durable con 1-3 `concepts` ligeros (salud/finanzas/deporte…); el writer crea/reusa un NODO-concepto (`kind='concept'`, recuperable por FTS/vector) y enlaza píldora↔concepto en `edges` (bidireccional). En la lectura, una query de CATEGORÍA ("¿qué hago de deporte?") casa el nodo por FTS y `graph_expand` (con `concept_discount` alto, conceptos procesados primero) aflora el cluster — SIN LLM. Validado por el bot (BATCH_16 #152) + smoke test (salud→operación+alergia+correr, sin solape léxico → ataca T150). PENDIENTE de pulir: consistencia de la etiqueta del LLM (mismo hecho a veces cae en ocio vs deporte), aristas temporales `antes/después` (atacaría T151), medición de precisión con más datos.
- [ ] T143 — Prompt DINÁMICO de importancia: se compone desde el estado/situación del operador; evalúa relevancia con contexto, no plano.
- [ ] T148 — CORTO = memoria RECIENTE UNIFICADA (corto y recencia = mismo módulo, decisión del operador): cada turno con substancia deja una traza COMPRIMIDA (dato/tema, NUNCA la frase entera) en `level='short'`; leer el corto ENTERO al prompt responde a la vez "¿qué acabo de decir?" y "¿de qué hemos hablado?". Sustituye el buffer verbatim `kind='conv'` (par crudo) por gists comprimidos. La recencia **NO va en `state`** (el estado es permanente). El decaimiento de detalle por antigüedad = V2-019 T149.
- [ ] T128 — Verificación: dar datos por voz → reiniciar → recuerda (estado poblado, con fecha); repetir el nombre de 3 formas → 1 hecho reforzado (no 3 duplicados) por significado; basura descartada; CORTO entero en el prompt; query sigue rápido (sin LLM); + **pasar la revisión de alineación**.

## Aceptación

- Digo mi nombre/ubicación; tras reiniciar zaelar lo recuerda (estado poblado, con fecha de alta).
- Digo el nombre de 3 formas distintas → UN solo hecho, con peso reforzado (no 3 duplicados) — dedup por SIGNIFICADO/slot.
- Charla sin valor se DESCARTA (no infla la memoria); lo relevante a mi situación se guarda con más importancia.
- El **query sigue siendo rápido (queries directas, cero LLM en la lectura)**; el procesamiento de escritura no bloquea la voz.
- El recuerdo es una PÍLDORA (dato canónico + metadatos), legible y puntuada en el visor.

## Riesgos

- El LLM local en el camino de escritura debe ir async/en cola (nunca en el turno) — no reintroducir latencia (V2-011).
- **Nunca meter LLM en la LECTURA** (regla del operador): la lectura son queries directas; el LLM de recall solo
  off-hot-path para tareas del LARGO.
- Dedup con umbral mal calibrado → fusiona cosas distintas o duplica; calibrar con el tester + umbral configurable.
- Prompt dinámico de importancia: evitar que "todo es importante"; presupuesto/umbral y el consolidador (V2-019) podan.
- El modelo local puede tardar/fallar → el procesador debe degradar a la heurística barata (fail-open, best-effort).

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T146 + bug del nombre — el CORTO no se inyectaba (solo se buscaba, poco fiable). Fix: `memory.recent_short(limit=30, max_chars=1800)` (µs, sin embeddings) + `memory_cache._compose` lo cachea y lo enchufa ENTERO como bloque "Conversación reciente". Verificado: 11 tarjetas · 1684 chars.
- 2026-07-10 · T125 (dedup) — supersede por SLOT (exacto) + DEDUP SEMÁNTICO al insertar (`memory/writer._find_semantic_dup`: embed + vec-search, distancia L2 ≤ 0.60 con embeddinggemma → `reinforce` en vez de duplicar; durable+sin-slot; `MEM_SEMANTIC_DEDUP`/`MEM_DEDUP_MAX_DIST`). Validado por el test bot (tanda 4): "Mi cumpleaños es el 12 de marzo" dicho de 3 formas → 1 recuerdo reforzado. 356 tests sin regresión.
- 2026-07-10 · Reajuste de diseño con el operador — LLM al ESCRIBIR / queries directas al LEER; memoria como PÍLDORA (dato canónico + `slot` + `meta`); tres velocidades confirmadas (ESTADO entero, CORTO sobre-incluye, LARGO tolera esperas y es la única capa donde el LLM puede entrar off-hot-path). Aislamiento del tester + consolidación se mueven a V2-019.
</parameter>
</invoke>
