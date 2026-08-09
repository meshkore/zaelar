# zaelar — Observabilidad y depuración (INI-013)

> Regla de oro: **no hace falta mirar la pantalla para depurar zaelar**. TODO lo que pasa (voz, frontend/widgets,
> cerebro «Colmena», llamadas a modelos LLM y por qué API) deja rastro en un **registro único de eventos**. Este
> documento dice dónde está y cómo leerlo. Cualquier agente que cargue el contexto debe empezar por aquí para depurar.

## El bus único de eventos

**UN solo sistema de registro**: todo pasa por `voice/observer.py` → `emit(kind, label, text="", role="", extra={})`,
expresado como un suscriptor del bus in-process (`bus/`, topic `observer`; el puente SSE `bus/sse.py` sirve
`GET /events` idéntico). No hay 2º logger: el motor de voz (`voice/engine/pipeline/agent.py`) registra transcripts,
estado, VAD/barge-in, métricas y errores llamando a `emit()`, igual que el cerebro, los widgets y los conectores.
`voice/engine/pipeline/instrument.py` ya **no** registra eventos — solo guarda el handshake de arranque (topic `vl2`,
para el splash) y una grabación de mic OPCIONAL. Cada evento se escribe a:

| Destino | Qué es | Cómo leerlo |
|---|---|---|
| **SSE `GET /events`** | stream en vivo (`data: {json}\n\n`) | `curl -N http://localhost:43917/events` · lo consume el frontend Y el tester |
| **`.meshkore/logs/sessions/<session_id>.jsonl`** | traza por sesión (append) | `cat` / `jq` el fichero de la sesión más reciente |
| **`.meshkore/logs/timeline-latest.jsonl`** | traza global rodante | tail para ver el turno actual |
| **`GET /debug`** | timeline en vivo en el navegador (anillo en memoria) | abrir en Chrome mientras hablas |
| **`.meshkore/logs/voice/<session_id>/mic_raw.wav`** | audio de entrada, **solo si `ZAELAR_RECORD_MIC=1`** (def OFF) | reproducir para verificar STT |

### El visor (◷): columnas, y DOS ejes de filtro

**Cabecera FIJA de columnas** (2026-08-09): bajo las barras de filtro hay una fila de rótulos con el **mismo grid
exacto** que `.dbg-row` (anchos, gap, padding y el borde izquierdo de 3px) → cada rótulo cae justo encima de su
columna sin cambiar ningún ancho. Vive **fuera** del contenedor con scroll: no scrollea, no la puede podar el
recorte de `MAX_ROWS`, y la lista ocupa exacto desde su borde inferior hasta el fondo del panel. Rótulo que no
cabe se recorta con `…` y el `title` (hover) lo explica. Las columnas son **Hora · ms · Tipo · Motor · Tokens ·
Evento**. Se oculta sola en la vista **Trazas** (árbol, sin columnas) y por debajo de 560px de panel, donde la
container query ya colapsa las filas a flujo libre.

**Todo el filtro vive en UN panel PLEGABLE** (2026-08-09): en la cabecera, un botón **«Filtros (N) ▾»** —N = tipos
marcados ahora mismo, para saber de un vistazo si estás viendo el hilo entero o uno recortado— junto a un buscador
a media anchura. **Cerrado no deja nada en pantalla**: debajo de la cabecera van directamente los rótulos de
columna y los eventos. Se cierra desde el mismo botón o desde «▴ Condensar», dentro del panel. Con tantas
familias y tipos, tenerlo todo desplegado se comía la pantalla, que es para lo que se abre el visor.

**Filtro por dos ejes independientes**, ambos aplicados en `visible(row)` y re-evaluados sobre TODO el log en cada
cambio (`reflow()`), no solo sobre lo que llegue después:

1. **CATEGORÍA** (2ª barra). Rediseñada 2026-08-09 a las **piezas reales del sistema** — se retiró «Principal»,
   que era un cajón de sastre: **FlashBrain · Brain Workers · Memoria · Widgets · Sistema/Código · Pulso**. Las
   cuatro primeras ON por defecto. La sella el backend en `observer.py::_CAT`; persiste en `hb_dbg_cats_v2` (clave
   reestrenada a propósito: con el vocabulario viejo, Widgets y Brain Workers habrían nacido apagados en silencio).
   - **Brain Workers incluye el navegador**: el Chromium interno no es una familia propia, es lo que abre un
     worker cuando le hace falta (`navegador`/`backed`/`background` cuelgan de ahí).
   - **Red de seguridad:** un `kind` sin clasificar (el backend le sella `cat="other"`) y los `error`/`alert`
     NO se ocultan nunca por este eje. Con el inventario completo + su test esto no debería dispararse jamás,
     pero si alguien añade un kind y se olvida, se VE en vez de desaparecer: el silencio por omisión es la peor
     forma de perder señal.
   **Inventario COMPLETO — cada `kind` pertenece a una familia** (norma del operador 2026-08-09: «si tenemos N
   familias, todos los eventos tienen que estar asociados a una»). El mapa vive en `observer.py::_CAT` y lo
   GUARDA un test que recorre el código, saca los `kind` literales de cada `emit(...)` real (siguiendo los
   wrappers `def _emit(kind, …)`) y falla si alguno se quedó sin clasificar —
   `tests/infrastructure/unit/core/test_observer_categories.py`, nodo 7.6:

   | Familia | Kinds |
   |---|---|
   | **FlashBrain** | `brain` · `transcript` · `interim` · `ambient` · `search` · `susurro` · `rail` · `music` · `trace` |
   | **Brain Workers** | `task` · `worker_start` · `navegador` · `backed` · `background` |
   | **Memoria** | `memory` |
   | **Widgets** | `widget` · `ui` · `panel` · `secret` |
   | **Sistema/Código** | `metric` · `stt` · `tts` · `bot_speech` · `vad` · `state` · `session` · `timing` · `notify` · `cluster` · `perf` · `error` · `alert` · `homeostasis` · `language` · `client` |
   | **Pulso** | `pulse` |

   **La familia dice QUÉ pasó, no QUIÉN lo hizo.** Una lectura de memoria es `memory` la haga el FlashBrain o un
   Brain Worker; una navegación es `navegador` aunque la ordenara el turno de voz. Quién la hizo lo dice el
   `span` (`worker:5`, `rail:music.playing`, `web:t2`) y el chip de `trace` — por eso apagar «Brain Workers»
   quita las filas de SESIÓN de worker pero no las de memoria que ese worker provocó: esas son memoria. Para
   aislar por ACTOR está la vista **Trazas** (⛓), que agrupa frase-raíz → actor → eventos.

2. **KIND** (dentro del panel, una LÍNEA POR FAMILIA con sus tipos a la derecha): un chip **por cada `kind` que
   ha aparecido**, con contador vivo. Es el desglose FINO que la categoría no da; apagar una familia se lleva su
   línea entera. Los rótulos se re-pintan al cambiar de idioma (viven fuera del árbol reactivo, así que hay un
   `createEffect` que los refresca — sin él salían mezclados en dos idiomas). Click = mostrar/ocultar; **shift+click = ver SOLO ese kind**
   (repetir devuelve todo). Persiste en `hb_dbg_kinds_off` — se guardan los **apagados**, no los encendidos, por la
   misma razón de arriba. Mientras haya algo apagado el botón «Tipos…» se pone en ámbar: **un hilo recortado no
   debe parecer completo**. Este eje sí puede silenciar errores: ahí la decisión es explícita, no una omisión.

Las filas ocultas siguen en el DOM (encender un chip las devuelve al instante, sin recargar) y **nada de esto toca
lo que se persiste**: los `.jsonl` y el SSE siguen llevándolo todo — el filtro es de LECTURA.

### Registro de acciones de widget — atar «widget equivocado» con la FRASE que lo pidió

Toda orden contra el canvas queda en la categoría **Widgets**, y **cada evento se lleva el texto del turno que la
originó** (2026-08-09). Antes había que reconstruirlo saltando al `transcript` anterior o abriendo la vista de
trazas; ahora la fila ya dice orden + objetivo + origen + frase, que es justo lo que hace falta cuando se abre el
widget que no era.

