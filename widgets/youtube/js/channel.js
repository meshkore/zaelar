// youtube widget — SUBSCRIPTIONS: the channel cards and a channel's own page.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { Y } from "./state.js";
import { el, tt } from "./shared.js";

// ── SUBSCRIPTIONS: cards and the channel page (2026-09-29) ─────────────────────────────────────────────────
export const DAY = 86400;

export function hl(ctx){ const l = String((ctx && ctx.lang) || document.documentElement.lang || "en"); return l.slice(0, 2); }
export function fmtNum(n, ctx){
  try{ return new Intl.NumberFormat(hl(ctx), {notation: "compact", maximumFractionDigits: 1}).format(n); }
  catch(_){ return String(n); }
}
export function relAge(ts, ctx){
  if(!ts) return "";
  const d = Math.max(0, Date.now() / 1000 - Number(ts));
  const steps = [[60, "second", 1], [3600, "minute", 60], [DAY, "hour", 3600], [7 * DAY, "day", DAY],
                 [30 * DAY, "week", 7 * DAY], [365 * DAY, "month", 30 * DAY], [Infinity, "year", 365 * DAY]];
  const [, unit, div] = steps.find((x) => d < x[0]);
  try{ return new Intl.RelativeTimeFormat(hl(ctx), {numeric: "auto"}).format(-Math.round(d / div), unit); }
  catch(_){ return ""; }
}
export function initial(name){ return String(name || "?").trim().slice(0, 1).toUpperCase() || "?"; }
export function avatar(url, name, big){
  if(url){
    const i = document.createElement("img");
    i.className = "hb-yt-av" + (big ? " lg" : ""); i.alt = ""; i.loading = "lazy"; i.referrerPolicy = "no-referrer";
    i.src = url;
    return i;
  }
  return el("span", "hb-yt-av" + (big ? " lg" : ""), initial(name));
}
export function statsLine(m, ctx){
  const bits = [];
  if(m.subscribers) bits.push(tt("ch_subs", {n: fmtNum(m.subscribers, ctx)}, "{n} suscriptores"));
  if(m.videos) bits.push(tt("ch_videos", {n: fmtNum(m.videos, ctx)}, "{n} vídeos"));
  return bits.join(" · ");
}

// One action that re-reads the card afterwards: the loader goes up BEFORE the request and comes down when
// the answer is back, whatever it says — the store save that follows repaints the content itself.
export async function chAct(root, ctx, name, payload, busy){
  if(!ctx || !ctx.action) return null;
  Y.chBusy = busy || "";
  if(busy) repaintSubs(root, ctx);
  let r = null;
  try{ r = await ctx.action(name, Object.assign({hl: hl(ctx)}, payload || {})); }catch(_){ r = null; }
  Y.chBusy = "";
  repaintSubs(root, ctx);
  return r;
}
export function repaintSubs(root, ctx){
  const E = root._hbYtEls || {};
  if(E.subsBox) renderSubs(E.subsBox, root, root._hbYtData || {}, ctx);
}

