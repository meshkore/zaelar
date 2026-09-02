// archivos — cloud file explorer (V2-557).
//
// Shaped like the file managers people already know: breadcrumb on top, a toolbar with search and a
// list/grid switch, folders before files, and a detail strip for whatever is selected. That was the order:
// «as close as possible to the ones that exist», drivable with the mouse and by voice.
//
// TWO RULES THIS FILE CANNOT BREAK:
//  · Every string in here — file names, folder names, mime types — arrives from somebody's cloud drive. It is
//    UNTRUSTED, so it is written with textContent and never with innerHTML. A file named `<img onerror=…>` is
//    a legal file name in every provider we speak to.
//  · No network and no polling. The card asks for a listing ONCE on mount when the cache is stale
//    (`data.needs_refresh`) and after that it repaints only when `store.save()` pushes over SSE.

const STYLE_ID = "hb-archivos-style";

const CSS = `
.arx{display:flex;flex-direction:column;height:100%;min-height:0;font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial;color:var(--hb-ink,#0d1622)}
.arx-bar{display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid var(--hb-line,#eef1f6);flex:0 0 auto;flex-wrap:wrap}
.arx-crumbs{display:flex;align-items:center;gap:4px;flex:1 1 220px;min-width:0;overflow:hidden}
.arx-crumb{background:none;border:0;padding:2px 6px;border-radius:6px;color:var(--hb-accent,#2f6df6);cursor:pointer;font:inherit;max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arx-crumb:hover{background:var(--hb-bg-soft,#f5f7fb)}
.arx-crumb[disabled]{color:var(--hb-ink,#0d1622);cursor:default}
.arx-sep{color:var(--hb-muted-2,#9aa4b2);flex:0 0 auto}
.arx-tools{display:flex;align-items:center;gap:6px;flex:0 0 auto}
.arx-find{display:flex;align-items:center;gap:4px;background:var(--hb-bg-soft,#f5f7fb);border:1px solid var(--hb-line,#eef1f6);border-radius:8px;padding:3px 6px}
.arx-find input{border:0;background:none;outline:none;font:inherit;color:var(--hb-ink,#0d1622);width:130px}
.arx-btn{border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);border-radius:8px;padding:3px 8px;cursor:pointer;font:inherit;line-height:1.6}
.arx-btn:hover{background:var(--hb-bg-soft,#f5f7fb)}
.arx-btn[disabled]{opacity:.4;cursor:default}
.arx-btn.on{border-color:var(--hb-accent,#2f6df6);color:var(--hb-accent,#2f6df6)}
.arx-body{flex:1 1 auto;min-height:0;overflow:auto;padding:6px}
.arx-row{display:flex;align-items:center;gap:10px;padding:6px 8px;border-radius:9px;cursor:pointer}
.arx-row:hover{background:var(--hb-bg-soft,#f5f7fb)}
.arx-row.sel{background:var(--hb-bg-soft,#f5f7fb);box-shadow:inset 2px 0 0 var(--hb-accent,#2f6df6)}
.arx-ic{flex:0 0 auto;font-size:16px;width:20px;text-align:center}
.arx-nm{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arx-meta{flex:0 0 auto;color:var(--hb-muted,#67707d);font-size:11.5px;white-space:nowrap}
.arx-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(116px,1fr));gap:8px}
.arx-tile{display:flex;flex-direction:column;align-items:center;gap:5px;padding:12px 6px;border:1px solid var(--hb-line,#eef1f6);border-radius:12px;cursor:pointer;background:var(--hb-bg,#fff)}
.arx-tile:hover{background:var(--hb-bg-soft,#f5f7fb)}
.arx-tile.sel{border-color:var(--hb-accent,#2f6df6)}
.arx-tile .arx-ic{font-size:26px;width:auto}
.arx-tile .arx-nm{width:100%;text-align:center;font-size:12px;white-space:normal;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.arx-note{margin:10px;padding:10px 12px;border-radius:10px;background:var(--hb-bg-soft,#f5f7fb);border:1px solid var(--hb-line,#eef1f6);color:var(--hb-muted,#67707d)}
.arx-note.warn{background:var(--hb-warn-bg,#fff8e6);border-color:var(--hb-warn-border,#f5d78e);color:var(--hb-warn-ink,#7a5b00)}
.arx-note.bad{border-color:var(--hb-risk,#d64545);color:var(--hb-risk,#d64545)}
.arx-foot{flex:0 0 auto;border-top:1px solid var(--hb-line,#eef1f6);padding:8px 10px;display:flex;gap:10px;align-items:center}
.arx-foot .arx-nm{font-weight:600}
.arx-cx{padding:12px}
.arx-cx h4{margin:0 0 4px;font-size:14px}
.arx-cx p{margin:0 0 10px;color:var(--hb-muted,#67707d);font-size:12px}
.arx-prov{border:1px solid var(--hb-line,#eef1f6);border-radius:12px;padding:10px;margin-bottom:10px;background:var(--hb-bg,#fff)}
.arx-prov b{font-size:13px}
.arx-field{display:flex;align-items:center;gap:8px;margin:6px 0}
.arx-field label{flex:0 0 96px;color:var(--hb-muted,#67707d);font-size:12px}
.arx-field input,.arx-field select{flex:1 1 auto;min-width:0;border:1px solid var(--hb-line,#eef1f6);border-radius:7px;padding:4px 7px;font:inherit;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
.arx-tiernote{color:var(--hb-muted-2,#9aa4b2);font-size:11.5px;margin:2px 0 8px}
.arx-badge{font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid var(--hb-line,#eef1f6);color:var(--hb-muted,#67707d)}
.arx-badge.ok{border-color:var(--hb-accent2,#12a594);color:var(--hb-accent2,#12a594)}
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

function iconFor(entry) {
  if (entry && entry.kind === "folder") return "📁";
  const mime = String((entry && entry.mime) || "").toLowerCase();
  for (const [re, ic] of ICONS) if (re.test(mime)) return ic;
  return "📄";
}

// Sizes are shown only when the provider gave one. A native Google document has no size, and printing «0 B»
// next to every document somebody owns is a statement that happens to be false.
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

export function render(root, data, ctx) {
  if (!document.getElementById(STYLE_ID)) {
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = CSS;
    document.head.appendChild(s);
  }
  const d = data || {};
  // Returns the backend's reply so an action that ANSWERS (a consent URL, a search) can be read. Kept
  // await-able rather than fire-and-forget: `connect_provider` is useless if its `url` is discarded.
  const act = async (name, payload) => {
    try { return ctx && ctx.action ? await ctx.action(name, payload || {}) : null; } catch (_) { return null; }
  };

  root.textContent = "";
  const wrap = el("div", "arx");
  root.appendChild(wrap);

  if (d.panel === "connect" || (!d.connected && !d.error)) {
    wrap.appendChild(connectPanel(d, act));
    return;
  }

  wrap.appendChild(toolbar(d, act));
  wrap.appendChild(body(d, act));
  if (d.selected) wrap.appendChild(footer(d.selected, act));

  // ONE listing request on mount when the cache is stale. The flag lives on the DOM node, not in module
  // scope: the host re-renders this card on every data push, and a module-level guard would make the very
  // first refresh the last one this widget ever asks for.
  if (d.needs_refresh && d.connected && !root._arxAsked) {
    root._arxAsked = true;
    act("refresh", {});
  }
  if (!d.needs_refresh) root._arxAsked = false;
}

function toolbar(d, act) {
  const bar = el("div", "arx-bar");

  const crumbs = el("div", "arx-crumbs");
  if (d.query) {
    crumbs.appendChild(el("span", "arx-sep", "🔎"));
    crumbs.appendChild(el("span", "arx-nm", `Resultados de «${d.query}»`));
  } else {
    const home = el("button", "arx-crumb", d.provider === "onedrive" ? "OneDrive" : "Mi unidad");
    home.onclick = () => act("go_home", {});
    if (!(d.trail || []).length) home.disabled = true;
    crumbs.appendChild(home);
    (d.trail || []).forEach((t, i, arr) => {
      crumbs.appendChild(el("span", "arx-sep", "›"));
      const b = el("button", "arx-crumb", t.name || "…");
      if (i === arr.length - 1) b.disabled = true;
      else b.onclick = () => act("open_folder", { folderId: t.id });
      crumbs.appendChild(b);
    });
  }
  bar.appendChild(crumbs);

  const tools = el("div", "arx-tools");

  const up = el("button", "arx-btn", "↑");
  up.title = "Subir una carpeta";
  up.disabled = !!d.query || !(d.trail || []).length;
  up.onclick = () => act("go_up", {});
  tools.appendChild(up);

  const find = el("div", "arx-find");
  find.appendChild(el("span", null, "🔎"));
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = "Buscar en mis archivos";
  input.value = d.query || "";
  input.onkeydown = (ev) => {
    if (ev.key !== "Enter") return;
    const q = input.value.trim();
    if (q) act("search_files", { query: q });
    else act("clear_search", {});
  };
  find.appendChild(input);
  tools.appendChild(find);

  if (d.query) {
    const clear = el("button", "arx-btn", "✕");
    clear.title = "Quitar la búsqueda";
    clear.onclick = () => act("clear_search", {});
    tools.appendChild(clear);
  }

  const list = el("button", "arx-btn" + (d.mode !== "grid" ? " on" : ""), "☰");
  list.title = "Lista";
  list.onclick = () => act("set_view", { mode: "list" });
  const grid = el("button", "arx-btn" + (d.mode === "grid" ? " on" : ""), "▦");
  grid.title = "Cuadrícula";
  grid.onclick = () => act("set_view", { mode: "grid" });
  tools.appendChild(list);
  tools.appendChild(grid);

  const connected = (d.providers || []).filter(p => p.connected);
  if (connected.length > 1) {
    const sw = el("button", "arx-btn", d.provider === "onedrive" ? "OneDrive" : "Drive");
    sw.title = "Cambiar de servicio";
    sw.onclick = () => {
      const ids = connected.map(p => p.id);
      const next = ids[(ids.indexOf(d.provider) + 1) % ids.length];
      act("set_provider", { provider: next });
    };
    tools.appendChild(sw);
  }

  const ref = el("button", "arx-btn", "⟳");
  ref.title = "Actualizar";
  ref.onclick = () => act("refresh", {});
  tools.appendChild(ref);

  const cx = el("button", "arx-btn", "⚙");
  cx.title = "Servicios de archivos";
  cx.onclick = () => act("open_connectors", {});
  tools.appendChild(cx);

  bar.appendChild(tools);
  return bar;
}

function body(d, act) {
  const box = el("div", "arx-body");

  if (d.error) {
    box.appendChild(el("div", "arx-note bad", d.error));
    return box;
  }
  // A permission that cannot list is not an empty drive. Saying which one it is here is the whole reason the
  // service layer answers `ok` with a `reason` instead of an empty array.
  if (d.reason) box.appendChild(el("div", "arx-note warn", d.reason));

  const entries = d.entries || [];
  if (!entries.length) {
    if (!d.reason) {
      box.appendChild(el("div", "arx-note",
        d.query ? `No hay nada que se llame o diga «${d.query}».` : "Esta carpeta está vacía."));
    }
    return box;
  }

  const grid = d.mode === "grid";
  const holder = grid ? el("div", "arx-grid") : el("div");
  entries.forEach(e => {
    const isFolder = e.kind === "folder";
    const sel = d.selected && d.selected.id === e.id;
    const node = el("div", (grid ? "arx-tile" : "arx-row") + (sel ? " sel" : ""));
    node.appendChild(el("span", "arx-ic", iconFor(e)));
    const nm = el("span", "arx-nm", e.name || "(sin nombre)");
    nm.title = e.name || "";
    node.appendChild(nm);
    if (!grid) {
      const bits = [humanSize(e.size), humanDate(e.modified)].filter(Boolean).join(" · ");
      node.appendChild(el("span", "arx-meta", bits));
    }
    node.onclick = () => isFolder ? act("open_folder", { folderId: e.id }) : act("open_file", { fileId: e.id });
    holder.appendChild(node);
  });
  box.appendChild(holder);

  if (d.next) {
    const more = el("div", "arx-note", "Hay más elementos en esta carpeta.");
    box.appendChild(more);
  }
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

// The connect wizard, INSIDE the card — house rule: a widget's sub-flow never becomes a separate window. The
// same catalog is also rendered in ⚙ → Conectores; both read `providers`, so they cannot drift apart.
//
// THE SPLIT between the two surfaces is not cosmetic, and it is the reason no credential input lives here:
// registering the OAuth application (client_id / client_secret) belongs to ⚙ → Conectores, and this card only
// carries INTENT — «connect this one», «drop that one». Same boundary V2-520 drew for messaging: the voice
// path, which reaches exactly these declared actions, transports intent and never a credential.
function connectPanel(d, act) {
  const box = el("div", "arx-cx");
  box.appendChild(el("h4", null, "Conectar tus archivos"));
  box.appendChild(el("p", null,
    "zaelar entra en tu nube con TU permiso y solo para leer. La aplicación se registra una sola vez en "
    + "Configuración → Conectores; desde aquí eliges el permiso y das el consentimiento."));

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
      // Saying WHERE it is done beats a disabled button: the operator can act on this sentence.
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

  // Only offered when there IS an explorer to go back to. With nothing connected, `close_connectors` would
  // return to a card whose only honest content is this same panel — a button that appears to do nothing.
  if (d.connected) {
    const back = el("button", "arx-btn", "← Volver al explorador");
    back.onclick = () => act("close_connectors", {});
    box.appendChild(back);
  }
  return box;
}

// The consent window is opened SYNCHRONOUSLY on the click and its address filled in afterwards. Opening it
// after the await instead would be a pop-up blocked by every browser: by then the gesture has been spent.
// The widget itself never speaks to the provider — it asks its own backend, which answers with the URL.
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
