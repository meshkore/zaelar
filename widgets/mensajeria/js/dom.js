// js/dom.js — Small DOM builders shared by every part: elements, platform badges and chips, the SVG action icons, body cleanup.
// Moved verbatim out of widget.js (refactor2710-12).
import { BRAND_SVG, PLAT, SVG_NS, tt } from "./state.js";

export function el(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=String(text); return e; }

export function badge(platform){
  const p=PLAT[platform]||{label:platform||"?",bg:"var(--hb-muted,#6b7b92)"};
  const b=el("span","badge",p.label); b.style.background=p.bg; return b;
}

// Small circle with the platform initial, used in the header (connection state, "on"=green) and in each simple
// profile row (fixed brand color, informational rather than state).
export function miniDot(platform, on){
  const p=PLAT[platform]||{label:"?"};
  const d=el("span","pdot"+(on?" on":""), p.label[0]);
  d.title = p.label + (on ? tt("dot_connected", null, ": conectado") : tt("dot_disconnected", null, ": no conectado"));
  return d;
}

export function platformChip(platform){
  const p=PLAT[platform]||{label:platform||"?",bg:"var(--hb-muted,#6b7b92)"};
  const c=el("span","pchip",(p.label||"?")[0]); c.style.background=p.bg; c.title=p.label;
  return c;
}

