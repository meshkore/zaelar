// realiza-cambio-real widget — cluster list with a SIDE PANEL: clicking a cluster in the list opens, from the
// lateral edge of THIS card, a shorter panel with its summarized view (status, peers, last messages) — the
// list stays put, no navigation away from it. Self-contained: no external deps, no network from JS.
// All third-party/log text goes through textContent (never innerHTML) — XSS safe.

function injectStyles(){
  if(document.getElementById("hb-rcr-css"))return;
  const s=document.createElement("style"); s.id="hb-rcr-css"; s.textContent=`
  .hb-rcr{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(680px,92vw)}
  .hb-rcr .rcr-hd{display:flex;align-items:baseline;gap:10px;margin:0 0 10px}
  .hb-rcr .rcr-hd b{font-size:15px;font-weight:600}
  .hb-rcr .rcr-hd .rcr-sub{font-size:12px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-rcr .rcr-hd .rcr-at{font-family:ui-monospace,Menlo,monospace;color:var(--hb-muted-2,#9aa7b8);font-size:12px;margin-left:auto}
  .hb-rcr .rcr-body{display:flex;align-items:stretch;gap:0;border:1px solid var(--hb-line,#eef1f6);border-radius:14px;
                    overflow:hidden;background:var(--hb-bg,#fff)}
  .hb-rcr .rcr-list{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:0;max-height:52vh;overflow:auto}
  .hb-rcr .rcr-item{display:flex;align-items:center;gap:9px;padding:10px 12px;border-bottom:1px solid var(--hb-line,#eef1f6);
                    cursor:pointer;background:var(--hb-bg,#fff)}
  .hb-rcr .rcr-item:last-child{border-bottom:none}
  .hb-rcr .rcr-item:hover{background:var(--hb-bg-soft,#fbfdff)}
  .hb-rcr .rcr-item.rcr-on{background:var(--hb-bg-soft,#fbfdff);box-shadow:inset 3px 0 0 var(--hb-accent,#3D6FE0)}
  .hb-rcr .rcr-dot{width:8px;height:8px;border-radius:50%;background:var(--hb-neutral,#c2ccda);flex:none}
  .hb-rcr .rcr-item.rcr-conn .rcr-dot{background:var(--hb-accent2,#16B8A6)}
  .hb-rcr .rcr-panel-status .rcr-dot.rcr-conn{background:var(--hb-accent2,#16B8A6)}
  .hb-rcr .rcr-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}
  .hb-rcr .rcr-name{font-size:13.5px;font-weight:600;color:var(--hb-ink,#0d1622)}
  .hb-rcr .rcr-meta{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-rcr .rcr-last{font-size:11px;color:var(--hb-muted-2,#9aa7b8);flex:none;font-family:ui-monospace,Menlo,monospace}
  .hb-rcr .rcr-empty{padding:22px 14px;text-align:center;color:var(--hb-muted-2,#9aa7b8);font-size:13px;flex:1}
  .hb-rcr .rcr-panel{flex:0 0 0;width:0;min-width:0;border-left:0 solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,#fbfdff);
                     overflow:hidden;transition:width .22s ease,flex-basis .22s ease;display:flex;flex-direction:column}
  .hb-rcr .rcr-panel.rcr-open{flex:0 0 280px;width:280px;border-left-width:1px}
  .hb-rcr .rcr-panel-hd{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-rcr .rcr-panel-hd b{font-size:13.5px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hb-rcr .rcr-close{flex:none;width:22px;height:22px;border:none;border-radius:7px;background:transparent;
                     color:var(--hb-muted-2,#9aa7b8);font-size:13px;cursor:pointer;display:flex;align-items:center;justify-content:center}
  .hb-rcr .rcr-close:hover{background:var(--hb-line,#eef1f6);color:var(--hb-ink,#0d1622)}
  .hb-rcr .rcr-panel-status{padding:8px 12px;font-size:11.5px;color:var(--hb-muted,#5b6b82);border-bottom:1px solid var(--hb-line,#eef1f6);
                            display:flex;align-items:center;gap:6px}
  .hb-rcr .rcr-panel-status .rcr-dot{width:7px;height:7px}
  .hb-rcr .rcr-panel-peers{padding:6px 12px 0;font-size:11px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-rcr .rcr-turns{flex:1;overflow:auto;padding:8px 12px 10px;display:flex;flex-direction:column;gap:7px}
  .hb-rcr .rcr-turn{border-radius:9px;padding:6px 9px;background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6)}
  .hb-rcr .rcr-turn.rcr-in{border-left:3px solid var(--hb-accent,#3D6FE0)}
  .hb-rcr .rcr-turn.rcr-out{border-left:3px solid var(--hb-accent2,#16B8A6)}
  .hb-rcr .rcr-turn-meta{display:flex;gap:6px;font-size:10.5px;color:var(--hb-muted-2,#9aa7b8);margin-bottom:2px}
  .hb-rcr .rcr-turn-who{font-weight:600;color:var(--hb-ink,#0d1622)}
  .hb-rcr .rcr-turn-txt{font-size:12px;line-height:1.4;color:var(--hb-ink,#0d1622);white-space:pre-wrap;word-break:break-word}
  .hb-rcr .rcr-panel-empty{padding:16px 12px;font-size:12px;color:var(--hb-muted-2,#9aa7b8)}
  `; document.head.appendChild(s);
}

