<!-- Auto-rendered from .meshkore/public/AGENT_INSTRUCTIONS.md per
     MeshKore standard §17 (v18+). Edit the source, not this file.
     Audience: Codex / Aider / general convention. -->

<!-- MESHKORE_PREAMBLE_BEGIN — managed by the daemon, do not hand-edit -->

# MeshKore — agent instructions (canonical preamble)

> **Canonical URL** — the verbatim content of this file is what the
> MeshKore daemon writes into the `MESHKORE_PREAMBLE` block of every
> cluster's `.meshkore/public/AGENT_INSTRUCTIONS.md` (standard §17,
> v18+). The rendered per-CLI files (`CLAUDE.md`, `AGENTS.md`,
> `GEMINI.md`, …) inherit it transitively. Audience: any AI assistant
> CLI walking into a MeshKore project for the first time.

You're an AI assistant working inside a project that follows the
MeshKore standard. Before doing anything substantial in this repo,
take 30 seconds to read this preamble and skim
`.meshkore/public/RESOURCES.md`. Both files are tiny on purpose; both
exist so you don't have to re-discover the mesh from scratch every
conversation.

## The standard

This project commits to the MeshKore standard. The canonical spec
lives at:

- Human-readable: <https://meshkore.com/standard>
- Machine-readable: <https://meshkore.com/standard.json>

The version this project pinned is in `.meshkore/STANDARD_VERSION`.
The version currently published is at
<https://meshkore.com/standard/version>. If the local is behind,
follow `.meshkore/docs/conventions/standard-evolution.md` to catch up.

## What the mesh gives you

Quick reference: read `.meshkore/public/RESOURCES.md`. It catalogues
every entry point — the Oracle (natural-language agent discovery),
the hub directory (browse 90 K+ indexed agents), the canonical agent
URL pattern, the deploy playbook, the daemon upgrade flow.

The three operations you'll do most often:

1. **"Use the agent at <URL>"** — the operator pastes
   `https://meshkore.com/agent/<id>`. You fetch
   `<URL>/.well-known/agent.json`, read the A2A Public Card (skills
   with examples, the agent's live `url`, pricing, default I/O
   modes), then HTTP straight to the agent. The MeshKore site does
   NOT proxy skill calls — per manifesto, MeshKore is a router, not
   a broker.

   **How to build the call:** `POST <card.url>/v1/<skill-id>`, JSON in,
   JSON out — standard §26. `<skill-id>` is the `id` from the card's
   `skills[]`, verbatim. Never guess a path and never special-case one
   agent: if it 404s, the agent is not serving what its card advertises,
   and that is the agent's bug. Check `operational` (§27) before you
   commit to a target — `online` is only a heartbeat.

2. **"Find me an agent that does X"** — POST to the Oracle:

   ```bash
   curl -X POST https://meshkore-oracle.rjj.workers.dev/v1/search \
     -H 'content-type: application/json' \
     -d '{"prompt":"X"}'
   ```

   Returns ranked, live agents. Pick any `agent_id` and use it with
   the canonical URL pattern above.

3. **"Publish this agent"** — read
   <https://meshkore.com/reference/agents/deploy-your-agent>. Three
   calls (register once, push a slim DiscoveryCard, heartbeat every
   ~5 min). The Oracle picks the agent up automatically.

Standard agent protocols you'll encounter: **HTTP/JSON** (universal,
mandatory baseline), **A2A** (the Card convention at
`/.well-known/agent.json`, mandatory in the card), **MCP** (optional,
for agents that double as Claude tools), streaming (SSE/WS, optional).

## Conventions you must follow

These are load-bearing rules of the MeshKore standard. Violations
break the daemon's automation or the project's git contract.

1. **Folder layout (§2).** Since v27 the git contract is a deny-list:
   commit `.meshkore/public/`, `docs/`, `modules/`, and
   `roadmap/initiatives/` (plus `STANDARD_VERSION`) — the project's
   identity, instructions, plan and task history travel with the repo.
   Do NOT commit runtime/secret/per-machine state — `.meshkore/.runtime/`,
   `credentials/`, `agents/`, `timeline/`, `log/`, `queues/`, `uploads/`,
   `snapshots/`, `state.json`, `roadmap/state.{json,js}`, `scripts/` —
   they're deliberately gitignored (see §2.2).

2. **Tasks (§4).** New tasks go under
   `.meshkore/modules/<module>/tasks/` as markdown files with
   frontmatter matching the `task_frontmatter` schema. The
   `category` field MUST equal `<module>` (the parent folder).

