// archivos — a real file manager: the agent's own library first, cloud drives beside it (V2-658/V2-662).
//
// Shaped like the file managers people already know: a small icon row up top for WHICH storage (this device,
// Drive, OneDrive…), a breadcrumb + ONE search field + list/grid toolbar under it, folders before files,
// double-click to open. Local files get real actions (rename/copy/delete); a cloud provider that cannot do
// one says so. At a wide card size a Finder/Explorer-style SIDEBAR appears (this device's shelves + the cloud
// services) so navigation never depends only on the small header chips.
//
// TWO RULES THIS FILE CANNOT BREAK:
//  · Every string in here — file names, folder names, mime types — is UNTRUSTED (a cloud drive, or a torrent's
//    own file name). textContent only, never innerHTML.
//  · No network and no polling. The card asks for a listing when its cache is stale (`data.needs_refresh`) and
//    for the provider catalog when ITS cache is stale (`data.providers_stale`) — both ONCE per staleness, then
//    repaints only when `store.save()` pushes over SSE.

const STYLE_ID = "hb-archivos-style";

const CSS = `
.arx{display:flex;flex-direction:column;width:100%;height:100%;min-height:0;box-sizing:border-box;
  position:relative;background:var(--hb-bg,#fff);border-radius:14px;overflow:hidden;
  font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial;color:var(--hb-ink,#0d1622)}
.arx-layout{display:flex;flex:1 1 auto;min-height:0}
.arx-main{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;min-height:0}
/* The SIDEBAR — a Finder/Explorer-style nav column. Only shown once the card is wide enough to hold it
   without squeezing the content area; see the tier system below, ensureTierObserver. */
.arx-side{flex:0 0 190px;display:none;flex-direction:column;gap:1px;padding:10px 6px;overflow:auto;
  border-right:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff)}
.arx[data-tier="l"] .arx-side{display:flex}
.arx-side-head{background:none;border:0;text-align:left;font:inherit;font-size:10.5px;font-weight:700;
  text-transform:uppercase;letter-spacing:.05em;color:var(--hb-muted-2,#9aa4b2);padding:9px 8px 4px;cursor:pointer}
.arx-side-head:hover{color:var(--hb-ink,#0d1622)}
.arx-side-item{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:8px;border:0;
  background:none;text-align:left;cursor:pointer;color:var(--hb-ink,#0d1622);font:inherit;width:100%}
.arx-side-item:hover{background:var(--hb-bg-soft,#f5f7fb)}
.arx-side-item.on{background:color-mix(in srgb,var(--hb-accent,#2f6df6) 14%,transparent);
  color:var(--hb-accent,#2f6df6);font-weight:600}
.arx-side-item .arx-ic{width:18px;flex:0 0 auto;text-align:center;font-size:14px}
.arx-side-nm{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arx-side-count{flex:0 0 auto;color:var(--hb-muted-2,#9aa4b2);font-size:11px}
.arx-side-dot{width:7px;height:7px;border-radius:50%;background:var(--hb-muted-2,#9aa4b2);flex:0 0 auto}
.arx-side-dot.conn{background:var(--hb-accent2,#12a594)}
/* ONE header row — the storage chips, the breadcrumb and the tools live together so the chrome never reads
   as two half-empty bands with a void between them. */
.arx-bar{display:flex;align-items:center;gap:10px;padding:10px 12px;border-bottom:1px solid var(--hb-line,#eef1f6);
  flex:0 0 auto;flex-wrap:wrap;row-gap:8px}
.arx-chips{display:flex;align-items:center;gap:6px;flex:0 0 auto}
.arx-pchip{width:32px;height:32px;border-radius:10px;border:1px solid var(--hb-line,#eef1f6);
  background:var(--hb-bg,#fff);display:grid;place-items:center;font-size:16px;line-height:1;
  font-weight:700;cursor:pointer;flex:0 0 auto;color:var(--hb-muted,#67707d);
  box-shadow:0 1px 2px rgba(0,0,0,.14);transition:transform .1s ease}
.arx-pchip:hover{background:var(--hb-bg-soft,#f5f7fb);transform:translateY(-1px)}
.arx-pchip.on{border-color:var(--hb-accent,#2f6df6);box-shadow:0 0 0 2px color-mix(in srgb,var(--hb-accent,#2f6df6) 30%,transparent);
  color:var(--hb-accent,#2f6df6)}
.arx-pchip.conn:not(.on){border-color:var(--hb-accent2,#12a594);color:var(--hb-accent2,#12a594)}
.arx-pchip.off{opacity:.5}
.arx-divider{width:1px;align-self:stretch;background:var(--hb-line,#eef1f6);flex:0 0 auto}
.arx-crumbs{display:flex;align-items:center;gap:4px;flex:1 1 180px;min-width:0;overflow:hidden;flex-wrap:nowrap}
.arx-crumb{background:none;border:0;padding:2px 6px;border-radius:6px;color:var(--hb-accent,#2f6df6);cursor:pointer;font:inherit;max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:0 1 auto}
.arx-crumb:hover{background:var(--hb-bg-soft,#f5f7fb)}
.arx-crumb[disabled]{color:var(--hb-ink,#0d1622);cursor:default;font-weight:600}
.arx-crumb-more{max-width:none;padding:2px 8px;font-weight:700}
.arx-sep{color:var(--hb-muted-2,#9aa4b2);flex:0 0 auto}
.arx-tag{flex:0 0 auto;font-size:11.5px;color:var(--hb-muted,#67707d);background:var(--hb-bg-soft,#f5f7fb);
  border-radius:999px;padding:1px 8px;white-space:nowrap}
.arx-tools{display:flex;align-items:center;gap:6px;flex:0 0 auto}
.arx-find{display:flex;align-items:center;gap:4px;background:var(--hb-bg-soft,#f5f7fb);border:1px solid var(--hb-line,#eef1f6);border-radius:8px;padding:3px 6px}
.arx-find.active{border-color:var(--hb-accent,#2f6df6)}
.arx-find input{border:0;background:none;outline:none;font:inherit;color:var(--hb-ink,#0d1622);width:130px}
.arx-find-ic{color:var(--hb-muted,#67707d);font-size:13px}
.arx-find-count{flex:0 0 auto;font-size:11px;color:var(--hb-muted,#67707d);background:var(--hb-bg,#fff);
  border-radius:999px;padding:1px 6px}
.arx-find-x{border:0;background:none;color:var(--hb-muted,#67707d);cursor:pointer;font-size:13px;padding:0 2px;line-height:1}
.arx-find-x:hover{color:var(--hb-ink,#0d1622)}
.arx-btn{border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);border-radius:8px;padding:3px 8px;cursor:pointer;font:inherit;line-height:1.6}
.arx-btn:hover{background:var(--hb-bg-soft,#f5f7fb)}
.arx-btn[disabled]{opacity:.4;cursor:default}
.arx-btn.on{border-color:var(--hb-accent,#2f6df6);color:var(--hb-accent,#2f6df6)}
.arx-btn.danger{color:var(--hb-risk,#d64545);border-color:var(--hb-risk,#d64545)}
/* The content PANEL — a visibly different surface from the chrome above it, so "where the files are" reads
   as one bounded area instead of bleeding into the rest of the card. */
.arx-body{flex:1 1 auto;min-height:0;overflow:auto;padding:12px;background:var(--hb-bg-soft,#f5f7fb)}
.arx-shelves{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.arx-shelf{display:flex;flex-direction:column;align-items:center;gap:8px;padding:20px 10px;
  border:1px solid var(--hb-line,#eef1f6);border-radius:14px;cursor:pointer;background:var(--hb-bg,#fff);
  box-shadow:0 1px 3px rgba(0,0,0,.12)}
.arx-shelf:hover{border-color:var(--hb-accent,#2f6df6);box-shadow:0 2px 8px rgba(0,0,0,.18)}
.arx-shelf .arx-ic{width:52px;height:52px;border-radius:16px;background:var(--hb-bg-soft,#f5f7fb);
  display:grid;place-items:center;font-size:26px;line-height:1}
.arx-shelf b{font-size:.85rem}
.arx-shelf span{color:var(--hb-muted,#67707d);font-size:.72rem}
.arx-row{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:9px;
  background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);margin-bottom:6px}
.arx-row:hover{border-color:var(--hb-accent,#2f6df6)}
.arx-row.sel{box-shadow:inset 3px 0 0 var(--hb-accent,#2f6df6)}
.arx-clickable{cursor:pointer;flex:1 1 auto;min-width:0;display:flex;align-items:center;gap:10px}
.arx-ic{flex:0 0 auto;font-size:17px;width:22px;text-align:center;line-height:1}
.arx-nm{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arx-meta{flex:0 0 auto;display:flex;align-items:center;color:var(--hb-muted,#67707d);font-size:11.5px;white-space:nowrap}
.arx-col-date{display:none}
.arx-col-loc{display:none;color:var(--hb-muted-2,#9aa4b2)}
.arx[data-tier="m"] .arx-col-date,.arx[data-tier="l"] .arx-col-date{display:inline}
.arx[data-tier="l"] .arx-col-loc{display:inline}
.arx-acts{display:flex;align-items:center;gap:3px;flex:0 0 auto}
.arx-ac{border:0;background:none;color:var(--hb-muted,#67707d);cursor:pointer;font-size:15px;padding:4px 5px;border-radius:6px;line-height:1}
.arx-ac:hover{background:var(--hb-bg-soft,#f5f7fb);color:var(--hb-ink,#0d1622)}
.arx-ac.danger:hover{color:var(--hb-risk,#d64545)}
.arx-rename{flex:1 1 auto;display:flex;gap:6px;min-width:0}
.arx-rename input{flex:1 1 auto;min-width:0;border:1px solid var(--hb-accent,#2f6df6);border-radius:6px;padding:3px 6px;font:inherit;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
.arx-confirm{display:flex;align-items:center;gap:6px;flex:0 0 auto}
.arx-confirm span{color:var(--hb-risk,#d64545);font-size:11.5px}
.arx-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px}
.arx-tile{display:flex;flex-direction:column;align-items:center;gap:5px;padding:12px 6px;
  border:1px solid var(--hb-line,#eef1f6);border-radius:12px;cursor:pointer;background:var(--hb-bg,#fff);
  box-shadow:0 1px 3px rgba(0,0,0,.12)}
.arx-tile:hover{border-color:var(--hb-accent,#2f6df6);box-shadow:0 2px 8px rgba(0,0,0,.18)}
.arx-tile img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px}
.arx-tile .arx-ic{font-size:26px;width:auto}
.arx-tile .arx-nm{width:100%;text-align:center;font-size:12px;white-space:normal;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.arx-note{padding:10px 12px;border-radius:10px;background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);color:var(--hb-muted,#67707d);
  margin-bottom:10px;display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.arx-path{background:var(--hb-bg-soft,#f5f7fb);border-radius:6px;padding:2px 6px;color:var(--hb-ink,#0d1622);
  word-break:break-all;font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}
.arx-note.warn{background:var(--hb-warn-bg,#fff8e6);border-color:var(--hb-warn-border,#f5d78e);color:var(--hb-warn-ink,#7a5b00)}
.arx-note.bad{border-color:var(--hb-risk,#d64545);color:var(--hb-risk,#d64545)}
.arx-foot{flex:0 0 auto;border-top:1px solid var(--hb-line,#eef1f6);padding:8px 10px;display:flex;gap:10px;align-items:center}
.arx-foot .arx-nm{font-weight:600}
/* The connect wizard, as its OWN screen with a persistent close/back — the operator's own report was
   "I got in here and had no way out". A gear-icon ⚙ opens this; the ✕ up top always gets back out. */
.arx-cxwrap{display:flex;flex-direction:column;height:100%;min-height:0}
.arx-cxtop{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;
  border-bottom:1px solid var(--hb-line,#eef1f6);flex:0 0 auto}
.arx-cxtop b{font-size:13.5px}
.arx-cxclose{background:none;border:0;color:var(--hb-muted,#67707d);font-size:19px;cursor:pointer;
  padding:2px 8px;line-height:1;border-radius:8px}
.arx-cxclose:hover{background:var(--hb-bg-soft,#f5f7fb);color:var(--hb-ink,#0d1622)}
.arx-cx{flex:1 1 auto;overflow:auto;padding:12px}
.arx-cx p{margin:0 0 10px;color:var(--hb-muted,#67707d);font-size:12px}
.arx-prov{border:1px solid var(--hb-line,#eef1f6);border-radius:12px;padding:10px;margin-bottom:10px;background:var(--hb-bg,#fff)}
.arx-prov b{font-size:13px}
.arx-field{display:flex;align-items:center;gap:8px;margin:6px 0}
.arx-field label{flex:0 0 96px;color:var(--hb-muted,#67707d);font-size:12px}
.arx-field input,.arx-field select{flex:1 1 auto;min-width:0;border:1px solid var(--hb-line,#eef1f6);border-radius:7px;padding:4px 7px;font:inherit;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
.arx-tiernote{color:var(--hb-muted-2,#9aa4b2);font-size:11.5px;margin:2px 0 8px}
.arx-badge{font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid var(--hb-line,#eef1f6);color:var(--hb-muted,#67707d)}
.arx-badge.ok{border-color:var(--hb-accent2,#12a594);color:var(--hb-accent2,#12a594)}
.arx-lb{position:absolute;inset:0;background:rgba(10,12,16,.86);display:flex;flex-direction:column;z-index:5;border-radius:14px}
.arx-lb-top{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;color:#fff;flex:0 0 auto}
.arx-lb-top b{font-size:.85rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arx-lb-close{background:none;border:0;color:#fff;font-size:20px;cursor:pointer;padding:2px 8px;line-height:1}
.arx-lb-body{flex:1 1 auto;display:flex;align-items:center;justify-content:center;overflow:auto;padding:10px;min-height:0}
.arx-lb-body img{max-width:100%;max-height:100%;object-fit:contain;border-radius:6px}
.arx-lb-body iframe{width:100%;height:100%;border:0;border-radius:6px;background:#fff}
`;

