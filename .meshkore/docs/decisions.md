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
- **A «process» was five stores and none of them the whole truth — the TASK is the unit now (V2-728, 2026-09-20)**: the operator, after a manual test: *«cada vez que hago un test manual encuentro muchos errores… si le digo resérvame hora en un restaurante, ya no quiero ir a nada más. Una vez tiene todos los criterios, ya me olvido de esa tarea»*. **Forgetting only works if somebody else remembers**, and nobody did for long. Live Brain Workers sat in `dispatch._SESSIONS`, a RAM dict a restart empties; finished ones in a **50-capped JSON blob** inside `sys_kv`, fenced by hand against a reset race; third-party errands in their own table; crons as `journal` rows; and the RESULT inside a widget sheet with a **hard cap of 8**, pruned by file mtime — so the ninth search deleted the report of the first, in a file whose own header says it persists precisely so «the operator does not lose a report he already paid for». One cap contradicted the other. `/api/tasks` had to STITCH two row shapes by hand, which is why the Processes tab and the Flows board once disagreed about the same work. And nothing could answer *«de la tarea de buscar piso que te dije antes»*: disambiguation reaches only what is on screen (`widgets/instances.py`) or the six-entry `recent_widgets` MRU. Now there is ONE durable row per commission (`tasks` + `task_artifacts` + an accent-insensitive `fts_tasks`, schema v7, purely additive), the RAM record keeps only the hot detail that churns every second and writes on TRANSITIONS, `/api/tasks` is a query, and `errands.board_rows()` is gone. **Four decisions the operator made**: one «Tareas» tab with four sub-tabs (the top level drops 5→4, «Crons» becomes «Periódicas»); the RESULT belongs to the task, not the sheet, so pruning destroys nothing and `results` becomes a rebuildable view — a narrowing of V2-604, not a contradiction, since a library is the widget's and an errand's result is the task's; the agent PROPOSES a recurring cadence and says it out loud; and only his own commissions are listed, behind a deterministic `visible` gate with a `⚙ todo` switch for manual testing. **`reopen_task` is the first production consumer of `jev.select_many`**, built and measured under V2-726 and until now called by nothing but its own test: a lexical FTS5 index narrows to ≤5 with NO model (the operator's rule, INI-027 §7) and Jev chooses among those — and with several equally good candidates nobody chooses, it ASKS, because opening the wrong report looks exactly like opening the right one and he would read it before noticing. ⚠️ **Two traps this pass paid for.** The tab rename touched five frontend files, each of which carried **its own whitelist** of tab names — `sse.js` had three, `main.js` a shorter three — which is how `clusters` was silently dropped at birth (V2-086); the list now lives in `store.setChatTab`, the one door every caller goes through, and a test pins that `sse.js` has not grown a second one. And the render test earned its place immediately: its first version asserted «four sub-tabs exist» by COUNTING nodes, which passes on four blank labels — exactly what a missing i18n key produces. **What was NOT done in that pass and was written down rather than implied**: the scheduler still STORES in `journal` and is MIRRORED onto the board (moving live standing reminders risks the one failure nobody notices until the day it fails to sound, V2-121) — still true; and the DISCARDED candidates — closed the same day, see the entry above. Nodes 4.150/3.66, disarms red at every wiring point — including one that found `tasks.retitled` disconnected from the dispatcher with the whole file still green.
- **A prohibition is not a diagnosis: the wide sweep hung on ONE line, and it hung on the operator's own 84 GB video (V2-727, 2026-09-20)**: from 2026-09-15 a whole-tree pytest run was forbidden here because it hung the operator's machine, and the rule shipped saying so — root cause **undiagnosed**, which was honest and still left the engine unable to answer «does everything pass?». Operator's correction: *«todos los tests se pueden pasar… había unos que se quedaban colgados… hay que buscar algún mecanismo que detecte si se han colgado o no»*. The cause is **one test**. `tests/infrastructure/unit/config/test_model_policy.py` greps the tree for a retired model name, and it walked the checkout with a **blacklist** of binary suffixes: `.mkv` was not on it, `library/downloads/` is his real media folder, and the sweep called `read_text()` on an **84 GB video file** — 10.009 files, **90.348 MB** of reads for a grep, with no output until the machine gave up. Two defects in one line: **a blacklist of binary formats is the list of the ones somebody remembered**, and it fails by HANGING rather than erroring; and it was reading gitignored operator content, against this suite's own rule that a test never touches his real state. It now asks `git ls-files` what the tree IS — which is also what the norm means by «anywhere», since a banned name matters when it is COMMITTED — and goes from hanging to **0,84 s**, disarmed both ways (the name in a tracked file goes red; the same name in an untracked one stays green, which is the new boundary said out loud). With that line fixed the deterministic suite is **57 chunks, 10.828 green, 414 s, zero hangs**. The runner that proves it is `tests/watchdog.py`: `faulthandler_timeout` — already inside pytest, **no new dependency** — dumps every thread to unbuffered fd 2 and NAMES the hung test, so a hang arrives identified and costs seconds; a per-chunk wall clock covers what the dump cannot see (a blocking import or collection); and the kill goes to the process **GROUP**, because the 2026-09-15 incident left **71 orphaned Chromium** and killing pytest alone leaves them exactly where they were. A lock refuses two WIDE sweeps on one checkout (measured 1222 s and 1589 s for 9 minutes of work) and deliberately does not apply to an explicit narrow path, which has to stay nestable. Selection is `--impacted <base>`, chosen by **the imports a test declares** rather than a hand-written folder map that rots when a module moves — its first version matched the bare leaf name and selected 14 tests for `tests/watchdog.py` because `use_cases` describes a «mid-scenario watchdog» in prose: **a word in a docstring is not a dependency**. Node 7.53 watches the watcher. ⚠️ The trap that nearly shipped it blind: pytest prints its progress character on the same line the dump starts (`.Timeout (0:00:04)!`), the first regex was anchored to the line start and saw NOTHING — every hang fell through to the chunk wall — and the test meant to catch that generated a file with ONE test, where the banner lands in column 0 and the broken detector passes. The disarm exposed it by going red on one case and green on the other. **The rule this leaves: a guard that enumerates what to EXCLUDE fails silently the first time the world shows it something nobody listed — enumerate what to include.**
- **Jev SELECTS over parsed data in one trip, and the call stopped throwing away work it had paid for (V2-726 F4+F5, 2026-09-20)**: the operator's own case — «si le mandamos a Jev los datos parseados de los 100 resultados y la lista de criterios, nos puede decir cuáles son los que mejor encajan, en una sola request». Measured live against 100 listings: **ONE trip, 1161 ms, $0,0005, recall 3/3 with ZERO false positives** once the confidence gate is applied. `jev.select_many(candidates, criteria)` is that capability, off the voice path by design — the Brain Worker has minutes, and `nucleo/workers`, `errands` and `research.py` were the only places with real selection to do and no Jev at all. ⚠️ **The trap, and it took a measurement to find: the candidate's identity has to travel INSIDE its own question, not only in the shared `state`.** Ten identical questions over one state answered `strong` to all ten — a 125 cc Vespa included, in a search for motocross bikes — at 0.82-0.89 confidence. Confidently wrong is the worst failure this module has, and it is invisible to a test that only checks the happy path, so `select_many` builds each question around its own candidate and no caller can get it wrong. Only confident `strong` comes back: `partial` is a shrug, and an unsure `strong` is exactly the false-positive band the measurement found (the three real hits sat at 0.64-0.94, the three false ones all under 0.33). Past `MAX_QUESTIONS` it raises instead of truncating, so a caller with a thousand rows pages them rather than silently scoring the first hundred. **F5, the hygiene the same measurements demanded**: the timeout goes 900 ms → 2 s, because 900 against a measured p50 of 800 was the engine cancelling its own calls at the edge — 5 % of canvas verdicts and **28 % of the escalate gate's** were dropped AFTER being paid for — and since F1 nobody blocks on the answer, so a slow call costs a daemon thread and nothing else. A **circuit breaker** (3 consecutive failures → 60 s quiet, one success closes it) stops a provider outage from costing a thread and a full timeout on every turn forever, which the longer timeout would otherwise have made worse. And the key file is read ONCE: `enabled()` runs on every Jev touch and `_post_*` reads it again for the header, so on a machine where the key lives in `credentials/jev.md` rather than the environment — which is this one — every verdict was opening and parsing a file twice on the turn's thread. Node 3.65, five disarms red.
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

