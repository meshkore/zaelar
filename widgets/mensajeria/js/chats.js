// js/chats.js — The ACTIVITY view (V2-624) and the CHAT LISTS: criteria bar, a platform's chat list, the «Nuevo» form, grouped chats.
// Moved verbatim out of widget.js (refactor2710-12).
import { _chatKind, _chatQuery, _newForm, tt } from "./state.js";
import { actionIcon, el, iconButton, markBusy, platformChip, splitBody } from "./dom.js";
import { displayBody, fmtWhen } from "./media.js";
import { attachControls } from "./compose.js";

// CHAT list (simple profile, default): one item per conversation instead of per message. Shows name, pending
// count, and the last message as preview. Click, or [[msg.open:N]] by voice, enters the full thread.
// ── ACTIVITY view (V2-624) ──────────────────────────────────────────────────
// A lens whose platform carries a view CRITERION («conversaciones con actividad en las últimas 72 h») lists
// CONVERSATIONS from the thread store — movement includes what he already read and what he himself sent —
// instead of the pending inbox. The criterion is per-platform STATE the operator set, so it is VISIBLE (a bar
// with a ✕), never a silent mode; without one, the lens stays byte-for-byte the classic pending view.
export function fmtWindow(h){
  const n = Number(h||0);
  if(n <= 48) return tt("last_f", null, "últimas ") + Math.round(n) + " h";
  return tt("last_m", null, "últimos ") + Math.round(n/24) + tt("_days", null, " días");
}

export function criteriaBar(platform, crit, ctx, rerender){
  const bar = el("div","critbar");
  bar.appendChild(el("span","critlbl",tt("activity_", null, "Actividad · ") + fmtWindow(crit.window_h)));
  if(platform === "telegram" || platform === "email"){
    const fetchBtn = el("button","bt bt-ghost critfetch",tt("fetch_connector", null, "⟳ Traer del conector"));
    fetchBtn.title = tt("fetch_connector_hint", null, "Pedirle al conector las conversaciones con actividad en ese período");
    fetchBtn.onclick = ()=>{ fetchBtn.textContent = tt("fetch_asked", null, "⟳ Pedido…"); fetchBtn.disabled = true;
      ctx.action("fetch_now", {platform: platform, since_hours: crit.window_h}); };
    bar.appendChild(fetchBtn);
  }
  const off = el("button","critoff","✕");
  off.title = tt("clear_criteria", null, "Quitar el criterio (volver a la vista de pendientes)");
  off.onclick = ()=> ctx.action("show_view", {platform: platform, window_h: 0});
  bar.appendChild(off);
  return bar;
}

export function activityList(rows, ctx){
  const wrap = el("div","tl");
  rows.forEach(c=>{
    const row = el("div","trow chatrow");
    row.title = tt("open_chat", null, "Abrir conversación");
    const lead = el("span","tlead");
    lead.style.background = c.unread ? "var(--hb-accent,#3D6FE0)" : "transparent";
    row.appendChild(lead);
    const main = el("div","tmain");
    const head = el("div","thead");
    head.appendChild(platformChip(c.platform));
    head.appendChild(el("span","tfrom", c.name));
    if(c.unread) head.appendChild(el("span","tcount", String(c.unread)));
    if(c.isGroup) head.appendChild(el("span","tpara",tt("group", null, "· grupo")));
    const when = fmtWhen(c.lastTs);
    if(when) head.appendChild(el("span","twhen", when));
    main.appendChild(head);
    const who = c.lastFrom ? c.lastFrom + ": " : "";
    main.appendChild(el("div","tprev", who + displayBody(c.lastBody, c.lastMediaType)));
    row.appendChild(main);
    row.onclick = ()=> { ctx.top(); ctx.action("open", {platform: c.platform, chatId: c.chatId}); };
    wrap.appendChild(row);
  });
  return wrap;
}

export const KIND_FILTERS = {
  whatsapp: ["all", "unread", "person", "group"],
  telegram: ["all", "unread", "person", "group", "channel"],
};

export function chatRowMatches(r, kind, q){
  if(kind === "unread" && !(r.unread || r.pending)) return false;
  if(kind === "person" || kind === "group" || kind === "channel"){ if((r.kind || "person") !== kind) return false; }
  if(q){
    const hay = ((r.name || "") + " " + (r.preview || "")).toLowerCase();
    if(!hay.includes(q)) return false;
  }
  return true;
}

