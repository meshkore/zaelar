// ============================================================================
// Deck.js — THE MOBILE WIDGET HOST.  The mobile counterpart of app/widgets/desktop.js, and a completely
// independent piece: the desktop imports nothing from here and this imports nothing from there.
//
// WHY A SECOND HOST INSTEAD OF MEDIA QUERIES ON THE FIRST ONE
// The desktop host's whole subject is a pointer on a large canvas: drag by the grip, eight resize handles,
// free-space tiling, z-order on click, a preferred size from the manifest. A phone has none of that and has
// something the desktop does not: exactly ONE screen. So this host keeps the open widgets as an ORDERED DECK and
// shows one card at a time, full screen.
//
// WHAT MAKES THE SPLIT CHEAP — the two contracts this file satisfies. Neither mentions the DOM:
//
//   1. THE HOST CONTRACT (services/sse.js -> host). `openSSE(host)` touches no DOM at all; the only thing it ever
//      does with its argument is call these methods. Implement them and the brain drives this shell for free —
//      voice-opened widgets, closes, confirmations, live data — with ZERO changes to sse.js:
//        show · close · closeAll · createWidget · modifyWidget · onDeleted · showConfirm · hideConfirm
//        move · resize · fullscreen · refreshData · refreshRegistry
//      plus setRunning(on)  (V2-092, from main.js) and _reportOpen()  (session-lk.js, on reconnect).
//      That list is asserted by tests/browser/unit/mobile/test_mobile_host_contract.mjs — if a method is dropped
//      here or added in sse.js, that test fails instead of the phone silently ignoring the brain.
//
//   2. THE WIDGET ctx (host -> /widgets/<id>/widget.js). Every widget is mounted with mod.render(el, data, ctx)
//      where ctx = { action(name, payload), close(), top(), t(key, params), get lang(), get running() }. Six
//      members, none of them about cards or dragging — which is why the ENTIRE widget catalog works here without
//      touching a single widget, including widgets the agent generates tomorrow. `t`/`lang` (V2-613) are a
//      SYSTEM widget's door into the SAME translation runtime the shell's own components read: `t(key)` for a
//      custom string, `lang` (the raw active code) for handing a locale-SHAPED need (date order, month names)
//      to `Intl`/`Date`/`Number` instead.
//
// THE DECK HAS A HOME (V2-815, operator 2026-10-26). Page -1 is the HOME: a grid of the open apps as tiles, the
// place to see how many are open and jump to one, and the resting state of the shell when nothing is open. Every
// card has a top bar — ⌂ home · ‹ · the app's name and k/n · › · × — and the pips above the dock count the home
// plus every card, the current one lit. The same shape every phone app with sub-apps uses: a page control, a
// launcher, and a bar that says where you are.
//
// PAGING IS ONE FINGER, anywhere on the screen, and still two or three. One finger pages when the swipe is clearly
// sideways (48px, twice as much sideways as down) and did NOT start on something that scrolls or drags sideways on
// its own — a tab strip, a thumbnail rail, a map, a slider, a canvas — unless it started at the screen's edge, which
// always pages. That is the rule a ViewPager and a UIPageViewController apply, and it is what keeps a vertical list
// scrollable and a map pannable while a swipe across the screen still turns the page. The vertical scroll is never
// prevented: a finger that commits to going down is the widget's.
//
// A CARD IS NEVER UNMOUNTED WHILE PAGING, only hidden. A video that keeps playing behind another card is correct;
// re-mounting it on every swipe would cut it off mid-sentence.
// ============================================================================

import { t as tr } from "../../../app/core/i18n.js?v=1";
import { noteSent } from "../../../app/services/feedback-sent-note.js?v=1";
import * as store from "../../../app/core/store.js?v=2";
// V2-792 — the screens service, loaded on first use (same as the desktop host: a host imports no service statically).
const _screens = () => import("../../../app/services/screens.js?v=1");
const _device = () => import("../../../app/services/api.js?v=2").then((m) => m.DEVICE).catch(() => "");
import { createEffect } from "../../../app/core/reactive.js?v=2";

const CARD_ANIM_MS = 260;
const EDGE_PX = 22;          // a one-finger swipe that starts this close to a screen edge always pages
const SWIPE_PX = 48;         // sideways travel before a swipe is a page turn
const COMMIT_PX = 24;        // vertical travel after which a finger belongs to the widget for good

// The top bar's glyphs: the same 24-box, 2px stroke, round caps as every icon in the UI (DockBar.js).
const SW = `viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"`;
const HOME_ICO = `<svg ${SW}><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M10 20v-6h4v6"/></svg>`;
const PREV_ICO = `<svg ${SW}><path d="m15 5-7 7 7 7"/></svg>`;
const NEXT_ICO = `<svg ${SW}><path d="m9 5 7 7-7 7"/></svg>`;
const X_ICO = `<svg ${SW}><path d="M6 6l12 12"/><path d="M18 6 6 18"/></svg>`;

// Anything that drags or pans SIDEWAYS on its own: a one-finger swipe that starts on one of these is the widget's.
const OWNS_SIDEWAYS = 'input[type="range"],[role="slider"],canvas,video,iframe,[data-hpan],[contenteditable="true"],'
  + '[draggable="true"],.leaflet-container,.maplibregl-map,.mapboxgl-map,.gm-style';

