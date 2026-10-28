// archivos · the Torrents section (V2-764): tabs, catalogue, live downloads and seeds.

import { el, tt } from "./common.js";

// ── V2-764 · TORRENTS ─────────────────────────────────────────────────────────────────────────────────────
// Evaluated per paint (V2-694): a label table built at import time freezes the language it was built in.
export function TOR_TABS() {
  return [
    { id: "catalogo", icon: "🎞", label: tt("tor_catalog", null, "Catálogo"),
      count: t => ((t.catalog || {}).releases || []).length },
    { id: "descargas", icon: "⬇", label: tt("tor_downloads", null, "Descargas"), count: t => (t.downloads || []).length },
    { id: "semillas", icon: "🌱", label: tt("tor_seeds", null, "Semillas"), count: t => (t.seeds || []).length },
  ];
}

export function torHuman(n) {
  n = Number(n) || 0;
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
  if (n < 1073741824) return (n / 1048576).toFixed(1) + " MB";
  return (n / 1073741824).toFixed(2) + " GB";
}

export function torState(r) {
  if ((r.state === "downloading" || r.state === "downloading_metadata") && r.progress <= 0)
    return tt("st_sources", null, "Buscando fuentes");
  switch (String(r.state || "")) {
    case "seeding": return tt("st_seeding", null, "Compartiendo (semilla)");
    case "finished": return tt("st_finished", null, "Terminada");
    case "checking_files": case "checking_resume_data": return tt("st_checking", null, "Comprobando");
    case "queued_for_checking": return tt("st_queued", null, "En cola");
    case "allocating": return tt("st_allocating", null, "Reservando espacio");
  }
  return r.complete ? tt("st_finished", null, "Terminada") : tt("st_downloading", null, "Descargando");
}

export function torrentCrumbs(d, act) {
  const crumbs = el("div", "arx-crumbs");
  const tor = d.torrents || {};
  const root = el("button", "arx-crumb", tt("tor_section", null, "Torrents"));
  root.onclick = () => act("show_section", { section: "torrents", tab: "catalogo" });
  crumbs.appendChild(root);
  const tb = TOR_TABS().find(x => x.id === tor.tab) || TOR_TABS()[0];
  crumbs.appendChild(el("span", "arx-sep", "›"));
  const here = el("button", "arx-crumb", tb.label);
  here.disabled = true;
  crumbs.appendChild(here);
  const q = (tor.catalog || {}).query;
  if (tor.tab === "catalogo" && q) {
    crumbs.appendChild(el("span", "arx-sep", "›"));
    const qq = el("button", "arx-crumb", "«" + q + "»");
    qq.disabled = true;
    crumbs.appendChild(qq);
  }
  return crumbs;
}

export function torrentTools(d, act) {
  const tools = el("div", "arx-tools");
  const back = el("button", "arx-btn", "↩");
  back.title = tt("tor_back_lib", null, "Volver a la biblioteca");
  back.onclick = () => act("show_section", { section: "biblioteca" });
  tools.appendChild(back);
  const find = el("div", "arx-find");
  find.appendChild(el("span", "arx-find-ic", "🧲"));
  const input = document.createElement("input");
  input.type = "search";
  input.className = "arx-tor-q";
  input.placeholder = tt("tor_search", null, "Buscar torrents…");
  input.value = ((d.torrents || {}).catalog || {}).query || "";
  input.onkeydown = (ev) => {
    if (ev.key !== "Enter") return;
    const q = input.value.trim();
    if (q) act("torrent_search", { query: q });
  };
  find.appendChild(input);
  tools.appendChild(find);
  const ref = el("button", "arx-btn", "⟳");
  ref.title = tt("refresh", null, "Actualizar");
  ref.onclick = () => act("torrent_poll", {});
  tools.appendChild(ref);
  return tools;
}

export function torrentTabs(d, act) {
  const bar = el("div", "arx-tabs");
  const tor = d.torrents || {};
  TOR_TABS().forEach(tb => {
    const b = el("button", "arx-tab" + (tor.tab === tb.id ? " on" : ""));
    b.dataset.tab = tb.id;
    b.appendChild(el("span", null, tb.icon + " " + tb.label));
    const n = tb.count(tor);
    if (n) b.appendChild(el("span", "arx-n", String(n)));
    b.onclick = () => act("show_section", { section: "torrents", tab: tb.id });
    bar.appendChild(b);
  });
  return bar;
}

