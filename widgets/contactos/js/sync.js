// Contacts widget — the provider icons in the bar, the sources screen and its sync/import boxes
// (refactor2710-12 T-03).
import { ICO_PEOPLE, ICO_SYNC, IMPORT_SOURCES, LIVE_SOURCES, SRC_SVG, _LANG, el2, hooks, srcKey,
  svgEl, tt } from "./shared.js";

// ── THE PROVIDER ICONS — a FILTER for a linked source, a door for one that is not (V2-715) ─────────────
// The operator's correction, 2026-09-17: «cuando entramos en Telegram quiero ver solo los contactos de
// Telegram… ya tenemos el botón de conectores para manejar la sincronización». So the icon stopped being
// a second door to the connectors screen — which is what V2-699 made it, and what made two controls on
// this row do one thing — and became the platform filter. It still opens the screen when the source is
// LINKABLE but not linked, because there is nothing to filter and «conéctalo» is the only useful answer.
//
// Three states remain three different sentences (the house standard): full colour = linked, dimmed = built
// and not linked, `.off` + disabled = no connector exists at all.
export function renderProviderIcons(providers, el, data, ctx){
  const wrap = el2("div","ctconnicons");
  (providers||[]).forEach(p=>{
    const live = !!LIVE_SOURCES[p.id];
    const on = p.status === "connected";
    const sel = !!el._ctSource && srcKey(el._ctSource) === srcKey(p.id);
    const btn = el2("button","ctconnicon" + (on?" on":"") + (live?"":" off") + (sel?" sel":""));
    const spec = SRC_SVG[p.id];
    if(spec){ btn.style.color = spec.color; btn.appendChild(svgEl(spec.path, {fill:true})); }
    else { btn.appendChild(svgEl(ICO_PEOPLE)); }
    btn.title = (p.label || p.id) + " — " + (!live ? tt("src_soon", null, "aún no disponible")
                                                   : !on ? tt("src_off_connect", null, "sin conectar — pulsa para conectarlo")
                                                   : sel ? tt("src_filter_off", null, "quitar el filtro")
                                                         : tt("src_filter_on", null, "ver solo estos contactos"));
    if(!live){ btn.disabled = true; }
    else if(!on){ btn.onclick = ()=>ctx.openConnector(p.id); }   // linking is the ⚙ Conectores section's job
    else { btn.onclick = ()=>{
      el._ctSource = sel ? "" : p.id;
      el._ctDetail = null; el._ctScreen = null; el._ctShown = 0; hooks.render(el,data,ctx); }; }
    wrap.appendChild(btn);
  });
  return wrap;
}

// ── THE SOURCES SCREEN — which address books feed the directory, and the sync switch of each ─────────────
// Linking a source is NOT done here (2026-10-04): every account is connected in the ⚙ Conectores section, the
// one door the voice and the buttons share. What stays is this card's own business — whether a linked
// source keeps bringing contacts in — and, for one that is not linked, the way to that section.
export function renderConnectors(el, host, data, ctx){
  const wrap = el2("div","ctconnscreen");
  const redraw = nd=>hooks.render(el,(nd&&nd.contacts)?nd:data,ctx);

  const head = el2("div","ctconnhead");
  head.appendChild(el2("div","ctconntitle", tt("sources_title", null, "Fuentes y sincronización")));
  const back = el2("button","ctconnback", "‹ " + tt("title", null, "Contactos"));
  back.onclick = ()=>{ el._ctScreen = null; hooks.render(el,data,ctx); };
  head.appendChild(back);
  wrap.appendChild(head);

  const sync = data.sync || {};
  (data.providers||[]).forEach(p=>{
    const live = !!LIVE_SOURCES[p.id];
    const on = p.status === "connected";
    const box = el2("div","ctsrcbox" + (live?"":" dim") + (on?" on":""));
    const row = el2("div","ctsrc");
    const ic = el2("div","ctsrcic");
    const spec = SRC_SVG[p.id];
    if(spec){ ic.style.color = spec.color; ic.appendChild(svgEl(spec.path,{fill:true})); }
    else { ic.appendChild(svgEl(ICO_PEOPLE)); }
    row.appendChild(ic);
    const tx = el2("div","ctsrctx");
    tx.appendChild(el2("div","ctsrcnm", p.label || p.id));
    const st = el2("div","ctsrcst");
    st.appendChild(el2("span","ctdot" + (on?" ok":"")));
    st.appendChild(document.createTextNode(
      !live ? tt("src_soon", null, "aún no disponible")
            : on ? tt("src_connected", null, "conectado")
                 : tt("src_off", null, "sin conectar")));
    tx.appendChild(st);
    row.appendChild(tx);
    if(live){
      const b = el2("button","ctbtn" + (on ? "" : " primary"),
                    on ? tt("src_manage", null, "Gestionar") : tt("src_connect", null, "Conectar"));
      b.onclick = ()=>ctx.openConnector(p.id);
      row.appendChild(b);
    }
    box.appendChild(row);
    if(live && on) box.appendChild(IMPORT_SOURCES[p.id] ? renderImportBox(el, data, ctx, p, redraw)
                                                        : renderSyncBox(el, data, ctx, sync, redraw));
    wrap.appendChild(box);
  });
  host.appendChild(wrap);
}

