---
title: Mobile Shell (PWA)
category: modules
updated: 2026-10-26
owner: ricart
status: current
---

# Mobile shell — a second face on the same engine

`frontend/mobile/` is a **second frontend shell**, not a responsive variant of the first one. It is installable on a
phone home screen as a Progressive Web App (Android and iOS, no app store involved) and it drives the **same
engine**: same services, same store, same widget catalog, same backend. There is no mobile backend and no mobile API.

Deployment-specific policy is out of scope here — see the public/private boundary in `CLAUDE.md`.

## Why a second shell rather than media queries

The two hosts have different subjects:

| | desktop shell | mobile shell |
|---|---|---|
| stylesheet | `app/styles.css`, a 3-column desk, docking chat, draggable chrome | `mobile/app/styles.css`, a fraction of the size |
| widget host | `app/widgets/desktop.js`, whose subject is a pointer: drag by the grip, 8 resize handles, free-space tiling, z-order on click | `mobile/app/shell/Deck.js`: one ordered deck, one card at a time, full screen |
| controls | an arc of icons above the orb + a top bar | one bottom dock of FIVE controls, orb in the CENTRE, every control within thumb reach |
| panels | several open at once, floating and dockable | mutually exclusive bottom sheets |

Retrofitting the first host would put every mobile regression inside the desktop's blast radius permanently. The
split costs one thing — two hosts to keep honest — and node **4.18** of the testmap is what pays it.

## The two contracts that made the split cheap

Neither mentions the DOM, which is why a second host was possible at all.

### 1. The host contract — `services/sse.js` → a host

`openSSE(host)` touches no DOM. The only thing it ever does with its argument is call these:

```
show · close · closeAll · createWidget · modifyWidget · onDeleted · showConfirm · hideConfirm
move · resize · fullscreen · refreshData · refreshRegistry
```

…plus `setRunning(on)` (from the entry point) and `_reportOpen()` (`session-lk.js`, on reconnect).

Implement those and the brain drives the shell for free — voice-opened widgets, closes, irreversible-action
confirmations, live data refresh — with **zero changes to `sse.js`**. Node 4.18 derives the required list from
`sse.js`'s own source, so a method added there fails the test instead of being silently ignored on the phone.

Two of them mean something different in a deck, and the difference is documented rather than faked:

- `move(id, where)` — "put it on the left" has no spatial meaning when one card fills the screen, so it REORDERS the
  card in the deck.
- `resize(id)` — accepted and refused explicitly (`{ok: false, reason}`). A card IS the screen. A silent no-op in a
  contract method is how a shell starts lying about what it did.

### 2. The widget ctx — a host → `/widgets/<id>/widget.js`

Every widget is mounted with `mod.render(el, data, ctx)` where `ctx` is four members:

```js
{ action(name, payload), close(), top(), get running() }
```

None of them is about cards or dragging. **The entire widget catalog therefore works in this shell without touching
a single widget**, including widgets the agent generates tomorrow. `running` is a getter on purpose: `ctx` is built
once per mount and reused across re-renders, so a copied value would go stale and a widget that produces something
would start up over a stopped agent.

## Anatomy

```
frontend/mobile/
├─ index.html               own shell: own preboot splash, PWA meta, service-worker registration
├─ manifest.webmanifest     PWA identity — scope/start_url at /m, standalone, icons
├─ sw.js                    service worker, deliberately almost empty (see below)
├─ offline.html             the only page the worker serves from its cache
├─ icons/                   192/512/maskable/apple-touch + generate.py (drawn from the palette, no design tool)
└─ app/
   ├─ main.js               entry point — parallel to app/main.js; every divergence is commented with why
   ├─ styles.css            own stylesheet; imports nothing from app/styles.css
   └─ shell/
      ├─ mobile-surfaces.js canonical list of native mobile surfaces (the pattern of core/system-surfaces.js)
      ├─ Deck.js            ★ the host: full-screen cards, two-finger paging
      ├─ DockBar.js         the bottom bar: ☰ menu · chat · wake word | ORB | mic · speaker · feedback
      ├─ OrbMini.js         the orb
      ├─ ChatSheet.js       chat as a bottom sheet
      ├─ MenuSheet.js       ☰: account (plan, Energy, billing, sign-out) · Energy → top-up · settings · voice · escape hatch
      ├─ FeedbackSheet.js   the feedback form in its own sheet, opened by the dock's ⚠ (never inside the menu)
      ├─ EnergyLine.js      the cycle's Energy left, a 3px line along the top edge (cloud only, inert to touch)
      ├─ SettingsSheet.js   the small settings sheet (language · theme · speaker)
      └─ VoiceHeldNotice.js "your voice is on the other device" + take it over
```

