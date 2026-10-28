// results widget — what each tab paints: results, summary, sources, criteria, and the browser's ask.
// Moved verbatim out of widget.js (refactor2710-12); widget.js stays the entry exporting `render`.

import { findFocused, gridStyle, makeCard, renderDetail } from "./card.js";
import { identityStrip, layoutFor } from "./parts.js";
import { CRIT_SECTIONS, SOURCE_STATUS, critLabel, critNote, elem, sourceLabel, tt } from "./shared.js";

// ── TAB 1 · RESULTS ─────────────────────────────────────────────────────────────────────────────────────────
export function paintResults(panel, data, ctx, nav){
  const items = Array.isArray(data.items) ? data.items : [];

  if(data.view === "detail"){
    const it = findFocused(items, data.focus);
    if(it){ renderDetail(panel, it, ctx, nav, data.viewWarn); return; }
    // focus pointing at nothing (list replaced under it) → fall through to the list, never a blank screen
  }

  const total = items.length;
  const all = items.slice(0, 24);
  if(!all.length){
    // V2-822 — an errand still working says so, and where its steps are: the processes panel, not this card.
    const working = !!(data.progress && data.progress.alive);
    panel.appendChild(elem("div","hr-empty" + (working ? " working" : ""), working
      ? tt("working_empty", null, "Buscando… Lo que va haciendo se ve en Procesos.")
      : (data.note || tt("no_results", null, "Sin resultados todavía."))));
    return;
  }

  const primary = all.filter(it => it && it.primary);
  const rest = all.filter(it => !it || !it.primary);
  const choose = data.choosable ? { root: panel, ctx, chosenTitle: data.chosen } : null;
  // ONE layout for the whole list, decided from ALL the items: choosing per card would put a photo column on
  // some rows and not on others, which is precisely the ragged look the grid exists to prevent.
  const lay = layoutFor(all, data.kind, data.layout);

  // ONE GRID, featured results first and the SAME box (V2-703): «si un resultado solo ya ocupa toda la pantalla,
  // ¿de qué me sirve la lista?» — the featured card is told apart by border, ground and badge, never by size.
  const grid = elem("div","hr-grid");
  grid.style.gridTemplateColumns = gridStyle(all, data.columns, lay);
  // The layout DECISION, readable by a test and by whoever debugs it.
  grid.dataset.layout = lay;
  panel.appendChild(grid);
  primary.forEach(it => grid.appendChild(makeCard(it, true, choose, ctx, lay, nav, data.kind)));
  rest.forEach(it => grid.appendChild(makeCard(it, false, choose, ctx, lay, nav, data.kind)));

  // Faithful count: if the real pushed results exceed what we render, say so — never silently drop
  // obtained data (the operator asked for a REAL search; the interface must reflect its true size).
  if(total > all.length){
    const more = elem("div","hr-sub", tt("showing_n_of_total", {n: all.length, total}, `Mostrando ${all.length} de ${total} resultados.`));
    more.style.marginTop = "10px";
    panel.appendChild(more);
  }
}

