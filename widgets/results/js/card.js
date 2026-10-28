// results widget — one card (`makeCard`), its column grid, and one item's full record (`renderDetail`).
// Moved verbatim out of widget.js (refactor2710-12); widget.js stays the entry exporting `render`.

import { factsTable, renderBlocks, scoreBlock, scoreTag } from "./blocks.js";
import { LAYOUTS, expandable, favicon, hostOf, isWide, itemKind, metaChips, photo, photoPlate, sourceLink } from "./parts.js";
import { elem, tt } from "./shared.js";

// ── column distribution: by REAL WIDTH — a per-layout MINIMUM and a column CAP, in pure CSS (`auto-fill` +
// `minmax`), so it reflows by itself when the card is resized or maximised.
export function gridStyle(items, cap, layout){
  const rich = items.some(it => it && (
    (it.parts && it.parts.length) ||
    (it.blocks && it.blocks.length) ||
    (it.facts && it.facts.length > 3) ||
    (it.images && it.images.length) ||
    (it.lines && it.lines.length > 4)
  ));
  const medium = !rich && items.some(it => it && ((it.lines && it.lines.length) || it.image || it.facts));
  // A PHOTO TEMPLATE'S FLOOR COMES FROM THE TEMPLATE, NOT FROM THE DATA (V2-703): the list card no longer draws the
  // facts the heuristic counts, so it only sizes `rows`.
  const min = layout === "split" ? 300 : layout === "gallery" ? 220 : rich ? 400 : medium ? 300 : 230;
  let maxCols = layout === "split" ? 4 : layout === "gallery" ? 5 : rich ? 2 : medium ? 3 : 4;
  const n = Number(cap);
  if(Number.isFinite(n) && n >= 1) maxCols = Math.min(maxCols, Math.floor(n));
  maxCols = Math.max(1, maxCols);
  // The GAP comes from the SAME variable that paints it (`--s3`): a copied 12px once dropped a column at 1,420px.
  const floor = `calc((100% - ${maxCols - 1} * var(--s3)) / ${maxCols})`;
  return `repeat(auto-fill,minmax(max(min(100%,${min}px),${floor}),1fr))`;
}

