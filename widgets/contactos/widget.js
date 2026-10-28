// Contacts widget — client render module (V2-541, redesigned V2-699, reorganised V2-715).
// Contract: render(el, data, ctx).
// ONE directory for every identity: ONE bar (the window chrome is the other), a RAIL derived from what the
// directory actually holds — kinds, labels, cities, the hidden shelf — a list, and a CARD that looks like a
// contact card: every basic field present even when empty, several phones and e-mails each with its label,
// and «how to reach this person» as a block of its own. The provider icons in the bar are the PLATFORM
// FILTER. Self-contained: scoped styles, plain DOM, no innerHTML on data, no network, no polling.

import { renderDetail } from "./js/detail.js";
import { renderList } from "./js/list.js";
import { renderRail } from "./js/rail.js";
import { ICO_PLUG, bindI18n, el2, hooks, svgEl, tt } from "./js/shared.js";
import { CSS } from "./js/style.js";
import { renderConnectors, renderProviderIcons } from "./js/sync.js";

hooks.render = render;      // the parts re-render the whole card through this (see js/shared.js)

function injectStyles(){
  if(document.getElementById("hb-contactos-css"))return;
  const s=document.createElement("style"); s.id="hb-contactos-css"; s.textContent=CSS; document.head.appendChild(s);
}

export function render(el, data, ctx){
  bindI18n(ctx);
  injectStyles();

  // A VIEW PUSHED FROM VOICE (`show_view` / `show_contact` / `show_sources`). Applied only when its
  // token MOVES — a plain data refresh never yanks what the operator is reading, but asking twice for the
  // same filter still lands, because the token is a counter and not the filter itself (V2-540).
  const pushed=data.view;
  if(pushed && pushed.n!==el._ctViewN){
    el._ctViewN=pushed.n;
    const sel=pushed.sel||{};
    if(sel.screen==="sources"){ el._ctScreen="conn"; el._ctDetail=null; }
    else if(sel.contactId){ el._ctDetail=sel.contactId; el._ctScreen=null; }
    else{
      // ⚠️ `kind` and `source` were pushed by `show_view` and DROPPED here until V2-715: «enséñame mis
      // empresas» filtered the spoken answer and left the card showing everything, which is the pair of
      // disagreeing surfaces this widget's own digest exists to prevent.
      el._ctDetail=null; el._ctScreen=null; el._ctShown=0;
      el._ctSource=sel.source||"";
      el._ctQuery=sel.query||"";
      const f={};
      if(sel.hidden) f.hidden=true;
      if(sel.favorites) f.fav=true;
      if(sel.kind) f.kind=String(sel.kind);
      if(sel.group) f.group=String(sel.group);
      if(sel.city) f.city=String(sel.city);
      if(sel.flag) f.flag=String(sel.flag);
      el._ctFilter=f;
    }
  }

  el.className="hb-contactos";
  el.textContent="";                                          // reset (no innerHTML)

  const contacts=data.contacts||[];
  const redraw=nd=>render(el,(nd&&nd.contacts)?nd:data,ctx);

  // ── THE ONE BAR — search, the sources, and the door to them ───────────────────────────────────────────
  const bar=el2("div","ctbar");
  const sb=el2("div","ctsearch");
  sb.appendChild(el2("span",null,"\u{1F50D}"));
  const q=document.createElement("input");
  q.placeholder=tt("search_ph", null, "Buscar…");
  q.value=el._ctQuery||"";
  q.oninput=()=>{ el._ctQuery=q.value; const keep=q.value; el._ctScreen=null; el._ctShown=0;
    render(el,data,ctx);
    const nq=el.querySelector(".ctsearch input");
    if(nq){ nq.focus(); nq.setSelectionRange(keep.length,keep.length); } };
  sb.appendChild(q);
  bar.appendChild(sb);
  const right=el2("div","ctviewsright");
  right.appendChild(renderProviderIcons(data.providers||[], el, data, ctx));
  const connBtn=el2("button","ctplug"+(el._ctScreen?" on":""));
  connBtn.appendChild(svgEl(ICO_PLUG));
  connBtn.title=tt("sources_hint", null, "De dónde vienen tus contactos y su sincronización");
  connBtn.setAttribute("aria-label", tt("sources_title", null, "Fuentes y sincronización"));
  connBtn.onclick=()=>{ el._ctScreen = el._ctScreen ? null : "conn"; el._ctDetail=null; render(el,data,ctx); };
  right.appendChild(connBtn);
  bar.appendChild(right);
  el.appendChild(bar);

  if(el._ctScreen === "conn"){
    renderConnectors(el, el, data, ctx);
    return;
  }

  const cols=el2("div","ctcols");
  cols.appendChild(renderRail(el, data, ctx));

  const main=el2("div","ctmain");
  const detail=el._ctDetail
    ? (contacts.find(c=>c.id===el._ctDetail) || (data.hidden_rows||[]).find(c=>c.id===el._ctDetail))
    : null;
  cols.classList.toggle("detail", !!detail);

  if(!contacts.length && !(data.hidden_rows||[]).length){
    main.appendChild(el2("div","ctempty",
      tt("empty_1", null, "El directorio está vacío. Dile a Zaelar: «apúntame el restaurante Elfo On de Soria como favorito» ")+
      tt("empty_2", null, "o «añade a Marta, amiga del trabajo».")));
  } else if(detail){
    renderDetail(el,main,data,ctx,detail);
  } else {
    renderList(el, main, data, ctx);
  }

  cols.appendChild(main);
  el.appendChild(cols);

  // A failed action says so where the gesture happened, instead of leaving the card looking unchanged.
  if(data.ok===false && data.error){
    const w=el2("div","ctnote",tt("action_failed", null, "No se ha podido hacer")); w.style.color="var(--hb-danger,#D9534F)";
    w.title=String(data.error);
    el.appendChild(w);
  }
}
