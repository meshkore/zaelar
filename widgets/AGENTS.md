# Widget house style — READ THIS before creating or editing any widget

You are building/editing a widget for **zaelar**, a warm voice-first assistant. The canvas supports BOTH a dark
theme (the default) and a light theme — the user toggles between them live from the toolbar (☾/☀), and a widget
already on screen must re-paint correctly the instant they do, with **zero JS changes**, purely via CSS. Make
widgets feel polished and consistent with the rest. These are HARD rules — follow them every time.

## Visual style (match the existing widgets: `agenda`, `meteo-soria`, `results`)
- **Theme via CSS variables — NEVER hardcode a hex color for anything theme-dependent.** The host page defines
  these custom properties on `:root` (both themes) and every widget inherits them since it renders inside that
  DOM tree — just reference them in your injected `<style>`, no import needed:
  - `--hb-bg` — card/panel background (white in light, dark slate in dark)
  - `--hb-bg-soft` — a softer/tinted surface (nested cards, "now" highlights, subtle rows)
  - `--hb-ink` — primary text
  - `--hb-muted` — secondary text (labels, timestamps, captions)
  - `--hb-muted-2` — tertiary/faint text (least important, e.g. source attributions)
  - `--hb-line` — hairline borders
  - `--hb-accent` (blue) / `--hb-accent2` (teal) — same hue in both themes, safe to use as-is
  - `--hb-risk` — error/danger red, same in both themes
  - `--hb-neutral` — neutral gray for default/unset states (e.g. an unfilled bar or a dot with no category)
  - `--hb-warn-bg` / `--hb-warn-border` / `--hb-warn-ink` — amber warning/nudge banner (bg / border / text)
  Give every `var(...)` a hex fallback matching the OLD light values (e.g. `var(--hb-bg,#fff)`) so a widget still
  renders sanely even if loaded outside the host page. Example: `background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)`.
- **Type**: system sans (`-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial`). Title ~15px/600, body ~12.5–14px.
- **Cards**: `background:var(--hb-bg,#fff)`, `border-radius:12–16px`, 1px `var(--hb-line,#eef1f6)` border, subtle
  shadow, ~11–14px padding. Optional 3–4px left accent bar in `var(--hb-accent,...)` / `var(--hb-accent2,...)`.
- **Layout**: COMPACT. Prefer horizontal / grid layouts where they fit. NEVER a tall single broken column of stacked tiny rows. Respect `width:min(620px,90vw)`-ish.
- **Language**: Spanish labels when the user speaks Spanish (numbers/dates in es too).
- **Widget kit (optional, `app/styles.css` §WIDGET KIT)**: global `hbk-`-prefixed helper classes for the patterns
  that repeat in almost every widget — `hbk-card` (surface), `hbk-hd` (header row: `<b>` title + `.hbk-sub` +
  optional `.hbk-sub.hbk-right` for a trailing timestamp), `hbk-muted`, `hbk-empty` (empty/error state box),
  `hbk-chip` (pill/badge), `hbk-btn` (small button). They already use the `--hb-*` tokens, so reaching for them
  instead of hand-rolling the same CSS again means LESS code to write and get a themed, consistent look for free.
  Not mandatory — a layout that doesn't fit this shape can still be 100% custom CSS.

## Hard rules
- **Self-contained**: no external libraries, no CDN, no network from `widget.js`. Inject your `<style>` once (id-guarded).
- **Security**: any web/3rd-party/user text → build DOM with `textContent` (NEVER `innerHTML` for untrusted data).
- **Class names must not collide with `frontend/app/styles.css`'s global classes** (checked by the generator's
  validation gate — see below). Scoping your rules under your own root wrapper (`.hb-msg .conn{...}`) does NOT
  protect you: the element still has `class="conn"`, and if the app-wide stylesheet ALSO has a bare `.conn{...}`
  rule (no ancestor prefix), its properties apply too — CSS cascades per-property, not per-rule. This shipped as a
  real bug once: `mensajeria`'s own connection card used `.conn`, which collided with the app's bare
  `.conn{position:fixed;left:20px;bottom:14px;...}` (the mic/SSE status line) and got yanked out of the widget
  card to a fixed corner of the screen — looking like a second, detached window. Pick class names specific to your
  widget's own vocabulary (`.linkcard`, `.wicon`, not `.conn`/`.ic`/`.me`/`.item`/`.row` if a short generic name is
  already in wide use elsewhere).
