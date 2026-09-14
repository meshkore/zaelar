// WidgetRail — the vertical bar on the LEFT that always says WHAT is on the canvas (V2-537, docked in V2-538).
//
// The operator's spec (2026-09-01, with his screenshot in front of him): a new widget had opened UNDER the
// floating chat and he had no way to know it was there. The rule this surface enforces: nothing on the canvas
// may be fully hidden without a visible trace — one small chip per open card, always on top, so covering or
// minimizing a widget never makes it unknowable.
//
// LAYOUT (V2-623, his spec — supersedes V2-552's vertical column; left cluster reordered in V2-666): a
// HORIZONTAL bar along the BOTTOM edge, L→R: the chat chevron + a running-PROCESS count, chips of the open
// widgets, the bar ORB at the true centre (swap button + the slot the one #orb canvas is reparented into —
// Orb.js owns the move), and the layout tools. The tools are the same four gestures V2-552 named:
//   ⊟ hide all      — MINIMIZE, never close: the chips stay, so any single one can be brought back
//   ⊞ show all      — bring back everything that was hidden
//   ▦ repack        — close the gaps, KEEPING every card at the size he made it (`Desktop.compact`)
//   ⤢ fit on screen — shrink into equal cells so everything fits at once (`Desktop.arrange`)
// Hide/show are two buttons rather than one flipping toggle: a glyph that changes meaning under you has to be
// read before it can be used. And the last two are genuinely different gestures — collapsing them meant
// «optimiza los huecos» also flattened a sheet he had deliberately enlarged.
//
// THE LEFT CLUSTER (V2-666, operator 2026-09-11): the chevron that opens/closes the chat panel sits at the
// bar's LEFT edge (it used to live among the right-side tools) — «la flechita que abre el menú de la
// izquierda va a la izquierda». Right beside it, a live count of RUNNING PROCESSES (store.tasks(), the exact
// feed the chat's own "Procesos" tab reads — NOT every widget show/close/minimize, which produces no
// process at all): a bare number with a small pulsing bar, deliberately not a circle-plus-number badge,
// which would read as a notification rather than a gauge of ongoing work. Clicking the chevron opens the
// chat (same gesture as the 💬 icon on the eye's lid); clicking the count opens it straight onto Procesos.
//
// DOCKED, not floating: the bar OWNS the bottom edge — widgets get less vertical room while it is open, they
// never slide under it (Desktop.railBand() reserves the band; this file only announces footprint changes with
// the "hb:rail-resized" event).
//
// NEVER HIDDEN, FIXED HEIGHT (V2-619's rule carried over the rotation): the bar never hides and never
// resizes — its height is the `--wrail-h` token. The chevron still collapses the CHAT COLUMN («lo que se
// puede esconder es la columna del chat»), toggling store.chatOpen.
//
// DELIBERATE LIMITS:
//  · Not voice-addressable (name:null in SYSTEM_SURFACES, like the top bar) — the voice already opens widgets
//    by name; the rail is pure chrome. Aliases can come later without touching this file's logic.
//  · It reaches the Desktop LAZILY through window.__zaelarDesktop (the same handle the SSE bridge uses):
//    system surfaces mount before the Desktop instance exists, so a captured reference would be null forever.
//  · It repaints on the "hb:canvas-changed" event the Desktop fires from its own persistence choke points —
//    no polling, no import cycle.
//  · Generic taskbar CONCEPT only: own glyphs and layout, no OS's trade dress is imitated.
import { t } from "../core/i18n.js?v=1";
import { createEffect } from "../core/reactive.js?v=2";
import { chatOpen, setChatOpen, setChatTab, orbDock, setOrbDock, agentState, agentLive, tasks } from "../core/store.js?v=2";