- **A question about what a widget HOLDS is answered by the widget (V2-668, 2026-09-11)**: session 53de97d4,
  10:58:33 → 11:00:03. «¿a qué hora tengo la cita con Hacienda?» → «no la tengo con hora, solo que tienes que
  ir próximamente» — while the agenda held `11:30–12:30 · Cita Agencia Tributaria` in ONE line. Six turns
  later, after he opened the card BY HAND, the model said «hoy a las once y media» **calling no tool**: a
  widget's interior only ever reached the prompt while the card was OPEN (`widgets/brief.py`, `if wid in
  opened`), and NO tool read a closed one — `widget_data` EXECUTES a declared action, `recall` reads his
  long-term memory («no es para datos del mundo»), `web_search` reads the world. A question about his own
  widget's store had no route and was answered from a memory pill, a race the susurro itself filed
  (`[P1·memoria] La memoria durable se inyecta DESPUÉS de responder`). His verdict: «si yo le tengo que
  explicar cómo llegar a los datos, pierdo menos tiempo buscándolos yo». **`read_widget`
  (`nucleo/flash/widget_read.py`) is the fourth door**, `recall`'s sibling in shape — a LIGHT two-pass route
  resolved IN the turn, no card opened, no worker — reading through the seams the widgets already publish for
  the prompt (`refs.prompt_digest` → `coach_context()` → `refs.items_line`), so every widget that can be
  reasoned about while open can be asked about while closed; the second pass has the widget's content as its
  ONLY source and states an absence rather than filling it (V2-210). It lives in the `memory` family, which
  `tool_selection` never trims — that module's docstring already named this exact case («when is the vehicle
  inspection appointment?») and pointed it at `recall`, the wrong store. `web_search`, `widget_data` and
  `recall` now point at it for his own data. Both channels call the module (V2-252). Keyword routing was
  measured and rejected: «¿a qué hora tengo la cita?» hits the CLOCK's keywords, not the agenda's. The 23 100
  catalog ceiling — paid on every voice turn — was met by compacting nine descriptions, never raised. Node
  **2.52**.

- **An order NAMES its target, and a notice waits its turn (V2-666, 2026-09-11)**: the same session, three
  rails each correct in intent and wrong on one sentence. **(1)** «ponme un gráfico de la evolución del
  Bitcoin» → the model escalated, and the show guard STOLE it and opened YouTube with «Aquí lo tienes»:
  `runtime.identify` returned the only OPEN card «by context» (score 0.0, zero candidates) and the guard read
  that as a NAME — a blind open of whatever was on screen, the thing `identify`'s own docstring says it never
  does. `identify_named()` (alias/name only, context breaks ties, never a fallback) is what a SHOW asks now, in
  both channels; with no name and no antecedent the guard resolves to NOTHING and the escalation stands.
  **(2)** «Mírame, ábreme la agenda inmediatamente» opened the SEARCH card: the article «la» is a bare deictic
  token for `looks_like_bare_ref` (right about «cancélala»), so one article made the whole sentence
  «muéstramelo»-shaped, the noun he actually said was discarded, and the fallback «the previous route was a web
  search» chose for him. A sentence that NAMES its widget is never deictic — the name wins first. **(3)**
  «¿a qué hora tengo la cita con Hacienda?» arrived BEHIND three `[SISTEMA]` notes about a dead Bitcoin task
  (`text = "\n".join(notes) + "\n\n" + text`), two of them ordering «Díselo en ESTE turno», and the reply
  opened «Primero, Ricardo, te debo una cosa pendiente…». The operator's rule is the inverse and it is the
  rule of any assistant: the order is served first, the news waits until it is answered. `brain_notes.
  compose_turn` puts his words FIRST and the notes AFTER under a header that says when they may be spoken; the
  two writers now say «DESPUÉS de contestar». A model reads what comes first as the frame of its answer; the
  frame is his. Node **4.160**. Named, not done: the arbiter (V2-653) VETOED the blank `results` card that
  same turn (`show-drag`) and ALLOWED the YouTube blind open — still in shadow, and it cannot arbitrate the
  second class until it consults `identify_named`.

- **The generator's contract never contradicts its gate, and a red gate gets ONE repair (V2-667,
  2026-09-11)**: «ha intentado preparar un widget, ha fallado varias veces, cosa que me preocupa; es un
  widget muy sencillo, quizás ha fallado a la hora de obtener los datos». Not the data: two builds of a
  Bitcoin chart died 17 minutes apart, ~3 min and ~1 $ each, on the SAME error — `data.py imports non-stdlib
  'memory' (data.py must be stdlib-only)`. `generator.py::_CONTRACT` said both things in one block: the
  `data.py` bullet «STDLIB ONLY», the BACKGROUND bullet «`from memory import api as memory; memory.write(…)`».
  A price chart classifies itself as data that changes on its own → the agent followed the second line → the
  gate (the stricter one) killed the widget after the money was spent. `widgets/AGENTS.md:88` had carried the
  corrected form (`ctx.remember(...)` — «so data.py stays stdlib-only, no import memory») and
  `background.TickCtx` is the sanctioned door; the prompt was left behind by that refactor, and it hid because
  it fails late, expensively, and looks like the model's fault. Two changes: the contract agrees with the gate
  (`tick(ctx=None)`, memory through `ctx`, the prohibition spelled out), and **`_repair_once`** — a freshly
  built widget that fails the gate gets the gate's own error and one bounded edit in place before `_discard`;
  a second failure reports the NEW error, what stood after the repair. Create path only; modify has its
  rollback. Node **4.161**.

- **A SEARCH is not irreversible, a confirmation never recites our tool prose, and a bare name is not an
  errand (V2-665, 2026-09-11)**: the operator, with a screenshot — «sólo le he dicho que abra el widget de
  vídeo y que me ponga un vídeo y me ha abierto el chat en la columna de la izquierda, me ha soltado mensajes
  que creo que son de sistema en la interface del usuario, no ha puesto el vídeo… simplifiquemos todo esto y
  arreglémoslo de una vez». **Three symptoms, ONE cause.** At 10:07:07 the model called `widget_data(youtube,
  search)` and `actions.classify` answered CONFIRM, so the irreversible-action gate fired: V2-518 puts
  confirmations in the chat (the column that opened), the question was composed from the action's `desc` —
  text written FOR THE MODEL, which he read as «Ojo, esto es permanente: "BUSCAR vídeos para elegir: pinta
  hasta n resultados NUMERADOS en el INICIO del widget…"» — and the overlay covered the card. **The video had
  LOADED** (`videoId 16AhQaStWxg`, «Apolo 11: cómo fue la llegada del hombre a la Luna»), dimmed behind a
  modal he could not get past; it is visible in his own screenshot. Why CONFIRM: `_IRREVERSIBLE_RE` matched
  «manda» inside «…add_results los manda a la cola» — prose describing a SIBLING action, inside an action
  declared `view: true`, which writes nothing at all. **The catalog audit is the finding**: across 15 widgets
  the heuristic produced TWO hits, both false positives (`youtube:search`, `torrent:open` — both `view: true`,
  both on «manda»), and ZERO true positives; all 15 genuine confirmations carry an explicit flag. Three fixes,
  most general first: **(1) a `view` action can never be irreversible** — the flag means it only changes what
  is displayed and «writes nothing the operator would have to undo and nothing outside the app» (the generator
  contract, verbatim), so the two are mutually exclusive by definition and only the guess put them together;
  an explicit `confirm: true` still wins. **(2) The heuristic reads the action's OWN clause**, not the usage
  guidance after the first period — the same boundary `confirm_gate._human_confirm_question` already draws
  when it quotes a desc, applied one level earlier, to the DECISION instead of to the sentence. **(3) A
  confirmation carries the sentence he hears**: NINE of seventeen confirming actions had no `confirm_q`, so
  reciting tool prose was the NORMAL path, not the rare one — the seven still bare now have one, and
  `widgets/validator.py` refuses both a bare confirmation and the `view`+`confirm` contradiction, because a
  rule each widget author has to remember is not a rule. **And the trigger**: that search came off a bare
  «Johnny.» — the wake word alone, reaching the model with a memory pill about the video he had asked for the
  night before, so it answered «Voy a buscar el vídeo del Apolo 11» and acted; six seconds later a second bare
  «Johnny.» got «Dime, Ricardo.», which is the right answer. The most frequent utterance in wake-word mode was
  non-deterministic and half the time it invented an errand. `presence.is_summons` makes it its own class
  beside the presence knock (a leading interjection and a trailing courtesy allowed — they carry no request
  either; anything else is a real turn), answered from the same honest pools with no model and no tool, in
  BOTH channels (V2-252/V2-539). The engine's own susurro had filed it at 10:07:40: «[P2·routing] Una
  locución de wake-up suelta se convierte en consulta de widget y en promesa de acción». Node **4.159** (21
  cases, including the whole-catalog ratchet that keeps the heuristic from ever DECIDING again); five disarms,
  mutations asserted, all red — and the `confirm_q` disarm also turns `make test-widgets` red, which is the
  gate biting rather than a test agreeing with itself. Open and named in the initiative: the turn that loaded
  the video returned `completion_chars: 0` and a susurro repair spoke 23 s later over work that had already
  succeeded; the fragment accumulator DUPLICATED his sentence around the summons; and the shadow arbiter
  vetoed both the correct load and the spurious search, so it still cannot arbitrate this class.
  **V2-665b, same day, found by DRIVING the live engine rather than by reading**: «Johnny.» through the probe
  still reached the model, because `fast_lane.presence` and `presence.mirror` both resolved his name with
  `config.settings.get("assistant_name")` — **a key nobody writes**. A rename lands in MEMORY state and is
  pushed into `voice.attention` by `memory_cache`; the settings file has held `None` the whole time. So this
  is a defect OLDER than the batch that found it: the vocative strip that recognises «Johnny, ¿sigues ahí?»
  as a knock has been dead for a renamed assistant since V2-640 shipped, and the summons check would have
  been born dead the same way — **passing its own unit tests, because those handed the name in by hand**.
  `presence.assistant_names()` is the single source now and asks the authority (`attention.wakewords()`, the
  same list the gate itself consults: default + env + rename); both callers stop reading the settings file,
  and `is_presence_check` strips every name it should, longest first. The node grew an end-to-end drive of the
  REAL probe mirror, and its guard is anchored on the IMPORT rather than on the words — both files explain
  this defect in prose, and a scan its own explanation trips is a scan that gets weakened instead of believed.
  Sixth disarm red.

- **An order about DATA is not an order about the CANVAS — and «me vas a poner el vídeo» is an order
  (V2-664, 2026-09-11)**: the operator drove his own session and reported three things: the Apollo 11 video
  never played, «borra los datos de la agenda» **closed every widget he had open**, and twenty seconds later
  the YouTube card **reopened by itself, empty**. He then asked the question that shaped the batch — are the
  GUARDRAILS failing, or the errand harness we have just been adding? **Session eedf7f9b contains ZERO
  harness events**: no goal was born, no `false_claim` ran, nothing escalated. V2-660/661 did not fire once.
  All three are rails, each correct in intent and wrong on one sentence.
  **(1) The media grammar does not know how Spanish asks for a video.** «Bien, me vas a poner el vídeo del
  Apolo 11 llegando a la luna» → the model DID call `play_video(query="Apolo 11 llegando a la luna")` and
  `canvas_license.video_license` ate it as context-bleed: the pattern spells out the infinitive of every verb
  it knows (cargar, buscar, reproducir, abrir, cambiar, repetir) except the commonest one —
  `pon(?:me|te|le|lo|la|gas?|ed)?` **cannot reach «poner»**, because after «pon» come word characters and the
  `\b` fails. The periphrastic form («me vas a poner…», «¿puedes ponerme…?») is how a person actually asks,
  and it was the one shape the guard could not see; the turn ended promising «Y ahora te pongo el vídeo del
  Apolo 11» over a player that never loaded. Fixed by adding the infinitive/gerund/future stems (plus
  `mostrar`/`ensenar`, missing for the same reason); V2-635's participle rule is untouched. Second-order and
  worth recording: the veto marks the turn `deduped`, so the promise backstop stayed quiet over it too.
  **(2) A bare quantifier is not the canvas until it says so.** `hard_interrupt` fired close-ALL on *(a close
  verb ANYWHERE) AND (a quantifier ANYWHERE)* — his sentence carries «quita» in one clause and «todas esas
  entradas» fifteen words later in ANOTHER, so an order to delete ROWS INSIDE the agenda wiped the desktop,
  twice (the glued fragments re-fired it). The rule is now structural and needs no lexicon of intentions —
  grammar, never intent (V2-095): look at what the quantifier **governs**. Nothing («cierra todo»), a
  particle («ciéralo todo ya») or a card noun («todos los widgets») is the canvas; any other noun («todas
  esas entradas», «todos los datos») is a thing inside a widget. Implemented in BOTH copies, because the
  decision genuinely exists twice (`voice/attention.py::_quantifies_the_canvas` and the client fast lane's
  `quantifiesTheCanvas` — V2-252/V2-555, with a test reading both). V2-600's fullscreen veto and V2-584's
  stop-object rule are untouched.
  **(3) The fail-open release was driving the canvas.** V2-647 holds a spoken turn until the gate rules and
  fails open after `HOLD_MS`, on the stated rationale that *showing an ambient line is a nuisance, swallowing
  a real one is the bug*. Two things were wrong: **2.5 s is shorter than the verdict it waits for** (the
  accumulator holds an unfinished sentence for as long as he keeps talking — his verdict landed 2.86 s after
  the first held fragment, so the hold was in practice not holding), and **the release delivered BOTH
  halves**. At 09:40:24 it fired 0.36 s before the verdict while he was describing this very failure out loud
  («…que ha sido poner un vídeo…», every fragment correctly ruled AMBIENT) and the fast lane opened the card
  he had closed. The two halves are not equally reversible: `deliver(text, isFinal, judged)` now carries
  whether a verdict actually ruled directed, the CHAT still fails open, and the CANVAS never does.
  Nodes **3.36** and **4.158** (the client half drives the REAL `voiceCommands.js`), plus five new groups on
  4.145. **Six disarms, each mutation asserted before measuring, all red.** ⚠️ 4.158's own trap: the fast lane
  dedupes an identical action signature for 2.5 s, so two `closeAll` cases in a row measure the DEDUPE and not
  the rule. ⚠️ Renumbered at closure: the concurrent session had already PUSHED the two numbers below this
  one, and what is pushed wins — the initiative file is created when the number is TAKEN, not at the end. **NOT verified live**: needs an engine restart and a page reload. Open and named in the
  initiative: four duplicate «dentista» crons injected as four identical notes into one turn, and the product
  question of a reminder riding the turn it interrupts (V2-607's design, his call).

- **The window measures SILENCE, not speech — and a text the agent produces is FILED in the library
  (V2-661, 2026-09-11)**: «prioridad absoluta: le digo la palabra, hablo de forma continua sin pausas de 3 o
  5 segundos, y me desactiva el micro — se apaga el color del orbe y yo no he terminado la frase». Session
  1cdcb08e, 00:46: with the window open he spoke for **47 s** with no gap over 1.1 s — eleven VAD rising
  edges, the STT holding the sentence as «frase a medias», no verdict possible mid-sentence — and the whole
  sentence was judged AMBIENT at :52. V2-660 had made the window measure from the speech ONSET, but every
  rising edge re-stamped that onset, so the sentence was measured from its LAST breath, 33 s after the
  anchor: the fix for «judged at the end» had moved the reference to the wrong start. The ring died 5 s in,
  because its client timer only knows the last DIRECTED verdict. His rule (V2-655): three or four seconds
  **of silence**. Now an utterance is a CHAIN of VAD segments: `note_speech_onset` keeps the chain's first
  onset when a rising edge follows the falling edge (`note_speech_end`, new) by less than the window;
  `note_directed` moves the onset ONTO the anchor when a fragment's verdict lands while he is still talking;
  `_window_ref`/`window_open` answer `now` once his voice stopped and the silence outlasted the window; a
  180 s cap bounds a missed falling edge. Both VAD events carry `edge: on|off` and `sse.js` holds a LIT ring
  while his voice is active, re-arming a full window when it stops — never lighting one from off. **The
  file**: «¿has guardado la declaración en mis archivos?» → the worker fetched and verified the text and
  wrote a perfect `.md` into `widgets/_data/navegador/` — the browser task's directory, the only path it had
  ever been told — then saw the `archivos` shelf empty and spent three minutes trying to download a PDF.
  Resource, not reasoning: `library/index.save_text` (one safe leaf, `.md` when the name has no document
  extension, collisions suffixed), `archivos.save_document {name,text}` (lands the card on the shelf with the
  file selected, returns `where` + absolute `path`), `documento.save_to_library` (the text ON SCREEN becomes a
  file — one data-op, no worker), and `dispatch_prompts.library_block()` appended to every trusted worker
  prompt: the root, the shelves, the filing action, and the wrong place it actually wrote to. Nodes **3.34**
  and **4.154**; four disarms, mutations asserted, all red. A sibling session owns the other half of that
  night (`reveal_local_file`: a double-click must not download a second copy). ⚠️ The ring holding through a
  long sentence is NOT verified live yet.

- **The errand HARNESS closes the circle, and the window measures silence from speech ONSET (V2-660,
  2026-09-11)**: the operator's directive — «cuando obtiene permiso para realizar una acción falta terminar
  de cerrar el círculo… un arnés dinámico que comprueba que lo pedido se ha conseguido y solo entonces se
  informa». Session 0141a72a, two defects in one minute. **(1)** «Johnny.» opened a 5 s window; he began
  «Enséñame la declaración…» 2 s later and the STT finalized it 6 s later — judged at the END it fell
  outside the window and three directed turns became room noise. The window measures his SILENCE, which
  ends when he opens his mouth: `attention.note_speech_onset()` (VAD rising edge, `pipeline/agent.py`) and
  `_window_ref()` measure against the onset when it fell inside the standing window (a stale onset older
  than the anchor grants nothing). **(2)** After his «Adelante» the model said «aquí tienes el texto
  completo…» having run ONE web_search — `documento` open and EMPTY — and nothing compared the claim with
  the screen: `promise_backstop` reads promises, not completion claims; `_no_tool` was False because the
  search fired; the susurro caught it 40 s later. **`nucleo/harness.py`**: a ledger of GOALS `(kind,
  target, his words)` born from what the turn TOUCHED (every card shown, incl. the promise-backstop show),
  verified by readers of the product's own truth (the widget's `view_data()` `empty` flag + the open-cards
  state; a widget that does not declare emptiness → unverifiable, and the harness stays SILENT — a wrong
  «you did not deliver» over a delivered card is worse than none). Three seams: turn end in BOTH channels
  (`claims_done` over an unmet goal with no data-op this turn — the V2-603 fire-and-forget race is trusted
  — → the honest follow-up is spoken, V2-572 shape, and the errand escalates with the doc surface quoting
  his words); the prompt's live state (an open goal is a FACT with its RULE, V2-453); the loop heartbeat
  (met goals close with an event — no second mouth, the delivery announced itself). Typed by the WIDGET
  touched, never by an errand's words — the doctrine's word-swap test holds. F2-F4 named in the initiative:
  widget-declared verifiers (his CRITERIA, the language), worker goals closed by delivery events, bounded
  iteration, and the clarifying-question hinge (a «¿te refieres a X?» + yes should bind to the original
  request; `dispatch_confirm` parks only PERMISSION questions). Node **3.33** (18 cases); five disarms,
  mutations asserted, all red. ⚠️ NOT verified live end-to-end.

- **A widget_data cut by the TOKEN CAP escalates with the doc surface instead of apologizing (V2-658,
  2026-09-10)**: «le he dicho un documento y no lo ha hecho» — measured twice in consecutive sessions
  (the Declaration of Independence): the model opened an EMPTY `documento`, promised twice, finally
  pasted the FULL text inline into ONE `widget_data` → `finish_reason: length`, the action was
  discarded (V2-171's recording worked), and the turn fell to the mute backstop's «Perdona, ¿me lo
  repites?» over an errand it had in hand. Content that exceeds a voice turn is a WORKER's delivery
  (V2-644's doc surface), never an inline retry: `_drop_tool_call` records **`args_head`** (the head of
  what the model was writing — the operator's bare turn text at the incident was «Venga, estoy
  esperando.», useless as an errand), `oversized_widget_write()` names exactly the token-capped
  `widget_data` class (the other two drop classes are different faults, V2-566, and are NOT escalated),
  and both channels rescue: the voice provider escalates the request with `surface=documento` BEFORE
  the holding line so the turn speaks it, the probe synthesizes the same `escalate_to_slowbrain` before
  action classification. The `documento` manifest teaches the rule (costs prompt only with the card
  open — exactly the failing state). The same session live-verified V2-657: ~90 s of wedding room talk,
  zero responses. Node **3.32**; four disarms, mutations asserted, all red. ⚠️ NOT verified live
  end-to-end (needs a real worker run).

- **The conversation can DIE during table talk: the aside, the spoken shut-up, and the honest provider
  label (V2-657, 2026-09-10)**: the operator's dinner session (130418ed), read event by event. With a
  window open, every table utterance was admitted `active_window` (V2-531: inside a live window nobody
  judges), the model ANSWERED the room («Acostaros» → «Buenas noches, Ricardo»; «Luis, disfrutemos de
  las noticias…» → a clarifying question; «¿Mi copa de vino?» → a hallucinated denial), and both the
  admission (`note_directed`) and the answer's falling edge (V2-655) re-anchored the 5 s window — the
  conversation structurally could not die while anybody talked near the mic, until «¿Por qué sigues
  escuchando? Maldita sea, cállate. Apaga.» and the ⏻ by hand (killing a live worker with it). Three
  mechanisms: **(1) `[[aparte]]`** — the model's SANCTIONED silence for a turn clearly addressed to
  somebody else present (rule rides the wake-word block of `style_directive.prompt_lines`; ante la
  mínima duda, contesta): the channel marks the turn handled (never on TYPED, V2-646), skips the hollow
  repairs (a sanctioned silence is not a hole for V2-642's closer to fill), and
  **`attention.retract_last_directed()`** rolls back exactly that admission's window refresh — refusing
  once anything newer re-anchored, because deafness is the worse failure (V2-655); the window then
  expires from the operator's own last word. Probe mirrors the backstop skip. **(2) A spoken SHUT-UP
  order** («cállate», «silencio», «deja de escuchar»; per-sentence, vocative-stripped, interjections
  admitted — the session's literal «Maldita sea, cállate.») is an ATTENTION order resolved at the gate
  BEFORE any model: `attention.close_window()` (shared `_wipe_window()` with the V2-656 mode flip, same
  `orb:attention` emit) and the turn is swallowed — answering it would re-anchor the window it ordered
  shut. «apaga/apágate» deliberately stay out: they name the power or a device. **(3) The provider
  LABEL derives from the endpoint** (`model_spec._provider_label`; `ollama` honoured — it IS routing):
  that session's every brain event said `engine: aimlapi` while every request went to
  `api.deepseek.com`, and the stale label had been resurrected at 21:59 by the remote PROFILE, whose
  `fast` section still declared the broker under a rationale that stopped being true when the cloud
  moved to DeepSeek direct — profile aligned to the canonical table titular, with a test measuring it
  AGAINST the table. Node **3.31**; six disarms, mutations asserted, all red — one came back GREEN
  first because the wiring guard's anchor also matched the second occurrence of the same expression
  (the V2-571 lesson, paid again; re-anchored on the unique `or (` shape). ⚠️ NOT verified live —
  needs an engine restart. Open, named: a filler can still sound over an aside turn (the addressee is
  only known post-model until V2-651 F1), and «apaga» by voice reaches no power switch on purpose.

- **A bare boot loads the PRODUCT, a dead session is VISIBLE and recycles, the ◉ reads the speaker side,
  and no conversational pause exceeds 5s (V2-656, 2026-09-10)**: the operator's integrity review after an
  evening lost to a restart without `BRAIN=nucleo` — the profile default handed the AgentSession the raw
  broker plugin (no FlashBrain, no memory, no relay), the fundless provider 403'd every turn, LiveKit
  closed the session as unrecoverable at 38 s, and the ◉ said «Todo bien» while he talked to a grey orb.
  **(1)** Both profiles default `llm` to `nucleo` (`profile.py`) — baselines stay one env var away; booting
  the real product never again depends on remembering one. **(2)** A close-with-error records
  `health_state("voice","dead")`, alerts the timeline, and asks `homeostasis.request_recycle()` (new seam
  `_consume_recycle_request`: honoured next beat, survives the cooldown, never loops); the `/api/status`
  voice row goes RED and `StatusPanel.js` stops overwriting a server-side error with the browser's green —
  the browser's room stays connected when the server session dies, so it structurally cannot see this
  failure. **(3)** `voiceStatus` says the two silent «no me habla» causes (blocked playback, the 🔊 mute);
  `server/system_audio.py` reads the MACHINE's output (macOS osascript, cached): volume 0 / muted → warn,
  and an unmeasured OS gets NO row, never a fake green. A genuinely dead ElevenLabs key reddens the TTS
  row via the balance probe; a key that 401s only `user_read` records nothing — measured first: the
  operator's scoped key serves TTS fine. **(4)** The broker left every DEFAULT path (profile default gone;
  the stale `fast.provider` label removed from the operator's v2.json → the canonical table's DeepSeek
  titular governs). **(5)** Operator directive superseding 2026-09-09's ceiling: **no pause over 5 s** —
  `attention_window.MAX_S`=5 (the shape scale stays, every rung clamps), and `window_s()` clamps AFTER the
  env override in smart mode, because the ⚙ knob offered 15-120 s and an old stored value would have
  silently defeated the rule (options now 3/4/5). Livable because V2-655 anchors at the agent's LAST word.
  **(6)** A mode FLIP closes the standing window NOW (`attention.on_mode_change`, called from the single
  `settings.update()` seam only on a REAL change — a bulk save re-sending the same mode wipes nothing) and
  announces `orb:attention`, where `sse.js` now also darkens the ring: he measured 20+ s of orange after
  activating wake-word mode, riding out a window opened under the previous mode. Node **9.3** + additions
  to 9.1 and the attention suite; four disarms, mutations asserted, all red. ⚠️ NOT verified live: the
  3-second ring darken and a recycle after a real death.

- **IF IT TALKS TO YOU IT LISTENS TO YOU · the core is not modifiable · ⏻ stopped resumes nothing
  (V2-655, 2026-09-10)**: the operator, on the forensics of session 85eec898 — «arregla todo eso, no
  podemos permitir la sordera». Three defects, one shape: every piece does something correct and the
  SUM fails in silence.
  **A · THE DEAFNESS.** Sixteen of his turns in a row classified `🙉 ambiente`, «¿Qué te ha pasado?
  ¿Te has colgado?» and «Hola otra vez ×3» among them — 44% of that session. The window opened at
  16:31:55 sized 15 s and expired at 16:32:10 while the agent was still working; it then spoke for
  **90 seconds** and ended with «¿Sigo?», and the answer two seconds after its last word was room
  noise. Structural, not a classifier miss: `note_bot_speech` could only HOLD a window somebody else
  opened, so **the agent's own mouth could never grant attention** and the silence clock ran down
  during its own monologue — with the irony that a proactive delivery DOES reach `note_reply`, so one
  ending in `?` computed a 15 s `window_hint` for a window nobody opened. `attention.
  note_addressed_speech()` now ARMS the window before the agent speaks and the falling edge ANCHORS it
  at the LAST word (arming and not anchoring is the whole point: anchoring at the first word of a 90 s
  delivery IS the bug); `proactive.notify(opens_window=True)` by default, because that is what a
  proactive delivery IS. **The kickoff stays closed** — the written decision was always about the
  GREETING, and the guard was re-scoped to say that rather than weakened. `loop.py` stopped opening the
  window BEFORE its own 10-20 s of TTS. And **ambient sound does not touch the counters** (his rule,
  verbatim): `sse.js` did `else store.clearAttentionHit()`, so **a stray word from the room turned off
  his «te escucho» ring** while the engine's window was wide open — the client contradicting the engine
  about the one thing the ring reports; both verdicts carry `window_open` now, the ring darkens only
  when the engine says the window closed, and never re-arms a ring already lit. **Deliberately NOT
  done**: widening the gate (the 09:24 session has 603 discarded turns and ZERO directed, with nobody
  ever saying the name — that is V2-647 working), and any new signal (his call: ambient is ignored,
  full stop).
  **B · THE CORE IS NOT MODIFIABLE.** His directive: voice, chat or any interface with permissions may
  only modify WIDGETS. A message he pasted into the chat, written for a DEV agent, became an errand to
  a `claude_code` worker **in the same second** the model asked «¿Me pongo?»; the only thing that
  stopped it was the SPEND gate, and `danger.py` is money/commerce vocabulary with **not one word about
  touching the engine** — a coincidence, not a control. The protection that seemed to exist was
  accidental: the `architect` branch is also `kind="code"` WITHOUT being a widget task, and that one
  does not go through the confined generator — a CLI worker with `Write`+`Edit` and **the whole
  repository as cwd**, reachable by voice. `nucleo/protected_core.py`, two layers: MECHANISM
  (`writes_are_confined` — the question is the ERRAND, not the kind; only the widget generator and the
  cluster dev worker write, everything else gets a scratch cwd and no Write/Edit; fails CLOSED) and
  INTENT (`touches_the_engine` — grammar, never intent, exempted when the sentence names a widget,
  applied at the SINGLE gateway so the errand never comes to exist: no record, no sheet, no name; the
  refusal is spoken and lands on the timeline, because refusing in silence reads as a fault). **No
  `confirmed` escape hatch**: the spend gate is lifted by a yes, this one is not. ⚠️ Measured while
  writing it: the Spanish SUBJUNCTIVE slipped through — `modific\w*` does not match «modifiques»
  (modifi-QUE-s), so «quiero que modifiques el motor de voz» passed clean; prefixes cut before the
  alternation now. 10 vetoes + 12 legitimate errands, 0 failures both ways. The cluster `dev` channel
  stays outside on purpose and says so.
  **C · ⏻ STOPPED.** With `{"state":"stopped","src":"operator"}` persisted, boot resurrected a stale
  errand and spawned a GLM Brain Worker; `rehydrate.py` consulted the switch in NO line. The gate goes
  at the TOP, before `forget()` consumes the trail and `_bump()` burns a `RESUME_CAP` life — gating six
  seconds later at the dispatch door rejects correctly and **destroys the interrupted work in
  silence**, the very failure that module exists to prevent (*postpone, don't lose*, the rule
  `loop._fire_due` already applies to crons). `runstate.blocks_new_work()` is the ONE answer for the
  three spending doors and **fails CLOSED**: all three carried their own try/except and **all three
  failed OPEN**, so an unreadable switch meant «go ahead and spend» (the asymmetry with `stopped()` is
  deliberate and written down). Second door found and closed: `resume_interrupted_generations` relaunches
  a real `claude -p` and was gated by neither the switch nor the active brain.
  **D · A QUESTION IS NOT THEATRE.** `clarifying.asks_permission` is a NEW grammar and deliberately not
  the existing `asks_for_missing_detail`, which is about a missing DATUM and keeps courtesy OUT; the
  distinguishing feature is what the question is about — STARTING («¿me pongo?») versus REPORTING LATER
  («¿te aviso cuando lo tenga?»). The errand is PARKED in `dispatch_confirm`, which already collects the
  yes/no deterministically, tells the brain something is stopped so it does not narrate progress, and
  expires silence into «esa tarea NUNCA empezó» rather than into execution; the line says OFFERED, never
  IRREVERSIBLE. Fails CLOSED. ⚠️ A disarm came back GREEN and accused the CODE: the courtesy veto guarded
  NOTHING («te aviso» was never a permission phrase) and would have vetoed «¿te lo busco y te aviso
  cuando lo tenga?», which IS asking — **a guard that guards nothing is worse than none**, deleted.
  Nodes **3.27-3.30**, 16 disarms with each mutation asserted. The architecture ratchet went red three
  times and was paid by EXTRACTING (the attention gate → `attention_turn.py`, nucleo.py 3049→3033),
  never by raising a ceiling. ⚠️ **NOT verified live** — needs an engine restart.

- **THE MICROPHONE SWITCH has ONE door, and it is not the wake-word mode (V2-654, 2026-09-10)**: the
  operator, reading the forensics of session 85eec898 — «cuando yo desactivo el icono, ese estado es
  TOTAL … el estado se debe controlar en un solo sitio y controla todo el sistema. No puede fallar
  nunca.» He was right and it was worse than it looked: `store.micMuted` + `hb_mic_muted` had **SIX
  writers and four of them only painted an icon** — the boot probe on both shells, the ⏻ power button on
  both shells, the mobile dock, the server-stopped branch — because `applyMic()` was not on their path;
  and there was **no fourth thing to move at all**, since the engine had no notion of a microphone
  switch, so a correct client could not be checked and a wrong one could not be caught. Measured: the
  icon read CLOSED while the track published, the engine transcribed him for seven minutes and escalated
  an errand off what it heard. The mobile file's own comment already NAMED the failure («the phone would
  paint itself off with the mic open — the state that lies, again») and the line under it still only
  painted. Two secondary faults in the same path: `setMicrophoneEnabled` returns a PROMISE whose
  rejection a synchronous `catch` cannot see (a failed publish change was a silent divergence), and
  nothing re-asserted after a republished track. **`frontend/app/services/mic.js` is THE door**: one
  write moves the SIGNAL, the STORAGE, the live TRACK and the ENGINE (`POST /api/mic`), with the
  transport injected by whichever session engine is live and **registering APPLYING** (the reconnect
  hole). **`voice/mic_input.py` is THE holder**, and its `blocks_turn()` is consulted in the turn path
  ABOVE the attention gate: a closed mic reaches no model, no tool, no widget, no memory, no errand.
  Failure directions are deliberate and asymmetric — **muted is STICKY** (a client that mutes then dies
  leaves the engine muted, the safe side) and **the boot default is OPEN** (a stale client must never
  leave the agent deaf forever — deafness is the OTHER failure that same session paid for, 16 turns
  discarded in a row); the **session heartbeat re-asserts every ~4 s**, so a divergence in either
  direction self-corrects without anyone remembering to, and `muted` stays OPTIONAL on the beat so an
  older client beats as before. **NOT the attention mode, and neither may be written in terms of the
  other** (operator's clarification mid-build): the 🤖 wake-word mode is what makes a permanently open
  microphone livable — audio arrives, is transcribed, and `attention.py` decides turn by turn what was
  addressed to us — and **those rules are untouched**; a hard close is consulted first and **no wake word
  lifts it**, lifting the close **changes no attention state**, and a swallowed turn never reaches
  `note_directed()`. The one exemption is the TYPED turn, because muting in order to type IS the use
  case: consumed **one-shot** (`attention.consume_typed`, beside the window-based `was_typed` the mute
  backstop owns), never on a time window — with a window, typing and then speaking walks the spoken turn
  straight through the closed switch. It is deliberately **not a privacy boundary against the browser**:
  a live track still reaches STT and the transcript still lands in observability, because that transcript
  is the EVIDENCE of a divergence and hiding it is what made this cost seven minutes to see. Nodes
  **3.26** (engine) and **4.152** (the frontend RATCHET — nobody writes the mic state outside the door,
  nobody touches the track outside a session engine; the incident was not a broken function, it was six
  writers of one state, and *a rule each caller has to remember is not a rule*). Nine disarms, each
  mutation asserted, all red. The architecture ratchet went red mid-build and was paid by EXTRACTING the
  rule to `mic_input` rather than raising the ceiling. ⚠️ **NOT verified live** — needs an engine restart
  and a page reload.

- **The CANVAS ARBITER — one decision tree for every widget mutation, shadow first (V2-653 F0,
  2026-09-10)**: the operator's structural verdict after 30 days of widget incidents — «cada vez que
  hago una prueba me falla por un lado o por otro… un catálogo de <15 widgets: un sistema de puertas
  lógicas podría manejarlo; los usuarios van a forkear widgets, el sistema tiene que ser
  estructuralmente sólido; decisión piramidal, pocas opciones por nivel» — and this pass's own census
  agrees: ~8 doors mutate the canvas, ~13 guards veto a posteriori across ~10 modules and 2 channels,
  each correct and measured, and the SUM is a blacklist that never converges (every session finds the
  next gap) whose pieces now collide (the V2-652 silent tail = two correct guards interacting).
  `nucleo/canvas_arbiter.py` inverts the posture: every mutation is judged by ONE pyramidal tree
  needing TWO credentials — PROVENANCE (closed set: user/system/worker:tid/actionmap/flash/backstop;
  an unknown src or op inherits NOBODY's pass) and a LICENSE (the operator's words in THIS turn, a
  task that owns the surface, or his own hands). The proven guard modules are the tree's LEAVES
  (`canvas_license`, `close_guards`, manifest-driven `producers`/`actions.is_view`/`runtime.identify`),
  so a user-forked widget inherits the rails from its OWN manifest with zero code of ours.
  **F0 is SHADOW, deliberately** (the V2-651 pattern): `decide()` is enforced nowhere; ONE tap in
  `observer.emit` — the funnel every canvas command already travels as a `widget` event with `src`
  (V2-039), every turn as a `transcript`, every gate ruling as an `ambient` — assembles context and
  emits `kind="arbiter"` verdicts (allow/veto · rule · evidence; `_CAT` family `widget`; kill-switch
  `ZAELAR_ARBITER_SHADOW=0`; re-entrancy-guarded, fail-open). `data:*` order logs now CARRY their
  payload, so `payload-in-turn` is judged precisely. **The conformance suite is the month replayed**:
  V2-567 (a close order licenses no show), V2-605, V2-635 (insults close nothing; pausing is not
  fullscreen), V2-650 (a replayed play order is an order; the dentist duplicate stays dead), V2-650b
  (chatter reopens nothing), V2-652 (the drag turn), ambient credit, backstop duplication — node
  **3.25**, all green against `decide()` first try. Its own first run found `op=None` walking out as
  `lifecycle` (op vocabulary validated BEFORE the provenance ladder now), and a carrier disarm came
  back green TWICE (the tap test hands in its own dict; then the fix's regex died on the first paren
  and failed on GOOD code, masked by a pipe eating pytest's exit code — measure both directions, with
  pipefail). **Gate F0→F1, the operator's condition**: ZERO false vetoes over his real sessions,
  audited from the shadow verdicts. Then F1 arms data-ops at `widgets/server_api._dispatch` (verdict
  travels as a ticket via `provenance`), F2 funnels the ~15 scattered `emit("widget","show"/"close")`
  sites through `arbiter.command()`, F3 RETIRES each absorbed guard (dedupe cross-turn, `show_
  contradicts_the_order`, the probe's duplicated wiring) with its disarm inverted — the system ends
  with FEWER pieces. Census, tree diagram and full plan: the V2-653 initiative.

- **An internal message never reaches the operator's ears, a cover matches the order, and the agenda
  never invents an hour (V2-652, 2026-09-10)**: the operator's manual session (7f77e2cc, «pide cita
  previa en Hacienda»), read event by event — five defect classes, four closed here. **(1)** `add_meeting`'s
  retry instruction («vuelve a llamar a add_meeting con el título, el día (YYYY-MM-DD)…») was SPOKEN aloud
  and painted into the chat as zaelar's own words, twice: `data_ops.report_failure` (V2-603) voiced
  `message or error`, and `error` is often literally addressed to the MODEL. Now only `message` (the
  speakable sentence, the V2-463/V2-650b convention) is voiced; a bare `error` still corrects the model
  through the [SISTEMA] note but never becomes agent speech — and the agenda's empty-add refusal carries
  both keys. **(2)** «…Añade en la agenda mañana una cita» was covered with «Un momento, que lo busco…» and
  the complaint «Te he dicho que hagas una acción sobre la agenda» with «Déjame que lo mire…»:
  `filler_kind` now judges per SENTENCE with the leading vocative stripped (the order lives in the LAST
  sentence of a spoken turn), `_ACTION_VERB_RE` knows the data-write verbs (añade/apunta/anota/recuérdame…,
  es+en), `_SOCIAL_RE` knows complaint shapes, and an explicit imperative outranks the complaint beside it.
  **(3)** The «17:00» item he read as us copying his «reunión a las cinco» was `add_meeting`'s own
  `default="17:00"` over the promise backstop's hour-less write: a missing hour is a FACT — no hour → an
  all-day entry, and a timed add of the same day+title SETTLES that twin in place (one row, the dictated
  hour) instead of standing beside it («dos ítems»). **(4)** The errand escalated onto `lista` and the
  worker delivered a booking as a comparison sheet of non-options: the escalation `surface` gloss now
  teaches that a GESTIÓN (reservar, pedir cita, tramitar) is voz — delivered DONE, never a list — paid
  under the shared catalog ceiling by compacting the same tool. **(5a)** The worker typed the placeholder
  NIF «12345678Z» into Hacienda's REAL form twice and ground the census-validation modal for minutes: the
  web prompt's RECON/ASK discipline now says recon ENDS at a validated personal field — ask
  (`worker_bridge ask`) or deliver the blocker naming the datum, never retry with invented values. Nodes
  5.15 / 2.50-family files / 4.6 / 4.151; nine disarms, mutations asserted, all red — one came back GREEN
  first because its strip anchor matched an earlier «bucle» in the file and nothing had mutated (assert the
  mutation before measuring, paid again), and the V2-650 checkout-over-uncommitted-fix trap was paid once
  more before switching to commit-before-disarm. **Open, named in the initiative**: the SILENT TAIL (ten
  consecutive zero-char replies while the dedupe swallowed a context-bled add_meeting — a spoken DIRECTED
  deduped turn still counts «handled», V2-646's rule is typed-only), «Quítalo inmediatamente» never
  reaching `cancel_meeting`, Flash reframing a booking as research in the escalation brief, and showing
  the worker's browser for a voz-surface errand.

- **Knowing WHO is talking — the browser computes it, F0 measures in shadow (V2-651 F0, 2026-09-10)**:
  the operator's order — identify HIS voice and give it priority (which is also what lets Zaelar follow him
  over a TV: a TV voice is a human voice, only the voiceprint separates it), know that other people are
  present without profiling them, and NEVER let a third party's «yo soy Pedro» rename him or dirty his
  single profile. Architectural directive: **the browser carries the cost** — in cloud the backend is on the
  server and the browser on the client's laptop, so the fingerprint is computed CLIENT-SIDE and only a tiny
  label would cross the wire, never the audio-to-analyze (local self-host is one machine, so the split is
  free). This ships **F0 only: shadow measurement, ZERO behaviour change.** `frontend/app/lib/speaker-id.js`
  is a pure DSP core (autocorrelation pitch + spectral centroid + loudness, unit-tested with synthetic
  frames) plus a thin `SpeakerID` AnalyserNode adapter that self-segments (its own energy gate — the LiveKit
  engine gives the browser no VAD signal), auto-enrolls the operator's first speech segments, and classifies
  every later segment against a MAP of profiles (`classify`) — operator today, household voices tomorrow, an
  ONNX embedding (CAM++/onnxruntime-web) later behind the SAME interface, all without changing this file.
  `session-lk.js` runs it in a best-effort rAF started after `audio.initMic` and stopped in `stop()`, logging
  each verdict (label · score · operator score · pitch/centroid/rms) through the EXISTING `api.clientLog` seam
  into observability — nothing gated, no memory written, killable with `?nospk=1` / `zaelar_spk_shadow=0`.
  Its whole job is to produce the separability numbers on the operator's real mic/room BEFORE any later phase
  thresholds against it (measure, don't deduce). Node **4.150** (8 groups); five disarms verified red.
  **A review pass the same day found three real defects in this very build, all fixed here**: (1) the coarse
  vote is unusable as a measurement — `matchScore` is a 3-criteria vote, and measured across 60 distinct
  synthetic voices it returns exactly THREE distinct values, so every verdict now also carries `distancesTo`,
  a CONTINUOUS per-feature z-distance (that is what F1's threshold gets chosen from); (2) the agent's OWN TTS
  comes back through the mic and could be auto-enrolled AS the operator, poisoning the measurement — a
  `suppressed()` predicate wired to `store.botSpeaking()` now discards anything in flight and fingerprints
  nothing while zaelar talks; (3) TWO wiring assertions were weak in the same way — `_stopSpeakerShadow()`
  also matched the function DEFINITION, and the start-ordering check merely asserted two independent
  substrings existed, staying GREEN with the lines swapped — both re-anchored on the real call sites and
  re-disarmed. Measured cost: `pitchOf` is 0.91 ms/frame ⇒ ~27 ms/s ≈ **2.7% of one core**, only while speech
  is active.
  ⚠️ **NOT verified live**: the real mic tap and the fingerprint's accuracy in a room need the operator's
  engine — F0 exists precisely to gather that. Next, per the study: F1 identity shield (operator-voice-only
  writes to identity/state, closing the empty-profile and correction-bypass holes), F2 the «environment
  people» roster + a compact per-turn presence line the FlashBrain manages cheaply (no per-turn prompt/traffic
  cost when nobody else is there), F3 the opt-in hard voice-lock. **Mechanism, limits and how to read the
  shadow log: `.meshkore/docs/modules/zaelar-speaker-identity.md`** (the phase plan lives in the initiative,
  which is not published). One measured interaction named there and load-bearing for F1: `attention.py`'s
  active-conversation shortcut (V2-531) means that INSIDE a live window nothing is judged — with a TV on, room
  lines were logged `👂 dirigido a zaelar` and answered — so a speaker check must be consulted BEFORE that
  shortcut or a perfect voiceprint would change nothing.

- **A just-closed widget does not reopen on chatter, and a garbled list name resolves or refuses
  naming what exists (V2-650b, 2026-09-10)**: the operator's very next live minute (sid 3d394…), read
  event by event. «Johnny, cierra el widget de YouTube» worked exactly as designed (the V2-567 guard
  discarded the model's spurious show, the backstop closed) — and eight seconds later ROOM CHATTER
  («Avisando de… cuidado, que aquí está pasando algo») made the model re-emit that DISCARDED
  show_widget, and nothing blocked it: the card he had just closed reopened over nobody's order.
  V2-635 built licenses for close, video and fullscreen; **SHOW had none**. New
  `canvas_license.reopen_license` (narrow on purpose): only a widget the OPERATOR ordered closed in
  the last two minutes is gated, and it reopens on a conjugated media/show request or when his own
  words resolve to that widget through the V2-082 certainty resolver — never on chatter; a discarded
  drag counts as handled (`deduped`). Every close door records the close (`note_operator_close`: the
  tag funnel, the named-close backstop, the close-not-delete guard, the action map's fast lane), and
  both channels consult the license (probe mirrored, parallel-impl rule). In the same minute, «arranca
  la lista de Trublo» (the STT's rendering of «True Blue») was served TWICE by two mechanisms — the
  `play_music` tool played the SONG, then a re-emitted `play_playlist` data-op failed
  `playlist_not_found` on the garble and the correction path read the RAW CODE aloud
  («playlistnotfound») over music already playing. `play_playlist` now resolves a spoken garble by
  unique-winner similarity (≥0.6 with the runner-up under 0.5 — «Trublo»→«True Blue» measures 0.71
  against 0.27 for the next list; two near-matches stay a refusal, never a guess) and its refusal is a
  SENTENCE that names the existing lists (V2-463 — `report_failure` already speaks `message` when one
  exists). The provider ratchet (3043) was paid by extracting the whole show_widget resolution to
  `show_target.resolve_show` (guard-target passed IN — importing it there would add an upward
  dependency the V2-569 ratchet freezes); nucleo.py ended at 3036. Node **4.149** (+3 cases in
  4.148's musica file); four disarms, mutations asserted, all red — run AFTER committing the fix,
  which is the V2-531 lesson applied instead of re-paid. Detail: the V2-650 initiative.

- **A replayed play order is an order — and the playlist keeps the playback it started (V2-650,
  2026-09-10)**: the operator's morning session (aed0736c, the «True Blue» errand), read event by event.
  The worker did its job — refused the torrent as protected, confirmed the real album (Flash had escalated
  «"Blue" de Madonna (es un álbum de versiones de blues/jazz)», an invented gloss), built the 9-track list
  and verified it on screen. Then the music died twice, silently. **(1)**
  `widgets/musica/data.py::play_playlist` loaded its store snapshot, called the provider — which resolved
  track 1 and wrote `yt.videoId` + an 8-track queue into the store through its own load/save, exactly the
  read-modify-write contract the file's own header declares — and then persisted the STALE snapshot,
  erasing the playback it had just started: nothing sounded, the action reported `ok: True`, and the live
  store still held `yt: {}` as the evidence (the write landed 0.6 s after the action — too fast for the
  resolutions the clobber then discarded). The V2-611 class again: a stale snapshot is never written back
  over a store a collaborator writes to. A non-local first track now gets NO db (the connector owns the
  store during play/queue) and the final persist runs on a fresh load; a local first track keeps the old
  single-writer flow. **(2)** The operator then ordered the play THREE times («Vale, pues reproduce la
  lista», «Vamos, dale al play, a la primera canción») and the data-op dedupe guard (V2-038) ate every
  one as context-bleed: its only escape measures word overlap against the PAYLOAD, and no natural play
  order names `{"playlist": "true-blue"}` — one turn even ended with `completion_chars=0` over his
  explicit command. New `canvas_license.replay_license` (V2-635 doctrine — declared data + grammar, never
  intent): an identical re-emission passes the dedupe only when the action is one the widget DECLARES as
  starting production (`runtime.produce` — agenda-class ops declare none, so the founding dentist
  duplicate stays dead) AND the turn carries a conjugated media request. Verified against the session's
  own four turns: exactly the two real orders pass, the two drag turns stay deduped. Node **4.148**;
  three disarms, mutations asserted, all red. ⚠️ The V2-531 lesson was paid AGAIN mid-build: a
  `git checkout` after a disarm restored HEAD and silently wiped the uncommitted fix in all three files —
  re-apply the edit or commit BEFORE disarming, never checkout over uncommitted work. Open, named in the
  initiative: the same session's «¿Qué tiempo va a hacer hoy en Soria?» (and the complaint after it) was
  classified `llm_ambient` in `always` mode and never answered — an attention-gate classifier miss, not
  touched here; Flash's invented album gloss in the escalation brief and the errand title frozen on
  «Blue» after the worker confirmed «True Blue» (the V2-644 title class, for widget-surface errands).

- **A REPORT is delivered as a DOCUMENT — the `informe` surface (V2-644, 2026-09-09)**: the operator's
  order after the Juncal research (session adc8a7c7, read event by event before touching anything): a report
  errand must open «el visor simple» — a process tab while the work runs, then ONE white-paper document —
  never the results sheet, whose card list «queda un poco ridículo» for a report. What the forensics showed:
  STT heard «la empresa junca de ella Salvador SL» (= Juncadella Salvador SL, the operator's own surname),
  Flash guessed «Juncal de El Salvador» and the errand title froze on the guess even after the worker
  CONFIRMED the real name and NIF (21:14:30); the surface was `lista`, so the browser's page-extract pushed
  einforma's own trust badges («Cero CO2», «Confianza Online», «Tarifas») into Resultados as findings; the
  worker sent its web_search query under a key the bridge did not read, got a SILENT
  `{"results": [], "source": "none"}` twice, concluded «el puente no devuelve nada» and drove the browser
  for four minutes; and the report never landed anywhere (cancelled by a restart). Four changes:
  **(1)** a SIXTH surface value `informe` (`surfaces.DOC`, aliases informe/documento/report/dossier;
  offered in the escalation tool's enum — the shared catalog ceiling was paid by compacting, ending UNDER
  the old 23_100). Deliberately NOT in `SHEET`: every `opens_sheet` caller branches, so a report errand
  never rides the results-sheet path. **(2)** commission opens the `documento` widget bound to the task
  (`nucleo/docsheet.py`: doc_open/doc_retitle/doc_close — the sheet's own three gestures, sibling module),
  criteria seeding is guarded off, `sheet_for_delivery` skips doc-surface errands (the badge-junk path),
  and the worker prompt gains `DOC_SURFACE_BLOCK`: deliver via `documento` (4d), results is NOT open, first
  `show` early + `append` per section, say «Elaborando el informe…» before writing, and the document title
  carries the TRUE confirmed name — not the errand's phonetic guess. **(3)** the widget grows a live
  process view: `view_data().process` derived per read from the new `dispatch.task_progress(tid)`
  (`sheets.task_progress`, task-keyed sibling of `sheet_progress`), persisted at finish; Proceso|Documento
  tabs only when a process exists, and the document is PAPER — a white page whatever the host theme.
  **(4)** the `use_tool web_search` gate refuses an EMPTY query loudly naming the exact form, and accepts
  the sibling keys (`q`/`text`/`search`/`consulta`) a worker actually writes. Node **4.143** (17 headless +
  4 bridge + 6 rendered cases); seven disarms, mutations asserted, all red — TWO came back green first and
  the TESTS were wrong: nothing measured the finished-empty default tab (the alive safety net covered the
  mutation), and the bare harness defined no theme vars, so `var(--hb-bg,#fff)` resolved white and a
  regression to theme-following was invisible — the fixture now mounts a hostile dark host theme.
  ⚠️ NOT verified live end-to-end: a real informe errand needs a worker run; the engine restart +
  served-code checks are the shipped verification. Detail: the V2-644 initiative.

- **The orb answers ONE question, and a stopped mic is crossed out (V2-648, 2026-09-10)**: three things
  were painting on the same surface and nobody had reconciled them since the orb's colour became the
  LISTENING signal (2026-09-09). **(A)** The claim ignored the microphone: `_listeningNow()` read powerOff +
  attention mode, so a muted mic left the orb glowing «te escucho» over a shut input. The rule moved out of
  the draw loop into `services/listening.js` (dependency-free, so the test drives it and not a copy) and
  now reads `agentLive()` → mic → mode, in that order; an unreadable store answers NO, because a false grey
  is a nuisance and a false orange is the reported bug. **(B)** `canvas#orb.muted{opacity:.5;grayscale(.45)}`
  predated the signal and desaturated the orange into a dull brown whenever he silenced zaelar's voice —
  «el altavoz no tiene ningún efecto sobre el color del orbe». Rule and class deleted; what they carried
  MOVED to the 🔊 control beside it, which already paints itself crossed and grey. `frozen` stays. **(C)**
  Grey alone was saying «mic off», and grey is also what a disabled control looks like: `MIC_OFF` now adds a
  slash (the speaker's own off-face language), and the lit state gained a halo + heavier stroke so ON reads
  as LIT, without dimming OFF further — the muted mic must stay legible, its slash IS the message. The VU
  meter's RESTING floor went .72 → .88 in the same pass: a live, unmuted mic between words sat closer to a
  disabled control than to a lit one, which is why the icon he singled out was the one that read wrong. Nodes
  **4.146** (e2e: the slash measured by its RENDERED ink, both swap directions, ON-vs-OFF weight through the
  real cascade, and the orb's painting identical either side of a speaker click) and **4.147** (unit: the
  real `isListening`). Three disarms red. Detail: the V2-648 initiative.

- **The room is not the operator (V2-647, 2026-09-09)**: «todo lo que voy diciendo en mi conversación en la
  sala está siendo captado y transcrito en el chat». The GATE was never wrong — every line of that
  conversation was correctly judged `ambient` and answered with silence, and the grey orb correctly meant
  «hearing, not attending». The FRONTEND was wrong, twice: the gate's verdict travels as its own event and
  arrives just AFTER the transcript, so `sse.js` painted every user transcript into the wall and learned the
  verdict second — and never unlearned; and that same ungated transcript drove `handleWidgetVoice`, so room
  speech carrying «cierra» could close his widgets — V2-015's premise bypassed by a client-side shortcut
  older than it. `services/attention_hold.js` now HOLDS a spoken turn until the gate rules: directed →
  released whole (wall + canvas, `isFinal` intact), ambient → the turns that verdict COVERS are dropped,
  uncovered fragments keep waiting for their own ruling. It FAILS OPEN (no verdict in 2.5 s → release:
  showing an ambient line is a nuisance, swallowing a real one is the bug) and holds nothing in `always`
  mode; typed text bypasses it, directed by construction. Node **4.145**, six groups against the REAL module
  (not a copy of its logic), three disarms red. ⚠️ Two traps paid: `node --check` said OK on an sse.js with a
  stray `}` (the ES-module trap — the browser boot is the real gate and caught it), and `wallpaper_clear`
  wrote to the store with nothing to clear, which made a contract test that calls every declared action touch
  the suite's real settings file. Clearing nothing writes nothing.
- **A typed message is never lost (V2-646, 2026-09-09)**: two defects, one promise. **(A)** With ⏻ OFF the
  composer swallowed messages: `sendText` queues the text and calls `start()`, whose own gate against the
  server's truth refuses — so the queue never flushed, while the wall showed «sent» and `send()` had already
  cleared the box («la primera lo ha mandado al vacío… he tenido que escribir dos veces»). `canSend()` =
  `agentState() !== "off"` now gates the button (disabled + a dead style + a title saying why) AND `send()`
  itself, because Enter bypasses a button's `disabled`; `starting` stays open (there the queue does flush).
  **(B)** Measured 22:30:39: a TYPED «puedes ponermela en youtube o de alguna forma?» spent its 51 tokens on
  a `play_video` the canvas license vetoed as context-bleed, `deduped` marked the turn handled, and the mute
  backstop stayed quiet — `completion_chars: 0`, a written question answered with nothing. The V2-633/634
  silence exemptions are for AMBIENT room speech; a sentence somebody sat down and WROTE can never be that.
  New fact `attention.note_typed()/was_typed()` (stamped by the chat/paste handler beside `note_directed()`),
  and on a typed turn a vetoed/deduped action stops counting as «handled». V2-634's source guard was narrowed
  by exactly one state, with the reason in the assertion — a deduped duplicate still counts on SPOKEN turns.
  Node **4.144**; four disarms verified red. Left open on purpose: the license refused «ponermela» because the
  request is ANAPHORIC (it points at «la peli de minions» from earlier), which is a licensing-vocabulary
  decision, not a silence bug.
- **A cover never ends the turn, and covers describe MOTION (V2-642, 2026-09-09)**: session 651c25ac,
  20:51:49 — «¿Por qué la vista semanal no tiene una columna para cada día?» → «Déjame que mire…» → a reply
  with `completion_tokens=84` but `completion_chars=0` (the model spent the turn re-emitting a stale data-op
  the context-bleed guard rightly ignored) → silence forever. The operator's rule: «igual no tenía
  respuesta, pero igualmente hay que cerrar las conversaciones». Four changes. **(1)** third hollow-turn
  guard `a_cover_left_hanging` (mute completion after a sounded cover, or over an information question —
  but an uncovered mute STATEMENT stays legitimate silence, V2-633) + `mute_cover_repair` composes the
  missing answer; failing even that, `langs.pick_closer()` speaks the honest deterministic closer («pues
  ahora mismo no tengo una buena respuesta a eso») — the turn ALWAYS closes. **(2)** the three repairs
  (V2-572 bare ack · V-587 empty wait · this) consolidated in `second_pass.hollow_repairs` — ONE seam,
  called by the voice channel with `covered = filler fired after this turn's stream began` (monotonic
  stamp); the extraction also paid nucleo.py's ceiling (3024/3043). **(3)** the filler pools follow
  OpenAI's realtime prompting doctrine, which the operator pointed at: a cover DESCRIBES THE ACTION («Voy
  a mirarlo…», «Te lo compruebo…»), never a bare thinking sound — their explicit avoid-list («Hmm…», «Let
  me think…», «One moment while I process…») was literally our old pool, and a source-level test bans
  those exact phrases from returning. **(4)** a DANGLING fragment arms NO cover («Ahora quiero» got «A ver
  qué tenemos…» at 20:51:26 — half a sentence gets no promise; suppression needs POSITIVE evidence, an
  empty text still arms). Tests ride existing nodes 3.19 + the mouth file; three disarms verified red
  (the first mute-guard disarm came back GREEN — both branches caught the case — and was replaced by the
  real one: «empty reply never repairs», the pre-fix world).
- **The desktop wallpaper is a SPOKEN property (V2-641, 2026-09-09)**: the operator's spec — «igual que
  podemos con la voz colocar widgets o pasar el orbe a la barra, quiero poder poner una imagen de fondo…
  la buscaremos con el sistema y le diré usa la número 3». The flow: `show_images` finds photos (with
  «fondo» in the query, `image_turn._WALLPAPER_INTENT_RE` prefers ≥1600px files and sorts by area — there
  are 2900x1440 monitors behind this), the viewer shows them, and `imagenes`'s new `wallpaper` action
  (item resolved exactly like `select`; no item = the one on screen) persists it. Persistence is the
  V2-617 two-layer seam: `config/settings.py` (with `_sanitize_wallpaper` — the URL is echoed into a CSS
  `url("…")` on every client, so the sanitizer is a SECURITY seam: http(s) only, no quote/backslash/space,
  else {}), plus localStorage for instant paint; the live push rides the widget event channel
  (`emit("widget","wallpaper")` → sse.js → `theme.setWallpaper`, persist:false to avoid the echo loop).
  CSS: `body.hb-wallpaper .canvas` paints the photo under a `--canvas`-colored ::after scrim (.38) so
  widgets stay legible over any photo in either theme. The tool CATALOG deliberately carries no line —
  it sits 3 chars under its per-turn ceiling; the manifest brief (costs prompt only with the widget on
  screen, V2-526) teaches the action instead. Node **4.141** (e2e paints a fresh browser from the mocked
  account settings + sanitizer unit); disarm of the CSS rule verified red.
- **Covers that LISTEN, and the presence fast lane (V2-640, 2026-09-09)**: the 19:27 testing session
  (sid 1674ee35) became a «diálogo de besugos» measured turn by turn: every meta-question («¿qué quieres
  ver?», «¿a qué tengo que esperar?») armed a THINKING filler («Déjame ver…»), which read as an answer
  promising to look at something, which spawned the next meta-question — while the real replies (3-5 s
  TTFT on deepseek via aimlapi) died to barge-ins. Four changes: **(1)** `filler_kind` gains a SOCIAL
  class (`_SOCIAL_RE`: presence checks, greetings, questions about the conversation itself) with its own
  explanation-opener pool («Pues…», «Verás…») — a thinking sound may never again answer a question about
  us. **(2)** pools grew (20 neutral es / 9 action / 6 social, en likewise) and `pick_filler`'s
  anti-repetition is now a recent WINDOW (depth 4), not depth-1 — the operator heard «A ver…» twice in
  three turns. **(3)** the cover is chosen at ARM time and `filler_audio.arm(messages=…)` appends a
  [SISTEMA] note with the exact phrase to the turn's last user message (local list only — the V2-536
  stable prefix never changes), so the reply CONTINUES the muletilla instead of colliding with it; fire
  time speaks the promised phrase. **(4)** «¿sigues ahí?» never reaches a model: `nucleo/flash/presence.py`
  holds the ONE detector (whole-utterance, ≤7 words, vocative-stripped; a knock with cargo falls through),
  `fast_lane.presence` answers instantly from the idle/busy pools and the exchange still lands in the
  window + conv buffer (the V2-605 canned-line lesson), `probe.py` mirrors it via `_presence.mirror`
  (parallel impl). Plus the prompt now says the model's UI capabilities are EXACTLY the declared surface
  (canvas tags + widget actions) — the wallpaper turn showed it narrating past a capability that did not
  exist. Node **3.24**; two disarms (social branch, arm note) verified red.
- **The agent gets its OWN filesystem, and the torrent client becomes a SYSTEM tool (V2-638, 2026-09-09)**:
  the operator's reframing of V2-637, the day after it shipped. What a widget downloads is **not that
  widget's property**: a paper for `documento`, a track, a film — it all belongs in a tree the AGENT owns,
  structured, reachable by every widget, present by default on a cloud Machine. Nine requirements, and the
  design falls out of the first: **one root, a folder per kind, layout from GENESIS and overridable by him.**
  - **`library/`** (new module, declared in `cluster.yaml`): `paths.py` — the layout read from
    `nucleo/genesis.json` with per-install overrides in `<workspace>/config/library.json`, mtime-cached
    exactly like V2-633's style policy, plus `resolve()`, the SINGLE door. That door is a security seam, not
    a convenience: every path arriving here comes from a magnet payload, model output or a query string, so
    absolutes are REFUSED (never silently reinterpreted — stripping the leading slash maps `/etc/passwd` to
    a plausible in-library path and hides the caller's real intent), `..` is refused, and the check is made
    against the RESOLVED path, which is the only version that catches a symlink planted inside the library.
    A renamed folder is one segment, so a rename can never relocate the tree. `formats.py` separates what a
    file IS from whether the BROWSER can play it; `index.py` is the normalized record a widget consumes
    (`url`/`playable`/`kind`/`size`) and files a finished download onto its shelf; `server_api.py` serves
    `/api/library/*` including the ONE stream route both players share.
  - **The download policy is his**: by default only bring home what the page can play, with `keep` as the
    explicit escape for «lo quiero para el pendrive» — and an unplayable file is still offered through
    `/download`, because refusing without a way round is how a legitimate file looks broken. This corrected
    a REAL defect shipped the day before: V2-637 listed `.mkv`/`.avi` as playable video. No mainstream
    browser decodes either, so the client could pick a file it was structurally unable to show.
  - **The torrent client is now a system tool**: it writes ONLY into `library/downloads/` (his isolation
    rule) and never needs a path outside it — filing is our move, afterwards; `want` picks the shelf the
    caller came for, so the same client serves video, music and documents; a refusal NAMES the file it
    declined and offers the way round; and it has an operator SWITCH (`config/connectors.json`, default ON —
    it is the one connector that can saturate a line). **Second real defect found**: `connectors.enabled()`
    consulted the store and an env var but never the declared `_DEFAULTS`, so any connector shipped ON
    answered False on a fresh install. It hid because all four pre-existing connectors default to False.
  - **The video player stops being YouTube-only** (his requirement that the player hold the torrent tool
    directly — a film is watched there, so the download that produces it belongs to the same surface): a new
    `widgets/youtube/sources.py` owns where a row comes from — `youtube` → the embed, `local`/`torrent` → a
    plain `<video src>` against our own routes (the library one, or the piece-aware one while it still
    fills). Extracted rather than added because `data.py` sat EXACTLY on the 900-line newborn ceiling, so it
    ends net negative (899→896). The control funnel learned the second vocabulary: `post()` translates the
    IFrame API's verbs into media-element operations, so all five control sites work unchanged instead of
    growing a parallel copy. **Two latent defects closed BEFORE any non-YouTube row could exist**:
    `blocked_ids` keyed the blocklist on `videoId` and every such row carries `""` — one blocked local file
    would have put `""` in the set, which the queue filter reads as «matches everything», silently skipping
    every local item forever; and `swap_to` located the playing row by `videoId`, so two local rows both
    resolved to the first. A streaming row is also no longer given an invented `youtube.com/watch` URL.
  - **The music widget gets its third source** and, with it, MIXED playlists — needing **no new schema**:
    the track shape already carries `uri` and YouTube-audio already uses a scheme there (`yt:<id>`), so a
    local track is just `uri = "local:<rel>"` and playlists, Recent, Top and dedup keep working untouched.
    `local_audio.play` clears the `yt` block (the bar shows ONE thing) and bumps a `seq`, because asking for
    the same file twice must be two events and not one silent no-op. Two things deliberately NOT done
    because they fail silently: a local track is never queued into the connector (that queue holds query
    STRINGS it re-resolves, so a file would be dropped), and a filename with no « - » never invents an
    artist (a wrong credit propagates into Recent, Top and every playlist that holds the track).
  - Nodes **7.42** (19 cases), **4.139** (10 RENDERED + 14 unit) and **4.3** (+13); twelve disarms, every
    mutation asserted, all red. ⚠️ The V2-554 Dockerfile guard caught the missing `COPY library` before it
    could break a cloud boot — `server/__init__.py` imports it at module level. **NOT verified live**: the
    engine was not restarted, so none of the three surfaces has been driven by hand.
  - ⚠️ **Concurrency incident worth keeping**: three sessions were editing `tests/run_testmap.py`. To keep a
    peer's staged hunk out of my commit I rebuilt the file as HEAD + my hunk — and in that window the peer
    committed, so their node was lost and HEAD went red with two test files outside the map. Restored in
    `2b9ba75`. Rebuilding a shared file from HEAD to isolate one hunk is only safe if nobody commits in that
    window, which a session cannot know.

- **The agenda looks like a CALENDAR — the shapes everybody already knows (V2-643, 2026-09-09)**: the
  operator's redesign order with two screenshots of the week view. Measured before touching anything: the
  card declared NO `manifest.size`, so it opened at the default 400×340 tile — literally «se muestra muy
  pequeño, se cortan las palabras de abajo», the same class as V2-630 (musica) and V2-597 (youtube); the
  «week» was a list of the seven horizon days, one per row, with the per-day tabs (Hoy · Mañana · vie · sáb
  · dom · lun · mar) that are exactly the cramped buttons he was complaining about; and the calendar
  connectors were three 15px icons in the header that dropped an explanatory paragraph over the content —
  «los iconos son tan pequeños y están apelmazados que no se sabe qué significa ninguno» plus «un texto ahí
  que me parece absurdo como descripción». Now: a toolbar (brand · range · ‹ Hoy ›), a defined view band
  whose active view is an INVERTED chip (the V2-636 language), and the four classic views — **Día** (hour
  grid beside the coach rail this widget has always had), **Semana** (seven Mon–Sun COLUMNS over the grid,
  each day's items inside its own column, overlapping meetings packed SIDE BY SIDE because a calendar that
  hides an appointment is the worst thing this widget can do), **Mes** (navigable 7×N grid) and **Lista**
  (the Schedule view). His «varios colores, varias intensidades» is two axes, both DERIVED FROM DATA and
  never from sniffing a title (V2-095): the HUE comes from the dictated `category` or the planner's own
  block kind, the INTENSITY from how settled it is — a confirmed appointment is solid, one the other side
  has not answered is dashed (the convention every calendar already uses), a planner-placed task block is
  soft. Badges carry the rest of his spec: a bell when a reminder exists, 👥N for attendees. So the data
  model grew what a calendar entry actually is — `attendees` (names or a bare count: «somos cuatro» is four
  seats), `status`, `location`, `category`, `allDay` — with `update_meeting` as the single door for editing
  them (it touches ONLY the keys the payload names) and one default that matters: a meeting WITH people is
  born `pending` and one without is `confirmed`, because you invite people and then wait. ⚠️ Two bugs the
  tests caught, both mine: «sigue pendiente» read as CONFIRMED because «si» lives inside «sigue» (word
  boundaries now, and `_PENDING_RE` runs FIRST because «sin confirmar» contains the confirm stem — a disarm
  that stayed green proved nothing measured that negated case, which is what decides the order); and an
  all-day entry CRASHED the whole day plan, because `planner.plan_day` read `mt["startTime"]` on a meeting
  that by definition has none. The card FILLS its frame (`:has` on `.hb-scroll`, V2-636) with the grid
  scrolling inside, so nothing is clipped at any size; `manifest.size` 920×640. Node **4.142** (17 RENDERED
  cases — seven columns, a chip landing at its hour's pixel, two meetings not covering each other, the real
  card chrome for the clipping cases per the V2-608 fixture lesson), V2-540's render test rewritten to the
  new DOM with every behavioural claim intact, and the XSS fixture repointed at the surface that now
  renders. Ten disarms, mutations asserted, all red. ⚠️ Renumbered TWICE at closure (640 → 642 → 643): the
  concurrent session had already pushed V2-640/641/642 into this log — what is pushed wins, and the cheap
  thing to move is the batch that is not committed yet. Detail: the V2-643 initiative.

- **The agenda answers to the voice: the view alias, the missing vocabulary, the visible details, and the
  operator's language (V2-639, 2026-09-09)**: the operator's session, read event by event — he asked FOUR
  times for the month view and the widget landed on today every time, silently. The model had done its job
  (`show_day {view: 'month'}`) and `apply_action` only read `day`/`date`: the V2-341 class again — the
  model's natural alias must not cost the fact. `show_day` reads `day|date|view|mode|vista` now. Three
  intentions had NO vocabulary at all (the clear_all lesson): `move_meeting` (find like cancel_meeting,
  the end keeps the meeting's DURATION, and the reminder MOVES with it — an alarm for the old day fires a
  ghost, V2-473), `set_reminder` with a date and no title reaches EVERY meeting of that day («avisos para
  todas las citas del jueves» is one intention, not N turns), and `add_task` (a task is not a fake
  appointment with an invented hour; same no-inventing write discipline as add_meeting). The appointment's
  SUBSTANCE travels in `notes` now, and `prompt_digest()` (the V2-544/V2-576 seam) hands the brain the
  upcoming meetings — date · hour · title · reminder · notes — so «qué es ese punto del dentista» stops
  being a guess: `coach_context` only ever carried TODAY, so every meeting beyond it was invisible and the
  model narrated. `ref_index` exposes future meetings and the manifest declares `ref: "title"` on the three
  meeting actions (V2-595), so a spoken reference resolves. The whole surface is multilingual now:
  `_resolve_date`/`_resolve_time` hear English, the planner's INVENTED labels (Lunch/Break/overflow/
  avoidance) follow a `lang` argument — dictated titles pass through untouched, they are data — and
  `widget.js` dresses through `ctx.t`/`Intl.DateTimeFormat(ctx.lang)` (V2-613; `widgets.agenda.*` in both
  bundles, i18n manifest 5→6). Seed packs v7 carry the operator's literal live sentence («muéstrame la
  agenda con vista mensual») and the day/view grid into the deterministic lane. Node **4.140** (19 + 6
  RENDERED cases); six disarms, mutations asserted, all red. Detail: the V2-639 initiative.

