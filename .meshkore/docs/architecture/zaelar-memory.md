# zaelar — the MEMORY subsystem (v2 architecture, «Colmena»)

> **Status:** operational. Top-level module `memory/` — see §Modules. Key pieces: the SQLite substrate, a
> three-speed read path, the write HEART (an LLM that distils every turn into pills), the memory map viewer and
> observability, light and deep (REM) sleep, a canonical slot registry with the v2 `value`/`change` atom contract,
> a gated external write path for Brain Workers, RAILS projected into `state.rails`, the `recall` tool of the
> FlashBrain, the multi-axis worker dossier (`compose_context`), and memory models chosen by benchmark
> (`zaelar-model-benchmarks.md §12`).
>
> **At a glance**
> - **Schema v9, 19 tables** (on a fresh `zaelar.db`): `state`, `memories` + `vec_memories` + `fts_memories`,
>   `edges`, `episodic`, `journal`, `sys_kv`, `tasks` + `task_artifacts` + `fts_tasks` (v9 adds `tasks.verdict`),
>   `errands` + `errand_threads`, `workflows`, `action_map`, `paraphrase_index` + `vec_paraphrases`,
>   `vault_meta` + `vault_secrets`.
> - **Spoken rules are not memory** (V2-806): they are rows of the rules table (`rules/`, its own table in the same
>   `zaelar.db`), imported once from the old `state.rules` / `state.rule_scopes`; memory neither holds nor renders
>   them. `zaelar-rules.md`, CRIT-M1, CRIT-M7.
> - **Genesis is per domain** (`style`, `consent`, `library`, `errands`, `playbooks`, `circuit`), each with its own
>   override file under `<workspace>/config/`. CRIT-M2.
> - **Factory reset** (`scripts/reset-memory.sh`) forgets the memory and the spoken rules (their override files are
>   in `FACTORY_PATHS`) and keeps credentials, settings and connectors; it never deletes under a live server.
> - **Recall degrades, never vanishes**: a slow or failed embedder drops the recall to lexical (FTS, then LIKE) and
>   records `memory: degraded` in health; embeddings have no failover row (a mixed vector space is worse than none).
> - **The record block**: «what is going on» is read from the `tasks` rows (`task_block.recent_lines`, inline
>   requests included), not from RAM registries. See `zaelar-architecture.md` §5h.
> - **Models** are declared in `config/models.default.json` (public defaults; the UI's `config/v2.json` overrides
>   them). See §Memory models.
>
> **Golden latency rule:** **LLM when WRITING (off the hot path), DIRECT queries when READING (no LLM on the path).**
> **Live diagram:** the public architecture diagrams (Memory tab) link here rather than duplicating the detail.
> **Source of truth** for *how it is built*: this document. To START working on the memory, read at least
> §«Reading in the turn — THREE speeds», §«The write HEART» and §«Memory observability».

A **human-like** memory whose **storage and retrieval run in-process** (SQLite + read path + vector index +
reranker: no external database or broker, cross-platform; mobile is a future target worth keeping in mind). It is
**ours** — never a black box. The **models** the memory calls (embeddings, the write HEART, REM synthesis) are
configurable providers: cloud by default so that every deployment measures the same system, with local options
(Ollama) for whoever prioritises privacy or offline use — see §Design principles.

## Design principles (decided, not to be reopened)

- **Local, one file.** Everything lives in a single SQLite file, `zaelar.db`. No server, no broker. Storage, the
  three-speed read path and the reranker run in-process. The **models** are a separate, configurable concern:
  the **write LLMs** (the distilling HEART and the REM synthesis) and the **embeddings** go to an external API by
  default, because write quality is the number-one lever of recall and the measured external models win it
  clearly; and because a default that only exists on a laptop (a local Ollama server) would make a laptop measure
  something different from a container. **Which model is chosen by the benchmark, not by provider reputation**
  (`zaelar-model-benchmarks.md §12.3`). The **local option** (the table's `local` block — one Ollama chat model for
  the HEART and `embeddinggemma` for the embeddings) stays available by config (`§memory.mem_processor_*`,
  `§memory.embed_*`, or the `local` profile) for whoever prioritises privacy/offline use. When the
  HEART runs on DeepSeek it uses the **direct** endpoint (`api.deepseek.com`), which honours
  `thinking:{"type":"disabled"}` where a broker may ignore it.
- **Insertion through an async queue — it may be slow.** Every source writes into a **queue**; only the queue
  (a **single writer**) touches the database → zero write collisions. Readers use **WAL** and never block.
- **Search in milliseconds.** This is the **hot path**: a prompt arrives and the **minimal context** has to be
  composed as fast as possible.
- **Writers:** the FlashBrain, the SlowBrain's memory agent, and widgets (e.g. messaging dumps what comes in).
  **What is irrelevant is discarded on the fly**; what is relevant is kept.
- **MONOLINGUAL — the memory lives in the OPERATOR'S LANGUAGE.** The whole system adapts to ONE language (the
  person's; if they speak German, everything moves to German — see `voice/engine/core/langs.py`,
  `ZAELAR_LANGUAGE`). The memory is NOT multilingual inside: the **HEART distils every pill in the canonical
  language** (`state.language`), **translating** whatever the operator says in another language — and **never
  discards a durable fact because it came in another language** (`nucleo/mem_processor._render`). So READING is
  always same-language (no cross-lingual gap, no complexity of indexing N languages). The FlashBrain DOES
  **understand** several languages (STT + model) and its gates/heuristics are es/en tolerant, but what is STORED
  and RECALLED stays in the operator's language. *Why:* a multilingual memory multiplies the cost (embeddings and
  recall across languages, duplicates per language) without helping the real case — one operator with their
  language.

## Layers (human-like memory)

- **State** — the VARIABLE part of the context that is **ALWAYS injected into the prompt, without search** (a
  fixed-table read, µs), as opposed to the FIXED part of the core (instructions/goal). It is the "what happened two
  hours ago is practically in context". It carries: our name and the person's, language, rules of address (direct
  vs elaborate…), where they live, topics discussed, and the **LIVE UI CONTEXT — what the operator has IN FRONT of
  them right now**: `open_widgets` (widgets open on the canvas), `activity`/`sessions` (SlowBrain tasks/sessions in
  progress) and **`rails`** (live runs of the FlashBrain RAILS — what is being searched/playing and the ISOLATED
  `sin_resolver` failures that can be resumed — projected by `nucleo/rails.py`, rendered as "Rails in progress").
  With that the brain resolves "modify/open the X widget" by looking at what is on screen — if it is open or the
  only one, it acts without asking. `open_widgets` is written by the frontend (authoritative for the canvas,
  `POST /api/canvas/state` from `desktop._persist()`); `activity`/`sessions` by the SlowBrain dispatcher; `rails`
  is projected by `nucleo/rails.py`. The operator's spoken RULES no longer live here: since V2-806 they are rows of
  the rules table (`rules/`, `zaelar-rules.md`), and the old `rules` / `rule_scopes` keys are imported there once.
  Schema in `memory/state.py`.
- **Short term = RECENT memory (short term and recency are THE SAME module, ONE format).** They are so closely
  related that separating them would be duplication. It is **one** recent memory, in a **MIXED format** (less
  storage-efficient, but simple and sufficient): the `level='short'` rows that are **read WHOLE** into the prompt
  (`recent_short` → "Recent conversation" block). That same block answers both "what did I just say?" (the most
  recent) and "what have we talked about / what is this about?" (steering the conversation). **No separate digest
  is created and `state` is not used** (STATE is permanent and has nothing to do with the last hour). Refinements
  live inside the same module: storing the compressed turn instead of the raw pair, and **detail decay by age**
  via consolidation (minutes almost verbatim → the hour summarised → yesterday a headline → older nothing, or
  promoted to LONG). It covers conversation AND activity (files, widgets).
- **Mid term** — session summaries; the short term that survives is archived here and later to long term.
- **Long term / store** — semantic recall + durable facts.
- **Task continuity** — a journal with status (pending / in progress / done): "how is that task going?".
- **Lazy-loaded episodic** — uploaded files/PDFs. They are kept with an **embedded summary** that DOES take part in
  search; the full file is only loaded on command ("look at the report") or if the retriever selects it. Never in
  context by default.

## States by SCOPE (a dimension distinct from the "Layers")

The "Layers" above organise the memory by **SPEED/permanence** (state µs → short → mid → long → episodic). There is
a second, orthogonal dimension that the code builds: the **SCOPE** — WHOSE/WHAT a piece of state is about. Three
rings, from widest to narrowest:

1. **The operator's GLOBAL state** (`memory/state.py`, table `state`, single row `id=1`) — the awareness of itself
   and of its surroundings that the FlashBrain ALWAYS carries in the prompt: identity/mission, language, address,
   location, `rules` (the operator's style rules), `open_widgets`/`activity`/`sessions`/`rails` (live UI context),
   `security` (hard flags such as `secrets_voice`). There is ONE operator and ONE row — this is the ring that voice
   and chat share.
2. **Per-RELATIONSHIP state** (a cluster conversation with ANOTHER agent) — lives in TWO complementary pieces, both
   indexed by `(cluster, peer)`, never mixed with ring 1:
   - **The capsule** (`connectors/meshkore/capsule.py`, generic table `sys_kv` under the key
     `capsule:<cluster>:<peer>`): the STRUCTURED state of the relationship — objective (`objective`, ONLY the
     operator sets it, tool `set_cluster_objective`), phase (greeting→probing→work→closing), open loops, stall
     counters (`turns`/`no_progress`), the resource-balance meter (`given`/`received`/`offloads`/`code_out`), the
     negotiated pact (`pact`) and guard flags (`_objective_gate_notified`). `sys_kv` is the GENERIC mechanism for
     scoped state that is not the operator's awareness (the consolidator and the REM phase also reuse it for their
     own markers) — not a new table per scope, but ONE key→JSON table with prefixes.
   - **The dossier** (`connectors/meshkore/mem_ingest.py`): unlike the capsule (numbers/flags), this is PROSE — an
     evolving synthesis of "what you have talked about", distilled by a LOCAL model after each exchange and stored
     as a NORMAL memory pill (`slot="cluster:<cluster>:<peer>"`, exact supersede → a single live row) but
     **QUARANTINED** (`trust="untrusted"`): it never enters the operator's passive `recent_short`/recall, it only
     surfaces on explicit query (`recent_by_source`). Capsule and dossier are merged into a single text block
     (`capsule.compose()`) prepended to EVERY turn of that relationship — it is "what a human would have in mind when
     resuming a conversation with a specific person". It survives a server restart (both live in `zaelar.db`).
3. **Per-TASK state** (a Brain Worker session in progress) — `nucleo/workers/session.py::SessionRecord`, in the
   **RAM registry** `nucleo/dispatch.py::_SESSIONS` (source of truth). It carries `goal`/`kind`/`phase`/`status`,
   the queue of pending injections, and rich observability (`plan`/`done`/`pct`/`steps`). It is DELIBERATELY
   ephemeral — it does not live in `zaelar.db`, it dies with the session or the process — for three reasons: (a) it
   is literally a running process, not a fact to remember; (b) it only matters while it runs (nobody asks "what
   phase was yesterday's finished task in?", only "how is the current one going?"); (c) mixing it with durable
   memory would bloat the database with thousands of rows of transient progress. Two bridges connect it to rings
   1-2 without persisting it whole: **upwards** — `nucleo/loop.py` projects the RAM registry into ring 1
   (`state.sessions`, ~1 Hz) so the FlashBrain KNOWS there are tasks in progress and can send them follow-ups;
   **on completion** — ONLY the final result, if `ok=True`, is written as a normal durable pill via
   `memory_agent.remember()` (with provenance `meta.source="worker:<id>"`) — the process disappears, the FACT it
   produced remains. A special sub-piece (`dispatch._WEB_RESUME`, also RAM) keeps the minimum needed to RESUME an
   incomplete web task (tab id + Claude Code `native_session_id`) — it does not survive a server restart either,
   only the worker itself dying halfway. The **Claude Code CLI** itself keeps, outside our memory, its native
   session history on disk (`--resume`) — a FOURTH, external level that `nucleo/workers/claude_session.py` uses for
   REASONING continuity without our memory having to store it.

**Why three rings and not one flattened one:** each answers a different question and has a different life cycle —
"who are you and what do you have in front of you NOW?" (ring 1, lives as long as the operator exists), "what is my
relationship with THIS agent about?" (ring 2, lives as long as the collaboration with that peer lasts, survives
restarts), "how is THIS specific task going?" (ring 3, lives as long as the process). Flattening them into a single
table would mix the operator's PII with content from an untrusted peer (breaking the quarantine) and fill the global
state with transient noise from finished tasks. The isolation rule is the same as in the rest of the system:
**scope-partitioned, same physical memory, NEVER mixed in the prompt.**

## Technologies and versions

