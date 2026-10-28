# zaelar — Observability and debugging

> Golden rule: **you do not need to look at the screen to debug zaelar**. EVERYTHING that happens (voice,
> frontend/widgets, the «Colmena» brain, LLM calls and through which API) leaves a trace in a **single event log**.
> This document says where it is and how to read it. Any agent that loads the context should start here to debug.

## The FOUR axes of an event

Every event answers four questions, and each one has its field. Understanding this is understanding the whole system:

| Axis | Field | What it answers | Where it comes from |
|---|---|---|---|
| **WHAT** | `kind` + `label` | what happened | the place that emits it |
| **WHICH PIECE** | `cat` | FlashBrain · Brain Workers · Memory · Widgets · System · Pulse | `observer.py::_CAT` |
| **WHICH FLOW** | `trace` → column `corr_id` | the **correlation id**: everything a stimulus sets off, from start to end | `voice/trace.py` (ContextVar) |
| **WHO and WHEN** | `uid` · `sid` | the installation and the work session | `observability/identity.py` |

**The correlation id is not a separate identifier**: it is the turn's `trace`, promoted from a field inside the JSON
to an indexed column. A second, parallel id would drift from the first at the first cross-loop seam someone forgot
to stitch. Every operator request opens its own flow — even when it corrects an earlier one —; whatever continues a
live flow (a worker delivering, a browser step) inherits its id.

**The family says WHAT happened, not WHO did it.** A memory read is `memory` whether the FlashBrain or a worker did
it; who did it is said by the `span` (`worker:5`, `rail:music`, `web:t2`). To isolate by actor there is the Traces
view (⛓).

## Where it is stored

**Everything on the installation, in one place.** No external service, no separate folder:

- **`memory/_data/zaelar.db`** (SQLite + WAL, the SAME file as memory), table `events`, written by the bus sink
  (`bus/log.py`) — single writer. Besides the full JSON `payload`, it lifts into **indexed columns** what is needed
  for querying: `corr_id · session_id · user_id · cat · kind · label · span · ms · model · tokens_in · tokens_out ·
  ver`. They are added with an idempotent `ALTER TABLE`: a live installation never loses its history to a
  migration, and older rows stay `NULL` because that datum did not exist yet.
- **`.meshkore/logs/timeline-latest.jsonl`** (rolling) and **`.meshkore/logs/sessions/<session_id>.jsonl`** (per
  work session) — the raw dump, for `jq`.

`GET /api/observability/*` reads it: `flows` (a summary per flow: real end-to-end duration, families, actors,
tokens, errors), `flow/{corr_id}` (chronological detail), `sessions`, `catalog` (the map of what can be filtered),
`identity` and `stats` (coverage of the axes themselves). Read-only.

**Identity**: `user_id` is a **random UUID4** generated the first time and stored in `config/identity.json`
(gitignored). Random and non-sequential on purpose — it identifies nobody by itself. It goes into a JSON file and
not into the database because a «wipe memory» reset destroys `zaelar.db`, and losing the identity when clearing
memory would make any longitudinal analysis useless. `session_id` is a UUID4 per **work session**: the frontend
opens it on connect and ⏻ or closing the tab closes it; a reconnection does NOT split it in two. After REAL
inactivity beyond `ZAELAR_SESSION_IDLE_MIN` (default 5 min) it closes by itself (`identity.note_real_activity`) —
but only REAL activity counts for that clock, and only REAL activity can reopen a session that is already closed:
a plumbing event (`cat` `system`/`pulse` — including the close event itself) reopens nothing, so a finished
session never resurrects in the act of closing it.

## The single event bus

**ONE logging system**: everything goes through `voice/observer.py` → `emit(kind, label, text="", role="",
extra={})`, expressed as a subscriber of the in-process bus (`bus/`, topic `observer`; the SSE bridge `bus/sse.py`
serves `GET /events` identically). There is no second logger: the voice engine (`voice/engine/pipeline/agent.py`)
records transcripts, state, VAD/barge-in, metrics and errors by calling `emit()`, just like the brain, the widgets
and the connectors. `voice/engine/pipeline/instrument.py` does **not** log events — it only keeps the startup
handshake (topic `vl2`, for the splash) and an OPTIONAL mic recording. Every event is written to:

| Destination | What it is | How to read it |
|---|---|---|
| **SSE `GET /events`** | live stream (`data: {json}\n\n`) | `curl -N http://localhost:43917/events` · consumed by the frontend AND the tester |
| **`.meshkore/logs/sessions/<session_id>.jsonl`** | per-session trace (append) | `cat` / `jq` the most recent session file |
| **`.meshkore/logs/timeline-latest.jsonl`** | rolling global trace | tail it to see the current turn |
| **`GET /debug`** | live timeline in the browser (in-memory ring) | open it in Chrome while you talk |
| **`.meshkore/logs/voice/<session_id>/mic_raw.wav`** | input audio, **only if `ZAELAR_RECORD_MIC=1`** (default OFF) | play it back to verify STT |

