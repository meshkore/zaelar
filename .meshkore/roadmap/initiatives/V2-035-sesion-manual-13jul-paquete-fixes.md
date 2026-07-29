# V2-035 — Paquete de fixes de la sesión manual 2026-07-13 (10:19–11:03)

Diagnóstico completo de la observabilidad de la sesión (server con Haiku 4.5 vivo). Estado: **algunos fixes YA
aplicados en este paquete; el resto, plan priorizado**. El operador va añadiendo subtareas → todo va aquí.

## ✅ YA arreglado en este paquete (2026-07-13)

- **Widgets que "no cargan" desaparecían en SILENCIO.** El operador pidió la agenda 4 veces y "no la veía": el
  backend estaba 100% sano (catálogo, `/widgets/agenda/data` 200, `widget.js` 200, evento `show` con id correcto),
  pero `desktop.show()` **auto-cerraba la tarjeta en el `catch`** de render (o `data.error`) → se creaba y se
  esfumaba, sin dejar rastro en ningún log. FIX (`frontend/app/widgets/desktop.js::_mountError`): un widget que
  falla al montar muestra un **estado de ERROR VISIBLE** en la tarjeta Y lo **reporta a observabilidad**
  (`/api/client-log` → evento `client` en /debug). Deja de ser invisible → la próxima sesión captura el error de
  render REAL de la agenda. (La causa exacta del fallo de render de agenda necesita ese dato del navegador.)
- **Turnos MUDOS al mostrar/cerrar un widget.** El modelo emitía `[[show:agenda]]` sin hablar → turno sin voz; el
  operador ni oía ni veía nada → "está roto". FIX (`nucleo.py`): si un show/close de canvas no lleva frase, se dice
  el `show_ack` ("Aquí lo tienes.") — nunca mudo al abrir/cerrar.

## 🔴 P0 — Búsqueda por navegador (Chromium headless): INTELIGENCIA + OBSERVABILIDAD (subtarea del operador)

Síntoma: pedí una **moto de enduro ~300cc 4T para principiante** y me devolvió Keeway Superlight 125, Benelli BN
302, Yamaha MT-125 — **motos de calle 125, nada de enduro**. Antes funcionaba depurando bien el término en Wallapop.

Causas (traza):
1. **El FlashBrain PERDIÓ la restricción "enduro" al escalar.** El operador dijo "la CILINDRADA no me interesa
   tanto, que sea para principiante" → el goal escalado quedó *"motos para principiantes, sin especificar
   cilindrada"* — se cayó **enduro** (que NO se había retirado). El modelo sobre-generalizó "cilindrada no importa"
   a "categoría no importa". → El goal debe conservar TODAS las restricciones vigentes (enduro) y soltar solo la
   retirada (cilindrada exacta).
2. **Query de Wallapop demasiado genérica** ("moto principiante") → categoría equivocada. El agente del navegador
   debe **depurar el término** (categoría motos + "enduro" + rango cc + precio) y usar la **URL de búsqueda con
   filtros** (categoría/precio/orden) antes de clicar a ciegas — lo hizo pero TARDE (min 6) y tras muchos atascos.
3. **Lento y con atascos**: navigate→type→click ref 17 repetido, `task_stuck`→VISIÓN ×4, ~7 min sin cerrar. El
   bucle DOM→visión (modelo del navegador = haiku) se pierde en la UI de Wallapop.

Trabajo (a diseñar en la funcionalidad de búsqueda del navegador):
- **Conservar las restricciones del operador** al componer el goal (no soltar "enduro").
- **Refinar el término + usar la URL de filtros de Wallapop** de entrada (categoría 14000 motos, keywords
  depuradas, `max_sale_price`, orden), en vez de teclear en la caja y navegar a mano.
- **Parámetro base LOCAL vs AMPLIO**: los procesos de búsqueda/estudio deben DECIDIR (o preguntar) si la búsqueda es
  **geográficamente local** (cerca de donde vive el operador → filtro de ubicación/orden por distancia) o **amplia**.
  Debe ser un parámetro del sistema para búsquedas de navegador y de estudios/informes.
