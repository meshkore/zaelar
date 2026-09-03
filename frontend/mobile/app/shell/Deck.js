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
//      where ctx = { action(name, payload), close(), top(), get running() }. Four members, none of them about
//      cards or dragging — which is why the ENTIRE widget catalog works here without touching a single widget,
//      including widgets the agent generates tomorrow.
//
// PAGING IS TWO- OR THREE-FINGER, ON PURPOSE (operator: «the two-finger effect», widened 2026-09-04 to «2 or 3
// fingers, right and left»). ONE finger belongs to the WIDGET: scrolling a list, panning a map, dragging a
// slider. If one finger also paged, every scrollable widget would be unusable — you could not scroll without
// changing cards. So a single touch is never intercepted here.
//
// A CARD IS NEVER UNMOUNTED WHILE PAGING, only hidden. A video that keeps playing behind another card is correct;
// re-mounting it on every swipe would cut it off mid-sentence.
// ============================================================================

import { t as tr } from "../../../app/core/i18n.js?v=1";
import { createEffect } from "../../../app/core/reactive.js?v=2";

const CARD_ANIM_MS = 260;

function injectStyles() {
  if (document.getElementById("zm-deck-css")) return;
  const s = document.createElement("style");
  s.id = "zm-deck-css";
  s.textContent = `
  .zm-deck{position:fixed;left:0;right:0;top:0;bottom:0;z-index:12;overflow:hidden;pointer-events:none}
  /* A CARD IS THE SCREEN. Full bleed, minus the dock at the bottom and the notch at the top. --dock-h and the
     safe-area insets are the only geometry in this shell — everything else is flow layout, because there is
     nothing to place: there is one card and it is the whole viewport. */
  .zm-card{position:absolute;inset:0;bottom:var(--dock-h);pointer-events:auto;display:flex;flex-direction:column;
    background:var(--hb-bg);opacity:0;transform:translateX(0);visibility:hidden;
    transition:opacity ${CARD_ANIM_MS}ms ease, transform ${CARD_ANIM_MS}ms cubic-bezier(.22,.9,.3,1)}
  .zm-card.live{opacity:1;visibility:visible}
  .zm-card.enter-l{transform:translateX(-14%)} .zm-card.enter-r{transform:translateX(14%)}
  /* HEADER: the widget's name + a close button. No grip (nothing to drag), no maximize (everything is maximal).
     Sits under the notch via safe-area, so the title is never eaten by the status bar. */
  .zm-head{flex:0 0 auto;display:flex;align-items:center;gap:8px;padding:calc(env(safe-area-inset-top) + 10px) 12px 10px;
    border-bottom:1px solid var(--hb-line);background:var(--hb-bg-soft)}
  .zm-title{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
    font:600 15px/1.25 var(--sans);color:var(--hb-ink)}
  /* The k/n counter is a BUTTON since 2026-08-29: it opens the deck switcher. Hidden with one card — a
     "1/1" chip invites a tap that shows a list of one, which reads as broken. */
  .zm-count{flex:0 0 auto;display:none;align-items:center;min-height:32px;padding:0 10px;border:1px solid var(--hb-line);
    border-radius:9px;background:var(--hb-bubble);color:var(--hb-muted);font:600 11px/1 var(--sans);letter-spacing:.04em}
  .zm-count.show{display:flex}
  .zm-x{flex:0 0 auto;width:34px;height:34px;border:none;border-radius:10px;background:var(--hb-bubble);
    color:var(--hb-muted);font-size:18px;line-height:1}
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
     once the clock had rendered, so this padding was already dead. */
  .zm-scroll > *{padding:12px 12px calc(12px + env(safe-area-inset-bottom));margin-block:0;
    min-height:100%;box-sizing:border-box}
  .zm-load{margin:auto;width:64px;height:64px;border-radius:50%;
    background:conic-gradient(from 0deg,var(--hb-accent),var(--hb-accent2),rgba(61,111,224,0) 78%);
    -webkit-mask:radial-gradient(farthest-side,transparent 58%,#000 60%);mask:radial-gradient(farthest-side,transparent 58%,#000 60%);
    animation:zmspin 1.05s linear infinite}
  @keyframes zmspin{to{transform:rotate(360deg)}}
  .zm-card.loading .zm-scroll{display:flex;align-items:center;justify-content:center}
  /* PAGE PIPS — the deck's position indicator, and a CONTROL: each pip is a 26px button that jumps to its card.
     They sit ABOVE the dock on purpose: at bottom:6px they were 100% hidden UNDER the fixed dock (z-index 60,
     84px + safe-area tall) — the only always-visible "there are more cards" signal did not exist on screen.
     Found by measuring geometry, not by reading (the unpainted-orb lesson again). pointer-events live on the
     BUTTONS, never the row: the row spans the full width and would eat taps meant for the widget under it. */
  .zm-pips{position:absolute;left:0;right:0;bottom:calc(var(--dock-h) + env(safe-area-inset-bottom) + 2px);
    display:flex;justify-content:center;pointer-events:none;z-index:4}
  .zm-pip{pointer-events:auto;width:26px;height:26px;border:none;background:transparent;padding:0;margin:0;
    display:flex;align-items:center;justify-content:center;cursor:pointer}
  .zm-pip::before{content:"";width:6px;height:6px;border-radius:3px;background:var(--hb-neutral);
    transition:background .2s,width .2s,box-shadow .2s}
  .zm-pip.on::before{width:18px;background:var(--hb-accent)}
  /* A hidden card that is PRODUCING (music playing behind the front card — the V2-092 runtime contract)
     announces itself on its pip: sound with no visible source reads as a haunted phone, not as a feature. */
  .zm-pip.prod::before{background:var(--hb-accent2);box-shadow:0 0 6px var(--hb-accent2)}
  .zm-pip.on.prod::before{background:var(--hb-accent)}
  /* THE DECK SWITCHER — the phone's task switcher. Opened from the k/n chip in any card header; lists every
     open card by its LIVE title (the same source the header paints), marks the one producing sound, jumps on
     tap, closes with its x. It stops ABOVE the dock like every sheet in this shell: the mic and the ⏻ must
     stay reachable whatever is open. */
  .zm-switch{position:fixed;left:0;right:0;top:0;bottom:calc(var(--dock-h) + env(safe-area-inset-bottom));
    z-index:66;display:flex;flex-direction:column;justify-content:flex-end;background:var(--hb-bg-a);
    backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);opacity:0;pointer-events:none;transition:opacity .18s}
  .zm-switch.open{opacity:1;pointer-events:auto}
  .zm-swpanel{background:var(--hb-bg-soft);border-top:1px solid var(--hb-line);border-radius:18px 18px 0 0;
    padding:14px 14px 10px;max-height:70%;overflow:auto;transform:translateY(14px);transition:transform .18s}
  .zm-switch.open .zm-swpanel{transform:none}
  .zm-swhead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 2px 10px}
  .zm-swhead b{font:600 15px/1.2 var(--sans);color:var(--hb-ink)}
  .zm-swall{border:none;border-radius:9px;background:var(--hb-bubble);color:var(--hb-muted);
    font:600 12px var(--sans);min-height:34px;padding:0 12px}
  .zm-swrow{display:flex;align-items:center;gap:4px;border:1px solid var(--hb-line);border-radius:12px;
    background:var(--hb-bg);min-height:52px;margin-bottom:8px;padding:0 4px 0 0}
  .zm-swrow.cur{border-color:var(--hb-accent)}
  .zm-swgo{flex:1 1 auto;min-width:0;display:flex;align-items:center;gap:8px;min-height:52px;border:none;
    background:transparent;padding:0 4px 0 14px;text-align:left;font:500 14px/1.3 var(--sans);color:var(--hb-ink)}
  .zm-swgo span{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .zm-swprod{flex:0 0 auto;color:var(--hb-accent2);font-size:14px;font-style:normal}
  .zm-swx{flex:0 0 auto;width:44px;height:44px;border:none;border-radius:10px;background:var(--hb-bubble);
    color:var(--hb-muted);font-size:17px;line-height:1}
  /* CONFIRM overlay (irreversible action): identical semantics to the desktop's, sized for a thumb. */
  .zm-confirm{position:absolute;inset:0;z-index:5;display:flex;flex-direction:column;align-items:center;justify-content:center;
    gap:16px;padding:24px;background:var(--hb-bg-a);backdrop-filter:blur(8px);text-align:center}
  .zm-confirm p{margin:0;font:500 16px/1.45 var(--sans);color:var(--hb-ink)}
  .zm-confirm div{display:flex;gap:12px}
  .zm-confirm button{min-width:104px;min-height:46px;border:none;border-radius:12px;font:600 15px var(--sans)}
  .zm-yes{background:var(--hb-risk);color:#fff} .zm-no{background:var(--hb-bubble);color:var(--hb-ink)}
  .zm-err{padding:20px;font:14px/1.5 var(--sans);color:var(--hb-muted)}
  /* THE EMPTY DECK is not an error state — it is the resting state of this shell. Nothing is open, the orb is
     listening, and the screen says what to do with it. */
  .zm-empty{position:absolute;inset:0;bottom:var(--dock-h);display:flex;flex-direction:column;align-items:center;
    justify-content:center;gap:10px;padding:32px;text-align:center;pointer-events:none;opacity:.001;transition:opacity .3s}
  .zm-empty.on{opacity:1}
  .zm-empty h2{margin:0;font:600 19px/1.3 var(--sans);color:var(--hb-ink)}
  .zm-empty p{margin:0;max-width:34ch;font:14px/1.55 var(--sans);color:var(--hb-muted)}`;
  document.head.appendChild(s);
}

