# zaelar — Observabilidad y depuración (INI-013)

> Regla de oro: **no hace falta mirar la pantalla para depurar zaelar**. TODO lo que pasa (voz, frontend/widgets,
> cerebro «Colmena», llamadas a modelos LLM y por qué API) deja rastro en un **registro único de eventos**. Este
> documento dice dónde está y cómo leerlo. Cualquier agente que cargue el contexto debe empezar por aquí para depurar.

## Los CUATRO ejes de un evento

Todo evento responde a cuatro preguntas, y cada una tiene su campo. Entender esto es entender el sistema entero:

| Eje | Campo | Qué contesta | De dónde sale |
|---|---|---|---|
| **QUÉ** | `kind` + `label` | qué ha pasado | el sitio que lo emite |
| **DE QUÉ PIEZA** | `cat` | FlashBrain · Brain Workers · Memoria · Widgets · Sistema · Pulso | `observer.py::_CAT` |
| **DE QUÉ FLUJO** | `trace` → columna `corr_id` | el **correlation id**: todo lo que desencadena un estímulo, de inicio a fin | `voice/trace.py` (ContextVar) |
| **QUIÉN y CUÁNDO** | `uid` · `sid` | la instalación y la sesión de trabajo | `observability/identity.py` |

**El correlation id no es un identificador aparte**: es el `trace` de V2-044, promovido de campo dentro del JSON a
columna indexada. Un segundo id paralelo se habría separado del primero en la primera costura cross-loop que
alguien olvidara coser. Cada petición del operador abre su propio flujo —aunque corrija una anterior—; lo que
continúa un flujo vivo (un worker entregando, un paso del navegador) hereda el suyo.

**La familia dice QUÉ pasó, no QUIÉN lo hizo.** Una lectura de memoria es `memory` la haga el FlashBrain o un
worker; quién la hizo lo dice el `span` (`worker:5`, `rail:music`, `web:t2`). Para aislar por actor está la vista
Trazas (⛓).

## Dónde se guarda

**Todo en la instalación, en un solo sitio.** No hay servicio externo ni carpeta aparte:

- **`memory/_data/zaelar.db`** (SQLite+WAL, el MISMO fichero de la memoria) tabla `events`, escrita por el sink
  del bus (`bus/log.py`) — escritor único. Además del `payload` JSON completo, sube a **columnas indexadas** lo
  que hace falta para consultar: `corr_id · session_id · user_id · cat · kind · label · span · ms · model ·
  tokens_in · tokens_out · ver`. Se añadieron con `ALTER TABLE` idempotente: una instalación viva no pierde su
  histórico por una migración, y las filas antiguas quedan a `NULL` porque ese dato no existía.
- **`.meshkore/logs/timeline-latest.jsonl`** (rodante) y **`.meshkore/logs/sessions/<session_id>.jsonl`** (por
  sesión de trabajo) — el volcado crudo, para `jq`.

`GET /api/observability/*` lo lee: `flows` (resumen por flujo: duración real de punta a punta, familias, actores,
tokens, errores), `flow/{corr_id}` (detalle cronológico), `sessions`, `catalog` (el mapa de lo filtrable),
`identity` y `stats` (cobertura de los propios ejes). Solo lectura.

**Identidad**: `user_id` es un **UUID4 aleatorio** generado la primera vez y guardado en `config/identity.json`
(gitignored). Aleatorio y no correlativo a propósito — no identifica a nadie por sí mismo. Va a un JSON y no a la
base de datos porque un reset con «borrar memoria» destruye `zaelar.db`, y perder la identidad al limpiar la
memoria haría inútil cualquier análisis longitudinal. `session_id` es un UUID4 por **sesión de trabajo**: la abre
el frontend al conectar y la cierran ⏻ o cerrar la pestaña; una reconexión NO la parte en dos. Con inactividad
REAL más allá de `ZAELAR_SESSION_IDLE_MIN` (def. 5 min) se cierra sola (`identity.note_real_activity`) — pero
solo la actividad REAL cuenta para ese reloj, y solo la actividad REAL puede volver a abrir una sesión que ya
está cerrada: un evento de plomería (`cat` `system`/`pulse` — incluido el propio evento de cierre) NO reabre
nada (V2-092 addenda, 2026-08-15; antes sí lo hacía, y una sesión terminada resucitaba en el acto de cerrarla).

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
cabe se recorta con `…` y el `title` (hover) lo explica. Las columnas cuentan una historia de izquierda a derecha
—CUÁNDO · de qué FLUJO · de qué PIEZA · QUÉ tipo · cuánto tardó · con qué modelo · cuántos tokens · y qué pasó—:
**Hora · Flujo · Familia · Tipo · ms · Motor · Tamaño · Evento**. Se oculta sola en la vista **Trazas** (árbol, sin
columnas) y por debajo de 700px de panel, donde la container query ya colapsa las filas a flujo libre.