### Shared, never forked

| Shared | Why a second copy would be worse than the duplication it removes |
|---|---|
| `app/core/store.js` | The single truth about power, energy, chat, tasks, language. Two stores would be two truths, and a state that can disagree with itself is exactly what a single store exists to prevent. |
| `app/core/reactive.js` · `dom.js` · `i18n.js` | Primitives. A fork breaks reactivity across the shared store. |
| `app/services/*` | `session.js` (→ `session-lk.js` via the route in `livekit_api.py`), `sse.js`, `api.js`, `visualizer.js`, `feedback-api.js`. None of them knows about layout. |
| `app/core/palette.css` | The `--hb-*` color contract both shells and every widget read. Extracted from `app/styles.css` for exactly this reason: a second copy of the tokens would not fail loudly, it would make a widget paint wrong colors in one shell only. |
| `app/core/shared-surfaces.css` | The CSS of the three components both shells mount verbatim — `BootOverlay`, `LanguageOnboarding`, `Alert`. Forking a first-run gate is how two shells end up disagreeing about whether onboarding happened. |

`MemoryMap` is the one shareable component deliberately left out: the component would import fine, but its styling
is a panel UI keyed to a wide window, and re-fitting it is its own piece of work.

## Design rules specific to this shell

- **Paging is one finger, anywhere — and still two or three** (V2-815, operator: «tiene que ser fácil movernos con
  un dedo a derecha e izquierda»). One finger pages when the swipe is clearly sideways (48px, twice as much sideways
  as down) and did not start on something that scrolls or drags sideways on its own — a tab strip, a thumbnail rail,
  a map, a slider, a canvas (`Deck._ownsSideways`) — unless it started within 22px of a screen edge, which always
  pages. A finger that goes down first is the widget's for the rest of the gesture, and the vertical scroll is never
  prevented. That is the rule a ViewPager and a UIPageViewController apply. Two or three fingers page as before:
  three is iOS muscle memory, and what an intended two-finger swipe becomes when a thumb rests on the edge. The
  centroid is taken over ALL active touches and re-baselined when the count changes mid-gesture.
- **Card content is TOP-aligned in a uniform box**, with the widget's own tabs (if any) as its first row. Centring
  anything shorter than the screen would float a clock mid-phone, push a widget's tabs away from the header, and
  make the body jump under a header that stays put while paging. `min-height:100%` is the half that makes the box
  FIXED rather than merely top-aligned.
- **A card is hidden while paging, never unmounted.** A video that keeps playing behind another card is correct;
  re-mounting it on every swipe would cut it off. The global stop is what silences it.

### The touch floor, its two exceptions, and the keyboard (V2-813)

The shell holds every card's controls to a thumb (`styles.css`, «TOUCH FLOOR»):
- every control is at least 44px;
- every text field is 16px (below that iOS zooms on focus);
- a row that directly holds controls wraps rather than push the card sideways.

That last rule is right for a toolbar and wrong for two shapes, which are exempt.

- **A row that manages its own width** — tabs that scroll sideways (`role="tablist"`), a thumbnail rail, a title
  that ellipsizes beside its close (`data-strip`). Wrapping youtube's tabs broke its header into two rows with the
  right cluster floating between them. A widget whose row scrolls or truncates on its own declares it.
- **A box that directly holds a text field** is one control (a search pill: field + clear + go). It never wraps, so
  the field shrinks instead; and it grows with its field, which the floor makes 44px tall.

**The keyboard** (`shell/keyboard.js`). Both phone browsers shrink only the VISUAL viewport, so with a field focused
the deck kept its full height: the keyboard covered its bottom half and the dock covered the rest. While a field
inside `.zm-deck` or inside a `.zm-sheet` has focus and the visual viewport is clearly shorter than the screen, the
root wears `zm-kbd` with `data-kbd="deck"|"sheet"`:
- the surface holding the field (the deck, or the open sheet) is laid over `--zm-vvh`/`--zm-vvt`;
- the dock, the pips, the voice notice and the install banner step aside;
- the field is scrolled into view.

