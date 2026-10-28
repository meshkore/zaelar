// js/list.js — Message and email ROWS: the rich (complete-profile) list, one message row, the compact email row and list.
// Moved verbatim out of widget.js (refactor2710-12).
import { URG, _expanded, tt } from "./state.js";
import { badge, el, iconButton, markBusy, splitBody } from "./dom.js";
import { displayBody, fmtWhen, isBareMediaLabel, linkify, markupText, mediaBlock } from "./media.js";

// COMPLETE profile list: original design with bordered cards and color badges.
export function richList(items, ctx){
  const list=el("div","list");
  items.forEach(it=>{
    const urg = URG[it.urgencia]||URG.media;
    const mine = !!it.dirigido_a_mi;
    const row = el("div","row"+(mine?" mine":""));
    const dot = el("span","dot"); dot.style.background=urg.dot; row.appendChild(dot);

    const body = el("div","body");
    const from = el("div","from");
    from.appendChild(badge(it.platform));
    from.appendChild(el("span",null, it.from!=null?it.from:"?"));
    if(it.isGroup && it.group && it.group!==it.from) from.appendChild(el("span","grp","· "+it.group));
    if(mine) from.appendChild(el("span","tag",tt("for_you", null, "para ti")));
    if(urg.urgent) from.appendChild(el("span","tag",tt("urgent", null, "urgente")));
    body.appendChild(from);
    const media = mediaBlock(it);
    if(!(media && isBareMediaLabel(it.body))){
      const msgEl = el("div","msg"); linkify(msgEl, displayBody(it.body, it.mediaType)); body.appendChild(msgEl);
    }
    if(media) body.appendChild(media);
    if(it.motivo) body.appendChild(el("div","why", it.motivo));
    row.appendChild(body);

    const acts = el("div","acts");
    const read=iconButton("check",tt("mark_read", null, "Marcar como leído")); read.onclick=()=>ctx.action("read",{n:it.n});
    const dis=iconButton("close",tt("dismiss", null, "Descartar (no marcar leído)")); dis.onclick=()=>ctx.action("dismiss",{n:it.n});
    const mute=iconButton("mute",tt("mute_channel_long", null, "Silenciar este canal (no volverán a salir sus mensajes)"),"mute");
    mute.onclick=()=>{ markBusy(mute); ctx.action("hide",{n:it.n}); };
    acts.append(read,dis,mute); row.appendChild(acts);
    list.appendChild(row);
  });
  return list;
}

export function messageActions(it, ctx){
  const acts = el("div","tacts");
  const read=iconButton("check",tt("mark_read", null, "Marcar como leído")); read.onclick=()=>ctx.action("read",{n:it.n});
  const dis=iconButton("close",tt("dismiss", null, "Descartar (no marcar leído)")); dis.onclick=()=>ctx.action("dismiss",{n:it.n});
  acts.append(read,dis);
  if(it.platform==="email"){
    // Email-only affordances (V2-543): they act on the REAL mailbox, which is the whole point of the widget
    // being a substitute — other platforms have no archive/delete API and get no fake buttons.
    const arc=iconButton("archive",tt("archive", null, "Archivar en tu buzón real"));
    arc.onclick=()=>{ markBusy(arc); ctx.action("archive",{n:it.n}); };
    const del=iconButton("trash",tt("trash", null, "Borrar en tu buzón real (pide confirmación)"));
    del.onclick=()=>ctx.action("trash",{n:it.n});
    acts.append(arc,del);
  }
  const mute=iconButton("mute",tt("mute_channel", null, "Silenciar este canal"));
  mute.onclick=()=>{ markBusy(mute); ctx.action("hide",{n:it.n}); };
  acts.append(mute);
  return acts;
}

