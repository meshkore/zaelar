# Criteria — the standing rules of the engine

**What this is.** The rules the engine obeys TODAY, one line each, and nothing else: no history, no incident
narrative, no superseded version. When a rule changes, its line changes here and the old text is gone — the
story of how it changed is the diary's job (`.meshkore/docs/decisions.md`, then `decisions-archive.md`). An
agent that has read this file knows what the engine must do; an agent that wants to know why reads the diary.

**How to read a line.** `CRIT-<group><n>` · the rule · `— since <date> · nodes <ids>` where the ids are nodes
of `tests/run_testmap.py` that guard it, and, when it helps, the code seam that implements it. A line marked
`⚠ sin test` names a rule nobody guards yet; it is a debt, not a decoration.

**How to change one.** Edit the line (never append a second line on the same topic), move the date, cite the
node of the test that proves the new behaviour, and write the WHY as a diary entry. The ratchet
(`tests/infrastructure/unit/test_the_criteria_are_one_and_current.py`) keeps every line dated and tested and
the contradictions table empty.

**The base, above all of these:** `.meshkore/context/principles.md` — mechanisms, not rules. A change that
bounds a CONSEQUENCE is a mechanism and stays; one that bounds JUDGEMENT is a rail and goes. Every criterion
below is the first kind, or it names the mechanism that replaced the second.

---

## 1 · What the mouth says (voice)

- **CRIT-V1 · One short line at most.** An order that ran says at most one short line: the model's own, or
  «Done.» / «Here it is.» when the model said nothing. A spoken rule turns the ack off («no me confirmes las
  órdenes») and a retraction restores it. — since 2026-09-29 · nodes 3.22, 2.50, 3.97 · `nucleo/genesis.json`,
  `nucleo/style_policy.py`, the ack backstops in `voice/engine/llm/providers/nucleo.py`.
- **CRIT-V2 · A repaired act is said after the words only when the words DENIED it** (or asked a question, which
  gets «I've gone ahead»); a claim or a promise in any language needs nothing after it. — since 2026-09-29 ·
  nodes 2.89, 2.154 · `nucleo/flash/act_repair.after_the_repair`.
- **CRIT-V3 · A «yes» is answered with a START, never with a completion.** The outcome is reported when the work
  settles (`op_receipt`), witnessed against the widget's own view; a pool timeout is not an outcome; an op that
  could not start or whose dispatch raised is said as not done, never left behind «Done.». — since 2026-09-30 ·
  nodes 2.17, 3.35, 2.201.
- **CRIT-V4 · Fillers are «smart».** A wait cover sounds only on a turn that thinks (a question, real work), never
  on a short order; a cover describes motion and never ends the turn; a promise to look with nothing behind it is
  withdrawn. — since 2026-09-17 · nodes 2.50, 2.164, 3.58 · `voice/engine/core/filler_audio.py`,
  `nucleo/flash/answer_guards.py`.
- **CRIT-V5 · A claim is not a fact.** A delivery claimed over an empty sheet becomes a follow-up; «still on it»
  is said only about live work on THIS request; a result already spoken is not news on the next turn. — since
  2026-09-19 · nodes 3.35, 2.102, 2.86.
- **CRIT-V6 · The agent's language, always.** Every spoken line is in the agent's language; an internal system
  note never sets the reply language; a stage direction the model writes is not read aloud. — since 2026-09-26 ·
  nodes 2.129, 2.123, 2.152, 2.160.
- **CRIT-V7 · The chat wall is the conversation.** A voice line is written when the mouth STARTED it
  (`bot_speech speaking`), never when generated; its identity is the turn's trace, not its position; a held
  fragment is glued to the next only if the next continues it. — since 2026-09-22 · nodes 4.210 ·
  `nucleo/flash/continuation.py`.
- **CRIT-V8 · The assistant's own name changes by a verdict, never by a regex, and fails CLOSED** (absent or
  unsure → no rename). — since 2026-09-22 · nodes 2.56.

## 2 · Consent — act or ask

- **CRIT-C1 · One consent rule.** A missing datum → ask for the DATUM; a doubt between two → ask which; a radius
  → ask; otherwise act. Genesis asks at `critical`; a spoken rule moves it («pregúntame siempre antes» → sensitive,
  «hazlo directamente» → critical) in both channels; a negation that governs «sin preguntar» / «without asking»
  in its own clause is MORE friction («nunca envíes un correo sin preguntarme» → sensitive). — since 2026-09-17,
  spoken rule 2026-09-30 · nodes 4.188, 4.185, 2.174, 2.199 · `nucleo/consent.py`.
