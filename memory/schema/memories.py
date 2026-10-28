"""The memory proper: the fixed state row, the pills and their migrations, the graph, episodic files, the task
journal, maintenance kv, the secret vault, the paraphrase index and the conditional vec/FTS virtual tables."""

# Embedding dimension (embeddinggemma 768; Matryoshka allows truncation, 768 is the default). `vec_memories` is
# formatted from it so an embedding-model change is one place.
EMBED_DIM = 768

# State: a single row, ALWAYS in the prompt, no search (µs).
STATE = """
CREATE TABLE IF NOT EXISTS state (
  id   INTEGER PRIMARY KEY CHECK (id = 1),
  data TEXT NOT NULL          -- JSON: nombres · idioma · reglas de trato · ubicación · recientes · temas
);
"""

# Memories (short/mid/long). The core of forgetting-by-weight + reinforcement.
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
    # V2-103: serves the synchronous EXACT dedup in `writer.insert_memory` (LOWER(text)=LOWER(?), slotless rows).
    "CREATE INDEX IF NOT EXISTS idx_mem_text_lower ON memories(LOWER(text))",
]

# Idempotent per-column ALTERs (v1→v2). SQLite has no `ADD COLUMN IF NOT EXISTS`: db.py checks `PRAGMA
# table_info` first.
MEMORIES_V2_COLUMNS = [
    ("slot", "ALTER TABLE memories ADD COLUMN slot TEXT"),
    ("meta", "ALTER TABLE memories ADD COLUMN meta TEXT"),
]

# v4→v5 (V2-111): bi-temporal. `valid_at` is backfilled to `created` once; `invalidated_at` stays NULL on old rows
# — there is no source for when they were invalidated, and an honest NULL beats a date `as_of()` would trust.
MEMORIES_V5_COLUMNS = [
    ("valid_at", "ALTER TABLE memories ADD COLUMN valid_at INTEGER"),
    ("invalidated_at", "ALTER TABLE memories ADD COLUMN invalidated_at INTEGER"),
]
MEMORIES_V5_INDEXES = [
    # `as_of()` filters by slot + validity window: composite, since one index per column does not serve it.
    "CREATE INDEX IF NOT EXISTS idx_mem_slot_validat ON memories(slot, valid_at)",
]

# Indexes on the v2 columns → created AFTER the ALTER (never in BASE_DDL, which runs before the column migration
# and would blow up on a v1 DB without `slot`).
MEMORIES_V2_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_mem_slot ON memories(slot)",
    # The HOT queries are composite ((level,valid)+ORDER BY updated; json_extract(meta,…)); single-column indexes
    # forced a full scan of the durables on every cache refresh.
    "CREATE INDEX IF NOT EXISTS idx_mem_lvu ON memories(level, valid, updated DESC)",
    "CREATE INDEX IF NOT EXISTS idx_mem_meta_source ON memories(json_extract(meta, '$.source'))",
    "CREATE INDEX IF NOT EXISTS idx_mem_meta_trust ON memories(json_extract(meta, '$.trust'))",
    "CREATE INDEX IF NOT EXISTS idx_mem_meta_critical ON memories(json_extract(meta, '$.critical'))",
]

# The graph as edges in the SAME file (no Neo4j).
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

# Lazy episodic: files/PDFs. Only the SUMMARY (a row in memories) takes part in search.
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

# Internal maintenance kv (consolidator markers: decay_last_run, rem_last_run…). NOT the operator's memory — never
# painted in the viewer nor put in a prompt.
SYS_KV = """
CREATE TABLE IF NOT EXISTS sys_kv (
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""

# Task continuity.
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

# ── the operator's secret vault (V2-060, see `memory/vault/`) ─────────────────────────────────────────────
# A SINGLE row. The PUBLIC key is in clear (sealing needs no unlock); the private key is never in clear — it is
# WRAPPED in `wraps` once per unlock method: JSON [{method, ...params, wrapped_sk_b64}, …].
VAULT_META = """
CREATE TABLE IF NOT EXISTS vault_meta (
  id         INTEGER PRIMARY KEY CHECK (id = 1),
  public_key BLOB NOT NULL,         -- Curve25519 public key (CLARO — sellar no requiere desbloqueo)
  wraps      TEXT NOT NULL,         -- JSON: sobres de la clave privada, uno por método de desbloqueo
  created    INTEGER NOT NULL,
  updated    INTEGER NOT NULL
);
"""

# The secret's VALUE, sealed and OPAQUE, keyed by the id of its label pill in `memories`. Never embedded, logged
# or put in a prompt; undecryptable without the private key, so it may live on disk/backup/cloud.
VAULT_SECRETS = """
CREATE TABLE IF NOT EXISTS vault_secrets (
  memory_id  INTEGER PRIMARY KEY,   -- id de la píldora-etiqueta en `memories`
  ciphertext BLOB NOT NULL,         -- crypto_box_seal(public_key, valor) — opaco
  created    INTEGER NOT NULL
);
"""


# ── write-time paraphrase index (V2-031 T2) ──────────────────────────────────────────────────────────────
# A REAL table with a synthetic PK: one `memory_id` may have 1-2 rephrasings, so it cannot key the vec0 (which
# requires uniqueness). `vec_paraphrases` uses THIS `id`, never `memory_id`.
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


# ── virtual tables (conditional) ─────────────────────────────────────────────────────────────────────────

# Vector (sqlite-vec). Only if the extension is loaded.
def vec_memories_ddl(dim: int = EMBED_DIM) -> str:
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0("
        f"memory_id INTEGER PRIMARY KEY, embedding FLOAT[{dim}])"
    )


# PARAPHRASE vectors (V2-031 T2) — synthetic PK (`paraphrase_index.id`), NEVER `memory_id` (see above).
def vec_paraphrases_ddl(dim: int = EMBED_DIM) -> str:
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_paraphrases USING vec0("
        f"id INTEGER PRIMARY KEY, embedding FLOAT[{dim}])"
    )


# Exact keyword (FTS5). content='memories' → an external index kept in sync by the writer.
FTS_MEMORIES = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories "
    "USING fts5(text, content='memories', content_rowid='id')"
)