// ── one card ────────────────────────────────────────────────────────────────────────────────────────────────
export function makeCard(it, isPrimary, choose, ctx, layout, nav, listKind){
  const parts = Array.isArray(it.parts) ? it.parts : [];
  const blocks = Array.isArray(it.blocks) ? it.blocks : [];
  const hasDetail = parts.length || blocks.length || it.score
                    || (Array.isArray(it.images) && it.images.length)
                    || (Array.isArray(it.facts) && it.facts.length);
  // A composite card owns interactive children, so it can't be an <a>; its url goes to the footer (`sourceLink`).
  const asLink = it.url && !hasDetail;
  const card = document.createElement(asLink ? "a" : "div");
  // ONE template per layout (V2-797): in a photo layout every card has a plate, a monogram when the photo is missing.
  const lay = LAYOUTS.includes(layout) ? layout : "rows";
  const photoLayout = lay === "split" || lay === "gallery";
  // V2-831 — the ITEM's template, inside the list's layout (see `itemKind`): an offer or a link has no plate, a
  // video has its 16:9 thumbnail in every layout.
  const ik = itemKind(it, listKind, lay);
  const pic = it.image || (Array.isArray(it.images) ? it.images[0] : "");
  card.className = "hr-card " + lay + (ik ? " k-" + ik : "") + (isPrimary ? " primary" : "");
  if(asLink){ card.href = it.url; card.target = "_blank"; card.rel = "noopener noreferrer"; }
  const inner = elem("div","hr-in");
  if(ik === "video"){ const th = photoPlate(pic, it.title); th.classList.add("hr-thumb"); inner.appendChild(th); }
  else if(photoLayout && !ik) inner.appendChild(photoPlate(pic, it.title));
  const body = elem("div","hr-body");
  // TITLE and SUBTITLE: whole in the data, clamped on screen, whole again on «Ver todo» and in the hover title.
  const txt = elem("div","hr-txt");
  // The SITE row of an offer or a link: the brand's logo (an offer's image is its seller's mark, never a photo
  // plate) or the page's icon and host.
  if(ik === "offer" && pic){
    const site = elem("div","hr-site"); const logo = photo(pic, "", "hr-logo");
    logo.addEventListener("load", ()=>{ if(!isWide(logo)) logo.classList.add("sq"); });
    site.appendChild(logo); txt.appendChild(site);
  } else if(ik === "link"){
    const host = hostOf(it.url);
    const site = elem("div","hr-site"); site.append(favicon(host), elem("span","hr-host", host));
    txt.appendChild(site);
  }
  const tEl = elem("div","hr-t"); tEl.appendChild(elem("div","hr-cl", it.title || ""));
  tEl.title = it.full_title || it.title || "";
  txt.appendChild(tEl);
  if(it.subtitle){ const sEl = elem("div","hr-s"); sEl.appendChild(elem("div","hr-cl", it.subtitle));
                   sEl.title = it.subtitle; txt.appendChild(sEl); }
  body.appendChild(txt);
  expandable(card, txt);
  if(ik === "offer" && it.price){ const bp = elem("div","hr-bigprice", it.price); bp.title = it.price; body.appendChild(bp); }
  // META: the rating, the badge that says why it leads, and the declared chips — one row that wraps, each chip
  // one line. The badge QUALIFIES the result, so it sits with the data, never beside the button.
  const meta = elem("div","hr-metarow");
  const sc = scoreTag(it.score); if(sc) meta.appendChild(sc);
  if(it.badge) meta.appendChild(elem("span","hr-badge", it.badge));
  metaChips(it).slice(0, ik === "offer" ? 2 : 4).forEach(c => meta.appendChild(c));
  if(meta.childElementCount) body.appendChild(meta);
  // 80 lines (data.py's cap) so a full block of text — e.g. a song's lyrics — fits in one item's body, not just
  // a handful of spec-sheet bullets (2026-08-03). In the list they are bounded: the full block belongs to the
  // record. A card WITH a photo is bounded harder still.
  (Array.isArray(it.lines) ? it.lines : []).slice(0, hasDetail ? (photoLayout ? 2 : 6) : 80)
    .forEach(l=>body.appendChild(elem("div","hr-ln", l)));

  if(!hasDetail){ const bl = renderBlocks(blocks, {compact: true}); if(bl) body.appendChild(bl); }

  // ⚠️ THE SPEC SHEET DOES NOT COME TO THE LIST (V2-703): the table is the RECORD's job (`renderDetail`); the
  // list carries the main data as chips, the photo and the way into the record.

  // the pieces of a composite result, so three proposals stay comparable at a glance
  if(parts.length){
    const box=elem("div","hr-parts");
    parts.forEach(p=>{
      const row=elem("div","hr-part");
      if(p.kind) row.appendChild(elem("span","hr-pk", p.kind));
      row.appendChild(elem("span","hr-pt", p.title||""));
      if(p.price) row.appendChild(elem("span","hr-pp", p.price));
      box.appendChild(row);
    });
    body.appendChild(box);
  }

  // ── the footer: open the record, and open the ORIGINAL page ──
  const foot = elem("div","hr-foot");
  if(it.price && ik !== "offer"){ const pr = elem("div","hr-price", it.price); pr.title = it.price; foot.appendChild(pr); }
  if(hasDetail && ctx){
    const btn=elem("button","hr-more",tt("see_detail", null, "Ver detalle →")); btn.type="button";
    // NAVIGATE FIRST, PERSIST AFTER: the item is already on screen, so the record paints locally (like the tabs,
    // V2-538) and the `detail` post only stores it — waiting on the SSE push once left a dead-looking button.
    btn.addEventListener("click", async (e)=>{ e.preventDefault(); e.stopPropagation();
      if(nav) nav("detail", it.title || "");
      btn.disabled=true;
      const r = await ctx.action("detail", { title: it.title || "" });
      btn.disabled=false;
      // A refused action SHOWS, but never un-navigates: the record is right, only storing the view failed.
      if(!r || r.ok===false){
        const why = (r && r.error) ? String(r.error) : tt("engine_silent", null, "el motor no respondió a la acción");
        if(nav) nav("detail", it.title || "", why);
        else { btn.textContent = tt("see_detail_", null, "Ver detalle → ") + tt("open_failed", null, "no se pudo abrir");
               btn.classList.add("hr-more-err"); btn.title = why; }
      }
    });
    foot.appendChild(btn);
  }
  // THE OUTBOUND LINK IS THE RECORD'S (V2-703): a row with a record offers one way forward; a row without one is
  // the anchor itself, or carries the link here — never a result with no way out.
  if(!asLink && !hasDetail){ const src = sourceLink(it.url); if(src) foot.appendChild(src); }
  if(foot.childElementCount) body.appendChild(foot);

  inner.appendChild(body);
  card.appendChild(inner);

  if(choose && !asLink){
    card.classList.add("choosable");
    const tagOf=()=>elem("span","hr-chosen-tag",tt("chosen", null, "✓ Elegido"));
    if(choose.chosenTitle && it.title === choose.chosenTitle){ card.classList.add("chosen"); card.appendChild(tagOf()); }
    card.addEventListener("click", async () => {
      if(card.classList.contains("chosen")) return;
      choose.root.querySelectorAll(".hr-card.chosen").forEach(c => { c.classList.remove("chosen"); const t=c.querySelector(".hr-chosen-tag"); if(t)t.remove(); });
      card.classList.add("chosen"); card.appendChild(tagOf());
      await choose.ctx.action("choose", { title: it.title || "" });
    });
  }
  return card;
}