#### El último evento va ARRIBA, y el scroll es del operador (2026-08-10)

**La lista crece por PREPEND**: lo recién ocurrido entra pegado a la cabecera de columnas y empuja al resto hacia
abajo. Mirando siempre el mismo trozo de pantalla se ve lo último; bajar es ir hacia atrás en el tiempo. En la vista
**Trazas** manda el mismo criterio —el flujo más reciente arriba— pero **dentro** de cada árbol los eventos siguen
en orden cronológico: un flujo se lee de principio a fin, que es lo que permite ver dónde se torció.

Esto **sustituye al «seguir el último evento»** y no es un detalle estético, es lo que hace que la superficie no
pueda mentir. La versión anterior fijaba el fondo en cada evento y tenía que decidir cuándo soltarse (el operador
sube a leer) y cuándo re-engancharse: estado de seguimiento, ventana de gesto real para distinguir su scroll del
nuestro, un `requestAnimationFrame` para medir la fila antes de fijar, y un indicador en la cabecera para que el
estado no fuera invisible. Se reportó dos veces que «a los diez o quince mensajes deja de seguir sola», se
endurecieron los dos caminos por los que podía perderse (el guarda de rAF que se colgaba con la pestaña en segundo
plano; el `stick` que soltaba cualquier scroll, incluido el programático) y **aun así el estado seguía pudiendo
mentir sobre lo que estabas viendo**. Creciendo por arriba no hay nada que perseguir: el problema no se blinda, se
elimina, y con él ~70 líneas.

Lo único que queda es **una compensación de tres líneas** (`DebugPanel.prepend()`): si el operador está arriba
(`scrollTop 0`) la fila entra y ya; si está leyendo más abajo se suma el alto que acaba de aparecer encima, para
que lo que tiene bajo los ojos no se mueva ni un píxel. El anclaje automático del navegador se **desactiva**
(`overflow-anchor:none` en `.dbg-list`) porque solo existe en Chrome/Firefox y su ajuste se sumaría al nuestro:
un solo dueño, mismo comportamiento en todos los navegadores. El scroll no se toca en ningún otro sitio, salvo al
ABRIR el panel (que es «a ver qué pasa ahora» → arriba).

**Todo el filtro vive en UN panel PLEGABLE** (2026-08-09): en la cabecera, un botón **«Filtros (N) ▾»** —N = tipos
marcados ahora mismo, para saber de un vistazo si estás viendo el hilo entero o uno recortado— junto a un buscador
a media anchura. **Cerrado no deja nada en pantalla**: debajo de la cabecera van directamente los rótulos de
columna y los eventos. Se cierra desde el mismo botón o desde «▴ Condensar», dentro del panel. Con tantas
familias y tipos, tenerlo todo desplegado se comía la pantalla, que es para lo que se abre el visor.

**UN SOLO EJE: el tipo.** Dentro del panel va una TABLA con el **mapa completo de lo filtrable** —una fila por
familia, todos sus tipos a la derecha— servida por `GET /api/observability/catalog`, que lo saca de
`observer.py::_CAT`: la MISMA fuente que sella la familia de cada evento, así que el frontend no duplica el mapa,
lo pide. Se pinta ENTERO aunque un tipo no haya ocurrido nunca — el operador ve de una lo que puede encender.

- **El rótulo de la familia es su mando**: enciende o apaga todos sus tipos de golpe. En cursiva cuando la familia
  está a medias, para que un filtro parcial no se confunda con la familia entera.
- La barra de chips de familia que había encima **se retiró** (2026-08-09): era un SEGUNDO eje que se solapaba con
  este y obligaba a razonar dos veces «¿esta fila no sale por la familia o por el tipo?». Con un solo eje,
  `visible(row)` tiene una respuesta y solo una.
- **Por defecto**: encendidas las familias de trabajo (FlashBrain · Brain Workers · Memoria · Widgets), apagadas
  las de plomería (Sistema/Código · Pulso) — **salvo `error` y `alert`, que arrancan encendidos aunque su familia
  esté apagada**: un error invisible es el peor modo de fallo posible. El operador puede apagarlos, pero como
  decisión suya, no por omisión.
- Se persisten los **apagados** (`hb_dbg_kinds_off_v2`), no los encendidos: un tipo NUEVO nace visible en vez de
  desaparecer por una lista vieja del localStorage.

El filtro se aplica en `visible(row)` y se re-evalúa sobre TODO el log en cada cambio (`reflow()`), no solo sobre
lo que llegue después:

Las filas ocultas siguen en el DOM (encender un chip las devuelve al instante, sin recargar) y **nada de esto toca
lo que se persiste**: los `.jsonl` y el SSE siguen llevándolo todo — el filtro es de LECTURA.

### La EVIDENCIA: qué trajo el mundo exterior (2026-08-10)

Un registro que cuenta la **pregunta** y la **decisión** pero no la **prueba** sirve para saber que el sistema
buscó, nunca si buscó BIEN. La fila decía «7 resultados» y el contenido que el modelo leyó se perdía; de un paso de
un Brain Worker quedaba la tool y su objetivo (la query, la URL), no lo que le contestaron — así que un worker que
trae basura y otro que trae el dato exacto dejaban **el mismo rastro**. Ahora cada punto donde entra el exterior
guarda su evidencia:

| Fila | Qué guarda de nuevo |
|---|---|
| `search · 🔎 resultados web` | título + **URL** + un trozo del snippet de cada resultado, y la respuesta sintetizada si el proveedor la dio |
| `task · <lugar> ↩` | el **`tool_result`** del CLI del worker — lo que le contestó la herramienta. Antes se descartaba entero como «ruido interno» |
| `navegador · 📋 candidatos extraídos` | los anuncios raspados de la página **con su URL**, para poder volver y comprobar precio y descripción |
| `navegador · 🏁 hito` | los hitos de la tarea (`N encontrados`, `descartados por no encajar`), que solo iban al feed EFÍMERO de la tarjeta y morían con ella |

El formato y **el presupuesto** viven en `observability/evidence.py`, y sus reglas explican las decisiones raras:

- **Se recorta, no se resume.** Un resumen es una interpretación; una auditoría necesita el texto tal cual, aunque
  sea el principio. Todo recorte deja marca visible (`…`).
- **Cabeceras antes que cuerpos.** Título y URL no se recortan nunca (identifican la fuente y permiten volver a
  ella); el snippet sí, y agresivo.
- **Techo por evento, y `omitted`.** Si no caben todos, entran los primeros y se dice cuántos quedaron fuera. Un
  recorte silencioso es peor que el recorte: quien audita creería que eso era todo lo que había.

El mismo camino está en el **probe** (`nucleo/flash/probe.py`), que es una implementación paralela del turno: sin
eso, auditar dependía de por dónde hubiera entrado la frase — el punto ciego exacto que esta capa existe para no
tener.

### Leer una sesión entera, viva o terminada

Dos lecturas nuevas encima de las de flujos:

- **`flows.session(sid)`** → la forma de UNA sesión (cuándo, cuánto, cuántos flujos y eventos, tokens, errores,
  familias tocadas, versión del código). Una sesión que no existe devuelve vacío; no se fabrica una que parezca real.
- **`flows.events(session_id, since_id)`** → los eventos EN CRUDO con su payload intacto (ahí vive la evidencia).
  `since_id` es un **cursor sobre `id`, no una ventana de tiempo**: dos eventos en el mismo milisegundo son
  normales —el bus reparte rápido— y una ventana temporal los duplicaría o se comería uno. La misma ruta sirve
  para dos cosas: **seguir** una sesión viva (pidiendo lo que haya después del último id visto) y **archivarla**
  entera paginando desde 0.

`GET /api/observability/session/{sid}` marca además `live` comparando con la sesión abierta, y devuelve `flows`
(número) y `flows_detail` (la lista) como campos DISTINTOS — meter la lista dentro de `flows` pisaba el contador y
quien lo consumiera recibía a veces un número y a veces un array según la ruta.

### Quién puede leer el CONTENIDO

Estas rutas nacieron para el visor local y eran **abiertas**. En una instalación en casa da igual: el puerto solo lo
alcanza la propia máquina. Pero el mismo código corre en despliegues donde el puerto SÍ es alcanzable, y ahí
«abierto» significa que cualquiera que dé con la URL se lleva las conversaciones. Patrón
guarded-until-configured, el mismo del resto del sistema:

- **sin `ZAELAR_OBS_TOKEN` → solo loopback.** Una instalación local funciona exactamente igual que antes.
- **con `ZAELAR_OBS_TOKEN` → hace falta la cabecera `X-Observability-Token`**, venga de donde venga (ni loopback
  pasa sin ella: si no, cualquier proceso de la máquina seguiría teniendo acceso libre al contenido).
- Fail-closed (sin origen determinable, se deniega) y comparación en **tiempo constante**, que no filtra el prefijo
  válido de un token a base de intentos.

