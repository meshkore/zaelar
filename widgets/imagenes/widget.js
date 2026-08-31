// Image viewer: one picture large, the set as thumbnails underneath, arrows, title + source on top.
//
// Deliberately a viewer and nothing else (operator, 2026-08-28: "nothing fancy... just so people can
// see the images"). No crop, no filters, no download button.
//
// Every mutation goes through ctx.action(), never local state: the same viewer is driven by voice, and a local
// "current index" would drift from the server's the moment the operator says "next one" instead of clicking.
// The server saves, the canvas re-renders over SSE — so this file only ever paints what it was handed.

function injectStyles(){
  if(document.getElementById("hb-imagenes-css"))return;
  const s=document.createElement("style"); s.id="hb-imagenes-css"; s.textContent=`
  .hb-imgv{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
           color:var(--hb-ink,#0d1622);width:min(720px,92vw);background:var(--hb-bg,#fff);
           border:1px solid var(--hb-line,#eef1f6);border-radius:16px;padding:12px 12px 10px;
           display:flex;flex-direction:column;gap:10px}
  .hb-imgv .imghd{display:flex;align-items:baseline;gap:8px;min-height:18px}
  .hb-imgv .imghd b{font-size:15px;font-weight:600;line-height:1.25;overflow:hidden;
                    text-overflow:ellipsis;white-space:nowrap;flex:1}
  .hb-imgv .imgcount{font-size:12px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums;flex:none}
  .hb-imgv .imgsrc{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);display:flex;gap:6px;align-items:center;
                   min-height:14px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
  .hb-imgv .imgsrc a{color:var(--hb-accent,#2F6FEB);text-decoration:none}
  .hb-imgv .imgsrc a:hover{text-decoration:underline}
  .hb-imgv .imgstage{position:relative;background:var(--hb-bg-soft,#f6f8fb);border-radius:12px;
                     border:1px solid var(--hb-line,#eef1f6);height:min(52vh,380px);
                     display:flex;align-items:center;justify-content:center;overflow:hidden}
  .hb-imgv .imgstage img{max-width:100%;max-height:100%;object-fit:contain;display:block}
  .hb-imgv .imgnav{position:absolute;top:50%;transform:translateY(-50%);width:34px;height:34px;
                   border-radius:50%;border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff);
                   color:var(--hb-ink,#0d1622);font-size:17px;line-height:1;cursor:pointer;opacity:.9;
                   display:flex;align-items:center;justify-content:center;padding:0}
  .hb-imgv .imgnav:hover{opacity:1}
  .hb-imgv .imgprev{left:8px} .hb-imgv .imgnext{right:8px}
  .hb-imgv .imgstrip{display:flex;gap:6px;overflow-x:auto;padding:2px 0 4px;scrollbar-width:thin}
  .hb-imgv .imgthumb{flex:none;width:74px;height:52px;border-radius:8px;overflow:hidden;cursor:pointer;
                     border:2px solid transparent;background:var(--hb-bg-soft,#f6f8fb);padding:0;
                     display:flex;align-items:center;justify-content:center}
  .hb-imgv .imgthumb img{width:100%;height:100%;object-fit:cover;display:block}
  .hb-imgv .imgthumb.on{border-color:var(--hb-accent,#2F6FEB)}
  .hb-imgv .imgempty{color:var(--hb-muted,#5b6b82);font-size:13px;text-align:center;padding:22px 12px}
  .hb-imgv .imgdim{font-variant-numeric:tabular-nums}
  `; document.head.appendChild(s);
}

// Any text reaching this file comes from a web search result, so it is built with textContent, never innerHTML.
function txt(tag, cls, s){
  const e=document.createElement(tag); if(cls)e.className=cls; if(s!=null)e.textContent=s; return e;
}

