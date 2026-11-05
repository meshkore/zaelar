---
title: Zaelar — Brain Worker doctrine (harden the resources, open the reasoning)
category: architecture
updated: 2026-11-05
owner: ricart
status: current
---

# Brain Worker doctrine

> **The rule, in one sentence.** Zaelar's agent must be able to resolve *any* errand the operator brings, so we
> harden the **resources** it works with and we keep the **reasoning** open. A fix that makes one scenario pass
> is worth nothing if changing a word in that scenario breaks it.

This is the doctrine every change to the worker side has to be oriented by. It is not a description of what
exists; it is the criterion for deciding whether a change is the right one.

---

## 1. What "any errand" means

Not a taxonomy. The operator's own list, kept verbatim because its breadth is the point:

- book a hotel or a restaurant table;
- run a research project on 2nd-century-BC Greek culture;
- draw the plans or the task list for building a rocket;
- invent a book;
- search Wallapop for a vehicle;
- search for houses around Los Angeles, on whatever sites are popular *there*, starting with the most popular.

There is no list of supported errands and there must never be one. The agent has to be a **flexible system that
can learn and experiment**: given a goal, it finds the formula that reaches the result the operator expects.

## 2. The split: two halves, opposite treatments

| | **RESOURCES** — the core | **REASONING** — the errand |
|---|---|---|
| What | Browser control, real-time data reaching the worker, parsing, screenshots, bridges, evidence, delivery | Planning, research, judgement, method, "how do I get to what he asked for" |
| Goal | **Correct, complete, proven.** Zero surprises. | **Open, general, discoverable.** Room to experiment. |
| Shape of a good change | A mechanism that works for every errand and is covered by tests | A broader prompt: formulas, resources, ways of solving — never a script |
| Failure we accept | None. A broken resource is a bug. | An errand solved by an unexpected route is a *success*, not a deviation |

Read the table as an instruction: **when something goes wrong, first ask which half it went wrong in.** A
resource defect very often wears the costume of a reasoning defect.

## 3. Why fitting the use case is a regression

A fix shaped like one scenario buys one green run and sells the next one. The deeper cause is almost never
scenario-shaped, which is why the resource-level fix is the one to build. Typical patterns:

- **A worker spending its budget learning its own CLI by trial and error.** The scenario-shaped fix is "make
  `scroll down` work". The resource fix is: every bridge prints the signature it expects and its errors name the
  right verb. The second one helps an errand nobody has written yet.
- **A composer that reads a provider chain but never writes to it**, so its relay cannot fire. That is not a
  hotel problem — it affects every errand that needs to search anything.
- **Findings that never reach anyone** — extracted, printed to the worker's stdout, gone. That is a transparency
  problem, and it affects every errand.
- **Delivery path matters.** A fact **pushed** as a system note is acted on in the next turn far more reliably
  than the same fact **rendered** as a prompt status line. That is a property of every message the system ever
  needs to get to the operator.

In each case a scenario-shaped fix would have hidden the real cause.

### The test to apply to any fix

Before writing it, answer these. If any answer is "no", the fix is aimed at the wrong half.

1. **Change a word in the errand — does it still hold?** Hotel → restaurant, Sevilla → Los Angeles, "4 stars" →
   "under 80 €", Spanish → English. If the fix only survives the sentence it was written for, it is scaffolding.
2. **Does it help an errand nobody has written yet?** A rocket task list, a book outline, a Wallapop search.
3. **Is it a resource, or is it a formula?** Resources get code and tests. Formulas get prompt breadth — and the
   prompt must offer *ways of solving*, not steps to follow.
4. **Would a person with these tools have managed?** If yes and the agent did not, the missing piece is
   information or capability, not instruction.
5. **Is any new hard-coded knowledge a STARTING POINT or a FENCE?** (see §5)

## 4. What the resources have to guarantee

This is the half that must be nailed down and kept tested. The contract, in the order the worker meets it:

**Drive the browser like a person.** `widgets/navegador/act_api.py` exposes `snapshot · look · navigate · click ·
type · select_option · scroll · press · click_at · type_at · extract`. `nucleo/cli/nav.py` is the CLI the worker
actually types. Both must be self-describing: a worker that has to *guess* a signature is spending the operator's
errand on our documentation.

**Tell the worker what stopped it, in real time.** Every response is annotated with the two facts that change
what to do next: `wall` (the page blocked us — anti-bot, CAPTCHA, "too many requests") and `stalled_s`/`hint`
(this page has not moved in N minutes). A field that is annotated and not printed is a fix that dies one line
short of its reader.

**See the page.** `look` writes a fresh viewport capture and hands back an absolute path the worker may `Read`.
The path is only advertised when the PNG is really there — advertising a file that does not exist sends the
worker to read nothing and blame itself.

**Parse what comes back, and never lose the tail.** `extract` returns structured listings. Evidence is clipped by
`observability/evidence.py`, whose own doctrine is *"we clip, we do not summarise"* and *"never lose in silence
the information that there was more"*. A clip that breaks a JSON list is not a clip — the reader discards the
whole list, and since ads come first and answers come last, the truncation eats the answer by construction.

**Hand findings over the moment they exist.** Whatever the browser extracts goes to the results sheet and onto the
task's row immediately — not at the end of the session, and not only into the worker's own transcript. Every act
through the bridge records its artefact on the row at the door (`nucleo/workers/task_files.py`), so the worker cannot
produce a deliverable that is not recorded. Facts are recorded; what is said to him goes through the one mouth.

**Keep the operator's picture true.** A task that is retrying itself is not a dead task; a dead task is said once
and then stops being announced without stopping being true.

