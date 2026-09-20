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
| table `task_artifacts` | the RESULT, by slot (`result`, `criteria`, `sources`, `process`, `considered` — the last one carries the breadth AND the rejected rows). Outlives the sheet. |
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

- **A LIVE errand's sheet is never pruned**, whatever its age. Recency is a proxy for «still in use» and
  this is where the proxy is wrong: a worker three hours into a hard errand while the operator runs a dozen
  quick searches beside it. There the sheet is not a view but the box the worker is WRITING INTO, and its
  snapshot does not exist yet because the errand has not closed. `prune_sheets` asks the task table.
- **`widgets/results/prune_sheets()` is no longer destructive of DATA**, but it still deletes sheets. The
  sheet is a VIEW; `rehydrate.sheet_from_task` rebuilds it from the artifact. Rebuilding is
  **non-destructive**: a sheet that still exists is left alone, because overwriting it would discard
  anything added since the errand closed — the «error de borrar búsquedas» this lineage exists to remove.
- **The task id and the sheet id are the same string on purpose.** If one of the two compositions ever
  changes, the other must change with it or the join silently returns nothing.
- **A test that writes a sheet must patch `widgets.store.DATA_DIR`**, a module constant resolved at import.
  Setting `ZAELAR_WORKSPACE` afterwards reaches nothing, and neither does patching `workspace.root` — both
  LOOK like isolation and leave the test writing into the operator's real `widgets/_data/`.

## Reaching it without the task table

A closed commission also writes ONE memory pill: `[task:<uid>] El encargo «…» terminó el <fecha>. Resultado:
…`. The two records answer different questions, and only one of them is ever asked mid-sentence:

| | question | when it runs |
|---|---|---|
| `task_search` (FTS5) | «which task do these WORDS name» | only once he has said he means a task |
| recall (the pill) | «what do I know that bears on what he just said» | every turn, unasked |

Before the pill, «¿encontraste algo de pisos?» — a question that never says *tarea* — retrieved the
conversation about flats and not the errand that went and found five. The pill is a NORMAL pill: the writer
embeds it and derives its graph edges with the same deterministic `derive_concepts` backstop every durable
pill gets, so «que todo eso quede vinculado» is that edge set and not a bespoke join. `meta.task_id` is what
makes it actionable rather than merely readable — and it is a field rather than an `edges` row for the
honest reason that an edge joins two MEMORY ids and a task is not one.

It SUPERSEDES its own earlier chapters (`memory.api.task_trace_ids`): a commission can close more than once
— a relay hands the baton back, a re-dispatch reopens it — and without the chain recall would serve
«terminó sin encontrar nada» beside «encontró 5 pisos» for the same errand, with no way to tell which is
current. That is V2-577's failure with a different prefix.

## Getting the report back onto the screen

Two doors, one mechanism (`widgets/results/rehydrate.sheet_from_task`, idempotent):

- **Voice** — `reopen_task` → `nucleo/flash/task_recall.py`. Index narrows to ≤5 without a model, Jev
  chooses among those, and with several equally good candidates it ASKS.
- **The button** — a finished row in «Hechas» draws «Ver resultados» when the board says `has_results`
  (one `task_artifacts` lookup per finished row; a button that opens nothing is worse than no button).
  It calls `POST /api/tasks/reopen`, which rebuilds the sheet if it has to and then emits the same
  `widget/show` the brain emits — so the card appears through the ONE door every card uses, reaches the
  mobile shell too, and lands on the observability timeline.

## The discarded ones

«Me encuentra los 5 mejores y otros 50 que ha descartado, pues todo eso tiene que quedar vinculado.» Until
V2-728 a rejection survived only as a COUNT, so «¿y por qué no este?» had no answer anywhere in the system.

Getting the rows was a change to **what the worker REPORTS**, not to where anything is stored: the results
sheet gained a `rejected` action (`{title, url, why, source}`, reported as it goes, deduped on url-or-title)
and the research brief asks for it by name. `why` is mandatory — a list of names with no reasons is not an
audit, it is a longer list. They ride to the task in the `considered` artifact alongside the breadth, and
come back with the report when it is rebuilt. They never enter the results LIST: the list is the selection,
and a rejected candidate on it is the confusion the worker guide exists to prevent. They render in the
Summary tab, under the count that was already there.

## The calendar sees the system's own work

«Si te digo la semana que viene, haz esto… se puede ver perfectamente en la agenda, aunque es una tarea no
para nosotros, sino para el sistema.» `widgets/agenda/data.py::_system_tasks` READS `mode IN
('scheduled','recurring')` and paints each one at its next moment, dotted and in its own hue — never as a
meeting, because nobody is meeting anybody.

The filter is `origin != 'agenda'`, and it is the whole subtlety: every appointment schedules its own notice
(`reminders._schedule_reminder`), which is a scheduled task like any other and would put a second mark on
the calendar for a meeting already on it. `scheduler.create(origin=…)` is what carries that distinction.

## What it does NOT do

- **It does not own the scheduler's storage.** Scheduled jobs stay in `journal` and are MIRRORED here
  (`scheduled_mirrored`, plus `reconcile_board()` at startup). Moving live standing reminders risks the one
  failure nobody notices until the day it fails to sound (V2-121).
- **It is not on the cloud Master.** `cloud/backoffice/` reads `events` and `sys_kv` from the same
  `zaelar.db` and is unaffected by any of this — it never read the retired worker ledger. Showing the task
  board there is a new screen, not an alignment fix.
