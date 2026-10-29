// results widget — what every part shares: the tab/source/criteria tables, `elem`, and the i18n seam (`tt`).
// Moved verbatim out of widget.js (refactor2710-12); widget.js stays the entry exporting `render`.

// V2-822 — there is no PROCESS tab any more. The sheet is the errand's DELIVERABLE and shows only that; what the
// errand is doing while it works lives in ONE place, the running process's entry in the processes panel (operator,
// 2026-10-27: «simplificar las tarjetas y mover la información del proceso al rail de procesos»). While it works,
// the Results tab carries the loader, and an empty list says where the steps are.
// The LABELS are resolved per paint (`tabLabel`), never stored in this table: a module-level constant is built
// once, at IMPORT time, so its text would freeze in whatever language happened to be active the first time this
// module loaded and would survive every later switch (V2-694). The table keeps only the ids, which are data.
export const TABS = [{id: "results"}, {id: "summary"}, {id: "sources"}, {id: "criteria"}];

// Source state → how it is phrased and colored. The vocabulary is closed in the backend; here it is only translated.
// The distinction matters: "could not enter" and "entered but was capped at 50" are VERY different outcomes.
export const SOURCE_STATUS = {
  ok:      {cls: "ok"},
  partial: {cls: "warn"},
  auth:    {cls: "warn"},
  blocked: {cls: "bad"},
  error:   {cls: "bad"},
  pending: {cls: "idle"},
};

export const CRIT_SECTIONS = [
  {key: "hard"}, {key: "soft"}, {key: "enrichments"},
  {key: "assumed"}, {key: "quality_bar"}, {key: "changes"},
];

// ── safe primitives ─────────────────────────────────────────────────────────────────────────────────────────
export function elem(tag, cls, text){
  const e=document.createElement(tag);
  if(cls) e.className=cls;
  if(text!=null && typeof text !== "object") e.textContent=String(text);   // an object is never painted as its repr (V2-831 R9)
  return e;
}

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
export const I18N = {t: null};   // set by render() each paint; ES imports are read-only
export function tt(key, params, fb){
  try{
    if(I18N.t){ const s=I18N.t("widgets.results."+key, params); if(s && s!=="widgets.results."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}

export function tabLabel(id){
  switch(id){
    case "results":  return tt("tab_results", null, "Resultados");
    case "summary":  return tt("tab_summary", null, "Sumario");
    case "sources":  return tt("tab_sources", null, "Fuentes");
    case "criteria": return tt("tab_criteria", null, "Criterios");
    default:         return id;
  }
}
export function sourceLabel(status){
  switch(String(status || "")){
    case "partial": return tt("src_partial", null, "Entró con límite");
    case "auth":    return tt("src_auth", null, "Pedía autenticación");
    case "blocked": return tt("src_blocked", null, "Acceso bloqueado");
    case "error":   return tt("src_error", null, "Error");
    case "pending": return tt("src_pending", null, "En curso");
    default:        return tt("src_ok", null, "Entró");
  }
}
export function critLabel(key){
  switch(key){
    case "hard":        return tt("crit_hard", null, "Criterios duros");
    case "soft":        return tt("crit_soft", null, "Preferencias");
    case "enrichments": return tt("crit_enrichments", null, "Añadido por criterio propio");
    case "assumed":     return tt("crit_assumed", null, "Datos asumidos");
    case "quality_bar": return tt("crit_quality_bar", null, "Baremo de calidad");
    case "changes":     return tt("crit_changes", null, "Tus correcciones");
    default:            return key;
  }
}
export function critNote(key){
  switch(key){
    case "hard":        return tt("crit_hard_n", null, "incumplirlos descalifica");
    case "soft":        return tt("crit_soft_n", null, "puntúan, no descalifican");
    case "assumed":     return tt("crit_assumed_n", null, "no los dijiste — corrígelos si no van");
    case "quality_bar": return tt("crit_quality_bar_n", null, "qué hay que verificar de verdad");
    case "changes":     return tt("crit_changes_n", null, "lo que fuiste ajustando por el camino");
    default:            return "";
  }
}
