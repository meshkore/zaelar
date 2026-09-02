// ============================================================================
// widgets-desktop.js — the zaelar "canvas" / window manager.  INDEPENDENT PIECE.
//
// This is the painter's canvas: it owns how widgets appear, where they go, drag-and-drop, z-order and the
// loading/boop choreography. It talks to the backend ONLY through the widgets HTTP contract, and it exposes a
// small API that the voice/SSE layer (and, later, the Hermes bot) drives:
//
//   const desk = new Desktop(stageEl)
//   desk.show(id, {q})   // instant placeholder → async load → render → "boop". Tiles in free space; if none, on top.
//   desk.close(id) · desk.closeAll() · desk.has(id) · desk.list()
//
// It can evolve completely on its own. When its capabilities change, the bridge layer re-reads desk.capabilities()
// and tells the bot, so prompts/brain adapt — without coupling the brain to the rendering.
//
// Backend contract used:  GET /widgets/{id}/data?q=  ·  GET /widgets/{id}/widget.js  ·  POST /widgets/{id}/action
// ============================================================================

import { t as tr } from "../core/i18n.js?v=1";

const NINE_DOTS = `<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
  <circle cx="2.5" cy="2.5" r="1.3"/><circle cx="7" cy="2.5" r="1.3"/><circle cx="11.5" cy="2.5" r="1.3"/>
  <circle cx="2.5" cy="7" r="1.3"/><circle cx="7" cy="7" r="1.3"/><circle cx="11.5" cy="7" r="1.3"/>
  <circle cx="2.5" cy="11.5" r="1.3"/><circle cx="7" cy="11.5" r="1.3"/><circle cx="11.5" cy="11.5" r="1.3"/></svg>`;

function injectStyles(){
  if(document.getElementById("hb-desk-css"))return;
  const s=document.createElement("style"); s.id="hb-desk-css"; s.textContent=`
  .hb-stage{position:fixed;inset:0;z-index:12;pointer-events:none}
  /* The card is a FLEX COLUMN with the body as its only scroller (the whole card used to scroll). Resizing
     requires this change: when the card scrolled, the absolutely positioned edge handles moved with the content
     and could not be grabbed. It also keeps the header and confirmation overlay from scrolling out of view in a
     long widget. */
  .hb-win{position:absolute;pointer-events:auto;background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#e3e8f0);border-radius:16px;
    box-shadow:var(--hb-shadow-2,0 20px 60px rgba(13,22,34,.22));padding:30px 16px 16px;max-width:92vw;max-height:82vh;overflow:hidden;
    display:flex;flex-direction:column;
    opacity:0;transform:scale(.9) translateY(10px);transition:opacity .2s,transform .2s cubic-bezier(.2,.9,.3,1.2)}
  .hb-win.in{opacity:1;transform:none}
  /* The SCROLLER wraps the canvas, NOT the widget div: widget.js sets el.className="…" and overwrites any class
     placed on its root (so a rule for .hb-body applied to nothing). The widget remains the sole owner of its div;
     scrolling is card chrome, like the grip or ×. NOTE: this is a template literal — no backticks inside. */
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}
  /* Resize WITHOUT a transition: with the one above enabled, dragging a corner stuttered (each frame animated
     for 200ms toward the new size). It is disabled while the gesture lasts. */
  .hb-win.rz{transition:none;user-select:none}
  .hb-grip{position:absolute;top:7px;left:8px;width:26px;height:26px;border:none;border-radius:7px;cursor:grab;
    background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted-2,#9aa7b8);display:flex;align-items:center;justify-content:center;touch-action:none;z-index:3}
  .hb-grip:active{cursor:grabbing}
  .hb-x{position:absolute;top:7px;right:8px;width:26px;height:26px;border:none;border-radius:7px;cursor:pointer;
    background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted,#5b6b82);font-size:14px;z-index:3}
  .hb-max{position:absolute;top:7px;right:38px;width:26px;height:26px;border:none;border-radius:7px;cursor:pointer;
    background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted,#5b6b82);font-size:12px;line-height:1;z-index:3}
  .hb-max:hover,.hb-x:hover{color:var(--hb-ink,#e8edf5)}
  /* RESIZE HANDLES — four corners and four edges. The operator asked to be able to grab “the widget corners”:
     they are invisible until hovered (a card full of handles is noise), but have a 14px hit area, making them
     grabbable without surgical precision. */
  .hb-rz{position:absolute;z-index:4;touch-action:none}
  .hb-rz-n,.hb-rz-s{left:14px;right:14px;height:8px}
  .hb-rz-e,.hb-rz-w{top:14px;bottom:14px;width:8px}
  .hb-rz-n{top:-4px;cursor:ns-resize} .hb-rz-s{bottom:-4px;cursor:ns-resize}
  .hb-rz-w{left:-4px;cursor:ew-resize} .hb-rz-e{right:-4px;cursor:ew-resize}
  .hb-rz-nw,.hb-rz-ne,.hb-rz-sw,.hb-rz-se{width:16px;height:16px}
  .hb-rz-nw{top:-4px;left:-4px;cursor:nwse-resize} .hb-rz-se{bottom:-4px;right:-4px;cursor:nwse-resize}
  .hb-rz-ne{top:-4px;right:-4px;cursor:nesw-resize} .hb-rz-sw{bottom:-4px;left:-4px;cursor:nesw-resize}
  .hb-rz-se::after{content:"";position:absolute;right:4px;bottom:4px;width:7px;height:7px;opacity:0;transition:opacity .15s;
    border-right:2px solid var(--hb-muted-2,#9aa7b8);border-bottom:2px solid var(--hb-muted-2,#9aa7b8);border-radius:0 0 3px 0}
  .hb-win:hover .hb-rz-se::after{opacity:.8}
  .hb-win:fullscreen{width:100vw!important;height:100vh!important;max-width:100vw;max-height:100vh;top:0!important;left:0!important;
    border-radius:0;background:#000}
  .hb-win.loading{padding:22px;min-width:120px;min-height:120px;display:flex;align-items:center;justify-content:center}
  .hb-win.loading .hb-x,.hb-win.loading .hb-max,.hb-win.loading .hb-grip,.hb-win.loading .hb-scroll,
  .hb-win.loading .hb-head,.hb-win.loading .hb-rz{display:none}
  /* Widget HEADER (V2-082): the NAME used to open it + a config button that expands the ALIASES. It lives in the
     30px top strip, between the grip (left) and × (right). Generic for EVERY widget — widget.js does not touch it.
     The name comes from _meta/registry (manifest.name|title). */
  /* right:70px, no 40: los botones de la derecha son DOS desde que existe ⤢ (ocupa de 38 a 64), así que la
     cabecera se le metía por debajo — invisible con un nombre corto y centrado, evidente con un título largo. */
  .hb-head{position:absolute;top:6px;left:40px;right:70px;height:24px;display:flex;align-items:center;justify-content:center;
    gap:5px;pointer-events:none}
  /* LIVE TITLE (2026-08-12): when the header carries the TASK instead of the widget name, it is left-aligned and
     uses the full space. A short label centers well; a sentence reads from the margin, and centering it wastes
     half the width on unnecessary symmetrical whitespace. */
  .hb-head.live{justify-content:flex-start}
  .hb-head.live .hb-name{max-width:100%;font-weight:600}
  .hb-name{pointer-events:auto;max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border:none;cursor:pointer;
    background:transparent;color:var(--hb-ink,#e8edf5);font:600 12px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .hb-name:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-cfg{pointer-events:auto;border:none;border-radius:6px;cursor:pointer;width:20px;height:20px;padding:0;font-size:11px;
    background:transparent;color:var(--hb-muted-2,#9aa7b8)}
  .hb-cfg:hover{color:var(--hb-ink,#e8edf5);background:var(--hb-bubble,#f1f4f9)}
  /* ALIAS dropdown (host-level, patterned after .hb-confirm): editable chip list + add. */
  .hb-aliases{position:absolute;top:30px;left:12px;right:12px;z-index:6;padding:12px;border-radius:12px;
    max-height:calc(100% - 44px);overflow-y:auto;
    background:var(--hb-bg,#141d29);border:1px solid var(--hb-line,#232e3d);box-shadow:var(--hb-shadow-2,0 12px 40px rgba(0,0,0,.3));
    max-height:60%;overflow:auto;opacity:0;transform:translateY(-6px);transition:opacity .16s,transform .16s}
  .hb-aliases.in{opacity:1;transform:none}
  .hb-al-t{font:600 11px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-muted,#5b6b82);
    margin-bottom:8px;text-transform:uppercase;letter-spacing:.04em}
  .hb-al-chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
  .hb-al-chip{display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:8px;background:var(--hb-bubble,#1b2534);
    color:var(--hb-ink,#e8edf5);font:500 12px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .hb-al-chip.name{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 22%,transparent);font-weight:600}
  .hb-al-chip button{border:none;background:transparent;color:var(--hb-muted,#9aa7b8);cursor:pointer;font-size:13px;padding:0;line-height:1}
  .hb-al-chip button:hover{color:var(--hb-risk,#e5484d)}
  .hb-al-add{display:flex;gap:6px}
  .hb-al-add input{flex:1;min-width:0;border:1px solid var(--hb-line,#232e3d);border-radius:8px;padding:6px 8px;
    background:var(--hb-bg,#0f1621);color:var(--hb-ink,#e8edf5);font:12px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .hb-al-add button{border:none;border-radius:8px;padding:6px 12px;cursor:pointer;background:var(--hb-accent,#3D6FE0);color:#fff;
    font:600 12px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .hb-al-err{color:var(--hb-risk,#e5484d);font:12px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;margin-top:7px}
  .hb-al-origin{margin-top:10px;padding-top:8px;border-top:1px solid var(--hb-line,#232e3d);}
  .hb-al-origin.top{margin:0 0 10px;padding:0 0 8px;border-top:none;border-bottom:1px solid var(--hb-line,#232e3d)}
  .hb-al-origin{
    color:var(--hb-muted,#9aa7b8);font:11.5px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .hb-al-restore{margin-top:7px;border:1px solid var(--hb-accent,#3D6FE0);border-radius:8px;padding:6px 12px;cursor:pointer;
    background:transparent;color:var(--hb-accent,#3D6FE0);font:600 12px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .hb-al-restore:hover{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 14%,transparent)}
  .hb-load{width:72px;height:72px;border-radius:50%;
    background:conic-gradient(from 0deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6),rgba(61,111,224,0) 78%);
    -webkit-mask:radial-gradient(farthest-side,transparent 58%,#000 60%);mask:radial-gradient(farthest-side,transparent 58%,#000 60%);
    animation:hbspin 1.05s linear infinite, hbbreath 2.2s ease-in-out infinite}
  @keyframes hbspin{to{transform:rotate(360deg)}}@keyframes hbbreath{0%,100%{scale:.84}50%{scale:1.04}}
  .hb-win.loading.long .hb-load{animation:hbspin 1.05s linear infinite, hbbreath 2.2s ease-in-out infinite, hbhue 7s linear infinite}
  @keyframes hbhue{to{filter:hue-rotate(300deg)}}
  @keyframes hbboop{0%{transform:scale(.9) translateY(12px);opacity:.5}58%{transform:scale(1.05) translateY(-3px)}100%{transform:scale(1) translateY(0);opacity:1}}
  .hb-win.boop{animation:hbboop .44s cubic-bezier(.2,.9,.3,1.35)}
  .hb-win.building{flex-direction:column;gap:10px}
  .hb-cap{font:12px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-muted-2,#7d8a9c);text-align:center;max-width:220px}
  .hb-cap.err{color:var(--hb-risk,#e5484d)}
  /* CONFIRM OVERLAY (host-level, generic for ANY widget — never touches its widget.js): irreversible action
     (delete) asks Yes/No ON the card. Fed by the confirm SSE events; resolves via POST /widgets/{id}/confirm. */
  .hb-confirm{position:absolute;inset:0;z-index:5;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;
    padding:18px;text-align:center;border-radius:16px;background:color-mix(in srgb,var(--hb-bg,#141d29) 82%,transparent);
    backdrop-filter:blur(4px);opacity:0;transition:opacity .18s}
  .hb-confirm.in{opacity:1}
  .hb-confirm-msg{font:600 14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#e8edf5);max-width:260px}
  .hb-confirm-row{display:flex;gap:10px}
  .hb-confirm-row button{font:600 13px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    border:1px solid var(--hb-line,#232e3d);border-radius:10px;padding:9px 18px;cursor:pointer;background:var(--hb-bg,#141d29);color:var(--hb-ink,#e8edf5)}
  .hb-confirm-row .hb-confirm-yes{border-color:transparent;background:var(--hb-risk,#e5484d);color:#fff}
  .hb-confirm-row button:hover{filter:brightness(1.08)}
  /* V2-537: a MINIMIZED card is open (the brain still sees it; its data survives) but off the canvas.
     The widget rail is the only door back in — its chip stays lit, so nothing on screen is ever unknowable. */
  .hb-win.hb-minned{display:none}
  `; document.head.appendChild(s);
}

