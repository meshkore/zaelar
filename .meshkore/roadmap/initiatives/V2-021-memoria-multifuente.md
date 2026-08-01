---
id: V2-021
title: Memoria MULTI-FUENTE — ingesta tipada de N fuentes (voz · mensajería · cluster · agentes) + consulta por tipo indexado + cuarentena de confianza
epic: v2-colmena
status: in-progress
priority: medium
owner: ricart
modules: [memory, connectors, nucleo]
depends_on: [V2-013, V2-008]
wall_order: 21
created: 2026-07-10
updated: 2026-07-10
---

## Goal

Que la memoria central ingiera datos de **varias fuentes de varios tipos** de forma UNIFORME e INDEXADA, y que
se pueda CONSULTAR por tipo/entidad sin LLM en la lectura. Objetivo de diseño: **extrapolable** — da igual 2
conectores que 200, un peer de cluster que veinte. Si gestionamos bien el dato tipado, todo el sistema gana:
"¿qué me han escrito por WhatsApp?", "¿qué me dijo Zalo por el cluster?", "¿qué me encontró tal agente?".

## Encaje con lo YA construido

Sobre V2-013 (píldora + `meta`) y V2-008 (conectores stateless que publican al bus). La mensajería ya volcaba a
memoria (`connectors/messaging/store._to_memory`) pero solo con el prefijo `[plataforma]` en el TEXTO, sin índice.
El canal de cluster (`connectors/meshkore`) NO escribía a memoria (reasoner stateless por seguridad).

## Qué se construyó (2026-07-10) — DONE

- **Primitivo TIPADO unificado** `memory.ingest_message(source, entity, text, *, trust, durable, group, directed)`:
  indexa `source`+`entity` en `meta` **y** en el texto (`[source] entity: body`). Vía ÚNICA para TODO conector.
- **Lectura por tipo INDEXADO** `memory.recent_by_source(source, entity)` — directa (json_extract sobre `meta`),
  µs, sin retriever ni LLM. Escala a N fuentes cambiando `source`.
- **Cuarentena por CONFIANZA** (`trust`): `operator`/`external` (datos del dueño) entran al bloque pasivo del
  FlashBrain; **`untrusted`** (peer de cluster/agente ajeno) NUNCA se inyecta en el prompt pasivo
  (`recent_short`/`salient_long` lo excluyen) — anti prompt-injection; solo aflora por consulta EXPLÍCITA.
- **Mensajería real** (`connectors/messaging/store`) migrada al primitivo → WhatsApp/Telegram quedan indexados.
- **Tests**: 4 unit (`tests/memory/integration/test_api.py`) + 5 tandas del bot (BATCH_30-34, 290→324):
  multi-fuente básico, cluster (Zalo) + agente, cross-source por entidad, hecho durable desde mensaje, escalado a
  fuentes futuras (email/linkedin/x), cuarentena. Verde.

## Tareas pendientes

- [x] T170 — **Cableado REAL cluster→memoria** (DONE 2026-07-10): `connectors/meshkore/mem_ingest.py` OBSERVA cada
  intercambio con un peer (peer→zaelar + zaelar→peer) y destila una **SÍNTESIS COMPRIMIDA y evolutiva por peer**
  bajo el slot canónico `cluster:<cluster>:<peer>` (supersede EXACTO → UNA píldora viva por peer, se reescribe, no
  acumula filas basura). Modelo LOCAL por defecto (mismo patrón que `mem_processor`/`triage`; fail-open a una fusión
  determinista ACOTADA). Se guarda `trust='untrusted'` + `durable` → **CUARENTENADA** (fuera del prompt pasivo y del
  recall; solo por `recent_by_source`). Cableado en `bridge.py::_brain_turn` (solo turnos de MENSAJE), fire-and-forget
  OFF-HOT-PATH — el reasoner **sigue stateless** (no gana estado ni capacidades; es pura observación). Contenido
  REDACTADO (secretos) y handles neutralizados antes de persistir. `dispatch`/`_route_reply` devuelven el saliente
  REALMENTE enviado (post-guard) para registrar lo que zaelar dijo. Superficie de seguridad: `MESHKORE_MEMORY=0` lo
  apaga. `ingest_message` extendido con `slot` (la síntesis evolutiva). Tests: `tests/cluster/unit/test_mem_ingest.py`
  (4 unit: síntesis cuarentenada, evolutiva/supersede, fail-open acotado, off por flag) + bot BATCH_37 (step nuevo
  `cluster_exchange`). Encaja con V2-010 (enrutado seguro del canal de cluster).
