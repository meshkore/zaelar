# V2-054 — Modo CHAT (voz-off) + retención de conversación + naturalidad de la voz (DISEÑO)

**Origen (operador, 2026-07-19):** dos peticiones + una verificación, más el trabajo de naturalidad de la voz que
está en curso.

Estado: **DISEÑO / EN CURSO.** La parte de naturalidad de la voz (lead-in filler) ya está construida (V2-053-ish,
commit del filler); el resto es plan.

---

## 1 · Modo CHAT = voz OFF (escribir en vez de hablar, sin latencia de voz)

**Petición:** cuando el operador escribe por el chat, se apaga la voz y TODO va por escrito — si alguien prefiere
teclear a hablar, la conversación es textual y **se elimina la latencia de la gestión por voz** (STT + TTS + TTFT
de audio).

**Estado actual (verificado 2026-07-19):** el chat escrito se inyecta como un turno normal
(`voice/engine/pipeline/agent.py:371-409` → `session.generate_reply(user_input=txt)`) → hoy **el chat TAMBIÉN
habla por TTS**. Esa es justo la latencia que el operador quiere quitar.

**Tareas:**
- [x] T1.1 **Icono de altavoz auto-off al abrir el chat** — `frontend/app/components/ChatWall.js`: `createEffect`
      sobre `store.chatOpen()`; al abrir recuerda `_prevMuted` y pone el 🔊 a OFF (`session.toggleBotMute`); al
      cerrar RESTAURA el estado previo (no fuerza "on"). (Se cableó en ChatWall, dueño del estado del chat, no en
      Orb.js.)
- [x] T1.2 **Turno de chat = respuesta SOLO texto (sin TTS)** — mecanismo LIMPIO a nivel de sesión de LiveKit:
      `session.output.set_audio_enabled(False)`. En `agent_activity` eso hace `audio_output=None` → el pipeline
      NO invoca el `tts_node` (rama text-only) → **cero síntesis** (ahorra latencia TTS + coste), no solo mute de
      playback. Nuevo topic de datos **`zaelar-voice`** (`agent.py::_on_data`): el frontend publica `{audio:false}`
      al abrir el chat y `{audio:true}` al cerrar (`session-lk.js::setVoiceOutput`). La respuesta llega al ChatWall
      por el evento `transcript/assistant` (`conversation_item_added`), independiente del audio. Acción/tags/memoria
      IDÉNTICOS — solo se suprime la síntesis. STT ya es cero en un turno tecleado (llega por data channel, sin micro).
- [x] T1.3 Coherencia con el gate de atención: el chat sigue llamando a `attention.note_directed()` (turno SIEMPRE
      dirigido); apagar el audio no toca el gate → nada del ciclo se rompe.
- [~] T1.4 Tests: sintaxis verificada (py + `node --check` de los 2 JS); **e2e vivo** = abrir chat → teclear →
      sin audio + respuesta en ChatWall + evento «voz OFF (modo chat — sin TTS)» en el timeline. Un test headless
      LiveKit automatizado queda pendiente (requiere 2º participante; hoy se valida en vivo + observabilidad).

## 2 · Retención de conversación (≥100 msgs) + verificación del pipeline de memoria

**Petición:** guardar TODA la conversación (chat abierto o cerrado), al menos ~100 mensajes hacia atrás; luego el
log puede podarse. La memoria de CORTO plazo registra lo reciente (1-2 días); el resto a LARGO. La memoria NO guarda
literales del chat — solo extractos filtrados/resumidos/optimizados. *"Comprueba y decide si hay que mejorar."*

**Verificación (2026-07-19) — lo que SÍ se cumple:**
- Voz y chat comparten camino; ambos turnos se (a) DESTILAN a píldoras vía el CORAZÓN (`nucleo/mem_processor.py`,
  NO literal — "no copies la frase cruda") y (b) escriben al buffer conv persistente
  (`nucleo.py:1379-1389`, `kind="conv" level="short" ttl_days=2` en SQLite).
- Promoción corto→largo AUTOMÁTICA (`memory/consolidator.py`: short→mid 2d, mid→long 30d) + decay Ebbinghaus +
  consolidación en el loop cada 1h. Resiembra de la ventana tras reinicio (`recent_window`).

