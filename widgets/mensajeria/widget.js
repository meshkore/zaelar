// Messaging widget client render. Contract: render(el, data, ctx).
// data = GET /widgets/mensajeria/data. No polling: the host (desktop.js) re-renders only when store.py emits the
//   SSE notice that this widget changed; QR, status, and messages refresh by themselves without timers.
//   data.platforms = { whatsapp:{status,qr}, telegram:{status,qr} }   data.items = [{n,platform,from,group,isGroup,body,urgencia,dirigido_a_mi,motivo}]
// ctx.action(name,payload) -> store mutation (read/dismiss/clear). Connector CONNECTION uses the messaging API
//   (same-origin fetch /api/messaging/*), so no .env editing; the user connects from here.
// SECURITY: bodies are UNTRUSTED (WhatsApp/Telegram). Always use textContent/createTextNode, never innerHTML
//   (anti-XSS), including when linking detected URLs inside a body (see `linkify`).
//
// PROFILE (2026-07-08): "simple" (default, minimal/timeline, no per-message borders) vs "completo" (original
// design, bordered cards + color badges). LOCAL preference (localStorage, cosmetic only); does not touch the store
// contract or pass through Hermes. Settings replaces the old footer with "connected" chips.
import { CSS } from "./js/style.js";
import { S, ORDER, PLAT, selectPlatform, tt } from "./js/state.js";
import { el } from "./js/dom.js";
import { connectPrompt, pendingStrip, settingsPanel } from "./js/settings.js";
import { mailKey, richList } from "./js/list.js";
import { mailDetail } from "./js/mail.js";
import { activityList, chatList, criteriaBar, platformChats } from "./js/chats.js";
import { threadView } from "./js/thread.js";
import { mailAct } from "./js/mailrail.js";
import { draftEditor, mailClient, mailMessage } from "./js/mailclient.js";
import { _captureWhere, _restoreWhere } from "./js/where.js";
import { _paintHeader } from "./js/header.js";

function injectStyles(){
  if(document.getElementById("hb-msg-css"))return;
  const s=document.createElement("style"); s.id="hb-msg-css"; s.textContent=CSS;
  document.head.appendChild(s);
}

export function render(root, data, ctx){
  const where = _captureWhere(root);
  _paint(root, data, ctx);
  _restoreWhere(root, where);
}

function _paint(root, data, ctx){
  S.T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  S.LANG = (ctx && ctx.lang) || "en";
  injectStyles();
  root.className="hb-msg";
  root.textContent="";

  const platforms=data.platforms||{};
  const items=data.items||[];
  const rerender=()=>render(root, data, ctx);
  const connectedCount = ORDER.filter(pl=>(platforms[pl]||{}).status==="connected").length;

  // A pushed VIEW (V2-543) applies only when its witness counter moves: «vuelve a la lista principal» /
  // «solo el WhatsApp» land even when repeated, and a plain repaint never yanks the operator's own choice.
  // V2-626 — it goes through the SAME door as a click, so the body follows the header by itself; and it is
  // resolved BEFORE `connect_focus` on purpose, so that when one payload carries both, the more specific
  // request (open THIS connector's wizard) is the one left standing.
  const pushed = data.view || null;
  if(pushed && Number(pushed.n||0) > 0 && Number(pushed.n) !== S.viewN){
    S.viewN = Number(pushed.n);
    selectPlatform(pushed.platform);
  }

  // V2-622 — an open thread/mail already carries its OWN header (platform + contact/subject + "← Volver");
  // the dashboard header below (inbox count, every platform dot, connectors/settings/clear) stacked ABOVE
  // that is not a second control surface, it is dead weight — on a hard refresh, with nothing to scroll past
  // to hide it, it read as two headers glued together (operator screenshot, 2026-09-08). Checked here, before
  // the dashboard header is even built, so it never gets appended for these two screens.
  const showChannels = connectedCount===0;
  const fItems = S.platFilter ? items.filter(it=>it.platform===S.platFilter) : items.filter(it=>it.highlight);
  const activeChat = !showChannels ? (data.active_chat || null) : null;
  if(activeChat){
    // V2-680 — a reading screen owns the card: header fixed, messages scrolling in the middle, reply box
    // pinned at the bottom. See the `.full` block in the stylesheet for why only these two screens opt in.
    root.classList.add("full");
    root.appendChild(threadView(activeChat, data.active_items||[], data, ctx, rerender, data.thread_meta||null));
    return;
  }
  // The mail section's own full-card screens (mailbox.py): a draft being finished, then one message open.
  const mb = data.mailbox || null;
  const draftKey = (mb && mb.draft && (data.drafts || {})[mb.draft]) ? mb.draft : null;
  // A new message whose Save/Send is on its way settles from the state: saved → the draft it became (or, sent,
  // the folder); refused → the same screen with his text and the reason.
  const pn = mb && mb.note;
  if(S.newMail && S.newMail.pending && pn && pn.at * 1000 >= S.newMail.pending - 1500){
    if(pn.key === "saved" || pn.key === "sent") S.newMail = null; else S.newMail.pending = null;
  }
  if(!showChannels && (S.newMail || draftKey)){
    root.classList.add("full");
    root.appendChild(draftEditor(S.newMail || data.drafts[draftKey], S.newMail ? null : draftKey,
      mb || {folders:[], folder:"INBOX", role:"inbox", rows:[]}, data, ctx, mailAct(ctx, data, rerender), rerender));
    return;
  }
  if(!showChannels && S.platFilter==="email" && mb && mb.open){
    root.classList.add("full");
    root.appendChild(mailMessage(mb, data, ctx, mailAct(ctx, data, rerender), rerender));
    return;
  }
  const openMailItem = (!showChannels && S.platFilter==="email" && S.openMail!=null)
    ? (fItems.find(x=>mailKey(x)===S.openMail) || items.find(x=>mailKey(x)===S.openMail))
    : null;
  if(openMailItem){
    root.classList.add("full");
    root.appendChild(mailDetail(openMailItem, data, ctx, ()=>{ S.openMail=null; rerender(); }, rerender));
    return;
  }

  _paintHeader(root, data, ctx, items, platforms, connectedCount, rerender);
  _paintBody(root, data, ctx, items, fItems, platforms, showChannels, rerender);
}

