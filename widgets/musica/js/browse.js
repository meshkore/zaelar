// musica — the one bar (crumb, search, source chip), the screen shell, and the catalogue screens: search, artist
// and album (refactor2710-12 T-03).
import { maybeEnrich, nowPlaying, playback, playbackBar, reportPlayed } from "./controls.js";
import { bottomNav, miniPlayer, navTabs, sidebar } from "./layout.js";
import { soundRow } from "./players.js";
import { panel, pill, trackRow } from "./playlist.js";
import { ICON_ADDLIST, ICON_BACK, ICON_CLOSE, ICON_LIST, ICON_NOTE, ICON_PLAY, ICON_SEARCH,
  artNode, fire, h, iconBtn, svgEl, tt } from "./shared.js";

// The name of what is making sound — the same word the bar's chip shows, so the two never disagree.
export function sourceLabel(data){
  if((data.local || {}).src) return tt("local_src", null, "Tu biblioteca");
  if(data.mode === "spotify") return "Spotify";      // V2-812: the player making the sound, not the account held
  if((data.yt || {}).videoId) return "YouTube";
  return tt("no_source", null, "Sin fuente");
}

// ── THE ONE BAR ──────────────────────────────────────────────────────────────────────────────────────────
// The window chrome above already carries the mark, the name and the system buttons. This bar holds what could
// not live anywhere else: where you are (a back crumb, or the derived switch), and ONE right cluster — the
// search and the source chip.
export function provChip(data, ctx){
  const b = h("button", "hb-mus2-prov");
  const live = !!(data.mode === "spotify" || (data.yt || {}).videoId || (data.local || {}).src);
  b.appendChild(h("span", "hb-mus2-dot" + (live ? " on" : "")));
  b.appendChild(h("span", null, sourceLabel(data)));
  b.title = tt("sources", null, "Fuentes de música");
  b.onclick = () => fire(ctx, "open_view", {kind: "connect"});
  return b;
}

// Desktop: which sources exist and which one is sounding — YouTube is always there (free, no account), Spotify only
// once it is linked. One click on either opens the sources screen.
export function provIndicators(data, ctx){
  const box = h("div", "hb-mus2-provs");
  const src = sourceLabel(data);
  [["YouTube", true], ["Spotify", !!data.connected]].forEach(([name, ready]) => {
    const b = h("button", "hb-mus2-prov" + (src === name ? " live" : ""));
    b.appendChild(h("span", "hb-mus2-dot" + (ready ? " on" : "")));
    b.appendChild(h("span", null, name));
    b.title = ready ? tt("prov_ready", {name}, "{name}: listo") : tt("prov_off", {name}, "{name}: sin conectar");
    b.onclick = () => fire(ctx, "open_view", {kind: "connect"});
    box.appendChild(b);
  });
  return box;
}

export function backBtn(ctx, to){
  const back = h("button", "hb-mus2-back");
  back.appendChild(svgEl(ICON_BACK)); back.appendChild(h("span", null, tt("back", null, "Volver")));
  back.onclick = () => fire(ctx, "open_view", {kind: to});
  return back;
}

// The bar above the content, per layout. Desktop (wide/compact): where you are, a search field that is ALWAYS there,
// and the source indicators — navigation lives in the sidebar. Narrow window: the tab strip (or back), the source
// chip. Phone:
// the shell already draws a header, so the card draws NONE of its own — only a slim back row on a sub-page.
export function headerBar(el, data, ctx, kind, opts, L){
  opts = opts || {};
  const mode = (L || {}).mode || "narrow";
  if(mode === "mobile"){
    if(!opts.back) return null;
    const bar = h("div", "hb-mus2-headfix slim");
    bar.appendChild(backBtn(ctx, opts.back));
    return bar;
  }
  const bar = h("div", "hb-mus2-headfix");
  const desk = mode === "wide" || mode === "compact";
  if(opts.back) bar.appendChild(backBtn(ctx, opts.back));
  else if(!desk) bar.appendChild(navTabs(data, ctx, kind));
  if(desk) bar.appendChild(searchBox(el, data, ctx, kind));
  const right = h("div", "hb-mus2-right");
  right.appendChild(desk ? provIndicators(data, ctx) : provChip(data, ctx));
  bar.appendChild(right);
  return bar;
}