export function renderSubs(box, root, data, ctx){
  box.textContent = "";
  const pg = data.channel_page || {};
  if(pg.id){ renderChannelPage(box, root, pg, ctx); return; }
  Y.chEntered = "";                                   // he left the page: walking in again refreshes it again

  // `channel_cards` is view_data's enriched view; a snapshot without it (an older engine) still has the
  // names he follows, and a name is a card.
  const cards = Array.isArray(data.channel_cards) ? data.channel_cards
    : (Array.isArray(data.channels) ? data.channels : []).filter((c) => c && c.name)
        .map((c) => ({name: String(c.name), tried: true}));
  const head = el("div", "hb-yt-sechead");
  const ttl = el("div", "hb-yt-hometitle");
  ttl.appendChild(el("span", "", tt("tab_subs", null, "Suscripciones")));
  ttl.appendChild(el("span", "hb-yt-homecount", String(cards.length)));
  head.appendChild(ttl);
  head.appendChild(el("span", "hb-yt-secnote", tt("subs_ours", null, "Solo en Zaelar — no te suscribe en YouTube")));
  box.appendChild(head);
  if(!cards.length){
    box.appendChild(el("div", "hb-yt-secmsg", tt("subs_none", null,
      "No sigues a nadie todavía. Con un vídeo puesto, di «sigue a este canal» y guardo al autor — sin tocar ninguna cuenta.")));
    return;
  }
  // Card facts are fetched once, lazily, for the channels that do not have them yet (bounded server-side).
  if(cards.some((c) => !c.tried && (!c.resolved || !c.videos)) && ctx && ctx.action && Date.now() - Y.chSyncAsked > 60000){
    Y.chSyncAsked = Date.now();
    try{ ctx.action("sync_channels", {hl: hl(ctx)}); }catch(_){}
  }
  const grid = el("div", "hb-yt-chgrid");
  cards.forEach((c) => {
    const card = el("div", "hb-yt-chcard");
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.title = tt("open_channel", {name: c.name}, "Abrir el canal {name}");
    card.appendChild(avatar(c.avatar, c.name));
    const info = el("div", "hb-yt-chinfo");
    info.appendChild(el("div", "hb-yt-chname", c.name));
    if(c.handle) info.appendChild(el("div", "hb-yt-chhandle", c.handle));
    const st = statsLine(c, ctx);
    info.appendChild(el("div", "hb-yt-chstats",
      st || (c.tried ? tt("ch_no_facts", null, "Sin datos del canal") : tt("ch_loading", null, "Buscando datos del canal…"))));
    const acts = el("div", "hb-yt-chacts");
    const vids = el("span", "hb-yt-chip", tt("videos_to_queue", null, "vídeos → cola"));
    vids.title = tt("latest_to_queue", {name: c.name}, "Lo más reciente de {name}, a la cola");
    vids.addEventListener("click", (e) => {
      e.stopPropagation();
      if(ctx && ctx.action) ctx.action("channel_videos", {channel: c.name});
      if(root._hbYtSelectTab) root._hbYtSelectTab("cola");
    });
    acts.appendChild(vids);
    info.appendChild(acts);
    card.appendChild(info);
    const x = el("button", "hb-yt-rowx hb-yt-chx", "✕");
    x.title = tt("unfollow", null, "Dejar de seguir");
    x.setAttribute("aria-label", x.title);
    x.addEventListener("click", (e) => {
      e.stopPropagation();
      if(ctx && ctx.action) ctx.action("unfollow_channel", {channel: c.name});
    });
    card.appendChild(x);
    const open = () => { chAct(root, ctx, "open_channel", {channel: c.name}, "refresh"); };
    card.addEventListener("click", open);
    card.addEventListener("keydown", (e) => { if(e.key === "Enter" || e.key === " "){ e.preventDefault(); open(); } });
    grid.appendChild(card);
  });
  box.appendChild(grid);
}

export function sectionLabel(t){
  switch(t){
    case "videos":    return tt("ch_tab_videos", null, "Vídeos");
    case "streams":   return tt("ch_tab_live", null, "En directo");
    case "shorts":    return tt("ch_tab_shorts", null, "Shorts");
    case "playlists": return tt("ch_tab_playlists", null, "Listas");
    default:          return t;
  }
}