Quedan ABIERTAS `catalog`, `identity` y `session/start|end`: las usa la propia interfaz del usuario, que en un
despliegue remoto no es loopback, y no exponen contenido.

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
- **`actionmap`** (V2-539, family `flash`) — the deterministic layer in FRONT of the FlashBrain
  (`nucleo/actionmap/`, doc `.meshkore/docs/modules/zaelar-action-map.md`). It answers **which layer resolved
  this turn**, which used to be unanswerable: ten real voice turns were served by the map while the viewer, the
  Master and the Susurro all reported the model. Labels: **`⚡ action map: direct action (no model)`** (a hit —
  with `action`, `entry`, `source`, `match_ms` and the phrase that produced it), **`🕵️ map candidate…`** (the
  model resolved a turn with a single canvas action, i.e. what the table is MISSING; `known_entry` tells a
  missing entry from one that exists and did not fire), **`🗺️ action map WATCHING`** (`watch.py` subscribed to
  `turn.completed`) and the seeding line, which is an **`alert`** if the pack refused any row. Provenance is a
  FIELD, not an inference: every event stamps `engine: "actionmap"` + `origin: "actionmap"` (a model turn stamps
  `origin: "flash"`), the LAYER column of the viewer reads exactly `engine`, and the match cost is folded into
  `pre_ms` as `amap_ms`. The canvas orders it issues are ordinary `kind="widget"` events with `src="actionmap"`,
  so «¿se abrió el widget?» keeps its single source of truth.
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
  con `src="user"` (POST `/api/ui-event`). Con esto el `/debug` responde "¿quién abrió/cerró/movió/creó esto?".
  **`kind="ui"` con `src="frontend"` (2026-08-10) = ESTADO del cliente, no actividad del operador** — ver abajo.

### Estado del CLIENTE: lo que el frontend sabe y el servidor no puede ver (2026-08-10)

El log tenía la **intención** del operador (`orb:power` al pulsar ⏻) pero no la **realidad** del navegador. Por eso
un agente CAÍDO que se pintaba vivo fue invisible en el registro: costó una sesión entera de diagnóstico y tres bugs
reportados que no existían. Ahora las **transiciones** del cliente entran por el mismo canal
(`api.uiState(action, {...})` → `POST /api/ui-event`, `kind="ui"`, `src="frontend"`):

| Acción | Campos | Qué contesta, que antes no se podía |
|---|---|---|
| `agent:state` | `state` ∈ `off\|starting\|live\|stalled` · `prev` | La VERDAD del agente (`store.agentState()`, no `powerOff`, que es la intención). `stalled` con `prev:"live"` = se cayó en marcha; con `prev:"starting"` = no llegó a subir |
| `mic:analyser` | `state` ∈ `open\|closed` · `reason` | Si el micro se libera **de verdad** al parar, no solo que el icono se apaga |
| `audio:out` | `state` ∈ `attached\|released` | El attach ya se veía (`🔈 TrackSubscribed`); el **release** no → un altavoz zombi no dejaba rastro |
| `tab:visibility` | `state` ∈ `hidden\|visible` | `requestAnimationFrame` NO corre en pestaña de fondo, y de rAF dependen el visualizador y varios guardas: distingue «se congeló» de «estabas en otra aplicación» |

**Regla de uso, y es la que los mantiene útiles: son eventos de ESTADO, no de actividad.** Se emiten SOLO en
transición y jamás dentro de un bucle de render. Dos consecuencias prácticas en el código: `agent:state` cuelga de un
`createEffect` sobre una señal DERIVADA —que se re-ejecuta cuando cambia cualquiera de sus dependencias, a veces con
el mismo valor— y por eso lleva un guarda de valor previo; y `mic:analyser`/`audio:out` viven en `services/audio.js`,
el ÚNICO dueño de los analizadores, que es el único sitio donde «se abrió» y «se soltó» son la verdad y no una
suposición del que llama.

**Hizo falta un arreglo para que el evento pudiera AFIRMAR algo:** `stop()` soltaba solo el analizador del bot
(`audio.dropBot()`) y el del micro sobrevivía con su `AudioContext` abierto — «cerrado» nunca habría ocurrido. Ahora
suelta el grafo entero (`audio.reset(reason)`, que además cierra el contexto). De paso mata una fuga real: `initMic`
abría un `AudioContext` nuevo por sesión sin cerrar el anterior, y Chrome corta a ~6 por página — unas cuantas
reconexiones y `new AudioContext()` empieza a lanzar, dejando el medidor de micro y el orbe muertos para el resto de
la vida de la pestaña.

El endpoint solo reenvía los campos que tiene en lista (`where`/`state`/`detail`/`prev`/`reason`/`cause` + `id`): uno
fuera de ella se descarta **en silencio**, que es peor que no instrumentar nada porque el código parece instrumentado.
Y `src` está acotado a `user`/`frontend` — cualquier otra cosa cae a `user`.
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
