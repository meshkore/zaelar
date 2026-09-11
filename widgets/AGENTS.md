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
- **Type**: `font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif)` —
  NEVER the raw stack alone: `--sans` is a THEME TOKEN (V2-617), so the operator's typeface choice in
  ⚙ Apariencia reaches your widget only if you read the token. Sizes in **rem** (the desktop's root font size
  is the ⚙ size knob — `1rem` scales with it, a hardcoded `13px` does not): title ~0.9rem/600, body
  ~0.78–0.875rem. The canonical steps exist as tokens too: `var(--fs-micro/-caption/-ui/-body/-title/-display)`.
- **Cards**: `background:var(--hb-bg,#fff)`, `border-radius:12–16px`, 1px `var(--hb-line,#eef1f6)` border, subtle
  shadow, ~11–14px padding. Optional 3–4px left accent bar in `var(--hb-accent,...)` / `var(--hb-accent2,...)`.
- **Layout: THREE SIZES, ONE WIDGET.** The same `widget.js` has to read well at all three, because the operator
  moves between them with one gesture: (1) a **PHONE** (`frontend/mobile/`: the widget IS the screen, ~390px
  wide, 366px of usable content); (2) the **DESK CARD**, a free-floating window that opens at your
  `manifest.size` and which the operator then drag-resizes down to `manifest.min`; (3) **MAXIMIZED / FULL
  SCREEN**, the whole canvas (~1400×800 and up), reached by the ⤢ button, a double-click on the header, or by
  voice. Write it FLUID and it works at all three; write it for one and it breaks at the others. In practice:
  - **The third is the one that gets forgotten**, and it is the one the operator asks for when he actually
    wants to LOOK at something. At that size a layout that only knows how to be narrow leaves a 400px column
    stranded in the middle of an enormous empty card. Let the content REFLOW into the room it is given:
    `repeat(auto-fit,minmax(<N>px,1fr))` for anything list- or grid-shaped, a `max-width` on long PROSE only
    (in `ch`, never a px cap on the root), and `height:100%` on the one element that should fill the card
    rather than a fixed pixel height.
  - **The CHROME belongs to the host, never to the widget.** Every card is built by
    `frontend/app/widgets/desktop.js` with a header carrying its name and its ⚙ aliases, a ✕ to close, a ⤢ to
    maximize/restore, eight drag-resize handles, a draggable header, and its chip in the widget rail to
    minimize — and the operator can drive every one of those by voice as well
    (`fullscreen_widget`, `arrange_canvas`, `show_widget`, `[[close]]`). So **never draw your own
    close/maximize/minimize/resize control, your own title bar, or your own outer border+shadow around
    everything** — that is a second frame inside the first. What a widget owns is the INSIDE. `ctx.close()` is
    there for content that means «I am done»; `ctx.top()` resets the scroll after you swap screens.
  - **Never a fixed `min-width` above 360px** — it is the one declaration no container can absorb, so the card
    ends up scrolling sideways and the operator has to drag the widget around to read it. *The validation gate
    rejects this* (`widgets/validator.py`). Sizes come from `%`, `minmax()`, `flex-wrap`, `grid-template-columns:
    repeat(auto-fit,minmax(140px,1fr))` — that one line is a row on a desk and a column on a phone, for free.
  - **Your ROOT element (the one `render(el, data, ctx)` sets `el.className` on) must be `width:100%` — never
    a fixed `width:<N>px` or `width:min(<N>px, <M>vw)` cap** (V2-615, the operator: *"si lo amplío para poder
    ver el texto mejor, que se pueda ampliar — todos los widgets deben ser auto-escalables"*). The desktop host
    (`frontend/app/widgets/desktop.js`) mounts your `el` directly into a fully fluid card with NO intermediate
    fixed-size wrapper, and drag-resize sets that card's width directly — so a hardcoded cap on your root is not
    a safety net, it is the operator dragging a card wider and NOTHING inside it using the extra room (measured
    live: a long URL wrapped across five lines inside a 480px column while the card itself sat empty at 900px).
    Nine of the fourteen system widgets carried this exact anti-pattern before it was fixed catalog-wide — it was
    desktop-era advice this file's own previous line already half-retracted for mobile but never actually
    corrected on desktop. `results`, `documento` and `youtube` are the reference: `width:100%;box-sizing:
    border-box`. *Measured, not assumed*: `tests/browser/e2e/widgets/test_widget_roots_fill_a_wide_desktop_card.py`
    renders every widget in the catalog on a 900px card and fails if its root measures meaningfully less.
  - **COMPACT still, and horizontal WHERE IT FITS** — but a single column is not a failure mode on a phone, it is
    the right answer. What is still wrong is a column of tiny stacked rows that wastes the width it *does* have.
  - **Genuinely wide content scrolls in its OWN box**: put a wide table/timeline inside a wrapper with
    `overflow-x:auto`. Wide is fine; wide that pushes the CARD sideways is not.
  - **Tap targets**: the phone shell already applies a 44px floor to every `button`/`input`/`select`/`a[href]`
    inside a card, and forces inputs to 16px (below that iOS Safari zooms the page on focus and never recovers).
    So you do not have to size for thumbs — but do not FIGHT the floor either: a control that must stay small
    (a checkbox, a slider track) is already excepted, and anything else you pin with a hard `height` will look
    cramped exactly where it matters most. Prefer `padding` over `height` on your own buttons.
  - Measured, not assumed: `tests/browser/e2e/mobile/render_widgets_on_a_phone.py` renders EVERY widget in the
    catalog — including this one, once it exists — at 390px with its real data and fails on horizontal overflow,
    anything escaping the screen, controls under 40px and inputs under 16px.
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
- **Translation (V2-613, OPTIONAL)**: `ctx.t(key, params?)` — a synchronous, in-memory lookup, never a network call — resolves a key from `i18n/bundles/en.json`+`es.json` (add yours as `widgets.<id>.<key>`, same file BOTH bundles) into the operator's active UI language, falling back to English then to the literal key. `ctx.lang` (a getter, the raw active code like `"es"`) is for the rarer need that ISN'T a string swap — day/month names, date order, currency — hand it to `Intl.DateTimeFormat`/`NumberFormat` instead of hand-building a template that only reads right in one language's word order (`widgets/clock` is the reference: `Intl.DateTimeFormat(ctx.lang, {...})`, not a hardcoded Spanish day-name array). **This only matters for a widget SHIPPED to every operator regardless of their language** — a one-off widget generated FOR this operator, after their language is already known, is already being written in it and needs neither. Both are GETTERS/live functions on `ctx`, so `render()` can be called again after a language switch (the host does this automatically for every open card) and see the new language without a data change.
- **If `data.py` also has `apply_action(action, payload)` (any mutation beyond pure read), declare EVERY action in `manifest.json` under `"actions"`: `{"add_meeting": {"desc": "one line", "payload": {"field": "type/example"}}, ...}` — one entry per action, no more, no less. ALSO add a top-level `"usage"` one-liner (how the brain should drive the widget: which action for which intent). This is the widget's DATA API — how the FlashBrain calls it via `[[widget.data:ID]]{"action":"add_meeting","payload":{...}}[[/widget.data]]`. An action NOT declared here is invisible to the brain even if `apply_action` accepts it; a declared action `apply_action` does NOT handle is a dead entry — **the validation gate REJECTS either mismatch** (`widgets/generator.py::_validate_actions_sync`), so keep `actions` and `apply_action` in sync. Keep `desc` short (it's injected into the brain's prompt every turn) and `payload` a flat example shape, not a JSON-schema.
  - **Every declared action is a DATA-OP the FlashBrain runs itself, instantly** (V2-025) — a data mutation is NEVER escalated to a code agent. The FlashBrain invokes it via the function-calling tool `widget_data(widget_id, action, item, payload)` (V2-026 — reliable; the inline `[[widget.data]]` tag is only a fallback). The only thing you mark is IRREVERSIBILITY: add **`"confirm": true`** (alias `"irreversible": true`) to an action ONLY if it has real, non-undoable consequences (pay, send, publish, delete-all, empty) — the FlashBrain still does it, but asks the operator for a yes/no first. Leave reversible edits (add, done, snooze, drop, mute) bare. The canonical semantics live in `widgets/actions.py`. The legacy `"safe": true|false` flag still parses (both map to a direct data-op now) but is **deprecated — do not emit it**; use `"confirm"` for the irreversible ones. `widgets/agenda/manifest.json` is the reference (`add_meeting` bare, `drop_project` `confirm:true`, plus a `usage` line).
  - **If an action targets an EXISTING item, SAY WHICH payload key names it: `"ref": "<key>"` in the action spec.** `widgets/refs.py` also accepts the older convention (a key whose name ends in `id`: `taskId`, `projectId`, `chatId`) — but a key named anything else is invisible without `ref`, and invisible here does not fail loudly: `resolve()` answers "nothing to resolve" and hands the widget an EMPTY payload whatever the operator said. Measured live (V2-595): `youtube.play_item` declares the key `item`, published its `ref_index()` rows for weeks, and answered `item_not_found` to «play the first one» over a list of five.
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
- **A screen change is ONE transition, and it belongs to the WIDGET, not to whoever asked (V2-626).** If your `render()` has module-level state that can hide the main face — a setup screen, a detail view, a pending confirmation — then changing what the widget is showing must go through a SINGLE function that resets all of it, and every entry point (a click, the title, a view the brain pushed through your declared action) must call that function. Do not clear those flags inline in each handler: the next entry point will not know, and it will fail SILENTLY — the header changes, the body does not, and there is no error anywhere. This is state mechanics, so it must not depend on which caller triggered it. Real bug: messaging lit the email icon by voice and left the WhatsApp connector screen underneath it, because the click path cleared the screen inline and the pushed-view path never learned to.
- **Keywords**: keep them PRECISE and non-overlapping with other widgets (e.g. a clock owns `hora/reloj`, NOT `tiempo` — that's weather). Avoid generic words that collide — validation REJECTS a manifest whose keywords are ALL already owned by other widgets.
- **Harness**: `make test-widgets` runs every widget through contract + golden `view_data()` shape + ES-module parse. `golden.json` in your folder is the recorded shape snapshot — if you intentionally change `view_data()`'s shape, delete it so the harness re-records it.

## Memory — DO NOT make the user repeat themselves
- Each widget folder has a **`notes.md`** = the running log of decisions and constraints for THIS widget.
- **Before editing**: READ `widgets/<id>/notes.md`. Treat every line as a standing decision — **never undo or regress** a recorded choice (e.g. if it says "horizontal hours, NOT vertical", keep it horizontal).
- **After editing**: APPEND one short bullet to `widgets/<id>/notes.md` recording what was asked + any constraint stated ("user wants X; rejected Y"). Keep it terse.
- The point: the next session reads notes.md and continues in the same direction instead of looping back to rejected ideas.
