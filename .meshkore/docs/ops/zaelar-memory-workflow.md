---
title: Zaelar Memory Change Workflow
category: ops
updated: 2026-07-14
owner: ricart
status: current
---

# Workflow de cambios en la MEMORIA — "pasa el workflow de memoria"

**Disparador:** cuando el operador dice **"pasa el workflow de memoria"** (o "revisa/cierra el cambio de memoria"),
o cuando TÚ mismo acabas de tocar algo ESTRUCTURAL de la memoria y vas a darlo por cerrado — ejecuta esta checklist
antes de decir que has terminado.

Existe porque un cambio en la memoria **irradia**: el substrato lo escriben y lo leen muchas piezas (FlashBrain,
agente de memoria, widgets, conectores, reset, episódica, visor). Cada vez que cambia el schema, el CORAZÓN de
escritura, el retriever o las velocidades de lectura, hay que verificar que **todas esas interacciones —al guardar Y
al leer— siguen alineadas**, documentarlo en varios sitios, testear y commitear. Este workflow lo captura de una vez
para no re-investigar "a quién afecta" cada vez.

> Es la especialización para `memory/` de [[zaelar-change-protocol]] / [[zaelar-docs-sync]] / [[zaelar-alignment-review]].
> Estado actual del subsistema: [[zaelar-memory]] (fuente de verdad del diseño). Diseño en curso: V2-013 (corazón de
> escritura) y V2-019 (sueño + aislamiento del tester).

---

## 0. ¿Aplica este workflow? (filtro de alcance)

Aplica si el cambio altera algo que **cualquier escritor o lector de la memoria tiene que respetar**. Sí a
cualquiera de estas → workflow completo:

- **Schema / píldora** — columnas de `memories` (`slot`/`meta`/…), `state`, `edges`, `episodic`, `journal`;
  `memory/schema.py` + migración en `memory/db.py` (`SCHEMA_VERSION`).
- **El CORAZÓN de escritura** — `nucleo/mem_processor.py` (procesador LLM: prompt, modelo, salida de píldoras) o
  `nucleo/memory_agent.py` (`classify`/`ingest_utterance`/`remember`/`_write_atom`/`compose_context`).
- **Writer / cola / slots** — `memory/writer.py` (insert, supersede/dedup por slot, reinforce, delete),
  `memory/queue.py`, y el **registro canónico `memory/slots.py`** (añadir/renombrar un slot o un alias afecta a
  writer + memory_agent + prompt del procesador A LA VEZ — es la gracia: un solo sitio).
- **Retriever / scoring** — `memory/retriever.py` (vec/FTS/RRF, pesos α/β/γ/δ, graph_expand), `memory/embeddings.py`.
- **Velocidades de lectura** — `memory.state()`, `memory.recent_short()`, `memory.query()`; y el cacheo del
  FlashBrain `nucleo/flash/memory_cache.py` + `nucleo/flash/prompt.py` (`needs_recall`/`compose_recall`).
- **Consolidador / olvido** — `memory/consolidator.py` (promote/dedup/decay/evict) y su disparo desde `nucleo/loop.py`.
- **Observabilidad / visor** — `memory/api.py::map`, `GET /api/memory/map`, el puente SSE `memory.updated` en
  `server/__init__.py`, `frontend/app/components/MemoryMap.js`, filas `kind=memory` en `DebugPanel.js`.

**NO lo dispara**: un comentario, un renombrado interno, un ajuste que no toca el contrato de datos ni ninguna de las
interacciones de arriba. Sigue como siempre.

---

## 1. Mapa de impacto — "si tocaste esto, revisa/actualiza aquello"

### 1a. ESCRITORES de la memoria (todos por la fachada `memory/api.py`, async — nunca la BD directa)

