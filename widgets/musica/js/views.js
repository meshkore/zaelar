// musica — the home faces: the song as the screen, the library, the empty hero and the connect screen
// (refactor2710-12 T-03).
import { provChip, shell, sourceLabel } from "./browse.js";
import { maybeEnrich, nowPlaying, playback, seekRow, transport } from "./controls.js";
import { addToListBtn, coverOf, favList, openMenu, panel, pill, queueBody, rowState, trackRow } from "./playlist.js";
import { ICON_HEART, ICON_HEART_FILL, ICON_MORE, ICON_NOTE, ICON_PAUSE, ICON_PLAY, ICON_PLUS, ICON_QUEUE, ICON_SEARCH,
  ICON_VOL_OFF, ICON_VOL_UP, _norm, artNode, eqIcon, fire, h, iconBtn, playOne, sourceOf, svgEl, tt } from "./shared.js";

// ── AHORA SUENA: the song IS the screen (V2-717) ─────────────────────────────────────────────────────────
// Desktop: the ficha in the middle, the transport stays in the bar at the foot (his own ask), and a wide card shows
// the queue beside it. Phone: ONE vertical stack — art, title, heart/add, the timeline, the five transport buttons
// with play as the big one, then queue and volume — sized against the HEIGHT that is there, so play is never pushed
// off the screen. A phone on its side puts the art on the left and the controls on the right.
export function nowView(el, data, ctx, opts){
  opts = opts || {};
  const np = nowPlaying(data);
  const s = shell(el, data, ctx, opts.kind || "now");
  const L = s.L;
  if(!np){
    s.scroll.classList.add("mid");
    s.scroll.appendChild(emptyHero(data, ctx));
    s.done();
    return s;
  }
  const phone = L.mode === "mobile";
  s.scroll.classList.add("mid");
  if(phone) s.scroll.classList.add("player");
  maybeEnrich(np, ctx);
  const box = h("div", "hb-mus2-now" + (phone ? " m" : "") + (phone && L.land ? " land" : ""));
  const art = h("div", "hb-mus2-nowart");
  const fallback = () => { art.textContent = ""; art.appendChild(svgEl(ICON_NOTE)); };
  if(np.art){ const img = document.createElement("img"); img.src = np.art; img.alt = ""; img.onerror = fallback; art.appendChild(img); }
  else fallback();
  // YouTube asks for its player to be SEEN while it plays: on this face the (persistent, never reloaded) embed is laid
  // over the art slot by the tick below; anywhere else it stays the hidden one — the limitation the notes record.
  const video = !!((data.yt || {}).videoId && !(data.local || {}).src && data.mode !== "spotify");
  if(video) art.classList.add("video");
  box.appendChild(art);
  const info = h("div", "hb-mus2-nowinfo");
  const words = h("div", "hb-mus2-nowwords");
  words.appendChild(h("div", "hb-mus2-nowt", np.title || tt("music_fb", null, "Música")));
  const who = h("div", "hb-mus2-nowa" + (np.artist ? " link" : ""), np.artist || tt("unknown_artist", null, "Artista desconocido"));
  if(np.artist) who.onclick = () => fire(ctx, "open_view", {kind: "artist", name: np.artist});
  words.appendChild(who);
  info.appendChild(words);
  const acts = h("div", "hb-mus2-nowacts");
  const fav = !!data.fav_current;
  acts.appendChild(iconBtn(fav ? ICON_HEART_FILL : ICON_HEART,
    fav ? tt("already_fav", null, "Ya está en Favoritos") : tt("save_fav", null, "Guardar en Favoritos"),
    () => fire(ctx, "favorite_current"), (phone ? "big" : "") + (fav ? " on" : "")));
  acts.appendChild(addToListBtn(np, data, ctx, phone ? "big" : ""));
  info.appendChild(acts);
  box.appendChild(info);
  if(!phone){
    const meta = h("div", "hb-mus2-nowm");
    if(np.playing) meta.appendChild(eqIcon());
    const facts = [];
    if(np.album) facts.push(np.album);
    facts.push(sourceLabel(data));
    if(np.device) facts.push(np.device);
    facts.forEach((f, i) => { if(i) meta.appendChild(h("i", null, "·")); meta.appendChild(h("span", null, f)); });
    box.appendChild(meta);
  }
  // The scrubber has a SLOT of its own, usually empty until the player sends its first clock frame. On the phone
  // the slot keeps its height either way, so the controls under it do not jump when the clock lands.
  const slot = h("div", "hb-mus2-seekslot");
  box.appendChild(slot);
  if(phone){
    box.appendChild(transport(data, ctx, np, "big").ctrls);
    box.appendChild(phoneExtras(el, data, ctx));
  }
  s.scroll.appendChild(box);
  if(L.mode === "wide" && opts.kind !== "queue") s.body.appendChild(queuePanel(data, ctx));
  s.done();
  el._hbTickers.push(() => {
    const pb = playback(el, data, ctx);
    if(!pb || !pb.dur){ if(slot.firstChild) slot.textContent = ""; }
    else if(!slot.firstChild) slot.appendChild(seekRow(pb));
    else slot.firstChild.update(pb);
    if(video) placeVideo(el, art);
  });
  return s;
}

