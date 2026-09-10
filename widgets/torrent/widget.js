// The Descargas widget — a torrent-client-style DOWNLOAD MANAGER (redesign). It never plays anything itself:
// a row's ▶ asks the backend to hand the file to `youtube` (video) or `musica` (finished audio), which is
// where it actually streams — this card only lists what is downloading and what has finished and is being
// shared as a seed, and lets the operator remove a download (+ its file) or save a finished one to the
// library. One download alone renders as a single "hero" card (the shape the operator liked); two or more
// render as compact rows, like any torrent client's transfer list.
//
// The shell (header + the collapsible "add magnet" box) is built ONCE and only the row list is rebuilt on
// each render (the V2-124/4.19 lesson): a re-render must never wipe what the operator is mid-typing into the
// magnet box.

function injectStyles(){
  if(document.getElementById("hb-torrent-css"))return;
  const s=document.createElement("style"); s.id="hb-torrent-css"; s.textContent=`
  .hbt{width:100%;box-sizing:border-box;display:flex;flex-direction:column;height:100%;min-height:0;
       background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif)}
  .hbt-head{display:flex;align-items:center;gap:.5rem;padding:.7rem .9rem;border-bottom:1px solid var(--hb-line,#eef1f6);flex:0 0 auto}
  .hbt-title{font-size:var(--fs-title,.95rem);font-weight:650;letter-spacing:-.01em;flex:1 1 auto;min-width:0}
  .hbt-count{font-size:var(--fs-caption,.72rem);color:var(--hb-muted,#8a95a5)}
  .hbt-addbtn{font-size:var(--fs-ui,.8rem);color:var(--hb-ink,#0d1622);border:1px solid var(--hb-line,#dde3ec);
             background:var(--hb-bg-soft,#f5f7fa);border-radius:8px;padding:.35rem .65rem;cursor:pointer;white-space:nowrap}
  .hbt-addbtn:hover{border-color:var(--hb-accent,#3b82f6)}
  .hbt-add{display:none;gap:.4rem;padding:.6rem .9rem;border-bottom:1px solid var(--hb-line,#eef1f6);flex:0 0 auto}
  .hbt-add.on{display:flex}
  .hbt-add input{flex:1 1 auto;min-width:0;font-size:.85rem;padding:.5rem .6rem;border-radius:8px;
                 border:1px solid var(--hb-line,#dde3ec);background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
  .hbt-add button{font-size:.8rem;border:none;border-radius:8px;padding:.5rem .8rem;cursor:pointer;
                  background:var(--hb-accent,#3b82f6);color:#fff;white-space:nowrap}
  .hbt-body{flex:1 1 auto;min-height:0;overflow:auto;padding:.7rem .9rem 1rem}
  .hbt-empty,.hbt-unavail{padding:1.4rem .5rem;text-align:center;color:var(--hb-muted,#8a95a5);font-size:.85rem}
  .hbt-sec{font-size:var(--fs-caption,.72rem);font-weight:650;text-transform:uppercase;letter-spacing:.04em;
          color:var(--hb-muted,#8a95a5);margin:.9rem 0 .4rem;display:flex;align-items:center;gap:.4rem}
  .hbt-sec:first-child{margin-top:0}
  .hbt-sec .n{background:var(--hb-bg-soft,#f0f2f6);border-radius:999px;padding:.05rem .5rem;font-weight:650}

  .hbt-row{display:flex;align-items:center;gap:.6rem;padding:.55rem .5rem;border-radius:10px;margin-bottom:.3rem}
  .hbt-row:hover{background:var(--hb-bg-soft,#f7f8fb)}
  .hbt-icon{flex:0 0 auto;width:1.6rem;height:1.6rem;display:flex;align-items:center;justify-content:center;
           font-size:1rem;border-radius:8px;background:var(--hb-bg-soft,#f0f2f6)}
  .hbt-mid{flex:1 1 auto;min-width:0}
  .hbt-name{font-size:.83rem;font-weight:550;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hbt-bar{height:5px;border-radius:999px;background:var(--hb-line,#e6e9ef);overflow:hidden;margin-top:.3rem}
  .hbt-fill{height:100%;width:0;background:var(--hb-accent,#3b82f6);transition:width .4s ease}
  .hbt-fill.done{background:var(--hb-accent2,#16b8a6)}
  .hbt-sub{font-size:var(--fs-caption,.72rem);color:var(--hb-muted,#8a95a5);margin-top:.2rem;
          display:flex;gap:.6rem;flex-wrap:wrap}
  .hbt-err{color:var(--hb-risk,#e5484d)}
  .hbt-acts{flex:0 0 auto;display:flex;gap:.3rem}
  .hbt-btn{border:1px solid var(--hb-line,#dde3ec);background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);
          border-radius:8px;width:1.9rem;height:1.9rem;display:flex;align-items:center;justify-content:center;
          font-size:.85rem;cursor:pointer;flex:0 0 auto}
  .hbt-btn:hover{border-color:var(--hb-accent,#3b82f6)}
  .hbt-btn.play{color:var(--hb-accent,#3b82f6);border-color:var(--hb-accent,#3b82f6)}
  .hbt-btn.danger{color:var(--hb-risk,#e5484d)}
  .hbt-btn.danger:hover{border-color:var(--hb-risk,#e5484d)}
  .hbt-btn[disabled]{opacity:.35;cursor:default}
  .hbt-confirm{display:flex;align-items:center;gap:.4rem;font-size:.78rem;color:var(--hb-risk,#e5484d)}
  .hbt-confirm button{font-size:.76rem;border-radius:8px;padding:.25rem .55rem;cursor:pointer;border:1px solid var(--hb-line,#dde3ec);background:var(--hb-bg,#fff)}
  .hbt-confirm button.yes{background:var(--hb-risk,#e5484d);border-color:var(--hb-risk,#e5484d);color:#fff}

  /* Hero: the one-download shape — keeps the original card's feel, larger and centered */
  .hbt-hero{display:flex;flex-direction:column;align-items:center;text-align:center;gap:.8rem;padding:2rem 1rem}
  .hbt-hero .hbt-icon{width:3.2rem;height:3.2rem;font-size:1.7rem;border-radius:14px}
  .hbt-hero .hbt-name{font-size:1rem;font-weight:650;white-space:normal;max-width:100%}
  .hbt-hero .hbt-bar{width:min(360px,88%);height:7px}
  .hbt-hero .hbt-sub{justify-content:center}
  .hbt-hero .hbt-acts{margin-top:.3rem}
  .hbt-hero .hbt-btn{width:2.4rem;height:2.4rem;font-size:1rem}`;
  document.head.appendChild(s);
}

