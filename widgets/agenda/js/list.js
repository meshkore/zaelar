// Agenda widget — the Schedule list and the TAREAS section (the operator's numbered task lists).
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { tt, fmtDate, raf, ymd, parseYmd, hhmm, el2, svgEl, ICO_CHECK, hueOf, badges } from "./shared.js";

// ── LIST (Schedule) ───────────────────────────────────────────────────────────────────────────────────
export function renderList(host, anchor, all, data, onPick){
  const today = data.date || ymd(new Date());  const from = anchor;
  const rows = all.filter(e=>e.date >= from).sort((a,b)=>
    a.date.localeCompare(b.date) || a.start-b.start);
  if(!rows.length){
    host.appendChild(el2("div","agempty", tt("nothing_ahead", null, "No tienes nada apuntado a partir de hoy.")));
    return;
  }  const wrap = el2("div","aglist");  const byDay = {};
  rows.forEach(e=>{ (byDay[e.date] = byDay[e.date] || []).push(e); });
  Object.keys(byDay).sort().slice(0,60).forEach(ds=>{
    const d = parseYmd(ds);
    const row = el2("div","agday" + (ds===today?" today":""));
    const dd = el2("div","agdaydate");  dd.appendChild(el2("div","d", String(d.getDate())));
    dd.appendChild(el2("div","w", fmtDate(d,{weekday:"short"},"").replace(/\.$/,"")));
    row.appendChild(dd);  const evs = el2("div","agdayevs");
    byDay[ds].forEach(e=>{
      const r = el2("div","agrow" + (e.status==="pending"?" pending":""));
      r.style.setProperty("--evc", hueOf(e));
      r.appendChild(el2("div","agrowh", e.allDay ? tt("all_day_short", null, "Todo el día") : hhmm(e.start)));
      r.appendChild(el2("div","agrowt", e.title));  const meta = [];
      if(e.location) meta.push(e.location);
      if((e.attendees||[]).length) meta.push(tt("n_people",{n:e.attendees.length},"{n} personas"));
      if(meta.length) r.appendChild(el2("div","agrowm", meta.join(" · ")));
      r.appendChild(badges(e));
      r.onclick = ev => { ev.stopPropagation(); onPick(e); };
      evs.appendChild(r);
    });  row.appendChild(evs);  wrap.appendChild(row);
  });  host.appendChild(wrap);
}

// ── V2-744 · TAREAS — the operator's own lists, numbered as he reads them ─────────────────────────────
//
// Operator, 2026-09-21: «arriba del todo un selector que separe lo que es agenda de tareas… una lista
// general y que el usuario pueda generar una lista para varias cosas… asegúrate de que todo está bastante
// numerado para que cuando yo vea una lista le diga: ábreme la lista número 3, coge el ítem número 2 y
// modifícalo por esto».
//
// So the NUMBER is a first-class part of the render and not an afterthought: every list row and every item
// row leads with the position the voice will name, and those positions come from the server's own
// `tasks.lists`/`tasks.items` — the same arrays `tasklists.digest()` builds the brain's view from. Two
// numberings of one screen would mean «the second one» points at different rows depending on who is asked,
// which is exactly the disagreement `index.py` was written to end.
export function taskWhen(it){
  if(!it.date && !it.time) return "";
  const d = it.date ? parseYmd(it.date) : null;
  const day = d ? fmtDate(d, {day:"numeric", month:"short"}, it.date) : "";
  return (day + (it.time ? " " + it.time : "")).trim();
}