- **A canvas mutation needs the operator's words — and a known order survives the wake word (V2-635,
  2026-09-09)**: one live session (34386d8f) measured four classes of the same failure, the model dragging
  its PREVIOUS tool call into a turn that licensed nothing: «Johnny pausa el vídeo» became fullscreen (the
  verbatim «pausa el video» seed missed because the phrase carried the agent's name — the map's exact
  whole-utterance lookup was dead in wake-word use), «minimiza el vídeo» became fullscreen TWICE (the
  toggle was the model's only route, and on a non-maximized card the toggle does the exact opposite),
  «Johnny eres tonto» and «¿Y por qué lo has quitado?» each CLOSED the widget nobody asked to close (the
  first emptied the loaded video, so «Continúa el vídeo» honestly died with «No hay ningún vídeo»), and
  «Muy bien, señora.» / «¿Pero por qué lo has cambiado otra vez?» each RELOADED the playing video. The
  remedy is grammar, never intent (V2-095), the stop_worker GUARD 2 posture: `nucleo/flash/
  canvas_license.py` (shared, BOTH channels) — `close_license` (looks_like_close: a model [[close]] or a
  widget_data «close» without a close verb in the turn is drag, discarded), `video_license` (conjugated
  request forms only — a participle narrates the past; «otro/otra» only NEXT TO a media noun, because
  «otra vez» in a complaint was the measured false positive; a short bare «Sí» keeps answering the
  model's own offer), and `fullscreen_license` (no screen-size words = drag, discarded; shrink words
  route to the new first-class `minimize` canvas order — executor + SSE + `desktop.shrink(id)`: exit
  fullscreen → restore maximize → rail chip — never the toggle backwards). A guarded discard counts as
  HANDLED (`deduped`), so the V2-633 silence never falls into the mute apology. And the fast lane retries
  its lookup with the leading VOCATIVE stripped (`attention.strip_leading_wakeword` +
  `actionmap.match_spoken`, both channels): only the known wake words come off — normalize.py's
  no-courtesy-stripping doctrine stands. Seed packs v6 add the session's missing phrases (minimiza /
  pantalla completa / cierra el vídeo, es+en). The provider ratchet was paid by extracting the play_video
  and fullscreen_widget branch BODIES into `video_turn.voice_execute` / `show_target.fullscreen_dispatch`
  (where the licenses live once for both channels). Node **3.23** (16 cases); eight disarms, mutations
  asserted, all red. Detail: the V2-635 initiative.