function injectStyles(){
  if(document.getElementById("wrail-css")) return;
  const s=document.createElement("style"); s.id="wrail-css";
  s.textContent=`
  /* V2-623 — the system bar lives at the BOTTOM now (operator, 2026-09-08: «move the left bar to bottom.
     orbe goes to center, left and right side contains the open widgets and the other icons»). Zones, L→R:
     the LEFT cluster (chat chevron + process count, V2-666) · chips (flex:1) · orb centre (fixed) · tools
     (flex:1) — the two flexible halves are equal so the orb zone sits at the true middle. */
  /* V2-689 — the DOCK has to read as part of the operating system at a glance, not as one more row floating
     over the desk. What makes it read that way is not decoration: its own ground (the sidebar rung, distinct
     from the desk under it), a real border along its top edge, and a shadow cast UPWARD that is barely there —
     just enough to say the band is in front of the desk rather than painted onto it. The blur stays very
     small: this is a clean dark interface, not glass. */
  #wrail{position:fixed;left:0;right:0;bottom:0;z-index:9002;display:none;box-sizing:border-box;
    flex-direction:row;align-items:center;gap:var(--sp-2,8px);padding:0 var(--sp-3,12px);
    height:var(--wrail-h,64px);overflow:hidden;
    background:color-mix(in srgb,var(--hb-sidebar,#0E1014) 94%,transparent);
    border-top:1px solid var(--hb-line,rgba(255,255,255,.10));
    box-shadow:0 -1px 0 rgba(255,255,255,.02), 0 -6px 20px rgba(0,0,0,.28);
    backdrop-filter:blur(8px)}
  #wrail.on{display:flex}
  /* V2-617 — orb-style silhouettes: 44px hit targets, 21px strokes, no box until you hover (the orb lid's
     own language). The operator's report on the old 30px/11px buttons: «no logro entender ninguno». */
  #wrail button{width:44px;height:44px;flex:none;border-radius:var(--hb-r-m,10px);border:1px solid transparent;
    cursor:pointer;background:transparent;color:var(--hb-muted,#A7AFBC);
    display:flex;align-items:center;justify-content:center;
    font:600 0.75rem/1 var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
    overflow:hidden;padding:0;box-sizing:border-box;
    transition:background var(--hb-t-fast,120ms) ease,color var(--hb-t-fast,120ms) ease,
               border-color var(--hb-t-fast,120ms) ease}
  #wrail button svg{width:21px;height:21px;flex:none}
  #wrail button:hover{background:var(--hb-hover,#242A34);color:var(--hb-ink,#F2F4F7)}
  #wrail button:active{background:var(--hb-bubble,#1D222A)}
  #wrail button:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px var(--hb-accent,#9B7CFF))}
  #wrail button:disabled{opacity:.35;cursor:default;background:transparent}
  /* V2-666 — chips carry the widget's NAME, not just its initials (operator, 2026-09-11: "vídeo", "música",
     "archivos" have to fit, more or less, in five or six characters). Three fixed widths, same for every
     chip at a given level — refresh() PICKS the level from the space actually left between the chips'
     left edge and the orb zone, widest-that-fits first, falling back to 3 then 1 character when there are
     too many open widgets to letter them out in full. */
  /* a chip is a card ON the dock: the widget rung, so it stands out from the band the way a widget stands out
     from the desk — the same ladder, one level down. */
  #wrail .wr-chip{border:1px solid var(--hb-line,rgba(255,255,255,.10));background:var(--hb-bg,#12151A);
    color:var(--hb-ink,#F2F4F7);letter-spacing:.04em;width:64px;flex:none}
  #wrail .wr-chip.wr-lv3{width:42px}
  #wrail .wr-chip.wr-lv1{width:30px;letter-spacing:0}
  #wrail .wr-chip:hover{background:var(--hb-hover,#242A34);border-color:var(--hb-line-strong,rgba(255,255,255,.18))}
  /* MINIMIZED is said twice — dimmer AND dashed — so the state survives a colourblind reader (the operator's
     rule about never leaning on colour alone), and it is the one chip state that is not merely a hover. */
  #wrail .wr-chip.min{opacity:.45;border-style:dashed}
  /* V2-690 — THE ACTIVE APPLICATION. The dock could say what is OPEN and what is HIDDEN and had no way to say
     which card the operator is actually in, which is the one thing a system bar exists to answer at a glance.
     Said TWICE, like every other state here: an accent underline pinned to the bar's own edge (the shape a
     dock uses, and the half that survives a colourblind reader) plus a light accent wash. It is a DEGREE of
     the same chip, never a different chip — the card it points at is marked the same way, with .hb-focus.
     A minimized card is never the active one, so .min wins by coming after. */
  #wrail .wr-chip.on{background:color-mix(in srgb,var(--hb-accent,#9B7CFF) 15%,var(--hb-bg,#12151A));
    border-color:color-mix(in srgb,var(--hb-accent,#9B7CFF) 45%,transparent);color:var(--hb-ink,#F2F4F7);
    position:relative}
  /* INSIDE the chip, not hanging below it: every button in this bar is overflow:hidden (chip labels are
     clipped rather than allowed to widen the bar), which clips at the PADDING box — so a marker at
     bottom:-1px paints one of its two pixels and silently renders at half the weight it declares. */
  #wrail .wr-chip.on::after{content:"";position:absolute;left:6px;right:6px;bottom:0;height:2px;
    border-radius:2px 2px 0 0;background:var(--hb-accent,#9B7CFF)}
  #wrail .wr-chip.on.min::after{display:none}
  /* V2-666 — the LEFT cluster (operator, 2026-09-11): the chevron that opens/closes the chat moves to the
     left EDGE of the bar (it used to sit at the far right, mirroring the tools — he wants it where a "deploy
     the side panel" control belongs), and right beside it a live count of RUNNING PROCESSES (background
     flows a worker is actually carrying out — not every widget open/close, which produces none). Explicitly
     NOT a circle-plus-number badge ("va a parecer que son notificaciones"): a bare number with a small bar
     that pulses up and down beside it, the same idea as the ⏻ VU meter — motion reads as "alive", not "new".
     Clicking the chevron opens the chat (same gesture as the 🤖/💬 icons on the eye's lid); clicking the
     count opens it straight onto the Procesos tab. Hidden entirely at zero — an idle "0" is dead chrome. */
  #wrail .wr-left{flex:none;display:flex;align-items:center;gap:2px}
  #wrail .wr-proc{display:none;flex:none;align-items:center;gap:6px;height:44px;padding:0 10px 0 6px;
    border-radius:var(--hb-r-m,10px);border:none;cursor:pointer;background:transparent;color:var(--hb-ink,#F2F4F7);
    transition:background var(--hb-t-fast,120ms) ease}
  #wrail .wr-proc.on{display:flex}
  #wrail .wr-proc:hover{background:var(--hb-hover,#242A34)}
  #wrail .wr-proc:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px var(--hb-accent,#9B7CFF))}
  #wrail .wr-proc-n{font:700 0.9375rem/1 var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif)}
  #wrail .wr-proc-bar{width:3px;height:15px;border-radius:2px;background:var(--hb-line,rgba(255,255,255,.10));
    position:relative;overflow:hidden;flex:none}
  #wrail .wr-proc-bar i{position:absolute;left:0;right:0;bottom:0;height:100%;border-radius:2px;
    background:var(--hb-accent,#9B7CFF);transform-origin:50% 100%;animation:wrProcPulse 1.15s ease-in-out infinite}
  @keyframes wrProcPulse{0%,100%{transform:scaleY(.28)}50%{transform:scaleY(1)}}
  /* chips flow LEFT→RIGHT and scroll among themselves; tools mirror them on the right */
  #wrail .wr-chips{display:flex;flex-direction:row;gap:6px;align-items:center;justify-content:flex-start;
    flex:1 1 0;min-width:0;overflow-x:auto;overflow-y:hidden;scrollbar-width:none}
  #wrail .wr-chips::-webkit-scrollbar{display:none}
  #wrail .wr-tools{display:flex;flex-direction:row;gap:6px;align-items:center;justify-content:flex-end;
    flex:1 1 0;min-width:0}
  /* the BAR ORB (V2-623): [3 lid controls] [orb slot] [2 lid controls + swap]. The slot is a BUTTON and in
     bar mode the ORB IS THE SWITCH (the V2-124 mobile-dock pattern): stopped shows a ⏻ face, running shows
     the reparented #orb canvas, and a click forwards to the real ⏻ control. Both faces are ALWAYS in the
     DOM and alternate by visibility — the 4.19 lesson: a re-created canvas renders blank with no error. */
  #wrail .wr-orb{flex:none;display:flex;align-items:center;gap:2px}
  #wrail .wr-orbl,#wrail .wr-orbr{display:flex;align-items:center;gap:2px}
  #wrail .wr-swap.on{color:var(--hb-accent,#9B7CFF);background:color-mix(in srgb,var(--hb-accent,#9B7CFF) 16%,transparent)}
  #wrail .orbic{width:40px;height:40px}
  #wrail .wr-orbslot{display:none;width:54px;height:54px;position:relative;border-radius:50%;flex:none}
  body.hb-orb-bar #wrail .wr-orbslot{display:flex}
  #wrail .wr-orbslot #orb{position:absolute;inset:0;margin:auto;width:46px!important;height:46px!important;
    pointer-events:none}
  #wrail .wr-orbslot .wr-orbpwr{position:absolute;inset:0;margin:auto;width:24px;height:24px;
    visibility:hidden;color:var(--hb-muted,#A7AFBC)}
  #wrail .wr-orbslot.off #orb{visibility:hidden}
  #wrail .wr-orbslot.off .wr-orbpwr{visibility:visible}
  #wrail .wr-orbslot:hover .wr-orbpwr{color:var(--hb-ink,#F2F4F7)}
  `; document.head.appendChild(s);
}

