// Contacts widget — the left rail and the filter crumb (refactor2710-12 T-03).
import { KICON, KIND_ORDER, basePool, el2, flagLabel, hooks, kindOf, kindPlural, normJs, selEmpty,
  selOf, srcKey, tt } from "./shared.js";

// ── THE RAIL — the directory's own map, derived from what it holds (V2-715) ─────────────────────────────
// The operator, 2026-09-17: «en la barra lateral de la izquierda es donde vayamos a desarrollar de forma
// dinámica todo lo que tenemos», and about the four fixed tabs that used to sit on top: «un contacto nunca
// va a ser un lugar, con lo cual eso no tiene ningún sentido ahí».
//
// So nothing here is a fixed word. Every section is TALLIED from the rows on screen and a section with
// nothing in it is not drawn — a directory of 2 688 people and no places never shows «Sitios (0)», and a
// directory that grows its first cluster grows a «Grupos» row the same day. The counts are tallied over
// the platform-filtered pool, so a number in the rail is a promise about what a click on it will show.
export function railSection(side, label){
  side.appendChild(el2("div","ctsep"));
  side.appendChild(el2("div","ctsidelbl", label));
}

export function tally(list, keyOf){
  const out = {};
  list.forEach(c=>{
    (keyOf(c)||[]).forEach(k=>{
      const n = normJs(k);
      if(!n) return;
      const e = out[n] || (out[n] = {id: k, count: 0});
      e.count++;
    });
  });
  return Object.values(out).sort((a,b)=> b.count - a.count || (normJs(a.id) < normJs(b.id) ? -1 : 1));
}

//: How many labels / cities the rail shows before it offers the rest. A Google address book brings its own
//: contact groups, so this list is long in real life and an unbounded rail would push «+ Nuevo contacto»
//: off the bottom of every card.
export const RAIL_PAGE = 10;

export function renderRail(el, data, ctx){
  const side = el2("div","ctside");
  const sel = selOf(el);
  const pool = basePool(data, el);
  const hiddenN = (data.hidden_rows||[]).length;

  const row = (axis, value, label, count, icon)=>{
    const on = axis==="all" ? selEmpty(sel)
             : (axis==="fav"||axis==="hidden") ? !!sel[axis]
             : String(sel[axis]||"")===String(value||"");
    const b = el2("button","ctg"+(on?" on":""));
    if(icon) b.append(el2("span","ctgi", icon));
    b.append(el2("span",null,label));
    if(count!=null) b.append(el2("span","ctgc",String(count)));
    // A CLICK means «show me this one thing», so it replaces the whole filter. Several axes at once is
    // something only a sentence can ask for, and the pushed view is where that arrives.
    b.onclick = ()=>{ el._ctFilter = axis==="all" ? {}
                    : (axis==="fav"||axis==="hidden") ? {[axis]: true} : {[axis]: value};
                      el._ctDetail=null; el._ctScreen=null; el._ctShown=0; hooks.render(el,data,ctx); };
    side.appendChild(b);
    return b;
  };

  // The count he asked for, where he asked for it: «con poner entre paréntesis al lado de las letras ALL
  // el número de contactos, todo el mundo lo entiende de la misma manera».
  row("all", "", tt("all", null, "Todos"),
      selOf(el).hidden ? (data.contacts||[]).length : pool.length);
  const favs = pool.filter(c=>c.favorite).length;
  row("fav", "", tt("favs", null, "★ Favoritos"), favs);

  const kinds = KIND_ORDER.map(k=>({k, n: pool.filter(c=>kindOf(c)===k).length})).filter(x=>x.n>0);
  // ONE kind present is not a classification, it is the whole directory said twice.
  if(kinds.length > 1){
    railSection(side, tt("side_kinds", null, "Tipos"));
    kinds.forEach(x=>row("kind", x.k, kindPlural(x.k), x.n, KICON[x.k]||""));
  }

  const labels = tally(pool, c=>c.groups||[]);
  if(labels.length){
    railSection(side, tt("side_groups", null, "Etiquetas"));
    const open = !!el._ctAllGroups;
    (open ? labels : labels.slice(0, RAIL_PAGE)).forEach(g=>row("group", g.id, g.id, g.count));
    if(labels.length > RAIL_PAGE){
      const more = el2("button","ctgmore", open ? tt("rail_less", null, "ver menos")
        : tt("rail_more", {n: labels.length - RAIL_PAGE}, "ver " + (labels.length - RAIL_PAGE) + " más"));
      more.onclick = ()=>{ el._ctAllGroups = !open; hooks.render(el,data,ctx); };
      side.appendChild(more);
    }
  }

  const cities = tally(pool, c=>[String(c.city||"").trim()].filter(Boolean));
  if(cities.length){
    railSection(side, tt("side_cities", null, "Ciudades"));
    const open = !!el._ctAllCities;
    (open ? cities : cities.slice(0, RAIL_PAGE)).forEach(g=>row("city", g.id, g.id, g.count));
    if(cities.length > RAIL_PAGE){
      const more = el2("button","ctgmore", open ? tt("rail_less", null, "ver menos")
        : tt("rail_more", {n: cities.length - RAIL_PAGE}, "ver " + (cities.length - RAIL_PAGE) + " más"));
      more.onclick = ()=>{ el._ctAllCities = !open; hooks.render(el,data,ctx); };
      side.appendChild(more);
    }
  }

  // HIDDEN — the rows he took off the directory. They were unreachable from the card until now, and a
  // «quítalo de la lista» that cannot be undone from the same card is a delete wearing a softer word.
  if(hiddenN){
    railSection(side, tt("side_hidden", null, "Ocultos"));
    row("hidden", "", tt("hidden_rows", null, "Ocultos"), hiddenN, "◌");
  }

  side.appendChild(el2("div","ctsep"));
  const addB = el2("button","ctact","+ "+tt("new_contact", null, "Nuevo contacto"));
  addB.onclick = ()=>{
    const inp=document.createElement("input"); inp.className="ctin";
    inp.placeholder=tt("new_name_ph", null, "nombre…");
    let done=false;
    const fin=async(save)=>{ if(done)return; done=true;
      const t=String(inp.value||"").trim();
      if(save && t){ const nd=await ctx.action("add_contact",{name:t});
                     hooks.render(el,(nd&&nd.contacts)?nd:data,ctx); }
      else hooks.render(el,data,ctx); };
    inp.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();fin(true);}
                       else if(e.key==="Escape"){e.preventDefault();fin(false);} };
    inp.onblur=()=>fin(true);
    addB.replaceWith(inp); inp.focus();
  };
  side.appendChild(addB);
  // NO import button here. It lived in this rail for one build and the operator had it removed: importing
  // is a CONNECTOR gesture, and in this product every connector gesture is reached the same way — the plug
  // button in the bar. A second door to it would be a second place to keep in sync.
  return side;
}

