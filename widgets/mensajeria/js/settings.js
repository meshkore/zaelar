// js/settings.js — The settings panel, the «connect a channel» prompt and the strip of what waits for his word.
// Moved verbatim out of widget.js (refactor2710-12).
import { S, ORDER, PLAT, tt } from "./state.js";
import { brandIcon, el, iconGrid, markBusy } from "./dom.js";

// Settings panel: simple/complete profile + connected platforms + muted channels. Replaces the old fixed footer
// (always-visible "connected"/"unlink" chips) with something that does not distract unless the user asks for it.
export function settingsPanel(platforms, data, ctx, rerender){
  const wrap = el("div","settings");

  wrap.appendChild(el("div","stitle",tt("profile", null, "Perfil")));
  const seg = el("div","seg");
  [["simple",tt("profile_simple", null, "Simple")], ["completo",tt("profile_full", null, "Completo")]].forEach(([key,label])=>{
    const b = el("button","segbtn"+(S.profile===key?" active":""), label);
    b.onclick=()=>{
      if(S.profile===key) return;
      S.profile=key;
      try{ localStorage.setItem("hb-msg-profile", key); }catch{ /* storage blocked: only affects this session */ }
      rerender();
    };
    seg.appendChild(b);
  });
  wrap.appendChild(seg);

  // Connect/disconnect lives in the CHANNELS panel from the header button, with credential-deletion confirmation.
  // Settings only contains profile + muted channels, to avoid two different disconnection paths.

  // V2-624 — the autoresponder's state, VISIBLE: something that answers people in the operator's name while
  // he is away must never be a mode he has to remember. Configured by voice (set_autoresponder); this panel
  // shows it and offers the off switch.
  const auto = data.autoresponder || {};
  const autoOn = Object.keys(auto).filter(p=> (auto[p]||{}).enabled);
  if(autoOn.length){
    wrap.appendChild(el("div","stitle",tt("autoresponder", null, "Autorespondedor")));
    const box = el("div","conns");
    autoOn.forEach(p=>{
      const cfg = auto[p] || {};
      const chip = el("span","ok");
      const win = cfg.hours ? (" · " + cfg.hours) : "";
      chip.append(document.createTextNode("🤖 " + ((PLAT[p]||{}).label||p) + win + " — «" +
                                          String(cfg.text||"").slice(0,80) + "»"));
      const off = el("span","lk",tt("autoresp_remove", null, "quitar"));
      off.onclick = ()=>{ off.textContent="…"; ctx.action("clear_autoresponder", {platform: p}); };
      chip.append(document.createTextNode(" · "), off);
      box.appendChild(chip);
    });
    wrap.appendChild(box);
  }

  // How long downloaded media stays on this device (widgets/mensajeria/media.py). Older pictures, videos and
  // voice notes leave this device and stay on the phone; the message keeps saying what was there.
  wrap.appendChild(el("div","stitle",tt("media_keep", null, "Multimedia en este dispositivo")));
  const mseg = el("div","seg");
  const cur = Number(data.media_days == null ? 14 : data.media_days);
  [[7,tt("media_7", null, "7 días")],[14,tt("media_14", null, "14 días")],[30,tt("media_30", null, "30 días")],
   [90,tt("media_90", null, "90 días")],[0,tt("media_always", null, "Siempre")]].forEach(([d,label])=>{
    const b = el("button","segbtn"+(cur===d?" active":""), label);
    b.onclick=()=>{ if(cur!==d) ctx.action("set_media_days", {days: d}); };
    mseg.appendChild(b);
  });
  wrap.appendChild(mseg);
  wrap.appendChild(el("div","snote",tt("media_keep_hint", null, "Lo más antiguo se borra de aquí; sigue en tu móvil.")));

  const muted = data.muted_channels||[];
  if(muted.length){
    wrap.appendChild(el("div","stitle",tt("muted", null, "Silenciados")));
    const row = el("div","conns");
    muted.forEach(m=>{
      const chip=el("span","ok"); chip.append(document.createTextNode("🔇 "+m.group));
      const lk=el("span","lk",tt("unhide", null, "reactivar"));
      // ZAELAR-FIX (2026-07-08): previously chatId:null was sent, so unhide never reactivated anything because
      // data.py requires chat_id is not None. m.chatId comes from view_data itself and must be sent back.
      lk.onclick=()=>{ lk.textContent="…"; ctx.action("unhide", {platform:m.platform, chatId:m.chatId}); };
      chip.append(document.createTextNode(" · "), lk);
      row.appendChild(chip);
    });
    wrap.appendChild(row);
  }

  return wrap;
}

// Loader + human-readable connection state.
// Nothing connected yet: the card says so and offers each channel — linking one is the ⚙ Conectores
// section's job (2026-10-04), the same place «conecta mi WhatsApp» opens by voice.
export function connectPrompt(platforms, ctx){
  const box=el("div","wiz");
  box.appendChild(el("div","wbody",tt("connect_prompt", null, "Conecta un canal para ver aquí tus mensajes.")));
  box.appendChild(iconGrid(ORDER.map(pl=>({key:pl, icon:brandIcon(pl, false), label:(PLAT[pl]||{}).label||pl,
    onClick:()=>ctx.openConnector(pl)}))));
  return box;
}

// V2-800 — a NEW message held for his word, and a send scheduled for later, are ROWS of this card: each one shown
// once, here, with the one control it needs. A held draft opens no conversation (there is none yet), so without
// this strip «ya está escrito, revísalo» pointed at nothing he could see.
export function pendingStrip(data, ctx){
  const held = Object.values(data.drafts || {}).filter(d => d && d.target && d.target.new);
  const later = (data.sent || []).filter(r => r && r.scheduled_for);
  if(!held.length && !later.length) return null;
  const box = el("div","pending");
  // A held draft is one line that opens its own screen (V2-807 T-02): the draft has ONE face, and it is never its
  // body painted over a list.
  held.forEach(d => {
    const t = d.target || {};
    const row = el("div","prow");
    row.append(el("b",null,tt("held_to", {to: t.name || t.to}, `Borrador para ${t.name || t.to}`)));
    const open = el("button","bt",tt("open_draft", null, "Abrir"));
    open.onclick = () => { markBusy(open); ctx.action("open_draft", {key: d.key}); };
    row.append(open);
    box.append(row);
  });
  later.forEach(r => {
    const row = el("div","prow");
    const when = new Date(Number(r.scheduled_for) * 1000).toLocaleString(S.LANG, {weekday:"short", hour:"2-digit", minute:"2-digit"});
    row.append(el("b",null,tt("scheduled_to", {to: r.name, when}, `Programado · ${r.name} · ${when}`)));
    row.append(el("div","pbody",String(r.body || "")));
    const cancel = el("button","bt",tt("cancel_send", null, "Cancelar envío"));
    cancel.onclick = () => { markBusy(cancel); ctx.action("cancel_send", {ref: r.id}); };
    row.append(cancel);
    box.append(row);
  });
  return box;
}
