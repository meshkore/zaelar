# V2-038 — Brain Workers interactivos (sesiones de trabajo bidireccionales, inyectables, agent-agnósticas)

> **Estado: DISEÑO v3 — GO de la revisión de cierre (Fable 5). SPEC CONSTRUIBLE, lista para el Gran Refactor.**
> Épica: `EPIC-v2-colmena`. Sucede y reencuadra a **V2-036** (workers Claude Code one-shot). No confundir con
> **V2-037** (observabilidad/rendimiento, ya cerrada).
> Autor del borrador: Opus 4.8 · Revisiones: Fable 5 (v2 aprobó-con-cambios · v3 GO) · Fecha: 2026-07-14 · es.
>
> **Cómo leer este doc:** las **DECISIONES FIRMES** viven en **§REVISIÓN v2 (A–F)** + **§REVISIÓN v3 (G–P, cierre)**,
> justo debajo del TL;DR — **mandan sobre el cuerpo**. Las secciones 4–16 son el diseño de fondo con avisos
> `⚠️ v2:`/`⚠️ v3:` donde algo se concretó. §14 (preguntas) → RESUELTA en v2·E. El **checklist de construcción del
> equipo = §REVISIÓN v2 (A–F) + §REVISIÓN v3 (G–P)**.

---

## NOTA PARA EL EVALUADOR (Fable 5) — léela primero

Recibes este documento en una **sesión limpia**, sin el contexto de la conversación en que nació. **Aquí está todo
lo que necesitas.** Tu tarea:

1. **Céntrate en LO QUE VAMOS A DISEÑAR (la arquitectura NUEVA)**, no en lo que había. La sección **★ VISIÓN** dice
   qué persigue el operador; las secciones **4–15** son la arquitectura propuesta. La sección **1 (Contexto)** está
   solo para que entiendas de dónde venimos y por qué el modelo viejo (un "gran SmartBrain" + workers de un solo
   tiro) **ya no sirve** — pero **no evalúes cómo migrar ni cómo borrar lo viejo**: eso será trabajo del equipo de
   ingeniería (irán modificando la arquitectura, borrando lo que no sirve y dejando solo lo bueno). Tú evalúa el
   DESTINO.
2. **Produce un INFORME** que responda: (a) ¿la arquitectura propuesta es correcta y suficiente para la VISIÓN?
   ¿soporta "todo" sin necesitar un rediseño posterior? (b) ¿Qué **fallos, riesgos o huecos** ves? (c) Respuestas
   razonadas a las **7 preguntas abiertas** de la §14. (d) Cualquier **simplificación o alternativa mejor**.
3. **No implementes nada.** Es una revisión de arquitectura. Puedes leer el código/documentos que se citan
   (rutas relativas a la raíz del repo zaelar) para fundamentar tu juicio, pero el entregable es el informe.

Contexto del proyecto para situarte: **zaelar** es un asistente personal por voz (STT → cerebro propio «Colmena» →
TTS sobre LiveKit Agents), monolítico (un solo proceso), 100% con memoria local. El **FlashBrain** (`nucleo/flash/`)
es la capa refleja no-razonadora que atiende cada turno de voz en ~1s y orquesta. Lee primero `CLAUDE.md` (raíz) y
`.meshkore/docs/architecture/zaelar-architecture.md` para el mapa general. Ficheros clave citados en este documento:
`nucleo/dispatch.py`, `nucleo/agentes/base.py`, `nucleo/agentes/claude_code.py`, `nucleo/flash/router.py`,
`nucleo/flash/escalate.py`, `nucleo/loop.py`, `nucleo/reset.py`, `voice/engine/llm/providers/nucleo.py`,
`nucleo/flash/probe.py`, `memory/state.py`, `frontend/app/components/ActivityStrip.js`. La iniciativa que reencuadra
es `V2-036-smartbrain-claude-code.md` (el modelo viejo).

---

## 0. TL;DR

Hoy un "worker" es un `claude -p` de **un solo tiro**: recibe un prompt, trabaja hasta el final y muere. No puede
recibir instrucciones nuevas a mitad, no puede preguntar al usuario, no puede pedir que el FlashBrain haga algo por
él, y si se encalla o se lanza por error **no hay forma limpia de pararlo** (el subproceso queda huérfano). Eso
rompe la idea de un sistema inteligente que forma **cadenas de conocimiento y acción continua**.

Esta iniciativa convierte esos procesos en **Brain Workers**: sesiones de trabajo **vivas, interactivas y
bidireccionales**, orquestadas por el **FlashBrain**, con un sustrato **agent-agnóstico** (Claude Code hoy; Codex,
Cursor o Hermes mañana; incluso varios A LA VEZ). Comunicación por el **bus de eventos** (plano de control,
fire-and-forget) + **request/response correlacionado** (cuando un worker PREGUNTA y debe ESPERAR respuesta). El
FlashBrain los **supervisa desde su loop** (~1 Hz): detecta encallamientos, relé de preguntas al usuario, timeouts,
entrega de resultados. Todo el estado de los workers vive en la **memoria de ESTADO** (fuente de verdad) → viaja en
el prompt del FlashBrain y se refleja en la UI.

---

## REVISIÓN v2 — DECISIONES FIRMES tras la 2ª opinión (Fable 5)

> Estas decisiones MANDAN sobre el cuerpo del documento. Son el resultado de incorporar el informe de revisión
> (veredicto: *aprobada con cambios*). Cada punto corrige un fallo/hueco concreto y es condición para construir.

### A. Inyección (↓) — asumimos TURNOS LARGOS (corrige el fallo rojo 2.1)
Un worker agéntico ejecuta toda la tarea dentro de UN turno largo (decenas de tool-calls); un mensaje escrito a
stdin **se encola hasta que el turno cierra** → "además, verde" llegaría cuando la búsqueda YA acabó. Por tanto:
- **Vía PRINCIPAL de inyección = piggyback en los bridges.** El worker habla con el server constantemente (`hbweb`
  tras cada acción, `hbmem`, `hbnote`). TODA respuesta de bridge puede llevar un bloque `⟦NUEVAS INSTRUCCIONES⟧`
  con lo inyectado pendiente para ese `task_id`. La inyección llega en el siguiente contacto (segundos en un worker
  activo) y es **agnóstica del backend por construcción** (solo toca el server; funciona igual con Codex/Hermes).
- **Protocolo de turnos cortos con checkpoint.** El prompt del worker le exige cerrar turno en cada frontera de fase
  ("terminé de filtrar; espero instrucciones o 'continúa'"); el supervisor inyecta `continúa` si no hay nada. Da al
  loop un **heartbeat** natural para detectar encallamiento.
- **`backend.send()` (stdin) = secundario** para workers conversacionales que sí cierran turnos.
- **`interrupt` real:** verificar si el CLI acepta `control_request` (como el Agent SDK) para abortar en caliente el
  caso "para eso" sin esperar al SIGTERM. Interrumpir ≠ inyectar (aborta), no sustituye al piggyback.

### B. Un solo plano request/response con POLÍTICA por acción (corrige el fallo rojo 2.2 + simplificación §4)
- **`ask` y `act` se FUSIONAN en un único plano** request/response: `ask` = `act` con `action="ask_user"`. Un solo
  registry, un solo endpoint (`/api/worker/act`), un solo pump de correlación. `hbask` = azúcar de CLI sobre
  `hbact ask_user`.
- **Política declarativa ALLOW / CONFIRM / DENY por acción, evaluada EN EL SERVER** (nunca en el prompt del worker),
  reutilizando el patrón de `widgets/actions.py::classify()`:
  - **ALLOW** (por defecto): lectura/consulta — `use_tool:web_search`, `read_widget`.
  - **CONFIRM**: mutaciones de UI/datos, `push_channel` externo (además pasa por `scan_outbound`).
  - **DENY duro**: las tools **operator-only** del catálogo (`authenticate_web`, `login_done`,
    `confirm_widget_delete`, `set_style_directive`) — un worker JAMÁS las invoca.
- **`use_tool` lee un catálogo FILTRADO**, no `router.TOOLS` entero: solo las tools marcadas "prestables a workers".
  Añadir una tool nueva al FlashBrain NO la expone a los workers hasta marcarla explícitamente (anti prompt-injection
  desde contenido web hostil).
- **`ask` relatado SIEMPRE con atribución** ("el buscador de la moto pregunta: …", nunca como si preguntara zaelar)
  + cap de `ask` por worker (ingeniería social con la voz de zaelar = superficie de ataque).
- **`act spawn` con límites duros**: profundidad de cadena ≤2 + cuota de descendientes por tarea raíz (evita
  fork-bomb de tokens; el pool acota concurrencia, no volumen encolado).

### C. Fuente de verdad = registro en RAM; ESTADO = proyección coalescada (corrige 2.3)
- **El registro de sesiones en RAM de `dispatch` es la FUENTE DE VERDAD.** El ESTADO de memoria es una **PROYECCIÓN**
  que el **loop (~1 Hz)** sincroniza **solo si cambió** — se ELIMINA la escritura de `set_state` por-evento (§5) para
  no floodear SQLite + `memory.updated` + recomposición de prompt-cache (mismo bug que las VADMetrics de V2-037).
- **`GET /api/tasks` lee el registro en RAM** (la UI reconcilia contra la verdad real). Los chips en vivo siguen del
  SSE `worker.*`.
- **El reinicio se resuelve solo:** el registro arranca vacío → la 1ª sincronización limpia el ESTADO → **cero
  sesiones fantasma** (ya no hace falta el parche de §12).

### D. Invariantes de robustez (corrigen 2.4/2.5/2.6/2.7/2.8)
- **Cross-loop (2.4):** el provider de voz corre en el loop del job-thread de LiveKit; los subprocesos, pipes y el
  pump de `events()` viven en el loop de uvicorn. **TODO comando de `WorkerSession`** (`send`/`stop`/`answer`/
  `inject`) disparado desde un turno de voz se **marshalea al loop dueño** (`run_coroutine_threadsafe`, patrón
  `browser_search.search_sync`/`bus.emit_sync`). Invariante explícito en `session.py`.
- **Kill de GRUPO (2.5):** el backend lanza con `start_new_session=True` y `stop()` mata el **grupo de procesos**
  (`killpg`) — el `claude` tiene hijos (cada Bash tool: `hbweb`, `mem_cli`…); matar solo al padre deja huérfanos (el
  bug que motiva la iniciativa, reencarnado — ya pasó con los chrome-headless de V2-036). Una tarea **encolada** en el
  pool (aún sin proceso) también es cancelable: el registro distingue `queued`/`running` y "para eso" aborta ambas.
- **Atención (2.6):** relatar un `ask` **abre/refresca la ventana de atención** (`attention.note_directed()`) — la
  respuesta inmediata del operador es dirigida por definición; si no, en modo `smart`/`wakeword` la respuesta "enduro"
  no pasaría el gate y el caso estrella moriría.
- **Backpressure (2.7):** las suscripciones `worker.*` con `maxsize` + drop-oldest; coalescing de `phase` (patrón
  V2-037). Cuota de `say` por worker + batching en el tick del loop (un worker charlatán no monopoliza la voz).
- **Auth de bridges (2.8):** **token aleatorio por tarea** (`ZAELAR_TASK_TOKEN`) verificado en `/api/worker/*` (y en
  el existente `/api/agent/report`), loopback-only. Va en `WorkerSpec` desde el día uno — un `task_id` secuencial
  adivinable no basta (un worker manipulado por contenido podría actuar en nombre de otra tarea).

### E. Respuestas a las 7 preguntas abiertas (§14 RESUELTA)
- **Q1 (CLI vs SDK):** **CLI stream-json** ahora; el SDK es un wrapper del mismo CLI → la agnosticidad la da
  `WorkerBackend`, no esta elección. El SDK queda como posible refactor INTERNO del adaptador; su comodidad
  (`interrupt`/hooks) existe por debajo en el protocolo → implementamos `interrupt` como `control_request` si el CLI
  lo acepta. Nunca dejar que el SDK se filtre al contrato `WorkerEvent`.