function pct(p){ return Math.max(0, Math.min(100, Math.round(Number(p)||0))); }
function human(n){ n=Number(n)||0; if(n<1024)return n+" B"; if(n<1048576)return (n/1024).toFixed(0)+" KB";
  if(n<1073741824)return (n/1048576).toFixed(1)+" MB"; return (n/1073741824).toFixed(2)+" GB"; }

const KIND_ICON = { video:"🎬", audio:"🎵", other:"📦", "":"⏳" };

const STATE_LABEL = {
  seeding:"Compartiendo (semilla)", finished:"Terminada", downloading:"Descargando",
  downloading_metadata:"Buscando fuentes", checking_files:"Comprobando ficheros",
  queued_for_checking:"En cola", allocating:"Reservando espacio", checking_resume_data:"Comprobando"
};
function stateLabel(row){
  if(row.state === "downloading" && row.progress <= 0) return "Buscando fuentes";
  return STATE_LABEL[row.state] || (row.complete ? "Terminada" : "Descargando");
}

function buildShell(root, ctx){
  root.className="hbt"; root.textContent="";
  const head=document.createElement("div"); head.className="hbt-head";
  const title=document.createElement("div"); title.className="hbt-title"; title.textContent="Descargas";
  const count=document.createElement("div"); count.className="hbt-count";
  const addBtn=document.createElement("button"); addBtn.className="hbt-addbtn"; addBtn.type="button";
  addBtn.textContent="+ Magnet";
  head.append(title, count, addBtn);

  const addRow=document.createElement("div"); addRow.className="hbt-add";
  const addInput=document.createElement("input"); addInput.type="text"; addInput.placeholder="magnet:?xt=urn:btih:…";
  const addGo=document.createElement("button"); addGo.type="button"; addGo.textContent="Descargar";
  addRow.append(addInput, addGo);
  addBtn.addEventListener("click", ()=>{
    addRow.classList.toggle("on");
    if(addRow.classList.contains("on")) addInput.focus();
  });
  const submitMagnet=()=>{
    const magnet=addInput.value.trim();
    if(!magnet || !ctx || !ctx.action) return;
    ctx.action("add_magnet", {magnet}).then(()=>{ addInput.value=""; addRow.classList.remove("on"); });
  };
  addGo.addEventListener("click", submitMagnet);
  addInput.addEventListener("keydown", e=>{ if(e.key==="Enter") submitMagnet(); });

  const body=document.createElement("div"); body.className="hbt-body";

  root.appendChild(head); root.appendChild(addRow); root.appendChild(body);
  return { title, count, body, addInput, addRow, confirmId:"" };
}

