// archivos · the body: shelf grid, grid and list views, and each row's actions.

import { el, humanDate, humanSize, iconFor, shelfLabel, tt } from "./common.js";
import { deleteConfirm, openEntry, pathHintNote, renameField, revealLocal } from "./file.js";

export function body(d, act, ui) {
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
        d.query ? tt("no_match_named", {q:d.query}, `No hay nada que se llame «${d.query}».`) : tt("folder_empty", null, "Esta carpeta está vacía.")));
    }
    return box;
  }

  if (d.mode === "grid") box.appendChild(gridView(d, entries, act));
  else box.appendChild(listView(d, entries, act, ui));

  if (d.next) box.appendChild(el("div", "arx-note", tt("folder_more", null, "Hay más elementos en esta carpeta.")));
  return box;
}

export function shelfGrid(d, act) {
  const grid = el("div", "arx-shelves");
  (d.entries || []).forEach(e => {
    const tile = el("div", "arx-shelf");
    tile.appendChild(el("span", "arx-ic", iconFor(e)));
    tile.appendChild(el("b", null, e.name || ""));
    const n = typeof e.count === "number" ? e.count : 0;
    tile.appendChild(el("span", null, n === 1 ? tt("one_file", null, "1 archivo") : tt("n_files", {n}, `${n} archivos`)));
    tile.onclick = () => act("open_folder", { folderId: e.id });
    grid.appendChild(tile);
  });
  return grid;
}

export function gridView(d, entries, act) {
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
    const nm = el("span", "arx-nm", e.name || tt("unnamed", null, "(sin nombre)"));
    nm.title = e.name || "";
    tile.appendChild(nm);
    tile.onclick = () => isFolder ? act("open_folder", { folderId: e.id }) : openEntry(e, act, tile);
    grid.appendChild(tile);
  });
  return grid;
}

export function listView(d, entries, act, ui) {
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
    const nm = el("span", "arx-nm", e.name || tt("unnamed", null, "(sin nombre)"));
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
      if (d.query && e.shelf && shelfLabel(e.shelf)) {
        meta.appendChild(el("span", "arx-col-loc", (sizeTxt || dateTxt ? " · " : "") + shelfLabel(e.shelf)));
      }
      click.appendChild(meta);
    }
    // A finger has no double-click: on a touch screen ONE tap opens the file (V2-813 — on a phone a local file
    // did nothing on a tap, and the double-tap that opened it is a gesture nobody looks for there).
    click.onclick = () => isFolder ? act("open_folder", { folderId: e.id })
      : (_coarse() && e.provider === "local") ? openEntry(e, act, row) : selectOrPreview(e, act);
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

export function _coarse() {
  try { return window.matchMedia("(pointer: coarse)").matches; } catch (_) { return false; }
}

export function selectOrPreview(e, act) {
  // A cloud row's single click behaves as it always has: fetch the metadata + web link into the footer. A
  // local row does nothing on a single click — its always-visible action icons ARE the affordance, so there
  // is no separate "select" state to build and keep in sync.
  if (e.provider !== "local") act("open_file", { fileId: e.id });
}

export function rowActions(e, act, ui) {
  const acts = el("div", "arx-acts");
  const isLocalUnplayable = e.provider === "local" && !e.playable;

  if (isLocalUnplayable) {
    // Never a silent download here — see the module notes. `same_machine` (self-host) gets a "where is it"
    // affordance; a cloud engine gets nothing extra (the explicit ⬇ below is its only, and correct, way).
    if (e.same_machine) {
      const reveal = el("button", "arx-ac", "📁");
      reveal.title = tt("reveal", null, "Ver dónde está");
      reveal.onclick = () => revealLocal(e, act, reveal.closest(".arx"));
      acts.appendChild(reveal);
    }
    if (e.download_url) {
      const dl = el("button", "arx-ac", "⬇");
      dl.title = tt("download_copy", null, "Descargar una copia");
      dl.onclick = () => { try { window.open(e.download_url, "_blank", "noopener,noreferrer"); } catch (_) {} };
      acts.appendChild(dl);
    }
  } else {
    const openBtn = el("button", "arx-ac", e.provider === "local" ? primaryGlyph(e) : "↗");
    openBtn.title = e.provider === "local" ? tt("open", null, "Abrir") : tt("open_link", null, "Abrir el enlace");
    openBtn.onclick = () => openEntry(e, act, openBtn.closest(".arx"));
    acts.appendChild(openBtn);
  }

  if (e.provider === "local") {
    const ren = el("button", "arx-ac", "✎");
    ren.title = tt("rename", null, "Renombrar");
    // A pure UI-state flip (entering rename mode) has no server-side counterpart, so it asks for a repaint the
    // same way the host already repaints after any real action: `refresh` round-trips the store and the next
    // `render()` call sees `ui.renameId` set, on the SAME root (`root._arxUi` survives the repaint).
    ren.onclick = () => { ui.renameId = e.id; ui.renameVal = e.name || ""; act("refresh", {}); };
    acts.appendChild(ren);

    const cp = el("button", "arx-ac", "⧉");
    cp.title = tt("duplicate", null, "Duplicar");
    cp.onclick = () => act("copy_file", { fileId: e.id });
    acts.appendChild(cp);

    const del = el("button", "arx-ac danger", "🗑");
    del.title = tt("delete", null, "Borrar");
    del.onclick = () => { ui.confirmId = e.id; act("refresh", {}); };
    acts.appendChild(del);
  }
  return acts;
}

export function primaryGlyph(e) {
  if (e.file_kind === "video" || e.file_kind === "audio") return e.playable ? "▶" : "⬇";
  if (e.file_kind === "image" || e.file_kind === "document") return e.playable ? "👁" : "⬇";
  return "⬇";
}