// Two rects overlap? (with a padding gap so widgets don't kiss edges)
function _overlap(a, b, pad=12){
  return !(a.right+pad<=b.left || a.left>=b.right+pad || a.bottom+pad<=b.top || a.top>=b.bottom+pad);
}

export class Desktop {
  constructor(stage){
    injectStyles();
    this.stage = stage; this.stage.classList.add("hb-stage");
    this.activity = document.getElementById("activity");   // rail above the voice orb (transient/process widgets)
    this.wins = new Map();           // id -> {card, body, q, _dataSig, _mod, _ctx, _refreshing}
    this.z = 20;
    this.tile = {w: 400, h: 340, top: 70, pad: 14};        // default footprint reserved while a card is loading
    // GRID (V2-551, operator's ask: «que este escritorio tenga algún tipo de rejilla… ponle 5 píxeles»). Fine
    // enough that dragging still feels free — nobody perceives a 5px quantum — and coarse enough that two cards
    // placed independently line up instead of missing each other by one or two pixels, which is what makes a
    // canvas look sloppy. It applies to PLACEMENT, DRAG and RESIZE alike: snapping only some of them produces
    // edges that ALMOST align, which reads worse than no grid at all.
    this.grid = 5;
    this._actId = null; this._actTimer = null;
    this._ver = {};                                        // id -> cache-bust version (bumped after a modify)
    this._busy = new Set();                                // ids with an agent in-flight → don't stack create/modify
    this._restoring = false;
    // V2-092: ¿está el agente EN MARCHA? Se lo pasamos a cada widget en su `ctx` (como getter, así que un widget ya
    // montado lo lee VIVO). Un widget que produce algo —vídeo, audio, una grabación— tiene prohibido arrancar solo
    // con el agente parado, y ese caso se da EN EL MONTAJE: recargar la página con el vídeo pausado por la parada
    // volvía a reproducirlo, porque su `<iframe>` nace con `autoplay=1` y nadie le había dicho que el agente estaba
    // parado. El servidor manda (nucleo/runstate.py); main.js nos lo empuja con `setRunning`.
    this._running = true;
    // V2-538 — the DOCKED widget rail owns the left edge: when it folds/unfolds (or appears with the first
    // card) it announces the new footprint and any card left under it gets shoved out. Widgets never overlap
    // the bar; they simply have less horizontal room while it is open (operator, 2026-09-01).
    document.addEventListener("hb:rail-resized", ()=>this._railClamp());
    this.restore();                                        // bring back the user's desktop (open widgets + positions)
  }

  // Left edge reserved by the docked widget rail (0 when hidden). Every placement/drag/resize/maximize
  // gesture starts right of it — see the constructor note.
  minX(){
    const r=document.querySelector("#wrail");
    if(!r || !r.classList.contains("on")) return 0;
    const rr=r.getBoundingClientRect();
    return rr.width ? Math.round(rr.right) : 0;
  }
  _railClamp(){
    const x0=this.minX(); if(!x0) return;
    let moved=false;
    this.wins.forEach(w=>{
      const c=w.card; if(!c) return;
      if((parseInt(c.style.left)||0) < x0){ c.style.left=(x0+this.tile.pad)+"px"; moved=true; }
    });
    if(moved) this._persist();
  }

  // Agent state → widgets. main.js calls this reactively from `store.powerOff()`.
  setRunning(on){ this._running = !!on; }

