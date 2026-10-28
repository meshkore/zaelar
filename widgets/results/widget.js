// Results widget — the GENERIC SURFACE where zaelar shows what it found; whoever did the work fills it through
// declared actions, this only RENDERS. Four persisted tabs (results · summary · sources · criteria), so voice moves
// the screen and the sheet survives re-render and restart. A record is DYNAMIC (`blocks`, a closed vocabulary), the
// width is FLUID (CSS distributes columns by the real width). SECURITY: web-sourced text → textContent ONLY.

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
  // THE TITLE IS SAID ONCE: when the canvas header already carries it (`data-host-title`), it is not repeated here.
  if(el.dataset.hostTitle !== "1"){
    top.appendChild(elem("div","hr-hd", data.title || tt("name", null, "Resultados")));
  }
  if(data.subtitle){
    // The header is FIXED, so the subtitle is bound to TWO lines on screen, the full text in the tooltip.
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

  // LOCAL NAVIGATION between the list and a record: the view is persisted sheet state, but the item is already in
  // `data`, so it is drawn here first (same shape as the tabs, V2-538); `WHERE` opens the record at the top.
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