- **Q2 (`ask`: long-poll vs bus):** **long-poll endurecido** — `hbask`/`hbact` registra la petición (POST → `corr_id`)
  y **re-pollea idempotente** (`GET /api/worker/act/{corr_id}`, ~25s/ciclo), respuesta guardada en el registry hasta
  reclamarse. Nada de `Future` atado a una conexión viva (frágil). Un reinicio devuelve error limpio → el worker
  decide.
- **Q3 (derivación de eventos):** **derivar solo lo mecánico** — `phase` (de cada `tool_use`), `result` (del mensaje
  `result`), `error`/`done` (del ciclo del proceso). **`say` y `ask` = SOLO explícitos** (`hbnote say`/`hbask`): un
  agente emite mucho texto intermedio; convertirlo en voz inundaría al operador. Además explícito = agnóstico
  (cualquier backend llama un CLI; no todos tienen stream parseable).
- **Q4 (generador de widgets):** **unificar el SUSTRATO, conservar el contrato.** El valor de `widgets/generator.py`
  (el `_CONTRACT`, la validación de acciones/background/CSS, el journal `_jobs`) se conserva íntegro como "receta de
  la tarea code"; solo se sustituye la EJECUCIÓN (`subprocess.run` → un `WorkerSession`). Así "crear widget" es
  matable/inyectable/observable de gratis y no quedan dos sustratos de subproceso.
- **Q5 (varios `ask` a la vez):** **cola FIFO con UN `ask` activo** (el relatado, con atribución); los demás esperan.
  La respuesta corta se enruta al `ask` ACTIVO, con backstop determinista por `options` si casa claramente con otro.
  `answer_worker(which, answer)` permite dirigir explícitamente. Un `ask` no relatado NO captura respuestas. Timeout
  por `ask` con re-relato una vez → "sin respuesta". Sin desambiguación por contenido libre del modelo pequeño.
- **Q6 (persistencia/`--resume`):** **matar-todo al reiniciar** ahora (el mundo externo del worker no sobrevive de
  todos modos) — PERO **capturar y persistir el `session_id` nativo** (del `init` de stream-json) junto a `goal`/
  `kind` en el journal DESDE EL DÍA UNO → "retomar el estudio tras un reinicio" será una feature (`--resume <sid>` +
  re-situación), no un rediseño (cumple O7).
- **Q7 (topes de coste/tiempo):** **tres capas** — (1) por worker: timeout de pared por kind + presupuesto de tokens
  (del `usage` que reporta stream-json); al 80% el supervisor AVISA y pregunta (nunca matar a ciegas a mitad); (2)
  por pool: `max_parallel` + presupuesto agregado de sesión/día con aviso; (3) por cadena: profundidad + cuota de
  `act spawn`. Todo por UI (invariante de producto). El único tope que ejecuta SOLO (sin preguntar) = emergencia
  (~3× presupuesto), trazado por `observer`.

### F. Simplificaciones adoptadas
- **`ask`+`act` = un plano** (ver B). **Piggyback = inyección principal** (ver A). **No duplicar la conciencia del
  FlashBrain**: el PROMPT (bloque "BRAIN WORKERS") es para asociar la orden del operador a su sesión EN EL TURNO; el
  LOOP es para actuar SIN turno (relatar `ask`, entregar, vigilar) — que nada dependa de que ambos vean lo mismo a la
  vez. **Etiquetas de fase baratas y con CAP** de caracteres (disciplina de prompt de V2-027).
- **Contrato:** cada `WorkerEvent` lleva `v` (versión de contrato) + `backend` — barato hoy, imprescindible cuando
  convivan adaptadores de generaciones distintas. `spawned` se unifica en la tabla de eventos (§5).
- **Prioridad de la voz:** los workers que usen el modelo rápido (`use_tool` con síntesis, 2º pases) se acotan contra
  `FastClient` para no competir NUNCA con un turno de voz vivo (el turno manda; los workers esperan).
- **Probe (trampa conocida del repo):** las tools nuevas + el bloque "BRAIN WORKERS" se cablean en
  `voice/engine/llm/providers/nucleo.py::_run` **Y** `nucleo/flash/probe.py` en el MISMO commit, con test que lo
  verifique.

---

## REVISIÓN v3 — CIERRE (Fable 5 · GO). Concreciones firmes para construir sin ambigüedad

> Veredicto de la puerta final: **GO**. Ninguna de estas afinaciones cambia una decisión de la v2; todas la
> CONCRETAN para que un implementador no tenga dos verdades ni resuelva un detalle a su aire. Mandan sobre el cuerpo.

### G. UN solo registro de sesiones absorbe los tres de hoy (cierra el cabo suelto nº1)
Hoy coexisten TRES registros parciales del mismo hecho: `nucleo/flash/escalate._tasks` (intenciones; alimenta
`summary_line()` y el dedup `_similar_pending` del provider), `dispatch._INFLIGHT` (etiquetas de chip) y
`dispatch._SESSIONS` (goal/fase). El **registro RAM de sesiones** (§v2·C) **los ABSORBE y reemplaza**:
- `escalate.pending()`/`summary_line()` y el **filler "sigo con ello"** del provider (`nucleo.py`) leen del registro
  nuevo; el bloque **"AHORA MISMO / BRAIN WORKERS EN MARCHA"** del prompt sale de él.
- `stop_worker` **cierra la escalada asociada** (equivalente a `escalate.finish`) → el prompt no anuncia tareas
  muertas.
- El **dedup V2-029 cambia de SEMÁNTICA**: el guard `_similar_pending` (`nucleo.py:~898-905`) pasa de **descartar**
  un refinamiento a **convertirlo en inyección** (`send_to_worker`). Documentarlo donde vive ese código.

### H. Ciclo de vida de una inyección (cola única, sin doble entrega, con timeout)
`send_to_worker`/refinamiento → **cola de inyección ÚNICA por tarea** con estados `pending → delivered`:
- La entrega la hace **el primer canal que llega** (piggyback en una respuesta de bridge **o** stdin/checkpoint) y
  **marca `delivered`** → el otro canal ya no la re-sirve (nunca doble).
- **Timeout de no-entrega**: si el worker no vuelve a contactar ni cierra turno (está terminando) y la instrucción
  no se entrega en `INJECT_TIMEOUT`, el supervisor lo convierte en aviso: *"no he podido pasarle lo del color, ¿la
  paro y la relanzo con el cambio?"* — el FlashBrain NO miente diciendo "hecho".

### I. Contrato de `hbask` frente al timeout del tool Bash
El re-poll (v2·E·Q2) corre DENTRO de una invocación de CLI que es un tool Bash del agente, con su propio timeout.
Un `ask` que espera minutos lo agotaría. Contrato: **`hbask` retorna ANTES del timeout del tool** con un resultado
explícito `"sin respuesta aún — reintenta con: hbask wait <corr_id>"`; el prompt del worker enseña ese bucle de
espera reentrante (o se sube el timeout de Bash por env en el spawn). Detalle de contrato del bridge, fijado aquí.

### J. Tabla de política del plano `act` (completa, incl. built-ins)
| acción                    | política                    | nota |
|---------------------------|-----------------------------|------|
| `ask_user`                | ALLOW (con cap por worker)  | atribución obligatoria al relatar |
| `use_tool:<prestable>`    | ALLOW                       | solo tools marcadas "prestable a workers" (catálogo filtrado) |
| `read_widget`             | ALLOW                       | lectura |
| `show_widget`/`close_widget` | ALLOW                    | reversible y visible |
| `push_channel` (externo)  | CONFIRM + `scan_outbound`   | ver K |
| `spawn` (encadenar)       | ALLOW dentro de cuota/profundidad; **DENY al exceder** | si fuera CONFIRM, las cadenas de ★.7 morirían pidiendo permiso a cada eslabón |
| tools **operator-only**   | **DENY duro**               | `authenticate_web`/`login_done`/`confirm_widget_delete`/`set_style_directive` |

