// Champions League widget — client render module. Contract: render(el, data, ctx).
// data = GET /widgets/futbol-champions/data : {competition, matchday, matches:[{home,away,home_goals,away_goals,score}], live, note}.
// Self-contained: scoped styles (id-guarded), plain DOM, theme via --hb-* variables. Read-only, no actions.
// Team names come from data → always via textContent (never innerHTML).

function injectStyles(){
  if(document.getElementById("hb-ucl-css"))return;
  const s=document.createElement("style"); s.id="hb-ucl-css"; s.textContent=`
  .hb-ucl{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(460px,90vw)}
  .hb-ucl .uclhd{display:flex;align-items:baseline;gap:8px;margin:0 0 12px}
  .hb-ucl .uclhd b{font-size:16px}
  .hb-ucl .uclhd .uclsub{font-size:12px;color:var(--hb-muted-2,#9aa7b8);margin-left:auto;font-family:ui-monospace,Menlo,monospace}
  .hb-ucl .uclmatch{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;
                    border:1px solid var(--hb-line,#eef1f6);border-radius:12px;padding:9px 12px;margin-bottom:7px;
                    background:var(--hb-bg,#fff)}
  .hb-ucl .uclteam{font-size:13.5px;line-height:1.25}
  .hb-ucl .uclteam.home{text-align:right}
  .hb-ucl .uclteam.away{text-align:left}
  .hb-ucl .uclscore{font-family:ui-monospace,Menlo,monospace;font-size:15px;font-weight:600;
                    color:var(--hb-ink,#0d1622);background:var(--hb-bg-soft,#fbfdff);
                    border:1px solid var(--hb-line,#eef1f6);border-radius:8px;padding:3px 10px;white-space:nowrap}
  .hb-ucl .uclempty{font-size:13px;color:var(--hb-muted,#5b6b82);border:1px solid var(--hb-line,#eef1f6);
                    border-radius:12px;padding:14px;text-align:center}
  .hb-ucl .uclfoot{font-size:11px;color:var(--hb-muted-2,#9aa7b8);margin-top:8px;text-align:right}
  `; document.head.appendChild(s);
}

function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=String(text); return e; }

export function render(el, data, ctx){
  injectStyles();
  data=data||{};
  el.className="hb-ucl";
  el.textContent="";

  const hd=el2("div","uclhd");
  hd.append(el2("b",null,"⚽ "+(data.competition||"Champions League")),
            el2("span","uclsub",data.matchday||""));
  el.appendChild(hd);

  const matches=Array.isArray(data.matches)?data.matches:[];
  if(!matches.length){
    el.appendChild(el2("div","uclempty", data.error?"No he podido cargar los resultados.":"Sin resultados por ahora."));
    return;
  }

  matches.forEach(m=>{
    const row=el2("div","uclmatch");
    row.append(el2("div","uclteam home", m&&m.home!=null?m.home:"—"));
    const sc=(m&&m.score!=null)?m.score
      :(m&&m.home_goals!=null&&m.away_goals!=null)?`${m.home_goals}-${m.away_goals}`:"–";
    row.append(el2("div","uclscore", sc));
    row.append(el2("div","uclteam away", m&&m.away!=null?m.away:"—"));
    el.appendChild(row);
  });

  if(data.note){ el.appendChild(el2("div","uclfoot", data.note)); }
}
