// results widget — small painted pieces: the identity strip, photos, chips, links, and WHICH list layout.
// Moved verbatim out of widget.js (refactor2710-12); widget.js stays the entry exporting `render`.

import { elem, tt } from "./shared.js";

// ── installation and session identifiers ─────────────────────────────────────────────────────────────────────
// They RIDE THE PAYLOAD now (`data.identity`, filled by data.py): the widget contract bans network in widget.js,
// and this fetch was the violation that kept `make test-widgets` permanently red — under which a NEW violation in
// any widget was invisible (V2-601 T-10). Same visible behavior: no identity → the strip removes itself.

export function shortId(id){
  id = String(id||"");
  return id.length > 13 ? id.slice(0,8) + "…" : (id || "—");
}

// Identity strip: User · Session · Copy (bottom of the Summary tab since V2-538). The button copies BOTH FULL ids, in a format a code agent understands at a
// glance. It is painted immediately (with "...") and filled when fetch returns; if there is no identity (endpoint
// down), the strip removes itself instead of leaving an empty gap.
export function identityStrip(id){
  id = (id && (id.user_id || id.session_id)) ? id : null;
  if(!id) return document.createDocumentFragment();     // no identity in the payload → no strip (as before)
  const strip = elem("div","hr-ident");
  const uBit = elem("span","hr-idbit"); const uCode = elem("code","","…"); uBit.append(elem("b","",tt("user", null, "Usuario")), uCode);
  const sBit = elem("span","hr-idbit"); const sCode = elem("code","","…"); sBit.append(elem("b","",tt("session", null, "Sesión")), sCode);
  const btn = elem("button","hr-idcopy",tt("copy", null, "⧉ Copiar")); btn.type = "button"; btn.disabled = true;
  strip.append(uBit, sBit, btn);
  {
    uCode.textContent = shortId(id.user_id);  uBit.title = tt("user_", null, "Usuario: ") + (id.user_id || "—");
    sCode.textContent = shortId(id.session_id); sBit.title = tt("session_", null, "Sesión: ") + (id.session_id || "—");
    btn.disabled = false;
    let reset = null;
    btn.addEventListener("click", async () => {
      const text = `user_id: ${id.user_id||""}\nsession_id: ${id.session_id||""}`;
      let ok = true;
      try{ await navigator.clipboard.writeText(text); }
      catch(_){                                    // no Clipboard API (insecure context) → textarea + execCommand
        try{
          const ta = document.createElement("textarea");
          ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
          document.body.appendChild(ta); ta.focus(); ta.select();
          ok = document.execCommand("copy"); ta.remove();
        }catch(__){ ok = false; }
      }
      btn.textContent = ok ? tt("copied", null, "✓ Copiado") : tt("copy_failed", null, "No se pudo copiar");
      btn.classList.toggle("ok", ok);
      if(reset) clearTimeout(reset);
      reset = setTimeout(() => { btn.textContent = tt("copy", null, "⧉ Copiar"); btn.classList.remove("ok"); }, 1800);
    });
  }
  return strip;
}

export function photo(url, alt, cls){
  const img=document.createElement("img"); img.className=cls||"";
  img.src=url; img.alt=alt||""; img.loading="lazy"; img.referrerPolicy="no-referrer";
  img.addEventListener("error",()=>img.remove());   // dead photo link → drop silently, never break the card
  return img;
}

// A photo inside a PLATE of fixed aspect. The plate is what holds the geometry (so a portrait bottle and a
// landscape car both get the same tile and the grid stays a grid) and the image is CONTAINED inside it, so
// nothing is ever cropped. A dead photo empties the plate rather than collapsing the card's layout — which is
// why the plate keeps its size: a row where one tile vanished reflows every sibling.
export function photoPlate(url, alt){
  const box=elem("div","hr-shot");
  if(!url){ box.classList.add("none"); box.appendChild(monogram(alt)); return box; }
  const img=photo(url, alt, "");
  // V2-797 — a dead photo keeps its plate AND says what it is: an empty light box read as a broken card.
  img.addEventListener("error",()=>{ box.classList.add("none"); if(!box.querySelector(".hr-mono")) box.appendChild(monogram(alt)); });
  box.appendChild(img);
  return box;
}

// The first letter or digit of a name, as the stand-in for its missing photo. Any script: \p{L} / \p{N}.
export function monogram(name){
  const m = String(name||"").match(/[\p{L}\p{N}]/u);
  const e = elem("span","hr-mono", m ? m[0].toLocaleUpperCase() : "·");
  e.setAttribute("aria-hidden","true");
  return e;
}

// The chips a LIST card shows under its title: what the item DECLARES as `meta`, else its first three facts.
export function metaChips(it){
  const pairs = (v) => Array.isArray(v) ? v.map(c => (c && typeof c === "object") ? c : {value: c})
                    : (v && typeof v === "object") ? Object.entries(v).map(([label, value]) => ({label, value})) : [];
  const own = pairs(it.meta);
  const meta = own.length ? own : pairs(it.facts).slice(0, 3);
  return meta.filter(c => c && c.value != null && String(c.value).trim()).slice(0, 4).map(c => {
    const chip = elem("span","hr-chip");
    if(c.label){ chip.appendChild(elem("small","", c.label)); }
    chip.appendChild(document.createTextNode(String(c.value)));
    chip.title = (c.label ? c.label + ": " : "") + String(c.value);
    return chip;
  });
}

