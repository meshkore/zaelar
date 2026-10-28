// results widget — small painted pieces: the identity strip, photos, chips, links, and WHICH list layout.
// Moved verbatim out of widget.js (refactor2710-12); widget.js stays the entry exporting `render`.

import { elem, tt } from "./shared.js";

// Installation and session ids RIDE THE PAYLOAD (`data.identity`): widget.js may not fetch (V2-601 T-10).
export function shortId(id){
  id = String(id||"");
  return id.length > 13 ? id.slice(0,8) + "…" : (id || "—");
}

// Identity strip (bottom of Summary, V2-538): the button copies BOTH full ids; no identity → no strip.
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
  // V2-831 — a WIDE image (a brand's logo strip, «icon_wide/…/skyshowtime») is not a photo: measured on load, it
  // sits inset in the plate as a logo instead of being blown up to the plate's width.
  img.addEventListener("load",()=>{ if(isWide(img)) box.classList.add("logo"); });
  box.appendChild(img);
  return box;
}

// A logo, not a photo: at least two and a half times as wide as it is tall (V2-831). Measured, never named.
export function isWide(img){
  return !!(img && img.naturalWidth && img.naturalHeight && img.naturalWidth >= 2.5 * img.naturalHeight);
}

// ── ITEM TEMPLATES (V2-831) ──────────────────────────────────────────────────────────────────────────────────
// Inside the list layout, ONE card may be drawn by the template of what it is: `offer` (price-led — name, big
// price, ≤2 chips, a logo at most, never a plate), `video` (16:9 thumbnail beside its text) or `link` (the site's
// icon and host over a snippet). The worker DECLARES it in one word (`kind` on the item, or on the list); on a
// list with no photo layout it is inferred from the FIELDS — a priced row is an offer, a bare page is a link.
// A photo layout infers nothing: its cards keep the plate that keeps the row in formation (V2-797).
export const ITEM_KINDS = ["offer", "video", "link"];

export function itemKind(it, listKind, layout){
  it = it || {};
  const own = String(it.kind || "").trim().toLowerCase();
  if(ITEM_KINDS.includes(own)) return own;
  const k = String(listKind || "").trim().toLowerCase();
  if(ITEM_KINDS.includes(k)) return k;
  if(layout !== "rows" || (it.parts||[]).length || (it.blocks||[]).length) return "";
  if(it.price) return "offer";
  if(it.url && !it.score) return "link";
  return "";
}

// The site's own icon, over the initial of its host: a dead icon leaves the letter, never an empty square.
export function favicon(host){
  const box = elem("span","hr-fav");
  box.appendChild(monogram(host));
  if(host){ const img = photo("https://" + host + "/favicon.ico", "", ""); box.appendChild(img); }
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

// ── WHICH of the four list layouts: decided from the SHAPE of the items; `kind` (what they ARE) is content.
export const LAYOUTS = ["split", "gallery", "rows", "compare"];

// ── THE TEMPLATES THE WORKER MAY ASK FOR (V2-703) — by the operator's decision the worker names one of these
// presets (never geometry); an impossible choice falls back instead of breaking the screen.
export const TEMPLATES = {card: "split", tile: "gallery", row: "rows", list: "rows", compare: "compare",
                   // the internal names are accepted too: sheets written before this vocabulary existed
                   split: "split", gallery: "gallery", rows: "rows"};

export function askedLayout(layout){
  return TEMPLATES[String(layout || "").trim().toLowerCase()] || "";
}

export function layoutFor(items, kind, layout){
  const arr = Array.isArray(items) ? items.filter(Boolean) : [];
  // V2-831 — A PHOTO LAYOUT NEEDS MOST OF THE LIST TO HAVE A PHOTO. It used to need ONE: a single wide logo among
  // thirteen rows flipped the whole list to plates, and twelve of them painted a monogram. Rows that declare
  // themselves an offer or a link carry no photo by template, so they do not vote for one.
  const photos = arr.filter(it => (it.image || (it.images||[]).length)
                                  && !["offer", "link"].includes(String(it.kind || "").trim().toLowerCase())).length;
  const withImg = photos * 2 > arr.length;
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
  if(ITEM_KINDS.includes(k)) return "rows";        // offers, videos and links draw their own picture, if any
  if(!withImg) return "rows";                       // a photo column of mostly empty plates is worse than none
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