- [ ] T171 — **Voz como fuente tipada**: hoy la voz entra por `ingest_utterance` (el CORAZÓN). Evaluar si el turno
  de voz debe llevar también `source='voz'` en `meta` para consultas "¿qué te dije por voz vs por WhatsApp?".
- [ ] T172 — **Recall dirigido por fuente en el FlashBrain**: cuando el operador pregunta por una fuente
  ("¿qué me dijo Zalo?"), enrutar a `recent_by_source` (detección regex de fuente/entidad, sin LLM) en vez de
  depender del bloque pasivo — hace la consulta por tipo de primera clase también en el camino de voz.
- [x] T173 — **Cuarentena también en el recall semántico** (DONE 2026-07-10): la hidratación del retriever
  (`memory/retriever.py`, búsqueda principal + `graph_expand`) excluye `trust='untrusted'` → invariante FUERTE: el
  contenido de peers/agentes no confiables NUNCA aflora por `memory.query`/recall/grafo de conceptos, SOLO por
  `recent_by_source`. Test en `test_api.py::test_untrusted_is_quarantined_from_passive_reads`.
- [ ] T174 — Verificación + **revisión de alineación**.
- [ ] T175 — **El CORAZÓN infra-asigna `slot` → supersede/dedup en cadena INCOMPLETOS** (cazado 2026-07-11 por el
  bot BATCH_52, dim D). Síntoma: 3 statements de "la oficina está en X→Y→Z" y 5 fraseos de "alérgico al abedul" se
  guardaron TODOS con `slot=None` → sin clave canónica no dispara ni el supersede (los valores viejos Trantor/Nébula
  SIGUEN aflorando junto al actual Córdoba) ni el dedup exacto (5 fraseos → 3 píldoras, no 1). El `slot` es el motor
  de "el más reciente MANDA", pero `mem_processor` (qwen local) solo lo pone en hechos claramente enumerados
  (`operator.name`…) y lo deja vacío en singulares no-canónicos (ubicación de la oficina, un alérgeno concreto).
  **Hipótesis de mejora**: (a) ampliar el prompt del CORAZÓN con más ejemplos de "hecho singular → asigna slot
  `dominio.entidad`" y exigir slot para patrones posesión/ubicación/atributo; (b) backstop DETERMINISTA de slot en
  `nucleo/memory_agent` (como `_FORGET_RE`/`_ROUTINE_RE`) para familias singulares frecuentes; (c) evaluar
  dedup-por-similitud-de-embedding en el writer (umbral coseno) para colapsar paráfrasis sin slot. Riesgo: tocar el
  prompt del modelo local puede regresar otros casos → hacerlo con re-validación completa del camino de ESCRITURA.
  Los tests B52 quedan como GUARD de regresión del comportamiento actual (que no empeore) hasta cerrar T175; al
  cerrarlo, endurecer #424 con `not_want:['trantor','nébula']` y #425 a `max_count:1`.
