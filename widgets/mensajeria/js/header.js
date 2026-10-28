// js/header.js — The dashboard header of the card: home, title and section crumb, the channel dots, connectors/settings/clear.
import { S, ORDER, PLAT, selectPlatform, tt } from "./state.js";
import { brandIcon, el, iconButton } from "./dom.js";
import { mailWhere } from "./mailrail.js";
import * as I from "/frontend/app/lib/icons.js";   // the shell's own glyphs (V2-831 T-12)

// The dashboard header of `_paint`: home, title and section crumb, the channel dots, connectors/settings/clear.
export function _paintHeader(root, data, ctx, items, platforms, connectedCount, rerender){
  // Header: title + counter, connected icons only, connectors, settings, clear.
  const hd=el("div","hd");
  // WHERE AM I (2026-10-26): the house + title lit on the home; inside a channel they dim and its name follows.
  const home = !S.platFilter;
  const homeBtn = iconButton("home", tt("home", null, "Inicio"), "homebtn" + (home ? " on" : ""));
  homeBtn.onclick=()=>{ selectPlatform(null); ctx.top(); ctx.action("show_view",{platform:"all"}); rerender(); };
  hd.appendChild(homeBtn);
  // V2-616 — names the SCREEN (the unified inbox), not the catalog the card chrome already says; a click is the
  // way back to it from any screen (V2-610).
  const title=el("b","hdtitle",tt("title", null, "Mensajes")); title.title=tt("title_hint", null, "Ver la bandeja unificada de todos tus canales");
  title.onclick=()=>{ selectPlatform(null); ctx.top(); ctx.action("show_view",{platform:"all"}); rerender(); };
  if(home) title.classList.add("on");
  hd.append(title);
  if(home){
    // «para ti» counts what the home shows — what is addressed to him — not every unread the channels hold.
    const mine = items.filter(it=>it.highlight).length;
    hd.append(el("span","sub", mine ? tt("n_for_you", {n: mine}, `${mine} para ti`)
      : (connectedCount ? tt("up_to_date", null, "al día") : tt("not_connected", null, "sin conectar"))));
  } else {
    hd.append(el("span","hdsep","›"),
              el("b","hdsec", S.platFilter === "email" ? tt("mail_section", null, "Correo") : (PLAT[S.platFilter]||{}).label || S.platFilter));
    // In the mail section the header says the one thing left: which entry of the rail is on screen.
    if(S.platFilter === "email" && data.mailbox) hd.append(el("span","hdsep","›"), el("span","hdcur", mailWhere(data.mailbox)));
  }
  const dots=el("div","dots");
  // V2-521: every channel is visible — a bright one toggles its lens, a dimmed one opens its connector (V2-570).
  ORDER.forEach(pl=>{
    const on=(platforms[pl]||{}).status==="connected";
    const ic=brandIcon(pl, on);
    ic.style.cursor="pointer";
    if(on){
      ic.title=(PLAT[pl]||{}).label+(S.platFilter===pl?tt("dot_clear_filter", null, ": quitar filtro"):tt("dot_only_channel", null, ": ver solo este canal"));
      if(S.platFilter===pl) ic.classList.add("filt");
      // Same door as the voice (V2-543): repaint locally AND stamp the server view. A click is a NAVIGATION
      // order (V2-610): it leaves whatever screen was open (`ctx.top()`), not only the list underneath.
      ic.onclick=()=>{ const next=(S.platFilter===pl ? "all" : pl); selectPlatform(S.platFilter===pl ? null : pl);
        ctx.top(); ctx.action("show_view",{platform:next}); rerender(); };
    } else {
      ic.title=(PLAT[pl]||{}).label+tt("dot_connect", null, ": sin conectar — toca para conectarlo");
      ic.onclick=()=>ctx.openConnector(pl);     // ⚙ Conectores, on that channel
    }
    dots.appendChild(ic);
  });
  hd.appendChild(dots);
  // V2-616 — `.hdactions` is a second cluster with its own divider: a different kind of control from the channels.
  const actions=el("div","hdactions");
  // V2-831 T-04 — every control of this cluster is the SAME stroke-icon button as the channel icons beside it (one
  // target size, one glyph size): the plug used to be a 🔌 emoji nearly invisible on the dark ground, and ⚙ a text
  // glyph a size smaller than everything around it.
  const connBtn=hdButton(I.PLUG_ICON, tt("channels_btn", null, "Canales / conectores"), "connbtn");
  connBtn.onclick=()=>ctx.openConnector(S.platFilter || "");
  actions.appendChild(connBtn);
  const gear=hdButton(I.GEAR_ICON, tt("settings", null, "Ajustes"), "gear"+(S.settingsOpen?" active":""));
  gear.onclick=()=>{ S.settingsOpen=!S.settingsOpen; rerender(); };
  actions.appendChild(gear);
  if(items.length){
    const clr=hdButton(I.CHECK_CHECK_ICON, tt("mark_all_read", null, "Marcar todo como leído"), "clr");
    clr.onclick=()=>ctx.action("clear"); actions.appendChild(clr);
  }
  hd.appendChild(actions);
  root.appendChild(hd);
}

function hdButton(icon, label, cls){
  const b=el("button","hdbtn"+(cls?" "+cls:"")); b.type="button"; b.title=label; b.setAttribute("aria-label", label);
  b.innerHTML=icon; b.firstElementChild.setAttribute("aria-hidden","true");
  return b;
}
