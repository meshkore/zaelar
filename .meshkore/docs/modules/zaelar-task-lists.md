# Task lists — a message with several tasks in it

> Whether the operator dictates it or pastes it, a message that asks for several things is ONE action whose
> completion requires doing everything in it. The agent does not read the list back; it acknowledges that there
> are several things to do and gets to work.

**Code:** `nucleo/batch/` (`detect.py` · `split.py` · `runner.py` · `__init__.py`) · the lanes
`voice/engine/llm/providers/fast_lane.py::task_list` and `nucleo/flash/probe.py::_task_list` · HTTP
`server/tasks_api.py` (`POST /api/lists`, `GET /api/lists/{uid}`) · boot `server/__init__.py` (resume).
**Tests:** node 4.216 (`tests/agent_headless/unit/test_a_message_with_several_tasks_is_a_list.py`), use cases
`demo-initialization__us` and `long-commission-errands` (scripted, graded on memory, agenda and the task board).

## Why it exists

A long setup message (the assistant's name, dozens of facts, several calendar entries, reminders, standing rules)
is not a turn. Every per-turn limit is correct for a turn, and each one would drop part of such a message:

| Limit | Where | What a long message would lose |
|---|---|---|
| input clamp keeps the LAST 1 600 chars | `voice/attention.py::clamp_input` | the opening sections never reach the model |
| memory distiller reads the FIRST 600 chars | `nucleo/memory_agent/processor/distill_prompt.py::MAX_INPUT` | most of the facts |
| 5 widget writes per turn; a 2nd action on one widget refused | `nucleo/flash/data_ops.py` | calendar entries past the cap |
| 1 + 2 escalations per turn | provider / probe | every task past the third |
| 1 200 output tokens | `nucleo/flash/fast_client.py` | trailing tool calls |
| rename lane owns the turn | `fast_lane.rename` | everything after the rename |

None of those limits is wrong. A list is simply run as a sequence of turns, each of which fits them.

## The mechanism, in the order a message meets it

1. **Is it a list?** `detect.is_a_list`. A SHAPE floor first — length, lines, enumeration, sentences — so an
   ordinary turn pays nothing (below 280 chars the answer is «no» without asking). Past it, ONE Jev Choice
   question (`message_shape`: `single` / `several`, ≥ 0.7 to leave the ordinary turn). No verb table: a list
   looks like a list in every alphabet, and «one detailed request» vs «several things» is exactly the kind of
   judgement a verb table gets wrong both ways. With Jev off or unavailable → only an unmistakable shape (long +
   three enumerated items) counts.
2. **Receipt.** As soon as the verdict is in (~1-2 s) the operator hears ONE line from the lang table
   (`list_started`) — that it is a list and work has started. Never the list read back, no count (the count
   needs the split, and the receipt must not wait for it).
3. **Split** (background). `split.split` — one `memllm` call, task `batch_split` (DeepSeek direct, reasoning
   off, `gpt-4.1-mini` stand-in, usage metered via `energy_meter`). Steps are SELF-CONTAINED, first person, in the
   message's language, references resolved, one calendar entry each, ≤ 560 chars (the distiller's window). A step
   over the ceiling is split at sentence boundaries, never cut. Fails open: the message's own numbered sections →
   one step holding the whole message (a single turn). An acknowledged list is never dropped.
4. **Durable.** `runner.create` writes a visible `tasks` row (`kind="lista"`, the operator's board) and a hidden
   child row per step (`parent_id`). A restart loses nothing: `resume()` at boot re-runs pending steps (and a
   step caught mid-turn, which never reported).
5. **Run.** Each step is an ORDINARY TURN of the text channel — `probe.run_turn(execute=True, lists=False)` —
   with the Jev brief, the real prompt, the model, widgets, memory and workers. So each step sits inside the
   per-turn limits instead of colliding with them. All steps share one conversation session (step 9 is read
   with steps 1-8 behind it). `lists=False` stops a step from being read as a list again.
5b. **A step is not believed on its words.** An ACTION step (split kind `agenda`/`reminder`/`message`/`task`)
   whose turn EXECUTED nothing (no tool call, tag, execution, worker or lane action in the turn's own report) is
   retried once in a fresh session, and marked failed if it still does nothing — a «Done» reply with no call
   behind it is not completion. A reply that ends in a question is asked to Jev (`step_reply`: needs an answer vs
   courtesy offer) before the step is left for the operator.
5c. **A step never eats the operator's notes and never claims a refused errand.** It runs with `lists=False`,
   which also stops it draining `brain_notes` (a worker's result or a refusal is for HIS next turn), and an
   escalation the portal refused (id 0) fails the step. A relayed worker (quota → stand-in, new id, same task row)
   is over when its durable row closes, not when its first RAM record does.
6. **Memory** is written by the runner, AWAITED, per step — not fire-and-forget: the distiller serialises and
   falls to a lossy heuristic when more than two writes wait (`mem_processor._QUEUE_MAX`), which a list would
   reach in seconds.
7. **Workers.** A step that escalates hands its worker to the pool and the list moves on. The pool is **two**
   at a time (`config/v2.py code_agent.max_parallel`; env `CODE_AGENT_MAX_PARALLEL` overrides), the rest queue
   FIFO. The list's report waits for its workers (up to 45 min) — «I've finished» is never said over running work
   — and past that names how many are still running.
8. **Report.** ONE line set via `voice.proactive.notify` (spoken when a voice session is live, a system note
   otherwise): counts, then only what failed, what needs the operator (a step whose turn answered with a
   question), and what is still running. The list closes once reported.
9. **One list at a time.** A second list queues behind the first rather than interleaving steps.

The pool limit is enforced by the dispatcher's real semaphore and covered by a unit test (five sessions, never
more than two inside, all five finish).

## Entry points

| Channel | Door | Notes |
|---|---|---|
| Voice / typed chat | `fast_lane.task_list`, first lane, before the input clamp and the rename lane | |
| Text channel (`/api/flash/say`) | `probe._task_list`, before `_fast_lanes`, only with `execute` | mirror of the above |
| Anything else authorised by the operator | `POST /api/lists {"text"}` | does not ask «is it a list?» — the caller chose |

## Scope and extension points

- **A spoken list longer than the accumulator valve** (40 words / 1 200 chars) arrives as several turns; each
  is handled as a successive request. Joining a dictated list back into one is a natural extension.
- **WhatsApp/Telegram and cluster peers are not command channels.** Messages there are triaged as third-party
  messages or answered by the untrusted cluster brain. Making the operator's own messages an order channel is a
  trust decision, not a code change here; `POST /api/lists` is the door it would use.
- **Step state comes from the turn's own report** (executed, failed, question, worker); the use cases grade the
  store. A step-level store witness (like `op_receipt`) would slot in at 5b.

## Related agenda behaviour

`date` + an end date with NO rule and NO weekdays is a daily span (`widgets/agenda/recur.py::parse`). A weekly
series names its day or its rule.
