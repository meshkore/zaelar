// Agenda widget — client render module (lazy-loaded by the canvas host). Contract: render(el, data, ctx).
// data = GET /widgets/agenda/data ; ctx.action(name,payload) -> new data (re-renders) ; ctx.close().
// Self-contained: scoped styles, live countdown, coach actions. The render is portable (plain DOM).

const KIND = {deep:"var(--hb-accent,#3D6FE0)", admin:"var(--hb-accent2,#16B8A6)", meeting:"#9b6bff",
              break:"var(--hb-muted-2,#9aa7b8)", exercise:"#e8973a",
              personal:"var(--hb-muted,#6b7b92)", buffer:"var(--hb-neutral,#c2ccda)"};

function injectStyles(){
  if(document.getElementById("hb-agenda-css"))return;
  const s=document.createElement("style"); s.id="hb-agenda-css"; s.textContent=`
  .hb-agenda{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(760px,90vw)}
  .hb-agenda .hd{display:flex;align-items:baseline;gap:10px;margin:0 0 10px}
  .hb-agenda .hd .cals{display:flex;align-items:center;gap:7px;margin-left:auto}
  .hb-agenda .calicon{display:inline-flex;align-items:center;justify-content:center;opacity:.32;flex:0 0 auto}
  .hb-agenda .calicon.on{opacity:1}
  .hb-agenda .calicon.soon{opacity:.28;filter:grayscale(1)}
  .hb-agenda .calnote{font-size:12px;color:var(--hb-muted-2,#7d8a9c);margin:-4px 0 8px}
  .hb-agenda .hd b{font-size:18px} .hb-agenda .hd .now{font-family:ui-monospace,Menlo,monospace;color:var(--hb-muted-2,#7d8a9c);font-size:13px;margin-left:auto}
  .hb-agenda .focus{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px}
  .hb-agenda .chip{font-size:12px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:4px 10px;color:var(--hb-muted,#3a4757);background:var(--hb-bg,#fff)}
  .hb-agenda .cols{display:grid;grid-template-columns:1fr 270px;gap:14px}
  @media(max-width:620px){.hb-agenda .cols{grid-template-columns:1fr}}
  .hb-agenda .tl{display:flex;flex-direction:column;gap:5px;max-height:46vh;overflow:auto}
  .hb-agenda .blk{display:flex;gap:10px;align-items:center;padding:8px 10px;border:1px solid var(--hb-line,#eef1f6);border-radius:10px;background:var(--hb-bg,#fff)}
  .hb-agenda .blk.act{border-color:var(--hb-accent2,#16B8A6);box-shadow:0 0 0 2px rgba(22,184,166,.15)}
  .hb-agenda .blk .t{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--hb-muted-2,#7d8a9c);min-width:86px}
  .hb-agenda .blk .bar{width:4px;align-self:stretch;border-radius:3px}
  .hb-agenda .blk .lb{font-size:14px}
  .hb-agenda .now-card{border:1px solid var(--hb-line,#e3e8f0);border-radius:14px;padding:14px;background:var(--hb-bg-soft,#fbfdff);display:flex;flex-direction:column;gap:10px}
  .hb-agenda .now-card .k{font-family:ui-monospace,Menlo,monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--hb-muted-2,#9aa7b8)}
  .hb-agenda .now-card .task{font-size:16px;font-weight:600}
  .hb-agenda .count{font-family:ui-monospace,Menlo,monospace;font-size:28px;color:var(--hb-accent2,#16B8A6)}
  .hb-agenda .acts{display:flex;flex-wrap:wrap;gap:6px}
  .hb-agenda .acts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:9px;padding:7px 10px;font-size:12px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-agenda .acts button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .acts .done{border-color:var(--hb-accent2,#16B8A6);color:#0f766e}
  .hb-agenda .nudge{font-size:12.5px;color:var(--hb-warn-ink,#9a6a00);background:var(--hb-warn-bg,#fff7e8);border:1px solid var(--hb-warn-border,#f2dca6);border-radius:9px;padding:7px 10px}
  .hb-agenda .warn{font-size:12px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-agenda .replan{margin-top:4px;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:9px;padding:7px 10px;font-size:12px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-agenda .agtabs{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px}
  .hb-agenda .agtab{font-size:12px;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:999px;padding:5px 12px;cursor:pointer;color:var(--hb-muted,#5b6b82)}
  .hb-agenda .agtab:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agtab.on{background:var(--hb-accent,#3D6FE0);border-color:var(--hb-accent,#3D6FE0);color:#fff}
  .hb-agenda .agweek{display:flex;flex-direction:column;gap:8px;max-height:52vh;overflow:auto}
  .hb-agenda .agwday{border:1px solid var(--hb-line,#eef1f6);border-radius:12px;padding:10px 12px;background:var(--hb-bg,#fff);cursor:pointer}
  .hb-agenda .agwday:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agwday.today{border-color:var(--hb-accent2,#16B8A6);box-shadow:0 0 0 2px rgba(22,184,166,.12)}
  .hb-agenda .agwh{display:flex;align-items:baseline;gap:8px;margin-bottom:6px}
  .hb-agenda .agwh b{font-size:14px}
  .hb-agenda .agwh .agwd{font-size:11px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace}
  .hb-agenda .agwh .agct{margin-left:auto;font-size:11px;color:var(--hb-muted,#5b6b82)}
  .hb-agenda .agwmeet{display:flex;gap:6px;flex-wrap:wrap}
  .hb-agenda .agwpill{font-size:11px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:2px 8px;color:var(--hb-muted,#5b6b82)}
  .hb-agenda .agmonth{display:flex;flex-direction:column;gap:10px}
  .hb-agenda .agmnav{display:flex;align-items:center;justify-content:center;gap:10px}
  .hb-agenda .agmnav button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:8px;padding:3px 11px;font-size:15px;cursor:pointer;color:var(--hb-muted,#5b6b82);line-height:1}
  .hb-agenda .agmnav button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agmnav b{font-size:14px;min-width:150px;text-align:center;text-transform:capitalize}
  .hb-agenda .aggrid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;max-height:52vh;overflow:auto}
  .hb-agenda .agdow{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--hb-muted-2,#9aa7b8);text-align:center;font-family:ui-monospace,Menlo,monospace}
  .hb-agenda .agcell{min-height:60px;border:1px solid var(--hb-line,#eef1f6);border-radius:9px;padding:5px 6px;background:var(--hb-bg,#fff);display:flex;flex-direction:column;gap:3px;overflow:hidden}
  .hb-agenda .agcell.agpad{background:transparent;border-color:transparent}
  .hb-agenda .agcell.aghas{cursor:pointer}
  .hb-agenda .agcell.aghas:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agcell.today{border-color:var(--hb-accent2,#16B8A6);box-shadow:0 0 0 2px rgba(22,184,166,.12)}
  .hb-agenda .agcell .agdn{font-size:12px;color:var(--hb-muted,#5b6b82);font-family:ui-monospace,Menlo,monospace}
  .hb-agenda .agcell.today .agdn{color:var(--hb-accent2,#16B8A6);font-weight:600}
  .hb-agenda .agev{font-size:10.5px;line-height:1.25;color:var(--hb-ink,#0d1622);background:var(--hb-bg-soft,#fbfdff);border-left:2px solid var(--hb-accent,#3D6FE0);border-radius:4px;padding:1px 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-agenda .agmore{font-size:10px;color:var(--hb-muted-2,#9aa7b8)}
  `; document.head.appendChild(s);
}

