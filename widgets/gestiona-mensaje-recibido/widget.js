// Gestiona-mensaje-recibido widget — client render. Contract: render(el, data, ctx).
// data = GET /widgets/gestiona-mensaje-recibido/data ; ctx.action(name,payload) -> new data (re-renders).
// Shows the one WhatsApp message received from Gonza + its REAL status (pendiente/procesado/respondido),
// updated only when apply_action actually mutates the store — never a cosmetic-only "done".
// LOCAL TRACKER ONLY (fixed 2026-07-26 audit): "reply" saves a draft in this widget's own store — it does NOT
// send anything over WhatsApp. A real send goes through the `mensajeria` widget (reply_message). Said explicitly
// in the UI so the operator never mistakes "saved a draft here" for "Gonza received it".
// SECURITY: sender/text/reply are message content (untrusted) → always textContent, never innerHTML.

const STATUS_LABEL = {pendiente: "Pendiente", procesado: "Procesado", respondido: "Respondido"};

function injectStyles(){
  if(document.getElementById("hb-gmr-css"))return;
  const s=document.createElement("style"); s.id="hb-gmr-css"; s.textContent=`
  .hb-gmr{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(420px,90vw)}
  .hb-gmr .gmrtop{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:2px}
  .hb-gmr .gmrchip{font-size:11px;font-weight:600;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:3px 10px}
  .hb-gmr .gmrchip.pendiente{color:var(--hb-warn-ink,#9a6a00);background:var(--hb-warn-bg,#fff7e8);border-color:var(--hb-warn-border,#f2dca6)}
  .hb-gmr .gmrchip.procesado{color:var(--hb-muted,#5b6b82);background:var(--hb-bg-soft,#fbfdff)}
  .hb-gmr .gmrchip.respondido{color:#0f766e;border-color:var(--hb-accent2,#16B8A6);background:var(--hb-bg-soft,#fbfdff)}
  .hb-gmr .gmrbox{background:var(--hb-bg-soft,#fbfdff);border:1px solid var(--hb-line,#eef1f6);border-radius:12px;
                  padding:11px 13px;margin:10px 0 6px;font-size:13.5px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
  .hb-gmr .gmrmeta{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-gmr .gmrsent{margin-top:10px;border-left:3px solid var(--hb-accent2,#16B8A6);padding:8px 11px;
                   background:var(--hb-bg-soft,#fbfdff);border-radius:0 10px 10px 0;font-size:13px;white-space:pre-wrap;word-break:break-word}
  .hb-gmr .gmrsent .gmrlbl{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--hb-muted-2,#9aa7b8);display:block;margin-bottom:3px}
  .hb-gmr textarea.gmrta{width:100%;box-sizing:border-box;border:1px solid var(--hb-line,#e3e8f0);border-radius:9px;
                         padding:8px 10px;font-size:13px;font-family:inherit;color:var(--hb-ink,#0d1622);
                         background:var(--hb-bg,#fff);resize:vertical;min-height:58px;margin-top:10px}
  .hb-gmr .gmrbtnrow{display:flex;gap:8px;margin-top:9px;flex-wrap:wrap}
  .hb-gmr .gmrbtnrow button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:9px;
                            padding:7px 12px;font-size:12.5px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-gmr .gmrbtnrow button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-gmr .gmrbtnrow button.gmrprimary{border-color:var(--hb-accent2,#16B8A6);color:#0f766e}
  .hb-gmr .gmrbtnrow button.gmrprimary:hover{background:var(--hb-accent2,#16B8A6);color:#fff}
  .hb-gmr .gmrreopen{background:none;border:0;color:var(--hb-muted-2,#9aa7b8);font-size:11.5px;cursor:pointer;
                     margin-top:10px;text-decoration:underline;padding:0}
  `; document.head.appendChild(s);
}

function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=text; return e; }

export function render(el, data, ctx){
  injectStyles();
  el.className="hb-gmr";
  el.textContent="";

  const status = data.status || "pendiente";
  const card = el2("div","hbk-card");

  const hd = el2("div","hbk-hd");
  hd.append(el2("b",null,"Mensaje de "+(data.sender||"Gonza")),
             el2("span","hbk-sub", data.platform==="whatsapp" ? "WhatsApp" : (data.platform||"")),
             el2("span","hbk-sub hbk-right", data.received_at||""));
  card.appendChild(hd);

  const top = el2("div","gmrtop");
  top.appendChild(el2("span","gmrchip "+status, STATUS_LABEL[status]||status));
  card.appendChild(top);

  card.appendChild(el2("div","gmrbox", data.text||""));
  card.appendChild(el2("div","gmrmeta", "Recibido de "+(data.sender||"Gonza")+" · "+(data.platform==="whatsapp"?"WhatsApp":data.platform||"")));

  if(status==="respondido" && data.reply_text){
    const sent = el2("div","gmrsent");
    sent.append(el2("span","gmrlbl","Borrador guardado (NO enviado por WhatsApp)"), document.createTextNode(data.reply_text));
    card.appendChild(sent);
  }

  if(status==="pendiente"){
    const ta = el2("textarea","gmrta");
    ta.placeholder = "Escribe un borrador de respuesta (se guarda aquí, no se envía)…";
    card.appendChild(ta);

    const row = el2("div","gmrbtnrow");
    const bProcess = el2("button",null,"Marcar procesado");
    bProcess.onclick = async ()=>{ const nd = await ctx.action("process",{}); if(nd)render(el,nd,ctx); };
    const bReply = el2("button","gmrprimary","Guardar borrador");
    bReply.onclick = async ()=>{
      const text = ta.value.trim();
      if(!text)return;
      const nd = await ctx.action("reply",{text});
      if(nd)render(el,nd,ctx);
    };
    row.append(bProcess, bReply);
    card.appendChild(row);
    card.appendChild(el2("div","gmrmeta","Esto NO envía nada por WhatsApp — es solo una nota. Para responder de verdad, usa el widget de mensajería."));
  } else {
    const reopen = el2("button","gmrreopen","↺ Reabrir");
    reopen.onclick = async ()=>{ const nd = await ctx.action("reopen",{}); if(nd)render(el,nd,ctx); };
    card.appendChild(reopen);
  }

  el.appendChild(card);
}
