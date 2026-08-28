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
  /* La tarjeta es una COLUMNA FLEX con el cuerpo como único scroller (antes scrolleaba la tarjeta entera). El
     cambio lo obliga el redimensionado: con la tarjeta scrolleando, los tiradores de borde —absolutos— se iban
     con el contenido y no se podían agarrar. De paso, la cabecera y el overlay de confirmación dejan de
     desplazarse fuera de la vista en un widget largo. */
  .hb-win{position:absolute;pointer-events:auto;background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#e3e8f0);border-radius:16px;
    box-shadow:var(--hb-shadow-2,0 20px 60px rgba(13,22,34,.22));padding:30px 16px 16px;max-width:92vw;max-height:82vh;overflow:hidden;
    display:flex;flex-direction:column;
    opacity:0;transform:scale(.9) translateY(10px);transition:opacity .2s,transform .2s cubic-bezier(.2,.9,.3,1.2)}
  .hb-win.in{opacity:1;transform:none}
  /* El SCROLLER es un envoltorio del canvas, NO el div del widget: un widget.js hace el.className="…" y se lleva
     por delante cualquier clase que le pongamos a su raíz (así que una regla sobre .hb-body no aplicaba a nadie).
     El widget sigue siendo dueño absoluto de su div; el scroll es chrome de la tarjeta, como el grip o la ×.
     OJO al editar este bloque: es un template literal — nada de acentos graves aquí dentro. */
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}
  /* Redimensionar SIN transición: con la de arriba puesta, arrastrar una esquina iba a tirones (cada frame
     animaba 200ms hacia el tamaño nuevo). Se apaga mientras dura el gesto. */
  .hb-win.rz{transition:none;user-select:none}
  .hb-grip{position:absolute;top:7px;left:8px;width:26px;height:26px;border:none;border-radius:7px;cursor:grab;
    background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted-2,#9aa7b8);display:flex;align-items:center;justify-content:center;touch-action:none;z-index:3}
  .hb-grip:active{cursor:grabbing}
  .hb-x{position:absolute;top:7px;right:8px;width:26px;height:26px;border:none;border-radius:7px;cursor:pointer;
    background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted,#5b6b82);font-size:14px;z-index:3}
  .hb-max{position:absolute;top:7px;right:38px;width:26px;height:26px;border:none;border-radius:7px;cursor:pointer;
    background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted,#5b6b82);font-size:12px;line-height:1;z-index:3}
  .hb-max:hover,.hb-x:hover{color:var(--hb-ink,#e8edf5)}
  /* TIRADORES DE REDIMENSIÓN — cuatro esquinas y cuatro bordes. El operador pidió poder agarrar «las esquinas del
     widget»: son invisibles hasta que pasas por encima (una tarjeta llena de asas es ruido) pero tienen 14px de
     zona sensible, que es lo que hace que se puedan coger sin apuntar con precisión de cirujano. */
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
  /* HEADER del widget (V2-082): el NOMBRE por el que se abre + un botón de config que despliega los ALIAS.
     Vive en la franja superior de 30px, entre el grip (izq) y la × (der). Genérico para TODO widget — el
     widget.js no lo toca. El nombre sale de _meta/registry (manifest.name|title). */
  /* right:70px, no 40: los botones de la derecha son DOS desde que existe ⤢ (ocupa de 38 a 64), así que la
     cabecera se le metía por debajo — invisible con un nombre corto y centrado, evidente con un título largo. */
  .hb-head{position:absolute;top:6px;left:40px;right:70px;height:24px;display:flex;align-items:center;justify-content:center;
    gap:5px;pointer-events:none}
  /* TÍTULO VIVO (2026-08-12): cuando la cabecera lleva la TAREA en vez del nombre del widget, se alinea a la
     izquierda y ocupa todo el hueco. Un rótulo corto se centra bien; una frase se lee desde el margen, y centrarla
     desperdicia la mitad del ancho en aire simétrico que no hace falta. */
  .hb-head.live{justify-content:flex-start}
  .hb-head.live .hb-name{max-width:100%;font-weight:600}
  .hb-name{pointer-events:auto;max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border:none;cursor:pointer;
    background:transparent;color:var(--hb-ink,#e8edf5);font:600 12px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .hb-name:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-cfg{pointer-events:auto;border:none;border-radius:6px;cursor:pointer;width:20px;height:20px;padding:0;font-size:11px;
    background:transparent;color:var(--hb-muted-2,#9aa7b8)}
  .hb-cfg:hover{color:var(--hb-ink,#e8edf5);background:var(--hb-bubble,#f1f4f9)}
  /* Desplegable de ALIAS (host-level, patrón de .hb-confirm): lista de chips editable + añadir. */
  .hb-aliases{position:absolute;top:30px;left:12px;right:12px;z-index:6;padding:12px;border-radius:12px;
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
     (delete) asks Sí/No ON the card. Fed by the confirm SSE events; resolves via POST /widgets/{id}/confirm. */
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
    this.restore();                                        // bring back the user's desktop (open widgets + positions)
  }

  // Estado del agente → los widgets. Lo llama main.js reactivamente desde `store.powerOff()`.
  setRunning(on){ this._running = !!on; }

  // ---- PERSISTENCE: the desktop is the user's state. Open widgets + their positions survive a refresh / reopen. ----
  // Geometría restaurable del escritorio: qué tarjetas, con qué consulta y dónde. Las tarjetas de INSTANCIA
  // (`navegador::t3` = una pestaña/tarea concreta) siguen siendo efímeras — su tarea muere con el proceso que la
  // conducía, así que restaurarlas pintaría una pestaña que ya no existe. La tarjeta BASE del navegador SÍ se
  // restaura desde 2026-08-12: era el único widget excluido por nombre, y como es justo el que está en pantalla
  // durante una tarea web, recargar la página en mitad de una búsqueda dejaba el escritorio literalmente en blanco.
  // El TAMAÑO viaja con la posición desde 2026-08-12. Antes solo se guardaba dónde estaba la tarjeta, así que
  // agrandar la hoja de resultados para leerla a gusto y recargar la devolvía a su tamaño de fábrica — el
  // esfuerzo del operador se perdía en cada refresco, que es la forma más rápida de que una función no se use.
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
                  w:c.style.width||"", h:c.style.height||""}); });
    return items;
  }
  _persist(){
    if(this._restoring) return;
    try{ localStorage.setItem("hb_desktop", JSON.stringify(this._layout())); }catch(_){}
    this._reportOpen();     // ESTADO: el canvas es autoritativo → el servidor refleja qué hay abierto en el prompt
  }
  // Reporta los widgets ABIERTOS al ESTADO de la memoria (POST /api/canvas/state) para que viajen en el prompt del
  // cerebro ("modifica el widget de X" sin preguntar) y se vean en el mapa. Debounce ligero (los arrastres/moves
  // llaman _persist a ráfagas) + best-effort. Envía this.list() crudo; el servidor normaliza (navegador::t3→navegador).
  // Lleva ADEMÁS la geometría, que el server guarda como red de seguridad del localStorage (que es per-origen y
  // per-navegador: el mismo zaelar por :43917 y por :44317 son dos escritorios distintos). Ver `restore()`.
  _reportOpen(){
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
        localStorage.setItem("hb_wipe", String(epoch));
        this._reportOpen();               // el ESTADO del servidor también a vacío
        return;                           // arranca sin widgets
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
      console.info("desktop: restaurado del servidor (este navegador no tenía escritorio guardado)");
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
  // V2-085: `GET /widgets` devuelve ahora el ÍNDICE COMPACTO (id/name/title/whenToUse/aliases/origin/transient),
  // no los manifests completos — es todo lo que este resolver y `_meta` necesitan, y deja de ser O(N·manifest)
  // (25 KB con 16 widgets, megas con miles). El manifest íntegro se pide por widget: /widgets/{id}/manifest.
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

  // ── NOMBRE + ALIAS del widget (V2-082) ───────────────────────────────────────────────────────────────────
  // El header de cada tarjeta muestra el NOMBRE canónico y, tras el ⚙, la lista de ALIAS editable. Fuente: el
  // registro unificado GET /widgets/registry (cacheado; se refresca por el evento SSE widget/alias).
  async _ensureRegistry(force){
    if(this._registry && !force) return this._registry;
    try{
      const r=await fetch("/widgets/registry").then(r=>r.json());
      this._registry={}; (r.registry||[]).forEach(e=>{ this._registry[e.id]=e; });
    }catch(_){ this._registry=this._registry||{}; }
    return this._registry;
  }
  async _applyName(w){
    if(w._liveTitle) return;                            // la TAREA manda sobre el nombre del catálogo (ver _liveTitle)
    const reg=await this._ensureRegistry(); const e=reg[w.base];
    if(e && w.nameBtn) w.nameBtn.textContent=e.name||w.base;
  }

  // ---- TÍTULO VIVO: la cabecera dice QUÉ es esto, no CÓMO se llama la pieza ----
  // Petición del operador (2026-08-12): «no hace falta que la gente sepa que eso es el visor o la muestra de
  // resultados, sino lo que le hemos pedido puesto ahí». En una superficie genérica el nombre del catálogo
  // («Resultados») no informa de nada: lo que identifica esa tarjeta es el ENCARGO que está mostrando. Así que un
  // widget puede declarar `"live_title": true` en su manifest y entonces la cabecera de la tarjeta lleva su
  // `data.title`.
  // Es OPT-IN por widget, no global: la agenda o el reloj sí se identifican por su nombre, y cambiárselo a todos
  // sería una regresión. Y el nombre POR EL QUE SE ABRE no se pierde — sigue en el tooltip y en el panel de alias
  // (⚙), que es donde el operador va a buscar cómo llamarlo por voz.
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
    // El nombre canónico queda a un gesto de distancia, no borrado: es como se dirige la pieza por voz.
    const reg = await this._ensureRegistry();
    const name = (reg[baseId] && reg[baseId].name) || baseId;
    w.nameBtn.title = `${title}\n(${name} — clic para ver/editar sus alias)`;
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
    // INSTANCIA por tarea: un id como `navegador::t3` = varias tarjetas del MISMO widget base. base = código+datos
    // (`navegador`), q = id de la tarea (para /data?q= y ctx.action), y la tarjeta se indexa por el id COMPLETO
    // (instancia) → N tarjetas independientes del navegador, una por pestaña/tarea. Un id normal se comporta igual.
    let baseId, id, wq;
    if(rawId && rawId.includes("::")){ const p=rawId.split("::"); baseId=p[0]; id=rawId; wq=p[1]||q; }
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
      // HEADER (V2-082): botón-NOMBRE + config para ver/editar los ALIAS. El nombre se rellena desde el registro.
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
      this._wireDrag(card, grip);
      this._wireResize(card, id);
      card.addEventListener("pointerdown",()=>this._bringFront(card));
      // el drag (grip) ya no engulle clicks del header; el header ignora pointerdown para no arrastrar la tarjeta.
      head.addEventListener("pointerdown",e=>e.stopPropagation());
      requestAnimationFrame(()=>card.classList.add("in"));
      card._long=setTimeout(()=>card.classList.add("long"),3500);
      w={card, body, q, id, base:baseId, nameBtn, head}; this.wins.set(id, w);
      nameBtn.onclick=()=>this._toggleAliases(w); cfg.onclick=()=>this._toggleAliases(w);
      this._applyName(w);                               // rellena el nombre desde el registro (async, best-effort)
    } else {
      this._bringFront(w.card);
      // Already open, no new data pushed, same query → just surface it (no re-fetch, no re-render, no flicker).
      if(providedData === null && q === w.q) return;
    }
    w.q = q;                                            // remember the query so a refresh reloads the same content
    // `desk` (NO `self`: en un navegador `self` es `window`, así que un getter que lo usara leería `window._running`
    // = undefined y TODO widget creería que el agente está parado — un fallo silencioso y difícil de ver).
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
        // «Vuelve arriba»: el widget pide, el canvas decide cómo (el scroller es chrome de la tarjeta, no suyo).
        // Lo llama SOLO al NAVEGAR — abrir una ficha, cambiar de pestaña, volver a la lista —, nunca en un
        // refresco de datos: resetear el scroll cada vez que llegan resultados nuevos le arrancaría de las manos
        // al operador lo que está leyendo, justo mientras la hoja se llena en vivo.
        top:()=>{ const sc=w.card && w.card.querySelector(".hb-scroll"); if(sc) sc.scrollTop=0; },
        // V2-092 — ¿está el agente en marcha? GETTER a propósito: el `ctx` se crea una vez por montaje y se guarda
        // (`w._ctx`) para los re-renders, así que una copia del valor se quedaría rancia. Un widget que REPRODUCE
        // algo debe consultarlo antes de arrancar solo (ver widgets/AGENTS.md, «producir»).
        get running(){ return desk._running; } };
      // La marca va ANTES de pintar: así el widget sabe en su PRIMERA pasada que la cabecera de la tarjeta ya lleva
      // el título y no lo repite. Puesta después, la primera pintada saldría con el título duplicado.
      if(this._wantsLiveTitle(baseId)) w.body.dataset.hostTitle = "1";
      mod.render(w.body, data, ctx);
      this._applyLiveTitle(w, baseId, data);            // …y el texto, que sale de los datos recién cargados
      // TAMAÑO PREFERIDO del widget, solo en el primer montaje y solo si el operador no le había dejado uno suyo.
      // Una superficie de ancho fluido (la hoja de resultados) no puede deducir su tamaño del contenido: sin esto
      // encogería a la anchura de su tarjeta más estrecha. Lo declara su manifest (`size`), no lo adivina el canvas.
      if(fresh && !(pos && (pos.w || pos.h))) this._applyPreferred(w.card, baseId);
      if(fresh){ w.card.classList.add("boop"); setTimeout(()=>w.card.classList.remove("boop"),460); }
      // Remember signature/module/ctx so refreshData() (SSE-triggered, NO polling) can re-render on change.
      w._dataSig = JSON.stringify(data); w._mod = mod; w._ctx = ctx;
      this._persist();                                  // widget is up → remember it for next refresh
    }catch(e){ console.error("widget mount failed", id, e); this._mountError(w, baseId, String(e&&e.message||e)); }
  }

  // Un widget que falla al montar/renderizar YA NO desaparece en silencio (bug 2026-07-13: el operador pedía la
  // agenda 4 veces y "no la veía" — la tarjeta se creaba y se auto-cerraba en el catch, sin dejar rastro). Ahora
  // muestra un estado de ERROR VISIBLE en la tarjeta Y lo REPORTA a la observabilidad (evento client en /debug) →
  // el fallo real de render deja de ser invisible. Invariante: un widget roto = estado de error aislado, nunca
  // tumba el resto ni se esfuma.
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
    const desk = this;                                       // ver la nota de `show()` sobre por qué no `self`
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
        get running(){ return desk._running; } };            // V2-092: mismo contrato que en una tarjeta normal
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
    if(this.stage){ this.stage.querySelectorAll(".hb-win").forEach(card=>{ card.classList.remove("in"); setTimeout(()=>card.remove(),220); }); }
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
      card.style.maxWidth="none"; card.style.maxHeight="none";
      card.style.left=pad+"px"; card.style.top=top+"px";
      card.style.width=(innerWidth - pad*2)+"px";
      card.style.height=(innerHeight - top - pad)+"px";
    }
    this._bringFront(card); this._persist(); this._uiAudit("maximize", id);
    return true;
  }

  // ---- redimensionado A MANO: ocho tiradores (cuatro esquinas + cuatro bordes) ----
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
  // Tamaño preferido declarado por el widget (`manifest.size`), aplicado solo si la tarjeta no trae uno guardado.
  _applyPreferred(card, baseId){
    const size = this._meta && this._meta[baseId] && this._meta[baseId].size;
    if(!size) return;
    const maxW = innerWidth - this.tile.pad*2, maxH = innerHeight - this.tile.top - this.tile.pad;
    if(size.w) card.style.width  = Math.min(Number(size.w), maxW) + "px";
    if(size.h) card.style.height = Math.min(Number(size.h), maxH) + "px";
    if(size.w || size.h){ card.style.maxWidth="none"; card.style.maxHeight="none"; }
    // Recolocar: la tarjeta se ubicó con el tamaño por defecto (400×340) y puede haber crecido fuera del lienzo.
    const L=parseInt(card.style.left)||this.tile.pad, T=parseInt(card.style.top)||this.tile.top;
    card.style.left = Math.max(this.tile.pad, Math.min(L, innerWidth - card.offsetWidth - this.tile.pad)) + "px";
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
      l = Math.max(0, l); t = Math.max(0, t);
      w = Math.min(w, innerWidth - l); h = Math.min(h, innerHeight - t);
      card.style.left=l+"px"; card.style.top=t+"px"; card.style.width=w+"px"; card.style.height=h+"px";
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
    const pad=this.tile.pad, top=this.tile.top, step=20, obs=this._obstacles(card);
    for(let y=top; y+H<=innerHeight-pad; y+=step){
      for(let x=pad; x+W<=innerWidth-pad; x+=step){
        const r={left:x, top:y, right:x+W, bottom:y+H};
        if(!obs.some(o=>_overlap(r,o))){ card.style.left=x+"px"; card.style.top=y+"px"; return; }
      }
    }
    const n=this.wins.size, off=(n%6)*26;          // no room anywhere → cascade near the centre, on top
    card.style.left=Math.max(pad,(innerWidth*0.5 - W*0.5 + off))+"px";
    card.style.top =Math.max(top,(innerHeight*0.30 + off))+"px";
  }

  // ORDENAR el canvas en una rejilla alineada (V2-464, showcase). One command, invocable from anywhere the
  // SSE reaches (POST /api/canvas/arrange -> widget/arrange), like the OS window-snap the operator asked for.
  // The area avoids a DOCKED chat wall and the orb strip at the bottom; every card gets the same cell so a
  // recording reads clean. Sizes clamp to the card's own max-width/height, so nothing distorts.
  arrange(){
    const cards=[...this.wins.values()].map(w=>w.card).filter(c=>c && c.isConnected);
    if(!cards.length) return {ok:true, n:0};
    const pad=this.tile.pad, y0=this.tile.top, y1=innerHeight-150;   // 150 = orb/status strip
    let x0=pad, x1=innerWidth-pad;
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
  _obstacles(exceptCard){
    const rects=[];
    this.wins.forEach(w=>{ if(w.card!==exceptCard){ const r=w.card.getBoundingClientRect(); if(r.width)rects.push(r); } });
    for(const sel of ["#me", "#orbwrap"]){ const e=document.querySelector(sel);
      if(e){ const r=e.getBoundingClientRect(); if(r.width)rects.push(r); } }
    return rects;
  }

  _bringFront(card){ card.style.zIndex = Math.min(8000, ++this.z); }   // stay BELOW the camera (9000) and orb (100000)

  // reverse lookup: which widget id owns this card? (para atribuir una acción de UI al widget correcto)
  _idOf(card){ for(const [id,w] of this.wins){ if(w && w.card===card) return id; } return ""; }
  // V2-039 — AUDITORÍA del frontend: registra en la línea de tiempo una acción que hace el OPERADOR sobre un widget
  // a mano (mover/redimensionar). El server la estampa con src="user". Fire-and-forget; nunca rompe el canvas.
  _uiAudit(action, id){ try{ fetch("/api/ui-event",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({kind:"widget",action,id})}); }catch(_){} }

  _wireDrag(card, grip){
    let dx=0,dy=0,drag=false,moved=false;
    grip.addEventListener("pointerdown",e=>{drag=true;moved=false;const r=card.getBoundingClientRect();
      dx=e.clientX-r.left;dy=e.clientY-r.top;this._bringFront(card);grip.setPointerCapture(e.pointerId);e.preventDefault();});
    grip.addEventListener("pointermove",e=>{if(!drag)return;moved=true;
      let x=Math.max(0,Math.min(e.clientX-dx,innerWidth-card.offsetWidth));
      let y=Math.max(0,Math.min(e.clientY-dy,innerHeight-card.offsetHeight));
      card.style.left=x+"px";card.style.top=y+"px"; });
    grip.addEventListener("pointerup",()=>{ drag=false; this._persist();   // remember the new position
      if(moved) this._uiAudit("move", this._idOf(card)); });               // …and audit the user's move
  }
}
