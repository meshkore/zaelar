// WidgetRail — the vertical bar on the LEFT that always says WHAT is on the canvas (V2-537, docked in V2-538).
//
// The operator's spec (2026-09-01, with his screenshot in front of him): a new widget had opened UNDER the
// floating chat and he had no way to know it was there. The rule this surface enforces: nothing on the canvas
// may be fully hidden without a visible trace — one small chip per open card, always on top, so covering or
// minimizing a widget never makes it unknowable.
//
// LAYOUT (V2-623, his spec — supersedes V2-552's vertical column): a HORIZONTAL bar along the BOTTOM edge.
// Chips of the open widgets flow on the LEFT half, the bar ORB sits at the true centre (swap button + the slot
// the one #orb canvas is reparented into — Orb.js owns the move), and the tools mirror the chips on the RIGHT.
// The tools are the same four gestures V2-552 named (plus the chat chevron):
//   ⊟ hide all      — MINIMIZE, never close: the chips stay, so any single one can be brought back
//   ⊞ show all      — bring back everything that was hidden
//   ▦ repack        — close the gaps, KEEPING every card at the size he made it (`Desktop.compact`)
//   ⤢ fit on screen — shrink into equal cells so everything fits at once (`Desktop.arrange`)
// Hide/show are two buttons rather than one flipping toggle: a glyph that changes meaning under you has to be
// read before it can be used. And the last two are genuinely different gestures — collapsing them meant
// «optimiza los huecos» also flattened a sheet he had deliberately enlarged.
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
import { chatOpen, setChatOpen, orbDock, setOrbDock, agentState, agentLive } from "../core/store.js?v=2";

function injectStyles(){
  if(document.getElementById("wrail-css")) return;
  const s=document.createElement("style"); s.id="wrail-css";
  s.textContent=`
  /* V2-623 — the system bar lives at the BOTTOM now (operator, 2026-09-08: «move the left bar to bottom.
     orbe goes to center, left and right side contains the open widgets and the other icons»). Three zones:
     chips (left, flex:1) · orb centre (fixed) · tools (right, flex:1) — the two flexible halves are equal so
     the orb zone sits at the true middle. padding-left clears the version badge pinned at the corner. */
  #wrail{position:fixed;left:0;right:0;bottom:0;z-index:9002;display:none;box-sizing:border-box;
    flex-direction:row;align-items:center;gap:8px;padding:0 12px 0 72px;height:var(--wrail-h,64px);overflow:hidden;
    background:color-mix(in srgb,var(--hb-bg-soft,#121216) 92%,transparent);
    border-top:1px solid var(--hb-line,#26262E);backdrop-filter:blur(6px)}
  #wrail.on{display:flex}
  /* V2-617 — orb-style silhouettes: 44px hit targets, 21px strokes, no box until you hover (the orb lid's
     own language). The operator's report on the old 30px/11px buttons: «no logro entender ninguno». */
  #wrail button{width:44px;height:44px;flex:none;border-radius:11px;border:none;
    cursor:pointer;background:transparent;color:var(--hb-muted,#A6A4AC);
    display:flex;align-items:center;justify-content:center;
    font:600 0.75rem/1 var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
    overflow:hidden;padding:0}
  #wrail button svg{width:21px;height:21px;flex:none}
  #wrail button:hover{background:var(--hb-hover,#24242C);color:var(--hb-ink,#F1EFEA)}
  #wrail button:disabled{opacity:.35;cursor:default;background:transparent}
  #wrail .wr-chip{border:1px solid var(--hb-line,#26262E);background:var(--hb-bg,#18181D);
    color:var(--hb-ink,#F1EFEA);letter-spacing:.04em}
  #wrail .wr-chip:hover{border-color:var(--hb-accent,#A48FFF)}
  #wrail .wr-chip.min{opacity:.45;border-style:dashed}
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
  #wrail .wr-swap.on{color:var(--hb-accent,#A48FFF)}
  #wrail .orbic{width:40px;height:40px}
  #wrail .wr-orbslot{display:none;width:54px;height:54px;position:relative;border-radius:50%;flex:none}
  body.hb-orb-bar #wrail .wr-orbslot{display:flex}
  #wrail .wr-orbslot #orb{position:absolute;inset:0;margin:auto;width:46px!important;height:46px!important;
    pointer-events:none}
  #wrail .wr-orbslot .wr-orbpwr{position:absolute;inset:0;margin:auto;width:24px;height:24px;
    visibility:hidden;color:var(--hb-muted,#A6A4AC)}
  #wrail .wr-orbslot.off #orb{visibility:hidden}
  #wrail .wr-orbslot.off .wr-orbpwr{visibility:visible}
  #wrail .wr-orbslot:hover .wr-orbpwr{color:var(--hb-ink,#F1EFEA)}
  `; document.head.appendChild(s);
}

function desk(){ return window.__zaelarDesktop || null; }

function chipLabel(w, id){
  // The card header already carries the canonical NAME (V2-082); the chip wears its first letters.
  const name=(w && w.nameBtn && w.nameBtn.textContent || id).trim();
  return name.slice(0, 2).toUpperCase() || "?";
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
  chips.innerHTML="";
  d.wins.forEach((w,id)=>{
    const b=document.createElement("button");
    b.className="wr-chip"+(d.isMinimized(id)?" min":"");
    b.dataset.wid=id;
    const name=(w && w.nameBtn && w.nameBtn.textContent || id).trim();
    b.textContent=chipLabel(w,id);
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
  // V2-619: the chevron collapses the CHAT COLUMN, never this bar (see the header comment). Reactive on
  // store.chatOpen so the arrow always says what a click will do — whoever closed/opened the chat (the ×,
  // the voice, a proactive push), the chevron follows.
  const paintFold=()=>{
    const open=!!chatOpen();
    fold.innerHTML=open?ICONS.foldL:ICONS.foldR;
    fold.title=open?t("rail.hideChat"):t("rail.showChat");
  };
  fold.onclick=(e)=>{ e.stopPropagation(); setChatOpen(!chatOpen()); };
  createEffect(paintFold);
  hide.onclick=()=>{ const d=desk(); if(d){ d.minimizeAll(); refresh(el); } };
  show.onclick=()=>{ const d=desk(); if(d){ d.revealAll();  refresh(el); } };
  // The two bulk layouts are DIFFERENT gestures and used to be one: `compact` closes the gaps and leaves every
  // card the size the operator made it; `arrange` shrinks everything into equal cells so it all fits at once.
  // Collapsing them meant «optimiza los huecos» also flattened the sheet he had deliberately enlarged.
  comp.onclick=()=>{ const d=desk(); if(d){ d.compact(); refresh(el); } };
  fitA.onclick=()=>{ const d=desk(); if(d){ d.arrange(); refresh(el); } };
  tools.append(hide,show,comp,fitA,fold);
  el.append(chips,orbzone,tools);
  el.classList.add("on");   // V2-619: visible from birth — the bar never hides, widgets or none
  document.addEventListener("hb:canvas-changed",()=>refresh(el));
  paintFold();
  // Tooltips read the i18n bundle, which loads async — repaint once shortly after mount so they land translated.
  const titles=()=>{ comp.title=t("rail.compact"); fitA.title=t("rail.fitAll");
                     hide.title=t("rail.hideAll"); show.title=t("rail.showAll"); };
  setTimeout(()=>{ titles(); paintFold(); paintSwap(); refresh(el); }, 800);
  titles();
  return el;
}
