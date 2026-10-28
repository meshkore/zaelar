// js/mailclient.js — THE EMAIL SECTION, A MAIL CLIENT (mailbox.py), second half: the list, an open message, the draft editor.
// Moved verbatim out of widget.js (refactor2710-12).
import { S, PLAT, tt } from "./state.js";
import { actionIcon, el, markBusy } from "./dom.js";
import { fmtWhen, linkify, markupText } from "./media.js";
import { pendingStrip } from "./settings.js";
import { emailList } from "./list.js";
import { mailDetail } from "./mail.js";
import { draftPointer, draftRow, folderRow, mailAct, mailCrumb, mailDrafts, mailRail, mailWhere } from "./mailrail.js";

export function mailList(mb, data, ctx, act){
  const wrap = el("div","tl mlist");
  const ptr = draftPointer(mb, data, act);
  if(ptr) wrap.appendChild(ptr);
  if(mb.role === "drafts"){
    const mine = mailDrafts(data);
    mine.forEach(d => wrap.appendChild(draftRow(d, act)));
    const later = (data.sent || []).filter(r => r && r.scheduled_for && r.platform === "email");
    if(later.length){
      const ps = pendingStrip({drafts:{}, sent: later}, ctx);
      if(ps) wrap.appendChild(ps);
    }
    if(mb.folder === "@drafts"){
      if(!mine.length && !later.length) wrap.appendChild(el("div","empty", tt("no_drafts", null, "No hay borradores")));
      return wrap;
    }
    if(mine.length && mb.rows.length) wrap.appendChild(el("div","mgroup", tt("in_mailbox", null, "En tu buzón")));
  }
  mb.rows.forEach(r => wrap.appendChild(folderRow(r, mb, act)));
  if(!mb.rows.length && !(mb.role === "drafts" && mailDrafts(data).length)){
    wrap.appendChild(el("div","empty", mb.loading || !mb.asked ? tt("loading", null, "Cargando…")
      : (mb.error ? tt("folder_error", null, "No he podido leer esta carpeta del buzón.")
                  : tt("folder_empty", null, "Esta carpeta está vacía"))));
  }
  if(mb.more || (mb.loading && mb.rows.length)){
    const more = el("button","bt bt-ghost mmore", mb.loading ? tt("loading", null, "Cargando…") : tt("load_more", null, "Cargar más"));
    more.disabled = !!mb.loading;
    more.onclick = () => { markBusy(more); act("mail_more", {}); };
    wrap.appendChild(more);
  }
  return wrap;
}

// One message of a folder, the whole card. A mail the home also holds is the SAME screen it always was
// (reply, archive, mark unread…); anything else is read from the mailbox and answered with «Responder».
export function mailMessage(mb, data, ctx, act, rerender){
  const o = mb.open || {};
  const item = String(mb.folder).toUpperCase() === "INBOX"
    ? (data.items || []).find(it => it.platform === "email" && String(it.messageId) === String(o.uid)) : null;
  const m = o.msg || {};
  const subject = (item ? item.subject : m.subject) || tt("no_subject", null, "(sin asunto)");
  const wrap = el("div","thread plat-email");
  wrap.appendChild(mailCrumb(mb, ctx, act, subject));
  if(item){
    const d = mailDetail(item, data, ctx, () => act("mail_back", {}), rerender);
    d.querySelector(".thd") && d.querySelector(".thd").remove();
    while(d.firstChild) wrap.appendChild(d.firstChild);
    return wrap;
  }
  const pane = el("div","mdet mpane");
  if(!o.msg){
    pane.appendChild(el("div","empty", o.loading ? tt("loading", null, "Cargando…") : tt("mail_unreadable", null, "No he podido abrir este correo.")));
  } else if(m.error){
    pane.appendChild(el("div","empty", tt("mail_unreadable", null, "No he podido abrir este correo.")));
  } else {
    const ltr = el("div","mltr");
    ltr.appendChild(el("div","mltrsubj", subject));
    const env = el("div","menv");
    const row = (k, v) => { if(v){ env.appendChild(el("div","menvk", k)); env.appendChild(el("div","menvv", v)); } };
    row(tt("from", null, "De"), m.fromName && m.fromName !== m.from ? `${m.fromName} · ${m.from}` : m.from);
    row(tt("to", null, "Para"), m.to);
    row(tt("cc", null, "Copia"), m.cc);
    row(tt("date", null, "Fecha"), fmtWhen(m.ts));
    ltr.appendChild(env);
    const body = el("div","mltrbody");
    linkify(body, markupText(m.body || ""));
    ltr.appendChild(body);
    pane.appendChild(ltr);
  }
  wrap.appendChild(pane);
  if(o.msg && !m.error && mb.role !== "sent" && mb.role !== "drafts"){
    const foot = el("div","dfoot");
    const reply = el("button","bt bt-primary", tt("reply", null, "Responder"));
    reply.onclick = () => {
      const subj = String(m.subject || "");
      S.newMail = {to: m.from || "", subject: /^re:/i.test(subj) ? subj : (subj ? "Re: " + subj : ""), text: ""};
      rerender();
    };
    foot.appendChild(reply);
    wrap.appendChild(foot);
  }
  return wrap;
}

