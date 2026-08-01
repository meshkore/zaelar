# Taxonomía de tests de la memoria de zaelar — el MAPA para no duplicar y cazar bugs

> **Objetivo del operador (2026-07-10):** llegar a **1000 casos** probando la memoria A FONDO, de forma
> **organizada por TIPOLOGÍA** para (a) NO duplicar trabajo cuando hagamos las próximas 1000 y (b) ser **incisivos**
> — cada dimensión ataca un modo de fallo distinto de "una memoria humana con superpoderes".
>
> **Cómo se usa este doc:** cada caso de `cases.py` lleva (idealmente) un campo **`dim`** con el CÓDIGO de dimensión
> (abajo). El runner (`--coverage`) cuenta casos por dimensión → vemos huecos de un vistazo. Antes de añadir una
> tanda, mira aquí qué dimensión está floja y ataca ESA. Los batches legacy (1-29) se mapean por lote más abajo.

## Las DIMENSIONES (tipologías de prueba)

| Cód | Dimensión | Qué ataca (modo de fallo que caza) |
|----|-----------|-------------------------------------|
| **A** | ESTADO / perfil singular | El `state` no se puebla aunque el operador diga su nombre/ubicación/trato; supersede de perfil. |
| **B** | CORTO / recencia | "¿qué acabo de decir?" / "¿de qué hablábamos?"; ventana de recencia; orden determinista; se cae del working set. |
| **C** | LARGO / recall semántico | Hecho durable no se recupera por significado; retención profunda (cientos de pasos atrás). |
| **D** | DEDUP / supersede | Mismo hecho en varios fraseos → debe colapsar en 1; dato cambiado → invalida el viejo (no deja duplicados). |
| **E** | DESCARTE / abstención | Guarda trivialidades (saludos/comandos) que debería tirar; o ALUCINA un dato que nunca se dijo. |
| **F** | GRAFO de conceptos / categoría | "¿cómo va mi salud?" no aflora el cluster; co-ocurrencia; recall por CATEGORÍA sin LLM. |
| **G** | MULTI-FUENTE / ingesta tipada | whatsapp/telegram/cluster/agent/email; índice por `source`/`entity`; escala a N conectores. |
| **H** | CUARENTENA / confianza | Contenido `untrusted` (peer de cluster) se cuela en el prompt pasivo/recall (inyección); o no aflora por consulta explícita. |
| **I** | INTERESES / intenciones | No infiere gustos latentes ni deseos a futuro del dato ("estudio buceo" → interés buceo + intención viaje). |
| **J** | TEMPORAL / cronología | "¿qué pasó ANTES, X o Y?"; fechas; ordenar eventos; co-recuperar dos eventos fechados (gap SOTA, T151). |
| **K** | ESCALA / grandes volúmenes | Con MILES de recuerdos: la precisión de recall colapsa (needle-in-haystack), la latencia se dispara, el working set desborda, lo importante queda enterrado. **La preocupación nº1 del operador.** |
| **L** | OLVIDO / consolidación / decay | El peso no baja con el tiempo; `pinned` se borra por error; eviction mata lo relevante; el CORTO no se poda (V2-019). |
| **M** | CONTRADICCIONES / correcciones | Corrección parcial ("en realidad no es X sino Y"); negación de un hecho previo; el viejo sigue vivo. |
| **N** | PRIVACIDAD / olvido a petición | "olvida esto / bórralo": el dato debe desaparecer del recall (borrado/invalidación explícita). |
| **O** | RUTINAS / hábitos / patrones | Recurrencia ("cada lunes gimnasio"): se guarda como patrón, no como N eventos sueltos; se recuerda la regularidad. |
| **P** | ADVERSARIAL / ruido / STT | Voz ambiente, fraseo confuso/roto del STT, mezcla de idiomas, intento de inyección → no corrompe la memoria. |
| **Q** | CROSS-SOURCE síntesis | "¿todo lo que sabes de mi salud?" combinando voz + mensajes + episódica de varias fuentes en una respuesta. |
| **R** | MULTILINGÜE | El mismo hecho dicho en es y en en; recall cruzado de idioma; no duplica por idioma. |
| **S** | EPISÓDICA / ficheros | paste/drop → resumen buscable; carga lazy; el fichero no entra al prompt por defecto pero es recuperable. |
| **T** | VOCABULARIO-GAP | Pregunta sin solape léxico con el hecho ("¿qué INSTRUMENTO toco?" → "toco la GUITARRA"): el techo del embedding local (T150). |
| **U** | MULTI-HOP / composición | Responder exige ENCADENAR 2+ hechos (hermana→Lucía→Valencia). El recall debe aflorar TODOS los eslabones para que el cerebro salte. No probamos el razonamiento del LLM (no hay LLM en la lectura) sino la SUFICIENCIA del recall. (LongMemEval: multi-session reasoning.) |
| **V** | VERBOSIDAD / extracción | El CORAZÓN extrae el hecho tanto de un input TELEGRÁFICO (1-4 palabras, staccato) como de una PARRAFADA de 100-300 palabras con la aguja enterrada. Eje explícito del operador: "entradas de pocas palabras, entradas de muchas palabras". |
| **W** | INSTRUCCIONES permanentes | Una directiva de comportamiento ("háblame de usted", "distancias siempre en km", "música en Spotify") se guarda como preferencia DURABLE y se recupera para OBEDECERLA. (MemBench/MemoryAgentBench: preference & instruction following.) |
| **X** | INVALIDACIÓN implícita / staleness | Un hecho nuevo deja OBSOLETO a otro SIN corrección explícita ("estoy embarazada"→"di a luz"; "vivo de alquiler"→"compré casa"). Requiere conocimiento del mundo al escribir para saber que el viejo ya no vale. (Benchmark STALE 2026.) Distinto de M (explícito "no X sino Y"). |
| **Y** | ESTADO / CONTEXTO DE UI VIVO | "Lo que el operador tiene DELANTE ahora": widgets ABIERTOS en el canvas + tareas del SlowBrain en marcha, guardado en el ESTADO (`memory/state.py`) y viajando SIEMPRE en el prompt (`memory_cache`) para resolver "modifica el widget de X" sin preguntar. Se verifica que GUARDA lo debido (patch sin pisar, supersede, limpieza) y que el FlashBrain lo VE en su bloque. Feat 2026-07-11. Step propio `ui_state`. |
| **Z** | MEMORIA → ACCIÓN encadenada | Un paso posterior COMPONE hechos guardados antes para PARAMETRIZAR una acción (reservar en "mi restaurante", regalo por el interés de un tercero, menú por mi dieta). Observable en el bot = el recall que alimentaría la acción trae los datos correctos combinados. (MemoryArena 2026: modelos casi-perfectos en LoCoMo caen a 40-60% cuando un paso depende de ACTUAR sobre lo aprendido.) |
| **AA** | ANTI-ALUCINACIÓN / precisión de recall | Preguntar por algo NO dado no debe aflorar un hecho CONFUNDIBLE que sí está guardado (fuga por adyacencia del retriever: hijos↔hermana, estudios↔trabajo, mi-moto↔la-del-vecino) → abstención honesta. Como la lectura no tiene LLM, no reproduce la alucinación de GENERACIÓN sino la PRECISIÓN de lectura. (HaluMem 2026.) Sharpening de E en query-time. |
| **AB** | VALIDEZ TEMPORAL / as-of | Un hecho PASADO sigue recuperable como histórico ("¿dónde vivía en 2013?", "mi perro anterior") mientras el VIGENTE manda para el presente y NO se cuela como actual. Invalidar ≠ borrar. (Zep bi-temporal / frontera temporal 2026 = problema abierto nº1.) Distinta de J (cronología entre eventos) y X (obsolescencia implícita). |
| **AC** | IDENTIDAD cross-sesión | Tras MUCHÍSIMA conversación acumulada, el modelo de la PERSONA sigue firme y coherente — nombre, sitio, proyecto, hábitos, correcciones aplicadas. Corre al FINAL del corpus (ve toda la historia): la prueba más dura de persistencia. (KnowMe-Bench 2026 / cross-session identity.) |
| **AD** | SEÑAL DE CAMBIO multiidioma | Un cambio de vida declarado (mudanza, cambio de oficio/coche/objetivo) en CUALQUIER fraseo/idioma actualiza el ESTADO y supersede la píldora vieja — la señal `change: update|correction` la emite el PROPIO procesador (multilingüe), ya no las regex es/en del host. (Auditoría 2026-07-14; corpus v2 `cases2.py`.) |
| **AE** | REGISTRO de slots / colapso de linajes | El mismo hecho SINGULAR dicho de N formas (que disparan alias de slot distintos) queda en UNA sola píldora vigente — el bug del retest V2-038 (4 ubicaciones a la vez) cerrado por el registro canónico `memory/slots.py`. Step `slot_count`. |
| **AF** | ESCRITURA de WORKERS (externa) | La vía `remember_external` (workers vía `hbmem`/HTTP) aplica gates que la voz no necesita: NUNCA toca `state`, slots de IDENTIDAD VETADOS, preguntas reificadas DESCARTADAS, procedencia estampada. Step `worker_write`. |
| **AG** | SANEO heal_slots (consolidador) | El consolidador colapsa linajes duplicados del stock YA existente (alias/legacy/unforget pre-normalización) → 1 vigente por slot. Step `heal_slots`. |

