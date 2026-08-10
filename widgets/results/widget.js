// Results widget — a generic grid to PRESENT, inside our desktop, whatever the brain (Hermes) found:
// web/ad searches, products, emails, files, WhatsApp messages… Anything. The brain passes the data via the
// [[push:results]]{json}[[/push]] protocol; this just renders it. It NEVER fetches on its own.
//
// Layout: items can carry { primary: true } → rendered FIRST in the top row(s). A single primary takes the full
// width; two or more primaries share a single row, side by side (up to 2 per row). The rest are laid out below in
// a 2-column grid. If no item is primary, all go into the columned grid.
//
// Expected data shape (all fields optional except items[].title):
//   { title, subtitle, columns: 1|2, choosable, chosen, view, focus,
//     items: [ { title, subtitle, lines:[...], price, badge, url, image, primary, score,
//                images:[...], facts:[{label,value}], parts:[{kind,title,subtitle,price,url,image,lines,facts}] } ] }
// `price` renders as a prominent tag next to the title (e.g. listing searches: modelo=title, precio=price,
// año/estado go in subtitle/lines) — kept as its own field so it's never buried in free text.
// `image` (a photo URL) renders as a cover photo at the TOP of the card — for searches the operator asked to see
// "con fotos" (hoteles/piscinas/campings, anuncios con imagen). Declarative <img> of the pushed URL (no JS network
// call, same pattern as the <a> link built for `url`); a broken photo link self-removes so a dead image never wrecks the card.
// `choosable:true` (e.g. a list of available product names) makes non-link items clickable so the operator can
// PICK one — click calls apply_action("choose",{title}); the pick is highlighted LOCALLY (not via store.save/SSE
// refresh, which would refetch data.py's static fallback and discard this pushed list — see data.py).
//
// TWO PAGES (2026-08-09). `parts` makes an item COMPOSITE — a travel proposal is a hotel + a ferry + maybe a
// restaurant, and the operator compares proposals on those pieces, so the grid shows them as labelled rows
// instead of dissolving them into prose. `view:"detail"` + `focus:<title>` turn this same sheet into ONE item's
// full dossier (photo gallery, every fact, every piece expanded with its own link and times). The view lives in
// the PERSISTED payload, never in this file's local state: that is what lets "enséñame en detalle la propuesta
// uno" — a voice line, arriving through the brain — drive the screen, and lets the page survive a re-render.
//
// SECURITY: item text is web/3rd-party-sourced → built with textContent ONLY (never innerHTML).

