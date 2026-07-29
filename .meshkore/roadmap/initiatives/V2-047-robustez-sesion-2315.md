# V2-047 — Robustez del cerebro: informe de la sesión 23:15 (16-jul) + plan de actuación MODULAR

**Estado:** informe cerrado · **F1-F11 aplicados** (Fases 0-2 + telemetría de la 1) · **Fecha:** 2026-07-16

> **Cierre de implementación (2026-07-16):** los 11 puntos tienen fix. Verificado con probe headless + suite
> (36→50 tests). El rail `music.queue` (F4) probado unitariamente de punta a punta (play→queue→ended→vacío) con
> `_resolve` mockeado — en vivo la resolución de YouTube depende de red (a ratos bloqueada en dev). F3/F7 son
> TELEMETRÍA (miden, no cambian conducta) hasta ver incidencia real con el chain-suite. Fase 3 (rails de usuario
> vs génesis) queda para su propia iniciativa cuando toque persistir reglas por-cuenta.

## Principio rector (palabras del operador, sesión 23:15)

> El sistema empieza a funcionar bastante bien → ajustar SIN romper lo anterior. NO ensuciar el cerebro con
> prompts cada vez más extensos: **todo lo nuevo entra de forma MODULAR, como RAILS** — unos de la *genética del
> génesis* (las reglas base del FlashBrain, los prompts de inicialización de tareas, la gestión del corto plazo/
> estado, comprimidos) y otros *de usuario* (reglas nuevas, widgets, memoria de ESTA cuenta) — un sistema flexible
> como un niño que aprende. El PULSO (~1 Hz) es el motor que espera/vigila (p. ej. «cuando acabe la canción, pon
> la siguiente»), no un prompt más largo.

Traducción operativa: cada fallo de abajo se arregla con (a) una **cadena en código** (rail/guard determinista),
(b) una **corrección de la descripción de UNA tool** (enseñar, no listas de palabras), o (c) **el pulso** vigilando
un run vivo — y NUNCA con un párrafo nuevo en el prompt global.

## Informe de fallos (sesión 23:15:45–23:27:56, trazas T2–T54)