### Corpus v2 (`cases2.py`) — persona NUEVA para genericidad + capacidades de la auditoría (2026-07-14)

Segundo corpus, hermano de `cases.py`, con **otra PERSONA** (Amaia Etxeberria, de Logroño — no el Ricart/Barcelona
de la GOLD) para verificar que la memoria se sirve **EN BLANCO** y es genérica/multi-operador (el sesgo que la
auditoría quitó de los fewshots), y con las **4 dimensiones nuevas AD–AG** que estresan lo cambiado en la
auditoría. Se corre con `--corpus v2` (BD/progreso/catálogo AISLADOS de v1; la GOLD de 1032 queda intacta):

```bash
python -m tests.memory.e2e.bot.runner --corpus v2 --coverage
python -m tests.memory.e2e.bot.runner --corpus v2 --fresh --range 0 N
```

Estado inicial (2026-07-14): **650 casos, 33 dimensiones**. Baseline de humo `[0,46]` = 42/46 (los 4 rojos son
hallazgos reales que el ciclo tría: write-completeness de `qwen2.5:3b` — mejora con `MEM_PROCESSOR_MODEL=qwen2.5:7b`
—, sensibilidad de fraseo del recall por categoría (frontera T178), y no-determinismo de la 1ª mudanza→estado).
Objetivo del corpus: crecer a ~1000 por el protocolo de tandas + `EXIGENCIA.md` (los generadores data-driven de
`cases2.py` hacen trivial añadir hechos distintos).

### Fundamento del estado del arte (por qué estas dimensiones — WebSearch 2026-07-11)

> **La TEORÍA canónica** (cómo se evalúa un sistema de memoria, las 5 competencias de MemoryAgentBench, la
> metodología de 3 superficies, las fronteras y las mejoras) vive en `.meshkore/docs/architecture/zaelar-memory.md`
> **§ Evaluación de la memoria**. Este doc es el MAPA operativo (dimensiones + cobertura para no duplicar).

La literatura de benchmarking de memoria de agentes converge en un puñado de **habilidades núcleo**. Nuestras
**29 dimensiones (A–Y + Z/AA/AB/AC)** las cubren TODAS, y varias las añadimos precisamente tras revisar el campo
(las 4 últimas, del barrido 2026-07-12: MemoryArena, HaluMem, Zep bi-temporal, KnowMe-Bench — ver `RESEARCH.md`). MemoryAgentBench
(ICLR 2026) las resume en 4 competencias + 1 hueco: recuperación exacta, aprendizaje-en-uso, comprensión de largo
alcance, olvido selectivo, y **organización de la estructura** (el grafo de conceptos, dims F/T/T178/T183):