Typing in the chat on the iPhone used to show composer · the whole dock · the keyboard's accessory row · the keys —
half the screen of chrome (V2-815). The accessory row is the system's; everything of ours around it is gone.

Two widget-side rules came out of the same pass:
- a hover-only affordance holds no space on a touch screen (`@media (hover:none)`);
- whatever a double-click opens, one tap opens on a coarse pointer.

### Navigating the deck

**The HOME is page zero** (V2-815, 2026-10-26). Swiping right past the first card, ⌂ in any card's top bar, the first
pip, the Android back button and the engine's `minimize` order all land there. It is a launcher of what is open: one
tile per card — the app's monogram on a colour hashed from its id, its LIVE title (the same source the top bar
paints), ♪ on the one producing sound, the card he came from ringed, an × on each — plus «Close all»; with nothing
open it is the resting state («Talk to zaelar»). Closing from a tile stays on the home. The bottom-sheet switcher the
k/n chip used to open is gone: the home is the switcher.

**Every card wears a top bar**: ⌂ · ‹ · the app's name with k/n under it (a tap goes home) · › · ×, every one a 44px
target; the arrows show only with two or more cards and › is disabled on the last one.

Then the pips and the gestures, all host chrome, none stealing a gesture from the widget:

- **The pips** sit ABOVE the dock (`bottom: calc(var(--dock-h) + safe-area)`): a ⌂ pip for the home, then one
  26px BUTTON per card, the current one lit, each jumping where it points. They are the only always-on "there are
  more cards" signal, so their geometry is checked by a rendered test (node 4.87), not assumed from the source.
  `pointer-events` live on the buttons, never the full-width row. They overlay the card's last 30px, which the
  scroller pads for.
- **A one-finger swipe anywhere pages** (rule above); the header, being host chrome, pages on any sideways finger.
- **The producing badge.** A hidden card that is PRODUCING (music behind the front card) marks its pip and its
  switcher row: sound with no visible source reads as a haunted phone. "Producing" is read from the manifest's
  `runtime.active_when`, evaluated with the SAME semantics as `widgets/producers.py::is_producing`
  (`true`/`false` by truthiness, anything else by text, degraded data never produces) — never a widget-name
  list, which is exactly the per-widget `if` that contract exists to kill. One manifest fetch per base, cached.

`restore()` is at parity with the desktop's, and each piece matters more on a phone: the SERVER fallback
(`/api/canvas/layout`) because localStorage is per-browser and a phone IS a new browser — a freshly installed PWA
opens on the account's current deck, not an empty one; the fossil sweep (a bare BASE card next to its own instance
would resurrect an empty sheet over the full one); live errands coming back even if this device never saved them
(start on the computer, follow on the phone); and a `navegador::tN` with no live task filtered out (process state,
nothing to reload).

### The dock, and why the orb is in the middle of it

Since 2026-10-25 the bar is `☰ · chat · wake word` | **ORB** | `mic · speaker · feedback`: the main menu is the classic
three bars (a gear promised «settings» and held the account), and feedback has its own sheet. What follows is the
earlier five-control rationale, which still holds for the orb and the zones:

- **chat / dashboards** are the WHOLE footer navigation, however many cards are open. Which card you are on is
  the deck's business — its pips and its `k/n` switcher — never the bar's. *Dashboards* is not a sheet: it is
  what sits UNDER every sheet, so the button closes chat, menu and settings.
- **the ORB is 74px and carries the mic glyph INSIDE it.** The inner mic is STATE (level while listening,
  slashed and red while muted); the mic BUTTON on the right is the control. Same relationship the desktop has
  between its orb and its arc.
- **No captions in this shell** — neither button nor band. `store.captionsOn` / `captionSeg` are untouched and
  still drive the desktop.
- **the SPEAKER lives in the config sheet.** There must always be a way to silence the agent from the phone, so a
  structural check asserts the control exists somewhere in the shell.
- **the MIC is the fifth slot**, and the reason is the rule: muting your own microphone is a privacy gesture,
  and a privacy gesture that takes two taps and a sheet is not one.

The dock grid is laid out `minmax(0, 1fr) auto minmax(0, 1fr)`. The `minmax` floor is load-bearing: a bare `1fr`
means `minmax(AUTO, 1fr)`, so a side with more buttons grows its own track past its fair share and shoves the orb
off centre. Icons are 48px, above the 44px minimum; each side carries two (98px of ~144 available on a 390px
screen), which is the slack that lets the orb be 74px.

