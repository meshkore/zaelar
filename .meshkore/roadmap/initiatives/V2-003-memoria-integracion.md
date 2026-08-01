---
id: V2-003
title: Memoria — integración (files/→episódica · migración Hermes→DB · widgets escriben · estado vivo)
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [memory, files, widgets, server]
depends_on: [V2-002]
wall_order: 3
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09T08:41:00.102Z
commit_sha: ab6d2326cdb14469cb50a2e07f737c1f7018a5d7
---
## Goal

Enchufar la memoria al resto del sistema (aún sin cerebro v2): **plegar `files/` dentro de `memory/`** como capa
episódica, **sembrar** la memoria con lo que ya sabía Hermes del operador, y hacer que **los widgets escriban**
sus datos durables a la memoria central. Al terminar, la memoria está viva y poblada, lista para que FlashBrain
(V2-004) la consuma.

## Qué se construye

### 1. `files/` → capa episódica de `memory/`
- El almacén de bytes de `files/uploads/` pasa a un directorio de datos de memoria (episódica); el módulo `files/`
  se retira como módulo independiente (queda su función absorbida). `POST /api/files/upload` se re-cablea a
  `memory.write_episode(bytes, mime)` → guarda el binario + genera resumen embebido buscable.
- Carga lazy: el binario/PDF solo se materializa bajo orden ("consulta el informe") o si el retriever lo elige.
- Retirar la nota `[SISTEMA]` de ruta absoluta (era para las tools de fichero de Hermes) — ahora el resumen ya
  está en la memoria y lo encuentra el retriever. (El cerebro v2 no tiene tools de fichero de Hermes.)

### 2. Migración/siembra Hermes → memoria
- Importador one-shot best-effort: `~/.hermes/memories/USER.md` + `MEMORY.md` → filas en `state` + `memories`
  (hechos/preferencias). Idempotente (re-ejecutable sin duplicar). NO toca `~/.hermes/` (solo lee).
- Es una siembra, no una dependencia: si no hay Hermes instalado, arranca vacío sin error.

### 3. Widgets escriben a memoria
- Contrato: un widget que produce datos durables llama a `memory.write(...)` (async, cola). Empezar por
  `mensajeria` volcando lo entrante (los mensajes) como `kind='msg'` nivel `short`.
- `store.save()` de widgets sigue emitiendo su SSE de UI; ADEMÁS lo durable va a memoria. (El store por-widget
  se mantiene para el estado de UI; la memoria es para el recall del cerebro.)
- Señal `memory.updated` por el bus → el desktop refresca si procede.

## Tareas

- [x] Mover el almacén de bytes de `files/uploads/` al data-dir de memoria episódica; migración perezosa de lo existente.
- [x] Re-cablear `POST /api/files/upload` → `memory.write_episode` (bytes + resumen embebido). Test de subida→búsqueda.
- [x] Retirar el módulo `files/` (o dejar shim que delega en memoria) + quitar la nota `[SISTEMA]` de ruta.
- [x] Importador `memory/seed_from_hermes.py` (one-shot, idempotente, solo-lectura de ~/.hermes) + test.
- [x] `mensajeria` vuelca lo entrante a `memory.write` (kind msg) — sin romper su store de UI.
- [x] Documentar en `zaelar-modules.md` que memoria absorbe files/ y que los widgets escriben a memoria (doc-sync).
- [x] Actualizar `cluster.yaml`: retirar `files` como módulo (su descripción pasa a `memory`).

## Aceptación

- Pego un archivo/imagen → aparece un resumen buscable por `memory.query`; el binario carga lazy.
- `memory.state()` devuelve el perfil del operador sembrado (nombre, idioma es, reglas de trato) si había Hermes.
- Un mensaje entrante de mensajería queda como recuerdo `msg` recuperable.
- Clone sin Hermes: arranca con memoria vacía, sin error.

## Riesgos

