// Pomodoro widget — client render module (lazy-loaded by the canvas host). Contract: render(el, data, ctx).
// data = GET /widgets/temporizador-pomodoro-ayudar/data ; ctx.action(name,payload) -> new data ; ctx.close().
// Self-contained: scoped styles, circular countdown, phase/break tracking. The remaining seconds tick LOCALLY
// (cosmetic display only, never polling) from the fresh `remaining` the backend hands us on each re-render.

function injectStyles(){
  if(document.getElementById("hb-pomo-css"))return;
  const s=document.createElement("style"); s.id="hb-pomo-css"; s.textContent=`
  .hb-pomo{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(320px,90vw);text-align:center}
  .hb-pomo .pomo-hd{display:flex;align-items:baseline;gap:8px;margin:0 0 14px}
  .hb-pomo .pomo-hd b{font-size:16px}
  .hb-pomo .pomo-phase{font-size:12.5px;color:var(--hb-muted,#5b6b82)}
  .hb-pomo .pomo-done{margin-left:auto;font-size:12px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace}
  .hb-pomo .pomo-ring{position:relative;width:186px;height:186px;margin:0 auto}
  .hb-pomo .pomo-ring svg{display:block;transform:rotate(-90deg)}
  .hb-pomo .pomo-ring circle{transition:stroke-dashoffset .3s linear}
  .hb-pomo .pomo-face{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px}
  .hb-pomo .pomo-clock{font-size:44px;font-weight:600;font-variant-numeric:tabular-nums;font-family:ui-monospace,Menlo,monospace;letter-spacing:1px;color:var(--hb-ink,#0d1622)}
  .hb-pomo .pomo-state{font-size:10.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--hb-muted-2,#9aa7b8)}
  .hb-pomo .pomo-dots{display:flex;justify-content:center;gap:7px;margin:15px 0 16px}
  .hb-pomo .pomo-dot{width:9px;height:9px;border-radius:50%;background:var(--hb-neutral,#c2ccda)}
  .hb-pomo .pomo-dot.on{background:var(--hb-accent,#3D6FE0)}
  .hb-pomo .pomo-acts{display:flex;justify-content:center;gap:8px}
  .hb-pomo .pomo-acts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:10px;padding:9px 16px;font-size:13px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-pomo .pomo-acts button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-pomo .pomo-acts button.pomo-primary{background:var(--hb-accent,#3D6FE0);border-color:var(--hb-accent,#3D6FE0);color:#fff}
  .hb-pomo .pomo-acts button.pomo-primary:hover{color:#fff;opacity:.9}
  `; document.head.appendChild(s);
}

const NS="http://www.w3.org/2000/svg";
function elc(tag, cls, txt){ const e=document.createElement(tag); if(cls)e.className=cls; if(txt!=null)e.textContent=String(txt); return e; }
function svg(tag, attrs){ const e=document.createElementNS(NS,tag); for(const k in attrs)e.setAttribute(k,String(attrs[k])); return e; }

export function render(el, data, ctx){
  injectStyles();
  if(el._pomoTimer){clearInterval(el._pomoTimer);el._pomoTimer=null;}
  data = data || {};

  const total   = Math.max(1, Number(data.total)||25*60);
  const running = !!data.running;
  const isWork  = (data.phase||"work")==="work";
  const col     = isWork ? "var(--hb-accent,#3D6FE0)" : "var(--hb-accent2,#16B8A6)";

  el.className="hb-pomo";
  el.textContent="";

  // header — title · phase · completed count
  const hd=elc("div","pomo-hd");
  hd.append(elc("b",null,"Pomodoro"), elc("span","pomo-phase",data.phase_label||"Concentración"),
            elc("span","pomo-done","✓ "+(Number(data.completed)||0)));
  el.appendChild(hd);

  // circular countdown ring (inline SVG, self-contained — no libs)
  const R=85, C=2*Math.PI*R;
  const ring=elc("div","pomo-ring");
  const s=svg("svg",{width:186,height:186,viewBox:"0 0 186 186"});
  s.appendChild(svg("circle",{cx:93,cy:93,r:R,fill:"none",stroke:"var(--hb-line,#eef1f6)","stroke-width":10}));
  const prog=svg("circle",{cx:93,cy:93,r:R,fill:"none",stroke:col,"stroke-width":10,
    "stroke-linecap":"round","stroke-dasharray":C,"stroke-dashoffset":0});
  s.appendChild(prog); ring.appendChild(s);

  const face=elc("div","pomo-face");
  const clock=elc("div","pomo-clock","25:00");
  face.append(clock, elc("div","pomo-state",running?"en marcha":"en pausa"));
  ring.appendChild(face); el.appendChild(ring);

  // pomodoros completed in the current set (before the long break)
  const every=Math.max(1,Number(data.long_every)||4), cyc=Math.max(0,Number(data.cycle)||0);
  const dots=elc("div","pomo-dots");
  for(let i=0;i<every;i++) dots.appendChild(elc("span","pomo-dot"+(i<cyc?" on":"")));
  el.appendChild(dots);

  // controls
  const acts=elc("div","pomo-acts");
  const main=elc("button","pomo-primary",running?"Pausar":"Iniciar"); main.dataset.a=running?"pause":"start";
  const reset=elc("button",null,"Reiniciar"); reset.dataset.a="reset";
  const skip=elc("button",null,"Saltar"); skip.dataset.a="skip";
  acts.append(main,reset,skip); el.appendChild(acts);

  // local cosmetic tick: derive an absolute end time from the fresh `remaining`, then count down the display.
  const endAt = running ? Date.now() + (Number(data.remaining)||0)*1000 : null;
  let autofired=false;
  function paint(){
    const rem = running ? Math.max(0,Math.round((endAt-Date.now())/1000)) : Math.max(0,Number(data.remaining)||0);
    clock.textContent = String(Math.floor(rem/60)).padStart(2,"0")+":"+String(rem%60).padStart(2,"0");
    const frac=Math.max(0,Math.min(1,rem/total));
    prog.setAttribute("stroke-dashoffset", String(C*(1-frac)));
    if(running && rem<=0 && !autofired){                    // phase finished on screen → advance server-side, once
      autofired=true;
      if(el._pomoTimer){clearInterval(el._pomoTimer);el._pomoTimer=null;}
      Promise.resolve(ctx&&ctx.action&&ctx.action("skip",{})).then(nd=>{ if(nd)render(el,nd,ctx); });
    }
  }
  paint();
  if(running) el._pomoTimer=setInterval(paint,250);

  // buttons → host applies the data-op + re-renders from fresh data
  el.querySelectorAll("[data-a]").forEach(btn=>btn.onclick=async()=>{
    const nd=await ctx.action(btn.dataset.a,{});
    if(nd)render(el,nd,ctx);
  });
}
