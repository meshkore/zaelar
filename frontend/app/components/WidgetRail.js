// WidgetRail — the thin vertical bar on the LEFT that always says WHAT is on the canvas (V2-537).
//
// The operator's spec (2026-09-01, with his screenshot in front of him): a new widget had opened UNDER the
// floating chat and he had no way to know it was there. The rule this surface enforces: nothing on the canvas
// may be fully hidden without a visible trace — one small chip per open card, always on top, so covering or
// minimizing a widget never makes it unknowable. Plus the two bulk gestures he asked for: ▦ auto-arrange
// (the same Desktop.arrange() the showcase mode uses — the OS-style window snap) and minimize/show all.
//
// DELIBERATE LIMITS of v1:
//  · Not voice-addressable (name:null in SYSTEM_SURFACES, like the top bar) — the voice already opens widgets
//    by name; the rail is pure chrome. Aliases can come later without touching this file's logic.
//  · It reaches the Desktop LAZILY through window.__zaelarDesktop (the same handle the SSE bridge uses):
//    system surfaces mount before the Desktop instance exists, so a captured reference would be null forever.
//  · It repaints on the "hb:canvas-changed" event the Desktop fires from its own persistence choke points —
//    no polling, no import cycle.
//  · Generic taskbar CONCEPT only: own glyphs and layout, no OS's trade dress is imitated.
import { t } from "../core/i18n.js?v=1";

function injectStyles(){
  if(document.getElementById("wrail-css")) return;
  const s=document.createElement("style"); s.id="wrail-css";
  s.textContent=`
  #wrail{position:fixed;left:0;top:50%;transform:translateY(-50%);z-index:9002;display:none;
    flex-direction:column;align-items:center;gap:6px;padding:8px 4px;max-height:70vh;overflow-y:auto;
    background:color-mix(in srgb,var(--hb-bg,#141d29) 88%,transparent);border:1px solid var(--hb-line,#232e3d);
    border-left:none;border-radius:0 12px 12px 0;backdrop-filter:blur(6px)}
  #wrail.on{display:flex}
  #wrail button{width:30px;height:30px;border-radius:8px;border:1px solid var(--hb-line,#232e3d);cursor:pointer;
    background:var(--hb-bg,#141d29);color:var(--hb-ink,#e8edf5);
    font:600 11px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 2px}
  #wrail button:hover{border-color:var(--hb-accent,#3D6FE0)}
  #wrail .wr-chip.min{opacity:.45;border-style:dashed}
  #wrail .wr-sep{width:22px;height:1px;background:var(--hb-line,#232e3d);border:none;padding:0;margin:2px 0;cursor:default}
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

function refresh(el){
  const d=desk();
  const chips=el.querySelector(".wr-chips");
  if(!d || !d.wins || d.wins.size===0){ el.classList.remove("on"); chips.innerHTML=""; return; }
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
}

export function WidgetRail(){
  injectStyles();
  const el=document.createElement("div"); el.id="wrail";
  const arr=document.createElement("button"); arr.className="wr-arrange"; arr.textContent="▦";
  const tg=document.createElement("button"); tg.className="wr-toggle"; tg.textContent="⊟";
  const sep=document.createElement("div"); sep.className="wr-sep";
  const chips=document.createElement("div"); chips.className="wr-chips";
  chips.style.cssText="display:flex;flex-direction:column;gap:6px;align-items:center";
  arr.onclick=()=>{ const d=desk(); if(d){ d.arrange(); refresh(el); } };
  tg.onclick=()=>{ const d=desk(); if(!d) return;
    const anyVisible=[...d.wins.keys()].some(id=>!d.isMinimized(id));
    if(anyVisible) d.minimizeAll(); else d.revealAll();
    refresh(el);
  };
  el.append(arr,tg,sep,chips);
  document.addEventListener("hb:canvas-changed",()=>refresh(el));
  // Tooltips read the i18n bundle, which loads async — repaint once shortly after mount so they land translated.
  setTimeout(()=>{ arr.title=t("rail.arrange"); refresh(el); }, 800);
  arr.title=t("rail.arrange");
  return el;
}
