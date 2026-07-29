# zaelar — subsistema de MEMORIA (arquitectura v2 «Colmena»)

> **Estado:** OPERATIVA, en evolución (V2-002 substrato · V2-011 latencia · V2-013 corazón de escritura con **LLM
> local que destila píldoras** · V2-014 visor+observabilidad · V2-019 sueño+aislamiento tester, pendiente ·
> auditoría 2026-07-14: registro canónico de slots + contrato v2 `value`/`change` + vía externa de workers con gates ·
> V2-042: RAILS proyectan runs vivos a `state.rails` + writeback de música `ingest_message(source="music")` ·
> **V2-056** (2026-07-20): F1 robustez del núcleo [decay POR VENTANA + prune_invalid + forget duro real + enforcement
> de firma de embedding + fail-open que no ensucia] + **sueño PROFUNDO «fase REM»** (`memory/rem.py`) + **tool
> `recall`** del FlashBrain + **dossier v2** de `compose_context` + modelos del módulo elegidos POR BENCHMARK
> (`zaelar-model-benchmarks.md §12`)).
> Actualizado 2026-07-20. Módulo top-level `memory/` — ver §Módulos.
> **Regla de oro de latencia:** **LLM al ESCRIBIR (off-hot-path), queries DIRECTAS al LEER (sin LLM en el camino).**
> **Diagrama vivo:** `/architecture` → pestaña **Memoria** (el diagrama central v2 solo enlaza aquí; sin duplicar el detalle).
> **Fuente de verdad** del *cómo se construye*: este documento. Para EMPEZAR a trabajar la memoria, leer sí o sí:
> §«Lectura en el turno — TRES velocidades», §«El CORAZÓN de escritura» y §«Observabilidad de la memoria».

Memoria **tipo humana**, con el **SUBSTRATO 100% local** dentro del proceso (SQLite + lectura + embeddings +
reranker: sin infraestructura externa, multiplataforma; móvil a futuro, tenerlo en mente). Es **nuestra** — nunca
una caja negra. ⚠️ Matiz V2-056: los **LLM de ESCRITURA** (CORAZÓN + síntesis REM) van hoy por **API externa
por decisión del operador** — ver §Principios.

## Principios de diseño (decididos, no reabrir)

- **Local, un solo fichero.** Todo vive en un único SQLite `zaelar.db`. Sin servidor, sin broker. **Matiz de
  alcance (decisión del operador 2026-07-17, no un abandono del principio):** el SUBSTRATO sigue 100% local —
  BD, lectura a 3 velocidades, embeddings (embeddinggemma vía Ollama) y reranker (fastembed/CPU). Los **LLM de
  ESCRITURA** (el CORAZÓN destilador + la síntesis del sueño REM) van por **API externa** por regla explícita del
  operador («memoria SIEMPRE OpenAI»; confirmado por benchmark, `zaelar-model-benchmarks.md §12`): la calidad de
  escritura es la palanca nº1 del recall y el modelo externo la gana con claridad. La **opción local** (qwen vía
  Ollama) sigue disponible por config (`§memory.mem_processor_*`) para quien priorice privacidad/offline.
- **Inserción por cola async — puede ser lenta.** Todas las fuentes escriben en una **cola**; solo la cola
  (un **único escritor**) toca la BD → cero colisiones de escritura. Los lectores van en **WAL** sin bloquear.
- **Búsqueda en milisegundos.** Es la **ruta caliente**: llega un prompt y hay que componer el **contexto mínimo**
  lo más rápido posible.
- **Escritores:** FlashBrain, el agente de memoria del SlowBrain, y los widgets (p. ej. mensajería vuelca lo
  entrante). **Lo irrelevante se descarta al vuelo**; lo relevante se guarda.
- **MONOLINGÜE — la memoria vive en el IDIOMA DEL OPERADOR** (decisión 2026-07-10, no reabrir). El sistema entero
  se adapta a UN idioma (el de la persona: castellano por defecto; si habla alemán, todo pasa a alemán — ver
  `voice/engine/core/langs.py`, `ZAELAR_LANGUAGE`). La memoria NO es multilingüe por dentro: el **CORAZÓN destila
  cada píldora en el idioma canónico** (`state.language`), **traduciendo** lo que el operador diga en otro idioma
  — y **nunca descarta un dato durable por venir en otro idioma** (`nucleo/mem_processor._render`). Así la LECTURA
  es siempre mismo-idioma (cero *gap* cross-lingual, cero complejidad de indexar N idiomas). El FlashBrain SÍ
  **entiende** varias lenguas (STT + modelo) y sus gates/heurísticas son es/en tolerantes, pero lo que se GUARDA y
  se RECUERDA queda en el idioma del operador. *Por qué:* una memoria multilingüe multiplica el coste (embeddings
  y recall cruzando idiomas, duplicados por lengua) sin aportar al caso real — un operador con su idioma.

## Capas (memoria tipo humana)

- **Estado** — la parte VARIABLE del contexto que **se inyecta SIEMPRE en el prompt, sin búsqueda** (lectura de
  tabla fija, µs), frente a la parte FIJA del núcleo (instrucciones/objetivo). Es el "lo de hace dos horas está
  prácticamente en contexto". Lleva: nombre(s) nuestro y de la persona, idioma (castellano), reglas de trato
  (directo vs elaborado…), dónde vive, temas hablados, y el **CONTEXTO DE UI VIVO — lo que el operador tiene
  DELANTE ahora mismo**: `open_widgets` (widgets abiertos en el canvas), `activity`/`sessions` (tareas/sesiones del
  SlowBrain en marcha) y **`rails`** (V2-042: runs vivos de los RAILS del FlashBrain — qué se busca/suena y los
  fallos AISLADOS `sin_resolver` reanudables — proyectados por `nucleo/rails.py`, se pintan como "Rails en curso").
  Con eso el cerebro resuelve "modifica/abre el widget de X" mirando lo que hay en pantalla — si está
  abierto o es el único, actúa sin preguntar. `open_widgets` lo escribe el frontend (autoritativo del canvas,
  `POST /api/canvas/state` desde `desktop._persist()`); `activity`/`sessions` los escribe el dispatcher del
  SlowBrain; `rails` los proyecta `nucleo/rails.py`. Y **`rules`** (V2-046 A1) = las **USER RULES**: reglas de
  comportamiento que el operador impone hablando ("sé más directo", "responde solo sí o no") — nace en blanco,
  persiste entre sesiones (≠ directiva de sesión). Las escribe el provider al reconocer la tool
  `set_style_directive` vía `memory.add_user_rule` (dedup por texto normalizado, cap 8, la más reciente manda) /
  `memory.remove_user_rule` (match difuso, "olvida esa regla", guard determinista `router.looks_like_rule_removal`);
  las lee `compose_state §B` como línea "REGLAS DEL OPERADOR" (con `rules` vacío el prompt es byte-idéntico). Es la
  capa APRENDIDA frente a las BRAIN RULES (genética primigenia, ver `zaelar-architecture.md §5e`). Todo es
  visible en el mapa de la memoria (columna ESTADO). Esquema en `memory/state.py`.
- **Corto plazo = memoria RECIENTE (corto y recencia = EL MISMO módulo, UN solo formato)** — decisión del operador
  (2026-07-10): están tan relacionados que separarlos sería DUPLICIDAD. Es **una sola** memoria reciente, en
  **formato MIXTO** (menos eficiente en almacenamiento, pero simple y suficiente): las filas `level='short'` que ya
  se **leen ENTERAS** al prompt (`recent_short` → bloque "Conversación reciente"). Ese mismo bloque responde a la
  vez "¿qué acabo de decir?" (lo más reciente) y "¿de qué hemos hablado / de qué va esto?" (conducir la
  conversación / memoria reciente). **NO se crea un dígest aparte ni se usa `state`** (el ESTADO es permanente, no
  tiene que ver con la última hora). Ya FUNCIONA hoy vía `recent_short`. Refinamientos (no módulos nuevos):
  guardar el turno comprimido en vez del par crudo (V2-013 T148, eficiencia) y el **decaimiento de detalle por
  antigüedad** vía consolidación (V2-019 T149: minutos casi literales → hora resumida → ayer titular → atrás nada,
  o promovido a LARGO). Cubre conversación Y actividad (ficheros, widgets).
- **Medio plazo** — resúmenes de sesión; el corto que sobrevive se archiva aquí y luego a largo.
- **Largo plazo / almacén** — recall semántico + hechos durables.
- **Continuidad de tarea** — journal con estado (pendiente / en progreso / hecho): "¿cómo va aquella tarea?".
- **Episódica lazy-loaded** — ficheros/PDF subidos. Se custodian con un **resumen embebido** que SÍ participa en la
  búsqueda; el fichero completo solo se carga bajo orden ("consulta el informe") o si el retriever lo selecciona.
  Nunca en contexto por defecto.

## Estados por SCOPE (una dimensión distinta de las "Capas" — auditoría 2026-07-26)

Las "Capas" de arriba organizan la memoria por **VELOCIDAD/permanencia** (estado µs → corto → medio → largo →
episódica). Hay una segunda dimensión, ortogonal, que el código ya construye pero que ninguna doc unía en un solo
sitio hasta ahora: el **SCOPE** — de QUIÉN/QUÉ es un dato de estado. Tres anillos, de más amplio a más estrecho:

1. **Estado GLOBAL del operador** (`memory/state.py`, tabla `state`, fila única `id=1`) — la conciencia de sí mismo
   y del entorno que el FlashBrain lleva SIEMPRE en el prompt: identidad/misión, idioma, trato, ubicación,
   `rules` (reglas de estilo del operador), `open_widgets`/`activity`/`sessions`/`rails` (contexto de UI vivo),
   `security` (flags duras tipo `secrets_voice`). Hay UN solo operador y UNA sola fila — este es el anillo que
   comparten voz y chat.
2. **Estado por-RELACIÓN** (una conversación de cluster con OTRO agente) — vive en DOS piezas complementarias,
   ambas indexadas por `(cluster, peer)`, nunca mezcladas con el anillo 1:
   - **La cápsula** (`connectors/meshkore/capsule.py`, tabla genérica `sys_kv` bajo la clave
     `capsule:<cluster>:<peer>`): estado ESTRUCTURADO de la relación — objetivo (`objective`, SOLO lo fija el
     operador, tool `set_cluster_objective`), fase (saludo→sondeo→trabajo→cierre), bucles abiertos, contadores de
     atasco (`turns`/`no_progress`), el medidor de balance de recursos (`given`/`received`/`offloads`/`code_out`),
     el pacto negociado (`pact`) y flags de guard (`_objective_gate_notified`). `sys_kv` es el mecanismo GENÉRICO
     de estado scopeado que no es la conciencia del operador (lo reusan también el consolidador y la fase REM
     para sus propios marcadores) — no es una tabla nueva por cada scope, es UNA tabla clave→JSON con prefijos.
   - **El dossier** (`connectors/meshkore/mem_ingest.py`): a diferencia de la cápsula (números/flags), esto es
     PROSA — una síntesis evolutiva de "de qué habéis hablado", destilada por un modelo LOCAL tras cada
     intercambio y guardada como una píldora NORMAL de la memoria (`slot="cluster:<cluster>:<peer>"`,
     supersede-exacto → una sola fila viva) pero **CUARENTENADA** (`trust="untrusted"`): nunca entra en el
     `recent_short`/recall pasivo del operador, solo aflora por consulta explícita (`recent_by_source`). La
     cápsula y el dossier se fusionan en un único bloque de texto (`capsule.compose()`) que se antepone a CADA
     turno de esa relación — es "lo que un humano tendría en la cabeza al retomar una conversación con alguien
     concreto". Sobrevive a un reinicio del servidor (ambos viven en `zaelar.db`).
