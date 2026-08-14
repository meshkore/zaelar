// Investments: token portfolio dashboard.
// DONUT allocation chart + 2x2 card grid, one card per position.
// Self-contained: styles injected once (id-guard), client-side SVG, no libraries or network.
// All server text -> textContent (XSS-safe). Theme through --hb-* vars with hex fallbacks.

const GLYPH = { BTC: "₿", ETH: "Ξ", SOL: "◎", ADA: "₳", USDT: "₮", BNB: "ⓑ", XRP: "✕", DOT: "●", LINK: "🔗", MATIC: "⬡" };
// Four distinct colors that remain readable in light and dark themes (host accents + fixed violet/amber).
const COLORS = ["var(--hb-accent,#3D6FE0)", "var(--hb-accent2,#16B8A6)", "#8B5CF6", "#F59E0B", "#EC4899", "#10B981"];

function injectStyles(){
  if(document.getElementById("hb-inv-css")) return;
  const s = document.createElement("style"); s.id = "hb-inv-css"; s.textContent = `
  .hb-inv{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(620px,94vw)}
  .hb-inv .hd{display:flex;align-items:baseline;gap:10px;margin:0 0 14px;flex-wrap:wrap}
  .hb-inv .hd b{font-size:17px;font-weight:600}
  .hb-inv .hd .sub{font-size:12px;color:var(--hb-muted,#3a4757)}
  .hb-inv .hd .tot{margin-left:auto;font-family:ui-monospace,Menlo,monospace;font-size:15px;font-weight:700}
  .hb-inv .body{display:flex;gap:18px;flex-wrap:wrap;align-items:center}
  /* Donut panel: left padding == bottom padding (26==26), keeping the chart large and centered. */
  .hb-inv .donut-wrap{padding:10px 6px 26px 26px;display:flex;align-items:center;justify-content:center}
  .hb-inv .donut-wrap svg{display:block;width:212px;height:212px;max-width:46vw}
  .hb-inv .hole{fill:var(--hb-bg,#fff)}
  .hb-inv .seg{fill:none;stroke-width:34;transition:stroke-dasharray .3s}
  .hb-inv .ctr-t{font-size:11px;fill:var(--hb-muted-2,#7d8a9c);text-anchor:middle;font-family:-apple-system,inherit,sans-serif}
  .hb-inv .ctr-v{font-size:21px;fill:var(--hb-ink,#0d1622);text-anchor:middle;font-weight:700;font-family:ui-monospace,Menlo,monospace}
  /* 2x2 grid: each position is its own card (border + background), with generous gaps; 4 data items, not 4 columns. */
  .hb-inv .grid{display:grid;grid-template-columns:1fr 1fr;gap:13px;flex:1 1 260px;min-width:240px}
  .hb-inv .box{position:relative;background:var(--hb-bg-soft,#f3f6fb);border:1px solid var(--hb-line,#eef1f6);border-radius:13px;padding:12px 14px 12px 20px;overflow:hidden}
  .hb-inv .box .bar{position:absolute;left:0;top:0;bottom:0;width:4px}
  .hb-inv .box .r1{display:flex;align-items:center;gap:9px}
  .hb-inv .box .ic{width:24px;height:24px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:12px;flex:0 0 auto}
  .hb-inv .box .nm{font-size:13px;font-weight:600;line-height:1.1}
  .hb-inv .box .tk{font-size:10.5px;color:var(--hb-muted-2,#7d8a9c);font-family:ui-monospace,Menlo,monospace;margin-top:1px}
  .hb-inv .box .r2{display:flex;align-items:baseline;gap:8px;margin-top:7px}
  .hb-inv .box .val{font-size:17px;font-weight:700;font-family:ui-monospace,Menlo,monospace}
  .hb-inv .box .pct{font-size:10.5px;color:var(--hb-muted-2,#7d8a9c);font-family:ui-monospace,Menlo,monospace}
  .hb-inv .box .chg{margin-left:auto;font-size:11.5px;font-weight:600;font-family:ui-monospace,Menlo,monospace}
  .hb-inv .up{color:#16B8A6}.hb-inv .dn{color:var(--hb-risk,#e0556a)}
  .hb-inv .note{margin-top:14px;font-size:11.5px;color:var(--hb-warn-ink,#9a6b14);background:var(--hb-warn-bg,#fdf6e3);border:1px solid var(--hb-warn-border,#f3e2b3);border-radius:10px;padding:8px 11px}
  .hb-inv .empty{font-size:13px;color:var(--hb-muted-2,#7d8a9c);padding:18px;text-align:center;border:1px dashed var(--hb-line,#e3e8f0);border-radius:12px}
  `; document.head.appendChild(s);
}