const ICONS = [
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

const SHELF_ICON = { video: "🎬", audio: "🎵", documents: "📄", images: "🖼", downloads: "⬇" };
const SHELF_LABEL = { video: "Vídeo", audio: "Audio", documents: "Documentos", images: "Imágenes", downloads: "Descargas" };
const SHELF_KINDS = ["video", "audio", "documents", "images", "downloads"];
const LOCAL_ICON = { video: "🎬", audio: "🎵", image: "🖼", document: "📄", other: "📦" };

function iconFor(entry) {
  if (entry && entry.kind === "folder") {
    const kind = String(entry.id || "").startsWith("shelf:") ? entry.id.slice(6) : "";
    return SHELF_ICON[kind] || "📁";
  }
  if (entry && entry.provider === "local") return LOCAL_ICON[entry.file_kind] || "📦";
  const mime = String((entry && entry.mime) || "").toLowerCase();
  for (const [re, ic] of ICONS) if (re.test(mime)) return ic;
  return "📄";
}

function humanSize(n) {
  if (typeof n !== "number" || !isFinite(n) || n < 0) return "";
  if (n < 1024) return n + " B";
  const u = ["KB", "MB", "GB", "TB"];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return (v < 10 ? v.toFixed(1) : Math.round(v)) + " " + u[i];
}

function humanDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const now = new Date();
  const sameYear = d.getFullYear() === now.getFullYear();
  try {
    return d.toLocaleDateString(undefined,
      sameYear ? { day: "numeric", month: "short" } : { day: "numeric", month: "short", year: "numeric" });
  } catch (_) { return ""; }
}

