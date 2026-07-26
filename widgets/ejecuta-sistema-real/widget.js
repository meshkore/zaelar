// Ejecución en el sistema real — muestra el resultado de EJECUTAR de verdad el alta de un agente (pasos con
// efecto persistente en disco: crear registro / verificar / activar), no una animación de mentira. Cada agente
// es una tarjeta con su estado y el detalle de cada paso; permite reintentar un alta incompleta o dar de baja.
// data = /widgets/ejecuta-sistema-real/data ; ctx.action(name,payload) -> new data (re-renders) ; ctx.close().

function injectStyles(){
  if(document.getElementById("hb-ejsr-css"))return;
  const s=document.createElement("style"); s.id="hb-ejsr-css"; s.textContent=`
  .hb-ejsr{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(520px,90vw)}
  .hb-ejsr .ejsr-form{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
  .hb-ejsr .ejsr-form input{flex:1;min-width:110px;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;padding:6px 9px;font-size:13px;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
  .hb-ejsr .ejsr-form button{border:1px solid var(--hb-accent,#3D6FE0);background:var(--hb-accent,#3D6FE0);color:#fff;border-radius:8px;padding:6px 12px;font-size:12.5px;cursor:pointer}
  .hb-ejsr .ejsr-list{display:flex;flex-direction:column;gap:10px;max-height:52vh;overflow:auto}
  .hb-ejsr .ejsr-card{border:1px solid var(--hb-line,#eef1f6);border-radius:12px;padding:10px 12px;background:var(--hb-bg,#fff)}
  .hb-ejsr .ejsr-top{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
  .hb-ejsr .ejsr-name{font-size:14px;font-weight:600}
  .hb-ejsr .ejsr-role{font-size:12px;color:var(--hb-muted,#5b6b82)}
  .hb-ejsr .ejsr-badge{margin-left:auto;font-size:11px;border-radius:999px;padding:2px 9px;border:1px solid var(--hb-line,#e3e8f0);color:var(--hb-muted,#5b6b82)}
  .hb-ejsr .ejsr-badge.activo{color:var(--hb-accent2,#16B8A6);border-color:var(--hb-accent2,#16B8A6);background:rgba(22,184,166,.08)}
  .hb-ejsr .ejsr-badge.incompleto{color:var(--hb-warn-ink,#9a6a00);border-color:var(--hb-warn-border,#f2dca6);background:var(--hb-warn-bg,#fff7e8)}
  .hb-ejsr .ejsr-badge.baja{background:var(--hb-bg-soft,#fbfdff)}
  .hb-ejsr .ejsr-steps{margin-top:8px;display:flex;flex-direction:column;gap:3px}
  .hb-ejsr .ejsr-step{font-size:12px;color:var(--hb-muted,#5b6b82);display:flex;align-items:center;gap:7px}
  .hb-ejsr .ejsr-step .dot{width:7px;height:7px;border-radius:50%;background:var(--hb-neutral,#c2ccda);flex:none}
  .hb-ejsr .ejsr-step.ok .dot{background:var(--hb-accent2,#16B8A6)}
  .hb-ejsr .ejsr-step.fail .dot{background:var(--hb-risk,#e5484d)}
  .hb-ejsr .ejsr-meta{font-size:11px;color:var(--hb-muted-2,#9aa7b8);margin-top:6px}
  .hb-ejsr .ejsr-acts{display:flex;gap:6px;margin-top:8px}
  .hb-ejsr .ejsr-acts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:8px;padding:5px 10px;font-size:11.5px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-ejsr .ejsr-acts button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-ejsr .ejsr-empty{font-size:12.5px;color:var(--hb-muted-2,#9aa7b8);border:1px dashed var(--hb-line,#e3e8f0);border-radius:10px;padding:14px;text-align:center}
  `; document.head.appendChild(s);
}

