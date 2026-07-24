// Meteo Soria — pronóstico horario para hoy en formato horizontal:
// fila de horas con precipitación arriba y temperatura abajo. Scroll horizontal si no caben.
// Self-contained: scoped styles, no external libs, no network from JS. data = GET /widgets/meteo-soria/data.
// IMPORTANT: textContent for any server/text field (XSS-safe — descriptions come from the web).

function injectStyles(){
  if(document.getElementById("hb-meteo-soria-css"))return;
  const s=document.createElement("style"); s.id="hb-meteo-soria-css"; s.textContent=`
  .hb-meteo{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(880px,94vw)}
  .hb-meteo .hd{display:flex;align-items:baseline;gap:10px;margin:0 0 10px}
  .hb-meteo .hd b{font-size:18px}
  .hb-meteo .hd .sub{font-size:12px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-meteo .hd .now{font-family:ui-monospace,Menlo,monospace;color:var(--hb-muted-2,#7d8a9c);font-size:12px;margin-left:auto}
  .hb-meteo .top{display:flex;align-items:center;gap:14px;background:var(--hb-bg-soft,#fbfdff);border:1px solid var(--hb-line,#e3e8f0);border-radius:14px;padding:12px 14px;margin-bottom:12px}
  .hb-meteo .top .wicon{font-size:34px;line-height:1}
  .hb-meteo .top .t{font-size:30px;font-weight:600;color:var(--hb-ink,#0d1622)}
  .hb-meteo .top .d{font-size:13px;color:var(--hb-muted,#3a4757)}
  .hb-meteo .top .r{margin-left:auto;text-align:right;font-size:12px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-meteo .top .r b{display:block;font-size:14px;color:var(--hb-ink,#0d1622);font-weight:600}

  /* Horizontal hourly strip: each column = una hora. Precipitación arriba, hora en medio, temperatura abajo. */
  .hb-meteo .strip{display:flex;flex-direction:row;gap:6px;overflow-x:auto;overflow-y:hidden;padding:4px 2px 6px;
                   border:1px solid var(--hb-line,#eef1f6);border-radius:12px;background:var(--hb-bg,#fff);scroll-snap-type:x proximity}
  .hb-meteo .col{flex:0 0 auto;width:54px;display:flex;flex-direction:column;align-items:center;gap:4px;
                 padding:8px 4px;border-radius:9px;scroll-snap-align:start;background:transparent;border:1px solid transparent}
  .hb-meteo .col.past{opacity:.4}
  .hb-meteo .col.now{border-color:var(--hb-accent2,#16B8A6);background:var(--hb-bg-soft,#f3fbf9);box-shadow:0 0 0 1px rgba(22,184,166,.15)}

  /* Precipitación (top): barra vertical + porcentaje */
  .hb-meteo .col .rain{display:flex;flex-direction:column;align-items:center;gap:3px;width:100%}
  .hb-meteo .col .rain .pct{font-size:10.5px;color:var(--hb-muted,#3a4757);font-variant-numeric:tabular-nums;line-height:1}
  .hb-meteo .col .rain .vbar{width:6px;height:36px;background:var(--hb-line,#eef1f6);border-radius:4px;overflow:hidden;position:relative}
  .hb-meteo .col .rain .vfill{position:absolute;left:0;right:0;bottom:0;background:var(--hb-accent,#3D6FE0);border-radius:4px}
  .hb-meteo .col.wet .rain .vfill{background:var(--hb-accent2,#16B8A6)}

  /* Hora + icono (centro) */
  .hb-meteo .col .wicon{font-size:18px;line-height:1;margin-top:2px}
  .hb-meteo .col .h{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--hb-muted,#5b6b82)}

  /* Temperatura (abajo) */
  .hb-meteo .col .t{font-size:14px;font-weight:600;color:var(--hb-ink,#0d1622);font-variant-numeric:tabular-nums;margin-top:2px}

  .hb-meteo .empty{font-size:13px;color:var(--hb-muted-2,#7d8a9c);padding:14px;text-align:center;border:1px dashed var(--hb-line,#e3e8f0);border-radius:10px}
  .hb-meteo .src{font-size:11px;color:var(--hb-muted-2,#9aa7b8);margin-top:8px;text-align:right}
  `; document.head.appendChild(s);
}