function desk(){ return window.__zaelarDesktop || null; }

// V2-666 — same width for every chip at a level; the widest level that fits wins. Matches the CSS widths
// above (`.wr-chip`/`.wr-lv3`/`.wr-lv1`) and the gap the flex row lays chips out with.
const CHIP_CHARS = [6, 3, 1];
const CHIP_W = { 6: 64, 3: 42, 1: 30 };
const CHIP_GAP = 6;
const CHIP_LV_CLASS = { 6: "", 3: " wr-lv3", 1: " wr-lv1" };

function chipLabel(w, id, chars){
  // The card header already carries the canonical NAME (V2-082); the chip wears as much of it as its
  // current level allows — 6 chars fits most system-widget names ("VÍDEO", "MÚSICA"), 3/1 are the
  // fallback for a canvas with too many open widgets to letter them out in full.
  const name=(w && w.nameBtn && w.nameBtn.textContent || id).trim();
  return (name.slice(0, chars) || "?").toUpperCase();
}

// The widest level whose chips, all together, still fit the space actually left for them — measured
// against the chips container's OWN width, which the flex layout already fixes independently of its
// content (flex:1 1 0, min-width:0; the orb zone and the tools column are the siblings that box it in).
function chipLevel(chipsEl, count){
  if(!count) return CHIP_CHARS[0];
  const avail = chipsEl ? chipsEl.clientWidth : 0;
  for(const lvl of CHIP_CHARS){
    const needed = count*CHIP_W[lvl] + (count-1)*CHIP_GAP;
    if(needed <= avail) return lvl;
  }
  return CHIP_CHARS[CHIP_CHARS.length-1];
}