| Piece | Pinned version | Role / note |
|---|---|---|
| **SQLite** | `3.53.3` | Single database (`zaelar.db`); **WAL** to read while writing. **FTS5 included** in the standard amalgamation. |
| **sqlite-vec** (C ext., `asg017`) | `v0.1.9` stable | Vector; **brute force** = 1-5 ms at tens of thousands of memories. (The `0.1.10-alpha` line adds ANN indexes should they ever be needed.) |
| **sqlite-vec** (pip) | `0.1.9` | Loads the extension into Python's `sqlite3` (`sqlite_vec.load(conn)`). `pip install sqlite-vec` (without `--pre`) gives 0.1.9. |
| **FTS5** | included in SQLite | Exact keyword; fused with the vector channel by RRF. |
| **Embeddings (default)** | `text-embedding-3-small` · **768 dims** | OpenAI `/embeddings` protocol, 768 dims requested via `dimensions` (Matryoshka). Runs identically on a laptop and in a container. Chosen by measurement (see that row's `why` in `config/models.default.json`). |
| **Embeddings (local option)** | `embeddinggemma` · **768 dims** | Google, via **Ollama** (≥0.11.10) — **multilingual**, on-device, **Matryoshka** (truncatable to 512/256/128). Selectable in the panel for whoever prefers fully local embeddings. |
| **Embeddings (safety nets)** | `fastembed 0.8.0` · hashing | ONNX-Runtime, no server/GPU (its default model is English-only, so it is a net, not a titular); and deterministic feature hashing, always available, lexical signal only. |
| **RRF** | `k = 60` | Reciprocal Rank Fusion (Cormack et al. 2009; default of Elastic/OpenSearch/Azure/Mongo Atlas). `score = Σ 1/(k+rank)`. |
| **Reranker** | `jina-reranker-v2-base-multilingual` · fastembed 0.8.0 | ONNX/**CPU** cross-encoder (zero GPU) that reorders the RRF top-N by reading query+memory together. **Off by default** (its ~1.1 GB model would dominate a cold start), turned on with `local` from the panel; model-agnostic (`config/v2.py` §`memory`): alt. `openai` (listwise LLM) / `cohere`/`voyage` (slots). LONG recall only, off the hot path, fail-open. |

**Mobile / low-memory alternative (future):** **SQLite-Vector by sqlite.ai** (`sqliteai/sqlite-vector`, Marco
Bambini) — a cross-platform vector-search extension aimed at mobile/embedded (~30 MB RAM by default) with strong
quantisation (Float32/16, BF16, Int8/UInt8, 1-bit, TurboQuant 2/3/4-bit). Distinct from `asg017/sqlite-vec`.
**Decision:** `sqlite-vec` by default (simplicity, one file); re-evaluate `SQLite-Vector` if mobile becomes a priority.

## SQLite schema (`zaelar.db`)

```sql
-- State: single row, ALWAYS in the prompt, no search (µs)
CREATE TABLE state (
  id   INTEGER PRIMARY KEY CHECK (id = 1),
  data JSON NOT NULL          -- names · language · rules of address · location · recent · topics
);

-- Memories (short/mid/long). Each one is a PILL: canonical statement (`text`) + metadata. Core of
-- forgetting-by-weight + reinforcement. `slot`/`meta` = schema v2.
CREATE TABLE memories (
  id            INTEGER PRIMARY KEY,
  level         TEXT NOT NULL,      -- 'short' | 'mid' | 'long'
  kind          TEXT NOT NULL,      -- 'profile' | 'fact' | 'pref' | 'event' | 'msg' | 'summary' | 'insight' | 'conv' | 'result'
  text          TEXT NOT NULL,      -- CANONICAL STATEMENT (distilled by the LLM processor; this is what gets embedded/indexed)
  importance    REAL DEFAULT 0.5,   -- base I0 (by type) — relevance GIVEN the context of the operator's situation
  weight        REAL DEFAULT 0.5,   -- LIVE weight: rises with use, falls with decay
  access_count  INTEGER DEFAULT 0,
  last_access   INTEGER,            -- epoch (for recency and decay)
  ttl_days      REAL,               -- NULL = infinite (immutable facts)
  pinned        INTEGER DEFAULT 0,  -- 1 = NEVER deleted (e.g. a ledger key)
  valid         INTEGER DEFAULT 1,  -- 0 = superseded by another
  superseded_by INTEGER,
  slot          TEXT,               -- v2: canonical key of the SINGULAR fact (operator.name, goal.current…) → EXACT supersede/dedup without an LLM
  meta          TEXT,               -- v2: free JSON pill (entity/attribute/source/said_at/path/raw…) — off the hot path; feeds the viewer/graph
  created       INTEGER NOT NULL,
  updated       INTEGER NOT NULL,
  valid_at      INTEGER,            -- v5: when the fact became TRUE (default = created)
  invalidated_at INTEGER            -- v5: NULL while valid=1; set ONCE, never touched again
);
-- `slot` gives a DETERMINISTIC "the newest WINS": when a fact with a slot is inserted, the writer invalidates the
-- current one with the same slot (or REINFORCES it if the normalised text is identical → zero duplicates).
-- Migrations are idempotent, non-destructive ALTERs in `memory/db.py`.
-- BI-TEMPORAL (v5): `updated` cannot serve as "when it was invalidated" — reinforcement (`writer.reinforce`) and the
-- consolidator's level promotion also touch it, so an invalid row does not guarantee that `updated` is the moment of
-- its invalidation. `valid_at`/`invalidated_at` are (set at every write/invalidation/restore site, never reused for
-- anything else), and they enable `memory/api.py::as_of(slot, ts)` — "what did we believe was true on date X?" —
-- without retroactivity inference (a correction said TODAY is dated TODAY, not in the past it describes).
-- Writer hardening (`memory/writer.py`):
--   (1) `canon_slot()` — alias NORMALISATION: the LLM may emit slots in its own words ('location', 'ubicación'…)
--       while the heuristic uses the canonical ones ('operator.location'); without normalisation that yields TWO
--       lineages of the same fact that never supersede each other. The writer is the single choke point → every
--       alias collapses to the canonical key there, for ALL writers.
--   (2) supersede invalidates ALL current rows of the slot (not LIMIT 1): if 2+ current rows coexist by any route
--       (old aliases, unforget, legacy), the next write collapses them — SELF-HEALING.
--   (3) the slot VOCABULARY lives in the SINGLE REGISTRY `memory/slots.py` (SlotSpec: key + aliases + state field +
--       identity flag). The writer (canon_slot), memory_agent (_IDENTITY_SLOTS/_PATCH_TO_SLOT, derived) and the
--       processor prompt (GENERATED catalogue) all consume it → the three layers cannot diverge. Namespaced slots
--       (cluster:*, navegador.session.*, <widget>:<key>) pass through lowercased/stripped without registration.
--   (4) the SELECT of current rows breaks ties by id (`updated` has one-second resolution).
--   (5) the consolidator's `heal_slots()` normalises LEGACY slots (aliases/uppercase from before normalisation) and
--       collapses multiple current rows of the existing stock on every sleep cycle (the counterpart of the
--       writer's self-healing).
--   (6) the supersede SELECT EXPANDS by ALIAS (`slots.equivalent_keys`): `operator.location` also collapses a raw
--       `location`/`ubicacion` left un-normalised → the collapse by slot is IMMEDIATE, it does not wait for sleep.

-- Vector (sqlite-vec). Brute force at our scale = ms.
CREATE VIRTUAL TABLE vec_memories USING vec0(
  memory_id INTEGER PRIMARY KEY,
  embedding FLOAT[768]              -- 768 dims (the active provider is asked for 768 via Matryoshka)
);

-- Exact keyword (FTS5, included in SQLite).
CREATE VIRTUAL TABLE fts_memories USING fts5(text, content='memories', content_rowid='id');

-- Graph as edges in the SAME file (no Neo4j).
CREATE TABLE edges (
  from_id INTEGER NOT NULL,
  to_id   INTEGER NOT NULL,
  type    TEXT NOT NULL,           -- 'about' | 'same_person' | 'caused' | 'refines' ...
  weight  REAL DEFAULT 1.0,
  PRIMARY KEY (from_id, to_id, type)
);

-- Lazy episodic: files/PDFs. Only the SUMMARY (a row in memories) is searchable.
CREATE TABLE episodic (
  id        INTEGER PRIMARY KEY,
  path      TEXT NOT NULL,         -- local path to the file
  summary   TEXT NOT NULL,
  memory_id INTEGER,               -- summary indexed in vec/fts via memories
  bytes INTEGER, mime TEXT, created INTEGER
);

-- Task continuity.
CREATE TABLE journal (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL,
  status TEXT NOT NULL,            -- 'pending' | 'in_progress' | 'done'
  detail TEXT, created INTEGER, updated INTEGER
);
```

## Hybrid retriever (hot path · ms)

**State** is always injected (no search). For everything else: vector (sqlite-vec) **∥** keyword (FTS5) in
parallel, **RRF** fusion, and ordering by weighted score.

**Lanes (2026-10-26, CRIT-M9).** Inbound messages (`kind='msg'`: WhatsApp, Telegram, email) are their OWN lane:
`query(lane="own")` (the default) never returns them, `lane="messages"` returns only them, `lane="all"` returns the
own rows first and the messages after, each with its own budget. The filter runs inside every channel before the
top-K cut. A `msg` row is never promoted and never enters `recent_short` / `salient_long`: an inbox of hundreds of
rows used to push his own conversation out of the turn and outrank his facts in recall. Recall results carry their
provenance (`memory.provenance`: id, date, level, kind, slot, source, lane), and his past conversation has one
reader, `memory.conversation(hours, query)` over the `conv` turns, exposed as `mem_cli history` and as
`source=conversation` on `/api/memory/recall`.

```
score = α·semantic_relevance + β·recency + γ·importance + δ·usage_weight
defaults:  α = 0.45   β = 0.25   γ = 0.20   δ = 0.10     (tunable per profile)
RRF:       rrf(doc) = Σ_lists 1 / (k + rank_list(doc))     with k = 60
```

```python
def query(prompt, budget_tokens):
    ctx = [ state.read() ]                      # ALWAYS, no search (µs)
    q   = embed(prompt)
    vec = vec_search(q, k=100)                  # sqlite-vec, brute force, ms (POOL_K = 100)
    kw  = fts_search(prompt, k=100)             # FTS5
    para = vec_search_paraphrases(q, k=100)     # paraphrases indexed at write time (vocabulary gap)
    cand = rrf(vec, kw, para, k=60)              # fuses THE THREE lists
    for m in cand:
        m.score = A*m.rel + B*recency(m.last_access) + G*m.importance + D*m.weight
    top = sort_desc(cand, key=score)
    top = rerank(prompt, top)                    # RE-RANKING: a cross-encoder reorders the top-N, fail-open
    top = graph_expand(top, edges)              # 1-hop (direct neighbours) + multi-hop PPR (an additional, bounded
                                                 # channel — up to MAX_HOPS/MAX_NODES, fully fail-open)
    emit("memory.reinforce", ids(top))          # async reinforcement (non-blocking)
    return pack(ctx + top, budget_tokens)       # truncates to the budget
```

### Re-ranking of LONG recall — model-agnostic, optional

At SCALE (hundreds of memories) a bi-encoder embedding (independent vectors) orders "blurrily": the right answer
is usually in the top-10 but NOT in the top-1/3. A **reranker** (cross-encoder) re-scores each candidate **reading
query+memory TOGETHER** → it lifts the right one. It is the biggest recall lever for the smallest cost, with a clear
gain at recall@1 and MRR; the evaluation harness is `tests/memory/e2e/bot/scale_eval.py` and the numbers are in
`zaelar-model-benchmarks.md`.

**Architecture** (`memory/rerank.py` + `memory/rerank_local.py`, config `config/v2.py` section `memory`): the same
LLM-agnostic pattern as the brain routing (`fast`/`code_agent`) — **provider CONFIGURABLE from the UI/config**.
Providers: `local` (fastembed `TextCrossEncoder` `jina-reranker-v2-base-multilingual`, **ONNX/CPU → no contention
with the GPU** that STT+TTS may already load) · `openai` (listwise LLM, or any OpenAI-compatible endpoint — quality
ceiling, data leaves the machine) · `cohere`/`voyage` (slots for dedicated rerank APIs) · `off` (the shipped
default, so that every deployment measures the same system; without it recall still works, just ordered less well).

**Invariants** (they respect the golden latency rule): ONLY on the LONG path, **off the hot path** (long recall is
already on demand + `asyncio.to_thread`) — **STATE/SHORT are untouched** (still direct µs reads without a model).
**Hard FAIL-OPEN**: error/timeout/missing model → the retriever's order is returned intact (it never breaks or
blocks). The reranker is **not generative** (it reorders already-retrieved candidates, it invents nothing → no
hallucination risk). It is blended with recency/importance (`rerank_blend` 0.85) so as not to sink a freshly said
fact. When enabled, the model is **warmed at boot** (`nucleo/flash/prewarm._warm_rerank`) → the first query with
recall does not pay the cold load. Observability: `status()` (provider/model/latency).

> **Raising the recall ceiling — the levers.** The reranker fixes most of the ORDERING gap; the real ceiling is
> `found@10` — what the retriever does not bring at all. The levers, ranked by evidence (see
> `zaelar-model-benchmarks.md §6/§7/§8` and `tests/memory/e2e/bot/RESEARCH.md`):
> - **A STRONGER embedding is NOT the lever**: a SOTA multilingual 1024-d model (`bge-m3`) performs on par with
>   the 768-d one on found@10. The axis is NOT the bi-encoder's quality. *(The provider-driven dimension
>   abstraction + `memory/reembed.py` stay, so the model can be changed.)*
> - **WRITE-completeness** — most "not retrieved" facts turn out to be **not stored** (the HEART discarded them or
>   they were superseded), not retrieval failures. Hardening what counts as durable is lever #1.
> - **Retrieval of what is stored — built**: a deeper pool (`POOL_K = 100`, `memory/retriever.py`) + a
>   **PARAPHRASE index at write time** (`memory/writer.py::index_paraphrases`, also a REM phase
>   `rem.py::index_paraphrases` — 1-2 rephrasings per durable pill generated off the hot path, extra surface for
>   the vocabulary gap with no LLM at read time) + the concept graph.
> - **Extension point: a continuously SELF-EVALUATING memory** — a sleep-time loop that probes itself, detects
>   unrecoverable facts and **REPAIRS** them (reinforce, add edges, index paraphrases, mark for re-embed).
> - **Extension point: SEMANTIC consolidation** — the `summarize_fn` hook (a no-op by default) can merge
>   near-duplicate pills by embedding to decongest the vector space; **temporal edges** (as in Graphiti) fit the
>   same `edges` table.
> - **EXTERNAL reranker/embedding** = opt-in by config: `rerank_provider=openai`/`cohere`/`voyage`.
>
> **Method caveat:** the test bot SEEDS with `hash` embeddings (lexical, deterministic and fast,
> `tests/memory/e2e/bot/runner.py`); measuring SEMANTIC recall requires **re-embedding** the corpus with the real
> model on BOTH sides — `tests/memory/e2e/bot/embed_bench.py` does that. Never compare a semantic query against
> hash vectors (space mismatch). In production the configured embedding provider is always used.

**CONCEPT graph** (organises the memory conceptually): at WRITE time the HEART tags each durable pill with 1-3
light `concepts` (health/finance/sport/family…); the writer creates/reuses a **concept NODE** (a `kind='concept'`
row, with its own FTS+vector row → retrievable) and links **pill↔concept** in `edges` (bidirectional, cap 3
concepts/pill). At READ time a CATEGORY query ("how is my health?") matches the node through FTS and
**`graph_expand`** surfaces its cluster (allergy+surgery+habits) — **WITHOUT an LLM**, direct traversal. A concept
node's neighbours are barely discounted (`concept_discount`, and concepts are processed first) because they ARE
the answer to the category. It closes the vocabulary gap (the fact surfaces through the `about→health` edge, not
through a flat embedding). Emergent and BOUNDED. Populated at write time (off the hot path), read by direct
traversal → it fits the golden rule.

> **Decision note (substrate vs. external library):** the substrate is SQLite + sqlite-vec + FTS5 + RRF + `edges` —
> the SAME (production) primitives that Zep/Graphiti/Mem0 use underneath; the "graph" is ~60 lines on top of the
> `edges` table, NOT a new engine. The "batteries-included" alternatives (Zep/Graphiti→Neo4j, Mem0-graph→Neo4j,
> Letta) break zaelar's HARD constraints: in-process storage, a core WITHOUT Docker, one process/file, and **zero LLM
> on the read path** (the voice golden latency rule — almost all of them put an LLM in search). We borrow IDEAS
> from the state of the art (Graphiti's temporal edges, A-MEM's emergent linking), not its infrastructure.
>
> The same reasoning applies to SaaS memory plugins for coding agents (project/session/global scopes per git root,
> automatic capture, "dream consolidation"): a generic cloud wrapper for a different use case (a coding agent's
> project memory, not an operator's personal memory). **Extension point** worth noting from that family:
> consolidation gated by **three conditions** (time OR number of sessions OR volume); zaelar's REM phase gates on
> time (`rem_every_hours`), and session/volume gates could be added next to it if write volume ever outgrows the
> daily cadence.

**Robust RECALL gate** (`prompt.needs_recall`): decides whether the turn triggers `compose_recall` (the retriever,
off-loop). It is not a whitelist of phrases: it fires on ANY substantive question (`¿?`/WH + ≥2 words) or recall
imperative ("tell me about…", "remind me…"), and NEVER on a greeting/acknowledgement/small talk (`_TRIVIAL_RE`). It
is biased towards REMEMBERING: a false positive = an off-loop query the LLM ignores; a false negative = an amnesic
brain. Plus a deterministic backstop maps keywords→concept (`memory_agent._derive_concepts`) when the LLM heart does
not tag, guaranteeing graph coverage by category.

**Retrieval refinements** (validated with the memory test bot, `tests/memory/e2e/bot/`):

- **FTS with prefix STEMMING** (`retriever._fts_query`): Spanish is highly inflected and the HEART canonicalises
  person/tense at write time ("estoy aprendiendo" → "aprende japonés"; "me operaron" → "se operó") → the exact
  query token would not match the stored one. Content tokens (≥5 chars) are truncated to 6 chars + `*` →
  `aprend*` matches aprende/aprendiendo/aprender. It only widens the FTS channel; RRF fusion + the vector channel
  keep precision.
- **META-VERB stopwords** in FTS (`recuerdas`/`acuerdas`/`dime`/`sabes`…): they are meta ("¿te acuerdas de…?"), NOT
  the data sought. Unfiltered, `recuerdas`→`recuer*` would match EVERY "recuérdame…" in the store and bury the real
  answer.
- **The FlashBrain's recall spends its budget on DURABLE memory** (`prompt.compose_recall`): it asks for a DEEP
  POOL (`limit=40`) and filters to `mid/long`. Recency (SHORT/conv buffer, ephemeral messages) ALREADY goes whole
  into the prompt (`memory_cache`); including it in recall would double-count, and recent chatter would BURY the
  durable task/fact being asked about.
- **The CONVERSATIONAL BUFFER (`kind='conv'`) is NOT embedded** (`memory/writer.py`): the raw turn↔reply pair
  (ephemeral, TTL 2d, `level='short'`) is written EVERY turn; it is read ONLY by recency (`recent_short`, direct
  SQL) and durable recall excludes it → embedding it would be a per-turn cost with no reader, and would put chatter
  noise at the top of the retriever. The HEART already distils what is memorable into separate pills (those ARE
  embedded). `consolidator.promote` **excludes `kind='conv'`** so a conv row never ends up durable without a
  vector. And the cheap pre-LLM discard (`memory_agent._TRIVIA_SKIP_RE`) covers fillers/acknowledgements
  ("ah/eh/mmm/ya está/bueno/venga…") → fewer processor runs on trivial turns. Rule: SHORT is for RECENCY, not for
  the index — it spends no vector.
- **Deterministic `recent_short`** (`ORDER BY updated DESC, id DESC`): `updated` has one-second resolution → writes
  in the same second would tie, so the tie is broken by `id` (insertion order) to keep "the newest WINS" stable.
- **Hard cases the design addresses explicitly:** recall across a pure vocabulary gap ("instrument" → "guitar",
  with no lexical overlap) is served by the concept graph and the paraphrase index; CHRONOLOGICAL ordering
  questions ("which came first, X or Y?") need both dated events co-retrieved, which the bi-temporal columns and
  `as_of` support.

## Forgetting by weight + reinforcement (the "neural" core)

Grounded in published research (access-frequency reinforcement, the Ebbinghaus curve, FadeMem).

- **Reinforcement by use**: every time a memory enters a prompt →
  `access_count++ · last_access = now · weight = min(1, weight + step)` (access **resets** the decay).
- **Time decay** (during consolidation): `I(t) = I₀·e^(−λ·Δt)`; **λ ≈ 0.001/day** (half-life ≈ **693 days** =
  ln2/λ), tunable per memory type. **PER WINDOW**: Δt is measured from the LAST decay cycle (marker
  `sys_kv.decay_last_run`), not from `last_access` on every pass — otherwise each hourly consolidation would
  re-apply the ACCUMULATED decay and an idle pill would lose weight many times faster than its real half-life.
- **TTL by category**: immutable facts (name, restrictions) → `ttl = NULL` (∞); transient context → short TTL;
  preferences → intermediate.
- **Pinned**: `pinned = 1` → never deleted even if never accessed (e.g. a Bitcoin ledger key).
- **Deletion by weight**: **ONLY** when the storage limit is exceeded; the lowest-weight non-pinned memories are
  deleted until back under the limit. While there is room, nothing is deleted.

## Consolidator ("sleep") — periodic job, no rush

Runs at intervals (daily / hourly / by size and memory type). Triggered by the **orchestrator loop**.

```python
def consolidate():                              # daily / hourly / by size
    # 1. compress: surviving short → 'mid' summary; old mid → 'long'
    for c in clusters(short_older_than(T)): upsert(summarize(c), level='mid')
    # 2. deduplicate (interference): merges very similar memories
    for a, b in near_duplicates(sim > τ): merge(a, b)
    # 3. temporal conflicts: the new fact supersedes the old one
    for old, new in conflicts(): old.valid = 0; old.superseded_by = new.id
    # 4. decay: weight/importance of the NOT accessed *= e^(−λ·Δt)
    for m in memories: m.weight = decay(m)
    # 5. deletion by weight ONLY if the limit is exceeded (never the pinned ones)
    while store_size() > LIMIT:
        delete(lowest_weight(where pinned = 0))
```

**Index pruning `prune_invalid`:** invalidated pills (`valid=0`, superseded) keep their ROW (history intact) but,
after a margin, leave the **vec/FTS** indexes — an invalidated shell should not keep competing in the retriever or
occupying vector space. It runs inside light sleep (`memory/consolidator.py::prune_invalid`).

### DEEP sleep — the REM phase (`memory/rem.py`)

The classic consolidator is **LIGHT** sleep (cheap mechanics every hour: promote/exact dedup/decay/prune/evict). The
**REM phase** is the **DEEP** cycle (daily by default), triggered by `nucleo/loop.py` after light sleep, in which
the memory is **ORDERED, RELATED and SYNTHESISED** — all off the hot path and with every phase ISOLATED (one
failure does not bring sleep down):

1. **`repair_embeddings()`** — re-embeds pills WITHOUT a vector or marked `meta.embed_pending` (the writer's
   signature enforcement leaves them like that when the model is mismatched/degraded) → the semantic index
   **self-repairs** every night. Configurable budget (**`§memory.rem_repair_limit` / `ZAELAR_REM_REPAIR_LIMIT`,
   default 1,000 per sleep**, large enough to drain a backlog of several hundred in one night; no LLM involved).
2. **`semantic_dedup()`** — dedup by MEANING (cosine over the already computed vectors, **no LLM**; the threshold is
   **per embedding model** — `memory/dedup_thresholds.py`, 0.86 CALIBRATED against a real database for
   `embeddinggemma`, and NO row yet for the cloud titular, so on it this pass is **skipped** and says so — + a
   **conflicting-figures guard**: two facts with different numbers/dates are never merged): paraphrase echoes of
   the same task ("ITV appointment on the 23rd" × 8) collapse into 1 — it
   transfers edges and invalidates the rest with `valid=0 + superseded_by` (history intact). **Complemented by a
   SYNCHRONOUS exact dedup at write time** (`writer.insert_memory`, `LOWER(text)=LOWER(?)` over the current rows
   without a slot) — the consolidator's exact dedup only runs hourly, a window wide enough for the same literal
   fact, said two turns in a row, to be stored twice.
3. **`synthesize(hook)`** — the only phase with an LLM, **INJECTED by the caller** (the memory does NOT import
   brains; the loop wires `nucleo/memllm.synthesize_concept_groups`, same pattern as `summarize_fn`): it groups
   durable pills by **CONCEPT** (the `edges` graph) and distils **1 high-level INSIGHT per group**
   (`kind='insight'`, **`slot=insight:<concept>`** → REWRITTEN on every sleep, not accumulated). It turns 30 loose
   facts into "what zaelar KNOWS about you" (the reflection of Generative Agents / sleep-time compute). Fail-open
   hook (`[]` = no insights, sleep continues). **It displaces, not only adds:** after writing the insight it calls
   `writer.demote_summarized(ids, insight_id)` on the raw pills that fed it — it multiplies their `weight` (factor
   0.6, floor 0.05, never touches `pinned`) and stamps `meta.summarized_by`, **without invalidating or deleting
   anything** (history is kept intact). That way the insight does not sit ON TOP of raw pills that keep competing
   at full weight forever. **Precisely because it displaces, no insight is written and nothing is demoted without
   passing a fidelity gate:**
   1. **`verify_fn`** (`nucleo/memllm.verify_insight_grounded`, wired by the loop next to
      `synthesize_concept_groups`) is the **ARBITER when available**: a FRESH call, independent of the one that
      generated the insight, asking whether every claim is backed by the data — fail-**CLOSED** (no clear answer =
      not trustworthy), the opposite of the other memory tasks, because losing a legitimate insight is cheaper than
      letting an invented one through to displace correct facts.
   2. **`_grounded()`** (deterministic backstop, no LLM: figures/proper names must anchor in the data) decides only
      when **NO `verify_fn` is available** — a free safety net for the no-LLM case, not a prior veto. A literal
      substring check cannot see that "las nueve" (source) and "las 9" (insight) are the same, while a model can;
      the semantic judgement belongs to a MODEL, not to a hard-coded pattern, so the pattern never vetoes ahead of
      the model.

   Any rejection is VISIBLE (`logger.warning` + `health_state.record`, never silent) and does not cost the concept —
   it is retried on the next sleep. There is also a length cap (`MAX_INSIGHT_CHARS=400`) so an insight cannot grow
   sleep after sleep.
4. **`hygiene()`** — the daily check: **% of heuristic writes in 24h → ALERT if >50%** (a HEART that is down must
   SHOW, never fail quietly), remaining `embed_pending`, sizes. The report goes back to the caller (the loop decides
   whether to alert) and is emitted on the bus (`memory.rem`).

Cadence: persistent marker **`sys_kv.rem_last_run`** + `config §memory.rem_every_hours` (default 24h, min 1h; env
`ZAELAR_REM_SECS` wins if set). **Kill switch `ZAELAR_REM=0`**. Synthesis model by config
(`§memory.rem_model/rem_base_url/rem_api_key`; defaults in `config/models.default.json` §memory_rem — see §Memory
models), resolved by the **internal router `nucleo/memllm.py`** (models PER TASK of the memory module, key PER
ENDPOINT — a key sent to the wrong endpoint must be impossible by construction).

> **Robustness rules of the synthesis call.** `_REM_SYSTEM` ends with the output-contract example
> (`[{"concept": str, "insight": str|null}]`), whose literal braces `str.format` would read as placeholders and
> turn into a `KeyError` on every call — so the prompt is filled with `.replace`, never `.format`, and
> `tests/memory/unit/test_rem_prompt.py` **explicitly forbids** going back to `.format` on it. A synthesis failure is
> logged at ERROR + `health_state.record("memory")` → it shows in the ◉ health indicator: **a memory failure must
> never end as a mere `logger.warning`**, because a fail-open path that is silent looks like "the memory does not
> consolidate", never like an error. The call budget is generous on purpose — `max_tokens` **4000** (a model that
> reasons can exhaust a small budget before closing the JSON and return a truncated array) and `timeout` **240s**
> (REM runs at night: there is no hurry that justifies losing the consolidation).

---

## Memory models — WHAT we use, WHY, and where the evidence is

> **This section is the canonical answer to "why these models?"**, written so that no benchmark has to be repeated
> to answer it. The dense detail lives in `zaelar-model-benchmarks.md §12.3` (distilling) and **§12.4**
> (consolidating); the harnesses are versioned and reproducible (see below), and each run writes its raw report
> under `tests/memory/e2e/bot/resultados/` (local output, not tracked). The effective defaults are declared, with
> their rationale, in **`config/models.default.json`** (`memory_writer`, `memory_rem`, `embeddings`, `reranker`).

> ⛔ **Embeddings have NO failover, by design.** The HEART and REM can fall through to a stand-in — they are chat
> models, and the next rung answers the same question. An **embedding model DEFINES the vector space** every pill
> in `zaelar.db` already lives in: a different stand-in does not answer more cheaply, it answers in coordinates
> that cannot be compared with anything stored. Moving it means **re-embedding the whole memory**
> (`memory/reembed.py`), never a config edit; the space signature lives in `<db>.embedsig`. The only honest
> stand-in would be the SAME model behind another door. So when the provider is unavailable the failure is made
> **VISIBLE** — amber in the memory box, saying that new memories are stored WITHOUT a vector (marked
> `embed_pending`, repaired by REM) and that search by meaning drops to lexical (FTS5 + the paraphrase channel,
> which is lexical in that window too) — instead of hiding it behind a substitute that would poison recall
> silently. `test_the_embeddings_row_still_declares_NO_stand_in` (node 2.77) turns red the day someone "fixes"
> the table, and `test_an_embedding_outage_defers_and_rem_repairs.py` (node 1.2) walks the whole path: pill
> written, marker set, FTS carries the read, REM repairs when the titular is back, signature never moved.

> 🔁 **Changing the embedding model is a MIGRATION, through one door (V2-824).** `memory/reembed.py::migrate()`
> is fired when `memory.embed_provider` / `embed_model` / `embed_base_url` change — from the panel
> (`POST /api/config/v2`, in the background) or from a profile (`config/profiles.apply`, `local` ↔ `cloud`). It
> re-embeds every pill AND every paraphrase (`vec_paraphrases` was left in the old space before), reseals
> `<db>.embedsig`, clears the stale `embed_pending` markers and counts the foreign vectors left (must be 0). A
> degraded provider ABORTS without resealing. Nothing migrates on its own: a boot that finds the signatures
> apart WARNS (`check()`) and the writer keeps deferring — an existing install keeps its sealed space until the
> user changes the model on purpose. By hand: `python -m memory.reembed` (`--force` to re-embed regardless).

> 📏 **The dedup thresholds belong to ONE model (V2-824).** The writer's insert-time distance and REM's cosine
> are geometry in one model's space, declared per model in `memory/dedup_thresholds.py` (`embeddinggemma`: 0.45 /
> 0.86, measured). A model with no row — the cloud titular, on purpose — gets **no semantic dedup**: the writer
> keeps exact-text and slot dedup (deterministic, no false positives) and REM skips the pass. The number for a
> new model comes ONLY from `python -m tests.memory.benchmarks.calibrate_dedup --db <copy of a real zaelar.db>`, which measures
> echoes of one fact (pill vs its stored paraphrase) vs same-entity different facts (two pills about one concept)
> vs negations, and prints a suggestion; a human writes the row.

**The memory uses an LLM in TWO places, both for WRITING and both off the hot path. READING never uses an LLM**
(retriever sqlite-vec + FTS5 + RRF + CPU reranker) — that is the invariant that makes the latency of these models
cost the voice turn nothing.

| task | what it does | default (`config/models.default.json`) | cadence | evidence |
|---|---|---|---|---|
| **HEART** (`nucleo/mem_processor.py`) | distils every turn into pills + metadata | **DeepSeek Flash DIRECT** (`api.deepseek.com`), stand-in OpenAI `gpt-4.1-mini` | **every turn** | §12.3 |
| **REM sleep** (`nucleo/memllm.py`) | groups durable pills by concept → 1 insight | **DeepSeek Flash DIRECT**, stand-in OpenAI `gpt-4.1-mini` | **once a day** | §12.4 |
| **Embeddings** (`memory/embeddings.py`) | text → vector for semantic search | OpenAI `text-embedding-3-small` at 768 dims, **no stand-in** (see above) | every durable write + every recall | `models.default.json` §embeddings |

The same defaults serve every deployment, self-hosted or not; any of them can be changed from the UI.

**A third task lives in the same router but is NOT memory** — worth not confusing them:

| task | what it does | default | cadence | evidence |
|---|---|---|---|---|
| **i18n init** (`i18n/init/generate.py`) | translates the UI strings into a new language | **`deepseek-v4-pro`** DIRECT, stand-in `gpt-4.1-mini` | **once per LANGUAGE** (init + upgrade) | §12.5 |

It is in `memllm` because it shares the off-hot-path seam (`chat_sync` + key per endpoint), not because it writes
to the memory. **Its criterion is RELIABILITY, not price or marginal quality**: it is paid once per language, and a
lost batch would leave a block of UI strings in English. The candidates that reason at length or truncate their
answer on long non-Latin batches are ruled out for that reason (§12.5).

### Provider routing rules

The model table follows a few rules (stated at the top of `config/models.default.json`):

- **A titular, ONE stand-in, and AT MOST a third rung.** Never more than three levels anywhere — a fourth cannot be
  reasoned about, configured or debugged.
- **The chat memory services (HEART, REM) run on a direct provider as titular**, with OpenAI `gpt-4.1-mini` as the
  stand-in one rung below — so a titular that returns an empty `200` (a reasoning model eating `max_tokens`) falls
  THROUGH to the stand-in instead of killing the cycle.
- **A broker (AIMLAPI) is failover only** — second or third rung at most, never the titular of any service.
- **Everything must be able to run in a container.** Ollama is a local server and does not exist there, which is
  why the default embeddings go through a cloud provider; Ollama remains a panel option for self-hosters.
- **The credential is resolved PER ENDPOINT** (`nucleo/provider_keys.py`): the key follows the URL, never the
  other way round, so changing a model never requires touching keys.

To see the endpoints the memory tasks resolve to right now (defaults plus whatever the UI changed):

```bash
cd engine && ./.venv/bin/python - <<'PY'
from nucleo import memllm
from nucleo.susurro import client as sus
from config import v2
m = v2.get("memory") or {}
print("HEART", m.get("mem_processor_base_url"))
for t in ("rem", "i18n"):
    print(t, memllm.resolve(t)[0])
print("susurro", (sus.cfg() or {}).get("base_url"))
PY
```

### Why the criterion is DIFFERENT for each one (not opinion — it follows from the shape of the code)

- **HEART → PRICE decides.** It runs on every turn, so its cost is linear with use. The DeepSeek Flash model was
  chosen because it TIES with `gpt-4.1-mini` on the two axes that destroy data — capturing the fact and not
  polluting with discards — at roughly half the cost per thousand distilled turns; not because it is "better".
- **REM → QUALITY decides.** `rem.py` sends ALL groups in **ONE call**, capped at `MAX_GROUPS=8` × `pills[:12]`,
  **once a day**: the input is BOUNDED by design and **the cost does NOT scale with the size of the memory**.
  Optimising price there would be optimising noise; a bad insight, on the other hand, is written as a DURABLE pill
  (`slot=insight:<concept>`) that the retriever can return as if it were a fact about the operator.

### The vetoes — why we use neither the cheapest nor the most powerful

- ⛔ **`gpt-4o-mini`** (cheaper than the titular) is **VETOED for the HEART**: given an allergy stated in
  **English**, it assigns `slot=operator.diet`, consistently. A `slot` **invalidates every earlier pill with that
  slot**, so a later "I'm vegetarian now" would erase the shellfish allergy. It is the very error the prompt warns
  about in writing; in a personal memory it is silent data loss, not a percentage point. (The SAME sentence in
  Spanish is handled correctly: what breaks is the language crossing.)
- ⛔ **REASONING models fit NEITHER task.** Distilling, small reasoners capture well but turn questions and orders
  into memories — a reasoner "finds meaning" in a turn that should have been dropped. Consolidating, several
  reasoners return nothing usable at all.
- ⚠️ **"More powerful" is NOT better here, and that is measured.** In REM, the larger and reasoning variants
  (`deepseek-v4-pro`, `deepseek-reasoner`, `gpt-4.1`, thinking modes) do not beat the flash model and cost several
  times more. Synthesis is mechanical (group, abstract, keep keys); reasoning adds verbosity and instability, not
  judgement.
- ⚠️ **Keeping quiet is part of the REM task.** Given a group of trivia ("had a coffee", "forgot where the keys
  were") a good synthesiser returns `null`; one that ALWAYS fabricates an insight ("experiences small lapses…")
  would consolidate it as a durable trait of the operator. §12.4 found `gpt-4.1-mini` weak on this `null`
  discipline — it is the REM stand-in, so if REM starts inventing patterns while running on the stand-in, that is
  the first seat to check.

### Alternatives measured as viable

Usable as a third rung by config (`§memory.mem_processor_*` / `§memory.rem_*`) or from the UI:

- **HEART:** `google/gemini-2.5-flash`; `x-ai/grok-4-fast-non-reasoning` (conservative, perfect metadata).
- **REM:** `x-ai/grok-4-fast-non-reasoning` (the cheapest and fastest; may drop a proper name when synthesising);
  `zhipu/glm-4.7` (top quality, but markedly slower and more expensive).

### The rule

The benchmark decides which model to CHOOSE within the routing rules above, and its findings expire: when a model
or a prompt changes, re-measure rather than reasoning from reputation. The `gpt-4o-mini` veto (it eats the allergy
through a slot) is not to be lifted without a new measurement that shows the cross-language slot error gone.

### How to REPRODUCE the benchmarks (both harnesses are versioned and deterministic in their corpus)

```bash
# HEART — fixed corpus × 4 axes (write-completeness · precision · layer/slot · $/1k turns)
PYTHONPATH=. ./.venv/bin/python tests/memory/e2e/bot/distiller_bench.py --preflight        # do the ids answer?
PYTHONPATH=. ./.venv/bin/python tests/memory/e2e/bot/distiller_bench.py --runs 3 --models deepseek-v4-flash,gpt-4.1-mini@aimlapi

# REM SLEEP — fixed groups × 6 axes (validity · keys · shape · null · no-invention · $/year)
PYTHONPATH=. ./.venv/bin/python tests/memory/e2e/bot/rem_synth_bench.py --runs 3 --models deepseek-v4-flash,grok-4-fast-nonreason
```

Both write `resultados/<date>-<bench>[-tag]/report.{md,json}` with per-case detail and the **concrete failures** of
each model. Rates live OUTSIDE the code in `tests/memory/e2e/bot/prices.json`, so they can be re-verified on the
web without touching the harness (LLM prices change without notice).

⚠️ **Method rule: measure through an endpoint with enough rate headroom.** A rate-limited account answering HTTP
429 under a handful of concurrent calls sinks a model's score for a reason that is not the model (and inflates its
latency). A rate limit disguises itself as poor quality.

### Usage: both tasks REPORT consumption

The HEART (`mem_processor`) and the memory router (`memllm`, which serves REM and i18n) capture the `usage` block
of the response and report it to `nucleo/energy_meter` when metering is enabled (fire-and-forget, fail-open). The
rate of the titular model and of its stand-ins are all declared, so a failover is metered at its own rate rather
than a generic one.

## Internal memory API

It fits the system's **hybrid** transport: `write`/`reinforce`/`link` = **async** (queue/events);
`query`/`state`/`load_episode` = **direct call** (hot path). A single writer (the queue) avoids SQLite write
collisions; readers use WAL without blocking.

| Operation | Path | Who uses it |
|---|---|---|
| `memory.write(item)` | async (queue) · slow is OK | FlashBrain · memory agent · widgets |
| `memory.query(prompt, budget) → ctx` | **direct · ms** (read), but the FlashBrain calls it **off the event loop** (`asyncio.to_thread`) and **on demand** | SlowBrain dispatcher · FlashBrain (recall) |
| `memory.state() → dict` | direct · µs (fixed table) | the composer (always) |
| `memory.recent_short(limit, max_chars) → list` | direct · µs (direct read, NO embeddings) | the composer: SHORT term **whole** into the prompt |
| `memory.recent_window(limit, max_chars) → [{role,content}]` | direct · µs (direct read, NO embeddings) | seeds `brain._window` at startup + the second short-term pass (short-term circuit) |
| `memory.reinforce(ids)` | async (event) | fired by the retriever when memories are used |
| `memory.pin(id)` / `unpin(id)` | async | operator (by voice) · memory agent |
| `memory.load_episode(id) → bytes/text` | direct (lazy) | agents when told to "look at the file" |
| `memory.link(from, to, type, w)` | async | memory agent · consolidator |
| `memory.consolidate()` | periodic job | the orchestrator loop (sleep) |

Signal it emits: `memory.updated` (so the UI and others can refresh).

## How the rest of the system USES it (guide for module authors)

Mental rule: **to STORE, let the heart decide; to READ, pick the speed by what you need.** Do not invent new paths
or touch the database directly.

**WRITING (all async, through the `memory/api.py` facade — never the database directly):**

- **Is it something the operator said/wrote in a turn?** → do NOT call `memory.write` by hand. Pass it through the
  HEART: `await nucleo.memory_agent.ingest_utterance(text)` (the FlashBrain already does this on every directed
  turn). The LLM processor decides whether it is stored, where and how. That way the memory LEARNS instead of
  accumulating raw text.
- **Are you the SlowBrain / an agent wanting to remember a result or a specific fact?** → `await
  nucleo.memory_agent.remember({"text": …, "kind": "result"|"fact"|…})`. It is the SlowBrain's ONLY sanctioned
  writer; it auto-classifies if you do not set `level`. You can set `slot` (singular fact → exact supersede) and
  `meta`.
- **Are you a Brain Worker (a headless process OUTSIDE the server)?** → talk HTTP to the live server:
  `python -m nucleo.mem_cli recall "<query>"` (read) and `… remember "<fact>" [--slot x]` (write via
  `remember_external`: per-task token + precision gates, no access to `state` or identity slots). It preserves the
  SINGLE WRITER — never open `zaelar.db` from a worker (the worker's Bash is restricted to these CLIs precisely for
  that reason).
- **Is it LIVE UI CONTEXT (what the operator has in front of them)?** → `memory.set_state({...})` (shallow patch).
  Two owners write it: the **frontend** reports the open widgets (`POST /api/canvas/state` from
  `desktop._persist()` → `set_state({open_widgets})`) and the **SlowBrain dispatcher** the tasks in progress
  (`nucleo/dispatch.py` → `set_state({activity})`). It is ALWAYS in the prompt and visible in the map. It is not
  memory that learns: it is the reflection of the "now".
- **Are you a CONNECTOR dumping incoming data from an external SOURCE (messaging, cluster, another agent)?** → use
  **`memory.ingest_message(source, entity, text, *, trust, durable, group, directed)`** — the UNIFIED TYPED path
  (multi-source). Whether there are two connectors or many, a cluster peer («Zalo») or a WhatsApp chat: they all
  come in here with their `source` (whatsapp/telegram/cluster/agent/email/**music**/…) and `entity` (who), which
  are **indexed in `meta`** (→ direct read by type with `recent_by_source`) **and** in the text (`[source] entity:
  body`). It is also the writeback path of the **RAILS**: e.g. the music rail writes every playback with
  `ingest_message(source="music", entity=<artist>, durable=True)` → history + tastes. **`trust`** is KEY:
  `operator`/`external` (the owner's own data) enter the FlashBrain's passive block; **`untrusted`** (a cluster
  peer/foreign agent) stays in **QUARANTINE** — it is NEVER injected into the passive prompt (anti prompt
  injection), it only surfaces on an EXPLICIT query. `durable=True` → level `mid` (persists + concepts for the
  graph); `short` by default (recency). `slot` (optional) = canonical key → **exact supersede**: every ingestion
  with the SAME slot OVERWRITES the previous one (for a SYNTHESIS that is rewritten per source/entity, not one row
  per message).
  - **CLUSTER channel (MeshKore peers) — PASSIVE, COMPRESSED observation** (`connectors/meshkore/mem_ingest.py`):
    the bridge does NOT dump every raw sentence of the cluster. For each exchange (peer→zaelar + zaelar→peer) a
    LOCAL model DISTILS, off the hot path, an **evolving synthesis per peer** (topics/agreements/data), stored with
    `slot="cluster:<cluster>:<peer>"` (one live pill that is rewritten) + `trust="untrusted"` (QUARANTINE). So
    "what have you talked about with Zalo?" is answered with `recent_by_source("cluster","Zalo")` without anything
    from the peer leaking into the operator's prompt. The channel runs in an untrusted profile (tools off,
    identity-safe): memory is a side effect of observation, it gives the peer neither state nor capabilities.
    Content is REDACTED (secrets) and handles neutralised before persisting. Fail-open (bounded deterministic
    merge if there is no model). Can be turned off with `MESHKORE_MEMORY=0`.
