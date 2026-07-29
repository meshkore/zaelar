// Results widget — a generic grid to PRESENT, inside our desktop, whatever the brain (Hermes) found:
// web/ad searches, products, emails, files, WhatsApp messages… Anything. The brain passes the data via the
// [[push:results]]{json}[[/push]] protocol; this just renders it. It NEVER fetches on its own.
//
// Layout: items can carry { primary: true } → rendered FIRST in the top row(s). A single primary takes the full
// width; two or more primaries share a single row, side by side (up to 2 per row). The rest are laid out below in
// a 2-column grid. If no item is primary, all go into the columned grid.
//
// Expected data shape (all fields optional except items[].title):
//   { title, subtitle, columns: 1|2, choosable, chosen, items: [ { title, subtitle, lines:[...], price, badge, url, primary } ] }
// `price` renders as a prominent tag next to the title (e.g. listing searches: modelo=title, precio=price,
// año/estado go in subtitle/lines) — kept as its own field so it's never buried in free text.
// `choosable:true` (e.g. a list of available product names) makes non-link items clickable so the operator can
// PICK one — click calls apply_action("choose",{title}); the pick is highlighted LOCALLY (not via store.save/SSE
// refresh, which would refetch data.py's static fallback and discard this pushed list — see data.py).
//
// SECURITY: item text is web/3rd-party-sourced → built with textContent ONLY (never innerHTML).

function injectStyles(){
  if(document.getElementById("hb-results-css"))return;
  const s=document.createElement("style"); s.id="hb-results-css"; s.textContent=`
  .hb-results{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(620px,90vw)}
  .hb-results .hr-hd{font-size:15px;font-weight:600;margin:0 0 3px}
  .hb-results .hr-sub{font-size:12px;color:var(--hb-muted-2,#7d8a9c);margin:0 0 12px}
  .hb-results .hr-grid{display:grid;gap:10px}
  .hb-results .hr-grid + .hr-grid{margin-top:10px}
  .hb-results .hr-card{display:block;text-decoration:none;color:inherit;border:1px solid var(--hb-line,#eef1f6);border-left:3px solid var(--hb-accent,#3D6FE0);
    border-radius:12px;padding:11px 13px;background:var(--hb-bg,#fff);transition:.15s}
  .hb-results a.hr-card:hover{border-color:var(--hb-accent,#3D6FE0);box-shadow:0 6px 18px rgba(61,111,224,.14);transform:translateY(-1px)}
  .hb-results .hr-card.primary{border-left-color:var(--hb-accent2,#16B8A6);background:var(--hb-bg-soft,#fbfffd)}
  .hb-results .hr-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
  .hb-results .hr-t{font-size:14px;font-weight:600;line-height:1.25;word-break:break-word}
  .hb-results .hr-card.primary .hr-t{font-size:15.5px}
  .hb-results .hr-price{flex:none;font-size:13px;font-weight:700;color:var(--hb-accent2,#16B8A6);white-space:nowrap}
  .hb-results .hr-s{font-size:12.5px;color:var(--hb-accent2,#16B8A6);font-weight:600;margin-top:3px}
  .hb-results .hr-card.primary .hr-s{color:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-ln{font-size:12.5px;color:var(--hb-muted,#5b6b82);margin-top:3px;line-height:1.4}
  .hb-results .hr-badge{display:inline-block;font-size:11px;color:var(--hb-accent,#3D6FE0);background:var(--hb-bg-soft,#eef3fe);border-radius:6px;padding:1px 7px;margin-top:6px}
  .hb-results .hr-empty{color:var(--hb-muted-2,#7d8a9c);font-size:13px;padding:6px 2px}
  .hb-results .hr-card.choosable{cursor:pointer}
  .hb-results .hr-card.choosable:hover{border-color:var(--hb-accent2,#16B8A6);box-shadow:0 6px 18px rgba(22,184,166,.14);transform:translateY(-1px)}
  .hb-results .hr-card.chosen{border-color:var(--hb-accent2,#16B8A6);box-shadow:0 0 0 1px var(--hb-accent2,#16B8A6) inset;cursor:default}
  .hb-results .hr-chosen-tag{display:inline-block;font-size:11px;font-weight:600;color:var(--hb-accent2,#16B8A6);margin-top:6px}
  `; document.head.appendChild(s);
}