3. **Logs (§6).** Append every meaningful event to
   `.meshkore/log/<YYYY-MM-DD>.md`. One file per day, append-only;
   never rewrite past entries. Format is plain markdown — start each
   entry with a `## <HH:MM> · <one-line summary>` heading. **One entry
   per unit of work, not per agent** (v33): if you delegated parts of
   it, you write a single entry covering the whole thing from your
   children's reports; if you WERE delegated, you write none.

4. **Commit attribution (§9.1, revised v21).** Every commit you
   author MUST end with three trailers, in this order, after a blank
   line:

   ```
   Agent: <agent-role>            # master, roadmap-architect, work-<I>-<T>, ...
   Model: <model-id>              # claude-opus-4-7, claude-sonnet-4-6, ...
   MeshKore: py-<X.Y.Z>           # the cluster's daemon version at commit time
   ```

   `MeshKore:` is the literal `DAEMON_VERSION` from the running
   daemon — every subagent briefing embeds it, so you can quote it
   verbatim without lookup. When your conv is bound to a team member,
   `Agent:` is that **member id** (`developer`, `deployer`, …). Work
   that another agent delegated to you adds a fourth trailer,
   `Parent: <parent member id>@<parent conv>` (v33) — it is how a
   reader reconstructs which agent tree produced a change.

   **Do NOT add `Co-Authored-By:`** (removed in v21). The operator's
   cross-repo convention is no-co-authoring; MeshKore is the
   exception because the three semantic trailers above already
   attribute the AI (role, model, runtime) far more usefully than a
   display-name boilerplate would.

   Full spec at
   <https://meshkore.com/standard#91-commit-attribution--agent--model--meshkore-trailers-v12-revised-v21>.
   The closure protocol embeds the same rule with extra context:
   `.meshkore/docs/conventions/closure-protocol.md`.

5. **Standard evolution (§11).** Bumping any of
   `webapp/standard.json` / `standard.md` / `standard/CHANGELOG.md`
   / `standard/version` requires bumping all four in the same
   commit. Drift between these four files is the most common bug in
   this area. Follow
   `.meshkore/docs/conventions/standard-evolution.md` for the
   pre-flight checklist and the five-step bump.

6. **Cluster config.** Lives in `.meshkore/public/cluster.yaml`. The
   schema is canonical at standard §3.

7. **File snapshots (§20, v19+).** Before any tool call that **Writes
   or Edits an EXISTING file**, POST the affected paths to the daemon
   so it can copy them under `.meshkore/snapshots/`:

   ```bash
   curl -X POST -H "Authorization: Bearer $TOKEN" \
        -H 'content-type: application/json' \
        -d '{"paths":["apps/web/src/X.tsx","apps/api/src/y.ts"],
             "agent_id":"<your agent_id>",
             "agent_type":"<your agent_type>",
             "conv":"<conv-slug>",
             "note":"<one-line what you are about to do>"}' \
        https://daemon.meshkore.com:<port>/snapshots
   ```

   The daemon writes a manifest + verbatim copies + appends a line to
   `.meshkore/log/<YYYY-MM-DD>.md`. Newly-created files are exempt
   (no prior content to preserve). Retention is bounded by
   `cluster.yaml#snapshots.retention_days` (default 7). This is
   non-negotiable: without it, the operator cannot inspect or restore
   the pre-edit state between commits.

8. **Initiative-anchored execution (§24, v23).** Every turn anchors to
   an `(initiative, task)` pair — that anchor is what puts your work on
   the cockpit roadmap and lets the daily log cross-reference it. If
   your dispatch arrived WITHOUT one, your FIRST action is to locate
   the matching initiative + task, or create them when none fits
   (initiative at `.meshkore/roadmap/initiatives/<slug>.md`, task at
   `.meshkore/modules/<module>/tasks/<id>-<slug>.md`), then continue.
   Unanchored code work leaves no roadmap trace and breaks the
   operator's live picture of the project. Full decision chain:
   `.meshkore/docs/conventions/initiative-anchored-execution.md`.