function injectStyles() {
  if (document.getElementById("zm-deck-css")) return;
  const s = document.createElement("style");
  s.id = "zm-deck-css";
  s.textContent = `
  .zm-deck{position:fixed;left:0;right:0;top:0;bottom:0;z-index:12;overflow:hidden;pointer-events:none}
  /* A CARD IS THE SCREEN. Full bleed, minus the dock at the bottom and the notch at the top. --dock-h and the
     safe-area insets are the only geometry in this shell — everything else is flow layout, because there is
     nothing to place: there is one card and it is the whole viewport. The bottom is the dock's TOP edge, safe area
     included, so the bar never covers a card's last line and nothing pads for it twice. */
  .zm-card,.zm-home{position:absolute;inset:0;bottom:calc(var(--dock-h) + env(safe-area-inset-bottom));pointer-events:auto;
    display:flex;flex-direction:column;background:var(--hb-bg);opacity:0;transform:translateX(0);visibility:hidden;
    transition:opacity ${CARD_ANIM_MS}ms ease, transform ${CARD_ANIM_MS}ms cubic-bezier(.22,.9,.3,1)}
  .zm-card.live,.zm-home.live{opacity:1;visibility:visible}
  .zm-card.enter-l,.zm-home.enter-l{transform:translateX(-14%)} .zm-card.enter-r,.zm-home.enter-r{transform:translateX(14%)}
  /* THE TOP BAR: ⌂ home · ‹ · the app's name with k/n · › · ×. Host chrome, 44px targets, under the notch via the
     safe area so the title is never eaten by the status bar. The arrows show only with two or more cards. */
  .zm-head{flex:0 0 auto;display:flex;align-items:center;gap:0;padding:calc(env(safe-area-inset-top) + 2px) 4px 2px;
    border-bottom:1px solid var(--hb-line);background:var(--hb-bg-soft)}
  .zm-hb{flex:0 0 auto;width:44px;height:44px;padding:0;border:none;border-radius:12px;background:transparent;
    color:var(--hb-muted);display:flex;align-items:center;justify-content:center;transition:background .12s,opacity .12s}
  .zm-hb svg{width:22px;height:22px}
  .zm-hb:active{background:var(--hb-bubble)}
  .zm-hb[disabled]{opacity:.25}
  .zm-nav{width:36px}
  .zm-nav.hide{display:none}
  .zm-ttl{flex:1 1 auto;min-width:0;min-height:44px;padding:0 4px;border:none;background:transparent;
    display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;color:var(--hb-ink)}
  .zm-title{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
    font:600 15px/1.25 var(--sans);color:var(--hb-ink)}
  /* k/n under the name — hidden with one card: "1/1" invites a tap that shows a list of one, which reads as broken. */
  .zm-count{display:none;font:600 10.5px/1 var(--sans);letter-spacing:.08em;color:var(--hb-muted-2)}
  .zm-count.show{display:block}
  /* THE SCROLLER is a wrapper around the widget's own div, never the widget div itself: a widget.js does
     el.className="…" and would wipe any class we put on its root (same lesson as the desktop host). */
  .zm-scroll{flex:1 1 auto;min-height:0;overflow:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;
    display:flex;flex-direction:column}
  /* CONTENT STARTS AT THE TOP, AND EVERY CARD IS THE SAME BOX (V2-573, operator: «show widgets on top of the
     screen, aligned, try to use fixed sizes to all. on top widgets will have tabs if needed»).
     Until 2026-09-04 this was margin-block:auto, which VERTICALLY CENTRED anything shorter than the screen so a
     clock floated in the middle of the phone. Centring one card at a time looks deliberate; PAGING between cards
     that each centre their own content does not — the header stays put and the body jumps up and down under it,
     and a widget whose own tabs are its first row (results, mensajería) hides them in the middle of the screen
     instead of directly under the title, where a tab strip is read. So: top-aligned, one uniform box.
     min-height:100% is what makes the box FIXED rather than merely top-aligned: without it, a short widget's
     background ends where its content does and the deck shows cards of visibly different heights while swiping.
     Targeted STRUCTURALLY (.zm-scroll > *) and not by .zm-body, because a widget.js does el.className="..." on
     the root it is handed and WIPES our class. A rule keyed to .zm-body therefore stops applying for exactly the
     widgets that style themselves, which is most of them: verified live, querySelector('.zm-body') found nothing
     once the clock had rendered, so this padding was already dead. The bottom padding clears the pips. */
  .zm-scroll > *{padding:12px 12px 40px;margin-block:0;min-height:100%;box-sizing:border-box}
  .zm-load{margin:auto;width:64px;height:64px;border-radius:50%;
    background:conic-gradient(from 0deg,var(--hb-accent),var(--hb-accent2),rgba(61,111,224,0) 78%);
    -webkit-mask:radial-gradient(farthest-side,transparent 58%,#000 60%);mask:radial-gradient(farthest-side,transparent 58%,#000 60%);
    animation:zmspin 1.05s linear infinite}
  @keyframes zmspin{to{transform:rotate(360deg)}}
  .zm-card.loading .zm-scroll{display:flex;align-items:center;justify-content:center}
  /* PAGE PIPS — the deck's position indicator, and a CONTROL: the first pip is the home, then one per card, each a
     26px button that jumps there. They sit ABOVE the dock on purpose: at bottom:6px they were 100% hidden UNDER the
     fixed dock — the only always-visible "there are more cards" signal did not exist on screen. Found by measuring
     geometry, not by reading (the unpainted-orb lesson again). pointer-events live on the BUTTONS, never the row:
     the row spans the full width and would eat taps meant for the widget under it. */
  .zm-pips{position:absolute;left:0;right:0;bottom:calc(var(--dock-h) + env(safe-area-inset-bottom) + 3px);
    display:flex;justify-content:center;pointer-events:none;z-index:4}
  .zm-pip{pointer-events:auto;width:26px;height:26px;border:none;background:transparent;padding:0;margin:0;
    display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--hb-neutral)}
  .zm-pip::before{content:"";width:6px;height:6px;border-radius:3px;background:var(--hb-neutral);
    transition:background .2s,width .2s,box-shadow .2s}
  .zm-pip.on::before{width:18px;background:var(--hb-accent)}
  .zm-pip.home::before{display:none}
  .zm-pip.home svg{width:13px;height:13px;stroke-width:2.4}
  .zm-pip.home.on{color:var(--hb-accent)}
  /* A hidden card that is PRODUCING (music playing behind the front card — the V2-092 runtime contract)
     announces itself on its pip: sound with no visible source reads as a haunted phone, not as a feature. */
  .zm-pip.prod::before{background:var(--hb-accent2);box-shadow:0 0 6px var(--hb-accent2)}
  .zm-pip.on.prod::before{background:var(--hb-accent)}
  /* THE HOME — the launcher. One tile per open card: a monogram on the app's own colour, its LIVE title under it
     (the same source the top bar paints), a ♪ on the one producing sound, the current one ringed, an × to close.
     With nothing open it is the resting state of the shell, and says what to do with the orb. */
  .zm-home .zm-head{justify-content:center}
  .zm-hall{flex:0 0 auto;min-height:36px;padding:0 12px;border:1px solid var(--hb-line);border-radius:10px;
    background:var(--hb-bubble);color:var(--hb-muted);font:600 12px var(--sans);margin-right:6px}
  .zm-hall.hide{display:none}
  .zm-hgrid{flex:1 1 auto;min-height:0;overflow:auto;-webkit-overflow-scrolling:touch;
    display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:14px 6px;align-content:start;
    padding:20px 12px 60px}
  .zm-hgrid.hide{display:none}
  .zm-tile{position:relative;display:flex;flex-direction:column;align-items:center;gap:8px;min-height:44px;
    padding:8px 4px 6px;border:none;border-radius:16px;background:transparent;color:var(--hb-ink)}
  .zm-tile:active{background:var(--hb-bubble)}
  .zm-tic{position:relative;width:62px;height:62px;border-radius:17px;display:flex;align-items:center;justify-content:center;
    font:700 26px/1 var(--sans);color:#fff;background:var(--tile,var(--hb-accent));
    box-shadow:inset 0 -14px 22px rgba(0,0,0,.18),0 2px 8px rgba(0,0,0,.25)}
  .zm-tile.cur .zm-tic{box-shadow:inset 0 -14px 22px rgba(0,0,0,.18),0 0 0 3px var(--hb-bg),0 0 0 5px var(--hb-accent)}
  .zm-tn{max-width:100%;font:500 12px/1.25 var(--sans);text-align:center;overflow:hidden;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;word-break:break-word}
  .zm-tprod{position:absolute;right:-5px;bottom:-5px;width:22px;height:22px;border-radius:11px;background:var(--hb-accent2);
    color:#fff;font:700 12px/22px var(--sans);font-style:normal;text-align:center;box-shadow:0 0 0 2px var(--hb-bg)}
  .zm-tx{position:absolute;top:-4px;right:calc(50% - 50px);width:40px;height:40px;padding:0;border:none;background:transparent;
    display:flex;align-items:flex-start;justify-content:flex-end}
  .zm-tx i{width:22px;height:22px;border-radius:11px;background:var(--hb-bg-soft);border:1px solid var(--hb-line);
    color:var(--hb-muted);font:600 12px/20px var(--sans);font-style:normal;text-align:center}
  /* CONFIRM overlay (irreversible action): identical semantics to the desktop's, sized for a thumb. */
  .zm-confirm{position:absolute;inset:0;z-index:5;display:flex;flex-direction:column;align-items:center;justify-content:center;
    gap:16px;padding:24px;background:var(--hb-bg-a);backdrop-filter:blur(8px);text-align:center}
  .zm-confirm p{margin:0;font:500 16px/1.45 var(--sans);color:var(--hb-ink)}
  .zm-confirm div{display:flex;gap:12px}
  .zm-confirm button{min-width:104px;min-height:46px;border:none;border-radius:12px;font:600 15px var(--sans)}
  .zm-yes{background:var(--hb-risk);color:#fff} .zm-no{background:var(--hb-bubble);color:var(--hb-ink)}
  .zm-err{padding:20px;font:14px/1.5 var(--sans);color:var(--hb-muted)}
  /* THE EMPTY HOME is not an error state — it is the resting state of this shell. Nothing is open, the orb is
     listening, and the screen says what to do with it. */
  .zm-empty{flex:1 1 auto;display:none;flex-direction:column;align-items:center;justify-content:center;gap:10px;
    padding:32px 32px 80px;text-align:center}
  .zm-empty.on{display:flex}
  .zm-empty h2{margin:0;font:600 19px/1.3 var(--sans);color:var(--hb-ink)}
  .zm-empty p{margin:0;max-width:34ch;font:14px/1.55 var(--sans);color:var(--hb-muted)}`;
  document.head.appendChild(s);
}

