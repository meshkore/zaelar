// Agenda widget — client render module (lazy-loaded by the canvas host). Contract: render(el, data, ctx).
// data = GET /widgets/agenda/data ; ctx.action(name,payload) -> new data (re-renders) ; ctx.close().
// Self-contained: scoped styles, live countdown, coach actions. The render is portable (plain DOM).
//
// V2-643 — a REAL calendar, in the shapes everybody already knows (the operator's spec: «tiene que parecerse a
// Google Calendar o a la agenda de Apple»): a toolbar with ‹ Hoy ›, the four classic views (Día · Semana · Mes ·
// Lista), a WEEK laid out as seven columns over an hour grid with the events inside each column, chips coloured
// by category and shaded by whether the other side has CONFIRMED, and badges for the reminder bell and how many
// people are coming. The card FILLS its frame and the grid scrolls inside it, so nothing is ever clipped.

import { CSS } from "./js/style.js";
import { I18N, tt, fmtDate, raf, ymd, parseYmd, addDays, startOfWeek, mins, fmtCount, el2, svgEl, ICO_CAL,
  ICO_CHECK, ICO_PREV, ICO_NEXT, ICO_PLUG, eventsOf, eventsOn, HOUR_PX, hourRange } from "./js/shared.js";
import { renderGrid, renderMonth } from "./js/calendar.js";
import { renderList, renderTasks } from "./js/list.js";
import { renderAdd, renderDetail } from "./js/detail.js";
import { renderProviderIcons, renderDefaultCalendar, renderProposals } from "./js/bands.js";