// The embed is laid OVER the slot, never moved into it: re-parenting an iframe reloads it, and a reload restarts the
// song (the oldest rule of this card).
export function placeVideo(el, slot){
  const host = el._ytHost;
  if(!host || !el._hbFrame) return;
  if(!slot.isConnected){ host.classList.remove("vis"); host.removeAttribute("style"); return; }
  const r = slot.getBoundingClientRect(), rr = el.getBoundingClientRect();
  // YouTube's own floor for an embedded player is 200x200: below it the embed stays the hidden one and the cover
  // shows instead — a smaller visible player would be neither the cover nor a compliant player.
  if(r.width < 200 || r.height < 200){ host.classList.remove("vis"); host.removeAttribute("style"); return; }
  host.classList.add("vis");
  host.style.left = (r.left - rr.left) + "px"; host.style.top = (r.top - rr.top) + "px";
  host.style.width = r.width + "px"; host.style.height = r.height + "px";
}

// The phone's second row: the queue, and the volume as a compact popover (the device keys stay the main volume).
function phoneExtras(el, data, ctx){
  const row = h("div", "hb-mus2-nowx");
  const q = data.queue || {};
  const n = (q.items || []).length;
  const qb = h("button", "hb-mus2-nowxb");
  qb.appendChild(svgEl(ICON_QUEUE));
  qb.appendChild(h("span", null, tt("tab_queue", null, "Cola") + (n ? " · " + n : "")));
  qb.onclick = () => fire(ctx, "open_view", {kind: "queue"});
  row.appendChild(qb);
  row.appendChild(h("span", "hb-mus2-nowsrc", sourceLabel(data)));
  const vol = data.volume || {};
  const muted = !!vol.muted;
  const vb = iconBtn(muted ? ICON_VOL_OFF : ICON_VOL_UP, tt("volume", null, "Volumen"), () => {
    el._hbVolOpen = !el._hbVolOpen; pop.hidden = !el._hbVolOpen;
  }, "big");
  row.appendChild(vb);
  const pop = h("div", "hb-mus2-volpop");
  pop.hidden = !el._hbVolOpen;
  pop.appendChild(iconBtn(muted ? ICON_VOL_OFF : ICON_VOL_UP, muted ? tt("unmute", null, "Quitar silencio") : tt("mute", null, "Silenciar"),
                          () => fire(ctx, "set_volume", {mute: !muted}), "big"));
  const sl = h("input", "hb-mus2-vol");
  sl.type = "range"; sl.min = "0"; sl.max = "100";
  sl.value = String(muted ? 0 : (vol.level != null ? vol.level : 70));
  sl.setAttribute("aria-label", tt("volume", null, "Volumen"));
  sl.onchange = () => {
    fire(ctx, "set_volume", {level: Number(sl.value)});
    if(el._hbAudio){ try{ el._hbAudio.volume = Number(sl.value) / 100; }catch(_){} }
  };
  pop.appendChild(sl);
  const wrap = h("div", "hb-mus2-nowxw");
  wrap.append(row, pop);
  return wrap;
}

// ── THE QUEUE beside the song (wide desktop): what comes next, always in view, editable where the player allows it.
export function queuePanel(data, ctx){
  const side = h("aside", "hb-mus2-qpanel");
  side.appendChild(queueBody(data, ctx, {compact: true}));
  return side;
}