- **LongMemEval** (ICLR 2025) — 5 habilidades: information extraction, multi-session reasoning, temporal
  reasoning, knowledge updates, **abstention**. Simula 115k–1.5M tokens con **distractores realistas**.
- **LoCoMo** — QA sobre 50 conversaciones (~300 turnos, 35 sesiones): single-hop, **multi-hop**, temporal,
  open-domain, adversarial (unanswerable).
- **MemBench / MemoryAgentBench** — factual recall, **preference/instruction following**, **contradiction
  handling**, temporal, multi-hop.
- **MemConflict** — sistemas de memoria bajo CONFLICTOS (dos hechos incompatibles).
- **BEAM** — escala a 1M y 10M tokens (needle-in-haystack extremo).
- **mem0 «State of AI Agent Memory 2026»** — informe de progreso/benchmark.

Mapa habilidad↔dim y los HUECOS que abrió esta revisión: ver `EXIGENCIA.md §Mapa de habilidades`. Lo que faltaba
y ya se ataca: **U** (multi-hop), **V** (verbosidad/extracción), **W** (instrucciones permanentes), **K graduado**
(harness `scale` con falsos-amigos). Lo que es límite del membot y va al tester en vivo (INI-013): **abstención
query-time** (es comportamiento del LLM, no de la lectura sin-LLM) y **conflicto multi-fuente** (MemConflict) que
aún debemos añadir como sharpening de M×G.

## Mapa de cobertura (batches → dimensión) — se actualiza al añadir tandas