function injectStyles(){
  if(document.getElementById("hb-results-css"))return;
  const s=document.createElement("style"); s.id="hb-results-css"; s.textContent=`
  .hb-results{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(620px,90vw)}
  .hb-results.detail{width:min(720px,92vw)}
  .hb-results .hr-hd{font-size:15px;font-weight:600;margin:0 0 3px}
  .hb-results .hr-sub{font-size:12px;color:var(--hb-muted-2,#7d8a9c);margin:0 0 12px}
  .hb-results .hr-grid{display:grid;gap:10px}
  .hb-results .hr-grid + .hr-grid{margin-top:10px}
  .hb-results .hr-card{display:block;text-decoration:none;color:inherit;border:1px solid var(--hb-line,#eef1f6);border-left:3px solid var(--hb-accent,#3D6FE0);
    border-radius:12px;padding:11px 13px;background:var(--hb-bg,#fff);transition:.15s}
  .hb-results a.hr-card:hover{border-color:var(--hb-accent,#3D6FE0);box-shadow:0 6px 18px rgba(61,111,224,.14);transform:translateY(-1px)}
  .hb-results .hr-card.primary{border-left-color:var(--hb-accent2,#16B8A6);background:var(--hb-bg-soft,#fbfffd)}
  .hb-results .hr-img{display:block;width:100%;height:130px;object-fit:cover;border-radius:8px;margin:0 0 10px;background:var(--hb-line,#eef1f6)}
  .hb-results .hr-card.primary .hr-img{height:160px}
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
  /* composite items: the pieces a proposal is made of, one labelled row each */
  .hb-results .hr-parts{margin-top:8px;border-top:1px dashed var(--hb-line,#eef1f6);padding-top:7px;display:grid;gap:5px}
  /* wrap + min-width: en una tarjeta de 2 columnas el precio (nowrap, empujado a la derecha) estrangulaba al
     título hasta partirlo letra a letra («Valenci / a → / Palma»). Con wrap el precio baja de línea entero en vez
     de robarle el ancho, y el título nunca se queda con menos de ~7em. */
  .hb-results .hr-part{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 6px;font-size:12.5px;line-height:1.35}
  .hb-results .hr-pk{flex:none;font-size:10.5px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;color:var(--hb-accent,#3D6FE0);
    background:var(--hb-bg-soft,#eef3fe);border-radius:5px;padding:1px 6px}
  .hb-results .hr-pt{flex:1 1 7em;min-width:7em;color:var(--hb-ink,#0d1622);overflow-wrap:break-word}
  .hb-results .hr-pp{flex:0 0 auto;margin-left:auto;font-weight:600;color:var(--hb-accent2,#16B8A6);white-space:nowrap}
  .hb-results .hr-more{margin-top:9px;display:inline-block;font-size:12px;font-weight:600;color:var(--hb-accent,#3D6FE0);
    background:none;border:1px solid var(--hb-line,#eef1f6);border-radius:8px;padding:4px 10px;cursor:pointer;font-family:inherit}
  .hb-results .hr-more:hover{border-color:var(--hb-accent,#3D6FE0);background:var(--hb-bg-soft,#eef3fe)}
  /* ── detail page ── */
  .hb-results .hr-back{font-size:12px;font-weight:600;color:var(--hb-accent,#3D6FE0);background:none;border:none;
    padding:0 0 8px;cursor:pointer;font-family:inherit}
  .hb-results .hr-back:hover{text-decoration:underline}
  .hb-results .hr-dt{font-size:18px;font-weight:700;line-height:1.2;word-break:break-word}
  .hb-results .hr-dprice{font-size:15px;font-weight:700;color:var(--hb-accent2,#16B8A6);margin-top:2px}
  .hb-results .hr-gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:6px;margin:11px 0}
  .hb-results .hr-gal img{width:100%;height:104px;object-fit:cover;border-radius:8px;background:var(--hb-line,#eef1f6)}
  .hb-results .hr-facts{display:grid;grid-template-columns:auto 1fr;gap:3px 12px;margin:9px 0;font-size:12.5px}
  .hb-results .hr-fl{color:var(--hb-muted-2,#7d8a9c);white-space:nowrap}
  .hb-results .hr-fv{color:var(--hb-ink,#0d1622);word-break:break-word}
  .hb-results .hr-sec{border:1px solid var(--hb-line,#eef1f6);border-radius:12px;padding:11px 13px;margin-top:10px;background:var(--hb-bg,#fff)}
  .hb-results .hr-sec .hr-pk{margin-bottom:5px;display:inline-block}
  .hb-results .hr-sect{font-size:14px;font-weight:600;margin-top:3px;word-break:break-word}
  .hb-results .hr-link{display:inline-block;margin-top:7px;font-size:12px;font-weight:600;color:var(--hb-accent,#3D6FE0);text-decoration:none;word-break:break-all}
  .hb-results .hr-link:hover{text-decoration:underline}
  `; document.head.appendChild(s);
}

function photo(url, alt, cls){
  const img=document.createElement("img"); img.className=cls;
  img.src=url; img.alt=alt||""; img.loading="lazy"; img.referrerPolicy="no-referrer";
  img.addEventListener("error",()=>img.remove());   // dead photo link → drop silently, never break the card
  return img;
}

function factsTable(facts){
  const box=document.createElement("div"); box.className="hr-facts";
  (Array.isArray(facts)?facts:[]).forEach(f=>{
    if(!f || !f.label) return;
    const l=document.createElement("div"); l.className="hr-fl"; l.textContent=String(f.label);
    const v=document.createElement("div"); v.className="hr-fv"; v.textContent=String(f.value==null?"":f.value);
    box.append(l,v);
  });
  return box.childElementCount ? box : null;
}