9. **The team (§25, §28, revised v38).** The project has a roster of agent
   profiles at `.meshkore/team/*.md`. A project is seeded with a small base
   team: `a01` (the Architect Agent, which coordinates), `developer`,
   `git-manager`, `deployer` and the public `consultant`. Each card is a
   short prompt plus the slice of the project's knowledge that member
   needs — a deployer does not load the data model.

   **`delegate`** — the default way to use a teammate:
   `POST <daemon>/chat/delegate {parent_conv, member, brief}`, then END
   your turn; the daemon wakes you when that member reports, naming your
   `request_id`. The member runs in its own session with its own profile
   and slice, so your thread stays about the plan. Chain the next step
   from the report (build → commit → deploy) and give independent steps
   to different members at once. **A member is ONE session** (§28.6): your
   brief joins whatever that member is already holding.

   **`become`** — `⟦become⟧ <member id>` on its own line adopts a profile
   for your next turn in this same conversation. Only for one short step;
   never to chain a pipeline through one thread.

   **Or neither.** Most work is just work: a small fix and its test are
   one agent's job. Never delegate to spread a task thin or to avoid
   reading code. When the team has a `git-manager`, commits are its job:
   leave your change in the working tree and list the files in your
   report.

   **Talk to the operator in sentences.** Report objects and markers are
   agent-to-agent; never paste them into prose the operator reads.

   **If YOU are the member holding briefs**, you will see the whole batch:
   read it together, merge what collapses into one piece of work, and name
   every request id you answered in the report's `"for"` field. **If YOU
   were delegated**, three duties follow: anchor to the `(initiative,
   task)` your brief names (never mint a new one for a delegated step),
   end your final reply with the `⟦report⟧` line (once, as the last line —
   never echo the object elsewhere), and add
   `Parent: <parent member id>@<parent conv>` to any commit trailers.
   Do not write a diary entry for a delegated step — the root of the unit
   of work writes one entry for the whole thing. Full contract: §28.

   Working from a plain CLI (VS Code, Cursor…) with no daemon conv? Then
   you are the root: do the work yourself, anchor it, and write the diary
   entry. The roster is still worth reading — it tells you which parts of
   this project have an owner with standing instructions.

## Where to dig deeper

- `.meshkore/context/` (§3.5) — the project's standing, invariant
  knowledge loaded into every spawn: `overview.md`, `product.md`,
  `stack.md`, `architecture.md`, `constraints.md`, plus `decisions/`,
  `glossary.md`, and `criteria/` (the base acceptance criteria your
  work is judged against). Read this before designing anything.
- `.meshkore/workflows/` (§14) — the cluster's reusable runbooks
  (`INDEX.md` + the W-numbered procedures: bump-standard, deploy,
  publish-repo, daemon-upgrade, daemon-release, verify). Follow the
  matching W-runbook for multi-step operations instead of improvising:
  releases and deploys have ordering rules that are not guessable from
  the code. (Renamed from `protocols/` on 2026-06-21 — "protocol" is
  reserved for wire protocols like A2A and MCP. A cluster that still has
  a `protocols/` folder predates the rename.)
- `.meshkore/docs/` — cross-cutting docs (architecture, product,
  conventions, security, ops); start at its `INDEX.md` if present.
- `.meshkore/docs/conventions/` — operational playbooks (close-out
  flow, deploy-by-agent, component-repo split, etc.)
- `https://meshkore.com/reference/` — public reference catalog
  (stack templates, prompt templates, conventions catalogue).
- `https://meshkore.com/reference/agents/` — agent-specific docs
  (`addressing` for the URL contract, `deploy-your-agent` for the
  operator playbook, `local-instructions` for the spec behind
  THIS file).
- `https://meshkore.com/roadmap` — what's shipping next.

## Notes for the AI you are

- **The daemon is ONE shared process per machine, NOT per-project.** It serves
  every project from a single base URL, routed by the `X-MeshKore-Project:
  <cluster-id>` header. This project has **no** `.meshkore/scripts/daemon.py`,
  binds no port, and runs nothing — never create, download, or run a daemon, and
  never bind `5570–5589`. A bare `/health` reporting a *different* `cluster_id`
  is expected (it's the daemon's default project), not a fault. To adopt a repo,
  add it in the Architect — the shared daemon onboards it (standard §10).
- **Anything not on this page → start at `/standard` or `/reference`.**
  These two trees cover every formal piece of MeshKore.
- **Live state never lives in this file.** For online flags, message
  counts, etc., query the API: `GET https://api.meshkore.com/v1/agents/<id>`.
- **Don't proxy skill calls through `meshkore.com`.** Always HTTP
  the agent's live `url` from its `.well-known/agent.json`.
- **The OPERATOR_CONTENT block below this preamble is the operator's
  project-specific rules.** They apply on top of this preamble; if
  there's a conflict, the OPERATOR_CONTENT wins (it knows the
  project better than MeshKore does).

---

*Standard §17 — mandated as of v18, 2026-06-09. Updated alongside
every standard bump that touches agent-side conventions.*

<!-- MESHKORE_PREAMBLE_END -->

<!-- OPERATOR_CONTENT_BEGIN — this is your project. Edit freely. -->
# zaelar

A **multilingual, always-on personal voice agent**: it starts in English and switches to the operator's language
as soon as it hears it. STT → **its own brain, «Colmena»** → TTS, on LiveKit Agents. The brain (`nucleo/`), the
memory (`memory/`) and the proactivity are **part of this repo**. For the outside world — bookings, travel,
events and thousands of other services — it orchestrates **external services**: the agents on the MeshKore
network, external MCP servers and third-party APIs.

