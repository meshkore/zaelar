// fotos — a Google-Photos-style gallery, virtualized (V2-564).
//
// The operator's own worry: "if I start scrolling and there are a thousand photos on screen, that will eat a
// lot of memory". So this grid never mounts more <img> nodes than fit near the viewport — it computes ROWS
// (year headers and item rows) as a pure layout, then only creates/keeps DOM nodes for the rows within a
// buffer of the visible scroll range, recycling the rest. Two rules this file cannot break, same as every
// other widget: no fetch/WebSocket here (the Picker session and paging go through `ctx.action`, never a
// direct call), and every string that came from Google (a filename) is untrusted — textContent only.

const STYLE_ID = "hb-fotos-style";

const CSS = `
.fts{display:flex;flex-direction:column;height:100%;min-height:0;font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial;color:var(--hb-ink,#0d1622)}
.fts-bar{display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid var(--hb-line,#eef1f6);flex:0 0 auto;flex-wrap:wrap}
.fts-find{display:flex;align-items:center;gap:4px;background:var(--hb-bg-soft,#f5f7fb);border:1px solid var(--hb-line,#eef1f6);border-radius:8px;padding:3px 6px;flex:1 1 200px;min-width:120px}
.fts-find input{border:0;background:none;outline:none;font:inherit;color:var(--hb-ink,#0d1622);width:100%}
.fts-btn{border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);border-radius:8px;padding:3px 8px;cursor:pointer;font:inherit;line-height:1.6}
.fts-btn:hover{background:var(--hb-bg-soft,#f5f7fb)}
.fts-btn[disabled]{opacity:.4;cursor:default}
.fts-count{color:var(--hb-muted,#67707d);font-size:11.5px;white-space:nowrap}
.fts-scroll{flex:1 1 auto;min-height:0;overflow:auto;position:relative}
.fts-canvas{position:relative}
.fts-year{position:absolute;left:0;right:0;font-weight:700;font-size:15px;padding:6px 10px;color:var(--hb-ink,#0d1622);background:var(--hb-bg,#fff)}
.fts-tile{position:absolute;border-radius:10px;overflow:hidden;background:var(--hb-bg-soft,#f5f7fb);cursor:pointer}
.fts-tile img{width:100%;height:100%;object-fit:cover;display:block}
.fts-tile .ph{width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:var(--hb-muted-2,#9aa4b2);font-size:20px}
.fts-note{margin:10px;padding:10px 12px;border-radius:10px;background:var(--hb-bg-soft,#f5f7fb);border:1px solid var(--hb-line,#eef1f6);color:var(--hb-muted,#67707d)}
.fts-note.bad{border-color:var(--hb-risk,#d64545);color:var(--hb-risk,#d64545)}
.fts-cx{padding:16px;text-align:center}
.fts-cx p{margin:0 0 12px;color:var(--hb-muted,#67707d);font-size:12.5px}
`;

const TILE = 130;   // px, square-ish tile including gap
const GAP = 6;
const HEADER_H = 30;

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = String(text);   // untrusted by default — never innerHTML
  return n;
}

// ── pure layout: items (already newest-first, grouped by year server-side) -> a list of ROWS ────────────
function buildRows(items, cols) {
  const rows = [];
  let y = 0;
  let curYear = null;
  let rowItems = [];
  const flushRow = () => {
    if (rowItems.length) { rows.push({ type: "items", top: y, h: TILE, items: rowItems }); y += TILE + GAP; rowItems = []; }
  };
  for (const it of items) {
    const yr = (it.taken_at || "").slice(0, 4) || "?";
    if (yr !== curYear) {
      flushRow();
      rows.push({ type: "header", top: y, h: HEADER_H, year: yr });
      y += HEADER_H;
      curYear = yr;
    }
    rowItems.push(it);
    if (rowItems.length === cols) flushRow();
  }
  flushRow();
  return { rows, total: y };
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

  root.textContent = "";
  const wrap = el("div", "fts");
  root.appendChild(wrap);

  if (!d.connected) {
    wrap.appendChild(connectPanel(d, act));
    return;
  }

  wrap.appendChild(toolbar(d, act));
  wrap.appendChild(gallery(d, act));
}

function connectPanel(d, act) {
  const box = el("div", "fts-cx");
  box.appendChild(el("p", "", d.app_configured
    ? "Google Photos no está conectado. Al pulsar se abrirá el consentimiento de Google."
    : "Google Photos necesita una app OAuth registrada una vez en Configuración → Conectores."));
  const b = el("button", "fts-btn", "Conectar Google Photos");
  b.onclick = async () => {
    b.disabled = true;
    const res = await act("connect", {});
    if (res && res.ok && res.url) {
      // Opened synchronously in the click handler, or the browser blocks the popup (rule §6.2).
      window.open(res.url, "_blank", "noopener");
    } else {
      box.appendChild(el("p", "fts-note bad", (res && res.error) || "No se pudo abrir el selector."));
    }
    b.disabled = false;
  };
  box.appendChild(b);
  if (d.error) box.appendChild(el("p", "fts-note bad", d.error));
  return box;
}