// The search box keeps what is being typed across a re-render (an SSE update rebuilds the view under the finger).
export function searchBox(el, data, ctx, kind){
  const box = h("div", "hb-mus2-sbox");
  box.appendChild(svgEl(ICON_SEARCH));
  const inp = h("input", "hb-mus2-sinp");
  inp.type = "search";
  inp.placeholder = tt("search_ph", null, "Canciones, artistas o álbumes");
  const last = ((data.browse || {}).search || {}).query || "";
  // The last query belongs to the search screen; elsewhere the always-there desktop field starts empty.
  inp.value = el._hbDraft != null ? el._hbDraft : (kind === "search" ? last : "");
  inp.addEventListener("input", () => { el._hbDraft = inp.value; });
  inp.addEventListener("keydown", (e) => {
    if(e.key === "Enter"){
      const q = inp.value.trim();
      // Enter also lets the phone's keyboard go: the results are what he wants to see now, not the keys.
      if(q){ el._hbDraft = q; fire(ctx, "search", {query: q}); try{ inp.blur(); }catch(_){} }
    }
  });
  box.appendChild(inp);
  const clr = h("button", "hb-mus2-sclear");
  clr.appendChild(svgEl(ICON_CLOSE));
  clr.title = tt("clear", null, "Borrar"); clr.setAttribute("aria-label", tt("clear", null, "Borrar"));
  const showClr = () => { clr.style.visibility = inp.value ? "" : "hidden"; };
  inp.addEventListener("input", showClr); showClr();
  clr.onclick = () => { inp.value = ""; el._hbDraft = ""; showClr(); try{ inp.focus(); }catch(_){} };
  box.appendChild(clr);
  // Focus only when the face was just opened or the box already had it: an SSE repaint must never pull the
  // keyboard away from whatever else he is typing in.
  if(el._hbFocusSearch) setTimeout(() => { try{ inp.focus(); }catch(_){} }, 0);
  return box;
}

export function shell(el, data, ctx, kind, opts){
  const L = el._hbLayout || {mode: "narrow", land: false};
  const wrap = h("div", "hb-mus2 L-" + L.mode + (L.land ? " land" : ""));
  wrap.dataset.layout = L.mode;
  const body = h("div", "hb-mus2-body");
  if(L.mode === "wide" || L.mode === "compact") body.appendChild(sidebar(el, data, ctx, kind, L.mode));
  const main = h("div", "hb-mus2-main");
  const head = headerBar(el, data, ctx, kind, opts, L);
  if(head) main.appendChild(head);
  const scroll = h("div", "hb-mus2-scroll");
  main.appendChild(scroll);
  body.appendChild(main);
  wrap.appendChild(body);
  return {wrap, scroll, main, body, L, done: () => {
    if(L.mode === "mobile"){
      const np = nowPlaying(data);
      if(np){ maybeEnrich(np, ctx); reportPlayed(np, ctx); }
      const tap = soundRow(el, data);
      if(tap) wrap.appendChild(tap);
      // The expanded player carries the full controls; a mini-player under it would say the same thing twice.
      const expanded = kind === "now" || kind === "queue" || (kind === "home" && np);
      if(!expanded){ const m = miniPlayer(el, data, ctx, playback); if(m) wrap.appendChild(m); }
      wrap.appendChild(bottomNav(data, ctx, kind));
    } else {
      wrap.appendChild(playbackBar(el, data, ctx));
    }
    el._viewHost.appendChild(wrap);
  }};
}
// ── SEARCH: songs, artists, albums (and lists, where the catalogue has them) ─────────────────────────────
// The filter is a per-screen convenience (which KIND of result to look at), so it lives on the card element, not in
// the store: two screens can look at the same results through different filters.
const FILTERS = [["all", () => tt("f_all", null, "Todo")], ["tracks", () => tt("songs", null, "Canciones")],
                 ["artists", () => tt("artists", null, "Artistas")], ["albums", () => tt("albums", null, "Álbumes")],
                 ["playlists", () => tt("playlists_found", null, "Listas")]];

