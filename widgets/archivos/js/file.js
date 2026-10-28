// archivos · one file: rename field, delete confirm, open/reveal, the lightbox and the footer.

import { el, humanDate, humanSize, iconFor, tt } from "./common.js";

export function renameField(e, act, ui) {
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

export function deleteConfirm(e, act, ui) {
  const wrap = el("div", "arx-confirm");
  wrap.appendChild(el("span", null, tt("confirm_delete", {name:e.name}, `¿Borrar «${e.name}»?`)));
  const yes = el("button", "arx-btn danger", tt("yes", null, "Sí"));
  yes.onclick = () => { ui.confirmId = ""; act("delete_file", { fileId: e.id }); };
  const no = el("button", "arx-btn", tt("no", null, "No"));
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
export async function openEntry(e, act, anyNodeInCard) {
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
export async function revealLocal(e, act, anyNodeInCard) {
  const hostEl = anyNodeInCard ? anyNodeInCard.closest(".arx") : null;
  const ui = hostEl ? hostEl._arxUi : null;
  const r = await act("reveal_local_file", { fileId: e.id });
  if (ui) ui.pathHint = (r && r.ok) ? { name: e.name, path: r.path, opened: !!r.opened } : null;
  act("refresh", {});
}

export function pathHintNote(ui, act) {
  const h = ui.pathHint;
  const note = el("div", "arx-note");
  const label = h.opened
    ? tt("reveal_at", {name:h.name}, `«${h.name}» está en:`)
    : tt("reveal_at_nofm", {name:h.name}, `«${h.name}» está en (no pude abrir el gestor de archivos):`);
  note.appendChild(el("span", null, label + " "));
  note.appendChild(el("code", "arx-path", h.path));
  const copy = el("button", "arx-btn", tt("copy", null, "Copiar"));
  copy.onclick = async () => {
    try { await navigator.clipboard.writeText(h.path); } catch (_) {}
  };
  const close = el("button", "arx-btn", "✕");
  close.onclick = () => { ui.pathHint = null; act("refresh", {}); };
  note.appendChild(copy);
  note.appendChild(close);
  return note;
}

export function lightbox(ui, act) {
  const p = ui.preview;
  const box = el("div", "arx-lb");
  const top = el("div", "arx-lb-top");
  top.dataset.strip = "";   // title + close manage their own width (ellipsis) — the phone never wraps them
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
    frame.title = p.name || tt("document_alt", null, "documento");
    inner.appendChild(frame);
  }
  box.appendChild(inner);
  return box;
}

export function footer(sel, act) {
  const f = el("div", "arx-foot");
  f.appendChild(el("span", "arx-ic", iconFor(sel)));
  f.appendChild(el("span", "arx-nm", sel.name || ""));
  const bits = [humanSize(sel.size), humanDate(sel.modified)].filter(Boolean).join(" · ");
  if (bits) f.appendChild(el("span", "arx-meta", bits));
  if (sel.web_url) {
    const a = document.createElement("a");
    a.className = "arx-btn";
    a.textContent = tt("open_on_web", null, "Abrir en su web ↗");
    a.href = sel.web_url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    f.appendChild(a);
  }
  return f;
}
