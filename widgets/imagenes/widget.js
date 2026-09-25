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
           color:var(--hb-ink,#0d1622);width:100%;box-sizing:border-box;background:var(--hb-bg,#fff);
           border:1px solid var(--hb-line,#eef1f6);border-radius:16px;padding:12px 12px 10px;
           display:flex;flex-direction:column;gap:10px;height:100%;min-height:0}
  /* The STAGE takes what the card has left and nothing more (operator, 2026-09-25: the card opened with the
     thumbnails below its edge). It used to be a fixed min(52vh,380px): on a laptop the card's own 82vh ceiling
     cut the strip off, so the one row that says «there are twelve of these» was the part nobody saw. The header,
     the source line and the strip are fixed; the picture flexes, down to a floor that still reads as a photo. */
  .hb-imgv .imghd{display:flex;align-items:baseline;gap:8px;min-height:18px}
  .hb-imgv .imghd b{font-size:15px;font-weight:600;line-height:1.25;overflow:hidden;
                    text-overflow:ellipsis;white-space:nowrap;flex:1}
  .hb-imgv .imgcount{font-size:12px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums;flex:none}
  .hb-imgv .imgsrc{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);display:flex;gap:6px;align-items:center;
                   min-height:14px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
  .hb-imgv .imgsrc a{color:var(--hb-accent,#2F6FEB);text-decoration:none}
  .hb-imgv .imgsrc a:hover{text-decoration:underline}
  .hb-imgv .imgstage{position:relative;background:var(--hb-bg-soft,#f6f8fb);border-radius:12px;
                     border:1px solid var(--hb-line,#eef1f6);flex:1 1 auto;min-height:140px;
                     display:flex;align-items:center;justify-content:center;overflow:hidden}
  .hb-imgv .imgstage img{max-width:100%;max-height:100%;object-fit:contain;display:block}
  .hb-imgv .imgnav{position:absolute;top:50%;transform:translateY(-50%);width:34px;height:34px;
                   border-radius:50%;border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff);
                   color:var(--hb-ink,#0d1622);font-size:17px;line-height:1;cursor:pointer;opacity:.9;
                   display:flex;align-items:center;justify-content:center;padding:0}
  .hb-imgv .imgnav:hover{opacity:1}
  .hb-imgv .imgprev{left:8px} .hb-imgv .imgnext{right:8px}
  /* The strip is exactly as wide as the card and SCROLLS (operator, 2026-09-25: «crecen hasta el infinito hacia
     la derecha… tengo que ampliar el ancho del widget y eso no es correcto»). A thin overlay scrollbar was
     invisible to a mouse, so the bar is always drawn, the wheel moves it sideways, and it can be dragged.
     width:0 + min-width:100% is what stops it widening a card that is still sizing itself to its content. */
  .hb-imgv .imgstrip{display:flex;gap:6px;overflow-x:auto;overflow-y:hidden;padding:2px 0 6px;flex:none;
                     width:0;min-width:100%;cursor:grab;scrollbar-width:thin;
                     scrollbar-color:var(--hb-line-strong,#6b7485) transparent}
  .hb-imgv .imgstrip.dragging{cursor:grabbing;user-select:none}
  .hb-imgv .imgstrip::-webkit-scrollbar{height:6px}
  .hb-imgv .imgstrip::-webkit-scrollbar-thumb{background:var(--hb-line-strong,#6b7485);border-radius:3px}
  .hb-imgv .imghd,.hb-imgv .imgsrc{flex:none}
  .hb-imgv .imgthumb{flex:none;width:74px;height:52px;border-radius:8px;overflow:hidden;cursor:pointer;
                     border:2px solid transparent;background:var(--hb-bg-soft,#f6f8fb);padding:0;
                     display:flex;align-items:center;justify-content:center}
  .hb-imgv .imgthumb img{width:100%;height:100%;object-fit:cover;display:block;-webkit-user-drag:none;pointer-events:none}
  .hb-imgv .imgthumb.on{border-color:var(--hb-accent,#2F6FEB)}
  .hb-imgv .imgfb{color:var(--hb-muted,#5b6b82)}
  .hb-imgv .imgempty{color:var(--hb-muted,#5b6b82);font-size:13px;text-align:center;padding:22px 12px}
  .hb-imgv .imgdim{font-variant-numeric:tabular-nums}
  `; document.head.appendChild(s);
}

// Any text reaching this file comes from a web search result, so it is built with textContent, never innerHTML.
function txt(tag, cls, s){
  const e=document.createElement(tag); if(cls)e.className=cls; if(s!=null)e.textContent=s; return e;
}

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
let _T = null;
function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.imagenes."+key, params); if(s && s!=="widgets.imagenes."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}

export function render(el, data, ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  injectStyles();
  el.className="hb-imgv";
  el.textContent="";
  const d = data || {};
  const items = Array.isArray(d.items) ? d.items : [];
  const i = Math.max(0, Math.min(Number(d.i)||0, Math.max(0, items.length-1)));
  const cur = items[i] || {};

  // ── slideshow (V2-589): the SERVER owns `auto`/`every_s`/the index; this file only re-arms ONE
  // one-shot timer per render that fires the ordinary `next` through ctx.action — the same path a click
  // or the voice takes, so the pase cannot drift from the server (the file's own header rule). Each
  // advance changes `i`, the canvas re-renders, and the next shot re-arms — no interval to leak. A
  // stopped agent arms nothing (ctx.running, V2-092), and the server's producers gate is the real stop.
  try{ if(el._hbImgAuto){ clearTimeout(el._hbImgAuto); el._hbImgAuto = null; } }catch(_){}
  if(d.auto && items.length>1 && !(ctx && ctx.running===false)){
    const ms = Math.max(2, Math.min(60, Number(d.every_s)||6)) * 1000;
    el._hbImgAuto = setTimeout(()=>{ try{ctx.action("next");}catch(_){} }, ms);
  }

  // ── header: what we are looking at, and how many ──────────────────────────────────────────────
  const hd = txt("div","imghd");
  hd.appendChild(txt("b", null, String(cur.title || d.title || d.query || tt("title_fb", null, "Imágenes"))));
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
    stage.appendChild(txt("div","imgempty",tt("empty", null, "Sin imágenes. Pide una foto y aparecerá aquí.")));
  } else {
    // A set from an image index carries TWO addresses for the SAME photograph: the file at the publisher
    // (`url`) and the index's own copy of it (`thumb`). Only the first one can die, and it does — measured
    // 2026-09-03 on «moto de cross», where photo 1 of 12 was a 404 at enduro21.com while the index still
    // served that exact photo as a live 480×290 JPEG. That is why the strip underneath looked FULL while the
    // stage was empty: the picture was never missing, only our copy of it. So the stage asks for the original,
    // then for the same photo from the index, and only gives up when both are gone.
    const full = String(cur.url||""), thumb = String(cur.thumb||"");
    const img=document.createElement("img");
    img.alt=String(cur.title||"");
    img.loading="eager"; img.decoding="async"; img.referrerPolicy="no-referrer";
    // A hotlinked picture can 403 or vanish. Saying so beats a silent broken-image glyph, which reads as our
    // bug rather than the source's — the same "never lie about an empty box" rule the players learned (V2-383).
    //
    // It replaces THE PICTURE, never the stage: clearing the stage also removed the ‹ › arrows, and a set where
    // one photo is dead is exactly when the operator needs them most — the notice would have told them to try
    // the next one while taking away the way to get there. Found by RENDERING it, not by reading it (V2-124).
    let aviso = null;
    img.onerror = () => {
      if(!aviso && thumb && thumb !== full){
        // The swap is NAMED. It is the same photograph at a smaller size, and a silent downgrade would leave
        // the dimensions printed beside it describing a file nobody is looking at — the same reason the source
        // line exists at all. Holding the node is what stops a thumb that is ALSO dead from looping here, and
        // what lets the marker be taken back: claiming a preview beside "this no longer loads" is worse than
        // either message alone.
        aviso = txt("span","imgfb",tt("preview", null, "· vista previa"));
        aviso.title = tt("preview_hint", null, "El original ya no carga; esta es la copia del buscador, más pequeña.");
        src.appendChild(aviso);
        img.src = thumb;
        return;
      }
      if(aviso) aviso.remove();
      img.replaceWith(txt("div","imgempty",tt("dead", null, "Esta imagen ya no carga desde su origen. Prueba con la siguiente.")));
    };
    img.src = full || thumb;
    stage.appendChild(img);
    if(items.length>1){
      const prev=txt("button","imgnav imgprev","‹"); prev.title=tt("prev", null, "Anterior");
      prev.onclick=()=>{ try{ctx.action("previous");}catch(_){} };
      const next=txt("button","imgnav imgnext","›"); next.title=tt("next", null, "Siguiente");
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
      t.draggable=false;   // the browser's own image drag cancelled the strip's drag after a few pixels
      t.onerror=()=>{ b.style.display="none"; };
      b.appendChild(t);
      // Selecting by NUMBER, not by URL: `select` resolves 1-N in the widget, which is the same path voice
      // takes ("the third"), so clicking and speaking cannot diverge.
      b.onclick=(e)=>{ if(strip._dragged){ e.preventDefault(); return; }
                       try{ctx.action("select",{item:String(k+1)});}catch(_){} };
      strip.appendChild(b);
    });
    // The WHEEL moves the strip sideways: a mouse has no horizontal wheel, and without this the only way to
    // the twelfth thumbnail was to widen the card. A trackpad's own sideways swipe is left alone.
    strip.addEventListener("wheel", (e)=>{
      if(strip.scrollWidth <= strip.clientWidth || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
      strip.scrollLeft += e.deltaY; e.preventDefault();
    }, {passive:false});
    // …and it can be DRAGGED. A drag that moved more than a few pixels is not a click on the thumbnail under it.
    let dx0=0, sl0=0, down=false;
    strip.addEventListener("pointerdown", (e)=>{ if(e.button!==0) return; down=true; strip._dragged=false;
      dx0=e.clientX; sl0=strip.scrollLeft; });
    strip.addEventListener("pointermove", (e)=>{ if(!down) return; const d=e.clientX-dx0;
      if(!strip._dragged && Math.abs(d)>5){ strip._dragged=true; strip.classList.add("dragging");
        try{ strip.setPointerCapture(e.pointerId); }catch(_){} }
      if(strip._dragged) strip.scrollLeft = sl0 - d; });
    const up = ()=>{ down=false; strip.classList.remove("dragging"); setTimeout(()=>{ strip._dragged=false; }, 0); };
    strip.addEventListener("pointerup", up); strip.addEventListener("pointercancel", up);
    el.appendChild(strip);
    // The photo on the stage is always one you can SEE in the strip — «next» by voice walks past the edge too.
    const on = strip.children[i];
    if(on) requestAnimationFrame(()=>{ try{
      const l = on.offsetLeft - strip.offsetLeft, r = l + on.offsetWidth;
      if(l < strip.scrollLeft) strip.scrollLeft = l - 6;
      else if(r > strip.scrollLeft + strip.clientWidth) strip.scrollLeft = r - strip.clientWidth + 6;
    }catch(_){} });
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
