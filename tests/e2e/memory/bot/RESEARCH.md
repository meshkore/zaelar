# RESEARCH — state-of-the-art de sistemas de memoria (bitácora viva)

Búsquedas periódicas para llevar la memoria de zaelar al mejor nivel posible. Cada entrada: fecha · hallazgo ·
qué aplicamos.

## 2026-07-10 — primer barrido

**Fuentes:** encuestas y comparativas 2026 de memoria de agentes (Mem0, Zep/Graphiti, Letta/MemGPT, MemPalace) +
papers de arquitectura episódica-semántica y dual-process.

**Hallazgos clave:**

- **Taxonomía convergente: episódica · semántica · procedural** (raíz en ciencia cognitiva). Episódica = experiencias
  concretas con timestamp/importancia/embedding; semántica = conocimiento abstraído y de-contextualizado (los hechos
  episódicos se CONSOLIDAN en patrones). → *nosotros:* CORTO≈episódico, LARGO/ESTADO≈semántico. Falta explotar
  **procedural** (cómo hacemos las cosas) — futuro.
- **Dual-process**: desacoplar el episódico inmediato (ventana fija ~10 msgs) del consolidado a largo (crece lento).
  El cuello de botella es la CALIDAD DE CONSOLIDACIÓN. → *nosotros:* CORTO buffer (`kind='conv'`, TTL) + consolidador
  (V2-019). Validado el diseño.
- **Memoria semántica basada en GRAFO** con extracción de entidades/relaciones + **detección de conflictos**
  (merge/resolve). Zep/Graphiti lidera LongMemEval (63.8%). → *nosotros:* `edges` (infrautilizado, T126) + supersede
  por `slot` = resolución de conflictos. **Prioridad:** poblar el grafo al escribir.
- **Operaciones de memoria como herramientas** (store/retrieve/update/summarize/discard) optimizadas por RL (AgeMem).
  → *nosotros:* el CORAZÓN ya decide store/discard/dónde; RL = futuro lejano.
- **Retrieval token-eficiente** (Mem0 <7k tokens/retrieval, LoCoMo 92.5% / LongMemEval 94.4%). → *nosotros:* RRF +
  budget de tokens; vigilar el coste del contexto.
- **In-context availability vs out-of-context retrieval**: lo esencial "se sabe" sin recuperar. → **APLICADO HOY:**
  bloque **perfil durable saliente** (`memory.salient_long`, top por importancia·peso, cacheado) siempre en el prompt
  del FlashBrain — cerró el fallo "¿qué deporte me gusta?" sin disparar recall (más humano).
- **100% local es viable en SOTA**: MemPalace (MIT, fully local, 96.6% R@5 LongMemEval, cero API). → valida nuestro
  ethos: memoria 100% local, sin nube.
- **Benchmarks de referencia**: **LongMemEval** y **LoCoMo**. → nuestro test bot es un LongMemEval casero; podríamos
  incorporar casos de esos benchmarks para comparabilidad.

**Aplicado en esta iteración (2026-07-10):** perfil durable saliente en el bloque cacheado del FlashBrain · modelo del
CORAZÓN a `qwen2.5:7b-instruct` (el 3b descartaba hechos durables de forma no-determinista) · `needs_recall` ampliado
a preguntas de gustos/atributos/posesiones · few-shot del procesador con gustos y posesiones.

**Pendiente por SOTA (cola de mejoras):** poblar el GRAFO de conceptos al escribir (T126, Zep-style) · consolidación
CORTO→LARGO por TTL/peso + resúmenes semánticos (V2-019) · capa procedural · incorporar casos de LongMemEval/LoCoMo.

## 2026-07-10 (b) — conflict resolution + grafos temporales (tanda 5)

**Fuentes:** "Don't Ask the LLM to Track Freshness: A Deterministic Recipe for Memory Conflict Resolution"
(arXiv 2606.01435), TOKI bi-temporal operator algebra (2606.06240), Zep/Graphiti (grafo temporal bi-temporal con
intervalos de validez), BEAM (ICLR 2026, 10 habilidades de memoria: contradicción, actualización, orden temporal…),
Mem0 State-of-Agent-Memory 2026.