- [ ] T176 — **El recall SEMÁNTICO a escala depende CRÍTICAMENTE del backend de embeddings** (cazado 2026-07-11
  por el bot BATCH_57, dim T×K). Con agujas cuya pregunta NO comparte léxico con el hecho (solo el vector las
  encuentra) enterradas entre miles de recuerdos: **embeddinggemma (Ollama, PRODUCCIÓN) AGUANTA** (5/6 a 300 y 1500,
  6/6 a 3000, latencia plana ~84ms) → la superpotencia es real; **el fallback `fastembed` COLAPSA** (5/6 a 300 →
  **0/6 a 1500**, latencia ~1ms pero recall nulo). Cuando FTS no ayuda (sin solape léxico), todo recae en el vector,
  y el fallback no discrimina a escala. **Implicación de producto**: (a) garantizar que en producción el backend sea
  embeddinggemma (Ollama arriba) y **avisar/telemetría si se cae al fallback** (degrada la memoria semántica sin que
  se note); (b) evaluar un fallback mejor (bge-m3/e5-multilingual vía fastembed) o forzar hash+FTS-only con aviso;
  (c) considerar re-ranking / K mayor cuando el backend sea débil. Nota: la aguja 'danés' (gran danés↔mascota +
  gentilicio) es un caso ambiguo duro que ni embeddinggemma resuelve siempre → `min_found` lo tolera. B57 queda como
  guard (embeddinggemma no debe bajar de 5/6@1500). No confundir con la escala LÉXICA (B47/B54): esa la salva FTS+RRF.
- [x] T184 — **BUG: `recent_by_source(source, entity)` fallaba con entidades ACENTUADAS** (cazado + DONE 2026-07-11,
  bot BATCH_131, dim G). El índice por fuente filtraba con `lower(json_extract(meta,'$.entity'))=?` y el `lower()` de
  SQLite es SOLO-ASCII → no baja Á/É/Í/Ó/Ú/Ñ, mientras el parámetro llegaba con el `.lower()` Unicode de Python →
  **asimetría → 0 filas para todo nombre con tilde/ñ** (Álvaro, María, mamá, Begoña, Jesús…). Impacto directo en la
  lectura multi-fuente ("¿qué me dijo María por WhatsApp?" no devolvía nada). Ningún test previo consultaba una
  entidad acentuada → pasó desapercibido. **FIX**: función SQL `pylower` (Unicode) registrada en `memory/db.py`;
  `memory/api.py::recent_by_source` la usa en el filtro de entidad. Guard: `test_api.py::
  test_recent_by_source_entity_is_accent_insensitive`. Riesgo nulo (función nueva, no sobrescribe el `lower` builtin).

## Aceptación

Ingesta de ≥4 fuentes distintas queryable por tipo indexado; el contenido untrusted nunca en el prompt pasivo y
sí por consulta explícita; el cluster real genera memoria cuarentenada; tests verdes; docs alineadas.
- [ ] T177 — **Retrieval MULTI-HOP limitado a ~1 salto de graph_expand** (cazado 2026-07-11, bot BATCH_59, dim U).
  Una cadena de 3 saltos (abuela→Remedios→Alcañiz→Teruel; amigo→Nicanor→Quantiova→solares) con la pregunta
  léxicamente disjunta del TERMINAL: el retriever aflora hasta el 2º salto (Alcañiz, Quantiova) pero NO el terminal
  (Teruel, solares) — `graph_expand` expande ~1 salto desde los nodos recuperados. El 2-hop SÍ funciona (B48).
  **Hipótesis de mejora**: retrieval ITERATIVO off-hot-path (re-query con las entidades recuperadas, 2-3 rondas)
  SOLO en el recall LARGO (tolera latencia, `asyncio.to_thread`); o graph_expand de profundidad 2 con tope de fan-out.
  No urgente (el LLM del turno puede re-preguntar). B59 queda como guard de 2-hop; al cerrar T177, añadir el
  terminal a `want`.
- [ ] T178 — **Completeness multi-instancia + FRAGMENTACIÓN de entidad** (cazado 2026-07-11, bot BATCH_66, dim G).
  La memoria conserva homónimos DISTINTOS (jefa Ana vs sobrina Ana, recuperables cada uno por su contexto — OK),
  PERO un "lista TODAS las personas llamadas Ana" es INCOMPLETO: una 3ª Ana (la vecina de B49, dicha en telegráfico
  "Ana. 34. Bilbao. Arquitecta") quedó FRAGMENTADA en 4 píldoras ("se llama Ana", "tiene 34 años", "es de Bilbao",
  "es arquitecta") que, con el top-K del retriever, ENTIERRAN a la sobrina (1 sola píldora). Dos causas: (a)
  FRAGMENTACIÓN en escritura (el CORAZÓN parte un input multi-atributo en N píldoras por atributo → infla una
  entidad) — ligado a T175; (b) el recall top-K no garantiza cubrir TODAS las instancias de una consulta "lista
  todos" — ligado a T177 (completeness multi-item). **Hipótesis**: (a) al destilar, agrupar atributos de la MISMA
  entidad en menos píldoras (o enlazarlas por slot `persona:<nombre>`); (b) para consultas "lista todos", una fase
  de agregación por entidad off-hot-path. B66 queda como guard del NO-COLAPSO (lo importante: no se funden).
