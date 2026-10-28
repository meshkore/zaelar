# zaelar — Bot testing playbook ("run a bot test")

> **Mandatory entry point for agents:** read `tests/README.md` first. That file holds the concise terminal↔UI
> contract, suite selection, isolation, ports and how to add runners. This playbook is the deep layer for preparing
> live scenarios, diagnosing results and archiving evidence. If they ever disagree, the current CLI behaviour +
> `tests/platform/SCHEMA.md` win, and both documents are aligned in the same change.

> **Trigger**: when the operator says **"run a bot test"**, **"run the (scenario) battery"**, **"test the bot"** or
> similar → run THIS playbook end to end. The steps are not meant to be remembered: they live here. The description
> of the system's PIECES lives in `zaelar-architecture.md`/`CLAUDE.md`; this doc is ONLY **how it is tested** (what,
> in which priority, how it is evaluated, where it is archived).

The bot is tested **on its own, with no human microphone**: a **tester** agent (`tests/voice/e2e/agent/`) joins the
LiveKit room as a 2nd participant, SPEAKS through TTS and LISTENS through STT; a **JUDGE** (GLM-4.6 via Z.AI,
DeepSeek fallback) evaluates the OBSERVABLE behaviour (frontend actions, brain tags, escalations, latencies) by
reading `GET /events`.

> **Unified entry point + real-time viewer** — `./.venv/bin/python -m tests run <suite>` runs memory,
> agent-headless, voice, browser, connectors, cluster or infrastructure under the same contract. Locally it opens
> the **Zaelar Test Observatory** at `http://127.0.0.1:8765` automatically; in CI use `--no-open`. Each new run hands
> off on that same port and replaces the previous dashboard, leaving no orphan servers. Every test, turn,
> input/output, latency, agent event and score is persisted in `tests/runs/<run-id>/events.jsonl`, and can be
> reopened with `python -m tests replay <run-id>`. For real voice: `python -m tests run voice --live` with zaelar UP.

> **Navigable test map** — the whole test surface can be walked through **`tests/run_testmap.py`** (axis **domain →
> use case → channel**, numbered `1.1`/`2.1`/…), with the narrative in **`tests/TESTMAP.md`**. One of the domains is
> **HOMEOSTASIS** (the machine's autonomous health layer, `nucleo/pulse/homeostasis.py` /
> `tests/infrastructure/unit/core/test_homeostasis.py`).

> **Map contract, schema 2** — the Observatory consumes one common tree for ALL the main types:
> `suite → ordered steps → groups → cases`. Each case has a stable ID, input, expectation, verification, internal
> path, source and validated execution. Pytest is normalized automatically and rich corpora are connected through
> `catalog_provider` (Memory, Voice and Headless). A whole suite, a group in order or a single case can be run from
> the UI or with `python -m tests run <suite> --case <id>`. Specification: `tests/platform/SCHEMA.md`.

> **Rule for Claude Code/Codex:** use `--no-open` if you do not need to drive the browser. The Observatory still
> comes up on `127.0.0.1:8765`, so the operator can watch and later launch cases from the web. The real engine uses
> `127.0.0.1:43917`. Do not overlap two Observatory runs; do not use `make reset` as routine preparation; and state
> honestly whether only deterministic logic ran or whether the real headless/Playwright/LiveKit boundary was crossed.

> **Shared causal journey** — for changes that cross domains, run
> `./.venv/bin/python -m tests run journey --no-open`. It is a chain of linked steps over an isolated engine,
> memory, canvas, agenda and worker registry. Each case declares `consumes`/`produces`; launching an intermediate
> case rebuilds J001→case. It covers natural extraction, pronouns, widgets, appointments, marketplace search,
> processes, connectors, cluster, temporal correction and checkpointing. It does not replace the physical
> microphone/STT/LiveKit, Playwright or remote WebSocket boundaries. Full design: `tests/journey/README.md`.

---

## A GREEN test has to mean something — suite isolation

A guard that looks like it covers something and does not is worse than a failing test, because nobody looks at what
is already green. The classic shapes:

| What you see | What is really happening |
|---|---|
| tests about phrases to the operator pass | they pass because of the MACHINE's config (its language), and fail on any other machine and in CI |
| a fixture that exercises the REAL reset | it wipes the operator's real widget data on every run |
| two map nodes with the same number | one is counted twice and the other does not exist |
| emptying a widget | a mutation without an event: looks like a persistence failure |

**The mechanism to remember:** setting the variable is not enough. `config/settings.load_into_env()` copies
`config/settings.json` ON TOP of the environment, unconditionally, because in production the store WINS over the env
— the right rule there. In a test it means the operator's PERSONAL configuration decides the suite's result:
language, STT/TTS provider, attention mode and engine profile.

**Invariants held by the root `conftest.py`**, and why each one:

- **`ZAELAR_LOG_DIR` to a temp dir** — a test's events cannot end up in the timeline the operator reads for REAL
  post-mortems, where a test's `kind:error` would be audited as an incident.
- **`SETTINGS_FILE` to an EMPTY temp file** — the operator's config does not decide the suite's result.
- **`ZAELAR_LANGUAGE=en` FORCED** (not `setdefault`): with a default, a `ZAELAR_LANGUAGE` in the shell would change
  what "green" means again. **Testing another language is declared IN the test**; testing both is done by checking
  both INSIDE the case, never by running the suite twice with a changed environment.
- **`ZAELAR_RESEARCH=0`** — an escalation's pre-flight calls a real provider; in a test it is an undeclared network
  call that hangs the case until timeout.
- And every test that touches widget data **isolates `store.DATA_DIR`** itself.

All of this is set **at module level** in the conftest, not in a fixture: test modules are imported BEFORE any
fixture runs, so a fixture arrives too late.

Permanent guard: **node 7.10** (`tests/infrastructure/unit/test_suite_isolation.py`) — a guard over the guards. If
any invariant breaks, the suite could lie again and nobody would notice until a test passed here and failed
somewhere else.

**How this class is hunted:** not with `grep`, with MEASUREMENT. Run the suite with the suspect variable changed and
diff the failures — and before that, check the knob REALLY reaches inside a test (a sweep that does not apply what it
thinks it applies is the same bug you are looking for).

## Step 0 — ALIGNMENT tests ↔ system (ALWAYS first, before launching anything)

Before testing, make sure **the scenarios test the CURRENT version of the system**. Checklist:

1. **Main modules covered**: every live capability has at least one scenario in `tests/voice/e2e/agent/scenarios.py`
   (see the catalog in `tests/voice/e2e/agent/anexos/catalogo-escenarios.md`): conversation · memory
   (save/recall/correction) · widgets (show/create/delete) · factual web search · deep web navigation (marketplaces) ·
   unified messaging · connectors · cluster · paste/chat · multilingual · **data security (the vault)**.
2. **Changes in the last ~48 h**: `git log --oneline --since='48 hours ago'`. For each NEW or CHANGED capability (a
   new tool, a new provider, a new flow), confirm a scenario exercises it; if not, **add it to
   `tests/voice/e2e/agent/scenarios.py` + the catalog** before launching. Also check new lines in
   `.meshkore/docs/criteria.md`.
3. **Real startup**: zaelar UP on `:43917` with the LATEST version (if you touched `.py`, restart — `make run` —, wait
   for `/api/livekit` + `registered worker`, and confirm in the log the **prewarm** (`prewarm FlashBrain OK`) and
   `browser_search OK`).

> ⚠️ **HARD VERSION RULE — development happens on THIS machine; the latest version is the LOCAL WORKING TREE.**
> Testing runs ON the code already checked out in the local repo; the operator (and other agents) develop here, so
> **local is the source of truth**, not `origin`. **NEVER** `git pull` / `fetch` + `merge` / `reset` / `checkout` of
> another branch or commit to "bring in the latest version" or to bring the repo up to date before a test: `origin`
> may be BEHIND local work, and any git operation can **DESTROY uncommitted local code** or switch commits under the
> feet of another agent working on the same tree. If you need to make sure of the startup, just **restart the
> process** (`make run`) with what is on disk. If you really think something is missing, ASK the operator — do not
> touch git.

> If Step 0 detects drift (a scenario tests something that no longer exists, or something new is not covered),
> **fix the scenarios first** and note it in the day's report. Misaligned tests give invalid verdicts.

