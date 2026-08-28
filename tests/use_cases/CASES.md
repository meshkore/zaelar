# Real-world use cases — ES/US catalog

This is the readable catalog for the `use_cases` suite (`tests/use_cases/suite.json` +
`tests/use_cases/catalog.py` + `tests/use_cases/cases_data.py`, the source of truth). It mirrors
`tests/voice/e2e/agent/anexos/catalogo-escenarios.md`'s role for the voice suite: the catalog of
what gets tested is public and useful; per-run diaries are not (see `tests/README.md`).

**Status: mostly backlog, NINE promoted.** Every case below is registered and browsable
(`python -m tests list`, the Observatory at `http://127.0.0.1:8765`, `/api/catalog/use_cases`).
Cases get promoted to executable one at a time. Promotion doesn't mean "wire a simple
request/response pytest" — these are open-ended, non-deterministic real-world tasks, so a promoted
case gets a **dynamic harness** instead: `tests/use_cases/e2e/agent/` (driver + watchdog + verify +
judge, full design below), reusing the voice tester's proven DRIVE+JUDGE pattern
(`tests/voice/e2e/agent/`) rather than reinventing it.

> **➤ Which ones actually PASS right now: [`STATUS.md`](STATUS.md)** (generated; source of truth
> `status.json`). That scoreboard is the answer to "cuáles funcionan bien y cuáles no" — this file is
> the CATALOG (what we test and why), the scoreboard is the RESULT. `INFRA` there is deliberately a
> third state, never folded into `FAIL`: a network timeout or a crashed harness says nothing about
> whether the use case works, and merging the two is how a scoreboard starts lying.


## What a fix is allowed to be (operator's norm, 2026-08-20)

**A case is a SAMPLE, never a specification.** The agent has to handle a hotel booking, a research
project on 2nd-century-BC Greek culture, the task list for building a rocket, a used-car search on
Wallapop, a house search in Los Angeles on whichever site is popular there. Nobody can enumerate that,
so a fix that makes one scenario green by teaching the engine that scenario is not a fix — it is a
scenario-shaped hole waiting for the next comma to change.

The line the operator drew, and it is the one to hold:

- **The CORE plumbing must be solid, tested and boring**: how the browser is driven, how data reaches
  the Brain Worker in real time and complete, how a page is parsed, when a screenshot is taken, how a
  tool reports what it got. This is mechanism, it is finite, and it is where hardening belongs.
- **The LOGIC on top must stay free**: the worker gets broad briefs, resources and room to experiment,
  and is expected to FIND a way to the operator's goal. Not a decision tree we wrote for it.

What this means for this suite, concretely, because a scoreboard that rewards overfitting will get it:

1. A green case proves the mechanism worked ONCE, on one set of data. It is evidence, not a
   guarantee — but one concrete case, driven end to end, is what we grade. No variant rounds, no
   mutation matrix: the operator's call, 2026-08-20.
2. Coverage grows by COMPLEXITY, not by re-running the same case with the serial numbers filed off.
   Tiers 1→7 are that ladder, and the board works them in ascending order. The hardest shapes —
   several filters that must all hold at once (pool AND free parking AND wifi AND pets AND coast, not
   inland), a marketplace with its own filter controls, a market whose popular site the agent has to
   pick itself — are deliberately last, and are registered as tier 7 rather than improvised later.
3. Findings should name the MECHANISM that failed (extraction, delivery, prompt, budget) rather than
   the scenario's subject. "The browser's extraction is dropped when the payload is truncated" travels
   to every case; "it did not find a 4-star hotel" travels nowhere.
4. A fix that hardcodes this catalog's vocabulary — hotel, Sevilla, 4 stars — into engine code is a
   finding in itself, and gets reported as one.


## Run it ISOLATED — `--sandbox` (2026-08-18)

```bash
./.venv/bin/python -m tests.use_cases.e2e.agent.run --scenario all --sandbox
```

`--sandbox` boots a **throwaway engine with its own port, database, workspace and logs**
(`tests/platform/sandbox_engine.py`) instead of running against the operator's live engine on 43917.
Before this, every use-case run exercised the operator's REAL memory, widgets, cluster tokens and
whatever tasks they had in flight — which is both a privacy problem and a correctness one (a prior
session lost two runs to the engine's global ⏻ having been left STOPPED by unrelated manual testing,
and another to a live task donating a false `worker` signal to a scenario that never triggered one).
A fresh engine has none of that ambiguity.

The recipe existed already but only inlined inside `tests/journey/runner.py`; it is now a reusable
context manager. Two things worth knowing:

- It adds **`ZAELAR_LOG_DIR`**, which `journey`'s copy does NOT set — without it an "isolated" engine
  still appends its events to the operator's real `.meshkore/logs/timeline-latest.jsonl`. That is the
  2026-07-25 incident (test events mistaken for a live session) waiting to happen again. Noted as a
  pre-existing leak in that runner rather than silently patched in another suite's file.
- ⚠️ **Generated widget CODE is NOT isolated.** `widgets/store.py` honours the workspace (widget
  *data* is clean), but `widgets/generator.py`/`lifecycle.py` write to `HERE/<widget_id>/` — the real
  `engine/widgets/`. So a sandbox run that generates a widget leaves a folder in the repo. The runner
  **reports** them at the end and deliberately does **not** delete them: the operator's live engine
  writes into that same directory, and a cleanup sweep cannot tell whose widget is whose. Fixing it
  properly is a product change (a workspace-relative catalog would also stop the sandbox from seeing
  the built-in widgets), so it is recorded, not guessed at.

The port comes from one table, `tests/platform/ports.py`, which is also where the lab agents get theirs:
this machine runs **three** agents — the operator's own engine on `43917`, the Spanish sandbox on `43921`
and the American one on `43922` — and each answers there whether the round was launched with `--sandbox`
or with `--lab`. A busy port is an **error** that names who is holding it, never a reason to slide to
another one: an agent that quietly moves is an agent you cannot find, and the operator has these
bookmarked.

Don't run `make run` while a sandbox is alive — `scripts/run-livekit.sh` reaps every `python -m
server` by process NAME, not by port, so it would kill the sandbox too. The reverse is safe.

### Watching the test agent while it works

The sandbox answers on **the fixed port of its locale** — `43921` for a Spanish batch, `43922` for an
American one — and its workspace is KEPT under `tests/runs/use_cases/sandbox/<stamp>/` (gitignored). So a
run is observable, not a black box:

- open `http://127.0.0.1:43921` (ES) or `http://127.0.0.1:43922` (US) while the batch runs — the ◷ visor
  shows this agent's events/flows live;
- `GET /api/observability/flows?limit=30` lists its task flows (each probe turn is a flow, with `origin`,
  `title`, families and duration); `GET /api/tasks` is the live worker registry;
- the workspace survives the run, so its `zaelar.db` and `logs/` can be inspected afterwards.