// ── TAB 2 · SUMMARY ─────────────────────────────────────────────────────────────────────────────────────────
// REPORTED and DERIVED data are rendered separately on purpose: "explored" is only known by the worker, and if nobody
// said it the tab SAYS so instead of showing the number of cards as if it were the breadth.
export function paintSummary(panel, data){
  const s = data.summary || {}, c = data.counts || {};
  const hasAny = Object.keys(s).length || c.shown || c.sources;
  if(!hasAny){
    panel.appendChild(elem("div","hr-empty",
      tt("summary_empty_1", null, "Todavía no hay nada que resumir. Esta pestaña se llena mientras se trabaja: estado, cuántos candidatos se ")
      + tt("summary_empty_2", null, "han explorado y qué se ha ido haciendo.")));
    panel.appendChild(identityStrip(data.identity));   // the audit ids belong to this tab now — see render()'s note (V2-538)
    return;
  }
  if(s.state){
    const row=elem("div","hr-state");
    const done=/termin|complet|listo|entregad|finaliz/i.test(s.state);
    row.appendChild(elem("span","hr-dot "+(done?"ok":"idle")));
    row.appendChild(elem("span","", s.state));
    panel.appendChild(row);
  }
  const stats=elem("div","hr-stats");
  const add=(value, label, tone)=>{
    const box=elem("div","hr-stat"+(tone?" "+tone:""));
    box.appendChild(elem("b","", value));
    // `label`, not `tallyLabel(k)`. There is no `k` in this scope: the call was copied from `paintHarvest`,
    // where the labels come from a table of KEYS, and here every caller already passes the translated string.
    // It went in with V2-694 (77640659) and has been throwing `ReferenceError: k is not defined` ever since —
    // out of `add`, out of `paintSummary`, out of `render`, so the WHOLE sheet died the moment the Summary tab
    // was the active one. `tests/browser/e2e/widgets/test_results_render.py` has been carrying it as an ERROR
    // (not a failure) in its summary fixture, which is why it read as a broken harness rather than a broken
    // widget. The operator's own pot sheet has a summary of 75 explored.
    box.appendChild(elem("span","", label));
    stats.appendChild(box);
  };
  const noBreadth = s.explored == null;
  add(noBreadth ? "—" : s.explored, noBreadth ? tt("unreported", null, "sin reportar") : tt("explored", null, "explorados"), noBreadth ? "dim" : "");
  add(c.shown || 0, tt("on_screen", null, "en pantalla"));
  if(s.discarded != null) add(s.discarded, tt("discarded", null, "descartados"));
  if(c.sources) add(c.sources, tt("sources", null, "fuentes"));
  // Problem sources go in their OWN cell and warning color. Stuffed into the "sources" label, they made a two-line
  // label ("SOURCES · 3 WITH / PROBLEM") that broke the row, and also hid the only datum here that asks the operator
  // for a decision inside another number's footer.
  if(c.sources_failed) add(c.sources_failed, tt("unused", null, "sin aprovechar"), "warn");
  if(s.round && s.round > 1) add(s.round, tt("round", null, "ronda"));
  panel.appendChild(stats);

  if(s.note) panel.appendChild(elem("div","hr-why", s.note));

  if(Array.isArray(s.steps) && s.steps.length){
    panel.appendChild(elem("div","hr-cgt",tt("what_was_done", null, "Lo que se ha hecho")));
    const ul=elem("ul","hr-steps");
    s.steps.forEach(st=>ul.appendChild(elem("li","", st)));
    panel.appendChild(ul);
  }

  // V2-728 — WHAT WAS THROWN OUT, and why. This tab already answered «how many did you discard»; the number
  // on its own was never the useful half. It goes HERE rather than in a tab of its own because it is the
  // same question at one more level of detail, and because the results list must keep meaning «the
  // selection»: a rejected candidate on it would be exactly the confusion the worker guide forbids.
  const rej = Array.isArray(data.rejected) ? data.rejected : [];
  if(rej.length){
    panel.appendChild(elem("div","hr-cgt", tt("discarded_title", null, "Descartados, y por qué")));
    const ul=elem("ul","hr-rejected");
    rej.forEach(r=>{
      const li=elem("li","");
      const name = r && r.title ? String(r.title) : "";
      if(r && r.url){
        const a=elem("a","hr-rej-t", name); a.href=String(r.url); a.target="_blank"; a.rel="noopener noreferrer";
        li.appendChild(a);
      } else {
        li.appendChild(elem("span","hr-rej-t", name));
      }
      if(r && r.why) li.appendChild(elem("span","hr-rej-w", String(r.why)));
      ul.appendChild(li);
    });
    panel.appendChild(ul);
  }
  panel.appendChild(identityStrip(data.identity));   // audit ids, moved here from the sticky header (V2-538)
}