export function platformChatRows(platform, rows, ctx){
  const wrap = el("div","tl");
  rows.forEach(c=>{
    const row = el("div","trow chatrow" + (c.archived ? " cxarch" : ""));
    row.title = tt("open_chat", null, "Abrir conversación");
    const lead = el("span","tlead");
    lead.style.background = c.urgent ? "var(--hb-risk,#e5484d)"
      : ((c.forMe || c.unread) ? "var(--hb-accent,#3D6FE0)" : "transparent");
    row.appendChild(lead);
    const main = el("div","tmain");
    const head = el("div","thead");
    if(c.photo && String(c.photo).match(/^(\/widgets\/|data:image\/)/)){
      const ph = document.createElement("img"); ph.className = "cxava"; ph.src = c.photo; ph.alt = ""; head.appendChild(ph);
    }
    head.appendChild(el("span","tfrom", c.name));
    const count = c.unread || c.pending || 0;
    if(count) head.appendChild(el("span","tcount", String(count)));
    if(c.kind === "group") head.appendChild(el("span","tpara", c.forum ? tt("forum", null, "· grupo con temas") : tt("group", null, "· grupo")));
    if(c.kind === "channel") head.appendChild(el("span","tpara", tt("channel", null, "· canal")));
    if(c.forMe) head.appendChild(el("span","tpara",tt("dot_for_you", null, "· para ti")));
    if(c.muted){ const m = el("span","cxtag"); m.appendChild(actionIcon("bellOff")); m.title = tt("muted_chat", null, "Silenciado"); head.appendChild(m); }
    if(c.archived) head.appendChild(el("span","cxtag",tt("archived", null, "archivado")));
    const when = fmtWhen(c.ts);
    if(when) head.appendChild(el("span","twhen", when));
    main.appendChild(head);
    const mine = c.fromMe ? tt("you_prefix", null, "Tú: ") : "";
    main.appendChild(el("div","tprev", mine + displayBody(c.preview, c.mediaType)));
    row.appendChild(main);
    row.onclick = ()=> { ctx.top(); ctx.action("open", {platform: platform, chatId: c.chatId}); };
    wrap.appendChild(row);
  });
  return wrap;
}

// «Nuevo chat» / «Nuevo grupo»: the same doors the voice uses (`send_to`, `create_group`), with the same
// resolution of who is who — an unknown or ambiguous name comes back as the action's own sentence, shown here.
export function newForm(platform, mode, ctx, close){
  const f = el("div","newform");
  const err = el("div","newerr");
  const files = [];
  const name = document.createElement("input");
  const who = document.createElement("input");
  const text = document.createElement("textarea"); text.rows = 3;
  if(mode === "group"){
    name.placeholder = tt("group_name", null, "Nombre del grupo");
    who.placeholder = tt("group_members", null, "Personas (separadas por comas)");
    text.placeholder = tt("group_first", null, "Primer mensaje (opcional)");
    f.append(name, who, text);
  } else {
    who.placeholder = tt("new_to", null, "Para: nombre del contacto");
    text.placeholder = tt("new_text", null, "Mensaje");
    f.append(who, text);
  }
  const att = attachControls(ctx, files, ()=>{});
  const go = el("button","bt bt-primary", mode === "group" ? tt("group_create", null, "Crear grupo") : tt("send", null, "Enviar ➤"));
  const cancel = el("button","bt", tt("cancel", null, "Cancelar"));
  cancel.onclick = close;
  go.onclick = async ()=>{
    err.textContent = ""; go.disabled = true;
    const names = files.map(x=>x.name);
    const res = mode === "group"
      ? await ctx.action("create_group", {platform, name: name.value.trim(),
          members: who.value.split(",").map(x=>x.trim()).filter(Boolean), text: text.value.trim(), files: names})
      : await ctx.action("send_to", {contact: who.value.trim(), channel: platform, text: text.value.trim(), files: names});
    go.disabled = false;
    if(res && res.ok === false){ err.textContent = res.message || res.error || tt("new_failed", null, "No se ha podido"); return; }
    close();
  };
  const row = el("div","row"); row.append(err, att.btn, att.input, cancel, go);
  f.append(att.row, row);
  return f;
}

