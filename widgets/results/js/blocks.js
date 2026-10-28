// results widget — the dynamic record: facts, score, and the closed block vocabulary (`renderBlock`).
// Moved verbatim out of widget.js (refactor2710-12); widget.js stays the entry exporting `render`.

import { photo } from "./parts.js";
import { elem, tt } from "./shared.js";

export function factsTable(facts){
  const box=elem("div","hr-facts");
  (Array.isArray(facts)?facts:[]).forEach(f=>{
    if(!f || !f.label) return;
    box.append(elem("div","hr-fl",f.label), elem("div","hr-fv",f.value==null?"":f.value));
  });
  return box.childElementCount ? box : null;
}

export function pct(v, max){
  const m=Number(max)||10, n=Number(v);
  if(!isFinite(n) || m<=0) return 0;
  return Math.max(0, Math.min(100, (n/m)*100));
}

// RATING as a compact label (for a card header).
export function scoreTag(score){
  if(!score) return null;
  if(score.value == null) return score.label ? elem("span","hr-score",score.label) : null;
  const tag=elem("span","hr-score", String(score.value));
  tag.appendChild(elem("small","", "/"+(score.max||10)));
  if(score.label) tag.title=score.label;
  return tag;
}

// ...and as an explained block (for the record): score, bar, and WHY.
export function scoreBlock(score){
  if(!score || (score.value==null && !score.label && !score.why)) return null;
  const box=elem("div","");
  box.appendChild(elem("div","hr-bt",tt("rating", null, "Valoración")));
  if(score.value != null){
    const row=elem("div","hr-head");
    row.appendChild(elem("div","hr-t", `${score.value} / ${score.max||10}`));
    if(score.label) row.appendChild(elem("div","hr-price",score.label));
    box.appendChild(row);
    const bar=elem("div","hr-bar"); const fill=elem("i");
    fill.style.width=pct(score.value, score.max)+"%"; bar.appendChild(fill); box.appendChild(bar);
  } else if(score.label){
    box.appendChild(elem("div","hr-t",score.label));
  }
  if(score.why) box.appendChild(elem("div","hr-why",score.why));
  return box;
}

// ── DYNAMIC RECORD: blocks ──────────────────────────────────────────────────────────────────────────────────
// Closed vocabulary, already sanitized in data.py. Each block is rendered with our primitives: the worker composes
// the record its result type needs, but does not provide even one HTML tag.
export function renderBlock(b, depth){
  if(!b || !b.kind) return null;
  const wrap=elem("div","");
  if(b.title) wrap.appendChild(elem("div","hr-bt",b.title));
  switch(b.kind){
    case "text":
      (b.lines||[]).forEach(l=>wrap.appendChild(elem("div","hr-ln"+(b.tone?" "+b.tone:""), l)));
      break;
    case "facts": {
      const ft=factsTable(b.facts); if(ft){ ft.style.margin="0"; wrap.appendChild(ft); }
      break;
    }
    case "chips": {
      const row=elem("div","hr-chips");
      (b.chips||[]).forEach(c=>row.appendChild(elem("span","hr-chip",c)));
      wrap.appendChild(row);
      break;
    }
    case "gallery": {
      const strip=elem("div","hr-strip");
      (b.images||[]).forEach(u=>strip.appendChild(photo(u, b.title||"", "")));
      wrap.appendChild(strip);
      break;
    }
    case "meter": {
      const bar=elem("div","hr-bar"); const fill=elem("i");
      fill.style.width=pct(b.value, b.max)+"%"; bar.appendChild(fill); wrap.appendChild(bar);
      wrap.appendChild(elem("div","hr-why", (b.caption ? b.caption+" · " : "") + `${b.value} / ${b.max||10}`));
      break;
    }
    case "table": {
      // The table lives in its OWN scroll container. It used to get `display:block` to overflow, and that removes its
      // table behavior: columns stop aligning across rows, which is the only thing a table adds over a list.
      const box=elem("div","hr-tblwrap");
      const t=elem("table","hr-tbl");
      if(b.columns && b.columns.length){
        const tr=elem("tr"); b.columns.forEach(c=>tr.appendChild(elem("th","",c)));
        const thead=elem("thead"); thead.appendChild(tr); t.appendChild(thead);
      }
      const tb=elem("tbody");
      (b.rows||[]).forEach(r=>{ const tr=elem("tr"); (r||[]).forEach(c=>tr.appendChild(elem("td","",c))); tb.appendChild(tr); });
      t.appendChild(tb); box.appendChild(t); wrap.appendChild(box);
      break;
    }
    case "link": {
      const a=elem("a","hr-link",b.label||b.url);
      a.href=b.url; a.target="_blank"; a.rel="noopener noreferrer";
      a.style.marginTop="0"; wrap.appendChild(a);
      break;
    }
    case "section": {
      const inner=elem("div","hr-sub-sec");
      (b.blocks||[]).forEach(x=>{ const e=renderBlock(x, (depth||0)+1); if(e) inner.appendChild(e); });
      if(!inner.childElementCount) return null;
      wrap.appendChild(inner);
      break;
    }
    default: return null;
  }
  return wrap.childElementCount ? wrap : null;
}

// The LIST has no room for the full record. Seen on screen: a card with its cost table, meter, and documentation
// section occupied the ENTIRE card, and with ten results —the delivery default since 2026-08-12— the list stops being
// SCANNABLE, which is the only thing a list must do. So the list keeps LIGHT blocks and the rest is what you open the
// record to inspect.
// The exception is `text` with WARNING tone: an important caveat hidden behind a click is exactly what the
// presentation rule forbids ("nothing important at the end of a long field").
export const LIGHT_BLOCKS = new Set(["chips"]);
export function isLight(b){
  if(!b) return false;
  if(LIGHT_BLOCKS.has(b.kind)) return true;
  return b.kind === "text" && b.tone === "warn";
}

export function renderBlocks(blocks, {compact = false} = {}){
  let list = Array.isArray(blocks) ? blocks : [];
  if(compact) list = list.filter(isLight).slice(0, 2);
  const box=elem("div","hr-blocks");
  list.forEach(b=>{ const e=renderBlock(b,0); if(e) box.appendChild(e); });
  return box.childElementCount ? box : null;
}
