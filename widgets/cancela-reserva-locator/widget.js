// Cancelación de reserva por localizador — client render module. Contract: render(el, data, ctx).
// data = { reservations:[{locator,provider,note,date,status,reason,updated_at}], pending } ; ctx.action(name,payload)
// -> new data (re-renders) ; ctx.close(). This card is a MIRROR of a real-world cancellation (e.g. ITV/Itevelesa):
// it never cancels anything itself — it just shows what the brain has confirmed for real.

function injectStyles(){
  if(document.getElementById("hb-crl-css"))return;
  const s=document.createElement("style"); s.id="hb-crl-css"; s.textContent=`
  .hb-crl{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(460px,90vw)}
  .hb-crl .crl-list{display:flex;flex-direction:column;gap:8px;margin-top:2px}
  .hb-crl .crl-res{border:1px solid var(--hb-line,#eef1f6);border-radius:12px;padding:10px 12px;background:var(--hb-bg,#fff);display:flex;flex-direction:column;gap:6px}
  .hb-crl .crl-top{display:flex;align-items:center;gap:8px}
  .hb-crl .crl-loc{font-family:ui-monospace,Menlo,monospace;font-size:13px;font-weight:600}
  .hb-crl .crl-prov{font-size:12px;color:var(--hb-muted,#5b6b82)}
  .hb-crl .crl-badge{margin-left:auto;font-size:11px;border-radius:999px;padding:3px 9px;border:1px solid var(--hb-line,#e3e8f0);white-space:nowrap}
  .hb-crl .crl-st-pendiente_cancelacion{color:var(--hb-warn-ink,#9a6a00);background:var(--hb-warn-bg,#fff7e8);border-color:var(--hb-warn-border,#f2dca6)}
  .hb-crl .crl-st-cancelada{color:#0f766e;background:rgba(22,184,166,.12);border-color:var(--hb-accent2,#16B8A6)}
  .hb-crl .crl-st-error{color:var(--hb-risk,#e5484d);background:rgba(229,72,77,.1);border-color:var(--hb-risk,#e5484d)}
  .hb-crl .crl-note{font-size:12.5px;color:var(--hb-muted,#5b6b82)}
  .hb-crl .crl-reason{font-size:12px;color:var(--hb-risk,#e5484d)}
  .hb-crl .crl-when{font-size:11px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-crl .crl-btns{display:flex;gap:6px;flex-wrap:wrap;margin-top:2px;align-items:center}
  .hb-crl .crl-shot-opened{font-size:12px;color:var(--hb-accent2,#16B8A6)}
  `; document.head.appendChild(s);
}

const STATUS_LABEL = {
  pendiente_cancelacion: "Cancelando…",
  cancelada: "Cancelada (confirmada real)",
  error: "No se pudo cancelar",
};

function el2(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = String(text);
  return e;
}

export function render(el, data, ctx){
  injectStyles();
  el.className = "hb-crl hbk-card";
  el.textContent = "";

  const items = data.reservations || [];

  const hd = el2("div", "hbk-hd");
  hd.appendChild(el2("b", null, "Cancelación de reserva"));
  hd.appendChild(el2("span", "hbk-sub hbk-right", items.length ? `${items.length} en seguimiento` : ""));
  el.appendChild(hd);

  if(!items.length){
    el.appendChild(el2("div", "hbk-empty", "No hay reservas en seguimiento."));
    return;
  }

  const list = el2("div", "crl-list");
  items.forEach(r => {
    const card = el2("div", "crl-res");

    const top = el2("div", "crl-top");
    top.appendChild(el2("span", "crl-loc", r.locator || ""));
    top.appendChild(el2("span", "crl-prov", r.provider || ""));
    const status = r.status || "";
    top.appendChild(el2("span", "crl-badge crl-st-" + status, STATUS_LABEL[status] || status || "—"));
    card.appendChild(top);

    if(r.note) card.appendChild(el2("div", "crl-note", r.note));
    if(status === "error" && r.reason) card.appendChild(el2("div", "crl-reason", "⚠ " + r.reason));
    if(r.updated_at) card.appendChild(el2("div", "crl-when", "Actualizado: " + r.updated_at));

    const btns = el2("div", "crl-btns");
    if(r.screenshot){
      const view = el2("button", "hbk-btn", r.screenshot_opened ? "Volver a abrir la captura" : "Ver captura");
      view.dataset.a = "view_screenshot";
      view.dataset.loc = r.locator || "";
      btns.appendChild(view);
      if(r.screenshot_opened) btns.appendChild(el2("span", "crl-shot-opened", "📷 Imagen abierta"));
    }
    const rm = el2("button", "hbk-btn", "Quitar de la lista");
    rm.dataset.a = "remove";
    rm.dataset.loc = r.locator || "";
    btns.appendChild(rm);
    card.appendChild(btns);

    list.appendChild(card);
  });
  el.appendChild(list);

  el.querySelectorAll("[data-a]").forEach(btn => {
    btn.onclick = async () => {
      const nd = await ctx.action(btn.dataset.a, { locator: btn.dataset.loc });
      if(nd) render(el, nd, ctx);
    };
  });
}
