// Agenda widget — the overlays inside the card: the new-appointment composer and an event's detail panel.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { tt, repeatLabel, fmtDate, raf, parseYmd, mins, hhmm, el2, svgEl, ICO_BELL, ICO_USERS, ICO_PIN,
  ICO_NOTE, ICO_CHECK, ICO_CLOCK, ICO_CAM, ICO_HOST, RSVP_MARK, safeHttpUrl, hueOf, timeLabel } from "./shared.js";

// ── DETAIL panel — what an event IS, and the few actions that are real ────────────────────────────────
// ── NEW APPOINTMENT, from a click on an empty half-hour (V2-693) ────────────────────────────────────────
// Until today the only way to put something in this calendar was to SAY it. His ask is the plain one every
// calendar answers: «asegúrate de que el widget permite clicar en algún punto para añadir un ítem». It sends
// `add_meeting` — a DECLARED data-op — and nothing else: a button that promises what the API cannot do is
// the failure this widget's own history is made of (V2-540).
export function renderAdd(root, ctx, state, redraw){
  const at = state.add || {};
  const veil = el2("div","agveil");
  const close = ()=>{ state.add = null; redraw(); };
  veil.onclick = e => { if(e.target===veil) close(); };
  const p = el2("div","agpanel agaddp");

  const head = el2("div","agphead");
  head.appendChild(el2("div","agpbar"));
  head.appendChild(el2("div","agptitle", tt("new_meeting", null, "Nueva cita")));
  const x = el2("button","agpx","×"); x.title = tt("close", null, "Cerrar"); x.onclick = close;
  head.appendChild(x); p.appendChild(head);

  const when = el2("div","agprow"); when.appendChild(svgEl(ICO_CLOCK));
  when.appendChild(el2("span",null, fmtDate(parseYmd(at.date),
    {weekday:"long",day:"numeric",month:"long"}, at.date)));
  p.appendChild(when);

  const title = el2("input","agfield");
  title.type = "text"; title.placeholder = tt("what_is_it", null, "¿Qué es?");
  title.value = at.title || "";
  p.appendChild(title);

  const row = el2("div","agfrow");
  const start = el2("input","agfield agftime"); start.type = "time"; start.value = hhmm(at.start || 9*60);
  const mins = el2("select","agfield agfdur");
  [[30,tt("dur_30",null,"30 min")],[60,tt("dur_60",null,"1 h")],
   [90,tt("dur_90",null,"1 h 30")],[120,tt("dur_120",null,"2 h")]].forEach(([v,l])=>{
    const o = el2("option",null,l); o.value = String(v); if(v===60) o.selected = true; mins.appendChild(o);
  });
  row.appendChild(start); row.appendChild(mins); p.appendChild(row);

  const meetRow = el2("label","agfcheck");
  const meet = el2("input"); meet.type = "checkbox";
  meetRow.appendChild(meet);
  meetRow.appendChild(el2("span",null, tt("with_meet", null, "Con videollamada de Google Meet")));
  p.appendChild(meetRow);

  const err = el2("div","agwarn"); err.hidden = true; p.appendChild(err);

  const acts = el2("div","agpacts");
  const save = el2("button","done", tt("save", null, "Guardar"));
  save.onclick = ()=>{
    const t = (title.value || "").trim();
    if(!t){ err.textContent = tt("needs_title", null, "Ponle un nombre a la cita."); err.hidden = false;
            title.focus(); return; }
    const m = mins2(start.value);
    if(m == null){ err.textContent = tt("needs_time", null, "Esa hora no la entiendo."); err.hidden = false;
                   return; }
    const dur = Number(mins.value) || 60;
    state.add = null;
    Promise.resolve(ctx.action("add_meeting", {
      title: t, date: at.date, startTime: hhmm(m), endTime: hhmm(Math.min(24*60-1, m + dur)),
      meet: meet.checked ? true : undefined,
    })).then(nd => redraw(nd)).catch(()=>redraw());
  };
  const no = el2("button",null, tt("cancel", null, "Cancelar")); no.onclick = close;
  acts.appendChild(save); acts.appendChild(no);
  p.appendChild(acts);

  veil.appendChild(p); root.appendChild(veil);
  raf(()=>{ try{ title.focus(); }catch(_){} });
}

// "HH:MM" → minutes, or null when the field is empty or unreadable. An unreadable time must not silently
// become midnight: an appointment nobody asked for at 00:00 is worse than a refusal that says so.
export function mins2(v){
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(v || "").trim());
  if(!m) return null;
  const h = Number(m[1]), mi = Number(m[2]);
  if(h > 23 || mi > 59) return null;
  return h*60 + mi;
}