- **Never** put an LLM or SYNCHRONOUS memory I/O on the voice hot path. The write is fire-and-forget.
- **A pill, not a paragraph**: pass a CANONICAL, short `text`; for singular facts that get overwritten, give it a
  `slot` (`operator.name`, `goal.current`…) → the writer deduplicates/supersedes on its own.

**READING (direct, no LLM — pick the speed):**

- **STATE** (`memory.state()`) — µs, fixed table. Use it for "who they are / what they are up to". ALWAYS in the
  prompt (the FlashBrain serves it cached through `nucleo/flash/memory_cache`). It is "opening your eyes".
- **SHORT** (`memory.recent_short()`) — µs, direct read, NO embeddings. The WHOLE recent working set. For "what were
  we talking about". Over-includes on purpose (cheap).
- **LONG** (`memory.query(prompt, budget)`) — ms, retriever vec+FTS→RRF. For real recall ("where did Bartolo live",
  "a message from months ago"). It is the only layer that tolerates waiting; **on demand** and **off the event
  loop** (`asyncio.to_thread`) from the FlashBrain. The SlowBrain may use `compose_context` (recall + a cheap LLM
  router) because it runs off the hot path.
- **BY TYPE / SOURCE** (`memory.recent_by_source(source, entity)`) — µs, DIRECT read by index (`json_extract` over
  `meta`), NO retriever or LLM. It is "what came in on WhatsApp?" / "what did Zalo tell me on the cluster?" / "what
  music have I listened to?" (`recent_by_source("music")` → history + tastes). It scales to N sources by changing
  only `source`. It is the ONLY path through which `untrusted` content surfaces (quarantined from the passive
  block) — the free SLOT for the brain when the operator asks about a source. The `entity` filter is **case- and
  accent-insensitive** (SQL function `pylower`, Unicode): "María"/"maría"/"MARÍA" retrieve the same — SQLite's
  `lower()` is ASCII-only and would fail on accents/ñ.