**Run it:** `make run` (= `BRAIN=nucleo`) → native LiveKit stack (no Docker) + web app with the embedded worker,
at http://localhost:43917 (plain HTTP: a local install carries no certificate). `make restart` picks up `.py`
changes; `make status` tells you whether it is up. Full install for a fresh clone: `README.md`.

## How we work here

- **Fix the CLASS, never the case.** No fix that only makes one test pass: green is the consequence of a healthy
  system. Name the class; fix it with verdict → declared data → one door; the test carries another variant
  (language, wording, domain). Product regexes and word tables only ever shrink. Full text:
  `.meshkore/context/principles.md`.
- **Don't restart the engine while someone is using it or a task is running.** Before `make restart`, look at the
  latest events in `.meshkore/logs/sessions/` (recent `transcript`/`brain` = someone is talking) and at
  `curl -s localhost:43917/api/tasks` (non-empty `sessions` = work in flight). A restart ends the LiveKit session
  and cancels running workers.
- **While iterating, run tests that take seconds** — the file you touched and its disarm. A wide pass is a
  deliberate step: run it with `tests/watchdog.py`, never bare `pytest`.
- **Commit with a pathspec** (`git commit -- <paths>`) after checking that `git diff --cached --name-only` is
  EMPTY. Several sessions may share one checkout, and the index is shared. See «Hard rules».
- **Commits carry a `Co-Authored-By:` trailer** naming the agent/CLI that wrote the change, after the MeshKore
  trailers.
- **Never overwrite or commit someone else's uncommitted work.**
- **Visual changes are agreed first.** No unrequested redesign passes.
- **What the engine obeys TODAY is `.meshkore/docs/criteria.md`** — one criterion per line, each with its test
  node. Read it BEFORE changing engine behaviour. The reasoning behind each decision lives in a local log,
  `.meshkore/docs/decisions.md` (gitignored; absent on a clone).
- **Say what was not verified.** «Not verified live» is an acceptable answer; claiming something works without
  measuring it is not. If a test turns green when the product is broken, the suspect is the TEST.

## Where things are

| Looking for | Where |
|---|---|
| The **rules** for working in this repo | this file |
| The **standing criteria** of the engine, one line each, with its test | `.meshkore/docs/criteria.md` |
| The **invariant context** (vision, product, stack, architecture, constraints, glossary) | `.meshkore/context/` |
| How to **test** | `tests/README.md` and «Testing» below |

Planning and diary folders (`.meshkore/roadmap/`, `.meshkore/modules/*/tasks|logs/`, `.meshkore/team/`,
`.meshkore/log/`, the decision log) are **local-only and gitignored on purpose**: the repo carries
what helps you understand and run the engine today. A pointer into one of them from a clean clone lands on an
empty folder by design.

## Working language: English, everywhere inside `engine/`

`engine/` is a PUBLIC repository, so **everything a developer reads is English**: comments and docstrings,
**test function names** and docstrings, log/warning/exception messages, technical documentation under
`.meshkore/`, this file, and **commit messages**.

Part of the codebase still carries Spanish comments from its early days; that is a translation backlog, not the
house style. Write **your** lines in English and leave your neighbours to the pass that owns that corpus.

Spanish that is **product data** stays Spanish: user-facing labels, voice replies, `i18n/bundles/*.json`, prompt
text the agent speaks, and Spanish vocabulary inside detectors and regexes. Those follow the i18n rules
(`voice/engine/core/langs.py`).

## Public / private boundary

This repo is public (fair-code, Sustainable Use License 1.0 — never call it «open source» or «MIT»). It documents
the **mechanism**, for anyone who self-hosts or contributes:

- Nothing about how a hosted deployment is operated, billed or priced lives here.
- Code may have seams one deployment uses and another doesn't (a service URL in an env var, a user id from the
  environment). Describe the mechanism («if `X_URL` is set, notify that service; without it this is a no-op»),
  never a product.
- When in doubt: *does this help someone who self-hosts?* If not, it doesn't go here.
- The **catalogue** of what is tested is public and useful; the **record** of what was run (session transcripts,
  run reports) stays local.

## First principle: mechanisms, not rules

> «We need a system that isn't trained case by case — one that is intelligent and knows what to do. We are
> building a SYSTEM, not a set of predefined rails. **The only thing with rails is the widgets.**»