- **The video widget dresses like the product (V2-636, 2026-09-09)**: the operator's redesign order with
  his screenshot — he grew the card with the mouse and the control buttons were CLIPPED under its bottom
  edge; the tabs read as a second title line; title and date burned two rows; the controls were text
  buttons («no sé si es necesario el texto Play en un botón de play»). Now: the PLAYER tab is a flex
  column that FILLS the card (`:has` on the real card chrome — `.hb-scroll` overflow hidden, root
  height 100% — the frame takes every spare pixel and YouTube letterboxes inside the iframe, so the icon
  bar below is pinned and visible at ANY card size; every other tab keeps its scroll); the tab strip is a
  DEFINED band (bottom border, nowrap) behind a red brand mark, with the active tab an INVERTED chip
  (ink↔bg — the operator's «color de fondo y el texto invertido», which is also YouTube's own dark-mode
  chip); title left + channel·date right on ONE line (`.hb-yt-tline`); the controls are SVG icon buttons
  (⏮ ▶/⏸ ⏭ · vol−/vol+ · mute) in the music widget's `.hb-mus2-cbtn` language — local copies per V2-557 —
  with the main play/pause a red round toggle whose face says what a click will DO, and the volume
  readout as the bar's only text («70%», «—» muted); playing markers wear #f03; the voice hint only
  teaches over an EMPTY player. Node 4.4 (+1 file, 10 RENDERED cases — the clipping case mounts the REAL
  card structure per the V2-608 fixture lesson). Frontend-only: a page reload picks it up. Detail: the
  V2-636 initiative.