| Escritor | Dónde | Qué revisar tras un cambio |
|---|---|---|
| **CORAZÓN — turno del operador** | `nucleo/memory_agent.ingest_utterance` → `mem_processor.process` (LLM) / `classify` (fail-open) → `remember`/`_write_atom` | Que las píldoras nuevas respeten el schema (`slot`/`meta`/`ttl`); que el fail-open siga funcionando sin Ollama; cableado en `voice/engine/llm/providers/nucleo.py` (fire-and-forget). |
| **Buffer conversacional de CORTO** | `voice/engine/llm/providers/nucleo.py` (`memory.write(kind='conv', level='short', ttl_days=…)`) | Que siga siendo EFÍMERO (TTL) y NO durable; que alimente `recent_short`; que no re-infle la memoria (adiós al write crudo 0.3). |
| **SlowBrain / agentes** | `nucleo/memory_agent.remember({text,kind[,slot,meta]})` (único escritor sancionado del SlowBrain); `nucleo/dispatch.py` | Que pase `slot` para hechos singulares; que no bloquee. |
| **Brain Workers (V2-036/38, EXTERNOS)** | `hbmem remember` (`nucleo/mem_cli.py`) → `POST /api/memory/remember` (`memory/server_api.py`) → `memory_agent.remember_external` | Que exija el token por-tarea (headers de mem_cli); que aplique gates P0a + veto de slots de identidad + `meta.source="worker:<id>"`; que NUNCA toque `state`; que el Bash del worker siga acotado a los CLIs (`dispatch._tools_for` sin "Bash" pelado). Resultado de sesión: solo si `ok` (`workers/session._deliver`). |
| **Contexto del worker al ARRANCAR** | `nucleo/dispatch._compose_context` → `memory_agent.compose_context` | Que el bloque «CONTEXTO DE MEMORIA» del prompt del worker NO quede vacío (regresión del typo `compose_task_context`, cazada en la auditoría 2026-07-14; guard en `nucleo/test_dispatch.py`). |
| **Reset duro** | `nucleo/reset.py` (`set_state({trabajo_interrumpido})` + `memory.write(level='short')`) | Que el congelado a ESTADO + registro a CORTO sigan válidos con el schema nuevo. |
| **Contexto de UI vivo → ESTADO** | Canvas (frontend autoritativo): `POST /api/canvas/state` (`server/voice_api.py`) → `set_state({open_widgets})`; tareas en marcha: `nucleo/dispatch.py::_emit_activity` → `set_state({activity})` | Que el reporte normalice ids de instancia y dedup; que `set_state` NO pise otros campos (patch superficial); que dispare `memory.updated` para refrescar prompt+mapa. |
| **Widgets / ciclo de vida** | `widgets/lifecycle.py` (`record_created`/lápida de borrado) | Que las trazas de alta/baja se escriban por la fachada; regla de oro "nunca se borra el histórico". |
| **Conectores / mensajería** | `connectors/messaging/store.py` (`memory.write(kind='msg', level='short')`) | Que el volcado siga por la fachada; `slot` si el dato es singular. |
| **Episódica (paste/drop)** | `memory/episodic.py` ← `memory/server_api.py` (`write_episode`) | Que el resumen buscable siga indexándose en `memories` (vec/fts). |

### 1b. LECTORES de la memoria (directos, SIN LLM en el camino — regla de oro V2-013/V2-011)

| Lector | Dónde | Qué revisar |
|---|---|---|
| **ESTADO (µs, siempre en el prompt)** | `memory.state()` → `nucleo/flash/memory_cache._compose` (incl. contexto de UI vivo: `open_widgets`/`activity`) | Que `_compose` pinte los campos nuevos (listas incluidas); invalidación por `memory.updated` intacta. |
| **Mapa de memoria (visor)** | `memory.map()` → `MemoryMap.js::stateItems` (columna ESTADO) | Que los campos nuevos del ESTADO se pinten en el mapa (`stateItems` es whitelist explícita, hay que añadir la fila). |
| **CORTO (µs, working set entero)** | `memory.recent_short()` → `memory_cache._compose` (bloque "Conversación reciente") | Que siga leyendo directo (sin embeddings) y acotado (limit/max_chars). |
| **LARGO (ms, bajo demanda, off-loop)** | `nucleo/flash/prompt.compose_recall` → `memory.query` → `retriever.search` → **reranker** (`memory/rerank.py`, V2-030, fail-open); `asyncio.to_thread` + `needs_recall` | Que NUNCA entre al event loop; que el scoring siga coherente; que el reranker siga fail-open. |
| **Brain Workers (lectura serial)** | `hbmem recall` → `POST /api/memory/recall` → `memapi.query()` | Que siga read-only y filtre `untrusted` (lo hace el retriever); que nunca abra la BD. |
| **SlowBrain (off-hot-path, puede LLM)** | `nucleo/memory_agent.compose_context` | Única cara que puede usar un LLM de recall — verificar que sigue off-hot-path. |
| **Visor / diagnóstico** | `memory.map()` → `GET /api/memory/map` → `MemoryMap.js` | Que exponga las columnas nuevas (`slot`/`meta`); tintado por `memory.updated` intacto. |

