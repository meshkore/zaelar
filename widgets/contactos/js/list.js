// Contacts widget — the LIST of contacts the rail and the search leave on screen (refactor2710-12 T-03).
import { renderCrumb } from "./rail.js";
import { avatar, detailValues, el2, favBtn, flagLabel, hooks, kindLabel, kindOf, preferredLine, rowsOf, selEmpty,
  selOf, tt } from "./shared.js";

//: How many rows are painted before «ver más». His own directory holds 2 688 and every one of them used to
//: become a DOM node on every keystroke of the search box.
export const PAGE = 120;

// `main` is the column the rows are appended to; `el` stays the widget root, where the filter state lives.
export function renderList(el, main, data, ctx){
  const sel=selOf(el);
  const rows=rowsOf(data, el);
  const shown=Math.min(rows.length, Math.max(PAGE, el._ctShown||0));
  const filtering = !!(el._ctSource || el._ctQuery) || !selEmpty(sel);
  if(filtering || rows.length>PAGE) main.appendChild(renderCrumb(el, data, ctx, shown, rows.length));
  if(sel.hidden){
    main.appendChild(el2("div","ctnote", tt("hidden_hint", null,
      "Ocultos: no salen en el directorio y la siguiente importación NO los vuelve a traer. "
      + "Pulsa ◌ en su ficha para devolverlos.")));
  }

  const list=el2("div","ctlist");
  if(!rows.length){
    list.appendChild(el2("div","ctempty",tt("no_match", null, "Nada que casar con ese filtro.")));
  }
  rows.slice(0, shown).forEach(c=>{
    const r=el2("div","ctrow");
    r.appendChild(avatar(c,false));
    const tx=el2("div","ctrtx");
    tx.appendChild(el2("span","ctnm",c.name||c.id));
    const sub=preferredLine(c) || detailValues(c,"phones")[0] || "";
    if(sub) tx.appendChild(el2("span","ctsub",sub));
    r.appendChild(tx);
    if(c.city)r.appendChild(el2("span","ctci",c.city));
    const gs=el2("span","ctgs");
    // The KIND on the row, but only when it is not the obvious one: a directory of people that labelled
    // every row «persona» would be spending its only free strip on a word that says nothing.
    if(kindOf(c)!=="person") gs.appendChild(el2("span","ctpill",kindLabel(kindOf(c))));
    (c.flags||[]).forEach(x=>gs.appendChild(el2("span","ctpill ctflag",flagLabel(x))));   // a STATE, before labels
    (c.groups||[]).slice(0,2).forEach(g=>gs.appendChild(el2("span","ctpill",g)));
    r.appendChild(gs);
    r.appendChild(favBtn(c,ctx,el,data));
    r.onclick=()=>{ el._ctDetail=c.id; hooks.render(el,data,ctx); };
    list.appendChild(r);
  });
  main.appendChild(list);
  if(rows.length>shown){
    const more=el2("button","ctmore",
      tt("rows_more", {n: rows.length-shown}, "Ver más (" + (rows.length-shown) + ")"));
    more.onclick=()=>{ el._ctShown=shown+PAGE; hooks.render(el,data,ctx); };
    main.appendChild(more);
  }
}