// A stable colour per app, from its id: the same app wears the same tile on every phone and after every reload.
function tileHue(base) {
  let h = 0;
  for (const ch of String(base || "")) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % 360;
}

export class Deck {
  constructor(stage) {
    injectStyles();
    this.stage = stage;
    this.stage.classList.add("zm-deck");
    this.cards = new Map();     // id -> {card, body, scroll, titleEl, q, base, _mod, _ctx, _dataSig}
    this.order = [];            // deck order, left to right
    this.at = -1;               // index of the visible card (-1 = the HOME)
    this._running = true;
    this._meta = null; this._ids = null; this._registry = null; this._ver = {};
    this._openTimer = 0;
    this._empty = null;
    this._pips = null;
    this._runtime = {};         // base -> active_when clauses (V2-092 runtime contract), null = declares none
    this._home = null;
    this._wireGestures();
    this._mountHome();
  }

  // ── the host contract, part 1: state the brain and main.js read ───────────────────────────────────────────
  setRunning(on) { this._running = !!on; }
  has(id) { return this.cards.has(id); }
  list() { return [...this.order]; }
  capabilities() { return { open: this.list(), canDrag: false, fullscreenAlways: true, paging: "one-finger", home: true }; }

  // ── the host contract, part 2: showing ───────────────────────────────────────────────────────────────────
  // V2-807 T-15 — same contract as the desktop host: every show/close names its cause (`by`), "hand" for a
  // gesture of the operator and anything else for code. The causes ride the next canvas report, and only
  // "hand" keeps the operator's provenance on the server. Unnamed = "code".
  _noteBy(id, by) { const b = String(id || "").split("::")[0].trim().toLowerCase(); if (b) (this._by || (this._by = {}))[b] = String(by || "code"); }
  async show(rawId, { q = "", data: providedData = null, background = false, by = "code" } = {}) {
    this._noteBy(rawId, this._restoring ? "restore" : by);
    // `background` (worker-commissioned shows, see app/services/sse.js): the card is mounted and
    // queued in the deck, but the visible card stays where the operator left it — same rule as
    // desktop, where background work opens beside, never over. Session 6d19df41.
    let baseId, id, wq;
    if (rawId && String(rawId).includes("::")) { const p = String(rawId).split("::"); baseId = p[0]; id = rawId; wq = p[1] || q; }
    else { baseId = await this._resolve(rawId); id = baseId; wq = q; }
    q = wq;
    // A widget the desktop would put in the activity rail above the orb (a transient/process widget) has no rail
    // here — the dock is where the orb lives. It becomes a normal card: on a phone, "what I am doing right now" IS
    // the thing you want the whole screen for.
    let w = this.cards.get(id);
    const fresh = !w;
    if (fresh && !this._restoring) _screens().then((m) => m.claimIfOneScreen(id)).catch(() => {});   // V2-792: a video opened here plays only here
    if (fresh) {
      w = this._buildCard(id, baseId, q);
      this.cards.set(id, w);
      this.order.push(id);
    }
    if (!background) this._goTo(this.order.indexOf(id), 0);
    else this._paint();                                           // the home and the pips learn about it
    if (!fresh && providedData === null && q === w.q) return;   // already up, same query, no pushed data → just surface it
    w.q = q;
    await this._load(w, baseId, q, providedData, fresh);
  }

  close(id, { by = "code" } = {}) {
    this._noteBy(id, by);
    const w = this.cards.get(id); if (!w) return;
    const i = this.order.indexOf(id);
    try { w.card.classList.remove("live"); } catch (_) {}
    setTimeout(() => { try { w.card.remove(); } catch (_) {} }, CARD_ANIM_MS);
    this.cards.delete(id);
    if (i >= 0) this.order.splice(i, 1);
    // Land on the card that took its place, or the new last one; the home when the deck went empty — and stay on
    // the home if that is where the close was done from (its × tiles).
    if (this.at === -1) this._paint(); else this._goTo(Math.min(i, this.order.length - 1), 0);
    this._persist();
  }

  closeAll({ by = "code" } = {}) { for (const id of [...this.order]) this.close(id, { by }); }

  onDeleted(id) { this._ids = null; this._meta = null; this.close(id); }

