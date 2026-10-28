// js/compose.js — The COMPOSE BAR (V2-611): the per-conversation draft box, attachments, reply-all, send and its outcome.
// Moved verbatim out of widget.js (refactor2710-12).
import { S, PLAT, _draftFiles, _draftLocal, _replyAll, _sendNote, _sending, tt } from "./state.js";
import { actionIcon, el } from "./dom.js";

export function _newRef(){ return "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
// The words for why a send did not leave: the server's code mapped to his language, its own sentence otherwise.
export function _sendFailText(res, platform){
  const label = (PLAT[platform] || {}).label || platform || "";
  const code = res && (res.error || res.state);
  if(!res) return tt("send_offline", null, "El agente no ha contestado: no se ha enviado nada.");
  if(code === "not_connected") return tt("send_not_connected", {platform: label}, `${label} no está conectado, así que no se ha enviado.`);
  if(code === "empty") return tt("send_empty", null, "No hay nada escrito que enviar.");
  if(code === "no_target") return tt("send_no_target", null, "No sé a qué conversación va: ábrela y vuelve a enviarlo.");
  if(code === "unconfirmed") return tt("send_unconfirmed", {platform: label}, `${label} todavía no ha confirmado el envío: puede que no haya salido.`);
  const why = String((res && (res.reason || res.message)) || "").trim();
  return tt("not_sent", null, "No se ha enviado") + (why ? ": " + why : "");
}

export function _composeKey(targetPayload, activeChat){
  if(targetPayload && (targetPayload.messageId != null || targetPayload.n != null))
    return "m:" + (targetPayload.messageId != null ? targetPayload.messageId : targetPayload.n);
  if(activeChat) return "c:" + activeChat.platform + ":" + activeChat.chatId;
  return "?";
}

export function _draftMatches(draft, targetPayload, activeChat){
  if(!draft || !draft.target) return false;
  const t = draft.target;
  if(targetPayload && (targetPayload.messageId != null || targetPayload.n != null))
    return (targetPayload.messageId != null && t.messageId === targetPayload.messageId) ||
           (targetPayload.n != null && t.n === targetPayload.n);
  if(activeChat) return t.platform === activeChat.platform && String(t.chatId) === String(activeChat.chatId);
  return false;
}

// The other people the original went to. It comes from the connector (`mailbox.parse_message`), which is
// the only layer that can see To/Cc and knows our own address to strip. An older stored item — ingested
// before this field existed — carries nothing, and then the choice is simply not offered: a reply-all that
// silently reaches nobody extra is exactly the lie this widget must not tell.
export function _otherRecipients(it){
  const r = (it && it.recipients) || [];
  return Array.isArray(r) ? r.filter(a => typeof a === "string" && a.trim()) : [];
}

// ATTACHING, the way every messaging app does it: the clip opens the file picker, each file is uploaded by the canvas
// (`ctx.upload` — this widget never touches the network) and shows as a chip; the chips' NAMES travel in the
// action that sends. `files` is the list being edited; `onChange` re-syncs whatever owns it.
export function attachControls(ctx, files, onChange){
  const row = el("div","attrow");
  const paint = ()=>{
    row.replaceChildren();
    files.forEach((f, i)=>{
      const pic = f.type === "image" && String(f.url||"").startsWith("/widgets/");
      const chip = el("span","attchip" + (pic ? " attthumb" : ""));
      if(pic){
        const img = document.createElement("img"); img.src = f.url; img.alt = f.original || f.name; chip.appendChild(img);
        chip.title = f.original || f.name;
      } else {
        chip.appendChild(actionIcon(f.type === "video" ? "video" : (f.type === "audio" ? "mic" : "file")));
        chip.appendChild(el("span", null, f.original || f.name));
      }
      const x = el("button", null, "✕"); x.title = tt("attach_remove", null, "Quitar");
      x.onclick = ()=>{ files.splice(i, 1); paint(); onChange(); };
      chip.appendChild(x);
      row.appendChild(chip);
    });
    row.style.display = files.length ? "" : "none";
  };
  const input = document.createElement("input");
  input.type = "file"; input.multiple = true; input.style.display = "none";
  const btn = el("button","bt attbtn"); btn.appendChild(actionIcon("clip"));
  btn.title = tt("attach", null, "Adjuntar foto, vídeo o archivo"); btn.setAttribute("aria-label", btn.title);
  btn.onclick = ()=> input.click();
  input.onchange = async ()=>{
    const picked = Array.from(input.files || []);
    input.value = "";
    if(!picked.length || typeof ctx.upload !== "function") return;
    btn.disabled = true; btn.classList.add("busy");
    for(const file of picked){
      const r = await ctx.upload(file);
      if(r && r.name) files.push({name: r.name, url: r.url, type: r.type, original: r.original || file.name});
    }
    btn.disabled = false; btn.classList.remove("busy");
    paint(); onChange();
  };
  paint();
  return {row, btn, input};
}

// The reply / reply-all selector of `composeBar`, and what reply-all adds, named out loud.
export function _replyAllRow(key, others, replyAll, rerender){
  const top = el("div","composetop");
  const seg = el("div","seg");
  [["one",tt("reply", null, "Responder")], ["all",tt("reply_all", null, "Responder a todos")]].forEach(([id, label])=>{
    const b = el("button","segbtn"+(((id==="all")===replyAll)?" active":""), label);
    b.onclick = ()=>{ _replyAll[key] = (id === "all"); rerender(); };
    seg.appendChild(b);
  });
  top.appendChild(seg);
  // What reply-all actually ADDS, named out loud: the promise is only worth making if he can see it.
  top.appendChild(el("span","composehint", replyAll
    ? (tt("cc_", null, "copia a ") + others.slice(0,3).join(", ") + (others.length > 3 ? tt("and_n_more", {n:others.length-3}, ` y ${others.length-3} más`) : ""))
    : (others.length === 1 ? tt("one_more_recipient", null, "1 destinatario más en el original")
                           : tt("n_more_recipients", {n:others.length}, `${others.length} destinatarios más en el original`))));
  return top;
}

export function composeBar(ctx, data, targetPayload, activeChat, rerender, mailItem){
  const key = _composeKey(targetPayload, activeChat);
  const wrap = el("div","compose");

  // The draft for THIS conversation, out of the per-conversation map (V2-680). `data.draft` stays the
  // fallback: it is the most recent one, which an older engine is all that ever answers with.
  const stored = (data.drafts || {})[key];
  const matches = _draftMatches(data.draft, targetPayload, activeChat);
  const serverText = stored ? String(stored.text || "") : (matches ? String(data.draft.text || "") : "");

  const others = _otherRecipients(mailItem);
  if(others.length && !(key in _replyAll) && stored && stored.reply_all) _replyAll[key] = true;
  const replyAll = others.length ? !!_replyAll[key] : false;

  const box = document.createElement("textarea");
  box.className = "composebox";
  box.placeholder = tt("compose_ph", null, "Escribe tu respuesta… (o dila por voz y aparecerá aquí)");
  box.rows = 5;                       // the operator's own minimum — a reply is written, not tweeted
  box.value = (key in _draftLocal) ? _draftLocal[key] : serverText;
  box.dataset.keep = "compose:" + key;      // V2-819: focus and caret survive a repaint (see _captureWhere)

  // Reply / reply-all, above the box. Only for a mail whose original really had other recipients.
  if(others.length) wrap.appendChild(_replyAllRow(key, others, replyAll, rerender));

  const main = el("div","composemain");
  const side = el("div","composeside");
  const send = el("button","bt bt-primary",tt("send", null, "Enviar ➤"));
  const save = el("button","bt",tt("save_draft", null, "Guardar borrador"));
  save.title = tt("save_draft_hint", null, "Guardar lo escrito sin enviarlo (también se guarda solo al dejar de escribir)");
  if(!(key in _draftFiles)){
    const saved = (stored && Array.isArray(stored.files)) ? stored.files : [];
    _draftFiles[key] = saved.map(n=>({name: n, url: "/widgets/mensajeria/asset/" + n, original: String(n).split("_").slice(2).join("_") || n,
                                      type: /\.(jpe?g|png|webp|gif|heic)$/i.test(n) ? "image" : "document"}));
  }
  const files = _draftFiles[key];
  const syncBtn = () => { send.disabled = !!_sending[key] || (!box.value.trim() && !files.length); };
  // V2-819 — the order on its way settles from the state: its outbox row says sent (the box empties), or failed /
  // unconfirmed (his text comes back, unlocked, with the reason).
  const going = _sending[key];
  if(going){
    const row = (data.outbox || []).find(r => r && r.ref === going.ref);
    if(row && row.state === "sent"){
      delete _sending[key]; delete _draftLocal[key]; _draftFiles[key] = []; files.length = 0;
      box.value = "";
    } else if(row && row.state !== "queued"){
      delete _sending[key]; _draftLocal[key] = going.text; box.value = going.text;
      _sendNote[key] = _sendFailText(row, row.platform);
    } else {
      box.value = going.text; box.readOnly = true;
      send.textContent = tt("sending", null, "Enviando…");
    }
  }
  syncBtn();

  const payload = () => ({...targetPayload, reply_all: replyAll, files: files.map(f=>f.name)});
  const att = attachControls(ctx, files, ()=>{ syncBtn(); ctx.action("draft", {...payload(), text: box.value}); });
  box.addEventListener("input", () => {
    _draftLocal[key] = box.value;
    if(_sendNote[key]){ delete _sendNote[key]; const n = wrap.querySelector(".composeerr"); if(n) n.remove(); }
    syncBtn();
    clearTimeout(S.draftTimer);
    S.draftTimer = setTimeout(() => { ctx.action("draft", {...payload(), text: box.value}); }, 500);
  });
  // Saving explicitly is the SAME write the autosave does, just now instead of in half a second — so the
  // two can never disagree about what is stored. It says so on screen, because a save nobody can see is
  // indistinguishable from a button that does nothing.
  save.onclick = async () => {
    clearTimeout(S.draftTimer);
    _draftLocal[key] = box.value;
    await ctx.action("draft", {...payload(), text: box.value});
    save.textContent = tt("saved", null, "Guardado ✓");
    setTimeout(()=>{ try{ save.textContent = tt("save_draft", null, "Guardar borrador"); }catch(_){} }, 1600);
  };
  send.onclick = async () => {
    const text = box.value;
    if(_sending[key] || (!text.trim() && !files.length)) return;
    clearTimeout(S.draftTimer);
    // ONE order, carrying what is in the box and naming the conversation it is for. It used to be two (`draft`,
    // then a bare `send_draft {}` that sent «the most recent draft», whichever conversation that was), and the box
    // was emptied before anything was known. Now the box keeps his text until the outbox row says it left.
    const ref = _newRef();
    _sending[key] = {ref, text};
    delete _sendNote[key];
    const chat = activeChat ? {platform: activeChat.platform, chatId: activeChat.chatId} : null;
    rerender();
    const res = await ctx.action("send_draft", {...targetPayload, ...(chat ? {chat} : {}), ref, box_key: key, text,
                                                reply_all: replyAll, files: files.map(f=>f.name)});
    if(!res || res.ok === false || (res.error && !res.ok)){
      delete _sending[key];
      _draftLocal[key] = text;
      _sendNote[key] = _sendFailText(res, (chat || mailItem || {}).platform || (mailItem ? "email" : ""));
      rerender();
    }
  };
  side.append(send, save);
  // V2-819 (approved design, 2026-10-27): the clip sits BESIDE the text on the same row, and what he attaches waits
  // ABOVE the box — a picture as a thumbnail — before it is sent.
  main.append(att.btn, att.input, box, side);
  if(_sendNote[key]) wrap.appendChild(el("div","composeerr", _sendNote[key]));
  wrap.appendChild(att.row);
  wrap.appendChild(main);
  const c = data.composing;
  if(c && activeChat && c.platform === activeChat.platform && String(c.chatId) === String(activeChat.chatId))
    _playCompose(c, box, send);
  return wrap;
}

// SEEN BEING SENT (data.py `_composing`): a message he ordered by voice is typed into this box and the send button
// is pressed at the moment the engine releases the queued order. Nothing here sends — the order is already in the
// queue — so the button is only ever pressed for show, and a rerender mid-way simply picks the typing up again.
// The clock is the server's, re-anchored on each render (`elapsed_s`/`left_s`), so a skewed browser clock
// cannot make the press land before or after the real send.
export function _playCompose(c, box, send){
  const text = String(c.text || "");
  const now0 = Date.now();
  const t0 = now0 - Number(c.elapsed_s || 0) * 1000;
  const t1 = now0 + Number(c.left_s || 0) * 1000;
  const typeEnd = t0 + Math.max(300, (t1 - t0) - 600);     // a beat with the text complete before the press
  box.readOnly = true;
  const done = () => {
    box.value = ""; box.readOnly = false;
    send.classList.remove("pressing"); send.classList.add("sent");
    send.textContent = tt("sent", null, "Enviado ✓"); send.disabled = true;
  };
  const tick = () => {
    if(!box.isConnected) return;
    const now = Date.now();
    if(now >= t1) return done();
    const f = Math.max(0, Math.min(1, (now - t0) / Math.max(1, typeEnd - t0)));
    box.value = text.slice(0, Math.round(f * text.length));
    send.disabled = !box.value.trim();
    send.classList.toggle("pressing", now >= t1 - 250);
    requestAnimationFrame(tick);
  };
  tick();
}