function injectStyles(){
  const prev = document.getElementById("hb-agenda-css");
  if(prev && (prev.dataset||{}).v === "744") return;   // dataset is optional on a foreign node
  if(prev) prev.remove();                      // an older build's sheet would fight this one, silently
  const s=document.createElement("style"); s.id="hb-agenda-css"; s.dataset.v="744"; s.textContent=CSS; document.head.appendChild(s);
}
// ── the render ────────────────────────────────────────────────────────────────────────────────────────
export function render(el, data, ctx){
  injectStyles();
  if(el._timer){ clearInterval(el._timer); el._timer=null; }
  I18N.T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  I18N.LANG = (ctx && ctx.lang) || "en";

  const today = data.date || ymd(new Date());
  // V2-744 — `sec` is WHICH OF THE TWO THINGS this card is showing (the calendar or his task lists), and
  // it is a different axis from `view` (day/week/month/list), which is a lens over the calendar alone.
  // `tl` is the list being read; `tlN` is the push counter of the last voice order that moved it.
  if(!el._ag) el._ag = {view:"week", anchor:today, sel:null, confirmDel:false, viewN:null, add:null,
                        sec:"agenda", tl:"", tlN:null, tlNew:false, tlEdit:false, tlItem:"", tlAsk:""};
  const S = el._ag;

  // A VIEW PUSHED FROM VOICE (`show_day`). Applied only when its token MOVES, so a plain refresh never
  // yanks what the operator is reading — but asking twice for the same day still lands, because the token
  // is a counter and not the day itself.
  const pushed = data.view;
  if(pushed && pushed.n !== S.viewN && pushed.close){
    // V2-770 — «cierra la ficha»: the detail card goes, and nothing else he is looking at moves.
    S.viewN = pushed.n; S.sel = null; S.confirmDel = false;
  } else if(pushed && pushed.n !== S.viewN){
    S.viewN = pushed.n;
    const want = String(pushed.sel||"");
    // V2-770 — «ábreme la cita del dentista»: the detail card by voice. Opening keeps the lens he is using
    // and moves it to that day.
    if(pushed.open && /^\d{4}-\d{2}-\d{2}$/.test(want)){ S.anchor = want; if(S.view === "list") S.view = "day"; }
    else if(want==="week" || want==="month" || want==="list"){ S.view = want; S.anchor = today; }
    else if(/^\d{4}-\d{2}-\d{2}$/.test(want)){ S.view = "day"; S.anchor = want; }
    S.sel = null; S.confirmDel = false;
    S.openWant = pushed.open || null;
    // V2-744 — a pushed view leaves the TASKS section: «enséñame el jueves» answered while the card sits on
    // the shopping list would be a day nobody can see.
    S.sec = "agenda";
  }

  // THE TASKS SECTION, PUSHED FROM VOICE (V2-744, `show_tasks`). Same token rule as the day above: it lands
  // when the counter MOVES, so a refresh never drags him out of what he is reading, and asking twice for
  // the same list still works — the counter changes even when the list does not.
  const pushedT = (data.tasks || {}).view;
  if(pushedT && pushedT.n !== S.tlN){
    S.tlN = pushedT.n;
    S.sec = "tasks";
    if(pushedT.list) S.tl = String(pushedT.list);
    S.sel = null; S.tlEdit = false; S.tlItem = ""; S.tlAsk = "";
  }

  if(!S.anchor) S.anchor = today;

  const all = eventsOf(data);
  const anchor = parseYmd(S.anchor);
  const redraw = nd => render(el, (nd && typeof nd === "object" && nd.date) ? nd : data, ctx);

  el.className = "hb-agenda";
  el.textContent = "";                                   // reset (never innerHTML)

  // ── V2-744/V2-746 · SECTION selector — the card's SUBHEADER ────────────────────────────────────────
  // «Arriba del todo un selector que separe lo que es agenda de tareas». It sits above the calendar's own
  // toolbar because it chooses WHAT you are looking at: everything below belongs to whichever half is lit.
  //
  // V2-746 — it is a BAND now and not a floating pill: «quizás debería ser una línea de subheader más
  // consistente. Por si hay que crear algo más ahí». The band spans the card and closes on a rule, and it
  // carries a right-hand slot that the tasks half fills with its counts and the calendar leaves empty. The
  // slot is the point of the change: whatever goes there next does not need a second band invented for it.
  const sub = el2("div","agsub");
  const secs = el2("div","agsec");
  [["agenda", tt("sec_agenda", null, "Agenda")], ["tasks", tt("sec_tasks", null, "Tareas")]].forEach(([id,label])=>{
    const b = el2("button","agsecb" + (S.sec === id ? " on" : ""));
    b.appendChild(svgEl(id === "agenda" ? ICO_CAL : ICO_CHECK)); b.appendChild(el2("span", null, label));   // a phone shows the mark
    b.dataset.sec = id;
    b.onclick = ()=>{ S.sec = id; S.sel = null; S.tlAsk = ""; render(el, data, ctx); };
    secs.appendChild(b);
  });
  sub.appendChild(secs);
  el.appendChild(sub);

  if(S.sec === "tasks"){
    // The slot, filled with what the half is actually holding. Counts and not a title: the title is the
    // window's, and repeating it here would spend the one line of chrome on something already on screen.
    const _T0 = (data && data.tasks) || {};
    const _ls = Array.isArray(_T0.lists) ? _T0.lists : [];
    const _open = _ls.reduce((n,l)=> n + Math.max(0, (l.total|0) - (l.done|0)), 0);
    const meta = el2("div","agsub-meta");
    meta.dataset.meta = "tasks";
    const _b1 = el2("b", null, String(_ls.length));
    meta.appendChild(_b1);
    meta.appendChild(el2("span", null, _ls.length === 1 ? tt("tasks_list_one", null, "lista")
                                                        : tt("tasks_list_many", null, "listas")));
    meta.appendChild(el2("span", null, "·"));
    const _b2 = el2("b", null, String(_open));
    meta.appendChild(_b2);
    meta.appendChild(el2("span", null, _open === 1 ? tt("tasks_open_one", null, "pendiente")
                                                   : tt("tasks_open_many", null, "pendientes")));
    sub.appendChild(meta);

    const tbody = el2("div","agbody tasks");
    renderTasks(tbody, data, ctx, S, redraw);
    el.appendChild(tbody);
    return;                       // the calendar's toolbar, views and overlays belong to the other half
  }

  // ── the toolbar lives INSIDE the band (2026-10-28, the operator: all the chrome in two lines, the window's
  // bar and this one): ‹ Hoy › · the range · the views, then the slot with the sources and the plug.
  const bar = el2("div","agbar");
  let rangeTxt = "", dates = [];
  if(S.view === "week"){
    const s = startOfWeek(anchor);
    for(let i=0;i<7;i++) dates.push(ymd(addDays(s,i)));
    const e = addDays(s,6);
    rangeTxt = (s.getMonth()===e.getMonth())
      ? `${s.getDate()} – ${e.getDate()} ${fmtDate(e,{month:"long",year:"numeric"},"")}`
      : `${s.getDate()} ${fmtDate(s,{month:"short"},"")} – ${e.getDate()} ${fmtDate(e,{month:"short",year:"numeric"},"")}`;
  } else if(S.view === "day"){
    dates = [S.anchor];
    rangeTxt = fmtDate(anchor,{weekday:"long",day:"numeric",month:"long"}, S.anchor);
  } else if(S.view === "month"){
    rangeTxt = fmtDate(anchor,{month:"long",year:"numeric"}, S.anchor);
  } else {
    rangeTxt = tt("upcoming", null, "Próximamente");
  }
  const nav = el2("div","agnav");
  const step = (n) => {
    const a = parseYmd(S.anchor);
    S.anchor = ymd(S.view==="month" ? new Date(a.getFullYear(), a.getMonth()+n, 1)
                                    : addDays(a, n * (S.view==="week" ? 7 : 1)));
    S.sel = null; render(el, data, ctx);
  };
  const prev = el2("button"); prev.appendChild(svgEl(ICO_PREV));
  prev.title = tt("prev", null, "Anterior"); prev.dataset.nav = "prev"; prev.onclick = ()=>step(-1);
  const now = el2("button", null, tt("today", null, "Hoy")); now.dataset.nav = "today";
  now.onclick = ()=>{ S.anchor = today; S.sel = null; render(el, data, ctx); };
  const next = el2("button"); next.appendChild(svgEl(ICO_NEXT));
  next.title = tt("next", null, "Siguiente"); next.dataset.nav = "next"; next.onclick = ()=>step(1);
  if(S.view !== "list"){ nav.appendChild(prev); }
  nav.appendChild(now);
  if(S.view !== "list"){ nav.appendChild(next); }
  bar.appendChild(nav); bar.appendChild(el2("div","agrange", rangeTxt));

  // ── the views: four tabs, and the SAME four as a <select> for a narrow card (the stylesheet shows one
  // or the other by the card's width, so a 400px card keeps every view reachable without a scroll strip)
  const views = el2("div","agviews"); views.setAttribute("role","tablist");
  const VIEWS = [["day", tt("day", null, "Día")], ["week", tt("week", null, "Semana")],
                 ["month", tt("month", null, "Mes")], ["list", tt("list", null, "Lista")]];
  VIEWS.forEach(([id,label])=>{
    const t = el2("button","agtab" + (S.view===id ? " on" : ""), label);
    t.dataset.view = id;
    t.onclick = ()=>{ S.view = id; S.sel = null; render(el, data, ctx); };
    views.appendChild(t);
  });
  const vsel = document.createElement("select"); vsel.className = "agviewsel"; vsel.title = tt("view", null, "Vista");
  VIEWS.forEach(([id,label])=>{ const o = document.createElement("option"); o.value = id; o.textContent = label;
    o.selected = S.view === id; vsel.appendChild(o); });
  vsel.onchange = ()=>{ S.view = vsel.value; S.sel = null; render(el, data, ctx); }; views.appendChild(vsel); bar.appendChild(views); sub.appendChild(bar);
  const right = el2("div","agviewsright");
  const defCal = renderDefaultCalendar(data, ctx);
  if(defCal) right.appendChild(defCal);
  right.appendChild(renderProviderIcons(data.calendars || [], ctx));
  // V2-699's plug, kept: it is the card's door to ITS connector, which lives in ⚙ Conectores (2026-10-04).
  // An ICON, as the header standard says — the word travels in aria-label and the tooltip.
  const calBtn = el2("button","agcalbtn");
  calBtn.appendChild(svgEl(ICO_PLUG)); calBtn.setAttribute("aria-label", tt("connectors", null, "Conectores"));
  calBtn.title = tt("calendars_hint", null, "Qué calendarios están conectados");
  calBtn.onclick = ()=>ctx.openConnector("google");
  right.appendChild(calBtn);
  sub.appendChild(right);

  // ── proposals ──────────────────────────────────────────────────────────────────────────────────────
  // V2-697 — appointments somebody ELSE asked for. Above the calendar and visually apart from it, because
  // NONE of this is on his calendar yet: the whole point is that it is a question, not an entry.
  renderProposals(el, data, ctx, redraw);

  // ── body ───────────────────────────────────────────────────────────────────────────────────────────
  const body = el2("div","agbody");
  const pick = e => { S.sel = e.key; S.confirmDel = false; render(el, data, ctx); };
  const pickDay = ds => { S.view = "day"; S.anchor = ds; S.sel = null; render(el, data, ctx); };
  const pickSlot = (ds, m) => { S.add = {date: ds, start: m, title: ""}; S.sel = null; render(el, data, ctx); };
  // The way OUT of a crowded slot, and it always goes somewhere wider: the week sends you to the day, the
  // day to the list, where a row is a row and nothing is hidden behind a count.
  const overflow = ds => {
    if(S.view === "day"){ S.view = "list"; } else { S.view = "day"; S.anchor = ds; }
    S.sel = null; render(el, data, ctx);
  };

  let active = null;
  if(S.view === "week"){
    renderGrid(body, dates, all, data, pick, pickDay, pickSlot, overflow);
  } else if(S.view === "month"){
    renderMonth(body, S.anchor, all, data, pick, pickDay);
  } else if(S.view === "list"){
    renderList(body, today, all, data, pick);
  } else {
    // DAY = the hour grid plus the coach rail this widget has always had (Now + countdown + task actions).
    const wrap = el2("div","agday-wrap");
    const gridBox = el2("div","agday-grid");
    renderGrid(gridBox, dates, all, data, pick, pickDay, pickSlot, overflow);
    wrap.appendChild(gridBox);

    const isToday = S.anchor === today;
    const dayPlan = (data.days||[]).find(d=>d.date===S.anchor);
    const plan = (dayPlan && dayPlan.plan) || (isToday ? (data.plan||{}) : {});
    active = isToday ? data.active : null;

    const side = el2("div","agside");
    const focus = (plan.focus||[]);
    if(focus.length){
      const chips = el2("div","agchips");
      focus.forEach(f=>{ const c=el2("span","agchip","🎯 " + (f.label!=null?f.label:""));
        if(f.objective!=null) c.setAttribute("title", String(f.objective)); chips.appendChild(c); });
      side.appendChild(chips);
    }
    const card = el2("div","agcard");
    if(isToday){
      card.appendChild(el2("div","agk", tt("now", null, "Ahora")));
      card.appendChild(el2("div","agtask", active ? active.label : "—"));
      const cnt = el2("div","agcount", active ? fmtCount(active.remaining_min||0) : "—");
      cnt.id = "hb-count"; card.appendChild(cnt);
      const taskId = active && active.taskId;
      if(taskId){
        const acts = el2("div","agacts");
        [["done","✓ "+tt("done", null, "Hecha"),"done"], ["not_now", tt("not_now", null, "No me apetece")],
         ["snooze", tt("snooze", null, "Posponer")], ["drop", tt("drop", null, "Quitar tarea")]]
          .forEach(([a,label,extra])=>{ const b=el2("button",extra||null,label); b.dataset.a=a; b.dataset.tid=taskId;
            if(active.projectId) b.dataset.pid=active.projectId; acts.appendChild(b); });
        card.appendChild(acts);
      } else {
        card.appendChild(el2("div","agwarn", tt("no_active", null, "Ahora mismo no hay tarea activa de foco.")));
      }
    } else {
      card.appendChild(el2("div","agk", fmtDate(anchor,{weekday:"long"}, S.anchor)));
      card.appendChild(el2("div","agtask", plan.summary || tt("planned_day", null, "Día planificado")));
    }
    side.appendChild(card);
    ((isToday ? data.coaching : plan.coaching)||[]).forEach(c=>side.appendChild(el2("div","agnudge","🧭 "+c)));
    ((isToday ? data.warnings : plan.warnings)||[]).forEach(w=>side.appendChild(el2("div","agwarn","⚠ "+w)));
    const replan = el2("button","agchip","↻ " + tt("replan", null, "Replanificar"));
    replan.dataset.a = "replan"; replan.style.cursor = "pointer"; side.appendChild(replan);
    wrap.appendChild(side);
    body.appendChild(wrap);
  }
  el.appendChild(body);

  // ── overlays ───────────────────────────────────────────────────────────────────────────────────────
  if(S.openWant){                                 // resolved here: event keys exist only once `all` is built
    const w = S.openWant; S.openWant = null;
    const ev = all.find(e=>e.meeting && e.date===w.date && e.title===w.title);
    if(ev) S.sel = ev.key;
  }
  if(S.sel){
    const ev = all.find(e=>e.key===S.sel);
    if(ev) renderDetail(el, ev, ctx, S, redraw); else S.sel = null;
  }
  if(S.add) renderAdd(el, ctx, S, redraw);
  // Live countdown for the active block (today only).
  if(active){
    let rem = (active.remaining_min||0)*60;
    el._timer = setInterval(()=>{ rem -= 1; const c = el.querySelector("#hb-count");
      if(c) c.textContent = fmtCount(rem/60); if(rem<=0) clearInterval(el._timer); }, 1000);
  }

  // Coach actions → host applies + re-renders.
  el.querySelectorAll("[data-a]").forEach(btn=>btn.onclick = async ()=>{
    const p = {}; if(btn.dataset.tid) p.taskId = btn.dataset.tid; if(btn.dataset.pid) p.projectId = btn.dataset.pid;
    const nd = await ctx.action(btn.dataset.a, p);
    if(nd) render(el, nd, ctx);
  });

  // Open the grid on the working hours instead of at midnight-ish, once per paint.
  if(S.view === "day" || S.view === "week"){
    const scroller = el.querySelector(".agday-grid") || el.querySelector(".agbody");
    if(scroller){
      const [lo] = hourRange(dates.flatMap(d=>eventsOn(all, d)));
      const target = Math.max(0, (mins(isFinite(mins(data.now))&&S.anchor===today ? data.now : "08:00") - lo - 60)/60*HOUR_PX);
      raf(()=>{ try{ scroller.scrollTop = target; }catch(_){} });
    }
  }
}
