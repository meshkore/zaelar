// js/mail.js — READING A MAIL (V2-680): the envelope, the letter and the detail screen.
// Moved verbatim out of widget.js (refactor2710-12).
import { tt } from "./state.js";
import { el, splitBody } from "./dom.js";
import { displayBody, fmtWhen, isBareMediaLabel, linkify, markupText, mediaBlock } from "./media.js";
import { composeBar } from "./compose.js";
import { messageActions } from "./list.js";

// The SECOND screen (V2-610): full subject, sender, timestamp and body — everything the compact row leaves
// out. Reuses `messageActions` so read/dismiss/archive/trash/mute stay the SAME five buttons the row itself
// used to carry, wired to the same `n` (unambiguous: read/dismiss/archive/trash/hide all resolve by the
// item's own `n` against the flat renumbered list, never against a chat grouping — see data.py).
// ── READING A MAIL (V2-680) ───────────────────────────────────────────────────────────────────────────
// One letter, shaped like a mail client: subject, the envelope (who wrote it, who it went to, who was
// copied, when) and the body WHOLE. `full` says whether the body may be cut — it never may here; the
// argument exists so the preview shapes elsewhere keep their own behaviour.
//
// Everything is DERIVED from what the message actually carries. An address we do not have is a row that
// is not drawn, never an invented one and never an empty label: "Cc: —" states something false about the
// original mail, and the operator reads this pane to know who was on it.
export function mailEnvelope(it, meta){
  const env = el("div","menv");
  const row = (k, node)=>{ env.appendChild(el("div","menvk", k)); env.appendChild(node); };
  const val = (text, addr)=>{
    const v = el("div","menvv", text);
    if(addr && addr !== text) v.appendChild(el("span","addr", " · " + addr));
    return v;
  };
  const outgoing = it.dir === "out";
  // The sender. On his OWN reply the thread stores our label, and the person it went TO is the
  // conversation itself — which is the only place that identity survives once the item is answered.
  const who = outgoing ? tt("you", null, "Tú") : (it.who || it.from || "?");
  row(tt("from", null, "De"), val(who, outgoing ? "" : (it.senderId || "")));
  const other = (meta && meta.chatId) || it.senderId || "";
  if(outgoing && other) row(tt("to", null, "Para"), val(other, ""));
  else if(!outgoing) row(tt("to", null, "Para"), val(tt("you", null, "Tú"), ""));
  const cc = (it.recipients || []).filter(a => typeof a === "string" && a.trim());
  if(cc.length) row(tt("cc", null, "Copia"), val(cc.join(", "), ""));
  const when = fmtWhen(it.ts);
  if(when) row(tt("date", null, "Fecha"), val(when, ""));
  return env;
}

// The connector folds the subject into the body as a leading "[Asunto: X]" line (mailbox.parse_message), so
// a screen that ALSO shows the subject in its own field prints it twice — visible in the very first render
// of this pane. Stripping it is exact and not a guess: that marker is ours, written by our own parser, and
// only the FIRST line is ever touched.
export const _SUBJECT_MARKER = /^\s*\[Asunto:([^\]\n]*)\]\n?/;

export function stripSubjectLine(text){
  return String(text == null ? "" : text).replace(_SUBJECT_MARKER, "");
}

export function mailLetter(it, ctx, meta){
  const wrap = el("div","mltr"+(it.dir === "out" ? " out" : ""));
  const media = mediaBlock(it);
  const raw = displayBody(it.body, it.mediaType);
  const marked = _SUBJECT_MARKER.exec(raw);
  const {title, rest} = splitBody(stripSubjectLine(raw));
  // The stored subject wins; the marker line is the fallback for a message ingested before the field
  // existed, and a plain first-line title is the last resort for a body with neither.
  const subject = (it.subject || "").trim() || (marked ? marked[1].trim() : "") || title || "";
  if(subject) wrap.appendChild(el("div","mltrsubj", subject));
  wrap.appendChild(mailEnvelope(it, meta));
  if(!(media && isBareMediaLabel(it.body))){
    const body = el("div","mltrbody");
    // NO clamp and NO «mostrar más», at any length — his rule: «lo quiero todo entero». The pane around
    // this scrolls, which is what makes showing everything affordable.
    // `rest` is the body once splitBody has lifted the "[Asunto: X]" line off it; `title` is the fallback
    // for a message that is nothing BUT that line.
    linkify(body, markupText(rest || title));   // the «[Asunto]» line is lifted first, then the markup
    wrap.appendChild(body);
  }
  if(media) wrap.appendChild(media);
  if(it.dir !== "out" && it.n != null) wrap.appendChild(messageActions(it, ctx));
  return wrap;
}

export function mailDetail(it, data, ctx, closeMail, rerender){
  const wrap = el("div","thread plat-email");
  const hd = el("div","thd");
  const back = el("button","back",tt("back_inbox", null, "← Bandeja")); back.onclick=()=>{ ctx.top(); closeMail(); };
  hd.appendChild(back);
  wrap.appendChild(hd);

  // V2-680 — the SAME letter shape the thread uses, inside the same bordered pane, so «open this mail»
  // and «open this conversation» are not two different-looking screens for the same act of reading.
  const pane = el("div","mdet mpane");
  pane.appendChild(mailLetter({...it, who: it.from}, ctx, {chatId: it.chatId}));
  wrap.appendChild(pane);

  // V2-611 — reply to THIS mail specifically: `n`+`messageId` address it unambiguously, the same identity
  // read/dismiss/archive/trash already use (never the chat-grouping numbering, which the flat email list
  // does not have). Outgoing mail (his own, echoed into the thread) has nothing to reply TO.
  if(it.dir !== "out") wrap.appendChild(composeBar(ctx, data, {n: it.n, messageId: it.messageId}, null, rerender, it));
  return wrap;
}
