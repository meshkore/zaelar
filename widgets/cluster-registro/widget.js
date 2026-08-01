// cluster-registro widget — full log of the MeshKore 'arena' cluster collaboration.
// Renders each cluster turn as a chat-style row (zaelar / peer, in/out, ts, text). Scrollable, most-recent at bottom.
// Self-contained: no external deps. All third-party text goes through textContent (never innerHTML) — XSS safe.

function injectStyles(){
  if(document.getElementById("hb-clusterreg-css"))return;
  const s=document.createElement("style"); s.id="hb-clusterreg-css"; s.textContent=`
  .hb-clusterreg{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(620px,90vw)}
  .hb-clusterreg .hd{display:flex;align-items:baseline;gap:10px;margin:0 0 10px}
  .hb-clusterreg .hd b{font-size:15px;font-weight:600}
  .hb-clusterreg .hd .sub{font-size:12px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-clusterreg .hd .at{font-family:ui-monospace,Menlo,monospace;color:var(--hb-muted-2,#7d8a9c);font-size:12px;margin-left:auto}
  .hb-clusterreg .hd .status{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-clusterreg .hd .status .dot{width:7px;height:7px;border-radius:50%;background:var(--hb-neutral,#c2ccda)}
  .hb-clusterreg .hd .status.on .dot{background:var(--hb-accent2,#16B8A6)}
  .hb-clusterreg .hd .status.off .dot{background:var(--hb-risk,#e5484d)}
  .hb-clusterreg .list{display:flex;flex-direction:column;gap:8px;max-height:58vh;overflow:auto;padding:2px 2px 4px;
                       border:1px solid var(--hb-line,#eef1f6);border-radius:12px;background:var(--hb-bg,#fff)}
  .hb-clusterreg .row{display:flex;flex-direction:column;gap:3px;padding:9px 11px;border-radius:10px;
                      border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff);margin:6px 6px 0}
  .hb-clusterreg .row:last-child{margin-bottom:6px}
  .hb-clusterreg .row.in{border-left:3px solid var(--hb-accent,#3D6FE0)}
  .hb-clusterreg .row.out{border-left:3px solid var(--hb-accent2,#16B8A6);background:var(--hb-bg-soft,#f6fbfa)}
  .hb-clusterreg .row.note{border-left:3px solid var(--hb-neutral,#c2ccda);background:var(--hb-bg-soft,#fafbfd)}
  .hb-clusterreg .meta{display:flex;align-items:baseline;gap:8px;font-size:11.5px;color:var(--hb-muted-2,#7d8a9c);line-height:1.2}
  .hb-clusterreg .meta .who{font-weight:600;color:var(--hb-ink,#0d1622);font-size:12.5px}
  .hb-clusterreg .meta .who.out{color:#0f766e}
  .hb-clusterreg .meta .who.in{color:var(--hb-accent,#3D6FE0)}
  .hb-clusterreg .meta .arrow{font-family:ui-monospace,Menlo,monospace;color:var(--hb-muted-2,#9aa7b8)}
  .hb-clusterreg .meta .ts{margin-left:auto;font-family:ui-monospace,Menlo,monospace}
  .hb-clusterreg .txt{font-size:13.5px;line-height:1.5;color:var(--hb-ink,#0d1622);white-space:pre-wrap;word-break:break-word}
  .hb-clusterreg .empty{padding:22px 14px;text-align:center;color:var(--hb-muted-2,#7d8a9c);font-size:13px}
  .hb-clusterreg .crgbar{display:flex;align-items:flex-end;gap:8px;margin-top:8px}
  .hb-clusterreg .crgta{flex:1;resize:none;min-height:34px;max-height:90px;border:1px solid var(--hb-line,#e3e8f0);
                        border-radius:10px;padding:8px 10px;font:inherit;font-size:13px;line-height:1.35;
                        color:var(--hb-ink,#0d1622);background:var(--hb-bg,#fff)}
  .hb-clusterreg .crgta:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}
  .hb-clusterreg .crgsend{flex:none;width:34px;height:34px;border:none;border-radius:9px;
                          background:var(--hb-accent,#3D6FE0);color:#fff;font-size:15px;cursor:pointer;
                          display:flex;align-items:center;justify-content:center}
  .hb-clusterreg .crgsend:disabled{opacity:.5;cursor:default}
  .hb-clusterreg .crgerr{font-size:11.5px;color:var(--hb-risk,#e5484d);margin-top:5px}
  .hb-clusterreg .conn{display:inline-flex;gap:6px;margin-left:10px}
  .hb-clusterreg .cbtn{font:inherit;font-size:11.5px;font-weight:600;line-height:1;padding:6px 10px;border-radius:8px;
                       cursor:pointer;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
                       color:var(--hb-ink,#0d1622);transition:border-color .12s,color .12s}
  .hb-clusterreg .cbtn:disabled{opacity:.4;cursor:default}
  .hb-clusterreg .cbtn.conn-on:not(:disabled){border-color:var(--hb-accent2,#16B8A6);color:#0f766e}
  .hb-clusterreg .cbtn.conn-off:not(:disabled){border-color:var(--hb-risk,#e5484d);color:var(--hb-risk,#e5484d)}
  `; document.head.appendChild(s);
}