### K. El CONFIRM de un `act` = un `ask_user` auto-generado (cero mecanismo nuevo)
`widgets/confirm.py` es un overlay sobre una TARJETA; un `act push_channel` puede no tener tarjeta. Un `act` con
política **CONFIRM** se **transforma en el server** en un `ask_user` auto-generado (*"el worker de X quiere enviar Y
al canal Z — ¿lo hago?"*) con la acción RETENIDA; el "sí" la ejecuta y resuelve el `corr_id` original. Es el mismo
plano respondiéndose a sí mismo (aprovecha la fusión de v2·B).

### L. Lifespan: apagado ordenado + barrido de huérfanos + purga al matar
- **Shutdown del server:** `cancel_all()` corre **ANTES** de parar el loop y el listener (si no, los pipes asyncio
  mueren con el loop y los grupos de proceso quedan vivos, el bug de hoy).
- **Arranque:** **barrido de huérfanos** de procesos-worker de sesiones previas (un `kill -9`/crash del server no
  deja rastro en el registro RAM) — identificables por marcador de env/grupo, igual que ya se hace con los
  `chrome-headless-shell` en `run-livekit.sh` (V2-036).
- **Al matar una sesión:** purgar sus entradas del registry de `act`/`ask` **y** su cola de inyección (si no, el loop
  intentará relatar la pregunta de un muerto).

### M. Precedencia determinista de "pendientes de respuesta" (cablear en provider Y probe)
Con esta iniciativa un "sí"/palabra suelta puede responder a: confirmación de borrado, login pendiente, o el `ask`
activo de un worker. **Orden ÚNICO de interpretación de un turno corto** (idéntico en `nucleo.py::_run` y `probe.py`):
```
hard_interrupt  >  confirm de widget pendiente  >  match por `options` del ask activo  >
login pendiente  >  ask activo (respuesta libre corta)  >  turno normal
```
Sin esta tabla, la precedencia la decide el orden accidental de los `if`.

### N. Eco vs respuesta corta a un `ask`
Relatar un `ask` abre la ventana de atención (v2·D), pero el provider tiene supresión de eco (`nucleo.py:~124-136`,
ventana 12s + `similar(thr=0.82)`). zaelar dice *"¿enduro o cross?"* y el operador responde *"enduro"* (palabra
contenida en lo último hablado, dentro de la ventana). Regla: **el turno inmediato tras relatar un `ask` queda EXENTO
del descarte por eco**. Va al criterio de aceptación (§15).

### O. `WorkerSpec` y prioridad de voz (fija los campos que las decisiones exigen)
- `WorkerSpec` gana: `token` (auth de bridges, v2·D), `parent_task_id` + `depth` (límites de `spawn`, v2·B),
  `budget` (topes Q7), y se **persiste el `session_id` nativo** en el journal (Q6).
- **Invariante V2-011 (crítico):** los handlers de `send_to_worker`/`stop_worker`/`answer_worker` en el provider son
  **fire-and-forget** (patrón `_spawn` que ya existe en `nucleo.py`), **NUNCA** `await` de una operación de worker
  dentro del turno (un `stop()` con grace de 3s esperado en el turno rompería la latencia de voz).
- **Serialización por widget-id** en la tarea `code` al unificar el generador (Q4): NO el `_lock` global de
  `generator.py` (mataría el paralelismo del pool), sino un lock por id de widget en `dispatch`.
- **Presupuesto sin `usage`:** un backend que no reporte consumo (posible Codex) → la capa-1 de Q7 cae a **tope por
  tiempo**.

### P. Invariante escrito: `deny_tools` ⇒ SIN bridges
Un worker no confiable (input de cluster, V2-010) **no tiene Bash → no tiene `hbask`/`hbact`/`hbmem`/`hbweb`** (hoy
`claude_code.py:~93-100` ya solo añade `_MEM_TOOLS` en la rama con tools; se ELEVA a invariante escrito en §12). Un
`ask` redactado por input hostil sería ingeniería social con la voz de zaelar.

### (Correcciones de higiene aplicadas al cuerpo)
`§7.4` (inyección ya no "no usa bridge") · `§10`/`§11.1` (refinar = `dispatch.inject`, no `backend.send→stdin`) ·
`§11.2` (sin `Future` atado a conexión ni `set_state` por-evento) · `§5`+`§6.1` (`say` NUNCA derivado del stream;
mapeo `tool_use→phase`, `result→result`, ciclo→`error/done`, texto assistant→nada) · `§6.4` (Q4 cerrada) · `§13`
(endpoint ÚNICO `/api/worker/act`; sync-ESTADO lo hace el LOOP, no `session.py`; añadir `hbnote say`).

---

## ★ VISIÓN Y OBJETIVO DE CONSTRUCCIÓN (lo que persigue el operador)

> Esta sección es la INTENCIÓN, en las palabras del operador (recogida de la conversación de diseño 2026-07-14).
> Es el "para qué"; el resto del documento es el "cómo". Si el cómo no sirve a esto, gana esto.

**Qué queremos conseguir:** un asistente **inteligente de verdad**, capaz de lanzar y **gobernar con vida propia**
un conjunto de subprocesos —los **Brain Workers**— que hacen el trabajo lento y real (manejar un widget, conducir un
navegador, crear/modificar un widget, modificar datos, hacer un estudio…), mientras el **FlashBrain** sigue
atendiendo al usuario por voz/chat en tiempo real. Hoy esos procesos son callejones sin salida (un tiro y mueren);
queremos que **vivan, se comuniquen y encadenen conocimiento y acción**.

**El FlashBrain es el EPICENTRO y el ORQUESTADOR de TODO.** No solo contesta al usuario: gobierna los procesos, los
canales de WebSocket externos, y las interfaces (voz, chat). Todo pasa por él. Lo hace en una **especie de loop
continuo** que, **sin sobrecargarse de tokens**, a partir del **ESTADO** sabe qué hay en marcha y qué le toca ir
haciendo — además de responder a lo que el usuario le pide en cada momento. Cuando hay cosas en marcha, las **va
controlando** (¿avanza?, ¿se encalló?, ¿necesita algo del usuario?, ¿hay que entregar un resultado?).

**Funcionalidades que DEBEMOS permitir (lo que este agente tiene que ser capaz de hacer):**
1. **Lanzar Brain Workers** y que se ejecuten de forma autónoma y asíncrona, sin bloquear la voz.
2. **Comunicación worker → FlashBrain**: cada worker puede hablar con el cerebro mientras trabaja (reportar,
   preguntar, pedir).
3. **Nuevas órdenes a un proceso en marcha** (inyección): **actualizar su objetivo**, **modificar los resultados**
   que ya está produciendo, o **ampliar funcionalidades/alcance** de la tarea — sin abrir otra tarea nueva. Ejemplo
   real del operador: una búsqueda de moto en curso a la que se le dice "además, que sea de color verde".
4. **Interacción del worker con el USUARIO** cuando haga falta — pero SIEMPRE a través del FlashBrain (el worker
   nunca habla directo; el FlashBrain relata la pregunta por voz y le devuelve la respuesta).
5. **El FlashBrain presta sus HERRAMIENTAS a los workers.** Si un worker no puede hacer algo por sí mismo (p.ej. una
   búsqueda web) pero el FlashBrain SÍ tiene esa capacidad como **tool** (`web_search` hoy, y **más tools en el
   futuro**), el worker se lo pide, el FlashBrain **ejecuta la tool y le devuelve el resultado**. El catálogo de
   capacidades del FlashBrain queda así disponible, mediado, para todos los workers — y crece con el sistema.
6. **El FlashBrain actúa sobre múltiples superficies**: los procesos (workers), **canales de WebSocket externos**,
   la **interfaz de usuario** (widgets del canvas), la **voz** y el **chat**. Dependencias y acciones cruzadas: un
   worker genera acciones en la UI o en un canal externo, y eso lo coordina el FlashBrain.
7. **Encadenamiento**: un worker puede desencadenar más trabajo (pedir al FlashBrain que dispare otra tarea, que lea
   otro widget, que consulte memoria…) → **cadenas de conocimiento y de acción continua**, no procesos aislados.
8. **Control por el ESTADO, no por tokens**: el FlashBrain se entera de todo lo que hay en marcha por el ESTADO
   compartido (barato, sin retriever), no metiendo el historial de cada worker en su prompt. Ligero por diseño.
9. **Todo esto de forma robusta y aislada**: N workers a la vez, cada uno aislado (uno que revienta o se encalla no
   tumba la voz ni a otro), matable a voluntad ("para eso"), y con la memoria intacta (escritor único).

**El objetivo NO NEGOCIABLE:** que esta arquitectura **lo soporte todo y no haya que rediseñarla otra vez**. Debe ser
lo bastante general para tareas que aún no existen, y **agnóstica del motor** de los workers (Claude Code hoy; Codex,
Cursor o Hermes mañana, incluso mezclados) — porque el motor concreto es una decisión que cambiará con el tiempo.

---

## 1. Contexto y problema (por qué AHORA)

### 1.1 Lo que hay (V2-036)
- `escalate_to_slowbrain(request)` → `bus:escalate.requested` → `nucleo/dispatch.py::run_listener` crea una `Task`
  y la despacha a un **worker Claude Code headless** (`nucleo/agentes/{worker,web_cc,code}.py`) vía la interfaz
  `CodeAgent` (`nucleo/agentes/base.py`), adaptador `claude_code.py` (`claude -p --output-format json`).
- Puentes **de subida** (worker → sistema), ya existentes y valiosos: `hbmem` (recall/remember), `hbnote` (reporte
  de fase → `dispatch.session_phase` → ESTADO), `hbweb` (conducir el navegador). Son CLIs que el worker ejecuta por
  Bash y hablan por HTTP con el server vivo → preservan el escritor único de memoria.
- El resultado vuelve por `voice/proactive` (voz+UI) + nota `[SISTEMA]`.

### 1.2 Lo que NO puede hacer (los fallos de raíz, confirmados con la sesión manual 2026-07-14 13:28)
1. **No hay canal DESCENDENTE.** No se le puede inyectar una instrucción nueva a un worker en marcha ("además, la
   moto en verde"). Hoy eso abre OTRO worker o se descarta como "duplicado" (hack de dedup de V2-029).
2. **No hay canal ASCENDENTE con respuesta.** Un worker no puede preguntar al usuario ("¿enduro o cross?") ni pedir
   una acción al FlashBrain ("léeme el widget X", "empuja esto al canal externo") y **esperar** la respuesta.
3. **No se puede MATAR.** `dispatch._run_and_deliver` se crea con `asyncio.create_task` **sin guardar el handle** →
   nada apunta a una sesión concreta. Peor: crear un widget corre por `widgets/generator.py::subprocess.run`
   **bloqueante** dentro de `asyncio.to_thread`, y `to_thread` **no es cancelable** → el subproceso sigue hasta el
   final. Y `claude -p` solo se mata por timeout; en cancelación queda **huérfano**. El HARD RESET
   (`nucleo/reset.py`) solo LIMPIA el registro de intenciones (`escalate.reset()`), no mata los procesos.
4. **El estado no es la fuente de verdad de la UI.** Los chips de actividad del orbe (`ActivityStrip`) son puro
   `start`/`end` por eventos: una tarea matada nunca emite `end` → **chip huérfano para siempre**; y no hay
   reconciliación al (re)conectar. Es una "pieza inconexa", no un espejo del estado real.

### 1.3 Evidencia (timeline 13:28)
`task id=1` (crear widget, no pedido) → "No pude crear el widget"; los intentos de parar generaron tareas nuevas
`id=5,6,3`; una preguntó confirmación de *"cancelar todas las sesiones de Cloud Code… irreversible"* y otra creó un
**widget basura** titulado `sistema-slowbrain-tarea-completada-te-mu` (la orden de parar convertida en widget). Tres
chips "Creando un widget…" a la vez cuando el operador solo quería parar el primero.

---

## 2. Objetivos y No-objetivos

### Objetivos
- **O1 — Agent-agnóstico.** El motor de razonamiento de un worker (Claude Code / Codex / Cursor / Hermes) es un
  **backend sustituible por configuración**, por tipo de tarea, y **combinable** (Claude para web + Codex para código
  a la vez). El resto del sistema NO conoce el backend.
- **O2 — Bidireccional.** (↓) Inyectar instrucciones a un worker vivo. (↑) Un worker informa su progreso al ESTADO,
  PREGUNTA al usuario y PIDE acciones al FlashBrain, y puede **disparar iteraciones del FlashBrain** para continuar.
- **O3 — Matable y observable.** Parar un worker concreto ("para eso") con cortesía; el ESTADO es la fuente de verdad
  y la UI su espejo (nada de chips huérfanos).
- **O4 — Supervisado.** El loop del FlashBrain vigila los workers: encallamiento, preguntas pendientes, timeouts,
  entrega de resultados.
- **O5 — Async y aislado.** N workers en paralelo (pool), cada uno aislado: un worker que revienta/encalla nunca
  tumba la voz ni a otro worker ni al planificador. Memoria: escritor único preservado, lecturas concurrentes.
- **O6 — Latencia intacta.** Nada de esto entra en la ruta caliente de voz (V2-011): el turno de voz nunca hace I/O
  de worker/memoria síncrono; la interacción va por el bus/loop off-hot-path.
- **O7 — "No modificar más".** El contrato (WorkerEvent + backend + planos de comunicación) debe ser lo bastante
  general para soportar tareas que aún no existen sin rediseño.

### No-objetivos (de esta iniciativa)
- Reescribir la memoria (`memory/`) — se USA tal cual (escritor único, ESTADO/CORTO/LARGO).
- Cambiar el motor de voz LiveKit ni el gate de atención (se INTEGRA con ellos).
- Añadir un broker externo (Kafka/Redis). El bus in-process sigue siendo el sustrato.
- Multi-máquina / workers remotos (se deja como extensión futura; el diseño no lo impide).

---

## 3. Modelo mental nuevo

```
                        ┌──────────────────────────────────────────────┐
                        │                 OPERADOR (voz)                │
                        └───────────────▲───────────────┬──────────────┘
                                        │ voz+subtítulos │ habla
                                        │                ▼
   ┌───────────────────────────────────┴───────────────────────────────────┐
   │                       FLASHBRAIN  (orquestador)                         │
   │  · atiende cada turno de voz (~1s, no-razonador)                        │
   │  · DECIDE: charla · widget_data · web_search · NUEVO worker ·           │
   │           INYECTAR a worker vivo · RESPONDER pregunta de worker ·       │
   │           MATAR worker                                                  │
   │  · LOOP supervisor (~1 Hz): vigila workers (encallado / pregunta        │
   │           pendiente / timeout / entrega de resultados)                  │
   └───▲───────────────┬─────────────────────────────────────▲─────────────┘
       │ ESTADO (prompt)│ inyectar (↓) / matar                 │ ask/act (↑, request-response)
       │                │                                      │  say/phase/result (↑, bus)
   ┌───┴──────┐   ┌─────▼───────────────────────────────────────┴───────────┐
   │  MEMORIA │   │                 BUS  (sistema nervioso)                  │
   │  ESTADO  │◄──┤  worker.spawned/phase/say/ask/act/result/done/killed     │
   └───▲──────┘   └───▲───────────────▲───────────────▲──────────────────────┘
       │              │               │               │
       │        ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
       │        │  Brain    │   │  Brain    │   │  Brain    │     … N (pool)
       └────────┤  Worker A │   │  Worker B │   │  Worker C │
        hbmem   │ (web/nav) │   │ (widget   │   │ (estudio) │
                │  Claude   │   │  código)  │   │  Codex)   │  ← backends MEZCLABLES
                └───────────┘   │  Claude   │   └───────────┘
                                └───────────┘
```

- Muere el "gran SmartBrain". Nacen **Brain Workers**: procesos lentos, independientes, especializados (manejar un
  widget, conducir el navegador, crear/modificar un widget, hacer un estudio…).
- El **FlashBrain es el ÚNICO que habla con el usuario** y el ÚNICO orquestador. Los workers NUNCA hablan directo al
  usuario: piden al FlashBrain que hable por ellos.
- Todo lo que un worker "sabe/necesita" pasa por **ESTADO+memoria** (asíncrono) y/o por el **bus**.

---

## 4. Principio rector: agent-agnóstico (O1)

Es el requisito nº1 del operador. Se resuelve con **una sola costura de abstracción** que ya existe en germen
(`nucleo/agentes/base.py::CodeAgent`), evolucionada de "un tiro" a **sesión interactiva**:

### 4.1 `WorkerBackend` — la interfaz (evolución de `CodeAgent`)
```python
class WorkerBackend(Protocol):
    name: str                                   # "claude_code" | "codex" | "cursor" | "hermes"
    async def start(self, spec: WorkerSpec) -> None      # arranca la sesión VIVA (no bloquea hasta el fin)
    async def send(self, text: str) -> None              # (↓) inyecta una instrucción nueva como turno
    def events(self) -> AsyncIterator[WorkerEvent]       # (↑) stream NORMALIZADO de eventos del agente
    async def stop(self, *, grace: float = 3.0) -> None  # cierre con cortesía: fin-de-entrada → SIGTERM → SIGKILL
    @property
    def alive(self) -> bool
```
- **Clave de la agnosticidad:** cada backend TRADUCE su protocolo nativo (Claude stream-json, el formato de Codex,
  el ACP de Hermes) al **MISMO vocabulario `WorkerEvent`**. Dispatch, FlashBrain, ESTADO y UI **solo hablan
  `WorkerEvent`** — nunca conocen el CLI concreto. Cambiar de backend = cambiar una entrada de config; mezclar
  backends = instanciar distintas clases. Esto es lo que hace el sistema "sustituible" y "no modificable".

### 4.2 `WorkerSpec` (evolución de `RunSpec`)
```python
@dataclass
class WorkerSpec:
    kind: str                 # "web" | "code" | "memory" | "research" | "generic"
    model: str = ""           # MODELO POR INVOCACIÓN (jamás env global) — se mantiene la regla V2-036
    tools: list[str] | None = None
    cwd: str | None = None
    deny_tools: bool = False  # input no confiable (V2-010) → sin tools
    env: dict[str,str] = {}
    trusted: bool = True
    task_id: str = ""         # id de sesión (para bridges/estado/kill)
    # ⚠️ v3·O — campos que exigen las decisiones:
    token: str = ""           # auth por-tarea de los bridges (§v2·D) — aleatorio, verificado en /api/worker/*
    parent_task_id: str = ""  # cadena (act spawn); depth acota la profundidad (§v2·B)
    depth: int = 0
    budget: dict = {}         # topes de tokens/tiempo por worker (§v2·E·Q7; fallback a tiempo sin `usage`)
    # (el session_id NATIVO del backend se captura al vuelo y se persiste en el journal — §v2·E·Q6)
```

### 4.3 Selección de backend (config, por tipo de tarea, mezclable)
- Extiende lo que ya hay: `config/v2.py §code_agent` con `provider` + overrides por tipo
  (`provider_web`/`provider_code`/`provider_research`…) y `model_*`. `get_backend(spec)` (evolución de
  `get_agent()`) devuelve la instancia del backend correcto por tarea. Gestionado por la UI (invariante de producto).

---

## 5. `WorkerEvent` — el vocabulario NORMALIZADO (el contrato central)

Todo evento lleva `task_id` + `ts`. Es la lengua franca entre backends y orquestador. **Este contrato es el corazón
de "no modificar más": si es lo bastante rico, cubre tareas futuras.**

> ⚠️ **v2:** (1) cada evento lleva además `v` (versión de contrato) + `backend`. (2) `ask` y `act` se FUSIONAN en un
> único plano request/response (`ask` = `act action="ask_user"`) — ver §REVISIÓN v2·B. (3) La columna "→ ESTADO" de
> `phase` NO se escribe por-evento: el ESTADO es una proyección coalescada por el loop (§REVISIÓN v2·C); el pump solo
> actualiza el registro en RAM. (4) `spawned` es un evento válido (unificado aquí).

| Tipo       | Payload                                   | Semántica / a dónde va |
|------------|-------------------------------------------|------------------------|
| `phase`    | `{label}`                                 | Progreso ("navegando a Wallapop"). → ESTADO (`sessions[].phase`) + SSE chip. |
| `say`      | `{text}`                                  | El worker quiere DECIR algo al usuario (informativo, no bloquea). → FlashBrain lo relata por voz+UI. |
| `ask`      | `{question, options?, corr_id, timeout?}` | El worker NECESITA respuesta del usuario para continuar. **Bloquea** al worker. → request/response (§7.2). |
| `act`      | `{action, payload, corr_id?}`             | El worker pide una ACCIÓN que solo el host/FlashBrain hace: leer/abrir/cerrar un widget, empujar a un canal WS externo, disparar otra tarea… → §7.3. Puede o no esperar respuesta. |
| `result`   | `{summary, ok, data?}`                    | Entregable final de la tarea. → voz+UI + `memory_agent.remember` + `[SISTEMA]`. |
| `progress` | `{pct?, note?}`                           | Avance cuantitativo opcional (barra). → SSE. |
| `error`    | `{message, fatal}`                        | Fallo. `fatal` → cierra la sesión. → observer + posible aviso al usuario. |
| `done`     | `{}`                                      | La sesión terminó (con o sin `result`). → limpieza + chip fuera. |

- `say`/`phase`/`result`/`progress`/`error`/`done` → **plano de control (bus)**, fire-and-forget.
- `ask`/`act` (los que esperan respuesta) → **plano request/response** (§7.2/7.3).
- Derivación automática (⚠️ **v3**, acotada por §v2·E·Q3): el backend deriva del stream nativo SOLO lo mecánico —
  `tool_use`→`phase`, `result`→`result`, ciclo del proceso→`error`/`done`. El **texto `assistant` NO se deriva a
  `say`** (un agente emite mucho monólogo interno; inundaría al operador). `say` y `ask` son **SIEMPRE explícitos**
  (`hbnote say` / `hbask`) — además es lo agnóstico (cualquier backend llama un CLI; no todos tienen stream
  parseable). Los bridges son la vía EXPLÍCITA y fiable para lo que llega al usuario o requiere respuesta.

---

## 6. Backends concretos

### 6.1 `ClaudeCodeSession` (backend por defecto, disponible YA)
- `claude --print --input-format stream-json --output-format stream-json --model <m> --allowedTools "<...>"
  --permission-mode acceptEdits`.
- **Verificado** en el CLI instalado (`--input-format stream-json` = "realtime streaming input"; `--output-format
  stream-json` = "realtime streaming"; + `--resume`/`--fork-session`). El proceso **VIVE**.
- `send(text)` → escribe una línea JSON `{"type":"user","message":{"role":"user","content":text}}` a **stdin**.
  ⚠️ **v2:** stdin **se encola hasta que cierra el turno** (un worker agéntico = un turno largo) → `send()` es la vía
  SECUNDARIA de inyección; la PRINCIPAL es piggyback en los bridges (§REVISIÓN v2·A). Lanzar con
  `start_new_session=True` para poder matar el GRUPO de procesos (§REVISIÓN v2·D).
- `events()` → lee stdout línea a línea, parsea los objetos stream-json de Claude y los MAPEA a `WorkerEvent`
  (⚠️ **v3**: `tool_use`→`phase`; `result`→`result`; ciclo del proceso→`error`/`done`; **texto `assistant`→nada**
  —o telemetría interna—, NUNCA `say`; ver §v2·E·Q3).
- `stop()` → cierra stdin (fin de entrada) → SIGTERM → espera `grace` → SIGKILL. Cortesía = lo más cercano a "pídele
  que pare" (idea del operador) que da un proceso; un `claude` matado a mitad de escribir un widget deja carpeta a
  medias que el generador **descarta** + la validación rechaza → seguro.

### 6.2 `CodexSession` (adaptador, mismo contrato)
- Mismo patrón con el CLI/So de Codex (streaming si lo soporta; si no, degradación a "un tiro por instrucción" con
  `send` re-arrancando contexto vía `--resume`/session-id). Se implementa DETRÁS del mismo `WorkerBackend`.

### 6.3 `HermesSession` / `CursorSession` (futuros)
- Hermes se reincorpora como backend de tareas (ACP → `WorkerEvent`) SIN tocar el orquestador. Cursor idem. El coste
  de añadir un motor nuevo = escribir un adaptador que hable `WorkerEvent`. Ese es el retorno de la abstracción.

### 6.4 El caso especial del **generador de widgets** (unificación)
Hoy `widgets/generator.py` usa `subprocess.run` bloqueante propio (no pasa por `claude_code.py`). Para que "crear/
modificar un widget" sea también interactivo y matable, se **unifica** bajo el mismo sustrato: la tarea `code` de
widget se conduce por un `WorkerSession` (backend por config), y el generador pasa a exponer sus operaciones como
**acciones que el worker invoca** (o el worker escribe los ficheros directamente con Write/Edit gated + validación).
⚠️ **v3 (Q4 CERRADA):** se **unifica el SUSTRATO conservando el CONTRATO**. El valor de `widgets/generator.py` (el
`_CONTRACT`, la validación de acciones/background/CSS, el journal `_jobs`) se conserva íntegro como "receta de la
tarea `code`"; solo se sustituye la EJECUCIÓN (`subprocess.run` → un `WorkerSession`). "Crear widget" pasa a ser
matable/inyectable/observable de gratis y sin dos sustratos de subproceso. Serialización **por widget-id** (no el
`_lock` global), ver §REVISIÓN v3·O. La alternativa "envolver en Popen" queda DESCARTADA (deuda desde el día uno).

---

## 7. Los planos de comunicación

> ⚠️ **v2:** `ask` y `act` (§7.2/§7.3) se FUSIONAN en UN plano request/response con política ALLOW/CONFIRM/DENY por
> acción evaluada en el server, y `use_tool` lee un catálogo FILTRADO (no todo `router.TOOLS`). Ver §REVISIÓN v2·B.
> La inyección (↓) es principalmente por piggyback en bridges, no por stdin (§REVISIÓN v2·A). Los bridges se
> autentican con token por tarea (§REVISIÓN v2·D). Lo que sigue es el razonamiento; la forma firme está arriba.

El operador dejó la elección ("por el event bus o comunicándote con alguien que te escucha en el FlashBrain").
Decisión: **LOS DOS, por capas, cada uno para lo suyo.** Es lo que mantiene cada pieza simple y cubre todos los flujos.

### 7.1 Plano de CONTROL = el bus (async, fan-out, sin respuesta)
- Todos los `WorkerEvent` informativos (`spawned/phase/say/result/progress/error/done/killed`) se publican en el bus
  con topic `worker.*`. De ahí salen: **SSE** (`/events` → UI: chips, feed), **ESTADO** (`sessions`), **conciencia
  del FlashBrain** (loop + prompt). Es "cada instancia emite eventos en un canal abierto" de la idea del operador.
- El FlashBrain **recibe** por dos vías equivalentes: (a) el ESTADO ya lleva el resumen de workers en cada prompt;
  (b) el **loop supervisor** (§8) está suscrito a `worker.*` y reacciona.

### 7.2 Plano REQUEST/RESPONSE = pregunta que ESPERA (`ask`)
Un worker que pregunta y debe **esperar** necesita semántica de request/response que el bus fire-and-forget no da
limpio. Diseño:

> ⚠️ **v3:** el diagrama de abajo es CONCEPTUAL. En la forma firme: NO hay `Future` atado a una conexión — es
> **re-poll idempotente** (`hbask`→POST devuelve `corr_id`, luego `GET /api/worker/act/{corr_id}` ~25s/ciclo,
> respuesta guardada hasta reclamarse; §v2·E·Q2 + §v3·I). NO se hace `set_state` por-evento — `waiting_on` vive en el
> **registro RAM** y el ESTADO se proyecta desde el loop (§v2·C). Endpoint ÚNICO `/api/worker/act` (`ask`=`act
> ask_user`, §v2·B).
```
worker (bridge `hbask "¿enduro o cross?"`)
   └─POST /api/worker/ask {task_id, question, corr_id}   ── el CLI se queda LONG-POLLING la respuesta ──┐
        server: aparca la pregunta en `AskRegistry[corr_id]` (Future) + set ESTADO sessions[].waiting_on="user"
        + emite bus `worker.ask`                                                                        │
   FlashBrain loop ve la pregunta pendiente → la RELATA al usuario por voz ("El buscador pregunta:      │
        ¿la prefieres de enduro o de cross?")  [respeta gate de atención / no interrumpe grosero]       │
   usuario responde por voz → el provider detecta que hay un `ask` pendiente (determinista, como el     │
        confirm-gate) → resuelve `AskRegistry[corr_id]` con la respuesta                                │
   server: el long-poll de `hbask` RETORNA la respuesta ──────────────────────────────────────────────┘
   worker continúa con la respuesta ("vale, filtro por enduro verde")
```
- Correlación por `corr_id`. Timeout configurable → el worker recibe "sin respuesta" y decide (seguir con un
  supuesto, esperar, o abortar). El FlashBrain también puede **responder él mismo** sin molestar al usuario si el
  dato está en memoria/estado (decisión del turno).

### 7.3 Plano de ACCIÓN mediada (`act`) — el FlashBrain PRESTA sus capacidades al worker
Un worker pide algo que solo el host/FlashBrain puede hacer, o que el FlashBrain hace MEJOR porque tiene la
capacidad como tool. **Este es el punto donde el FlashBrain presta su catálogo de HERRAMIENTAS a los workers**
(requisito explícito del operador, §★.5):
- **Usar una TOOL del FlashBrain** (`act use_tool {tool, args}`) → si el worker no puede hacer algo por sí mismo
  pero el FlashBrain sí (hoy `web_search`; **mañana cualquier tool nueva del catálogo**), lo pide y el FlashBrain
  **ejecuta la tool y le DEVUELVE el resultado**. Así el poder del FlashBrain crece con el sistema y queda disponible,
  mediado, para todos los workers — sin que cada backend tenga que reimplementar búsquedas ni integraciones.
- **Leer un widget** (`act read_widget {id}`) → el server llama a `widgets/runtime.view_data` → devuelve al worker.
- **Abrir/cerrar/mostrar un widget** en el canvas (`act show_widget`/`close_widget`) → el FlashBrain emite el tag.
- **Empujar a un canal externo** (`act push_channel {channel, payload}`) → p.ej. un WebSocket externo/cluster.
- **Disparar otra tarea** (`act spawn {request, kind}`) → el worker ENCADENA otro Brain Worker (cadenas de acción).
- Con o sin respuesta (usa el mismo mecanismo de §7.2 si espera resultado).
- Bridge: `hbact <action> <json>`.

> **Nota de futuro (importante para no rediseñar):** `use_tool` debe leer el MISMO catálogo de tools que ofrece el
> FlashBrain en su turno (`nucleo/flash/router.TOOLS`), de modo que **toda tool nueva que se añada al FlashBrain
> quede automáticamente disponible para los workers** sin tocar este plano. El catálogo es la única fuente.

### 7.4 Puentes CLI (agent-agnósticos, estables)
El worker (cualquier backend) interactúa por un set PEQUEÑO y ESTABLE de CLIs gated por Bash — iguales sea cual sea
el motor, lo que mantiene la agnosticidad también en esta capa:
| Bridge | Existe | Función |
|--------|--------|---------|
| `hbmem recall/remember` | sí | memoria (serial, escritor único) |
| `hbnote phase` | sí | reporte de fase (además de la derivación automática del stream) |
| **`hbnote say "<txt>"`** | NUEVO | DECIR algo al usuario (explícito; `say` no se deriva del stream, §v2·E·Q3) |
| `hbweb …` | sí | conducir el navegador |
| **`hbask "<q>"`** | NUEVO | preguntar al usuario/FlashBrain y ESPERAR respuesta (azúcar de `hbact ask_user`; §v3·I) |
| **`hbact <action> <json>`** | NUEVO | pedir una acción mediada (plano único; política ALLOW/CONFIRM/DENY §v3·J) |
| — todos los bridges | — | autenticados con **token por-tarea** (§v2·D); `deny_tools`⇒SIN bridges (§v3·P) |
- La INYECCIÓN (↓) la dispara el FlashBrain vía `dispatch.inject(which, msg)` → **cola de inyección** entregada
  principalmente por **piggyback en las respuestas de bridge** (`stdin`/checkpoint como entrega alternativa). Ver
  §REVISIÓN v2·A + §REVISIÓN v3·H (ciclo de vida `pending→delivered` sin doble entrega). `hbnote say` = decir algo al
  usuario (explícito, §v2·E·Q3).

---

## 8. El LOOP supervisor del FlashBrain (O4)

> ⚠️ **v2:** el encallamiento se detecta con el **heartbeat** del protocolo de turnos cortos (§REVISIÓN v2·A), no
> solo por ausencia de `phase`. El loop sincroniza el ESTADO desde el registro en RAM (§REVISIÓN v2·C) y batchea los
> `say` (§REVISIÓN v2·D). Todo comando que el loop mande a una sesión se marshalea a su loop dueño (§REVISIÓN v2·D).

`nucleo/loop.py` (~1 Hz, ya existe: cron + proactividad + consolidación) asume la **supervisión de workers**. En cada
tick, además de lo suyo:
1. **Encallamiento**: worker sin `phase`/evento nuevo en `STUCK_SECS` → acción escalonada: (a) inyectar un "¿cómo
   vas?" suave, (b) si sigue mudo, informar al usuario ("la búsqueda lleva 3 min sin avanzar, ¿insisto o la paro?"),
   (c) opción de subir a un modelo más fuerte (`model_strong`).
2. **Preguntas pendientes**: si hay `ask` sin relatar y el momento es oportuno (gate de atención, no pisar al usuario)
   → relatarla por voz.
3. **Timeouts**: worker que supera `MAX_SECS` → avisar + ofrecer matar (no matar a ciegas).
4. **Entrega**: `result`/`say` pendientes → voz+UI (raíl `proactive` existente).
5. **Sincronía de ESTADO**: refresca `sessions` (fase, edad, `waiting_on`, último evento) → memoria de ESTADO.

Esto es literalmente lo que pidió el operador: "el FlashBrain tiene un loop que cada X mira si tiene algo que hacer y
controla cómo están los procesos".

---

## 9. Impacto en ESTADO + memoria

### 9.1 ESTADO (`memory/state.py` → `state.sessions`)

> ⚠️ **v2:** la FUENTE DE VERDAD es el **registro en RAM de `dispatch`**; el ESTADO es una **proyección coalescada**
> que el loop (~1 Hz) sincroniza solo si cambió. `GET /api/tasks` lee el registro en RAM. Ver §REVISIÓN v2·C. Esto
> elimina el flood de SQLite por-evento y las sesiones fantasma tras un reinicio.
De la forma pobre actual `{id, goal, phase}` a:
```json
sessions: [
  { "id":"7", "kind":"web", "backend":"claude_code", "goal":"moto de enduro verde",
    "phase":"filtrando anuncios", "started":"…", "age_s":42,
    "waiting_on":"user", "ask":"¿enduro o cross?", "last_event":"ask", "pct":60 }
]
```
- Viaja SIEMPRE en el prompt del FlashBrain vía `memory_cache` (off-hot-path, V2-011: recompone fuera del loop al
  `memory.updated`). El prompt gana un bloque **"BRAIN WORKERS EN MARCHA"** (qué corre, en qué fase, cuál ESPERA tu
  respuesta y a qué).
- Se sirve por **`GET /api/tasks`** (read-only) → el frontend RECONCILIA sus chips (fin de la pieza inconexa).
- Visible en el mapa de memoria (columna ESTADO), como hoy.

### 9.2 Memoria (sin cambios de contrato)
- Escritor único preservado; workers usan `hbmem`. Resultados recordados como hoy. Lecturas concurrentes (WAL).
- Nada de I/O de worker en la ruta caliente de voz (O6/V2-011).

---

## 10. Routing del FlashBrain: la inteligencia de orquestación

> ⚠️ **v3:** (1) REFINAR un worker = `dispatch.inject(which,msg)` → cola de inyección (piggyback), NO
> `backend.send→stdin` directo (§v3·H). (2) El dedup V2-029 (`_similar_pending`) ya NO descarta: **convierte** el
> refinamiento en inyección (§v3·G). (3) La interpretación de un turno corto sigue la **tabla de precedencia
> determinista** de §v3·M (confirm > options-del-ask > login > ask libre > normal), cableada en provider Y probe.

Cada turno de voz, el FlashBrain (con el bloque "BRAIN WORKERS EN MARCHA" en su prompt) decide entre:
| Intención del operador | Acción | Mecanismo |
|---|---|---|
| Tarea NUEVA ("búscame una moto") | arrancar worker | `escalate_to_slowbrain` (nombre legado) → `WorkerSession` |
| REFINAR un worker vivo ("además verde") | **inyectar** | NUEVA tool `send_to_worker(which, message)` → `dispatch.inject` (cola piggyback, §v3·H) |
| RESPONDER a un `ask` de un worker | resolver la pregunta | determinista (hay `waiting_on:user`) **o** tool `answer_worker` |
| PARAR ("para eso / cancela el widget") | **matar** | NUEVA tool `stop_worker(which)` → `cancel_session` |
| Datos de widget / charla / web | como hoy | `widget_data` / chat / `web_search` |

- **Resolución de "cuál" (`which`)**: determinista (como `attention.hard_interrupt`) — "todo"→todos; si hay UNA
  sesión→esa; si varias→por kind ("widget"→code, "búsqueda"→web) o solape de palabras con el goal; ambiguo→preguntar.
- **`send_to_worker` reemplaza el hack de dedup de V2-029**: un refinamiento de una tarea en curso YA no se
  descarta; se INYECTA a la sesión correcta.
- Backstops DETERMINISTAS (regex es/en) para inyección/parada, por si el modelo pequeño no dispara la tool
  (mismo patrón que login/confirm), **gated a que HAYA workers vivos** (si no, no aplican).

### Tools nuevas del FlashBrain (catálogo canónico = `zaelar-architecture.md §8`)
- `send_to_worker(which, message)` — inyectar (situacional: solo si hay workers).
- `stop_worker(which)` — matar (situacional: solo si hay workers).
- `answer_worker(which, answer)` — responder un `ask` (situacional: solo si hay `ask` pendiente).
- (`escalate_to_slowbrain` se mantiene por legado como "arrancar worker".)

---

## 11. Diagramas de secuencia (los 4 flujos críticos)

> ⚠️ **v3:** diagramas CONCEPTUALES. Ajustes firmes: 11.1 refinar = `dispatch.inject`→cola piggyback (no
> `backend.send→stdin`); 11.2 = re-poll idempotente sin `Future` + `waiting_on` en registro RAM (no `set_state`
> por-evento) + el turno tras relatar el `ask` está EXENTO de la supresión de eco (§v3·N). Ver §REVISIÓN v3.

### 11.1 Inyección (↓) — "además, verde"
```
Operador: "búscame una moto de enduro"    → FlashBrain: escalate → WorkerSession#7 (Claude, kind=web) arranca
WorkerSession#7: phase "navegando a Wallapop" → bus → ESTADO.sessions[7].phase → prompt + chip
Operador (30s después): "ah, y que sea verde"
FlashBrain (ve worker#7 vivo, kind web, goal "moto enduro") → send_to_worker("la búsqueda de la moto","añade: color verde")
   → backend.send(#7, "añade restricción: color verde")  → stdin del claude vivo
WorkerSession#7: phase "re-filtrando por color verde"   (NO se abrió una tarea nueva)
```

### 11.2 Pregunta con respuesta (↑) — `ask`
```
WorkerSession#7 (a mitad):  hbask "¿la prefieres de enduro o de cross?"  ── long-poll ──┐
server: AskRegistry[c1]=Future; ESTADO.sessions[7].waiting_on="user"; bus worker.ask     │
FlashBrain loop: relata por voz → "Oye, el buscador pregunta: ¿enduro o cross?"          │
Operador: "enduro"  → provider ve waiting_on=user → resuelve AskRegistry[c1]="enduro" ────┘
hbask retorna "enduro" → WorkerSession#7 sigue con la respuesta
```

### 11.3 Parada ("para eso")
```
Operador: "para eso, cancela el widget que estás creando"
FlashBrain: stop_worker("el widget") → resolve_sessions → [#9 (code)]
   cancel_session(9): (a) backend.stop(9) [stdin close→SIGTERM→SIGKILL]  (b) generator.kill(9) si aplica
   → ESTADO.sessions sin #9  → chip fuera  → voz "vale, lo he parado"
```

### 11.4 Encallamiento (loop)
```
loop tick: WorkerSession#5 sin evento en 180s → nudge send(#5,"¿sigues avanzando?")
loop tick+N: sigue mudo → voz "la búsqueda lleva un rato parada, ¿insisto o la dejo?"
```

---

## 12. Casos límite y seguridad

- **Aislamiento (O5):** un worker que revienta/encalla → capturado, trazado (`observer` kind `worker`), nunca tumba
  voz/otros/loop. Pool `max_parallel` acota concurrencia.
- **Atención:** un `say`/`ask` relatado por voz respeta el gate (no pisar una reunión); un `ask` pendiente es
  prioritario pero se relata en el primer hueco dirigido, no interrumpe grosero.
- **Input no confiable (cluster, V2-010):** NUNCA arranca un worker con tools; `deny_tools`. Un peer no puede
  inyectar ni responder asks de workers del operador (allowlist de tags de cluster intacta).
- **Escritor único de memoria:** preservado (bridges por HTTP, no BD directa).
- **Irreversibles:** el confirm-gate (`nucleo/danger.py` + `widgets/confirm.py`) sigue ANTES de una acción
  irreversible de worker (comprar/pagar/publicar/borrar). Un `act push_channel` externo pasa por `scan_outbound`.
- **Reconexión / reinicio del server:** al arrancar, no hay workers vivos (los procesos murieron). ⚠️ **v2:** ya NO
  hace falta limpiar el ESTADO a mano — como la fuente de verdad es el registro en RAM (§REVISIÓN v2·C), arranca vacío
  y la 1ª sincronización deja el ESTADO sin fantasmas. Los `_jobs` a medias del generador se descartan como hoy; el
  `session_id` nativo persistido (§REVISIÓN v2·E·Q6) habilita `--resume` como feature futura.
- **Backpressure de eventos:** el pump de `events()` no debe floodear el SSE (coalescing de `phase`, igual que el
  puente `memory.updated`→SSE de V2-037).
- **Cortesía de kill:** SIGTERM→grace→SIGKILL; carpeta de widget a medias descartada + validación.

---

## 13. Layout de módulos (propuesto)

```
nucleo/workers/                     NUEVO paquete (evoluciona nucleo/agentes/)
  base.py            WorkerBackend (Protocol) + WorkerEvent + WorkerSpec  (evol. de agentes/base.py)
  claude_session.py  backend Claude Code stream-json  (evol. de agentes/claude_code.py)
  codex_session.py   backend Codex  (adaptador; stub si el CLI no está listo)
  registry.py        get_backend(spec)  (evol. de agentes/__init__.get_agent)
  session.py         WorkerSession: posee backend + event-pump + actualiza el REGISTRO RAM + parking act + cola
                     de inyección + kill de grupo   (⚠️ v3: la sync ESTADO NO es de la sesión, la hace el LOOP §v2·C)
nucleo/dispatch.py   → gestor de sesiones: start / inject / stop / resolve / cancel_all  (evoluciona el actual)
nucleo/loop.py       → + supervisor de workers (§8)
nucleo/worker_bridge.py + worker_api.py   hbask/hbact/hbnote-say  +  /api/worker/act (UN endpoint; ask=act ask_user,
                     §v2·B) + GET /act/{corr_id} re-poll idempotente (§v3·I) + auth token por-tarea (§v2·D)
nucleo/flash/router.py   + tools send_to_worker / stop_worker / answer_worker  (+ backstops deterministas)
voice/engine/llm/providers/nucleo.py  + wiring (inyectar/responder/matar, has_workers en tool_context)
nucleo/flash/probe.py   + reconocer las tools nuevas (impl PARALELA — SIEMPRE cablear en ambos)
memory/state.py         sessions enriquecido (waiting_on, ask, age, pct, backend)
server/voice_api.py     GET /api/tasks (read-only)  + /reset/hard usa cancel_all real
nucleo/reset.py         cancel_all() real (mata procesos, no solo limpia el registro)
frontend: ActivityStrip + store   estados waiting/asking; reconcile desde /api/tasks al (re)conectar
```
- Los `nucleo/agentes/{worker,web_cc,code,claude_code}.py` se **reescriben/absorben** dentro de `nucleo/workers/`
  (piezas one-shot → sesiones). `web.py`/`otros.py` ya parkeados se retiran.

---

## 14. Preguntas abiertas → **RESUELTAS en §REVISIÓN v2·E**

> ⚠️ **v2:** estas 7 preguntas ya tienen respuesta firme en la §REVISIÓN v2 (apartado E). Se conservan aquí como
> enunciado/contexto del razonamiento; la decisión vive arriba.


- **Q1 — ¿stream-json CLI o Agent SDK?** El diseño asume **stream-json CLI** (encaja con tool-gating + modelo-por-
  invocación + el patrón de subprocess/bridges existente, mínima dependencia nueva). El **Claude Agent SDK** daría
  interrupts/hooks/resume nativos y un pump más limpio, a cambio de dependencia + repensar el gating. ¿Merece la pena
  para la agnosticidad (¿el SDK es solo-Claude y ata más que el CLI?)? — el CLI parece MÁS agnóstico.
- **Q2 — `ask` con respuesta: long-poll HTTP vs canal por el bus.** El diseño usa long-poll con `corr_id`
  (request/response nítido). ¿Preferible un `ask`/`ask.reply` por el bus con el worker suscrito? (evita long-poll
  pero mete al worker como suscriptor del bus, que hoy es in-process). Trade-off simplicidad vs pureza.
- **Q3 — Derivación automática de `phase`/`say` del stream nativo vs bridges explícitos.** ¿Cuánta inteligencia
  ponemos en el mapeo backend→WorkerEvent vs exigir al worker que llame a `hbnote`/`hbask`? (fiabilidad vs esfuerzo
  de prompt del worker).
- **Q4 — Generador de widgets: unificar bajo WorkerSession o envolver en Popen matable.** Unificar es más limpio y
  hace "crear widget" interactivo/matable de gratis; envolver es menos cambio pero deja dos caminos.
- **Q5 — Enrutado de la respuesta del usuario a un `ask` cuando hay VARIOS asks pendientes** (2 workers preguntan a la
  vez). ¿Cola FIFO relatada de una en una? ¿El FlashBrain desambigua por contenido?
- **Q6 — Persistencia de sesión entre reinicios.** ¿Vale con matar todo al reiniciar (simple, propuesto) o queremos
  `--resume` para retomar un estudio largo tras un reinicio? (afecta a durabilidad del ESTADO).
- **Q7 — Límite de vida / coste.** ¿Tope de tokens/tiempo por worker y por pool? ¿Presupuesto configurable?

---

## 15. Plan de construcción (el operador eligió "TODO de una")

> ⚠️ **v2:** este plan sigue vigente, pero cada fase incorpora las DECISIONES FIRMES de §REVISIÓN v2 (piggyback de
> inyección, plano `act` único con política, registro-RAM=verdad, kill de grupo, cross-loop, token por tarea,
> `session_id` persistido). El checklist de aceptación del equipo es §REVISIÓN v2 (A–F), no solo lo de abajo.

Aunque la integración se prueba al final, internamente se construye por capas para acotar el riesgo:
1. **Sustrato agnóstico**: `nucleo/workers/{base,registry,session,claude_session}.py` (WorkerBackend, WorkerEvent,
   WorkerSpec, pump de eventos, stream-json). `codex_session.py` como adaptador (stub honesto si el CLI no está).
2. **Dispatch como gestor de sesiones**: start/inject/stop/resolve/cancel_all + registro con handle + kill cortés.
3. **Planos de comunicación**: bus `worker.*` + `worker_api`/`worker_bridge` (`hbask`/`hbact`, AskRegistry long-poll).
4. **ESTADO enriquecido** + `GET /api/tasks` + prompt "BRAIN WORKERS EN MARCHA".
5. **FlashBrain**: tools `send_to_worker`/`stop_worker`/`answer_worker` + backstops + wiring en provider Y probe.
6. **Loop supervisor** (§8).
7. **Frontend**: ActivityStrip con estados waiting/asking + reconcile desde `/api/tasks`.
8. **reset.py** con `cancel_all` real.
9. **Observabilidad + docs (§8, architecture.html, zaelar-memory §sessions, CLAUDE.md) + tests (routing, kill,
   inject, ask) + versión + bitácora**. Cierre con revisión de alineación.

**Criterio de aceptación (e2e, con el probe + una prueba manual):** arrancar una búsqueda; inyectarle "verde" y ver
que NO abre otra tarea; que el worker pregunte y la respuesta por voz le llegue; "para eso" mata el proceso real
(sin huérfanos) y limpia el chip; un worker encallado dispara aviso; todo agnóstico (mismo flujo con backend Codex).

---

## 16. Qué NO cambia (para tranquilidad)
- El motor de voz LiveKit, el gate de atención, la memoria (contrato), el bus in-process, la regla no-razonador del
  FlashBrain, el escritor único de memoria, la latencia de la ruta caliente (V2-011), la configuración-por-UI.

---

## Bitácora de construcción

### 2026-07-14 — Gran Refactor implementado (P1→P10), rama `feat/v2-038-brain-workers`
Construido en 10 fases con commit por fase, sobre el baseline `v1.6.0` / tag `pre-brainworkers` (ancla de rollback):
- **P1** sustrato agnóstico `nucleo/workers/` (base + claude_session stream-json + generator_session + codex stub + registry).
- **P2** `dispatch.py` = gestor de sesiones (registro RAM único, WorkerSession, kill de grupo, inject, resolve).
- **P3** comunicación: `worker_api.py` (/api/worker/act, política ALLOW/CONFIRM/DENY, re-poll, piggyback, token) + `worker_bridge.py` (hbask/hbact/hbsay).
- **P4** ESTADO enriquecido (bloque BRAIN WORKERS + waiting_on) + `GET /api/tasks`.
- **P5** tools del FlashBrain (send/stop/answer_worker) + gating + backstops + precedencia; wiring en provider Y probe; marshaling cross-loop.
- **P6** loop supervisor (proyección RAM→ESTADO, relato de asks con atribución, encallamiento/timeout).
- **P7** frontend: reconcile desde /api/tasks + estado `waiting` en el ActivityStrip.
- **P8** reset mata de verdad + apagado ordenado del lifespan + barrido de huérfanos.
- **P9** generador de widgets unificado bajo WorkerSession (matable por token, contrato+validación intactos).
- **P10** tests (router + `tests/agent_headless/unit/workers/test_workers.py`, 74 verdes en flash+workers) + docs (§8, architecture.html, CLAUDE.md, cluster.yaml) + versión 1.6.0→1.7.0.

**Verificación en esta sesión:** imports de todos los módulos runtime OK; 74 tests flash+workers verdes; routing de backend (widget→generator, web→claude); política del act; resolve/inject/cancel; gating situacional de tools; backstop stop-work. **Pendiente de PRUEBA EN VIVO del operador** (el stack LiveKit + un worker real end-to-end no se ejecutó aquí). **Pendiente (equipo):** redibujar el SVG de nodos de `/architecture` al modelo Brain Workers (los sellos y las tablas ya están actualizados; la topología dibujada del SlowBrain sigue mostrando el modelo previo).

### 2026-07-14 — AUDITORÍA post-implementación (Fable 5) + diagramas redibujados · v1.7.0
Auditoría de P1–P10 contra las decisiones firmes §v2·A–F + §v3·G–P, fichero a fichero. **Veredicto: la
implementación cumple la spec** (agnosticidad, registro RAM único, killpg, piggyback, política del act, token,
marshaling cross-loop, precedencia, eximir eco, apagado ordenado §L, barrido de huérfanos, generador matable,
frontend reconciliado). Se encontraron y ARREGLARON **7 defectos** en la misma pasada:
1. **`worker_api._new_corr` era secuencial/adivinable** — y el re-poll `GET /act/{corr_id}` no lleva token: un
   proceso local podía leer la respuesta del operador y ROBAR el piggyback de inyecciones. Ahora el corr_id lleva
   sufijo aleatorio (capability, §v2·D).
2. **`read_widget` devolvía el manifest, no los DATOS** (§7.3 exige `view_data`). Ahora devuelve manifest + data
   (off-loop, timeout, vía `widgets/server_api._run_widget`).
3. **Sin purga §v3·L**: al matar/terminar una sesión, sus asks pendientes quedaban en `_ACTS` → el loop relataría
   la pregunta de un muerto. `worker_api.purge_task()` + cableado en `cancel_session` y el final de `_run_session`;
   + poda TTL de respondidas (el registro no crece sin límite).
4. **Inyección a una sesión EN COLA del pool se perdía en silencio** (`inject` exigía `r.session`). Ahora encola
   en el record (`pending`) y se entrega por piggyback al primer contacto; `take_pending_injects` lee el record.
5. **Error fatal del backend = SILENCIO** (result_summary vacío → sin entrega; había un no-op evidente en
   `session._on_event`). Ahora un fatal sin summary entrega «No pude completar la tarea» — nunca mudo.
6. **Segunda verdad en el prompt**: `prompt.live_state()` seguía leyendo `escalate.summary_line()` (registro
   legacy). Recableado a `dispatch.pending_summaries()` (registro RAM, §v3·G; lectura µs, V2-011 intacto).
7. **Backstop ask demasiado voraz** (§v3·M pide «respuesta libre CORTA»): se tragaba como respuesta al worker
   turnos que YA dispararon otra acción (show/búsqueda/escalada/data-op), largos, o con login pendiente (rango
   superior). Guardas añadidas en el provider.
Re-verificado: 74/74 tests verdes; probe en vivo (`/api/flash/say`): charla→chat, «para eso» sin workers→chat con
las 3 tools de worker GATED OFF (6 tools base). **Diagramas**: `buildSlowArch()` REDIBUJADO al modelo Brain Workers
(FlashBrain→dispatch[RAM]→N workers; 3 canales ↓inyección/↑bus/↑ask-act; worker_api+bridges; loop supervisor;
proyección→ESTADO+/api/tasks; entrega), panel/nota/sello actualizados; sello de Widgets des-desfasado (bucle Haiku
parkeado → worker hbweb; generator_session). Tag `v1.7.0`. Anotado (no bloqueante): `push_channel` retenido aún es
stub (sin canal consumidor; al confirmar no ejecuta — tampoco filtra `scan_outbound` porque nada sale);
`match_by_options` es placeholder conservador; cuota de descendientes de `spawn` = solo profundidad (≤2), sin
contador por raíz; `resolve_sessions` ambiguo cae a «todas» (documentado: mejor parar de más) en vez de preguntar.

### 2026-07-14 — FIX del round headless post-refactor (26 turnos, reporte del developer) · verificado en vivo
Los 6 hallazgos del round, arreglados y RE-VERIFICADOS por el probe contra el server vivo:
1. **[MEDIA] Context-bleed en el turno de borrar** — raíz: en el probe una data-op MUDA dejaba la ventana sin
   respuesta del asistente → el turno siguiente veía la petición «sin atender» y la RE-disparaba. Doble fix:
   (a) **paridad "nunca mudo" en `probe.py`** (data_ack/show_ack/filler deterministas, como el provider — impl
   paralela, cablear en ambos); (b) **guard anti-refire en el provider**: una data-op IDÉNTICA a la recién
   ejecutada (<120s) cuyo contenido el turno actual NI MENCIONA se ignora como arrastre (`brain._last_dataop`).
   Verificado: «apunta dentista» → "Hecho." (no mudo); «borra el reloj» → SOLO delete_widget.
2. **[MEDIA] Tiempo con ciudad equivocada** — DOS raíces: (a) el prompt no anclaba lugar→ciudad viva ni frescura →
   regla en `prompt._flash_layer` (dato de LUGAR sin ciudad = la del estado; dato guardado de OTRA ciudad o viejo
   → busca); (b) **la mudanza nunca llegaba al ESTADO**: «me he mudado a Valencia» no matcheaba `_PROFILE_LOC_RE`,
   y aunque matcheara, el gate anti-garble P0b la mandaba a cuarentena, y aunque pasara, la rama LLM del ingest
   NUNCA aplicaba el patch heurístico. Fix triple en `memory_agent.py`: `_RELOCATION_RE` (matchea mudanzas es/en +
   cuenta como corrección para P0b) + **backstop PERFIL→ESTADO** (si los átomos del LLM no patchean los campos que
   la heurística detectó, el patch se aplica igual, pasando por el mismo gate). Verificado e2e: «me he mudado a
   Valencia» → `state.location=Valencia`; «¿qué tiempo hace hoy?» → `web_search("tiempo Valencia hoy")`.
3. **[BAJA] Data-op muda** — cubierto por 1a. 4. **[BAJA] Conectores tipo dump** + 5. **[BAJA] jerga «escalo»** —
   dos reglas tersas en `_flash_layer` (estados/listas en UNA frase natural; la cocina interna no existe para el
   operador). Verificado: "Tienes WhatsApp y Telegram conectados y funcionando" (degen=False) · "Me pongo con
   ello, te lo preparo ahora mismo". 6. **[INFO] doble [[show]]** — verificado idempotente en `desktop.show()`
   (reutiliza la tarjeta si existe; re-pinta, no duplica). Sin cambio.
Docs-sync: `zaelar-memory.md §backstops/§P0b` (mudanza + perfil→estado) + sello Memoria de `/architecture`
(2026-07-14). `.gitignore`: regla general `widgets/_data/*/` (agenda/state.json estaba trackeado por accidente y
el reset lo borraba dejando el árbol sucio). Pendiente igual que antes: la pasada REAL de workers (voz/dispatch)
que el headless no cubre.

### 2026-07-14 — RETEST: cierre definitivo de #2 (mudanza→ESTADO fiable + supersede de slot auto-curativo)
El retest confirmó #1/#3/#4/#5/#6 y que la regla de grounding del prompt funciona — pero #2 no cerró: la mudanza
no llegaba FIABLEMENTE al estado. Tres raíces, arregladas:
1. **Regex corta** (`memory_agent`): "me acabo de mudar a X" / "acabo de mudarme a" / "me he trasladado a" /
   "nos trasladamos a" / "I've just moved to" / "I now live in" no matcheaban → `_MOVE_VERBS` compartido por
   `_PROFILE_LOC_RE` y `_RELOCATION_RE`. "ahora estoy en X" entra SOLO con Capital y sin artículo/lugar común
   ("ahora estoy en el trabajo/casa/EL COCHE" no pisa location). Al disparar, cuenta como corrección → el patch
   fuerza `state.location` saltándose la cuarentena (backstop PERFIL→ESTADO del fix anterior).
2. **Slots sin normalizar** (`memory/writer.canon_slot`): el CORAZÓN emitía 'location'/'ubicación' y la heurística
   'operator.location' → DOS linajes del mismo hecho que nunca se supersedían entre sí (la causa de las píldoras
   contradictorias coexistiendo). El writer es el único punto de paso → alias→canónico ahí, para TODOS los
   escritores (`_SLOT_ALIASES`: location/ubicación/city/name/nombre/goal/objetivo/…).
3. **Supersede LIMIT 1** (`memory/writer.insert_memory`): solo invalidaba EL último vigente — si ya coexistían 2+
   (alias previos, unforget, legacy) nunca volvía a colapsar. Ahora invalida TODOS los vigentes del slot en cada
   escritura (y también al reforzar) → **auto-curativo**.
**Criterio de cierre verificado e2e** (memoria fresca, server vivo): "vivo en Soria"→Soria(1 píldora) →
"en realidad me acabo de mudar a Valencia"→Valencia(1) → "¿qué tiempo hace hoy?"→`web_search("tiempo hoy Valencia
España temperatura")` → "me he trasladado a Girona"→Girona(1) → "acabo de mudarme a Bilbao"→Bilbao(1). Siempre
UNA sola píldora vigente en `operator.location`. Tests: 96 verdes (flash+workers+memory_agent). Docs:
zaelar-memory.md (schema §slot + backstop mudanza ampliado). NO tocado: la regla de grounding del prompt
(verificada por el operador con Bilbao).

### 2026-07-14 — AUDITORÍA GLOBAL de memoria post-refactor (equipo de memoria): regresiones + cierre de fondo
Auditoría completa del sistema de memoria tras V2-036/V2-038 (4 pasadas: arqueología git · invariantes ·
genericidad/multidioma · alineación docs/diagrama/tests). Informe: `~/.meshkore/tmp/auditoria-memoria-2026-07-14.md`.
**Hallazgo de proceso:** los cambios de memoria de V2-036 entraron squasheados bajo bandera V2-035 (`0e90bb7`)
sin pasar el memory-workflow — por eso "creíamos no haber tocado la memoria".
**Regresiones arregladas (P0/P1):**
1. `dispatch.py:371` llamaba a `compose_task_context` (INEXISTENTE; typo de `compose_context`) con fail-open
   silencioso → TODOS los Brain Workers arrancaban SIN el bloque «CONTEXTO DE MEMORIA». Arreglado + warning +
   guard en `tests/agent_headless/unit/test_dispatch.py`.
2. `_tools_for` daba **`Bash` PELADO** a los workers web/code → el escritor único quedaba sin enforcement
   (un worker inducido por web hostil podía abrir la SQLite). Ahora Bash SOLO por los CLIs puente
   (`_BRIDGE_TOOLS`), como documentaba CLAUDE.md.
3. `POST /api/memory/remember` era una 2ª semántica de escritura SIN gates: `remember(auto=True)` podía derivar
   un `state_patch` y PISAR la identidad del operador; sin token. Ahora exige `ZAELAR_TASK_TOKEN` (headers de
   `mem_cli`; escotilla dev `ZAELAR_MEM_API_OPEN=1`) y entra por **`memory_agent.remember_external`**: gate P0a,
   NUNCA toca `state`, slots de IDENTIDAD vetados, `meta.source="worker:<id>"`.
4. Las tareas FALLIDAS escribían píldora mid («No pude completar la tarea») — el refactor P2 perdió el gate `ok`
   de `_deliver`. Restaurado (`workers/session.py`): solo el ÉXITO se recuerda; el fallo va por voz+[SISTEMA].
5. `tests/agent_headless/unit/test_dispatch.py` mockeaba la costura MUERTA (`agentes.get_agent`) → lanzaba un `claude` REAL y
   colgaba la suite. Reescrito contra `dispatch.get_backend` con un `_FakeBackend` (+ test de tarea fallida).
**Cierre de FONDO del retest #2 (P2 — decisiones del equipo de memoria):**
6. **Registro canónico de slots `memory/slots.py`** (SlotSpec: clave+alias+campo de state+flag identity): lo
   consumen writer (`canon_slot`), memory_agent (`_IDENTITY_SLOTS`/`_PATCH_TO_SLOT` DERIVADOS — phone/address/diet
   quedan por fin protegidos por P0b) y el prompt del procesador (catálogo GENERADO). Muere `_SLOT_ALIASES`.
7. **Contrato v2 del átomo**: `value` (valor escueto del hecho singular → el host SINTETIZA el `state_patch`
   MECÁNICAMENTE del registro, aunque el LLM escriba el cambio como hecho suelto) + `change: none|update|correction`
   (la señal "cambio legítimo vs garble" la emite el PROPIO procesador multilingüe, por átomo, y la consume el
   gate P0b) → la familia de regex (`_RELOCATION_RE`, `_CORRECTION_*`, …) pasa a BACKSTOP del castellano, ya no
   es el mecanismo único. Fewshot nuevo del cambio declarado; simetría verificada (sin señal, el garble sigue
   yendo a cuarentena).
8. **Fewshots NEUTROS**: fuera «Ricard»/«zaelar»/Barcelona/«Toby» del prompt de producción (dato de fábrica que
   sesgaba al 3b) → persona ficticia. La prosa de orquestación de workers salió de `memory.compose_state()`
   (substrato) a `nucleo/flash/prompt._workers_directive()` (capa del FlashBrain, condicionada a workers vivos) —
   V2-027: la memoria compone DATOS, cada cerebro añade SU capa.
9. **`heal_slots()` en el consolidador**: normaliza slots LEGACY (alias/mayúsculas pre-normalización) y colapsa
   multi-vigentes del stock en cada sueño. + desempate por `id` en el SELECT de vigentes del writer (resolución
   de segundo, mismo fix que recent_short).
10. **Write-completeness** (tensión con V2-031): el modelo del CORAZÓN pasa a config
    (`v2.json §memory.mem_processor_model`, env fallback) y el SKIP-si-ocupado se sustituye por una **cola
    diferida corta** (serial en GPU — sin pileup; espera acotada `MEM_PROCESSOR_QUEUE_WAIT/[_MAX]`; solo al
    agotarse cae a heurística, de forma observable).
**Tests:** 318 verdes (suite memory/nucleo/tests/bus completa) + `tests/memory/unit/test_slots_audit.py` nuevo
(12 casos: alias, auto-curativo, heal, contrato v2, señal change end-to-end con LLM mockeado en CATALÁN,
remember_external). Docs-sync: zaelar-memory.md + zaelar-memory-workflow.md (mapa 1a/1b con workers) + CLAUDE.md +
diagrama Memoria de /architecture (writer auto-curativo + registro + workers como escritores + consolidador).
**PENDIENTE (P3, decisión del operador):** lexicones por idioma (`MemoryLexicon` paralelo a `LangSpec`) para los
~50 backstops es/en restantes + `memory/concepts.py`/`_FORGET_STOP`; y sacar del repo los widgets del operador
(`widgets/meteo-soria`/`meteo-tarragona` — su tick siembra «Tiempo en Soria» en una instalación fresca, violación
de "memoria en blanco").

### 2026-07-14 — FIX de la demo en vivo (19:12–19:24): falso-positivo de parada + tarea web INVISIBLE
Diagnóstico desde `timeline-latest.jsonl` (sesión con público, micro abierto):
- **El worker del widget Snake (tarea 1) lo mató un FALSO POSITIVO** del backstop determinista de parada a las
  19:16:54: la charla ambiente *"…está creando su memoria vectorial, que es lo que necesita **para** poder
  acceder…"* matcheó "para" (preposición) + "creando" → `stop_worker(['1'])`. Encima el kill fue MUDO (la voz
  decía "no te he entendido" a la vez) y el chip emitió DOBLE `end` contradictorio.
- **La tarea de Wallapop (tarea 2) corrió INVISIBLE 12+ min sin entregar**: en el refactor V2-038 (P2) el flujo
  `kind=web` perdió el paso de `web_cc` que creaba la tarea+TARJETA del navegador y el contrato de cierre; el
  worker deambulaba con fases genéricas ("ejecutando un paso…") y sin tope duro (el aviso de 15 min no corta).
  El operador lo constató en vivo: *"No lo está abriendo, se ha estropeado"*.
**Arreglos (P1+P2 del plan; P3-atención pendiente de decisión del operador — el 🤖 wakeword ya sirve de modo demo):**
- **P1 `router.looks_like_stop_work` CONSERVADOR**: solo órdenes CORTAS (≤12 palabras/90 chars) con verbo en
  forma de MANDATO — "para" solo como imperativo ("para eso/esto/ya/todo/el…/de <verbo>"), nunca preposicional
  ("para poder/que…"). Con duda NO se mata (el kill fino queda para la tool `stop_worker` del modelo). El kill
  del backstop SIEMPRE se anuncia por voz (provider), y una sesión cancelada emite UN solo chip `end`
  (`session._finish` ya no re-emite el de `cancel_session`).
- **P2 contrato web RESTAURADO bajo el sustrato V2-038** (`dispatch`): `_prepare_web` crea/reutiliza la tarea del
  navegador (continuidad V2-032 + force-new) y ABRE la tarjeta ANTES de arrancar el worker (`ZAELAR_NAV_TASK` →
  capturas/fases casan con ESA tarjeta); `_web_prompt` portado de `web_cc` (conducción por hbweb + categoría
  exacta + CIERRE OBLIGATORIO extraer→concluir→entregar + hitos por hbnote + honrar ⟦NUEVAS INSTRUCCIONES⟧);
  `_finalize_web` vuelca los anuncios extraídos a la tarjeta y fija su estado final TAMBIÉN al cancelar (nunca
  una tarjeta girando). `SessionRecord.nav_task` nuevo.
- **P2 PRESUPUESTO DURO por worker** (`loop`, 2 fases): al agotarse (`WORKER_BUDGET_SECS` def 600; por-kind
  `WORKER_BUDGET_<KIND>_SECS`) se INYECTA "entrega ya"; tras la gracia (`WORKER_BUDGET_GRACE_S` 90) se MATA con
  aviso por voz y entrega parcial (la tarjeta conserva lo extraído). Un worker en `waiting_on=user` no consume
  presupuesto. El aviso pasivo de `_max_secs` se conserva.
- **P2 fases legibles** (`claude_session._tool_phase` ahora mira el COMANDO del Bash): nav_cli → "abriendo una
  página…/recogiendo resultados…", mem_cli → "consultando la memoria…"; `agent_report` NO pisa la fase que fija
  el propio hbnote (devuelve "" y no se emite).
- **P4 regresión**: `test_stop_work_ignores_ambient_speech` con el texto REAL de la demo + "para" preposicionales
  + parrafada-con-verbos (cap de longitud); los stops reales cortos siguen disparando. **97 tests verdes.**
Integrado sin conflicto con la auditoría del equipo de memoria de hoy (Bash acotado en `_tools_for`, contexto de
memoria de los workers reparado, `memory/slots.py`).

### 2026-07-14 — Test extenso post-P1/P2: falso-positivo de parada (frase corta) + show-por-nombre + menores
Routing/conversación 24-25/25; 3 hallazgos del orquestador arreglados:
- **[ALTA] `looks_like_stop_work` daba FALSO POSITIVO en frases CORTAS con "para" PREPOSICIONAL** (el cap de
  longitud salva la parrafada, no la frase corta): "hazme un widget PARA el tiempo", "necesito un widget PARA la
  agenda" (4/8) auto-mataban el worker recién nacido — el escenario de la demo, ahora en petición. `para` es a la
  vez verbo de parada y la preposición más común. **Fix (2 defensas)**: (a) si el turno EMPIEZA con verbo de
  PETICIÓN (quiero/necesito/hazme/crea/abre/muéstrame…) → NO es parada; (b) "para" cuenta como imperativo SOLO al
  INICIO del turno y con complemento de parada REAL (deíctico eso/ya/todo · "de <verbo>" · artículo+palabra-de-
  TRABAJO como "la búsqueda/esa tarea") — nunca "para <sintagma nominal>" ("para el tiempo/la agenda/el finde") ni
  "para" a media frase ("eso ES para la búsqueda de piso"). Los verbos inequívocos (detén/cancela/deja de/aborta/
  stop/kill) intactos. Regresión `test_stop_work_ignores_short_prepositional_para` con las 4 frases del test.
- **[MEDIA-2a] Mostrar por NOMBRE natural**: el guard determinista de show (`_show_guard_target`) ya cancelaba una
  ESCALADA espuria; ahora también cancela un **web_search** espurio (las palabras-tema cebaban la búsqueda) cuando
  el turno es "muéstrame/abre X" y `runtime.identify` (fuzzy por keywords, GENÉRICO) resuelve un widget real. Se
  refleja también en el **probe** (`_show_target`, impl paralela — cablear en ambos). Verificado: "muéstrame la
  agenda"/"enséñame los resultados de fútbol" → `canvas:show`. NOTA: "fútbol" a secas no resuelve a
  `futbol-champions` — es un hueco de KEYWORDS de ESE widget (contenido del operador, no core; identify funciona:
  champions/agenda/resultados/results sí resuelven). NO se hardcodea nada en el core.
- **[MEDIA-2b] Responder CONTENIDO por voz** ("¿qué tengo en la agenda?", "¿tengo mensajes?" → hoy abren la
  tarjeta; el contenido no llega al prompt). **NO parcheado a propósito** (mandato del operador: nada hardcodeado
  ni por-widget): es una CAPACIDAD nueva que debe hacerse GENÉRICA — heurística `needs_widget_content` + surfaceo
  de `view_data()` del widget que resuelve `identify`, bajo demanda y FUERA del event loop (mismo patrón que
  `needs_recall`/`needs_recent`, respetando V2-011). Queda como ítem de diseño acotado (no una regex ad-hoc).
- **[BAJA]** (a) **dedup de `[[show]]`** por id en el mismo turno (provider; `desktop.show` ya era idempotente, no
  floodeamos SSE); (b) **ack de data-op variado** (`langs.data_acks`: Hecho/Listo/Ya está/… — el provider elige
  uno que NO repita el anterior → dos data-ops seguidas ya no disparan el loop-detector); (c) **fraseo**: una
  cláusula tersa en la regla de voz (palabras BIEN formadas, sin deformar/mezclar idiomas: "bici de montaña" no
  "biking de montaña", "te abro la mensajería" no "ábrole"). **98 tests verdes.**
Solo se commitean los ficheros de este fix (router/prompt/probe/test_router/langs/provider); `memory/*` y
`tests/memory/e2e/*` del status son trabajo en curso del equipo de memoria, NO se tocan.

### 2026-07-15 — Confirmación de data-op irreversible: copy CRÍPTICO ocultaba el alcance
Sesión en vivo (log 09:14): el operador pidió eliminar UN ítem de la agenda ("el primer ítem que pone revisar
obligaciones… de todos los días") y el overlay mostró **«¿Confirmas «drop_project»?»** — lo LEYÓ como "borrar el
widget entero". Diagnóstico: el modelo eligió `drop_project` (agenda: «congela un proyecto entero y descarta sus
tareas pendientes», `confirm:true`, `projectId`) en vez de `drop` (quita UNA tarea, `taskId`, directo) — la frase
del operador era ambigua/garbleada ("de todos los días" cebó "proyecto"). El confirm de `drop_project` es CORRECTO
(sí es irreversible), pero el copy exponía el NOMBRE INTERNO de la acción, no su ALCANCE → el operador no podía ver
que iba a tirar un proyecto entero, no la tarea que nombró.
**Fix (genérico, sin hardcode ni por-widget):** el texto de la confirmación de data-op (`_request_data_confirm` en
el provider) se compone del MANIFEST — `desc` de la acción + etiqueta del item resuelto (`widgets/refs.label_for`,
nuevo helper genérico): «Ojo, esto es permanente: «\<desc\>» («\<item\>»). ¿Lo confirmo?» — overlay Y voz iguales.
Así el operador ve el alcance REAL de CUALQUIER data-op irreversible de CUALQUIER widget y puede rechazarla. NO se
añade ninguna regla ad-hoc de "drop vs drop_project": la selección de acción es del modelo y la resolución de item
por campo (V2-026) ya la filtra; verificado por probe que con frase CLARA el modelo enruta bien ("quita la tarea de
estabilizar el daemon"→`drop` directo · "descarta el proyecto de marketing"→`drop_project`+confirm con copy humano).
No hubo ningún `delete_widget` en el log — el "borrar todo el widget" era la mala lectura del copy, ahora resuelta.
76 tests verdes.
