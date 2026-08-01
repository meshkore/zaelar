---
title: Zaelar Architecture
category: architecture
updated: 2026-08-01
owner: ricart
status: current
---

# zaelar — Architecture (source of truth)

> The portable mental model of what we've built. Read this to understand the whole system and its seams.
> Companion to [`.meshkore/docs/product/zaelar-product.md`](../product/zaelar-product.md) (onboarding/status).
>
> zaelar's brain is **its own**: the module `nucleo/` («Colmena», two speeds — **FlashBrain** on the voice turn +
> **SlowBrain** async), with a **central memory** (`memory/`, SQLite) and an in-process **event bus** (`bus/`).
> Cron/proactivity are governed by the `nucleo/` orchestrator loop. **The design source of truth is
> `EPIC-v2-colmena` (`.meshkore/roadmap/`) + the live diagram at `/architecture`.**

## 0. Roles at a glance — client vs server

Two independent sides talk over **WebRTC (audio) + HTTP + SSE**. Naming note: `voice/` is the SERVER-side pipeline,
NOT the browser UI — the user-facing audio I/O lives in `frontend/`.

| Piece | Side | Role |
|---|---|---|
| `frontend/` | **client** (browser) | The whole UI: captures mic + camera, draws the orb (agent voice) and the mic spectrum, shows widgets on the canvas, text chat wall, ☾/☀ dark/light theme (dark default, one `--hb-*` CSS variable namespace shared with widgets — INI-011). No business logic — a thin reactive shell (ES modules, no build). |
| `server/` | server | FastAPI transport: serves the frontend, the WebRTC offer/ICE, `/events` SSE, settings, the widgets HTTP API, the first-run wizard (`/api/wizard/*`), the music connector control plane (`/api/spotify/*` OAuth + `/api/music/state`) and the **full-screen config area** (`/api/config*`, V2-043: per-piece API/model + API balances). Composition root + entrypoint (`python -m server`); its lifespan also starts the LiveKit agent worker (embedded), the `nucleo/` loop, the widgets supervisor and the memory queue consumer. |
| `voice/` | server | The voice **engine** (`voice/engine/`, LiveKit AgentSession): receives mic audio → STT → brain → TTS → back to the client. Turn-taking/VAD/barge-in are governed by LiveKit (VAD Silero + turn-detector `MultilingualModel` + `allow_interruptions`). Top level = brain-agnostic contract: observer (SSE), prompt, `tag_protocol`, `brain_notes`, `proactive`, TTS/STT backends. |
| `nucleo/` | server | zaelar's **own brain** (default `BRAIN=nucleo`). Two speeds: **FlashBrain** (`nucleo/flash/`, sub-second voice layer, non-reasoning model per-invocation) + **SlowBrain** (`nucleo/dispatch.py` + `nucleo/memory_agent.py` + `nucleo/agentes/`, async Claude Code / Codex agents behind a `CodeAgent` interface). Orchestrator loop `nucleo/loop.py` (~1 Hz) + own cron `nucleo/scheduler.py` + panel `nucleo/cron_api.py` + `nucleo/sparks.py`. Exposed to the voice engine as provider `voice/engine/llm/providers/nucleo.py`. |
| `memory/` | server | **Central memory** — SQLite `zaelar.db` (sqlite-vec + FTS5 + RRF + graph + forgetting). Absorbed the old `files/` as an episodic layer. |
| `bus/` | server | In-process **event bus** (pub/sub, generalization of `voice/observer.py`) + durable SQLite log + SSE bridge. |
| `widgets/` | server + client | Full-stack widgets: `widget.js` renders in the client, `data.py` serves data on the server, per-widget JSON store. Isolated from the voice core. |
| `config/` | server | Runtime settings. `config/settings.py` = STT/TTS/voice/language; `config/v2.py` = model routing (fast + code_agent + memory) + `active_brain()`; `config/credentials.py` = single writer of the credential store; `config/profiles.py`+`doctor.py` = coordinated profiles + capability detector (wizard V2-040); **`config/balances.py`** (V2-043) = external-API balances (proactive where exposed — ElevenLabs — + reactive from the last classified error). The **⚙ full-screen config area** (choose API/model per piece) is served by `server/config_api.py` (`/api/config*`); its balance alerts surface in the ◉ status dialog. |

**Role of the brain (`nucleo/`):** it is zaelar's OWN brain — memory, cron/proactivity, tools, reasoning — no
external agent. **FlashBrain** owns the hard-realtime voice turn (~sub-second); **SlowBrain** does async
memory/tools/reasoning off the voice path (escalation via `escalate_to_slowbrain` → `nucleo/dispatch.py`). The brain
drives the canvas through a thin tag contract (§2).

## 1. Three layers, decoupled

```
┌── VOICE + CANVAS (zaelar, this app · :43917) ─────────────────────────────┐
│  The ONLY user-facing surface.                                           │
│  • Mic → STT (Whisper LOCAL by default) → BRAIN → TTS  (voice/agent.py)   │
│  • Widget desktop run BY VOICE (frontend/app/widgets/desktop.js):        │
│      draggable + position-persisted chrome, non-overlapping placement,   │
│      activity rail above the orb. The frontend/ ES-module app is the front.│
└──────────────────────────────────────────────────────────────────────────┘
        ▲ silent tags over SSE                │ user speech (turns)
        │ (show/close/push/create/modify)     ▼
┌── BRAIN («Colmena» = nucleo/, zaelar's OWN) ─────────────────────────────┐
│  Decides + acts. Owns the canvas via SILENT TAGS in its reply.           │
│  • FlashBrain (nucleo/flash/) — sub-second voice turn, non-reasoning     │
│    model per-invocation; provider voice/engine/llm/providers/nucleo.py   │
│    (streams reply, parses tags, keeps them out of TTS)                   │
│  • SlowBrain (nucleo/dispatch.py + memory_agent.py + agentes/) — async   │
│    CodeAgent (Claude Code/Codex), reached via escalate_to_slowbrain      │
│  • Loop nucleo/loop.py (~1 Hz) + cron nucleo/scheduler.py + sparks.py    │
│  • Memory: memory/ (SQLite zaelar.db). Persona/instructions injected     │
│    each connect from widgets/brief.py + nucleo/flash/prompt.py           │
└──────────────────────────────────────────────────────────────────────────┘
        │ POST /widgets/generate · /widgets/modify
        ▼
┌── COMPUTE (one atomic Claude Code agent) ────────────────────────────────┐
│  widgets/generator.py — spawns ONE headless `claude -p` per task:        │
│  born → does exactly the task → deploys into widgets/<id>/ → exits.       │
│  File tools only, scoped to zaelar, hard timeout, single-agent lock,     │
│  output VALIDATED before trusted. No context/queue/history (by design).  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Ownership / isolation.** The widget circuit (`widgets/` + `frontend/app/widgets/desktop.js` + the SSE `widget`
events) is a **self-contained feature**. It never touches the voice core (STT/turn-taking/TTS). The agent is the
only thing that writes new code, and only under `widgets/<id>/`.

> **Note (V2-070):** these three layers describe how zaelar *thinks and acts*. **Machine health** — keeping the
> process itself alive and unclogged (LiveKit engine, logs, capsules) — is maintained by a separate **autonomic
> homeostasis layer** (`nucleo/homeostasis.py`, deterministic, no model) that lives beside the brain. See §5g.

## 1b. Trust boundaries — voice/chat (trusted) vs cluster (UNTRUSTED)

> **Full end-to-end narrative** (connection lifecycle, the exact order every guard runs in, the permission-gated
> dev-worker + its filesystem jail, a defense-in-depth summary table): `zaelar-cluster-channel.md`. This section
> stays a summary of the trust-boundary MODEL; that doc walks the actual algorithm.

zaelar has a **third I/O channel** next to voice + chat: the native MeshKore cluster link
(`connectors/meshkore/`), where zaelar talks to **external agents we don't control**. Voice and chat are the
operator's (trusted, local). The cluster is not. **One mind, two profiles** (V2-069): the SAME FlashBrain engine
conducts every conversation — operator OR agent — but a cluster turn runs in the **UNTRUSTED profile**: **tools OFF
in code** (`nucleo/flash/cluster.py` offers none) and an **identity-safe system** (`build_cluster_system` never
touches operator state/PII). A peer can make zaelar reason + talk, never act. The trust boundary is a **deterministic
capability profile bound to WHO you're talking to** — enforced structurally, not by prompts:

```
   operator (TRUSTED)                         external agents (UNTRUSTED)
   voice / chat ──┐                            MeshKore cluster (WS)
                  ▼                                     │  peer text fenced as ⟦UNTRUSTED⟧,
   ┌── FlashBrain engine (nucleo/flash/) ┐              │  our security trailer appended LAST
   │  operator profile: full tools       │              ▼
   │  + operator memory                  │   ┌── FlashBrain · UNTRUSTED profile ──┐
   └─────────────────────────────────────┘   │  tools OFF · identity-safe system  │
              │                               │  reason + talk to peers ONLY       │
              ▼                               │  state in the per-peer CAPSULE     │
        terminal / files / tools             └────────────────────────────────────┘
        (operator turns only, $HOME)