// ¿Cuántas columnas? Se deduce de la FORMA de las tarjetas, no de un parámetro que pueda venir mal.
// · Una tarjeta con piezas (ida/vuelta, hotel+ferry), ficha de datos larga, fotos o líneas de texto tiene estructura
//   PROPIA dentro: necesita el ancho entero o se convierte en una columna de palabras partidas.
// · Solo las tarjetas simples y cortas pueden compartir fila.
// · Y nunca se deja una tarjeta HUÉRFANA sola en la última fila con pocos items: preferimos menos columnas.
// `cap` (el `columns` del payload) solo puede REDUCIR, nunca forzar más de lo que el contenido admite.
function columnsFor(items, cap){
  const rich = items.some(it => it && (
    (it.parts && it.parts.length) ||
    (it.facts && it.facts.length > 3) ||
    (it.images && it.images.length) ||
    (it.lines && it.lines.length > 4)
  ));
  let cols = rich ? 1 : (items.length > 6 ? 3 : items.length > 3 ? 2 : 1);
  const n = Number(cap);
  if(Number.isFinite(n) && n >= 1) cols = Math.min(cols, Math.floor(n));
  cols = Math.max(1, Math.min(3, cols));
  // Huérfana DESEQUILIBRANTE: cuando no hay ni para dos filas completas, una sola tarjeta suelta debajo se lee como
  // un error de maquetación (el caso del operador: 3 propuestas en 2 columnas). Con más items una última fila
  // incompleta es normal y no se toca — bajar a 1 columna 7 tarjetas sería peor que el problema.
  if(cols > 1 && items.length < cols * 2) cols = 1;
  return cols;
}