| Batches | Dimensión(es) | Estado |
|---------|---------------|--------|
| 1-6 | A, B, C, D, E (cimientos) | ✅ base |
| 7 | B (recencia) | ✅ |
| 8 | G (conectores) | ✅ |
| 9 | O/agenda (tareas·recordatorios) | 🟡 parcial |
| 10 | P (messy-human) | 🟡 parcial |
| 11 | C, I (resultados·estudios) | ✅ |
| 12 | J (cronología·saliencia) | 🟡 parcial (gap SOTA) |
| 13 | D, I (aprendizaje·emoción·supersede móvil) | ✅ |
| 14 | D, F (alergia aditiva·dedup) | ✅ |
| 15 | D, F (finanzas·dirección supersede) | ✅ |
| 16-18 | F (grafo conceptos: deporte/familia/finanzas/trabajo) | ✅ |
| 19-28 | F, C (categorías: viajes/tech/estudios/ocio/comida/mascotas/relaciones/vivienda/agenda) | ✅ |
| 29 | I (intereses inferidos + intenciones futuras) | ✅ |
| 30-34 | G, H (multi-fuente + índice por tipo + cuarentena) | ✅ |
| 35 | G, K, H (muchos peers de cluster — extrapolabilidad 1↔200) | 🟡 escala ligera |
| 36 | G, H, C (durables desde mensajes + cuarentena en LARGO) | ✅ |
| 37 | G, H (cluster→memoria: síntesis comprimida por peer, T170) | ✅ |
| 38 | **N** (olvido a petición: "olvida lo de X", conserva histórico) | ✅ |
| 39 | **O** (rutinas/hábitos: backstop de recurrencia) | ✅ |
| 40 | **A** (el NOMBRE: bug en vivo — estado + no exponer capas internas) | ✅ |
| 41 | **M** (contradicciones/correcciones: "no X sino Y" / "ya no X") | ✅ |
| 42 | **P** (adversarial/ruido: descarta galimatías, extrae dato enterrado) | ✅ |
| 43 | **R** (multilingüe: memoria MONOLINGÜE, traduce al idioma del operador) | ✅ |
| 44 | **Q** (cross-source síntesis: voz+whatsapp sobre un tema → recall combina) | ✅ |
| 45 | **L** (olvido/eviction: pinned intocable en poda agresiva) | ✅ |
| 46 | **S** (episódica: paste → resumen buscable, binario lazy) | ✅ |
| 47 | **K** (escala GRADUADA 100→8000 + falsos-amigos, harness `scale`) | ✅ recall 6/6, latencia ≤3ms |
| 48 | **U** (multi-hop: el recall aflora todos los eslabones para encadenar) | ✅ |
| 49 | **V** (verbosidad: telegráfico ↔ parrafada de 150+ palabras con aguja enterrada) | ✅ |
| 50 | **W** (instrucciones permanentes: km/usted/Spotify → preferencia recuperable) | ✅ |
| 51 | **J** (temporal: co-retrieval de 2 y 3 eventos fechados; fecha relativa preservada) | ✅ |
| 52 | **D** (supersede en cadena A→B→C + dedup multi-fraseo) | 🟡 **cazó T175** (slot=None → supersede/dedup parciales) |
| 53 | **P/H** (prompt-injection de peer untrusted: identidad + fence-escape → cuarentena aguanta) | ✅ anti-inyección OK |
| 54 | **K** (escala con embeddings REALES fastembed 200→2000: índice vectorial real) | ✅ recall 6/6, latencia ≤1ms |
| 55 | **T** (vocab-gap: recall por SIGNIFICADO, sinónimo→hiperónimo 2-saltos, vía `recall_probe`) | ✅ el embedding puentea vehículo→automóvil, lenguaje→python, deporte→correr, animal→golden |
| 56 | **F** (recall por CATEGORÍA: salud/trabajo/alergias → aflora el cluster sin nombrarlo) | ✅ |
| 57 | **T×K** (needle SEMÁNTICO a escala 300→3000, sin solape léxico) | ✅ embeddinggemma AGUANTA (5-6/6, ~84ms); **cazó T176**: el fallback fastembed COLAPSA (0/6 a 1500) |
| 58 | **N** (DES-OLVIDO: forget→unforget round-trip; feature `memory.unforget` implementada) | ✅ mejora hecha (machacar→detectar→mejorar) |
| 59 | **U** (multi-hop 3 SALTOS con recall_probe) | 🟡 **cazó T177** (graph_expand ~1 salto; el terminal disjunto no co-aflora) |
| 60 | **M** (conflicto MULTI-FUENTE: whatsapp vs voz sobre la misma cita) | ✅ la memoria EXPONE ambas versiones (no esconde el conflicto) |
| 61 | **W** (instrucción CONDICIONAL + REVOCADA) | ✅ mejora: `_FORGET_RE` ahora tolera coletillas "ya no…" |
| 62 | **C** (retención profunda en el corpus REAL de ~460 memorias) | ✅ lo importante (alergia/trabajo/salud) SOBREVIVE; lo trivial viejo hard-evicted (dim L, humano) |
| 63 | **S** (episódica MULTI-FICHERO: 2 docs buscables e independientes) | ✅ sin contaminación cruzada (not_want) |
| 64 | **P/H** (inyección que ordena BORRAR: peer untrusted + spam externo → "olvida/resetea") | ✅ el dato del operador SOBREVIVE (forget solo por voz del dueño) |
| 65 | **Q** (síntesis 4 fuentes: voz+whatsapp+telegram; cluster untrusted EXCLUIDO) | ✅ combina confiables, cuarentena el chisme |
| 66 | **G** (homónimos: jefa Ana vs sobrina Ana) | ✅ no-colapso (cada una por contexto); 🟡 **cazó T178** ("lista todas" incompleto por fragmentación+top-K) |
| 67 | **O** (rutina con excepción: "voy los martes" + "este martes no") | ✅ la excepción no borra la rutina; ambas coexisten |
| 68 | **D** (near-dup ≠ dup: mi móvil vs el de mi mujer) | ✅ NO se fusionan; ambos coexisten (dedup no over-merge) |
| 69 | **I** (interés que evoluciona: buceo → senderismo) | ✅ el nuevo es vigente, la historia se conserva |
| 70 | **H** (cuarentena por CATEGORÍA: chisme untrusted no aflora en "mis finanzas") | ✅ fuera del pasivo, trazable por fuente |
| 71 | **X** (invalidación implícita STALE: embarazada→di a luz; alquiler→compré) | 🟡 **cazó T179** (el estado viejo NO se invalida; ambos coexisten) |
| 72 | **E** (abstención write-side: pregunta al asistente ≠ hecho) | ✅ mejora: descarte de "¿qué tiempo…?"/"¿me recomiendas…?" (T180) |
| 73 | **R** (recall CROSS-LINGUAL: query en inglés → hecho guardado en español) | ✅ embeddinggemma multilingüe puentea es↔en |
| 74 | **J** (event ordering: 3 eventos fechados, fecha preservada) | ✅ co-retrieval de 2 con fecha; 🟡 T178 2ª manif. (3º cae del top-K; timeline abstracto no recupera) |
| 75 | **L** (REFUERZO medible: usar un recuerdo lo fortalece, access ↑) | ✅ nuevo step `weight_check`; la curva de refuerzo funciona |
| 76 | **B** (recencia "¿qué acabo de decir?" con charla intermedia) | ✅ el dato reciente sigue en el working-set del CORTO |
| 77 | **P** (STT REALISTA: homófonos/tildes/'boy'←soy) | ✅ el CORAZÓN rescata el hecho pese al ruido del STT |
| 78 | **S** (documento GRANDE, invariante LAZY) | ✅ el resumen es buscable; el cuerpo del binario NO se indexa |
| 79 | **U** (hop CROSS-FUENTE: abogado (voz)→Ramírez→jueves (whatsapp)) | ✅ ambos eslabones afloran (multi-hop cross-source) |
| 80 | **V** (parrafada 300 palabras con 2 agujas) | ✅ extrae LAS DOS; 🟡 **cazó T181** (generalizó 'concierto de Muse'→'un concierto', perdió el nombre) |
| 81 | **K** ("importante enterrado" a 5000 reales: agujas semánticas PINNED) | ✅ 6/6, ~86ms — lo importante sobrevive a gran escala |
| 82 | **M** (cadena de correcciones A→B→C) | ✅ el forget encadena (viejos fuera); 🟡 **cazó T182** (corrección sin sujeto → misatribución del valor nuevo) |
| 83 | **G** (coreferencia de apodos Alejandro/Álex/Ale) | ✅ cada alias recupera su dato; 🟡 sin coreferencia cross-alias (frontera entity-resolution) |
| 84 | **A** (SUPERSEDE en el ESTADO: location Girona→Tarragona) | ✅ el estado SOBRESCRIBE limpio (contraste positivo con T175 a nivel píldora) |
| 85 | **Q** (conflicto DENTRO de síntesis rica: coche Toyota, color gris vs blanco) | ✅ síntesis + conflicto de color visible por fuente |
| 86 | **M** (corrección de valor NUMÉRICO: PIN 4471→8890) | ✅ **MEJORA**: `_CORRECTION_RE` ahora captura valores que empiezan por dígito |
| 87 | **W** (prioridad entre 2 instrucciones: español general + inglés para código) | ✅ ambas coexisten, cada una por contexto |
| 88 | **N** (olvido DURO por voz: "bórralo del todo") | ✅ **MEJORA**: hook detecta 'del todo/sin rastro' → forget(hard) → borrado real no recuperable |
| 89 | **K** (escala EXTREMA 15.000 recuerdos, estilo BEAM) | ✅ recall 6/6, p50 5ms — aguanta el techo de volumen |
| 90 | **P** (fidelidad de la NEGACIÓN: "no tengo X" sin flip) | ✅ 'no consume alcohol', 'no tiene carné', 'hijo único' — el 'no' se conserva |
| 91 | **I** (preferencias COMPARATIVAS: "prefiero X a Y") | ✅ la dirección se conserva (té>café, cine>teatro, Pol mayor) |
| 92 | **C** (memoria ESPACIAL: "¿dónde dejé X?") | ✅ objeto→ubicación (llaves/pasaporte/mando) recuperable por el objeto |
| 93 | **F** (relaciones de PARENTESCO: "¿quién es X?") | ✅ vínculo persona↔rol, incluso indirecto (marido de la jefa→bombero) |
| 94 | **A** (datos NUMÉRICOS de perfil: altura/peso/sueldo) | ✅ cifras EXACTAS (1.83, 76 kilos, 2800) sin mutar |
| 95 | **I** (PROMESAS/DEUDAS: "le debo X a Y", "le prometí a Z") | ✅ compromisos con otros recuperables; 🟡 T178 (consulta amplia compite → gancho) |
| 96 | **C** (PROCEDIMIENTOS/secuencias: rutina gym, receta) | ✅ los pasos se recuperan (orden implícito en lista) |
| 97 | **I** (SUPERLATIVOS/favoritos: mejor amigo, película favorita, mejor viaje) | ✅ recuperables por el rol superlativo |
| 98 | **I** (aplicación IMPLÍCITA de restricción, Mem2ActBench) | 🟡 **cazó T183** (celíaco no aflora al pedir restaurante; el retriever no aplica constraints cross-topic) |
| 99 | **I** (ERRORES/malas experiencias: restaurante que sentó mal, inversión fallida) | ✅ se recuerdan para evitarlas |
| 100 | **I** (DECISIONES: "he decidido X") + **MEJORA** vocab de conceptos (dietéticos) | ✅ decisiones recuperables; celíaco/gluten→'comida' (desbloquea T183/T178) |
| 101 | **C** (eventos EMOCIONALES: día más feliz, mayor frustración) | ✅ el HECHO se recuerda; 🟡 el CORAZÓN SUAVIZA la emoción ('rabia'→'disgustó', pariente T181) |
| 102 | **O** (horario semanal DÍA-específico) | ✅ jueves→oficina, martes→teletrabajo, viernes→natación, sin conflación |
| 103 | **B** (ESTADO TEMPORAL: gripe/viaje "esta semana") | ✅ recuperable; el CORAZÓN lo manda a CORTO (efímero), no a LARGO — distingue pasajero vs permanente |
| 104 | **I** (APRENDIZAJES/habilidades: ukelele, paella, alemán) | ✅ habilidades adquiridas recuperables (a LARGO, permanentes) |
| 105 | **A** (CONTACTO/referencias: email, teléfono, URL) | ✅ strings estructurados EXACTOS (email/URL/tel intactos) |
| 106 | **I** (OBSERVACIONES/autoconocimiento) | ✅ **MEJORA**: backstop de observación ('he notado que…') → el LLM ya no las descarta |
| 107 | **O** (RÉGIMEN de medicación: pastilla mañana vs jarabe noche) | ✅ pauta con timing correcto, sin confundir mañana/noche |
| 108 | **I** (AVERSIONES con motivo: cilantro/jabón, conducir/faros) | ✅ el disgusto Y su razón se recuperan |
| 109 | **I** (METAS con plazo: cafetería en 2 años, maratón antes de 40) | ✅ meta + horizonte temporal recuperables |
| 110 | **C** (LISTAS/inventarios: compra de 3 y 4 ítems) | ✅ la lista ENTERA se recupera, ningún ítem perdido |
| 111 | **V** (hechos COMPUESTOS/anidados: 4 hechos en una frase) | ✅ descompone en 4 píldoras, cada una recuperable |
| 112 | **P** (INCERTIDUMBRE preservada: rango de fecha, "no seguro") | ✅ conserva el rango (14 y 15) y la duda; 🟡 'no me acuerdo bien' a veces se descarta (variabilidad LLM) |
| 113 | **O** (SUSCRIPCIONES/recurrentes: Spotify día 5, seguro marzo) | ✅ recurrencia + fecha recuperables |
| 114 | **A** (MÉTRICAS de salud con valores: colesterol 210, glucosa 95) | ✅ cada métrica con su cifra, sin intercambiar |
| 115 | **M** (REVERSIÓN de preferencia: "ya no bebo café") | ✅ **MEJORA**: backstop de reversión ('ya no…') → el nuevo estado ya no se pierde |
| 116 | **I** (preferencias CONTEXTUALES: verano/cerveza, invierno/vino) | ✅ cada contexto su preferencia, sin cruzar |
| 117 | **M** (corrección de UN atributo entre varios: Nuria pediatra→cirujana) | ✅ actualiza solo la profesión, sin dañar Berlín/junio |
| 118 | **P** (desambiguación de topónimos: Santiago de Chile, Guadalajara de México) | ✅ conserva CUÁL homónimo |
| 119 | **J** (razonamiento de DURACIÓN: "hace 3 años", "llevo 5 años") | ✅ la duración se conserva para calcular "¿cuánto llevo?" |
| 120 | **C** (INTERFERENCIA: dos viajes a Oporto, distinto año/acompañante) | ✅ distintos, sin blur; 🟡 T178 4ª manif. (list-all trae uno) |
| 121 | **W** (nombre preferido/apodo: Richi vs Ricardo formal) | ✅ apodo informal + registro formal coexisten |
| 122 | **I** (habilidades con NIVEL: inglés fluido, francés básico) | ✅ cada idioma con su nivel, sin intercambiar |
| 123 | **I** (preferencias por CATEGORÍA: música/cine/comida) | ✅ cada categoría su preferencia, sin cruzar |
| 124 | **C** (INVENTARIO con atributos: Seat blanco + moto Honda roja) | ✅ cada objeto con su color; 🟡 T178 (list-all no agrega) |
| 125 | **P** (cantidades APROXIMADAS: ~200 libros, ~150 invitados) | ✅ la aproximación se conserva, sin inventar exacto |
| 126 | **I** (PROCEDENCIA de un hecho: "me lo dijo el médico/cuñado") | ✅ conserva QUIÉN lo dijo, no solo el hecho |
| 127 | **J** (fechas relativas COMPUESTAS: "jueves de la semana que viene") | ✅ conserva la referencia relativa completa |
| 128 | **M** (corrección ENCADENADA + negación: empleo slotted→supersede limpio, código sin slot→coexisten T175, "ya no tengo perro") | ✅ el valor nuevo/la negación afloran; supersede limpio solo con slot |
| 129 | **V** (dato dicho «DE PASADA»: hecho real incrustado en small-talk desdeñoso) | ✅ el CORAZÓN extrae piano/jefe/alergia/móvil pese al marco "nada importante" |
| 130 | **H** (anti prompt-injection: peer untrusted spoofa identidad / inyecta tags / fence-escape) | ✅ NUNCA entra en pasivo ni recall; auditable solo por fuente |
| 131 | **G/Q** (HOMÓNIMOS por fuente + entidad con TILDE) | ✅ desambigua por source+entity, expone ambos sin fuente · ★ CAZÓ BUG: `lower()` ASCII de SQLite → fix `pylower` |
| 132 | **F** (recall por DOMINIO con varias píldoras: finanzas/salud/forma física) | ✅ co-recall por pregunta de dominio (léxico compartido, NO la categoría vacía de T178) |
| 133 | **T** (vocab-gap hiperónimo/paráfrasis: bulldog→animal, trompeta→viento, relojes→colección) | ✅ el vector puentea; ancla = token que sobrevive a la generalización del CORAZÓN |
| 134 | **R** (multilingüe cross-lingual BIDIRECCIONAL: EN→ES, ES→EN, code-switch) | ✅ el CORAZÓN normaliza al idioma del perfil; el recall cruza idioma |
| 135 | **X** (invalidación IMPLÍCITA / STALE: mudanza, dejar hábito, cambio de empleo) | ✅ el estado ACTUAL manda; slotted→supersede limpio, sin slot→el update aflora |
| 136 | **E** (ABSTENCIÓN LongMemEval: no-hecho/cavilación/pregunta descartados; condicional NO categórico) | ✅ membot no fabrica hechos; abstención plena de respuesta = LLM (tester en vivo) |
| 137 | **B** (recencia BAJO INTERFERENCIA: dato + 3 turnos de ruido) | ✅ el dato sigue en el working-set pese al ruido intermedio |
| 138 | **L** (refuerzo medible: usar un hecho sube peso/acceso) | ✅ 0.5→0.9/1.0; poda de pinned ya cubierta (no se re-testea sobre BD acumulada) |
| 139 | **S** (episódica: 2 documentos nuevos, resumen buscable, token único) | ✅ recuperable por significado; binario fuera del prompt |
| 140 | **D** (NEAR-DUP que NO es dup: hermano/primo Pedro, 2 citas, 2 tallas) | ✅ hechos parecidos-pero-distintos NO se sobre-funden; ambos afloran |
| 141 | **U** (multi-hop CROSS-FUENTE: voz↔mensajería por entidad compartida) | ✅ co-recupera ambos eslabones (jefe→Ramón→jueves; cardiólogo→Ferrán→resultados) |
| 142 | **Q** (AUTO-contradicción dentro de UNA fuente: Diego confirma y se desdice) | ✅ el índice preserva el hilo completo; la contradicción queda expuesta |
| 143 | **N** (olvido SELECTIVO/granular: olvidar 1 dato sin borrar los vecinos) | ✅ · ★ CAZÓ BUG: `forget` LIKE contiguo fallaba con posesivo mi→su → fix token-AND |
| 144 | **H** (untrusted intenta REESCRIBIR/CONFIRMAR un hecho del operador) | ✅ no reescribe ni gana confianza; el hecho del operador manda; auditable por fuente |
| 145 | **G** (extrapolabilidad a 10+ peers de cluster: índice por fuente a volumen) | ✅ disambigua por entidad sin contaminación; cuarentena untrusted aguanta a volumen (1↔200) |
| 146 | **T** (vocab-gap ABSTRACTO: concreto→categoría abstracta ansiedad/pasión/procrastinar) | ✅ el vector puentea de lo concreto a lo abstracto sin solape léxico |
| 147 | **S** (episodio CORRECTO entre varios: 4 docs, pregunta semántica por cada uno) | ✅ aflora el documento correcto por significado, sin confundirlo con los otros 3 |
| 148 | **R** (CODE-SWITCH pesado es-en: meeting/team/deadline/overtime + turno entero en inglés) | ✅ el CORAZÓN normaliza al perfil (es), el recall cruza idioma; anglicismos asentados se conservan |
| 149 | **Y** (ESTADO / UI vivo: widgets abiertos + tareas en marcha, feat 2026-07-11) | ✅ el ESTADO GUARDA lo debido (patch sin pisar) y el FlashBrain lo VE en su bloque; supersede + limpieza del canvas |
| 150 | **M** (FactConsolidation, MemoryAgentBench: mismo hecho ×N versiones → el más nuevo) | ✅ supersede determinista por slot ("no preguntes frescura al LLM"); test-time learning inmediato |
| 151 | **F** (agregación por ENTIDAD: cluster de la madre / del hermano Dani) | ✅ co-recupera el cluster por el nombre-puente, sin mezclar entidades |
| 152 | **P** (DISFLUENCIA/auto-reparación: titubeos "eh, o sea, espera, quiero decir") | ✅ el CORAZÓN extrae el hecho limpio pese al ruido conversacional |
| 153 | **J** (ORDEN temporal explícito: antes/después entre dos eventos) | ✅ co-recupera los eslabones · ⚠️ el edge de orden se pierde al descomponer (frontera T151) |
| 154 | **Y** (ESTADO combinado: PERFIL + UI vivo juntos + tareas en paralelo + limpieza) | ✅ nombre/trato/widgets/tareas viajan juntos; una tarea que acaba desaparece; el perfil persiste con UI vacía |
| 155 | **B** (CORTO: working-set ENTERO + "lo más reciente manda" en la ventana) | ✅ varias tareas de turnos distintos co-afloran; la última corrección pesa dentro del CORTO |
| 156 | **W** (conflicto/PRIORIDAD entre dos instrucciones + directivas durables) | ✅ la instrucción más nueva gana (trato slotted→supersede); unidades/música/formato recuperables |
| 157 | **O** (rutina que EVOLUCIONA: gimnasio lunes→miércoles, café→té) | ✅ el patrón ACTUAL aflora; sin slot el viejo coexiste (T175) |
| 158 | **Q** (síntesis de 4+ fuentes sobre un tema: voz+whatsapp+telegram, cluster untrusted fuera) | ✅ combina las confiables, el chisme untrusted no entra al prompt (auditable por fuente) |
| 159 | **N** (olvido por PERSONA + round-trip + olvido DURO) | ✅ · ★ CAZÓ BUG: el regex de olvido no aceptaba enclíticos ('bórrame X') → fix T186 |
| 160 | **X** (invalidación implícita por conocimiento del mundo: embarazo→parto, alquiler→compra, paro→empleo) | ✅ el estado NUEVO aflora · ⚠️ auto-invalidar el viejo = frontera STALE (necesita razonar el mundo) |
| 161 | **T** (vocab-gap peor caso: saxofón→viento, vinilos→colección, escalada→riesgo, mandarín→lengua…) | ✅ el vector puentea de lo concreto a la categoría de la pregunta |
| 162 | **C** (retención profunda / recall biográfico antiguo: primer coche, socorrista, astronauta…) | ✅ el retriever aflora datos del pasado por significado |
| 163 | **U** (multi-hop por entidad: jefa→Silvia→Fénix→septiembre; médico→días de consulta) | ✅ co-recupera los eslabones para que el LLM salte |
| 164 | **Y/B/C** (CAPSTONE 3 velocidades: UI abierta + charla reciente + hecho durable en una escena) | ✅ cada capa contiene lo suyo; el cerebro lo VE en el sitio correcto |
| 165 | **CIERRE 1000** (barrido S·H·R·G·D con anclas fuertes) | ✅ episódica, cuarentena, cross-lingual, multi-fuente y near-dup verdes al cerrar |

