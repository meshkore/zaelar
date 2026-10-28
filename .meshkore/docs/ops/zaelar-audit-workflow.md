---
title: Zaelar Audit Workflow
category: ops
updated: 2026-07-09
owner: ricart
status: current
---

# Zaelar audit workflow — "run the audit"

**Trigger:** when the operator says **"run the audit"** (or "audit the system", "check that everything is well
built"), the agent runs THIS workflow end to end. The goal is a **repeatable** procedure to re-verify, every
time the project evolves (new feature, refactor, new module), that **the code, the architecture, the canonical
documentation and the security module are still aligned** — without having to remember what to look at.

> Scope: a **full** review of the system. To review a single domain (e.g. after touching widgets), run only that
> domain's fan-out phase (§3) + the docs alignment phase (§4). The full workflow runs at milestones: before a
> major release, after a structural refactor, or when the operator asks.

> Complements [[zaelar-change-protocol]]: the *change protocol* closes **one** change; **this** workflow audits
> **the whole system** across the board. They chain (audit → fix → run the protocol for each fix).

---

## 0. Principles of this audit (how to look, not only what)

1. **The code is the source of truth; the documentation is the hypothesis.** Every documented claim is checked
   against the code with `file:line` evidence. Names are not trusted — a module called `security.py` is not
   audited until what it does has been read.
2. **Skeptical / adversarial.** In security it is not enough to confirm that a control exists: **try to break
   it**, thinking like an attacker (an untrusted peer in the cluster, data flowing from the brain into a widget, etc.).
3. **Fan-out by domain, in parallel.** The system is split into independent domains and **one subagent per
   domain is launched at once** (`Agent`/`general-purpose`, in parallel). Each returns a structured report; the
   main agent **synthesises** rather than redoing the work.
4. **Alignment across three layers.** Everything found must match: (a) the **diagram + modules** in
   `.meshkore/docs/architecture` and `modules`, (b) the **context** in `.meshkore/docs/product` + `security`, and
   (c) the **public diagrams** at `/technology` (public site, outside this repo), which are user-facing docs and
   should reflect the current state (their sync is a MANUAL step, so drift there is less urgent than elsewhere —
   see the note below). Every drift is reported as a concrete fix.
5. **Output = report + prioritised plan.** The deliverable is a report with findings by severity and a
   **prioritised improvement plan P0→P3**. The HTML report goes to `~/.meshkore/tmp/*.html`, **never** as an
   artifact.

---

## 1. Reconnaissance phase (get your bearings — ALWAYS first)

Read, in this order, to load the mental model before touching anything:

1. **`CLAUDE.md`** (root) — hard rules, layout of modules, change protocol — and **`.meshkore/docs/criteria.md`**
   (the standing criteria).
2. **`.meshkore/public/cluster.yaml`** — declared modules + `admission` (project rules) + `version`.
3. **Canonical context** (`.meshkore/docs/`):
   - `product/zaelar-product.md` — what zaelar is, its pieces, contracts, decisions (the onboarding single source of truth).
   - `architecture/zaelar-architecture.md` — mental model, seams, how the `nucleo/` brain, `memory/` and `bus/` fit
     together, ASCII diagram.
   - `architecture/zaelar-memory.md` — design of the central memory (SQLite `zaelar.db`, retriever, consolidator).
   - `modules/zaelar-modules.md` — module table + detailed map of the frontend + the meshkore connector.
   - `security/zaelar-security.md` — threat model and controls of the cluster channel (the security module).
4. **Actual repo structure** — list source files (excluding `.venv/.git/.pytest_cache/node_modules`) and
   `git status --short` (to spot uncommitted work, e.g. new widgets).
5. **The public diagrams** — `/technology/*`, outside this repo: curated outward-facing docs; they enter the
   alignment comparison (§4) at lower priority — they are not an automatic mirror of the code.

Live context references INSIDE the repo (the brain is part of this repo; there is no external agent):
`config/v2.json` (the real model routing `fast`/`code_agent`, managed by the UI) and the central memory
`memory/_data/zaelar.db` (persona + the operator's facts).

---

## 2. Audit domains (the system split into pieces)

zaelar is audited in **four domains**. They are the same four every time — extended when a new module appears
(then its domain is added, or it is assigned to the closest one).

| # | Domain | Covers | Reference docs |
|---|---|---|---|
| A | **Voice core + brain (nucleo) + memory + bus + server** | `voice/`, `nucleo/` (FlashBrain + SlowBrain), `memory/`, `bus/`, `server/`, `config/` — pipeline, two speeds, escalation, central memory, nervous system, routers, settings | architecture §0-8, memory (all), product §2/§4/§5 |
| B | **Frontend + widgets** | `frontend/`, `widgets/` — reactive shell, widget isolation, widget contract, generator, SSE | modules §Frontend, architecture §1-5, product §2/§4/§6, `widgets/AGENTS.md` |
| C | **Cluster channel security** | `connectors/meshkore/` (channel on the untrusted profile: `brain.py`→`nucleo/flash/cluster.py`, tools off) + hard controls in `security.py`, `bridge.py`, `voice/tag_protocol.py` | security (all) |
| D | **Docs ↔ code ↔ cluster.yaml alignment** | the `.meshkore/docs/`, `cluster.yaml`, the planning state, the `/technology` diagrams (public site), `CLAUDE.md`, `.env.example`, Makefile | modules, product, architecture, ops, the whole standard |

**MeshKore standard rule:** every domain maps to the modules declared in `cluster.yaml`. When a new module is
declared, **add its check to the corresponding domain** here.

---

## 3. Fan-out: what each domain checks (the checkpoints)

Launch **one `general-purpose` subagent per domain, in parallel** (all in the same message). Each gets: (a) the
context of §1, (b) its checkpoint list below, (c) the output format (§5). Each subagent reads the real code and
returns, per checkpoint, a **VERDICT (OK / DRIFT / BROKEN) + `file:line` evidence + a one-line explanation**,
and at the end a list of **Findings ordered by severity**.

### Domain A — Voice core + brain (nucleo) + memory + bus + server
1. **Entrypoint + composition root**: `python -m server` (`server/__main__.py`); `server/__init__.py create_app`
   mounts the routers and, in its lifespan, starts the EMBEDDED LiveKit worker, the `nucleo/` loop, the `backed`
   widget supervisor and the `memory/` queue consumer. Map which routers exist and how they are mounted.
2. **Conditional mounting per brain**: `active_brain()` (env-first `BRAIN`, default `nucleo`; `direct`/`local` =
   bare baselines) decides what is mounted; the orchestrator loop + `/api/cron` **only** with `BRAIN=nucleo`. The
   UI must query `/api/brain` before polling. Nothing brain-specific wired unconditionally.
3. **Two speeds — FlashBrain**: `nucleo/flash/` (provider `voice/engine/llm/providers/nucleo.py`) serves each turn
   in about a second with a model PER INVOCATION (not a global env) and decides when to escalate. Check that its
   real tools `escalate_to_slowbrain`/`set_style_directive` are declared in `nucleo/flash/router.py` and that
   escalation is enforced in code (not only in the prompt) for what the Flash cannot do.
4. **Two speeds — SlowBrain**: `nucleo/dispatch/` composes the [context+task] prompt → `CodeAgent`
   (`nucleo/agentes/`) async, consumes `escalate.requested` from the bus and delivers through `voice/proactive`
   (voice+UI); `nucleo/memory_agent.py` is the ONLY writer of `memory/`. Check that the SlowBrain never blocks
   the hot voice path and that the CodeAgent model is per invocation (`config/v2.py`, `code_agent` section).
5. **Orchestrator loop + OWN cron**: `nucleo/pulse/loop.py` (~1 Hz) + `nucleo/pulse/scheduler.py` (cron backed by
   `memory.journal`) + `nucleo/cron_api.py` (`/api/cron`) + `nucleo/pulse/sparks.py` (double-gated sparks) — scheduled
   tasks + proactivity + triggers the memory consolidator off the hot path. One loop, mounted in the lifespan;
   look for double starts or paths that start it outside the lifespan.
6. **Loop-agnostic turn coordination**: voice runs on the LiveKit job thread, uvicorn on another loop →
   cross-loop delivery uses `bus.emit_sync`/`call_soon_threadsafe` (`bus/`), NOT a shared `asyncio.Lock`.
   Turn-taking/VAD/barge-in are governed by LiveKit (Silero VAD + turn detector). Check that no lock assuming a
   single event loop has crept back.
7. **Pipeline order** in `voice/engine/pipeline/agent.py` (`input → VAD → stt → brain(nucleo) → tts → output`);
   STT/TTS off the event loop; the LiveKit engine owns streaming/turns/barge-in/preemptive generation.
8. **Tag protocol** (`voice/tag_protocol.py` + the `nucleo.py` provider): tags never reach TTS, a tag split
   across chunks is safe, which tags are recognised (widget + `msg.*` + `cluster.*` + `cron.*` + `architect.*`).
9. **Nervous system** (`bus/`): in-process pub/sub (fnmatch + cross-loop `emit_sync`), `bus/log.py` durable SQLite
   log, `bus/sse.py` SSE bridge (`GET /events`). Check that the key signals (`escalate.requested`,
   `memory.updated`, `widget`, `observer`) have a producer and a consumer, and that nothing introduces an
   external broker.
10. **Central memory** (`memory/`, see `zaelar-memory.md`): a single SQLite `zaelar.db` (WAL); **single writer** =
    `nucleo/memory_agent.py` through the queue/writer; the retriever reads on the hot path (ms). Check there is no
    second direct writer, and that uploads go through the episodic layer (`memory/server_api.py`).
11. **Layering / imports**: does `voice/` import internals of `nucleo/`/`memory/`/`widgets/`/`connectors/` directly
    (coupling must go through the `nucleo.py` provider + `bus/`, not internal paths)? Does `nucleo/` import
    `voice/`? Does anything import `server/` upwards? Map the real edges and flag the undocumented ones.
12. **Config**: `config/settings.py`→`settings.json` (⚙) and `config/v2.py`→`v2.json` (routing `fast`/`code_agent`)
    are applied at boot; redacted public view (secrets → `<key>_set: bool`); look for REASONING models offered for
    the voice path (hard rule) or a global model env (violates "per invocation"), and drift against the docs.
13. **Dead code / orphans / bugs**: check whether loose modules are wired or leftovers; TODOs; visible bugs.

### Domain B — Frontend + widgets
1. **Frontend structure** matches the documented map (Solid-compatible reactive core, dom.js `h()`, store,
   framework-free services, components, lib, `widgets/desktop.js`). Flag present-but-undocumented and
   documented-but-absent.
2. **"No business logic in the client"**: services/components must not carry logic that belongs on the server.
3. **Widget isolation (KEY CLAIM)**: cross-imports in both directions (`widgets/*.py` ↔ `voice/`/`nucleo/`/
   `server/`/`connectors/`; and whether the core imports widgets beyond the `widgets/brief.py` bridge). A broken
   widget must NOT be able to take down audio; a `backed` owner that crashes is isolated by the supervisor
   (`widgets/supervisor.py`). `desktop.js` only speaks the widgets HTTP contract.
4. **Contract + XSS per widget**: audit EVERY `widgets/<id>/` folder — complete manifest, `render(el,data,ctx)`,
   self-contained (no CDN/network from JS), style injected once, **`textContent` for untrusted/web data** (look
   for `innerHTML` with brain or transcript data → XSS). In `data.py`: stdlib only, timeouts, no unbounded fetch,
   no secrets.
5. **`widgets/generator.py`**: atomic `claude -p` agent — prompt over stdin, `--allowedTools "Write Edit Read"`
   (no Bash), `acceptEdits`, cwd, timeout, process lock, never overwrites an existing id, `_validate` (manifest,
   `render`, `data.py` compiles, `__init__.py`). Injection risk (id/spec → path traversal), and whether validation
   is enough (does it check house rules: `innerHTML`/network/non-stdlib imports in the generated output?).
6. **`widgets/server_api.py`**: routes as documented; `wid` normalised at the edge (no traversal). Look for unsafe routes.
7. **`widgets/store.py`**: isolated JSON per widget, atomic write, with a lock.
8. **`widgets/runtime.py`**: catalogue auto-discovery through `manifest.json`, mtime cache.
9. **SSE event path**: brain tag → `llm_processor`/`observer` → SSE → `services/sse.js` → desktop;
   `Desktop._resolve()` id drift (exact→prefix→contains). Confirm the wiring.
10. **Dead/duplicate/inconsistent**: folders with no manifest/`__init__.py`, name overlaps
    (`widgets/brief.py` vs `connectors/meshkore/brief.py`), uncommitted widgets.

### Domain C — Cluster channel security (ADVERSARIAL — try to break every control)
> The cluster channel receives messages from **untrusted external agents**. The channel runs on the FlashBrain
> engine in the **UNTRUSTED profile — NO tools + identity-safe** (`connectors/meshkore/brain.py`→
> `nucleo/flash/cluster.py`): it can reason and talk to peers, never run commands/files/tools. For each claim:
> verify it in code AND **build the attack** that tries to get round it.
1. **Untrusted profile with no tool surface BY DEFAULT**: `nucleo/flash/cluster.py` offers no tools with zero
   permission; check that without a granted permission NO cluster path reaches the `CodeAgent`/dev-worker
   (fail-closed by construction). The permission-gated path — `connectors/meshkore/perms.py`+`store.py`
   (per-cluster profile, deny-all default) — can open `escalate_to_slowbrain` to a bounded dev-worker (temporary
   cwd + `Bash` only to `nucleo/cli/git.py`, authorised repo, re-verified on every commit/push). Also check the
   objective guard (`perms.gate_dev_by_objective`): the `code` permission must NOT suffice on its own without a
   `capsule.objective` set by the operator (set through the operator-only tool `set_cluster_objective`). The
   dev-worker's Read/Write/Edit/Glob/Grep jail is real code (`nucleo/dev_worker_guard.py`, a PreToolUse hook),
   not a prompt convention — check that it is still wired (`--settings` in `claude_session.py`) and that the
   settings file lives OUTSIDE the worker's own workdir.
2. **Cluster tag allowlist**: only `cluster.send`/`cluster.done` from a peer turn; `connect`/`disconnect`
   operator-only. Can a peer slip `[[create:...]]`/`[[cron.create]]` into its reply? See what `_route_reply`
   does with non-cluster tags.
3. **`fence_untrusted`**: neutralises `⟦ ⟧` and sentinels. Try bypasses (homoglyphs, nested fences, zero-width)
   and — critically — check that the **trailer ALWAYS goes last** on EVERY path where peer text enters a prompt,
   **including identity metadata** (the peer's handle/name) and the journal/brief injection into the **voice
   kickoff** (where the turn runs with auto-approved tools).
4. **`scan_outbound`**: hard-secret blocking / fingerprint redaction on EVERY output: the `[[cluster.send]]` tag,
   REST `/send`, heartbeat/nudge, ack/error, **and the `media` field** of any `client.send`.
5. **REST guard** `/api/meshkore/*`: loopback-only + anti DNS-rebind (Host/Origin) or token; EVERY route guarded
   (incl. `/status`), constant-time token compare, no credential leak in responses.
6. **Transport**: `wss://` mandatory unless `MESHKORE_ALLOW_INSECURE=1`; a token in a query string redacted in
   EVERY log/exception/journal.
7. **Flood cap** `MESHKORE_MAX_INFLIGHT`: decremented on ALL exits (an exception in the turn → a leak that jams the channel?).
8. **`store.py`**: `meshkore.json` chmod 600, redaction in journal/SSE/timeline (incl. **inbound peer text**).
9. **Inbound frame validation**: oversized, malformed JSON, unexpected `kind` (the protocol uses `kind`, not
   `type`), unicode tricks in agent/cluster names (does a handle `[SECURITY]` or one with `⟦` break the fence
   labelling?), URLs in the payload (fetched server-side = SSRF?).
10. **Run the tests**: `.venv/bin/python -m pytest tests/cluster/unit/test_security.py -q`; compare against what
    the docs claim; assess coverage against the attacks above.

### Domain D — Docs ↔ code ↔ cluster.yaml alignment
1. **Declared modules vs reality**: every path in `cluster.yaml` exists and is not empty; flag ghost modules
   (declared, not present) and undeclared root directories; `git status` for uncommitted work.
2. **Version coherence**: `cluster.yaml version` = git tag = commits; `state.json` (generated, NOT edited by
   hand); the real model routing (`config/v2.json`, `fast`/`code_agent` sections) vs what the docs say
   (`CLAUDE.md`, `zaelar-model-benchmarks.md`, the `/technology` diagrams on the public site).
3. **The public diagrams** (`/technology/*`, outside this repo): compare their narrative/topology against
   `architecture.md` + `modules.md`. Quote every stale fragment. It is curated content, TRIMMED on purpose for an
   external audience (no internal file paths) — do not expect the same detail as the canonical docs; only flag
   it if it tells an architecture that has been SUPERSEDED.
4. **Planning state**: statuses consistent with reality (WIP / parked / done…).
5. **Ops/deploy/conventions/change-protocol/audit**: stale content (paths that no longer exist, commands that do
   not match the Makefile — cross-check every `make` quoted, env vars vs `config/.env.example`).
6. **`CLAUDE.md` vs reality**: logging to `.meshkore/logs/`, a root with no loose `.py`/`.html`, current rules.
7. **Standard hygiene**: no ad-hoc `docs/`, module logs under `.meshkore/modules/<id>/logs/` match the declared
   ids; no folders for undeclared modules nor modules without a log folder.

---

## 4. Synthesis (the main agent, after the fan-out)

When the four subagents return, the main agent **cross-checks and consolidates** — it does NOT re-audit:
1. Merge findings; deduplicate those that appear in several domains (e.g. the "zero cross-imports" claim is seen
   by B and A; a model-name drift by A and D).
2. Classify by cross-cutting severity: **security > architecture/correctness bugs > doc drift > cosmetic**.
3. Confirm the **three-layer alignment** (§0.4): do the diagram, the modules, the context and the public
   `/technology` diagrams say the same as the code? Each divergence = a concrete fix in the plan.
4. Build the **prioritised improvement plan** (see §5).

---

## 5. Output — the deliverable

**A) Audit report.** Kept **locally**, never committed to this public repo: an HTML or Markdown report in
`~/.meshkore/tmp/zaelar-audit-<date>.*` with an executive summary (3-5 lines), verdicts per checkpoint and domain
with `file:line` evidence, and consolidated findings by severity (id, severity, `file:line`, scenario/impact,
fix), plus the audited commit/version.

**B) Prioritised improvement plan — as a planning initiative (mandatory):** create a remediation initiative in
the local planning folder with the tasks **one by one** (checkbox `[ ]`, id `T-NN`), each anchored to a finding
in the report (`file:line` + fix + whether it needs an operator decision), grouped by priority:
- **P0 — Security** (bypass of hard controls, XSS, exfiltration, credential leak). Fixed first.
- **P1 — Architecture / correctness bugs** (event-loop stalls, an update that does not restart the brain, races,
  fire-and-forget).
- **P2 — Doc ↔ code drift** (`cluster.yaml` first, since it is what the daemon reads, then the `.md` docs,
  `CLAUDE.md`, `.env.example`; the public-site diagrams go last — their sync is manual by design).
- **P3 — Cosmetic / dead code / housekeeping.**

That way the remediation work is tracked and not lost; each task is closed individually with
[[zaelar-change-protocol]].

**C) Rule:** the audit **fixes nothing on its own**. It reports and stops. Fixes are applied only with the
operator's OK, and each one is closed with [[zaelar-change-protocol]] ("run the protocol").

---

## 6. How to repeat it (quick checklist for the agent)
1. `TodoWrite` with the phases (reconnaissance → 4 domains → synthesis → report).
2. §1 reconnaissance (read the 5 context groups).
3. Launch the 4 subagents of §3 **in parallel** (one `Agent general-purpose` per domain, with its checkpoints).
4. When they all return, §4 synthesis + §5 report + P0-P3 plan.
5. Report to the operator and wait for a decision on what to fix. Touch no code during the audit itself.

> **As the project evolves:** when a module is added, update §2 (domain table) and §3 (checkpoints) of this
> workflow so the next audit covers it. This doc is part of the context that travels with zaelar.