- **Contract**: `widget.js` exports `render(el, data, ctx)`; `data.py` has `view_data(q="")` (stdlib only, never raises — it is executed as a smoke-test at generation time); `manifest.json` has `{id,version,title,description,whenToUse,keywords[],entry:"widget.js"}`; `__init__.py` empty.
- **If `data.py` also has `apply_action(action, payload)` (any mutation beyond pure read), declare EVERY action in `manifest.json` under `"actions"`: `{"add_meeting": {"desc": "one line", "payload": {"field": "type/example"}}, ...}` — one entry per action, no more, no less. ALSO add a top-level `"usage"` one-liner (how the brain should drive the widget: which action for which intent). This is the widget's DATA API — how the FlashBrain calls it via `[[widget.data:ID]]{"action":"add_meeting","payload":{...}}[[/widget.data]]`. An action NOT declared here is invisible to the brain even if `apply_action` accepts it; a declared action `apply_action` does NOT handle is a dead entry — **the validation gate REJECTS either mismatch** (`widgets/generator.py::_validate_actions_sync`), so keep `actions` and `apply_action` in sync. Keep `desc` short (it's injected into the brain's prompt every turn) and `payload` a flat example shape, not a JSON-schema.
  - **Every declared action is a DATA-OP the FlashBrain runs itself, instantly** (V2-025) — a data mutation is NEVER escalated to a code agent. The FlashBrain invokes it via the function-calling tool `widget_data(widget_id, action, item, payload)` (V2-026 — reliable; the inline `[[widget.data]]` tag is only a fallback). The only thing you mark is IRREVERSIBILITY: add **`"confirm": true`** (alias `"irreversible": true`) to an action ONLY if it has real, non-undoable consequences (pay, send, publish, delete-all, empty) — the FlashBrain still does it, but asks the operator for a yes/no first. Leave reversible edits (add, done, snooze, drop, mute) bare. The canonical semantics live in `widgets/actions.py`. The legacy `"safe": true|false` flag still parses (both map to a direct data-op now) but is **deprecated — do not emit it**; use `"confirm"` for the irreversible ones. `widgets/agenda/manifest.json` is the reference (`add_meeting` bare, `drop_project` `confirm:true`, plus a `usage` line).
  - **If any action targets an EXISTING item by an id (a `taskId`/`projectId`/`chatId` in its payload), add `def ref_index() -> list[dict]` to `data.py`** returning the widget's LIVE referenceable items as `[{"id","label","field"[,"hint"]}]` (`field` = the payload key that identifies it, e.g. `"taskId"`; `label` = human text to match; only current items — skip done/dropped). This lets `widgets/refs.py` resolve a natural-language reference the operator speaks ("the daemon task") to the real id — the model NEVER guesses ids (V2-026). Without it, actions that take an item id can't be driven reliably by voice. `widgets/agenda/data.py:ref_index()` is the reference. Also normalise any relative dates/times the operator might speak inside the widget layer (see `agenda.data._resolve_date/_resolve_time`), so a meeting "tomorrow at five" lands correctly.
- **Background execution — decide this for EVERY widget (V2-034).** Does this widget's data change on its own, off-screen, so the operator could ask about it by voice without opening the card (an inbox, a feed, weather)? If NO (most widgets — a search box, a chart computed on read), leave it foreground-only: `view_data()` runs on demand, nothing else. If YES, declare a cycle in `manifest.json`: `"background": {"every": "1m"}` (also accepts `"1m"`/`"30s"`/`"1h"` or a number of seconds; **minimum 1s** — a fast feed 1m, weather 1h) and add `def tick(ctx=None):` to `data.py`. The scheduler calls `tick(ctx)` every cycle OFF the hot path — fetch/refresh, `store.save(...)` ONLY if data changed, and WRITE anything the operator might ask about into central memory THROUGH `ctx` (so data.py stays stdlib-only, no `import memory`): `ctx.remember(text, slot="<widget>:<key>")` — use a `slot` so it SUPERSEDES instead of piling up — or `ctx.ingest(source, entity, text)` for incoming items. `tick` must be cheap and never raise (a failing tick is isolated). A `backed` widget is already background (its owner self-schedules) and needs no `tick()`. Reference: `widgets/meteo-soria` (passive, `every:1h`, weather → `slot=weather:soria`) and `widgets/mensajeria` (backed, messages → memory → voice).
- **Does your widget PRODUCE something (V2-092)?** «Produce» = it keeps doing something after the operator stops
  looking: playing audio or video, recording, running a live process. If YES you MUST declare it — otherwise your
  widget keeps going with the agent STOPPED, and that shipped as a real bug (with the agent stopped, a YouTube
  video kept playing, restarted itself on page reload, and played over the music player at the same time):
  ```json
  "runtime": {
    "output": "audio",                                   // exclusive channel it takes (omit if it competes for none)
    "produce": ["load", "play", "restart", "unmute"],     // the actions that START it producing
    "suspend": "pause",                                  // the action that makes it STOP
    "active_when": {"videoId": true, "paused": false}     // how "it is producing" reads from view_data()
  }
  ```
  `suspend` and every `produce` entry must be REAL declared actions (a typo here = a stop that stops nothing, and it
  would fail silently). `active_when` may be a LIST of conditions when a widget can produce more than one way (AND
  inside one, OR between them); it accepts dotted paths (`yt.paused`). With that declared, three things come free
  via `widgets/producers.py`: the global stop suspends you, taking the `output` channel silences whoever else had it
  (the speaker is ONE), and the server refuses your `produce` actions while the agent is stopped.
  **Also gate it in `widget.js`**: `ctx.running === false` means the agent is stopped, so do NOT autoplay on mount —
  and for an `<iframe>`, leave `autoplay=0` out of the `src` itself, because a pause sent afterwards arrives late and
  the first instant is audible. Read it as "stopped only if explicitly false" (an old `ctx` has no such field).
