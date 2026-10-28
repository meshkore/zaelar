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

import { CSS } from "./js/style.js";
import { S, el, ensureTierObserver } from "./js/common.js";
import { footer, lightbox } from "./js/file.js";
import { header } from "./js/header.js";
import { body } from "./js/list.js";
import { sidebar } from "./js/sidebar.js";
import { torrentBody, torrentTabs } from "./js/torrents.js";

export function render(root, data, ctx) {
  S.T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  S.LANG = (ctx && ctx.lang) || "en";
  S.openCx = id => { try { ctx.openConnector(id || ""); } catch (_) {} };
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

  const layout = el("div", "arx-layout");
  layout.appendChild(sidebar(d, act));
  const main = el("div", "arx-main");
  main.appendChild(header(d, act, ui));
  const onTorrents = d.section === "torrents";
  if (onTorrents) {
    main.appendChild(torrentTabs(d, act));
    main.appendChild(torrentBody(d, act, ui));
  } else {
    main.appendChild(body(d, act, ui));
    if (d.selected) main.appendChild(footer(d.selected, act));
  }
  layout.appendChild(main);
  root.appendChild(layout);
  if (ui.preview && !onTorrents) root.appendChild(lightbox(ui, act));

  // V2-764 — keep the live lists moving while anything is still filling (the retired widget's own rule:
  // one timer per card, cleared and re-armed on every render, stopped once nothing is downloading).
  if (root._arxPoll) { clearTimeout(root._arxPoll); root._arxPoll = 0; }
  const tor = d.torrents || {};
  if (onTorrents && tor.available && (tor.downloads || []).some(r => r.progress < 100)) {
    root._arxPoll = setTimeout(() => act("torrent_poll", {}), 1500);
  }

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