export function searchView(el, data, ctx){
  const L = el._hbLayout || {};
  const s = shell(el, data, ctx, "search", {search: true});
  const res = (data.browse || {}).search || {};
  const has = k => (res[k] || []).length;
  // The phone and the narrow window have no room for it in a bar: the field is the first thing in the screen.
  if(L.mode === "mobile" || L.mode === "narrow"){
    const top = h("div", "hb-mus2-stop");
    top.appendChild(searchBox(el, data, ctx, "search"));
    s.scroll.appendChild(top);
  }
  if(!res.query){
    s.scroll.appendChild(h("div", "hb-mus2-note mid", tt("search_hint", null, "Busca una canción, un artista o un álbum.")));
    s.done(); return;
  }
  if(!has("tracks") && !has("artists") && !has("albums") && !has("playlists")){
    s.scroll.appendChild(h("div", "hb-mus2-note", tt("no_results", {q: res.query}, "Nada para «{q}».")));
    s.done(); return;
  }
  const kinds = FILTERS.filter(([k]) => k === "all" || has(k));
  let f = el._hbFilter || "all";
  if(!kinds.some(([k]) => k === f)) f = "all";
  if(kinds.length > 2){
    const row = h("div", "hb-mus2-filters");
    row.setAttribute("role", "tablist");
    kinds.forEach(([k, label]) => {
      const b = h("button", "hb-mus2-filter" + (f === k ? " on" : ""), label());
      b.setAttribute("role", "tab"); b.setAttribute("aria-selected", f === k ? "true" : "false");
      b.onclick = () => { el._hbFilter = k; if(el._hbRedraw) el._hbRedraw(); };
      row.appendChild(b);
    });
    s.scroll.appendChild(row);
  }
  const show = k => has(k) && (f === "all" || f === k);
  if(show("tracks")){
    const sec = panel(tt("songs", null, "Canciones"), null, []);
    const g = h("div", "hb-mus2-grid");
    res.tracks.forEach(t => g.appendChild(trackRow(t, ctx, {data, addToList: true})));
    sec.appendChild(g); s.scroll.appendChild(sec);
  }
  if(show("artists")){
    const sec = panel(tt("artists", null, "Artistas"), null, []);
    const row = h("div", "hb-mus2-faces");
    res.artists.forEach(a => {
      const fc = h("div", "hb-mus2-face");
      fc.appendChild(artNode(a.art, ICON_NOTE));
      fc.appendChild(h("div", "hb-mus2-facen", a.name));
      fc.onclick = () => fire(ctx, "open_view", {kind: "artist", id: a.id, source: a.source, name: a.name});
      row.appendChild(fc);
    });
    sec.appendChild(row); s.scroll.appendChild(sec);
  }
  if(show("albums")) s.scroll.appendChild(albumShelf(tt("albums", null, "Álbumes"), res.albums, ctx));
  if(show("playlists")){
    const sec = panel(tt("playlists_found", null, "Listas"), null, []);
    const grid = h("div", "hb-mus2-lists");
    res.playlists.forEach(p => {
      const c = h("div", "hb-mus2-pl");
      c.appendChild(artNode(p.art, ICON_LIST));
      c.appendChild(h("div", "hb-mus2-plname", p.name));
      if(p.owner) c.appendChild(h("div", "hb-mus2-plsub", p.owner));
      c.onclick = () => fire(ctx, "play_album", {uri: p.uri, album: p.name});
      grid.appendChild(c);
    });
    sec.appendChild(grid); s.scroll.appendChild(sec);
  }
  s.done();
}

export function albumShelf(title, albums, ctx){
  const sec = panel(title, null, []);
  const grid = h("div", "hb-mus2-lists");
  albums.forEach(al => {
    const c = h("div", "hb-mus2-pl");
    c.appendChild(artNode(al.art, ICON_NOTE));
    c.appendChild(h("div", "hb-mus2-plname", al.name));
    c.appendChild(h("div", "hb-mus2-plsub", [al.year, al.artist].filter(Boolean).join(" · ")));
    const pp = h("button", "hb-mus2-plplay"); pp.appendChild(svgEl(ICON_PLAY));
    pp.title = tt("play", null, "Reproducir");
    pp.onclick = (e) => { e.stopPropagation(); fire(ctx, "play_album", {id: al.id, source: al.source, uri: al.uri,
                                                                         album: al.name, artist: al.artist}); };
    c.appendChild(pp);
    c.onclick = () => fire(ctx, "open_view", {kind: "album", id: al.id, source: al.source, name: al.name, artist: al.artist});
    grid.appendChild(c);
  });
  sec.appendChild(grid);
  return sec;
}