- **Isolation is the prime directive — a widget must NEVER be able to break the rest of the system.** Stay inside your own folder for CODE. Stay inside your own `widgets/_data/<your-id>/` directory for DATA — no background threads, no long-lived connections/websockets, no imports from `voice/`/`brains/`/`server/`, no writing anywhere else on disk. A crash in your `view_data`/`render` must degrade to an empty state, never take down the canvas or another widget.
- **Persistence = INDEPENDENT per widget, in its OWN data directory** (the ideal, chosen deliberately, and kept separate from your CODE folder on purpose — `[[modify]]`/`[[delete]]`/regeneration rewrite `widgets/<id>/`, so data living there would be destroyed by your next edit). Use the shared helper `from .. import store`:
  - `store.load("<id>", {})` / `store.save("<id>", db)` — atomic JSON at `widgets/_data/<id>/state.json`, one directory per widget.
  - `store.data_dir("<id>")` — the directory itself, for anything beyond a flat JSON (media/, attachments, a criteria file the voice can edit) — still 100% isolated to your own namespace, never write outside it.
  NEVER a single shared blob — that would couple widgets and let one corrupt another. To READ system-produced data (e.g. `.meshkore/logs/`) read it with stdlib; don't copy it into your store. Prefer deriving on read; persist only what can't be recomputed.
- **Store versioning (if your schema may evolve)**: declare `DB_VERSION = 1` and load with `store.load("<id>", seed, version=DB_VERSION, migrate=_migrate)`. The store keeps the version in a reserved `_v` field and calls `_migrate(db, from_v)` LAZILY on read when it finds an older file — no migration scripts; old data upgrades the first time the new code reads it. Bump `DB_VERSION` when the stored shape changes and handle each older version in `_migrate` (`widgets/agenda/data.py` is the reference).
- **Communication is brain-mediated.** Widgets are dumb and never talk to each other. The brain is the only orchestrator (it reads one widget's data and pushes to another via its tag protocol; the FlashBrain runs the declared data-ops, the SlowBrain writes/changes the widget's code). Do not add cross-widget calls or an event bus.
- **This contract describes PASSIVE widgets** — a single writer (the widget's own `ctx.action`/Hermes), no background process. A widget that needs a genuinely live backend (an open connection to an external service, a poller, something that changes state on its own between user actions) is a different, more advanced shape — see `.meshkore/docs/modules/zaelar-modules.md` §Widgets ("backed" widgets, designed 2026-07-07, not yet wired) before attempting one; don't improvise a background thread inside a passive widget's `data.py`.
- **No polling, ever.** `widget.js` already can't fetch its own data (network from JS is banned outright — see below), so there's never a reason to poll. The host (`desktop.js`) re-renders your widget automatically, exactly once, whenever your `data.py` calls `store.save()` (any path: the widget's own `ctx.action`, or Hermes via `[[widget.data]]`) — it's pushed over SSE, not polled. Your `render()` just needs to be safe to call repeatedly with fresh `data`. (A `setInterval` purely for a LOCAL cosmetic tick with no data implications — a clock face, a countdown display — is fine, e.g. `clock`/`agenda`/`timer`; that's not polling.)
- **Keywords**: keep them PRECISE and non-overlapping with other widgets (e.g. a clock owns `hora/reloj`, NOT `tiempo` — that's weather). Avoid generic words that collide — validation REJECTS a manifest whose keywords are ALL already owned by other widgets.
- **Harness**: `make test-widgets` runs every widget through contract + golden `view_data()` shape + ES-module parse. `golden.json` in your folder is the recorded shape snapshot — if you intentionally change `view_data()`'s shape, delete it so the harness re-records it.

## Memory — DO NOT make the user repeat themselves
- Each widget folder has a **`notes.md`** = the running log of decisions and constraints for THIS widget.
- **Before editing**: READ `widgets/<id>/notes.md`. Treat every line as a standing decision — **never undo or regress** a recorded choice (e.g. if it says "horizontal hours, NOT vertical", keep it horizontal).
- **After editing**: APPEND one short bullet to `widgets/<id>/notes.md` recording what was asked + any constraint stated ("user wants X; rejected Y"). Keep it terse.
- The point: the next session reads notes.md and continues in the same direction instead of looping back to rejected ideas.