// V2-690 — the ACTIVE card, i.e. the one the operator is working in. `hb-focus` is the desktop's own
// single-writer marker (_bringFront), so the dock reports the same fact the window border already shows
// rather than inventing a second opinion about it. A canvas nobody has clicked yet has no focused card;
// there the topmost visible one is the honest answer, because that is what a click would reach.
function activeCardId(d){
  let focused=null;
  d.wins.forEach((w,id)=>{ if(w && w.card && w.card.classList.contains("hb-focus")) focused=id; });
  if(focused && !d.isMinimized(focused)) return focused;
  return topCardId(d);
}

function topCardId(d){
  // The visible card with the highest z — the one a click would reach first.
  let best=null, bz=-1;
  d.wins.forEach((w,id)=>{
    if(!w.card || w.card.classList.contains("hb-minned")) return;
    const z=parseInt(w.card.style.zIndex)||0;
    if(z>=bz){ bz=z; best=id; }
  });
  return best;
}

// Footprint change → tell the Desktop, which shoves any card out from under the bar. Announced only when the
// occupied width actually changed: refresh() runs on every canvas event and must not echo it back as a resize.
let _lastFoot = null;
function announce(el){
  const w = el.classList.contains("on") ? el.getBoundingClientRect().width : 0;
  if(_lastFoot !== null && Math.abs(w - _lastFoot) < 1) return;
  _lastFoot = w;
  try{ document.dispatchEvent(new CustomEvent("hb:rail-resized")); }catch(_){}
}

