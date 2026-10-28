// Agenda widget — the time grid (day + week) and the month — and the lane packing they share.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { tt, fmtDate, raf, ymd, parseYmd, addDays, startOfWeek, mins, hhmm, el2, hueOf, eventsOn, badges,
  chipClasses, timeLabel, HOUR_PX, GUTTER, hourRange } from "./shared.js";

// Side-by-side layout for events sharing a slot — what turns a list into a calendar. Overlapping events are
// grouped, then each takes 1/N of the column's width. Without it two 10:00 meetings hide one another.
export function layoutColumn(evs){
  const timed = evs.filter(e=>!e.allDay);
  const groups = []; let cur = [];
  let end = -1;
  timed.forEach(e=>{
    if(cur.length && e.start >= end){ groups.push(cur); cur = []; end = -1; }
    cur.push(e); end = Math.max(end, e.end);
  });
  if(cur.length) groups.push(cur);
  const placed = [];
  groups.forEach((g, gi)=>{
    const cols = [];                                    // greedy column packing inside the overlap group
    g.forEach(e=>{
      let ci = cols.findIndex(c => c[c.length-1].end <= e.start);
      if(ci < 0){ cols.push([e]); ci = cols.length-1; } else { cols[ci].push(e); }
      placed.push({ev:e, col:ci, g:gi});
    });
    const n = cols.length;
    placed.slice(-g.length).forEach(p=>{ p.of = n; });
  });
  return placed;
}

// How many events may sit side by side before the column stops being readable. Measured on the operator's
// own week: SIX appointments at 17:00 in a ~110px column is 18px each — not a truncated title, a coloured
// bar. «No se puede dejar así de mal.» Past the budget the last lane becomes a «+N» that opens the day.
//
// It is a BUDGET, not a constant, and that is the half a first attempt got wrong: with one number for every
// view, the «+N» in the week opened a day that still said «+N» — a dead end dressed as a way out. A day
// column is the whole card, so it holds what a seventh of it cannot, and the overflow always has somewhere
// wider to send you.
export function laneBudget(nDates){ return nDates > 1 ? 3 : 8; }

// Trim each overlap group to the lane budget and hand back what has to be drawn: the chips that fit, plus
// one overflow marker per group that had to hide something.
export function lanes(placed, budget){
  const byGroup = new Map();
  placed.forEach(p=>{ if(!byGroup.has(p.g)) byGroup.set(p.g, []); byGroup.get(p.g).push(p); });
  const shown = [], more = [];
  byGroup.forEach(items=>{
    const of = items[0] && items[0].of || 1;
    if(of <= budget){ items.forEach(p=>shown.push({...p, of})); return; }
    const keep = items.filter(p=>p.col < budget-1);
    const hid  = items.filter(p=>p.col >= budget-1);
    keep.forEach(p=>shown.push({...p, of: budget}));
    if(hid.length){
      more.push({col: budget-1, of: budget, n: hid.length,
                 start: Math.min(...hid.map(p=>p.ev.start)),
                 end: Math.max(...hid.map(p=>p.ev.end))});
    }
  });
  return {shown, more};
}