// ── WHAT IS BEING FILTERED RIGHT NOW, and how to drop it ────────────────────────────────────────────────
// Two of the three filters live somewhere the eye can miss (an icon in the bar, a row in a rail that
// scrolls), and a list showing 412 of 2 688 rows with no visible reason is indistinguishable from a
// directory that lost them. Each chip REMOVES its own filter, so the way out is where the surprise is.
export function renderCrumb(el, data, ctx, shown, total){
  const bar = el2("div","ctcrumb");
  const sel = selOf(el);
  const chip = (label, clear)=>{
    const b = el2("button","ctcx");
    b.append(el2("span",null,label));
    b.append(el2("span",null,"✕"));
    b.title = tt("crumb_clear", null, "quitar este filtro");
    b.onclick = ()=>{ clear(); el._ctDetail=null; el._ctShown=0; hooks.render(el,data,ctx); };
    bar.appendChild(b);
  };
  if(el._ctSource){
    const p = (data.providers||[]).find(x=>srcKey(x.id)===srcKey(el._ctSource));
    chip((p && p.label) || el._ctSource, ()=>{ el._ctSource=""; });
  }
  const drop=(axis)=>()=>{ const f={...selOf(el)}; delete f[axis]; el._ctFilter=f; };
  if(sel.hidden) chip(tt("hidden_rows", null, "Ocultos"), drop("hidden"));
  if(sel.fav) chip(tt("favs", null, "★ Favoritos"), drop("fav"));
  if(sel.kind) chip(kindPlural(sel.kind), drop("kind"));
  if(sel.group) chip(String(sel.group), drop("group"));
  if(sel.city) chip(String(sel.city), drop("city"));
  if(sel.flag) chip(flagLabel(sel.flag), drop("flag"));
  if(el._ctQuery) chip("“"+String(el._ctQuery)+"”", ()=>{ el._ctQuery=""; });
  bar.appendChild(el2("span","ctcount", shown < total
    ? tt("shown_of", {n: shown, total: total}, shown + " de " + total)
    : tt("shown_n", {n: total}, String(total))));
  return bar;
}