The question that decides whether a change belongs in this engine: **does it bound a CONSEQUENCE or bound a
JUDGEMENT?** Bounding a consequence is a mechanism and stays (`party.py` offers NO tools and the engine only
executes what the mandate allows; `contract.guard` rejects a destructive action without a selector;
`book.unbook` can only undo the row that errand wrote). Bounding a judgement is a rail and goes («don't argue»,
«acknowledge in one sentence», a verb table that decides intent).

And a third question: **is what I am writing a sentence about how to behave?** If so, delete it and find the
mechanism it was standing in for. Full text: **`.meshkore/context/principles.md`**.

## How ANY agent fix is aimed

There is no list of supported errands and there can't be one. Two halves, treated in opposite ways: **RESOURCES
pinned, complete and tested** (browser, real-time data, parsing, screenshots, bridges, evidence, delivery — a
failure here is a bug) and **REASONING open** (Brain Worker prompts carry formulas, resources and ways to solve,
never a script). Adapting to the use case is what's off-limits: *change a word in the errand — hotel→restaurant,
Seville→Los Angeles — does it still hold?* Full doctrine:
`.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md`.

**Other ways to start:** `BRAIN=direct` / `BRAIN=local` are bare-model baselines (no memory, no tools);
`make lk-server` and `make agent-worker` start the two halves separately for debugging.

## Canonical documentation and the MeshKore standard

This repo follows the **MeshKore Standard**. All documentation lives in `.meshkore/` — don't create `docs/` or
ad-hoc folders outside it. Install and start-up for a fresh clone: **[`README.md`](README.md)**; the detail in
`.meshkore/docs/ops/zaelar-ops.md`. Keep both aligned.

### Canonical documents (`.meshkore/docs/`)

| Topic | File |
|---|---|
| Architecture | `.meshkore/docs/architecture/zaelar-architecture.md` |
| **Modularity / coupling contracts** | `.meshkore/docs/architecture/zaelar-modularity.md` |
| **Central memory** | `.meshkore/docs/architecture/zaelar-memory.md` |
| **Why THESE models** | `.meshkore/docs/ops/zaelar-model-benchmarks.md` |
| **Cluster channel — end-to-end algorithm** | `.meshkore/docs/architecture/zaelar-cluster-channel.md` |
| **MeshKore network — external agents (Oracle) + clusters** | `.meshkore/docs/architecture/zaelar-meshkore-network.md` |
| **⭐ Brain Worker doctrine — harden the RESOURCES, open the REASONING** | `.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md` |
| **Multilingual / i18n** | `.meshkore/docs/architecture/zaelar-i18n.md` |
| **⭐ Prompt that belongs to a PHASE (context packs) — read BEFORE adding a sentence to the turn prompt** | `.meshkore/docs/architecture/zaelar-context-packs.md` |
| **First run, end to end (language → folder → voice → greeting)** | `.meshkore/docs/modules/zaelar-first-run.md` |
| Product / context | `.meshkore/docs/product/zaelar-product.md` |
| Conventions | `.meshkore/docs/conventions/zaelar-conventions.md` |
| Modules | `.meshkore/docs/modules/zaelar-modules.md` |
| **Reference docs by mechanism** (action map, jobs, task lists, decision model, daemon, connectors…) | `.meshkore/docs/modules/zaelar-module-map.md` |
| **Connectors — the list and where each piece is wired** | `.meshkore/docs/modules/zaelar-connectors-inventory.md` |
| **An appointment someone else asks for — the authorisation rule** | `.meshkore/docs/modules/zaelar-appointment-proposals.md` |
| **Contacts — import/sync with Google, and who wins a conflict** | `.meshkore/docs/modules/zaelar-contacts-sync.md` |
| Security | `.meshkore/docs/security/zaelar-security.md` |
| **Change protocol** | `.meshkore/docs/ops/zaelar-change-protocol.md` |
| **Audit workflow** | `.meshkore/docs/ops/zaelar-audit-workflow.md` |
| **Docs & structure sync** | `.meshkore/docs/ops/zaelar-docs-sync.md` |
| **⭐ Widget header STANDARD — the two bars and the door to connectors** | `.meshkore/docs/conventions/zaelar-widget-header-standard.md` |
| **Widgets change workflow** | `.meshkore/docs/ops/zaelar-widgets-workflow.md` |
| **⭐ NEW widget or connector — the complete workflow** | `.meshkore/docs/ops/zaelar-new-widget-or-connector-workflow.md` |
| **⭐ NEW native surface (panel, wall tab, overlay)** | `.meshkore/docs/ops/zaelar-native-surface-workflow.md` |
| **Memory change workflow** | `.meshkore/docs/ops/zaelar-memory-workflow.md` |
| **Alignment review** | `.meshkore/docs/ops/zaelar-alignment-review.md` |
| **Changing a model (checklist + traps)** | `.meshkore/docs/ops/zaelar-model-change.md` |
| **Testing playbook** | `.meshkore/docs/ops/zaelar-testing.md` |
| **Cluster conversation monitoring** | `.meshkore/docs/ops/zaelar-cluster-conversation-monitoring.md` |
| Observability / debugging | `.meshkore/docs/ops/zaelar-observability.md` |