export function renderGrid(host, dates, all, data, onPick, onDayPick, onSlot, onOverflow){
  const today = data.date || ymd(new Date());
  const visible = [];
  dates.forEach(d=>{ eventsOn(all, d).forEach(e=>visible.push(e)); });
  const [lo, hi] = hourRange(visible);
  const cols = `${GUTTER}px repeat(${dates.length},minmax(0,1fr))`;

  const head = el2("div","aghead"); head.style.gridTemplateColumns = cols;
  head.appendChild(el2("div","agdh"));                  // gutter corner
  dates.forEach(d=>{
    const dt = parseYmd(d);
    const h = el2("div","agdh" + (d===today?" today":"") + (dates.length>1?" pick":""));
    h.appendChild(el2("div","agdw", fmtDate(dt,{weekday:"short"},"").replace(/\.$/,"")));
    h.appendChild(el2("div","agdn", String(dt.getDate())));
    if(dates.length>1){ h.onclick=()=>onDayPick(d); h.title=fmtDate(dt,{weekday:"long",day:"numeric",month:"long"},d); }
    head.appendChild(h);
  });
  host.appendChild(head);

  // ALL-DAY band — a row above the hours, exactly where every calendar puts it. A MULTI-DAY event is ONE bar
  // across the days it covers (2026-10-28), clipped at the band's edges with its title said once.
  const d0 = dates[0], dN = dates[dates.length-1];
  const spans = all.filter(e=>e.lastDay && e.date<=dN && e.lastDay>=d0);
  if(visible.some(e=>e.allDay) || spans.length){
    const band = el2("div","agallday"); band.style.gridTemplateColumns = cols;
    band.appendChild(el2("div","agalllb", tt("all_day_short", null, "Todo el día")));
    dates.forEach((d,i)=>{
      const cell = el2("div","agallcell"); cell.style.gridColumn = i+2; cell.style.paddingTop = (3 + spans.length*24)+"px";
      eventsOn(all, d).filter(e=>e.allDay && !e.lastDay).forEach(e=>{
        const chip = el2("div", chipClasses(e)+" allday");
        chip.style.setProperty("--evc", hueOf(e));
        chip.appendChild(el2("div","agevt", e.title));
        chip.onclick = ev => { ev.stopPropagation(); onPick(e); };
        cell.appendChild(chip);
      });
      band.appendChild(cell);
    });
    spans.forEach((e,lane)=>{
      const a = Math.max(0, dates.indexOf(e.date)), b = e.lastDay > dN ? dates.length-1 : dates.indexOf(e.lastDay);
      const bar = el2("div","agev allday agspan" + (e.date<d0?" cl":"") + (e.lastDay>dN?" cr":""));
      bar.style.gridColumn = `${a+2} / ${b+3}`; bar.style.marginTop = (3 + lane*24)+"px"; bar.style.setProperty("--evc", hueOf(e));
      bar.appendChild(el2("div","agevt", e.title)); bar.title = `${timeLabel(e)} · ${e.title}`;
      bar.onclick = ev => { ev.stopPropagation(); onPick(e); }; band.appendChild(bar);
    });
    host.appendChild(band);
  }

  const grid = el2("div","aggrid"); grid.style.gridTemplateColumns = cols;
  const height = (hi-lo)/60*HOUR_PX;
  const gut = el2("div","aghours"); gut.style.height = height+"px";
  for(let m=lo; m<=hi; m+=60){
    const lb = el2("div","aghour", hhmm(m)); lb.style.top = ((m-lo)/60*HOUR_PX)+"px"; gut.appendChild(lb);
  }
  grid.appendChild(gut);

  dates.forEach(d=>{
    const col = el2("div","agcol"); col.style.height = height+"px";
    for(let m=lo; m<=hi; m+=30){
      const line = el2("div","agline" + (m%60?" half":""));
      line.style.top = ((m-lo)/60*HOUR_PX)+"px"; col.appendChild(line);
    }
    // The empty half-hours, each one its own target. Drawn BEFORE the chips so an event keeps its click,
    // and each carries the minute it represents rather than reading it back out of a mouse coordinate.
    for(let m=lo; m<hi; m+=30){
      const slot = el2("div","agslot");
      slot.style.top = ((m-lo)/60*HOUR_PX)+"px";
      slot.style.height = (HOUR_PX/2 - 1)+"px";
      slot.title = tt("add_at", {at: hhmm(m)}, "Nueva cita a las {at}");
      slot.onclick = ev => { ev.stopPropagation(); onSlot(d, m); };
      col.appendChild(slot);
    }
    if(d===today && data.now){
      const nowM = mins(data.now);
      if(nowM>=lo && nowM<=hi){
        const n = el2("div","agnow"); n.style.top = ((nowM-lo)/60*HOUR_PX)+"px";
        n.title = tt("now", null, "Ahora"); col.appendChild(n);
      }
    }
    const packed = lanes(layoutColumn(eventsOn(all, d)), laneBudget(dates.length));
    packed.shown.forEach(p=>{
      const e = p.ev, of = p.of || 1;
      const h = Math.max(20, (e.end-e.start)/60*HOUR_PX - 2);
      // What the chip can HOLD decides what goes in it. Two lines need ~34px; one needs ~24. And a lane
      // narrower than a word holds initials, not a sentence — the class is what the stylesheet reads.
      const cls = chipClasses(e)
        + (h < 34 ? " tight" : "") + (h < 24 ? " tiny" : "") + (of >= 3 ? " narrow" : "");
      const chip = el2("div", cls);
      chip.style.setProperty("--evc", hueOf(e));
      chip.style.top = ((e.start-lo)/60*HOUR_PX)+"px";
      chip.style.height = h+"px";
      chip.style.left = (p.col*100/of)+"%";
      chip.style.width = `calc(${100/of}% - 3px)`;
      chip.appendChild(el2("div","agevt", e.title));
      const hr = el2("div","agevh", hhmm(e.start));
      hr.appendChild(badges(e)); chip.appendChild(hr);
      chip.title = `${timeLabel(e)} · ${e.title}`;
      chip.onclick = ev => { ev.stopPropagation(); onPick(e); };
      col.appendChild(chip);
    });
    packed.more.forEach(m=>{
      const chip = el2("div","agev more");
      chip.style.top = ((m.start-lo)/60*HOUR_PX)+"px";
      chip.style.height = Math.max(20, (m.end-m.start)/60*HOUR_PX - 2)+"px";
      chip.style.left = (m.col*100/m.of)+"%";
      chip.style.width = `calc(${100/m.of}% - 3px)`;
      chip.appendChild(el2("div","agevt", "+" + m.n));
      chip.title = tt("more_n", {n: m.n}, "{n} citas más — ábrelas en el día");
      chip.onclick = ev => { ev.stopPropagation(); onOverflow(d); };
      col.appendChild(chip);
    });
    grid.appendChild(col);
  });
  host.appendChild(grid);

  // The sticky all-day band has to sit exactly under the sticky header, whose height depends on the fonts.
  raf(()=>{ try{ host.style.setProperty("--aghead-h", head.offsetHeight+"px"); }catch(_){} });
  return {lo, hi, height};
}