| # | Qué pasó (evidencia) | Causa raíz | Destino |
|---|---|---|---|
| F1 | **stop_worker(todo) mató las DOS tareas** (T49 23:26:37, `todo → ['2','3']`): la queja era de VENTANAS duplicadas y se cargó la ITV que SÍ trabajaba + el retry del widget. Luego el modelo reconoció "absurdo". | Matar es irreversible y el modelo no-razonador eligió `todo` sin que el operador lo dijera. | **HECHO** — guard: `todo` con varias tareas de objetivos distintos exige "todo/todas/ambos" en el turno; si no, `resolve_sessions` o PREGUNTA. |
| F2 | **«No pude crear el widget»** (23:22:54) en un MODIFY, sin razón alguna en observabilidad — indiagnosticable. | Copy fija + el `error` del generador se quedaba en un dict interno. | **HECHO** — copy por acción + evento `task/generator_fail` con la razón al timeline. |
| F3 | **ITV: "me pongo con ello" SIN llamar a la tool** (T22 23:20:32; decisión forense: `escalated:false`, 10 tools ofrecidas). Solo escaló 6 min después (T43), tras dos quejas. | Fallo del modelo ("decirlo sin llamarla", regla ya presente en la descripción). Con un worker de widget ya vivo, el bloque "NO DUPLICAR" pudo inhibirle. | Fase 1 — **detector determinista de compromiso-sin-acción** como TELEMETRÍA primero (evento `promise_no_tool` cuando reply en 1ª persona + decisión vacía), medir incidencia con el chain-suite; si es frecuente, backstop de re-pase. NO añadir prosa al prompt. |
| F4 | **Playlist encadenada NO automática**: "Beatles, luego Shakira, luego Bruce" → cada cambio lo tuvo que pedir el operador (T23); "next" no existe en la fuente gratis; **"cuando acabe la de Shakira pon Bruce" (T27) no tiene mecanismo** — el pulso no vigila el fin de canción. | No hay COLA en el rail de música ni señal de FIN de canción. | Fase 2 (la joya) — **rail `music.queue`**: cola en el run `music.playing`; el widget escucha `onStateChange` del player (handshake `listening` del iframe API) y al `ended` dispara `apply_action("ended")` → el conector reproduce el siguiente de la cola EN CÓDIGO. `play_music` gana `action=queue` (1 línea en SU descripción). El pulso vigila runs `playing` sin latido de widget (tarjeta cerrada) como fallback. |
| F5 | **Re-play que PISA la canción sonando**: T31 ("Y no tenías por qué." — una QUEJA) disparó `play Shakira` y cambió "Dai Dai"→"La Tortura" en mitad de la reproducción (T32: bronca). También T27 re-lanzó `play Shakira` sonando ya Shakira. | El modelo sobre-actúa en turnos de queja/corrección; y `play` de lo MISMO que suena re-resuelve y reinicia. | Fase 2 — guard determinista EN el rail (no en el prompt): `play <X>` con run `music.playing` cuyo label ya casa con X → NO re-lanzar (no-op + "ya suena"); la queja no puede reiniciar la música. |
| F6 | **Widget `results` abierto espontáneamente** (T24 23:21:16, `show:results src:flash`) en un turno de queja sobre la playlist; el operador lo percibió como "widget de proyectos/búsqueda" y lo hizo cerrar (T41). | Mismo patrón F5: sobre-acción en turno de queja — el modelo coló un `[[show:results]]` sin relación. | Fase 1 — ampliar el guard `_is_meta_widget_question` a **turnos de CORRECCIÓN pura** (queja sobre lo YA hecho, sin verbo de orden nuevo): show/data-op RETENIDOS. Determinista, ejecución, no prompt. |
| F7 | **Voz que se corta a media locución** y tras una pausa suelta el mensaje SIGUIENTE sin acabar el anterior (narrado T36–T40; evidencia "Cl" truncado 22:47:11 al entregar un worker). | Hipótesis: `proactive.notify` → `session.say()` en una ventana de falso-silencio (probe 0.3s) o `say` pisando el speech en vuelo. NO concluyente aún. | Fase 1 — INSTRUMENTAR primero: evento `say` con `speech_in_flight` + duración del speech interrumpido; reproducir con el tester. Fix probable: cola de locuciones (un `say` espera al handle vivo) — tocar SOLO `agent.py::_speak`. |
| F8 | **Doble kickoff** (23:15:45 y 23:15:46, dos `worker_start` + dos saludos T2/T3 generados). | Dos jobs de agente en la misma sala (reconexión rápida del frontend / doble dispatch de LiveKit). | Fase 1 — guard de agente único por sala (si el entrypoint ve otro job vivo <5s en la misma sala, el viejo muere limpio) + kickoff idempotente por sesión. |
| F9 | **"Dos navegadores, uno en blanco"** (23:26:24-33): el operador vio dos ventanas; solo consta `navegador::t1` (tarea) + el eco normalizado del canvas. La "ventana en blanco" pudo ser la tarjeta de tarea aún sin captura o el singleton `browse` restaurado del localStorage. | Sin evidencia suficiente en el timeline (la auditoría V2-039 registra geometría pero no hubo 2º `show`). | Fase 1 — el frontend reporta en `/api/canvas/state` los ids de INSTANCIA completos (además del set normalizado) → la próxima vez sabremos exactamente qué tarjetas había. |
| F10 | **La música tardó ~1 min en oírse** (T5 23:16:19 → "Ahora sí" 23:17:21) pese al fix mute=1+unMute. | Los dos `wake` (1.2s/2.6s) llegan ANTES de que el player esté listo si el iframe tarda (red YouTube); no hay reintento posterior ni señal de readiness. | Fase 2 (junto a F4) — el handshake `listening` del iframe API da `onReady` REAL → unMute+play al evento, no a ciegas por timeout. |
| F11 | Deuda de higiene: mensajes del conector empalmados sin espacio ("…sin pausa.Con esta fuente gratis…"); bridge WhatsApp huérfano de un stack viejo escribiendo en logs ajenos (pid 99530). | Concat sin separador en la respuesta del turno + patrón del pkill que no casa el cmdline real del bridge. | Fase 1 — separador; ajustar patrón de reap del bridge. |