const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs){
  const el = document.createElementNS(SVG_NS, tag);
  if(attrs) for(const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

function fmtMoney(v, cur){
  try{
    const n = new Intl.NumberFormat("es-ES", {maximumFractionDigits:0}).format(Math.round(v || 0));
    return n + " " + (cur || "€");
  }catch(e){ return Math.round(v || 0) + " " + (cur || "€"); }
}

export function render(el, data, ctx){
  injectStyles();
  el.className = "hb-inv";
  el.textContent = "";

  const mk = (tag, cls, txt) => {
    const e = document.createElement(tag);
    if(cls) e.className = cls;
    if(txt != null) e.textContent = txt;
    return e;
  };

  const cur = data.currency || "€";
  const holdings = Array.isArray(data.holdings) ? data.holdings : [];

  // Header.
  const hd = mk("div", "hd");
  hd.appendChild(mk("b", null, data.title || "Cartera de inversiones"));
  hd.appendChild(mk("span", "sub", holdings.length + (holdings.length === 1 ? " posición" : " posiciones")));
  hd.appendChild(mk("span", "tot", "Total " + fmtMoney(data.total || 0, cur)));
  el.appendChild(hd);

  if(!holdings.length){
    el.appendChild(mk("div", "empty", "Sin posiciones. Dime tus tokens y cantidades y los cargo."));
    return;
  }

  const body = mk("div", "body");

  // ---- DONUT ----
  const C = 2 * Math.PI * 80;            // circumference (r=80)
  const GAP = 1.6;                        // visual gap between segments
  const dwrap = mk("div", "donut-wrap");
  const root = svg("svg", {viewBox: "0 0 240 240", preserveAspectRatio: "xMidYMid meet", role: "img", "aria-label": "Asignación de la cartera"});
  const g = svg("g", {transform: "rotate(-90 120 120)"});
  let acc = 0;
  holdings.forEach((h, i) => {
    const frac = (data.total > 0) ? (h.value / data.total) : 0;
    const seg = Math.max(0, frac * C - GAP);
    const c = svg("circle", {
      class: "seg", cx: "120", cy: "120", r: "80",
      stroke: COLORS[i % COLORS.length],
      "stroke-dasharray": seg.toFixed(2) + " " + (C - seg).toFixed(2),
      "stroke-dashoffset": (-acc).toFixed(2),
      "stroke-linecap": "butt"
    });
    const title = svg("title"); title.textContent = h.name + " · " + (frac * 100).toFixed(1) + "%";
    c.appendChild(title);
    g.appendChild(c);
    acc += frac * C;
  });
  root.appendChild(g);
  // Center: total in the hole.
  const lblT = svg("text", {class: "ctr-t", x: "120", y: "108"}); lblT.textContent = "Total"; root.appendChild(lblT);
  const lblV = svg("text", {class: "ctr-v", x: "120", y: "135"});
  lblV.textContent = fmtMoney(data.total || 0, cur);
  root.appendChild(lblV);
  dwrap.appendChild(root);
  body.appendChild(dwrap);

  // ---- 2x2 GRID ----
  const grid = mk("div", "grid");
  holdings.forEach((h, i) => {
    const color = COLORS[i % COLORS.length];
    const box = mk("div", "box");
    const bar = mk("div", "bar"); bar.style.background = color; box.appendChild(bar);

    const r1 = mk("div", "r1");
    const ic = mk("span", "ic"); ic.style.background = color;
    ic.textContent = GLYPH[(h.ticker || "").toUpperCase()] || (h.ticker || "?").charAt(0);
    r1.appendChild(ic);
    const nt = mk("div");
    nt.appendChild(mk("div", "nm", h.name));
    if(h.ticker) nt.appendChild(mk("div", "tk", h.ticker));
    r1.appendChild(nt);
    box.appendChild(r1);

    const r2 = mk("div", "r2");
    r2.appendChild(mk("span", "val", fmtMoney(h.value, cur)));
    const pct = (data.total > 0) ? (h.value / data.total * 100) : 0;
    r2.appendChild(mk("span", "pct", pct.toFixed(1) + "%"));
    const chg = h.change;
    const up = (chg >= 0);
    const cspan = mk("span", "chg " + (up ? "up" : "dn"));
    cspan.textContent = (up ? "▲ " : "▼ ") + Math.abs(chg).toFixed(1).replace(/\.0$/, "") + "%";
    r2.appendChild(cspan);
    box.appendChild(r2);

    grid.appendChild(box);
  });
  body.appendChild(grid);

  el.appendChild(body);

  if(data.sample){
    el.appendChild(mk("div", "note", "Datos de ejemplo — dime tus tokens y cantidades reales y los cargo en el disco."));
  }
}
