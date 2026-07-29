# V2-046 — «Sistema arena»: rails/widgets/tools auto-generados, genética y reglas (ANÁLISIS + PLAN)

**Origen (operador, 2026-07-16; encargo completo en `V2-046-PROMPT-encargo-sistema-arena.md`):** el detonante fue
V2-045 — `play_video` entró como tool NATIVA para arreglar un P1 (el no-razonador confundía vídeo con música y la
prosa no lo movía). Fix táctico correcto, problema estratégico destapado: **cada capacidad nueva ha necesitado que
un desarrollador hardcodee una tool + su rail + sus reglas.** La visión: un sistema que se adapta "como la arena al
recipiente" — cualquier caso de uso inventado por cualquier usuario = widget (código+storage) + rail auto-generado
+ reglas + instrucciones, **generado sobre la marcha por el propio agente**; instintos (genética primigenia
hardcodeada) conviviendo con lo aprendido por el uso; **BRAIN RULES** (nombrar las reglas hardcodeadas) + **USER
RULES** (reglas por-usuario que viven en el ESTADO, el agente nace en blanco de ellas); y, a futuro, **GENÉTICA
transmisible** entre agentes conocidos en red.

Este documento es el ANÁLISIS DE ENCAJE con la arquitectura actual + el plan en tres cubos (AHORA/DESPUÉS/
PLACEHOLDER). **Regla de oro: nada de lo aquí propuesto rompe lo que funciona** — todo es aditivo sobre costuras
que ya existen. En este encargo NO se escribió código de producción.

---

## 1 · Mapeo honesto: la visión YA está construida a medias

La conclusión central del análisis: **zaelar no necesita un sistema nuevo — necesita nombrar, declarar y
generalizar piezas que ya existen.** Pieza a pieza:

| Pieza de la visión | Qué EXISTE hoy | El hueco real |
|---|---|---|
| **Widget generado sobre la marcha** (código + storage + reglas + instrucciones) | `widgets/generator.py` COMPLETO: un `claude -p` headless crea/modifica `manifest.json` (con `actions` + `usage` = las INSTRUCCIONES declarativas) + `widget.js` + `data.py` + `notes.md`; storage separado (`widgets/_data/`); gate de validación (acciones↔`apply_action` en sync por AST, background+`tick()`, XSS/red/stdlib/secretos/colisión CSS); rollback en modify; alta/LÁPIDA en memoria (V2-017) | Ninguno estructural. Es **el 70% de la visión, ya en producción**. Lo que falta es que el widget pueda declarar además su RAIL y (futuro) su tool |
| **Rail auto-generado** | `nucleo/rails.py` es GENÉRICO (runs por `kind` arbitrario, TTL, `sin_resolver`, proyección a `state.rails`, evento `rail`); el writeback `ingest_message(source=<rail>)` es genérico. Pero la GUÍA vive en un dict hardcodeado (`rails._GUIDANCE`) y la CADENA en un `.py` por dominio (`music_flow.py`) | La guía y los kinds NO son declarables por un widget. La cadena determinista sí es código legítimo — pero para la mayoría de casos de uso "de usuario" la cadena se reduce a `refs.resolve` + `widget_data` + run + writeback, que YA es la maquinaria del rail fundacional |
| **Instrucciones que se aprenden con el uso** | `widgets/brief.py::for_prompt` es **data-driven del catálogo VIVO**: cada widget nuevo entra al prompt del FlashBrain (id+misión+acciones+`usage`+items) sin tocar código del cerebro. El writeback tipado (`source="music"`) + el CORAZÓN (`mem_processor`) ya acumulan gustos/historial | El brief ES el mecanismo por el que "lo aprendido se vuelve conducta". Falta solo la variante situacional del rail (guía con run vivo) declarada por widget |
| **User rules** | `set_style_directive` (tool, directiva de SESIÓN re-inyectada cada turno vía `prompt._directive_block`) — pero NO persiste: la descripción actual manda lanzar un WORKER para "guardarla en memoria" (desproporcionado y poco fiable). `memory/state.py` ya tiene `treatment` (una proto-user-rule singular) y el ESTADO viaja en cada prompt vía `compose_state` (µs) | **El hueco más barato de cerrar**: un campo `rules` en el ESTADO + persistencia directa desde la propia tool + render en `compose_state §B`. Cero sistemas nuevos |
| **Brain rules (genética primigenia)** | Ya existen TODAS, sin nombre: `prompt._lang_lock` + `_flash_layer` (reglas de operación) + las descripciones de `router.TOOLS` (el "cuándo SÍ/NO" por tool) + los guards deterministas de invariante (`hard_interrupt`, `looks_like_stop_work/close/login…`, gates de memoria V2-033, `danger.py`) | Solo NOMBRARLAS como concepto de 1ª clase en docs. Cero código |
| **Instintos vs aprendido (convivencia)** | **Ya conviven**: catálogo estático `router.TOOLS` + guards (instintos) ∥ brief dinámico del catálogo de widgets + `state` + memoria (aprendido). El FlashBrain compone ambos cada turno | Formalizar la frontera (criterios §3) y, en DESPUÉS, dejar que lo aprendido también declare tools/rails |
| **Widgets incompletos → los completa el agente** | Ya existe: `[[modify:ID]]` → `generator.modify_widget` (quirúrgico, con backup+rollback+gate). "Al widget de vídeo le faltan botones" ES una frase que hoy escala y se resuelve | El hueco es de FIABILIDAD (bug 15-jul: modify→create basura, dedup de escalada), no de arquitectura. Endurecer, no construir |
| **Genética en red** | Sustrato de seguridad ya construido: cuarentena `trust=untrusted` + fence + allowlist de tags + `scan_outbound` (canal cluster); y el **gate del generador ya es un validador de "genes" entrantes** (un widget recibido pasaría el MISMO `_validate`: AST, XSS, red, secretos, acciones en sync) | Todo lo demás (consentimiento, permisos, transporte) es futuro → PLACEHOLDER |

