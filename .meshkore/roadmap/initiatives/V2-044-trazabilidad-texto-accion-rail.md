# V2-044 — Trazabilidad texto → acción → rail → sesión → eventos (traces encadenados)

**Estado:** v1 IMPLEMENTADA (2026-07-16) · **Origen:** pedido del operador (sesión 16-jul)

> **v1 verificada**: probe headless → `trace: T1·a90f` en la respuesta; el timeline muestra la raíz (frase) + la
> destilación del CORAZÓN (off-hot-path, segundos después) + la forense del turno, todos con el mismo id — el
> ContextVar cruzó `create_task`→`to_thread` sin stamping manual. Tests `tests/voice/unit/test_trace.py` 5/5.
> **Fuera de v1** (documentado): ticks de `widgets/background.py` como origen, triaje de mensajería como origen
> propio, filtro del árbol de Trazas por texto.

## El problema (palabras del operador)

Cada frase del operador acaba en uno de tres destinos: **solo memoria** ("me gusta el fútbol"), **una acción
directa** ("enciende el reproductor de música" → data-op sobre un widget), o **una cadena** ("ponme la mejor
canción de Sinatra" → buscar cuál es + reproducirla; "créame un widget de parchís" → escalada → worker Claude
Code → generación → show → modificación posterior en la MISMA sesión; "búscame una moto en Wallapop" → navegador
→ búsqueda → análisis de cada resultado → resultados). La calidad del sistema ES que cada texto caiga en el rail
correcto y desemboque en el set de eventos que corresponde. Hoy la columna de observabilidad es un firehose
cronológico: no se puede ver QUÉ frase originó QUÉ eventos, ni evaluar si la asociación frase→acción→rail fue la
correcta. Queremos:

1. **Un id de trazabilidad por estímulo**: cada frase del operador (y cada disparo del sistema: cron, mensaje
   entrante) nace con un `trace` id; TODO lo que derive (tool calls, tags de canvas, runs de rail, sesiones de
   worker, pasos del navegador, escrituras de memoria, notas [SISTEMA], notify) queda sellado con ese id.
2. **La columna cronológica** muestra el trace de cada evento (chip clicable → filtra esa cadena).
3. **Una segunda vista "Trazas"**: un árbol por trace — la FRASE que lo inició como raíz y debajo, encadenado,
   todo lo que generó (agrupado por actor: turno flash, rail, worker, navegador, memoria).

> "Abre un widget" es un trace; "ciérralo" es OTRO; cada modificación posterior de un widget es OTRO trace aunque
> reutilice la MISMA sesión de worker — el árbol muestra la sesión como actor, y la continuidad de sesión se ve
> porque ambos traces cuelgan del mismo `worker:<id>`.

## Diseño

### 1. Núcleo: `voice/trace.py` (nuevo, sin dependencias)

- `contextvars.ContextVar` con `(trace_id, span)`. Contextvars viajan SOLOS por `asyncio.create_task` y
  `asyncio.to_thread` (copian el contexto) → la mayoría del turno se traza GRATIS, sin tocar call-sites.
- `begin(text, origin) -> tid`: genera id corto legible (`T<seq>·<hex4>`), setea el ctxvar y emite el **evento
  raíz** `emit("trace", origin, text=frase, extra={trace, root:True, origin})`. Orígenes v1: `turno` (voz+chat,
  nacen en `providers/nucleo.py::_run` ANTES del gate — así los descartes ambient/echo/hard-interrupt también se
  trazan y son evaluables), `kickoff`, `probe`, `cron` (scheduler), `proactive`.
- `current() -> tid` · `adopt(tid, span="")`: re-unirse a un trace desde OTRO loop/hilo (los cruces
  `run_coroutine_threadsafe`/`call_soon_threadsafe` NO copian contexto → esos seams se cosen a mano).
- `span` = actor del nivel 2 del árbol (`worker:<id>`, `web:<task>`, `rail:<kind>`, `gen:<widget>`, `memoria`).

### 2. `observer.emit()` adjunta trace+span automáticamente

Si el evento no trae `trace` explícito, lee el ctxvar (ns, cero I/O). Nada del hot path se toca (V2-011 intacto).

### 3. Costuras explícitas (donde el contexto NO viaja solo)

| Seam | Stamping |
|---|---|
| `SessionRecord` (workers) | nuevo campo `trace_id` sellado al crear la escalada (en-turno, ctx vivo); `_run_task` hace `trace.adopt(rec.trace_id, span=f"worker:{id}")` → TODOS los emits del ciclo del worker (fases, notify, entrega) heredan |
| `agent_report`/`worker_api` (HTTP del CLI del worker) | resuelven la sesión por task_id → `adopt(rec.trace_id, span)` al inicio del handler |
| `widgets/navegador/tasks.py` | el registro de tarea guarda `trace`; los emits por tarjeta lo sellan; el mailbox del owner acarrea `trace` en el comando y el owner adopta al despachar |
| `nucleo/rails.py` | el run guarda `trace` al crearse; `_observe` lo sella (span=`rail:<kind>`) — transiciones off-turn quedan atribuidas |
| `memory/queue.py` | cada item encolado lleva `trace.current()`; el writer (hilo propio) adopta por item (span=`memoria`) |
| generador de widgets | el job de generación acarrea el trace del turno que lo pidió; adopta en su task |
| `dispatch.inject_soon`/`cancel_soon`/… | capturan `trace.current()` al llamar y adoptan en la coroutine marshalada |

Fuera de alcance v1 (documentado): ticks de `widgets/background.py` (crearían un trace/tick de ruido), triaje de
mensajería como origen propio (v1.1), eventos de conectores puros.

### 4. Frontend (DebugPanel)

- **Columna cronológica**: chip `trace` por fila (id corto, hue determinista por hash), click → mete el id en el
  filtro (la cadena completa se aísla en un click). El id entra en `dataset.s` (buscable).
- **Vista «Trazas»** (toggle en la cabecera ≣ Log ⇄ ⛓ Trazas): árbol por trace —
  `raíz (origen + FRASE + hora + nº eventos)` → `span-nodos (worker:3, rail:music, web:t2, memoria, flash)` →
  `eventos cronológicos`. `<details>` nativos (colapsables sin JS). Eventos sin trace → cubo «sin traza» (oculto
  por defecto). Cap de traces vivos en DOM (~100).

### 5. Contrato del evento (nuevo, aditivo)

`{..., "trace": "T12·9f3a", "span": "worker:5"?, "root": true?}` — aditivo: nada existente se rompe; el JSONL y
el juez del tester pueden agrupar por `trace` (el juez gana correlación gratis).

## Por qué así

- **Contextvars primero, stamping después**: el 80% de la cadena (turno → create_task → to_thread) se traza sin
  tocar los ~40 ficheros que emiten; solo se cosen los 6-7 cruces de loop/hilo reales.
- **El árbol es de 3 niveles fijos (trace → span → eventos)**, no un DAG de parentescos por evento: legible,
  barato, y suficiente para evaluar "¿cayó en el rail correcto y desembocó en los eventos que tocan?".
- **Latencia intocable**: leer un ctxvar son nanosegundos; el único evento nuevo por turno es la raíz.

## Verificación

- `tests/voice/unit/test_trace.py`: propagación por create_task/to_thread + adopt cross-thread.
- Probe headless: `make flash T="pon música de Sinatra"` → todos los eventos del timeline comparten `trace`.
- Manual: vista Trazas con una orden de widget + una escalada → dos árboles con su frase raíz.
