// js/mailrail.js — THE EMAIL SECTION, A MAIL CLIENT (mailbox.py), first half: folders, crumb, the rail and its rows.
// Moved verbatim out of widget.js (refactor2710-12).
import { S, selectPlatform, tt } from "./state.js";
import { actionIcon, el, iconButton, markBusy } from "./dom.js";
import { fmtWhen } from "./media.js";

// ── THE EMAIL SECTION, A MAIL CLIENT (mailbox.py) ─────────────────────────────────────────────────────────
// The operator, 2026-10-26: the home holds only what is addressed to him; the mail section is his mailbox —
// the Inbox first, every folder the account syncs, a draft opened over the whole card with everything needed
// to finish it, and a way back one level at a time. Gmail is the reference. All of it is SERVER state
// (`data.mailbox`), so a tap and a voice order land on the same screen; a tap repaints from the action's own
// answer instead of waiting for the store's notice.
export const FOLDER_FB = {inbox:"Recibidos", flagged:"Destacados", drafts:"Borradores", sent:"Enviados",
                   archive:"Archivo", all:"Todos", junk:"Spam", trash:"Papelera"};
export function folderLabel(f){
  // A role this card has no word for keeps the server's own name — an empty row in the rail is worse than English.
  return f && f.role ? tt("folder_"+f.role, null, FOLDER_FB[f.role] || f.label || "") : ((f && f.label) || "");
}

export function mailAct(ctx, data, rerender){
  return (name, payload) => Promise.resolve(ctx.action(name, payload)).then(r => {
    if(r && r.mailbox){ Object.assign(data, r); rerender(); }
    return r;
  });
}

export function mailDrafts(data){
  return Object.values(data.drafts || {}).filter(d => d && d.target && (d.target.platform || "email") === "email")
    .sort((a, b) => (b.at || 0) - (a.at || 0));
}

export function mailFolderList(mb){
  const folders = (mb.folders && mb.folders.length) ? mb.folders.slice() : [{name:"INBOX", role:"inbox", label:"INBOX"}];
  // The card's own drafts always have a home, even on a server that names no Drafts folder.
  if(!folders.some(f => f.role === "drafts")) folders.splice(1, 0, {name:"@drafts", role:"drafts", label:""});
  return folders;
}

// Navigation bar of every mail screen: Home › Correo › <folder> [› <what is open>] and «← <folder>» on the right.
export function mailCrumb(mb, ctx, act, current){
  const bar = el("div","thd mcrumb");
  const home = iconButton("home", tt("home", null, "Inicio"), "mchome");
  home.onclick = () => { selectPlatform(null); ctx.top && ctx.top(); act("show_view", {platform:"all"}); };
  bar.appendChild(home);
  // One level up is the list this screen was opened from: a draft's own `back_to`, else the list on screen.
  const up = mailWhere(mb.draft && mb.back_to ? {...mb, ...mb.back_to} : mb);
  const parts = [[tt("mail_section", null, "Correo"), () => act("mail_folder", {folder:"inbox"})],
                 [up, current ? () => act("mail_back", {}) : null]];
  if(current) parts.push([current, null]);
  parts.forEach(([label, go], i) => {
    if(i) bar.appendChild(el("span","msep","›"));
    const c = el(go ? "button" : "b", go ? "mcr" : "mcr cur", label);
    if(go) c.onclick = go;
    bar.appendChild(c);
  });
  if(current){
    const back = el("button","back", "← " + up);
    back.onclick = () => act("mail_back", {});
    bar.appendChild(back);
  }
  return bar;
}

// The provider's categories of the Inbox, named in his language; a key no bundle names shows as the provider sent it.
export const CAT_FB = {primary:"Principal", social:"Social", promotions:"Promociones", updates:"Notificaciones", forums:"Foros"};
export const CAT_ICON = {primary:"inbox", social:"users", promotions:"tag", updates:"info", forums:"chat"};
export const ROLE_ICON = {inbox:"inbox", flagged:"star", drafts:"file", sent:"send", archive:"archive", all:"mail",
                   junk:"alert", trash:"trash"};
// Where unread is noise (what he sent, his drafts, the bin, «all mail»), no figure is shown — as Gmail does.
export const NO_COUNT = new Set(["sent", "drafts", "trash", "all", "flagged", "archive"]);
export function catLabel(key){ return tt("cat_" + key, null, CAT_FB[key] || key); }

// Where he is inside the mail section, in one name: the category of the Inbox, or the folder.
export function mailWhere(mb){
  if(String(mb.folder).toUpperCase() === "INBOX" && mb.category) return catLabel(mb.category);
  return folderLabel(mailFolderList(mb).find(f => f.name === mb.folder) || {role:"inbox"});
}

export function railEntry(icon, label, n, on, go, cls, rerender){
  const b = el("button", "mnav" + (on ? " on" : "") + (cls ? " " + cls : ""));
  b.type = "button"; b.title = label;
  b.setAttribute("aria-label", n ? `${label} (${n})` : label);
  if(on) b.setAttribute("aria-current", "page");
  b.append(actionIcon(icon), el("span", "mnl", label));
  if(n) b.appendChild(el("span", "mfn", String(n)));      // the provider's real number, never rounded
  // A tap in the drawer closes it at once; the list follows when the action answers.
  b.onclick = () => { const was = S.railOpen; S.railOpen = false; go(); if(was && rerender) rerender(); };
  return b;
}