> **Regla de oro de latencia (repetida porque es fácil romperla):** **LLM al ESCRIBIR (off-hot-path), queries
> DIRECTAS al LEER.** Ningún cambio puede meter un LLM ni I/O de memoria SÍNCRONO en el turno de voz.

---

## 2. Migración de schema (si tocaste columnas/tablas)

- Sube `SCHEMA_VERSION` en `memory/schema.py` y añade la migración **ALTER idempotente y NO destructiva** en
  `memory/db.py::_migrate` (SQLite no tiene `ADD COLUMN IF NOT EXISTS` → comprueba `PRAGMA table_info` antes).
- Los índices que dependen de columnas nuevas se crean **después** del ALTER (nunca en `BASE_DDL`, que corre antes).
- **Verifica ambas rutas**: BD nueva (desde `BASE_DDL`) y BD vieja existente (v_anterior → v_nueva) — que migra y
  **no pierde datos**. Prueba con una BD simulada de la versión anterior.

---

## 3. Documenta — la regla de oro es SIEMPRE tres sitios, nunca dos de tres

1. **`zaelar-memory.md`** (fuente de verdad): §Schema, §El CORAZÓN de escritura, §Lectura en TRES velocidades,
   §Cómo la USA el resto del sistema, §Observabilidad — lo que hayas tocado.
2. **`CLAUDE.md`**: la decisión clave "Memoria central" + el bullet del módulo `memory/`/`nucleo/` + (si es un
   invariante nuevo) su regla dura. **Explica cómo se usa la memoria desde otros módulos** — es mandatorio que esté
   al día (guardar Y leer).
3. **Diagrama público** `web/src/pages/technology/memory.astro` + `web/src/lib/diagrams/memory.ts` (antes
   `frontend/pages/architecture.html` pestaña Memoria, retirado el 2026-07-24 — paso MANUAL, ningún workflow lo
   sincroniza solo): piezas + **modelos en uso** (el modelo del procesador de escritura, embeddings, etc.) +
   coste (local/gratis vs nube), solo si el cambio es significativo de cara a fuera. Si el operador ve un
   modelo/topología obsoleto en `/technology`, es un fallo de este workflow.
4. **Roadmap**: marca la tarea `done` + una línea en la Bitácora de su iniciativa (V2-013/V2-019).

---

## 4. Tests — no solo revisión de código

- `.venv/bin/pytest memory/ nucleo/ -q` (con `ZAELAR_EMBED_BACKEND=hash` para no depender de Ollama).
- Añade/ajusta tests para lo que cambiaste: schema/migración (`memory/test_pill_slot.py`), corazón
  (`nucleo/test_memory_agent.py`), writer/retriever/consolidador.
- **Determinismo**: el procesador LLM se apaga en tests con `MEM_PROCESSOR=0` (ruta heurística); para ejercitar el
  LLM, mockea `mem_processor.process`.
- Si tocaste escritores fuera de `memory/` (mensajería, widgets, reset), corre también SU suite.

---

## 5. Reinicia y verifica en vivo (si tocaste `.py`)

- `make run` y comprueba en el **visor 🧠** (cuenco del orbe) + la **columna ◷** que la memoria se forma como
  esperas (píldoras curadas, ESTADO poblado, nada de basura cruda). El flujo de eventos `kind=memory` debe reflejar
  el cambio.

---

## 6. Commit / push — regla dura

- `git add -A && git commit` con co-autoría; mensaje que ancle la tarea (V2-0NN · Txxx). **NO push** sin OK explícito
  del operador.

---

## 7. Cierra con la revisión de alineación

Ejecuta [[zaelar-alignment-review]]: **código ↔ CLAUDE.md ↔ zaelar-memory.md ↔ diagrama Memoria de `/technology`
↔ roadmap ↔ tests** deben contar la MISMA historia (estado actual, sin dirty/legacy). Es la puerta de calidad final.

---

## Resumen para el operador (al terminar)

Reporta en 4 líneas: **(1) qué cambió** en la memoria; **(2) qué escritores/lectores revisé** y si siguen alineados;
**(3) migración + tests** (verde/rojo, nº); **(4) docs + diagrama** actualizados y alineación pasada. Si algo quedó
abierto (calibración, un consumidor por migrar), dilo explícitamente.
