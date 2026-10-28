// Contacts widget — what every part of the card shares: the channel and kind tables, the provider marks, the
// filter predicates, the avatar, the i18n seam and the hook back to `render` (refactor2710-12 T-03).

// The entry's `render`, set by `widget.js` when it loads: every part re-renders the whole card from its root, and
// a part cannot import the entry back.
export const hooks = {render: null};

export const KICON = {person: "\u{1F464}", place: "\u{1F4CD}", company: "\u{1F3E2}"};

// ── The three channels a contact can carry, and the ORDER the card lists them in ─────────────────────────
// Mirrors `widgets/directory.py::PLATFORMS`. It is a fixed list on purpose: a card that only drew the
// channels a contact HAS is the card this replaced — the operator could not tell «no tengo su WhatsApp»
// from «esta ficha no enseña WhatsApp», which is exactly what he reported («no muestra ni siquiera los
// campos básicos, aunque sean vacíos»).
export const CHANNELS = [
  {id: "telegram", icon: "✈", label: "Telegram"},
  {id: "whatsapp", icon: "✆", label: "WhatsApp"},
  {id: "email",    icon: "✉", label: "Email"},
];

// ── The HOUSE HEADER (V2-699) — the same two bars every widget with a connector wears ────────────────────
// Operator, 2026-09-15: «esto es un sistema operativo, con lo cual esas barras ya tienen un formato estándar
// y nos llevan al sistema de conectores». The contract is written up in
// `.meshkore/docs/conventions/zaelar-widget-header-standard.md`; the shape copied here is the agenda's
// (V2-679), which copied messaging's. Icons, class names and behaviour are deliberately one-for-one.
export const SVG_NS = "http://www.w3.org/2000/svg";

export function svgEl(paths, opts){
  const svg=document.createElementNS(SVG_NS,"svg");
  svg.setAttribute("viewBox","0 0 24 24"); svg.setAttribute("aria-hidden","true");
  svg.setAttribute("fill", (opts&&opts.fill) || "none");
  if(!(opts&&opts.fill)){ svg.setAttribute("stroke","currentColor"); svg.setAttribute("stroke-width","2");
    svg.setAttribute("stroke-linecap","round"); svg.setAttribute("stroke-linejoin","round"); }
  else { svg.setAttribute("fill","currentColor"); }
  (Array.isArray(paths)?paths:[paths]).forEach(d=>{
    const p=document.createElementNS(SVG_NS,"path"); p.setAttribute("d",d); svg.appendChild(p);
  });
  return svg;
}

export const ICO_PEOPLE = ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2","M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
                    "M22 21v-2a4 4 0 0 0-3-3.87","M16 3.13a4 4 0 0 1 0 7.75"];
export const ICO_PLUG   = ["M9 2v6","M15 2v6","M6 8h12v3a6 6 0 0 1-12 0z","M12 17v5"];
export const ICO_SYNC   = ["M21 2v6h-6","M3 12a9 9 0 0 1 15-6.7L21 8","M3 22v-6h6","M21 12a9 9 0 0 1-15 6.7L3 16"];

// The provider marks. Same source as the agenda's `CAL_SVG` so Google looks like Google in both.
export const SRC_SVG = {
  "google-contacts": {color:"#4285F4", path:"M12.545 10.239v3.821h5.445c-.712 2.315-2.647 3.972-5.445 3.972a6.033 6.033 0 1 1 0-12.064c1.498 0 2.866.549 3.921 1.453l2.814-2.814A9.969 9.969 0 0 0 12.545 2C7.021 2 2.543 6.477 2.543 12s4.478 10 10.002 10c8.396 0 10.249-7.85 9.426-11.748l-9.426-.013z"},
  icloud: {color:"#3693F3", path:"M13.762 4.29a6.51 6.51 0 0 0-5.669 3.332 3.571 3.571 0 0 0-1.558-.36 3.571 3.571 0 0 0-3.516 3A4.918 4.918 0 0 0 0 14.796a4.918 4.918 0 0 0 4.92 4.914 4.93 4.93 0 0 0 .617-.045h14.42c2.305-.272 4.041-2.258 4.043-4.589v-.009a4.594 4.594 0 0 0-3.727-4.508 6.51 6.51 0 0 0-6.511-6.27z"},
  carddav: {color:"var(--hb-muted,#6b7b92)", path:"M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm-9 4a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5zm4.5 9h-9v-.75c0-1.5 3-2.32 4.5-2.32s4.5.82 4.5 2.32V17z"},
  // V2-714 — «en el widget de contactos quiero que aparezcan los iconos de WhatsApp y de Telegram y que se
  // vea si están conectados o no». They are message connectors AND contact sources now, and the same
  // connector deliberately lives in both cards: «eso le da claridad al asunto».
  telegram: {color:"#26A5E4", path:"M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"},
  whatsapp: {color:"#25D366", path:"M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51a12.8 12.8 0 0 0-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413Z"},
  meshkore: {color:"var(--hb-accent,#4f7cff)", path:"M12 2a3 3 0 0 1 1 5.83V10h4a3 3 0 0 1 3 3v1.17a3 3 0 1 1-2 0V13a1 1 0 0 0-1-1h-4v2.17a3 3 0 1 1-2 0V12H7a1 1 0 0 0-1 1v1.17a3 3 0 1 1-2 0V13a3 3 0 0 1 3-3h4V7.83A3 3 0 0 1 12 2z"},
};

