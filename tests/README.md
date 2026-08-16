# Zaelar testing — operational contract for agents and humans

This is the first document to read before testing a change. It applies equally to Codex, Claude Code, local
developers, CI and the Test Observatory web UI.

## One system, two interfaces

The terminal and the browser are two controls over the same catalog and event stream:

- **Agent/terminal:** `./.venv/bin/python -m tests ...`
- **Human/spectator:** `http://127.0.0.1:8765`

An agent does not need to interact with the browser. Running through the unified CLI preserves the normal exit
code while starting the Observatory on loopback. Use `--no-open` to avoid opening a browser window; the server
still runs and the operator can watch it. The web UI can launch the same server-validated suite, group or case
when no agent is already testing.

Port **8765 is fixed**. Starting or replaying a run performs a controlled handoff from the previous Observatory.
Do not start two Observatory-managed runs concurrently: their test processes could overlap even though only the
latest dashboard is visible.

## Source of truth

1. `tests/<suite>/suite.json` — suite identity, ordered functional steps and providers.
2. `tests/run_testmap.py` — ownership of deterministic pytest files by domain/step.
3. Rich catalog providers — scenario/corpus metadata and executable actions.
4. `tests/platform/SCHEMA.md` — normalized `suite → step → group → case` contract.
5. `.meshkore/docs/ops/zaelar-testing.md` — complete testing and diagnosis playbook.

There must be no alternative `test/` or `tester/` root. Historical reports and run artifacts may exist below
their owning suite, but executable testing code belongs under `tests/<suite>/`.

## Mandatory workflow after a code change

1. Inspect the local diff and identify the owning suite(s). Never change git state merely to prepare a test.
2. Run the smallest deterministic case that proves the change.
3. Run the owning suite's deterministic regression when risk justifies it.
4. If the behavior crosses a real boundary, run the corresponding live/headless/browser/voice scenario.
5. Read the terminal exit code and failure trace. The dashboard is observability, not the source of truth for PASS.
6. Report the exact command, passed/failed/skipped counts, live services used and remaining untested boundary.
7. If a new behavior has no catalog case, add it in the same change and validate `tests/platform/tests`.

## Core commands

```bash
# Discovery
./.venv/bin/python -m tests list
./.venv/bin/python tests/run_testmap.py --list

# Deterministic suite; browser opens automatically
./.venv/bin/python -m tests run memory
./.venv/bin/python -m tests run agent-headless
./.venv/bin/python -m tests run browser

# Agent/CI mode: same events and Observatory, without opening a browser window
./.venv/bin/python -m tests run all --no-open

# One pytest node, still observable
./.venv/bin/python -m tests run memory --node tests/memory/unit/test_consolidator.py --no-open

# One stable catalog case or an ordered group
./.venv/bin/python -m tests run journey --no-open
./.venv/bin/python -m tests run journey --case journey::whole-system-v1::0015 --no-open
./.venv/bin/python -m tests run voice --case voice::scenario::agenda --no-open
./.venv/bin/python -m tests run memory --case memory::group::1.4::v4 --no-open
./.venv/bin/python -m tests run memory --case memory::group::1.4::timeline-6m --no-open

# Replay a durable run without rerunning tests
./.venv/bin/python -m tests replay <run-id> --no-open
```

Make aliases: `make test-list`, `make test-all`, `make test-ui`.

Raw `pytest` is allowed for a very fast local iteration, but it does not create an Observatory run unless the
platform plugin and run environment are supplied. Before handoff, repeat the meaningful verification through
`python -m tests run ...` whenever practical.

## Choosing the correct suite