## Huecos PRIORITARIOS (lo que ataca lo que viene) — 2026-07-10

1. **K — ESCALA / grandes volúmenes** (la preocupación nº1): needle-in-haystack con miles de recuerdos, latencia,
   working-set overflow, lo importante enterrado. → harness de estrés dedicado (`scale_probe`).
2. **M — CONTRADICCIONES / correcciones** parciales y negaciones.
3. **N — PRIVACIDAD / olvido a petición** ("olvídate de eso").
4. **O — RUTINAS / hábitos** recurrentes.
5. **L — OLVIDO / consolidación** (parte depende de V2-019 sueño, pero se puede probar decay/pinned/eviction).
6. **Q — CROSS-SOURCE síntesis** (combinar fuentes en una respuesta).
7. **J — TEMPORAL** (reforzar el gap conocido) · **P — ADVERSARIAL** (ampliar) · **R — MULTILINGÜE**.

## PLAN 400→1000 — asignación pensada (para NO improvisar ni duplicar)

> El operador dio 1000 «para abrir la mente»: variedad y originalidad, no relleno. Esta es la asignación objetivo
> de los ~590 casos que faltan, por dimensión, priorizando sus ejes (escala, longitud de input, las 3 velocidades).
> Cada checkpoint de `EXIGENCIA.md` (cada 50) puede REBALANCEAR esto — es un plan vivo, no un contrato.