function whoLabel(t){
  if(t.dir==="out"||t.who==="zaelar") return "zaelar";
  if(t.dir==="in"||t.who==="peer")    return t.peer || "peer";
  return t.who || "sistema";
}

export function render(el, data, ctx){
  injectStyles();
  el.className="hb-rcr";
  el.textContent="";

  const clusters = data.clusters || [];
  let sel = el._rcrSel;
  if(sel!=null && !clusters.some(c=>c.name===sel)) sel = null;
  el._rcrSel = sel;

  const hd=document.createElement("div"); hd.className="rcr-hd";
  const b=document.createElement("b"); b.textContent="Clusters"; hd.appendChild(b);
  const sub=document.createElement("span"); sub.className="rcr-sub";
  sub.textContent = clusters.length ? `${clusters.length} conocido${clusters.length===1?"":"s"}` : "";
  hd.appendChild(sub);
  const at=document.createElement("span"); at.className="rcr-at"; at.textContent=data.at||""; hd.appendChild(at);
  el.appendChild(hd);

  const body=document.createElement("div"); body.className="rcr-body"; el.appendChild(body);

  if(data.error){
    const e=document.createElement("div"); e.className="rcr-empty"; e.textContent=data.error; body.appendChild(e);
    return;
  }

  const list=document.createElement("div"); list.className="rcr-list"; body.appendChild(list);

  if(!clusters.length){
    const e=document.createElement("div"); e.className="rcr-empty";
    e.textContent="Aún no hay clusters MeshKore registrados."; list.appendChild(e);
  }

  for(const c of clusters){
    const item=document.createElement("div");
    item.className = "rcr-item" + (c.connected?" rcr-conn":"") + (sel===c.name?" rcr-on":"");
    item.dataset.name = c.name;

    const dot=document.createElement("span"); dot.className="rcr-dot"; item.appendChild(dot);

    const main=document.createElement("div"); main.className="rcr-main";
    const name=document.createElement("div"); name.className="rcr-name"; name.textContent=c.name; main.appendChild(name);
    const meta=document.createElement("div"); meta.className="rcr-meta";
    const peersTxt = c.peer_count ? `${c.peer_count} peer${c.peer_count===1?"":"s"}` : "sin peers";
    meta.textContent = `${peersTxt} · ${c.count} turno${c.count===1?"":"s"}` + (c.last_text?` · ${c.last_text}`:"");
    main.appendChild(meta);
    item.appendChild(main);

    const last=document.createElement("span"); last.className="rcr-last"; last.textContent=c.last_ts||""; item.appendChild(last);

    item.addEventListener("click", ()=>{
      el._rcrSel = (el._rcrSel===c.name) ? null : c.name;
      render(el, data, ctx);
    });
    list.appendChild(item);
  }

  // Side panel — slides in from the lateral edge of the card when a cluster is selected; a SHORTER, summarized
  // view of that one cluster (status + peers + last few turns), never the full registry.
  const panel=document.createElement("div"); panel.className="rcr-panel"; body.appendChild(panel);
  const active = sel ? clusters.find(c=>c.name===sel) : null;
  if(active){
    panel.classList.add("rcr-open");
    const phd=document.createElement("div"); phd.className="rcr-panel-hd";
    const pb=document.createElement("b"); pb.textContent=active.name; phd.appendChild(pb);
    const closeBtn=document.createElement("button"); closeBtn.className="rcr-close"; closeBtn.type="button";
    closeBtn.title="Cerrar"; closeBtn.textContent="✕";
    closeBtn.addEventListener("click", ()=>{ el._rcrSel=null; render(el,data,ctx); });
    phd.appendChild(closeBtn);
    panel.appendChild(phd);

    const status=document.createElement("div"); status.className="rcr-panel-status";
    const sdot=document.createElement("span"); sdot.className="rcr-dot"+(active.connected?" rcr-conn":""); status.appendChild(sdot);
    const slbl=document.createElement("span"); slbl.textContent = active.connected?"conectado":"desconectado"; status.appendChild(slbl);
    panel.appendChild(status);

    if(active.peers && active.peers.length){
      const peers=document.createElement("div"); peers.className="rcr-panel-peers";
      peers.textContent = "Peers: " + active.peers.join(", ");
      panel.appendChild(peers);
    }

    const turns=document.createElement("div"); turns.className="rcr-turns";
    const recent = active.recent || [];
    if(!recent.length){
      const e=document.createElement("div"); e.className="rcr-panel-empty";
      e.textContent="Sin mensajes recientes en este cluster."; turns.appendChild(e);
    } else {
      for(const t of recent){
        const dir = t.dir==="out" ? "rcr-out" : (t.dir==="in" ? "rcr-in" : "");
        const row=document.createElement("div"); row.className="rcr-turn"+(dir?" "+dir:"");
        const meta=document.createElement("div"); meta.className="rcr-turn-meta";
        const who=document.createElement("span"); who.className="rcr-turn-who"; who.textContent=whoLabel(t); meta.appendChild(who);
        const ts=document.createElement("span"); ts.textContent=t.ts||""; meta.appendChild(ts);
        row.appendChild(meta);
        const txt=document.createElement("div"); txt.className="rcr-turn-txt"; txt.textContent=t.text||""; row.appendChild(txt);
        turns.appendChild(row);
      }
    }
    panel.appendChild(turns);
    requestAnimationFrame(()=>{ turns.scrollTop = turns.scrollHeight; });
  }
}
