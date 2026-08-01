# Catálogo de escenarios de test — anexo del bot tester

> Lista LEGIBLE de los casos de uso que probamos, agrupados por capacidad y por prioridad. Es el ANEXO humano de
> `tests/voice/e2e/agent/scenarios.py` (la fuente ejecutable). **Debe mantenerse alineado con `scenarios.py` en el Paso 0** del
> playbook (`.meshkore/docs/ops/zaelar-testing.md`): si se añade/cambia un escenario en el código, se refleja aquí;
> si aquí falta cubrir una capacidad nueva (últimas 48 h), se añade el escenario al código.
>
> Cada escenario declara: **canal** (voz/chat/paste), **objetivo** (lo que el tester intenta), **criterio de éxito**
> (lo que el juez/nosotros verificamos), y si necesita **comparación humana** (✋) además del juez.

## Prioridad 1 — Búsqueda y datos precisos (V2-022 / V2-024)
| id | canal | qué prueba | éxito |
|---|---|---|---|
| `search` | voz | búsqueda web ligera factual ("quién ganó la última carrera F1") | responde EN el turno un dato concreto, hablado, sin URLs/JSON; capa Google ~1-2s |
| `busqueda_web` | voz | dato de actualidad/tiempo dicho de viva voz (ciudad concreta) | dato exacto (weather widget) o síntesis de snippets; sin inventar; ~4-6s |

## Prioridad 1 — MÚSICA + RAILS + WIDGETS (V2-041 / V2-042)
| id | canal | qué prueba | éxito |
|---|---|---|---|
| `musica` | voz | "pon música" / "ponme a Frank Sinatra" + sube/siguiente/pausa | play_music (no web_search, no widget de vídeo); SIEMPRE suena (fallback GRATIS YouTube-audio oculto en widget `musica`, que se abre); controles actúan; traza: evento `music` + `rail` music.playing |
| `musica_difusa` | voz | pista VAGA ("esa que dice volare") → resolver; dar un dato al fallar → RETOMAR | cadena del rail (resolver→validar→actuar), anuncia qué pone; si falla, run AISLADO `sin_resolver` visible en el prompt («Rails en curso»), y el 2º intento usa la pista ENRIQUECIDA (no arranca de cero) |
| `musica_spotify_connect` | voz | "conéctame Spotify" | ABRE el widget `musica` con la tarjeta de conexión guiada; NO abre navegador ni inventa credenciales ni escala |
| `widget_conducciones` | voz | MOSTRAR + OPERAR datos + CREAR + CERRAR en una charla | cada conducción por su vía (rail fundacional V2-042): mostrar=canvas al instante; operar=`widget_data`→apply_action sin escalar (id correcto, no inventado); crear=escala UNA vez con id sensato; cerrar=`[[close:ID]]` correcto; sin widgets basura ni dobles workers |

## Prioridad 1 — Navegación web profunda / marketplace (INI-016, ✋ comparación)
| id | canal | qué prueba | éxito |
|---|---|---|---|
| `navegador_moto` | voz | "búscame una moto naked <3000 € cerca" → automate_web | escala al SlowBrain, abre Chromium backed en 2º plano (tarjeta de tarea), NO crea widget ni responde de memoria; resultado asíncrono con anuncios reales ✋ |
| `navegador_coche` | voz | "coche <5000 € y <250.000 km en Wallapop/coches.net" | igual: navega, EXTRAE anuncios reales (precio+km), top-3; sin autenticar (si pide login, lo dice) ✋ |
| `reserva_web` | voz | "resérvame cita para la ITV cuanto antes; hazlo tú en la web" (+ dale datos si pregunta) | ACCIÓN transaccional (bug ITV 2026-07-15): ROUTING → ESCALA (no web_search dando consejos en bucle; sin widget navegador en blanco); el worker CONDUCE la web, acepta cookies para avanzar, y PIDE los datos que falten (matrícula/estación/fecha) con worker_bridge ask en vez de dar vueltas o inventar. NO se exige cerrar reserva real |

## Prioridad 2 — Memoria (humo; la suite exhaustiva vive aparte en memory/)
| id | canal | qué prueba | éxito |
|---|---|---|---|
| `memory` | voz | "recuérdame que el coche está en el taller hasta el viernes" → luego "¿dónde está mi coche?" | guarda y hace recall correcto en el mismo hilo; maneja corrección |

## Prioridad 2 — Widgets (V2-023)
| id | canal | qué prueba | éxito |
|---|---|---|---|
| `widget` | voz | "muéstrame un reloj y luego el tiempo" | emite `[[show]]` de widgets existentes; NO crea widgets basura; idempotente |
| `mensajeria` | voz | "abre el widget de mensajería y dime cuántos importantes tengo + si WhatsApp/Telegram conectados" | MUESTRA el `mensajeria` EXISTENTE (regresión bug V2-023: jamás crear uno nuevo); da estado natural |
| `youtube_voice` | voz | re-simulación sesión 2026-07-15: montar widget YouTube (gol mano de Dios) → comentar ambiente → estado → MODIFICAR (pantalla completa + control por voz) → insistir → "cierra el resto menos youtube" | **1 solo worker/objetivo** (`task/dedup`, no 2º `task/start`, sin doble chip); **modificar≠crear** (toca `youtube`, sin id-basura); "cierra el resto" conserva youtube (`[[close:ID]]` uno-a-uno, no `[[close]]` global); voz AMBIENTE no actúa; hecho conocido→busca (≤1 aclaración); estado=paso+tiempo (no frase-loro); hay `perf func=turn` para diagnosticar. Fixes P0 `d78d457` + P1 `dc436cc`/`5367200`. Companion headless determinista: `python -m tests.voice.e2e.agent.youtube_flow_probe` |

