// Agenda widget — what every part shares: i18n seam, date helpers, DOM builders, icons, the event model.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().

export const SVG_NS_AG = "http://www.w3.org/2000/svg";

// Event palette. HUE says WHAT KIND of thing it is; the INTENSITY (below) says how settled it is. Both are
// derived from stored data — the category the operator dictated, or the planner's own block kind — never from
// sniffing the title, which would be guessing intent (V2-095).
export const HUES = {
  meeting:  "#7C6BFF",   // an appointment with the world
  work:     "#3D6FE0",
  deep:     "#3D6FE0",
  admin:    "#16B8A6",
  health:   "#E5484D",
  travel:   "#0EA5E9",
  social:   "#EC4899",
  personal: "#22A06B",
  exercise: "#E8973A",
  break:    "#8B98AC",
  buffer:   "#8B98AC",
  // V2-728 — work the SYSTEM does at a moment, not an appointment the operator keeps. Its own hue because
  // it is its own kind of thing: nobody is meeting anybody, and colouring it like a meeting would put a
  // commitment on his calendar that he never made.
  system:   "#9A6BFF",
};
// Dictated category → hue key. Spanish and English, because the category is PRODUCT DATA the operator speaks.
export const CATEGORY_HUE = {
  trabajo:"work", work:"work", oficina:"work", reunion:"meeting", meeting:"meeting",
  salud:"health", health:"health", medico:"health", doctor:"health", dentista:"health",
  viaje:"travel", travel:"travel", vuelo:"travel", trip:"travel",
  social:"social", amigos:"social", family:"social", familia:"social", cumpleanos:"social", birthday:"social",
  personal:"personal", casa:"personal", home:"personal",
  deporte:"exercise", gym:"exercise", exercise:"exercise", sport:"exercise",
};