export function renderTasks(host, data, ctx, S, redraw){
  const T = (data && data.tasks) || {};  const lists = Array.isArray(T.lists) ? T.lists : [];
  const byId = (T.items && typeof T.items === "object") ? T.items : {};
  const cur = lists.find(l => l.id === S.tl) || lists[0] || null;
  const items = (cur && byId[cur.id]) || [];

  // Every mutation goes through the host, like the coach rail does: the widget never writes, it ASKS, and
  // the fresh data comes back as the new render. `act` re-renders with the answer rather than guessing it.
  const act = async (name, payload) => { redraw(await ctx.action(name, payload || {})); };

  const wrap = el2("div","agt");

  // ── the lists, each with its number and its progress ───────────────────────────────────────────────
  // V2-746 — the column is a PANE with its own header, and the header is where "＋ Nueva lista" lives now.
  // The operator: «el botón de nueva lista, pues abajo no está bien porque cuando tengamos 100 listas no se
  // va a ver». It sat after the rows, so it scrolled with them; a control that leaves the screen when the
  // data grows is a control that stops existing exactly when it is most needed. It is a flex SIBLING of the
  // scroller now, which is stickiness by construction rather than by a `position` nobody can see is load
  // bearing.
  const side = el2("div","agt-side");  const shead = el2("div","agt-sidehead");
  shead.appendChild(el2("span","agt-sidetitle", tt("tasks_lists", null, "Listas")));
  side.appendChild(shead);  const rows = el2("div","agt-rows");
  lists.forEach(l => {
    const b = el2("button","agt-list" + (cur && l.id === cur.id ? " on" : ""));
    b.dataset.list = l.id; b.dataset.no = String(l.no);
    // V2-746 — the row's cells are DIRECT children of the row, because the row is a grid and a grid only
    // places its own children. They used to live inside two nested inline-styled divs, so every row sized
    // its own count cell to its own digits: twelve lists landed on six different right edges, and «1/3»
    // under «12/40» is exactly the alignment this pass is for. The nesting also left `.agt-prog` outside
    // the grid, where the rule that spans it across the row could never apply.
    b.appendChild(el2("span","agt-no", String(l.no)));
    // The BUILT-IN list keeps a translated label while it carries its untouched default name; once he
    // renames it, the name he chose wins — it is his data from that moment on.
    const name = (l.builtin && String(l.name) === "General") ? tt("tasks_general", null, "General") : String(l.name || "");
    b.appendChild(el2("span","agt-lname", name));
    b.appendChild(el2("span","agt-count", `${l.done}/${l.total}`));
    const bar = el2("div","agt-prog" + (l.total && l.done >= l.total ? " full" : "")); const fill = el2("span");
    fill.style.width = (l.total ? Math.round(100 * l.done / l.total) : 0) + "%";
    bar.appendChild(fill); b.appendChild(bar);
    b.onclick = () => { S.tl = l.id; S.tlEdit = false; S.tlAsk = ""; redraw(); };
    rows.appendChild(b);
  });
  if(!lists.length) rows.appendChild(el2("div","agt-empty", tt("tasks_no_lists", null, "Ninguna lista todavía.")));
  side.appendChild(rows);
  // `.agt-newl` keeps its class because it keeps its JOB — it is the new-list affordance, and where it sits
  // is a layout decision, not an identity one. Open, it takes the header's width; closed, it is one ＋.
  const newl = el2("div","agt-newl" + (S.tlNew ? " open" : ""));
  if(S.tlNew){
    const inp = el2("input","agt-in"); inp.type = "text";
    inp.placeholder = tt("tasks_list_name", null, "Nombre de la lista");
    const save = () => { const v = inp.value.trim(); S.tlNew = false;
                         if(v) act("add_list", {name: v}); else redraw(); };
    inp.onkeydown = e => { if(e.key === "Enter") save(); if(e.key === "Escape"){ S.tlNew = false; redraw(); } };
    const ok = el2("button","agt-b on", tt("tasks_add", null, "Añadir")); ok.onclick = save;
    newl.appendChild(inp); newl.appendChild(ok);  raf(() => { try{ inp.focus(); }catch(_){} });
  } else {
    // The ＋ carries its words in the tooltip, not on its face: in a 40px header bar a full label would push
    // the column title out, and the label is what the pointer asks for rather than what the eye scans.
    const add = el2("button","agt-plus", "＋");  add.dataset.a2 = "newlist";
    add.title = tt("tasks_new_list", null, "Nueva lista");  add.setAttribute("aria-label", add.title);
    add.onclick = () => { S.tlNew = true; redraw(); };  newl.appendChild(add);
  }  shead.appendChild(newl);  wrap.appendChild(side);

  // ── the chosen list ────────────────────────────────────────────────────────────────────────────────
  const main = el2("div","agt-main");
  if(!cur){ main.appendChild(el2("div","agt-empty", tt("tasks_empty", null, "Esta lista está vacía."))); }
  else {
    const head = el2("div","agt-head");
    head.appendChild(el2("span","agt-no", String(cur.no)));
    if(S.tlEdit){
      const inp = el2("input","agt-in"); inp.type = "text"; inp.value = String(cur.name || "");
      const save = () => { const v = inp.value.trim(); S.tlEdit = false;
                           if(v && v !== cur.name) act("rename_list", {list: cur.id, newName: v}); else redraw(); };
      inp.onkeydown = e => { if(e.key === "Enter") save(); if(e.key === "Escape"){ S.tlEdit = false; redraw(); } };
      inp.onblur = save;  head.appendChild(inp);
      raf(() => { try{ inp.focus(); inp.select(); }catch(_){} });
    } else {
      const nm = (cur.builtin && String(cur.name) === "General") ? tt("tasks_general", null, "General") : String(cur.name || "");
      head.appendChild(el2("div","agt-title", nm));  const id = el2("span","agt-id", cur.id);
      id.title = tt("tasks_share_id", null, "Identificador de la lista — para compartirla");
      // No clipboard permission, no network: selecting the text is what a widget is allowed to do, and it
      // is enough for him to read it out or copy it by hand.
      id.onclick = () => { try{ const r = document.createRange(); r.selectNodeContents(id);
                                const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); }catch(_){} };
      head.appendChild(id);
    }  const acts = el2("div","agt-acts");
    const ren = el2("button","agt-b", tt("tasks_rename", null, "Renombrar"));
    ren.dataset.a2 = "rename"; ren.onclick = () => { S.tlEdit = true; redraw(); };
    const clr = el2("button","agt-b danger", tt("tasks_clear", null, "Vaciar"));
    clr.dataset.a2 = "clear"; clr.onclick = () => { S.tlAsk = "clear"; redraw(); };
    acts.appendChild(ren); acts.appendChild(clr);
    if(!cur.builtin){
      const del = el2("button","agt-b danger", tt("tasks_delete_list", null, "Borrar lista"));
      del.dataset.a2 = "deletelist"; del.onclick = () => { S.tlAsk = "delete"; redraw(); };
      acts.appendChild(del);
    }  head.appendChild(acts);
    main.appendChild(head);

    // The confirmation is IN the card with Yes/No — the house rule (no popups), the same shape the
    // appointment's own «¿la cancelo?» uses two hundred lines above.
    if(S.tlAsk){
      const ask = el2("div","agt-ask");  const del = S.tlAsk === "delete";
      ask.appendChild(el2("span", null, (del ? tt("tasks_confirm_delete", {name: cur.name},
                                                  `¿Borro la lista «${cur.name}» entera?`)
                                             : tt("tasks_confirm_clear", {name: cur.name},
                                                  `¿Vacío «${cur.name}»?`))));
      const yes = el2("button","agt-b on", del ? tt("tasks_delete_yes", null, "Sí, bórrala")
                                               : tt("tasks_clear_yes", null, "Sí, vacíala"));
      yes.dataset.a2 = del ? "deleteyes" : "clearyes";
      yes.onclick = () => { S.tlAsk = ""; act(del ? "delete_list" : "clear_list", {list: cur.id}); };
      const no = el2("button","agt-b", tt("cancel", null, "Cancelar"));
      no.onclick = () => { S.tlAsk = ""; redraw(); };  ask.appendChild(yes); ask.appendChild(no);
      main.appendChild(ask);
    }

    // The table's label line. It carries no data and it is what turns a stack of rows into columns — the
    // one thing a spreadsheet has that a list of chips does not.
    if(items.length){
      const cols = el2("div","agt-cols");  cols.appendChild(el2("i", null, ""));
      cols.appendChild(el2("i","n", "Nº"));
      cols.appendChild(el2("i", null, tt("tasks_col_task", null, "Tarea")));
      cols.appendChild(el2("i", null, tt("tasks_col_when", null, "Cuándo")));
      cols.appendChild(el2("i", null, ""));  main.appendChild(cols);
    }

    const box = el2("div","agt-items");
    if(!items.length) box.appendChild(el2("div","agt-empty", tt("tasks_empty", null, "Esta lista está vacía.")));
    items.forEach(it => {
      const row = el2("div","agt-item" + (it.status === "done" ? " done" : ""));
      row.dataset.task = it.id; row.dataset.no = String(it.no);
      const chk = el2("button","agt-check" + (it.status === "done" ? " on" : ""));
      chk.title = tt("done", null, "Hecha");
      if(it.status === "done") chk.appendChild(svgEl(ICO_CHECK));
      chk.onclick = () => act(it.status === "done" ? "update_task" : "done",
                              {list: cur.id, task: it.id, taskId: it.id, status: "pendiente"});
      row.appendChild(chk);
      row.appendChild(el2("span","agt-ino", it.no + "."));
      if(S.tlItem === it.id){
        const inp = el2("input","agt-in"); inp.type = "text"; inp.value = String(it.title || "");
        const save = () => { const v = inp.value.trim(); S.tlItem = "";
                             if(v && v !== it.title) act("update_task", {list: cur.id, task: it.id, newTitle: v});
                             else redraw(); };
        inp.onkeydown = e => { if(e.key === "Enter") save(); if(e.key === "Escape"){ S.tlItem = ""; redraw(); } };
        inp.onblur = save;
        row.appendChild(inp);
        raf(() => { try{ inp.focus(); inp.select(); }catch(_){} });
      } else {
        row.appendChild(el2("span","agt-text", String(it.title || "")));
        const when = taskWhen(it);
        // The "Cuándo" cell is ALWAYS present, empty or not: a grid column that some rows skip is a grid
        // whose later columns slide left on those rows, and the alignment is the whole point of the change.
        row.appendChild(when ? el2("span","agt-when", when) : el2("span", null, ""));
        const ops = el2("div","agt-ops");
        const ed = el2("button","agt-ib", "✎"); ed.title = tt("tasks_edit", null, "Editar");
        ed.dataset.a2 = "edititem";
        ed.onclick = () => { S.tlItem = it.id; redraw(); };
        const rm = el2("button","agt-ib danger", "✕"); rm.title = tt("tasks_delete", null, "Borrar");
        rm.dataset.a2 = "deleteitem";
        rm.onclick = () => act("delete_task", {list: cur.id, task: it.id});
        ops.appendChild(ed); ops.appendChild(rm);
        row.appendChild(ops);
      }
      box.appendChild(row);
    });
    main.appendChild(box);

    const add = el2("div","agt-add");
    const inp = el2("input","agt-in"); inp.type = "text"; inp.dataset.add = "task";
    inp.placeholder = tt("tasks_add_item", null, "Añadir tarea…");
    const push = () => { const v = inp.value.trim(); if(!v) return; inp.value = "";
                         act("add_task", {title: v, list: cur.id}); };
    inp.onkeydown = e => { if(e.key === "Enter") push(); };
    const ok = el2("button","agt-b on", tt("tasks_add", null, "Añadir"));
    ok.dataset.a2 = "additem"; ok.onclick = push;
    add.appendChild(inp); add.appendChild(ok);
    main.appendChild(add);
  }
  wrap.appendChild(main);
  host.appendChild(wrap);
}
