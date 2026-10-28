// youtube widget — the pieces every part uses: icons, DOM builders, the i18n helper, the tab ids and labels.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { Y } from "./state.js";

// Control-bar icons - the music widget's visual language, duplicated locally on purpose (V2-557:
// widget modules never import each other). Outline strokes for secondary controls, solid for the
// main play/pause face; solid icons get their OWN attribute set (the V2-629 lesson: appending a
// second fill to the outline tag leaves fill="none" winning).
export const _SW = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
           'stroke-linejoin="round"';
export const _SF = 'viewBox="0 0 24 24" fill="currentColor" stroke="none"';
export const ICON_PREV     = `<svg ${_SW}><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/></svg>`;
export const ICON_NEXT     = `<svg ${_SW}><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg>`;
export const ICON_PLAY     = `<svg ${_SF}><path d="M8 5v14l11-7z"/></svg>`;
export const ICON_PAUSE    = `<svg ${_SF}><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;
export const ICON_VOL_DOWN = `<svg ${_SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/></svg>`;
export const ICON_VOL_UP   = `<svg ${_SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>`;
export const ICON_MUTED    = `<svg ${_SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><line x1="22" y1="9" x2="16" y2="15"/><line x1="16" y1="9" x2="22" y2="15"/></svg>`;
// The plug is contactos' ICO_PLUG stroke for stroke: one door to the connectors, one drawing of it.
export const ICON_PLUG     = `<svg ${_SW}><path d="M9 2v6"/><path d="M15 2v6"/><path d="M6 8h12v3a6 6 0 0 1-12 0z"/><path d="M12 17v5"/></svg>`;
export const ICON_SEARCH   = `<svg ${_SW}><circle cx="11" cy="11" r="7"/><line x1="20" y1="20" x2="16.2" y2="16.2"/></svg>`;
export const ICON_CLEAR    = `<svg ${_SW}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;

export function svgEl(markup){
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content.firstElementChild;
}

export function el(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = String(text);
  return e;
}

// Ids only: the LABEL is resolved per paint (`tabLabel`), because a module-level table is built once, at IMPORT
// time, so its text would freeze in whatever language was active the first time this module loaded (V2-694).
export const _TABS = ["inicio", "player", "cola", "subs", "listas"];
export function tabLabel(id){
  switch(id){
    case "inicio": return tt("tab_home", null, "Inicio");
    case "player": return tt("tab_player", null, "Reproductor");
    case "cola":   return tt("tab_queue", null, "Cola");
    case "subs":   return tt("tab_subs", null, "Suscripciones");
    case "listas": return tt("tab_lists", null, "Listas");
    default:       return id;
  }
}
export function applyTabClass(root){
  _TABS.forEach((id) => root.classList.toggle("hb-yt-t-" + id, Y.tab === id));
}

export function halted(ctx){ return !!(ctx && ctx.running === false); }

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
export function tt(key, params, fb){
  try{
    if(Y.T){ const s=Y.T("widgets.youtube."+key, params); if(s && s!=="widgets.youtube."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}