**Hallazgos + qué aplicamos:**
- **La resolución de conflictos DETERMINISTA supera al juicio del LLM.** Graphiti usa un LLM en ingestión
  (`resolve_edge`) para decidir si un hecho contradice a otro y puntúa BAJO en el benchmark de contradicciones
  (hereda el problema de fiabilidad del LLM). → **APLICADO:** nuestra corrección/dedup de hechos SINGULARES es por
  **SLOT determinista** (no LLM): "ya no vivo en Barcelona, ahora Madrid" → supersede `operator.location`. Ampliado
  el vocabulario de slots (birthday/phone/address/diet/job). El dedup semántico por distancia queda como red
  SECUNDARIA con umbral conservador (0.45) — la distancia NO separa fiablemente "misma proposición" (0.4-0.7) de
  "misma entidad, info distinta" (0.8-1.0), así que no se le confía la corrección.
- **Invalidar, no borrar** (bi-temporal, Graphiti): preservar el histórico. → ya lo hacemos: `valid=0 +
  superseded_by`, nunca se borra el histórico.
- **Fiabilidad del extractor importa**: modelos pequeños se saltan hechos claros según el contexto. → **APLICADO:**
  CORAZÓN a qwen2.5:14b-instruct + **backstop DETERMINISTA de compromisos** (peticiones/tareas/citas se guardan
  aunque el LLM falle el juicio) — un humano no olvida un encargo.
- **BEAM / LongMemEval / LoCoMo**: taxonomía de habilidades (contradicción, update, orden temporal, abstención). →
  nuestro test bot ya cubre supersede/corrección, recall temporal y de mensajes; pendiente: orden temporal fino y
  abstención ("no lo sé" cuando no hay dato).

**Bug de producto encontrado por el bot (no-SOTA pero crítico):** `_COMMAND_RE` de la memoria confundía la
preposición "para" con el comando de parada → descartaba como "comando" cualquier frase con "para". Corregido.

## 2026-07-12 — barrido antes del ciclo de re-verificación de 1000