  // "Put it on the left" has no spatial meaning in a deck of one-at-a-time cards, so it is honoured as the thing
  // it actually means here: REORDER. left/before → one position earlier, right/after → one later. This satisfies
  // the contract without pretending there is a canvas.
  move(id, where) {
    const i = this.order.indexOf(id); if (i < 0) return;
    const w = String(where || "").toLowerCase();
    const back = /izq|left|atr|before|prev|anter/.test(w);
    const j = Math.max(0, Math.min(this.order.length - 1, back ? i - 1 : i + 1));
    if (j === i) return;
    this.order.splice(i, 1); this.order.splice(j, 0, id);
    this._goTo(j, 0);
    this._persist();
  }

  // Size is not the operator's to choose here: a card IS the screen. Accepted and ignored, deliberately and
  // visibly (a silent no-op in a contract method is how a shell starts lying about what it did).
  resize(id) { return { ok: false, reason: "mobile: every card is full screen" }; }

  // Already full screen. The contract method exists so «put it full screen» resolves to something true:
  // bring that card to the front.
  fullscreen(id) { const i = this.order.indexOf(id); if (i >= 0) this._goTo(i, 0); }
  // V2-635 — the canvas `minimize` order («minimise those while you work», «go to the home»): on the phone the one
  // honest step down from a full-screen card is the HOME — the card stays open, as a tile, and stops covering the
  // screen. Native fullscreen, if the browser is in it, is left as well.
  shrink(_id) { if (document.fullscreenElement) document.exitFullscreen?.(); this.home(); }

  // Desktop aligns its grid here (V2-464 showcase). On mobile there is no grid — one card fills the screen —
  // so an aligned deck is the deck it already is. Kept explicit so the shared bridges' contract stays whole.
  arrange() {}

  async refreshData(id) {
    const w = this.cards.get(id); if (!w || !w._mod) return;
    try {
      const data = await fetch(`/widgets/${w.base}/data` + (w.q ? `?q=${encodeURIComponent(w.q)}` : ""), { cache: "no-store" }).then(r => r.json());
      const sig = JSON.stringify(data);
      if (sig === w._dataSig) return;                 // nothing changed → no re-render, no flicker
      w._dataSig = sig;
      w._data = data;
      w._mod.render(w.body, data, w._ctx);
      this._applyTitle(w, data);
      this._paint();                                  // fresh data can flip the producing badge (V2-092)
    } catch (_) { /* a failed refresh leaves the last good render on screen, which is the honest fallback */ }
  }

  // V2-613 — mirrors desktop.js's relanguage(): a language switch re-renders every open card's cached data
  // through `ctx.t`, without a re-fetch. `w._data` is already cached by every load path on this host.
  relanguage() {
    for (const w of this.cards.values()) {
      if (!w._mod || w._data == null) continue;
      try { w._mod.render(w.body, w._data, w._ctx); } catch (_) {}
    }
    this._paint();                                    // the home's own labels follow the language too
  }

  // A name or alias changed (SSE `widget/alias`, V2-082) → drop both caches and repaint every card header.
  async refreshRegistry() {
    this._meta = null; this._ids = null; this._registry = null;
    await this._catalog();
    try {
      const r = await fetch("/widgets/registry").then(r => r.json());
      this._registry = {}; (r.registry || []).forEach(e => { this._registry[e.id] = e; });
    } catch (_) { this._registry = this._registry || {}; }
    for (const w of this.cards.values()) this._applyTitle(w, null);
    this._paint();
  }

  showConfirm(id, { question = "" } = {}) {
    const w = this.cards.get(id); if (!w) return;
    this.hideConfirm(id);
    const ov = document.createElement("div"); ov.className = "zm-confirm";
    const p = document.createElement("p"); p.textContent = question || tr("desktop.confirm_default");
    const row = document.createElement("div");
    const yes = document.createElement("button"); yes.className = "zm-yes"; yes.textContent = tr("common.yes");
    const no = document.createElement("button"); no.className = "zm-no"; no.textContent = tr("common.no");
    yes.onclick = () => { this.hideConfirm(id); this._confirmReply(w.base, true); };
    no.onclick = () => { this.hideConfirm(id); this._confirmReply(w.base, false); };
    row.append(yes, no); ov.append(p, row); w.card.appendChild(ov); w._confirm = ov;
    this._goTo(this.order.indexOf(id), 0);            // a question the operator cannot see is not a question
  }

  hideConfirm(id) { const w = this.cards.get(id); if (w && w._confirm) { w._confirm.remove(); w._confirm = null; } }