### The viewer (◷): columns, and the filter

**A FIXED column header**: below the filter bars there is a row of labels with **exactly the same grid** as
`.dbg-row` (widths, gap, padding and the 3px left border) → each label sits right above its column without changing
any width. It lives **outside** the scrolling container: it does not scroll, the `MAX_ROWS` trim cannot prune it,
and the list fills exactly from its bottom edge to the bottom of the panel. A label that does not fit is clipped
with `…` and its `title` (hover) explains it. The columns tell a story from left to right — WHEN · which FLOW ·
which PIECE · what TYPE · how long it took · with which model · how many tokens · and what happened —:
**Time · Flow · Family · Type · ms · Engine · Size · Event**. It hides itself in the **Traces** view (a tree, no
columns) and below a 700px panel width, where the container query already collapses rows into free flow.

#### The latest event goes on TOP, and the scroll belongs to the operator

**The list grows by PREPEND**: what just happened enters right under the column header and pushes the rest down.
Looking at the same patch of screen always shows the latest; scrolling down goes back in time. In the **Traces**
view the same rule applies — the most recent flow on top — but **within** each tree events stay in chronological
order: a flow reads from start to finish, which is what lets you see where it went wrong.

Growing from the top means there is no "follow the latest event" state to maintain — no sticky-bottom tracking,
no heuristics to tell the operator's scroll from ours, no indicator for an invisible state — so the surface cannot
misrepresent what you are looking at.

