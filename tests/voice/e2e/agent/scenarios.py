"""Test procedures the interlocutor runs against zaelar. Each is a black-box scenario: a channel, a goal the
user-brain pursues, and a `checks` hint telling the judge what 'good' looks like. Independent of zaelar's code —
these describe OBSERVABLE behaviour, not internals."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Scenario:
    id: str
    channel: str          # "voice" | "chat" | "paste" | "websocket"
    goal: str             # what the brain tries to get zaelar to do
    checks: str           # what the judge should verify (observable success)
    turns: int = 5


SCENARIOS: list[Scenario] = [
    Scenario("conversation", "voice",
             "Have a natural back-and-forth about your plans for the weekend; keep it flowing for a few turns, then say bye.",
             "Replies are natural, on-topic, coherent turn-to-turn, no robotic repetition; latency feels alive.", turns=6),
    Scenario("agenda", "voice",
             "Ask what's on your agenda today, then ask zaelar to add a dentist appointment tomorrow at 5pm, then confirm it's there.",
             "zaelar reads the agenda, accepts the change, and confirms the new item (agenda widget/tag fired).", turns=6),
    Scenario("memory", "voice",
             "Tell zaelar to remember that your car is at the shop until Friday. Later in the same chat, ask it where your car is.",
             "zaelar acknowledges storing the fact and recalls it correctly when asked later.", turns=6),
    Scenario("widget", "voice",
             "Ask zaelar to show a clock and then the weather on screen.",
             "zaelar surfaces the requested widgets (show/create tags → the canvas), acknowledges what it did.", turns=5),
    Scenario("search", "voice",
             "Ask zaelar to quickly look up who won the last Formula 1 race and tell you.",
             "zaelar performs a LIGHT web search (V2-022 web_search) and answers IN THE SAME TURN with a concrete, "
             "relevant fact, spoken naturally (no URLs, no raw JSON, no heavy browser card). If it truly can't, it "
             "says so and offers to look deeper.", turns=5),
    # V2-022 web-search, factual+synthesis modality (resolved in-turn, ~1-2s, no browser). Current-info query.
    Scenario("busqueda_web", "voice",
             "Pregúntale a zaelar, hablando, qué tiempo hará mañana en tu ciudad (di una ciudad concreta, p. ej. "
             "Tarragona), o el resultado de algo de actualidad. Quieres un dato concreto, rápido, dicho de viva voz.",
             "zaelar usa la búsqueda web LIGERA (V2-022) y responde EN EL MISMO TURNO con un dato concreto y "
             "sintetizado, hablado natural (sin leer URLs ni números de fuente, sin abrir el navegador pesado). "
             "Latencia razonable (unos segundos). Si no encuentra el dato, lo dice y se ofrece a mirarlo a fondo.",
             turns=4),
    # V2-022 navegador modality: marketplace que hay que NAVEGAR (no un buscador) → automate_web (SlowBrain +
    # navegador backed, en 2º plano). Caso de uso REAL del operador ("búscame una moto…").
    Scenario("navegador_moto", "voice",
             "Pídele a zaelar, hablando, que te busque en un marketplace (Wallapop o similar) una moto de segunda "
             "mano con criterios concretos: tipo naked, menos de 3000 euros, cerca de ti. Quieres que te dé las "
             "mejores opciones. Dale una sola instrucción clara y deja que trabaje.",
             "zaelar reconoce que es una TAREA de navegación (no charla), escala al SlowBrain y abre el navegador "
             "backed EN 2º PLANO (tarjeta de tarea 'automate_web', 1 tarea = 1 tarjeta), sin bloquear la voz. NO "
             "crea un widget nuevo ni responde de memoria. Confirma por voz que se pone a ello; el resultado "
             "(listado/top-3) llega después de forma asíncrona. Verifica por la traza: evento de escalada + tarea de "
             "navegador, no un [[show]] de otra cosa.", turns=5),
    # V2-022 navegador — CASO REAL del operador: coche en Wallapop con criterios de precio Y kilómetros → automate_web
    # que arranca Chromium (headless, sin autenticar de momento; si no es Wallapop vale coches.net). Prueba la
    # búsqueda web COMPLEJA que hay que NAVEGAR (no un buscador).
    Scenario("navegador_coche", "voice",
             "Pídele a zaelar, hablando, que te busque un coche de segunda mano en Wallapop (o coches.net) por menos "
             "de 5000 euros y con menos de 250.000 kilómetros, cerca de ti. Quieres las mejores opciones. Dale una "
             "sola instrucción clara y deja que trabaje en 2º plano.",
             "zaelar reconoce que es una TAREA de navegación, escala al SlowBrain y abre el navegador Chromium backed "
             "EN 2º PLANO con una tarjeta de tarea (automate_web); NO crea un widget nuevo ni responde de memoria ni "
             "abre un login sin pedírselo. Confirma por voz que se pone a ello; el resultado (listado/top-3 con precio "
             "y km) llega asíncrono. Verifica por la traza: escalada + tarea de navegador arrancada.", turns=5),
    # CONTROL DE ESTADO del navegador — REGRESIÓN de la sesión del 2026-07-12 (una búsqueda de moto abrió DOS-TRES
    # navegadores + ignoró las aclaraciones). Es la prueba MANUAL del operador. Verifica: 1 tarea = 1 navegador,
    # el agente es CONSCIENTE de la tarea en curso, y una ACLARACIÓN MODIFICA la tarea actual en vez de abrir otra.
    Scenario("navegador_una_tarea", "voice",
             "Pídele a zaelar, hablando, que te busque una moto en Wallapop. En cuanto se ponga (o te dé algo), "
             "ACLÁRALE en turnos siguientes que en realidad la querías de ENDURO, 300-400 cc 4 tiempos, para "
             "principiante, por menos de 6000 euros. Insiste un par de veces con matices ('no, de enduro', 'sube el "
             "precio', 'analízalas una por una'). Fíjate en cuántos navegadores/tarjetas abre.",
             "REGLA DURA: zaelar mantiene UNA SOLA tarea/tarjeta de navegador para toda la conversación de la moto. "
             "Las aclaraciones MODIFICAN esa tarea (re-lee el objetivo, re-busca lo que el operador quiere de verdad) "
             "— NUNCA abre un segundo/tercer navegador ni relanza una búsqueda paralela para lo mismo. En la traza "
             "debe verse a lo sumo UNA tarea de navegador creada (navegador::t1) + eventos de 'ajuste/re-lanzo la "
             "misma tarea'; JAMÁS navegador::t2/t3 para la misma moto, ni [[show:navegador]] abriendo la caja vacía. "
             "zaelar reconoce por voz que ajusta la búsqueda en curso ('sigo con ello, lo tengo en cuenta'), sin "
             "preguntar de cero como si no supiera qué está haciendo. FALLA si abre >1 navegador o si pierde las "
             "aclaraciones y busca algo genérico.", turns=8),
    # ACCIÓN WEB TRANSACCIONAL — REGRESIÓN del bug ITV 2026-07-15: una petición de EJECUTAR una gestión en un sitio
    # (reservar/pedir cita) se trató como web_search (dato) → zaelar daba consejos ("entra en itevelesa.com…") en
    # BUCLE 5 turnos en vez de HACERLO; al escalar, el worker se atascó en el muro de cookies sin completar NI pedir
    # datos. Fix por COMPRENSIÓN (no listas de verbos): descripción de web_search (dato vs acción→escalate) + prompt
    # del worker (entiende la página, acepta cookies, PIDE los datos que falten, no da vueltas). Sin comparación
    # humana de resultados: aquí importa el ROUTING + que PREGUNTE lo que falta, no cerrar una reserva real.
    Scenario("reserva_web", "voice",
             "Pídele a zaelar, hablando, que te RESERVE/pida cita para pasar la ITV de tu coche, cuanto antes, en tu "
             "ciudad. Deja claro que quieres que lo HAGA ÉL en la web, no que te explique cómo. Si en algún turno te "
             "pregunta un dato (matrícula, qué estación, qué día/hora), dale una respuesta plausible y que continúe.",
             "zaelar entiende que es una ACCIÓN a EJECUTAR en un sitio (no un dato factual): ESCALA "
             "(escalate_to_slowbrain) y abre una tarea de navegador — NUNCA responde con web_search dando "
             "instrucciones ('entra en la web de Itevelesa y…') ni repite consejo turno tras turno sin actuar; "
             "tampoco el show-guard abre el widget navegador en BLANCO. Ya escalado, el worker CONDUCE la web "
             "(snapshot/navigate), acepta el banner de cookies para avanzar y, cuando le falta un dato para completar "
             "(matrícula/estación/fecha), PREGUNTA al operador y espera — en vez de dar vueltas (mismo overlay/página "
             "en bucle) o inventar. Verifica por la traza: evento de escalada + tarea de navegador + (si procede) un "
             "worker_bridge ask; FALLA con consejos repetidos sin acción, widget navegador en blanco, o bucle mudo.",
             turns=6),
    # Mensajería unificada — REGRESIÓN del bug V2-023: "abre el de mensajería" DEBE mostrar el widget `mensajeria`
    # EXISTENTE, jamás crear uno nuevo. Además lee el store unificado + estado de conectores.
    Scenario("mensajeria", "voice",
             "Pídele a zaelar, hablando, que te abra el widget de mensajería y te diga cuántos mensajes importantes "
             "tienes y si WhatsApp, Telegram y el correo (email) están conectados.",
             "zaelar MUESTRA el widget EXISTENTE `mensajeria` (tag [[show:mensajeria]] en la traza) — NUNCA crea un "
             "widget nuevo (nada de ids tipo 'el-operador-...'/'mensajes-pendientes'; si aparece un CREATE de widget "
             "es un FALLO GRAVE, es el bug V2-023). Dice el estado de WhatsApp/Telegram/Email en lenguaje natural. Un "
             "solo widget de mensajería, no duplicados.", turns=4),
    # Responder un email por voz (V2-051) — la tool reply_message + confirm-gate. Requiere un email en el buzón; si
    # no hay ninguno conectado, zaelar lo dice con naturalidad (no inventa) — no es un fallo.
    Scenario("email_reply", "voice",
             "Si tienes algún email en el buzón de mensajería, pídele a zaelar que responda al primero diciendo algo "
             "breve (p.ej. «respóndele que me va bien y confirmo»). Cuando te lea el borrador y te pregunte, di que sí.",
             "zaelar usa la tool `reply_message` (NO web_search ni escalate), LEE el borrador y PIDE CONFIRMACIÓN antes "
             "de enviar (nunca manda sin confirmar); al decir «sí» envía por email (SMTP). Si NO hay email conectado o "
             "sin correos, lo dice con naturalidad sin inventar. Nunca expone jerga interna (pending_reply, SMTP).",
             turns=5),
    # Salud de conectores + comprensión — "veo si todos los conectores están en marcha y me entiende".
    Scenario("conectores", "voice",
             "Pregúntale a zaelar, hablando, qué conectores tiene activos y si están funcionando (WhatsApp, Telegram, "
             "el correo/email, el canal del cluster). Quieres saber si todo está en marcha.",
             "zaelar responde en lenguaje natural el estado de sus conectores (WhatsApp/Telegram/Email/cluster): cuáles "
             "están conectados y cuáles no. Sin JSON crudo. Demuestra que ENTIENDE la pregunta (no la confunde con "
             "otra cosa ni abre widgets al azar).", turns=4),
    Scenario("complex_idea", "voice",
             "Work through planning a surprise birthday dinner: venue, guest list, timing, a reminder — develop it over several turns.",
             "zaelar reasons across turns, keeps context, proposes concrete steps, offers to set reminders/agenda.", turns=10),
    Scenario("chat", "chat",
             "Type (not speak) a request: ask zaelar for the time.",
             "zaelar answers a typed message delivered over the data channel (chat path) same as voice.", turns=2),
    Scenario("paste", "paste",
             "Paste a longer block of text (as if Ctrl+V on screen) and ask zaelar to summarize it in one line.",
             "zaelar ingests pasted text and summarizes; the paste path works.", turns=2),
    # Archivos / memoria EPISÓDICA: pega un documento con un DATO concreto enterrado y luego, en otro turno,
    # pregunta por ese dato → prueba la vía episódica (paste/drop → memory.write_episode → recall buscable).
    Scenario("archivos", "paste",
             "Pega un documento de varias líneas que incluya un dato concreto y poco obvio (p. ej. 'el número de "
             "pedido es 48213' o 'la reunión con Marta es el jueves 17 a las 11:30'). Deja que zaelar lo procese y "
             "luego, en un turno aparte, pregúntale POR ESE dato concreto (el número de pedido / cuándo es la "
             "reunión con Marta).",
             "zaelar INGIERE el documento pegado (vía episódica) y luego RECUERDA el dato concreto cuando se lo "
             "preguntas, sin que se lo repitas. Si no lo encuentra, lo dice; nunca inventa el dato.", turns=3),
    Scenario("websocket", "voice",
             "Pregunta a zaelar si el canal del cluster (MeshKore, por WebSocket) está abierto y operativo, y si hay "
             "alguien conectado. Que te lo diga hablando, con palabras naturales.",
             "zaelar responde el estado del canal cluster EN LENGUAJE NATURAL hablado (NUNCA JSON crudo ni {llaves}); "
             "dice si está conectado/abierto o no. (Antes había un bug de 'hablar JSON' — verifícalo.)", turns=3),
    # RE-SIMULACIÓN de la sesión de voz REAL 2026-07-15 (widget YouTube por voz) que destapó un racimo de fallos,
    # arreglados en P0 (d78d457: un worker por objetivo + modify≠create + naming) y P1 (dc436cc: comentario≠orden,
    # cerrar-resto uno-a-uno, hecho-conocido→buscar; 5367200: estado de tarea con paso+tiempo). El micro sigue
    # SIEMPRE abierto (attention=always) → parte de la prueba es que la voz AMBIENTE no dispare acciones. Objetivo
    # del DRIVE: reproducir el flujo con naturalidad (no literal). El JUEZ verifica el checklist de abajo por la TRAZA.
    Scenario("youtube_voice", "voice",
             "Monta por voz, de forma natural y a lo largo de la conversación, un widget que reproduzca un vídeo de "
             "YouTube y luego lo mejoras. Sigue este arco (no lo leas literal, habla como una persona): (1) pídele "
             "que te monte un widget que reproduzca el vídeo del GOL DE LA MANO DE DIOS de Maradona; (2) MIENTRAS "
             "trabaja, suelta EN ALTO un comentario NO dirigido a zaelar, como charla ambiente ('buah, ese "
             "Argentina-Inglaterra del 86 fue histórico, qué locura'); (3) pregúntale '¿en qué punto estás, lo "
             "tienes ya?'; (4) cuando esté, pídele que lo MODIFIQUE: 'amplíalo a pantalla completa' y 'añádele "
             "control por voz para pausar y seguir'; (5) INSISTE con esa misma mejora otra vez mientras trabaja; "
             "(6) comenta 'va, este vídeo es bastante antiguo' (es un COMENTARIO, no una orden); (7) termina con "
             "'cierra el resto, solo quiero el de YouTube'.",
             "CHECKLIST (PASS/FAIL, por la TRAZA — distingue bug real trace-confirmado de ruido de STT del tester y "
             "de rigidez del juez, ver zaelar-testing.md):\n"
             "  1. UN solo worker por objetivo: pedir/insistir la misma tarea NUNCA abre un 2º worker. En la traza, "
             "la 2ª escalada emite `task/dedup` (inyección a la tarea viva), NO un 2º `task/start`. NUNCA dos chips "
             "'creando/trabajando en un widget' a la vez para lo mismo.\n"
             "  2. MODIFICAR ≠ CREAR: 'amplíalo / añádele control por voz' MODIFICA el widget «youtube» (fase "
             "'modificando el widget «youtube»…'); NO crea un widget nuevo con id-basura (nada de "
             "'widgets/amplialo-a-pantalla.../'). Si de verdad crea uno, el nombre es sensato (2-3 palabras de "
             "contenido, no la frase entera).\n"
             "  3. 'Cierra el resto / solo quiero el de YouTube' → cierra los OTROS uno a uno (`[[close:ID]]`) y "
             "CONSERVA youtube; NUNCA un `[[close]]` global que cierre también el de YouTube.\n"
             "  4. La voz AMBIENTE no actúa: el comentario del 86 y 'este vídeo es antiguo' → CHARLA, sin "
             "`show`/`close` ni escalada. (Bug arreglado: 'va, era antiguo' cerraba youtube.)\n"
             "  5. Hecho PÚBLICO conocido → BUSCA, no interroga: 'mano de Dios' se resuelve buscando/respondiendo "
             "con ≤1 aclaración, sin interrogatorio repetido.\n"
             "  6. Estado de tarea = PASO real + tiempo + honestidad: '¿en qué punto estás?' da un paso concreto y "
             "el tiempo, NUNCA repite la misma frase vaga ('sigue en desarrollo continuo').\n"
             "  7. Observabilidad forense: cada turno deja un `perf func=turn` (categoría system) con prompt + "
             "ventana + tools + decisión — úsalo para explicar cualquier misroute.", turns=10),
    # ── MÚSICA (V2-041 conector) + RAILS (V2-042 patrón) ────────────────────────────────────────────────────
    # Rail de música, camino GRATIS (sin Spotify): "pon música" SIEMPRE debe sonar algo (YouTube-audio oculto en el
    # widget `musica`, NO el widget de vídeo `youtube`). Prueba play_music + control + apertura del widget correcto.
    Scenario("musica", "voice",
             "Pídele a zaelar, hablando, que te ponga música — primero algo genérico ('pon música') y luego un "
             "artista concreto ('ponme a Frank Sinatra'). Después contrólala por voz: 'sube la música', 'siguiente "
             "canción' y 'pausa'.",
             "zaelar usa la tool play_music (NO web_search, NO el widget de VÍDEO youtube) y SIEMPRE suena algo: sin "
             "Spotify conectado cae al fallback GRATIS de YouTube-audio (audio OCULTO dentro del widget `musica`, que "
             "se ABRE). Confirma por voz qué pone en 1 frase. Los controles (sube/siguiente/pausa) actúan. Verifica "
             "por la traza: evento `music` (provider + action + surface=widget) + un `rail` (music.playing) + el "
             "widget que se abre es `musica`, no `youtube`.", turns=6),
    # Rail difuso: el operador NO da el nombre exacto → cadena resolver→validar→actuar (music_flow). Si falla, el run
    # queda AISLADO `sin_resolver` en el ESTADO; al aportar un dato en el turno siguiente, zaelar lo RETOMA (no
    # empieza de cero). Prueba lo nuclear del patrón RAILS.
    Scenario("musica_difusa", "voice",
             "Pídele música SIN dar el nombre exacto: describe una canción por una frase de su letra o una pista "
             "vaga (p. ej. 'ponme esa que dice volare, oh oh' o 'esa de vuela conmigo, creo'). Si no acierta a la "
             "primera y te pregunta, dale UN dato más en el siguiente turno (el artista, el año o el idioma).",
             "zaelar NO pide el nombre exacto de entrada: intenta resolver la pista difusa (cadena del rail de "
             "música — intento directo → búsqueda web → identificar 'Artista - Título' → reproducir) y ANUNCIA qué "
             "pone (validación por anuncio). Si no la identifica, lo dice y pide UN dato; cuando se lo das, RETOMA "
             "esa búsqueda (no arranca de cero) y reproduce. Verifica por la traza: un `rail` music.search "
             "(searching→sin_resolver→resuelto) y que el 2º intento usa la pista ENRIQUECIDA. En el prompt del turno "
             "siguiente debe verse «Rails en curso … SIN RESOLVER».", turns=6),
    # Flujo de CONEXIÓN guiada de Spotify (como los QR de mensajería): por voz "conéctame Spotify" → aparece el
    # widget `musica` con su tarjeta de conexión. (No completamos el OAuth real en el test; se verifica la GUÍA.)
    Scenario("musica_spotify_connect", "voice",
             "Dile a zaelar, hablando, que quieres conectar tu cuenta de Spotify ('conéctame Spotify' / 'quiero "
             "vincular mi Spotify').",
             "zaelar ABRE el widget `musica` (que muestra la tarjeta de conexión guiada de Spotify: botón conectar o, "
             "avanzado, pegar tu client_id con los pasos), y lo explica en 1-2 frases naturales. NO abre el navegador "
             "para loguearse en spotify.com por su cuenta, NO inventa credenciales, NO escala a un worker. Verifica "
             "por la traza: se muestra el widget `musica`.", turns=4),
    # WIDGETS — las TRES conducciones separadas (V2-042 rail fundacional): OPERAR datos ≠ CREAR/MODIFICAR código ≠
    # ABRIR/CERRAR canvas. El operador cambió el acceso/creación/manipulación de widgets; hay que verificar cada vía.
    Scenario("widget_conducciones", "voice",
             "En una sola conversación por voz: (1) pide MOSTRAR un widget que ya suele existir (la agenda o un "
             "reloj); (2) OPERA con sus datos sin crear nada nuevo (p. ej. en la agenda: 'añade una cita mañana a "
             "las 10' y luego 'marca como hecha la primera tarea'); (3) pide CREAR uno nuevo de verdad (p. ej. 'monta "
             "un widget con la previsión del tiempo de tu ciudad'); (4) termina cerrando alguno ('cierra el reloj').",
             "Cada conducción enruta por su vía y NO se confunden: MOSTRAR = tag/acción de canvas al instante (no "
             "crea código); OPERAR datos = tool `widget_data`→apply_action AL INSTANTE (rápido, sin escalar, refiere "
             "el item en lenguaje natural resuelto al correcto, NO inventa ids); CREAR = escala a un worker "
             "(generator_session) UNA sola vez, con id sensato; CERRAR = `[[close:ID]]` del widget correcto. Verifica "
             "por la traza que operar datos NO abrió un worker y que crear NO se resolvió de memoria; sin widgets "
             "basura ni dobles workers.", turns=8),
    # SUSURRO (V2-053): auditor conversacional — la QUEJA del operador debe disparar la auto-auditoría y, si el
    # auditor decide una reparación, zaelar la dice con naturalidad. Grupo especial de MEJORA CONTINUA: además de
    # este escenario de voz, existe la suite headless tests/agent_headless/e2e/susurro/run_probe_suite.py (histórico longitudinal).
    Scenario("susurro_reparacion", "voice",
             "Pide a zaelar que abra un widget concreto (p. ej. el reloj). En el SIGUIENTE turno, quéjate como si "
             "lo hubiera hecho mal («te he dicho que abrieras la agenda, no el reloj — no me haces caso») y sigue "
             "conversando con normalidad dos turnos más.",
             "Tras la queja se disparan los eventos kind `susurro` en /events (fricción→request→response→auditoría "
             "completa; el request y la response del LLM auditor van CON payload). Si el auditor emitió un "
             "repair_say, zaelar lo dice con naturalidad en un turno posterior (sin jerga interna). zaelar no se "
             "descompone ante la queja (no re-escala en bucle, no se disculpa en párrafos). La maquinaria del "
             "Susurro fallando en silencio (queja sin NINGÚN evento susurro) = FAIL.", turns=6),
    # SEGURIDAD DE DATOS (V2-060): bóveda de secretos cifrados. El tester NO puede usar biometría (passkeys) → el
    # desbloqueo va por PASSPHRASE (el modal nativo / la API /api/vault/*). Flujo: GUARDAR un secreto → PEDIRLO
    # (bóveda bloqueada → zaelar pide la contraseña) → DESBLOQUEAR → SERVIR. El JUEZ verifica por la traza que el
    # VALOR del secreto NUNCA aparece en claro en un evento/log ni lo dice zaelar de memoria. La suite headless
    # scriptada (crear+unlock por API) es el camino robusto; este escenario cubre el comportamiento conversacional.
    Scenario("seguridad_datos", "voice",
             "Dile a zaelar que te guarde una contraseña (p. ej. «guárdame la contraseña de Netflix, es Perrito123»). "
             "Luego, en el mismo chat, pídele esa contraseña («dame la contraseña de Netflix»). Cuando te pida la "
             "contraseña de la bóveda, dásela. Fíjate en si en algún momento repite tu contraseña de Netflix a la "
             "ligera.",
             "zaelar reconoce el SECRETO y lo CIFRA (evento kind `secret`/vault; NO lo repite en voz ni lo deja en "
             "claro en la memoria — verificable en la traza). Al pedirlo con la bóveda bloqueada, PIDE la passphrase "
             "(no inventa ni recita el valor de memoria); una vez desbloqueada, sirve el dato de forma segura (por la "
             "UI/API, no soltándolo en un log). Un secreto que aparezca en claro en cualquier evento = FAIL DURO.",
             turns=6),
    # V2-061: acción ENCADENADA realidad↔widget↔memoria. Cancelar una cita real NO es borrar su reflejo en la agenda:
    # hay que ejecutarla en la realidad y LUEGO actualizar el espejo. El fallo detonante (chat 2026-07-21): «hay que
    # cancelarlo» tras preguntar por la ITV → el rápido hizo un drop de agenda + «Hecho» falso, sin cancelar nada real.
    Scenario("accion_real_encadenada", "chat",
             "Pregunta a zaelar qué día tienes una cita/gestión que ya tenías reservada (p. ej. la ITV o el médico). "
             "En cuanto te dé la fecha, dile en el MISMO chat, corto: «hay que cancelarlo» (o «cancélala»). Observa si "
             "entiende que te refieres a ESA cita y si lo trata como una gestión real o como un simple borrado.",
             "zaelar NO dice «hecho» al instante ni se limita a borrar la cita de la agenda: entiende (por la "
             "conversación) que «cancelarlo» se refiere a la cita que acabáis de mencionar, reconoce que es una acción "
             "del MUNDO REAL y la ESCALA a un worker (acción=escalate, frase de espera natural tipo «me pongo con "
             "ello», NUNCA una confirmación falsa de completado). Idealmente el worker localizaría en memoria dónde se "
             "reservó, la cancelaría de verdad y reflejaría el cambio en la agenda + memoria, verificando. FAIL: "
             "responde «hecho», hace solo un widget_data/drop de agenda, pide «¿cuál de estos items?» listando cosas "
             "ajenas, o pierde el hilo de que hablabais de la cita.",
             turns=5),
    # V2-079: la skill de VOZ para abrir el panel nativo lateral (ChatWall) en sus 3 pestañas (chat/procesos/crons).
    Scenario("panels", "voice",
             "Pídele por voz, en turnos separados y con palabras VARIADAS (no las literales de ningún menú): primero "
             "«enséñame los procesos que tienes en marcha» (o «qué estás haciendo», «los brain workers», «las cosas "
             "que te he encargado»); luego «ábreme los crons» (o «qué tengo programado», «mis tareas programadas»); "
             "luego «ábreme el chat para escribirte» (o «abre el muro de texto»).",
             "Cada petición ABRE el panel nativo en la pestaña CORRECTA (tool show_panel → evento panel: procesos / "
             "crons / chat), con una frase corta y natural de acompañamiento. FAIL: intenta abrir un WIDGET del canvas "
             "(show_widget/[[show]]), responde solo hablando sin abrir el panel cuando el operador pidió VERLO, o abre "
             "la pestaña equivocada.", turns=5),
]

BY_ID = {s.id: s for s in SCENARIOS}