// ── i18n seam (V2-613): `ctx.t` for our own chrome, `ctx.lang` for locale SHAPE (Intl) ────────────────
export const I18N = {T: null, LANG: "en"};   // set by render() from ctx
export function tt(key, params, fb){
  try{
    if(I18N.T){ const s=I18N.T("widgets.agenda."+key, params); if(s && s!=="widgets.agenda."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}
// V2-769 — the rule of a repeating appointment, in his language: weekday names come from Intl, never a table.
export function repeatLabel(r){
  if(!r) return "";
  const names = (r.days||[]).map(d=>fmtDate(new Date(2024,0,1+Number(d)), {weekday:"long"}, String(d)));
  let s = r.freq === "daily" ? tt("repeat_daily", null, "Se repite cada día")
        : r.freq === "monthly" ? tt("repeat_monthly", null, "Se repite cada mes")
        : tt("repeat_weekly", {days: names.join(", ")}, "Se repite cada semana: {days}");
  if(r.until){
    const u = parseYmd(r.until);
    s += " · " + tt("repeat_until", {until: u ? fmtDate(u, {day:"numeric", month:"long", year:"numeric"}, r.until)
                                               : r.until}, "hasta el {until}");
  }
  return s;
}
export function intl(opts){ try{ return new Intl.DateTimeFormat(I18N.LANG, opts); }catch(_){ return null; } }
export function fmtDate(d, opts, fb){ const f=intl(opts); return f ? f.format(d) : fb; }

// ── date helpers (local time, no libraries) ───────────────────────────────────────────────────────────
// Optional browser surface — a widget must render (and a headless DOM stub must be able to drive it) even
// where these do not exist; neither carries behaviour, only polish.
export function raf(fn){ try{ if(typeof requestAnimationFrame === "function") requestAnimationFrame(fn); else fn(); }
  catch(_){} }

export const _pad = n => String(n).padStart(2,"0");
export function ymd(d){ return `${d.getFullYear()}-${_pad(d.getMonth()+1)}-${_pad(d.getDate())}`; }
export function parseYmd(s){
  const p = String(s||"").split("-").map(Number);
  return (p[0] && p[1] && p[2]) ? new Date(p[0], p[1]-1, p[2]) : new Date();
}
export function addDays(d, n){ const x = new Date(d.getTime()); x.setDate(x.getDate()+n); return x; }
export function startOfWeek(d){ const x=new Date(d.getTime()); x.setDate(x.getDate()-((x.getDay()+6)%7)); return x; }  // Monday
export function mins(hhmm){ const p=String(hhmm||"").split(":"); const h=Number(p[0]), m=Number(p[1]);
  return (isFinite(h)?h:0)*60 + (isFinite(m)?m:0); }
export function hhmm(m){ return `${_pad(Math.floor(m/60)%24)}:${_pad(Math.round(m)%60)}`; }
export function fmtCount(min){ const m=Math.max(0,Math.round(min));
  return `${_pad(Math.floor(m/60))}:${_pad(m%60)}`; }

// ── DOM builder — data-derived text ALWAYS via textContent (data is brain-pushable, i.e. UNTRUSTED) ───
export function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=String(text); return e; }
export function svgEl(paths, opts){
  const svg=document.createElementNS(SVG_NS_AG,"svg");
  svg.setAttribute("viewBox","0 0 24 24"); svg.setAttribute("aria-hidden","true");
  svg.setAttribute("fill", (opts&&opts.fill) || "none");
  if(!(opts&&opts.fill)){ svg.setAttribute("stroke","currentColor"); svg.setAttribute("stroke-width","2");
    svg.setAttribute("stroke-linecap","round"); svg.setAttribute("stroke-linejoin","round"); }
  else { svg.setAttribute("fill","currentColor"); }
  (Array.isArray(paths)?paths:[paths]).forEach(d=>{
    const p=document.createElementNS(SVG_NS_AG,"path"); p.setAttribute("d",d); svg.appendChild(p);
  });
  return svg;
}
export const ICO_CAL   = ["M8 2v4","M16 2v4","M3 10h18","M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"];
export const ICO_PREV  = "M15 18l-6-6 6-6";
export const ICO_NEXT  = "M9 18l6-6-6-6";
export const ICO_BELL  = ["M18 8a6 6 0 0 0-12 0c0 7-3 8-3 8h18s-3-1-3-8","M13.7 21a2 2 0 0 1-3.4 0"];
export const ICO_USERS = ["M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2","M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
                   "M23 21v-2a4 4 0 0 0-3-3.87","M16 3.13a4 4 0 0 1 0 7.75"];
export const ICO_PIN   = ["M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0","M12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5"];
export const ICO_NOTE  = ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z","M14 2v6h6","M8 13h8","M8 17h5"];
export const ICO_CHECK = "M20 6L9 17l-5-5";
export const ICO_CLOCK = ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z","M12 6v6l4 2"];
export const ICO_PLUG  = ["M9 2v6","M15 2v6","M6 8h12v3a6 6 0 0 1-12 0z","M12 17v5"];
export const ICO_CAM   = ["M23 7l-7 5 7 5V7z","M14 5H3a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2z"];
export const ICO_HOST  = ["M20 21v-2a4 4 0 0 0-3-3.87","M4 21v-2a4 4 0 0 1 3-3.87",
                   "M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8"];

// V2-697 — what each guest answered, as a mark instead of a word: a roster of six people is read at a glance
// and never as six sentences. `needsAction` and an answer Google did not report both render as the same open
// circle on purpose — «has not answered» and «we were not told» are equally «unknown» to the operator.
export const RSVP_MARK = {accepted: "✓", declined: "✗", tentative: "?"};

// The connector refuses a non-http(s) join link at the boundary; this refuses it again at the SINK, because a
// row stored before that guard existed is still on disk and this is the line that becomes an `href`.
export function safeHttpUrl(u){
  const s = String(u || "").trim();
  return /^https?:\/\//i.test(s) ? s : "";
}

// CALENDAR CONNECTORS (V2-540). Official simple-icons outlines (CC0), inline so the widget stays
// self-contained with no CDN. CalDAV is a PROTOCOL, not a brand, so it wears a calendar glyph: painting a
// Microsoft logo on it would be a lie for a Fastmail account.
export const CAL_SVG = {
  google: {color:"#4285F4", path:"M18.316 5.684H24v12.632h-5.684V5.684zM5.684 24h12.632v-5.684H5.684V24zM18.316 5.684V0H1.895A1.894 1.894 0 0 0 0 1.895v16.421h5.684V5.684h12.632zm-7.207 6.25v-.065c.272-.144.5-.349.687-.617s.279-.595.279-.982c0-.379-.099-.72-.3-1.025a2.05 2.05 0 0 0-.832-.714 2.703 2.703 0 0 0-1.197-.257c-.6 0-1.094.156-1.481.467-.386.311-.65.671-.793 1.078l1.085.452c.086-.249.224-.461.413-.633.189-.172.445-.257.767-.257.33 0 .602.088.816.264a.86.86 0 0 1 .322.703c0 .33-.12.589-.36.778-.24.19-.535.284-.886.284h-.567v1.085h.633c.407 0 .748.109 1.02.327.272.218.407.499.407.843 0 .336-.129.614-.387.832s-.565.327-.924.327c-.351 0-.651-.103-.897-.311-.248-.208-.422-.502-.521-.881l-1.096.452c.178.616.505 1.082.977 1.401.472.319.984.478 1.538.477a2.84 2.84 0 0 0 1.293-.291c.382-.193.684-.458.902-.794.218-.336.327-.72.327-1.149 0-.429-.115-.797-.344-1.105a2.067 2.067 0 0 0-.881-.689zm2.093-1.931l.602.913L15 10.045v5.744h1.187V8.446h-.827l-2.158 1.557zM22.105 0h-3.289v5.184H24V1.895A1.894 1.894 0 0 0 22.105 0zm-3.289 23.5l4.684-4.684h-4.684V23.5zM0 22.105C0 23.152.848 24 1.895 24h3.289v-5.184H0v3.289z"},
  icloud: {color:"#3693F3", path:"M13.762 4.29a6.51 6.51 0 0 0-5.669 3.332 3.571 3.571 0 0 0-1.558-.36 3.571 3.571 0 0 0-3.516 3A4.918 4.918 0 0 0 0 14.796a4.918 4.918 0 0 0 4.92 4.914 4.93 4.93 0 0 0 .617-.045h14.42c2.305-.272 4.041-2.258 4.043-4.589v-.009a4.594 4.594 0 0 0-3.727-4.508 6.51 6.51 0 0 0-6.511-6.27z"},
  caldav: {color:"var(--hb-muted,#6b7b92)", path:"M19 3h-1V1h-2v2H8V1H6v2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm0 18H5V9h14v12z"},
};

// ── the model: one shape for everything that can be drawn on a calendar ───────────────────────────────
// A MEETING is authoritative and comes from `data.meetings` (any date, all its detail). A planner BLOCK is
// the coach half — a task placed in a free gap — and only exists for the horizon (today..+6); its meeting
// blocks are dropped because the same appointment already arrived through `meetings` with more inside it.
export function hueOf(ev){
  const cat = String(ev.category||"").toLowerCase();
  const key = CATEGORY_HUE[cat] || (HUES[cat] ? cat : null) || ev.kind || "meeting";
  return HUES[key] || HUES.meeting;
}
export function eventsOf(data){
  const out = [];
  (data.meetings||[]).forEach((m,i)=>{
    if(!m || !m.date) return;
    const allDay = !!m.allDay;
    const start = allDay ? 0 : mins(m.startTime);
    let end = allDay ? 24*60 : mins(m.endTime||"");
    if(!allDay && end <= start) end = start + 60;
    out.push({key:"m"+i, kind:"meeting", date:String(m.date).slice(0,10), allDay,
      start, end, title:m.title!=null?String(m.title):"", notes:m.notes||"", location:m.location||"",
      attendees:Array.isArray(m.attendees)?m.attendees:[], status:m.status||"confirmed",
      category:m.category||"", remindAt:m.remindAt||"", meeting:true,
      // V2-697 — what makes an appointment somebody ELSE convened readable: where you join, who invited you,
      // what each guest answered, and what YOU answered. The connector has written these since the first
      // import; nothing copied them here, so the detail card could not show what Google plainly knew.
      guests:Array.isArray(m.guests)?m.guests:[], organizer:m.organizer||"",
      myRsvp:m.myRsvp||"", meetLink:m.meetLink||"", htmlLink:m.htmlLink||"", source:m.source||"",
      // V2-769 — a repeating appointment arrives as its days; each one knows the rule it belongs to.
      repeat:(m.repeat && typeof m.repeat === "object") ? m.repeat : null});
  });
  // V2-728 — the SYSTEM's own timed work, read from the task table (`data.systemTasks`, never copied into
  // `meetings`). One event at the next moment it will happen: a recurring job has no single date, and its
  // next run is the one instant a calendar can place without inventing the rest.
  (data.systemTasks||[]).forEach((s,i)=>{
    if(!s || !s.date) return;
    const start = mins(s.startTime||"");
    out.push({key:"s"+i, kind:"system", date:String(s.date).slice(0,10), allDay:false,
      start, end:start+30, title:s.title!=null?String(s.title):"", notes:s.every||"", location:"",
      attendees:[], status:"planned", category:"", remindAt:"", system:true,
      recurring:!!s.recurring, taskId:s.id||""});
  });
  (data.days||[]).forEach(d=>{
    ((d.plan||{}).blocks||[]).forEach((b,i)=>{
      if(b.kind === "meeting") return;                 // already here, richer, from `meetings`
      out.push({key:`b${d.date}-${i}`, kind:b.kind||"admin", date:d.date, allDay:false,
        start:mins(b.start), end:Math.max(mins(b.start)+15, mins(b.end)), title:b.label!=null?String(b.label):"",
        notes:b.why||"", location:"", attendees:[], status:"planned", category:"",
        remindAt:"", planned:true, taskId:b.taskId||"", projectId:b.projectId||""});
    });
  });
  return out;
}
export function eventsOn(all, dateStr){
  return all.filter(e=>e.date===dateStr).sort((a,b)=>a.start-b.start || a.end-b.end);
}


// ── one event chip, in the time grid ──────────────────────────────────────────────────────────────────
export function badges(ev){
  const box = el2("span","agbadges");
  if(ev.remindAt){
    const b=el2("span","agbadge"); b.title=tt("has_reminder",{at:ev.remindAt},"Aviso programado: {at}");
    b.appendChild(svgEl(ICO_BELL)); box.appendChild(b);
  }
  const n = (ev.attendees||[]).length;
  if(n){
    const b=el2("span","agbadge"); b.appendChild(svgEl(ICO_USERS)); b.appendChild(el2("span",null,String(n)));
    b.title=tt("n_people",{n},"{n} personas"); box.appendChild(b);
  }
  return box;
}
export function chipClasses(ev){
  if(ev.system) return "agev system";
  return "agev" + (ev.planned ? " planned" : (ev.status==="pending" ? " pending" : ""));
}
export function timeLabel(ev){
  if(ev.allDay) return tt("all_day", null, "Todo el día");
  return `${hhmm(ev.start)}–${hhmm(ev.end)}`;
}

// ── the grid (day + week share it) ────────────────────────────────────────────────────────────────────
export const HOUR_PX = 46, GUTTER = 46;

export function hourRange(evs){
  let lo = 8*60, hi = 20*60;
  evs.forEach(e=>{ if(e.allDay) return; lo = Math.min(lo, e.start); hi = Math.max(hi, e.end); });
  lo = Math.max(0, Math.floor(lo/60)*60 - 60);
  hi = Math.min(24*60, Math.ceil(hi/60)*60 + 60);
  if(hi - lo < 8*60) hi = Math.min(24*60, lo + 8*60);
  return [lo, hi];
}