function whoLabel(t){
  if(t.dir==="out"||t.who==="zaelar") return "zaelar";
  if(t.dir==="in"||t.who==="peer")    return t.peer || "peer";
  return t.who || "sistema";
}
function arrowFor(t){
  if(t.dir==="out") return "⇢ " + (t.peer || t.cluster || "");
  if(t.dir==="in")  return "⇠ " + (t.peer || t.cluster || "");
  return t.cluster || "";
}

export function render(el, data, ctx){
  injectStyles();
  el.className="hb-clusterreg";
  el.textContent=""; // reset safely

  // Header (all static / trusted strings — safe to build with innerHTML for structure only)
  const hd=document.createElement("div"); hd.className="hd";
  const b=document.createElement("b"); b.textContent="Mesh for Cluster"; hd.appendChild(b);
  const sub=document.createElement("span"); sub.className="sub";
  const count=(data.turns||[]).length;
  const peers=(data.peers||[]).filter(Boolean);
  const cid=data.cluster_id||"";
  // Subheader = NOMBRE del cluster + su ID real (p. ej. meshcore · ID c_f6aae47f6fa44a428cca). El ID lo sirve
  // data.py (config/meshkore.json); si aún no llega (data.py sin recargar), se muestra solo el nombre.
  sub.textContent = `${data.cluster||"—"}${cid?` · ID ${cid}`:""} · ${count} turno${count===1?"":"s"}` + (peers.length?` · ${peers.join(", ")}`:"");
  hd.appendChild(sub);
  if(data.live_reachable){
    const st=document.createElement("span"); st.className="status " + (data.connected?"on":"off");
    const dot=document.createElement("span"); dot.className="dot"; st.appendChild(dot);
    const lbl=document.createElement("span"); lbl.textContent = data.connected?"conectado":"desconectado"; st.appendChild(lbl);
    hd.appendChild(st);
  }
  const at=document.createElement("span"); at.className="at"; at.textContent=data.at||""; hd.appendChild(at);
  // Dos botones de conexión (Conectar / Desconectar) — "opciones de conexión" en la cabecera del cluster.
  // Van por ctx.action (data-ops connect/disconnect): el POST al plano de control lo hace el SERVER por loopback,
  // no un fetch del navegador, así funciona desde cualquier dominio de acceso (el _guard de /api/meshkore/* rechaza
  // origins que no sean localhost — la ruta data-op lo evita, igual que el botón de enviar).
  const conn=document.createElement("span"); conn.className="conn";
  const cBtn=document.createElement("button"); cBtn.type="button"; cBtn.className="cbtn conn-on"; cBtn.textContent="Conectar";
  const dBtn=document.createElement("button"); dBtn.type="button"; dBtn.className="cbtn conn-off"; dBtn.textContent="Desconectar";
  if(data.live_reachable){            // refleja el estado real: deshabilita la dirección que no aplica
    cBtn.disabled = data.connected===true;
    dBtn.disabled = data.connected===false;
  }
  conn.appendChild(cBtn); conn.appendChild(dBtn); hd.appendChild(conn);
  // Botones de conexión → data-ops connect/disconnect; al volver, re-pintamos con el view_data() refrescado
  // (que ya trae el nuevo estado connected + cluster_id). Cableados AQUÍ (antes de los `return` tempranos de
  // lista vacía/error) para que respondan aunque aún no haya mensajes en el registro. Si la acción no existe
  // todavía (data.py sin recargar), restauramos el estado sin inventar nada.
  async function doConn(act){
    cBtn.disabled=true; dBtn.disabled=true;
    let nd=null;
    try{ nd=await ctx.action(act,{}); }catch(_){ nd=null; }
    if(nd && typeof nd==="object"){ render(el,nd,ctx); }
    else { cBtn.disabled = data.connected===true; dBtn.disabled = data.connected===false; }
  }
  cBtn.addEventListener("click", ()=>doConn("connect"));
  dBtn.addEventListener("click", ()=>doConn("disconnect"));
  el.appendChild(hd);
  if(data.conn_error){
    const ce=document.createElement("div"); ce.className="crgerr"; ce.textContent=data.conn_error; el.appendChild(ce);
  }

  const list=document.createElement("div"); list.className="list"; el.appendChild(list);

  if(data.error){
    const e=document.createElement("div"); e.className="empty"; e.textContent=data.error; list.appendChild(e); return;
  }
  const turns=data.turns||[];
  if(!turns.length){
    const e=document.createElement("div"); e.className="empty";
    e.textContent="Aún no hay mensajes registrados en este cluster."; list.appendChild(e); return;
  }

  // Build each row with textContent — turn.text comes from remote peers, never trust it for innerHTML.
  for(const t of turns){
    const row=document.createElement("div");
    const dir = t.dir==="out" ? "out" : (t.dir==="in" ? "in" : "note");
    row.className = "row " + dir;

    const meta=document.createElement("div"); meta.className="meta";
    const who=document.createElement("span"); who.className="who " + dir; who.textContent = whoLabel(t); meta.appendChild(who);
    const arr=document.createElement("span"); arr.className="arrow"; arr.textContent = arrowFor(t); meta.appendChild(arr);
    const ts=document.createElement("span"); ts.className="ts"; ts.textContent = t.ts || ""; meta.appendChild(ts);
    row.appendChild(meta);

    const txt=document.createElement("div"); txt.className="txt"; txt.textContent = t.text || ""; row.appendChild(txt);
    list.appendChild(row);
  }

  // Anchor scroll at the bottom (most recent) after layout.
  requestAnimationFrame(()=>{ list.scrollTop = list.scrollHeight; });

  // Chat wall input — the widget's own send box, driving the SAME 'send' data-op the brain uses.
  const bar=document.createElement("div"); bar.className="crgbar";
  const ta=document.createElement("textarea"); ta.className="crgta"; ta.rows=1;
  ta.placeholder="Escribe un mensaje al cluster…"; bar.appendChild(ta);
  const btn=document.createElement("button"); btn.className="crgsend"; btn.type="button";
  btn.title="Enviar"; btn.textContent="➤"; bar.appendChild(btn);
  el.appendChild(bar);
  if(data.send_error){
    const err=document.createElement("div"); err.className="crgerr"; err.textContent=data.send_error; el.appendChild(err);
  }

  ta.addEventListener("input", ()=>{ ta.style.height="auto"; ta.style.height=Math.min(ta.scrollHeight,90)+"px"; });
  ta.addEventListener("keydown", e=>{
    if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); doSend(); }
  });
  btn.addEventListener("click", doSend);

  async function doSend(){
    const text=ta.value.trim();
    if(!text || ta.disabled) return;
    ta.disabled=true; btn.disabled=true;
    const nd=await ctx.action("send",{text});
    if(!nd){ ta.disabled=false; btn.disabled=false; return; }
    render(el,nd,ctx);
    if(nd.send_error){
      const ta2=el.querySelector(".crgta");
      if(ta2){ ta2.value=text; ta2.focus(); }
    }
  }
}