export function render(el, data, ctx){
  injectStyles();
  el.className="hb-imgv";
  el.textContent="";
  const d = data || {};
  const items = Array.isArray(d.items) ? d.items : [];
  const i = Math.max(0, Math.min(Number(d.i)||0, Math.max(0, items.length-1)));
  const cur = items[i] || {};

  // ── header: what we are looking at, and how many ──────────────────────────────────────────────
  const hd = txt("div","imghd");
  hd.appendChild(txt("b", null, String(cur.title || d.title || d.query || "Imágenes")));
  if(items.length) hd.appendChild(txt("span","imgcount", `${i+1} / ${items.length}`));
  el.appendChild(hd);

  // ── source line: where this exact picture came from ───────────────────────────────────────────
  // The operator asked for the source to be visible ("including the source itself"). It names the SITE
  // and links the PAGE, because a bare image URL tells you a CDN hostname and not who published it.
  const src = txt("div","imgsrc");
  if(cur.site){
    if(cur.page){
      const a=document.createElement("a"); a.textContent=String(cur.site);
      a.href=String(cur.page); a.target="_blank"; a.rel="noopener noreferrer"; src.appendChild(a);
    } else src.appendChild(txt("span",null,String(cur.site)));
  }
  if(cur.w && cur.h) src.appendChild(txt("span","imgdim", `· ${cur.w}×${cur.h}`));
  if(cur.weight) src.appendChild(txt("span",null, `· ${cur.weight}`));
  el.appendChild(src);

  // ── stage: the big picture ────────────────────────────────────────────────────────────────────
  const stage = txt("div","imgstage");
  if(!items.length){
    stage.appendChild(txt("div","imgempty","Sin imágenes. Pide una foto y aparecerá aquí."));
  } else {
    const img=document.createElement("img");
    img.src=String(cur.url||""); img.alt=String(cur.title||"");
    img.loading="eager"; img.decoding="async"; img.referrerPolicy="no-referrer";
    // A hotlinked picture can 403 or vanish. Saying so beats a silent broken-image glyph, which reads as our
    // bug rather than the source's — the same "never lie about an empty box" rule the players learned (V2-383).
    //
    // It replaces THE PICTURE, never the stage: clearing the stage also removed the ‹ › arrows, and a set where
    // one photo is dead is exactly when the operator needs them most — the notice would have told them to try
    // the next one while taking away the way to get there. Found by RENDERING it, not by reading it (V2-124).
    img.onerror = () => {
      img.replaceWith(txt("div","imgempty","Esta imagen ya no carga desde su origen. Prueba con la siguiente."));
    };
    stage.appendChild(img);
    if(items.length>1){
      const prev=txt("button","imgnav imgprev","‹"); prev.title="Anterior";
      prev.onclick=()=>{ try{ctx.action("previous");}catch(_){} };
      const next=txt("button","imgnav imgnext","›"); next.title="Siguiente";
      next.onclick=()=>{ try{ctx.action("next");}catch(_){} };
      stage.appendChild(prev); stage.appendChild(next);
    }
  }
  el.appendChild(stage);

  // ── strip: the whole set, current one marked ──────────────────────────────────────────────────
  if(items.length>1){
    const strip=txt("div","imgstrip");
    items.forEach((it,k)=>{
      const b=txt("button","imgthumb"+(k===i?" on":""));
      b.title=String(it.title||it.site||`Foto ${k+1}`);
      const t=document.createElement("img");
      t.src=String(it.thumb||it.url||""); t.alt=""; t.loading="lazy"; t.referrerPolicy="no-referrer";
      t.onerror=()=>{ b.style.display="none"; };
      b.appendChild(t);
      // Selecting by NUMBER, not by URL: `select` resolves 1-N in the widget, which is the same path voice
      // takes ("the third"), so clicking and speaking cannot diverge.
      b.onclick=()=>{ try{ctx.action("select",{item:String(k+1)});}catch(_){} };
      strip.appendChild(b);
    });
    el.appendChild(strip);
  }

  // ── KEYBOARD: ← → to move through photos (V2-465) ───────────────────────────────────────────────
  // The third of the family without keys: `musica` and `youtube` already had them. In a photo viewer the
  // arrows are the FIRST thing people try, and without them they have to reach for the mouse for something
  // the widget already knows how to do. Listen on the CARD (not on document) so that two open viewers do not
  // fight over the same key, and `tabIndex` is what lets the card receive focus.
  if(items.length>1){
    el.tabIndex = 0;
    el.onkeydown = (e)=>{
      // Never steal the arrows while someone is typing (the chat, a field in another widget above it).
      const a = document.activeElement;
      if(a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.isContentEditable)) return;
      let act = "";
      if(e.key === "ArrowRight") act = "next";
      else if(e.key === "ArrowLeft") act = "previous";
      if(!act) return;
      e.preventDefault();
      try{ ctx.action(act); }catch(_){}
    };
  }
}