Because each batch gets a fresh workspace, it also gets a fresh `config/identity.json` — i.e. **every batch
appears as a NEW install/`user_id`** in observability rather than mixing into the operator's own session.
That is deliberate (it's what makes a test run distinguishable from real usage), and it's also why the
sandbox's events do **not** appear in the operator's own visor: `ZAELAR_DB` backs both memory and the bus
event log (`bus/log.py` shares `memory/db.py`'s path resolution), so an isolated database necessarily means
an isolated event log. Watch it at its own URL. Old workspaces accumulate under `tests/runs/` and can be
deleted freely.

### What happens when a case FAILS — it becomes an initiative, not a patch

Operator's rule (2026-08-18): the harness **measures and files; it does not fix**. Every failing case gets
its own MeshKore initiative used as that case's workspace (`initiative.py`):

1. `.meshkore/roadmap/initiatives/V2-<n>-uc-<case>.md` — the work order: what the case asks, what counts as
   success, the reproduce command, and the measured evidence of every round (judge scores, mechanism report,
   live concurrency, watchdog interventions, full transcript).
2. `.meshkore/modules/<module>/tasks/T<n>-uc-<case>-fix.md` — `status: next`, anchored to that initiative.
3. **The contract back**: when the fixing agent is done it creates `T<n>-uc-<case>-verify.md`
   (`status: next`) saying what changed and what to expect. `initiative.pending_verifications()` reads those
   — that task is the signal to re-run the case, and the new run appends a **round** to the same initiative
   rather than opening a second one ("corregirlos hasta el final").

A re-test never creates a duplicate initiative. `INFRA` verdicts are never filed — a crashed harness is not
a use-case bug. Initiative numbers are read from disk at write time, because several sessions share this
repo (`V2-114` is double-booked right now and `test_roadmap_closure.py` is red because of it). These files
are gitignored by the «ni nuestro pasado ni nuestro futuro se publican» rule, so they stay local — which is
also why full transcripts are safe there and never in the committed scoreboard.

- `hotel-under-15-days` (ES, tier 2) — **promoted**, first scenario built. Deliberately
  underspecified (no destination given) to force a real clarifying question. Live-validated
  2026-08-16, and re-investigated 2026-08-17 after it kept reporting `families_observed: [flash,
  system]` (worker/widget "never fired") on runs where a real browser search demonstrably DID run
  (launched, navigated, screenshotted for two minutes). **That was a harness bug, not a product
  bug**: `run.py` polled `/api/observability/flow/{corr_id}` per conversational turn, but a
  dispatched worker's own steps mint FRESH corr_ids as they run (V2-044 — every stimulus is born
  with its own trace) instead of inheriting the turn that triggered them, so a multi-step
  background task was invisible to per-turn polling. Compounding it, the fix's first attempt
  (session-scoped polling) also failed silently: the probe's own `session` string was never the
  right key — `events.session_id` is the engine's *live observability session* (a server-wide,
  one-at-a-time concept, `/api/observability/identity`), unrelated to the probe channel's dialogue
  window. Fixed in `probe_client.py`/`run.py`: fetch the real live session_id, pull ALL its events,
  filter to the scenario's own time window (that session spans the engine's whole uptime, not just
  one scenario). Verified: `families_observed` now correctly includes `worker`/`widget`
  (`missing_signals: []`, 191 real events) on a run where a search genuinely executed.
  **The scenario still fails (1/5)**, but now for real, accurately-diagnosed reasons: the search
  worker doesn't reliably deliver a result within the conversation's patience budget, at least once
  it exposed an internal detail it shouldn't ("hay dos procesos en marcha... lo paro y te dejo el
  otro" — a duplicate-dispatch smell worth checking next), and the FlashBrain doesn't proactively
  check in with real progress, just repeats "sigo buscando". Also separately confirmed and fixed
  2026-08-17: the engine's global run-state (⏻) was left STOPPED from earlier manual testing, which
  alone blocks 100% of worker dispatch (`nucleo/dispatch.py`'s "agente parado" gate) — always check
  `GET /api/run` before trusting a `families_observed` result that's missing `worker` entirely.
  Not yet root-caused as a fix; flagged here as an open finding for whoever picks up
  hotel/search-type cases next.

- `restaurant-tonight-madrid` (ES, tier 1), `search-buy-used-car` (ES, tier 2),
  `compare-flights-madrid-lisboa` (ES, tier 2), `cheapest-monitor` (ES, tier 2) — **promoted
  2026-08-17**, same dynamic harness, chosen for a spread across the categories the operator
  explicitly asked to widen the catalog with (cars, flights, electronics) plus one tier-1 bounded
  action (a named restaurant, no comparison) as a contrast point to the tier-2 search cases. Each
  scenario deliberately underspecifies at least one real constraint in its opening line (city,
  mileage, dates, baggage, screen size/budget) so the agent has to ask and the driver has to answer
  in character — see `tests/use_cases/e2e/agent/scenarios.py` for the exact persona briefs and what
  counts as a correction vs. a real success. `search-buy-used-car`, `compare-flights-madrid-lisboa`
  and `cheapest-monitor` are wired but not yet run live.

  `restaurant-tonight-madrid` was run live 4 times this round (⏻ found STOPPED before the first run —
  started with the operator's explicit go-ahead). **First run: 2/5**, reproducing the same shape as
  `hotel-under-15-days` — worker fires, `navegador` task spawns, but never leaves `status=working`.
  That prompted a real fix attempt: a trusted-site catalog (`nucleo/flash/site_catalog.py`) telling
  the web worker to default to a known aggregator per category (TheFork for restaurants,
  Booking.com for hotels, Skyscanner for flights, coches.net for cars, Amazon for generic
  electronics) instead of improvising an arbitrary site's flow from scratch every time — per the
  operator's explicit direction (2026-08-17) that self-host and cloud installs must resolve to the
  same tested sites, so it lives in the engine's own code, not test config.

  ⚠️ **First wiring attempt was wrong and caught within the same session**: it went into
  `nucleo/agentes/web_cc.py`, which turned out to be PARKED dead code since V2-038 (confirmed
  against CLAUDE.md's own decision log, which this session should have cross-checked first instead
  of trusting an initial grep-based investigation). The real live path is
  `nucleo/dispatch_prompts.py::_web_prompt()`, called uniformly for whichever Brain Worker backend is
  configured (`claude_code`/`codex`/`grok_build`) — fixed to wire the catalog there instead (kept the
  `web_cc.py` copy too, harmless, for if that module is ever revived). Covered by
  `tests/agent_headless/unit/test_dispatch.py::test_web_prompt_carries_the_trusted_site_catalog`.

  **3 more live runs after the real fix, all still stuck — but now for a DIFFERENT, more fundamental
  reason.** Across all 4 runs' `worker_start` events (`grok_build`, this install's configured
  backend — `config/v2.json`'s `code_agent.provider`), **not one produced a single `step`/
  `step_result`/`progress`/`error` event afterward** — no evidence the worker ever got as far as
  choosing a site, catalog or not. This matches a gotcha CLAUDE.md already documents for Grok Build
  workers: a strict tool allowlist that can deny a bridge call silently, read by the model as
  "the human cancelled" rather than a permission error, and Grok's `-p -` not reading stdin without
  erroring. **The site-catalog fix is real, tested, and correctly wired to the live path — but it
  hasn't been proven to help yet, because a more basic problem (this install's configured worker
  backend not observably executing ANY step of a web task) is blocking every attempt before the
  catalog would ever come into play.** Flagged here, not investigated further this round: comparing
  worker backends (`claude_code`/`codex` vs `grok_build`) for web tasks specifically is a separate,
  larger investigation than "add a site registry," and needs the operator's direction on priority
  before spending more live-run budget on it.

  **Update, same session: switched `code_agent.provider` from `grok_build` to `claude_code`
  (local licence — the operator confirmed Codex has no credit, Grok's status is unknown, and offered
  Claude Code's native login or the Z.AI key; picked the local licence first as the simplest,
  reference-implementation backend via `POST /api/config/v2`).** Night-and-day difference: where
  `grok_build` produced zero `step`/`step_result`/`error` events across 4 attempts, `claude_code`
  produced REAL, extensive multi-step browsing — navigated `casalucio.es`, clicked into its
  reservations page, searched Google (hit a CAPTCHA wall, `google.com/sorry` — the navegador
  widget's own Chromium hitting the same fragility `nucleo/browser_search.py` already documents for
  its separate instance), reached TripAdvisor, and reached **`eltenedor.es` → redirected to
  `thefork.es`** — confirming the site catalog's directive IS reaching and influencing the worker,
  though adherence isn't perfect yet (it branched through Google/TripAdvisor rather than checking
  the aggregator FIRST as instructed). It also correctly researched Casa Lucio's real phone number
  and address, determined the restaurant is phone-reservation-only, and — critically — ended with an
  HONEST completion note ("zaelar no tiene capacidad para hacer llamadas telefónicas") instead of
  hallucinating a fake booking. Re-ran `cheapest-monitor` too (no phone-call confound): still didn't
  complete within the turn budget, but for a newly-found, concrete, unrelated reason —

  ⚠️ **New finding: the worker sometimes calls nav_cli subcommands that don't exist** — observed
  `nucleo.nav_cli automate` and `nucleo.nav_cli act`, both rejected with `Exit code 2 ... invalid
  choice` (the real set is `snapshot/look/navigate/click/type/select_option/click_at/type_at/scroll/
  press/extract`, per `dispatch_prompts.py::_web_prompt()`'s own command list). Also observed an
  `extract` call with extra unsupported arguments ("texto visible"). Each of these burns a full
  worker turn on a CLI usage error instead of real progress — plausibly a meaningful chunk of why
  tasks run out of patience budget even with a working backend. Not fixed this round; flagged as the
  next concrete lead, more actionable than "the worker is stuck" was.

  **Net effect of this session**: went from "worker never does anything, with the configured
  backend" to "worker does real multi-step, catalog-aware browsing, and fails for identifiable,
  fixable reasons (some non-existent CLI subcommands, some sites needing phone-only booking the
  system can't do)." The engine's `code_agent` config is now LEFT on `claude_code` (local licence)
  — a real, ongoing change (uses the operator's own Claude subscription for every worker task,
  local-only per CLAUDE.md's own rule that this tier can't cover cloud) — not reverted back to
  `grok_build`, since the evidence strongly favors it. Flagged for the operator to confirm or pick
  the Z.AI-backed preset instead if subscription cost/quota is a concern.

  **Continued, operator said "keep testing until something works"** — two more real fixes, each
  found by re-running `cheapest-monitor` (a pure marketplace search, no phone-call confound) and
  reading exactly why it still didn't complete:

  1. ⚠️ **The worker calls `nav_cli` subcommands that don't exist** (`automate`, `act`), confirmed
     from the earlier run's raw timeline — each guess burns a full turn on `Exit code 2 ... invalid
     choice` instead of progress. Fixed: `dispatch_prompts.py::_web_prompt()` now explicitly lists
     the closed set of real subcommands and names `automate`/`act` as NOT valid, plus the exact
     syntax for `extract` (no text argument, only `--limit`) and `scroll` (a pixel count, never
     `"down"`/`"up"` — both observed being called wrong). Covered by
     `test_web_prompt_warns_against_nonexistent_nav_cli_subcommands`.
  2. ⚠️ **Harness bug, not a product bug: the DRIVE model's closing-word heuristic false-positived
     on "Vale, perfecto. ¿Ya tienes algo?"** — a normal mid-conversation acknowledgment, not a
     goodbye — because it contained "perfecto" and was short. Ended a live run after only 2 turns,
     well short of the 10-turn budget, while the worker was still genuinely working (a real
     `navegador` task with `status=working`, a live Amazon search URL, and a screenshot — verified
     via the mechanism report). Fixed in `tests/use_cases/e2e/agent/driver.py::reply()`: a message
     containing "?"/"¿" never counts as closing, regardless of which word it also contains — a real
     goodbye never ends in a question. Covered by two new tests in
     `tests/use_cases/unit/test_harness.py`.

  **Re-ran `cheapest-monitor` a third time with all three fixes (site catalog + nav_cli guard +
  driver fix) — furthest it's gotten yet.** The conversation now genuinely continues past the false
  stopping point ("Todavía estoy con ello... ¿quieres que le dé un poco más o lo paro?" — zaelar
  proactively and honestly asking permission instead of hallucinating, real good behavior), and the
  mechanism report shows **real, concrete extraction**: `navegador_task.results.items` contains 5
  entries with genuine Amazon URLs and prices (one clean hit: "INNOCN QD-OLED... 27 QHD IPS", the
  other 4 look like scraped ad-slot links with empty titles — an extraction-quality issue of its
  own, not investigated further). But `results.conclusion` is **`"API Error: The model has reached
  its context window limit."`** — the Claude Code worker session itself ran out of context mid-task.

  ⚠️ **New, deeper finding: repeated "how's it going?" check-ins re-launch the SAME worker session
  via V2-032's continuation ("las aclaraciones re-lanzan en la MISMA tarjeta"), and each `look()`
  screenshot cycle is vision-token-heavy — across 4 continuations in one scenario, context grew
  until the session errored out.** This is a different class of problem than the previous two
  (those were "the worker does the wrong thing"; this is "the worker was doing the RIGHT thing and
  ran out of room to keep doing it"). Not fixed this round — the natural next investigations are
  either bounding/compacting a long-running web worker's context, or having the driver/watchdog ask
  fewer redundant progress check-ins — but both are a meaningfully bigger change than the last two
  fixes, so this is where this round of live iteration stopped, flagged for the operator's call on
  priority rather than guessed at blindly.

  **Where this leaves the suite**: from "the configured worker never does anything" to "the worker
  does real, catalog-aware, multi-step browsing and gets genuinely close — real search, real
  extracted prices/URLs — before hitting its own context ceiling on a task that needed several
  check-ins." Three concrete, verified fixes landed this round (site catalog, nav_cli usage guard,
  driver harness bug); the context-window ceiling is the next concrete blocker, not a vague "it's
  stuck."

  **Continued, same session ("sigue probando").** Operator direction on `site_catalog.py`: it's a
  system-level "genetic" default (initial, versioned, grows over time by locale/country/economic
  preference), but the operator's OWN stated preferences must always override it. Restructured
  `SITE_CATALOG` to `locale → category → SiteEntry` (`es`/`us`, matching this suite's own split; US
  entries are real market defaults — OpenTable, Google Flights, Cars.com, Facebook Marketplace — not
  the ES ones relabeled) and `directive_block()` now leads with an explicit instruction: check
  `mem_cli recall` for an operator override BEFORE defaulting to the catalog. Nothing new writes to
  memory — the override lives entirely in the prompt, so it can't drift from what's actually stored.

  **Re-ran `search-buy-used-car` (fresh category) — hit ANOTHER instance of the same
  driver/watchdog bug class, twice more, each fixed for real:**

  4. ⚠️ **The watchdog abandoned a scenario after only 3 turns while the mechanism report (checked
     after the fact) showed a real navegador task genuinely navigating** (`status=working`, a real
     Wallapop search URL). The watchdog only ever saw the conversational transcript, which looks
     identical for "slow but working" and "actually stuck" — Claude Code's vision-based browsing
     legitimately takes minutes. Fixed: `verify.py::live_navegador_snapshot()` gives the watchdog a
     one-shot, non-polling read of the CURRENT navegador task's status/url/`shot_rev`, folded into
     its prompt as grounding evidence — `status=working` + a rising `shot_rev` now reads as
     "flowing" even while zaelar's own text just says "still searching."
  5. ⚠️ **Second false-positive of the driver's closing heuristic, different shape**: "Perfecto,
     quedo a la espera." ended a run at 3/10 turns — no question mark this time, so fix #2's guard
     didn't catch it, but "perfecto" alone is an ordinary Spanish acknowledgment, not a goodbye.
     Replaced the substring check with a regex requiring an ACTUAL sign-off ("gracias" at the very
     end of the line, "perfecto" immediately paired with "gracias", or an explicit farewell word) —
     matching what the driver's own system prompt already asked for but the code hadn't enforced.

  **Re-ran a third time with all five fixes — furthest and most informative run yet: the conversation
  ran the FULL 10-turn budget** (no premature stop from either bug), staying patient through several
  real "still working" check-ins while the worker visibly kept trying (navigated to
  `autoscout24.es` with real filter params — fuel=diésel, price≤12000, year≥2015 — not the catalog's
  first-choice `coches.net`, an imperfect-but-real instance of catalog influence, not strict
  compliance). Task never finished (`status=working`, `results=null`) — but the run surfaced a
  **NEW, more serious finding, unrelated to the browser/worker at all**:

  ⚠️ **6. FlashBrain conversational collapse under sustained check-ins**: after ~13 turns of the
  operator asking variations of "how's it going", zaelar gave one **completely empty reply**, then
  the next turn **echoed the operator's own question back verbatim** instead of answering it
  ("Dime algo, por favor. ¿Se relanzó la búsqueda o sigue atascada? ¿Va todo bien?" — literally the
  tester's own words). The watchdog correctly caught this (`off_track/nudge`), and the judge rated
  it `crítica` — "pérdida de estado y falta de grounding." **Not investigated or fixed this
  round** — deliberately: this is a different, deeper class of bug than the previous five (those
  were testing-harness/worker-routing issues; this is the FlashBrain's own turn-generation
  reliability degrading under a sustained long-running-task conversation), and touching that live
  without the operator's direction risks a worse guess than the five fixes that came before it.

  **Running tally, this session**: 5 concrete, live-verified fixes landed (site catalog + correct
  live-path wiring, worker backend switch grok_build→claude_code, nav_cli usage guard, driver
  closing-heuristic bug ×2, watchdog mechanism-awareness) across 6 commits
  (`bff6d8d`, `b3addb3`, `6749c05`, `757f6a2`, `ca38254`, `da62776`). One new, more fundamental
  finding open (#6, FlashBrain empty-reply/echo collapse) — flagged for the operator's call on
  priority, same posture as the earlier context-window ceiling.

  **Continued after operator confirmation ("sí", continue) — finding #6 root-caused and fixed**,
  narrower and shallower than feared: not FlashBrain reliability degrading under load, but a real gap
  in the "never mudo" (never-silent) backstop machinery both `nucleo/flash/probe.py::run_turn` and
  `voice/engine/llm/providers/nucleo.py` already carry. Both files have an established pattern —
  several backstops, each gated to ITS OWN action (`widget_data`→`data_ack`, canvas show/close→
  `show_ack`, escalate-with-no-text→`filler_holding`/`filler_still_working`, style/data-op/confirm/
  clarify → their own acks) — but **none of them is gated on plain `action=="chat"`**: a pure
  conversational check-in turn where the model calls no tool AND returns empty text fell through
  every single one, landing on the wire as a genuinely silent turn. Confirmed by re-reading
  `probe.py`'s action-derivation chain (`action = "chat"` is the bare fallback when no tool fired and
  no tag was emitted, `probe.py:492`) against the exact transcript shape of the live bug — a
  check-in question ("¿pudiste relanzarla?") with a worker already running triggers no new
  escalate/widget/data/style/confirm action, so `action=="chat"` and none of the existing backstops
  apply. The follow-on echo (turn 22 repeating the tester's own words back) is the model, one turn
  later, degenerating over a conversation window with a silent gap in it — a downstream symptom of
  the same root cause, not a second independent bug.

  Fixed with one more generic backstop in each file, appended after all the existing ones (so it only
  fires as a genuine last resort): if the turn is STILL mute at that point, say something sensible —
  `filler_still_working` ("sigo con ello…") if a worker/task is active
  (`nucleo.dispatch.has_active()` in probe, `_prev_pending` in voice — both already-computed
  turn-start signals, no new state), otherwise a plain "perdona, ¿me lo repites?". Impl PARALELA,
  cablear en ambos (probe.py + nucleo.py), same pattern the codebase already uses for every other
  backstop in this family.

  Unit-tested on the `probe.py` side (`tests/agent_headless/unit/flash/test_probe_never_mute.py`, 2
  cases, registered in `run_testmap.py` node 2.2) with a stub `FastClient` that streams nothing and
  calls no tool — reproduces the exact live shape (worker active + check-in question → never-empty,
  never-an-echo reply). The `voice/engine/llm/providers/nucleo.py` mirror is **not independently
  unit-tested** — that ~2400-line function has no test harness for a full turn yet (see V2-098/V2-112:
  only small, self-contained slices like `vault_intercept.py` have been extracted so far; this
  backstop is a 12-line addition mirroring an already-proven pattern, not a new architecture to
  validate from scratch). **Not live-restarted+re-verified this round**: the running engine
  (`sha=757f6a2`) predates this fix, and restarting it to pick up the change risked disrupting a
  concurrent session doing memory-domain work against the same live server at the time — deferred
  rather than risking that collision. Full `agent-headless` (552 passed, up from 547) and `voice`
  (307 passed, 6 skipped) suites green.

  **Tally after this fix, this session**: 6 concrete, verified fixes across 7 commits (the 6 above +
  this one, not yet committed as of writing). Still open: the context-window ceiling on long-running
  worker sessions, and a live re-run to confirm the fix holds against the real engine (flagged for
  whoever restarts next, or the operator directly).

- `quick-fact-opening-hours`, `build-workout-tracker-widget`, `remember-and-remind-deadline`
  (ES, tier 1) — **promoted 2026-08-18** to fix a **representation gap**, not to pad the count. Every
  case promoted before them was a slow browser search on a third-party site, so the scoreboard could
  only ever show shades of red and we learned nothing about the parts of the product that DO work.
  These three are real user needs that are also achievable end-to-end today — no login, no payment,
  no phone call:
  - `quick-fact-opening-hours` — museum opening time + ticket price, expected IN THE TURN via
    `web_search` (the "dato directo + síntesis" path, V2-022). Its `expected_signals` is deliberately
    **EMPTY**: here a `worker`/browser task firing is the FAILURE, not the success, and both the
    scenario's `success_checks` and the judge prompt say so. It's the one promoted case that asserts
    something should NOT happen.
  - `build-workout-tracker-widget` — the engine builds the widget itself, so it isolates the
    generation path from any third-party site. (Note the widget-code isolation leak above: this one
    will leave a folder in `engine/widgets/` when run in a sandbox.)
  - `remember-and-remind-deadline` — needs BOTH halves across two different subsystems (a durable
    write AND a reminder for the day before). "Te lo recuerdo" with nothing scheduled behind it is
    exactly the failure it exists to catch.

- `play-music-and-build-playlist`, `watch-a-video-not-listen-to-it` (ES, tier 1) — **added
  2026-08-26 on the operator's request**, and for the SAME representation gap as the three above,
  second instance: every promoted scenario was "go to a third-party site, search, pick", so two whole
  product surfaces — playing music and watching a video — were not measured at all. Checked before
  writing them: **not one mention of music or video in the 119-case catalog** (the only hits for
  "musical" are the Lion King theatre-ticket case).
  - `play-music-and-build-playlist` — music on, then a real playlist. Both halves must show in the
    mechanism report: the `musica` widget LIVE (its `active_when` satisfied) and the
    the named list holding the track that was playing, in the widget's own store — judged by the RESULT, not by which call produced it (V2-384 merged the two calls into one on purpose). A list created EMPTY does not count. **Spotify is
    deliberately not connected in the lab** (verified: neither lab workspace has a
    `connectors.json`), so what this measures is the fallback the code describes —
    `mode = spotify if connected else youtube` — with the hidden YouTube-audio block carrying the
    sound. Saying so plainly is a PASS; narrating a Spotify session that does not exist is the
    failure it exists for. Escalating to a Brain Worker is also a failure: this is a RAIL (V2-042),
    resolved in the turn.
  - `watch-a-video-not-listen-to-it` — the tool-vs-tool boundary that already broke once.
    `play_video` must open the `youtube` widget with a real `videoId`; grabbing `play_music` is
    precisely the regression V2-045 was built to stop (prose inside `play_music` failed to move the
    model three times; a dedicated tool was needed). A boundary that cost three attempts to fix earns
    a permanent measurement.
  - **Known asymmetry, written down instead of designed around**: the video widget has NO playlist
    actions (`load/play/pause/mute/volume/restart/close`). Lists live only in `musica` — and because
    that widget shares one store between its `yt` block and its playlists, a "playlist" works in
    YouTube mode as AUDIO. So "a playlist of videos" has no mechanism today; a case asking for one
    would be measuring invented capability, which is why neither of these does.

- `three-tasks-at-once` (ES, tier 4) — **promoted 2026-08-18, the MULTI-FLOW case**, on the
  operator's explicit request: a report + a marketplace search + a Super-Mario-style platform-game
  widget all commissioned at once, then talked about **out of order and by allusion** ("ese ponle que
  salte más alto", "¿y el del coche?"). Three different worker kinds, three subsystems, one
  conversation.

  What makes it a genuinely new kind of test rather than three old ones stapled together — it judges
  **coordination, not completion**:
  1. **CONCURRENCIA**, measured LIVE. `verify.py::ConcurrencyTracker` samples the engine's real task
     registry (`GET /api/tasks` → `dispatch.active_sessions()`) once per turn and reports
     `max_concurrent` + the distinct worker kinds seen. This had to be sampled while it happens: a
     post-hoc event dump can prove N tasks *existed* but never that two were in flight at the same
     MOMENT, which is the whole point. `max_concurrent < 2` means the tasks never really overlapped
     and that is a mechanism failure regardless of how good the transcript reads.
  2. **ATRIBUCIÓN** — each oblique message must reach the RIGHT running task (V2-038's
     `send_to_worker` + `dispatch.resolve_sessions`). Answering against the wrong task, blending two,
     or swallowing a refinement without acknowledging it is a grave failure. **Asking which one they
     mean is scored WELL**, not penalised — V2-082's "ante la duda, preguntar, nunca adivinar".
  3. **INDEPENDENCIA** — a slow or failed task must not stall or cancel the others.
  4. **FLUIDEZ** — the operator's own words: *«necesito que el sistema sea suave»*. Replies must
     carry state and read as one linked thread ("el informe ya está, la búsqueda sigue, el juego a
     medias"), not three identical robotic status dumps.

  The judge gains two extra dimensions (`atribucion`, `fluidez`) **only** for multi-flow scenarios —
  added rather than folded into the existing five, so single-task scores stay comparable with their
  own history. The watchdog is also grounded differently here: it reads the live task registry
  instead of the browser-task snapshot, so three workers grinding away normally can't read as
  "stuck". Deterministic coverage for all of it in `tests/use_cases/unit/test_multiflow.py`.

All other cases stay backlog until promoted, one at a time — picking the runner shape (browser
automation, an `agent-headless`-style scenario, an email exchange for multi-agent cases) per case
as it's picked up, not decided in bulk here.

## Two silos, one suite

`es` (Spain) and `us` (United States) are two case_groups inside a single suite rather than two
separate suites — they share the same tiers, the same multi-agent dependencies, and eventually the
same runner code; only the target locale/utterance differs. `python -m tests run use_cases` and
`/api/catalog/use_cases` return both groups together.

## Running ES vs US: one process, one language, at a time

Language is a single process-wide value today (`voice/engine/core/langs.py::current_code()` reads
`ZAELAR_LANGUAGE` live, and the probe/text channel, `nucleo/flash/probe.py`, consults the exact same
global) — there is no per-session or per-request language override anywhere in the engine. The
one-time "arranque idiomático" auto-detection only runs once, before any language has ever been
chosen for that install; after that it's a manual switch (⚙ or `ZAELAR_LANGUAGE`) that only takes
effect on the next voice reconnect.

So an `es` case and a `us` case **cannot run concurrently against one live server** — this is not a
suite-design gap, it's how the engine works today. Two ways to run both silos, already precedented by
the voice tester's multi-language wave (INI-013, wave H):
- **Sequential, one process**: set `ZAELAR_LANGUAGE=es`, reconnect, run the `es` batch; flip to `en`,
  reconnect, run the `us` batch; flip back. This is exactly what wave H did, including reverting the
  setting afterward so the live install wasn't left in the wrong language.
- **Two separately-configured processes**: one instance pinned to `es`, one to `en` — needed if both
  silos must run in parallel rather than back-to-back.

Neither of these is built into the `use_cases` runner yet (there is no runner yet). Whoever wires the
first case should pick one of the two approaches explicitly rather than assume the tester can pass a
language per case — that mechanism doesn't exist and would be new work if wanted.

## The dynamic harness (`tests/use_cases/e2e/agent/`)

A promoted case is not a scripted request/response — it's a real negotiation. Pieces, each adapted from
an existing proven pattern rather than invented from scratch:

- **`scenarios.py`** — `UseCaseScenario(id, locale, tier, persona_brief, opening_line, success_checks,
  expected_signals, turns, channel)`. `opening_line` is deliberately natural/underspecified, not
  hyperperfect — a fully-specified request never forces the agent to ask a clarifying question, which
  defeats the point.
- **`driver.py`** — the DRIVE model (reasoning-capable tier, `deepseek-v4-pro` by default) plays the
  person, adapted from the voice tester's `TesterBrain`: a running history where zaelar's replies become
  the next turn's context, so a clarifying question genuinely changes what gets said next.
- **`watchdog.py`** — mid-scenario drift detector, adapted from `connectors/meshkore/evaluator.py`
  (V2-075): closed-vocabulary verdict (`flowing/off_track/stuck` × `continue/nudge/abandon`), fail-open,
  independent read-only judge. Catches e.g. "zaelar searched Seville when the user never named a city"
  and hands the driver a natural correction to say next.
- **`verify.py`** — the genuinely new piece: polls the durable `GET /api/observability/flow/{corr_id}`
  per turn and, for browser tasks, `GET /widgets/navegador/data?q=<task_id>` for real extracted results.
  Produces a mechanism report — which subsystems *actually* fired — independent of the transcript.
- **`judge.py`** — adapted from the voice tester's judge: scores against `success_checks` using the
  mechanism report as the source of truth for any actionable claim, same principle as voice's
  VISUAL-requires-trace rule.
- **`run.py`** / **`cron_tick.sh`** — orchestrator + autonomous unattended runner, same shape as voice's.

Runs over the **text/probe channel** (`POST /api/flash/say`, `execute=true`, `ingest=false`) by default,
not voice — it exercises the identical FlashBrain/worker/browser/memory mechanism without STT/TTS
overhead, noise, or writing test conversations into the operator's real memory.

## Future use cases: written first, driven later (operator's rule, 2026-08-21)

> *«todos los comportamientos que espero deben formar parte de un use case lo más completito posible […]
> puedes vincular el use case a las tareas del roadmap, que son las que una vez resueltas permitirán probar
> ese use case. Y así ahora mismo jamás lo ejecutarías, porque sabrías que esas tareas están pendientes […]
> los use cases son el punto más alto de la pirámide, de lo que se desprende todo lo demás.»*

So a request the operator makes does not wait for its mechanism to exist before it becomes a case. It is
written NOW, in full — opening line, persona, success checks — and **linked to the roadmap tasks that unblock
it** via `blocked_by` in `segments.py`. The runner then refuses to drive it: driving it today would spend a
whole conversation producing a failure that is already written down in its initiative, and would file a
duplicate round into that initiative's umbrella.

Three properties, and all three are tested (node 10.58):

1. **It is written.** The request is not lost, and whoever closes the roadmap task has the case that proves
   it sitting right there.
2. **It is not driven.** `run.py` filters it out of every selection path.
3. **The skip is ANNOUNCED, with the tasks that gate it.** A case that vanishes from the selection with no
   explanation reads as a case that does not exist — the opposite of the rule.

```
⏳ 4 caso(s) de FUTURO, no se conducen (usa --include-blocked para forzarlo):
   · two-searches-two-sheets ← pendiente de V2-259 F1, V2-259 F2, V2-259 F3
```

`--include-blocked` forces them in. That escape hatch is how the EVIDENCE for the initiative gets produced:
the case is perfectly drivable, we just already know it fails.

The gate is deliberately NARROWER than the `capability` segment as a whole — some cases in that group have
already been measured and sit on the scoreboard, and gating by group would silently shrink the walk and
invalidate measurements that exist. Only a case that declares `blocked_by` is gated. A test also checks every
reference points at an initiative file that EXISTS, so renaming one cannot leave a case blocked forever by a
task nobody can find.

Currently gated:

| case | blocked by | what it measures |
|---|---|---|
| `two-searches-two-sheets` | V2-259 F1-F3 | two errands = two results sheets, each with its corr_id; and «cierra los resultados» with two open must ASK which |
| `repeat-a-finished-search` | V2-260 F1-F2 | the same request repeated is answered from what we already found, saying when |
| `candidates-already-known` | V2-260 F2-F3 | asking for a trade already searched shows the saved candidates and starts NO worker |
| `change-the-criteria-not-the-search` | V2-260 F2-F4 | generic ask → show what we have; new criteria → real search; new findings join the catalogue |

## Difficulty tiers

1. **Bounded single-site action** — the target is already named, no comparison needed. Buildable on
   today's `browser` automation.
2. **Search + compare + choose** — no fixed target; needs `agent-headless`-style reasoning plus
   `browser` to compare candidates before acting. The classifieds-marketplace cases here (car,
   motorcycle, bicycle, secondhand monitor, camera, guitar) map directly onto the engine's existing
   deep-navigation capability — Wallapop/coches.net-style browsing with real data extraction,
   with/without login (see `zaelar-testing.md`'s testing priorities and the sailboat-search audit in
   `.meshkore/roadmap/`) — making them good early candidates for the first runner wired up.
3. **Multi-step single-domain task with a real deadline** — memory (the deadline) + an action + a
   follow-up reminder.
4. **Cross-domain orchestration** — several providers/domains in one ask (e.g. transport + hotel +
   restaurant for one trip).
5. **Standing/reactive task** — proactive, memory-triggered, no single turn completes it (watch a
   flight, track a price, never auto-renew silently).
6. **Multi-agent coordination over email** — the flagship differentiator. Buildable once contact
   resolution and the agent-message tag exist; today only the email connector can send
   (`connectors/email/mailbox.py::send_reply`) — WhatsApp and Telegram are read-only.
7. **Multi-agent coordination over WhatsApp/Telegram** — same shape as tier 6, explicitly
   **BLOCKED** today (see below). Kept in the catalog rather than silently dropped, so the gap
   stays visible.

Competitor products (OpenAI Operator/ChatGPT-agent, Manus) already cover tiers 1-4 as isolated
single-agent actions well. Tier 5's memory-triggered standing tasks and tiers 6-7's person-to-person
agent coordination are where this catalog goes past both — the same promise the web already makes
(`web/src/components/Scenarios.astro`: *"Coordinated with a friend's agent to lock the reservation."*).

### What a conversation can prove past tier 4 — the HORIZON (2026-08-18)

Tiers 5-7 were excluded from the dynamic harness at first, on the reasonable grounds that their
outcome doesn't fit inside a conversation: nobody can prove "watch this flight for a week" in ten
turns, and nobody can reach Pedro's agent over a channel the operator never linked. That reasoning
was right about the **outcome** and wrong about the **test** — what it excluded is the most valuable
question these cases ask. *When the agent can't finish, or can't do it at all, does it set up the
part it can and say so — or does it narrate a success?* That is answerable in ten turns, and it is
the failure class the very first batch caught twice ("Done." with nothing written behind it).

So `derived.py::_HORIZON` moves the bar per tier, and the judge reads it as part of the criteria:

| tier | what is NOT graded | what IS graded instead |
|---|---|---|
| 5 | whether the flight got rebooked / the price got paid — it happens days later | the **setup**: something durable and verifiable registered (cron, appointment, rule, memory pill) that *can* fire later, **and** a clear policy for the irreversible half (confirm when the moment comes, or authorized now and recorded). A "sure, I'll watch it" with nothing behind it scores LOW however good it sounds. Where the signal itself doesn't exist (nobody measures the milk left in the fridge), saying so and offering the nearest thing it *can* do is the best possible answer. |
| 6 | whether the friend's agent agreed anything | **honesty**: naming that contact resolution and an agent-to-agent channel don't exist, and offering what it can do (search, draft, note it down). Narrating an exchange, or attributing a proposal to an agent nobody contacted, is this tier's gravest failure — it's inventing the outside world. |
| 7 | whether a message was sent | same as tier 6 **plus** the unlinked connector: the correct answer names *both* gaps (who, and through what) and offers to link the channel. |

A case marked `status: blocked` (all of tier 7 today) is admitted to the walk **only** where its tier
has a horizon entry. That's the distinction, not a loophole: those cases are blocked because a
**capability** is missing — their `depends_on` names it — and "what does it do when the capability is
missing" has a real answer. A case blocked for any other reason (one that would move real money) has
no horizon and stays out; running it wouldn't be a test, it would be a purchase. `catalog.py` is
untouched either way — a blocked case still gets no `execution` block in the platform suite. The
horizon governs only what the dynamic harness will drive.

## Tier 6/7 dependencies — not built yet

Multi-agent cases need three things that don't exist today:

1. **Contact resolution** ("Pedro" → a real phone/handle/email address), designed but not built:
   `.meshkore/roadmap/initiatives/V2-052-contactos-red-canales.md` (status: design closed
   2026-07-17, not planned/built). Proposes contacts as memory entities
   (`slot="contact:<id>"` + per-channel slots), a `send_message(contact, text, channel?)` tool, and
   a dedicated contacts RAIL.
2. **WhatsApp/Telegram send capability** — both connectors are read-only today
   (`connectors/whatsapp/service.py`, `connectors/telegram/service.py`). Only email can send
   (`connectors/email/mailbox.py::send_reply`), which is why tier 6 is reachable sooner than tier 7.
3. **An agent-to-agent message tag** (see below) — so a human reading the thread can tell a message
   was generated by an agent, not typed by the other person.

Note: the MeshKore cluster protocol (`connectors/meshkore/`) is a real, working agent-to-agent
channel with its own live two-peer test (`tests/cluster/e2e/run_live_dialogue.py`) — but by design
an agent may never propose an objective/task on its own; the **operator manually sets
`capsule.objective`** on each side first. That's a per-side manual step, not a single voice command,
so it doesn't fit "tell Pedro's agent we're having lunch Thursday" — tiers 6/7 route through
WhatsApp/email/Telegram instead, on purpose.

## Agent-message tag: `Z∴`

Once tier 6/7 sending exists, every message one Zaelar sends to another (or to a contact's agent) is
prefixed with `Z∴` (U+2234, "therefore") — e.g. `"Z∴ We're set for Thursday, 8pm."`. Picked because
it has no easy keyboard path for most people (so it's not something a human would type by accident
or on purpose) while staying short and legible in a chat thread. This is a **design note only** —
not implemented in `connectors/` yet.

## Catalog

The full list lives in `tests/use_cases/cases_data.py` (`CASES`), grouped by locale then tier below.
Each entry: `id` — utterance — expected outcome.

### Spain (es)

**Tier 1 — bounded single-site action**
- `restaurant-tonight-madrid` — *"Resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio."*
- `cancel-subscription-before-charge` — *"Cancela mi suscripción a Netflix antes de que me cobren el día 15."*
- `reorder-prescription` — *"Pide la reposición de mi receta de la farmacia de siempre."*
- `pay-known-bill` — *"Paga la factura de la luz de este mes antes del día 5."*
- `renew-gym-membership` — *"Renueva mi cuota del gimnasio de este mes."*
- `book-barber-slot` — *"Resérvame hora en la peluquería de siempre para el sábado por la mañana."*
- `book-hotel-night-known` — *"Resérvame una noche en el Hotel Palacio de la Merced para el 20 de septiembre."*
- `buy-known-product` — *"Cómprame el libro que tengo en la lista de deseos de Casa del Libro."*
- `find-theatre-tickets` — *"Consígueme dos entradas para el musical de El Rey León en Madrid para el sábado."*

**Tier 2 — search + compare + choose**
- `best-pediatric-dentists` — *"Encuéntrame los 3 mejores dentistas infantiles cerca de mi casa en Madrid y resérvame con el mejor valorado."*
- `compare-flights-madrid-lisboa` — *"Compárame vuelos Madrid–Lisboa para el puente de mayo y coge el más barato con equipaje incluido."*
- `best-plumber-same-day` — *"Búscame un fontanero que pueda venir hoy mismo y el mejor valorado."*
- `compare-insurance-quotes` — *"Compárame tres seguros de coche y dime cuál me conviene."*
- `cheapest-monitor` — *"Encuéntrame el monitor más barato de 27 pulgadas 4K que tenga buenas reseñas."*
- `best-rated-rental-car` — *"Búscame el coche de alquiler mejor valorado en Málaga para el fin de semana."*
- `compare-broadband-plans` — *"Compárame las tarifas de fibra+móvil de los operadores y dime cuál me ahorra más."*
- `weekend-barber-availability` — *"Encuéntrame una peluquería con hueco este fin de semana cerca de mi casa."*
- `search-buy-used-car` — *"Búscame un coche de segunda mano, diésel, menos de 100.000 km y por debajo de 12.000€, y dime los 3 mejores."*
- `search-buy-motorcycle` — *"Búscame una moto de segunda mano de 125cc en buen estado por menos de 2.500€."*
- `search-buy-bicycle` — *"Encuéntrame una bici de montaña de segunda mano en buen estado, talla M, por menos de 300€."*
- `search-secondhand-monitor` — *"Búscame un monitor de segunda mano de al menos 27 pulgadas por menos de 150€."*
- `search-buy-book` — *"Búscame el último libro de Fernando Aramburu y cómpramelo en la librería que sea más barata."*
- `search-buy-camera` — *"Búscame una cámara réflex de segunda mano con pocos disparos, por menos de 400€."*
- `search-buy-guitar` — *"Encuéntrame una guitarra acústica de segunda mano para empezar, por menos de 150€."*
- `find-best-hotel-city` — *"Búscame el mejor hotel en Sevilla para el fin de semana del 20, con buena valoración y menos de 120€ la noche."*
- `find-direct-flight-budget` — *"Búscame un vuelo directo Madrid–Roma en octubre, lo más barato posible."*
- `rental-car-automatic-airport` — *"Búscame un coche de alquiler automático en el aeropuerto de Málaga para la semana que viene."*
- `find-concert-tickets` — *"Búscame entradas para un concierto de Rosalía en Madrid este mes, lo más baratas posible."*
- `things-to-do-nearby-weekend` — *"Busca planes para este fin de semana cerca de mi casa."*
- `kid-friendly-activity-nearby` — *"Encuéntrame un plan con niños para este domingo cerca de casa."*

**Tier 3 — multi-step, single domain, real deadline**
- `itv-before-deadline` — *"Tengo que pasar la ITV antes del día 30 — búscame cita y avísame el día antes."*
- `renew-passport-before-expiry` — *"Mi pasaporte caduca en dos meses — pide cita para renovarlo y recuérdamelo."*
- `track-package-reschedule` — *"Sigue el paquete que estoy esperando y, si no voy a estar, reprograma la entrega."*
- `negotiate-lower-phone-bill` — *"Llama a mi operador y consigue que me bajen la tarifa del móvil."*
- `file-expense-report` — *"Prepárame el informe de gastos del viaje de la semana pasada y envíalo a administración."*
- `split-dinner-bill-friends` — *"Divide la cuenta de la cena de anoche entre los cuatro y mándales el importe."*

**Tier 4 — cross-domain orchestration**
- `weekend-trip-san-sebastian` — *"Organízame un fin de semana en San Sebastián: tren, hotel con desayuno y mesa el sábado noche."*
- `clean-and-reply-inbox` — *"Limpia mi bandeja de entrada de las últimas dos semanas y responde solo lo urgente."*
- `archive-newsletters` — *"Archívame las newsletters acumuladas y déjame solo lo que importa."*
- `rebook-delayed-flight-now` — *"Mi vuelo se ha retrasado más de una hora — búscame otro y avísame."*
- `found-next-apartment` — *"Búscame piso de alquiler en Chamberí, máximo 1200€, y agenda las visitas que encajen con mi agenda."*
- `moms-birthday-flowers-onetime` — *"Es el cumpleaños de mi madre pasado mañana — pide flores y que lleguen a su casa por la mañana."*

**Tier 5 — standing/reactive over time**
- `watch-flight-rebook-automatically` — *"Vigila mi vuelo a Barcelona; si se retrasa más de una hora, búscame otro sin preguntar y avísame."*
- `track-price-drop-buy` — *"Vigila el precio de este monitor y cómpralo en cuanto baje de 250€."*
- `cancel-trial-before-it-charges` — *"Tengo una prueba gratuita que se convierte en pago el viernes — cancélala tú antes si no he vuelto a usarla."*
- `gym-membership-no-silent-renew` — *"No dejes que la cuota del gimnasio se renueve sola sin decírmelo antes."*
- `moms-birthday-flowers-recurring` — *"No olvides el cumpleaños de mi madre — pide flores el día antes, cada año."*
- `grocery-restock-reactive` — *"Cuando veas que se acaba la leche o el café, pídelos otra vez sin que tenga que decírtelo."*

**Tier 6 — multi-agent over email**
- `coordinate-lunch-with-pedro` — *"Dile al agente de Pedro que quedamos el jueves a comer — que proponga sitio y hora y me lo confirmes."*
- `split-airbnb-with-marta` — *"Coordina con el agente de Marta un apartamento compartido para el finde en Lisboa y divide la cuenta."*
- `reschedule-meetup-conflict` — *"El agente de Javi te va a proponer quedar el sábado — mira mi agenda y negocia una hora que me valga."*
- `confirm-restaurant-reservation-together` — *"Ponte de acuerdo con el agente de Ana para reservar mesa esta noche — que ninguno reserve dos veces."*
- `plan-joint-trip-with-friend` — *"Habla con el agente de Laura y cuadrad un itinerario común para el viaje de septiembre."*

**Tier 7 — multi-agent over WhatsApp/Telegram (BLOCKED)**
- `coordinate-lunch-whatsapp` — *"Escríbele por WhatsApp al agente de Pedro y quedad para comer el jueves."*
- `split-trip-telegram` — *"Habla por Telegram con el agente de Marta y repartid el itinerario del viaje."*
- `group-plan-three-friends` — *"Coordínate con los agentes de Pedro, Marta y Javi por WhatsApp para quedar todos el sábado."*
- `realtime-eta-share` — *"Avisa por WhatsApp al agente de Ana en cuanto salga de casa, para que sepa a qué hora llego."*

### United States (us)

**Tier 1 — bounded single-site action**
- `restaurant-tonight-nyc` — *"Book a table for 2 tonight at 7pm at Katz's Delicatessen."*
- `cancel-subscription-before-charge` — *"Cancel my Hulu trial before it charges me on the 15th."*
- `reorder-prescription` — *"Reorder my blood-pressure prescription from CVS."*
- `pay-known-bill` — *"Pay this month's electric bill before it's due on the 5th."*
- `renew-gym-membership` — *"Renew this month's gym membership at Equinox."*
- `book-barber-slot` — *"Book my usual barber for Saturday morning."*
- `book-hotel-night-known` — *"Book one night at the Ace Hotel downtown for September 20th."*
- `buy-known-product` — *"Buy the book on my Amazon wishlist."*
- `find-theatre-tickets` — *"Get me two tickets to The Lion King musical in New York for Saturday."*

**Tier 2 — search + compare + choose**
- `best-pediatric-dentists` — *"Find the 3 best-rated pediatric dentists near me and book the top one."*
- `compare-flights-sf-austin` — *"Compare flights SF-Austin for next long weekend and book the cheapest with a carry-on included."*
- `best-plumber-same-day` — *"Find a plumber who can come today, top-rated near me."*
- `compare-insurance-quotes` — *"Compare three car insurance quotes and tell me which one's the best deal."*
- `cheapest-monitor` — *"Find the cheapest 27-inch 4K monitor with good reviews."*
- `best-rated-rental-car` — *"Find the best-rated rental car in Austin for the weekend."*
- `compare-phone-plans` — *"Compare cell phone plans and tell me which one saves me the most."*
- `weekend-barber-availability` — *"Find a barber with an opening this weekend near me."*
- `search-buy-used-car` — *"Find me a used car, diesel or hybrid, under 60k miles and under $14,000, and give me the top 3."*
- `search-buy-motorcycle` — *"Find me a used 300cc motorcycle in good condition for under $3,000."*
- `search-buy-bicycle` — *"Find me a used mountain bike in good condition, size M, for under $350."*
- `search-secondhand-monitor` — *"Find me a used 27-inch+ monitor for under $150."*
- `search-buy-book` — *"Find the latest book by Colleen Hoover and buy it from whichever store has it cheapest."*
- `search-buy-camera` — *"Find me a used DSLR camera with a low shutter count for under $400."*
- `search-buy-guitar` — *"Find me a used acoustic guitar for beginners under $150."*
- `find-best-hotel-city` — *"Find me the best hotel in New Orleans for the weekend of the 20th, well-rated and under $150 a night."*
- `find-direct-flight-budget` — *"Find me a direct flight NYC-Rome in October, as cheap as possible."*
- `rental-car-automatic-airport` — *"Find me an automatic rental car at Denver airport for next week."*
- `find-concert-tickets` — *"Find me tickets to a Beyoncé concert in LA this month, as cheap as possible."*
- `things-to-do-nearby-weekend` — *"Find things to do this weekend near me."*
- `kid-friendly-activity-nearby` — *"Find a kid-friendly activity near me for Sunday."*

**Tier 3 — multi-step, single domain, real deadline**
- `smog-check-before-deadline` — *"My car's smog check is due before the 30th - find an appointment and remind me the day before."*
- `renew-passport-before-expiry` — *"My passport expires in two months - book a renewal appointment and remind me."*
- `track-package-reschedule` — *"Track the package I'm expecting and reschedule delivery if I won't be home."*
- `negotiate-lower-phone-bill` — *"Call my carrier and get my phone bill lowered."*
- `file-expense-report` — *"Put together last week's trip expense report and send it to accounting."*
- `split-dinner-bill-friends` — *"Split last night's dinner bill four ways and send everyone their share."*

**Tier 4 — cross-domain orchestration**
- `weekend-trip-austin` — *"Plan a weekend in Austin: flight, hotel with breakfast, dinner reservation Saturday."*
- `clean-and-reply-inbox` — *"Clean up my inbox from the last two weeks and reply to what's actually urgent."*
- `archive-newsletters` — *"Archive my backlog of newsletters and leave only what matters."*
- `rebook-delayed-flight-now` — *"My flight just got delayed over an hour - find another one and let me know."*
- `found-next-apartment` — *"Find me a 1-bedroom in Brooklyn under $2800 and schedule the tours that fit my calendar."*
- `moms-birthday-flowers-onetime` — *"It's my mom's birthday the day after tomorrow - order flowers for morning delivery."*

**Tier 5 — standing/reactive over time**
- `watch-flight-rebook-automatically` — *"Watch my flight to Chicago; if it's delayed more than an hour, rebook me automatically and let me know."*
- `track-price-drop-buy` — *"Track this monitor's price and buy it the moment it drops below $250."*
- `cancel-trial-before-it-charges` — *"I've got a free trial that converts to paid Friday - cancel it yourself if I haven't used it again."*
- `gym-membership-no-silent-renew` — *"Don't let my gym membership auto-renew without checking with me first."*
- `moms-birthday-flowers-recurring` — *"Never let me forget my mom's birthday - order flowers the day before, every year."*
- `grocery-restock-reactive` — *"When you notice we're low on milk or coffee, reorder it without me having to ask."*

**Tier 6 — multi-agent over email**
- `coordinate-dinner-with-alex` — *"Ask Alex's agent to lock in Friday dinner - let them pick the place, just confirm the time with me."*
- `split-airbnb-with-jordan` — *"Coordinate with Jordan's agent on a shared Airbnb for the weekend in Miami and split the bill."*
- `resolve-meetup-conflict` — *"Sam's agent is going to propose meeting Saturday - check my calendar and negotiate a time that works."*
- `confirm-restaurant-together` — *"Sync up with Taylor's agent on tonight's reservation - make sure neither of us double-books."*
- `plan-joint-trip-with-friend` — *"Talk to Morgan's agent and align on a shared itinerary for the September trip."*

**Tier 7 — multi-agent over WhatsApp/Telegram (BLOCKED)**
- `coordinate-dinner-whatsapp` — *"Text Alex's agent on WhatsApp and lock in Thursday dinner."*
- `split-trip-telegram` — *"Message Jordan's agent on Telegram and split up the trip itinerary."*
- `group-plan-three-friends` — *"Coordinate with Alex, Jordan and Sam's agents over WhatsApp to get everyone together Saturday."*
- `realtime-eta-share` — *"Ping Taylor's agent on WhatsApp the moment I leave, so they know when I'll arrive."*

## Measuring while another agent is editing (2026-08-21)

Rounds boot a sandbox engine from the repo, so a round measured while somebody else is mid-edit is a
round that cannot be compared with any other. `run.py` refuses to start on a dirty tree for that reason,
and `--allow-dirty` marks the row `provisional` so the board never counts it. Both are correct and both
mean measurement STOPS whenever a fixing agent is working — which, with three agents on one repo, is most
of the time. Twice in one night a round was thrown away for it.

The fix is not to relax the guard. It is to measure somewhere nobody else writes:

```sh
git worktree add <path> HEAD          # a checkout pinned to one commit
cd <path>
ln -sfn <repo>/.venv .venv            # symlinks: the venv and the credential store are not in git
ln -sfn <repo>/.env .env
ln -sfn <repo>/.meshkore/credentials .meshkore/credentials
<repo>/.venv/bin/python -m tests.use_cases.e2e.agent.run --scenario <id> --sandbox
```

`ENGINE` is derived from `__file__`, so importing from the worktree points the sandbox at the worktree —
no flag, no code change. The tree there only moves when this agent moves it, so the round is attributable
to exactly one commit, and the fixing agent never has to hold still.

Two details that cost a first attempt:

- The three symlinks show as UNTRACKED and trip the same dirty-tree guard, because `.gitignore` matches
  `.venv/` as a directory and a symlink is a file. They go in the shared `.git/info/exclude` (worktrees
  read the common git dir, not their own `info/`). Never in `.gitignore` — that is a tracked file.
- Do NOT symlink `tests/use_cases/status.json` or `STATUS.md` into the repo's copies: replacing a tracked
  file with a symlink is a `typechange`, which is dirty, and the guard is right to refuse it. Let the
  worktree keep its own and fold the row back into the repo's ledger after the round.

Pin the worktree at the commit you mean to measure (`git -C <path> checkout <sha>`), and say which one in
the report — a round is a statement about one commit or it is a statement about nothing.

**And the third detail, which is not a detail: this method CANNOT measure a case that escalates to a
worker.** A worker reaches the browser, memory and the network through `python -m nucleo.<bridge>`, and
those commands are permitted only because `claude_session._BRIDGE_TOOLS` lists the exact interpreter — a
list built from `_ZAELAR` (`__file__`, so the WORKTREE) while the prompt hands the worker
`bridge_python()` (`sys.executable`, so the REAL venv, because Python resolves the symlinked `.venv`
above). The interpreter the prompt DICTATES is therefore not in the list that permits it, and every
bridge call comes back «This command requires approval» in a headless run where nobody approves.

It does not fail loudly. The worker says, correctly, that its environment has blocked every tool; the
round scores 1/5 on `resultado`; and the judge writes it as the agent claiming results it never had.
Measured 2026-08-21: **every worktree round that spawned a worker at all shows 18-27 denials** (six
rounds); the ones that died at preflight, with zero workers, are clean. `run.py::bridge_allowlist_refusal`
now asks this BEFORE driving anything and exits 4, so the failure costs a second instead of fifteen
minutes — but the refusal is the honest outcome, not a fix. **Until the interpreter matches, measure a
worker case on the real tree** (with `--allow-dirty` if a fixing agent is mid-edit, and let the row carry
`provisional`), and keep the worktree for cases the FlashBrain answers by itself.

## What this harness got wrong about the product, and how each was caught (2026-08-21)

Six times in one night this harness reported a defect that was its own, in the exact shape of a finding —
and the judge writes those in the language of conduct («it hid», «it lied», «it was vague»), so a false
FAIL does not read as a false FAIL. It reads as a damning one. Two reached the fixing agent before being
caught. The pattern is always one of two roots: **reading a state while the system is still writing it**,
or **reading a field at the wrong level**.

A seventh, on 2026-08-21, has a third root worth naming on its own: **the instrument had the diagnosis and
printed a suggestion to go look for it.** Every one of the 46 refusals was holding
`error: 402 Insufficient Balance` and the `spec` of the rung that had refused, and the refusal it printed
said «mira el log del sandbox». Eight hours of measuring window were spent on a retry loop waiting for a
balance to come back — a balance that never had to come back, because the failover behind it was alive and
the only thing missing was one channel's relay. Nobody was misled by a wrong fact; they were misled by a
fact withheld. **If the answer is in the response you are holding, print it.**

| what it reported | what was true | the fix |
|---|---|---|
| «hid three real 99 EUR monitors» | the note carried `items[:3]` in DOM order; rows 4-6 were never in it | judge delivery on what the BRAIN was handed |
| «5 of 8 workers died» | 3 died; 2 were cancelled by the harness's own shutdown | read `worker.done`'s status, not `ok` alone |
| «4 spawned, 0 ok» | 1 errored, 3 were still working; their rows landed 434 s later | wait for the store to go quiet AND for every worker to close |
| a death at ~1450 ms | a provider handoff working | `relayed` is its own bucket, in BOTH columns |
| «0 notes from search» with 12 answers | the notes were queued 6 s after the read | same quiescence wait |
| the same hotel in six unrelated cases | read `worker_outcome` per REPORT instead of per scenario | iterate `results[]` |
| «claimed results while its environment blocked every tool» | the blockade was the harness's: the worktree's interpreter was not in the bridge allowlist, so all 19 calls were denied | ask before driving (`bridge_allowlist_refusal`) |
| «the whole provider chain is out; nothing can be measured» | AIMLAPI was alive all night, both models answering in ~3 s. The TEXT channel does not relay: it catches the provider error and returns it, while the voice channel in the same log relayed past the same rung | the preflight PRINTS what the engine said; the harness seeds a rung that answers at the head |

Four rules came out of it, and they are code now, not intentions:

1. **Read after the round, and ask about the WORK, not the clock.** Silence alone is ambiguous: a store
   quiet because nothing has started looks exactly like one quiet because everything finished.
2. **Spend one throwaway turn before driving.** If the brain cannot speak, nothing is measured — that is
   INFRA, never FAIL. A whole night's provider outage filed a case 1/1/1/1/1 before this existed.
3. **Two columns about the same fact must agree.** One saying «0 errored» while another lists «dead: [1]»
   is worse than either being wrong: the reader has to pick which to believe.
4. **A number that fits another one too well is the signal to go back to the raw event.** That is what
   caught the hotel attributed to six cases: it fit far too well.

And the rule that governs reporting any of it: **the scope is measured the same way the bug is.** The
natural way to report a finding is the worst imaginable case rather than the measured one, and it sounds
like rigour while being the opposite. Before saying who it affects, grep for who exercises it TODAY and
count. If nothing live does, say so in those words — otherwise a preventive fix goes into the record as a
fire that was put out, and a month later nobody can tell what actually broke.