3. **Estado por-TAREA** (una sesión de Brain Worker en marcha) — `nucleo/workers/session.py::SessionRecord`, en
   el **registro RAM** `nucleo/dispatch.py::_SESSIONS` (fuente de verdad, §V2-038). Lleva `goal`/`kind`/`phase`/
   `status`, la cola de inyecciones pendientes, y observabilidad rica (`plan`/`done`/`pct`/`steps`). Es
   DELIBERADAMENTE efímero — no vive en `zaelar.db`, muere con la sesión o el proceso — por tres razones: (a) es
   literalmente proceso en marcha, no un hecho a recordar; (b) solo importa mientras corre (nadie pregunta "¿en
   qué fase estaba la tarea de ayer que ya terminó?", solo "¿cómo va la de ahora?"); (c) mezclarlo con la memoria
   durable inflaría la BD con miles de filas de progreso transitorio. Dos puentes lo conectan con los anillos
   1-2 sin persistirlo entero: **arriba** — `nucleo/loop.py` proyecta el registro RAM al anillo 1 (`state.sessions`,
   ~1 Hz) para que el FlashBrain SEPA que hay tareas en marcha y pueda dirigirles follow-ups; **al terminar** — SOLO
   el resultado final, si `ok=True`, se escribe como una píldora normal y durable vía `memory_agent.remember()`
   (con procedencia `meta.source="worker:<id>"`) — el proceso desaparece, el HECHO que produjo queda. Una
   sub-pieza especial (`dispatch._WEB_RESUME`, también RAM) guarda lo mínimo para REANUDAR una tarea web
   incompleta (id de pestaña + `native_session_id` de Claude Code) — tampoco sobrevive a un reinicio del server,
   solo a que el propio worker muera a mitad. El propio **Claude Code CLI** mantiene, fuera de nuestra memoria,
   su histórico de sesión nativo en disco (`--resume`) — un CUARTO nivel, externo, que `nucleo/workers/
   claude_session.py` aprovecha para continuidad de RAZONAMIENTO sin que nuestra memoria tenga que guardarlo.

**Por qué tres anillos y no uno solo aplanado:** cada uno responde a una pregunta distinta y tiene un ciclo de
vida distinto — "¿quién eres y qué tienes delante AHORA?" (anillo 1, vive mientras exista el operador),
"¿de qué va mi relación con ESTE agente?" (anillo 2, vive mientras dure la colaboración con ese peer, sobrevive
reinicios), "¿cómo va ESTA tarea concreta?" (anillo 3, vive lo que dure el proceso). Aplanarlos en una sola tabla
mezclaría PII del operador con contenido de un peer no confiable (rompería la cuarentena) y llenaría el estado
global de ruido transitorio de tareas ya terminadas. La regla de aislamiento es la misma que en el resto del
sistema: **scope-partido, misma memoria física, JAMÁS mezclado en el prompt.**

## Tecnologías y versiones (verificadas 2026-07-08)

| Pieza | Versión fijada | Rol / nota |
|---|---|---|
| **SQLite** | `3.53.3` | Base única (`zaelar.db`); **WAL** para leer mientras se escribe. **FTS5 incluido** en la amalgama estándar. |
| **sqlite-vec** (ext. C, `asg017`) | `v0.1.9` estable | Vector; **fuerza bruta** = 1-5 ms a decenas de miles de recuerdos. (Línea `0.1.10-alpha` añade índices ANN si algún día hiciera falta.) |
| **sqlite-vec** (pip) | `0.1.9` | Carga la extensión en el `sqlite3` de Python (`sqlite_vec.load(conn)`). `pip install sqlite-vec` (sin `--pre`) da 0.1.9. |
| **FTS5** | incluido en SQLite | Keyword exacto; se fusiona con el vector por RRF. |
| **Embeddings locales** | `embeddinggemma` · **768 dims** | Google, vía **Ollama** (≥0.11.10) — **multilingüe** (bueno para castellano), on-device, **Matryoshka** (truncable a 512/256/128 para ahorrar en SQLite). Fallback probado: `nomic-embed-text v1.5` (768). Sin coste por inserción. |
| **Embeddings sin server (alt.)** | `fastembed 0.8.0` | ONNX-Runtime, sin server/GPU. Modelo multilingüe p. ej. `intfloat/multilingual-e5-small` (384) o `BAAI/bge-m3` (1024). |
| **RRF** | `k = 60` | Reciprocal Rank Fusion (Cormack et al. 2009; default de Elastic/OpenSearch/Azure/Mongo Atlas). `score = Σ 1/(k+rank)`. |
| **Reranker** (V2-030) | `jina-reranker-v2-base-multilingual` · fastembed 0.8.0 | Cross-encoder ONNX/**CPU** (cero GPU) que reordena el top-N del RRF leyendo query+recuerdo juntos → recall@1 41.6→56.2%. **Local por defecto**, model-agnostic (`config/v2.py` §`memory`): alt. `openai` (LLM listwise, techo) / `cohere`/`voyage` (slots). Solo recall LARGO, off-hot-path, fail-open. |

**Alternativa móvil / baja memoria (futuro):** **SQLite-Vector de sqlite.ai** (`sqliteai/sqlite-vector`, Marco
Bambini) — extensión de búsqueda vectorial cross-platform orientada a móvil/embebido (~30 MB RAM por defecto) con
cuantización fuerte (Float32/16, BF16, Int8/UInt8, 1-bit, TurboQuant 2/3/4-bit). Distinta de `asg017/sqlite-vec`.
**Decisión:** `sqlite-vec` por defecto (simplicidad, un fichero); reevaluar `SQLite-Vector` si priorizamos móvil.

## Schema SQLite (`zaelar.db`)

```sql
-- Estado: fila única, SIEMPRE en el prompt, sin búsqueda (µs)
CREATE TABLE state (
  id   INTEGER PRIMARY KEY CHECK (id = 1),
  data JSON NOT NULL          -- nombres · idioma · reglas de trato · ubicación · recientes · temas
);

-- Recuerdos (corto/medio/largo). Cada uno es una PÍLDORA: dato canónico (`text`) + metadatos. Núcleo del
-- olvido-por-peso + refuerzo. `slot`/`meta` = schema v2 (V2-013).
CREATE TABLE memories (
  id            INTEGER PRIMARY KEY,
  level         TEXT NOT NULL,      -- 'short' | 'mid' | 'long'
  kind          TEXT NOT NULL,      -- 'profile' | 'fact' | 'pref' | 'event' | 'msg' | 'summary' | 'insight' | 'conv' | 'result'
  text          TEXT NOT NULL,      -- ENUNCIADO CANÓNICO (lo destila el procesador LLM; es lo que se embebe/indexa)
  importance    REAL DEFAULT 0.5,   -- I0 base (por tipo) — relevancia CON contexto de la situación del operador
  weight        REAL DEFAULT 0.5,   -- peso VIVO: sube con el uso, baja con el decay
  access_count  INTEGER DEFAULT 0,
  last_access   INTEGER,            -- epoch (para recencia y decay)
  ttl_days      REAL,               -- NULL = infinito (hechos inmutables)
  pinned        INTEGER DEFAULT 0,  -- 1 = NUNCA se borra (ej: clave del ledger)
  valid         INTEGER DEFAULT 1,  -- 0 = superseded por otro
  superseded_by INTEGER,
  slot          TEXT,               -- v2: clave canónica del hecho SINGULAR (operator.name, goal.current…) → supersede/dedup EXACTO sin LLM
  meta          TEXT,               -- v2: píldora JSON libre (entity/attribute/source/said_at/path/raw…) — no toca el hot path; alimenta visor/grafo
  created       INTEGER NOT NULL,
  updated       INTEGER NOT NULL
);
-- `slot` da el "el más reciente MANDA" DETERMINISTA: al insertar un hecho con slot, el writer invalida el vigente
-- con el mismo slot (o lo REFUERZA si el texto normalizado es idéntico → cero duplicados). SCHEMA_VERSION=2;
-- migración ALTER idempotente y NO destructiva en `memory/db.py`.
-- V2-038 retest (2026-07-14), dos endurecimientos del writer (`memory/writer.py`):
--   (1) `canon_slot()` — NORMALIZACIÓN de alias: el CORAZÓN (LLM) emitía slots a su aire ('location',
--       'ubicación'…) mientras la heurística usaba los canónicos ('operator.location') → DOS linajes del mismo
--       hecho que nunca se supersedían (Soria+Valencia+Bilbao vigentes A LA VEZ). El writer es el único punto de
--       paso → todos los alias colapsan al canónico ahí, para TODOS los escritores.
--   (2) el supersede invalida TODOS los vigentes del slot (antes LIMIT 1): si por cualquier vía (alias previos,
--       unforget, legacy) coexisten 2+ vigentes, la siguiente escritura los colapsa — AUTO-CURATIVO.
-- Auditoría de memoria (2026-07-14, cierre de fondo del retest):
--   (3) el VOCABULARIO de slots vive en el REGISTRO ÚNICO `memory/slots.py` (SlotSpec: clave + alias + campo de
--       state + flag identity). Lo consumen writer (canon_slot), memory_agent (_IDENTITY_SLOTS/_PATCH_TO_SLOT,
--       derivados) y el prompt del procesador (catálogo GENERADO) → las tres capas no pueden divergir. El mapa
--       _SLOT_ALIASES hardcodeado del stopgap murió aquí. Slots namespaced (cluster:*, navegador.session.*,
--       <widget>:<clave>) pasan lowercased/stripped sin registrarse.
--   (4) el SELECT de vigentes desempata por id (updated tiene resolución de segundo — mismo fix que recent_short).
--   (5) el consolidador añade `heal_slots()`: normaliza slots LEGACY (alias/mayúsculas pre-normalización) y
--       colapsa multi-vigentes del stock existente en cada ciclo de sueño (la pareja del auto-curativo del writer).
--   (6) 2ª auditoría (2026-07-14, hallazgos del auditor): el SELECT del supersede EXPANDE por ALIAS
--       (`slots.equivalent_keys`): `operator.location` colapsa también un `location`/`ubicacion` crudo que quedara
--       sin normalizar → el colapso por slot es INMEDIATO, no espera al sueño (heal_slots). Cierra el residuo de
--       "dos píldoras del mismo hecho con claves distintas conviviendo".

-- Vector (sqlite-vec). Fuerza bruta a nuestra escala = ms.
CREATE VIRTUAL TABLE vec_memories USING vec0(
  memory_id INTEGER PRIMARY KEY,
  embedding FLOAT[768]              -- embeddinggemma (truncable por Matryoshka)
);

-- Keyword exacto (FTS5, incluido en SQLite).
CREATE VIRTUAL TABLE fts_memories USING fts5(text, content='memories', content_rowid='id');

-- Grafo como aristas en el MISMO fichero (nada de Neo4j).
CREATE TABLE edges (
  from_id INTEGER NOT NULL,
  to_id   INTEGER NOT NULL,
  type    TEXT NOT NULL,           -- 'about' | 'same_person' | 'caused' | 'refines' ...
  weight  REAL DEFAULT 1.0,
  PRIMARY KEY (from_id, to_id, type)
);

-- Episódica lazy: ficheros/PDF. Solo el RESUMEN (fila en memories) busca.
CREATE TABLE episodic (
  id        INTEGER PRIMARY KEY,
  path      TEXT NOT NULL,         -- ruta local al fichero
  summary   TEXT NOT NULL,
  memory_id INTEGER,               -- resumen indexado en vec/fts vía memories
  bytes INTEGER, mime TEXT, created INTEGER
);

-- Continuidad de tarea.
CREATE TABLE journal (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL,
  status TEXT NOT NULL,            -- 'pending' | 'in_progress' | 'done'
  detail TEXT, created INTEGER, updated INTEGER
);
```

## Retriever híbrido (ruta caliente · ms)

El **estado** se inyecta siempre (sin búsqueda). Para lo demás: vector (sqlite-vec) **∥** keyword (FTS5) en
paralelo, fusión **RRF**, y orden por score ponderado.

```
score = α·relevancia_semántica + β·recencia + γ·importancia + δ·peso_de_uso
por defecto:  α = 0.45   β = 0.25   γ = 0.20   δ = 0.10     (ajustables por perfil)
RRF:          rrf(doc) = Σ_listas 1 / (k + rank_lista(doc))     con k = 60
```

```python
def query(prompt, budget_tokens):
    ctx = [ state.read() ]                      # SIEMPRE, sin búsqueda (µs)
    q   = embed_local(prompt)
    vec = vec_search(q, k=40)                   # sqlite-vec, fuerza bruta, ms
    kw  = fts_search(prompt, k=40)              # FTS5
    cand = rrf(vec, kw, k=60)                   # fusiona rankings
    for m in cand:
        m.score = A*m.rel + B*recency(m.last_access) + G*m.importance + D*m.weight
    top = sort_desc(cand, key=score)
    top = rerank(prompt, top)                    # RE-RANKING (V2-030): cross-encoder reordena el top-N, fail-open
    top = graph_expand(top, edges)              # opcional: vecinos relevantes (top-K)
    emit("memory.reinforce", ids(top))          # refuerzo async (no bloquea)
    return pack(ctx + top, budget_tokens)       # trunca al presupuesto
```

### Re-ranking del recall LARGO — model-agnostic, local por defecto (V2-030)

A ESCALA (cientos de recuerdos) el embedding local (bi-encoder, vectores independientes) ordena "borroso": la
respuesta correcta suele estar en el top-10 pero NO en el top-1/3. Un **reranker** (cross-encoder) vuelve a puntuar
cada candidato **leyendo query+recuerdo JUNTOS** → sube el correcto. Es la mayor palanca de recall por el menor
coste. Medido en `tests/e2e/memory/bot/scale_eval.py` (442 durables, 281 queries de recall largo):

| | baseline | **local (jina-v2-multi)** | openai (gpt-4o-mini) |
|---|---|---|---|
| recall@1 | 41.6% | **56.2%** | 64.8% |
| recall@3 | 62.3% | **68.7%** | 69.0% |
| recall@5 | 71.9% | **74.4%** | 73.0% |
| MRR | 0.544 | 0.642 | 0.686 |
| lat p50 | 114ms | 260ms | 849ms |

**Arquitectura** (`memory/rerank.py` + `memory/rerank_local.py`, config `config/v2.py` sección `memory`): mismo
patrón LLM-agnostic que el routing del cerebro (`fast`/`code_agent`) — **proveedor CONFIGURABLE por la UI/config,
local por defecto, cloud = cambiar `rerank_provider`**. Proveedores: `local` (default, fastembed `TextCrossEncoder`
`jina-reranker-v2-base-multilingual`, **ONNX/CPU → cero contención con la GPU** que ya cargan STT+TTS) · `openai`
(LLM listwise, o cualquier endpoint OpenAI-compatible — techo de calidad, datos salen a la nube) · `cohere`/`voyage`
(slots para APIs de rerank dedicadas) · `off`.

**Invariantes** (respetan la regla de oro de latencia): SOLO en la ruta LARGO, **fuera del hot path** (el recall
largo ya va bajo demanda + `asyncio.to_thread`) — **ESTADO/CORTO NO se tocan** (siguen lectura directa µs sin
modelo). **FAIL-OPEN duro**: error/timeout/ausencia de modelo → se devuelve el orden del retriever intacto (nunca
rompe ni bloquea). El reranker **no es generativo** (reordena candidatos ya recuperados, no inventa → no viola la
no-alucinación). Se funde con recencia/importancia (`rerank_blend` 0.85) para no hundir un hecho recién dicho. El
modelo se **calienta en el arranque** (`nucleo/flash/prewarm._warm_rerank`) → la 1ª consulta con recall no paga la
carga en frío. Observabilidad: `status()` (proveedor/modelo/latencia).

> **Subir el techo del recall — iniciativa `V2-031` (memoria de fidelidad máxima).** El reranker local cierra la
> mayor parte del hueco de ORDENACIÓN, pero el techo real es `found@10` (~82%): lo que el retriever ni trae. La
> T1 de V2-031 midió las palancas y **reordenó las prioridades con datos** (ver `zaelar-model-benchmarks.md §6/§7/§8`
> y `tests/e2e/memory/bot/RESEARCH.md`):
> - ❌ **Un embedding más FUERTE NO es la palanca** (hallazgo T1): `bge-m3` (1024d SOTA multilingüe) ≈ embeddinggemma
>    (768) en found@10. El eje NO es la calidad del bi-encoder. *(Se dejó la abstracción provider-driven de dim +
>    `memory/reembed.py` para poder cambiarlo, pero no mejora el recall.)*
> - ✅ **WRITE-completeness** — el diagnóstico de los fallos reveló que la mayoría de los "no recuperados" **no
>    están guardados** (el CORAZÓN los descartó o quedaron superseded), no son fallos de retrieval. Endurecer qué se
>    considera durable es la palanca #1.
> - ✅ **Retrieval de lo guardado** — pool más profundo (k) + **índice de PARÁFRASIS al escribir** (reformulaciones
>    de la píldora → superficie para el vocab-gap T150, off-hot-path, sin LLM al leer) + el grafo de conceptos.
> - ✅ **Memoria AUTO-EVALUATIVA continua** (T5, la idea del operador) — un lazo *sleep-time* que se auto-sondea,
>    detecta hechos no recuperables y los **REPARA** (refuerza, añade aristas, indexa paráfrasis, marca re-embed).
> - ✅ **Consolidación SEMÁNTICA** — cablear el hook `summarize_fn` (hoy no-op, V2-006): fusionar píldoras
>    casi-duplicadas por embedding descongestiona el espacio vectorial. Y **aristas temporales** (Graphiti, T151).
> - 🔒 **Reranker/embedding EXTERNO** = solo tier PREMIUM (nunca default, insostenible en coste): `rerank_provider=`
>    `openai`/`cohere`/`voyage`, o los mismos modelos LOCALES en nuestro **VPS con GPU**. Ya enchufado por config.
>
> ⚠️ **Caveat de método (V2-031 T1):** el test bot SIEMBRA con embeddings `hash` (léxicos, deterministas y rápidos,
> `runner.py:702`); medir el recall SEMÁNTICO exige **re-embeber** el corpus con el modelo real (embeddinggemma/
> bge-m3) por AMBOS lados — lo hace `tests/e2e/memory/bot/embed_bench.py`. No comparar query-semántica contra
> vectores-hash (mismatch de espacio). En PRODUCCIÓN se escribe siempre con embeddinggemma.

**Grafo de CONCEPTOS** (T126, organiza la memoria conceptualmente — lo pidió el operador): al ESCRIBIR, el
CORAZÓN etiqueta cada píldora durable con 1-3 `concepts` ligeros (salud/finanzas/deporte/familia…); el writer
crea/reusa un **NODO-concepto** (fila `kind='concept'`, con su fila FTS+vector → recuperable) y enlaza
**píldora↔concepto** en `edges` (bidireccional, cap 3 conceptos/píldora). Al LEER, una query de CATEGORÍA
("¿cómo va mi salud?") casa el nodo por FTS y **`graph_expand`** aflora su cluster (alergia+operación+hábitos) —
**SIN LLM**, traversal directo. Los vecinos de un nodo-concepto apenas se descuentan (`concept_discount`, y los
conceptos se procesan primero) porque SON la respuesta a la categoría. Ataca T150 (el hecho aflora por la arista
`sobre→salud`, no por embedding plano). Emergente y ACOTADO. Se puebla al escribir (off-hot-path), se lee por
traversal directo → encaja con la regla de oro.

> **Nota de decisión (substrato vs. librería externa):** el substrato es SQLite + sqlite-vec + FTS5 + RRF + `edges`
> — los MISMOS primitivos (de producción) que usan Zep/Graphiti/Mem0 por debajo; el "grafo" son ~60 líneas sobre
> la tabla `edges` que YA existía, NO un motor nuevo. Las alternativas "con garantías" (Zep/Graphiti→Neo4j,
> Mem0-grafo→Neo4j, Letta) rompen las restricciones DURAS de zaelar: 100% local/offline, core SIN Docker, un
> proceso/fichero, y **cero LLM en el read path** (la regla de oro de latencia de voz — casi todas meten LLM en el
> search). Seguimos robando IDEAS del SOTA (aristas temporales de Graphiti para T151, linking emergente de A-MEM),
> no su infra. Se re-evaluaría solo ante un pivote a **SaaS cloud multi-tenant**.
>
> **Re-evaluación puntual (2026-07-23):** revisado el plugin Mem0 para Pi Code (memoria SaaS para agentes de
> código: scopes project/session/global por git-root, captura automática, "dream consolidation"). Confirma la
> decisión de arriba — es un wrapper cloud genérico para OTRO caso de uso (memoria de proyecto de un agente de
> código, no memoria personal de un operador de voz); nuestro retriever (vec+FTS+RRF+reranker+grafo) y el CORAZÓN
> (slot determinista + gates de precisión + REM) son más sofisticados que lo que documentan para ese plugin, y
> somos 100% locales frente a su SaaS. Única idea con algo de mordida, sin construir: su consolidación gatea por
> **3 condiciones** (tiempo O nº-sesiones O volumen); la fase REM de aquí solo gatea por tiempo
> (`rem_every_hours`). Añadir gates de nº-sesiones/volumen junto al de tiempo sería un refinamiento barato si algún
> día el volumen de escritura crece más rápido que la cadencia diaria — no hay señal hoy de que haga falta.

**Gate de RECALL robusto** (`prompt.needs_recall`, tanda 29): decide si el turno dispara `compose_recall` (el
retriever, off-loop). Antes era una WHITELIST de frases que había que ampliar sin fin. Rediseño: dispara ante
CUALQUIER pregunta con sustancia (`¿?`/WH + ≥2 palabras) o imperativo de recuerdo ("cuéntame de…", "recuérdame…"),
y NUNCA en saludo/asentimiento/charla trivial (`_TRIVIAL_RE`). Sesga a RECORDAR: un falso positivo = una query
off-loop que el LLM ignora; un falso negativo = cerebro amnésico. + un backstop determinista mapea keywords→concepto
(`memory_agent._derive_concepts`) cuando el LLM heart no etiqueta, garantizando cobertura del grafo por categoría.

**Mejoras de recuperación validadas con el test bot** (V2-013, `tests/e2e/memory/bot/`, tandas 7-15):

- **FTS con STEM por prefijo** (`retriever._fts_query`): el español es muy flexivo y el CORAZÓN canonicaliza
  persona/tiempo al escribir ("estoy aprendiendo" → "aprende japonés"; "me operaron" → "se operó") → el token
  exacto de la query NO casaba con el almacenado y, con el embedding local plano, el hecho se enterraba. Se
  truncan los tokens de contenido (≥5) a 6 chars + `*` → `aprend*` casa aprende/aprendiendo/aprender. Solo
  ensancha el canal FTS; la fusión RRF + el canal vectorial mantienen la precisión.
- **Stopwords de VERBOS META** en el FTS (`recuerdas`/`acuerdas`/`dime`/`sabes`…): son meta ("¿te acuerdas
  de…?"), NO el dato buscado. Sin filtrarlos, `recuerdas`→`recuer*` casaba con TODOS los "recuérdame…" del
  store y tapaba la respuesta real.
- **El recall del FlashBrain gasta su presupuesto en la memoria DURABLE** (`prompt.compose_recall`): pide un
  POOL PROFUNDO (`limit=40`) y filtra a `mid/long`. La recencia (CORTO/conv-buffer, mensajes efímeros) YA va
  entera en el prompt (`memory_cache`); incluirla en el recall es doble-conteo y la charla reciente ENTIERRA
  la tarea/hecho durable que se pregunta.
- **El BUFFER CONVERSACIONAL (`kind='conv'`) NO se embebe** (optimización 2026-07-12, `memory/writer.py`): el par
  turno↔respuesta crudo (efímero, TTL 2d, `level='short'`) se escribe CADA turno; se lee SOLO por recencia
  (`recent_short`, SQL directo) y el recall durable lo excluye → calcular su embedding (embeddinggemma/Ollama, GPU)
  era gasto por turno GASTADO que además competía con el STT/TTS local y metía charla-ruido en el top del retriever.
  El CORAZÓN ya destila lo memorable en píldoras aparte (esas SÍ se embeben). El `consolidator.promote` **excluye
  `kind='conv'`** para que un conv nunca acabe durable sin vector. Y el descarte barato pre-LLM
  (`memory_agent._TRIVIA_SKIP_RE`) cubre más muletillas/asentimientos ("ah/eh/mmm/ya está/bueno/venga…") → menos
  corridas del procesador LLM local en turnos triviales (menos GPU/eventos). Regla: el CORTO es de RECENCIA, no de
  índice — no gasta vector.
- **`recent_short` DETERMINISTA** (`ORDER BY updated DESC, id DESC`): `updated` tiene resolución de segundo →
  escrituras del mismo segundo empataban con desempate arbitrario y un turno más reciente podía caer fuera de
  la ventana (rompía "el más reciente MANDA"). El desempate por `id` (orden de inserción) lo estabiliza.
- **Gaps ABIERTOS** (techos reales, NO se falsean los tests): **T150** recall por vocabulario-gap puro
  ("instrumento"→"guitarra", sin solape léxico, exige saber que la guitarra es un instrumento — techo del
  embedding local); **T151** comparación CRONOLÓGICA de orden ("¿qué fue antes, X o Y?" exige co-recuperar
  ambos eventos fechados — gap del SOTA, LongMemEval "chronological awareness" 0.20-0.29). Ambos en V2-019.

## Olvido por peso + refuerzo (el corazón "neuronal")

Respaldado por investigación 2026 (access-frequency reinforcement, curva de Ebbinghaus, FadeMem).

- **Refuerzo por uso**: cada vez que un recuerdo entra en un prompt →
  `access_count++ · last_access = now · weight = min(1, weight + step)` (el acceso **resetea** el decay).
- **Decay temporal** (en consolidación): `I(t) = I₀·e^(−λ·Δt)`; **λ ≈ 0.001/día** (vida media ≈ **693 días** =
  ln2/λ), ajustable por tipo de memoria. **POR VENTANA desde 2026-07-20** (fix F1, auditoría 2026-07-19): el Δt se
  mide desde el ÚLTIMO ciclo de decay (marcador `sys_kv.decay_last_run`), no desde `last_access` en cada pasada —
  antes cada consolidación horaria re-aplicaba el decay ACUMULADO (~24×/día: una píldora idle 30 días perdía ~51%
  de peso POR DÍA en vez de seguir su vida media real).
- **TTL por categoría**: hechos inmutables (nombre, restricciones) → `ttl = NULL` (∞); contexto transitorio →
  TTL corto; preferencias → intermedio.
- **Pinned**: `pinned = 1` → nunca se borra aunque nunca se acceda (ej: clave del Bitcoin ledger).
- **Borrado por peso**: **SOLO** cuando se supera el límite de almacenamiento; se borran los de menor peso que no
  estén pinned, hasta volver bajo el límite. Mientras haya espacio, no se borra nada.

## Consolidador ("sueño") — job periódico, sin prisa

Corre a intervalos (diario / horario / según tamaño y tipo de memoria). Lo dispara el **loop orquestador**.

```python
def consolidate():                              # diario / horario / por tamaño
    # 1. comprimir: corto que sobrevive → resumen 'mid'; mid viejo → 'long'
    for c in clusters(short_older_than(T)): upsert(summarize(c), level='mid')
    # 2. deduplicar (interferencia): fusiona recuerdos muy similares
    for a, b in near_duplicates(sim > τ): merge(a, b)
    # 3. conflictos temporales: el hecho nuevo supersede al viejo
    for old, new in conflicts(): old.valid = 0; old.superseded_by = new.id
    # 4. decay: weight/importance de los NO accedidos *= e^(−λ·Δt)
    for m in memories: m.weight = decay(m)
    # 5. borrado por peso SOLO si se excede el límite (nunca los pinned)
    while store_size() > LIMIT:
        delete(lowest_weight(where pinned = 0))
```

**Poda de índices `prune_invalid` (F1, 2026-07-20):** las píldoras invalidadas (`valid=0`, superseded) conservan su
FILA (histórico intacto) pero, pasado un margen, salen de los índices **vec/FTS** — una cáscara invalidada no debe
seguir compitiendo en el retriever ni ocupando espacio vectorial. Corre dentro del sueño ligero
(`memory/consolidator.py::prune_invalid`).

### Sueño PROFUNDO — fase REM (V2-056, `memory/rem.py`)

El consolidador clásico es el sueño **LIGERO** (mecánica barata cada hora: promote/dedup-exacto/decay/prune/evict).
La **fase REM** es el ciclo **PROFUNDO** (diario por defecto), disparado por `nucleo/loop.py` tras el sueño ligero,
en el que la memoria se **ORDENA, se RELACIONA y se SINTETIZA** — todo OFF-hot-path y con cada fase AISLADA (un
fallo no tumba el sueño):

1. **`repair_embeddings()`** — re-embebe píldoras SIN vector o marcadas `meta.embed_pending` (las deja así el
   enforcement de firma del writer ante modelo discordante/degradado) → el índice semántico se **auto-repara** cada
   noche.
2. **`semantic_dedup()`** — dedup por SIGNIFICADO (coseno sobre los vectores ya calculados, **sin LLM**; umbral
   0.86 CALIBRADO contra la BD real + **guarda de cifras en conflicto**: dos hechos con números/fechas distintos
   jamás se fusionan): los ecos-paráfrasis de una misma tarea ("cita ITV el 23" × 8) colapsan en 1 — transfiere
   aristas, invalida el resto con `valid=0 + superseded_by` (histórico intacto). Era el pendiente declarado de V2-013.
3. **`synthesize(hook)`** — la única fase con LLM, **INYECTADA por el llamador** (la memoria NO importa cerebros;
   el loop cablea `nucleo/memllm.synthesize_concept_groups`, mismo patrón que `summarize_fn`): agrupa durables por
   **CONCEPTO** (grafo `edges`) y destila **1 INSIGHT de alto nivel por grupo** (`kind='insight'`,
   **`slot=insight:<concepto>`** → se REESCRIBE en cada sueño, no se acumula). Convierte 30 hechos sueltos en "lo
   que zaelar SABE de ti" (la reflexión de Generative Agents / sleep-time compute). Hook fail-open (`[]` = sin
   insights, el sueño sigue).
4. **`hygiene()`** — el chequeo del día: **% de escritura heurística en 24h → ALERTA si >50%** (un CORAZÓN caído
   debe SALTAR, no otra vez 2 días en silencio — incidente 2026-07-17/19), `embed_pending` restantes, tamaños. El
   informe vuelve al llamador (el loop decide alertar) y se emite por el bus (`memory.rem`).

Cadencia: marcador persistente **`sys_kv.rem_last_run`** + `config §memory.rem_every_hours` (def 24h, mín 1h; env
`ZAELAR_REM_SECS` manda si está). **Kill-switch `ZAELAR_REM=0`**. Modelo de síntesis por config
(`§memory.rem_model/rem_base_url/rem_api_key`, default `gpt-4.1-mini` — bench de síntesis 100%, §12) resuelto por el
**router interno `nucleo/memllm.py`** (modelos POR TAREA del módulo de memoria, key POR ENDPOINT — lección del
incidente: una key suelta enviada al endpoint equivocado tumbó el CORAZÓN 2 días en silencio).

## API interna de la memoria

Encaja con el transporte **híbrido** del sistema: `write`/`reinforce`/`link` = **async** (cola/eventos);
`query`/`state`/`load_episode` = **llamada directa** (hot path). Un solo escritor (la cola) evita las colisiones
de escritura de SQLite; los lectores van en WAL sin bloquear.

| Operación | Ruta | Quién la usa |
|---|---|---|
| `memory.write(item)` | async (cola) · lenta OK | FlashBrain · agente de memoria · widgets |
| `memory.query(prompt, budget) → ctx` | **directa · ms** (lectura), pero el FlashBrain la llama **fuera del event loop** (`asyncio.to_thread`) y **bajo demanda** (V2-011) | dispatcher del SlowBrain · FlashBrain (recall) |
| `memory.state() → dict` | directa · µs (tabla fija) | el compositor (siempre) |
| `memory.recent_short(limit, max_chars) → list` | directa · µs (lectura directa, SIN embeddings) | el compositor: CORTO plazo **entero** al prompt (V2-013 T146) |
| `memory.recent_window(limit, max_chars) → [{role,content}]` | directa · µs (lectura directa, SIN embeddings) | siembra `brain._window` al arrancar + 2º pase de corto (circuito de corto plazo, 2026-07-14) |
| `memory.reinforce(ids)` | async (evento) | lo dispara el retriever al usar recuerdos |
| `memory.pin(id)` / `unpin(id)` | async | operador (por voz) · agente de memoria |
| `memory.load_episode(id) → bytes/text` | directa (lazy) | agentes cuando se ordena "consulta el fichero" |
| `memory.link(from, to, type, w)` | async | agente de memoria · consolidador |
| `memory.consolidate()` | job periódico | el loop orquestador (sueño) |

Señal que emite: `memory.updated` (para que la UI u otros refresquen).

## Cómo la USA el resto del sistema (guía para quien escribe módulos)

Regla mental: **para GUARDAR, deja que el corazón decida; para LEER, elige la velocidad por lo que necesitas.**
No inventes rutas nuevas ni toques la BD directo.

**ESCRIBIR (todo async, por la fachada `memory/api.py` — nunca la BD directa):**

- **¿Es algo que dijo/escribió el operador en un turno?** → NO llames a `memory.write` a mano. Pásalo por el
  CORAZÓN: `await nucleo.memory_agent.ingest_utterance(text)` (el FlashBrain ya lo hace en cada turno dirigido).
  El procesador LLM decide si se guarda, dónde y cómo. Así la memoria APRENDE en vez de acumular texto crudo.
- **¿Eres el SlowBrain / un agente y quieres recordar un resultado o un hecho concreto?** → `await
  nucleo.memory_agent.remember({"text": …, "kind": "result"|"fact"|…})`. Es el ÚNICO escritor sancionado del
  SlowBrain; auto-clasifica si no fijas `level`. Puedes fijar `slot` (hecho singular → supersede exacto) y `meta`.
- **¿Eres un Brain Worker (proceso headless FUERA del server)?** → habla por HTTP con el server vivo:
  `python -m nucleo.mem_cli recall "<consulta>"` (lee) y `… remember "<dato>" [--slot x]` (escribe vía
  `remember_external`: token por-tarea + gates de precisión, sin acceso a `state` ni a slots de identidad).
  Preserva el ESCRITOR ÚNICO — jamás abras `zaelar.db` desde un worker (el Bash del worker está acotado a estos
  CLIs precisamente por eso).
- **¿Es CONTEXTO DE UI VIVO (lo que el operador tiene delante)?** → `memory.set_state({...})` (patch superficial).
  Lo escriben dos dueños: el **frontend** reporta los widgets abiertos (`POST /api/canvas/state` desde
  `desktop._persist()` → `set_state({open_widgets})`) y el **dispatcher del SlowBrain** las tareas en marcha
  (`nucleo/dispatch.py` → `set_state({activity})`). Va SIEMPRE en el prompt y se ve en el mapa. No es memoria que
  aprende: es el reflejo del "ahora".
- **¿Eres un CONECTOR volcando datos entrantes de una FUENTE externa (mensajería, cluster, otro agente)?** → usa
  **`memory.ingest_message(source, entity, text, *, trust, durable, group, directed)`** — la vía TIPADA UNIFICADA
  (multi-fuente). Da igual 2 conectores que 200, o un peer de cluster («Zalo») que un chat de WhatsApp: todos
  entran por aquí con su `source` (whatsapp/telegram/cluster/agent/email/**music**/…) y `entity` (quién), que quedan
  **indexados en `meta`** (→ lectura directa por tipo con `recent_by_source`) **y** en el texto (`[source] entity:
  body`). Es también la vía de writeback de los **RAILS** (V2-042): p.ej. el rail de música escribe cada
  reproducción con `ingest_message(source="music", entity=<artista>, durable=True)` → historial + gustos. **`trust`** es CLAVE: `operator`/`external` (datos del propio dueño) entran en el bloque pasivo del
  FlashBrain; **`untrusted`** (peer de cluster/agente ajeno) queda en **CUARENTENA** — NUNCA se inyecta en el
  prompt pasivo (anti prompt-injection), solo aflora por consulta EXPLÍCITA. `durable=True` → nivel `mid` (persiste
  + conceptos para el grafo); por defecto `short` (recencia). `slot` (opcional) = clave canónica → **supersede
  exacto**: cada ingesta con el MISMO slot SOBRESCRIBE la anterior (para una SÍNTESIS que se reescribe por
  fuente/entidad, no una fila por mensaje).
  - **Canal de CLUSTER (peers MeshKore) — observación PASIVA y COMPRIMIDA** (`connectors/meshkore/mem_ingest.py`,
    V2-021 T170): el bridge NO vuelca cada frase cruda del cluster. Por cada intercambio (peer→zaelar + zaelar→peer)
    un modelo LOCAL DESTILA off-hot-path una **síntesis evolutiva por peer** (temas/acuerdos/datos), guardada con
    `slot="cluster:<cluster>:<peer>"` (una píldora viva que se reescribe) + `trust="untrusted"` (CUARENTENA). Así
    "¿qué has hablado con Zalo?" se responde con `recent_by_source("cluster","Zalo")` sin que nada del peer se cuele
    en el prompt del operador. El canal corre en perfil untrusted (tools off, identidad-safe): la memoria es un side-effect de
    observación, no le da estado ni capacidades. Contenido REDACTADO (secretos) y handles neutralizados antes de
    persistir. Fail-open (fusión determinista acotada si no hay modelo). Apagable con `MESHKORE_MEMORY=0`.