// ── page 2: ONE item, in full ────────────────────────────────────────────────────────────────────────────────
// This renders "show me proposal one in detail": every photo, every datum, THE RATING with its reason, the whole
// dynamic record, and each package piece expanded with its price, times, and real link.
export function renderDetail(panel, it, ctx, nav, warn){
  const back=elem("button","hr-back",tt("back_list", null, "← Volver a la lista")); back.type="button";
  // Same rule as the detail button and the tabs: paint NOW, persist after. Going back to a list that is already
  // in memory must not wait for a round trip either.
  back.addEventListener("click", async ()=>{ if(nav) nav(null); await ctx.action("list", {}); });
  panel.appendChild(back);

  panel.appendChild(elem("div","hr-dt", it.title||""));
  if(it.price) panel.appendChild(elem("div","hr-dprice", it.price));
  const dmeta = elem("div","hr-metarow");
  if(it.subtitle) dmeta.appendChild(elem("span","hr-s", it.subtitle));
  if(it.badge) dmeta.appendChild(elem("span","hr-badge", it.badge));
  if(dmeta.childElementCount) panel.appendChild(dmeta);
  // The way OUT of our summary and into the full record, ABOVE the fold. The record we render is what the search
  // found worth keeping; the shop's own page is where the thousand remaining fields live, and the operator asked
  // for that door to be on every result. It was at the very bottom, after the whole spec table, printed as a raw
  // url. Now it reads as what it is and sits where it is decided.
  const top = sourceLink(it.url, {wide: true}); if(top) panel.appendChild(top);
  if(warn) panel.appendChild(elem("div","hr-warn", tt("view_not_saved", null,
    "Esta vista no se ha podido guardar en la hoja — la pantalla es correcta, pero al recargar volverá a la lista.")));

  // THE RATING goes ABOVE, before photos: it is the VERDICT. Below the gallery it read like one more datum at the end
  // of the record, when it is exactly what answers "why this one and not another?"
  const sb=scoreBlock(it.score);
  if(sb){ const sec=elem("div","hr-sec"); sec.appendChild(sb); panel.appendChild(sec); }

  const gallery = Array.isArray(it.images) && it.images.length ? it.images : (it.image ? [it.image] : []);
  if(gallery.length){
    const g=elem("div","hr-gal");
    gallery.forEach(u=>g.appendChild(photoPlate(u, it.title)));
    panel.appendChild(g);
  }

  (Array.isArray(it.lines)?it.lines:[]).slice(0,80).forEach(l=>panel.appendChild(elem("div","hr-ln", l)));

  const ft=factsTable(it.facts); if(ft) panel.appendChild(ft);
  const bl=renderBlocks(it.blocks); if(bl) panel.appendChild(bl);

  // The item's own url is NOT repeated here as a bare string: it is the «Ver en <site>» control at the top of
  // this page. Printing it twice —once as a button, once as 60 characters of url— was two controls for one door.

  (Array.isArray(it.parts)?it.parts:[]).forEach(p=>{
    const sec=elem("div","hr-sec");
    if(p.kind) sec.appendChild(elem("span","hr-pk", p.kind));
    sec.appendChild(elem("div","hr-sect", p.title||""));
    if(p.price) sec.appendChild(elem("div","hr-dprice", p.price));
    if(p.subtitle) sec.appendChild(elem("div","hr-s", p.subtitle));
    if(p.image) sec.appendChild(photoPlate(p.image, p.title));
    (Array.isArray(p.lines)?p.lines:[]).forEach(l=>sec.appendChild(elem("div","hr-ln", l)));
    const pf=factsTable(p.facts); if(pf) sec.appendChild(pf);
    const ps = sourceLink(p.url); if(ps) sec.appendChild(ps);
    panel.appendChild(sec);
  });
}

export function findFocused(items, focus){
  const f=String(focus||"").trim().toLowerCase();
  if(!f) return null;
  return items.find(it=>String(it&&it.title||"").trim().toLowerCase()===f)
      || items.find(it=>String(it&&it.title||"").trim().toLowerCase().includes(f))
      || null;
}
