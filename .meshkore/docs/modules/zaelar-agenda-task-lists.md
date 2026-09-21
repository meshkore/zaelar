# The agenda's TASK LISTS — the operator's own, numbered so he can speak them

**Modules:** `widgets/agenda/tasklists.py` (the model and every verb) · `widgets/agenda/when.py` (a spoken
date or hour) · `widgets/agenda/planner.py` (what may be placed in a day) · `widgets/agenda/index.py` (what
the brain reads) · `widgets/agenda/widget.js` (the section)
**Store:** the agenda widget's own isolated file, `db["taskLists"]` + `db["tasks"]`, schema **v2**
**Initiative:** V2-744 · **Sibling doc:** `zaelar-jobs.md` — the other thing that used to be called a
«tarea», and is not one.

## The vocabulary, because it is the whole point

The operator, 2026-09-21: *«a las tareas que yo hago las llamo **procesos** (jobs en inglés) y las separo
de las **tareas personales del operador**, que van en su agenda»*.

| | what it is | where it lives | how it is opened |
|---|---|---|---|
| **tarea / task** | something HE has to do | a numbered list in the agenda widget | `agenda:show_tasks` |
| **proceso / job** | something the AGENT is doing for him | the `tasks` table, the wall's Procesos tab | `show_panel` |

## What the card holds

A selector at the very top of the agenda — **Agenda | Tareas** — and the tasks half is his:

- a built-in **General** list (where anything with no list named lands) plus any list he creates;
- every list numbered **1, 2, 3…** in screen order, with `done/total` and a progress bar;
- every item numbered **1, 2, 3…** inside its list, with an optional day and hour;
- the list's **identifier** on screen (`tl_la_compra`) — a readable slug, because it is what he will hand
  to another agent over the MeshKore cluster and he will read it aloud.

## The three decisions, and what each one is protecting

### 1 · ONE array, not two

A list item and a planner task are both «something the operator has to do», so they share `db["tasks"]` and
a task carries the `listId` it hangs from. A second array for the new section would be the
two-writers-of-one-fact defect this widget already has a monument to — the header of `system_tasks.py`
(«THE AGENDA READS, IT DOES NOT DUPLICATE») was written about the same mistake one surface over.

Migration is lazy (`DB_VERSION` 1 → 2) **and** defensive on every read of the lists: a task written by an
older build has no `listId`, and a section built around lists would have shown an empty screen — data loss
wearing the face of a fresh start.

### 2 · The planner places only what says how long it takes

`tasklists.plannable(t)` = a duration, an hour, or a project. Before V2-744 `plan_day` read
`int(t.get("estimateMinutes", 30))`, so **anything without a duration was scheduled as half an hour**. That
was invisible while every task came from the coach; with a shopping list in the same array it becomes
visible immediately — «Pan» takes the 9:00 slot and «Leche» the 9:30.

It is not a special case for lists. It is V2-652's rule — *a missing fact is a fact, not a slot for a
default* — applied to the one field the planner cannot work without. A task that DOES declare
`estimateMinutes` is still planned exactly as before.

### 3 · The number is the screen position and nothing else

He asked for numbering so he can say «la lista número 3, el ítem número 2». A number stored on the row
would drift from what he is reading the moment anything is deleted, so `no` is **derived on every read** —
and `tasklists.digest()`, what the brain sees, is built by the same function the render reads.
`index.py` exists because two views of one card once disagreed about what «next» meant; building the second
view out of the first is the fix that nobody has to remember.

## Driving it by voice

| He says | What runs |
|---|---|
| «ábreme las tareas» · «la lista de la compra» · «la lista 3» | `show_tasks` — `view: true`, so the card comes up AND the section opens |
| «hazme una lista de la compra» | `add_list` |
| «apúntame comprar pan» · «añade leche a la compra» | `add_task` (no list named → General) |
| «marca hecha la 2 de la compra» | `done` |
| «cambia el ítem 2 por huevos camperos» · «pásalo a la lista de casa» | `update_task` |
| «borra el ítem 2» | `delete_task` |
| «vacía la compra» · «borra esa lista» | `clear_list` / `delete_list` — both confirm |
| «renombra la lista 2» | `rename_list` |

### How a reference is resolved

`tasklists.pick_list` / `pick_task`, in this order: the **id** (what `widgets/refs.py` writes into the key
the manifest's `ref` names) → an **ordinal** → the **name**, exact then prefix then substring then token
overlap. Two candidates are a QUESTION, never a guess — the rule `refs.py` already follows.

An ordinal counts only when the number is ALL that is left after the filler words: «el ítem 2» is a
position, «comprar 2 barras de pan» is a title with a digit in it, and reading the second as a position
would act on a row he never mentioned.

### What refuses, and why

- `clear_list` / `delete_list` with an **empty selector** are refused twice over: by `contract.guard`
  through the manifest's `ref`, and again next to the write. `pick_list` falls back to the open list by
  design — right for «añade pan», wrong for «vacíala», where the fallback would empty whatever happened to
  be on screen.
- **General is never deleted, only emptied.** It is where a task with no home lands; removing it would
  leave the next `add_task` writing into a list that does not exist.
- A number that is not there comes back naming what IS there («la lista tiene 3: 1. Pan; 2. Leche…»), so
  the model's retry has something to aim at.

## The seams a change has to keep in step

| If you touch | Also check |
|---|---|
| the numbering | `tasklists.items()/lists()` — the render, `digest()` and `ref_rows()` all read them |
| a new verb | the manifest (undeclared = invisible to the brain; declared and unhandled = the gate rejects it) |
| a destructive verb | its `ref`, and the census in `test_a_destructive_action_needs_a_selector` |
| `whenToUse` | it must stay under `brief._PURPOSE_CAP` (300) or the routing line is cut before the model reads the boundary |
| the store shape | `DB_VERSION` + `_migrate`, and `tasklists.migrate`'s defensive pass |

## Tests

| Node | What |
|---|---|
| 4.200 | the model: lists, numbering, every verb, the refusals, the migration, the planner boundary |
| 4.201 | RENDERED in Chromium: the selector, the numerals, the progress bar, every gesture reaching its declared action, the pushed view, and titles staying TEXT |
| 8.10 | the vocabulary ratchet: no frontend label calls the agent's work a «tarea» |