**Lo que SÍ funcionó** (no tocar): stop de música a la primera (T9, fix de ayer), show/close de agenda y data-op
de agenda correctos (T18/T20), la inyección al worker vivo (T17 "estilo Spotify" → inject, no duplicó), el dedup
de escalada, `results` cerrado a la primera (T41), la CONVERSACIÓN RECIENTE ya viajó al worker ITV (T43), el guard
de cierre corto y las trazas V2-044 (este informe existe gracias a ellas).

## Plan de actuación (fases pequeñas, cada una verificable con el probe/chain-suite antes de seguir)

- **Fase 0 (hecha en esta sesión):** F1 guard matar-todo · F2 razón del generador a observabilidad.
- **Fase 1 — visibilidad y guards de ejecución (sin tocar prompts):** F3 telemetría compromiso-sin-acción ·
  F6 guard de turno-de-corrección · F7 instrumentar `say`/speech-in-flight · F8 agente único por sala ·
  F9 canvas reporta instancias · F11 higiene. Cada pieza = un cambio acotado + un caso nuevo en
  `tester/chain_suite.py`.
- **Fase 2 — el rail de COLA de música (`music.queue`, la petición estrella):** cola en el run + `ended` del
  widget (handshake iframe API con `onReady`/`onStateChange` reales → cierra también F10) + guard no-reiniciar-lo-
  que-suena (F5) + `action=queue` en `play_music`. El FlashBrain sigue no-razonador: la cadena vive EN CÓDIGO y
  el pulso vigila. Diseño del patrón: V2-042 (rails); este es el 2º rail conducido completo.
- **Fase 3 — génesis vs usuario:** formalizar que `_GUIDANCE` (guía por run vivo) admite rails DE USUARIO
  (aprendidos/configurados por cuenta, persistidos en memoria) además de los de génesis — el "niño que aprende":
  una corrección repetida del operador se convierte en regla de usuario inyectada SOLO cuando su rail está vivo,
  nunca en el prompt global.

## Addendum — sesión 17-jul (F12): widget espurio por doble-disparo del safety-net

**Síntoma (operador):** «le he dicho que pusiera música… luego ha abierto el reloj y la música a la vez; no puede
haber deducido de ninguna manera que había que abrir el reloj».

**Traza (T8·c0ec):** «Y ahora necesito que **pon**gas a Bruce Springsteen» → el modelo resolvió BIEN
(`play_music(Bruce)` → sonó + `show:musica`), pero el timeline muestra ADEMÁS `widget show id=clock src=flash` con
`decision.shown_ids=[]` (NO vino de una tag del modelo).

**Causa raíz (doble bug compuesto):**
1. `play_music` (y `play_video`) NO marcan `acted["widget"]`. El **safety-net** `_widget_fallback` (para «el modelo
   charló pero olvidó la tag de show») solo se gateaba con `acted["widget"]/escalate/search` → corría IGUAL tras un
   `play_music` correcto.
2. Su regex de verbos-de-show incluye `\bpon` → casó **"pongas"**, y `runtime.identify("…ahora…")` fuzzy-casó
   **"aHORA" → "hora" → widget clock** (sin la palabra "ahora" devuelve `None`). Resultado: `show:clock` que nadie
   pidió.

**Fix (quirúrgico, sin prompt más gordo, sin tabla nueva):** un predicado `_tool_handled` (turno resuelto por
CUALQUIER tool: música/vídeo/data-op/escalada/búsqueda/worker/estilo/confirm) gatea AMBOS fallbacks
(`_widget_fallback` y el login-fallback). Los fallbacks son SOLO para pura charla — jamás re-adivinan sobre un turno
ya accionado. `runtime.identify` NO se toca (lo consumen muchos sitios; el riesgo de "ahora→clock" queda contenido
al no dejar correr el fallback tras una tool). `voice/engine/llm/providers/nucleo.py`.

## Regla de verificación

Cada fase: (1) probe/chain-suite en verde ANTES y DESPUÉS (43 casos actuales + los nuevos); (2) una sesión manual
corta del operador; (3) alineación (docs/diagrama) solo al cerrar la fase, no a medias.