- **CRIT-C2 · A «yes» answers ONE proposal** and spends only that proposal's authority; an order that starts with
  «ok» is not a yes to a different pending action; every pending confirmation can be answered in words. — since
  2026-09-18 · nodes 2.29, 2.156, 2.125.
- **CRIT-C3 · The agenda goes DIRECT.** Deleting or adding an item never asks; a bounded trash and `restore` put
  the row back in its slot; sweeps (clear or delete a list, clear all or a range) still ask. A row's content is
  never an order («add a task: buy bread» buys nothing) — the danger gate is repaired by SUBTRACTING, never by
  adding a pattern. — since 2026-09-21 · nodes 4.206, 4.188, 2.67 · `widgets/agenda/data.py`, `nucleo/danger.py`.
- **CRIT-C4 · Building or rewriting a card of his asks first**, at the one door a worker is lit
  (`dispatch._run_session`, `kind == code`); the cluster dev-worker is exempt. — since 2026-09-23 · nodes 2.76.
- **CRIT-C5 · An act that LEAVES runs only when the verdict backs it.** A send or a forward (≥ sensitive) runs
  when the verdict does not name another action; unbacked, it is DROPPED with a note to the model — never turned
  into a question, because the next «ok» would answer it. — since 2026-09-29 · nodes 2.106, 2.168.
- **CRIT-C6 · An action does not manufacture permission for its own side effects**; the confirm gate asks
  SOMEONE, and its «yes» returns to the click it stopped. — since 2026-09-18 · nodes 4.21, 2.29.
- **CRIT-C7 · A transactional op never enters the task list** (deleting an item, sending a message); the list is
  for work that takes time and that he may come back to. — since 2026-09-21 · nodes 3.82.
- **CRIT-C8 · A search is never gated as a charge.** A negated act («do not buy») and a first-person wish beside
  a lookup order («I want to buy X, give me the link») are subtracted before the money verbs are read — a
  negation only subtracts the act it governs, inside its own clause («don't forget to pay», «no compres el barato,
  compra este» still park); the pay click is where money stops. The core guard reads whole words only. — since
  2026-09-30 · nodes 2.181, 2.200, 3.29 ·
  `nucleo/danger.py`, `nucleo/protected_core.py`.

## 3 · The canvas — whose card, what runs

- **CRIT-K1 · A verb table is not a router.** A grammar may PROPOSE (free, instant); the decision model chooses
  among DECLARED options; a backstop never contradicts a verdict already paid. — since 2026-09-22 · nodes 2.71,
  2.72, 3.59 · `nucleo/jev.py`, `nucleo/flash/build_decision.py`.
- **CRIT-K2 · The verdict COMPLETES the model, never contradicts it.** A valid, resolvable model call runs (a
  discrepancy is recorded ⚖️); an empty turn or an unresolved call is filled by the verdict's declared action on
  the open card; unsure, closed card or Jev off → the model's path bit for bit. — since 2026-09-23 · nodes 2.73,
  2.121 · `nucleo/flash/direct_action.complete`.
- **CRIT-K3 · The verdict's action lands on the LIVE card**, never a bare phantom; with several cards of one type
  «close» goes to the one his last turn touched; «it» / «that» is the card his last turn acted on. — since
  2026-09-29 · nodes 2.167, 2.169, 2.85 · `nucleo/flash/show_target.py`, `nucleo/canvas_focus.py`.
- **CRIT-K4 · An order NAMES its target.** A show never falls on the card that happens to be open; what is
  unknown is the REFERENCE, never the card; the show backstop uses the verdict's card before a contextual guess.
  — since 2026-09-29 · nodes 4.160, 2.170.
- **CRIT-K5 · A canvas mutation needs the operator's words.** The room is not the operator: ambient speech
  reaches neither the chat nor the canvas; a system note never names a card to close and never vetoes a show. —
  since 2026-09-09 · nodes 4.145, 2.134, 3.99.
- **CRIT-K6 · The canvas that counts is the tab holding the voice session**; a fullscreen card covers everything
  and always has an exit; leaving fullscreen is its own, idempotent order. — since 2026-09-24 · nodes 2.91, 2.78,
  2.79.
- **CRIT-K7 · A descriptor is written under the cut and measured against its NEIGHBOURS** (`MAX_DESC_CHARS`); a
  homograph is closed by naming it; a number he said is a READING, not an invention, and a question asked twice
  keeps its answer. — since 2026-09-23 · nodes 2.74, 4.204.