  // ---- PERSISTENCE: the desktop is the user's state. Open widgets + their positions survive a refresh / reopen. ----
  // Restorable desktop geometry: which cards, with which query, and where. INSTANCE cards
  // (`navegador::t3` = a specific tab/task) remain ephemeral — their task dies with the process that drove it,
  // so restoring them would paint a tab that no longer exists. The browser BASE card IS restored since 2026-08-12:
  // it was the only widget excluded by name, and since it is precisely what is on screen during a web task,
  // reloading mid-search left the desktop literally blank. SIZE travels with position since 2026-08-12. Previously
  // only the card position was saved, so enlarging the results sheet and reloading returned it to factory size —
  // the operator’s effort was lost on every refresh, the fastest way to make a feature unused.
  _layout(){
    // V2-351 — INSTANCE cards persist too. This used to skip every `base::instance` id, so the desktop the
    // operator actually works on (the errand sheet `results::ece70b-1` with 12 real candidates, the browser
    // tab card) was NEVER saved: a refresh mid-errand restored only the fossil BASE cards and the operator
    // read «Sin resultados todavía» on top of a sheet that was full. Measured live 2026-08-26 on the test
    // rig: /api/canvas/layout held exactly [{id:"results", q:""}] while the live canvas held two instances.
    // The sheet data itself persists on disk (view_data(q) reloads it), so restoring the card is honest.
    const items=[];
    this.wins.forEach((w,id)=>{
      const c=w.card;
      items.push({id, q:w.q||"", left:c.style.left, top:c.style.top, z:c.style.zIndex||"",
                  min:c.classList.contains("hb-minned")?1:0,
                  w:c.style.width||"", h:c.style.height||""}); });
    return items;
  }
  _persist(){
    if(this._restoring) return;
    try{ localStorage.setItem("hb_desktop", JSON.stringify(this._layout())); }catch(_){}
    this._reportOpen();     // STATE: the canvas is authoritative → the server reflects what is open in the prompt
    try{ document.dispatchEvent(new CustomEvent("hb:canvas-changed")); }catch(_){}   // V2-537: the rail repaints
  }
  // Reporta los widgets ABIERTOS al ESTADO de la memoria (POST /api/canvas/state) para que viajen en el prompt del
  // cerebro ("modifica el widget de X" sin preguntar) y se vean en el mapa. Debounce ligero (los arrastres/moves
  // llaman _persist a ráfagas) + best-effort. Envía this.list() crudo; el servidor normaliza (navegador::t3→navegador).
  // Lleva ADEMÁS la geometría, que el server guarda como red de seguridad del localStorage (que es per-origen y
  // per-navegador: el mismo zaelar por :43917 y por :44317 son dos escritorios distintos). Ver `restore()`.
  _reportOpen(){
    try{ document.dispatchEvent(new CustomEvent("hb:canvas-changed")); }catch(_){}   // V2-537 (closeAll/restore too)
    clearTimeout(this._openTimer);
    this._openTimer=setTimeout(()=>{
      try{ fetch("/api/canvas/state",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({open:this.list(), layout:this._layout()})}); }catch(_){}
    }, 250);
  }
  async restore(){
    // WIPEOUT → ESCRITORIO EN BLANCO: los widgets abiertos se guardan en el localStorage del navegador, que un
    // `make reset` de servidor no alcanza. El server sirve una ÉPOCA de wipe (/api/desktop/epoch) que cambia en cada
    // reset; si es más nueva que la nuestra, vaciamos el escritorio local → sesión en blanco, como recién instalado.
    try{
      const { epoch } = await fetch("/api/desktop/epoch").then(r=>r.json());
      if(epoch && localStorage.getItem("hb_wipe") !== String(epoch)){
        localStorage.removeItem("hb_desktop");
        // The chat wall remembers being open since V2-550, and a wipe has to reach it too — otherwise a reset
        // leaves a desktop that is blank except for the one panel that outlived it.
        try{ const m = await import("../components/ChatWall.js?v=5"); m.forgetChatPlacement && m.forgetChatPlacement(); }catch(_){}
        localStorage.setItem("hb_wipe", String(epoch));
        this._reportOpen();               // the server STATE is also cleared
        return;                           // starts with no widgets
      }
    }catch(_){}
    let items=[]; try{ items=JSON.parse(localStorage.getItem("hb_desktop")||"[]"); }catch(_){ items=[]; }
    // REHIDRATACIÓN: sin nada guardado AQUÍ, preguntamos al server por el último escritorio conocido. El
    // localStorage es per-origen y per-navegador — abrir el mismo zaelar por otro origen (:43917 ↔ :44317), en otro
    // navegador o en otro perfil enseña un escritorio vacío que parece pérdida de datos y no lo es. El server
    // conserva la geometría (`/api/canvas/layout`) y la devuelve para reconstruirlo. Solo como FALLBACK: si este
    // navegador tiene su propio estado, MANDA él (el frontend sigue siendo autoritativo del canvas), y la época de
    // wipe de arriba sigue teniendo la última palabra — un reset deja el escritorio en blanco y aquí no se resucita.
    // V2-351: the layout endpoint is fetched ALWAYS now — besides the fallback geometry it reports `live`, the
    // instance cards of errands running RIGHT NOW (their sheet, their browser tab), which is the truth the
    // operator asked the refresh to reflect.
    let srv={items:[], live:[]};
    try{ srv = await fetch("/api/canvas/layout").then(r=>r.json()) || srv; }catch(_){}
    if(!items.length && Array.isArray(srv.items) && srv.items.length){
      items=srv.items;
      console.info("desktop: restored from server (this browser had no saved desktop)");
    }
    // V2-351 — THE FOSSIL SWEEP. A bare BASE card next to an instance of the same base is the ghost the round
    // report names («se abrió la pieza BASE encima de su propia instancia, vacía»): the pre-V2-261 echo used to
    // open base cards and _persist saved them forever, so every restore resurrected an empty «Resultados» ON TOP
    // of the real sheet. A base card is legitimate alone; next to its own instances it is the fossil.
    const bases = new Set(items.filter(it=>String(it.id||"").includes("::")).map(it=>String(it.id).split("::",1)[0]));
    items = items.filter(it=>{ const id=String(it.id||""); return id.includes("::") || !bases.has(id); });
    // …and the errands running right now come back even if this desktop never saved them (the page was closed
    // when their card opened, or another browser did the work). Geometry-less: they auto-place.
    const have = new Set(items.map(it=>String(it.id||"")));
    for(const id of (Array.isArray(srv.live)?srv.live:[])){
      if(id && !have.has(String(id))){ items.push({id:String(id), q:""}); have.add(String(id)); }
    }
    // A browser-tab card with no LIVE task behind it has nothing to reload: navegador data is process state,
    // not a persisted sheet. Sheets and every other widget restore always.
    const liveSet = new Set((Array.isArray(srv.live)?srv.live:[]).map(String));
    items = items.filter(it=>{ const id=String(it.id||"");
      return !(id.startsWith("navegador::") && !liveSet.has(id)); });
    if(!items.length) return;
    this._restoring=true;
    try{ for(const it of items){ await this.show(it.id, {q:it.q, pos:it}); } }
    finally{ this._restoring=false; this._persist(); }
  }

  has(id){ return this.wins.has(id) || this._actId===id; }
  list(){ return [...this.wins.keys(), ...(this._actId?[this._actId]:[])]; }
  capabilities(){ return {open: this.list(), canDrag: true, zTopIsNewest: true}; }  // for the bot bridge

  // The brain doesn't always emit the EXACT catalog id (it said "agenda-today" for the "agenda" widget). Resolve
  // loosely against the live catalog so id drift never silently swallows a widget: exact → prefix → contains.
  // V2-085: `GET /widgets` now returns the COMPACT INDEX (id/name/title/whenToUse/aliases/origin/transient),
  // not the full manifests — everything this resolver and `_meta` need, no longer O(N·manifest)
  // (25 KB with 16 widgets, megabytes with thousands). The complete manifest is requested per widget:
  // /widgets/{id}/manifest.
  async _resolve(id){
    if(!id) return id;
    try{
      if(!this._ids){ const c=await fetch("/widgets").then(r=>r.json()); const ws=c.widgets||[];
        this._ids=ws.map(w=>w.id); this._meta={}; ws.forEach(w=>this._meta[w.id]=w); }
      if(this._ids.includes(id)) return id;
      const hit=this._ids.find(cid=>id===cid||id.startsWith(cid+"-")||id.startsWith(cid+"_")||id.includes(cid)||cid.includes(id));
      if(hit && hit!==id) console.info("widget id resolved:", id, "→", hit);
      return hit || id;
    }catch(_){ return id; }
  }

  // ── Widget NAME + ALIASES (V2-082) ───────────────────────────────────────────────────────────────────
  // Each card header shows the canonical NAME and, behind ⚙, the editable ALIAS list. Source: the unified
  // GET /widgets/registry registry (cached; refreshed by the widget/alias SSE event).
  async _ensureRegistry(force){
    if(this._registry && !force) return this._registry;
    try{
      const r=await fetch("/widgets/registry").then(r=>r.json());
      this._registry={}; (r.registry||[]).forEach(e=>{ this._registry[e.id]=e; });
    }catch(_){ this._registry=this._registry||{}; }
    return this._registry;
  }
  async _applyName(w){
    if(w._liveTitle) return;                            // the TASK takes precedence over the catalog name (see _liveTitle)
    const reg=await this._ensureRegistry(); const e=reg[w.base];
    if(e && w.nameBtn) w.nameBtn.textContent=e.name||w.base;
  }

  // ---- LIVE TITLE: the header says WHAT this is, not WHAT the piece is called ----
  // Operator request (2026-08-12): “people do not need to know this is the viewer or results display, but what we
  // asked it to show.” On a generic surface the catalog name (“Results”) conveys nothing: the card is identified by
  // the TASK it is displaying. A widget may therefore declare `"live_title": true` in its manifest, making the card
  // header use its `data.title`. This is OPT-IN per widget, not global: the agenda or clock is identified by name,
  // and changing all of them would be a regression. The name USED TO OPEN IT is not lost — it remains in the
  // tooltip and alias panel (⚙), where the operator looks up what to call it by voice.
  _wantsLiveTitle(baseId){
    const meta = this._meta && this._meta[baseId];
    return !!(meta && meta.live_title);
  }
  async _applyLiveTitle(w, baseId, data){
    if(!this._wantsLiveTitle(baseId)) return;
    const title = String((data && data.title) || "").trim();
    if(!title || !w.nameBtn) return;
    w._liveTitle = true;
    w.nameBtn.textContent = title;
    if(w.head) w.head.classList.add("live");
    // The canonical name remains one gesture away, not deleted: it is how the piece is addressed by voice.
    const reg = await this._ensureRegistry();
    const name = (reg[baseId] && reg[baseId].name) || baseId;
    w.nameBtn.title = `${title}\n(${name} — click to view/edit its aliases)`;
  }
  async refreshRegistry(){                              // SSE widget/alias → repinta nombres + panel abierto
    await this._ensureRegistry(true);
    for(const w of this.wins.values()){ this._applyName(w); if(w._alias) this._renderAliases(w); }
  }
  _toggleAliases(w){
    if(w._alias){ this._closeAliases(w); return; }
    const panel=document.createElement("div"); panel.className="hb-aliases"; w._alias=panel;
    w.card.appendChild(panel); this._renderAliases(w);
    requestAnimationFrame(()=>panel.classList.add("in"));
    w._aliasAway=(e)=>{ if(w._alias && !w._alias.contains(e.target) && !w.head.contains(e.target)) this._closeAliases(w); };
    setTimeout(()=>document.addEventListener("pointerdown",w._aliasAway),0);
  }
  _closeAliases(w){
    if(w._aliasAway){ document.removeEventListener("pointerdown",w._aliasAway); w._aliasAway=null; }
    if(w._alias){ w._alias.remove(); w._alias=null; }
  }
  async _renderAliases(w){
    const panel=w._alias; if(!panel) return;
    const reg=await this._ensureRegistry(); const e=reg[w.base]||{name:w.base,aliases:[w.base]};
    const name=e.name||w.base, aliases=e.aliases||[name];
    panel.innerHTML="";
    const t=document.createElement("div"); t.className="hb-al-t"; t.textContent=tr("desktop.aliases_title", { name }); panel.appendChild(t);
    // V2-518: the ⚙ panel is the widget's CONFIG corner — it says where the piece comes from, and a FORK
    // carries the RESTORE affordance here (never on the widget's face, per the operator). It sits right
    // under the title so a SHORT card never scrolls it out of sight. The click only OPENS the confirmation:
    // the question lands in the chat thread and on the card (house norm — no popups), answerable by voice
    // or by button; a system widget keeps its reference id visible instead.
    const org=document.createElement("div"); org.className="hb-al-origin top";
    if(e.forked){
      org.textContent=tr("desktop.origin_fork",{id:w.base});
      const rb=document.createElement("button"); rb.className="hb-al-restore";
      rb.textContent=tr("desktop.restore_btn");
      rb.onclick=async()=>{ this._closeAliases(w);
        try{ await fetch(`/widgets/${w.base}/restore/ask`,{method:"POST"}); }catch(_){ } };
      org.appendChild(document.createElement("br")); org.appendChild(rb);
    } else if((e.origin||"user")==="builtin"){
      org.textContent=tr("desktop.origin_system",{id:w.base});
    } else {
      org.textContent=tr("desktop.origin_yours");
    }
    panel.appendChild(org);
    const chips=document.createElement("div"); chips.className="hb-al-chips";
    aliases.forEach(a=>{
      const isName=a.toLowerCase()===name.toLowerCase();
      const chip=document.createElement("span"); chip.className="hb-al-chip"+(isName?" name":"");
      chip.append(document.createTextNode(a));
      if(!isName){ const rm=document.createElement("button"); rm.textContent="×"; rm.title=tr("desktop.remove_tooltip");
        rm.onclick=()=>this._removeAlias(w,a); chip.appendChild(rm); }
      chips.appendChild(chip);
    });
    panel.appendChild(chips);
    const add=document.createElement("div"); add.className="hb-al-add";
    const inp=document.createElement("input"); inp.type="text"; inp.placeholder=tr("desktop.alias_placeholder");
    const btn=document.createElement("button"); btn.textContent=tr("desktop.add_btn");
    const go=()=>{ const v=inp.value.trim(); if(v) this._addAlias(w,v,inp); };
    btn.onclick=go; inp.onkeydown=(ev)=>{ if(ev.key==="Enter"){ ev.preventDefault(); go(); } };
    add.append(inp,btn); panel.appendChild(add);
  }
  async _addAlias(w,alias,inp){
    try{
      const r=await fetch(`/widgets/${w.base}/aliases`,{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({alias})});
      const j=await r.json().catch(()=>({}));
      if(r.ok){ if(inp)inp.value=""; await this.refreshRegistry(); }
      else this._aliasError(w, j.error||tr("desktop.couldnt_add"));
    }catch(_){ this._aliasError(w,tr("desktop.network_error")); }
  }
  async _removeAlias(w,alias){
    try{
      const r=await fetch(`/widgets/${w.base}/aliases/${encodeURIComponent(alias)}`,{method:"DELETE"});
      const j=await r.json().catch(()=>({}));
      if(r.ok) await this.refreshRegistry(); else this._aliasError(w, j.error||tr("desktop.couldnt_remove"));
    }catch(_){ this._aliasError(w,tr("desktop.network_error")); }
  }
  _aliasError(w,msg){
    if(!w._alias) return;
    let e=w._alias.querySelector(".hb-al-err");
    if(!e){ e=document.createElement("div"); e.className="hb-al-err"; w._alias.appendChild(e); }
    e.textContent=msg;
  }

  async show(rawId, {q="", data:providedData=null, pos=null}={}){
    // TASK INSTANCE: an id such as `navegador::t3` = multiple cards for the SAME base widget. base = code+data
    // (`navegador`), q = task id (for /data?q= and ctx.action), and the card is indexed by the COMPLETE id
    // (instance) → N independent browser cards, one per tab/task. A normal id behaves the same way.
    let baseId, id, wq;
    if(rawId && rawId.includes("::")){ const p=rawId.split("::"); baseId=p[0]; id=rawId; wq=p[1]||q;
      // V2-538 — instance ids used to SKIP _resolve, so if the first card of the session was an instance
      // (results::<errand> restored on reload, which is the normal case mid-errand), `_meta` was never loaded and
      // everything that reads it no-opped in silence: no preferred size (the card grew line by line with the
      // worker's text), no live title (the header said "Resultados" and the sheet repeated the task below it),
      // no transient check. Same call, just not skipped; for an exact base id it resolves to itself.
      await this._resolve(baseId);
    }
    else { baseId = await this._resolve(rawId); id = baseId; wq = q; }
    q = wq;
    // Transient/process widgets (search, "what I'm doing") render into the ACTIVITY RAIL above the orb, not a card.
    if(this._meta && this._meta[baseId] && this._meta[baseId].transient) return this._showActivity(baseId, q, providedData);
    let w = this.wins.get(id), fresh=!w;
    if(fresh){
      const card=document.createElement("div"); card.className="hb-win loading"; card.dataset.wid=id;
      const grip=document.createElement("button"); grip.className="hb-grip"; grip.innerHTML=NINE_DOTS; grip.title=tr("desktop.move_tooltip");
      const x=document.createElement("button"); x.className="hb-x"; x.textContent="×"; x.onclick=()=>this.close(id);
      const mx=document.createElement("button"); mx.className="hb-max"; mx.textContent="⤢"; mx.title=tr("desktop.maximize_tooltip");
      mx.onclick=()=>this.maximize(id);
      // HEADER (V2-082): NAME button + config to view/edit ALIASES. The name is populated from the registry.
      const head=document.createElement("div"); head.className="hb-head";
      const nameBtn=document.createElement("button"); nameBtn.className="hb-name"; nameBtn.textContent=baseId;
      nameBtn.title=tr("desktop.name_tooltip");
      const cfg=document.createElement("button"); cfg.className="hb-cfg"; cfg.textContent="⚙"; cfg.title=tr("desktop.cfg_tooltip");
      head.append(nameBtn,cfg);
      const load=document.createElement("div"); load.className="hb-load";
      const scroll=document.createElement("div"); scroll.className="hb-scroll";
      const body=document.createElement("div"); body.className="hb-body";
      scroll.appendChild(body);
      card.append(grip,mx,x,head,load,scroll); this.stage.appendChild(card);
      this._addHandles(card);
      if(pos && pos.left){                              // restored: honor the SAVED position instead of auto-placing
        card.style.left=pos.left; card.style.top=pos.top;
        const pz=parseInt(pos.z)||0; if(pz){ card.style.zIndex=pz; this.z=Math.max(this.z, pz); } else this._bringFront(card);
      } else { this._place(card); this._bringFront(card); }   // fit into free space without overlapping anything
      if(pos && (pos.w || pos.h)) this._applyGeom(card, pos.w, pos.h);   // …y con el tamaño que le dejó el operador
      if(pos && pos.min) card.classList.add("hb-minned");                // V2-537: minimized survives a reload
      this._wireDrag(card, grip);
      this._wireResize(card, id);
      this._watchSize(card);
      card.addEventListener("pointerdown",()=>this._bringFront(card));
      // Dragging (grip) no longer swallows header clicks; the header ignores pointerdown so it does not drag the card.
      head.addEventListener("pointerdown",e=>e.stopPropagation());
      requestAnimationFrame(()=>card.classList.add("in"));
      card._long=setTimeout(()=>card.classList.add("long"),3500);
      w={card, body, q, id, base:baseId, nameBtn, head}; this.wins.set(id, w);
      nameBtn.onclick=()=>this._toggleAliases(w); cfg.onclick=()=>this._toggleAliases(w);
      this._applyName(w);                               // populate the name from the registry (async, best-effort)
      // V2-537: the rail paints the chip NOW, not when the module finishes loading — a card whose code fails
      // to load still occupies the canvas, and a card on the canvas without a chip is exactly what the rail forbids.
      try{ document.dispatchEvent(new CustomEvent("hb:canvas-changed")); }catch(_){}
    } else {
      this._bringFront(w.card);
      // Already open, no new data pushed, same query → just surface it (no re-fetch, no re-render, no flicker).
      if(providedData === null && q === w.q) return;
    }
    w.q = q;                                            // remember the query so a refresh reloads the same content
    // `desk` (NOT `self`: in a browser `self` is `window`, so a getter using it would read `window._running`
    // = undefined and EVERY widget would believe the agent was stopped — a silent, hard-to-see failure).
    const desk = this;
    // async load — never blocks the voice loop; other widgets load in parallel
    try{
      const t0=Date.now();
      // DATA provided by the brain (pushed) → render it as-is; otherwise the widget loads its own data.
      const data = providedData!=null ? providedData
                 : await fetch(`/widgets/${baseId}/data`+(q?`?q=${encodeURIComponent(q)}`:"")).then(r=>r.json());
      const mod=await import(`/widgets/${baseId}/widget.js`+(this._ver[baseId]?`?v=${this._ver[baseId]}`:""));
      if(data.error){ this._mountError(w, baseId, "data: "+data.error); return; }
      const el=Date.now()-t0; if(fresh && el<700) await new Promise(r=>setTimeout(r,700-el));
      clearTimeout(w.card._long); w.card.classList.remove("loading","long");
      const l=w.card.querySelector(".hb-load"); if(l)l.remove();
      const ctx={ action:async(name,payload)=>{ try{return await fetch(`/widgets/${baseId}/action`,{method:"POST",
          headers:{"Content-Type":"application/json"},body:JSON.stringify({action:name,payload:{...(payload||{}),q}})}).then(r=>r.json());}catch(_){return null;} },
        close:()=>this.close(id),
        // “Back to top”: the widget requests it; the canvas decides how (the scroller is card chrome, not the widget’s).
        // Called ONLY when NAVIGATING — opening a record, changing tabs, returning to the list — never on a data
        // refresh: resetting scroll whenever new results arrive would take what the operator is reading out of
        // their hands, precisely while the sheet is filling live.
        top:()=>{ const sc=w.card && w.card.querySelector(".hb-scroll"); if(sc) sc.scrollTop=0; },
        // V2-092 — is the agent running? DELIBERATELY A GETTER: `ctx` is created once at mount and saved
        // (`w._ctx`) for re-renders, so a copied value would become stale. A widget that PLAYS something must check
        // it before starting on its own (see widgets/AGENTS.md, “produce”).
        get running(){ return desk._running; } };
      // The marker goes BEFORE rendering: on its FIRST pass the widget then knows the card header already has the
      // title and does not repeat it. If set afterward, the first render would show the title twice.
      if(this._wantsLiveTitle(baseId)) w.body.dataset.hostTitle = "1";
      mod.render(w.body, data, ctx);
      this._applyLiveTitle(w, baseId, data);            // …y el texto, que sale de los datos recién cargados
      // TAMAÑO PREFERIDO del widget, solo en el primer montaje y solo si el operador no le había dejado uno suyo.
      // Una superficie de ancho fluido (la hoja de resultados) no puede deducir su tamaño del contenido: sin esto
      // encogería a la anchura de su tarjeta más estrecha. Lo declara su manifest (`size`), no lo adivina el canvas.
      if(fresh) this._applyPreferred(w.card, baseId, !!(pos && pos.w), !!(pos && pos.h));
      if(fresh){ w.card.classList.add("boop"); setTimeout(()=>w.card.classList.remove("boop"),460); }
      // Remember signature/module/ctx so refreshData() (SSE-triggered, NO polling) can re-render on change.
      w._dataSig = JSON.stringify(data); w._mod = mod; w._ctx = ctx;
      this._persist();                                  // widget is up → remember it for next refresh
    }catch(e){ console.error("widget mount failed", id, e); this._mountError(w, baseId, String(e&&e.message||e)); }
  }

  // A widget that fails to mount/render NO LONGER disappears silently (bug 2026-07-13: the operator requested the
  // agenda four times and “could not see it” — the card was created and auto-closed in the catch, leaving no trace).
  // It now shows a VISIBLE ERROR state in the card AND REPORTS it to observability (client event at /debug) → the
  // actual render failure is no longer invisible. Invariant: a broken widget = isolated error state, never harms the
  // rest or vanishes.
  _mountError(w, baseId, msg){
    try{
      if(w && w.card){
        clearTimeout(w.card._long); w.card.classList.remove("loading","long");
        const l=w.card.querySelector(".hb-load"); if(l) l.remove();
        if(w.body) w.body.innerHTML =
          '<div style="padding:16px;color:var(--hb-muted,#8a95a5);font-size:13px;line-height:1.4">'
          +tr("desktop.load_failed")+'<br><small style="opacity:.8">'
          +String(msg||"error").replace(/[<>&]/g,"").slice(0,140)+'</small></div>';
      }
    }catch(_){}
    try{ fetch("/api/client-log",{method:"POST",headers:{"Content-Type":"application/json"},
         body:JSON.stringify({label:"widget mount failed", text:(baseId||"?")+" — "+String(msg||"").slice(0,200)})}); }catch(_){}
  }

  // Transient widget → the activity rail above the orb. Text that grows up from the spectrum, then auto-fades.
  // One at a time (re-showing replaces it). Renders the widget's own UI but chrome-free, anchored to the orb.
  async _showActivity(id, q, providedData=null){
    const rail=this.activity; if(!rail) return;
    const desk = this;                                       // see the `show()` note explaining why not `self`
    clearTimeout(this._actTimer);
    rail.innerHTML="";
    const item=document.createElement("div"); item.className="hb-act"; rail.appendChild(item);
    const mount=document.createElement("div"); mount.textContent="…"; item.appendChild(mount);   // widget mounts here (keeps .hb-act chrome)
    this._actId=id;
    try{
      const data = providedData!=null ? providedData
                 : await fetch(`/widgets/${id}/data`+(q?`?q=${encodeURIComponent(q)}`:"")).then(r=>r.json());
      const mod=await import(`/widgets/${id}/widget.js`+(this._ver[id]?`?v=${this._ver[id]}`:""));
      if(data.error){ if(this._actId===id){rail.innerHTML="";this._actId=null;} return; }
      mount.textContent="";
      const ctx={ action:async(name,payload)=>{ try{return await fetch(`/widgets/${id}/action`,{method:"POST",
          headers:{"Content-Type":"application/json"},body:JSON.stringify({action:name,payload:{...(payload||{}),q}})}).then(r=>r.json());}catch(_){return null;} },
        close:()=>{ clearTimeout(this._actTimer); rail.innerHTML=""; this._actId=null; },
        get running(){ return desk._running; } };            // V2-092: same contract as on a normal card
      mod.render(mount, data, ctx);
      this._actTimer=setTimeout(()=>{                     // transient: let it linger, then fade and clear the rail
        item.style.transition="opacity .6s"; item.style.opacity="0";
        setTimeout(()=>{ if(this._actId===id){ rail.innerHTML=""; this._actId=null; } },600);
      }, 15000);
    }catch(e){ console.error("activity widget failed", id, e); if(this._actId===id){rail.innerHTML="";this._actId=null;} }
  }

  // CREATE A NEW WIDGET ON DEMAND: the brain emitted [[create:id]]spec[[/create]] for a widget that doesn't exist
  // yet. Show a "building…" placeholder, ask the server to generate it (headless Claude Code), then show the real
  // widget. Natural + simple for the user: they just asked for it by voice.
  async createWidget(id, spec=""){
    const rid = await this._resolve(id);
    if(this._busy.has(rid)) return;                                          // an agent is already building/editing this
    if(this._meta && this._meta[rid]){ return this.show(rid, {q:spec}); }   // already exists → just show it
    this._busy.add(rid);
    const card=document.createElement("div"); card.className="hb-win loading long building"; card.dataset.wid=id;
    const load=document.createElement("div"); load.className="hb-load";
    const cap=document.createElement("div"); cap.className="hb-cap"; cap.textContent=tr("desktop.creating");
    card.append(load,cap); this.stage.appendChild(card);
    this._place(card); this._bringFront(card); requestAnimationFrame(()=>card.classList.add("in"));
    try{
      const r=await fetch("/widgets/generate",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id, spec})}).then(r=>r.json());
      if(r && r.ok){
        card.classList.remove("in"); setTimeout(()=>card.remove(),200);
        this._ids=null; this._meta=null;                      // refresh the catalog so the new widget is known
        await this.show(r.id||id, {q:spec});
      } else {
        const l=card.querySelector(".hb-load"); if(l)l.remove();
        cap.className="hb-cap err"; cap.textContent=tr("desktop.create_failed", { error: (r&&r.error)||"error" });
        setTimeout(()=>{card.classList.remove("in");setTimeout(()=>card.remove(),200);},4000);
      }
    }catch(e){ console.error("createWidget failed", e); card.classList.remove("in"); setTimeout(()=>card.remove(),200); }
    finally{ this._busy.delete(rid); }
  }

  // MODIFY an existing widget on demand (atomic agent edits widgets/<id>/), then re-render it. Cache-bust the
  // ES module so the new widget.js actually loads (browsers cache modules by URL).
  async modifyWidget(id, change=""){
    const rid = await this._resolve(id);
    if(this._busy.has(rid)) return;                  // don't stack agents on the same widget (rapid re-modify)
    this._busy.add(rid);
    const open = this.wins.has(rid);
    if(open){ const cap=document.createElement("div"); cap.className="hb-cap"; cap.textContent=tr("desktop.updating");
      this.wins.get(rid).card.appendChild(cap); }
    try{
      const r=await fetch("/widgets/modify",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:rid, change})}).then(r=>r.json());
      if(r && r.ok){
        this._ver[rid]=Date.now();                 // bust the module cache so the edited widget.js loads
        await this.show(rid, {q:change});           // re-render in place
      }
    }catch(e){ console.error("modifyWidget failed", e); }
    finally{ this._busy.delete(rid); }
  }

  // DELETE a widget for good: the brain emitted [[delete:id]]. Close the card, ask the server to remove the
  // widget folder + its private store, and drop the cached catalog so identify()/create stop knowing the id.
  async deleteWidget(id){
    const rid = await this._resolve(id);
    if(this._busy.has(rid)) return;                  // an agent is building/editing it — don't delete under it
    this._busy.add(rid);
    try{
      this.close(rid);
      const r=await fetch(`/widgets/${rid}`,{method:"DELETE"}).then(r=>r.json());
      if(r && r.ok){ this._ids=null; this._meta=null; }
      else console.warn("deleteWidget:", (r&&r.error)||"error");
    }catch(e){ console.error("deleteWidget failed", e); }
    finally{ this._busy.delete(rid); }
  }

  // CONFIRM an irreversible action (delete) ON the card: bring the widget up so the user SEES which one, then
  // overlay a Sí/No. Host-level chrome — works for ANY widget without touching its widget.js. Buttons resolve via
  // POST /widgets/{id}/confirm; voice ("sí/no") resolves it backend-side, which fires confirm-cancel/delete here.
  async showConfirm(rawId, {question="", action=""}={}){
    const rid = await this._resolve(rawId);
    if(!this.wins.has(rid)) await this.show(rid);                 // surface it so it's clear WHAT is being deleted
    const w = this.wins.get(rid); if(!w) return;
    let ov = w.card.querySelector(".hb-confirm");
    if(!ov){ ov=document.createElement("div"); ov.className="hb-confirm"; w.card.appendChild(ov); }
    ov.innerHTML="";
    const msg=document.createElement("div"); msg.className="hb-confirm-msg"; msg.textContent=question||tr("desktop.confirm_default");
    const row=document.createElement("div"); row.className="hb-confirm-row";
    const no=document.createElement("button"); no.className="hb-confirm-no"; no.textContent=tr("desktop.no");
    const yes=document.createElement("button"); yes.className="hb-confirm-yes";
    // Bug real 2026-07-25 (reporte del operador): el botón de confirmar decía SIEMPRE "Borrar", aunque la
    // confirmación fuera de OTRA cosa (conectar a un cluster, enviar un mensaje…) — confuso y directamente
    // engañoso ("¿Conectar al cluster...? Borrar" no tiene sentido). `action` = la CLASE que ya manda
    // `widgets/confirm.py` ("delete" | "data") — "delete" sigue diciendo "Borrar" (comportamiento previo
    // intacto); cualquier otra data-op (connect_cluster, send, o lo que declare cualquier widget futuro) usa
    // un texto genérico correcto para TODAS, sin tener que enumerar cada acción posible.
    yes.textContent = action === "delete" ? tr("desktop.delete_btn") : tr("desktop.confirm_btn");
    no.onclick=()=>this._resolveConfirm(rid,false);
    yes.onclick=()=>this._resolveConfirm(rid,true);
    row.append(no,yes); ov.append(msg,row);
    this._bringFront(w.card);
    requestAnimationFrame(()=>ov.classList.add("in"));
  }
  _resolveConfirm(id, ok){
    this.hideConfirm(id);                                          // optimistic — the backend emits delete/cancel too
    fetch(`/widgets/${id}/confirm`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ok})}).catch(()=>{});
  }
  hideConfirm(id){ const w=this.wins.get(id); if(!w)return; const ov=w.card.querySelector(".hb-confirm");
    if(ov){ ov.classList.remove("in"); setTimeout(()=>{if(ov.parentNode)ov.remove();},180); } }
  // Backend ALREADY deleted the widget (widgets/lifecycle) and told us over SSE → just close the card and drop the
  // cached catalog so identify()/create stop knowing the id. (No endpoint call — the delete already happened.)
  onDeleted(id){ this._ids=null; this._meta=null; this.close(id); }

  // Live data, NO POLLING: widgets/store.py emits ONE SSE "widget/data" event whenever a widget's store is
  // actually written (its own ctx.action, or Hermes via [[widget.data]]) — sse.js routes it here. Re-fetch once
  // and re-render ONLY if the data actually changed (diff by JSON signature) and ONLY if the widget is open.
  async refreshData(id){
    const w = this.wins.get(id);
    if(!w || !w._mod) return;              // not open, or hasn't finished its first render yet — nothing to do
    if(w._refreshing) return;              // coalesce a burst of saves into whichever fetch is already in flight
    w._refreshing = true;
    try{
      const data = await fetch(`/widgets/${w.base||id}/data`+(w.q?`?q=${encodeURIComponent(w.q)}`:"")).then(r=>r.json());
      if(data.error) return;
      const sig = JSON.stringify(data);
      const ww = this.wins.get(id);        // re-check: it may have been closed while the fetch was in flight
      if(ww && sig !== ww._dataSig){
        ww._dataSig = sig;
        ww._mod.render(ww.body, data, ww._ctx);
        // Y la cabecera sigue a los datos: una búsqueda nueva cambia el título, y dejarlo con el de la anterior
        // sería un rótulo que MIENTE sobre lo que hay debajo.
        this._applyLiveTitle(ww, ww.base || id, data);
      }
    }catch(_){}
    finally{ w._refreshing = false; }
  }

  _unwatchSize(card){ try{ if(card && card._ro){ card._ro.disconnect(); card._ro=null; } }catch(_){} }

  close(id){
    if(this._actId===id){ clearTimeout(this._actTimer); if(this.activity)this.activity.innerHTML=""; this._actId=null; return; }
    const w=this.wins.get(id);
    if(w) this._closeAliases(w);                        // V2-082: limpia el listener del panel de alias si estaba abierto
    if(!w){
      // ROBUSTEZ (2026-07-14): la tarjeta puede estar en el DOM pero NO en `wins` (huérfana tras una reconexión/
      // reinicio → desync). Antes `close` la ignoraba en silencio y el operador "seguía viendo el widget" pese a
      // pedir cerrarlo N veces. Barremos el DOM por si acaso: si hay tarjeta con ese id, la quitamos igual.
      const orphan=this.stage&&this.stage.querySelector(`.hb-win[data-wid="${(id||"").replace(/"/g,'')}"]`);
      if(orphan){ orphan.classList.remove("in"); setTimeout(()=>orphan.remove(),220); this._persist(); }
      return;
    }
    // Cerrar la tarjeta de una TAREA de NAVEGADOR (navegador::<taskid>) cierra también su PESTAÑA en el navegador
    // real y cancela la tarea si seguía viva — así no se acumulan pestañas ni tareas huérfanas.
    //
    // V2-259 — la condición era `id.includes("::")` con `w.base||"navegador"` de reserva, o sea que daba por
    // hecho que la ÚNICA pieza instanciada era el navegador. Desde que la hoja de resultados también lo está
    // (results::<corr_id>), cerrar una hoja mandaba un `cancel_task` a `results`: una acción que ese widget no
    // declara, y por tanto una llamada que solo puede acabar en nada o en un DENY. Cerrar una vista no cancela
    // un encargo, así que se comprueba la pieza en vez de asumirla.
    if(id.includes("::") && (w.base||"")==="navegador"){
      const taskId=id.split("::")[1];
      try{ fetch(`/widgets/navegador/action`,{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({action:"cancel_task",payload:{task_id:taskId}})}); }catch(_){}
    }
    this._unwatchSize(w.card);      // a closed card must not keep an observer alive
    w.card.classList.remove("in");
    setTimeout(()=>w.card.remove(),220);
    this.wins.delete(id);
    this._persist();                                    // closing it removes it from the saved desktop too
  }
  closeAll(){
    [...this.wins.keys()].forEach(id=>this.close(id));
    // BARRIDO DEL DOM (2026-07-14): "cierra todo" DEBE dejar el canvas limpio SIEMPRE, aunque haya tarjetas
    // huérfanas fuera de `wins` (desync tras reconexión/reinicio → el bug de "no eres capaz de cerrar la agenda"
    // con el close disparándose una y otra vez sin efecto). Quitamos toda .hb-win que quede en el escenario.
    if(this.stage){ this.stage.querySelectorAll(".hb-win").forEach(card=>{ this._unwatchSize(card); card.classList.remove("in"); setTimeout(()=>card.remove(),220); }); }
    this.wins.clear();
    clearTimeout(this._actTimer); if(this.activity)this.activity.innerHTML=""; this._actId=null;
    try{ localStorage.removeItem("hb_desktop"); }catch(_){}   // que un reconnect/restore no reviva lo cerrado
    this._reportOpen();                                       // el ESTADO del cerebro también a vacío
  }

  // Reposition an OPEN widget on the canvas. `where` accepts EN/ES tokens (left/izquierda, right/derecha,
  // center/centro, top/arriba, bottom/abajo, and combos like "top-left"). Pure UI — idempotent, persists.
  // The brain lacked any move capability, so "muévelo a la izquierda" was confabulated; this makes it real.
  move(id, where){
    const w = this.wins.get(id); if(!w || !w.card) return false;
    const card = w.card, s = String(where||"").toLowerCase();
    const W = card.offsetWidth || this.tile.w, H = card.offsetHeight || this.tile.h;
    const pad = this.tile.pad, top = this.tile.top;
    const maxX = Math.max(pad, innerWidth - W - pad), maxY = Math.max(top, innerHeight - H - pad);
    let x = parseInt(card.style.left) || pad, y = parseInt(card.style.top) || top;
    const L=/left|izquierd/.test(s), R=/right|derech/.test(s), C=/cent|middle|medio/.test(s);
    const T=/top|arrib|encim/.test(s), B=/bottom|abaj|debaj/.test(s);
    if(L) x=pad; else if(R) x=maxX; else if(C && !T && !B) x=Math.round((innerWidth-W)/2);
    if(T) y=top; else if(B) y=maxY; else if(C && !L && !R) y=Math.round((innerHeight-H)/2);
    card.style.left = x+"px"; card.style.top = y+"px";
    this._bringFront(card); this._persist();
    return true;
  }

  // "PANTALLA COMPLETA" son DOS cosas distintas y hasta hoy solo existía una. La nativa (Fullscreen API) tapa el
  // resto de zaelar: perfecta para un vídeo, pésima para una hoja de resultados — el operador la agranda JUSTO
  // para seguir hablando con el agente sobre lo que está mirando ("acótalo a 42 pies"), y sin orbe ni chat no
  // puede. Así que por defecto se MAXIMIZA dentro de la app (ocupa casi todo el lienzo, la voz sigue ahí), y la
  // nativa se reserva a los widgets que la declaran en su manifest (`"fullscreen":"native"`, p.ej. el vídeo).
  // La decisión es del WIDGET, no del modelo: una elección declarada no se enruta mal.
  fullscreen(id){
    const meta = this._meta && this._meta[(id||"").split("::")[0]];
    if(meta && meta.fullscreen === "native") return this.nativeFullscreen(id);
    return this.maximize(id);
  }

  // TRUE fullscreen (native Fullscreen API — Escape exits it, no extra tag needed). Toggle: calling it again
  // while already fullscreen exits. Bug real 2026-07-23: "ponlo a pantalla completa" had NO real capability
  // behind it — the brain confabulated success on a request it couldn't act on.
  nativeFullscreen(id){
    const w = this.wins.get(id); if(!w || !w.card) return false;
    const card = w.card;
    if(document.fullscreenElement === card){ document.exitFullscreen?.(); return true; }
    const req = card.requestFullscreen || card.webkitRequestFullscreen;
    if(!req) return false;
    try{ req.call(card); } catch(_){ return false; }
    return true;
  }

  // MAXIMIZAR dentro de la app: la tarjeta ocupa casi todo el lienzo sin tapar zaelar. Es un TOGGLE y guarda la
  // geometría anterior, así que volver deja la tarjeta exactamente donde y como estaba (si no, "ponlo grande"
  // sería una operación de ida sin vuelta y el operador tendría que recolocarla a mano).
  maximize(id){
    const w = this.wins.get(id); if(!w || !w.card) return false;
    const card = w.card, pad = this.tile.pad, top = this.tile.top;
    if(card._restore){
      const r = card._restore; card._restore = null;
      card.style.left=r.left; card.style.top=r.top; card.style.width=r.w; card.style.height=r.h;
      card.style.maxWidth=r.mw; card.style.maxHeight=r.mh;
    } else {
      card._restore = {left:card.style.left, top:card.style.top, w:card.style.width, h:card.style.height,
                       mw:card.style.maxWidth, mh:card.style.maxHeight};
      const x0 = this.minX() + pad;                      // V2-538: maximized still respects the docked rail
      card.style.maxWidth="none"; card.style.maxHeight="none";
      card.style.left=x0+"px"; card.style.top=top+"px";
      card.style.width=(innerWidth - x0 - pad)+"px";
      card.style.height=(innerHeight - top - pad)+"px";
    }
    this._bringFront(card); this._persist(); this._uiAudit("maximize", id);
    return true;
  }

  // ---- MANUAL resizing: eight handles (four corners + four edges) ----
  _addHandles(card){
    for(const dir of ["n","s","e","w","ne","nw","se","sw"]){
      const h=document.createElement("div"); h.className="hb-rz hb-rz-"+dir; h.dataset.dir=dir;
      card.appendChild(h);
    }
  }
  _applyGeom(card, w, h){
    if(w){ card.style.width = w; card.style.maxWidth="none"; }
    if(h){ card.style.height = h; card.style.maxHeight="none"; }
  }
  // Preferred size declared by the widget (`manifest.size`). A card gets a FIXED default footprint and the
  // content scrolls inside it (operator, 2026-09-01): without an explicit height the card auto-sizes to its
  // content and GROWS line by line as a worker streams text in. `haveW`/`haveH` mark dimensions the operator
  // already saved for this card — those are his and stay; only the missing ones are filled. (Before V2-538 a
  // card restored with a saved width but an empty height — the layout format of every card saved before sizes
  // were persisted — kept auto height forever.)
  _applyPreferred(card, baseId, haveW, haveH){
    const size = this._meta && this._meta[baseId] && this._meta[baseId].size;
    if(!size) return;
    const maxW = innerWidth - this.minX() - this.tile.pad*2, maxH = innerHeight - this.tile.top - this.tile.pad;
    if(size.w && !haveW) card.style.width  = Math.min(Number(size.w), maxW) + "px";
    if(size.h && !haveH) card.style.height = Math.min(Number(size.h), maxH) + "px";
    if((size.w && !haveW) || (size.h && !haveH)){ card.style.maxWidth="none"; card.style.maxHeight="none"; }
    // Reposition: the card was placed at the default size (400×340) and may have grown beyond the canvas.
    const L=parseInt(card.style.left)||this.tile.pad, T=parseInt(card.style.top)||this.tile.top;
    card.style.left = Math.max(this.minX()+this.tile.pad, Math.min(L, innerWidth - card.offsetWidth - this.tile.pad)) + "px";
    card.style.top  = Math.max(this.tile.top, Math.min(T, innerHeight - card.offsetHeight - this.tile.pad)) + "px";
  }
  _wireResize(card, id){
    const MIN_W = 240, MIN_H = 150;
    let dir="", sx=0, sy=0, sw=0, sh=0, sl=0, st=0, live=false;
    const onMove = e => {
      if(!live) return;
      const dx = e.clientX - sx, dy = e.clientY - sy;
      let w=sw, h=sh, l=sl, t=st;
      if(dir.includes("e")) w = sw + dx;
      if(dir.includes("s")) h = sh + dy;
      if(dir.includes("w")){ w = sw - dx; l = sl + dx; }
      if(dir.includes("n")){ h = sh - dy; t = st + dy; }
      // Los mínimos se aplican ANTES de mover el origen: si no, arrastrar el borde izquierdo más allá del ancho
      // mínimo seguía desplazando la tarjeta a la derecha y parecía que se estaba moviendo, no redimensionando.
      if(w < MIN_W){ if(dir.includes("w")) l = sl + (sw - MIN_W); w = MIN_W; }
      if(h < MIN_H){ if(dir.includes("n")) t = st + (sh - MIN_H); h = MIN_H; }
      l = Math.max(this.minX(), l); t = Math.max(0, t);
      w = Math.min(w, innerWidth - l); h = Math.min(h, innerHeight - t);
      // Snapped like placement and drag (V2-551). Snapping only SOME of the three produces edges that almost
      // line up, which reads worse than no grid: a card dragged to x=200 next to one resized to x=203.
      card.style.left=this._snap(l)+"px"; card.style.top=this._snap(t)+"px";
      card.style.width=this._snap(w)+"px"; card.style.height=this._snap(h)+"px";
    };
    card.addEventListener("pointerdown", e => {
      const h = e.target.closest && e.target.closest(".hb-rz");
      if(!h || !card.contains(h)) return;
      dir = h.dataset.dir || ""; if(!dir) return;
      const r = card.getBoundingClientRect();
      sx=e.clientX; sy=e.clientY; sw=r.width; sh=r.height; sl=r.left; st=r.top; live=true;
      card._restore = null;                       // redimensionar a mano invalida el "volver" de maximizar
      card.style.maxWidth="none"; card.style.maxHeight="none";
      card.classList.add("rz"); this._bringFront(card);
      h.setPointerCapture(e.pointerId); e.preventDefault(); e.stopPropagation();
      h.addEventListener("pointermove", onMove);
      const end = () => { live=false; card.classList.remove("rz");
        h.removeEventListener("pointermove", onMove);
        this._persist(); this._uiAudit("resize", id); };
      h.addEventListener("pointerup", end, {once:true});
      h.addEventListener("pointercancel", end, {once:true});
    });
  }

  // Resize an OPEN widget to given dimensions (width/height in px). `opts` = {width?:number, height?:number}.
  // Clamped to viewport limits. Pure UI — idempotent, persists. HERMES-ONLY (not safe for the fast layer).
  resize(id, opts = {}){
    const w = this.wins.get(id); if(!w || !w.card) return false;
    const card = w.card;
    card._restore = null;
    if(opts.width != null){
      const maxW = innerWidth - this.tile.pad * 2;
      card.style.width = Math.max(120, Math.min(opts.width, maxW)) + "px";
      card.style.maxWidth = "none";
    }
    if(opts.height != null){
      const maxH = innerHeight - this.tile.top - this.tile.pad;
      // ALTO REAL, no `max-height`. Con max-height la tarjeta seguía encogiéndose al contenido, así que "hazla
      // más alta" no hacía nada visible salvo que el contenido ya desbordara — y el tamaño tampoco se podía
      // guardar (no había ninguno). Ahora es el mismo eje que mueve el tirador de la esquina.
      card.style.height = Math.max(120, Math.min(opts.height, maxH)) + "px";
      card.style.maxHeight = "none";
    }
    this._persist();
    return true;
  }

  // ---- placement: scan the VISIBLE viewport for a spot where the widget FITS without overlapping any other
  // widget, the camera, or the voice orb. While there's free room nothing ever lands on top. Only when nothing
  // fits do we cascade on top. The default tile size is reserved while the card is still loading (its real size
  // isn't known yet); later widgets collide against the LIVE rects, so they tuck around the rendered sizes. ----
  _place(card){
    const W=Math.max(card.offsetWidth, this.tile.w), H=Math.max(card.offsetHeight, this.tile.h);
    const pad=this.tile.pad, top=this.tile.top, step=this.grid, obs=this._obstacles(card);
    // The scan ORIGIN is snapped up to the grid, not just the step: starting at an unaligned x (the rail's
    // right edge + pad) and stepping by 5 keeps that offset forever, so every card lands 4px off the grid and
    // the grid buys nothing.
    const xmin=this._snapUp(Math.max(pad, this.minX()+pad)), ytop=this._snapUp(top);
    // COLUMN-MAJOR, and that order IS the feature (V2-551): the operator asked for cards «colocados
    // verticalmente pegados unos a otros». Row-major fills left-to-right first and scatters a session across
    // the top of the screen; sweeping y INSIDE x stacks each new card under the previous one and only starts a
    // new column when this one is full — which is also how a person tidies a desk.
    for(let x=xmin; x+W<=innerWidth-pad; x+=step){
      for(let y=ytop; y+H<=innerHeight-pad; y+=step){
        const r={left:x, top:y, right:x+W, bottom:y+H};
        if(!obs.some(o=>_overlap(r,o))){ card.style.left=x+"px"; card.style.top=y+"px"; return; }
      }
    }
    // NOTHING FITS. The old fallback cascaded near the centre with `Math.max` on both axes and no upper bound,
    // so a tall or wide card hung off the bottom-right — the operator saw exactly that: «se abre un widget de
    // imagen y medio widget está en el área visible y medio aparece como si estuviera fuera de la pantalla».
    // A clamp is not enough either: it would pile every overflow card in the same corner. So we put it in the
    // LARGEST FREE GAP (his words) and bring it to the front, which is the honest answer to «there is no room»:
    // it overlaps as little as possible, it is wholly visible, and it is the one you can see and move.
    const gap = this._largestGap(obs, W, H, xmin, top, pad);
    card.style.left = gap.x + "px";
    card.style.top  = gap.y + "px";
    this._fit(card);
    // (no `_bringFront` here: every caller of `_place` already does it. A second call measured nothing and
    // made a guard look like it was testing this branch when it was testing the caller.)
  }

  // The free-est spot for a WxH card: scan the grid and keep the position whose overlap with existing cards is
  // smallest. Not a rectangle-packing algorithm — the canvas is a few dozen cards at 5px resolution, and the
  // answer only has to be the one a person would point at.
  _largestGap(obs, W, H, xmin, top, pad){
    const step = Math.max(this.grid, 20);          // coarser here: this only runs when nothing fits at all
    const maxX = Math.max(xmin, innerWidth - W - pad), maxY = Math.max(top, innerHeight - H - pad);
    let best = {x: xmin, y: top, cover: Infinity};
    for(let x=xmin; x<=maxX; x+=step){
      for(let y=top; y<=maxY; y+=step){
        const r={left:x, top:y, right:x+W, bottom:y+H};
        let cover = 0;
        for(const o of obs){
          const ow = Math.min(r.right,o.right) - Math.max(r.left,o.left);
          const oh = Math.min(r.bottom,o.bottom) - Math.max(r.top,o.top);
          if(ow>0 && oh>0) cover += ow*oh;
        }
        if(cover < best.cover){ best = {x, y, cover}; if(!cover) return best; }
      }
    }
    return best;
  }

  // A card is ALWAYS WHOLLY VISIBLE, and snapped to the grid (V2-551). This is the guarantee the canvas lacked:
  // `_place` reserves the DEFAULT tile while a card is still loading, so a widget that renders bigger than
  // 400×340 — an image viewer with twelve photos — grew past the edge it had been fitted to and nothing pulled
  // it back. There was a re-clamp, but only inside `_applyPreferred`, i.e. only for widgets that DECLARE a size.
  // A card too large for the viewport is shrunk rather than cropped: half a card is not a smaller card, it is a
  // card with its content missing.
  _fit(card){
    if(!card || card.classList.contains("hb-minned")) return;
    const pad=this.tile.pad, top=this.tile.top, xmin=Math.max(pad, this.minX()+pad);
    const availW = Math.max(240, innerWidth - xmin - pad), availH = Math.max(150, innerHeight - top - pad);
    if(card.offsetWidth  > availW){ card.style.maxWidth ="none"; card.style.width  = this._snap(availW)+"px"; }
    if(card.offsetHeight > availH){ card.style.maxHeight="none"; card.style.height = this._snap(availH)+"px"; }
    const L = parseInt(card.style.left)||xmin, T = parseInt(card.style.top)||top;
    card.style.left = this._snap(Math.max(xmin, Math.min(L, innerWidth  - card.offsetWidth  - pad))) + "px";
    card.style.top  = this._snap(Math.max(top,  Math.min(T, innerHeight - card.offsetHeight - pad))) + "px";
  }

  _snap(n){ const g=this.grid||1; return Math.round(Number(n||0)/g)*g; }
  _snapUp(n){ const g=this.grid||1; return Math.ceil(Number(n||0)/g)*g; }

  // A card is placed BEFORE it knows its own size: `_place` reserves the default 400×340 tile while the module
  // loads, and the widget then renders whatever it renders — twelve photos, a full results sheet. That is the
  // real shape of «medio widget fuera de la pantalla»: the fit was correct for the tile and wrong for the card.
  // So the fit is not a one-off at open time, it is a STANDING guarantee.
  //
  // It never fights the operator: only a card that actually STICKS OUT is touched, so dragging, resizing and
  // maximizing are all left alone — and `_restore` (maximize's saved geometry) is respected, because a maximized
  // card is deliberately the size of the canvas and pulling it in would undo the very thing that was asked for.
  _watchSize(card){
    if(typeof ResizeObserver !== "function" || card._ro) return;
    let t = 0;
    card._ro = new ResizeObserver(() => {
      clearTimeout(t);                        // a render can fire this many times in one frame
      t = setTimeout(() => {
        if(card._restore) return;             // maximized on purpose
        const pad=this.tile.pad, top=this.tile.top, xmin=Math.max(pad, this.minX()+pad);
        const r = card.getBoundingClientRect();
        const out = r.right > innerWidth - pad || r.bottom > innerHeight - pad
                 || r.left < xmin - 1 || r.top < top - 1;
        if(out){ this._fit(card); this._persist(); }
      }, 80);
    });
    try{ card._ro.observe(card); }catch(_){}
  }

  // ORDENAR el canvas en una rejilla alineada (V2-464, showcase). One command, invocable from anywhere the
  // SSE reaches (POST /api/canvas/arrange -> widget/arrange), like the OS window-snap the operator asked for.
  // The area avoids a DOCKED chat wall and the orb strip at the bottom; every card gets the same cell so a
  // recording reads clean. Sizes clamp to the card's own max-width/height, so nothing distorts.
  // RECOLOCAR sin tocar el tamaño (V2-552). The operator asked for two different bulk gestures and they were
  // one: `arrange()` tiles everything into equal cells, which also RESIZES — perfect for «ponlo todo en
  // pantalla», wrong for «optimiza los huecos», because it flattens a sheet he had deliberately made large.
  // This one keeps every card exactly the size he left it and only closes the gaps between them, packing them
  // top-to-bottom in columns — the same order `_place` uses, so a compacted canvas and a grown one look alike.
  //
  // BIGGEST FIRST, and that is not cosmetic: packing a large card after several small ones leaves it nowhere to
  // go, and it would end up in the largest-gap fallback ON TOP of the tidy ones — a «tidy» gesture that buries
  // a card is worse than not tidying.
  compact(){
    this.revealAll();          // a layout with invisible holes in it is not a layout
    const cards=[...this.wins.values()].map(w=>w.card).filter(c=>c && c.isConnected);
    if(!cards.length) return {ok:true, n:0};
    const pad=this.tile.pad, top=this._snapUp(this.tile.top);
    const xmin=this._snapUp(Math.max(pad, this.minX()+pad)), step=this.grid;
    const placed=[];
    const fixed=this._obstacles(null).filter(r=>!cards.some(c=>{
      const cr=c.getBoundingClientRect(); return Math.abs(cr.left-r.left)<1 && Math.abs(cr.top-r.top)<1; }));
    // SIZES SETTLE FIRST. A card wider than the canvas is shrunk by `_fit` — and if that happens AFTER we have
    // packed around its old size, the standing fit guarantee moves it back to the corner and lands it on top of
    // the cards we just tidied. Measured: an oversized card packed at 1900px wide, then shrunk to 1177 and
    // clamped to (xmin, top), sitting on two neighbours. Pack against final sizes, never intended ones.
    cards.forEach(c=>this._fit(c));
    cards.sort((a,b)=>(b.offsetWidth*b.offsetHeight)-(a.offsetWidth*a.offsetHeight));
    for(const c of cards){
      c._restore=null;                                   // a compacted card is no longer «maximized, restorable»
      const W=c.offsetWidth, H=c.offsetHeight;
      let put=false;
      for(let x=xmin; !put && x+W<=innerWidth-pad; x+=step){
        for(let y=top; y+H<=innerHeight-pad; y+=step){
          const r={left:x, top:y, right:x+W, bottom:y+H};
          if(![...placed,...fixed].some(o=>_overlap(r,o))){
            c.style.left=x+"px"; c.style.top=y+"px"; placed.push(r); put=true; break;
          }
        }
      }
      if(!put){                                          // genuinely no room at this size: least-overlap, whole
        const g=this._largestGap([...placed,...fixed], W, H, xmin, top, pad);
        c.style.left=g.x+"px"; c.style.top=g.y+"px"; this._fit(c);
        const r=c.getBoundingClientRect(); placed.push({left:r.left,top:r.top,right:r.right,bottom:r.bottom});
      }
    }
    this._persist();
    return {ok:true, n:cards.length};
  }

  arrange(){
    this.revealAll();          // "ordénalo todo" is a show-all gesture: a grid with invisible holes is not a grid
    const cards=[...this.wins.values()].map(w=>w.card).filter(c=>c && c.isConnected);
    if(!cards.length) return {ok:true, n:0};
    const pad=this.tile.pad, y0=this.tile.top, y1=innerHeight-150;   // 150 = orb/status strip
    let x0=Math.max(pad, this.minX()+pad), x1=innerWidth-pad;       // V2-537/538: the rail owns the left edge
    const cw=document.querySelector("#chatwall");
    if(cw && cw.classList.contains("open")){
      const r=cw.getBoundingClientRect();
      if(r.width){
        if(r.left <= innerWidth*0.3) x0=Math.max(x0, r.right+pad);       // docked/floating on the LEFT
        else if(r.right >= innerWidth*0.7) x1=Math.min(x1, r.left-pad);  // …or on the RIGHT
      }
    }
    const n=cards.length;
    const cols=n===1?1:(n<=4?2:Math.ceil(Math.sqrt(n)));
    const rows=Math.ceil(n/cols);
    const cellW=Math.floor((x1-x0-(cols-1)*pad)/cols), cellH=Math.floor((y1-y0-(rows-1)*pad)/rows);
    cards.forEach((c,i)=>{
      const row=Math.floor(i/cols), col=i%cols;
      c.style.left=(x0+col*(cellW+pad))+"px"; c.style.top=(y0+row*(cellH+pad))+"px";
      c.style.width=Math.max(320, cellW)+"px"; c.style.height=Math.max(240, cellH)+"px";
    });
    this._persist();
    return {ok:true, n};
  }

  // Live rects to avoid: every OTHER open widget + the camera unit + the voice orb (so widgets never sit on them).
  // ── V2-537: MINIMIZE — open but off the canvas. The card stays in `wins` and in the brain's open set on
  // purpose (an OS-minimized window is still open: its data lives, widget_data still works); only the pixels go.
  // The widget rail's chip is the way back, so a minimized card is never unknowable — which is the operator's
  // rule: nothing on screen may be fully hidden without a visible trace of it.
  minimize(id){
    const w = this.wins.get(id); if(!w || !w.card) return false;
    w.card.classList.add("hb-minned"); this._persist(); return true;
  }
  reveal(id){
    const w = this.wins.get(id); if(!w || !w.card) return false;
    w.card.classList.remove("hb-minned"); this._bringFront(w.card); this._persist(); return true;
  }
  isMinimized(id){ const w = this.wins.get(id); return !!(w && w.card && w.card.classList.contains("hb-minned")); }
  minimizeAll(){ [...this.wins.keys()].forEach(id=>{ const w=this.wins.get(id); if(w&&w.card)w.card.classList.add("hb-minned"); }); this._persist(); }
  revealAll(){ [...this.wins.keys()].forEach(id=>{ const w=this.wins.get(id); if(w&&w.card)w.card.classList.remove("hb-minned"); }); this._persist(); }

  _obstacles(exceptCard){
    const rects=[];
    this.wins.forEach(w=>{ if(w.card!==exceptCard && !w.card.classList.contains("hb-minned")){
      const r=w.card.getBoundingClientRect(); if(r.width)rects.push(r); } });
    // V2-537 — the OPEN CHAT WALL (and the cron panel, and the widget rail) are obstacles too. Measured on the
    // operator's screen 2026-09-01: a new card landed exactly under the floating chat (z 9001, above every card's
    // 8000 cap by design) and was invisible — the scan avoided widgets, camera and orb, and nothing else.
    for(const sel of ["#me", "#orbwrap", "#chatwall.open", ".cronpanel", "#wrail"]){ const e=document.querySelector(sel);
      if(e){ const r=e.getBoundingClientRect(); if(r.width)rects.push(r); } }
    return rects;
  }

  _bringFront(card){ card.style.zIndex = Math.min(8000, ++this.z); }   // stay BELOW the camera (9000) and orb (100000)

  // reverse lookup: which widget id owns this card? (to attribute a UI action to the correct widget)
  _idOf(card){ for(const [id,w] of this.wins){ if(w && w.card===card) return id; } return ""; }
  // V2-039 — FRONTEND AUDIT: records on the timeline an action the OPERATOR performs manually on a widget
  // (move/resize). The server stamps it with src="user". Fire-and-forget; never breaks the canvas.
  _uiAudit(action, id){ try{ fetch("/api/ui-event",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({kind:"widget",action,id})}); }catch(_){} }

  _wireDrag(card, grip){
    let dx=0,dy=0,drag=false,moved=false;
    grip.addEventListener("pointerdown",e=>{drag=true;moved=false;const r=card.getBoundingClientRect();
      dx=e.clientX-r.left;dy=e.clientY-r.top;this._bringFront(card);grip.setPointerCapture(e.pointerId);e.preventDefault();});
    grip.addEventListener("pointermove",e=>{if(!drag)return;moved=true;
      // Snapped to the grid, and clamped so the card cannot be dragged off the canvas: the operator moves things
      // wherever he wants (V2-551), and «wherever» is still inside the screen.
      let x=Math.max(this.minX(),Math.min(e.clientX-dx,innerWidth-card.offsetWidth));
      let y=Math.max(0,Math.min(e.clientY-dy,innerHeight-card.offsetHeight));
      card.style.left=this._snap(x)+"px";card.style.top=this._snap(y)+"px"; });
    grip.addEventListener("pointerup",()=>{ drag=false; this._persist();   // remember the new position
      if(moved) this._uiAudit("move", this._idOf(card)); });               // …and audit the user's move
  }
}