## Prioridad 2 — Conectores y cluster
| id | canal | qué prueba | éxito |
|---|---|---|---|
| `conectores` | voz | "¿qué conectores tengo activos y funcionan?" | estado natural de WhatsApp/Telegram/cluster; sin JSON; sin abrir login por "conectado" (bug V2-023 corregido) |
| `websocket` | voz | "¿está abierto el canal del cluster MeshKore?" | responde en lenguaje natural (nunca JSON crudo) |

## Prioridad 3 — Conversación, razonamiento, canales de texto, agenda
| id | canal | qué prueba | éxito |
|---|---|---|---|
| `conversation` | voz | back-and-forth natural + despedida | coherente turno a turno, sin repetición robótica ni mutes |
| `complex_idea` | voz | planificar algo en 5-10 turnos (cena sorpresa) | mantiene contexto, propone pasos, ofrece agenda/recordatorios |
| `agenda` | voz | leer agenda + añadir cita mañana 17h + confirmar | lee, acepta el cambio, confirma (tag/widget de agenda) |
| `chat` | chat | pedir la hora POR TEXTO (data channel) | responde el texto igual que por voz |
| `paste` | paste | pegar bloque largo + "resúmelo en una línea" | ingiere el pegado y resume |
| `archivos` | paste | pegar un documento con un dato concreto → luego preguntar por ese dato | vía EPISÓDICA: ingiere y RECUERDA el dato después sin repetírselo; no inventa |

## Harness por PROBE (rápido, sin voz — headless, alto volumen)
Complementan los escenarios de voz de arriba. Usan el canal PROBE (`POST /api/flash/say`) → ejercitan el MISMO
FlashBrain/router/rails/tools/memoria-estado/Susurro sin STT/TTS. Ideales para barrer routing a escala.

| herramienta | qué hace | uso |
|---|---|---|
| `tests/voice/e2e/agent/domain_sea.py` | **Mar de testing por DOMINIOS** (routing): N parafraseos NATURALES por semilla (vía AIMLAPI) → probe → auto-marca fallos de routing por dominio. 16 dominios: mem·web·math·chat·show·close·**create**·**modify**·music·video·**latest** (V2-057)·**market** (idealista/coches.net/autoscout/wallapop/milanuncios/amazon → escalate)·deep·style·ml_en/ca/fr. | `PYTHONPATH=. .venv/bin/python tests/voice/e2e/agent/domain_sea.py all 5` (≈220 turnos) · o un dominio: `… domain_sea.py market 6` |
| `tests/voice/e2e/agent/deep_nav.py` | **Navegación REAL** (ejecución, V2-057): escala un objetivo de marketplace con `execute=true` → el server lanza un Brain Worker que CONDUCE el navegador contra el sitio VIVO → observa el timeline (fases·tocó el sitio·extrajo anuncios·entrega·verificación). LENTO, toca sitios vivos (1-3 min c/u) → pocos, como prueba e2e. | `PYTHONPATH=. .venv/bin/python tests/voice/e2e/agent/deep_nav.py idealista` · o `… deep_nav.py coches 150` · `all` para todos |
| `tests/voice/e2e/agent/chat_convo.py` | **Canal CHAT (voz OFF, V2-054)** — conversación MULTI-TURNO headless: sesión persistente del probe (la ventana se conserva) → verifica que la charla por TEXTO se mantiene COHERENTE, arrastra el CONTEXTO de turnos previos, no degenera/buclea, enruta un dato factual en medio → `search` y vuelve a charla, y responde rápido (< 3.5 s). Es el lado CEREBRO/CONVERSACIÓN del canal sin voz (el mecanismo audio-OFF a nivel LiveKit = escenario de voz, T1.4). Complementa al escenario single-shot `chat`. | `.venv/bin/python -m tests.voice.e2e.agent.chat_convo` · o hilos sueltos: `… -m tests.voice.e2e.agent.chat_convo smalltalk context` |

> **Doctrina (mar de testing, confirmada):** parchear verbo a verbo NO generaliza; ampliar verbos AMBIGUOS regresiona.
> El techo determinista (fraseo indirecto/deseo sin verbo — «me vendría bien un gadget», y elegir web_search sobre
> navegar un marketplace) es **territorio del Susurro** (F2/F3), no de más regex. El mar es la herramienta para no
> re-investigar: cada ronda arregla lo GENERALIZABLE (p. ej. sinónimos de widget panel/gadget + escalate-task de
> marketplace/informe en el backstop de promesa, V2-057 2026-07-21) y deja el resto marcado.

## Notas de mantenimiento
- Añadir un escenario: definirlo en `tests/voice/e2e/agent/scenarios.py` (dataclass `Scenario`) **y** aquí, en su grupo de
  prioridad, indicando ✋ si requiere comparación humana de datos.
- Rotación de la batería y del cron: `tests/voice/e2e/agent/run_battery.sh` (todos, con settle) y `tests/voice/e2e/agent/cron_tick.sh`
  (SCENARIOS[] round-robin). Mantener ambas listas al día si se añaden escenarios.