- Perder los ficheros ya subidos en la migración → migración perezosa + no borrar el origen hasta verificar.
- El formato de `~/.hermes/memories/*` es texto libre → el importador es best-effort, no crítico.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T53 — `memory/episodic.py` absorbe los BYTES: `episodic_dir()` (bajo `memory/_data/`, respeta `ZAELAR_DB`) sustituye a la bandeja plana `files/uploads/`; `write_episode(data, filename, mime)` guarda el binario (escritura atómica tmp+rename, colisiones resueltas) + genera un RESUMEN buscable best-effort (nombre+tipo, y para texto legible un extracto) — la sumarización semántica queda al agente de memoria (V2-006). `list_episodes()` (reemplaza `files.store.list_files`) y `migrate_inbox()` (migración PEREZOSA, idempotente por marker `.migrated.json`, NO destructiva). Fachada en `memory/api.py` (`write_episode`/`list_episodes`/`migrate_inbox`, emiten `memory.updated`). 6 tests verdes (`memory/test_episodic_bytes.py`).
- 2026-07-09 · T54 — subida re-cableada a la memoria: `memory/server_api.py` (nuevo) sirve `POST /api/files/upload` (→ `memory.write_episode`) y `GET /api/files` (→ `list_episodes`); `server/__init__.py` importa el router desde ahí y **monta la memoria en el lifespan** (`memory.api.start()` = consumidor único de la cola de escritura en el loop del server + `migrate_inbox()` al arrancar; `stop(drain=True)` al apagar; flag `ZAELAR_MEMORY`, def 1). Verificado EN VIVO: subida de un .txt → aparece en `/api/files` con resumen, bytes en `memory/_data/episodic/`, y `memory.query('Wallapop')` lo recupera. 3 tests verdes (`memory/test_server_api.py`, subida→búsqueda + listado + 413).
- 2026-07-09 · T55 — `files/` RETIRADO como módulo: `files/store.py` y `files/server_api.py` quedan como **shims de compatibilidad** que delegan en `memory.api` (por si un importador externo aún los usa). **Nota `[SISTEMA]` de ruta absoluta ELIMINADA** — era para las tools de fichero de Hermes; ahora el resumen ya vive en la memoria y lo encuentra el retriever del cerebro por su cuenta. Import de los shims verificado OK.
- 2026-07-09 · T56 — `memory/seed_from_hermes.py`: importador one-shot, **idempotente y SOLO-LECTURA** de `~/.hermes/memories/{USER.md,MEMORY.md}` (secciones `§`) → `state` (nombre + idioma por heurística, sin pisar lo editado a mano) + `memories` **pinned** (`kind='pref'` USER, `kind='fact'` MEMORY, `level='long'`). Dedupe por coincidencia exacta de texto → re-ejecutar no duplica. Si no hay Hermes, no hace nada y no falla (siembra, no dependencia). 4 tests verdes (`memory/test_seed_from_hermes.py`: siembra estado+recuerdos, idempotencia, pinned+buscable, sin-Hermes sin error).
- 2026-07-09 · T57 — **widgets escriben a memoria**: `connectors/messaging/store.py::upsert_items` vuelca cada mensaje entrante NUEVO a `memory.write(kind='msg', level='short')` (fire-and-forget por la cola; importancia 0.6 si dirigido_a_mí, 0.4 si no; salta cuerpos vacíos) — **sin tocar el store de UI** (`save()` sigue emitiendo su SSE; el volcado va DESPUÉS y es best-effort). Es el primer caso del contrato "un widget con datos durables → `memory.write`". 3 tests verdes (`tests/connectors/unit/messaging/test_memory_dump.py`: entrante buscable como `msg`, dedupe no duplica, cuerpo vacío no entra).
- 2026-07-09 · T58 — doc-sync: banner V2-003 al frente de `§Files module` de `zaelar-modules.md` (files/ plegado en la capa episódica de memory/ — bytes al data-dir, upload en `memory/server_api.py`, resumen buscable+lazy, nota `[SISTEMA]` retirada, migración perezosa/no-destructiva) + nota "widgets escriben a memoria" (mensajeria `kind='msg'`). El diseño INI-017 original queda vigente para los gestos de frontend (paste/drop), solo cambia el destino del backend.
- 2026-07-09 · T59 — `cluster.yaml`: módulo `files` RETIRADO (queda un comentario que apunta a memory/ + shim de compat); descripción de `memory` ampliada al estado INTEGRADA (absorbe files/ episódico, upload en memory/server_api.py, migración, seed_from_hermes, widgets vuelcan, consumidor de cola en el lifespan).
- 2026-07-09 · **V2-003 CERRADA** — Aceptación cumplida: (a) subida de archivo → resumen buscable por `memory.query`, binario lazy (verificado EN VIVO + `test_server_api.py`); (b) `memory.state()` devuelve el perfil del operador sembrado desde ~/.hermes si lo hay (`seed_from_hermes` + test); (c) mensaje entrante de mensajería queda como recuerdo `msg` recuperable (`test_memory_dump.py`); (d) clone sin Hermes arranca con memoria vacía sin error (seed best-effort + flag `ZAELAR_MEMORY`). Suite `memory/ bus/ config/ nucleo/ connectors/messaging/` = **109 passed**. Arranque EN VIVO `make run-duo` limpio: `/api/brain`=duo (cerebro actual intacto, cero regresión), boot «Memoria v2 montada — cola de escritura arrancada», `/events` idéntico. **status/completed_at/state.json = artefacto del daemon MeshKore** (no editables a mano de forma persistente; el daemon los reconcilia al re-leer los .md con todas las tareas [x] + esta línea de cierre; no hay generador local ejecutable — `meshcore-py` es el servicio compartido). Siguiente: **V2-004 — FlashBrain** (`depends_on: [V2-002, V2-003]` satisfecho).