- [ ] T179 — **Sin detección de INVALIDACIÓN IMPLÍCITA (staleness)** (cazado 2026-07-11, bot BATCH_71, dim X;
  benchmark STALE 2026). Un hecho nuevo deja OBSOLETO a otro SIN corrección explícita: "estoy embarazada" →
  "ayer di a luz" (ya no lo está); "vivo de alquiler" → "firmé la escritura, soy propietario". Hoy AMBOS estados
  coexisten en el recall (el viejo NO se invalida) — hace falta conocimiento del mundo al ESCRIBIR para saber que
  el nuevo obsoleta al viejo. No es dim M (ahí el operador dice "no X sino Y"). **Hipótesis**: (a) el CORAZÓN, al
  destilar un hecho de estado, marca si CIERRA un estado anterior del mismo slot/entidad (p. ej. `estado.embarazo`,
  `estado.vivienda`) → supersede; (b) atenuar por recencia dos hechos del mismo slot incompatibles. Aceptable como
  frontera: la memoria SIRVE ambos y el LLM del turno puede inferir la obsolescencia; el ideal es down-weight del
  stale. Ligado a T175 (sin slot no hay supersede). B71 guarda que el hecho NUEVO se recupera.
- [ ] T180 — **Preguntas al asistente guardadas como hechos** (cazado + MITIGADO PARCIAL 2026-07-11, bot BATCH_72,
  dim E). "¿qué tiempo hace en Sevilla?"/"¿me recomiendas una serie?" se guardaban como datos del operador
  (polución del perfil). MITIGACIÓN: backstop determinista `_ASSISTANT_QUERY_RE` en `nucleo/memory_agent` descarta
  peticiones INEQUÍVOCAS al asistente (tiempo de una ciudad, recomendación) — conservador, NO toca preguntas que
  traen un dato ("¿sabes que me mudé a Madrid?"). PENDIENTE: la deliberación "¿debería comprar X?" sigue entrando
  al working-set (borde: interés débil, aceptable); ampliar cobertura si aparecen más patrones de pregunta-no-hecho.
- [ ] T181 — **La destilación GENERALIZA y pierde nombres propios en input verboso** (cazado 2026-07-11, bot
  BATCH_80, dim V). De una parrafada de ~300 palabras el CORAZÓN SÍ extrajo los 2 hechos (multi-extracción OK),
  pero canonicalizó "he comprado entradas para el concierto de MUSE" → "Ha comprado dos entradas para un concierto"
  — perdió el nombre propio "Muse". Contraste: de una parrafada MÁS CORTA (B49) el nombre "Kroxel" SÍ sobrevivió →
  la fidelidad de detalle CAE con la longitud del input (el modelo resume más agresivo). **Hipótesis de mejora**:
  una línea en el prompt de `mem_processor` — "PRESERVA nombres propios y detalles específicos (marcas, bandas,
  lugares, cifras, nombres); NO los generalices" — y validar que no infla píldoras. Riesgo bajo-medio (prompt del
  modelo local → re-validar el camino de escritura). Aceptable como frontera: se recuerda el HECHO (compró
  entradas), se pierde el discriminador (qué banda). B80 guarda que el hecho se extrae.
  **ACTUALIZACIÓN 2026-07-11**: PROBADO el enfoque de prompt (añadir 'PRESERVA nombres propios, no generalices' a `mem_processor._SYSTEM`) → INEFECTIVO: el qwen local siguió destilando 'un concierto' (ignoró la instrucción). Revertido. T181 necesita otra táctica: (a) post-paso DETERMINISTA que reinyecte los nombres propios del texto crudo ausentes en la píldora, o (b) un modelo destilador más fuerte. No es prompt-tunable en el modelo local actual.
