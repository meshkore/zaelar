---
title: Mobile Shell (PWA)
category: modules
updated: 2026-08-18
owner: ricart
status: current
---

# Mobile shell — a second face on the same engine

`frontend/mobile/` is a **second frontend shell**, not a responsive variant of the first one. It is installable on a
phone home screen as a Progressive Web App (Android and iOS, no app store involved) and it drives the **same
engine**: same services, same store, same widget catalog, same backend. There is no mobile backend and no mobile API.

Delivered by **V2-124**. The product/cloud side (where it is served, who pays for what, the home-computer bridge)
lives in the workspace root's private repo — see the public/private boundary in `CLAUDE.md`.

## Why a second shell rather than media queries

Measured before deciding, not assumed:

| | desktop shell | mobile shell |
|---|---|---|
| stylesheet | `app/styles.css`, ~89 KB of 3-column desk, docking chat, draggable chrome | `mobile/app/styles.css`, ~11 KB |
| widget host | `app/widgets/desktop.js`, 859 lines whose subject is a pointer: drag by the grip, 8 resize handles, free-space tiling, z-order on click | `mobile/app/shell/Deck.js`: one ordered deck, one card at a time, full screen |
| controls | an arc of 7 icons above the orb + a top bar | one bottom dock, orb in the CENTRE, every control within thumb reach |
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

…plus `setRunning(on)` (V2-092, from the entry point) and `_reportOpen()` (`session-lk.js`, on reconnect).

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
      ├─ DockBar.js         the bottom bar: mic · speaker · captions | ORB | chat · menu
      ├─ OrbMini.js         the orb, and the caption band above the dock
      ├─ ChatSheet.js       chat as a bottom sheet
      ├─ MenuSheet.js       energy · account · voice · settings · feedback · escape hatch
      ├─ SettingsSheet.js   the small settings sheet (language · theme · captions · speaker)
      └─ VoiceHeldNotice.js "your voice is on the other device" + take it over
```

### Shared, never forked

| Shared | Why a second copy would be worse than the duplication it removes |
|---|---|
| `app/core/store.js` | The single truth about power, energy, chat, tasks, language. Two stores would be two truths, and a state that can lie is a failure this codebase has paid for repeatedly. |
| `app/core/reactive.js` · `dom.js` · `i18n.js` | Primitives. A fork breaks reactivity across the shared store. |
| `app/services/*` | `session.js` (→ `session-lk.js` via the route in `livekit_api.py`), `sse.js`, `api.js`, `visualizer.js`, `feedback-api.js`. None of them knows about layout. |
| `app/core/palette.css` | The `--hb-*` color contract both shells and every widget read. Extracted from `app/styles.css` for exactly this reason: a second copy of the tokens would not fail loudly, it would make a widget paint wrong colors in one shell only. |
| `app/core/shared-surfaces.css` | The CSS of the three components both shells mount verbatim — `BootOverlay`, `LanguageOnboarding`, `Alert`. Forking a first-run gate is how two shells end up disagreeing about whether onboarding happened. |

`MemoryMap` is the one shareable component deliberately left out: the component would import fine, but its styling
is a ~200-line panel UI keyed to a wide window, and re-fitting it is its own piece of work.

## Design rules specific to this shell

- **Paging is two-finger.** One finger belongs to the widget — scrolling a list, panning a map, dragging a slider.
  If one finger also paged, every scrollable widget would be unusable. A single touch is never intercepted.
- **A card is hidden while paging, never unmounted.** A video that keeps playing behind another card is correct;
  re-mounting it on every swipe would cut it off. The global stop (V2-092) is what silences it.
### The dock, and why the orb is in the middle of it

Six controls in three zones — `mic · speaker · captions` | **ORB** | `chat · menu` — laid out
`minmax(0, 1fr) auto minmax(0, 1fr)`. The `minmax` floor is load-bearing: a bare `1fr` means
`minmax(AUTO, 1fr)`, so the three-button side grows its own track past its fair share and shoves the orb off
centre (measured at 8px). Icons are 48px because three of them plus gaps must fit ONE side track
(390 − 16 dock padding − 70 orb column = 152 per side; 3×48 + 2×2 = 148), still above the 44px minimum.

**The orb IS the switch.** Stopped, the centre slot is a ⏻ and nothing else — nothing else is true about a
stopped agent. Running, it is zaelar's face, and tapping it stops (or, mid-`pausing`, cancels the stop). Both
faces go through ONE handler, the same `api.runStop()`/`runStart()` + `markPowerCommand()` seam the desktop ⏻
uses: since V2-092 the switch is the SERVER's state, so a mobile-only path that flipped a local signal would
show "stopped" on the phone while the agent kept working.

⚠️ **Both faces are built ONCE and swapped by visibility — never `() => cond ? a : b`.** That reactive shape is
the natural way to write it and it is wrong: the child function re-runs on every `agentState` change and returns
a NEW tree, so each transition mints a fresh `OrbMini` with a fresh `<canvas>`. `main.js` hands `$("#orb")` to
the visualiser exactly once at boot, so after one re-render that reference is a DETACHED node — the render loop
keeps running (measured: 741 frames) painting into a canvas nobody can see, while the one on screen is never
drawn to. Symptom: an empty hole in the middle of the bar, no error anywhere, 0 painted pixels of 9216 against
the desktop's 10490 under the same preview. Guarded by test nodes 4.18 (structural) and 4.19 (rendered).

The glyphs are the desktop's byte for byte, copied from `app/components/Orb.js`, and node 4.18 DERIVES its
assertion from that file: if the desktop redraws its mic, the mobile shell goes red and somebody decides,
instead of the two drifting apart unnoticed.

- **`--dock-h` is the only geometry.** Every other surface is flow layout in a full-bleed box. Cards end above the
  dock; sheets stop ON TOP of it rather than over it, so the mic and ⏻ are never more than one tap away.
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
  bundle had before its async fetch landed. Both were found by rendering the shell in a phone-sized browser, not
  by reading the source.

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

## One voice, two surfaces

`server/livekit_api.py` allows exactly **one live voice session per machine** (heartbeat ~4s, 12s TTL): two open
mics against the same agent break the pipeline. Until now the two surfaces that could hold that lock were two tabs
on one computer, so "close the other one" was advice you could act on in a second. A phone and a laptop in another
room are not two tabs.

The automatic behaviour is unchanged and right: `session.start()` sets `store.micBlocked` and retries every 3s, so
when the other surface closes, the phone picks the voice up on its own. What was missing is that `micBlocked`
paints a 🚫 ring over the desktop orb — legible when "the other tab" is one you can see, meaningless between rooms.
`VoiceHeldNotice` names the situation and offers the one gesture that resolves it: `POST /api/session/steal` claims
the lock, and the previous holder's next heartbeat already knows how to stand down. The surface that loses it drops
to chat plus observer, which has worked since V2-088.

## Testing

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
- the three PWA paths are in the ingress allowlist.

Verified by breaking each one: dropping a Deck method, inventing an endpoint and linking the desktop stylesheet
each turn the node red.