**Veredicto del mapeo:** la visión NO exige rediseño. El generador de widgets es el prototipo funcional del
"sistema arena"; los rails V2-042 son el patrón a declarar; el ESTADO es el hogar natural de las user rules; la
seguridad de cluster + el gate del generador son la base de la genética. Lo que toca es (1) cerrar el hueco
pequeño (user rules), (2) nombrar lo que existe (brain rules, criterios), (3) declarar lo hardcodeado (rails por
manifest, DESPUÉS), (4) documentar el futuro (genética, PLACEHOLDER).

## 2 · Instintos vs aprendido — el modelo de convivencia (decidido)

- **INSTINTOS** = lo que TODO agente trae de nacimiento, hardcodeado y versionado con el código: las **brain
  rules** (lock de idioma, capa de operación V2-027, descripciones de `router.TOOLS`), los **guards deterministas
  de invariante** (interrupción dura, cerrar≠borrar, gates de memoria/danger) y las **tools nativas** del catálogo
  §8. Se cambian por desarrollo, nunca por el uso. `play_music`/`play_video` son HOY instintos de facto — correcto
  a corto plazo (§3), revisitable cuando exista la declaración de tools por widget (DESPUÉS).
- **APRENDIDO** = lo que se forma con el uso y vive en DATOS, no en código: los **widgets generados** (+ sus
  `actions`/`usage`, que entran al prompt por el brief data-driven), las **user rules** en el ESTADO, la
  **memoria** (gustos/historial por writeback tipado + destilación del CORAZÓN), y (DESPUÉS) los **rails
  declarados** por manifest. El agente nace EN BLANCO de todo esto.
- La convivencia ya está resuelta por construcción: el prompt de cada turno = brain rules (fijas) + ESTADO
  compuesto (aprendido) + brief del catálogo (aprendido) + guía situacional de rails (aprendido/declarado). No hay
  colisión: lo aprendido NUNCA pisa un guard determinista ni una brain rule (orden de ensamblado + gates en código).

## 3 · Criterios CANÓNICOS: ¿tool nativa o widget+rail? (aplicables desde YA)

Una capacidad nueva merece **tool NATIVA de 1ª clase** (catálogo §8) solo si cumple (a) y al menos una de (b)/(c):

- **(a) Es un instinto**: la querrá TODO usuario desde el día 0 (buscar, escalar, música, vídeo) — no un caso de
  uso personal de un usuario.