// ── INICIO: continue listening, your lists, recently played, favourites — each a panel, and a shelf that is empty
// is not drawn at all (an empty desktop-style panel on a phone is the screen this pass exists to remove).
export function libraryView(el, data, ctx, opts){
  opts = opts || {};
  const s = shell(el, data, ctx, opts.kind || "library");
  const np = nowPlaying(data);
  const bare = !(data.playlists || []).length && !(data.top || []).length && !(data.recent || []).length;
  if(s.L.mode === "mobile") s.scroll.appendChild(pageHead(tt("nav_home", null, "Inicio"), [provChip(data, ctx)]));
  if(bare && !np){
    s.scroll.classList.add("mid");
    s.scroll.appendChild(emptyHero(data, ctx));
    s.done();
    return;
  }
  const seen = new Set();
  const keyOf = t => _norm(t.title || t.query) + "|" + _norm(t.artist);
  const cont = [];
  if(np){ cont.push(Object.assign({}, np, {_current: true})); seen.add(keyOf(np)); }
  (data.recent || []).forEach(t => { const k = keyOf(t); if(cont.length < 8 && !seen.has(k)){ seen.add(k); cont.push(t); } });
  if(cont.length){
    const sec = panel(tt("continue", null, "Seguir escuchando"), null, []);
    const shelf = h("div", "hb-mus2-shelf");
    cont.forEach(t => shelf.appendChild(trackCard(t, data, ctx)));
    sec.appendChild(shelf); s.scroll.appendChild(sec);
  }
  const fav = favList(data);
  const pls = (data.playlists || []).slice().sort((a, b) => (b === fav) - (a === fav));   // favourites first
  const secL = panel(tt("your_playlists", null, "Tus listas"), pls.length || "", []);
  secL.right.appendChild(newListPill(secL, ctx));
  if(pls.length){
    const shelf = h("div", "hb-mus2-shelf");
    pls.forEach(pl => shelf.appendChild(listCard(pl, pl === fav, ctx)));
    secL.appendChild(shelf);
  }
  else secL.appendChild(h("div", "hb-mus2-note", tt("no_lists", null, "Aún no tienes listas. Crea una o dime «guárdame esta en una lista».")));
  s.scroll.appendChild(secL);
  const rows = (title, list, numbered) => {
    if(!list.length) return;
    const sec = panel(title, null, []);
    const g = h("div", "hb-mus2-grid");
    list.forEach((t, i) => g.appendChild(trackRow(t, ctx, {index: numbered ? String(i + 1) : null,
      ...rowState(t, np), data, addToList: true})));
    sec.appendChild(g); s.scroll.appendChild(sec);
  };
  rows(tt("recent", null, "Recientes"), (data.recent || []).slice(0, 8), false);
  rows(tt("favorites", null, "Favoritos"), ((fav || {}).tracks || []).slice(0, 5), false);
  s.done();
}

// A song as a square card on a shelf: the cover, a play button over it, title and artist. The song that is sounding
// opens the player instead of starting itself again.
function trackCard(t, data, ctx){
  maybeEnrich(t, ctx);
  const c = h("div", "hb-mus2-pl hb-mus2-card" + (t._current ? " current" : ""));
  const art = artNode(t.art, ICON_NOTE);
  c.appendChild(art);
  c.appendChild(h("div", "hb-mus2-plname", t.title || t.query || "—"));
  c.appendChild(h("div", "hb-mus2-plsub", t.artist || sourceOf(t) || ""));
  const pp = h("button", "hb-mus2-plplay"); pp.appendChild(svgEl(t._current && t.playing ? ICON_PAUSE : ICON_PLAY));
  pp.title = tt("play", null, "Reproducir"); pp.setAttribute("aria-label", pp.title);
  pp.onclick = (e) => { e.stopPropagation(); if(t._current) fire(ctx, t.playing ? "pause" : "resume"); else playOne(t, ctx); };
  art.appendChild(pp);
  c.onclick = () => { if(t._current) fire(ctx, "open_view", {kind: "now"}); else playOne(t, ctx); };
  return c;
}

// A list as a card: cover mosaic, name, how many songs, a play button and its menu (rename, shuffle, delete live on
// the list's own page — the menu is the way in on a screen with no hover).
export function listCard(pl, isFav, ctx){
  const c = h("div", "hb-mus2-pl");
  const cover = coverOf(pl, isFav);
  c.appendChild(cover);
  c.appendChild(h("div", "hb-mus2-plname", pl.name || tt("playlist", null, "Lista")));
  const n = (pl.tracks || []).length;
  c.appendChild(h("div", "hb-mus2-plsub", `${n} ${n === 1 ? tt("song_one", null, "canción") : tt("song_many", null, "canciones")}`));
  if(n){
    const pp = h("button", "hb-mus2-plplay"); pp.appendChild(svgEl(ICON_PLAY));
    pp.title = tt("play_playlist", null, "Reproducir esta lista"); pp.setAttribute("aria-label", pp.title);
    pp.onclick = (e) => { e.stopPropagation(); fire(ctx, "play_playlist", {playlist: pl.id}); };
    cover.appendChild(pp);
  }
  const more = iconBtn(ICON_MORE, tt("more", null, "Más opciones"), (e) => openMenu(e.currentTarget, [
    {label: tt("open", null, "Abrir"), run: () => fire(ctx, "open_view", {kind: "playlist", id: pl.id})},
    ...(n ? [{label: tt("play", null, "Reproducir"), run: () => fire(ctx, "play_playlist", {playlist: pl.id})},
             {label: tt("shuffle", null, "Aleatorio"), run: () => fire(ctx, "play_playlist", {playlist: pl.id, shuffle: true})}] : []),
  ]), "hb-mus2-plmore");
  c.appendChild(more);
  c.onclick = () => fire(ctx, "open_view", {kind: "playlist", id: pl.id});
  return c;
}