function refresh(el){
  const d=desk();
  const chips=el.querySelector(".wr-chips");
  // V2-619, the operator's rule: the system bar NEVER hides — with zero widgets the chips area is simply
  // empty and the layout tools sit disabled. (It used to vanish with the last card, which also made the
  // version tag and the desk's left inset come and go with it.)
  el.classList.add("on");
  if(!d || !d.wins || d.wins.size===0){
    chips.innerHTML="";
    for(const cls of [".wr-hide",".wr-show"]){ const b=el.querySelector(cls); if(b) b.disabled=true; }
    announce(el); return;
  }
  const level=chipLevel(chips, d.wins.size);
  const lvClass=CHIP_LV_CLASS[level];
  const active=activeCardId(d);
  chips.innerHTML="";
  d.wins.forEach((w,id)=>{
    const b=document.createElement("button");
    b.className="wr-chip"+lvClass+(id===active?" on":"")+(d.isMinimized(id)?" min":"");
    b.dataset.wid=id;
    const name=(w && w.nameBtn && w.nameBtn.textContent || id).trim();
    b.textContent=chipLabel(w,id,level);
    b.title=name+(d.isMinimized(id)?" · "+t("rail.minimized"):"");
    // Taskbar semantics: minimized → bring it back on top; buried → bring it on top; already on top → minimize.
    b.onclick=()=>{ const dd=desk(); if(!dd) return;
      if(dd.isMinimized(id)) dd.reveal(id);
      else if(topCardId(dd)===id) dd.minimize(id);
      else { const ww=dd.wins.get(id); if(ww&&ww.card) dd._bringFront(ww.card); }
      refresh(el);
    };
    chips.appendChild(b);
  });
  // HIDE ALL and SHOW ALL are two buttons, not one toggle whose meaning flips (V2-552, his spec: «un botón que
  // esconde todos los widgets… y luego tiene que haber otro botón para restaurarlos»). A single glyph that
  // changes under you is a control you have to read before you can use it, and it cannot be aimed at from
  // muscle memory. Each is disabled when it would do nothing, which says the same thing without moving.
  const anyVisible=[...d.wins.keys()].some(id=>!d.isMinimized(id));
  const anyHidden=[...d.wins.keys()].some(id=>d.isMinimized(id));
  const hide=el.querySelector(".wr-hide"), show=el.querySelector(".wr-show");
  if(hide){ hide.disabled=!anyVisible; hide.title=t("rail.hideAll"); }
  if(show){ show.disabled=!anyHidden;  show.title=t("rail.showAll"); }
  announce(el);
}

