// musica — the home faces: the song as the screen, the library, the empty hero and the connect screen
// (refactor2710-12 T-03).
import { shell, sourceLabel } from "./browse.js";
import { maybeEnrich, nowPlaying, playback, seekRow } from "./controls.js";
import { coverOf, favList, panel, pill, rowState, trackRow } from "./playlist.js";
import { ICON_NOTE, ICON_PLAY, ICON_PLUS, artNode, eqIcon, fire, h, svgEl, tt } from "./shared.js";

// ── AHORA SUENA: the song IS the screen (V2-717) ─────────────────────────────────────────────────────────
export function nowView(el, data, ctx){
  const np = nowPlaying(data);
  const s = shell(el, data, ctx, "now");
  s.scroll.classList.add("mid");
  maybeEnrich(np, ctx);
  const box = h("div", "hb-mus2-now");
  const art = h("div", "hb-mus2-nowart");
  const fallback = () => { art.textContent = ""; art.appendChild(svgEl(ICON_NOTE)); };
  if(np.art){ const img = document.createElement("img"); img.src = np.art; img.alt = ""; img.onerror = fallback; art.appendChild(img); }
  else fallback();
  box.appendChild(art);
  box.appendChild(h("div", "hb-mus2-nowt", np.title || tt("music_fb", null, "Música")));
  const who = h("div", "hb-mus2-nowa" + (np.artist ? " link" : ""), np.artist || tt("unknown_artist", null, "Artista desconocido"));
  if(np.artist) who.onclick = () => fire(ctx, "open_view", {kind: "artist", name: np.artist});
  box.appendChild(who);
  const meta = h("div", "hb-mus2-nowm");
  if(np.playing) meta.appendChild(eqIcon());
  const facts = [];
  if(np.album) facts.push(np.album);
  facts.push(sourceLabel(data));
  if(np.device) facts.push(np.device);
  facts.forEach((f, i) => { if(i) meta.appendChild(h("i", null, "·")); meta.appendChild(h("span", null, f)); });
  box.appendChild(meta);
  // The scrubber has a SLOT of its own, usually empty until the player sends its first clock frame.
  const slot = h("div", "hb-mus2-seekslot");
  box.appendChild(slot);
  s.scroll.appendChild(box);
  s.done();
  el._hbTickers.push(() => {
    const pb = playback(el, data, ctx);
    if(!pb || !pb.dur){ if(slot.firstChild) slot.textContent = ""; return; }
    if(!slot.firstChild) slot.appendChild(seekRow(pb));
    else slot.firstChild.update(pb);
  });
}

// ── TU MÚSICA: lists + most played + recent, each a panel ────────────────────────────────────────────────
export function libraryView(el, data, ctx){
  const s = shell(el, data, ctx, "library");
  const np = nowPlaying(data);
  const bare = !(data.playlists || []).length && !(data.top || []).length && !(data.recent || []).length;
  if(bare){
    s.scroll.classList.add("mid");
    s.scroll.appendChild(emptyHero(data, ctx));
    s.done();
    return;
  }
  const fav = favList(data);
  const pls = (data.playlists || []).slice().sort((a, b) => (b === fav) - (a === fav));   // favourites first
  const secL = panel(tt("your_playlists", null, "Tus listas"), pls.length || "", []);
  const lists = h("div", "hb-mus2-lists");
  pls.forEach(pl => {
    const c = h("div", "hb-mus2-pl");
    c.appendChild(coverOf(pl, pl === fav));
    c.appendChild(h("div", "hb-mus2-plname", pl.name || tt("playlist", null, "Lista")));
    const n = (pl.tracks || []).length;
    c.appendChild(h("div", "hb-mus2-plsub", `${n} ${n === 1 ? tt("song_one", null, "canción") : tt("song_many", null, "canciones")}`));
    if(n){
      const pp = h("button", "hb-mus2-plplay"); pp.appendChild(svgEl(ICON_PLAY));
      pp.title = tt("play_playlist", null, "Reproducir esta lista");
      pp.onclick = (e) => { e.stopPropagation(); fire(ctx, "play_playlist", {playlist: pl.id}); };
      c.appendChild(pp);
    }
    c.onclick = () => fire(ctx, "open_view", {kind: "playlist", id: pl.id});
    lists.appendChild(c);
  });
  secL.right.appendChild(newListPill(secL, ctx));
  if(pls.length) secL.appendChild(lists);
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
  rows(tt("most_played", null, "Más escuchadas"), (data.top || []).slice(0, 5), true);
  rows(tt("recent", null, "Recientes"), (data.recent || []).slice(0, 8), false);
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