function pageHead(title, right){
  const head = h("div", "hb-mus2-phead");
  head.appendChild(h("div", "hb-mus2-pheadt", title));
  const r = h("div", "hb-mus2-pheadr");
  (right || []).forEach(x => x && r.appendChild(x));
  head.appendChild(r);
  return head;
}

// ── TU MÚSICA: lists, favourites, most played, recently played — one tab each, a filter over the open one ──────
const COLL_TABS = [["playlists", () => tt("playlists_found", null, "Listas")], ["favorites", () => tt("favorites", null, "Favoritos")],
                   ["top", () => tt("most_played", null, "Más escuchadas")], ["recent", () => tt("recent", null, "Recientes")]];

export function collectionView(el, data, ctx){
  const s = shell(el, data, ctx, "collection");
  const np = nowPlaying(data);
  const tab = COLL_TABS.some(([k]) => k === (data.view || {}).id) ? data.view.id : "playlists";
  const create = pill(ICON_PLUS, tt("new_short", null, "Nueva"), () => askName(create, (v) => fire(ctx, "create_playlist", {name: v})));
  create.classList.add("hb-mus2-new");
  s.scroll.appendChild(pageHead(tt("nav_collection", null, "Tu música"),
                                [create, s.L.mode === "mobile" ? provChip(data, ctx) : null]));
  const tabs = h("div", "hb-mus2-filters");
  tabs.setAttribute("role", "tablist");
  COLL_TABS.forEach(([k, label]) => {
    const b = h("button", "hb-mus2-filter" + (tab === k ? " on" : ""), label());
    b.setAttribute("role", "tab"); b.setAttribute("aria-selected", tab === k ? "true" : "false");
    b.onclick = () => { el._hbColFilter = ""; fire(ctx, "open_view", {kind: "collection", id: k}); };
    tabs.appendChild(b);
  });
  s.scroll.appendChild(tabs);
  const fbox = h("div", "hb-mus2-sbox hb-mus2-cfilter");
  fbox.appendChild(svgEl(ICON_SEARCH));
  const finp = h("input", "hb-mus2-sinp hb-mus2-cfinp");
  finp.type = "search"; finp.placeholder = tt("filter_ph", null, "Filtrar");
  finp.setAttribute("aria-label", tt("filter_ph", null, "Filtrar"));
  finp.value = el._hbColFilter || "";
  fbox.appendChild(finp);
  s.scroll.appendChild(fbox);
  const host = h("div", "hb-mus2-collbody");
  s.scroll.appendChild(host);
  const fav = favList(data);
  const paint = () => {
    host.textContent = "";
    const q = _norm(el._hbColFilter || "");
    const hit = (...xs) => !q || xs.some(x => _norm(x).includes(q));
    if(tab === "playlists"){
      const pls = (data.playlists || []).slice().sort((a, b) => (b === fav) - (a === fav)).filter(pl => hit(pl.name));
      if(!pls.length){ host.appendChild(h("div", "hb-mus2-note", q ? tt("no_match", null, "Nada coincide.")
        : tt("no_lists", null, "Aún no tienes listas. Crea una o dime «guárdame esta en una lista»."))); return; }
      const grid = h("div", "hb-mus2-lists two");
      pls.forEach(pl => grid.appendChild(listCard(pl, pl === fav, ctx)));
      host.appendChild(grid);
      return;
    }
    const list = tab === "favorites" ? ((fav || {}).tracks || []) : (tab === "top" ? (data.top || []) : (data.recent || []));
    const items = list.filter(t => hit(t.title, t.query, t.artist));
    if(!items.length){ host.appendChild(h("div", "hb-mus2-note", q ? tt("no_match", null, "Nada coincide.")
      : tt("coll_empty", null, "Aquí aún no hay nada."))); return; }
    const g = h("div", "hb-mus2-grid");
    items.forEach((t, i) => g.appendChild(trackRow(t, ctx, {index: tab === "top" ? String(i + 1) : null,
      ...rowState(t, np), data, addToList: true})));
    host.appendChild(g);
  };
  finp.addEventListener("input", () => { el._hbColFilter = finp.value; paint(); });
  paint();
  s.done();
}

