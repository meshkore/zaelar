"""memory/schema — central memory DDL (V2-002), one `zaelar.db` file.

Mirrors `.meshkore/docs/architecture/zaelar-memory.md §Schema SQLite`. The virtual tables (`vec_memories` =
sqlite-vec vec0, `fts_memories`/`fts_tasks` = FTS5) are only created when the extension is available on the
connection; `db.py` decides what to create and tracks the version in `PRAGMA user_version`.

  memories.py  the memory proper: state, pills, edges, episodic, journal, sys_kv, vault, paraphrases, vec/FTS
  ledgers.py   process state that is never a pill: action map, workflows, errands, tasks, notices, push devices
"""
from .ledgers import (  # noqa: F401
    ACTION_MAP, ACTION_MAP_INDEXES, ERRAND_THREADS, ERRANDS, ERRANDS_INDEXES, FTS_TASKS, NOTICES, NOTICES_INDEXES,
    PUSH_DEVICES, TASK_ARTIFACTS, TASKS, TASKS_INDEXES, TASKS_STATUS_COLUMNS, TASKS_V9_COLUMNS, WORKFLOWS,
    WORKFLOWS_INDEXES,
)
from .memories import (  # noqa: F401
    EDGES, EDGES_INDEXES, EMBED_DIM, EPISODIC, FTS_MEMORIES, JOURNAL, MEMORIES, MEMORIES_INDEXES, MEMORIES_V2_COLUMNS,
    MEMORIES_V2_INDEXES, MEMORIES_V5_COLUMNS, MEMORIES_V5_INDEXES, PARAPHRASE_INDEX, PARAPHRASE_INDEXES, STATE,
    SYS_KV, VAULT_META, VAULT_SECRETS, vec_memories_ddl, vec_paraphrases_ddl,
)

# Schema version. Bump it when adding/altering tables and add the migration in db.py. Every step is additive
# (IF NOT EXISTS, or an idempotent ALTER checked against `PRAGMA table_info`).
#   v2 (V2-013)  the memory is a PILL: `slot` (canonical key for exact supersede/dedup) + `meta` (free JSON).
#   v3 (V2-060)  the secret vault: `vault_meta`, `vault_secrets` (the value opaque, the label a normal pill).
#   v4 (V2-031)  write-time paraphrase index: `paraphrase_index` + `vec_paraphrases`, keyed by a SYNTHETIC id
#                (a pill may need N vectors, `vec_memories` allows 1); the retriever maps hits back to `memory_id`.
#   v5 (V2-111)  explicit bi-temporal: `valid_at` + `invalidated_at` (set ONCE). `updated` cannot say when a row
#                was invalidated — reinforcement and level promotion touch it too.
#   v6 (V2-242)  background pills renamed in place to carry their author in the slot (`<widget>:…`, from
#                `meta.widget`): supersede is by EXACT slot, so an old-shape slot would never be replaced.
#   v7 (V2-728)  the TASK is the unit: `tasks` + `task_artifacts` + `fts_tasks` replace five partial stores.
#   v8 (V2-776)  a worker's live state, durable (`TASKS_STATUS_COLUMNS`).
#   v9 (V2-776)  the circuit's verdict per row (`TASKS_V9_COLUMNS`).
#   v10 (refactor2710-11) a request the distiller stored as `result` is relabelled `request`: a result is only
#                the circuit's verdict. Selected by provenance (`meta.path='llm'`), never by wording.
SCHEMA_VERSION = 10

BASE_DDL = [STATE, MEMORIES, *MEMORIES_INDEXES, EDGES, *EDGES_INDEXES, EPISODIC, JOURNAL, SYS_KV,
            VAULT_META, VAULT_SECRETS, PARAPHRASE_INDEX, *PARAPHRASE_INDEXES,
            ACTION_MAP, *ACTION_MAP_INDEXES, WORKFLOWS, *WORKFLOWS_INDEXES,
            ERRANDS, ERRAND_THREADS, *ERRANDS_INDEXES,
            TASKS, TASK_ARTIFACTS, *TASKS_INDEXES,
            NOTICES, PUSH_DEVICES, *NOTICES_INDEXES]