// The first screen of a platform, like its own app: the conversations, not only what is unread.
export function platformChats(platform, v, ctx){
  const box = el("div","cxwrap");
  const nb = el("div","cxnew");
  const formSlot = el("div");
  const openForm = (mode)=>{
    _newForm[platform] = _newForm[platform] === mode ? null : mode;
    formSlot.replaceChildren();
    if(_newForm[platform]) formSlot.appendChild(newForm(platform, mode, ctx, ()=>{ _newForm[platform] = null; formSlot.replaceChildren(); }));
  };
  const iconBtn = (icon, label)=>{ const b = el("button","bt cxnewbt"); b.append(actionIcon(icon), el("span", null, label)); return b; };
  const nc = iconBtn("pencil", tt("new_chat", null, "Nuevo chat")); nc.onclick = ()=> openForm("chat");
  const ng = iconBtn("users", tt("new_group", null, "Nuevo grupo")); ng.onclick = ()=> openForm("group");
  nb.append(nc, ng);
  box.append(nb, formSlot);
  if(_newForm[platform]) formSlot.appendChild(newForm(platform, _newForm[platform], ctx, ()=>{ _newForm[platform] = null; formSlot.replaceChildren(); }));
  const bar = el("div","cxbar");
  const chips = el("div","cxchips");
  const kind = _chatKind[platform] || "all";
  const labels = {all: tt("kind_all", null, "Todos"), unread: tt("kind_unread", null, "No leídos"),
                  person: tt("kind_person", null, "Personas"), group: tt("kind_group", null, "Grupos"),
                  channel: tt("kind_channel", null, "Canales")};
  const listBox = el("div","cxlist");
  const fill = ()=>{
    const k = _chatKind[platform] || "all";
    const q = (_chatQuery[platform] || "").trim().toLowerCase();
    const rows = (v.rows || []).filter(r=> chatRowMatches(r, k, q));
    listBox.replaceChildren();
    if(rows.length) listBox.appendChild(platformChatRows(platform, rows, ctx));
    else if(v.loading || !v.asked) listBox.appendChild(el("div","empty",tt("chats_loading", null, "Cargando tus chats…")));
    else listBox.appendChild(el("div","empty", (q || k !== "all")
      ? tt("chats_none_match", null, "Ningún chat de los cargados coincide")
      : tt("chats_none", null, "No hay chats todavía")));
  };
  (KIND_FILTERS[platform] || KIND_FILTERS.whatsapp).forEach(k=>{
    const b = el("button","cxchip" + (k === kind ? " on" : ""), labels[k]);
    b.onclick = ()=>{ _chatKind[platform] = k; chips.querySelectorAll(".cxchip").forEach(x=>x.classList.remove("on"));
      b.classList.add("on"); fill(); };
    chips.appendChild(b);
  });
  bar.appendChild(chips);
  const search = el("input","cxsearch");
  search.type = "search";
  search.placeholder = tt("chats_search", null, "Buscar un chat");
  search.value = _chatQuery[platform] || "";
  search.dataset.keep = "chatsearch:" + platform;
  search.oninput = ()=>{ _chatQuery[platform] = search.value; fill(); };
  bar.appendChild(search);
  box.appendChild(bar);
  box.appendChild(listBox);
  fill();
  if(v.error) box.appendChild(el("div","cxnote", tt("chats_error", null, "La app no me ha dado más chats: ") + v.error));
  if(v.more){
    const more = el("button","bt bt-ghost cxmore", v.loading ? tt("chats_loading_more", null, "Cargando…") : tt("chats_more", null, "Cargar más"));
    more.disabled = !!v.loading;
    more.onclick = ()=>{ more.disabled = true; more.textContent = tt("chats_loading_more", null, "Cargando…");
      ctx.action("chats_more", {platform: platform}); };
    box.appendChild(more);
  } else if((v.rows || []).length){
    box.appendChild(el("div","cxnote", platform === "whatsapp"
      ? tt("chats_end_whatsapp", null, "Son todos los chats que WhatsApp ha pasado a este dispositivo")
      : tt("chats_end", null, "No hay más chats")));
  }
  return box;
}

export function chatList(chats, ctx){
  const wrap = el("div","tl");
  chats.forEach(c=>{
    const row = el("div","trow chatrow");
    row.title = tt("open_chat", null, "Abrir conversación");
    const lead = el("span","tlead");
    lead.style.background = c.urgencia === "alta" ? "var(--hb-risk,#e5484d)"
      : (c.dirigido_a_mi ? "var(--hb-accent,#3D6FE0)" : "transparent");
    row.appendChild(lead);

    const main = el("div","tmain");
    const head = el("div","thead");
    head.appendChild(platformChip(c.platform));
    head.appendChild(el("span","tfrom", c.name));
    if(c.count > 1) head.appendChild(el("span","tcount", String(c.count)));
    if(c.dirigido_a_mi) head.appendChild(el("span","tpara",tt("dot_for_you", null, "· para ti")));
    const when = fmtWhen(c.lastTs);
    if(when) head.appendChild(el("span","twhen", when));
    main.appendChild(head);

    const {title, rest} = splitBody(displayBody(c.lastBody, c.lastMediaType));
    main.appendChild(el("div","tprev", title ? (title+" — "+rest) : rest));
    row.appendChild(main);
    // V2-616 F2 — opening a thread swaps the whole screen (a chat list row for the thread's own header +
    // messages), so the outer card scroller has to go back to the top. Without this, a chat list left
    // scrolled down handed the fresh thread a stale scrollTop: its own header rendered scrolled PAST the
    // visible area on first paint, reported live as "se ha metido como por debajo el header del otro" — his
    // own scroll gesture only fixed it by accident, forcing the browser to reflow.
    row.onclick = ()=> { ctx.top(); ctx.action("open", {n:c.n}); };

    const acts = el("div","tacts");
    const read=iconButton("check",tt("read_whole_chat", null, "Marcar todo el chat como leído"));
    read.onclick=(ev)=>{ ev.stopPropagation(); ctx.action("readchat",{n:c.n}); };
    const mute=iconButton("mute",tt("mute_channel", null, "Silenciar este canal"));
    mute.onclick=(ev)=>{ ev.stopPropagation(); markBusy(mute); ctx.action("hide",{n:c.n}); };
    acts.append(read,mute);
    row.appendChild(acts);

    wrap.appendChild(row);
  });
  return wrap;
}