- [ ] T182 — **Corrección SIN sujeto → MISATRIBUCIÓN del valor nuevo (destilación de UN turno sin contexto)**
  (cazado 2026-07-11, bot BATCH_82, dim M). Cadena "la clave del garaje es Azulón" → "no es Azulón sino Verdín"
  (acierta: repite 'del garaje') → "no es Verdín sino Escarlex" (NO repite el sujeto) → el CORAZÓN guardó
  "El perro se llama Escarlex" (¡misatribuido a la mascota!). Causa: `mem_processor.process(t)` destila UN turno
  aislado, SIN el buffer de conversación, así que "no es Verdín sino Escarlex" pierde a QUÉ se refiere. El FORGET
  encadena bien (Azulón/Verdín invalidados); lo que falla es la ATRIBUCIÓN del valor nuevo. **Hipótesis de mejora**:
  (a) en el hook de corrección (`_CORRECTION_RE`), tras capturar X (viejo) e Y (nuevo), tomar la píldora que casa X,
  sustituir X→Y en su TEXTO y guardar esa píldora corregida (hereda el sujeto: "La clave del garaje es Escarlex") —
  determinista, sin depender del LLM; (b) pasar el último turno como contexto a `mem_processor`. Riesgo (a) bajo
  (solo dispara con "no es X sino Y" explícito). Nota: (a) deja además el pill fantasma "perro=Escarlex" del LLM →
  habría que suprimirlo. B82 guarda el forget-chain.
