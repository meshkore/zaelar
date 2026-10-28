// youtube widget — the ACCOUNT layer: brand marks, the sources shelf and the platform icons in the nav.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { Y } from "./state.js";
import { el, tt } from "./shared.js";

// ── ACCOUNT layer (V2-597) ────────────────────────────────────────────────────────────────────────────────
// Brand mark, inline SVG (simple-icons outline path, CC0) — never a CDN: widget.js touches no network.
export const _BRAND = {
  youtube: {color: "#FF0000", path: "M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 " +
    "12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 " +
    "3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 " +
    "2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"},
};

export function brandIcon(pid, on){
  const wrap = el("button", "hb-yt-picon" + (on ? " on" : ""));
  const b = _BRAND[pid] || null;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", b ? b.path : "M12 2a10 10 0 1 0 0 20a10 10 0 0 0 0-20z");
  path.setAttribute("fill", b ? b.color : "currentColor");
  svg.appendChild(path);
  wrap.appendChild(svg);
  return wrap;
}

// The SOURCES shelf (V2-632): every video source with its honest state. A usable one opens the ⚙ Conectores
// section on it (2026-10-04) — the card no longer carries its own connect wizard or status screen.
export function renderConn(E, root, data, ctx){
  const box = E.conn;
  if(!box) return;
  
  root.classList.toggle("hb-yt-connmode", !!Y.screen);
  const plug = root.querySelector(".hb-yt-plug"); if(plug) plug.classList.toggle("on", !!Y.screen);
  if(root._hbYtPaintTabs) root._hbYtPaintTabs();
  box.textContent = "";
  if(!Y.screen) return;
  const repaint = () => renderConn(E, root, data, ctx);

  const back = () => {
    if(root._hbYtSelectTab) root._hbYtSelectTab(Y.tab || "inicio");
    else { Y.screen = null; repaint(); }
  };
  const crumb = el("div", "hb-ytw-crumb", tt("back", null, "‹ Volver"));
  crumb.addEventListener("click", back);
  box.appendChild(crumb);

  // THE SHELF (V2-632): every video source, live or not, with its honest state — the messaging igrid
  // language. YouTube disabled says WHY (no OAuth client yet); a planned provider says it is not
  // built. Nothing here pretends: a box that cannot open never wears an active face.
  if(Y.screen.view === "shelf"){
    const grid = el("div", "hb-yt-igrid");
    const shelf = Array.isArray(data.connector_shelf) && data.connector_shelf.length
      ? data.connector_shelf
      : [{id: "youtube", label: "YouTube", state: "planned", connected: false, note: ""}];
    const enabled = !!data.accounts_enabled;
    shelf.forEach((rw) => {
      const usable = rw.id === "youtube" && enabled;
      const bx = el("button", "hb-yt-ibox" + (rw.connected ? " conn" : "") + (usable ? "" : " off"));
      const ic = el("span", "hb-yt-iicon");
      if(_BRAND[rw.id]){
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", _BRAND[rw.id].path);
        path.setAttribute("fill", _BRAND[rw.id].color);
        svg.appendChild(path); ic.appendChild(svg);
      } else {
        ic.textContent = (rw.label || rw.id || "?").slice(0, 1).toUpperCase();
      }
      bx.appendChild(ic);
      bx.appendChild(el("span", "hb-yt-ilabel", rw.label || rw.id));
      bx.appendChild(el("span", "hb-yt-isub",
        rw.connected ? tt("st_connected", null, "Conectada")
          : usable ? tt("st_disconnected", null, "Sin conectar — toca para conectarla")
          : rw.state === "not-possible" ? tt("st_impossible", null, "No es posible")
          : tt("st_soon", null, "No disponible aún")));
      bx.addEventListener("click", () => {
        if(usable){ ctx.openConnector(rw.id); return; }
        // `rw.note` is the catalog's own wording (Castilian): the reason is said in HIS language, the note is the tooltip
        Y.connErr = (rw.label || rw.id) + ": " + (rw.id === "youtube"
            ? tt("why_impossible", null, "de momento no es posible conectar la cuenta — falta registrar el cliente OAuth.")
            : rw.state === "not-possible" ? tt("st_impossible", null, "No es posible")
            : tt("why_soon", null, "todavía no está construido."));
        Y.connErrTip = rw.note || "";
        repaint();
      });
      grid.appendChild(bx);
    });
    box.appendChild(grid);
    if(Y.connErr) box.appendChild(el("div", "hb-yt-shnote", Y.connErr)).title = Y.connErrTip;
  }
}

export function paintAccount(root, E, data, ctx){
  // ACCOUNT layer (V2-597) — the card asks for ONE platform re-sync when the cache is stale (the archivos
  // needs_refresh pattern; local file reads server-side, no provider network) and paints the platform icons
  // and the sources shelf.
  // V2-603 F2 — the account layer is HIDDEN whole while no OAuth client exists anywhere (operator's
  // directive, 2026-09-06: «until that is done I do not want the connector active, leave it deactivated and
  // hidden»). Not a disabled button and not a wizard that dead-ends: no platform row, no connect screen, and
  // no `sync_platforms` chatter either. The player itself is untouched — searching, playing and lists never
  // depended on an account. `accounts_enabled` is DERIVED server-side, so this whole surface comes back on
  // its own the day a client id exists.
  if(!data.accounts_enabled){
    if(E.dots){ E.dots.textContent = ""; E.dots.style.display = "none"; }
    // V2-632: the SHELF survives the gate — the operator asked to SEE the sources, disabled and honest
    // (its note included).
    renderConn(E, root, data, ctx);
  } else {
  if(E.dots) E.dots.style.display = "";
  if(data.platforms_stale && ctx && ctx.action && Date.now() - Y.syncAsked > 60000){
    Y.syncAsked = Date.now();
    try{ ctx.action("sync_platforms", {}); }catch(_e){}
  }
  if(E.dots){
    E.dots.textContent = "";
    const rows = Array.isArray(data.platforms) ? data.platforms : [];
    const list = rows.length ? rows : [{id: "youtube", label: "YouTube", connected: false, app_configured: false}];
    list.forEach((r) => {
      const ic = brandIcon(r.id, !!r.connected);
      ic.title = r.connected ? tt("dot_connected", {label: r.label || r.id}, "{label}: cuenta conectada")
                             : tt("dot_disconnected", {label: r.label || r.id}, "{label}: sin conectar — toca para conectarla");
      ic.setAttribute("aria-label", ic.title);
      ic.addEventListener("click", () => ctx.openConnector(r.id));   // ⚙ Conectores, the one door
      E.dots.appendChild(ic);
    });
  }
  renderConn(E, root, data, ctx);
  }
}