// A DRAFT over the whole card: recipient, subject, text, and Send · Save · Discard. `d` is one of the card's
// drafts (`data.drafts[key]`) or, for a message not saved yet, `S.newMail`.
export function draftEditor(d, key, mb, data, ctx, act, rerender){
  const t = (d && d.target) || {};
  const fresh = !key;
  const isNew = fresh || !!t.new;
  const email = fresh || (t.platform || "email") === "email";
  const wrap = el("div","thread plat-" + (t.platform || "email") + " mdraft");
  const title = fresh ? tt("new_mail", null, "Nuevo correo") : tt("draft_tag", null, "Borrador");
  const leave = () => { if(fresh){ S.newMail = null; rerender(); } else act("mail_back", {}); };
  if(email) wrap.appendChild(mailCrumb(mb, ctx, act, title));
  else {
    const hd = el("div","thd");
    hd.appendChild(el("b","thdname", title + " · " + ((PLAT[t.platform] || {}).label || t.platform)));
    const back = el("button","back", tt("back", null, "← Volver")); back.onclick = leave;
    hd.appendChild(back);
    wrap.appendChild(hd);
  }
  if(fresh){   // the crumb's «←» goes one level up: for a message not saved yet that is simply closing it
    const b = wrap.querySelector(".mcrumb .back"); if(b) b.onclick = leave;
  }
  const pane = el("div","mdet mpane mdform");
  const field = (label, node) => { const f = el("label","mdf"); f.appendChild(el("span","mdk", label)); f.appendChild(node); pane.appendChild(f); return node; };
  const toIn = field(tt("to", null, "Para"), el("input","mdin"));
  // A new message's recipient is editable (re-resolved on save); a reply goes where the conversation is.
  toIn.value = fresh ? (d.to || "") : isNew ? (t.to || t.name || "")
    : (t.name && t.senderId && t.name !== t.senderId ? `${t.name} <${t.senderId}>` : (t.senderId || t.chatId || t.name || ""));
  toIn.readOnly = !isNew;
  let subjIn = null;
  if(email){
    subjIn = field(tt("subject", null, "Asunto"), el("input","mdin"));
    subjIn.value = fresh ? (d.subject || "") : (t.subject || "");
    subjIn.readOnly = !isNew;
  }
  const box = el("textarea","mdbody");
  box.value = d.text || "";
  // V2-819 — the focused field keeps focus and caret through a repaint; a saved draft's fields have no buffer of
  // their own (a new one has `S.newMail`), so theirs keep the typed value too.
  const tag = "draft:" + (key || "new") + ":";
  [[toIn, "to"], [subjIn, "subject"], [box, "body"]].forEach(([n, f]) => { if(!n) return;
    n.dataset.keep = tag + f; if(!fresh) n.dataset.keepValue = "1"; });
  box.placeholder = tt("draft_ph", null, "Escribe el mensaje…");
  pane.appendChild(box);
  if(!fresh && (d.files || []).length) pane.appendChild(el("div","mdfiles", "📎 " + d.files.join(", ")));
  wrap.appendChild(pane);
  // Every button is ONE order, and the outcome comes back through the state (`mb.note`): this card's taps are
  // queued to its owner and answered with nothing, so a screen that waited for the answer waited forever.
  const note = el("span","mdnote", noteText(mb.note));
  const values = () => ({text: box.value, ...(isNew ? {to: toIn.value.trim()} : {}),
                         ...(subjIn && isNew ? {subject: subjIn.value} : {})});
  if(fresh){   // what he types survives the repaints that arrive while the order is on its way
    const keepTyped = () => Object.assign(S.newMail, {to: toIn.value, subject: subjIn ? subjIn.value : "", text: box.value});
    [toIn, subjIn, box].forEach(n => n && n.addEventListener("input", keepTyped));
  }
  const order = (send, btn) => {
    if(!box.value.trim()){ note.textContent = tt("empty_draft", null, "El mensaje está vacío"); return; }
    if(isNew && !toIn.value.trim()){ note.textContent = tt("no_recipient", null, "Falta el destinatario"); return; }
    markBusy(btn);
    note.textContent = send ? tt("sending", null, "Enviando…") : tt("saving", null, "Guardando…");
    if(fresh) S.newMail.pending = Date.now();
    if(!send && !fresh) act("save_draft", {key, ...values()});
    else act("compose", {...(fresh ? {channel: "email"} : {key}), ...values(), ...(send ? {send: true} : {})});
  };
  const foot = el("div","dfoot");
  const send = el("button","bt bt-primary", tt("send", null, "Enviar"));
  send.onclick = () => order(true, send);
  const save = el("button","bt bt-ghost", tt("save_draft", null, "Guardar borrador"));
  save.onclick = () => order(false, save);
  const discard = el("button","bt bt-ghost mddel", tt("discard", null, "Descartar"));
  discard.onclick = () => { if(fresh) leave(); else { markBusy(discard); act("discard_draft", {key}); } };
  foot.append(send, save, discard, note);
  wrap.appendChild(foot);
  return wrap;
}

