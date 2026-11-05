---
title: Cluster conversation monitoring — evaluation criteria
category: ops
updated: 2026-07-26
owner: ricart
status: current
---

# How cluster (agent-to-agent) conversations are monitored, and against which criteria

**Goal:** our agent conducts a conversation with ANOTHER agent **the way a human would** — knowing who it is
talking to, whether things are moving forward, not letting its resources be taken, agreeing on how to work
together, and **knowing when to stop**.

**Hard boundary:** this applies ONLY to the **agent-to-agent (cluster)** channel. With the **operator**
(voice/chat) and with **humans** (WhatsApp/email) the conversation must **always flow** — nothing here slows it
down. The model-to-model tunnel is the only one that needs regulating (unequal capabilities, risk of wasted time
or of being exploited).

## How it is monitored (two layers + observability)

1. **Deterministic layer, in the bridge (real time, every turn).** Cheap, no LLM, fail-open. It is the reflex:
   it measures, decides and acts in the moment (`connectors/meshkore/bridge.py` + `capsule.py` + `security.py`).
2. **Semantic layer, on the heartbeat.** A model reads the recent exchange and judges what a heuristic cannot
   catch (nonsense, capability mismatch). It intervenes or warns when the conversation is going nowhere
   (`connectors/meshkore/evaluator.py`, see criterion 2).
3. **Observability.** Everything leaves a trace in the timeline (`kind:cluster` with `pace`/`stall`,
   `kind:resource`, `kind:homeostasis`), and **every event carries `ver`** → you know which version evaluated each
   line.

## THE CRITERIA (the evaluation checklist)

Each criterion = the **human behaviour** it emulates · **mechanism** · **signal/threshold** · **what it does**.

### 1. Do I know who I am talking to and where we are? — SITUATION (capsule)
- **Human:** you remember who everyone is, what you talked about, what was left open and which phase you are in.
- **Mechanism:** per-peer capsule (dossier + objective + open loops + PHASE greeting→probing→work→closing).
- **Signal:** phase derived from the state of the relationship.
- **Does:** no re-introductions during work/probing; steers toward the objective; does not re-negotiate what was
  already decided.

### 2. Does the conversation FLOW, or has it stopped making sense? — HEALTH by INTELLIGENCE
- **Human:** you step back and judge whether the conversation is worth it; if the other side does not follow,
  repeats itself, is blocked or says things that make no sense, you STOP and hand back the turn.
- **Mechanism (KEY):** the semantic judgement is made by a **MODEL**, not by hardcoded patterns (`evaluator.py`):
  an INDEPENDENT, read-only evaluator with a CLOSED catalog `health`
  (flowing/stuck/dead_end/imbalanced/off_track) × `action` (continue/concise/hand_back/pause), fail-open. Being
  generic, it works for ANY agent and ANY way a conversation can degenerate — a phrase regex would only fit one
  peer and miss the next. The only deterministic support: EXACT repetition (dedup, tokens) + `near_repeat`
  (near-repetition, as a signal).
- **When:** off the hot path, on the heartbeat, throttled by `MESHKORE_EVAL_SECS`, only for ACTIVE conversations
  (it does not re-judge a dead one). It is a «step back» judgement, not a per-turn reflex.
- **Does:** applies the model's verdict — `hand_back` (yields the turn with one sentence and waits) · `pause`
  (goes quiet + notifies the operator once) · `concise` (the next turn is short) · `continue` (no interruption).
  A `dir:eval` event with the verdict lands in the timeline.

### 3. Is there a BALANCE of resources? — NO ONE DRAINS OUR TOKENS
- **Human:** you do not let others dump all the work on you; you collaborate as equals.
- **Mechanism:** per-peer balance (`given`/`received`/`offloads`/`code_out`) + `looks_like_offload` (requests to
  produce) + `guard_code_outbound` (code dump → pointer to the repo).
- **Threshold:** `equilibrado` <3× · `sesgado` ≥3× + offload · `explotación` ≥6× + sustained offload (min turns
  4, given 1500).
- **Does:** silence toward the peer + keep it short · code goes through the repo · notifies the operator once on
  `explotación`. `kind:resource` events.

### 4. Have we AGREED on how to work? — PACT
- **Human:** you agree on working norms with the other side and respect them while they make sense.
- **Mechanism:** per-peer pact (cadence/medium/scope), CLOSED vocabulary; tag `[[cluster.pact]]`; proposed when
  greeting; hierarchy **system > operator > pact** (a pact never loosens what is above it).
- **Does:** injects the norms into the turn + **REAL cadence** (throttle in `cluster.send` → no flooding).

### 5. Is it SAFE? — PROTECTION (cluster security)
- **Human:** you do not trust a stranger: you do not reveal what is yours, you do not act on their behalf.
- **Mechanism:** tools OFF (untrusted profile) · identity-safe (no operator PII) · `scan_outbound` (blocks
  secrets) · fence + trailer at the end (anti-injection) · tag allowlist · flood cap.
- **Development work for a peer** is a separate, explicitly granted path: a per-cluster `code` permission plus
  an operator-set objective (`capsule.objective`, tool `set_cluster_objective`, guard
  `perms.gate_dev_by_objective`) enable a bounded dev-worker (temporary cwd + git to the authorized repo + real
  Read/Write/Edit confinement via `nucleo/dev_worker_guard.py`, a PreToolUse hook — see
  [`zaelar-security.md`](../security/zaelar-security.md)).

### 6. Is the MACHINE healthy? — HOMEOSTASIS
- **Human:** your body keeps itself going (you do not think about your heartbeat). It sustains the channel; it is
  not about the conversation.
- **Mechanism:** recycles a degraded LiveKit engine (when safe), rotates logs, evicts dead capsules.
  Deterministic.

### 7. Do I know which VERSION is evaluating? — TRACEABILITY
- **Mechanism:** `version.short()` (`2.74+sha`) in `/api/status`, in the `ver` of every event and in the frontend
  (◉).
- **Use:** the `sha` in `/api/status` == `git HEAD` proves an instance runs the latest code; timelines can be
  audited per version.

## What «all good» vs «intervene» looks like

- **Good:** coherent phase (no re-introductions), low `no_progress`, resource ratio <3×, no `pace:silent` or
  `resource:explotación`, the peer contributes, the channel is connected, no errors in the timeline.
- **Intervene:** `no_progress` rising → hand back the turn; ratio ≥3× + offload → shorten / use the repo;
  repetition → assertive → go quiet; incoherent peer / capability mismatch → pause and wait; always notify the
  operator once per event.

## Extension points

The design leaves room for:

1. **Per-peer state in `/api/meshkore/status`** (resource balance + pact + conversation health + `no_progress`)
   for an at-a-glance view alongside the timeline.
2. **Folding the resource signal into the evaluator's verdict**, and tuning the evaluator's window/throttle for
   many simultaneous conversations.
3. **Pact management by the operator** (an endpoint to set/read norms), multi-round negotiation and
   cluster-level pacts.
4. **Richer reciprocity** than character counts (counting the peer's real contributions, e.g. commits to the
   repo).
5. **Self-audit of cluster conversations**, complementary to the health evaluator (the general conversational auditor was
   removed in V2-851; a cluster-only one would be new work).
6. **Historical per-peer conversation-quality metrics** (trend, not only the instant).

## Sources

Context: `CLAUDE.md`. Security: [`zaelar-security.md`](../security/zaelar-security.md). Observability:
[`zaelar-observability.md`](zaelar-observability.md).
