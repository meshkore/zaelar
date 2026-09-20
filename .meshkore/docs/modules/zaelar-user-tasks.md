# The task — one durable record of a commission

**Modules:** `nucleo/tasks.py` (the decisions) · `memory/tasks_store.py` (the storage) ·
`nucleo/flash/task_recall.py` (finding one again) · `widgets/results/rehydrate.py` (putting it back)
**Tables:** `tasks`, `task_artifacts`, `fts_tasks` (`memory/schema.py`, schema v7)
**Initiative:** V2-728 · **Sibling docs:** `zaelar-workflow-table.md` (a different object with a confusing
name — that one caches WHICH CHANNEL serves a domain; this one is the commission itself).

## What it answers

*«Resérvame hora en un restaurante»* — and then nothing. The operator hands the errand over and stops
carrying it: the counter goes up, the row stays on the board, and if he wants to know how it ended he opens
the list. **Forgetting only works if somebody else remembers**, and before this nobody did for long.

A «process» was five separate stores, none of which was the whole truth:

| # | what | where | durability |
|---|---|---|---|
| 1 | live Brain Workers | `dispatch._SESSIONS`, a RAM dict | **gone on restart** |
| 2 | finished ones | a JSON blob in `sys_kv`, **capped at 50** | fenced by hand against a reset race |
| 3 | third-party errands | the `errands` table | durable, but parallel |
| 4 | crons, one-shots, agenda alerts | `journal` rows | durable, but a different object |
| 5 | the RESULT | a widget sheet, **cap of 8**, pruned by file mtime | **the ninth search deleted the first** |

`/api/tasks` stitched two row shapes by hand, which is how the Processes tab and the Flows board came to
disagree about the same work. And nothing could answer *«de la tarea de buscar piso que te dije antes»*.

## Anatomy

| piece | what it is |
|---|---|
| table `tasks` | one row per commission: `title` · `goal` (his words, verbatim) · `kind` · `mode` · `state` · `visible` · `origin` · `schedule` · `surface`/`sheet` · `parent_id` · `outcome` · four timestamps. |
| table `task_artifacts` | the RESULT, by slot (`result`, `criteria`, `sources`, `process`, `considered`). Outlives the sheet. |
| `fts_tasks` | standalone FTS5 over title+goal, accent-insensitive. The lexical half of finding one again. |
| `nucleo/tasks.py` | the durable id, the state vocabulary, the admission gate, the board, the two mirrors. |
| `memory/tasks_store.py` | storage only. The ONE production importer is `nucleo/tasks.py` (boundary ratchet). |

### Two write rates, kept apart

A task row changes a handful of times in its life — created, started, waiting, finished. The worker's phase,
step and percentage change every second and stay in `dispatch._SESSIONS`, in RAM, where they belong.
`nucleo.tasks.board()` merges the two on read. Nothing here is on the voice path.

### Three vocabularies that do not match, and why the differences matter

- A worker says `queued|running|done|error|cancelled|relevada`; a task says
  `pending|running|waiting|done|failed|cancelled`. **`relevada` maps to `running`**: a relay continues the
  same commission, and painting it «done» for the seconds in between puts a task he is still waiting for in
  the finished list. **`waiting` is not a worker state at all** — it is `waiting_on` being set, and the
  operator needs to see that it is parked on HIS answer.
- An errand says `contacting|negotiating|agreed|gathering`; all of them are `running` from where he sits.
  Which one it is belongs on the row's second line, not in a different answer to «is this still going?».
- A schedule says `once|interval|cron`; `once` is a **scheduled** task and the other two are **recurring**.
  Until they were two lists, «enséñame las tareas programadas» opened the things that repeat.

### The admission gate

`is_visible(kind, src, origin)` — deterministic, by origin and kind, **never a model**: a list whose
contents depend on a classifier is one the operator cannot predict. Internal escalations (memory upkeep,
dev, relays, auto-resume) get a row, for the audit trail, and never the counter. The `⚙ todo` switch in the
tab is the one place they can be seen, which is what a manual test needs and nothing else does.

### One commission, one row, across a relay

`escalate._seq` restarts at 0 in every process, so a `task_id` names a SESSION and never an errand — the
defect `nucleo/runtime_ids.py` exists for, and the one that made a fresh errand land on the previous
session's sheet and delete it (V2-259). The durable id composes `boot_id()`, exactly as `sheets.sheet_id_for`
does, so **the sheet id and the task id are the same string** and the two are joinable by construction.
A relay carries `task_uid` in its escalation context and UPDATES that row instead of opening a second one.

## Finding one again (V2-728 F5)

The operator's rule, INI-027 §7: **an index narrows, a model chooses.**

1. `tasks_store.task_search` — FTS5 over title+goal, OR-matched (a reference is a paraphrase, not a
   quotation), ranked by bm25, ≤5 candidates. **No model, no network.**
2. `jev.select_many` — ONE round trip scoring those against his actual sentence. This is its first
   production consumer; it was built and measured under V2-726 and called by nothing but its own test.
3. **With several equally good candidates, nobody chooses.** Same rule `widgets/directory.py` keeps for
   contacts, and it matters more here: opening the wrong report looks exactly like opening the right one,
   and he would read it before noticing.

A single candidate is taken WITHOUT asking Jev — paying 800 ms to confirm what nothing contradicts is the
call V2-726 was written to stop making.

## Traps

- **`widgets/results/prune_sheets()` is no longer destructive of DATA**, but it still deletes sheets. The
  sheet is a VIEW; `rehydrate.sheet_from_task` rebuilds it from the artifact. Rebuilding is
  **non-destructive**: a sheet that still exists is left alone, because overwriting it would discard
  anything added since the errand closed — the «error de borrar búsquedas» this lineage exists to remove.
- **The task id and the sheet id are the same string on purpose.** If one of the two compositions ever
  changes, the other must change with it or the join silently returns nothing.
- **A test that writes a sheet must patch `widgets.store.DATA_DIR`**, a module constant resolved at import.
  Setting `ZAELAR_WORKSPACE` afterwards reaches nothing, and neither does patching `workspace.root` — both
  LOOK like isolation and leave the test writing into the operator's real `widgets/_data/`.

## What it does NOT do

- **It does not store the DISCARDED candidates.** A worker reports breadth as a count
  (`hbnote considered N --kept M`) and never as rows, so «los 50 que descartó» do not exist to be copied.
- **It does not own the scheduler's storage.** Scheduled jobs stay in `journal` and are MIRRORED here
  (`scheduled_mirrored`, plus `reconcile_board()` at startup). Moving live standing reminders risks the one
  failure nobody notices until the day it fails to sound (V2-121).
- **It does not reach the cloud Master.** `cloud/backoffice/` reads the same `zaelar.db` and still speaks
  the old shape; touching observability is always two places, and only the engine is touched here.