- **Nunca** metas un LLM ni I/O de memoria SÍNCRONO en la ruta caliente de voz (V2-011). El write es fire-and-forget.
- **Píldora, no párrafo**: pasa un `text` CANÓNICO y breve; para hechos singulares que se sobrescriben, dale un
  `slot` (`operator.name`, `goal.current`…) → el writer deduplica/supersede solo.

**LEER (directo, sin LLM — elige la velocidad):**

- **ESTADO** (`memory.state()`) — µs, tabla fija. Úsalo para "quién es / en qué anda". Va SIEMPRE en el prompt (el
  FlashBrain lo sirve cacheado por `nucleo/flash/memory_cache`). Es "abrir los ojos".
- **CORTO** (`memory.recent_short()`) — µs, lectura directa, SIN embeddings. El working set reciente ENTERO. Para
  "de qué hablábamos". Sobre-incluye a propósito (barato).
- **LARGO** (`memory.query(prompt, budget)`) — ms, retriever vec+FTS→RRF. Para recall real ("dónde vivía Bartolo",
  "un mensaje de hace meses"). Es la única capa que tolera esperas; **bajo demanda** y **fuera del event loop**
  (`asyncio.to_thread`) desde el FlashBrain. El SlowBrain puede usar `compose_context` (recall + router LLM barato)
  porque va off-hot-path.