| Dim | Objetivo aprox | Qué explorar SIN duplicar (arquetipos incisivos que faltan) |
|----|---:|---|
| **K** escala | ~120 | ~~embeddings REALES~~ ✓B54; ~~5k reales~~ ✓B81; ~~importante ENTERRADO~~ ✓B81 (pinned 6/6 a 5000, ~86ms); ⛔ **recall por CATEGORÍA a escala** = 0/4 a noise 400 con embeddinggemma → NO es bug nuevo: es la frontera **T178/T183** (una categoría genérica no recupera el hecho específico sin expansión por conceptos; el ruido same-category lo tapa) → NO se añade test rojo, se ataca en sesión dedicada. PENDIENTE (filler puro, bajo valor): 15k reales, working-set overflow. |
| **U** multi-hop | ~55 | ~~cadenas de 3 saltos~~ ✓B59 (cazó T177: terminal disjunto no co-aflora); ~~hop que cruza FUENTES~~ ✓B141 (voz↔mensajería por entidad compartida: jefe→Ramón→jueves; cardiólogo→Ferrán→resultados); PENDIENTE: hop temporal. **Depende de T177** para 3+ saltos con terminal léxicamente disjunto. |
| **V** verbosidad | ~50 | ~~parrafadas de 300+ palabras con 2 agujas~~ ✓B80; ~~input telegráfico multi-hecho~~ ✓B49; ~~dato dicho «de pasada»~~ ✓B129 (hecho real en small-talk desdeñoso; el CORAZÓN no se deja engañar por "nada importante"); PENDIENTE: misma info repetida con longitudes distintas (bloqueado por T175: sin slot NO colapsa a 1 píldora — 3 fraseos = 3 facetas). |
| **J** temporal | ~55 | ~~co-recuperar dos eventos~~ ✓B51; ~~ordenar 3 eventos fechados~~ ✓B51; ~~fechas relativas~~ ✓B51; PENDIENTE: «¿qué pasó ANTES?» explícito, recencia vs importancia, fecha absoluta resuelta. |
| **T** vocab-gap | ~40 | ~~sinónimos~~ ✓B55; ~~hiperónimos 2-saltos~~ ✓B55; ~~paráfrasis~~ ✓B55; ~~needle semántico a escala 3k~~ ✓B57 (embeddinggemma aguanta 5-6/6; fastembed COLAPSA→T176). ~~hiperónimo/paráfrasis extra~~ ✓B133 (bulldog→animal, trompeta→viento, relojes→colección, fontanero-paráfrasis; ancla = token que sobrevive a la generalización del CORAZÓN). PENDIENTE: 15k reales, robustez del backend fallback. |
| **M** contradicción | ~45 | ~~CONFLICTO multi-fuente~~ ✓B60 (la memoria EXPONE ambas versiones; resolver es del LLM); ~~corrección encadenada~~ ✓B128 (slotted→supersede limpio; sin slot→coexisten, T175); ~~negación de un hecho~~ ✓B128 ("ya no tengo perro"→backstop reversión durable); ~~reafirmar tras corregir~~ ✓B128 (no reintroduce el viejo en el slot). PENDIENTE: conflicto entre dos hechos slotted distintos, corrección que cambia el TIPO del hecho. |
| **W** instrucciones | ~35 | ~~instrucción condicional~~ ✓B61; ~~instrucción que se REVOCA~~ ✓B61 (vía forget, +robustez regex); PENDIENTE: prioridad entre dos instrucciones en conflicto. |
| **D** dedup | ~35 | ~~5+ fraseos~~ ✓B52 (cazó T175); ~~supersede en cadena A→B→C~~ ✓B52 (cazó T175); ~~near-dup que NO es dup~~ ✓B140 (hermano/primo Pedro, 2 citas, 2 tallas: NO se sobre-funden). PENDIENTE: fraseos en varios idiomas. **Bloqueado por T175** (slot=None) para el objetivo dedup ≤1. |
| **F** grafo | ~35 | ~~recall por DOMINIO con varias píldoras~~ ✓B132 (finanzas/salud/forma física co-afloran por la pregunta de dominio, léxico compartido); PENDIENTE: co-ocurrencia de 3 conceptos vía concept_graph (map), categoría emergente. NOTA: la categoría genérica-vacía (sin puente léxico) es T178, no se testea en verde. |
| **P** adversarial | ~35 | ~~inyección escribe estado~~ ✓B53; ~~inyección dispara forget~~ ✓B64; ~~STT realista (homófonos/tildes)~~ ✓B77 (el CORAZÓN rescata el hecho); PENDIENTE: palabra partida letra a letra, mezcla es/en, orden de turnos roto. |
| **Q** cross-source | ~30 | ~~síntesis de 4+ fuentes~~ ✓B65 (voz+whatsapp+telegram, cluster untrusted excluido); PENDIENTE: conflicto DENTRO de la síntesis; «todo lo de la persona X» con homónimos. |
| **G** multi-fuente | ~30 | ~~índice por entity con homónimos~~ ✓B131 (★ fix `pylower` tildes); ~~20+ peers de cluster (extrapolabilidad 1↔200)~~ ✓B145 (10 peers: disambigua sin contaminación + cuarentena a volumen). PENDIENTE: email/LinkedIn/X (slots futuros). |
| **H** cuarentena | ~25 | ~~fuga de untrusted al prompt por varias vías~~ ✓B130; ~~untrusted que intenta REFORZAR/reescribir un hecho del operador~~ ✓B144 (trust-washing: ni reescribe ni gana peso; el hecho del operador manda). PENDIENTE: downgrade de trust (external→untrusted). |
| **C** largo | ~25 | retención a 500+ pasos atrás; recall tras muchas escrituras intermedias. |
| **A/B** estado/corto | ~25 | supersede de perfil; poda del CORTO (V2-019); «¿qué acabo de decir?» con ruido intermedio. |
| **N/O/L/R/S/E/I** | ~30 | ~~revocar olvido~~ ✓B58; ~~rutina con excepción~~ ✓B67; ~~decay/refuerzo medible~~ ✓B75; ~~cross-lingual recall~~ ✓B73; ~~episodio multi-fichero~~ ✓B63; ~~abstención write-side~~ ✓B72; ~~interés que evoluciona~~ ✓B69. PENDIENTE: decay por TIEMPO (no solo refuerzo), olvido natural medible. |

