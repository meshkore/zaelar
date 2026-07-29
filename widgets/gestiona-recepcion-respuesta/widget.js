// gestiona-recepcion-respuesta — render module (lazy-loaded by the canvas host). Contract: render(el, data, ctx).
// data = GET /widgets/gestiona-recepcion-respuesta/data ; ctx.action(name,payload) -> new data ; ctx.close().
// Espeja la gestión del mensaje de Estefanía en WhatsApp. El texto entrante/enviado viene del exterior (WhatsApp)
// → UNTRUSTED: SIEMPRE por textContent, nunca innerHTML (XSS). Self-contained, temas via var(--hb-*).

const STEP = ["recibido", "respondiendo", "respondido"];
const STEP_LABEL = {recibido: "Recibido", respondiendo: "Respondiendo", respondido: "Respondido"};

function injectStyles(){
  if(document.getElementById("hb-grr-css"))return;
  const s=document.createElement("style"); s.id="hb-grr-css"; s.textContent=`
  .hb-grr{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(460px,90vw)}
  .hb-grr .grr-hd{display:flex;align-items:baseline;gap:9px;margin:0 0 12px}
  .hb-grr .grr-hd b{font-size:15px}
  .hb-grr .grr-ch{font-size:11px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace}
  .hb-grr .grr-at{margin-left:auto;font-size:11px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace}
  .hb-grr .grr-steps{display:flex;align-items:center;gap:6px;margin:0 0 12px}
  .hb-grr .grr-step{flex:1;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;text-align:center;
                    padding:5px 4px;border-radius:8px;border:1px solid var(--hb-line,#eef1f6);
                    color:var(--hb-muted-2,#9aa7b8);background:var(--hb-bg,#fff)}
  .hb-grr .grr-step.done{color:var(--hb-accent2,#16B8A6);border-color:var(--hb-accent2,#16B8A6)}
  .hb-grr .grr-step.on{color:#fff;background:var(--hb-accent,#3D6FE0);border-color:var(--hb-accent,#3D6FE0)}
  .hb-grr .grr-msg{border:1px solid var(--hb-line,#eef1f6);border-left:3px solid var(--hb-accent,#3D6FE0);
                   border-radius:10px;padding:10px 12px;background:var(--hb-bg-soft,#fbfdff);margin-bottom:10px}
  .hb-grr .grr-msg .grr-from{font-size:12px;font-weight:600;color:var(--hb-muted,#5b6b82);margin-bottom:4px}
  .hb-grr .grr-msg .grr-body{font-size:14px;line-height:1.45;white-space:pre-wrap;word-break:break-word}
  .hb-grr .grr-msg .grr-empty{font-size:13px;color:var(--hb-muted-2,#9aa7b8);font-style:italic}
  .hb-grr .grr-lbl{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--hb-muted-2,#9aa7b8);margin:0 0 4px}
  .hb-grr .grr-draft{width:100%;box-sizing:border-box;min-height:64px;resize:vertical;font:inherit;font-size:13.5px;
                     line-height:1.45;color:var(--hb-ink,#0d1622);background:var(--hb-bg,#fff);
                     border:1px solid var(--hb-line,#eef1f6);border-radius:10px;padding:8px 10px;margin-bottom:8px}
  .hb-grr .grr-draft:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}
  .hb-grr .grr-sent{border:1px solid var(--hb-line,#eef1f6);border-left:3px solid var(--hb-accent2,#16B8A6);
                    border-radius:10px;padding:9px 12px;background:var(--hb-bg,#fff);margin-bottom:10px}
  .hb-grr .grr-sent .grr-body{font-size:13.5px;line-height:1.45;white-space:pre-wrap;word-break:break-word}
  .hb-grr .grr-acts{display:flex;flex-wrap:wrap;gap:7px}
  .hb-grr .grr-acts button{border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff);border-radius:9px;
                           padding:7px 12px;font-size:12.5px;cursor:pointer;color:var(--hb-muted,#5b6b82)}
  .hb-grr .grr-acts button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-grr .grr-acts button.grr-primary{border-color:var(--hb-accent2,#16B8A6);color:#0f766e}
  .hb-grr .grr-acts button:disabled{opacity:.45;cursor:default}
  .hb-grr .grr-note{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);margin-top:10px;line-height:1.4}
  .hb-grr .grr-err{font-size:12px;color:var(--hb-risk,#e5484d);margin-top:8px}
  `; document.head.appendChild(s);
}