  async createWidget(id, spec = "") {
    const rid = await this._resolve(id);
    const meta = await this._catalog();
    if (meta && meta[rid]) return this.show(rid, { q: spec });
    const w = this._buildCard(rid, rid, spec); this.cards.set(rid, w); this.order.push(rid);
    this._goTo(this.order.indexOf(rid), 0);
    w.body.innerHTML = `<div class="zm-err">${tr("desktop.creating")}</div>`;
    try {
      const r = await fetch("/widgets/generate", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: rid, spec }) }).then(r => r.json());
      this._ids = null; this._meta = null;
      if (r && r.ok) { this.close(rid); await this.show(r.id || rid, { q: spec }); }
      else this._mountError(w, rid, (r && r.error) || tr("desktop.generate_failed"));
    } catch (e) { this._mountError(w, rid, String((e && e.message) || e)); }
  }

  async modifyWidget(id, change = "") {
    const rid = await this._resolve(id);
    try {
      await fetch("/widgets/modify", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: rid, change }) }).then(r => r.json());
      this._ver[rid] = Date.now();                    // bust the module cache so the EDITED widget.js is the one that loads
      this._ids = null; this._meta = null;
      if (this.cards.has(rid)) { this.close(rid); await this.show(rid); }
    } catch (_) { /* the backend reports its own failure through SSE; nothing to invent here */ }
  }

  // Report the OPEN cards to memory STATE (POST /api/canvas/state) so they travel in the brain's prompt — that is
  // what makes «close the music one» work without asking which one. Called by session-lk.js on (re)connect and
  // by _persist(). Debounced, because _persist fires in bursts while a deck is being restored. No `layout` key:
  // there is no geometry in a deck, and sending a fake one would poison the desktop's safety net for the same
  // account (the server keeps ONE last-known layout per install).
  _reportOpen() {
    clearTimeout(this._openTimer);
    this._openTimer = setTimeout(async () => {
      const dev = await _device();
      const by = this._by || {}; this._by = {};        // V2-807 T-15: the causes of the changes in this report
      try {
        fetch("/api/canvas/state", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ open: this.list(), dev, by }) });
      } catch (_) {}
    }, 250);
  }

  // ── paging: home ← card 1 ← … ← card n, no wrap-around ─────────────────────────────────────────────────────
  home() { this._goTo(-1, 1); }
  next() { if (this.at < this.order.length - 1) this._goTo(this.at + 1, -1); }
  prev() { if (this.at > -1) this._goTo(this.at - 1, 1); }
  // The name the k/n chip used to open a bottom-sheet switcher under; the home IS the switcher now.
  openSwitcher() { this.home(); }

  _goTo(i, dir) {
    i = Math.max(-1, Math.min(this.order.length - 1, i));
    if (i === this.at) { this._paint(); return; }
    if (i === -1 && this.at >= 0) this._lastId = this.order[this.at];   // the home rings the card we came from
    this.at = i;
    const el = i < 0 ? this._home : (this.cards.get(this.order[i]) || {}).card;
    if (el) {
      // Enter from the side the finger came FROM, so the motion matches the gesture instead of contradicting it.
      el.classList.remove("enter-l", "enter-r");
      if (dir) el.classList.add(dir < 0 ? "enter-r" : "enter-l");
      requestAnimationFrame(() => { el.classList.remove("enter-l", "enter-r"); });
    }
    this._paint();
  }

  _paint() {
    const n = this.order.length;
    this.order.forEach((id, k) => {
      const w = this.cards.get(id); if (!w) return;
      // HIDDEN, never unmounted: a widget that produces (music, a video) keeps producing behind the front card —
      // the global stop (V2-092) is what silences it, not paging away from it.
      w.card.classList.toggle("live", k === this.at);
      w.card.setAttribute("aria-hidden", k === this.at ? "false" : "true");
      if (w.countEl) {
        w.countEl.textContent = n > 1 ? `${k + 1}/${n}` : "";
        w.countEl.classList.toggle("show", n > 1);
      }
      if (w.prevEl) { w.prevEl.classList.toggle("hide", n < 2); }
      if (w.nextEl) { w.nextEl.classList.toggle("hide", n < 2); w.nextEl.disabled = k >= n - 1; }
    });
    if (this._home) {
      this._home.classList.toggle("live", this.at === -1);
      this._home.setAttribute("aria-hidden", this.at === -1 ? "false" : "true");
      this._renderHome();
    }
    if (this._pips) {
      this._pips.innerHTML = "";
      if (n >= 1) {
        const hp = document.createElement("button");
        hp.className = "zm-pip home" + (this.at === -1 ? " on" : "");
        hp.innerHTML = HOME_ICO;
        hp.setAttribute("aria-label", tr("mobile.home"));
        hp.onclick = () => this.home();
        this._pips.appendChild(hp);
        this.order.forEach((id, k) => {
          const w = this.cards.get(id);
          const d = document.createElement("button");
          d.className = "zm-pip" + (k === this.at ? " on" : "") + (w && this._producing(w) ? " prod" : "");
          d.setAttribute("aria-label", (w && w.titleEl.textContent) || id);
          d.onclick = () => this._goTo(k, 0);
          this._pips.appendChild(d);
        });
      }
    }
    if (this._empty) this._empty.classList.toggle("on", n === 0);
  }

  // ── the home: the launcher of what is open ────────────────────────────────────────────────────────────────
  _mountHome() {
    const home = document.createElement("div"); home.className = "zm-home"; home.dataset.wid = "";
    const head = document.createElement("div"); head.className = "zm-head";
    const ttl = document.createElement("div"); ttl.className = "zm-ttl";
    const title = document.createElement("div"); title.className = "zm-title";
    const count = document.createElement("div"); count.className = "zm-count";
    ttl.append(title, count);
    const all = document.createElement("button"); all.className = "zm-hall hide";
    all.onclick = () => this.closeAll({ by: "hand" });
    const spacer = document.createElement("div"); spacer.className = "zm-hb"; spacer.style.visibility = "hidden";
    head.append(spacer, ttl, all);
    const grid = document.createElement("div"); grid.className = "zm-hgrid";
    const e = document.createElement("div"); e.className = "zm-empty on";
    const h = document.createElement("h2");
    const p = document.createElement("p");
    // REACTIVE, not a one-off assignment. This runs at Deck construction and `initI18n()` fetches the bundle
    // ASYNCHRONOUSLY, so at this instant `tr()` legitimately has nothing and returns the KEY itself
    // (core/i18n.js: "visible = needs a string"). A plain textContent= froze that key on screen forever — it
    // showed as a literal "mobile.empty_title" in a phone-sized browser render. `t()` is a reactive read, so an
    // effect repaints the moment the bundle lands, and again if the operator switches language.
    createEffect(() => { h.textContent = tr("mobile.empty_title"); });
    createEffect(() => { p.textContent = tr("mobile.empty_hint"); });
    createEffect(() => { title.textContent = tr("mobile.home"); });
    createEffect(() => { all.textContent = tr("mobile.close_all"); });
    e.append(h, p);
    home.append(head, grid, e);
    this.stage.appendChild(home);
    this._home = home; this._hgrid = grid; this._hcount = count; this._hall = all; this._empty = e;
    const pips = document.createElement("div"); pips.className = "zm-pips";
    this.stage.appendChild(pips); this._pips = pips;
    this._paint();
  }

  _renderHome() {
    const g = this._hgrid; if (!g) return;
    const n = this.order.length;
    g.classList.toggle("hide", n === 0);
    if (this._hall) this._hall.classList.toggle("hide", n === 0);
    if (this._hcount) {
      this._hcount.textContent = n ? tr("mobile.home_count", { n }) : "";
      this._hcount.classList.toggle("show", n > 0);
    }
    g.textContent = "";
    this.order.forEach((id, k) => {
      const w = this.cards.get(id); if (!w) return;
      const meta = this._meta && this._meta[w.base];
      const reg = this._registry && this._registry[w.base];
      const appName = String((reg && reg.name) || (meta && (meta.name || meta.title)) || w.base);
      const tile = document.createElement("button");
      const cur = this.at === -1 ? id === this._lastId : k === this.at;
      tile.className = "zm-tile" + (cur ? " cur" : "");
      tile.dataset.wid = id;
      tile.style.setProperty("--tile", `hsl(${tileHue(w.base)} 46% 46%)`);
      const ic = document.createElement("span"); ic.className = "zm-tic";
      ic.textContent = [...appName.trim()][0] ? [...appName.trim()][0].toUpperCase() : "·";
      if (this._producing(w)) {
        const b = document.createElement("i"); b.className = "zm-tprod"; b.textContent = "♪";
        b.title = tr("mobile.producing");
        ic.appendChild(b);
      }
      const nm = document.createElement("span"); nm.className = "zm-tn";
      nm.textContent = w.titleEl.textContent || appName;      // the LIVE title, same source the top bar paints
      tile.append(ic, nm);
      tile.setAttribute("aria-label", nm.textContent);
      tile.onclick = () => this._goTo(k, 0);
      const x = document.createElement("button"); x.className = "zm-tx";
      x.setAttribute("aria-label", tr("desktop.close") + " · " + nm.textContent);
      const xi = document.createElement("i"); xi.textContent = "×"; x.appendChild(xi);
      x.onclick = (ev) => { ev.stopPropagation(); this.close(id, { by: "hand" }); };
      const cell = document.createElement("div"); cell.style.position = "relative";
      cell.append(tile, x);
      g.appendChild(cell);
    });
  }

  // ── "is this card PRODUCING right now?" — V2-092's runtime contract, read the way the server reads it ─────
  async _runtimeFor(base) {
    if (base in this._runtime) return;
    this._runtime[base] = null;                              // claimed: one manifest fetch per base, ever
    try {
      const man = await fetch(`/widgets/${base}/manifest`).then((r) => (r.ok ? r.json() : null));
      const aw = man && man.runtime && man.runtime.active_when;
      const clauses = Array.isArray(aw) ? aw : (aw && typeof aw === "object" ? [aw] : []);
      if (clauses.length) { this._runtime[base] = clauses; this._paint(); }
    } catch (_) { /* no runtime declared or unreachable → never marked producing, which is the safe reading */ }
  }
  // Mirrors widgets/producers.py::is_producing EXACTLY — `true`/`false` compare by TRUTH (a videoId is a
  // string), anything else by text, degraded data (`error`) never produces. Diverging from the server here
  // would make the phone claim something plays that the global ⏻ does not know about, or the reverse.
  _producing(w) {
    const clauses = (w && this._runtime[w.base]) || null;
    const d = w && w._data;
    if (!clauses || !clauses.length || !d || typeof d !== "object" || d.error) return false;
    const dig = (o, path) => {
      let c = o;
      for (const part of String(path).split(".")) { if (!c || typeof c !== "object") return undefined; c = c[part]; }
      return c;
    };
    return clauses.some((cond) => Object.entries(cond || {}).every(([path, want]) => {
      const got = dig(d, path);
      if (want === true) return !!got;
      if (want === false) return !got;
      return String(got) === String(want);
    }));
  }

  // Does a one-finger swipe that started on `el` belong to the widget? Yes when something between the finger and
  // the card scrolls or drags SIDEWAYS on its own — a tab strip, a thumbnail rail, a map, a slider, a canvas. The
  // card's own scroller is vertical and is where the walk stops: the top bar and the home never own a swipe.
  _ownsSideways(el) {
    for (let n = el; n && n !== this.stage; n = n.parentElement) {
      if (n.classList && (n.classList.contains("zm-scroll") || n.classList.contains("zm-head"))) return false;
      if (n.matches && n.matches(OWNS_SIDEWAYS)) return true;
      try {
        const cs = getComputedStyle(n);
        if (/auto|scroll/.test(cs.overflowX) && n.scrollWidth > n.clientWidth + 2) return true;
      } catch (_) { /* not an element */ }
    }
    return false;
  }

  // PAGING. Tracked on the STAGE in the capture phase so a widget's own scroller cannot swallow the gesture, and
  // never preventDefault()ed, which is what keeps every scrollable widget usable.
  //
  //   ONE finger (2026-10-26, operator: «tiene que ser fácil movernos con un dedo a derecha e izquierda»): a swipe
  //   that is clearly sideways pages, unless it began on something that pans sideways on its own (`_ownsSideways`)
  //   — a swipe from the screen's EDGE pages regardless, so a map card is never a trap. A finger that commits to
  //   going down first is the widget's for the rest of the gesture.
  //   TWO OR THREE fingers page as before (V2-573, operator: «2 or 3 fingers, right and left»): three is iOS muscle
  //   memory and what a two-finger swipe becomes when a thumb rests on the edge. The centroid is computed over ALL
  //   active touches and re-baselined when the count changes mid-gesture, or the jump would read as a page.
  _wireGestures() {
    let x0 = 0, y0 = 0, tracking = false, fingers = 0, vertical = false;
    const PAGING_TOUCHES = (n) => n === 2 || n === 3;
    const mid = (e) => {
      let x = 0, y = 0;
      for (let i = 0; i < e.touches.length; i++) { x += e.touches[i].clientX; y += e.touches[i].clientY; }
      return { x: x / e.touches.length, y: y / e.touches.length };
    };
    this.stage.addEventListener("touchstart", (e) => {
      const n = e.touches.length;
      if (n === 1) {
        const t = e.touches[0]; x0 = t.clientX; y0 = t.clientY; fingers = 1; vertical = false;
        const edge = x0 <= EDGE_PX || x0 >= window.innerWidth - EDGE_PX;
        tracking = edge || !this._ownsSideways(e.target);
        return;
      }
      if (!PAGING_TOUCHES(n)) { tracking = false; return; }
      const m = mid(e); x0 = m.x; y0 = m.y; tracking = true; fingers = n; vertical = false;
    }, { capture: true, passive: true });
    this.stage.addEventListener("touchmove", (e) => {
      if (!tracking) return;
      const n = e.touches.length;
      if (n === 1 && fingers === 1) {
        const t = e.touches[0];
        const dx = t.clientX - x0, dy = t.clientY - y0;
        if (vertical) return;
        if (Math.abs(dy) >= COMMIT_PX && Math.abs(dy) > Math.abs(dx)) { vertical = true; return; }
        if (Math.abs(dx) < SWIPE_PX || Math.abs(dx) < Math.abs(dy) * 2) return;
        tracking = false;
        if (dx < 0) this.next(); else this.prev();
        return;
      }
      if (!PAGING_TOUCHES(n)) return;
      // The count may CHANGE mid-gesture (a third finger lands, or one lifts). Re-baseline instead of dropping
      // the gesture: the centroid jumps when the set of fingers changes, and comparing it against the old origin
      // is what would produce a phantom page — measured as the failure mode of a plain `!==` count check.
      if (n !== fingers) { const m0 = mid(e); x0 = m0.x; y0 = m0.y; fingers = n; return; }
      const m = mid(e);
      // Horizontal intent only, and with a real threshold: a multi-finger PINCH or scroll must not page. 56px of
      // travel and twice as much horizontal as vertical is the line.
      if (Math.abs(m.x - x0) < 56 || Math.abs(m.x - x0) < Math.abs(m.y - y0) * 2) return;
      tracking = false;
      if (m.x < x0) this.next(); else this.prev();
    }, { capture: true, passive: true });
    this.stage.addEventListener("touchend", (e) => { if (!e.touches.length) tracking = false; }, { capture: true, passive: true });
    this.stage.addEventListener("touchcancel", () => { tracking = false; }, { capture: true, passive: true });
  }

  // ── card construction / widget loading ────────────────────────────────────────────────────────────────────
  _buildCard(id, baseId, q) {
    const card = document.createElement("div"); card.className = "zm-card loading"; card.dataset.wid = id;
    const head = document.createElement("div"); head.className = "zm-head";
    const homeB = document.createElement("button"); homeB.className = "zm-hb zm-home-b"; homeB.innerHTML = HOME_ICO;
    homeB.setAttribute("aria-label", tr("mobile.home"));
    homeB.onclick = () => this.home();
    const prevB = document.createElement("button"); prevB.className = "zm-hb zm-nav zm-prev"; prevB.innerHTML = PREV_ICO;
    prevB.setAttribute("aria-label", tr("mobile.prev_card"));
    prevB.onclick = () => this.prev();
    const ttl = document.createElement("button"); ttl.className = "zm-ttl";
    ttl.setAttribute("aria-label", tr("mobile.open_widgets"));
    ttl.onclick = () => this.home();
    const titleEl = document.createElement("div"); titleEl.className = "zm-title"; titleEl.textContent = baseId;
    const countEl = document.createElement("span"); countEl.className = "zm-count";
    ttl.append(titleEl, countEl);
    const nextB = document.createElement("button"); nextB.className = "zm-hb zm-nav zm-next"; nextB.innerHTML = NEXT_ICO;
    nextB.setAttribute("aria-label", tr("mobile.next_card"));
    nextB.onclick = () => this.next();
    const x = document.createElement("button"); x.className = "zm-hb zm-x"; x.innerHTML = X_ICO;
    x.setAttribute("aria-label", tr("desktop.close"));
    x.onclick = () => this.close(id, { by: "hand" });
    head.append(homeB, prevB, ttl, nextB, x);
    const scroll = document.createElement("div"); scroll.className = "zm-scroll";
    const load = document.createElement("div"); load.className = "zm-load";
    const body = document.createElement("div"); body.className = "zm-body";
    scroll.append(load);
    card.append(head, scroll);
    this.stage.appendChild(card);
    requestAnimationFrame(() => card.classList.add("live"));
    return { card, head, body, scroll, load, titleEl, countEl, prevEl: prevB, nextEl: nextB, q, base: baseId, id };
  }

  async _load(w, baseId, q, providedData, fresh) {
    try {
      const data = providedData != null ? providedData
        : await fetch(`/widgets/${baseId}/data` + (q ? `?q=${encodeURIComponent(q)}` : "")).then(r => r.json());
      const mod = await import(`/widgets/${baseId}/widget.js` + (this._ver[baseId] ? `?v=${this._ver[baseId]}` : ""));
      if (data && data.error) return this._mountError(w, baseId, "data: " + data.error);
      w.card.classList.remove("loading");
      if (w.load) { w.load.remove(); w.load = null; }
      if (!w.body.parentNode) w.scroll.appendChild(w.body);
      const deck = this;
      const ctx = {
        action: async (name, payload) => {
          try {
            return await fetch(`/widgets/${baseId}/action`, { method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ action: name, payload: { ...(payload || {}), q } }) }).then(r => r.json());
          } catch (_) { return null; }
        },
        close: (by) => this.close(w.id, { by: by === "hand" ? "hand" : "card" }),
        // V2-613 — same contract as the desktop host: a synchronous, in-memory translation lookup, never a
        // network call from inside widget.js. Already imported at the top of this file for the shell's own chrome.
        t: tr,
        get lang() { return store.lang(); },
        top: () => { try { w.scroll.scrollTop = 0; } catch (_) {} },
        // V2-591 — same contract as the desktop host (a ctx member implemented in one host silently no-ops
        // on the phone): page ≈ 80% of the card's scroller.
        scroll: (where) => { try {
          const sc = w.scroll; if (!sc) return;
          const page = Math.max(120, Math.round(sc.clientHeight * 0.8));
          if (where === "top") sc.scrollTop = 0;
          else if (where === "bottom") sc.scrollTop = sc.scrollHeight;
          else if (where === "up") sc.scrollTop = Math.max(0, sc.scrollTop - page);
          else sc.scrollTop = sc.scrollTop + page;
        } catch (_) {} },
        // The SAME members the desktop card gives (desktop.js): a member one host forgets is a TypeError inside the
        // card the moment it is tapped — seven cards call `openConnector`, and on the phone every one of those taps
        // threw. The phone has no ⚙ Conectores section, so its door says where linking is done.
        openConnector: () => noteSent(tr("mobile.connect_on_computer"), 5000),
        // A file the operator picked in the card: uploaded to the widget's own data dir, same boundary as desktop.
        upload: async (file) => {
          try {
            const fd = new FormData(); fd.append("file", file);
            return await fetch(`/widgets/${baseId}/upload`, { method: "POST", body: fd }).then(r => r.json());
          } catch (_) { return { error: "upload failed" }; }
        },
        // Linking an account from a card (a picker, an OAuth page): the tab is opened INSIDE the tap — one opened
        // after an await is blocked in silence — and pointed at the URL the action returns. The card repaints from
        // the widget's own change notice when the account comes back.
        connect: async (action, payload) => {
          let tab = null;
          try { tab = window.open("", "zaelar_connect_" + baseId); } catch (_) { tab = null; }
          const res = await ctx.action(action, payload || {});
          const url = res && res.ok !== false && res.url;
          if (!url) { try { if (tab) tab.close(); } catch (_) {} return res || { ok: false, error: "no url" }; }
          try { if (tab) tab.location = url; else tab = window.open(url, "zaelar_connect_" + baseId); } catch (_) {}
          return Object.assign({}, res, { blocked: !tab });
        },
        // GETTER, not a copied value: ctx is built once per mount and reused across re-renders, so a snapshot
        // would go stale and a widget that produces would start over a stopped agent (V2-092).
        get running() { return deck._running; },
      };
      // The card header already carries the title, so tell the widget not to draw its own — same marker the
      // desktop host uses, set BEFORE the first render or the first paint ships a duplicated title.
      w.body.dataset.hostTitle = "1";
      mod.render(w.body, data, ctx);
      this._applyTitle(w, data);
      w._dataSig = JSON.stringify(data); w._data = data; w._mod = mod; w._ctx = ctx;
      this._runtimeFor(baseId);                       // lazy, cached: does this widget declare production?
      this._paint();
      this._persist();
    } catch (e) {
      console.error("mobile widget mount failed", w.id, e);
      this._mountError(w, baseId, String((e && e.message) || e));
    }
  }

  // A widget that fails to mount must show a VISIBLE error and REPORT it, never vanish. Same invariant as the
  // desktop host, and for the same reason: a card that silently closes itself is how "I asked four times and
  // nothing happened" happens.
  _mountError(w, baseId, msg) {
    try {
      w.card.classList.remove("loading");
      if (w.load) { w.load.remove(); w.load = null; }
      if (!w.body.parentNode) w.scroll.appendChild(w.body);
      w.body.innerHTML = `<div class="zm-err">${tr("desktop.load_failed")}<br><small style="opacity:.8">`
        + String(msg || "error").replace(/[<>&]/g, "").slice(0, 160) + "</small></div>";
    } catch (_) {}
    try {
      fetch("/api/client-log", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: "mobile widget mount failed", text: (baseId || "?") + " — " + String(msg || "").slice(0, 200) }) });
    } catch (_) {}
  }

  // Title priority: the LIVE task the widget is working on (a sentence beats a label — same call the desktop
  // header makes), then the operator's own name for it (registry, V2-082), then the catalog index, then the id.
  _applyTitle(w, data) {
    const reg = this._registry && this._registry[w.base];
    const meta = this._meta && this._meta[w.base];
    const live = data && (data.title || data.task);
    w.titleEl.textContent = String(live || (reg && reg.name) || (meta && (meta.name || meta.title)) || w.base);
  }

  // The card's Yes/No resolves the PENDING confirmation server-side. Body is `{ok}` and nothing else — the server
  // already knows which action is pending (widgets/confirm.py); sending our own `action` here is how the desktop's
  // equivalent once consumed a confirmation without executing it.
  _confirmReply(baseId, ok) {
    try {
      fetch(`/widgets/${baseId}/confirm`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ok }) });
    } catch (_) {}
  }

  // GET /widgets is the COMPACT catalog INDEX (V2-085): id + four header fields, NOT full manifests. That is all
  // the resolver and the card titles need — asking for `?full=1` here would download megabytes at every startup.
  async _catalog() {
    if (this._meta) return this._meta;
    try {
      const c = await fetch("/widgets").then(r => r.json());
      const ws = c.widgets || [];
      this._ids = ws.map(w => w.id);
      this._meta = {}; ws.forEach(w => { this._meta[w.id] = w; });
    } catch (_) { this._meta = this._meta || {}; this._ids = this._ids || []; }
    return this._meta;
  }

  // The brain does not always emit the EXACT catalog id (it said "agenda-today" for "agenda"). Resolve loosely
  // against the live catalog — exact, then prefix, then contains — and only then ask the server's own resolver.
  // Same ladder as the desktop host, deliberately: two hosts that resolve names differently would answer the same
  // sentence with different widgets.
  async _resolve(rawId) {
    const id = String(rawId || "").trim();
    await this._catalog();
    const ids = this._ids || [];
    if (ids.includes(id)) return id;
    const hit = ids.find(cid => id === cid || id.startsWith(cid + "-") || id.startsWith(cid + "_")
      || id.includes(cid) || cid.includes(id));
    if (hit) return hit;
    try {
      const r = await fetch("/widgets/identify?q=" + encodeURIComponent(id)).then(r => r.json());
      if (r && r.id) return r.id;
    } catch (_) {}
    return id;                                        // unknown → let the data fetch fail VISIBLY rather than guess
  }

  // Which cards are open, so a reload comes back to the same deck. Local only (the desktop persists its own
  // geometry server-side; there is no geometry here, so there is nothing to reconcile).
  _persist() {
    try { localStorage.setItem("zaelar_mobile_deck", JSON.stringify(this.order)); } catch (_) {}
    this._reportOpen();     // the brain's prompt should know what is on screen, on the phone as on the desktop
  }

  async restore() {
    // WIPE EPOCH first (V2-084/4.14): the deck lives in this browser's localStorage, which a server-side reset
    // cannot reach. The server serves an epoch that changes on every reset; newer than ours → start BLANK, like a
    // fresh install. Without this, «reset» leaves cards on the phone that the server no longer knows about.
    try {
      const { epoch } = await fetch("/api/desktop/epoch").then(r => r.json());
      if (epoch && localStorage.getItem("zaelar_mobile_wipe") !== String(epoch)) {
        localStorage.setItem("zaelar_mobile_wipe", String(epoch));
        localStorage.removeItem("zaelar_mobile_deck");
        this._reportOpen();
        return;
      }
    } catch (_) {}
    let ids = [];
    try { ids = JSON.parse(localStorage.getItem("zaelar_mobile_deck") || "[]"); } catch (_) {}
    let items = (Array.isArray(ids) ? ids : []).map((id) => ({ id: String(id || ""), q: "" })).filter((it) => it.id);
    // V2-351, the mobile half (2026-08-29). The desktop got these on 2026-08-26 and this host silently did not,
    // and each one bites HARDER on a phone:
    //   · SERVER FALLBACK — localStorage is per-browser, and a phone IS a new browser: a freshly installed PWA
    //     opened on an empty deck even while the account had a desktop full of work. /api/canvas/layout is the
    //     same endpoint the desktop consults, geometry ignored here (a deck has none).
    //   · LIVE ERRANDS — the sheet/browser card of an errand running RIGHT NOW comes back even if this device
    //     never saved it. That is the start-on-the-computer, follow-on-the-phone story, and it is `srv.live`.
    //   · THE FOSSIL SWEEP — a bare BASE card next to its own instance is the pre-V2-261 ghost: every restore
    //     resurrected an empty «Results» on top of the full sheet. A base card is legitimate ALONE.
    //   · a browser::tN with no live task behind it has nothing to reload (process state, not a sheet).
    let srv = { items: [], live: [] };
    try { srv = (await fetch("/api/canvas/layout?dev=" + encodeURIComponent(await _device())).then((r) => r.json())) || srv; } catch (_) {}
    if (!items.length && Array.isArray(srv.items) && srv.items.length) {
      items = srv.items.map((it) => ({ id: String((it && it.id) || ""), q: String((it && it.q) || "") })).filter((it) => it.id);
    }
    const bases = new Set(items.filter((it) => it.id.includes("::")).map((it) => it.id.split("::", 1)[0]));
    items = items.filter((it) => it.id.includes("::") || !bases.has(it.id));
    const have = new Set(items.map((it) => it.id));
    for (const id of Array.isArray(srv.live) ? srv.live : []) {
      if (id && !have.has(String(id))) { items.push({ id: String(id), q: "" }); have.add(String(id)); }
    }
    const liveSet = new Set((Array.isArray(srv.live) ? srv.live : []).map(String));
    items = items.filter((it) => !(it.id.startsWith("navegador::") && !liveSet.has(it.id)));
    // Capped at 8: a deck is paged one card at a time, so restoring 40 would mount 40 widgets to show one.
    try { items = await (await _screens()).filterRestore(this, items, srv); } catch (_) {}   // V2-792: a video playing on the other screen stays there
    this._restoring = true;
    try { for (const it of items.slice(0, 8)) { try { await this.show(it.id, { q: it.q }); } catch (_) {} } }
    finally { this._restoring = false; }
    this._goTo(this.order.length ? 0 : -1, 0);
  }
}