function fmt(min){const m=Math.max(0,Math.round(min));return `${String(Math.floor(m/60)).padStart(2,"0")}:${String(m%60).padStart(2,"0")}`;}

// CALENDAR CONNECTORS in the header (V2-540). Official simple-icons outlines (CC0), inline as <path> so the
// widget stays self-contained with no CDN — same rule as the messaging widget's brand strip.
// CalDAV has no logo and is not a brand: it is the open protocol that reaches Outlook, Fastmail and Nextcloud
// with ONE connector, so it wears a calendar glyph. Painting a Microsoft logo on it would be a lie for a
// Fastmail account, exactly as an envelope beats a Gmail logo over there.
const SVG_NS_AG = "http://www.w3.org/2000/svg";
const CAL_SVG = {
  google: {color:"#4285F4", path:"M18.316 5.684H24v12.632h-5.684V5.684zM5.684 24h12.632v-5.684H5.684V24zM18.316 5.684V0H1.895A1.894 1.894 0 0 0 0 1.895v16.421h5.684V5.684h12.632zm-7.207 6.25v-.065c.272-.144.5-.349.687-.617s.279-.595.279-.982c0-.379-.099-.72-.3-1.025a2.05 2.05 0 0 0-.832-.714 2.703 2.703 0 0 0-1.197-.257c-.6 0-1.094.156-1.481.467-.386.311-.65.671-.793 1.078l1.085.452c.086-.249.224-.461.413-.633.189-.172.445-.257.767-.257.33 0 .602.088.816.264a.86.86 0 0 1 .322.703c0 .33-.12.589-.36.778-.24.19-.535.284-.886.284h-.567v1.085h.633c.407 0 .748.109 1.02.327.272.218.407.499.407.843 0 .336-.129.614-.387.832s-.565.327-.924.327c-.351 0-.651-.103-.897-.311-.248-.208-.422-.502-.521-.881l-1.096.452c.178.616.505 1.082.977 1.401.472.319.984.478 1.538.477a2.84 2.84 0 0 0 1.293-.291c.382-.193.684-.458.902-.794.218-.336.327-.72.327-1.149 0-.429-.115-.797-.344-1.105a2.067 2.067 0 0 0-.881-.689zm2.093-1.931l.602.913L15 10.045v5.744h1.187V8.446h-.827l-2.158 1.557zM22.105 0h-3.289v5.184H24V1.895A1.894 1.894 0 0 0 22.105 0zm-3.289 23.5l4.684-4.684h-4.684V23.5zM0 22.105C0 23.152.848 24 1.895 24h3.289v-5.184H0v3.289z"},
  icloud: {color:"#3693F3", path:"M13.762 4.29a6.51 6.51 0 0 0-5.669 3.332 3.571 3.571 0 0 0-1.558-.36 3.571 3.571 0 0 0-3.516 3A4.918 4.918 0 0 0 0 14.796a4.918 4.918 0 0 0 4.92 4.914 4.93 4.93 0 0 0 .617-.045h14.42c2.305-.272 4.041-2.258 4.043-4.589v-.009a4.594 4.594 0 0 0-3.727-4.508 6.51 6.51 0 0 0-6.511-6.27z"},
  caldav: {color:"var(--hb-muted,#6b7b92)", path:"M19 3h-1V1h-2v2H8V1H6v2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm0 18H5V9h14v12z"},
};