// The last outcome of the draft screen, said in his language: saved, sent, or why not.
export function noteText(n){
  if(!n || !n.key) return "";
  const fb = {saved:"Guardado ✓", sent:"Enviado ✓", not_saved:"No se ha guardado", not_sent:"No se ha enviado"};
  const head = tt(n.key === "sent" ? "sent_ok" : n.key, null, fb[n.key] || "");
  return n.text && /^not_/.test(n.key) ? `${head}: ${n.text}` : head;
}

export function mailClient(data, ctx, rerender){
  const mb = data.mailbox || {folders:[], folder:"INBOX", role:"inbox", rows:[]};
  const act = mailAct(ctx, data, rerender);
  const box = el("div","mclient");
  const grid = el("div","mcgrid" + (S.railOpen ? " open" : ""));
  const pane = el("div","mpanel");
  // On a card too narrow for the rail, this button names where he is and opens the rail as a drawer.
  const drawer = el("button","mdrawerbtn");
  drawer.type = "button";
  drawer.setAttribute("aria-expanded", S.railOpen ? "true" : "false");
  drawer.append(actionIcon("menu"), el("span", null, mailWhere(mb)));
  drawer.onclick = () => { S.railOpen = !S.railOpen; rerender(); };
  pane.appendChild(drawer);
  grid.append(mailRail(mb, data, ctx, act, rerender), pane);
  box.appendChild(grid);
  const its = (data.items || []).filter(it => it.platform === "email");
  if(mb.role === "inbox" && !mb.category && !(mb.rows || []).length && its.length){
    // The Inbox page has not arrived (or the mailbox could not be listed): the mail the card already holds IS
    // Inbox mail, shown at once instead of an empty box — and said, when the mailbox failed. Not on a category:
    // the held mail is every category mixed, the very thing a category view exists to separate.
    if(mb.error) pane.appendChild(el("div","mnote", tt("folder_error", null, "No he podido leer esta carpeta del buzón.")));
    pane.appendChild(emailList(its, ctx, n => { S.openMail = n; rerender(); }));
    return box;
  }
  if(mb.note && mb.note.key === "sent") pane.appendChild(el("div","mnote", noteText(mb.note)));
  pane.appendChild(mailList(mb, data, ctx, act));
  return box;
}