```

Key invariants (full detail in `.meshkore/docs/security/zaelar-security.md`):
- **The cluster turn runs tool-less BY DEFAULT (UNTRUSTED profile)** — there is nothing to deny on that path because
  it offers no tool/terminal/file surface, and its system prompt never exposes operator PII. Conversation state
  lives in the per-peer **capsule** (`connectors/meshkore/capsule.py`), quarantined (`trust=untrusted`) — never in
  the operator's prompt. **V2-076 (2026-07-26) built the permission-gated version of what V2-010 scoped**: the
  operator can grant a per-cluster permission profile (`connectors/meshkore/perms.py`+`store.py`, deny-all default)
  that lets a cluster turn reach `escalate_to_slowbrain` → a **dev-worker** (`nucleo/dispatch.py`) scoped to a
  disposable cwd + `Bash` only to `nucleo/git_cli.py` (clone/commit/push to the operator-authorized repo only, with
  the real git `origin` re-verified on every commit/push). This additionally requires the operator to have set an
  **objective** for that specific relationship (`capsule.objective`, `perms.gate_dev_by_objective`) — permission
  alone never suffices. Zero permission = byte-identical to the tool-less path above. **Filesystem jail: closed
  2026-07-26** — `nucleo/dev_worker_guard.py` (a real Claude Code `PreToolUse` hook) denies Read/Write/Edit/Glob/
  Grep outside the worker's cwd (code-enforced, not prompt convention); `nucleo/sandbox.py` adds resource rlimits
  on top (best-effort on macOS for the memory cap specifically — see zaelar-security.md for the honest platform
  caveat).
- Only `cluster.send`/`cluster.done` may fire from a cluster turn; `connect`/`disconnect` are operator-only.
- **Third rule level — the conversation pact (V2-072).** A cluster turn is governed by THREE hierarchical rule
  levels: **(1) system/hard** (BRAIN RULES + security: trailer, tools-off, `scan_outbound`, V2-071 resource guard) >
  **(2) operator** (`state.rules`) > **(3) pact** = communication norms NEGOTIATED between the two agents for their
  relationship. The pact is cluster-only and can only RESTRICT our own behaviour (cadence / medium / scope) — never
  grant a capability (closed vocabulary). It is proposed at greeting, recorded when agreed via the cluster-turn tag
  `[[cluster.pact:<cluster>]]{to,cadence_s,medium,scope,note}[[/cluster.pact]]` (added to the cluster-turn tag
  allowlist → `capsule.pact_set`), lives in the per-peer capsule (`capsule.pact`), is injected into every cluster turn
  below the trailer + operator rules (`capsule.pact_compose`), and its **cadence is really enforced** by a throttle in
  `cluster.send` (`capsule.cadence_wait`). Full detail in `.meshkore/docs/security/zaelar-security.md`.
- **Conversation health by MODEL JUDGMENT (V2-075, supersedes V2-073) — cluster-only.** With the OPERATOR the
  conversation must ALWAYS flow; this criterion applies ONLY to the agent-to-agent (cluster) channel. **V2-073's
  first attempt was a hardcoded regex** (`capsule.looks_stuck`: Spanish block phrases + ⛔/🚫) that caught one real
  peer (`zalo` repeating "⛔ Estamos en fase Definición, no puedo discutir…") but, per the operator's own correction
  of principle, a regex only ever adapts to the last peer seen — degeneration patterns are infinite. **`looks_stuck`/
  `advanced` were DELETED**; `connectors/meshkore/evaluator.py` now runs an **independent model** (read-only, no
  tools, safe over untrusted content) over the recent window + metrics, returning a closed catalog — `health` ∈
  `flowing`/`stuck`/`dead_end`/`imbalanced`/`off_track`, `action` ∈ `continue`/`concise`/`hand_back`/`pause` — off-
  hot-path in a throttled heartbeat (`MESHKORE_EVAL_SECS`, active chats only), fail-open. The bridge applies the
  verdict: hand back the turn (one short message then stop), pause + alert the operator once, or go concise.
  Deterministic bits remain only for the generic/structural: exact-repeat dedup, `capsule.near_repeat` (a signal
  feeding the evaluator, not a verdict by itself), resource ratios, security. Emits observer `cluster` events with a
  `pace` field. **`off_track` enforcement (closed 2026-07-26):** the dev-worker escalation path is gated by
  `perms.gate_dev_by_objective` (needs an operator-set objective, not just a granted permission); the conversation
  itself gets a DIFFERENT operator alert specifically for `off_track` (names the objective set or missing, asks
  the operator to decide) instead of the generic dead_end/stuck wording — see `bridge._evaluate_and_apply`. The
  operator sets a relationship's objective with the operator-only tool `set_cluster_objective`. Full initiative:
  `.meshkore/roadmap/initiatives/V2-075-criterio-conversacion-inteligencia.md` (+ V2-073 for history).
- Outbound `scan_outbound` blocks hard secrets (+ redacts fingerprints); the REST control-plane is loopback/token-
  guarded; `wss://` only; peer text is fenced (`neutralize_identity`/fence-escape) with our trailer LAST.
- The cluster (text + URLs over WS) has **no path to mic/camera/voice** — those are client-side over local WebRTC.

## 2. The brain ⇄ canvas contract — silent tags

The brain emits these in its spoken reply; the nucleo provider (`voice/engine/llm/providers/nucleo.py`, via
`voice/tag_protocol.py`) extracts them (never spoken) and emits a `widget` event on the bus that the frontend
(`services/sse.js`) routes to the desktop. **This tag vocabulary is the entire coupling between the brain and the
UI** — keep it small and stable.

| Tag | Meaning | Desktop action |
|---|---|---|
| `[[show:ID]]` | show a widget that loads its own data | `desktop.show(id)` |
| `[[close:ID]]` / `[[close]]` | **hide** a widget (never deletes) | `desktop.close(id)` / `closeAll()` |
| `[[push:ID]]{json}[[/push]]` | hand the brain's gathered DATA to a widget | `desktop.show(id,{data})` |
| `[[create:ID]]<spec>[[/create]]` | build a NEW widget on demand | `desktop.createWidget(id,spec)` → `POST /widgets/generate` |
| `[[modify:ID]]<change>[[/modify]]` | edit an existing widget | `desktop.modifyWidget(id,change)` → `POST /widgets/modify` |

Streaming safety: tags can arrive split across token chunks; the parser holds any unclosed `[[…`/`[[push`/
`[[create`/`[[modify` out of the TTS stream until complete, so a tag is never spoken and never half-parsed.

## 3. The widget contract — `widgets/<id>/`

A widget is a folder (catalog auto-discovers it from `manifest.json`, cached by mtime in `runtime.py`):
- `manifest.json` — `{id, version, title, description, whenToUse, keywords[], entry:"widget.js"[, transient]}`.
- `widget.js` — ES module `export function render(el, data, ctx)`. Self-contained (no CDN/network from JS),
  injects its own style once, **textContent for any untrusted/web data** (XSS), styled with the shared `--hb-*`
  CSS variable contract so it follows the app's dark/light theme automatically (`widgets/AGENTS.md`, INI-011).
  Served with `Cache-Control: no-cache` (`widgets/server_api.py`) so an edit is never invisible behind stale
  browser cache (W-009).
- `data.py` — `view_data(q="") -> dict` (server-side, stdlib only; may fetch live). Optional.
- `__init__.py` — empty (package).
`transient:true` widgets (e.g. `search`) render in the **activity rail above the orb**; the rest are cards.

## 3b. PROGRESSIVE capability selection — the prompt is O(K), not O(N) (V2-085, 2026-08-01)

**Measured before touching anything** (real catalog, 16 widgets): `brief.for_prompt()` put the ENTIRE catalog in
EVERY turn's prompt (2,497 chars) and `GET /widgets` returned all 16 manifests in full (25,639 chars) to a consumer
(`desktop.js::_resolve`) that only wanted the **ids**. Both are O(N): at 1,000 widgets a "¿qué hora es?" would drag
~150 KB of irrelevant catalog, and at 10,000 the turn is simply not viable — cost, latency, and above all decision
noise for a small model.

