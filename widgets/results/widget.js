// Results widget — the GENERIC SURFACE where zaelar shows what it found. Whoever did the work (a Brain Worker, the
// browser, the brain) fills it through declared actions; this only RENDERS. It never searches by itself.
//
// FOUR TABS (2026-08-12) — because a complex search is not just its result:
//   · RESULTS — the cards, and a full record when one is opened (second page, with its "back").
//   · SUMMARY — where the work stands, how many candidates it explored, how many remain, and what it did.
//   · SOURCES — which websites it entered and WHAT HAPPENED on each one (entered · capped at 50 · required login · error).
//   · CRITERIA — the task as currently executed, with corrections the operator gave along the way.
// The active tab lives in the PERSISTED payload (like `view`/`focus`), not in a variable in this file: this is why
// "show me where you got this from" —a voice phrase that arrives through the brain— moves the screen, and why the
// sheet survives re-render, reconnect, and restart. The local click is rendered IMMEDIATELY and also persisted, so
// the tab does not blink waiting for the server and is not lost either.
//
// DYNAMIC RECORD. A boat does not read like a paper or an email: beyond fixed fields, an item may bring `blocks` — a
// list of composition pieces from a CLOSED vocabulary (text · facts · chips · gallery · meter · table · link ·
// section). This gives the freedom of "a different HTML record per result type" WITHOUT accepting third-party HTML:
// this payload comes from the open web, and everything is rendered with textContent.
//
// FLUID WIDTH. The sheet no longer owns its width (before: fixed 620px, so fullscreen left a narrow column in the
// middle of the screen). It takes 100% of its card and CSS distributes columns by the REAL available width — with a
// minimum per card type and a column CAP, so it neither strangles when shrunk nor turns into eight confetti columns
// when maximized.
//
// SECURITY: item text is web/3rd-party-sourced → built with textContent ONLY (never innerHTML).

import { CSS } from "./js/style.js";
import { PAINT, paintBrowser, paintResults } from "./js/panels.js";
import { CRIT_SECTIONS, I18N, TABS, elem, tabLabel, tt } from "./js/shared.js";

function injectStyles(){
  if(document.getElementById("hb-results-css"))return;
  const s=document.createElement("style"); s.id="hb-results-css"; s.textContent=CSS; document.head.appendChild(s);
}

// Is this paint a NAVIGATION or a data refresh? It matters for scroll: "View detail →" lives at the end of a card, so
// without returning to top the record opens halfway down (and switching tabs left you mid-list). But a worker `append`
// while the operator is reading must NOT move the page. Compare only the sheet position —tab and page—, never content.
// WeakMap: if the card dies, this goes with it.
const WHERE = new WeakMap();
function navigated(el, data, cur){
  const now = [cur, data.view || "list", data.focus || ""].join("|");
  const was = WHERE.get(el);
  WHERE.set(el, now);
  return was !== undefined && was !== now;
}

// Counter painted on each tab. Only when it says something: a "0" on four tabs is noise, and a red number on Sources
// is exactly what draws attention ("3 sites did not let me in").
function tabCount(id, data){
  const c = data.counts || {}, s = data.summary || {};
  // While the errand works, the Results tab carries the loader (V2-822: the process tab that used to is gone):
  // when the first rows land the list is what he reads, and this is what still says «I am working».
  if(id === "results"){
    const alive = !!(data.progress && data.progress.alive);
    return (c.shown || alive) ? {n: c.shown || 0, spin: alive} : null;
  }
  if(id === "sources") return c.sources ? {n: c.sources, bad: !!c.sources_failed} : null;
  if(id === "criteria"){
    const crit=data.criteria||{};
    const n=CRIT_SECTIONS.reduce((a,x)=>a+((crit[x.key]||[]).length),0);
    return n ? {n} : null;
  }
  if(id === "summary") return s.explored ? {n: s.explored} : null;
  return null;
}