- **An embedded torrent client, so a magnet becomes a video playing INSIDE the agent (V2-637, 2026-09-09)**:
  the operator asked whether Zaelar could carry its own torrent client as an add-on — the mesh already has a
  search agent that returns a magnet, and he wanted the other half: find the movie AND play it in the agent,
  the same promise as the embedded browser, working on cloud and self-host, «part of our code package, nothing
  installed on the system». Measured before designing anything: `libtorrent` (the qBittorrent core) installs
  as a pure-Python wheel (2.1.1, py3.12) with zero system deps, and a public-domain magnet resolved its
  torrent metadata over the real network in ~4 s. So it ships in `requirements.txt` and the whole feature is
  in-package. `connectors/torrent/` mirrors the `connectors/video` family shape: `session.py` is the ONLY
  file that imports libtorrent (a LAZY process singleton — built on first use, never in the ASGI lifespan,
  which runs twice), `search.py` gets the magnet through `mesh_agents.serve` (free agents only, a 402 is a
  fact never paid, «nobody does this» is a spoken reason — the search itself is a network agent, not ours),
  `service.py` is the fail-safe facade whose `available()` is DERIVED from the wheel importing (V2-603 rule —
  a machine without it hides the connector, never shows-and-breaks), and `server_api.py` serves
  `/api/torrent/*`. The one hard part is streaming a file that is still DOWNLOADING: `FileResponse` stats once
  and is useless, so `stream` hand-rolls a `206` — parses `Range:`, reports `Content-Range` against the FULL
  size a `<video>` needs to seek, and streams through `session.iter_range`, which reads from DISK (a completed
  piece is checked and flushed there by default storage) after prioritizing (`set_piece_deadline`) and
  awaiting (`have_piece`) the pieces it is about to serve; sequential download + a per-file priority delivers
  the front first, so «play while it downloads» works. A chunk that never arrives raises and CLOSES the stream
  (a browser re-requests a Range better than it survives a hung socket). The `torrent` widget (`Descargas`)
  builds its `<video>` ONCE and only updates it on re-render (the V2-124/4.19 rule), showing the player only
  when `streamable` (metadata + first ~4 MB down), progress until then — its declared actions ARE the skills
  (V2-544), driven by the generic `widget_data` tool. **The FlashBrain model-tool wiring (a dedicated
  `stream_torrent` in the 5-file router core) was DEFERRED on purpose** — the V2-561 precedent: a
  self-contained feature does not also touch the sensitive, well-tested tool-routing core in the same commit;
  the agent already operates it through `widget_data` like `documento`/`archivos`. Node **5.22** (16 cases,
  three disarms verified red — the stream_url gate, the search-miss-must-not-download guard, the Range clamp);
  `make test-widgets` 15/15, connectors unit 299 green. Data lands under `widgets/_data/` (a declared
  workspace root). **NOT verified live end-to-end**: the metadata path is proven, the byte streaming of a real
  payload is not exercised in the suite (a unit test opens no session, reaches no network). Detail:
  `.meshkore/docs/modules/zaelar-torrent-addon.md`.