// ── THE IMPORT SWITCH (V2-714) — one control, both halves, and an honest count ──────────────────────────
// «No vamos a poner dos opciones, quieres sincronizar esto, lo otro. En el momento en que le damos a
// conectar… un botón de sincronizar que se queda activado y se queda en modo sincronizando en tiempo real.»
// So: ONE switch. It brings contacts AND groups, and turning it on runs a pass immediately rather than
// promising one in fifteen minutes.
export function renderImportBox(el, data, ctx, p, redraw){
  const st = (p.sync || {});
  const on = !!st.on;
  const box = el2("div","ctsync");
  const top = el2("div","ctsynctop");
  top.appendChild(svgEl(ICO_SYNC));
  top.appendChild(el2("b", null, tt("import_title", null, "Contactos y grupos")));
  box.appendChild(top);

  const line = el2("div","ctsyncfoot");
  const sw = el2("button","ctbtn" + (on ? " primary" : ""),
                 on ? tt("import_on", null, "Sincronizando") : tt("import_off", null, "Sincronizar"));
  sw.onclick = async ()=>{
    sw.disabled = true;
    sw.textContent = tt("import_working", null, "Trayendo…");
    redraw(await ctx.action("set_auto", {source: p.id, auto: !on}));
  };
  line.appendChild(sw);
  box.appendChild(line);

  // WHAT IT BROUGHT, and — for the one platform that cannot be asked for everything — what that number
  // does NOT mean. A count presented as a total when it is not is a promise the card cannot keep.
  const bits = [];
  if(st.last){ bits.push(tt("import_added", {n: st.added || 0}, (st.added || 0) + " nuevos en la última pasada")); }
  if(p.id === "whatsapp"){ bits.push(tt("import_partial", null,
    "WhatsApp va entregando su libreta a medida que el móvil la sincroniza: esto es lo conocido hasta ahora")); }
  if(st.error){ bits.push(tt("sync_failed", null, "La última sincronización falló")); }
  if(bits.length){ const w=box.appendChild(el2("div","ctsyncwhen", bits.join(" · ")));
    if(st.error) w.title=String(st.error); }
  return box;
}