- **(b) Necesita discriminación tool-vs-tool EN el turno**: el no-razonador confunde la intención con otra tool y
  la prosa NO lo arregla (la lección medida de V2-045: 3 ciclos de prosa fallaron; una tool dedicada discriminó).
- **(c) Cruza subsistemas**: no pertenece a ningún widget (escalar, dirigir workers, autenticar).

Todo lo demás = **widget + data-ops** (sus `actions` declaradas, conducidas por `widget_data`) **+ rail declarado**
cuando exista (DESPUÉS). Presión estructural a favor de esta vía: cada tool nativa es coste de prompt PERMANENTE
en cada turno y ruido de decisión para el modelo pequeño (~12 tools hoy; el set contextual V2-035 lo mitiga pero no
lo elimina). **Regla de decisión corta: "¿lo pediría cualquier usuario el primer día Y el modelo lo confunde sin
tool propia?" → nativa. Si no → widget.**

## 4 · Plan en tres cubos

### AHORA (pequeño, sin riesgo — 1 sesión corta de implementación cuando el operador dé el OK)

**A1 · USER RULES en el ESTADO** (~½ día, ~150-200 líneas con tests). Mapeado 100% sobre costuras existentes,
sin sistema paralelo:
1. `memory/state.py::_DEFAULT` → campo nuevo `"rules": []` (lista corta de frases imperativas; cap ~8, dedup por
   texto normalizado, la más reciente manda).
2. `memory/api.py::compose_state §B` → render «REGLAS DEL OPERADOR (las dio él; síguelas SIEMPRE): …» cuando hay
   reglas. Viaja ya cacheado por `memory_cache` (µs, V2-011 intacto: es el MISMO camino del ESTADO).
3. `router.py::set_style_directive` → la tool RECONOCE la regla y **PERSISTE por defecto**: además de fijar la
   directiva de sesión (comportamiento actual, intacto como capa inmediata), el provider escribe la regla en
   `state.rules` off-loop (`asyncio.to_thread` → `memory.set_state`). Se ELIMINA de la descripción el "llama
   TAMBIÉN a escalate_to_slowbrain para guardarla" (lanzar un worker para persistir una preferencia era
   desproporcionado y poco fiable). Quitar una regla = la misma tool con el fraseo natural («olvida esa regla») —
   el provider la retira de la lista; sin tool nueva (el catálogo no crece).
4. Paridad voz/probe (V2-035: el probe es implementación paralela — cablear en ambos) + tests (`test_router`,
   `test_prompt`/`compose_state`) + docs-sync §8 + pestaña FlashBrain del diagrama.
   Nace en blanco: fresh install/`reset` ⇒ `rules: []`. Nada existente cambia de significado; si `rules` está
   vacío, el prompt es BYTE-idéntico al actual. Toca `compose_state` ⇒ al implementarse, pasar el **workflow de
   memoria** + revisión de alineación.

**A2 · Nombrar las BRAIN RULES** (docs, 0 código, hecho EN esta pasada): concepto de 1ª clase en
`zaelar-architecture.md` (§5e) + puntero en CLAUDE.md. Brain rules ≡ `_lang_lock` + `_flash_layer` +
descripciones de `router.TOOLS` + guards deterministas. Son la "genética primigenia": versionadas con el código,
no editables por el uso.

**A3 · Criterios tool-nativa vs widget+rail** (docs, 0 código, hecho EN esta pasada): la §3 de arriba queda como
criterio canónico, referenciado desde `zaelar-architecture.md §5e`. Aplica desde ya a cualquier "V2-045 siguiente".

### DESPUÉS (requiere diseño fino; no arrancar sin OK del operador)

**D1 · Rail DECLARADO por el widget** (el paso natural de V2-042; tamaño M, ~2-3 sesiones): el `manifest.json`
declara `"rail": {"kinds": ["<id>.search", …], "guidance": {"<kind>": {"when": ["sin_resolver"], "line": "…"}}}`
→ `rails.prompt_lines()` lee del catálogo además de `_GUIDANCE`; el gate del generador valida la declaración
(mismo patrón que `_validate_actions_sync`); el `_CONTRACT` la enseña. Con esto, un widget generado por voz trae
su conducción cross-turno SIN tocar `nucleo/`. La cadena determinista compleja (tipo `music_flow`) sigue siendo
código cuando haga falta — pero la mayoría de casos de usuario quedan cubiertos por refs+`widget_data`+run+guía.

