// archivos · the pieces every part shares: icons, sizes/dates, the DOM helper, the tier observer, i18n.


export const ICONS = [
  [/folder|directory/, "📁"],
  [/pdf/, "📕"],
  [/spreadsheet|excel|csv/, "📊"],
  [/presentation|powerpoint|slide/, "📽"],
  [/^image\//, "🖼"],
  [/^video\//, "🎬"],
  [/^audio\//, "🎵"],
  [/zip|compress|tar|rar/, "🗜"],
  [/document|msword|officedocument|^text\//, "📄"],
];

export const SHELF_ICON = { video: "🎬", audio: "🎵", documents: "📄", images: "🖼", downloads: "⬇" };

export const SHELF_KINDS = ["video", "audio", "documents", "images", "downloads"];
export const LOCAL_ICON = { video: "🎬", audio: "🎵", image: "🖼", document: "📄", other: "📦" };

export function iconFor(entry) {
  if (entry && entry.kind === "folder") {
    const kind = String(entry.id || "").startsWith("shelf:") ? entry.id.slice(6) : "";
    return SHELF_ICON[kind] || "📁";
  }
  if (entry && entry.provider === "local") return LOCAL_ICON[entry.file_kind] || "📦";
  const mime = String((entry && entry.mime) || "").toLowerCase();
  for (const [re, ic] of ICONS) if (re.test(mime)) return ic;
  return "📄";
}

export function humanSize(n) {
  if (typeof n !== "number" || !isFinite(n) || n < 0) return "";
  if (n < 1024) return n + " B";
  const u = ["KB", "MB", "GB", "TB"];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return (v < 10 ? v.toFixed(1) : Math.round(v)) + " " + u[i];
}

export function humanDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const now = new Date();
  const sameYear = d.getFullYear() === now.getFullYear();
  try {
    return d.toLocaleDateString(S.LANG,
      sameYear ? { day: "numeric", month: "short" } : { day: "numeric", month: "short", year: "numeric" });
  } catch (_) { return ""; }
}

export function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = String(text);   // untrusted by default — never innerHTML
  return n;
}

// The card is a FINDER, not a fixed-size box: at a narrow width everything lives in the central column with a
// tightly-controlled breadcrumb; past ~900px a sidebar of shortcuts appears, the way any desktop file manager
// grows. `data-tier` (s|m|l) drives it — CSS shows/hides the sidebar and the extra list columns from it, so a
// resize needs no re-render, just a class flip. Attached ONCE per mount node; render() clears children every
// call but never replaces the root itself, so the observer survives every repaint.
export function ensureTierObserver(root) {
  if (root._arxRO) return;
  const apply = () => {
    const w = root.getBoundingClientRect().width;
    const tier = w >= 900 ? "l" : w >= 560 ? "m" : "s";
    if (root.dataset.tier !== tier) root.dataset.tier = tier;
  };
  apply();
  try {
    const ro = new ResizeObserver(apply);
    ro.observe(root);
    root._arxRO = ro;
  } catch (_) { /* no ResizeObserver — the tier just stays at its first computed value */ }
}

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
// Module state the parts share (ES imports are read-only bindings): `T`/`LANG` are the instance's i18n and
// language (ctx.lang) — dates never follow the browser locale; `openCx` opens the ⚙ Conectores section on a
// cloud service (2026-10-04): linking one is that section's job, not this card's.
export const S = { T: null, LANG: "en", openCx: () => {} };
export function tt(key, params, fb){
  try{
    if(S.T){ const s=S.T("widgets.archivos."+key, params); if(s && s!=="widgets.archivos."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}

// Evaluated per paint, never a module-level table: one built at IMPORT time freezes its labels in whatever
// language was active when the module first loaded, and survives every later switch (V2-694).
export function shelfLabel(kind){
  switch(String(kind || "")){
    case "video":     return tt("shelf_video", null, "Vídeo");
    case "audio":     return tt("shelf_audio", null, "Audio");
    case "documents": return tt("shelf_documents", null, "Documentos");
    case "images":    return tt("shelf_images", null, "Imágenes");
    case "downloads": return tt("shelf_downloads", null, "Descargas");
    default:          return "";
  }
}