// ONE left rail (V2-807 T-01, the operator's design): Compose; the Inbox and, under it, every category the provider
// sorts it by; then every other folder the server declares. Each with the PROVIDER's unread figure — an Inbox that
// is sorted counts its first category, the way Gmail's own badge does.
export function mailRail(mb, data, ctx, act, rerender){
  const rail = el("nav", "mrail");
  rail.setAttribute("aria-label", tt("mail_section", null, "Correo"));
  const compose = el("button", "bt bt-primary mcompose");
  compose.title = tt("compose", null, "Redactar");
  compose.append(actionIcon("pen"), el("span", "mnl", tt("compose", null, "Redactar")));
  compose.onclick = () => { S.railOpen = false; S.newMail = {to:"", subject:"", text:""}; rerender(); };
  rail.appendChild(compose);
  const counts = mb.counts || {};
  const cats = mb.categories || [];
  const inInbox = String(mb.folder).toUpperCase() === "INBOX";
  const drafts = mailDrafts(data).length;
  mailFolderList(mb).forEach((f, i) => {
    const label = folderLabel(f);
    if(f.role === "inbox"){
      const n = cats.length ? (cats[0].unread || 0) : (counts[f.name] || 0);
      rail.appendChild(railEntry("inbox", label, n, inInbox && !cats.length, () => act("mail_folder", {folder: f.name}),
                                 "", rerender));
      cats.forEach(c => rail.appendChild(railEntry(CAT_ICON[c.key] || "tag", catLabel(c.key), c.unread || 0,
        inInbox && mb.category === c.key, () => act("mail_folder", {folder: f.name, category: c.key}), "sub", rerender)));
      return;
    }
    if(i && !f.role && (mailFolderList(mb)[i - 1] || {}).role) rail.appendChild(el("div", "mrailsep"));
    const n = f.role === "drafts" ? drafts : (NO_COUNT.has(f.role) ? 0 : (counts[f.name] || 0));
    rail.appendChild(railEntry(ROLE_ICON[f.role] || "tag", label, n, f.name === mb.folder,
                               () => act("mail_folder", {folder: f.name}), "", rerender));
  });
  // His criteria over the categories (V2-807 T-03): rows of his rules, in his words, each removable here too.
  const mine = mb.rules || [];
  if(mine.length){
    const box = el("div", "mrules");
    box.appendChild(el("div", "mruleshd", tt("mail_rules", null, "Tus criterios")));
    mine.forEach(r => {
      const row = el("div", "mrule");
      row.appendChild(el("span", "mrulet", r.text));
      const x = iconButton("close", tt("rule_forget", null, "Quitar este criterio"), "mrulex");
      x.onclick = () => { markBusy(x); act("mail_sort", {forget: r.id}); };
      row.appendChild(x);
      box.appendChild(row);
    });
    rail.appendChild(box);
  }
  return rail;
}

export function folderRow(r, mb, act){
  const row = el("div","mrow" + (r.seen ? " seen" : " unseen"));
  const lead = el("span","tlead");
  if(!r.seen) lead.style.background = "var(--hb-accent,#3D6FE0)";
  row.appendChild(lead);
  const main = el("div","mmain");
  const line1 = el("div","mline1");
  const sent = mb.role === "sent" || mb.role === "drafts";
  line1.appendChild(el("span","mfrom", sent ? (tt("to", null, "Para") + ": " + (r.to || "?")) : (r.fromName || r.from || "?")));
  if(r.pending) line1.appendChild(el("span","mtag", tt("for_you", null, "para ti")));
  const when = fmtWhen(r.ts);
  if(when) line1.appendChild(el("span","mwhen", when));
  main.appendChild(line1);
  main.appendChild(el("div","msubj", (r.subject || "").trim() || tt("no_subject", null, "(sin asunto)")));
  row.appendChild(main);
  row.onclick = () => act("mail_open", {uid: r.uid, folder: mb.folder});
  return row;
}

export function draftRow(d, act){
  const t = d.target || {};
  const row = el("div","mrow mdraftrow");
  row.appendChild(el("span","tlead"));
  const main = el("div","mmain");
  const line1 = el("div","mline1");
  line1.appendChild(el("span","mdtag", tt("draft_tag", null, "Borrador")));
  line1.appendChild(el("span","mfrom", t.name || t.to || t.chatId || "?"));
  const when = fmtWhen(d.at);
  if(when) line1.appendChild(el("span","mwhen", when));
  main.appendChild(line1);
  const subj = (t.subject || "").trim();
  main.appendChild(el("div","msubj", (subj ? subj + " — " : "") + String(d.text || "").replace(/\s+/g, " ")));
  row.appendChild(main);
  row.onclick = () => act("open_draft", {key: d.key});
  return row;
}

// A draft has ONE face — its own screen (V2-807 T-02). On any other list it is one line that opens it: never its
// body, never a Send button. Several drafts point at the Drafts entry instead.
export function draftPointer(mb, data, act){
  const mine = mailDrafts(data);
  if(!mine.length || mb.role === "drafts") return null;
  const t = mine[0].target || {};
  const one = mine.length === 1;
  const b = el("button","mdptr");
  b.type = "button";
  b.append(actionIcon("pen"), el("span", "mdptrt", one
    ? tt("held_to", {to: t.name || t.to}, `Borrador para ${t.name || t.to}`)
    : tt("n_drafts", {n: mine.length}, `${mine.length} borradores a medias`)),
    el("span", "mdptro", tt("open_draft", null, "Abrir")));
  b.onclick = () => one ? act("open_draft", {key: mine[0].key}) : act("mail_folder", {folder: "drafts"});
  return b;
}