// ── AN ARTIST: face, name, the popular songs, the albums ─────────────────────────────────────────────────
export function artistView(el, data, ctx){
  const s = shell(el, data, ctx, "artist", {back: "search"});
  const page = (data.browse || {}).artist || {};
  const a = page.artist || {};
  const head = h("div", "hb-mus2-head");
  const wrap = h("div", "hb-mus2-artwrap");
  const face = artNode(a.art, ICON_NOTE); face.classList.add("round");
  wrap.appendChild(face);
  head.appendChild(wrap);
  const hm = h("div", "hb-mus2-headmeta");
  hm.appendChild(h("div", "hb-mus2-headk", tt("artist", null, "Artista")));
  hm.appendChild(h("div", "hb-mus2-headn", a.name || "—"));
  const acts = h("div", "hb-mus2-acts");
  if((page.top || []).length) acts.appendChild(pill(ICON_PLAY, tt("play", null, "Reproducir"),
    () => fire(ctx, "play_album", {kind: "artist", id: a.id, source: a.source, name: a.name})));
  hm.appendChild(acts);
  head.appendChild(hm);
  s.scroll.appendChild(head);
  if((page.top || []).length){
    const sec = panel(tt("popular", null, "Populares"), null, []);
    const g = h("div", "hb-mus2-grid");
    page.top.forEach((t, i) => g.appendChild(trackRow(t, ctx, {index: String(i + 1), data, addToList: true,
                                                                hideArtist: true})));
    sec.appendChild(g); s.scroll.appendChild(sec);
  }
  if((page.albums || []).length) s.scroll.appendChild(albumShelf(tt("albums", null, "Álbumes"), page.albums, ctx));
  s.done();
}

// ── AN ALBUM: cover, name, the artist (a door to the artist), year, its songs; play it, keep it as a list ──
export function albumView(el, data, ctx){
  const s = shell(el, data, ctx, "album", {back: "search"});
  const page = (data.browse || {}).album || {};
  const al = page.album || {};
  const tracks = page.tracks || [];
  const head = h("div", "hb-mus2-head");
  const wrap = h("div", "hb-mus2-artwrap");
  wrap.appendChild(artNode(al.art, ICON_NOTE));
  const play = h("button", "hb-mus2-playfab"); play.appendChild(svgEl(ICON_PLAY));
  play.title = tt("play", null, "Reproducir");
  if(!tracks.length) play.disabled = true;
  play.onclick = () => fire(ctx, "play_album", {id: al.id, source: al.source, uri: al.uri, album: al.name, artist: al.artist});
  wrap.appendChild(play);
  head.appendChild(wrap);
  const hm = h("div", "hb-mus2-headmeta");
  hm.appendChild(h("div", "hb-mus2-headk", tt("album", null, "Álbum")));
  hm.appendChild(h("div", "hb-mus2-headn", al.name || "—"));
  const who = h("div", "hb-mus2-plsub" + (al.artist ? " link" : ""),
                [al.artist, al.year, `${tracks.length} ${tracks.length === 1 ? tt("song_one", null, "canción") : tt("song_many", null, "canciones")}`]
                  .filter(Boolean).join(" · "));
  if(al.artist) who.onclick = () => fire(ctx, "open_view", {kind: "artist", name: al.artist});
  hm.appendChild(who);
  const acts = h("div", "hb-mus2-acts");
  if(tracks.length) acts.appendChild(pill(ICON_ADDLIST, tt("save_as_list", null, "Guardar como lista"),
    () => fire(ctx, "add_tracks", {playlist: al.name, tracks: tracks.slice(0, 25).map(t => ({title: t.title, artist: t.artist}))})));
  hm.appendChild(acts);
  head.appendChild(hm);
  s.scroll.appendChild(head);
  const sec = panel(tt("songs", null, "Canciones"), tracks.length || "", []);
  const g = h("div", "hb-mus2-grid");
  tracks.forEach((t, i) => g.appendChild(trackRow(t, ctx, {index: String(i + 1), data, addToList: true, hideArtist: true})));
  sec.appendChild(g); s.scroll.appendChild(sec);
  s.done();
}