function toolbar(d, act) {
  const bar = el("div", "fts-bar");
  const find = el("div", "fts-find");
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "fotos del año pasado, o de un viaje…";
  input.value = (d.active_filter && d.active_filter.query) || "";
  find.appendChild(input);
  bar.appendChild(find);

  const searchBtn = el("button", "fts-btn", "Buscar");
  searchBtn.onclick = () => { const q = input.value.trim(); if (q) act("search", { query: q }); };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") searchBtn.click(); });
  bar.appendChild(searchBtn);

  if (d.active_filter && Object.keys(d.active_filter).length) {
    const clearBtn = el("button", "fts-btn", "Quitar filtro");
    clearBtn.onclick = () => act("clear_search", {});
    bar.appendChild(clearBtn);
  }

  const labelBtn = el("button", "fts-btn", "Etiquetar última tanda");
  labelBtn.onclick = () => {
    const label = window.prompt("¿Qué nombre le pongo a la última tanda importada?", "");
    if (label && label.trim()) act("label_batch", { label: label.trim() });
  };
  bar.appendChild(labelBtn);

  const addBtn = el("button", "fts-btn", "Elegir más fotos");
  addBtn.onclick = async () => {
    addBtn.disabled = true;
    const res = await act("connect", {});
    if (res && res.ok && res.url) window.open(res.url, "_blank", "noopener");
    addBtn.disabled = false;
  };
  bar.appendChild(addBtn);

  bar.appendChild(el("span", "fts-count", `${d.total || 0} fotos`));
  return bar;
}

function gallery(d, act) {
  const wrap = el("div", "fts-scroll");
  const items = d.items || [];
  if (d.session_pending) {
    wrap.appendChild(el("div", "fts-note", "Esperando a que termines de elegir en el selector de Google…"));
  }
  if (!items.length) {
    wrap.appendChild(el("div", "fts-note", d.session_pending ? "" : "Todavía no hay fotos importadas."));
    return wrap;
  }

  const canvas = el("div", "fts-canvas");
  wrap.appendChild(canvas);

  // Column count depends on the card's actual width; recomputed on resize.
  let cols = 4;
  let layout = { rows: [], total: 0 };
  const mounted = new Map();   // row index -> DOM node, so we recycle rather than rebuild every scroll tick

  const recompute = () => {
    const w = wrap.clientWidth || 600;
    cols = Math.max(2, Math.floor(w / (TILE + GAP)));
    layout = buildRows(items, cols);
    canvas.style.height = layout.total + "px";
    for (const node of mounted.values()) node.remove();
    mounted.clear();
    paint();
  };

  const paint = () => {
    const viewTop = wrap.scrollTop;
    const viewH = wrap.clientHeight || 400;
    const buffer = viewH;   // one screen of buffer above/below, so scrolling doesn't pop tiles in visibly
    const lo = viewTop - buffer;
    const hi = viewTop + viewH + buffer;
    const keep = new Set();
    layout.rows.forEach((row, i) => {
      if (row.top + row.h < lo || row.top > hi) return;
      keep.add(i);
      if (mounted.has(i)) return;
      const node = row.type === "header" ? paintHeader(row) : paintRow(row, cols);
      mounted.set(i, node);
      canvas.appendChild(node);
    });
    for (const [i, node] of mounted) {
      if (!keep.has(i)) { node.remove(); mounted.delete(i); }
    }
    // Bottom sentinel: real infinite scroll, not a silent truncation.
    if (d.has_more && viewTop + viewH >= layout.total - viewH) act("more", {});
  };

  wrap.addEventListener("scroll", () => requestAnimationFrame(paint));
  const ro = new ResizeObserver(() => recompute());
  ro.observe(wrap);
  recompute();
  return wrap;
}

function paintHeader(row) {
  const h = el("div", "fts-year", row.year === "?" ? "Sin fecha" : row.year);
  h.style.top = row.top + "px";
  return h;
}

function paintRow(row, cols) {
  const frag = document.createDocumentFragment();
  const holder = el("div");
  holder.style.position = "absolute";
  holder.style.top = row.top + "px";
  holder.style.left = "0";
  holder.style.right = "0";
  holder.style.height = TILE + "px";
  row.items.forEach((it, idx) => {
    const t = el("div", "fts-tile");
    t.style.left = (idx * (TILE + GAP)) + "px";
    t.style.top = "0";
    t.style.width = TILE + "px";
    t.style.height = TILE + "px";
    t.title = it.filename || "";
    if (it.thumb) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = it.thumb;
      img.alt = it.filename || "";
      t.appendChild(img);
    } else {
      t.appendChild(el("div", "ph", "🖼"));
    }
    holder.appendChild(t);
  });
  frag.appendChild(holder);
  return holder;
}