const STATUS_LABEL = {activo:"activo en el sistema", incompleto:"incompleto", baja:"dado de baja"};

export function render(el, data, ctx){
  injectStyles();
  el.className="hb-ejsr";
  el.textContent="";
  const agents=data.agents||[];

  const hd=document.createElement("div"); hd.className="hbk-hd";
  const b=document.createElement("b"); b.textContent="Ejecución en el sistema real";
  const sub=document.createElement("span"); sub.className="hbk-sub";
  sub.textContent=agents.length?`${agents.length} agente${agents.length===1?"":"s"}`:"sin agentes";
  hd.append(b, sub); el.appendChild(hd);

  // alta manual (paridad con la data-op que ejecuta el cerebro rápido vía [[widget.data]])
  const form=document.createElement("div"); form.className="ejsr-form";
  const nameInp=document.createElement("input"); nameInp.placeholder="nombre del agente";
  const roleInp=document.createElement("input"); roleInp.placeholder="rol (opcional)";
  const btn=document.createElement("button"); btn.textContent="Ejecutar alta";
  btn.onclick=async()=>{
    const name=nameInp.value.trim(); if(!name)return;
    const nd=await ctx.action("onboard_agent", {name, role: roleInp.value.trim()});
    if(nd)render(el,nd,ctx);
  };
  form.append(nameInp, roleInp, btn); el.appendChild(form);

  const list=document.createElement("div"); list.className="ejsr-list";
  if(!agents.length){
    const empty=document.createElement("div"); empty.className="ejsr-empty";
    empty.textContent="Todavía no se ha ejecutado ninguna incorporación real.";
    list.appendChild(empty);
  }

  // last-onboarded first
  agents.slice().reverse().forEach(a=>{
    const card=document.createElement("div"); card.className="ejsr-card";

    const top=document.createElement("div"); top.className="ejsr-top";
    const nm=document.createElement("span"); nm.className="ejsr-name"; nm.textContent=a.name||a.id||"";
    top.appendChild(nm);
    if(a.role){
      const rl=document.createElement("span"); rl.className="ejsr-role"; rl.textContent="· "+a.role;
      top.appendChild(rl);
    }
    const status=a.status||"";
    const badge=document.createElement("span"); badge.className="ejsr-badge "+status;
    badge.textContent=STATUS_LABEL[status]||status||"—";
    top.appendChild(badge);
    card.appendChild(top);

    const steps=document.createElement("div"); steps.className="ejsr-steps";
    (a.steps||[]).forEach(s=>{
      const row=document.createElement("div"); row.className="ejsr-step "+(s.status==="ok"?"ok":"fail");
      const dot=document.createElement("span"); dot.className="dot"; row.appendChild(dot);
      row.appendChild(document.createTextNode((s.label||"")+(s.detail?" — "+s.detail:"")));
      steps.appendChild(row);
    });
    card.appendChild(steps);

    const meta=document.createElement("div"); meta.className="ejsr-meta";
    meta.textContent="actualizado "+(a.updated_at||"");
    card.appendChild(meta);

    const acts=document.createElement("div"); acts.className="ejsr-acts";
    if(status==="incompleto"){
      const rb=document.createElement("button"); rb.textContent="Reintentar";
      rb.onclick=async()=>{ const nd=await ctx.action("retry", {agentId:a.id}); if(nd)render(el,nd,ctx); };
      acts.appendChild(rb);
    }
    if(status==="activo"){
      const rm=document.createElement("button"); rm.textContent="Dar de baja";
      rm.onclick=async()=>{
        if(!window.confirm(`¿Dar de baja a "${a.name||a.id}" en el sistema real?`))return;
        const nd=await ctx.action("remove_agent", {agentId:a.id}); if(nd)render(el,nd,ctx);
      };
      acts.appendChild(rm);
    }
    if(acts.childNodes.length)card.appendChild(acts);

    list.appendChild(card);
  });
  el.appendChild(list);
}