**Regla de oro del plan:** antes de escribir la tanda N, mira aquí la dim más floja vs su objetivo, y coge el
PRIMER arquetipo de su celda que aún no exista. Al usarlo, TÁCHALO (edita esta celda). Así 590 casos salen
pensados, no improvisados.

## EXIGENCIA cada 50 (obligatorio)

Cada vez que `len(CASES)` cruza un múltiplo de 50, ANTES de seguir se pasa el **`EXIGENCIA.md`** (checklist de
calidad: ¿duplicamos? ¿variedad? ¿qué falta? ¿cambio de approach? ¿buscar munición web? ¿mejorar la memoria?) y se
escribe su veredicto fechado en INI-013. De 400 a 1000 son 12 controles. No es opcional.

## Reglas para no duplicar (LÉELAS antes de añadir una tanda)

1. **Cada caso lleva `dim`** con su código (los nuevos; los legacy se mapean por lote arriba).
2. **Antes de escribir una tanda**, corre `--coverage` y elige la dimensión MÁS floja del bloque de huecos.
3. **Un caso = un modo de fallo concreto.** Si dos casos cazan lo mismo, sobra uno.
4. **Ancla inequívoca**: el `marker`/`want` debe ser una palabra que SOLO aparezca en el dato objetivo (evita
   colisiones tipo "barcelona" ciudad vs "FC Barcelona"). Ver el histórico de anclas problemáticas en el git log.
5. **Autocontenida** salvo que la dimensión sea de RETENCIÓN PROFUNDA (C) o CRONOLOGÍA (J), que exigen replay largo
   (`--range 0 N`), no aislado.
6. **Incisivo, no amable**: busca romper la memoria (edge cases, ruido, contradicción, escala), no confirmarla.
7. Al añadir una tanda, **actualiza el mapa de cobertura** de este doc y su nota en INI-013 / el batch header.
