// musica — the one bar (crumb, search, source chip), the screen shell, and the catalogue screens: search, artist
// and album (refactor2710-12 T-03).
import { nowPlaying, playbackBar } from "./controls.js";
import { panel, pill, trackRow } from "./playlist.js";
import { ICON_ADDLIST, ICON_BACK, ICON_LIST, ICON_NOTE, ICON_PLAY, ICON_QUEUE, ICON_SEARCH,
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

export function headerBar(el, data, ctx, kind, opts){
  opts = opts || {};
  const bar = h("div", "hb-mus2-headfix");
  if(opts.back){
    const back = h("button", "hb-mus2-back");
    back.appendChild(svgEl(ICON_BACK)); back.appendChild(h("span", null, tt("back", null, "Volver")));
    back.onclick = () => fire(ctx, "open_view", {kind: opts.back});
    bar.appendChild(back);
  } else if(nowPlaying(data)){
    // DERIVED: a switch with one side is a label, so with nothing sounding there is no switch at all.
    const seg = h("div", "hb-mus2-seg");
    seg.setAttribute("role", "tablist");   // one row of views — the phone never wraps it into a two-line pill
    const tab = (id, icon, label) => {
      const b = h("button", "hb-mus2-segb" + (kind === id ? " on" : ""));
      b.appendChild(svgEl(icon)); b.appendChild(h("span", null, label));
      b.onclick = () => fire(ctx, "open_view", {kind: id});
      return b;
    };
    seg.appendChild(tab("now", ICON_NOTE, tt("tab_now", null, "Sonando")));
    seg.appendChild(tab("library", ICON_LIST, tt("tab_library", null, "Tu música")));
    if(((data.queue || {}).items || []).length || kind === "queue")
      seg.appendChild(tab("queue", ICON_QUEUE, tt("tab_queue", null, "Cola")));
    bar.appendChild(seg);
  }
  if(opts.search){
    bar.appendChild(searchBox(el, data, ctx));
  }
  const right = h("div", "hb-mus2-right");
  if(!opts.search) right.appendChild(iconBtn(ICON_SEARCH, tt("search", null, "Buscar"),
                                             () => fire(ctx, "open_view", {kind: "search"})));
  right.appendChild(provChip(data, ctx));
  bar.appendChild(right);
  return bar;
}

// The search box keeps what is being typed across a re-render (an SSE update rebuilds the view under the finger).
export function searchBox(el, data, ctx){
  const box = h("div", "hb-mus2-sbox");
  box.appendChild(svgEl(ICON_SEARCH));
  const inp = h("input", "hb-mus2-sinp");
  inp.type = "search";
  inp.placeholder = tt("search_ph", null, "Canciones, artistas o álbumes");
  const last = ((data.browse || {}).search || {}).query || "";
  inp.value = el._hbDraft != null ? el._hbDraft : last;
  inp.addEventListener("input", () => { el._hbDraft = inp.value; });
  inp.addEventListener("keydown", (e) => {
    if(e.key === "Enter"){ const q = inp.value.trim(); if(q){ el._hbDraft = q; fire(ctx, "search", {query: q}); } }
  });
  box.appendChild(inp);
  // Focus only when the face was just opened or the box already had it: an SSE repaint must never pull the
  // keyboard away from whatever else he is typing in.
  if(el._hbFocusSearch) setTimeout(() => { try{ inp.focus(); }catch(_){} }, 0);
  return box;
}

export function shell(el, data, ctx, kind, opts){
  const wrap = h("div", "hb-mus2");
  wrap.appendChild(headerBar(el, data, ctx, kind, opts));
  const scroll = h("div", "hb-mus2-scroll");
  wrap.appendChild(scroll);
  return {wrap, scroll, done: () => { wrap.appendChild(playbackBar(el, data, ctx)); el._viewHost.appendChild(wrap); }};
}
// ── SEARCH: songs, artists, albums (and lists, where the catalogue has them) ─────────────────────────────
export function searchView(el, data, ctx){
  const s = shell(el, data, ctx, "search", {back: "library", search: true});
  const res = (data.browse || {}).search || {};
  const has = k => (res[k] || []).length;
  if(!res.query){
    s.scroll.classList.add("mid");
    s.scroll.appendChild(h("div", "hb-mus2-note", tt("search_hint", null, "Busca una canción, un artista o un álbum.")));
    s.done(); return;
  }
  if(!has("tracks") && !has("artists") && !has("albums") && !has("playlists")){
    s.scroll.appendChild(h("div", "hb-mus2-note", tt("no_results", {q: res.query}, "Nada para «{q}».")));
    s.done(); return;
  }
  if(has("tracks")){
    const sec = panel(tt("songs", null, "Canciones"), null, []);
    const g = h("div", "hb-mus2-grid");
    res.tracks.forEach(t => g.appendChild(trackRow(t, ctx, {data, addToList: true})));
    sec.appendChild(g); s.scroll.appendChild(sec);
  }
  if(has("artists")){
    const sec = panel(tt("artists", null, "Artistas"), null, []);
    const row = h("div", "hb-mus2-faces");
    res.artists.forEach(a => {
      const f = h("div", "hb-mus2-face");
      f.appendChild(artNode(a.art, ICON_NOTE));
      f.appendChild(h("div", "hb-mus2-facen", a.name));
      f.onclick = () => fire(ctx, "open_view", {kind: "artist", id: a.id, source: a.source, name: a.name});
      row.appendChild(f);
    });
    sec.appendChild(row); s.scroll.appendChild(sec);
  }
  if(has("albums")) s.scroll.appendChild(albumShelf(tt("albums", null, "Álbumes"), res.albums, ctx));
  if(has("playlists")){
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