| Fila | De dónde sale | Qué dice |
|---|---|---|
| `widget · show\|close\|move` | `providers/nucleo.py` (tag `[[show]]`/`[[close]]`) | la orden de canvas + `id` + `src=flash` + **la frase** |
| `widget · data:<acción>` | `providers/nucleo.py::_apply_widget_data` | la DATA-OP en sí (subir volumen, maximizar, marcar hecha) con su `mode` (`fast`/`confirm`/`escalate`) + **la frase** |
| `widget · data` | `widgets/store.py::save()` | el EFECTO (el widget guardó). Sigue marcada como ruido — es consecuencia, no orden |
| `widget · action` | `widgets/server_api.py` | el operador pulsando un botón de la tarjeta (`src=user`) |
| `widget · show\|close` | `nucleo/worker_api.py` | lo mismo pedido por un Brain Worker (`src=worker:<id>`) |

Con el chip de trace (V2-044) de esa misma fila se salta a la cadena completa de la frase.

## Trazabilidad texto → acción → rail → sesión → eventos (V2-044)

Cada **estímulo** que entra al sistema nace con un **trace id** (`T12·9f3a`) y TODO lo que deriva de él queda
sellado con ese id en cada evento — la pregunta de calidad («¿esta frase cayó en el rail correcto y desembocó en
el set de eventos que corresponde?») se responde agrupando por `trace`.

- **Orígenes** (evento raíz `kind="trace"`, `root:true`, `origin`): `turno` (voz+chat, nace en
  `providers/nucleo.py::_run` ANTES del gate — los descartes ambient/eco también se trazan) · `kickoff` · `probe`
  (el probe devuelve el id en su respuesta) · `cron` (scheduler) · `proactivo` (chispas) · `ui` (taps manuales del
  canvas) · `cluster` (mensaje de peer).
- **Cómo viaja**: `voice/trace.py` (ContextVar) — gratis por `create_task`/`to_thread`; costuras explícitas donde
  el contexto no cruza: la escalada lleva el trace en su payload de bus → `SessionRecord.trace_id` → el ciclo del
  worker adopta (`span=worker:<id>`), los handlers HTTP de los CLIs puente (hbnote/hbask) resuelven la sesión y
  sellan, el run de un rail guarda su trace (`span=rail:<kind>`), y el registro de tareas del navegador lo acarrea
  (`span=web:<tid>`). `observer.emit` lo adjunta solo (leer el ctxvar son ns; V2-011 intacto).
- **`span`** = ACTOR (nivel 2 del árbol): `worker:5` · `rail:music.playing` · `web:t2`.
- **En el visor** (◷): cada fila lleva un **chip de trace** (color determinista; click → filtra la cadena entera),
  y el botón **⛓** alterna a la vista **Trazas**: un árbol por trace — la FRASE raíz + todo lo que generó,
  agrupado por actor. `jq` equivalente: `jq 'select(.trace=="T12·9f3a")' timeline-latest.jsonl`.
- Diseño completo: `.meshkore/roadmap/initiatives/V2-044-trazabilidad-texto-accion-rail.md`.

## Pasos de un Brain Worker — DÓNDE trabaja y QUÉ usa (V2-048)

Un worker ya no cuenta solo fases genéricas («consultando la memoria…»). Cada `tool_use` de su stream se traduce a
una fila RICA que dice **el LUGAR** (badge/categoría por sitio) + **la acción y su objetivo concreto**:

- **🧠 memoria** (`kind=memory`, filtro Memoria) — `recall «query»` · `guarda [slot] …`.
- **🧭 navegador** (`kind=navegador`, filtro Navegador) — `navigate → url` · `click [12]` · `type «texto»` ·
  `scroll` · `extract`. Además, tras ejecutarse, el propio browser emite el **RESULTADO**: `🧭 página` con
  `título · url` a los que llegó, y `🧭 resultados` con el nº de anuncios de `extract` (lo que el comando no dice).
- **🌐 web** (`kind=search`) — `web_search «query»` · `fetch url`.
- **✏️ código / 📄 archivo** (`kind=task`) — `escribe fichero` · `lee fichero` · `busca patrón`.
- **↩ zaelar** (`kind=task`) — el worker `ask`/`act`/`say` a través de los puentes.