//: The only source with a connector behind it today. Everything else stays VISIBLE but INERT — no button,
//: no click handler — until it lands in `connectors/contacts/providers.py`. «No lo has enlazado» and «no lo
//: hemos construido» are different sentences and the strip has to be able to say both.
export const LIVE_SOURCES = {"google-contacts": true, telegram: true, whatsapp: true, meshkore: true};

//: Sources that IMPORT (V2-714). They carry one switch, not two: «no vamos a poner dos opciones… un botón
//: de sincronizar que se queda activado». The switch brings contacts AND groups in the same pass, and the
//: server refuses it when the connector is not linked, so the card never promises what it cannot do.
export const IMPORT_SOURCES = {telegram: true, whatsapp: true, meshkore: true};
export function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=text; return e; }

export function normJs(s){ return String(s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"")
  .replace(/\s+/g," ").trim().toLowerCase(); }

// Loose group match, BOTH directions («fontanero» ↔ «fontaneros») — mirrors data.py's `_group_matches`.
export function groupMatch(want, c){
  const w=normJs(want); if(!w) return true;
  return (c.groups||[]).some(g=>{const gn=normJs(g); return gn.includes(w)||w.includes(gn);});
}

// ── Reachability, mirroring `widgets/directory.py` — INCLUDING its one asymmetry ─────────────────────────
// A stored `email` IS an email channel: the address is the whole capability. A stored `phone` is NOT a
// WhatsApp channel — having somebody's number is not proof they use WhatsApp. Painting a green WhatsApp row
// off `c.phone` would make the card claim a reachability the sending door refuses, which is the worst kind
// of disagreement between two surfaces of the same fact.
export function channelOf(c, id){
  const row=(c.channels||[]).find(ch=>String(ch.platform||"")===id);
  if(row && (row.handle || row.chatId)) return {handle:String(row.handle||""), chatId:String(row.chatId||""), stored:true};
  if(id==="email" && c.email) return {handle:String(c.email), chatId:"", stored:false};
  return null;
}

export function preferredLine(c){
  const p=String(c.preferred||"");
  const order=p ? [p].concat(CHANNELS.map(x=>x.id).filter(x=>x!==p)) : CHANNELS.map(x=>x.id);
  for(const id of order){ const ch=channelOf(c,id); if(ch && ch.handle) return ch.handle; }
  return "";
}

// A stable colour per contact so the same face keeps the same disc across renders and reorders.
export function avatarHue(s){ let h=0; const t=String(s||"?");
  for(let i=0;i<t.length;i++) h=(h*31+t.charCodeAt(i))>>>0;
  return h%360; }

export function avatar(c, big){
  const nm=String(c.name||c.id||"?").trim();
  const a=el2("div","ctav"+(big?" big":""), (nm[0]||"?").toUpperCase());
  a.style.background="hsl("+avatarHue(nm)+",42%,42%)";   // L=42% keeps white text above the 4.5:1 floor
  return a;
}

// ── WHICH CONTACTS ARE ON SCREEN (V2-715) ───────────────────────────────────────────────────────────────
// Two independent axes, and they are independent on purpose: the RAIL picks ONE thing to look at (all,
// favourites, a kind, a label, a city, the hidden ones), and the PLATFORM narrows whatever that is. His
// own words for the second one: «cuando entramos en Telegram quiero ver solo los contactos de Telegram».
// A mirror of `model.py::matches` / `model.py::source_matches`, marked as such — this one is the same
// decision made client-side over a directory the card already holds whole, and the two must never drift.
export const KIND_ORDER = ["person", "company", "place", "group", "agent"];

export function kindOf(c){ const k=String(c.kind||"person"); return KIND_ORDER.indexOf(k)<0 ? "person" : k; }

export function srcKey(v){
  const n=normJs(v);
  return ({"google-contacts":"google","google contacts":"google","googlecontacts":"google","gmail":"google",
           "google-people":"google","apple":"icloud"})[n] || n;
}

// Mirrors `model.source_matches`: where the row CAME FROM and where he can REACH the person. A contact he
// typed here and later matched to a Telegram account is as much a Telegram contact as an imported one.
export function sourceMatch(c, source){
  const s=srcKey(source);
  if(!s) return true;
  if(srcKey(c.source)===s || srcKey(c.platform)===s) return true;
  for(const k in (c.externalIds||{})) if(srcKey(k)===s) return true;
  if(s==="google" && String(c.googleId||"").trim()) return true;
  return (c.channels||[]).some(ch=>srcKey(ch.platform)===s);
}

