"""memory/schema.py — central memory DDL (V2-002).

Copia FIEL del schema de `.meshkore/docs/architecture/zaelar-memory.md §Schema SQLite`. Un solo fichero
`zaelar.db`. Las tablas virtuales (`vec_memories` = sqlite-vec vec0, `fts_memories` = FTS5) solo se crean si
la extensión correspondiente está disponible en la conexión (sqlite-vec puede faltar en algún entorno; FTS5
viene en la amalgama estándar de SQLite). `db.py` decide qué crear según capacidades y lleva la versión de
schema en `PRAGMA user_version`.

`EMBED_DIM` es la dimensión del vector (embeddinggemma → 768). El schema de `vec_memories` se formatea con
esta constante para que un cambio de modelo de embeddings sea un solo sitio.
"""

# Dimensión del embedding (embeddinggemma 768; Matryoshka permite truncar, pero fijamos 768 por defecto).
EMBED_DIM = 768

# Versión del schema. Súbela al añadir/alterar tablas y añade la migración correspondiente en db.py.
#   v1 → v2 (V2-013): la memoria es una PÍLDORA — se añaden `slot` (clave canónica para supersede/dedup exacto)
#   y `meta` (JSON libre: entity/attribute/source/said_at/confidence…). Migración ALTER idempotente en db.py.
#   v2 → v3 (V2-060): BÓVEDA DE SECRETOS. Dos tablas nuevas (`vault_meta`, `vault_secrets`) para los secretos del
#   operador cifrados (contraseñas, IBAN, private keys). El VALOR va cifrado y OPACO en `vault_secrets` (nunca en
#   `memories`); en `memories` solo vive la ETIQUETA en claro y buscable (píldora normal con `meta.vault=1`). Ambas
#   con CREATE IF NOT EXISTS en BASE_DDL → migración idempotente, no destructiva.
#   v3 → v4 (V2-031 T2, 2026-08-17): ÍNDICE DE PARÁFRASIS al escribir — cierra el vocab-gap ("instrumento" vs
#   "guitarra") sin LLM en la lectura. `paraphrase_index` (real, PK sintética porque una píldora puede tener
#   varias reformulaciones) + `vec_paraphrases` (vec0, keyed por esa PK sintética, NUNCA por `memory_id` — un
#   `memory_id` puede necesitar N vectores, `vec_memories` exige 1). El retriever las funde en la fusión RRF
#   mapeando de vuelta al `memory_id` real — nunca se devuelven como resultado por sí mismas.
#   v4 → v5 (V2-111 §9.2, 2026-08-17): BI-TEMPORAL explícito. `updated` no sirve como "cuándo se invalidó" —
#   lo toca también el refuerzo (`writer.reinforce`) y la promoción de nivel del consolidador, así que una
#   fila ya inválida no garantiza que `updated` sea el momento de su invalidación. `valid_at` (cuándo el hecho
#   pasó a ser cierto, por defecto = `created`) e `invalidated_at` (NULL mientras `valid=1`, fijado UNA VEZ,
#   nunca vuelto a tocar) permiten reconstruir "qué estaba vigente en la fecha X" (`memory/api.py::as_of()`).
#   v5 → v6 (V2-242, 2026-08-21): background pills written by a widget tick get their author into the KEY.
#   Readers separate «the operator's own facts» from «a background job's dump» by the SHAPE of the slot (dots
#   for the person, a namespace for background). `TickCtx.remember` now enforces that on write, but the pills
#   already on disk keep the old shape — and supersede is by EXACT slot, so a `weather:soria` written for months
#   would never be replaced by the new `meteo-soria:weather:soria`: two live lineages of the same fact, the old
#   one frozen forever and still competing in recall. This renames them in place, using `meta.widget` (which the
#   old writer already stamped, so the author is known for every one of them).
SCHEMA_VERSION = 6


# ── Tablas base (siempre) ──────────────────────────────────────────────────────────────────────────────────

# Estado: fila única, SIEMPRE en el prompt, sin búsqueda (µs).
STATE = """
CREATE TABLE IF NOT EXISTS state (
  id   INTEGER PRIMARY KEY CHECK (id = 1),
  data TEXT NOT NULL          -- JSON: nombres · idioma · reglas de trato · ubicación · recientes · temas
);
"""