- **CRIT-K8 · Closing a card is a TOOL, like opening one**; «close the calendar and the messages» closes both; an
  op inside a card runs and the card he NAMED closes after it. — since 2026-09-24 · nodes 2.88, 2.127, 2.126.
- **CRIT-K9 · A classifier before the model is a PRICE** (~780 ms), paid only where the decision cannot be read
  after; a fixed table may decide alone only where a wrong answer costs nothing — a fail-open default, as the scope
  of a spoken rule is. — since 2026-09-22 · nodes 3.58, 2.172.

## 4 · Errands and workers

- **CRIT-E1 · The TASK is the unit.** One durable row per errand; the worker reports or the pulse demands it; a
  task is born from four sources only, never from a loop having a tick. — since 2026-09-27 · nodes 3.82, 3.83,
  3.84, 2.18.
- **CRIT-E2 · A message with several tasks is a LIST**: split, queued, run step by step, reported once; the ack of
  a list never blocks its own turn. — since 2026-09-26 · nodes 4.216, 3.90.
- **CRIT-E3 · Resources pinned, reasoning open.** A worker's prompt carries formulas, resources and ways of
  solving, never a script; a fix shaped like the scenario is scaffolding (change one word of the request: does it
  stand?); in doubt it is a RESOURCES problem. — since 2026-08-20 · nodes 2.82, 4.32 ·
  `.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md`.
- **CRIT-E4 · The rungs, cheapest first**: a declared widget action, then the network (an agent), then the
  browser, which is the LAST resort; a delivered hunt is not re-hunted; one widget per errand, the browser inside
  the sheet's process tab. — since 2026-09-21 · nodes 2.84, 2.43, 4.109.
- **CRIT-E5 · A report is a DOCUMENT**, and a fast listing pass serves the turn or hands off with its sheet inside
  its budget — a turn is never left mute. — since 2026-09-29 · nodes 4.143, 2.43, 2.171.
- **CRIT-E6 · An errand with a third party offers the model NO tools**: it returns one JSON object and the engine
  executes what the mandate allows — the template of every rail on consequences. — since 2026-09-13 · nodes 3.44 ·
  `nucleo/errands/party.py`.
- **CRIT-E7 · A worker's endpoint comes from its spec or the provider chain**, never from the inherited shell; a
  worker never depends on ONE provider. — since 2026-09-19 · nodes 2.82, 4.27.
- **CRIT-E8 · A parked errand is still the errand.** The dedup compares against the errands waiting on his
  yes/no as well as the live ones; a repeat folds into the parked one, the yes carries what he added, and the
  brain repeats the QUESTION, not the work. An audit that comes back after the conversation moved (a turn of
  his, a widget op) may record a finding but never acts or speaks. — since 2026-09-29 · nodes 2.182, 2.180 ·
  `nucleo/dispatch_confirm.py`, `nucleo/susurro/engine.py`.
- **CRIT-E9 · Every request that acts is ONE row, and it ends in a verdict of four values**: `met` (its end state
  was attested), `unmet` (attested false after its grace — corrected out loud when he ordered it), `unverifiable`
  (nothing readable could say) or `undeclared` (the action declares no end
  state). A later op never improves a failed row; a worker's verdict comes from `circuit.close`, a list step's from
  its ops; the prompt's recent state reads these rows, facts only. — since 2026-09-30 · nodes 2.194, 2.196, 2.198,
  3.105, 3.106 · `nucleo/request_row.py`, `nucleo/circuit.py`, `nucleo/spec.py`.

## 5 · Memory and rules

- **CRIT-M1 · A spoken rule carries a scope** decided by a fixed classifier — `voice`, `widget:<id>` or `general`
  — and each prompt surface carries only its own: the worker never carries voice rules; a widget's rule rides in
  that widget's row. — since 2026-09-29 · nodes 2.172 · `nucleo/flash/rule_scope.py`, `memory/rules.py`.
- **CRIT-M2 · Genesis is per domain** (`style`, `consent`, `library`, `errands`, `playbooks`), each with its own
  override file; a factory reset forgets the spoken rules and keeps credentials, settings and connectors; it never
  deletes under a live server. — since 2026-09-29 · nodes 2.173, 8.4, 3.94.
- **CRIT-M3 · A late recall DEGRADES durable memory, never deletes it**; the memory row says whose fact it
  shows. — since 2026-09-24 · nodes 3.79, 3.33.