### Workflows — the request and the doc that runs it

Steps are not recalled from memory: they live in their doc. Each row is a complete procedure.

| When asked to… | Run |
|---|---|
| «run the protocol» | `.meshkore/docs/ops/zaelar-change-protocol.md` — restart+verify → version → docs → commit → push |
| «audit the system» | `.meshkore/docs/ops/zaelar-audit-workflow.md` — recon → fan-out over 4 domains → synthesis → report + P0-P3 plan |
| (any change of STRUCTURE or invariants) | `.meshkore/docs/ops/zaelar-docs-sync.md` — README, this file, `cluster.yaml`, the category doc, the public diagrams |
| «run the alignment review» | `.meshkore/docs/ops/zaelar-alignment-review.md` — code ↔ context ↔ docs ↔ diagrams ↔ tests tell the SAME story |
| change the widget SYSTEM | `.meshkore/docs/ops/zaelar-widgets-workflow.md` — «what you touched → what to update» |
| «add a connector for X» / «make a widget for Y» | `.meshkore/docs/ops/zaelar-new-widget-or-connector-workflow.md` — the four prior decisions, the wiring points, declaring it DONE |
| a STRUCTURAL memory change | `.meshkore/docs/ops/zaelar-memory-workflow.md` — writers and readers, migration, docs, tests |
| «run the bot test» / «run the battery» | `.meshkore/docs/ops/zaelar-testing.md` — align scenarios → launch → JUDGE (real bug vs STT noise vs rigidity) → report |

**Closing a change:** (1) the test with its NODE in `tests/run_testmap.py` — not in the map = doesn't exist for
«is everything green?»; (2) one line in `criteria.md` IF a rule changed, and the reasoning in the local
`.meshkore/docs/decisions.md`.

**Testing contract for agents:** before testing, read `tests/README.md`. The entry point is
`./.venv/bin/python -m tests run <suite> [--case ID] --no-open` (exit code + Test Observatory at
`http://127.0.0.1:8765`; the real app stays on `43917`). No two managed runs in parallel; never against real
memory when there is a fixture; every new test under `tests/<suite>/`; anything crossing memory + conversation +
widgets/workers is also closed with `-m tests run journey --no-open`.

> The public architecture diagrams live on zaelar.com/technology (a curated picture, NOT a mirror of the code).
> If you change topology, a model or a provider, they need updating too; the detailed source stays in
> `.meshkore/docs/architecture/`.

### Modules — the short map

Before creating a new module, declare it in `.meshkore/public/cluster.yaml`. No loose `.py`/`.html` at the root;
start-up is `make run` → `python -m server`.

| Module | What it is |
|---|---|
| `voice/` | The **LiveKit** engine (`voice/engine/`): STT/TTS, turns, VAD, barge-in. On top, the transport-agnostic brain contract: `attention.py` (which turn is addressed to zaelar), `speech.py`, `observer.py` (SSE). |
| `nucleo/` | The **«Colmena» brain**: `flash/` (sub-second reflex, routes and answers), `workers/` (Brain Workers for what doesn't fit in a turn), `errands/` (an errand that outlives the turn), `loop.py`+`scheduler.py` (pulse, crons, proactivity), `memory_agent/` (the memory's single writer; `processor/` distils a turn into pills, `writer.py` holds the pill grammar). A request's life: `spec.py` (born with its end state) → `circuit.py` (one loop, one bound, one report) → `tasks.py` (the durable row); `consent.py` (the one act-or-ask rule), `turn/` (decisions both channels share), `batch/` (several tasks → a list), `actionmap/` (a known phrase skips the model), `jev.py`, `susurro/`, `context_packs/`. |
| `search/` | The **search service**: one door (`find()`), one result shape (candidate ≠ page that lists them), routing by verdict, providers declared once with a health probe (`python -m search.health`) and the HTTP face `/api/search/*`. Map: `.meshkore/docs/modules/zaelar-search.md`. |
| `rules/` | **One scoped table** for every standing rule and preference (`global` · `<domain>/<channel>/<act>` · `widget:<id>` · `item:<id>`), read by a cascade over the request's path; a spoken rule is shaped ONCE when written; `consent.decide` reads the gate. Design: `.meshkore/docs/architecture/zaelar-rules.md`. |
| `memory/` | **Central memory** in a single SQLite (`zaelar.db`): pills with `slot`, retriever (sqlite-vec + FTS5 + reranker), graph, consolidator and REM phase, episodic layer and the secrets vault. |
| `observability/` | **WHO · WHEN · in which FLOW**: install and session identity, reads by `corr_id`. Read-only — the only writer of `events` is the bus sink. |
| `bus/` | **Nervous system**: in-process pub/sub + durable event log + SSE bridge to the frontend. No Kafka. |
| `frontend/` | The interface, ES modules **with no build step**. `frontend/app/` (desktop) and `frontend/mobile/` (PWA). NATIVE surfaces are declared in `core/system-surfaces.js`; everything else on screen is a widget. |
| `server/` | FastAPI app + routers + entrypoint. Runs the LiveKit agent worker EMBEDDED and starts the loop, the widget supervisor and the memory queue in its lifespan. |
| `widgets/` | Full-stack widgets (`manifest.json` + `data.py` + `widget.js` per folder), generator, catalogue and runtime. Two kinds: `passive` and `backed` (own supervised process). |
| `config/` | Runtime settings managed by the UI (gitignored): `settings.json`, `connectors.json`, `v2.json` (model routing). Each with its owner module and a redacted public view. |
| `connectors/` | The outside world: WhatsApp, Telegram, email, Google (one OAuth client for Calendar/Meet/Drive/Photos/YouTube), cloud files, the native MeshKore channel, Architect. |
| `tests/` | See «Testing» below. The synthetic harness, the microphone self-test and the voice tester live under `tests/`. |