function fmtTemp(v){ return (v==null) ? "—" : (Math.round(v*10)/10).toString().replace(/\.0$/,"") + "°"; }

export function render(el, data, ctx){
  injectStyles();
  el.className="hb-meteo";
  el.textContent=""; // clear

  const make=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e;};

  // Header
  const hd=make("div","hd");
  hd.appendChild(make("b",null,"Meteo · " + (data.location || "Soria")));
  hd.appendChild(make("span","sub", data.date ? "hoy " + data.date : "hoy"));
  hd.appendChild(make("span","now", data.now || ""));
  el.appendChild(hd);

  // Error / empty state (still render header)
  if(data.error){
    el.appendChild(make("div","empty", "No he podido cargar el pronóstico: " + data.error));
    return;
  }

  // Top summary
  const cur = data.current || {};
  const sum = data.summary || {};
  const top=make("div","top");
  top.appendChild(make("div","wicon", cur.icon || "•"));
  const mid=make("div"); mid.appendChild(make("div","t", fmtTemp(cur.temp)));
  mid.appendChild(make("div","d", cur.desc || sum.desc || "—"));
  top.appendChild(mid);
  const r=make("div","r");
  r.appendChild(make("b", null, "Mín " + fmtTemp(sum.temp_min) + " · Máx " + fmtTemp(sum.temp_max)));
  r.appendChild(make("span", null, "Lluvia máx: " + ((sum.rain_max==null) ? "—" : (sum.rain_max + "%"))));
  top.appendChild(r);
  el.appendChild(top);

  // Horizontal hourly strip
  const strip=make("div","strip");
  const hours = Array.isArray(data.hours) ? data.hours : [];
  if(!hours.length){
    strip.appendChild(make("div","empty","Sin datos horarios para hoy."));
  } else {
    let nowIdx = hours.findIndex(h => !h.past);
    if(nowIdx < 0) nowIdx = hours.length - 1;
    hours.forEach((h,i)=>{
      const cls=["col"];
      if(h.past) cls.push("past");
      if(i === nowIdx) cls.push("now");
      const p = (typeof h.rain_prob === "number") ? h.rain_prob : null;
      if(p != null && p >= 50) cls.push("wet");
      const col = make("div", cls.join(" "));
      col.title = (h.desc || "") + (p!=null ? " · lluvia " + p + "%" : "");

      // Precipitación arriba
      const rain = make("div","rain");
      rain.appendChild(make("div","pct", (p == null) ? "—" : (p + "%")));
      const vbar = make("div","vbar");
      const vfill = make("div","vfill");
      const pctVal = (p == null) ? 0 : Math.max(0, Math.min(100, p));
      vfill.style.height = pctVal + "%";
      vbar.appendChild(vfill);
      rain.appendChild(vbar);
      col.appendChild(rain);

      // Icono + hora (centro)
      col.appendChild(make("div","wicon", h.icon || "•"));
      col.appendChild(make("div","h", h.label || ""));

      // Temperatura abajo
      col.appendChild(make("div","t", fmtTemp(h.temp)));

      strip.appendChild(col);
    });
  }
  el.appendChild(strip);

  // Auto-scroll to the "now" column once mounted
  if(hours.length){
    requestAnimationFrame(()=>{
      const cur = strip.querySelector(".col.now");
      if(cur && cur.scrollIntoView){
        try{ cur.scrollIntoView({block:"nearest", inline:"center"}); } catch(_){}
      }
    });
  }

  if(data.source){
    el.appendChild(make("div","src","Fuente: " + data.source));
  }
}
