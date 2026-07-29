---
id: V2-014
title: Visualizador del MAPA DE MEMORIA — estado + corto + largo plazo, grafo, en tiempo real
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [frontend, memory, server, voice]
depends_on: [V2-013]
wall_order: 14
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-13T16:36:14.556Z
commit_sha: e5298232d74569141da4f36341aa92b7fae434c8
---
## Goal

Una pantalla para VER la memoria de zaelar en tiempo real mientras hablas: cómo se compone, dónde coloca cada cosa,
cómo la puntúa y la relaciona. Herramienta de debug y de confianza (ver que la memoria de V2-013 funciona de verdad).

## Qué se construye

- **Icono 🧠 (cerebro/memoria) en la barra superior, junto a Reset.** Al clicar, abre el visualizador del mapa de
  memoria a pantalla (overlay).
- **Tres capas visibles**, muy gráficas (nubes/nodos conectados):
  - **ESTADO** — la conciencia de zaelar de sí mismo y su entorno (quién es el operador, trato, ubicación, idioma…).
  - **CORTO PLAZO** — memoria reciente/episódica.
  - **LARGO PLAZO** — hechos durables, tareas realizadas, preferencias… ordenados (p. ej. una tarea hecha aparece
    en "largo plazo / tareas realizadas").
- **Cada unidad de memoria** muestra su contenido + **scoring/puntuación** + **fecha/hora** del evento + **metadatos**
  (kind, weight, access_count, pinned, ttl…). Texto diminuto (~8px) **ampliable** (zoom/pan).
- **Grafo de conceptos**: aristas que conectan conceptos y sus instancias (deporte→pádel/fútbol), leídas de `edges`.
- **Tiempo real**: se actualiza mientras hablas (SSE, sin polling) — se ve cómo entra cada cosa y se coloca en su
  capa/orden en el momento.

> No es un widget del canvas: es una vista de sistema (como `/debug`/`/architecture`). El recorte cuando la memoria
> crezca demasiado se aborda más adelante; ahora el objetivo es VERLA formarse.

## Tareas

- [x] T129 — API de lectura del mapa de memoria (read-only, no-cache): estado + corto + largo + edges + metadatos completos (scoring, fecha/hora, kind, weight, access, pinned) para el visualizador.
- [x] T130 — Icono 🧠 en el CUENCO del orbe (`frontend/`), abre el overlay del visualizador. (El operador pidió el 🧠 en el cuenco del orbe, no en la barra superior; ⏰ cron BAJÓ también de TopBar al cuenco.)
- [x] T131 — Visualizador gráfico: nubes/nodos por las 3 capas (estado/corto/largo), texto ~8px ampliable (zoom/pan), cada unidad con contenido+scoring+fecha/hora+metadatos; aristas del grafo de conceptos.
- [x] T132 — Tiempo real por SSE (sin polling): al hablar, la unidad nueva aparece y se coloca en su capa/orden en vivo (reusar el bus/observer + la señal `memory.updated`).
- [x] T133 — Alineación: docs (observability/modules) + CLAUDE.md §Frontend + **pasar la revisión de alineación** (diagrama `/architecture` no toca — no cambia topología ni modelos, solo se añade una ruta de lectura + una vista de sistema).
- [x] T144 — Layout que APROVECHA la pantalla: columnas PROPORCIONALES (20% ESTADO · 20% CORTO · 60% LARGO) sizadas al viewport, cajas que RELLENAN el ancho de su columna y refluyen (varias por fila), vista por defecto que llena el ancho (luego zoom/pan), reflow en resize. `done` 2026-07-09.
- [ ] T145 — Capa de OBSERVABILIDAD en vivo (gated por `memory_observability`, default ON): cada dato escrito tiñe el nodo unos segundos (verde), cada sobrescritura (ámbar) y cada query/prompt dinámico ilumina las piezas que tocó (azul). SSE local con `op`+`ids` afectados. **Falta: toggle en la UI del flag + tintado del ESTADO (hoy solo refetch, sin id) + calibrar con V2-013.**
- [x] T147 — Layout PROPORCIONAL 10/20/70 (ESTADO 1 col · CORTO 2 col · LARGO el resto), cajas que rellenan el ancho. `done` 2026-07-09.
- [x] T148 — Memoria en la columna de LOGS (◷): filas `kind=memory` con módulo=memory · capa (state/short/long/slow) · petición → resultado (nº tarjetas/chars) + tiempo (`mem_ms`). El turno emite una fila por capa leída (estado/corto/recall) y el puente etiqueta las escrituras/queries; las tarjetas del mapa se siguen iluminando. `done` 2026-07-09.