- **POR TIPO / FUENTE** (`memory.recent_by_source(source, entity)`) — µs, lectura DIRECTA por índice (json_extract
  sobre `meta`), SIN retriever ni LLM. Es "¿qué me ha llegado por WhatsApp?" / "¿qué me dijo Zalo por el cluster?" /
  "¿qué música he escuchado?" (`recent_by_source("music")` → historial + gustos, V2-042).
  Escala a N fuentes cambiando solo `source`. Es la ÚNICA vía por la que aflora el contenido `untrusted`
  (cuarentenado del bloque pasivo). El SLOT libre para el cerebro cuando el operador pregunta por una fuente.
  El filtro por `entity` es case-**e-acento-insensitive** (función SQL `pylower`, Unicode): "María"/"maría"/"MARÍA"
  recuperan igual — el `lower()` de SQLite es solo-ASCII y fallaría con tildes/ñ (bug T184, arreglado 2026-07-11).
- **Mapa completo** (`memory.map()`) — solo para el visor/diagnóstico (read-only, no refuerza).

## Acciones ↔ memoria: cuándo y cómo tocar la memoria (protocolo, V2-017)

Regla mental: **la memoria es el "yo recuerdo" de zaelar, no el estado del sistema.** El estado de qué existe
AHORA lo dan las fuentes vivas (el catálogo de widgets, el store de cada widget, el scheduler…). La memoria
guarda lo que zaelar debe **recordar haber hecho o sabido** para hablar como un humano mañana. Por eso:

- **Toca la memoria** cuando la acción cambia algo que el operador podría preguntar/recordar más tarde: un
  **hecho o preferencia** suya ("me llamo…", "no me narres"), un **resultado** entregado (una búsqueda, un
  informe), un **hito del ciclo de vida** (widget creado/borrado), un episodio (paste/drop).
- **NO toques la memoria** para lo efímero o ya derivable de una fuente viva: abrir/cerrar/mover un widget, una
  lectura de estado, charla trivial sin dato nuevo. (La ruta caliente de voz **nunca** hace I/O de memoria
  síncrono — V2-011.)
- **Quién escribe**: siempre por la fachada `memory.write` (cola async, loop-agnóstica). Desde el SlowBrain lo
  decide el **agente de memoria** (`nucleo/memory_agent.remember`, único punto de decisión). Los **widgets** y el
  **ciclo de vida de widgets** (`widgets/lifecycle.py`) escriben directamente por la fachada (son escritores
  sancionados).

**Regla de ORO del borrado — nunca se borra el histórico.** Borrar algo del mundo (un widget) elimina su
código/datos, pero **escribe un evento** de que se borró; el recuerdo de su creación se conserva. Así el recall
puede responder *"ese widget lo mandaste borrar el <fecha>"* aunque ya no exista. Para invalidar un hecho que
quedó obsoleto (no borrarlo) está `valid=0 + superseded_by` (lo usa el consolidador ante conflictos); un
**evento de ciclo de vida** en cambio NO invalida nada — se acumula como historia.

Ciclo de vida de un **widget** (implementado en `widgets/lifecycle.py`, disparado por el FlashBrain/SlowBrain):

| Acción | Ejecuta | Memoria |
|---|---|---|
| **CREAR** | SlowBrain (agente de código headless — escribe código) | `record_created()` → evento `[widget:<id>] «X» CREADO el <fecha> para: …` |
| **MODIFICAR** | SlowBrain (agente de código) | (el resultado de la tarea ya se recuerda por el dispatcher) |
| **BORRAR** | **FlashBrain, determinista** (rm carpeta + store), tras **confirmación** | `delete_widget()` → **lápida** `[widget:<id>] «X» BORRADO el <fecha> a petición del operador` (histórico conservado) |

**Autenticación del navegador ↔ memoria** (`widgets/navegador/auth_memory.py`, INI-016): mismo reparto memoria↔storage.
El **secreto NUNCA entra en memoria** (las cookies viven en el perfil de Chromium `widgets/_data/navegador/profile/`,
cifrado en reposo por el SO — la memoria es buscable y aflora en prompts/recall/visor, un secreto ahí se filtraría).
La memoria solo guarda lo que zaelar debe RECORDAR: **el HECHO de la sesión** (`record_session_established(site)` →
evento `mid` con `slot=navegador.session.<sitio>` → un re-login SUPERSEDE, no duplica; recall responde *"¿tengo sesión
en Wallapop?"*) y un **checkpoint recuperable** de un login a medias (`checkpoint_auth_pending` → `set_state({auth_pendiente})`
+ evento CORTO, calcando el `nucleo/reset.py`) que sobrevive a crash/reinicio para recordarte que lo dejaste a medias.

## Puntos de acceso

- **Escriben** (vía cola, async): **FlashBrain** (lo trivial que valga la pena), **agente de memoria del SlowBrain**
  (resultados, hechos, resúmenes), **widgets** (mensajería vuelca lo entrante) y los **Brain Workers** (V2-036/38,
  como pieza SERIAL por HTTP: `hbmem remember` → `POST /api/memory/remember` → `remember_external` con gates +
  token por-tarea — NUNCA abren la BD; ver §El CORAZÓN). Lo irrelevante se descarta antes de encolar.
- **Leen** (directo, ms): el **retriever** (lo llaman el dispatcher del SlowBrain y el FlashBrain para componer el
  contexto mínimo). **La lectura del FlashBrain NO va en el turno síncrono de voz** (V2-011, latencia): el bloque
  de ESTADO (`memory.state()`) se **cachea por sesión** (`nucleo/flash/memory_cache.py` — TTL + refresco async +
  invalidación por `memory.updated`), y el **recall** (`memory.query` → embeddings) es **bajo demanda**
  (heurística `nucleo/flash/prompt.needs_recall`) y **fuera del event loop** (`asyncio.to_thread`). Así el turno
  de charla nunca dispara el retriever ni bloquea el loop; el recall real se conserva (medido en
  `zaelar-model-benchmarks.md §4`).
- **Mantiene el estado**: el agente de memoria y el consolidador escriben la tabla `state`; el compositor la lee
  en cada prompt.

## Lectura en el turno — TRES velocidades (cómo se reciben peticiones y se devuelven datos)

Cuando llega un turno de voz/chat, el FlashBrain compone su prompt en `nucleo/flash/prompt.py::build_flash_system`.
La memoria entra por **tres rutas de lectura con tres velocidades distintas, alineadas con la latencia** (el turno
de voz NUNCA hace I/O de memoria síncrono en el event loop — V2-011).

> **Cada capa tiene ESTRUCTURA DE DATOS y MÉTODO DE CONSULTA propios** (aclaración del operador, 2026-07-10 — no es
> un mecanismo único): **ESTADO** = slots clave–valor (fila fija, dict pequeño, `memory/state.py`) → lectura entera
> directa (µs), SIEMPRE, cero búsqueda. **CORTO/reciente** = **lista cronológica** (log rodante, filas
> `level='short'`) → se lee ENTERA, reciente-primero, SIN búsqueda (`recent_short`). **LARGO** = archivo
> **indexado** (vector sqlite-vec + FTS5 + grafo) → **QUERY semántica** (RRF vec∥fts → score → graph_expand), bajo
> demanda y off-loop. Estructuras y accesos distintos a propósito: cada uno optimizado para su rol y su latencia.

| Capa | Rol | Cómo se LEE | Código |
|---|---|---|---|
| **ESTADO** = *la pila* | Lo grabado a fuego (nombre, objetivo/proyecto, ubicación…) **+ el CONTEXTO DE UI VIVO** (widgets abiertos `open_widgets`, tareas/sesiones en marcha `activity`/`sessions`, y los RAILS vivos `rails` → "Rails en curso", V2-042): lo que el operador tiene DELANTE. Va SIEMPRE en el prompt. | **Instantánea, siempre** — string ya compuesto y **cacheado** (`memory_cache.get()`, TTL + refresco async off-loop + invalidación por `memory.updated`; el reporte del canvas dispara el refresco). Cero query. | `nucleo/flash/memory_cache.py` · `memory.state()` |
| **CORTO PLAZO** = *working set* | Lo reciente/efímero (turnos, mensajes de hoy). Pequeño → cabe entero. | **Entera y barata** — se enchufa TODO el corto reciente al prompt SIN retriever (lectura directa µs). Fix del bug del nombre: en vez de *buscar* (poco fiable) se *lee entero*. | `memory.recent_short()` → cacheado en `memory_cache._compose()` (bloque "Conversación reciente") |
| **LARGO PLAZO** = *el archivo* | Durable, mucha info, no cabe. | **Solo por QUERY** — retriever vec+FTS→RRF (BD, más lento), **bajo demanda** (`prompt.needs_recall` como prefetch + **tool `recall`**, V2-056) y **fuera del loop** (`asyncio.to_thread`). | `nucleo/flash/prompt.compose_recall()` → `memory.query()` → `memory/retriever.py` |

> **Invariante:** ESTADO se lee gratis (cache), CORTO se lee entero-y-barato (cabe), LARGO se lee por query (no
> cabe). El SlowBrain, en cambio, compone contexto con `nucleo/memory_agent.compose_context()` (dossier v2
> multi-eje, ver §El CORAZÓN) — ese sí puede permitirse la búsqueda porque va off-hot-path.

**El gate de recall tiene DOS caminos desde V2-056** (auditoría 2026-07-19 — «quién decide buscar = el modelo»,
V2-022, aplicado a la memoria):
- **Prefetch heurístico** (`prompt.needs_recall`, determinista es/en) — el camino clásico, optimista y gratis.
  Ampliado con **fraseos de planificación** («quiero irme de vacaciones», «organízame un viaje», «búscame un
  hotel», «resérvame un restaurante»…) que antes NO disparaban recall → cerebro amnésico justo cuando iba a
  planear algo para el operador.
- **Tool `recall`** (`router.TOOLS`, catálogo canónico en `zaelar-architecture.md §8`) — el **MODELO decide
  recordar**: cubre lo que el prefetch no cazó. Ruta LIGERA hermana de `web_search` en
  `voice/engine/llm/providers/nucleo.py`: `compose_recall` off-loop (`asyncio.to_thread`) + 2º pase con el modelo
  que el turno ya paga → los recuerdos vuelven EN el turno, sin tarjeta ni worker. Solo memoria DURABLE del
  operador (no datos del mundo = `web_search`; no lo ya visible en ESTADO/conversación).

### Circuito de CORTO PLAZO de interacción con el operador (2026-07-14)

El FlashBrain debe estar **super situado** en cada petición (quién es el operador, qué tiene delante, de qué íbais
hablando) SIN inflar el prompt. Tres piezas, "lo básico siempre + lo pesado bajo demanda":

- **Suelo de identidad SAGRADO** (`nucleo/flash/memory_cache._store`): el bloque de ESTADO cacheado **nunca se
  sobrescribe con vacío**. `compose_state()` puede fallar transitoriamente (lectura de BD bajo contención en sesiones
  con muchas escrituras) y devolver `('','')`; si eso pisara el caché, el FlashBrain diría *"no sé quién eres"* aunque
  el nombre esté en el estado (bug intermitente real, 2026-07-13). La guarda mantiene el último bloque bueno y marca
  `dirty` para reintentar. El vacío legítimo (fresh install / `reset()`) parte de un caché ya vacío, así que pasa.
- **Ventana sembrada desde memoria** (`brain._window` ← `memory.recent_window`): la ventana de diálogo (últimos
  `_WINDOW_MAX`=10 turnos verbatim que ve el modelo) vive en RAM y **arrancaba vacía** en cada instancia del brain
  (reinicio/reconexión) → se perdía "de qué hablábamos". Ahora se **siembra una vez** desde el buffer conversacional
  persistente (`kind='conv'`, con `meta.u`/`meta.a` estructurados). Cero tokens extra (la ventana ya estaba capada).
  Cableado IDÉNTICO en la voz (`nucleo.py::_run`) y en el probe (`nucleo/flash/probe.py`) → el probe reproduce fiel
  el arranque tras reconectar.
