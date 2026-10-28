// Agenda widget — the strips above the calendar: provider icons, the default-calendar picker, the proposals band.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { tt, fmtDate, parseYmd, el2, svgEl, ICO_CAL, CAL_SVG } from "./shared.js";

// ── The PLATFORM ICONS in the subheader (V2-679 follow-up) — the messaging widget's own pattern: every
// provider visible at a glance, the ones we have not built dimmed and inert, the live one a door into its
// screen. Deliberately NOT the cramped 15px strip V2-643 removed: these are 26px targets with a tooltip each,
// sitting beside the Conectores button instead of competing with the range title. ───────────────────────────
export function renderProviderIcons(cals, ctx){
  const wrap = el2("div","agconnicons");
  (cals||[]).forEach(c=>{
    const live = c.id === "google";            // the only provider with a connector behind it today
    const on = c.status === "connected";
    const btn = el2("button","agconnicon" + (on?" on":"") + (live?"":" off"));
    const spec = CAL_SVG[c.id];
    if(spec){ btn.style.color = spec.color; btn.appendChild(svgEl(spec.path, {fill:true})); }
    else { btn.appendChild(svgEl(ICO_CAL)); }
    btn.title = (c.label || c.id) + " — " + (!live ? tt("cal_soon", null, "aún no disponible")
                                                   : on ? tt("cal_connected", null, "conectado")
                                                        : tt("cal_off", null, "sin conectar"));
    if(!live){ btn.disabled = true; }
    else btn.onclick = ()=>ctx.openConnector("google");   // the ⚙ Conectores section, the one door
    wrap.appendChild(btn);
  });
  return wrap;
}

// The calendar new appointments are written into, when Google has more than one. A calendar PREFERENCE,
// not a connection, so it stays on the card; connecting and disconnecting live in ⚙ Conectores.
export function renderDefaultCalendar(data, ctx){
  const gcals = data.googleCalendars || [];
  const on = (data.calendars||[]).some(c => c.id === "google" && c.status === "connected");
  if(!on || gcals.length < 2) return null;
  const sel = document.createElement("select"); sel.className = "agcaldefsel";
  sel.title = tt("cal_default_label", null, "Calendario donde crear las citas nuevas:");
  gcals.forEach(gc=>{
    const o = document.createElement("option"); o.value = gc.id; o.textContent = gc.summary || gc.id;
    o.selected = gc.id === data.defaultCalendarId; sel.appendChild(o);
  });
  sel.onchange = ()=>{ ctx.action("set_default_calendar", {calendarId: sel.value}); };
  return sel;
}
// V2-697 — the proposals band. Each row says WHO asked, WHEN, and what for, and offers exactly two answers.
// There is no «propose another time» by the operator's own scoping, and no auto-accept at all: the name on a
// proposal is a label he reads, never a credential — a cluster peer's handle is self-declared.
export function renderProposals(el, data, ctx, redraw){
  const rows = Array.isArray(data.proposals) ? data.proposals : [];
  if(!rows.length) return;
  const box = el2("div","agprops");
  for(const p of rows){
    const r = el2("div","agprop");
    const head = el2("div","agprophead");
    head.appendChild(el2("strong",null, tt("prop_asks",{who: p.party || "Alguien"}, "{who} te propone una cita")));
    r.appendChild(head);
    const d = parseYmd(String(p.date || ""));
    const when = d ? fmtDate(d,{weekday:"long",day:"numeric",month:"long"},String(p.date)) : String(p.date||"");
    const hh = p.startTime ? ` · ${p.startTime}${p.endTime ? "–" + p.endTime : ""}` : "";
    r.appendChild(el2("div","agpropwhen", when + hh));
    if(p.objective) r.appendChild(el2("div","agpropwhy", String(p.objective)));
    const acts = el2("div","agpropacts");
    const call = name => {
      Promise.resolve(ctx.action(name, {errand_id: p.errand_id})).then(nd => redraw(nd)).catch(()=>redraw());
    };
    const yes = el2("button","ok","✓ " + tt("prop_accept", null, "Aceptar"));
    yes.onclick = ()=>call("accept_proposal");
    const no = el2("button",null,"✗ " + tt("prop_decline", null, "Rechazar"));
    no.onclick = ()=>call("decline_proposal");
    acts.appendChild(yes); acts.appendChild(no);
    r.appendChild(acts);
    box.appendChild(r);
  }
  el.appendChild(box);
}
