// archivos · the header (provider chips), the breadcrumb and the toolbar row.

import { S, el, tt } from "./common.js";
import { torrentCrumbs, torrentTools } from "./torrents.js";

export function header(d, act, ui) {
  const bar = el("div", "arx-bar");
  const isLocal = d.provider === "local";

  const chips = el("div", "arx-chips");
  const onTor = d.section === "torrents";
  const local = el("button", "arx-pchip" + (isLocal && !onTor ? " on" : ""), "💻");
  local.title = tt("device_lib", null, "Este dispositivo — tu biblioteca");
  local.onclick = () => { ui.preview = null; act("set_provider", { provider: "local" }); };
  chips.appendChild(local);
  // V2-764 — the Torrents section's own door, beside the library's («debería haber un icono ahí para poder
  // acceder al apartado de torrent»).
  const torChip = el("button", "arx-pchip tor" + (onTor ? " on" : ""), "🧲");
  torChip.title = tt("tor_section_tip", null, "Torrents — catálogo, descargas y semillas");
  torChip.dataset.section = "torrents";
  torChip.onclick = () => { ui.preview = null; act("show_section", { section: "torrents" }); };
  // V2-778 F0-6 — no door to a client that is not there (a hosted account has it off); kept while its section
  // is open so the reason stays reachable.
  const torOk = !!(d.torrents && d.torrents.available);
  if (torOk || onTor) chips.appendChild(torChip);

  (d.providers || []).forEach(p => {
    const letter = String(p.label || p.id || "?").trim().charAt(0).toUpperCase() || "?";
    const cls = "arx-pchip" + (d.provider === p.id ? " on" : (p.connected ? " conn" : " off"));
    const chip = el("button", cls, letter);
    const _pl = p.label || p.id;
    chip.title = d.provider === p.id ? tt("chip_here", {p:_pl}, `${_pl} — estás aquí`)
      : p.connected ? tt("chip_connected", {p:_pl}, `${_pl} — conectado, pulsa para entrar`)
      : tt("chip_off", {p:_pl}, `${_pl} — sin conectar, pulsa para conectarlo`);
    chip.onclick = () => {
      ui.preview = null;
      if (p.connected) act("set_provider", { provider: p.id });
      else S.openCx(p.id);
    };
    chips.appendChild(chip);
  });
  bar.appendChild(chips);
  bar.appendChild(el("div", "arx-divider"));

  if (onTor) {
    bar.appendChild(torrentCrumbs(d, act));
    bar.appendChild(torrentTools(d, act));
  } else {
    bar.appendChild(crumbsRow(d, ui, act));
    bar.appendChild(toolsRow(d, act));
  }
  return bar;
}

// The breadcrumb ALWAYS shows the real place (never a "search results" placeholder that repeats the query —
// the query already lives, once, in the search field itself). Long trails (a deeply-nested cloud folder)
// collapse to Home › … › the last couple of steps, never a 200-item wall; the "…" itself is a control that
// expands it inline, kept as pure UI state on `ui` (V2-608's own convention for a rename/delete flip).
export function crumbsRow(d, ui, act) {
  const crumbs = el("div", "arx-crumbs");
  const isLocal = d.provider === "local";
  const trail = d.trail || [];

  const home = el("button", "arx-crumb", isLocal ? tt("library", null, "Biblioteca") : (d.provider === "onedrive" ? "OneDrive" : tt("my_drive", null, "Mi unidad")));
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
    more.title = tt("crumbs_more", {n:hidden}, `${hidden} carpeta(s) más — pulsa para ver la ruta completa`);
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
    crumbs.appendChild(el("span", "arx-tag", n === 1 ? tt("one_result", null, "1 resultado") : tt("n_results", {n}, `${n} resultados`)));
  }
  return crumbs;
}

// The tools row: up · ONE search field (icon + text, count + clear live INSIDE it — never a second box
// duplicating the same query) · list/grid · refresh · cloud services.
export function toolsRow(d, act) {
  const tools = el("div", "arx-tools");

  const up = el("button", "arx-btn", "↑");
  up.title = tt("up_folder", null, "Subir una carpeta");
  up.disabled = !!d.query || !(d.trail || []).length;
  up.onclick = () => act("go_up", {});
  tools.appendChild(up);

  const find = el("div", "arx-find" + (d.query ? " active" : ""));
  find.appendChild(el("span", "arx-find-ic", "🔎"));
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = d.provider === "local" ? tt("search_lib", null, "Buscar en tu biblioteca") : tt("search_files", null, "Buscar en tus archivos");
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
    clear.title = tt("clear_search", null, "Quitar la búsqueda y volver");
    clear.onclick = () => act("clear_search", {});
    find.appendChild(clear);
  }
  tools.appendChild(find);

  const list = el("button", "arx-btn" + (d.mode !== "grid" ? " on" : ""), "☰");
  list.title = tt("view_list", null, "Vista de lista");
  list.onclick = () => act("set_view", { mode: "list" });
  const grid = el("button", "arx-btn" + (d.mode === "grid" ? " on" : ""), "▦");
  grid.title = tt("view_grid", null, "Vista de cuadrícula");
  grid.onclick = () => act("set_view", { mode: "grid" });
  tools.appendChild(list);
  tools.appendChild(grid);

  const ref = el("button", "arx-btn", "⟳");
  ref.title = tt("refresh", null, "Actualizar");
  ref.onclick = () => act("refresh", {});
  tools.appendChild(ref);

  const cx = el("button", "arx-btn", "⚙");
  cx.title = tt("cloud_services", null, "Servicios en la nube");
  cx.onclick = () => S.openCx("");
  tools.appendChild(cx);

  return tools;
}
