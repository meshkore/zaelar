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
// PAGING IS TWO-FINGER, ON PURPOSE (operator: «el efecto de los dos deditos»). ONE finger belongs to the WIDGET:
// scrolling a list, panning a map, dragging a slider. If one finger also paged, every scrollable widget would be
// unusable — you could not scroll without changing cards. So a single touch is never intercepted here.
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
  .zm-count{flex:0 0 auto;font:600 11px/1 var(--sans);color:var(--hb-muted-2);letter-spacing:.04em}
  .zm-x{flex:0 0 auto;width:34px;height:34px;border:none;border-radius:10px;background:var(--hb-bubble);
    color:var(--hb-muted);font-size:18px;line-height:1}
  /* THE SCROLLER is a wrapper around the widget's own div, never the widget div itself: a widget.js does
     el.className="…" and would wipe any class we put on its root (same lesson as the desktop host). */
  .zm-scroll{flex:1 1 auto;min-height:0;overflow:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;
    display:flex;flex-direction:column}
  /* margin-block:auto and NOT justify-content:center. Both centre content that is shorter than the screen, but
     justify-content:center in a SCROLL container clips the overflow above the top and makes it unreachable —
     auto margins collapse to 0 the moment the content is taller, so a long widget still scrolls from its first
     line. Compact widgets (a clock) then sit in the middle of the screen instead of hugging the header with two
     thirds of a phone empty below them, which is what "casi todo a pantalla completa" has to mean when the
     widget itself is small. */
  /* Targeted STRUCTURALLY (.zm-scroll > *) and not by .zm-body, because a widget.js does el.className="..." on
     the root it is handed and WIPES our class — the very thing the comment above warns about. A rule keyed to
     .zm-body therefore stops applying for exactly the widgets that style themselves, which is most of them:
     verified live, querySelector('.zm-body') found nothing once the clock had rendered, so this padding was
     already dead.
     margin-block:auto centres content SHORTER than the screen (a clock stops hugging the header with two thirds
     of the phone empty below it) and COLLAPSES to 0 as soon as it is taller, so a long widget keeps scrolling
     from its first line. Verified with content forced to 2199px in a 705px scroller: top offset 0, 1496px
     scrollable, scrolls to the bottom and back to the very top. Auto margins are the idiom that guarantees that
     in an overflow container; whether justify-content:center would actually clip here was NOT reproduced, so it
     is not claimed. */
  .zm-scroll > *{padding:12px 12px calc(12px + env(safe-area-inset-bottom));margin-block:auto}
  .zm-load{margin:auto;width:64px;height:64px;border-radius:50%;
    background:conic-gradient(from 0deg,var(--hb-accent),var(--hb-accent2),rgba(61,111,224,0) 78%);
    -webkit-mask:radial-gradient(farthest-side,transparent 58%,#000 60%);mask:radial-gradient(farthest-side,transparent 58%,#000 60%);
    animation:zmspin 1.05s linear infinite}
  @keyframes zmspin{to{transform:rotate(360deg)}}
  .zm-card.loading .zm-scroll{display:flex;align-items:center;justify-content:center}
  /* PAGE PIPS: the only affordance that says "there are more cards and two fingers move you between them". */
  .zm-pips{position:absolute;left:0;right:0;bottom:6px;display:flex;justify-content:center;gap:6px;pointer-events:none}
  .zm-pip{width:6px;height:6px;border-radius:50%;background:var(--hb-neutral);transition:background .2s,width .2s}
  .zm-pip.on{width:18px;border-radius:3px;background:var(--hb-accent)}
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
    this._wireGestures();
    this._mountEmpty();
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

  // Already full screen. The contract method exists so «ponlo a pantalla completa» resolves to something true:
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
      w._mod.render(w.body, data, w._ctx);
      this._applyTitle(w, data);
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
  // what makes «cierra el de la música» work without asking which one. Called by session-lk.js on (re)connect and
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
      if (w.countEl) w.countEl.textContent = this.order.length > 1 ? `${k + 1}/${this.order.length}` : "";
    });
    if (this._pips) {
      this._pips.innerHTML = "";
      if (this.order.length > 1) for (let k = 0; k < this.order.length; k++) {
        const d = document.createElement("i"); d.className = "zm-pip" + (k === this.at ? " on" : ""); this._pips.appendChild(d);
      }
    }
    if (this._empty) this._empty.classList.toggle("on", this.order.length === 0);
  }

  // TWO fingers page; one finger is the widget's. Tracked on the STAGE (capture phase) so a widget's own scroller
  // cannot swallow the gesture, but only ever acted on when touches.length === 2 — a single touch is passed
  // straight through and never preventDefault()ed, which is what keeps every scrollable widget usable.
  _wireGestures() {
    let x0 = 0, y0 = 0, tracking = false;
    const mid = (e) => {
      const a = e.touches[0], b = e.touches[1];
      return { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 };
    };
    this.stage.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 2) { tracking = false; return; }
      const m = mid(e); x0 = m.x; y0 = m.y; tracking = true;
    }, { capture: true, passive: true });
    this.stage.addEventListener("touchmove", (e) => {
      if (!tracking || e.touches.length !== 2) return;
      const m = mid(e);
      // Horizontal intent only, and with a real threshold: a two-finger PINCH or a two-finger scroll must not
      // page. 56px of travel and twice as much horizontal as vertical is the line.
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
    const titleEl = document.createElement("div"); titleEl.className = "zm-title"; titleEl.textContent = baseId;
    const countEl = document.createElement("div"); countEl.className = "zm-count";
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
      w._dataSig = JSON.stringify(data); w._mod = mod; w._ctx = ctx;
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
    // Capped at 8: a deck is paged one card at a time, so restoring 40 would mount 40 widgets to show one.
    for (const id of Array.isArray(ids) ? ids.slice(0, 8) : []) { try { await this.show(id); } catch (_) {} }
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