**HUECOS detectados (lo que NO se cumple):**
- [ ] T2.1 **El TTL de corto NO se aplica**: `ttl_days=2` del buffer conv se guarda pero **ningún código lo
      purga** (grep confirmó que no hay `DELETE ... WHERE ttl`); `consolidator.promote` EXCLUYE `kind='conv'`
      (`consolidator.py:135`). El comentario `nucleo.py:1372` ("el consolidador poda este buffer por TTL") es
      FALSO respecto al código. → **Implementar la poda por TTL del buffer conv** en el consolidador (o una purga
      dedicada), respetando pinned. Corregir el comentario.
- [ ] T2.2 **No existe retención explícita "≥100 msgs, luego poda"**: hoy se guarda TODO en disco (sin poda
      temporal) hasta el cap global de 50k (`evict`), y las LECTURAS están capadas a `recent_window(6)`/
      `recent_short(30)`. → Definir la política: conservar N≥100 turnos conv recientes y podar el resto por TTL
      (liga con T2.1). Decidir si subir el límite de lectura del corto.
- [ ] T2.3 **Se guarda texto LITERAL en memoria durable** (contra "solo extractos"): el buffer conv guarda el
      turno verbatim (`meta.u`/`meta.a`) y varios backstops `*-net` (`memory_agent.py:918-956`) persisten el turno
      CRUDO a `long`. → Decidir: es aceptable que el buffer conv reciente sea verbatim (es corto plazo, se poda con
      T2.1); pero revisar si los `*-net` deberían destilar en vez de guardar crudo a largo. Decisión del operador.
- [ ] T2.4 **El chat wall del frontend no se persiste** (RAM del navegador, se pierde al recargar; sin cap). →
      Si se quiere historial visible ≥100 tras recargar, hidratarlo desde el buffer conv persistente al conectar
      (nuevo endpoint de lectura o ampliar `recent_window`).

**Veredicto:** el núcleo (destilar a extractos + corto/largo + decay) YA funciona como el operador espera; los
huecos son de PODA (TTL no aplicado), RETENCIÓN explícita (100), literales en `*-net`, y persistencia del chat
wall. Ninguno es urgente; T2.1 (TTL real) es el más sano de cerrar primero.

## 3 · Naturalidad de la voz — lead-in filler sin cortes (EN CURSO)

**Petición:** iterar con la simulación de voz e2e (`tester/`, INI-013) leyendo la observabilidad milisegundo a
milisegundo: evaluar si los nexos/frases-para-ganar-tiempo están bien colocados y son naturales, y **garantizar
que NO se cortan** — si un nexo corto de 4 palabras está sonando y ya hay respuesta que reproducir, el nexo debe
TERMINAR y luego enlazar con lo siguiente, natural.

- [x] T3.1 Lead-in filler timer-gated (`ZAELAR_FILLER_MS`, pool variado neutro, cancela al primer token real).
- [x] **Iteración e2e #1 (2026-07-19)**: la simulación de voz destapó 2 bugs del SALUDO, arreglados y verificados: (a) el filler sonaba en el KICKOFF («Pues…» antes de saludar) → suprimido en `first_turn`; (b) el kickoff se mal-enrutaba a `set_style_directive` → zaelar saludaba «Pues… Hecho.» → el kickoff ahora va SIN tools (saludo puro) → «Hola, Ricart. ¿Cómo estás?…» correcto.
- [ ] T3.2 **Garantizar que el nexo no se corta**: verificar en el stream de TTS que el chunk del filler se
      sintetiza ENTERO antes de encadenar la respuesta real (mismo `_event_ch` → debería ser continuo; el `…`
      del filler da pausa natural). Medir con el tester e2e y la observabilidad (transcripción acompasada al audio).