// ── TAB 3 · SOURCES ─────────────────────────────────────────────────────────────────────────────────────────
// Where data comes from and WHAT happened at each site. This turns "I found nothing" into data that can be audited
// and corrected ("you enter that one, it asks for login").
export function paintSources(panel, data){
  const src = Array.isArray(data.sources) ? data.sources : [];
  if(!src.length){
    panel.appendChild(elem("div","hr-empty",
      tt("sources_empty_1", null, "Nadie ha reportado fuentes todavía. Aquí aparecerá cada web que se consulte y qué pasó en ella: si entró, ")
      + tt("sources_empty_2", null, "si le limitaron los resultados, si pedía autenticación o si dio error.")));
    return;
  }
  const c = data.counts || {};
  panel.appendChild(elem("div","hr-sub",
    `${src.length} fuente${src.length===1?"":"s"}`
    + (c.sources_failed ? ` · ${c.sources_failed} sin poder aprovechar` : "")
    + (c.from_sources ? ` · ${c.from_sources} resultados reunidos` : "")));
  // Sources that could NOT be used, FIRST. They are the ones asking for an operator decision ("that one asks for
  // login, I will enter"); successful ones only need to be counted. Stable order within each group.
  const rank = {bad: 0, warn: 1, idle: 2, ok: 3};
  const ordered = src.map((s, i) => [s, i]).sort((a, b) => {
    const ra = rank[(SOURCE_STATUS[a[0].status] || SOURCE_STATUS.ok).cls] ?? 3;
    const rb = rank[(SOURCE_STATUS[b[0].status] || SOURCE_STATUS.ok).cls] ?? 3;
    return ra - rb || a[1] - b[1];
  }).map(x => x[0]);

  const list=elem("div","hr-srcs");
  ordered.forEach(s=>{
    const st = SOURCE_STATUS[s.status] || SOURCE_STATUS.ok;
    const row=elem("div","hr-src"+(st.cls==="bad"||st.cls==="warn" ? " "+st.cls : ""));
    row.appendChild(elem("span","hr-dot "+st.cls));
    const mid=elem("div","");
    const name=elem("div","hr-sname");
    if(s.url){
      const a=elem("a","", s.name); a.href=s.url; a.target="_blank"; a.rel="noopener noreferrer"; name.appendChild(a);
    } else name.textContent = s.name;
    mid.appendChild(name);
    mid.appendChild(elem("div","hr-sst "+st.cls, sourceLabel(s.status)));
    if(s.detail) mid.appendChild(elem("div","hr-sd", s.detail));
    row.appendChild(mid);
    if(s.found != null){
      const n=elem("div","hr-sn"+(s.found ? "" : " zero"), String(s.found));
      n.appendChild(elem("small","", s.found === 1 ? tt("result_one", null, "resultado") : tt("result_many", null, "resultados")));
      row.appendChild(n);
    } else row.appendChild(elem("div",""));
    list.appendChild(row);
  });
  panel.appendChild(list);
}

// ── TAB 4 · CRITERIA ────────────────────────────────────────────────────────────────────────────────────────
// The task as it is being executed NOW. Not the conversation history: the active search criteria at this moment, so
// they can be seen and corrected ("make them 42 to 49 feet").
export function paintCriteria(panel, data){
  const c = data.criteria || {};
  const any = c.goal || CRIT_SECTIONS.some(s=>Array.isArray(c[s.key]) && c[s.key].length);
  if(!any){
    panel.appendChild(elem("div","hr-empty",
      tt("criteria_empty_1", null, "Todavía no hay criterios fijados. En cuanto se dirija una búsqueda aparecerán aquí el objetivo, los ")
      + tt("criteria_empty_2", null, "requisitos que descalifican, las preferencias y lo que se haya dado por supuesto — y podrás corregirlos ")
      + tt("criteria_empty_3", null, "hablando.")));
    return;
  }
  if(c.goal) panel.appendChild(elem("div","hr-goal", c.goal));
  const meta=[];
  if(c.domain) meta.push(c.domain);
  if(c.min_candidates) meta.push(tt("min_breadth", {n:c.min_candidates}, `amplitud mínima: ${c.min_candidates} candidatos`));
  if(c.n_final) meta.push(tt("n_final", {n:c.n_final}, `entrega: ${c.n_final} finalistas`));
  if(meta.length) panel.appendChild(elem("div","hr-sub", meta.join(" · ")));

  CRIT_SECTIONS.forEach(sec=>{
    const list = c[sec.key];
    if(!Array.isArray(list) || !list.length) return;
    const grp=elem("div","hr-cgrp "+sec.key);
    const t=elem("div","hr-cgt", critLabel(sec.key));
    const _note = critNote(sec.key);
    if(_note){ t.appendChild(document.createTextNode(" ")); t.appendChild(elem("em","","— "+_note)); }
    grp.appendChild(t);
    const ul=elem("ul","hr-clist");
    list.forEach(x=>ul.appendChild(elem("li","", x)));
    grp.appendChild(ul);
    panel.appendChild(grp);
  });
}

