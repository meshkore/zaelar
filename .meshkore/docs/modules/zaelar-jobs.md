# The JOB — one durable record of a commission

> ⚠️ **Vocabulary.** What this document describes is the work the AGENT does, and its name is a **proceso**
> in Spanish and a **job** in English — never a «tarea». A TASK is the operator's own: a line in one of the
> numbered lists inside his agenda widget (`zaelar-agenda-task-lists.md`). Keeping the two names apart is not
> cosmetic: if the ChatWall tab's id were `tareas`, «ábreme las tareas», routed correctly by every layer,
> would open the agent's job list instead of his shopping list.
>
> The CODE still says `tasks` throughout (`nucleo/tasks.py`, the `tasks` table, `/api/tasks`): renaming a
> schema and its API to follow a label is churn with a migration attached, and the vocabulary rule is about
> what the operator READS.


**Modules:** `nucleo/tasks.py` (the decisions) · `memory/tasks_store.py` (the storage) ·
`nucleo/turn/task_recall.py` (finding one again) · `widgets/results/rehydrate.py` (putting it back)
**Tables:** `tasks`, `task_artifacts`, `fts_tasks` (`memory/schema.py`, schema v7)
**Sibling docs:** `zaelar-workflow-table.md` (a different object with a confusing name — that one caches WHICH
CHANNEL serves a domain; this one is the commission itself).

## What it answers

*«Resérvame hora en un restaurante»* — and then nothing. The operator hands the errand over and stops
carrying it: the counter goes up, the row stays on the board, and if he wants to know how it ended he opens
the list. **Forgetting only works if somebody else remembers**, and the job record is that somebody.

A commission touches several kinds of state, and the job row is the one place that holds the whole truth
about it:

| what | where it lives | how the job relates to it |
|---|---|---|
| live Brain Workers | `dispatch._SESSIONS`, a RAM dict | merged into the board on read |
| third-party errands | the `errands` table | mirrored onto the job row |
| crons, one-shots, agenda alerts | `journal` rows | mirrored onto the job row |
| the RESULT | `task_artifacts` | durable, independent of any widget sheet |

So the Processes tab and the Flows board read ONE row shape, and *«de la tarea de buscar piso que te dije
antes»* has something to resolve against.

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
  They are two lists, so «enséñame las tareas programadas» never opens the things that repeat.

### The admission gate

`is_visible(kind, src, origin)` — deterministic, by origin and kind, **never a model**: a list whose
contents depend on a classifier is one the operator cannot predict. Internal escalations (memory upkeep,
dev, relays, auto-resume) get a row, for the audit trail, and never the counter. The `⚙ todo` switch in the
tab is the one place they can be seen, which is what a manual test needs and nothing else does.

### One commission, one row, across a relay

`escalate._seq` restarts at 0 in every process, so a `task_id` names a SESSION and never an errand — the
reason `nucleo/runtime_ids.py` exists: without a boot-scoped id, a fresh errand could land on the previous
session's sheet and overwrite it. The durable id composes `boot_id()`, exactly as `sheets.sheet_id_for` does,
so **the sheet id and the task id are the same string** and the two are joinable by construction. A relay
carries `task_uid` in its escalation context and UPDATES that row instead of opening a second one.

## Finding one again

The rule: **an index narrows, a model chooses.**

1. `tasks_store.task_search` — FTS5 over title+goal, OR-matched (a reference is a paraphrase, not a
   quotation), ranked by bm25, ≤5 candidates. **No model, no network.**
2. `jev.select_many` — ONE round trip scoring those against his actual sentence.
3. **With several equally good candidates, nobody chooses.** Same rule `widgets/directory.py` keeps for
   contacts, and it matters more here: opening the wrong report looks exactly like opening the right one,
   and he would read it before noticing.

A single candidate is taken WITHOUT asking Jev — paying a model round trip to confirm what nothing
contradicts buys nothing.

## Traps

- **A LIVE errand's sheet is never pruned**, whatever its age. Recency is a proxy for «still in use» and
  this is where the proxy is wrong: a worker three hours into a hard errand while the operator runs a dozen
  quick searches beside it. There the sheet is not a view but the box the worker is WRITING INTO, and its
  snapshot does not exist yet because the errand has not closed. `prune_sheets` asks the task table.
- **`widgets/results/prune_sheets()` never destroys DATA**, but it still deletes sheets. The sheet is a VIEW;
  `rehydrate.sheet_from_task` rebuilds it from the artifact. Rebuilding is **non-destructive**: a sheet that
  still exists is left alone, because overwriting it would discard anything added since the errand closed.
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

The pill is what lets «¿encontraste algo de pisos?» — a question that never says *tarea* — retrieve the errand
that went and found flats, not just the conversation about them. It is a NORMAL pill: the writer embeds it and
derives its graph edges with the same deterministic `derive_concepts` backstop every durable pill gets, so
linking the job to what it touched is that edge set and not a bespoke join. `meta.task_id` is what makes it
actionable rather than merely readable — and it is a field rather than an `edges` row because an edge joins
two MEMORY ids and a task is not one.

It SUPERSEDES its own earlier chapters (`memory.api.task_trace_ids`): a commission can close more than once
— a relay hands the baton back, a re-dispatch reopens it — and without the chain recall would serve
«terminó sin encontrar nada» beside «encontró 5 pisos» for the same errand, with no way to tell which is
current.

## Getting the report back onto the screen

Two doors, one mechanism (`widgets/results/rehydrate.sheet_from_task`, idempotent):

- **Voice** — `reopen_task` → `nucleo/turn/task_recall.py`. Index narrows to ≤5 without a model, Jev
  chooses among those, and with several equally good candidates it ASKS.
- **The button** — a finished row in «Hechas» draws «Ver resultados» when the board says `has_results`
  (one `task_artifacts` lookup per finished row; a button that opens nothing is worse than no button).
  It calls `POST /api/tasks/reopen`, which rebuilds the sheet if it has to and then emits the same
  `widget/show` the brain emits — so the card appears through the ONE door every card uses, reaches the
  mobile shell too, and lands on the observability timeline.

## The discarded ones

A search that returns the best five also keeps the ones it discarded, linked to the job, so «¿y por qué no
este?» always has an answer.

Getting the rows is a matter of **what the worker REPORTS**, not of where anything is stored: the results
sheet has a `rejected` action (`{title, url, why, source}`, reported as it goes, deduped on url-or-title)
and the research brief asks for it by name. `why` is mandatory — a list of names with no reasons is not an
audit, it is a longer list. They ride to the task in the `considered` artifact alongside the breadth, and
come back with the report when it is rebuilt. They never enter the results LIST: the list is the selection,
and a rejected candidate on it is the confusion the worker guide exists to prevent. They render in the
Summary tab, under the count.

## The calendar sees the system's own work

A job scheduled for later («la semana que viene, haz esto…») is visible in the agenda, even though it is work
for the system rather than for the operator. `widgets/agenda/data.py::_system_tasks` READS `mode IN
('scheduled','recurring')` and paints each one at its next moment, dotted and in its own hue — never as a
meeting, because nobody is meeting anybody.

The filter is `origin != 'agenda'`, and it is the whole subtlety: every appointment schedules its own notice
(`reminders._schedule_reminder`), which is a scheduled task like any other and would put a second mark on
the calendar for a meeting already on it. `scheduler.create(origin=…)` is what carries that distinction.

## Boundaries

- **It does not own the scheduler's storage.** Scheduled jobs stay in `journal` and are MIRRORED here
  (`scheduled_mirrored`, plus `reconcile_board()` at startup), so a standing reminder keeps the storage that
  fires it.