export class Deck {
  constructor(stage) {
    injectStyles();
    this.stage = stage;
    this.stage.classList.add("zm-deck");
    this.cards = new Map();     // id -> {card, body, scroll, titleEl, q, base, _mod, _ctx, _dataSig}
    this.order = [];            // deck order, left to right
    this.at = -1;               // index of the visible card (-1 = empty deck)
    this._running = true;
    this._meta = null; this._ids = null; this._registry = null; this._ver = {};
    this._openTimer = 0;
    this._empty = null;
    this._pips = null;
    this._runtime = {};         // base -> active_when clauses (V2-092 runtime contract), null = declares none
    this._sw = null; this._swPanel = null;
    this._wireGestures();
    this._mountEmpty();
    this._mountSwitch();
  }

  // ── the host contract, part 1: state the brain and main.js read ───────────────────────────────────────────
  setRunning(on) { this._running = !!on; }
  has(id) { return this.cards.has(id); }
  list() { return [...this.order]; }
  capabilities() { return { open: this.list(), canDrag: false, fullscreenAlways: true, paging: "two-finger" }; }

  // ── the host contract, part 2: showing ───────────────────────────────────────────────────────────────────
  async show(rawId, { q = "", data: providedData = null } = {}) {
    let baseId, id, wq;
    if (rawId && String(rawId).includes("::")) { const p = String(rawId).split("::"); baseId = p[0]; id = rawId; wq = p[1] || q; }
    else { baseId = await this._resolve(rawId); id = baseId; wq = q; }
    q = wq;
    // A widget the desktop would put in the activity rail above the orb (a transient/process widget) has no rail
    // here — the dock is where the orb lives and it is 64px tall. It becomes a normal card: on a phone, "what I am
    // doing right now" IS the thing you want the whole screen for.
    let w = this.cards.get(id);
    const fresh = !w;
    if (fresh) {
      w = this._buildCard(id, baseId, q);
      this.cards.set(id, w);
      this.order.push(id);
    }
    this._goTo(this.order.indexOf(id), 0);
    if (!fresh && providedData === null && q === w.q) return;   // already up, same query, no pushed data → just surface it
    w.q = q;
    await this._load(w, baseId, q, providedData, fresh);
  }