---

## Priorities — WHAT we care about testing (in order)

1. **Perceived latency** — (a) **1st turn** (the prewarm must absorb the cold start → about a second); (b)
   steady-state chat; (c) **search**. Any chat turn noticeably slower than steady state is suspect.
2. **Low cost** — ALWAYS prefer what is free and works (Google via the browser, local Ollama, Kokoro/Whisper Metal)
   over paid APIs. A test must not assume a paid key; if a paid layer is present, all the better, but the free
   default has to work well.
3. **Correct memory** — saving what was said, recall in the same thread AND from previous sessions, **correction**
   ("no, actually it's X"), forgetting, and NOT hallucinating data. (Memory also has its **own** exhaustive suite —
   here 1-2 smoke scenarios are enough; do not duplicate.)
4. **Accurate search** — a factual answer spoken IN the turn (weather, a match result, a stock quote, "who won").
   Weather and match results must come out EXACT (Google widgets); for the rest, quality snippets → the brain
   synthesizes; never invent a fact that is not there.
5. **Deep web navigation (with or without login)** — the flagship case: "find me a car under €5000 and under
   250,000 km on Wallapop/coches.net" → opens the **Chromium browser in the background**, navigates, **extracts real
   listings** (price + km) and gives a top 3. **Requires comparison** (see below): do the cars exist and meet the
   criteria? **Unauthenticated** for now (if a site asks for a login, the bot should say so; we do not force
   credentials).
6. **Robustness / turn-taking** — no going silent, no greeting loops, handling corrections and interruptions. (Many
   battery "mutes" are a harness artifact — see Harness notes.)
7. **Multilingual** — a subset in English; voice/persona/STT never crossed with the language.
8. **Data security** — the encrypted **secrets vault** (scenario `seguridad_datos`): SAVE a secret
   (password/IBAN/crypto) → ASK for it → zaelar asks for the **passphrase** → SERVE it. The tester **does NOT use
   biometrics** (passkeys are hardware) → unlocking goes through the **passphrase** (the native modal / the
   `/api/vault/*` API; the robust path is scripting `create`+`unlock` over HTTP). **HARD FAIL** if a secret's VALUE
   appears IN CLEAR in any event/log/trace or zaelar recites it from memory — the invariant is that the value only
   travels `DB(ciphertext)→/api/vault/reveal→frontend`, never through the LLM or the observer.

---

## FAST TEXT channel — the FlashBrain probe (3rd way of testing)

Before the VOICE battery (slow, with STT noise), to iterate on the **fast brain / conversation / prompt /
memory-state / tools** there is a **headless text channel** that runs the REAL FlashBrain turn (same
`build_flash_system` + model + `router.TOOLS` + `dialog.py` defences) and returns an evaluable JSON — no voice, UI
or LiveKit room. It is the fastest way to reproduce/validate a fix from Claude Code.

```bash
make reset                 # memory + observability to ZERO (keeps credentials/auth; boundary in scripts/reset-memory.sh)
make flash-serve           # HEADLESS server (no voice/browser); in another terminal:
make flash T="hola, ¿cómo te llamas?"     # one-shot  →  zaelar ▸ … [action=… ⚠️LOOP/DEGENERATE] (ms)
make flash-repl                            # interactive conversation (/reset clears the window)
curl -s localhost:43917/api/flash/say -H 'content-type: application/json' -d '{"text":"…","ingest":false}'
```

Response: `{ok, reply, action, tool_calls, tags, degenerate, loop_run, turns, prompt_chars, spec, timings}`.
`action` = what the real turn WOULD do (`chat`/`escalate`/`search`/`widget_data`/`delete_widget`/`canvas:show…`).
`ingest=true` (default) writes to memory like the real turn (check against `curl /api/memory/map`); `ingest=false` =
isolated chat. `degenerate`/`loop_run` flag the splicing/repetition pathologies. The defences live in
`nucleo/flash/dialog.py` (loop breaking + pruning + anti-degeneration), SHARED by voice and the probe → what you
validate by text runs the same way in voice. Endpoint only with `BRAIN=nucleo`. See `nucleo/flash/probe.py`.