// An empty library is the FIRST thing a new operator sees (V2-717): something to say and something real to press.
export function emptyHero(data, ctx){
  const hero = h("div", "hb-mus2-hero");
  const disc = h("div", "hb-mus2-herod");
  disc.appendChild(svgEl(ICON_NOTE));
  hero.appendChild(disc);
  hero.appendChild(h("div", "hb-mus2-herot", tt("empty_title", null, "Aquí vivirá tu música")));
  hero.appendChild(h("div", "hb-mus2-heros",
    tt("empty_sub", null, "Pídeme una canción y suena al momento. Lo que escuches irá apareciendo aquí, en Recientes y en Más escuchadas.")));
  const chips = h("div", "hb-mus2-chips");
  [tt("ex_1", null, "Pon música"), tt("ex_2", null, "Ponme a Frank Sinatra"), tt("ex_3", null, "Pon jazz tranquilo")]
    .forEach(q => {
      const c = h("button", "hb-mus2-chip", q);
      c.onclick = () => fire(ctx, "play", {query: q});
      chips.appendChild(c);
    });
  hero.appendChild(chips);
  const lists = h("div", "hb-mus2-lists");
  const card = h("div", "hb-mus2-pl hb-mus2-new");
  card.appendChild(artNode(null, ICON_PLUS));
  card.appendChild(h("div", "hb-mus2-plname", tt("new_playlist", null, "Nueva lista")));
  card.onclick = () => askName(card, (v) => fire(ctx, "create_playlist", {name: v}));
  lists.appendChild(card);
  hero.appendChild(lists);
  return hero;
}

// Inline: an input takes the place of the gesture; Enter or leaving it creates, Escape gives up.
export function askName(anchor, done, initial){
  const inp = h("input", "hb-mus2-inp hb-mus2-newinp");
  inp.placeholder = tt("name_ph", null, "Nombre");
  if(initial) inp.value = initial;
  anchor.replaceWith(inp);
  inp.focus(); if(initial) inp.select();
  let over = false;
  const submit = () => { if(over) return; over = true; const v = (inp.value || "").trim();
                         if(v && v !== initial) done(v); else inp.replaceWith(anchor); };
  inp.addEventListener("keydown", e => { if(e.key === "Enter") submit();
                                         if(e.key === "Escape"){ over = true; inp.replaceWith(anchor); } });
  inp.addEventListener("blur", submit);
  return inp;
}

export function newListPill(sec, ctx){
  const b = pill(ICON_PLUS, tt("new_short", null, "Nueva"), () => askName(b, (v) => fire(ctx, "create_playlist", {name: v})));
  b.classList.add("hb-mus2-new");
  return b;
}

// ── FUENTES: where the music comes from (V2-717) ─────────────────────────────────────────────────────────
export function connectView(el, data, ctx){
  const s = shell(el, data, ctx, "connect", {back: "library"});
  const sec = panel(tt("sources", null, "Fuentes de música"), null, []);
  sec.appendChild(h("div", "hb-mus2-sub", tt("free_source", null,
    "YouTube suena gratis y sin cuenta: ya está listo, no hay nada que conectar.")));
  if(data.connected){
    sec.appendChild(h("div", "hb-mus2-sub", tt("spotify_on", null,
      "Spotify está conectado: tu biblioteca y tus dispositivos ya están disponibles.")));
    const d = h("button", "hb-mus2-btn ghost", tt("manage_spotify", null, "Gestionar Spotify"));
    d.onclick = () => ctx.openConnector("spotify");
    sec.appendChild(d);
  } else {
    sec.appendChild(h("div", "hb-mus2-sub", tt("connect_hint", null,
      "Dime «pon música» o «ponme a Frank Sinatra» y suena gratis. Conecta tu Spotify (Premium) para tu biblioteca.")));
    // The connection itself lives in ⚙ Conectores (2026-10-04) — the one door the voice also opens.
    const b = h("button", "hb-mus2-btn", tt("connect_spotify", null, "Conectar Spotify"));
    b.onclick = () => ctx.openConnector("spotify");
    sec.appendChild(b);
  }
  s.scroll.appendChild(sec);
  s.done();
}
