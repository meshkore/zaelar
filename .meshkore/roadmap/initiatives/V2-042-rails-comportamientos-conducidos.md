# V2-042 — RAILS: comportamientos comunes CONDUCIDOS (patrón de orquestación del FlashBrain)

**Origen (operador, 2026-07-15):** al pedir la música difusa («alguien querrá escuchar una canción concreta pero no
nos dará el nombre exacto… buscarla, validarla y reproducirla; manejarlo por el ESTADO — que sepa qué buscamos, qué
se reproduce, y guardar el estado de esa búsqueda AISLADO hasta tenerla; y las reproducciones/artistas a la MEMORIA
para que zaelar nos conozca»), pidió **estudiar y FIJAR el patrón**: música, vídeo, estudios de datos, búsquedas
complejas en sites, mensajería, agendas, búsquedas recursivas (parte cron, parte búsqueda) «serán comportamientos
habituales y debemos ajustarnos a ellos». Y el naming es suyo: **RAILS** — «acciones que vamos a conducir de una
determinada forma» — con la idea de **modularizar, reducir prompts y dar visibilidad** («quizás son prompts que
deberían estar aislados como tools y ponerlos solo cuando hagan falta»).

## El patrón (5 primitivas)

Un **RAIL** = un comportamiento habitual con conducción predefinida. Cada rail aporta piezas MODULARES:

1. **Recursos CALIENTES en el arranque** — ya existía (V2-024, verificado en vivo: `prewarm browser_search OK` —
   el Chromium de búsqueda arranca con el sistema). Un rail declara qué necesita caliente; el prewarm lo absorbe.
2. **Cadena determinista resolver→validar→actuar EN CÓDIGO** — el FlashBrain sigue NO-razonador: él dispara la
   tool; el rail conduce (p.ej. `nucleo/flash/music_flow.py`). Los 2º pases de modelo (extraer/validar) reusan el
   modelo del turno YA pagado (patrón `web_search`).
3. **Runs vivos en el ESTADO** (`nucleo/rails.py` → `state.rails` → «Rails en curso» en el prompt de ambos
   cerebros): qué se busca, qué suena/corre, y los fallos **AISLADOOS `sin_resolver`** (label + intentos + TTL 15min)
   que el turno siguiente puede retomar con más datos («era de Sinatra»). Singleton por `kind`; observabilidad =
   evento `rail` en /debug por cada transición.
4. **Prompts aislados, SOLO cuando hacen falta** (idea del operador): cada rail registra su GUÍA en
   `rails._GUIDANCE` y `prompt._rails_directive()` la inyecta ÚNICAMENTE mientras hay un run vivo en el estado que
   aplica — cero coste de prompt en reposo (mismo patrón situacional que las tools V2-035 y `_workers_directive`).
5. **Writeback tipado a MEMORIA** — outcomes por la vía única `memory.ingest_message(source=<rail>, entity=…)`
   → historial consultable (`recent_by_source("music")`) + píldoras durables que el retriever/recall usan
   («pon algo que me guste») + el CORAZÓN infiere gustos/intereses con el tiempo.

**Estado vs memoria (aclaración del operador, 2026-07-15):** un run vivo genera SIEMPRE **información de ESTADO**
(`state.rails`, efímera, se limpia en reset) y **OPCIONALMENTE memoria PERMANENTE** — de CORTO o LARGO plazo según
el outcome (`ingest_message` con `durable=False`→CORTO / `durable=True`→mid/LARGO). No todo run deja huella durable:
una búsqueda `sin_resolver` no escribe nada permanente; una reproducción sí (gustos).

**Recurrencia** (búsquedas recursivas cron+búsqueda): el `scheduler` crea/renueva runs de un rail en cada tick —
documentado como parte del patrón; se cablea por-dominio cuando llegue (no se construyó maquinaria especulativa).

## 1ª instanciación: MÚSICA DIFUSA (`nucleo/flash/music_flow.py`, sobre V2-041)

`play_music("esa que dice vuela conmigo")` →
1. intento directo (`music.control` — los buscadores de proveedor ya toleran lo difuso);
2. si `no_track`: run `music.search` (buscando, bump intentos) + **websearch con el Chromium CALIENTE**;
3. 2º pase del modelo del turno: extraer `Artista - Título` canónico (formato estricto | NO);
4. reintento con el canónico → si suena: run `music.search` resuelto (desaparece), run `music.playing` (qué suena,
   vía qué proveedor), **writeback** `[music] Frank Sinatra: Sonó «Come Fly With Me» (la pidió como: …)` y la voz
   ANUNCIA qué suena (validación por anuncio: si no era, el operador corrige y ese turno reintenta con más datos);
5. si no: run queda `sin_resolver` AISLADO + la voz pide un dato más; el rail inyecta su guía («si aporta un dato,
   re-llama a play_music con la query ENRIQUECIDA») SOLO mientras ese estado exista.

## Los WIDGETS son el rail FUNDACIONAL (aclaración del operador, 2026-07-15)