- **Autenticación**: decidir si hace falta login para el sitio/tarea (a veces sí, a veces no) como parte del plan.
- **OBSERVABILIDAD PROFUNDA de la sesión de navegador** (requisito del operador — poder repasar qué hizo): registrar
  y poder revisar **la query depurada lanzada, la URL/filtros, los anuncios EXTRAÍDOS (candidatos), cuáles se
  quedan/descartan y POR QUÉ, qué fichas abrió, si aplicó filtro geográfico, el ranking final y su justificación**.
  Hoy se ven `task_step`/`task_stuck`/`navigate`; falta la capa de RAZONAMIENTO de resultados (qué/por qué).

## 🟠 P1 — otros hallazgos de la sesión

- **Mensajería no renderiza IMÁGENES** (WhatsApp de Eva: "imagen recibida" pero no se ve la imagen). El operador lo
  pidió y se escaló al SlowBrain (modify del widget) — confirmar que esa tarea de código terminó y renderiza el
  binario (endpoint `asset`), no solo el texto.
- **TTS Kokoro Metal peta MUCHO** (mlx-audio `broadcast_shapes`, ~decenas de veces; cae a onnx→Kokoro-FastAPI). Es la
  causa real de "voz lenta" y de algún turno mudo. Evaluar: (a) fijar el TTS por defecto a la ruta estable (onnx/CPU
  o Cartesia) mientras el bug de mlx-audio persista, o (b) hacer el fallback más barato. Ver CLAUDE.md §TTS Metal.
- **Escalada MAL enrutada de "muéstrame/carga el widget de X"**: "no veo el widget de la agenda" se escaló al
  SlowBrain que etiquetó *"Creando un widget…"* para un widget que YA EXISTE. Mostrar/cargar un widget existente es
  DETERMINISTA del FlashBrain (`[[show:agenda]]`), nunca una escalada a código. Ampliar los verbos del show-guard
  ("carga/cargar/arranca/no veo/no aparece/no se ve el widget de X") para resolverlo sin escalar.

## 🟠 P1 — añadidos por el operador (2026-07-13, 2ª tanda)