**D2 · Tools declaradas por widget** (tamaño L, el paso que permitiría a `play_music`/`play_video` dejar de ser
nativas): un widget declara UNA intención de 1ª clase y `router.tools(context)` la añade dinámicamente al
catálogo. Riesgos reales que lo mandan a DESPUÉS: presupuesto de prompt y ruido de decisión del no-razonador
(justo lo que V2-027/V2-035 arreglaron), el invariante docs-sync §8 (catálogo canónico), y la calidad de una
descripción de tool escrita por un generador. Necesita: cap duro de tools dinámicas, gate de calidad de la
descripción, y medición con el probe ANTES de tocar producción.

**D3 · Aprendizaje por uso del rail** (S-M): los `sin_resolver` repetidos de un rail + el historial
`recent_by_source(<rail>)` alimentan el refinamiento de su guía/cadena (p. ej. el CORAZÓN destila «las búsquedas
de canciones del operador casi siempre son de los 80») — primero como memoria consultable, nunca editando prompts
en caliente sin gate.

**D4 · Endurecer el ciclo "widget incompleto → complétalo por voz"** (S): la arquitectura ya está
(`[[modify]]`+rollback); los bugs de la sesión 15-jul (modify→create basura, escaladas duplicadas) son fiabilidad
del despacho, no diseño. Anclar sus fixes aquí cuando se aborden.

### PLACEHOLDER (solo diseño documentado; NO construir nada aún)

**P1 · GENÉTICA transmisible entre agentes en red.** Cuando los agentes personales se conecten (canal MeshKore ya
existe), podrán transmitirse "genes": widgets, declaraciones de rail, mejoras. Restricciones de diseño que
CUALQUIER implementación futura debe respetar (quedan fijadas aquí):
1. **Solo entre conocidos con consentimiento** explícito de ambos operadores (el cluster ya exige connect
   operator-only; la transferencia hereda ese plano de control).
2. **Qué se transmite / qué NO**: se transmiten ARTEFACTOS validables (carpeta de widget, declaración de rail).
   NUNCA se transmiten user rules, ESTADO, memoria ni credenciales (son la persona, no la genética). Las brain
   rules son código versionado — se actualizan por release, no por peer.
3. **Todo gen entrante es `trust=untrusted` hasta pasar el gate**: cuarentena (la postura del canal de cluster,
   `mem_ingest`/security.py) + el **gate del generador como validador de importación** (`generator._validate` ya
   rechaza XSS/red/dinámico/secretos/acciones-desincronizadas — es EXACTAMENTE el banco de pruebas anti
   prompt-injection/malware que la visión pide) + revisión de manifest/usage como texto no confiable (fence antes
   de que llegue a un prompt).
4. **Permisos de datos por clase** para lo que un gen puede leer al ejecutarse (conocimientos, agenda…), sobre la
   costura de vías sancionadas que ya existe (`ctx.remember`/`ctx.ingest`/`memory.write` — un widget nunca toca la
   BD directa, luego el permiso se aplica en la fachada).
5. **Procedencia estampada** (`meta.source="peer:<id>"`, como los workers estampan `worker:<id>`).

## 5 · Invariantes que este plan NO toca (verificado contra el código)

- FlashBrain NO-razonador, sub-segundo; memoria FUERA del turno síncrono (V2-011) — las user rules van por el
  camino cacheado del ESTADO que ya existe; la persistencia es off-loop.
- Escritor único de memoria; workers por `remember_external` con gates — sin cambios.
- Un widget nunca rompe el resto; gate del generador; storage separado — el plan lo REFUERZA (el gate pasa a ser
  además el validador de genes).
- Catálogo de tools canónico §8 + docs-sync — A1 actualiza la fila de `set_style_directive` al implementarse; D2
  queda explícitamente condicionado a ese invariante.
- Cuarentena/anti-injection del cluster — P1 se apoya en ella, no la relaja.
- Nada de tablas de verbos/keywords para routing (feedback duro del operador): user rules = el modelo reconoce por
  tool-calling (mecanismo ya probado); rails declarados = datos, no diccionarios de comportamiento.

