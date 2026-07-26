// Registro de Agentes — client render module. Contract: render(el, data, ctx).
// data = GET /widgets/ejecuta-gestion-real/data ; ctx.action(name,payload) -> new data (re-renders) ; ctx.close().
// Cada alta/estado/baja se persiste en el store del widget (data.py), no solo en este DOM.

const STATUS_COLOR = {
  activo: "var(--hb-accent2,#16B8A6)",
  inactivo: "var(--hb-muted-2,#9aa7b8)",
  error: "var(--hb-risk,#e5484d)",
};
const NEXT_STATUS = { activo: "inactivo", inactivo: "error", error: "activo" };

function injectStyles(){
  if(document.getElementById("hb-egr-css"))return;
  const s=document.createElement("style"); s.id="hb-egr-css"; s.textContent=`
  .hb-egr{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(480px,90vw)}
  .hb-egr .egr-form{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
  .hb-egr .egr-input{flex:1 1 120px;min-width:100px;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);border-radius:9px;padding:7px 10px;font-size:12.5px}
  .hb-egr .egr-input:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}
  .hb-egr .egr-list{display:flex;flex-direction:column;gap:7px;max-height:50vh;overflow:auto}
  .hb-egr .egr-row{display:flex;align-items:center;gap:10px;border:1px solid var(--hb-line,#eef1f6);border-radius:12px;padding:9px 11px;background:var(--hb-bg,#fff)}
  .hb-egr .egr-dot{width:9px;height:9px;border-radius:50%;flex:none;cursor:pointer}
  .hb-egr .egr-body{flex:1;min-width:0}
  .hb-egr .egr-name{font-size:13.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-egr .egr-meta{font-size:11px;color:var(--hb-muted-2,#9aa7b8);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-egr .egr-times{font-size:10.5px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace;text-align:right;flex:none}
  .hb-egr .egr-rm{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);color:var(--hb-muted,#5b6b82);border-radius:8px;padding:5px 8px;font-size:14px;line-height:1;cursor:pointer;flex:none}
  .hb-egr .egr-rm:hover{border-color:var(--hb-risk,#e5484d);color:var(--hb-risk,#e5484d)}
  `; document.head.appendChild(s);
}

function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=String(text); return e; }

export function render(el, data, ctx){
  injectStyles();
  el.className="hb-egr";
  el.textContent="";

  const hd=el2("div","hbk-hd");
  hd.append(el2("b",null,"Registro de Agentes"), el2("span","hbk-sub hbk-right", `${data.count||0} registrados`));
  el.appendChild(hd);

  const form=el2("div","egr-form");
  const nameIn=el2("input","egr-input"); nameIn.placeholder="nombre del agente";
  const roleIn=el2("input","egr-input"); roleIn.placeholder="rol (opcional)";
  const addBtn=el2("button","hbk-btn","+ Registrar");
  addBtn.onclick=async()=>{
    const name=nameIn.value.trim(); if(!name)return;
    const nd=await ctx.action("register_agent",{name, role:roleIn.value.trim()});
    if(nd)render(el,nd,ctx);
  };
  form.append(nameIn, roleIn, addBtn);
  el.appendChild(form);

  const agents=data.agents||[];
  if(!agents.length){
    el.appendChild(el2("div","hbk-empty","Ningún agente registrado todavía."));
    return;
  }

  const list=el2("div","egr-list");
  agents.forEach(a=>{
    const row=el2("div","egr-row");
    const dot=el2("span","egr-dot"); dot.style.background=STATUS_COLOR[a.status]||"var(--hb-neutral,#c2ccda)";
    dot.title=`estado: ${a.status} (clic para cambiar)`;
    dot.onclick=async()=>{
      const nd=await ctx.action("update_status",{agentId:a.id, status:NEXT_STATUS[a.status]||"activo"});
      if(nd)render(el,nd,ctx);
    };
    const body=el2("div","egr-body");
    body.append(el2("div","egr-name",a.name), el2("div","egr-meta",[a.role, a.status].filter(Boolean).join(" · ")));
    const times=el2("div","egr-times", `alta ${a.registered_at}`);
    const rm=el2("button","egr-rm","✕"); rm.title="eliminar del registro";
    rm.onclick=async()=>{
      const nd=await ctx.action("remove_agent",{agentId:a.id});
      if(nd)render(el,nd,ctx);
    };
    row.append(dot, body, times, rm);
    list.appendChild(row);
  });
  el.appendChild(list);
}