---

## The «susurro» group — self-audit and CONTINUOUS IMPROVEMENT

A SPECIAL group: it does not test a feature but **that the system corrects itself** — the strong model must work out
where the problem is when something goes wrong, and correct it. Three anchors:

1. **Unit** — `tests/agent_headless/unit/susurro/test_susurro.py` (es/en friction, catalog, appliers, engine with a
   fake LLM, cooldown, kill-switch). Runs with normal pytest.
2. **Headless integration** — `tests/agent_headless/e2e/susurro/run_probe_suite.py` (live server): simulates
   friction through the probe (a complaint after an action), requires the complete MACHINERY (trigger → request WITH
   payload → response → full audit, `susurro` kind events in the timeline) and checks that a `repair_say` comes out
   SPOKEN on the next turn (the probe drains `brain_notes`). The model's JUDGEMENT is reported without failing the
   suite (deciding `corrections=[]` for a healthy stretch is correct). **Every run appends to
   `tests/agent_headless/e2e/susurro/history.jsonl`** — the LONGITUDINAL history: over time friction per session
   should go down and diagnosis quality should improve (review that file when evaluating waves). Mind the
   `cooldown_s` (default 60s) between runs.
3. **Voice e2e** — scenario `susurro_reparacion` in `tests/voice/e2e/agent/scenarios.py` (cron rotation): the tester
   complains out loud and the judge checks the `susurro` events + the natural repair. A complaint with NO susurro
   event = machinery FAIL.

When FIXING a Susurro finding (the dev loop consumes them from `.meshkore/logs/susurro/findings.jsonl`), treat the
finding like a wave's finding: fix + control test + re-verify + document.

## The «cluster channel» group — talking to AGENTS ("one mind")

The cluster channel is agent-to-agent (NOT voice), so the voice tester does not cover it — it has its own group,
which checks the conduct INTELLIGENCE (no re-introducing, phase, objective present, loop cutting) and SECURITY
(untrusted profile: tools off + identity-safe). Two anchors:

1. **Deterministic regression (no LLM)** — `tests/cluster/unit/test_capsule.py` + `test_capsule_flow.py` +
   `test_security.py` (stall guard). They capture the EXACT prompt the bridge gives the brain per turn and check: NO
   re-introduction after the 1st contact, phase progression (greeting→probing→work), the operator's objective
   present, capsule injected, `build_cluster_system` identity-safe (zero operator PII), structural tools-off, and the
   stall escalation (repetition → 1 assertive message → go quiet + notify). They run with normal pytest.
2. **e2e with the REAL ENGINE** — `tests/cluster/e2e/run_cluster_suite.py`: scripts a peer conversation and passes it
   through `nucleo/flash/cluster.py::respond` (GLM-5.2) with the SAME framing as the bridge (capsule + fence +
   trailer). HARD invariants (machinery + identity-safe + no re-introduction) fail the suite; the soft judgement
   (intro/on-goal/concise) is reported. Appends to `tests/cluster/e2e/history.jsonl` (longitudinal). Requires the
   channel tier's key (loads `.env` + the credential store on its own).

---

## The WIDE pytest pass — with the watchdog

A wide pass always runs through the watchdog, never bare `pytest`:

```sh
./.venv/bin/python tests/watchdog.py                          # everything deterministic (~7 min)
./.venv/bin/python tests/watchdog.py tests/voice/unit         # one folder
./.venv/bin/python tests/watchdog.py --impacted origin/main   # only what your diff reaches
```

Three layers catch a hang: the `faulthandler` dump — already inside pytest, **no new dependencies** — **names** the
file, line and function of the hung test and cuts it off within seconds; a wall-clock limit per chunk covers what the
dump cannot see (an import or a collection that blocks); and the process **GROUP** is killed, because killing pytest
alone leaves any browsers it spawned where they were. A lock prevents two WIDE passes at once on the same checkout
(they slow each other down several-fold); explicit paths take no lock, on purpose, so they can be nested.

Tests that scan the source tree ask `git ls-files` what the tree is, rather than walking the disk with a blacklist of
binary suffixes: a working copy can hold large local files (downloads, media) that are not part of the repo.