- **An unplayable video is swapped, not served — and the silent turn must not apologize (V2-634,
  2026-09-09)**: the operator, with LaLiga's «Video unavailable» on the card. We use the NATIVE YouTube
  IFrame embed, so embedding restrictions are per-video, set by the rights holder — the video plays on
  youtube.com and refuses every embed. The widget HAD reported it (`player_error`, one second after the
  load) and nothing consumed the report. His rule, now mechanism (`widgets/youtube/availability.py`,
  extracted paying the newborn ceiling — data.py sits at 900 exactly): a fatal code (101/150 embed
  disabled, 100 removed, 2/5 broken) puts the video on a BLOCKLIST no search or swap ever re-offers, and
  **provenance decides the rest** — a video WE resolved (query, search band, queue) is silently swapped
  for the next playable candidate (queue after pos → search band → the stored `last_query` re-resolved
  through the injected `_search_id`), while a link HE pasted gets the honest copyright message EVERY time
  («swapping what he explicitly asked for would be a different lie»). The onError report now names its
  `videoId`, so a late report for an already-replaced video never blames the successor. The card SAYS it
  (`.hb-yt-blockmsg`, via the V2-613 `ctx.t` seam, keys in both bundles, interpolated fallback) and the
  brain is told through `prompt_digest` (AVISO DEL REPRODUCTOR + the forbidden moves). **The same session
  also measured a one-hour-old V2-633 regression**: the model understood «ponme un vídeo de Ronaldinho»
  every time and called the tool every time — but with the ack gated, an acted-but-silent turn fell into
  the MUTE backstop and APOLOGIZED («se me ha ido» ×3) over turns that had worked, reading as
  not-understanding; and the context-bleed guard's correct swallows left those turns looking void. The
  backstop is gated on `_tool_handled` (hoisted above it) and a dedupe now marks the turn as handled.
  Node 4.4 (+11 cases) · 4.138 (+1 rendered) · 3.22 (+1); seven disarms red, one repeated against the
  MOVED code after the extraction. Detail: the V2-634 initiative.