// Everything below the dashboard header of `_paint`: the pending strip, settings, then the screen the lens asks for.
function _paintBody(root, data, ctx, items, fItems, platforms, showChannels, rerender){
  // V2-800: what waits for his word, and what leaves later — inside its OWN channel, never on the home (the
  // operator: the home holds only the messages addressed to him). Email's live in the mail section's Drafts.
  const pend = (S.platFilter && S.platFilter !== "email") ? pendingStrip({
    drafts: Object.fromEntries(Object.entries(data.drafts || {}).filter(([, d]) => d && d.target && d.target.platform === S.platFilter)),
    sent: (data.sent || []).filter(r => r && r.platform === S.platFilter)}, ctx) : null;
  if(pend) root.appendChild(pend);

  if(S.settingsOpen) root.appendChild(settingsPanel(platforms, data, ctx, rerender));

  // CHANNELS area: onboarding when nothing is connected, or when the user opens it from the header connector
  // button, or when the brain pushed a `connect_focus`. Messaging starts EMPTY; do not dump every connection
  // form by default (V2-051 product decision, unchanged).
  if(showChannels){
    root.appendChild(connectPrompt(platforms, ctx));
    return;
  }

  // MESSAGES view, reached whenever at least one channel is connected (an open thread/mail already
  // returned above, before the dashboard header — see V2-622 near the top of this function). The lens
  // (V2-521) narrows every shape below to one platform.
  // V2-607 — TWO SHAPES, on purpose. With a lens on, this is that channel's own section: EVERYTHING unread it
  // has brought, nothing filtered. With no lens, this is the summary, and it shows only what meets the criterion
  // he set (`highlight`, default = addressed to him) — the rest is not gone, it is one tap away in its channel.
  const hidden = S.platFilter ? 0 : items.length - fItems.length;
  const emptyMsg = S.platFilter
    ? tt("nothing_from_", null, "Nada de ")+((PLAT[S.platFilter]||{}).label||S.platFilter)+tt("_to_handle", null, " que atender ✓")
    : (hidden ? tt("nothing_for_you", null, "Nada dirigido a ti ✓") : tt("nothing_now", null, "Nada que atender ahora ✓"));
  // V2-624 — the ACTIVITY view wins the lens when its platform has a criterion set: it is a different
  // question («qué se ha movido») than the pending inbox («qué me espera»), and the operator set it
  // explicitly. Applies in BOTH profiles — it is a lens-level view, not a density preference.
  const crit = S.platFilter ? (data.lens_criteria || {})[S.platFilter] : null;
  if(crit){
    root.appendChild(criteriaBar(S.platFilter, crit, ctx, rerender));
    const rows = (data.activity_chats || []).filter(r=> r.platform === S.platFilter);
    if(rows.length) root.appendChild(activityList(rows, ctx));
    else root.appendChild(el("div","empty",
      tt("no_activity", null, "Sin conversaciones guardadas con actividad en ese período") +
      ((S.platFilter === "telegram" || S.platFilter === "email")
        ? tt("no_activity_hint", null, " — «Traer del conector» las pide de verdad") : "")));
    return;
  }
  if(S.platFilter==="email"){
    // The mail section is a MAIL CLIENT (mailbox.py): the rail and the list fill the card and scroll each on its
    // own, whatever the density profile, the same way a thread is a thread in both.
    root.classList.add("full");
    root.appendChild(mailClient(data, ctx, rerender));
    return;
  }
  if(S.profile==="completo"){
    if(fItems.length) root.appendChild(richList(fItems, ctx));
    else root.appendChild(el("div","empty",emptyMsg));
    if(hidden) root.appendChild(restNote(hidden));
    return;
  }

  const lensList = S.platFilter ? (data.chat_list || {})[S.platFilter] : null;
  if(lensList){
    root.appendChild(platformChats(S.platFilter, lensList, ctx));
    return;
  }
  const chats = (data.chats || []).filter(c=> S.platFilter ? c.platform===S.platFilter : c.highlight);
  if(chats.length) root.appendChild(chatList(chats, ctx));
  else root.appendChild(el("div","empty",emptyMsg));
  if(hidden) root.appendChild(restNote(hidden));
}

// What the summary is NOT showing, said out loud. A filtered list that looks identical to an empty one is how
// the operator ends up believing a connector is broken — the failure V2-606 came from (V2-607).
function restNote(n){
  const d = el("div","rest");
  d.textContent = n===1 ? tt("one_more_msg", null, "1 mensaje más en sus canales") : n+tt("n_more_msgs", null, " mensajes más en sus canales");
  return d;
}