- **Full map** (`memory.map()`) — only for the viewer/diagnostics (read-only, does not reinforce).

## Actions ↔ memory: when and how to touch the memory (protocol)

Mental rule: **the memory is zaelar's "I remember", not the system's state.** The state of what exists NOW is given
by the live sources (the widget catalogue, each widget's store, the scheduler…). The memory keeps what zaelar must
**remember having done or known** in order to talk like a human tomorrow. Therefore:

- **Touch the memory** when the action changes something the operator could ask about/remember later: a **fact or
  preference** of theirs ("my name is…", "don't narrate"), a delivered **result** (a search, a report), a
  **life-cycle milestone** (widget created/deleted), an episode (paste/drop).
- **Do NOT touch the memory** for what is ephemeral or already derivable from a live source: opening/closing/moving
  a widget, a state read, small talk with no new data. (The voice hot path **never** does synchronous memory I/O.)
- **Who writes**: always through the `memory.write` facade (async queue, loop-agnostic). From the SlowBrain the
  **memory agent** decides (`nucleo/memory_agent.remember`, the single decision point). **Widgets** and the
  **widget life cycle** (`widgets/lifecycle.py`) write directly through the facade (they are sanctioned writers).

**GOLDEN rule of deletion — history is never deleted.** Deleting something from the world (a widget) removes its
code/data, but **writes an event** that it was deleted; the memory of its creation is kept. So recall can answer
*"you had that widget deleted on <date>"* even though it no longer exists. To invalidate a fact that became obsolete
(not delete it) there is `valid=0 + superseded_by` (used by the consolidator on conflicts); a **life-cycle event**,
on the other hand, invalidates nothing — it accumulates as history.

Life cycle of a **widget** (implemented in `widgets/lifecycle.py`, triggered by the FlashBrain/SlowBrain):

| Action | Executed by | Memory |
|---|---|---|
| **CREATE** | SlowBrain (headless code agent — writes code) | `record_created()` → event `[widget:<id>] «X» CREATED on <date> for: …` |
| **MODIFY** | SlowBrain (code agent) | (the task result is already remembered by the dispatcher) |
| **DELETE** | **FlashBrain, deterministic** (rm folder + store), after **confirmation** | `delete_widget()` → **tombstone** `[widget:<id>] «X» DELETED on <date> at the operator's request` (history kept) |

**Browser authentication ↔ memory** (`widgets/navegador/auth_memory.py`): the same memory↔storage split. The
**secret NEVER enters memory** (cookies live in the Chromium profile `widgets/_data/navegador/profile/`, encrypted at
rest by the OS — the memory is searchable and surfaces in prompts/recall/the viewer, so a secret there would leak).
The memory only keeps what zaelar must REMEMBER: **the FACT of the session** (`record_session_established(site)` →
a `mid` event with `slot=navegador.session.<site>` → a re-login SUPERSEDES, it does not duplicate; recall answers
*"do I have a session on Wallapop?"*) and a **recoverable checkpoint** of a half-finished login
(`checkpoint_auth_pending` → `set_state({auth_pendiente})` + a SHORT event, mirroring `nucleo/reset.py`) that
survives a crash/restart to remind you that you left it halfway.

## Access points

- **Writers** (through the queue, async): **FlashBrain** (whatever is worth keeping), **the SlowBrain's memory
  agent** (results, facts, summaries), **widgets** (messaging dumps what comes in) and **Brain Workers** (as a
  SERIAL piece over HTTP: `hbmem remember` → `POST /api/memory/remember` → `remember_external` with gates + a
  per-task token — they NEVER open the database; see §The write HEART). What is irrelevant is discarded before
  enqueuing.
- **Readers** (direct, ms): the **retriever** (called by the SlowBrain dispatcher and the FlashBrain to compose the
  minimal context). **The FlashBrain's read is NOT on the synchronous voice turn** (latency): the STATE block
  (`memory.state()`) is **cached per session** (`nucleo/flash/memory_cache.py` — TTL + async refresh +
  invalidation on `memory.updated`), and **recall** (`memory.query` → embeddings) is **on demand** (heuristic
  `nucleo/flash/prompt.needs_recall`) and **off the event loop** (`asyncio.to_thread`). So a small-talk turn never
  triggers the retriever or blocks the loop, while real recall is preserved (see `zaelar-model-benchmarks.md §4`).
- **State maintenance**: the memory agent and the consolidator write the `state` table; the composer reads it on
  every prompt.

## Reading in the turn — THREE speeds (how requests come in and data goes back)

When a voice/chat turn arrives, the FlashBrain composes its prompt in `nucleo/flash/prompt.py::build_flash_system`.
The memory enters through **three read paths with three different speeds, aligned with latency** (the voice turn
NEVER does synchronous memory I/O on the event loop).

> **Each layer has its OWN DATA STRUCTURE and QUERY METHOD** (it is not a single mechanism): **STATE** = key–value
> slots (a fixed row, a small dict, `memory/state.py`) → whole direct read (µs), ALWAYS, zero search.
> **SHORT/recent** = a **chronological list** (a rolling log, `level='short'` rows) → read WHOLE, newest first,
> WITHOUT search (`recent_short`). **LONG** = an **indexed** archive (sqlite-vec vector + FTS5 + graph) →
> **semantic QUERY** (RRF vec∥fts → score → graph_expand), on demand and off-loop. Different structures and access
> paths on purpose: each one optimised for its role and its latency.

| Layer | Role | How it is READ | Code |
|---|---|---|---|
| **STATE** = *the stack* | What is burned in (name, goal/project, location…) **+ the LIVE UI CONTEXT** (open widgets `open_widgets`, tasks/sessions in progress `activity`/`sessions`, and live RAILS `rails` → "Rails in progress"): what the operator has IN FRONT of them. ALWAYS in the prompt. | **Instant, always** — an already composed and **cached** string (`memory_cache.get()`, TTL + off-loop async refresh + invalidation on `memory.updated`; the canvas report triggers the refresh). Zero query. | `nucleo/flash/memory_cache.py` · `memory.state()` |
| **SHORT TERM** = *working set* | What is recent/ephemeral (turns, today's messages). Small → fits whole. | **Whole and cheap** — ALL recent short term is plugged into the prompt WITHOUT the retriever (direct µs read). Reading it whole is more reliable than *searching* it for a fact just said (such as the operator's name). | `memory.recent_short()` → cached in `memory_cache._compose()` ("Recent conversation" block) |
| **LONG TERM** = *the archive* | Durable, a lot of information, does not fit. | **Only by QUERY** — retriever vec+FTS→RRF (database, slower), **on demand** (`prompt.needs_recall` as prefetch + the **`recall` tool**) and **off the loop** (`asyncio.to_thread`). | `nucleo/flash/prompt.compose_recall()` → `memory.query()` → `memory/retriever.py` |

> **Invariant:** STATE is read for free (cache), SHORT is read whole and cheaply (it fits), LONG is read by query (it
> does not fit). The SlowBrain, by contrast, composes context with `nucleo/memory_agent.compose_context()` (the
> multi-axis v2 dossier, see §The write HEART) — that one can afford search because it runs off the hot path.

**The recall gate has TWO paths** («the model decides when to search», applied to memory):
- **Heuristic prefetch** (`prompt.needs_recall`, deterministic es/en) — the classic path, optimistic and free. It
  includes **planning phrasings** ("I want to go on holiday", "organise a trip for me", "find me a hotel", "book me
  a restaurant"…) so the brain recalls exactly when it is about to plan something for the operator.
- **The `recall` tool** (`router.TOOLS`, canonical catalogue in `zaelar-architecture.md §8`) — the **MODEL decides to
  remember**: it covers what the prefetch did not catch. A LIGHT path, sibling of `web_search` in
  `voice/engine/llm/providers/nucleo.py`: `compose_recall` off-loop (`asyncio.to_thread`) + a second pass with the
  model the turn already pays for → the memories come back IN the turn, without a card or a worker. Only the
  operator's DURABLE memory (not world data = `web_search`; not what is already visible in STATE/conversation).

### The SHORT-TERM interaction circuit with the operator

The FlashBrain must be **fully situated** on every request (who the operator is, what they have in front of them,
what you were talking about) WITHOUT inflating the prompt. Three pieces, "the basics always + the heavy stuff on
demand":

- **A SACRED identity floor** (`nucleo/flash/memory_cache._store`): the cached STATE block is **never overwritten
  with empty**. `compose_state()` can fail transiently (a database read under contention in sessions with many
  writes) and return `('','')`; if that overwrote the cache, the FlashBrain would say *"I don't know who you are"*
  even though the name is in the state. The guard keeps the last good block and marks it `dirty` to retry. A
  legitimate empty state (fresh install / `reset()`) starts from an already empty cache, so it passes.
- **A window seeded from memory** (`brain._window` ← `memory.recent_window`): the dialogue window (the last
  `_WINDOW_MAX`=10 verbatim turns the model sees) lives in RAM, so a new brain instance (restart/reconnection) would
  start empty and lose "what we were talking about". It is **seeded once** from the persistent conversational buffer
  (`kind='conv'`, with structured `meta.u`/`meta.a`). Zero extra tokens (the window was already capped). Wired
  IDENTICALLY in voice (`nucleo.py::_run`) and in the probe (`nucleo/flash/probe.py`) → the probe faithfully
  reproduces start-up after reconnecting.
- **An on-demand second SHORT-TERM pass** (`prompt.needs_recent` → `prompt.compose_recent_block`): when the turn
  **refers to the recent interaction** ("what were we talking about", "what I told you before", "repeat that", "a
  while ago"; es/en, deterministic) the **EXTENDED** conversational buffer (verbatim, ~20 turns, more than the
  normal window) is injected as a labelled block — **off the event loop** (`asyncio.to_thread`). Normal chat does
  NOT carry it (a light prompt); it is only loaded when needed. It is the short-term sibling of `needs_recall`
  (which is for the DURABLE fact by meaning, via embeddings). Telemetry `recent_fired` in `/debug`.

### The COMPOSED STATE — `memory.compose_state()` (contract)

The brain's prompt is **[dynamically composed STATE] + [the operator's request]** (a compact prompt of a few dozen
lines). The MEMORY owns the composition of that STATE: `memory.compose_state(*, mission_fallback="") -> (block,
operator_name, stats)`. It is what the **two brains SHARE**; RESOURCES/tools diverge per brain (their own layer).
**DIRECT** read (µs, no LLM or retriever) → safe to cache outside the turn (`nucleo/flash/memory_cache` caches it
with TTL + async refresh + invalidation on `memory.updated`; the voice turn NEVER composes it without the cache).
Ordered structure:

| Section | What it carries | Where from |
|---|---|---|
| **A · WHO YOU ARE** | The MISSION/identity (3-4 sentences, in the operator's language). It LIVES IN THE MEMORY — not in an English prompt. | `state.mission`, seeded at start-up by `memory_cache.prime()` from `langs.LangSpec.mission`; `mission_fallback` if not yet seeded (the caller passes it so as not to invert the memory→voice dependency). |
| **B · WHO IS IN FRONT OF YOU** | VARIABLE situational data: operator (name/address/location + durable STATE fields), OPEN widgets, tasks/sessions IN PROGRESS, **RAILS in progress** (live FlashBrain runs), and the salient durable profile ("what you know about them"). | `memory.state()` + `memory.salient_long()` (terse cap). |
| **C · WHAT YOU WERE TALKING ABOUT** | A TIGHT synthesis of the recent conversation — the last lines of short term (aggressive cap), NOT the whole raw dump nor LONG memory. | `memory.recent_short(limit=5, max_chars=550)`. The cut IS the "synthesis" (it is still a direct read; an LLM synthesis, if ever wanted, would go OFF the turn). |

The mission (A) seeded in `state.mission` is visible in the memory map (STATE column) and editable — identity is not
hard-coded in `voice/prompt.py` (that English persona only serves the `BRAIN=direct|local|duo` baselines and the
harness). On top of this STATE, the FlashBrain adds its TERSE resources layer (`nucleo/flash/prompt._flash_layer`)
and the SlowBrain its own; "when to use each tool" lives in the tool description (`router.TOOLS`), not duplicated in
prose.

### The SHAPE OF THE KEY decides whether a pill is a fact about the PERSON

The operator's slots use a **dot** (`operator.location`, `goal.current`); background dumps — widget, cron, cluster
— use a **namespace with a colon** (`<widget>:<key>`). This is not cosmetic: it is the only thing that tells "a fact
about the person" from "what an automatic job produced", and **both readers that serve the model apply it**:

| Reader | What it renders | Where it is filtered |
|---|---|---|
| PASSIVE block (every turn) | "[What you know about them]" | `memory/api.py::salient_long` — `slot NOT LIKE '%:%'` |
| Worker DOSSIER (per task) | "WHAT YOU KNOW ABOUT THE OPERATOR (relevant to the task)" | `nucleo/memory_agent.py::compose_context` |

The dossier is where this matters most: without the filter, a background pill such as `weather:<city>` (`mid/note`,
importance 0.3) written every hour by a weather widget could outrank `operator.location` under that heading, and a
worker searching for a local service would search in the wrong city. Weather widgets ship in the repository, so
this applies to every self-hosted install, not just to test data.

Three decisions worth not reopening:

1. **The exclusion is CONDITIONAL, not a veto.** Namespaced pills must stay reachable on an EXPLICIT question, and a
   worker's task can legitimately be about that city. A namespaced pill enters if the task names its namespace or
   its key ("the weather in <city>" yes; "find a plumber" no).
2. **The origin goes in the KEY, not in `meta`.** The retriever **does not return `meta`** (it does return `slot`):
   resolving it through `meta['widget']` would mean pulling another column and having every consumer parse JSON.
   The write lock lives in `widgets/background.py::TickCtx._own_slot` — the only place that KNOWS the author is a
   background job.
3. **Renaming a slot WITHOUT migrating leaves two live lineages.** Supersede works on the EXACT slot, so
   `weather:<city>` and `<widget>:weather:<city>` would both stay `valid=1` and — with no TTL — the old one would
   compete in recall forever. The **v5→v6** migration (`memory/db.py::_namespace_widget_slots`) closes it: it
   mirrors `_own_slot`, collapses duplicates keeping the MOST RECENT, and **touches no row without `meta.widget`**
   (a slot without `:` and without a widget belongs to the operator and does not move). The old writer already
   stamped `meta.widget`, so the author is known row by row. A migration **freezes the rule of ITS version**: if
   `_own_slot` changes, that calls for a v6→v7, not for the migration chasing the writer.

Tests: node **1.1** — `tests/memory/unit/test_widget_slot_migration.py` (several cases go red if the migration is
removed) and `tests/memory/integration/test_memory_agent.py` (the dossier filter, in both directions).

## The write HEART — the LLM that DISTILS every datum into a pill

**Golden invariant: WRITING may be SLOW; READING must be MAXIMUM SPEED.** Writing WELL is the priority and may take
as long as it needs: placing each datum in its layer (STATE/SHORT/LONG), not duplicating, scoring weight/importance,
organising the graph's concepts and computing embeddings/vectors — all **off the hot path** (async queue); there is
no need for writes and reads to be immediate, so a SLOWER, MORE PRECISE write model is preferable. READING, on the
other hand, is paid by the FlashBrain IN the turn (composing the prompt, answering, acting) → it **NEVER carries an
LLM or synchronous memory I/O** (it would block the voice). The "heart" that decides, for each thing the operator
says, **whether it is stored, WHERE (STATE/SHORT/LONG/DISCARD), with what importance/TTL and under which `slot`**,
lives in `nucleo/memory_agent.py` + `nucleo/mem_processor.py`:

- **`mem_processor.process(text, state) → list|None`** — the **LLM processor**. Default model: DeepSeek Flash
  DIRECT (`api.deepseek.com`), stand-in OpenAI `gpt-4.1-mini` (`config/models.default.json` §memory_writer; config
  `§memory.mem_processor_model/_base_url/_api_key`). Chosen by the **distillation bench**
  (`tests/memory/e2e/bot/distiller_bench.py`, `zaelar-model-benchmarks.md §12.3`): many commercial candidates over a
  fixed corpus on **four separate axes** (write-completeness · precision/no-pollution · layer+slot · $/1k turns with
  real tokens) — see §Memory models for the reasoning and the `gpt-4o-mini` veto. Writing is off the hot path, so a
  slower model costs the turn nothing. The **local OPTION** (qwen via Ollama) remains available by pointing
  `base_url` at Ollama, for battery/privacy. It reports usage to `nucleo/energy_meter` when metering is enabled
  (`energy_meter.report_llm_usage`). Env `MEM_PROCESSOR_MODEL/URL/KEY` = power-user fallback; model per invocation.
  The **credential is resolved PER ENDPOINT** (`mem_processor._key` → `_endpoint_key`, same pattern as
  `fast_client.resolved_api_key` — the key follows the URL, never the other way round), so a stale key can never be
  sent to the wrong endpoint. **First-class HEALTH**: a **streak of failures** fires an alert through the observer
  (and a recovery notice when it comes back), and `mem_processor.status()` exposes model/streak/last error/degraded
  to the settings area — a HEART that is down cannot go unnoticed. Write-completeness is the number-one lever of
  recall, and since writing is off the hot path, **we prefer the most precise model even if it is slower**. It
  **DISTILS** the raw turn into **canonical pills** (not the literal sentence): `{text, dest, kind, importance,
  ttl_days, slot, value, change, state_patch}` (v2 contract, see §Supersede). Under GPU contention turns are not
  lost: a **short deferred queue** (serial — never two distillations at once; bounded wait
  `MEM_PROCESSOR_QUEUE_WAIT`/`_MAX`) and only when that runs out does it fall to the heuristic, OBSERVABLY.
  `importance` is **dynamic** — the prompt receives the current STATE to judge relevance in context (studying law
  → law matters). Return semantics: **`None`** = model unavailable → falls to the heuristic; **`[]`** = the LLM ran
  and decided to DISCARD (respected); a list = pills to store. ⚠️ With an external provider the turn's TEXT is sent
  to that provider to be distilled; with the local option (qwen via Ollama) nothing leaves the machine.
- **`ingest_utterance(text)`** — the entry point for "something the operator said". Flow: (1) obvious trivia/command
  → cheap DISCARD without an LLM (anti-noise); (2) the LLM processor distils pills; (3) **fail-open**: if the model
  is unavailable, it falls back to `classify()` (regex heuristic) so the profile is not lost. **Wired on every
  directed turn** in `voice/engine/llm/providers/nucleo.py` (`asyncio.create_task`, fire-and-forget → zero cost to
  TTFB).
- **`classify(text)`** — the µs FALLBACK heuristic (es/en regex): PROFILE (name/location/address/hardware/car/
  goal/project) → `state_patch` + a pinned `long` trace with `slot`; WISH/PREF → `long`; TRIVIA/COMMAND → skip;
  everything else → `mid`. It is the fail-open when the LLM does not answer, and **it does not pollute**: the raw
  turn degrades to `short` + a 3-day TTL (an undistilled text is NEVER made durable), while the deterministic nets
  (health/commitments/routines) keep rescuing what is critical.
- **`remember(item)`** — the SlowBrain's ONLY writer; accepts `slot`/`meta`/`ttl_days` (auto-classifies if the
  caller does not set a destination). **`_write_atom(atom)`** maps an LLM pill → layer (state→state + long/pinned
  trace; long/short→a memory with its ttl/slot).
- **`compose_context(prompt)`** — the worker's **multi-axis v2 DOSSIER**: the operator's profile (**without the
  mission** — that is zaelar's identity and only noise in a worker's prompt) + **operator rules** (`state.rules`) +
  **⚠️ critical facts ALWAYS** (`memory.critical_facts`, independent of the ranking) + RRF recall + **the CONCEPTS
  axis** (`memory.by_concepts` — the task's concepts aggregate the graph cluster) + **upcoming agenda** (read-only
  from the widget). **DURABLE only** (the raw conv buffer does not compete for the slots) and all I/O in
  **`asyncio.to_thread`** (`_dossier_sync`). It is the ONLY face of the agent that can afford recall + an LLM
  router — it runs off the hot path.

**Supersede/dedup by SLOT (DETERMINISTIC, no LLM)** — "the newest WINS": `memory/writer.insert_memory`, on receiving
a `slot` (normalised by `canon_slot` against the `memory/slots.py` registry), looks at **ALL current memories** with
that slot → if the normalised text of the most recent one is identical it **REINFORCES** it (raises weight, zero
duplicates) and collapses the stragglers; if it differs, it inserts the new one and marks **all** the old ones
`valid=0, superseded_by=new` (self-healing). So "my name is Ricard" said three ways = ONE reinforced fact, not three
rows — and a historically duplicated lineage collapses on its own. The SELECT of current rows **expands by ALIAS**
(`slots.equivalent_keys`): writing `operator.location` also collapses a legacy pill with a raw `location`/`ubicacion`
key → the collapse is IMMEDIATE, without waiting for the `heal_slots` of sleep.

**BACKGROUND slots are SUBORDINATE to `state.location` (`salient_long`):** the passive state block ("what you know
about them, take it as known **without searching**") only renders facts about the OPERATOR (slots with `.`:
`operator.*`/`goal.*`/`project.*`, or no slot). Background slots namespaced with `:` (`weather:<city>` dumped by a
weather widget in the background, `<widget>:<key>`, `cluster:*`) stay **OUT of the passive block**, so a salient
`weather:<city>` can never hijack "what's the weather today?" (the brain lands on `state.location` and searches).
They remain **retrievable by the retriever** on an EXPLICIT question about that city; they just do not compete with
the operator's profile in the passive prompt.

**MEDICAL SAFETY — allergies are ADDITIVE + always present:** an allergy/intolerance is an **additive and critical**
medical fact. An LLM could mis-assign it to the SINGULAR slot `operator.diet`, and then a DIET declared later would
ERASE it (supersede by slot: "I'm vegetarian" overwriting "allergic to penicillin"). A DETERMINISTIC guard in the
WRITER (the choke point, `_is_critical_health`, es/en) ensures a critical allergy/condition **never keeps a singular
identity slot** (it stays additive → several allergies coexist; semantic dedup merges repetitions), is set **pinned
+ importance ≥0.95**, and is marked `meta.critical='health'`. At READ time, `memory.critical_facts()` feeds a
**dedicated ⚠️ CRITICAL line** of `compose_state` that surfaces **ALWAYS**, independent of the ranking/cap of
`salient_long` (under density the allergy could otherwise fall outside the top-N). Forgetting an allergy is a safety
failure — that is why it does not depend on the retriever. A real diet (without an allergy marker) still supersedes
another diet normally.

**v2 atom contract — `value` + `change`:** besides `slot`, the processor emits (a) **`value`** = the bare value of
the singular fact ("Valencia") → the host **SYNTHESISES the `state_patch` MECHANICALLY** from the slot registry
(even if the LLM wrote the change as a loose fact without patching the state); (b) **`change:
none|update|correction`** = the semantic signal "this is a declared change/correction, not a garble", consumed by
the P0b anti-garble gate **per atom**. The signal is emitted by the MODEL itself (multilingual by nature, agnostic to
phrasing) → the host's regex family (`_RELOCATION_RE`, `_CORRECTION_*`, …) remains a **BACKSTOP for literal
Spanish/English**, not the only mechanism. The processor's few-shots are NEUTRAL (a fictional persona — never the
real operator: the memory ships BLANK) and include the declared-change case.

