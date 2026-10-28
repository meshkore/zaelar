// archivos · the wide-card sidebar of shelves and cloud services.

import { S, SHELF_ICON, SHELF_KINDS, el, shelfLabel, tt } from "./common.js";
import { TOR_TABS } from "./torrents.js";

// ── the SIDEBAR: shortcuts for this device's five shelves + every cloud service — the "quick access" a real
// file manager always has, so navigation never depends on the small header chips alone. Additive: the header
// keeps its own chips too, this just gives a wide card a second, richer way to the same places.
export function sidebar(d, act) {
  const side = el("div", "arx-side");
  const isLocal = d.provider === "local";

  const devHead = el("button", "arx-side-head", tt("device", null, "Este dispositivo"));
  devHead.title = tt("go_library", null, "Ir a tu biblioteca");
  devHead.onclick = () => act("set_provider", { provider: "local" });
  side.appendChild(devHead);

  SHELF_KINDS.forEach(k => {
    const active = isLocal && d.folder_id === `shelf:${k}`;
    const item = el("button", "arx-side-item" + (active ? " on" : ""));
    item.appendChild(el("span", "arx-ic", SHELF_ICON[k]));
    item.appendChild(el("span", "arx-side-nm", shelfLabel(k)));
    item.title = shelfLabel(k);
    item.onclick = async () => {
      if (!isLocal) await act("set_provider", { provider: "local" });
      act("open_folder", { folderId: `shelf:${k}` });
    };
    side.appendChild(item);
  });

  const provs = d.providers || [];
  if (provs.length) {
    side.appendChild(el("div", "arx-side-head", tt("cloud", null, "Nube")));
    provs.forEach(p => {
      const active = d.provider === p.id;
      const item = el("button", "arx-side-item" + (active ? " on" : ""));
      item.appendChild(el("span", "arx-side-dot" + (p.connected ? " conn" : "")));
      item.appendChild(el("span", "arx-side-nm", p.label || p.id));
      item.title = p.connected ? (p.label || p.id) : `${p.label || p.id} — sin conectar`;
      item.onclick = () => {
        if (p.connected) act("set_provider", { provider: p.id });
        else S.openCx(p.id);
      };
      side.appendChild(item);
    });
  }

  // V2-764 — the Torrents section and its three tabs, reachable from the quick-access column too.
  const tor = d.torrents || {};
  const torHead = el("button", "arx-side-head", tt("tor_section", null, "Torrents"));
  torHead.onclick = () => act("show_section", { section: "torrents" });
  side.appendChild(torHead);
  TOR_TABS().forEach(tb => {
    const on = d.section === "torrents" && tor.tab === tb.id;
    const item = el("button", "arx-side-item" + (on ? " on" : ""));
    item.appendChild(el("span", "arx-ic", tb.icon));
    item.appendChild(el("span", "arx-side-nm", tb.label));
    const n = tb.count(tor);
    if (n) item.appendChild(el("span", "arx-side-count", String(n)));
    item.onclick = () => act("show_section", { section: "torrents", tab: tb.id });
    side.appendChild(item);
  });

  const gear = el("button", "arx-side-item", null);
  gear.appendChild(el("span", "arx-ic", "⚙"));
  gear.appendChild(el("span", "arx-side-nm", tt("cloud_services", null, "Servicios en la nube")));
  gear.title = tt("cloud_manage", null, "Conectar o gestionar servicios en la nube");
  gear.onclick = () => S.openCx("");
  side.appendChild(gear);

  return side;
}

// ── ONE header row: this device + every cloud service, then the breadcrumb, then the tools ─────────────────
// Kept as a single row deliberately (see the module notes) — two half-empty bands read as "un doble header
// vacío" the instant a card has real width; one populated row reads as one screen.
