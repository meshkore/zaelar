// js/header.js — The dashboard header of the card: home, title and section crumb, the channel dots, connectors/settings/clear.
// Moved verbatim out of widget.js (refactor2710-12).
import { S, ORDER, PLAT, selectPlatform, tt } from "./state.js";
import { brandIcon, el, iconButton } from "./dom.js";
import { mailWhere } from "./mailrail.js";

// The dashboard header of `_paint`: home, title and section crumb, the channel dots, connectors/settings/clear.
export function _paintHeader(root, data, ctx, items, platforms, connectedCount, rerender){
  // Header: title + counter, connected icons only, connectors, settings, clear.
  const hd=el("div","hd");
  // WHERE AM I (the operator, 2026-10-26: «ahora mismo no sé si estoy en la home o en alguno de los apartados»).
  // A house at the left of the title, lit together with the title while the home is on screen; inside a channel
  // the house and «Mensajes» dim and the channel's name follows them as the current section — the same
  // breadcrumb every other screen of this card carries.
  const home = !S.platFilter;
  const homeBtn = iconButton("home", tt("home", null, "Inicio"), "homebtn" + (home ? " on" : ""));
  homeBtn.onclick=()=>{ selectPlatform(null); ctx.top(); ctx.action("show_view",{platform:"all"}); rerender(); };
  hd.appendChild(homeBtn);
  // V2-616 — this title used to repeat the CATALOG name ("Mensajería"), which the outer card chrome
  // already says (V2-082's header). What this line actually names is the SCREEN underneath it — the
  // unified inbox — so it reads "Mensajes" now, the operator's own suggestion. The click behavior is
  // unchanged: from V2-610, the way BACK to the dashboard, always, from any screen (a platform lens, a
  // wizard, the connectors list, an open thread or mail).
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
  // V2-521: every channel is VISIBLE up here — connected bright, unconnected dimmed (the operator's ask:
  // seeing the catalogue at a glance). A bright icon toggles that platform's lens; a dimmed one opens that
  // connector's own wizard screen — the same door the voice takes (V2-570).
  ORDER.forEach(pl=>{
    const on=(platforms[pl]||{}).status==="connected";
    const ic=brandIcon(pl, on);
    ic.style.cursor="pointer";
    if(on){
      ic.title=(PLAT[pl]||{}).label+(S.platFilter===pl?tt("dot_clear_filter", null, ": quitar filtro"):tt("dot_only_channel", null, ": ver solo este canal"));
      if(S.platFilter===pl) ic.classList.add("filt");
      // Same door as the voice (V2-543): apply locally for an instant repaint AND stamp the server view, so
      // the next voice order and the next SSE repaint agree with what the click just did.
      // V2-610 — a click here is a NAVIGATION order («llévame a WhatsApp»), and a navigation order must
      // leave wherever it was, not just change what the list underneath would show. Before this, clicking
      // a platform icon while the Conectores screen was open changed `S.platFilter` and called `show_view`
      // but never cleared `_screen`, so `showChannels` stayed true and the click was invisible — the
      // operator kept seeing Conectores no matter which platform he tapped (reported live 2026-09-07).
      ic.onclick=()=>{ const next=(S.platFilter===pl ? "all" : pl); selectPlatform(S.platFilter===pl ? null : pl);
        ctx.top(); ctx.action("show_view",{platform:next}); rerender(); };
    } else {
      ic.title=(PLAT[pl]||{}).label+tt("dot_connect", null, ": sin conectar — toca para conectarlo");
      ic.onclick=()=>ctx.openConnector(pl);     // ⚙ Conectores, on that channel
    }
    dots.appendChild(ic);
  });
  hd.appendChild(dots);
  // V2-616 — the operator: the platform icons and the settings/connectors icons "no pueden estar al mismo
  // nivel ni pegados a lo que son secciones o diferentes plataformas". `.hdactions` is a second cluster with
  // its own divider, so it reads as a DIFFERENT kind of control from the row of channel icons beside it.
  const actions=el("div","hdactions");
  const connBtn=el("button","connbtn","🔌"); connBtn.title=tt("channels_btn", null, "Canales / conectores");
  connBtn.onclick=()=>ctx.openConnector(S.platFilter || "");
  actions.appendChild(connBtn);
  const gear=el("button","gear"+(S.settingsOpen?" active":""),"⚙"); gear.title=tt("settings", null, "Ajustes");
  gear.onclick=()=>{ S.settingsOpen=!S.settingsOpen; rerender(); };
  actions.appendChild(gear);
  if(items.length){
    const clr=el("button","clr",tt("clear", null, "Limpiar")); clr.title=tt("mark_all_read", null, "Marcar todo como leído");
    clr.onclick=()=>ctx.action("clear"); actions.appendChild(clr);
  }
  hd.appendChild(actions);
  root.appendChild(hd);
}