export function WidgetRail(){
  injectStyles();
  const el=document.createElement("div"); el.id="wrail";
  // V2-617: the tools are SILHOUETTE icons (stroke currentColor, the orb lid's language) instead of the old
  // 11px text glyphs the operator could not read. Same four gestures, same handlers — only the face changed.
  const ICONS={
    hide:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="3"/><path d="M8 15h8"/></svg>',
    show:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>',
    comp:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2.5"/><path d="M4 12h16M12 4v16"/></svg>',
    fit:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M10 7h7v7"/></svg>',
    foldL:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m14 6-6 6 6 6"/></svg>',
    foldR:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m10 6 6 6-6 6"/></svg>',
    orbBar:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><rect x="3" y="16" width="18" height="5" rx="2"/></svg>',
    orbUp:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="16" width="18" height="5" rx="2"/><path d="M12 13V4"/><path d="m8 8 4-4 4 4"/></svg>',
  };
  const mk=(cls,svg)=>{ const b=document.createElement("button"); b.className=cls; if(svg) b.innerHTML=svg; return b; };
  const fold=mk("wr-fold","");
  const hide=mk("wr-hide",ICONS.hide);   // minimize every card — hide, never close: the chips stay, so each comes back
  const show=mk("wr-show",ICONS.show);   // bring back everything that was hidden
  const comp=mk("wr-compact",ICONS.comp);// close the gaps, KEEPING every card's size
  const fitA=mk("wr-fitall",ICONS.fit);  // shrink to fit: everything on screen at once
  const left=document.createElement("div"); left.className="wr-left";
  // V2-666 — the RUNNING-PROCESS count (background flows the brain is actually carrying out, not every
  // widget open/close/minimize, which produces none — store.tasks() is exactly the "Procesos" tab's own
  // feed, V2-608 F7). A bare number + a pulsing bar, never a circle: a circle+number reads as a
  // notification, and this is a live gauge, not something to dismiss.
  const proc=document.createElement("button"); proc.className="wr-proc";
  const procN=document.createElement("span"); procN.className="wr-proc-n";
  const procBar=document.createElement("span"); procBar.className="wr-proc-bar";
  procBar.innerHTML="<i></i>";
  proc.append(procN,procBar);
  proc.onclick=(e)=>{ e.stopPropagation(); setChatTab("procesos"); setChatOpen(true); };
  const chips=document.createElement("div"); chips.className="wr-chips";
  const tools=document.createElement("div"); tools.className="wr-tools";
  // V2-623 — the bar's CENTRE: the swap button + the slot the ONE #orb canvas is reparented into (Orb.js owns
  // the move; this file only offers the slot and the toggle). «initially the hor bar orbe is deactivated»: in
  // eye mode the slot is hidden and the swap wears a dimmed orb-on-a-bar; in bar mode the canvas sits here and
  // the swap becomes the way back up.
  const orbzone=document.createElement("div"); orbzone.className="wr-orb";
  const swap=mk("wr-swap","");
  const orbl=document.createElement("div"); orbl.className="wr-orbl";
  const orbr=document.createElement("div"); orbr.className="wr-orbr";
  // The slot is the bar's POWER SWITCH while the orb lives here: it holds the ⏻ face and (in bar mode) the
  // reparented canvas, and forwards its click to the REAL ⏻ control — one owner of the power logic, in
  // Orb.js, however many faces it has (the V2-124 rule).
  const slot=mk("wr-orbslot",'<svg class="wr-orbpwr" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/></svg>');
  slot.onclick=(e)=>{ e.stopPropagation(); const p=document.querySelector('[data-ctl="pwr"]'); if(p) p.click(); };
  createEffect(()=>{ slot.classList.toggle("off", !agentLive());
                     slot.title=t("orb.power_"+agentState()); });
  orbr.append(swap);
  orbzone.append(orbl,slot,orbr);
  const paintSwap=()=>{
    const bar=orbDock()==="bar";
    swap.innerHTML=bar?ICONS.orbUp:ICONS.orbBar;
    swap.title=bar?t("rail.orbToEye"):t("rail.orbHere");
    swap.classList.toggle("on",bar);
  };
  swap.onclick=(e)=>{ e.stopPropagation(); setOrbDock(orbDock()==="bar"?"eye":"bar"); };
  createEffect(paintSwap);
  // V2-619/666: the chevron collapses the CHAT COLUMN, never this bar (see the header comment) — it MOVED
  // to the bar's left edge (operator, 2026-09-11: «la flechita que abre… el menú de la izquierda va a la
  // izquierda»), same gesture as before (opens/closes the SAME chat the 💬 icon on the eye's lid opens).
  // Reactive on store.chatOpen so the arrow always says what a click will do — whoever closed/opened the
  // chat (the ×, the voice, a proactive push, the process count below), the chevron follows.
  const paintFold=()=>{
    const open=!!chatOpen();
    fold.innerHTML=open?ICONS.foldL:ICONS.foldR;
    fold.title=open?t("rail.hideChat"):t("rail.showChat");
  };
  fold.onclick=(e)=>{ e.stopPropagation(); setChatOpen(!chatOpen()); };
  createEffect(paintFold);
  // V2-666 — hidden at zero (an idle "0" is dead chrome, and this is a gauge of REAL background work, not
  // a decoration that is always there). Clicking it opens the chat straight onto Procesos, not just chat.
  createEffect(()=>{
    const n=(tasks()||[]).length;
    proc.classList.toggle("on", n>0);
    if(n>0){ procN.textContent=String(n); proc.title=t("rail.processes",{n}); }
  });
  hide.onclick=()=>{ const d=desk(); if(d){ d.minimizeAll(); refresh(el); } };
  show.onclick=()=>{ const d=desk(); if(d){ d.revealAll();  refresh(el); } };
  // The two bulk layouts are DIFFERENT gestures and used to be one: `compact` closes the gaps and leaves every
  // card the size the operator made it; `arrange` shrinks everything into equal cells so it all fits at once.
  // Collapsing them meant «optimiza los huecos» also flattened the sheet he had deliberately enlarged.
  comp.onclick=()=>{ const d=desk(); if(d){ d.compact(); refresh(el); } };
  fitA.onclick=()=>{ const d=desk(); if(d){ d.arrange(); refresh(el); } };
  left.append(fold,proc);
  tools.append(hide,show,comp,fitA);
  el.append(left,chips,orbzone,tools);
  el.classList.add("on");   // V2-619: visible from birth — the bar never hides, widgets or none
  document.addEventListener("hb:canvas-changed",()=>refresh(el));
  // V2-666 — the chip level has to track the space actually LEFT for chips, not just the widget count: a
  // narrower window (or a docked chat column eating into the bar) can shrink that space with the canvas
  // itself unchanged. `chips` is flex:1 1 0/min-width:0, so its own width never grows from its content —
  // safe to watch without the watch re-triggering itself.
  try{
    const ro=new ResizeObserver(()=>refresh(el));
    ro.observe(chips);
  }catch(_){ addEventListener("resize",()=>refresh(el)); }
  paintFold();
  // Tooltips read the i18n bundle, which loads async — repaint once shortly after mount so they land translated.
  const titles=()=>{ comp.title=t("rail.compact"); fitA.title=t("rail.fitAll");
                     hide.title=t("rail.hideAll"); show.title=t("rail.showAll"); };
  setTimeout(()=>{ titles(); paintFold(); paintSwap(); refresh(el); }, 800);
  titles();
  return el;
}