- **2º pase de CORTO plazo bajo demanda** (`prompt.needs_recent` → `prompt.compose_recent_block`): cuando el turno
  **referencia la interacción reciente** ("de qué hablábamos", "lo que te dije antes", "repite eso", "hace un rato";
  es/en, determinista) se inyecta el buffer conversacional **AMPLIADO** (verbatim, ~20 turnos, más que la ventana
  normal) como bloque etiquetado — **fuera del event loop** (`asyncio.to_thread`, respeta V2-011). La charla normal
  NO lo lleva (prompt ligero); solo se carga cuando hace falta. Es el hermano de corto plazo de `needs_recall`
  (que es para el dato DURABLE por significado, vía embeddings). Telemetría `recent_fired` en `/debug`.

### El ESTADO COMPUESTO — `memory.compose_state()` (contrato, V2-027)

El prompt del cerebro es **[ESTADO compuesto dinámicamente] + [petición del operador]** (rediseño V2-027, ~30
líneas frente a las ~280 de antes). La MEMORIA es la dueña de componer ese ESTADO: `memory.compose_state(*,
mission_fallback="") -> (bloque, operator_name, stats)`. Es lo **COMPARTIDO por los dos cerebros**; los RECURSOS/tools
divergen por cerebro (capa propia). Lectura **DIRECTA** (µs, sin LLM ni retriever) → seguro cachearla fuera del turno
(`nucleo/flash/memory_cache` la cachea con TTL + refresco async + invalidación por `memory.updated`; el turno de voz
NUNCA la compone sin caché — invariante V2-011). Estructura ordenada:

| Sección | Qué lleva | De dónde |
|---|---|---|
| **A · QUIÉN ERES** | La MISIÓN/identidad (3-4 frases, idioma del operador). VIVE EN LA MEMORIA — no en un prompt inglés. | `state.mission`, sembrada al arrancar por `memory_cache.prime()` desde `langs.LangSpec.mission`; `mission_fallback` si aún no se sembró (el llamador lo pasa para no invertir la dependencia memoria→voz). |
| **B · QUIÉN TIENES DELANTE** | Situacional VARIABLE: operador (nombre/trato/ubicación + campos durables del ESTADO), widgets ABIERTOS, tareas/sesiones EN MARCHA, **RAILS en curso** (runs vivos del FlashBrain, V2-042), y el perfil durable saliente ("lo que sabes de él"). | `memory.state()` + `memory.salient_long()` (cap terso). |
| **C · DE QUÉ ÍBAIS HABLANDO** | Síntesis TENSA de la conversación reciente — las últimas líneas del corto plazo (cap agresivo), NO el volcado crudo entero ni la memoria de LARGO. | `memory.recent_short(limit=5, max_chars=550)`. El recorte ES la "síntesis" (sigue siendo lectura directa; una síntesis por LLM, si se quisiera, iría OFF del turno). |

La misión (A) sembrada en `state.mission` es visible en el mapa de la memoria (columna ESTADO) y editable — la
identidad deja de estar hardcodeada en `voice/prompt.py` (esa persona inglesa ya SOLO sirve a los baselines
`BRAIN=direct|local|duo` y al harness). Sobre este ESTADO, el FlashBrain añade su capa TERSA de recursos
(`nucleo/flash/prompt._flash_layer`) y el SlowBrain la suya; el "cuándo usar cada tool" vive en la descripción de la
tool (`router.TOOLS`), no duplicado en prosa.

## El CORAZÓN de escritura — el LLM que DESTILA cada dato en una píldora (V2-013)

**Invariante de oro (aclaración del operador 2026-07-10, REAFIRMADO 2026-07-14): ESCRIBIR puede ser LENTO; LEER
debe ser MÁXIMA VELOCIDAD.** Escribir BIEN es lo prioritario y puede tardar lo que haga falta: colocar cada dato en
su capa (ESTADO/CORTO/LARGO), no duplicar, puntuar peso/importancia, organizar los conceptos del grafo y calcular
embeddings/vectores — todo **off-hot-path** (cola async); no necesitamos que escritura y lectura sean inmediatas, así
que un modelo de escritura MÁS LENTO y MÁS PRECISO es preferible (2ª auditoría 2026-07-14: el CORAZÓN pasó de
`qwen2.5:3b` a `qwen2.5:7b-instruct` — 3/12→12/12 en write-completeness; ronda V2-056 2026-07-20: pasa a
`gpt-4.1-mini` vía OpenAI — **98.3%** en el bench de destilación §12). La LECTURA, en cambio, la paga el FlashBrain
EN el turno (compone prompt, responde, actúa) → **NUNCA lleva un LLM ni I/O síncrono de memoria** (bloquearía la
voz — regla de V2-011). El "corazón" que decide, por cada cosa que dice el operador, **si se guarda, DÓNDE
(ESTADO/CORTO/LARGO/DESCARTAR), con qué importancia/TTL y bajo qué `slot`**, vive en `nucleo/memory_agent.py` +
`nucleo/mem_processor.py`:

- **`mem_processor.process(text, state) → list|None`** — el **procesador LLM**: default actual
  **`gpt-4.1-mini` vía OpenAI** (config `§memory.mem_processor_model/_base_url/_api_key`; decisión del operador
  2026-07-17 «memoria SIEMPRE OpenAI», confirmada por el **bench de destilación V2-056**
  (`tests/e2e/memory/bot/distiller_bench.py`, `zaelar-model-benchmarks.md §12`): gpt-4.1-mini **98.3%** (28.5/29,
  1.1s) vs **qwen2.5:7b local 86.2%** — el qwen queda como **OPCIÓN local** apuntando `base_url` a Ollama, para
  batería/privacidad). Env `MEM_PROCESSOR_MODEL/URL/KEY` = fallback power-user; modelo por invocación. La
  **credencial se resuelve POR ENDPOINT** (`mem_processor._key` → `_endpoint_key`, mismo patrón que
  `fast_client.resolved_api_key` — la key sigue a la URL, nunca al revés; fix del incidente 2026-07-17→19: una key
  rancia de env enviada al endpoint equivocado dejó el CORAZÓN **2 días caído EN SILENCIO**, todo escribiéndose por
  la heurística). **SALUD de 1ª clase** desde ese incidente: una **racha de fallos** dispara una alerta por el
  observer (y aviso de recuperación al volver), y `mem_processor.status()` expone
  modelo/racha/último-error/degradado al área de config — un CORAZÓN caído ya no puede pasar desapercibido. La
  write-completeness es la palanca nº1 del recall (V2-031) y como escribir va off-hot-path, **preferimos el modelo
  más preciso aunque sea más lento**. **DESTILA** el turno crudo
  en **píldoras canónicas** (no la frase literal): `{text, dest, kind, importance, ttl_days, slot, value, change,
  state_patch}` (contrato v2, ver §Supersede). Bajo contención de GPU los turnos ya NO se pierden: **cola diferida
  corta** (serial — jamás dos distilaciones a la vez; espera acotada `MEM_PROCESSOR_QUEUE_WAIT`/`_MAX`, y solo al
  agotarse cae a la heurística, de forma OBSERVABLE — auditoría 2026-07-14; antes SKIP silencioso).
  La `importance` es **dinámica** — el prompt recibe el ESTADO actual para juzgar relevancia con contexto (estudio
  derecho → derecho importa). Retorno con semántica: **`None`** = modelo no disponible → cae a la heurística;
  **`[]`** = el LLM corrió y decidió DESCARTAR (se respeta); lista = píldoras a guardar. ⚠️ Con el default externo
  el TEXTO del turno SÍ sale a la nube para destilarse (tradeoff aceptado explícitamente por el operador
  2026-07-17); con la opción local (qwen vía Ollama) nada sale de la máquina.
- **`ingest_utterance(text)`** — punto de entrada "algo que dijo el operador". Flujo: (1) trivia/comando obvio →
  DESCARTE barato sin LLM (anti-ruido); (2) el procesador LLM destila píldoras; (3) **fail-open**: si el modelo no
  está, cae a `classify()` (heurística regex) para no perder el perfil. **Cableado en cada turno dirigido** en
  `voice/engine/llm/providers/nucleo.py` (`asyncio.create_task`, fire-and-forget → cero coste en TTFB).
- **`classify(text)`** — heurística µs de RESERVA (regex es/en): PERFIL (nombre/ubicación/trato/hardware/coche/
  objetivo/proyecto) → `state_patch` + traza `long` pinned con `slot`; DESEO/PREF → `long`; TRIVIA/COMANDO → skip;
  resto → `mid`. Es el fail-open cuando el LLM no responde. **F1 (2026-07-20): el fail-open ya NO ensucia** — el
  turno crudo degrada a `short` + TTL 3 días (NUNCA se hace durable un texto sin destilar; el incidente de 2 días
  de heurística llenó el largo plazo de basura), y las redes deterministas (salud/compromisos/rutinas) siguen
  rescatando lo crítico.
- **`remember(item)`** — ÚNICO escritor del SlowBrain; acepta `slot`/`meta`/`ttl_days` (auto-clasifica si el caller
  no fija destino). **`_write_atom(atom)`** mapea una píldora del LLM → capa (state→estado+traza long/pinned;
  long/short→recuerdo con su ttl/slot).
- **`compose_context(prompt)`** — el **DOSSIER v2 multi-eje** del worker (redseño V2-056): perfil del operador
  (**sin la misión** — es identidad de zaelar, era ruido de ~900 chars en el prompt de un worker) + **reglas del
  operador** (`state.rules`) + **⚠️ hechos críticos SIEMPRE** (`memory.critical_facts`, independientes del ranking)
  + recall RRF + **eje por CONCEPTOS** (`memory.by_concepts` — T178/T183 por fin CABLEADA en producción: los
  conceptos de la tarea agregan el cluster del grafo) + **agenda próxima** (read-only del widget). **Solo
  DURABLES** (el conv-buffer crudo ya no compite por los huecos) y todo el I/O en **`asyncio.to_thread`**
  (`_dossier_sync`). Es la ÚNICA cara del agente que puede permitirse recall+router LLM — va off-hot-path.

**Supersede/dedup por SLOT (DETERMINISTA, sin LLM)** — el "el más reciente MANDA": `memory/writer.insert_memory`,
al recibir un `slot` (normalizado por `canon_slot` contra el registro `memory/slots.py`), mira **TODOS los
recuerdos vigentes** con ese slot → si el texto normalizado del más reciente es idéntico lo **REFUERZA** (sube
peso, cero duplicados) y colapsa los rezagados; si difiere, inserta el nuevo y marca **todos** los viejos
`valid=0, superseded_by=nuevo` (auto-curativo, V2-038/auditoría 2026-07-14). Así "me llamo Ricard" dicho de tres
formas = UN hecho reforzado, no tres filas — y un linaje históricamente duplicado se colapsa solo. El SELECT de
vigentes **expande por ALIAS** (`slots.equivalent_keys`): escribir `operator.location` colapsa también una píldora
legacy con clave cruda `location`/`ubicacion` → el colapso es INMEDIATO, sin esperar al `heal_slots` del sueño
(2ª auditoría 2026-07-14, hallazgo del auditor: dos píldoras contradictorias del mismo hecho con claves distintas).

**Slots de FONDO SUBORDINADOS a `state.location` (`salient_long`, 2ª auditoría 2026-07-14):** el bloque pasivo del
estado ("lo que sabes de él, dalo por sabido **sin buscar**") solo pinta hechos del OPERADOR (slots con `.`:
`operator.*`/`goal.*`/`project.*` o sin slot). Los slots de FONDO namespaced con `:` (`weather:soria` que vuelca
el widget meteo en background, `<widget>:<clave>`, `cluster:*`) quedan **FUERA del bloque pasivo** — antes un
`weather:soria` saliente SECUESTRABA "¿qué tiempo hace hoy?" (el cerebro leía Soria en vez de aterrizar en
`state.location` y buscar). Siguen **recuperables por el retriever** ante una pregunta EXPLÍCITA por esa ciudad; solo
dejan de competir con el perfil del operador en el prompt pasivo.