function el(tag, cls, text) {
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
function ensureTierObserver(root) {
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

export function render(root, data, ctx) {
  if (!document.getElementById(STYLE_ID)) {
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = CSS;
    document.head.appendChild(s);
  }
  const d = data || {};
  const act = async (name, payload) => {
    try { return ctx && ctx.action ? await ctx.action(name, payload || {}) : null; } catch (_) { return null; }
  };
  // Local view state (rename-in-progress, delete confirm, the lightbox, the expanded breadcrumb) survives
  // across pushed re-renders on the SAME dom node — it is not server state, and losing it on every SSE
  // repaint would close the lightbox the instant a sibling action (e.g. a background download) touched the store.
  const ui = root._arxUi || (root._arxUi = { renameId: "", renameVal: "", confirmId: "", preview: null, crumbsExpanded: false });

  // The passed-in element IS the root — no wrapper div. A wrapped root sizes to its own CONTENT instead of
  // the card it was handed (`el.className` set here is what `desktop.js`'s fluid `.hb-win`/`.hb-scroll`
  // actually measures); `results`/`documento`/`youtube` set the same convention (V2-615).
  root.textContent = "";
  root.className = "arx";
  ensureTierObserver(root);

  if (d.panel === "connect") {
    root.appendChild(connectPanel(d, act));
    return;
  }

  const layout = el("div", "arx-layout");
  layout.appendChild(sidebar(d, act));
  const main = el("div", "arx-main");
  main.appendChild(header(d, act, ui));
  main.appendChild(body(d, act, ui));
  if (d.selected) main.appendChild(footer(d.selected, act));
  layout.appendChild(main);
  root.appendChild(layout);
  if (ui.preview) root.appendChild(lightbox(ui, act));

  if (d.needs_refresh && !root._arxAsked) {
    root._arxAsked = true;
    act("refresh", {});
  }
  if (!d.needs_refresh) root._arxAsked = false;

  if (d.providers_stale && !root._arxProvAsked) {
    root._arxProvAsked = true;
    act("sync_providers", {});
  }
  if (!d.providers_stale) root._arxProvAsked = false;
}

// ── the SIDEBAR: shortcuts for this device's five shelves + every cloud service — the "quick access" a real
// file manager always has, so navigation never depends on the small header chips alone. Additive: the header
// keeps its own chips too, this just gives a wide card a second, richer way to the same places.
function sidebar(d, act) {
  const side = el("div", "arx-side");
  const isLocal = d.provider === "local";

  const devHead = el("button", "arx-side-head", "Este dispositivo");
  devHead.title = "Ir a tu biblioteca";
  devHead.onclick = () => act("set_provider", { provider: "local" });
  side.appendChild(devHead);

  SHELF_KINDS.forEach(k => {
    const active = isLocal && d.folder_id === `shelf:${k}`;
    const item = el("button", "arx-side-item" + (active ? " on" : ""));
    item.appendChild(el("span", "arx-ic", SHELF_ICON[k]));
    item.appendChild(el("span", "arx-side-nm", SHELF_LABEL[k]));
    item.title = SHELF_LABEL[k];
    item.onclick = async () => {
      if (!isLocal) await act("set_provider", { provider: "local" });
      act("open_folder", { folderId: `shelf:${k}` });
    };
    side.appendChild(item);
  });

  const provs = d.providers || [];
  if (provs.length) {
    side.appendChild(el("div", "arx-side-head", "Nube"));
    provs.forEach(p => {
      const active = d.provider === p.id;
      const item = el("button", "arx-side-item" + (active ? " on" : ""));
      item.appendChild(el("span", "arx-side-dot" + (p.connected ? " conn" : "")));
      item.appendChild(el("span", "arx-side-nm", p.label || p.id));
      item.title = p.connected ? (p.label || p.id) : `${p.label || p.id} — sin conectar`;
      item.onclick = () => {
        if (p.connected) act("set_provider", { provider: p.id });
        else act("open_connectors", { provider: p.id });
      };
      side.appendChild(item);
    });
  }

  const gear = el("button", "arx-side-item", null);
  gear.appendChild(el("span", "arx-ic", "⚙"));
  gear.appendChild(el("span", "arx-side-nm", "Servicios en la nube"));
  gear.title = "Conectar o gestionar servicios en la nube";
  gear.onclick = () => act("open_connectors", {});
  side.appendChild(gear);

  return side;
}

// ── ONE header row: this device + every cloud service, then the breadcrumb, then the tools ─────────────────
// Kept as a single row deliberately (see the module notes) — two half-empty bands read as "un doble header
// vacío" the instant a card has real width; one populated row reads as one screen.
function header(d, act, ui) {
  const bar = el("div", "arx-bar");
  const isLocal = d.provider === "local";

  const chips = el("div", "arx-chips");
  const local = el("button", "arx-pchip" + (isLocal ? " on" : ""), "💻");
  local.title = "Este dispositivo — tu biblioteca";
  local.onclick = () => { ui.preview = null; act("set_provider", { provider: "local" }); };
  chips.appendChild(local);

  (d.providers || []).forEach(p => {
    const letter = String(p.label || p.id || "?").trim().charAt(0).toUpperCase() || "?";
    const cls = "arx-pchip" + (d.provider === p.id ? " on" : (p.connected ? " conn" : " off"));
    const chip = el("button", cls, letter);
    chip.title = d.provider === p.id ? `${p.label || p.id} — estás aquí`
      : p.connected ? `${p.label || p.id} — conectado, pulsa para entrar`
      : `${p.label || p.id} — sin conectar, pulsa para conectarlo`;
    chip.onclick = () => {
      ui.preview = null;
      if (p.connected) act("set_provider", { provider: p.id });
      else act("open_connectors", { provider: p.id });
    };
    chips.appendChild(chip);
  });
  bar.appendChild(chips);
  bar.appendChild(el("div", "arx-divider"));

  bar.appendChild(crumbsRow(d, ui, act));
  bar.appendChild(toolsRow(d, act));
  return bar;
}

// The breadcrumb ALWAYS shows the real place (never a "search results" placeholder that repeats the query —
// the query already lives, once, in the search field itself). Long trails (a deeply-nested cloud folder)
// collapse to Home › … › the last couple of steps, never a 200-item wall; the "…" itself is a control that
// expands it inline, kept as pure UI state on `ui` (V2-608's own convention for a rename/delete flip).
function crumbsRow(d, ui, act) {
  const crumbs = el("div", "arx-crumbs");
  const isLocal = d.provider === "local";
  const trail = d.trail || [];

  const home = el("button", "arx-crumb", isLocal ? "Biblioteca" : (d.provider === "onedrive" ? "OneDrive" : "Mi unidad"));
  home.onclick = () => act("go_home", {});
  if (!trail.length) home.disabled = true;
  crumbs.appendChild(home);

  const KEEP = 2; // how many of the deepest steps stay visible once a trail collapses
  let visible = trail;
  let hidden = 0;
  if (trail.length > KEEP + 1 && !ui.crumbsExpanded) {
    hidden = trail.length - KEEP;
    visible = trail.slice(trail.length - KEEP);
  }
  if (hidden > 0) {
    crumbs.appendChild(el("span", "arx-sep", "›"));
    const more = el("button", "arx-crumb arx-crumb-more", "…");
    more.title = `${hidden} carpeta(s) más — pulsa para ver la ruta completa`;
    more.onclick = () => { ui.crumbsExpanded = true; act("refresh", {}); };
    crumbs.appendChild(more);
  }
  visible.forEach((t, i) => {
    crumbs.appendChild(el("span", "arx-sep", "›"));
    const b = el("button", "arx-crumb", t.name || "…");
    const isLast = i === visible.length - 1;
    if (isLast) b.disabled = true;
    else b.onclick = () => act("open_folder", { folderId: t.id });
    crumbs.appendChild(b);
  });

  if (d.query) {
    const n = typeof d.count === "number" ? d.count : (d.entries || []).length;
    crumbs.appendChild(el("span", "arx-tag", n === 1 ? "1 resultado" : `${n} resultados`));
  }
  return crumbs;
}

// The tools row: up · ONE search field (icon + text, count + clear live INSIDE it — never a second box
// duplicating the same query) · list/grid · refresh · cloud services.
function toolsRow(d, act) {
  const tools = el("div", "arx-tools");

  const up = el("button", "arx-btn", "↑");
  up.title = "Subir una carpeta";
  up.disabled = !!d.query || !(d.trail || []).length;
  up.onclick = () => act("go_up", {});
  tools.appendChild(up);

  const find = el("div", "arx-find" + (d.query ? " active" : ""));
  find.appendChild(el("span", "arx-find-ic", "🔎"));
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = d.provider === "local" ? "Buscar en tu biblioteca" : "Buscar en tus archivos";
  input.value = d.query || "";
  input.onkeydown = (ev) => {
    if (ev.key !== "Enter") return;
    const q = input.value.trim();
    if (q) act("search_files", { query: q });
    else act("clear_search", {});
  };
  find.appendChild(input);
  if (d.query) {
    const clear = el("button", "arx-find-x", "✕");
    clear.title = "Quitar la búsqueda y volver";
    clear.onclick = () => act("clear_search", {});
    find.appendChild(clear);
  }
  tools.appendChild(find);

  const list = el("button", "arx-btn" + (d.mode !== "grid" ? " on" : ""), "☰");
  list.title = "Vista de lista";
  list.onclick = () => act("set_view", { mode: "list" });
  const grid = el("button", "arx-btn" + (d.mode === "grid" ? " on" : ""), "▦");
  grid.title = "Vista de cuadrícula";
  grid.onclick = () => act("set_view", { mode: "grid" });
  tools.appendChild(list);
  tools.appendChild(grid);

  const ref = el("button", "arx-btn", "⟳");
  ref.title = "Actualizar";
  ref.onclick = () => act("refresh", {});
  tools.appendChild(ref);

  const cx = el("button", "arx-btn", "⚙");
  cx.title = "Servicios en la nube";
  cx.onclick = () => act("open_connectors", {});
  tools.appendChild(cx);

  return tools;
}

function body(d, act, ui) {
  const box = el("div", "arx-body");

  if (ui.pathHint) box.appendChild(pathHintNote(ui, act));

  if (d.error) {
    box.appendChild(el("div", "arx-note bad", d.error));
    return box;
  }
  if (d.reason) box.appendChild(el("div", "arx-note warn", d.reason));

  // The local home screen is the five shelves, not a real folder listing — see the module's own docstring.
  if (d.provider === "local" && !d.query && !d.folder_id) {
    box.appendChild(shelfGrid(d, act));
    return box;
  }

  const entries = d.entries || [];
  if (!entries.length) {
    if (!d.reason) {
      box.appendChild(el("div", "arx-note",
        d.query ? `No hay nada que se llame «${d.query}».` : "Esta carpeta está vacía."));
    }
    return box;
  }

  if (d.mode === "grid") box.appendChild(gridView(d, entries, act));
  else box.appendChild(listView(d, entries, act, ui));

  if (d.next) box.appendChild(el("div", "arx-note", "Hay más elementos en esta carpeta."));
  return box;
}

function shelfGrid(d, act) {
  const grid = el("div", "arx-shelves");
  (d.entries || []).forEach(e => {
    const tile = el("div", "arx-shelf");
    tile.appendChild(el("span", "arx-ic", iconFor(e)));
    tile.appendChild(el("b", null, e.name || ""));
    const n = typeof e.count === "number" ? e.count : 0;
    tile.appendChild(el("span", null, n === 1 ? "1 archivo" : `${n} archivos`));
    tile.onclick = () => act("open_folder", { folderId: e.id });
    grid.appendChild(tile);
  });
  return grid;
}

function gridView(d, entries, act) {
  const grid = el("div", "arx-grid");
  entries.forEach(e => {
    const isFolder = e.kind === "folder";
    const tile = el("div", "arx-tile");
    if (!isFolder && e.provider === "local" && e.file_kind === "image" && e.url) {
      const img = document.createElement("img");
      img.src = e.url;
      img.alt = "";
      tile.appendChild(img);
    } else {
      tile.appendChild(el("span", "arx-ic", iconFor(e)));
    }
    const nm = el("span", "arx-nm", e.name || "(sin nombre)");
    nm.title = e.name || "";
    tile.appendChild(nm);
    tile.onclick = () => isFolder ? act("open_folder", { folderId: e.id }) : openEntry(e, act, tile);
    grid.appendChild(tile);
  });
  return grid;
}

function listView(d, entries, act, ui) {
  const holder = el("div");
  entries.forEach(e => {
    const isFolder = e.kind === "folder";
    const isLocal = e.provider === "local";
    const row = el("div", "arx-row" + (d.selected && d.selected.id === e.id ? " sel" : ""));

    if (!isFolder && ui.renameId === e.id) {
      row.appendChild(renameField(e, act, ui));
      holder.appendChild(row);
      return;
    }

    const click = el("div", "arx-clickable");
    click.appendChild(el("span", "arx-ic", iconFor(e)));
    const nm = el("span", "arx-nm", e.name || "(sin nombre)");
    nm.title = e.name || "";
    click.appendChild(nm);
    if (!isFolder) {
      const meta = el("span", "arx-meta");
      const sizeTxt = humanSize(e.size);
      if (sizeTxt) meta.appendChild(el("span", "arx-col-size", sizeTxt));
      const dateTxt = humanDate(e.modified);
      if (dateTxt) meta.appendChild(el("span", "arx-col-date", (sizeTxt ? " · " : "") + dateTxt));
      // The "location" column only earns its keep when results are MIXED across shelves — a plain folder
      // listing already says where you are in the breadcrumb, so repeating it per row would be noise.
      if (d.query && e.shelf && SHELF_LABEL[e.shelf]) {
        meta.appendChild(el("span", "arx-col-loc", (sizeTxt || dateTxt ? " · " : "") + SHELF_LABEL[e.shelf]));
      }
      click.appendChild(meta);
    }
    click.onclick = () => isFolder ? act("open_folder", { folderId: e.id }) : selectOrPreview(e, act);
    click.ondblclick = () => { if (!isFolder) openEntry(e, act, row); };
    row.appendChild(click);

    if (!isFolder) {
      if (ui.confirmId === e.id) {
        row.appendChild(deleteConfirm(e, act, ui));
      } else {
        row.appendChild(rowActions(e, act, ui));
      }
    }
    holder.appendChild(row);
  });
  return holder;
}

function selectOrPreview(e, act) {
  // A cloud row's single click behaves as it always has: fetch the metadata + web link into the footer. A
  // local row does nothing on a single click — its always-visible action icons ARE the affordance, so there
  // is no separate "select" state to build and keep in sync.
  if (e.provider !== "local") act("open_file", { fileId: e.id });
}

function rowActions(e, act, ui) {
  const acts = el("div", "arx-acts");
  const isLocalUnplayable = e.provider === "local" && !e.playable;

  if (isLocalUnplayable) {
    // Never a silent download here — see the module notes. `same_machine` (self-host) gets a "where is it"
    // affordance; a cloud engine gets nothing extra (the explicit ⬇ below is its only, and correct, way).
    if (e.same_machine) {
      const reveal = el("button", "arx-ac", "📁");
      reveal.title = "Ver dónde está";
      reveal.onclick = () => revealLocal(e, act, reveal.closest(".arx"));
      acts.appendChild(reveal);
    }
    if (e.download_url) {
      const dl = el("button", "arx-ac", "⬇");
      dl.title = "Descargar una copia";
      dl.onclick = () => { try { window.open(e.download_url, "_blank", "noopener,noreferrer"); } catch (_) {} };
      acts.appendChild(dl);
    }
  } else {
    const openBtn = el("button", "arx-ac", e.provider === "local" ? primaryGlyph(e) : "↗");
    openBtn.title = e.provider === "local" ? "Abrir" : "Abrir el enlace";
    openBtn.onclick = () => openEntry(e, act, openBtn.closest(".arx"));
    acts.appendChild(openBtn);
  }

  if (e.provider === "local") {
    const ren = el("button", "arx-ac", "✎");
    ren.title = "Renombrar";
    // A pure UI-state flip (entering rename mode) has no server-side counterpart, so it asks for a repaint the
    // same way the host already repaints after any real action: `refresh` round-trips the store and the next
    // `render()` call sees `ui.renameId` set, on the SAME root (`root._arxUi` survives the repaint).
    ren.onclick = () => { ui.renameId = e.id; ui.renameVal = e.name || ""; act("refresh", {}); };
    acts.appendChild(ren);

    const cp = el("button", "arx-ac", "⧉");
    cp.title = "Duplicar";
    cp.onclick = () => act("copy_file", { fileId: e.id });
    acts.appendChild(cp);

    const del = el("button", "arx-ac danger", "🗑");
    del.title = "Borrar";
    del.onclick = () => { ui.confirmId = e.id; act("refresh", {}); };
    acts.appendChild(del);
  }
  return acts;
}

function primaryGlyph(e) {
  if (e.file_kind === "video" || e.file_kind === "audio") return e.playable ? "▶" : "⬇";
  if (e.file_kind === "image" || e.file_kind === "document") return e.playable ? "👁" : "⬇";
  return "⬇";
}

function renameField(e, act, ui) {
  const wrap = el("div", "arx-rename");
  const input = document.createElement("input");
  input.type = "text";
  input.value = ui.renameVal || e.name || "";
  input.onkeydown = (ev) => {
    if (ev.key === "Enter") save();
    if (ev.key === "Escape") cancel();
  };
  wrap.appendChild(input);
  const ok = el("button", "arx-btn", "✓");
  ok.onclick = save;
  const no = el("button", "arx-btn", "✕");
  no.onclick = cancel;
  wrap.appendChild(ok);
  wrap.appendChild(no);
  function save() {
    const name = input.value.trim();
    ui.renameId = "";
    if (name && name !== e.name) act("rename_file", { fileId: e.id, name });
    else act("refresh", {});
  }
  function cancel() { ui.renameId = ""; act("refresh", {}); }
  setTimeout(() => { try { input.focus(); input.select(); } catch (_) {} }, 0);
  return wrap;
}

function deleteConfirm(e, act, ui) {
  const wrap = el("div", "arx-confirm");
  wrap.appendChild(el("span", null, `¿Borrar «${e.name}»?`));
  const yes = el("button", "arx-btn danger", "Sí");
  yes.onclick = () => { ui.confirmId = ""; act("delete_file", { fileId: e.id }); };
  const no = el("button", "arx-btn", "No");
  no.onclick = () => { ui.confirmId = ""; act("refresh", {}); };
  wrap.appendChild(yes);
  wrap.appendChild(no);
  return wrap;
}

// Open a row: local media hands off to its player (the server raises that card); a local image/document
// previews INSIDE this card; a local file that cannot play NEVER auto-downloads — see `revealLocal` and the
// module notes (a double-click that quietly copies a file already on this disk into the browser's own
// Downloads folder is how the operator ended up with two copies of the same film); a cloud file returns its
// web link.
async function openEntry(e, act, anyNodeInCard) {
  // `.arx` IS the widget's mount node (no wrapper) — where `render()` keeps `_arxUi` across repaints.
  const hostEl = anyNodeInCard ? anyNodeInCard.closest(".arx") : null;
  const ui = hostEl ? hostEl._arxUi : null;
  if (e.provider === "local" && !e.playable) {
    if (e.same_machine) await revealLocal(e, act, anyNodeInCard);
    return;                                                 // cloud engine: the row's own ⬇ button is the way
  }
  const r = await act("open_file", { fileId: e.id });
  if (!r) return;
  if (r.ok && r.preview && ui) {
    ui.preview = r.preview;
    act("refresh", {});                                   // cheapest way to force a repaint with `ui` intact
    return;
  }
  if (r.ok && r.file && r.file.web_url) {
    window.open(r.file.web_url, "_blank", "noopener,noreferrer");
  }
}

// Ask the server to reveal a local file in its native file manager (self-host only — see `_same_machine` on
// the backend) and show the resolved path either way, so the operator can find it by hand if the OS call
// could not run (e.g. a headless install with no desktop).
async function revealLocal(e, act, anyNodeInCard) {
  const hostEl = anyNodeInCard ? anyNodeInCard.closest(".arx") : null;
  const ui = hostEl ? hostEl._arxUi : null;
  const r = await act("reveal_local_file", { fileId: e.id });
  if (ui) ui.pathHint = (r && r.ok) ? { name: e.name, path: r.path, opened: !!r.opened } : null;
  act("refresh", {});
}

function pathHintNote(ui, act) {
  const h = ui.pathHint;
  const note = el("div", "arx-note");
  const label = h.opened
    ? `«${h.name}» está en:`
    : `«${h.name}» está en (no pude abrir el gestor de archivos):`;
  note.appendChild(el("span", null, label + " "));
  note.appendChild(el("code", "arx-path", h.path));
  const copy = el("button", "arx-btn", "Copiar");
  copy.onclick = async () => {
    try { await navigator.clipboard.writeText(h.path); } catch (_) {}
  };
  const close = el("button", "arx-btn", "✕");
  close.onclick = () => { ui.pathHint = null; act("refresh", {}); };
  note.appendChild(copy);
  note.appendChild(close);
  return note;
}

function lightbox(ui, act) {
  const p = ui.preview;
  const box = el("div", "arx-lb");
  const top = el("div", "arx-lb-top");
  top.appendChild(el("b", null, p.name || ""));
  const close = el("button", "arx-lb-close", "✕");
  close.onclick = () => { ui.preview = null; act("refresh", {}); };
  top.appendChild(close);
  box.appendChild(top);

  const inner = el("div", "arx-lb-body");
  if (p.kind === "image") {
    const img = document.createElement("img");
    img.src = p.url;
    img.alt = "";
    inner.appendChild(img);
  } else {
    const frame = document.createElement("iframe");
    frame.src = p.url;
    frame.title = p.name || "documento";
    inner.appendChild(frame);
  }
  box.appendChild(inner);
  return box;
}

function footer(sel, act) {
  const f = el("div", "arx-foot");
  f.appendChild(el("span", "arx-ic", iconFor(sel)));
  f.appendChild(el("span", "arx-nm", sel.name || ""));
  const bits = [humanSize(sel.size), humanDate(sel.modified)].filter(Boolean).join(" · ");
  if (bits) f.appendChild(el("span", "arx-meta", bits));
  if (sel.web_url) {
    const a = document.createElement("a");
    a.className = "arx-btn";
    a.textContent = "Abrir en su web ↗";
    a.href = sel.web_url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    f.appendChild(a);
  }
  return f;
}

// The connect wizard, INSIDE the card — house rule: a widget's sub-flow never becomes a separate window. It
// is its OWN screen with a persistent close (✕, top-right, reachable without scrolling) AND the original
// "← Volver" at the bottom — the operator's own report was landing here with no way back out.
function connectPanel(d, act) {
  const wrap = el("div", "arx-cxwrap");

  const top = el("div", "arx-cxtop");
  top.appendChild(el("b", null, "Servicios de archivos en la nube"));
  const close = el("button", "arx-cxclose", "✕");
  close.title = "Cerrar y volver al explorador";
  close.onclick = () => act("close_connectors", {});
  top.appendChild(close);
  wrap.appendChild(top);

  const box = el("div", "arx-cx");
  box.appendChild(el("p", null,
    "zaelar entra en tu nube con TU permiso y solo para leer. La aplicación se registra una sola vez en "
    + "Configuración → Conectores; desde aquí eliges el permiso y das el consentimiento. Tu biblioteca en "
    + "este dispositivo no necesita nada de esto — ya funciona."));

  const provs = (d.providers || []);
  if (!provs.length) {
    box.appendChild(el("div", "arx-note", "No pude leer el catálogo de servicios. Prueba a actualizar."));
  }
  provs.forEach(p => {
    const card = el("div", "arx-prov");
    const head = el("div", "arx-field");
    head.appendChild(el("b", null, p.label || p.id));
    head.appendChild(el("span", "arx-badge" + (p.connected ? " ok" : ""),
      p.connected ? "conectado" : (p.app_configured ? "lista para conectar" : "sin registrar")));
    card.appendChild(head);
    if (p.note) card.appendChild(el("div", "arx-tiernote", p.note));

    if (p.connected) {
      if (p.tier_label) card.appendChild(el("div", "arx-tiernote", "Permiso concedido: " + p.tier_label));
      const off = el("button", "arx-btn", "Desconectar");
      off.onclick = () => act("disconnect_provider", { provider: p.id });
      card.appendChild(off);
    } else if (!p.app_configured) {
      card.appendChild(el("div", "arx-note",
        "Todavía no has registrado su aplicación. Entra en Configuración → Conectores y pega ahí su "
        + "client_id (una sola vez); después vuelve aquí y dale a Conectar."));
    } else {
      let tierId = p.default_tier || "";
      const tiers = p.tiers || [];
      if (tiers.length > 1) {
        const tierRow = el("div", "arx-field");
        tierRow.appendChild(el("label", null, "Permiso"));
        const sel = document.createElement("select");
        tiers.forEach(t => {
          const o = document.createElement("option");
          o.value = t.id;
          o.textContent = t.label;
          if (t.id === tierId) o.selected = true;
          sel.appendChild(o);
        });
        tierRow.appendChild(sel);
        card.appendChild(tierRow);
        const tnote = el("div", "arx-tiernote", "");
        const paint = () => {
          tierId = sel.value;
          const t = tiers.find(x => x.id === sel.value);
          tnote.textContent = t ? (t.note || "") : "";
        };
        sel.onchange = paint;
        paint();
        card.appendChild(tnote);
      }
      const go = el("button", "arx-btn", "Conectar " + (p.label || p.id));
      go.onclick = () => beginConsent(p.id, tierId, go, act);
      card.appendChild(go);
    }
    box.appendChild(card);
  });

  const back = el("button", "arx-btn", "← Volver al explorador");
  back.onclick = () => act("close_connectors", {});
  box.appendChild(back);
  wrap.appendChild(box);
  return wrap;
}

async function beginConsent(provider, tier, btn, act) {
  let win = null;
  try { win = window.open("", "_blank", "noopener"); } catch (_) { win = null; }
  btn.disabled = true;
  const prev = btn.textContent;
  btn.textContent = "Abriendo…";
  try {
    const r = await act("connect_provider", { provider, tier });
    if (r && r.ok && r.url) {
      if (win) win.location = r.url;
      else window.open(r.url, "_blank", "noopener");
    } else {
      if (win) { try { win.close(); } catch (_) {} }
      btn.textContent = (r && r.error) ? String(r.error).slice(0, 110) : "No se pudo abrir";
      return;
    }
  } catch (_) {
    if (win) { try { win.close(); } catch (_) {} }
    btn.textContent = "No se pudo abrir";
    return;
  } finally {
    setTimeout(() => { btn.disabled = false; if (btn.textContent === "Abriendo…") btn.textContent = prev; }, 1500);
  }
}