## Aceptación

- El icono 🧠 junto a Reset abre el mapa; se ven las 3 capas con nodos/nubes conectados y texto ampliable.
- Cada unidad muestra scoring, fecha/hora y metadatos; el grafo muestra relaciones (deporte→pádel).
- Hablando con zaelar, una memoria nueva (p. ej. "he hecho X") aparece en vivo en su capa correcta, sin refrescar.

## Riesgos

- Rendimiento con muchas memorias: virtualizar/nivel de detalle por zoom; el recorte de memorias grandes es trabajo futuro.
- Depende de V2-013: sin estado/hechos/grafo poblados, el mapa se ve vacío — por eso `depends_on: [V2-013]`.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T129 (commit `49142b8`) — `memory/api.py::map()`: mapa COMPLETO read-only (no hot path, no refuerza) = `state` + `layers:{short (level 'short'), long ('mid'/'long')}` + `edges` + `counts`, cada recuerdo con TODOS sus metadatos (`id,kind,text,importance,weight,access_count,last_access,ttl_days,pinned,valid,superseded_by,level,created,updated`). `GET /api/memory/map` (`memory/server_api.py`, `no-cache`). Tolera BD vacía/NULL. Verificado en vivo: 95 memorias reales (77 corto + 18 largo), estado vacío (`operator_name=None` — correcto, V2-013 pendiente), header `no-cache`, todos los metadatos presentes. Tests: `test_map_groups_by_layer_with_metadata`, `test_map_empty_db_is_graceful`, `test_memory_map_endpoint` (13 memory verdes; 100 memory+bus sin regresión).
- 2026-07-09 · T132 (commit `49142b8` backend + `348d5f2` frontend) — tiempo real SIN polling: puente en el lifespan del server (`server/__init__.py`) que reenvía la señal `memory.updated` del bus al topic `observer` (→ `GET /events`) como `{kind:"memory"}`, sin pasar por el ring de `/debug` (cero ruido). `services/sse.js` → `store.bumpMemory()`; `MemoryMap` re-fetchea (debounced 250ms) SOLO si está abierto; `store.memBump`. Verificado e2e: subir un fichero (→ `memory.updated` op=episode) emite `{"kind":"memory","op":"episode"}` en `/events`.
- 2026-07-09 · T130 + cuenco del orbe (commit `348d5f2`) — DECISIÓN del operador: los iconos de zaelar (voz/memoria/chat/crons/gate) van en un **CUENCO** (semicírculo cóncavo) BAJO el orbe (el orbe = zaelar personificado); los del PROYECTO se quedan en `TopBar`. `Orb.js`: 5 `.orbic` en arco (CSS `translateY` por `nth-child`, centro abajo) — **⏰ cron · 🧠 memoria · 🔊 altavoz (centro) · 📝 subtítulos · 🤖 gate**. ⏰ cron **BAJÓ** de `TopBar.js` al cuenco (abre el mismo `CronPanel`); 🧠 memoria nuevo (abre el visor, `store.memOpen`). Azul=on/abierto, gris=off/cerrado. `node --check` OK, assets 200 `no-cache`.
- 2026-07-09 · T131 (commit `348d5f2`) — `frontend/app/components/MemoryMap.js`: overlay a pantalla (patrón `/debug`, NO widget) con 3 capas apiladas en bandas (ESTADO/CORTO/LARGO), cada recuerdo un nodo/tarjeta (texto ~8px, scoring, fecha/hora, chips kind/access/pin, barra de weight); **grafo** de `edges` como curvas SVG entre nodos; **zoom** (rueda, alrededor del cursor) + **pan** (arrastre) + controles +/−/⊡/⟳; fit-to-view inicial. Tema `--hb-*` (cero hex) → se repinta al cambiar de tema. Montado en `main.js`.
- 2026-07-09 · T133 (commit docs) — alineación: CLAUDE.md §Frontend (cuenco de 5 iconos + ⏰ bajado + visor de memoria), `zaelar-modules.md` (§Frontend MemoryMap · §Memory `map()`/`/api/memory/map` · tabla de módulos), `zaelar-observability.md` (evento `kind:memory` + sección «El visor de memoria»). Diagrama `/architecture` NO tocado (sin cambio de topología/modelos).
- 2026-07-09 · T144 (layout proporcional) — feedback del operador: "aprovecha la pantalla, no dos columnas gigantes". `MemoryMap.js` pasa de columnas de ancho FIJO (1/2/4 nodos) a columnas PROPORCIONALES al viewport (`computeGeom(viewW)`: fracciones 0.20/0.20/0.60, `cols`+`nodeW` derivados del ancho real → las cajas RELLENAN el ancho y refluyen). `fitView` ahora **llena el ancho** de la pantalla (scale=w/worldW, top-aligned) en vez de encoger todo hasta caber en alto. Reflow en `resize` (debounced 120ms, re-render+fit). Tarjetas con `width` inline (memCard/stateCard reciben `w`) → `.mm-node{width:152px}` deja de mandar. `node --check` verde.
- 2026-07-09 · T145 (observabilidad en vivo, parcial) — capa de tintado por SSE: **backend** — `memory/queue.py` re-emite `memory.updated` con el **id real** tras el insert async (verificado in-process: write→id 181; e2e paste→`{kind:memory,op:episode,id:182}` en `/events`); `server/__init__.py` reenvía `op`+`ids`/`id` por el puente (antes solo `op`); `nucleo/flash/prompt.py::compose_recall` emite `op:"query"` con los ids que tocó (gated `_observability_on()`); `config/settings.py` gana `get()` + knob booleano `memory_observability` (default True, env fallback `ZAELAR_MEM_OBSERVABILITY`) + persistencia en `update()`. **frontend** — `store.memPulse`/`pushMemPulse`; `sse.js` enruta `op`+`ids` (query no refetchea, solo tiñe); `MemoryMap.js` mantiene `pulses` (id→{cls,until}), `applyPulses()` (por `data-mid`), expiración 4.2s; CSS `.pulse-new/upd/qry` (verde/ámbar/azul, keyframe). Pendiente (queda tarea abierta): toggle UI del flag + tintado del ESTADO + calibrar con V2-013.
- 2026-07-09 · ajuste de layout post-feedback del operador — el visor pasa de **3 bandas apiladas** (una debajo de otra, todo amontonado arriba) a **3 COLUMNAS lado a lado**: ESTADO (estrecha, 1 nodo de ancho, izq) · CORTO PLAZO (estrecha, 2 nodos, centro) · LARGO PLAZO (la MÁS ancha, 4 nodos, der — la que crece). Cada columna = su propio bloque con rail de color arriba + cabecera (título·count·sub), y fluye sus nodos verticalmente dentro. Solo `MemoryMap.js` (geometría por-columna `ZONE_GEOM` con `x`/`w` fijos por zona, `zoneColumn()`, `fitView` encuadra las 3) + su CSS en `styles.css` (`.mm-band` como columna con `border-top` de color, `.mm-zhead`/`.mm-zsub`). Backend/API/SSE/edges/zoom/pan/hover intactos. Verificado: `node --check` OK, assets 200 `no-cache`, simulación con el JSON real (158 memorias) coloca las 3 zonas en columnas ordenadas y sin solape (WORLD_W≈1352).