El manejo de widgets (crear, modificar, operar datos, borrar) **ES un rail** — el primero, construido ANTES de que
el patrón tuviera nombre, y ya cumple las 4 piezas con su propia maquinaria: (1) cadenas deterministas en código
(`widgets/actions.classify()` FAST/CONFIRM/ESCALATE · `widgets/refs.resolve()` item-en-lenguaje-natural→id real con
pregunta si ambiguo · confirm de borrado V2-017 · show-guard/canvas_verb), (2) sus tools (`widget_data`,
`delete_widget`, `confirm_widget_delete` + escalate para CÓDIGO), (3) estado vivo (`open_widgets` + «CONFIRMACIÓN
PENDIENTE» + sesiones de generación vía dispatch), (4) writeback a memoria (alta `record_created` + LÁPIDA al
borrar, `zaelar-memory.md §Acciones↔memoria`). **Unificación = taxonómica, no de código**: no se reescribe la
maquinaria que ya funciona sobre `rails.py`; las conducciones NUEVAS de widgets que crucen turnos (p.ej. una
aclaración de creación pendiente) sí usarán runs de rails, y si algún canal viejo converge (confirm-pending como
run `widget.confirm`) será oportunista, no un refactor.

**El rail de widgets son en realidad TRES conducciones distintas** (aclaración del operador, 2026-07-15 — «operar
con ellos es diferente a crearlos o modificarlos o abrirlos y cerrarlos»), las tres ya especificadas y separadas
EN CÓDIGO:

1. **OPERAR/USAR un widget** (la del día a día): cada widget es un «objeto global» autónomo que declara sus
   FUNCIONES (`manifest.json §actions`: nombre+desc+payload) y sus INSTRUCCIONES de conducción (`§usage`) —
   **modulares DENTRO de cada widget**, exactamente la idea del operador; el gate del generador
   (`_validate_actions_sync`) obliga a que la declaración y el `apply_action` real casen. El FlashBrain las ve vía
   `widgets/brief.for_prompt(open_ids)` (acciones inline; items vivos SOLO si está abierto — prompt aislado
   por-widget, mismo espíritu que la guía de rails) y opera con la tool `widget_data` → `apply_action()` (el MISMO
   código que los botones), con gate FAST/CONFIRM (V2-025) y referencia a item en lenguaje natural resuelta a id
   real (`refs.resolve`, V2-026; pregunta si es ambiguo). **La parte de MEMORIA COMÚN**: un widget vuelca lo
   durable SOLO por las vías sancionadas (`ctx.remember`/`ctx.ingest` en background V2-034; `memory.write` con
   slot) — nunca BD directa.
2. **CREAR/MODIFICAR el CÓDIGO** de un widget → escalate a worker (generator_session), alta/LÁPIDA en memoria.
3. **ABRIR/CERRAR/BORRAR en el canvas** → tags `[[show]]`/`[[close]]` + `delete_widget` con confirmación (V2-017).

## Dominios sobre el mismo patrón (mapa)

| Dominio | cadena | runs | writeback |
|---|---|---|---|
| **widgets (FUNDACIONAL, ya construido)** | actions.classify + refs.resolve + confirm | open_widgets · confirm-pending · sessions | alta/LÁPIDA (V2-017) |
| vídeo | resolver título→videoId→widget youtube | video.search/playing | source="video" |
| estudio de datos | escalar a worker + fases | (ya: sessions de dispatch) | resultado OK → píldora (ya, V2-036) |
| búsqueda compleja en site | navegador + extract_listings | site.search sin_resolver reanudable | source="research" |
| mensajería | (ya: triaje en widget backed) | msg.pending | (ya: ingest_message) |
| agenda/calendario | widget_data + refs | agenda.confirm pendiente | (ya: auto-ingest) |
| búsqueda recursiva | scheduler crea run cada tick + websearch | watch.<tema> con últimos hallazgos | source="watch", slot evolutivo |

## Invariantes / cuidado
- El FlashBrain sigue **NO-razonador**: los rails conducen EN CÓDIGO; el modelo solo dispara tools y habla.
- **V2-011 intacto**: todo I/O de un rail va off-loop (`to_thread`); `rails.project()` es µs y off-loop; la
  lectura del estado va por `memory_cache` como siempre.
- Los runs son **estado de sesión**, no memoria durable: `reset_all` los limpia (`rails.clear_all`); lo durable
  va por el writeback tipado.
- SOLO DATOS en el ESTADO compartido (auditoría 2026-07-14): la guía/directiva por rail es capa del FlashBrain
  (`_rails_directive`), no de la memoria.

## Bitácora
- **2026-07-15** — Estudio (prewarm/estado/memoria: casi todo el sustrato existía; faltaba la abstracción) +
  patrón fijado + construidas las piezas: `nucleo/rails.py` (registro de runs + `prompt_lines()` + evento `rail`),
  `state.rails` + render «Rails en curso» en `compose_state`, `nucleo/flash/music_flow.py` (cadena música +
  writeback `source="music"`), cableado en el provider de voz (extractor = 2º pase del modelo del turno) +
  `_rails_directive` en el prompt + `reset_all` limpia runs. Naming «rails» y «prompts aislados solo-cuando-vivos»
  = ideas del operador, adoptadas. Tests: 14 nuevos (rails + music_flow) verdes; regresión nucleo/connectors/
  widgets 196 verdes; suites memoria verdes (1 fallo PRE-existente `test_degraded_embedding_backend_warns`,
  independiente — depende del entorno Ollama). **Pendiente:** probar la cadena difusa en vivo; siguientes rails
  (vídeo, watch recursivo) cuando toquen.