Y dos filas de marco: al **nacer**, `worker · <backend>` con **modelo** (chip) + **capa** (chip) → qué motor/modelo
conduce; al **terminar**, `fin` con **tokens** input/output (chip de tamaño) + **coste USD**. Todo se agrupa bajo
`span=worker:<id>` en la vista Trazas (⛓) y se persiste en los jsonl. La fase coarse (`rec.phase`) se mantiene para
el prompt «PROCESOS DE FONDO» del FlashBrain, pero no duplica fila. Fuente: `nucleo/workers/claude_session.py`
(`_tool_step`) + `nucleo/workers/session.py` (`_emit_step`/`_PLACE`) + `widgets/navegador/act_api.py` (`_emit_nav`).
Diseño: `.meshkore/roadmap/initiatives/V2-048-observabilidad-workers.md`.

## Tipos de evento (`kind`) — qué observar

- **`susurro`** (V2-053) — el auditor conversacional, con **observabilidad TOTAL por regla del operador**: `👂
  fricción → auditoría` (motivo + señales; la variante «en cooldown» marca `skipped`), `📤 request → LLM auditor`
  (**`extra.request` = el payload COMPLETO enviado**, messages incluidos), `📥 response ← LLM auditor`
  (**`extra.raw` = la respuesta CRUDA** + ms + tokens), `🩹 repair_say → brain_notes` / `📌 finding → cola
  dev-loop` (cada corrección con su **antes/después** en `extra`), `✅ auditoría completa` (assessment + types +
  total_ms) y `⚠️ … (fail-open)`. Todo sellado con el `trace` del estímulo que causó la fricción (span
  `susurro`) → el visor ◷/⛓ enseña la cadena queja→auditoría→reparación. Los findings viven además en
  `.meshkore/logs/susurro/findings.jsonl`. **Topic de bus asociado: `turn.completed`** — el cierre semántico de
  CADA turno (voz Y probe, emitido por `observer.turn_detail`) con `{user, decision, tools, window,
  system_prompt, trace}`; es la costura de suscripción para consumidores programáticos (depende de
  `ZAELAR_LOG_PROMPTS=1`, def ON — apagarlo deja al Susurro solo con las señales sueltas).
- **`homeostasis`** (V2-070, `nucleo/homeostasis.py`) — la **capa autónoma** que mantiene sana la MÁQUINA (sin
  modelo, determinista; vive AL LADO del cerebro, fuera del bucle de voz, fail-open; gate `ZAELAR_HOMEOSTASIS`). Es
  la fuente de verdad para "¿por qué se degradó/se recicló el motor?". Labels: **`start`** (arranque del supervisor),
  **`degraded`** (vital en rojo detectado — p.ej. el motor LiveKit en `wait_pc_connection timed out` /
  `entrypoint did not exit`, captado por un `logging.Handler` sobre el logger `livekit`), **`recycle`** (recicla el
  worker LiveKit embebido — `aclose`+`make_server`+tarea nueva, sin reiniciar el proceso — SOLO cuando es seguro:
  voz apagada + canal ocioso ≥120s, con cooldown), **`rotate`** (rota `timeline-latest.jsonl`/`meshkore.jsonl` por
  tamaño + poda archivos viejos), **`evict`** (desaloja cápsulas concluidas/viejas, `sys_kv` `capsule:*`) y
  **`alert`** (aviso único al operador cuando detecta degradación pero NO es seguro actuar). Motivada por el
  incidente 2026-07-25 (el worker LiveKit embebido se degradó tras ~7h → voz/chat mudos hasta reinicio manual).
- `worker_start` — arranque de sesión: `profile`, `stt`, **`stt_device`** (metal/cuda/cpu), `llm_provider`, `tts`, `turn`.
- `state` — máquina de 5 estados (idle/listening/thinking/speaking…). Marcado "ruido" en `/debug` (colapsable).
- `transcript` (role=user|bot) — lo que se **dijo** (STT del usuario / respuesta del brain). `interim` = parcial en vivo,
  **efímero** (SSE-only, no toca disco ni el anillo — subtítulos/chat mientras hablas).