**The orb IS the switch.** Stopped, the centre slot is a ⏻ and nothing else — nothing else is true about a
stopped agent. Running, it is zaelar's face, and tapping it stops (or, mid-`pausing`, cancels the stop). Both
faces go through ONE handler, the same `api.runStop()`/`runStart()` + `markPowerCommand()` seam the desktop ⏻
uses: the switch is the SERVER's state, so a mobile-only path that flipped a local signal would show "stopped" on
the phone while the agent kept working.

⚠️ **Both faces are built ONCE and swapped by visibility — never `() => cond ? a : b`.** That reactive shape is
the natural way to write it and it is wrong: the child function re-runs on every `agentState` change and returns
a NEW tree, so each transition mints a fresh `OrbMini` with a fresh `<canvas>`. `main.js` hands `$("#orb")` to
the visualiser exactly once at boot, so after one re-render that reference is a DETACHED node — the render loop
keeps painting into a canvas nobody can see, while the one on screen is never drawn to. The symptom is an empty
hole in the middle of the bar with no error anywhere. Guarded by test nodes 4.18 (structural) and 4.19 (rendered,
counting painted pixels).

The glyphs are the desktop's byte for byte, copied from `app/components/Orb.js`, and node 4.18 DERIVES its
assertion from that file: if the desktop redraws its mic, the mobile shell goes red and somebody decides,
instead of the two drifting apart unnoticed.

- **`--dock-h` is the only geometry, and it is 64px** (V2-815 — operator, iPhone 14 screenshots: the bar was wasting
  the bottom of the screen). The bar is exactly its row of 44px icons plus the safe area ONCE; the 72px orb hangs from
  the bar's top edge and rises 8px above it, the raised centre of a tab bar. Every other surface is flow layout in a
  full-bleed box. Cards end exactly at the dock's top edge; sheets stop ON TOP of it rather than over it, so the mic
  and ⏻ are never more than one tap away.
- **The phone must be able to HEAR.** Two browser rules govern a voice app, not one: the MICROPHONE needs a user
  gesture (handled by re-arming the session on `pointerdown`) and so does audio PLAYBACK. This shell connects at
  LOAD by design, so the agent's first audio track arrives before any tap and the browser refuses it. LiveKit
  reports that as `room.canPlaybackAudio` and clears it with `room.startAudio()` — call it from inside the
  gesture's own call stack (awaiting anything first spends the user activation), and never rely on a bare
  `element.play()`, which a suspended audio context rejects again. The block is painted as an amber ring on the
  ORB, because that is what an operator who cannot hear the agent is looking at.
- **A phone does not inherit silence.** `hb_bot_muted` is persisted by the power switch too, so a mute decided
  in one session would otherwise come back invisibly in the next one. This shell clears it at boot; the desktop
  deliberately keeps its preference.
- **The app icon is a SILHOUETTE on flat black** (`mobile/icons/generate.py`): the mark is the EYE, which
  `CLAUDE.md` already fixes as zaelar's identity (the orb is the iris), drawn with the real eyelid ratios
  (±2.16·R corners, ±1.24·R apex) solved to a circular arc. Strokes, one colour, same vocabulary as every icon
  in the UI. The maskable variant fits the 80% safe CIRCLE by its bounding-box CORNER (2.49·R ≤ 0.4·S) — the
  usual reason a PWA icon looks decapitated on one phone and fine on another.
- **Safe areas are not optional.** `viewport-fit=cover` plus `env(safe-area-inset-*)`, or the dock sits under the
  iPhone home indicator (every tap becomes a swipe-up) and card titles hide behind the notch.
- **Every tap target is ≥ 44px.** The desktop's 26–30px icons assume a mouse's pixel of precision.
- **Inputs are exactly 16px.** Below that, iOS Safari zooms the page on focus and the fixed layout never recovers.
- **Reactive bindings, not snapshots.** `t()` returns the KEY when a string is missing, which is truthy — so
  `t("x") || "fallback"` is dead code, and a `textContent = t("x")` at construction time freezes whatever the
  bundle had before its async fetch landed. Rendering the shell in a phone-sized browser is what catches this;
  reading the source does not.

## The service worker is almost empty on purpose

This is a live agent, and **a cached module is a stale agent**. `server/pages.py` serves the shells with
`no-store` precisely so a reload cannot execute yesterday's JavaScript, and every ES import carries a `?v=`.