function makeCard(it, isPrimary, choose, ctx){
  const parts = Array.isArray(it.parts) ? it.parts : [];
  const hasDetail = parts.length || (Array.isArray(it.images) && it.images.length)
                    || (Array.isArray(it.facts) && it.facts.length);
  // A composite card owns interactive children (per-piece links, "ver detalle") so it can't be an <a> — nesting
  // links/buttons inside an anchor is invalid and swallows their clicks into the outer navigation.
  const asLink = it.url && !hasDetail;
  const card = document.createElement(asLink ? "a" : "div");
  card.className = "hr-card" + (isPrimary ? " primary" : "");
  if(asLink){ card.href = it.url; card.target = "_blank"; card.rel = "noopener noreferrer"; }
  if(it.image) card.appendChild(photo(it.image, it.title, "hr-img"));
  const head = document.createElement("div"); head.className = "hr-head";
  const t = document.createElement("div"); t.className = "hr-t"; t.textContent = it.title || ""; head.appendChild(t);
  if(it.price){ const p=document.createElement("div"); p.className="hr-price"; p.textContent=it.price; head.appendChild(p); }
  card.appendChild(head);
  if(it.subtitle){ const s=document.createElement("div"); s.className="hr-s"; s.textContent=it.subtitle; card.appendChild(s); }
  // 80 lines (data.py's cap) so a full block of text — e.g. a song's lyrics — fits in one item's body, not just
  // a handful of spec-sheet bullets (2026-08-03).
  (Array.isArray(it.lines) ? it.lines : []).slice(0,80).forEach(l=>{
    const ln=document.createElement("div"); ln.className="hr-ln"; ln.textContent=String(l); card.appendChild(ln); });

  // the pieces of a composite result, so three proposals stay comparable at a glance
  if(parts.length){
    const box=document.createElement("div"); box.className="hr-parts";
    parts.forEach(p=>{
      const row=document.createElement("div"); row.className="hr-part";
      if(p.kind){ const k=document.createElement("span"); k.className="hr-pk"; k.textContent=p.kind; row.appendChild(k); }
      const pt=document.createElement("span"); pt.className="hr-pt"; pt.textContent=p.title||""; row.appendChild(pt);
      if(p.price){ const pp=document.createElement("span"); pp.className="hr-pp"; pp.textContent=p.price; row.appendChild(pp); }
      box.appendChild(row);
    });
    card.appendChild(box);
  }
  if(it.badge){ const b=document.createElement("span"); b.className="hr-badge"; b.textContent=it.badge; card.appendChild(b); }

  if(hasDetail && ctx){
    const btn=document.createElement("button"); btn.className="hr-more"; btn.type="button";
    btn.textContent="Ver detalle →";
    btn.addEventListener("click", async (e)=>{ e.preventDefault(); e.stopPropagation();
      await ctx.action("detail", { title: it.title || "" }); });
    card.appendChild(btn);
  }

  const chosenTag = document.createElement("span"); chosenTag.className = "hr-chosen-tag"; chosenTag.textContent = "✓ Elegido";
  if(choose && !asLink){
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

// ONE item, in full. This is what "enséñame en detalle la propuesta uno" paints: every photo, every fact, and
// each piece of the bundle expanded with its own price, times and link to the real source.
function renderDetail(el, data, it, ctx){
  el.className = "hb-results detail";
  el.textContent = "";

  const back=document.createElement("button"); back.className="hr-back"; back.type="button";
  back.textContent="← Volver a la lista";
  back.addEventListener("click", async ()=>{ await ctx.action("list", {}); });
  el.appendChild(back);

  const t=document.createElement("div"); t.className="hr-dt"; t.textContent=it.title||""; el.appendChild(t);
  if(it.price){ const p=document.createElement("div"); p.className="hr-dprice"; p.textContent=it.price; el.appendChild(p); }
  if(it.subtitle){ const s=document.createElement("div"); s.className="hr-s"; s.textContent=it.subtitle; el.appendChild(s); }
  if(it.badge){ const b=document.createElement("span"); b.className="hr-badge"; b.textContent=it.badge; el.appendChild(b); }

  const gallery = Array.isArray(it.images) && it.images.length ? it.images : (it.image ? [it.image] : []);
  if(gallery.length){
    const g=document.createElement("div"); g.className="hr-gal";
    gallery.forEach(u=>g.appendChild(photo(u, it.title, "")));
    el.appendChild(g);
  }

  (Array.isArray(it.lines)?it.lines:[]).slice(0,80).forEach(l=>{
    const ln=document.createElement("div"); ln.className="hr-ln"; ln.textContent=String(l); el.appendChild(ln); });

  const ft=factsTable(it.facts); if(ft) el.appendChild(ft);

  if(it.url){
    const a=document.createElement("a"); a.className="hr-link"; a.href=it.url; a.target="_blank";
    a.rel="noopener noreferrer"; a.textContent=it.url; el.appendChild(a);
  }

  (Array.isArray(it.parts)?it.parts:[]).forEach(p=>{
    const sec=document.createElement("div"); sec.className="hr-sec";
    if(p.kind){ const k=document.createElement("span"); k.className="hr-pk"; k.textContent=p.kind; sec.appendChild(k); }
    const st=document.createElement("div"); st.className="hr-sect"; st.textContent=p.title||""; sec.appendChild(st);
    if(p.price){ const pp=document.createElement("div"); pp.className="hr-dprice"; pp.textContent=p.price; sec.appendChild(pp); }
    if(p.subtitle){ const s=document.createElement("div"); s.className="hr-s"; s.textContent=p.subtitle; sec.appendChild(s); }
    if(p.image) sec.appendChild(photo(p.image, p.title, "hr-img"));
    (Array.isArray(p.lines)?p.lines:[]).forEach(l=>{
      const ln=document.createElement("div"); ln.className="hr-ln"; ln.textContent=String(l); sec.appendChild(ln); });
    const pf=factsTable(p.facts); if(pf) sec.appendChild(pf);
    if(p.url){
      const a=document.createElement("a"); a.className="hr-link"; a.href=p.url; a.target="_blank";
      a.rel="noopener noreferrer"; a.textContent=p.url; sec.appendChild(a);
    }
    el.appendChild(sec);
  });
}

function findFocused(items, focus){
  const f=String(focus||"").trim().toLowerCase();
  if(!f) return null;
  return items.find(it=>String(it&&it.title||"").trim().toLowerCase()===f)
      || items.find(it=>String(it&&it.title||"").trim().toLowerCase().includes(f))
      || null;
}

export function render(el, data, ctx){
  injectStyles();
  data = data || {};
  const items = Array.isArray(data.items) ? data.items : [];

  // second page first: if the persisted payload says we're on a detail, paint that instead of the grid
  if(data.view === "detail"){
    const it = findFocused(items, data.focus);
    if(it){ renderDetail(el, data, it, ctx); return; }
    // focus pointing at nothing (list replaced under it) → fall through to the list, never a blank screen
  }

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
    primary.forEach(it => pgrid.appendChild(makeCard(it, true, choose, ctx)));
  }

  // remaining items: LA SUPERFICIE decide el reparto (2026-08-10). Antes `data.columns` MANDABA, y un `columns:2`
  // adivinado por el modelo pisaba la heurística correcta de aquí: 3 propuestas ricas quedaron en dos columnas con
  // una huérfana en la última fila, cuando lo que tocaba era 1 columna = tres filas horizontales. Quien rellena la
  // hoja describe el CONTENIDO; cuántas columnas caben es cosa de quien conoce el CSS. `columns` pasa a ser un TOPE.
  if(rest.length){
    const cols = primary.length ? 2 : columnsFor(rest, data.columns);
    const sgrid = document.createElement("div"); sgrid.className = "hr-grid";
    sgrid.style.gridTemplateColumns = `repeat(${cols},minmax(0,1fr))`;
    el.appendChild(sgrid);
    rest.forEach(it => sgrid.appendChild(makeCard(it, false, choose, ctx)));
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
