"""memory/schema.py — DDL de la memoria central (V2-002).

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
SCHEMA_VERSION = 3


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


# ── Tablas virtuales (condicionales) ────────────────────────────────────────────────────────────────────────

# Vector (sqlite-vec). Solo si la extensión está cargada.
def vec_memories_ddl(dim: int = EMBED_DIM) -> str:
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0("
        f"memory_id INTEGER PRIMARY KEY, embedding FLOAT[{dim}])"
    )


# Keyword exacto (FTS5). content='memories' → índice externo sincronizado por el writer.
FTS_MEMORIES = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories "
    "USING fts5(text, content='memories', content_rowid='id')"
)


BASE_DDL = [STATE, MEMORIES, *MEMORIES_INDEXES, EDGES, *EDGES_INDEXES, EPISODIC, JOURNAL, SYS_KV,
            VAULT_META, VAULT_SECRETS]