So `sw.js`:

- intercepts **only** navigations (`request.mode === "navigate"`): network first, `offline.html` when there is no
  network;
- touches nothing else — `/api/*`, `/events` (SSE), `/widgets/*`, `/static/*` never pass through it;
- **never stores a response**. There is no `cache.put` anywhere in it.

Its whole job is (a) making the app installable on Android, which requires a manifest plus a worker with a fetch
handler, and (b) showing a decent card instead of the browser's dinosaur underground. iOS needs no worker at all —
it needs `apple-mobile-web-app-capable` and an `apple-touch-icon`, both in `index.html`. Node 4.18 ratchets both
properties so nobody "improves" this into a cache.

## Notifications and the install banner (V2-796)

The work happens on the engine; what the phone has to be is a place a notice can LAND. Three pieces:

- **The notice ledger** — `nucleo/pulse/notices.py`. Every reminder, finished job and pending approval is a row in
  `notices` (`zaelar.db`) with a UNIQUE `dedupe_key`, delivered in order: voice when someone touched a visible screen
  in the last 15 min → Web Push to every subscribed browser → `owed` (retried with backoff for 24 h, and painted on
  the next screen that opens its event stream). The row ends `spoken · pushed · covered · shown · seen`. A default
  appointment notice whose Google event rings by itself (a popup override, or the calendar's default popup) is
  `covered`, decided at FIRE time (`widgets/agenda/reminders.covered_by`); an asked notice is always ours. ⏻ stops
  the voice, not the push.
- **Web Push** — `nucleo/pulse/webpush.py`: RFC 8291 (`aes128gcm`) + RFC 8292 (VAPID) on `cryptography`, no push library.
  The key pair is generated on first use beside the credential store. Routes in `server/notices_api.py`
  (`/api/push/key|subscribe|unsubscribe|device|devices|test`, `/api/notices`, `/api/notices/{id}/seen`). The
  browser half is `app/services/push.js`, shared by both shells. `sw.js` gained `push` (always shows — iOS revokes a
  subscription whose pushes are not shown) and `notificationclick` (marks `seen`, focuses or opens the app); it
  still caches nothing.
- **The banner** — `mobile/app/shell/InstallBanner.js`, at the top, one step at a time (`install-step.js`, pure):
  a phone browser tab is offered the APP first (Chromium: one tap through the captured `beforeinstallprompt`; iOS:
  the two steps, because there is no API and Safari tabs get no Web Push at all); installed, it offers
  notifications, and the tap IS the permission prompt. Granted or denied → nothing is shown (no nagging); «Not now»
  snoozes 7 days. Each load reports `installed/permission` to `/api/push/device`. The settings sheet carries the
  same switch plus «test», and the desktop has it under ⚙ → Notifications.

A deployment that stops idle engines may set `ZAELAR_WAKE_URL` (or `CONTROL_PLANE_URL` + its token → `/wake`):
`nucleo/pulse/wake.py` reports the next due instant after every schedule change so the process can be started in time.
Without it, nothing is sent.

Not covered: a self-hosted engine opened from a phone over plain `http://<lan-ip>` is not a secure origin, so it
cannot register a service worker or push. iOS shows no action buttons on web notifications: an approval opens the app.

## Routes and admission

Three paths, all served from the root, all added to `server/ingress.py`'s `PUBLIC_EXACT` allowlist:

| Route | What | Why it can answer without a session |
|---|---|---|
| `/m` | the mobile shell | Like `/`: one HTML file, identical in every process, holding nobody's data. |
| `/manifest.webmanifest` | PWA identity | The browser fetches it before anything else exists. |
| `/sw.js` | the service worker | Must be served from the root — a worker only controls its own directory downwards, so one under `/static/mobile/` could never see a navigation to `/m`. Sent with `Service-Worker-Allowed: /`. |

All three are build constants. Whether tenant data crosses is the only question that allowlist asks, and the answer
is no.

## How a device ends up in which shell

A picker in `frontend/index.html` runs **before any ES module loads**, so a phone never downloads the desktop
stylesheet just to be redirected away from it:

1. an explicit choice wins and sticks — `?desktop=1` / `?mobile=1` persist to `localStorage.zaelar_shell`;
2. a stored choice beats detection;
3. otherwise: narrow viewport **and** coarse pointer → `/m`. Both conditions, deliberately — a narrow desktop
   window is still a mouse, and getting this wrong permissively would strand a laptop user in a one-card shell.

The escape hatch is not optional and appears in two places (the menu sheet and the settings sheet): a shell you
cannot leave is a trap, and the picker would otherwise bounce a tablet back on every load. `/` keeps answering 200
with HTML because the platform's health check fetches it — the redirect is client-side, never an HTTP 302.

## One agent, one voice, many screens (V2-792)

The desktop tab and the phone are **one agent and one conversation**. What differs between them is not the
conversation but what a request does to a screen. The rules, and where each one lives:

| Rule | Mechanism |
|---|---|
| **Voice in and out on ONE screen.** | `server/livekit_api.py`: one live session per machine (heartbeat ~4 s, 12 s TTL). Taking it is an explicit gesture: opening the mic or the speaker on a screen (`session.openMicHere` / `openSpeakerHere`), the phone's load, or `VoiceHeldNotice` → `POST /api/session/steal`. |
| **The loser stands down at once.** | Every change of hands emits `session · voice held by <dev>` with `voice_sid` (the new holder's tab). `sse.js` re-dispatches it as `hb:voice-held`; `session-lk.js` stands down on it (mic and speaker off, the blue «voice elsewhere» orb), instead of waiting up to 4 s for its next heartbeat. |
| **Typed chat from ANY screen.** | Only the holder has a LiveKit room. Every other screen sends its typed line over `POST /api/chat`; the live session registered a typed door (`voice/screens.register_typed`) and injects it as a turn exactly like the data channel does (`agent_events.receive_typed`). `reason:"no_session"` means nobody holds a session — only then does the typing screen bring the voice up. |
| **Every event names the screen that asked.** | `voice/screens.py` stamps `origin_dev` at the stream's single gate (`observer.stamp_identity`). A spoken turn → the voice holder; a typed turn → the screen that typed it (a context var set around the injection, so the reply task inherits it); a background errand → the screen that commissioned it (`note_task`, read from the escalation's context); within a turn the `trace` keeps it even if another turn starts meanwhile. |
| **What a request does to a screen happens on the screen that asked.** | `frontend/app/services/event-scope.js` is the ONE table: `widget` show/create/fullscreen/move/resize/arrange/minimize and `panel` are `origin`-scoped; everything else (transcript, chat, task progress, notices, energy, close, data, confirm) reaches every screen. An origin event for another screen leaves a passive chip (`ElsewhereChips`: «📄 Document · open on the computer — Open here»). A kind routed by `sse.js` in neither list fails node 4.266. |
| **Each app says how it lives on several screens.** | Every manifest declares `"screens"` (`widgets/screen_policy.py`, resolved into the compact index): **`shared`** — a reflection of data (agenda, contacts, results, map…): open on any number of screens, opens where it was asked, the others get a chip, every copy shows the same data live; **`single`** — it takes the device's sound or picture (`youtube`, `musica`): it lives on ONE screen. A `show` of a single card asked from another screen is a MOVE, announced by the server inside that show's own stamp — before the show goes out — so the screen that had it stops and closes its copy before it can load what the new order put in the card, and keeps «▶ now on the phone — Bring here». Opening one by hand calls `POST /api/screens/bring`. A restored screen skips single cards another open screen has (`/api/canvas/layout?dev=` → `elsewhere`). Pause, volume and «páralo» are card data, so they reach the card wherever it plays. `runtime.output` ⇒ `single`; the validator rejects the contradiction, and every widget the generator creates or modifies leaves with the field written. |
| **The brain sees the canvas of the screen it is talking to.** | `server/canvas_api.py` keeps every screen's last report and lets only the current turn's screen write `open_widgets`; when a turn starts on another screen its canvas is adopted silently (`on_active_change`). |
| **The agent knows the screens — only when there are two.** | `screens.slot_line()` adds one line to the turn context (`screens: computer (voice, active) · phone (open)`) with ≥ 2 screens open, nothing otherwise. `show_widget(screen=computer|phone|here)` sends the turn's cards to that screen and moves them there. |
| **Each screen shows ITS state.** | `store.screenState()` — the one derived state every face paints (desktop eye, desktop bar slot, phone dock): `off` → the grey ⏻ (a tap switches the agent on, server first); `holder` → the grey orb (a tap switches it off); `speaking` → the ORANGE orb, only here (`services/orb-colour.js`); `secondary` → the grey orb with the slashed mic, never orange (a tap BRINGS THE VOICE HERE — it used to wear the ⏻ face and stop everything). The ⏻ means power only. Icons: lilac on/open, grey off/closed; mic and speaker only when really live on this screen. One door: `services/power.js` (`setPower`, `centreTap`). Node 4.147. |
| **The wake word is per screen.** | By construction: the spotter runs only on a live session with the mic open, and a screen without the voice has neither. |

The registry (`GET /api/screens`) is process memory: open screens (by event stream, `/events?dev=`), visibility
and last touch (`POST /api/screens/beat`, sent on `visibilitychange` and on a throttled touch), and the voice holder.
A restart forgets it and every screen re-registers on reconnect. A screen whose stream drops stays «open» for
`ZAELAR_SCREEN_GONE_S` (90 s), so a phone on the metro does not lose its results to the other screen.

**A result whose screen has gone** is announced, never opened elsewhere: it keeps its origin, and every open
screen shows the chip.

## Testing

**The phone pass** (node **4.301**, `tests/browser/e2e/mobile/phone_pass.py [ids] [--tabs]`). Every native app is
opened in the REAL shell (`/m`) on Playwright's iPhone 14 (WebKit) and Pixel 7 (Chromium) and screenshotted, tab by
tab. It runs against a preview of the engine's routers in a temp workspace holding a COPY of each app's state, with
no LiveKit router and every session request aborted. It measures four things:
- sideways scroll;
- anything escaping the screen;
- inputs under 16px;
- wrapped tab strips.

The measurement passed all sixteen apps while the screenshots showed real breakage, so the pass ends when the
pictures are looked at. The keyboard has its own rendered node, **4.300**.

Node **4.18** — `tests/browser/unit/mobile/test_mobile_host_contract.mjs` (+ its pytest wrapper). Every assertion
is derived from a source of truth rather than a hand-copied list, because a hand-copied list keeps passing while the
phone silently ignores the brain:

- every `desktop.<method>` call in `sse.js` must exist on `Deck` (and on `Desktop`, as a check on how the test
  reads code);
- every `/api/...` and `/widgets/...` URL the Deck fetches must be a **declared** backend route, scanned out of the
  Python decorators — this is what catches a typo, since a 404 inside a best-effort fetch is swallowed;
- the palette and veil stylesheets are shared and the mobile stylesheet does not redefine an `--hb-*` token;
- the mobile shell does not link the desktop layout stylesheet, and nothing in `app/` imports from `mobile/`;
- the service worker intercepts only navigations and never calls `cache.put`;
- the three PWA paths are in the ingress allowlist;
- the i18n key scan recognises both `t(` and the `tr(` alias that `Deck.js` imports, so no key the deck asks for
  escapes the check.

Each assertion has a disarm: dropping a Deck method, inventing an endpoint and linking the desktop stylesheet each
turn the node red.

Nodes **4.266 / 4.267 / 4.268** (V2-792) — the screens: the scope table and the hand-over wiring
(`tests/browser/unit/mobile/test_every_event_kind_declares_its_screen.py`), two real browsers against one engine
(`tests/browser/e2e/mobile/test_a_card_opens_on_the_screen_that_asked.py`: a card asked on the desktop opens only
there, the phone paints a chip, the transcript reaches both, the phone types without a room, a one-screen card moved
away leaves a chip), and the server half (`tests/voice/unit/test_one_agent_many_screens.py`).

Node **4.19** — `tests/browser/e2e/mobile/render_dock.py` renders the shell at 390×844 and measures the dock:
orb centred and PAINTED, tap targets, sheets stopping above the dock, the stopped→⏻→painted cycle.

Node **4.87** — `tests/browser/e2e/mobile/render_deck.py` renders the DECK with three fake widgets served by
Playwright route interception (catalog, data, manifest and the `widget.js` module itself) and measures the
navigation: pips visible above the dock and jumping on tap, the producing badge following `active_when`, the
switcher opening/jumping/closing/emptying, one-finger header paging, and `restore()`'s parity with the desktop
(fossil sweep, live errands, server fallback on a fresh browser — that last one needs its OWN browser context, or
page 2's localStorage leaks into "fresh install"). Each of those checks has its own disarm (pips back under the
dock, fossil sweep dropped, producing evaluation shorted, header swipe unwired), and each disarm turns exactly its
own checks red.