export function renderChannelPage(box, root, pg, ctx){
  // Walking in = ONE refresh for what is new, with its loader up («Buscando últimos vídeos del canal»).
  // Keyed on the channel id, so a click, a voice «ábreme el canal de X» and a reload all get exactly one.
  if(Y.chEntered !== pg.id && !Y.chBusy){
    Y.chEntered = pg.id;
    setTimeout(() => chAct(root, ctx, "refresh_channel", {}, "refresh"), 0);
    Y.chBusy = "refresh";
  }
  const m = pg.meta || {};
  const wrap = el("div", "hb-yt-chpage");
  const back = el("button", "hb-yt-crumb", pg.playlist ? tt("back_lists", null, "‹ Listas")
                                                       : tt("back_subs", null, "‹ Suscripciones"));
  back.addEventListener("click", () => {
    if(pg.playlist) chAct(root, ctx, "channel_playlist", {playlist: ""}, "");
    else chAct(root, ctx, "close_channel", {}, "");
  });
  wrap.appendChild(back);

  const head = el("div", "hb-yt-chhead");
  head.appendChild(avatar(m.avatar, pg.name || m.title, true));
  const info = el("div", "hb-yt-chinfo");
  info.appendChild(el("div", "hb-yt-chname", pg.playlist ? (pg.playlist.title || pg.name) : (m.title || pg.name)));
  const sub = [m.handle, statsLine(m, ctx)].filter(Boolean).join(" · ");
  if(pg.playlist) info.appendChild(el("div", "hb-yt-chhandle", m.title || pg.name));
  else if(sub) info.appendChild(el("div", "hb-yt-chhandle", sub));
  head.appendChild(info);
  const status = el("div", "hb-yt-chstatus");
  if(Y.chBusy === "refresh"){
    status.appendChild(el("span", "hb-yt-spin"));
    status.appendChild(el("span", "", tt("ch_refreshing", null, "Buscando últimos vídeos del canal…")));
  } else if(pg.refreshed_at){
    const n = (pg.new_ids || []).length;
    status.appendChild(el("span", "", n ? tt("ch_new_n", {n}, "{n} nuevos") + " · " + relAge(pg.refreshed_at, ctx)
                                        : tt("ch_updated", {when: relAge(pg.refreshed_at, ctx)}, "Actualizado {when}")));
    const rf = el("button", "hb-yt-sbtn");
    rf.appendChild(el("span", "", "↻"));
    rf.title = tt("ch_refresh", null, "Buscar vídeos nuevos");
    rf.setAttribute("aria-label", rf.title);
    rf.addEventListener("click", () => chAct(root, ctx, "refresh_channel", {}, "refresh"));
    status.appendChild(rf);
  }
  head.appendChild(status);
  wrap.appendChild(head);

  if(!pg.playlist){
    const tabs = el("div", "hb-yt-subtabs");
    (pg.tabs || []).forEach((t) => {
      const b = el("button", "hb-yt-subtab" + (t === pg.tab ? " on" : ""), sectionLabel(t));
      b.dataset.section = t;
      b.addEventListener("click", () => { if(t !== pg.tab) chAct(root, ctx, "channel_tab", {tab: t}, "tab"); });
      tabs.appendChild(b);
    });
    wrap.appendChild(tabs);
  }

  const items = Array.isArray(pg.items) ? pg.items : [];
  if(Y.chBusy === "tab" || (!items.length && (Y.chBusy === "refresh" || !pg.loaded))){
    const msg = el("div", "hb-yt-chmsg");
    msg.appendChild(el("span", "hb-yt-spin"));
    msg.appendChild(el("span", "", Y.chBusy === "refresh" ? tt("ch_refreshing", null, "Buscando últimos vídeos del canal…")
                                                         : tt("ch_loading_more", null, "cargando…")));
    wrap.appendChild(msg);
    box.appendChild(wrap);
    return;
  }
  if(!items.length){
    wrap.appendChild(el("div", "hb-yt-chmsg", tt("ch_empty", null, "El canal no tiene nada en esta sección.")));
    box.appendChild(wrap);
    return;
  }
  const isShorts = !pg.playlist && pg.tab === "shorts";
  const grid = el("div", "hb-yt-vgrid" + (isShorts ? " shorts" : ""));
  const now = Date.now() / 1000;
  items.forEach((it) => {
    const tile = el("div", "hb-yt-tile");
    tile.tabIndex = 0;
    tile.setAttribute("role", "button");
    const th = el("div", "hb-yt-thumb");
    const img = document.createElement("img");
    img.loading = "lazy"; img.alt = "";
    if(it.kind === "playlist") img.src = it.thumb || "";
    else img.src = "https://i.ytimg.com/vi/" + encodeURIComponent(it.id) + (isShorts ? "/hqdefault.jpg" : "/mqdefault.jpg");
    th.appendChild(img);
    const age = it.ts ? now - Number(it.ts) : Infinity;
    if(it.live) th.appendChild(el("span", "hb-yt-flag live", tt("flag_live", null, "EN DIRECTO")));
    else if(age < DAY) th.appendChild(el("span", "hb-yt-flag d1", tt("flag_24h", null, "24 h")));
    else if(age < 3 * DAY) th.appendChild(el("span", "hb-yt-flag d3", tt("flag_72h", null, "72 h")));
    if(it.duration) th.appendChild(el("span", "hb-yt-dur", it.duration));
    if(it.kind === "playlist" && it.count) th.appendChild(el("span", "hb-yt-dur", tt("n_videos", {n: it.count}, "{n} vídeos")));
    if(it.kind !== "playlist"){
      const addB = el("button", "hb-yt-radd", tt("to_queue", null, "+ cola"));
      addB.title = tt("to_queue_hint", null, "Añadir a la cola sin reproducir");
      addB.addEventListener("click", (e) => {
        e.stopPropagation();
        if(ctx && ctx.action) ctx.action("add", {url: it.id});
      });
      th.appendChild(addB);
    }
    tile.appendChild(th);
    tile.appendChild(el("div", "hb-yt-tilet", it.title || "—"));
    const meta = [];
    if(it.views) meta.push(tt("n_views", {n: fmtNum(it.views, ctx)}, "{n} visualizaciones"));
    if(it.ts) meta.push(relAge(it.ts, ctx));
    if(meta.length) tile.appendChild(el("div", "hb-yt-tilem", meta.join(" · ")));
    const go = () => {
      if(it.kind === "playlist"){ chAct(root, ctx, "channel_playlist", {playlist: it.id, title: it.title}, "tab"); return; }
      if(ctx && ctx.action) ctx.action("load", {videoId: it.id, title: it.title || ""});
      if(root._hbYtSelectTab) root._hbYtSelectTab("player");
    };
    tile.addEventListener("click", go);
    tile.addEventListener("keydown", (e) => { if(e.key === "Enter"){ e.preventDefault(); go(); } });
    grid.appendChild(tile);
  });
  wrap.appendChild(grid);
  if(pg.has_more){
    const more = el("button", "hb-yt-btn hb-yt-more", Y.chBusy === "more" ? tt("ch_loading_more", null, "cargando…")
                                                                         : tt("ch_more", null, "Cargar más"));
    more.disabled = Y.chBusy === "more";
    more.addEventListener("click", () => chAct(root, ctx, "channel_more", {}, "more"));
    wrap.appendChild(more);
  }
  box.appendChild(wrap);
}
