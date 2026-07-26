// Ejecuta acción real — vista viva de las acciones del mundo real que el cerebro rápido escaló a un worker
// (V2-061): pendiente → en curso → verificada/fallida. El worker (puente hbwidget) y el FlashBrain conducen la
// tarjeta con las data-ops de manifest.json (queue/progress/verified/failed/retry/dismiss); esta vista solo
// pinta lo que hay en data.actions y re-renderiza cuando el host la refresca (SSE, sin polling).

function injectStyles(){
  if(document.getElementById("hb-ejecuta-real-css"))return;
  const s=document.createElement("style"); s.id="hb-ejecuta-real-css"; s.textContent=`
  .hb-ejecuta-real{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(480px,90vw)}
  .hb-ejecuta-real .eje-list{display:flex;flex-direction:column;gap:10px;max-height:56vh;overflow:auto;margin-top:10px}
  .hb-ejecuta-real .eje-card{border:1px solid var(--hb-line,#eef1f6);border-left:3px solid var(--hb-neutral,#c2ccda);border-radius:12px;padding:10px 12px;background:var(--hb-bg,#fff)}
  .hb-ejecuta-real .eje-card.running{border-left-color:var(--hb-accent,#3D6FE0)}
  .hb-ejecuta-real .eje-card.verified{border-left-color:var(--hb-accent2,#16B8A6)}
  .hb-ejecuta-real .eje-card.failed{border-left-color:var(--hb-risk,#e5484d)}
  .hb-ejecuta-real .eje-top{display:flex;align-items:center;gap:8px}
  .hb-ejecuta-real .eje-desc{font-size:14px;font-weight:600;flex:1}
  .hb-ejecuta-real .eje-badge{font-size:11px;border-radius:999px;padding:2px 9px;white-space:nowrap}
  .hb-ejecuta-real .eje-badge.pending{background:var(--hb-bg-soft,#fbfdff);color:var(--hb-muted,#5b6b82)}
  .hb-ejecuta-real .eje-badge.running{background:rgba(61,111,224,.14);color:var(--hb-accent,#3D6FE0)}
  .hb-ejecuta-real .eje-badge.verified{background:rgba(22,184,166,.14);color:var(--hb-accent2,#16B8A6)}
  .hb-ejecuta-real .eje-badge.failed{background:rgba(229,72,77,.14);color:var(--hb-risk,#e5484d)}
  .hb-ejecuta-real .eje-target{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);margin-top:2px}
  .hb-ejecuta-real .eje-steps{margin-top:7px;display:flex;flex-direction:column;gap:3px}
  .hb-ejecuta-real .eje-step{font-size:12px;color:var(--hb-muted,#5b6b82);line-height:1.4}
  .hb-ejecuta-real .eje-step .ts{font-family:ui-monospace,Menlo,monospace;color:var(--hb-muted-2,#9aa7b8);margin-right:6px}
  .hb-ejecuta-real .eje-reason{margin-top:6px;font-size:12px;color:var(--hb-risk,#e5484d)}
  .hb-ejecuta-real .eje-acts{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
  .hb-ejecuta-real .eje-acts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:9px;padding:5px 10px;font-size:11.5px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-ejecuta-real .eje-acts button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  `; document.head.appendChild(s);
}

const STATUS_LABEL = {pending: "pendiente", running: "en curso", verified: "verificada", failed: "fallida"};

// DOM builder — el texto viene de un worker/proceso (no confiable) → SIEMPRE textContent, nunca innerHTML.
function el2(tag, cls, text){ const e = document.createElement(tag); if (cls) e.className = cls;
  if (text != null) e.textContent = String(text); return e; }

export function render(el, data, ctx){
  injectStyles();
  el.className = "hb-ejecuta-real";
  el.textContent = "";

  const hd = el2("div", "hbk-hd");
  hd.appendChild(el2("b", null, "Acción real pendiente"));
  hd.appendChild(el2("span", "hbk-sub hbk-right", data.pending ? `${data.pending} en curso` : "al día"));
  el.appendChild(hd);

  const actions = data.actions || [];
  if (!actions.length){
    el.appendChild(el2("div", "hbk-empty", "No hay acciones reales pendientes."));
    return;
  }

  const list = el2("div", "eje-list");
  actions.forEach(a => {
    const status = a.status || "pending";
    const card = el2("div", "eje-card " + status);

    const top = el2("div", "eje-top");
    top.appendChild(el2("span", "eje-desc", a.desc || ""));
    top.appendChild(el2("span", "eje-badge " + status, STATUS_LABEL[status] || status));
    card.appendChild(top);

    if (a.target) card.appendChild(el2("div", "eje-target", a.target));

    const steps = (a.steps || []).slice(-4);
    if (steps.length){
      const box = el2("div", "eje-steps");
      steps.forEach(s => {
        const row = el2("div", "eje-step");
        row.appendChild(el2("span", "ts", s.ts || ""));
        row.appendChild(document.createTextNode(s.note || ""));
        box.appendChild(row);
      });
      card.appendChild(box);
    }

    if (status === "failed" && a.reason) card.appendChild(el2("div", "eje-reason", a.reason));

    const acts = el2("div", "eje-acts");
    if (status === "failed"){
      const retry = el2("button", null, "↻ Reintentar");
      retry.dataset.a = "retry"; retry.dataset.id = a.id; acts.appendChild(retry);
    }
    const dismiss = el2("button", null, "Descartar");
    dismiss.dataset.a = "dismiss"; dismiss.dataset.id = a.id; acts.appendChild(dismiss);
    card.appendChild(acts);

    list.appendChild(card);
  });
  el.appendChild(list);

  el.querySelectorAll("[data-a]").forEach(btn => btn.onclick = async () => {
    const nd = await ctx.action(btn.dataset.a, {actionId: btn.dataset.id});
    if (nd) render(el, nd, ctx);
  });
}