function buildRow(row, ctx, ui, {hero}={}){
  const wrap=document.createElement("div"); wrap.className="hbt-row"+(hero?" hbt-hero":"");
  const icon=document.createElement("div"); icon.className="hbt-icon"; icon.textContent=KIND_ICON[row.kind]||KIND_ICON.other;
  const mid=document.createElement("div"); mid.className="hbt-mid";
  const name=document.createElement("div"); name.className="hbt-name"; name.textContent=row.title;
  const bar=document.createElement("div"); bar.className="hbt-bar";
  const fill=document.createElement("div"); fill.className="hbt-fill"+(row.complete?" done":"");
  fill.style.width=pct(row.progress)+"%"; bar.appendChild(fill);
  const sub=document.createElement("div"); sub.className="hbt-sub";
  const addSub=(t)=>{ const s=document.createElement("span"); s.textContent=t; sub.appendChild(s); };
  addSub(`${pct(row.progress)}% · ${stateLabel(row)}`);
  if(!row.complete){
    addSub(`${row.num_peers} fuentes`);
    if(row.download_rate>0) addSub(`${human(row.download_rate)}/s`);
  }
  addSub(row.size ? `${human(row.downloaded)} / ${human(row.size)}` : human(row.downloaded));
  mid.append(name, bar, sub);

  const acts=document.createElement("div"); acts.className="hbt-acts";
  if(ui.confirmId === row.id){
    const cf=document.createElement("div"); cf.className="hbt-confirm";
    const q=document.createElement("span"); q.textContent="¿Eliminar y borrar el fichero?";
    const yes=document.createElement("button"); yes.className="yes"; yes.type="button"; yes.textContent="Sí, eliminar";
    yes.addEventListener("click", ()=>{ ui.confirmId=""; ctx&&ctx.action&&ctx.action("remove",{id:row.id}); });
    const no=document.createElement("button"); no.type="button"; no.textContent="Cancelar";
    no.addEventListener("click", ()=>{ ui.confirmId=""; render(ui.root, ui.lastData, ctx); });
    cf.append(q, yes, no); acts.appendChild(cf);
  } else {
    if(row.can_play){
      const play=document.createElement("button"); play.className="hbt-btn play"; play.type="button";
      play.title="Reproducir"; play.textContent="▶";
      play.addEventListener("click", ()=>{ ctx&&ctx.action&&ctx.action("open",{id:row.id}); });
      acts.appendChild(play);
    }
    if(row.complete){
      const save=document.createElement("button"); save.className="hbt-btn"; save.type="button";
      save.title="Guardar en la biblioteca"; save.textContent="💾";
      save.addEventListener("click", ()=>{ ctx&&ctx.action&&ctx.action("save",{id:row.id}); });
      acts.appendChild(save);
    }
    const del=document.createElement("button"); del.className="hbt-btn danger"; del.type="button";
    del.title="Eliminar"; del.textContent="✕";
    del.addEventListener("click", ()=>{ ui.confirmId=row.id; render(ui.root, ui.lastData, ctx); });
    acts.appendChild(del);
  }

  wrap.append(icon, mid, acts);
  return wrap;
}

function renderRows(ui, data, ctx){
  const body=ui.body; body.textContent="";
  const seeds=data.seeds||[], downloads=data.downloads||[];
  const total=seeds.length+downloads.length;

  if(!data.available){
    const p=document.createElement("div"); p.className="hbt-unavail";
    p.textContent=data.unavailable_reason || "El cliente de descargas no está disponible.";
    body.appendChild(p); return;
  }
  if(data.error && total===0){
    const p=document.createElement("div"); p.className="hbt-unavail hbt-err"; p.textContent=data.error;
    body.appendChild(p); return;
  }
  if(total===0){
    const p=document.createElement("div"); p.className="hbt-empty";
    p.textContent="No hay descargas. Pide «descarga la película X» o añade un magnet.";
    body.appendChild(p); return;
  }
  if(total===1){
    const row=downloads[0]||seeds[0];
    body.appendChild(buildRow(row, ctx, ui, {hero:true}));
    return;
  }
  if(downloads.length){
    const h=document.createElement("div"); h.className="hbt-sec";
    const t=document.createElement("span"); t.textContent="Descargando";
    const n=document.createElement("span"); n.className="n"; n.textContent=String(downloads.length);
    h.append(t,n); body.appendChild(h);
    for(const row of downloads) body.appendChild(buildRow(row, ctx, ui, {hero:false}));
  }
  if(seeds.length){
    const h=document.createElement("div"); h.className="hbt-sec";
    const t=document.createElement("span"); t.textContent="Semillas";
    const n=document.createElement("span"); n.className="n"; n.textContent=String(seeds.length);
    h.append(t,n); body.appendChild(h);
    for(const row of seeds) body.appendChild(buildRow(row, ctx, ui, {hero:false}));
  }
}

export function render(root, data, ctx){
  injectStyles();
  const d = data || {};
  let ui = root.__hbt;
  if(!ui){ ui = root.__hbt = buildShell(root, ctx); ui.root = root; }
  ui.lastData = d;

  const total=(d.seeds||[]).length + (d.downloads||[]).length;
  ui.count.textContent = total ? `${total} activa${total===1?"":"s"}` : "";
  // A row that got removed out from under an open confirm must not leave it dangling forever.
  if(ui.confirmId && !(d.seeds||[]).concat(d.downloads||[]).some(r=>r.id===ui.confirmId)) ui.confirmId="";

  renderRows(ui, d, ctx);

  // Keep polling while anything is still filling; stop once everything is either seeding or there is nothing
  // to watch. One timer per card, cleared and reset on every render.
  if(root.__hbtPoll){ clearTimeout(root.__hbtPoll); root.__hbtPoll = 0; }
  const active = d.available && (d.downloads||[]).some(r => r.progress < 100);
  if(active && ctx && ctx.action){
    root.__hbtPoll = setTimeout(()=>{ try{ ctx.action("poll"); }catch(_){} }, 1500);
  }
}