All that remains is **a three-line compensation** (`DebugPanel.prepend()`): if the operator is at the top
(`scrollTop 0`) the row just enters; if they are reading further down, the height that just appeared above is
added, so what is under their eyes does not move by a single pixel. The browser's automatic scroll anchoring is
**disabled** (`overflow-anchor:none` on `.dbg-list`) because it only exists in Chrome/Firefox and its adjustment
would add to ours: one owner, the same behaviour in every browser. Scroll is not touched anywhere else, except when
OPENING the panel (which means «let's see what is happening now» → top).

**The whole filter lives in ONE COLLAPSIBLE panel**: in the header, a **«Filters (N) ▾»** button — N = types
currently checked, so you can tell at a glance whether you are seeing the whole thread or a trimmed one — next to a
half-width search box. **Closed, it leaves nothing on screen**: right below the header come the column labels and
the events. It closes from the same button or from «▴ Collapse» inside the panel. With many families and types,
keeping everything unfolded would eat the screen, which is what the viewer is opened for.

**ONE AXIS: the type.** Inside the panel there is a TABLE with the **complete map of what can be filtered** — one
row per family, all its types to the right — served by `GET /api/observability/catalog`, which derives it from
`observer.py::_CAT`: the SAME source that stamps each event's family, so the frontend does not duplicate the map,
it asks for it. It is painted IN FULL even if a type has never occurred — the operator sees at once what can be
switched on.

- **The family label is its control**: it switches all its types on or off at once. Italic when the family is
  partially on, so a partial filter is not mistaken for the whole family.
- There is deliberately no second filter axis (no separate family chips): with a single axis, `visible(row)` has
  one answer and only one, and nobody has to reason «is this row hidden by the family or by the type?».
- **Defaults**: the working families are on (FlashBrain · Brain Workers · Memory · Widgets), the plumbing ones off
  (System/Code · Pulse) — **except `error` and `alert`, which start on even when their family is off**: an
  invisible error is the worst possible failure mode. The operator can switch them off, but as their decision, not
  by default.
- What is persisted is the set of **switched-off** types (`hb_dbg_kinds_off_v2`), not the switched-on ones: a NEW
  type is born visible instead of disappearing because of an old list in localStorage.

The filter is applied in `visible(row)` and re-evaluated over the WHOLE log on every change (`reflow()`), not only
over what arrives afterwards.

Hidden rows stay in the DOM (switching a chip on brings them back instantly, without reloading) and **none of this
touches what is persisted**: the `.jsonl` files and the SSE keep carrying everything — the filter is for READING.

### The EVIDENCE: what the outside world brought back

A log that records the **question** and the **decision** but not the **proof** tells you the system searched,
never whether it searched WELL. So every point where the outside world enters keeps its evidence — two workers, one
bringing back noise and one bringing back the exact datum, leave different traces:

| Row | What it keeps |
|---|---|
| `search · 🔎 web results` | title + **URL** + a slice of each result's snippet, and the synthesized answer if the provider gave one |
| `task · <place> ↩` | the worker CLI's **`tool_result`** — what the tool answered |
| `navegador · 📋 extracted candidates` | the listings scraped from the page **with their URL**, so you can go back and check price and description |
| `navegador · 🏁 milestone` | the task's milestones (`N found`, `discarded as not matching`), which otherwise only live in the card's EPHEMERAL feed |

The format and **the budget** live in `observability/evidence.py`, and its rules explain the unusual decisions:

- **Trim, don't summarize.** A summary is an interpretation; an audit needs the text verbatim, even if only its
  beginning. Every trim leaves a visible mark (`…`).
- **Headers before bodies.** Title and URL are never trimmed (they identify the source and let you go back to
  it); the snippet is, and aggressively.
- **A ceiling per event, and `omitted`.** If not everything fits, the first ones go in and the count left out is
  stated. A silent trim is worse than the trim: whoever audits would believe that was all there was.
- **What the model HAD IN FRONT OF IT is never omitted.** The turn's forensic record keeps the system prompt by
  head and tail (`voice/observer._prompt_excerpt`), and the middle is exactly where `widgets/brief` writes «items
  ahora (de lo ABIERTO)» with what is on screen: the numbered band of the open card. That block survives the trim,
  bounded and with its own mark, so the log can always answer whether the model had the list in front of it.
  General rule: **a positional trim assumes the middle is filler**, and in a composed prompt the middle is where
  the state lives.

The same path exists in the **probe** (`nucleo/flash/probe.py`), which is a parallel implementation of the turn:
auditing never depends on which door the sentence came through.

### Reading a whole session, live or finished

Two reads on top of the flow reads:

- **`flows.session(sid)`** → the shape of ONE session (when, how long, how many flows and events, tokens, errors,
  families touched, code version). A session that does not exist returns empty; one that looks real is never
  fabricated.
- **`flows.events(session_id, since_id)`** → the RAW events with their payload intact (that is where the evidence
  lives). `since_id` is a **cursor over `id`, not a time window**: two events in the same millisecond are normal —
  the bus delivers fast — and a time window would duplicate one or swallow one. The same route serves two purposes:
  **following** a live session (asking for whatever comes after the last id seen) and **archiving** it whole by
  paging from 0.

`GET /api/observability/session/{sid}` also marks `live` by comparing with the open session, and returns `flows`
(a number) and `flows_detail` (the list) as SEPARATE fields, so a consumer always gets the same type for each.

### Who may read the CONTENT

In a home installation the port is only reachable from the machine itself. The same code runs in deployments where
the port IS reachable, and there an open route would hand the conversations to anyone who finds the URL. The
guarded-until-configured pattern, the same as the rest of the system:

- **without `ZAELAR_OBS_TOKEN` → loopback only.** A local installation works exactly as expected.
- **with `ZAELAR_OBS_TOKEN` → the `X-Observability-Token` header is required**, wherever the request comes from
  (not even loopback passes without it: otherwise any process on the machine would still have free access to the
  content).
- Fail-closed (with no determinable origin, access is denied) and a **constant-time** comparison, which does not
  leak a token's valid prefix through repeated attempts.

`catalog`, `identity` and `session/start|end` stay OPEN: the user's own interface uses them, which in a remote
deployment is not loopback, and they expose no content.

### Widget action log — tying «wrong widget» to the SENTENCE that asked for it

Every order against the canvas lands in the **Widgets** category, and **every event carries the text of the turn
that originated it**: the row already says order + target + origin + sentence, which is exactly what you need when
the wrong widget opens.

| Row | Where it comes from | What it says |
|---|---|---|
| `widget · show\|close\|move` | `providers/nucleo.py` (tag `[[show]]`/`[[close]]`) | the canvas order + `id` + `src=flash` + **the sentence** |
| `widget · data:<action>` | `providers/nucleo.py::_apply_widget_data` | the DATA-OP itself (raise volume, maximize, mark done) with its `mode` (`fast`/`confirm`/`escalate`) + **the sentence** |
| `widget · data` | `widgets/store.py::save()` | the EFFECT (the widget saved). Still marked as noise — it is a consequence, not an order |
| `widget · action` | `widgets/server_api.py` | the operator pressing a button on the card (`src=user`) |
| `widget · show\|close` | `nucleo/worker_api.py` | the same, requested by a Brain Worker (`src=worker:<id>`) |

The trace chip on that same row jumps to the sentence's whole chain.

## Traceability text → action → rail → session → events

Every **stimulus** that enters the system is born with a **trace id** (`T12·9f3a`) and EVERYTHING derived from it is
stamped with that id on every event — the quality question («did this sentence land on the right rail and end in
the set of events it should?») is answered by grouping by `trace`.

- **Origins** (root event `kind="trace"`, `root:true`, `origin`): `turno` (voice + chat, born in
  `providers/nucleo.py::_run` BEFORE the gate — ambient/echo discards are traced too) · `kickoff` · `probe` (the
  probe returns the id in its response) · `cron` (scheduler) · `proactivo` (sparks) · `ui` (manual canvas taps) ·
  `cluster` (peer message).
- **How it travels**: `voice/trace.py` (ContextVar) — free across `create_task`/`to_thread`; explicit seams where the
  context does not cross: the escalation carries the trace in its bus payload → `SessionRecord.trace_id` → the
  worker cycle adopts it (`span=worker:<id>`), the HTTP handlers of the bridge CLIs (hbnote/hbask) resolve the
  session and stamp it, a rail's run keeps its trace (`span=rail:<kind>`), and the browser task registry carries it
  (`span=web:<tid>`). `observer.emit` attaches it by itself (reading the ctxvar costs nanoseconds; the hot path is
  untouched).
- **`span`** = ACTOR (level 2 of the tree): `worker:5` · `rail:music.playing` · `web:t2`.
- **In the viewer** (◷): every row carries a **trace chip** (deterministic colour; click → filters the whole chain),
  and the **⛓** button toggles to the **Traces** view: one tree per trace — the root SENTENCE + everything it
  generated, grouped by actor. `jq` equivalent: `jq 'select(.trace=="T12·9f3a")' timeline-latest.jsonl`.

## A Brain Worker's steps — WHERE it works and WHAT it uses

A worker does not just report generic phases («consulting memory…»). Every `tool_use` in its stream is translated
into a RICH row that says **the PLACE** (badge/category per site) + **the action and its concrete target**:

- **🧠 memory** (`kind=memory`, Memory filter) — `recall «query»` · `save [slot] …`.
- **🧭 browser** (`kind=navegador`, Browser filter) — `navigate → url` · `click [12]` · `type «text»` · `scroll` ·
  `extract`. In addition, after running, the browser itself emits the **RESULT**: `🧭 page` with the `title · url`
  it reached, and `🧭 results` with the number of listings from `extract` (what the command does not say).
- **🌐 web** (`kind=search`) — `web_search «query»` · `fetch url`.
- **✏️ code / 📄 file** (`kind=task`) — `write file` · `read file` · `search pattern`.
- **↩ zaelar** (`kind=task`) — the worker's `ask`/`act`/`say` through the bridges.

And two frame rows: at **birth**, `worker · <backend>` with **model** (chip) + **layer** (chip) → which engine/model
drives it; at the **end**, `fin` with input/output **tokens** (size chip) + **USD cost**. Everything is grouped
under `span=worker:<id>` in the Traces view (⛓) and persisted in the jsonl files. The coarse phase (`rec.phase`) is
kept for the FlashBrain's «PROCESOS DE FONDO» prompt, but does not duplicate the row. Source:
`nucleo/workers/providers/claude.py` (`_tool_step`) + `nucleo/workers/session.py` (`_emit_step`/`_PLACE`) +
`widgets/navegador/act_api.py` (`_emit_nav`).

## Event types (`kind`) — what to watch

- **`susurro`** — the conversational auditor, with **FULL observability by design**: `👂 friction → audit` (reason
  + signals; the «in cooldown» variant marks `skipped`), `📤 request → LLM auditor` (**`extra.request` = the
  COMPLETE payload sent**, messages included), `📥 response ← LLM auditor` (**`extra.raw` = the RAW response** + ms
  + tokens), `🩹 repair_say → brain_notes` / `📌 finding → dev-loop queue` (every correction with its
  **before/after** in `extra`), `✅ audit complete` (assessment + types + total_ms) and `⚠️ … (fail-open)`. All
  stamped with the `trace` of the stimulus that caused the friction (span `susurro`) → the ◷/⛓ viewer shows the
  complaint→audit→repair chain. Findings also live in `.meshkore/logs/susurro/findings.jsonl`. **Associated bus
  topic: `turn.completed`** — the semantic close of EVERY turn (voice AND probe, emitted by `observer.turn_detail`)
  with `{user, decision, tools, window, system_prompt, trace}`; it is the subscription seam for programmatic
  consumers (it depends on `ZAELAR_LOG_PROMPTS=1`, default ON — switching it off leaves the Susurro with only the
  loose signals).
- **`homeostasis`** (`nucleo/homeostasis.py`) — the **autonomous layer** that keeps the MACHINE healthy (no model,
  deterministic; it lives NEXT TO the brain, outside the voice loop, fail-open; gate `ZAELAR_HOMEOSTASIS`). It is
  the source of truth for «why was the engine degraded/recycled?». Labels: **`start`** (supervisor start),
  **`degraded`** (a red vital sign detected — e.g. the LiveKit engine reporting `wait_pc_connection timed out` /
  `entrypoint did not exit`, caught by a `logging.Handler` on the `livekit` logger), **`recycle`** (recycles the
  embedded LiveKit worker — `aclose` + `make_server` + a new task, without restarting the process — ONLY when it is
  safe: voice off + channel idle ≥120 s, with a cooldown), **`rotate`** (rotates
  `timeline-latest.jsonl`/`meshkore.jsonl` by size + prunes old files), **`evict`** (evicts concluded/stale
  capsules, `sys_kv` `capsule:*`) and **`alert`** (a single notice to the operator when it detects degradation but
  it is NOT safe to act). It exists so that a long-running embedded worker that degrades recovers by itself instead
  of leaving voice/chat silent until a manual restart.
- **`actionmap`** (family `flash`) — the deterministic layer in FRONT of the FlashBrain (`nucleo/actionmap/`, doc
  `.meshkore/docs/modules/zaelar-action-map.md`). It answers **which layer resolved this turn**, so the viewer and
  the Susurro never attribute a map-served turn to the model. Labels: **`⚡ action map: direct action (no model)`**
  (a hit — with `action`, `entry`, `source`, `match_ms` and the phrase that produced it), **`🕵️ map candidate…`**
  (the model resolved a turn with a single canvas action, i.e. what the table is MISSING; `known_entry` tells a
  missing entry from one that exists and did not fire), **`🗺️ action map WATCHING`** (`watch.py` subscribed to
  `turn.completed`) and the seeding line, which is an **`alert`** if the pack refused any row. Provenance is a
  FIELD, not an inference: every event stamps `engine: "actionmap"` + `origin: "actionmap"` (a model turn stamps
  `origin: "flash"`), the LAYER column of the viewer reads exactly `engine`, and the match cost is folded into
  `pre_ms` as `amap_ms`. The canvas orders it issues are ordinary `kind="widget"` events with `src="actionmap"`,
  so «did the widget open?» keeps its single source of truth.
- `worker_start` — session start: `profile`, `stt`, **`stt_device`** (metal/cuda/cpu), `llm_provider`, `tts`, `turn`.
- `state` — 5-state machine (idle/listening/thinking/speaking…). Marked as "noise" in `/debug` (collapsible).
- `transcript` (role=user|bot) — what was **said** (the user's STT / the brain's reply). `interim` = live partial,
  **ephemeral** (SSE-only, touches neither disk nor the ring — captions/chat while you talk).
- **`vad`** — voice activity and interruption (barge-in), the source of truth for «why was the speech cut?»:
  "🎤 voz detectada (VAD)", "✂️ barge-in — voz pisa la locución" (`extra.over_agent`), "… fin de voz", "🤫 falsa
  interrupción (ruido)" with **`extra.resumed`** (did LiveKit resume the speech after the noise?), "🔊 voz solapada"
  (`extra.is_interruption`). Barge-in tunable by env: `ZAELAR_MIN_INTERRUPTION_SEC` (default 0.6),
  `ZAELAR_MIN_INTERRUPTION_WORDS`, `ZAELAR_FALSE_INTERRUPTION_TIMEOUT`, `ZAELAR_RESUME_FALSE_INTERRUPTION`.
- **`widget`** — canvas action: `label` = `show` / `close` / `move` / `resize` / `data` / `action` / `delete` /
  `confirm` … with `extra.id`. **This is the source of truth for «did the widget open?»**, independent of whether
  the TTS sounded. **PROVENANCE (`extra.src`) — where the order came from**, to audit the frontend as an independent
  piece: **`flash`** (the FlashBrain in a turn), **`worker:<task_id>`** (a Brain Worker through the bridges /
  browser / code agent), **`user`** (the operator touching the UI: opening/closing/dragging a card or pressing a
  widget button), **`system`** (lifecycle / background / reset / unknown). Every emit stamps the field; for the ONE
  blind spot (the data choke point `widgets/store.py::save()`) the intent registry `widgets/provenance.py`
  (`note`/`who`, TTL) resolves it. `widget` dedup keys on `(kind,label,id,src)` — two different widgets (or the same
  one by flash and by worker) do NOT collapse. **`kind="ui"`** = taps on the orb icons
  (`orb:cron|memory|speaker|captions|attention`) and the TopBar (`topbar:status|docs|debug|theme|settings|reset`),
  with `src="user"` (POST `/api/ui-event`). With this, `/debug` answers «who opened/closed/moved/created this?».
  **`kind="ui"` with `src="frontend"` = CLIENT STATE, not operator activity** — see below.

### CLIENT state: what the frontend knows and the server cannot see

The log carries the operator's **intent** (`orb:power` when pressing ⏻) and also the browser's **reality**: the
client's **transitions** enter through the same channel (`api.uiState(action, {...})` → `POST /api/ui-event`,
`kind="ui"`, `src="frontend"`), so an agent that is down but painted as alive is visible in the log:

| Action | Fields | What it answers |
|---|---|---|
| `agent:state` | `state` ∈ `off\|starting\|live\|stalled` · `prev` | The agent's TRUTH (`store.agentState()`, not `powerOff`, which is the intent). `stalled` with `prev:"live"` = it went down while running; with `prev:"starting"` = it never came up |
| `mic:analyser` | `state` ∈ `open\|closed` · `reason` | Whether the mic is **really** released on stop, not just that the icon turns off |
| `audio:out` | `state` ∈ `attached\|released` | The attach is visible (`🔈 TrackSubscribed`); the **release** is logged too, so a zombie speaker leaves a trace |
| `tab:visibility` | `state` ∈ `hidden\|visible` | `requestAnimationFrame` does NOT run in a background tab, and the visualizer and several guards depend on rAF: it tells «it froze» from «you were in another app» |

### Device health — `🎤 mic health` / `🔈 spk health` (V2-788)

Rows `kind="client"` (POST `/api/client-log`) written by `frontend/app/services/device-health.js` on every
**change**, never periodically. `device` ∈ `mic|spk`; `state` is `problem:<cond>` / `clear:<cond>` for a
condition that turns the orb icon red, or `<key>:<value>` for a report-only fact; `text` carries the detail and
the resulting verdict (`verdict=ok|<reason>`).