The full contract lives in `engine/tests/README.md`; node **7.53** watches the watchdog. ⚠️ `tests/run_testmap.py`
**without arguments** stays off-limits: it is the same wide pass without watchdog or lock.

## How it is LAUNCHED

- **Full battery** (every scenario, with settle time between them so the worker THREAD is not saturated):
  `bash tests/voice/e2e/agent/run_battery.sh` → writes a summary table
  `tests/voice/e2e/agent/runs/battery_summary_<hhmmss>.tsv` + one report per scenario
  `tests/voice/e2e/agent/runs/report_*.{json,md}`. Variables: `BATTERY_SCENARIOS="a b c"` (subset),
  `BATTERY_SETTLE=12` (s between scenarios), `BATTERY_MAX_RUN=360` (watchdog per scenario).
- **A single tick** (rotates by cursor): `bash tests/voice/e2e/agent/cron_tick.sh` — prints a `VERDICT status=…`
  block.
- **A single scenario**: `./.venv/bin/python -m tests run voice --case voice::scenario::<id> --no-open`
  (canonical observable action), or directly
  `./.venv/bin/python -m tests.voice.e2e.agent.run --scenario <id> --no-open --hold 0` to diagnose the harness.
- **Autonomous test→fix loop**: `cron_tick.sh` can be driven by a session cron (e.g. every 15 min). Each firing tests
  ONE case, the judge scores it, and the agent FIXES the code if there is a real bug.

Requirements: zaelar UP (Step 0) + the tester's keys in `.env`/`.meshkore/credentials/tester.env`
(`TESTER_AIMLAPI_KEY`, `CARTESIA_API_KEY`, `DEEPGRAM_API_KEY`, `TESTER_ZAI_KEY`).

## Driving the operator's LIVE engine remotely (assisted testing / demo passes)

When an agent drives the operator's own local engine from a scripted browser (Playwright typing into the chat,
the way demo passes run), these rules hold:

- **Microphone AND speaker off by default.** The pulse and the running agent may be visible; the agent must
  neither hear the room (room audio would enter as a turn) nor speak out loud. The driver mutes the mic
  (`POST /api/mic {"muted": true}` + `mic.setMuted(true)` in its page) and the bot's voice output.
- **The driver takes the session lock and keeps it.** A tab the operator left open holds the single voice
  session; the driver calls `POST /api/session/steal` at start AND before each step — the operator's tab
  retries every 3 s and takes the lock back whenever it lapses, after which the driver's orders silently reach
  nobody.
- **Remote control is BLUE.** While a session is driven remotely the ⏻ blinks, and blue is the default colour of
  every remote-control indicator: on a filled control, blue background with white text/icon; on an icon drawn
  straight on the desktop (no background), the ⏻ outline itself in blue, blinking. Built for the ⏻ (agent state
  `remote`, token `--hb-remote`); any new remote-control indicator uses the same token.
- **What a pass may touch.** The operator's connected calendar and the demo contacts he designated; any other
  real contact only after asking him. The list of those contacts is private and never lives in this repo.

---

## How it is EVALUATED (telling signal from noise)

The judge gives `overall` (1-5) + `scores{naturalidad,coherencia,utilidad,accion,latencia,robustez}` + `veredicto`.
Threshold: **`overall ≥ 4` = PASS**. But a FAIL is **NOT automatically a zaelar bug** — it has to be discerned:

- **REAL bug** → confirm it in `.meshkore/logs/timeline-latest.jsonl` (`brain`/`widget`/`search`/`error`/
  `transcript` events correlated with the report). Only then is code touched. Fix → restart if `.py` was touched →
  **re-run THAT scenario** → document.
- **Tester STT noise** — the tester's own Deepgram garbles ("zaelar"→"Arbe/Harvey/Árix", mixes languages). A
  garbage input invalidates the turn; it is NOT a zaelar failure. **Careful**: when testing against a live account,
  it also writes misheard names into that account's memory.
- **Judge rigidity** — it sometimes penalizes correct things (two idempotent `show`s = "duplicate"; correctly saying
  "I can't find it" when the search did not return the fact = "hallucination"). Verify before believing it.
