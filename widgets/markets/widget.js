// Markets: one price chart — name and ticker, the price, the move over the period, the line, the period tabs.
//
// Paints only what data.py hands it (the server fetches; this file never touches the network). The period tabs
// go through ctx.action("range"), the same door the voice uses, so a click and «the last month instead» cannot
// disagree. Text from the price source is set with textContent, never innerHTML.

function injectStyles(){
  if(document.getElementById("hb-markets-css"))return;
  const s=document.createElement("style"); s.id="hb-markets-css"; s.textContent=`
  .hb-mkt{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
          color:var(--hb-ink,#F2F4F7);width:100%;box-sizing:border-box;height:100%;min-height:0;
          display:flex;flex-direction:column;gap:var(--sp-3,12px)}
  .hb-mkt .mkthd{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--sp-2,8px) var(--sp-3,12px)}
  .hb-mkt .mktname{font-size:var(--fs-title,1rem);font-weight:600;line-height:var(--hb-lh-tight,1.35)}
  .hb-mkt .mktsym{font-size:var(--fs-caption,.86rem);color:var(--hb-muted,#A7B0BE)}
  .hb-mkt .mktrow{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--sp-2,8px) var(--sp-3,12px)}
  .hb-mkt .mktprice{font-size:1.9rem;font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
  .hb-mkt .mktcur{font-size:var(--fs-caption,.86rem);color:var(--hb-muted,#A7B0BE)}
  .hb-mkt .mktchg{font-size:var(--fs-ui,.95rem);font-weight:600;font-variant-numeric:tabular-nums}
  .hb-mkt .mktchg.up{color:var(--hb-ok,#6FE0B0)} .hb-mkt .mktchg.down{color:var(--hb-risk,#FF8A92)}
  .hb-mkt .mktasof{font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A7B0BE);width:100%}
  .hb-mkt .mktchart{flex:1 1 auto;min-height:150px;position:relative;background:var(--hb-bg-soft,#272D35);
          border:1px solid var(--hb-line,rgba(255,255,255,.14));border-radius:var(--hb-r-l,12px);overflow:hidden}
  .hb-mkt .mktchart svg{position:absolute;inset:0;width:100%;height:100%;display:block}
  .hb-mkt .mktlbl{position:absolute;font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A7B0BE);
          font-variant-numeric:tabular-nums;pointer-events:none}
  .hb-mkt .mkttabs{display:flex;flex-wrap:wrap;gap:var(--sp-1,4px)}
  .hb-mkt .mkttab{font:inherit;font-size:var(--fs-caption,.86rem);padding:4px 12px;border-radius:var(--hb-r-s,8px);
          border:1px solid var(--hb-line,rgba(255,255,255,.14));background:transparent;color:var(--hb-ink,#F2F4F7);
          cursor:pointer;transition:background var(--hb-t-fast,120ms)}
  .hb-mkt .mkttab:hover{background:var(--hb-hover,#3C434F)}
  .hb-mkt .mkttab:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-mkt .mkttab.is-on{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);
          border-color:color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent);font-weight:700}
  .hb-mkt .mktempty,.hb-mkt .mkterr{font-size:var(--fs-caption,.86rem);color:var(--hb-muted,#A7B0BE);padding:var(--sp-4,16px) 0}
  `; document.head.appendChild(s);
}

let _T = null;
function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.markets."+key, params); if(s && s!=="widgets.markets."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}
function txt(tag, cls, s){ const e=document.createElement(tag); if(cls)e.className=cls; if(s!=null)e.textContent=s; return e; }

const SVGNS = "http://www.w3.org/2000/svg";
function rangeLabel(r){
  return ({ "1d": tt("r_1d", null, "1D"), "5d": tt("r_5d", null, "5D"), "1mo": tt("r_1mo", null, "1M"),
            "6mo": tt("r_6mo", null, "6M"), "1y": tt("r_1y", null, "1Y"), "5y": tt("r_5y", null, "5Y") })[r] || r;
}