| Change | First suite | Real-boundary follow-up |
|---|---|---|
| Cross-domain behavior/state carried across features | `journey` | affected LiveKit/Playwright/WebSocket boundary |
| SQLite, recall, writer, TTL, consolidation, REM, vault | `memory` | six-month chronology or memory corpus |
| FlashBrain, router, prompt, dialog, worker, scheduler | `agent-headless` | text probe/search/persona case |
| VAD, attention, STT/TTS bridge, LiveKit agent | `voice` | voice scenario or microphone self-test |
| Widget contracts, browser owner, navigation, UI data | `browser` | Playwright/browser session against live Zaelar |
| Email, messaging, Spotify, WhatsApp, architect | `connectors` | provider sandbox/live connector only when authorized |
| Peer capsule, cluster policy, security | `cluster` | live peer conversation |
| Bus, SSE, config, server, homeostasis | `infrastructure` | chat transport/full smoke against live Zaelar |
| Real-world ES/US task scenarios (backlog, no runner yet) | `use_cases` | see `tests/use_cases/CASES.md` |

`browser` currently contains deterministic browser/widget contracts. It must not be reported as a rendered UI
E2E unless Chromium/Playwright was actually driven against the live application.

### Whole-system chronological journey

`journey` is the primary integration story, not another collection of isolated checks. Its 26 cases share one
disposable engine, workspace, database, session history, canvas, agenda and worker registry. Each case declares
what prior state it consumes and what verified state it produces; selecting a later case replays its full prefix.
It covers natural memory extraction and correction, deictic widget use, a persisted appointment, one complex
Wallapop worker refined in place, process/debug visibility, connectors and cluster dialogue. Run it after changes
that cross two or more domains. Full contract and honest boundary list: `tests/journey/README.md`.

## Test types and state boundaries

### Deterministic pytest

Runs without the live Zaelar server unless the test explicitly declares otherwise. Fixtures must isolate DB,
filesystem and network state. These tests may run independently and must not depend on collection order.

### Conversational memory gateway (primary)

The primary Memory action in the UI is `Diálogo natural → memoria · gateway real`:

```bash
./.venv/bin/python -m tests run memory \
  --case memory::group::1.4::v4 --no-open
```

It uses ordinary, multi-fact utterances rather than explicit “remember X” commands. Every turn crosses the real
`memory_agent.ingest_utterance → mem_processor/CORAZÓN LLM → deterministic gates → queue/writer → SQLite` path.
It checks extraction and discard, multi-atom splitting, layer/TTL decisions, current state and slots, corrections,
pinned medical information, and delayed recall. The isolated v4 DB is rebuilt from step 1 for a whole group or an
individual later case. It loads the repository `.env` without overriding process variables; this is a live-model
test and must report the actual provider/model or fail when `require_llm` is declared.

The historical v1/v2/v3 corpora add 1,847 cases. They are separate isolated memories, not chronological
continuations of v4 or each other.

### Chronological memory lifecycle

The second Memory group isolates aging and lifecycle behavior:

```bash
./.venv/bin/python -m tests run memory \
  --case memory::group::1.4::timeline-6m --no-open
```

It creates one fresh isolated timeline DB, executes 966 operations in causal order and stops at the first failure.
Executing an individual timeline case replays its complete prefix from step 1. Never replace that behavior with a
shared developer/operator DB. Details: `tests/memory/e2e/timeline/README.md`.

REM runs after light consolidation on every simulated day 1–180, matching production's default 24-hour cadence.
This deterministic chronology writes structured atoms deliberately: it tests how memories age, reinforce, expire,
supersede and survive REM independently from LLM extraction, which is owned by v4 and the historical corpora.

### Headless text/probe

For deterministic FlashBrain logic, use the `agent-headless` suite. For the real running brain:

```bash
make flash-serve                    # or make run; Zaelar at 127.0.0.1:43917
make flash T="hola, ¿cómo te llamas?"
curl -s http://127.0.0.1:43917/api/flash/say \
  -H 'content-type: application/json' \
  -d '{"text":"hola","ingest":false}'
```

Use a unique `session` and `ingest:false` unless persistence is the feature under test. Prefer mapped search or
persona cases from the Observatory when the action already exists there. A direct ad-hoc curl is diagnostic and
does not become a scored Observatory case automatically.

### Live browser / Playwright

Start the current local working tree with `make run` and wait for:

```bash
curl -fsS http://127.0.0.1:43917/api/livekit
```