**The rule: what the model sees is O(K).** Growing the catalog must not grow an unrelated turn.

**`widgets/selection.py`** is the only place that decides which widgets enter a turn, in priority layers (extending
the V2-078 ladder rather than replacing it):

| Layer | What it is | Why it can't be dropped |
|---|---|---|
| `open` | everything the operator has ON SCREEN | it's their screen — the source of truth |
| `named` | what the operator NAMES this turn, resolved by `runtime.rank()` (name/alias, V2-082) | **this is what makes thousands viable** — a widget at position 9,999 is promoted into the prompt the moment it's named |
| `recent` | the MRU `state.recent_widgets` (V2-078), capped | cross-turn continuity after it's closed |
| `fill` | the rest of the catalog, in order, until the budget runs out | discoverability only — first thing to go |

Hard budget `MAX_WIDGETS = 20`, chosen so **today nothing changes** (16 widgets → all fit, prompt byte-identical to
before: zero regression for the operator) while the O(K) guarantee is written in code. The exact value barely
matters: correctness does not depend on it, it depends on the `named` layer.

**What it deliberately does NOT do:** classify intent with verb/keyword tables. It does not decide whether the turn
"is about widgets" — it only RETRIEVES plausible candidates and lets the model decide by function-calling.
Retrieval ≠ understanding (`feedback_no_hardcoded_understand`).

**Why truncating is safe — the escape hatch.** `show_widget` and `widget_data` resolve their argument server-side
with `runtime.identify()` against the FULL catalog (`providers/nucleo.py`). If a named widget somehow missed the
top-K, the model can pass the operator's own words and the server still resolves it. When anything is left out the
prompt SAYS SO, with that instruction attached — otherwise the model would either deny capabilities that do exist
or start inventing ids. **Trimming the prompt never trims what the system can open.**

**Endpoints — progressive loading.** `GET /widgets` now returns a COMPACT INDEX (id, name, title, aliases, origin,
one-line purpose capped at 120 chars, `transient`): 25,639 → 5,142 chars on the real catalog, ~5× less, and it
drops `actions`, payload schemas and `usage` prose entirely. Full manifests come one at a time from
`GET /widgets/{id}/manifest`, or via the explicit ADMIN escape hatch `?full=1` (debug/export — never the hot path).
`?q=` + `?limit=` narrow the index server-side with the same name/alias ranking for consumers that can't take
thousands of rows; `count` is always the real total, so nobody mistakes an extract for the inventory.

**State can't swallow the catalog.** `state.widget_registry` is capped at `_REGISTRY_CAP = 200` rows + a
`_truncated` marker. `compose_state()` does not include it today — but "today it doesn't" is not a guarantee, and a
10,000-widget catalog leaking into a prompt through a future change would be an expensive, silent incident.

**Observability per turn.** `build_flash_system` writes `widgets_n_total`, `widgets_n_selected`, `widgets_n_open` /
`_named` / `_recent` / `_fill`, `widgets_hidden`, `widgets_selected_ids` and `sz_widgets` into `timings` — the same
channel `/debug` already uses for the `sz_*` size breakdown. So a turn can always answer *how many widgets were
candidates, which were selected, and why*.

**Measured after** (turn that is NOT about widgets): 100 widgets → 2,763 chars · 1,000 → 2,764 · 10,000 → 2,765.
Flat. Naming the last widget of a 10,000 catalog finds it in 4.5 ms. Pinned by
`tests/browser/unit/widgets/test_selection_scale.py` (synthetic 100 / 1,000 / 10,000).

## 3c. The NETWORK is native, not a widget — public clusters (V2-086, 2026-08-01)

**What happened:** the operator pasted MeshKore's own invitation to a public cluster and nothing happened. The
cause was not one bug but **four stacked blockers**, each of which alone was enough to kill it:

1. **The tool wasn't offered.** `connect_cluster` was gated on having the `cluster-registro` widget open (V2-064)
   — verified live in turn 766: the tool simply wasn't in the offered set, so the model *could not* act. That gate
   made the capability undiscoverable: to connect a NEW cluster you had to already know to open a specific widget.
2. **The schema couldn't express it.** `required: ["cluster_id", "token"]` — and MeshKore Commons is `tokenless`
   by design. The model had to either invent a token or not call.
3. **The description refused that shape of input** — correctly. The MeshKore invite is textbook prompt-injection
   shape ("connect now and keep the socket open", "pick your own handle", "Then GET https://…"), and that guard
   exists because of a real incident.
4. **The transport couldn't do it.** `client._url()` always sent `token=` and never `vis=public`.

**The resolution for #3 is the interesting one, and it is NOT weakening the guard: separate ORDER from
PARAMETERS.** The operator's request is the authorization; the pasted block is only where the parameters come
from. Block alone → recognize it and ASK ("veo una invitación a un cluster público, ¿quieres que entre?"), never
act. Block + operator's request → act, reading the id from the block. This preserves the defense exactly (a block
arriving on its own still does nothing) while making the workflow possible — and it's the operator's own
ask-when-uncertain pattern from V2-082, applied to the network.

**Public vs private is a real protocol distinction, not cosmetic.** Sending `token=` empty on a public cluster is
NOT the same as omitting it: the server reads a blank token as failed auth, not anonymous entry. So `_url()` has
two modes and `store.resolve()` accepts `cluster_id` alone when `vis="public"`.

**The network is a NATIVE surface.** The `cluster-registro` widget is **gone** (its last state is preserved in
git at `ea49962`). Connectivity is infrastructure — it's what plugs the agent into the outside world — not a
user widget the operator creates or deletes. It now lives as the **4th ChatWall tab** («Clusters», beside
Chat/Procesos/Crons), routed by `show_panel` like the others. It lists every cluster we hold credentials for —
**connected or not** (before, a cluster that failed to connect vanished from the list precisely when knowing it
existed mattered most) — with state, peers and message counters. **No conversation is stored**: clusters have
their own monitor, so duplicating history here would just be a second source of truth (operator's call).

**Alias collision guard.** Caught by live testing: connecting to Commons, the model picked the default alias
`meshcore` — already the operator's PRIVATE cluster — which would have overwritten its token. The alias is chosen
by a model, so uniqueness is guaranteed in code (`store.unique_name`): same name + same cluster_id = legitimate
reconnect; same name + different cluster_id = suffixed (`meshcore-2`).

**Verified live:** connected to MeshKore Commons (`c_1b938b9ede1b436980e2`) with no token, peers
`greeter, wanderer, zalo` visible, alongside the operator's private cluster, both rendered in the native tab.

## 4. The widget circuit (check → reuse / create; hide ≠ delete)

When the user wants a widget, the brain follows: **1)** is it (or a close match) already in the catalog? → just
`[[show]]` it. **2)** if not → tell the user it's not available yet, ASK to create it, then `[[create]]`.
Widgets are **never deleted** — `[[close]]` only HIDES; they persist and can be shown again. Reuse beats
duplicating. (`generator.generate_widget` also refuses to overwrite an existing id, as a safety net.)

## 5. The compute layer — one atomic agent

`widgets/generator.py` is zaelar's single local code agent, learned from (but NOT dependent on) MeshKore's daemon
runner. Per task it runs `claude -p` (prompt via **stdin** — claude 2.1.x truncates large positional prompts),
with `--allowedTools "Write Edit Read"` (no Bash), `--permission-mode acceptEdits`, `cwd=zaelar`, a timeout, and
a process-wide lock so **only one agent runs at a time**. The agent reads the example widgets to learn the
contract, writes `widgets/<id>/`, and exits. zaelar then `_validate`s (manifest parses + has title/keywords,
`export function render` present, `data.py` compiles, `__init__.py` exists) before the widget is trusted.

**Credentials / auth seam.** There IS a credential store: `.meshkore/credentials/` (gitignored, chmod 600). API
keys live in `zaelar.env` (loaded by `server/common.py` AFTER `.env` with `override=True` → the store WINS);
`config/credentials.py` is its single writer (atomic, name-validated, redacted `status()` that returns presence
only). Provider-specific dynamic secrets get their own file (e.g. Spotify OAuth tokens → `spotify.json`, written by
`connectors/spotify/auth.py`). The UI-managed flow is the first-run **wizard** (V2-040, `server/wizard_api.py` +
`config/doctor.py`) + per-connector guided cards. Config is UI-managed (product invariant); `.env` is a power-user
fallback. If a capability still needs a key the brain doesn't have, it ASKS in conversation rather than building blind.

