// Meteo Tarragona: 14-day chart with temperature at 12 h and 18 h.
// Two lines (12h in blue #3D6FE0, 18h in teal #16B8A6) over a day-based X axis.
// Self-contained: styles injected once, client-generated SVG, no external libraries and no JS-side network.
// Any server text is inserted with textContent (XSS-safe).

function injectStyles(){
  if(document.getElementById("hb-meteo-tgn-graf-css"))return;
  const s=document.createElement("style"); s.id="hb-meteo-tgn-graf-css"; s.textContent=`
  .hb-mtgn{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(820px,94vw)}
  .hb-mtgn .hd{display:flex;align-items:baseline;gap:10px;margin:0 0 10px}
  .hb-mtgn .hd b{font-size:18px}
  .hb-mtgn .hd .sub{font-size:12px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-mtgn .hd .now{font-family:ui-monospace,Menlo,monospace;color:var(--hb-muted-2,#7d8a9c);font-size:12px;margin-left:auto}
  .hb-mtgn .legend{display:flex;gap:14px;align-items:center;font-size:12px;color:var(--hb-muted,#3a4757);margin-bottom:8px}
  .hb-mtgn .legend .it{display:inline-flex;align-items:center;gap:6px}
  .hb-mtgn .legend .sw{width:10px;height:10px;border-radius:50%;display:inline-block}
  .hb-mtgn .legend .sw.h12{background:var(--hb-accent,#3D6FE0)}
  .hb-mtgn .legend .sw.h18{background:var(--hb-accent2,#16B8A6)}
  .hb-mtgn .legend .rng{margin-left:auto;color:var(--hb-muted-2,#7d8a9c);font-family:ui-monospace,Menlo,monospace}
  .hb-mtgn .chart{background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);border-radius:14px;padding:10px 8px 6px;overflow-x:auto}
  .hb-mtgn svg{display:block;width:100%;height:auto}
  .hb-mtgn .grid line{stroke:var(--hb-line,#eef1f6);stroke-width:1}
  .hb-mtgn .axis text{font-size:10.5px;fill:var(--hb-muted-2,#7d8a9c);font-family:ui-monospace,Menlo,monospace}
  .hb-mtgn .ylab text{font-size:10px;fill:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace}
  .hb-mtgn .ln{fill:none;stroke-width:2}
  .hb-mtgn .ln.h12{stroke:var(--hb-accent,#3D6FE0)}
  .hb-mtgn .ln.h18{stroke:var(--hb-accent2,#16B8A6)}
  .hb-mtgn .dot{stroke:var(--hb-bg,#fff);stroke-width:1.5}
  .hb-mtgn .dot.h12{fill:var(--hb-accent,#3D6FE0)}
  .hb-mtgn .dot.h18{fill:var(--hb-accent2,#16B8A6)}
  .hb-mtgn .val{font-size:9.5px;font-family:ui-monospace,Menlo,monospace;font-weight:600}
  .hb-mtgn .val.h12{fill:var(--hb-accent,#3D6FE0)}
  .hb-mtgn .val.h18{fill:var(--hb-accent2,#16B8A6)}
  .hb-mtgn .dow text{font-size:10.5px;fill:var(--hb-muted,#3a4757);font-family:ui-monospace,Menlo,monospace}
  .hb-mtgn .dow text.today{fill:var(--hb-ink,#0d1622);font-weight:600}
  .hb-mtgn .day text{font-size:10px;fill:var(--hb-muted-2,#7d8a9c);font-family:ui-monospace,Menlo,monospace}
  .hb-mtgn .today-bg{fill:var(--hb-bg-soft,#f3fbf9);stroke:var(--hb-accent2,#16B8A6);stroke-opacity:.25}
  .hb-mtgn .empty{font-size:13px;color:var(--hb-muted-2,#7d8a9c);padding:14px;text-align:center;border:1px dashed var(--hb-line,#e3e8f0);border-radius:10px}
  .hb-mtgn .src{font-size:11px;color:var(--hb-muted-2,#9aa7b8);margin-top:6px;text-align:right}
  `; document.head.appendChild(s);
}

const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs){
  const el=document.createElementNS(SVG_NS, tag);
  if(attrs) for(const k in attrs){ el.setAttribute(k, attrs[k]); }
  return el;
}
function fmtTemp(v){ return (v==null) ? "—" : (Math.round(v*10)/10).toString().replace(/\.0$/,"") + "°"; }