- **`vad`** — actividad de voz e interrupción (barge-in), la fuente de verdad para "¿por qué se cortó la locución?":
  "🎤 voz detectada (VAD)", "✂️ barge-in — voz pisa la locución" (`extra.over_agent`), "… fin de voz", "🤫 falsa
  interrupción (ruido)" con **`extra.resumed`** (¿LiveKit reanudó la locución tras el ruido?), "🔊 voz solapada"
  (`extra.is_interruption`). Barge-in tuneable por env: `ZAELAR_MIN_INTERRUPTION_SEC` (def 0.6),
  `ZAELAR_MIN_INTERRUPTION_WORDS`, `ZAELAR_FALSE_INTERRUPTION_TIMEOUT`, `ZAELAR_RESUME_FALSE_INTERRUPTION`.
- **`widget`** — acción de canvas: `label` = `show` / `close` / `move` / `resize` / `data` / `action` / `delete` /
  `confirm` … con `extra.id`. **Ésta es la fuente de verdad para "¿se abrió el widget?"**, independiente de si el
  TTS sonó. **PROCEDENCIA (V2-039, `extra.src`) — de dónde salió la orden**, para auditar el frontend como pieza
  independiente: **`flash`** (el FlashBrain en un turno), **`worker:<task_id>`** (un Brain Worker vía los puentes /
  navegador / agente de código), **`user`** (el operador tocando la UI: abrir/cerrar/arrastrar una tarjeta o pulsar
  un botón del widget), **`system`** (ciclo de vida / background / reset / desconocido). El campo lo estampa cada
  emit; para el ÚNICO punto ciego (el choke point de datos `widgets/store.py::save()`) lo resuelve el registro de
  intención `widgets/provenance.py` (`note`/`who`, TTL). El dedup de `widget` clavea por `(kind,label,id,src)` — dos
  widgets distintos (o el mismo por flash y por worker) NO se colapsan. **`kind="ui"`** = taps de iconos del orbe
  (`orb:cron|memory|speaker|captions|attention`) y del TopBar (`topbar:status|docs|debug|theme|settings|reset`),
  siempre `src="user"` (POST `/api/ui-event`). Con esto el `/debug` responde "¿quién abrió/cerró/movió/creó esto?".
- `brain` — prompts/replies del cerebro «Colmena» (FlashBrain), notas `[SISTEMA]`, escalados a SlowBrain
  (`escalate_to_slowbrain`).
- **`ambient`** — gate de ATENCIÓN (V2-015, `voice/attention.py`): un turno que NO iba dirigido a zaelar (sin
  wake-word y fuera de la ventana de conversación). `label` = "🙉 ambiente — no dirigido a zaelar" con
  `extra.mode` (`smart`/`wakeword`/`ptt`/`always`) y `extra.reason` (`ambient`); o "✋ interrupción dura atendida"
  (`extra.cmd` = `close`/`stop`) cuando una orden dura salta el gate. **Es la fuente de verdad para "¿zaelar ignoró
  voz ambiente?"**: si en una reunión NO hay eventos `widget`/`brain reply` sino `ambient`, el gate está haciendo su
  trabajo. Si ves `widget`/escaladas sobre frases que no le hablaban a zaelar → revisar `ZAELAR_ATTENTION` (¿en
  `always`?) o la ventana. El evento no lleva role de chat (no ensucia el ChatWall), solo `/debug` + SSE `/events`.
- `bot_speech` — orbe hablando/idle. `tts` — síntesis. `metric` — métricas CRUDAS del plugin de LiveKit
  (`STTMetrics`, `LLMMetrics ttft/dur`, `TTSMetrics ttfb`, `EOUMetrics`). ⚠️ **`VADMetrics` NO se registra**
  (anti-flood 2026-07-12): se dispara ~2/s de forma continua (más con ruido de fondo) y no lleva latencias útiles →
  floodeaba el stream y hacía I/O de fichero síncrono en el hilo de voz. `agent.py::_on_metrics` descarta toda
  métrica sin números reales. ⚠️ **`metric` vive en la categoría `system`, NO en `main`** (2026-08-09, queja del
  operador): con un STT de **streaming** (Deepgram) la métrica **no depende de que nadie hable** — el
  `PeriodicCollector` del plugin suelta `STTMetrics: audio=5.00s` **cada 5 s mientras el micro esté abierto**, de
  forma perpetua (~720 filas/hora en un canal ocioso). La latencia POR FRASE, que sí es señal, ya sale como
  `stt`/`tts`/`brain` con backend, modelo y texto. Se sigue persistiendo al jsonl; solo deja de ensuciar el hilo
  principal del visor.
  `error` — errores de sesión. `alert` — errores hablables (p.ej. "Cerebro rápido caído"). `session` — apertura/cierre.
