// js/thread.js — An open THREAD: where our copy begins, and the conversation as bubbles with its compose bar.
// Moved verbatim out of widget.js (refactor2710-12).
import { PLAT, tt } from "./state.js";
import { el, platformChip } from "./dom.js";
import { composeBar } from "./compose.js";
import { messageRow } from "./list.js";
import { mailLetter } from "./mail.js";

// Open thread: header (back + platform + name) and its messages one by one. `close` returns to the chat list,
// is also addressable by voice ([[msg.close]]), and converges on the same ctx.action.
// V2-546 — the boundary of what we hold. Our copy of a conversation starts somewhere, and saying where is the
// difference between a scrollback and a lie: without this line the oldest message we have LOOKS like the start
// of the conversation. Offers to go further only where the platform can actually serve it.
export function threadStart(meta, ctx){
  const box = el("div","tstart");
  if(meta && meta.complete){
    box.appendChild(el("span","tsl",tt("chat_start", null, "· principio de la conversación ·")));
    return box;
  }
  box.appendChild(el("span","tsl",tt("stored_start", null, "· aquí empieza lo que tengo guardado ·")));
  if(meta && meta.can_load_more){
    const b = el("button","tsbtn",tt("load_older", null, "Cargar anteriores"));
    b.onclick=()=>{ b.disabled=true; b.textContent=tt("loading_older", null, "Pidiéndolos…"); ctx.action("load_more",{}); };
    box.appendChild(b);
  }
  return box;
}

export function threadView(active, items, data, ctx, rerender, meta){
  const wrap = el("div","thread"+(" plat-"+active.platform));
  const hd = el("div","thd");
  hd.appendChild(platformChip(active.platform));
  // The chat's name comes from an INBOUND message: with outbound ones in the thread (V2-546) the first row can
  // be the operator's own, and naming the conversation after himself is how a thread stops being recognisable.
  const inbound = items.filter(it=> it.dir !== "out");
  // V2-819 — a one-to-one chat is named by the server's ONE resolver (`names.py`: his contact first, then the
  // platform's own display name), so the header says what the list says; a group keeps its subject.
  const resolved = meta && !meta.isGroup ? meta.name : "";
  const name = resolved || (inbound.find(it=>it.group)||{}).group || (inbound.find(it=>it.from)||{}).from
    || (PLAT[active.platform]||{}).label || tt("chat", null, "Chat");
  if(meta && meta.photo && String(meta.photo).match(/^(\/widgets\/|data:image\/)/)){
    const ph = document.createElement("img"); ph.className = "cxava"; ph.src = meta.photo; ph.alt = ""; hd.appendChild(ph);
  }
  hd.appendChild(el("b","thdname", name));
  // V2-616 F2/F3 — the operator: the name goes on the LEFT, "volver" moves to the far RIGHT as a real
  // button, never a bare underlined link (`margin-left:auto` on the LAST child, same pattern the connectors
  // list already used). And it resets the outer scroller (ctx.top()) — this IS a screen change (thread ->
  // chat list), and skipping it is the same stale-scrollTop bug the "open" click just below it fixes.
  const back = el("button","back",tt("back", null, "← Volver"));
  back.onclick=()=>{ ctx.top(); ctx.action("close"); };
  hd.appendChild(back);
  wrap.appendChild(hd);

  wrap.appendChild(threadStart(meta, ctx));
  const isGroup = !!(meta && meta.isGroup);
  // V2-680 — EMAIL is read like a mail client, not like a chat. A bubble timeline is the right shape for
  // WhatsApp and Telegram (short turns, one line each) and the wrong one for a letter: it clamped a
  // three-page mail to three lines behind a «mostrar más», hid the subject, showed neither the recipients
  // nor who was copied, and put an urgency stripe down the side of the one thing he had opened on purpose.
  const list = el("div","tl" + (active.platform === "email" ? " mpane" : ""));
  // V2-819 — this scroller is THIS conversation's: a repaint keeps him where he was in it, and a chat (not a mail,
  // whose latest letter is read from its top) opens on its latest message, the way every messaging app does.
  list.dataset.scrollKey = "thread:" + active.platform + ":" + active.chatId;
  if(active.platform !== "email") list.dataset.open = "bottom";
  if(active.platform === "email"){
    const who = {chatId: active.chatId};
    items.forEach(it=> list.appendChild(mailLetter(it, ctx, who)));
  } else {
    items.forEach(it=> list.appendChild(messageRow(it, ctx, rerender, isGroup)));
  }
  wrap.appendChild(list);
  // V2-611 — reply to the CONVERSATION, not a specific past message: `{}` lets the server resolve the
  // target from `active_chat` itself (`_resolve_target`), which is what «responderle» means for a thread.
  wrap.appendChild(composeBar(ctx, data, {}, active, rerender));
  return wrap;
}
