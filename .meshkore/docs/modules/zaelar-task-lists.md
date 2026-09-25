# Task lists — a message with several tasks in it (V2-771)

> «Tanto si nos las vomita por voz como si nos las pega, el sistema tiene que ver que esto es una acción que para
> completarse necesita realizar todo lo que se pide aquí… y cuando reciba todo esto tampoco tiene que decir
> "he recibido tu tarea de hacer esto, hacer lo otro…". "Vale, entiendo que me pides unas cuantas cosas, me
> pongo a trabajar en ello".» — the operator, 2026-09-25

**Code:** `nucleo/batch/` (`detect.py` · `split.py` · `runner.py` · `__init__.py`) · the lanes
`voice/engine/llm/providers/fast_lane.py::task_list` and `nucleo/flash/probe.py::_task_list` · HTTP
`server/tasks_api.py` (`POST /api/lists`, `GET /api/lists/{uid}`) · boot `server/__init__.py` (resume).
**Tests:** node 4.216 (`tests/agent_headless/unit/test_a_message_with_several_tasks_is_a_list.py`), use cases
`demo-initialization__us` and `long-commission-errands` (scripted, graded on memory, agenda and the task board).

## Why it exists — the measurement

A 12-section setup message (~4 000 chars: the assistant's name, ~40 facts, 7 calendar entries, reminders,
standing rules) was ONE turn. Six limits, each correct for a turn, each dropped part of it without a word:

| Limit | Where | What it lost |
|---|---|---|
| input clamp keeps the LAST 1 600 chars | `voice/attention.py::clamp_input` | sections 1-8 never reached the model |
| memory distiller reads the FIRST 600 chars | `nucleo/mem_processor.py::_MAX_INPUT` | ~35 of ~40 facts |
| 5 widget writes per turn; a 2nd action on one widget refused | `nucleo/flash/data_ops.py` | 2 of 7 entries |
| 1 + 2 escalations per turn | provider / probe | every task past the third |
| 1 200 output tokens | `nucleo/flash/fast_client.py` | trailing tool calls |
| rename lane owns the turn | `fast_lane.rename` | a one-line paste renamed the assistant and dropped the rest |

None of them was wrong. The message was not a turn.

## The mechanism, in the order a message meets it

1. **Is it a list?** `detect.is_a_list`. A SHAPE floor first — length, lines, enumeration, sentences — so an
   ordinary turn pays nothing (below 280 chars the answer is «no» without asking). Past it, ONE Jev Choice
   question (`message_shape`: `single` / `several`, ≥ 0.7 to leave the ordinary turn). No verb table: a list
   looks like a list in every alphabet, and «one detailed request» vs «several things» is exactly the kind of
   judgement a verb table gets wrong both ways. Jev off or failing → only an unmistakable shape (long + three
   enumerated items) counts.
2. **Receipt.** As soon as the verdict is in (~1-2 s) the operator hears ONE line from the lang table
   (`list_started`) — that it is a list and work has started. Never the list read back, no count (the count
   needs the split, and the receipt must not wait ~5 s for it).
3. **Split** (background). `split.split` — one `memllm` call, task `batch_split` (DeepSeek direct, reasoning
   off, `gpt-4.1-mini` stand-in, billed to Energy). Steps are SELF-CONTAINED, first person, in the message's
   language, references resolved, one calendar entry each, ≤ 560 chars (the distiller's window). A step over
   the ceiling is split at sentence boundaries, never cut. Fails open: the message's own numbered sections →
   one step holding the whole message (today's single turn). An acknowledged list is never dropped.
4. **Durable.** `runner.create` writes a visible `tasks` row (`kind="lista"`, the operator's board) and a hidden
   child row per step (`parent_id`). A restart loses nothing: `resume()` at boot re-runs pending steps (and a
   step caught mid-turn, which never reported).
5. **Run.** Each step is an ORDINARY TURN of the text channel — `probe.run_turn(execute=True, lists=False)` —
   with the Jev brief, the real prompt, the model, widgets, memory and workers. So each step sits inside the
   per-turn limits instead of colliding with them. All steps share one conversation session (step 9 is read
   with steps 1-8 behind it). `lists=False` stops a step from being read as a list again.
6. **Memory** is written by the runner, AWAITED, per step — not fire-and-forget: the distiller serialises and
   falls to a lossy heuristic when more than two writes wait (`mem_processor._QUEUE_MAX`), which a list would
   reach in seconds.
7. **Workers.** A step that escalates hands its worker to the pool and the list moves on. The pool is **two**
   at a time (`config/v2.py code_agent.max_parallel`, V2-771; env `CODE_AGENT_MAX_PARALLEL` overrides), the rest
   queue FIFO. The list's report waits for its workers (up to 45 min) — «I've finished» over running work is the
   claim V2-743 forbids — and past that names how many are still running.
8. **Report.** ONE line set via `voice.proactive.notify` (spoken when a voice session is live, a system note
   otherwise): counts, then only what failed, what needs the operator (a step whose turn answered with a
   question), and what is still running. The list closes once reported.
9. **One list at a time.** A second list queues behind the first rather than interleaving steps.

## Entry points

| Channel | Door | Notes |
|---|---|---|
| Voice / typed chat | `fast_lane.task_list`, first lane, before the input clamp and the rename lane | |
| Text channel (`/api/flash/say`) | `probe._task_list`, before `_fast_lanes`, only with `execute` | mirror of the above |
| Anything else authorised by the operator | `POST /api/lists {"text"}` | does not ask «is it a list?» — the caller chose |

## Deliberately out of scope (v1)

- **A spoken list longer than the accumulator valve** (40 words / 1 200 chars) arrives as several turns; each
  is handled as successive requests are today. Joining a dictated list back into one is future work.
- **WhatsApp/Telegram and cluster peers are not command channels.** Messages there are triaged as third-party
  messages or answered by the untrusted cluster brain. Making the operator's own messages an order channel is a
  trust decision, not a code change here; `POST /api/lists` is the door it would use.
- **Per-step verification against the store.** The step's state comes from the turn's own report (executed,
  failed, question, worker). The use cases grade the store; a step-level witness (like `op_receipt`) is open.

## What the list exposed and fixed on the way

- Agenda: `date` + an end date with NO rule and NO weekdays was a WEEKLY series; it is now a daily span
  (`widgets/agenda/recur.py::parse`). A weekly series still names its day or its rule.
- Worker pool default 3 → 2.