Then drive `http://127.0.0.1:43917` with Playwright/Chromium. Reuse the repository's persistent browser profile
only when the scenario requires its authenticated state; never clear cookies or auth as test cleanup. Avoid real
irreversible actions. A new repeatable visual flow belongs in `tests/browser/e2e/`, must be declared by the browser
catalog, and should emit the event protocol below so the Observatory shows each action and screenshot/artifact.

### Voice and microphone

Voice E2E requires Zaelar live on `43917`, LiveKit, STT/TTS and judge credentials:

```bash
./.venv/bin/python -m tests run voice --case voice::scenario::<id> --no-open
./.venv/bin/python -m tests run voice --live --no-open
./.venv/bin/python -m tests.voice.e2e.mic.mic_selftest
```

Do not run a voice battery while the operator is in an active voice session. STT noise is not automatically an
engine bug; correlate the transcript, `/events`, actions and judge report first.

## Live service and data safety

- Engine/application: `http://127.0.0.1:43917`.
- Test Observatory: `http://127.0.0.1:8765`.
- Both bind to loopback and serve different purposes.
- `make reset` deletes human-memory/observability state; it is destructive and is **not** routine test setup.
- Prefer fixture DBs, `ingest:false`, unique session IDs and provider sandboxes.
- Never expose secrets in cases, command arguments, events, screenshots or reports. Event fields named token,
  password, passphrase, authorization, cookie, api_key or secret are redacted, but callers remain responsible for
  not embedding credentials inside arbitrary text.
- Live connectors or purchases/messages require explicit authorization and test accounts.

## Observatory lifecycle and durable evidence

Every unified run creates `tests/runs/<run-id>/`:

- `run.json` — status, counts, exit code and dashboard URL.
- `events.jsonl` — append-only event stream, readable during a crash or live run.
- `artifacts/` — screenshots, reports and runner-specific evidence.
- `dashboard.log` — local server diagnostics.

Useful read-only checks:

```bash
curl -fsS http://127.0.0.1:8765/api/meta
curl -fsS http://127.0.0.1:8765/api/catalog/memory
lsof -nP -iTCP:8765 -sTCP:LISTEN
tail -f tests/runs/<run-id>/events.jsonl
```

The latest UI launch intentionally stops only the previous Observatory server and reuses port 8765. Do not kill
unrelated Python/Chromium processes broadly. If the port belongs to a non-Observatory service, the CLI fails rather
than killing it.

## Adding a mapped test or E2E runner

1. Put it under the owning `tests/<suite>/unit|integration|e2e/` directory.
2. Add deterministic paths to `tests/run_testmap.py`, or add a rich `catalog_provider` to the suite manifest.
3. Give every rich case a stable ID, input, expected result, verification, execution path, source and declared
   execution action. Browser clients cannot submit arbitrary shell commands.
4. Stateful cases must declare their ordering/replay policy explicitly.
5. Rich runners launched by the platform receive:

   - `ZAELAR_TEST_RUN_DIR`
   - `ZAELAR_TEST_RUN_ID`
   - `ZAELAR_TEST_SUITE`
   - `ZAELAR_TEST_DASHBOARD_URL`

   Use `tests.platform.events.EventWriter` to emit `test.discovered`, `test.started`,
   `interaction.input`, `interaction.output`, `test.finished` and judge scores. Put binary evidence in the run's
   `artifacts/` directory. Mark `nested_events:true` only when the child runner emits its own lifecycle events.
6. Validate:

```bash
./.venv/bin/pytest -q tests/platform/tests
./.venv/bin/python -m tests run <suite> --no-open
curl -fsS http://127.0.0.1:8765/api/catalog/<suite>
```

An unowned pytest appears under `unmapped`; do not hide or filter it away. The target state is zero unmapped cases.

## Interpreting and reporting results

- Deterministic pass rate and LLM judge quality are separate measurements.
- A failed setup/teardown/assertion means FAIL regardless of judge score.
- A live timeout means the boundary was not verified; report it as blocked/infra, not PASS.
- For voice/browser/search, distinguish engine defect, tester/STT noise, provider outage and judge weakness.
- Always state what was not exercised. Never infer voice/rendered-browser correctness from unit tests alone.