// Real brand icon for the header connection state. `on` only changes opacity (dimmed = disconnected); brand color
// always remains, so the app stays recognizable even when unlinked.
// Action icons are inline SVG (same self-contained pattern as BRAND_SVG above):
// the row of per-message buttons used to be emoji text, and one emoji font drew
// the mute glyph as something the operator read as a subwoofer (live report,
// 2026-09-18: "an okay flag, then an x, then a subwoofer"). Stroke style matches
// the app icon language (24px grid, currentColor). Same five actions, same order.
export const ACTION_SVG = {
  home:    [["path", {d: "M3 10.5 12 3l9 7.5"}], ["path", {d: "M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"}]],
  pen:     [["path", {d: "M12 20h9"}], ["path", {d: "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"}]],
  check:   [["path", {d: "M20 6 9 17l-5-5"}]],
  close:   [["path", {d: "M18 6 6 18"}], ["path", {d: "m6 6 12 12"}]],
  archive: [["rect", {x: "2", y: "3", width: "20", height: "5", rx: "1"}],
            ["path", {d: "M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"}],
            ["path", {d: "M10 12h4"}]],
  trash:   [["path", {d: "M3 6h18"}],
            ["path", {d: "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"}],
            ["path", {d: "M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"}],
            ["path", {d: "M10 11v6"}], ["path", {d: "M14 11v6"}]],
  mute:    [["path", {d: "M11 5 6 9H2v6h4l5 4V5z"}],
            ["path", {d: "m22 9-6 6"}], ["path", {d: "m16 9 6 6"}]],
  // Composing and the chat list — same 24px stroke language.
  clip:    [["path", {d: "m21.4 11.6-8.5 8.5a5.5 5.5 0 0 1-7.8-7.8l8.5-8.5a3.7 3.7 0 0 1 5.2 5.2l-8.5 8.5a1.8 1.8 0 0 1-2.6-2.6l7.8-7.8"}]],
  pencil:  [["path", {d: "M12 20h9"}], ["path", {d: "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"}]],
  users:   [["path", {d: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"}], ["circle", {cx: "9", cy: "7", r: "4"}],
            ["path", {d: "M22 21v-2a4 4 0 0 0-3-3.9"}], ["path", {d: "M16 3.1a4 4 0 0 1 0 7.8"}]],
  image:   [["rect", {x: "3", y: "3", width: "18", height: "18", rx: "2"}], ["circle", {cx: "9", cy: "9", r: "2"}],
            ["path", {d: "m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"}]],
  video:   [["path", {d: "m16 13 5.2 3.5a.5.5 0 0 0 .8-.4V7.9a.5.5 0 0 0-.8-.4L16 11"}],
            ["rect", {x: "2", y: "6", width: "14", height: "12", rx: "2"}]],
  mic:     [["path", {d: "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"}], ["path", {d: "M19 10v2a7 7 0 0 1-14 0v-2"}],
            ["path", {d: "M12 19v3"}]],
  file:    [["path", {d: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"}], ["path", {d: "M14 2v4a2 2 0 0 0 2 2h4"}]],
  // The mail rail: one icon per folder role and per provider category (V2-807 T-01).
  inbox:   [["path", {d: "M22 12h-6l-2 3h-4l-2-3H2"}],
            ["path", {d: "M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z"}]],
  star:    [["path", {d: "m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8-6.2-3.2L5.8 21 7 14.2 2 9.3l6.9-1Z"}]],
  send:    [["path", {d: "m22 2-7 20-4-9-9-4Z"}], ["path", {d: "M22 2 11 13"}]],
  mail:    [["rect", {x: "2", y: "4", width: "20", height: "16", rx: "2"}], ["path", {d: "m22 7-10 6L2 7"}]],
  alert:   [["circle", {cx: "12", cy: "12", r: "10"}], ["path", {d: "M12 8v4"}], ["path", {d: "M12 16h.01"}]],
  tag:     [["path", {d: "M12.6 2.6A2 2 0 0 0 11.2 2H4a2 2 0 0 0-2 2v7.2a2 2 0 0 0 .6 1.4l8.7 8.7a2.4 2.4 0 0 0 3.4 0l6.6-6.6a2.4 2.4 0 0 0 0-3.4Z"}],
            ["circle", {cx: "7.5", cy: "7.5", r: "1"}]],
  info:    [["circle", {cx: "12", cy: "12", r: "10"}], ["path", {d: "M12 16v-4"}], ["path", {d: "M12 8h.01"}]],
  chat:    [["path", {d: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"}]],
  menu:    [["path", {d: "M4 6h16"}], ["path", {d: "M4 12h16"}], ["path", {d: "M4 18h16"}]],
  bellOff: [["path", {d: "M8.7 3A6 6 0 0 1 18 8a21.3 21.3 0 0 0 .6 5"}], ["path", {d: "M17 17H3s3-2 3-9a4.7 4.7 0 0 1 .3-1.7"}],
            ["path", {d: "M10.3 21a1.9 1.9 0 0 0 3.4 0"}], ["path", {d: "m2 2 20 20"}]],
};
export function actionIcon(name){
  const svg=document.createElementNS(SVG_NS,"svg");
  svg.setAttribute("viewBox","0 0 24 24"); svg.setAttribute("width","14"); svg.setAttribute("height","14");
  svg.setAttribute("fill","none"); svg.setAttribute("stroke","currentColor");
  svg.setAttribute("stroke-width","2"); svg.setAttribute("stroke-linecap","round");
  svg.setAttribute("stroke-linejoin","round"); svg.setAttribute("aria-hidden","true");
  for(const [tag, attrs] of (ACTION_SVG[name]||[])){
    const s=document.createElementNS(SVG_NS,tag);
    for(const k of Object.keys(attrs)) s.setAttribute(k,attrs[k]);
    svg.appendChild(s);
  }
  return svg;
}
export function iconButton(name, title, cls){
  const b=document.createElement("button");
  b.type="button"; if(cls)b.className=cls;
  b.title=title; b.setAttribute("aria-label",title);
  b.appendChild(actionIcon(name));
  return b;
}
// Busy feedback that keeps the icon: disabling + dimming blocks a second press
// without wiping the button's SVG (the old textContent="…" replaced the glyph).
export function markBusy(btn){ btn.disabled=true; btn.style.opacity=".45"; }

export function brandIcon(platform, on){
  const p=PLAT[platform]||{label:platform||"?",bg:"var(--hb-muted,#6b7b92)"};
  const spec=BRAND_SVG[platform];
  const wrap=el("span","picon"+(on?" on":""));
  wrap.title=p.label+(on?tt("dot_connected", null, ": conectado"):tt("dot_disconnected", null, ": no conectado"));
  wrap.style.color=p.bg;
  if(spec){
    const svg=document.createElementNS(SVG_NS,"svg");
    svg.setAttribute("viewBox",spec.viewBox); svg.setAttribute("width","17"); svg.setAttribute("height","17");
    svg.setAttribute("aria-hidden","true");
    const path=document.createElementNS(SVG_NS,"path");
    path.setAttribute("d",spec.path); path.setAttribute("fill","currentColor");
    svg.appendChild(path); wrap.appendChild(svg);
  } else {
    wrap.appendChild(document.createTextNode((p.label||"?")[0]));
  }
  return wrap;
}

// One box in an icon grid (V2-570): the connector list AND the email-provider picker are both "choose one of
// several, shown as an icon with a label", so they share this renderer instead of one being a grid and the
// other a dropdown. `it.cls` names the extra state class ("sel" = chosen in a picker, "conn" = connected in
// the connector list) — the two never mean the same thing, so they get their own visual language.
export function iconGrid(items){
  const grid=el("div","igrid");
  items.forEach(it=>{
    const box=document.createElement("button");
    box.type="button";
    box.className="ibox"+(it.cls?(" "+it.cls):"");
    const holder=el("span","iicon"); holder.appendChild(it.icon); box.appendChild(holder);
    box.appendChild(el("span","ilabel", it.label));
    if(it.sub) box.appendChild(el("span","isub", it.sub));
    if(it.onClick) box.onclick=it.onClick;
    grid.appendChild(box);
  });
  return grid;
}

// No brand icon exists for a specific email PROVIDER (Gmail/Outlook/iCloud/Yahoo) the way one does for the
// whole email channel — an avatar with the provider's initial is honest about that instead of pretending.

// Split a short message title from the rest of the body when they are joined by a blank line, a common pattern in
// triaged messages. If the pattern does not fit, everything is body text with no title.
export function splitBody(body){
  const idx = body.indexOf("\n\n");
  if(idx > 0 && idx <= 100){
    const title = body.slice(0, idx).trim();
    const rest = body.slice(idx + 2).trim();
    if(title && !title.includes("\n") && rest) return {title, rest};
  }
  return {title: "", rest: body};
}

// Minimal incoming-text cleanup: collapse excessive line breaks (3+) so huge gaps do not appear. Never touches
// emojis/links/content, only spacing.
export function cleanBody(text){
  return String(text==null?"":text).replace(/\n{3,}/g, "\n\n").trim();
}