function drawChart(box, pts, up, rng, lang){
  if(!pts.length) return;
  const W = 1000, H = 400, PAD = 14;
  const ys = pts.map(p => p[1]), lo = Math.min(...ys), hi = Math.max(...ys);
  const span = (hi - lo) || Math.abs(hi) * 0.01 || 1;
  const x = i => pts.length === 1 ? W/2 : (i / (pts.length - 1)) * W;
  const y = v => PAD + (1 - (v - lo) / span) * (H - 2 * PAD);
  const svg = document.createElementNS(SVGNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("preserveAspectRatio", "none");
  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
  const color = up ? "var(--hb-ok,#6FE0B0)" : "var(--hb-risk,#FF8A92)";
  const area = document.createElementNS(SVGNS, "path");
  area.setAttribute("d", `${line}L${W},${H}L0,${H}Z`);
  area.setAttribute("fill", color); area.setAttribute("fill-opacity", "0.12");
  const path = document.createElementNS(SVGNS, "path");
  path.setAttribute("d", line); path.setAttribute("fill", "none"); path.setAttribute("stroke", color);
  path.setAttribute("stroke-width", "2.5"); path.setAttribute("vector-effect", "non-scaling-stroke");
  svg.appendChild(area); svg.appendChild(path); box.appendChild(svg);
  const nf = new Intl.NumberFormat(lang || undefined, { maximumFractionDigits: hi >= 1000 ? 0 : 2 });
  const hiL = txt("div", "mktlbl", nf.format(hi)); hiL.style.top = "6px"; hiL.style.right = "10px";
  const loL = txt("div", "mktlbl", nf.format(lo)); loL.style.bottom = "6px"; loL.style.right = "10px";
  const fmt = rng === "1d" ? { hour: "2-digit", minute: "2-digit" }
            : (rng === "1y" || rng === "5y") ? { month: "short", year: "2-digit" } : { day: "numeric", month: "short" };
  const df = new Intl.DateTimeFormat(lang || undefined, fmt);
  const t0 = txt("div", "mktlbl", df.format(new Date(pts[0][0] * 1000))); t0.style.bottom = "6px"; t0.style.left = "10px";
  const t1 = txt("div", "mktlbl", df.format(new Date(pts[pts.length-1][0] * 1000))); t1.style.top = "6px"; t1.style.left = "10px";
  box.appendChild(hiL); box.appendChild(loL); box.appendChild(t0); box.appendChild(t1);
}

export function render(el, data, ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  const lang = (ctx && ctx.lang) || undefined;
  injectStyles();
  el.className = "hb-mkt";
  el.textContent = "";
  const d = data || {};
  if(!d.symbol){
    el.appendChild(txt("div", "mktempty", tt("empty", null, "Ask for a stock, an index or a coin — «a chart of Apple» — and it shows up here.")));
    return;
  }
  const pts = Array.isArray(d.points) ? d.points : [];
  const pct = typeof d.change_pct === "number" ? d.change_pct : null;
  const up = pct === null ? true : pct >= 0;

  const hd = txt("div", "mkthd");
  hd.appendChild(txt("span", "mktname", String(d.name || d.symbol)));
  hd.appendChild(txt("span", "mktsym", [d.symbol, d.exchange].filter(Boolean).join(" · ")));
  el.appendChild(hd);

  const row = txt("div", "mktrow");
  if(typeof d.price === "number"){
    const nf = new Intl.NumberFormat(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    row.appendChild(txt("span", "mktprice", nf.format(d.price)));
    if(d.currency) row.appendChild(txt("span", "mktcur", String(d.currency)));
  }
  if(pct !== null){
    // the sign is said by the arrow AND the number, never by the colour alone
    const chg = txt("span", "mktchg " + (up ? "up" : "down"),
      `${up ? "▲" : "▼"} ${Math.abs(pct).toFixed(2)}% · ${rangeLabel(d.range)}`);
    row.appendChild(chg);
  }
  if(d.as_of){
    const when = new Intl.DateTimeFormat(lang, { weekday: "short", day: "numeric", month: "short",
                                                 hour: "2-digit", minute: "2-digit" }).format(new Date(d.as_of * 1000));
    row.appendChild(txt("span", "mktasof", tt("as_of", { when }, "Last price {when}")));
  }
  el.appendChild(row);

  const box = txt("div", "mktchart");
  el.appendChild(box);
  if(pts.length) drawChart(box, pts, up, d.range, lang);
  else box.appendChild(txt("div", "mkterr", tt("no_points", null, "No price history for this period.")));
  if(d.error) el.appendChild(txt("div", "mkterr", tt("stale", null, "The price source did not answer; this is the last chart it gave.")));

  const tabs = txt("div", "mkttabs");
  for(const r of (Array.isArray(d.ranges) && d.ranges.length ? d.ranges : ["1d","5d","1mo","6mo","1y","5y"])){
    const b = txt("button", "mkttab" + (r === d.range ? " is-on" : ""), rangeLabel(r));
    b.type = "button";
    b.setAttribute("aria-pressed", r === d.range ? "true" : "false");
    b.onclick = () => { try{ ctx && ctx.action && ctx.action("range", { range: r }); }catch(_){} };
    tabs.appendChild(b);
  }
  el.appendChild(tabs);
}