**The provider catalog.** The atomic `claude -p` agent is one provider of code/compute; zaelar models these as a
flexible catalog the brain routes between per task. The second provider is the **Architect**
(`connectors/architect/`, doc in `zaelar-modules.md §Architect`): the machine's shared MeshKore daemon, driven by
voice through silent `[[architect.ask:<project>]]` / `[[architect.new]]` tags. Where the widget agent is atomic
and context-free, an Architect project's **architect-master** is long-lived and conversational — it plans, keeps
a roadmap, dispatches worker agents, and its output can stay in its own repo or be adopted back (e.g. as a
widget). Both providers share the same async feedback loop: fire-and-forget from the brain's point of view,
result returned as a `[SISTEMA]` note (`voice/brain_notes.py`) + proactive voice/UI delivery (`voice/proactive.py`),
so the brain reports real outcomes, never assumed ones. Architect tags are operator-only (the cluster bridge
allow-list never admits them) and the daemon token lives in `.env`.

## 5b. Web search — a SHARED, model-agnostic capability (V2-022)

Web search is **its own primitive** (`nucleo/websearch.py`), shared by both brains — we do NOT rely on the model
having native search (Grok/GLM/Z.AI don't; Claude Code does). **Who decides to search = the model itself, via
function-calling** — no separate classifier. The FlashBrain gets the question + the tool catalog and decides in one
step: answer from memory (the STATE block is already in the prompt), do the math itself, call `web_search`, or
escalate.

**Three search modalities, kept distinct:**
1. **Direct datum + SYNTHESIS** (`web_search`, this module) — "who won?", weather, a price, a forecast. The
   FlashBrain resolves it **in the same turn** (~1-2s, no card, no browser). The bug that motivated this: a football
   score fell through to `automate_web` → the heavy browser hung on "Pensando…" for something a snippet answers.
2. **Navigating a site / marketplace** (Amazon, Wallapop…) — NOT this: there's no search endpoint that returns that
   datum, you must ENTER and browse. That is the **navegador** (`widgets/navegador/`, `automate_web`, SlowBrain).
3. **Deep research / report** (a study needing many current data points) — the **SlowBrain** CodeAgent with native
   `WebSearch`/`WebFetch` (Claude Code, enabled in `dispatch._tools_for`) and/or this primitive in a loop; synthesis
   happens inside the agent as it writes the report.

**Layered provider — QUALITY first, cost second, auto-upgrade by key** (`websearch.provider()`):
- **AI-answer** (already synthesized + cited): **Perplexity Sonar** → **Tavily** (if `PERPLEXITY_API_KEY` /
  `TAVILY_API_KEY`). The answer arrives prepared; the brain only adapts it to voice/language.
- **Snippets**: **Brave Search API** (`BRAVE_SEARCH_KEY`) → **DuckDuckGo HTML** (in-process `httpx`, **no key, always
  available**). The brain synthesizes the spoken answer from snippets.
- `WEBSEARCH_PROVIDER` forces one. With **no keys at all it works free** on DuckDuckGo. Credentials live in
  `.meshkore/credentials/zaelar.env` (the store wins over `.env`; set from the wizard/UI, §5 credential seam).

**Latency & cost**: the search is blocking network I/O → run under `asyncio.to_thread` (keeps the V2-011 invariant).
The answer is shaped to voice/language by the **model the turn already pays for** (2nd FastClient pass — if the source
is an AI-answer provider it only rephrases; if snippets, it synthesizes) → ≈0 marginal LLM cost, no mandatory paid MCP.
Fail-open: providers degrade down the chain; if all fail the brain says so — never crashes, never blocks the voice.

**Routing** is enforced in code (`router.TOOLS` + `prompt._FAST_RULES`), not just prose: factual datum → `web_search`;
a web TASK → escalate to the navegador. Observability: `search` events on `/debug` (provider + ai flag + count + ms).

## 5c. RAILS — common behaviors, deterministically CONDUCTED (V2-042)

A **RAIL** is a recurring behavior we know how to drive a fixed way — fuzzy music, video, data studies, deep
site searches, messaging, agenda, recursive (cron+search) watches. The FlashBrain stays **non-reasoning**: it only
fires a tool; the rail *conducts* in code. Each rail has four modular pieces:

1. **A deterministic resolve→validate→act chain IN CODE** (e.g. `nucleo/flash/music_flow.py`). Any 2nd model pass
   (extract/validate) reuses the model the turn already pays for (the `web_search` pattern) — no extra reasoner.
2. **A tool** in `router.TOOLS` (the "when yes/no" lives in the tool description, not prose — V2-035).
3. **Live RUNS in state** (`nucleo/rails.py` → `state.rails` → rendered "Rails en curso" in the composed STATE, so
   both brains see what's being searched / playing / running). A run is a singleton per `kind`; a FAILED run is kept
   **ISOLATED as `sin_resolver`** (label + attempts + TTL) so the *next* turn can resume it when the operator adds a
   clue ("era de Sinatra"). Transitions emit `rail` events on `/debug`; `reset_all` clears runs (`rails.clear_all`).
4. **Typed memory writeback** (`memory.ingest_message(source=<rail>)`) → history + tastes readable via
   `recent_by_source(<rail>)`.

Per-rail prompt guidance is injected **only while a run is live** (`nucleo/rails.prompt_lines` →
`nucleo/flash/prompt._rails_directive`) — zero prompt cost at rest (same situational discipline as the contextual
tools). The first rail is fuzzy music (§5d). **The widget circuit (§4) is the FOUNDING rail**: its V2-017/025/026
machinery already implements the four pieces with its own channels, and it is really three separated conductions —
operate DATA (`widget_data`→`apply_action`), create/modify CODE (escalate), canvas open/close/delete (tags). The
unification is taxonomic, not a rewrite. Full pattern + domain map: `roadmap/initiatives/V2-042-rails-*.md`.

## 5d. Music — a provider-agnostic capability (V2-041)

Playing music by voice is a first-class capability behind an agnostic seam, so a future music widget (a SEPARATE
piece) can drive **any** streaming connector:

- **The seam** (`connectors/music/`): `base.py` = the `MusicProvider` contract + `Track`/`NowPlaying`/`MusicResult`;
  `registry.py` = a lazy registry (`active()` picks the first connected, preferring the richer provider);
  `__init__.py` = the facade `control(action, query)` used by the FlashBrain tool `play_music`.
- **Spotify** (`connectors/spotify/`): Web API client (search + `/me/player/*` with NO_ACTIVE_DEVICE recovery) +
  OAuth 2.0 Authorization Code + PKCE (`auth.py`; client_id via the credential store, tokens in
  `.meshkore/credentials/spotify.json`; one-click connect when `SPOTIFY_DEFAULT_CLIENT_ID` is set — a PKCE client_id
  is not a secret). Playback control needs **Premium + an active device**. OAuth callback served by `/api/spotify/*`.
- **YouTube-audio** (`connectors/music/youtube_audio.py`): the FREE, no-login fallback — resolves a song to a
  `videoId` (YouTube Data API if `YOUTUBE_API_KEY`, else a stdlib scrape) and plays **only its audio, hidden, inside
  the `musica` widget**. Always available, so "pon música" always plays something. This is NOT the `youtube` video
  widget — music vs video, kept separate.

Music is the first non-widget **rail** (§5c): `nucleo/flash/music_flow.py` drives fuzzy requests
(direct try → websearch on the warm Chromium → extract `Artist - Title` with the turn's model → retry → announce
what plays), keeps its run in `state.rails`, and writes each play back to memory (`ingest_message(source="music")`)
so tastes accrue. All I/O is off the event loop (`asyncio.to_thread`, V2-011).

## 5e. «Sistema arena» — BRAIN RULES, USER RULES, and the auto-generation path (V2-046, DESIGN)

Long-term vision (operator, 2026-07-16): capabilities should not require a developer to hardcode a tool + rail per
use case (the trigger was `play_video`, V2-045) — a user-invented use case should become a **widget + its rail +
its rules, generated on the fly**. The honest mapping (full analysis + 3-bucket plan in
`roadmap/initiatives/V2-046-sistema-arena.md`) is that this is already half-built: the widget generator (§5)
creates code+storage+declared actions+usage on demand; rails (§5c) are the pattern to make declarable; the brief
is data-driven. Two named first-class concepts come out of it:

- **BRAIN RULES** = the hardcoded primal genetics every agent is born with: the language lock + operating layer
  (`nucleo/flash/prompt.py`), the per-tool "when yes/no" in `router.TOOLS` descriptions (§8), and the
  deterministic invariant guards (`hard_interrupt`, `looks_like_*`, memory precision gates, `danger.py`).
  Versioned with the code; never edited by use.
- **USER RULES** = per-user behaviour rules that live in the **STATE** (`state.rules`, born empty), recognized by
  the FlashBrain via the existing `set_style_directive` tool-calling seam and rendered by `compose_state` — always
  in the prompt at µs cost, persisting across sessions (the session directive stays as the immediate layer).
  Planned as the AHORA step of V2-046 (pending operator OK; not yet implemented).

**Native tool vs widget+rail — canonical criteria:** a capability earns a native §8 tool only if it is (a) an
instinct every user wants from day 0 AND (b) needs tool-vs-tool discrimination in the turn (prose provably fails
on the non-reasoner — the V2-045 lesson) or (c) crosses subsystems. Everything else = widget + declared data-ops
(+ a manifest-declared rail, a V2-046 DESPUÉS step). **Transmissible genetics between networked agents** stays a
documented placeholder: artifacts only (widgets/rail declarations — never user rules/state/memory/credentials),
consented known peers only, imported as `trust=untrusted` through the generator's validation gate.

## 5f. «Susurro» — conversational self-audit & continuous improvement (V2-053, F1 BUILT 2026-07-17)

The non-reasoning FlashBrain misroutes; the test→fix loop patches it case-by-case and does not generalize (81
fix commits in 5 days, ~55% routing class). The missing piece is an INTERNAL AUDITOR: `nucleo/susurro/`, a
powerful model (config `§susurro`, UI-managed; OFF the voice path, so a reasoner is allowed here) that audits a
conversation stretch when FRICTION is detected and returns corrections from a CLOSED catalog.

- **Plugged in ONLY via the bus** (modularity doc `zaelar-modularity.md`): the semantic topic
  **`turn.completed`** — emitted by `observer.turn_detail`, the single point both the voice provider and the
  probe already close every turn through — plus existing friction signals (`alert` degraded turn, `rail` fail,
  `worker.stuck`/`budget_kill`). Zero imports of the voice provider. Mounted in the server lifespan behind a
  first-class kill-switch (`ZAELAR_SUSURRO` env + `susurro.enabled` in the ⚙ area).
- **Friction detector** (`friction.py`): deterministic es/en — operator complaint/correction ("te he dicho…",
  "no era eso"), repeated request (Jaccard vs recent user turns, shared `dialog.similar` seam), plus the system
  signals above. Precision over recall; an optional pulse (`pulse_turns`) audits every N turns.
- **Audit window** (`window.py`): verbatim conversation (`memory.recent_window`) + per-turn decisions (from
  `turn.completed`) + filtered event ring + compact STATE — ~2-4k tokens. Operator content only; `untrusted`
  cluster content NEVER enters (anti prompt-injection).
- **Closed catalog** (`catalog.py`): F1 applies `repair_say` (a short natural repair line → `brain_notes`
  [SISTEMA], spoken next turn — the probe now drains notes too, so it's testable headless) and `finding`
  (→ `.meshkore/logs/susurro/findings.jsonl`, dedup by area+title, + bus topic `susurro.finding`, consumed by
  the dev test→fix loop). Future-phase types (user_rule / worker_action / state_patch / memory_fix) are accepted
  from the model but DOWNGRADED to findings until their gated appliers ship (F2/F3, initiative V2-053).
- **Total observability** (operator rule): events kind `susurro` — trigger (reason+signals), **request (the
  exact payload SENT to the LLM)**, **response (raw)**, apply (per correction, with BEFORE/AFTER), done
  (assessment + types + ms) — all trace-stamped (span `susurro`), on the timeline + /debug + durable bus log.
- **Hard invariant:** the Susurro NEVER modifies BRAIN RULES / the system prompt at runtime (no fixed point if
  corrupted). Improvement runs at two speeds: runtime corrections on the MUTABLE layer; findings change the
  genetics via development (git + tests + alignment review).
- Measured e2e (probe suite `tests/agent_headless/e2e/susurro/run_probe_suite.py`, longitudinal `history.jsonl`): complaint →
  correct diagnosis → natural spoken repair + P1 finding, full cycle ~2.5-2.9s with gpt-4.1-mini.

## 5g. «Homeostasis» — the autonomic / health-supervisor layer (V2-070)

zaelar emulates a human at **THREE levels, only two of which "think":**

- **Mente = FlashBrain** (`nucleo/flash/`) — the mind: conducts the conversation, uses a model (§6).
- **Conciencia = Susurro** (`nucleo/susurro/`) — the conscience: audits the conversation, uses a model (§5f).
- **Autónomo = Homeostasis** (`nucleo/homeostasis.py`) — the autonomic nervous system: keeps the **MACHINE**
  healthy, **NO model, fully deterministic**. It thinks about nothing; it watches vitals and heals.

Homeostasis lives **BESIDE the brain, never inside it** — it is off the voice loop, started in the server lifespan
with `start(app)` / `stop()` exactly like the other supervisors (messaging, widgets), and it is **fail-open** (its
own failure can never touch voice/chat). It exists because of a real incident: **2026-07-25 the embedded LiveKit
worker degraded after ~7h → chat/voice stopped responding, and nothing self-healed until a manual restart.**

**Binary rule.** Each watched resource has exactly **two states — healthy or degraded**; degraded → heal. No
gradations, no scoring, no model in the loop. **THREE checks:**

1. **LiveKit engine** — the degradation the incident exposed. Homeostasis detects it **IN-PROCESS** via a
   `logging.Handler` attached to the `livekit` logger, watching for the markers `wait_pc_connection timed out` /
   `entrypoint did not exit`. When it is **SAFE to act** (voice OFF **and** the channel idle ≥120s) it **RECYCLES
   the embedded worker** — `aclose()` + `make_server()` + a fresh task, **no process restart** — with a cooldown
   between recycles. When it is NOT safe, it **ALERTS the operator once** and touches nothing (never yanks a live
   voice turn out from under the operator).
2. **LOGS** — rotates `timeline-latest.jsonl` / `meshkore.jsonl` by **rename** when either exceeds a size cap (both
   files are opened `"a"` on every write, so the next append recreates the file — no fd juggling), and prunes old
   archives.
3. **CAPSULES** — evicts concluded + old per-peer capsules and caps the total (the `sys_kv` `capsule:*` rows, via
   the new facade `memory.kv_keys(prefix)` / `memory.kv_del(key)`).

**Invariants.** Off the voice loop; deterministic (no model, ever); fail-open; heals the machine ONLY when safe
(never interrupts a live voice turn); one recycle per cooldown. **Kill-switch:** env `ZAELAR_HOMEOSTASIS`.
**Observability:** it emits observer events of kind `homeostasis` (labels: `start` / `degraded` / `recycle` /
`rotate` / `evict` / `alert`) — see `zaelar-observability.md`. **Tests:** `tests/infrastructure/unit/core/test_homeostasis.py` (13
deterministic tests; domain 9 of the test map). Full initiative:
`.meshkore/roadmap/initiatives/V2-070-homeostasis-anti-degeneracion.md`.

## 6. The brain seams (model routing, why they matter)

The brain (`nucleo/`) is zaelar's own, but its MODELS are pluggable behind a thin contract — nothing model-specific
is woven through voice/widgets/frontend:
- **FlashBrain model** = the fast voice-turn model, chosen **per invocation** from `config/v2.py` `fast` section
  (`FAST_PROVIDER`/`FAST_MODEL`/`FAST_BASE_URL`/`FAST_API_KEY`): a local Ollama model or a cloud model. The api-key is
  resolved **by endpoint** in `fast_client.py` (x.ai→`XAI_API_KEY`, groq.com→`GROQ_API_KEY`, aimlapi→`AIMLAPI_KEY`,
  gemini→`GEMINI_API_KEY`), so switching provider only needs the matching key in the credential store. **Production
  since 2026-07-15 = `grok-4.20-0309-non-reasoning` via xAI direct** (`api.x.ai`); Haiku/AIMLAPI and Groq are
  alternatives. NEVER a reasoning model, NEVER local on the voice path (local qwen ≈19 s/turn under GPU contention).
- **Worker tier** (a.k.a. "SlowBrain" in older docs) = the async agent tier, configured in `config/v2.py`
  `code_agent` section (`CODE_AGENT_*`, Claude Code / Codex behind the `CodeAgent` interface in `nucleo/agentes/`).
  **V2-036: there is no separate reasoning brain anymore** — escalating LAUNCHES a headless worker that drives the
  task; the FlashBrain is the sole orchestrator. The tool that triggers this is `escalate_to_slowbrain` (legacy
  name) — see the **canonical tool catalog in §8**.
- `active_brain()` (`config/v2.py`, env-first `BRAIN`, default `nucleo`) selects the brain; `BRAIN=direct`/`local`
  are plain-model baselines.
Everything else — the tag vocabulary (§2), the widget contract (§3), the circuit (§4), and the compute layer (§5)
— is brain-agnostic and stays.

**Hard constraint on the FlashBrain (voice) model: it MUST be non-reasoning.** A reasoning model on the real-time
path adds seconds of thinking latency (5s+ TTFT) and, in the old ACP brain, never closed its turn → zaelar went
silent. A non-reasoner answers in ~1s. Reasoning belongs OFF the critical path — that is exactly what the SlowBrain
does in the background. Model routing changes apply on the next voice reconnect (`config/v2.py` is read after
`config.settings.load_into_env()`).

## 7. Files map (the pieces)  ·  (see zaelar-modules.md for the full layout)
- Voice core: `voice/engine/` (LiveKit AgentSession, providers), `voice/tag_protocol.py`, `voice/observer.py`, `server/` (entry: `server/__main__.py`, `python -m server`).
- Brain: `nucleo/flash/` (FlashBrain) + `nucleo/websearch.py` (shared web search, §5b) + `nucleo/rails.py` + `nucleo/flash/music_flow.py` (RAILS, §5c) + `nucleo/dispatch.py`/`nucleo/memory_agent.py`/`nucleo/agentes/` (SlowBrain, web search via native `WebSearch`/`WebFetch`) + `nucleo/loop.py`/`nucleo/scheduler.py`/`nucleo/cron_api.py`/`nucleo/sparks.py`; provider `voice/engine/llm/providers/nucleo.py`. Memory: `memory/` (SQLite). Bus: `bus/`.
- Widget circuit: `widgets/{runtime,server_api,brief,generator}.py`, `widgets/<id>/` (data.py + widget.js), `frontend/app/widgets/desktop.js`.
- Music (§5d): `connectors/music/` (agnostic seam) + `connectors/spotify/` (Web API + OAuth PKCE) + `connectors/music/youtube_audio.py` (free fallback) + `widgets/musica/` (surface) + `server/spotify_api.py` (`/api/spotify/*` + `/api/music/state`).
- Front: `frontend/` — ES-module app (`app/core` reactive store, `app/services` WebRTC/audio/VAD/STT/SSE engine, `app/components`, SSE + voice-command fast-path). `index.html` is a thin bootstrap. Solid-migration-ready.
- Autonomic health (§5g): `nucleo/homeostasis.py` (the health supervisor — LiveKit engine recycle + log rotation + capsule eviction; no model, deterministic; `start(app)`/`stop()` in the lifespan) + `tests/infrastructure/unit/core/test_homeostasis.py`.
- Self-test: `tests/voice/e2e/mic/mic_selftest.py` (headless: injects speech, checks the server pipeline).
- Runtime config: `config/settings.py` (GET/POST `/api/settings`) → `config/settings.json` (⚙ panel: STT/TTS/voice/language); `config/v2.py` = model routing (fast + code_agent) + `active_brain()`. Both gitignored where they persist state.

## 8. FlashBrain tool catalog — CANONICAL (V2-035, 2026-07-14)

**This is the single source of truth for the FlashBrain's function-calling catalog** (`nucleo/flash/router.py::TOOLS`).
The FlashBrain decides every turn **by function-calling** (§5b): it gets the composed STATE + the tool catalog and
picks one action. The `/architecture` page (FlashBrain tab) mirrors this list. Every tool must be **justified and
fit the V2-036 flow** — no dead/stale entries.

> **Naming note (important):** `escalate_to_slowbrain` is **legacy**. In V2-004 the "SlowBrain" was a separate
> reasoning brain; in **V2-036 that brain was DISSOLVED**. Escalating today = `nucleo/dispatch.py` **launches a
> headless worker** (a Claude Code agent, or whatever headless `CodeAgent` is configured) that drives the task with
> its own intelligence (memory/tools/browser). The function name is kept as a stable model-facing contract; its
> **description reflects the real mechanism** (it no longer says "slow brain"). Renaming would touch 6 files + the
> model's learned behavior + tests, so it stays until a deliberate rename task.

| Tool | What it does | Flow route | When offered |
|---|---|---|---|
| `escalate_to_slowbrain` | **Launch a Brain Worker** → `dispatch.py` starts a LIVE, interactive worker session (`nucleo/workers/`, agent-agnostic) that drives it async (memory, code, browser, reasoning). Injectable/killable; result returns by voice+UI. **V2-061 boundary:** managing a widget's LOCAL list (add/mark/drop a note/task/reminder that lives only there) = `widget_data`; but EXECUTING/UNDOING a REAL-WORLD commitment (cancel/change a booking or appointment, unsubscribe, place/cancel an order, pay) = escalate — it must happen in reality (the site/service), the widget is only its MIRROR (updated after by the worker via `hbwidget`). If unsure, escalate. | → `nucleo/dispatch.py` → `WorkerSession` | always |
| `web_search` | One factual, time-changing datum answered **in the turn** (~1-2s, no card/browser). ONLY gets a datum to say — DOING something on a site (book/appointment, fill/submit a form, transact, buy) or "do it / book it for me" → `escalate` (drive the browser and complete), never advice. | → `nucleo/websearch.py` (§5b) | always |
| `recall` | **V2-056** · Query the operator's DURABLE long-term memory (tastes, family, plans, budgets, things said days/weeks ago) when the turn needs it and it is NOT already in the STATE/recent conversation — e.g. about to plan/organize/book something ("quiero irme de vacaciones", "organízame el finde"). The V2-022 principle ("the MODEL decides to search") applied to memory: the `needs_recall` heuristic stays as optimistic PREFETCH; this tool covers what it misses. Lightweight sibling of `web_search` (`compose_recall` off-loop + 2nd pass with the turn's model — memories return IN the turn, no card/worker). NOT for world data (`web_search`), NOT for what's already visible in STATE/conversation. Never says "memory"/"database" out loud. | → `prompt.compose_recall` → `memory.query()` (off-loop) | always |
| `reveal_secret` | **V2-060** · Retrieve an ENCRYPTED operator secret (password/IBAN/crypto account/wallet key). The model only IDENTIFIES which one (`vault_flow.py`, fuzzy match); the **value is delivered OUT-OF-BAND** — it NEVER enters the model prompt nor the observer/logs. Vault locked → asks for the passphrase/passkey (opens the native modal); no vault → offers to create it; comfort mode (default) says it by voice, hard rule `secrets_voice=False` → screen-only. NOT web_search (world data), NOT recall (that's plaintext durable memory). | → `nucleo/flash/vault_flow.py` → `memory/vault.py` → `/api/vault/reveal` (loopback) | always |
| `play_music` | **V2-041/042** · Play/control MUSIC ("pon música", "ponme a X", "sube la música", "siguiente", "pausa"). The **music rail** (§5c/§5d) resolves fuzzy requests in the turn (off-loop); always plays something (free YouTube-audio fallback if no Spotify). NOT web_search, NOT the `youtube` video widget. | → `nucleo/flash/music_flow` → `connectors/music` facade → `MusicProvider` (Spotify \| YouTube-audio) | always |
| `play_video` | **V2-045** · Play a VIDEO in the `youtube` widget (SEE on screen): "pon el vídeo de…", "ponme un vídeo/tráiler/peli de…", "reproduce en youtube…", "quiero ver…". Sibling of `play_music` (SEE vs HEAR) — a **first-class tool** because the non-reasoner conflated video with music via prose alone; tool-vs-tool discriminates cleanly (no verb tables). Provider emits `[[show:youtube]]` + data-op `load(query)`. NOT play_music (audio), NOT web_search. | → provider → `youtube` widget `load` | always |
| `show_widget` | **2026-07-17 · V2-082** · SHOW/open/play a widget on the canvas, incl. GAMES: "abre el reloj", "muéstrame X", "juega al snake". A **first-class tool** (sibling of `play_video`) because a text tag `[[show]]` loses to a function-calling tool when the word collides ("jugar"≈play → play_music/video hijacked it). Provider+probe converge on `[[show:id]]`; id resolved by **NOMBRE/ALIAS with CERTAINTY** via `runtime.identify` (V2-082: only name/alias open, description never does; the word "widget" scopes to user widgets; a SYSTEM surface named → routes there, not a widget; NO match → **ASK, never fabricate a widget** — the old "escalate as possible CREATE" is gone). NOT play_music/play_video (playing≠showing), NOT widget_data (data). | → provider `_tag_emit("show", id)` / clarify if unknown | when widgets exist |
| `manage_widget_alias` | **V2-082** · ADD/REMOVE a NAME/ALIAS a widget answers to ("añade el alias WhatsApp al widget de mensajería", "quítale el apodo X"). SURGICAL manifest write (`widgets/aliases.py`), NOT regenerate the widget (not escalate) NOR change its data (not widget_data). Collision-guarded (an alias belongs to ONE piece — widget or system surface; rejects otherwise); the canonical name can't be removed. `op`='add' (default) \| 'remove'. Provider writes off-loop + emits SSE `widget/alias`; probe classifies only. | → `widgets/aliases.add/remove` + SSE | when widgets exist |
| `widget_data` | Run ONE declared action of a widget to change its **data** (add meeting, mark task…). NOT create/modify code, NOT show/close. **V2-061 caveat:** if the item MIRRORS a real-world commitment (a booking/appointment made somewhere, a subscription, an order) and the operator wants to CANCEL/change it, the real action goes to its source → `escalate`; this widget is only the mirror. A bare-pronoun item ("cancélalo") on a widget that is neither open nor named is a mis-route (guard `router.looks_like_bare_ref` → escalate with context). | → `widgets` `apply_action` (FAST/CONFIRM gate) | when widgets exist |
| `reply_message` | **V2-051** · Reply/answer a message in the operator's unified inbox (`mensajeria`; EMAIL today, WhatsApp/Telegram to inherit). Converges on the `reply` data-op (`confirm:true`) → the **CONFIRM gate reads the draft back and asks OK before SENDING** (not undoable). NOT for initiating a message to someone who hasn't written (contacts subsystem, V2-052); only replying to something in the inbox. | → provider → `mensajeria` `reply` → `pending_reply` → bus `msg.reply` → connector SMTP | when messaging has items |
| `delete_widget` | Delete a widget **for good** (opens a confirm; ≠ close). Deterministic, not escalated. | → `widgets/lifecycle` + confirm | when widgets exist |
| `set_style_directive` | **V2-046 A1** · The operator gives a BEHAVIOUR RULE ("be more direct", "yes/no answers only"). Applies NOW (session directive, immediate layer) **and PERSISTS as a USER RULE** (`state.rules` via `memory.add_user_rule`, off-loop; rendered every prompt in `compose_state §B` "REGLAS DEL OPERADOR"). Removing = same tool + deterministic guard `looks_like_rule_removal` ("olvida esa regla") → fuzzy `remove_user_rule`. No more "escalate a worker to save it". | → `brain._directive` + `memory.add/remove_user_rule` | always |
| `authenticate_web` | Open the browser to **log in** to a site, ONLY when login is the sole goal (a task verb → escalate instead). | → navegador auth | always |
| `confirm_widget_delete` | Resolve a **pending** delete confirmation (yes/no). | → `widgets/confirm` | **only if a delete-confirm is pending** |
| `login_done` | Operator says they finished logging in → close window, resume task. | → navegador auth | **only if a login is in progress** |
| `connect_cluster` | **V2-064 · rediseñada V2-086** · Connect to a MeshKore cluster — PRIVATE (`cluster_id`+`token`) or **PUBLIC/tokenless** (`cluster_id`+`vis:"public"`, e.g. MeshKore Commons). **Never connects directly** — opens a deterministic Sí/No confirm (`widgets/confirm.py`) showing the real cluster_id, now on the NATIVE «Clusters» tab. A text-only guard in the description was NOT enough (a pasted block merely MENTIONING a cluster_id made the model call it), and that confirm — not the old widget gate — is the actual protection. Only a "sí" resolves to `meshkore.dispatch_tag("cluster.connect", …)`. | → `widgets/confirm` → (on yes) `connectors.meshkore.dispatch_tag` | always |
| `cluster_send` | **V2-086** · Send a message to a cluster you're ALREADY connected to ("dile a zalo que…", "pregunta en el cluster"). Sent instantly, no confirm (it's ordinary communication the operator just asked for). Replaces the old `widget_data(cluster-registro, send)` route, gone with the widget; the `[[cluster.send]]` tag can't serve as the primary path because its protocol lives in the MeshKore brief, which is OUTSIDE the FlashBrain's hot prompt. | → `meshkore.dispatch_tag("cluster.send:<name>")` (inherits the outbound secret guard + journal) | **only with a cluster connected** |
| `send_to_worker` | **V2-038** · Inject a refinement into a **live** Brain Worker ("además, verde") — do NOT open another. | → `dispatch.inject_soon` (piggyback queue) | **only if workers are live** |
| `stop_worker` | **V2-038** · **Kill** a live Brain Worker ("para eso"). ≠ close/delete a widget. | → `dispatch.cancel_soon` (killpg) | **only if workers are live** |
| `answer_worker` | **V2-038** · Answer a Brain Worker that is **waiting** on the operator. | → `worker_api.answer_active_soon` | **only if a worker ask is pending** |

> **Brain Workers (V2-038):** the worker tier is now LIVE interactive sessions (`nucleo/workers/`, agent-agnostic
> backend: Claude Code stream-json today, Codex/Cursor/Hermes tomorrow). Three channels: ↓ inject (`send_to_worker` →
> piggyback queue), ↑ report-to-state (phase auto-derived + `hbnote`), ↑ ask/act with response (`hbask`/`hbact` →
> `/api/worker/act`, policy ALLOW/CONFIRM/DENY, the FlashBrain lends its tools e.g. `web_search`). The RAM session
> registry in `dispatch.py` is the source of truth; the loop supervises (stuck/timeout/relay asks). Full design:
> `.meshkore/roadmap/initiatives/V2-038-brain-workers-interactivos.md`.
>
> **Worker→widget bridge (`hbwidget`, V2-061):** `nucleo/widget_cli.py` lets a worker `read`/`data`/`show`/`close` a
> canvas widget — the `widget_data` action of `/api/worker/act` applies the data-op via `widgets.brain_action` under
> the SAME canonical FAST/CONFIRM gate the FlashBrain uses (ESCALATE/undeclared → DENY: a worker never escalates a
> data-op nor invents an action; it reads the widget first), provenance stamped `worker:<id>`. This closes the chained
> action loop: after acting in reality the worker REFLECTS the change in the widget (e.g. removes the now-cancelled
> appointment from the agenda) and verifies — `dispatch._METHOD_BLOCK` drives it.

**Canvas tags + `show_widget`.** Hide/move a widget = text tags `[[close]]` / `[[move:…]]` (processed by
`frontend.py` + `voice.tag_protocol`). SHOW is available BOTH as the tag `[[show:ID]]` AND (since 2026-07-17) the
first-class tool `show_widget` — the tool is the reliable primary path (function-calling beats a text tag when the
verb collides with play_music/play_video), the tag is the reserve; both converge on `desktop.show(id)`. Changing a
widget's DATA is never a canvas action — that's `widget_data`. This boundary is enforced in the prompt and the tool
descriptions because a small model kept confusing them.

**Widget NAMES + ALIASES — resolución con CERTEZA (V2-082, 2026-08-01).** Cada pieza tiene un NOMBRE canónico +
una lista de ALIAS y se resuelve SOLO por ellos (`runtime.identify` reescrito): la `description`/`whenToUse` ya NO
abre nada (fin del "abrió por parecido temático"), la palabra "widget" acota a widgets de usuario, las SUPERFICIES
DE SISTEMA (chat/config/debug… en `widgets/system_surfaces.py`, espejo del front `system-surfaces.js`) viven en el
mismo espacio de nombres pero jamás se devuelven como widget, y sin match de nombre/alias se PREGUNTA (nunca se abre
el más parecido ni se fabrica un widget). Alias de widget EDITABLES por voz/texto (`manage_widget_alias` + REST
`/widgets/{id}/aliases`); alias de sistema FIJOS. Registro unificado `widgets/registry.py` (`GET /widgets/registry`,
proyectado a `state.widget_registry` para visibilidad). Concepto sin mezclar: WIDGET (catálogo, alias editables) ·
SUPERFICIE DE SISTEMA (nativa, alias fijos) · TOOL (este §8) · ACCIÓN/data-op (≡"skill", `manifest.actions`) ·
EMBEDDING (solo memoria). Plan: `.meshkore/docs/architecture/zaelar-widget-naming-v2082.md`.

**Contextual tool set (V2-035 · extended V2-085):** `router.tools(context)` OMITS situational tools when their state
does not apply (`confirm_widget_delete` without a pending delete, `login_done` without an active login, the widget
tools when no widgets exist) → shorter prompt, less decision noise. The voice turn (`providers/nucleo.py`) and the
probe (`nucleo/flash/probe.py`) build the same context so `make flash` mirrors reality. **Descriptions are
condensed** (V2-035) but keep the routing rules that came from real bugs (reminder-simple = no tool,
no-duplicate-task, no-answer-then-search, login-vs-task); those are marked in `router.py` comments.

**V2-085 adds three CAPABILITY gates** — `reply_message` (a messaging connector is enabled), `reveal_secret` (a
vault exists), `play_video` (the `youtube` widget is in the catalog). All **fail-OPEN**: if the probe raises, the
tool is offered anyway — a monitoring glitch must never silently take a capability away from the operator.

> **Gating invariant (V2-085, hard).** A gate reads **STATE, never the words of the turn.** "Is there a live
> worker?", "is the vault created?", "is the messaging connector connected?" are verifiable, language-agnostic
> facts about the system. "Does the sentence contain *recuérdame*?" would be a keyword table deciding routing —
> exactly what this brain rejects (`feedback_no_hardcoded_understand`; see the module docstring at the top of
> `router.py`). **Who decides intent is the model, by function-calling.** A tool that cannot be switched off by
> state is OFFERED; it is never guessed at.

**Tool families + budget observability (V2-085).** `router.FAMILIES` classifies every tool (core · widgets ·
workers · cluster · messaging · media · web · memory) and `router.tools_report(offered)` returns the per-turn
breakdown (`n_tools_offered`, `sz_tools`, `tool_families`, `tools_omitted`) into `llm_metrics`. **Measured
2026-08-01:** the full catalog is 22 tools / 29,659 chars; the typical gated turn is 15 tools / 22,522 chars; with
no messaging, no vault and no youtube widget, 12 tools / 18,868 chars. Note the catalog is **O(1)** — it does NOT
grow with the widget catalog, so it is a fixed per-turn cost, not the scalability bottleneck (that one is §3b).
`test_router.py::test_tool_catalog_is_constant_sized` pins this: if a tool ever starts enumerating widgets in its
description, the test fails.

> **Change rule:** touching `router.TOOLS` (add/remove/rename a tool, change a description or its gating) MUST update
> **this §8**, the `/architecture` FlashBrain tab, and `test_router.py`, and re-check the contextual gating in
> `providers/nucleo.py` + `probe.py`. See `zaelar-docs-sync.md §Tools`. Sizes are observable per turn (`tools_chars`,
> `n_tools_offered` in the `reply` event / probe).

## 9. Server boot sequence — critical path vs. deferred (V2-065, 2026-07-23)

**Problem measured, not assumed:** the operator reported the first turn after a restart taking >30s to become
usable, with the LiveKit room dropping and reconnecting 2-3 times before settling. Root cause found in
`server/__init__.py::_lifespan`: everything before the generator's `yield` runs **sequentially**, and the app does
not accept **any** HTTP/WS request — including the page load and the voice token endpoint — until `yield` is
reached. The MeshKore cluster autoreconnect loop `await`ed each persisted cluster's WebSocket handshake **inline**,
so a slow or unreachable cluster held the *entire* app hostage for as long as it took (unbounded — a hung TCP
connect can be tens of seconds). Any browser tab left open across the restart would then race a half-up server,
producing the 2-3 reconnect cycles.

**Rule going forward: the lifespan has exactly TWO kinds of startup work, and they must never mix.**
1. **Critical path (`await`ed, sequential, must be FAST)** — only what voice/FlashBrain themselves need to exist:
   the memory queue consumer (`memory.api.start()`, local SQLite, sub-millisecond) and pure in-process wiring with
   zero I/O (`meshkore.init()`, `bridge.start_heartbeat()` — object construction, no network). Nothing that talks
   to a remote endpoint belongs here.
2. **Deferred (`asyncio.create_task(...)`, fire-and-forget, own background task)** — anything that is genuine
   network I/O with unbounded latency: the MeshKore cluster **reconnect** loop, the messaging supervisor's
   WhatsApp/Telegram reconnects (already correctly async — `connectors/messaging/supervisor.py::start()` only
   schedules its `_loop()` task, never awaits a connect inline), widget-generation resume, the FlashBrain/browser
   prewarm, and the **autonomic homeostasis supervisor** (`nucleo/homeostasis.py::start(app)`, §5g — a sibling of
   the messaging and widgets supervisors: `start(app)`/`stop()`, off the voice loop, fail-open, gated by
   `ZAELAR_HOMEOSTASIS`). A strong ref goes on `app.state.<name>_task` so the GC can't drop it (same pattern for all of these).
   The LiveKit `AgentServer` itself (`voice/engine/pipeline/agent.py::make_server`) was ALREADY correctly deferred
   this way — it just sat, in the source, physically *after* the blocking MeshKore loop, so it never got the
   chance to start until that loop finished. Moving a `create_task(...)` call earlier in the function does nothing
   by itself (it doesn't block either way) — the fix is entirely about which operations `await` vs. which ones get
   wrapped in a task, not about reordering fire-and-forget calls.

**Verification method (repeatable, not vibes):** grep `await ` inside `_lifespan` before `yield` — today that list
is exactly `memapi.start()` and nothing else. Confirmed via the boot log timestamps
(`.meshkore/logs/run-*.log`): `LiveKit agent worker started EMBEDDED` now logs essentially immediately after
`Memoria v2 montada`, **concurrently with**, not after, `MeshKore: connecting cluster 'arena'` (which itself still
takes ~2s to complete — that's fine now, because nothing is waiting on it).

**Scales to more connectors:** any FUTURE connector (a new cluster type, a new messaging platform) that reconnects
saved credentials on boot must follow pattern 2 — wrap its reconnect loop in its own `asyncio.create_task`, never
an inline `await` in the shared lifespan. A single slow connector must never be able to delay every other one, let
alone voice itself.

## 10. Testing control plane — terminal and Observatory (V2-077)

Testing is one platform with two clients, not separate terminal and web systems. `python -m tests` resolves the
catalog, executes the declared action and preserves its exit code; `tests/platform/events.py` writes an append-only
JSONL stream; `tests/platform/server.py` projects that same run at `127.0.0.1:8765`. Therefore Codex/Claude Code can
run headlessly with `--no-open` while the operator watches or later replays exactly the same evidence. The
application under test remains a different process at `127.0.0.1:43917` when a live boundary is required.

```text
tests/<suite>/suite.json + run_testmap.py + catalog_provider
                         │
                         ▼
             schema 2 ordered catalog
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
 python -m tests / CI             Observatory UI :8765
          │                             │ launch validated ID
          └──────────────┬──────────────┘
                         ▼
        pytest | headless runner | Playwright | voice runner
                         │
                         ▼
       tests/runs/<run-id>/{run.json,events.jsonl,artifacts/}
```

The server accepts only catalog-owned suite/group/case IDs and rejects a UI handoff while the visible run is still
active. One port represents one run; overlapping test processes are forbidden. Deterministic pass/fail and an LLM
judge score are separate signals. Stateful corpora must declare their causal policy—for example, the six-month
memory timeline uses one isolated DB and replays the complete prefix before an individual step. Operational rules:
`tests/README.md`; diagnosis playbook: `.meshkore/docs/ops/zaelar-testing.md`; machine contract:
`tests/platform/SCHEMA.md`.

**Evidence is complete; the PRESENTATION is summarized (V2-085).** A journey `interaction.output` can carry the
engine's whole response (tens of KB). Dumping it inline meant ONE case filled the screen and hid the rest of the
run — what was lost wasn't the data, it was the view. Worse, `runner.py` printed
`json.dumps(output)[:12000]`: flooding the console AND **truncating** the proof exactly when it was needed most.
Now:

- **Terminal** — on failure, `runner._dump_failure()` writes the FULL output (indented, greppable, diffable) to
  `artifacts/journey-<case>-output.json` and prints size + the verdict fields + the path.
- **Dashboard** — payloads over 400 chars render as a summary (verdict fields + char count) with the complete JSON
  in a collapsed `<details>`; the signals column always summarizes (it's a scanner, one line per event).

Nothing is deleted or capped: the raw stays in the DOM, in `events.jsonl` and in the run's artifacts. It just stops
being the first thing you see.