function makeCard(it, isPrimary, choose){
  const card = document.createElement(it.url ? "a" : "div");
  card.className = "hr-card" + (isPrimary ? " primary" : "");
  if(it.url){ card.href = it.url; card.target = "_blank"; card.rel = "noopener noreferrer"; }
  const head = document.createElement("div"); head.className = "hr-head";
  const t = document.createElement("div"); t.className = "hr-t"; t.textContent = it.title || ""; head.appendChild(t);
  if(it.price){ const p=document.createElement("div"); p.className="hr-price"; p.textContent=it.price; head.appendChild(p); }
  card.appendChild(head);
  if(it.subtitle){ const s=document.createElement("div"); s.className="hr-s"; s.textContent=it.subtitle; card.appendChild(s); }
  (Array.isArray(it.lines) ? it.lines : []).slice(0,4).forEach(l=>{
    const ln=document.createElement("div"); ln.className="hr-ln"; ln.textContent=String(l); card.appendChild(ln); });
  if(it.badge){ const b=document.createElement("span"); b.className="hr-badge"; b.textContent=it.badge; card.appendChild(b); }
  const chosenTag = document.createElement("span"); chosenTag.className = "hr-chosen-tag"; chosenTag.textContent = "✓ Elegido";
  if(choose && !it.url){
    card.classList.add("choosable");
    if(choose.chosenTitle && it.title === choose.chosenTitle){ card.classList.add("chosen"); card.appendChild(chosenTag); }
    card.addEventListener("click", async () => {
      if(card.classList.contains("chosen")) return;
      choose.root.querySelectorAll(".hr-card.chosen").forEach(c => { c.classList.remove("chosen"); const tag=c.querySelector(".hr-chosen-tag"); if(tag)tag.remove(); });
      card.classList.add("chosen"); card.appendChild(chosenTag);
      await choose.ctx.action("choose", { title: it.title || "" });
    });
  }
  return card;
}

export function render(el, data, ctx){
  injectStyles();
  data = data || {};
  const items = Array.isArray(data.items) ? data.items : [];
  const total = items.length;
  const all = items.slice(0, 24);
  el.className = "hb-results";
  el.textContent = "";

  const hd = document.createElement("div"); hd.className = "hr-hd";
  hd.textContent = data.title || "Resultados"; el.appendChild(hd);
  if(data.subtitle){ const sub=document.createElement("div"); sub.className="hr-sub"; sub.textContent=data.subtitle; el.appendChild(sub); }

  if(!all.length){
    const grid=document.createElement("div"); grid.className="hr-grid";
    grid.style.gridTemplateColumns="minmax(0,1fr)"; el.appendChild(grid);
    const e=document.createElement("div"); e.className="hr-empty";
    e.textContent = data.note || "Sin resultados todavía."; grid.appendChild(e); return;
  }

  const primary = all.filter(it => it && it.primary);
  const rest = all.filter(it => !it || !it.primary);
  const choose = data.choosable ? { root: el, ctx, chosenTitle: data.chosen } : null;

  // primary items: share the top row. One primary → full width; 2+ → side by side (up to 2 per row).
  if(primary.length){
    const pcols = primary.length === 1 ? 1 : 2;
    const pgrid = document.createElement("div"); pgrid.className = "hr-grid";
    pgrid.style.gridTemplateColumns = `repeat(${pcols},minmax(0,1fr))`;
    el.appendChild(pgrid);
    primary.forEach(it => pgrid.appendChild(makeCard(it, true, choose)));
  }

  // remaining items: side grid. When primary items exist, use 2 columns (the side-projects layout).
  // Otherwise honor data.columns (back-compat for generic uses).
  if(rest.length){
    const cols = primary.length
      ? 2
      : Math.max(1, Math.min(3, data.columns || (rest.length > 6 ? 3 : rest.length > 3 ? 2 : 1)));
    const sgrid = document.createElement("div"); sgrid.className = "hr-grid";
    sgrid.style.gridTemplateColumns = `repeat(${cols},minmax(0,1fr))`;
    el.appendChild(sgrid);
    rest.forEach(it => sgrid.appendChild(makeCard(it, false, choose)));
  }

  // Faithful count: if the real pushed results exceed what we render, say so — never silently drop
  // obtained data (the operator asked for a REAL search; the interface must reflect its true size).
  if(total > all.length){
    const more = document.createElement("div"); more.className = "hr-sub";
    more.style.marginTop = "10px";
    more.textContent = `Mostrando ${all.length} de ${total} resultados.`;
    el.appendChild(more);
  }
}