export function renderSyncBox(el, data, ctx, sync, redraw){
  const box = el2("div","ctsync");
  const top = el2("div","ctsynctop");
  top.appendChild(svgEl(ICO_SYNC));
  top.appendChild(el2("b",null, tt("sync_title", null, "Sincronización")));
  box.appendChild(top);

  // THE CONTROL IS A STATE, NOT AN ERRAND (V2-701). His words: «el tema de la sincronización de contactos
  // no es algo que deberíamos hacer de forma puntual… eso debería quedarse conectado de forma permanente».
  // A button is a one-off by its very grammar, so the button stopped being the control and became the
  // switch that is either on or off — and while it is on, the engine keeps them in step on its own.
  const on = sync.auto !== false;
  const row = el2("button","ctswrow" + (on?" on":""));
  row.appendChild(el2("span","ctsw"));
  row.appendChild(el2("span","ctswtx", tt("sync_auto", null, "Mantener sincronizado con Google")));
  const every = Math.max(1, Math.round((sync.every || 60)/60));
  row.appendChild(el2("span","ctswsub", on
    ? tt("sync_auto_on", {min: every}, every === 1 ? "comprueba cada minuto"
                                                   : "comprueba cada " + every + " minutos")
    : tt("sync_auto_off", null, "apagada")));
  row.onclick = ()=>{ sync.auto = !on; redraw(null); ctx.action("set_auto", {auto: !on}).then(redraw); };
  box.appendChild(row);

  // ONE state, said in one line — his own simplification: «quizás quieras simplificar esto de Google a
  // nosotros y nosotros a Google, quitando esas opciones y solo dejando la sincronización activa».
  const dir = el2("div","ctsyncdir");
  dir.appendChild(el2("span","ctsyncarrow", sync.twoWay ? "⇄" : "→"));
  dir.appendChild(el2("span",null, sync.twoWay
    ? tt("sync_two_way", null, "Google y zaelar se mantienen iguales. Lo que cambies aquí —un nombre, un "
        + "teléfono— también cambia en Google.")
    : tt("sync_one_way", null, "De Google hacia zaelar. Trae tus contactos; por ahora no puede devolver "
        + "los cambios que hagas aquí.")));
  box.appendChild(dir);

  // What would unblock two-way (an OAuth scope on the deployment's app) is the deployer's business, not the
  // person's: the direction line above already says what it does, and nothing on this card asks them to act.

  if(sync.blockedDeletes){
    // Said out loud rather than swallowed: the engine REFUSED to mirror a deletion it did not believe, and
    // a guard that protects silently is indistinguishable from one that is not there (V2-701).
    const w = el2("div","ctwarn", tt("sync_blocked_deletes", {n: sync.blockedDeletes},
      "Google decía que " + sync.blockedDeletes + " contactos se habían borrado. Eran demasiados de golpe, "
      + "así que no he borrado ninguno. Revísalo en Google y vuelve a sincronizar."));
    w.style.color = "var(--hb-danger,#D9534F)";
    w.style.borderLeftColor = "var(--hb-danger,#D9534F)";
    box.appendChild(w);
  }

  const foot = el2("div","ctsyncfoot");
  // «Sincronizar ahora» is impatience, not the feature: the switch above is what keeps them in step. It is
  // still a BUTTON, the same `ctbtn` as «Gestionar» above it — one look for every action on this panel.
  const go = el2("button","ctbtn", tt("sync_now", null, "Sincronizar ahora"));
  go.onclick = async()=>{
    go.disabled = true; go.textContent = tt("syncing", null, "Sincronizando…");
    redraw(await ctx.action("sync_contacts", {}));
  };
  foot.appendChild(go);
  const when = el2("div","ctsyncwhen");
  when.appendChild(el2("div",null, sync.last
    ? tt("sync_last", {when: new Date(sync.last*1000).toLocaleString(_LANG)},
         "Última vez: " + new Date(sync.last*1000).toLocaleString(_LANG))
    : tt("sync_never", null, "Todavía no se ha sincronizado")));
  const r = sync.lastResult || {};
  if(r.error){
    when.appendChild(el2("div",null, tt("sync_failed", null, "La última sincronización falló"))).title=String(r.error);
  } else if(sync.last){
    const bits = [];
    if(r.added) bits.push(tt("sync_added", {n:r.added}, r.added + " nuevos"));
    if(r.updated) bits.push(tt("sync_updated", {n:r.updated}, r.updated + " completados"));
    if(r.removed) bits.push(tt("sync_removed", {n:r.removed}, r.removed + " borrados"));
    if(r.pushed || r.created) bits.push(tt("sync_pushed", {n:(r.pushed||0)+(r.created||0)},
      ((r.pushed||0)+(r.created||0)) + " enviados a Google"));
    when.appendChild(el2("div",null, bits.length ? bits.join(" · ")
      : tt("sync_nothing", null, "sin cambios")));
  }
  foot.appendChild(when);
  box.appendChild(foot);
  return box;
}