function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=String(text); return e; }

export function render(el, data, ctx){
  injectStyles();
  data = data || {};
  const status = data.status || "recibido";
  const curIdx = Math.max(0, STEP.indexOf(status));

  el.className="hb-grr";
  el.textContent="";

  // cabecera: contacto + canal + hora de recepción
  const hd=el2("div","grr-hd");
  hd.append(el2("b",null,data.contact||"Estefanía"),
            el2("span","grr-ch",data.channel||"WhatsApp"),
            el2("span","grr-at",data.repliedAt||data.receivedAt||""));
  el.appendChild(hd);

  // barra de pasos: recibido → respondiendo → respondido
  const steps=el2("div","grr-steps");
  STEP.forEach((st,i)=>{
    const c=el2("div","grr-step"+(i<curIdx?" done":(i===curIdx?" on":"")), STEP_LABEL[st]);
    steps.appendChild(c);
  });
  el.appendChild(steps);

  // mensaje entrante (texto de WhatsApp = untrusted → textContent)
  const msg=el2("div","grr-msg");
  msg.appendChild(el2("div","grr-from","Mensaje de "+(data.contact||"Estefanía")));
  if(data.incoming){ msg.appendChild(el2("div","grr-body",data.incoming)); }
  else { msg.appendChild(el2("div","grr-empty","(mensaje nuevo pendiente de gestión)")); }
  el.appendChild(msg);

  const replied = status==="respondido";

  if(replied && data.sent){
    el.appendChild(el2("div","grr-lbl","Respuesta enviada"));
    const sent=el2("div","grr-sent"); sent.appendChild(el2("div","grr-body",data.sent));
    el.appendChild(sent);
  } else {
    // borrador editable de la respuesta (aún sin enviar)
    el.appendChild(el2("div","grr-lbl","Borrador de respuesta"));
    const ta=el2("textarea","grr-draft"); ta.value=data.draft||"";
    ta.placeholder="Escribe la respuesta para Estefanía…";
    el.appendChild(ta);

    const acts=el2("div","grr-acts");
    const save=el2("button",null,"💾 Guardar borrador"); save.dataset.a="draft_reply";
    const send=el2("button","grr-primary","✓ Ya le he respondido"); send.dataset.a="mark_replied";
    acts.append(save, send);
    el.appendChild(acts);

    // los botones toman el texto del textarea en el momento del clic
    save.onclick=async()=>{ const nd=await ctx.action("draft_reply",{text:ta.value}); if(nd)render(el,nd,ctx); };
    send.onclick=async()=>{ const nd=await ctx.action("mark_replied",{text:ta.value}); if(nd)render(el,nd,ctx); };
  }

  // reset (siempre disponible, reversible)
  const bottom=el2("div","grr-acts");
  const reset=el2("button",null,"↩ Reabrir"); reset.dataset.a="reset";
  reset.disabled = status==="recibido";
  reset.onclick=async()=>{ const nd=await ctx.action("reset",{}); if(nd)render(el,nd,ctx); };
  bottom.appendChild(reset);
  el.appendChild(bottom);

  el.appendChild(el2("div","grr-note", data.note ||
    "El envío se realiza en WhatsApp (sistema real); este panel solo refleja el estado de la gestión."));
  if(data.error) el.appendChild(el2("div","grr-err","⚠ "+data.error));
}
