// WidgetRail — the vertical bar on the LEFT that always says WHAT is on the canvas (V2-537, docked in V2-538).
//
// The operator's spec (2026-09-01, with his screenshot in front of him): a new widget had opened UNDER the
// floating chat and he had no way to know it was there. The rule this surface enforces: nothing on the canvas
// may be fully hidden without a visible trace — one small chip per open card, always on top, so covering or
// minimizing a widget never makes it unknowable. Plus the two bulk gestures he asked for: ▦ auto-arrange
// (the same Desktop.arrange() the showcase mode uses — the OS-style window snap) and minimize/show all.
//
// DOCKED, not floating (operator, same day): the bar is a fixed full-height column that OWNS the left edge —
// widgets get less horizontal room while it is open, they never slide under it. It folds to a thin border
// (the fold survives a reload) and unfolds from that border with one click. Chips stack top-to-bottom.
// The Desktop enforces the reservation (Desktop.minX()); this file only announces footprint changes with the
// "hb:rail-resized" event so open cards get nudged out from under the bar.
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

const FOLD_KEY = "wrail.folded";

function injectStyles(){
  if(document.getElementById("wrail-css")) return;
  const s=document.createElement("style"); s.id="wrail-css";
  s.textContent=`
  #wrail{position:fixed;left:0;top:0;bottom:0;z-index:9002;display:none;box-sizing:border-box;
    flex-direction:column;align-items:center;gap:6px;padding:10px 4px;width:40px;overflow:hidden;
    background:color-mix(in srgb,var(--hb-bg,#141d29) 92%,transparent);
    border-right:1px solid var(--hb-line,#232e3d);backdrop-filter:blur(6px)}
  #wrail.on{display:flex}
  #wrail button{width:30px;height:30px;flex:none;border-radius:8px;border:1px solid var(--hb-line,#232e3d);
    cursor:pointer;background:var(--hb-bg,#141d29);color:var(--hb-ink,#e8edf5);
    font:600 11px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 2px}
  #wrail button:hover{border-color:var(--hb-accent,#3D6FE0)}
  #wrail .wr-chip.min{opacity:.45;border-style:dashed}
  #wrail .wr-sep{width:22px;height:1px;flex:none;background:var(--hb-line,#232e3d);border:none;padding:0;margin:2px 0}
  /* chips stack from the TOP downward and scroll on their own when there are many */
  #wrail .wr-chips{display:flex;flex-direction:column;gap:6px;align-items:center;
    flex:1 1 auto;min-height:0;overflow-y:auto;scrollbar-width:none}
  #wrail .wr-chips::-webkit-scrollbar{display:none}
  /* FOLDED: a thin border that stays visible (and clickable) so the bar can be pushed back and pulled out.
     Everything but the fold handle disappears; the handle grows to fill the strip so the whole edge is the
     target — a 12px sliver with a 30px button inside would be unhittable. */
  #wrail.folded{width:12px;padding:0;gap:0;cursor:pointer}
  #wrail.folded .wr-chips,#wrail.folded .wr-arrange,#wrail.folded .wr-toggle,#wrail.folded .wr-sep{display:none}
  #wrail.folded .wr-fold{width:100%;height:100%;border:none;border-radius:0;background:transparent;
    color:var(--hb-muted-2,#7d8a9c);font-size:10px}
  #wrail.folded:hover{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 18%,var(--hb-bg,#141d29))}
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
  if(!d || !d.wins || d.wins.size===0){ el.classList.remove("on"); chips.innerHTML=""; announce(el); return; }
  el.classList.add("on");
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
  const anyVisible=[...d.wins.keys()].some(id=>!d.isMinimized(id));
  const tg=el.querySelector(".wr-toggle");
  tg.textContent=anyVisible?"⊟":"⊞";
  tg.title=anyVisible?t("rail.hideAll"):t("rail.showAll");
  announce(el);
}

export function WidgetRail(){
  injectStyles();
  const el=document.createElement("div"); el.id="wrail";
  const fold=document.createElement("button"); fold.className="wr-fold";
  const arr=document.createElement("button"); arr.className="wr-arrange"; arr.textContent="▦";
  const tg=document.createElement("button"); tg.className="wr-toggle"; tg.textContent="⊟";
  const sep=document.createElement("div"); sep.className="wr-sep";
  const chips=document.createElement("div"); chips.className="wr-chips";
  const paintFold=()=>{
    const folded=el.classList.contains("folded");
    fold.textContent=folded?"»":"«";
    fold.title=folded?t("rail.expand"):t("rail.collapse");
  };
  const setFold=(folded)=>{
    el.classList.toggle("folded", !!folded);
    try{ localStorage.setItem(FOLD_KEY, folded?"1":"0"); }catch(_){}
    paintFold(); announce(el);
  };
  try{ if(localStorage.getItem(FOLD_KEY)==="1") el.classList.add("folded"); }catch(_){}
  fold.onclick=(e)=>{ e.stopPropagation(); setFold(!el.classList.contains("folded")); };
  // folded, the WHOLE strip is the unfold target — see the .folded CSS note
  el.addEventListener("click",()=>{ if(el.classList.contains("folded")) setFold(false); });
  arr.onclick=()=>{ const d=desk(); if(d){ d.arrange(); refresh(el); } };
  tg.onclick=()=>{ const d=desk(); if(!d) return;
    const anyVisible=[...d.wins.keys()].some(id=>!d.isMinimized(id));
    if(anyVisible) d.minimizeAll(); else d.revealAll();
    refresh(el);
  };
  el.append(fold,arr,tg,sep,chips);
  document.addEventListener("hb:canvas-changed",()=>refresh(el));
  paintFold();
  // Tooltips read the i18n bundle, which loads async — repaint once shortly after mount so they land translated.
  setTimeout(()=>{ arr.title=t("rail.arrange"); paintFold(); refresh(el); }, 800);
  arr.title=t("rail.arrange");
  return el;
}