- **The genesis rules govern the engine's OWN mouths — a short order runs in silence, and a spoken rule
  rules the very next turn (V2-633, 2026-09-09)**: the operator's session (6c715232) proved the style
  mechanism worked and still failed him: his rule («al recibir órdenes no responder nada») was captured and
  persisted by `set_style_directive` at 16:40:41 — and «Reproduce el vídeo» still got «Déjame ver…» +
  «Hecho.», twice, after the model had agreed. Cause: THREE mouths speak without the model and none
  consulted any rule — the fast lane's ack (V2-572, born from his own earlier opposite order), the
  never-mute backstops (the model OBEYED and said nothing; the engine injected «Hecho.» into its mouth),
  and the lead-in filler (whose `filler_kind` did not even know «reproduce» as an action verb). Now:
  `nucleo/genesis.json` ships the base rules (silent short orders; fillers "smart" — never covering a turn
  that is itself a short order), `nucleo/style_policy.py` layers per-install overrides written by the
  directive handler IN the same turn (`<workspace>/config/style.json`, mtime-cached read per use — a rule
  given by voice or chat governs the next utterance, and survives restarts; retraction restores genesis),
  and all three mouths consult it: the fast-lane ack is opt-in («confírmame las órdenes» brings it back),
  the data-op/show backstops gate on `_ack_allowed` (clarify/confirm stay never-mute — they are questions,
  not confirmations), and the filler checks `filler_allowed(kind)` at fire time. VOICE mouths only, stated
  in the module: chat keeps its text acks (an empty chat bubble looks broken; a written «Hecho.» interrupts
  nobody) — which is also why the probe's ack faces are untouched while a chat-given rule still moves the
  flags. `prompt_line()` teaches the MODEL's own mouth the same manners, only while the policy says silent.
  The missing seeds shipped too: «reproduce el video»/«dale al play»/… → youtube play (es+en, packs v5) —
  the session's exact phrase resolves in the deterministic lane now, like «pausa» always did. The ratchet
  fired twice and was paid by extracting `nucleo/flash/style_directive.py` — the WHOLE set_style_directive
  path for both channels (`handle`/`handle_probe`) plus `prompt_lines()` (wake-word + silent-orders: the
  tool's teaching and its handler in one place); wiring guards repointed to the CHANNEL (V2-555). Node
  **3.22** (15 cases, isolated workspace, two disarms red). Detail: the V2-633 initiative.

- **The video widget becomes a real player: tabs, a dashboard that carries the search, and the honest
  shelf of sources (V2-632, 2026-09-09)**: the operator's full redesign, triggered by his screenshot — the
  card opened EMPTY and small («reproduce un vídeo» opened the card before the video existed; V2-630's
  freeze pinned the footprint the missing manifest height produced). What was already built stayed the
  foundation (V2-366 queue · V2-597 account layer · V2-604 library); this pass reorganizes the SURFACE and
  the search's destination:
  · **Top TABS** (Inicio · Reproductor · Cola · Suscripciones · Listas) replace the home↔player toggle.
    `selectTab` is the ONE writer and clears the connectors screen — the V2-626 rule applied at birth
    instead of paid later (this widget's latent copy of that bug was already named in the V2-626 entry).
    A video ARRIVING on an empty card auto-jumps to Reproductor; a disarm proved the tab-close claim had
    to be measured ACROSS a re-render, not at the click (clearing pixels while `_screen` survives
    resurrects the shelf on the first SSE repaint).
  · **The SEARCH lands on the DASHBOARD, never in the queue** (`search_results` — numbered band, replaces
    the previous search; the queue only receives what he sends in): `play_result{item}` /
    `add_results{items:"1,3"|"all"}` / `clear_search` steer it, `prompt_digest()` (V2-576's seam) hands
    the numbered rows to the brain so «reproduce el tercero» resolves against what he SEES.
    `play_video(action=list)`'s whole chain updated (tool text · `video_turn` spoken face with real
    singular/plural · manifest `view:true` per V2-547's lesson) — the shared tool-catalog ceiling tripped
    at +60 chars and was paid by compacting the same description, never raised.
  · **Placeholder** on the player tab («Sin vídeo» title + the 16:9 frame kept and marked), queue rows
    with thumbnails, Suscripciones/Listas as real tabs over V2-604's data, and `follow_channel` with no
    name follows the CURRENT video's author (a required argument the sentence never fills, V2-609 class).
  · **The 🔌 SHELF** (messaging igrid language, local copy per V2-557): every video source with its truth —
    YouTube disabled naming INI-032's reason, Vimeo/Dailymotion/Twitch as shut doors from the V2-526
    catalog (`connector_shelf` composed server-side, fail-soft). A disabled box never fires a connect.
  · **Manifest sizes made honest** for the two width-only declarations the V2-630 freeze exposed:
    youtube 680×560, musica 468×540.
  · Data per the domain-stores doctrine (2026-09-09): everything in the widget's own store, ZERO rows into
    memory; the inferred channel preference is REM/heart's lane. Coordinated over the dev cluster with
    memoria-dev (heads-up + exact key inventory sent for the doctrine's Video section).
  Node **4.138** (9 rendered cases) + 4.4/4.52/4.53/4.116 files realigned to the new faces; golden
  re-recorded (40 keys); seven disarms, mutations asserted, all red after one test was hardened.
  ⚠️ Caught by SCREENSHOT, not by reading: the connmode CSS block sat BEFORE the per-tab rules and lost by
  order at equal specificity — the queue rendered underneath the shelf. Detail: the V2-632 initiative.

- **A card's size never follows its content (V2-630, 2026-09-09)**: the operator, with two screenshots of
  the same musica card at two widths — «el tamaño de los widgets debe ser fijo; si el texto no cabe, se
  acorta; el usuario decidirá si lo hace más grande o más pequeño». Mechanism: `.hb-win` has no width of its
  own (shrink-to-fit), musica declared no `manifest.size`, and the playback bar's nowrap title propagated
  its max-content width into the card — so the card's width was a function of the current song title. Fixed
  at CLASS level in the canvas: `desktop.js::_freezeSize` runs once per fresh card, right after
  `_applyPreferred`, and writes any still-auto dimension as explicit px (snapped, canvas-clamped, floored at
  the widget's `_minSize`; a minimized card and operator-set dimensions are untouched) — from then on
  content truncates or scrolls INSIDE the card, and only the operator's gestures and the canvas's own `_fit`
  change its size. Companions: musica declares `"size":{"w":468}` (deterministic first footprint — the
  freeze alone would pin whatever the current title happened to measure), and `/api/canvas/state`'s
  whitelist keeps `w`/`h` (the server fallback restore silently dropped the size half of «where he left
  it»). Node **4.137**, RENDERED with the real desktop.js and a CONTROL case proving an unfrozen card
  genuinely grows (without it the other cases measure air); two disarms red. Frontend-only: a page reload
  picks it up. Detail: the V2-630 initiative.

- **The free source CAN skip, and a narrated close is not an order (V2-631, 2026-09-09)**: the operator's
  session review (7be94951), each link verified in observability. (1) «Pasa a la siguiente canción» met
  `youtube_audio.py::next()` returning `unsupported` with a canned «Con esta fuente gratis no puedo saltar
  de canción» — spoken three times, twice right after AGREEING with him — while he skipped by hand through
  the very queue `on_ended()` already advances. `next()` now delegates to that same advance (empty queue =
  the honest refusal, naming the queue), `previous()` works off a new bounded `history` and requeues the
  current track at the front, the canned string is DELETED from both language tables, and the skip phrases
  are SEEDED in the action map (es+en) — the deterministic lane pause/resume already had. (2) The musica
  card closed itself TWICE — killing the audio, which lives inside it: `looks_like_close` matched «¿Van a
  cerrar anuncios?» (infinitive, third-person future) and «has cerrado el widget de música» (a complaint
  narrating the FIRST wrongful close) — the second one both fired the close backstop AND made
  `show_contradicts_the_order` discard the `show_widget` the model had correctly called to reopen it: one
  wrong True, three symptoms. Grammar, not intent: `_NARRATED_CLOSE_RE` STRIPS (never vetoes) participles
  after «haber»/«you've» and «va(n) a <infinitivo>» before testing — an imperative beside a narrated close
  still closes. The `action_map` was checked and NOT poisoned (zero learned rows). The ratchet fired on
  `router_guards.py` and was paid by extracting the whole close-order grammar to
  `nucleo/flash/close_guards.py` (AST-identical, re-exported). (3) The source catalog he asked for is the
  honest version: priority already existed (`music/registry._BUILTIN`: connected Spotify first,
  YouTube-audio always) — what was missing was VISIBILITY: `registry._music()` now lists youtube-audio as a
  live always-connected row, and the V2-526 shelf gains the music family (apple-music `planned` with its
  real gate; amazon-music/deezer/soundcloud/tidal/youtube-music `not-possible`, each naming why) — showing
  what we do NOT have on purpose, instead of narrating an Amazon integration that cannot exist. Nodes 5.11
  (+1 file) and the router/actionmap/music suites; six disarms red. NOT verified live (needs an engine
  restart). Detail: the V2-631 initiative.

- **The music widget brings real cover art, fast first, then enhancements (V2-629, 2026-09-09)**: the
  operator asked for a nicer design in "our line" of icons, real album/song art, and a player better than the
  competition — with a hard ordering constraint: music has to SOUND fast, art can arrive after, and whatever
  is fetched gets cached. Two speeds: (1) FREE and instant — a track played through YouTube-audio already has
  a resolved `videoId`, so `connectors/music/youtube_audio.py::_yt_thumb(id)` derives the video's own
  thumbnail URL with zero extra network call of ours; wired into every `Track(...)` and the persisted `yt`
  block. Same fix let `widgets/musica/data.py::_track_from_resolved` store what the PROVIDER resolved (real
  title/artist/art) into Recent/Top instead of the operator's raw spoken words, and `_clean_yt_title`/
  `_yt_display` strip upload boilerplate ("(Official Video)"…) and split an explicit "Artist - Title"
  delimiter for DISPLAY only — the stored title never changes. (2) SLOW and CACHED — a track never actually
  played (typed into a list, a legacy row) gets a lazy, once-per-song iTunes Search API lookup
  (`_enrich_art`/`_itunes_lookup`, free, no key), cached forever on a hit / 14 days on a miss, backfilling
  every occurrence of that song across Recent/Top/every playlist. The widget asks for it AFTER the row is
  already painted with its fallback (`widget.js::maybeEnrich`, deduped per page life, defensively tolerant of
  a `ctx.action` that returns anything other than a Promise) — never on the play path. `art_cache` rides
  along in `_compose` (which `_persist` also uses to write the disk file whole) but is stripped by
  `view_data()` before it crosses the wire, so the cache survives while the payload stays light. Every emoji
  control (⏮⏸▶⏭🔉🔊♥) became an inline SVG matching the app shell's own visual language (duplicated locally —
  `widget.js` cannot import app-shell code, V2-557's rule); the heart is a STATE indicator now
  (`data.fav_current`, filled when the playing track is already saved) and a dead cover URL degrades to the
  placeholder icon via `img.onerror` instead of a broken-image glyph.
  **A real bug the render tests caught, not reading**: `ICON_PLAY`/`ICON_PAUSE` were built as the outline
  base (`fill="none"`) plus an APPENDED `fill="currentColor"` on the same tag — the HTML parser keeps the
  FIRST duplicate attribute, so `fill` stayed `"none"` and the "solid" icons rendered as hairline outlines;
  invisible in a screenshot at icon size, caught only by asserting the resolved attribute. Fixed with a
  second, clean attribute set for solid icons, never an override on top of the outline one. Node 4.3
  (+1 file, 10 RENDERED cases + 4 connector-level), seven disarms, each mutation verified red. Two
  pre-existing tests needed fixing, not weakening: one asserted an empty call list that the new (correct)
  background enrichment now legitimately populates (filtered to exclude `enrich_art`); another's mock
  `ctx.action` returns `undefined`, so `maybeEnrich` was made defensive against any shape, matching the
  `try{...}catch(_){}` caution the same file already takes for `ended`. `make test-widgets` 14/14 (golden
  re-recorded — `fav_current` is a new key). **Coordination, per the operator's explicit split**: a message
  went to `memoria-dev` over the MeshKore dev cluster describing this build and asking about the in-progress
  memory upgrade, to align a FUTURE listening-preference ingestion path — no memory code was touched here;
  that is memory's call, briefed separately. Detail: the V2-629 initiative.

- **⏻ ON took two presses: two right fixes from the same day, racing (V2-627, 2026-09-09)**: the operator
  reported that the first press on a stopped agent «se sombrea un poco pero no arranca». His own observability
  had it — `orb:power on`, `agent:state starting`, `agent:state off`, all in the same second, and a SECOND
  `orb:power on` five seconds later (two consecutive `on` is the proof that `powerOff` had gone back to true).
  Cause: the 2026-08-31 pair. Orb.js was sequenced server-first (`runStart().then(session.start)`), and
  main.js gained an effect that revives the voice when `powerOff` drops from outside this tab — but
  `setPowerOff(false)` runs SYNCHRONOUSLY inside the click, so that effect started a session before
  `POST /api/run/start` was even sent; its ⏻ gate asked the server, was told STOPPED (true for a few more
  ms), aborted and set `powerOff` back to true, and the click's own `start()` then found `starting` still
  true and no-opped. The ordering fix was bypassed, not broken. Fix: a HANDOFF (`store.powerOnAt`) — while a
  ⏻ ON is in flight the click owns the startup and no other road may open a session; the guard lives INSIDE
  `ensureVoice`, so all three of its roads (boot, `pointerdown`, the effect) are covered at once, and the
  gate treats an in-flight ⏻ ON as history too. A TIMESTAMP with a 15 s expiry, never a boolean: a reply that
  never comes must not wedge the voice shut. Counterweight (a regression the fix could have introduced): EVERY
  press drops the handoff before branching and only ON takes it again — ON then OFF inside the window would
  otherwise have let the ON's still-scheduled `then(...)` bring the voice up over an agent just stopped. Two observability changes ship with it — every ⏻ press names
  itself and the state it was pressed in (`[zaelar] ⏻ ON — agent was off`, his request), and **the gate's
  abort stopped being silent** (`console.warn` + `voice:refused` on the server timeline): it is a legitimate
  outcome, but an invisible decision is the expensive kind. Node **4.136** — the handoff state machine is
  exercised by loading the REAL `core/store.js` in Chromium (it depends only on `reactive.js` and
  `localStorage`), the wiring is structural like its neighbour 4.91; six disarms red. Detail: the V2-627
  initiative.

- **Choosing a channel is ONE state transition, not a filter assignment (V2-626, 2026-09-09)**: the operator
  asked for his mail; the email dot lit and the WhatsApp connector screen stayed underneath it. `render()`
  applied a pushed view by assigning `_platFilter` alone, while the body is gated on
  `showChannels = !!_screen || …`, which returns EARLY — so the lens never rendered. The click path had no
  such bug: V2-610 had taught it, INLINE, to clear `_screen`/`_openMail`/`_confirmDisconnect`. That is the
  whole lesson — the behaviour lived in the CALLER, so each new caller had to remember it and the voice path
  never did. Now `selectPlatform(pl)` is the ONLY writer of `_platFilter` and owns the whole transition; the
  header dot, the title and the brain's pushed view all go through it. `connect_focus` resolves AFTER the
  pushed view on purpose: when one payload carries both, the SPECIFIC request (open this connector) survives.
  His framing is the rule to keep: *«toda esa mecánica del widget es mecánica… gestiones de estados. Por lo
  tanto, no puede ser que eso falle»* — and a rule every caller has to remember is not a rule.
  Node **4.135**, RENDERED (source cannot see it: the assignment is identical either way, only the screen on
  top differs), five disarms red. Two of them were green at first and the TEST was wrong, not the code: an
  open mail only yields visibly when the SAME channel is re-asked (otherwise the platform guard hides it),
  and a pending disconnect confirmation only renders back inside that connector's own screen.
  The class, checked in the siblings: `contactos` already clears its detail; `agenda` has no blocking screen;
  **`youtube` has the same latent defect** (`.hb-yt-connmode` hides the player/list/home, `_screen` is
  module-lived, nothing clears it) — unreachable today because INI-032 leaves `accounts_enabled` false, and
  named in the V2-626 initiative so reactivating accounts carries it. Detail: the V2-626 initiative.

- **Messaging pro: fetch on demand, per-platform view criteria, `peek` for analysis, and the autoresponder
  (V2-624, 2026-09-09)**: the operator's directive after driving the widget live (sid `952fcf2f`) and
  hitting two honest refusals — «todas las conversaciones con actividad en las últimas 72 horas» had no
  criterion anywhere, and «¿puedes ir al conector y chupar más mensajes?» had no door. His governing
  constraint: strictly incremental — «respeta lo que ya funciona y añade lo nuevo… no alterar los circuitos
  de memoria». Detail: the V2-624 initiative. Four additive capabilities, zero rewrites:
  - **`fetch_now {platform, since_hours}`** — a platform-wide pull through the connector, the same
    queue→bus round-trip shape as `load_more` (`msg.fetch` topic, per-platform `FetchInbox`). Telegram
    walks its own dialogs (a stale one is SKIPPED, never a reason to stop — Telegram floats PINNED dialogs
    to the head of the list, and an early exit on the first stale one answered 0 over a live account whose
    newest message was 12 minutes old; the walk is bounded by a 60-dialog cap instead, `3627978`. Broadcast
    channels excluded — a feed is not a conversation); email searches IMAP `SINCE` (day-granular — the service trims to the
    hour by each message's own timestamp). Everything lands in the CONVERSATIONS as read scrollback via
    the existing `connector.history` seam, never in triage: pulling the past must not interrupt anybody.
    **WhatsApp refuses honestly, naming what IS possible** (realtime + per-chat `load_more`) — its bridge
    has no bulk door, and offering one that cannot work is worse. `publish_history` gained optional
    `name`/`isGroup` so a thread BORN from a pull is labeled correctly (a group named after whichever
    member spoke first reads as a different conversation); a name a live message already wrote wins.
  - **`show_view {window_h}`** — the per-platform view CRITERION, persisted until changed (his words:
    criteria are per-platform state, not per-utterance; a plain `show_view` keeps it, `0` clears it). With
    one set, that platform's lens lists conversations from the THREAD store with movement in the window —
    «movimiento» includes what he read and what he sent — under a VISIBLE bar (label + ✕ + a «traer del
    conector» button exactly where the transport can serve it). Without one, the lens stays byte-for-byte
    the classic pending view. Activity rows carry no `n` on purpose (they open by identity,
    platform+chatId — a second numbering space colliding with the chat list's would open wrong chats).
  - **`peek {name|limit}`** — a conversation handed WHOLE to the brain (≤40 msgs, per-body and total
    budget, newest win), so the model summarizes/extracts IN the turn: «dame lo relevante del grupo del
    viaje», «la esencia de esos correos». Read-only by construction: the thread store IS the segregated
    data his storage doctrine describes; analysis is a READ of it, never an index into memory — the memory
    circuits (`kind='msg'` short-level ingestion, unchanged) were deliberately not touched.
  - **The autoresponder** — the «Phase 4» `connectors/whatsapp/client.py` has named since INI-014, now
    with its go-ahead. `set_autoresponder {platform|all, text, hours?}` (confirm-gated: it speaks for
    him), decision whole in `autorespond.py` (zero-import, the policy.py placement): NEVER a group, email
    only when `dirigido_a_mi`, hours window with wrap-around («22:00-08:00»), once per chat per 24 h
    against a DURABLE ledger (V2-607: an in-memory guard cannot dedupe a durable source). The send rides
    the EXISTING `msg.reply` seam — each connector's tested send path, echoed into the thread by the
    existing outbound-capture seams; the original item is NOT marked read: an automatic «estoy fuera» does
    not deal with the message. State is VISIBLE (settings panel chip + a brief line for the brain — an
    undeclared capability is one the model narrates, V2-540) and **survives a Reset** (`blank()` preserves
    `autoresponder`/`lens_criteria`: config is not «messages and queues»).
  - The architecture ratchet fired on `data.py` (1184 > 900) and was paid by EXTRACTING `views.py` (the
    read side: name resolution, thread/activity views, peek, previews, `_group_chats`) — one-directional
    seam, lazy back-imports, 892/313 after. ⚠️ One disarm came back GREEN on its first anchor: the
    mutation hit the `answer_action` PREVIEW instead of the `apply_action` branch — the same code shape
    exists twice (preview computes what the owner will persist), so a disarm must anchor on something
    unique to the function it claims to disarm (the V2-571 lesson, paid again).
  - Nodes **4.134** (4 files: criteria/fetch/peek/autoresponder + the RENDERED activity lens) and
    **5.20** (the two connector fetch drains, faked at the transport). Six disarms red. Sweeps:
    mensajería+connectors 445, infrastructure 648, `make test-widgets` 14/14.

### Archived decisions — index (full text: `.meshkore/docs/decisions-archive.md`)

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