export function render(el, data, ctx){
  I18N.t = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  injectStyles();
  data = data || {};
  el.className = "hb-results";
  // The panel is the sheet's scroller (V2-821) and it is rebuilt on every render, so a data refresh would throw the
  // operator back to the top of what he is reading. Its offset is carried over unless this paint is a NAVIGATION.
  const _was = el.querySelector(":scope > .hr-panel");
  const _wasTop = _was ? _was.scrollTop : 0;
  el.textContent = "";

  // Title and tabs live together in a FIXED header, outside the scroller: with several dozen results the sheet
  // scrolls and tabs must stay there (looking at the last card and jumping to Sources is a normal case).
  const top = elem("div","hr-top");
  // THE TITLE IS SAID ONCE. If the card already carries the TASK in its header (canvas marks it with
  // `data-host-title` when the manifest declares `live_title`), repeating it here in larger body text was the same
  // text twice 4px apart: noise, and one lost line of height in the most valuable part of the sheet. Own rendering is
  // kept as BACKUP: if this surface is ever mounted without the canvas header, the task cannot disappear.
  if(el.dataset.hostTitle !== "1"){
    top.appendChild(elem("div","hr-hd", data.title || tt("name", null, "Resultados")));
  }
  if(data.subtitle){
    // The header is FIXED: every line it occupies is taken away from results throughout scrolling. A real subtitle
    // ("8 real listings from Levante (SUV, ~5.00 m long...), from coches.net and coches.com. Ordered by...") reached
    // three lines. Bound to TWO on screen and keep the full text in the tooltip: control space without losing data,
    // which is different from clipping it.
    const sub = elem("div","hr-sub clamp2", data.subtitle);
    sub.title = data.subtitle;
    top.appendChild(sub);
  }
  // The USER/SESSION identity strip is NOT here anymore (V2-538, operator with the screenshot in front of
  // him: "una línea que no necesito para nada" between the title and the tabs of every sheet). Auditing a
  // session is SUMMARY work, so the strip lives at the bottom of that tab — see paintSummary().

  // ACTIVE TAB — the one he chose (`data.tab`, persisted, it RULES), else Results: the deliverable is what the sheet
  // shows; the work behind it is in the processes panel (V2-822).
  let cur = TABS.some(t=>t.id===data.tab) ? data.tab : "results";
  const bar = elem("div","hr-tabs");
  bar.setAttribute("role","tablist");     // a strip that scrolls sideways — the phone never wraps it
  const panel = elem("div","hr-panel");
  panel.setAttribute("data-hb-scroller", "");   // the hosts' ctx.top()/ctx.scroll() move THIS, not the card (V2-821)

  const paint = (moved)=>{
    panel.textContent="";
    paintBrowser(panel, data, ctx);          // only when the page needs HIM (a wall, a login, a question)
    (PAINT[cur] || paintResults)(panel, data, ctx, nav);
    bar.querySelectorAll(".hr-tab").forEach(b=>b.classList.toggle("on", b.dataset.tab===cur));
    if(moved && ctx && ctx.top) ctx.top();
  };

  // LOCAL NAVIGATION between the list and a record. The page the operator is on is sheet state (so the brain
  // knows what he is looking at, and a reload or «vuelve a la lista» by voice agrees with the screen) — but it
  // does not have to travel to the server and back to be DRAWN: the item is already in `data`. This is the same
  // shape the tabs have used since V2-538, and its absence here is what made «Ver detalle» look like a dead
  // button for as long as the SSE id was wrong. `WHERE` sees the change too, so the record opens at the top
  // instead of halfway down the page the button was at the bottom of.
  function nav(view, focus, warn){
    if(view === "detail"){ data.view = "detail"; data.focus = focus || ""; data.viewWarn = warn || ""; }
    else { delete data.view; delete data.focus; delete data.viewWarn; }
    cur = "results";
    paint(navigated(el, data, cur));
  }

  TABS.forEach(t=>{
    const b=elem("button","hr-tab"); b.type="button"; b.dataset.tab=t.id;
    b.appendChild(document.createTextNode(tabLabel(t.id)));
    const c=tabCount(t.id, data);
    if(c && c.n) b.appendChild(elem("span","hr-n"+(c.bad?" bad":""), String(c.n)));
    if(c && c.spin) b.appendChild(elem("span","hr-spin hr-tspin"));
    b.addEventListener("click", ()=>{
      if(cur===t.id) return;
      cur=t.id;
      // Paint IMMEDIATELY (the tab cannot blink while waiting for the server) and ALSO persist, because this sheet's
      // state does not live in the browser: this way the brain knows what the operator is looking at, and a reload or
      // "go back to results" by voice still matches the screen.
      paint(true);
      if(ctx && ctx.action) ctx.action("tab", {tab: t.id});
    });
    bar.appendChild(b);
  });

  top.appendChild(bar);
  el.append(top, panel);
  const _moved = navigated(el, data, cur);
  paint(_moved);
  if(!_moved && _wasTop) panel.scrollTop = _wasTop;

  // V2-591 — a voice scroll request, applied ONCE per push (the token guards the re-render loop: every data
  // refresh re-runs render, and without it one order would scroll on every refresh of a live sheet). The
  // scroller is card chrome, so the widget only ASKS its host (ctx.scroll) — same ownership as ctx.top().
  const scReq = data.scroll;
  if(scReq && scReq.n && scReq.n !== el._hbScrollN && ctx && ctx.scroll){
    el._hbScrollN = scReq.n;
    try{ ctx.scroll(scReq.where || "down"); }catch(_){}
  }
}