// One connector icon. Dimmed means NOT linked; the title says WHICH of the two reasons, because «you have not
// linked it» and «we have not built it» are different sentences and only one of them is the operator's to fix.
function calIcon(c){
  const spec=CAL_SVG[c.id];
  const on=c.status==="connected";
  const wrap=el2("span","calicon"+(on?" on":"")+(c.status==="unavailable"?" soon":""));
  wrap.title=c.label+(on ? ": conectado"
                         : (c.status==="unavailable" ? ": todavía no disponible — aún no hemos construido este conector"
                                                     : ": sin conectar"));
  if(spec){
    wrap.style.color=spec.color;
    const svg=document.createElementNS(SVG_NS_AG,"svg");
    svg.setAttribute("viewBox","0 0 24 24"); svg.setAttribute("width","15"); svg.setAttribute("height","15");
    svg.setAttribute("aria-hidden","true");
    const path=document.createElementNS(SVG_NS_AG,"path");
    path.setAttribute("d",spec.path); path.setAttribute("fill","currentColor");
    svg.appendChild(path); wrap.appendChild(svg);
  } else { wrap.appendChild(document.createTextNode((c.label||"?")[0])); }
  return wrap;
}

// DOM builder — ALL data-derived text goes in via textContent, never innerHTML. `data` here is brain-pushable
// (via [[push:agenda]]) i.e. UNTRUSTED, so string interpolation into HTML would be an XSS sink (audit SEC-1).
function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=String(text); return e; }