- [ ] T183 — **Sin APLICACIÓN IMPLÍCITA de restricciones cross-topic** (cazado 2026-07-11, bot BATCH_98, dim I;
  benchmark Mem2ActBench 2026). Una restricción establecida ("soy celíaco", "voy justo de presupuesto") NO aflora
  cuando llega una consulta de OTRO tema relacionado ("¿me recomiendas un restaurante?", "¿qué plan para el finde?")
  → el asistente no la APLICA sola. El dato SÍ se recupera con una consulta del MISMO tema ("¿tengo restricciones
  alimentarias?"). El retriever casa por proximidad léxica/semántica y 'restaurante/cenar' no está lo bastante cerca
  de 'celíaco/gluten'. Es "retain memory without using the right evidence when a later task requires it". **Hipótesis
  de mejora**: expansión de consulta por CONCEPTOS (query→conceptos→traer hechos con ese concepto: 'restaurante'→
  concepto 'comida'→píldoras 'comida' incluida la celiaquía), off-hot-path en el recall LARGO. Comparte raíz con
  T178 (agregación por concepto/categoría). Alto valor de producto (un asistente que aplica tus restricciones sin
  que las repitas). B98 guarda que la restricción se almacena y se recupera same-topic.
  **AVANCE 2026-07-11**: PRERREQUISITO hecho — el vocab de `memory/concepts.py` no etiquetaba las
  restricciones dietéticas ('celíaco/gluten/lactosa'→[]); ahora → 'comida' (guard pytest). Así la restricción Y
  la consulta ('restaurante'→'comida') comparten concepto → el puente EXISTE. Falta solo la 2ª mitad (la de sesión
  dedicada): expansión por conceptos en `compose_recall` (sparse-fill: si el recall directo trae <8 durables,
  rellenar con hechos del concepto de la consulta vía un `memory.by_concepts` que recorra las aristas del grafo,
  respetando cuarentena). Eso cierra T183 y T178 a la vez.
  **AVANCE 2026-07-11 (2)**: `memory.by_concepts(concepts, limit)` CONSTRUIDO y probado (guard pytest
  `test_by_concepts_returns_linked_facts_and_quarantines_untrusted`): recorre las aristas concepto→píldora, respeta
  valid+cuarentena. AL PROBARLO se AISLÓ el verdadero BLOQUEO: NO es el wiring de recall — es la COBERTURA DE
  ETIQUETADO del grafo. Ej.: 'fui a Oporto' NO deriva el concepto 'viajes' (la regex de `memory/concepts.py` no
  cubre verbo+lugar: 'fui/estuve/visité <lugar>'), y la píldora de celiaquía guardada ANTES del fix de vocab no
  tiene arista 'comida'. → la sesión dedicada de T178/T183 es: (1) ampliar MUCHO el vocab de `concepts.py` + mejorar
  el etiquetado del CORAZÓN, (2) RE-ETIQUETAR los hechos existentes (poblar aristas que faltan), (3) recién entonces
  cablear el sparse-fill en `compose_recall` con by_concepts. El primitivo ya está; falta la densidad del grafo.
  **EVIDENCIA (3) 2026-07-11**: intento de tanda K "recall por CATEGORÍA a escala" (pregunta genérica "¿qué problema
  de salud tengo?" contra un hecho específico enterrado entre ruido same-category) da **0/4** a noise 400 con
  embeddinggemma. Confirma que el retriever RRF puro NO resuelve la agregación por categoría: el hecho específico no
  es léxica ni fuertemente-semánticamente más cercano a la categoría que N notas genéricas que SÍ contienen la palabra
  de categoría → el fix es la expansión por conceptos (by_concepts), no más embeddings. Refuerza el alcance de la
  sesión dedicada. NO se añadió test rojo al suite (frontera conocida-sin-arreglar).

**Testing @800 (2026-07-11)**: el suite del bot cruzó 800 casos sin nuevos bugs multi-fuente (el último fue T184,
`pylower`). EXIGENCIA @800 pasada: incorporado el arquetipo de ABSTENCIÓN de LongMemEval (membot-level: no fabricar
hechos; la abstención plena de respuesta es del LLM → tester en vivo). Frontera estructural viva sigue siendo T178.

- [x] T185 — **BUG: olvido GRANULAR fallaba con fraseo natural** (cazado + DONE 2026-07-11, bot BATCH_143, dim N).
  `memory.forget(match)` invalidaba por `LIKE '%match%'` CONTIGUO → "olvida la matrícula de MI coche" no casaba con
  el hecho canónico "matrícula de SU coche" (el CORAZÓN canoniza el posesivo a 3ª persona) ni toleraba cambios de
  orden → el dato NO se olvidaba (fallo de privacidad). **FIX**: cuando el contiguo no encuentra nada, fallback
  TOKEN-AND sobre tokens de contenido (≥3 chars, sin stopwords/posesivos `_FORGET_STOP`) → invalida los recuerdos
  que contienen TODOS. Conservador (solo se activa si el contiguo falla; exige todos los tokens → no sobre-borra) y
  respeta `pinned`. Guard: `test_api.py::test_forget_selective_matches_by_content_tokens`.

**Extrapolabilidad validada (2026-07-11)**: bot BATCH_145 (dim G) ejercita 10 peers de cluster distintos → el índice
por fuente (`recent_by_source`) disambigua por entidad SIN contaminación cruzada y la cuarentena `untrusted` aguanta
a volumen (ninguno de los 10 se cuela en el prompt pasivo/recall). Sostiene la afirmación de diseño "da igual 2 que
200 fuentes". Cierra el arquetipo pendiente de G en el PLAN.

- [x] T186 — **BUG: el olvido NL no aceptaba enclíticos** (cazado + DONE 2026-07-11, bot BATCH_159, dim N).
  `_FORGET_RE` (`nucleo/memory_agent.py`) reconocía "olvida/olvídate/bórrate/elimina" pero NO el enclítico -me/-lo/
  -melo ("bórrame el número", "olvídame lo de X", "bórramelo") — el fraseo NATURAL más común del olvido → el hook no
  disparaba y el dato NO se olvidaba (fallo de privacidad/usabilidad). **FIX**: verbo + enclítico opcional
  (`olv[ií]da(?:te|me|lo|la)?|b[oó]rra(?:te|me|lo|la|melo|mela)?`). Guard:
  `test_memory_agent.py::test_forget_regex_accepts_enclitic_pronouns` ('bórralo' anafórico sin objeto NO dispara).