- **Tarjeta del navegador SIEMPRE muestra la TAREA PRINCIPAL bajo la captura.** El widget (`navegador::tN`) tiene la
  ventanita de captura arriba; debajo debe mantenerse VISIBLE el objetivo actual ("buscar moto de enduro 300cc 4T
  para principiante"). Así, si el modelo lo cambia (a "moto cualquiera"), el operador lo VE y puede corregir por voz
  ("te dije enduro, no una moto cualquiera") → el cerebro corrige la MISMA búsqueda (usa la continuidad de V2-032:
  refina la tarea viva, no abre otra). data.py ya expone `goal`; falta que widget.js lo pinte prominente y estable.
- **Enlace Flash→Slow TRANSPARENTE en la voz.** Al operador NO le interesa cuántas partes tiene el cerebro. Prohibido
  decir "escalo/SlowBrain/cerebro lento/cerebro profundo". El FlashBrain gestiona el enlace de forma invisible: "vale,
  me pongo con ello, tardará un poco" / "arranco tu solicitud y lo verás actualizado en el widget". Fix en la
  descripción de `escalate_to_slowbrain` (router.py — hoy dice literalmente "Delega al SlowBrain…" y el modelo lo
  parrotea) + `langs.filler_holding`/`persona` (quitar "cerebro lento") + regla en el prompt (como la de "nunca
  expongas las capas internas de memoria"). Espejo de esa regla, para la arquitectura del cerebro.
- **Snippets de PROCESOS EN LA SOMBRA alrededor del orbe.** Los procesos SIN reflejo propio en pantalla —modificar/
  crear/programar un widget (código del SlowBrain)— deben mostrar pequeños snippets abajo, a izquierda y derecha del
  orbe (SIN pisar el texto de subtítulos): "programando el widget…", "modificando…", "creando…". Ya existe el chip de
  actividad (`dispatch._emit_activity` → evento `task`); falta cablearlo a esa zona del orbe y que se refleje perfecto
  (un widget de búsqueda ya se ve trabajar en su tarjeta; esto es para lo que NO tiene tarjeta).
- **TTS fiable — proveedor cloud bueno y económico.** ✅ HECHO: **ElevenLabs** wired como provider
  (`voice/engine/speech/tts/elevenlabs.py`, modelo `eleven_flash_v2_5` barato/rápido/multilingüe), clave en el
  credential store, validado end-to-end (síntesis real). Se activa con ⚙ `tts_provider=elevenlabs` o
  `ZAELAR_TTS=elevenlabs`; el local (Kokoro) queda como fallback. Pendiente opcional: exponer las voces de ElevenLabs
  en el selector del ⚙ (hoy por `ELEVENLABS_VOICE_ID`/default) y elegir/curar una voz ES concreta.

## 🟠 P1 — modelo del FlashBrain: usar SIEMPRE el flash MÁS NUEVO + comparar COSTE (operador, 2026-07-13)

Regla del operador: usar SIEMPRE la ÚLTIMA versión flash de cada familia (son flash = rápidos Y los más listos); NO
elegir modelos por memoria (se quedan anticuados). **De momento se queda Haiku 4.5**, pero hay que comparar coste y
probar los flash más nuevos. **Candidatos NO-razonadores del catálogo AIMLAPI EN VIVO (consultado hoy, autoritativo):**
- **grok**: `x-ai/grok-4-1-fast-non-reasoning` ← MÁS NUEVO que el `grok-4-fast-non-reasoning` que usábamos (grok 4.1
  fast). También `grok-4-fast-non-reasoning`.
- **anthropic**: `claude-haiku-4.5` (actual titular) / `claude-haiku-latest`.
- **gemini**: confirmar el id EXACTO del flash más nuevo (el catálogo trae familia gemini-2/3; el operador menciona
  "3.5 flash" — verificar el id real disponible, NO asumir).
- **deepseek**: `deepseek-v4-flash` (flash no-razonador).
- **openai**: `gpt-5-nano` / `gpt-5-mini` / `gpt-5.4-nano` / `gpt-5.4-mini` (rápidos/baratos).
- otros: `z-ai/glm-4.7-flash`, `rekaai/reka-flash-3`, `stepfun/step-3.7-flash`.

TAREA: (1) traer PRECIOS ACTUALES (input/output por 1M tok) de AIMLAPI/proveedor — NUNCA de memoria; (2) A/B con el
canal de prueba (`make flash --model`) de los flash más nuevos (grok-4.1-fast, gemini flash último, deepseek-v4-flash,
gpt-5-nano/mini) en inteligencia + latencia + coste; (3) recomendar titular por relación calidad/latencia/coste. El
canal de prueba ya soporta `model=` para el A/B. Latencia medida hoy: grok-4-fast p50 ~1.57s vs haiku-4.5 ~1.75s
(diferencia pequeña; haiku más consistente).

## 🔬 2ª SESIÓN MANUAL (13:04–13:15, 29 turnos) — el paquete V2-035 ROMPIÓ la acción. Diagnóstico + plan.

Tras aplicar el paquete de arriba, el operador probó en vivo y **fue peor que nunca**: no se arrancó **ni un solo
widget**, no se buscó nada de verdad. Análisis de `timeline-latest.jsonl` (memoria/observabilidad recién reseteadas
→ el timeline es exactamente esta sesión).

### Fallos OBSERVADOS (datos duros, no percepción)
1. **CERO ACCIÓN — el fallo capital.** En 29 turnos de asistente: `escalated=0`, `searched=1`. El FlashBrain dijo
   "me pongo con ello" / "escalarlo de verdad" **~8 veces** pero **no llamó a NINGUNA tool**. No abrió ningún widget,
   no arrancó el navegador. La única `web_search` (13:12, forzada tras el enfado del operador) devolvió snippets
   crudos inútiles.
2. **Latencia ~4s constante.** LLM TTFT (Haiku/AIMLAPI) 1.1–4.9s (muchos 3s+); **recall que hace TIMEOUT de 2s**
   (`recall_fired:True, recall_timeout:True, prompt_ms≈2003`) en ~10 turnos; STT `dur` hasta 8s; EOU spikes 8.6 / 5.7 / 2.2s.
3. **Voz con DRIFT de acento** — inglés/portugués pronunciando español, sin venir a cuento (el operador lo anotó 2 veces).
4. **Barge-in no corta la voz** en frío ("interrumpo, no se para"); mejora al calentar.
5. **web_search de investigación inútil** — snippets orgánicos de Google (`ai:False, n:5`) para "mejor moto enduro
   principiantes"; el modelo admitió "los resultados no me muestran específicamente cuál es". + fallo de ORQUESTACIÓN
   (pidió al operador presupuesto/zona/marca en vez de resolver él el CONOCIMIENTO).

### Causas RAÍZ (verificadas en el código, no hipótesis)
- **#1 CERO ACCIÓN = REGRESIÓN de HOY, commit `3425afc` (V2-035, 11:53) — el mismo día.** La regla de transparencia
  ("no digas SlowBrain/escalar; di que te pones con ello") se colocó en el sitio equivocado:
  - Como **cláusula FINAL de la `description` de `escalate_to_slowbrain`** (`nucleo/flash/router.py:65-67`). La última
    instrucción de la tool le dice al modelo QUÉ DECIR, no CUÁNDO LLAMAR → el modelo pequeño verbaliza el filler y da
    el turno por cumplido.
  - La **`mission`** (`voice/engine/core/langs.py:62-72`) se reescribió de *"delegas en tu cerebro lento lo que lleva
    trabajo"* → *"le dices con naturalidad que te pones con ello"*. Describe el comportamiento como **DECIR**, no como
    **LLAMAR una función**; no menciona el mecanismo en absoluto.
  - Agravado por la regla NO-DUPLICAR (`router.py:59-63` + `prompt.py:357-361`) que empuja a "solo dilo, no vuelvas
    a escalar".
  - El plumbing de tool-calling está **intacto** (dialog no interfiere; `tool_choice=auto` OK). **NO es culpa de Haiku.**
- **#2 LATENCIA = contención de GPU Metal + recall mal calibrado.**
  - `needs_recall` se **sobre-dispara**: `_TRIVIAL_RE` anclado a `$` deja pasar "qué tal colegita"; catch-all de
    pregunta (`prompt.py:156-159`) + `_WH_START_RE`; stems de categoría sueltos (`salud|trabajo|comida…`). Dispara en
    charla normal.
  - Cuando dispara, el **embedding de la query** (embeddinggemma vía Ollama, Metal — `memory/retriever.py:198` →
    `memory/embeddings.py:85-105`) ha sido **desalojado de VRAM** por el CORAZÓN `qwen2.5:7b` y compite con whisper-STT
    → recarga >2s → **timeout** (`nucleo.py:190`, `ZAELAR_RECALL_BUDGET_MS=2000`). El reranker jina NO interviene con
    memoria vacía. Resultado: +2s TIRADOS por turno.
  - TTFT de Haiku vía AIMLAPI variable (Cloudflare) 1.1–4.9s; STT whisper-metal frío/contención hasta 8s.
  - **Hilo común: demasiados modelos peleando por Metal** — whisper-STT + embeddinggemma + qwen2.5:7b (CORAZÓN) +
    jina reranker (+ Kokoro cuando estuvo). TTS ya salió de Metal (cloud), bien.
- **#3 VOZ:** `eleven_flash_v2_5` es el modelo multilingüe **menos estable** + **NO hay voz castellana concreta
  seleccionada** (`settings.json assistant_voice="ef_dora"` es un id de Kokoro que ElevenLabs ignora → voz por
  defecto anglo). Flash canjea calidad por velocidad → drift arbitrario.
- **#4 BARGE-IN:** downstream de #2 (STT/EOU lentos en frío → el turn-detector llega tarde). No es regresión de config.
- **#5 BÚSQUEDA:** snippets orgánicos no bastan para una pregunta de INVESTIGACIÓN; hacía falta buscador-IA
  (answer-mode) o escalar a informe. + fallo de orquestación (resolver el conocimiento uno mismo vs preguntar decisiones).

### PLAN DE CORRECCIÓN (por prioridad)
- **P0 — Revertir la regresión de acción (lo que rompió todo). ~30 min, sin riesgo.**
  1. Sacar la regla de transparencia de la `description` de `escalate_to_slowbrain`; que termine en acción imperativa
     ("Llámalo YA; lo que digas es secundario, viene después").
  2. Reponer en la `mission` el MECANISMO: ante trabajo, **LLAMAS a la función** (no "dices"). Mover la transparencia
     a una regla de ESTILO separada (cómo hablar de una tarea ya lanzada), no como objetivo del turno.
  3. Revisar NO-DUPLICAR para que solo suprima escaladas con tarea REAL en curso.
  4. Verificar con el canal de prueba (`make flash`): "móntame una búsqueda de moto de enduro" → `escalate_to_slowbrain`
     con request que conserva "enduro"; "arranca el widget" → escala; charla → NO escala.
- **P1 — Latencia / contención GPU. ~1-2h.**
  1. **Embedding de la query del recall FUERA de la GPU** (fastembed CPU) → el recall no espera desalojo de Metal.
  2. Endurecer `needs_recall` (no disparar en turnos cortos/WH sin sustancia). Menos recalls → menos timeouts.
  3. Bajar `ZAELAR_RECALL_BUDGET_MS` mientras (recorta el desperdicio).
  4. CORAZÓN `qwen2.5:7b`: que no desaloje embeddinggemma (residencia / tamaño / scheduling).
  5. Instrumentar /debug: separar TTFT-modelo vs recall vs STT (no volver a confundir latencias).
- **P2 — Voz fiable (DECISIÓN del operador).**
  1. ElevenLabs: `eleven_flash_v2_5` → `eleven_turbo_v2_5`/`eleven_multilingual_v2` (más estable) + **seleccionar una
     voz castellana nativa concreta**. A/B de estabilidad de acento.
  2. Si persiste el drift: la voz más estable que teníamos es **Cartesia**, pero `CARTESIA_API_KEY` está **VACÍA** →
     hace falta que el operador la aporte para volver.
  3. Kokoro local = fallback offline (crashea por mlx-audio; no titular).
  4. No se puede leer crédito de ElevenLabs (key scoped solo-TTS) ni de AIMLAPI vía API; los modelos responden → hay
     crédito, pero conviene mirar los dashboards. El coste importa.
- **P3 — Orquestación + búsqueda (inteligencia del FlashBrain). Diseño.**
  1. Regla de orquestación: distinguir CONOCIMIENTO que debe averiguar él (buscar con IA / escalar a investigación)
     vs DECISIÓN del operador (presupuesto, zona) que sí pregunta.
  2. web_search de investigación → preferir capa answer-IA o escalar a informe, no quedarse con snippets crudos.
  3. AQUÍ probar los flash más nuevos (grok-4.1-fast, gemini flash último, deepseek-v4-flash) con el prompt YA
     arreglado, por calidad de orquestación + latencia + coste. **Haiku de momento.**
- **P4 — Re-test.** Canal de prueba headless (routing/orquestación) + sesión de voz e2e (latencia/voz/barge-in).

## Cómo se prueba
Canal rápido (`make flash`) para el FlashBrain (goal que conserva enduro; show de widget no escala). La búsqueda de
navegador y el render de agenda/imagen necesitan el e2e con navegador vivo (o el visor de observabilidad de la
sesión de navegador, una vez ampliado). Reset de cero con `make reset`.

## ✅ Sesión manual 2026-07-14 (~20:43) — diálogo absurdo + circuito de corto plazo

**Síntoma (transcripción leída turno a turno):** (1) zaelar "abría" el widget de Proyectos sin que se lo pidieran
y **negaba** conocerlo; (2) al preguntarle *por qué* lo abrió, respondía sobre **web_search** (tema del turno
anterior) — diálogo absurdo; (3) **no sabía el nombre** del operador aunque estaba en el estado, de forma
**intermitente** ("eres Ricard" y "no sé quién eres" en la misma sesión).

**Causas raíz (confirmadas con datos, no suposición):**
- **Proyectos "abierto solo":** zaelar NO lo abrió (cero `show:proyectos` en el timeline) — estaba restaurado del
  `localStorage`. El servidor tenía `open_widgets=['mensajeria','results']` (leído de la BD) mientras la pantalla
  mostraba Proyectos → **estado DESINCRONIZADO del DOM**. Causa: el frontend solo re-reportaba el canvas al
  *cambiarlo*; al **reiniciar el server con la página abierta**, `open_widgets` quedó obsoleto y nadie lo re-empujó.
- **Nombre intermitente:** el estado SÍ viaja (verificado: "Ricard" en el prompt real). El bug estaba en
  `memory_cache._store`: cuando `compose_state()` fallaba un instante (BD bajo contención en sesiones con muchas
  escrituras) devolvía `('','')` y **pisaba el bloque bueno con vacío** → turnos sin nombre.
- **Diálogo absurdo:** anclaje de tema del FlashBrain (Haiku) + negación por estado erróneo.

**Fixes aplicados (código + verificado con probe):**
- **Fix 1 — reconciliación de canvas al (re)conectar** (`frontend/app/services/session-lk.js`): al conectar la
  sesión el frontend re-reporta su set REAL de widgets abiertos → cura la desincronización tras cualquier reinicio.
- **Fix 2 — regla de prompt** (`nucleo/flash/prompt.py`): la línea «Widgets ABIERTOS» del estado ES la verdad de la
  pantalla; si preguntan por un widget que no abrió este turno, no lo niega (dice que ya estaba, ofrece cerrar); y
  responde a lo que se pregunta AHORA, no al tema anterior. Verificado: T2 deja de reciclar web_search.
- **CIRCUITO DE CORTO PLAZO (A+B+C)** — el "circuito de interacción con el operador" que faltaba:
  - **A. Suelo de identidad sagrado** (`nucleo/flash/memory_cache._store`): nunca sobrescribe estado bueno con vacío.
  - **B. Ventana sembrada** (`memory.recent_window` → `brain._window`, voz + probe): la ventana de diálogo se
    siembra del buffer conversacional persistente al arrancar → no se pierde "de qué hablábamos" al reiniciar.
  - **C. 2º pase de corto plazo** (`prompt.needs_recent`→`compose_recent_block`, voz + probe): al referenciar lo
    reciente ("lo que te dije antes", "repite eso"), inyecta el buffer AMPLIADO verbatim fuera del event loop; la
    charla normal se queda ligera. Gating F/T/F verificado, coste ~1.4ms.
- **Doc:** `.meshkore/docs/architecture/zaelar-memory.md` (reader `recent_window` + §Circuito de corto plazo).

**Verificación:** 27 tests verdes (prompt/memory_cache/compose_state); probe en vivo — identidad sólida, T2
recupera el intercambio reciente exacto, charla normal no dispara el 2º pase.

## ✅ Latencia + observabilidad + optimización de tools (2026-07-14)

Tras un test de voz e2e a ~9.6s/turno, se estudió la latencia (el TTFT del modelo NO era el villano: Haiku
caliente 1.2s; los picos = cold-start + solapamiento + contención). Plan por fases, TODO con observabilidad como
premisa (totalizadores de tamaño/tokens para distinguir «lento por el modelo» de «lento por prompt gigante»):

- **FASE 0 — observabilidad**: `fast_client` emite tokens in/out (reales del proveedor si vienen, si no est.), chars
  exactos, nº tools + tools_chars, tok/s, cold_estimate, y desglose de QUÉ infla el prompt (sz_memory/recent/recall/
  resources/live). Fluye al evento `reply`, al `timing`, al probe (`make flash` lo imprime) y al DebugPanel (chip
  in→out tok, ámbar si el prompt es gordo).
- **FASE 1 — cold-start**: cliente httpx con keepalive 1800s (antes ~5s → la conexión prewarmeada moría antes del 1er
  turno). Prewarm con la FORMA REAL (prompt+tools). Eventos `prewarm` observables. Flag cold/gap por turno. Medido:
  tras 22s de hueco el turno sale cold=False (conexión reusada).
- **FASE 2 — solapamiento/zombie**: supresión de ECO determinista (el mic recaptura el TTS de zaelar como turno →
  se descartaba respondiéndose a sí mismo); cancelación por barge-in observable (no reinyecta respuesta vieja).
- **FASE 3 — contención**: tracker `busy` (corazon/embed/rerank) en el observer; el turno adjunta `busy_at_start`/
  `contended` al `reply` → correlaciona si el TTFT (cloud) sube bajo carga LOCAL (⇒ sería CPU/event-loop, no GPU).
- **FASE 4 — bench de inteligencia**: `tester/model_bench.py` + 5 turnos DUROS (meta/contradicción/no-buscar/
  no-actuar/introspección) puntuados APARTE del TTFT (`🧠 intel`) + tamaño de prompt por turno.
- **FASE 5 — optimización de tools**: el catálogo pesaba 11.313 chars (descripciones-ensayo con referencias cruzadas
  + 2 tools situacionales enviadas siempre). Descripciones condensadas (−34%, conservando reglas de bugs) + SET
  CONTEXTUAL (`router.tools(context)`: omite confirm_widget_delete/login_done si no aplican). Turno normal
  11.313→6.263 chars (−45%), input ~4.744→~3.480 tok. Routing verificado intacto (chat/search/widget/meta).
- **Documentación de tools (canónica)**: la tool `escalate_to_slowbrain` era naming LEGADO (el SlowBrain-cerebro se
  disolvió en V2-036; hoy LANZA un worker headless) → descripción y docstrings actualizados. **Doc canónica del
  catálogo = `zaelar-architecture.md §8`**, enumerado también en el diagrama `/architecture` (pestaña FlashBrain),
  con punteros desde `CLAUDE.md` y `router.py`, y REGLA de cross-ref en `zaelar-docs-sync.md §Tools`.

Verificación: 64 tests flash verdes; probe en vivo (routing + totalizadores); página `/architecture` sirve la tabla.

## ✅ Sesión manual 2026-07-14 12:07-12:14 — 4 fixes de raíz (voz + cierre + agenda + estilo)

Leída la sesión turno a turno (la observabilidad de FASE 3 lo probó). Problemas y fixes:

- **FIX 1 (EL corte de voz) — CORAZÓN apilándose en la GPU.** El destilador de memoria (LLM local) se disparaba en
  CADA turno SIN límite → 15-29s apilados en la GPU Metal (medido) → asfixiaba STT/TTS → la voz se cortaba a media
  frase. Fix (`nucleo/mem_processor.py`): **cap de concurrencia a 1** (`asyncio.Semaphore`, `MEM_PROCESSOR_CONCURRENCY`)
  con **SKIP-si-ocupado** (el turno cae a la heurística; el buffer conversacional ya tiene el crudo) + **modelo 3b**
  por defecto (antes 14b; contención breve) + timeout 30→20s. Credential store bajado 7b→3b. Verificado: ráfaga de
  4 turnos → 3 SKIP (no pileup). Evento observable `CORAZÓN … SKIP`.
- **FIX 2 — `[[close]]` no cerraba.** Repetía el close ~6 veces y la agenda seguía en pantalla. Causa: `close/closeAll`
  solo tocaban `this.wins`; una tarjeta HUÉRFANA (fuera de wins tras reconexión/reinicio) se ignoraba. Fix
  (`desktop.js`): `closeAll` BARRE el DOM (`.hb-win`) + limpia `wins` + borra `localStorage` (que un restore no la
  reviva) + reporta canvas vacío; `close(id)` cae a buscar la tarjeta huérfana por `data-wid`.
- **FIX 3 — quitar item de agenda ESCALABA.** "quítalo para siempre / todos los días" → el modelo escalaba (creía
  código) + gate de irreversibilidad + minutos; y elegía `drop_project` para un descanso (es `drop`) → ref sin
  resolver. Fix (`router.py` escalate desc): quitar/marcar/aplazar un item de widget —aunque diga "para siempre/
  recurrente"— es widget_data con la acción del widget, NO escala ni pide confirmación. Verificado: → widget_data.
- **FIX 4 — estilo + disciplina.** (a) Prompt (`prompt.py` ops): ante una orden, ACTÚA y confirma en 1 frase; no
  disculparse en bucle, no narrar, no repetir "tienes razón". (b) Mis reinicios cayeron en mitad de su sesión
  (kickoff/prewarm) → memoria de disciplina: comprobar `/api/status` voice.state ANTES de reiniciar; no reiniciar en
  vivo.

Verificación: 26 tests flash verdes; probe en vivo (routing widget_data/escalate correcto, SKIP anti-pileup);
cierre robusto por node-check. Voz off comprobada antes de reiniciar.
