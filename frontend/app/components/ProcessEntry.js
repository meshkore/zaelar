// ============================================================================
// ProcessEntry.js — what a RUNNING process is doing, under its row in the processes panel (V2-822).
//
// The operator (2026-10-27): an errand's work happens in the background, the card he asked for is the only card it
// opens, and its progress lives in ONE place — here, under the running process's row. Collapsed it is three or four
// lines (the plan around the step it is on: ✓ done · ▸ now · · next, and whether the page needs him); expanded, by
// his click, it is everything the results sheet's «Proceso» tab used to show: the whole plan, the browser's page and
// capture, how much it has looked at, and the narration, newest first.
//
// ONE SOURCE. Both views paint the SAME record, `GET /api/tasks/<id>/process` (`nucleo/process_view.py`), derived
// from the dispatcher's live registry on every read and never stored. Nothing here keeps its own copy of the story:
// the record is re-read when the engine says the process moved (SSE `task` events → `store.processRev`).
//
// Shared by both shells: the desktop's processes tab (ChatWall) and the phone's menu (MenuSheet). Its CSS lives in
// core/shared-surfaces.css for that reason. Built imperatively, not with nested reactive children: the live list is
// rebuilt on every board refresh, and an effect per entry would outlive the node it painted.
// ============================================================================

import { h } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";

const _recs = new Map();      // key → the last record read (so a rebuilt row paints at once, then refreshes)
const _open = new Set();      // keys he expanded — his choice survives the list being rebuilt
let _watching = false, _timer = null;

// The i18n seam, same shape as the widgets': the key, else the literal fallback (a render outside the engine).
function tt(key, params, fb){
  try{ const s = t(key, params); if(s && s !== key) return s; }catch(_){}
  return fb;
}
function elem(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = text;
  return e;
}

// ── THE HARVEST in numbers (moved here from the results sheet's process tab, V2-296 → V2-822). It is a FUNNEL, read
// in order: how much was examined → what was collected → what fell out at each cut → what remains. The three pillars
// are ALWAYS painted, zero included («0 fichas leídas» says nobody read anything); a rejection only when there is
// one; `{}` means «we do not know» and paints nothing. `sub` rows SUBTRACT, and a leading minus keeps the arithmetic
// readable when the grid wraps on a narrow panel.
const TALLY = [
  {k:"pages",    always:true},
  {k:"rows",     always:true},
  {k:"repeated", sub:true},
  {k:"unnamed",  sub:true},
  {k:"hollow",   sub:true},
  {k:"kept",     always:true},
  {k:"offered"},
];
const TALLY_FB = {pages:"páginas miradas", rows:"fichas leídas", repeated:"repetidas", unnamed:"sin nombre",
                  hollow:"sin precio ni tel.", kept:"candidatos", offered:"en la conversación"};

function tallyLabel(k){ return tt("chat.procTally." + k, null, TALLY_FB[k] || k); }

function paintHarvest(panel, harvest){
  if(!harvest || !Object.keys(harvest).length) return;
  const grid = elem("div","pe-stats");
  TALLY.forEach(({k, always, sub})=>{
    const n = Number(harvest[k] || 0);
    if(!n && !always) return;
    const box = elem("div","pe-stat" + (!n ? " dim" : "") + (sub ? " cut" : ""));
    box.appendChild(elem("b","", (sub ? "−" : "") + String(n)));   // U+2212: arithmetic, not a dash
    box.appendChild(elem("span","", tallyLabel(k)));
    grid.appendChild(box);
  });
  if(grid.childNodes.length) panel.appendChild(grid);
}

// The plan the worker DECLARED, in its words, never steps we invent: `rows` is the whole plan (expanded) or the
// window around the step it is on (collapsed — the one before, the one now, the one after).
function planRows(rec, all){
  const plan = Array.isArray(rec.plan) ? rec.plan.filter(s => String(s || "").trim()) : [];
  const done = Math.max(0, Math.min(plan.length, parseInt(rec.done, 10) || 0));
  const idx = plan.map((_, i) => i);
  const shown = all ? idx : idx.filter(i => i >= done - 1 && i <= done + 1);
  return shown.map(i => ({ text: String(plan[i]), state: i < done ? "done" : (i === done ? "now" : "next") }));
}