  close(id) {
    const w = this.cards.get(id); if (!w) return;
    const i = this.order.indexOf(id);
    try { w.card.classList.remove("live"); } catch (_) {}
    setTimeout(() => { try { w.card.remove(); } catch (_) {} }, CARD_ANIM_MS);
    this.cards.delete(id);
    if (i >= 0) this.order.splice(i, 1);
    // Land on the card that took its place, or the new last one; -1 when the deck went empty.
    this._goTo(Math.min(i, this.order.length - 1), 0);
    this._persist();
  }

  closeAll() { for (const id of [...this.order]) this.close(id); }

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

  // A name or alias changed (SSE `widget/alias`, V2-082) → drop both caches and repaint every card header.
  async refreshRegistry() {
    this._meta = null; this._ids = null; this._registry = null;
    await this._catalog();
    try {
      const r = await fetch("/widgets/registry").then(r => r.json());
      this._registry = {}; (r.registry || []).forEach(e => { this._registry[e.id] = e; });
    } catch (_) { this._registry = this._registry || {}; }
    for (const w of this.cards.values()) this._applyTitle(w, null);
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
      else this._mountError(w, rid, (r && r.error) || "generate failed");
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
    this._openTimer = setTimeout(() => {
      try {
        fetch("/api/canvas/state", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ open: this.list() }) });
      } catch (_) {}
    }, 250);
  }

  // ── paging ────────────────────────────────────────────────────────────────────────────────────────────────
  next() { if (this.order.length > 1) this._goTo((this.at + 1) % this.order.length, -1); }
  prev() { if (this.order.length > 1) this._goTo((this.at - 1 + this.order.length) % this.order.length, 1); }

  _goTo(i, dir) {
    if (this.order.length === 0) { this.at = -1; this._paint(); return; }
    i = Math.max(0, Math.min(this.order.length - 1, i));
    if (i === this.at) { this._paint(); return; }
    this.at = i;
    const w = this.cards.get(this.order[i]);
    if (w) {
      // Enter from the side the finger came FROM, so the motion matches the gesture instead of contradicting it.
      w.card.classList.remove("enter-l", "enter-r");
      if (dir) w.card.classList.add(dir < 0 ? "enter-r" : "enter-l");
      requestAnimationFrame(() => { w.card.classList.remove("enter-l", "enter-r"); });
    }
    this._paint();
  }

  _paint() {
    this.order.forEach((id, k) => {
      const w = this.cards.get(id); if (!w) return;
      // HIDDEN, never unmounted: a widget that produces (music, a video) keeps producing behind the front card —
      // the global stop (V2-092) is what silences it, not paging away from it.
      w.card.classList.toggle("live", k === this.at);
      w.card.setAttribute("aria-hidden", k === this.at ? "false" : "true");
      if (w.countEl) {
        w.countEl.textContent = this.order.length > 1 ? `${k + 1}/${this.order.length}` : "";
        w.countEl.classList.toggle("show", this.order.length > 1);
      }
    });
    if (this._pips) {
      this._pips.innerHTML = "";
      if (this.order.length > 1) this.order.forEach((id, k) => {
        const w = this.cards.get(id);
        const d = document.createElement("button");
        d.className = "zm-pip" + (k === this.at ? " on" : "") + (w && this._producing(w) ? " prod" : "");
        d.setAttribute("aria-label", (w && w.titleEl.textContent) || id);
        d.onclick = () => this._goTo(k, 0);
        this._pips.appendChild(d);
      });
    }
    if (this._empty) this._empty.classList.toggle("on", this.order.length === 0);
    // The switcher mirrors the deck it lists: a close/show/title change repaints it, and an emptied deck
    // dismisses it (a switcher over nothing is a modal with no purpose and no obvious way out).
    if (this._sw && this._sw.classList.contains("open")) {
      if (this.order.length === 0) this.closeSwitcher(); else this._renderSwitch();
    }
  }

  // ── the deck switcher: the phone's task switcher ──────────────────────────────────────────────────────────
  _mountSwitch() {
    const ov = document.createElement("div"); ov.className = "zm-switch";
    ov.addEventListener("click", (e) => { if (e.target === ov) this.closeSwitcher(); });
    const panel = document.createElement("div"); panel.className = "zm-swpanel";
    ov.appendChild(panel);
    // Sibling of the stage, not a child: the stage carries pointer-events:none, which would kill every tap.
    this.stage.parentNode.appendChild(ov);
    this._sw = ov; this._swPanel = panel;
  }
  openSwitcher() {
    if (!this.order.length || !this._sw) return;
    this._renderSwitch();
    this._sw.classList.add("open");
  }
  closeSwitcher() { if (this._sw) this._sw.classList.remove("open"); }
  _renderSwitch() {
    const p = this._swPanel; if (!p) return;
    p.textContent = "";
    const head = document.createElement("div"); head.className = "zm-swhead";
    const title = document.createElement("b"); title.textContent = tr("mobile.open_widgets");
    const all = document.createElement("button"); all.className = "zm-swall";
    all.textContent = tr("mobile.close_all");
    all.onclick = () => { this.closeAll(); this.closeSwitcher(); };
    head.append(title, all); p.appendChild(head);
    this.order.forEach((id, k) => {
      const w = this.cards.get(id); if (!w) return;
      const row = document.createElement("div"); row.className = "zm-swrow" + (k === this.at ? " cur" : "");
      const go = document.createElement("button"); go.className = "zm-swgo";
      const name = document.createElement("span");
      name.textContent = w.titleEl.textContent || w.base;      // the LIVE title, same source the header paints
      go.appendChild(name);
      if (this._producing(w)) {
        const b = document.createElement("i"); b.className = "zm-swprod"; b.textContent = "♪";
        b.title = tr("mobile.producing");
        go.appendChild(b);
      }
      go.onclick = () => { this._goTo(k, 0); this.closeSwitcher(); };
      const x = document.createElement("button"); x.className = "zm-swx"; x.textContent = "×";
      x.setAttribute("aria-label", tr("desktop.close"));
      x.onclick = () => this.close(id);
      row.append(go, x); p.appendChild(row);
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

  // ONE-finger paging on the HEADER only. The header is host chrome — no widget scrolls, pans or drags there —
  // so a single finger is safe to claim, unlike the card body where one finger belongs to the widget (the rule
  // at the top of this file). Same thresholds as the two-finger gesture, for one muscle memory.
  _wireHeadSwipe(head) {
    let x0 = 0, y0 = 0, on = false;
    head.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 1) { on = false; return; }
      x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; on = true;
    }, { passive: true });
    head.addEventListener("touchmove", (e) => {
      if (!on || e.touches.length !== 1) return;
      const dx = e.touches[0].clientX - x0, dy = e.touches[0].clientY - y0;
      if (Math.abs(dx) < 48 || Math.abs(dx) < Math.abs(dy) * 2) return;
      on = false;
      if (dx < 0) this.next(); else this.prev();
    }, { passive: true });
    head.addEventListener("touchend", () => { on = false; }, { passive: true });
  }

  // TWO OR THREE fingers page; one finger is the widget's. Tracked on the STAGE (capture phase) so a widget's own
  // scroller cannot swallow the gesture, but only ever acted on with 2+ touches — a single touch is passed
  // straight through and never preventDefault()ed, which is what keeps every scrollable widget usable.
  //
  // THREE was added on 2026-09-04 at the operator's request («we can switch screens moving mobile screen with 2 or
  // 3 fingers, right and left»), and it is not just a looser count: on iOS a three-finger horizontal swipe is
  // muscle memory from the system's own app switching, and a phone case or a thumb resting on the edge turns an
  // intended two-finger swipe into a three-finger one. Refusing it made the gesture feel unreliable rather than
  // strict. The centroid is computed over ALL active touches, so the threshold means the same thing either way.
  _wireGestures() {
    let x0 = 0, y0 = 0, tracking = false, fingers = 0;
    const PAGING_TOUCHES = (n) => n === 2 || n === 3;
    const mid = (e) => {
      let x = 0, y = 0;
      for (let i = 0; i < e.touches.length; i++) { x += e.touches[i].clientX; y += e.touches[i].clientY; }
      return { x: x / e.touches.length, y: y / e.touches.length };
    };
    this.stage.addEventListener("touchstart", (e) => {
      if (!PAGING_TOUCHES(e.touches.length)) { tracking = false; return; }
      const m = mid(e); x0 = m.x; y0 = m.y; tracking = true; fingers = e.touches.length;
    }, { capture: true, passive: true });
    this.stage.addEventListener("touchmove", (e) => {
      // The count may CHANGE mid-gesture (a third finger lands, or one lifts). Re-baseline instead of dropping
      // the gesture: the centroid jumps when the set of fingers changes, and comparing it against the old origin
      // is what would produce a phantom page — measured as the failure mode of a plain `!==` count check.
      if (!tracking || !PAGING_TOUCHES(e.touches.length)) return;
      if (e.touches.length !== fingers) { const m0 = mid(e); x0 = m0.x; y0 = m0.y; fingers = e.touches.length; return; }
      const m = mid(e);
      // Horizontal intent only, and with a real threshold: a multi-finger PINCH or scroll must not page. 56px of
      // travel and twice as much horizontal as vertical is the line.
      if (Math.abs(m.x - x0) < 56 || Math.abs(m.x - x0) < Math.abs(m.y - y0) * 2) return;
      tracking = false;
      if (m.x < x0) this.next(); else this.prev();
    }, { capture: true, passive: true });
    this.stage.addEventListener("touchend", () => { tracking = false; }, { capture: true, passive: true });
  }

  // ── card construction / widget loading ────────────────────────────────────────────────────────────────────
  _buildCard(id, baseId, q) {
    const card = document.createElement("div"); card.className = "zm-card loading"; card.dataset.wid = id;
    const head = document.createElement("div"); head.className = "zm-head";
    this._wireHeadSwipe(head);
    const titleEl = document.createElement("div"); titleEl.className = "zm-title"; titleEl.textContent = baseId;
    const countEl = document.createElement("button"); countEl.className = "zm-count";
    countEl.setAttribute("aria-label", tr("mobile.open_widgets"));
    countEl.onclick = () => this.openSwitcher();
    const x = document.createElement("button"); x.className = "zm-x"; x.textContent = "×";
    x.setAttribute("aria-label", tr("desktop.close"));
    x.onclick = () => this.close(id);
    head.append(titleEl, countEl, x);
    const scroll = document.createElement("div"); scroll.className = "zm-scroll";
    const load = document.createElement("div"); load.className = "zm-load";
    const body = document.createElement("div"); body.className = "zm-body";
    scroll.append(load);
    card.append(head, scroll);
    this.stage.appendChild(card);
    requestAnimationFrame(() => card.classList.add("live"));
    return { card, head, body, scroll, load, titleEl, countEl, q, base: baseId, id };
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
        close: () => this.close(w.id),
        top: () => { try { w.scroll.scrollTop = 0; } catch (_) {} },
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
    try { srv = (await fetch("/api/canvas/layout").then((r) => r.json())) || srv; } catch (_) {}
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
    for (const it of items.slice(0, 8)) { try { await this.show(it.id, { q: it.q }); } catch (_) {} }
    this._goTo(0, 0);
  }

  _mountEmpty() {
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
    e.append(h, p);
    this.stage.parentNode.insertBefore(e, this.stage);
    this._empty = e;
    const pips = document.createElement("div"); pips.className = "zm-pips";
    this.stage.appendChild(pips); this._pips = pips;
  }
}