**SEGURIDAD MÉDICA — alergias ADITIVAS + siempre presentes (2ª auditoría 2026-07-14, hallazgo del corpus v3):** una
alergia/intolerancia es un hecho médico **aditivo y crítico**. El CORAZÓN LLM la mis-asignaba al slot SINGULAR
`operator.diet` → una **DIETA declarada después la BORRABA** (supersede por slot: "soy vegetariana" pisaba "alérgica
a la penicilina"). Guard DETERMINISTA en el WRITER (chokepoint, `_is_critical_health`, es/en): una alergia/condición
crítica **nunca conserva un slot de identidad singular** (queda aditiva → varias alergias coexisten; el dedup
semántico funde repeticiones), se fija **pinned + importancia ≥0.95**, y se marca `meta.critical='health'`. En la
LECTURA, `memory.critical_facts()` alimenta una **línea ⚠️ CRÍTICO propia** del `compose_state` que se surface
**SIEMPRE**, independiente del ranking/cap de `salient_long` (bajo densidad la alergia se enterraba fuera del top-N).
Olvidar una alergia es un fallo de seguridad — por eso no depende del retriever. Una dieta real (sin marca de
alergia) sí sigue superseding normalmente a otra dieta.

**Contrato v2 del átomo — `value` + `change` (auditoría 2026-07-14, cierre de fondo del retest V2-038):** el
procesador emite, además de `slot`, (a) **`value`** = el valor escueto del hecho singular ("Valencia") → el host
**SINTETIZA el `state_patch` MECÁNICAMENTE** del registro de slots (aunque el LLM escribiera el cambio como hecho
suelto sin patchear el estado — la raíz del bug de la mudanza); (b) **`change: none|update|correction`** = la
señal semántica de "esto es un cambio/corrección declarado, no un garble", que consume el gate anti-garble P0b
**por átomo**. La señal la emite el PROPIO modelo (multilingüe por naturaleza, agnóstico del fraseo) → la familia
de regex del host (`_RELOCATION_RE`, `_CORRECTION_*`, …) queda como **BACKSTOP del castellano**, ya no es el
único mecanismo. Fewshots del procesador NEUTROS (persona ficticia — nunca el operador real: la memoria se sirve
EN BLANCO) e incluyen el caso del cambio declarado.

**Escritura EXTERNA (Brain Workers) — `memory_agent.remember_external`** (auditoría 2026-07-14): la vía de los
workers (`hbmem remember` → `POST /api/memory/remember`) exige el **token por-tarea** (`ZAELAR_TASK_TOKEN`,
headers de `mem_cli`; escotilla dev `ZAELAR_MEM_API_OPEN=1`) y aplica los MISMOS gates que la voz: gate de
precisión P0a, **NUNCA toca `state`** (un worker no habla por el operador), **slots de IDENTIDAD vetados**
(degradan a hecho suelto; los de trabajo `goal.*`/namespaced pasan) y **procedencia estampada**
(`meta.source="worker:<id>"`). El resultado de una tarea solo se recuerda si terminó **OK** (las fallidas avisan
por voz pero no ensucian el nivel `mid`).

**Red de BACKSTOPS DETERMINISTAS del CORAZÓN (regex es/en, sin LLM)** — el LLM local a veces DESCARTA por "charla"
cosas que un humano SÍ recuerda, o su decisión es inconsistente. `nucleo/memory_agent.py` intercepta patrones
inequívocos ANTES/DESPUÉS del LLM y garantiza el comportamiento correcto sin depender del fraseo (cada uno con guard
en `nucleo/test_memory_agent.py` y batch propio en el bot de memoria):
- **Compromisos** (`_COMMITMENT_RE`) — una petición/cita/encargo ("mi jefa me pidió el informe para el miércoles")
  se guarda SIEMPRE aunque el LLM la canonicalice y la tire.
- **Rutinas** (`_ROUTINE_RE`) — una costumbre recurrente ("cada lunes gimnasio") es memorable como patrón.
- **Observaciones/autoconocimiento** (`_OBSERVATION_RE`) — "he notado que rindo por las mañanas", "cuando ceno
  tarde duermo mal" → autoconocimiento útil para aconsejar; el LLM lo descartaba de forma inconsistente.
- **Reversiones/cese** (`_REVERSAL_RE`) — "ya no bebo café", "ya no trabajo allí" → cambio de estado; se guarda el
  NUEVO estado para que el cerebro sepa que eso YA NO aplica (el LLM lo tiraba).
- **Corrección explícita** (`_CORRECTION_RE` "no es X sino Y" — captura valores que empiezan por letra O DÍGITO, para
  PIN/códigos; `_CORRECTION_YANO_RE` "ya no … NombrePropio") → olvida (invalida) el valor erróneo y sigue para guardar
  el nuevo.
- **Mudanza declarada** (`_RELOCATION_RE`, round headless V2-038 2026-07-14) — "me he mudado a Valencia", "nos hemos
  mudado a X", "I moved to X" → actualiza `location` (patch de perfil + slot `operator.location`, supersede exacto)
  y cuenta como CORRECCIÓN para el gate P0b (un cambio de vida dicho con todas las letras no es un garble). Además,
  **backstop de PERFIL→ESTADO**: si la heurística detectó perfil (nombre/ubicación/…) y los átomos del LLM NO
  tocaron esos campos de `state`, el patch se aplica igualmente (el CORAZÓN tendía a escribir la mudanza como hecho
  suelto — "ahora vive en Valencia" — SIN actualizar el estado → el tiempo respondía con la ciudad VIEJA).
  **⚠️ Desde la auditoría 2026-07-14 esta familia es BACKSTOP, no el mecanismo primario:** la señal de cambio
  legítimo la emite el propio procesador (`change: update|correction`, cualquier idioma/fraseo) y el patch de
  perfil se sintetiza mecánicamente de `slot`+`value` — las regex solo cubren la ruta heurística (LLM caído) y
  el castellano/inglés literal.
- **Olvido a petición** (`_FORGET_RE`) — "olvida lo de X" → soft-invalida (conserva histórico). **Olvido DURO**
  (`_FORGET_HARD_RE` "del todo / para siempre / sin dejar rastro") → `forget(hard=True)`, borrado real irreversible
  (derecho al olvido para datos sensibles). **F1 (2026-07-20): el hard DELEGA en `writer.delete_memory`** — el
  DELETE plano anterior dejaba **fantasmas en el índice FTS5** (el texto "borrado" seguía recuperable → rompía la
  privacidad); el writer hace el `delete` de FTS5 CON el texto ANTES de borrar la fila (+vec +edges), índice limpio
  de verdad. **Des-olvido** (`_UNFORGET_RE` "recupera lo de X") → revierte un soft-forget
  (valid=1; el retriever ya filtra por valid).
- **Abstención write-side** (`_ASSISTANT_QUERY_RE`) — una pregunta INEQUÍVOCA al asistente ("¿qué tiempo hace en X?",
  "¿me recomiendas…?") NO es un hecho del operador → DESCARTE (evita inventar preferencias). Conservador: no toca
  preguntas que traen un dato ("¿sabes que me mudé a Madrid?").

**GATES de PRECISIÓN de escritura (V2-033, 2026-07-12) — el CORAZÓN no ENSUCIA el largo plazo.** Simétricos a los
backstops (que RESCATAN lo que el LLM tira de más), estos FILTRAN lo que el LLM guarda de más. El modelo pequeño
reifica preguntas/peticiones como "hechos", propaga el garble del STT a `state` y sobre-generaliza directivas
efímeras → guards DETERMINISTAS en `nucleo/memory_agent.py`, aplicados a la salida del LLM **y** de la heurística:
- **(P0a) Peticiones/preguntas/ack → DESCARTE.** Pre-LLM: directiva/pregunta vaga sin referente (`_is_vague_request`
  "mira eso", "¿puedes mirar eso?"). Post-LLM: `_ATOM_NONFACT_RE` tira el átomo cuyo texto canónico es una pregunta
  reificada ("el operador pregunta si…", "quiere saber…") o interrogativo. **No** toca TAREAS CONCRETAS con dato
  ("búscame vuelos a Tokio" → sigue recordable vía `_COMMITMENT_RE`) ni AFIRMACIONES envueltas ("recuérdame que soy
  alérgico…" → el hecho se guarda).
- **(P0b) Plausibilidad de IDENTIDAD** (`_plausibility_demote`): un valor de slot singular (`operator.name`…) que
  CONTRADICE el ya establecido en `state` NO lo sobrescribe en una mención única (garble típico del STT) → se degrada
  a `long` en **CUARENTENA** (`trust=untrusted`: recuperable solo por consulta explícita, jamás aflora en recall/
  prompt). Las CORRECCIONES explícitas ("no me llamo X sino Y") y la MUDANZA declarada (`_RELOCATION_RE`) sí pasan
  (ya olvidaron/superseden el valor viejo). En un
  perfil VACÍO el primer dato entra normal (no hay conflicto). Ataca la confusión de identidad ("zaelar llegó a decir
  «me llamo Alex Teigano»" por un `state` polucionado).
- **(P1) Preferencias EFÍMERAS** (`_is_ephemeral_directive`): una directiva de pantalla/acción inmediata ("no me
  muestres nada ahora", "ahora no") es estilo de sesión que ejecuta el FlashBrain — NUNCA una preferencia durable;
  descarte pre-LLM. Solo se hace durable si trae marca de durabilidad ("prefiero/siempre/en general…").
Verificado por `tests/integration/memory/test_write_precision_v2033.py` (16 casos, `MEM_PROCESSOR=0` → determinista
sin GPU) + smoke con el destilador LLM real; sin regresión (291 tests de memoria). Cruza con **V2-031**: el eje del
recall no es el embedding sino **write-completeness + PRECISIÓN** — esta es la cara "precisión".

**Estado de V2-013 (2026-07-10):** construido — schema v2 (`slot`+`meta`), procesador LLM local, supersede/dedup por
slot, ingesta re-cableada (adiós al write crudo 0.3), CORTO como buffer conversacional limpio (`kind='conv'`, TTL).
Pendiente en el roadmap: **dedup SEMÁNTICO** (por embedding, para lo SIN slot), **grafo de conceptos** (poblar
`edges`), y afinar el few-shot del procesador. La **consolidación CORTO→LARGO por TTL/peso** + **aislamiento del
tester** + limpieza de la BD se trabajan en **V2-019** (`.meshkore/roadmap/initiatives/V2-019-memoria-sueno-aislamiento.md`).

**Reset duro ↔ memoria** (V2-018 `nucleo/reset.py`): al parar todo, el trabajo en curso se **CONGELA en ESTADO**
(`set_state({trabajo_interrumpido})`) y la orden queda registrada en **CORTO** (`memory.write level='short'`) antes de
matar los procesos. También limpia los **RAILS vivos** (`rails.clear_all` → `state.rails=[]`): un run
(`sin_resolver`, sonando…) es estado de SESIÓN, no memoria durable — lo durable ya se volcó por su writeback tipado.

## Bóveda de secretos del operador — cifrado + storage partido (V2-060, CONSTRUIDO 2026-07-21)

> Construido (rama `feat/v2-060-boveda-secretos-cifrados`). Módulos de memoria: `memory/vault.py` (cripto),
> `memory/secrets.py` (detección), `memory/vault_api.py` (`/api/vault/*`). El flujo de lectura del cerebro vive en
> `nucleo/flash/vault_flow.py` + la tool `reveal_secret`. Modelo de seguridad en `zaelar-security.md`, superficie de
> config en `zaelar-conventions.md`. Aquí, lo que toca a la MEMORIA.

Los **secretos del operador** (contraseña de Netflix, IBAN/tarjeta, nº de cuenta cripto, private key de un wallet)
no pueden vivir en una píldora en claro. La memoria gana:

- **Gate de clasificación FAIL-CLOSED en el CORAZÓN** (`mem_processor`, §arriba): además de DESCARTAR/ESTADO/CORTO/
  LARGO, decide **¿es un SECRETO?** — patrones deterministas (Luhn/IBAN/BIP-39/`0x…`/`sk-…`/«contraseña de …») **+**
  LLM; **ante la duda, cifrar** (invierte el fail-open habitual: un secreto en claro = privacidad rota). El operador
  puede forzar «guárdalo cifrado».
- **Storage PARTIDO** (una píldora especial): **etiqueta en claro y buscable** («contraseña de Netflix» → se
  embebe/indexa/rerankea normal, `slot=secret:*` para supersede) **+ valor cifrado opaco** (`meta.vault=1`,
  `meta.sensitivity`). El valor NUNCA se embebe, loguea, entra en el prompt/`memory_cache`, ni va a un worker.
- **Cifrado asimétrico** (sealed box): la **clave pública** vive en claro → **escribir un secreto NO pide desbloqueo**
  (el CORAZÓN cifra y guarda sin más, y un worker también puede *escribir* uno); la **privada** (para LEER) va
  envuelta por passphrase y/o passkey. Detalle cripto en `zaelar-security.md`.
- **Lectura:** el retriever encuentra por etiqueta y devuelve la señal **«sellado → pide desbloqueo»** (nunca el
  texto) → el FlashBrain solicita passkey/passphrase; el descifrado ocurre en el navegador (modo estricto) o en el
  servidor un instante (modo cómodo, para TTS).

## Observabilidad de la memoria (V2-014) — registro de eventos + visor

Dos superficies para VER la memoria trabajar en tiempo real:

- **Columna de logs ◷** (`/debug` · `frontend/app/components/DebugPanel.js`): el turno emite filas `kind=memory`
  con **módulo=memory · capa (state/short/long/slow) · petición → resultado (nº tarjetas/chars) · tiempo `mem_ms`**
  (emitidas en `voice/engine/llm/providers/nucleo.py` tras `build_flash_system`); las escrituras/queries llegan
  etiquetadas por el puente SSE. Detalle en `zaelar-observability.md`.
- **Visor «Mapa de la memoria» 🧠 — DOS VISTAS** (`frontend/app/components/MemoryMap.js`, overlay a pantalla, se abre
  desde el cuenco del orbe; redseño 2026-07-10 a petición del operador). Un **toggle** alterna dos representaciones de
  la misma memoria; la clave del redseño: separar **CONTENIDO** de **ORGANIZACIÓN**, y NO mezclar corto con largo (son
  storages distintos en la realidad → mapas distintos):
  - **SLOTS** (cómo se GUARDA): tres COLUMNAS proporcionales **ESTADO 10% · CORTO 20% · LARGO 70%** (el modelo de
    LECTURA a 3 velocidades); cada recuerdo un nodo con texto+scoring+fecha+metadatos. Es la vista con **tintado en
    vivo** por-nodo (`[data-mid]`). La columna **ESTADO** muestra también el CONTEXTO DE UI VIVO —**widgets
    abiertos**, **tareas en marcha** y **rails en curso** (V2-042)— así el operador VE lo que el cerebro tiene
    delante en cada momento.
  - **CONCEPTOS** (cómo se ORGANIZA, T126): **mapa de red** — cada concepto un **nodo circular dimensionado por su nº de
    datos** (el número DENTRO), unido a OTROS conceptos por aristas de **co-ocurrencia** (comparten píldora; grosor = nº
    compartido). SIN contenido. **CORTO y LARGO = DOS MAPAS SEPARADOS** (paneles apilados): el LARGO desde el grafo
    persistido (`edges`), el CORTO derivado al vuelo (`memory/concepts.py::derive_concepts` — el corto no persiste
    aristas). Vocabulario de conceptos centralizado en **`memory/concepts.py`** (substrato): un solo sitio para cómo se
    ESCRIBE (backstop de `memory_agent`) y cómo se DIBUJA el mapa de corto.
  - Datos: `GET /api/memory/map` (`memory.api.map()`, read-only, no-cache) → `{state, layers:{short,long},
    concept_graph:{short:{nodes[+count],links[+weight]}, long:{…}}, concepts, edges, counts}`.
- **Tiempo real + tintado** (gated por el flag `memory_observability`, default ON, en `config/settings.py`): el
  server puentea `memory.updated` del bus → topic `observer` → `/events` (`server/__init__.py`). Ambas vistas
  **re-fetchean** en vivo; en SLOTS cada evento lleva `op`+`ids` → el visor **tiñe** el nodo (`[data-mid]`) unos
  segundos: **verde**=alta (`write`), **ámbar**=sobrescritura (`supersede`/`reinforce`/`state`), **azul**=query
  (`compose_recall` emite `op:"query"` con los ids que tocó). `services/sse.js` enruta `store.bumpMemory()` (refetch)
  + `store.pushMemPulse({op,ids})` (tinte).

## Evaluación de la memoria — CÓMO se prueba un sistema de memoria (teoría + práctica)

> **Encargo del operador (2026-07-10/11):** "una memoria cada vez más parecida a la de un humano pero con
> superpoderes". Para llegar ahí hay que **probarla A FONDO, de forma original y bien estructurada**, deduciendo
> cómo se pone a prueba una memoria y **aplicando lo que dice la literatura**. Esta sección es la TEORÍA canónica;
> el mapa operativo vive en `tests/e2e/memory/bot/TAXONOMY.md` (dimensiones + cobertura) y `EXIGENCIA.md` (control
> de calidad cada 50 casos). Registro de oleadas: `.meshkore/roadmap/initiatives/INI-013-voice-tester.md`.

**Qué mide la literatura (WebSearch 2026-07-11).** El campo converge en unas **habilidades núcleo**: los benchmarks
LongMemEval (ICLR 2025), LoCoMo, MemBench, **MemoryAgentBench** (ICLR 2026), MemConflict, BEAM, STALE, Mem2ActBench.
MemoryAgentBench las resume en **4 competencias + 1 hueco que casi nadie prueba**:
1. **Recuperación exacta** (accurate retrieval) — el hecho sale cuando se pide.
2. **Aprendizaje en uso** (test-time learning) — actualizar/adaptarse a lo nuevo (correcciones, reversiones).
3. **Comprensión de largo alcance** (long-range understanding) — retención profunda + multi-hop + temporal.
4. **Olvido selectivo** (selective forgetting) — decay, eviction, olvido a petición; NO todo se guarda para siempre.
5. **Organización de la estructura** (structure organization) — *el hueco*: cómo se ORGANIZA la memoria (grafo de
   conceptos), no solo qué contiene. En zaelar es el `edges`/`memory/concepts.py` y la vista CONCEPTOS del visor.

**Cómo lo probamos en zaelar (metodología).** Tres superficies, alineadas con las buenas prácticas del campo
(interacción **incremental multi-turno** + **checks de regresión** en cada cambio + **revisión humana** para lo que
un juez-LLM no puede decidir):
- **Bot de memoria** (`tests/e2e/memory/bot/`, `python -m tests.e2e.memory.bot.runner`): alimenta la memoria turno a
  turno sobre una **BD que ACUMULA** (como MemoryAgentBench: chunks incrementales), y verifica el comportamiento por
  el CAMINO REAL — `_brain_view` reconstruye EXACTAMENTE lo que ve el FlashBrain (bloque cacheado + recall si el gate
  `needs_recall` dispara), **sin LLM en la lectura**. Tipos de paso: `save`/`query`/`dedup`/`turn`/`connector`/
  `source_query`/`cluster_exchange`/`forget`/`unforget`/`consolidate`/`episode`/`scale`/`recall_probe`/`weight_check`.
- **pytest** (`tests/`, `nucleo/test_memory_agent.py`): guards deterministas de las piezas (backstops, forget/unforget,
  concept vocab, aviso de backend degradado…) — la red de regresión que corre en cada cambio.
- **Tester en vivo** (INI-013): lo que es comportamiento del LLM del turno (abstención query-time, resolución de un
  conflicto, ironía) NO es del membot (que lee sin LLM) → se prueba con el agente que HABLA con zaelar y un juez.

**Taxonomía de 27 dimensiones (A–X + subtipos).** Cada dimensión ataca UN modo de fallo distinto y se ancla a la
habilidad SOTA que le corresponde (tabla completa en `TAXONOMY.md`). Cubre extracción (telegráfica↔parrafada),
estado/corto/largo, dedup/supersede, descarte/abstención, grafo/categoría, multi-fuente, cuarentena de confianza,
intereses, temporal/orden, **escala** (needle-in-haystack a 15k, la preocupación nº1), olvido/decay, contradicciones,
privacidad, rutinas, adversarial/STT/inyección, cross-source, multilingüe, episódica, vocab-gap, **multi-hop**,
verbosidad, instrucciones permanentes, invalidación implícita (STALE), y ~30 escenarios humanos (memoria espacial,
parentesco, promesas/deudas, procedimientos, superlativos, errores, decisiones, observaciones, aversiones, metas…).

**Disciplina de calidad (`EXIGENCIA.md`).** Objetivo: 1000 casos ORIGINALES, sin duplicar. Cada 50 casos se pasa un
control: ¿duplicamos? ¿variedad (longitud de input / volumen / las 3 velocidades)? ¿qué falta? ¿cambio de approach?
¿buscar munición nueva en la literatura? ¿EVOLUCIONAR la memoria (machacar→detectar→mejorar→machacar)? De 400 a 1000
son 12 controles fechados en INI-013.

**Fronteras conocidas (cazadas por los tests, pendientes de una sesión dedicada — ver `V2-021`).** T175 (el CORAZÓN
infra-asigna `slot` → supersede/dedup en cadena incompletos), T177 (retrieval multi-hop limitado a ~1 salto de
graph_expand), **T178 + T183 (misma raíz: falta EXPANSIÓN POR CONCEPTOS en el recall** → una consulta amplia/de otro
tema no agrega ni aplica una restricción; el prerequisito de vocabulario ya está hecho), T179 (sin detección de
invalidación IMPLÍCITA/staleness), T181 (la destilación generaliza y pierde nombres propios en input verboso — no
prompt-tunable en el modelo local), T182 (una corrección SIN sujeto misatribuye el valor nuevo — el mem_processor
destila un turno sin contexto de conversación). Mejoras YA aplicadas y validadas: aviso de backend degradado (T176),
descarte de preguntas al asistente (T180), corrección de valores numéricos, olvido DURO por voz, vocabulario de
conceptos (dietéticos), y los backstops de OBSERVACIONES y REVERSIONES.

## Módulos (carpetas)

> **Decisión v2 (2026-07-09, V2-002):** la memoria es un módulo **top-level `memory/`** (hermano de `voice/`,
> `widgets/`), **NO** `nucleo/memoria/`. Es el substrato compartido — la escriben FlashBrain, el agente de
> memoria del SlowBrain y los widgets; no forma parte del cerebro. Los paths de abajo (y el diagrama Memoria de
> `/architecture`) reflejan ya esta decisión.

- `memory/db.py` — conexión SQLite `zaelar.db` (WAL) + carga de `sqlite-vec` + migraciones de schema.
- `memory/schema.py` — DDL (state · memories · vec_memories · fts_memories · edges · episodic · journal).
- `memory/queue.py` — cola async (asyncio.Queue): todas las escrituras entran aquí.
- `memory/writer.py` — único escritor → BD; embeddings locales al insertar. **ENFORCEMENT de firma de embedding**
  (F1, 2026-07-20): si el modelo de embedding activo no casa con la firma de la BD (o está degradado), la píldora
  se marca `meta.embed_pending` en vez de insertar un vector de OTRO espacio (la fase REM la repara) — nunca se
  mezclan espacios vectoriales en silencio (incidente fastembed bge-EN, 2026-07-17/19).
- `memory/embeddings.py` — cliente de embeddings locales (Ollama embeddinggemma 768 · fallback fastembed).
- `memory/retriever.py` — ruta caliente: vec ∥ fts → RRF → score ponderado → graph_expand.
- `memory/state.py` — tabla fija (lectura µs, sin búsqueda).
- `memory/graph.py` — aristas (link/expand).
- `memory/episodic.py` — ficheros/PDF: resumen embebido buscable + carga lazy del binario.
- `memory/consolidator.py` — el job "sueño" LIGERO (horario: promote/dedup-exacto/decay POR VENTANA/prune_invalid/evict).
- **`memory/rem.py`** — el sueño PROFUNDO «fase REM» (V2-056, diario): repair_embeddings + semantic_dedup +
  synthesize (insights por concepto, hook LLM inyectado) + hygiene. Ver §Sueño PROFUNDO.
- `memory/api.py` — fachada pública (write[+`slot`/`meta`]/write_now/query/**recent_short**/state/set_state/reinforce/pin/unpin/link/load_episode/consolidate/**map**).
- **`nucleo/mem_processor.py`** — el procesador LLM (default `gpt-4.1-mini` vía OpenAI, opción local qwen; §12)
  que DESTILA cada turno en píldoras; vive en `nucleo/` (es cerebro de escritura, no substrato) pero es el corazón
  que decide qué entra a `memory/`. Ver §El CORAZÓN.
- **`nucleo/memllm.py`** — router interno de modelos POR TAREA del módulo de memoria (V2-056: tarea `rem` +
  futuras), config `§memory.<task>_*` + key POR ENDPOINT; la memoria recibe el hook INYECTADO (no importa cerebros).
- Datos: `zaelar.db` (SQLite) en `memory/_data/` (gitignored). Override por `ZAELAR_DB`.