// Compact WEEK overview: one clickable row per day with its meetings, jumps to that day's tab.
function renderWeek(el, days, todayIdx){
  const wrap=el2("div","agweek");
  days.forEach((d,i)=>{
    const plan=d.plan||{}, blocks=(plan.blocks||[]);
    const row=el2("div","agwday"+(i===todayIdx?" today":"")); row.dataset.sel=String(i);
    const wh=el2("div","agwh");
    wh.append(el2("b",null,d.label), el2("span","agwd",d.date||""),
      el2("span","agct",plan.summary||`${blocks.length} bloques`));
    row.appendChild(wh);
    const mrow=el2("div","agwmeet");
    const meets=blocks.filter(b=>b.kind==="meeting");
    if(meets.length){ meets.forEach(m=>mrow.appendChild(el2("span","agwpill",`${m.start} ${m.label!=null?m.label:""}`))); }
    else { mrow.appendChild(el2("span","warn","sin citas")); }
    row.appendChild(mrow);
    wrap.appendChild(row);
  });
  el.appendChild(wrap);
}

const _MONTHS=["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
const _DOW=["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"];
const _pad=n=>String(n).padStart(2,"0");

// Full MONTH view: calendar with meetings at a glance. Previous/next month navigation stays client-side because
// all dated meetings already arrive in `data.meetings`, without another request. A day inside the horizon
// (Today..+6) is clickable and jumps to its tab (data-sel -> the generic handler re-renders).
function renderMonth(el, data, ctx, days){
  const wrap=el2("div","agmonth");
  const [ty,tm]=(data.date||"").split("-").map(Number);
  const off=el._agMoff||0;
  const disp=new Date((ty||new Date().getFullYear()),(tm?tm-1:new Date().getMonth())+off,1);
  const dy=disp.getFullYear(), dm=disp.getMonth();            // dm: 0-based

  const nav=el2("div","agmnav");
  const prev=el2("button",null,"‹"); const next=el2("button",null,"›");
  prev.onclick=()=>{el._agMoff=off-1;render(el,data,ctx);};
  next.onclick=()=>{el._agMoff=off+1;render(el,data,ctx);};
  nav.append(prev, el2("b",null,`${_MONTHS[dm]} ${dy}`), next);
  wrap.appendChild(nav);

  // Meetings by date (YYYY-MM-DD), sorted by time.
  const byDate={};
  (data.meetings||[]).forEach(m=>{ if(m&&m.date){ (byDate[m.date]=byDate[m.date]||[]).push(m); } });
  Object.values(byDate).forEach(a=>a.sort((x,y)=>String(x.startTime||"").localeCompare(String(y.startTime||""))));

  const grid=el2("div","aggrid");
  _DOW.forEach(d=>grid.appendChild(el2("div","agdow",d)));
  const lead=(new Date(dy,dm,1).getDay()+6)%7;               // getDay Sunday=0 -> Monday=0
  const nDays=new Date(dy,dm+1,0).getDate();
  for(let i=0;i<lead;i++) grid.appendChild(el2("div","agcell agpad"));
  for(let dn=1;dn<=nDays;dn++){
    const dateStr=`${dy}-${_pad(dm+1)}-${_pad(dn)}`;
    const evs=byDate[dateStr]||[];
    const cell=el2("div","agcell"+(dateStr===data.date?" today":""));
    cell.appendChild(el2("div","agdn",String(dn)));
    evs.slice(0,2).forEach(m=>cell.appendChild(
      el2("div","agev",`${m.startTime?m.startTime+" ":""}${m.title!=null?m.title:""}`)));
    if(evs.length>2) cell.appendChild(el2("div","agmore",`+${evs.length-2} más`));
    const hi=days.findIndex(d=>d.date===dateStr);            // in the horizon -> clickable, jumps to its day
    if(hi>=0){ cell.classList.add("aghas"); cell.dataset.sel=String(hi); }
    grid.appendChild(cell);
  }
  wrap.appendChild(grid);
  el.appendChild(wrap);
}

export function render(el, data, ctx){
  injectStyles();
  if(el._timer){clearInterval(el._timer);el._timer=null;}

  // Time horizon: precomputed days (today + upcoming). Compatibility: if `days` is missing, wrap today's plan.
  const days = (data.days&&data.days.length) ? data.days
    : [{date:data.date, label:"Hoy", weekday:"", plan:data.plan||{}}];
  const todayIdx = data.todayIndex||0;
  // A VIEW PUSHED FROM VOICE (`show_day`, V2-540). Applied only when its token MOVES, so a plain data refresh
  // never yanks the day the operator is reading out from under him — but asking twice for the same day still
  // lands, because the token is a counter and not the day itself.
  const pushed = data.view;
  if(pushed && pushed.n !== el._agViewN){
    el._agViewN = pushed.n;
    const want = pushed.sel;
    if(want==="week" || want==="month"){ el._agSel = want; }
    else {
      const hi = days.findIndex(d=>d.date===want);
      if(hi>=0){ el._agSel = hi; }
      else {
        // Outside the horizon (today..+6) there is no tab to select, and silently landing on today would be
        // the same lie this action exists to kill. The MONTH view can reach any date, so point it at that month.
        const [wy,wm] = String(want||"").split("-").map(Number);
        const [ty,tm] = String(data.date||"").split("-").map(Number);
        if(wy && wm && ty && tm){ el._agMoff = (wy-ty)*12 + (wm-tm); el._agSel = "month"; }
      }
    }
  }

  let sel = el._agSel;
  if(sel==null || (typeof sel==="number" && sel>=days.length)) sel = todayIdx;
  el._agSel = sel;
  const onWeek = sel==="week";
  const onMonth = sel==="month";
  const day = (onWeek||onMonth) ? null : days[sel];
  const isToday = !onWeek && !onMonth && sel===todayIdx;
  let active=null;

  el.className="hb-agenda";
  el.textContent="";                                          // reset (no innerHTML)

  const hd=el2("div","hd"); hd.append(el2("b",null,"Agenda"),
    el2("span","warn",onWeek?"Vista semana":(onMonth?"Vista mes":(day.date||""))),
    el2("span","now",isToday?(data.now||""):""));
  // The calendar connectors, at a glance and always visible — the same reading the messaging widget gives for
  // its channels (V2-521). None is linked today because none is BUILT; saying so out loud is deliberate.
  const cals=(data.calendars||[]);
  if(cals.length){
    const strip=el2("div","cals");
    cals.forEach(c=>{ const ic=calIcon(c); ic.style.cursor="pointer";
      ic.onclick=()=>{ el._agCalNote = (el._agCalNote===c.id ? null : c.id); render(el,data,ctx); };
      strip.appendChild(ic); });
    hd.appendChild(strip);
  }
  el.appendChild(hd);
  if(el._agCalNote){
    const c=cals.find(x=>x.id===el._agCalNote);
    if(c) el.appendChild(el2("div","calnote", c.status==="connected" ? c.label+": conectado."
      : (c.status==="unavailable"
         ? c.label+": todavía no está construido. Mientras tanto la agenda es la del propio Zaelar — lo que le dictes vive aquí, no en ese calendario."
         : c.label+": construido pero sin enlazar. Conéctalo desde Configuración › Conectores.")));
  }

  // Tabs: one day per tab plus Week view; switching stays client-side without another request.
  const tabs=el2("div","agtabs");
  days.forEach((d,i)=>{ const t=el2("button","agtab"+(sel===i?" on":""),d.label); t.dataset.sel=String(i); tabs.appendChild(t); });
  const wkTab=el2("button","agtab"+(onWeek?" on":""),"Semana"); wkTab.dataset.sel="week"; tabs.appendChild(wkTab);
  const moTab=el2("button","agtab"+(onMonth?" on":""),"Mes"); moTab.dataset.sel="month"; tabs.appendChild(moTab);
  el.appendChild(tabs);

  if(onWeek){
    renderWeek(el, days, todayIdx);
  } else if(onMonth){
    renderMonth(el, data, ctx, days);
  } else {
    const plan=day.plan||{};
    active = isToday ? data.active : null;

    const focus=el2("div","focus");
    (plan.focus||[]).forEach(f=>{ const c=el2("span","chip","🎯 "+(f.label!=null?f.label:""));
      if(f.objective!=null) c.setAttribute("title",String(f.objective)); focus.appendChild(c); });
    el.appendChild(focus);

    const cols=el2("div","cols");
    const tl=el2("div","tl");
    const blocks=(plan.blocks||[]);
    if(blocks.length){ blocks.forEach(b=>{
      const on = active && b.start===active.start && b.label===active.label;
      const blk=el2("div","blk"+(on?" act":""));
      blk.appendChild(el2("span","t",`${b.start}–${b.end}`));
      const bar=el2("span","bar"); bar.style.background=KIND[b.kind]||"var(--hb-neutral,#c2ccda)"; blk.appendChild(bar);  // KIND map = fixed palette, safe
      blk.appendChild(el2("span","lb",b.label!=null?b.label:""));
      tl.appendChild(blk);
    }); } else { tl.appendChild(el2("div","warn","Sin bloques: revisa tu jornada o tus tareas.")); }
    cols.appendChild(tl);

    const card=el2("div","now-card");
    if(isToday){
      const nowBox=el2("div"); nowBox.append(el2("div","k","Ahora"), el2("div","task",active?active.label:"—")); card.appendChild(nowBox);
      card.appendChild(el2("div","count",active?fmt(active.remaining_min||0):"—")).id="hb-count";

      const taskId = active && active.taskId;
      if(taskId){ const acts=el2("div","acts");
        [["done","✓ Hecha","done"],["not_now","No me apetece"],["snooze","Posponer"],["drop","Quitar tarea"]]
          .forEach(([a,label,extra])=>{ const b=el2("button",extra||null,label); b.dataset.a=a; b.dataset.tid=taskId;
            if(active.projectId)b.dataset.pid=active.projectId; acts.appendChild(b); });
        card.appendChild(acts);
      } else { card.appendChild(el2("div","warn","Ahora mismo no hay tarea activa de foco.")); }
    } else {
      const box=el2("div"); box.append(el2("div","k",day.label), el2("div","task",plan.summary||"Día planificado")); card.appendChild(box);
    }

    ((isToday?data.coaching:plan.coaching)||[]).forEach(c=>card.appendChild(el2("div","nudge","🧭 "+c)));
    ((isToday?data.warnings:plan.warnings)||[]).forEach(w=>card.appendChild(el2("div","warn","⚠ "+w)));

    const replan=el2("button","replan","↻ Replanificar"); replan.dataset.a="replan";
    card.appendChild(replan);
    cols.appendChild(card);
    el.appendChild(cols);
  }

  // Live countdown for the active block (today only).
  if(active){ let rem=(active.remaining_min||0)*60;
    el._timer=setInterval(()=>{rem-=1;const c=el.querySelector("#hb-count");if(c)c.textContent=fmt(rem/60);
      if(rem<=0)clearInterval(el._timer);},1000); }

  // Tabs / week rows: re-render from the same already-fetched data, without network.
  el.querySelectorAll("[data-sel]").forEach(btn=>btn.onclick=()=>{
    const v=btn.dataset.sel; el._agSel=(v==="week"||v==="month")?v:Number(v); render(el,data,ctx);
  });

  // actions → host applies + re-renders
  el.querySelectorAll("[data-a]").forEach(btn=>btn.onclick=async()=>{
    const p={}; if(btn.dataset.tid)p.taskId=btn.dataset.tid; if(btn.dataset.pid)p.projectId=btn.dataset.pid;
    const nd=await ctx.action(btn.dataset.a,p);
    if(nd)render(el,nd,ctx);
  });
}