- Conectores: `label` con prefijo `cluster.` / `cron.` / `architect.` / `wa.` (WhatsApp) / (Telegram) = despacho de tag.
- **`cluster` · campo `pace` (V2-075, supersede V2-073)** — el **criterio de salud de conversación** del canal
  agente-a-agente (SOLO cluster; con el operador la conversación fluye siempre). El primer intento (V2-073) usaba
  un regex de frases (`capsule.looks_stuck`/`advanced`) — **eliminado** por decisión del operador (un regex solo se
  adapta a un peer y falla con el siguiente). Hoy el juicio lo hace `connectors/meshkore/evaluator.py`: un modelo
  INDEPENDIENTE (sin tools, read-only, seguro sobre contenido untrusted) devuelve `health` (`flowing`/`stuck`/
  `dead_end`/`imbalanced`/`off_track`) + `action` (`continue`/`concise`/`hand_back`/`pause`) sobre la ventana
  reciente, off-hot-path en un heartbeat throttled (`MESHKORE_EVAL_SECS`). El evento `cluster` lleva `extra.pace`
  con la decisión APLICADA por el bridge. Es la fuente de verdad para "¿por qué zaelar dejó de responderle a este
  peer / le devolvió el turno?". Valores: **`handback`** (le DEVOLVEMOS el turno con UN mensaje corto y paramos),
  **`silent`/`pause`** (dejamos de responder + aviso único al operador), **`waiting`**/**concise** según el veredicto.
  Lo determinista queda solo para lo genérico (dedup exacto, `capsule.near_repeat` como señal de entrada al
  evaluador, no como veredicto). Iniciativa:
  `.meshkore/roadmap/initiatives/V2-075-criterio-conversacion-inteligencia.md` (+ V2-073 histórico).
- **`memory`** — actividad de la memoria central (V2-014). Dos orígenes:
  1. **Mutaciones**: el server puentea la señal `memory.updated` del bus (cada mutación en `memory/api.py::_emit` —
     write/reinforce/pin/link/state/episode/consolidate/query) al topic `observer` como `{kind:"memory", op, ids}`
     (+ `label=op`). Alimenta el **tintado** del visor y sale como fila en la columna ◷.
  2. **Lecturas del turno**: `voice/engine/llm/providers/nucleo.py` emite, tras componer el prompt, una fila por
     CAPA leída: `{kind:"memory", label:"estado|corto|recall", layer:"state|short|slow", text:"petición → resultado",
     mem_ms}`. Así se VE en ◷ qué capa se tocó, cuánto tardó y qué devolvió (nº tarjetas/chars). Columna 4 del
     DebugPanel = la capa; latencia = `mem_ms`.
  Gated por el flag `memory_observability` (default ON, `config/settings.py`; env `ZAELAR_MEM_OBSERVABILITY`).
  Sale por SSE `GET /events`; el puente de mutaciones NO pasa por el ring de `/debug` (fino, cero ruido). **El
  puente de mutaciones va COALESCADO** (anti-flood 2026-07-12): un turno dispara varias `memory.updated` (buffer
  conv + píldoras + reinforce + state) → un **trailing-debounce** (400ms, `ZAELAR_MEM_SSE_COALESCE_MS`) las funde en
  UNA señal SSE con la UNIÓN de ids afectados. El visor sigue en vivo (re-fetch con su propio debounce); ~1 orden de
  magnitud menos de tráfico SSE.

## El visor de memoria (🧠) — ver la memoria formarse en vivo

Vista de sistema (overlay a pantalla, como `/debug`; NO un widget) que muestra **cómo se compone la memoria central
de zaelar en tiempo real** mientras hablas. Se abre desde el **🧠 del cuenco del orbe** (`frontend/app/components/
MemoryMap.js`). Tres **columnas proporcionales** al ancho: **ESTADO 10%** (la pila `memory/state.py`), **CORTO PLAZO
20%** (`level=='short'`) y **LARGO PLAZO 70%** (`mid`/`long`, la que crece); las cajas rellenan el ancho de su columna
y refluyen. Cada recuerdo = un nodo con texto ~8px + **scoring** (importance) + fecha/hora + metadatos (kind, weight,
access, pinned), ampliable con **zoom (rueda) / pan (arrastre)**; el **grafo** de `edges` se dibuja como curvas entre
nodos. **Tintado en vivo** (gated `memory_observability`, default ON): al escribirse un dato el nodo se tiñe **verde**
unos segundos, al sobrescribirse **ámbar**, y una **query** ilumina **azul** las piezas que tocó — cada evento SSE
lleva `op`+`ids` afectados (`services/sse.js` → `store.pushMemPulse`). Fuente: `GET /api/memory/map` (read-only,
`no-cache`) → `{state, layers:{short,long}, edges, counts}` con todos los metadatos. Es la fuente de verdad para
"¿qué recuerda zaelar y cómo lo puntúa?" — complementa a `/debug` (que es el flujo de eventos, no el estado).

## Cómo depurar un fallo de voz (receta)

1. `ls -t .meshkore/logs/sessions/ | head` → fichero de la última sesión (o `tail -f .meshkore/logs/timeline-latest.jsonl`).
2. Léelo: mira `worker_start` (¿qué STT/TTS/brain?), los `transcript` (¿qué oyó/dijo?), los `metric`
   con `*Metrics` (¿dónde está la latencia: STT, LLM ttft, TTS ttfb?), los `error`/`alert`; y los `vad`
   (¿un ruido cortó la locución? ¿`resumed`?).
3. ¿El brain no dispara widgets? Busca eventos `widget`. Si NO hay ninguno pese a pedirlo → el brain no emitió el tag
   (modelo poco capaz o prompt) — NO es el frontend.
4. ¿zaelar mudo? Suele ser: (a) el FlashBrain devuelve 4xx del proveedor rápido (mira el log de zaelar
   `fast brain error`), (b) TTS Metal tropieza el bug de shapes de mlx-audio y el fallback Kokoro-FastAPI no está
   arriba. Ver INI-012 §TTS.

## El tester independiente (INI-013) usa esta observabilidad

`tests/voice/e2e/agent/interlocutor/trace.py` se **suscribe a `/events`** y captura la traza por escenario; el **juez GLM** (Z.AI)
la lee para verificar el comportamiento OBSERVABLE (acciones de frontend + cerebro), no solo el transcript. Los
informes salen a `tests/voice/e2e/agent/runs/report_*.md` con las acciones de frontend observadas por escenario.

**Routing de modelos** (operador 2026-07-07): conducir el tester + juicio barato = **DeepSeek vía AIMLAPI**; juicio
competente/razonamiento = **GLM vía Z.AI** (coding-plan, endpoint Anthropic `api.z.ai/api/anthropic`, con fallback a
DeepSeek). **Gemini free-tier = NO usable** (cuota 20/día, da 429). Claves en `.env` + `.meshkore/credentials/tester.env`
(gitignored).

## Bucle autónomo nocturno

- `tests/voice/e2e/agent/overnight.sh` — bucle: rota escenarios + goals creativos contra zaelar vivo, escribe informes.
- `tests/voice/e2e/agent/guard.sh` — idempotente: levanta zaelar (`make run`, LiveKit nativo sin Docker) y el bucle si están caídos.
- El loop autónomo (`/loop <intervalo> <prompt>`, skill `loop`) re-invoca al agente para: guard → leer último
  informe → arreglar el top bug → reprobar → documentar en INI-013 → repetir.

Ver también: `.meshkore/roadmap/initiatives/INI-013-voice-tester.md`, INI-012 (motor de voz), `voice/observer.py`.