# Recuerdos (corto/medio/largo). Núcleo del olvido-por-peso + refuerzo.
MEMORIES = """
CREATE TABLE IF NOT EXISTS memories (
  id            INTEGER PRIMARY KEY,
  level         TEXT NOT NULL,      -- 'short' | 'mid' | 'long'
  kind          TEXT NOT NULL,      -- 'fact' | 'pref' | 'event' | 'msg' | 'summary' | 'insight'
  text          TEXT NOT NULL,
  importance    REAL DEFAULT 0.5,   -- I0 base (por tipo)
  weight        REAL DEFAULT 0.5,   -- peso VIVO: sube con el uso, baja con el decay
  access_count  INTEGER DEFAULT 0,
  last_access   INTEGER,            -- epoch (para recencia y decay)
  ttl_days      REAL,               -- NULL = infinito (hechos inmutables)
  pinned        INTEGER DEFAULT 0,  -- 1 = NUNCA se borra
  valid         INTEGER DEFAULT 1,  -- 0 = superseded por otro
  superseded_by INTEGER,
  slot          TEXT,               -- v2: clave canónica del hecho singular (operator.name, goal.current…) → supersede/dedup EXACTO sin LLM
  meta          TEXT,               -- v2: píldora JSON libre (entity/attribute/source/said_at/confidence…) — no toca el hot path
  created       INTEGER NOT NULL,
  updated       INTEGER NOT NULL
);
"""

MEMORIES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_mem_level   ON memories(level)",
    "CREATE INDEX IF NOT EXISTS idx_mem_kind    ON memories(kind)",
    "CREATE INDEX IF NOT EXISTS idx_mem_valid   ON memories(valid)",
    "CREATE INDEX IF NOT EXISTS idx_mem_pinned  ON memories(pinned)",
    "CREATE INDEX IF NOT EXISTS idx_mem_weight  ON memories(weight)",
    "CREATE INDEX IF NOT EXISTS idx_mem_access  ON memories(last_access)",
    # V2-103: soporta el dedup EXACTO síncrono en `writer.insert_memory` (LOWER(text)=LOWER(?), filas sin slot) —
    # no depende de ninguna columna v2, va en BASE_DDL como los demás.
    "CREATE INDEX IF NOT EXISTS idx_mem_text_lower ON memories(LOWER(text))",
]

# Migraciones ALTER idempotentes por columna (v1→v2). `db.py` las aplica: añade la columna solo si falta (SQLite
# no soporta `ADD COLUMN IF NOT EXISTS`, así que db.py comprueba `PRAGMA table_info` antes). No destructivo.
MEMORIES_V2_COLUMNS = [
    ("slot", "ALTER TABLE memories ADD COLUMN slot TEXT"),
    ("meta", "ALTER TABLE memories ADD COLUMN meta TEXT"),
]

# v4→v5 (V2-111 §9.2): bi-temporal. `valid_at` se backfillea a `created` en filas existentes (db.py, una vez,
# guardado por `WHERE valid_at IS NULL`); `invalidated_at` se queda NULL en filas existentes — no hay forma
# retroactiva de saber cuándo se invalidaron, así que no se inventa un valor (mejor NULL honesto que una
# fecha inventada que `as_of()` daría por buena).
MEMORIES_V5_COLUMNS = [
    ("valid_at", "ALTER TABLE memories ADD COLUMN valid_at INTEGER"),
    ("invalidated_at", "ALTER TABLE memories ADD COLUMN invalidated_at INTEGER"),
]
MEMORIES_V5_INDEXES = [
    # `as_of()` filtra por slot + ventana de vigencia — compuesto, no dos mono-columna (mismo motivo que
    # `idx_mem_lvu` en v2: la query caliente es compuesta, un índice por columna no la sirve).
    "CREATE INDEX IF NOT EXISTS idx_mem_slot_validat ON memories(slot, valid_at)",
]

# Índices que dependen de las columnas v2 → se crean DESPUÉS del ALTER (nunca en BASE_DDL, que corre antes de la
# migración de columnas y reventaría en una BD v1 sin `slot`).
MEMORIES_V2_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_mem_slot ON memories(slot)",
    # Compuestos/expresión (auditoría 2026-07-19 P2-9): las queries CALIENTES son compuestas —
    # recent_short/recent_window filtran (level,valid)+ORDER BY updated; recent_by_source/critical_facts filtran
    # por json_extract(meta,…). Los mono-columna obligaban a full scan de durables en cada refresh del caché.
    "CREATE INDEX IF NOT EXISTS idx_mem_lvu ON memories(level, valid, updated DESC)",
    "CREATE INDEX IF NOT EXISTS idx_mem_meta_source ON memories(json_extract(meta, '$.source'))",
    "CREATE INDEX IF NOT EXISTS idx_mem_meta_trust ON memories(json_extract(meta, '$.trust'))",
    "CREATE INDEX IF NOT EXISTS idx_mem_meta_critical ON memories(json_extract(meta, '$.critical'))",
]