export function torrentBody(d, act, ui) {
  const box = el("div", "arx-body");
  const tor = d.torrents || {};
  if (tor.error) box.appendChild(el("div", "arx-tnote", tt("action_failed", null, "No se ha podido hacer"))).title = String(tor.error);
  if (tor.tab === "descargas" || tor.tab === "semillas") {
    if (!tor.available) {
      box.appendChild(el("div", "arx-tnote", tor.unavailable_reason || tt("tor_unavailable", null, "El cliente de descargas no está disponible.")));
      return box;
    }
    const rows = tor.tab === "semillas" ? (tor.seeds || []) : (tor.downloads || []);
    if (ui.torConfirm && !rows.some(r => r.id === ui.torConfirm)) ui.torConfirm = "";
    if (!rows.length) {
      box.appendChild(el("div", "arx-tnote", tor.tab === "semillas"
        ? tt("tor_empty_seeds", null, "No hay nada compartiéndose como semilla.")
        : tt("tor_empty_downloads", null, "No se está descargando nada. Busca en el catálogo y pulsa «Descargar».")));
      return box;
    }
    rows.forEach(r => box.appendChild(torrentRow(r, act, ui)));
    return box;
  }
  const cat = tor.catalog || {};
  if (cat.error) box.appendChild(el("div", "arx-tnote", tt("action_failed", null, "No se ha podido hacer"))).title = String(cat.error);
  const rels = cat.releases || [];
  if (!rels.length) {
    if (!cat.error) box.appendChild(el("div", "arx-tnote", tt("tor_empty_catalog", null,
      "Busca una peli, una serie o un disco y aquí verás lo que ofrece la red para descargar.")));
    return box;
  }
  const grid = el("div", "arx-cine");
  rels.forEach(r => grid.appendChild(filmCard(r, act)));
  box.appendChild(grid);
  return box;
}

export const FILM_ICON = { movie: "🎬", tv: "📺", music: "🎵", audio: "🎵", book: "📚", software: "💿", game: "🎮" };

export function filmCard(r, act) {
  const card = el("div", "arx-film");
  card.dataset.n = String(r.n);
  const poster = el("div", "arx-poster", FILM_ICON[r.kind] || "🎞");
  poster.appendChild(el("span", "arx-num", String(r.n)));
  if (r.resolution) poster.appendChild(el("span", "arx-res", r.resolution));
  card.appendChild(poster);
  const b = el("div", "arx-film-b");
  const t = el("div", "arx-film-t", r.title);
  t.title = r.title;
  b.appendChild(t);
  const m = el("div", "arx-film-m");
  if (r.size) m.appendChild(el("span", null, r.size));
  m.appendChild(el("span", "seed", tt("tor_seeders", { n: r.seeders }, "▲ " + r.seeders + " semillas")));
  if (r.published) m.appendChild(el("span", null, r.published.slice(0, 4)));
  b.appendChild(m);
  const dl = el("button", "arx-dl", tt("tor_download", null, "Descargar"));
  dl.onclick = () => act("torrent_download", { item: r.n });
  b.appendChild(dl);
  card.appendChild(b);
  return card;
}

export function torrentRow(r, act, ui) {
  const row = el("div", "arx-trow");
  row.dataset.id = r.id;
  const h = el("div", "arx-trow-h");
  h.appendChild(el("span", "arx-ic", r.kind === "video" ? "🎬" : r.kind === "audio" ? "🎵" : "📦"));
  const t = el("div", "arx-trow-t", r.title);
  t.title = r.title;
  h.appendChild(t);
  if (r.can_play) {
    const play = el("button", "arx-btn", "▶");
    play.title = tt("tor_play", null, "Reproducir");
    play.onclick = () => act("torrent_open", { id: r.id });
    h.appendChild(play);
  }
  if (r.complete) {
    const save = el("button", "arx-btn", "💾");
    save.title = tt("tor_save", null, "Guardar en la biblioteca");
    save.onclick = () => act("torrent_save", { id: r.id });
    h.appendChild(save);
  }
  const x = el("button", "arx-btn", "✕");
  x.title = tt("tor_cancel", null, "Cancelar y borrar el fichero");
  x.onclick = () => { ui.torConfirm = r.id; act("torrent_poll", {}); };
  h.appendChild(x);
  row.appendChild(h);
  if (!r.complete) {
    const bar = el("div", "arx-tbar");
    const fill = document.createElement("i");
    fill.style.width = Math.max(0, Math.min(100, r.progress || 0)) + "%";
    bar.appendChild(fill);
    row.appendChild(bar);
  }
  const s = el("div", "arx-trow-s");
  s.appendChild(el("span", null, (r.progress || 0) + "% · " + torState(r)));
  if (r.size) s.appendChild(el("span", null, torHuman(r.size)));
  if (!r.complete && r.download_rate > 0) s.appendChild(el("span", null, torHuman(r.download_rate) + "/s"));
  if (r.num_peers) s.appendChild(el("span", null, tt("tor_peers", { n: r.num_peers }, r.num_peers + " pares")));
  row.appendChild(s);
  if (ui.torConfirm === r.id) {
    const c = el("div", "arx-trow-s");
    c.appendChild(el("span", null, tt("tor_confirm", null, "¿Cancelo la descarga y borro el fichero?")));
    const yes = el("button", "arx-btn", tt("tor_yes", null, "Sí, borrar"));
    yes.onclick = () => { ui.torConfirm = ""; act("torrent_remove", { id: r.id }); };
    const no = el("button", "arx-btn", tt("tor_no", null, "No"));
    no.onclick = () => { ui.torConfirm = ""; act("torrent_poll", {}); };
    c.appendChild(yes); c.appendChild(no);
    row.appendChild(c);
  }
  return row;
}