// V2-616 — a bubble timeline, not a repeated-name log. His report: in a 1:1 chat the sender's name on
// EVERY line is noise (the header above the list already names who this is), and his OWN replies need to
// stand apart from theirs at a glance — the classic left/right convention, not an indented quieter copy of
// the same row shape. `isGroup` is the ONLY thing that still earns a per-bubble name: a group has no single
// "who this is" to put in the header, so each inbound bubble still has to say which member sent it.
export function messageRow(it, ctx, rerender, isGroup){
  const urgente = it.urgencia === "alta";
  const key = String(it.messageId != null ? it.messageId : it.n);
  // V2-546 — «out» is what the OPERATOR wrote, here or in his own app; it is context, never something to act
  // on. And a row with no `n` is history: it is no longer in the inbox, so there is nothing left to mark read
  // or dismiss and offering the buttons would be a lie about what pressing them does.
  const outgoing = it.dir === "out";
  const actionable = !outgoing && it.n != null;

  const row = el("div","tbrow"+(outgoing?" out":""));
  row.dataset.rowKey = key;
  const stack = el("div","tbstack");
  const bubble = el("div","tbubble"+(urgente && !outgoing?" urg":""));
  if(isGroup && !outgoing) bubble.appendChild(el("div","tbfrom", it.from!=null?it.from:"?"));

  const when = fmtWhen(it.ts);
  const media = mediaBlock(it, when);
  const bareLabel = media && isBareMediaLabel(it.body);
  const {title, rest: _rest} = splitBody(displayBody(it.body, it.mediaType));
  const rest = markupText(_rest);
  const isLong = rest.length > 220 || rest.split("\n").length > 4;
  const expanded = _expanded.has(key);
  if(!bareLabel){
    if(title) bubble.appendChild(el("div","tbtitle", title));
    const bodyEl = el("div","tbbody"+(isLong && !expanded ? " clamp" : ""));
    linkify(bodyEl, rest);
    bubble.appendChild(bodyEl);
  }
  if(media) bubble.appendChild(media);

  if(isLong){
    const more = el("span","more", expanded ? tt("show_less", null, "mostrar menos") : tt("show_more", null, "mostrar más"));
    more.onclick=()=>{ expanded ? _expanded.delete(key) : _expanded.add(key); rerender(); };
    bubble.appendChild(more);
  }
  if(when && !(media && media.usedWhen)) bubble.appendChild(el("span","tbwhen", when));
  if(media && media.usedWhen) bubble.classList.add("hasaudio");
  stack.appendChild(bubble);

  if(actionable) stack.appendChild(messageActions(it, ctx));
  row.appendChild(stack);
  return row;
}

// ── EMAIL default view (V2-610) ─────────────────────────────────────────────────────────────────────────
// Operator's spec, verbatim in spirit: «un formato que se vea parecido a Gmail — la fecha y hora y el
// asunto, y si cabe quién lo envía, en dos líneas; si pido abrir el asunto pasa a una segunda pantalla con
// el detalle». A classic mail client's list shows subject/sender/time and NOTHING of the body; the body is
// what the second screen is for. `messageRow`'s inline clamp+«mostrar más» is the wrong shape for that —
// it is what threads (WhatsApp/Telegram) already use and stays theirs.
//
// This is the hardcoded DEFAULT, not a setting: the operator asked for it four times by voice in one
// session and the widget kept re-rendering the SAME expanded shape because no action existed to change it
// (`show_view` only ever moved the LENS, never the density) — the fix is to make the classic shape the one
// that ships, not to add a toggle nobody would find. His own words close the door on a toggle: «si un día
// el usuario decide hacer un fork del widget y cambiarlo, que lo haga».
export function emailRow(it, ctx, openMail){
  const urgente = it.urgencia === "alta";
  const row = el("div","mrow");
  row.title = tt("open", null, "Abrir");
  const lead = el("span","tlead");
  lead.style.background = urgente ? "var(--hb-risk,#e5484d)" : "var(--hb-accent,#3D6FE0)";
  row.appendChild(lead);

  const main = el("div","mmain");
  const line1 = el("div","mline1");
  line1.appendChild(el("span","mfrom", it.from!=null ? it.from : "?"));
  const when = fmtWhen(it.ts);
  if(when) line1.appendChild(el("span","mwhen", when));
  main.appendChild(line1);
  // `subject` is a first-class field on the item (mailbox.py/service.py) — reading it directly is more
  // reliable than parsing it back out of `body`, which only carries "[Asunto: X]\n…" on a LIVE arrival and
  // nothing at all on history (V2-546's `load_more` already folds subject into body there for that reason).
  const subj = (it.subject || "").trim() || displayBody(it.body, it.mediaType).split("\n")[0] || tt("no_subject", null, "(sin asunto)");
  main.appendChild(el("div","msubj", subj));
  row.appendChild(main);

  row.onclick=()=>{ ctx.top(); openMail(mailKey(it)); };
  return row;
}

// `n` is POSITIONAL and gets REUSED the moment an earlier item leaves the list (`_renumber` in data.py
// reassigns 1..len by order on every save) — `S.openMail` holding a bare `n` across a repaint would resolve
// to whatever mail inherited that number next, and silently show the WRONG one instead of falling back to
// the list. `messageId` is the STABLE identity every item already carries for exactly this reason (`_key()`
// in data.py, and the same fallback `_expanded`'s own key already uses a few lines above).
export function mailKey(it){ return it.messageId != null ? it.messageId : it.n; }

export function emailList(items, ctx, openMail){
  const wrap = el("div","tl");
  items.forEach(it=> wrap.appendChild(emailRow(it, ctx, openMail)));
  return wrap;
}
