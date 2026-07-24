// Cita con el Dentista — client render module. Contract: render(el, data, ctx).
// data = GET /widgets/reserva-cita-dentista/data ; ctx.action(name,payload) -> new data (re-renders) ; ctx.close().

function injectStyles(){
  if(document.getElementById("hb-dentista-css"))return;
  const s=document.createElement("style"); s.id="hb-dentista-css"; s.textContent=`
  .hb-dentista{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(360px,88vw)}
  .hb-dentista .hbd-dt{display:flex;align-items:center;gap:12px;margin:10px 0 12px;padding:12px;border-radius:12px;
                        background:var(--hb-bg-soft,#fbfdff);border:1px solid var(--hb-line,#eef1f6)}
  .hb-dentista .hbd-day{font-size:22px;font-weight:700}
  .hb-dentista .hbd-time{font-family:ui-monospace,Menlo,monospace;font-size:20px;color:var(--hb-accent,#3D6FE0);margin-left:auto}
  .hb-dentista .hbd-status{display:inline-flex;align-items:center;gap:6px}
  .hb-dentista .hbd-dot{width:8px;height:8px;border-radius:50%;background:var(--hb-neutral,#c2ccda)}
  .hb-dentista .hbd-status.confirmed .hbd-dot{background:var(--hb-accent2,#16B8A6)}
  .hb-dentista .hbd-status.cancelled .hbd-dot{background:var(--hb-risk,#e5484d)}
  .hb-dentista .hbd-acts{display:flex;gap:8px;margin-top:10px}
  `; document.head.appendChild(s);
}

const STATUS_LABEL = {none: "Sin reservar", confirmed: "Confirmada", cancelled: "Cancelada"};

export function render(el, data, ctx){
  injectStyles();
  el.className="hb-dentista hbk-card"; el.textContent="";

  const hd=document.createElement("div"); hd.className="hbk-hd";
  const b=document.createElement("b"); b.textContent=data.title||"Dentista";
  const st=document.createElement("span"); st.className="hbk-sub hbk-right hbd-status "+(data.status||"none");
  const dot=document.createElement("span"); dot.className="hbd-dot";
  st.append(dot, document.createTextNode(" "+(STATUS_LABEL[data.status]||"Sin reservar")));
  hd.append(b, st); el.appendChild(hd);

  if(data.status==="confirmed" && data.date){
    const box=document.createElement("div"); box.className="hbd-dt";
    const day=document.createElement("span"); day.className="hbd-day"; day.textContent=data.date;
    const time=document.createElement("span"); time.className="hbd-time"; time.textContent=data.time||"";
    box.append(day, time); el.appendChild(box);
  } else if(data.status==="cancelled"){
    const empty=document.createElement("div"); empty.className="hbk-empty";
    empty.textContent="La cita fue cancelada."+(data.date?` (era el ${data.date} ${data.time||""})`:"");
    el.appendChild(empty);
  } else {
    const empty=document.createElement("div"); empty.className="hbk-empty";
    empty.textContent="Aún no hay cita reservada.";
    el.appendChild(empty);
  }

  const acts=document.createElement("div"); acts.className="hbd-acts";
  const bookBtn=document.createElement("button"); bookBtn.className="hbk-btn";
  bookBtn.textContent = data.status==="confirmed" ? "Cambiar hora" : "Reservar mañana 17:00";
  bookBtn.onclick=async()=>{
    const nd=await ctx.action("reservar", data.status==="confirmed" ? {date:data.date,time:data.time} : {date:"mañana",time:"17:00"});
    if(nd)render(el,nd,ctx);
  };
  acts.appendChild(bookBtn);
  if(data.status==="confirmed"){
    const cancelBtn=document.createElement("button"); cancelBtn.className="hbk-btn"; cancelBtn.textContent="Cancelar";
    cancelBtn.onclick=async()=>{ const nd=await ctx.action("cancelar",{}); if(nd)render(el,nd,ctx); };
    acts.appendChild(cancelBtn);
  }
  el.appendChild(acts);
}