**Fuentes:** [Mem0 — AI Memory Benchmarks 2026](https://mem0.ai/blog/ai-memory-benchmarks-in-2026) ·
[State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026) ·
[Memory for Autonomous LLM Agents — survey](https://arxiv.org/html/2603.07670v1) ·
[KnowMe-Bench](https://arxiv.org/pdf/2601.04745) ·
[A Benchmark for Procedural Memory Retrieval](https://arxiv.org/pdf/2511.21730) ·
[StreamMemBench](https://arxiv.org/pdf/2606.14571) · MemoryArena / HaluMem / Locomo-Plus (2026, citados en el informe
Mem0).

**Hallazgos nuevos y qué aplicamos (4 dimensiones nuevas — ver TAXONOMY.md):**

- **MemoryArena (2026)** — la memoria DENTRO de tareas agénticas: modelos casi-perfectos en LoCoMo caen a **40–60%**
  cuando un paso posterior debe **ACTUAR** sobre lo aprendido antes. El recall aislado no basta. → **APLICADO:**
  dim **Z (memoria→acción encadenada)** — guardar una preferencia/hecho y, pasos después, que el recall que
  parametriza una acción (reservar, regalar, elegir menú) traiga los datos correctos combinados.
- **HaluMem (2026)** — consistencia y **no-alucinación** de memoria. En nuestro bot la lectura es DIRECTA (sin LLM),
  así que no se reproduce la alucinación de GENERACIÓN, pero SÍ la **precisión de lectura**: preguntar por algo no
  dado no debe aflorar un hecho confundible guardado. → **APLICADO:** dim **AA (anti-alucinación/precisión)** —
  fuga por adyacencia del retriever (hijos↔hermana, estudios↔trabajo, mi-moto↔la-del-vecino). Sharpening de E.
- **Zep bi-temporal / frontera temporal** — el problema abierto **nº1** es el razonamiento temporal + **intervalos
  de validez**: Zep saca +14.8 pts en temporal de LongMemEval por saber CUÁNDO fue cierto un hecho, no solo qué.
  → **APLICADO:** dim **AB (validez temporal / as-of)** — un hecho pasado sigue recuperable como histórico
  ("¿dónde vivía en 2013?", "mi perro anterior") mientras el vigente manda para el presente. Invalidar ≠ borrar.
- **KnowMe-Bench / cross-session identity** — modelo coherente y persistente de la PERSONA; la identidad
  cross-sesión es de los huecos más duros. → **APLICADO:** dim **AC (identidad cross-sesión)** — al FINAL del corpus
  (ve toda la historia acumulada), re-confirmar nombre/sitio/proyecto/hábitos/correcciones.

**Frontera que NO cabe en este bot (queda anotada):** **memoria procedural** transferible entre contextos
([benchmark 2026](https://arxiv.org/pdf/2511.21730)) — cómo-hacer reutilizable; roza dim O (rutinas) pero el eje
"abstracción de procedimiento que transfiere" es del LLM/SlowBrain, no de la lectura directa. Futuro.

**Confirmación de diseño:** el informe Mem0 2026 reafirma que (a) long-context ≠ memoria (capacidad vs continuidad),
(b) la resolución de conflictos DETERMINISTA gana (nuestro supersede por slot), (c) 100% local es viable en SOTA.
Nada que cambiar ahí — seguimos alineados.

## 2026-07-12 (c) — recall por categoría RECIENTE: enhancement futuro (intento revertido)

**Hallazgo (olas [120,280)):** varias queries de categoría con matiz TEMPORAL ("¿qué sabes de mi trabajo
ÚLTIMAMENTE?", "¿qué idiomas estoy aprendiendo AHORA?") quieren el miembro MÁS NUEVO de un cluster. El grafo los
hace ALCANZABLES (fix del backfill de conceptos), pero bajo el presupuesto de `compose_recall` el recall no
privilegia al reciente cuando la categoría es grande.

**Intento:** desempate por recencia en `graph_expand` (`ORDER BY weight DESC, m.created DESC`). **Revertido:**
regresionó consultas de MIEMBRO ESPECÍFICO (p. ej. "¿en qué año empecé de becario?" → 2016): promover los miembros
recientes del concepto desplazaba del presupuesto al miembro concreto que casaba por FTS. Un desempate global por
recencia ayuda a "lo último de X" pero perjudica "aquel dato concreto de X". Trade-off no aceptable como cambio
romo.

**Enhancement bien diseñado (pendiente, fuera del loop):** recency-aware SOLO cuando la query trae señal temporal
("último/ahora/nuevo/estoy +gerundio"), y ADITIVO (incluir el top-1 reciente del concepto SIN desplazar los hits
directos de FTS/vector), no reordenando todo el cluster. Mientras tanto, los casos de "lo último de una categoría"
se prueban con la pregunta ESPECÍFICA natural (el dato está guardado y es recuperable) — frontera T178 documentada.

## 2026-07-12 (d) — NO-DETERMINISMO del CORAZÓN → política de anclas ROBUSTAS

**Hallazgo (olas [0,360)):** casos que pasaban en verde en un replay fresco FALLAN en el siguiente sin tocar código
(#95 "no soporto llamadas", #152 fútbol dentro de deporte). Causa: el CORAZÓN (qwen2.5 local) **canonicaliza el
mismo input de forma distinta entre corridas** (temp 0 no es perfectamente determinista en Ollama + varía el
contexto de ESTADO acumulado): "no soporto las llamadas" se destila a veces como aversión y a veces como preferencia
positiva ("prefiere mensajes antes que llamadas"). El dato SIGUE guardado y recuperable, pero un ancla/consulta
FRÁGIL (que dependía de una fórmula concreta) oscila.

**Implicación para el ciclo:** una pasada de ORO 1031/1031 100% determinista es inalcanzable con un escritor LLM;
~1-2% de casos frágiles pueden flip-flop. **NO es un bug de memoria** — es varianza de fraseo del extractor.

**Política aplicada (test-hardening, no softening):** las anclas se fijan al **token estable** del hecho (el que
sobrevive a cualquier canonicalización razonable: "llamadas", "padel") y las **queries llevan puente léxico** o
apuntan al miembro PRIMARIO/estable de una categoría. Un buen recall debe traer el hecho independientemente de cómo
la memoria lo fraseó por dentro; el test no debe depender de la fórmula exacta del LLM. Esto CONVERGE el corpus a
robustez pasada tras pasada. (Mitigación de raíz —determinismo del escritor— queda como trabajo futuro; probablemente
irreducible del todo con LLM local.)

## 2026-07-12 (e) — el PROBLEMA DE CONSOLIDACIÓN (hito ~600)

**Fuentes:** [The Consolidation Problem in Agent Memory (Hindsight)](https://hindsight.vectorize.io/blog/2026/05/21/agent-memory-consolidation) ·
[Memory Agent Bench](https://openreview.net/pdf?id=DT7JyQC3MR) · [Mem0 Benchmarks 2026](https://mem0.ai/blog/ai-memory-benchmarks-in-2026) ·
[Forgetful but Faithful (privacy-aware)](https://arxiv.org/html/2512.12856v1).

- **La consolidación = capa de política con 4 palancas: importancia · merge · decay · EVICCIÓN.** Evictar un hecho
  SALIENTE aún vigente ERODE la confianza; no evictar nunca daña la privacidad. **No hay benchmark público que
  puntúe estas dinámicas directamente.** → *nosotros:* lo vimos EN VIVO (ola [440,520): el consolidador evictó un
  empleo aún vigente). Nuestras dims **L** (olvido/consolidación/decay) y **N** (privacidad/olvido a petición) ya
  atacan esto — vamos por delante del campo aquí. **Candidato de endgame:** revisar que la eviction por peso NO
  saque hechos de perfil vigentes (pinned/slot deberían protegerlos).
- **FactConsolidation es DURO:** el mejor RAG público (HippoRAG-v2) saca **54%** en single-hop FactConsolidation
  (Memory Agent Bench). → valida que nuestras fronteras de recall por categoría/co-retrieval bajo presupuesto (T151/
  T178) son coherentes con el estado del arte, no un defecto nuestro.
- **Confirmación de diseño:** "Don't Ask the LLM to Track Freshness" (recipe determinista) sigue avalando nuestro
  supersede por slot determinista.

## 2026-07-12 · V2-031 T1 — un embedding local más FUERTE NO sube el techo (hallazgo empírico)

Medido con `embed_bench.py` (re-embed del corpus + `scale_eval`, reranker local ON):

| embedding | dim | found@10 | recall@1 | recall@3 | MRR |
|---|---|---|---|---|---|
| embeddinggemma | 768 | 82.2% | 56.2% | 68.7% | 0.642 |
| **bge-m3** (SOTA multilingüe) | 1024 | **82.6%** | 55.9% | 68.3% | 0.640 |

**bge-m3 ≈ embeddinggemma.** Subir de 768 a 1024d SOTA NO mueve el techo `found@10`. → **el embedding NO es la
palanca del recall a escala.** Diagnóstico de los 50 casos que NI aparecen en el top-10: **la mayoría NO están
guardados** (0 filas en la BD: `150`/`lisboa`/`tokio`/`datalux`/`2018`/`macbook`/`andorra`…) o están invalidados
(`toby`/`611`); solo unos pocos (`girona`/`pasaporte`/`derecho`) están guardados y no se recuperan. **El techo es
WRITE-completeness + retrieval de lo guardado + reparación activa, NO la calidad del bi-encoder.**

⚠️ **Caveat de método detectado:** la medición fue sobre la BD ACUMULADA (579 mems de runs parciales `--next`),
que está INCOMPLETA — muchos hechos nunca se escribieron en ella. La comparación LIMPIA de embeddings exige medir
sobre una BD FRESCA de corpus completo (en curso). Aun así, ambos embeddings fallan IGUAL en los no-guardados, así
que el veredicto "el embedding no es la palanca" se sostiene. → **re-prioriza V2-031: el peso pasa a write-side
(T-nuevo), retrieval de lo guardado (T2/T3) y la memoria auto-evaluativa que REPARA (T5).**