| Device | Red conditions | Reported only |
|---|---|---|
| mic | `permission_denied` (permissions API + its `change`, or `NotAllowedError`), `no_device`, `capture_error` (`NotReadableError` — another application holds it), `track_ended`, `track_muted` (the source went silent) | `permission:<state>`, `inputs:<n>`, `device:gone` |
| spk | `blocked` (= `canPlaybackAudio`), `paused`, `element_error`, `track_ended`, `remote_muted` (only while `bot_speech speaking`), `context_interrupted`, `no_output`, `sink_lost`, `silent_while_speaking` (the engine says speaking, the received remote audio carries no energy for 4 s) | `element:playing\|stalled\|waiting`, `context:<state>`, `default_output:<label>`, `recovery:…` |

A deliberate mute hides every condition but `permission_denied`; a stopped session clears the session-scoped
ones. «Engine generated TTS, operator heard nothing» now reads as one of these rows — or, if none appears, as an
output problem past the browser (see the module's limits).

### `🎙️ speaker` — the voice-identification SHADOW

Rows `kind="client"` with label **`🎙️ speaker`**, ONE per speech segment, emitted by the BROWSER
(`frontend/app/lib/speaker-id.js` → `api.clientLog`). They are **pure measurement**: they close no gate, write no
memory and do not touch the prompt. They exist to choose, with the operator's REAL mic and room data, the threshold
the next stage will use. Switch them off with `?nospk=1` or `localStorage.zaelar_spk_shadow=0`.

| Field | What it is |
|---|---|
| `label` | `enroll` · `operator` · `other` · `known:<id>` |
| `op_score` | the coarse VOTE against the operator's profile (only 0, ⅓, ⅔ or 1) |
| `d_mean` / `d_pitch` / `d_centroid` | **continuous** distances in σ (0 = spot on the profile, 1 = one deviation away) |
| `rms_ratio` | loudness relative to enrollment (≪ 1 = far from the mic) |
| `pitch` / `centroid` / `rms` | the raw snapshot, for offline analysis |

There are also three DIAGNOSTIC rows, so that a silent log can be read:
**`🎙️ speaker: armado`** (it started; **if it is MISSING, the browser tab is running old code** — the ES module is
cached per page load, so after touching this you must reload), **`⚠️ speaker: no arrancó`** (it failed to arm) and
**`🎙️ speaker: nivel`** (once, at ~25 s: the peak loudness seen against the segmenter's start threshold — if
`peak_rms` < `start_floor`, no segment can open with that mic and what needs adjusting is the calibration, not the
code).

⚠️ **To set a threshold use `d_mean`, NEVER `op_score`**: the vote is over 3 criteria, so it can only take four
values. It is good for classifying and useless for deciding where to cut. Mechanism detail and its limits:
`.meshkore/docs/modules/zaelar-speaker-identity.md`.

**Usage rule, and it is what keeps them useful: they are STATE events, not activity events.** They are emitted ONLY
on transition and never inside a render loop. Two practical consequences in the code: `agent:state` hangs off a
`createEffect` over a DERIVED signal — which re-runs whenever any of its dependencies changes, sometimes with the
same value — and so it carries a previous-value guard; and `mic:analyser`/`audio:out` live in `services/audio.js`,
the ONLY owner of the analysers, which is the only place where «opened» and «released» are the truth and not the
caller's assumption.

**`stop()` releases the whole audio graph** (`audio.reset(reason)`, which also closes the `AudioContext`), so
«closed» is a real state and not just an icon. It also keeps contexts from accumulating: `initMic` reuses a single
context lifecycle per session, because Chrome caps the number of `AudioContext`s per page and, once exceeded,
`new AudioContext()` throws and the mic meter and the orb stop working for the life of the tab.

The endpoint only forwards the fields on its allow-list (`where`/`state`/`detail`/`prev`/`reason`/`cause` + `id`):
one outside it is dropped **silently** — when instrumenting, add the field to the list or it will look instrumented
and record nothing. And `src` is bounded to `user`/`frontend` — anything else falls back to `user`.

- `brain` — prompts/replies of the «Colmena» brain (FlashBrain), `[SISTEMA]` notes, escalations
  (`escalate_to_slowbrain`).
- **`ambient`** — the ATTENTION gate (`voice/attention.py`): a turn that was NOT addressed to zaelar (no wake word
  and outside the conversation window). `label` = "🙉 ambiente — no dirigido a zaelar" with `extra.mode`
  (`smart`/`wakeword`/`ptt`/`always`) and `extra.reason` (`ambient`); or "✋ interrupción dura atendida"
  (`extra.cmd` = `close`/`stop`) when a hard command skips the gate. **It is the source of truth for «did zaelar
  ignore ambient speech?»**: if in a meeting there are NO `widget`/`brain reply` events but `ambient` ones, the gate
  is doing its job. If you see `widget`/escalations on sentences that were not addressed to zaelar → check
  `ZAELAR_ATTENTION` (set to `always`?) or the window. The event carries no chat role (it does not clutter the
  ChatWall), only `/debug` + SSE `/events`.
- `bot_speech` — orb speaking/idle. `tts` — synthesis. `metric` — RAW metrics from the LiveKit plugin
  (`STTMetrics`, `LLMMetrics ttft/dur`, `TTSMetrics ttfb`, `EOUMetrics`). ⚠️ **`VADMetrics` is NOT logged**: it fires
  ~2/s continuously (more with background noise) and carries no useful latencies → it would flood the stream and do
  synchronous file I/O on the voice thread. `agent.py::_on_metrics` drops every metric without real numbers.
  ⚠️ **`metric` lives in the `system` category, NOT in `main`**: with a **streaming** STT (Deepgram) the metric does
  **not depend on anyone speaking** — the plugin's `PeriodicCollector` emits `STTMetrics: audio=5.00s` **every 5 s
  while the mic is open**, perpetually. The PER-SENTENCE latency, which is signal, already comes out as
  `stt`/`tts`/`brain` with backend, model and text. It is still persisted to the jsonl; it just stays out of the
  viewer's main thread.
  `error` — session errors. `alert` — speakable errors (e.g. "Cerebro rápido caído"). `session` — open/close.
- Connectors: `label` prefixed with `cluster.` / `cron.` / `architect.` / `wa.` (WhatsApp) / (Telegram) = tag
  dispatch.
- **`cluster` · field `pace`** — the **conversation-health criterion** of the agent-to-agent channel (cluster ONLY;
  with the operator the conversation always flows). The judgement is made by `connectors/meshkore/evaluator.py`
  rather than by phrase regexes (a regex adapts to one peer and breaks with the next): an INDEPENDENT model (no
  tools, read-only, safe over untrusted content) returns `health` (`flowing`/`stuck`/`dead_end`/`imbalanced`/
  `off_track`) + `action` (`continue`/`concise`/`hand_back`/`pause`) over the recent window, off the hot path in a
  throttled heartbeat (`MESHKORE_EVAL_SECS`). The `cluster` event carries `extra.pace` with the decision APPLIED by
  the bridge. It is the source of truth for «why did zaelar stop answering this peer / hand the turn back?». Values:
  **`handback`** (we HAND BACK the turn with ONE short message and stop), **`silent`/`pause`** (we stop answering +
  a single notice to the operator), **`waiting`**/**concise** according to the verdict. Determinism is kept only for
  the generic parts (exact dedup, `capsule.near_repeat` as an input signal to the evaluator, not as a verdict).
- **`memory`** — central-memory activity. Two origins:
  1. **Mutations**: the server bridges the bus signal `memory.updated` (every mutation in `memory/api.py::_emit` —
     write/reinforce/pin/link/state/episode/consolidate/query) to the `observer` topic as
     `{kind:"memory", op, ids}` (+ `label=op`). It feeds the viewer's **tinting** and shows up as a row in the ◷
     column.
  2. **Turn reads**: `voice/engine/llm/providers/nucleo.py` emits, after composing the prompt, one row per LAYER
     read: `{kind:"memory", label:"estado|corto|recall", layer:"state|short|slow", text:"request → result",
     mem_ms}`. So ◷ SHOWS which layer was touched, how long it took and what it returned (number of cards/chars).
     DebugPanel column 4 = the layer; latency = `mem_ms`.
  Gated by the `memory_observability` flag (default ON, `config/settings.py`; env `ZAELAR_MEM_OBSERVABILITY`). It
  goes out through SSE `GET /events`; the mutation bridge does NOT go through the `/debug` ring (fine-grained, zero
  noise). **The mutation bridge is COALESCED**: one turn fires several `memory.updated` (conversation buffer + pills
  + reinforce + state) → a **trailing debounce** (400 ms, `ZAELAR_MEM_SSE_COALESCE_MS`) merges them into ONE SSE
  signal with the UNION of affected ids. The viewer stays live (re-fetch with its own debounce) with roughly an
  order of magnitude less SSE traffic.

## The memory viewer (🧠) — watch memory form live

A system view (a full-screen overlay, like `/debug`; NOT a widget) that shows **how zaelar's central memory is
composed in real time** while you talk. It opens from the **🧠 in the orb's bowl**
(`frontend/app/components/MemoryMap.js`). Three **proportional columns**: **STATE 10%** (the `memory/state.py`
stack), **SHORT TERM 20%** (`level=='short'`) and **LONG TERM 70%** (`mid`/`long`, the one that grows); boxes fill
their column's width and reflow. Every memory = a node with ~8px text + **scoring** (importance) + date/time +
metadata (kind, weight, access, pinned), expandable with **zoom (wheel) / pan (drag)**; the `edges` **graph** is
drawn as curves between nodes. **Live tinting** (gated by `memory_observability`, default ON): when a datum is
written the node turns **green** for a few seconds, when overwritten **amber**, and a **query** lights up in
**blue** the pieces it touched — every SSE event carries `op` + affected `ids` (`services/sse.js` →
`store.pushMemPulse`). Source: `GET /api/memory/map` (read-only, `no-cache`) → `{state, layers:{short,long}, edges,
counts}` with all the metadata. It is the source of truth for «what does zaelar remember and how does it score
it?» — it complements `/debug` (which is the flow of events, not the state).

## How to debug a voice problem (recipe)

1. `ls -t .meshkore/logs/sessions/ | head` → the latest session file (or `tail -f .meshkore/logs/timeline-latest.jsonl`).
2. Read it: look at `worker_start` (which STT/TTS/brain?), the `transcript`s (what did it hear/say?), the `metric`s
   with `*Metrics` (where is the latency: STT, LLM ttft, TTS ttfb?), the `error`/`alert`s; and the `vad`s (did a
   noise cut the speech? `resumed`?).
3. The brain does not trigger widgets? Look for `widget` events. If there are NONE despite asking → the brain did
   not emit the tag (model not capable enough, or the prompt) — it is NOT the frontend.
4. zaelar silent? Usually: (a) the FlashBrain gets a 4xx from the fast provider (look in zaelar's log for
   `fast brain error`), (b) Metal TTS hits the mlx-audio shapes bug and the Kokoro-FastAPI fallback is not up.
5. ⚠️ **A widget behaves as if your fix did not exist? Check WHICH FILE IS RUNNING.** `widgets/_user/<id>/` shadows
   `widgets/<id>/` in the catalog, in `identify`, in the `widget.js` that is served and in the **Python imports**
   (`widgets/paths.roots()` puts the generated root first), and it is **gitignored**: a fork leaves `git status`
   clean while what runs is not the repo.
   `ls widgets/_user/` · `./.venv/bin/python -c "import widgets.<id>.data as m; print(m.__file__)"`.
6. **A CLIENT error does not show up where you look for it.** A `widget mount failed` («Failed to fetch dynamically
   imported module») lives in the `client` family, which is noise by default — while the server call that caused
   it may have answered `ok`. If something appeared broken on screen and the server says all went well, filter by
   `client` before doubting it.
7. ⚠️⚠️ **«Cerebro rápido caído» does NOT by itself mean the provider is down.** The engine tells an internal
   exception apart from a provider failure, and they read differently:
   - **row «Motor · fallo interno» in the ◉ panel + alert «Fallo del motor — el modelo no tiene la culpa»**
     → it is OURS. The alert and the row NAME the exception; no ladder is touched and no provider light turns on.
     It is fixed in the code, not by switching models.
   - **«Cerebro rápido caído — turno degradado»** → it is the provider's, and the alert carries `text` with the
     real error and `extra.relayed_from`/`relayed_to` if the fallback was tried within the same turn.
   Hot hand-over only happens in the CONNECTION phase: if the failure arrived mid-stream the turn is dropped on
   purpose (retrying would duplicate what was already spoken).
8. **The panel says WHO is answering, and amber is not red.** The «Cerebro rápido · FlashBrain» and «Memoria ·
   CORAZÓN» boxes name the primary and the fallback on every probe — not only when a light is on: as soon as the
   fallback answers, `fast_client` turns the light off on the first chunk, so the name is what tells you a
   successfully relayed engine is running on its fallback. Amber = working on the fallback; red = nobody answers.
   And the memory row keeps its own `detail` (that is where «el recall no cerró en 0.8s» lives, which is a
   different fact from which model writes).

## The independent tester uses this observability

`tests/voice/e2e/agent/interlocutor/trace.py` **subscribes to `/events`** and captures the trace per scenario; the
**GLM judge** (Z.AI) reads it to verify the OBSERVABLE behaviour (frontend actions + brain), not just the
transcript. Reports go to `tests/voice/e2e/agent/runs/report_*.md` with the frontend actions observed per scenario.

**Model routing**: driving the tester + cheap judging = **DeepSeek**; competent judging/reasoning = **GLM via Z.AI**
(coding plan, Anthropic endpoint `api.z.ai/api/anthropic`, with fallback to DeepSeek). The Gemini free tier is not
used (its daily quota is too low for a battery). Keys in `.env` + `.meshkore/credentials/tester.env` (gitignored).

## Autonomous overnight loop

- `tests/voice/e2e/agent/overnight.sh` — loop: rotates scenarios + creative goals against a live zaelar, writes reports.
- `tests/voice/e2e/agent/guard.sh` — idempotent: brings up zaelar (`make run`, native LiveKit without Docker) and
  the loop if they are down.
- The autonomous loop (`/loop <interval> <prompt>`, skill `loop`) re-invokes the agent to: guard → read the latest
  report → fix the top bug → re-test → document → repeat.

See also: `voice/observer.py`.