export function renderDetail(root, ev, ctx, state, redraw){
  const veil = el2("div","agveil");
  veil.onclick = e => { if(e.target===veil){ state.sel=null; state.confirmDel=false; redraw(); } };
  const p = el2("div","agpanel"); p.style.setProperty("--evc", hueOf(ev));
  const head = el2("div","agphead");
  head.appendChild(el2("div","agpbar"));
  head.appendChild(el2("div","agptitle", ev.title));
  const x = el2("button","agpx","×"); x.title = tt("close", null, "Cerrar");
  x.onclick = ()=>{ state.sel=null; state.confirmDel=false; redraw(); };
  head.appendChild(x); p.appendChild(head);

  const when = el2("div","agprow"); when.appendChild(svgEl(ICO_CLOCK));
  const d = parseYmd(ev.date);
  when.appendChild(el2("span",null,
    `${fmtDate(d,{weekday:"long",day:"numeric",month:"long"},ev.date)} · ${timeLabel(ev)}`));
  p.appendChild(when);

  if(ev.location){ const r=el2("div","agprow"); r.appendChild(svgEl(ICO_PIN));
    r.appendChild(el2("span",null,ev.location)); p.appendChild(r); }
  // V2-697 — HOW YOU JOIN, first among the optional rows: it is the one thing on this card somebody is about
  // to need at a specific minute. The connector only ever stores a VIDEO entry point, so the phone bridge and
  // its PIN never reach here — the operator's own words, «cosas que yo considero que son extras y absurdas».
  const meetHref = safeHttpUrl(ev.meetLink);
  if(meetHref){
    const r=el2("div","agprow"); r.appendChild(svgEl(ICO_CAM));
    const a=el2("a","agpmeet", tt("join_meet", null, "Entrar a la videollamada"));
    a.href = meetHref; a.target = "_blank"; a.rel = "noopener noreferrer";
    r.appendChild(a); p.appendChild(r);
  }
  // WHO CONVENED IT. The connector sets `organizer` only when it is NOT us, so its mere presence is the
  // answer to «did somebody invite me, or is this mine?» — and when it is ours the row is simply absent
  // rather than saying so, because a card about your own appointment does not need to name you.
  if(ev.organizer){
    const r=el2("div","agprow"); r.appendChild(svgEl(ICO_HOST));
    r.appendChild(el2("span",null, tt("invited_by",{who:ev.organizer},"Te invitó {who}")));
    p.appendChild(r);
  }
  if((ev.guests||[]).length){
    const r=el2("div","agprow agpguests"); r.appendChild(svgEl(ICO_USERS));
    const box=el2("div","agpglist");
    for(const g of ev.guests){
      const row=el2("div","agpg");
      const rs=String(g.rsvp||"");
      const mk=el2("i","agpgm "+(RSVP_MARK[rs]?rs:"unknown"), RSVP_MARK[rs]||"·");
      mk.title = rs==="accepted" ? tt("rsvp_yes", null, "Ha aceptado")
               : rs==="declined" ? tt("rsvp_no", null, "No va")
               : rs==="tentative" ? tt("rsvp_maybe", null, "Quizá")
               : tt("rsvp_none", null, "Sin responder");
      row.appendChild(mk);
      row.appendChild(el2("span","agpgn", g.name || g.email || ""));
      if(g.organizer) row.appendChild(el2("i","agpgo", tt("organizer", null, "organiza")));
      box.appendChild(row);
    }
    r.appendChild(box); p.appendChild(r);
  } else if((ev.attendees||[]).length){
    // A meeting the operator dictated: names only, no roster to report.
    const named = ev.attendees.filter(a=>String(a).trim());
    const r=el2("div","agprow"); r.appendChild(svgEl(ICO_USERS));
    r.appendChild(el2("span",null, named.length
      ? `${ev.attendees.length} · ${named.join(", ")}`
      : tt("n_people",{n:ev.attendees.length},"{n} personas")));
    p.appendChild(r);
  }
  if(ev.remindAt){ const r=el2("div","agprow"); r.appendChild(svgEl(ICO_BELL));
    r.appendChild(el2("span",null, tt("reminder_at",{at:ev.remindAt},"Aviso el {at}"))); p.appendChild(r); }
  if(ev.notes){ const r=el2("div","agprow"); r.appendChild(svgEl(ICO_NOTE));
    r.appendChild(el2("span",null,ev.notes)); p.appendChild(r); }

  // V2-697 — YOUR answer and THEIRS are two different facts, and this card used to print one under the other's
  // name: on a Google row `status` was the OPERATOR's own responseStatus while the label said «sin confirmar
  // por la otra parte». An invitation he had accepted therefore read «Confirmada» as though THEY had agreed.
  const invited = !!(ev.myRsvp && ev.organizer);      // somebody else convened it and we are on the guest list
  if(ev.meeting && invited){
    const mine = ev.myRsvp;
    const st = el2("div","agpstate " + (mine==="accepted" ? "confirmed" : mine==="declined" ? "declined" : "pending"));
    st.appendChild(svgEl(mine==="accepted" ? ICO_CHECK : ICO_CLOCK));
    st.appendChild(el2("span",null,
      mine==="accepted"  ? tt("mine_yes", null, "Vas a ir")
    : mine==="declined"  ? tt("mine_no", null, "Has dicho que no vas")
    : mine==="tentative" ? tt("mine_maybe", null, "Has dicho que quizá")
    :                      tt("mine_none", null, "No has respondido todavía")));
    p.appendChild(st);
  }
  if(ev.meeting && (ev.guests||[]).length){
    const yes = ev.guests.filter(g=>g.rsvp==="accepted").length;
    const st = el2("div","agpstate " + (yes===ev.guests.length ? "confirmed" : "pending"));
    st.appendChild(svgEl(yes===ev.guests.length ? ICO_CHECK : ICO_CLOCK));
    st.appendChild(el2("span",null, tt("others_yes",{yes,total:ev.guests.length},
      "{yes} de {total} han aceptado")));
    p.appendChild(st);
  } else if(ev.meeting && (ev.attendees||[]).length){
    const st = el2("div","agpstate " + (ev.status==="pending" ? "pending" : "confirmed"));
    st.appendChild(svgEl(ev.status==="pending" ? ICO_CLOCK : ICO_CHECK));
    st.appendChild(el2("span",null, ev.status==="pending"
      ? tt("state_pending", null, "Sin confirmar por la otra parte")
      : tt("state_confirmed", null, "Confirmada")));
    p.appendChild(st);
  }

  if(ev.repeat) p.appendChild(el2("div","agnote", "↻ " + repeatLabel(ev.repeat)));

  // Only actions that map to a DECLARED data-op — a button that promises what the API cannot do is the
  // failure this widget's own history is made of (V2-540).
  if(ev.meeting){
    const acts = el2("div","agpacts");
    const call = (name, payload) => {
      state.sel = null; state.confirmDel = false;
      Promise.resolve(ctx.action(name, payload)).then(nd => redraw(nd)).catch(()=>redraw());
    };
    // V2-697 — ANSWERING an invitation. Offered only when somebody else convened it and we are on the guest
    // list, because that is the only case where a response status exists for us to set; and the answer we
    // have already given is not offered again. No «propose another time», by the operator's own scoping:
    // «yo por ahora no haría la funcionalidad de proponer otra hora, pero sí diría si sí o si no».
    if(invited){
      if(ev.myRsvp !== "accepted"){
        const b = el2("button","ok","✓ " + tt("rsvp_accept", null, "Sí, voy"));
        b.onclick = ()=>call("rsvp_meeting", {title: ev.title, date: ev.date, answer: "accepted"});
        acts.appendChild(b);
      }
      if(ev.myRsvp !== "declined"){
        const b = el2("button",null,"✗ " + tt("rsvp_decline", null, "No puedo ir"));
        b.onclick = ()=>call("rsvp_meeting", {title: ev.title, date: ev.date, answer: "declined"});
        acts.appendChild(b);
      }
    } else if(ev.status === "pending"){
      const b = el2("button",null,"✓ " + tt("mark_confirmed", null, "Ya está confirmada"));
      b.onclick = ()=>call("update_meeting", {title: ev.title, date: ev.date, status: "confirmed"});
      acts.appendChild(b);
    }
    if(!ev.remindAt && !ev.allDay){
      const b = el2("button",null,"🔔 " + tt("remind_2h", null, "Avisarme 2 h antes"));
      b.onclick = ()=>call("set_reminder",
        {title: ev.title, date: ev.date, at: hhmm(Math.max(0, ev.start-120))});
      acts.appendChild(b);
    }
    if(state.confirmDel){
      // V2-769 — one day of a series, or the whole series: two different deletions, two buttons.
      const yes = el2("button","risk", ev.repeat ? tt("delete_once", null, "Solo este día")
                                                 : tt("delete_yes", null, "Sí, cancélala"));
      yes.onclick = ()=>call("cancel_meeting", {title: ev.title, date: ev.date});
      if(ev.repeat){
        const all = el2("button","risk", tt("delete_series", null, "Toda la serie"));
        all.onclick = ()=>call("cancel_meeting", {title: ev.title, date: ev.date, whole: true});
        acts.appendChild(all);
      }
      const no = el2("button",null, tt("delete_no", null, "No"));
      no.onclick = ()=>{ state.confirmDel=false; redraw(); };
      acts.appendChild(yes); acts.appendChild(no);
    } else {
      const b = el2("button","risk", tt("delete", null, "Cancelar cita"));
      b.onclick = ()=>{ state.confirmDel=true; redraw(); };
      acts.appendChild(b);
    }
    p.appendChild(acts);
  } else if(ev.system){
    // What it IS, said plainly, because the one thing that must not happen is him reading it as a meeting.
    p.appendChild(el2("div","agnote", ev.recurring
      ? tt("system_task_every", {every: ev.notes || ""},
           "Tarea del sistema: se repite {every}. No es una cita tuya.")
      : tt("system_task_note", null,
           "Tarea del sistema: zaelar la hará a esta hora. No es una cita tuya.")));
  } else if(ev.planned){
    p.appendChild(el2("div","agnote",
      tt("planned_note", null, "Bloque planificado por tu agenda, no una cita: se recoloca solo al replanificar.")));
  }
  veil.appendChild(p); root.appendChild(veil);
}