> **The invariant behind all of it:** the worker and the operator must both be able to see what actually
> happened. Every defect in this half looks the same from outside — the system *did* the work and nobody could
> tell.

## 5. The task's frame: one worker, one row, one playbook

The reasoning is open; the FRAME it runs in is fixed, the same for every errand (criteria §4b):

- **One request = one worker session, resumable by id.** The task's row (`tasks`) is the truth — what it waits for,
  its open question, `session_id` and `cwd`, its playbook; the session is a cache. The worker never keeps task state
  only in its head, never speaks on its own channel and never closes its task.
- **Ask → end the turn → resume by id.** When a fact is missing or a door asks for consent, the worker calls `ask`
  through the bridge (one question, every candidate named). The question becomes durable on the row with an `ask_id`
  and goes on his screen; the worker's process ENDS. His answer — by screen with its `ask_id`, or by voice bound by the
  brief's verdict — relaunches THAT session by id in its stored cwd, and its first message is a re-brief built from
  the row (where it was, what it waited for, the question and his answer). A restart changes nothing: the row is still
  waiting. A worker that dies without finishing is resumed by id once.
- **Verify, never declare.** The worker asks `verify` through the bridge and gets the circuit's verdict against the
  task's `done_when`; `circuit.settle` writes the ending. A worker's own «done» proves nothing.
- **The playbook** (`nucleo/workers/prompts/playbook.py`) is the method given with the brief, in the session's
  language: understand → record → resolve the facts → choose channel and UI → compose → confirm → act → verify →
  report, with a bounded number of attempts per checkpoint (then `ask` or fail with the reason, never a silent retry).
  Which playbook (`errand`, `message`, `document`, `lista`) is read from facts the engine has — the surface, the
  mandate, the request's shape — never from words of the request. His rules are DATA in the brief; the door is their
  only authoritative reader.
- **The bridge's catalogue** (`nucleo/workers/prompts/catalog.py`) has two layers: the brief carries one headline per
  family (browser, network, sites, widgets, results, library, third parties, decide, method, messaging, schedule,
  rules); a family's full text comes on request — `python -m nucleo.cli.bridge catalog <family>`, read locally. A brief
  over its measured ceiling is a defect: model time is most of a worker's wall, and the first request is the slowest.
- **The internal API is the worker's only hands.** Everything it does to the agent goes through the bridge
  (`/api/worker/act`, per-task token) to the same doors Flash uses, consent inside each door; a session that read a
  stranger's text is tainted and its exits ask him.

## 5b. What the reasoning half is allowed to look like

The worker prompt (`nucleo/workers/prompts/`) is where breadth lives, and it must stay **method, not script**:

- The `method` family (`prompts/context._METHOD_BLOCK`) — understand (including the implicit constraints) → plan and
  recall → act where it truly lives → reflect it in the widgets → **verify for real** → iterate until certified.
  Generalises because it names no domain. A widget with a connector IS the source (the agenda IS the calendar,
  messaging IS the outbox), so a cita or a message is created/cancelled/sent WITH the widget (`nucleo/cli/widget`),
  never by driving its web; only a commitment made on a SITE with no connector (a booking, a subscription, a payment)
  is done there and then reflected.
- The `browser` family (`prompts/drawer._HUMAN_NAV_GUIDE` with the driving and method blocks of `prompts/web.py`) —
  human rhythm, use the site's own search and filters, accept cookies, scroll gradually, back off from anti-bot walls
  instead of hammering. Also domain-free.
- `nucleo/workers/brief.py` — the brief *directs* an investigation (breadth floor, hard vs soft criteria, a scoring
  rubric) instead of prescribing where to look. Direction generalises; itineraries do not.

### Starting points, not fences

`nucleo/flash/site_catalog.py` is the sharp edge of this doctrine, and it is worth being explicit about it. Naming
a trusted site per category is legitimate **as a starting point**: it saves the worker a decision it was making
badly. It would become a fence the moment an errand outside the catalog got *less* capability than one inside
it — for example, a category that `category_of` does not detect must still have a real path when it hits a
wall.

So the rule for any hard-coded knowledge about the world:

- it may say **"start here"**; it may never say **"only here"**;
- the path for an errand with **no** entry must be a real path, not an absence — "try another site" without
  naming one is a wish, not an instruction;
- and the *general* capability (find the popular sites for this domain and locale, then work them) is the thing
  worth building. The catalog is a cache of that capability, not a substitute for it.

The operator's own example is the measuring stick: *houses around Los Angeles, on whatever sites are popular
there, starting with the most popular*. No catalog we write will contain that. The agent has to be able to find
it.

## 6. Instruction design

Instructions to the brain are part of the reasoning half, and they have their own rule:

**One instruction per block.** If the state changes the order, split the *faces* of the block and
give each turn exactly one — and the fact that decides which face is **counted in code**, never inferred by the
model from the conversation window. Two orders in one sentence resolve by coin flip — the same instruction can
produce a broken record on one run and total silence on the next, and a block with three clauses may be obeyed
only in its middle clause.

And when splitting: **silencing the repetition is not silencing the state.** The face that stops announcing must
keep forbidding the reassuring phrase, or fixing the broken record reopens the silence.

## 7. How this changes what you do next

When a use case does not resolve:

1. Read what actually happened — the worker's stream and the **whole** system prompt of the turns, not the line
   you went looking for. A prompt that argues with itself is invisible otherwise.
2. Classify: **resource** or **reasoning**?
3. If resource → fix the mechanism for *every* errand, and add the test that would have caught it.
4. If reasoning → widen the method, the formulas, the ways of solving. Do not encode the scenario.
5. If you cannot tell → treat it as a resource problem until proven otherwise.

**Never** close a round by teaching the system the answer to that round.