- **Harness contention** — a single worker THREAD; back-to-back scenarios without settle → false mutes/timeouts
  (all-1s). `run_battery.sh` already adds settle; even so, an isolated all-1s is usually this.

**Web navigation = explicit comparison**: for the car/marketplace scenarios, besides the judge, **compare by hand**
what was extracted: are they REAL listings? do they meet price and km? is there a top 3 with data? or did it
hallucinate / fail to get in? Record the human verdict in the day's report.

---

## Where it is ARCHIVED (queryable history)

- **Scenario catalog** (what is tested and why): `tests/voice/e2e/agent/anexos/catalogo-escenarios.md` — kept aligned
  with `tests/voice/e2e/agent/scenarios.py` in Step 0.
- **Report of each test session**: when closing a batch, create a folder
  **`tests/voice/e2e/agent/reports/<YYYYMMDD>-<desc>/`** (year-month-day + a short description) with: the summary
  table (`.tsv`), the relevant `report_*.{json,md}`, and an **`INFORME.md`** with: what was tested, the results
  table, findings (real bug vs noise), fixes made, and latencies before/after. That way, repeating the battery a week
  later leaves a comparable history. (`tests/voice/e2e/agent/runs/` is the raw scratch; `reports/` is the curated
  archive.) Reports are session transcripts, so `reports/` is gitignored and stays on the machine that ran them: the
  CATALOG of what is tested is public, the RECORD of what was run is not.

---

## Harness notes (not worth chasing each time)
- `--goal` ALWAYS uses the VOICE channel (chat/paste only through the fixed scenarios).
- The tester's Deepgram STT garbles/mixes languages → with a dirty signal, look at `timeline-latest.jsonl`, not the
  audio.
- A single embedded worker THREAD → settle between scenarios (already in `run_battery.sh`); do not run a battery while
  the operator is LIVE in a voice session (collision) — `cron_tick.sh` already SKIPS if it detects active voice.
- Docker IS allowed in the testing system (isolation); zaelar's CORE never depends on Docker.

## MEMORY re-verification cycle (1000+ request test bot)

Besides the voice battery, memory has its own **re-verification cycle**: the test bot (`tests/memory/e2e/bot/`)
role-plays a PERSONA over 1000+ steps and checks through the REAL PATH (writing with the configured CORAZÓN LLM +
reading with the FlashBrain without an LLM) that every request lands/surfaces where it should, across a broad set of
typologies (STATE/SHORT/LONG + dedup, graph, multi-source, forgetting, episodic, scale, contradictions, adversarial,
memory→action, anti-hallucination, temporal validity, cross-session identity…). It runs as an **autonomous
advance-first loop** (wave of 80 → triage bug/flaky/test-flaw → commit) until a **fresh GOLD pass 0→N is green**.

The first Observatory battery is **`Natural dialogue → memory · real gateway`** (`cases4.py`): ordinary multi-fact
turns that test extraction and discarding, splitting into pills, importance/layer/TTL, current slots and state,
corrections and deferred recall. It uses no artificial "remember X" phrases; it checks, among other things, that a
significant event inside a long paragraph is kept and that passing states (coffee, tiredness) are not promoted to
long-term memory.

The second battery is **`Chronological life · 180 days`** (`tests/memory/e2e/timeline/`): hundreds of operations over
a single DB with an injected clock. It simulates daily activity, 2/20/90-day TTLs, durable goals, a
Sevilla→Segovia correction on day 45, reinforcement by query frequency, nightly consolidation, **daily REM across
the 180 days**, and capacity pressure. An isolated case always replays its causal prefix. The chronology uses
structured atoms to isolate the lifecycle; semantic extraction belongs to the v4 gateway and the historical corpora.
It checks that TTLs are applied, not just stored; that FTS stays consistent across prune+evict; and that
reinforcement targets what was actually used rather than the whole context bundle.

The full methodology, how to repeat it from scratch, the failure classification, how often it is questioned and its
boundaries (CORAZÓN non-determinism, recall-at-scale of the local embedding) are in the **reusable playbook**:
`.meshkore/docs/ops/anexos/zaelar-memory-cycle-playbook.md`. Results of a cycle are written under
`tests/memory/e2e/bot/resultados/`.
