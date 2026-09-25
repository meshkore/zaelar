# Decisiones clave — el diario del motor

**Qué es esto.** Una entrada por tanda entregada: qué se decidió, POR QUÉ, y el fallo real que lo motivó.
No son instrucciones — las instrucciones viven en `CLAUDE.md`, que es lo que todo agente carga al empezar.
Esto se lee cuando hace falta: antes de tocar una pieza, para saber qué se intentó ya y qué se descartó.

**Dónde está el resto.** Las entradas más antiguas viven, íntegras y en su orden original, en
`.meshkore/docs/decisions-archive.md`; abajo queda su línea de índice. El detalle denso de cada una está en
su iniciativa, bajo `.meshkore/roadmap/initiatives/` (gitignoreado a propósito: no publicamos el roadmap).

**Cómo crece.** Al cerrar una tanda se añade la entrada AQUÍ, arriba del todo. Cuando este fichero pasa de su
techo (`tests/infrastructure/unit/test_claude_md_ratchet.py`), se mueven las entradas más viejas al archivo
dejando su línea de índice — **nunca se borra una cita**: el trinquete de cierre exige que toda iniciativa
entregada siga citada aquí.

> **Compaction policy (V2-601 T-18, 2026-09-06).** This log holds recent decisions VERBATIM and a one-line
> citation index for everything older. The full text of every archived entry lives, untouched and in its
> original order, in `.meshkore/docs/decisions-archive.md`; the dense per-decision source is each entry's
> initiative under `.meshkore/roadmap/initiatives/`. When closing work, keep writing full entries here — and
> when the size ratchet (`tests/infrastructure/unit/test_claude_md_ratchet.py`) trips, move the oldest
> full entries to the archive and leave their index line, exactly as this pass did. Never delete a citation:
> the closure trinquete requires every delivered initiative to stay cited in this file.

- **A message with several tasks in it is a LIST — split, queued, run step by step, reported once (V2-771,
  2026-09-25)**: *«tanto si nos las vomita por voz como si nos las pega, el sistema tiene que ver que esto es una
  acción que para completarse necesita realizar todo lo que se pide… "vale, entiendo que me pides unas cuantas
  cosas, me pongo a trabajar en ello"»* and *«dos tareas a la vez, el resto en cola»*. Measured on his 12-section
  setup message: it was ONE turn, and six per-turn limits each dropped part of it silently (the input clamp kept
  its LAST 1 600 chars, the distiller read its FIRST 600, 5 widget writes, 1+2 workers, 1 200 output tokens, the
  rename lane took a one-line paste whole). None of those limits was wrong — the message was not a turn. Now
  `nucleo/batch`: a shape floor (no vocabulary) and ONE Jev question decide «list?» before every lane and before
  the clamp; the receipt is one lang-table line (never the list read back, no count — it must not wait for the
  split); a `memllm` call splits it into self-contained steps (oversized ones cut at sentences, never mid-fact;
  fail-open to its sections, then to one step); the list is a visible `tasks` row with hidden child rows
  (resumed at boot); each step runs as an ORDINARY text-channel turn, memory written and AWAITED per step (the
  distiller turns lossy past two queued writes), workers go to a pool of TWO (was 3), and ONE report waits for
  them. A question-ending step reply is asked to Jev — «Anything else I can dig up?» is a courtesy, not a need
  (three done steps were reported as needing him on the first live run) — and an ACTION step whose turn executed
  nothing is retried once, then failed: «Done — it's on for Monday» with no call happened twice per run with no
  card open, where neither the phrase-table promise detector nor the verdict (`catalog_widget=none`) could see it. The errands case found three more, all product-wide: `protected_core` refused «prepárame una comparativa de
  bicis eléctricas» as «reprogram yourself» (the brief listed «revisa autonomía, motor y batería») — repaired by
  SUBTRACTING an ambiguous engine noun that the sentence gives another owner or lists as a feature; a list step
  drained the operator's system notes (a step no longer does); and a relayed worker kept the list waiting on
  its first RAM record (the closed durable row decides). Found on the way: an end date with no
  rule was a WEEKLY series (a holiday showed on two days); now a daily span. Live, sandbox, real models: his demo
  → 25 steps in 2 min 47 s; after the two fixes, run 3: 26/26 steps, 13/13 store checks, judge 5/5. Open: a spoken list past the accumulator
  valve still arrives as several turns; WhatsApp/Telegram/cluster are not order channels (a trust decision); a
  step's own outcome is read from its turn, not witnessed on the store; one step answered in Chinese (model
  language drift, no reply-language guard exists). Mechanism doc: `.meshkore/docs/modules/zaelar-task-lists.md`.

- **The everyday edits of an appointment, and a verdict that is READ where the reply only claims (V2-770,
  2026-09-25)**: *«abrir un item para que aparezca la ficha, pedir cerrarla, modificar el título, la descripción o
  la hora, cancelar una cita recursiva… la gente no pide las cosas de forma precisa»*. Measured with 13 loose
  phrasings against the real model in a sandbox: **3/13** landed, most turns answering «Hecho.» over nothing.
  Four causes, none of them the model alone: (1) missing doors — no way to open/close the detail card, say an end
  time (`update_meeting` dropped `endTime`, a key it knew), move ONE day of a series, or end a series «from» a
  date — now `widgets/agenda/edit.py`; (2) the open card's `usage` — the ONE place the model learns an action's
  fields — never mentioned series, the card or the end; (3) the promise repair (`act_repair`) waited for a regex
  to see a PROMISE, and a reply that CLAIMS slipped under it while the paid verdict already named the action —
  now `direct_action.names_an_order` gates it in both channels; (4) the text channel fired no turn brief and its
  repaired call was labelled so the executor never ran it (since V2-764), so it measured a product voice does not
  run. And one inversion: «ya la puedes cerrar» over a detail card closed the whole AGENDA — the canvas verb reads
  «close», only the action question knows WHAT closes (`order_is_inside`). Result: es 12/13, en 11/13. Open: the
  model still sometimes claims without calling on a sentence Jev reads as a remark («el martes 6 no hay clase» →
  `request_type=comment`); and in the text channel a question answered by a view op reads out the card's index.

- **A repeating appointment is ONE row with a rule (V2-769, 2026-09-25)**: *«no solo poner un ítem un día,
  sino también hacerlo recursivo entre el período que yo te digo»*. Measured on his agenda: the model sent
  `recurrence: "weekly", repeatUntil: "2027-06-30"` and `add_meeting` dropped both keys in silence (one Tuesday
  stored, «hasta junio» promised); the Thursday one before it had no field at all, so «recursiva» went into the
  category; and «recursiva los jueves», delivered as a turn of its own, wrote a junk task. Now a meeting carries
  `repeat` (`widgets/agenda/recur.py`) and every reader expands it — card, planner, digest, query, sweeps,
  notice (rolled forward by `tick`), Google (one RRULE series, its instances skipped by the sync). A key the
  widget does not read comes back in `ignored` and `nucleo/flash/write_outcome.py` corrects the model; a create
  whose sentence CONTAINS an earlier create's sentence takes that one back out (`revert`). Node 4.214.
- **A health notice never opens the door, and the agent knows what did (V2-768, 2026-09-25)**: *«estaba
  activada la word activation… el sistema no tendría que haberse puesto a escuchar nada… yo en ningún momento he
  dicho la palabra clave»*. Measured: a transient LiveKit stall made `homeostasis` SAY an alert aloud; every
  proactive delivery opens the reply window (V2-655), so his next sentence — to somebody on the phone — ran as an
  order and the chain lasted until ⏻; asked why, the agent said «oí tu nombre», which was false.
  `homeostasis._alert` is screen-only (the `homeostasis` event; never `proactive.notify`, not even `speak=False`,
  which would slip it into his next answer). `voice/attention_opening.py` records what opened the conversation
  (a cold turn's verdict reason, or our own delivery with its words) and the wake-word prompt line states it with
  «nunca inventes otra causa». Node 8.18.
- **No language, no agent — the picker is the only door (V2-765, 2026-09-24)**: *«no quiero que ninguno esté
  seleccionado por defecto… si no hace clic, el micrófono, el agente personal, todo está parado… es una pantalla
  sine qua non»*. Measured on his factory reset: the voice session was live behind the picker (V2-101's «a spoken
  answer still works»), and a sentence said to somebody else — ruled ambient — was classified `es`, LOCKED, closed
  the picker and got answered; the picker opened with a row already marked. A missing language now reads as a
  STOPPED agent through `runstate` (derived from `stt_language`, no second copy): no LiveKit token, no worker, no
  tick, and ⏻ cannot start it. `detect.lock()` is the only way out and starts the agent through ⏻'s own `start()`
  (unless he had stopped it). The voice no longer locks a language; no row is marked before the click. Node 3.80.
- **Torrents dentro de Archivos, y una promesa sobre una tarjeta recibe su llamada (V2-764, 2026-09-24)**:
  *«si hay un widget de torrents separado… lo fusionas con el de los archivos… biblioteca y torrents… dashboard,
  descargas y semillas… cuando alguien pida una búsqueda de torrents, a esa sección, en formato cine»*. Medido:
  el `search` del widget viejo DESCARGABA el primer magnet (no había catálogo) cuando el agente de la red
  (`seedhound`) ya devuelve diez versiones; sus magnets llegaban con `&amp;` (los trackers no se leían) y cada
  versión traía un `torrent_url` con la clave de su indexador. Archivos tiene ahora dos secciones; Torrents con
  Catálogo (sin descargar, sin magnets hacia la tarjeta), Descargas y Semillas; el widget `torrent` retirado y
  sus palabras son alias de Archivos y rejillas del mapa de acciones. **El enrutado, medido**: el modelo
  PROMETÍA («voy a por la serie Sherlock en torrent») sin llamar → `nucleo/flash/act_repair.py`: una pasada con
  UNA tool y las acciones declaradas de la tarjeta que nombra el veredicto, antes del respaldo que gasta un
  worker. Queda ~25% que el modelo escala a worker, y Jev dice «escalate» 0,91-0,99 también en los encargos de
  verdad: no se puede convertir en acción sin desmentir un veredicto pagado — descartado y escrito. Nodos 5.60,
  2.81. `7617f869`, `ee004671`.
- **El muro no contradice al orbe (V2-763, 2026-09-24)**: *«el orbe está en gris… lo que no puede ser es que se
  apague y que el micro siga escuchando, transcribiendo y aceptando órdenes»*. Medido (sesión 2ffe9713): 90 s
  de monólogo sin palabra de activación, todo AMBIENTE, cero turnos del cerebro — nada se aceptó, pero el
  fail-open de 9 s de la retención lo pintó como burbujas suyas (el veredicto de una frase inacabada llegó a los
  415 s de un turno empezado a los 324 s) y la transcripción final reescribía el subtítulo sin mirar el anillo.
  El fail-open pregunta ahora al orbe (`paintsProvisional`): encendido, como antes; apagado, espera su veredicto
  (dirigido pinta, ambiente descarta, sin veredicto en 180 s descarta). `b67d83a6`.
- **Un recall tardío DEGRADA la memoria durable, nunca la borra (V2-762, 2026-09-24)**: *«necesitamos la memoria
  permanente, ya sea a través del proveedor principal o del de failover… lo que no podemos es hacer que falle y
  no tener memoria permanente»*. Medido: 6 de 21 recalls de sus últimas sesiones no cerraron en 0,8 s y esos
  turnos iban SIN memoria de largo plazo; en vivo el recall tardaba 1-3,5 s (solo 0,3-0,5 s aislado), casi todo
  la llamada de embeddings a OpenAI. El canal LÉXICO (FTS5) vive en esta máquina — 3-27 ms — y ahora corre AL
  LADO del completo: si el completo llega tarde, el turno lleva el léxico y el completo llega como nota al
  siguiente. Ámbar solo si no llegó nada. Y el recuadro que fotografió mentía: «deepseek no responde» salía del
  COLOR de la fila (ámbar por el recall) con el corazón escribiendo todo el día sin relevo ni heurística; ahora el
  titular lo juzga el corazón. Descartado: keep-alive en embeddings (~100 ms) — los tests interceptan `urlopen` y
  habrían llegado a OpenAI sin notarlo. ABIERTO: la CALIDAD de lo que se guarda como largo plazo (frases de
  charla como píldoras mid/long). Nodo 3.79. `16820de6`.
- **La pestaña «Apps»: el catálogo de widgets, Sistema · Custom, por voz o a mano (V2-761, 2026-09-24)**:
  *«necesito un icono de app… en realidad va a ser la pestaña de widgets… quiero que responda a todo… dos
  subtabuladores, uno sería para sistema y la otra sería custom… cuando alguien modifique uno de esos widgets
  de sistema… en gris pálido y encima un mensaje que pone Custom»*. **(1) UNA PESTAÑA DEL MURO, no una
  superficie propia**, con un solo GET (`/widgets/registry` ya traía `origin` y `forked`) y el clic por la
  puerta de siempre (`hb:open-card`). Un widget de sistema bifurcado aparece DOS veces a propósito: pálido con
  «Custom» en Sistema —el nativo ya no corre— y como suyo en Custom. Icono: 3×3 PUNTOS, porque los botones de
  ordenar del raíl son CUADRADOS. **(2) TRES PUERTAS DE VOZ**: semillas del mapa de acciones (es/en, paquetes a
  v10 — sin subir versión, una frase nueva no llega a ninguna instalación existente), `show_panel` con `apps`
  (pagado comprimiendo su propia descripción: techos del catálogo y del prompt intactos) y `show_widget`
  nombrando la superficie de sistema `apps`, que el proveedor y su espejo `probe` enrutan ya al panel en vez de
  preguntar «¿qué widget?». **(3) ⭐ LOS ALIAS SE MIDEN CONTRA EL VECINDARIO**: el resolvedor difumina los alias
  de UNA palabra; un «aplicaciones» suelto habría cazado «abre la APLICACIÓN de música». Multipalabra donde hay
  vecino, y el test fija las frases que deben llegar Y las que no deben moverse. **(4) MEDIDO AL RENDERIZAR, no
  pedido:** con CUATRO pestañas, a 320 px (el flotante por defecto) Conectores ya quedaba tras una barra de
  scroll oculta — la tira necesitaba 183 px y tenía 132. Por debajo de 400 px el rótulo fijo de la pestaña
  activa cede; ninguna pestaña queda fuera de 260 a 800 px. **(5) No había workflow para una superficie
  NATIVA** — ahora `docs/ops/zaelar-native-surface-workflow.md`, con los 13 puntos que fallan en silencio.
  Y el pulgar de V2-760 se movió ENCIMA del lanzador, sin disco, mano negra, solo escritorio. Nodos 4.212 y
  2.80. `f4b8ca82`, `7a0d443e`.
  **(6) SU PRIMERA PRUEBA FALLÓ CINCO VECES — y la causa principal fue que el motor corría el código de ANTES**
  (`3.33+43b2a2ad`): la pestaña llega refrescando el navegador, el cerebro solo con `make restart`, y no se
  reinició porque él estaba en sesión. Lección: una entrega que cruza frontend y cerebro no está «en su
  pantalla» hasta que el motor que la sirve lleva el commit — se comprueba el `ver` de la sesión antes de
  darla por probable. Además: «catálogo de aplicaciones» y «widgets customizados» pasan a ser ALIAS de la
  superficie (el mecanismo de nombres, no una regla), «los míos/customizados» abre la subpestaña Custom, y el
  catálogo que ve el modelo marca por fila qué widget es suyo — «las personalizadas no me salen en la lista
  que veo» era literal. Icono de pestaña = silueta maciza de «widgets»; cajas ≤56 px, cabe el catálogo entero.
  **(7) Y AUN CON EL CÓDIGO NUEVO, EL MODELO DECIDÍA DISTINTO CADA VEZ**: sus seis frases, tres rondas con
  ventana limpia → `show_panel` 10-13 de 18; el resto se negaba, prometía sin tool o lanzaba un WORKER a «listar
  sus widgets personalizados». Lo decide ahora el NOMBRE, antes del modelo (`nucleo/flash/wall_lane.py`, carril
  hermano del de renombrar, espejo en el probe): el resolvedor nombra una superficie que es pestaña del muro sin
  ningún widget → se abre. Para el catálogo basta el nombre (su propia lista incluye «dime qué widgets tengo
  disponibles», sin verbo); para el chat sigue haciendo falta una orden de abrir. **21/21** en vivo.
- **El pulgar abajo marca un fallo en un clic, y la evidencia son los ÚLTIMOS eventos (V2-760, 2026-09-24)**:
  *«cada vez que la gente detecte un fallo, les pediré que clique en este pulgar hacia abajo… así el usuario no
  tiene que estar rellenando un mail o un texto… quedará vinculado por ID de agente con los datos de
  observabilidad… sale un mensaje hacia la izquierda, dura dos o tres segundos y desaparece en un fundido, y el
  icono vuelve al color original»* — local y nube. **(1) EL INFORME ES LA SESIÓN.** Un botón junto al lanzador
  de feedback, mismo color y un tamaño menor; un clic → `POST /api/feedback/thumbs_down` sin cuerpo: el servidor
  compone la frase con su ÚLTIMA petición y la respuesta que recibió, adjunta la evidencia y le añade un
  `marker` (sesión, traza del turno, hora) dentro del propio paquete, así que el otro lado no necesita columna
  nueva para saber dónde pulsó. Sin sesión de voz abierta (chat escrito) marca la más reciente. Sale por la
  MISMA puerta que el formulario (`_post`/`_deliver`, extraídas): credencial de workload en la nube, id de
  instalación en self-host. El aviso sale a la izquierda en su idioma, dura 3 s, se funde en 0,6 s y el icono
  vuelve al acento; un segundo clic mientras se ve no manda otro. **(2) ⭐ EL DEFECTO QUE DESTAPÓ, debajo de
  TODO el feedback:** `flows.events(limit=200)` devuelve los 200 PRIMEROS eventos de una sesión. Medido en la
  suya de hoy (621 eventos, 12:26:54-12:29:12): cualquier informe llevaba 12:26:54-12:27:33 — **los primeros
  39 segundos**, así que un aviso enviado al final nunca contenía el fallo que describía. `events(tail=True)`
  lee los últimos y los devuelve en orden; los lectores con cursor (`since_id`) no cambian. Y el doble de un
  test vecino tenía la firma fija: con el parámetro nuevo lanzaba `TypeError` dentro del `except` del producto,
  que lo leía como «sin evidencia» — reanclado para EXIGIR la cola. **Limitación dicha:** el tope de 30 KB lo
  llenan pocos eventos pesados (en esa sesión, los últimos 10 s); por eso el marcador importa más que el
  paquete: quien lo revise puede abrir la sesión ENTERA desde ese punto. Nodo 4.211, 14 tests, **13 desarmes rojos**.
  **No probado por voz ni contra la nube desplegada desde el propio botón.**

- **La pantalla completa TAPA TODO y siempre tiene salida; salir es su propia orden (V2-759, 2026-09-24)**:
  sesión `ee542271`, con V2-758 ya funcionando (la foto del Cobra salió). Él: *«que se ponga por encima de
  absolutamente todo y siempre de sistema con alguna especie de iconito para cerrarlo, arriba del todo a la
  derecha… una pequeña X que no se vea mucho… o hacer doble clic en la pantalla y que todo vuelva a la visión
  normal… para que la gente no se quede sin poder ver la barra»*. **(1) NO PODÍA TAPAR EL CHAT, POR NINGÚN
  Z-INDEX.** `#desk` lleva `transform` (V2-608): es el bloque contenedor de todo `position:fixed` de dentro Y
  un contexto de apilamiento. La tarjeta «a pantalla completa» se medía desde el escritorio —empezaba donde
  acaba el chat acoplado— y su `z-index:99900` solo competía dentro de `#desk`; el chat vive fuera, en el
  `body`. Su captura lo enseña exacto: chat visible, y tapados solo la barra y el orbe (que viven DENTRO).
  Mientras algo está a pantalla completa, `#desk` suelta el `transform` y sube a **9300**: por encima de chat,
  paneles y feedback; **por debajo** del mapa de memoria, la configuración, la bóveda y los modales, que abre
  él a propósito y no pueden quedar nunca bajo un vídeo. **(2) TODOS LOS WIDGETS IGUAL**: la franja de la barra
  deja de reservarse (V2-658) — la salida de sistema es ahora el camino de vuelta; la cabecera se queda (V2-693).
  **(3) LA SALIDA DE SISTEMA**: una X pequeña y tenue con una zona de 52 px en la esquina, la misma en todos los
  estados, dibujada por el escritorio y nunca por un widget, y por encima de un iframe (encima de un vídeo es la
  única salida que siempre funciona); **doble clic en cualquier sitio**, salvo la cabecera (ya conmuta sola), un
  campo de texto, o un widget que usa el doble clic para sí (archivos, música); y **Esc**, que la nativa ya
  hacía y la de la app no. Todas restauran la geometría exacta de antes. **(4) ENTRAR Y SALIR ERAN UN
  INTERRUPTOR**, y ahí estaba el «ya está» falso: «Y sal de pantalla completa.» → «Ya está, fuera de pantalla
  completa.» **sin llamar a nada** —el mismo fallo que V2-609, cuyo arreglo no aguantó—; su queja «No, sigues
  estando en pantalla completa» se leyó como ENTRAR y solo salió porque el frontend conmuta (sobre una tarjeta
  normal la habría agrandado). La dirección es ahora un argumento obligatorio (`mode: on|off`), las dos
  operaciones son idempotentes, y cuando el modelo no llama a nada en un turno que la licencia EXISTENTE ya lee
  como salida y **la pantalla dice que hay una tarjeta a pantalla completa**, la salida se completa — acotada a
  que esa tarjeta vuelva a su sitio, sin palabras nuevas. El catálogo lo pagó compactando: 23.597/23.600, techo
  intacto. **(5) Un test que copiaba el CSS defendía la regla derogada** —`…_but_not_the_rail.py` seguía verde
  con el producto cambiado, porque medía su COPIA—: reanclado y renombrado. El test nuevo monta el DOM REAL
  (`#desk` con su `transform`, chat fuera, barra dentro) con la hoja de estilos real, y afirma PUNTOS de
  pantalla: quién está encima ahí. Nodos 2.78/2.79, 43 tests, **31 desarmes rojos**, incluido el que devuelve
  el chat por encima (su captura). De paso, cerrados los 5 desarmes pendientes de V2-758: **el de «un solo
  salto» no fallaba, se COLGABA** —la escalera rebotaba titular↔suplente sin fin, y el bucle nunca cedía al
  event loop, así que ningún plazo de asyncio podía cortarlo—: era lo que tuvo 20 minutos parado el lote de
  ayer. Ahora el doble lanza una `BaseException` a la séptima llamada. **No probado por voz.** Pendiente y
  dicho: «vuelve al tamaño normal» no lo reconoce la licencia (sigue vetándolo); el banner de avisos (z 60)
  queda por debajo de una pantalla completa, igual que ya quedaba bajo el chat.

- **Un fallo NUESTRO no es un proveedor caído (V2-758, 2026-09-23)**: él fotografió el banner rojo —
  *«Cerebro rápido caído — turno degradado»*— y preguntó *«tengo que saber qué pasa… identificarlo»*. **No era
  el proveedor.** `server.log` de esa tarde: nueve turnos con `cannot access local variable '_cvis'`. `_cvis`
  es el alias de módulo de `canvas_visibility`; una **local del mismo nombre** en el `connect_cluster` de
  `_on_tool_call` (ahí desde V2-086) lo volvía local para TODA la función, así que los tres usos anteriores
  —`show_images`, el guarda de música y el de mensajería— reventaban con `UnboundLocalError` antes de llegar a
  esa línea. Vivo desde que nació el alias el **2026-09-18** (`91d60052`): cinco días en los que pedir una foto
  no podía funcionar. **(1) UNA LOCAL QUE ENSOMBRECE UN MÓDULO IMPORTADO MATA TODOS SUS USOS ANTERIORES, EN
  SILENCIO** — y un test anclado al CÓDIGO FUENTE no lo ve nunca: la línea `_cvis.present(...)` estaba escrita,
  presente y correcta, solo que no podía ejecutarse. El trinquete es de la CLASE, no del caso: symtable
  contesta «¿es local aquí?» y ast «¿se lee antes de escribirse?»; medido en todo el motor, dos sombras
  inocuas y CERO vivas. **(2) EL MANEJADOR CULPABA AL PROVEEDOR de cualquier excepción**: abría un cooldown
  sobre un escalón sano, encendía la luz del modelo acusando a DeepSeek mientras DeepSeek contestaba, y
  ascendía al suplente para un fallo que ningún suplente puede curar —la misma excepción salta en el suplente—.
  Ahora el turno pregunta **de quién es la culpa antes de tocar la escalera**, y la prueba es la EXCEPCIÓN, no
  su texto: un fallo de proveedor trae un estado HTTP, uno nuestro es un error de Python pelado. **(3) LA
  ALERTA VIAJABA COMO EL LITERAL «flash layer error»**, con la excepción tirada, así que la observabilidad
  enseñaba seis alertas idénticas sin causa y el diagnóstico había que hacerlo grepeando el log del proceso —
  justo lo que él pedía no tener que hacer. **(4) EL FAILOVER SOLO MOVÍA EL TURNO SIGUIENTE.** *«Para eso
  tenemos un failover, para que esa misma request que ha fallado se vuelva a enviar al otro modelo.»* Ahora se
  reenvía, y vive en el bucle de CONEXIÓN de `fast_client`: es el único momento del turno en que el proveedor
  ha fallado y no ha salido ni un token, así que reenviar no cuesta ni media frase hablada ni una tool
  disparada dos veces. Un solo salto, nunca a la puerta que acaba de fallar, y **el cuerpo se reconstruye para
  el proveedor nuevo** (`thinking:disabled` es de DeepSeek y un 400 en OpenAI: reusarlo haría parecer roto a un
  suplente sano). Un fallo a mitad de stream sigue perdiendo el turno, a propósito. **(5) EL PANEL LEE LA
  ESCALERA EN CADA SONDEO**, no solo con la luz ya encendida — que era el caso invisible: en cuanto contesta el
  suplente, `fast_client` apaga la luz al primer chunk, así que un motor relevado con éxito pintaba la fila
  VERDE. Quién contesta es un hecho de la escalera, no de si un error sigue fresco. La caja del modelo se llama
  ya **«Cerebro rápido · FlashBrain»**, nombra al titular siempre, enseña al suplente aun sano, y pasa a ámbar
  con dos líneas cuando el suplente sirve; la de **memoria lleva las mismas dos líneas** (el CORAZÓN releva
  desde 2026-08-19 y nada fuera de `process()` podía verlo: `status()` reportaba el titular contestara quien
  contestara); y un fallo NUESTRO tiene **fila propia, solo cuando existe**, con el nombre de la excepción. Un
  relevo es ÁMBAR, nunca rojo —*«si fallaran los dos, entonces sí que habría que marcarlo en rojo»*—. **(6) LA
  CAÍDA DE EMBEDDINGS ERA MUDA**: `_report_degraded` solo saltaba al DEGRADAR el backend; que el titular falle
  una llamada viva difiere el vector y tira el recall a léxico sin decir nada. Ahora lo dice, una vez por
  cambio, y solo se apaga su propio ámbar («una luz, catorce escritores»). **⛔ Y LO ÚNICO QUE PIDIÓ Y NO SE HA
  HECHO: los embeddings NO PUEDEN tener un modelo de relevo, y construirlo sería el bug.** Un modelo de
  embeddings DEFINE el espacio vectorial en el que ya vive cada píldora de `zaelar.db`: un suplente distinto no
  contesta la misma pregunta más barato, contesta en coordenadas que no se pueden comparar con nada guardado.
  Moverlo es re-embeber la memoria entera, nunca una edición de config. El único suplente honesto es el MISMO
  modelo por otra puerta, y hoy no hay: medido contra sus claves ese día, OpenAI 200 en 269 ms, **AIMLAPI 403
  `error code: 1010`** (clave muerta) y DeepSeek sin endpoint de embeddings. Así que se hizo VISIBLE la
  degradación en vez de taparla con un sustituto que envenenaría el recall en silencio, con un test que se pone
  rojo el día que alguien «arregle» la tabla. Decisión suya pendiente: el camino barato a un relevo real de
  embeddings es una clave de AIMLAPI que funcione (mismo modelo, mismo espacio, sin migración). Nodo 2.77, 39
  tests, **28 desarmes rojos** — cuatro nacieron VERDES y los cuatro acusaban al test: `UnboundLocalError` es
  **subclase de `NameError`** (quitar solo el primero no cambia nada), la rebanada del bucle de conexión cogía
  la primera de DOS ocurrencias del mismo comentario y abarcaba media clase, el ámbar de embeddings se probaba
  llamando a la función y no al CABLEADO (lección de V2-756), y un ancla que no existe no es un verde.
  **No probado por voz.**

- **Tocar una tarjeta suya se le PREGUNTA antes (V2-757, 2026-09-23)**: sesión `f84f91ef`, sobre el build
  de V2-756. Con el micro abierto, el operador dictó un encargo de diseño a OTRA conversación; el turno lo
  leyó como suyo (`escalate` 0,73 — y no se equivocaba: ERA un encargo, lo que no era es NUESTRO), contestó
  «lo mando hacer», y un Brain Worker **bifurcó su tarjeta de vídeo y le reescribió 249 líneas de CSS**. Su
  *«Olvídate de eso, no va por ti»* llegó a los cuarenta segundos y el worker siguió un minuto más; el
  *«no estaba hablando contigo. Eso lo tienes que parar y deshacer»* llegó con la ventana de atención ya
  cerrada. **(0)** ⭐⭐ El fork vivía en `widgets/_user/youtube/`, que **ensombrece al built-in** en catálogo,
  `identify`, el `widget.js` servido y los imports de Python — y está gitignoreado: `git status` limpio
  mientras la tarjeta que CORRE no es la del repo. **V2-755 y V2-756 llevaban horas inertes en su máquina.**
  Lo encontré porque un test falló enseñando el `__file__` del módulo, no por leer código. Deshecho a
  `TMP/deshecho-2026-09-23/`. **(1)** ⭐ Su norma, dicha esa tarde: *«hay que pedir confirmación siempre que
  pidamos crear un widget o modificar un widget… que sea algo de sistema»*. La puerta va en
  `dispatch._run_session`, junto al gate de irreversibles, porque al generador se llega por SEIS sitios y
  *una regla que cada llamador tiene que recordar no es una regla*; allí `kind == "code"` ya significa «va a
  escribir el código de una tarjeta». Reusa el confirm-gate entero (el sí/no determinista, la línea que
  impide narrar progreso, la caducidad); la pregunta sale de la tabla de idiomas y **no dice «irreversible»**
  — construir no es peligroso, es caro y visible. Medido: sus dos frases de retirada clasifican `no`.
  **(2)** `worker_api` montaba CUALQUIER id: `act show --help` dejó una tarjeta rota llamada «--help» en su
  pantalla y contestó `OK`. Ahora se valida contra el catálogo y el error **nombra lo que sí hay**.
  **(3)** Una búsqueda dejaba seis resultados numerados en una cara que él no miraba: *«yo no veo el
  catálogo, solo veo el vídeo de Ronaldinho»*. Espejo de V2-755 sobre el mismo raíl `goto_tab`; el
  reproductor no se toca. **(4)** `question` sale de `NOT_AIMED_AT_THE_SCREEN`: «¿Puedes enseñarme el
  catálogo?» midió `show_tab` **0,85** y lo vetó `request_type=question` 0,64 → la tarjeta no se movió y el
  turno lo PROMETIÓ (*«dices que vas a hacer eso, pero no lo haces»*). En castellano la orden educada tiene
  forma de pregunta; medido sobre los candidatos reales, toda pregunta de verdad contesta `none` 0,78-0,94.
  **(5)** La cola de una frase no es una orden: «…en el año» es léxicamente una frase TERMINADA, así que
  «sesenta y nueve.» llegó como turno propio y se ejecutó como `set_volume 69` (*«Yo no he dicho nada de
  ningún volumen»*). Reusa `escalation_guard.is_a_fragment` —una regla, dos consecuencias— con tres
  condiciones obligatorias: sin la de «solo un número» el guarda alcanza «páusalo» y «páralo», que
  `too_thin_to_commission` también llama fragmentos (medido en el desarme). **(6)** El orbe se va a la barra
  cuando algo se pone a pantalla completa y vuelve al salir, sin pisar su preferencia — el dock de V2-623
  movido por el DOM. ABIERTO: no probado por voz; retirar un worker YA lanzado sigue dependiendo de su raíl
  de `stop`; y por qué un encargo dictado a otra conversación se lee como propio dentro de una ventana de
  atención abierta no se ha tocado — la puerta lo convierte en una pregunta, que es contención, no
  diagnóstico. Nodo 2.76. Detalle: `V2-757-tocar-una-tarjeta-suya-se-le-pregunta.md`, `N-024`.

- **Un número que él ha dicho no es una invención (V2-756, 2026-09-23)**: sesión `74be8e9a`, sobre el
  build de V2-755 — que AGUANTÓ (el catálogo obedece, el arnés abre objetivos y los CIERRA, el veredicto
  completa turnos vacíos y registra discrepancias, «Pausa el vídeo» la resolvió la tabla hash sin modelo).
  Cinco capas nuevas. **(1)** ⭐ «Ahora quiero que me pongas el vídeo número tres» volvió como
  `play_video(action=list)` —una BÚSQUEDA— tres turnos seguidos, con el brief diciendo `play_result` 0,95;
  y cada búsqueda re-descargaba y **renumeraba** la banda a la que sus números se referían: *«Bueno, ponme
  el vídeo dos, que los has cambiado»*. **Una pregunta hecha dos veces no puede cambiar su respuesta**: la
  misma query sobre la misma banda se responde (`unchanged`), no se re-ejecuta. Con su límite, que cazó un
  test vecino y no yo — si la banda lleva algo que él ha rechazado desde entonces, repetir NO es la misma
  pregunta (V2-634). **(2)** ⭐ «Bórrame los tres últimos de la cola» borró UNA fila: `remove` tomaba un
  `item` mientras su espejo `add_results` acepta «1,3» desde V2-632, y la regla es una acción por turno.
  El modelo lo había entendido —la voz dijo «quito el 4, el 5 y el 6»— y el veredicto, sin nada mejor,
  llegó a contestar `clear_list`, que vacía la cola ENTERA (patrón V2-742). Acabó en *«Eso es absurdo, no
  estás entendiendo la tarea»*. Declarado el plural: `remove` 0,98-1,00 sobre sus frases y `clear_list`
  0,94 sobre «vacía la cola entera», intacto. **(3)** ⭐ **Un número que ÉL ha dicho es una lectura, no una
  invención** — V2-741 se niega a inventar y tiene razón, pero «el vídeo número tres» sobre una banda
  numerada no es inventar; misma clase que el alias declarado de V2-754. Destapó un defecto viejo:
  `resolve` metía la frase ENTERA en `item`, y una clave de índice no es una query. **(4)** `show_tab` sin
  `tab` volvía `unknown_tab` sobre una frase que nombra la cara, y él preguntó *«¿Has ignorado la orden que
  te he dado?»*: `fill_missing` solo AÑADE una clave vacía, por un alias declarado o un número dicho —
  repara una omisión, nunca edita una decisión. Y **un alias que casa con casi todas las frases no
  desambigua nada**: `player` declaraba «el vídeo» en una tarjeta de VÍDEO. **(5)** ⭐ **Inseguro ≠ ausente**:
  «Para el vídeo» midió `pause` **0,95** en la pregunta de pantalla con `request_type` partido (answer 0,49
  / comment 0,39) y no pasó nada, porque el gate exigía una orden CONFIADA — un lector inseguro vetando a
  uno casi seguro. Ahora es lista de RECHAZO (comment/question/greeting) y el motivo está medido: la
  pregunta de pantalla contesta `none` **0,87-0,99** para toda observación ambiental, así que los dos
  guardas coinciden donde importa y solo éste se equivocaba; `complaint` queda fuera a propósito (V2-750);
  sin respuesta ninguna se sigue fallando cerrado. **Observabilidad, sus dos mitades**: el registro del
  prompt guardaba cabeza y cola y omitía el CENTRO —donde va lo que hay EN PANTALLA—, así que para saber si
  el modelo veía la banda hubo que reconstruir el digest a mano contra un almacén que ya había cambiado
  (tercera vez que este recorte cuesta un diagnóstico: V2-195, V2-255); y una discrepancia con una tool
  GLOBAL no dejaba rastro, porque el `⚖️` solo vivía dentro de la rama de `widget_data`. **⚠️ Una medición
  contra el conjunto de candidatos EQUIVOCADO acusa al arreglo**: medí «los tres últimos» con los
  candidatos de otra sesión, donde `remove` ni estaba, y parecía que lo empeoraba. Nodo 2.75 · 10 desarmes, 10 rojos ·
  **⭐⭐ y una trampa que vale más que los arreglos: un desarme puede dejar BYTECODE RANCIO.** El arnés
  restaura con `cp`, y si eso cae en el MISMO SEGUNDO en que se escribió el `.pyc` compilado desde la
  versión desarmada, Python da la caché por buena (mtime con granularidad de un segundo) y todo proceso
  posterior ejecuta el código DESARMADO: cuatro tests míos salieron rojos en la pasada ancha y verdes
  sueltos, y una pasada entera corrió contra código desarmado sin que nada lo dijera. Se ve en
  `fn.__code__.co_names`, no en `inspect.getsource`, que lee el fichero. El arnés ahora borra
  `__pycache__` al restaurar. · una regresión real cazada por un test vecino y un desarme verde por el motivo equivocado,
  ambos escritos. ABIERTO y dicho: por qué el modelo eligió `play_video` no se ha medido (la elección de
  tool es del modelo rápido, no de Jev), y el árbitro vetó en sombra SIETE acciones legítimas en esta
  sesión — el portón F0→F1 de V2-653 es «cero falsos vetos en sesiones reales».

- **Un descriptor le roba la palabra al vecino (V2-755, 2026-09-23)**: sesión `665e666a`, sobre el build de
  V2-754 — que aguantó: «Vuelve, por favor, al inicio. Al catálogo inicial.» → `show_tab` **0,97** y el alias
  `home` resuelto. Lo que falló fueron tres capas apiladas en noventa segundos. **(1)** «**Vale, para el
  vídeo.**» volvió `screen_action` = **none 0,65** (pause 0,05) y el modelo no llamó a nada: `pause` estaba
  declarado en cuatro palabras y `close`, engordado por MÍ en V2-753 para ganar «Páralo, y vuelve al inicio»,
  abría con «**PARA** el vídeo de verdad» — y «para» es además la preposición, así que «Vale, para el vídeo.»
  se lee «OK, for the video.». Tuvo que decirlo dos veces: *«Yo no tengo por qué estar repitiendo las
  acciones.»* ⭐ **Tercera vez con esta forma y las tres son mías** (V2-754 metió «inicio» en `restart`): al
  tocar un descriptor se mide el **vecindario**, no la frase que se persigue. Y **un homógrafo se cierra
  nombrándolo**: con las frases citadas pero sin «ahí «para» es el verbo, no la preposición» medía `none`
  0,47; con ella, `pause` **0,98**. **(2)** El `show_tab` que escribí en V2-754 tiene **485** caracteres sobre
  un corte de 200, así que «al inicio del widget de vídeo» nunca llegaba y su frase seguía volviendo `restart`
  (0,69). V2-753 subió el corte; el fallo es escribir por encima de él. **48 de 220** acciones declaradas
  estaban por encima: tres arregladas, **45 son deuda declarada con trinquete** (nodo 2.74). **(3)** «Ponme el
  vídeo número seis» desde el catálogo: `play_result` disparó, el sexto entró en el reproductor y **la
  pantalla no se movió** — la tarjeta salta al reproductor cuando un vídeo LLEGA a una tarjeta vacía
  (`!st.key.slice(2)`), no cuando se CAMBIA. Corrió dos veces invisible y el tercer intento lo comió, con
  razón, el guarda de re-emisión. Una orden de reproducir declara ahora la cara del reproductor en la **capa
  de datos**, donde se sabe que es una orden, por el raíl `goto_tab` de V2-742 — y el avance automático al
  terminar un vídeo NO, porque leer la cola mientras suena uno es cosa suya; más una guarda para que una orden
  rancia no le aparque en un reproductor vacío tras recargar. **(4)** Y en CADA turno de esa sesión el prompt
  decía «la hoja `youtube` sigue **VACÍA**» sobre seis resultados y un vídeo sonando: ⭐ `harness.verify`
  devolvía «ilegible» y se callaba —como manda el docstring del módulo— pero `prompt_lines` imprimía todo
  objetivo abierto como vacío **sin preguntarle**. La regla estaba instalada en la rama que nadie lee (la
  clase de V2-743). Ahora el prompt solo habla de lo que un verificador encontró incumplido, `youtube` declara
  `empty` (así que el objetivo por fin puede cerrarse) y una tarjeta ilegible deja una línea en vez de
  silencio. **No tocado a propósito**: la tabla de verbos del backstop de promesas («le doy al pause» no casa
  `_COMMITTED_RE`) sería la quinta del mes. **Anotado**: el árbitro vetó en sombra un `pause` legítimo
  (`data-drag`) — un falso veto en sesión real, que es el portón F0→F1 de V2-653. Nodo 2.74 · 13 desarmes, 13
  rojos · tres de ellos salieron verdes primero porque las comillas del shell dejaron el fichero intacto: el
  arnés de desarme ahora compara el fichero y se niega a correr si no mordió.

- **El veredicto completa al modelo, nunca lo desmiente (V2-754, 2026-09-23)**: sesión `3afe34a8`, sobre el build de V2-753, cuatro órdenes para volver al catálogo de vídeos — *«no sé por qué no entiende rápidamente… tampoco entiendo cuál es el papel del modelo Jev aquí»*. La tabla lo dice todo: «Vuelve al dashboard, quiero seguir viendo el catálogo» → brief `show_tab` **0,96** ✓ y el modelo `play_item` sobre un ítem inexistente ✗ → «¿a cuál te refieres?»; «Sí, el catálogo de vídeos» → `show_tab` 0,88 ✓ y el modelo **nada** ✗ → «te dejo otra vez el catálogo» sobre nada; «vuelve al inicio del widget de vídeo» → brief `restart` **0,99** ✗ y el modelo `show_tab(tab="home")` ✓ → **`unknown_tab`**; a la cuarta funcionó y apagó. ⭐ **Cada lector acertó exactamente donde el otro falló, y nadie los cruzaba.** El papel de Jev era una segunda opinión que leían guardas sueltos; no un enrutador. Y **no puede serlo solo**: a 0,99 habría reiniciado el vídeo que pedía dejar. Su propuesta —jerarquía con pesos por contexto y estado, tabla hash para lo canónico— contrastada con lo que hay: la tabla hash **existe** (V2-539, 2.817 entradas; «ábreme la agenda» va directa) y lo que la mató fue «Fantástico, » delante, por doctrina escrita; la jerarquía existe como preguntas paralelas con probabilidades, no como decisión. Faltaba el único sitio donde se compone. **La regla** (`direct_action.complete`), en el único sentido que la evidencia permite: (1) una llamada VÁLIDA del modelo corre siempre y una discrepancia se REGISTRA — la medición que dirá a quién creer; (2) donde el modelo dejó el turno vacío o su llamada no resolvió, la acción del veredicto sobre la tarjeta abierta rellena el hueco por `apply_widget_data`, la misma puerta `action_mode_now` que toda llamada — **nada nuevo ejecuta; algo declarado deja de quedarse sin ejecutar**; (3) el turno vacío solo si el brief leyó ORDEN o RESPUESTA. Dos formas de payload que el peldaño de V2-741 no sabía rellenar, ambas el incidente: acción SIN payload (dispara sin inventar; con claves opcionales sigue sin rellenarse) y clave ENUMERADA por un alias que él dijo — `widgets/enums.py` lee `inicio (home, dashboard, catálogo) | player (reproductor) | …` del manifiesto, **un solo texto, dos lectores**: el modelo ve las palabras y el widget las acepta. ⚠️ **Mi descriptor de la noche anterior empeoró una frase**: «vuelve al inicio DEL VÍDEO» en `restart` es lo que lo puso a 0,99; sin «inicio», 0,61, y sus propios casos siguen a 1,0. **Valorado y retirado**: tolerar muletillas en la tabla hash — su doctrina lo prohíbe y era la pieza de más que él pidió no añadir. Simulación con los veredictos reales del log: T2 y T3 → `show_tab{inicio}`; T4 → `home` aceptado como alias, discrepancia registrada. Nodo **2.73**; **10 desarmes, 10 rojos**; dos tests vecinos reanclados sobre su afirmación. **ABIERTO y dicho**: no probado por voz; una orden compuesta sigue teniendo un veredicto; el canal de texto no dispara brief; `nucleo.py` crece 18 líneas con el trinquete ya rojo.
- **Parar el vídeo y volver al catálogo — la llamada correcta, comida cinco veces (V2-753, 2026-09-23)**: segunda vez que lo reporta. *«Ha ido muy bien hasta el vídeo, pero luego ha sido **incapaz de parar el vídeo y de volver al catálogo**, que es lo mismo que había dicho yo en la versión anterior.»* Sesión `46dcfcb4`: tarjeta abierta, búsqueda de vídeos de Boeing 747, «ponme el tercero» → reproduciendo, todo correcto. Entonces *«Uf, me he equivocado. Páralo, y vuelve al inicio.»* y **el modelo acertó**: emitió `widget_data(youtube, close)`, que está declarada como «lo detiene de verdad y lo quita del reproductor» — las dos mitades de su orden. El guarda de V2-635 leyó la frase, no halló ningún verbo de `_CLOSE_VERB_RE` —«parar» no es un verbo de cerrar y no debe serlo— y la llamó arrastre. **Cinco veces en noventa segundos**, mientras la voz decía «lo paro y vuelvo al inicio» sobre un vídeo que seguía sonando, hasta que él dijo *«veo que es incapaz de pararlo»*. ⭐ **TRES defectos apilados sobre una sola orden.** **(1) La pregunta de pantalla decapitaba su propia respuesta.** `turn_brief.target_question` cortaba cada `desc` declarado a **90 caracteres**, y `youtube:show_tab` declara «CAMBIA de pantalla… `'inicio'` es el catálogo/dashboard… **es lo que responde a «vuelve al catálogo», «a la página de inicio»**…» — frase que V2-742 metió en el manifiesto justamente para que la decisión encontrara la acción, y el corte caía en «`'inicio'` es el ca». Medido contra la API real con sus palabras: «vuelve al catálogo» → `none` **0,77** a 90 chars y `youtube:show_tab` **0,96** a 200; «y tampoco vuelves al inicio a ver el catálogo» 0,32 → 0,83; y `pause` 1,00, `next` 0,94, `search` 0,99 sin moverse en ninguno de los dos. Precio: **+1,1 KB sobre una pregunta de 4,7 KB y ningún cambio de latencia** (47 candidatos, ~850 ms en ambos). La regla que deja: antes de acusar al modelo de decisión de no elegir una acción, mirar **cuánto de su descriptor llega a la pregunta**. **(2) «vuelve al inicio» es ambiguo y el manifiesto no ayudaba**: `restart` decía «reinicia el vídeo desde el principio», así que la frase volvía `youtube:restart` a 0,98 — un veredicto que habría **reanudado** el vídeo que acababa de pedir parar. Con los dos descriptores afilados (restart dice que SIGUE sonando y que su «inicio» es el del vídeo; close dice que PARA), la misma frase vuelve `youtube:close` a 0,93 y «ponlo otra vez desde el principio» sigue siendo `restart` a 0,99. Un descriptor es dato de producto y el sitio donde se repara un fallo de enrutado — pero solo la parte que LLEGA decide algo. **(3) Una gramática decidía una ruta sola, y el arreglo ya existía una rama más allá**: el guarda del `[[close]]` de canvas consulta un segundo lector desde V2-635 (`show_target.close_has_order`) y el de la **data-op** `close` nunca tuvo esa salida — la misma regla instalada en una sola de dos ramas, y la rama sin reparar es la que dispara sobre un reproductor de verdad. `close_guards.dataop_close_licensed` la instala: gramática primero, después el veredicto `screen_action` que este turno YA pagó, y su «no» («no lo cierres») vetando a los dos. Exige nombrar **esta tarjeta Y esta acción** — «pausa el vídeo» tiene que seguir siendo una pausa y no un reproductor vaciado— así que solo CONCEDE, y «Johnny eres tonto» (el incidente de V2-635) sigue bloqueado. Cableado también en la puerta de «mostrar puro», que se comió otro close esa misma sesión sobre una frase con «ver» dentro. ⭐ **Y encadenó hacia lo caro**: la promesa vacía que dejó el guarda disparó el backstop de promesas, que **FORZÓ** un worker `claude_code` con navegador headless —cuatro minutos, cero resultados, un `about:blank`— para parar un vídeo, sobre un brief que había contestado `escalate_or_inline = handle_inline` a **1,00**. Él tuvo que decir *«yo no te he pedido que hagas nada… páralo inmediatamente»*. Un backstop existe para cuando NO hay información; cuando la hay, la lee — y **una promesa que vaciamos nosotros no es un encargo, es un bug, y gastar minutos en él lo convierte en dos**. Solo un `handle_inline` CONFIADO anula la escalada: sin brief, inseguro o en vuelo, la ruta de hoy bit a bit. Nodo **2.72**; **8 desarmes, 8 rojos**. ⚠️ Tres casos del backstop pasaron en verde con la frase equivocada —escribí un `op_text` bonito y `looks_like_web_task`, el disparador que está por encima de esa puerta, no casaba, así que los tres «se mantiene el camino de hoy» pasaban porque nunca escalaba nada—; se pincharon con sus palabras verbatim y la razón quedó escrita en el fixture. Un test vecino fijaba la ORTOGRAFÍA vieja del guarda (`not _router.looks_like_close(text)`): reanclado sobre la llamada nueva conservando su afirmación, y comprobado que sigue cazando la eliminación entera del guarda. **ABIERTO y dicho**: el veredicto sigue siendo UNA respuesta para una orden COMPUESTA —aquí da igual porque `close` cubre las dos mitades por definición, pero una compuesta cuyas mitades sean dos acciones distintas pierde una—; el canal de texto no dispara brief, así que ahí la gramática sigue decidiendo sola (abierto desde V2-741); **y no lo ha probado por voz**.
- **La columna del chat es la conversación (V2-752, 2026-09-22)**: sesión `fce3eff3`, 1.401 eventos, 7,5 minutos, con el encargo de leerla entera — *«el motor de la conversación es una de las bases de nuestro proyecto… no puede dar la sensación de que se pierden cosas en el limbo y no puede ser porque yo las veo en pantalla, eso es que las has procesado»*. Siete fallos, y **él los fue narrando en directo para que quedaran transcritos**. ⭐ **9 de 24 respuestas (37,5 %) se escribieron en el muro y NUNCA sonaron** — incluida la que leyó en voz alta como prueba («este mensaje de “un momento”, si ahora mismo no llevas ningún widget»). Dos mecanismos, los dos suyos: la línea se escribía al GENERARSE y una ventana de gracia de 1.200 ms la mostraba entera si no llegaba subtítulo, así que un barge-in que cancelaba la locución antes del primer frame de audio pintaba un párrafo jamás dicho… y la respuesta siguiente lo BORRABA — *«vas poniendo de golpe un montón de un párrafo lleno de mensajes y luego lo borras»*, que es literalmente el código; y el subtítulo progresivo era privilegio del ÚLTIMO mensaje (`i === msgs.length - 1`), de modo que tres respuestas generadas en 3 s pintaban las dos primeras enteras y de golpe. **La ventana de gracia se retira y lo que la sustituye no es un temporizador más largo: es EVIDENCIA.** `bot_speech speaking` es el motor diciendo que la locución llegó al altavoz, lleva el `trace` del turno y no depende del transporte de subtítulos — así que un build sin transcripción sincronizada sigue escribiendo el muro (el caso para el que existía la ventana) y una respuesta cancelada no escribe nada. Y **la identidad de una línea es su `trace`, no su posición**: el registro hablado llega con mediana **7,3 s** (máx **20,8 s**) de retraso, así que comparándolo solo contra la última fila cualquier frase suya en medio lo convertía en burbuja nueva debajo — *«en el chat estás duplicando mensajes, me los estás intercalando entre los míos»*. ⭐ **El acumulador pegó dos frases que no van juntas y CERRÓ un widget.** «quita este vídeo y vamos otra vez al [inicio]» — Deepgram nunca entregó «inicio» — más «No me estás oyendo.» produjo `«…vamos otra vez al No me estás oyendo.»`, y Jev leyó ese sinsentido como `canvas=close` a **0,93**. Ninguna capa podía cazarlo: capa 1 pregunta si el texto MEZCLADO cuelga (acaba en punto → «completa») y capa 2 solo se consulta cuando capa 1 dice incompleta, o sea que **nunca corrió**; las dos juzgan la mezcla DESPUÉS de hacerla. `nucleo/flash/continuation.py` hace la pregunta que nadie hacía —¿B continúa a A?— con opciones enumeradas, en cualquier alfabeto. **Es un clasificador PRE-modelo y cuesta lo que cuesta uno**: el precio que él autorizó, dicho en la cabecera del módulo, y contenido porque solo se pregunta EN UN EMPALME — 10 turnos de 28 en esa sesión; los otros 18 no pagan nada. Ausente, apagado o inseguro → pega, la ruta de hoy bit a bit. Mismo módulo: `_grows` comparaba contra el búfer ENTERO y el STT devolvió el SEGUNDO fragmento más largo, así que una cláusula que él dijo una vez llegó al prompt, a Jev, al procesador de memoria y a su muro **dos veces** (la fila 19 de su `memories` real la conserva). ⭐ **Dos correcciones suyas eran CORRECTAS en el modelo y un guarda se las comió.** «He dicho, Apollo once.» → `query="Apollo 11"` → `🛡️ play_video ignorado` → `⚠️ promesa sin acción`, y otra vez 15 s después. Aterrizó a la tercera, cuando puso un sustantivo de medios en la frase: *«¿Cómo es posible que haya costado tanto llegar hasta aquí?»* — llevaba bien desde la primera. **Todos los lectores acertaron sobre la frase que les dieron**: la gramática no halló verbo de medios (cierto: una corrección toma su sujeto de lo que corrige) y `screen_action` contestó `none` a 0,92 (cierto: leída sola, esa frase no pide nada). Nadie preguntaba lo que la situación planteaba, y `🗣️ queja sobre lo ya hecho` saltó **cinco veces** en la sesión usándose solo para SUPRIMIR. `redo_decision` lo pregunta con lo que REALMENTE se hizo delante (`done_ops`, mutaciones que corrieron de verdad) y **solo concede la licencia de la op que corrige**, acotada a esa tarjeta. ⭐ **Y el worker de los vídeos lo lanzó el AUDITOR, no el enrutador** — su queja de V2-750 por una puerta que aquella tanda no miró. El susurro vio la promesa sin nada detrás, concluyó bien que una acción consecuente había fallado, y escaló un Claude Code entero para una búsqueda de YouTube: **4 minutos**, navegador real, un clic dentro de los comentarios de un vídeo, dos peticiones de un widget llamado `videos` (la tarjeta es `youtube`) y cero resultados. Cuando la acción fallida es una acción DECLARADA de una tarjeta, la reparación que pide esa premisa es la LLAMADA. ⚠️ La primera versión de ese guarda degradaba por NOMBRAR una tarjeta y era demasiado ancha —«búscame un restaurante y apúntalo en la agenda» nombra una y es exactamente para lo que existe un worker—, así que exige además que esa misma tarjeta haya corrido una op hace minutos, que ES la premisa y es falsa en todo encargo en frío. ⭐ **El backstop de cierre es una tabla de verbos y cerró su tarjeta tres veces**, dos de ellas sobre frases en las que él se quejaba del cierre: *«Yo no te he dicho en ningún momento que CERRARAS el widget de vídeo»* → cerrado otra vez. En las dos, `canvas` ya había contestado `neither` — preguntado, pagado, sin lector. Ahora el veredicto manda, **y solo un `neither` seguro prohíbe**: ausente o inseguro deja la ruta de hoy, porque un brief que no aterriza no puede dejar al motor sordo a «ciérralo». ⭐⭐ **Y auditando el propio plan —que él pidió antes de ejecutarlo— apareció lo peor, en su memoria REAL**: la fila 16 decía `slot: assistant.name · «El asistente se llama Apollo 11.»`. Su asistente llevaba desde `+154.9 s` llamándose **«Apollo 11»** por una corrección de búsqueda, con la palabra de activación detrás, en silencio y entre sesiones. **El agujero es nuestro y tenía un día**: V2-747 eximió ese slot de la guarda «¿habla del operador?» (con razón: un renombrado nunca habla de él) y del anti-garble (con razón: un renombrado contradice el valor viejo a propósito), y entre las dos lo dejaron escribible con la sola firma del modelo pequeño. V2-747 fue una guarda aplicada al conjunto que PARECÍA la clase en la dirección de negar; esto es el mismo error en la de conceder. La pregunta que faltaba la contesta un veredicto y **nunca una regex** — una hermana de `_talks_about_the_operator` sería una tabla de verbos y además ciega fuera del alfabeto latino. ⚠️ **Aquí la dirección de fallo es CERRADA**, al revés que el resto: negar de más cuesta repetir un renombrado (y la vía explícita, que funcionó bien en esa misma sesión, sigue intacta); conceder de más cuesta una identidad que él nunca dio. **Su estado está reparado**: `assistant_name` vuelve a «Johnny» —sus propias palabras de esa sesión, no un nombre elegido por mí— y la píldora 16 queda inválida, no borrada. **Lo que se RETIRÓ a propósito**: `_deduped` sobre el texto junto (colapsa una restitución acústica **y también a una persona que se repite**, y rompía la válvula de tamaño — editar sus palabras es la dirección cara); una rama para «¿y si la mitad retenida estaba completa?» (código muerto: un fragmento completo se entrega al llegar y nunca alcanza un empalme); y **armar el árbitro del canvas** — su propia puerta es cero vetos falsos en sesiones reales y **esta sesión la suspende** (`⛔ vetaría · show-drag` sobre el YouTube que él acababa de pedir), además de que su regla `close-grammar` lee la misma tabla y no podía cazar el fallo del backstop. Nodos **2.69**, **2.70**, **2.71**, **3.78** y **4.210**; **23 desarmes, 23 rojos**, tres de ellos verdes al primer intento y reescritos (uno no desarmaba nada; otro fijaba `WINDOW_S + 60`, cierto para cualquier ventana, cuando la decisión era la DISTANCIA). **Dos defectos de mi propio código los encontró su test, no yo**: el registro hablado de un turno cancelado seguía creando burbuja, y el registro sin `trace` de una línea aún no pintada perdía el recorte. De paso, el instrumento que faltaba: `window.onerror` y una línea por sesión diciendo si el canal de subtítulos vive — auditando esto, «¿llegó a disparar?» no se podía contestar desde el log y se planificó una fase entera sobre esa conjetura. **ABIERTO y dicho**: la reparación post-modelo del vocativo («Pues verás, Johnny» dicho A él) — la mitigación de prompt ya es la forma más fuerte y su propio comentario admite que no es garantía dura, y reescribirlo sería editar lo que dice el agente en mitad del stream; «inicio» lo perdió Deepgram y ninguna fase lo recupera (lo que cambia es que dejamos de INVENTAR una frase con el hueco); `test_task_recall_finds_the_errand_he_means.py` es flaky donde existe la base real del operador (2 fallos estables en checkout limpio, 2-5 variables en su árbol, también con mis ficheros fuera); **y no lo ha probado por voz**. `20b1ae4e` `516661a5` `1098c0ad` `a3ea0357`.
- **Una tabla de verbos no es un enrutador (V2-751, 2026-09-22)**: medido en la sesión **b41925f6**. Con la tarjeta de YouTube ya en pantalla —la había abierto él con la mano— dijo *«Entonces, vamos a hacer una cosa, ábreme el widget de vídeo, preséntame un catálogo de vídeos sobre el Apolo once»*. `looks_like_create_widget` contestó True, el `show_widget` se desvió al **GENERADOR**, se abrió un Brain Worker y dos minutos después su catálogo tenía un reproductor de vídeo **duplicado** llamado **`entonces-vamos-cosa`** — una tarjeta bautizada con el preámbulo de una orden. La casación, literal: `hacer una cosa, abreme el widget`; `_CREATE_WIDGET_RE` permite **45 caracteres de lo que sea** entre un verbo de crear y la palabra «widget» y nunca pregunta si el verbo lo **rige**. ⭐ **Y el veredicto del propio turno ya lo había contestado**: `catalog_widget = youtube` a **1.00** —preguntado, pagado y **sin un solo lector en todo el motor**, que es V2-740 otra vez— y al turno siguiente `screen_action = youtube:search` a 0.91, leído, USADO y desmentido, porque el guarda escribe la comisión *durante el stream*, antes de que nadie lea nada. **Tercera vez del mes con esa forma exacta** (V2-741 una licencia de gramática, V2-748 el gate de irreversibles), así que la reparación es una regla de AUTORIDAD y no otro patrón. ⭐ **F0, la medición que pidió él antes de construir nada** —nueve órdenes × cinco idiomas, catálogo real, criterios **sin traducir**—: `looks_like_create_widget` saca **35/45** (es 8/9 · en 9/9 · **zh 6/9 · ja 6/9 · hi 6/9**) y la decisión compuesta **44-45/45** en los cinco, a **p50 758 ms** dentro del brief que ya se paga. La tabla **no está sesgada al español: es de alfabeto latino** — «チェスのウィジェットを作って» (hazme un widget de ajedrez) devuelve False, o sea que en chino, japonés e hindi **el generador es inalcanzable por voz**, en silencio, que es la forma de fallo que nadie reporta. **¿Traducir al inglés? NO**: añade un viaje de modelo en la ruta crítica para algo que no es un problema de traducción — Jev no analiza gramática, **elige entre opciones declaradas**, y las opciones son el nombre y los alias que cada widget declara de sí mismo. **La regla** (`nucleo/flash/build_decision.py`): **VETO** si hay tarjeta nombrada y `build_or_use` no dice `build_new` → no hay generador, diga lo que diga la gramática; **ADD** si `build_or_use` dice `build_new` y no hay tarjeta → generador aunque ninguna tabla nuestra sepa leer el alfabeto; **si no**, la ruta de hoy bit a bit. Asimétricas a propósito: el veto solo puede NEGAR trabajo (negar de más cuesta una tarjeta que se abre en vez de una que se escribe) y construir exige un veredicto POSITIVO más ninguna tarjeta nombrada, porque un widget son dos minutos y una carpeta nueva en su catálogo. ⚠️ Dos cosas que la medición dictó en vez de decorar: **`catalog_widget` SIEMPRE nombra algo** («¿qué tiempo va a hacer mañana?» → su propia tarjeta de tiempo a 0.76), por eso esta decisión **nunca abre nada** por su cuenta; y **`build_or_use` oscila** (0.32-0.97), por eso vetar necesita una señal y construir dos. **Depuración de contexto, su otra petición**: sección **«ALERTS»** nueva arriba del todo de `zaelar-architecture.md` (siete entradas, cada una con su incidente medido y su id de sesión, y regla de admisión escrita); y el **§8, que se declara CANÓNICO del catálogo de tools, iba nueve por detrás** — decía 20 y `router.TOOLS` tenía 29, así que `show_panel`, `fullscreen_widget`, `arrange_canvas`, `read_widget`, `search_listings`, `show_images`, `reopen_task`, `restore_widget` y `set_cluster_objective` existían en el motor y no en la página que un agente lee para saber qué sabe hacer el motor (V2-540 apuntándonos a nosotros). Añadidas, y **la afirmación pasa a medirse** en los dos sentidos (nodo 3.77): ni tool sin fila ni fila sin tool. Retirado además `entonces-vamos-cosa` por la puerta del motor (carpeta, store, caché de módulos, catálogo, tarjeta y lápida en memoria; 17 → 16 sin reiniciar). **Y su autorización, escrita con su precio**: un clasificador DELANTE del modelo queda permitido donde aporte, pero el número sigue siendo el número —brief a 785 ms, prompt a 3 ms, tools a 381 ms— así que cuesta **~780 ms de espera al turno**; aquí no hacía falta y no se ha puesto. Nodos **3.76** (la regla y su cableado), **2.68** (el corpus, live, tras `ZAELAR_LIVE_JEV=1` para que una pasada ancha no gaste 45 viajes) y **3.77**. 8+3 desarmes rojos; dos salieron verdes acusando al test y un `.pyc` rancio fingió un tercero. **ABIERTO**: F2 —`MAX_QUERY_WORDS` se mide contra el acumulado del segmentador y `take_rung` va sin `swallowed`— y F4, el trinquete de «ningún guarda nuevo decide solo». `454b4495`.
- **Un titular, UN suplente, y una luz que pregunta en vez de esperar (V2-751, 2026-09-22 — ⚠️ los commits `fddad31a` y `b1fcdde`, y los comentarios del código, dicen V2-750: otra sesión concurrente se llevó ese número y `main` no se reescribe por una atribución)**: *«¿Qué podemos hacer cuando falla el modelo principal? Cuando esto pasa no funciona nada.»* Y el panel se equivocaba sobre la avería que estaba reportando. **(1) LA ALARMA ERA UNA LUZ PEGADA.** Un turno de voz falló a las 12:21:02 (`Cerebro rápido caído — turno degradado`); a las 12:27 el panel seguía diciendo «deepseek-v4-pro · DeepSeek · no responde» mientras DeepSeek, sondeado ESE MISMO MINUTO, contestaba `/models` 200, $2,77 de saldo y un chat en 1,22 s. **Muchos escritores y UN solo apagador**: solo el primer trozo de un turno de VOZ llamaba a `health_state.clear("llm")`, así que sin micrófono abierto nada podía repintarla antes de los 600 s de TTL — la misma familia que la luz de memoria de 2026-09-10 («catorce escritores, una luz»). `nucleo/flash/titular_watch.py` es ahora la ÚNICA pieza del motor que le pregunta a un proveedor cómo está, con su cadencia: *«primero cada 10 segundos, luego cada 60 segundos, luego cada 3 minutos, hasta que consiguiéramos volver al principal»*. ⚠️ **Solo puede poner VERDE**: un sondeador que pudiera condenar a un proveedor sería una segunda opinión compitiendo con los turnos reales, y los turnos reales llevan el prompt, las tools y la latencia de verdad — así que no vota. Y el veredicto sale del ESTADO HTTP, nunca del cuerpo: `deepseek-v4-pro` contesta 200 con '' cuando el razonamiento se come el presupuesto, y leer el cuerpo sería condenar a un proveedor sano por responder como responde siempre. **(2) LA ESCALERA ERA DECORATIVA.** `voice_brain.failover` era `null` —documentado como RIESGO CONOCIDO a la espera de una decisión suya— y la cadena que debía relevar nombraba UN escalón que apuntaba a `api.deepseek.com`, **el mismo host que el titular**: una caída de DeepSeek se llevaba los dos. Peor: `_relays_suppressed()` vaciaba esa lista leyendo `is_cloud_account`, así que SU máquina no tenía relevo ninguno mientras la tabla decía lo contrario. El gate deja de preguntar QUIÉN CORRE y pregunta SI LA CLAVE ESTÁ, que es la misma protección aplicada al hecho que de verdad importa. **(3) SUS TRES REGLAS, EN TODAS LAS FILAS.** *Un titular y un failover* — la escalera de memoria de `memllm` pasa de tres escalones a uno. *Solo nativos* — fuera el escalón del broker: *«hay más posibilidades de que se caiga IML que que se caiga el proveedor original»*. *OpenAI NUNCA es titular*, lo que **revierte su propia directriz del 2026-09-10** que lo había puesto a la cabeza de la memoria: *«tenemos modelos baratos como titulares, los más potentes a nuestra disposición»*. La única fila que la regla no alcanza es `embeddings`, y lo dice en el fichero: un modelo de embeddings DEFINE el espacio vectorial donde vive cada píldora guardada, así que moverlo es una MIGRACIÓN, no una edición de config. **(4) EL SUPLENTE SE ELIGIÓ MIDIENDO** contra sus claves reales ese día: xAI 403 (créditos agotados, confirmando la retirada del 2026-08-30), Groq 403, Mistral 429 (tramo gratis), Gemini 2.5-flash 200 en 1,6 s pero **contestó en PORTUGUÉS** a un prompt en castellano al primer intento. `gpt-4.1-mini`: 200 en 1,16 s, castellano correcto y tool-calling ya probado en este motor — que es lo que importa, porque el cerebro de voz enruta widgets y eso es justo lo que rompe un suplente flojo. **(5) Y EL TITULAR DE VOZ ES V4.1-FLASH**, por instrucción suya y de vuelta a donde la voz pertenece (*«la voz tiene que funcionar súper ágil»*). Medido: `deepseek-flash` VE imágenes —un cuadrado rojo, «Rojo», 1,77 s— mientras `deepseek-v4-pro` devolvió cuerpo VACÍO en 7,47 s en la misma llamada. ⚠️ **El id es `deepseek-flash`**: `deepseek-v4.1-flash` da 400 con «The supported API model names are…». *Un anuncio no es un modelo*, medido dos veces ya. RIESGO ABIERTO y dicho: el banco que sentó a v4-pro midió al Flash VIEJO fallando `mostrar widget` 3 de 3; el 4.1 no está re-medido y ese banco se debe. **(6) EL PANEL DICE QUIÉN CONTESTA**: ámbar en vez de rojo cuando actúa el suplente —un titular caído CON suplente es un sistema degradado que funciona, y pintar eso de rojo le enseña a leer el rojo como «seguramente sigue bien»— con dos líneas y dos colores, compuestas en su idioma desde datos estructurados. **(7)** Cuatro literales que eran COPIAS de la tabla ahora la LEEN (`profiles.py`, `model_spec`, y dos tests): los cuatro se habían quedado atrás en esta promoción, que es lo que hace una copia de un hecho. 13 desarmes, todos rojos. Varios tests existentes hubo que reescribirlos en vez de borrarlos, y uno de ellos ya avisaba de esto exactamente: *«un test puede volverse el sitio donde sobrevive una decisión derogada, y entonces defender justo lo que hay que quitar»*.

- **«La primera vez le ha costado mucho» — el oído que no avisa de que no está (V2-749b, 2026-09-22)**: el mismo día, probándolo. *«He estado diciendo la palabra Johnny mucho tiempo y la primera vez le ha costado mucho, sin embargo la segunda vez ha sido prácticamente instantáneo… si dicen Johnny cuatro veces después de darle el botón de Start y no funciona se van a preocupar.»* Dos sesiones, tres defectos. **(1) EL DETECTOR SOLO SE CREÍA UN RESULTADO FINAL, Y CHROME FINALIZA CUANDO DEJAS DE HABLAR.** Sesión `5789bad4`: el grifo aparcó en **+0,32 s** (correcto) y el spot no llegó hasta **+33,55 s**, con los cinco «Johnny» dentro de UN solo final — `"entonces me estás escuchando Johnny Johnny no me oyes verdad Johnny Honey Johnny"`. Sin parpadeos de aparcado entre medias: el oído estuvo vivo todo el rato y sencillamente no reporta hasta que él calla. La latencia de un spot solo-finales **no es un número, es «lo que él tarde en parar»** — y eso no se puede escribir en un tooltip. Se arregla PARTIENDO las dos preocupaciones en vez de intercambiarlas: el INTERIM abre el grifo, la ventana y el anillo (barato y reversible: un falso positivo cuesta unos segundos de STT, nunca una acción equivocada), y el FINAL pasa a ser un RESPALDO para el único caso que el spot deja mudo — dijo el nombre y nada más, así que el STT de pago arrancó a media palabra y no tiene nada que contestar. El respaldo espera 1,2 s y se descarta solo si el STT de pago ya produjo un turno (`_wake["last_user_final"]`), porque los dos pueden aterrizar con cientos de ms de diferencia y **contestar dos veces es peor que contestar un segundo más tarde**. **(2) EL SALUDO SE PREGUNTABA A UN MICRÓFONO APARCADO.** El kickoff acaba en pregunta («¿Quieres que te cuente en qué puedo ayudarte?») y `attention` lo dejaba fuera de `note_addressed_speech` a propósito: correcto con el micro siempre abierto, donde una ventana gratis al arrancar significa contestarle a una sala entera. Con el grifo aparcado significa otra cosa — el agente le pregunta a quien pulsó Start hace un segundo y luego no puede oír la respuesta. Medido: saludo en +4 s, primera cosa que el motor oyó en +33 s. Ahora se arma, acotado a los modos que aparcan. **(3) EN UNA RECONEXIÓN EL OÍDO NO VOLVÍA, Y NADIE LO DECÍA.** Sesión `b41925f6`: `kickoff omitido — reconexión` y **ni un solo `grifo aparcado` en toda la sesión**. `_armWakeEar` cortocircuitaba en `_wakeWired`, así que la segunda sesión corrió sin reconocedor y volvió a pagarlo todo — y PARECÍA que iba bien, porque el spotter viejo del servidor sobre el stream de Deepgram cazó el nombre en 1 s. *Degradar a la conducta anterior sin decirlo es la forma de fallo que nadie reporta.* Ahora `_applyEar()` es el único sitio que arranca el oído y corre en cada `start()`, y el oído reporta su propio estado al timeline. **(4) Y el parpadeo que esto habría provocado**: un reconocedor continuo termina y rearranca cada pocos segundos de silencio, y reportarlo literalmente aparcaría y desaparcaría el micrófono a ese ritmo. La ausencia se perdona `_GRACE_MS = 1500` y solo entonces se llama caída; el coste, dicho: un nombre dentro de un hueco de rearranque se puede perder una vez. **17 desarmes más, y CINCO volvieron verdes acusando al test** — tres porque la aserción no podía fallar con esa mutación (el valor que medía ya era vacío por otra vía) y dos porque el test no esperaba lo bastante para que ocurriera lo que nombraba. Encontrado y NO arreglado: `widgets/_user/` tiene ahora un widget llamado **`entonces-vamos-cosa`**, nacido de la frase entera «Entonces, vamos a hacer una cosa, ábreme el widget de vídeo» — un generador que bautiza una tarjeta con el preámbulo de una orden.

- **El oído barato, y la palabra que el modo no exigía (V2-749, 2026-09-22)**: el 🤖 se llama «Modo palabra de activación» y no cambiaba **nada** de lo que cuesta el micrófono. Medido en la sesión `48394dd0` con `stt_provider=deepgram` y `attention_mode=smart`: cada frase de la habitación se publicaba, se transcribía y se **pagaba** antes de que el gate la tirara — «Me llamo Paco.» transcrita tres veces, «Vale, vamos a centrarnos en arreglar» transcrita y descartada. Sus palabras: *«si yo lo tengo todo el día escuchando como si fuera un Alexa, me va a consumir la energía, los créditos, y en realidad no lo vamos a llegar a utilizar ni una sola vez… esa detección del nombre se tiene que hacer a nivel de navegador»*. **(1) EL GRIFO ES UN TERCER EJE.** Con el agente en frío y un modo con palabra, la pista publicada se **aparca**: no sale audio, no se transcribe, no se factura, y quien escucha es un reconocedor del propio navegador (Web Speech API) que no nos cuesta tokens. No es un modelo de keyword entrenado a propósito: **el nombre lo elige él y lo cambia por voz** (V2-747), así que un spotter con la palabra compilada dejaría de funcionar en silencio el día que lo renombre — que es exactamente el fallo de V2-747. El aparcado **nunca escribe el interruptor del micro**: `voice/mic_input.py` lleva desde 2026-09-10 la regla de que el interruptor y el modo de atención «no se escriben el uno en términos del otro», y esto no es ninguno de los dos — es el transporte preguntando si alguien va a leer ese audio. Se cruzan en una sola línea, el transporte, y el interruptor conserva su veto. **(2) ⚠️ APARCAR SOBRE UN OÍDO QUE NO ESTÁ ES SORDERA**, que es peor que cualquier factura y desde fuera parece un producto muerto, no un bug. Por eso aparcar no es un modo sino una **consecuencia**: `wakeword.armed()` solo dice que sí después de que el `onstart` del reconocedor haya disparado, un error fatal lo desarma para toda la sesión, y desarmado el motor se comporta exactamente como antes de que esto existiera. Un navegador sin la API (Firefox, Safari viejo) no aparca nunca. **(3) LAS PALABRAS ANTES DEL NOMBRE SON EL PUNTO.** *«si yo digo "muéstrame el tiempo Johnny"… lo que no puede ser es que el sistema empiece a escuchar a partir de la palabra clave en adelante»*. El reconocedor ya las tiene gratis, así que el spot lleva la frase ENTERA y lo dicho en los segundos previos viaja como `before` → `attention.note_preroll()` → lo reclama el turno de detrás. No es mecanismo nuevo: es `reclaim_ambient_tail` (10 s, de V2-639) alimentado desde una fuente más barata. `note_preroll` existe aparte de `note_ambient` por una razón: un descarte SÍ cuenta una frase sin contestar y una pre-rueda **no**, o una palabra de activación acertada inflaría la propia racha que abre un turno en frío sin ella. **(4) NADA ABRE UN TURNO EN FRÍO SIN LA PALABRA.** En la misma sesión el agente contestó a la tercera «Me llamo Paco.» con `reason: unanswered_repeat`, sin que sonara ninguna — *«hay que ser estrictos. Si hay palabra de activación, el agente debe quedarse quieto»*. **Esto REVIERTE en `smart` la escotilla de V2-743, del día anterior**, y el argumento es el que el propio test de V2-743 ya aplicaba a `wakeword`: «abrirlo por repetición borraría el modo». La escotilla se queda donde se midió que hacía falta — en `always`, el único modo sin palabra con la que volver a entrar. La ventana que abre una palabra no se toca: eso es una conversación que él empezó. **(5) EL TEXTO QUE SE ESCRIBE Y SE BORRA NO SE ESCRIBE.** *«va escribiendo el texto y luego lo borra… ese texto jamás debe aparecer ahí»*. La línea provisional del muro ya no pinta un turno en frío de un modo con palabra; la condición es el ANILLO, no el modo, así que empieza a escribirse en el instante en que su nombre se oye (el spot instantáneo sobre el stream interim ya emitía ese veredicto) y nunca antes. **(6) Y EL AGENTE QUE PREGUNTA TIENE QUE DECIRLO.** Con el grifo aparcado, el cliente ya no puede enterarse solo de que hay ventana abierta: la aprendía del veredicto sobre lo siguiente que OÍA, que necesita audio, que necesita el grifo. Una pregunta del agente («¿Sigo?») abriría una ventana que nadie ve — la versión *deadlock* del fallo de 2026-09-10. El flanco de bajada de una locución **armada** lo anuncia ahora por el mismo canal `ambient` que ya usaba el spot. **(7) La palabra se DICE en voz alta**: el tooltip del 🤖 la nombra con el nombre de HOY, y al pulsarlo aparece durante tres segundos, donde van los subtítulos y en otro color, «Para activar, di la palabra «Johnny»». *Una nota que se queda es mobiliario.* Nodos **4.208** (reglas del oído), **4.209** (los tres cables, que fallan en silencio) y **8.15** (el gate) · **20 desarmes, todos rojos** · de paso, `tests/watchdog.py --impacted` le pasaba a pytest los `test_*.mjs` cambiados, que no puede recoger: un rojo sin significado en cada tanda que añadiera un contrato de navegador.

- **Lo que el interruptor no alcanza, y el número que no se podía decir (V2-747, 2026-09-21)**: cinco sesiones después de V2-745 (`16a39050`, `eb1decb3`, `4648cbb8`, `981dd54c` —729 eventos— y `b7399910`), con el encargo de siempre: *«todos te los he puesto en el chat… lee la conversación, identifica los fallos, compáralos con la observabilidad»*. Seis fallos, todos medidos en `zaelar.db`. ⭐ **El número que pidió no funcionaba, un día después de construirlo.** «Modifica la tarea número tres» sobre tres tareas numeradas que estaba leyendo → `❓ agenda:update_task:la tarea 3 de la lista Obra` con lista de candidatos **VACÍA** y «No tengo claro a cuál te refieres». Tres causas independientes: (a) `positional:false` de la agenda —correcto para el calendario, que no numera nada (V2-643)— **silenciaba también la mitad de TAREAS, que numera todo**; una bandera cargando con dos decisiones, esta vez para dos mitades de una tarjeta, así que ahora la declaración de la ACCIÓN gana a la de su widget en ambos sentidos; (b) `ref_index` publicaba solo `taskId`, y `update_task`/`delete_task` declaran `ref:"task"` — para las dos acciones que CAMBIAN una tarea no había ni una fila que mirar, y las listas no se publicaban en absoluto; (c) la posición se contaba **PLANA** sobre una tarjeta con varias listas que reinician en #1, o sea que «la tarea 3» habría tocado la fila equivocada **sin preguntar**. Un widget que numera sus filas publica ahora el número impreso (`no`) y su sección (`group`), y un número que significa dos cosas es una PREGUNTA. ⭐ **Su frase volvía del revés y duplicada**: `🧩 «Porque no he dicho no he dicho la palabra Johnny, Pero no deberías escucharme, ¿no?»` — y esa cadena llegó al prompt, a Jev, al procesador de memoria y a su muro (hay una tarea suya titulada «Cambiar no en cualquier momento» nacida de una). Dos causas: la cola pelada por la marca de agua de V2-096 se re-pegaba DELANTE del turno acumulativo que ya la traía (`_grows` solo veía prefijos, y la cola es un SUFIJO de lo que acaba de llegar), así que la mitad ya contestada aterrizaba al final y se contestaba dos veces; y la costura que el STT repitió no se colapsaba. El acumulador recuerda ahora QUÉ consumió (`consumed_head`), que es el compañero que la marca de agua nunca tuvo, y una repetición inmediata de **tres o más** palabras se colapsa — tres y no dos, medido: «dos por dos por dos» pierde un factor a dos. ⭐ **El gate de atención NO falló, falló el renombrado.** Se quejó de que «el modo de activación está activado y el micrófono parece abierto al cien por cien»; los veredictos dicen 2 ambientes, **UNA** apertura por `unanswered_repeat` (el rescate de V2-743) y 15 `active_window`. Llevaba toda la sesión llamándole «Johnny» —un nombre que pidió y que se vetaba en la memoria en silencio— así que el gate rechazaba correctamente un nombre que no existía. `voice/attention.py` **no se ha tocado**. El renombrado estaba roto por tres sitios a la vez, cada uno suficiente: (1) `memory_agent/ingest` solo acepta un `change` autodeclarado sobre un slot de identidad **cuando el turno habla DEL OPERADOR** —guarda escrita para `operator.location`— y `assistant.name` es el único slot de identidad que **no** habla de él, así que esa prueba no podía pasarse nunca; el registro declara ahora de qué slots es la pregunta (`about_operator`), y la guarda de INYECCIÓN sigue cubriéndolos todos; (2) el catálogo no declaraba la capacidad —`identity_actions` la lleva desde que existe el slot `assistant.name` y la descripción de `set_style_directive` la cubría «en espíritu»—, así que el modelo contestó «no puedo cambiarme el nombre» y luego prometió sin disparar nada; ahora la nombra y **el catálogo acaba 1 char más pequeño que antes**; (3) el patrón era el imperativo (`cámbiate`) y él dijo «quiero que **te cambies** el nombre a Johnny». Arreglar esto arregla la queja del gate: `attention.wakewords()` se extiende sola y aditivamente. ⭐ **Los subtítulos no estaban rotos**: `Orb.js` los apaga con el chat abierto, por un reporte SUYO del 2026-07-23, y él tenía el chat abierto toda la sesión (a +170 s los apagó y encendió buscándolos). La reparación es lo que pidió a continuación y era el punto abierto de V2-745: **el muro escribe la línea MIENTRAS la voz la dice** —*«solo ir mostrando las palabras a medida que las vas diciendo, y si yo te corto, te paras en ese momento y ya no imprimes más»*— leyendo `voicedLine` del mismo canal sincronizado con el audio que ya usa el teleprompter del orbe. **La ventana de gracia es la mitad que impide que sea una regresión**: sin canal de subtítulos una línea sin transmitir quedaría invisible hasta la respuesta siguiente, así que a los 1,2 s sin un solo segmento el muro la enseña entera, como antes — la misma doctrina que el guarda de borrado de V2-745, el silencio de un canal nunca es prueba sobre la voz. De sus dos opciones visuales tomé el REALCE y no el desvaído: «más pálido» significaba *provisional*, y después de este cambio ya no hay nada provisional en pantalla. ⭐ **Parar no era hibernar, era ejecutar.** Tras `run stop` a las 20:13:20: el pulso del cluster siguió disparando un turno de cerebro entero a las 20:14:15, 20:15:55, 20:17:35, 20:19:15, 20:20:55 y 20:22:35 —`connectors/meshkore/bridge.py` no tenía **ni una** referencia a `runstate`, siendo el único conector que gasta una llamada al modelo por iniciativa propia—; y a las **20:18:20** `nucleo/workers/stall.py` abortó su encargo por «sin respuesta del proveedor en 5 min», porque contaba el silencio de un proceso SIGSTOPeado como silencio del proveedor: **la congelación que debía preservarlo es lo que lo mató**, y después le mandó una notificación sobre una tarea que el motor había matado él mismo. El pulso lee ahora el interruptor antes de decidir nada (solo el trabajo AUTOPROPULSADO: un mensaje entrante de un peer conserva su ruta, porque perder un mensaje no es hibernar) y el reloj del vigilante solo cuenta el tiempo en que el agente estaba EN MARCHA, en rodajas sobre una única lectura (`wait_for` cancela lo que expira, así que un bucle de rodajas construido sobre él perdería lo que el proveedor mandó en la rodaja que venció). **No hace falta el mecanismo de resurrección que él mismo ofreció como plan B**: pausar con garantías ya existía y ya continúa donde estaba; lo que fallaba era un reloj que le sobrevivía. Y el indicador del «1» tiene tres caras: en marcha (acento, pulsando), **PARANDO** (ámbar parpadeando, que es lo que pidió) y RETENIDO (ámbar quieto) con el interruptor apagado — esta última es la que el arreglo de arriba vuelve honesta. **Diecinueve desarmes, todos rojos; dos volvieron VERDES primero y los dos acusaron al TEST** (un fixture que clavaba a mano justo lo que decía medir, y un suelo de eco cuya tabla no tenía ni un caso que se rompiera al bajarlo). Nodos 4.204, 4.205, 8.12, 8.13, 8.14. **Abierto y dicho**: los comentarios en castellano del repo están destrozados por una traducción automática palabra a palabra («the RELOJES of a task of background, definidos a vez»); no se ha tocado —de ese corpus se ocupa una pasada aparte— pero ya no es deuda, es daño.

- **Una fila de su lista no es una compra, y un borrado ya no pregunta (V2-748, 2026-09-21)**: medido en la sesión **48e85cd5**. Pidió dos escrituras de agenda corrientes y el producto se fue a buscar pan por internet. Turno 1: «Y ahora añade una nueva tarea, que sea comprar el pan» → `agenda:add_task` **DESPACHADA** (arbiter «✅ permitiría · payload-in-turn»), la fila escrita… y 0,0 s después «🛑 orden irreversible sin escalar → tarea», un Brain Worker, una tarea durable llamada «Comprar el pan» en la lista que la regla de V2-743 —de dos commits antes— dice que no debe ver trabajo transaccional, y en voz alta: *«Esto mueve dinero y no hago ningún cargo sin tu OK»*. Turno 2: «Borra la tarea. Cuatro de compra del pan» → el mismo gate, la misma frase enlatada, segunda tarea. Y su «Sí» liberó el encargo, que `errand_kind` había clasificado `kind="web"`: **se abrió el NAVEGADOR, titulado «Comprar el pan», «Buscando en la web…»**. ⭐ **DOS causas, y cada una bastaba sola.** (1) `danger.is_dangerous` leyó el **TÍTULO DE LA FILA** como la orden — `comprar`/`compra` están a pelo en `_DANGER_RE` y el título de una tarea es texto arbitrario que él dicta; y como `moves_money` corre la MISMA cadena de restas, el mismo error le dio después el navegador vía `router_guards.money_work_needs_a_browser`. (2) el backstop de la voz **desmintió a la pantalla**: disparó con `data_done` en true, o sea con la mutación ya hecha. **La reparación de (1) es una RESTA, no un patrón nuevo** — la técnica que este módulo lleva cuatro incidentes pagando: `_drop_agenda_items` quita lo que una escritura de agenda NOMBRA antes de buscar ningún verbo, como `_REMINDER_RE` con «recuérdame pagar…» y `_AMOUNT_QUESTION_RE` con «¿cuánto hay que pagar?». Corta en `.!?;` **y en un «y» suelto**, que es toda su seguridad: «pon la lista de la compra **y paga la factura**» conserva su pago; y «compra» se disculpa **solo tras «de»**, así que «confirma la compra» y «finalizar compra» siguen parando (lo cazó el desarme). La de (2) **no depende de que ningún patrón acierte**: una data-op no es el mundo abierto —pasó por `widgets/server_api._dispatch`, el contrato de V2-705 y el snapshot de `store.save`— y el propio `danger.py` ya decía junto a `_DESTROY_OBJECT_RE` que *«the gate is for what has NO funnel»*; simplemente no lo hacía cumplir nadie. ⭐ **Más ancho que el incidente**: con la resta desarmada, TODA frase sobre «la compra» era un encargo de dinero para un navegador — «hazme una lista de la compra», «vacía la lista de la compra», «marca como hecha la tarea dos de la compra». «La lista de la compra» es el ejemplo trabajado de la cabecera de `tasklists.py`: roto desde que esa sección nació. **Y su regla, instalada**: *«la agenda va directa. Cuando digo borrar esto, lo borras sin preguntar (…) otra cosa es que guardes un rastro de lo que había, por si me he equivocado, y te digo restáuralo»*. La pregunta NO venía del widget (`delete_task` ya declaraba `confirm: false`), venía del gate. Las dos mitades viajan juntas porque cualquiera sola es peor producto: la agenda guarda ahora una **papelera acotada** (20 retiradas, `db["trash"]`) con acción `restore` declarada, para tareas, vaciados y listas enteras. Devuelve el **HUECO**, no solo el dato — `items()` numera por orden de almacén y el número es la forma entera en que él se dirige a una tarea. Tres trampas ahí: `_to_trash` leía el hueco DESPUÉS de quitar la fila; `int(v) or 10**6` lee el `_pos` **0** de la primera fila como ausente, así que todo restore aterrizaba abajo; y al deshacer un `delete_list` la lista tiene que volver ANTES que sus filas o `migrate` se las lleva a General. **Sigue preguntando a propósito** lo que él no pidió: `clear_list`, `delete_list`, `clear_all`, `clear_range` — barridos de lista entera; su regla habla de «esto», un ítem. Nodos **2.67** (las 30 acciones declaradas de la tarjeta, una frase natural por cada una, más trece órdenes que tienen que seguir parando; un test comprueba que el corpus cubre cada acción declarada) y **4.206** (el borrado que no pregunta y la papelera que devuelve el hueco). El cableado del backstop se lee del **AST**: la primera versión del test casaba con el COMENTARIO que describe el arreglo. 16 desarmes, todos rojos. **NO afirmado**: no lo ha probado él con la voz; las dos filas basura del incidente siguen en su tablero en `pending` y no las he tocado porque son estado real suyo; y 8 tests de la agenda siguen rojos como deuda anterior —verificada idéntica en un worktree limpio en HEAD— seis por el cambio de `ctx.action("connect", …)` a `ctx.connect(…)` en V2-700 y dos por la clase de consentimiento de `invite`, que necesita decisión suya. `8012b025`.
- **Dos paneles delimitados y una tabla dentro (V2-746, 2026-09-21)**: el operador, acotando él mismo el alcance porque otra sesión estaba tocando el núcleo: *«te voy a pedir una tarea que **afecte solo al widget de la agenda**… que tuviera un poco más **aspecto tipo Excel**… que se **delimiten mejor** las listas de tareas de la izquierda, a la derecha también todo el formato de la lista, los botones… **el botón de nueva lista, pues abajo no está bien porque cuando tengamos 100 listas no se va a ver**… esa barra segunda que pone agenda y tareas, quizás debería ser **una línea de subheader más consistente. Por si hay que crear algo más ahí**… debe seguir pareciendo un widget de nuestro sistema operativo»*. ⭐ **Es la única clase de pasada de diseño que se hace aquí**: encargada, con las quejas nombradas y el rumbo dado — la prohibición de V2-625 es contra el «mejóralo en general» autónomo, no contra esto. Ancla anotada (`f98c5e6a`), snapshot §20, y una escritura por bloque en vez de un barrido largo, porque su motor sirve el ÁRBOL DE TRABAJO y cada edición intermedia es literalmente su pantalla. **Lo entregado, objeción por objeción**: cada mitad es un **panel** con su propio escalón de la escalera de V2-689 (`--hb-sidebar` a la izquierda, `--hb-bg` a la derecha), pelo de borde y barra de cabecera; el **＋ vive en la cabecera de la columna**, hermano del scroller, o sea pegajoso por construcción y no por un `position` que nadie ve que sostiene nada; las filas son **contiguas y regladas** en vez de fichas flotando en aire, con cebra discreta, columnas numéricas **monoespaciadas y de ancho fijo**, fila de etiquetas en la tabla y los controles de cada fila en su propia columna fija (antes seguían al título y bailaban con su longitud); y el selector de sección es una **banda a todo el ancho** cerrada con una regla, con un **hueco a la derecha** que tareas rellena con sus cuentas y el calendario deja vacío — el hueco ES el cambio, porque «por si hay que crear algo más ahí» no debería necesitar inventar una segunda banda. Cero hex nuevos: toda superficie es un escalón y toda tinta un token; el único color añadido **dice algo** (el medidor de una lista terminada pasa a `--hb-ok`, porque una barra de acento llena es lo que también parece una fila seleccionada de reojo). ⭐ **Tres defectos que aparecieron construyéndolo, ninguno cosmético y los tres desde V2-744**: (1) **el grid no colocaba nada** — las celdas de `.agt-list` vivían dentro de DOS divs anidados con estilo en línea, así que `grid-template-columns` no las veía: cada fila dimensionaba su celda de cuenta a sus propios dígitos (doce listas en **seis bordes derechos distintos**) y `.agt-prog` quedaba fuera del grid, donde la regla que lo extiende no podía aplicar nunca; (2) **`.agbody` no es contenedor flex**, así que los paneles se dimensionaban a su contenido — **258 px dentro de una tarjeta de 620**, y una columna que se acaba debajo de su última fila no es una columna, que es buena parte del «no se delimita» que él estaba mirando; (3) **los numerales medían 3,67:1 sobre la fila seleccionada, por debajo de AA** — glifos de acento sobre un tinte de acento, encima de una fila que es ella misma un tinte de acento, justo el emparejamiento que V2-691 llamó lo más ajustado de aquella pantalla; ahora llevan tinta primaria y al seleccionarse cambian al relleno de acento con tinta `--canvas` que esa pasada dejó probado (**6,91:1**, y nada en esta mitad baja de eso). ⚠️ **El nodo 4.170 —el suelo de contraste y de 12 px de TODO el producto— recorre ahora también esta mitad**, anclado en elementos que no existen en ninguna otra pantalla; extenderlo cazó cuatro etiquetas bajo el suelo de tamaño en el momento de escribirlas, tal y como la memoria de V2-691 avisaba. Nodo **4.203**, 16 tests, y todo lo que fija es **ESTRUCTURAL** a propósito —el ＋ con 100 listas, los bordes y superficies distintas, que los paneles llenan la tarjeta, que las filas se tocan, que las columnas comparten borde izquierdo Y ancho, que la banda mide lo que el cuerpo, que el hueco cuenta bien y que el calendario lo deja vacío—: fijar colores, radios y espaciados convertiría el siguiente cambio de diseño en un ejercicio de editar tests. **18 desarmes todos rojos**, y ⚠️ **tres salieron verdes primero y los tres acusaron al TEST**: una aserción de borde DERECHO que `auto` cumple igual que una columna fija (lo que distingue una columna es el borde IZQUIERDO); un fixture cuyas cuentas medían todas lo mismo, así que medía su propia uniformidad; y los numerales, que el nodo 4.170 **no puede ver nunca** porque su auditoría salta el texto de menos de dos caracteres (`own.length < 2`) — un suelo que no puede ver el elemento que suspendería no es un suelo, así que su ratio se mide en el 4.203. ⚠️ **Lo que NO se afirma**: no lo ha visto él; y el 4.170 no se puede correr verde en este árbol ahora mismo **por trabajo en vuelo de otra sesión** en `store.js`/`WidgetRail.js`/`ChatWall.js` (el shell no arranca, `window.zaelar` sale `undefined`) — comprobado revirtiendo MI `widget.js` a HEAD, que falla igual, y verificado 5/5 antes de que esos cambios entraran.
- **El saludo que nadie oyó, y un chat que enseña lo que la voz no dijo (V2-745, 2026-09-21)**: sesión `8fc3e1c9`, un agente recién creado, cuatro minutos y medio desde el botón de arranque hasta que el operador lo paró — *«dicho esto, paramos aquí y vamos a corregir todo esto»*. Cuatro quejas, y la observabilidad nombra la causa de cada una. ⭐ **(1) «Se pasará diez segundos hablando contra una pared».** Desde `session start`: **+0,11 s** `agent:state → live` · **+1,06 s** kickoff · **+4,04 s** respuesta generada («¡Hola! Soy Zaelar…»), con `turno LENTO 2516 ms — ARRANQUE EN FRÍO… la 1ª llamada paga handshake` y TTFT 2,43 s · **+4,07 s** 🎤 **VAD on con `over_agent: false`** —llevaba cuatro segundos en silencio y dijo «¿Qué pasa?»— · **+4,62 s** `TTSMetrics… audio=6,77 s` · **+4,63 s** `bot_speech → idle`, **sin un solo flanco `speaking` antes**. Seis segundos de voz sintetizados, pagados y tirados 30 ms después de existir el texto; sus dos turnos siguientes se juzgaron ambiente y lo primero que oyó fue un relleno **a los 22 s**. Dos arreglos: **un barge-in es cortar algo que ESTÁS OYENDO** —el propio flanco lo decía— así que el saludo nace `allow_interruptions=False` y recupera la interrupción en cuanto suena su primer fotograma; y **el velo de arranque se levanta en ese mismo flanco**, no dos fases antes bajo un comentario que prometía «the greeting lands as the orb appears». *Una fase que AFIRMA estar caliente no está caliente*: «reflejo» lleva desde el día que se escribió declarando un reflejo tibio sobre una primera llamada que siempre ha pagado el handshake. Acotado a 12 s, y toda ruta que no vaya a saludar lo levanta ya. Su regla: *«no deberíamos dar acceso a la gente hasta que eso estuviera totalmente inicializado y operativo… hay que controlar que todos los servicios estén activos»*. ⭐ **(2) y (3) son el mismo hecho por dos lados:** una frase suya llegó en **ONCE** eventos `transcript` y el muro pintaba un globo por segmento —*«lo conviertes en dos frases separadas cuando es el mismo párrafo»*— mientras el subtítulo se reseteaba al fragmento nuevo cada vez que Deepgram cerraba uno —*«las antiguas desaparecen y empiezas a escribir las nuevas»*. **El hold ya tenía la unidad correcta y no la usaba**: todo lo que espera un mismo veredicto ES un turno, porque la puerta juzga la frase acumulada. Se une al soltar, y el subtítulo lee esa misma acumulación; el CANVAS sigue viendo los fragmentos (V2-664 lo afinó contra ellos). ⭐ **(4) «El texto que no has dicho no quiero que exista».** Tres veces: a **+157,1 s** «Me alegra que lo veas mejor…» sintetizó **14,05 s de audio** y `bot_speech` no salió de `idle` —él ya estaba hablando— y la frase entera se quedó en el muro; a +48,7 s y +163,1 s el registro hablado SÍ volvió («...tienes», «Te tomo nota de las dos cosas: el texto que parece borrarse») y **se tiró**, porque la regla escrita en `pushAgentChat` decía que gana la versión larga, *«what the agent intended to say, as it is the useful history»*. Esa decisión deliberada es la que él deroga, y su razón es mejor: **un chat al lado de una voz es la transcripción de esa voz**. Ahora el muro sigue el subtítulo SINCRONIZADO CON EL AUDIO (el `TextSynchronizer` de LiveKit, al ritmo de la reproducción real): se recorta con puntos suspensivos donde la voz paró, y se borra si no llegó a empezar; el emparejamiento es por CONTENIDO, nunca por tiempo, así que un relleno sonando sobre una respuesta cancelada no puede confundirse con ella. **No puede borrar por ausencia de evidencia**, y el guarda es POR LÍNEA: solo se quita cuando el contador de subtítulos se ha MOVIDO desde que se pintó, o sea cuando la voz demostrablemente dijo otra cosa. Un primer intento llevaba además un flag de sesión y **su desarme volvió VERDE** —el contador por línea ya cubría todos sus casos—: dos guardas para una cosa, una no medible, fuera. `agent.py` cruzó su techo de 900 y la decisión se EXTRAJO a `first_air.py` (892 → 864), que es también lo que la hizo testeable sin media pila de LiveKit. Nodos **8.11** y **4.202**, **doce desarmes rojos**. Pagado de paso: `config/settings.py → voice.engine.speech`, la deuda que dejó mi propio V2-733 y que tenía el trinquete de direcciones rojo en main. **Abierto y dicho**: el handshake frío sigue costando lo que cuesta —ahora lo tapa el velo, no su silencio— y su IDEAL, ir transcribiendo en el chat lo que va diciendo la voz, queda a un paso: el dato ya llega donde el muro lo ve, falta la decisión de pintado, que se cambia contra la velocidad de V2-116 que él elogió en esta misma sesión.

- **La agenda alberga TAREAS en listas numeradas, y el trabajo del agente es un PROCESO (V2-744, 2026-09-21)**: dos mitades de una regla que el operador enunció antes de pedir ninguna de las dos — *«a las tareas que yo hago las llamo **procesos** (jobs en inglés) y las separo de las **tareas personales del operador**, que van en su agenda»* — y el encargo: *«arriba del todo un selector que separe lo que es agenda de tareas… una lista general y que el usuario pueda generar una lista para varias cosas… podemos generar una lista de la compra y eso tendrá un identificador y ese identificador lo podré compartir en el futuro con otro agente a través de la red de MeshKore… asegúrate de que todo está bastante numerado para que cuando yo vea una lista le diga: ábreme la lista número 3, coge el ítem número 2 y modifícalo por esto»*. ⭐ **Lo medido primero, que es lo que dio forma a todo lo demás:** la agenda YA tenía un array `tasks` —el del planificador, con `estimateMinutes`/`priority`/`projectId`— así que esto no era añadir una sección, era no añadir una segunda verdad. **Tres decisiones.** (1) **UN array, no dos**: una tarea de lista y una del planificador son las dos «algo que él tiene que hacer», así que comparten `db["tasks"]` y llevan `listId`; un segundo array es el defecto de los dos escritores de un mismo hecho que este widget ya tiene grabado en la cabecera de `system_tasks.py` («THE AGENDA READS, IT DOES NOT DUPLICATE»). Migración perezosa v1→v2 y también defensiva en cada lectura: una tarea escrita por un build viejo no tiene `listId` y en una sección construida sobre listas habría sido invisible — pérdida de datos con cara de pantalla en blanco. (2) **El planificador solo coloca lo que dice cuánto dura**: leía `int(t.get("estimateMinutes", 30))`, así que **cualquier cosa sin duración se agendaba como media hora** — con una lista de la compra en el mismo array, «Pan» y «Leche» le habrían ocupado las 9:00 y las 9:30. Es la regla de V2-652 («un dato que falta es un dato, no un hueco para un valor por defecto») aplicada al único campo sin el cual el planificador no puede trabajar. (3) **El NÚMERO es la posición en pantalla y nada más**: pidió numeración para poder decirla, y un número guardado se separaría de lo que él está leyendo en cuanto se borre algo; se deriva en cada lectura, y el digest que ve el cerebro lo construye la MISMA función que la pantalla — `index.py` existe porque dos vistas de un mismo cromo discreparon sobre qué era «la siguiente». El id de la lista es un slug legible (`tl_la_compra`) y está A LA VISTA, porque es lo que él va a pasarle a otro agente por el cluster. ⭐ **El renombrado, y la mitad que un cambio de rótulo se habría saltado:** el id de la pestaña se mudó CON el rótulo. `panel_canon` devuelve una cadena, el evento SSE la transporta y `store.setChatTab` la recibe: mientras esa puerta contestaba a `tareas`, la orden «ábreme las tareas» —enrutada correctamente por todas las capas— abría la lista de trabajo del agente. `tareas` se sigue absorbiendo (una fila de su action map grabada antes de hoy significaba ese panel); lo que ya no pasa es que nada lo OFREZCA con ese nombre. «Tarea» no está prohibida: fue reasignada, y el trinquete nombra los tres sitios donde sigue siendo correcta. **Presupuestos pagados, no subidos:** `data.py` estaba en 899 de su techo de 900, así que el resolutor de fechas habladas se EXTRAJO a `when.py` (byte por byte, todos los nombres reexportados) → 820; el catálogo de tools salió 7 caracteres MÁS PEQUEÑO de lo que entró (23 579 → 23 572); y `whenToUse` quedó en 267 de los 300 de `brief._PURPOSE_CAP` — el primer borrador iba por 560 y se cortaba a media frase, que es exactamente el fallo de V2-547. Nodos **4.200 · 4.201 · 8.10** (61 casos; el 4.201 RENDERIZA en Chromium). **Veinte desarmes, todos rojos**, y uno volvió VERDE acusando al test: `test_the_tool_the_model_picks_tells_the_two_apart` leía `whenToUse + usage` como una sola cadena, así que cualquiera de las dos mitades podía perder la frontera mientras la otra la tapaba. Separadas, rojo. Verificado en vivo sobre `3.33+fa1cc3b4`: la ronda entera por la ruta HTTP real, y la limpieza dejó su almacén como estaba (General vacía, 273 citas intactas). ⚠️ Esta entrada llegó tarde: el commit `3ac4cf3a` dice traerla y NO la trae — un `git checkout` mío para deshacer un intento fallido de pasada de archivo se la llevó por delante, y el mensaje quedó afirmando algo que no era cierto.

- **Un parte no se da antes del trabajo — y una frase que nadie contesta no es ruido de sala (V2-743, 2026-09-21)**: el operador, tras una ronda corta sobre la agenda que *«ha funcionado bastante bien»*, con dos quejas y una confirmación. La que él llamó importante: *«le he dicho que hiciera una tarea de borrado. El agente personal ha contestado que ya estaba hecho […] **lo más importante es que el arnés que decide si esa tarea ha terminado tiene que comprobar todo lo que incluye**: tenía que revisar tanto la memoria como el widget de la pantalla y no haber dicho que está hecho hasta que estuviera todo terminado. Incluso previamente le tenía que avisar: me pongo a hacerlo ahora mismo y te aviso»*. Sesión `bcd4aba1`, `clear_range` sobre 47 citas, cuatro eventos: **2948,168** confirmación · **2948,169** despacho · **2949,026** «Hecho.» (**+0,86 s**) · **2956,175** `action_failed · timed out after 8s` (**+8,0 s**). ⭐ **Cuatro defectos, y ninguno es el que parece la frase.** (1) La puerta de confirmación contestaba a su «sí» con `data_ack`, que es «Hecho.»: nunca fue un parte, era un acuse del *sí* con las palabras de un parte. Ahora contesta `work_started` («me pongo a ello y te aviso»), en los dos idiomas. (2) **La operación no falló**: `server_api` corre cada hook de widget en un pool acotado a 8 s y **un hilo no se puede matar** —lo dice su propio comentario—, así que el hook siguió y terminó el borrado; él vio desaparecer las filas unos diez segundos después. Un timeout de pool **no es un veredicto, es la ausencia de uno**, y `nucleo/flash/op_receipt.py` lo atestigua ahora contra el `view_data()` del propio widget, con firma tomada ANTES y comparada después: **una sola lectura cubre las dos mitades que él nombró**, porque la vista es la pantalla y sale del almacén. (3) **Nadie corrigió la afirmación**: `report_failure` abría con `res.get("ok") is not False` y el timeout trae `{"error": …}` sin `ok` ninguno, así que volvía en su primera línea — mientras `server_api.brain_action` leía el MISMO resultado como `error or ok is False` desde V2-390. Dos lectores de una forma, discrepando, y ganó el callado: el fallo estaba en la línea de tiempo y nunca en la habitación. (4) ⭐ **Y la queja sobre todo esto era inaudible**: seis frases suyas se juzgaron `ambient`, todas él, solo, hablándole de frente, todas ya con `framed: true` — «¿Por qué no transcribes el audio que estoy dictando?», «¿Hola?». `note_ambient` alimenta una racha `unanswered` desde fix01 y la escapatoria que la lee estaba dentro de `evaluate_content`, **tras su guarda de `always`**, y `evaluate_content` abre con `if m != "always": return evaluate(text)` — o sea que en `smart`, **que es su modo**, la racha se escribía en cada descarte y no la leía nadie: instrumentación viva cableada a nada, la misma forma que el hallazgo de V2-741. La escapatoria vive ahora en `evaluate()`, donde la leen los dos modos; `wakeword` y `ptt` salen antes y no se tocan. **La ventana de 5 s es regla suya (2026-09-10) y no se ensancha**: lo que cambia es que agotarla tres veces seguidas deja de ser un veredicto. ⚠️ **Y el muro del chat, medido en esa sesión**: desde su primer flanco de VAD hasta que la línea aparece, **mediana 3,45 s · p90 10,1 s · peor 19,0 s** — cada turno hablado retenido hasta el veredicto (V2-647), el veredicto esperando al endpointer, y el endpointer con el techo que ESTE repo había subido a 3,0 s el día antes (V2-742), que alargó la espera en vez de acortarla. Ahora el muro lleva **una línea provisional** alimentada por el interim: marcada como provisional (hueca, con borde discontinuo — no solo más tenue: el muro ya atenúa lo viejo, y dos significados en una superficie es como pierde la señal nueva), nunca persistida, **sustituida** por la burbuja real al soltarse el turno y **retirada** si el veredicto lo descarta — así V2-647 queda intacto y la habitación sigue sin dejar rastro. ⭐ La flecha de 325 líneas de `es.onmessage` pasó a ser `routeEvent` exportada; el enrutado no cambió, **solo se volvió alcanzable**, porque su propio desarme demostró que un test que conduce una costura POR DEBAJO del router prueba el mapeo y nunca el cableado. ⭐ **Y lo que él confirmó como correcto y queda escrito**: borrar una cita, añadir una o mandar un mensaje son **transaccionales y NO entran en la lista de procesos** que ve el usuario; esa lista es para encargos que llevan tiempo y que querrá consultar. No hay cambio de código — se anota para que la próxima tanda no lo «mejore» hasta convertirlo en un registro de tareas. Nodos **3.74**, **3.75** y **4.199**; 40 tests y **25 desarmes todos rojos**. ⚠️ **Cuatro desarmes salieron verdes primero y los cuatro acusaron al TEST**: una coincidencia de prosa alrededor de una etiqueta en vez del keyword de la llamada; `window_s()` asertado sin sus dos constantes (subir solo el TECHO deja `window_s()` leyendo 5,0); `textContent` sobre un nodo oculto con `display:none` (V2-690 otra vez: un estilo computado no prueba que algo se PINTE); y el test del cartel llamando a `captionPartial` directamente, que sobrevivía al borrado de la rama que lo llama. ⚠️ **Lo que NO se afirma**: nada de esto está verificado en vivo — el camino del recibo («dice que sí, oye «me pongo a ello», y oye el desenlace cuando aterriza») necesita una ronda real con un modelo real, y el cartel necesita parciales reales de Deepgram. Las dos son una sesión.
- **La tarjeta tenía cinco caras y la voz no llegaba a ninguna (V2-742, 2026-09-21)**: el operador, probando la sesión recién arrancada y separando él mismo lo temporal de lo estructural: *«lo que no desaparecerá es la incompetencia a la hora de manejar el widget de vídeo… una vez hemos llegado al vídeo, ya ha sido **incapaz de volver al catálogo, de volver al dashboard**, para poder seleccionar otro, que es una de las cosas más básicas que quiero hacer»*. Sesión `891f2091`, 1 003 eventos, todos con `ver=3.33+c33c74ab` — el build de V2-741. Pidió volver **cuatro veces** con cuatro formulaciones distintas, y lo que se disparó fue: `clear_search` (cuya PROPIA descripción dice «quita la banda de resultados de búsqueda del inicio» — **borra justo la lista a la que quería volver**), `clear_search` otra vez, `show_history`, y a la cuarta **nada**, mientras la respuesta decía «Te llevo al inicio de la lista». ⭐ **Y no enrutó mal**: `grep` sobre los doce widgets embarcados — `youtube` es el ÚNICO con conmutador de pestañas (`selectTab`, la superficie de navegación única desde V2-632), tiene **cinco caras** (`inicio`, `player`, `cola`, `listas`, `subs`) y de sus **48 acciones declaradas ninguna navega entre ellas**; la más parecida hace lo contrario. ⭐ **Este es exactamente el límite que V2-741 no cruza**: el motor ya lee el veredicto en cada bifurcación, pero el veredicto enumera acciones DECLARADAS — **una capacidad sin declarar no es enrutable por bueno que sea el enrutado**, y el modelo elegirá lo más parecido que exista, que aquí destruía el objetivo. **Lo entregado**: `youtube:show_tab`, con payload enumerado (`inicio | player | cola | listas | subs`) y `view: true`, cuyo `desc` lleva SUS palabras («vuelve al catálogo», «página de inicio») porque el `desc` es lo que lee el clasificador, y dice explícitamente que `clear_search` es lo CONTRARIO de volver. Validado contra las caras propias del widget, que **rechaza una desconocida NOMBRANDO las reales** (un `ok` silencioso sobre una pestaña que nadie tiene es como empieza «dice que lo hace y no lo hace»), y guardado como **secuencia y no bandera**: pidió cuatro veces seguidas, y una bandera que la tarjeta ya consumió no puede volver a disparar. ⚠️ **Dos ubicaciones del consumo eran falsas y las dos están escritas en el código**: dentro de la rama de reconstrucción solo corre cuando cambia el VÍDEO —y el caso entero es que el vídeo NO cambia, está viéndolo y quiere la lista— así que tres tests se pusieron rojos; y antes del salto automático al reproductor, el salto deshacía en silencio cada orden que diera, que es un no-op que además reporta éxito. Va al FINAL de `render`, y llama a `selectTab`, el mismo raíl que mueve su clic. ⭐ **Y construir esto encontró un defecto en el peldaño de V2-741**: `fillable_key` habría metido «vuelve al catálogo de vídeos» dentro de `tab`, porque `tab` es la única clave no marcada «(opcional)» — ahora una clave cuya descripción ENUMERA alternativas (`a | b | c`, `'x' o 'y'`) no es rellenable con una frase, porque una frase no es uno de sus valores. Nodo **4.198**, 16 tests, **12 desarmes todos rojos**; todo lo de cliente RENDERIZA el widget real. ⚠️ **Medido en la misma sesión y NO arreglado — la fragmentación del STT**: 54 fragmentos hablados, mediana de **3 palabras**, **46 % de dos o menos**; hueco mediano entre fragmentos **1,59 s** contra un `HOLD_BASE` de **1,2 s** (`HOLD_MAX` 2,2, crecimiento 0,15/s), o sea que sus pausas caen JUSTO por encima del umbral y el turno se cierra a media frase — **19 de 44 huecos sí estaban por debajo y esos sí se fundieron**. Él lo atribuye a tener la máquina saturada con un modelo local de 27B y lo da por temporal, pero pidió «una cierta tolerancia de milisegundos». Las constantes son de entorno (`TURN_HOLD_BASE`/`TURN_HOLD_MAX`) y el cambio es una línea; se paga en latencia de CADA orden corta, y un número no se elige con una sesión. Pide su propia medición. Y sin diagnosticar: `🔁 break-loop: nudge anti-repetición` disparó **8 veces** y `✂️ turno descartado — sin respuesta` **7**, en seis minutos.
- **El tercer peldaño: el motor nombró la acción barata y gastó cinco minutos en la cara (V2-741, 2026-09-21)**: el operador, tras probar él mismo la ejecución local: *«nunca nos vayamos a lanzar un brain worker que tarde 5 minutos en hacer una tarea que una búsqueda de vídeos directa utilizando el módulo de búsqueda pues soluciona rápidamente. Y eso puede pasar para la música, para buscar documentos en internet, para encontrar datos, para buscar datos en la memoria»*, y antes de eso su intuición exacta: *«a veces ha fallado la primera petición pero la segunda ha funcionado bien y eso me preocupa porque en realidad **el sistema sabía cómo hacer esas cosas**»*. Tenía razón literalmente. Sesión `092569ab`, **1 148 eventos todos con `ver=3.33+3e44994b`** — el build actual, así que aquí no había desfase que explicara nada (al revés que V2-738). La cadena del Apolo 11, eslabón a eslabón: **146,8 s** el brief contestó `screen_action = youtube:search` a **0,97**; **149,3 s** el modelo llamó a `play_video(query="Apollo 11 documentales")`, también correcto; **149,3 s** `video_license` se lo comió como context-bleed porque su tabla de verbos conjugados no tiene «preparar» ni «podrías», y la frase era «¿me podrías preparar un catálogo de vídeos sobre el Apollo once?»; sin tool, la respuesta fue una promesa vacía; **193,2 s** el auditor de fricción diagnosticó «data-op fantasma» y **reparó con un worker `claude_code` genérico**; **387,8 s** ese worker alcanzó su primer `youtube:search` — **195 segundos**. ⭐ **El diagnóstico de clase**: el motor le hace a Jev las preguntas correctas y luego deja que una regex o un segundo modelo le lleven la contraria — tres decisores en el mismo circuito que no se hablan (el brief, enumerado y calibrado y **pagado cada turno**; los guardas de gramática; y Susurro, con permiso para lanzar workers) sobre una escalera de **solo dos peldaños**. Y lo más caro: `friction.py` **ya había resuelto** que el widget era `youtube` y que declara acciones, y eligió igualmente el instrumento más caro que tenía. **Lo entregado, cinco cambios de la misma clase —leer el veredicto donde se decide—**: (1) `nucleo/flash/direct_action.py`, **el peldaño que faltaba** — qué acción declarada sirve a esta comisión y cómo se rellena su payload, con el `payload` del manifiesto decidiendo qué clave es rellenable (**exactamente una** no marcada «(opcional)», y nunca la que nombra una fila que ya existe: dos requeridas es un `ASK_FACT`, no una llamada); se intenta ANTES del gate de escalada y solo donde la alternativa cuesta minutos. (2) `canvas_license.verdict_grants` — **una tabla de verbos no puede desmentir al veredicto**; la tabla no se puede completar y cada intento de completarla está en sus propios comentarios (el infinitivo de `poner`, los stems ingleses, `sacar` para salir de pantalla completa), cada uno una orden real comida en una sesión real. **Solo CONCEDE**: puede añadir una llamada permitida y nunca quitar una. (3) `escalation_guard.covered_by_live_work` — `anything_running` responde «¿está ocupado el motor?» y la pregunta que hace falta es «¿lo que acaba de pedir ya se está haciendo?», que tiene dueño desde V2-507 (el dedup del dispatch, con el `kind` neutro a propósito: `code`/`generic` deduplican por widget objetivo y dos encargos distintos sobre la misma tarjeta siguen siendo dos). Sus **diez restaurantes se anularon** como `handled_inline / worker-running` porque corría el worker del Apolo: el encargo no falló, **no llegó a nacer**. (4) `escalation_guard.is_a_fragment` — un «Sí.» a nuestro propio ofrecimiento se anulaba como «fragmento, no un encargo», y **una confirmación es corta por naturaleza** porque el verbo estaba en NUESTRA frase; el brief ya decía `request_type=answer` a **1,00**. Hacen falta las dos mitades (el veredicto y que hubiera pregunta que contestar), el mismo emparejamiento de `offer_of_media`. (5) `memory/retriever.py` — la línea de recall degradado imprimía «active embedding space (cloud:text-embedding-3-small:768) does not match the indexed one (cloud:text-embedding-3-small:768)», **la misma cadena dos veces**, mientras la causa real era que la cuenta de OpenAI no tenía saldo (17 relevos en 6 minutos); ahora las compara y nombra la causa que encontró, porque un diagnóstico que manda al fichero equivocado gasta la confianza del lector. ⭐ **Y la respuesta a su pregunta**: no fue la segunda petición. La inyección de su queja llegó al worker a 386,5 s y el worker la **leyó** a 389,0 s, *después* de la búsqueda de 387,8 s — y el motor le explicó la diferencia con una frase falsa («he tirado de la búsqueda rápida de YouTube»): el mismo worker lento. Nodo **3.73**, 32 tests, **15 desarmes todos rojos**. ⚠️ **Dos tests existentes se pusieron rojos y uno de ellos CODIFICABA el defecto**: `test_a_live_worker_counts_as_the_work_being_under_way` asertaba que cualquier worker vivo anulaba cualquier comisión, y llevaba verde todo el tiempo que eso costó encargos — reescrito con el motivo dentro. ⭐ **El trinquete de arquitectura se pagó extrayendo**, no subiendo techos: el cuerpo del peldaño vive en `direct_action.take_rung` y el del guarda de fragmentos en `escalation_guard.drop_if_fragment`, así que el provider acaba **igual que en HEAD (3 143)** y el probe **igual (1 166)** con cinco cambios dentro. ⚠️ **Lo que NO se afirma**: no está probado en vivo — seis aserciones son de CABLEADO y están desarmadas, pero «el peldaño elige bien con un modelo de verdad» es una medición sin hacer; **el canal de texto sigue sin disparar brief**, así que allí E1/E2/E4 leen como el camino de hoy y el parámetro está cableado solo para que los dos canales no diverjan el día que lo tenga; y el relleno de palabras del peldaño está **acotado, no es listo**: sin tool que reutilizar mete la frase del operador en la única clave declarada y se niega pasadas `MAX_QUERY_WORDS`, porque un encargo largo SÍ es trabajo de worker. ⚠️ **Medido y NO tocado**: **cinco briefs duplicados** (29 llamadas para 24 frases, 25,1 s, máx 1 793 ms) por re-admisión de fragmentos; **el acumulador baraja** («En el centro. Dame *Mientras tanto*, mira, estoy de viaje en Sevilla. En el centro. Dame diez restaurantes…» — un fragmento antepuesto y repetido, y el modelo contestó a eso); **14 turnos cancelados por solape** y 3 frases tiradas por el hueco, una de ellas una especificación de 33 segundos que hubo que pedirle que repitiera. Los tres viven en el bucle de turno del fichero-dios y son otra tanda. Y **no existe widget de mapa**, ni mapa en `search`: lo que pidió no está roto, no está construido.
- **De QUIÉN era la orden: el veredicto de pantalla estaba pagado y se tiraba (V2-740, 2026-09-21)**: el operador, corrigiendo el encuadre de V2-739 que llamaba «defecto» a las acciones homónimas: *«nuestro sistema no tiene problemas. Si tengo dos widgets que tienen las mismas tools con los mismos nombres, el motor va a dar un 50% […] y cuando eso pase, el flashbrain tendrá que decir: tienes dos reproductores abiertos y me tienes que especificar cuál. Si por contexto sabe identificarlo, perfecto […] probablemente el modelo de evaluación de la decisión será capaz de decirnos a qué cree que se refiere el usuario y deberíamos utilizarlo en ese punto del flujo»*. **Tenía razón y el encuadre era mío**: que `youtube` y `musica` compartan nueve nombres de acción no es un defecto, compartir vocabulario es lo que los hace ambos reproductores. ⭐ **Y lo que faltaba ya estaba construido y sin leer**: el brief pregunta `screen_action` desde V2-726 A4 —clave `<tarjeta>:<acción>`, **68 opciones** con los dos abiertos, cada candidato etiquetado con la CARA VIVA de su tarjeta («youtube — Apolo 11 · pausado»)— y su único lector era `repair_action_from_brief`, que según su propio docstring dispara *«ONLY on the invented-action path»*. Con una acción DECLARADA nadie comprobaba la tarjeta que eligió el modelo: **el veredicto se pagaba cada turno y se tiraba**. `frontend.which_card` lo lee ahora en el punto de la decisión, con tres salidas y **ninguna cuesta nada en el camino común**: una sola tarjeta capaz → no lee el brief siquiera (hay test de eso); ambigua y el brief sabe → REUBICA; ambigua y no sabe → PREGUNTA, que es `consent.ASK_WHICH`, la segunda de las cuatro preguntas de V2-712 y no una nueva. ⚠️ **Nunca cambia la acción, solo la tarjeta**: dos decisiones detrás de un veredicto harían el caso «seguro y equivocado» el doble de caro. ⚠️ **Y no abre una llamada bloqueante**: el canal de texto no dispara brief, y la reparación obvia —preguntar síncronamente, «el probe no tiene bucle de eventos que congelar»— añade un TERCER `choose_sync`; el nodo 3.61 los congela en dos y dice qué hacer en su lugar, así que un canal sin brief PREGUNTA, que no es una respuesta degradada sino la conducta pedida. ⭐ **Dos extracciones pagaron el crecimiento que cazó el trinquete de arquitectura**, y una era deuda vieja: `card_decision` (la decisión Y su consecuencia, para que cada canal gaste cuatro líneas) y `absent_widget_misroute` — el guarda del pronombre suelto sobre un widget ausente, que vivía **COPIADO** en la voz y en el probe con el comentario del probe admitiéndolo por escrito, y cuya trampa de las acciones de CREAR hubo que arreglar **dos veces por separado**. **El provider acaba en 3 143 (era 3 153) y el probe en 1 166 (era 1 172)**. Y una tercera cosa que el trinquete hizo bien: `langs.py` estaba en 899 de 900 y mi frase nueva lo cruzaba — la salida no fue partirlo ni subir el techo, sino ver que **una segunda frase para la misma pregunta era preciosismo**: `ask_which_item` ya ES la frase de `ASK_WHICH`. ⚠️ **Lo que NO se afirma**: no se ha probado en vivo — hay tres aserciones de CABLEADO desarmadas (la voz decide ANTES de despachar, el probe toma la misma decisión por la misma función, nadie reintrodujo el `choose_sync`), pero «acierta la tarjeta» con un modelo de verdad es una medición y no se ha hecho; y **el probe seguirá preguntando siempre** donde la voz resolverá, así que los escenarios de V2-739 medirán esa rama hasta que el operador decida si el canal de texto paga su propio brief. ⚠️ **Hallazgo abierto**: `test_task_recall_finds_the_errand_he_means.py` es FLAKY EN HEAD —2-3 rojos de 14 que cambian de nombre entre corridas, también aislado y con `PYTHONHASHSEED` fijo, así que es TIEMPO, no orden— verificado que no es de esta tanda. Nodo **3.72**.
- **Una vara de medir también se pudre, y la otra concurrencia es la que el operador VE (V2-739, 2026-09-21)**: el operador, sobre el testing de widgets: *«necesitamos un sistema de testing que […] utilice palabras precisas, palabras imprecisas, incluso un use case puede tener abiertos tres widgets e intentar manejar los tres a la vez […] no un test que diga «abre el widget de vídeo, carga el vídeo llamado». Eso está claro que va a funcionar. Necesito lo otro: dinámico, variable, humano»*. Medido primero: de **211 acciones declaradas** por los doce widgets embarcados, **155 (73 %) las EJECUTA algún test** — `navegador` 2 de 12, `agenda` 12 de 22, vídeo 42 de 48, y las seis que faltaban eran justo el transporte (`mute`, `unmute`, `volume_up`, `volume_down`, `restart`). Pero el hueco de verdad no era la cobertura: el único caso de uso de vídeo en verde es **una frase y un seguimiento**. ⚠️ **Y su expectativa llevaba 26 días mintiendo**: decía al juez que el reproductor «has NO playlist actions», escrita el 2026-08-26 — **un día antes** de que `8861c929` entregara `sort_list`/`filter_list`/`clear_list`. El marcador enseñaba ✅ y un 5 mientras instruía a puntuar una cola correcta como fuera de alcance, y **nada podía estar rojo: un juez no puede notar que la vara que le dan tiene la medida mal**. Barrido el catálogo entero (167 casos) buscando la misma forma: solo ese uno — los otros cinco declaran ausencias que siguen siendo ciertas y nombran un CONECTOR o un estado, nunca una acción declarada. **Lo construido, sobre el arnés que ya existía** (su instrucción: «creo que ya tenemos un sistema así, simplemente se trata de utilizarlo»): `verify.open_widgets_by_turn` — **la OTRA concurrencia**. `task_registry.max_concurrent` cuenta encargos de fondo y no dice nada de cuántas TARJETAS tenía delante cuando habló, que es lo que decide a cuál se refería; con eso publicado y renderizado para el juez, más un campo `concurrent_widgets` y su rubric de atribución, dos escenarios: tres tarjetas abiertas con órdenes que no nombran ninguna, y la cola del reproductor manejada por referencia imprecisa. ⭐ **El dato que convierte eso en una pregunta real y no en estilo**: `youtube` y `musica` declaran **NUEVE acciones con el MISMO nombre** (play, pause, next, previous, volume_up/down, set_volume, play_local, ended), así que con los dos abiertos «baja el volumen» es **indecidible al nivel del nombre de la acción** — y la conducta correcta es PREGUNTAR: acertar en silencio es suerte, no acierto, y así se puntúa. ⚠️ **`concurrent_widgets` se deriva a posteriori y eso no es un atajo**: `show`/`close` son transiciones de estado, así que el conjunto abierto se reconstruye entero del stream; una tarea no tiene ese par y por eso sí hay que muestrearla viva. Escrito en el campo para que nadie lo «arregle» añadiendo un sondeo. Nodos **10.129** y **10.130** (este último guarda también el encabezado del catálogo, que decía «NINE promoted» cuando eran 20 — la misma clase, un nivel más arriba). **Lo que NO se afirma**: los dos escenarios **no se han corrido** — gastan modelo y juez por ronda y sus primeras notas serían la línea base; y esto mide ENRUTAMIENTO, no cobertura de acciones, que sigue en el 73 % y merece su propio trinquete.
- **Un panel que pinta su propio código fuente — y una sesión que medía un motor de hace catorce commits (V2-738, 2026-09-21)**: el operador, tras una sesión local: *«no se transcribe el texto en el chat, parece que hay algún error de entendimiento, no se abren los widgets, el sistema ahora mismo está muy roto»*. Tres quejas, y **el hallazgo que más vale es que dos de las tres medían código que no estaba corriendo**. Los 312 eventos de esa sesión están estampados `ver: 3.33+eacc5381`; el disco estaba en `89bc8eca`, **catorce commits después**. Un proceso de Python carga sus módulos una vez; el **frontend se sirve del disco en cada petición** (`RevalidatingStatics`, `cache-control: no-cache`), así que su navegador tenía el JavaScript de HOY hablando con un motor de hacía cuatro horas. Ese desfase no es un detalle: *«y tú hablas en latino»* —una de sus quejas de esa misma sesión— es literalmente el asunto de **V2-734**, uno de los commits que el proceso vivo no tenía. Y el motor, turno a turno, estaba limpio: los ocho turnos emitieron su `transcript` **y** su veredicto `ambient`, **los ocho `directed: true`**; `widget/show youtube` salió tres veces y el auditor susurro registró `widget_acted=True, shown_ids=['youtube']`. **El defecto que SÍ era real** está en el cliente y es de clase: `dom.js` acepta una función como hijo y la trata como enlace reactivo, pero **solo como hijo DIRECTO de `h()`**; devuelta dentro de un ARRAY llega a `toNode`, cuya última línea era `createTextNode(String(v))`. `ChatWall.js` (V2-728) devuelve exactamente eso, así que la pestaña «Tareas» **pintaba el código fuente de la flecha** a lo ancho del panel. No lanzaba nada, no registraba nada — y **el nodo 4.193 renderiza ese panel, entra en las dos sub-pestañas donde ocurre, recoge `pageerror` y pasaba**, porque asertaba sobre las cuatro listas y nunca sobre el formulario que la flecha debía construir: *una aserción apuntada a la costura equivocada no puede fallar*, la misma clase que la ruta muerta con la que empezó V2-726. Arreglado envolviendo el condicional en su propio `h("div")` —la forma que `dom.js` ya enlaza— y, sobre todo, **`toNode` ahora RECHAZA una función en voz alta** (`console.error`, nada pintado) en vez de convertirla: deliberadamente NO se vuelve reactiva ahí, porque un elemento de array no tiene ancla que posea una región anidada ni desechador que la retire en la siguiente pasada, y «hazla reactiva» cambiaría un fallo visible por efectos que se fugan. ⚠️ **Lo que NO se afirma**: las otras dos quejas NO están reproducidas. La cadena del cliente en disco pinta bien un turno dirigido — eso es lo que mide el **nodo 4.197 nuevo**, que conduce la página REAL con sus cuatro frases reales y lee el DOM, y que está desarmado (quitando el `pushChat` del `deliver` de `sse.js` caen tres de sus cinco). `attention_hold.js` estaba bien cubierto, pero allí «entregado» significa «se llamó al callback», y el callback es un doble: de ahí a una burbuja pintada hay cuatro costuras más que fallan todas en silencio. ⚠️ **Y una trampa del propio cierre, por segunda noche seguida**: archivar por bloques se tragó dos encabezados del índice, porque el límite de un bloque no está donde parece — va hasta el siguiente `- **` **o hasta cualquier encabezado**. Lo cazó el trinquete, y se rehízo desde el snapshot §20 verificado por sha. ⚠️ **Y el agujero que esto encontró y no cierra**: **una excepción de JavaScript en el cliente es invisible para la observabilidad** — no hay puente de `window.onerror`/`unhandledrejection` a `emit`, así que la línea de tiempo de una sesión no distingue «al cliente no le llegó» de «el cliente petó». Tres de las cuatro quejas de esa noche hubo que resolverlas leyendo código porque el único sitio que las habría contestado en una línea no existe. Merece su propio cambio.
- **A decision model is only worth its round trip where the ROUND TRIP is free — V2-726's audit, executed (2026-09-21)**: an outside audit (Astra 6) of where Jev sits, re-checked line by line against the code: **nine findings, nine confirmed**, two sharpened and one blocker corrected. What it found was not a broken integration but a set of things that were true of the CODE and false of the TURN. **(1) The brief classified a FRAGMENT.** It was fired at the top of the turn — before echo suppression, before the accumulator — while the model was handed `text = _merged` a hundred and seventy lines later. «Ponme música» fired it; «de los ochenta» arrived three seconds afterwards. It fires at the ADMITTED sentence now, and nothing is lost by waiting: the prompt is assembled 3 ms after admission and every reader is 2-4 s away behind the model's own TTFT. **(2) The state it carried was false**: `has_workers`/`ask_pending` were never passed, so the escalate question said «no worker is waiting» on every turn — including the turns where one was, which is exactly the shape that must not become a second worker. **(3) The filler opened a SECOND socket** for the same words, one second later, read at the same deadline: two trips per turn became one. **(4) A confident `handle_inline` cleared the commission with no completion evidence** — and by then the operator had HEARD a reply that usually promises the errand, so the gate built to prevent wasted work was producing the oldest failure in this engine: a promise with nothing on the board. It needs evidence now (an uncovered promise vetoes; a real inline result allows; neither keeps it), every commission ends in a NAMED disposition, and no second model referees. **(5) The route pre-choice was REMOVED, not repaired**: it never reached the wire once in 312 real calls (four positional args into a one-positional signature, eaten by its own `except`), and F0a had already measured its question away — a full stable catalog beats trimming, because the trim breaks the prefix cache to save a prefill cheaper than the trip. Repairing it would have reinstated a cancelled design. **(6) The screen question is keyed by INSTANCE**, carries what each card is SHOWING and only actions POSSIBLE NOW; with nothing open its twin asks which widget of the catalogue is NAMED, using the alias table (V2-082) that already existed and had never been handed to the chooser — the direct cause of «ábreme el vídeo» scoring 0/8 at 0.52-0.61, which is ABOVE the gate and therefore acted on. **(7) Nothing recorded whether a verdict was USED**: `jev.read` computed `info["used"]` and every consumer threw it away, the brief event reported `max()` confidence across its questions, and no handle carried an id — so «these two events are the same turn» was a claim about clocks. Every trip has a `call_id`, every read leaves one bounded event with WHY, and `select_many` stopped answering `[]` to «nothing fits», «no key», «network down» and «switched off» alike. **(8) A worker could not reach any of it**: `nucleo/workers/`, `errands/` and `research.py` mention Jev nowhere, because a Brain Worker is a subprocess that talks to the engine only through `/api/worker/act`. One new allowed action — not a second client, not a new bridge, not a model inside the worker — plus `jev.decide()` with eight statuses where three are ANSWERS and five ABSENCES. **(9) A voice turn whose brief failed to build could still reach a blocking `urlopen`** from inside the provider's `async def`; the static ratchet could not see it because the provider names the wrapper, not the call inside it. ⚠️ **The rule this whole pass turns on**: Jev serves what is decided AFTER the model. Nothing decided before it can wait 800 ms for a verdict when the catalog is settled at 381 — so «put the classifier in front» is not a smaller version of this design, it is the opposite one. ⚠️ **And the testing lesson, paid for four times in one night**: a disarm that stays GREEN accuses the TEST. Four did — one asserted on the brief's transport while the blocking call goes out the single-question door; one asserted an action `results` never offers at all; one asserted a word YouTube's own description also contains, so deleting the alias list changed nothing; and one aimed at `decide`'s membership check when `_parse` already blanks an invented id one layer down. Same class as the dead route the audit started from: an assertion aimed at the wrong seam cannot fail. ⚠️ **Three defects the tests found while being written**: a negated promise («no voy a buscarlo») read as a commitment, because `promises_action` runs through `unnegated_match` and `a_promise_left_hanging` does not; the possible-now filter asked «which key identifies this call» instead of «which key names an EXISTING row», which deleted every CREATION action from an empty widget; and `worker_bridge decide` first took inline JSON, which the worker's own prompt says in capitals our permission gate rejects — the door would have been unusable by the only process it was built for. ⚠️ **And a live call escaped during development**: a three-line smoke test of `decide` hit the real API and wrote an event into the operator's timeline, removed by hand. A smoke test is a test. Nodes 3.61-3.65 and 3.69-3.71; 16 red widget tests triaged to 1 (twelve were a fixture with an expiry date nobody wrote down, two were `radius == 0` read as «names one thing», one was a confirmation decided by heuristic instead of declaration). **What is NOT claimed**: the pilot's A/B against the old path and the effectiveness bench have not been run — both need live, paid runs, and the first numbers become the baseline everything after is compared to.

- **Every piece was green while the CHAIN was broken — the use case is what closed V2-728 (2026-09-20)**: the five things left open the same morning, done. The one that mattered is the test: `tasks_store` stored, the seam translated, `task_recall` narrowed, the tab rendered — four green files, and nobody was asserting that they agreed about the same task. `test_the_flat_hunt_he_told_me_about.py` walks the operator's own sentence end to end (commission → live row with its start time → report with five kept and fifty rejected → close → the sheet cap prunes it off disk → «enséñame lo del piso que te dije» rebuilds it), and it found two real breaks on its first run: without a declared `surface` the errand seals no sheet, so there was nothing to snapshot; and a worker does not carry its sheet in its spec — it resolves it from its own task id, which the test had to do too or it would have been writing into a box the product never reads. **Four more closures.** (1) **The memory pill.** `tasks` answers «which task do these WORDS name» and is only consulted once he has said he means a task; recall answers «what bears on what he just said» and runs every turn unasked. Before the pill, «¿encontraste algo de pisos?» — a sentence that never says *tarea* — retrieved the conversation and not the errand that went and found five. It is a NORMAL pill, so the writer derives its graph edges with the same `derive_concepts` backstop every durable pill gets: «que todo eso quede vinculado» is that edge set, not a bespoke join. It supersedes its own earlier chapters (`memory.api.task_trace_ids`), because a commission can close twice and recall would otherwise serve «no encontró nada» beside «encontró 5 pisos» — V2-577's failure with a different prefix. And `meta.task_id` is a FIELD and not an `edges` row for the honest reason that an edge joins two MEMORY ids and a task is not one. (2) **The button.** «Le da el botón y ve los datos derivados» had nowhere to call — a voice tool is not reachable from a click. `POST /api/tasks/reopen` rebuilds the sheet and then emits the same `widget/show` the brain emits, rather than answering with an id: one door, so it reaches the mobile shell and lands on the observability timeline. The row draws it only when the board says `has_results`, because a button that opens nothing is worse than no button. (3) **The discarded ones**, which the operator asked for by name and which the earlier pass declared out of reach: it was a change to what the worker REPORTS, and that is a prompt and a widget action (`rejected`, `{title, url, why, source}`, reported as it goes, `why` mandatory — a list of names with no reasons is not an audit, it is a longer list). They never enter the results LIST, which is the selection; they render under the count that was already in the Summary tab. (4) **The calendar** now READS the task table instead of anything being copied into it (`_system_tasks`), dotted and in its own hue — never as a meeting, because nobody is meeting anybody. The subtlety is the filter: every appointment schedules its own notice, which is a scheduled task like any other and would mark the calendar twice for one meeting, so `scheduler.create` now carries an `origin`. ⚠️ **And the worker ledger is retired** — `nucleo/workers/ledger.py`, `/api/workers/history` and `workersHistory()` are gone. The interesting part is its FENCE: `clear()` stamped «wiped at T» into `sys_kv` and every writer had to remember to compare against it, because a reset kills the workers and the dying one writes its tombstone onto the fresh slate milliseconds later (seen live 2026-08-31). A rule each writer has to remember is not a rule. The table lets the question be asked directly — **does this task still exist?** — and a row the reset deleted is not one to be closed, so nothing downstream runs either: no orphan report, no memory pill about a commission he just erased. **The sheet cap stopped being a data-loss cap** (8 → 40) and gained the guard recency only approximates: a LIVE errand's sheet is never pruned, because there the sheet is not a rebuildable view but the box the worker is writing into, whose snapshot does not exist yet. The ratchets did their job twice: `memory.api.__all__` refused `task_trace_ids` until it was declared with its reason, and the loop's injection test passed a hook with the wrong arity — `consolidate` calls it inside a `try/except` that logs at DEBUG, so a mismatched signature does not fail, it silently stops pruning forever; the assert now CALLS the hook the way the consolidator does. Node 3.66 grew the chain test; the fence test moved to `test_a_reset_leaves_the_board_blank.py`. Seven disarms, all red. **Still open, and unchanged**: the scheduler's storage.
- **The first screen, end to end: a first run stops wearing the previous install, a link in the chat IS a link, and the introduction OFFERS the tour (V2-735/736/737, 2026-09-20)**: one message from the operator, three separate things. **(1) V2-735.** *«Cuando el sistema arranca, no quiero que por defecto el orbe esté metido en la barra inferior… totalmente arrancado, porque la voz tiene que empezar a sonar enseguida.»* Both of those already ARE the defaults — `orbDock` is `"eye"` and `powerOff` false unless localStorage says otherwise — so what he was looking at was **the previous install's browser state**. A factory reset (V2-670) starts the AGENT over and cannot reach `localStorage`, which is per-origin and survives everything the server can do to itself: the orb came up docked, the voice off (and with it the boot veil lifted on a session that was never going to start), the previous desktop's cards restored. Now a first run (`chosen:false`) wipes our own prefixes and reloads, ONCE, guarded in `sessionStorage`. **A wipe and not a list of signals to re-apply**: the signals are seeded at module import, long before anything knows this is a first run, so re-applying them means naming them — orb, power, desktop, chat, theme, captions, mic — and that list is the one somebody remembers (V2-727). **(2) V2-736.** He asked the agent to leave him the public guide in the chat; measured first, `markdown-lite.js` rendered bold, code and lists and **nothing about URLs**, so the link would have arrived as text to copy by hand — telling a model to use a capability the surface does not have is V2-540 with the halves swapped. Autolinking now runs over already-escaped text and only on a literal http(s) scheme. ⚠️ Its first version had a real defect the test caught: `escapeHtml` does NOT touch quotes, so `<a href="https://evil.example">click</a>` escapes to text whose URL run swallows `"&gt;click…` and the anchor **broke out of its own attribute** — not an injection (nothing new is created, the tag is merely malformed), which is exactly why «no foreign element» and «no non-http href» both passed on it. The test pins the anchor's exact SHAPE instead, and the disarm is honest about the three guards: removing any ONE leaves it green because the other two cover it, removing two goes red. **(3) V2-737.** The introduction pack (V2-675) already greeted, asked his name and ended by itself. Its capability half was one word wrong — *«**SI TE PREGUNTA** qué puedes hacer»* — purely reactive, and **somebody who does not know what to ask never asks**, which is the whole description of the person this phase exists for. Now it is offered once, dropped for good if he declines, led one thing per turn, reaching the examples he named (vídeo, música, un piso, un coche, unas vacaciones para unas fechas y una zona, sugerencias) and leaving the guide in the chat without reading a URL out loud. NOT added: a second widget catalog — the live one is in the same prompt above, and two hand-written inventories is how they come to disagree (V2-594, V2-603). Nodes 4.195, 4.196, 3.38; five disarms red. ⚠️ **And a finding this pass owes to nobody's change**: `tests/browser/unit/widgets/test_resolver_certainty.py` reads the REAL widget catalog, and a widget the operator generated today (`widgets/_user/canvas-shows-day`, «Tiempo · San Mateo») makes «qué tiempo hace hoy» open something — so that test now measures his machine. Second instance today of the same class as `i18n/generated/` not being sandboxed; both are open. **The rule: a reset that cannot reach the browser has not reset the product.**
- **The region chooses the accent: es-ES / es-419 / en-US / en-GB in the picker (V2-734, 2026-09-20)**: the operator, right after V2-733 got the Spanish voice to the live session: *«la voz que hay ahora de una chica… no es lo mismo el español de España que el español latino. Pon inglés de Estados Unidos, inglés de Reino Unido, español de España o español latino. Eso nos ayudará a elegir por defecto la voz más adecuada»*. Measured in his own cached catalog, `for_language("es")` returns **Elena (peruvian)** first, `Sara Martin 1` (**peninsular**) second, `Brian C` (latin american) third — so *the first native voice*, which is correct and was the whole of V2-672's fix, hands a Castilian operator a Peruvian voice. Sara is `KHCvMklQZZo0O30ERnVn`: the very voice V2-672 removed as the hardcoded default, and the one he remembers as «una chica que hablaba muy bien el español». **A variant is NOT a language**: `es-ES` and `es-419` share the bundle, the STT code, `ZAELAR_LANGUAGE`, the memory's canonical language and the whole UI — the only thing a region decides is which ACCENT the default voice has, so making them languages would mean a second Spanish UI to generate for a difference the interface does not have. `catalog.VARIANTS` + `split_locale()`; `picker()` offers a shipped language AS its variants while `PINNED` stays `("en","es")` so the «instant» promise still mirrors `runtime.PRESET`; `_REGION_ACCENTS` in the vocabulary the Voice Library actually uses; the region persisted as `language_region` beside the language by the ONE door both callers go through, and read only where a voice is chosen. After: `es-ES → Sara (peninsular)`, `es-419 → Brian C`, `en-GB → George (british)`. ⚠️ **The trap is `voice_is_aligned`'s own trap, one level down**: it exists because «is it in the list» is not «is it right for this language» — and a peninsular voice IS a native Spanish voice, so switching es-ES→es-419 would have looked aligned and changed nothing. It now asks about the accent too, but only when some native voice actually has one of the region's accents, and never on a voice whose accent we cannot read: an unknown accent is not evidence of a wrong one, and losing a deliberate choice to a missing field is worse than the bug. ⚠️ And the picker's single mark (V2-730) had to learn the full code: with rows called `en-US` and an active language of `en`, matching by code would have marked NOTHING — it falls back to the language's first variant, which is also the one whose voice is the default. Nodes 8.6 and 4.162, three disarms red. **The rule: a preference that only affects one output does not need to become a new dimension of the system** — the alternative, a locale propagating into bundles, STT codes and memory, would cost every module a branch to answer a question only the mouth asks.
- **A setting read once at construction is not applied by being saved — the realigned voice never reached the mouth that was speaking (V2-733, 2026-09-20)**: the operator, arriving in Spanish on a fresh install: *«acabo de probar arrancar en español y me sale la voz del señor inglés intentando hablar español, con lo cual lo hace muy mal»*. Everything upstream already worked — V2-672's per-language ElevenLabs catalog is right (measured on his machine: `en → CwhRBWXzGAHq8TQ4Fs17`, `es → dyTONAae6PhdRb3hMKPM`, two correct native voices) and `settings.update()` does realign `assistant_voice` the moment a language is locked. **What did not exist is the last metre.** The TTS is constructed when the pipeline is built, reads its voice ONCE via `voices.selected_voice()` and keeps it for the session; `settings.py`'s own header says «Effect: RECONNECT the voice session to apply», the ⚙ honours that by reading `needs_reconnect` and calling `session.reconnect()`, and **the first-run lock ignores the return value entirely**. So the right voice sat in `settings.json` waiting for a reconnect onboarding never asks for, while the live session spoke the new language in the old language's voice — starting with `onboarding.confirmSpoken`, which by design is *the first sentence the operator ever hears*. **A reconnect cannot be the fix here**: the confirmation is spoken the instant `lock()` returns, so it would land in the session being torn down. `voice/engine/speech/live_tts.py` holds the TTS that is speaking now — `agent.py` attaches it between `build_tts()` and `AgentSession(`, and the realignment branch calls `apply_voice(want, lang)`, appending `assistant_voice(en vivo)` when the plugin took it. Measured: the installed plugins expose `update_options` (ElevenLabs `voice_id=/language=`, Cartesia `voice=/language=`), so the swap is a method call and not a rebuild; the module asks the SIGNATURE which keyword names the voice, so a plugin rename surfaces as «could not re-point» rather than a call that looks fine and does nothing. The language is re-locked with the voice — a multilingual model drifts in accent on short text when it is not told what it is speaking (V2-035). Every failure path degrades to exactly the old behaviour. ⚠️ **The STT did NOT have the same hole and that is deliberate**: at first run it is multilingual on purpose (`deepgram` `"multi"`, `voxtral` omits the language) because the language is not known yet — his Spanish was understood all along, it was only the mouth that was wrong. Node 8.6, two disarms red. **The rule: the question to ask of a knob that reaches a live pipeline is not «did we persist the right value» but «what is running right now, and how does it find out» — and if the answer is «a reconnect», check what is queued to happen before it.**
- **Nothing is shown for nothing: a language already initialized gets NO preparing screen (V2-732, 2026-09-20)**: the operator, minutes after V2-731 gave that screen a 2,2 s floor and a bar: *«espera, si no hay que hacer nada para idiomas inicializados, mejor no mostrar NADA en ese caso»*. He is right and it is the better rule: V2-731 answered «a screen I cannot read» by making it last longer, and the screen it was making last had **nothing behind it** — for en/es there is no preparation at all. The floor and the bar are kept; what changed is who they apply to. `_pending_steps(code)` now answers *what is this lock actually going to GENERATE* before anything runs, and each check mirrors the early return of the step it stands for so the count cannot claim work that will not happen: `code in PRESET` or no `missing_keys` → no bundle step (`ensure_language` returns on its first line for a preset), `aliases.read(code)` → no alias step, `read_smalltalk(code)["intents"]` → no phrasebook step. An unreadable store counts AS work: unknown means we are probably about to do it, and a missed step is a wait with no screen, which is the cheaper failure direction. Zero travels as `total: 0` in the `detected` event and `sse.js` then sets nothing, arms no floor and draws nothing — he keeps looking at the picker, with the choice he just made marked on it (V2-730), until the veil fades; `_step()` reports only steps that were pending, because a no-op returning in a millisecond is not progress. ⚠️ **The card's order had to change with it, and that is the part to know.** `view()` was keyed on the PHASE, so the folder question could only appear once the engine had said «detected» — an accident of ordering, not a rule — and anything past «ask» fell through to the preparing screen; suppressing the screen would have made step two unreachable. The order is now by CLAIM (the question if it is ours to ask → the preparing screen if there is real work → the picker), which means **the folder question now appears as soon as the server says this deployment may choose a folder** rather than waiting for an event that has nothing to do with it. ⚠️ **And the trap this found, open**: `i18n/generated/` is NOT sandboxed by the root conftest — a test asking the disk whether `ja` has a phrasebook reads the operator's real one, left by an earlier run, so the first version of these tests passed or failed on which languages this machine had tried. Both were rewritten to state the rule with monkeypatched readers; the conftest gap is the same class the suite has paid for five times and it reaches every i18n test, so it wants its own pass. Nodes 4.194 and 4.162, disarms red on both halves. **The rule: a screen earns its place by having something behind it — making an empty one last longer makes it worse.**
- **A screen nobody can read is a screen that did not happen — the preparing step gets a floor and a bar (V2-731, 2026-09-20)**: the operator, seconds after choosing a language: *«ha salido como una pequeña pantalla que ha durado un segundo o dos y no sé qué era. Si hay un loader o una pantalla tiene que tener un progress bar o algo, pero como mínimo debe durar dos segundos para que la gente lo vea»*. Two defects, neither of which errors. **(1) No floor.** `lock()` emits `detected` and then `ready` once `prepare()` returns, and for a PRESET language — which is every operator's first run, since en/es are what we ship — `prepare()` reads a bundle already on disk and returns immediately, so both events land in the same breath and the veil fades 550 ms later. **(2) Nothing readable on it**: a bare spinner, which says «something is happening» — exactly the sentence he could not turn into an answer for *what was that*. And there was nothing to build a bar out of: the engine reported NO progress between the two events, though it does up to three distinguishable things (UI bundle, alias pack, phrasebook). Now the floor is `LANG_LOADER_FLOOR_MS = 2200`, armed by `sse.js` when the screen appears rather than when the work started, and the bar is fed by the ENGINE's own step count (1 for a preset, 3 for a language it has to build), sent with the first event so the denominator never grows halfway through; with no count it SWEEPS rather than inventing a percentage. **The load-bearing change is the hold.** V2-672 established that the language being ready is not enough to close the veil and wrote it as one boolean — and a second reason cannot be added to a boolean without the floor's release taking the folder question off the screen mid-answer, which is the exact regression V2-672 exists to prevent; `holdLangOnboard(on, reason)` now keeps a SET and the veil closes only when it is empty. ⚠️ The progress event deliberately carries no `code`: `sse.js` re-applies the language on any `language` event that has one, so a progress report with a `code` refetches the bundle once per step — pinned by a test, because the next person to add a field there will not know. Nodes 4.194 (the real `sse.js` over the real store — a test that armed the floor itself would pass with the wiring cut) and 4.162 (rendered: the bar has ink, 0/3 is a sliver and not an empty track, `ready` is 100 %). Three disarms, three reds. **The rule: a transient surface needs a floor measured from when it APPEARS, and if it is worth showing it is worth saying how far along it is — when the honest answer is «I cannot say», an indeterminate bar says that and a made-up number lies.**
- **A colour that means «chosen» cannot be borrowed to mean «important» — the first screen showed two languages selected at once (V2-730, 2026-09-20)**: the operator, on a fresh install: *«ya cuando esto arranca, si te fijas por primera vez, te quedan seleccionados los dos idiomas. Tienes que seleccionar solo uno y entonces el usuario puede clicar otro, pero no los dos a la vez»*. V2-672 needed English and Spanish «destacados arriba» and drew that prominence with `--hb-accent` — the colour this product uses everywhere to say CHOSEN — so `.lang-onb-row.pinned` put an accent border on **both** shipped rows. The picker had no notion of a current language at all: `.pinned` came straight off the catalog row and nothing ever read `/api/i18n/state`'s `active`, so the first screen of the product asserted a fact about state that was false, and a click on either row changed nothing visible. Split in two: prominence is now `--hb-line-strong` plus the raised surface, and the accent marks the ONE language the engine is actually running in (`aria-pressed` with it), moved by the click rather than by the round-trip. The row's `class` is a function, so the mark repaints two borders instead of re-rendering forty rows, and `:hover:not(.sel)` sits last — which also restores the hover feedback `.pinned` used to swallow, i.e. the half of the request that says the other row is clickable. One fix, both shells: the mobile PWA mounts the same component and links the same stylesheet. Node 4.162; the rendered test resolves the accent through a probe element and asks every row what colour its border ACTUALLY is, because a `classList` check passes with the rule deleted from the stylesheet — the disarm goes red with `got ['en', 'es']`, the operator's sentence in the assertion's own words.
- **A «process» was five stores and none of them the whole truth — the TASK is the unit now (V2-728, 2026-09-20)** — texto íntegro en `.meshkore/docs/decisions-archive.md`.
- **A prohibition is not a diagnosis: the wide sweep hung on ONE line, and it hung on the operator's own 84 GB video (V2-727, 2026-09-20)** — texto íntegro en `.meshkore/docs/decisions-archive.md`.
- **Jev SELECTS over parsed data in one trip, and the call stopped throwing away work it had paid for (V2-726 F4+F5, 2026-09-20)** — texto íntegro en `.meshkore/docs/decisions-archive.md`.
- **The turn asks Jev ONCE, and the voice path stopped blocking on it (V2-726 F1+F2, 2026-09-20)** — texto íntegro en `.meshkore/docs/decisions-archive.md`.
- **Trimming the tool catalog per turn costs 35% MORE than sending all of it (V2-726 F0, 2026-09-20)** — texto íntegro en `.meshkore/docs/decisions-archive.md`.
- **A fix whose only changed file is the one no test executes ships green (review of the voice-session-fixes batch, 2026-09-20)** — texto íntegro en `.meshkore/docs/decisions-archive.md`.
- **Nobody can tell a doomed turn from a live one at dispatch — so murdered streams survive downstream, by choreography (voice-session-fixes, 2026-09-19)**: all 10 errors from voice session 6d19df41 fixed and committed (`faed7601`…`5ff39903`). The last one, the turn fight (14 streamed turns murdered mid-sentence, 13 pre-token, + 3 pre-stream drops), resisted every dispatch-time reading: the operator dictates in 1–4 s bursts against 1–3 s TTFT and each fragment reads complete standalone («It is car.»), so any rule that acts before the murder either kills live turns or keeps ghosts. Trace reconciliation showed survival was already working — 38 prompts = 23 replies + 14 murders with exactly one scissors line each + 3 drops, no lost words (successors re-merged them) — via a three-step choreography in `voice/engine/llm/providers/nucleo.py`: the stream's CancelledError handler preserves the operator's text (prefix-coalesced) + sets `_death_logged` + reports with metrics; the `_run` wrapper returns early on the re-raise and is an idempotent preserve-and-report backstop for deaths the handler never sees. No production code changed for fix10; the deliverable is the regression pin (node 3.57, disarm-proven). Deliberately NOT decided: endpointing vs barge-in tuning stays open.
- **A «yes» answers ONE proposal, and spends only that proposal's authority (V2-724, 2026-09-18)**: the
  audit's correction to V2-723's own down payment, and it landed on a hole opened hours earlier. Requiring
  that we «previously asked something» is necessary and NOT sufficient: with only that, a «sí» to «¿te
  apunto la cita del dentista?» still licensed a video load — one proposal's answer spending another
  proposal's authority. The affirmative is now bound to the proposal's EFFECT CLASS, and the class is read
  from declared data twice over: the certainty resolver every show already uses, and failing that the
  vocabulary the producing widgets publish about themselves (`musica` lists «canción», `youtube` lists
  «clip»). No verb table of ours, and a forked player brings its own words. Its sibling covers the other
  effect a yes can spend: a just-closed card reopens on «vale» only when the pending proposal was about
  THAT card — «¿lo vuelvo a abrir?» names nothing and now authorizes nothing. Known limit, written down
  instead of patched with more words: an offer naming no medium («want me to play something else?») is not
  recognised, so it costs a repeat — the failure direction we want. Same node 3.54, two more disarms.
  ⚠️ **The envelope the audit specifies is the real fix and is NOT built**: a turn/task authority narrowed
  into a per-action GRANT (originating turn or continuing task · action + resolved targets or an authorized
  selection scope · allowed effects · expiry and revocation · execution identity), children narrowing and
  never expanding; enforcement at BOTH ends (dispatch validates the grant before work starts, each effect
  door enforces the actual effect as it happens) with ONE policy evaluator; a delayed worker deriving a
  FRESH grant from persisted task authority rather than reusing an old turn's or re-reading its own
  free-text description; and three outcomes instead of one — suppress-and-trace an incidental effect, PAUSE
  the dependent work and request authorization for an essential one (`awaiting_authorization`, never by
  opening a card or speaking to ask), stop and explain a prohibited one, and never report full success when
  suppression prevented completion. Also on the record: the emitter ratchet prevents regression, it does
  **not** establish coverage while the twenty-one legacy bypasses remain.

- **An action does not manufacture permission for its own side effects (V2-723, 2026-09-18)**: an external
  audit of this layer read the catalog, the single dispatch and the browser-owned canvas as sound boundaries
  and put the weak point exactly where the month's incidents live — «authorizing an action is not the same as
  authorizing all its effects». It is the same sentence V2-721 had just paid for one widget at a time:
  `musica:pause` was an action the operator asked for, and running it spent a SECOND authorization (present
  the card) that nobody had given. **Three pieces, and the first is the one that makes the other two
  possible.** (1) `widgets/effects.py` — the effect vocabulary (`data.read/write`, `present.mount`,
  `output.start/stop`, `external.send`), DERIVED from the four declarations that already existed and never
  agreed with each other: `actions.classify`, `actions.is_view`, `runtime.produce/suspend/output`, plus what
  a manifest declares outright. Nothing new to keep in sync, and the one thing that is NOT derivable —
  `external.send`, because a `consent_class` says an action is sensitive, not that it leaves the machine —
  is written down as a hole instead of guessed from names. (2) `canvas_visibility.present()` — ONE door, with
  a declared REASON from a closed set (`operator-hands`, `turn-order`, `producer-mount`, `task-owned`,
  `widget-handoff`, `lifecycle`). The claim is CHECKED, not believed: a caller saying `producer-mount` over
  `pause` is refused by the manifest. An open card is never raised again. And a refusal is EMITTED — the
  audit's «include suppressed effects», without which this door would just be a new silence. Thirteen call
  sites emitted `show` anonymously; the voice provider now holds zero, and a ratchet freezes the twenty-one
  remaining (workers, sheets, the action map) so the next one cannot be born anonymous. It also retired a
  hand-written verb list in the probe's music mirror that said `stop/pause/close` and knew nothing about
  `volume_up` or `seek`. (3) The down payment on the audit's sharpest point — «grammar licenses are
  misplaced if they are keyword gates»: `video_license` licensed ANY turn of ≤4 words containing an
  affirmative, an escape written for «¿busco de nuevo el vídeo?» → «sí» with nothing checking that an offer
  existed. Measured 2026-09-17: «Okay. What if» licensed a `resume` and restarted music he had paused by
  hand. The table was not widened — the FACT it depends on is now required, in both channels and in the
  arbiter's tap. Nodo 3.54, cinco desarmes rojos. ⚠️ What the audit asks for and is NOT done: the execution
  envelope (originating turn, permitted effects, resolved targets, expiry, execution identity) that would
  retire these grammar licenses instead of tightening them, and canvas revisions/acknowledgements so
  «requested open», «actually open» and «unknown after disconnect» stop being one flag. Its other correction
  stands on the record: **the shadow arbiter is not to become the enforcement boundary** (V2-653 F1 was
  planned the other way round) — deterministic doors enforce, the arbiter reports disagreement.

- **A card opens only for what the widget DECLARES as production (V2-721, 2026-09-17)**: session
  `c553a1e0`, demoing to a guest. Music was playing; he paused it, asked for his agenda, closed everything —
  and four minutes later, mid-sentence about his headphones, the music card came back on screen three times
  and the player woke up. «Ha habido como un baile de abrir y cerrar widgets sin mi permiso […] los widgets
  no dejan de ser un catálogo y deben tener un flag de si están abiertos o cerrados.» **The flag existed and
  was authoritative** (`/api/canvas/state` → `memory.state().open_widgets`, written by the frontend, which
  owns the canvas); what nobody owned was **who may move it**. The voice lane opened the card on EVERY
  successful music action, because the connector's result says `surface: "widget"` — and `pause`,
  `volume_up`, `seek` and `queue` say it too. That field answers «where does the sound come from» (a hidden
  iframe in the card, versus a Spotify device): a fact about AUDIO, read as an instruction about the screen.
  The same complaint is on record a day earlier (`928c8761`, 772 s, on a `stop`): «I did pause it manually,
  and you did start it without my request.» **The rule, and it is declared data, not a verb table:** an
  action may open a card only if the widget's manifest lists it in `runtime.produce` — the same declaration
  `producers.py` has owned since V2-092 and the replay license reads since V2-650 — and never if the card is
  already open, because a `show` on an open card raises and refocuses it, which was the other half of the
  dance. `musica` declares play/resume/next/previous/play_playlist/ended; pause, volume and seek are not
  there and now change nothing about the screen. The canvas arbiter learned the SAME rule (`producer-mount`
  beats `show-drag`), and that mattered more than it looks: of its six `show-drag` verdicts over the music
  card in twelve real sessions, five were the control shows this removes — but ONE was the honest mount of a
  play he had just asked for, so **arming the arbiter (V2-653 F1) as it stood would have answered him with
  silence**. Nodo 3.53, cinco desarmes rojos. ⚠️ Two things this did NOT fix, both measured in the same
  session and left as findings: the model issued `resume` on «Okay. What if» because `video_license` licenses
  any turn of ≤4 words containing an affirmative (an escape written for «shall I search again?» → «yes», with
  nothing checking that anything was asked); and the accumulator closed the turn «…play us some music?»
  WITHOUT the «Maybe Bruce Springsteen» fragment that had arrived four seconds earlier, so the agent asked
  which artist he wanted after he had named one.

- **«All of these EXCEPT that one» never means all of them (V2-720, 2026-09-17)**: session `e22cdba8`, and he
  said it three times — «can you delete all the items but the meeting with Ivan?», «please do not delete the
  meeting with Ivan», «delete the others and ask me for confirmation». What ran, with no question asked, was
  `clear_range {from: hoy, to: hoy, keep: {title: "Approval rules: who signs off"}}`: a real exception,
  correctly shaped, **aimed at an appointment that was not in the day**. `kept()` answered False for every
  row, the keeper evaporated, and the day went with his ten o'clock inside it. Then the model told him the
  tool «didn't let me specify an exception» — it had specified one, at a phantom — and escalated a Brain
  Worker task to build the capability that already existed, whose first step DELETED the agenda widget
  (`hidden.json`; restored by hand). Three mechanisms, no rule about conduct: **(1)** a keeper that matches
  nothing REFUSES and hands back what the window really holds — the same thing `rows.plan` has said since
  V2-707 («nothing matched» on a destructive op is a misunderstanding, never a silent no-op), which one floor
  down was letting it mean «everything». **(2)** the RADIUS of a sweep is its ROWS, and only the widget can
  count them: `data.radius(action, payload)` is a hook `frontend._scope` consults before the consent rule, in
  the shape of `consent_scope` — absent or unreadable keeps the old verdict. Until it existed, `_scope` read
  `clear_range`'s selector, `from`, found the DATE filled and answered «names one thing», so a day of
  deletions was charged one appointment's friction: `confirm:true` in the manifest, `fast` in the call. The
  rail was already written (V2-707: more than one asks); nobody was counting. **(3)** the sentence he speaks
  is now sayable: the generic door takes `where` + `not`/`except` (one clause or several) + `ids` from a
  `rows.list`, and a negated LIST finally means «none of these» instead of «any of these» — it inverted, so a
  three-name exception selected the whole collection, the three keepers included. That last clause is what he
  asked for in his own words: list what is really there, pick from THAT, and delete the rest one by one,
  every row through the widget's own `cancel_meeting`, so the Google mirror and the V2-705 contract still run.
  Nodo 4.191, cinco desarmes rojos.

- **Una invitación que no LLEGA, y el criterio de a qué se pide permiso (V2-718, 2026-09-17)**: su asistente
  había negociado una reunión con Ivan por Telegram, acordado la hora, creado el enlace de Meet y escrito la
  cita en Google Calendar — y el último mensaje de Ivan, «can you send me a calendar invite to:
  ivan@charms.dev», se quedó sin contestar. El operador: «lógicamente si tenemos el conector de email y las
  acciones deberíamos ejecutar esa petición […] pero no crees un guardarraíl o un workflow solo para eso».
  **La agenda podía crear una cita, editarla, responder a la invitación de otro y borrarla, y no tenía forma
  de invitar a nadie a la suya** — y, aunque el verbo hubiera existido, no habría funcionado: `sendUpdates`
  no aparecía en todo el repo, y el valor por defecto de la API de Google es `none`, así que añadir a alguien
  a `attendees` devuelve 200, lo pone en el evento y **no le manda nada**. La misma clase de fallo silencioso
  que `conferenceDataVersion` ya documentaba una función más abajo en el mismo fichero.
  **Dos peldaños de UNA escalera, y los elige la CITA, nunca el destinatario**: si la cita vive en un
  calendario nuestro, se añade al invitado ahí y la manda el calendario —lo que recibe es una invitación
  iCalendar real que su propio calendario enseña con Aceptar/Rechazar, sea Gmail, iCloud u Outlook, y cuya
  respuesta vuelve al evento—; si no hay calendario detrás, la construimos (`connectors/calendar/ics.py`) y
  la mandamos como parte `text/calendar; method=REQUEST` más `invite.ics` adjunto, que es lo que hace que un
  cliente enseñe los botones en vez de un fichero suelto. Adivinar el proveedor por la dirección («esta
  parece de Apple») sería una afirmación sobre el correo de otra persona que no se puede saber.
  **Y el criterio de consentimiento, que es lo que pidió de verdad**: «esto que no nos hace ningún daño no
  necesita permiso; añadir a otra persona, cambiar de hora sí». La regla única de V2-712 ya era dato
  declarado y no podía distinguirlos, porque la diferencia no está en el verbo, ni en las claves del payload,
  ni en las palabras de la petición: está en **si la llamada se queda dentro de un compromiso ya adquirido
  con quien ya estaba dentro**. Solo el widget que tiene la lista de invitados lo sabe, así que ahora puede
  decirlo (`consent_scope`, leído por `nucleo/flash/frontend._policy_key`) y la respuesta es una CLASE de
  genesis que él cambia hablando: `calendar.invite_agreed` allow, `calendar.invite_new_party` ask,
  `calendar.reschedule_committed` ask. El seam REFINA, nunca inventa: un widget sin el hook, o cuyo hook
  revienta, conserva la clase de su manifiesto.
  ⚠️ «Quién ya estaba dentro» sale de datos —los contactos que el título nombra, resueltos con el matcher de
  la casa y **solo si son inequívocos**, y las direcciones que esas personas nos han escrito— porque recorrer
  el directorio buscando subcadenas es cómo «Meeting with Ivan Mikushin» adoptó en silencio a otro contacto
  llamado solo «Ivan», y adoptar a la persona equivocada aquí es el daño que la pregunta existe para evitar.
  Nodos 5.30 y 2.36; 11 desarmes, los 11 rojos. **Preparado y NO ejecutado**: el encargo lo termina él. **Revisado el mismo día:** una clase declarada en el manifest es un SUELO que el hook no puede bajar (`move_meeting` la declaraba y toda cita preguntaba, el dentista incluido, con el test mirando el hook y no el veredicto); y «la última cita de la agenda» como fallback era un festivo de 2027 — ahora la PRÓXIMA con hora, nunca una de día entero.
- **El widget ES la ventana, y la canción ES la pantalla (V2-717, 2026-09-17)**: con la tarjeta de música
  abierta y una canción sonando, el operador: «has puesto como un contenedor exterior con el título y los
  botones del sistema, y dentro has metido otra caja como si eso fuera el widget de música. Yo solo quiero
  UNA caja encima del escritorio» · «me gustaría ver la canción en toda la pantalla del widget: la imagen
  más grande, el nombre, el artista, la duración, una barra de progreso para que yo la pueda mover» ·
  «está un poco triste al verse tan vacía».
  **Tres cosas, y la primera generaliza el estándar de cabecera.** (1) Un widget que dibuja su propio
  `border`+`radius`+`background` pinta una tarjeta encima de la que el canvas ya dibujó: dos marcos, dos
  radios y un pasillo muerto entre ellos. Un widget NO añade caja — las tres bandas se separan por TONO y
  una línea de pelo. (2) La cara por defecto es ADAPTATIVA: `home` es la canción cuando suena algo y la
  biblioteca cuando no; `now`/`library` la fijan por clic o por voz, y el conmutador entre ellas se DIBUJA
  SOLO si hay a dónde ir (la misma regla del raíl de contactos: una sección sin nada no se dibuja). (3) La
  pantalla vacía dice algo y ofrece algo real que pulsar.
  **El cabezal de reproducción es de quien hace el sonido, y por eso NO hay posición en el store.** Un
  fichero local y el iframe oculto de YouTube suenan EN SU PÁGINA y tienen su propio reloj: la tarjeta los
  lee directamente y arrastrar la barra los mueve sin servidor de por medio. Spotify suena en un aparato de
  otra habitación, así que su `progress_ms` es una FOTOGRAFÍA que la tarjeta adelanta con su reloj y
  arrastrar es una ida y vuelta (`MusicProvider.seek` se añadió deliberadamente NO abstracto: quien no pueda
  ninguna de las dos cosas conserva el «unsupported» honesto). Un seek pedido por VOZ viaja al revés — una
  orden NUMERADA en el store que aplica la página. Tres detalles que sostienen eso: el contador es propio y
  nunca `cmd_seq` (montarlo sobre la secuencia compartida hace que la canción salte atrás cada vez que tocas
  el volumen); `_bump(yt,"load")` descarta un seek pendiente (si no, cruza a la canción SIGUIENTE); y un
  seek no toca `local.seq`, que significa «vuelve a empezar este fichero».
  **El reloj del reproductor gratis ya estaba ahí**: el mismo handshake `listening` que da onReady/ENDED
  desde V2-047 entrega `infoDelivery` con `currentTime` y `duration` — cero llamadas nuevas. Se guarda como
  muestra SELLADA (para interpolar entre tramas en vez de dar saltos), se tira al cambiar de vídeo y se
  filtra por id de handshake: el reproductor del widget de youtube emite en la misma ventana (el cruce de
  V2-366) y sin el filtro su reloj se convertiría en la posición de esta tarjeta. Hasta que llega una trama
  NO se dibuja barra: una barra clavada en cero que no se puede mover es peor que ninguna barra.
  **Dos cosas medidas, no razonadas** (y las dos pasaron por verde antes de medirlas): un carril que pide
  `width:100%` de un hueco sin anchura propia mide 0 píxeles — está en el DOM, se lee bien y no se puede
  arrastrar; y una columna flex que CENTRA su contenido no hace scroll al desbordar, lo RECORTA por los dos
  extremos con `scrollHeight` sin enterarse, así que el test de geometría mide CONTENCIÓN (dónde está el
  borde de la portada y el del carril) y no `scrollHeight`. Nodo 4.3 ampliado con
  `test_the_song_fills_the_screen.py` (18 casos); 26 desarmes en rojo.
- **Una partición que edita el RENDER la deshace el daemon en una pasada (estabilización del repo,
  2026-09-17)**: el operador, mirando un árbol sucio que dos sesiones seguidas habían marcado como «no mío»
  sin tocarlo: «toma el control y estabiliza el repo».
  **La causa era de dos días antes y de una clase que este motor ya ha pagado por otros caminos.**
  `bba7aac8` partió `CLAUDE.md` —el diario a `.meshkore/docs/decisions.md`, el inventario denso a
  `.meshkore/docs/modules/zaelar-module-map.md`— y pasó las cinco copias por CLI a dos, con toda la razón:
  400 KB que carga entero cada agente en cada sesión, y cuatro de las cinco copias ya iban una tanda por
  detrás. Editó **los renders y no la fuente**: `.meshkore/public/AGENT_INSTRUCTIONS.md` conservaba el
  bloque `OPERATOR_CONTENT` viejo, y el daemon de MeshKore renderiza los cinco ficheros DESDE ahí. Su
  siguiente pasada —2026-09-16, 14:09— deshizo la partición entera: `CLAUDE.md` 57 KB → 402 KB con el diario
  dentro otra vez, `AGENTS.md` de puntero a copia, y `GEMINI.md`, `.clinerules` y `.cursor/rules/`
  resucitados. Nadie falló: el trinquete del tamaño se puso rojo y se quedó rojo dos días mientras todo lo
  demás seguía verde.
  **La lección, que es la de V2-687 una capa más arriba**: un arreglo que vive en el CONSUMIDOR lo reaplica
  cada consumidor que llegue después — y cuando el consumidor es un PROCESO, no lo reaplica nadie y encima
  te lo deshace. Si un fichero dice «auto-rendered from X», editarlo es escribir en la salida de otro.
  **Lo que se comprobó antes de reescribir nada**, porque el riesgo real era perder texto: de las 3 874
  líneas del bloque viejo, todas tienen casa en el nuevo ∪ el diario ∪ el archivo ∪ el mapa de módulos salvo
  103, y esas 103 son prosa REESCRITA más compacta — verificado concepto a concepto (`run_testmap`,
  `make run`, `BRAIN=nucleo`, LiveKit, INI-013, Colmena…), no por igualdad de líneas, que es lo que hacía
  parecer que faltaban 311. Copia de seguridad de los seis ficheros fuera del repo antes del primer `write`.
  **El arreglo va en la fuente** y el preámbulo del daemon se respeta verbatim (el suyo era MÁS NUEVO —
  §28 v34, delegación—, así que restaurar `CLAUDE.md` a HEAD habría tirado una actualización legítima: lo
  correcto era el MERGE, preámbulo nuevo + contenido partido). ⚠️ **El daemon reescribió `AGENTS.md`
  mientras esta tanda corría**, ya con el contenido bueno: se acepta como render en vez de restaurar el
  puntero, porque con la fuente correcta ninguna copia puede quedarse atrás —que era todo el objetivo— y un
  árbol permanentemente sucio es lo contrario de estable. Las otras tres se borran y se gitignoran con el
  porqué escrito al lado.
  **Y los dos trinquetes que llevaban días rojos sin que nadie los mirara**: `.meshkore/team/tester.md`
  arrancaba a su agente con `refs: [.meshkore/workflows/INDEX.md]`, un directorio que **no ha existido nunca
  en este repo** (apunta a `tests/README.md` y al playbook, y la ficha dice que aquí no hay W10 — que es
  justo el caso que su propio cuerpo ya contemplaba); y el diario citaba **V2-700, V2-701 y V2-703 sin su
  fichero de iniciativa**, tandas entregadas que el roadmap no sabía que existían. Reconstruidas desde su
  entrada del diario y **marcadas como reconstruidas**: el plan previo y lo medido antes de empezar no se
  pueden recuperar sin inventarlos, y no se inventan. `tests/infrastructure/` entero: 1085 verdes.

- **The directory ORGANISES ITSELF, a platform icon is a FILTER, and a company has several numbers
  (V2-715, 2026-09-17)**: his redesign order over the card open on his **2 688 real contacts**, two days
  after he had asked for the two-bar header himself. Four asks, and the first three are one idea.
  - **«Dos barras» means two ON SCREEN, and the canvas already drew one.** «La barra del sistema parece un
    espacio desaprovechado… me vuelves a repetir un icono de contactos, el nombre de contactos, un texto
    gigante para buscar, un número de contactos con demasiado texto.» The window chrome carries the
    widget's mark, its name and its ⚙, so the brand disc and the content title under it were the same
    sentence twice: **V2-699 was counting from the wrong zero**. The widget now adds ONE bar — search ·
    provider icons · plug — the kind tab strip is gone, and the count went where he put it: «Todos (2 688)»
    on its own rail row. The house standard was AMENDED rather than quietly broken, and it names the three
    widgets (`agenda`, `mensajeria`, `youtube`) still carrying the old shape as a pending sweep — a
    reference implementation that disagrees with the rule is how a standard becomes decoration.
  - **The rail is TALLIED, never a fixed vocabulary.** «El hecho de que arriba me pongas todos, personas,
    lugares o compañías, no sé si es la selección más adecuada… en la barra lateral es donde vayamos a
    desarrollar de forma dinámica todo lo que tenemos. Obviamente, un contacto nunca va a ser un lugar.»
    Kinds, labels, cities and the hidden shelf are counted from the rows on screen: a section with nothing
    in it is not drawn, **one kind present is not a classification** (it is the whole directory said twice),
    and the counts are tallied over the platform-filtered pool so a number in the rail is a promise about
    what a click on it will show.
  - **A linked source icon FILTERS; an unlinked one still opens the screen.** His own correction of what he
    had asked for: «creo que yo lo solicité mal pero debemos cambiarlo. Cuando entramos en Telegram quiero
    ver solo los contactos de Telegram… ya tenemos el botón de conectores para manejar la sincronización.»
    Belonging is BOTH halves (`model.source_matches`) — where the row came from AND where he can reach the
    person — because somebody typed here and later matched to a Telegram account is as much a Telegram
    contact as an imported one, and a tab showing only the imported half would hide the people he talks to
    most. The three states of the house standard survive: unlinked → the connectors screen (there is
    nothing to filter and «conéctalo» is the only useful answer), no connector at all → visible and inert.
    The plug lost its word and kept its `aria-label`.
  - **The record grew, and the scalar did not move.** «Varios teléfonos que estén vinculados a la misma
    empresa.» `phones`/`emails`, several per entry, each with a free label — and `phone`/`email` stay as
    the PRIMARY, kept in step with the head of the list in BOTH directions by `model.normalize`, because
    four modules outside this widget read the scalar (`widgets/directory.py` resolves a spoken number with
    it, `google_people.py` pushes it). A list that silently replaced it would have made every one of them
    read an empty field on a contact holding three numbers. A number's identity is its DIGITS, or «+34 91
    555 00 00» and «915550000» become two rows and two pushes to Google. ⚠️ **The migration runs row by row
    inside its own `try`**: `store.load` degrades a migration that RAISES to the seed, which here is an
    EMPTY address book, and the next save would persist it over 2 688 real rows.
  - **Two defects the measurement found before the redesign did.** `show_view` had carried `kind` and
    `source` since V2-714 and **`widget.js` read neither**, so «enséñame mis empresas» filtered the spoken
    answer and left the card showing everything — the two-surfaces-disagreeing failure this widget's own
    `prompt_digest` exists to prevent, arriving through the pushed view instead. And `link_contact` had
    existed **with no control behind it since V2-541**: «cuatro personas vinculadas a la misma empresa» was
    a sentence only the voice could say. Both have a door now, and the plug got one too
    (`show_connectors`) — a button with no name is a button the voice cannot press, which is the other half
    of his «que los botones funcionen, tanto si se hace clic como si el usuario los pide por voz».
  - ⚠️ **A click and a sentence are not the same filter**, and the first cut got it wrong: a rail click
    means «show me THIS» and replaces the whole selection, while «mi restaurante favorito en Barcelona» is
    group + city + favourites at once. A single-axis rail broke exactly that case, and an existing test
    caught it — the card holds every axis now and only a click clears the others.
  - ⚠️ **Two contacts tests and one testmap node were RED on a clean tree before this batch began**: the
    capability list went stale when V2-714 shipped three actions, `test_two_near_names_stay_a_refusal`
    measured a rule V2-705 deliberately changed (the tolerant matcher returns EVERY near match so the
    caller can ask «¿cuál?» — the property is «never exactly ONE», not «nothing»), and node **4.188 was
    duplicated** by V2-712 and V2-714. All three fixed here.
  - Node **4.190** (17 cases) plus the card and render nodes rewritten to the new contract (39 and 21);
    the list is capped at 120 rows with «ver más», because every one of his 2 688 rows used to become a DOM
    node on every keystroke of the search box. **Eighteen disarms, every mutation asserted before
    measuring, all red.** **NOT verified live**: the v1 → v2 migration has never been seen running over his
    own 2 688-row store, which is exactly why it is written row by row. Telegram, WhatsApp and MeshKore
    stay import-only and the card says so — none of the three exposes an address-book write API.

- **Todos sus contactos en un sitio: import-only, ocultables, y un grupo es un KIND (V2-714, 2026-09-16)**:
  sesión `c20123ab`. Quiso escribir a un contacto suyo de Telegram y no pudo: el directorio le ofreció OTRO
  Iván (el de Google, con su email), y al abrir la tarjeta de contactos vio «Google y Apple y otro. Pero no
  WhatsApp ni Telegram». Sus reglas, dadas después: «hacemos solo import, idealmente continuo; en local son
  editables y se pueden ocultar, se quedan mapeados, pero ya no se modifican más desde el conector» ·
  «debemos soportar grupos… y los combinamos con los clusters de MeshKore, que también son grupos pero de
  agentes» · «no me importa que el conector viva duplicado en varios widgets, eso le da claridad».
  · **Una fuente puede servir a varias FAMILIAS.** `telegram` y `whatsapp` eran `family: "mensajeria"` y la
  tira de Contactos filtraba por `"contactos"`: por eso no los veía. `family` sigue siendo un string —ninguna
  vista del motor cambia— y `families` es la lista; `registry.serves(d, fam)` es el ÚNICO lector, para que
  una tira y una pestaña de ajustes no puedan discrepar sobre si Telegram es una fuente de contactos.
  · **El TELÉFONO es la clave que funde tres libretas.** Un JID de WhatsApp *es* un teléfono, Google lo
  guarda y Telegram lo da para los contactos guardados — reducido a sus últimas nueve cifras (`phone_key`),
  porque nadie escribe el mismo número igual dos veces. Bajo nueve cifras devuelve `""`, que no casa con
  NADA en vez de casar con todo: fundir a dos desconocidos es lo que él no puede deshacer. El `notify` de
  WhatsApp —el apodo que se pone el OTRO— rellena un nombre vacío y **nunca** decide una identidad.
  · **Import-only, y eso SIMPLIFICA.** Sin push, sin `authoritative`, sin «el último que tocó gana»: ese es
  el contrato de Google (V2-699) y se queda solo para Google. Importación continua = DESCUBRIMIENTO continuo:
  cada pasada trae lo que no teníamos y **jamás** reescribe una fila que ya existe. Dos cosas sí se AÑADEN,
  porque son información nueva y no ediciones suyas: un CANAL nuevo (sin él, «escríbele a Iván por Telegram»
  se rompe el mes que Iván se abre Telegram, que es justo lo que esto arregla) y una PERTENENCIA a grupo.
  · **Ocultar conserva el mapeo, y ese es el motivo entero.** Borrar es local por fuerza —ninguna de las dos
  plataformas tiene API de escritura de libreta— y una fila borrada se queda sin mapa, así que la siguiente
  pasada la resucita y él tendría que ocultarla para siempre. `data.visible()` es el único lector de
  «hidden», para que la tarjeta, el digest del cerebro y el índice de voz no puedan discrepar.
  · **Un grupo es un KIND, no una etiqueta.** `data.py` avisa desde V2-523 de esa confusión: un `kind` dice
  lo que la entrada ES y una etiqueta dice cómo la archiva él. Un chat de Telegram, uno de WhatsApp y un
  cluster de MeshKore tienen identidad, tienen MIEMBROS, vienen de una plataforma y **se les puede escribir**
  — nada de lo cual tiene una etiqueta. `members` vive en el GRUPO porque ahí vive en las tres plataformas, y
  `parentId` no servía: da UN padre y una persona está en muchos grupos. Los miembros se funden como personas
  ANTES, con las mismas claves, así que el Iván del grupo es el Iván de su libreta. Un canal de difusión no
  enumera a nadie y lo DICE (`membersKnown: false`): una lista vacía que significa «no podemos saberlo» no
  puede parecerse a una que significa «nadie». Los clusters entran sin conector nuevo: el dato ya está en casa.
  · **WhatsApp no se puede preguntar «dámelos todos».** El bridge (Baileys, vendorizado) no escuchaba
  `contacts.upsert`/`contacts.update`; ahora los acumula y los sirve en `GET /contacts` marcados `partial`, y
  la tarjeta dice «lo conocido hasta ahora» en vez de un total que no podemos cumplir.
  Nodo 4.188. Doce desarmes, los doce rojos — **uno salió verde y acusó a mi test**: listar Telegram en la
  tira no era la propiedad (`_SOURCES` lo nombra igual), la propiedad era su ESTADO, porque filtrar por
  `family ==` deja un Telegram CONECTADO leyéndose como «aún no disponible».
  ⚠️ **Y la extracción volvió a pagar «mover código byte por byte cambia sus globals»**: el merge de Google
  salió de `data.py` a `gcontacts.py` para pagar el trinquete (926 LOC) y reventó con `NameError` en el
  primer sync real — allí `time` se importa como `_time` y `store`/`_touch` no existen.

- **El item que ÉL nombró llegaba a la basura, no al handler (V2-708, 2026-09-16)**: sesión `2fe99f15`,
  nueve turnos y una sola orden. Dijo «A dentist», «At five o'clock in the afternoon», «Thursday,
  seventeenth. Please delete that appointment» — y salieron **cinco `cancel_meeting {}` idénticos**, cada uno
  rechazado por la puerta de V2-705 por selector vacío y cada uno contestado leyéndole su propia agenda. La
  fila que pedía borrar, «Dentist (cita 2026-09-17 17:00)», **estaba en el menú que le recitó**. Su frase:
  «no veo ningún gramo de inteligencia… esto en un prompt a mi perro y sería capaz de ejecutarlo».
  · **La causa: `refs.resolve` nunca leía la referencia.** Su primera línea es
  `field = id_field_for_action(...)` y `if not field: return RefResult(True, payload)` — «nada que resolver»,
  con `ref` sin abrir. Y `field` era `None` porque esa función conocía solo dos formas de saber qué clave
  nombra una fila: un `"ref"` declarado, o la convención de V2-026 (clave terminada en `id`). `cancel_meeting`
  declara `title`/`date`.
  · **Y la ausencia de `ref` NO era un descuido.** V2-643 se lo quitó a propósito, y su test lo decía: `ref`
  era TAMBIÉN el interruptor del resolvedor POSICIONAL, y «la tercera» sobre un calendario que no numera nada
  cancelaría una cita que nadie nombró. Una sola declaración cargaba dos decisiones sin relación —QUÉ CLAVE
  nombra una fila, y SI contar filas significa algo— y el widget no podía tener la primera sin la segunda. Ese
  acoplamiento es el fallo real, y es el que se ha roto: `"positional": false` es ahora su propia declaración.
  · **La otra mitad del corte cierra la CLASE, no la ruta.** `id_field_for_action` lee también el `collections`
  que el manifiesto ya traía (`meetings.id == "title"`, doscientas líneas por encima de la acción que lo
  necesitaba), y solo para los verbos `via` que tocan una fila EXISTENTE — nunca `put`, que haría que
  `add_meeting` rechazara toda cita con título nuevo. V2-595 arregló una ruta (`youtube`); esto cierra el
  patrón. Precedente exacto de «arreglar una ruta no arregla la clase».
  · **Las dos mitades de la misma máquina contestaban distinto.** `contract.selector_for` decía `title` (tiene
  fallback a la primera clave del payload); `refs.id_field_for_action` decía `None` (no lo tiene). El hueco
  entre las dos es donde se perdía la referencia, y el propio docstring de V2-705 ya describía el síntoma
  («nothing between the model and the handler read that declaration») sin conectar el resolvedor. Ahora
  comparten el lector de «¿este selector es opcional?» y un test recorre el catálogo entero exigiendo que no
  discrepen.
  · **El scorer castigaba la precisión.** Dividía por la longitud de la REFERENCIA, así que cada palabra de más
  que él decía bajaba la puntuación de la fila correcta: «the Dentist appointment on Thursday the 17th» sacaba
  0.8 contra «Dentist» —bajo el suelo de 1.0, `no_match`— y «Dentist» a secas sacaba 3.0. Cuanto mejor la
  identificaba, menos resolvía. La cobertura se mide ahora **en los dos sentidos** y gana la mejor: una
  etiqueta que la frase contiene ENTERA es un acierto, por mucho contexto que venga con ella.
  · **Y si el modelo no nombra nada, se lee SU FRASE.** Último recurso, nunca por delante de `item`, y solo
  para ENCONTRAR una fila que ya existe. Antes se estrellaba contra el menú teniendo en la frase todo lo
  necesario, cinco veces. Se le quitan primero los días y los meses —clase cerrada, como `_ORDINALS`— porque
  en una frase «del jueves» FECHA la petición: medido, «avisos para todas las citas del jueves» puntuaba lo
  bastante alto la cita TITULADA «Jueves Santo» para ganar, y habría movido un aviso en vez de el día entero.
  · **Dos filas con la misma etiqueta son dos cosas distintas.** El atajo de coincidencia exacta devolvía la
  primera en silencio; con 29 filas tituladas «New» ese día, `cancel_meeting {"title": "New"}` resolvía a una
  de ellas sin preguntar. Ahora caen al scorer, que las empata, y el desempate pregunta con el `hint` que las
  distingue.
  · **Y el evento de la data-op ya dice qué `item` se nombró.** Cinco filas de «payload: {}» sin `item` en
  ninguna parte no pueden distinguir «el modelo no mandó nada» de «el resolvedor tiró lo que mandó», y se creyó
  la primera lectura durante una semana. Esa ausencia de observabilidad es lo que hizo que el diagnóstico
  costara siete días, no la complejidad del fallo.
  Nodo 4.186. Once desarmes, los once rojos, control verde antes y después — y **tres salieron verdes primero y
  acusaron a mis tests**: una guarda redundante (el desempate ya preguntaba, así que la rama se borró en vez de
  taparse con un test), una fila de fixture con fecha PASADA que `ref_index()` no publica, y una identidad
  (`contract._OPTIONAL_RE is refs._OPTIONAL_RE`) que no probaba que la PUERTA llamara al lector.

- **La puerta CUENTA, lo hecho es un HECHO, y una queja no es un encargo (V2-707 F6, 2026-09-16)**:
  sesión `080b96a7`, con el aviso del propio operador de que el servidor vivo era anterior a F0/F1/F2 —cierto:
  corría `3.27+60dbdb98` contra HEAD `d65e593c`—. Reiniciado primero, **los cuatro fallos se reprodujeron en
  HEAD**. Cuatro cortes, todos sobre la CONSECUENCIA:
  · **Enunciar el número no es compararlo.** Pidió «clean the three» y la puerta dijo «Voy a borrar **5** citas
  del 2026-09-17. Es permanente. ¿Las borro?»; su «Yes.» se llevó cinco filas. El número lo puso V2-693 a
  propósito, porque «una confirmación que no cuenta lo que se lleva por delante es una a la que se dice que sí
  sin mirar» — lo que faltaba es la RESTA. Tres y cinco no son una pregunta y su respuesta: son dos
  afirmaciones sobre el mismo acto, y un «sí» a una contradicción no autoriza nada. Ahora `confirm_gate.decide`
  mide las dos mitades —`nucleo/asked_count.named` lee el número que él dijo, `radius` el que dan los datos
  desde `sweep`/`rows.plan`, los MISMOS que ejecutan— y ante el desajuste lo dice con los dos números y los
  nombres, **sin registrar nada**. Igual para un radio de CERO, que antes abría una confirmación cuya
  «pregunta» era la frase «No hay ninguna cita que borrar en ese tramo». Lo delicado no era comparar: era no
  leer una FECHA como una cuenta («clean the 17th»), porque refusar ahí es el mismo fallo apuntando al otro
  lado — de ahí que solo cuenten las palabras de número en marco de conteo, y un dígito solo con su
  sustantivo contado.
  · **Lo ejecutado tiene que ser un hecho del turno.** Habían corrido dos `clear_range` (i=10545, i=10780) y el
  turno dijo «In this conversation I never confirmed a deletion, so nothing has been removed from your
  calendar». Era una deducción CORRECTA del único registro que llevaba el prompt: el de confirmaciones
  PENDIENTES. Nada le contaba lo EJECUTADO, así que razonó desde la ausencia de una confirmación hasta la
  ausencia de un acto y le dijo a su dueño que su calendario estaba intacto con nueve filas menos. `nucleo/
  done_ops.py` se escribe en el EMBUDO único (voz, botón, worker y cron caen en él) y solo cuando la op
  ocurrió —la misma regla que F0 puso en el sello anti-arrastre—, y llega al turno CON su instrucción (V2-453):
  la línea prohíbe por su nombre la frase que oyó.
  · **Una queja sobre lo ya hecho no es un encargo.** Sus tres quejas abrieron tres tareas de Brain Worker, cada
  una aparcada en la puerta de irreversibles y descartada, mientras se le abrían `navegador::t1` y
  `results::b8ed90-4` en el canvas y él pedía explicaciones («Do not open a fucking widget for this»). El
  arreglo es una RESTA en `danger.is_dangerous` —el clasificador que leen los TRES decisores, no el backstop,
  porque no pueden discrepar sobre qué es una orden— con la técnica que ese módulo ya usa dos veces: recortar
  la cláusula antes de buscar el verbo. La cláusula acaba en el siguiente `. ! ? ; ,`, **en la coma a
  propósito**, para que una queja que TERMINA en una orden conserve la orden. La queja que él citó (`delete`
  pelado) ya la cerraba F0 al juzgar «borrar» por su objeto; la CLASE seguía viva con los demás verbos
  («Why did you buy that? I never asked you to.» = `True` en HEAD).
  · **Las frases del confirm-gate no pasaban por la tabla de idioma.** Treinta segundos después de «Do not speak
  Spanish» oyó «Voy a borrar 5 citas…», «No hay ninguna cita que borrar…» y «¿Vacío la agenda entera?».
  Ninguna es un `notify`/`say` ni una asignación a un campo hablado: son RETURN, **la única forma que el
  trinquete de prosa de V2-682 no ve**, y por eso el escape llevaba un mes invisible. 23 campos nuevos en
  `i18n/langs.py` con su mitad inglesa —la frase del barrido en PIEZAS, porque el tramo, lo conservado y el
  plural los decide el dato y un idioma que los ordene distinto tiene que poder decirlo—, y el `confirm_q` del
  MANIFIESTO (donde van los carriles de un widget) se busca primero en el bundle,
  `widgets.<id>.confirm.<acción>`, igual que V2-694 con los nombres: 18 claves × 2 idiomas, con un test que
  exige la clave para TODA acción `confirm:true` de todo widget enviado.
  · Enseñarle al trinquete a mirar los `return` encuentra **415 frases en 100 ficheros** y muchas son para el
  MODELO (V2-652), así que no cabía en la tanda: en su lugar, un test por fichero sobre `confirm_gate.py`.
  **Queda abierto como clase.**
  · Bajo el trinquete de arquitectura: `i18n/phrasebooks.py` (los libros de frases, DATO puro leído en un solo
  sitio, byte por byte — 911 → 824) y la narración de `_request_cluster_confirm` condensada, porque
  `providers/nucleo.py` estaba clavado EXACTAMENTE en 3043.
  · ⚠️ **Dos desarmes salieron VERDES y acusaron a mis tests**: uno usaba `cancel_meeting {}`, que el contrato
  de V2-705 rechaza ANTES del embudo, así que nunca llegaba a la línea desarmada; el otro medía una frontera de
  coma con una frase que no casaba ninguna cláusula en pasado. Los dos cerrados con casos que sí la ejercen.
  10 desarmes, los 10 rojos, control verde antes y después. Nodos 2.64, 2.65, 4.185.

- **El círculo se cierra solo: la reunión del jueves, de punta a punta (V2-705, 2026-09-15 noche)**:
  el operador pidió una última prueba conducida por él como usuario —«dile que se olvide del resto de reuniones,
  empezamos de cero, una para el jueves a las 5»— y que se verificara que el sistema es autónomo «independientemente
  de si contesto rápido o al cabo de una hora». **Se cerró**: mensaje enviado por Telegram, respuesta «Ok», y en
  **20 s** el encargo despertó, escribió la cita del 2026-09-17 17:00 en el Google Calendar real, acuñó el enlace de
  Meet y lo devolvió al contacto. El «empezamos de cero» se aplicó también por dentro sin pedirlo: el encargo nuevo
  desalojó al del viernes vía `claim()` y lo cerró con motivo. Cuatro fallos medidos y cerrados por el camino, cada
  uno en su puerta y no en su caso:
  · **Un sinónimo no es un campo que falta.** El primer intento NO envió nada: el modelo puso `message` donde el
  manifiesto declara `text` y la puerta lo rechazó. `widgets/contract.fold_aliases` renombra al manifiesto en el
  EMBUDO ÚNICO (`server_api._dispatch`), antes del guarda destructivo — así una cancelación que nombra su objetivo
  como `name` es una cancelación NOMBRADA, no un selector vacío. Se niega a adivinar: la clave destino debe estar
  DECLARADA, debe llegar vacía, y el sinónimo no puede estar declarado también en esa acción.
  · **Un playbook no nombra empresas.** El vocabulario ampliado la tanda anterior metió «google meet» en las
  palabras de match, y el test de doctrina del propio repo lo cazó (`test_nothing_in_a_playbook_names_a_person_or_a_company`).
  `«meet link»` sola cubre «Google Meet link» sin saber quién lo fabrica. Dos ficheros iban ROJOS desde `7a91a59a`.
  · **La voz propia de un encargo no abre otro encargo.** La red de autonomía leyó la confirmación que el propio
  encargo acababa de enviar («Here's the Google Meet link») como una propuesta nueva, abrió un SEGUNDO encargo y
  `claim()` le quitó la conversación al primero. Cerró inofensivo solo porque la cita ya existía; un pulso antes
  habría robado el hilo a un encargo VIVO — justo el fallo para el que se escribió `claim` en V2-692. El remitente
  se lee del `ref` que estampa `wake._send` («<id>:<epoch>») preguntándole al STORE si ese id es un encargo real,
  nunca fiándose de la forma de una cadena.
  · **El manejador de métricas de voz no IMPORTABA.** La extracción del 2026-09-10 se llevó `from ..core.logging
  import logger` «por paridad» a un módulo donde ese nombre no existe: cinco días sin líneas de métrica, sin
  latencia STT/TTS remota y sin informes de consumo, con un `ERROR` por turno. El guarda que cubre el fichero lo
  lee como TEXTO y siguió verde todo el tiempo — **leer un fichero no es ejecutarlo**.
  **Y el diagnóstico que costó más que los cuatro:** el encargo se armaba bien y nunca se ejecutaba porque el
  **interruptor ⏻ estaba apagado** desde las 18:07 (`{"state":"stopped","src":"operator"}`, puesto por él tras el
  borrado de la agenda). `runstate.blocks_new_work()` falla CERRADO y corta en `watch._fire_wakes` *antes* de
  consumir la cola —«aplazar, no perder», V2-684— sin dejar rastro en INFO. Un encargo parado con la respuesta ya
  en el hilo: mirar el ⏻ antes que el código. El guardarraíl también se probó solo en vivo: el contacto pidió
  «cancel the meet and appointment» por Telegram y **no movió nada** — un tercero no manda en el calendario del
  operador.

- **La pirámide: UNA decisión por turno, y ninguna acción destructiva sin selector (V2-705, 2026-09-15)**:
  el operador paró la sesión: «cada corrección al final no suma; arreglamos una cosa y estropeamos otra… debería
  funcionar de forma piramidal». Detonante medido (sesión 878b0122, 18:03): pidió «quita la cita de mañana a las
  siete» y el cerebro llamó `agenda.cancel_meeting` con `payload {}`; el handler leyó «sin título y sin fecha»
  como «todas» y mandó **147 DELETE al Google Calendar real en 60 s, 100 aceptados**. Y una sola orden la
  ejecutaron DOS veces: el cerebro rápido (data-op local) y, tras él, un worker que el Susurro lanzó para
  «cancelarla de verdad en la fuente externa» — porque tres prompts decían que los widgets son ESPEJOS mientras
  el código dice que la agenda ES el calendario. Antes: «escríbele a X y concierta» fue a un worker de shell 6
  minutos con 0 mensajes, porque el selector de tools podó `messaging` (ni «write» ni «contact» son semillas).
  **Tres niveles, todos genéricos.**
  **(0) Invariantes en CÓDIGO** (`widgets/contract.py`, en `server_api._dispatch`, la única puerta de cerebro,
  worker, botón y cron): una acción destructiva cuyo selector declarado llega vacío se RECHAZA con el menú del
  widget, nunca se ensancha a «todas»; reproducido sobre 14 días, rechaza SOLO las 3 llamadas que vaciaron el
  calendario. `cancel_meeting` cancela UNA (título ambiguo = pregunta; duplicados idénticos juntos). `store.save`
  guarda un snapshot de lo que sobrescribe.
  **(1) UNA doctrina**: un widget con conector ES la fuente, dicho igual por la tool de escalado, `widget_data`,
  el método del worker y el Susurro (que deja de tratar un data-op como riesgo). Escribir a una persona deja de
  ser escalada.
  **(2) Routing por ESTADO** (`nucleo/flash/addressed.py`): un turno que NOMBRA a un contacto del directorio
  fuerza la familia `messaging` — el dato durable de «escríbele a X» es X, no el verbo. **El arnés del encargo de
  reunión no estaba roto** (`errands/verify.py` ya lee la agenda y contempla el Meet pendiente); lo que estaba
  roto era que el encargo no arrancaba por ir al camino equivocado. Pendiente: Nivel 3 (dieta de prompt).
  Commits `dbc84b88`/`3aa1138f`/`e38bebdf`.

- **Una pregunta se contesta desde el REGISTRO, y una orden sin marco no es ruido (V2-704, 2026-09-15)**:
  una prueba manual que debía ser trivial —contactar con alguien, concertar la reunión, mandar el Meet— no llegó
  a empezar. «Hay algo de fondo que no funciona», y lo había.
  **El lector de widgets tenía un parámetro `question` decorativo.** `read_widget` llamaba a `read(wid)` con solo
  el id, así que devolvía el mismo `prompt_digest` preguntases lo que preguntases — y un digest es el resumen
  SIEMPRE-ACTIVO de la tarjeta: primera página y sin identificadores personales, las dos cosas correctas para lo
  que es y letales en cuanto se le entrega a alguien que ha preguntado. Medido: cuatro llamadas pidiendo el
  Telegram de un contacto, cuatro veces los mismos 910 caracteres (15 filas de 2.686, plataformas sin handles), y
  la respuesta «no hay handle de Telegram guardado» con `@cryptonite_fund` en la fila. No alucinó: el bloque
  afirma en su primera línea que «lo que no esté aquí NO está guardado». Por widget: contactos 15 de 2.686,
  agenda truncada y solo hacia delante, **mensajería 0 caracteres** con diez mensajes dentro.
  **La costura es `read_query(question)`** en el `data.py` de cualquier widget, hermana de `prompt_digest`, y el
  lector la busca por contrato sin nombrar a ninguno. Contactos contesta a través de `directory.resolve` —la
  MISMA puerta que usa el envío, así que lo que el cerebro dice de quién es alguien y lo que la puerta de
  mensajes hace con esa persona ya no pueden ser dos respuestas—; la agenda busca el calendario entero y colapsa
  las citas idénticas diciendo cuántas copias hay (así salieron 15 de «renovar el seguro» y 11 de «Dentist»); la
  mensajería publica por fin las dos costuras.
  **Y un RESUMEN ya no puede leerse como una negación.** El prompt de la segunda pasada dice cuál de las dos
  cosas tiene delante: con una ficha resuelta, una ausencia es real; con el resumen, una ausencia es «no lo he
  podido ver», NUNCA «no está guardado» — e ignora la línea del propio bloque que se declare completo mientras
  también diga que hay más entradas. Esto protege a todo widget cuyo digest pueda truncar, no solo al que falló.
  **Sin marco de diálogo no hay veredicto.** A las 14:23 dijo «Contact» y «Contact to the kryptonite» y las dos
  se tiraron como ruido de sala: había reconectado a una sesión parada 1.014 s, la ventana estaba fría y el
  cerebro aún no había hablado, así que el juez de atención recibió `context=""`. La única fuerza MEDIDA de ese
  juez es el marco —su propia nota registra que presentar la última frase como «Zaelar acaba de decir …» voltea
  «¿me estás escuchando?» de ambiente a dirigido, 3/3—, o sea que sin él no se le está haciendo la pregunta que
  se midió y su veredicto no puede descartar nada. La exposición dura hasta que el asistente habla una vez, y ya
  la tenía tasada el módulo: «ante la duda, marca DIRIGIDO».
  **El nombre de la pieza, en el idioma del operador**: `widget_read.title()` leía el manifest (castellano en
  todos), así que una sesión en inglés oía «Let me check Contactos…» y la segunda pasada leía «el widget
  "Contactos"». Pasa por `registry.display_name`, que resuelve V2-694 y cae al manifest para un widget que los
  bundles no conozcan.
  **Y la observabilidad, que es lo que costó el diagnóstico:** la lectura lleva `answered` (¿registro o primera
  página?) y el veredicto de atención lleva `warm` y `framed`. En modo `always` `window_open()` es `True`
  permanentemente —el micrófono ES la ventana—, así que un turno descartado se registraba con `window_open: true`
  al lado y el log se contradecía solo. **Un desarme encontró un agujero antes de que el test existiera**: poner
  `direct = ""` en `prepare` no ponía nada rojo — todos los casos por widget podían estar verdes mientras el
  cableado tiraba la consulta al suelo, que es justo lo que llevaba pasando. Trinquete pagado extrayendo
  `widgets/contactos/lookup.py` (941 → 819).

- **Una lista de resultados TIENE formato, y todo resultado tiene puerta a su ficha original (V2-702,
  2026-09-15)**: el operador buscó una olla, la búsqueda acertó, y se la enseñamos mal. Cuatro defectos de
  GEOMETRÍA medidos renderizando su hoja real, ninguno visible desde el fuente.
  **La foto se veía al 19 %.** `.hr-img` era `width:100%;height:128px;object-fit:cover`, o sea que el aspecto
  de la caja salía del ANCHO DE LA TARJETA y de una constante — y la hoja se redimensiona y se maximiza. En su
  pantalla: caja 1142×168 (6,8:1) para una foto de 320×251 (1,27:1); `cover` la escala a 1142×896 y sobreviven
  168 filas. «Estas fotos horizontales no sirven para nada porque no se ve absolutamente nada.» `cover` solo es
  seguro cuando la caja se parece a la foto, y aquí nunca se parece: las fotos vienen de la tienda donde haya
  caído la búsqueda. Ahora el aspecto lo fija el FORMATO y la imagen va contenida.
  **El enlace faltaba justo donde más falta hacía.** La tarjeta se volvía `<a>` solo si `url && !hasDetail`, así
  que los resultados con valoración, ficha y fotos —los que merece la pena abrir— eran exactamente los que
  perdían su enlace. Su item llevaba la url de Amazon y la lista renderizada tenía CERO anclas. El motivo
  original era bueno (no se anidan enlaces dentro de un `<a>`) y la conclusión era la mala: había que sacar la
  url del `<a>`, no tirarla. La otra mitad tampoco la puede arreglar el widget — el ejemplo de `present` del
  manifest, que es lo que un modelo copia, no llevaba `url`, y `presentation.audit` no mencionaba el campo.
  **«Ver detalle» no estaba muerto: el canvas no escuchaba.** `widgets/store.py::save()` avisaba con la clave de
  DISCO (`results--t1`, porque un directorio solo admite `[A-Za-z0-9_-]`) y el canvas indexa sus tarjetas por la
  de CANVAS (`results::t1`), así que `refreshData` buscaba una ventana inexistente y se volvía callando. Se caía
  al suelo TODO empujón de datos a una hoja instanciada — el `present` y el `append` de un worker incluidos; solo
  llegaban los tics de progreso, que salen por `sheets.py` con el id bueno. En la línea de tiempo del incidente:
  167 eventos con `::` contra 16 con `--`, y solo los 167 movieron un píxel. Arreglado en el único punto por el
  que pasa todo, y el botón además pinta LOCAL y persiste después, como las pestañas desde V2-538.
  **Cuatro formatos de lista preseteados** (`split` foto-izquierda · `gallery` · `rows` · `compare`) elegidos por
  la superficie. La costura para adaptarse al tipo de artículo es `kind` —qué SON los resultados—, nunca un
  nombre de formato: `presentation.py` regla 1 existe porque un `columns:2` adivinado desde fuera dejó tres
  tarjetas ricas con una huérfana. Un test guarda esa frontera y ya sirvió: el primer borrador llamaba `media` al
  formato de foto a la izquierda y `media` ya era un TIPO (audio, vídeo) — dos significados en una palabra dentro
  del mismo fichero, donde el viejo gana y el nuevo se rompe callado.
  **Y la pestaña de Sumario llevaba muerta desde V2-694**: `paintSummary` llamaba a `tallyLabel(k)` con una `k`
  que no existe en ese ámbito, copiada de `paintHarvest`. Lanzaba `ReferenceError` fuera de `render`, o sea que
  la hoja ENTERA moría al activar Sumario. El e2e lo arrastraba como ERROR de fixture, no como fallo, y por eso
  se leía como arnés roto y no como widget roto.
  **La lección del arnés, que costó una pasada:** la primera versión del test de la foto comparaba el
  `getBoundingClientRect()` del `<img>` con el aspecto natural, y el desarme salió VERDE — devolver la banda no
  lo puso rojo. El rectángulo de un `<img>` es su caja de MAQUETACIÓN; con `object-fit` los píxeles se pintan
  fuera de ella y lo que se ve es lo que sobrevive al recorte del padre. La medida honesta es la FRACCIÓN de la
  foto que llega al cristal, y vale sea cual sea el mecanismo CSS. Trinquete pagado extrayendo
  `widgets/results/record.py` (1006 → 818).

- **A results LIST is a list, and the templates are the worker's to choose (V2-703, 2026-09-15)**: the day
  after V2-702 made a result look like a result, he sent the same sheet back: «los resultados aparecen en una
  línea horizontal y cada cosa en su sitio. Son cajitas bien puestas, plantilladas […] el botón de ver en
  Amazon es el que aparece en la ficha […] en las listas de resultados puede haber menos datos para que quepan
  más resultados. Si un resultado solo ya ocupa toda la pantalla, ¿de qué me sirve la lista de resultados y
  tener acceso a la ficha? Lo que queremos es los datos principales, la foto y un botón para entrar en la ficha
  ampliada. Ni siquiera el botón de ver en Amazon en la propia lista.»
  **The list gave up three things and got a formation back.** The spec table (four `facts` rows, each a full
  sentence) and the outbound link both belong to the RECORD; the list row offers one way forward, which is to
  open it. And the featured result is now MARKED, not INFLATED: `primary.length === 1 ? 1 : 2` drew his only
  result across the whole sheet, and a second clamp held the rest to two columns so the featured one still
  looked bigger. Both gone, one grid, the featured card first. Cards stretch to their row and the footer is
  pushed to the bottom of each, so the «Ver detalle» buttons line up; every text field has a line budget.
  **The templates are now the WORKER's to name** — `layout`: card | tile | row | compare — which is a
  deliberate amendment to `presentation.py` rule 1 («the surface owns the layout»), by his decision: «esto no
  es una página web, esto es un sistema dinámico e inteligente que tiene que soportar cualquier tipo de
  resultado, tanto si buscamos barcos como cafeteras, como recetas, como eventos históricos de la Primera
  Guerra Mundial». A boat puts its length where a recipe puts its time, and no heuristic here can know that.
  The rule's REASON survives as a guard rather than a veto: a NAME, never a number; an impossible choice (a
  photo template over results with no photos) falls back; an invented one is refused at `data.py`, where the
  closed vocabulary lives. `columns` stays forbidden — that one really is geometry.
  **Three measurement lessons, all paid in this batch.** (1) The width floor still came from the `rich`/
  `medium` heuristic, which counts `facts`, `blocks` and `images` — none of which the list draws any more, so
  it was sizing a card that is not on screen. Same defect class as V2-702's photo band, one level up. (2)
  Counting the badge in the DOM said nothing about whether it is ON SCREEN: clipping it with a max-height
  leaves the element exactly where it was, and the disarm came back GREEN with the badge outside its box.
  It is now measured against the rectangle that clips it. (3) The layout DECISION had to be written down
  (`data-layout` on the grid): `makeCard` degrades each card on its own, so the drawing looks right whether
  the guard ran or not, and the disarm was green for that reason too.
  ⚠️ **One V2-702 assertion was moved, not deleted.** It read «the link is on the CARD», written against a
  list containing zero anchors. It now reads «the link always REACHES the operator», with the list asserted
  empty and the record asserted to carry it. Pinning a button's LOCATION instead of the guarantee is what made
  a test contradict him a day later.
  ⚠️ **An injected stylesheet fails SILENTLY, and it cost three separate rounds here.** A comment paragraph
  landed outside an already-closed comment, so prose was parsed as declarations and the parser ate the rules
  after it — `node --check` green, `-webkit-line-clamp` declared and inert, titles four lines tall. The only
  way it was found was reading the COMPUTED style back. Reading back a property you just set is how you learn
  it never arrived. 14 disarms, all red. Testmap **4.179**.

- **A sync that STAYS ON, and stays a mirror (V2-701, 2026-09-15)**: after a one-off pass brought 2 685
  people in, he said «el tema de la sincronización de contactos no es algo que deberíamos hacer de forma
  puntual, deberíamos realmente marcar un botón de sincronización y eso debería quedarse conectado de forma
  permanente», and then defined what he means by synced: «se modifica en un sitio o en otro, todo se
  sincroniza linealmente y es un espejo […] si eso está conectado a un teléfono y se modifica en el
  teléfono, todo el sistema se sincronizará.»
  **The control is a SWITCH, because a button is a one-off by its grammar** whatever its label says — a
  primary «Sincronizar contactos» teaches that syncing is an errand you run. `sync.auto` is the state,
  `set_auto` writes it (declared, so voice reaches it), and `widgets/background.py` calls `data.tick` on
  the manifest's cycle. Doing it by hand survives as a quiet secondary. Written into the header standard.
  **Three things had to become true for «permanente» to be honest, and each was a real defect waiting.**
  (1) **A pass had to be cheap enough to repeat**: 2 685 contacts is six pages, and a full re-read every
  minute is a request budget spent to learn that nothing happened. `list_people` now carries Google's SYNC
  TOKEN, so a quiet minute is ONE round-trip — and the token is also what tells the merge that a row is one
  Google CHANGED. Two of Google's rules are load-bearing and easy to break by editing one branch:
  `sortOrder` may not be combined with a sync request, and «all other request parameters must match the
  first call», so there is exactly ONE parameter set rather than a full one and an incremental one that can
  drift. A TRUNCATED read throws its token away: a pass that stopped at `max_pages` never saw the last
  pages, and a token stamped there makes everything it skipped invisible forever while the card honestly
  reports «sin cambios» about a question it never asked.
  (2) **The push had to know what it had already sent.** The old test was a DATE — `updated` is
  `YYYY-MM-DD`, so «edited today» stays true until midnight. Harmless for a button pressed now and then;
  **on a timer it is a PATCH per edited contact per minute, and nobody would ever have seen it**, because
  every one of those writes succeeds and writes the same values. Now a local write stamps `touchedAt`, a
  successful push stamps `pushedAt`, and «ours» is one comparison of two clocks; legacy rows fall back to
  the date rule ONCE and the push that follows moves them onto the precise path. The mirror image of the
  same trap: an import filling in a blank must NOT stamp `touchedAt`, or the next pass sends Google its own
  value straight back, forever.
  (3) **A mirror reflects deletions or it is not a mirror.** Google→here arrives through the token as a
  person carrying `metadata.deleted` and nothing else — no name, no email — so handing it to the shaper
  returns None and the deletion vanishes silently; `list_people` separates them out. Here→Google cannot ride
  a pull at all (once the row is gone there is nothing left to compare), so `remove_contact` queues the
  `googleId` in `sync.pendingDeletes` and the next push spends it — cleared only on a pass that actually
  reached Google, or a refused push would lose the deletion and the next full read would resurrect the row.
  A row he edited since we last sent it is **not Google's to delete**: he touched it last, the same rule
  that decides every other conflict, applied to the direction that cannot be undone.
  **And a circuit breaker around our own code**: the failure mode of a sync token gone wrong is «everything
  looks deleted», so a pass may never remove more than 20 % of the address book (min 25 rows). When it
  trips, nothing is removed and the card SAYS SO — a guard that protects silently is one he cannot trust.
  Also settled here: a row that reached us through a token, with nothing pending locally, lets GOOGLE win
  instead of only filling a blank. That is what makes his phone edit land. A full re-read is never
  authoritative — there «changed» is unknown, and treating every row as fresh undoes his corrections
  wholesale. 12 disarms, all red. Testmap **5.29**.
  ⚠️ **Paid twice in one session**: a backtick inside the injected `<style>` template literal (`node
  --check` green, module dead at runtime — V2-689's trap, already documented), and `.ctlink` redefined when
  the sheet already used it for «jump to a linked contact», so the later rule won silently.

- **Connecting an account opens a POPUP, and the card notices in real time (V2-700, 2026-09-15)**: he
  linked Google Contacts and reported two things — «se ha abierto en una pestaña nueva en lugar de en un
  pop-up […] no me ha gustado en la versión desktop que se me cambie de pestaña», and the bigger one:
  «cuando volvemos a la pantalla […] ya automáticamente desaparece la opción de conectar y se marca como
  conectado. Eso sigue sin suceder y se tiene que estar detectando en tiempo real. Si no, el usuario está
  confundido y podría volver a iniciar indefinidamente la conexión.»
  **MEASURED: five widgets had five hand-rolled copies of «open a window and hope», and they had drifted
  into two behaviours** — the agenda passed a features string (a popup), contacts and youtube passed
  `"_blank"` (a tab). `fotos` was worse: it called `window.open` AFTER the `await`, under a comment
  claiming it did the opposite, which is the silently-blocked-popup class V2-603 already paid for. And all
  five shared the real defect: **the callback page told the OPERATOR it had worked and told the CARD
  nothing.** The reason is exact and worth keeping: a widget's own store goes through
  `widgets/store.py::save`, which emits ONE `widget/data` event that makes the open card re-fetch itself —
  which is why the messaging card notices a Telegram QR being scanned **with no polling anywhere**. OAuth
  tokens live in a `SecureJsonStore`, which emits nothing, so linking an account changed nothing the canvas
  could see. Delivered: **`ctx.connect(...)` on the canvas** — it opens the window inside the click, with
  features on the desktop and without on a narrow screen, and then watches three independent signals (the
  callback page's `postMessage` to its opener; the new `widget/data` announcement from the server; a
  bounded poll for a window that was never ours, like a mobile tab with no opener). ⚠️ **None of the three
  is BELIEVED** — every one ends in `refreshData`, which re-reads state from the engine, which is what
  makes accepting the message loosely safe (a forged one buys a refresh and nothing more) and what stops a
  card painting «conectado» over an account that is not. One shared callback page
  (`connectors/oauth_callback.py`) replaces the five copies, and `announce()` fires on disconnect too,
  because a card that goes on saying «conectado» is the same lie in reverse. Six widgets converted
  (contactos, agenda, fotos, youtube, archivos, musica) and a ratchet —
  `test_no_widget_hand_rolls_its_own_consent_window` — fails the suite on a `window.open("")` inside any
  `widget.js`, so the seventh connector cannot re-invent it. Eleven disarms, all red. **Not verified live:
  no real consent has travelled the new path yet.**

- **A contact card looks like a CONTACT CARD, the header is the house's, and Google Contacts is a
  connector like any other (V2-699, 2026-09-15)**: he opened the card for his only contact — Cryptonite,
  whom he messages on Telegram every day — and reported that it showed «que es una persona» and nothing
  else: «no está estructurado, no muestra ni siquiera los campos básicos, aunque sean vacíos… no está
  tampoco la cuenta de Telegram, que es lo único que tenemos de ese contacto», plus «un menú ahí suelto que
  no está bien diferenciado del resto». He asked whether a restart would fix it.
  **It would not, and the measurement is the whole story: the Telegram account WAS stored** — handle,
  chatId, marked preferred — and `view_data` shipped the entire record to the browser. `renderDetail`
  painted five fixed rows and `row()` returned early on an empty value, so a contact whose only datum is a
  channel painted a name, the word «PERSON», and nothing more. **The same family as V2-697's `eventsOf`,
  two days earlier**: the store and the card each correct on their own, which is exactly why a source scan
  does not find it. Delivered: every basic field present even when empty and editable in place (with
  `clear`, because `update_contact` ignores `""` on purpose so a model cannot wipe a field it did not hear);
  «Cómo contactar» listing all three platforms always, with the ★ of the preferred one — and **mirroring
  `directory.py`'s written asymmetry, a stored phone still never becomes a WhatsApp**; a real sidebar; the
  duplicated ★ chip gone.
  **Then he reframed it mid-build, and the second half is the bigger one**: «esto es un sistema operativo,
  con lo cual esas barras ya tienen un formato estándar y nos llevan al sistema de conectores». So the
  widget now wears the agenda's two bars verbatim — brand disc + 14/600 content title, then the band with
  the provider icons (Google lit, iCloud and CardDAV visible and INERT) and the plug button opening a
  connectors SCREEN, not an overlay. **The sidebar's «Importar de Google» was removed**: importing is a
  connector gesture, and a second door to it is a second vocabulary for one idea. The standard is now a
  rule with a checklist, `zaelar-widget-header-standard.md`, so the next widget does not re-invent it.
  **He also overruled the one-way import, and his reason beat the objection**: Google Calendar is already
  two-way in the agenda, so a one-way contacts connector would be the odd one out in his own product. «Who
  wins» turned out to be answerable — **whoever touched the row last**, which `updated` has recorded since
  V2-541 — so the sync PUSHES his newer rows and then PULLS, in that order (pulling first would fetch a
  stale row, merge it, and push the result back, laundering a stale value into a fresh one), and the pull
  never overwrites a non-empty local field. Two People API traps, both already paid for elsewhere: an
  update needs the person's `etag` (read-modify-write, V2-697's RSVP shape) and `updatePersonFields` is a
  whitelist where **anything listed is REPLACED**, so a constant mask would delete on Google every field
  that happens to be empty here. **NOT done and said out loud:** the `sync` tier needs
  `.../auth/contacts` declared on the OAuth app — until then the card says «solo puedo traer» instead of
  promising what Google would refuse; there is no live link yet (the People API has no push for a personal
  account, so it would be a `syncToken` poll); and nothing here has been verified against a real Google
  address book. **Session incident:** `tests/run_testmap.py` with no arguments RUNS the whole map — it is
  the forbidden broad sweep under another name, and `CLAUDE.md` was RECOMMENDING it as the answer to
  «¿funciona todo bien?». Killed within a minute; the contradiction is now fixed in both places.

- **An appointment says WHO convened it, and one that somebody else ASKS for waits for the operator
  (V2-697, 2026-09-15)**: he opened the detail card for a real invitation — an intro convened by somebody at
  zerohash — and put it beside Google's own popover for the same event. Ours showed a title, a date, one bare
  address and a chip reading «Confirmed». Google's showed the Meet link, both guests with their answers, who
  organized it, and buttons to say whether he was going. His priorities, verbatim: **«sobre todo el enlace, el
  enlace a Google Meet, que es lo que más me importa, y nosotros no exponemos eso»** · «quién me ha convocado.
  Porque a veces nosotros somos los que insertamos el ítem en la agenda, pero a veces es una invitación
  externa que nosotros aceptamos». And what he explicitly did NOT want: the phone bridge, the PIN, «more
  phone numbers» — «cosas que yo considero que son extras y absurdas» — nor proposing another time.
  - **MEASURED before writing a line, and it reframed the whole batch: the data was already there.**
    `connectors/calendar/google_calendar.py::event_to_meeting` has written `meetLink`, `organizer` and
    `location` since the first import; `widget.js::eventsOf` simply never COPIED them into the object the
    detail card reads. Connector and card were each individually correct, which is exactly why a source scan
    does not find this — and why every case for it is RENDERED.
  - ⚠️ **The chip was not merely missing information, it was MISLABELLED.** On a Google row `status` held the
    OPERATOR's own `responseStatus` while the card said «sin confirmar por la otra parte», so an invitation he
    had accepted read as though THEY had agreed — and on a locally dictated meeting the same field genuinely
    did mean the other party. **One field, two meanings, decided by provenance.** Split: `status` is about the
    other guests, `myRsvp` is his own answer, and both are shown. A guest whose answer Google does not report
    leaves it **pending** on purpose — not knowing is not being confirmed.
  - **`attendees` deliberately did NOT change shape.** Seven callers already read it as `list[str]` — the
    voice payloads, the errand booker, the digest line, and the write direction that rebuilds Google bodies
    from it — so the rich roster (`{name, email, rsvp, organizer}`) rides ALONGSIDE it under `guests`, written
    from the same list in the same pass so the two cannot drift. Changing seven consumers to gain what a
    second key gives free is a blast radius bought for nothing.
  - ⚠️ **An RSVP is a READ-MODIFY-WRITE, and that is not belt-and-braces**: in the Google API `attendees` is an
    array and **a PATCH carrying an array REPLACES it**, so answering by sending only our own row would delete
    every other guest from the organizer's meeting — a silent, destructive 200. `service.rsvp` reads the live
    roster back, edits OUR row alone (located by `selfEmail`, captured at import), and sends the whole list up
    again. It deliberately does not reuse `patch_event`, which would rebuild the entire body from
    `meeting_to_event` on an event we are a guest of and do not own. No new scope: the connector already holds
    `auth/calendar`.
  - ⚠️ **`meetLink` is attacker-controlled** — anybody who can send an invitation writes `conferenceData`, and
    the card turns that string into an `href`. Only `http`/`https` survive the import, and the widget refuses
    it again at the sink for rows stored before the guard existed. Only a **video** entry point is ever stored,
    so the dial-in he called absurd cannot reach the card even by accident.
  - **The second half — a cita can be born outside the operator.** An inbound message ALREADY became a
    calendar entry (`errands/wake` → `book.book()`); what was missing is the branch where the errand has no
    mandate to schedule: `may_schedule()` returned False and `book()` **returned**, so the other person had
    agreed, the slot was in hand, and nobody was told. **Refusing to WRITE is right; refusing to ASK is not.**
    The slot is parked ON THE ERRAND ROW — already durable, already expiring, already on his board, and
    already holding the binding to the conversation the answer must travel back to — announced through
    `brain_notes`, and offered on the agenda as a band that is deliberately NOT styled like an appointment,
    because a row that looks like an entry is already making the claim. **Telegram and WhatsApp inherit it
    with no code of their own; email is out by his own call** (a Gmail invite already lands in Calendar, so
    treating it as a proposal would make the appointment twice).
  - **The authorization criterion, and why «always manual» is not provisional.** He asked for the obvious
    guard and floated an allowlist of authorized contacts. **A list like that would be worse than none
    today**: a cluster peer's `handle` is SELF-DECLARED (`security.neutralize_identity` sanitizes the string,
    it does not prove it), a cryptographic identity exists only for US (`identity.did_key`), and the allowlist
    that does exist is per-CLUSTER, not per-person. So the name on a proposal is **a label he reads, never a
    credential**; every proposal needs his explicit yes; **his yes IS the grant** (`accept` adds `schedule` to
    the errand's mandate and calls the same `book.book()`, so nothing re-implements booking); and peer text
    stays fenced DATA. The seam for auto-accept is left and the auto-accept is not built — it should not be
    until a peer identity is something we can verify.
  - `verify.meeting_exists` returns False while a proposal is parked, the `link_owed` shape one field over:
    nothing is in the calendar, so a neighbouring meeting must not close the errand — and closing RELEASES the
    conversation, leaving the person who asked waiting for an answer nobody will send.
  - Nodes **4.175** (16 RENDERED), **3.50** (9) and **5.26** (7); the connector's own node grew 6. **Ten
    disarms, every mutation asserted, all red** — the one that matters most turned 8 cases red at once: it
    removed the field copy in `eventsOf`, which is the defect the operator photographed. One pre-existing test
    pinned the OLD mixed-up `status` semantics and was **rewritten to the new contract with its claim intact**
    (his unanswered invitation is still visible, now as `myRsvp`) plus a counterweight proving `status` still
    moves — never relaxed.
  - **NOT built, and named**: `cluster.propose` — `bridge.py::_CLUSTER_TURN_ALLOWED` still admits only
    `send`/`done`/`pact`, so a peer turn has no verb that reaches this path and it is messaging-only for now.
    **NOT verified live**: no real invitation has been answered and no real proposal has travelled the path.
    Criterion and mechanism: `.meshkore/docs/modules/zaelar-appointment-proposals.md`.

- **A messaging errand runs in the BACKGROUND — no browser card, no sheet, and the name as he says it
  (V2-698, 2026-09-15)**: the operator's own test, read event by event before touching anything: «Coge
  nuestro contacto Kryptonite y propone una reunión mañana a las 19 horas…». **The cycle CLOSED on its own at
  00:47:39** — the contact answered «Yes, works», the errand booked `Meeting with Cryptonite` 16/09 19:00 on
  Google with a `meetLink` and sent it — and what he saw on the way was four defects, the first one mine.
  (1) «he iniciado la tarea y no ha hecho nada»: a `make restart` 36 s after the worker was born killed it
  (`task | cancel · session | end`), and a second one landed while the errand was waiting (it survived only
  because V2-683/684 rehydrate). (2) The **browser card**: `classify_kind` said `web` because `login_site`
  resolved «Google Meet» to google.com and «send/add» are task verbs — but Calendar and Meet are linked
  INSIDE the agenda (V2-685), the same class as music and messaging, which already had their guard;
  `is_google_connector_service` joins them, and «busca en google» stays web. (3) The **results sheet**: the
  provider relay relaunches with a context that carried `sheet` and NOT `surface`, so a «voz» errand was
  reborn with the default surface — the exact hole V2-259's «both relaunches send the sheet» test closed,
  one field over; both send the surface now. (4) «no tengo a Kryptonite en el directorio»: he dictates K,
  the row (kept by V2-693's dedupe because it holds the Telegram account) says C; `directory.resolve` gains
  a last resort where a UNIQUE near match resolves and two near matches stay a refusal — writing to the
  wrong person is what this must never trade for. ⚠️ **And one thing NOT fixed, said plainly**: the worker
  fell through three providers ($1.23) on `400 [1210]` (z.ai) and `400 Invalid schema for function
  'Artifact'` (DeepSeek) on each first message; 55 minutes later the worker's EXACT argv reproduced neither,
  with or without `--tools`. The relay did its job; `--tools` ships as a narrowing (only the allowed tools'
  schemas travel), not as a proven fix. Seven disarms, every mutation asserted, all red. **NOT verified
  live** — it needs a restart, and a restart is not made with the operator inside. His design ask stays
  open and named in the initiative: the PULSE as the owner of an open errand, not a worker sitting in a
  session.

- **A NAME is a UI string, and the voice keeps answering to the one it shipped with (V2-694, 2026-09-14)**:
  the operator, on a session he had deliberately started in English — «el título de los widgets es en
  castellano… una vez está inicializada la sesión en inglés, se usa en inglés», and the rule that frames the
  whole batch: **«todos los nombres, etiquetas, títulos, botones… todo es configurable cuando se inicializa un
  idioma»**. **MEASURED before touching anything, because the first question was whether HE had broken it**:
  nothing had switched. `config/settings.json` held `stt_language: "en"`, every turn's prompt said «Responde
  ÚNICAMENTE en English», and `i18n.init.detect.should_detect()` is False the moment a language is persisted —
  so speaking Castilian could not have moved it and a reset only would with `wipe_profile`, which he had not
  ticked. **The Castilian was HARDCODED.** V2-613 built the seam (`ctx.t`/`ctx.lang`) and migrated two pilots;
  the other thirteen widgets carried their text inside `widget.js`, and every card TITLE came from
  `manifest.json`, which V2-082 had frozen on purpose because the voice resolver matches against it.
  - **That freeze is the interesting half.** The name is now `widgets.<id>.name` / `surfaces.<id>.name`, read by
    `widgets/registry.py::display_name`, so it follows the operator's language like every other label — and the
    manifest's own name stays as the FALLBACK (a generated widget has no bundle row and still needs a name) and
    **stays in `aliases`**. Translating it without keeping the original would have quietly retired half the
    vocabulary of every install that has ever spoken Castilian: a regression with no error message anywhere.
  - ⚠️ **`widgets/naming.py` (the worker's door) went through the registry and answered to the translated name
    from the first minute; `widgets/runtime.py::identify` (the VOICE) built its own lexical index straight off
    the manifests and did not.** Measured with the bundles in place and nothing else changed: «messages»,
    «downloads» and «browser» resolved to None for the voice while resolving correctly one module over — an
    English operator could READ «Messages» on the card and not be able to say it. Two doors into one namespace
    (V2-555), found only because the test was written against the real doors instead of against the registry.
  - **~480 strings across the catalog**, migrated as `tt("key", params, "<the literal>")` where the fallback is
    byte for byte what was hardcoded — so a widget rendered outside the engine behaves exactly as before and the
    change is reviewable line by line. ⚠️ **Ten module-level TABLES were the trap**: `const STATUS = {ok:
    "Hecho"}` is built at IMPORT time, before any `ctx` exists, so its text freezes in whatever language loaded
    first and survives every later switch; every one became a function resolved per paint. ⚠️ And **a whole class
    was invisible to the first scan** — sentences written as template literals, and labels living inside a
    `${…}` substitution (`${n === 1 ? "canción" : "canciones"}`) — so the scanner had to learn that a
    substitution is CODE, not template text, and then that a regex literal can contain backticks
    (`widgets/documento`'s `/`([^`]+)`/g` desynced it into reading every later comment as operator-facing text).
  - **The ratchet is the deliverable.** The old one recognised only a FULL key, so with fourteen widgets migrated
    it would still have been green having measured one — *a ratchet that cannot see the thing it ratchets reports
    safety*. It now derives each widget's prefix from its own helper, and refuses: a key missing from either
    bundle, an accented literal outside a translation call, and — **language-independently**, which is what made
    it bite — ANY literal assigned to `textContent`/`title`/`placeholder`/`alt`/`ariaLabel`. That last half was
    added because disarming `tt("seeds", …)` back to a bare `"Semillas"` left the accent check GREEN.
  - **Changing language is MANUAL and never spoken** (his rule: «hay que hacer todas las traducciones de todos
    los prompts, de todos los widgets… no es una cosa que vamos a permitir hacer con la voz»). No tool changes
    the language and none is added. ⚠️ Measured: the desktop ⚙ had **no language control at all** — the picker
    existed only in the first-run veil and the phone's sheet, so on this shell the answer to «I want it in
    English» was a factory reset. ⚙ → Apariencia carries it now, posting to `/api/i18n/choose/{code}` and never
    to the raw `stt_language` knob: that endpoint is what LOCKS the choice, generates the bundle for a language
    we do not ship, realigns the TTS voice and speaks the confirmation — writing the setting directly would
    leave a Swedish operator with a Swedish `stt_language` and an English interface. It asks **twice**.
  - `config.settings.update` is the ONE seam both doors cross, so that is where `i18n.runtime.invalidate()` and
    `registry.refresh_state()` live. On the client, `Desktop.relanguage()` re-rendered every widget's BODY since
    V2-613 and left the card HEADER alone — fine while the title was a constant, wrong the moment it became a
    translated string: it drops the registry and the compact-index caches and re-applies the names.
  - Nodes **4.11** (widened), **4.172** and **4.173** (RENDERED: a source scan proves the fetch line exists and
    proves nothing about whether the header changes); sixteen disarms, every mutation asserted, all red — ⚠️ and
    **four came back GREEN first, each accusing the test**: two properties were held by a second, independent
    guard (every shipped manifest already repeats its own name as its first alias; every surface's es/en word is
    already in the FIXED alias table), one measured a REIMPORT instead of the in-process cache the ⚙ actually
    hits, and one scanned raw source whose own COMMENT contained the words it was looking for (the V2-615 trap).
    The surface case could only be closed with a THIRD language, so the batch ships a generated-bundle test.
  - **NOT done, and named**: the per-widget `whenToUse` routing prose stays Castilian on purpose — it is an
    INTERNAL note the model reads and the prompt says so; and the catalog line still names a widget by its `id`
    rather than its label, which is defensible and would cost the shared per-turn budget (V2-526) to change.

- **A proxy in front of a hardened thing is a SECOND front door (V2-575 P1, 2026-09-14)**: the daemon had five
  guards and no way for a person to obtain it or point it at a folder. The engine now proxies it — a page over
  https cannot call plain http, a direct call needs CORS headers the daemon must never send, and the bearer
  token would have to reach JavaScript — and that proxy is the part worth writing down. It exposes `status`,
  `grant` and `revoke` and **no file route, ever**: proxying `files.read` would hand every page that can reach
  the engine the exact capability `daemon/security/guards.py` refuses, through our own credentials, and a
  ratchet fixes the route set so a future one needs a threat model rather than a test edit. Cross-origin is
  refused here too — without CORS a hostile page cannot READ the answer, but `grant` changes state, so fire and
  forget already puts a folder on somebody's allowlist. The guard reads `Sec-Fetch-Site` first and compares
  `Origin` against the request's OWN `Host`, never a configured hostname, because this engine is reached as
  localhost, as local.zaelar.com and as whatever a cloud account resolves to; the counterweight is in the same
  file, since our own page IS a browser. Three defects fell out of measuring rather than of reading: with no
  `daemon.json` the engine answered `reachable: true` because `/health` needs no token — a green icon over a
  daemon it cannot authenticate to; both CI runners uploaded `zaelar-daemon.pyz`, `manifest.json` and
  `SHA256SUMS` under those names into one flattened release, so one platform silently overwrote the other; and
  the first real Windows runner found `build.py` dying on `UnicodeEncodeError` printing `→` to a cp1252
  console **after every artifact was written** — the build worked, the script died on its own success line.
  The 🖥 icon is the one TopBar control not gated on `cloudProfile`: a cloud account is precisely the case
  where the user's own machine is unreachable, so hiding it hides it from the only people who cannot solve it
  another way — and that screen says outright that connecting a daemon to the cloud agent is still being
  built. Nodes **7.44** (offered and governed) and **7.41** (the cp1252 console). (2026-09-14; V2-575)

- **The errand FINISHES what it agreed — and a verifier reads ONE fact while an objective has several
  (V2-692, 2026-09-14)**: the operator reviewed his own test session and reported it whole — «he pedido que
  se organice una reunión… me ha pedido permiso para hacer el envío. Después el otro ha respondido, pero no
  ha seguido procesando… le he tenido que decir yo, acepta el mensaje. Y aún así no hemos terminado ni
  añadiendo el ítem a la agenda, ni tampoco creando el link de Google Meet.» Read from his own
  observability before touching anything (session `16770007`, flow `T9·08d2`, 209 events): **four defects
  stacked under one sentence, three of them silent by construction.**
  - **`bind()` refuses and NOBODY read the refusal.** A conversation belongs to one errand — right, and two
    objectives answering one person is how they get two different replies to one message. What was wrong is
    what the caller did with it: nothing. Yesterday's errand was still live (it had reached `agreed` and
    could never verify, see below), so it held his Telegram thread with a deadline sixteen hours past, and
    the errand born from his new order got **ZERO conversations** — a row that showed on the board as
    «esperando respuesta», rode the turn's context pack as an open gestión, and could not be woken by
    anything. His contact's reply then woke YESTERDAY's errand, against yesterday's objective. `claim()`
    takes the thread from a live incumbent — his newest word about this person is the current one — and the
    hand-over is TOLD; an errand that cannot take its conversation is closed on the spot rather than left
    to announce, in four hours, that nobody answered.
  - **`party.parse` has always returned an `agreed` block and NOTHING has ever read it.** The errand reached
    «hora acordada» and wrote nothing, anywhere. `errands/book.py` writes the meeting the ENGINE was told
    about, inside the mandate (`schedule` is a separate grant from `message`), and the Meet link Google
    mints as `conferenceData` (V2-685) is appended to the very reply that promises it — booking happens
    BEFORE the send, which is the whole point of the ordering. Meanwhile the worker was driving a browser
    into `accounts.google.com/signin`, twice, in two sessions.
  - **`verify.meeting_exists` filters on a `created` stamp the agenda has NEVER written**, so no errand in
    this house could close by being ACHIEVED — only by running out of time. Its own note records that the
    unit test missed it by writing the field BY HAND. `commit_meeting` stamps it now.
  - **His permission travels with his ORDER**: `send_to` stops being confirm-gated (the worker was gated
    FOUR times on one order and he had to answer «I don't want you to ask» to get his own errand moving);
    `reply` stays gated, because answering something that arrived on its own is nobody's order — his own
    rule, quoted. And `errands.shadow` ships FALSE: it shipped true so autonomy toward real people is not
    handed over on a green suite, and he has now read those rows and asked for the opposite. The bound does
    not move: an errand only ever writes to the ONE conversation it was born in.
  - **A gestión with a third party is HANDED OVER, never sat out.** Measured twice: the worker sent the
    message and then waited inside its own session — 25 `peek` calls, `sleep 150/240/300/420`, a `Monitor`
    loop the permission gate refused — ten minutes of paid session doing nothing, and then the session ended
    and the task ended with it. The durable mechanism existed since V2-683; nobody had told the worker. It
    also settles which door: an errand can only be born from `send_to`, so a follow-up with somebody who had
    already written to us could never become one — **what decides is not whether they wrote first, it is
    whether this message opens something that has to be followed.**
  - **A worker could not READ a widget that grows.** `read agenda` answered with **59 955 bytes**, 55 666 of
    them his whole calendar; the CLI persisted it and the worker was then refused the file twice («31 844
    tokens exceeds maximum allowed 25 000»), reaching 111 282 tokens of context in three minutes. Both
    worker doors hand back the digest the turn prompt has used since V2-576 — 975 bytes for that same
    calendar — plus what is inside and how big, so it can ask a declared action for a slice. Nothing is ever
    truncated: cut JSON reads as complete and is a different shape.
  - ⚠️ **THE BATCH SHIPPED THREE DEFECTS OF ITS OWN AND ITS LIVE RUN CAUGHT EVERY ONE**, all in the same
    family. (d) Lifting V2-683's «never promise a link» prohibition UNCONDITIONALLY, so with his calendar
    unlinked it told a real person «the Google Meet link will be sent with the invitation — it gets added
    automatically»: **a capability stated unconditionally is one the model promises unconditionally**, and
    the gap is paid by a stranger. What it may promise is read from the connector per wake, and fails
    CLOSED. (g) An anti-duplicate guard keyed on the SLOT and blind to the title — his calendar held five
    «Dentista» at 17:00, so it read «already booked», wrote nothing and **reported success**; the row an
    errand owns is the one IT wrote (`done_when.at`), a different slot MOVES the meeting, and an
    appointment that merely shares the hour belongs to somebody else's day. (h) And the verifier then closed
    it as «hecha y verificada» with the link debt outstanding — **closing RELEASES the conversation**, so
    the link could never be delivered.
  - **The class, worth more than the three cases: a verifier reads ONE fact and an objective can have
    SEVERAL**, and the error always falls the same way — it says done, and the operator finds out from the
    other person. Three times in one evening: a stamp nobody wrote, a neighbouring meeting in the same
    window, and a promise still unkept. «Acordar la videollamada Y MANDARLE el enlace» is one errand with
    two halves, and his condition reads literally — «la tarea no termina hasta que no está correctamente
    programada esa reunión» — where *programada* includes what was promised about it.
  - ⭐ **VERIFIED LIVE**: one order → worker → `send_to` with an objective → errand born and bound, **zero
    confirmations**; the engine RESTARTED mid-gestión and the errand came back exactly where it was; his
    reply at 20:27:03 woke it **eleven seconds later** and it decided, answered and booked on its own; and a
    second round moved the meeting from 16:00 to 17:00 instead of duplicating it. **NOT completed, and the
    reason is not code**: the Meet link needs the OAuth consent, a click in HIS browser on HIS account that
    the popup only survives inside — so the debt is recorded and the beat pays it the moment the link
    exists. The same click blocks deleting 23 test appointments: 22 live in his real Google Calendar with
    their own `googleId`, so a local-only delete would return on the next sync.
  - Nodes **3.47** (33 cases) and **3.48** (8). Twenty-eight disarms, every mutation asserted. Three came
    back green: two were harness artifacts (a `"confirm": true` inserted at the head of a JSON object is
    overridden by the real key later in it) and one accused the TEST — that property is held by the AGENDA's
    own `_is_same_meeting` (V2-208), not by this code, and the case now says so instead of taking credit.

- **A COMPOUND close does not swallow the rest of the sentence (V2-688, 2026-09-14)**: «close all, open
  agenda, connect to my google calendar» cleared the canvas and did nothing else — his question was the one
  anybody would ask, «why is this order not followed?». Read from his own observability before touching
  anything (flow `T10·c053`), and the WHOLE event chain of that turn is four lines: `✋ interrupción dura
  atendida · widget close · ⛔ vetaría close-drag · flow end`. **No tool, no model call, no reply.** Two
  thirds of one sentence discarded in silence — and the canvas DID clear, which looks enough like obedience
  to hide the two orders thrown away with it.
  - **The mechanism was right and the outcome wrong.** `attention.hard_interrupt()` exists because a close
    order once fell OUTSIDE the excerpt of a 14 000-char turn and simply never happened (T136); its
    guarantee — executed deterministically, before any model, always — is worth keeping and is not weakened
    here. What nobody had examined is the **`return` after it**: it treats «close» as the whole of what the
    operator said, which is true of «cierra todo» and false of every compound order. **Speech is full of
    compound orders** — that is how a person clears a desk before starting something.
  - **The close keeps its guarantee and the rest of the sentence keeps its turn.** ⚠️ The closing clause is
    **REMOVED** from what the model reads, not left in: handed «close all» against an already-empty canvas a
    model re-emits it (the context-bleed shape V2-635 catalogued across four classes), and that second close
    would land on whatever the very same sentence had just asked to open — turning one silent failure into
    an intermittent one, which is worse. `close_all_remainder()` is conservative by construction: courtesy
    («cierra todo, por favor»), timing («ya», «ahora mismo») and a single bare word all come back empty, and
    the caller then behaves exactly as before. **The comma is the only difference between its splitter and
    the one `_closes_the_whole_canvas` uses**, which stays comma-blind on purpose so an enumeration of
    things to close («cierra el vídeo, la música y todo lo demás») keeps reading as ONE closing clause.
  - The architecture ratchet went red (`nucleo.py` 3054 > 3043) and was paid by **EXTRACTING**, never by
    raising the ceiling: the whole hard-interrupt decision — worker vs music vs canvas, and whether closing
    was the entire request — moved to `nucleo/flash/hard_turn.py`, and nucleo.py ends at **3014**, below
    where the batch started. Wiring guards anchor on the module that OWNS the block (V2-555). Also dropped a
    dead re-export (`_action_is_negated`) that nothing in the repo reads and that had the ruff F401 gate red
    on that file before this batch.
  - **Deliberately NOT mirrored into the probe channel, and a test says so**: the probe never had this
    defect — it calls the model with the full text and only LABELS the action afterwards — so there is
    nothing to mirror, and stripping text before its model call would be a change with no defect behind it.
    V2-252's rule is that a behaviour fixed in one channel is fixed in both; **the channel that always
    worked is not the one to change**. Node **3.46** (20 cases); seven disarms, every mutation asserted, all
    red. ⚠️ **NOT verified live by voice** — the engine restarted onto it (`3.26+61100472`), but only the
    operator saying the sentence proves the whole path.

- **Both doors ask Google for the SAME return address (V2-687, 2026-09-14)**: the operator's FIRST real
  Google connect, and it died at the last step — «Access blocked: This app's request is invalid ·
  **Error 400: redirect_uri_mismatch**». Everything on this side was correct AND consistent, which is what
  made it hard to see: the client resolved (`source() == "shipped"`, project `studied-reason-508412-f7`,
  web client) with **no per-connector override set**, and the pending OAuth record proves the exact string
  we sent — `http://127.0.0.1:43917/api/calendar/callback`, verbatim what the engine printed and what he
  was told to register. Two further measurements framed it: the error is `redirect_uri_mismatch` and NOT
  `invalid_client`, so the client id was accepted; and the console's exported JSON carries **no
  `redirect_uris` key at all**, which a web client omits only when it has none registered.
  - **The defect is that TWO doors open this same consent and derived the address DIFFERENTLY.** ⚙ →
    Conectores → Calendario (`/api/calendar/connect`) reads the REQUEST headers — V2-603's fix, because a
    hardcoded loopback only works for a self-host opened on that machine — while the agenda card's own
    button went through `gcal.ui_action` → `service.connect_url(provider, tier)` with **no origin**, so it
    always fell back to the loopback default. Which URI Google had to match depended on which button he
    pressed, and this engine serves TWO origins (`127.0.0.1:43917` and `local.zaelar.com:44317`, the two
    listeners of the same app). **Registering the five the engine printed left the other five failing**,
    with an error that names neither door.
  - ⚠️ **The class is worth more than the case.** V2-603's origin fix was copied into this connector «from
    day one instead of being paid twice» — its own docstring says so — and it was copied into ONE of its
    two callers. **A fix that lives in a CALLER has to be re-applied by every caller that arrives later**,
    which is exactly V2-626's «a rule every caller has to remember is not a rule», one connector over.
  - Fixed by making the card send `location.origin` in the connect payload (absent — a voice-driven
    connect, a worker — it falls back to the loopback, the only honest answer when nobody is looking at a
    page), and by adding **`app.uris_to_register()`**, which is what the operator PASTES: every callback ×
    every origin this engine answers on, ports read from the same env names `server/__main__.py` honours.
    `redirect_uris(origin)` stays what the FLOW uses. **A list printed for one origin is right half the
    time**, and that is what made this read as «I did exactly what it said and it still failed». The
    README and the module docstring now name the error that actually happens and the right console box
    (*URI de redirección autorizados*, **not** *Orígenes autorizados de JavaScript*).
  - An origin in a payload is not a credential (V2-520) and cannot leak a code: Google only ever redirects
    to a URI the client has REGISTERED — the control this entire batch tripped over — and a malformed one
    falls back instead of travelling. Node **4.168**; five disarms, every mutation asserted, all red.
  - ⚠️ **The retry failed too, and agreeing was never going to be enough (V2-687b, same afternoon).** The
    engine probed Google's OWN authorize endpoint for every URI on the list — building the same URL the flow
    builds, following none of it, consenting nothing — and all five answered `redirect_uri_mismatch` while
    echoing the exact string we sent. So the client had **no redirect URI registered at all**, and **three
    defects were stacked under one error message** with only the first found. **(2) The list asked him to
    register five URIs Google will not accept.** `local.zaelar.com` is a DOMAIN — OURS, shipped as a DNS
    alias of 127.0.0.1 so a local engine can be opened over TLS — and Google exempts only the LOOPBACK
    address from domain ownership, so **no self-hoster can ever register it**. The remedy V2-687 reached for
    — print TEN instead of five — therefore made half the list unregistrable, which is worse than the defect
    it replaced. `app.normalize_origin()` collapses this engine's two local listeners onto loopback: same
    process, same token store, and a callback page that reads nothing from the origin's session, so which of
    the two Google returns to changes nothing the operator can observe. A genuinely remote origin is not one
    of `served_origins()` and passes through untouched, so V2-603 stays true and the list is five again.
    **(3) `CALLBACK_PATHS` named `/api/files/callback`, which this engine has NEVER served** — Drive answers
    on `/api/cloudfiles/callback`, and `/api/files/*` belongs to `memory_routes`, which `server/__init__.py`
    says in as many words. A wrong address on a list of five reads, to whoever pasted it, as «I did exactly
    what it said». The test derives the truth from the MOUNTED routers instead of trusting the tuple, which
    is the only one of the three a test could have caught the day it was written — and it declares the gap
    it exposes: **`/api/email/callback` has no router at all** (`server/email_api.py`, named by
    `connectors/email/oauth.py:7`, does not exist), so Gmail's OAuth door is dead and now says so.
  - **`app.check_registered()` — ask Google instead of guessing.** Registering a redirect URI is the one
    step of this setup that happens in somebody ELSE's console, and until today the only way to find out
    whether it had worked was to run a whole consent flow and read `Error 400` at the end of it. It answers
    **None, never False, when it cannot tell** — an offline machine must not be told its setup is broken,
    because «could not tell» and «not registered» send the operator to two different places. ⚠️ The general
    lesson, and the one worth more than this connector: **a list of addresses to register is only worth what
    it is DERIVED from** — hand-typed, it drifts from the routes in silence, and the drift only ever
    surfaces in the operator's browser, as HIS failure. Seven more disarms, every mutation asserted, all red.

- **The LAST METRE of a connector: the agenda owns its own, and a voice order ends in front of the BUTTON
  (V2-686, 2026-09-14)**: the operator tried to connect Google Calendar by voice, twice, minutes after
  V2-685 shipped the client, and lost both times — «he intentado conectar la agenda con Google Calendar
  pero el sistema no me ha entendido… necesito hacer ese test manual porque la conexión la tengo que hacer
  yo desde el browser con mi cuenta de Google». Read from his own observability before touching anything
  (session `a9fcd650`, engine `3.26+860dd7fb`):
  - **`T12·9e60` «open the google connector» → the model opened MESSAGING** and answered «the Google
    connector is right there with the login steps». It did not hallucinate: `widgets_n_selected: 15` of 15,
    so the whole catalog was in the prompt and selection filtered nothing — what decided it was that the
    only purpose line mentioning connecting was messaging's («…o conectar un canal», plus `gmail`,
    `conectar email` in its keywords), while the agenda's said nothing about connecting, nothing about
    Google and nothing about a calendar. **A connector adds ACTIONS and almost never the WORDS that lead to
    them**, and the routing line is the half nobody updates. Fixed by naming the service, the linking verb
    and **the frontier** («es la agenda, no mensajería») in `whenToUse` — 283 of the 300-char budget,
    asserted against `brief._purpose`, because what the cap trims is the END, which is exactly where the
    frontier clause lives (trap T4) — plus 21 keywords and 5 aliases **in both languages**: both lost turns
    were in ENGLISH against a widget whose vocabulary was Castilian except for «schedule» and «my day».
  - **`T14·76b6`, naming the widget, DID reach it — and nothing happened.** `widget_data agenda:connect`
    was allowed, executed, and returned a perfectly good consent URL; the screen did not move and the mouth
    said nothing (`completion_chars: 0`). The connector was never broken. **Two links cut the last metre,
    and neither is a bug that shows up in a log**: `widget_data_turn.py` keeps `{widget, act}` from a
    successful data-op and **throws the result away**, so no `url`/`hint` in a return value can ever reach
    the model; and even if it did, **the voice cannot finish an OAuth consent** — the popup only survives
    inside the click that opened it, which `widget.js` already documents and the calendar connector already paid for.
  - **So the voice does the half it CAN: it puts the button in front of him.** `gcal.push_connect_screen`
    leaves the card ON its connect step, published through `view_data` with the same token shape as the
    pushed view — a COUNTER (asking twice lands twice; a flag would stay true and move nothing) and an `at`
    that EXPIRES at 180 s (or tomorrow's first repaint ambushes him with a setup screen over the agenda he
    was reading). **The push happens BEFORE the connector is consulted**: if it depended on the URL coming
    out well, the case that needs a screen most — no OAuth app registered — would be the one without one.
    And the sentence is declared in the action's `desc`, which DOES travel in the prompt: call it, tell him
    to press «Conectar Google Calendar», never dictate the URL.
  - **The alta was not closed, and closing it found three live drifts**, each of which failed silently:
    `connectors/catalog/youtube.json` was still `planned` — parked in V2-603 F2 for ONE written reason, «no
    Google OAuth client», which V2-685 removed two days earlier — so the chat wall was offering him a **«Lo
    quiero»** button for a connector he already had (`oauth.authorize_url('youtube')` returns a valid URL);
    `google-calendar.json` declared id `google-calendar` while its live row is `google`, so
    `catalog.search()` could never rank his own calendar as connected; and `ChatWall.js`'s
    `CONN_FAMILY_ORDER` was missing `video` and `agenda`, live families since the YouTube account connector and the
    calendar one, so both rendered below Infraestructura in the «a family nobody expects» bucket. **If a manifest parks something
    behind a CONDITION, the condition goes in its notes and lifting it is the last step of whatever
    satisfies it.**
  - **The workflow now carries what this proved was missing**: six more wiring points (§4 is 14 now), the
    ROUTING half in §5, **§7-bis the LAST METRE** and **§7-ter declararlo HECHO**, four new traps — plus the
    two docs that did not exist: the connector **LIST**
    (`.meshkore/docs/modules/zaelar-connectors-inventory.md`, the operator's «añádelo a la carpeta MeshKore,
    a la lista de conectores») and the Google connector's module doc, which §8.1 required and V2-685 never
    wrote. Node **5.7** (+1 file) is the ratchet behind it: no live connector may sit on the wishlist, a
    `built` manifest with no live row must say why in writing, every live family has a name in BOTH bundles,
    a place in the chat wall's order and a section in the ⚙ panel, and no two rows share an id.
  - ⭐ **VERIFIED LIVE on his engine, and driving it found TWO MORE causes that no reading would have.**
    With the routing fixed, «conecta mi google calendar» and «connect my google calendar» reach
    `agenda:connect` (5 of 6 samples; the baseline reached it 0 times), and the action drives the real card:
    `POST /widgets/agenda/action` returns a consent URL **and** the live card comes back carrying
    `connect: {n: 1, …}`, which is the push. But the bare «open the google connector» kept opening
    Messaging, and the prompt said why: **`connectors/messaging/brief.py` claimed EVERY connection
    ceremony in the product** — «si quiere conectar/ver UNA APP, emite `[[show:mensajeria]]` … Guíale tú
    también de palabra ('te abro Mensajería, ahí tienes los pasos')», with the reply pre-written, which is
    almost verbatim what the model said. True when messaging was the only connector with a wizard; a defect
    once the engine grew five more and nobody narrowed the sentence. **A brief may claim its OWN family and
    no more.** And `connectors/google/brain.py` — mine, one day old — told the model it could offer to
    connect Google and never said THROUGH WHICH DOOR, so it picked the only widget whose text mentions
    connecting anything: the mechanism is a table now (`_DOORS`), and the offer SHRINKS as each door opens.
    ⚠️ **That same sentence was also wrong on its own terms**: «una sola vez sirve para Gmail, Calendar,
    Meet, Drive, Fotos y YouTube» is true of the CLIENT and false of the CONSENT — each connector runs its
    own flow, with its own scopes and its own token store, so linking the calendar grants nothing to Gmail,
    and a model that had just connected one door would have reported the other five as connected.
  - ⚠️ **And a lesson about HOW this was measured**: two rounds of prompt wording were added on the strength
    of ONE probe sample each, and both made it worse (`show_widget` with no action, then three turns calling
    nothing at all) before a third round showed the first «regression» had been a single unlucky draw on an
    UNCHANGED file. Reverted to the wording that measured best and sampled each phrase three times.
    **Tuning a prompt by single samples is not measurement**, and it was being done on the operator's live
    engine. Left as it is and reported: the bare «the google connector» still resolves to Gmail — defensible
    (Gmail IS a Google connector) and deliberately not forced, because forcing it breaks «conecta mi gmail».
  - Node **4.167**; fifteen disarms, every mutation asserted, all red — ⚠️ one came back GREEN and was a
    real gap: **nothing measured the scope of the messaging brief**, the very sentence that caused T12. ⚠️ **Two were harness artifacts** — a
    `-k "a or b"` split on whitespace produced «no tests ran», which exits non-zero and reads as red (the
    zsh trap, paid again) — and ⚠️ **one came back GREEN and accused the TEST**: the first two routing cases
    asserted `selection.candidates`' ranking, and with fifteen widgets **everything** is a candidate, so
    they measured nothing; rewritten against the artifact that actually failed, the row
    `brief.for_prompt` puts in the turn prompt. **Not fixed here and named**: the turn report still discards
    a successful data-op's result — making it reach the model is a change on the shared voice path and
    deserves its own batch.

- **ONE Google account, six doors — and Meet is an ARGUMENT, not a tool (V2-685, 2026-09-13)**: the
  operator, handing over the OAuth client he had just registered — «we need to create the google connector…
  we will use it for gmail. **change current to standardize**. use it for calendar and meet and for now i
  guess we do not have more widgets were applicable», then «add features to the system so brain workers etc,
  flashbrain, all can use it when need it». **MEASURED before writing a line**: six near-identical OAuth
  modules (1 325 lines), **five of them fronting Google**, each asking for the SAME client under a different
  name — `EMAIL_GMAIL_*`, `CALENDAR_GOOGLE_*`, `VIDEO_YOUTUBE_*`, `PHOTOS_GOOGLE_PHOTOS_*`, `FILES_GDRIVE_*`.
  He answers one and the other four stay dormant in silence. `builtin_client_id` had been declared and EMPTY
  since V2-603 and copied verbatim into the calendar connector the day it was built, both saying «EMPTY until Zaelar registers its own Google OAuth
  client». He registered it on 2026-09-12.
  - **`connectors/google/` holds the answer once, and is a LEAF**: nothing there imports another connector,
    because everything else imports it. `app.py` resolves the client — the operator's own (`GOOGLE_CLIENT_ID`)
    first, then the `client_secret_*.json` the console hands you, read **verbatim** out of
    `.meshkore/credentials/` so nothing is retyped into a source file and no second copy can drift; cached on
    (path, mtime), so a file dropped in while the engine runs is seen without a restart, and a value frozen at
    import would have left him restarting to be believed. It reports WHERE the client came from, never what it
    is. **Each connector's own name still wins**, which is what keeps the fair-code self-host story honest and
    what makes the change safe: Outlook, which authenticates against Microsoft, gets nothing — handing it a
    Google client would turn a dormant connector into a broken one, and that counterweight is the test that
    matters most here.
  - **`services.py` deliberately does NOT own the scopes of a connector that has its own registry.** Each
    already declares them next to the client that requests them, this package sits BELOW those connectors and
    cannot import them to check, and two copies of a scope list drift. It fills in `scopes` only for a service
    with no connector at all — which today means exactly one.
  - **Meet is that one, and it asks for NOTHING extra**: a Meet link is `conferenceData` on a calendar event,
    minted by the calendar scope the connector already holds. There IS a standalone Meet REST API behind
    `.../auth/meetings.space.created` and it is **named in `FUTURE_SCOPES` and not requested** — an unused
    sensitive scope buys nothing today and costs a harder Google verification for every user of the app.
    ⚠️ **`conferenceDataVersion=1` is the half that fails silently**: without that query parameter Google
    returns 200, creates the event, and DROPS the conference — no error, no link, and an agent that has just
    told the operator it made them a meeting room.
  - **The capability is an ARGUMENT of the tool the model already has**, and `brain.py` says so out loud. Meet
    is a verb this engine has never had, so a model asked for one has no prior behaviour to fall back on
    except inventing a `create_meet` tool or promising a link before Google minted it. Naming the capability
    alone is what makes a model improvise a verb — so the line names `meet: true` and states that no separate
    tool exists. Third payment of V2-603's receipt («four claims, zero connections»). **Workers needed no
    exception**: they reach it through `act widget_data`, already allowed and gated on the widget's own
    manifest, so `_PRESTABLE_TOOLS` — whose comment says it «grows only with an explicit designation, never by
    accident» — was left untouched.
  - ⚠️ **Three ratchets went red and two were paid by EXTRACTING**: `prompt.py` (846 > 834, 30 lazy imports >
    29) → `flash/connector_briefs.py`, ending at **789 and 26**, lower than before the batch started; the
    Google wiring guard re-anchored on the module that OWNS the block, per V2-555. The third was **not paid**:
    `widgets/agenda/data.py` sits EXACTLY on the 900-line newborn ceiling while another session edits it, so
    its one-line delegation (`gcal.apply_meet(meeting, payload)`) is deliberately left out — extracting from
    somebody else's in-flight file is worse than leaving one line, and a ratchet is never paid by a smaller
    diff. Its test is skipped and says exactly that.
  - ⚠️ **Eight tests in three other files went red, and all eight were MINE**: video, calendar and agenda each
    assumed no Google client could exist — video's `sandbox` fixture said so in its own docstring and simply
    had a third source it did not know about. **Pinned, never relaxed** (V2-606's lesson: a test that measures
    the machine it runs on), each with its counterweight asserting the new reality — including a FOURTH
    connector state the agenda had no sentence for: an app registered and awaiting consent is not «you have
    not linked it». And one test DOUBLE had a narrower signature than the real client (`post` with no
    `params`), so the new query parameter raised a TypeError that `insert_event`'s own except swallowed into
    `{"ok": False}`.
  - ⚠️ **The number collided.** This batch took V2-684 and the concurrent session already owned it; renumbered
    at closure, and the blind rename then clobbered **four foreign citations** in `tests/run_testmap.py`,
    restored by hand. Create the initiative file when the number is TAKEN.
  - Node **5.25** (27 cases, ten disarms, every mutation asserted, all red — one came back GREEN and accused
    the TEST: the case started from the already-trimmed state, so removing the guard popped a key that was not
    there). **NOT verified live, and it cannot be yet**: it is a **web** client, so Google refuses a redirect
    URI it has never seen — with `invalid_client`, at the END of a flow that looks healthy all the way up —
    and the five the engine serves (`app.redirect_uris()`) are not registered in the console. Nothing connects
    until the operator pastes them. **NOT committed**: `connectors/registry.py`, `connectors/calendar/`,
    `widgets/agenda/` and their tests all carry another session's uncommitted work, and a pathspec limits
    files, never hunks.

- **The test system learns the ERRAND, and a language leak becomes a failure (V2-684, 2026-09-13)**: the
  operator, handing over a second Telegram account of his own (`@cryptonite_fund`) to answer from — «así
  lo podrás probar contra una cuenta real» — and merging two testing plans into one batch, errand first.
  They ARE one plan: the errand's party turn is a language surface (`party.build_system` answers in the
  PARTY's language, not the operator's), which is the one case neither plan covered.
  - **The ARC, and why the pieces were not enough.** V2-683's 105 cases each move one piece with the
    neighbours stubbed; all of the errand's interesting behaviour is multi-turn, and the multi-turn shape
    had never run once. `tests/agent_headless/harness/errand_world.py` is ONE double, at the TRANSPORT —
    it hears `msg.send`, decides whether the message really went out, echoes the conversation it created,
    and can make the other person answer — with a clock the arc controls, so ten hours cost no seconds.
    Everything above it is product: the widget's `send_to`, the owner's flush WITH its secret scan, the
    watcher's three signals, the ledger, the wake, the parse, the verifier and the expiry sweep. Node
    **3.43** (19 cases): agreement closing against the AGENDA and not against the model, the answer ten
    hours later, «quiero hablar con Ricart» (blocks AND then stays quiet — the second half is the
    assertion), nobody answering, two exchanges as ONE conversation, a send that failed, a meeting he
    already had. Plus the half he said matters most, «sin necesidad de que lo tengamos que programar»: the
    same arc with NO playbook, with reunión→cena, and with `config/playbooks.json` beating genesis — with
    a ratchet that no playbook may name a person, a company or a site, which is what keeps a briefing from
    quietly becoming a script.
  - ⚠️ **The arc found a real defect: an ARMED errand would have answered NOBODY.** `wake._send` queues
    the composed reply in `pending_send`, and the only flush lived inside `_Owner.handle` — with no
    operator action on the messaging widget, nothing ever drained it. Invisible because the feature ships
    in SHADOW (nothing to flush) and because every unit test stopped at «it was queued». The owner's own
    beat drains it now; the flush stays where it is, because that is the one door where `memory/secrets.py`
    reads a text written by a MODEL for somebody outside.
  - **The shadow gate is a number now** (node **3.44**, read-only): every decision the errand logged, per
    errand, with what it WOULD have said — and the one question answerable mechanically, «how many would
    have written to a conversation that is not this errand's own». Zero is the gate. A log with no
    decisions says so instead of printing a reassuring zero over nothing. And node **3.45** is the only
    test in the house that writes to a PERSON: it arms the engine out of shadow for the length of the run
    and restores it in a `finally`, **refuses to start while any other errand is open** (the flag is
    global), and waits — saying what it is waiting for — through as many replies as the conversation takes.
  - **A language leak is a failure of the test that caused it.** `tests/lang.speaking(code)` does the
    THREE things a language change is (env + `actionmap.invalidate()` + `detect._should_cache`); five
    files each did a subset by hand and only one invalidated the pack, so a test that switched language
    read the previous language's table and passed describing the wrong one. The root conftest now fails
    whoever leaves `ZAELAR_LANGUAGE` changed — documented in prose since 2026-08-20 and never made red —
    and found two real leaks the day it was installed: one file POPPED the variable in its teardown
    (leaving every later test with no language at all) and two cases call `settings.update
    ({"stt_language": "de"})`, which writes the process env by design. Node **8.9**.
  - **The segmenter corpus stops mixing languages.** It was red at 54 % against a 70 % floor and all ten
    escaped fragments were English, while the segmenter has no branch for another language — so one
    blended number was pressing to LOWER the Castilian bar to accommodate English. Two buckets, two
    floors, a bucket too small to mean anything reported instead of asserted. ⚠️ Measured: the registry
    holds ZERO Castilian fragments today (the sessions rotated), so that side SKIPS rather than passing,
    and the test says which. ⚠️ Also measured, and the plan had it wrong: a session does NOT record its
    language — one event in 12 127 carries the field — so the label is lexical and says it is test-side.
  - Seven disarms, every mutation asserted, all red; two came back GREEN first and each accused the test
    (the failed-send guard is not what stops a birth — no echo is; and the flush's WIRING was measured by
    nobody, since the arcs drive it through the harness). `memory.errands_store` is blessed in the memory
    contract: the boundary test and the architecture ratchet pointed opposite ways in V2-683 and the
    extraction won — the blessing records that instead of leaving a red test with no written reason.
  - ⭐ **VERIFIED LIVE, and the live run found SIX more defects, none of them visible from the suite.**
    The operator answered from `@cryptonite_fund` and at 23:13:29 the errand answered him BY ITSELF —
    «Perfecto, mañana por la mañana. ¿Te viene bien a las 10:00?» — the first sentence this system has ever
    said to a person with nobody dictating it. What it cost, in the order it was found: (1) an errand
    CLOSED ITSELF in the same second over his real «Cinema with Mary», because `verify.meeting_exists`
    filtered on a `created` field the agenda never writes — **the earlier tests passed because they wrote
    that field BY HAND**; (2) an answer arriving with the ⏻ off was LOST rather than postponed, because
    `_fire_wakes` POPPED the wake six lines before `wake()` refused with «parado»; (3) the errand tests read
    his REAL `config/playbooks.json`, which the live node writes `shadow: false` into, so the shadow arcs
    ARMED themselves; (4) **an answer that arrived before a RESTART was lost for ever** — three messages
    landed at 22:28, the engine came back at 22:33, and the errand sat in `contacting` with `last_inbound`
    empty, because `_pending_wakes` is memory, the bus subscription is memory, and nothing ever asked the
    thread store what it was ALREADY HOLDING (`watch._reconcile` now compares each live errand against its
    own conversation: the bus becomes the FAST path instead of the only path, which also covers a ⏻ off for
    longer than one process and any dropped event); (5) **the model said NOTHING and the conversation
    died** — the party turn asked `deepseek-v4-pro`, a REASONER, for 700 tokens and got `reasoning_tokens:
    700` of 700, `finish_reason: length`, `content: ''`, which `wake()` filed as «ilegible» and answered
    with silence toward somebody who was waiting (the V2-658 class one layer over: `no_thinking`, a wider
    budget, ONE bounded retry — and the operator is told, because a turn that could not answer is
    indistinguishable from a gestión still in flight); (6) the dossier announced his OCCUPIED hours under
    the label «HUECOS LIBRES», so the next thing it would have done is offer «Cinema with Mary»'s slot to a
    stranger — **a label that contradicts its own value is worse than no line at all** — and the person was
    called «telegram», because the contact is filed by the handle he dictated while the conversation is
    keyed by the platform's numeric id.
  - ⚠️ **And the first real errand turned four UNRELATED tests red on a clean tree**:
    `context_packs.active_ids()` answered `['errands']` — his own gestión, in his own ledger — so the
    PHRASEBOOK cases failed, because the phrasebook correctly stands aside while a phase is guiding.
    Nothing was broken; the suite had started depending on whether he happened to have an errand open. The
    cause is this invariant's last unreached store, **`zaelar.db`** (the memory, the durable event log and
    the errand ledger), and the gap was already written down in `tests/browser/unit/agenda/conftest.py` —
    «nothing in the test conftests overrides `ZAELAR_DB`» — which is the same shape V2-673 paid for
    `config/v2.json`. The database moves for the whole session in the ROOT `conftest.py` now, beside the
    three that already do, with its row in `test_suite_isolation`; a runner pointing at its own corpus is
    honoured, because that is a test choosing its state. **NOT built**: the journey case and the language
    axis proper (T-B…T-G), named in the initiative. **Still not verified live**: the full CLOSE of an
    errand against a real agreement — the party turn holds no tools, so nothing turns «agreed» into an
    agenda row yet (V2-683 row 6, blocked on `connectors/calendar/`).

- **An errand with a THIRD PARTY outlives the turn — and it ships in SHADOW (V2-683, 2026-09-13)**: the
  operator's errand — «contacta con Iván Musikin y mantén una conversación con él para organizar una
  reunión esta tarde… y cuando él conteste, ahora o dentro de diez horas, sigue esa conversación» — plus
  the architectural half that outlives it: «que el sistema pueda soportar workflows de este tipo o de
  cualquier otra índole SIN necesidad de que lo tengamos que programar». **Measured before building
  anything: four kinds of «ongoing» existed and not one could hold it** — the TURN (seconds), the WORKER
  SESSION (`workers/session.py`: minutes, RAM, buried by `rehydrate.py` past `STALE_S`), the CRON (a prompt
  at a time, no state) and the HARNESS GOAL (`harness.py`: TTL 300 s, cap 8, RAM, verifies only whether a
  widget is empty). And three capabilities were missing outright: a contact had **no channels** (phone and
  email, no Telegram handle, no preferred one), **every outbound path required a conversation that already
  existed** (`_resolve_target` → `pending_reply` → each connector's drain), and nothing linked an inbound
  message to an errand WE started. So the work is a missing NOUN plus its resources, and deliberately NOT a
  workflow engine: no steps, no branches, no retries — that is the script the brain-worker doctrine
  forbids, and it is what would make «reservar una mesa» need a second engine next month.
  - **`nucleo/errands/` is a ROW, not a process**: it survives a restart because that is what a row does,
    and it is woken by the world instead of sitting in memory waiting. It is born from HIS OWN YES —
    `mensajeria.send_to` is confirm-gated and its question IS the mandate («Voy a escribir a Iván Musikin
    por Telegram: "…". Es para organizar una reunión esta tarde: si contesta, sigo yo la conversación por
    ahí y te aviso») — and, his own rule, **it closes itself**: the objective verifies, the deadline passes
    («en las próximas cuatro horas» is a GRAMMAR; a vague «esta tarde» falls back to a DECLARED default
    rather than a guessed date, the call `scheduler.parse_when` already makes), or he says so. A closed
    errand RELEASES its conversations, and `errand_threads`' primary key `(platform, chat_id)` makes «one
    errand per conversation» structural rather than remembered.
  - **The party turn holds NO TOOLS.** A stranger's words reach a model — that is what following a
    conversation means — and the model returns ONE JSON object the ENGINE executes. There is nothing for an
    injected instruction to call, structurally rather than by prompt wording. The profile is `cluster.py`'s
    UNTRUSTED one (V2-069) with exactly two differences, both written down: identity is disclosed BY MANDATE
    and only that much (the assistant's name, the operator's first name, that it writes on his behalf —
    that IS the errand), and the language follows the PARTY. `compose_state` is never read. The reply can
    only reach the conversation the errand already owns, held by two independent guards (a whitelist on the
    parse, and a send BUILT from the binding).
  - **SHADOW is what ships** (`errands.shadow`, genesis, default true): it decides and LOGS what it would
    say, and sends nothing. Autonomy that writes to real people in his name is handed over after he has read
    a few of those rows, not on the strength of a green suite. Fails closed, as do ⏻ (postponed, never lost)
    and an unreadable answer (half an action out of unparseable prose is worse than none: it reaches a
    person). Outbound text passes `memory/secrets.py` at the owner's flush and FAILS CLOSED — unlike a reply
    he dictated, this text was written by a model for a third party.
  - **Playbooks are DATA and a briefing** (`genesis.json`, overridable in `config/playbooks.json` — his
    «otro usuario podría querer Zoom», one file away): what «done» means, what must be known first, how the
    thing is done well, what ends it. Three properties keep it a shortcut and not a fence, each a test: an
    errand with NO playbook still runs, the operator's file wins, and nothing in it names a person, a company
    or a site — swap reunión→cena→taller and it stands.
  - **It closes on the product's own truth**: `verify.py` asks the agenda, ignores a meeting he ALREADY had
    (or last week's dentist closes today's errand), and answers None when it cannot read — which closes
    nothing, because a wrong «ya está» is the exact lie the V2-660 harness was built against.
  - ⚠️ **The ratchet caught a DESIGN mistake, not just a size**: the errand rows were being merged inside
    `dispatch.active_sessions()`, which feeds the stall detector, the susurro's dedup and the worker ledger
    — all three reasoning about a PROCESS, to which «waiting three hours for somebody to answer» reads as a
    stuck worker. Moved to the `/api/tasks` route (the operator's board); the brain has its own seam, the
    context pack. `dispatch.py` ended UNCHANGED and `memory/api.py` too (the facade went to
    `memory/errands_store.py`), both paid by extraction and never by a higher ceiling.
  - ⚠️ **Twenty green disarms across the batch, and they split three ways**: a guard that guarded NOTHING
    (deleted, V2-655's rule), tests that measured with values where the mutation changed nothing (a window
    equal to the default, a ceiling the grammar rejected, a numeric id where the point was a non-numeric
    one), and — three times — a property genuinely held by TWO independent guards, re-anchored on the
    load-bearing one, with the one that cannot be disarmed alone SAYING SO in the test instead of pretending.
    Sixty-three disarms in total, every mutation asserted, all red.
  - Nodes **4.96**, **4.166**, **5.24**, **3.41** and **3.42** (105 cases). ⚠️ **NOT verified live**: no
    real message has been sent by this path and no real person has answered one — which is what shadow mode
    is for. **NOT built**: the Meet link (`conferenceData.createRequest`, one small gap) waits on
    `connectors/calendar/` being committed by the session that owns it; and the messaging widget's prompt
    debt (a legacy 2 090-char `[[msg.*]]` protocol duplicating its 26 declared actions, and no
    `prompt_digest`) is named in the initiative and deliberately left alone: retiring the protocol and
    adding the digest are two halves of ONE swap on a live path, and that deserves its own batch.

- **A SET PHRASE is answered from a table, in any language — the phrasebook (V2-674, 2026-09-11)**: the
  operator, after starting a session in ENGLISH to check the product is language agnostic — «le digo hola y
  me dice un segundo o check-in, o sea, ¿qué vas a chequear si te acabo de decir hola?… ya lo pedí, una serie
  de frases hechas que estuvieran ya preseteadas en el idioma, en una hash table de saludos». **MEASURED in
  that session's own observability (sid fdd096a3 / daa7a385) before writing a line**: «Hello and good
  morning. How are you?» cost a **3 440 ms** model call covered by «Let me explain…»; «You were saying?» got
  «One sec, checking…» and then an **INVENTED errand** («there's a WhatsApp message from Jo that came in as
  an image»), assembled out of a memory pill; «Hey, mate. You there?» got «Let me check that for you…». None
  of the three is a request. **The mechanism already existed for a narrower case**: `presence.py` answers
  «¿sigues ahí?» from a pool, with no model and no tool. This is the same idea widened to the phrases that
  open, close and cushion a conversation — greeting, «¿qué tal?», «gracias», «adiós» — and one more that only
  exists as a pair («bien» means «I'm fine» ONLY when our own previous reply handed the question back;
  otherwise it is the answer to something WE asked, which is V2-665's defect with the roles reversed).
  **It is DATA and not a regex, and that is the whole reason it earns the words «language agnostic»**:
  `presence.py`'s regex is Spanish + English and structurally cannot grow to forty languages, so cues and
  replies hang off `LangSpec.smalltalk` (es/en, verified native) and `i18n/init/smalltalk.py` GENERATES a pack
  for any other language at onboarding, beside the alias pack that has been doing exactly this since V2-101.
  A language with neither answers `{}` — the lane declines and the model answers, as before. **Matching is
  deliberately strict**: the whole utterance must decompose into cues, generic forms of address and the
  language's own coordinating words («hello AND good morning» is two phrases with no punctuation between
  them, which is how he actually said it), and ONE unknown word hands the turn back untouched. The asymmetry
  is the point — answering «hola» with a model costs three seconds, and answering a real request with «¡Hola!
  Dime.» is a broken product — so the refusing cases carry most of the test weight. Replies come from a pool
  avoiding the last one used, per his «una especie de diálogo heurístico, un poco random»; and the
  `bounces`/`after_bounce` flags are OURS and never the translator's, because they encode a rule about the
  CONVERSATION and a pack that could set them would quietly change how the lane behaves. Two smaller findings
  from the same three sentences shipped with it: the presence knock now strips generic forms of address
  **wherever they appear** (the only word standing between «Hey, mate. You there?» and the lane that answers
  it was «mate»), and «you were saying» joins the social filler class so a question about the conversation
  stops arming a cover that promises to go and look at something. Node **3.37**; ten disarms, mutations
  asserted, all red. Ratchet paid by EXTRACTING: the probe's three deterministic lanes are one call now
  (`probe_actionmap.try_fast_lanes`, 1147 → 1138), and the three wiring guards that named `probe.py` name the
  CHANNEL instead, per V2-555.

- **A PHASE of the relationship has its own prompt, and it archives itself — context packs (V2-675,
  2026-09-11)**: the operator's second half of the same message — «una excepción al inicio en el que la
  conversación fuera guiada por el agente… ¿quién eres? ¿cómo te llamas? ¿dónde vives? ¿qué podría hacer por
  ti?», «tiene que conocerse a sí mismo y saber quién es y sus capacidades», and the architectural ask that
  outlives the feature: «este sistema de prompts que podamos inyectar en ciertas fases o en ciertos momentos
  o en ciertas situaciones es un sistema bastante potente que podría formar parte de nuestra arquitectura…
  de momento solo tendrá esta parte inicial», with the closing rule — «cuando ya hemos terminado con eso,
  esos prompts iniciales desaparecen y ya pasamos a la fase normal». **Three things already put text in the
  turn and none of them is this**: the resource layer is what the agent ALWAYS is (and is cached as the
  stable prefix, V2-536, which is precisely why a phase block may never live there — a cached block keeps
  being spoken after its phase is over); `_directive_block` is ONE style preference he gave this session;
  `live_state()` is what is true this second. A pack is the fourth thing, and the registry
  (`nucleo/context_packs/`) enforces what keeps it from becoming a permanent tax: it is re-judged EVERY turn
  from a cheap local read, an archived pack answers False for good, and **the catch is PER PACK** — one net
  around the whole section would let a single broken pack silently delete every other phase's contribution,
  producing a turn that looks exactly like the steady state. **The INTRODUCTION is the only pack today**, and
  it was measured first: the kickoff asked his name, he answered around it, and `operator_name` was still
  `None` three sessions later — there WAS no phase, so whether the two ever met depended on whether one
  greeting happened to land. The block says what to DO this turn and never what the agent IS, asks ONE thing
  at a time and drops it if he deflects, and **deliberately does not list the widgets**: the resource layer
  already carries the live catalog in the same prompt, and a second inventory written by hand is how two
  lists end up disagreeing (V2-594, V2-603). His «tampoco hace falta que se pase cuatro minutos hablando» is
  in there as a hard rule: two or three capabilities chosen from what he has already said about himself, then
  stop. **Closing it is the hard half**, and he asked for it to be ours and, where needed, a model's: three
  exits, cheapest first — DETERMINISTIC (we know his name, the one fact the phase exists to learn, and the
  memory writes it on its own, so the common case ends with no extra call at all), a JUDGE off the hot path
  and rationed (nothing is settled before four turns, then one call every four), and a CAP (an introduction
  still running after thirty turns is not introducing). **An unreachable judge leaves the phase OPEN** — a
  network blip must not silently skip the introduction — while unreadable settings mean NO phase, because a
  missing block costs a plainer first conversation and a block that cannot be turned off costs every turn
  forever. Watched from the bus (`turn.completed`), the Susurro/actionmap pattern: zero coupling with the
  voice provider, and it covers BOTH channels for free. The flag lives in `AGENT_KEYS`, so a factory reset
  correctly starts the relationship over. **And the phrasebook of V2-674 stands aside while a phase is
  guiding**: during the introduction «hola» is not small talk, it is the first move of a conversation that
  has somewhere to go — his own «excepción al inicio», and the reason the two batches are one. Node **3.38**;
  seventeen disarms, mutations asserted, all red — one came back GREEN and the TEST was wrong: it measured
  `compose()`'s outer net instead of the per-pack catch it claimed to be about, and now asserts that a
  healthy pack SURVIVES a broken neighbour. Ratchet paid by EXTRACTING the cron line to `live_blocks.py`
  (the browser/background-block precedent), and prompt.py's ceiling comes DOWN 854 → 834.

- **A config save is judged by what it LEAVES, and the suite stops writing the operator's routing (V2-673,
  2026-09-11)**: found on his LIVE engine while verifying something else — `config/v2.json` held
  `{"fast": {"provider": "aimlapi"}}` and nothing else, so the EFFECTIVE config was the broker as TITULAR of
  the voice brain (which the model table forbids outright) over a `model` and a `base_url` that were still
  DeepSeek's: one vendor's name printed over another's traffic, the V2-657 defect arriving by a new road.
  **Two faults, and the second is the one that matters.** (1) `config_api._model_mismatch` exists to stop
  exactly this and compared `patch["provider"]` against `patch["model"]` — a patch carrying ONLY a provider
  has no model IN IT to compare, and a partial write is the NORMAL shape of a config edit, so the guard was
  blind to the common case rather than to an exotic one. It reads the RESULT of the patch now, and also
  refuses a provider whose `base_url` was left behind. (2) The writer was
  `tests/infrastructure/unit/core/test_config_api_cloud_gate.py`, which POSTs a real save through the router
  and isolated NOTHING: every run of node 8.2 silently re-routed his brain, and had done since it was
  written — visible only because the new guard started refusing the incoherent result. Fixing that one file
  is not the fix: this is the THIRD time this class has been paid («a test never touches live artifacts»,
  «my suite reset its LIVE engine»), and each time the remedy was one file remembering. `config/v2.json` now
  moves to a temp path for the whole session in the ROOT `conftest.py`, beside `settings.json` and
  `widgets.store.DATA_DIR` which were already there — the routing store was simply the one this invariant
  had never reached — with its row in `test_suite_isolation`. Node **8.8**; four disarms, mutations
  asserted, all red. ⚠️ **A rule every test has to remember is not a rule**, and an unisolated test does not
  fail: it leaves something behind.

- **The DEPLOYMENT picks the profile — nobody is asked, and one default replaces two (V2-671,
  2026-09-11)**: the operator, shown the first-run wizard again after a factory reset — «el paso de si
  quiero una instalación local o remota es absurdo porque tú ya sabes si estás corriendo en el ordenador
  del cliente o la versión de la nube. Entonces esa pregunta va fuera» — and, about the damage it had
  already done, «ni siquiera es una opción en el reset que se altere la configuración del sistema».
  **MEASURED on his own install**: his engine came back on `qwen2.5:14b-instruct` over Ollama with
  `whisper_local` + `kokoro_local`, against the canonical table's `deepseek-v4-pro` + `deepgram` +
  `elevenlabs`. The reset did NOT do that, and the chain is the finding: V2-670 put `wizard_done` in
  `AGENT_KEYS` → the reset dropped it → `_first_run()` went True → `main.js` opened the wizard → it
  recommended `local` (correctly, by its own rules, on Apple Silicon with Ollama running) →
  `profiles.apply()` writes `settings.json` **and** `config/v2.json` as one coordinated lever. **The four
  install keys V2-670 deliberately preserved were preserved, and overwritten twenty seconds later**, along
  with the model routing the Reset dialog promises in writing is never touched — a hint that was therefore
  false, and is true again. Fixes: `_first_run()` returns False in BOTH deployments (a cloud account was
  already exempt, so the question only ever reached a self-hosted human — and asked them, in English,
  before they had chosen a language, to arbitrate between two provider stacks BY NAME; the panel stays
  reachable from 🧭, because wanting local models is legitimate and having it decided FOR you is not);
  `config/profiles.DEFAULT` becomes the canonical table's stack, ending the older fault underneath — **two
  defaults for one concept**, `profiles.py` saying `local` while `voice/engine/core/profile.py` said
  `remote`, whose `remote` row also named `voxtral` + `cartesia` against the table's `deepgram` +
  `elevenlabs` while NOTHING compared the two (that row is what a bare boot uses: every fresh install and
  every factory reset, so the drift shipped a voice stack nobody chose); `profiles.deployment()` reads
  WHERE the process runs from the provisioner's env var and is deliberately independent of WHICH providers
  the profile names — they share a word and are not the same question, and conflating them is what made the
  wizard's answer damaging rather than merely redundant; and `wizard_done` moves to `INSTALL_KEYS`, since
  it records something about the INSTALLATION and having it on the agent side is what let a reset arm the
  wizard. Node **8.5**, whose engine-row assertion is measured AGAINST `config/models.default.json` so a
  table change goes red instead of drifting; five disarms, mutations asserted, all red. The operator's own
  install was restored in the same pass (`settings.json` emptied, the wizard-written `fast`/`memory`
  sections dropped from `v2.json`) so the table governs again.

- **NOBODY SPEAKS before a language is chosen — the wordless picker, the voice that follows the language,
  and where the files live (V2-672, 2026-09-11)**: the operator on his fresh install — «me pide los
  idiomas, pero por detrás está hablando ya en un idioma por defecto… **no quiero que la gente hable hasta
  que no hayamos seleccionado el idioma**» — and «la voz que viene por defecto en español habla bien
  español, pero habla mal inglés… si hay alguien que habla chino o alemán o suajili tenemos que ponerle una
  voz que esté entrenada para esos idiomas». **Both were WRITTEN DECISIONS, not slips**: `agent.py` said
  the question «HAS to go out now, in English (the product default)» and the kickoff began `[FIRST RUN …
  SPEAK ENGLISH ONLY]`, so the one sentence a person could not understand was the one asking which language
  they understand; and `core/config.py` hardcoded `elevenlabs_voice_id` to a Castilian voice chosen by
  V2-035 when the product spoke one language. **MEASURED against the live API before a line was written**:
  `/v1/voices` returns the ACCOUNT's voices and **all 21 premade ones are `language: en`**, so that set
  structurally cannot answer «a voice trained for German»; `/v1/shared-voices?language=<code>` returns real
  NATIVE voices (es → latin american, peruvian; zh → beijing/taiwan mandarin) and honestly returns ZERO for
  Swahili; and a shared-library id works DIRECTLY in text-to-speech with no «add to my voices» step
  (verified with a nine-character synthesis) — without that last one this would have shipped a picker full
  of ids that 400. Also measured: the `.env` copy of the key on this machine answers **401** while the
  credential store's answers 200, so the new module asks the store first and says why. Built: **(1)** the
  first-run branch RETURNS — the session still starts (the mic must be live to hear a spoken answer) and
  says nothing, and the first thing anyone hears is `onboarding.confirmSpoken` in the language they just
  chose, which is also the greeting. **(2)** `i18n/catalog.py` + a rewritten picker that carries no word of
  ours: a speaking mark, then 40 rows of flag + the language's OWN native name, `en`/`es` pinned because
  those are the two the repo SHIPS; typing FILTERS the rows instead of submitting free text, because
  submitting needed a prompt telling you to write something in a language you may not read. **(3)**
  `voice/engine/speech/elevenlabs_voices.py` ranks natives first and KEEPS the multilingual ones last (a
  language with no native voice must still speak), and the ⚙'s list is per-language like Kokoro's. The
  realignment on a language change covered KOKORO only — which is why the cloud TTS never followed — and
  now asks **`voice_is_aligned(provider, voice, lang)`**, a different question from «is it in the list»,
  and the difference IS the defect: the ElevenLabs list deliberately keeps fallbacks, so a Castilian voice
  is in the English list and a membership check would have found it and changed nothing. **(4)** the folder
  step, self-host only and skippable, running DURING the generation (his own sequencing) with its words
  riding the same SSE event already translated: `library/paths.check_base()` is a SECOND door to
  `resolve()` with a different provenance — a person, on their own machine, once — so it accepts an
  absolute path, which `resolve()` never may, and pays for that with a validator that REFUSES instead of
  repairing (exists · directory · writable · never the filesystem root · never HOME itself · never a system
  directory · checked on the RESOLVED path). A cloud account is never asked: there the Volume IS the
  storage. **Two ratchets bit and both were right**: the energy sweep caught the new API calls (exempted —
  ElevenLabs bills per synthesised character and these two endpoints are metadata), and the dependency
  ratchet refused `i18n` reaching into the motor's voice catalog, so the alignment came out of `lock()` and
  lives only in `settings.update()`, the one seam every language writer already goes through. Nodes
  **8.6**, **8.7** and **4.162** (RENDERED); twenty-four disarms, mutations asserted, all red. ⚠️ **The
  rendered node caught a defect on its first run that no source read could**: the speaking mark was mounted
  with `innerHTML`, a prop `dom.js::h()` does not know, so it was set as a plain attribute and painted
  nothing. ⚠️ **And the path validator over-refused on macOS**: `/var` resolves to `/private/var` and the
  per-user temp directory lives under it, so the prefix ban refused an ordinary writable folder belonging
  to the person choosing — `/var` came out, because on Linux it is root-owned and the writability check was
  doing the work anyway. **NOT verified**: the native folder dialog headless (it cannot be), and the whole
  ceremony driven end to end by the operator.

- **A turn that calls a TOOL is covered at the SEAM (V2-669, 2026-09-11)**: the operator, after the engine
  moved onto the slower/better model — «si una pregunta como a qué hora tengo esta actividad en la agenda
  tarda 8 segundos en resolverse, necesitamos alguna frase o palabra de relleno… o incluso más rápido que
  dijera "dame unos segundos", porque si tenemos una locución demasiado larga alargaremos innecesariamente el
  tiempo de respuesta». **Measured in his own observability before building anything** (`deepseek-v4-pro`):
  the `read_widget` turn answering «¿a qué hora tengo la cita con Hacienda?» took **6 029 ms with
  `ttft_ms: 0`** — the first pass returned a TOOL CALL and no text, so the reply stream stayed empty for the
  whole turn — and across **7 real voice turns on a light route the turn ENDED 3.4-5.9 s AFTER the tool
  event**, while the lead-in filler had sounded 1.0-3.3 s BEFORE it. Its ~1 s of audio was long over. Nothing
  covered that stretch: both light-route branches went straight from the tool decision into the second pass,
  and the `emit()` beside them is observability, not a mouth. **The lead-in cannot fix this by construction**:
  it is chosen ~1.1 s in, before any model has spoken, so it can only ever be a blind thinking sound. The
  node now keeps racing the model's first chunk after the lead-in settles and covers a SECOND time when the
  provider publishes a work note at the seam (`filler_audio.note_work`, called from `read_widget`, `recall`
  and `web_search`). **The cover NAMES the source** — «Lo miro en Agenda…», «Lo busco en internet…» — which
  is the one thing the blind lead-in could not say, and is what keeps two covers from reading as the same
  wait said twice: the failure this codebase already met once (V2-189, session 2bdc67ee, «Déjame que mire…»
  then «Vale, dame un momento que lo miro.»). Guards, each disarmed: a second pass that answers inside
  `_WORK_GRACE_S` beats it and nothing is said; it never sounds within `_COVER_MIN_GAP_S` of the lead-in's
  FIRE (measured from the fire, because this node cannot know how long the TTS took); at most one per turn;
  `fillers: off` silences it; it is stripped from the forwarded transcript; and it updates anti-echo but
  **never `_last_reply`** — a cover carries no topic either, and feeding one to the directed-content judge is
  the 2026-08-17 bug. Pools are per language (`covers_widget`/`covers_search`/`covers_recall`, es+en) behind
  the same generated-pack seam the fillers use, so an onboarded language can eventually ship its own; a
  length ceiling is enforced in the test, because **a cover cannot be cut mid-sentence, so its own length IS
  latency** (his rule). **VOICE ONLY, and the module says why**: the text channel has no dead air to fill, so
  the parallel-implementation rule (V2-252) deliberately does not reach this one — written down instead of
  left as drift, with a guard that keeps `note_work` out of `probe.py`. Node **2.53**; eight disarms, each
  mutation asserted before measuring, all red. ⚠️ **Two of them were MINE and green at first**: one left the
  banned call alive inside the comment that replaced it, and one anchored on a line `pick_filler` carries
  BYTE-IDENTICALLY, so it mutated the wrong function (the V2-571 lesson). ⚠️ **And the harness left a
  mutation in the tree**: the mutation-landed assertion raised BEFORE the restore line, so a weakened
  `pick_filler` sat in the working tree after the sweep had already gone green — the restore is in a
  `finally` now. Also fixed here, and the same class: `test_filler_path_never_writes_last_reply` banned the
  string `_last_reply` in the whole file, so DOCUMENTING that rule in a comment turned it red (V2-615's trap);
  it reads comment-stripped code now and asserts BOTH mouths keep anti-echo. **Measured and NOT built,
  reported instead**: the second pass runs on the TURN's spec, so `deepseek-v4-pro` is paid twice per light
  route — 18 samples over the real agenda block put `deepseek-v4-flash` at **715-868 ms TTFT vs 805-949 ms**
  and **909-1 155 ms total vs 1 248-1 769 ms**, with **zero confabulation in 6/6 runs** of the two
  answer-is-absent cases (it states the absence AND names what IS there). The recorded reason pro holds the
  seat is a ROUTING bench («Pro routes 41/42, direct Flash 38/42»), and the second pass does no routing — but
  the allocation table is the operator's and `voice_brain` has no failover, so a split would add a second
  failure surface. His call.

- **A question about what a widget HOLDS is answered by the widget (V2-668, 2026-09-11)** — texto íntegro en `decisions-archive.md`
- **An order NAMES its target, and a notice waits its turn (V2-666, 2026-09-11)** — texto íntegro en
  `decisions-archive.md`; cita además V2-584, V2-651, V2-656, V2-661, V2-667
- **THE MICROPHONE SWITCH has ONE door, and it is not the wake-word mode (V2-654, 2026-09-10)** — texto
  íntegro en `decisions-archive.md`; cita además V2-651

### Archived decisions — index (full text: `.meshkore/docs/decisions-archive.md`)

#### Movidas el 2026-09-23 (V2-757)

- **A question about what a widget HOLDS is answered by the widget (V2-668, 2026-09-11)**
- **An order NAMES its target, and a notice waits its turn (V2-666, 2026-09-11)**
- **THE MICROPHONE SWITCH has ONE door, and it is not the wake-word mode (V2-654, 2026-09-10)**

#### Movidas el 2026-09-23 (V2-756)

- **A replayed play order is an order — and the playlist keeps the playback it started (V2-650, 2026-09-10)**
- **A REPORT is delivered as a DOCUMENT — the `informe` surface (V2-644, 2026-09-09)**
- **The orb answers ONE question, and a stopped mic is crossed out (V2-648, 2026-09-10)**

#### Movidas el 2026-09-23 (V2-755)

- **The room is not the operator (V2-647, 2026-09-09)**
- **A typed message is never lost (V2-646, 2026-09-09)**
- **A cover never ends the turn, and covers describe MOTION (V2-642, 2026-09-09)**

#### Movidas el 2026-09-23 (V2-754)

- **Covers that LISTEN, and the presence fast lane (V2-640, 2026-09-09)**
- **The desktop wallpaper is a SPOKEN property (V2-641, 2026-09-09)**

#### Movidas el 2026-09-23 (V2-753)

- **The agent gets its OWN filesystem, and the torrent client becomes a SYSTEM tool (V2-638, 2026-09-09)**

#### Movidas el 2026-09-22 (V2-752)

- **The agenda answers to the voice: the view alias, the missing vocabulary, the visible details, and the operator's language (V2-639, 2026-09-09)** (V2-639)
- **The agenda looks like a CALENDAR — the shapes everybody already knows (V2-643, 2026-09-09)** (V2-643)


#### Movidas el 2026-09-22 (V2-751)

- A canvas mutation needs the operator's words — and a known order survives the wake word (V2-635, 2026-09-09) — V2-635, V2-095, V2-633
- The video widget dresses like the product (V2-636, 2026-09-09) — V2-636, V2-557, V2-608
- An embedded torrent client, so a magnet becomes a video playing INSIDE the agent (V2-637, 2026-09-09) — V2-637, V2-603, V2-124, V2-544, V2-561
- An unplayable video is swapped, not served — and the silent turn must not apologize (V2-634, 2026-09-09) — V2-634, V2-613, V2-633

#### Movidas el 2026-09-22 (V2-749)

- The genesis rules govern the engine's OWN mouths — a short order runs in silence, and a spoken rule
  rules the very next turn (V2-633, 2026-09-09) — V2-633, V2-572, V2-555
- The video widget becomes a real player: tabs, a dashboard that carries the search, and the honest
  shelf of sources (V2-632, 2026-09-09) — V2-632, V2-630, V2-366, V2-597, V2-604, V2-626, V2-576, V2-547, V2-609, V2-557, INI-032, V2-526
- A card's size never follows its content (V2-630, 2026-09-09) — V2-630
- The free source CAN skip, and a narrated close is not an order (V2-631, 2026-09-09) — V2-631, V2-526

#### Movidas el 2026-09-21 (V2-747)

- **Messaging pro: fetch on demand, per-platform view criteria, `peek` for analysis, and the autoresponder (V2-624, 2026-09-09)** (2026-09-09; INI-014, V2-540, V2-571, V2-607, V2-624)
- **Choosing a channel is ONE state transition, not a filter assignment (V2-626, 2026-09-09)** (2026-09-09; INI-032, V2-610, V2-626)
- **⏻ ON took two presses: two right fixes from the same day, racing (V2-627, 2026-09-09)** (2026-09-09; V2-627)
- **The music widget brings real cover art, fast first, then enhancements (V2-629, 2026-09-09)** (2026-09-09; V2-557, V2-629)


#### Movidas el 2026-09-21 (V2-744)

- **A redundant media label, and a thread/mail screen stops stacking the dashboard header above its own (V2-622, 2026-09-08)** (2026-09-08; V2-561, V2-620, V2-622)
- **The system bar rotates to the BOTTOM, the orb swaps into its centre, and 🧠 moves upstairs (V2-623, 2026-09-08)** (2026-09-08; V2-124, V2-619, V2-622, V2-623)
- **The chat header names its tab, wide tabs keep their icons, and the ⧉ toggles BOTH ways (V2-621, 2026-09-08)** (2026-09-08; V2-608, V2-619, V2-621)
- **A screen change resets the scroller, "Volver" becomes a real button, each platform gets its own color, and a voice note can actually be dragged (V2-620, 2026-09-08)** (2026-09-08; V2-557, V2-618, V2-620)

#### Movidas el 2026-09-21 (V2-741)
 - **Connecting an account is ONE step, and a failed data-op corrects the claim it already made (V2-603, 2026-09-06)** (2026-09-06; V2-603)
 - **The music widget goes pro — a shared artist is said ONCE, and the play button lives on the art (V2-612, 2026-09-07)** (2026-09-07; V2-612)
 - **The skin is DATA: design profiles in ⚙ Apariencia, custom knobs, and the graphite default (V2-617, 2026-09-08)** (2026-09-08; V2-617)
 - **- **Chrome polish on the new skin: the composer writes, the tabs adapt, the rail never hides, and ONE grip** (?; )
 - **- **The widget layer gets its i18n seam — `ctx.t`/`ctx.lang`, and two pilots prove it (V2-613,** (?; V2-613)

#### Movidas el 2026-09-21 (V2-726)

- **Messaging reads like a chat, and the card chrome stops looking like two headers (V2-618, 2026-09-08)** (2026-09-08; V2-546, V2-608, V2-618)
- **A widget's root actually uses the width of the card it is given (V2-615, 2026-09-08)** (2026-09-08; V2-574, V2-615)
- **A Reset does not leave a CONNECTED mailbox mute (V2-614, 2026-09-08)** (2026-09-08; V2-606, V2-607, V2-614)

- **The stop record declares its own lifespan (V2-568, 2026-09-03)** (2026-09-03; V2-567, V2-568)
- **A spoken correction reaches the SLOTLESS pill it corrects (V2-565, 2026-09-03)** (2026-09-03; V2-498, V2-536, V2-565)
- **A screen belongs to ONE connector, and a picker is a grid you can already see (V2-561, 2026-09-03)** (2026-09-03; V2-520, V2-526, V2-559, V2-561)
- **A fresh Volume has no directories, and a session born LAZILY told nobody (V2-562, 2026-09-03)** (2026-09-03; V2-102, V2-562)
- **The picture was never missing, only OUR COPY of it (V2-563, 2026-09-03)** (2026-09-03; V2-466, V2-563)
- **Google Photos via the PICKER, and a real gallery has to VIRTUALIZE its grid (V2-564, 2026-09-03)** (2026-09-03; V2-547, V2-564)
- **A follow-up is not a new errand, and an alias fragment is not a name (V2-566, 2026-09-03)** (2026-09-03; V2-565, V2-566)
- **One widget order, ONE mutation — and the boring ones never wait for a model (V2-567, 2026-09-03)** (2026-09-03; V2-210, V2-526, V2-539, V2-564, V2-567)
- **A DELIVERED hunt is not re-hunted in parallel — the linear gate (V2-570, 2026-09-03)** (2026-09-03; V2-095, V2-199, V2-222, V2-259, V2-453, V2-556, V2-566, V2-570)
- **ONE widget per errand — the browser lives INSIDE the sheet's process tab (V2-571, 2026-09-03)** (2026-09-03; V2-202, V2-434, V2-538, V2-539, V2-540, V2-562, V2-571)

- **El worker escribe lo natural y el CLI le cobraba el turno — tres formas más (V2-341, 2026-08-26)** (2026-08-26; V2-123, V2-248, V2-253, V2-306, V2-341)
- **Las dos puertas del motor le decían cosas opuestas al mismo worker (V2-350, 2026-08-26)** (2026-08-26; V2-350)
- **Un contratiempo también se cuenta: solo las buenas noticias llevaban un «cuéntalo» (V2-348, 2026-08-26)** (2026-08-26; V2-131, V2-133, V2-222, V2-276, V2-348)
- **Un nombre que comparten todas las filas no nombra a ninguna (V2-346, 2026-08-26)** (2026-08-26; V2-334, V2-345, V2-346, V2-347)
- **Una ruta que comparten decenas de anclas no es la ficha de nada (V2-334, 2026-08-26)** (2026-08-26; V2-320, V2-334)
- **Sin filas no se puede pedir que las cuente (V2-330, 2026-08-25)** (2026-08-25; V2-298, V2-330)
- **El informe dice qué nombró ZAELAR él mismo (V2-329, 2026-08-25)** (2026-08-25; V2-329)
- **Un SUPERÍNDICE no es parte del número (V2-326, 2026-08-25)** (2026-08-25; V2-326)
- **Pedir ayuda no es equivocarse (V2-325, 2026-08-25)** (2026-08-25; V2-325)
- **Cuando dos anclas apuntan al mismo anuncio, gana la que lo NOMBRA (V2-324, 2026-08-25)** (2026-08-25; V2-234, V2-324)
- **«Cero filas» no es «sin resultados» (V2-323, 2026-08-25)** (2026-08-25; V2-294, V2-323)
- **Verificar el ARREGLO no es verificar el CASO (V2-322, 2026-08-25)** (2026-08-25; V2-321, V2-322)
- **Una FECHA no es un teléfono, y la diferencia costaba la hoja entera (V2-321, 2026-08-25)** (2026-08-25; V2-321)
- **Las tools, de menos a más (2026-08-02, norma del operador)** (2026-08-02; no refs)
- **El FlashBrain se queda en DeepSeek V4 Flash — y la latencia NO es del prompt (2026-08-02)** (2026-08-02; no refs)
- **Dominios públicos → motor local (CERRADO 2026-07-22)** (2026-07-22; no refs)
- **Motor de voz = LiveKit Agents** (2026-07-29; INI-012)
- **Cerebro propio «Colmena» — FlashBrain ORQUESTADOR + workers Claude Code** (2026-07-13; V2-036)
- **Workers Claude Code = memoria serial + reporte por el bus + pool** (2026-07-16; V2-036)
- **Brain Workers INTERACTIVOS — sesiones vivas, bidireccionales y AGNÓSTICAS del motor** (2026-07-14; V2-029, V2-038, V2-063, V2-084)
- **UN BRAIN WORKER HACE CASI DE TODO — la seguridad es un FILTRO, no una lista corta de permisos** (2026-08-21; V2-117, V2-236)
- **Gate de ATENCIÓN — el micro abierto no actúa sobre voz ambiente** (2026-07-09; V2-015)
- **Latencia del turno — la memoria FUERA del camino caliente** (sin fecha; V2-011)
- **Circuito de CORTO PLAZO de interacción con el operador** (2026-07-14; V2-035)
- **El canvas es AUTORITATIVO — reconciliar al (re)conectar** (2026-07-14; V2-035)
- **ESTADO = contexto VARIABLE con UI vivo — el cerebro sabe lo que el operador tiene DELANTE** (sin fecha; V2-011)
- **RAILS — comportamientos comunes CONDUCIDOS** (sin fecha; V2-042, V2-047)
- **- **«Sistema arena» — rails/widgets/tools auto-generados, BRAIN RULES + USER RULES, genética (V2-046, DISEÑO** (2026-07-16; V2-042, V2-045, V2-046)
- **- **Bóveda de secretos del operador — cifrado E2E + passkeys (V2-060, CONSTRUIDO 2026-07-21, rama** (2026-07-21; V2-046, V2-060)
- **«Susurro» — auto-auditoría conversacional y mejora continua** (2026-08-09; V2-053, V2-061)
- **Acciones ENCADENADAS realidad↔widgets↔memoria + inteligencia asertiva de DOS velocidades** (2026-07-21; V2-061)
- **Búsqueda web = capacidad COMPARTIDA por los dos cerebros, model-agnóstica** (sin fecha; V2-011, V2-022, V2-024)
- **Prewarm del camino caliente en el ARRANQUE** (sin fecha; V2-024)
- **Prompt del FlashBrain = ESTADO compuesto + petición, ~30 líneas (no ~280)** (2026-07-11; V2-011, V2-027, V2-028, V2-029)
- **ORDEN DE PROVEEDORES — DeepSeek V4 DIRECTO primero, luego el broker, y solo al final OpenAI/Anthropic** (2026-08-19; no refs)
- **Cerebro de voz = NO-razonador** (sin fecha; no refs)
- **- **ORDEN DE PROVEEDOR — DeepSeek V4 DIRECTO primero, broker después, OpenAI/Anthropic el último (NORMA del** (2026-08-19; V2-097)
- **Routing de modelos — POR INVOCACIÓN** (2026-08-19; V2-034, V2-077, V2-097)
- **Memoria central** (2026-08-16; V2-013, V2-056)
- **Recuperación del recall LARGO = RERANKER model-agnostic, LOCAL por defecto** (2026-07-12; V2-030, V2-031)
- **Sistema Nervioso** (sin fecha; no refs)
- **Perfiles remote/local** (sin fecha; no refs)
- **Multidioma con catálogo alineado** (sin fecha; no refs)
- **UI multilingüe que se adapta a CUALQUIER idioma** (2026-08-09; V2-089)
- **La autodetección de idioma colgaba SOLO de la voz — un canal de texto se quedaba en inglés para siempre** (2026-08-20; V2-101, V2-170)
- **TTS local por hardware (Metal)** (sin fecha; no refs)
- **TTS cloud FIABLE — ElevenLabs** (2026-07-13; V2-035)
- **STT local por hardware** (2026-07-12; no refs)
- **Sistema de widgets** (sin fecha; V2-017, V2-025)
- **Nombres + alias de widgets con CERTEZA de enrutamiento** (2026-08-01; V2-082)
- **CHAT y VOZ, INDEPENDIENTES — el icono es el único dueño del silencio** (2026-08-02; V2-054, V2-088)
- **El icono del altavoz MANDA — un solo interruptor para la voz** (2026-08-01; V2-087)
- **La RED es NATIVA, y hay clusters PÚBLICOS** (2026-08-01; V2-082, V2-086)
- **Selección PROGRESIVA de capacidades — el prompt es O(K), no O(N)** (2026-08-02; V2-035, V2-078, V2-082, V2-085)
- **Acciones de widget = FRONTERA datos/código + gate de irreversibilidad (NO de escalado)** (2026-07-11; V2-025)
- **Data-ops por FUNCTION-CALLING + resolución de referencias a items** (2026-07-11; V2-025, V2-026)
- **Widgets en BACKGROUND — ejecución OFF-SCREEN con ciclo declarado** (2026-07-12; V2-034)
- **Ciclo de vida de widgets + memoria — CREAR/MODIFICAR = SlowBrain; BORRAR = FlashBrain con confirmación** (2026-07-09; V2-017)
- **Widgets "backed" + supervisor** (sin fecha; INI-016)
- **navegador — navegador web REAL + agente de tareas web** (sin fecha; INI-016)
- **navegador — TAREAS: una tarea = una tarjeta = una pestaña** (sin fecha; INI-016)
- **El navegador es el ÚLTIMO recurso: primero se le pregunta a la RED** (2026-08-19; V2-167, V2-169)
- **Un código de idioma inventado no falla: es un idioma** (2026-08-21; V2-171, V2-248, V2-249, V2-251)
- **Un informe de lo que ya pasó no es una orden** (2026-08-21; V2-039, V2-047, V2-259, V2-261)
- **Dos búsquedas son dos hojas, y estrenar deja de significar borrar** (2026-08-21; V2-242, V2-257, V2-259)
- **El navegador MUESTRA y la hoja GUARDA** (2026-08-21; V2-192, V2-200, V2-223, V2-240, V2-257)
- **Un formulario que calla no se distingue de uno que funciona** (2026-08-21; V2-124, V2-256)
- **Para vigilar el ARTEFACTO, el artefacto tiene que contener lo que se comprueba** (2026-08-21; V2-171, V2-195, V2-253, V2-254, V2-255)
- **La regla estaba escrita en TRES sitios y aplicada en UNO** (2026-08-21; V2-242, V2-252, V2-253, V2-254)
- **Unos argumentos ILEGIBLES no son una acción sin argumentos** (2026-08-21; V2-171, V2-253)
- **El canal de TEXTO no relevaba — y era la TERCERA vez que `probe.py` se separaba del provider de voz** (2026-08-21; V2-252)
- **Un solo reloj para el «hoy» que se le DICE al worker** (2026-08-21; V2-250)
- **La píldora que se auto-avala: un aviso PROGRAMADO existe de verdad, o no se dice** (2026-08-21; V2-219, V2-249)
- **Un `ref` caducado decía QUÉ pasaba y no CÓMO salir** (2026-08-21; V2-203, V2-212, V2-236, V2-241, V2-247, V2-248)
- **Traer el elemento a la vista es una CORTESÍA, no el clic** (2026-08-21; V2-236, V2-247)
- **Un escalón que se atasca SIEMPRE no se penalizaba nunca** (2026-08-21; V2-244, V2-246)
- **Callar un escalón es legítimo; callar QUE LO CALLAS, no** (2026-08-21; V2-244)
- **246 tests verdes que ninguna suite ejecutaba, y TRES formas de desaparecer** (2026-08-21; V2-098, V2-243, V2-245)
- **Un SALDO agotado no es una cuota, y quedarse sin proveedor no es un tropiezo** (2026-08-21; V2-098, V2-158, V2-243)
- **Una píldora de fondo no es un hecho sobre la persona** (2026-08-21; V2-242)
- **La puerta avisaba UNA vez y el worker chocó TRES** (2026-08-21; V2-211, V2-236, V2-241)
- **El extractor exigía PRECIO, así que un fontanero devolvía CERO filas** (2026-08-21; V2-236, V2-240)
- **Un RELEVO no es una muerte** (2026-08-21; V2-198, V2-222, V2-237, V2-238, V2-239)
- **Un `native_sid` que MATÓ a un worker no se vuelve a armar** (2026-08-21; V2-237, V2-239)
- **La búsqueda dio la respuesta perfecta y MURIÓ dentro del worker** (2026-08-21; V2-199, V2-223, V2-226, V2-236)
- **El extractor PARTÍA el precio y no cogía el nombre** (2026-08-21; V2-234, V2-235)
- **La nota llevaba delante el CROMO DE NAVEGACIÓN, y el turno describió eso** (2026-08-20; V2-223, V2-234)
- **UN ENCARGO, UNA SUPERFICIE: el panal de hexágonos se RETIRA** (2026-08-20; V2-233)
- **El contrato de pantalla estaba en verde y el operador seguía sin ver nada** (2026-08-20; V2-199, V2-227, V2-233)
- **La nota del hallazgo llevaba TRES órdenes, y el turno obedeció la del medio** (2026-08-20; V2-223, V2-224, V2-226)
- **Decirlo una vez no es olvidarlo** (2026-08-20; V2-189, V2-221, V2-224)
- **El compositor de investigación LEÍA la cadena de proveedores y nunca la ESCRIBÍA** (2026-08-25; V2-225)
- **El prompt se contradecía a sí mismo, y el turno elegía la mitad cierta** (2026-08-20; V2-199, V2-221, V2-222)
- **Lo que el navegador ENCUENTRA no llegaba a nadie** (2026-08-20; V2-215, V2-220, V2-223)
- **Una tarea de fondo MUERTA no es una pregunta pendiente** (2026-08-20; V2-185, V2-189, V2-193, V2-196, V2-198, V2-213, V2-220, V2-221)
- **El aviso proactivo existía y no tenía dónde llegar** (2026-08-20; V2-073, V2-214, V2-215, V2-220)
- **El worker dejaba de trabajar en la aridad de NUESTRO propio CLI** (2026-08-20; V2-117, V2-153, V2-219)
- **Un hecho recogido en TODAS partes y dicho en NINGUNA** (2026-08-20; V2-185, V2-193, V2-197, V2-202, V2-207, V2-211, V2-212, V2-215)
- **El aviso existía y su CONTENIDO estaba roto** (2026-08-20; V2-214)
- **DOS REGRESIONES MÍAS, medidas el mismo día y en el único caso 5/5 del tablero** (2026-08-20; V2-176, V2-202, V2-209, V2-210)
- **«Prueba otro sitio» sin decir CUÁL es un deseo, no una instrucción** (2026-08-20; V2-176, V2-185, V2-186, V2-213)
- **Un `usage` dice la FORMA, no el ERROR** (2026-08-20; V2-203, V2-212)
- **La puerta es NUESTRA: el worker se muere en ella y en silencio** (2026-08-20; V2-117, V2-202, V2-211)
- **Un dato del mundo, dicho con una cifra y sin consultar nada** (2026-08-20; V2-022, V2-135, V2-210)
- **Desde fuera del proceso, «el muro no se anotó» y «se anotó y el turno lo ignoró» se veían IDÉNTICOS** (2026-08-20; V2-176, V2-207)
- **La MISMA cita dos veces, ahora por la data-op del modelo** (2026-08-27; V2-194, V2-208)
- **«Aquí lo tienes» sobre una tarjeta vacía — y la frase es NUESTRA** (2026-08-20; V2-176, V2-209)
- **Le decíamos al worker que mirara una captura que no estaba en disco** (2026-08-20; V2-117, V2-203, V2-205)
- **El puente del payload contestaba con el OSError pelado, y el worker lo leía como un callejón sin salida** (2026-08-20; V2-117, V2-186, V2-203)
- **El confirm-gate paró un clic irreversible y no preguntó a NADIE** (2026-08-20; V2-126, V2-153, V2-202)
- **Una tarea de verificación se cuelga del CASO, no del arreglo** (2026-08-20; V2-133, V2-199, V2-200, V2-201)
- **Cada cara del bloque del navegador tiene que poder DISPARARSE** (2026-08-20; V2-176, V2-199, V2-200, V2-201)
- **El arreglo anterior no estaba roto: estaba MUERTO** (2026-08-20; V2-185, V2-192, V2-199, V2-200)
- **Un test que no recorre el camino real prueba que el código compila, no que funciona** (2026-08-20; V2-126, V2-190, V2-198, V2-199)
- **Una sesión de WORKER que acaba desaparecía del estado** (2026-08-20; V2-150, V2-197, V2-198)
- **Dos listas de estados que había que mantener sincronizadas — y `open` llevaba en el hueco desde siempre** (2026-08-20; V2-196, V2-197)
- **Una tarea CANCELADA no estaba ni viva ni terminada** (2026-08-20; V2-150, V2-176, V2-190, V2-195, V2-196)
- **La captura forense de un turno guardaba la persona y tiraba el ESTADO** (2026-08-20; V2-195)
- **La suite escribía en la agenda REAL del operador: 328 citas de prueba** (2026-08-20; V2-194)
- **La cita se apuntaba DOS veces** (sin fecha; V2-153, V2-186, V2-189, V2-194)
- **Con varias tareas vivas, el estado MANDABA entregar una y no decía cuál** (2026-08-20; V2-189, V2-192, V2-193)
- **REGRESIÓN PROPIA: pasé de demasiado optimista a demasiado pesimista** (2026-08-20; V2-185, V2-192)
- **«Sí, adelante» → «Hecho.» → «¿Ya está cancelada del todo?»** (2026-08-20; V2-176, V2-189)
- **Una tarea parada esperando a que el operador ENTRE decía «te dará el resultado sola»** (2026-08-20; INI-016, V2-167, V2-176, V2-185)
- **Un hecho que solo vive un turno es un hecho que la conversación pierde** (2026-08-20; V2-150, V2-171, V2-176, V2-190)
- **Una confirmación que CADUCA borraba el hecho de que existió** (2026-08-20; V2-138, V2-150, V2-190)
- **El relleno de espera decía CUATRO veces la misma frase, y no lo decía el modelo** (2026-08-20; V2-038, V2-133, V2-189)
- **El muro más silencioso: la página de error del PROPIO sitio** (2026-08-20; V2-187, V2-188)
- **Un hecho que no se puede decir en voz alta es un hecho que no llega** (2026-08-20; V2-145, V2-150, V2-185, V2-187)
- **El operador pidió el aviso en SUBJUNTIVO y el backstop no lo reconoció** (2026-08-20; V2-151, V2-167)
- **Una respuesta que aún PREGUNTA archivaba una cita hecha con su propia pregunta** (2026-08-20; V2-167)
- **El muro del cuerpo DISPARÓ, y el hecho se borró al re-enrutarse** (2026-08-20; V2-167, V2-176)
- **«¿Hay algo corriendo?» era la pregunta equivocada** (2026-08-20; V2-132, V2-176, V2-196)
- **Una búsqueda vacía y una búsqueda IMPOSIBLE eran el mismo dato** (2026-08-30; V2-176)
- **El traspaso de inicio de sesión no estaba cableado en el canal de TEXTO** (2026-08-20; V2-153, V2-176)
- **El día del aviso podía estar SOLO en la frase del operador** (2026-08-20; V2-121, V2-167)
- **Una fecha sola no es un compromiso** (2026-08-20; V2-167)
- **El muro y el atasco NUNCA llegaron al worker** (2026-08-20; V2-167, V2-186)
- **«No me habías pedido eso» era VERDAD** (2026-08-20; V2-176)
- **Un proveedor roto no se le decía a NADIE en el canal de texto** (2026-08-20; V2-176)
- **Un muro puede estar en el CUERPO de la página, con URL normal y status 200** (2026-08-20; V2-167)
- **El atasco llegaba al TURNO y no al WORKER** (2026-08-20; V2-167, V2-186)
- **- **Una salvedad no compite con una promesa: el estado PROMETÍA que la tarea iba a terminar sola, también** (2026-08-20; V2-152, V2-167, V2-185)
- **El turno que fija la FECHA no es el que dice el QUÉ** (2026-08-20; V2-075, V2-132, V2-151, V2-176)
- **El turno corría con un tope que NO cabía la tool más importante del sistema** (2026-08-20; V2-171)
- **Una ruta de FastAPI no sabe qué función viene detrás del decorador** (2026-08-19; V2-169)
- **navegador — AUTENTICACIÓN = abrir un navegador REAL** (2026-07-10; INI-016)
- **«Una sola mente» — el FlashBrain conduce TODA conversación** (2026-07-25; V2-069)
- **El SEGUNDO backend de Brain Worker: Codex — y su frontera de seguridad es DISTINTA** (2026-08-12; V2-010, V2-038)
- **El TERCER backend: Grok Build — y la elección de worker es una TERNA, no una casilla** (2026-08-13; no refs)
- **Los Brain Workers no dependen de UN proveedor — cadena + relevo automático** (2026-08-09; no refs)
- **Energy metering — cobertura real, no solo tabla de tarifas** (2026-08-16; INI-019, INI-020)
- **Control central de proveedores en el perfil cloud** (2026-08-05; INI-019)
- **«Homeostasis» — el LATIDO AUTÓNOMO del sistema** (2026-07-25; V2-070)
- **REHIDRATACIÓN — el trabajo que corta un reinicio se recoge, no desaparece** (2026-08-12; no refs)
- **El ESCRITORIO se rehidrata — y el `localStorage` es per-ORIGEN** (2026-08-12; no refs)
- **Canal nativo MeshKore** (2026-07-26; V2-069, V2-072, V2-075, V2-076)
- **Una tarea/flujo SOLO nace de CUATRO fuentes — el pulso NUNCA crea trabajo por tener un loop** (2026-08-16; no refs)
- **- **`voice.trace.active()` — un puntero EXPLÍCITO para eventos que el ContextVar nunca puede ver (2026-08-16,** (2026-08-16; no refs)
- **- **El gate de atención en modo `always` (el default, micro SIEMPRE abierto — permanente, NO es algo a reverti** (2026-08-17; V2-093, V2-097, V2-105, V2-109)
- **- **Fusionar dos flujos que resultan ser la MISMA tarea — la capacidad existe, el disparo automático NO (pass** (2026-08-16; V2-105)
- **El motor no arrancaba NUNCA en frío — deadlock de reentrancia en `memory/db.py::get_db()`** (2026-08-16; V2-105, V2-106)
- **Seguridad del canal de cluster** (2026-07-26; V2-021, V2-069, V2-071)
- **Reglas en TRES niveles + PACTO de conversación agente-agente** (2026-07-25; V2-046, V2-067, V2-071, V2-072)
- **Criterio de conversación por INTELIGENCIA — parar/ceder el turno cuando no fluye** (2026-07-26; V2-010, V2-073, V2-075)
- **Sello de VERSIÓN — saber qué código corre y qué versión generó cada línea** (2026-07-26; V2-074)
- **Proveedor Architect** (sin fecha; no refs)
- **Mensajería personal UNIFICADA con triaje** (sin fecha; V2-051, V2-052)
- **Configuración MANEJADA POR LA INTERFAZ — "instala una vez, todo lo demás desde la UI"** (sin fecha; V2-083)
- **Tema dark/light** (sin fecha; no refs)
- **- **Controles del orbe = «EL OJO» — 7 iconos como párpado superior + ECG como párpado inferior (el orbe = iris** (2026-07-22; V2-014, V2-016, V2-039)
- **LA PILA de Energy — el saldo se VE antes de agotarse** (2026-08-13; no refs)
- **Visor de memoria (🧠 «mapa de la memoria») — DOS VISTAS** (2026-07-10; V2-014)
- **ADMISIÓN — cuando el proceso NO es la frontera, sin sesión verificada no se sirve nada** (2026-08-13; no refs)
- **PARAR ES PARAR — el interruptor global vive en el SERVIDOR, y un widget DECLARA lo que produce** (2026-08-13; V2-039, V2-065, V2-092)
- **PARAR ES PARAR, de verdad: ni sesión fantasma con el agente parado, ni turno cortado a medias** (2026-08-15; V2-092)
- **La ESPERA se oye, y el veredicto de latencia ya puede culpar al proveedor** (sin fecha; V2-093)
- **RELEVO por latencia del cerebro de voz** (2026-08-14; V2-094, V2-097)
- **DeepSeek DIRECTO cura el TTFT, y por eso es RELEVO y no titular** (2026-08-17; V2-094, V2-097)
- **El turno se cierra cuando la frase ACABA, no cuando hay silencio** (2026-08-14; INI-012, V2-092, V2-095, V2-096, V2-102)
- **Una frase en DOS TIEMPOS es UNA petición — y el fragmento no genera nada** (2026-08-02; V2-095, V2-096)
- **SELECCIÓN PROGRESIVA de tools — el turno lleva su RUMBO, no el catálogo entero** (2026-08-02; V2-085, V2-096)
- **Architecture/modularization pass — real duplication killed, three god-files split, one deliberately NOT split** (2026-08-16; V2-095, V2-096, V2-098)
- **V2-098 follow-up: FlashBrain modularization, 9 splits executed** (2026-08-17; V2-076, V2-098, V2-108, V2-109, V2-112)
- **- **Floating feedback widget — a self-hosted engine's first outbound call, and the control-plane's first** (2026-08-16; INI-023, V2-100, V2-256)
- **First-run language onboarding — a blocking ceremony, and the alias-pack extension point finally built** (2026-08-16; V2-101)
- **Turn-completeness judge — real intelligence replaces "hold forever"** (2026-08-16; V2-095, V2-096, V2-097, V2-102)
- **RESET left stale rows on screen and never touched the chat wall** (2026-08-16; no refs)
- **Memory — write-path self-healing, and REM stops being purely additive** (2026-08-16; V2-103)
- **REM — gate de fidelidad antes de escribir/demotar un insight** (2026-08-16; V2-075, V2-103, V2-104)
- **Corpus longitudinal con contradicciones + REM real end-to-end (V2-107)** (2026-08-17; V2-107)
- **Susurro's friction window had no recency boundary — an 11-hour-old exchange got escalated as "now" (V2-108)** (2026-08-17; V2-108)
- **- **A worker-dispatched browser task's own trace was empty for its whole lifetime — TaskBrowser used ambient** (2026-08-17; V2-108)
- **La query de recall llevaba pegada la nota `[SISTEMA]` del turno — el modelo alucinó un familiar (V2-110)** (2026-08-17; V2-110)
- **- **Grafo multi-hop (PPR) + bi-temporal explícito — dos piezas de V2-111 §9, construidas por delante de las** (2026-08-17; V2-095, V2-102, V2-111)
- **- **An escalated flow closed itself seconds after opening — a structural race, not an occasional one (V2-113,** (2026-08-17; V2-113)
- **- **Lead-in filler leaked into the chat wall AFTER the real reply — now its own module, and structurally unabl** (2026-08-18; V2-096, V2-101, V2-102, V2-122)
- **- **Showing data is the generic sheet's job, not a reason to write a component — and a created widget was neve** (2026-08-18; V2-098, V2-115)
- **- **One sentence must be ONE flow — and flow continuity can no longer hang on getting completeness right; plus** (2026-08-18; V2-090, V2-095, V2-096, V2-097, V2-102, V2-116)
- **- **A worker started with the engine's own developer manual inside it, and its raw provider error was delivere** (2026-08-18; V2-105, V2-117)
- **- **The flow-merge TRIGGER, built at last — and neither of the two resolvers we already had could do it (V2-12** (2026-08-18; V2-029, V2-075, V2-090, V2-105, V2-113, V2-117, V2-123)
- **- **A SECOND SHELL over one engine — the mobile PWA, and the two contracts that made it cheap (V2-124, 2026-08** (2026-08-18; V2-088, V2-092, V2-124)
- **La memoria estaba sana; la deuda era ESTRUCTURAL — y tres imports inversos se BENDICEN, no se arreglan** (2026-08-23; V2-114, V2-117, V2-273)
- **Un recall que NO llega se veía igual que una memoria vacía** (2026-08-25; V2-031, V2-273, V2-311)
- **Un encargo viejo viajaba en CADA prompt como un hecho permanente de la persona** (2026-08-26; V2-254, V2-337)
- **La SONDA de backend esperaba como una llamada real: 20,3 s en el PRIMER acceso a memoria** (2026-08-26; V2-103, V2-311, V2-349)
- **El widget de YouTube tiene LISTA, y `add` NUNCA arranca la reproducción (V2-366, 2026-08-27)** (2026-08-27; V2-092, V2-366)
- **Buscar vídeos va al REPRODUCTOR, no a la hoja de resultados (V2-402, 2026-08-27)** (2026-08-27; V2-366, V2-380, V2-402)
- **- **El Brain Worker corre con lo que la NUBE puede contratar, y un escalón que no ve se declara ciego** (2026-08-27; V2-403)
- **El deck móvil se NAVEGA, y su restore alcanzó la paridad V2-351 (V2-474, 2026-08-29)** (2026-08-29; V2-351, V2-465, V2-474)
- **- **El arranque en frío enseñaba claves i18n crudas — y la leyenda buena llegaba sin que la viera nadie** (2026-08-29; V2-124, V2-481)
- **Cinco filas eran pocas, y decirle que hay más no es enseñárselas (V2-479, 2026-08-29)** (2026-08-29; V2-374, V2-479)
- **A terminal field cannot tell a process, and a zero must say why it is zero (V2-512, 2026-08-30)** (2026-08-30; V2-506, V2-512)
- **The instrument must not turn a coincidence into a cause (V2-506, 2026-08-30)** (2026-08-30; V2-506)
- **A retired provider may not be named by ANY ladder (V2-504, 2026-08-30)** (2026-08-30; V2-500, V2-504)
- **A lab measures the PRODUCT, not the machine it runs on (V2-502, 2026-08-30)** (2026-08-30; V2-500, V2-502)
- **- **The memory's semantic space comes from a CLOUD provider, and a paid call is metered (V2-501,** (2026-08-30; V2-103, V2-501)
- **El reparto de modelos vive en UNA tabla pública, y un solo failover por servicio (V2-500, 2026-08-30)** (2026-08-30; V2-500)
- **Z.AI es del BRAIN WORKER y de nadie más (V2-496, 2026-08-30 — deroga V2-462)** (2026-09-01; V2-462, V2-496)
- **- **El compositor del brief pedía «no razones» a un modelo que NO PUEDE dejar de hacerlo, y toda búsqueda** (2026-08-29; V2-225, V2-488)
- **- **La red MeshKore estaba construida, verificada en vivo y NUNCA se consultaba — dos causas apiladas y** (2026-08-29; V2-118, V2-167, V2-211, V2-486, V2-487)
- **Una frase deja DOS píldoras críticas, y el corte expulsaba un hecho de SEGURIDAD (V2-491, 2026-08-29)** (2026-08-29; V2-123, V2-490, V2-491)
- **- **DOS puertas por las que entra un vector de otro espacio, y ninguna fallaba con ruido (V2-484 y V2-485,** (2026-08-29; V2-482, V2-484, V2-485)
- **La voz de V2-497 estaba colgada DESPUÉS de la puerta que más se cierra (V2-503, 2026-08-30)** (2026-08-30; V2-311, V2-482, V2-484, V2-497, V2-503)
- **Un reparador INERTE parecía un reparador SIN TRABAJO (V2-497, 2026-08-29)** (2026-08-29; V2-311, V2-482, V2-485, V2-497)
- **Los GUSTOS son estado ACTIVO, y el slot obvio está medido como MUERTO (V2-498, 2026-08-29)** (2026-08-29; V2-337, V2-491, V2-497, V2-498)
- **- **Una limitación de INGESTIÓN dicha sin palabra de categoría también es crítica (V2-499, 2026-08-29,** (2026-08-29; V2-490, V2-491, V2-499)
- **Un vector de espacio AJENO no lo repara nadie, nunca (V2-482, 2026-08-29)** (2026-08-29; INI-026, V2-482)
- **La TERCERA puerta al scheduler no normalizaba (V2-480, 2026-08-29)** (2026-08-29; V2-151, V2-249, V2-480)
- **La puerta del backstop de entrega tampoco era la LONGITUD (V2-478, 2026-08-29)** (2026-08-29; V2-364, V2-371, V2-478)
- **Una garantía escrita en un solo idioma es un defecto para todos los demás (V2-475, 2026-08-29)** (2026-08-29; V2-475)
- **La entrega se NOMBRA y lo no verificable no se da por cumplido (V2-469, 2026-08-29)** (2026-08-29; V2-341, V2-469)
- **Un caso BLOQUEADO no es una avería, ni un turno que gastar cada vuelta (V2-448, 2026-08-28)** (2026-08-28; V2-260, V2-448)
- **Un solo formateador de fila (V2-455, 2026-08-28)** (2026-08-28; V2-240, V2-451, V2-455)
- **La sesión NUNCA pide la cámara — mic-only (V2-456, 2026-08-28)** (2026-08-28; V2-088, V2-456)
- **Cadena de buscadores de imágenes (V2-466, 2026-08-28)** (2026-08-28; V2-466)
- **El reproductor publica su lista y el visor tiene teclado (V2-465, 2026-08-28)** (2026-08-28; V2-026, V2-380, V2-465)
- **La ronda deja un VÍDEO — modo escaparate + grabador (V2-464, 2026-08-28)** (2026-08-28; V2-464)
- **La tarjeta se abre donde aterrizan los datos (V2-463, 2026-08-28)** (2026-08-28; V2-346, V2-463)
- **Z.AI: el plan primero, los créditos después (V2-462, 2026-08-28)** (2026-08-28; V2-458, V2-462)
- **Un MATIZ sobre una foto no es un encargo · y la conversación por API se VE (V2-461, 2026-08-28)** (2026-08-28; V2-032, V2-461)
- **Un agente del plató arranca con la sesión EN BLANCO (V2-460, 2026-08-28)** (2026-08-28; V2-460)
- **Tres agentes en esta máquina, tres puertos, y ninguno se mueve (V2-459, 2026-08-28)** (2026-08-28; V2-459)
- **Enseñar una foto es un turno de 3 s, no un encargo de 355 (V2-457, 2026-08-28)** (2026-08-28; V2-402, V2-457)
- **Un saldo agotado apaga a los escalones de su MISMA cuenta (V2-458, 2026-08-28)** (2026-08-28; V2-243, V2-252, V2-458)
- **La oferta de PARAR se hace una vez — el hecho se queda (V2-454, 2026-08-28)** (2026-08-28; V2-131, V2-224, V2-454)
- **El recall que NO llegó se cuenta — «preguntó lo que ya sabía» tiene DOS causas (V2-453, 2026-08-28)** (2026-08-28; V2-311, V2-432, V2-453)
- **- **El prompt está en castellano y el operador habla inglés: el modelo copiaba su idioma (V2-452,** (2026-08-28; V2-221, V2-452)
- **Las filas de la hoja viajan aunque NO haya navegador (V2-451, 2026-08-28)** (2026-08-28; V2-259, V2-432, V2-438, V2-441, V2-444, V2-451)
- **Un precio de mercado ANTES de entregar nada — y los TRES caminos de entrega (V2-450, 2026-08-28)** (2026-08-28; V2-223, V2-450)
- **La entrega multimedia no está en la hoja (V2-445, 2026-08-28)** (2026-08-28; V2-366, V2-402, V2-445)
- **El mismo defecto en el SEGUNDO bloque, y era el que disparaba (V2-444, 2026-08-28)** (2026-08-28; V2-222, V2-443, V2-444)
- **Sin filas, lo único que hay es la PALABRA del worker (V2-443, 2026-08-28)** (2026-08-28; V2-152, V2-238, V2-249, V2-330, V2-358, V2-440, V2-443)
- **Pedirlo dos veces no es hacerlo dos veces (V2-442, 2026-08-28)** (2026-08-28; V2-123, V2-442)
- **«Le pedimos lo imposible»: avisado de que había algo y servido con CERO filas (V2-441, 2026-08-28)** (2026-08-28; V2-330, V2-441)
- **El censo del INSTANTE separa dos causas que se veían idénticas (V2-440, 2026-08-28)** (2026-08-28; V2-330, V2-439, V2-440)
- **`results::X` y `X` son la MISMA hoja, y una volvía VACÍA (V2-439, 2026-08-28)** (2026-08-28; V2-242, V2-259, V2-439)
- **La cara dice que hay filas y la hoja no las da (V2-438, 2026-08-28)** (2026-08-28; V2-438)
- **Un elemento muerto dice qué hacer (V2-437, 2026-08-28)** (2026-08-28; V2-437)
- **Una memoria rechazada dice POR QUÉ (V2-436, 2026-08-28)** (2026-08-28; V2-344, V2-436)
- **El worker PUEDE escribir lo que le decimos que escriba (V2-435, 2026-08-28)** (2026-08-28; V2-435)
- **Un RELEVO no es un encargo nuevo, tampoco para quien LEE la hoja (V2-434, 2026-08-28)** (2026-08-28; V2-432, V2-434)
- **El puente del worker habla el vocabulario de widgets (V2-433, 2026-08-28)** (2026-08-28; V2-429, V2-433)
- **La hoja llena y el prompt diciendo que no (V2-432, 2026-08-28)** (2026-08-28; V2-352, V2-432)
- **Un «no» bien fundado es una ENTREGA (V2-431, 2026-08-28)** (2026-08-28; V2-431)
- **El precio que DICE es el que TIENE (V2-430, 2026-08-28)** (2026-08-28; V2-430)
- **Un comando rechazado dice qué se intentó (V2-429, 2026-08-28)** (2026-08-28; V2-424, V2-426, V2-429)
- **Un traceback se recorta por la COLA (V2-428, 2026-08-28)** (2026-08-28; V2-421, V2-425, V2-428)
- **La apertura del tester no puede recitar nuestra hoja (V2-427, 2026-08-28)** (2026-08-28; V2-427)
- **El `cd` bloqueado, y la premisa falsa que lo provoca (V2-426, 2026-08-28)** (2026-08-28; V2-426)
- **El error de payload dice QUÉ falló (V2-425, 2026-08-28)** (2026-08-28; V2-425)
- **El `&` solo también lo bloquea nuestro guarda, y no estaba en la regla (V2-424, 2026-08-28)** (2026-08-28; V2-412, V2-424)
- **Una fila INFRA dice CUÁL (V2-423, 2026-08-28)** (2026-08-28; V2-423)
- **La misma búsqueda dos veces no son dos búsquedas (V2-422, 2026-08-28)** (2026-08-28; V2-422)
- **Un payload que falta dice lo que SÍ hay (V2-421, 2026-08-28)** (2026-08-28; V2-421)
- **El denominador es lo que se le MOSTRÓ, no lo que hay en la hoja (V2-420, 2026-08-28)** (2026-08-28; V2-420)
- **Un worker MIRANDO EL MENÚ no es un worker estrellado (V2-418, 2026-08-28)** (2026-08-28; V2-418)
- **Una función que decide fechas leía DOS relojes (V2-419, 2026-08-28)** (2026-08-28; V2-419)
- **El plató no para: 24/7 con guardián (V2-417, 2026-08-28)** (2026-08-28; V2-417)
- **El marcador dice con qué CEREBRO se midió cada fila (V2-415, 2026-08-27)** (2026-08-27; V2-415)
- **Que nos BLOQUEEN no es que el mundo esté vacío (V2-414, 2026-08-27)** (2026-08-27; V2-414)
- **Una recarga es INVISIBLE desde el motor, así que se vuelve a probar (V2-413, 2026-08-27)** (2026-08-27; V2-243, V2-413)
- **La búsqueda mira desde donde vive la persona (V2-411, 2026-08-27)** (2026-08-27; V2-411)
- **El prompt del worker no enseña lo que nuestro guarda bloquea (V2-412, 2026-08-27)** (2026-08-27; V2-412)
- **El dedup decía que NO y no decía POR QUÉ (V2-507, 2026-08-30)** (2026-08-30; V2-507)
- **Un encargo CONFIRMADO conserva su hoja (V2-508, 2026-08-30)** (2026-08-30; V2-117, V2-128, V2-227, V2-238, V2-259, V2-507, V2-508, V2-509)
- **Lo que vuelve de una búsqueda es una PISTA, y la NOTA seguía ordenando entregarla (V2-510, 2026-08-30)** (2026-08-30; V2-222, V2-226, V2-234, V2-236, V2-479, V2-508, V2-510)
- **Lo que CUENTA lo que pasó no es lo que TRAE algo (V2-511, 2026-08-30)** (2026-08-30; V2-236, V2-240, V2-321, V2-364, V2-511)
- **The gate reads the ORDER, not the words (V2-509, 2026-08-30)** (2026-08-30; V2-128, V2-507, V2-508, V2-509)
- **A SHIPPED widget is forked, never edited in place — and never deleted from disk (V2-515, 2026-08-31)** (2026-08-31; V2-515, V2-518)
- **A catalog costs nothing until it is CONNECTED (V2-526, 2026-08-31 — DESIGN, no code yet)** (2026-08-31; V2-078, V2-083, V2-169, V2-520, V2-526)
- **- **Stopping is DISCARDING — abandon_work (V2-528, 2026-08-31; supersedes the 2026-07-10 freeze-to-resume** (2026-08-31; V2-214, V2-528)
- **- **A `[SISTEMA]` note is never the errand: the SECOND door, and a question is not a promise (V2-534,** (2026-09-01; V2-049, V2-095, V2-530, V2-534)
- **A NEGATED clause is not a promise (V2-534 follow-up, 2026-09-01)** (2026-09-01; V2-049, V2-095, V2-252, V2-534)
- **STABLE PREFIX FIRST — the prompt's block order is what the provider's cache can see (V2-536, 2026-09-01)** (2026-09-01; V2-097, V2-255, V2-533, V2-536)
- **The MURAL — placement that dodges the chat, the widget RAIL, and auto-arrange (V2-537, 2026-09-01)** (2026-09-01; V2-087, V2-464, V2-474, V2-537)
- **The rail is DOCKED, and a card gets the size its manifest declares (V2-538, 2026-09-01)** (2026-09-01; V2-538)
- **A sheet is for RESULTS, and an ITEM is a real candidate (V2-538, 2026-09-01)** (2026-09-01; V2-538)
- **Figures are made SPEAKABLE at the TTS node, and only there (V2-538, 2026-09-01)** (2026-09-01; V2-538)
- **An undeclared capability is one the model NARRATES — the agenda's view is an action (V2-540, 2026-09-01)** (2026-09-01; INI-027, V2-521, V2-540)
- **A canvas click has to land on the sheet the operator is LOOKING AT (V2-540, 2026-09-01)** (2026-09-01; V2-259, V2-540)
- **Who may interrupt is CONFIGURATION — per-connector notification policy (V2-532, 2026-09-01)** (2026-09-01; V2-520, V2-522, V2-527, V2-532)
- **- **The turn clock tells OUR share — pre-turn attribution + prefix-cache visibility + pooled judges (V2-533,** (2026-09-01; V2-533, V2-536)
- **- **Inside an active conversation, NOBODY judges — the attention gate went deaf mid-dialogue (V2-531,** (2026-09-01; V2-531)
- **An errand has a NAME, and it is not a slice of the conversation (V2-530, 2026-08-31)** (2026-08-31; V2-151, V2-199, V2-530)
- **The lead-in filler sounds BEFORE the reply — it IS the reply's first segment (V2-529, 2026-08-31)** (2026-08-31; V2-122, V2-529)
- **The proactive delivery QUEUE — one message at a time (V2-527, 2026-08-31)** (2026-08-31; INI-008, V2-047, V2-525, V2-527)
- **⏻ ON has to START it — the reload was the tell (V2-525, 2026-08-31)** (2026-08-31; V2-092, V2-525)
- **The BOUNDARIES of a work session (V2-524, 2026-08-31)** (2026-08-31; V2-524)
- **Messaging is a MAIN widget now — the operator's spec (V2-521/522/523, 2026-08-31)** (2026-08-31; V2-051, V2-520, V2-521, V2-522, V2-523)
- **Connecting a channel can be ASKED FOR (V2-520, 2026-08-31)** (2026-08-31; V2-051, V2-520)
- **The attachment can never swallow the message (V2-519, 2026-08-31)** (2026-08-31; V2-519)
- **The widget's CONFIG corner + confirmations live in the CHAT (V2-518, 2026-08-31)** (2026-08-31; V2-518)
- **CONTACTOS: un directorio para TODAS las identidades — y su vista contesta (V2-541, 2026-09-01)** (2026-09-01; V2-124, V2-208, V2-473, V2-523, V2-540, V2-541)
- **Borrar una superficie es MUDAR lo que llevaba, o es perderlo (V2-542, 2026-09-01)** (2026-09-01; V2-538, V2-542)
- **- **MENSAJERÍA: la vista es una acción que contesta, los medios se VEN, y las órdenes llegan a las apps** (2026-09-01; V2-520, V2-531, V2-541, V2-543)
- **- **The INSIDE of a widget belongs to widget_data — the prompt no longer contradicts the catalog (V2-544,** (2026-09-01; V2-222, V2-467, V2-539, V2-544)
- **- **What a pure show may RUN is decided by the ACTION, not by the words — and the lens phrases resolve before** (2026-09-01; V2-544, V2-545)
- **The messaging widget FOLLOWS the real apps instead of drifting from them (V2-546, 2026-09-01)** (2026-09-01; V2-546)
- **A KNOWN phrase skips the model — the ACTION MAP (V2-539, 2026-09-01)** (2026-09-01; V2-095, V2-539, V2-545)

#### Movidas el 2026-09-20 (V2-728)

- **A connected mailbox that shows nothing, forever — the inbox was declared already-seen (V2-606, 2026-09-07)** (2026-09-07; V2-221, V2-603, V2-606)
- **Storing is not notifying — nothing interrupts by default, and the summary is not the mailbox (V2-607, 2026-09-07)** (2026-09-07; V2-606, V2-607)
- **The desk shrank underneath the cards and nobody told them (V2-608, 2026-09-07)** (2026-09-07; V2-062, V2-530, V2-550, V2-606, V2-608)

#### Movidas el 2026-09-20 (V2-726)

- **- **A card question the operator cannot answer is asked forever — and the captch** (; V2-032, V2-259, V2-526, V2-530, V2-539, V2-540, V2-555, V2-567, V2-605)
- **Messaging navigation gets unstuck, and email defaults to a classic list (V2-610, 2026-09-07)** (2026-09-07; V2-610)
- **Reply from the widget with review-first draft/send, and a real email signature (V2-611, 2026-09-07)** (2026-09-07; V2-608, V2-611)

#### Movidas el 2026-09-14
- **A voice fullscreen order must change the screen — requestFullscreen is gesture-gated and rejects in SILENCE (V2-583, 2026-09-05)** (2026-09-05; V2-583)
- **The video widget gets an ACCOUNT — the video connector family, and the interior anchors to the parent (V2-597, 2026-09-05)** (2026-09-05; V2-034, V2-557, V2-564, V2-597)
- **A fullscreen order is about a SCREEN STATE, never a close — and cinema goes above everything (V2-600, 2026-09-05)** (2026-09-05; V2-583, V2-600)
- **A stale connector error never greets a fresh open — and the state line OUTRANKS the window (V2-582, 2026-09-05)** (2026-09-05; V2-221, V2-567, V2-582)
- **The daemon is the piece that reads somebody's disk, so it gets an attacker with a name (V2-575 P0 security pass + P4, 2026-09-06)** (2026-09-06; V2-575, V2-601)
- **The controls exist; a ROBOT runs them now — the audit remediation tier (V2-601 T-01..T-14, 2026-09-05/06)** (2026-09-05; V2-090, V2-121, V2-348, V2-554, V2-555, V2-600, V2-601)
- **The A2A card names SKILLS, not a contact URL (V2-616, 2026-09-08)** (2026-09-08; V2-616)
- **An empty answer is not a served errand (V2-602, 2026-09-06)** (2026-09-06; V2-596, V2-602)
- **The engine is licensed: Sustainable Use License 1.0, fair-code (V2-601 T-03, 2026-09-06)** (2026-09-06; INI-027, V2-601)
- **This file compacts by ARCHIVING, never by deleting (V2-601 T-18, 2026-09-06)** (2026-09-06; V2-601)
- **A catch-all category must not outrank a specific match (V2-599, 2026-09-05)** (2026-09-05; V2-599)
- **A broken upstream is not a request for fields (V2-598, 2026-09-05)** (2026-09-05; V2-487, V2-598)
- **The workflow table: what serves this kind of errand (V2-594, 2026-09-05)** (2026-09-05; V2-487, V2-594)
- **A free tier arrives as one entry in a LIST (V2-593, 2026-09-05)** (2026-09-05; V2-593)
- **Zero agents beats a wrong one (V2-581, 2026-09-05)** (2026-09-05; V2-580, V2-581)
- **The answer says what the agent claims to be (V2-580, 2026-09-05)** (2026-09-05; V2-580)
- **A mesh agent can gate its skills behind a bearer of its own issue (V2-579, 2026-09-05)** (2026-09-05; V2-579, INI-030)
- **The phone is HEARD, and the dock is the operator's (V2-573, 2026-09-04)** (2026-09-04; V2-573)
- **The mouth matches the order (V2-572, 2026-09-03)** (2026-09-03; V2-210, V2-572)
- **Dependency directions are a ratchet, like sizes (V2-569, 2026-09-03)** (2026-09-03; V2-569)

#### Movidas el 2026-09-11
- **La agenda no inventa, y el aviso por defecto es SUYO (V2-473, 2026-08-29)** (2026-08-29; V2-222, V2-341, V2-473)
- **La acción que ES el propósito de un widget es la que se salta el censo (V2-547, 2026-09-02)** (2026-09-02; V2-545, V2-547)
- **El catálogo enrutaba con la frase cortada a mitad de palabra (V2-547, 2026-09-02)** (2026-09-02; V2-027, V2-526, V2-545, V2-547)
- **Un fallo de RECUPERACIÓN es invisible cuando sobrevive un vecino plausible (V2-548, 2026-09-02)** (2026-09-02; V2-457, V2-547, V2-548)
- **LA HOJA EN BLANCO: una sola cosa para leer, y el borde que la mantiene pequeña (V2-549, 2026-09-02)** (2026-09-02; V2-457, V2-463, V2-547, V2-549)
- **Lo que se perdía del chat no era la posición, era estar ABIERTO (V2-550, 2026-09-02)** (2026-09-02; V2-550)
- **Media tarjeta no es una tarjeta más pequeña (V2-551, 2026-09-02)** (2026-09-02; V2-551)
- **Un glifo que cambia de significado bajo la mano hay que leerlo antes de usarlo (V2-552, 2026-09-02)** (2026-09-02; V2-551, V2-552)
- **Un número de versión no sabe si el navegador tiene que recargar (V2-553, 2026-09-02)** (2026-09-02; V2-551, V2-553)
- **Un `COPY` no significa que el directorio viaje (V2-554, 2026-09-02)** (2026-09-02; V2-500, V2-554)
- **Mover código «byte por byte» cambia sus GLOBALS (V2-555, 2026-09-02)** (2026-09-02; V2-554, V2-555)
- **BUSCAR ANUNCIOS es UNA tool, y el MÓDULO decide si sirve el turno o escala (V2-556, 2026-09-02)** (2026-09-02; V2-117, V2-222, V2-510, V2-556)
- **ARCHIVOS EN LA NUBE: el tramo de permiso es el DISEÑO, y un permiso que no puede listar no es un disco vacío (V2-557, 2026-09-02)** (2026-09-02; V2-507, V2-520, V2-526, V2-540, V2-541, V2-545, V2-557)
- **A refusal has to name what you PASTED, and a retry has to move something (V2-559, 2026-09-03)** (2026-09-03; V2-559)


#### Movidas el 2026-09-14 (V2-694)

- **Two screens, ONE widget (V2-574, 2026-09-04)** (2026-09-04; V2-574)
- **The voice SEES the open directory — a widget the operator is looking at publishes its truth (V2-576, 2026-09-04)** (2026-09-04; V2-311, V2-576)
- **A widget event reaches the pills it outdates — the lifecycle chain (V2-577, 2026-09-04)** (2026-09-04; V2-577)
- **The sleep circuit review — five silent integrity holes in the REM process (V2-578, 2026-09-05)** (2026-09-05; V2-578)

#### Movidas el 2026-09-15 (V2-697)

- **«Sal de pantalla completa» needs no name — the canvas knew which card and never said so (V2-609, 2026-09-07)** (2026-09-07; V2-026, V2-540, V2-600, V2-609)
- **The video widget OWNS its library; the connector only EXTENDS it (V2-604, 2026-09-07)** (2026-09-07; V2-366, V2-384, V2-603, V2-604)