// ── THE BROWSER NEEDS HIM (V2-571 · V2-822) ──────────────────────────────────────────────────────────────────
// A browser task and its results sheet are ONE flow (V2-571), so the separate navegador card does not open for an
// errand. Its PROGRESS — the capture, the page, the narration — lives in the processes panel (V2-822); what stays
// here is only what the page needs HIM to do: a wall, a login handoff, a question. Then the page shows on the sheet
// he is looking at, above the tab, with the button. `data.browser` is DERIVED per read and `{}` once the errand
// ends; the capture refreshes by SSE (the task registry notifies this sheet's card), never by polling.
export function needsHim(br){ return !!(br && br.task_id && (br.wall || br.awaiting_login || br.question)); }
export function paintBrowser(panel, data, ctx){
  const br = data.browser || {};
  if(!needsHim(br)) return false;
  const wrap = elem("div","hr-proc");
  const nav = elem("div","hr-proc-nav");
  const view = elem("div","hr-navview");
  if((br.shot_rev || 0) > 0 && br.shot){
    const img = document.createElement("img");
    img.className = "hr-navimg";
    img.alt = br.page_title || tt("page_alt", null, "página");
    img.src = "/widgets/navegador/asset/" + br.shot + "?v=" + (br.shot_rev || 0);
    img.addEventListener("error", ()=>{
      view.textContent = "";
      view.appendChild(elem("div","hr-navph",tt("no_shot", null, "sin captura todavía…")));
    });
    view.appendChild(img);
  } else {
    view.appendChild(elem("div","hr-navph",tt("opening_tab", null, "abriendo pestaña…")));
  }
  nav.appendChild(view);
  if(br.page_title || br.url){
    const u = elem("div","hr-navurl", br.page_title || br.url);
    u.title = br.url || "";
    nav.appendChild(u);
  }
  if(br.wall) nav.appendChild(elem("div","hr-wall","⛔ " + br.wall));
  if(br.awaiting_login){
    const box = elem("div","hr-login");
    box.appendChild(elem("div","hr-login-t",
      tt("login_hint", null, "🔓 Inicia sesión en la ventana de Chrome que se abrió. Tu sesión se guardará para las próximas tareas.")));
    const btn = elem("button","hr-login-btn",tt("login_done", null, "Ya he iniciado sesión")); btn.type = "button";
    btn.addEventListener("click", async ()=>{
      btn.disabled = true;
      const r = (ctx && ctx.action) ? await ctx.action("auth_done", {task_id: br.task_id}) : null;
      // A REFUSED action has to SHOW (the V2-540 lesson): a silently dead login button on a refused forward
      // is exactly the undiagnosable click this sheet already paid for once.
      if(!r || r.ok === false){
        btn.disabled = false;
        btn.textContent = tt("login_done_", null, "Ya he iniciado sesión — ") + ((r && r.error) ? tt("login_retry", null, "no llegó, reintenta") : tt("no_answer", null, "sin respuesta"));
        btn.title = (r && r.error) ? String(r.error) : tt("engine_silent", null, "el motor no respondió a la acción");
      }
    });
    box.appendChild(btn);
    nav.appendChild(box);
  }
  if(br.question){
    const q = elem("div","hr-navq","❓ " + br.question);
    q.appendChild(elem("small","",tt("answer_voice", null, "Responde por voz.")));
    nav.appendChild(q);
  }
  wrap.appendChild(nav);
  panel.appendChild(wrap);
  return true;
}

export const PAINT = {results: paintResults, summary: paintSummary,
               sources: paintSources, criteria: paintCriteria};