**The detail** — which pieces form each module and why: `.meshkore/docs/modules/zaelar-module-map.md`.

### The MeshKore daemon

The MeshKore daemon is a **single shared service** (`daemon.meshkore.com`): this repo neither starts nor ships
one — don't create `.meshkore/daemon.py`, `make meshkore` targets, or bind port 5570.

## What the agent may CLAIM, and what it asks permission for

A «yes» is answered with a START, never with a completion; a transactional op doesn't enter the task list; the
agenda goes DIRECT and a delete doesn't ask, with a bin and `restore`. All in `.meshkore/docs/criteria.md` §1-2.

## Who decides which card an order goes to

A verb table is not a router: grammar PROPOSES, the decision model chooses among what is DECLARED, and a backstop
never overrules a verdict already paid for (CRIT-K1). The verdict COMPLETES the model, never contradicts it
(CRIT-K2); a descriptor is written under the cut and measured against its NEIGHBOURS (CRIT-K7); a classifier in
front of the model is a PRICE paid only where the decision can't be read afterwards (CRIT-K9).
`.meshkore/docs/criteria.md` §3; read `.meshkore/docs/architecture/zaelar-architecture.md` §«ALERTS» BEFORE
writing a rule that reads the operator's WORDS. A disarm can leave stale bytecode: the harness clears
`__pycache__` when it restores (CRIT-W5).

## Our failure is not a provider outage

The exception decides whose fault it is (an HTTP status is theirs, a bare Python error is ours), the SAME request
hands over to the fallback in the connection loop, and embeddings have no fallback (CRIT-R1, CRIT-R3).
`.meshkore/docs/criteria.md` §6.

## The chat column is the conversation

A voice line is OWED when the mouth starts it, its identity is the turn's `trace`, and a held fragment only joins
the next one if the next one continues it (CRIT-V7); a complaint about what was just done is an order to redo it,
with the licence of the op it corrects; the assistant's name changes by verdict and fails CLOSED (CRIT-V8).
`.meshkore/docs/criteria.md` §1.

## Building or rewriting one of the user's cards is asked first

At the single door a worker is started through (`dispatch._run_session`, `kind == code`), with the whole confirm
gate; the cluster dev-worker is exempt (CRIT-C4). `widgets/_user/<id>/` SHADOWS the built-in and is gitignored:
before diagnosing a widget, check **which file runs**. A polite question is an order; a turn that is ONLY a
number moves nothing (CRIT-K7). `.meshkore/docs/criteria.md` §2-3.

## Testing

**Mandatory contract: before testing any change, read `tests/README.md`.** It's the short operational guide
shared by Claude Code, Codex, humans and CI. The deep playbook — how each battery is launched, formats,
evaluation — lives in `.meshkore/docs/ops/zaelar-testing.md`.

**`tests/run_testmap.py` is the TEST MAP**: all testing ordered by DOMAIN → USE CASE → CHANNEL (nodes `N.M`). It
is the source of truth for which file covers which case, and it marks LIVE nodes (they need `make run`). The
second opinion — coverage, gaps, duplication — is `tests/TESTMAP.md`. **A test that isn't in the map doesn't
exist for «is everything green?»**.