- **CRIT-M4 · What the operator said survives a failing turn**, and a spoken correction reaches the pill it
  corrects. — since 2026-09-03 · nodes 2.19.
- **CRIT-M5 · The whole prompt of every turn is on disk**, joined by trace; capture is never switched off. — since
  2026-09-20 · nodes 2.100.

## 6 · Resilience

- **CRIT-R1 · A bug of ours is not a provider outage.** The exception decides (an HTTP status is theirs, a bare
  Python error is ours); the SAME request relays to the stand-in inside the connect loop; the panel names titular
  and stand-in, amber while the substitute serves. — since 2026-09-23 · nodes 2.77, 2.54, 4.27.
- **CRIT-R2 · The voice brain is a non-reasoner, model per invocation, and the provider order is
  CONFIGURATION** (`config/v2.json`, managed by the UI) — never a rule in a document. — since 2026-08-19 · nodes
  2.54.
- **CRIT-R3 · Embeddings have no failover model** (a stand-in answers in another vector space); the fall is made
  visible. — since 2026-09-23 · nodes 10.52.
- **CRIT-R4 · No language, no agent**: until the picker locks a language the agent is stopped; after ANY reset it
  comes up listening. — since 2026-09-24 · nodes 4.217, 8.4.
- **CRIT-R5 · The voice has a stand-in**: the models table's `tts.failover` is built beside the titular; a titular
  that cannot be built (no key) is replaced at boot, and LiveKit's `FallbackAdapter` switches on a synthesis that
  fails for good (a 402); the meter bills the provider that spoke. — since 2026-09-30 · nodes 2.202 ·
  `voice/engine/speech/tts/__init__.py`.
- **CRIT-R6 · A hosted account runs no torrent client** unless the deployment sets `ZAELAR_TORRENT_IN_CLOUD=1`;
  self-host keeps the operator's switch. — since 2026-09-30 · nodes 5.61 · `connectors/torrent/service.py`.

## 7 · Working here

- **CRIT-W1 · Mechanisms, not rules.** A change that bounds a CONSEQUENCE stays; one that bounds JUDGEMENT is
  removed; a sentence about how to behave is a rail — delete it and find the mechanism it stood for. — since
  2026-09-15 · nodes 7.32 · `.meshkore/context/principles.md`.
- **CRIT-W2 · English everywhere inside `engine/`** — code, tests, logs, docs, commits; product data in the
  user's language; the module logs in the operator's; Castilian comment lines only shrink. — since 2026-10-01 ·
  nodes 7.60.
- **CRIT-W3 · Never restart with someone inside or an errand alive** (recent `transcript`/`brain` events, or a
  non-empty `/api/tasks`). — since 2026-09-15 · ⚠ sin test.
- **CRIT-W4 · Commit with pathspec after `git diff --cached --name-only` is empty; push after every commit;
  never rewrite pushed `main` for an attribution; never touch another session's uncommitted work.** — since
  2026-08-20 · ⚠ sin test.
- **CRIT-W5 · A wide pass runs under `tests/watchdog.py`, never bare `pytest`**; while iterating, the touched
  file and its DISARM; a test is not a test until seen red; a disarm that stays green accuses the TEST; the
  harness clears `__pycache__` on restore. — since 2026-09-20 · nodes 7.53.
- **CRIT-W6 · A test never touches the operator's real state** (the root `conftest.py` sandbox, which pins
  `ZAELAR_WORKSPACE` and fails BY NAME the test after which his consent/style/library config changed); a red that
  does not reproduce alone is contamination, not a bug; no real identity sits in a tracked file. — since
  2026-09-30 · nodes 3.94, 7.10, 7.55.
- **CRIT-W7 · A test outside the map does not exist**; every mechanism ships with its node; a node whose file is
  gone is red, and a file answers one deterministic node. — since 2026-09-30 · nodes 7.32, 7.56.
- **CRIT-W8 · Public and private.** `engine/` describes mechanism, never product; neither our past nor our future
  is published (roadmap, module logs, test reports stay local and untracked). — since 2026-10-01 · nodes 7.60.
- **CRIT-W9 · Closing a batch:** the node in the map, the WHY in the diary, the operator's words in the module
  log — and a line HERE only when a rule changed. — since 2026-09-29 · ⚠ sin test.

---

## Contradicciones (esta tabla tiene que estar vacía)

| topic | rule A | rule B | winner |
|---|---|---|---|