- [ ] T3.2b **DEUDA del tester de voz (bloquea la iteración multi-turno)**: el DRIVE del tester apuntaba a Ollama local (apagado por batería) → connection refused; repuntado a xAI da HTTP 400 (payload user/assistant invertido que xAI no tolera) y a OpenAI da 401 (clave). El tester solo completa el kickoff. **Migrar el DRIVE del tester a un modelo de nube que funcione** (formato de mensajes compatible) para poder conducir conversaciones multi-turno. Hasta entonces, la iteración de voz se hace con el kickoff + probe + oído del operador en vivo.
- [ ] T3.3 **Iteración autónoma con el tester de voz** (`tester/`): lanzar simulación → evaluar con inteligencia
      la observabilidad (timing STT/TTFT/TTS por ms) → decidir si los nexos son naturales / bien colocados / sin
      cortes → mejorar el sistema → repetir. Archivar hallazgos.

## 5 · «Mar de testing por dominios» — simulación de conversación a escala (2026-07-19/20)

Construido `tester/domain_sea.py` (INI-013): genera N parafraseos NATURALES por semilla (vía AIMLAPI, `tester.llm`)
y los pasa por el canal PROBE (`/api/flash/say`, headless, rápido) → ejercita el MISMO FlashBrain/router/rails/
tools/memoria-estado/Susurro. 14 dominios (mem/web/math/chat/show/close/create/music/video/deep/style + multiidioma
en/ca/fr). Auto-marca fallos de routing; el operador/agente evalúa con criterio. Corre cientos de turnos por ronda
(`domain_sea.py all 8` ≈ 200). **Bugs REALES arreglados en 8 rondas (~1500 turnos):**
1. **música-cambio**: tras poner música, «no quería esa, ponme algo más tranquilo» se quedaba en chat (promesa) →
   `play_music` distingue queja-comentario de queja-con-cambio.
2. **apaga/quita el reloj**: no eran verbos de cerrar → `quita el reloj`→`delete_widget` (¡borrar permanente!) y
   `apaga`→escalate. +apag/quit/cerr\w*/turn off en `_CLOSE_VERB_RE` + guardas (no cerrar si hubo música/data-op).
3. **crear widget cortés**: «¿podrías crearme un widget?» → chat sin escalar. +conjugaciones (hac/hacer/hag).
4. **PROMESA SIN ACCIÓN (unificado, el más generalizable)**: fraseo cortés/subjuntivo → el modelo CHARLA una
   promesa sin llamar a la tool. Backstop gated por la promesa en la RESPUESTA (`router.promises_action`) →
   re-deriva la intención con clasificadores deterministas (create→escala, show-estricto→show, música→play).
   Generaliza sobre todas las conjugaciones. Provider+probe (paridad).
- **Lecciones (doctrina del operador confirmada):** (a) parchear verbo a verbo NO generaliza (cerraras→hacer→
  hicieras…); (b) ampliar verbos AMBIGUOS ('pon'/'ver') REGRESIONA ('va a poner el tiempo'→show) — revertido; (c)
  el **techo determinista** es el fraseo indirecto SIN verbo («me vendría bien un widget») → **territorio del
  Susurro** (F2/F3), no de más regex. El mar de testing es ahora la herramienta para no re-investigar.

## 4 · Bitácora
- **2026-07-20** · §1 CONSTRUIDO (modo CHAT = voz OFF): topic `zaelar-voice` → `session.output.set_audio_enabled`
  (salta el TTS en el pipeline de LiveKit, ahorro real de latencia+coste, no mute de playback) + efecto en ChatWall
  (icono OFF al abrir, restaura al cerrar). T1.1/T1.2/T1.3 hechas; T1.4 e2e headless pendiente (validado en vivo).
- **2026-07-19** · Creada. §1 y §2 anotados a petición del operador ("para que no se me olvide"). §2 verificado
  (pipeline de memoria: núcleo OK, 4 huecos). §3 en curso (filler construido; falta iteración e2e).
- **2026-07-19/20** · §5 mar de testing construido (`tester/domain_sea.py`) + 4 clases de bug arregladas en ~1500
  turnos parafraseados (música-cambio, apaga/quita-close incl. delete peligroso, crear-cortés, promesa-sin-acción
  unificado). DRIVE del tester repuntado a AIMLAPI (Ollama estaba apagado). Kickoff arreglado (saludo sin tools ni
  filler). Techo determinista identificado → Susurro.