⛔ **`./.venv/bin/python tests/run_testmap.py` WITH NO ARGUMENTS RUNS THE WHOLE MAP** — a wide pass under another
name. To READ the map without running it: `tests/run_testmap.py --list`. To check your test is in it, run
`tests/infrastructure/unit/test_a_test_outside_the_map_is_not_a_test.py` on its own.

**A red that doesn't reproduce in isolation is contamination between tests, not your code.** The cause is always
the same family: something touches shared state and doesn't give it back. The root `conftest.py` moves EVERYTHING
the product really stores — logs, settings, model routing, widget data, the database, hidden widgets — to a temp
dir, and fails BY NAME the test that leaves the module table (`sys.modules`) purged. Before touching anything,
reproduce the red in its folder alone.

**Three ways to test**, fastest first: the **FlashBrain text channel** (headless, `make flash-serve` +
`make flash T="…"`) for the fast brain/conversation/prompt/tools; the **memory battery**
(`tests/memory/e2e/bot/`); and the **voice tester** (`tests/voice/e2e/agent/`), a second LiveKit participant
that TALKS to zaelar while a JUDGE evaluates what zaelar DOES, not what it says. All three, with triggers and
evaluation, in the playbook.

**Disarms.** A new test isn't worth anything until it has been seen RED: mutate the guard it claims to protect,
ASSERT the mutation landed, measure, and restore in a `finally` that clears `__pycache__`. **A disarm that stays
green indicts the TEST**, not the product.

**A test NEVER touches the operator's real state**: not the agenda, not the memory, not `config/`, not the logs.
That rule lives in the root `conftest.py`, not in each test.

## Deploy

Container image: `Dockerfile`. Hosting a deployment is out of scope for this repo.

## Hard rules

- **A WIDE PASS RUNS UNDER THE WATCHDOG, NEVER WITH BARE `pytest`** (CRIT-W5):

  ```sh
  ./.venv/bin/python tests/watchdog.py                           # everything deterministic
  ./.venv/bin/python tests/watchdog.py tests/voice/unit          # one folder
  ./.venv/bin/python tests/watchdog.py --impacted origin/main    # only what your diff reaches
  ```

  It names the test that hangs, kills the process GROUP and refuses two sweeps at once (node 7.53). While
  iterating: the FILE you touched and its DISARM. A red inside a wide pass is reproduced in its folder alone
  before touching anything (CRIT-W6).
- **COMMIT EARLY AND ALWAYS — every agent and every session commits ITS OWN work**, small and coherent, with a
  clear message of WHAT and WHY. Undoing a commit is cheap; losing code is not. Never close a session or switch
  tasks with uncommitted changes; never step on another agent's uncommitted work. After committing, push the
  current branch.
- **With concurrent sessions, protection is in what you COMMIT: `git commit -- <paths>`.** A bare `git commit`
  commits the WHOLE index, and the index is SHARED between sessions working in the same tree. With a pathspec,
  only those paths are committed from the working tree. Check that `git diff --cached --name-only` is EMPTY
  before starting. In `git status --short`, staged is `M ` (FIRST column) and modified-only is ` M`.
- Never `pull`/`merge`/`reset`/`checkout` to bring a remote version over the local tree (the local tree is the
  truth); never `git stash` in a shared checkout; never merge to `main` unless asked.
- Don't commit `.env`, `.venv/`, `logs/`, `config/settings.json`, `config/connectors.json`, `config/v2.json`
  (all in `.gitignore`), nor any personal profile file.
- **Nothing the end user configures goes in `.env`.** Every connector/integration activation or credential is
  handled from the UI (stores `config/connectors.json`/`config/v2.json`, written by the UI; env is only a
  power-user fallback). A new connector ALWAYS ships its guided setup flow in the widget.
- **Voice brain = NON-reasoning** (hard rule): a reasoning model doesn't close the turn in time. The FlashBrain
  (`nucleo/flash/`) uses only fast non-reasoning models. **Model PER INVOCATION**, never a global model env
  (concurrent sessions). Routing (`fast` + `code_agent`) lives in `config/v2.py` (managed by the UI).
- Don't create modules without declaring them in `.meshkore/public/cluster.yaml`.
- Don't edit `.meshkore/roadmap/state.json` by hand — it's a generated artefact.
- Don't create ad-hoc `docs/` folders — all documentation goes in `.meshkore/docs/<category>/`.
- **Zaelar's CORE must NOT require Docker.** The LiveKit server runs from the native `livekit-server` binary
  (`make install-livekit`); Docker is only an optional fallback. The **testing system MAY use Docker**.

<!-- OPERATOR_CONTENT_END -->