# Grafo como aristas en el MISMO fichero (nada de Neo4j).
EDGES = """
CREATE TABLE IF NOT EXISTS edges (
  from_id INTEGER NOT NULL,
  to_id   INTEGER NOT NULL,
  type    TEXT NOT NULL,           -- 'about' | 'same_person' | 'caused' | 'refines' ...
  weight  REAL DEFAULT 1.0,
  PRIMARY KEY (from_id, to_id, type)
);
"""

EDGES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_to   ON edges(to_id)",
]

# Episódica lazy: ficheros/PDF. Solo el RESUMEN (fila en memories) participa en la búsqueda.
EPISODIC = """
CREATE TABLE IF NOT EXISTS episodic (
  id        INTEGER PRIMARY KEY,
  path      TEXT NOT NULL,         -- ruta local al fichero
  summary   TEXT NOT NULL,
  memory_id INTEGER,               -- resumen indexado en vec/fts vía memories
  bytes     INTEGER,
  mime      TEXT,
  created   INTEGER
);
"""

# Continuidad de tarea.
# KV interno de mantenimiento (marcadores del consolidador: decay_last_run, rem_last_run…). NO es memoria del
# operador — jamás se pinta en el visor ni entra en prompts.
SYS_KV = """
CREATE TABLE IF NOT EXISTS sys_kv (
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""

JOURNAL = """
CREATE TABLE IF NOT EXISTS journal (
  id      INTEGER PRIMARY KEY,
  title   TEXT NOT NULL,
  status  TEXT NOT NULL,           -- 'pending' | 'in_progress' | 'done'
  detail  TEXT,
  created INTEGER,
  updated INTEGER
);
"""

# ── Bóveda de secretos del operador (V2-060) ─────────────────────────────────────────────────────────────────
# Metadatos de la bóveda: fila ÚNICA. La clave PÚBLICA vive EN CLARO (sella secretos nuevos SIN desbloqueo); la
# privada NO se guarda en claro nunca — va ENVUELTA (cifrada) en `wraps` por cada método de desbloqueo (passphrase
# Argon2id y/o passkey WebAuthn). `wraps` = JSON [{method, ...params, wrapped_sk_b64}, …]. Ver `memory/vault.py`.
VAULT_META = """
CREATE TABLE IF NOT EXISTS vault_meta (
  id         INTEGER PRIMARY KEY CHECK (id = 1),
  public_key BLOB NOT NULL,         -- Curve25519 public key (CLARO — sellar no requiere desbloqueo)
  wraps      TEXT NOT NULL,         -- JSON: sobres de la clave privada, uno por método de desbloqueo
  created    INTEGER NOT NULL,
  updated    INTEGER NOT NULL
);
"""

# El VALOR del secreto, CIFRADO y OPACO (sealed box a la clave pública). Keyed por el id de la píldora-etiqueta en
# `memories` (la parte buscable, en claro). NUNCA se embebe, loguea ni entra en un prompt. Sin la clave privada es
# indescifrable → puede vivir en disco/backup/nube sin riesgo.
VAULT_SECRETS = """
CREATE TABLE IF NOT EXISTS vault_secrets (
  memory_id  INTEGER PRIMARY KEY,   -- id de la píldora-etiqueta en `memories`
  ciphertext BLOB NOT NULL,         -- crypto_box_seal(public_key, valor) — opaco
  created    INTEGER NOT NULL
);
"""


# ── Índice de paráfrasis al escribir (V2-031 T2) ────────────────────────────────────────────────────────────
# Tabla REAL con PK sintética (`id`) — un `memory_id` puede tener 1-2 reformulaciones, así que no puede ser la
# clave del vec0 (que exige unicidad). `vec_paraphrases` (abajo) usa ESTE `id`, nunca `memory_id`, como su PK.
PARAPHRASE_INDEX = """
CREATE TABLE IF NOT EXISTS paraphrase_index (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  memory_id  INTEGER NOT NULL,
  text       TEXT NOT NULL,
  created    INTEGER NOT NULL
);
"""
PARAPHRASE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_paraphrase_memory ON paraphrase_index(memory_id)",
]


# ── Action map (V2-539) ─────────────────────────────────────────────────────────────────────────────────────
# Known command phrases → verified direct actions, matched BEFORE the fast LLM (`nucleo/actionmap/`). One row
# per (lang, normalized phrase); `action` is opaque JSON validated by the executor's allowlist at load, never
# here. `source`/`status` carry provenance and the user's vetoes: a seed row the user disabled must survive a
# seed re-import (the importer respects status != 'active' and hits > 0). Runtime only ever loads ONE lang.
ACTION_MAP = """
CREATE TABLE IF NOT EXISTS action_map (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  lang        TEXT NOT NULL,
  phrase      TEXT NOT NULL,
  action      TEXT NOT NULL,
  source      TEXT NOT NULL DEFAULT 'seed',
  status      TEXT NOT NULL DEFAULT 'active',
  hits        INTEGER NOT NULL DEFAULT 0,
  agree       INTEGER NOT NULL DEFAULT 0,
  disagree    INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL,
  last_hit_at INTEGER,
  UNIQUE(lang, phrase)
);
"""
ACTION_MAP_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_action_map_lang ON action_map(lang, status)",
]


# V2-594 · WORKFLOWS — «for this kind of errand, which channel actually works, and is that still true?»
#
# One row per (domain, channel). It is NOT a second action_map: `action_map` maps a PHRASE to a LOCAL action
# on a widget and never leaves the machine, while this maps a DOMAIN of errand to the ORDER of external
# channels to try. They meet only in that both are looked up by a function and cost ZERO prompt tokens.
#
# The row that matters most is the NEGATIVE one (`status='none'`): «the mesh has nothing for wellness». Until
# now that answer was thrown away every time, so every errand of an uncovered kind paid the Oracle round trip
# again — and then paid a language model to narrate the emptiness. A negative row with a TTL is what stops
# both. It EXPIRES on purpose: a new agent appears on the mesh and the answer has to be allowed to change.
WORKFLOWS = """
CREATE TABLE IF NOT EXISTS workflows (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  domain      TEXT NOT NULL,
  channel     TEXT NOT NULL,
  rank        INTEGER NOT NULL DEFAULT 100,
  status      TEXT NOT NULL DEFAULT 'active',
  source      TEXT NOT NULL DEFAULT 'seed',
  target      TEXT,
  evidence    TEXT,
  hits        INTEGER NOT NULL DEFAULT 0,
  ttl_s       INTEGER NOT NULL DEFAULT 604800,
  checked_at  INTEGER,
  created_at  INTEGER NOT NULL,
  last_hit_at INTEGER,
  UNIQUE(domain, channel)
);
"""
WORKFLOWS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_workflows_domain ON workflows(domain, status, rank)",
]


# ── Tablas virtuales (condicionales) ────────────────────────────────────────────────────────────────────────

# Vector (sqlite-vec). Solo si la extensión está cargada.
def vec_memories_ddl(dim: int = EMBED_DIM) -> str:
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0("
        f"memory_id INTEGER PRIMARY KEY, embedding FLOAT[{dim}])"
    )


# Vectores de PARÁFRASIS (V2-031 T2) — PK sintética (`paraphrase_index.id`), NUNCA `memory_id` (ver arriba).
def vec_paraphrases_ddl(dim: int = EMBED_DIM) -> str:
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_paraphrases USING vec0("
        f"id INTEGER PRIMARY KEY, embedding FLOAT[{dim}])"
    )


# Keyword exacto (FTS5). content='memories' → índice externo sincronizado por el writer.
FTS_MEMORIES = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories "
    "USING fts5(text, content='memories', content_rowid='id')"
)


BASE_DDL = [STATE, MEMORIES, *MEMORIES_INDEXES, EDGES, *EDGES_INDEXES, EPISODIC, JOURNAL, SYS_KV,
            VAULT_META, VAULT_SECRETS, PARAPHRASE_INDEX, *PARAPHRASE_INDEXES,
            ACTION_MAP, *ACTION_MAP_INDEXES, WORKFLOWS, *WORKFLOWS_INDEXES]