## 6 · Veredicto

**Implementar YA (cuando el operador dé el OK): A1 (user rules en el ESTADO) — ~½ día, ~150-200 líneas con
tests.** No rompe nada: campo aditivo en `state`, línea aditiva en `compose_state` (prompt idéntico si no hay
reglas), y una tool EXISTENTE que gana persistencia (perdiendo de paso el anti-patrón de lanzar un worker para
guardar una preferencia). A2/A3 (nombrar brain rules + criterios) quedan HECHOS en esta pasada (docs). D1 (rail
por manifest) es el siguiente paso natural y pequeño-mediano cuando el operador quiera extender; D2 (tools por
widget) es la generalización final y se hace SOLO con medición de probe. P1 (genética) queda como diseño fijado.

## Tareas

| ID | Tarea | Estado |
|---|---|---|
| T1 | **A1a** · `state.rules` en `memory/state.py::_DEFAULT` (nace en blanco) | ✅ done 2026-07-16 |
| T2 | **A1b** · `memory.add_user_rule`/`remove_user_rule` (dedup normalizado, cap 8, retirada por match difuso, emite `memory.updated`) + render `compose_state §B` «REGLAS DEL OPERADOR» (vacío = prompt byte-idéntico) | ✅ done 2026-07-16 |
| T3 | **A1c** · `set_style_directive`: nueva descripción (reconoce REGLA, persiste, retira; fuera el anti-patrón de escalar a worker) + guard determinista `router.looks_like_rule_removal` | ✅ done 2026-07-16 |
| T4 | **A1d** · Handler del provider (aplica ya + persiste off-loop `to_thread`; la retirada suelta también la directiva de sesión) + PARIDAD probe (gated a `ingest`) | ✅ done 2026-07-16 |
| T5 | **A1e** · Tests: `test_compose_state` (render/byte-idéntico/dedup/cap/retirada difusa/no-retirada-falsa) + `test_router` (guard) — 91/91 verde | ✅ done 2026-07-16 |
| T6 | **A1f** · Docs-sync: CLAUDE.md, `zaelar-architecture.md §8`, `zaelar-memory.md §Capas`, diagrama `/architecture` (fila de la tool + sellos de ambas pestañas, JS validado) | ✅ done 2026-07-16 |
| T7 | **A1g** · Verificación EN VIVO por el probe (regla → persiste + viaja en el prompt de OTRA sesión; «olvida esa regla» → se retira; NUNCA mudo — se arregló el turno de retirada mudo con ack `style_fired`) + ciclo permanente `user_rules_cycle` en `tester/loop_cycle.py` (3/3) | ✅ done 2026-07-16 |
| T8 | **D1** · Rail declarado por `manifest.json` (guía `_GUIDANCE` + kinds declarables por widget) | backlog (OK del operador) |
| T9 | **D2** · Tools declaradas por widget (medir presupuesto de prompt con probe; permitiría des-nativizar play_music/play_video) | backlog |
| T10 | **D3** · Aprendizaje por uso (writeback → afina la conducción del rail) · **D4** · endurecer el ciclo modify | backlog |
| T11 | **P1** · Genética transmisible en red (diseño fijado en §PLACEHOLDER; construir con la red de agentes) | placeholder |

## Bitácora
- **2026-07-16 (2)** — **A1 CONSTRUIDO** (el operador dio luz verde: "sin público aún, desde el génesis"): user
  rules persistentes end-to-end — estado + helpers de memoria + tool + provider + paridad probe + tests 91/91 +
  docs/diagrama. Detalle en Tareas T1-T6; T7 (verificación en vivo) en el mismo cierre.
- **2026-07-16** — Análisis de encaje (encargo del operador, agente Fable 5): mapeo pieza-a-pieza visión↔código
  (generator/rails/state/brief/set_style_directive/seguridad cluster), criterios canónicos tool-vs-widget, plan
  AHORA/DESPUÉS/PLACEHOLDER, restricciones de diseño de la genética en red. Docs tocadas: esta iniciativa +
  entrada en CLAUDE.md §Decisiones + `zaelar-architecture.md §5e` + placeholder en la teoría del diagrama
  (`/architecture`, pestaña Arquitectura). Sin código de producción (por encargo).