export function render(el, data, ctx){
  injectStyles();
  el.className="hb-mtgn";
  el.textContent="";

  const make=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e;};

  // Header.
  const hd=make("div","hd");
  hd.appendChild(make("b",null,"Meteo · " + (data.location || "Tarragona")));
  hd.appendChild(make("span","sub","previsión 14 días — 12 h y 18 h"));
  hd.appendChild(make("span","now", data.now || ""));
  el.appendChild(hd);

  // Error state.
  if(data.error){
    el.appendChild(make("div","empty","No he podido cargar la previsión: " + data.error));
    return;
  }

  const days = Array.isArray(data.days) ? data.days : [];
  if(!days.length){
    el.appendChild(make("div","empty","Sin datos para los próximos días."));
    return;
  }

  // Legend + range.
  const rng = data.range || {};
  const lg = make("div","legend");
  const i1 = make("span","it");
  const sw1 = document.createElement("span"); sw1.className = "sw h12"; i1.appendChild(sw1);
  i1.appendChild(document.createTextNode("12 h (mediodía)")); lg.appendChild(i1);
  const i2 = make("span","it");
  const sw2 = document.createElement("span"); sw2.className = "sw h18"; i2.appendChild(sw2);
  i2.appendChild(document.createTextNode("18 h (tarde)")); lg.appendChild(i2);
  if(rng.tmin != null && rng.tmax != null){
    lg.appendChild(make("span","rng","mín " + fmtTemp(rng.tmin) + " · máx " + fmtTemp(rng.tmax)));
  }
  el.appendChild(lg);

  // Y scale with margin around the range.
  let tmin = (rng.tmin != null) ? rng.tmin : 0;
  let tmax = (rng.tmax != null) ? rng.tmax : 30;
  if(tmax - tmin < 4){ const c=(tmax+tmin)/2; tmin=c-2; tmax=c+2; }
  const pad = Math.max(1, (tmax - tmin) * 0.12);
  tmin = Math.floor(tmin - pad);
  tmax = Math.ceil(tmax + pad);

  // SVG chart.
  const COL_W = 50;
  const LEFT = 32, RIGHT = 12, TOP = 18, BOT = 38;
  const W = LEFT + RIGHT + COL_W * days.length;
  const H = 260;
  const plotW = W - LEFT - RIGHT;
  const plotH = H - TOP - BOT;
  const xFor = (i) => LEFT + COL_W/2 + i * COL_W;
  const yFor = (t) => TOP + plotH * (1 - (t - tmin) / (tmax - tmin));

  const host = make("div","chart");
  const root = svg("svg", {viewBox:`0 0 ${W} ${H}`, width:String(W), height:String(H), preserveAspectRatio:"xMinYMid meet"});

  // Subtle highlight for today's column (offset 0).
  const todayX = LEFT + 0 * COL_W;
  root.appendChild(svg("rect", {class:"today-bg", x:String(todayX+1), y:String(TOP), width:String(COL_W-2), height:String(plotH), rx:"6", ry:"6"}));

  // Grid + Y labels (4 levels).
  const grid = svg("g", {class:"grid"});
  const ylab = svg("g", {class:"ylab"});
  const ticks = 4;
  for(let k=0; k<=ticks; k++){
    const v = tmin + (tmax - tmin) * (k / ticks);
    const y = yFor(v);
    grid.appendChild(svg("line", {x1:String(LEFT), x2:String(W - RIGHT), y1:String(y), y2:String(y)}));
    const tx = svg("text", {x:String(LEFT - 6), y:String(y + 3), "text-anchor":"end"});
    tx.textContent = Math.round(v) + "°";
    ylab.appendChild(tx);
  }
  root.appendChild(grid);
  root.appendChild(ylab);

  // Lines: only strokes between points that have values.
  function pathFor(slot){
    let d = "", penDown = false;
    days.forEach((day, i) => {
      const t = day[slot] && day[slot].temp;
      if(t == null){ penDown = false; return; }
      const x = xFor(i), y = yFor(t);
      d += (penDown ? " L " : "M ") + x.toFixed(1) + " " + y.toFixed(1);
      penDown = true;
    });
    return d;
  }
  const p12 = svg("path", {class:"ln h12", d: pathFor("h12")});
  const p18 = svg("path", {class:"ln h18", d: pathFor("h18")});
  root.appendChild(p18);
  root.appendChild(p12);

  // Points + numeric values.
  const dotsG = svg("g");
  days.forEach((day, i) => {
    const x = xFor(i);
    [["h12", -10], ["h18", 12]].forEach(([slot, dy]) => {
      const t = day[slot] && day[slot].temp;
      if(t == null) return;
      const y = yFor(t);
      const c = svg("circle", {class:"dot " + slot, cx:String(x), cy:String(y), r:"3"});
      const tt = svg("title");
      tt.textContent = day.dow + " " + day.label + " · " + (slot === "h12" ? "12 h" : "18 h") + ": " + fmtTemp(t)
        + (day[slot].desc ? " · " + day[slot].desc : "");
      c.appendChild(tt);
      dotsG.appendChild(c);
      const lab = svg("text", {class:"val " + slot, x:String(x), y:String(y + dy), "text-anchor":"middle"});
      lab.textContent = fmtTemp(t);
      dotsG.appendChild(lab);
    });
  });
  root.appendChild(dotsG);

  // X axis: weekday + dd/mm.
  const dowG = svg("g", {class:"dow"});
  const dayG = svg("g", {class:"day"});
  days.forEach((day, i) => {
    const x = xFor(i);
    const a = svg("text", {x:String(x), y:String(H - BOT + 16), "text-anchor":"middle"});
    a.textContent = day.dow || "";
    if(i === 0) a.setAttribute("class","today");
    dowG.appendChild(a);
    const b = svg("text", {x:String(x), y:String(H - BOT + 30), "text-anchor":"middle"});
    b.textContent = day.label || "";
    dayG.appendChild(b);
  });
  root.appendChild(svg("g", {class:"axis"}));
  root.appendChild(dowG);
  root.appendChild(dayG);

  host.appendChild(root);
  el.appendChild(host);

  if(data.source){
    el.appendChild(make("div","src","Fuente: " + data.source));
  }
}