function paintPlan(box, rec, all){
  const rows = planRows(rec, all);
  if(!rows.length) return;
  const ul = elem("div","pe-plan");
  for(const r of rows){
    const li = elem("div","pe-step " + r.state);
    li.appendChild(elem("b","", r.state === "done" ? "✓" : (r.state === "now" ? "▸" : "·")));
    li.appendChild(elem("span","", r.text));
    ul.appendChild(li);
  }
  box.appendChild(ul);
}

function needsHim(br){ return !!(br && (br.wall || br.awaiting_login || br.question)); }

function paintBrowser(box, br){
  if(!br || !br.task_id) return;
  const wrap = elem("div","pe-page");
  const view = elem("div","pe-shot");
  if((br.shot_rev || 0) > 0 && br.shot){
    const img = document.createElement("img");
    img.alt = br.page_title || tt("chat.procPage", null, "Página");
    img.src = "/widgets/navegador/asset/" + br.shot + "?v=" + (br.shot_rev || 0);
    img.addEventListener("error", () => { view.textContent = ""; view.appendChild(elem("span","", tt("chat.procNoShot", null, "sin captura todavía…"))); });
    view.appendChild(img);
  } else {
    view.appendChild(elem("span","", tt("chat.procNoShot", null, "sin captura todavía…")));
  }
  wrap.appendChild(view);
  if(br.page_title || br.url){
    const u = elem("div","pe-url", br.page_title || br.url);
    u.title = br.url || "";
    wrap.appendChild(u);
  }
  if(br.wall) wrap.appendChild(elem("div","pe-need","⛔ " + br.wall));
  box.appendChild(wrap);
}

// ONE paint from ONE record. `open` only decides how much of it is shown.
export function paintEntry(node, rec, open){
  node.textContent = "";
  if(!rec || !rec.alive) return;
  const br = rec.browser || {};
  paintPlan(node, rec, open);
  if(!open){
    if(needsHim(br)) node.appendChild(elem("div","pe-need", tt("chat.procNeedsYou", null, "La página necesita que actúes en ella.")));
  } else {
    paintBrowser(node, br);
    paintHarvest(node, rec.harvest || {});
    const lines = Array.isArray(rec.phases) ? rec.phases.filter(x => String(x || "").trim()) : [];
    if(lines.length){
      node.appendChild(elem("div","hb-sectitle pe-logt", tt("chat.procLog", null, "Lo que ha ido haciendo (lo último, arriba)")));
      const log = elem("div","pe-log");
      lines.slice().reverse().forEach((s, i) => log.appendChild(elem("div","pe-line" + (i === 0 ? " now" : ""), String(s))));
      node.appendChild(log);
    }
  }
  const more = elem("button","hb-btn hb-btn--ghost hb-btn--sm pe-toggle",
                    open ? tt("chat.procLess", null, "Menos") : tt("chat.procMore", null, "Ver detalle"));
  more.type = "button";
  more.setAttribute("aria-expanded", open ? "true" : "false");
  more.addEventListener("click", (e) => {
    e.stopPropagation();
    const k = node.dataset.key;
    if(_open.has(k)) _open.delete(k); else _open.add(k);
    paintEntry(node, _recs.get(k), _open.has(k));
  });
  node.appendChild(more);
}

async function _load(key){
  try{
    const r = await fetch("/api/tasks/" + encodeURIComponent(key) + "/process", { cache: "no-cache" });
    const rec = await r.json();
    _recs.set(key, rec);
    document.querySelectorAll(".pe[data-key]").forEach(n => {
      if(n.dataset.key === key) paintEntry(n, rec, _open.has(key));
    });
  }catch(_){ /* the row's own note still says what it is doing; the next notice retries */ }
}

function _refreshAll(){
  const keys = new Set([...document.querySelectorAll(".pe[data-key]")].filter(n => n.isConnected).map(n => n.dataset.key));
  keys.forEach(_load);
}

function _watch(){
  if(_watching) return;
  _watching = true;
  // The engine says a process moved (a line, a plan, a step, a page) → re-read the visible entries, once per burst.
  createEffect(() => { store.processRev(); clearTimeout(_timer); _timer = setTimeout(_refreshAll, 350); });
}

// The entry under a live row. `key` is the errand's session id (what the SSE events name) or its durable row id —
// the record answers to both.
export function ProcessEntry(key){
  const k = String(key || "");
  const node = h("div", { class: "pe", "data-key": k });
  if(!k) return node;
  _watch();
  if(_recs.has(k)) paintEntry(node, _recs.get(k), _open.has(k));
  _load(k);
  return node;
}