// Text clamped to its lines, with «Ver todo» offered ONLY when something was really cut — measured on screen,
// because only the screen knows how wide the card is (V2-797). The hover title carries the whole text too.
export function expandable(card, txt){
  const xb=elem("button","hr-xbtn", tt("show_more", null, "Ver todo")); xb.type="button";
  xb.setAttribute("aria-expanded","false");
  txt.appendChild(xb);
  const measure=()=>{
    if(card.classList.contains("hr-x")) return;
    const cut=[...txt.querySelectorAll(".hr-cl")].some(c=>c.scrollHeight > c.clientHeight + 1);
    txt.classList.toggle("can-x", cut);
  };
  if(typeof ResizeObserver === "function") new ResizeObserver(measure).observe(txt);
  else if(typeof requestAnimationFrame === "function") requestAnimationFrame(measure);
  xb.addEventListener("click", e=>{ e.preventDefault(); e.stopPropagation();
    const on=card.classList.toggle("hr-x");
    xb.textContent = on ? tt("show_less", null, "Ver menos") : tt("show_more", null, "Ver todo");
    xb.setAttribute("aria-expanded", String(on));
    if(!on) measure();
  });
}

// The SITE a link lands on, which is what the operator is deciding about when he clicks. A raw url is not an
// answer to "where does this take me": `amazon.es` is.
export function hostOf(url){
  try{ return new URL(String(url), "https://x.invalid").hostname.replace(/^www\./, ""); }
  catch(_){ return ""; }
}

// The link to the ORIGINAL page, as a labelled control. `stopPropagation` because a card can be CHOOSABLE:
// without it, opening the shop would also silently pick the result.
export function sourceLink(url, {wide=false}={}){
  const u=String(url||""); if(!u) return null;
  const host=hostOf(u);
  const a=elem("a","hr-open"+(wide?" wide":""),
               host ? tt("view_on", {site: host}, "Ver en " + host) : tt("view_source", null, "Ver la ficha original"));
  a.href=u; a.target="_blank"; a.rel="noopener noreferrer";
  a.title = tt("open_original", null, "Abrir la ficha original en una pestaña nueva") + " — " + u;
  a.addEventListener("click", e=>e.stopPropagation());
  return a;
}

// ── WHICH of the four list layouts ──────────────────────────────────────────────────────────────────────────
// The surface decides, from the SHAPE of what it was given — `widgets/presentation.py` rule 1, which exists
// because a guessed `columns:2` from outside once left three rich cards with an orphan. The sheet may declare
// WHAT KIND OF THING it found (`kind`), which is content, not layout: saying "these are products" is a fact
// about the results; saying "draw them in two columns" is a decision that belongs here.
export const LAYOUTS = ["split", "gallery", "rows", "compare"];

// ── THE TEMPLATES THE WORKER MAY ASK FOR (V2-703) ───────────────────────────────────────────────────────────
// «tenemos varias que le ofrecemos al Brainworker para que elija la más adecuada para cada lista de resultados».
//
// This REVERSES presentation.py's rule 1 («the surface owns the layout»), by his explicit decision. The reason
// the rule existed is still true, so it survives as a GUARD rather than as a veto: the worker names one of four
// presets — never geometry, never a size — and an impossible choice falls back instead of breaking the screen.
// The names are the worker's vocabulary; the classes below are the drawing. Keeping them separate is what lets
// the sheet keep saying `card` the day the drawing changes.
export const TEMPLATES = {card: "split", tile: "gallery", row: "rows", list: "rows", compare: "compare",
                   // the internal names are accepted too: sheets written before this vocabulary existed
                   split: "split", gallery: "gallery", rows: "rows"};

export function askedLayout(layout){
  return TEMPLATES[String(layout || "").trim().toLowerCase()] || "";
}

export function layoutFor(items, kind, layout){
  const arr = Array.isArray(items) ? items.filter(Boolean) : [];
  const withImg = arr.filter(it => it.image || (it.images||[]).length).length;
  // WHAT THE WORKER ASKED FOR, if it can be honoured. A photo template over a list with no photos would draw a
  // column of empty plates, so it falls to the dense one — and `makeCard` degrades per-card too, because one
  // result missing its photo must not drag the other nine out of formation.
  const want = askedLayout(layout);
  if(want){
    if(want === "compare" || want === "rows") return want;
    return withImg ? want : "rows";
  }
  if(arr.some(it => (it.parts||[]).length)) return "compare";
  const k = String(kind||"").trim().toLowerCase();
  if(k === "plan") return "compare";
  if(!withImg) return "rows";                       // nothing to show: a photo column of empty plates is worse
  if(k === "document" || k === "link") return "rows";
  if(k === "place" || k === "media" || k === "photo") return "gallery";
  // A DECLARED product list is photo-left even when this particular batch came back thin: what a result is does
  // not change because one search forgot to bring prices, and a list that reflows between two formats as facts
  // trickle in is worse than one that stays put.
  if(k === "product") return "split";
  // Does the card carry enough DATA to deserve a column of its own next to the photo? A result with a price, a
  // rating or a spec sheet does; a bare titled thumbnail does not — that one reads better as a gallery tile.
  const rich = arr.some(it => it.price || it.score || (it.facts||[]).length || (it.lines||[]).length > 1
                              || (it.blocks||[]).length);
  return rich ? "split" : "gallery";
}