// ── MONTH ─────────────────────────────────────────────────────────────────────────────────────────────
export function renderMonth(host, anchor, all, data, onPick, onDayPick){
  const today = data.date || ymd(new Date()), a = parseYmd(anchor);
  const first = new Date(a.getFullYear(), a.getMonth(), 1), start = startOfWeek(first);
  const dows = el2("div","agmdows"); for(let i=0;i<7;i++) dows.appendChild(el2("div","agmdow",
    fmtDate(addDays(start,i),{weekday:"short"},"").replace(/\.$/,""))); host.appendChild(dows);

  const grid = el2("div","agmgrid");
  const weeks = Math.ceil((((first.getDay()+6)%7) + new Date(a.getFullYear(), a.getMonth()+1, 0).getDate())/7);
  grid.style.gridTemplateRows = `repeat(${weeks},minmax(66px,1fr))`; grid.style.minHeight = (weeks*66)+"px";
  // A MULTI-DAY event is ONE bar per week it touches (2026-10-28), placed on the grid over its cells — every
  // cell is placed explicitly so the bars never shift them — with its title once and a cut edge where the
  // week breaks. The cells under it keep a spacer the height of the week's bar lanes.
  const spans = all.filter(e=>e.lastDay), di = s => Math.round((parseYmd(s) - start)/864e5), bars = [];
  for(let i=0;i<weeks*7;i++){
    const d = addDays(start, i), ds = ymd(d), w = Math.floor(i/7), w0 = ymd(addDays(start, w*7)), w1 = ymd(addDays(start, w*7+6));
    const lanes = spans.filter(e=>e.date<=w1 && e.lastDay>=w0);
    const cell = el2("div","agmcell" + (d.getMonth()!==a.getMonth()?" out":"") + (ds===today?" today":"")
                                     + (d.getDay()%6===0?" we":"") + (w===weeks-1?" last":""));
    cell.style.gridArea = `${w+1} / ${i%7+1}`;
    cell.appendChild(el2("div","agmn", String(d.getDate())));
    if(lanes.length){ const sp = el2("div","agmsp"); sp.style.height = (lanes.length*22)+"px"; cell.appendChild(sp); }
    if(i%7===0) lanes.forEach((e,lane)=>{
      const a1 = Math.max(0, di(e.date)-w*7), b1 = Math.min(6, di(e.lastDay)-w*7);
      const bar = el2("div","agmev allday agspan" + (e.date<w0?" cl":"") + (e.lastDay>w1?" cr":""));
      bar.style.gridArea = `${w+1} / ${a1+1} / auto / ${b1+2}`; bar.style.marginTop = (30 + lane*22)+"px";
      bar.style.setProperty("--evc", hueOf(e)); bar.appendChild(el2("span","agmt", e.title));
      bar.title = `${timeLabel(e)} · ${e.title}`; bar.onclick = ev => { ev.stopPropagation(); onPick(e); }; bars.push(bar);
    });
    const evs = eventsOn(all, ds).filter(e=>!e.lastDay);
    evs.forEach(e=>{
      const row = el2("div","agmev" + (e.status==="pending"?" pending":"") + (e.allDay?" allday":""));
      row.style.setProperty("--evc", hueOf(e));
      row.appendChild(el2("span","agmdot"));
      if(!e.allDay) row.appendChild(el2("span","agmh", hhmm(e.start)));
      row.appendChild(el2("span","agmt", e.title));
      row.title = `${timeLabel(e)} · ${e.title}`; row.onclick = ev => { ev.stopPropagation(); onPick(e); };
      cell.appendChild(row);
    });
    cell.appendChild(el2("div","agmore"));
    cell.onclick = ()=>onDayPick(ds); grid.appendChild(cell);
  }
  bars.forEach(b=>grid.appendChild(b));   // after every cell, so the cells' own nth-child rules hold
  host.appendChild(grid);
  // What a cell SHOWS is what its row can hold, measured — three chips in a tall card, one in a short one —
  // and the rest is a count, never a chip cut through its glyphs (the operator's rule from V2-693, here).
  // ~30px go to the day number, ~21px to each row; the last row of a full cell is the count itself.
  raf(()=>grid.querySelectorAll(".agmcell").forEach(c=>{
    const rows = c.querySelectorAll(".agmev"), more = c.querySelector(".agmore");
    const sp = c.querySelector(".agmsp"), n = Math.max(1, Math.floor((c.clientHeight-30-(sp ? sp.offsetHeight : 0))/21)), hide = rows.length > n ? rows.length-n+1 : 0;
    rows.forEach((r,i)=>{ r.style.display = i < rows.length-hide ? "" : "none"; });
    more.style.display = hide ? "" : "none"; more.textContent = hide ? tt("n_more",{n:hide},"+{n} más") : "";
  }));
}