**EXTERNAL writes (Brain Workers) — `memory_agent.remember_external`:** the workers' path (`hbmem remember` → `POST
/api/memory/remember`) requires the **per-task token** (`ZAELAR_TASK_TOKEN`, headers from `mem_cli`; dev hatch
`ZAELAR_MEM_API_OPEN=1`) and applies the SAME gates as voice: precision gate P0a, **NEVER touches `state`** (a worker
does not speak for the operator), **IDENTITY slots vetoed** (they degrade to a loose fact; work slots `goal.*`/
namespaced pass) and **stamped provenance** (`meta.source="worker:<id>"`). A task's result is only remembered if it
finished **OK** (failed ones are announced by voice but do not pollute the `mid` level).

**The HEART's net of DETERMINISTIC BACKSTOPS (es/en regex, no LLM)** — an LLM sometimes DISCARDS as "chatter" things a
human DOES remember, or decides inconsistently. `nucleo/memory_agent.py` intercepts unambiguous patterns
BEFORE/AFTER the LLM and guarantees the correct behaviour regardless of phrasing (each with a guard in
`tests/memory/integration/test_memory_agent.py` and its own batch in the memory bot):
- **Commitments** (`_COMMITMENT_RE`) — a request/appointment/errand ("my boss asked me for the report by
  Wednesday") is ALWAYS stored even if the LLM canonicalises it and drops it.
- **Routines** (`_ROUTINE_RE`) — a recurring habit ("gym every Monday") is memorable as a pattern.
- **Observations/self-knowledge** (`_OBSERVATION_RE`) — "I've noticed I perform best in the mornings", "when I have
  dinner late I sleep badly" → self-knowledge useful for advice, which an LLM may discard inconsistently.
- **Reversals/cessation** (`_REVERSAL_RE`) — "I don't drink coffee any more", "I no longer work there" → a change of
  state; the NEW state is stored so the brain knows that NO LONGER applies.
- **Explicit correction** (`_CORRECTION_RE` "it's not X but Y" — captures values starting with a letter OR A DIGIT,
  for PINs/codes; `_CORRECTION_YANO_RE` "ya no … ProperName") → forgets (invalidates) the wrong value and goes on to
  store the new one.
- **Declared relocation** (`_RELOCATION_RE`) — "me he mudado a Valencia", "we've moved to X", "I moved to X" →
  updates `location` (profile patch + slot `operator.location`, exact supersede) and counts as a CORRECTION for the
  P0b gate (a life change stated in so many words is not a garble). Plus a **PROFILE→STATE backstop**: if the
  heuristic detected profile data (name/location/…) and the LLM's atoms did NOT touch those `state` fields, the
  patch is applied anyway (otherwise a relocation written as a loose fact — "now lives in Valencia" — would leave
  the state on the OLD city). **This family is a BACKSTOP, not the primary mechanism:** the legitimate-change
  signal comes from the processor itself (`change: update|correction`, any language/phrasing) and the profile
  patch is synthesised mechanically from `slot`+`value` — the regexes only cover the heuristic path (LLM down) and
  literal Spanish/English.
- **Forget on request** (`_FORGET_RE`) — "forget about X" → soft-invalidates (keeps history). **HARD forget**
  (`_FORGET_HARD_RE` "completely / forever / without a trace") → `forget(hard=True)`, a real, irreversible deletion
  (the right to be forgotten for sensitive data). The hard path **DELEGATES to `writer.delete_memory`**, which
  issues the FTS5 `delete` WITH the text BEFORE deleting the row (+vec +edges), so no phantom remains in the FTS5
  index and the "deleted" text is truly unrecoverable. **Un-forget** (`_UNFORGET_RE` "recover the X thing") →
  reverts a soft forget (valid=1; the retriever already filters by valid).
- **Write-side abstention** (`_ASSISTANT_QUERY_RE`) — an UNAMBIGUOUS question to the assistant ("what's the weather
  in X?", "can you recommend…?") is NOT a fact about the operator → DISCARD (avoids inventing preferences).
  Conservative: it does not touch questions that carry a datum ("did you know I moved to Madrid?").

**Write PRECISION gates — the HEART does not POLLUTE long term.** Symmetric to the backstops (which RESCUE what the
LLM drops too eagerly), these FILTER what the LLM keeps too eagerly. A small model may reify questions/requests as
"facts", propagate STT garble into `state` and over-generalise ephemeral directives → DETERMINISTIC guards in
`nucleo/memory_agent.py`, applied to the output of the LLM **and** of the heuristic:
- **(P0a) Requests/questions/acks → DISCARD.** Pre-LLM: a vague directive/question with no referent
  (`_is_vague_request` "look at that", "can you look at that?"). Post-LLM: `_ATOM_NONFACT_RE` drops the atom whose
  canonical text is a reified question ("the operator asks whether…", "wants to know…") or an interrogative. It does
  **not** touch CONCRETE TASKS with data ("find me flights to Tokyo" → still rememberable via `_COMMITMENT_RE`) or
  WRAPPED STATEMENTS ("remind me that I'm allergic…" → the fact is stored).
- **(P0b) IDENTITY plausibility** (`_plausibility_demote`): a singular slot value (`operator.name`…) that
  CONTRADICTS the one already established in `state` does NOT overwrite it on a single mention (typical STT garble)
  → it is demoted to `long` in **QUARANTINE** (`trust=untrusted`: retrievable only by explicit query, never surfaces
  in recall/prompt). Explicit CORRECTIONS ("my name isn't X, it's Y") and a declared RELOCATION (`_RELOCATION_RE`)
  do pass (they have already forgotten/superseded the old value). In an EMPTY profile the first datum enters
  normally (there is no conflict). This keeps a polluted `state` from ever making the agent introduce the operator
  by a misheard name.
- **(P1) EPHEMERAL preferences** (`_is_ephemeral_directive`): an immediate screen/action directive ("don't show me
  anything now", "not now") is session style that the FlashBrain executes — NEVER a durable preference; pre-LLM
  discard. It only becomes durable if it carries a durability marker ("I prefer/always/in general…").

Covered by `tests/memory/integration/test_write_precision_v2033.py` (`MEM_PROCESSOR=0` → deterministic, no GPU) +
a smoke run with the real LLM distiller, alongside the rest of the memory suite. Together with the recall levers
above, this is the "precision" face of the principle that recall depends on **write-completeness + PRECISION** more
than on the embedding.

**Hard reset ↔ memory** (`nucleo/reset.py`): when everything is stopped, the work in progress is **FROZEN in
STATE** (`set_state({trabajo_interrumpido})`) and the order is recorded in **SHORT** (`memory.write
level='short'`) before the processes are killed. It also clears the **live RAILS** (`rails.clear_all` →
`state.rails=[]`): a run (`sin_resolver`, playing…) is SESSION state, not durable memory — what is durable was
already dumped through its typed writeback.

## The operator's secrets vault — encryption + split storage

> Memory modules: `memory/vault.py` (crypto), `memory/secrets.py` (detection), `memory/vault_api.py`
> (`/api/vault/*`). The brain's read flow lives in `nucleo/flash/vault_flow.py` + the `reveal_secret` tool. Security
> model in `zaelar-security.md`, configuration surface in `zaelar-conventions.md`. Here, what concerns the MEMORY.

The **operator's secrets** (a Netflix password, IBAN/card, a crypto account number, a wallet's private key) cannot
live in a pill in plain text. The memory provides:

- **A FAIL-CLOSED classification gate in the HEART** (`mem_processor`, above): besides DISCARD/STATE/SHORT/LONG, it
  decides **is it a SECRET?** — deterministic patterns (Luhn/IBAN/BIP-39/`0x…`/`sk-…`/"password for …") **+** the
  LLM; **when in doubt, encrypt** (this inverts the usual fail-open: a secret in plain text = broken privacy). The
  operator can force "store it encrypted".
- **SPLIT storage** (a special pill): a **plain, searchable label** ("Netflix password" → embedded/indexed/reranked
  normally, `slot=secret:*` for supersede) **+ an opaque encrypted value** (`meta.vault=1`, `meta.sensitivity`).
  The value is NEVER embedded, logged, put into the prompt/`memory_cache`, or sent to a worker.
- **Asymmetric encryption** (sealed box): the **public key** lives in plain text → **writing a secret does NOT need
  an unlock** (the HEART encrypts and stores without more ado, and a worker can also *write* one); the **private**
  key (for READING) is wrapped by a passphrase and/or passkey. Crypto detail in `zaelar-security.md`.
- **Reading:** the retriever finds by label and returns the signal **"sealed → ask for unlock"** (never the text) →
  the FlashBrain requests the passkey/passphrase; decryption happens in the browser (strict mode) or on the server
  for an instant (comfort mode, for TTS).

## Memory observability — event log + viewer

Two surfaces to SEE the memory working in real time:

- **The ◷ logs column** (`/debug` · `frontend/app/components/DebugPanel.js`): the turn emits `kind=memory` rows with
  **module=memory · layer (state/short/long/slow) · request → result (number of cards/chars) · time `mem_ms`**
  (emitted in `voice/engine/llm/providers/nucleo.py` after `build_flash_system`); writes/queries arrive labelled
  through the SSE bridge. Detail in `zaelar-observability.md`.
- **The memory viewer 🧠 — a monitor, not a browser** (V2-808, V2-814; `frontend/app/components/MemoryMap.js` +
  `components/memory/`, full-screen overlay opened from the orb's bowl): **Overview · Graph**. It shows totals and how
  the memory relates concepts; no stored row (a fact, a turn, a message, a file) ever leaves the server through it,
  and it says nothing about the machine it runs on.
  - **Totals are COUNTs** on the server (`GET /api/memory/viewer/stats`, cached a few seconds), one card per store:
    memories, conversations (sessions and days, from the event log), messages (per source, per day, size), files
    (by type, with their size), contacts, agenda, app data (each widget's data folder, walked in a background thread
    and reported `pending` until measured; a browser widget's `profile*` is its browsing session and is not
    counted), rules, learnt phrases, activity log, vault (a number, nothing else). Each card with a series carries its
    last 30 days, and opens in place to show them with its breakdown.
  - **The graph is aggregated on the server** (`memory/viewer.py::graph`): concepts with counts and concept↔concept
    weights over a time window (scan cap 20.000 rows), bounded by the node budget the client sends (clamped
    50..3000). LONG pills hang from their persisted concept edges, SHORT ones from `memory/concepts.py::derive_concepts`
    (the same substrate the writer's backstop uses). Inbound messages (`kind='msg'`) are out unless the messages lane
    is asked for (the viewer never asks). A selected concept is its numbers and the concepts it is related to
    (`/concept`) — never a memory's text.
  - **The device budget** (`components/memory/budget.js`): phone 300 nodes, laptop 1.500, big screen 3.000, from
    `navigator.deviceMemory`, `hardwareConcurrency` and the viewport; an unknown reading never promotes a device. It is
    internal: the viewer never prints it.
  - **Drawing**: one `<canvas>` sized to its section and re-fitted whenever the layout moves or the section resizes;
    labels and dots by level of detail; the force layout runs in `force-worker.js` (hub↔hub repulsion, grid
    collision, springs split by degree, capped velocity) and stops posting once it settles.
  - `GET /api/memory/map` (`memory.api.map()`) stays for probes and tests, BOUNDED: valid rows, the newest per layer
    up to 500, the edges of those rows, totals as COUNTs.
- **Real time + tinting** (gated by the `memory_observability` flag, default ON, in `config/settings.py`): the server
  bridges `memory.updated` from the bus → topic `observer` → `/events` (`server/__init__.py`). While the viewer is
  open, only the VISIBLE tab refreshes (debounced): the graph re-aggregates and keeps its node positions, a list
  prepends only the rows it does not show yet; each event's `ids` ring the touched memory dots for a few seconds.
  `services/sse.js` routes `store.bumpMemory()` (refresh) + `store.pushMemPulse({op,ids})` (ring).

## Evaluating the memory — HOW a memory system is tested (theory + practice)

> The goal: "a memory ever closer to a human's, but with superpowers". Getting there requires testing it IN DEPTH,
> in an original and well-structured way, deriving how a memory is put to the test and **applying what the
> literature says**. This section is the canonical THEORY; the operational map lives in
> `tests/memory/e2e/bot/TAXONOMY.md` (dimensions + coverage) and `EXIGENCIA.md` (periodic quality review of the case
> corpus).

**What the literature measures.** The field converges on a set of **core abilities**: the LongMemEval (ICLR 2025),
LoCoMo, MemBench, **MemoryAgentBench** (ICLR 2026), MemConflict, BEAM, STALE and Mem2ActBench benchmarks.
MemoryAgentBench summarises them as **4 competencies + 1 gap that almost nobody tests**:
1. **Accurate retrieval** — the fact comes out when asked for.
2. **Test-time learning** — updating/adapting to what is new (corrections, reversals).
3. **Long-range understanding** — deep retention + multi-hop + temporal.
4. **Selective forgetting** — decay, eviction, forgetting on request; NOT everything is kept forever.
5. **Structure organisation** — *the gap*: how the memory is ORGANISED (a concept graph), not only what it contains.
   In zaelar that is `edges`/`memory/concepts.py` and the viewer's CONCEPTS view.

**How we test it in zaelar (methodology).** Several surfaces, aligned with the field's good practice (**incremental
multi-turn** interaction + **regression checks** on every change + **human review** for what an LLM judge cannot
decide):
- **The memory bot** (`tests/memory/e2e/bot/`, `python -m tests.memory.e2e.bot.runner`): feeds the memory turn by
  turn over a database that **ACCUMULATES** (as in MemoryAgentBench: incremental chunks), and checks the behaviour
  along the REAL PATH — `_brain_view` reconstructs EXACTLY what the FlashBrain sees (cached block + recall if the
  `needs_recall` gate fires), **with no LLM on the read**. Step types: `save`/`query`/`dedup`/`turn`/`connector`/
  `source_query`/`cluster_exchange`/`forget`/`unforget`/`consolidate`/`episode`/`scale`/`recall_probe`/
  `weight_check`.
- **The focused conversational gateway** (`cases4.py`): the primary action of the Test Observatory. It passes
  natural paragraphs through `ingest_utterance → HEART → gates → writer`, requires an LLM source, inspects every
  pill, slot and state, and then questions the same memory. That way extraction is not hidden behind direct writes.
- **The life-cycle timeline** (`tests/memory/e2e/timeline/`): a long sequence of operations on an isolated database
  and clock, with light sleep and REM after every simulated day. It uses explicit atoms to measure aging, TTL,
  reinforcement, correction and forgetting without confusing a life-cycle regression with variation in the
  extractor model.
- **pytest** (`tests/`, `tests/memory/integration/test_memory_agent.py`): deterministic guards of the pieces
  (backstops, forget/unforget, concept vocabulary, degraded-backend warning…) — the regression net that runs on
  every change.
- **The live tester**: what is behaviour of the turn's LLM (query-time abstention, resolving a conflict, irony) is
  NOT the membot's job (it reads without an LLM) → it is tested with the agent that TALKS to zaelar plus a judge.

**Which MODEL runs in each layer (so as not to confuse it with whatever is installed in Ollama).** This machine may
have local models installed for other reasons (self-hosting, tests unrelated to the memory module) — an `ollama
list` showing something does not mean the memory uses it. The memory has TWO model-decision families, completely
separate:

1. **Embeddings (the retriever's vectors)** — `memory/embeddings.py`, config `§memory.embed_provider/embed_model`.
   Default: the cloud provider declared in `config/models.default.json` §embeddings (`text-embedding-3-small`,
   768); Ollama `embeddinggemma` (the table's `local` block) as the free local option from the panel or
   `ZAELAR_EMBED_BACKEND=ollama`; `fastembed`→`hash` as safety nets (the space is never mixed silently,
   `writer.py::_embed_sig_ok()`; changing it is a migration, `reembed.py::migrate`). **It takes no part in
   writing/reasoning about what is remembered** — it only turns text into a vector for semantic search.
2. **Writing/synthesis (reasoning about what to store or summarise)** — the HEART (`nucleo/mem_processor.py`) and the
   REM synthesis (`nucleo/memllm.py`, including the fidelity gate `verify_insight_grounded`). Defaults in
   `config/models.default.json` (§memory_writer, §memory_rem): a DeepSeek Flash model through the direct endpoint
   with OpenAI `gpt-4.1-mini` as stand-in; the table's local model (§local.llm, via Ollama) can be configured instead.

**What EACH test layer runs, concretely:**

| layer | real WRITING/SYNTHESIS model | runs with a real LLM? | cost |
|---|---|---|---|
| pytest (`tests/memory/unit`,`integration`) | none — hooks/mocks injected by hand | NO | $0, every commit |
| bot corpus (`tests/memory/e2e/bot/`, `cases.py`/`cases2.py`/`cases3.py`) | the configured HEART (`§memory.mem_processor_*`) | YES on write; read without an LLM | real, occasional |
| conversational gateway (`cases4.py`) | the configured HEART | YES (full extraction) | real, occasional |
| timeline (`tests/memory/e2e/timeline/`) | by default: a DETERMINISTIC pure-Python hook (`_deterministic_hook`) — no real LLM; **`--real` wires the REAL HEART + `verify_insight_grounded` + paraphrases** inside the timeline itself | NO by default; YES with `--real` | $0 by default; real and occasional with `--real` |
| `distiller_bench.py` | SWEEPS commercial candidates to CHOOSE the HEART | YES, many models at once | real, only when re-evaluating |
| `scale_eval.py` | none — measures the retriever (embeddings+reranker), not synthesis | NO | embeddings/reranker only |
| insight-fidelity unit tests (`test_rem.py`) | `verify_fn` MOCKED by hand (`lambda insight, pills: True/False`) | NO — mechanics, free, every commit | $0 |
| `live_rem_faithfulness.py` (dedicated script) | the REAL `verify_insight_grounded()` — no mock | YES | real, small |

`tests/memory/e2e/bot/live_rem_faithfulness.py` validates `verify_insight_grounded()` against the real model; re-run
it whenever the REM model or its prompt changes.

**A taxonomy of failure dimensions (A–X + subtypes).** Each dimension attacks ONE distinct failure mode and is
anchored to the corresponding state-of-the-art ability (full table in `TAXONOMY.md`). It covers extraction
(telegraphic↔long-winded), state/short/long, dedup/supersede, discard/abstention, graph/category, multi-source,
trust quarantine, interests, temporal/order, **scale** (needle-in-a-haystack in a large store), forgetting/decay,
contradictions, privacy, routines, adversarial/STT/injection, cross-source, multilingual, episodic, vocabulary gap,
**multi-hop**, verbosity, standing instructions, implicit invalidation (STALE), and a wide set of human scenarios
(spatial memory, kinship, promises/debts, procedures, superlatives, mistakes, decisions, observations, aversions,
goals…).

**Quality discipline (`EXIGENCIA.md`).** The case corpus grows with ORIGINAL cases, never duplicates. At regular
intervals a review asks: are we duplicating? Is there variety (input length / volume / the three speeds)? What is
missing? Should the approach change? Is there new ammunition in the literature? Should the memory EVOLVE
(stress→detect→improve→stress)?

**Extension points the evaluation keeps an eye on:** denser slot assignment by the HEART (so chained
supersede/dedup is complete), multi-hop retrieval beyond the bounded `graph_expand`/PPR channel, CONCEPT EXPANSION in
recall so a broad or cross-topic query aggregates and applies a constraint (`memory.by_concepts` already does it for
the worker dossier), detection of IMPLICIT invalidation/staleness, keeping proper names in verbose input, and giving
the distiller conversation context so a correction without a subject is attributed correctly.

## Modules (folders)

> **Design decision:** the memory is a **top-level `memory/`** module (a sibling of `voice/`, `widgets/`), **NOT**
> `nucleo/memoria/`. It is the shared substrate — written by the FlashBrain, the SlowBrain's memory agent and
> widgets; it is not part of the brain.

- `memory/db.py` — SQLite connection `zaelar.db` (WAL) + loading `sqlite-vec` + schema migrations.
- `memory/schema.py` — DDL (state · memories · vec_memories · fts_memories · edges · episodic · journal · …).
- `memory/queue.py` — async queue (asyncio.Queue): every write goes in here.
- `memory/writer.py` — the single writer → database; embeddings computed on insert. **Embedding SIGNATURE
  enforcement**: if the active embedding model does not match the database's signature (or is degraded), the pill is
  marked `meta.embed_pending` instead of inserting a vector from ANOTHER space (the REM phase repairs it) — vector
  spaces are never mixed silently.
- `memory/embeddings.py` — embeddings client (cloud provider by default · Ollama `embeddinggemma` option · fastembed
  and hashing safety nets). `memory/reembed.py` — the space signature and the MIGRATION door; `memory/dedup_thresholds.py`
  — the per-model dedup thresholds; `tests/memory/benchmarks/calibrate_dedup.py` — measures them on a copy of a real database.
- `memory/retriever.py` — hot path: vec ∥ fts ∥ paraphrases → RRF → weighted score → rerank → graph_expand.
- `memory/state.py` — fixed table (µs read, no search).
- `memory/graph.py` (+ `memory/graph_ppr.py`) — edges (link/expand, multi-hop PPR).
- `memory/episodic.py` — files/PDFs: searchable embedded summary + lazy load of the binary.
- `memory/consolidator.py` — the LIGHT "sleep" job (hourly: promote/exact dedup/decay PER WINDOW/prune_invalid/evict).
- **`memory/rem.py`** — DEEP sleep, the "REM phase" (daily): repair_embeddings + semantic_dedup + synthesize
  (insights per concept, injected LLM hook) + hygiene. See §DEEP sleep.
- `memory/api.py` — the public facade (write[+`slot`/`meta`]/write_now/query/**recent_short**/state/set_state/
  reinforce/pin/unpin/link/load_episode/consolidate/**map**).
- **`nucleo/mem_processor.py`** — the LLM processor (defaults in `config/models.default.json` §memory_writer; local
  qwen option) that DISTILS every turn into pills; it lives in `nucleo/` (it is write-side brain, not substrate) but
  it is the heart that decides what goes into `memory/`. See §The write HEART.
- **`nucleo/memllm.py`** — the internal per-TASK model router of the memory module (task `rem`, plus `i18n`), config
  `§memory.<task>_*` + key PER ENDPOINT; the memory receives the hook INJECTED (it does not import brains).
- Data: `zaelar.db` (SQLite) in `memory/_data/` (gitignored). Override with `ZAELAR_DB`.