export function cityMatch(want, c){
  const cw=normJs(want), cn=normJs(c.city);
  return cw ? (cn.includes(cw)||(!!cn&&cw.includes(cn))) : true;
}

export function detailValues(c, key){
  const rows=(c[key]||[]).map(r=>String((r&&r.value)||"")).filter(Boolean);
  const head=String((key==="phones"?c.phone:c.email)||"").trim();
  return rows.length ? rows : (head?[head]:[]);
}

export function haystack(c){
  return normJs([c.name,c.city,c.address,c.notes,(c.groups||[]).join(" "),
    detailValues(c,"phones").join(" "), detailValues(c,"emails").join(" "),
    (c.channels||[]).map(ch=>ch.handle||"").join(" ")].join(" "));
}

// ── THE FILTER: every axis at once, because the VOICE can set several ───────────────────────────────────
// A click on the rail means «show me THIS», so it sets one axis and clears the others. A pushed
// `show_view` does not: «mi restaurante favorito en Barcelona» is group + city + favourites in one
// sentence, and the spoken answer is already computed over all three. A card that could hold only one
// would show a different set from the one it had just read out — the two-surfaces-disagreeing failure
// this widget's own digest exists to stop (V2-576). Measured: a single-axis rail broke exactly that case.
export const AXES = ["fav", "hidden", "kind", "group", "city", "flag"];

// A flag's label: «closed» is a state of the entry, said in the operator's language (bundle `flag_<id>`).
export function flagLabel(f){ return tt("flag_"+f, null, String(f)); }

export function selOf(el){ return el._ctFilter || {}; }

export function selEmpty(f){ return !AXES.some(a=>f && f[a]); }

export function bySel(list, f){
  if(!f) return list;
  let out = list;
  if(f.fav) out = out.filter(c=>c.favorite);
  if(f.kind) out = out.filter(c=>kindOf(c)===f.kind);
  if(f.group) out = out.filter(c=>groupMatch(f.group,c));
  if(f.city) out = out.filter(c=>cityMatch(f.city,c));
  if(f.flag) out = out.filter(c=>(c.flags||[]).includes(f.flag));     // closed | blocked | vip (model.FLAGS)
  return out;                                    // `hidden` chooses the POOL, not a predicate — see basePool
}

// The pool the RAIL counts over: everything the platform filter allows. Counting over the whole archive
// instead would paint a rail whose numbers disagree with what a click on it actually shows.
export function basePool(data, el){
  const hidden = !!selOf(el).hidden;
  const list = (hidden ? (data.hidden_rows||[]) : (data.contacts||[])).slice();
  const src = el._ctSource||"";
  return src ? list.filter(c=>sourceMatch(c,src)) : list;
}

export function rowsOf(data, el){
  let out = bySel(basePool(data,el), selOf(el));
  const q = normJs(el._ctQuery||"");
  if(q) out = out.filter(c=>haystack(c).includes(q));
  out.sort((a,b)=>(a.favorite===b.favorite ? (normJs(a.name)<normJs(b.name)?-1:1) : (a.favorite?-1:1)));
  return out;
}

export function favBtn(c, ctx, el, data){
  const b=el2("button","ctfav"+(c.favorite?" on":""),"★");
  b.title=c.favorite?tt("unfav", null, "Quitar de favoritos"):tt("fav", null, "Marcar como favorito");
  b.onclick=async(ev)=>{ ev.stopPropagation();
    const nd=await ctx.action("set_favorite",{contactId:c.id,favorite:!c.favorite});
    hooks.render(el,(nd&&nd.contacts)?nd:data,ctx); };
  return b;
}

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
let _T = null;
export let _LANG = "en";   // instance language (ctx.lang) — dates never follow the browser locale

// Bound once per render, here: an imported binding is read-only, so the module that declares them is the one
// that writes them.
export function bindI18n(ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  _LANG = (ctx && ctx.lang) || "en";
}
export function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.contactos."+key, params); if(s && s!=="widgets.contactos."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}

// A FUNCTION, not the module-level map it replaces: a table built at IMPORT time freezes its labels in
// whatever language was active when the module first loaded, and survives every later switch (V2-694).
export function kindLabel(kind){
  switch(String(kind || "")){
    case "person":  return tt("kind_person", null, "persona");
    case "place":   return tt("kind_place", null, "sitio");
    case "company": return tt("kind_company", null, "empresa");
    case "group":   return tt("kind_group", null, "grupo");
    case "agent":   return tt("kind_agent", null, "agente");
    default:        return "";
  }
}

// The RAIL says them in the plural, because a rail row is a set and not an example.
export function kindPlural(kind){
  switch(String(kind || "")){
    case "person":  return tt("kind_people", null, "Personas");
    case "place":   return tt("kind_places", null, "Sitios");
    case "company": return tt("kind_companies", null, "Empresas");
    case "group":   return tt("kind_groups", null, "Grupos");
    case "agent":   return tt("kind_agents", null, "Agentes");
    default:        return "";
  }
}
